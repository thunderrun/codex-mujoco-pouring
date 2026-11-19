"""SO-ARM101 pouring adapter for the upstream task, evaluator and spectator cameras."""
from functools import lru_cache
from pathlib import Path
import xml.etree.ElementTree as ET

import mujoco
import numpy as np

from robo_mj_bench.protocol import BadRequest, MAX_JOINT_SPEED, TIMESTEP
from robo_mj_bench.scene import yam_scene
from robo_mj_bench.task_simulation import TaskSimulation
from robo_mj_bench.tasks.pouring import PouringTask


MODEL_DIR = Path(__file__).resolve().parent / "models" / "robotstudio_so101"
MENAGERIE_COMMIT = "0059d4335f8156206f63a35662313385f7ad6d74"
ARM_JOINT_NAMES = ("shoulder_pan", "shoulder_lift", "elbow_flex", "wrist_flex", "wrist_roll")
HOME_JOINTS_RAD = np.deg2rad((0, -60, 60, 35, 0))
BASE_POSITION = (.14, 0., 0.)


@lru_cache(maxsize=1)
def _mesh_assets():
    return {mesh.name: mesh.read_bytes() for mesh in (MODEL_DIR / "assets").glob("*.stl")}


def _mounted_arm():
    root = ET.parse(MODEL_DIR / "so101.xml").getroot()
    root.find("option").set("timestep", str(TIMESTEP))
    world = root.find("worldbody")
    base = world.find("body[@name='base']")
    world.remove(base)
    # The upstream evaluator uses descendants of 'arm' for its release test.
    mount = ET.SubElement(world, "body", name="arm", pos=" ".join(map(str, BASE_POSITION)))
    mount.append(base)
    return root


def robot_only_model():
    """Return the calibrated robot geometry without any episode objects for IK."""
    return mujoco.MjModel.from_xml_string(ET.tostring(_mounted_arm(), encoding="unicode"),
                                          assets=_mesh_assets())


def _pouring_scene(task_id):
    root = _mounted_arm()
    root.set("model", "so101_" + task_id)
    world = root.find("worldbody")
    backdrop = yam_scene(task_id)
    for node in backdrop.find("worldbody"):
        if node.tag in ("camera", "geom") or (node.tag == "light" and not node.get("target")):
            world.append(node)
    for name in ("global", "quality"):
        root.find("visual").append(backdrop.find("visual").find(name))
    return root


class SO101PouringSimulation(TaskSimulation):
    robot_id = "robotstudio_so101"
    scene_factory = staticmethod(_pouring_scene)
    home_joints = HOME_JOINTS_RAD

    def _initialize_robot(self, seed, xml, extra_assets=None):
        self.seed, self.xml = seed, xml
        self.model = mujoco.MjModel.from_xml_string(xml, assets={**_mesh_assets(), **(extra_assets or {})})
        self.data = mujoco.MjData(self.model)
        joint_ids = [self.model.joint(name).id for name in (*ARM_JOINT_NAMES, "gripper")]
        self._qadr = self.model.jnt_qposadr[joint_ids]
        self._vadr = self.model.jnt_dofadr[joint_ids]
        initial = np.append(self.home_joints, .4)
        self.data.qpos[self._qadr] = initial
        self.data.ctrl[:] = initial
        mujoco.mj_forward(self.model, self.data)
        self._renderer = None
        self._closed = False
        self._invalid_physics = False

    def robot_state(self):
        return {
            "joint_positions": self.data.qpos[self._qadr[:5]].tolist(),
            "joint_velocities": self.data.qvel[self._vadr[:5]].tolist(),
            "gripper_angle_rad": float(self.data.qpos[self._qadr[5]]),
            "sim_time": round(float(self.data.time), 6),
        }

    def move_joints(self, targets, duration):
        joints = np.asarray(targets, dtype=float)
        limits = self.model.actuator_ctrlrange[:5]
        if joints.shape != (5,) or not np.isfinite(joints).all() or not np.isfinite(duration) or duration <= 0:
            raise BadRequest("Expected five joint angles and a positive duration.")
        if np.any(joints < limits[:, 0] - 1e-6) or np.any(joints > limits[:, 1] + 1e-6):
            raise BadRequest("Requested pose exceeds SO-101 joint travel.")
        if np.max(np.abs(joints - self.data.ctrl[:5])) > MAX_JOINT_SPEED * duration + 1e-9:
            raise BadRequest("Motion exceeds joint target speed limit.")
        target = self.data.ctrl.copy()
        target[:5] = joints
        self._advance(duration, target)

    def set_gripper(self, angle, duration):
        lo, hi = self.model.actuator_ctrlrange[5]
        if not lo <= angle <= hi or not np.isfinite(duration) or duration <= 0:
            raise BadRequest("Expected an SO-101 jaw angle within its range and a positive duration.")
        target = self.data.ctrl.copy()
        target[5] = angle
        self._advance(duration, target)

    def finish(self):
        report = super().finish()
        # TaskSimulation otherwise identifies the benchmark's original YAM source revision.
        report["robot_source_commit"] = MENAGERIE_COMMIT
        return report


def create_so101_pouring(seed, *, task=None):
    return SO101PouringSimulation(PouringTask() if task is None else task, seed)
