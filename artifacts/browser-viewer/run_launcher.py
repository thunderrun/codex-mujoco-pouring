"""Launch a selected camera episode in a user service independent of the browser."""
from datetime import datetime
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import threading
import time

from arm_config import ARM_LABELS, ARM_SKILLS, DEFAULT_ARM, DEFAULT_SKILL, checked_skill
from codex_actor import DEFAULT_REASONING_EFFORT, MODEL_SPEEDS, REASONING_EFFORTS, SPEED_LABELS, run_settings
from codex_feed import CURRENT, RUNS

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
UNIT = "robo-mj-codex-selected.service"
RUN_ID = re.compile(r"[0-9]{8}-[0-9]{6}-[0-9]{6}")
LAUNCH_LOCK = threading.Lock()
LABELS = {"gpt-6.2-astra": "GPT-6.2 Astra", "gpt-6.2-sol": "GPT-6.2 Sol"}


class RunBusy(Exception):
    pass


def running():
    return subprocess.run(["systemctl", "--user", "is-active", "--quiet", UNIT],
                          check=False, timeout=3).returncode == 0


def options():
    effort_choices = [{"id": effort, "label": "Extra high" if effort == "xhigh" else effort.capitalize()}
                      for effort in REASONING_EFFORTS]
    recordings = []
    for folder in sorted(RUNS.glob("*"), reverse=True):
        if not RUN_ID.fullmatch(folder.name) or not (folder / "replay.mp4").is_file():
            continue
        status_file = folder / "status.json"
        if not status_file.is_file():
            continue  # A published replay can have only a summary in run-history.json.
        st = json.loads(status_file.read_text())
        speed = st.get("speed_label") or SPEED_LABELS[st.get("speed", "standard")]
        date = datetime.strptime(folder.name, "%Y%m%d-%H%M%S-%f").strftime("%b %d, %H:%M")
        effort = st.get("reasoning_effort")
        if not effort and st.get("reasoning") == "Standard":
            effort = "medium"  # The original viewer called its fixed medium effort "Standard".
        effort_label = next((choice["label"] for choice in effort_choices if choice["id"] == effort), None)
        arm = st.get("arm", "yam")
        parts = [ARM_LABELS.get(arm, arm), LABELS.get(st["model"], st["model"]), speed]
        if effort_label:
            parts.append(f"{effort_label} reasoning")
        label = " · ".join([*parts, date])
        recordings.append({"id": folder.name, "label": label, "url": f"/runs/{folder.name}/replay.mp4"})
    return {
        "arms": [
            {"id": arm, "label": label, "default_skill": DEFAULT_SKILL[arm],
             "skills": [{"id": version, "label": title} for version, title in ARM_SKILLS[arm].items()]}
            for arm, label in ARM_LABELS.items()
        ],
        "default_arm": DEFAULT_ARM,
        "models": [{"id": model, "label": label, "reasoning_efforts": effort_choices,
                    "speeds": [{"id": speed, "label": SPEED_LABELS[speed]} for speed in MODEL_SPEEDS[model]]}
                   for model, label in LABELS.items()],
        "default_model": "gpt-6.2-astra", "default_speed": "standard",
        "default_reasoning_effort": DEFAULT_REASONING_EFFORT,
        "recordings": recordings, "busy": running(),
    }


def launch(payload):
    allowed = {"arm", "model", "speed", "layout", "reasoning_effort", "skill_version"}
    if not isinstance(payload, dict) or not {"model", "speed"} <= payload.keys() <= allowed:
        raise ValueError("Invalid run settings. Select a model and speed to start a run.")
    model, speed = payload["model"], payload["speed"]
    arm = payload.get("arm", DEFAULT_ARM)
    if not isinstance(arm, str) or arm not in ARM_LABELS:
        raise ValueError("Choose a supported robot arm.")
    skill_version = checked_skill(arm, payload.get("skill_version", DEFAULT_SKILL[arm]))
    effort = payload.get("reasoning_effort", DEFAULT_REASONING_EFFORT)
    run_settings(model, speed, effort)
    layout = payload.get("layout", "previous")
    if layout not in ("previous", "fresh"):
        raise ValueError("Invalid layout.")
    with LAUNCH_LOCK:
        if running():
            raise RunBusy("A run is already active. Its cameras and output are live.")
        run_id = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        args = ["systemd-run", "--user", "--quiet", "--collect", "--unit=" + UNIT,
                "--property=WorkingDirectory=" + str(REPO), "--setenv=MUJOCO_GL=egl",
                "--setenv=PATH=" + os.environ["PATH"]]
        if os.environ.get("ROBO_MJ_BENCH_DIR"):
            checkout = Path(os.environ["ROBO_MJ_BENCH_DIR"]).expanduser().resolve()
            args.append(f"--setenv=ROBO_MJ_BENCH_DIR={checkout}")
        args.extend("--setenv=" + name for name in ("HTTPS_PROXY","https_proxy") if os.environ.get(name))
        args.extend([sys.executable, "-B", str(HERE / "run_codex.py"), "--run-id", run_id,
                     "--arm", arm, "--skill-version", skill_version, "--model", model, "--speed", speed,
                     "--reasoning-effort", effort])
        prev = CURRENT.resolve()
        if layout == "previous" and RUN_ID.fullmatch(prev.name) and (prev / "private/episode.json").is_file():
            args.extend(["--seed-from", prev.name])
        started = subprocess.run(args, capture_output=True, timeout=8)
        if started.returncode:
            if running():
                raise RunBusy("A run is already active.")
            raise RuntimeError("The run service could not start.")
        # Wait for the data directory to become current so a returning page is
        # guaranteed to render the new selection on its very first refresh.
        response = {"run_id": run_id, "arm": arm, "skill_version": skill_version,
                    "model": model, "speed": speed, "reasoning_effort": effort}
        for _ in range(50):
            if CURRENT.resolve().name == run_id and (RUNS / run_id / "status.json").is_file():
                return {**response, "message": "Run started."}
            time.sleep(.1)
        if running():
            return {**response, "message": "The simulator is starting."}
        raise RuntimeError("The simulator exited before publishing its first camera view.")
