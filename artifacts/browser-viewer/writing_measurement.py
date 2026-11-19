"""Instrumented SO-ARM101 tasks for contact handwriting and visual box metrology."""

import hashlib
import math
import subprocess
import xml.etree.ElementTree as ET
from difflib import SequenceMatcher
from io import BytesIO
from itertools import pairwise

import mujoco
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from robo_mj_bench.task_simulation import TaskSimulation
from robo_mj_bench.tasks.base import Task
from robo_mj_bench.tasks.measurement import MeasurementTask

from so101_controls import PourControls
from so101_scene import SO101Robot, tabletop_scene

NIB = np.array([0.018, 0.0, -0.155])
PITCH = math.radians(-55)
WIDTH, HEIGHT = 640, 480


def numbers(vector):
    return " ".join(f"{n:.9g}" for n in vector)


def ortho(world, name, pos, axes, span):
    camera = world.find(f"camera[@name='{name}']")
    camera.attrib.update(pos=numbers(pos), xyaxes=axes, fovy=str(span), projection="orthographic")


def overhead_point(sim, camera, u, v, plane_z):
    """Unproject a selected image point using only the fixed overhead camera calibration."""
    i = sim.model.camera(camera).id
    rotation = sim.data.cam_xmat[i].reshape(3, 3)
    span = sim.model.cam_fovy[i]
    origin = (
        sim.data.cam_xpos[i]
        + (rotation[:, 0] * (u + 0.5 - WIDTH / 2) - rotation[:, 1] * (v + 0.5 - HEIGHT / 2))
        * span
        / HEIGHT
    )
    return origin[:2] + (plane_z - origin[2]) / rotation[2, 2] * rotation[:2, 2]


class ContactWriting(Task):
    task_id = "so101_handwriting"
    requires_stability = False
    paper_height = 0.003
    # A 0.25 mm raster, covering the paper, the box, and the surrounding tabletop.
    width, height = 960, 480
    mpp = 0.00025
    nib_radius = 0.001
    box_width, box_height = 0.170, 0.066

    def build(self, world, root, rng):
        self.xy = np.array([0.415 + rng.uniform(-0.002, 0.002), rng.uniform(-0.003, 0.003)])
        x, y = self.xy
        ortho(world, "overhead", [0.415, 0.0, 0.7], "0 1 0 -1 0 0", 0.158)
        world.find("camera[@name='front']").attrib.update(
            pos=".82 -.40 .43", xyaxes=".69 .72 0 -.39 .38 .84", fovy="37"
        )
        world.find("camera[@name='left']").attrib.update(
            pos=".58 .45 .35", xyaxes="-.92 .39 0 -.23 -.55 .8", fovy="40"
        )
        ET.SubElement(
            world,
            "geom",
            name="writing_paper",
            type="box",
            pos=numbers([x, y, self.paper_height / 2]),
            size=".050 .100 .0015",
            rgba=".97 .97 .96 1",
        )
        for axis, half in enumerate((self.box_height / 2, self.box_width / 2)):
            for sign in (-1, 1):
                mid = [x, y, self.paper_height + 0.00003]
                mid[axis] += sign * half
                size = [self.box_height / 2 + 0.0004, self.box_width / 2 + 0.0004, 0.00002]
                size[axis] = 0.0004
                ET.SubElement(
                    world,
                    "geom",
                    type="box",
                    size=numbers(size),
                    pos=numbers(mid),
                    contype="0",
                    conaffinity="0",
                    rgba=".025 .025 .025 1",
                )
        # A rigid tool adapter on the wrist holds a real colliding marker nib.
        hand = root.find(".//body[@name='gripper']")
        ET.SubElement(
            hand,
            "geom",
            name="marker_barrel",
            type="capsule",
            fromto=".018 0 -.081 .018 0 -.151",
            size=".0036",
            mass=".008",
            rgba=".05 .23 .78 1",
            contype="0",
            conaffinity="0",
        )
        ET.SubElement(
            hand,
            "geom",
            name="marker_tip",
            type="sphere",
            pos=numbers(NIB),
            size=str(self.nib_radius),
            mass=".001",
            rgba=".025 .025 .025 1",
            friction=".28 .001 .0001",
            solref=".008 1",
        )
        contact = root.find("contact")
        if contact is None:
            contact = ET.SubElement(root, "contact")
        ET.SubElement(
            contact,
            "pair",
            geom1="marker_tip",
            geom2="writing_paper",
            friction=".14 .14 .001 .0001 .0001",
            solref=".007 1",
        )
        self.mask = Image.new("L", (self.width, self.height))
        self.paint = ImageDraw.Draw(self.mask)
        self.samples = self.outside = 0
        self.start = self.last = None
        self.lines = []

    def bind(self, model, data):
        super().bind(model, data)
        self.tip = model.geom("marker_tip").id
        self.paper = model.geom("writing_paper").id
        self.table = model.geom("table").id

    def raster_point(self, xy):
        # Same orientation as the calibrated overhead photograph.
        return (
            (xy[1] - self.xy[1]) / self.mpp + self.width / 2,
            (xy[0] - self.xy[0]) / self.mpp + self.height / 2,
        )

    def after_step(self, simulation):
        point = None
        for idx, con in enumerate(self.data.contact):
            if self.tip not in con.geom or con.efc_address < 0 or con.dist > 0:
                continue
            other = con.geom[0] if con.geom[1] == self.tip else con.geom[1]
            if other not in (self.table, self.paper):
                continue
            force = np.zeros(6)
            mujoco.mj_contactForce(self.model, self.data, idx, force)
            if force[0] <= 0.004:
                continue
            point = con.pos[:2].copy()
            if (
                other != self.paper
                or abs(point[0] - self.xy[0]) + self.nib_radius >= self.box_height / 2 - 0.0004
                or abs(point[1] - self.xy[1]) + self.nib_radius >= self.box_width / 2 - 0.0004
            ):
                self.outside += 1
            break
        if point is None:
            self.start = self.last = None
            return
        self.samples += 1
        p = self.raster_point(point)
        r = self.nib_radius / self.mpp
        if self.last is not None:
            self.paint.line([self.raster_point(self.last), p], fill=255, width=round(2 * r))
        self.paint.ellipse([p[0] - r, p[1] - r, p[0] + r, p[1] + r], fill=255)
        # A render-only stroke is drawn from the same measured contacts as the OCR raster.
        if self.start is None or np.linalg.norm(point - self.start) >= 0.00075:
            previous = self.start if self.start is not None else point
            self.lines.append((previous, point))
            self.start = point
        self.last = point

    def decorate_scene(self, scene, simulation):
        color = np.array([0.025, 0.03, 0.045, 1.0], dtype=np.float32)
        for start, end in self.lines:
            if scene.ngeom >= scene.maxgeom:
                break
            z = self.paper_height + 0.00018
            obj = scene.geoms[scene.ngeom]
            mujoco.mjv_initGeom(
                obj, mujoco.mjtGeom.mjGEOM_CAPSULE, np.zeros(3), np.zeros(3), np.eye(3).ravel(), color
            )
            mujoco.mjv_connector(
                obj, mujoco.mjtGeom.mjGEOM_CAPSULE, 0.00085, np.r_[start, z], np.r_[end, z]
            )
            scene.ngeom += 1

    def evaluate(self, simulation, answer=None):
        raw = ""
        bounds = self.mask.getbbox()
        if bounds:
            ink = self.mask.crop(bounds)
            white = Image.new("L", (ink.width + 60, ink.height + 60), 255)
            white.paste(0, (30, 30), ink)
            output = BytesIO()
            white.save(output, format="PNG")
            raw = (
                subprocess.run(
                    ["tesseract", "stdin", "stdout", "-l", "eng", "--psm", "6"],
                    input=output.getvalue(),
                    capture_output=True,
                    check=True,
                    timeout=20,
                )
                .stdout.decode()
                .strip()
            )
        reading = " ".join(raw.casefold().split())
        correct = reading == "hello world"
        in_bounds = bool(bounds) and self.outside == 0
        success = correct and in_bounds
        similarity = SequenceMatcher(None, "hello world", reading).ratio() if reading else 0.0
        score = 100 if success else min(99.0, round(100 * similarity * (1 if in_bounds else 0.5), 1))
        return {
            "success": success,
            "score": score,
            "metrics": {
                "ocr_text": raw,
                "in_bounds": in_bounds,
                "contact_samples": self.samples,
                "outside_samples": self.outside,
                "ink_sha256": hashlib.sha256(self.mask.tobytes()).hexdigest(),
                "recognizer": "Tesseract English, page segmentation 6",
                "stroke_source": "model polylines; mounted physical marker",
            },
        }


class OpticalMeasurement(MeasurementTask):
    task_id = "so101_visual_metrology"

    def build(self, world, root, rng):
        super().build(world, root, rng)
        # Orthographic inspection cameras eliminate depth parallax. Their physical
        # field of view at this resolution supplies an independent metric calibration.
        ortho(world, "overhead", [0.365, 0, 0.65], "1 0 0 0 1 0", 0.200)
        ortho(world, "front", [0.365, -0.55, 0.075], "1 0 0 0 0 1", 0.160)
        world.find("camera[@name='left']").attrib.update(
            pos=".76 -.43 .37", xyaxes=".73 .68 0 -.37 .40 .84", fovy="35"
        )
        world.find("body[@name='ruler_table_x']").set("pos", ".365 -.080 .002")
        world.find("body[@name='ruler_table_y']").set("pos", ".480 .012 .002")
        upright = world.find("body[@name='ruler_upright']")
        upright.attrib.pop("quat")
        upright.set("xyaxes", "0 0 1 -1 0 0")
        upright.set("pos", ".453 .060 .100")

    @staticmethod
    def reticle(image, name):
        if name not in ("front", "overhead"):
            return image
        # A fixed optical graticule, calibrated from the camera span. Its tick
        # positions and labels are independent of the box and its dimensions.
        span = 200.0 if name == "overhead" else 160.0
        scale = HEIGHT / span
        origin_z = 0.0 if name == "overhead" else 75.0
        draw = ImageDraw.Draw(image, "RGBA")
        font = ImageFont.load_default(size=11)
        for axis in (0, 1):
            for mm in range(-150, 176, 5):
                pixel = round(
                    (WIDTH / 2 - 0.5 + mm * scale)
                    if axis == 0
                    else (HEIGHT / 2 - 0.5 - (mm - origin_z) * scale)
                )
                if not 0 <= pixel < (WIDTH if axis == 0 else HEIGHT):
                    continue
                major = mm % 10 == 0
                if axis == 0:
                    draw.line(
                        (pixel, 0, pixel, HEIGHT - 1), fill=(35, 90, 100, 75 if major else 28), width=1
                    )
                    if major:
                        draw.text(
                            (pixel + 2, HEIGHT - 16),
                            str(mm),
                            font=font,
                            fill=(0, 33, 40, 255),
                            stroke_width=1,
                            stroke_fill=(245, 248, 240, 255),
                        )
                else:
                    draw.line(
                        (0, pixel, WIDTH - 1, pixel), fill=(35, 90, 100, 75 if major else 28), width=1
                    )
                    if major:
                        draw.text(
                            (WIDTH - 27, pixel - 6),
                            str(mm),
                            font=font,
                            fill=(0, 33, 40, 255),
                            stroke_width=1,
                            stroke_fill=(245, 248, 240, 255),
                        )
        return image


class InstrumentArm(SO101Robot, TaskSimulation):
    scene_factory = staticmethod(tabletop_scene)

    def _step(self):
        super()._step()
        if self.frame_callback and self.data.time >= self.next_frame:
            self.next_frame = self.data.time + 1.0
            self.frame_callback()

    def __init__(self, task, seed):
        self.frame_callback = None
        self.next_frame = 0.0
        super().__init__(task, seed)


WRITING_GUIDE = """Use the SO-ARM101's mounted marker to write HELLO WORLD, legible, inside the black
rectangle on the paper. Uppercase block letters on one line with a clear word gap work well. Read the current
640×480 overhead image to choose your letter positions. draw executes the polylines you explicitly author:
strokes=[[[u,v],[u,v],...], ...]. Each polyline is one uninterrupted nib-down stroke;
the pen lifts between polylines. Author the shape of every letter yourself. Use your available width,
leave margins, separate adjacent letters and use an extra gap between words. Each draw can contain
up to 32 polylines; you may draw several letters or words together. The controller uses calibrated
pen motion; ink appears only where the nib makes physical contact. Use park if needed for a clear
image. Submit finish when visually satisfied. Use [] for strokes on other actions."""
MEASURE_GUIDE = """Measure the orange box (long horizontal edge, short horizontal edge, and vertical height).
Use the overhead and front calibrated orthographic photographs and the visible rulers. The overhead image
spans 200 mm vertically at 480 pixels (2.4 pixels per mm); its screen horizontal measures length and its
screen vertical measures width. The orthographic front view spans 160 mm vertically (3 pixels per mm).
The front tabletop level is v=464.5, and the box top is higher in the image. Use the solid orange face
edges, not the shadow or rulers; subtract endpoint coordinates before dividing by the image scale.
Thin teal metric graticule lines correspond to 5 mm, darker lines to 10 mm. Grid labels at the bottom
and right are millimetres. A separate black pixel ruler may appear on the overhead image. For a closer
look, inspect(u,v,angle) aims the inspection crop at ANY selected original image pixel
(angle=0 for overhead, 1 for front) and shows the optical detail on the left view; the arm stays clear.
park physically moves the SO-ARM101 away for inspection. submit with dimensions_mm=[length,width,height],
in millimetres; all three must be within 2 mm. Use [] for dimensions_mm on other actions."""


class InstrumentScenario:
    def __init__(self, task, seed):
        self.writing = task == "writing"
        self.sim = InstrumentArm(ContactWriting() if self.writing else OpticalMeasurement(), seed)
        self.motion = PourControls(self.sim)
        self.actions = (
            ("draw", "park", "finish") if self.writing else ("inspect", "park", "submit", "finish")
        )
        self.terminal_actions = () if self.writing else ("submit",)
        self.guide = WRITING_GUIDE if self.writing else MEASURE_GUIDE
        self.fields = (
            {
                "strokes": {
                    "type": "array",
                    "items": {"type": "array", "items": {"type": "array", "items": {"type": "integer"}}},
                }
            }
            if self.writing
            else {"dimensions_mm": {"type": "array", "items": {"type": "number"}}}
        )
        self.crop = None
        # Start with the arm parked beside the workspace to keep calibrated views readable.
        self.park = np.deg2rad([-64, -60, 60, 35, 0])
        self.motion.move(self.park, 1.3)
        self.sim.wait(0.25)

    def observe(self):
        views = {}
        for name in ("overhead", "front", "left", "wrist"):
            img = Image.open(BytesIO(self.sim.observe(name))).convert("RGB")
            views[name] = img if self.writing else OpticalMeasurement.reticle(img, name)
        if self.crop:
            name, u, v = self.crop
            # Nearest-neighbor enlargement preserves the original pixels and graduations.
            x = int(np.clip(u - 128, 0, WIDTH - 256))
            y = int(np.clip(v - 96, 0, HEIGHT - 192))
            views["left"] = (
                views[name]
                .crop((x, y, x + 256, y + 192))
                .resize((WIDTH, HEIGHT), Image.Resampling.NEAREST)
            )
        return views

    def _pen(self, uv, z, duration=0.14):
        xy = overhead_point(self.sim, "overhead", *uv, z)
        q = self.motion.solve(np.r_[xy, z], NIB, 0.0, PITCH)
        seconds = max(duration, float(np.max(np.abs(q - self.motion.joints))) / 1.05)
        self.sim.move_joints(q.tolist(), seconds)
        self.motion.joints = q
        self.sim.wait(0.07)

    def execute(self, d):
        action = d["action"]
        if action == "park":
            self.motion.move(self.park, 1.2)
            self.crop = None
            return "Arm parked; inspect the scene."
        if self.writing and action == "draw":
            strokes = d["strokes"]
            if (
                not 1 <= len(strokes) <= 32
                or any(not 2 <= len(line) <= 64 for line in strokes)
                or any(
                    len(p) != 2
                    or any(type(n) is not int for n in p)
                    or not (0 <= p[0] < WIDTH and 0 <= p[1] < HEIGHT)
                    for line in strokes
                    for p in line
                )
            ):
                raise ValueError("Supply one to 32 polylines of 2–64 in-image pixel pairs each.")
            for line in strokes:
                self._pen(line[0], 0.020, 0.35)
                self._pen(line[0], 0.0028, 0.30)
                for a, b in pairwise(line):
                    for t in np.linspace(0.0, 1.0, max(2, math.ceil(math.dist(a, b) / 12) + 1))[1:]:
                        point = np.array(a) + (np.array(b) - a) * t
                        self._pen(point, 0.0028, 0.15)
                self._pen(line[-1], 0.020, 0.24)
            return f"Completed {len(strokes)} pen trajectories; inspect the paper."
        if not self.writing and action == "inspect":
            u, v = d["u"], d["v"]
            if not (0 <= u < WIDTH and 0 <= v < HEIGHT and d["angle"] in (0, 1)):
                raise ValueError(
                    "Choose an original camera pixel and set angle to 0 (overhead) or 1 (front)."
                )
            self.crop = ("front" if d["angle"] else "overhead", u, v)
            return "Selected camera region enlarged on the left view."
        if not self.writing and action == "submit":
            dims = d["dimensions_mm"]
            if (
                not isinstance(dims, list)
                or len(dims) != 3
                or not all(type(n) in (int, float) and math.isfinite(n) and 0 < n <= 1000 for n in dims)
            ):
                raise ValueError(
                    "Submit three positive finite dimensions in millimetres, length, width, height."
                )
            self.sim.set_answer({"dimensions_m": [n / 1000 for n in dims]})
            return "Box dimensions submitted."
        raise ValueError("Unknown task action.")

    def grade(self):
        report = self.sim.finish()
        m = report["metrics"]
        if self.writing:
            summary = f"Ink read as {m['ocr_text']!r}; all ink inside box: {m['in_bounds']}."
        else:
            answer = report["answer"]
            m["submitted_mm"] = [round(1000 * n, 4) for n in answer["dimensions_m"]] if answer else []
            m["errors_mm"] = [round(1000 * n, 4) for n in m.get("absolute_errors_m", [])]
            summary = (
                f"Length/width/height errors: {m['errors_mm']} mm."
                if answer
                else "No dimensions submitted."
            )
        return {
            "success": report["success"],
            "score": report["score"],
            "summary": summary,
            "metrics": m,
            "safe": report["safe"],
            "sim_time_s": round(report["sim_time"], 6),
            "scene_sha256": report["scene_sha256"],
        }

    def robot_state(self):
        return self.sim.robot_state()

    def set_frame_callback(self, callback):
        self.sim.frame_callback = callback
        self.sim.next_frame = self.sim.data.time + 1.0

    def close(self):
        self.sim.close()


def create(task, seed, revision="v1"):
    if task not in ("writing", "measurement") or revision != "v1":
        raise ValueError("Unknown instrument task or revision.")
    return InstrumentScenario(task, seed)
