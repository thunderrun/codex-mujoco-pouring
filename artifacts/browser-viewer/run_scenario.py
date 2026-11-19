"""Run or independently replay a camera-guided SO-ARM101 button or crocodile episode."""
import argparse
import hashlib
import io
import json
from datetime import datetime
from pathlib import Path
import time

from PIL import Image

from codex_actor import MODEL, MODEL_SPEEDS, REASONING_EFFORTS, decide, run_settings
from run_codex import overhead_ruler, save


HERE = Path(__file__).resolve().parent
TASKS = {"button": "Press the red button", "crocodile": "Place the crocodile toy in the rectangle"}
DECISION_LIMIT = 10


class CrocodileScenario:
    actions = ("pick", "place", "park", "finish")

    def __init__(self, seed):
        from so101_crocodile import create
        self.sim, self.controls, self.guide = create(seed)

    def observe(self):
        return {name: Image.open(io.BytesIO(self.sim.observe(name))).convert("RGB")
                for name in ("overhead", "front", "left", "wrist")}

    def robot_state(self):
        return self.sim.robot_state()

    def execute(self, decision):
        return self.controls.execute(decision)

    def grade(self):
        return self.sim.finish()

    def set_frame_callback(self, callback):
        self.sim.set_frame_callback(callback)

    def close(self):
        self.sim.close()


def create_task(task, seed):
    if task == "button":
        from button_scenario import create
        return create(seed)
    if task == "crocodile":
        return CrocodileScenario(seed)
    raise ValueError("Unknown task.")


def execute(scene, decision):
    try:
        return scene.execute(decision)
    except ValueError as error:
        return f"Command rejected: {error}"


def replay(folder):
    manifest = json.loads((folder / "model_receipt.json").read_text())
    first_grade = json.loads((folder / "grading.json").read_text())
    scene = create_task(manifest["task"], manifest["seed"])
    feedback_matches = True
    count = 0
    try:
        for path in sorted((folder / "decisions").glob("*/decision.json")):
            count += 1
            if int(path.parent.name) != count:
                raise ValueError("An archived decision is missing.")
            decision = json.loads(path.read_text())
            if decision["action"] == "finish":
                break
            feedback = execute(scene, decision)
            feedback_matches &= json.loads((path.parent / "feedback.json").read_text()) == feedback
        # A recorded JSON array and a runtime tuple represent the same measured vector.
        replay_grade = json.loads(json.dumps(scene.grade(), allow_nan=False))
    finally:
        scene.close()
    expected = json.loads((folder / "grading-input.json").read_text())["decision_count"]
    verified = count == expected and first_grade == replay_grade and feedback_matches
    result = {"verified": verified, "decision_count": count, "expected_decisions": expected,
              "grade_match": first_grade == replay_grade, "controller_feedback_match": feedback_matches,
              "replay_grade": replay_grade}
    save(folder / "verification.json", result)
    return result


def timestamp():
    return datetime.now().astimezone().isoformat(timespec="milliseconds")


def append_event(folder, state, kind, text):
    row = {"id": len(state["events"]) + 1, "time": timestamp(), "decision": state["decision"],
           "frame_seq": state["seq"], "sim_time": state.get("sim_time"), "kind": kind, "text": text}
    state["events"].append(row)
    with (folder / "public.jsonl").open("a", encoding="utf-8") as log:
        log.write(json.dumps(row, ensure_ascii=False) + "\n")


def publish_verified(folder, state, grade, verification, finished_at, duration):
    if not verification["verified"]:
        raise RuntimeError("The independent replay did not match the recorded episode.")
    task, success = state["task"], grade["success"]
    if type(success) is not bool:
        raise ValueError("The task grader did not return a boolean pass decision.")
    score = 100 if success else 0
    descriptions = {
        "button": ("No qualifying button flash.", "Button flashed."),
        "crocodile": ("Final placement did not meet the physical pass criteria.",
                      "The whole toy settled inside the rectangle."),
    }
    outcome = ("Pass" if success else "Fail") + " · " + descriptions[task][success]
    settings = run_settings(state["model"], state["speed"], state["reasoning_effort"])
    result = {"task": task, **settings, "arm": state["arm"], "run_id": state["run_id"],
              "success": success, "score": score, "grade": grade, "verification": verification,
              "decision_count": state["decision"], "started_at": state["started_at"],
              "finished_at": finished_at, "duration_seconds": duration, "verified_at": timestamp()}
    save(folder / "result.json", result)
    append_event(folder, state, "result", outcome)
    state.update(phase="finished", verified=True, success=success, score=score, result=outcome,
                 finished_at=finished_at, duration_seconds=duration, caption="Trial finished.")
    save(folder / "status.json", state)
    return result


def finalize(folder):
    """Recover a completed physics trial after a verification interruption, without model calls."""
    state = json.loads((folder / "status.json").read_text())
    grade = json.loads((folder / "grading.json").read_text())
    if state["phase"] == "finished":
        result = json.loads((folder / "result.json").read_text())
        if not result["verification"]["verified"] or result["grade"] != grade:
            raise ValueError("The published grade does not match the completed run.")
        return result
    if state["phase"] != "error" or not state["finished_at"]:
        raise ValueError("Only a stopped, fully graded trial can be finalized.")
    verification = replay(folder)
    return publish_verified(folder, state, grade, verification, state["finished_at"], state["duration_seconds"])


def run(task, model, effort, seed, folder, *, decision_limit=DECISION_LIMIT):
    settings = run_settings(model, "standard", effort)
    folder = Path(folder).resolve()
    folder.mkdir(parents=True, exist_ok=False)
    started = time.monotonic()
    receipt = {"task": task, "arm": "so101", "seed": seed, "run_id": folder.name,
               "started_at": timestamp(), "decision_limit": decision_limit, **settings}
    save(folder / "model_receipt.json", receipt)
    state = {**{k: v for k, v in receipt.items() if k != "seed"},
             "title": TASKS[task], "arm_label": "SO-ARM101", "phase": "starting", "seq": 0,
             "caption": "Preparing the SO-ARM101", "decision": 0, "cameras": [], "events": [],
             "score": None, "success": None, "verified": None, "result": "", "finished_at": None}
    path = folder / "status.json"

    def update(**changes):
        state.update(changes)
        state["duration_seconds"] = round(time.monotonic() - started, 3)
        save(path, state)

    def event(kind, text):
        append_event(folder, state, kind, text)
        update()

    scene = None
    latest = {}
    history = []
    event("system", f"Starting {TASKS[task]} with {model}, {effort} reasoning and four RGB cameras.")
    try:
        scene = create_task(task, seed)
        (folder / "skill.md").write_text(scene.guide)

        def capture():
            seq = state["seq"] + 1
            directory = folder / "frames" / f"{seq:05d}"
            directory.mkdir(parents=True)
            for name, image in scene.observe().items():
                target = directory / f"{name}.jpg"
                if name == "overhead":
                    image = overhead_ruler(image)
                image.save(target, "JPEG", quality=94, subsampling=0)
                latest[name] = target
            encoders = scene.robot_state()
            with (folder / "frames.jsonl").open("a") as index:
                index.write(json.dumps({"seq": seq, "wall_seconds": round(time.monotonic() - started, 3)}) + "\n")
            update(seq=seq, cameras=list(latest), sim_time=encoders.get("sim_time", encoders.get("sim_time_s")))

        capture()
        scene.set_frame_callback(capture)
        initial = latest["overhead"]
        for number in range(1, decision_limit + 1):
            update(phase="thinking", decision=number, caption=f"Codex is inspecting the cameras for decision {number}.")
            step_dir = folder / "decisions" / f"{number:02d}"
            step_dir.mkdir(parents=True)
            images = dict(latest)
            if number > 1:
                images["initial_overhead"] = initial
            save(step_dir / "observations.json",
                 {name: {"path": str(p.relative_to(folder)), "sha256": hashlib.sha256(p.read_bytes()).hexdigest()}
                  for name, p in images.items()})
            prompt = (scene.guide + "\nUse the public camera images to locate objects. The overhead image has a "
                      "20-pixel reference grid; x increases to the right, y increases down the image. "
                      "For commands with no angle, return 0 for angle. Give one action and one concise "
                      "observable reason. Inspect the scene after motion. When your task appears complete, "
                      "submit finish.\n"
                      f"Decision {number} of {decision_limit}. Public encoders: {json.dumps(scene.robot_state())}.\n"
                      f"Previous actions and feedback: {json.dumps(history, ensure_ascii=False)}.")
            def relay(kind, message):
                if kind in ("model", "status", "error"):
                    event({"model": "codex", "status": "system", "error": "error"}[kind], message)
            decision = decide(images, prompt, step_dir, relay, model=model, reasoning_effort=effort,
                              camera_names=list(images), actions=scene.actions)
            action = decision["action"]
            event("command", f"{action} ({decision['u']}, {decision['v']}, {decision['angle']}°)"
                  if action not in ("finish", "park") else action)
            if action == "finish":
                break
            update(phase="moving", caption=f"Executing {action}.")
            feedback = execute(scene, decision)
            save(step_dir / "feedback.json", feedback)
            event("result", feedback)
            history.append({**decision, "feedback": feedback})
            capture()
        else:
            event("system", "Decision limit reached. Grading the current physical state.")
        update(phase="verifying", caption="Grading and replaying the recorded commands.")
        grade = scene.grade()
        # Some scenes settle for grading. Preserve their last visible state in the archive.
        capture()
        scene.close()
        scene = None
        save(folder / "grading.json", grade)
        save(folder / "grading-input.json", {"decision_count": state["decision"]})
        verification = replay(folder)
        return publish_verified(folder, state, grade, verification, timestamp(), round(time.monotonic() - started, 3))
    except Exception as exc:
        message = f"{type(exc).__name__}: {exc}"
        event("error", message)
        update(phase="error", result=message, finished_at=timestamp(), caption="Trial interrupted.")
        raise
    finally:
        if scene is not None:
            scene.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--finalize", type=Path, help="Verify and publish a stopped, fully graded run without invoking Codex.")
    modes.add_argument("--verify", type=Path, help="Independently replay an existing run without invoking Codex.")
    parser.add_argument("--task", choices=TASKS)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--model", choices=MODEL_SPEEDS, default=MODEL)
    parser.add_argument("--effort", choices=REASONING_EFFORTS, default="medium")
    parser.add_argument("--run-dir", type=Path)
    args = parser.parse_args()
    if args.verify:
        result = replay(args.verify.resolve())
        print(json.dumps(result, ensure_ascii=False))
        raise SystemExit(0 if result["verified"] else 1)
    if args.finalize:
        result = finalize(args.finalize.resolve())
        print(json.dumps({key: result[key] for key in ("task", "run_id", "success", "score", "decision_count", "duration_seconds")}))
        raise SystemExit(0)
    if not args.task:
        parser.error("--task is required to start a new run")
    folder = args.run_dir or (HERE / "scenario-runs" / args.task /
                             (datetime.now().strftime("%Y%m%d-%H%M%S-%f") + f"-{args.model}-{args.effort}"))
    result = run(args.task, args.model, args.effort, args.seed, folder)
    print(json.dumps({k: result[k] for k in ("task", "run_id", "success", "score", "decision_count", "duration_seconds")}))
