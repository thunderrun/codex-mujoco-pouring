"""Replay saved Codex decisions in fresh, unrendered MuJoCo physics."""
import argparse
import json
import os
import tempfile
from pathlib import Path

import mujoco
import numpy as np
from arm_config import LEGACY_SKILL
from pouring_arms import load_pouring_arm
from pouring_score import FINAL_CAPTURE_SCORER, TABLETOP_SCORER, UPSTREAM_SCORER


def load(path):
    return json.loads(path.read_text())


def replay_episode(directory, scoring_version):
    episode = load(directory / "private" / "episode.json")
    arm = episode.get("arm", "yam")  # The original archives predate arm selection.
    skill_version = episode.get("skill_version", LEGACY_SKILL[arm])
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
    sim, controller, _ = load_pouring_arm(arm, episode["seed"], scoring_version=scoring_version,
                                          skill_version=skill_version)
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
    if scoring_version != UPSTREAM_SCORER:
        replay["scoring_version"] = scoring_version
    evidence = {"decision_count": len(steps), "rejected_decisions": rejected,
                "controller_feedback_match": feedback_matches}
    return replay, evidence


def compare(actual, replay, evidence):
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
        "controller_feedback_match": evidence["controller_feedback_match"],
    }
    return {
        "verified": all(checks.values()), "method": "fresh unrendered MuJoCo replay of archived decisions",
        "decision_count": evidence["decision_count"], "rejected_decisions": evidence["rejected_decisions"],
        "max_qpos_difference": float(np.max(np.abs(original_qpos-replay_qpos))) if original_qpos.shape == replay_qpos.shape else None,
        "replay_score": replay["score"], **checks,
    }


def write_json(path, value):
    with tempfile.NamedTemporaryFile(mode="w", dir=path.parent, delete=False) as f:
        json.dump(value, f, indent=2, allow_nan=False)
        f.write("\n")
    os.replace(f.name, path)


def verify(directory, *, rescore=False):
    directory = directory.resolve()
    original = load(directory / "private" / "grading.json")
    version = original.get("scoring_version", UPSTREAM_SCORER)
    replay, evidence = replay_episode(directory, version)
    verification = compare(original, replay, evidence)
    if not rescore or version == FINAL_CAPTURE_SCORER:
        write_json(directory / "verification.json", verification)
        return verification
    if not verification["verified"]:
        raise ValueError("Original grade failed independent replay. No rescore was saved.")

    # Keep any previously published tabletop-v2 result reproducible too.
    prior = directory / "private" / "grading-v2.json"
    if prior.exists():
        older, older_evidence = replay_episode(directory, TABLETOP_SCORER)
        if not compare(load(prior), older, older_evidence)["verified"]:
            raise ValueError("The archived tabletop-v2 result failed independent replay.")

    revised, evidence = replay_episode(directory, FINAL_CAPTURE_SCORER)
    grade_path = directory / "private" / "grading-v3.json"
    verification_path = directory / "verification-v3.json"
    same_fields = all(revised[key] == value for key, value in original.items()
                      if key not in {"score", "success", "metrics", "stable_terminal_window", "scoring_version"})
    same_counts = all(revised["metrics"][key] == value
                      for key, value in original["metrics"].items() if key not in {"beads_stable", "beads_spilled"})
    same_actions = (evidence["controller_feedback_match"]
                    and evidence["rejected_decisions"] == verification["rejected_decisions"])
    if not (same_fields and same_counts and same_actions):
        raise ValueError("Rescored replay differs from the original physics, counts or command feedback.")
    if grade_path.exists() and load(grade_path) != revised:
        raise ValueError("Rescored replay differs from the existing revised grade.")
    verification = {
        "verified": True, "method": "fresh replays with original and revised pouring scorers",
        "scoring_version": FINAL_CAPTURE_SCORER, "original_scoring_version": version,
        "replay_score": revised["score"],
        "decision_count": evidence["decision_count"], "rejected_decisions": evidence["rejected_decisions"],
        "original_replay_verified": True, "end_state_match": True, "max_qpos_difference": 0.0,
        "unchanged_grading_inputs_match": True, "controller_feedback_match": True,
    }
    write_json(grade_path, revised)
    write_json(verification_path, verification)
    return verification


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_directory", type=Path)
    parser.add_argument("--rescore", action="store_true",
                        help="Verify the recorded grade and write a separate final-capture-v3 grade for legacy runs.")
    args = parser.parse_args()
    result = verify(args.run_directory, rescore=args.rescore)
    print(json.dumps(result))
    raise SystemExit(0 if result["verified"] else 1)
