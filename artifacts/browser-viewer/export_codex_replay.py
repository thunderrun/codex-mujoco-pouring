"""Export the public views and camera-driven decisions from a completed episode."""
import argparse
from bisect import bisect_right
from collections import defaultdict
from datetime import datetime
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

from PIL import Image, ImageDraw, ImageFont

from arm_config import ARM_LABELS
from public_grading import public_status

HERE = Path(__file__).resolve().parent
CAMERAS = ("front", "overhead", "left", "wrist")
WIDTH, VIEW_HEIGHT, HEADER, FOOTER, FPS = 1280, 960, 52, 174, 10
HEIGHT = HEADER + VIEW_HEIGHT + FOOTER
FONT_ROOT = Path("/usr/share/fonts/truetype/dejavu")
TITLE = ImageFont.truetype(str(FONT_ROOT / "DejaVuSans-Bold.ttf"), 25)
LABEL = ImageFont.truetype(str(FONT_ROOT / "DejaVuSans-Bold.ttf"), 17)
BODY = ImageFont.truetype(str(FONT_ROOT / "DejaVuSans.ttf"), 22)
SMALL = ImageFont.truetype(str(FONT_ROOT / "DejaVuSans.ttf"), 17)


def binary(name):
    bundled = HERE.parents[1] / ".venv/bin" / name
    return str(bundled) if bundled.is_file() else shutil.which(name) or name


def capture_track(root, max_sequence):
    captures = sorted(d for d in (root / "frames").iterdir() if d.is_dir() and d.name.isdigit() and int(d.name) <= max_sequence)
    if not captures:
        raise ValueError("The episode has no camera captures.")
    stamps = [max((d / f"{camera}.jpg").stat().st_mtime for camera in CAMERAS) for d in captures]
    if stamps != sorted(stamps):
        raise ValueError("The camera file timestamps are out of sequence.")
    return captures, stamps


def decision_cues(root, captures, stamps):
    """Model reads and its command share the last image it observed before moving."""
    events = [json.loads(line) for line in (root / "public.jsonl").read_text().splitlines()]
    seq_index = {int(d.name): i for i, d in enumerate(captures)}
    model_events = defaultdict(list)
    cues = defaultdict(list)
    for row in events:
        turn = row["decision"]
        if row["kind"] == "codex":
            model_events[turn].append(row)
        if row["kind"] != "command":
            continue
        receipt = json.loads((root / "decisions" / f"{turn:02d}" / "decision.json").read_text())
        observation = receipt["observation"]
        anchor = next((e for e in model_events[turn] if e["text"] == observation), row)
        if anchor.get("frame_seq") in seq_index:
            index = seq_index[anchor["frame_seq"]]
        else:
            # Public event timestamps have one-second precision. During deliberation
            # no physics is stepped. The model event normally follows the input by
            # several seconds, before the new command is executed.
            timestamp = datetime.fromisoformat(anchor["time"]).timestamp()
            index = max(0, bisect_right(stamps, timestamp) - 1)
        cues[index].append((f'Decision {turn}   ·   {row["text"]}', observation))
    return cues


def wrap(draw, text, font, width):
    lines = []
    words = text.split()
    line = ""
    for word in words:
        candidate = f"{line} {word}".strip()
        if line and draw.textlength(candidate, font=font) > width:
            lines.append(line)
            line = word
        else:
            line = candidate
    if line:
        lines.append(line)
    return lines


def camera_mosaic(folder, title, note="Motion replay · thinking pauses shortened"):
    canvas = Image.new("RGB", (WIDTH, HEIGHT), "#10221c")
    draw = ImageDraw.Draw(canvas)
    draw.text((17, 10), title, font=TITLE, fill="#f4f8f5")
    draw.text((WIDTH-16, 18), note, font=SMALL, fill="#c2d2c8", anchor="ra")
    for i, name in enumerate(CAMERAS):
        x, y = (i % 2) * 640, HEADER + (i // 2) * 480
        with Image.open(folder / f"{name}.jpg") as im:
            if im.size != (640, 480):
                raise ValueError(f"Unexpected camera dimensions at {folder.name}/{name}")
            canvas.paste(im, (x, y))
        camera = name.capitalize()
        label_width = int(draw.textlength(camera, font=LABEL)) + 18
        draw.rounded_rectangle((x+8, y+8, x+8+label_width, y+37), radius=5, fill="#18251f")
        draw.text((x+17, y+12), camera, font=LABEL, fill="#f4f8ee")
    return canvas


def encoded_card(mosaic, title, content):
    frame = mosaic.copy()
    y = HEADER + VIEW_HEIGHT
    draw = ImageDraw.Draw(frame)
    draw.text((17, y+10), title, font=TITLE, fill="#9fedc0")
    lines = wrap(draw, content, BODY, WIDTH-34)
    if len(lines) > 4:
        raise ValueError("Observation exceeds the replay strip; increase its height for this run.")
    for idx, line in enumerate(lines):
        draw.text((17, y+47+idx*29), line, font=BODY, fill="#f4f8ef")
    buf = io.BytesIO()
    frame.save(buf, "JPEG", quality=88, subsampling=1)
    return buf.getvalue()


def verify(movie, num_frames):
    probe = subprocess.run([binary("ffprobe"), "-v", "error", "-select_streams", "v:0",
                            "-show_entries", "stream=codec_name,width,height,nb_frames,r_frame_rate",
                            "-of", "json", str(movie)], check=True, capture_output=True, text=True)
    stream = json.loads(probe.stdout)["streams"][0]
    if (stream["codec_name"], stream["width"], stream["height"], int(stream["nb_frames"]), stream["r_frame_rate"]) != (
            "h264", WIDTH, HEIGHT, num_frames, f"{FPS}/1"):
        raise RuntimeError(f"Unexpected video metadata: {stream}")
    subprocess.run([binary("ffmpeg"), "-v", "error", "-xerror", "-i", str(movie),
                    "-f", "null", "-"], check=True, stdout=subprocess.DEVNULL)


def encode_movie(movie, frames):
    """Atomically publish a decoded and frame-count-verified H.264 movie."""
    num_frames = 0
    with tempfile.TemporaryDirectory(dir=movie.parent, prefix=".encode-") as temp:
        draft = Path(temp) / "movie.mp4"
        cmd = [binary("ffmpeg"), "-nostdin", "-hide_banner", "-loglevel", "error", "-f", "image2pipe",
               "-framerate", str(FPS), "-vcodec", "mjpeg", "-i", "pipe:0", "-an", "-c:v", "libx264",
               "-threads", "3", "-preset", "veryfast", "-crf", "22", "-pix_fmt", "yuv420p",
               "-movflags", "+faststart", str(draft)]
        with subprocess.Popen(cmd, stdin=subprocess.PIPE) as encoder:
            try:
                for data, count in frames:
                    for _ in range(count):
                        encoder.stdin.write(data)
                    num_frames += count
            finally:
                encoder.stdin.close()
            if encoder.wait():
                raise RuntimeError("FFmpeg could not encode the camera replay.")
        verify(draft, num_frames)
        os.replace(draft, movie)
    return num_frames


def export(root, *, partial=False, destination=None):
    root = Path(root).resolve()
    state = public_status(root)
    if not partial and state["phase"] not in ("exporting", "finished", "error"):
        raise ValueError("The episode is still recording.")
    movie = Path(destination).resolve() if destination else root / "replay.mp4"
    if partial and movie == root / "replay.mp4":
        raise ValueError("A preview of an active episode needs a separate output path.")
    model = state.get("model", "Codex")
    if model.startswith("gpt-"):
        family, name = model.rsplit("-", 1)
        model_label = f"{family.upper()} {name.capitalize()}"
    else:
        model_label = model
    arm = state.get("arm", "yam")
    title = f'{ARM_LABELS.get(arm, arm)} · {model_label} · {state.get("speed_label", "Standard")}'
    if effort := state.get("reasoning_effort"):
        title += f" · {effort.capitalize()} reasoning"
    captures, stamps = capture_track(root, state["seq"])
    cues = decision_cues(root, captures, stamps)

    def frames():
        card = ("Camera observation", "Codex receives the front, overhead, left and wrist views.")
        for idx, folder in enumerate(captures):
            mosaic = camera_mosaic(folder, title)
            for card in cues[idx]:
                # Leave a short pause at each decision so the actual model
                # observation can be read even if the camera never moved.
                yield encoded_card(mosaic, *card), round(FPS * min(4.0, max(1.6, len(card[1])/48)))
            # Native cameras capture at ~5 Hz; preserve motion and compress
            # stationary wall time spent waiting for model replies.
            next_gap = stamps[idx+1] - stamps[idx] if idx+1 < len(stamps) else .2
            count = max(1, round(FPS * min(.30, next_gap)))
            yield encoded_card(mosaic, *card), count
        result = state.get("result") or ("Episode still running." if partial else state["caption"])
        yield encoded_card(mosaic, "Run result" if not partial else "Preview", result), FPS*4

    num_frames = encode_movie(movie, frames())
    return {"path": str(movie), "camera_sets": len(captures), "decisions": sum(map(len, cues.values())),
            "frames": num_frames, "seconds": num_frames/FPS, "bytes": movie.stat().st_size}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_dir", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--partial", action="store_true", help="Make a preview at an explicit --output path.")
    args = parser.parse_args()
    print(json.dumps(export(args.run_dir, partial=args.partial, destination=args.output)))
