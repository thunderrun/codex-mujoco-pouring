"""SO-ARM101 press-button trial with a camera-selected physical press stroke."""
import io
import math
import xml.etree.ElementTree as ET

import mujoco
import numpy as np
from PIL import Image
from robo_mj_bench.simulation import ButtonSimulation

from so101_controls import PourControls
from so101_scene import HOME_JOINTS_RAD, SO101Robot, tabletop_scene

GUIDE = """Press the red button with the SO-ARM101 gripper. It flashes on a successful press
and the small indicator on the housing stays green afterwards. Use the overhead
image (640 pixels wide by 480 tall) to select the center of the red cap. Pixels
start at the upper left. press(u,v) closes the jaws, approaches that location,
presses down, and retracts. park moves clear of the scene. Review the cameras and
submit finish when ready. Set unused coordinates to zero."""
FIXED_TIP = np.array([-.009, 0., -.103])
CAP_TOP = .046


class ButtonArm(SO101Robot, ButtonSimulation):
    def _initialize_robot(self, seed, xml, extra_assets=None):
        # Reuse the benchmark's seeded spring-loaded cap, contact exclusions and evaluator.
        original = ET.fromstring(xml)
        root = tabletop_scene("press_button_so101")
        base = original.find("./worldbody/body[@name='button_base']")
        indicator = base.find("geom[@name='indicator']")
        indicator.set("size", ".007")
        root.find("worldbody").append(base)
        ET.SubElement(root, "contact").append(original.find("./contact/exclude[@body1='button_base']"))
        super()._initialize_robot(seed, ET.tostring(root, encoding="unicode"), extra_assets)
        self._finger_geoms = {
            i for i in range(self.model.ngeom)
            if self.model.geom(i).name.startswith(("moving_jaw_", "fixed_jaw_"))
            or (self.model.geom_group[i] == 4 and self.model.geom_bodyid[i] in
                (self.model.body("gripper").id, self.model.body("moving_jaw_so101_v1").id))
        }
        self.first_flash_time = None
        self.qualified_seconds = 0.
        self.on_frame = None

    def public_spec(self):
        return {"task_id": "press_button_so101", "instruction": GUIDE,
                "approximation": "rigid_body", "reference_image_png": None}

    def _step(self):
        super()._step()
        self.qualified_seconds = max(self.qualified_seconds, self._press_seconds)
        triggered = self._pressed and self.first_flash_time is None
        if self._pressed:
            if self.first_flash_time is None:
                self.first_flash_time = float(self.data.time)
            elapsed = self.data.time - self.first_flash_time
            self.model.geom_rgba[self._cap_id] = ((1., .85, .15, 1.) if elapsed < .35
                                                  else (.9, .05, .04, 1.))
        if self.on_frame is not None and (triggered or round(self.data.time / self.model.opt.timestep) % 175 == 0):
            self.on_frame()

    def finish(self):
        report = super().finish()
        report.update(task="press_button_so101", robot=self.robot_id,
                      flash_time_s=self.first_flash_time, qualified_hold_s=self.qualified_seconds)
        return report


class ButtonScenario:
    guide = GUIDE
    actions = ("press", "park", "finish")

    def __init__(self, seed):
        self.sim = ButtonArm(seed)
        self.controls = PourControls(self.sim)
        self.sim.wait(.4)

    def observe(self):
        return {name: Image.open(io.BytesIO(self.sim.observe(name))).convert("RGB")
                for name in ("overhead", "front", "left", "wrist")}

    def set_frame_callback(self, callback):
        self.sim.on_frame = callback

    def robot_state(self):
        return self.sim.robot_state()

    def execute(self, decision):
        action = decision["action"]
        if action == "park":
            self.controls.move(HOME_JOINTS_RAD, 1.4)
            return "Arm parked."
        if action == "finish":
            return "Submitted."
        if action != "press":
            raise ValueError("Use press, park, or finish.")
        u, v = decision["u"], decision["v"]
        if not 0 <= u < 640 or not 0 <= v < 480:
            raise ValueError("Choose a pixel within the 640 by 480 overhead image.")
        # Back-project the actor's chosen pixel to the nominal cap-top plane. Only
        # camera calibration, standard switch dimensions and robot geometry enter IK.
        scale = (1.2 - CAP_TOP) * 2 * math.tan(math.radians(29)) / 480
        xy = np.array([.3 + (u - 319.5) * scale, (239.5 - v) * scale])
        def target(height):
            return self.controls.solve(np.r_[xy, height], FIXED_TIP, 0., math.radians(-70))
        above = target(.115)
        contact = target(.037)
        self.sim.set_gripper(.01, .45)
        self.controls.move(above, 1.)
        self.controls.move(contact, 1.2)
        self.controls.move(above, .8)
        return "Press stroke and retraction completed at the selected image point."

    def grade(self):
        return self.sim.finish()

    def close(self):
        self.sim.close()


def create(seed):
    return ButtonScenario(seed)
