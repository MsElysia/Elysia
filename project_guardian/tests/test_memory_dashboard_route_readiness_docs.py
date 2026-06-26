# project_guardian/tests/test_memory_dashboard_route_readiness_docs.py

from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
READINESS_PATH = REPO_ROOT / "docs" / "MEMORY_DASHBOARD_ROUTE_READINESS_REVIEW.md"
GATES_PATH = REPO_ROOT / "docs" / "MEMORY_DASHBOARD_ROUTE_IMPLEMENTATION_GATES.md"

STATIC_MEMORY_PAGES = (
    "index.html",
    "memory_hub.html",
    "memory_import_screen.html",
    "memory_review_search.html",
    "memory_first_run_setup.html",
    "memory_safety.html",
    "memory_diagnostics.html",
)

GO_NO_GO_VALUES = (
    "GO_WITH_HUMAN_APPROVAL",
    "NO_GO_NEEDS_MORE_DESIGN",
    "NO_GO_RISKY_FILE_TOUCH_REQUIRED",
    "NO_GO_UNCLEAR_DASHBOARD_STRUCTURE",
)


def _read(path: Path) -> str:
    assert path.is_file(), f"Missing doc: {path}"
    return path.read_text(encoding="utf-8")


def _lower(path: Path) -> str:
    return _read(path).lower()


def test_readiness_review_doc_exists():
    assert READINESS_PATH.is_file()


def test_implementation_gates_doc_exists():
    assert GATES_PATH.is_file()


@pytest.mark.parametrize("page", STATIC_MEMORY_PAGES)
def test_readiness_review_lists_static_memory_pages(page):
    assert page in _read(READINESS_PATH)


def test_readiness_review_references_route_contract():
    text = _read(READINESS_PATH)
    assert "memory_dashboard_route_contract.py" in text
    assert "test_memory_dashboard_route_contract.py" in text


def test_readiness_review_includes_dashboard_ui_discovery():
    text = _read(READINESS_PATH)
    for item in (
        "project_guardian/ui/templates/",
        "project_guardian/ui/static/",
        "project_guardian/ui/app.py",
        "project_guardian/ui_control_panel.py",
        "Elysia_Control_Panel_Standalone.html",
        "elysia/api/server.py",
    ):
        assert item in text
    assert "Dashboard/UI discovery" in text


def test_readiness_review_states_no_route_implemented():
    text = _lower(READINESS_PATH)
    assert "no route is currently implemented" in text or "did not add a route" in text


def test_readiness_review_states_no_server_api_route_added():
    text = _lower(READINESS_PATH)
    assert "no server/api route was added" in text


def test_readiness_review_includes_go_no_go_decision():
    text = _read(READINESS_PATH)
    assert any(value in text for value in GO_NO_GO_VALUES)


def test_readiness_review_requires_human_approval_before_implementation():
    text = _lower(READINESS_PATH)
    assert "human approval" in text
    assert "must not begin" in text or "before route implementation" in text


def test_readiness_review_mentions_autonomy_disabled():
    text = _lower(READINESS_PATH)
    assert "autonomy" in text
    assert "enabled=false" in text or "disabled" in text


def test_readiness_review_mentions_no_model_api_account_network_access():
    text = _lower(READINESS_PATH)
    for word in ("model", "api", "account", "network"):
        assert word in text
    assert "no account/api/network/model/embedding calls" in text


def test_readiness_review_mentions_no_live_memory_vector_writes():
    text = _lower(READINESS_PATH)
    assert "live runtime memory" in text
    assert "vector db" in text
    assert "no live runtime memory or vector db writes" in text


def test_implementation_gates_require_design_risk_contract_readiness_prerequisites():
    text = _read(GATES_PATH)
    for item in (
        "MEMORY_DASHBOARD_ROUTE_DESIGN.md",
        "MEMORY_DASHBOARD_ROUTE_RISK_REVIEW.md",
        "memory_dashboard_route_contract.py",
        "MEMORY_DASHBOARD_ROUTE_READINESS_REVIEW.md",
        "GO_WITH_HUMAN_APPROVAL",
    ):
        assert item in text


def test_implementation_gates_require_human_approval():
    text = _lower(GATES_PATH)
    assert "human explicitly approves" in text or "explicit approval" in text


def test_implementation_gates_require_allowlisted_static_pages_only():
    text = _lower(GATES_PATH)
    assert "serve only allowlisted static memory pages" in text


def test_implementation_gates_require_traversal_rejection():
    text = _lower(GATES_PATH)
    assert "reject traversal" in text
    assert "backslash traversal" in text


def test_implementation_gates_require_encoded_traversal_rejection():
    text = _lower(GATES_PATH)
    assert "encoded traversal" in text
    assert "double-encoded traversal" in text


def test_implementation_gates_require_no_backend_command_execution():
    text = _lower(GATES_PATH)
    assert "avoid backend command execution" in text or "no backend command execution" in text


def test_implementation_gates_require_no_file_writes():
    text = _lower(GATES_PATH)
    assert "avoid file writes" in text or "no file writes" in text


def test_implementation_gates_require_safe_stack_and_dry_run_safe():
    text = _read(GATES_PATH)
    assert "run_safe_stack_smoke_tests.py" in text
    assert "run_elysia_dry_run_report.py --mode real-planning" in text
    assert "SAFE" in text


def test_implementation_gates_include_stop_rules():
    text = _lower(GATES_PATH)
    assert "stop immediately" in text
    assert "broad server refactor" in text
    assert "project_guardian/core.py" in text


def test_docs_do_not_instruct_immediate_route_implementation():
    combined = _lower(READINESS_PATH) + _lower(GATES_PATH)
    forbidden = (
        "implement the route now",
        "add the route now",
        "wire the route now",
        "start route implementation now",
    )
    for phrase in forbidden:
        assert phrase not in combined
    assert "does not authorize route implementation" in combined or "not an implementation prompt" in combined


def test_docs_do_not_instruct_modifying_server_py_in_this_campaign():
    combined = _lower(READINESS_PATH) + _lower(GATES_PATH)
    assert "elysia/api/server.py" in combined
    assert "must remain untouched" in combined or "would be touched without separate explicit approval" in combined


def test_docs_do_not_instruct_modifying_core_py():
    combined = _lower(READINESS_PATH) + _lower(GATES_PATH)
    assert "project_guardian/core.py" in combined
    assert "must remain untouched" in combined or "would be touched" in combined
