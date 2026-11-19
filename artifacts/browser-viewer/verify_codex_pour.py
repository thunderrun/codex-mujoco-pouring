"""Replay saved Codex decisions in fresh, unrendered MuJoCo physics."""
import argparse
import json
import os
import tempfile
from pathlib import Path

import mujoco
import numpy as np
from pouring_arms import load_pouring_arm


def load(path):
    return json.loads(path.read_text())


def verify(directory):
    directory = directory.resolve()
    actual = load(directory / "private" / "grading.json")
    episode = load(directory / "private" / "episode.json")
    arm = episode.get("arm", "yam")  # The original archives predate arm selection.
    steps = sorted((directory / "decisions").glob("*/decision.json"))
    numbers = [int(step.parent.name) for step in steps]
    if not numbers or numbers != list(range(1, len(steps) + 1)):
        raise ValueError("The decision archive is empty or has missing decision numbers.")
    events = [json.loads(line) for line in (directory / "public.jsonl").read_text().splitlines()]
    commands = [event["decision"] for event in events if event["kind"] == "command"]
    if commands != numbers:
        raise ValueError("Published commands and saved decision numbers differ.")
    feedback = {}
    for event in events:
        if event["kind"] == "result":
            feedback.setdefault(event["decision"], event["text"])
    rejected = []
    feedback_matches = True
    sim, controller, _ = load_pouring_arm(arm, episode["seed"])
    try:
        controls = controller(sim)
        for number, step in zip(numbers, steps):
            decision = load(step)
            if decision["action"] == "finish":
                if number != numbers[-1]:
                    raise ValueError("The decision archive continues after submission.")
                break
            try:
                message = controls.execute(decision)
            except (ValueError, RuntimeError) as exc:
                if sim._invalid_physics or sim._closed:
                    raise
                rejected.append(number)
                message = f"Robot controller: {exc}"
            feedback_matches &= feedback.get(number) == message
        replay = sim.finish()
    finally:
        sim.close()
    original_qpos = np.asarray(actual["final_qpos"], dtype=float)
    replay_qpos = np.asarray(replay["final_qpos"], dtype=float)
    same_qpos = np.array_equal(original_qpos, replay_qpos)
    checks = {
        "end_state_match": bool(same_qpos),
        "score_match": replay["score"] == actual["score"],
        "metrics_match": replay["metrics"] == actual["metrics"],
        "success_match": replay["success"] == actual["success"],
        "sim_time_match": replay["sim_time"] == actual["sim_time"],
        "scene_match": replay["scene_sha256"] == actual["scene_sha256"],
        "robot_match": replay["robot"] == actual["robot"],
        "engine_version_match": mujoco.__version__ == actual["mujoco_version"],
        "controller_feedback_match": feedback_matches,
    }
    verification = {
        "verified": all(checks.values()), "method": "fresh unrendered MuJoCo replay of archived decisions",
        "decision_count": len(steps), "rejected_decisions": rejected,
        "max_qpos_difference": float(np.max(np.abs(original_qpos-replay_qpos))) if original_qpos.shape == replay_qpos.shape else None,
        "replay_score": replay["score"], **checks,
    }
    with tempfile.NamedTemporaryFile(mode="w", dir=directory, delete=False) as f:
        json.dump(verification, f, indent=2, allow_nan=False)
        f.write("\n")
    os.replace(f.name, directory / "verification.json")
    return verification


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_directory", type=Path)
    result = verify(parser.parse_args().run_directory)
    print(json.dumps(result))
    raise SystemExit(0 if result["verified"] else 1)
