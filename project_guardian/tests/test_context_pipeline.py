# project_guardian/tests/test_context_pipeline.py

from __future__ import annotations

from unittest.mock import patch

from project_guardian.context_pipeline.ingestion_normalizer import make_record, normalize_user_input
from project_guardian.context_pipeline.relevance_engine import build_relevance_map, extract_contradictions, tfidf_cosine
from project_guardian.context_pipeline.retrieval import balanced_retrieve
from project_guardian.context_pipeline.runner import (
    _load_pipeline_cfg,
    format_planner_injection_fallback,
    run_context_pipeline_for_decider,
    should_run_online_reasoning,
)
from project_guardian.context_pipeline.structured_response_validator import classify_structured_online_response, validate_structured_online_response


def test_tfidf_cosine_semantic_overlap():
    a = "optimize agent retrieval latency for production workloads"
    b = "production retrieval latency tradeoffs for agents"
    assert tfidf_cosine(a, b) > 0.25


def test_relevance_map_orders_user_higher():
    recs = [
        make_record(source_type="memory", raw_text="misc note about cats", session_id="s1", initial_importance=0.4),
        make_record(source_type="user_input", raw_text="We must improve autonomy decision quality", session_id="s1"),
    ]
    cfg = {"recency_half_life_hours": 48.0, "source_priority_weights": {}, "keyword_rules": [], "semantic_backend": "tfidf"}
    rm, meta = build_relevance_map(recs, "improve autonomy decisions", cfg=cfg)
    uid = recs[1]["id"]
    mid = recs[0]["id"]
    assert rm[uid]["score"] >= rm[mid]["score"]
    assert meta.get("semantic_backend") == "tfidf"


@patch("project_guardian.context_pipeline.relevance_engine.embed_texts")
def test_embeddings_backend_selected_when_configured(mock_embed):
    def _fake(texts, cfg=None):
        vecs = [[1.0, 0.0, 0.0] for _ in texts]
        return "embeddings_ollama", vecs

    mock_embed.side_effect = _fake
    recs = [
        make_record(source_type="memory", raw_text="optimize retrieval latency production", session_id="s1"),
    ]
    cfg = {
        "recency_half_life_hours": 48.0,
        "source_priority_weights": {},
        "keyword_rules": [],
        "semantic_backend": "embeddings",
        "embedding_model": "nomic-embed-text",
    }
    rm, meta = build_relevance_map(recs, "production retrieval latency", cfg=cfg)
    assert recs[0]["id"] in rm
    mock_embed.assert_called()
    assert "embedding" in str(meta.get("semantic_backend", "")).lower() or meta.get("semantic_backend") == "embeddings_ollama"


@patch("project_guardian.context_pipeline.relevance_engine.embed_texts")
def test_tfidf_fallback_skips_embedding(mock_embed):
    recs = [
        make_record(source_type="memory", raw_text="cats and dogs", session_id="s1"),
    ]
    cfg = {"recency_half_life_hours": 48.0, "source_priority_weights": {}, "keyword_rules": [], "semantic_backend": "tfidf"}
    rm, meta = build_relevance_map(recs, "birds", cfg=cfg)
    assert rm
    mock_embed.assert_not_called()
    assert meta.get("semantic_backend") == "tfidf"


def test_source_balancing_caps_dominant_source():
    recs = []
    base_ts = 1_700_000_000.0
    for i in range(14):
        recs.append(
            make_record(
                source_type="chat_history",
                raw_text=f"chat export line {i} discussion autonomy goals milestones " * 3,
                session_id="s1",
                timestamp=base_ts + i,
                record_id=f"ch_{i}",
            )
        )
    for i in range(4):
        recs.append(
            make_record(
                source_type="user_input",
                raw_text=f"user directive {i} must improve autonomy decision pipeline",
                session_id="s1",
                timestamp=base_ts + 100 + i,
                record_id=f"u_{i}",
            )
        )
    rel_map = {str(r["id"]): {"total_score": 0.88, "score": 0.88} for r in recs}
    caps = {"chat_history": 3, "user_input": 5}
    bundle = balanced_retrieve(recs, rel_map, [], cfg={"source_retrieval_caps": caps, "max_total_retrieved_items": 18})
    assert bundle.source_mix.get("chat_history", 0) <= 3
    assert bundle.source_mix.get("user_input", 0) >= 1


def test_contradiction_objects_for_conflicting_records():
    ra = make_record(
        source_type="memory",
        raw_text="We must not deploy the broken agent loop; no this is incorrect and cannot proceed safely",
        session_id="s1",
        record_id="a1",
    )
    rb = make_record(
        source_type="memory",
        raw_text="We should definitely deploy the agent loop now; never disagree with rollout",
        session_id="s1",
        record_id="b1",
    )
    rel_map = {"a1": {"total_score": 0.75}, "b1": {"total_score": 0.74}}
    out = extract_contradictions([ra, rb], rel_map, min_score=0.4)
    assert isinstance(out, list)
    assert len(out) >= 1
    assert out[0].record_ids[0] in ("a1", "b1")


def test_unsupported_online_claims_block_decision_safe_merge():
    packet = {
        "facts": [],
        "evidence": [{"record_id": "x1", "snippet": "hello world"}],
    }
    norm = {
        "decision": "This is always definitely proven to be the only correct capability execute_capability.",
        "reasoning": "Short.",
        "confidence": 0.95,
        "missing_info": [],
        "next_steps": [],
        "risks": [],
    }
    vr = classify_structured_online_response(packet, norm, min_confidence_for_safe=0.35)
    assert vr.decision_safe is False
    assert vr.safe_guidance_dict() == {}


def test_archive_decay_multiplier_bounds():
    from project_guardian.context_pipeline.archive_manager import relevance_decay_multiplier

    m = relevance_decay_multiplier("nonexistent_id_xyz", {"archive_decay_enabled": True})
    assert 0.3 < m <= 1.1


def test_merged_context_pipeline_prefers_top_level_packet():
    from project_guardian.mistral_engine import _merged_context_pipeline_view

    st = {
        "context_pipeline": {"enabled": True, "context_pipeline_packet": None},
        "context_pipeline_packet": {"objective": "o", "task_type": "t"},
    }
    v = _merged_context_pipeline_view(st)
    assert v.get("context_pipeline_packet", {}).get("objective") == "o"


def test_parse_decide_response_pipeline_trace():
    from project_guardian.mistral_engine import MistralEngine

    eng = MistralEngine.__new__(MistralEngine)
    candidates = [{"action": "execute_task", "source": "x", "reason": "r", "priority_score": 1}]
    raw = {
        "chosen_action": "execute_task",
        "reasoning": "ok",
        "confidence": 0.6,
        "needs_memory": False,
        "ask_user_question": "",
        "exploration_score": 0.5,
        "fallback_action": "",
        "pre_recon_summary": "",
        "capability_route": "internal_module",
    }
    state = {
        "context_pipeline": {
            "context_pipeline_packet": {"objective": "x"},
            "context_pipeline_online": {"decision": "x", "next_steps": [], "missing_info": [], "risks": []},
            "context_pipeline_validation": {"decision_safe": True, "risk_safe": True},
        }
    }
    out = MistralEngine._parse_decide_response(eng, raw, candidates, state)
    tr = out.get("_pipeline_trace") or {}
    assert tr.get("used_context_pipeline_packet") is True
    assert tr.get("used_structured_online_support") is True
    assert "decision_basis_summary" in tr
    assert out.get("used_context_pipeline_packet") is True
    assert out.get("decision_basis_summary")


@patch("project_guardian.context_pipeline.relevance_engine.embed_texts")
def test_embeddings_fallback_meta_when_ollama_returns_none(mock_embed):
    mock_embed.return_value = ("none", [None])
    recs = [make_record(source_type="memory", raw_text="goal autonomy pipeline safety", session_id="s1")]
    cfg = {"semantic_backend": "embeddings", "keyword_rules": [], "source_priority_weights": {}}
    _rm, meta = build_relevance_map(recs, "autonomy goal safety", cfg=cfg)
    assert meta.get("semantic_backend") == "embeddings_fallback_tfidf"


def test_archive_hygiene_duplicate_cluster():
    import json
    from pathlib import Path
    from tempfile import TemporaryDirectory
    from unittest.mock import patch

    from project_guardian.context_pipeline.archive_manager import analyze_archive_hygiene

    with TemporaryDirectory() as td:
        p = Path(td) / "context_archive.jsonl"
        body = "same canonical text for duplicate detection " * 2
        lines = []
        for i in range(4):
            lines.append(
                json.dumps(
                    {
                        "ts": 1.0 + i,
                        "session_id": "s",
                        "topic": "goals",
                        "relevance": 0.9,
                        "archive_meta": {},
                        "record": {"id": f"id{i}", "raw_text": body},
                    }
                )
            )
        p.write_text("\n".join(lines) + "\n", encoding="utf-8")
        with patch("project_guardian.context_pipeline.archive_manager.archive_path", return_value=p):
            hy = analyze_archive_hygiene(max_lines=50)
        assert hy.get("duplicate_clustered", 0) >= 1


def test_validate_structured_online_response():
    ok, norm, issues = validate_structured_online_response(
        {
            "decision": "proceed",
            "reasoning": "Because evidence supports it.",
            "confidence": 0.7,
            "missing_info": [],
            "next_steps": ["a"],
            "risks": [],
        }
    )
    assert ok
    assert norm["decision"] == "proceed"
    assert not issues


def test_load_pipeline_cfg_merges_decider():
    merged = _load_pipeline_cfg({"use_context_pipeline": True})
    assert merged.get("enabled") is True


def test_run_context_pipeline_builds_fallback_packet_when_local_fails():
    class _Mem:
        def recall_last(self, _n):
            return [{"content": "Memory says prioritize reliable execution under pressure."}]

    class _G:
        _pending_operator_question = "Pick the best next autonomy action."
        _pre_decision_context = {"task_context": "Autonomy cycle"}
        _last_monitor_snapshot = {"memory_pressure": "high"}
        _last_planner_snapshot = {"mode": "autonomy"}
        memory = _Mem()

    with patch("project_guardian.context_pipeline.runner._load_pipeline_cfg", return_value={"enabled": True}):
        with patch("project_guardian.context_pipeline.runner.build_local_prompt_packet", return_value=(None, "timeout")):
            out = run_context_pipeline_for_decider(_G(), active_goal="Stay productive", session_id="s1")

    pkt = out.get("context_pipeline_packet") or {}
    status = (out.get("context_pipeline_summary") or {}).get("prompt_packet_status") or {}
    assert pkt.get("objective")
    assert isinstance(pkt.get("facts"), list)
    assert status.get("fallback_used") is True
    assert status.get("error_reason") == "timeout"


def test_run_context_pipeline_skips_local_packet_under_memory_pressure():
    class _Mem:
        def recall_last(self, _n):
            return [{"content": "Memory says prioritize reliable execution under pressure."}]

    class _G:
        _pending_operator_question = "Pick the best next autonomy action."
        _pre_decision_context = {"task_context": "Autonomy cycle"}
        _last_monitor_snapshot = {"memory_pressure": "high"}
        _last_planner_snapshot = {"mode": "autonomy"}
        memory = _Mem()

    with patch("project_guardian.context_pipeline.runner._load_pipeline_cfg", return_value={"enabled": True}):
        with patch("project_guardian.context_pipeline.runner.build_local_prompt_packet") as local_mock:
            out = run_context_pipeline_for_decider(
                _G(),
                active_goal="Stay productive",
                session_id="s1",
                pipeline_signals={"memory_pressure_high": True},
            )

    local_mock.assert_not_called()
    status = (out.get("context_pipeline_summary") or {}).get("prompt_packet_status") or {}
    assert status.get("fallback_used") is True
    assert status.get("error_reason") == "memory_pressure_skip"


def test_format_planner_injection_truncates():
    s = format_planner_injection_fallback(
        {"task_type": "t", "retrieval": {}, "validation": {}},
        max_chars=900,
    )
    assert "CONTEXT_PIPELINE_LEGACY_FALLBACK" in s


def test_normalize_user_input_logs_shape():
    rows = normalize_user_input("hello operator", "sess")
    assert len(rows) == 1
    assert rows[0]["source_type"] == "user_input"


def test_should_run_online_low_confidence():
    cfg = {"online_reasoning_enabled": True, "online_reasoning_confidence_threshold": 0.9}
    on, reason = should_run_online_reasoning(
        cfg,
        contradictions=[],
        source_mix={},
        pipeline_signals={},
        packet_ok=True,
        local_confidence=0.2,
    )
    assert on is True
    assert "confidence" in reason


def test_should_run_online_skips_when_disabled():
    cfg = {"online_reasoning_enabled": False, "run_online_reasoning": False}
    on, reason = should_run_online_reasoning(
        cfg,
        contradictions=[1, 2],
        source_mix={"a": 1, "b": 1, "c": 1, "d": 1, "e": 1},
        pipeline_signals={"uncertainty_level": "high"},
        packet_ok=True,
        local_confidence=0.1,
    )
    assert on is False


def test_should_run_online_skips_under_memory_pressure_when_configured():
    cfg = {
        "online_reasoning_enabled": True,
        "online_skip_when_memory_pressure": True,
        "online_reasoning_confidence_threshold": 0.62,
    }
    on, reason = should_run_online_reasoning(
        cfg,
        contradictions=[],
        source_mix={},
        pipeline_signals={"memory_pressure_high": True},
        packet_ok=True,
        local_confidence=0.2,
    )
    assert on is False
    assert reason == "memory_pressure_remote_unlikely"


def test_should_run_online_maximize_free_reserves_without_strong_signal():
    cfg = {
        "online_reasoning_enabled": True,
        "maximize_free_tokens": True,
        "online_reasoning_confidence_threshold": 0.62,
        "online_reasoning_confidence_ceiling_skip": 0.92,
    }
    on, reason = should_run_online_reasoning(
        cfg,
        contradictions=[],
        source_mix={"a": 1},
        pipeline_signals={"task_type": "autonomy_decide_next", "uncertainty_level": "low"},
        packet_ok=True,
        local_confidence=0.85,
    )
    assert on is False
    assert reason == "maximize_free_reserve_paid_no_strong_signal"


def test_should_run_online_autonomy_decide_next_not_forced_without_allowlist():
    cfg = {
        "online_reasoning_enabled": True,
        "online_reasoning_confidence_threshold": 0.62,
        "online_reasoning_confidence_ceiling_skip": 0.92,
        "default_task_type": "autonomy_decide_next",
    }
    on, reason = should_run_online_reasoning(
        cfg,
        contradictions=[],
        source_mix={"x": 2},
        pipeline_signals={"task_type": "autonomy_decide_next"},
        packet_ok=True,
        local_confidence=0.75,
    )
    assert on is False
    assert reason == "gates_not_met"
