"""Robot arms and compatible pouring skills shared by the runner and viewer."""

DEFAULT_ARM = "so101"
ARM_LABELS = {"so101": "SO-ARM101", "yam": "I2RT YAM"}

LEGACY_SKILL = {"so101": "so101-pour-v1", "yam": "yam-pour-v1"}
DEFAULT_SKILL = {**LEGACY_SKILL, "so101": "so101-pour-v2"}

ARM_SKILLS = {
    "so101": {"so101-pour-v1": "v1 · Original", "so101-pour-v2": "v2 · Low-drop pour"},
    "yam": {"yam-pour-v1": "v1 · Original"},
}


def checked_skill(arm, version):
    if not isinstance(version, str) or version not in ARM_SKILLS[arm]:
        raise ValueError(f"Choose a supported pouring skill for {ARM_LABELS[arm]}.")
    return version
