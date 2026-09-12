"""Static checks for Memory dashboard route design, risk review, and acceptance tests."""

from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
DESIGN_PATH = REPO_ROOT / "docs" / "MEMORY_DASHBOARD_ROUTE_DESIGN.md"
RISK_PATH = REPO_ROOT / "docs" / "MEMORY_DASHBOARD_ROUTE_RISK_REVIEW.md"
ACCEPTANCE_PATH = REPO_ROOT / "docs" / "MEMORY_DASHBOARD_ROUTE_ACCEPTANCE_TESTS.md"

STATIC_MEMORY_PAGES = (
    "index.html",
    "memory_hub.html",
    "memory_import_screen.html",
    "memory_review_search.html",
    "memory_first_run_setup.html",
    "memory_safety.html",
    "memory_diagnostics.html",
)

DIAGNOSTICS_TOOLS = (
    "scripts/memory_doctor.py",
    "scripts/create_memory_demo_workspace.py",
    "scripts/run_memory_health_smoke.py",
)

FORBIDDEN_IMPLEMENTATION_PHRASES = (
    "implement the route now",
    "wire the route now",
    "add the route in this step",
    "modify elysia/api/server.py in this step",
    "change elysia/api/server.py now",
)


def _read(path: Path) -> str:
    assert path.is_file(), f"Missing doc: {path}"
    return path.read_text(encoding="utf-8")


def _lower(path: Path) -> str:
    return _read(path).lower()


def test_design_doc_exists():
    assert DESIGN_PATH.is_file()


def test_risk_review_doc_exists():
    assert RISK_PATH.is_file()


def test_acceptance_tests_doc_exists():
    assert ACCEPTANCE_PATH.is_file()


@pytest.mark.parametrize("page", STATIC_MEMORY_PAGES)
def test_design_doc_lists_static_memory_pages(page):
    text = _read(DESIGN_PATH)
    assert page in text
    assert f"project_guardian/ui/static/{page}" in text or page in text


@pytest.mark.parametrize("tool", DIAGNOSTICS_TOOLS)
def test_design_doc_lists_diagnostics_demo_tooling(tool):
    assert tool in _read(DESIGN_PATH)


def test_design_doc_includes_allowlist():
    text = _lower(DESIGN_PATH)
    assert "allowlist" in text
    for page in STATIC_MEMORY_PAGES:
        assert page in text


def test_design_doc_says_no_arbitrary_path_serving():
    text = _lower(DESIGN_PATH)
    assert "arbitrary" in text or "allowlisted" in text
    assert "never expose" in text or "no other" in text or "unknown" in text


def test_design_doc_says_no_command_execution():
    text = _lower(DESIGN_PATH)
    assert "no command execution" in text or "never execute" in text or "subprocess" in text


def test_design_doc_says_no_diagnostics_demo_execution_from_browser():
    text = _lower(DESIGN_PATH)
    assert "memory_doctor.py" in text
    assert "create_memory_demo_workspace.py" in text
    assert "browser" in text or "from the browser" in text


def test_risk_review_mentions_path_traversal():
    text = _lower(RISK_PATH)
    assert "path traversal" in text
    assert "%2e%2e" in text or ".." in text


def test_risk_review_mentions_arbitrary_file_serving():
    text = _lower(RISK_PATH)
    assert "arbitrary file serving" in text or "arbitrary file" in text


def test_risk_review_mentions_no_backend_calls():
    text = _lower(RISK_PATH)
    assert "backend call" in text or "unexpected backend calls" in text
    assert "fetch" in text or "xhr" in text or "websocket" in text


def test_risk_review_mentions_no_account_api_model_embedding_calls():
    text = _lower(RISK_PATH)
    assert "account" in text or "api" in text
    assert "model" in text or "embedding" in text


def test_risk_review_mentions_no_live_memory_vector_writes():
    text = _lower(RISK_PATH)
    assert "live memory" in text or "vector" in text
    assert "write" in text


def test_risk_review_mentions_no_diagnostics_demo_execution_from_browser():
    text = _lower(RISK_PATH)
    assert "memory_doctor.py" in text or "diagnostics" in text
    assert "browser" in text or "demo workspace" in text


def test_acceptance_tests_include_traversal_rejection():
    text = _lower(ACCEPTANCE_PATH)
    assert "path traversal" in text or "traversal rejection" in text
    assert ".." in text


def test_acceptance_tests_include_encoded_traversal_rejection():
    text = _lower(ACCEPTANCE_PATH)
    assert "%2e%2e" in text
    assert "encoded traversal" in text


def test_acceptance_tests_include_allowlist_behavior():
    text = _lower(ACCEPTANCE_PATH)
    assert "allowlist" in text
    assert "unknown" in text or "404" in text


def test_acceptance_tests_include_no_file_writes():
    text = _lower(ACCEPTANCE_PATH)
    assert "does not write files" in text or "no file writes" in text or "not write files" in text


def test_acceptance_tests_include_no_diagnostics_demo_execution_from_browser():
    text = _lower(ACCEPTANCE_PATH)
    assert "memory_doctor.py" in text or "diagnostics" in text
    assert "demo workspace" in text or "create_memory_demo_workspace" in text


def test_acceptance_tests_include_autonomy_disabled():
    text = _lower(ACCEPTANCE_PATH)
    assert "autonomy" in text
    assert '"enabled": false' in text or "enabled\": false" in text or "disabled" in text


def test_docs_do_not_instruct_route_implementation_yet():
    combined = _lower(DESIGN_PATH) + _lower(RISK_PATH) + _lower(ACCEPTANCE_PATH)
    assert "does not authorize route implementation" in combined or "no route is implemented" in combined
    assert "design-only" in combined or "future route" in combined or "future implementation" in combined
    for phrase in FORBIDDEN_IMPLEMENTATION_PHRASES:
        assert phrase not in combined


def test_docs_do_not_instruct_modifying_server_py_in_this_step():
    combined = _lower(DESIGN_PATH) + _lower(RISK_PATH) + _lower(ACCEPTANCE_PATH)
    assert "do not modify `elysia/api/server.py`" in combined or "does not authorize modifying `elysia/api/server.py`" in combined
    assert "in this step" in combined or "design step" in combined or "design-only milestone" in combined
