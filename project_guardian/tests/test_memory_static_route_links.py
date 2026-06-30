# project_guardian/tests/test_memory_static_route_links.py

from __future__ import annotations

import re
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlparse

from project_guardian.local_ingestion import memory_dashboard_route_contract as contract

REPO_ROOT = Path(__file__).resolve().parents[2]
STATIC_DIR = REPO_ROOT / "project_guardian" / "ui" / "static"

STATIC_MEMORY_PAGES = (
    "index.html",
    "memory_hub.html",
    "memory_first_run_setup.html",
    "memory_safety.html",
    "memory_diagnostics.html",
    "memory_import_screen.html",
    "memory_review_search.html",
)

ALLOWED_ROUTE_TARGETS = {
    "/memory",
    "/memory/",
    "/memory/index.html",
    "/memory/memory_hub.html",
    "/memory/memory_import_screen.html",
    "/memory/memory_review_search.html",
    "/memory/memory_first_run_setup.html",
    "/memory/memory_safety.html",
    "/memory/memory_diagnostics.html",
}

RELATIVE_MEMORY_LINK_PATTERN = re.compile(
    r"""href\s*=\s*["'](?:\./)?(?:memory_[^"']+|index\.html)["']""",
    re.IGNORECASE,
)


class _AnchorParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._current_href: str | None = None
        self._parts: list[str] = []
        self.links: list[tuple[str, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "a":
            return
        self._current_href = dict(attrs).get("href")
        self._parts = []

    def handle_data(self, data: str) -> None:
        if self._current_href is not None:
            self._parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() != "a" or self._current_href is None:
            return
        text = " ".join("".join(self._parts).split())
        self.links.append((self._current_href, text))
        self._current_href = None
        self._parts = []


def _html(page_name: str) -> str:
    return (STATIC_DIR / page_name).read_text(encoding="utf-8")


def _links(page_name: str) -> list[tuple[str, str]]:
    parser = _AnchorParser()
    parser.feed(_html(page_name))
    return parser.links


def _memory_links(page_name: str) -> list[tuple[str, str]]:
    links: list[tuple[str, str]] = []
    for href, text in _links(page_name):
        if href in {"#", ""}:
            continue
        if href.startswith("/memory") or href.startswith("memory_") or href == "index.html":
            links.append((href, text))
    return links


def test_static_memory_pages_have_no_relative_sibling_memory_links():
    for page_name in STATIC_MEMORY_PAGES:
        assert not RELATIVE_MEMORY_LINK_PATTERN.search(_html(page_name)), page_name


def test_static_memory_pages_have_no_dot_relative_sibling_memory_links():
    for page_name in STATIC_MEMORY_PAGES:
        html = _html(page_name)
        assert 'href="./memory_' not in html
        assert "href='./memory_" not in html


def test_memory_cross_links_use_memory_route_paths():
    for page_name in STATIC_MEMORY_PAGES:
        for href, _text in _memory_links(page_name):
            assert href.startswith("/memory"), f"{page_name}: {href}"


def test_memory_route_targets_are_allowlisted():
    allowlist = set(contract.ALLOWED_STATIC_MEMORY_PAGES)
    for page_name in STATIC_MEMORY_PAGES:
        for href, _text in _memory_links(page_name):
            parsed = urlparse(href)
            assert parsed.path in ALLOWED_ROUTE_TARGETS, f"{page_name}: {href}"
            if parsed.path in {"/memory", "/memory/"}:
                continue
            target_page = parsed.path.removeprefix("/memory/")
            assert target_page in allowlist, f"{page_name}: {href}"


def test_diagnostics_safety_link_uses_memory_route_path():
    links = dict(_links("memory_diagnostics.html"))
    assert links["/memory/memory_safety.html"] == "Open Memory Safety"


def test_memory_hub_sibling_links_use_memory_route_paths():
    hub_targets = {href for href, _text in _memory_links("memory_hub.html")}
    expected = {
        "/memory/memory_first_run_setup.html",
        "/memory/memory_safety.html",
        "/memory/memory_diagnostics.html",
        "/memory/memory_import_screen.html",
        "/memory/memory_review_search.html",
    }
    assert expected.issubset(hub_targets)


def test_sibling_pages_link_back_to_memory_hub_through_route():
    for page_name in (
        "memory_first_run_setup.html",
        "memory_safety.html",
        "memory_diagnostics.html",
        "memory_import_screen.html",
        "memory_review_search.html",
    ):
        links = _links(page_name)
        assert ("/memory/memory_hub.html", "Back to Memory Hub") in links


def test_route_links_do_not_add_browser_network_or_forms():
    for page_name in STATIC_MEMORY_PAGES:
        for href, text in _memory_links(page_name):
            rendered = f"{href} {text}".lower()
            for token in (
                "fetch(",
                "xmlhttprequest",
                "websocket",
                "<form",
                "method=\"post\"",
                "method='post'",
                "action=",
                "onclick=",
                "<script",
            ):
                assert token not in rendered


def test_route_links_do_not_call_backend_commands_or_expose_filesystem_paths():
    for page_name in STATIC_MEMORY_PAGES:
        for href, text in _memory_links(page_name):
            rendered = f"{href} {text}".lower()
            for token in (
                "/api/",
                "memory_import.py",
                "memory_doctor.py",
                "create_memory_demo_workspace.py",
                "run_memory_health_smoke.py",
                "subprocess",
                "popen",
                "os.system",
                "c:\\",
                "f:\\",
                "\\\\",
                "project_guardian/",
                "scripts/",
                ".jsonl",
                ".sqlite",
            ):
                assert token not in rendered
