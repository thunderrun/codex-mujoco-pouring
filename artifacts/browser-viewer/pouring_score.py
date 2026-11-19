"""Local pouring scorer for a finite tabletop with no collision floor below it."""
import numpy as np

from robo_mj_bench.task_simulation import TaskSimulation
from robo_mj_bench.tasks.pouring import PouringTask

UPSTREAM_SCORER = "upstream-v0.3.0"
TABLETOP_SCORER = "tabletop-v2"
FINAL_CAPTURE_SCORER = "final-capture-v3"


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


def final_capture_score(metrics):
    valid = (metrics["finite"] and metrics["released"] and metrics["cups_stable"]
             and metrics["cups_separate"] and metrics["beads_stable"] and not metrics["ambiguous_beads"])
    return 100.0 * metrics["beads_in_target"] / metrics["beads_total"] if valid else 0.0


class FinalCapturePouringTask(TabletopPouringTask):
    def bind(self, model, data):
        super().bind(model, data)
        self._table_geom = model.geom("table").id
        self._bead_set = set(self._beads)
        self._bead_ids = np.asarray(self._beads)

    def _within_cup_walls(self, cup, bead, radius):
        # A bead can penetrate the compliant cup floor slightly on impact.
        # Use the whole interior when classifying a collision during motion.
        rotation = self.data.xmat[cup].reshape(3, 3)
        local = rotation.T @ (self.data.xpos[bead] - self.data.xpos[cup])
        return np.linalg.norm(local[:2]) < radius and -self.bead_radius <= local[2] <= self.rim_height

    def after_step(self, simulation):
        # A bead contacting the receiving cup base can momentarily sit below
        # the stricter settled containment threshold without touching the table.
        contacts = self.data.contact
        pairs = contacts.geom[(contacts.dist <= 0) & (contacts.efc_address >= 0)]
        for table_side in (0, 1):
            touching = pairs[pairs[:, table_side] == self._table_geom, 1 - table_side]
            for bead in self._bead_set.intersection(self.model.geom_bodyid[touching]):
                if (bead not in self._spilled
                        and not self._within_cup_walls(self._source, bead, self.source_radius)
                        and not self._within_cup_walls(self._target, bead, self.target_radius)):
                    self._spilled.add(bead)
        fallen = ((self.data.xpos[self._bead_ids, 2] + self.bead_radius < self._table_bottom)
                  & (self.data.cvel[self._bead_ids, 5] < 0))
        self._spilled.update(self._bead_ids[fallen])

    def evaluate(self, simulation, answer=None):
        result = super().evaluate(simulation, answer)
        result["score"] = final_capture_score(result["metrics"])
        return result


class PouringSimulation(TaskSimulation):
    def finish(self):
        report = super().finish()
        if isinstance(self.task, FinalCapturePouringTask):
            # The upstream finish step promotes strict passes to 100 and caps
            # other results at 99. Keep its strict pass and safety checks, but
            # award the independently requested final-capture score for v3.
            report["score"] = final_capture_score(report["metrics"]) if report["safe"] else 0.0
            report["scoring_version"] = FINAL_CAPTURE_SCORER
        return report


def pouring_task(version):
    if version == FINAL_CAPTURE_SCORER:
        return FinalCapturePouringTask()
    if version == TABLETOP_SCORER:
        return TabletopPouringTask()
    if version == UPSTREAM_SCORER:
        return PouringTask()
    raise ValueError(f"Unknown pouring scorer version: {version!r}")
