"""Operator's read-only feed for an independently running Codex episode."""
import re
from pathlib import Path

from public_grading import public_status

RUNS = Path(__file__).resolve().parent / "codex-runs"
CURRENT = RUNS / "current"
MODEL = "gpt-6.2-sol"


def empty():
    return dict(phase="ready", caption="Waiting for an operator to start Codex", result=None,
                mode="Codex", task="Pouring", run_id="", can_replay=False, seq=0,
                sim_time=0, model=MODEL, reasoning="Standard", decision=0, events=[])


def snapshot():
    return public_status(CURRENT.resolve()) or empty()


def frame(camera, seq, run_id=None):
    if camera not in {"front", "overhead", "left", "wrist"}:
        return None
    try:
        seq = int(seq) if seq else snapshot()["seq"]
        directory = CURRENT
        if run_id:
            if not re.fullmatch(r"[0-9]{8}-[0-9]{6}-[0-9]{6}", run_id):
                return None
            directory = RUNS / run_id
        return (directory / "frames" / f"{seq:05d}" / f"{camera}.jpg").read_bytes()
    except (ValueError, FileNotFoundError):
        return None
