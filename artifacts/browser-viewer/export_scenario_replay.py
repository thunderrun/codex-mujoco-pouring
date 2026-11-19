"""Export a verified tabletop trial from its recorded cameras and public event times."""
import argparse
from bisect import bisect_right
from datetime import datetime
import json
from pathlib import Path

from export_codex_replay import FPS, camera_mosaic, encode_movie, encoded_card
from scenario_catalog import TASKS


def result_card(result):
    grade = result["grade"]
    passed = result["success"]
    task = result["task"]
    if task == "button":
        outcome = "The button flashed." if grade["pressed"] else "The button did not flash."
        detail = (f'Travel {grade["max_button_travel_m"] * 1000:.2f} mm. '
                  f'Peak force {grade["peak_button_force_n"]:.2f} N. '
                  f'Qualifying hold {grade["qualified_hold_s"] * 1000:.0f} ms.')
    elif task == "crocodile":
        outcome = "The entire toy settled inside the rectangle." if passed else "Placement criteria were unmet."
        detail = f'Closest edge clearance {grade["min_clearance_mm"]:.2f} mm across {grade["geometries_checked"]} shapes.'
    elif task in TASKS:
        outcome = grade.get("summary") or TASKS[task]
        detail = ""
    else:
        raise ValueError(f"Unknown tabletop task: {task}")
    score = f'{result["score"]:.1f}'.removesuffix(".0")
    details = " ".join(s for s in (outcome, detail) if s)
    return (f'Verified {"pass" if passed else "fail"} · {score}/100',
            f'{details} {result["decision_count"]} decisions. Wall time {result["duration_seconds"]:.2f} s.')


def export(folder, destination=None):
    folder = Path(folder).resolve()
    state = json.loads((folder / "status.json").read_text())
    result = json.loads((folder / "result.json").read_text())
    if state["phase"] != "finished" or result["verification"]["verified"] is not True:
        raise ValueError("A finished trial with a verified result is required.")
    captures = [json.loads(line) for line in (folder / "frames.jsonl").read_text().splitlines()]
    if [c["seq"] for c in captures] != list(range(1, state["seq"] + 1)) or not captures:
        raise ValueError("The camera timeline is incomplete.")
    camera_ticks = [round(c["wall_seconds"] * FPS) for c in captures]
    if camera_ticks != sorted(camera_ticks):
        raise ValueError("Camera timestamps are out of sequence.")
    start = datetime.fromisoformat(result["started_at"])
    end_tick = round(result["duration_seconds"] * FPS)
    if camera_ticks[-1] > end_tick:
        raise ValueError("The camera timeline exceeds the recorded duration.")
    events = [json.loads(line) for line in (folder / "public.jsonl").read_text().splitlines()]
    messages = {}
    for e in events:
        tick = round((datetime.fromisoformat(e["time"]) - start).total_seconds() * FPS)
        if 0 <= tick < end_tick:
            label = {"codex": "Codex", "command": "Command", "result": "Feedback",
                     "system": "Run", "error": "Error"}[e["kind"]]
            messages[tick] = (f'Decision {e["decision"]} · {label}' if e["decision"] else label, e["text"])

    boundaries = sorted({0, end_tick, *camera_ticks, *messages})
    family, name = result["model"].rsplit("-", 1)
    label = f'{family.upper()} {name.title()} · {result["reasoning_effort"].title()}'
    if result.get("revision"):
        label += f' · {result["revision"]}'
    title = f'{state["title"]} · {state["arm_label"]}'

    def frames():
        card = ("Run", state["title"])
        camera_index = None
        for begin, end in zip(boundaries, boundaries[1:]):
            index = max(0, bisect_right(camera_ticks, begin) - 1)
            if index != camera_index:
                mosaic = camera_mosaic(folder / "frames" / f'{captures[index]["seq"]:05}', title, label)
                camera_index = index
            card = messages.get(begin, card)
            yield encoded_card(mosaic, *card), end - begin
        final = camera_mosaic(folder / "frames" / f'{captures[-1]["seq"]:05}', title, label)
        yield encoded_card(final, *result_card(result)), 4 * FPS

    movie = Path(destination) if destination else folder / "replay.mp4"
    num_frames = encode_movie(movie, frames())
    return {"path": str(movie), "camera_sets": len(captures), "frames": num_frames, "seconds": num_frames / FPS}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_directory", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    print(json.dumps(export(args.run_directory, args.output)))
