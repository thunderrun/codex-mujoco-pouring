"""Load an arm's pouring physics and matching camera-based controls."""


def load_pouring_arm(arm, seed):
    if arm == "so101":
        from so101_controls import GUIDE, PourControls
        from so101_scene import create_so101_pouring

        return create_so101_pouring(seed), PourControls, GUIDE
    if arm == "yam":
        from pour_controls import GUIDE, PourControls
        from robo_mj_bench.tasks.registry import create_simulation

        return create_simulation("pouring", seed), PourControls, GUIDE
    raise ValueError(f"Unknown pouring arm: {arm!r}")
