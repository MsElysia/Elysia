# project_guardian/tests/test_api_host_route_parity.py
"""Parity tests for safe-stack routes on RuntimeAPIServer vs UIControlPanel (no live servers/LLMs)."""

from __future__ import annotations

import inspect
import json
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Set, Tuple
from unittest.mock import Mock

import pytest

from elysia.api.server import RuntimeAPIServer
from elysia.events import EventBus
from project_guardian.brain.config import BrainPipelineConfig
from project_guardian.conversation_store import ConversationStore, DEFAULT_CONVERSATIONS_DIR
from project_guardian.self_improvement.proposal_queue import (
    ProposalQueue,
    append_proposal,
    create_proposal,
)

# Safe-stack path fragments (Flask/Werkzeug rules use angle-bracket params).
SAFE_STACK_ROUTE_SPECS: Tuple[Tuple[str, Set[str]], ...] = (
    ("/api/chat/history", {"GET", "DELETE"}),
    ("/api/conversations", {"GET", "POST"}),
    ("/api/conversations/<conversation_id>", {"GET", "DELETE"}),
    ("/api/brain/trace/latest", {"GET"}),
    ("/api/memory/ranking/summary", {"GET"}),
    ("/api/prompt-contracts/status", {"GET"}),
    ("/api/governance/operator-confirmations", {"GET"}),
    ("/api/governance/operator-confirmations/<operator_confirmation_id>", {"GET"}),
    ("/api/self-improvement/proposals", {"GET"}),
    ("/api/self-improvement/proposals/<proposal_id>", {"GET"}),
    ("/api/self-improvement/proposals/<proposal_id>/status", {"POST"}),
    ("/api/self-improvement/proposals/<proposal_id>/export_prompt", {"GET"}),
)

FORBIDDEN_SAFE_ROUTE_FRAGMENTS = (
    "/implement",
    "/api/proposals",
)

FORBIDDEN_HANDLER_TOKENS = (
    "apply_patch",
    "run_command",
    "subprocess",
    "run_autonomous_cycle",
    "operator_chat_live_execution",
    "implementer.run_for_proposal",
)

EXPORT_REQUIRED_KEYS = frozenset(
    {"success", "proposal_id", "target", "prompt", "copy_safe", "warnings"}
)

PROPOSAL_API_KEYS = frozenset(
    {
        "proposal_id",
        "title",
        "problem_summary",
        "proposed_change",
        "status",
        "risk_level",
        "priority_score",
        "affected_files",
    }
)

BRAIN_TRACE_TOP_KEYS = frozenset(
    {
        "available",
        "enabled",
        "dry_run",
        "trace_path",
        "trace_exists",
        "warnings",
    }
)

MEMORY_RANKING_TOP_KEYS = frozenset(
    {
        "available",
        "enabled",
        "dry_run",
        "mutation_allowed",
        "delete_allowed",
        "proposal_counts",
    }
)

PROMPT_CONTRACT_TOP_KEYS = frozenset(
    {
        "available",
        "enabled",
        "mode",
        "contract_count",
        "contracts",
        "latest_validation",
    }
)

RAW_TRACE_FORBIDDEN_IN_JSON = (
    '"think_decide_act_trace"',
    '"tda_trace"',
    '"raw_trace"',
    '"unified_export":',
)


def _imports():
    try:
        from project_guardian.ui_control_panel import UIControlPanel
    except ImportError:
        pytest.skip("UIControlPanel not available")
    return UIControlPanel


def _sample_proposal(**overrides):
    base = dict(
        source="brain_pipeline",
        source_trace_id="trace-parity",
        title="Parity test proposal",
        problem_summary="Verify API host parity.",
        proposed_change="Add shared route helpers.",
        affected_files=["project_guardian/tests/test_api_host_route_parity.py"],
        expected_benefit="Less handler drift.",
        risk_level="low",
        priority_score=0.5,
    )
    base.update(overrides)
    return create_proposal(**base)


def _brain_cfg(trace_path: Path, **kwargs) -> BrainPipelineConfig:
    ep = {
        "operator_chat": kwargs.pop("operator_chat", False),
        "operator_chat_live_execution": False,
        "tool_execution": False,
        "autonomy": False,
        "diagnostic": False,
    }
    return BrainPipelineConfig(
        enabled=kwargs.get("enabled", False),
        use_think_decide_act=True,
        dry_run=True,
        persist_trace=True,
        trace_path=trace_path,
        entrypoints=ep,
    )


def _route_index(app) -> List[Tuple[str, Set[str], str]]:
    rows: List[Tuple[str, Set[str], str]] = []
    for rule in app.url_map.iter_rules():
        methods = set(rule.methods or set()) - {"HEAD", "OPTIONS"}
        rows.append((rule.rule, methods, rule.endpoint))
    return rows


def _has_safe_route(app, path_fragment: str, methods: Set[str]) -> bool:
    """Methods may be split across multiple Flask rules for the same path."""
    matched: Set[str] = set()
    for rule, rule_methods, _ in _route_index(app):
        if path_fragment not in rule:
            continue
        matched |= rule_methods
    return methods <= matched


def _safe_stack_endpoints(app) -> List[Tuple[str, str]]:
    out: List[Tuple[str, str]] = []
    for rule, methods, endpoint in _route_index(app):
        if not any(frag in rule for frag, _ in SAFE_STACK_ROUTE_SPECS):
            continue
        if any(bad in rule for bad in FORBIDDEN_SAFE_ROUTE_FRAGMENTS):
            continue
        if methods & {"GET", "POST", "DELETE"}:
            out.append((rule, endpoint))
    return out


@pytest.fixture
def host_clients(tmp_path, monkeypatch):
    """Runtime + control panel Flask test clients sharing temp store paths."""
    conv_dir = tmp_path / "conversations"
    proposal_path = tmp_path / "proposals.jsonl"
    trace_path = tmp_path / "brain_trace.json"

    trace_path.write_text(
        json.dumps(
            {
                "brain_pipeline_id": "brain-parity",
                "started_at": "2026-05-16T12:00:00+00:00",
                "input_source": "operator_chat",
                "risk": "low",
                "execution_ok": True,
                "think_decide_act_trace_present": True,
                "transitions": ["observation_received"],
                "dry_run": True,
                "unified_export": {"think_decide_act_trace": {"secret": "hidden"}},
                "context_preview": "safe preview",
            }
        ),
        encoding="utf-8",
    )

    cfg = _brain_cfg(trace_path)
    monkeypatch.setattr(
        "project_guardian.brain.config.get_brain_pipeline_config",
        lambda **_k: cfg,
    )

    from project_guardian.self_improvement import proposal_queue as pq

    monkeypatch.setattr(pq, "DEFAULT_PROPOSALS_PATH", proposal_path)
    monkeypatch.setattr(pq, "_default_queue", None)

    store = ConversationStore(conv_dir)
    queue = ProposalQueue(proposal_path)
    proposal = _sample_proposal()
    append_proposal(proposal, path=proposal_path)

    runtime = RuntimeAPIServer(
        status_provider=lambda: {"running": True},
        event_bus=EventBus(),
        conversation_store=store,
        self_improvement_queue=queue,
        architect=None,
        proposal_system=None,
        implementer=None,
    )
    runtime._app.config["TESTING"] = True
    runtime_client = runtime._app.test_client()

    UIControlPanel = _imports()
    orch = Mock()
    orch.conversation_store_dir = str(conv_dir)
    panel = UIControlPanel(orchestrator=orch, host="127.0.0.1", port=0)
    panel.app.config["TESTING"] = True
    panel_client = panel.app.test_client()

    return {
        "runtime_client": runtime_client,
        "panel_client": panel_client,
        "store": store,
        "conv_dir": conv_dir,
        "proposal_path": proposal_path,
        "trace_path": trace_path,
        "proposal_id": proposal.proposal_id,
        "runtime_server": runtime,
        "panel_instance": panel,
    }


def test_safe_stack_route_registration_parity(host_clients):
    runtime_app = host_clients["runtime_server"]._app
    panel_app = host_clients["panel_instance"].app
    for path_fragment, methods in SAFE_STACK_ROUTE_SPECS:
        assert _has_safe_route(runtime_app, path_fragment, methods), (
            f"RuntimeAPIServer missing {methods} {path_fragment}"
        )
        assert _has_safe_route(panel_app, path_fragment, methods), (
            f"UIControlPanel missing {methods} {path_fragment}"
        )


def test_brain_trace_response_shape_parity(host_clients):
    for label, client in (
        ("runtime", host_clients["runtime_client"]),
        ("panel", host_clients["panel_client"]),
    ):
        r = client.get("/api/brain/trace/latest")
        assert r.status_code == 200, label
        body = r.get_json()
        assert BRAIN_TRACE_TOP_KEYS <= set(body.keys()), label
        blob = json.dumps(body).lower()
        for forbidden in RAW_TRACE_FORBIDDEN_IN_JSON:
            assert forbidden not in blob, f"{label} leaked raw trace key"
        if body.get("trace_exists"):
            assert body.get("brain_pipeline_id") or (body.get("trace") or {}).get("brain_pipeline_id")


def test_memory_ranking_response_shape_parity(host_clients):
    for label, client in (
        ("runtime", host_clients["runtime_client"]),
        ("panel", host_clients["panel_client"]),
    ):
        r = client.get("/api/memory/ranking/summary?limit=5")
        assert r.status_code == 200, label
        body = r.get_json()
        assert MEMORY_RANKING_TOP_KEYS <= set(body.keys()), label
        assert body["mutation_allowed"] is False
        assert body["delete_allowed"] is False
        assert isinstance(body["proposal_counts"], dict)


def test_prompt_contract_status_shape_parity(host_clients):
    for label, client in (
        ("runtime", host_clients["runtime_client"]),
        ("panel", host_clients["panel_client"]),
    ):
        r = client.get("/api/prompt-contracts/status")
        assert r.status_code == 200, label
        body = r.get_json()
        assert PROMPT_CONTRACT_TOP_KEYS <= set(body.keys()), label
        assert isinstance(body["contracts"], list)
        assert isinstance(body["latest_validation"], dict)


def test_self_improvement_list_detail_status_shape_parity(host_clients):
    pid = host_clients["proposal_id"]
    runtime = host_clients["runtime_client"]
    panel = host_clients["panel_client"]

    for client in (runtime, panel):
        lst = client.get("/api/self-improvement/proposals?limit=10")
        assert lst.status_code == 200
        data = lst.get_json()
        assert data.get("success") is True
        assert isinstance(data.get("proposals"), list)
        assert data["proposals"]
        row = data["proposals"][0]
        assert PROPOSAL_API_KEYS <= set(row.keys())

    for client in (runtime, panel):
        one = client.get(f"/api/self-improvement/proposals/{pid}")
        assert one.status_code == 200
        body = one.get_json()
        assert body.get("success") is True
        prop = body.get("proposal") or {}
        assert PROPOSAL_API_KEYS <= set(prop.keys())
        assert "think_decide_act_trace" not in json.dumps(prop).lower()

    for client in (runtime, panel):
        st = client.post(
            f"/api/self-improvement/proposals/{pid}/status",
            json={"status": "reviewing", "note": "parity test"},
        )
        assert st.status_code == 200
        body = st.get_json()
        assert body.get("success") is True
        assert body.get("status") == "reviewing"


def test_prompt_export_shape_parity(host_clients):
    """Both hosts return the normalized export envelope (including success: true)."""
    pid = host_clients["proposal_id"]
    runtime_body = host_clients["runtime_client"].get(
        f"/api/self-improvement/proposals/{pid}/export_prompt?target=cursor"
    ).get_json()
    panel_body = host_clients["panel_client"].get(
        f"/api/self-improvement/proposals/{pid}/export_prompt?target=cursor"
    ).get_json()

    assert EXPORT_REQUIRED_KEYS <= set(runtime_body.keys())
    assert EXPORT_REQUIRED_KEYS <= set(panel_body.keys())
    assert runtime_body.get("success") is True
    assert panel_body.get("success") is True
    for key in EXPORT_REQUIRED_KEYS:
        assert runtime_body[key] == panel_body[key], f"export field drift: {key}"


def test_conversation_storage_path_parity(host_clients):
    store = host_clients["store"]
    conv_dir = host_clients["conv_dir"]
    panel_store = host_clients["panel_instance"]._conversation_store

    assert Path(panel_store.base_dir).resolve() == conv_dir.resolve()
    assert Path(store.base_dir).resolve() == conv_dir.resolve()

    store.append_message("parity-conv", role="user", content="hello from shared store")
    panel_hist = host_clients["panel_client"].get("/api/conversations/parity-conv").get_json()
    runtime_hist = host_clients["runtime_client"].get("/api/conversations/parity-conv").get_json()
    assert panel_hist.get("success") is True
    assert runtime_hist.get("success") is True
    panel_msgs = panel_hist.get("messages") or []
    runtime_msgs = runtime_hist.get("messages") or []
    assert any("hello from shared store" in str(m.get("content", "")) for m in panel_msgs)
    assert any("hello from shared store" in str(m.get("content", "")) for m in runtime_msgs)


def test_default_conversation_store_path_matches_canonical():
    UIControlPanel = _imports()
    orch = Mock(spec=[])  # no conversation_store_dir override
    panel = UIControlPanel(orchestrator=orch, host="127.0.0.1", port=0)
    assert Path(panel._conversation_store.base_dir).resolve() == DEFAULT_CONVERSATIONS_DIR.resolve()


def test_negative_safe_stack_routes_exclude_implement_and_change_proposals(host_clients):
    panel_app = host_clients["panel_instance"].app
    runtime_app = host_clients["runtime_server"]._app

    for app in (panel_app, runtime_app):
        for rule, _methods, _ep in _route_index(app):
            if not any(frag in rule for frag, _ in SAFE_STACK_ROUTE_SPECS):
                continue
            for bad in FORBIDDEN_SAFE_ROUTE_FRAGMENTS:
                assert bad not in rule, f"safe-stack rule must not include {bad}: {rule}"

    panel_rules = {r for r, _, _ in _route_index(panel_app)}
    assert not any("/api/proposals" in r for r in panel_rules)

    for app_label, app in (("runtime", runtime_app), ("panel", panel_app)):
        for rule, endpoint in _safe_stack_endpoints(app):
            fn = app.view_functions[endpoint]
            src = inspect.getsource(fn).lower()
            for token in FORBIDDEN_HANDLER_TOKENS:
                assert token not in src, f"{app_label} handler for {rule} mentions {token}"


def test_chat_brain_hook_both_hosts_when_config_enabled(tmp_path, monkeypatch, host_clients):
    """Both hosts invoke operator_chat brain trace when config enables it (fail-open bypass in test)."""
    calls: List[str] = []

    def _fake_brain_run(*_a, **_k):
        calls.append("brain")
        return {"bypass": True, "reason": "test"}

    monkeypatch.setattr(
        "project_guardian.brain.runtime.run_brain_pipeline_for_operator_event",
        _fake_brain_run,
    )
    cfg = _brain_cfg(host_clients["trace_path"], enabled=True, operator_chat=True)
    monkeypatch.setattr(
        "project_guardian.brain.config.get_brain_pipeline_config",
        lambda **_k: cfg,
    )

    runtime = host_clients["runtime_client"]
    r = runtime.post("/api/chat", json={"message": "parity brain hook"})
    assert r.status_code == 200

    panel = host_clients["panel_client"]
    orch = host_clients["panel_instance"].orchestrator
    orch._unified_system = None
    orch.ask_ai = lambda _msg: "ok"

    pr = panel.post("/api/chat", json={"message": "panel chat"})
    assert pr.status_code == 200
    assert len(calls) == 2
