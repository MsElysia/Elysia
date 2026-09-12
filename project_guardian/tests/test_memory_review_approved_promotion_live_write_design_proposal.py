# project_guardian/tests/test_memory_review_approved_promotion_live_write_design_proposal.py

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
    / "run_memory_review_approved_promotion_live_write_design_proposal_smoke.py"
)
DESIGN_AUTHORIZATION_PHRASE = "AUTHORIZE_LIVE_WRITE_DESIGN_PROPOSAL_ONLY"
ACCEPTED_CHECKPOINT_TAG = (
    "memory_review_approved_promotion_live_write_design_authorization_gate_clean_1"
)
ACCEPTED_CHECKPOINT_HASH = "a5b4f7ef480bc591fa9ef95d63adc8bf0b64f88a"
REQUIRED_PROPOSAL_CASES = (
    "missing_design_proposal_artifact",
    "invalid_design_authorization_phrase",
    "mismatched_gate_hash",
    "gate_not_pass",
    "proposal_claims_live_write_implementation",
    "proposal_claims_live_memory_write",
    "proposal_claims_vector_db_write",
    "proposal_omits_separate_implementation_campaign",
    "valid_design_proposal_only",
)
INVALID_PROPOSAL_CASES = REQUIRED_PROPOSAL_CASES[:-1]
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
    "live-write design proposal is recorded",
    "live memory writes remain blocked",
    "vector db writes remain blocked",
    "live-write implementation remains blocked",
    "future live-write implementation requires a separate explicit campaign after design approval",
    "separate operator approval is still required for live writes",
)
REQUIRED_SMOKE_FIELDS = {
    "verdict",
    "workspace",
    "proposal_json_path",
    "proposal_json_valid",
    "proposal_report_path",
    "proposal_report_valid_json",
    "proposal_readme_path",
    "proposal_readme_sha256",
    "design_authorization_phrase",
    "design_authorization_phrase_valid",
    "accepted_checkpoint_tag",
    "accepted_checkpoint_hash",
    "source_live_write_design_authorization_gate_sha256",
    "live_write_design_authorization_gate_verdict",
    "authorized_for_live_write_design_proposal",
    "authorized_for_live_write_implementation",
    "authorized_for_live_memory_write",
    "authorized_for_vector_db_write",
    "live_memory_write_allowed",
    "vector_db_write_allowed",
    "live_write_implemented",
    "ready_for_live_write_implementation",
    "requires_separate_live_write_implementation_campaign",
    "requires_separate_operator_approval_for_live_write",
    "proposal_scope",
    "proposal_non_goals",
    "operator_next_steps",
    "proposal_cases",
    "proposal_case_count",
    "all_invalid_proposal_cases_failed_closed",
    "valid_design_proposal_passed_proposal_only",
    "dry_run",
    "local_only",
    "model_called",
    "embeddings_used",
    "live_memory_written",
    "live_vector_db_written",
    "account_api_network_accessed",
    "autonomy_enabled",
    "errors",
}


def _parse_json_payload(text: str) -> dict:
    start = text.find("{")
    if start < 0:
        raise ValueError("no JSON object found")
    return json.loads(text[start:])


def _run_script(*args: str) -> dict:
    result = subprocess.run(
        [sys.executable, str(SCRIPT_PATH), "--json", *args],
        check=False,
        capture_output=True,
        text=True,
    )
    try:
        payload = _parse_json_payload(result.stdout)
    except (ValueError, json.JSONDecodeError) as exc:
        raise AssertionError(
            "design proposal smoke did not emit JSON\n"
            f"returncode={result.returncode}\n"
            f"stdout={result.stdout}\n"
            f"stderr={result.stderr}"
        ) from exc
    if result.returncode != 0 and payload.get("verdict") != "FAIL":
        raise AssertionError(
            "design proposal smoke failed without FAIL verdict\n"
            f"returncode={result.returncode}\n"
            f"stderr={result.stderr}\n"
            f"payload={payload}"
        )
    return payload


@pytest.fixture(scope="module")
def smoke_payload() -> dict:
    base_dir = Path(tempfile.mkdtemp(prefix="elysia_lwdp_t_"))
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


def _assert_writes_unauthorized(payload: dict) -> None:
    assert payload["authorized_for_live_write_implementation"] is False
    assert payload["authorized_for_live_memory_write"] is False
    assert payload["authorized_for_vector_db_write"] is False
    assert payload["live_memory_write_allowed"] is False
    assert payload["vector_db_write_allowed"] is False
    assert payload["live_write_implemented"] is False
    assert payload["ready_for_live_write_implementation"] is False


def _cases(payload: dict) -> dict:
    return {case["case_name"]: case for case in payload["proposal_cases"]}


def test_proposal_script_emits_verdict_pass(smoke_payload):
    assert smoke_payload["verdict"] == "PASS"
    assert smoke_payload["errors"] == []


def test_proposal_json_exists_and_is_valid(smoke_payload):
    path = Path(smoke_payload["proposal_json_path"])
    assert path.is_file()
    loaded = json.loads(path.read_text(encoding="utf-8"))
    assert loaded["design_authorization_phrase"] == DESIGN_AUTHORIZATION_PHRASE
    assert smoke_payload["proposal_json_valid"] is True


def test_proposal_report_json_exists_and_is_valid(smoke_payload):
    path = Path(smoke_payload["proposal_report_path"])
    assert path.is_file()
    loaded = json.loads(path.read_text(encoding="utf-8"))
    assert loaded["verdict"] == "PASS"
    assert smoke_payload["proposal_report_valid_json"] is True
    assert REQUIRED_SMOKE_FIELDS.issubset(loaded)


def test_proposal_readme_exists_and_hash_is_present(smoke_payload):
    path = Path(smoke_payload["proposal_readme_path"])
    assert path.is_file()
    digest = smoke_payload["proposal_readme_sha256"]
    assert isinstance(digest, str) and len(digest) == 64
    assert all(char in "0123456789abcdef" for char in digest)
    text = path.read_text(encoding="utf-8")
    assert DESIGN_AUTHORIZATION_PHRASE in text
    assert "design proposal" in text.lower()


def test_design_phrase_is_recorded_exactly_and_valid(smoke_payload):
    assert smoke_payload["design_authorization_phrase"] == DESIGN_AUTHORIZATION_PHRASE
    assert smoke_payload["design_authorization_phrase_valid"] is True
    proposal = json.loads(Path(smoke_payload["proposal_json_path"]).read_text(encoding="utf-8"))
    assert proposal["design_authorization_phrase"] == DESIGN_AUTHORIZATION_PHRASE


def test_accepted_checkpoint_tag_and_hash_are_recorded_exactly(smoke_payload):
    assert smoke_payload["accepted_checkpoint_tag"] == ACCEPTED_CHECKPOINT_TAG
    assert smoke_payload["accepted_checkpoint_hash"] == ACCEPTED_CHECKPOINT_HASH


def test_source_gate_hash_and_verdict_are_present(smoke_payload):
    digest = smoke_payload["source_live_write_design_authorization_gate_sha256"]
    assert isinstance(digest, str) and len(digest) == 64
    assert all(char in "0123456789abcdef" for char in digest)
    gate_path = Path(smoke_payload["source_live_write_design_authorization_gate_path"])
    assert gate_path.is_file()
    assert smoke_payload["live_write_design_authorization_gate_verdict"] == "PASS"


def test_missing_design_proposal_artifact_fails_closed(smoke_payload):
    case = _cases(smoke_payload)["missing_design_proposal_artifact"]
    assert case["expected_verdict"] == "FAIL"
    assert case["actual_verdict"] == "FAIL"
    assert case["detected"] is True
    assert case["details"]["authorized_for_live_write_design_proposal"] is False
    assert any(
        "missing_design_proposal_artifact" in error for error in case["details"]["errors"]
    )
    assert not Path(smoke_payload["artifact_paths"]["missing_design_proposal_artifact"]).exists()


def test_invalid_design_phrase_fails_closed(smoke_payload):
    case = _cases(smoke_payload)["invalid_design_authorization_phrase"]
    assert case["actual_verdict"] == "FAIL"
    assert case["detected"] is True
    assert any(
        "invalid_design_authorization_phrase" in error for error in case["details"]["errors"]
    )


def test_mismatched_gate_hash_fails_closed(smoke_payload):
    case = _cases(smoke_payload)["mismatched_gate_hash"]
    assert case["actual_verdict"] == "FAIL"
    assert case["detected"] is True
    assert any("mismatched_gate_hash" in error for error in case["details"]["errors"])


def test_gate_not_pass_fails_closed(smoke_payload):
    case = _cases(smoke_payload)["gate_not_pass"]
    assert case["actual_verdict"] == "FAIL"
    assert case["detected"] is True
    assert any("gate_not_pass" in error for error in case["details"]["errors"])


def test_proposal_claiming_live_write_implementation_fails_closed(smoke_payload):
    case = _cases(smoke_payload)["proposal_claims_live_write_implementation"]
    assert case["actual_verdict"] == "FAIL"
    assert case["detected"] is True
    assert case["details"]["authorized_for_live_write_implementation"] is False
    assert any(
        "proposal_claims_live_write_implementation" in error
        for error in case["details"]["errors"]
    )


def test_proposal_claiming_live_memory_write_fails_closed(smoke_payload):
    case = _cases(smoke_payload)["proposal_claims_live_memory_write"]
    assert case["actual_verdict"] == "FAIL"
    assert case["detected"] is True
    assert case["details"]["authorized_for_live_memory_write"] is False
    assert any(
        "proposal_claims_live_memory_write" in error for error in case["details"]["errors"]
    )


def test_proposal_claiming_vector_db_write_fails_closed(smoke_payload):
    case = _cases(smoke_payload)["proposal_claims_vector_db_write"]
    assert case["actual_verdict"] == "FAIL"
    assert case["detected"] is True
    assert case["details"]["authorized_for_vector_db_write"] is False
    assert any(
        "proposal_claims_vector_db_write" in error for error in case["details"]["errors"]
    )


def test_proposal_omitting_separate_implementation_campaign_fails_closed(smoke_payload):
    case = _cases(smoke_payload)["proposal_omits_separate_implementation_campaign"]
    assert case["actual_verdict"] == "FAIL"
    assert case["detected"] is True
    assert any(
        "proposal_omits_separate_implementation_campaign" in error
        for error in case["details"]["errors"]
    )


def test_valid_design_proposal_passes_proposal_only(smoke_payload):
    case = _cases(smoke_payload)["valid_design_proposal_only"]
    assert case["expected_verdict"] == "PASS"
    assert case["actual_verdict"] == "PASS"
    assert case["detected"] is True
    assert case["details"]["authorized_for_live_write_design_proposal"] is True
    assert case["details"]["authorized_for_live_write_implementation"] is False
    assert case["details"]["authorized_for_live_memory_write"] is False
    assert case["details"]["authorized_for_vector_db_write"] is False
    assert case["details"]["live_memory_write_allowed"] is False
    assert case["details"]["vector_db_write_allowed"] is False
    assert case["details"]["live_write_implemented"] is False
    assert case["details"]["ready_for_live_write_implementation"] is False
    assert case["details"]["errors"] == []
    assert smoke_payload["valid_design_proposal_passed_proposal_only"] is True
    assert smoke_payload["authorized_for_live_write_design_proposal"] is True


def test_valid_proposal_does_not_authorize_implementation_or_writes(smoke_payload):
    case = _cases(smoke_payload)["valid_design_proposal_only"]
    assert case["details"]["authorized_for_live_write_implementation"] is False
    assert case["details"]["authorized_for_live_memory_write"] is False
    assert case["details"]["authorized_for_vector_db_write"] is False
    _assert_writes_unauthorized(smoke_payload)


def test_authorized_for_live_write_implementation_false_for_every_case(smoke_payload):
    for case in smoke_payload["proposal_cases"]:
        assert case["details"]["authorized_for_live_write_implementation"] is False
    assert smoke_payload["authorized_for_live_write_implementation"] is False


def test_authorized_for_live_memory_write_false_for_every_case(smoke_payload):
    for case in smoke_payload["proposal_cases"]:
        assert case["details"]["authorized_for_live_memory_write"] is False
    assert smoke_payload["authorized_for_live_memory_write"] is False


def test_authorized_for_vector_db_write_false_for_every_case(smoke_payload):
    for case in smoke_payload["proposal_cases"]:
        assert case["details"]["authorized_for_vector_db_write"] is False
    assert smoke_payload["authorized_for_vector_db_write"] is False


def test_live_write_implemented_false_for_every_case(smoke_payload):
    for case in smoke_payload["proposal_cases"]:
        assert case["details"]["live_write_implemented"] is False
    assert smoke_payload["live_write_implemented"] is False


def test_invalid_cases_keep_design_false_except_valid(smoke_payload):
    cases = _cases(smoke_payload)
    for name in INVALID_PROPOSAL_CASES:
        details = cases[name]["details"]
        assert details["authorized_for_live_write_design_proposal"] is False
        assert details["authorized_for_live_write_implementation"] is False
        assert details["authorized_for_live_memory_write"] is False
        assert details["authorized_for_vector_db_write"] is False
        assert details["live_memory_write_allowed"] is False
        assert details["vector_db_write_allowed"] is False


def test_requires_separate_implementation_and_operator_approval(smoke_payload):
    assert smoke_payload["requires_separate_live_write_implementation_campaign"] is True
    assert smoke_payload["requires_separate_operator_approval_for_live_write"] is True
    assert smoke_payload["dry_run"] is True
    assert smoke_payload["local_only"] is True
    joined = " ".join(smoke_payload["operator_next_steps"]).lower()
    for marker in OPERATOR_NEXT_STEP_MARKERS:
        assert marker in joined
    assert smoke_payload["proposal_scope"]
    assert smoke_payload["proposal_non_goals"]


def test_json_report_contains_required_pass_contract(smoke_payload):
    assert REQUIRED_SMOKE_FIELDS.issubset(smoke_payload)
    assert smoke_payload["verdict"] == "PASS"
    names = [case["case_name"] for case in smoke_payload["proposal_cases"]]
    assert names == list(REQUIRED_PROPOSAL_CASES)
    assert smoke_payload["proposal_case_count"] == len(REQUIRED_PROPOSAL_CASES)
    assert smoke_payload["all_invalid_proposal_cases_failed_closed"] is True
    assert smoke_payload["valid_design_proposal_passed_proposal_only"] is True
    _assert_safety_flags_false(smoke_payload)
    _assert_writes_unauthorized(smoke_payload)


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
    payload = _parse_json_payload(result.stdout)
    assert payload["verdict"] == "FAIL"
    assert "repository root" in payload["errors"][0]
