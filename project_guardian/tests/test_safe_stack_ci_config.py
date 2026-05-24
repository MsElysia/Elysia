# project_guardian/tests/test_safe_stack_ci_config.py
"""Static checks for safe-stack CI workflow and developer docs (no network)."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_PATH = ROOT / ".github" / "workflows" / "safe-stack-smoke.yml"
SMOKE_SCRIPT = ROOT / "scripts" / "run_safe_stack_smoke_tests.py"
CHECKPOINT_DOC = ROOT / "docs" / "ELYSIA_ARCHITECTURE_CHECKPOINT.md"
README = ROOT / "README.md"
MAKEFILE = ROOT / "Makefile"


@pytest.fixture(scope="module")
def workflow_text() -> str:
    if not WORKFLOW_PATH.is_file():
        pytest.skip("GitHub Actions workflow not present")
    return WORKFLOW_PATH.read_text(encoding="utf-8")


def test_workflow_file_exists():
    assert WORKFLOW_PATH.is_file(), f"missing {WORKFLOW_PATH.relative_to(ROOT)}"


def test_workflow_invokes_smoke_script(workflow_text: str):
    assert "scripts/run_safe_stack_smoke_tests.py" in workflow_text
    assert "python scripts/run_safe_stack_smoke_tests.py" in workflow_text


def test_workflow_does_not_use_secrets(workflow_text: str):
    lowered = workflow_text.lower()
    assert "secrets." not in lowered
    assert "${{ secrets" not in lowered
    for token in ("openai_api_key", "anthropic_api_key", "api_key:", "password:"):
        assert token not in lowered


def test_workflow_does_not_run_autonomy_or_live_execution(workflow_text: str):
    for forbidden in (
        "run_autonomous_cycle",
        "operator_chat_live_execution",
        "/api/proposals/",
        "implement",
        "docker compose up",
        "services:",
    ):
        assert forbidden not in workflow_text


def test_workflow_does_not_start_servers(workflow_text: str):
    lowered = workflow_text.lower()
    assert "run_elysia" not in lowered
    assert "flask run" not in lowered
    assert "uvicorn" not in lowered


def test_smoke_script_path_exists():
    assert SMOKE_SCRIPT.is_file()


def test_checkpoint_documents_smoke_command():
    assert CHECKPOINT_DOC.is_file()
    text = CHECKPOINT_DOC.read_text(encoding="utf-8")
    assert "scripts/run_safe_stack_smoke_tests.py" in text
    assert "Safe stack smoke" in text


def test_checkpoint_documents_ci_workflow():
    text = CHECKPOINT_DOC.read_text(encoding="utf-8")
    assert "safe-stack-smoke.yml" in text or "Safe stack smoke" in text


def test_local_make_target_or_readme_mentions_smoke():
    if MAKEFILE.is_file():
        assert "safe-smoke" in MAKEFILE.read_text(encoding="utf-8")
        assert "run_safe_stack_smoke_tests.py" in MAKEFILE.read_text(encoding="utf-8")
        return
    if README.is_file():
        readme = README.read_text(encoding="utf-8")
        assert "run_safe_stack_smoke_tests.py" in readme
        return
    pytest.skip("No Makefile or README for local command documentation")


def test_readme_mentions_safe_smoke_when_present():
    if not README.is_file():
        pytest.skip("README not present")
    assert re.search(r"run_safe_stack_smoke_tests|safe-smoke", README.read_text(encoding="utf-8"))
