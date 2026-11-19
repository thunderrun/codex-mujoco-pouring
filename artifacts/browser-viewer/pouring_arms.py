"""Load an arm's pouring physics and matching camera-based controls."""

from pouring_score import TABLETOP_SCORER, pouring_task


def load_pouring_arm(arm, seed, *, scoring_version=TABLETOP_SCORER):
    task = pouring_task(scoring_version)
    if arm == "so101":
        from so101_controls import GUIDE, PourControls
        from so101_scene import create_so101_pouring

        return create_so101_pouring(seed, task=task), PourControls, GUIDE
    if arm == "yam":
        from pour_controls import GUIDE, PourControls
        from robo_mj_bench.task_simulation import TaskSimulation

        return TaskSimulation(task, seed), PourControls, GUIDE
    raise ValueError(f"Unknown pouring arm: {arm!r}")
