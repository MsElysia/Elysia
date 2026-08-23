#!/usr/bin/env python3
"""Dry-run/local smoke proving operator-approved staging detects tampering.

This smoke builds a valid operator-approved staging package from local fixtures
in a temporary workspace, validates the clean package, then writes isolated
corrupted staging-manifest copies and checks that each one returns FAIL with a
specific error token. It never calls models, embeddings, networks, live
accounts, UI routes, or live runtime memory/vector DB.
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

from run_memory_review_approved_promotion_operator_approval_gate_smoke import (  # noqa: E402
    APPROVAL_TOKEN_PHRASE,
)
from run_memory_review_approved_promotion_operator_approved_staging_smoke import (  # noqa: E402
    run_memory_review_approved_promotion_operator_approved_staging_smoke,
)

REQUIRED_STAGING_MANIFEST_FIELDS = (
    "verdict",
    "workspace",
    "staging_path",
    "operator_approved_staging_manifest_path",
    "operator_approved_staging_manifest_valid_json",
    "promotion_bundle_path",
    "promotion_manifest_path",
    "promotion_manifest_sha256",
    "operator_handoff_path",
    "operator_handoff_sha256",
    "operator_approval_gate_path",
    "operator_approval_gate_sha256",
    "approval_token_phrase",
    "approval_gate_verdict",
    "ready_for_operator_approved_staging",
    "ready_for_live_memory_write",
    "future_live_write_allowed",
    "requires_explicit_operator_approval",
    "operator_approval_valid",
    "tamper_evidence_verdict",
    "all_tamper_cases_detected",
    "promotion_item_count",
    "approved_candidate_count",
    "edited_candidate_count",
    "excluded_rejected_count",
    "staged_items",
    "staging_readme_path",
    "staging_readme_sha256",
    "live_write_blocked_reason",
    "staging_paths_inside_workspace",
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

REQUIRED_STAGED_ITEM_FIELDS = (
    "candidate_id",
    "decision_id",
    "decision_type",
    "source_type",
    "promoted_text",
    "promoted_text_sha256",
    "candidate_sha256",
    "source_handoff_sha256",
    "source_approval_gate_sha256",
    "ready_for_operator_approved_staging",
    "ready_for_live_memory_write",
    "requires_explicit_operator_approval",
    "live_memory_written",
    "live_vector_db_written",
)

UNSAFE_MANIFEST_METADATA = (
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

UNSAFE_STAGED_ITEM_METADATA = (
    ("live_memory_written", True, "live_memory_written=true"),
    ("live_vector_db_written", True, "live_vector_db_written=true"),
    ("requires_explicit_operator_approval", False, "requires_explicit_operator_approval=false"),
)

REQUIRED_TAMPER_CASES = (
    "malformed_json",
    "missing_required_manifest_field",
    "missing_required_staged_item_field",
    "promoted_text_hash_mismatch",
    "promotion_manifest_hash_mismatch",
    "operator_handoff_hash_mismatch",
    "approval_gate_hash_mismatch",
    "rejected_candidate_included",
    "staging_item_count_mismatch",
    "unsafe_metadata",
    "live_write_unblocked",
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
class OperatorApprovedStagingTamperEvidenceReport:
    verdict: str
    workspace: str
    clean_staging_verdict: str = "UNKNOWN"
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
    clean_staging_path: str = ""
    clean_staging_manifest_path: str = ""
    clean_staging_still_passes: bool = False
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


def _sha256_bytes(data: bytes) -> str:
    digest = hashlib.sha256()
    digest.update(data)
    return digest.hexdigest()


def _sha256_text(text: str) -> str:
    return _sha256_bytes(text.encode("utf-8"))


def _sha256_file(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


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


def _promotion_manifest_content_hash(path_value: Any) -> str:
    if not path_value:
        return ""
    path = Path(str(path_value))
    if not path.is_file():
        return ""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ""
    if not isinstance(payload, dict):
        return ""
    payload_without_hash = dict(payload)
    payload_without_hash.pop("promotion_manifest_sha256", None)
    serialized = json.dumps(payload_without_hash, indent=2, ensure_ascii=False) + "\n"
    return _sha256_bytes(serialized.encode("utf-8"))


def audit_operator_approved_staging_manifest(
    manifest_path: Path,
) -> Tuple[str, List[str]]:
    """Local-only checker for an operator-approved staging manifest.

    Returns a (verdict, errors) tuple. Detects malformed JSON, missing required
    manifest and staged-item fields, hash mismatches, rejected inclusion, item
    count mismatches, unsafe metadata, and live-write unblocking.
    """
    errors: List[str] = []
    if not manifest_path.is_file():
        return "FAIL", [f"missing_manifest_file: {manifest_path}"]

    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return "FAIL", [f"malformed_json: staging manifest is not valid JSON ({exc})"]

    if not isinstance(manifest, dict):
        return "FAIL", ["malformed_json: staging manifest root is not a JSON object"]

    missing_manifest_fields = [
        field_name
        for field_name in REQUIRED_STAGING_MANIFEST_FIELDS
        if field_name not in manifest
    ]
    if missing_manifest_fields:
        errors.append(
            "missing_required_manifest_field: missing "
            + ", ".join(missing_manifest_fields)
        )

    staged_items = manifest.get("staged_items")
    if not isinstance(staged_items, list):
        errors.append("missing_required_manifest_field: staged_items is not a list")
        staged_items = []

    promotion_item_count = manifest.get("promotion_item_count")
    if not isinstance(promotion_item_count, int) or promotion_item_count != len(staged_items):
        errors.append(
            "staging_item_count_mismatch: "
            f"promotion_item_count={promotion_item_count!r} actual_items={len(staged_items)}"
        )

    for field_name, unsafe_value, label in UNSAFE_MANIFEST_METADATA:
        if field_name in manifest and manifest.get(field_name) is unsafe_value:
            errors.append(f"unsafe_metadata: manifest {label}")

    if manifest.get("ready_for_live_memory_write") is True:
        errors.append("live_write_unblocked: ready_for_live_memory_write=true")
    if manifest.get("future_live_write_allowed") is True:
        errors.append("live_write_unblocked: future_live_write_allowed=true")

    if (
        "approval_token_phrase" in manifest
        and str(manifest.get("approval_token_phrase") or "") != APPROVAL_TOKEN_PHRASE
    ):
        errors.append("approval_token_phrase_not_recorded: unexpected approval token phrase")

    if (
        "tamper_evidence_verdict" in manifest
        and str(manifest.get("tamper_evidence_verdict") or "") != "PASS"
    ):
        errors.append("tamper_evidence_verdict_not_pass: tamper_evidence_verdict is not PASS")

    if (
        "approval_gate_verdict" in manifest
        and str(manifest.get("approval_gate_verdict") or "") != "PASS"
    ):
        errors.append("approval_gate_verdict_not_pass: approval_gate_verdict is not PASS")

    if "operator_approval_valid" in manifest and manifest.get("operator_approval_valid") is not True:
        errors.append("operator_approval_valid_not_true: operator_approval_valid is not true")

    if (
        "ready_for_operator_approved_staging" in manifest
        and manifest.get("ready_for_operator_approved_staging") is not True
    ):
        errors.append(
            "ready_for_operator_approved_staging_not_true: "
            "ready_for_operator_approved_staging is not true"
        )

    recorded_promotion_hash = str(manifest.get("promotion_manifest_sha256") or "")
    actual_promotion_hash = _promotion_manifest_content_hash(manifest.get("promotion_manifest_path"))
    if "promotion_manifest_sha256" in manifest and recorded_promotion_hash != actual_promotion_hash:
        errors.append(
            "promotion_manifest_hash_mismatch: promotion_manifest_sha256 does not match file"
        )

    recorded_handoff_hash = str(manifest.get("operator_handoff_sha256") or "")
    actual_handoff_hash = _file_sha256_or_blank(manifest.get("operator_handoff_path"))
    if "operator_handoff_sha256" in manifest and recorded_handoff_hash != actual_handoff_hash:
        errors.append(
            "operator_handoff_hash_mismatch: operator_handoff_sha256 does not match file"
        )

    recorded_gate_hash = str(manifest.get("operator_approval_gate_sha256") or "")
    actual_gate_hash = _file_sha256_or_blank(manifest.get("operator_approval_gate_path"))
    if "operator_approval_gate_sha256" in manifest and recorded_gate_hash != actual_gate_hash:
        errors.append(
            "approval_gate_hash_mismatch: operator_approval_gate_sha256 does not match file"
        )

    approved_included = False
    edited_included = False
    for index, item in enumerate(staged_items, start=1):
        if not isinstance(item, dict):
            errors.append(f"missing_required_staged_item_field: item {index} is not an object")
            continue

        missing_item_fields = [
            field_name for field_name in REQUIRED_STAGED_ITEM_FIELDS if field_name not in item
        ]
        if missing_item_fields:
            errors.append(
                "missing_required_staged_item_field: "
                f"item {index} missing {', '.join(missing_item_fields)}"
            )

        candidate_id = str(item.get("candidate_id") or "")
        decision_type = str(item.get("decision_type") or "").strip().lower()
        if decision_type == "approved":
            approved_included = True
        elif decision_type == "edited":
            edited_included = True
        elif decision_type == "rejected":
            errors.append(
                "rejected_candidate_included: "
                f"item {index} candidate_id={candidate_id!r}"
            )

        promoted_text = str(item.get("promoted_text") or "")
        promoted_hash = str(item.get("promoted_text_sha256") or "")
        if "promoted_text_sha256" in item and promoted_hash != _sha256_text(promoted_text):
            errors.append(
                "promoted_text_hash_mismatch: "
                f"item {index} candidate_id={candidate_id!r}"
            )

        item_handoff_hash = str(item.get("source_handoff_sha256") or "")
        if (
            "source_handoff_sha256" in item
            and recorded_handoff_hash
            and item_handoff_hash != recorded_handoff_hash
        ):
            errors.append(
                "operator_handoff_hash_mismatch: "
                f"item {index} source_handoff_sha256 does not match staging handoff hash"
            )

        item_gate_hash = str(item.get("source_approval_gate_sha256") or "")
        if (
            "source_approval_gate_sha256" in item
            and recorded_gate_hash
            and item_gate_hash != recorded_gate_hash
        ):
            errors.append(
                "approval_gate_hash_mismatch: "
                f"item {index} source_approval_gate_sha256 does not match staging gate hash"
            )

        if item.get("ready_for_live_memory_write") is True:
            errors.append(
                f"live_write_unblocked: item {index} ready_for_live_memory_write=true"
            )

        for field_name, unsafe_value, label in UNSAFE_STAGED_ITEM_METADATA:
            if field_name in item and item.get(field_name) is unsafe_value:
                errors.append(f"unsafe_metadata: item {index} {label}")

    if staged_items and not approved_included:
        errors.append("approved_candidates_missing: no approved staged item present")
    if staged_items and not edited_included:
        errors.append("edited_candidates_missing: no edited staged item present")

    verdict = "PASS" if not errors else "FAIL"
    return verdict, errors


def _load_clean_staging(workspace: Path) -> Tuple[Path, Dict[str, Any], Dict[str, str]]:
    staging_workspace = Path(
        tempfile.mkdtemp(prefix="clean_staging_", dir=str(workspace.resolve()))
    )
    staging_report = run_memory_review_approved_promotion_operator_approved_staging_smoke(
        base_dir=staging_workspace,
        keep_temp=True,
    )
    if staging_report.verdict != "PASS":
        raise ValueError(
            "Operator-approved staging smoke did not pass while building clean package: "
            + "; ".join(staging_report.errors)
        )
    manifest_path = Path(staging_report.operator_approved_staging_manifest_path)
    if not manifest_path.is_file():
        raise ValueError(f"Clean staging manifest was not created: {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    artifact_paths = {
        "clean_staging_workspace": str(staging_workspace.resolve()),
        "clean_staging_dir": staging_report.staging_path,
        "clean_staging_manifest": str(manifest_path.resolve()),
        "clean_staging_readme": str(Path(staging_report.staging_readme_path).resolve()),
        "clean_promotion_manifest": str(Path(staging_report.promotion_manifest_path).resolve()),
        "clean_operator_handoff": str(Path(staging_report.operator_handoff_path).resolve()),
        "clean_operator_approval_gate": str(
            Path(staging_report.operator_approval_gate_path).resolve()
        ),
    }
    return manifest_path, manifest, artifact_paths


def _copy_manifest(manifest: Dict[str, Any]) -> Dict[str, Any]:
    return copy.deepcopy(manifest)


def _first_item(manifest: Dict[str, Any]) -> Dict[str, Any]:
    items = manifest.get("staged_items")
    if not isinstance(items, list) or not items or not isinstance(items[0], dict):
        raise ValueError("Clean staging manifest does not contain a staged item template.")
    return items[0]


def _make_rejected_item(template: Dict[str, Any]) -> Dict[str, Any]:
    text = "Reject branch fixture: rejected-only note should never be staged."
    item = dict(template)
    item.update(
        {
            "candidate_id": "rejected-staging-tamper-candidate",
            "decision_id": "rejected-staging-tamper-decision",
            "decision_type": "rejected",
            "promoted_text": text,
            "promoted_text_sha256": _sha256_text(text),
            "candidate_sha256": _sha256_text(text),
            "ready_for_operator_approved_staging": True,
            "ready_for_live_memory_write": False,
            "requires_explicit_operator_approval": True,
            "live_memory_written": False,
            "live_vector_db_written": False,
        }
    )
    return item


def _error_type(error: str) -> str:
    return error.split(":", 1)[0].strip()


def _run_tamper_flow(
    workspace: Path,
    *,
    workspace_preserved: bool,
) -> OperatorApprovedStagingTamperEvidenceReport:
    errors: List[str] = []
    case_paths: Dict[str, str] = {}
    report = OperatorApprovedStagingTamperEvidenceReport(
        verdict="FAIL",
        workspace=str(workspace.resolve()),
        workspace_preserved=workspace_preserved,
        autonomy_enabled=_read_autonomy_enabled(),
    )
    if report.autonomy_enabled:
        report.errors.append(
            "Autonomy is enabled; operator-approved staging tamper evidence smoke is blocked."
        )
        return report

    clean_manifest_path, clean_manifest, artifact_paths = _load_clean_staging(workspace)
    report.clean_staging_manifest_path = str(clean_manifest_path.resolve())
    report.clean_staging_path = artifact_paths.get("clean_staging_dir", "")
    tamper_dir = workspace / "tampered_operator_approved_staging_manifests"
    tamper_dir.mkdir(parents=True, exist_ok=True)

    clean_verdict, clean_errors = audit_operator_approved_staging_manifest(clean_manifest_path)
    report.clean_staging_verdict = clean_verdict
    report.clean_staging_still_passes = clean_verdict == "PASS" and not clean_errors
    if not report.clean_staging_still_passes:
        errors.append(f"Clean operator-approved staging package did not pass: {clean_errors}")

    cases: List[TamperCaseResult] = []

    def _record_case(name: str, expected_token: str, path: Path) -> None:
        verdict, case_errors = audit_operator_approved_staging_manifest(path)
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

    malformed_path = tamper_dir / "malformed_json_manifest.json"
    _write_raw(malformed_path, "{ this is not valid json\n")
    _record_case("malformed_json", "malformed_json", malformed_path)

    missing_manifest = _copy_manifest(clean_manifest)
    missing_manifest.pop("workspace", None)
    missing_manifest_path = tamper_dir / "missing_required_manifest_field.json"
    _write_json(missing_manifest_path, missing_manifest)
    _record_case(
        "missing_required_manifest_field",
        "missing_required_manifest_field",
        missing_manifest_path,
    )

    missing_item = _copy_manifest(clean_manifest)
    _first_item(missing_item).pop("promoted_text", None)
    missing_item_path = tamper_dir / "missing_required_staged_item_field.json"
    _write_json(missing_item_path, missing_item)
    _record_case(
        "missing_required_staged_item_field",
        "missing_required_staged_item_field",
        missing_item_path,
    )

    promoted_hash = _copy_manifest(clean_manifest)
    _first_item(promoted_hash)["promoted_text_sha256"] = "0" * 64
    promoted_hash_path = tamper_dir / "promoted_text_hash_mismatch.json"
    _write_json(promoted_hash_path, promoted_hash)
    _record_case(
        "promoted_text_hash_mismatch",
        "promoted_text_hash_mismatch",
        promoted_hash_path,
    )

    promotion_hash = _copy_manifest(clean_manifest)
    promotion_hash["promotion_manifest_sha256"] = "0" * 64
    promotion_hash_path = tamper_dir / "promotion_manifest_hash_mismatch.json"
    _write_json(promotion_hash_path, promotion_hash)
    _record_case(
        "promotion_manifest_hash_mismatch",
        "promotion_manifest_hash_mismatch",
        promotion_hash_path,
    )

    handoff_hash = _copy_manifest(clean_manifest)
    handoff_hash["operator_handoff_sha256"] = "0" * 64
    handoff_hash_path = tamper_dir / "operator_handoff_hash_mismatch.json"
    _write_json(handoff_hash_path, handoff_hash)
    _record_case(
        "operator_handoff_hash_mismatch",
        "operator_handoff_hash_mismatch",
        handoff_hash_path,
    )

    gate_hash = _copy_manifest(clean_manifest)
    gate_hash["operator_approval_gate_sha256"] = "0" * 64
    gate_hash_path = tamper_dir / "approval_gate_hash_mismatch.json"
    _write_json(gate_hash_path, gate_hash)
    _record_case(
        "approval_gate_hash_mismatch",
        "approval_gate_hash_mismatch",
        gate_hash_path,
    )

    rejected_included = _copy_manifest(clean_manifest)
    rejected_item = _make_rejected_item(_first_item(rejected_included))
    rejected_included["staged_items"].append(rejected_item)
    rejected_included["promotion_item_count"] = len(rejected_included["staged_items"])
    rejected_path = tamper_dir / "rejected_candidate_included.json"
    _write_json(rejected_path, rejected_included)
    _record_case(
        "rejected_candidate_included",
        "rejected_candidate_included",
        rejected_path,
    )

    count_mismatch = _copy_manifest(clean_manifest)
    count_mismatch["promotion_item_count"] = len(count_mismatch["staged_items"]) + 1
    count_mismatch_path = tamper_dir / "staging_item_count_mismatch.json"
    _write_json(count_mismatch_path, count_mismatch)
    _record_case(
        "staging_item_count_mismatch",
        "staging_item_count_mismatch",
        count_mismatch_path,
    )

    unsafe = _copy_manifest(clean_manifest)
    unsafe["dry_run"] = False
    unsafe["live_memory_written"] = True
    unsafe_path = tamper_dir / "unsafe_metadata.json"
    _write_json(unsafe_path, unsafe)
    _record_case("unsafe_metadata", "unsafe_metadata", unsafe_path)

    live_write = _copy_manifest(clean_manifest)
    live_write["ready_for_live_memory_write"] = True
    live_write["future_live_write_allowed"] = True
    live_write_path = tamper_dir / "live_write_unblocked.json"
    _write_json(live_write_path, live_write)
    _record_case("live_write_unblocked", "live_write_unblocked", live_write_path)

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

    reverify_verdict, reverify_errors = audit_operator_approved_staging_manifest(
        clean_manifest_path
    )
    if reverify_verdict != "PASS" or reverify_errors:
        report.clean_staging_still_passes = False
        errors.append(
            f"Clean operator-approved staging package regressed after tamper cases: {reverify_errors}"
        )

    case_path_objects = [Path(path) for path in case_paths.values()]
    report.tamper_paths_inside_workspace = all(
        _path_inside_workspace(path, workspace) for path in [tamper_dir, *case_path_objects]
    )

    if not report.clean_staging_still_passes:
        errors.append("Clean operator-approved staging package did not remain PASS.")
    if not report.all_tamper_cases_detected:
        errors.append("One or more required staging tamper cases were not detected.")
    if any(case.actual_verdict != "FAIL" for case in cases):
        errors.append("A tampered staging manifest did not return verdict=FAIL.")
    if not report.tamper_paths_inside_workspace:
        errors.append("One or more tamper manifest paths are outside the temp workspace.")
    if report.tamper_case_count != len(REQUIRED_TAMPER_CASES):
        errors.append(
            "tamper_case_count does not match the required staging tamper-case set."
        )

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


def run_memory_review_approved_promotion_operator_approved_staging_tamper_evidence_smoke(
    *,
    base_dir: Path | None = None,
    keep_temp: bool = False,
) -> OperatorApprovedStagingTamperEvidenceReport:
    """Build a clean staging package and prove tampered variants fail."""
    owned_temp = base_dir is None
    workspace = (
        Path(tempfile.mkdtemp(prefix="elysia_memory_operator_approved_staging_tamper_"))
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


def format_operator_summary(report: OperatorApprovedStagingTamperEvidenceReport) -> str:
    lines = [
        "Memory review approved promotion operator-approved staging tamper evidence smoke",
        "=" * 78,
        f"Verdict: {report.verdict}",
        f"Workspace: {report.workspace}",
        f"Workspace preserved: {report.workspace_preserved}",
        f"Clean staging path: {report.clean_staging_path}",
        f"Clean staging verdict: {report.clean_staging_verdict}",
        f"Clean staging still passes: {report.clean_staging_still_passes}",
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
            "Run local-only Memory review approved promotion operator-approved "
            "staging tamper evidence smoke."
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
        report = run_memory_review_approved_promotion_operator_approved_staging_tamper_evidence_smoke(
            base_dir=args.base_dir,
            keep_temp=args.keep_temp,
        )
    except ValueError as exc:
        report = OperatorApprovedStagingTamperEvidenceReport(
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
