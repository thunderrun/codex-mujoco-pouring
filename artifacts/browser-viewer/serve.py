"""Loopback spectator viewer for one official episode and a restartable operator demo."""
import io
import json
import os
import re
import threading
import time
import traceback
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from PIL import Image
from robo_mj_bench.tasks.registry import create_simulation

from arm_config import ARM_LABELS
from gateway import GatewayFeed
import codex_feed
import run_history
import run_launcher
from run_instructions import instructions
from scenario_web import scenario_resource, scenario_movie

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
CAMERAS = ("front", "left", "overhead", "wrist")
PORT = int(os.environ.get("ROBO_VIEWER_PORT", "37656"))
FRAME_INTERVAL = 0.20
RECORDING = Path(os.environ.get("ROBO_BUTTON_RECORDING") or
                 ROOT / "artifacts/local-igpu-20261119/button/seed-101/button.mp4").expanduser()


class Demo:
    def __init__(self):
        self.lock = threading.Lock()
        self.frames = deque(maxlen=16)
        self.state = dict(phase="ready", mode="Scripted simulation", task="Pouring",
                          caption="Ready to start the arm", sim_time=0, seq=0,
                          run_id=0, result=None, can_replay=True)

    def snapshot(self):
        with self.lock:
            return self.state.copy()

    def frame(self, view, seq):
        with self.lock:
            if self.frames:
                images = next((images for n, images in reversed(self.frames) if str(n) == seq),
                              self.frames[-1][1])
                return images[view]
        return None

    def start(self, initial=False):
        with self.lock:
            if (initial and self.state["run_id"]) or not self.state["can_replay"]:
                return
            self.state.update(phase="loading", run_id=self.state["run_id"] + 1, caption="Loading the tabletop",
                              can_replay=False, sim_time=0, result=None)
        threading.Thread(target=self.run, daemon=True).start()

    def run(self):
        sim = None
        try:
            from pour_demo import run_demo
            sim = create_simulation("pouring", 17)
            start_sim = float(sim.data.time)
            start_wall = time.monotonic()
            last_sim = -1.0

            def capture():
                nonlocal last_sim
                instant = float(sim.data.time)
                images = {}
                for camera in CAMERAS:
                    with Image.open(io.BytesIO(sim.observe(camera))) as image:
                        target = io.BytesIO()
                        image.save(target, format="JPEG", quality=84)
                        images[camera] = target.getvalue()
                time.sleep(max(0, start_wall + instant - start_sim - time.monotonic()))
                with self.lock:
                    self.state.update(seq=self.state["seq"] + 1, sim_time=round(instant, 2), phase="running")
                    self.frames.append((self.state["seq"], images))
                last_sim = instant

            def note(caption):
                with self.lock:
                    self.state["caption"] = caption

            capture()
            step = sim._step
            def step_with_camera():
                step()
                if float(sim.data.time) - last_sim >= FRAME_INTERVAL - 1e-8:
                    capture()
            sim._step = step_with_camera
            run_demo(sim, note)
            note("Checking the settled cups")
            report = sim.finish()
            capture()
            metrics = report["metrics"]
            summary = (f'{metrics["beads_in_target"]} of {metrics["beads_total"]} beads in the orange cup'
                       f' · {metrics["beads_spilled"]} spilled')
            with self.lock:
                self.state.update(phase="finished", caption="Scripted run complete", result=summary, can_replay=True)
        except Exception as err:
            traceback.print_exc()
            with self.lock:
                self.state.update(phase="error", caption=f"Camera run stopped: {type(err).__name__}", can_replay=True)
        finally:
            if sim is not None:
                sim.close()


class Viewer(BaseHTTPRequestHandler):
    def log_message(self, template, *args):
        return

    def reply(self, body, kind, status=200, headers=()):
        self.send_response(status)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        for key, value in headers:
            self.send_header(key, value)
        self.end_headers()
        if self.command != "HEAD":
            try:
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                pass

    def do_HEAD(self):
        self.do_GET()

    def do_GET(self):
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)
        view = params.get("view", ["codex"])[0]
        if parsed.path == "/" and "view" not in params:
            self.reply((HERE / "overview.html").read_bytes(), "text/html; charset=utf-8")
        elif parsed.path in ("/", "/pouring"):
            if view == "gateway" and gateway is None:
                self.reply(b"", "text/plain", 302, [("Location", "/pouring")])
                return
            self.reply((HERE / "index.html").read_bytes(), "text/html; charset=utf-8")
        elif parsed.path.startswith("/scenarios/") and parsed.path.endswith("/replay.mp4"):
            self.serve_movie(scenario_movie(HERE, parsed.path))
        elif parsed.path in ("/scenarios", "/api/scenarios") or parsed.path.startswith("/scenarios/"):
            body, kind, status = scenario_resource(HERE, parsed.path)
            self.reply(body, kind, status)
        elif parsed.path == "/api/options":
            options = run_launcher.options()
            options["capabilities"] = {"gateway": gateway is not None, "button_recording": RECORDING.is_file()}
            self.reply(json.dumps(options).encode(), "application/json")
        elif parsed.path == "/api/history":
            self.reply(json.dumps(run_history.sync_history(), ensure_ascii=False).encode(),
                       "application/json; charset=utf-8")
        elif parsed.path == "/api/run-instructions":
            data, status = instructions(codex_feed.RUNS, parse_qs(parsed.query, keep_blank_values=True))
            self.reply(json.dumps(data, ensure_ascii=False).encode(), "application/json; charset=utf-8", status)
        elif parsed.path == "/api/status":
            if view == "demo":
                demo.start(initial=True)
                state = demo.snapshot()
            elif view == "gateway":
                if gateway is None:
                    self.reply(b'{"error":"No gateway episode is configured."}', "application/json", 404)
                    return
                state = gateway.snapshot()
            else:
                state = codex_feed.snapshot()
                run_id = state.get("run_id", "")
                if run_history.RUN_ID.fullmatch(run_id):
                    folder = codex_feed.RUNS / run_id
                    state["replay_ready"] = (folder / "replay.mp4").is_file()
                else:
                    state["replay_ready"] = False
            if view in ("demo", "gateway") or state.get("run_id"):
                arm = state.setdefault("arm", "yam")
                state["arm_label"] = ARM_LABELS.get(arm, arm)
            self.reply(json.dumps(state).encode(), "application/json")
        elif parsed.path == "/api/events":
            self.stream_events(params)
        elif parsed.path.startswith("/frame/"):
            match = re.fullmatch(r"/frame/(front|left|overhead|wrist)\.jpg", parsed.path)
            if not match:
                self.send_error(404)
                return
            camera = match.group(1)
            try:
                seq = params.get("s", [""])[0]
                if view == "gateway":
                    if gateway is None:
                        self.send_error(404, "No gateway episode is configured.")
                        return
                    frame = gateway.get_frame(camera)
                elif view == "demo":
                    frame = demo.frame(camera, seq)
                else:
                    frame = codex_feed.frame(camera, seq, params.get("run", [""])[0])
            except KeyError:
                frame = None
            self.reply(frame or b"", "image/jpeg", 200 if frame else 503)
        elif parsed.path in ("/button.mp4", "/codex-run.mp4") or parsed.path.startswith("/runs/"):
            if parsed.path.startswith("/runs/"):
                match = re.fullmatch(r"/runs/([0-9]{8}-[0-9]{6}-[0-9]{6})/replay\.mp4", parsed.path)
                if not match:
                    self.send_error(404)
                    return
                recording = codex_feed.RUNS / match.group(1) / "replay.mp4"
            else:
                recording = RECORDING if parsed.path == "/button.mp4" else codex_feed.CURRENT / "replay.mp4"
            self.serve_movie(recording)
        else:
            self.send_error(404)

    def serve_movie(self, recording):
        if recording is None or not recording.is_file():
            self.send_error(404)
            return
        length = recording.stat().st_size
        start, end, status = 0, length - 1, 200
        headers = [("Accept-Ranges", "bytes")]
        byte_range = self.headers.get("Range")
        if byte_range:
            match = re.fullmatch(r"bytes=(\d+)-(\d*)", byte_range)
            if not match:
                self.send_error(416)
                return
            start = int(match.group(1))
            if match.group(2):
                end = min(end, int(match.group(2)))
            if start > end:
                self.send_error(416)
                return
            headers.append(("Content-Range", f"bytes {start}-{end}/{length}"))
            status = 206
        with recording.open("rb") as stream:
            stream.seek(start)
            self.reply(stream.read(end-start+1), "video/mp4", status, headers)

    def stream_events(self, params):
        try:
            after = int(self.headers.get("Last-Event-ID") or params.get("after", ["0"])[0])
        except ValueError:
            self.send_error(400)
            return
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "close")
        self.end_headers()
        if self.command == "HEAD":
            return
        deadline = time.monotonic() + 55
        heartbeat = 0
        try:
            self.wfile.write(b"retry: 1000\n\n")
            self.wfile.flush()
            while time.monotonic() < deadline:
                state = codex_feed.snapshot()
                for event in state["events"]:
                    if event["id"] > after:
                        after = event["id"]
                        message = json.dumps(event, ensure_ascii=False)
                        self.wfile.write(f"id: {after}\ndata: {message}\n\n".encode())
                        self.wfile.flush()
                if time.monotonic() >= heartbeat:
                    self.wfile.write(b": connected\n\n")
                    self.wfile.flush()
                    heartbeat = time.monotonic() + 7
                time.sleep(.12)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def do_POST(self):
        if self.path not in {"/api/replay", "/api/runs"}:
            self.send_error(404)
            return
        allowed = {f"http://127.0.0.1:{PORT}", f"http://localhost:{PORT}"}
        if (f'http://{self.headers.get("Host")}' not in allowed or
                self.headers.get("Origin") not in allowed | {None}):
            self.send_error(403)
            return
        if self.path == "/api/replay":
            demo.start()
            self.reply(json.dumps(demo.snapshot()).encode(), "application/json")
            return
        try:
            if self.headers.get_content_type() != "application/json":
                self.send_error(415)
                return
            count = int(self.headers.get("Content-Length", 0))
            if not 1 <= count <= 2048:
                raise ValueError("Invalid request size.")
            payload = json.loads(self.rfile.read(count))
            response, code = run_launcher.launch(payload), 202
        except (ValueError, TypeError) as error:
            response, code = {"error": str(error)}, 400
        except run_launcher.RunBusy as error:
            response, code = {"error": str(error)}, 409
        except RuntimeError as error:
            response, code = {"error": str(error)}, 503
        self.reply(json.dumps(response).encode(), "application/json", code)


if __name__ == "__main__":
    run_history.sync_history(full=True)
    demo = Demo()
    directory = Path(os.environ.get("ROBO_GATEWAY_RUN_DIR") or
                     ROOT / "private-runs/pour-3.17-ready-20261119").expanduser()
    gateway = None
    if (directory / "events.jsonl").is_file() and (directory / "manifest.json").is_file():
        try:
            gateway = GatewayFeed(directory)
        except (OSError, ValueError, KeyError, TypeError):
            print("The optional gateway episode could not be loaded.", flush=True)
    ThreadingHTTPServer(("127.0.0.1", PORT), Viewer).serve_forever()
