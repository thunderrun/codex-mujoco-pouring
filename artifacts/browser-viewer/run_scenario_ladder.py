"""Run one controller revision in the requested model order, stopping at its first verified pass."""
import argparse
import fcntl
import json
from pathlib import Path
import re
import subprocess
import sys

from run_scenario import HERE, TASK_LIMITS


PRESETS = (("sol", "medium"), ("sol", "max"), ("astra", "medium"), ("astra", "max"))


def run_ladder(task, batch, revision, seed):
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,60}", batch):
        raise ValueError("Use a short alphanumeric batch name.")
    archive = HERE / "scenario-runs" / task
    archive.mkdir(exist_ok=True, parents=True)
    with (archive / f".{batch}.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        for index, (model, effort) in enumerate(PRESETS, start=1):
            name = f"{batch}-{revision}-{index}-{model}-{effort}"
            folder = archive / name
            result_file = folder / "result.json"
            if not result_file.exists():
                if folder.exists():
                    raise RuntimeError(f"Inspect the incomplete trial before resuming: {folder}")
                print(f"Starting {task} {revision} {model} {effort}", flush=True)
                subprocess.run([sys.executable, "-B", str(HERE / "run_scenario.py"), "--task", task,
                                "--revision", revision, "--seed", str(seed), "--model", "gpt-6.2-" + model,
                                "--effort", effort, "--run-dir", str(folder)], check=True)
            result = json.loads(result_file.read_text())
            receipt = json.loads((folder / "model_receipt.json").read_text())
            if (not result["verification"]["verified"] or receipt["seed"] != seed
                    or (result["task"], result["revision"], result["model"], result["reasoning_effort"])
                    != (task, revision, "gpt-6.2-" + model, effort)):
                raise ValueError(f"Run identity or independent verification mismatch in {folder}.")
            print(f'{task} {model} {effort}: {result["score"]:.1f}/100 (pass={result["success"]})', flush=True)
            if result["success"]:
                return True
        return False


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task", required=True, choices=TASK_LIMITS)
    parser.add_argument("--batch", required=True)
    parser.add_argument("--revision", choices=("v1", "v2"), default="v1")
    parser.add_argument("--seed", type=int, default=101)
    args = parser.parse_args()
    passed = run_ladder(args.task, args.batch, args.revision, args.seed)
    print("First verified pass reached." if passed else "All four settings returned verified non-passes.")
