"""Camera-guided, friction-only crocodile placement with a Menagerie SO-ARM101."""
from io import BytesIO
from pathlib import Path

import mujoco
import numpy as np
from PIL import Image

from so101_scene import MODEL_DIR
from so101_tabletop_ik import solve

SCENE = Path(__file__).parent / "models" / "crocodile_tabletop.xml"
PARK_DEG = (-75., -60., 60., 35., 0.)
FPS, SUBSTEPS = 30, 7
WIDTH, HEIGHT = 640, 480
ACTIONS = ("pick", "place", "park", "finish")
CAMERAS = ("front", "overhead", "left", "wrist")

GUIDE = """Place the entire green toy crocodile inside the blue rectangular outline on the
table. Its snout, feet, and tail tip all need to fit. Leave the toy resting and released.
Use the current overhead RGB to choose (u,v) in its 640 × 480 image; right increases u and
down increases v. Pick(u,v,angle) approaches the torso, closes the jaws and lifts. Choose
a pinch point on the torso clear of the legs. The jaw-closing axis is measured clockwise
from image right in degrees (0 horizontal, 90 vertical). The jaws should close across the
torso. Place(u,v,angle) brings the held pinch point over that table pixel, lowers the toy,
opens, and withdraws. The angle is an absolute jaw-closing axis in the overhead image.
Use the pick angle to keep the orientation, or rotate the toy to fit. Account for the
snout and tail relative to the pinch point. Park opens the gripper and moves it clear
for inspection. Robot motion acknowledgements describe only the arm. Inspect the
images to verify grasp and placement. Retry after a miss if needed. Finish submits."""


def _lookat(point, distance, azimuth, elevation):
    camera = mujoco.MjvCamera()
    camera.lookat[:] = point
    camera.distance, camera.azimuth, camera.elevation = distance, azimuth, elevation
    return camera


class CrocodileSimulation:
    def __init__(self, seed):
        scene = mujoco.MjSpec.from_file(str(SCENE))
        arm = mujoco.MjSpec.from_file(str(MODEL_DIR / "so101.xml"))
        for mat in arm.materials:
            if not mat.name.startswith("sts3215"):
                mat.rgba = [.30, .62, .68, 1.]
        scene.attach(arm, site="so101_mount", prefix="")
        self.model = scene.compile()
        self.data = mujoco.MjData(self.model)
        self.qadr = self.model.jnt_qposadr[self.model.actuator_trnid[:, 0]]
        jaw_min, jaw_max = self.model.actuator_ctrlrange[-1]
        self.open_jaw = jaw_min + .36 * (jaw_max - jaw_min)
        self.park = np.r_[np.deg2rad(PARK_DEG), self.open_jaw]
        self.data.qpos[self.qadr] = self.data.ctrl[:] = self.park
        self.toy = self.model.body("crocodile").id
        self.target = self.model.body("target").id
        self.toy_geoms = np.flatnonzero(self.model.geom_bodyid == self.toy)
        toy_joint = self.model.body_jntadr[self.toy]
        self.toy_dof = self.model.jnt_dofadr[toy_joint]
        self.table = self.model.geom("table").id
        self.jaws = {self.model.body("gripper").id, self.model.body("moving_jaw_so101_v1").id}
        self.renderer = None
        self.views = {
            "overhead": "top", "wrist": "wrist_cam",
            "front": _lookat([.18, 0., .06], .64, 118., -37.),
            "left": _lookat([.20, .035, .025], .43, -63., -33.),
        }
        self.callback = None
        self.last_frame_time = 0.
        self.rest_seconds = 0.
        self.lifted = self.released = self.supported = False
        self.peak_height = 0.
        # Only the fixture sets scene objects; every actor motion uses the actuators.
        q = self.model.jnt_qposadr[toy_joint]
        rng = np.random.default_rng(seed)
        for xy, quaternion in ((self.data.qpos[q:q+2], self.data.qpos[q+3:q+7]),
                               (self.model.body_pos[self.target, :2], self.model.body_quat[self.target])):
            half_yaw = np.deg2rad(rng.uniform(-9., 9.)) / 2
            xy += rng.uniform(-.009, .009, 2)
            quaternion[:] = [np.cos(half_yaw), 0., 0., np.sin(half_yaw)]
        mujoco.mj_forward(self.model, self.data)
        for _ in range(FPS):
            mujoco.mj_step(self.model, self.data, nstep=SUBSTEPS)
            self._measure()
        self.data.time = 0.
        mujoco.mj_forward(self.model, self.data)
        self.initial_clearance = float(self.clearances().min())

    def robot_state(self):
        q = self.data.qpos[self.qadr]
        return {"joint_positions_rad": q[:5].tolist(), "gripper_angle_rad": float(q[5]),
                "sim_time": round(float(self.data.time), 6)}

    def set_frame_callback(self, callback):
        self.callback = callback

    def observe(self, camera):
        if self.renderer is None:
            self.renderer = mujoco.Renderer(self.model, height=HEIGHT, width=WIDTH)
        self.renderer.update_scene(self.data, camera=self.views[camera])
        image = Image.fromarray(self.renderer.render())
        with BytesIO() as buf:
            image.save(buf, format="PNG")
            return buf.getvalue()

    def move(self, goal, duration):
        initial = self.data.ctrl.copy()
        ticks = round(duration * FPS)
        for tick in range(1, ticks + round(.30 * FPS) + 1):
            t = min(tick / ticks, 1.)
            self.data.ctrl[:] = initial + t*t*(3-2*t)*(goal-initial)
            mujoco.mj_step(self.model, self.data, nstep=SUBSTEPS)
            self._measure()
            if self.callback and self.data.time - self.last_frame_time >= .35:
                self.last_frame_time = float(self.data.time)
                self.callback()
        mujoco.mj_forward(self.model, self.data)

    def _measure(self):
        contacts = set()
        for contact in self.data.contact:
            if contact.efc_address < 0 or contact.dist > 0:
                continue
            a, b = contact.geom
            if self.model.geom_bodyid[a] == self.toy:
                contacts.add(b)
            elif self.model.geom_bodyid[b] == self.toy:
                contacts.add(a)
        self.supported = self.table in contacts
        self.released = all(self.model.geom_bodyid[g] == 0 for g in contacts)
        height = float(self.data.xpos[self.toy, 2])
        self.peak_height = max(self.peak_height, height)
        self.lifted |= bool(height > .035 and not self.supported
                            and self.jaws.intersection(self.model.geom_bodyid[g] for g in contacts))
        twist = self.data.qvel[self.toy_dof:self.toy_dof+6]
        resting = np.linalg.norm(twist[:3]) <= .009 and np.linalg.norm(twist[3:]) <= .12
        self.rest_seconds = self.rest_seconds + 1/FPS if resting and self.supported and self.released else 0.

    def clearances(self):
        """Calculate all 27 geoms' exact projected extents in the rectangle's local frame."""
        axes = self.data.xmat[self.target].reshape(3, 3)[:, :2].T
        origin = self.data.xpos[self.target]
        edges = []
        geom_type = mujoco.mjtGeom
        for gid in self.toy_geoms:
            center = axes @ (self.data.geom_xpos[gid] - origin)
            rotation = axes @ self.data.geom_xmat[gid].reshape(3, 3)
            size = self.model.geom_size[gid]
            shape = self.model.geom_type[gid]
            if shape == geom_type.mjGEOM_MESH:
                mid = self.model.geom_dataid[gid]
                first, count = self.model.mesh_vertadr[mid], self.model.mesh_vertnum[mid]
                projected = self.model.mesh_vert[first:first+count] @ rotation.T + center
                edges.append((projected.min(axis=0), projected.max(axis=0)))
                continue
            if shape == geom_type.mjGEOM_ELLIPSOID:
                radius = np.linalg.norm(rotation * size, axis=1)
            elif shape == geom_type.mjGEOM_BOX:
                radius = np.abs(rotation) @ size
            elif shape == geom_type.mjGEOM_CAPSULE:
                radius = size[0] + np.abs(rotation[:, 2]) * size[1]
            elif shape == geom_type.mjGEOM_SPHERE:
                radius = np.full(2, size[0])
            else:
                raise ValueError(f"Unsupported toy geometry {shape}")
            edges.append((center-radius, center+radius))
        lo, hi = np.min([e[0] for e in edges], axis=0), np.max([e[1] for e in edges], axis=0)
        a, b, c, d = (self.model.geom(n) for n in ("end_a", "end_b", "side_a", "side_b"))
        return np.array([lo[0] - (a.pos[0]+a.size[0]), b.pos[0]-b.size[0]-hi[0],
                         lo[1] - (c.pos[1]+c.size[1]), d.pos[1]-d.size[1]-hi[1]])

    def finish(self):
        margins = self.clearances()
        inside = bool(np.all(margins >= 0))
        settled = self.rest_seconds >= .2
        return {"success": bool(inside and settled), "entirely_inside": inside,
                "settled": settled, "released": self.released, "supported_by_table": self.supported,
                "min_clearance_mm": round(float(margins.min()) * 1000, 3),
                "edge_clearances_mm": dict(zip(("end_a", "end_b", "side_a", "side_b"),
                                               (margins * 1000).round(3).tolist())),
                "initial_min_clearance_mm": round(self.initial_clearance * 1000, 3),
                "geometries_checked": len(self.toy_geoms), "lifted": self.lifted,
                "peak_toy_origin_height_mm": round(self.peak_height * 1000, 3),
                "settled_seconds": round(self.rest_seconds, 3), "sim_time_s": round(float(self.data.time), 3)}

    def close(self):
        if self.renderer:
            self.renderer.close()
            self.renderer = None


class CrocodileControls:
    def __init__(self, sim):
        self.sim = sim
        # Robot-only model for IK. Neither targets nor toy geometry are available to the solver.
        self.kinematics = mujoco.MjModel.from_xml_path(str(MODEL_DIR / "so101.xml"))
        camera = sim.model.camera("top")
        self.camera_origin = camera.pos.copy()
        self.camera_rotation = sim.data.cam_xmat[camera.id].reshape(3, 3).copy()
        self.focal = .5 * HEIGHT / np.tan(np.deg2rad(camera.fovy.item()) / 2)

    def _point(self, u, v, z):
        ray = self.camera_rotation @ [(u-(WIDTH-1)/2)/self.focal, -(v-(HEIGHT-1)/2)/self.focal, -1.]
        return (self.camera_origin + ray * ((z-self.camera_origin[2]) / ray[2]))[:2]

    def _waypoint(self, xy, axis, height, opening, seconds):
        current = self.sim.robot_state()["joint_positions_rad"]
        arm_joints = solve(self.kinematics, current, [*xy, height], axis)
        low, high = self.kinematics.actuator_ctrlrange[-1]
        jaw = low + opening / 100 * (high-low)
        self.sim.move(np.r_[arm_joints, jaw], seconds)

    def execute(self, decision):
        action = decision["action"]
        if action == "park":
            self.sim.move(self.sim.park, .9)
            return "Arm parked with open jaws."
        if action == "finish":
            return "Submitted for grading."
        if action not in ("pick", "place"):
            raise ValueError("Choose pick, place, park or finish.")
        u, v, deg = (decision[k] for k in ("u", "v", "angle"))
        if not (0 <= u < WIDTH and 0 <= v < HEIGHT and np.isfinite(deg)):
            raise ValueError("Choose a valid overhead pixel and jaw angle.")
        z = .028 if action == "pick" else .001
        xy = self._point(u, v, z)
        if not (.08 <= xy[0] <= .34 and -.2 <= xy[1] <= .2):
            raise ValueError("Selected pixel is outside the arm workspace.")
        angle = np.deg2rad(deg)
        direction = self._point(u+np.cos(angle), v+np.sin(angle), z) - xy
        # An opposed-jaw axis is periodic every 180 degrees.
        world_angle = np.arctan2(direction[1], direction[0]) % np.pi
        axis = np.array([np.cos(world_angle), np.sin(world_angle), 0.])
        xy -= .004 * axis[:2]   # Asymmetric SO-101 jaw contact-center offset.
        if action == "pick":
            path = ((.080,36),(.045,36),(.024,36),(.021,33),(.021,14),(.021,0),
                    (.040,0),(.062,0),(.078,0))
            for height, opening in path:
                self._waypoint(xy, axis, height, opening, .4)
        else:
            for height, opening, seconds in ((.076,0,.9),(.030,0,.55),(.030,36,.48),(.076,36,.45)):
                self._waypoint(xy, axis, height, opening, seconds)
        return f"{action.capitalize()} trajectory completed. Inspect the camera views."


def create(seed):
    sim = CrocodileSimulation(seed)
    return sim, CrocodileControls(sim), GUIDE
