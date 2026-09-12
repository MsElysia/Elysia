from .module_profiles_common import build_module_profiles

PROMPT_PROFILES = build_module_profiles(
    "parallel_processing",
    ["independent_analysis", "disagreement_detection", "consensus_synthesis"],
    reasoning_style="synthesis",
)
