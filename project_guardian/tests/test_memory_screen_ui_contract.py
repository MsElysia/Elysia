# project_guardian/tests/test_memory_screen_ui_contract.py

from __future__ import annotations

import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
CONTRACT_PATH = REPO_ROOT / "docs" / "MEMORY_SCREEN_UI_CONTRACT.json"
FOUNDATION_PATH = REPO_ROOT / "docs" / "MEMORY_SCREEN_UI_FOUNDATION.md"
PROTOTYPE_PATH = REPO_ROOT / "project_guardian" / "ui" / "static" / "memory_import_screen.html"

REQUIRED_SAFETY_TEXT = [
    "No memory is saved until you confirm.",
    "Imported items become pending memories for review.",
    "Approved memories can be searched later.",
    "Elysia does not connect to your email or ChatGPT account for this import.",
    "Only local files you choose are used.",
]

REQUIRED_SOURCE_TYPES = ("transcription", "chatgpt_export", "email_export")

SAFETY_FLAGS = (
    "model_called",
    "embeddings_used",
    "live_memory_written",
    "autonomy_enabled",
)


@pytest.fixture
def contract() -> dict:
    assert CONTRACT_PATH.is_file(), f"Missing contract: {CONTRACT_PATH}"
    return json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))


def test_contract_file_exists():
    assert CONTRACT_PATH.is_file()


def test_foundation_doc_exists():
    assert FOUNDATION_PATH.is_file()


def test_static_prototype_exists():
    assert PROTOTYPE_PATH.is_file()


def test_preview_request_and_response_sections(contract):
    assert contract["preview_request"]["action"] == "preview"
    assert "dest_dir" in contract["preview_request"]["fields"]
    assert "inputs" in contract["preview_request"]["fields"]
    assert "source_type" in contract["preview_request"]["fields"]
    assert "recursive" in contract["preview_request"]["fields"]
    assert "memory_import.py preview" in contract["preview_request"]["expected_backend_command"]

    preview_resp = contract["preview_response"]["fields"]
    for key in (
        "source_type",
        "session_json",
        "session_markdown",
        "files_seen",
        "supported_now_count",
        "supported_later_count",
        "skipped_count",
        *SAFETY_FLAGS,
    ):
        assert key in preview_resp


def test_apply_request_and_response_sections(contract):
    assert contract["apply_request"]["action"] == "apply"
    assert "session_json" in contract["apply_request"]["fields"]
    assert "apply" in contract["apply_request"]["fields"]
    assert "memory_import.py apply" in contract["apply_request"]["expected_backend_command_apply"]

    apply_resp = contract["apply_response"]["fields"]
    for key in (
        "source_type",
        "dry_run",
        "candidates_staged",
        "apply_report_json",
        *SAFETY_FLAGS,
    ):
        assert key in apply_resp


@pytest.mark.parametrize("source_type", REQUIRED_SOURCE_TYPES)
def test_all_source_types_represented(contract, source_type):
    assert source_type in contract["supported_source_types"]
    enum = contract["preview_request"]["fields"]["source_type"]["enum"]
    assert source_type in enum


def test_safety_flags_are_false_in_contract(contract):
    for section in ("preview_response", "apply_response"):
        fields = contract[section]["fields"]
        for flag in SAFETY_FLAGS:
            assert fields[flag]["const"] is False


def test_user_facing_safety_text(contract):
    for phrase in REQUIRED_SAFETY_TEXT:
        assert phrase in contract["user_facing_safety_text"]


def test_user_facing_text_in_foundation_doc():
    text = FOUNDATION_PATH.read_text(encoding="utf-8")
    for phrase in REQUIRED_SAFETY_TEXT:
        assert phrase in text


def test_user_facing_text_in_static_prototype():
    html = PROTOTYPE_PATH.read_text(encoding="utf-8")
    for phrase in REQUIRED_SAFETY_TEXT:
        assert phrase in html


def test_no_server_route_requirement(contract):
    assert contract["server_routes_required"] is False
    assert contract["safety_guarantees"]["no_server_api_routes_in_this_milestone"] is True


def test_no_live_account_access_language(contract):
    assert contract["live_account_access"] is False
    assert contract["safety_guarantees"]["no_live_account_access"] is True
    assert any("ChatGPT" in s for s in contract["user_facing_safety_text"])
    assert any("email" in s.lower() for s in contract["user_facing_safety_text"])


def test_review_and_search_future_sections(contract):
    assert "review_future" in contract
    assert "search_approved_future" in contract
    assert "context_bundle_future" in contract
    assert contract["review_future"]["status"] == "not_wired_in_this_milestone"


def test_prototype_declares_not_wired():
    html = PROTOTYPE_PATH.read_text(encoding="utf-8")
    assert "not connected" in html.lower() or "prototype" in html.lower()
    assert "memory_import.py preview" in html
