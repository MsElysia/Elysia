# project_guardian/tests/test_memory_route_navigation_graph.py

from __future__ import annotations

from html.parser import HTMLParser
from urllib.parse import urlparse

import pytest

from project_guardian.local_ingestion import memory_dashboard_route_contract as contract

ALLOWLISTED_ROUTES = {
    "/memory",
    "/memory/",
    *(
        f"/memory/{page_name}"
        for page_name in contract.ALLOWED_STATIC_MEMORY_PAGES
    ),
}

EXPECTED_NAVIGATION_ROUTES = {
    "/memory/index.html",
    "/memory/memory_hub.html",
    "/memory/memory_import_screen.html",
    "/memory/memory_review_search.html",
    "/memory/memory_first_run_setup.html",
    "/memory/memory_safety.html",
    "/memory/memory_diagnostics.html",
}


class _AnchorParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "a":
            return
        href = dict(attrs).get("href")
        if href:
            self.links.append(href)


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


def _get_html(client, route: str) -> str:
    response = client.get(route)
    assert response.status_code == 200, route
    assert "text/html" in response.headers.get("content-type", "")
    return response.text


def _links_from_html(html: str) -> list[str]:
    parser = _AnchorParser()
    parser.feed(html)
    return parser.links


@pytest.mark.parametrize("route", sorted(ALLOWLISTED_ROUTES))
def test_allowlisted_memory_routes_serve_html(client, route):
    html = _get_html(client, route)
    assert "<html" in html.lower()


@pytest.mark.parametrize("route", sorted(EXPECTED_NAVIGATION_ROUTES))
def test_memory_route_pages_only_link_to_allowlisted_memory_routes(client, route):
    html = _get_html(client, route)
    for href in _links_from_html(html):
        if href == "#":
            continue
        parsed = urlparse(href)
        assert not parsed.scheme, f"{route} links to external route: {href}"
        assert not parsed.netloc, f"{route} links to network route: {href}"
        assert parsed.path.startswith("/memory"), f"{route} has non-memory route link: {href}"
        assert parsed.path in ALLOWLISTED_ROUTES, f"{route} has unallowlisted link: {href}"


def test_memory_route_navigation_graph_reaches_expected_pages(client):
    seen = {"/memory"}
    pending = ["/memory"]

    while pending:
        route = pending.pop()
        html = _get_html(client, route)
        for href in _links_from_html(html):
            parsed = urlparse(href)
            if parsed.path not in EXPECTED_NAVIGATION_ROUTES:
                continue
            if parsed.path not in seen:
                seen.add(parsed.path)
                pending.append(parsed.path)

    assert EXPECTED_NAVIGATION_ROUTES.issubset(seen)


def test_routed_navigation_has_no_backend_action_links(client):
    forbidden = ("/api/", "fetch(", "XMLHttpRequest", "WebSocket", "<form")
    for route in sorted(EXPECTED_NAVIGATION_ROUTES):
        html = _get_html(client, route)
        for token in forbidden:
            assert token not in html
