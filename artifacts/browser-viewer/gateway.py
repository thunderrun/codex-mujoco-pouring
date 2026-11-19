"""Read-only browser view of the photos already captured by the benchmark agent."""
import hashlib
import io
import json
import re
import threading
from pathlib import Path

from PIL import Image


class GatewayFeed:
    cameras = ("front", "left", "overhead", "wrist")
    motion = ("/v1/move_joints", "/v1/set_gripper", "/v1/wait", "/v1/move_bimanual")

    def __init__(self, run_dir):
        self.directory = Path(run_dir)
        self.lock = threading.Lock()
        self.task = json.loads((self.directory / "manifest.json").read_text())["task_family"]
        self.offset = 0
        self.request = {}
        self.images = {}
        self.sim_time = 0.0
        self.last_capture_time = 0.0
        self.sequence = 0

    def _refresh(self):
        with (self.directory / "events.jsonl").open("rb") as stream:
            stream.seek(self.offset)
            while line := stream.readline():
                if not line.endswith(b"\n"):
                    break
                event = json.loads(line)
                if event["event"] == "request":
                    self.request = event
                elif event["event"] == "frame" and self.request.get("path") == "/v1/observe":
                    camera = self.request["payload"]["camera_id"]
                    name = event["file"]
                    if camera in self.cameras and re.fullmatch(r"frame-[0-9]+\.png", name):
                        source = (self.directory / name).read_bytes()
                        if hashlib.sha256(source).hexdigest() != event["sha256"]:
                            raise ValueError("Camera capture checksum mismatch")
                        packed = io.BytesIO()
                        with Image.open(io.BytesIO(source)) as frame:
                            frame.convert("RGB").save(packed, format="JPEG", quality=88)
                        self.images[camera] = packed.getvalue()
                        self.sequence += 1
                        self.last_capture_time = self.sim_time
                elif event["event"] == "response":
                    if (event["status"] == 200 and "terminal" not in event
                            and event["path"] in self.motion and event["path"] == self.request.get("path")):
                        self.sim_time += self.request["payload"]["duration"]
                    self.request = {}
                self.offset = stream.tell()

    def snapshot(self):
        with self.lock:
            self._refresh()
            report = self.directory / "result.json"
            ended = report.is_file()
            final_message = None
            if ended:
                reason = json.loads(report.read_text()).get("termination")
                final_message = {
                    "submitted": "The agent submitted this episode.",
                    "operator_stopped": "The operator stopped this episode.",
                    "safety_stop": "The simulator stopped this episode.",
                }.get(reason, "The API episode has ended.")
            return {
                "phase": "finished" if ended else "ready",
                "caption": "Latest agent camera captures. Each view updates when the agent requests it.",
                "sim_time": round(self.last_capture_time, 6),
                "seq": self.sequence,
                "task": self.task,
                "run_id": "gateway",
                "mode": "Agent camera captures",
                "can_replay": False,
                "result": final_message,
            }

    def get_frame(self, camera):
        with self.lock:
            self._refresh()
            return self.images[camera]
