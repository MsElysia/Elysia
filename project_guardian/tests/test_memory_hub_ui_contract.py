# project_guardian/tests/test_memory_hub_ui_contract.py

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
CONTRACT_PATH = REPO_ROOT / "docs" / "MEMORY_HUB_UI_CONTRACT.json"
FOUNDATION_PATH = REPO_ROOT / "docs" / "MEMORY_HUB_UI_FOUNDATION.md"
PROTOTYPE_PATH = REPO_ROOT / "project_guardian" / "ui" / "static" / "memory_hub.html"

REQUIRED_SAFETY_TEXT = [
    "Use local files to build memory safely.",
    "No memory is saved until you confirm.",
    "Imported items become pending memories for review.",
    "Only approved memories are searchable.",
]

REQUIRED_SOURCE_TYPES = ("transcription", "chatgpt_export", "email_export")

REQUIRED_USER_FLOW = (
    "import_memory",
    "preview",
    "confirm_import",
    "review_pending",
    "approve_reject_edit",
    "search_approved",
    "build_context_bundle",
)

SAFETY_FLAGS = (
    "model_called",
    "embeddings_used",
    "live_memory_written",
    "autonomy_enabled",
)

LINKED_PAGES = ("memory_import_screen.html", "memory_review_search.html")

FORBIDDEN_NETWORK_JS = ("fetch(", "XMLHttpRequest", "WebSocket")

EXTERNAL_ASSET_PATTERN = re.compile(
    r'(?:src|href|action)\s*=\s*["\']https?://',
    re.IGNORECASE,
)


@pytest.fixture
def contract() -> dict:
    assert CONTRACT_PATH.is_file(), f"Missing contract: {CONTRACT_PATH}"
    return json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))


@pytest.fixture
def html() -> str:
    assert PROTOTYPE_PATH.is_file(), f"Missing prototype: {PROTOTYPE_PATH}"
    return PROTOTYPE_PATH.read_text(encoding="utf-8")


def test_static_prototype_exists():
    assert PROTOTYPE_PATH.is_file()


def test_contract_exists():
    assert CONTRACT_PATH.is_file()


def test_prototype_only_true(contract):
    assert contract["prototype_only"] is True


def test_server_routes_required_false(contract):
    assert contract["server_routes_required"] is False


def test_backend_calls_allowed_false(contract):
    assert contract["backend_calls_allowed"] is False


def test_external_network_allowed_false(contract):
    assert contract["external_network_allowed"] is False


@pytest.mark.parametrize("source_type", REQUIRED_SOURCE_TYPES)
def test_all_source_types_represented(contract, source_type):
    assert source_type in contract["source_types"]


@pytest.mark.parametrize("page", LINKED_PAGES)
def test_linked_static_pages(contract, page):
    assert page in contract["linked_static_pages"]


@pytest.mark.parametrize("step", REQUIRED_USER_FLOW)
def test_user_flow_includes_steps(contract, step):
    assert step in contract["user_flow"]


def test_safety_flags_false(contract):
    flags = contract["safety_flags"]
    for flag in SAFETY_FLAGS:
        assert flags[flag] is False


def test_static_html_contains_safety_copy(html):
    for phrase in REQUIRED_SAFETY_TEXT:
        assert phrase in html


def test_static_html_links_to_prototypes(html):
    for page in LINKED_PAGES:
        assert page in html


def test_no_network_js_in_html(html):
    lower = html.lower()
    assert "<script" not in lower
    for token in FORBIDDEN_NETWORK_JS:
        assert token not in html


def test_no_external_network_assets_in_html(html):
    assert not EXTERNAL_ASSET_PATTERN.search(html)


def test_no_server_route_requirement(contract):
    assert contract["server_routes_required"] is False
    assert contract["backend_calls_allowed"] is False


def test_foundation_doc_exists():
    assert FOUNDATION_PATH.is_file()


def test_hub_page_name(contract):
    assert contract["page_name"] == "memory_hub"


def test_live_account_language_in_html(html):
    assert "no live account access" in html.lower() or "no live chatgpt" in html.lower()
