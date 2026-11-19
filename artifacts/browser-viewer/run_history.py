"""Persist a public, restartable index of the locally archived pouring episodes."""
import fcntl
import json
import os
import re
import subprocess
import tempfile
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

from arm_config import ARM_LABELS
from codex_feed import RUNS

RUN_ID = re.compile(r"[0-9]{8}-[0-9]{6}-[0-9]{6}")
FILENAME = "run-history.json"


def read_json(path):
    try:
        return json.loads(path.read_text())
    except FileNotFoundError:
        return {}


@contextmanager
def runner_lease(folder):
    # The kernel releases this lock even if the process dies before saving status.
    with (folder / ".runner.lock").open("a") as lease:
        fcntl.flock(lease, fcntl.LOCK_EX)
        yield


def is_active(folder):
    try:
        with (folder / ".runner.lock").open() as lease:
            try:
                fcntl.flock(lease, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                return True
            return False
    except FileNotFoundError:
        # Episodes already running when this index was introduced have no lease.
        if (folder.parent / "current").resolve() != folder.resolve():
            return False
        pid = subprocess.run(["systemctl", "--user", "show", "robo-mj-codex-selected.service",
                              "-p", "MainPID", "--value"], capture_output=True,
                             text=True, timeout=3).stdout.strip()
        if not pid.isdecimal() or pid == "0":
            return False
        try:
            return folder.name.encode() in Path("/proc", pid, "cmdline").read_bytes().split(b"\0")
        except FileNotFoundError:
            return False


def format_outcome(report):
    metrics = report["metrics"]
    return (f'{metrics["beads_in_target"]} of {metrics["beads_total"]} beads in the orange cup · '
            f'{metrics["beads_in_source"]} in the blue cup · {metrics["beads_outside_cups"]} outside at finish · '
            f'{metrics["beads_spilled"]} counted as spilled during the run · score {report["score"]:.1f}/100')


def verified_rescore(folder):
    report = read_json(folder / "private" / "grading-v2.json")
    if report:
        verification = read_json(folder / "verification-v2.json")
        if verification.get("verified"):
            return report, verification
    return None


def summarize(folder):
    manifest = read_json(folder / "model_receipt.json")
    status = read_json(folder / "status.json")
    if not status and not manifest:
        return None
    settings = {**manifest, **status}
    events = status.get("events", [])
    first_event = events[0].get("time") if events else None
    started = manifest.get("started_at") or first_event
    if not started:
        started = datetime.strptime(folder.name, "%Y%m%d-%H%M%S-%f").astimezone().isoformat()
    timing = read_json(folder / "timing.json")
    started = timing.get("started_at", started)
    phase = status.get("phase")
    if timing.get("completed_at") and phase == "exporting":
        phase = "finished"  # Export completed immediately before the final status write.
    result = status.get("result")
    finished = status.get("finished_at")
    if phase in ("finished", "error"):
        finished = finished or (events[-1].get("time") if events else None)
    elif is_active(folder):
        phase = "running"
    else:
        phase = "interrupted"
        result = result or "The runner stopped before recording a final outcome."
    graded = timing.get("graded_at") or status.get("graded_at")
    duration = None
    duration_scope = None
    if phase == "finished" and timing.get("completed_at"):
        finished = timing["completed_at"]
        duration = timing["duration_seconds"]
        duration_scope = "complete"
    elif phase in ("finished", "error") and finished:
        duration = round((datetime.fromisoformat(finished) - datetime.fromisoformat(started)).total_seconds(), 3)
        if phase == "finished":
            graded = graded or finished
            duration_scope = "to_grading"
        else:
            duration_scope = "to_error"
    elif phase == "running":
        duration_scope = "running"
    grading = read_json(folder / "private" / "grading.json")
    verification = read_json(folder / "verification.json")
    revision = verified_rescore(folder) if phase == "finished" else None
    revision_fields = {}
    if revision:
        revision_fields["original_score"] = grading["score"]
        grading, verification = revision
        result = format_outcome(grading)
    effort = settings.get("reasoning_effort")
    if not effort and status.get("reasoning") == "Standard":
        effort = "medium"  # Original Sol viewer used this display label for medium.
    scoring_version = grading.get("scoring_version")
    if grading and not scoring_version:
        scoring_version = f'upstream-v{grading.get("benchmark_version", "0.3.0")}'
    arm = settings.get("arm", "yam")  # All runs predating arm selection used the YAM.
    return {
        "run_id": folder.name, "started_at": started, "finished_at": finished,
        "completed_at": timing.get("completed_at"), "graded_at": graded,
        "duration_seconds": duration, "duration_scope": duration_scope, "duration_source": timing.get("source"),
        "arm": arm, "arm_label": ARM_LABELS.get(arm, arm),
        "phase": phase, "task": settings.get("task", "pouring").lower(),
        "model": settings.get("model"), "speed": settings.get("speed", "standard"),
        "reasoning_effort": effort, "layout_reference_run": settings.get("layout_reference_run"),
        "decision_count": verification.get("decision_count", status.get("decision", 0)),
        "result": result, "score": grading.get("score"), "success": grading.get("success"),
        "metrics": grading.get("metrics", {}), "sim_seconds": grading.get("sim_time"),
        "scoring_version": scoring_version,
        **revision_fields,
        "verified": verification.get("verified"),
        "replay_url": f"/runs/{folder.name}/replay.mp4" if (folder / "replay.mp4").is_file() else None,
    }


def sync_history(runs=RUNS, *, folder=None, full=False):
    """Merge snapshots under a cross-process lock; leave older archived entries intact."""
    runs.mkdir(exist_ok=True)
    path = runs / FILENAME
    with (runs / ".run-history.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            old = read_json(path)
        except json.JSONDecodeError:
            old = {}  # Rebuild from each episode's authoritative artifacts.
        records = {r["run_id"]: dict(r) for r in old.get("runs", [])}
        for record in records.values():
            arm = record.setdefault("arm", "yam")
            record["arm_label"] = ARM_LABELS.get(arm, arm)
        if full or old.get("version") != 3:
            folders = [p for p in runs.iterdir() if RUN_ID.fullmatch(p.name) and p.is_dir()]
        else:
            # Running episodes need crash reconciliation, plus completed episodes
            # whose verification/export may have landed since the last snapshot.
            folders = [runs / rid for rid, r in records.items()
                       if r["phase"] == "running" or
                       (r["phase"] == "finished" and (r["verified"] is None or not r["replay_url"]))]
            if folder is not None:
                folders.append(folder)
            else:
                current = (runs / "current").resolve()
                if RUN_ID.fullmatch(current.name) and current.name not in records:
                    folders.append(current)
        for item in dict.fromkeys(folders):
            entry = summarize(item)
            if entry:
                records[item.name] = entry
        history = {"version": 3, "runs": [records[key] for key in sorted(records, reverse=True)]}
        if old != history:
            with tempfile.NamedTemporaryFile("w", dir=runs, prefix=".run-history-", delete=False) as tmp:
                name = tmp.name
                try:
                    json.dump(history, tmp, ensure_ascii=False, indent=2, allow_nan=False)
                    tmp.write("\n")
                    tmp.flush()
                    os.fsync(tmp.fileno())
                    os.replace(name, path)
                    fd = os.open(runs, os.O_RDONLY | os.O_DIRECTORY)
                    try:
                        os.fsync(fd)
                    finally:
                        os.close(fd)
                finally:
                    Path(name).unlink(missing_ok=True)
        return history
