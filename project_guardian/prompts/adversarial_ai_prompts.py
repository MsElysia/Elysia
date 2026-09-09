from .module_profiles_common import build_module_profiles

PROMPT_PROFILES = build_module_profiles(
    "adversarial_ai",
    ["weakness_detection", "exploit_analysis", "failure_mode_prediction", "adversarial_critique"],
    reasoning_style="adversarial",
    allowed_command_types=["NO_ACTION", "RUN_ANALYSIS", "ASK_USER", "ESCALATE_TO_HUMAN"],
)
