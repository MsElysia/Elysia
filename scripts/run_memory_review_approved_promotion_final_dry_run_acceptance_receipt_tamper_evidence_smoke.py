#!/usr/bin/env python3
"""Dry-run/local smoke proving final dry-run acceptance receipts detect tampering.

This smoke builds a valid final dry-run acceptance receipt, validates the clean
receipt as PASS, then writes isolated corrupted copies and checks that each one
returns FAIL with a specific error token. It never calls models, embeddings,
networks, live accounts, UI routes, or live runtime memory/vector DB.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import shutil
import sys
import tempfile
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Sequence, Tuple

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from run_memory_review_approved_promotion_final_dry_run_acceptance_receipt_smoke import (  # noqa: E402
    ACCEPTANCE_PHRASE,
    ACCEPTED_CHECKPOINT_HASH,
    ACCEPTED_CHECKPOINT_TAG,
    OPERATOR_NEXT_STEPS,
    RECEIPT_DIRNAME,
    RECEIPT_JSON_FILENAME,
    REQUIRED_RECEIPT_FIELDS,
    run_memory_review_approved_promotion_final_dry_run_acceptance_receipt_smoke,
)

REQUIRED_TAMPER_CASES = (
    "malformed_json",
    "missing_required_receipt_field",
    "operator_acceptance_phrase_changed",
    "operator_acceptance_phrase_valid_false",
    "accepted_checkpoint_tag_changed",
    "accepted_checkpoint_hash_changed",
    "source_final_readiness_packet_hash_mismatch",
    "source_final_readiness_packet_tamper_hash_mismatch",
    "source_operator_acceptance_gate_hash_mismatch",
    "source_operator_acceptance_gate_tamper_hash_mismatch",
    "final_readiness_packet_verdict_not_pass",
    "final_readiness_tamper_evidence_verdict_not_pass",
    "operator_acceptance_gate_verdict_not_pass",
    "operator_acceptance_gate_tamper_evidence_verdict_not_pass",
    "accepted_for_final_dry_run_readiness_false",
    "accepted_for_live_memory_write_true",
    "accepted_for_vector_db_write_true",
    "ready_for_future_live_write_design_true",
    "requires_separate_live_write_campaign_false",
    "requires_separate_operator_approval_for_live_write_false",
    "live_memory_write_allowed_true",
    "vector_db_write_allowed_true",
    "live_write_blocked_reason_missing",
    "vector_db_write_blocked_reason_missing",
    "operator_next_steps_missing",
    "dry_run_false",
    "local_only_false",
    "model_called_true",
    "embeddings_used_true",
    "live_memory_written_true",
    "live_vector_db_written_true",
    "account_api_network_accessed_true",
    "autonomy_enabled_true",
)

OPERATOR_NEXT_STEP_MARKERS = (
    "final dry-run readiness is accepted",
    "live memory writes remain blocked",
    "vector db writes remain blocked",
    "future live-write design requires a separate explicit campaign",
    "future live-write implementation requires a separate explicit campaign after design approval",
)

UNSAFE_RECEIPT_METADATA = (
    ("model_called", True, "model_called_true"),
    ("embeddings_used", True, "embeddings_used_true"),
    ("live_memory_written", True, "live_memory_written_true"),
    ("live_vector_db_written", True, "live_vector_db_written_true"),
    ("account_api_network_accessed", True, "account_api_network_accessed_true"),
    ("autonomy_enabled", True, "autonomy_enabled_true"),
)

DEFAULT_SOURCE_RELATIVE = {
    "packet_json": Path("approved_promotion_final_readiness_packet")
    / "final_readiness_packet.json",
    "packet_tamper_json": Path("approved_promotion_final_readiness_packet_tamper_evidence")
    / "final_readiness_packet_tamper_evidence.json",
    "gate_json": Path("approved_promotion_final_readiness_operator_acceptance_gate")
    / "operator_acceptance_gate.json",
    "gate_tamper_json": Path(
        "approved_promotion_final_readiness_operator_acceptance_gate_tamper_evidence"
    )
    / "operator_acceptance_gate_tamper_evidence.json",
}

SOURCE_HASH_CHECKS = (
    (
        "source_final_readiness_packet_sha256",
        "packet_json",
        "source_final_readiness_packet_hash_mismatch",
    ),
    (
        "source_final_readiness_packet_tamper_evidence_sha256",
        "packet_tamper_json",
        "source_final_readiness_packet_tamper_hash_mismatch",
    ),
    (
        "source_operator_acceptance_gate_sha256",
        "gate_json",
        "source_operator_acceptance_gate_hash_mismatch",
    ),
    (
        "source_operator_acceptance_gate_tamper_evidence_sha256",
        "gate_tamper_json",
        "source_operator_acceptance_gate_tamper_hash_mismatch",
    ),
)


@dataclass
class TamperCaseResult:
    case_name: str
    expected_verdict: str
    actual_verdict: str
    detected: bool
    detected_error_type: str
    details: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class AcceptanceReceiptTamperEvidenceReport:
    verdict: str
    workspace: str
    clean_receipt_verdict: str = "UNKNOWN"
    tamper_case_count: int = 0
    tamper_cases: List[Dict[str, Any]] = field(default_factory=list)
    all_tamper_cases_detected: bool = False
    detected_error_types: List[str] = field(default_factory=list)
    operator_required: bool = True
    dry_run: bool = True
    local_only: bool = True
    model_called: bool = False
    embeddings_used: bool = False
    live_memory_written: bool = False
    live_vector_db_written: bool = False
    account_api_network_accessed: bool = False
    autonomy_enabled: bool = False
    errors: List[str] = field(default_factory=list)
    workspace_preserved: bool = False
    clean_receipt_path: str = ""
    clean_receipt_json_path: str = ""
    clean_receipt_still_passes: bool = False
    tamper_paths_inside_workspace: bool = False
    artifact_paths: Dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _repo_root() -> Path:
    return PROJECT_ROOT.resolve()


def _read_autonomy_enabled() -> bool:
    path = _repo_root() / "config" / "autonomy.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return True
    return bool(payload.get("enabled"))


def _reject_dangerous_base(base_dir: Path) -> Path:
    if not str(base_dir).strip():
        raise ValueError("Refusing to use empty smoke workspace path.")
    resolved = base_dir.expanduser().resolve()
    repo_root = _repo_root()
    home = Path.home().resolve()
    if resolved == resolved.parent:
        raise ValueError(f"Refusing to use filesystem root as smoke workspace: {resolved}")
    if resolved == home:
        raise ValueError(f"Refusing to use home directory as smoke workspace: {resolved}")
    if resolved == repo_root:
        raise ValueError(f"Refusing to use repository root as smoke workspace: {resolved}")
    if resolved.anchor and str(resolved) == resolved.anchor:
        raise ValueError(f"Refusing to use drive root as smoke workspace: {resolved}")
    if resolved.exists() and not resolved.is_dir():
        raise ValueError(f"Smoke workspace exists but is not a directory: {resolved}")
    return resolved


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    digest.update(path.read_bytes())
    return digest.hexdigest()


def _path_inside_workspace(path: Path, workspace: Path) -> bool:
    try:
        path.resolve().relative_to(workspace.resolve())
        return True
    except ValueError:
        return False


def _write_json(path: Path, payload: Dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return path


def _write_raw(path: Path, raw: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(raw, encoding="utf-8")
    return path


def _copy_report(report: Dict[str, Any]) -> Dict[str, Any]:
    return copy.deepcopy(report)


def _error_type(error: str) -> str:
    return error.split(":", 1)[0].strip()


def _resolve_source_file(report: Dict[str, Any], key: str) -> Path | None:
    artifact_paths = report.get("artifact_paths")
    if isinstance(artifact_paths, dict):
        raw = artifact_paths.get(key)
        if raw:
            path = Path(str(raw))
            if path.is_file():
                return path
    workspace = Path(str(report.get("workspace") or ""))
    relative = DEFAULT_SOURCE_RELATIVE.get(key)
    if workspace.is_dir() and relative is not None:
        path = workspace / relative
        if path.is_file():
            return path
    return None


def audit_final_dry_run_acceptance_receipt(report_path: Path) -> Tuple[str, List[str]]:
    """Local-only checker for a final dry-run acceptance receipt JSON."""
    errors: List[str] = []
    if not report_path.is_file():
        return "FAIL", [f"missing_receipt_file: {report_path}"]

    try:
        report = json.loads(report_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return "FAIL", [f"malformed_json: receipt is not valid JSON ({exc})"]

    if not isinstance(report, dict):
        return "FAIL", ["malformed_json: receipt root is not a JSON object"]

    missing_fields = [
        field_name for field_name in REQUIRED_RECEIPT_FIELDS if field_name not in report
    ]
    if missing_fields:
        errors.append("missing_required_receipt_field: missing " + ", ".join(missing_fields))

    if (
        "operator_acceptance_phrase" in report
        and report.get("operator_acceptance_phrase") != ACCEPTANCE_PHRASE
    ):
        errors.append(
            "operator_acceptance_phrase_changed: operator_acceptance_phrase is not the required phrase"
        )
    if (
        "operator_acceptance_phrase_valid" in report
        and report.get("operator_acceptance_phrase_valid") is not True
    ):
        errors.append(
            "operator_acceptance_phrase_valid_false: operator_acceptance_phrase_valid is not true"
        )
    if (
        "accepted_checkpoint_tag" in report
        and report.get("accepted_checkpoint_tag") != ACCEPTED_CHECKPOINT_TAG
    ):
        errors.append("accepted_checkpoint_tag_changed: accepted_checkpoint_tag is not the required tag")
    if (
        "accepted_checkpoint_hash" in report
        and report.get("accepted_checkpoint_hash") != ACCEPTED_CHECKPOINT_HASH
    ):
        errors.append(
            "accepted_checkpoint_hash_changed: accepted_checkpoint_hash is not the required hash"
        )

    for field_name, source_key, token in SOURCE_HASH_CHECKS:
        if field_name not in report:
            continue
        recorded = str(report.get(field_name) or "")
        source_path = _resolve_source_file(report, source_key)
        if recorded and source_path is not None and recorded != _sha256_file(source_path):
            errors.append(f"{token}: {field_name} does not match file")

    if (
        "final_readiness_packet_verdict" in report
        and report.get("final_readiness_packet_verdict") != "PASS"
    ):
        errors.append(
            "final_readiness_packet_verdict_not_pass: final_readiness_packet_verdict is not PASS"
        )
    if (
        "final_readiness_packet_tamper_evidence_verdict" in report
        and report.get("final_readiness_packet_tamper_evidence_verdict") != "PASS"
    ):
        errors.append(
            "final_readiness_tamper_evidence_verdict_not_pass: "
            "final_readiness_packet_tamper_evidence_verdict is not PASS"
        )
    if (
        "operator_acceptance_gate_verdict" in report
        and report.get("operator_acceptance_gate_verdict") != "PASS"
    ):
        errors.append(
            "operator_acceptance_gate_verdict_not_pass: operator_acceptance_gate_verdict is not PASS"
        )
    if (
        "operator_acceptance_gate_tamper_evidence_verdict" in report
        and report.get("operator_acceptance_gate_tamper_evidence_verdict") != "PASS"
    ):
        errors.append(
            "operator_acceptance_gate_tamper_evidence_verdict_not_pass: "
            "operator_acceptance_gate_tamper_evidence_verdict is not PASS"
        )

    if (
        "accepted_for_final_dry_run_readiness" in report
        and report.get("accepted_for_final_dry_run_readiness") is not True
    ):
        errors.append(
            "accepted_for_final_dry_run_readiness_false: accepted_for_final_dry_run_readiness is not true"
        )
    if report.get("accepted_for_live_memory_write") is True:
        errors.append("accepted_for_live_memory_write_true: accepted_for_live_memory_write=true")
    if report.get("accepted_for_vector_db_write") is True:
        errors.append("accepted_for_vector_db_write_true: accepted_for_vector_db_write=true")
    if report.get("ready_for_future_live_write_design") is True:
        errors.append(
            "ready_for_future_live_write_design_true: ready_for_future_live_write_design=true"
        )
    if (
        "requires_separate_live_write_campaign" in report
        and report.get("requires_separate_live_write_campaign") is not True
    ):
        errors.append(
            "requires_separate_live_write_campaign_false: "
            "requires_separate_live_write_campaign is not true"
        )
    if (
        "requires_separate_operator_approval_for_live_write" in report
        and report.get("requires_separate_operator_approval_for_live_write") is not True
    ):
        errors.append(
            "requires_separate_operator_approval_for_live_write_false: "
            "requires_separate_operator_approval_for_live_write is not true"
        )
    if report.get("live_memory_write_allowed") is True:
        errors.append("live_memory_write_allowed_true: live_memory_write_allowed=true")
    if report.get("vector_db_write_allowed") is True:
        errors.append("vector_db_write_allowed_true: vector_db_write_allowed=true")

    if "live_write_blocked_reason" in report and not str(
        report.get("live_write_blocked_reason") or ""
    ).strip():
        errors.append("live_write_blocked_reason_missing: live_write_blocked_reason is missing")
    if "vector_db_write_blocked_reason" in report and not str(
        report.get("vector_db_write_blocked_reason") or ""
    ).strip():
        errors.append(
            "vector_db_write_blocked_reason_missing: vector_db_write_blocked_reason is missing"
        )

    if "operator_next_steps" in report:
        steps = report.get("operator_next_steps")
        joined = " ".join(str(step) for step in steps).lower() if isinstance(steps, list) else ""
        missing_markers = [
            marker for marker in OPERATOR_NEXT_STEP_MARKERS if marker not in joined
        ]
        if not isinstance(steps, list) or not steps or missing_markers:
            errors.append("operator_next_steps_missing: required operator next steps are missing")

    if "dry_run" in report and report.get("dry_run") is not True:
        errors.append("dry_run_false: dry_run is not true")
    if "local_only" in report and report.get("local_only") is not True:
        errors.append("local_only_false: local_only is not true")

    for field_name, unsafe_value, token in UNSAFE_RECEIPT_METADATA:
        if field_name in report and report.get(field_name) is unsafe_value:
            errors.append(f"{token}: {field_name}={str(unsafe_value).lower()}")

    return ("PASS" if not errors else "FAIL"), errors


def _load_clean_receipt(workspace: Path) -> Tuple[Path, Dict[str, Any], Dict[str, str]]:
    receipt_report = run_memory_review_approved_promotion_final_dry_run_acceptance_receipt_smoke(
        base_dir=workspace,
        keep_temp=True,
    )
    if receipt_report.verdict != "PASS":
        raise ValueError(
            "Final dry-run acceptance receipt smoke did not pass while "
            "building clean receipt: " + "; ".join(receipt_report.errors)
        )
    report_path = Path(receipt_report.receipt_json_path)
    if not report_path.is_file():
        fallback = workspace / RECEIPT_DIRNAME / RECEIPT_JSON_FILENAME
        if fallback.is_file():
            report_path = fallback
        else:
            raise ValueError(f"Clean acceptance receipt was not created: {report_path}")
    report = json.loads(report_path.read_text(encoding="utf-8"))
    artifact_paths = {
        "clean_receipt_dir": receipt_report.receipt_path,
        "clean_receipt_json": str(report_path.resolve()),
        "clean_receipt_readme": str(Path(receipt_report.receipt_readme_path).resolve())
        if receipt_report.receipt_readme_path
        else "",
        **{
            key: str(Path(value).resolve())
            for key, value in (receipt_report.artifact_paths or {}).items()
            if value
        },
    }
    return report_path, report, artifact_paths


def _run_tamper_flow(
    workspace: Path,
    *,
    workspace_preserved: bool,
) -> AcceptanceReceiptTamperEvidenceReport:
    errors: List[str] = []
    case_paths: Dict[str, str] = {}
    report = AcceptanceReceiptTamperEvidenceReport(
        verdict="FAIL",
        workspace=str(workspace.resolve()),
        workspace_preserved=workspace_preserved,
        autonomy_enabled=_read_autonomy_enabled(),
    )
    if report.autonomy_enabled:
        report.errors.append(
            "Autonomy is enabled; acceptance receipt tamper evidence smoke is blocked."
        )
        return report

    clean_report_path, clean_report, artifact_paths = _load_clean_receipt(workspace)
    report.clean_receipt_json_path = str(clean_report_path.resolve())
    report.clean_receipt_path = artifact_paths.get("clean_receipt_dir", "")
    tamper_dir = workspace / "tampered_acceptance_receipts"
    tamper_dir.mkdir(parents=True, exist_ok=True)

    clean_verdict, clean_errors = audit_final_dry_run_acceptance_receipt(clean_report_path)
    report.clean_receipt_verdict = clean_verdict
    report.clean_receipt_still_passes = clean_verdict == "PASS" and not clean_errors
    if not report.clean_receipt_still_passes:
        errors.append(f"Clean acceptance receipt did not pass: {clean_errors}")

    cases: List[TamperCaseResult] = []

    def _record_case(name: str, expected_token: str, path: Path) -> None:
        verdict, case_errors = audit_final_dry_run_acceptance_receipt(path)
        token_found = any(expected_token in error for error in case_errors)
        detected_types = [_error_type(error) for error in case_errors]
        detected_error_type = expected_token if token_found else (
            detected_types[0] if detected_types else ""
        )
        cases.append(
            TamperCaseResult(
                case_name=name,
                expected_verdict="FAIL",
                actual_verdict=verdict,
                detected=verdict == "FAIL" and token_found,
                detected_error_type=detected_error_type,
                details=case_errors,
            )
        )
        case_paths[name] = str(path.resolve())

    malformed_path = tamper_dir / "malformed_json.json"
    _write_raw(malformed_path, "{ this is not valid json\n")
    _record_case("malformed_json", "malformed_json", malformed_path)

    missing_field = _copy_report(clean_report)
    missing_field.pop("workspace", None)
    missing_path = tamper_dir / "missing_required_receipt_field.json"
    _write_json(missing_path, missing_field)
    _record_case("missing_required_receipt_field", "missing_required_receipt_field", missing_path)

    phrase_changed = _copy_report(clean_report)
    phrase_changed["operator_acceptance_phrase"] = "INVALID_FINAL_DRY_RUN_READINESS_TOKEN"
    phrase_path = tamper_dir / "operator_acceptance_phrase_changed.json"
    _write_json(phrase_path, phrase_changed)
    _record_case(
        "operator_acceptance_phrase_changed",
        "operator_acceptance_phrase_changed",
        phrase_path,
    )

    phrase_invalid = _copy_report(clean_report)
    phrase_invalid["operator_acceptance_phrase_valid"] = False
    phrase_invalid_path = tamper_dir / "operator_acceptance_phrase_valid_false.json"
    _write_json(phrase_invalid_path, phrase_invalid)
    _record_case(
        "operator_acceptance_phrase_valid_false",
        "operator_acceptance_phrase_valid_false",
        phrase_invalid_path,
    )

    tag_changed = _copy_report(clean_report)
    tag_changed["accepted_checkpoint_tag"] = "wrong_checkpoint_tag"
    tag_path = tamper_dir / "accepted_checkpoint_tag_changed.json"
    _write_json(tag_path, tag_changed)
    _record_case("accepted_checkpoint_tag_changed", "accepted_checkpoint_tag_changed", tag_path)

    hash_changed = _copy_report(clean_report)
    hash_changed["accepted_checkpoint_hash"] = "0" * 40
    hash_path = tamper_dir / "accepted_checkpoint_hash_changed.json"
    _write_json(hash_path, hash_changed)
    _record_case(
        "accepted_checkpoint_hash_changed",
        "accepted_checkpoint_hash_changed",
        hash_path,
    )

    packet_hash = _copy_report(clean_report)
    packet_hash["source_final_readiness_packet_sha256"] = "0" * 64
    packet_hash_path = tamper_dir / "source_final_readiness_packet_hash_mismatch.json"
    _write_json(packet_hash_path, packet_hash)
    _record_case(
        "source_final_readiness_packet_hash_mismatch",
        "source_final_readiness_packet_hash_mismatch",
        packet_hash_path,
    )

    packet_tamper_hash = _copy_report(clean_report)
    packet_tamper_hash["source_final_readiness_packet_tamper_evidence_sha256"] = "0" * 64
    packet_tamper_hash_path = tamper_dir / "source_final_readiness_packet_tamper_hash_mismatch.json"
    _write_json(packet_tamper_hash_path, packet_tamper_hash)
    _record_case(
        "source_final_readiness_packet_tamper_hash_mismatch",
        "source_final_readiness_packet_tamper_hash_mismatch",
        packet_tamper_hash_path,
    )

    gate_hash = _copy_report(clean_report)
    gate_hash["source_operator_acceptance_gate_sha256"] = "0" * 64
    gate_hash_path = tamper_dir / "source_operator_acceptance_gate_hash_mismatch.json"
    _write_json(gate_hash_path, gate_hash)
    _record_case(
        "source_operator_acceptance_gate_hash_mismatch",
        "source_operator_acceptance_gate_hash_mismatch",
        gate_hash_path,
    )

    gate_tamper_hash = _copy_report(clean_report)
    gate_tamper_hash["source_operator_acceptance_gate_tamper_evidence_sha256"] = "0" * 64
    gate_tamper_hash_path = tamper_dir / "source_operator_acceptance_gate_tamper_hash_mismatch.json"
    _write_json(gate_tamper_hash_path, gate_tamper_hash)
    _record_case(
        "source_operator_acceptance_gate_tamper_hash_mismatch",
        "source_operator_acceptance_gate_tamper_hash_mismatch",
        gate_tamper_hash_path,
    )

    packet_verdict = _copy_report(clean_report)
    packet_verdict["final_readiness_packet_verdict"] = "FAIL"
    packet_verdict_path = tamper_dir / "final_readiness_packet_verdict_not_pass.json"
    _write_json(packet_verdict_path, packet_verdict)
    _record_case(
        "final_readiness_packet_verdict_not_pass",
        "final_readiness_packet_verdict_not_pass",
        packet_verdict_path,
    )

    packet_tamper_verdict = _copy_report(clean_report)
    packet_tamper_verdict["final_readiness_packet_tamper_evidence_verdict"] = "FAIL"
    packet_tamper_verdict_path = tamper_dir / "final_readiness_tamper_evidence_verdict_not_pass.json"
    _write_json(packet_tamper_verdict_path, packet_tamper_verdict)
    _record_case(
        "final_readiness_tamper_evidence_verdict_not_pass",
        "final_readiness_tamper_evidence_verdict_not_pass",
        packet_tamper_verdict_path,
    )

    gate_verdict = _copy_report(clean_report)
    gate_verdict["operator_acceptance_gate_verdict"] = "FAIL"
    gate_verdict_path = tamper_dir / "operator_acceptance_gate_verdict_not_pass.json"
    _write_json(gate_verdict_path, gate_verdict)
    _record_case(
        "operator_acceptance_gate_verdict_not_pass",
        "operator_acceptance_gate_verdict_not_pass",
        gate_verdict_path,
    )

    gate_tamper_verdict = _copy_report(clean_report)
    gate_tamper_verdict["operator_acceptance_gate_tamper_evidence_verdict"] = "FAIL"
    gate_tamper_verdict_path = (
        tamper_dir / "operator_acceptance_gate_tamper_evidence_verdict_not_pass.json"
    )
    _write_json(gate_tamper_verdict_path, gate_tamper_verdict)
    _record_case(
        "operator_acceptance_gate_tamper_evidence_verdict_not_pass",
        "operator_acceptance_gate_tamper_evidence_verdict_not_pass",
        gate_tamper_verdict_path,
    )

    authorization_cases = (
        ("accepted_for_final_dry_run_readiness_false", "accepted_for_final_dry_run_readiness", False),
        ("accepted_for_live_memory_write_true", "accepted_for_live_memory_write", True),
        ("accepted_for_vector_db_write_true", "accepted_for_vector_db_write", True),
        ("ready_for_future_live_write_design_true", "ready_for_future_live_write_design", True),
        (
            "requires_separate_live_write_campaign_false",
            "requires_separate_live_write_campaign",
            False,
        ),
        (
            "requires_separate_operator_approval_for_live_write_false",
            "requires_separate_operator_approval_for_live_write",
            False,
        ),
        ("live_memory_write_allowed_true", "live_memory_write_allowed", True),
        ("vector_db_write_allowed_true", "vector_db_write_allowed", True),
    )
    for case_name, field_name, value in authorization_cases:
        flipped = _copy_report(clean_report)
        flipped[field_name] = value
        flipped_path = tamper_dir / f"{case_name}.json"
        _write_json(flipped_path, flipped)
        _record_case(case_name, case_name, flipped_path)

    live_reason_missing = _copy_report(clean_report)
    live_reason_missing["live_write_blocked_reason"] = ""
    live_reason_path = tamper_dir / "live_write_blocked_reason_missing.json"
    _write_json(live_reason_path, live_reason_missing)
    _record_case(
        "live_write_blocked_reason_missing",
        "live_write_blocked_reason_missing",
        live_reason_path,
    )

    vector_reason_missing = _copy_report(clean_report)
    vector_reason_missing["vector_db_write_blocked_reason"] = ""
    vector_reason_path = tamper_dir / "vector_db_write_blocked_reason_missing.json"
    _write_json(vector_reason_path, vector_reason_missing)
    _record_case(
        "vector_db_write_blocked_reason_missing",
        "vector_db_write_blocked_reason_missing",
        vector_reason_path,
    )

    next_steps_missing = _copy_report(clean_report)
    next_steps_missing["operator_next_steps"] = []
    next_steps_path = tamper_dir / "operator_next_steps_missing.json"
    _write_json(next_steps_path, next_steps_missing)
    _record_case("operator_next_steps_missing", "operator_next_steps_missing", next_steps_path)

    mode_and_unsafe_cases = (
        ("dry_run_false", "dry_run", False),
        ("local_only_false", "local_only", False),
        ("model_called_true", "model_called", True),
        ("embeddings_used_true", "embeddings_used", True),
        ("live_memory_written_true", "live_memory_written", True),
        ("live_vector_db_written_true", "live_vector_db_written", True),
        ("account_api_network_accessed_true", "account_api_network_accessed", True),
        ("autonomy_enabled_true", "autonomy_enabled", True),
    )
    for case_name, field_name, value in mode_and_unsafe_cases:
        flipped = _copy_report(clean_report)
        flipped[field_name] = value
        flipped_path = tamper_dir / f"{case_name}.json"
        _write_json(flipped_path, flipped)
        _record_case(case_name, case_name, flipped_path)

    report.tamper_cases = [case.to_dict() for case in cases]
    report.tamper_case_count = len(cases)
    report.detected_error_types = sorted(
        {case.detected_error_type for case in cases if case.detected_error_type}
    )
    report.all_tamper_cases_detected = all(case.detected for case in cases) and [
        case.case_name for case in cases
    ] == list(REQUIRED_TAMPER_CASES)
    if not report.all_tamper_cases_detected:
        missing = [case.case_name for case in cases if not case.detected]
        extra = [case.case_name for case in cases if case.case_name not in REQUIRED_TAMPER_CASES]
        if [case.case_name for case in cases] != list(REQUIRED_TAMPER_CASES):
            errors.append("required_tamper_case_set_mismatch")
        if missing:
            errors.append("undetected_tamper_cases: " + ", ".join(missing))
        if extra:
            errors.append("unexpected_tamper_cases: " + ", ".join(extra))

    still_clean, still_clean_errors = audit_final_dry_run_acceptance_receipt(clean_report_path)
    report.clean_receipt_still_passes = still_clean == "PASS" and not still_clean_errors
    if not report.clean_receipt_still_passes:
        errors.append(
            f"Clean acceptance receipt no longer passes after tamper copies: {still_clean_errors}"
        )

    report.tamper_paths_inside_workspace = all(
        _path_inside_workspace(Path(path), workspace) for path in case_paths.values()
    )
    if not report.tamper_paths_inside_workspace:
        errors.append("tamper_paths_outside_workspace")

    report.artifact_paths = {
        **artifact_paths,
        "tamper_dir": str(tamper_dir.resolve()),
        **{f"tampered_{name}": path for name, path in case_paths.items()},
    }
    report.errors = errors
    report.verdict = "PASS" if not errors else "FAIL"
    return report


def run_memory_review_approved_promotion_final_dry_run_acceptance_receipt_tamper_evidence_smoke(
    *,
    base_dir: Path | None = None,
    keep_temp: bool = False,
) -> AcceptanceReceiptTamperEvidenceReport:
    """Build a clean acceptance receipt and prove tampered variants fail."""
    owned_temp = base_dir is None
    workspace = (
        Path(tempfile.mkdtemp(prefix="elysia_fdrarte_"))
        if owned_temp
        else _reject_dangerous_base(Path(base_dir))
    )
    workspace.mkdir(parents=True, exist_ok=True)
    try:
        try:
            return _run_tamper_flow(
                workspace,
                workspace_preserved=(not owned_temp) or keep_temp,
            )
        except Exception as exc:
            return AcceptanceReceiptTamperEvidenceReport(
                verdict="FAIL",
                workspace=str(workspace.resolve()),
                workspace_preserved=(not owned_temp) or keep_temp,
                autonomy_enabled=_read_autonomy_enabled(),
                errors=[f"acceptance_receipt_tamper_build_failed: {exc}"],
            )
    finally:
        if owned_temp and not keep_temp:
            shutil.rmtree(workspace, ignore_errors=True)


def format_operator_summary(report: AcceptanceReceiptTamperEvidenceReport) -> str:
    lines = [
        "Memory review approved promotion final dry-run acceptance receipt tamper evidence smoke",
        "=" * 86,
        f"Verdict: {report.verdict}",
        f"Workspace: {report.workspace}",
        f"Clean receipt verdict: {report.clean_receipt_verdict}",
        f"Tamper case count: {report.tamper_case_count}",
        f"All tamper cases detected: {report.all_tamper_cases_detected}",
        "",
        "Tamper cases:",
    ]
    for case in report.tamper_cases:
        lines.append(
            f"  {case.get('case_name')}: expected={case.get('expected_verdict')} "
            f"actual={case.get('actual_verdict')} detected={case.get('detected')} "
            f"error_type={case.get('detected_error_type')}"
        )
    lines.extend(
        [
            "",
            "Safety:",
            f"  operator_required: {report.operator_required}",
            f"  dry_run: {report.dry_run}",
            f"  local_only: {report.local_only}",
            f"  model_called: {report.model_called}",
            f"  embeddings_used: {report.embeddings_used}",
            f"  live_memory_written: {report.live_memory_written}",
            f"  live_vector_db_written: {report.live_vector_db_written}",
            f"  account_api_network_accessed: {report.account_api_network_accessed}",
            f"  autonomy_enabled: {report.autonomy_enabled}",
        ]
    )
    if report.errors:
        lines.extend(["", "Errors:"])
        lines.extend(f"  - {error}" for error in report.errors)
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Run local-only Memory review approved promotion final dry-run "
            "acceptance receipt tamper evidence smoke."
        ),
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON to stdout")
    parser.add_argument("--base-dir", type=Path, default=None)
    parser.add_argument("--keep-temp", action="store_true")
    args = parser.parse_args(argv)
    try:
        report = run_memory_review_approved_promotion_final_dry_run_acceptance_receipt_tamper_evidence_smoke(
            base_dir=args.base_dir,
            keep_temp=args.keep_temp,
        )
    except (ValueError, OSError) as exc:
        report = AcceptanceReceiptTamperEvidenceReport(
            verdict="FAIL",
            workspace=str(args.base_dir or ""),
            errors=[str(exc)],
            autonomy_enabled=_read_autonomy_enabled(),
        )
    if args.json:
        print(json.dumps(report.to_dict(), indent=2, ensure_ascii=False))
    else:
        print(format_operator_summary(report))
    return 0 if report.verdict == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
