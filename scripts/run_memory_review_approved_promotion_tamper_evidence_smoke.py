#!/usr/bin/env python3
"""Dry-run/local smoke proving approved-promotion manifests detect tampering.

This smoke builds a valid approved-promotion bundle from local fixtures in a
temporary workspace, then writes tampered promotion manifest copies and runs a
self-contained, local-only checker against each. It verifies the clean manifest
passes and every tampered manifest fails with a specific error token. It never
calls models, embeddings, networks, live accounts, UI routes, or live runtime
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

from run_memory_review_approved_promotion_bundle_smoke import (  # noqa: E402
    run_memory_review_approved_promotion_bundle_smoke,
)

REQUIRED_MANIFEST_FIELDS = (
    "verdict",
    "workspace",
    "bundle_path",
    "approved_candidate_count",
    "edited_candidate_count",
    "rejected_candidate_count",
    "promotion_item_count",
    "excluded_rejected_count",
    "promotion_items",
    "source_queue_path",
    "review_decisions_log_path",
    "review_decisions_log_sha256",
    "candidate_source_hashes",
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
    "promotion_manifest_sha256",
)

REQUIRED_PROMOTION_ITEM_FIELDS = (
    "candidate_id",
    "decision_id",
    "decision_type",
    "source_type",
    "original_text",
    "promoted_text",
    "text_was_edited",
    "source_queue_path",
    "review_decision_log_path",
    "candidate_sha256",
    "promoted_text_sha256",
    "ready_for_future_promotion",
    "live_memory_written",
    "live_vector_db_written",
    "operator_required",
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

UNSAFE_PROMOTION_ITEM_METADATA = (
    ("ready_for_future_promotion", False, "ready_for_future_promotion=false"),
    ("operator_required", False, "operator_required=false"),
    ("live_memory_written", True, "live_memory_written=true"),
    ("live_vector_db_written", True, "live_vector_db_written=true"),
)


@dataclass
class TamperCaseResult:
    name: str
    verdict: str
    expected_token: str
    token_found: bool
    manifest_path: str
    errors: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ApprovedPromotionTamperEvidenceReport:
    verdict: str
    workspace: str
    workspace_preserved: bool
    clean_manifest_path: str = ""
    clean_manifest_verdict: str = "UNKNOWN"
    clean_manifest_still_passes: bool = False
    tampered_cases_run: int = 0
    malformed_json_detected: bool = False
    missing_required_manifest_field_detected: bool = False
    missing_required_promotion_item_field_detected: bool = False
    promoted_text_hash_mismatch_detected: bool = False
    candidate_hash_mismatch_detected: bool = False
    rejected_candidate_included_detected: bool = False
    promotion_item_count_mismatch_detected: bool = False
    unsafe_metadata_detected: bool = False
    manifest_hash_mismatch_detected: bool = False
    manifest_hash_validation_present: bool = True
    specific_errors_present: bool = False
    tamper_paths_inside_workspace: bool = False
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
    cases: List[Dict[str, Any]] = field(default_factory=list)
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


def _manifest_hash(manifest: Dict[str, Any]) -> str:
    manifest_without_hash = dict(manifest)
    manifest_without_hash.pop("promotion_manifest_sha256", None)
    payload = json.dumps(manifest_without_hash, indent=2, ensure_ascii=False) + "\n"
    return _sha256_bytes(payload.encode("utf-8"))


def _attach_manifest_hash(manifest: Dict[str, Any]) -> Dict[str, Any]:
    hashed = dict(manifest)
    hashed.pop("promotion_manifest_sha256", None)
    hashed["promotion_manifest_sha256"] = _manifest_hash(hashed)
    return hashed


def _path_inside_workspace(path: Path, workspace: Path) -> bool:
    try:
        path.resolve().relative_to(workspace.resolve())
        return True
    except ValueError:
        return False


def _write_manifest(path: Path, manifest: Dict[str, Any], *, refresh_hash: bool = True) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = _attach_manifest_hash(manifest) if refresh_hash else manifest
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


def audit_promotion_manifest(manifest_path: Path) -> Tuple[str, List[str]]:
    """Local-only checker for an approved-promotion manifest.

    Returns a (verdict, errors) tuple. Detects malformed JSON, missing required
    manifest and promotion-item fields, promoted/candidate hash mismatches,
    rejected candidates included in promotion items, item-count mismatches,
    unsafe metadata, and promotion manifest hash mismatches.
    """
    errors: List[str] = []
    if not manifest_path.is_file():
        return "FAIL", [f"missing_manifest_file: {manifest_path}"]

    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return "FAIL", [f"malformed_json: manifest is not valid JSON ({exc})"]

    if not isinstance(manifest, dict):
        return "FAIL", ["malformed_json: manifest root is not a JSON object"]

    missing_manifest_fields = [
        field_name for field_name in REQUIRED_MANIFEST_FIELDS if field_name not in manifest
    ]
    if missing_manifest_fields:
        errors.append(
            "missing_required_manifest_field: missing "
            + ", ".join(missing_manifest_fields)
        )

    promotion_items = manifest.get("promotion_items")
    if not isinstance(promotion_items, list):
        errors.append("missing_required_manifest_field: promotion_items is not a list")
        promotion_items = []

    promotion_item_count = manifest.get("promotion_item_count")
    if not isinstance(promotion_item_count, int) or promotion_item_count != len(promotion_items):
        errors.append(
            "promotion_item_count_mismatch: "
            f"promotion_item_count={promotion_item_count!r} actual_items={len(promotion_items)}"
        )

    candidate_source_hashes = manifest.get("candidate_source_hashes")
    if not isinstance(candidate_source_hashes, dict):
        errors.append("candidate_hash_mismatch: candidate_source_hashes is not an object")
        candidate_source_hashes = {}

    for field_name, unsafe_value, label in UNSAFE_MANIFEST_METADATA:
        if field_name in manifest and manifest.get(field_name) is unsafe_value:
            errors.append(f"unsafe_metadata: manifest {label}")

    for index, item in enumerate(promotion_items, start=1):
        if not isinstance(item, dict):
            errors.append(f"missing_required_promotion_item_field: item {index} is not an object")
            continue

        missing_item_fields = [
            field_name for field_name in REQUIRED_PROMOTION_ITEM_FIELDS if field_name not in item
        ]
        if missing_item_fields:
            errors.append(
                "missing_required_promotion_item_field: "
                f"item {index} missing {', '.join(missing_item_fields)}"
            )

        candidate_id = str(item.get("candidate_id") or "")
        decision_type = str(item.get("decision_type") or "").strip().lower()
        if decision_type == "rejected":
            errors.append(
                "rejected_candidate_included: "
                f"item {index} candidate_id={candidate_id!r}"
            )

        original_text = str(item.get("original_text") or "")
        candidate_hash = str(item.get("candidate_sha256") or "")
        expected_candidate_hash = _sha256_text(original_text)
        if candidate_hash != expected_candidate_hash:
            errors.append(
                "candidate_hash_mismatch: "
                f"item {index} candidate_id={candidate_id!r}"
            )

        if candidate_id and candidate_source_hashes.get(candidate_id) != candidate_hash:
            errors.append(
                "candidate_hash_mismatch: "
                f"candidate_source_hashes mismatch for candidate_id={candidate_id!r}"
            )

        promoted_text = str(item.get("promoted_text") or "")
        promoted_hash = str(item.get("promoted_text_sha256") or "")
        expected_promoted_hash = _sha256_text(promoted_text)
        if promoted_hash != expected_promoted_hash:
            errors.append(
                "promoted_text_hash_mismatch: "
                f"item {index} candidate_id={candidate_id!r}"
            )

        for field_name, unsafe_value, label in UNSAFE_PROMOTION_ITEM_METADATA:
            if field_name in item and item.get(field_name) is unsafe_value:
                errors.append(f"unsafe_metadata: item {index} {label}")

    manifest_hash = str(manifest.get("promotion_manifest_sha256") or "")
    if "promotion_manifest_sha256" in manifest and manifest_hash != _manifest_hash(manifest):
        errors.append("manifest_hash_mismatch: promotion_manifest_sha256 does not match content")

    verdict = "PASS" if not errors else "FAIL"
    return verdict, errors


def _load_clean_manifest(workspace: Path) -> Tuple[Path, Dict[str, Any], Dict[str, str]]:
    bundle_workspace = Path(
        tempfile.mkdtemp(prefix="clean_bundle_", dir=str(workspace.resolve()))
    )
    bundle_report = run_memory_review_approved_promotion_bundle_smoke(
        base_dir=bundle_workspace,
        keep_temp=True,
    )
    if bundle_report.verdict != "PASS":
        raise ValueError(
            "Approved promotion bundle smoke did not pass while building clean manifest: "
            + "; ".join(bundle_report.errors)
        )
    manifest_path = Path(bundle_report.promotion_manifest_path)
    if not manifest_path.is_file():
        raise ValueError(f"Clean promotion manifest was not created: {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    artifact_paths = {
        "clean_bundle_workspace": str(bundle_workspace.resolve()),
        "clean_bundle_dir": bundle_report.bundle_path,
        "clean_promotion_manifest": str(manifest_path.resolve()),
        "clean_promotion_readme": str(
            Path(bundle_report.artifact_paths.get("promotion_readme", "")).resolve()
        ),
        "clean_review_queue": str(
            Path(bundle_report.artifact_paths.get("review_queue", "")).resolve()
        ),
        "clean_review_decisions": str(
            Path(bundle_report.artifact_paths.get("review_decisions", "")).resolve()
        ),
    }
    return manifest_path, manifest, artifact_paths


def _copy_manifest(manifest: Dict[str, Any]) -> Dict[str, Any]:
    return copy.deepcopy(manifest)


def _first_item(manifest: Dict[str, Any]) -> Dict[str, Any]:
    items = manifest.get("promotion_items")
    if not isinstance(items, list) or not items or not isinstance(items[0], dict):
        raise ValueError("Clean manifest does not contain a promotion item template.")
    return items[0]


def _make_rejected_item(template: Dict[str, Any]) -> Dict[str, Any]:
    text = "Reject branch fixture: rejected-only note should never be promoted."
    candidate_id = "rejected-tamper-candidate"
    item = dict(template)
    item.update(
        {
            "candidate_id": candidate_id,
            "decision_id": "rejected-tamper-decision",
            "decision_type": "rejected",
            "original_text": text,
            "promoted_text": text,
            "text_was_edited": False,
            "candidate_sha256": _sha256_text(text),
            "promoted_text_sha256": _sha256_text(text),
            "ready_for_future_promotion": True,
            "live_memory_written": False,
            "live_vector_db_written": False,
            "operator_required": True,
        }
    )
    return item


def _run_tamper_flow(
    workspace: Path,
    *,
    workspace_preserved: bool,
) -> ApprovedPromotionTamperEvidenceReport:
    errors: List[str] = []
    case_paths: Dict[str, str] = {}
    report = ApprovedPromotionTamperEvidenceReport(
        verdict="FAIL",
        workspace=str(workspace.resolve()),
        workspace_preserved=workspace_preserved,
        autonomy_enabled=_read_autonomy_enabled(),
    )
    if report.autonomy_enabled:
        report.errors.append(
            "Autonomy is enabled; approved promotion tamper evidence smoke is blocked."
        )
        return report

    clean_manifest_path, clean_manifest, artifact_paths = _load_clean_manifest(workspace)
    report.clean_manifest_path = str(clean_manifest_path.resolve())
    tamper_dir = workspace / "tampered_promotion_manifests"
    tamper_dir.mkdir(parents=True, exist_ok=True)

    clean_verdict, clean_errors = audit_promotion_manifest(clean_manifest_path)
    report.clean_manifest_verdict = clean_verdict
    report.clean_manifest_still_passes = clean_verdict == "PASS" and not clean_errors
    if not report.clean_manifest_still_passes:
        errors.append(f"Clean promotion manifest did not pass: {clean_errors}")

    cases: List[TamperCaseResult] = []

    def _record_case(name: str, expected_token: str, path: Path) -> None:
        verdict, case_errors = audit_promotion_manifest(path)
        token_found = any(expected_token in error for error in case_errors)
        cases.append(
            TamperCaseResult(
                name=name,
                verdict=verdict,
                expected_token=expected_token,
                token_found=token_found,
                manifest_path=str(path.resolve()),
                errors=case_errors,
            )
        )
        case_paths[name] = str(path.resolve())

    malformed_path = tamper_dir / "malformed_json_manifest.json"
    _write_raw(malformed_path, "{ this is not valid json\n")
    _record_case("malformed_json", "malformed_json", malformed_path)

    missing_manifest = _copy_manifest(clean_manifest)
    missing_manifest.pop("workspace", None)
    missing_manifest_path = tamper_dir / "missing_required_manifest_field.json"
    _write_manifest(missing_manifest_path, missing_manifest)
    _record_case(
        "missing_required_manifest_field",
        "missing_required_manifest_field",
        missing_manifest_path,
    )

    missing_item = _copy_manifest(clean_manifest)
    _first_item(missing_item).pop("promoted_text", None)
    missing_item_path = tamper_dir / "missing_required_promotion_item_field.json"
    _write_manifest(missing_item_path, missing_item)
    _record_case(
        "missing_required_promotion_item_field",
        "missing_required_promotion_item_field",
        missing_item_path,
    )

    promoted_hash = _copy_manifest(clean_manifest)
    _first_item(promoted_hash)["promoted_text_sha256"] = "0" * 64
    promoted_hash_path = tamper_dir / "promoted_text_hash_mismatch.json"
    _write_manifest(promoted_hash_path, promoted_hash)
    _record_case(
        "promoted_text_hash_mismatch",
        "promoted_text_hash_mismatch",
        promoted_hash_path,
    )

    candidate_hash = _copy_manifest(clean_manifest)
    _first_item(candidate_hash)["candidate_sha256"] = "0" * 64
    candidate_hash_path = tamper_dir / "candidate_hash_mismatch.json"
    _write_manifest(candidate_hash_path, candidate_hash)
    _record_case("candidate_hash_mismatch", "candidate_hash_mismatch", candidate_hash_path)

    rejected_included = _copy_manifest(clean_manifest)
    rejected_item = _make_rejected_item(_first_item(rejected_included))
    rejected_included["promotion_items"].append(rejected_item)
    rejected_included["promotion_item_count"] = len(rejected_included["promotion_items"])
    rejected_included["candidate_source_hashes"][rejected_item["candidate_id"]] = rejected_item[
        "candidate_sha256"
    ]
    rejected_path = tamper_dir / "rejected_candidate_included.json"
    _write_manifest(rejected_path, rejected_included)
    _record_case(
        "rejected_candidate_included",
        "rejected_candidate_included",
        rejected_path,
    )

    count_mismatch = _copy_manifest(clean_manifest)
    count_mismatch["promotion_item_count"] = len(count_mismatch["promotion_items"]) + 1
    count_mismatch_path = tamper_dir / "promotion_item_count_mismatch.json"
    _write_manifest(count_mismatch_path, count_mismatch)
    _record_case(
        "promotion_item_count_mismatch",
        "promotion_item_count_mismatch",
        count_mismatch_path,
    )

    unsafe = _copy_manifest(clean_manifest)
    unsafe["live_memory_written"] = True
    _first_item(unsafe)["operator_required"] = False
    unsafe_path = tamper_dir / "unsafe_metadata.json"
    _write_manifest(unsafe_path, unsafe)
    _record_case("unsafe_metadata", "unsafe_metadata", unsafe_path)

    manifest_hash = _copy_manifest(clean_manifest)
    manifest_hash["promotion_manifest_sha256"] = "0" * 64
    manifest_hash_path = tamper_dir / "manifest_hash_mismatch.json"
    _write_manifest(manifest_hash_path, manifest_hash, refresh_hash=False)
    _record_case("manifest_hash_mismatch", "manifest_hash_mismatch", manifest_hash_path)

    report.tampered_cases_run = len(cases)
    report.cases = [case.to_dict() for case in cases]

    detections = {case.name: case.verdict == "FAIL" and case.token_found for case in cases}
    report.malformed_json_detected = detections.get("malformed_json", False)
    report.missing_required_manifest_field_detected = detections.get(
        "missing_required_manifest_field", False
    )
    report.missing_required_promotion_item_field_detected = detections.get(
        "missing_required_promotion_item_field", False
    )
    report.promoted_text_hash_mismatch_detected = detections.get(
        "promoted_text_hash_mismatch", False
    )
    report.candidate_hash_mismatch_detected = detections.get("candidate_hash_mismatch", False)
    report.rejected_candidate_included_detected = detections.get(
        "rejected_candidate_included", False
    )
    report.promotion_item_count_mismatch_detected = detections.get(
        "promotion_item_count_mismatch", False
    )
    report.unsafe_metadata_detected = detections.get("unsafe_metadata", False)
    report.manifest_hash_mismatch_detected = detections.get("manifest_hash_mismatch", False)
    report.specific_errors_present = all(case.token_found for case in cases)
    all_failed = all(case.verdict == "FAIL" for case in cases)

    reverify_verdict, reverify_errors = audit_promotion_manifest(clean_manifest_path)
    if reverify_verdict != "PASS" or reverify_errors:
        report.clean_manifest_still_passes = False
        errors.append(
            f"Clean promotion manifest regressed after tamper cases: {reverify_errors}"
        )

    case_path_objects = [Path(path) for path in case_paths.values()]
    report.tamper_paths_inside_workspace = all(
        _path_inside_workspace(path, workspace) for path in [tamper_dir, *case_path_objects]
    )

    required_detections = (
        report.malformed_json_detected
        and report.missing_required_manifest_field_detected
        and report.missing_required_promotion_item_field_detected
        and report.promoted_text_hash_mismatch_detected
        and report.candidate_hash_mismatch_detected
        and report.rejected_candidate_included_detected
        and report.promotion_item_count_mismatch_detected
        and report.unsafe_metadata_detected
        and report.manifest_hash_mismatch_detected
    )

    if not report.clean_manifest_still_passes:
        errors.append("Clean promotion manifest did not remain PASS.")
    if not required_detections:
        errors.append("One or more required approved-promotion tamper cases were not detected.")
    if not all_failed:
        errors.append("A tampered promotion manifest did not return verdict=FAIL.")
    if not report.specific_errors_present:
        errors.append("A tamper case did not produce a specific error token.")
    if not report.tamper_paths_inside_workspace:
        errors.append("One or more tamper manifest paths are outside the temp workspace.")

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


def run_memory_review_approved_promotion_tamper_evidence_smoke(
    *,
    base_dir: Path | None = None,
    keep_temp: bool = False,
) -> ApprovedPromotionTamperEvidenceReport:
    """Build a clean promotion manifest and prove tampered variants fail."""
    owned_temp = base_dir is None
    workspace = (
        Path(tempfile.mkdtemp(prefix="elysia_memory_approved_promotion_tamper_"))
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


def format_operator_summary(report: ApprovedPromotionTamperEvidenceReport) -> str:
    lines = [
        "Memory review approved promotion tamper evidence smoke",
        "=" * 56,
        f"Verdict: {report.verdict}",
        f"Workspace: {report.workspace}",
        f"Workspace preserved: {report.workspace_preserved}",
        f"Clean manifest: {report.clean_manifest_path}",
        f"Clean manifest verdict: {report.clean_manifest_verdict}",
        f"Clean manifest still passes: {report.clean_manifest_still_passes}",
        f"Tampered cases run: {report.tampered_cases_run}",
        "",
        "Detections:",
        f"  malformed_json: {report.malformed_json_detected}",
        (
            "  missing_required_manifest_field: "
            f"{report.missing_required_manifest_field_detected}"
        ),
        (
            "  missing_required_promotion_item_field: "
            f"{report.missing_required_promotion_item_field_detected}"
        ),
        f"  promoted_text_hash_mismatch: {report.promoted_text_hash_mismatch_detected}",
        f"  candidate_hash_mismatch: {report.candidate_hash_mismatch_detected}",
        f"  rejected_candidate_included: {report.rejected_candidate_included_detected}",
        (
            "  promotion_item_count_mismatch: "
            f"{report.promotion_item_count_mismatch_detected}"
        ),
        f"  unsafe_metadata: {report.unsafe_metadata_detected}",
        f"  manifest_hash_mismatch: {report.manifest_hash_mismatch_detected}",
        f"  specific errors present: {report.specific_errors_present}",
        f"  tamper paths inside workspace: {report.tamper_paths_inside_workspace}",
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
    if report.errors:
        lines.extend(["", "Errors:"])
        lines.extend(f"  - {error}" for error in report.errors)
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run local-only Memory review approved promotion tamper evidence smoke.",
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
        report = run_memory_review_approved_promotion_tamper_evidence_smoke(
            base_dir=args.base_dir,
            keep_temp=args.keep_temp,
        )
    except ValueError as exc:
        report = ApprovedPromotionTamperEvidenceReport(
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
