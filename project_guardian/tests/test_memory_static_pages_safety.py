# project_guardian/tests/test_memory_static_pages_safety.py

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
STATIC_DIR = REPO_ROOT / "project_guardian" / "ui" / "static"

STATIC_MEMORY_PAGES = (
    "index.html",
    "memory_first_run_setup.html",
    "memory_safety.html",
    "memory_hub.html",
    "memory_import_screen.html",
    "memory_review_search.html",
    "memory_diagnostics.html",
)

EXTERNAL_ASSET_PATTERN = re.compile(
    r'(?:src|href|action)\s*=\s*["\']https?://',
    re.IGNORECASE,
)

ABSOLUTE_API_ROUTE_PATTERN = re.compile(
    r'(?:src|href|action)\s*=\s*["\']/(?:api|memory|review|search|import)',
    re.IGNORECASE,
)

FORBIDDEN_RUNTIME_TOKENS = (
    "fetch(",
    "XMLHttpRequest",
    "WebSocket",
)


@pytest.mark.parametrize("page_name", STATIC_MEMORY_PAGES)
def test_static_memory_page_exists(page_name):
    assert (STATIC_DIR / page_name).is_file()


@pytest.mark.parametrize("page_name", STATIC_MEMORY_PAGES)
def test_static_memory_pages_have_no_external_network_assets(page_name):
    html = (STATIC_DIR / page_name).read_text(encoding="utf-8")
    assert not EXTERNAL_ASSET_PATTERN.search(html)


@pytest.mark.parametrize("page_name", STATIC_MEMORY_PAGES)
def test_static_memory_pages_have_no_runtime_network_tokens(page_name):
    html = (STATIC_DIR / page_name).read_text(encoding="utf-8")
    for token in FORBIDDEN_RUNTIME_TOKENS:
        assert token not in html


@pytest.mark.parametrize("page_name", STATIC_MEMORY_PAGES)
def test_static_memory_pages_do_not_link_to_api_routes(page_name):
    html = (STATIC_DIR / page_name).read_text(encoding="utf-8")
    assert "/api/" not in html
    assert not ABSOLUTE_API_ROUTE_PATTERN.search(html)
