from ..memory_condense_helpers import MEMORY_CONDENSE_OUTPUT_SCHEMA
from .module_profiles_common import build_module_profiles, build_profile

PROMPT_PROFILES = build_module_profiles(
    "memory",
    ["relevance_ranking", "condensation", "conflict_detection", "retrieval_planning"],
    reasoning_style="analytical",
    allowed_command_types=["NO_ACTION", "STORE_MEMORY", "RETRIEVE_MEMORY", "ASK_USER", "RUN_ANALYSIS"],
)

PROMPT_PROFILES["chatlog_reranking"] = build_profile(
    prompt_id="memory.chatlog_reranking.v1",
    module_name="memory",
    function_name="chatlog_reranking",
    reasoning_style="analytical",
    allowed_command_types=["NO_ACTION"],
)
PROMPT_PROFILES["chatlog_reranking"].update(
    {
        "structured_output_kind": "plain_object_keys",
        "purpose": "Rank chatlog export files by operator-useful actionable content; JSON object with rankings array only.",
        "output_schema": {
            "type": "object",
            "required": ["rankings"],
            "properties": {
                "rankings": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "required": ["file", "actionable", "priority", "category", "reason"],
                    },
                }
            },
        },
        "validation_rules": {
            "json_only": True,
            "require_envelope": False,
            "required_top_level_keys": ["rankings"],
            "list_keys": ["rankings"],
        },
    }
)

# Legacy contract: JSON array of {thought, category, priority} — not the internal command envelope.
PROMPT_PROFILES["condensation"].update(
    {
        "structured_output_kind": "memory_condense_array",
        "output_schema": MEMORY_CONDENSE_OUTPUT_SCHEMA,
        "validation_rules": {
            "json_only": True,
            "require_envelope": False,
            "reject_unknown_command_types": False,
        },
    }
)
