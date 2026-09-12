from .module_profiles_common import build_module_profiles

PROMPT_PROFILES = build_module_profiles(
    "autonomy",
    ["goal_selection", "next_action_planning", "task_decomposition", "priority_ranking"],
    reasoning_style="planning",
)
