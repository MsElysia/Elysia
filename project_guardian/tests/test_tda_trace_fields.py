# project_guardian/tests/test_tda_trace_fields.py
"""Canonical Think–Decide–Act trace field naming and API sanitization."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from project_guardian.brain.contracts import BrainPipelineTrace
from project_guardian.brain.pipeline import BrainPipeline
from project_guardian.brain.memory_module import InMemoryBrainStore
from project_guardian.brain.tda_trace_fields import (
    ALIAS_TDA_TRACE_KEY,
    CANONICAL_TDA_TRACE_KEY,
    apply_persisted_tda_fields,
    get_think_decide_act_trace,
    has_think_decide_act_trace,
)
from project_guardian.brain.trace_visibility import load_latest_brain_trace_summary, summarize_trace


def test_brain_trace_tda_property_alias():
    trace = BrainPipelineTrace()
    payload = {"dry_run": True, "stage_logs": ["observe"]}
    trace.tda_trace = payload
    assert trace.think_decide_act_trace == payload
    assert trace.tda_trace is trace.think_decide_act_trace


def test_get_think_decide_act_trace_prefers_canonical_key():
    canonical = {"x": 1}
    assert get_think_decide_act_trace({CANONICAL_TDA_TRACE_KEY: canonical}) is canonical
    assert get_think_decide_act_trace({ALIAS_TDA_TRACE_KEY: {"y": 2}}) == {"y": 2}
    assert get_think_decide_act_trace({CANONICAL_TDA_TRACE_KEY: canonical, ALIAS_TDA_TRACE_KEY: {"y": 2}}) is canonical


def test_apply_persisted_tda_fields_writes_alias_matching_canonical():
    trace = BrainPipelineTrace()
    trace.think_decide_act_trace = {"k": "v"}
    payload: dict = {}
    apply_persisted_tda_fields(payload, trace)
    assert payload[CANONICAL_TDA_TRACE_KEY] == {"k": "v"}
    assert payload[ALIAS_TDA_TRACE_KEY] is payload[CANONICAL_TDA_TRACE_KEY]
    assert payload["think_decide_act_trace_present"] is True


def test_persisted_trace_file_has_canonical_and_alias(tmp_path, monkeypatch):
    import project_guardian.brain.pipeline as brain_pipeline_module

    monkeypatch.setattr(brain_pipeline_module, "_TRACE_PATH", tmp_path / "brain.json")

    class StaticLLM:
        def choose_backend(self, **kwargs):
            return "fake", "ok"

    class NoopSI:
        def enqueue(self, *a, **k):
            pass

    import project_guardian.orchestration.think_decide_act as tda

    real = tda.run_think_decide_act_pipeline
    monkeypatch.setattr(tda, "run_think_decide_act_pipeline", lambda *a, **k: real(*a, **k))

    pipe = BrainPipeline(
        guardian=None,
        memory=InMemoryBrainStore(),
        llm_router=StaticLLM(),
        self_improvement=NoopSI(),
    )
    from project_guardian.brain.contracts import Observation

    trace, _ = pipe.run(
        Observation("user", "safe noop"),
        context={"use_think_decide_act": True, "dry_run": True, "persist_trace": True},
    )
    assert trace.think_decide_act_trace is not None
    raw = json.loads((tmp_path / "brain.json").read_text(encoding="utf-8"))
    assert raw[CANONICAL_TDA_TRACE_KEY] == raw[ALIAS_TDA_TRACE_KEY]
    assert has_think_decide_act_trace(raw)


def test_trace_visibility_summary_has_tda_used_not_raw_trace(tmp_path):
    trace_path = tmp_path / "t.json"
    raw = {
        "brain_pipeline_id": "b1",
        "think_decide_act_trace_present": True,
        CANONICAL_TDA_TRACE_KEY: {"nested": "secret"},
        ALIAS_TDA_TRACE_KEY: {"nested": "secret"},
        "transitions": ["think_decide_act_finished"],
    }
    trace_path.write_text(json.dumps(raw), encoding="utf-8")
    summary = summarize_trace(json.loads(trace_path.read_text(encoding="utf-8")))
    assert summary["tda_used"] is True
    assert CANONICAL_TDA_TRACE_KEY not in summary
    assert ALIAS_TDA_TRACE_KEY not in summary

    from project_guardian.brain.config import BrainPipelineConfig

    ep = {
        "operator_chat": False,
        "operator_chat_live_execution": False,
        "tool_execution": False,
        "autonomy": False,
        "diagnostic": False,
    }
    out = load_latest_brain_trace_summary(
        config=BrainPipelineConfig(
            enabled=False,
            use_think_decide_act=True,
            dry_run=True,
            persist_trace=True,
            trace_path=trace_path,
            entrypoints=ep,
        )
    )
    text = json.dumps(out)
    assert "nested" not in text
    assert out.get("tda_used") is True
