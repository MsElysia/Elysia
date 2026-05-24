# project_guardian/tests/test_one_shot_ui_scripts_quarantined.py
"""One-shot UI repair scripts must stay quarantined (not runtime/CI/smoke)."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

ONE_SHOT_SCRIPT_NAMES = (
    "_restore_safe_stack_control_panel_ui.py",
    "_apply_control_panel_ui_clarity.py",
    "_apply_control_panel_secondary_clarity.py",
    "_patch_prompt_contract_ui.py",
)

ONE_SHOT_DIR = REPO_ROOT / "scripts" / "maintenance" / "one_shot"
LEGACY_SCRIPTS_DIR = REPO_ROOT / "scripts"

RUNTIME_SCAN_DIRS = (
    REPO_ROOT / "project_guardian",
    REPO_ROOT / "elysia",
)

WARNING_MARKERS = (
    "ONE-SHOT",
    "ONE_SHOT",
    "HISTORICAL REPAIR",
    "NOT RUNTIME",
)

REAL_UI_TEST_MODULES = (
    "project_guardian/tests/test_control_panel_ui_clarity.py",
    "project_guardian/tests/test_control_panel_brain_visibility.py",
    "project_guardian/tests/test_control_panel_js_smoke.py",
)


@pytest.fixture
def one_shot_scripts() -> list[Path]:
    paths = [ONE_SHOT_DIR / name for name in ONE_SHOT_SCRIPT_NAMES]
    missing = [p for p in paths if not p.is_file()]
    assert not missing, f"missing quarantined scripts: {missing}"
    return paths


def test_one_shot_scripts_live_under_maintenance_one_shot(one_shot_scripts):
    for path in one_shot_scripts:
        assert path.parent == ONE_SHOT_DIR
        assert "maintenance" in path.parts and "one_shot" in path.parts


def test_legacy_scripts_root_has_no_one_shot_ui_repair_scripts():
    for name in ONE_SHOT_SCRIPT_NAMES:
        assert not (LEGACY_SCRIPTS_DIR / name).is_file(), (
            f"{name} must not remain at scripts/ root; use scripts/maintenance/one_shot/"
        )


def test_one_shot_scripts_contain_clear_warning_text(one_shot_scripts):
    for path in one_shot_scripts:
        text = path.read_text(encoding="utf-8")
        assert any(marker in text for marker in WARNING_MARKERS), (
            f"{path.name} missing quarantine warning"
        )


def test_runtime_modules_do_not_reference_one_shot_scripts():
    pattern = re.compile(
        "|".join(re.escape(n) for n in ONE_SHOT_SCRIPT_NAMES)
        + r"|maintenance/one_shot|_restore_safe_stack_control_panel|_apply_control_panel_ui_clarity|_patch_prompt_contract_ui"
    )
    for root in RUNTIME_SCAN_DIRS:
        for py in root.rglob("*.py"):
            if "tests" in py.parts or "one_shot" in py.parts:
                continue
            content = py.read_text(encoding="utf-8", errors="replace")
            assert not pattern.search(content), f"runtime reference in {py.relative_to(REPO_ROOT)}"


def test_smoke_script_does_not_invoke_one_shot_repair_scripts():
    smoke = (REPO_ROOT / "scripts" / "run_safe_stack_smoke_tests.py").read_text(encoding="utf-8")
    for name in ONE_SHOT_SCRIPT_NAMES:
        assert name not in smoke
    assert "maintenance/one_shot" not in smoke
    assert "_restore_safe_stack" not in smoke
    assert "_apply_control_panel" not in smoke
    assert "_patch_prompt_contract" not in smoke


def test_ci_workflow_does_not_invoke_one_shot_repair_scripts():
    workflow = REPO_ROOT / ".github" / "workflows" / "safe-stack-smoke.yml"
    text = workflow.read_text(encoding="utf-8")
    for name in ONE_SHOT_SCRIPT_NAMES:
        assert name not in text
    assert "maintenance/one_shot" not in text


def test_smoke_includes_real_ui_marker_tests_not_repair_scripts():
    smoke = (REPO_ROOT / "scripts" / "run_safe_stack_smoke_tests.py").read_text(encoding="utf-8")
    assert "test_one_shot_ui_scripts_quarantined.py" in smoke
    for mod in REAL_UI_TEST_MODULES:
        assert mod in smoke, f"smoke must include {mod}"
    assert "test_one_shot_ui_scripts_quarantined.py" not in (
        m for m in REAL_UI_TEST_MODULES
    )


def test_final_checkpoint_documents_one_shot_quarantine():
    doc = (REPO_ROOT / "docs" / "ELYSIA_SAFE_STACK_FINAL_CHECKPOINT.md").read_text(
        encoding="utf-8"
    )
    assert "scripts/maintenance/one_shot" in doc
    assert "quarantined" in doc.lower() or "one-shot" in doc.lower()
    arch = (REPO_ROOT / "docs" / "ELYSIA_ARCHITECTURE_CHECKPOINT.md").read_text(
        encoding="utf-8"
    )
    assert "maintenance/one_shot" in arch or "one-shot" in arch.lower()


def test_one_shot_readme_exists():
    readme = ONE_SHOT_DIR / "README.md"
    assert readme.is_file()
    text = readme.read_text(encoding="utf-8")
    assert "Not runtime" in text or "not runtime" in text.lower()
    assert "ui_control_panel.py" in text
