from .module_profiles_common import build_module_profiles, build_profile

PROMPT_PROFILES = build_module_profiles(
    "implementer",
    ["plan_step", "verify_patch"],
    reasoning_style="technical",
    allowed_command_types=["NO_ACTION"],
)

PROMPT_PROFILES["codegen_patch"] = build_profile(
    prompt_id="implementer.codegen_patch.v1",
    module_name="implementer",
    function_name="codegen_patch",
    reasoning_style="technical",
    allowed_command_types=["NO_ACTION"],
)
PROMPT_PROFILES["codegen_patch"].update(
    {
        "structured_output_kind": "plain_object_keys",
        "forbidden_outputs": [],
        "purpose": (
            "Generate complete updated file contents for implementer proposals; respond with JSON only "
            "embedding the full FILE-block document under patch_document."
        ),
        "behavioral_instructions": [
            "Return ONE JSON object only. Required key: patch_document (string).",
            "The patch_document string must use this exact layout for each target file:\n"
            "FILE: <file_path>\n<complete file content>\n\n"
            "Repeat FILE: blocks for multiple files. No markdown fences around the outer JSON.",
            "Only modify files listed in the task target_files; preserve style and existing patterns.",
            "Do not execute shell, install packages, or exfiltrate secrets; output source text only.",
        ],
        "output_schema": {
            "type": "object",
            "required": ["patch_document"],
            "properties": {"patch_document": {"type": "string"}},
        },
        "validation_rules": {
            "json_only": True,
            "require_envelope": False,
            "required_top_level_keys": ["patch_document"],
            "list_keys": [],
        },
        "structured_wire_reply_key": "patch_document",
    }
)
