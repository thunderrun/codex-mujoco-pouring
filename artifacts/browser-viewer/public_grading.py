"""Public pouring results shared by the history, live feed and video exporter."""
import json
import re


REVISIONS = (("v3", "final-capture-v3"), ("v2", "tabletop-v2"))


def read_json(path):
    try:
        return json.loads(path.read_text())
    except FileNotFoundError:
        return {}


def format_outcome(report):
    metrics = report["metrics"]
    return (f'{metrics["beads_in_target"]} of {metrics["beads_total"]} beads in the orange cup · '
            f'{metrics["beads_in_source"]} in the blue cup · {metrics["beads_outside_cups"]} outside at finish · '
            f'{metrics["beads_spilled"]} counted as spilled during the run · score {report["score"]:.1f}/100')


def effective_grade(folder):
    """Use the newest verified revision, or the run's native grade."""
    original = read_json(folder / "private" / "grading.json")
    for suffix, version in REVISIONS:
        if original.get("scoring_version") == version:
            break
        verification = read_json(folder / f"verification-{suffix}.json")
        if verification.get("verified") is True and verification.get("scoring_version") == version:
            grade = read_json(folder / "private" / f"grading-{suffix}.json")
            if (grade.get("scoring_version") == version and grade.get("score") is not None
                    and grade["score"] == verification.get("replay_score")):
                return grade, verification
    return original, read_json(folder / "verification.json")


def has_newer_grade(folder, published_version):
    for suffix, version in REVISIONS:
        if version == published_version:
            break
        if (folder / f"verification-{suffix}.json").is_file():
            return True
    return False


def is_outcome(text):
    return isinstance(text, str) and re.match(r"^\d+ of \d+ beads in the orange cup\b", text) is not None


def project_score(state, grade):
    """Update the grading summary and grading events, leaving robot and model feedback intact."""
    if grade:
        outcome = format_outcome(grade)
        if state.get("phase") == "finished" or is_outcome(state.get("result")):
            state["result"] = outcome
        for row in state.get("events", ()):
            if row.get("kind") == "result" and is_outcome(row.get("text")):
                row["text"] = outcome
    return state


def public_status(folder):
    state = read_json(folder / "status.json")
    # During a normal episode the live stream polls several times a second. It
    # needs the grade only once the terminal result starts being published.
    events = state.get("events", ())
    if state.get("result") or state.get("phase") == "finished" or (events and is_outcome(events[-1].get("text"))):
        grade, _ = effective_grade(folder)
        project_score(state, grade)
    return state
