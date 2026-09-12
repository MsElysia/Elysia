# project_guardian/tests/test_memory_review_search_ui_contract.py

from __future__ import annotations

import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
CONTRACT_PATH = REPO_ROOT / "docs" / "MEMORY_REVIEW_SEARCH_UI_CONTRACT.json"
FOUNDATION_PATH = REPO_ROOT / "docs" / "MEMORY_REVIEW_SEARCH_UI_FOUNDATION.md"
PROTOTYPE_PATH = REPO_ROOT / "project_guardian" / "ui" / "static" / "memory_review_search.html"

REQUIRED_SAFETY_TEXT = [
    "Pending memories are not active memory yet.",
    "Only approved memories are used for search/context.",
    "Review actions are operator controlled.",
    "No model is called during review.",
    "No live account access is used.",
    "No memory is written to live runtime memory or vector DB.",
]

REQUIRED_SOURCE_TYPES = ("transcription", "chatgpt_export", "email_export")

SAFETY_FLAGS = (
    "model_called",
    "embeddings_used",
    "live_memory_written",
    "autonomy_enabled",
)

REVIEW_ACTIONS = ("approve_candidate", "reject_candidate", "edit_candidate")


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


def test_pending_candidates_list_section(contract):
    section = contract["pending_candidates_list_request"]
    assert section["action"] == "list_pending_candidates"
    assert "dest_dir" in section["fields"]
    assert "filters" in section["fields"]
    assert section["read_only"] is True
    assert "review_memory_candidates.py" in section["expected_backend_command"]

    resp = contract["pending_candidates_list_response"]["fields"]
    assert "candidates" in resp
    assert "counts" in resp
    for flag in SAFETY_FLAGS:
        assert resp[flag]["const"] is False


def test_review_decision_actions(contract):
    req = contract["review_decision_request"]
    for action in REVIEW_ACTIONS:
        assert action in req["actions"]
        assert action in req["expected_backend_commands"]
    assert req["requires_operator_confirm"] is True
    assert "candidate_id" in req["fields"]
    assert "operator_note" in req["fields"]
    assert "edited_text" in req["fields"]

    resp = contract["review_decision_response"]["fields"]
    for key in ("decision_written", "decision_path", "candidate_id", "new_status", *SAFETY_FLAGS):
        assert key in resp
    for flag in SAFETY_FLAGS:
        assert resp[flag]["const"] is False


def test_approved_memory_search_section(contract):
    req = contract["approved_memory_search_request"]
    assert req["action"] == "search_approved_memory"
    assert req["read_only"] is True
    assert "query" in req["fields"]
    assert "limit" in req["fields"]
    assert "search_approved_memory_store.py" in req["expected_backend_command"]

    resp = contract["approved_memory_search_response"]["fields"]
    assert "results" in resp
    assert "result_count" in resp
    for flag in SAFETY_FLAGS:
        assert resp[flag]["const"] is False


def test_context_bundle_section(contract):
    req = contract["context_bundle_request"]
    assert req["action"] == "build_context_bundle"
    assert req["requires_operator_confirm"] is True
    assert "query" in req["fields"]
    assert "limit" in req["fields"]
    assert "max_chars" in req["fields"]
    assert "build_approved_memory_context.py" in req["expected_backend_command"]

    resp = contract["context_bundle_response"]["fields"]
    for key in ("context_bundle_markdown", "context_bundle_json", "result_count", *SAFETY_FLAGS):
        assert key in resp
    for flag in SAFETY_FLAGS:
        assert resp[flag]["const"] is False


@pytest.mark.parametrize("source_type", REQUIRED_SOURCE_TYPES)
def test_all_source_types_represented(contract, source_type):
    assert source_type in contract["supported_source_types"]
    enum = contract["pending_candidates_list_request"]["fields"]["filters"]["properties"]["source_type"]["enum"]
    assert source_type in enum
    search_enum = contract["approved_memory_search_request"]["fields"]["source_type"]["enum"]
    assert source_type in search_enum


def test_data_sources_present(contract):
    sources = contract["data_sources"]
    for key in (
        "review_queue_path",
        "review_decisions_path",
        "approved_memory_export_path",
        "approved_memory_store_path",
        "context_bundle_path",
    ):
        assert key in sources


def test_safety_flags_are_false_in_contract(contract):
    for section in (
        "pending_candidates_list_response",
        "review_decision_response",
        "approved_memory_search_response",
        "context_bundle_response",
    ):
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
    assert any("live account" in s.lower() for s in contract["user_facing_safety_text"])


def test_review_requires_operator_confirmation(contract):
    assert contract["review_decision_request"]["requires_operator_confirm"] is True
    assert contract["safety_guarantees"]["review_requires_operator_confirm"] is True


def test_search_is_read_only(contract):
    assert contract["approved_memory_search_request"]["read_only"] is True
    assert contract["safety_guarantees"]["search_is_read_only"] is True


def test_context_bundle_requires_operator_confirmation(contract):
    assert contract["context_bundle_request"]["requires_operator_confirm"] is True
    assert contract["safety_guarantees"]["context_bundle_requires_operator_confirm"] is True


def test_prototype_declares_not_wired():
    html = PROTOTYPE_PATH.read_text(encoding="utf-8")
    assert "not connected" in html.lower() or "prototype" in html.lower()
    assert "review_memory_candidates.py" in html
    assert "search_approved_memory_store.py" in html
