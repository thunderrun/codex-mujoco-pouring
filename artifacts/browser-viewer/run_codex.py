"""Run one camera-guided Codex pouring episode and publish it to the local viewer."""
import argparse
import io
import json
import os
import re
import secrets
import time
import traceback
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageDraw

from arm_config import ARM_LABELS, DEFAULT_ARM
from codex_actor import DEFAULT_REASONING_EFFORT, MODEL, REASONING_EFFORTS, decide, run_settings
from codex_feed import CURRENT, RUNS, empty
from pouring_arms import load_pouring_arm
from run_history import runner_lease, sync_history

CAMERAS = ("front", "overhead", "left", "wrist")
DECISION_LIMIT = 20


def save(path, value):
    pending = path.with_suffix(".tmp")
    pending.write_text(json.dumps(value, ensure_ascii=False, allow_nan=False))
    pending.replace(path)


def overhead_ruler(image):
    overlay = Image.new("RGBA", image.size)
    draw = ImageDraw.Draw(overlay)
    for x in range(0, image.width, 20):
        draw.line((x, 0, x, image.height - 1), fill=(20, 30, 40, 30))
        if x % 40 == 0:
            draw.text((x + 2, 2), str(x), fill=(10, 15, 20, 255), stroke_width=1, stroke_fill="white")
    for y in range(0, image.height, 20):
        draw.line((0, y, image.width - 1, y), fill=(20, 30, 40, 30))
        if y % 40 == 0:
            draw.text((2, y + 2), str(y), fill=(10, 15, 20, 255), stroke_width=1, stroke_fill="white")
    return Image.alpha_composite(image.convert("RGBA"), overlay).convert("RGB")


def checked_id(value):
    if not re.fullmatch(r"[0-9]{8}-[0-9]{6}-[0-9]{6}", value):
        raise ValueError("Expected a run ID in YYYYMMDD-HHMMSS-ffffff format.")
    return value


def go(model=MODEL, speed="standard", seed_from=None, run_id=None, *,
       reasoning_effort=DEFAULT_REASONING_EFFORT, arm=DEFAULT_ARM):
    settings = run_settings(model, speed, reasoning_effort)
    if arm not in ARM_LABELS:
        raise ValueError(f"Unknown pouring arm: {arm!r}")
    settings.update(arm=arm, arm_label=ARM_LABELS[arm])
    run_id = checked_id(run_id or datetime.now().strftime("%Y%m%d-%H%M%S-%f"))
    RUNS.mkdir(exist_ok=True)
    if seed_from is None:
        seed = secrets.randbits(31)
    else:
        path = RUNS / checked_id(seed_from) / "private" / "episode.json"
        seed = json.loads(path.read_text())["seed"]
        if type(seed) is not int or seed < 0:
            raise ValueError("The reference episode has no valid layout seed.")
    root = RUNS / run_id
    root.mkdir(mode=0o700, exist_ok=False)
    try:
        with runner_lease(root):
            run_episode(root, settings, seed, seed_from)
    finally:
        sync_history(RUNS, folder=root)


def run_episode(root, settings, seed, seed_from):
    run_id = root.name
    model, speed = settings["model"], settings["speed"]
    for name in ("frames", "decisions", "private"):
        (root / name).mkdir()
    created_at = datetime.now().astimezone().isoformat(timespec="milliseconds")
    manifest = dict(settings, run_id=run_id, task="pouring", started_at=created_at,
                    layout_reference_run=seed_from, decision_limit=DECISION_LIMIT)
    save(root / "model_receipt.json", manifest)
    save(root / "private" / "episode.json", {"seed": seed, "arm": settings["arm"], "layout_reference_run": seed_from})
    status = empty()
    status.update(settings)
    status.update(run_id=run_id, reasoning=settings["reasoning_effort"].capitalize(), phase="loading",
                  layout_reference_run=seed_from, caption="Preparing the four RGB cameras")
    save(root / "status.json", status)
    staged = RUNS / f".current-{run_id}"
    staged.symlink_to(root.name)
    staged.replace(CURRENT)
    sync_history(RUNS, folder=root)
    def update(**updates):
        status.update(updates)
        save(root / "status.json", status)

    def event(kind, message):
        row = dict(id=len(status["events"]) + 1, time=datetime.now().astimezone().isoformat(timespec="milliseconds"),
                   decision=status["decision"], sim_time=status["sim_time"], frame_seq=status["seq"], kind=kind, text=message)
        status["events"].append(row)
        with (root / "public.jsonl").open("a") as log:
            log.write(json.dumps(row, ensure_ascii=False) + "\n")
        update()

    event("system", f'Starting {model} · {settings["speed_label"]} speed · {settings["reasoning_effort"]} reasoning. '
          f'Controlling {settings["arm_label"]} using four RGB cameras and joint encoders.')
    sim = None
    initial = None
    history = []
    latest = {}
    last_capture = -1.
    tick = time.monotonic()
    def capture(pace=False):
        nonlocal last_capture, tick, latest
        folder = root / "frames" / f'{status["seq"] + 1:05d}'
        folder.mkdir()
        images = {}
        for name in CAMERAS:
            with Image.open(io.BytesIO(sim.observe(name))) as raw:
                view = overhead_ruler(raw) if name == "overhead" else raw
                path = folder / f"{name}.jpg"
                view.save(path, "JPEG", quality=94, subsampling=0)
                images[name] = path
        if pace:
            time.sleep(max(0, tick + .20 - time.monotonic()))
        tick = time.monotonic()
        last_capture = float(sim.data.time)
        latest = images
        update(seq=status["seq"] + 1, sim_time=round(last_capture, 3))
        with (root / "frames.jsonl").open("a") as index:
            index.write(json.dumps({"seq":status["seq"], "sim_time":status["sim_time"], "wall_time":time.time()}) + "\n")
    try:
        sim, controller, guide = load_pouring_arm(settings["arm"], seed)
        capture()
        initial = latest["overhead"]
        controls = controller(sim)
        original_step = sim._step
        def camera_step():
            original_step()
            if float(sim.data.time) - last_capture >= .20 - 1e-8:
                capture(True)
        sim._step = camera_step
        for n in range(1, DECISION_LIMIT + 1):
            state = sim.robot_state()
            update(phase="thinking", decision=n, caption=f"Codex is inspecting the cameras for decision {n}")
            sync_history(RUNS, folder=root)
            event("system", f"Camera views and joint encoders sent for decision {n}.")
            pictures = dict(latest)
            if n > 1:
                pictures["initial_overhead"] = initial
            prompt = (f'Operate the simulated {settings["arm_label"]} robotic arm. Your goal is to transfer the yellow beads '
                      "from the blue cup to the orange cup, avoid spills, and leave both cups upright on the "
                      "table with the gripper released. Use the received images to locate the cups and assess "
                      "each motion. The overhead view has original pixel numbers and 20-pixel grid lines; "
                      "x increases right, y increases down. The first overhead image from the episode, when "
                      "provided as a separate reference, can help if the arm obscures a cup. Give one command. "
                      "State one concise public camera observation per decision.\n" + guide +
                      f"\nDecision {n} of {DECISION_LIMIT}. Robot command phase: {controls.phase}." +
                      "\nCurrent encoders: " + json.dumps(state) + "\nPrevious decisions: " + json.dumps(history))
            step_dir = root / "decisions" / f"{n:02d}"
            event_start = len(status["events"])
            fragments = []
            def relay(kind, message):
                if kind == "delta":
                    fragments.append(message)
                    # The CLI can stream a JSON final response. Publish plain observation
                    # text when complete, keeping the structured packet in the decision file.
                    if not "".join(fragments).lstrip().startswith(("{", "```")):
                        event("codex", message)
                else:
                    if kind == "model" and "".join(fragments) == message:
                        return
                    event({"model":"codex", "error":"error"}.get(kind, "system"), message)
            decision = decide(pictures, prompt, step_dir, relay, model=model, speed=speed,
                              reasoning_effort=settings["reasoning_effort"])
            if not any(row["kind"] == "codex" and row["text"] == decision["observation"]
                       for row in status["events"][event_start:]):
                event("codex", decision["observation"])
            act = decision["action"]
            command = act
            if act in {"approach", "align"}:
                command += f' at overhead pixel ({decision["u"]}, {decision["v"]})'
            if act == "tip":
                command += f' to {decision["angle"]:g}°'
            event("command", command)
            if act == "finish":
                break
            update(phase="moving", caption=f"Executing {command}")
            try:
                answer = controls.execute(decision)
            except (ValueError, RuntimeError) as exc:
                if sim._invalid_physics or sim._closed:
                    raise
                answer = f"Robot controller: {exc}"
            event("result", answer)
            history.append(dict(command=command, observation=decision["observation"], feedback=answer))
            capture()
        else:
            event("system", "The decision limit was reached. Grading the current pose.")
        update(phase="running", caption="Grading the settled cups")
        report = sim.finish()
        capture()
        metrics = report["metrics"]
        save(root / "private" / "grading.json", report)
        outcome = (f'{metrics["beads_in_target"]} of {metrics["beads_total"]} beads in the orange cup · '
                   f'{metrics["beads_in_source"]} in the blue cup · {metrics["beads_outside_cups"]} outside at finish · '
                   f'{metrics["beads_spilled"]} counted as spilled during the run · score {report["score"]:.1f}/100')
        event("result", outcome)
        update(phase="finished", result=outcome, caption="Codex run complete",
               finished_at=datetime.now().astimezone().isoformat(timespec="milliseconds"))
    except Exception as exc:
        traceback.print_exc()
        message=f"Run interrupted: {exc}"
        event("error", message)
        update(phase="error", caption="Codex run interrupted", result=message,
               finished_at=datetime.now().astimezone().isoformat(timespec="milliseconds"))
        raise
    finally:
        if sim is not None:
            sim.close()

    if status["phase"] == "finished":
        sync_history(RUNS, folder=root)
        from verify_codex_pour import verify
        from export_codex_replay import export
        if not verify(root)["verified"]:
            event("error", "Independent replay differed from the recorded run.")
        export(root)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default=MODEL)
    parser.add_argument("--arm", choices=ARM_LABELS, default=DEFAULT_ARM)
    parser.add_argument("--speed", default="standard")
    parser.add_argument("--reasoning-effort", choices=REASONING_EFFORTS, default=DEFAULT_REASONING_EFFORT)
    parser.add_argument("--seed-from", metavar="RUN_ID", help="Use the initial layout of this archived run.")
    parser.add_argument("--run-id", metavar="RUN_ID", help="Create a new run with this unique ID.")
    args = parser.parse_args()
    os.umask(0o077)
    go(args.model, args.speed, args.seed_from, args.run_id, reasoning_effort=args.reasoning_effort, arm=args.arm)
