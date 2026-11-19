"""Reachable four-block tower, evaluated with the benchmark's physical support graph."""
import numpy as np

from robo_mj_bench.tasks.tower import TowerTask
from packing_scenarios import body, box, COLORS


class Tower:
    actions = ("pick", "place_table", "place_level2", "place_level3", "place_level4", "park", "finish")
    guide = """Build the tallest freestanding tower using all four foam blocks. Each block
is 20 mm tall and the blocks have different square footprints. Use a large base and
center each successively smaller block on the one below. Keep their marked faces up,
release the gripper, and inspect the final stack. A hand-supported tower fails.
Pick selects a block on the tabletop by its top-center overhead pixel (u,v).
Use place_level2 on a one-block base, place_level3 on a two-block stack, and
place_level4 on a three-block stack. Aim at the overhead center of the current
TOP face. These commands calibrate the gripper height for that tier; you select
the stack and aim. place_table sets a held block on bare table.
The angle in pick/place is the jaw-closing axis clockwise from overhead-image right.
Align the jaws with flat sides. Keeping the same angle on pick and release keeps
the orientation. Park clears the view if the jaws hide the stack. Use the initial
overhead view for loose blocks that the arm temporarily hides. Submit finish."""
    height = .020

    def __init__(self, revision="v1"):
        if revision != "v1":
            raise ValueError("Unknown tower controller revision")
        self.evaluator = TowerTask()

    def build(self, root, world, rng):
        locations = [(0.200, 0.056), (0.196, -0.075), (0.166, 0.000), (0.236, -0.006)]
        rng.shuffle(locations)
        sizes = []
        for i, (side, color, location) in enumerate(zip((.036, .030, .026, .022),
                                                        ("red","blue","yellow","green"), locations)):
            xy = np.asarray(location) + rng.uniform(-.002, .002, 2)
            block = body(world, f"tower_block_{i}", [*xy, self.height / 2 + .0001], free=True)
            size = np.array([side / 2, side / 2, self.height / 2])
            sizes.append(size)
            box(block, f"tower_geom_{i}", size, [0, 0, 0], COLORS[color], .012)
            box(block, f"top_mark_{i}", [.003, .003, .00005], [0, 0, self.height/2+.00005],
                "1 1 1 1", 0, contype="0", conaffinity="0")
        self.evaluator.half_sizes = sizes
        self.evaluator.maximum_height = len(sizes) * self.height

    def pick_place(self, action):
        if action == "pick":
            return self.height, .016, .074, 48
        levels = {"place_table": 0, "place_level2": 1, "place_level3": 2, "place_level4": 3}
        support = levels[action] * self.height
        release = support + .019
        return support, release, max(.076, release + .012), 48

    def park(self, sim):
        # Raise the shoulder before rotating the base past a tall stack.
        shoulder_up = sim.data.ctrl.copy()
        shoulder_up[1] = sim.park[1]
        sim.move(shoulder_up, .6)
        sim.move(sim.park, .9)
        return "Arm parked with open jaws."

    def grade(self, sim):
        # The upstream contour/contact/speed grader is arm-independent. Bind the
        # fixture geometries directly (the upstream bind expects an arm named "arm").
        scorer = self.evaluator
        scorer.model, scorer.data = sim.model, sim.data
        scorer.geom_ids = [sim.model.geom(f"tower_geom_{i}").id for i in range(4)]
        scorer.body_ids = [sim.model.body(f"tower_block_{i}").id for i in range(4)]
        scorer.table_geom = sim.model.geom("table").id
        report = scorer.evaluate(sim)
        metrics = report["metrics"]
        report["summary"] = (f'{metrics["stacked_blocks"]}/4 blocks in a freestanding stack, '
                             f'{1000*metrics["stack_height"]:.1f} of {1000*scorer.maximum_height:.0f} mm tall.')
        return report
