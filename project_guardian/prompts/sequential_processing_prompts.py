from .module_profiles_common import build_module_profiles

PROMPT_PROFILES = build_module_profiles(
    "sequential_processing",
    ["stage_by_stage_transformation", "handoff_formatting", "accumulated_context_compression"],
    reasoning_style="planning",
)

PROMPT_PROFILES["accumulated_context_compression"].update(
    {
        "structured_output_kind": "plain_object_keys",
        "purpose": "Compress long retrieved or learned text into a short operator-useful summary (plain JSON object).",
        "output_schema": {
            "type": "object",
            "required": ["compressed_text"],
            "properties": {"compressed_text": {"type": "string"}},
        },
        "validation_rules": {
            "json_only": True,
            "require_envelope": False,
            "required_top_level_keys": ["compressed_text"],
            "list_keys": [],
        },
    }
)
