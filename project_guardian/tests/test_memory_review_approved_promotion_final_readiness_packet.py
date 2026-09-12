# project_guardian/tests/test_memory_review_approved_promotion_final_readiness_packet.py

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = (
    REPO_ROOT
    / "scripts"
    / "run_memory_review_approved_promotion_final_readiness_packet_smoke.py"
)
REQUIRED_SAFETY_CHAIN_STAGES = (
    "promotion_bundle",
    "promotion_tamper_evidence",
    "operator_handoff",
    "operator_approval_gate",
    "operator_approved_staging",
    "staging_tamper_evidence",
    "live_write_blockade",
    "live_write_blockade_tamper_evidence",
)
REQUIRED_SOURCE_HASH_FIELDS = (
    "source_bundle_sha256",
    "source_promotion_manifest_sha256",
    "source_operator_handoff_sha256",
    "source_approval_gate_sha256",
    "source_staging_manifest_sha256",
    "source_staging_tamper_evidence_sha256",
    "source_live_write_blockade_sha256",
    "source_live_write_blockade_tamper_evidence_sha256",
)
EDITED_TEXT_MARKER = "Edited approved memory"
APPROVAL_TOKEN_PHRASE = "APPROVE_DRY_RUN_MEMORY_PROMOTION_STAGING_ONLY"
FORBIDDEN_SCRIPT_TOKENS = (
    "fetch(",
    "XMLHttpRequest",
    "WebSocket",
    "requests.",
    "urllib.",
    "socket.",
    "http://",
    "https://",
    "@app.",
    "FastAPI",
    "Flask",
    "route(",
)
OPERATOR_NEXT_STEP_MARKERS = (
    "final dry-run readiness only",
    "does not authorize live memory writes",
    "does not authorize vector db writes",
    "separate explicit future milestone",
)


def _run_script(*args: str) -> dict:
    result = subprocess.run(
        [sys.executable, str(SCRIPT_PATH), "--json", *args],
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(result.stdout)


@pytest.fixture(scope="module")
def smoke_payload() -> dict:
    return _run_script()


def _assert_safety_flags_false(payload: dict) -> None:
    assert payload["model_called"] is False
    assert payload["embeddings_used"] is False
    assert payload["live_memory_written"] is False
    assert payload["live_vector_db_written"] is False
    assert payload["account_api_network_accessed"] is False
    assert payload["autonomy_enabled"] is False


def test_final_packet_script_emits_verdict_pass(smoke_payload):
    assert smoke_payload["verdict"] == "PASS"
    assert smoke_payload["errors"] == []


def test_packet_json_exists_and_is_valid(smoke_payload):
    if smoke_payload.get("workspace_preserved"):
        path = Path(smoke_payload["packet_json_path"])
        assert path.is_file()
        loaded = json.loads(path.read_text(encoding="utf-8"))
        assert loaded["verdict"] == "PASS"
    assert smoke_payload["packet_json_valid"] is True
    assert smoke_payload["packet_json_path"]


def test_packet_readme_exists_and_hash_is_present(smoke_payload):
    assert smoke_payload["packet_readme_path"]
    assert len(smoke_payload["packet_readme_sha256"]) == 64
    if smoke_payload.get("workspace_preserved"):
        assert Path(smoke_payload["packet_readme_path"]).is_file()


def test_all_source_hashes_are_present(smoke_payload):
    for field_name in REQUIRED_SOURCE_HASH_FIELDS:
        value = smoke_payload[field_name]
        assert isinstance(value, str)
        assert len(value) == 64
        assert all(char in "0123456789abcdef" for char in value)


def test_approval_token_phrase_is_present(smoke_payload):
    assert smoke_payload["approval_token_phrase"] == APPROVAL_TOKEN_PHRASE


def test_approved_and_edited_items_included_rejected_excluded(smoke_payload):
    items = smoke_payload["approved_items"]
    types = [item["decision_type"] for item in items]
    texts = [item["promoted_text"] for item in items]
    assert "approved" in types
    assert "edited" in types
    assert any(EDITED_TEXT_MARKER in text for text in texts)
    assert "rejected" not in types
    assert smoke_payload["promotion_item_count"] == 2
    assert smoke_payload["excluded_rejected_count"] == 1


def test_safety_chain_contains_all_required_pass_stages(smoke_payload):
    chain = smoke_payload["safety_chain"]
    for stage in REQUIRED_SAFETY_CHAIN_STAGES:
        assert stage in chain
        assert chain[stage] == "PASS"


def test_readiness_flags_remain_blocked_for_live_writes(smoke_payload):
    assert smoke_payload["ready_for_operator_review"] is True
    assert smoke_payload["ready_for_operator_approved_staging"] is True
    assert smoke_payload["ready_for_live_memory_write"] is False
    assert smoke_payload["future_live_write_allowed"] is False
    assert smoke_payload["requires_explicit_operator_approval"] is True
    assert smoke_payload["requires_future_live_write_milestone"] is True


def test_blocked_reasons_and_next_steps_present(smoke_payload):
    assert smoke_payload["live_write_blocked_reason"]
    assert smoke_payload["vector_db_write_blocked_reason"]
    joined = " ".join(smoke_payload["operator_next_steps"]).lower()
    for marker in OPERATOR_NEXT_STEP_MARKERS:
        assert marker in joined


def test_safety_flags_are_false(smoke_payload):
    _assert_safety_flags_false(smoke_payload)
    assert smoke_payload["dry_run"] is True
    assert smoke_payload["local_only"] is True


def test_script_has_no_network_or_ui_tokens():
    source = SCRIPT_PATH.read_text(encoding="utf-8")
    for token in FORBIDDEN_SCRIPT_TOKENS:
        assert token not in source


def test_script_refuses_repository_root_as_base_dir():
    result = subprocess.run(
        [sys.executable, str(SCRIPT_PATH), "--json", "--base-dir", str(REPO_ROOT)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0
    payload = json.loads(result.stdout)
    assert payload["verdict"] == "FAIL"
    assert any("repository root" in error for error in payload["errors"])
