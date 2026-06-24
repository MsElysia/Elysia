# project_guardian/tests/test_memory_hub_navigation.py

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
STATIC_DIR = REPO_ROOT / "project_guardian" / "ui" / "static"
NAV_ENTRY = STATIC_DIR / "index.html"
HUB_PATH = STATIC_DIR / "memory_hub.html"
IMPORT_PATH = STATIC_DIR / "memory_import_screen.html"
REVIEW_PATH = STATIC_DIR / "memory_review_search.html"
CORE_PATH = REPO_ROOT / "project_guardian" / "core.py"
SERVER_PATH = REPO_ROOT / "elysia" / "api" / "server.py"

REQUIRED_MEMORY_LANGUAGE = (
    "Memory",
    "Import, review, and search local memories",
    "Uses local files only",
    "No account connection required",
)

FORBIDDEN_NETWORK_JS = ("fetch(", "XMLHttpRequest", "WebSocket")

EXTERNAL_ASSET_PATTERN = re.compile(
    r'(?:src|href|action)\s*=\s*["\']https?://',
    re.IGNORECASE,
)


@pytest.fixture
def nav_html() -> str:
    assert NAV_ENTRY.is_file(), f"Missing navigation entry: {NAV_ENTRY}"
    return NAV_ENTRY.read_text(encoding="utf-8")


@pytest.fixture
def hub_html() -> str:
    assert HUB_PATH.is_file()
    return HUB_PATH.read_text(encoding="utf-8")


def test_navigation_entry_exists():
    assert NAV_ENTRY.is_file()


def test_navigation_links_to_memory_hub(nav_html):
    assert "memory_hub.html" in nav_html
    assert 'href="memory_hub.html"' in nav_html


def test_memory_hub_links_to_import_prototype(hub_html):
    assert "memory_import_screen.html" in hub_html


def test_memory_hub_links_to_review_search_prototype(hub_html):
    assert "memory_review_search.html" in hub_html


def test_navigation_includes_direct_prototype_links(nav_html):
    assert "memory_import_screen.html" in nav_html
    assert "memory_review_search.html" in nav_html


@pytest.mark.parametrize("phrase", REQUIRED_MEMORY_LANGUAGE)
def test_user_facing_memory_language(nav_html, phrase):
    assert phrase in nav_html


def test_local_files_only_language(nav_html):
    assert "Uses local files only" in nav_html


def test_no_account_connection_language(nav_html):
    assert "No account connection required" in nav_html


def test_no_network_js_in_navigation_entry(nav_html):
    lower = nav_html.lower()
    assert "<script" not in lower
    for token in FORBIDDEN_NETWORK_JS:
        assert token not in nav_html


def test_no_external_network_assets_in_navigation_entry(nav_html):
    assert not EXTERNAL_ASSET_PATTERN.search(nav_html)


def test_no_server_route_in_navigation_entry(nav_html):
    assert "/api/" not in nav_html
    assert 'href="/' not in nav_html


def test_core_py_untouched():
    text = CORE_PATH.read_text(encoding="utf-8")
    assert "memory_hub.html" not in text
    assert "memory_hub_navigation" not in text


def test_server_py_untouched():
    text = SERVER_PATH.read_text(encoding="utf-8")
    assert "memory_hub.html" not in text
    assert "memory_hub_navigation" not in text
