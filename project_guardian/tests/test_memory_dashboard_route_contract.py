# project_guardian/tests/test_memory_dashboard_route_contract.py

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from project_guardian.local_ingestion import memory_dashboard_route_contract as contract

REPO_ROOT = Path(__file__).resolve().parents[2]
CONTRACT_PATH = (
    REPO_ROOT / "project_guardian" / "local_ingestion" / "memory_dashboard_route_contract.py"
)
DESIGN_PATH = REPO_ROOT / "docs" / "MEMORY_DASHBOARD_ROUTE_DESIGN.md"
ACCEPTANCE_PATH = REPO_ROOT / "docs" / "MEMORY_DASHBOARD_ROUTE_ACCEPTANCE_TESTS.md"

APPROVED_PAGES = (
    "index.html",
    "memory_hub.html",
    "memory_import_screen.html",
    "memory_review_search.html",
    "memory_first_run_setup.html",
    "memory_safety.html",
    "memory_diagnostics.html",
)

UNKNOWN_FILENAMES = (
    "dashboard.html",
    "elysia.py",
    "config.json",
    "anything.exe",
    "memory_unknown.html",
)

TRAVERSAL_NAMES = (
    "../config/autonomy.json",
    "memory/../../secret.txt",
)

BACKSLASH_TRAVERSAL_NAMES = (
    "..\\config\\autonomy.json",
)

ENCODED_TRAVERSAL_NAMES = (
    "%2e%2e/config/autonomy.json",
)

DOUBLE_ENCODED_TRAVERSAL_NAMES = (
    "%252e%252e/config/autonomy.json",
)

NULL_BYTE_STYLE_NAMES = (
    "memory_hub.html%00.txt",
)

WINDOWS_ABSOLUTE_PATHS = (
    "C:\\Users\\example\\secret.txt",
)

POSIX_ABSOLUTE_PATHS = (
    "/etc/passwd",
)

DRIVE_ROOT_STYLE_PATHS = (
    "F:\\ElysiaMemory\\secret.txt",
)

DIRECTORY_ONLY_PATHS = (
    ".",
    "..",
    "/",
    "project_guardian/ui/static/",
)


def _contract_source() -> str:
    return CONTRACT_PATH.read_text(encoding="utf-8")


def _contract_ast() -> ast.Module:
    return ast.parse(_contract_source())


def test_allowlist_contains_exactly_approved_memory_static_files():
    assert contract.ALLOWED_STATIC_MEMORY_PAGES == APPROVED_PAGES


@pytest.mark.parametrize("page", APPROVED_PAGES)
def test_all_allowlisted_files_exist_in_static_directory(page):
    assert (contract.static_memory_directory() / page).is_file()


@pytest.mark.parametrize("page", APPROVED_PAGES)
def test_known_allowed_files_validate_as_safe(page):
    assert contract.is_safe_static_memory_page_name(page) is True


@pytest.mark.parametrize("name", UNKNOWN_FILENAMES)
def test_unknown_files_validate_as_unsafe(name):
    assert contract.is_safe_static_memory_page_name(name) is False
    assert contract.resolve_static_memory_page(name) is None


@pytest.mark.parametrize("name", TRAVERSAL_NAMES)
def test_dotdot_traversal_validates_as_unsafe(name):
    assert contract.is_safe_static_memory_page_name(name) is False
    assert contract.resolve_static_memory_page(name) is None


@pytest.mark.parametrize("name", BACKSLASH_TRAVERSAL_NAMES)
def test_backslash_traversal_validates_as_unsafe(name):
    assert contract.is_safe_static_memory_page_name(name) is False
    assert contract.resolve_static_memory_page(name) is None


@pytest.mark.parametrize("name", ENCODED_TRAVERSAL_NAMES)
def test_encoded_traversal_validates_as_unsafe(name):
    assert contract.is_safe_static_memory_page_name(name) is False
    assert contract.resolve_static_memory_page(name) is None


@pytest.mark.parametrize("name", DOUBLE_ENCODED_TRAVERSAL_NAMES)
def test_double_encoded_traversal_validates_as_unsafe(name):
    assert contract.is_safe_static_memory_page_name(name) is False
    assert contract.resolve_static_memory_page(name) is None


@pytest.mark.parametrize("name", NULL_BYTE_STYLE_NAMES)
def test_null_byte_style_payload_validates_as_unsafe(name):
    assert contract.is_safe_static_memory_page_name(name) is False
    assert contract.resolve_static_memory_page(name) is None


@pytest.mark.parametrize("name", WINDOWS_ABSOLUTE_PATHS)
def test_absolute_windows_paths_validate_as_unsafe(name):
    assert contract.is_safe_static_memory_page_name(name) is False
    assert contract.resolve_static_memory_page(name) is None


@pytest.mark.parametrize("name", POSIX_ABSOLUTE_PATHS)
def test_absolute_posix_paths_validate_as_unsafe(name):
    assert contract.is_safe_static_memory_page_name(name) is False
    assert contract.resolve_static_memory_page(name) is None


@pytest.mark.parametrize("name", DRIVE_ROOT_STYLE_PATHS)
def test_drive_root_style_paths_validate_as_unsafe(name):
    assert contract.is_safe_static_memory_page_name(name) is False
    assert contract.resolve_static_memory_page(name) is None


@pytest.mark.parametrize("name", DIRECTORY_ONLY_PATHS)
def test_directory_only_paths_validate_as_unsafe(name):
    assert contract.is_safe_static_memory_page_name(name) is False
    assert contract.resolve_static_memory_page(name) is None


@pytest.mark.parametrize("page", APPROVED_PAGES)
def test_safe_resolver_never_returns_path_outside_static_directory(page):
    resolved = contract.resolve_static_memory_page(page)
    assert resolved is not None
    resolved.relative_to(contract.static_memory_directory().resolve())


def test_safe_resolver_only_resolves_allowlisted_files():
    for page in APPROVED_PAGES:
        assert contract.resolve_static_memory_page(page) is not None
    for name in UNKNOWN_FILENAMES + TRAVERSAL_NAMES + POSIX_ABSOLUTE_PATHS:
        assert contract.resolve_static_memory_page(name) is None


def test_contract_module_does_not_import_flask():
    assert "flask" not in _contract_source().lower()


def test_contract_module_does_not_import_fastapi():
    assert "fastapi" not in _contract_source().lower()


def test_contract_module_does_not_import_elysia_api_server():
    assert "elysia.api.server" not in _contract_source()


def test_contract_module_does_not_import_project_guardian_core():
    assert "project_guardian.core" not in _contract_source()


def test_contract_module_does_not_expose_command_execution():
    source = _contract_source().lower()
    forbidden = ("subprocess", "popen", "system(", "exec(", "spawn", "shell")
    for token in forbidden:
        assert token not in source
    assert contract.COMMAND_EXECUTION_ENABLED is False
    assert contract.BACKEND_MEMORY_COMMANDS_ENABLED is False
    assert contract.DIAGNOSTICS_DEMO_BROWSER_EXECUTION_ENABLED is False


def test_contract_module_does_not_expose_file_writing_functions():
    source = _contract_source().lower()
    forbidden = ("write_text", "write_bytes", "open(", "mkdir", "unlink", "remove", "rmdir")
    for token in forbidden:
        assert token not in source
    assert contract.FILE_WRITES_ENABLED is False


def test_contract_module_imports_only_safe_standard_library_modules():
    imports = []
    for node in ast.walk(_contract_ast()):
        if isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imports.append(node.module or "")
    assert set(imports) <= {"__future__", "pathlib", "typing", "urllib.parse"}


def test_contract_safety_flags_remain_false():
    assert contract.SAFETY_FLAGS == {
        "model_called": False,
        "embeddings_used": False,
        "live_memory_written": False,
        "autonomy_enabled": False,
    }
    assert contract.ACCOUNT_API_NETWORK_ACCESS_ENABLED is False
    assert contract.LIVE_MEMORY_VECTOR_WRITES_ENABLED is False


def test_design_docs_reference_route_contract_test_harness():
    text = DESIGN_PATH.read_text(encoding="utf-8")
    assert "MEMORY_DASHBOARD_ROUTE_TEST_HARNESS.md" in text
    assert "test_memory_dashboard_route_contract.py" in text
    assert "memory_dashboard_route_contract.py" in text


def test_future_route_acceptance_docs_mention_contract_tests():
    text = ACCEPTANCE_PATH.read_text(encoding="utf-8")
    assert "test_memory_dashboard_route_contract.py" in text
    assert "memory_dashboard_route_contract.py" in text
