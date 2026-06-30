# project_guardian/tests/test_memory_static_landmarks_skiplinks.py

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
        "description": "Static local Memory UI entry page for Project Guardian.",
        "heading": "Elysia Memory Static UI",
        "title_terms": ("Elysia", "Memory", "Static UI"),
        "breadcrumb": "Memory Hub / Static UI",
        "current": "Static UI",
        "back_to_hub": False,
    },
    "memory_hub.html": {
        "route": "/memory/memory_hub.html",
        "description": "Static local Memory Hub for Project Guardian import, review, search, diagnostics, and safety guidance.",
        "heading": "Memory Hub",
        "title_terms": ("Elysia", "Memory Hub"),
        "breadcrumb": "Memory Hub",
        "current": "Memory Hub",
        "back_to_hub": False,
    },
    "memory_first_run_setup.html": {
        "route": "/memory/memory_first_run_setup.html",
        "description": "Static first-run setup guide for local Project Guardian memory workflows.",
        "heading": "Memory First-Run Setup",
        "title_terms": ("Elysia", "First-Run Setup"),
        "breadcrumb": "Memory Hub / First-Run Setup",
        "current": "First-Run Setup",
        "back_to_hub": True,
    },
    "memory_safety.html": {
        "route": "/memory/memory_safety.html",
        "description": "Static safety guide explaining local memory boundaries and disabled live execution.",
        "heading": "Memory Safety",
        "title_terms": ("Elysia", "Safety"),
        "breadcrumb": "Memory Hub / Safety",
        "current": "Safety",
        "back_to_hub": True,
    },
    "memory_diagnostics.html": {
        "route": "/memory/memory_diagnostics.html",
        "description": "Static diagnostics guide for checking local memory workspace health.",
        "heading": "Memory Diagnostics",
        "title_terms": ("Elysia", "Diagnostics"),
        "breadcrumb": "Memory Hub / Diagnostics",
        "current": "Diagnostics",
        "back_to_hub": True,
    },
    "memory_import_screen.html": {
        "route": "/memory/memory_import_screen.html",
        "description": "Static import guide for supported local memory source previews.",
        "heading": "Import Memory",
        "title_terms": ("Elysia", "Import Memory"),
        "breadcrumb": "Memory Hub / Import Memory",
        "current": "Import Memory",
        "back_to_hub": True,
    },
    "memory_review_search.html": {
        "route": "/memory/memory_review_search.html",
        "description": "Static review and search guide for approved local memory candidates.",
        "heading": "Review and Search Memory",
        "title_terms": ("Elysia", "Review and Search"),
        "breadcrumb": "Memory Hub / Review and Search",
        "current": "Review and Search",
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

FILESYSTEM_PATH_PATTERN = re.compile(
    r"[A-Za-z]:[\\/]|\\\\|(?:^|\s)(?:\.{1,2}[\\/]|~[\\/])|"
    r"/Users/|/home/|project_guardian[\\/]|scripts[\\/]"
)


class _PageParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.html_lang: str | None = None
        self.meta_descriptions: list[str] = []
        self.title_parts: list[str] = []
        self.h1s: list[str] = []
        self.text_parts: list[str] = []
        self.links: list[tuple[str, str]] = []
        self.main_ids: list[str | None] = []
        self.nav_labels: list[str] = []
        self.current_page_items: list[str] = []
        self.start_tags: list[tuple[str, list[tuple[str, str | None]]]] = []
        self._in_title = False
        self._in_h1 = False
        self._h1_parts: list[str] = []
        self._current_href: str | None = None
        self._anchor_parts: list[str] = []
        self._current_page_parts: list[str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag_lower = tag.lower()
        attrs_dict = {name.lower(): value for name, value in attrs if value}
        self.start_tags.append((tag_lower, attrs))
        if tag_lower == "html":
            self.html_lang = attrs_dict.get("lang")
        if tag_lower == "meta" and attrs_dict.get("name", "").lower() == "description":
            self.meta_descriptions.append(attrs_dict.get("content", ""))
        if tag_lower == "main":
            self.main_ids.append(attrs_dict.get("id"))
        if tag_lower == "nav":
            self.nav_labels.append(attrs_dict.get("aria-label", ""))
        if tag_lower == "title":
            self._in_title = True
        if tag_lower == "h1":
            self._in_h1 = True
            self._h1_parts = []
        if attrs_dict.get("aria-current") == "page":
            self._current_page_parts = []
        if tag_lower == "a":
            self._current_href = attrs_dict.get("href")
            self._anchor_parts = []

    def handle_data(self, data: str) -> None:
        self.text_parts.append(data)
        if self._in_title:
            self.title_parts.append(data)
        if self._in_h1:
            self._h1_parts.append(data)
        if self._current_href is not None:
            self._anchor_parts.append(data)
        if self._current_page_parts is not None:
            self._current_page_parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        tag_lower = tag.lower()
        if tag_lower == "title":
            self._in_title = False
        if tag_lower == "h1":
            self._in_h1 = False
            self.h1s.append(_collapse("".join(self._h1_parts)))
            self._h1_parts = []
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


def _parse(html: str) -> _PageParser:
    parser = _PageParser()
    parser.feed(html)
    return parser


def _text(parser: _PageParser) -> str:
    return _collapse(" ".join(parser.text_parts))


def _route_labels(html: str) -> list[str]:
    return ROUTE_LABEL_PATTERN.findall(_text(_parse(html)))


def _landmark_text(html: str) -> str:
    parser = _parse(html)
    pieces = [
        " ".join(label for label in parser.nav_labels if label),
        " ".join(str(main_id) for main_id in parser.main_ids if main_id),
    ]
    pieces.extend(href for href, text in parser.links if text == "Skip to main content")
    return " ".join(pieces)


@pytest.mark.parametrize("page_name", PAGE_EXPECTATIONS)
def test_every_memory_static_page_has_skip_to_main_content_link(page_name):
    parser = _parse(_html(page_name))
    assert ("#main-content", "Skip to main content") in parser.links


@pytest.mark.parametrize("page_name", PAGE_EXPECTATIONS)
def test_skip_links_target_main_content(page_name):
    skip_hrefs = [
        href
        for href, text in _parse(_html(page_name)).links
        if text == "Skip to main content"
    ]
    assert skip_hrefs == ["#main-content"]


@pytest.mark.parametrize("page_name", PAGE_EXPECTATIONS)
def test_every_memory_static_page_has_exactly_one_main(page_name):
    assert len(_parse(_html(page_name)).main_ids) == 1


@pytest.mark.parametrize("page_name", PAGE_EXPECTATIONS)
def test_every_main_landmark_has_main_content_id(page_name):
    assert _parse(_html(page_name)).main_ids == ["main-content"]


@pytest.mark.parametrize("page_name", PAGE_EXPECTATIONS)
def test_every_memory_static_page_has_breadcrumb_navigation_landmark(page_name):
    assert "Memory breadcrumb" in _parse(_html(page_name)).nav_labels


@pytest.mark.parametrize("page_name", PAGE_EXPECTATIONS)
def test_breadcrumb_navigation_has_useful_accessible_label(page_name):
    labels = _parse(_html(page_name)).nav_labels
    assert labels.count("Memory breadcrumb") == 1


@pytest.mark.parametrize("page_name, expected", PAGE_EXPECTATIONS.items())
def test_active_breadcrumb_item_still_uses_aria_current_page(page_name, expected):
    assert _parse(_html(page_name)).current_page_items == [expected["current"]]


@pytest.mark.parametrize("page_name", PAGE_EXPECTATIONS)
def test_navigation_link_groups_have_useful_labels(page_name):
    assert "Memory page navigation" in _parse(_html(page_name)).nav_labels


@pytest.mark.parametrize("page_name", PAGE_EXPECTATIONS)
def test_focus_styles_exist_for_links_or_buttons(page_name):
    html = _html(page_name)
    assert ".skip-link:focus" in html
    assert "a:focus" in html
    assert "button:focus" in html
    assert "outline:" in html


@pytest.mark.parametrize("page_name", PAGE_EXPECTATIONS)
def test_html_lang_en_remains_present(page_name):
    assert _parse(_html(page_name)).html_lang == "en"


@pytest.mark.parametrize("page_name, expected", PAGE_EXPECTATIONS.items())
def test_meta_descriptions_remain_present(page_name, expected):
    assert _parse(_html(page_name)).meta_descriptions == [expected["description"]]


@pytest.mark.parametrize("page_name, expected", PAGE_EXPECTATIONS.items())
def test_page_titles_remain_present(page_name, expected):
    title = _collapse("".join(_parse(_html(page_name)).title_parts))
    assert title
    for term in expected["title_terms"]:
        assert term in title


@pytest.mark.parametrize("page_name, expected", PAGE_EXPECTATIONS.items())
def test_top_level_headings_remain_present(page_name, expected):
    assert _parse(_html(page_name)).h1s == [expected["heading"]]


@pytest.mark.parametrize("page_name, expected", PAGE_EXPECTATIONS.items())
def test_visible_route_labels_remain_present(page_name, expected):
    labels = _route_labels(_html(page_name))
    assert expected["route"] in labels
    for label in labels:
        assert label == "/memory" or label.startswith("/memory/")
        assert urlparse(label).path in ALLOWED_ROUTE_TARGETS


@pytest.mark.parametrize("page_name, expected", PAGE_EXPECTATIONS.items())
def test_breadcrumb_identity_remains_present(page_name, expected):
    assert expected["breadcrumb"] in _text(_parse(_html(page_name)))


def test_sibling_pages_still_contain_back_to_memory_hub_links():
    for page_name, expected in PAGE_EXPECTATIONS.items():
        if not expected["back_to_hub"]:
            continue
        assert ("/memory/memory_hub.html", "Back to Memory Hub") in _parse(
            _html(page_name)
        ).links


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
def test_landmark_markup_does_not_expose_filesystem_paths(page_name):
    assert not FILESYSTEM_PATH_PATTERN.search(_landmark_text(_html(page_name)))
