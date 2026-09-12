import asyncio
import importlib.util
import os
import sys
from pathlib import Path
from types import SimpleNamespace

from project_guardian.ai_mutation_validator import (
    AIMutationValidator,
    ValidationCategory,
    ValidationSeverity,
)


def test_organized_project_is_not_prepended_to_sys_path():
    """
    organized_project contains legacy/generated placeholder packages. Appending it is acceptable for
    launcher.* imports; prepending can shadow stdlib/site packages with broken stubs.
    """
    repo_root = Path(__file__).resolve().parents[2]
    banned_call = "sys.path." + "insert(0"
    offenders = []
    ignored_parts = {
        ".git",
        ".pytest_cache",
        ".venv",
        "venv",
        "__pycache__",
        "organized_project",
        "agent-transcripts",
    }
    for root, dirs, files in os.walk(repo_root):
        dirs[:] = [d for d in dirs if d not in ignored_parts]
        root_path = Path(root)
        for filename in files:
            if not filename.endswith(".py"):
                continue
            path = root_path / filename
            rel = path.relative_to(repo_root)
            text = path.read_text(encoding="utf-8", errors="ignore")
            for lineno, line in enumerate(text.splitlines(), start=1):
                if banned_call in line and "organized_project" in line:
                    offenders.append(f"{rel}:{lineno}:{line.strip()}")
    assert offenders == []


def test_deprecated_ai_engine_placeholders_are_import_safe():
    repo_root = Path(__file__).resolve().parents[2]
    targets = {
        "consciousness_engine": repo_root
        / "organized_project"
        / "core_modules"
        / "ai_engines"
        / "consciousness_engine.py",
        "advanced_mutation_engine": repo_root
        / "organized_project"
        / "core_modules"
        / "ai_engines"
        / "advanced_mutation_engine.py",
    }
    for name, path in targets.items():
        spec = importlib.util.spec_from_file_location(f"legacy_{name}", path)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        assert getattr(module.default_instance, "status", None) == "deprecated_placeholder"


def test_ai_engine_folder_has_no_invalid_generated_placeholder_pattern():
    repo_root = Path(__file__).resolve().parents[2]
    ai_engines = repo_root / "organized_project" / "core_modules" / "ai_engines"
    offenders = []
    for path in ai_engines.glob("*.py"):
        text = path.read_text(encoding="utf-8", errors="ignore")
        if "class CoreModules." in text or "{module_name}" in text or "Placeholder Module" in text:
            offenders.append(path.name)
    assert offenders == []


def test_ai_mutation_validator_requires_manual_review_without_ask_ai():
    proposal = SimpleNamespace(
        mutation_id="mut-no-ai",
        target_module="project_guardian/example.py",
        mutation_type="code_modification",
        description="Exercise missing AskAI fallback",
        confidence=0.9,
        proposed_code="def changed():\n    return True\n",
    )
    validator = AIMutationValidator(ask_ai=None)

    result = asyncio.run(validator.validate_mutation(proposal))

    assert result.passed is False
    assert result.confidence == 0.0
    assert result.score == 0.0
    assert "manual review required" in result.summary
    assert result.issues
    assert result.issues[0].severity == ValidationSeverity.ERROR
    assert result.issues[0].category == ValidationCategory.COMPATIBILITY

    stats = validator.get_statistics()
    assert stats["total_validations"] == 1
    assert stats["passed"] == 0
    assert stats["failed"] == 1
    assert stats["pass_rate"] == 0.0


def test_income_generator_marks_pass_skeleton_as_draft(tmp_path):
    repo_root = Path(__file__).resolve().parents[2]
    organized_project = repo_root / "organized_project"
    sys.path.append(str(organized_project))
    try:
        from launcher.elysia_income_generator import ElysiaIncomeGenerator
    finally:
        try:
            sys.path.remove(str(organized_project))
        except ValueError:
            pass

    api_manager = SimpleNamespace(openai_client=object())
    multi_api_router = SimpleNamespace(available_apis=[])
    generator = ElysiaIncomeGenerator(
        api_manager=api_manager,
        multi_api_router=multi_api_router,
    )
    generator.project_root = tmp_path
    generator.income_tracking_file = tmp_path / "data" / "elysia_income_tracking.json"
    generator.revenue_projects_file = tmp_path / "data" / "elysia_revenue_projects.json"
    generator.income_data = {
        "total_earned": 0.0,
        "revenue_streams": [],
        "active_projects": [],
        "draft_projects": [],
        "completed_projects": [],
        "api_services": [],
        "content_products": [],
    }
    generator.revenue_projects = {
        "active_projects": [],
        "draft_projects": [],
        "completed_projects": [],
        "revenue_streams": [],
    }
    generator._ensure_project_buckets()

    result = generator.start_income_generation("api_wrapper_library")

    assert result["success"] is True
    assert result["status"] == "draft_skeleton"
    assert result["operational_ready"] is False
    assert result["stub_files"]
    assert generator.income_data["active_projects"] == []
    assert len(generator.income_data["draft_projects"]) == 1
    assert generator.revenue_projects["active_projects"] == []
    assert len(generator.revenue_projects["draft_projects"]) == 1

    summary = generator.get_income_summary()
    assert summary["active_projects"] == 0
    assert summary["draft_projects"] == 1
