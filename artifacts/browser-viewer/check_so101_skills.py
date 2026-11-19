"""Compare the two SO-101 controllers with the same RGB picks and scripted tilts."""
import io
import json

import numpy as np
from PIL import Image

from pouring_arms import load_pouring_arm


def rim_centers(overhead_png):
    # These fixtures start with the receiver in the upper half. The lower
    # half also contains orange robot parts. Model-controlled episodes receive
    # the full RGB views and choose their own points.
    with Image.open(io.BytesIO(overhead_png)) as image:
        rgb = np.asarray(image.convert("RGB"), dtype=float)
    red, green, blue = rgb.transpose(2, 0, 1)
    source = (blue > 1.7 * red) & (blue > 1.4 * green)
    receiver = (red > 2 * blue) & (red > 1.6 * green) & (green > 1.3 * blue)
    receiver[rgb.shape[0] // 2:] = False
    centers = []
    for mask in (source, receiver):
        y, x = np.where(mask)
        if not len(x):
            raise ValueError("The fixture camera could not resolve both cup colors.")
        centers.append((round(float(np.median(x))), round(float(np.median(y)))))
    return centers


def check(seed, angles, version):
    sim, controller, _ = load_pouring_arm("so101", seed, skill_version=version)
    try:
        source, target = rim_centers(sim.observe("overhead"))
        controls = controller(sim)
        for action, (u, v) in (("approach", source), ("grasp", (0, 0)), ("lift", (0, 0)), ("align", target)):
            controls.execute(dict(action=action, u=u, v=v, angle=0))
        for angle in angles:
            controls.execute(dict(action="tip", u=0, v=0, angle=angle))
        for action in ("upright", "return", "release", "park"):
            controls.execute(dict(action=action, u=0, v=0, angle=0))
        report = sim.finish()
        return dict(seed=seed, skill_version=version, angles=angles, source_uv=source, target_uv=target,
                    captured=report["metrics"]["beads_in_target"], spilled=report["metrics"]["beads_spilled"],
                    score=report["score"])
    finally:
        sim.close()


if __name__ == "__main__":
    layouts = [(seed, [60, 95, 120]) for seed in (101, 307, 502, 815)]
    layouts.extend([(166, [45, 75, 100, 120]), (720, [75, 110, 120])])
    for seed, angles in layouts:
        for version in ("so101-pour-v1", "so101-pour-v2"):
            print(json.dumps(check(seed, angles, version)), flush=True)
