from .module_profiles_common import build_module_profiles, build_profile

PROMPT_PROFILES = build_module_profiles(
    "mutation_engine",
    ["mutation_proposal", "usefulness_scoring", "mutation_risk_review"],
    reasoning_style="adversarial",
)

PROMPT_PROFILES["openai_file_rewrite"] = build_profile(
    prompt_id="mutation_engine.openai_file_rewrite.v1",
    module_name="mutation_engine",
    function_name="openai_file_rewrite",
    reasoning_style="evaluator",
    allowed_command_types=["NO_ACTION", "PROPOSE_CODE_CHANGE"],
)
PROMPT_PROFILES["openai_file_rewrite"].update(
    {
        "structured_output_kind": "plain_object_keys",
        "purpose": (
            "Rewrite one source file per operator instruction; respond with JSON only containing "
            "the full replacement source under proposed_source."
        ),
        "behavioral_instructions": [
            "Return ONE JSON object only. Required key: proposed_source (string) = complete updated file contents.",
            "Do not emit markdown fences around JSON or around code; JSON string escapes must be valid.",
            "Do not use os.system, subprocess, eval, exec, __import__ tricks, or network I/O in generated code unless task explicitly requires documented imports.",
            "Preserve existing behavior unless the task asks for documentation or clarity improvements only.",
        ],
        "output_schema": {
            "type": "object",
            "required": ["proposed_source"],
            "properties": {"proposed_source": {"type": "string"}},
        },
        "validation_rules": {
            "json_only": True,
            "require_envelope": False,
            "required_top_level_keys": ["proposed_source"],
            "list_keys": [],
        },
    }
)
