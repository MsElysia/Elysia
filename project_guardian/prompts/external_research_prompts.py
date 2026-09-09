from .module_profiles_common import build_module_profiles, build_profile

PROMPT_PROFILES = build_module_profiles(
    "external_research",
    ["search_planning", "source_evaluation", "information_extraction", "synthesis"],
    reasoning_style="analytical",
    allowed_command_types=["NO_ACTION", "CALL_TOOL", "ASK_USER", "RUN_ANALYSIS"],
)

PROMPT_PROFILES["webscout_url_discovery"] = build_profile(
    prompt_id="external_research.webscout_url_discovery.v1",
    module_name="external_research",
    function_name="webscout_url_discovery",
    reasoning_style="analytical",
    allowed_command_types=["NO_ACTION", "CALL_TOOL", "ASK_USER", "RUN_ANALYSIS"],
)
PROMPT_PROFILES["webscout_url_discovery"].update(
    {
        "structured_output_kind": "plain_object_keys",
        "forbidden_outputs": [],
        "purpose": "Propose concrete https URLs to fetch for a research query (JSON only).",
        "behavioral_instructions": [
            "Return ONE JSON object with key urls (array of strings). Each string must be a full http(s) URL.",
            "Prefer authoritative docs, specifications, or reputable sources over generic homepages when possible.",
            "Do not include markdown fences or commentary outside JSON.",
        ],
        "output_schema": {
            "type": "object",
            "required": ["urls"],
            "properties": {"urls": {"type": "array", "items": {"type": "string"}}},
        },
        "validation_rules": {
            "json_only": True,
            "require_envelope": False,
            "required_top_level_keys": ["urls"],
            "list_keys": ["urls"],
        },
        "structured_wire_reply_key": "urls",
    }
)

PROMPT_PROFILES["webscout_source_summary"] = build_profile(
    prompt_id="external_research.webscout_source_summary.v1",
    module_name="external_research",
    function_name="webscout_source_summary",
    reasoning_style="analytical",
    allowed_command_types=["NO_ACTION", "CALL_TOOL", "ASK_USER", "RUN_ANALYSIS"],
)
PROMPT_PROFILES["webscout_source_summary"].update(
    {
        "structured_output_kind": "plain_object_keys",
        "forbidden_outputs": [],
        "purpose": "Summarize fetched research sources into a coherent markdown research summary.",
        "behavioral_instructions": [
            "Return ONE JSON object with key summary (string) containing markdown sections and citations to the given URLs.",
            "Be factual; attribute claims to sources. No JSON inside the summary string except if quoting.",
            "Outer response must be JSON only (no markdown fences around the JSON object).",
        ],
        "output_schema": {
            "type": "object",
            "required": ["summary"],
            "properties": {"summary": {"type": "string"}},
        },
        "validation_rules": {
            "json_only": True,
            "require_envelope": False,
            "required_top_level_keys": ["summary"],
            "list_keys": [],
        },
        "structured_wire_reply_key": "summary",
    }
)

PROMPT_PROFILES["webscout_llm_only_research"] = build_profile(
    prompt_id="external_research.webscout_llm_only_research.v1",
    module_name="external_research",
    function_name="webscout_llm_only_research",
    reasoning_style="analytical",
    allowed_command_types=["NO_ACTION", "CALL_TOOL", "ASK_USER", "RUN_ANALYSIS"],
)
PROMPT_PROFILES["webscout_llm_only_research"].update(
    {
        "structured_output_kind": "plain_object_keys",
        "forbidden_outputs": [],
        "purpose": (
            "When web fetch is unavailable, produce a structured research object with summary text "
            "and a sources array matching WebScout downstream parsing."
        ),
        "behavioral_instructions": [
            "Return ONE JSON object with keys: summary (string), sources (array of objects).",
            "Each source object: url, title, relevance (high|medium|low), extracted_patterns (string array), summary (string).",
            "Use plausible https URLs; do not claim live fetch occurred. JSON only, no markdown fences.",
        ],
        "output_schema": {
            "type": "object",
            "required": ["summary", "sources"],
            "properties": {
                "summary": {"type": "string"},
                "sources": {"type": "array"},
            },
        },
        "validation_rules": {
            "json_only": True,
            "require_envelope": False,
            "required_top_level_keys": ["summary", "sources"],
            "list_keys": ["sources"],
        },
    }
)
