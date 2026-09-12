#!/usr/bin/env python3
"""Dry-run/local smoke proving live-write blockade reports detect tampering.

This smoke builds a valid live-write blockade report from local fixtures in a
temporary workspace, validates the clean report, then writes isolated corrupted
report copies and checks that each one returns FAIL with a specific error
token. It never calls models, embeddings, networks, live accounts, UI routes,
or live runtime memory/vector DB.
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

from run_memory_review_approved_promotion_live_write_blockade_smoke import (  # noqa: E402
    run_memory_review_approved_promotion_live_write_blockade_smoke,
)

REQUIRED_BLOCKADE_REPORT_FIELDS = (
    "verdict",
    "workspace",
    "blockade_path",
    "live_write_blockade_report_path",
    "live_write_blockade_report_valid_json",
    "source_staging_manifest_path",
    "source_staging_manifest_sha256",
    "source_staging_tamper_evidence_verdict",
    "clean_staging_valid",
    "operator_approval_valid",
    "approval_gate_verdict",
    "tamper_evidence_verdict",
    "ready_for_operator_approved_staging",
    "ready_for_live_memory_write",
    "future_live_write_allowed",
    "live_memory_write_requested",
    "live_memory_write_allowed",
    "live_memory_write_denied",
    "live_memory_write_denial_reason",
    "live_memory_write_attempted",
    "live_memory_write_performed",
    "live_memory_write_path",
    "live_memory_write_path_created",
    "vector_db_write_requested",
    "vector_db_write_allowed",
    "vector_db_write_denied",
    "vector_db_write_denial_reason",
    "vector_db_write_attempted",
    "vector_db_write_performed",
    "vector_db_write_path",
    "vector_db_write_path_created",
    "runtime_memory_files_created",
    "vector_db_files_created",
    "promotion_item_count",
    "approved_candidate_count",
    "edited_candidate_count",
    "excluded_rejected_count",
    "operator_required",
    "requires_future_live_write_milestone",
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

UNSAFE_REPORT_METADATA = (
    ("operator_required", False, "operator_required=false"),
    ("dry_run", False, "dry_run=false"),
    ("local_only", False, "local_only=false"),
    ("model_called", True, "model_called=true"),
    ("embeddings_used", True, "embeddings_used=true"),
    ("live_memory_written", True, "live_memory_written=true"),
    ("live_vector_db_written", True, "live_vector_db_written=true"),
    ("account_api_network_accessed", True, "account_api_network_accessed=true"),
    ("autonomy_enabled", True, "autonomy_enabled=true"),
)

REQUIRED_TAMPER_CASES = (
    "malformed_json",
    "missing_required_report_field",
    "source_staging_manifest_hash_mismatch",
    "clean_staging_invalid",
    "staging_tamper_evidence_failed",
    "live_memory_write_allowed",
    "live_memory_write_not_denied",
    "live_memory_write_attempted",
    "live_memory_write_performed",
    "live_memory_write_path_created",
    "vector_db_write_allowed",
    "vector_db_write_not_denied",
    "vector_db_write_attempted",
    "vector_db_write_performed",
    "vector_db_write_path_created",
    "runtime_memory_files_created_nonzero",
    "vector_db_files_created_nonzero",
    "ready_for_live_memory_write_true",
    "future_live_write_allowed_true",
    "future_milestone_not_required",
    "missing_denial_reason",
    "unsafe_metadata",
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
class LiveWriteBlockadeTamperEvidenceReport:
    verdict: str
    workspace: str
    clean_blockade_verdict: str = "UNKNOWN"
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
    clean_blockade_path: str = ""
    clean_blockade_report_path: str = ""
    clean_blockade_still_passes: bool = False
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
        return False
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
    path.write_text(raw, encoding="utf-8", newline="\n")
    return path


def _file_sha256_or_blank(path_value: Any) -> str:
    if not path_value:
        return ""
    path = Path(str(path_value))
    if not path.is_file():
        return ""
    return _sha256_file(path)


def audit_live_write_blockade_report(report_path: Path) -> Tuple[str, List[str]]:
    """Local-only checker for a live-write blockade report.

    Returns a (verdict, errors) tuple. Detects malformed JSON, missing required
    fields, source-staging hash mismatch, flipped safety/blockade flags, nonzero
    created-file counts, missing denial reasons, and unsafe metadata.
    """
    errors: List[str] = []
    if not report_path.is_file():
        return "FAIL", [f"missing_report_file: {report_path}"]

    try:
        report = json.loads(report_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return "FAIL", [f"malformed_json: blockade report is not valid JSON ({exc})"]

    if not isinstance(report, dict):
        return "FAIL", ["malformed_json: blockade report root is not a JSON object"]

    missing_fields = [
        field_name for field_name in REQUIRED_BLOCKADE_REPORT_FIELDS if field_name not in report
    ]
    if missing_fields:
        errors.append("missing_required_report_field: missing " + ", ".join(missing_fields))

    recorded_hash = str(report.get("source_staging_manifest_sha256") or "")
    actual_hash = _file_sha256_or_blank(report.get("source_staging_manifest_path"))
    if "source_staging_manifest_sha256" in report and recorded_hash != actual_hash:
        errors.append(
            "source_staging_manifest_hash_mismatch: "
            "source_staging_manifest_sha256 does not match file"
        )

    if report.get("clean_staging_valid") is False:
        errors.append("clean_staging_invalid: clean_staging_valid=false")

    if (
        "source_staging_tamper_evidence_verdict" in report
        and str(report.get("source_staging_tamper_evidence_verdict") or "") != "PASS"
    ):
        errors.append(
            "staging_tamper_evidence_failed: source_staging_tamper_evidence_verdict is not PASS"
        )
    if (
        "tamper_evidence_verdict" in report
        and str(report.get("tamper_evidence_verdict") or "") != "PASS"
    ):
        errors.append("staging_tamper_evidence_failed: tamper_evidence_verdict is not PASS")

    if (
        "approval_gate_verdict" in report
        and str(report.get("approval_gate_verdict") or "") != "PASS"
    ):
        errors.append("approval_gate_verdict_not_pass: approval_gate_verdict is not PASS")
    if "operator_approval_valid" in report and report.get("operator_approval_valid") is not True:
        errors.append("operator_approval_valid_not_true: operator_approval_valid is not true")
    if (
        "ready_for_operator_approved_staging" in report
        and report.get("ready_for_operator_approved_staging") is not True
    ):
        errors.append(
            "ready_for_operator_approved_staging_not_true: "
            "ready_for_operator_approved_staging is not true"
        )

    if report.get("live_memory_write_allowed") is True:
        errors.append("live_memory_write_allowed: live_memory_write_allowed=true")
    if "live_memory_write_denied" in report and report.get("live_memory_write_denied") is not True:
        errors.append("live_memory_write_not_denied: live_memory_write_denied is not true")
    if report.get("live_memory_write_attempted") is True:
        errors.append("live_memory_write_attempted: live_memory_write_attempted=true")
    if report.get("live_memory_write_performed") is True:
        errors.append("live_memory_write_performed: live_memory_write_performed=true")
    if report.get("live_memory_write_path_created") is True:
        errors.append("live_memory_write_path_created: live_memory_write_path_created=true")

    if report.get("vector_db_write_allowed") is True:
        errors.append("vector_db_write_allowed: vector_db_write_allowed=true")
    if "vector_db_write_denied" in report and report.get("vector_db_write_denied") is not True:
        errors.append("vector_db_write_not_denied: vector_db_write_denied is not true")
    if report.get("vector_db_write_attempted") is True:
        errors.append("vector_db_write_attempted: vector_db_write_attempted=true")
    if report.get("vector_db_write_performed") is True:
        errors.append("vector_db_write_performed: vector_db_write_performed=true")
    if report.get("vector_db_write_path_created") is True:
        errors.append("vector_db_write_path_created: vector_db_write_path_created=true")

    runtime_count = report.get("runtime_memory_files_created")
    if isinstance(runtime_count, int) and runtime_count > 0:
        errors.append(
            "runtime_memory_files_created_nonzero: "
            f"runtime_memory_files_created={runtime_count}"
        )
    vector_count = report.get("vector_db_files_created")
    if isinstance(vector_count, int) and vector_count > 0:
        errors.append(
            f"vector_db_files_created_nonzero: vector_db_files_created={vector_count}"
        )

    if report.get("ready_for_live_memory_write") is True:
        errors.append("ready_for_live_memory_write_true: ready_for_live_memory_write=true")
    if report.get("future_live_write_allowed") is True:
        errors.append("future_live_write_allowed_true: future_live_write_allowed=true")
    if (
        "requires_future_live_write_milestone" in report
        and report.get("requires_future_live_write_milestone") is not True
    ):
        errors.append(
            "future_milestone_not_required: requires_future_live_write_milestone is not true"
        )

    memory_reason = str(report.get("live_memory_write_denial_reason") or "").strip()
    vector_reason = str(report.get("vector_db_write_denial_reason") or "").strip()
    if "live_memory_write_denial_reason" in report and not memory_reason:
        errors.append("missing_denial_reason: live_memory_write_denial_reason is empty")
    if "vector_db_write_denial_reason" in report and not vector_reason:
        errors.append("missing_denial_reason: vector_db_write_denial_reason is empty")

    for field_name, unsafe_value, label in UNSAFE_REPORT_METADATA:
        if field_name in report and report.get(field_name) is unsafe_value:
            errors.append(f"unsafe_metadata: report {label}")

    verdict = "PASS" if not errors else "FAIL"
    return verdict, errors


def _load_clean_blockade(workspace: Path) -> Tuple[Path, Dict[str, Any], Dict[str, str]]:
    blockade_report = run_memory_review_approved_promotion_live_write_blockade_smoke(
        base_dir=workspace,
        keep_temp=True,
    )
    if blockade_report.verdict != "PASS":
        raise ValueError(
            "Live-write blockade smoke did not pass while building clean report: "
            + "; ".join(blockade_report.errors)
        )
    report_path = Path(blockade_report.live_write_blockade_report_path)
    if not report_path.is_file():
        raise ValueError(f"Clean live-write blockade report was not created: {report_path}")
    report = json.loads(report_path.read_text(encoding="utf-8"))
    artifact_paths = {
        "clean_blockade_dir": blockade_report.blockade_path,
        "clean_blockade_report": str(report_path.resolve()),
        "clean_blockade_readme": str(Path(blockade_report.blockade_readme_path).resolve()),
        "clean_source_staging_manifest": str(
            Path(blockade_report.source_staging_manifest_path).resolve()
        ),
    }
    return report_path, report, artifact_paths


def _copy_report(report: Dict[str, Any]) -> Dict[str, Any]:
    return copy.deepcopy(report)


def _error_type(error: str) -> str:
    return error.split(":", 1)[0].strip()


def _run_tamper_flow(
    workspace: Path,
    *,
    workspace_preserved: bool,
) -> LiveWriteBlockadeTamperEvidenceReport:
    errors: List[str] = []
    case_paths: Dict[str, str] = {}
    report = LiveWriteBlockadeTamperEvidenceReport(
        verdict="FAIL",
        workspace=str(workspace.resolve()),
        workspace_preserved=workspace_preserved,
        autonomy_enabled=_read_autonomy_enabled(),
    )
    if report.autonomy_enabled:
        report.errors.append(
            "Autonomy is enabled; live-write blockade tamper evidence smoke is blocked."
        )
        return report

    clean_report_path, clean_report, artifact_paths = _load_clean_blockade(workspace)
    report.clean_blockade_report_path = str(clean_report_path.resolve())
    report.clean_blockade_path = artifact_paths.get("clean_blockade_dir", "")
    tamper_dir = workspace / "tampered_live_write_blockade_reports"
    tamper_dir.mkdir(parents=True, exist_ok=True)

    clean_verdict, clean_errors = audit_live_write_blockade_report(clean_report_path)
    report.clean_blockade_verdict = clean_verdict
    report.clean_blockade_still_passes = clean_verdict == "PASS" and not clean_errors
    if not report.clean_blockade_still_passes:
        errors.append(f"Clean live-write blockade report did not pass: {clean_errors}")

    cases: List[TamperCaseResult] = []

    def _record_case(name: str, expected_token: str, path: Path) -> None:
        verdict, case_errors = audit_live_write_blockade_report(path)
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

    malformed_path = tamper_dir / "malformed_json_report.json"
    _write_raw(malformed_path, "{ this is not valid json\n")
    _record_case("malformed_json", "malformed_json", malformed_path)

    missing_field = _copy_report(clean_report)
    missing_field.pop("workspace", None)
    missing_field_path = tamper_dir / "missing_required_report_field.json"
    _write_json(missing_field_path, missing_field)
    _record_case("missing_required_report_field", "missing_required_report_field", missing_field_path)

    hash_mismatch = _copy_report(clean_report)
    hash_mismatch["source_staging_manifest_sha256"] = "0" * 64
    hash_mismatch_path = tamper_dir / "source_staging_manifest_hash_mismatch.json"
    _write_json(hash_mismatch_path, hash_mismatch)
    _record_case(
        "source_staging_manifest_hash_mismatch",
        "source_staging_manifest_hash_mismatch",
        hash_mismatch_path,
    )

    clean_invalid = _copy_report(clean_report)
    clean_invalid["clean_staging_valid"] = False
    clean_invalid_path = tamper_dir / "clean_staging_invalid.json"
    _write_json(clean_invalid_path, clean_invalid)
    _record_case("clean_staging_invalid", "clean_staging_invalid", clean_invalid_path)

    tamper_failed = _copy_report(clean_report)
    tamper_failed["source_staging_tamper_evidence_verdict"] = "FAIL"
    tamper_failed_path = tamper_dir / "staging_tamper_evidence_failed.json"
    _write_json(tamper_failed_path, tamper_failed)
    _record_case("staging_tamper_evidence_failed", "staging_tamper_evidence_failed", tamper_failed_path)

    memory_allowed = _copy_report(clean_report)
    memory_allowed["live_memory_write_allowed"] = True
    memory_allowed_path = tamper_dir / "live_memory_write_allowed.json"
    _write_json(memory_allowed_path, memory_allowed)
    _record_case("live_memory_write_allowed", "live_memory_write_allowed", memory_allowed_path)

    memory_not_denied = _copy_report(clean_report)
    memory_not_denied["live_memory_write_denied"] = False
    memory_not_denied_path = tamper_dir / "live_memory_write_not_denied.json"
    _write_json(memory_not_denied_path, memory_not_denied)
    _record_case("live_memory_write_not_denied", "live_memory_write_not_denied", memory_not_denied_path)

    memory_attempted = _copy_report(clean_report)
    memory_attempted["live_memory_write_attempted"] = True
    memory_attempted_path = tamper_dir / "live_memory_write_attempted.json"
    _write_json(memory_attempted_path, memory_attempted)
    _record_case("live_memory_write_attempted", "live_memory_write_attempted", memory_attempted_path)

    memory_performed = _copy_report(clean_report)
    memory_performed["live_memory_write_performed"] = True
    memory_performed_path = tamper_dir / "live_memory_write_performed.json"
    _write_json(memory_performed_path, memory_performed)
    _record_case("live_memory_write_performed", "live_memory_write_performed", memory_performed_path)

    memory_path_created = _copy_report(clean_report)
    memory_path_created["live_memory_write_path_created"] = True
    memory_path_created_path = tamper_dir / "live_memory_write_path_created.json"
    _write_json(memory_path_created_path, memory_path_created)
    _record_case(
        "live_memory_write_path_created",
        "live_memory_write_path_created",
        memory_path_created_path,
    )

    vector_allowed = _copy_report(clean_report)
    vector_allowed["vector_db_write_allowed"] = True
    vector_allowed_path = tamper_dir / "vector_db_write_allowed.json"
    _write_json(vector_allowed_path, vector_allowed)
    _record_case("vector_db_write_allowed", "vector_db_write_allowed", vector_allowed_path)

    vector_not_denied = _copy_report(clean_report)
    vector_not_denied["vector_db_write_denied"] = False
    vector_not_denied_path = tamper_dir / "vector_db_write_not_denied.json"
    _write_json(vector_not_denied_path, vector_not_denied)
    _record_case("vector_db_write_not_denied", "vector_db_write_not_denied", vector_not_denied_path)

    vector_attempted = _copy_report(clean_report)
    vector_attempted["vector_db_write_attempted"] = True
    vector_attempted_path = tamper_dir / "vector_db_write_attempted.json"
    _write_json(vector_attempted_path, vector_attempted)
    _record_case("vector_db_write_attempted", "vector_db_write_attempted", vector_attempted_path)

    vector_performed = _copy_report(clean_report)
    vector_performed["vector_db_write_performed"] = True
    vector_performed_path = tamper_dir / "vector_db_write_performed.json"
    _write_json(vector_performed_path, vector_performed)
    _record_case("vector_db_write_performed", "vector_db_write_performed", vector_performed_path)

    vector_path_created = _copy_report(clean_report)
    vector_path_created["vector_db_write_path_created"] = True
    vector_path_created_path = tamper_dir / "vector_db_write_path_created.json"
    _write_json(vector_path_created_path, vector_path_created)
    _record_case("vector_db_write_path_created", "vector_db_write_path_created", vector_path_created_path)

    runtime_nonzero = _copy_report(clean_report)
    runtime_nonzero["runtime_memory_files_created"] = 1
    runtime_nonzero_path = tamper_dir / "runtime_memory_files_created_nonzero.json"
    _write_json(runtime_nonzero_path, runtime_nonzero)
    _record_case(
        "runtime_memory_files_created_nonzero",
        "runtime_memory_files_created_nonzero",
        runtime_nonzero_path,
    )

    vector_nonzero = _copy_report(clean_report)
    vector_nonzero["vector_db_files_created"] = 1
    vector_nonzero_path = tamper_dir / "vector_db_files_created_nonzero.json"
    _write_json(vector_nonzero_path, vector_nonzero)
    _record_case(
        "vector_db_files_created_nonzero",
        "vector_db_files_created_nonzero",
        vector_nonzero_path,
    )

    ready_live = _copy_report(clean_report)
    ready_live["ready_for_live_memory_write"] = True
    ready_live_path = tamper_dir / "ready_for_live_memory_write_true.json"
    _write_json(ready_live_path, ready_live)
    _record_case("ready_for_live_memory_write_true", "ready_for_live_memory_write_true", ready_live_path)

    future_allowed = _copy_report(clean_report)
    future_allowed["future_live_write_allowed"] = True
    future_allowed_path = tamper_dir / "future_live_write_allowed_true.json"
    _write_json(future_allowed_path, future_allowed)
    _record_case("future_live_write_allowed_true", "future_live_write_allowed_true", future_allowed_path)

    milestone_off = _copy_report(clean_report)
    milestone_off["requires_future_live_write_milestone"] = False
    milestone_off_path = tamper_dir / "future_milestone_not_required.json"
    _write_json(milestone_off_path, milestone_off)
    _record_case("future_milestone_not_required", "future_milestone_not_required", milestone_off_path)

    missing_reason = _copy_report(clean_report)
    missing_reason["live_memory_write_denial_reason"] = ""
    missing_reason_path = tamper_dir / "missing_denial_reason.json"
    _write_json(missing_reason_path, missing_reason)
    _record_case("missing_denial_reason", "missing_denial_reason", missing_reason_path)

    unsafe = _copy_report(clean_report)
    unsafe["dry_run"] = False
    unsafe["local_only"] = False
    unsafe["autonomy_enabled"] = True
    unsafe["model_called"] = True
    unsafe["embeddings_used"] = True
    unsafe["account_api_network_accessed"] = True
    unsafe_path = tamper_dir / "unsafe_metadata.json"
    _write_json(unsafe_path, unsafe)
    _record_case("unsafe_metadata", "unsafe_metadata", unsafe_path)

    report.tamper_case_count = len(cases)
    report.tamper_cases = [case.to_dict() for case in cases]
    report.detected_error_types = sorted(
        {
            case.detected_error_type
            for case in cases
            if case.detected and case.detected_error_type
        }
    )
    report.all_tamper_cases_detected = all(case.detected for case in cases) and {
        case.case_name for case in cases
    } == set(REQUIRED_TAMPER_CASES)

    reverify_verdict, reverify_errors = audit_live_write_blockade_report(clean_report_path)
    if reverify_verdict != "PASS" or reverify_errors:
        report.clean_blockade_still_passes = False
        errors.append(
            f"Clean live-write blockade report regressed after tamper cases: {reverify_errors}"
        )

    case_path_objects = [Path(path) for path in case_paths.values()]
    report.tamper_paths_inside_workspace = all(
        _path_inside_workspace(path, workspace) for path in [tamper_dir, *case_path_objects]
    )

    if not report.clean_blockade_still_passes:
        errors.append("Clean live-write blockade report did not remain PASS.")
    if not report.all_tamper_cases_detected:
        errors.append("One or more required live-write blockade tamper cases were not detected.")
    if any(case.actual_verdict != "FAIL" for case in cases):
        errors.append("A tampered blockade report did not return verdict=FAIL.")
    if not report.tamper_paths_inside_workspace:
        errors.append("One or more tamper report paths are outside the temp workspace.")
    if report.tamper_case_count != len(REQUIRED_TAMPER_CASES):
        errors.append("tamper_case_count does not match the required blockade tamper-case set.")

    for flag_name in (
        "model_called",
        "embeddings_used",
        "live_memory_written",
        "live_vector_db_written",
        "account_api_network_accessed",
        "autonomy_enabled",
    ):
        if getattr(report, flag_name):
            errors.append(f"{flag_name} unexpectedly true.")

    report.artifact_paths = {
        **artifact_paths,
        "tamper_dir": str(tamper_dir.resolve()),
        **{f"tampered_{name}": path for name, path in case_paths.items()},
    }
    report.errors = errors
    report.verdict = "PASS" if not errors else "FAIL"
    return report


def run_memory_review_approved_promotion_live_write_blockade_tamper_evidence_smoke(
    *,
    base_dir: Path | None = None,
    keep_temp: bool = False,
) -> LiveWriteBlockadeTamperEvidenceReport:
    """Build a clean blockade report and prove tampered variants fail."""
    owned_temp = base_dir is None
    workspace = (
        Path(tempfile.mkdtemp(prefix="elysia_lwbte_"))
        if owned_temp
        else _reject_dangerous_base(Path(base_dir))
    )
    workspace.mkdir(parents=True, exist_ok=True)
    try:
        return _run_tamper_flow(
            workspace,
            workspace_preserved=(not owned_temp) or keep_temp,
        )
    finally:
        if owned_temp and not keep_temp:
            shutil.rmtree(workspace, ignore_errors=True)


def format_operator_summary(report: LiveWriteBlockadeTamperEvidenceReport) -> str:
    lines = [
        "Memory review approved promotion live-write blockade tamper evidence smoke",
        "=" * 74,
        f"Verdict: {report.verdict}",
        f"Workspace: {report.workspace}",
        f"Workspace preserved: {report.workspace_preserved}",
        f"Clean blockade path: {report.clean_blockade_path}",
        f"Clean blockade verdict: {report.clean_blockade_verdict}",
        f"Clean blockade still passes: {report.clean_blockade_still_passes}",
        f"Tamper case count: {report.tamper_case_count}",
        f"All tamper cases detected: {report.all_tamper_cases_detected}",
        f"Detected error types: {', '.join(report.detected_error_types)}",
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
            "Run local-only Memory review approved promotion live-write blockade "
            "tamper evidence smoke."
        ),
    )
    parser.add_argument("--json", action="store_true", help="Print JSON smoke result")
    parser.add_argument(
        "--base-dir",
        type=Path,
        default=None,
        help="Optional workspace root. Defaults to a temporary directory.",
    )
    parser.add_argument(
        "--keep-temp",
        action="store_true",
        help="Preserve an automatically-created temporary workspace.",
    )
    args = parser.parse_args(argv)

    try:
        report = run_memory_review_approved_promotion_live_write_blockade_tamper_evidence_smoke(
            base_dir=args.base_dir,
            keep_temp=args.keep_temp,
        )
    except ValueError as exc:
        report = LiveWriteBlockadeTamperEvidenceReport(
            verdict="FAIL",
            workspace=str(args.base_dir or ""),
            workspace_preserved=False,
            autonomy_enabled=_read_autonomy_enabled(),
            errors=[str(exc)],
        )

    if args.json:
        print(json.dumps(report.to_dict(), indent=2, ensure_ascii=False))
    else:
        print(format_operator_summary(report))
    return 0 if report.verdict == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
