"""Physical regression fixtures for the versioned pouring scores."""
import unittest

import mujoco
from robo_mj_bench.task_simulation import TaskSimulation
from robo_mj_bench.tasks.pouring import PouringTask

from pouring_score import FINAL_CAPTURE_SCORER, FinalCapturePouringTask, PouringSimulation, TabletopPouringTask


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


class FinalCaptureScoringTests(unittest.TestCase):
    def setUp(self):
        self.sim = PouringSimulation(FinalCapturePouringTask(), 7)
        self.addCleanup(self.sim.close)
        self.task = self.sim.task
        self.target = self.sim.data.xpos[self.task._target].copy()

    def place(self, body, position):
        sim = self.sim
        joint = sim.model.body_jntadr[body]
        q = sim.model.jnt_qposadr[joint]
        v = sim.model.jnt_dofadr[joint]
        sim.data.qpos[q:q+3] = position
        sim.data.qvel[v:v+6] = 0.
        mujoco.mj_forward(sim.model, sim.data)
        self.task.after_step(sim)

    def transfer(self, count):
        # A single layer at 11 mm spacing leaves clearance between 10 mm beads.
        for i, bead in enumerate(self.task._beads[:count]):
            self.place(bead, self.target + [(i % 5 - 2)*.011, (i // 5 - 2)*.011, .0112])

    def test_recovered_table_contacts_do_not_reduce_complete_capture(self):
        for i, bead in enumerate(self.task._beads[:2]):
            self.place(bead, [.65, .1 + .02*i, .0048])
        self.assertEqual(len(self.task._spilled), 2)
        self.transfer(21)
        result = self.sim.finish()
        self.assertEqual(result["scoring_version"], FINAL_CAPTURE_SCORER)
        self.assertEqual(result["metrics"]["beads_in_target"], 21)
        self.assertEqual(result["metrics"]["beads_spilled"], 2)
        self.assertFalse(result["success"])
        self.assertEqual(result["score"], 100)
        self.assertEqual(self.sim.finish()["score"], 100)

    def test_twenty_of_twenty_one_is_fraction_even_when_strict_task_passes(self):
        self.transfer(20)
        result = self.sim.finish()
        self.assertEqual(result["metrics"]["beads_in_target"], 20)
        self.assertTrue(result["success"])
        self.assertAlmostEqual(result["score"], 2000/21)

    def test_impact_inside_target_is_not_a_table_spill(self):
        bead = self.task._beads[0]
        self.place(bead, self.target + [.02, 0, .0075])
        bead_geom = self.sim.model.body_geomadr[bead]
        base = self.sim.model.geom("pour_target_base").id
        self.assertTrue(any({c.geom1, c.geom2} == {bead_geom, base}
                            for c in self.sim.data.contact))
        self.assertNotIn(bead, self.task._spilled)
        self.transfer(21)
        self.assertEqual(self.sim.finish()["metrics"]["beads_spilled"], 0)

    def test_unsafe_simulation_has_zero_score(self):
        self.transfer(21)
        self.sim._invalid_physics = True
        result = self.sim.finish()
        self.assertEqual(result["metrics"]["beads_in_target"], 21)
        self.assertFalse(result["safe"])
        self.assertEqual(result["score"], 0)


if __name__ == "__main__":
    unittest.main()
