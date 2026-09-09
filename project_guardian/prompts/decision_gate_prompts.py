from .module_profiles_common import build_module_profiles

PROMPT_PROFILES = build_module_profiles(
    "decision_gate",
    ["approve_reject_defer", "risk_classification", "missing_information_analysis"],
    reasoning_style="evaluator",
    allowed_command_types=["NO_ACTION", "ASK_USER", "RUN_ANALYSIS", "ESCALATE_TO_HUMAN"],
)
