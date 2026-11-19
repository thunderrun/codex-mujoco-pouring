"""Local pouring scorer for a finite tabletop with no collision floor below it."""
import numpy as np

from robo_mj_bench.tasks.pouring import PouringTask

UPSTREAM_SCORER = "upstream-v0.3.0"
TABLETOP_SCORER = "tabletop-v2"


class TabletopPouringTask(PouringTask):
    def bind(self, model, data):
        super().bind(model, data)
        table = model.geom("table")
        self._table_bottom = data.geom_xpos[table.id, 2] - table.size[2]

    def evaluate(self, simulation, answer=None):
        result = super().evaluate(simulation, answer)
        metrics = result["metrics"]
        # The upstream environment has no floor below its horizontal table. Once
        # a spilled bead has cleared the underside and is falling, it cannot land
        # on the tabletop again. It still counts against transfer and spill limits.
        lost = {b for b in self._spilled
                if metrics["finite"] and self.data.xpos[b, 2] + self.bead_radius < self._table_bottom
                and self.data.cvel[b, 5] < 0}
        metrics["beads_lost_below_table"] = len(lost)
        metrics["all_beads_stable"] = metrics["beads_stable"]
        if not lost or metrics["beads_stable"]:
            return result
        # Apply the upstream linear and tangential speed limits to every bead
        # still in play, including spilled beads rolling across the tabletop.
        metrics["beads_stable"] = all(
            np.linalg.norm(self.data.cvel[b, 3:]) < .02
            and np.linalg.norm(self.data.cvel[b, :3]) * self.bead_radius < .02
            for b in self._beads if b not in lost
        )
        if (metrics["beads_stable"] and metrics["released"] and metrics["cups_stable"]
                and metrics["cups_separate"] and not metrics["ambiguous_beads"]):
            fraction = metrics["beads_in_target"] / metrics["beads_total"]
            result["success"] = fraction >= .9 and metrics["beads_spilled"] <= 1
            result["score"] = 100.0 if result["success"] else min(99., 100. * fraction)
        return result


def pouring_task(version):
    if version == TABLETOP_SCORER:
        return TabletopPouringTask()
    if version == UPSTREAM_SCORER:
        return PouringTask()
    raise ValueError(f"Unknown pouring scorer version: {version!r}")
