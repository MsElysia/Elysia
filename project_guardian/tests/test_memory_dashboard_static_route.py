# project_guardian/tests/test_memory_dashboard_static_route.py

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

from project_guardian.local_ingestion import memory_dashboard_route_contract as contract

REPO_ROOT = Path(__file__).resolve().parents[2]
APP_PATH = REPO_ROOT / "project_guardian" / "ui" / "app.py"
AUTONOMY_PATH = REPO_ROOT / "config" / "autonomy.json"

ALLOWLIST = contract.ALLOWED_STATIC_MEMORY_PAGES

UNKNOWN_FILENAMES = (
    "unknown.html",
    "dashboard.html",
    "elysia.py",
)

TRAVERSAL_NAMES = (
    "../config/autonomy.json",
    "memory/../../secret.txt",
)

BACKSLASH_TRAVERSAL_NAMES = (
    "..\\config\\autonomy.json",
)

ENCODED_TRAVERSAL_URLS = (
    "/memory/%2e%2e/config/autonomy.json",
    "/memory/%2e%2e%2fconfig%2fautonomy.json",
)

DOUBLE_ENCODED_TRAVERSAL_URLS = (
    "/memory/%252e%252e/config/autonomy.json",
)

ABSOLUTE_PATH_URLS = (
    "/memory/C:/Users/example/secret.txt",
    "/memory//etc/passwd",
)

NESTED_PATH_URLS = (
    "/memory/project_guardian/ui/static/memory_hub.html",
)


@pytest.fixture
def client():
    try:
        from fastapi.testclient import TestClient
        from project_guardian.ui import app as ui_app
    except Exception as exc:
        pytest.skip(f"FastAPI dashboard unavailable: {exc}")

    if not getattr(ui_app, "FASTAPI_AVAILABLE", False):
        pytest.skip(f"FastAPI dashboard unavailable: {ui_app.FASTAPI_IMPORT_ERROR}")

    return TestClient(ui_app.app, client=("127.0.0.1", 50000))


def _hub_markers() -> tuple[str, ...]:
    return ("Elysia Memory", "Memory Hub")


def test_memory_root_serves_hub(client):
    response = client.get("/memory")
    assert response.status_code == 200
    assert "text/html" in response.headers.get("content-type", "")
    for marker in _hub_markers():
        assert marker in response.text


def test_memory_trailing_slash_serves_hub(client):
    response = client.get("/memory/")
    assert response.status_code == 200
    for marker in _hub_markers():
        assert marker in response.text


def test_memory_hub_html_serves_hub(client):
    response = client.get("/memory/memory_hub.html")
    assert response.status_code == 200
    for marker in _hub_markers():
        assert marker in response.text


def _memory_route_source_block() -> str:
    source = APP_PATH.read_text(encoding="utf-8")
    start = source.find("def _serve_static_memory_page")
    end = source.find("async def status_dashboard")
    assert start != -1 and end != -1
    return source[start:end]


@pytest.mark.parametrize("page", ALLOWLIST)
def test_allowlisted_pages_served(client, page):
    response = client.get(f"/memory/{page}")
    assert response.status_code == 200
    assert "text/html" in response.headers.get("content-type", "")
    body = response.text.replace("\r\n", "\n")
    expected = (
        REPO_ROOT / "project_guardian" / "ui" / "static" / page
    ).read_text(encoding="utf-8").replace("\r\n", "\n")
    assert body.strip() == expected.strip()


@pytest.mark.parametrize("name", UNKNOWN_FILENAMES)
def test_unknown_filenames_rejected(client, name):
    response = client.get(f"/memory/{name}")
    assert response.status_code == 404


@pytest.mark.parametrize("name", TRAVERSAL_NAMES)
def test_dotdot_traversal_rejected(client, name):
    response = client.get(f"/memory/{name}")
    assert response.status_code in {404, 400}


@pytest.mark.parametrize("name", BACKSLASH_TRAVERSAL_NAMES)
def test_backslash_traversal_rejected(client, name):
    response = client.get(f"/memory/{name}")
    assert response.status_code in {404, 400}


@pytest.mark.parametrize("url", ENCODED_TRAVERSAL_URLS)
def test_encoded_traversal_rejected(client, url):
    response = client.get(url)
    assert response.status_code in {404, 400}


@pytest.mark.parametrize("url", DOUBLE_ENCODED_TRAVERSAL_URLS)
def test_double_encoded_traversal_rejected(client, url):
    response = client.get(url)
    assert response.status_code in {404, 400}


@pytest.mark.parametrize("url", ABSOLUTE_PATH_URLS)
def test_absolute_paths_rejected(client, url):
    response = client.get(url)
    assert response.status_code in {404, 400}


@pytest.mark.parametrize("url", NESTED_PATH_URLS)
def test_nested_non_allowlisted_paths_rejected(client, url):
    response = client.get(url)
    assert response.status_code == 404


def test_route_does_not_serve_autonomy_config(client):
    response = client.get("/memory/../config/autonomy.json")
    assert response.status_code in {404, 400}


def test_app_route_code_uses_contract_allowlist():
    source = APP_PATH.read_text(encoding="utf-8")
    assert "memory_dashboard_route_contract" in source
    assert "resolve_static_memory_page" in source


def test_app_route_code_does_not_import_core_or_api_server_in_memory_route_block():
    block = _memory_route_source_block()
    assert "project_guardian.core" not in block
    assert "elysia.api.server" not in block


def test_app_memory_route_handlers_do_not_execute_commands():
    block = _memory_route_source_block().lower()
    forbidden = ("subprocess", "popen", "os.system", "memory_import.py", "memory_doctor.py")
    for token in forbidden:
        assert token not in block


def test_app_memory_route_handlers_do_not_write_files():
    block = _memory_route_source_block().lower()
    forbidden = ("write_text", "write_bytes", ".mkdir(", "unlink(", "remove(")
    for token in forbidden:
        assert token not in block


def test_route_module_imports_only_expected_local_ingestion_helper():
    tree = ast.parse(APP_PATH.read_text(encoding="utf-8"))
    imports = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            imports.append(node.module)
    assert "project_guardian.local_ingestion.memory_dashboard_route_contract" in imports


def test_autonomy_config_remains_disabled():
    payload = json.loads(AUTONOMY_PATH.read_text(encoding="utf-8"))
    assert payload.get("enabled") is False


def test_contract_allowlist_matches_static_route_expectations():
    assert set(ALLOWLIST) == {
        "index.html",
        "memory_hub.html",
        "memory_import_screen.html",
        "memory_review_search.html",
        "memory_first_run_setup.html",
        "memory_safety.html",
        "memory_diagnostics.html",
    }
