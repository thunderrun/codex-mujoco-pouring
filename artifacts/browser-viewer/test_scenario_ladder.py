import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import run_scenario_ladder as ladder


class ScenarioLadderTests(unittest.TestCase):
    def test_resume_stops_at_the_first_verified_pass_in_each_revision(self):
        with TemporaryDirectory() as base, patch.object(ladder, "HERE", Path(base)):
            calls = []

            def finish_run(command, check):
                def argument(name):
                    return command[command.index(name) + 1]

                folder = Path(argument("--run-dir"))
                folder.mkdir()
                model = argument("--model")
                effort = argument("--effort")
                revision = argument("--revision")
                calls.append((model, effort))
                success = revision == "v2" and effort == "max"
                result = {"task": argument("--task"), "revision": revision, "model": model,
                          "reasoning_effort": effort, "success": success, "score": 100 if success else 50,
                          "verification": {"verified": True}}
                (folder / "result.json").write_text(json.dumps(result))
                (folder / "model_receipt.json").write_text(json.dumps({"seed": int(argument("--seed"))}))

            with patch.object(ladder.subprocess, "run", side_effect=finish_run):
                self.assertFalse(ladder.run_ladder("tidying", "suite", "v1", 101))
                self.assertEqual(calls, [("gpt-6.2-sol", "medium"), ("gpt-6.2-sol", "max"),
                                         ("gpt-6.2-astra", "medium"), ("gpt-6.2-astra", "max")])
                calls.clear()
                self.assertTrue(ladder.run_ladder("tidying", "suite", "v2", 101))
                self.assertEqual(calls, [("gpt-6.2-sol", "medium"), ("gpt-6.2-sol", "max")])
                calls.clear()
                self.assertTrue(ladder.run_ladder("tidying", "suite", "v2", 101))
                self.assertEqual(calls, [])
                with self.assertRaisesRegex(ValueError, "verification mismatch"):
                    ladder.run_ladder("tidying", "suite", "v2", 102)


if __name__ == "__main__":
    unittest.main()
