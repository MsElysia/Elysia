from .module_profiles_common import build_module_profiles

PROMPT_PROFILES = build_module_profiles(
    "social_intelligence",
    ["tone_analysis", "user_intent_detection", "relationship_interpretation", "response_strategy"],
    reasoning_style="synthesis",
)

PROMPT_PROFILES["response_strategy"].update(
    {
        "structured_output_kind": "plain_object_keys",
        "purpose": (
            "Draft bounded forum replies from thread notes; "
            "single JSON object with reply_draft, outreach_draft, follow_up_questions, user_summary."
        ),
        "output_schema": {
            "type": "object",
            "required": ["reply_draft", "outreach_draft", "follow_up_questions", "user_summary"],
        },
        "validation_rules": {
            "json_only": True,
            "require_envelope": False,
            "required_top_level_keys": ["reply_draft", "outreach_draft", "follow_up_questions", "user_summary"],
            "list_keys": ["follow_up_questions"],
        },
    }
)
