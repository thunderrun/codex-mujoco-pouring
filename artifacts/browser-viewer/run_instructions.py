"""Serve archived arm skills and the recorded SO-101 v2 decision prompts."""
import hashlib
import json
import re

from arm_config import LEGACY_SKILL
from run_history import RUN_ID

# Recovered byte-for-byte from the decision inputs of the eight original runs.
ORIGINAL_GUIDE_HASH = {
    "yam-pour-v1": "f4dd757b53bf2cced8641e9edebf313cde9582530d6f7167034b6d77ef9c7dd8",
    "so101-pour-v1": "49fbe511ec791fe5e81455da38305a79fb3b3c356807338000e4a373003321e0",
}


def regular_file(path):
    # Only the literal public archive path may be read, including its parents.
    return path.is_file() and path.resolve() == path


def checked_text(data, digest):
    if hashlib.sha256(data).hexdigest() != digest:
        raise ValueError("The instructions do not match their recorded checksum.")
    return data.decode("utf-8")


def instructions(runs, params):
    if set(params) - {"run_id", "decision"} or any(len(v) != 1 for v in params.values()):
        return {"error": "Use one run_id and at most one decision number."}, 400
    rid = params.get("run_id", [""])[0]
    requested = params.get("decision", [None])[0]
    if not RUN_ID.fullmatch(rid):
        return {"error": "A valid run_id is required."}, 400
    if requested is not None and (not re.fullmatch(r"[0-9]{1,2}", requested) or int(requested) == 0):
        return {"error": "Use a positive decision number from the run."}, 400

    folder = runs.resolve() / rid
    try:
        manifest_path = folder / "model_receipt.json"
        if not regular_file(manifest_path):
            manifest_path = folder / "status.json"  # Earliest YAM run predates receipts.
        if not regular_file(manifest_path):
            return {"error": "Run instructions are unavailable for this run."}, 404
        manifest = json.loads(manifest_path.read_bytes())
        arm = manifest.get("arm", "yam")
        legacy = LEGACY_SKILL.get(arm)
        version = manifest.get("skill_version", legacy)
        if not legacy or not (version == legacy or (arm == "so101" and version == "so101-pour-v2")):
            return {"error": "Run instructions are unavailable for this arm or skill."}, 404
        result = {"run_id": rid, "skill_version": version, "skill_text": None,
                  "decision": None, "decisions": [], "prompt_text": None, "prompt_sha256": None}
        skill_path = folder / "pouring-skill.md"
        if version == legacy:
            if requested is not None:
                return {"error": "This v1 run publishes its arm skill only."}, 404
            digest = manifest.get("skill_sha256", ORIGINAL_GUIDE_HASH[version])
            if regular_file(skill_path):
                result["skill_text"] = checked_text(skill_path.read_bytes(), digest)
            else:
                # Older live archives may still have the original prompt and no extracted skill.
                first = folder / "decisions" / "01" / "input.txt"
                if not regular_file(first):
                    if "skill_version" in manifest and "skill_sha256" not in manifest:
                        return result, 200  # A new v1 run is still initializing.
                    return {"error": "The recorded v1 skill is unavailable."}, 404
                _, _, rest = first.read_bytes().partition(b"State one concise public camera observation per decision.\n")
                guide = rest.partition(b"\nDecision 1 of ")[0]
                result["skill_text"] = checked_text(guide, digest)
            return result, 200
        if "skill_sha256" not in manifest:  # The runner is still initializing the skill.
            return result, 200
        if not regular_file(skill_path):
            return {"error": "The recorded skill file is unavailable."}, 404
        result["skill_text"] = checked_text(skill_path.read_bytes(), manifest["skill_sha256"])

        steps = {}
        for step in (folder / "decisions").glob("[0-9][0-9]"):
            if step.name != "00" and regular_file(step / "input.txt") and regular_file(step / "run-settings.json"):
                steps[int(step.name)] = step
        result["decisions"] = sorted(steps)
        number = int(requested) if requested is not None else max(steps, default=None)
        if number is None:  # The initial prompt has not yet been written.
            return result, 200
        if number not in steps:
            return {"error": "No recorded prompt is available for this decision."}, 404
        step = steps[number]
        receipt = json.loads((step / "run-settings.json").read_bytes())
        digest = receipt.get("input_sha256")
        result.update(decision=number, prompt_text=checked_text((step / "input.txt").read_bytes(), digest),
                      prompt_sha256=digest)
        return result, 200
    except (ValueError, AttributeError, RuntimeError):
        return {"error": "The recorded instructions are incomplete or failed checksum verification."}, 409
    except OSError:
        return {"error": "The instruction files could not be read. Try again shortly."}, 503
