"""Read public RGB frames and return one action from the authenticated Codex CLI."""
import hashlib
import json
import math
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

MODEL = "gpt-6.2-sol"
DEFAULT_REASONING_EFFORT = "medium"
REASONING_EFFORTS = ("low", "medium", "high", "xhigh", "max", "ultra")
MODEL_SPEEDS = {
    "gpt-6.2-sol": ("standard", "fast", "ultrafast"),
    "gpt-6.2-astra": ("standard", "fast"),
}
SPEED_LABELS = {"standard": "Standard", "fast": "Fast", "ultrafast": "Ultrafast"}
SERVICE_TIERS = {"standard": "default", "fast": "priority", "ultrafast": "ultrafast"}


def run_settings(model, speed, reasoning_effort=DEFAULT_REASONING_EFFORT):
    if not isinstance(model, str) or model not in MODEL_SPEEDS:
        raise ValueError("Choose a supported pouring model.")
    if not isinstance(speed, str) or speed not in MODEL_SPEEDS[model]:
        raise ValueError(f"Supported speeds for {model}: {', '.join(MODEL_SPEEDS[model])}.")
    if reasoning_effort not in REASONING_EFFORTS:
        raise ValueError(f"Supported reasoning efforts: {', '.join(REASONING_EFFORTS)}.")
    return {"model": model, "speed": speed, "speed_label": SPEED_LABELS[speed],
            "service_tier": SERVICE_TIERS[speed], "reasoning_effort": reasoning_effort}


CAMERAS = ("front", "overhead", "left", "wrist")
ACTIONS = ("approach", "grasp", "lift", "align", "tip", "upright", "return", "release", "park", "finish")
SCHEMA = {
    "type": "object",
    "properties": {
        "observation": {"type": "string"},
        "action": {"type": "string", "enum": list(ACTIONS)},
        "u": {"type": "integer"}, "v": {"type": "integer"}, "angle": {"type": "number"},
    },
    "required": ["observation", "action", "u", "v", "angle"],
    "additionalProperties": False,
}
# The public camera images are already attached to the multimodal turn.
DISABLED = ("shell_tool", "unified_exec", "view_image", "image_generation",
            "multi_agent", "browser_use", "apps", "plugins", "hooks")


def public_text(value):
    """Redact sensitive-looking literals before forwarding text into a browser."""
    value = re.sub(r"(?i)\b(?:Bearer\s+\S+|sk-[\w-]{12,}|https?://[^\s/@]+:[^\s/@]+@[^\s]+)",
                   "[redacted]", str(value))
    return re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", value)


def public_error(value):
    msg = str(value).lower()
    if "capacity" in msg or "rate limit" in msg or "429" in msg:
        return "The model service is at capacity or rate-limited."
    if any(term in msg for term in ("login", "unauthorized", "401", "authentication")):
        return "The Codex CLI needs a valid login."
    if any(term in msg for term in ("stream", "reconnect", "proxy", "network", "connect")):
        return "The Codex connection was interrupted."
    return "The Codex request failed."


def parse_decision(text):
    try:
        d = json.loads(text)
        if (isinstance(d, dict) and set(d) == set(SCHEMA["required"])
                and isinstance(d["observation"], str) and d["observation"].strip()
                and d["action"] in ACTIONS and type(d["u"]) is int and type(d["v"]) is int
                and type(d["angle"]) in (int, float) and math.isfinite(d["angle"])):
            return {**d, "observation": public_text(d["observation"])}
    except (ValueError, TypeError):
        pass
    return None


def decide(images: dict[str, Path], prompt: str, work: Path, on_event, *, model=MODEL,
           speed="standard", reasoning_effort=DEFAULT_REASONING_EFFORT):
    selected = run_settings(model, speed, reasoning_effort)
    work = Path(work).resolve()
    work.mkdir(parents=True, exist_ok=True)
    camera_names = list(CAMERAS)
    camera_names.extend(name for name in ("initial_overhead", "previous_tip_overhead_sequence") if name in images)
    ordered = [Path(images[camera]).resolve(strict=True) for camera in camera_names]
    cli = shutil.which("codex") or str(Path.home() / ".local/bin/codex")
    order_text = ", ".join(name.replace("_", " ") for name in camera_names)
    actual_prompt = (prompt + f"\nThe attached RGB images are, in order: {order_text}. "
                     "If you give a progress update, use a brief public camera observation. "
                     "Return your one final camera observation and requested action as the specified JSON. "
                     "Use only the public information and images in this message. Do not use tools.")
    receipt_fields = {**selected, "input_sha256": hashlib.sha256(actual_prompt.encode("utf-8")).hexdigest(),
                      "observation_views": camera_names}
    (work / "run-settings.json").write_text(json.dumps(receipt_fields, indent=2) + "\n", encoding="utf-8")
    (work / "input.txt").write_text(actual_prompt, encoding="utf-8")
    with tempfile.TemporaryDirectory(prefix="pour-camera-codex-") as directory:
        isolated = Path(directory)
        schema_path = isolated / "action-schema.json"
        schema_path.write_text(json.dumps(SCHEMA), encoding="utf-8")
        receipt = isolated / "answer.json"
        command = ["timeout", "--kill-after=8s", "165s", cli, "exec", "-m", selected["model"],
                   "--ephemeral", "--ignore-user-config", "--ignore-rules", "--skip-git-repo-check",
                   "--sandbox", "read-only", "-c", 'approval_policy="never"', "-c",
                   'web_search="disabled"', "-c", f'model_reasoning_effort="{selected["reasoning_effort"]}"',
                   "-c", f'service_tier="{selected["service_tier"]}"',
                   "--enable", "skip_host_skill_discovery", "--output-schema", str(schema_path),
                   "--output-last-message", str(receipt), "--json", "--color", "never"]
        for feature in DISABLED:
            command.extend(["--disable", feature])
        for image in ordered:
            command.extend(["-i", str(image)])
        command.extend(["--", actual_prompt])
        with (work / "public-cli.jsonl").open("a", encoding="utf-8", buffering=1) as log:
            def emit(kind, text):
                text = public_text(text)
                if text:
                    log.write(json.dumps({"kind": kind, "text": text}, ensure_ascii=False) + "\n")
                    on_event(kind, text)

            for attempt in range(1, 4):
                last_model = None
                receipt.unlink(missing_ok=True)
                if attempt > 1:
                    emit("status", f"Retrying the same camera images (attempt {attempt}/3).")
                with tempfile.TemporaryFile(mode="w+t") as errors, subprocess.Popen(
                    command, cwd=isolated, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                    stderr=errors, text=True, errors="replace", bufsize=1,
                ) as proc:
                    for line in proc.stdout:
                        try:
                            event = json.loads(line)
                        except ValueError:
                            continue
                        event_type = event.get("type", "")
                        item = event.get("item", {})
                        item_type = item.get("type", "")
                        if item_type in ("command_execution", "mcp_tool_call", "web_search", "file_change", "image_view"):
                            proc.terminate()
                            raise RuntimeError("The camera-only actor requested an unexpected tool.")
                        if event_type == "turn.started":
                            emit("status", "Codex is inspecting the four camera images.")
                        elif event_type == "item.completed" and item_type == "agent_message":
                            value = item.get("text", "")
                            decision = parse_decision(value)
                            if decision:
                                message = decision["observation"]
                            else:
                                message = value
                            if message and message != last_model:
                                emit("model", message)
                                last_model = message
                        elif event_type in ("agent_message_delta", "response.output_text.delta"):
                            # These specific public types exclude reasoning and reasoning summaries.
                            fragment = event.get("delta")
                            if isinstance(fragment, str) and fragment:
                                emit("delta", fragment)
                        elif event_type in ("error", "turn.failed"):
                            emit("error", public_error(event.get("error", event.get("message", ""))))
                    code = proc.wait()
                    if code:
                        errors.seek(0)
                        emit("error", public_error(errors.read(24000)))
                if code == 0 and receipt.is_file():
                    decision = parse_decision(receipt.read_text(encoding="utf-8"))
                    if decision:
                        if decision["observation"] != last_model:
                            emit("model", decision["observation"])
                        (work / "decision.json").write_text(json.dumps(decision, ensure_ascii=False, indent=2))
                        return decision
                if code == 124:
                    emit("error", "Codex reached its time limit for this camera inspection.")
                if code == 0:
                    emit("error", "The CLI returned an incomplete action.")
    raise RuntimeError("Codex could not complete the camera decision after three attempts.")
