"""Eight colored pieces, a passive socket board, and its public target picture."""

import xml.etree.ElementTree as ET

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from packing_scenarios import body, box, fmt

KINDS = ("square", "triangle", "hexagon", "circle")
PALETTE = {
    "red": ".84 .11 .08 1",
    "blue": ".06 .33 .86 1",
    "green": ".07 .59 .22 1",
    "yellow": ".92 .68 .04 1",
}
PIECE_HALF_HEIGHT = 0.004
FLOOR = 0.003
# Apertures have an actual wall and a beveled mouth. The bottom aperture defines containment.
FLOOR_GAP = 0.0055
WALL_TOP = 0.010

GUIDE = """Seat all eight colored pieces in the physical board to match the attached goal_reference picture.
The picture has the same orientation as the overhead camera. Each target needs the correct
shape AND color. The board has two rows of four recessed sockets. Use the picture to
distinguish the pair of pieces of each shape. The loose pieces have raised center
handles. The white symbol on each handle repeats its colored outline. pick(u,v,angle) pinches the handle at the specified overhead pixel and lifts.
place(u,v,angle) lowers the held piece at your chosen socket center, opens, and withdraws.
Empty recesses have a dark floor; occupied ones show a colored top. All piece handles
and sockets start axis-aligned, so use angle 90 for both pickup and release. It opens into the space between rows and preserves
the orientation. Angle is clockwise from image right. Inspect after each operation.
The initial overhead reference can help when the current wrist obscures a destination.
Finish after all eight are seated and released. Only use the current views and public
reference picture; there is no per-piece grader feedback before submission."""


def polygon(kind):
    if kind == "square":
        return np.array([[-0.009, -0.009], [0.009, -0.009], [0.009, 0.009], [-0.009, 0.009]])
    n = {"triangle": 3, "hexagon": 6, "circle": 24}[kind]
    r = 0.014 if kind == "triangle" else 0.011
    a = np.arange(n) * 2 * np.pi / n
    return np.stack([np.cos(a) * r, np.sin(a) * r], axis=1)


def prism(assets, name, bottom, top, z0, z1):
    points = np.vstack(
        [
            np.column_stack((bottom, np.full(len(bottom), z0))),
            np.column_stack((top, np.full(len(top), z1))),
        ]
    )
    ET.SubElement(assets, "mesh", name=name, vertex=fmt(points.ravel()))


def geom(parent, name, mesh, rgba, mass=None):
    props = dict(
        type="mesh", name=name, mesh=mesh, rgba=rgba, friction="1.15 .012 .001", solref=".008 1"
    )
    if mass is not None:
        props["mass"] = str(mass)
    return ET.SubElement(parent, "geom", props)


class ShapeMatching:
    actions = ("pick", "place", "park", "finish")
    guide = GUIDE

    def build(self, root, world, rng):
        self.targets = {}
        self.pieces = []
        self.slots = []
        self.board_center = np.array([0.188, 0.073]) + rng.uniform(-0.0015, 0.0015, 2)
        assets = root.find("asset")
        board = body(world, "matching_board", [*self.board_center, 0])
        box(board, "matching_floor", [0.060, 0.090, FLOOR / 2], [0, 0, FLOOR / 2], ".22 .28 .29 1")
        colors = list(PALETTE)
        order = [list(rng.permutation(KINDS)), list(rng.permutation(KINDS))]
        assignments = dict(zip(KINDS, rng.permutation(colors)))
        alternatives = {kind: colors[(colors.index(assignments[kind]) + 2) % 4] for kind in KINDS}
        colors_by_row = [assignments, alternatives]
        positions = [(x, y) for x in (0.163, 0.208) for y in (-0.037, -0.072, -0.107, -0.142)]
        # The loose rows are shuffled relative to the reference.
        rng.shuffle(positions)
        for kind in KINDS:
            poly = polygon(kind)
            prism(assets, "piece_" + kind, poly, poly, -PIECE_HALF_HEIGHT, PIECE_HALF_HEIGHT)
            prism(assets, "mark_" + kind, poly * 0.43, poly * 0.43, 0.020, 0.02025)
            radius = min(
                abs(np.cross(poly[(i + 1) % len(poly)] - a, -a))
                / np.linalg.norm(poly[(i + 1) % len(poly)] - a)
                for i, a in enumerate(poly)
            )
            inner = poly * (1 + FLOOR_GAP / radius)
            mouth = poly * (1 + (FLOOR_GAP + 0.0018) / radius)
            outer = poly * (1 + (FLOOR_GAP + 0.0038) / radius)
            for i in range(len(poly)):
                j = (i + 1) % len(poly)
                prism(
                    assets,
                    f"wall_{kind}_{i}",
                    [inner[i], outer[i], outer[j], inner[j]],
                    [mouth[i], outer[i], outer[j], mouth[j]],
                    0,
                    WALL_TOP - FLOOR,
                )
        for row_index, row in enumerate(order):
            for col, kind in enumerate(row):
                color = colors_by_row[row_index][kind]
                xy = self.board_center + [(0.026 if row_index == 0 else -0.026), (0.066 - 0.044 * col)]
                socket = body(world, f"socket_{row_index}_{col}", [*xy, FLOOR])
                poly = polygon(kind)
                for k in range(len(poly)):
                    geom(socket, f"ring_{row_index}_{col}_{k}", f"wall_{kind}_{k}", ".76 .79 .71 1")
                name = color + "_" + kind
                self.targets[name] = xy
                self.slots.append((row_index, col, color, kind))
                self.pieces.append((name, kind))
                pos = np.array(positions.pop()) + rng.uniform(-0.001, 0.001, 2)
                piece = body(world, name, [*pos, PIECE_HALF_HEIGHT + 0.0001], free=True)
                geom(piece, name + "_shape", "piece_" + kind, PALETTE[color], 0.017)
                box(piece, name + "_handle", [0.008, 0.008, 0.008], [0, 0, 0.012], PALETTE[color], 0.002)
                mark = geom(piece, name + "_mark", "mark_" + kind, ".98 .98 .94 1", 0.00001)
                mark.set("contype", "0")
                mark.set("conaffinity", "0")

    def reference_image(self):
        picture = Image.new("RGB", (640, 330), "#e8ecdf")
        draw = ImageDraw.Draw(picture)
        font = ImageFont.truetype("DejaVuSans.ttf", 17)
        title = ImageFont.truetype("DejaVuSans-Bold.ttf", 20)
        draw.text((18, 10), "Target board · overhead orientation", fill="#203128", font=title)
        draw.rounded_rectangle((12, 47, 627, 317), radius=9, fill="#384b4d")
        for row, col, color, kind in self.slots:
            u, v = 86 + col * 153, 103 + row * 130
            poly = polygon(kind)
            points = [(u - y * 2900, v - x * 2900) for x, y in poly]
            fill = tuple(round(float(k) * 255) for k in PALETTE[color].split()[:3])
            draw.polygon(points, fill=fill, outline="#f7f6e5", width=2)
            draw.text((u, v + 40), f"{color} {kind}", fill="#ffffff", anchor="mt", font=font)
        return picture

    def pick_place(self, action):
        return {"pick": (0.024, 0.019, 0.074, 30), "place": (FLOOR, 0.030, 0.074, 30)}[action]

    def grade(self, sim):
        placed = {}
        model, data = sim.model, sim.data
        for name, kind in self.pieces:
            bid = model.body(name).id
            pos, rotation = data.xpos[bid], data.xmat[bid].reshape(3, 3)
            poly = polygon(kind)
            xyz = np.array([[x, y, z] for z in (-PIECE_HALF_HEIGHT, PIECE_HALF_HEIGHT) for x, y in poly])
            real = xyz @ rotation.T + pos
            xy = real[:, :2] - self.targets[name]
            inside = True
            for i, a in enumerate(poly):
                direction = poly[(i + 1) % len(poly)] - a
                inward = np.array([-direction[1], direction[0]]) / np.linalg.norm(direction)
                if np.min((xy - a) @ inward) < -FLOOR_GAP - 0.00015:
                    inside = False
                    break
            flat = rotation[2, 2] > 0.992 and abs(pos[2] - FLOOR - PIECE_HALF_HEIGHT) < 0.0013
            placed[name] = bool(inside and flat and sim.settled_and_released(name))
        n = sum(placed.values())
        return dict(
            success=n == len(placed),
            score=n * 100 / len(placed),
            correct_count=n,
            pieces_total=len(placed),
            seated=placed,
            summary=f"{n}/{len(placed)} colored shapes seated in the reference arrangement.",
        )
