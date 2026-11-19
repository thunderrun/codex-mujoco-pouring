"""Terminal-state fixtures for spills at the edge of the finite pouring table."""
import unittest

import mujoco
from robo_mj_bench.task_simulation import TaskSimulation
from robo_mj_bench.tasks.pouring import PouringTask

from pouring_score import TabletopPouringTask


class TabletopScoringTests(unittest.TestCase):
    def setUp(self):
        self.sim = TaskSimulation(TabletopPouringTask(), 7)
        self.addCleanup(self.sim.close)
        self.task = self.sim.task
        self.target_bead, self.spill = self.task._beads[:2]
        self.target_point = self.sim.data.xpos[self.task._target].copy() + [0, 0, .0112]
        self.place(self.target_bead, self.target_point)
        self.place(self.spill, [.9, 0, -.20], [0, 0, -1])

    def place(self, body, xyz, velocity=(0, 0, 0)):
        joint = self.sim.model.body_jntadr[body]
        q = self.sim.model.jnt_qposadr[joint]
        v = self.sim.model.jnt_dofadr[joint]
        self.sim.data.qpos[q:q+3] = xyz
        self.sim.data.qvel[v:v+3] = velocity
        mujoco.mj_forward(self.sim.model, self.sim.data)
        self.task.after_step(self.sim)

    def test_falling_spill_costs_credit_for_one_bead(self):
        self.assertEqual(PouringTask.evaluate(self.task, self.sim)["score"], 0)
        result = self.task.evaluate(self.sim)
        self.assertAlmostEqual(result["score"], 100/21)
        self.assertEqual(result["metrics"]["beads_spilled"], 1)
        self.assertEqual(result["metrics"]["beads_lost_below_table"], 1)
        self.assertFalse(result["metrics"]["all_beads_stable"])
        self.assertTrue(result["metrics"]["beads_stable"])

    def test_moving_bead_still_in_play_invalidates_transfer(self):
        for position, motion in (([.65, .1, .005], [1, 0, 0]),
                                 ([.9, 0, .10], [0, 0, -1]),
                                 ([.9, 0, -.052], [0, 0, -1]),
                                 ([.9, 0, -.2], [0, 0, 1])):
            with self.subTest(position=position, motion=motion):
                self.place(self.spill, position, motion)
                result = self.task.evaluate(self.sim)
                self.assertEqual(result["metrics"]["beads_lost_below_table"], 0)
                self.assertEqual(result["score"], 0)

    def test_fallen_spill_cannot_mask_an_unsettled_target_bead(self):
        self.place(self.target_bead, self.target_point, [.2, 0, 0])
        result = self.task.evaluate(self.sim)
        self.assertEqual(result["metrics"]["beads_lost_below_table"], 1)
        self.assertFalse(result["metrics"]["beads_stable"])
        self.assertEqual(result["score"], 0)

    def test_fallen_spill_cannot_mask_a_floating_cup(self):
        self.place(self.task._target, self.sim.data.xpos[self.task._target].copy() + [0, 0, .1])
        self.place(self.target_bead, self.target_point + [0, 0, .1])
        result = self.task.evaluate(self.sim)
        self.assertTrue(result["metrics"]["beads_stable"])
        self.assertFalse(result["metrics"]["cups_stable"])
        self.assertEqual(result["score"], 0)


if __name__ == "__main__":
    unittest.main()
