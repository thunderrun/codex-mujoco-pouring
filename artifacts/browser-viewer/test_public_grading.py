"""Regression coverage for publishing a newly verified pouring score."""
import json
from pathlib import Path
import tempfile
import unittest

from public_grading import format_outcome, public_status
from run_history import sync_history


class PublicGradingTests(unittest.TestCase):
    def test_late_verification_updates_cached_history_and_terminal_event(self):
        with tempfile.TemporaryDirectory() as temp:
            runs = Path(temp)
            run = runs / "20261119-120000-000000"
            (run / "private").mkdir(parents=True)

            def save(name, data):
                (run / name).write_text(json.dumps(data))

            native = {"score": 99, "scoring_version": "tabletop-v2",
                      "metrics": {"beads_in_target": 21, "beads_total": 21, "beads_in_source": 0,
                                  "beads_outside_cups": 0, "beads_spilled": 0}}
            revision = {**native, "score": 100, "scoring_version": "final-capture-v3"}
            old_result = format_outcome(native)
            feedback = [{"kind": "codex", "text": "The orange cup is full."},
                        {"kind": "command", "text": "park"},
                        {"kind": "result", "text": "Park movement completed."}]
            save("status.json", {"phase": "finished", "result": old_result,
                                 "events": [*feedback, {"kind": "result", "text": old_result}]})
            save("private/grading.json", native)
            save("verification.json", {"verified": True})
            (run / "replay.mp4").touch()  # This episode already has a completed cache entry.
            self.assertEqual(sync_history(runs)["runs"][0]["score"], 99)

            save("private/grading-v3.json", revision)
            verification = {"scoring_version": "final-capture-v3", "replay_score": 100}
            for verified, grade in ((False, native), (True, revision)):
                with self.subTest(verified=verified):
                    save("verification-v3.json", {**verification, "verified": verified})
                    row = sync_history(runs)["runs"][0]
                    self.assertEqual(row["score"], grade["score"])
                    self.assertEqual(row["scoring_version"], grade["scoring_version"])
                    self.assertNotIn("original_score", row)
                    outcome = format_outcome(grade)
                    self.assertEqual(row["result"], outcome)
                    state = public_status(run)
                    self.assertEqual(state["result"], outcome)
                    self.assertEqual(state["events"], [*feedback, {"kind": "result", "text": outcome}])
