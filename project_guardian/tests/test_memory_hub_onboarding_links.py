# project_guardian/tests/test_memory_hub_onboarding_links.py

from __future__ import annotations

import re
from html.parser import HTMLParser
from pathlib import Path

from project_guardian.local_ingestion import memory_dashboard_route_contract as contract

REPO_ROOT = Path(__file__).resolve().parents[2]
HUB_PATH = REPO_ROOT / "project_guardian" / "ui" / "static" / "memory_hub.html"

EXPECTED_ONBOARDING_LINKS = {
    "/memory/memory_first_run_setup.html": (
        "First-Run Setup",
        "Start here if this is your first time using local memory.",
    ),
    "/memory/memory_safety.html": (
        "Memory Safety",
        "Review what this local memory prototype does and does not do.",
    ),
    "/memory/memory_diagnostics.html": (
        "Diagnostics",
        "Check local memory workspace health.",
    ),
    "/memory/memory_import_screen.html": (
        "Import Memory",
        "Preview and apply supported local imports.",
    ),
    "/memory/memory_review_search.html": (
        "Review and Search",
        "Review pending candidates and search approved local memory.",
    ),
}


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


def _hub_html() -> str:
    return HUB_PATH.read_text(encoding="utf-8")


def _onboarding_block() -> str:
    html = _hub_html()
    match = re.search(
        r'<(?P<tag>section|nav)\s+id="memory-onboarding"[^>]*>.*?</(?P=tag)>',
        html,
        re.IGNORECASE | re.DOTALL,
    )
    assert match is not None
    return match.group(0)


def _onboarding_links() -> dict[str, str]:
    parser = _AnchorParser()
    parser.feed(_onboarding_block())
    return dict(parser.links)


def test_memory_hub_contains_all_onboarding_links():
    links = _onboarding_links()
    for href in EXPECTED_ONBOARDING_LINKS:
        assert href in links


def test_onboarding_links_use_memory_route_paths():
    for href in _onboarding_links():
        assert href.startswith("/memory/")


def test_onboarding_link_targets_are_allowlisted_pages():
    allowlist = set(contract.ALLOWED_STATIC_MEMORY_PAGES)
    for href in _onboarding_links():
        page_name = href.removeprefix("/memory/")
        assert page_name in allowlist


def test_onboarding_links_have_readable_labels_and_supporting_text():
    block = _onboarding_block()
    links = _onboarding_links()
    for href, (label, supporting_text) in EXPECTED_ONBOARDING_LINKS.items():
        assert label in links[href]
        assert supporting_text in block


def test_static_local_prototype_language_remains_present():
    html = _hub_html().lower()
    for marker in ("static", "local", "prototype"):
        assert marker in html


def test_onboarding_links_do_not_add_browser_network_or_forms():
    block = _onboarding_block().lower()
    forbidden = (
        "fetch(",
        "xmlhttprequest",
        "websocket",
        "<form",
        "method=\"post\"",
        "method='post'",
        "action=",
        "onclick=",
        "<script",
    )
    for token in forbidden:
        assert token not in block


def test_onboarding_links_do_not_call_backend_commands():
    block = _onboarding_block().lower()
    forbidden = (
        "/api/",
        "memory_import.py",
        "memory_doctor.py",
        "create_memory_demo_workspace.py",
        "run_memory_health_smoke.py",
        "subprocess",
        "popen",
        "os.system",
    )
    for token in forbidden:
        assert token not in block


def test_onboarding_links_do_not_expose_filesystem_paths():
    block = _onboarding_block().lower()
    forbidden = (
        "c:\\",
        "f:\\",
        "\\\\",
        "project_guardian/",
        "scripts/",
        ".jsonl",
        ".sqlite",
    )
    for token in forbidden:
        assert token not in block
