# project_guardian/tests/test_memory_static_responsive_print.py

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
        "breadcrumb": "Memory Hub / Static UI",
        "current": "Static UI",
        "required_links": {
            "/memory/memory_hub.html",
            "/memory/memory_first_run_setup.html",
            "/memory/memory_safety.html",
            "/memory/memory_diagnostics.html",
            "/memory/memory_import_screen.html",
            "/memory/memory_review_search.html",
        },
    },
    "memory_hub.html": {
        "route": "/memory/memory_hub.html",
        "breadcrumb": "Memory Hub",
        "current": "Memory Hub",
        "required_links": {
            "/memory/memory_first_run_setup.html",
            "/memory/memory_safety.html",
            "/memory/memory_diagnostics.html",
            "/memory/memory_import_screen.html",
            "/memory/memory_review_search.html",
        },
    },
    "memory_first_run_setup.html": {
        "route": "/memory/memory_first_run_setup.html",
        "breadcrumb": "Memory Hub / First-Run Setup",
        "current": "First-Run Setup",
        "required_links": {
            "/memory/memory_hub.html",
            "/memory/memory_import_screen.html",
            "/memory/index.html",
        },
    },
    "memory_safety.html": {
        "route": "/memory/memory_safety.html",
        "breadcrumb": "Memory Hub / Safety",
        "current": "Safety",
        "required_links": {
            "/memory/memory_hub.html",
            "/memory/memory_first_run_setup.html",
            "/memory/index.html",
        },
    },
    "memory_diagnostics.html": {
        "route": "/memory/memory_diagnostics.html",
        "breadcrumb": "Memory Hub / Diagnostics",
        "current": "Diagnostics",
        "required_links": {
            "/memory/memory_hub.html",
            "/memory/memory_safety.html",
        },
    },
    "memory_import_screen.html": {
        "route": "/memory/memory_import_screen.html",
        "breadcrumb": "Memory Hub / Import Memory",
        "current": "Import Memory",
        "required_links": {"/memory/memory_hub.html"},
    },
    "memory_review_search.html": {
        "route": "/memory/memory_review_search.html",
        "breadcrumb": "Memory Hub / Review and Search",
        "current": "Review and Search",
        "required_links": {"/memory/memory_hub.html"},
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

FILESYSTEM_PATH_PATTERN = re.compile(
    r"[A-Za-z]:[\\/]|\\\\|(?:^|\s)(?:\.{1,2}[\\/]|~[\\/])|"
    r"/Users/|/home/|project_guardian[\\/]|scripts[\\/]"
)

FORBIDDEN_RUNTIME_TOKENS = (
    "fetch(",
    "XMLHttpRequest",
    "WebSocket",
)

BACKEND_COMMAND_TOKENS = (
    "memory_import.py",
    "review_memory_candidates.py",
    "search_approved_memory_store.py",
    "build_approved_memory_context.py",
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


class _PageParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.text_parts: list[str] = []
        self.links: list[tuple[str, str]] = []
        self.main_ids: list[str | None] = []
        self.nav_labels: list[str] = []
        self.current_page_items: list[str] = []
        self.start_tags: list[tuple[str, list[tuple[str, str | None]]]] = []
        self._current_href: str | None = None
        self._anchor_parts: list[str] = []
        self._current_page_parts: list[str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag_lower = tag.lower()
        attrs_dict = {name.lower(): value for name, value in attrs if value}
        self.start_tags.append((tag_lower, attrs))
        if tag_lower == "main":
            self.main_ids.append(attrs_dict.get("id"))
        if tag_lower == "nav":
            self.nav_labels.append(attrs_dict.get("aria-label", ""))
        if attrs_dict.get("aria-current") == "page":
            self._current_page_parts = []
        if tag_lower == "a":
            self._current_href = attrs_dict.get("href")
            self._anchor_parts = []

    def handle_data(self, data: str) -> None:
        self.text_parts.append(data)
        if self._current_href is not None:
            self._anchor_parts.append(data)
        if self._current_page_parts is not None:
            self._current_page_parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        tag_lower = tag.lower()
        if tag_lower == "a" and self._current_href is not None:
            self.links.append(
                (self._current_href, _collapse("".join(self._anchor_parts)))
            )
            self._current_href = None
            self._anchor_parts = []
        if self._current_page_parts is not None:
            self.current_page_items.append(
                _collapse("".join(self._current_page_parts))
            )
            self._current_page_parts = None


def _collapse(text: str) -> str:
    return " ".join(text.split())


def _html(page_name: str) -> str:
    return (STATIC_DIR / page_name).read_text(encoding="utf-8")


def _styles(page_name: str) -> str:
    blocks = re.findall(
        r"<style[^>]*>(.*?)</style>",
        _html(page_name),
        flags=re.IGNORECASE | re.DOTALL,
    )
    assert blocks, page_name
    return "\n".join(blocks)


def _parse(html: str) -> _PageParser:
    parser = _PageParser()
    parser.feed(html)
    return parser


def _text(parser: _PageParser) -> str:
    return _collapse(" ".join(parser.text_parts))


def _route_labels(html: str) -> list[str]:
    return ROUTE_LABEL_PATTERN.findall(_text(_parse(html)))


@pytest.mark.parametrize("page_name", PAGE_EXPECTATIONS)
def test_responsive_css_exists_for_memory_static_pages(page_name):
    styles = _styles(page_name)
    assert "@media (max-width: 720px)" in styles
    assert "body { padding: 16px; }" in styles
    assert ".wrap { max-width: 100%; }" in styles


@pytest.mark.parametrize("page_name", PAGE_EXPECTATIONS)
def test_print_css_exists_for_memory_static_pages(page_name):
    styles = _styles(page_name)
    assert "@media print" in styles
    assert ".skip-link" in styles
    assert "body { background: #ffffff; color: #000000; padding: 0; }" in styles
    assert 'a::after { content: " (" attr(href) ")";' in styles


@pytest.mark.parametrize("page_name", PAGE_EXPECTATIONS)
def test_reduced_motion_preference_is_supported(page_name):
    styles = _styles(page_name)
    assert "@media (prefers-reduced-motion: reduce)" in styles
    assert "scroll-behavior: auto;" in styles
    assert "transition-duration: 0.01ms;" in styles
    assert "animation-duration: 0.01ms;" in styles


@pytest.mark.parametrize("page_name", PAGE_EXPECTATIONS)
def test_color_scheme_preference_is_declared_safely(page_name):
    styles = _styles(page_name)
    assert "@media (prefers-color-scheme: light)" in styles
    assert "color-scheme: dark;" in styles


@pytest.mark.parametrize("page_name", PAGE_EXPECTATIONS)
def test_visible_focus_styles_are_preserved(page_name):
    styles = _styles(page_name)
    assert ".skip-link:focus" in styles
    assert "a:focus" in styles
    assert "button:focus" in styles
    assert "outline:" in styles


@pytest.mark.parametrize("page_name", PAGE_EXPECTATIONS)
def test_skip_links_and_main_landmarks_are_preserved(page_name):
    parser = _parse(_html(page_name))
    assert ("#main-content", "Skip to main content") in parser.links
    assert parser.main_ids == ["main-content"]


@pytest.mark.parametrize("page_name", PAGE_EXPECTATIONS)
def test_breadcrumb_navigation_landmarks_are_preserved(page_name):
    parser = _parse(_html(page_name))
    assert "Memory breadcrumb" in parser.nav_labels
    assert "Memory page navigation" in parser.nav_labels


@pytest.mark.parametrize("page_name, expected", PAGE_EXPECTATIONS.items())
def test_breadcrumbs_and_route_labels_are_preserved(page_name, expected):
    html = _html(page_name)
    assert expected["breadcrumb"] in _text(_parse(html))
    assert _parse(html).current_page_items == [expected["current"]]
    labels = _route_labels(html)
    assert expected["route"] in labels
    for label in labels:
        assert label == "/memory" or label.startswith("/memory/")
        assert urlparse(label).path in ALLOWED_ROUTE_TARGETS


@pytest.mark.parametrize("page_name, expected", PAGE_EXPECTATIONS.items())
def test_required_memory_links_are_preserved(page_name, expected):
    parser = _parse(_html(page_name))
    hrefs = {href for href, _text in parser.links}
    assert expected["required_links"].issubset(hrefs)
    for href in hrefs:
        if href.startswith("/memory/"):
            assert urlparse(href).path in ALLOWED_ROUTE_TARGETS


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
    for tag, attrs in _parse(_html(page_name)).start_tags:
        attrs_dict = {name.lower(): value for name, value in attrs if value}
        assert tag != "form", page_name
        assert attrs_dict.get("method", "").lower() != "post"
        assert "action" not in attrs_dict
        assert "formaction" not in attrs_dict


@pytest.mark.parametrize("page_name", PAGE_EXPECTATIONS)
def test_backend_memory_commands_are_not_callable_from_pages(page_name):
    for _tag, attrs in _parse(_html(page_name)).start_tags:
        for name, value in attrs:
            if not value or name.lower() not in CALLABLE_ATTRS:
                continue
            rendered = value.lower()
            for token in BACKEND_COMMAND_TOKENS:
                assert token not in rendered


@pytest.mark.parametrize("page_name", PAGE_EXPECTATIONS)
def test_diagnostics_demo_commands_are_not_callable_from_pages(page_name):
    for _tag, attrs in _parse(_html(page_name)).start_tags:
        for name, value in attrs:
            if not value or name.lower() not in CALLABLE_ATTRS:
                continue
            rendered = value.lower()
            for token in DIAGNOSTIC_COMMAND_TOKENS:
                assert token not in rendered


@pytest.mark.parametrize("page_name", PAGE_EXPECTATIONS)
def test_static_style_and_route_surfaces_do_not_expose_filesystem_paths(page_name):
    parser = _parse(_html(page_name))
    route_surface = " ".join(
        [
            _styles(page_name),
            " ".join(label for label in parser.nav_labels if label),
            " ".join(main_id for main_id in parser.main_ids if main_id),
            " ".join(href for href, _text in parser.links),
        ]
    )
    assert not FILESYSTEM_PATH_PATTERN.search(route_surface), page_name
