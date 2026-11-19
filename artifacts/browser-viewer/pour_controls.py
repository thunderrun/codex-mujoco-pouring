"""Camera-selected pouring primitives for the public YAM robot model."""
import math
import os
import sys
from pathlib import Path

import mujoco
import numpy as np

from robo_mj_bench.protocol import HOME_JOINTS, JOINT_LIMITS, TIMESTEP

_viewer_root = Path(__file__).resolve().parents[2]
_sibling_checkout = _viewer_root / "benchmark"
_benchmark = Path(os.environ.get("ROBO_MJ_BENCH_DIR") or
                  (_sibling_checkout if _sibling_checkout.is_dir() else _viewer_root)).expanduser().resolve()
if not (_benchmark / "agent" / "robot_kinematics.py").is_file():
    raise ImportError("Set ROBO_MJ_BENCH_DIR to the benchmark checkout containing agent/robot_kinematics.py.")
sys.path.insert(0, str(_benchmark / "agent"))
from robot_kinematics import RobotKinematics


GUIDE = """Each fresh observation contains four camera views. The overhead image is
640 pixels wide by 480 high. From its original top-left corner u increases right,
v increases down. approach(u,v) opens the jaws and lowers them around the center
of the blue cup's TOP RIM you select. grasp closes the jaws; lift raises them for
inspection. align(u,v) carries the cup towards the center of the orange cup's
TOP RIM you select. You may refine align while upright. The controls account for
nominal rim height, gripper orientation and lip offset. tip(angle) requests an
ABSOLUTE wrist tilt, between 1 and 120 degrees, towards the receiver. You may
start with a smaller tilt and increase it after watching the beads. Upright is
0 degrees, and the normal stroke includes tilts past 90 degrees for emptying.
upright reverses the tilt; return lowers the gripper at the selected pickup site;
release opens it and backs away; park moves the arm clear. finish ends the trial
for independent grading. If a grasp appears empty after lifting, use return and
release before selecting a new source pixel. Use whole pixels. For unused fields
return zero. You decide when and where to move and when to finish. Motion
acknowledgements report robot commands and never imply a successful grasp or pour."""


def rim_xy(u, v):
    if not (0 <= u < 640 and 0 <= v < 480):
        raise ValueError("Choose a point within the 640 by 480 overhead image.")
    meters_per_pixel = (1.2 - .080) * 2 * math.tan(math.radians(58 / 2)) / 480
    return np.array([.3 + (u - 319.5) * meters_per_pixel, (239.5 - v) * meters_per_pixel])


def rotation_y(angle):
    c, s = np.cos(angle), np.sin(angle)
    return np.array([[c, 0, s], [0, 1, 0], [-s, 0, c]])


class PourControls:
    def __init__(self, sim):
        self.sim = sim
        self.kin = RobotKinematics()
        self.joints = np.array(HOME_JOINTS)
        self.phase = "parked"
        self.source = self.target = None
        self.tilt = 0.
        self.tip_path = []
        self.upright_joints = self.orientation = self.last_tip_joints = None

    def move(self, q, minimum_time=1.):
        limits = np.array(JOINT_LIMITS)
        q = np.clip(q, limits[:, 0], limits[:, 1])
        time_needed = max(minimum_time, float(np.max(np.abs(q - self.joints))) / 1.4)
        duration = math.ceil(time_needed / TIMESTEP) * TIMESTEP
        if duration > 5.0:
            raise ValueError("That pose is beyond this joint motion's travel.")
        self.sim.move_joints(q.tolist(), duration)
        self.joints = q.copy()
        self.sim.wait(.18)

    def down(self, xy, height):
        try:
            q = np.array(self.kin.downward_pose(*xy, height))
        except RuntimeError as error:
            raise ValueError("That camera point is outside the reachable downward-grasp workspace.") from error
        # Orient the linear fingers across an upright cup using robot geometry.
        q[5] += 1.50
        self.move(q)

    def forward(self, q):
        self.kin.data.qpos[self.kin.qadr] = q
        mujoco.mj_forward(self.kin.model, self.kin.data)

    def pose(self, target, orientation, q):
        kin = self.kin
        jac_p = np.empty((3, kin.model.nv))
        jac_r = jac_p.copy()
        for _ in range(180):
            self.forward(q)
            current = kin.data.site_xmat[kin.site].reshape(3, 3)
            relative = orientation @ current.T
            angular = .5 * np.array([relative[2, 1] - relative[1, 2],
                                     relative[0, 2] - relative[2, 0],
                                     relative[1, 0] - relative[0, 1]])
            linear = target - kin.data.site_xpos[kin.site]
            if np.linalg.norm(linear) < .0007 and np.linalg.norm(angular) < .003:
                break
            mujoco.mj_jacSite(kin.model, kin.data, jac_p, jac_r, kin.site)
            jac = np.vstack([jac_p[:, kin.vadr], .19 * jac_r[:, kin.vadr]])
            error = np.r_[linear, .19 * angular]
            delta = jac.T @ np.linalg.solve(jac @ jac.T + .00003 * np.eye(6), error)
            q = np.clip(q + delta * min(1, .16 / max(np.linalg.norm(delta), 1e-12)),
                        kin.limits[:, 0] + 1e-6, kin.limits[:, 1] - 1e-6)
        return q

    def roll_upright(self):
        for joints in reversed(self.tip_path[:-1]):
            self.move(joints, .7)
        if self.tip_path:
            self.move(self.upright_joints)
        self.tip_path.clear()
        self.tilt = 0.

    def roll_to(self, angle):
        if not 1 <= angle <= 120:
            raise ValueError("Select a tilt angle between 1 and 120 degrees, or use upright.")
        if angle < self.tilt:
            self.roll_upright()
        # Split the requested absolute roll into reach-limited segments about the
        # nominal cup lip. Store executed robot targets for the reversal.
        for degrees in sorted({20., 40., 60., 80., 98., 110., float(angle)}):
            if not self.tilt < degrees <= angle:
                continue
            if degrees <= 98:
                rot = rotation_y(-math.radians(degrees))
                offset = rot @ np.array([-.028, 0, .025])
                lip = np.r_[self.target[0] - .003, self.target[1], .155]
                q = self.pose(lip - offset, rot @ self.orientation, self.joints.copy())
                self.last_tip_joints = q.copy()
                self.move(q, .7)
            else:
                extension = self.last_tip_joints.copy()
                extension[3] += .22 * min(1., (degrees - 98.) / 12.)
                extension[1] -= .28 * max(0., (degrees - 110.) / 10.)
                extension[2] += .15 * max(0., (degrees - 110.) / 10.)
                self.move(extension, 1.25)
            self.tip_path.append(self.joints.copy())
            self.tilt = degrees
            if degrees >= 98:
                self.sim.wait(1.)
        self.sim.wait(.35)

    def execute(self, decision):
        action = decision["action"]
        allowed = {
            "parked": ("approach", "park"), "open": ("approach", "grasp", "park"),
            "grasped": ("lift", "release"), "lifted": ("align", "return"),
            "aligned": ("align", "tip", "return"), "tilted": ("tip", "upright"),
            "returned": ("release",), "released": ("park", "approach"),
        }
        if action == "finish":
            return "The actor submitted its terminal decision."
        if action not in allowed[self.phase]:
            raise ValueError(f"Robot command phase is {self.phase}. Available actions: "
                             + ", ".join((*allowed[self.phase], "finish")) + ".")
        if action == "approach":
            self.source = rim_xy(decision["u"], decision["v"])
            self.sim.set_gripper(.094, 1.2)
            self.down(self.source, .16)
            self.down(self.source, .055)
            self.phase = "open"
        elif action == "grasp":
            self.sim.set_gripper(.028, 1.5)
            self.sim.wait(.3)
            self.phase = "grasped"
        elif action == "lift":
            self.down(self.source, .19)
            self.phase = "lifted"
        elif action == "align":
            self.target = rim_xy(decision["u"], decision["v"])
            self.down(self.target + [-.055, 0.], .16)
            self.upright_joints = self.joints.copy()
            self.forward(self.joints)
            self.orientation = self.kin.data.site_xmat[self.kin.site].reshape(3, 3).copy()
            self.phase = "aligned"
        elif action == "tip":
            self.roll_to(decision["angle"])
            self.phase = "tilted"
        elif action == "upright":
            self.roll_upright()
            self.phase = "aligned"
        elif action == "return":
            self.down(self.source, .19)
            self.down(self.source, .055)
            self.phase = "returned"
        elif action == "release":
            self.sim.set_gripper(.094, 1.5)
            self.down(self.source, .16)
            self.phase = "released"
        elif action == "park":
            self.move(np.array(HOME_JOINTS), 1.5)
            self.sim.wait(1.)
            self.phase = "parked"
        return f"{action} movement completed. Robot command phase: {self.phase}."
