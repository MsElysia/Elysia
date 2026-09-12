"""Tests for context pipeline telemetry-driven tuning heuristics."""
from project_guardian.context_pipeline.telemetry_tuning import recommend_context_pipeline_patch


def test_insufficient_cycles_no_patch():
    cp = {
        "counters": {"cycles": 3, "fallback_used": 2, "error_timeout": 2},
        "fallback_rate": 0.5,
        "timeout_rate": 0.5,
        "last_packet_status": {},
    }
    cfg = {"local_timeout_sec": 60}
    notes, patch = recommend_context_pipeline_patch(cp, cfg, min_cycles=8)
    assert patch == {}
    assert any("Not enough" in n for n in notes)


def test_high_timeout_rate_proposes_local_bump():
    cp = {
        "counters": {
            "cycles": 20,
            "fallback_used": 10,
            "error_timeout": 8,
            "error_ollama_unavailable": 0,
            "error_invalid_packet": 0,
            "error_other": 2,
            "error_none": 0,
        },
        "fallback_rate": 0.5,
        "timeout_rate": 0.4,
        "last_packet_status": {"ok": True, "fallback_used": False, "error_reason": "none"},
    }
    cfg = {"local_timeout_sec": 60, "online_timeout_sec": 75, "embedding_http_timeout_sec": 30}
    notes, patch = recommend_context_pipeline_patch(cp, cfg, min_cycles=8)
    assert patch.get("local_timeout_sec") == 95
    assert "online_timeout_sec" in patch


def test_healthy_high_cycle_no_patch():
    cp = {
        "counters": {"cycles": 40, "error_timeout": 0, "fallback_used": 1},
        "fallback_rate": 0.025,
        "timeout_rate": 0.0,
        "last_packet_status": {},
    }
    cfg = {"local_timeout_sec": 60}
    _, patch = recommend_context_pipeline_patch(cp, cfg, min_cycles=8)
    assert patch == {}
