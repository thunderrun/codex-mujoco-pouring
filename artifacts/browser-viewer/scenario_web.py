"""Read-only access to the public camera views and results of tabletop trials."""
import json
from pathlib import Path
import re

from scenario_catalog import TASKS, public_catalog

TASK_PATH = "|".join(map(re.escape, TASKS))
RUN_ID = r"[A-Za-z0-9][A-Za-z0-9_-]{0,119}"
ASSET = (r"status\.json|result\.json|reference\.png|skill\.md|decisions/[0-9]{2}/input\.txt|"
         r"frames/[0-9]{5}/(?:overhead|front|left|wrist)\.jpg")
NOT_FOUND = (b"Not found", "text/plain", 404)


def scenario_movie(viewer, path):
    match = re.fullmatch(rf"/scenarios/({TASK_PATH})/({RUN_ID})/replay\.mp4", path)
    if not match:
        return None
    archive = viewer / "scenario-runs"
    task, run = match.groups()
    movie = archive / task / run / "replay.mp4"
    return movie if movie.resolve().is_relative_to(archive.resolve()) else None


def scenario_resource(viewer, path):
    archive = viewer / "scenario-runs"
    if path == "/scenarios":
        return (viewer / "scenarios.html").read_bytes(), "text/html; charset=utf-8", 200
    if path == "/scenarios/catalog.json":
        return json.dumps(public_catalog(), ensure_ascii=False).encode(), "application/json", 200
    if path == "/api/scenarios":
        trials = []
        for task in TASKS:
            for file in sorted((archive / task).glob("*/status.json")):
                if not re.fullmatch(RUN_ID, file.parent.name):
                    continue
                state = json.loads(file.read_text())
                summary = {k: state.get(k) for k in ("model", "reasoning_effort", "phase", "success",
                                                       "duration_seconds", "started_at", "finished_at",
                                                       "seq", "score", "arm_label", "verified", "revision")}
                run = file.parent.name
                base = f"/scenarios/{task}/{run}/"
                replay = base + "replay.mp4" if (file.parent / "replay.mp4").is_file() else None
                reference = base + "reference.png" if (file.parent / "reference.png").is_file() else None
                skill = base + "skill.md" if (file.parent / "skill.md").is_file() else None
                trials.append(dict(summary, task=task, run_id=run, replay_url=replay, reference_url=reference,
                                   skill_url=skill))
        trials.sort(key=lambda t: t["started_at"] or t["run_id"], reverse=True)
        return json.dumps(trials).encode(), "application/json", 200
    match = re.fullmatch(rf"/scenarios/({TASK_PATH})/({RUN_ID})/({ASSET})", path)
    if not match:
        return NOT_FOUND
    task, run, asset = match.groups()
    file = archive / task / run / Path(asset)
    if not file.resolve().is_relative_to(archive.resolve()) or not file.is_file():
        return NOT_FOUND
    kind = {".jpg": "image/jpeg", ".png": "image/png", ".json": "application/json",
            ".md": "text/plain; charset=utf-8", ".txt": "text/plain; charset=utf-8"}[file.suffix]
    return file.read_bytes(), kind, 200
