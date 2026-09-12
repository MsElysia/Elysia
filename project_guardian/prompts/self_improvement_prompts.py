from .module_profiles_common import build_module_profiles

PROMPT_PROFILES = build_module_profiles(
    "self_improvement",
    ["bug_detection", "improvement_proposals", "patch_planning", "architecture_critique"],
    reasoning_style="evaluator",
    allowed_command_types=["NO_ACTION", "ASK_USER", "RUN_ANALYSIS", "PROPOSE_CODE_CHANGE", "ESCALATE_TO_HUMAN"],
)
