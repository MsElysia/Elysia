# project_guardian/tests/test_memory_static_backlinks.py

from __future__ import annotations

from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlparse

from project_guardian.local_ingestion import memory_dashboard_route_contract as contract

REPO_ROOT = Path(__file__).resolve().parents[2]
STATIC_DIR = REPO_ROOT / "project_guardian" / "ui" / "static"
HUB_TARGETS = {"/memory", "/memory/memory_hub.html"}

SIBLING_PAGES = {
    "memory_first_run_setup.html": "first-run setup",
    "memory_safety.html": "safety",
    "memory_diagnostics.html": "diagnostics",
    "memory_import_screen.html": "import",
    "memory_review_search.html": "review/search",
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


def _html(page_name: str) -> str:
    return (STATIC_DIR / page_name).read_text(encoding="utf-8")


def _links(page_name: str) -> list[tuple[str, str]]:
    parser = _AnchorParser()
    parser.feed(_html(page_name))
    return parser.links


def _backlinks(page_name: str) -> list[str]:
    return [
        href
        for href, text in _links(page_name)
        if "Back to Memory Hub" in text
    ]


def test_each_sibling_page_contains_back_to_memory_hub_link():
    for page_name in SIBLING_PAGES:
        assert _backlinks(page_name), f"missing backlink in {page_name}"


def test_backlinks_use_memory_route_paths():
    for page_name in SIBLING_PAGES:
        for href in _backlinks(page_name):
            assert href in HUB_TARGETS


def test_backlink_targets_are_allowlisted_route_targets():
    allowlist = set(contract.ALLOWED_STATIC_MEMORY_PAGES)
    for page_name in SIBLING_PAGES:
        for href in _backlinks(page_name):
            parsed = urlparse(href)
            if parsed.path == "/memory":
                continue
            assert parsed.path.startswith("/memory/")
            target_page = parsed.path.removeprefix("/memory/")
            assert target_page in allowlist


def test_backlink_supporting_text_is_static_local():
    for page_name in SIBLING_PAGES:
        html = _html(page_name)
        assert "Return to the static local Memory Hub." in html


def test_existing_static_local_prototype_language_remains_present():
    for page_name in SIBLING_PAGES:
        html = _html(page_name).lower()
        assert "local" in html
        assert "static" in html or "prototype" in html


def test_backlinks_do_not_add_browser_network_or_forms():
    for page_name in SIBLING_PAGES:
        for href, text in _links(page_name):
            if "Back to Memory Hub" not in text:
                continue
            rendered = f'{href} {text}'.lower()
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
                assert token not in rendered


def test_backlinks_do_not_call_backend_commands_or_expose_filesystem_paths():
    for page_name in SIBLING_PAGES:
        for href, text in _links(page_name):
            if "Back to Memory Hub" not in text:
                continue
            rendered = f'{href} {text}'.lower()
            forbidden = (
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
            )
            for token in forbidden:
                assert token not in rendered
