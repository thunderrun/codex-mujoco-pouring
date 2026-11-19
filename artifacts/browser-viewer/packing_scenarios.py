"""SO-ARM101 tabletop manipulation using RGB-selected jaw targets and contact physics."""

import math
import xml.etree.ElementTree as ET

import mujoco
import numpy as np
from PIL import Image

from so101_crocodile import FPS, PARK_DEG, SUBSTEPS, CrocodileControls, _lookat
from so101_scene import MODEL_DIR

BASE = """<mujoco model="so101_tabletop">
<compiler angle="radian"/>
<option integrator="implicitfast" timestep=".004761904761904762" cone="elliptic" iterations="32" impratio="10"/>
<visual><headlight diffuse=".45 .45 .45" ambient=".30 .30 .30" specular=".05 .05 .05"/></visual>
<asset/><worldbody>
<light pos="0 0 2" dir="0 0 -1" directional="true"/>
<geom name="table" type="box" size=".38 .35 .014" pos=".19 0 -.014" rgba=".76 .70 .58 1"/>
<geom type="plane" size="1 1 .05" pos="0 0 -.65" rgba=".37 .40 .42 1"/>
<site name="so101_mount" pos="0 0 0"/>
<camera name="top" pos=".205 0 .52" xyaxes="0 -1 0 1 0 0" fovy="44"/>
</worldbody></mujoco>"""
COLORS = {
    "red": ".86 .12 .09 1",
    "blue": ".09 .35 .86 1",
    "green": ".10 .62 .22 1",
    "yellow": ".94 .70 .06 1",
}
WOOD = ".48 .28 .16 1"
TIDY_GUIDE = """Put all four colored blocks completely inside the open brown box. Finally
put the removable teal lid flat on the box with its four edges flush and release it.
The overhead grid is 640 by 480. Choose absolute pixel centers. The arm uses a
vertical friction pinch: pick(u,v,angle) lifts a block from the table, and place(u,v,angle)
gently drops it into the box at a point you choose. Use four separate quadrants.
Use pick_lid(u,v,angle) on the CENTER of the raised pale handle on the teal lid,
and place_lid(u,v,angle) at the CENTER of the open box. The housing and lid long
axes should match. The lid handle and the cubes are designed to be grasped with
the jaw-closing axis across their flat sides. The angle is clockwise in the
overhead view, 0 for horizontal and 90 for vertical. The IK accepts either
direction on that axis. Keep the same grasp and release angle to retain orientation.
The saved initial overhead image remains available if a moving jaw obscures a target.
Place actions withdraw the gripper. Inspect the images after each motion; press
finish to submit. Park is optional. Motion feedback only confirms robot movement."""


def fmt(values):
    return " ".join(f"{v:.9g}" for v in values)


def box(body, name, half, pos, color, mass=None, **props):
    attrs = {
        "name": name,
        "type": "box",
        "size": fmt(half),
        "pos": fmt(pos),
        "rgba": color,
        "friction": "1.2 .012 .001",
        "solref": ".008 1",
        **props,
    }
    if mass is not None:
        attrs["mass"] = str(mass)
    return ET.SubElement(body, "geom", attrs)


def body(world, name, xyz, yaw=0, free=False):
    item = ET.SubElement(world, "body", name=name, pos=fmt(xyz), euler=f"0 0 {yaw}")
    if free:
        ET.SubElement(item, "freejoint")
    return item


class Tidying:
    guide = TIDY_GUIDE
    actions = ("pick", "place", "pick_lid", "place_lid", "park", "finish")
    cubes = tuple(COLORS)
    half = 0.011
    inside = np.array([0.044, 0.050])
    rim = 0.032

    def build(self, root, world, rng):
        self.center = np.array([0.201, 0.088]) + rng.uniform(-0.003, 0.003, 2)
        case = body(world, "box", [*self.center, 0])
        a, b = self.inside
        box(case, "floor", [a + 0.004, b + 0.004, 0.002], [0, 0, 0.002], ".67 .48 .31 1")
        for sign in (-1, 1):
            box(case, f"wx{sign}", [0.002, b + 0.004, 0.014], [sign * (a + 0.002), 0, 0.018], WOOD)
            box(case, f"wy{sign}", [a, 0.002, 0.014], [0, sign * (b + 0.002), 0.018], WOOD)
        positions = [(0.172, -0.032), (0.221, -0.032), (0.173, -0.079), (0.226, -0.080)]
        rng.shuffle(positions)
        for name, (x, y) in zip(self.cubes, positions):
            off = rng.uniform(-0.002, 0.002, 2)
            block = body(world, name, [x + off[0], y + off[1], self.half + 0.0002], free=True)
            box(block, name + "_geom", [self.half] * 3, [0, 0, 0], COLORS[name], 0.010)
        lid = body(world, "lid", [0.175, -0.160, 0.0033], free=True)
        box(lid, "panel", [a + 0.004, b + 0.004, 0.003], [0, 0, 0], ".12 .51 .57 1", 0.017)
        box(lid, "handle", [0.009, 0.011, 0.009], [0, 0, 0.012], ".79 .95 .89 1", 0.003)

    def pick_place(self, action):
        # Overhead observation plane, target gripper height, transit height, jaw opening.
        return {
            "pick": (0.022, 0.017, 0.078, 35),
            "place": (0.004, 0.031, 0.085, 35),
            "pick_lid": (0.027, 0.019, 0.091, 35),
            "place_lid": (0.032, 0.052, 0.092, 35),
        }[action]

    def grade(self, sim):
        m, d = sim.model, sim.data
        packed = []
        for name in self.cubes:
            g = m.geom(name + "_geom").id
            center = d.geom_xpos[g]
            extent = np.abs(d.geom_xmat[g].reshape(3, 3)) @ m.geom_size[g]
            inside = np.all(abs(center[:2] - self.center) + extent[:2] <= self.inside + 0.0002)
            below = center[2] + extent[2] <= self.rim + 0.0005 and center[2] - extent[2] >= 0.003
            if inside and below and sim.settled_and_released(name):
                packed.append(name)
        lid = d.xpos[m.body("lid").id]
        r = d.xmat[m.body("lid").id].reshape(3, 3)
        offset = float(np.max(abs(lid[:2] - self.center)))
        panel_half = m.geom("panel").size
        # Compare all four bottom corners to the corresponding rim corners.
        half_turn = 1 if r[0, 0] >= 0 else -1
        worst_horizontal = 0.0
        worst_vertical = 0.0
        for x, y in ((-1, -1), (-1, 1), (1, -1), (1, 1)):
            corner = lid + r @ [x * panel_half[0], y * panel_half[1], -panel_half[2]]
            reference = self.center + half_turn * np.array([x * panel_half[0], y * panel_half[1]])
            worst_horizontal = max(worst_horizontal, float(np.linalg.norm(corner[:2] - reference)))
            worst_vertical = max(worst_vertical, abs(float(corner[2] - self.rim)))
        flush = bool(
            worst_horizontal <= 0.004
            and worst_vertical <= 0.0015
            and r[2, 2] > 0.998
            and sim.settled_and_released("lid")
        )
        success = len(packed) == 4 and flush
        return dict(
            success=success,
            score=100 if success else 20 * len(packed),
            summary=f"{len(packed)}/4 blocks packed; lid {'flush' if flush else 'not flush'}.",
            packed_count=len(packed),
            packed=packed,
            lid_flush=flush,
            lid_center_offset_mm=round(offset * 1000, 3),
            maximum_lid_corner_offset_mm=round(worst_horizontal * 1000, 3),
            maximum_lid_height_error_mm=round(worst_vertical * 1000, 3),
        )


class PackingScenario:
    def __init__(self, fixture, seed):
        self.fixture = fixture
        self.guide, self.actions = fixture.guide, fixture.actions
        self.fields = getattr(fixture, "fields", None)
        if hasattr(fixture, "reference_image"):
            self.reference_image = fixture.reference_image
        root = ET.fromstring(BASE)
        fixture.build(root, root.find("worldbody"), np.random.default_rng(seed))
        self.model = mujoco.MjModel.from_xml_string(self._assembled_xml(root), assets=self._assets)
        del self._assets
        self.data = mujoco.MjData(self.model)
        self.qadr = self.model.jnt_qposadr[self.model.actuator_trnid[:, 0]]
        low, high = self.model.actuator_ctrlrange[-1]
        self.park = np.r_[np.deg2rad(PARK_DEG), low + 0.36 * (high - low)]
        self.data.qpos[self.qadr] = self.data.ctrl[:] = self.park
        self.renderer = None
        self.callback = None
        self.last_frame = 0.0
        self.views = {
            "overhead": "top",
            "front": _lookat([0.20, 0, 0.035], 0.60, 112.0, -40.0),
            "left": _lookat([0.21, 0.015, 0.028], 0.53, -66.0, -40.0),
            "wrist": "wrist_cam",
        }
        mujoco.mj_forward(self.model, self.data)
        mujoco.mj_step(self.model, self.data, nstep=30 * SUBSTEPS)
        self.data.time = 0.0
        mujoco.mj_forward(self.model, self.data)
        self.controls = PackingControls(self)
        self.phase = "ready"

    def _assembled_xml(self, root):
        # Keep the source arm geometry, actuators, contacts and hand camera from Menagerie.
        arm = ET.parse(MODEL_DIR / "so101.xml").getroot()
        root.find("asset").extend(list(arm.find("asset")))
        for n in arm:
            if n.tag in ("default", "actuator", "contact", "equality", "tendon", "sensor"):
                root.append(n)
        root.find("worldbody").extend(list(arm.find("worldbody")))
        self._assets = {p.name: p.read_bytes() for p in (MODEL_DIR / "assets").glob("*.stl")}
        for mesh in root.findall("./asset/mesh"):
            if mesh.get("file"):
                mesh.set("file", mesh.get("file").split("/")[-1])
        return ET.tostring(root, encoding="unicode")

    def robot_state(self):
        q = self.data.qpos[self.qadr]
        return dict(
            joint_positions_rad=q[:5].tolist(),
            gripper_angle_rad=float(q[5]),
            sim_time=round(self.data.time, 6),
        )

    def move(self, target, seconds):
        start = self.data.ctrl.copy()
        ticks = max(1, round(seconds * FPS))
        for i in range(1, ticks + 7):
            t = min(1, i / ticks)
            self.data.ctrl[:] = start + (target - start) * t * t * (3 - 2 * t)
            mujoco.mj_step(self.model, self.data, nstep=SUBSTEPS)
            if self.callback and self.data.time - self.last_frame >= 0.50:
                self.last_frame = float(self.data.time)
                self.callback()
        mujoco.mj_forward(self.model, self.data)

    def set_frame_callback(self, cb):
        self.callback = cb

    def observe(self):
        if self.renderer is None:
            self.renderer = mujoco.Renderer(self.model, height=480, width=640)
        views = {}
        for k, cam in self.views.items():
            self.renderer.update_scene(self.data, camera=cam)
            views[k] = Image.fromarray(self.renderer.render())
        return views

    def settled_and_released(self, name):
        bid = self.model.body(name).id
        dof = self.model.jnt_dofadr[self.model.body_jntadr[bid]]
        twist = self.data.qvel[dof : dof + 6]
        if np.linalg.norm(twist[:3]) > 0.015 or np.linalg.norm(twist[3:]) > 0.20:
            return False
        for con in self.data.contact:
            if con.efc_address < 0 or con.dist > 0:
                continue
            a, b = self.model.geom_bodyid[con.geom]
            if (
                bid in (a, b)
                and self.model.body_rootid[b if a == bid else a] == self.model.body("base").id
            ):
                return False
        return True

    def execute(self, decision):
        return self.controls.execute(decision)

    def grade(self):
        return self.fixture.grade(self)

    def close(self):
        if self.renderer is not None:
            self.renderer.close()


class PackingControls(CrocodileControls):
    def execute(self, d):
        action = d["action"]
        if action == "park" and hasattr(self.sim.fixture, "park"):
            return self.sim.fixture.park(self.sim)
        if action in ("park", "finish"):
            return super().execute(d)
        if action not in self.sim.actions:
            raise ValueError("Select one of the available hand actions.")
        fixture = self.sim.fixture
        plane, height, lift, opening = (
            fixture.motion(action, d) if hasattr(fixture, "motion") else fixture.pick_place(action)
        )
        u, v, deg = d["u"], d["v"], d["angle"]
        if not (0 <= u < 640 and 0 <= v < 480 and math.isfinite(deg)):
            raise ValueError("Choose an overhead pixel and a finite jaw angle.")
        xy = self._point(u, v, plane)
        if not (0.08 < xy[0] < 0.34 and abs(xy[1]) < 0.20):
            raise ValueError("The selected point lies outside the arm workspace.")
        angle = math.radians(deg)
        ray = self._point(u + math.cos(angle), v + math.sin(angle), plane) - xy
        a = math.atan2(ray[1], ray[0]) % math.pi
        axis = np.array([math.cos(a), math.sin(a), 0.0])
        xy = xy + (-0.004 if action.startswith("pick") else 0.003) * axis[:2]
        pick = action.startswith("pick")
        path = (
            ((lift, opening, 0.62), (height, opening, 0.52), (height, 0, 0.42), (lift, 0, 0.55))
            if pick
            else ((lift, 0, 0.74), (height, 0, 0.48), (height, opening, 0.40), (lift, opening, 0.48))
        )
        for z, jaw, secs in path:
            self._waypoint(xy, axis, z, jaw, secs)
        return f"{action} trajectory completed. Inspect the cameras."


def create(task, seed, revision="v1"):
    if task == "tower":
        from tower_fixture import Tower

        return PackingScenario(Tower(revision), seed)
    if revision != "v1":
        raise ValueError("Unknown control revision.")
    if task == "shape_matching":
        from shape_fixture import ShapeMatching

        return PackingScenario(ShapeMatching(), seed)
    if task == "tidying":
        return PackingScenario(Tidying(), seed)
    raise ValueError("Unknown manipulation task.")
