#!/usr/bin/env python3
"""Dry-run/local smoke producing an approved-promotion operator handoff.

This smoke builds a validated approved-promotion bundle, runs the existing
approved-promotion tamper-evidence checks, and writes an operator handoff
package for human review. It never writes live runtime memory, vector DB data,
models, embeddings, networks, live accounts, UI routes, or background work.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import tempfile
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Sequence

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from run_memory_review_approved_promotion_bundle_smoke import (  # noqa: E402
    run_memory_review_approved_promotion_bundle_smoke,
)
from run_memory_review_approved_promotion_tamper_evidence_smoke import (  # noqa: E402
    audit_promotion_manifest,
    run_memory_review_approved_promotion_tamper_evidence_smoke,
)

HANDOFF_DIRNAME = "approved_promotion_operator_handoff"
HANDOFF_FILENAME = "operator_handoff.json"
CHECKLIST_FILENAME = "OPERATOR_CHECKLIST.md"
README_FILENAME = "README.md"

LIVE_WRITE_BLOCKED_REASON = (
    "Live memory writing is intentionally not implemented or enabled in this "
    "dry-run approved-promotion operator handoff campaign."
)

TAMPER_DETECTION_FIELDS = (
    "malformed_json_detected",
    "missing_required_manifest_field_detected",
    "missing_required_promotion_item_field_detected",
    "promoted_text_hash_mismatch_detected",
    "candidate_hash_mismatch_detected",
    "rejected_candidate_included_detected",
    "promotion_item_count_mismatch_detected",
    "unsafe_metadata_detected",
    "manifest_hash_mismatch_detected",
)


@dataclass
class ApprovedPromotionOperatorHandoffReport:
    verdict: str
    workspace: str
    workspace_preserved: bool
    handoff_path: str = ""
    operator_handoff_path: str = ""
    operator_handoff_valid_json: bool = False
    operator_checklist_path: str = ""
    operator_checklist_created: bool = False
    operator_checklist_sha256: str = ""
    promotion_bundle_path: str = ""
    promotion_manifest_path: str = ""
    promotion_manifest_hash_present: bool = False
    promotion_manifest_sha256: str = ""
    tamper_evidence_verdict: str = "UNKNOWN"
    tamper_case_count: int = 0
    all_tamper_cases_detected: bool = False
    promotion_item_count: int = 0
    approved_candidate_count: int = 0
    edited_candidate_count: int = 0
    approved_candidate_included: bool = False
    edited_candidate_included: bool = False
    edited_promoted_text_preserved: bool = False
    rejected_candidate_excluded: bool = False
    excluded_rejected_count: int = 0
    ready_for_operator_review: bool = False
    ready_for_live_memory_write: bool = False
    requires_explicit_operator_approval: bool = True
    future_live_write_allowed: bool = False
    live_write_blocked_reason: str = LIVE_WRITE_BLOCKED_REASON
    handoff_paths_inside_workspace: bool = False
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


def _sha256_file(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _path_inside_workspace(path: Path, workspace: Path) -> bool:
    try:
        path.resolve().relative_to(workspace.resolve())
        return True
    except ValueError:
        return False


def _load_json(path: Path) -> Dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"JSON file does not contain an object: {path}")
    return payload


def _all_tamper_cases_detected(tamper_report: Any) -> bool:
    return (
        getattr(tamper_report, "verdict", "") == "PASS"
        and getattr(tamper_report, "tampered_cases_run", 0) >= len(TAMPER_DETECTION_FIELDS)
        and all(bool(getattr(tamper_report, field_name, False)) for field_name in TAMPER_DETECTION_FIELDS)
    )


def _build_handoff_items(promotion_items: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    handoff_items: List[Dict[str, Any]] = []
    for item in promotion_items:
        handoff_items.append(
            {
                "candidate_id": str(item.get("candidate_id") or ""),
                "decision_id": str(item.get("decision_id") or ""),
                "decision_type": str(item.get("decision_type") or ""),
                "source_type": str(item.get("source_type") or ""),
                "promoted_text": str(item.get("promoted_text") or ""),
                "promoted_text_sha256": str(item.get("promoted_text_sha256") or ""),
                "candidate_sha256": str(item.get("candidate_sha256") or ""),
                "ready_for_operator_review": True,
                "ready_for_live_memory_write": False,
                "requires_explicit_operator_approval": True,
                "live_memory_written": False,
                "live_vector_db_written": False,
            }
        )
    return handoff_items


def _write_checklist(
    checklist_path: Path,
    *,
    manifest: Dict[str, Any],
    tamper_verdict: str,
) -> str:
    lines = [
        "# Approved Promotion Operator Checklist",
        "",
        "This dry-run handoff is for human review only.",
        "",
        "## Required checks before any future live promotion",
        "",
        "- Confirm the promotion manifest path and hash in `operator_handoff.json`.",
        f"- Confirm tamper-evidence verdict is `{tamper_verdict}`.",
        "- Confirm approved and edited promotion items are expected.",
        "- Confirm rejected candidates remain excluded.",
        "- Confirm edited items preserve promoted text and original text remains in the promotion manifest.",
        "- Confirm `ready_for_live_memory_write` is `false`.",
        "- Confirm `future_live_write_allowed` is `false`.",
        "- Confirm explicit operator approval is required for any future live promotion.",
        "- Confirm live memory writing is not implemented or enabled by this campaign.",
        "",
        "## Fixture summary",
        "",
        f"- Promotion items: `{manifest.get('promotion_item_count', 0)}`",
        f"- Approved candidates: `{manifest.get('approved_candidate_count', 0)}`",
        f"- Edited candidates: `{manifest.get('edited_candidate_count', 0)}`",
        f"- Excluded rejected candidates: `{manifest.get('excluded_rejected_count', 0)}`",
        "",
        "## Safety",
        "",
        "- dry_run: `true`",
        "- local_only: `true`",
        "- model_called: `false`",
        "- embeddings_used: `false`",
        "- live_memory_written: `false`",
        "- live_vector_db_written: `false`",
        "- account_api_network_accessed: `false`",
        "- autonomy_enabled: `false`",
    ]
    checklist_path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    return _sha256_file(checklist_path)


def _write_readme(readme_path: Path, handoff: Dict[str, Any]) -> None:
    lines = [
        "# Approved Promotion Operator Handoff",
        "",
        "Dry-run operator staging package for approved-memory promotion review.",
        "",
        f"- Handoff JSON: `{handoff.get('operator_handoff_path', '')}`",
        f"- Operator checklist: `{handoff.get('operator_checklist_path', '')}`",
        f"- Promotion manifest: `{handoff.get('promotion_manifest_path', '')}`",
        f"- Tamper-evidence verdict: `{handoff.get('tamper_evidence_verdict', '')}`",
        "",
        "This package is ready for operator review only. It is not ready for live",
        "memory writing, and future live promotion remains blocked until an explicit",
        "operator-approved live path exists.",
    ]
    readme_path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")


def _build_operator_handoff(workspace: Path) -> ApprovedPromotionOperatorHandoffReport:
    errors: List[str] = []
    report = ApprovedPromotionOperatorHandoffReport(
        verdict="FAIL",
        workspace=str(workspace.resolve()),
        workspace_preserved=True,
        autonomy_enabled=_read_autonomy_enabled(),
    )
    if report.autonomy_enabled:
        report.errors.append(
            "Autonomy is enabled; approved promotion operator handoff smoke is blocked."
        )
        return report

    bundle_report = run_memory_review_approved_promotion_bundle_smoke(
        base_dir=workspace,
        keep_temp=True,
    )
    if bundle_report.verdict != "PASS":
        report.errors.append(
            "Approved promotion bundle did not pass: " + "; ".join(bundle_report.errors)
        )
        return report

    manifest_path = Path(bundle_report.promotion_manifest_path)
    manifest = _load_json(manifest_path)
    clean_manifest_verdict, clean_manifest_errors = audit_promotion_manifest(manifest_path)
    tamper_workspace = workspace / "approved_promotion_tamper_evidence"
    tamper_report = run_memory_review_approved_promotion_tamper_evidence_smoke(
        base_dir=tamper_workspace,
        keep_temp=True,
    )

    report.promotion_bundle_path = bundle_report.bundle_path
    report.promotion_manifest_path = str(manifest_path.resolve())
    report.promotion_manifest_sha256 = str(manifest.get("promotion_manifest_sha256") or "")
    report.promotion_manifest_hash_present = bool(report.promotion_manifest_sha256)
    report.tamper_evidence_verdict = str(getattr(tamper_report, "verdict", "UNKNOWN"))
    report.tamper_case_count = int(getattr(tamper_report, "tampered_cases_run", 0) or 0)
    report.all_tamper_cases_detected = _all_tamper_cases_detected(tamper_report)
    report.promotion_item_count = int(manifest.get("promotion_item_count") or 0)
    report.approved_candidate_count = int(manifest.get("approved_candidate_count") or 0)
    report.edited_candidate_count = int(manifest.get("edited_candidate_count") or 0)
    report.excluded_rejected_count = int(manifest.get("excluded_rejected_count") or 0)

    promotion_items = [
        item for item in manifest.get("promotion_items") or [] if isinstance(item, dict)
    ]
    handoff_items = _build_handoff_items(promotion_items)
    report.approved_candidate_included = any(
        item.get("decision_type") == "approved" for item in handoff_items
    )
    report.edited_candidate_included = any(
        item.get("decision_type") == "edited" for item in handoff_items
    )
    report.edited_promoted_text_preserved = any(
        item.get("decision_type") == "edited"
        and "Edited approved memory" in str(item.get("promoted_text") or "")
        for item in handoff_items
    )
    report.rejected_candidate_excluded = all(
        item.get("decision_type") != "rejected" for item in handoff_items
    )

    review_ready = (
        clean_manifest_verdict == "PASS"
        and not clean_manifest_errors
        and report.tamper_evidence_verdict == "PASS"
        and report.all_tamper_cases_detected
        and report.promotion_item_count == 2
        and report.excluded_rejected_count == 1
        and report.approved_candidate_included
        and report.edited_candidate_included
        and report.rejected_candidate_excluded
    )
    report.ready_for_operator_review = review_ready

    handoff_dir = workspace / HANDOFF_DIRNAME
    handoff_dir.mkdir(parents=True, exist_ok=True)
    report.handoff_path = str(handoff_dir.resolve())
    handoff_json_path = handoff_dir / HANDOFF_FILENAME
    checklist_path = handoff_dir / CHECKLIST_FILENAME
    readme_path = handoff_dir / README_FILENAME
    report.operator_checklist_path = str(checklist_path.resolve())
    report.operator_checklist_sha256 = _write_checklist(
        checklist_path,
        manifest=manifest,
        tamper_verdict=report.tamper_evidence_verdict,
    )
    report.operator_checklist_created = checklist_path.is_file()

    handoff_payload: Dict[str, Any] = {
        "verdict": "PASS" if review_ready else "FAIL",
        "workspace": report.workspace,
        "handoff_path": report.handoff_path,
        "promotion_bundle_path": report.promotion_bundle_path,
        "promotion_manifest_path": report.promotion_manifest_path,
        "promotion_manifest_sha256": report.promotion_manifest_sha256,
        "tamper_evidence_verdict": report.tamper_evidence_verdict,
        "tamper_case_count": report.tamper_case_count,
        "all_tamper_cases_detected": report.all_tamper_cases_detected,
        "promotion_item_count": report.promotion_item_count,
        "approved_candidate_count": report.approved_candidate_count,
        "edited_candidate_count": report.edited_candidate_count,
        "excluded_rejected_count": report.excluded_rejected_count,
        "promotion_items": handoff_items,
        "operator_checklist_path": report.operator_checklist_path,
        "operator_checklist_sha256": report.operator_checklist_sha256,
        "ready_for_operator_review": review_ready,
        "ready_for_live_memory_write": False,
        "requires_explicit_operator_approval": True,
        "future_live_write_allowed": False,
        "live_write_blocked_reason": LIVE_WRITE_BLOCKED_REASON,
        "operator_required": True,
        "dry_run": True,
        "local_only": True,
        "model_called": False,
        "embeddings_used": False,
        "live_memory_written": False,
        "live_vector_db_written": False,
        "account_api_network_accessed": False,
        "autonomy_enabled": False,
        "errors": [],
    }
    report.operator_handoff_path = str(handoff_json_path.resolve())
    handoff_json_path.write_text(
        json.dumps(handoff_payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    _write_readme(readme_path, {**handoff_payload, "operator_handoff_path": report.operator_handoff_path})

    try:
        loaded_handoff = _load_json(handoff_json_path)
        report.operator_handoff_valid_json = isinstance(loaded_handoff, dict)
    except (OSError, json.JSONDecodeError, ValueError):
        report.operator_handoff_valid_json = False

    report.handoff_paths_inside_workspace = all(
        _path_inside_workspace(path, workspace)
        for path in (
            handoff_dir,
            handoff_json_path,
            checklist_path,
            readme_path,
            Path(report.promotion_bundle_path),
            manifest_path,
            tamper_workspace,
        )
    )

    report.artifact_paths = {
        "handoff_dir": report.handoff_path,
        "operator_handoff": report.operator_handoff_path,
        "operator_checklist": report.operator_checklist_path,
        "handoff_readme": str(readme_path.resolve()),
        "promotion_bundle": report.promotion_bundle_path,
        "promotion_manifest": report.promotion_manifest_path,
        "tamper_evidence_workspace": str(tamper_workspace.resolve()),
    }

    if clean_manifest_verdict != "PASS" or clean_manifest_errors:
        errors.append(f"Promotion manifest audit did not pass: {clean_manifest_errors}")
    if report.tamper_evidence_verdict != "PASS":
        errors.append(f"Tamper-evidence smoke did not pass: {getattr(tamper_report, 'errors', [])}")
    if not report.all_tamper_cases_detected:
        errors.append("Not all tamper cases were detected.")
    if report.promotion_item_count != 2:
        errors.append("Expected exactly two promotion items for fixture flow.")
    if report.excluded_rejected_count != 1:
        errors.append("Expected exactly one rejected candidate to be excluded.")
    if not report.approved_candidate_included:
        errors.append("Approved candidate is missing from handoff.")
    if not report.edited_candidate_included:
        errors.append("Edited candidate is missing from handoff.")
    if not report.edited_promoted_text_preserved:
        errors.append("Edited promoted text is missing from handoff.")
    if not report.rejected_candidate_excluded:
        errors.append("Rejected candidate was included in handoff.")
    if not report.promotion_manifest_hash_present:
        errors.append("Promotion manifest hash is missing.")
    if not report.operator_checklist_created:
        errors.append("Operator checklist was not created.")
    if not report.operator_checklist_sha256:
        errors.append("Operator checklist hash is missing.")
    if not report.operator_handoff_valid_json:
        errors.append("Operator handoff JSON is invalid.")
    if not report.ready_for_operator_review:
        errors.append("Operator handoff was not marked ready for operator review.")
    if report.ready_for_live_memory_write:
        errors.append("Operator handoff unexpectedly ready for live memory write.")
    if report.future_live_write_allowed:
        errors.append("Operator handoff unexpectedly allows future live write.")
    if not report.live_write_blocked_reason:
        errors.append("Live write blocked reason is missing.")
    if not report.handoff_paths_inside_workspace:
        errors.append("One or more handoff paths are outside the temp workspace.")

    for flag_name in (
        "model_called",
        "embeddings_used",
        "live_memory_written",
        "live_vector_db_written",
        "account_api_network_accessed",
        "autonomy_enabled",
    ):
        if getattr(report, flag_name) or handoff_payload.get(flag_name):
            errors.append(f"{flag_name} unexpectedly true.")

    report.errors = errors
    report.verdict = "PASS" if not errors else "FAIL"
    if errors:
        handoff_payload["verdict"] = "FAIL"
        handoff_payload["errors"] = errors
        handoff_json_path.write_text(
            json.dumps(handoff_payload, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
            newline="\n",
        )
    return report


def run_memory_review_approved_promotion_operator_handoff_smoke(
    *,
    base_dir: Path | None = None,
    keep_temp: bool = False,
) -> ApprovedPromotionOperatorHandoffReport:
    """Build a dry-run approved-promotion operator handoff package."""
    owned_temp = base_dir is None
    workspace = (
        Path(tempfile.mkdtemp(prefix="elysia_memory_approved_promotion_handoff_"))
        if owned_temp
        else _reject_dangerous_base(Path(base_dir))
    )
    workspace.mkdir(parents=True, exist_ok=True)
    try:
        report = _build_operator_handoff(workspace)
        report.workspace_preserved = (not owned_temp) or keep_temp
        return report
    finally:
        if owned_temp and not keep_temp:
            shutil.rmtree(workspace, ignore_errors=True)


def format_operator_summary(report: ApprovedPromotionOperatorHandoffReport) -> str:
    lines = [
        "Memory review approved promotion operator handoff smoke",
        "=" * 61,
        f"Verdict: {report.verdict}",
        f"Workspace: {report.workspace}",
        f"Workspace preserved: {report.workspace_preserved}",
        f"Handoff path: {report.handoff_path}",
        f"Operator handoff JSON: {report.operator_handoff_path}",
        f"Operator checklist: {report.operator_checklist_path}",
        "",
        "Handoff checks:",
        f"  handoff valid JSON: {report.operator_handoff_valid_json}",
        f"  checklist created: {report.operator_checklist_created}",
        f"  checklist SHA-256: {bool(report.operator_checklist_sha256)}",
        f"  promotion manifest hash present: {report.promotion_manifest_hash_present}",
        f"  tamper-evidence verdict: {report.tamper_evidence_verdict}",
        f"  all tamper cases detected: {report.all_tamper_cases_detected}",
        f"  promotion items: {report.promotion_item_count}",
        f"  excluded rejected: {report.excluded_rejected_count}",
        f"  ready_for_operator_review: {report.ready_for_operator_review}",
        f"  ready_for_live_memory_write: {report.ready_for_live_memory_write}",
        f"  future_live_write_allowed: {report.future_live_write_allowed}",
        f"  handoff paths inside workspace: {report.handoff_paths_inside_workspace}",
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
        description="Run local-only Memory review approved promotion operator handoff smoke.",
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
        report = run_memory_review_approved_promotion_operator_handoff_smoke(
            base_dir=args.base_dir,
            keep_temp=args.keep_temp,
        )
    except ValueError as exc:
        report = ApprovedPromotionOperatorHandoffReport(
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
