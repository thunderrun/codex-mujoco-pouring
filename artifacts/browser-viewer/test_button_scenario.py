"""A press must exceed the physical switch threshold with the gripper."""
import math
import unittest

from button_scenario import CAP_TOP, create


class ButtonTests(unittest.TestCase):
    def test_press_and_missed_press(self):
        # The test targets a known fixture privately. No target position is part
        # of the camera-guided actor's observations or commands.
        for offset, expected in ((0, True), (-18, False)):
            with self.subTest(offset=offset):
                trial = create(7)
                try:
                    x, y = trial.sim.button_xy
                    scale = (1.2 - CAP_TOP) * 2 * math.tan(math.radians(29)) / 480
                    u = round(319.5 + (x - .3) / scale)
                    v = round(239.5 - y / scale)
                    trial.execute({"action": "press", "u": u + offset, "v": v})
                    grade = trial.grade()
                finally:
                    trial.close()
                self.assertTrue(grade["safe"])
                self.assertIs(grade["success"], expected)
                self.assertIs(grade["flash_time_s"] is not None, expected)
                if expected:
                    self.assertGreaterEqual(grade["qualified_hold_s"], .08)
                    self.assertGreaterEqual(grade["max_button_travel_m"], .006)
                    self.assertGreaterEqual(grade["peak_button_force_n"], .5)
                else:
                    self.assertEqual(grade["score"], 0)
