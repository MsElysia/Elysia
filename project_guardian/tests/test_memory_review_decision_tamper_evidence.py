# project_guardian/tests/test_memory_review_decision_tamper_evidence.py

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts" / "run_memory_review_decision_tamper_evidence_smoke.py"


def _load_smoke_module():
    module_name = "run_memory_review_decision_tamper_evidence_smoke"
    spec = importlib.util.spec_from_file_location(module_name, SCRIPT_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


SMOKE = _load_smoke_module()


def _run_script(*args: str) -> dict:
    result = subprocess.run(
        [sys.executable, str(SCRIPT_PATH), "--json", *args],
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(result.stdout)


def _assert_safety_flags_false(payload: dict) -> None:
    assert payload["model_called"] is False
    assert payload["embeddings_used"] is False
    assert payload["live_memory_written"] is False
    assert payload["live_vector_db_written"] is False
    assert payload["account_api_network_accessed"] is False
    assert payload["autonomy_enabled"] is False


def _valid_entry(**overrides: Any) -> Dict[str, Any]:
    entry = {
        "decision_id": "0123456789abcdef0123456789abcdef",
        "candidate_id": "aaaaaaaaaaaaaaaaaaaaaaaa",
        "previous_status": "pending",
        "new_status": "approved",
        "decided_at": "2026-01-01T00:00:00+00:00",
        "operator_required": True,
        "live_memory_written": False,
        "source_queue_path": "review_queue.jsonl",
    }
    entry.update(overrides)
    return entry


def _write_log(path: Path, *json_entries: Dict[str, Any], raw_lines=()) -> Path:
    lines = [json.dumps(entry, ensure_ascii=False) for entry in json_entries]
    lines.extend(raw_lines)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    return path


# --- Overall smoke (subprocess) --------------------------------------------


def test_tamper_smoke_json_cli_passes():
    payload = _run_script()

    assert payload["verdict"] == "PASS"
    assert payload["clean_log_verdict"] == "PASS"
    assert payload["clean_log_still_passes"] is True
    assert payload["tampered_cases_run"] == 5

    assert payload["malformed_json_detected"] is True
    assert payload["missing_field_detected"] is True
    assert payload["non_chronological_detected"] is True
    assert payload["unknown_candidate_detected"] is True
    assert payload["unsupported_transition_detected"] is True
    assert payload["specific_errors_present"] is True
    assert payload["errors"] == []
    _assert_safety_flags_false(payload)


def test_tamper_json_contract_fields_present():
    payload = _run_script()
    required_fields = {
        "verdict",
        "workspace",
        "clean_log_verdict",
        "tampered_cases_run",
        "malformed_json_detected",
        "missing_field_detected",
        "non_chronological_detected",
        "unknown_candidate_detected",
        "unsupported_transition_detected",
        "specific_errors_present",
        "clean_log_still_passes",
        "model_called",
        "embeddings_used",
        "live_memory_written",
        "live_vector_db_written",
        "account_api_network_accessed",
        "autonomy_enabled",
        "errors",
    }
    assert required_fields.issubset(payload)
    _assert_safety_flags_false(payload)


def test_tamper_each_case_returns_fail_with_specific_token():
    payload = _run_script()
    cases = {case["name"]: case for case in payload["cases"]}
    for name in (
        "malformed_json",
        "missing_field",
        "non_chronological",
        "unknown_candidate",
        "unsupported_transition",
    ):
        assert cases[name]["verdict"] == "FAIL"
        assert cases[name]["token_found"] is True
        assert any(cases[name]["expected_token"] in err for err in cases[name]["errors"])


# --- Direct checker (unit) --------------------------------------------------


def test_checker_clean_log_passes(tmp_path):
    log = _write_log(
        tmp_path / "clean.jsonl",
        _valid_entry(candidate_id="aaaaaaaaaaaaaaaaaaaaaaaa"),
        _valid_entry(
            candidate_id="bbbbbbbbbbbbbbbbbbbbbbbb",
            new_status="rejected",
            decided_at="2026-01-01T00:00:01+00:00",
        ),
    )
    verdict, errors = SMOKE.audit_decision_log(log)
    assert verdict == "PASS"
    assert errors == []


def test_checker_detects_malformed_json(tmp_path):
    log = _write_log(
        tmp_path / "malformed.jsonl",
        _valid_entry(),
        raw_lines=["{ not valid json"],
    )
    verdict, errors = SMOKE.audit_decision_log(log)
    assert verdict == "FAIL"
    assert any("malformed_json" in err for err in errors)


def test_checker_detects_missing_required_field(tmp_path):
    bad = _valid_entry()
    bad.pop("new_status")
    log = _write_log(tmp_path / "missing.jsonl", _valid_entry(), bad)
    verdict, errors = SMOKE.audit_decision_log(log)
    assert verdict == "FAIL"
    assert any("missing_required_field" in err for err in errors)


def test_checker_detects_non_chronological(tmp_path):
    log = _write_log(
        tmp_path / "nonchrono.jsonl",
        _valid_entry(decided_at="2026-06-01T00:00:00+00:00"),
        _valid_entry(
            candidate_id="bbbbbbbbbbbbbbbbbbbbbbbb",
            decided_at="2020-01-01T00:00:00+00:00",
        ),
    )
    verdict, errors = SMOKE.audit_decision_log(log)
    assert verdict == "FAIL"
    assert any("non_chronological" in err for err in errors)


def test_checker_detects_unknown_candidate(tmp_path):
    log = _write_log(
        tmp_path / "unknown.jsonl",
        _valid_entry(candidate_id="aaaaaaaaaaaaaaaaaaaaaaaa"),
        _valid_entry(
            candidate_id="ffffffffffffffffffffffff",
            decided_at="2026-01-01T00:00:02+00:00",
        ),
    )
    verdict, errors = SMOKE.audit_decision_log(
        log, known_candidate_ids={"aaaaaaaaaaaaaaaaaaaaaaaa"}
    )
    assert verdict == "FAIL"
    assert any("unknown_candidate" in err for err in errors)


def test_checker_detects_unsupported_transition(tmp_path):
    log = _write_log(
        tmp_path / "unsupported.jsonl",
        _valid_entry(new_status="deleted"),
    )
    verdict, errors = SMOKE.audit_decision_log(log)
    assert verdict == "FAIL"
    assert any("unsupported_transition" in err for err in errors)


def test_checker_clean_log_still_passes_independently(tmp_path):
    # After separate tamper cases above, a fresh clean log still passes.
    log = _write_log(tmp_path / "clean_again.jsonl", _valid_entry())
    verdict, errors = SMOKE.audit_decision_log(log)
    assert verdict == "PASS"
    assert errors == []


# --- Safety guards ----------------------------------------------------------


def test_tamper_script_has_no_network_ui_or_route_behavior():
    script = SCRIPT_PATH.read_text(encoding="utf-8")
    forbidden_tokens = (
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
    for token in forbidden_tokens:
        assert token not in script


def test_tamper_script_refuses_repository_root_workspace():
    result = subprocess.run(
        [sys.executable, str(SCRIPT_PATH), "--json", "--base-dir", str(REPO_ROOT)],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert payload["verdict"] == "FAIL"
    assert "repository root" in payload["errors"][0]
