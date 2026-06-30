# project_guardian/tests/test_memory_static_page_identity.py

from __future__ import annotations

import re
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlparse

import pytest

from project_guardian.local_ingestion import memory_dashboard_route_contract as contract

REPO_ROOT = Path(__file__).resolve().parents[2]
STATIC_DIR = REPO_ROOT / "project_guardian" / "ui" / "static"

PAGE_EXPECTATIONS = {
    "index.html": {
        "route": "/memory/index.html",
        "heading": "Elysia Memory Static UI",
        "title_terms": ("Elysia", "Memory", "Static UI"),
        "breadcrumb": "Memory Hub / Static UI",
        "identity": "Static UI",
        "back_to_hub": False,
    },
    "memory_hub.html": {
        "route": "/memory/memory_hub.html",
        "heading": "Memory Hub",
        "title_terms": ("Elysia", "Memory Hub"),
        "breadcrumb": "Memory Hub",
        "identity": "Memory Hub",
        "back_to_hub": False,
    },
    "memory_first_run_setup.html": {
        "route": "/memory/memory_first_run_setup.html",
        "heading": "Memory First-Run Setup",
        "title_terms": ("Elysia", "First-Run Setup"),
        "breadcrumb": "Memory Hub / First-Run Setup",
        "identity": "First-Run Setup",
        "back_to_hub": True,
    },
    "memory_safety.html": {
        "route": "/memory/memory_safety.html",
        "heading": "Memory Safety",
        "title_terms": ("Elysia", "Safety"),
        "breadcrumb": "Memory Hub / Safety",
        "identity": "Memory Safety",
        "back_to_hub": True,
    },
    "memory_diagnostics.html": {
        "route": "/memory/memory_diagnostics.html",
        "heading": "Memory Diagnostics",
        "title_terms": ("Elysia", "Diagnostics"),
        "breadcrumb": "Memory Hub / Diagnostics",
        "identity": "Diagnostics",
        "back_to_hub": True,
    },
    "memory_import_screen.html": {
        "route": "/memory/memory_import_screen.html",
        "heading": "Import Memory",
        "title_terms": ("Elysia", "Import Memory"),
        "breadcrumb": "Memory Hub / Import Memory",
        "identity": "Import Memory",
        "back_to_hub": True,
    },
    "memory_review_search.html": {
        "route": "/memory/memory_review_search.html",
        "heading": "Review and Search Memory",
        "title_terms": ("Elysia", "Review and Search"),
        "breadcrumb": "Memory Hub / Review and Search",
        "identity": "Review and Search",
        "back_to_hub": True,
    },
}

ALLOWED_ROUTE_TARGETS = {
    "/memory",
    "/memory/",
    *(
        f"/memory/{page_name}"
        for page_name in contract.ALLOWED_STATIC_MEMORY_PAGES
    ),
}

ROUTE_LABEL_PATTERN = re.compile(
    r"Local route:\s*(/memory(?:/[A-Za-z0-9_.-]+)?)"
)

FORBIDDEN_RUNTIME_TOKENS = (
    "fetch(",
    "XMLHttpRequest",
    "WebSocket",
)

BACKEND_COMMAND_TOKENS = (
    "memory_import.py",
    "review_memory_candidates.py",
    "search_approved_memory.py",
    "build_memory_context_bundle.py",
)

DIAGNOSTIC_COMMAND_TOKENS = (
    "memory_doctor.py",
    "create_memory_demo_workspace.py",
    "run_memory_health_smoke.py",
)

CALLABLE_ATTRS = {
    "href",
    "action",
    "formaction",
    "onclick",
    "data-action",
    "data-command",
}

FILESYSTEM_PATH_PATTERN = re.compile(
    r"[A-Za-z]:[\\/]|\\\\|(?:^|\s)(?:\.{1,2}[\\/]|~[\\/])|"
    r"/Users/|/home/|project_guardian[\\/]|scripts[\\/]"
)


class _PageParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._current_title = False
        self._current_h1 = False
        self._current_href: str | None = None
        self._anchor_parts: list[str] = []
        self.title_parts: list[str] = []
        self.h1s: list[str] = []
        self._h1_parts: list[str] = []
        self.text_parts: list[str] = []
        self.links: list[tuple[str, str]] = []
        self.start_tags: list[tuple[str, list[tuple[str, str | None]]]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag_lower = tag.lower()
        self.start_tags.append((tag_lower, attrs))
        if tag_lower == "title":
            self._current_title = True
        if tag_lower == "h1":
            self._current_h1 = True
            self._h1_parts = []
        if tag_lower == "a":
            self._current_href = dict(attrs).get("href")
            self._anchor_parts = []

    def handle_data(self, data: str) -> None:
        self.text_parts.append(data)
        if self._current_title:
            self.title_parts.append(data)
        if self._current_h1:
            self._h1_parts.append(data)
        if self._current_href is not None:
            self._anchor_parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        tag_lower = tag.lower()
        if tag_lower == "title":
            self._current_title = False
        if tag_lower == "h1":
            self._current_h1 = False
            self.h1s.append(_collapse("".join(self._h1_parts)))
            self._h1_parts = []
        if tag_lower == "a" and self._current_href is not None:
            text = _collapse("".join(self._anchor_parts))
            self.links.append((self._current_href, text))
            self._current_href = None
            self._anchor_parts = []


def _collapse(text: str) -> str:
    return " ".join(text.split())


def _html(page_name: str) -> str:
    return (STATIC_DIR / page_name).read_text(encoding="utf-8")


def _parse(html: str) -> _PageParser:
    parser = _PageParser()
    parser.feed(html)
    return parser


def _text(parser: _PageParser) -> str:
    return _collapse(" ".join(parser.text_parts))


def _route_labels(html: str) -> list[str]:
    return ROUTE_LABEL_PATTERN.findall(_text(_parse(html)))


def _identity_blocks(html: str) -> list[str]:
    return re.findall(
        r'<div class="identity"[^>]*>(.*?)</div>',
        html,
        flags=re.IGNORECASE | re.DOTALL,
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


@pytest.mark.parametrize("page_name, expected", PAGE_EXPECTATIONS.items())
def test_every_memory_static_page_has_title(page_name, expected):
    parser = _parse(_html(page_name))
    title = _collapse("".join(parser.title_parts))
    assert title
    for term in expected["title_terms"]:
        assert term in title


@pytest.mark.parametrize("page_name, expected", PAGE_EXPECTATIONS.items())
def test_every_memory_static_page_has_clear_top_level_heading(page_name, expected):
    parser = _parse(_html(page_name))
    assert parser.h1s == [expected["heading"]]


@pytest.mark.parametrize("page_name, expected", PAGE_EXPECTATIONS.items())
def test_every_served_memory_page_has_visible_route_label(client, page_name, expected):
    response = client.get(expected["route"])
    assert response.status_code == 200
    assert expected["route"] in _route_labels(response.text), page_name


@pytest.mark.parametrize("page_name", PAGE_EXPECTATIONS)
def test_route_labels_use_memory_routes(page_name):
    labels = _route_labels(_html(page_name))
    assert labels, page_name
    for label in labels:
        assert label == "/memory" or label.startswith("/memory/"), label


@pytest.mark.parametrize("page_name", PAGE_EXPECTATIONS)
def test_route_labels_are_allowlisted(page_name):
    for label in _route_labels(_html(page_name)):
        parsed = urlparse(label)
        assert parsed.path in ALLOWED_ROUTE_TARGETS, f"{page_name}: {label}"


@pytest.mark.parametrize("page_name, expected", PAGE_EXPECTATIONS.items())
def test_breadcrumb_or_navigation_identity_is_visible(page_name, expected):
    assert expected["breadcrumb"] in _text(_parse(_html(page_name)))


@pytest.mark.parametrize("page_name, expected", PAGE_EXPECTATIONS.items())
def test_page_specific_identity_is_visible(page_name, expected):
    assert expected["identity"] in _text(_parse(_html(page_name)))


def test_memory_hub_page_identifies_itself_as_memory_hub():
    text = _text(_parse(_html("memory_hub.html")))
    assert "Memory Hub" in text
    assert "Local route: /memory/memory_hub.html" in text


def test_first_run_page_identifies_itself_as_first_run_setup():
    assert "First-Run Setup" in _text(_parse(_html("memory_first_run_setup.html")))


def test_safety_page_identifies_itself_as_memory_safety():
    assert "Memory Safety" in _text(_parse(_html("memory_safety.html")))


def test_diagnostics_page_identifies_itself_as_diagnostics():
    assert "Diagnostics" in _text(_parse(_html("memory_diagnostics.html")))


def test_import_page_identifies_itself_as_import_memory():
    assert "Import Memory" in _text(_parse(_html("memory_import_screen.html")))


def test_review_search_page_identifies_itself_as_review_and_search():
    assert "Review and Search" in _text(_parse(_html("memory_review_search.html")))


def test_sibling_pages_still_link_back_to_memory_hub():
    for page_name, expected in PAGE_EXPECTATIONS.items():
        if not expected["back_to_hub"]:
            continue
        parser = _parse(_html(page_name))
        assert ("/memory/memory_hub.html", "Back to Memory Hub") in parser.links


@pytest.mark.parametrize("page_name", PAGE_EXPECTATIONS)
def test_static_local_prototype_language_is_preserved(page_name):
    text = _text(_parse(_html(page_name))).lower()
    assert "local" in text
    assert "static" in text or "prototype" in text


@pytest.mark.parametrize("page_name", PAGE_EXPECTATIONS)
def test_no_browser_fetch_xhr_or_websocket_was_added(page_name):
    html = _html(page_name)
    for token in FORBIDDEN_RUNTIME_TOKENS:
        assert token not in html


@pytest.mark.parametrize("page_name", PAGE_EXPECTATIONS)
def test_no_post_forms_or_actions_were_added(page_name):
    parser = _parse(_html(page_name))
    for tag, attrs in parser.start_tags:
        assert tag != "form", page_name
        attrs_dict = {name.lower(): value for name, value in attrs if value}
        assert attrs_dict.get("method", "").lower() != "post"
        assert "action" not in attrs_dict
        assert "formaction" not in attrs_dict


@pytest.mark.parametrize("page_name", PAGE_EXPECTATIONS)
def test_backend_memory_commands_are_not_callable_from_pages(page_name):
    parser = _parse(_html(page_name))
    for _tag, attrs in parser.start_tags:
        for name, value in attrs:
            if not value or name.lower() not in CALLABLE_ATTRS:
                continue
            rendered = value.lower()
            for token in BACKEND_COMMAND_TOKENS:
                assert token not in rendered


@pytest.mark.parametrize("page_name", PAGE_EXPECTATIONS)
def test_diagnostics_demo_commands_are_not_callable_from_pages(page_name):
    parser = _parse(_html(page_name))
    for _tag, attrs in parser.start_tags:
        for name, value in attrs:
            if not value or name.lower() not in CALLABLE_ATTRS:
                continue
            rendered = value.lower()
            for token in DIAGNOSTIC_COMMAND_TOKENS:
                assert token not in rendered


@pytest.mark.parametrize("page_name", PAGE_EXPECTATIONS)
def test_no_backend_command_execution_helpers_were_added(page_name):
    html = _html(page_name).lower()
    for token in ("subprocess", "popen", "os.system"):
        assert token not in html


@pytest.mark.parametrize("page_name", PAGE_EXPECTATIONS)
def test_page_identity_does_not_expose_filesystem_paths(page_name):
    blocks = _identity_blocks(_html(page_name))
    assert blocks, page_name
    for block in blocks:
        assert not FILESYSTEM_PATH_PATTERN.search(block), page_name
