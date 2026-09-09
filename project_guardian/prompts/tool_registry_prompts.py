from .module_profiles_common import build_module_profiles

PROMPT_PROFILES = build_module_profiles(
    "tool_registry",
    ["tool_selection", "argument_planning", "tool_result_interpretation"],
    reasoning_style="planning",
)
