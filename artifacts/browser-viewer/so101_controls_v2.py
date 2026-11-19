"""Low-drop, camera-targeted SO-101 pouring skill. Units are metres and degrees."""
import math

import numpy as np

from so101_controls import (
    CUP_RADIUS, GRASP_HEIGHT, PINCH, PITCH, RIM_HEIGHT, UPRIGHT_ROLL, PourControls as OriginalControls,
)


class PourControls(OriginalControls):
    def align(self, xy):
        super().align(xy)
        # The cup starts upright. Calibrate its nominal long axis in hand coordinates.
        _, rotation = self.forward(self.joints)
        self.cup_axis = rotation.T @ np.array([0., 0., 1.])

    def _pour_pose(self, angle):
        roll = UPRIGHT_ROLL + math.radians(angle)
        pitch = PITCH * (1 - angle / 120)
        # Keep transit clearance with a near-upright cup. As the mouth tips,
        # lower the outlet from 90 to 53 mm above the receiving rim.
        blend = float(np.clip((angle - 22) / 65, 0., 1.))
        height = RIM_HEIGHT + .090 - blend * .037
        rim_center = PINCH + (RIM_HEIGHT - GRASP_HEIGHT) * self.cup_axis
        pose = self.joints.copy()
        pose[4] = roll
        # A change in arm pitch changes the hand orientation and hence the lowest
        # point on the circular rim. Re-evaluate the outlet with the solved pose.
        for _ in range(3):
            _, rotation = self.forward(pose)
            cup_up = rotation @ self.cup_axis
            flow = cup_up[:2].copy()
            flow /= max(np.linalg.norm(flow), 1e-8)
            gravity = -rotation[2, :]
            downhill = gravity - np.dot(gravity, self.cup_axis) * self.cup_axis
            downhill /= max(np.linalg.norm(downhill), 1e-8)
            outlet = rim_center + CUP_RADIUS * downhill
            offset = (1 - blend) * self.lip + blend * outlet
            # The falling beads retain horizontal velocity. Place the outlet a
            # cup radius upstream, in the robot's computed tilt direction.
            xy = self.target - blend * CUP_RADIUS * flow
            pose = self.solve(np.r_[xy, height], offset, roll, pitch)
        return pose

    def roll_to(self, angle):
        if not 1 <= angle <= 120:
            raise ValueError("Choose a wrist roll between 1 and 120 degrees.")
        if angle < self.tilt:
            self.upright()
        stages = math.ceil((angle - self.tilt) / 10)
        for stage in np.linspace(self.tilt, angle, stages + 1)[1:]:
            pose = self._pour_pose(stage)
            # Follow short, continuous arcs instead of stopping the cup between
            # IK waypoints. Keep both wrist tilt and individual joint speeds bounded.
            duration = max(.13, (stage - self.tilt) / 28, np.max(np.abs(pose - self.joints)) / 1.15)
            self.sim.move_joints(pose.tolist(), float(duration))
            self.joints = pose.copy()
            self.tip_path.append(pose.copy())
            self.tilt = float(stage)
        self.sim.wait(.65)
