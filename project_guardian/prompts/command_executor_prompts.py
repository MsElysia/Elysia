from .module_profiles_common import build_module_profiles

PROMPT_PROFILES = build_module_profiles(
    "command_executor",
    ["command_conversion", "execution_interpretation", "execution_review"],
    reasoning_style="evaluator",
    allowed_command_types=["NO_ACTION", "ASK_USER", "RUN_ANALYSIS", "ESCALATE_TO_HUMAN"],
)
