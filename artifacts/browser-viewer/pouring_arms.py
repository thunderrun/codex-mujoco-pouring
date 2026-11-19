"""Load an arm's pouring physics, controls and operator skill as a matched set."""
from pathlib import Path

from arm_config import DEFAULT_SKILL, checked_skill
from pouring_score import TABLETOP_SCORER, pouring_task


def load_pouring_arm(arm, seed, *, scoring_version=TABLETOP_SCORER, skill_version=None):
    if arm not in DEFAULT_SKILL:
        raise ValueError(f"Unknown pouring arm: {arm!r}")
    version = checked_skill(arm, DEFAULT_SKILL[arm] if skill_version is None else skill_version)
    task = pouring_task(scoring_version)
    if arm == "so101":
        from so101_scene import create_so101_pouring

        if version == "so101-pour-v2":
            from so101_controls_v2 import PourControls

            guide = (Path(__file__).resolve().parent / "skills" / version / "SKILL.md").read_text()
        else:
            from so101_controls import GUIDE as guide, PourControls
        return create_so101_pouring(seed, task=task), PourControls, guide

    from pour_controls import GUIDE, PourControls
    from robo_mj_bench.task_simulation import TaskSimulation

    return TaskSimulation(task, seed), PourControls, GUIDE
