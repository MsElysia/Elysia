# project_guardian/tests/test_memory_review_approved_promotion_final_dry_run_acceptance_receipt.py

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = (
    REPO_ROOT
    / "scripts"
    / "run_memory_review_approved_promotion_final_dry_run_acceptance_receipt_smoke.py"
)
ACCEPTANCE_PHRASE = "ACCEPT_FINAL_DRY_RUN_READINESS_PACKET_ONLY"
ACCEPTED_CHECKPOINT_TAG = (
    "memory_review_approved_promotion_final_readiness_operator_acceptance_gate_tamper_evidence_clean_1"
)
ACCEPTED_CHECKPOINT_HASH = "a6ceaf4d944751c665ecbdc32a6d4c9d0c862949"
REQUIRED_SOURCE_HASH_FIELDS = (
    "source_final_readiness_packet_sha256",
    "source_final_readiness_packet_tamper_evidence_sha256",
    "source_operator_acceptance_gate_sha256",
    "source_operator_acceptance_gate_tamper_evidence_sha256",
)
OPERATOR_NEXT_STEP_MARKERS = (
    "final dry-run readiness is accepted",
    "live memory writes remain blocked",
    "vector db writes remain blocked",
    "future live-write design requires a separate explicit campaign",
    "future live-write implementation requires a separate explicit campaign after design approval",
)
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


def _run_script(*args: str) -> dict:
    result = subprocess.run(
        [sys.executable, str(SCRIPT_PATH), "--json", *args],
        check=False,
        capture_output=True,
        text=True,
    )
    start = result.stdout.find("{")
    if start < 0:
        raise AssertionError(
            "acceptance receipt smoke did not emit JSON\n"
            f"returncode={result.returncode}\nstdout={result.stdout}\nstderr={result.stderr}"
        )
    payload = json.loads(result.stdout[start:])
    if result.returncode != 0 and payload.get("verdict") != "FAIL":
        raise AssertionError(
            "acceptance receipt smoke failed without FAIL verdict\n"
            f"returncode={result.returncode}\nstderr={result.stderr}"
        )
    return payload


@pytest.fixture(scope="module")
def smoke_payload() -> dict:
    base_dir = Path(tempfile.mkdtemp(prefix="elysia_fdrar_t_"))
    try:
        payload = _run_script("--base-dir", str(base_dir), "--keep-temp")
        yield payload
    finally:
        shutil.rmtree(base_dir, ignore_errors=True)


def _assert_safety_flags_false(payload: dict) -> None:
    assert payload["model_called"] is False
    assert payload["embeddings_used"] is False
    assert payload["live_memory_written"] is False
    assert payload["live_vector_db_written"] is False
    assert payload["account_api_network_accessed"] is False
    assert payload["autonomy_enabled"] is False


def test_receipt_script_emits_verdict_pass(smoke_payload):
    assert smoke_payload["verdict"] == "PASS"
    assert smoke_payload["errors"] == []


def test_receipt_json_exists_and_is_valid(smoke_payload):
    path = Path(smoke_payload["receipt_json_path"])
    assert path.is_file()
    loaded = json.loads(path.read_text(encoding="utf-8"))
    assert loaded["verdict"] == "PASS"
    assert smoke_payload["receipt_json_valid"] is True


def test_receipt_readme_exists_and_hash_is_present(smoke_payload):
    path = Path(smoke_payload["receipt_readme_path"])
    assert path.is_file()
    digest = smoke_payload["receipt_readme_sha256"]
    assert isinstance(digest, str)
    assert len(digest) == 64
    assert all(char in "0123456789abcdef" for char in digest)
    assert ACCEPTANCE_PHRASE in path.read_text(encoding="utf-8")


def test_operator_phrase_is_recorded_exactly_and_valid(smoke_payload):
    assert smoke_payload["operator_acceptance_phrase"] == ACCEPTANCE_PHRASE
    assert smoke_payload["operator_acceptance_phrase_valid"] is True


def test_accepted_checkpoint_tag_and_hash_are_recorded_exactly(smoke_payload):
    assert smoke_payload["accepted_checkpoint_tag"] == ACCEPTED_CHECKPOINT_TAG
    assert smoke_payload["accepted_checkpoint_hash"] == ACCEPTED_CHECKPOINT_HASH


def test_source_hashes_are_present(smoke_payload):
    for field_name in REQUIRED_SOURCE_HASH_FIELDS:
        value = smoke_payload[field_name]
        assert isinstance(value, str)
        assert len(value) == 64
        assert all(char in "0123456789abcdef" for char in value)


def test_prior_chain_verdicts_are_pass(smoke_payload):
    assert smoke_payload["final_readiness_packet_verdict"] == "PASS"
    assert smoke_payload["final_readiness_packet_tamper_evidence_verdict"] == "PASS"
    assert smoke_payload["operator_acceptance_gate_verdict"] == "PASS"
    assert smoke_payload["operator_acceptance_gate_tamper_evidence_verdict"] == "PASS"


def test_authorization_flags_remain_dry_run_only(smoke_payload):
    assert smoke_payload["accepted_for_final_dry_run_readiness"] is True
    assert smoke_payload["accepted_for_live_memory_write"] is False
    assert smoke_payload["accepted_for_vector_db_write"] is False
    assert smoke_payload["ready_for_future_live_write_design"] is False
    assert smoke_payload["requires_separate_live_write_campaign"] is True
    assert smoke_payload["requires_separate_operator_approval_for_live_write"] is True
    assert smoke_payload["live_memory_write_allowed"] is False
    assert smoke_payload["vector_db_write_allowed"] is False


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


def test_no_live_runtime_memory_or_vector_db_path_is_written(smoke_payload):
    workspace = Path(smoke_payload["workspace"])
    assert workspace.is_dir()
    assert "forbidden_live_writes" not in smoke_payload
    assert not (workspace / "forbidden_live_writes").exists()
    assert list(workspace.rglob("runtime_memory.jsonl")) == []
    assert list(workspace.rglob("vector_db.index")) == []
    assert "forbidden_live_writes" not in json.dumps(smoke_payload)


def test_script_has_no_network_ui_or_route_behavior():
    script = SCRIPT_PATH.read_text(encoding="utf-8")
    for token in FORBIDDEN_SCRIPT_TOKENS:
        assert token not in script


def test_script_refuses_repository_root_workspace():
    result = subprocess.run(
        [sys.executable, str(SCRIPT_PATH), "--json", "--base-dir", str(REPO_ROOT)],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1
    start = result.stdout.find("{")
    payload = json.loads(result.stdout[start:])
    assert payload["verdict"] == "FAIL"
    assert "repository root" in payload["errors"][0]
