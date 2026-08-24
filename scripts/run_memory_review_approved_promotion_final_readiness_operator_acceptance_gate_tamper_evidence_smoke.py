#!/usr/bin/env python3
"""Dry-run/local smoke proving acceptance-gate reports detect tampering.

This smoke builds a valid final readiness operator acceptance gate report,
validates the clean report as PASS, then writes isolated corrupted copies and
checks that each one returns FAIL with a specific error token. It never calls
models, embeddings, networks, live accounts, UI routes, or live runtime
memory/vector DB.
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

from run_memory_review_approved_promotion_final_readiness_operator_acceptance_gate_smoke import (  # noqa: E402
    ACCEPTANCE_PHRASE,
    INVALID_ACCEPTANCE_CASES,
    REQUIRED_ACCEPTANCE_CASES,
    run_memory_review_approved_promotion_final_readiness_operator_acceptance_gate_smoke,
)

REQUIRED_GATE_FIELDS = (
    "verdict",
    "workspace",
    "gate_path",
    "gate_report_path",
    "gate_report_valid_json",
    "acceptance_phrase",
    "acceptance_phrase_valid",
    "acceptance_artifact_present",
    "acceptance_artifact_sha256",
    "source_final_readiness_packet_path",
    "source_final_readiness_packet_sha256",
    "source_final_readiness_tamper_evidence_path",
    "source_final_readiness_tamper_evidence_sha256",
    "packet_tamper_evidence_verdict",
    "clean_packet_verdict",
    "operator_acceptance_valid",
    "accepted_for_final_dry_run_readiness",
    "accepted_for_live_memory_write",
    "accepted_for_vector_db_write",
    "ready_for_future_live_write_design",
    "requires_separate_live_write_campaign",
    "live_memory_write_allowed",
    "vector_db_write_allowed",
    "live_write_blocked_reason",
    "vector_db_write_blocked_reason",
    "acceptance_cases",
    "all_invalid_acceptance_cases_failed_closed",
    "valid_acceptance_passed_dry_run_only",
    "operator_required",
    "dry_run",
    "local_only",
    "model_called",
    "embeddings_used",
    "live_memory_written",
    "live_vector_db_written",
    "account_api_network_accessed",
    "autonomy_enabled",
    "errors",
)

REQUIRED_TAMPER_CASES = (
    "malformed_json",
    "missing_required_gate_field",
    "acceptance_phrase_changed",
    "acceptance_artifact_missing_but_valid_true",
    "acceptance_artifact_hash_mismatch",
    "source_packet_hash_mismatch",
    "source_packet_tamper_hash_mismatch",
    "packet_tamper_evidence_not_pass",
    "clean_packet_not_pass",
    "missing_acceptance_case",
    "invalid_case_marked_pass",
    "valid_case_marked_fail",
    "all_invalid_cases_not_failed_closed",
    "valid_acceptance_not_dry_run_only",
    "accepted_for_live_memory_write_true",
    "accepted_for_vector_db_write_true",
    "live_memory_write_allowed_true",
    "vector_db_write_allowed_true",
    "requires_separate_live_write_campaign_false",
    "operator_required_false",
    "dry_run_false",
    "local_only_false",
    "model_called_true",
    "embeddings_used_true",
    "live_memory_written_true",
    "live_vector_db_written_true",
    "account_api_network_accessed_true",
    "autonomy_enabled_true",
)

UNSAFE_GATE_METADATA = (
    ("model_called", True, "model_called_true"),
    ("embeddings_used", True, "embeddings_used_true"),
    ("live_memory_written", True, "live_memory_written_true"),
    ("live_vector_db_written", True, "live_vector_db_written_true"),
    ("account_api_network_accessed", True, "account_api_network_accessed_true"),
    ("autonomy_enabled", True, "autonomy_enabled_true"),
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
class AcceptanceGateTamperEvidenceReport:
    verdict: str
    workspace: str
    clean_gate_verdict: str = "UNKNOWN"
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
    clean_gate_path: str = ""
    clean_gate_report_path: str = ""
    clean_gate_still_passes: bool = False
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


def _cases_by_name(report: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    cases = report.get("acceptance_cases")
    if not isinstance(cases, list):
        return {}
    named: Dict[str, Dict[str, Any]] = {}
    for case in cases:
        if isinstance(case, dict) and case.get("case_name"):
            named[str(case["case_name"])] = case
    return named


def audit_operator_acceptance_gate_report(report_path: Path) -> Tuple[str, List[str]]:
    """Local-only checker for a final readiness operator acceptance gate JSON."""
    errors: List[str] = []
    if not report_path.is_file():
        return "FAIL", [f"missing_gate_file: {report_path}"]

    try:
        report = json.loads(report_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return "FAIL", [f"malformed_json: gate report is not valid JSON ({exc})"]

    if not isinstance(report, dict):
        return "FAIL", ["malformed_json: gate report root is not a JSON object"]

    missing_fields = [
        field_name for field_name in REQUIRED_GATE_FIELDS if field_name not in report
    ]
    if missing_fields:
        errors.append("missing_required_gate_field: missing " + ", ".join(missing_fields))

    if "acceptance_phrase" in report and report.get("acceptance_phrase") != ACCEPTANCE_PHRASE:
        errors.append("acceptance_phrase_changed: acceptance_phrase is not the required phrase")

    if report.get("acceptance_artifact_present") is False and (
        report.get("operator_acceptance_valid") is True
        or report.get("accepted_for_final_dry_run_readiness") is True
    ):
        errors.append(
            "acceptance_artifact_missing_but_valid_true: "
            "acceptance artifact is missing but acceptance is marked valid"
        )

    artifact_path = Path(str(report.get("artifact_paths", {}).get("valid_acceptance_artifact") or ""))
    if not artifact_path.is_file():
        artifact_path = Path(str(report.get("gate_path") or "")) / "operator_acceptance.json"
    recorded_artifact = str(report.get("acceptance_artifact_sha256") or "")
    if recorded_artifact and artifact_path.is_file():
        if recorded_artifact != _sha256_file(artifact_path):
            errors.append(
                "acceptance_artifact_hash_mismatch: "
                "acceptance_artifact_sha256 does not match file"
            )

    packet_path = Path(str(report.get("source_final_readiness_packet_path") or ""))
    recorded_packet = str(report.get("source_final_readiness_packet_sha256") or "")
    if recorded_packet and packet_path.is_file():
        if recorded_packet != _sha256_file(packet_path):
            errors.append(
                "source_packet_hash_mismatch: "
                "source_final_readiness_packet_sha256 does not match file"
            )

    tamper_path = Path(str(report.get("source_final_readiness_tamper_evidence_path") or ""))
    recorded_tamper = str(report.get("source_final_readiness_tamper_evidence_sha256") or "")
    if recorded_tamper and tamper_path.is_file():
        if recorded_tamper != _sha256_file(tamper_path):
            errors.append(
                "source_packet_tamper_hash_mismatch: "
                "source_final_readiness_tamper_evidence_sha256 does not match file"
            )

    if (
        "packet_tamper_evidence_verdict" in report
        and report.get("packet_tamper_evidence_verdict") != "PASS"
    ):
        errors.append("packet_tamper_evidence_not_pass: packet_tamper_evidence_verdict is not PASS")
    if "clean_packet_verdict" in report and report.get("clean_packet_verdict") != "PASS":
        errors.append("clean_packet_not_pass: clean_packet_verdict is not PASS")

    named_cases = _cases_by_name(report)
    if "acceptance_cases" in report:
        missing_cases = [
            name for name in REQUIRED_ACCEPTANCE_CASES if name not in named_cases
        ]
        if missing_cases:
            errors.append("missing_acceptance_case: missing " + ", ".join(missing_cases))
        for name in INVALID_ACCEPTANCE_CASES:
            case = named_cases.get(name)
            if case and case.get("actual_verdict") != "FAIL":
                errors.append(
                    f"invalid_case_marked_pass: {name} actual_verdict is not FAIL"
                )
        valid_case = named_cases.get("valid_final_dry_run_acceptance")
        if valid_case and valid_case.get("actual_verdict") != "PASS":
            errors.append("valid_case_marked_fail: valid_final_dry_run_acceptance is not PASS")

    if (
        "all_invalid_acceptance_cases_failed_closed" in report
        and report.get("all_invalid_acceptance_cases_failed_closed") is not True
    ):
        errors.append(
            "all_invalid_cases_not_failed_closed: "
            "all_invalid_acceptance_cases_failed_closed is not true"
        )
    if (
        "valid_acceptance_passed_dry_run_only" in report
        and report.get("valid_acceptance_passed_dry_run_only") is not True
    ):
        errors.append(
            "valid_acceptance_not_dry_run_only: "
            "valid_acceptance_passed_dry_run_only is not true"
        )

    if report.get("accepted_for_live_memory_write") is True:
        errors.append("accepted_for_live_memory_write_true: accepted_for_live_memory_write=true")
    if report.get("accepted_for_vector_db_write") is True:
        errors.append("accepted_for_vector_db_write_true: accepted_for_vector_db_write=true")
    if report.get("live_memory_write_allowed") is True:
        errors.append("live_memory_write_allowed_true: live_memory_write_allowed=true")
    if report.get("vector_db_write_allowed") is True:
        errors.append("vector_db_write_allowed_true: vector_db_write_allowed=true")
    if (
        "requires_separate_live_write_campaign" in report
        and report.get("requires_separate_live_write_campaign") is not True
    ):
        errors.append(
            "requires_separate_live_write_campaign_false: "
            "requires_separate_live_write_campaign is not true"
        )
    if "operator_required" in report and report.get("operator_required") is not True:
        errors.append("operator_required_false: operator_required is not true")
    if "dry_run" in report and report.get("dry_run") is not True:
        errors.append("dry_run_false: dry_run is not true")
    if "local_only" in report and report.get("local_only") is not True:
        errors.append("local_only_false: local_only is not true")

    for field_name, unsafe_value, token in UNSAFE_GATE_METADATA:
        if field_name in report and report.get(field_name) is unsafe_value:
            errors.append(f"{token}: {field_name}={str(unsafe_value).lower()}")

    return ("PASS" if not errors else "FAIL"), errors


def _load_clean_gate(workspace: Path) -> Tuple[Path, Dict[str, Any], Dict[str, str]]:
    gate_report = run_memory_review_approved_promotion_final_readiness_operator_acceptance_gate_smoke(
        base_dir=workspace,
        keep_temp=True,
    )
    if gate_report.verdict != "PASS":
        raise ValueError(
            "Final readiness operator acceptance gate smoke did not pass while "
            "building clean report: " + "; ".join(gate_report.errors)
        )
    report_path = Path(gate_report.gate_report_path)
    if not report_path.is_file():
        raise ValueError(f"Clean acceptance gate report was not created: {report_path}")
    report = json.loads(report_path.read_text(encoding="utf-8"))
    artifact_paths = {
        "clean_gate_dir": gate_report.gate_path,
        "clean_gate_report": str(report_path.resolve()),
        "clean_gate_readme": str(Path(gate_report.gate_readme_path).resolve()),
        "valid_acceptance_artifact": str(
            Path(gate_report.artifact_paths.get("valid_acceptance_artifact", "")).resolve()
        )
        if gate_report.artifact_paths.get("valid_acceptance_artifact")
        else "",
    }
    return report_path, report, artifact_paths


def _run_tamper_flow(
    workspace: Path,
    *,
    workspace_preserved: bool,
) -> AcceptanceGateTamperEvidenceReport:
    errors: List[str] = []
    case_paths: Dict[str, str] = {}
    report = AcceptanceGateTamperEvidenceReport(
        verdict="FAIL",
        workspace=str(workspace.resolve()),
        workspace_preserved=workspace_preserved,
        autonomy_enabled=_read_autonomy_enabled(),
    )
    if report.autonomy_enabled:
        report.errors.append(
            "Autonomy is enabled; acceptance gate tamper evidence smoke is blocked."
        )
        return report

    clean_report_path, clean_report, artifact_paths = _load_clean_gate(workspace)
    report.clean_gate_report_path = str(clean_report_path.resolve())
    report.clean_gate_path = artifact_paths.get("clean_gate_dir", "")
    tamper_dir = workspace / "tampered_acceptance_gate_reports"
    tamper_dir.mkdir(parents=True, exist_ok=True)

    clean_verdict, clean_errors = audit_operator_acceptance_gate_report(clean_report_path)
    report.clean_gate_verdict = clean_verdict
    report.clean_gate_still_passes = clean_verdict == "PASS" and not clean_errors
    if not report.clean_gate_still_passes:
        errors.append(f"Clean acceptance gate report did not pass: {clean_errors}")

    cases: List[TamperCaseResult] = []

    def _record_case(name: str, expected_token: str, path: Path) -> None:
        verdict, case_errors = audit_operator_acceptance_gate_report(path)
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

    malformed_path = tamper_dir / "malformed_json_gate.json"
    _write_raw(malformed_path, "{ this is not valid json\n")
    _record_case("malformed_json", "malformed_json", malformed_path)

    missing_field = _copy_report(clean_report)
    missing_field.pop("workspace", None)
    missing_path = tamper_dir / "missing_required_gate_field.json"
    _write_json(missing_path, missing_field)
    _record_case("missing_required_gate_field", "missing_required_gate_field", missing_path)

    phrase_changed = _copy_report(clean_report)
    phrase_changed["acceptance_phrase"] = "INVALID_FINAL_DRY_RUN_READINESS_TOKEN"
    phrase_path = tamper_dir / "acceptance_phrase_changed.json"
    _write_json(phrase_path, phrase_changed)
    _record_case("acceptance_phrase_changed", "acceptance_phrase_changed", phrase_path)

    missing_but_valid = _copy_report(clean_report)
    missing_but_valid["acceptance_artifact_present"] = False
    missing_but_valid["operator_acceptance_valid"] = True
    missing_but_valid["accepted_for_final_dry_run_readiness"] = True
    missing_but_valid_path = tamper_dir / "acceptance_artifact_missing_but_valid_true.json"
    _write_json(missing_but_valid_path, missing_but_valid)
    _record_case(
        "acceptance_artifact_missing_but_valid_true",
        "acceptance_artifact_missing_but_valid_true",
        missing_but_valid_path,
    )

    artifact_hash = _copy_report(clean_report)
    artifact_hash["acceptance_artifact_sha256"] = "0" * 64
    artifact_hash_path = tamper_dir / "acceptance_artifact_hash_mismatch.json"
    _write_json(artifact_hash_path, artifact_hash)
    _record_case(
        "acceptance_artifact_hash_mismatch",
        "acceptance_artifact_hash_mismatch",
        artifact_hash_path,
    )

    packet_hash = _copy_report(clean_report)
    packet_hash["source_final_readiness_packet_sha256"] = "0" * 64
    packet_hash_path = tamper_dir / "source_packet_hash_mismatch.json"
    _write_json(packet_hash_path, packet_hash)
    _record_case("source_packet_hash_mismatch", "source_packet_hash_mismatch", packet_hash_path)

    tamper_hash = _copy_report(clean_report)
    tamper_hash["source_final_readiness_tamper_evidence_sha256"] = "0" * 64
    tamper_hash_path = tamper_dir / "source_packet_tamper_hash_mismatch.json"
    _write_json(tamper_hash_path, tamper_hash)
    _record_case(
        "source_packet_tamper_hash_mismatch",
        "source_packet_tamper_hash_mismatch",
        tamper_hash_path,
    )

    tamper_not_pass = _copy_report(clean_report)
    tamper_not_pass["packet_tamper_evidence_verdict"] = "FAIL"
    tamper_not_pass_path = tamper_dir / "packet_tamper_evidence_not_pass.json"
    _write_json(tamper_not_pass_path, tamper_not_pass)
    _record_case(
        "packet_tamper_evidence_not_pass",
        "packet_tamper_evidence_not_pass",
        tamper_not_pass_path,
    )

    packet_not_pass = _copy_report(clean_report)
    packet_not_pass["clean_packet_verdict"] = "FAIL"
    packet_not_pass_path = tamper_dir / "clean_packet_not_pass.json"
    _write_json(packet_not_pass_path, packet_not_pass)
    _record_case("clean_packet_not_pass", "clean_packet_not_pass", packet_not_pass_path)

    missing_case = _copy_report(clean_report)
    missing_case["acceptance_cases"] = [
        case
        for case in missing_case.get("acceptance_cases") or []
        if case.get("case_name") != "missing_acceptance_artifact"
    ]
    missing_case["acceptance_case_count"] = len(missing_case["acceptance_cases"])
    missing_case_path = tamper_dir / "missing_acceptance_case.json"
    _write_json(missing_case_path, missing_case)
    _record_case("missing_acceptance_case", "missing_acceptance_case", missing_case_path)

    invalid_marked_pass = _copy_report(clean_report)
    for case in invalid_marked_pass.get("acceptance_cases") or []:
        if case.get("case_name") == "missing_acceptance_artifact":
            case["actual_verdict"] = "PASS"
            case["detected"] = True
    invalid_marked_pass_path = tamper_dir / "invalid_case_marked_pass.json"
    _write_json(invalid_marked_pass_path, invalid_marked_pass)
    _record_case("invalid_case_marked_pass", "invalid_case_marked_pass", invalid_marked_pass_path)

    valid_marked_fail = _copy_report(clean_report)
    for case in valid_marked_fail.get("acceptance_cases") or []:
        if case.get("case_name") == "valid_final_dry_run_acceptance":
            case["actual_verdict"] = "FAIL"
            case["detected"] = False
    valid_marked_fail_path = tamper_dir / "valid_case_marked_fail.json"
    _write_json(valid_marked_fail_path, valid_marked_fail)
    _record_case("valid_case_marked_fail", "valid_case_marked_fail", valid_marked_fail_path)

    invalid_not_closed = _copy_report(clean_report)
    invalid_not_closed["all_invalid_acceptance_cases_failed_closed"] = False
    invalid_not_closed_path = tamper_dir / "all_invalid_cases_not_failed_closed.json"
    _write_json(invalid_not_closed_path, invalid_not_closed)
    _record_case(
        "all_invalid_cases_not_failed_closed",
        "all_invalid_cases_not_failed_closed",
        invalid_not_closed_path,
    )

    not_dry_run_only = _copy_report(clean_report)
    not_dry_run_only["valid_acceptance_passed_dry_run_only"] = False
    not_dry_run_only_path = tamper_dir / "valid_acceptance_not_dry_run_only.json"
    _write_json(not_dry_run_only_path, not_dry_run_only)
    _record_case(
        "valid_acceptance_not_dry_run_only",
        "valid_acceptance_not_dry_run_only",
        not_dry_run_only_path,
    )

    flag_cases = (
        ("accepted_for_live_memory_write_true", "accepted_for_live_memory_write", True),
        ("accepted_for_vector_db_write_true", "accepted_for_vector_db_write", True),
        ("live_memory_write_allowed_true", "live_memory_write_allowed", True),
        ("vector_db_write_allowed_true", "vector_db_write_allowed", True),
        ("requires_separate_live_write_campaign_false", "requires_separate_live_write_campaign", False),
        ("operator_required_false", "operator_required", False),
        ("dry_run_false", "dry_run", False),
        ("local_only_false", "local_only", False),
        ("model_called_true", "model_called", True),
        ("embeddings_used_true", "embeddings_used", True),
        ("live_memory_written_true", "live_memory_written", True),
        ("live_vector_db_written_true", "live_vector_db_written", True),
        ("account_api_network_accessed_true", "account_api_network_accessed", True),
        ("autonomy_enabled_true", "autonomy_enabled", True),
    )
    for case_name, field_name, value in flag_cases:
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

    still_clean, still_clean_errors = audit_operator_acceptance_gate_report(clean_report_path)
    report.clean_gate_still_passes = still_clean == "PASS" and not still_clean_errors
    if not report.clean_gate_still_passes:
        errors.append(
            f"Clean acceptance gate report no longer passes after tamper copies: {still_clean_errors}"
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


def run_memory_review_approved_promotion_final_readiness_operator_acceptance_gate_tamper_evidence_smoke(
    *,
    base_dir: Path | None = None,
    keep_temp: bool = False,
) -> AcceptanceGateTamperEvidenceReport:
    """Build a clean acceptance gate report and prove tampered variants fail."""
    owned_temp = base_dir is None
    workspace = (
        Path(tempfile.mkdtemp(prefix="elysia_fragt_"))
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
            return AcceptanceGateTamperEvidenceReport(
                verdict="FAIL",
                workspace=str(workspace.resolve()),
                workspace_preserved=(not owned_temp) or keep_temp,
                autonomy_enabled=_read_autonomy_enabled(),
                errors=[f"acceptance_gate_tamper_build_failed: {exc}"],
            )
    finally:
        if owned_temp and not keep_temp:
            shutil.rmtree(workspace, ignore_errors=True)


def format_operator_summary(report: AcceptanceGateTamperEvidenceReport) -> str:
    lines = [
        "Memory review approved promotion final readiness operator acceptance gate tamper evidence smoke",
        "=" * 86,
        f"Verdict: {report.verdict}",
        f"Workspace: {report.workspace}",
        f"Clean gate verdict: {report.clean_gate_verdict}",
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
            "Run local-only Memory review approved promotion final readiness "
            "operator acceptance gate tamper evidence smoke."
        ),
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON to stdout")
    parser.add_argument("--base-dir", type=Path, default=None)
    parser.add_argument("--keep-temp", action="store_true")
    args = parser.parse_args(argv)
    try:
        report = run_memory_review_approved_promotion_final_readiness_operator_acceptance_gate_tamper_evidence_smoke(
            base_dir=args.base_dir,
            keep_temp=args.keep_temp,
        )
    except (ValueError, OSError) as exc:
        report = AcceptanceGateTamperEvidenceReport(
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
