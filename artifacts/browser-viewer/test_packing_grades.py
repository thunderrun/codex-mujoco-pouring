"""Check the final-state graders independently of model and motion accuracy."""

import unittest

import mujoco
import numpy as np

from packing_scenarios import create
from shape_fixture import FLOOR, PIECE_HALF_HEIGHT


def set_free_pose(scene, name, xyz):
    body = scene.model.body(name).id
    joint = scene.model.body_jntadr[body]
    position = scene.model.jnt_qposadr[joint]
    velocity = scene.model.jnt_dofadr[joint]
    scene.data.qpos[position : position + 7] = [*xyz, 1, 0, 0, 0]
    scene.data.qvel[velocity : velocity + 6] = 0
    mujoco.mj_forward(scene.model, scene.data)


class PackingGradesTests(unittest.TestCase):
    def test_equal_shape_with_wrong_color_is_a_mismatch(self):
        scene = create("shape_matching", 17)
        self.addCleanup(scene.close)
        targets = scene.fixture.targets
        level = FLOOR + PIECE_HALF_HEIGHT
        self.assertEqual(scene.grade()["score"], 0)
        for name in targets:
            set_free_pose(scene, name, [*targets[name], level])
        self.assertTrue(scene.grade()["success"])
        first, second = [name for name, kind in scene.fixture.pieces if kind == "circle"]
        set_free_pose(scene, first, [*targets[second], level])
        set_free_pose(scene, second, [*targets[first], level])
        result = scene.grade()
        self.assertEqual(result["score"], 75)
        self.assertFalse(result["seated"][first])
        self.assertFalse(result["seated"][second])

    def test_lid_requires_edge_alignment_and_four_contained_blocks(self):
        scene = create("tidying", 17)
        self.addCleanup(scene.close)
        fixture = scene.fixture
        for name, offset in zip(
            fixture.cubes, ((-0.02, -0.025), (-0.02, 0.025), (0.02, -0.025), (0.02, 0.025))
        ):
            set_free_pose(scene, name, [*(fixture.center + offset), 0.004 + fixture.half])
        self.assertEqual(scene.grade()["packed_count"], 4)
        self.assertFalse(scene.grade()["success"])
        lid_half = scene.model.geom("panel").size[2]
        set_free_pose(scene, "lid", [*fixture.center, fixture.rim + lid_half])
        self.assertTrue(scene.grade()["success"])
        set_free_pose(scene, "lid", [*(fixture.center + np.array([0.007, 0])), fixture.rim + lid_half])
        self.assertFalse(scene.grade()["lid_flush"])


if __name__ == "__main__":
    unittest.main()
