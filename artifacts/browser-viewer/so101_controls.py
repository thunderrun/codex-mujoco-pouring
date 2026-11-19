"""Camera-guided grasp and wrist-roll primitives for the five-joint SO-101."""
import math

import mujoco
import numpy as np

from pour_controls import rim_xy
from so101_scene import ARM_JOINT_NAMES, HOME_JOINTS_RAD, robot_only_model


GUIDE = """You control a five-joint SO-101 with a hinged gripper. The overhead camera
is 640 by 480 pixels, u increasing to the right and v downward. Use approach(u,v)
to select the blue cup's top-rim center. The arm brings the open jaws around the
cup from the side. Grasp closes the fingers and lift raises them for inspection.
Use align(u,v) to select the orange cup's top-rim center; you may refine it while
upright. Tip(angle) rolls the wrist towards the receiver. The angle is absolute,
from 1 to 120 degrees, and can be increased in stages while observing the beads.
Upright reverses the wrist motion; return lowers the gripper at the pickup site;
release opens it; park moves the arm clear. Finish submits the scene for grading.
After a missed grasp you may return, release and approach a new point. Use whole
pixels and put zero in unused fields. Each acknowledgement confirms only that
the arm executed the command. Judge the result from cameras and encoders."""


# A side grasp puts the fixed and moving fingers on opposite sides of the cup.
# Coordinates below are nominal gripper-frame dimensions, not episode poses.
PINCH = np.array([.022, 0., -.081])
GRASP_HEIGHT = .054
CUP_RADIUS = .029
RIM_HEIGHT = .080
PITCH = math.radians(-35)
UPRIGHT_ROLL = math.radians(-87.2)


class PourControls:
    def __init__(self, sim):
        self.sim = sim
        self.model = robot_only_model()
        self.data = mujoco.MjData(self.model)
        ids = [self.model.joint(n).id for n in ARM_JOINT_NAMES]
        self.qadr = self.model.jnt_qposadr[ids]
        self.dof = self.model.jnt_dofadr[ids[:4]]
        self.limits = self.model.actuator_ctrlrange[:5]
        self.hand = self.model.body("gripper").id
        self.joints = HOME_JOINTS_RAD.copy()
        self.phase = "parked"
        self.source = self.target = None
        self.tilt = 0.
        self.tip_path = []
        self.lip = None

    def forward(self, q):
        self.data.qpos[self.qadr] = q
        mujoco.mj_kinematics(self.model, self.data)
        return self.data.xpos[self.hand], self.data.xmat[self.hand].reshape(3, 3)

    def solve(self, position, offset, roll, pitch):
        # Four joints set XYZ and approach pitch; wrist roll is specified directly.
        jp = np.zeros((3, self.model.nv))
        jr = np.zeros_like(jp)
        for start in (self.joints, HOME_JOINTS_RAD, [0., .4, 1.2, -.7, 0.]):
            q = np.array(start, dtype=float)
            q[4] = roll
            for _ in range(100):
                origin, rotation = self.forward(q)
                point = origin + rotation @ offset
                forward = -rotation[:, 2]
                linear = position - point
                pitch_error = math.sin(pitch) - forward[2]
                if np.linalg.norm(linear) < .0005 and abs(pitch_error) < .004:
                    return q
                mujoco.mj_comPos(self.model, self.data)
                mujoco.mj_jac(self.model, self.data, jp, jr, point, self.hand)
                vertical = forward[1] * jr[0, self.dof] - forward[0] * jr[1, self.dof]
                jac = np.vstack([jp[:, self.dof], .085 * vertical])
                error = np.r_[linear, .085 * pitch_error]
                delta = jac.T @ np.linalg.solve(jac @ jac.T + np.eye(4) * 1e-5, error)
                q[:4] = np.clip(q[:4] + delta * min(1, .23 / max(np.linalg.norm(delta), 1e-12)),
                                self.limits[:4, 0], self.limits[:4, 1])
        raise ValueError("The selected camera point is outside this SO-101 grasp workspace.")

    def move(self, q, minimum=1.0):
        duration = max(minimum, float(np.max(np.abs(q - self.joints))) / 1.15)
        self.sim.move_joints(q.tolist(), duration)
        self.joints = q.copy()
        self.sim.wait(.16)

    def position(self, xy, z):
        q = self.solve(np.r_[xy, z], PINCH, UPRIGHT_ROLL, PITCH)
        self.move(q)

    def align(self, xy):
        # Keep the near pouring lip over the chosen receiver as the wrist rolls.
        # At pickup the blue cup is upright in the world; map its geometric
        # center-to-lip vector into the hand's frame before changing orientation.
        _, rotation = self.forward(self.joints)
        vertical_local = rotation.T @ np.array([0., 0., 1.])
        lip = PINCH + np.array([-CUP_RADIUS, 0., 0.]) + (RIM_HEIGHT - GRASP_HEIGHT) * vertical_local
        self.move(self.solve(np.r_[xy, .170], lip, UPRIGHT_ROLL, PITCH))
        self.target = xy
        self.lip = lip
        self.tip_path = [self.joints.copy()]

    def upright(self):
        for q in reversed(self.tip_path[:-1]):
            self.move(q, .45)
        self.tip_path = self.tip_path[:1]
        self.tilt = 0.

    def roll_to(self, angle):
        if not 1 <= angle <= 120:
            raise ValueError("Choose a wrist roll between 1 and 120 degrees.")
        if angle < self.tilt:
            self.upright()
        stages = np.linspace(self.tilt, angle, math.ceil((angle - self.tilt) / 20) + 1)[1:]
        for stage in stages:
            roll = UPRIGHT_ROLL + math.radians(stage)
            pitch = PITCH * (1 - stage / 120)
            q = self.solve(np.r_[self.target, .170], self.lip, roll, pitch)
            self.move(q, .60)
            self.tip_path.append(q.copy())
            self.tilt = float(stage)
        self.sim.wait(.65)

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
            xy = rim_xy(decision["u"], decision["v"])
            self.sim.set_gripper(1.35, .8)
            self.position(xy, .16)
            self.position(xy, GRASP_HEIGHT)
            self.source = xy
            self.phase = "open"
        elif action == "grasp":
            self.sim.set_gripper(.28, 1.)
            self.phase = "grasped"
        elif action == "lift":
            self.position(self.source, .165)
            self.phase = "lifted"
        elif action == "align":
            self.align(rim_xy(decision["u"], decision["v"]))
            self.phase = "aligned"
        elif action == "tip":
            self.roll_to(decision["angle"])
            self.phase = "tilted"
        elif action == "upright":
            self.upright()
            self.phase = "aligned"
        elif action == "return":
            self.position(self.source, .165)
            self.position(self.source, GRASP_HEIGHT)
            self.phase = "returned"
        elif action == "release":
            self.sim.set_gripper(1.35, .8)
            self.position(self.source, .16)
            self.phase = "released"
        elif action == "park":
            self.move(HOME_JOINTS_RAD, 1.5)
            self.phase = "parked"
        return f"{action} movement completed. Robot command phase: {self.phase}."
