# project_guardian/tests/test_memory_dashboard_control_panel_link.py

from __future__ import annotations

import re
from html.parser import HTMLParser
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DASHBOARD_TEMPLATE = REPO_ROOT / "project_guardian" / "ui" / "templates" / "dashboard.html"
TEST_PATH = Path(__file__).resolve()


class _AnchorTextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._current_href: str | None = None
        self._parts: list[str] = []
        self.links: list[tuple[str, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "a":
            return
        attributes = dict(attrs)
        self._current_href = attributes.get("href")
        self._parts = []

    def handle_data(self, data: str) -> None:
        if self._current_href is not None:
            self._parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "a" and self._current_href is not None:
            text = " ".join("".join(self._parts).split())
            self.links.append((self._current_href, text))
            self._current_href = None
            self._parts = []


def _dashboard_html() -> str:
    return DASHBOARD_TEMPLATE.read_text(encoding="utf-8")


def _memory_link_block() -> str:
    html = _dashboard_html()
    match = re.search(
        r'<div id="memory-hub-dashboard-link"[^>]*>.*?</div>',
        html,
        re.IGNORECASE | re.DOTALL,
    )
    assert match is not None
    return match.group(0)


def test_main_dashboard_template_includes_memory_hub_link():
    parser = _AnchorTextParser()
    parser.feed(_dashboard_html())
    assert ("/memory", "Memory Hub") in parser.links


def test_memory_hub_link_is_labeled_static_local_prototype():
    block = _memory_link_block().lower()
    assert "memory hub" in block
    for marker in ("static", "local", "prototype"):
        assert marker in block
    for marker in ("import", "review", "search", "diagnostics", "safety"):
        assert marker in block


def test_memory_hub_link_uses_no_browser_api_or_post_form():
    block = _memory_link_block().lower()
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


def test_memory_hub_link_does_not_call_memory_commands_or_api_routes():
    block = _memory_link_block().lower()
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


def test_memory_hub_link_does_not_expose_filesystem_paths():
    block = _memory_link_block().lower()
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


def test_control_panel_link_test_avoids_protected_runtime_imports():
    source = TEST_PATH.read_text(encoding="utf-8")
    forbidden_imports = (
        "elysia.api." + "server",
        "project_guardian." + "core",
    )
    for token in forbidden_imports:
        assert token not in source
