"""operator_insights: overview bundle shape."""

from project_guardian.operator_insights import (
    build_insights_overview,
    build_mcp_bundle,
    build_mission_clarity_bundle,
    build_ollama_runtime_bundle,
    build_parallel_brains_matrix,
    build_selfbuild_bundle,
    build_storage_alignment_bundle,
)


def test_build_insights_overview_keys():
    d = build_insights_overview(trace_lines=5, rag_lines=5)
    assert "generated_at" in d
    assert "storage_alignment" in d
    assert "ollama_runtime" in d
    assert "parallel_brains" in d
    assert "mission_clarity" in d
    assert "selfbuild" in d
    assert "mcp" in d
    assert "llm_traces" in d
    assert "rag_unified_log" in d
    assert isinstance(d["hints"], list)


def test_mission_clarity_bundle():
    m = build_mission_clarity_bundle()
    assert "focus_missions" in m
    assert isinstance(m["focus_missions"], list)
    assert len(m["focus_missions"]) <= 5
    assert "merged_guidance_keywords_sample" in m
    assert "corpus_keyword_alignment" in m


def test_parallel_brains_matrix_bundle():
    m = build_parallel_brains_matrix()
    assert "unified_chat_llm_router_enabled" in m
    assert "unified_route_scenarios" in m
    assert isinstance(m["unified_route_scenarios"], list)


def test_storage_alignment_has_keys():
    s = build_storage_alignment_bundle()
    assert "config_exists" in s
    assert "warnings" in s


def test_selfbuild_bundle_structure():
    sb = build_selfbuild_bundle()
    assert "learned_root" in sb or "error" in sb
    if "error" not in sb:
        assert "rag_inject_effective" in sb
        assert "embed_ram_pressure" in sb
        ri = sb["rag_inject_effective"]
        assert set(["top_k", "max_chars", "min_score"]).issubset(ri.keys())


def test_mcp_bundle_structure():
    m = build_mcp_bundle()
    assert "mcp_sdk_installed" in m
    assert "allowlist_exists" in m


def test_ollama_runtime_bundle_structure():
    o = build_ollama_runtime_bundle()
    assert "effective_model" in o
    assert "readiness_label" in o
    assert "startup" in o
    assert isinstance(o["startup"], dict)
