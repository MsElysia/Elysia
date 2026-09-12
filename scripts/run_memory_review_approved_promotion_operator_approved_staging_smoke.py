#!/usr/bin/env python3
"""Dry-run/local smoke producing an operator-approved staging package.

This smoke builds the existing approved-promotion operator approval gate, then
creates a dry-run staging package only when the explicit operator approval is
valid and bound to the current handoff hash. It never writes live runtime
memory, vector DB data, models, embeddings, networks, live accounts, UI
actions, or background work.
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

from run_memory_review_approved_promotion_operator_approval_gate_smoke import (  # noqa: E402
    APPROVAL_TOKEN_PHRASE,
    _evaluate_approval_artifact,
    run_memory_review_approved_promotion_operator_approval_gate_smoke,
)

STAGING_DIRNAME = "approved_promotion_operator_approved_staging"
STAGING_MANIFEST_FILENAME = "operator_approved_staging_manifest.json"
STAGING_README_FILENAME = "STAGING_README.md"
EDITED_TEXT_MARKER = "Edited approved memory"

LIVE_WRITE_BLOCKED_REASON = (
    "Live memory writing remains intentionally not implemented or enabled in "
    "this dry-run approved-promotion operator-approved staging campaign. "
    "Future live promotion still requires a separate milestone."
)


@dataclass
class ApprovedPromotionOperatorApprovedStagingReport:
    verdict: str
    workspace: str
    workspace_preserved: bool
    staging_path: str = ""
    operator_approved_staging_manifest_path: str = ""
    operator_approved_staging_manifest_valid_json: bool = False
    staging_readme_path: str = ""
    staging_readme_created: bool = False
    staging_readme_sha256: str = ""
    promotion_bundle_path: str = ""
    promotion_manifest_path: str = ""
    promotion_manifest_sha256: str = ""
    promotion_manifest_hash_present: bool = False
    operator_handoff_path: str = ""
    operator_handoff_sha256: str = ""
    operator_handoff_hash_present: bool = False
    operator_approval_gate_path: str = ""
    operator_approval_gate_sha256: str = ""
    approval_gate_hash_present: bool = False
    approval_token_phrase: str = APPROVAL_TOKEN_PHRASE
    approval_gate_verdict: str = "UNKNOWN"
    operator_approval_valid: bool = False
    tamper_evidence_verdict: str = "UNKNOWN"
    all_tamper_cases_detected: bool = False
    promotion_item_count: int = 0
    approved_candidate_count: int = 0
    edited_candidate_count: int = 0
    excluded_rejected_count: int = 0
    approved_candidate_included: bool = False
    edited_candidate_included: bool = False
    edited_promoted_text_preserved: bool = False
    rejected_candidate_excluded: bool = False
    staged_items: List[Dict[str, Any]] = field(default_factory=list)
    ready_for_operator_approved_staging: bool = False
    ready_for_live_memory_write: bool = False
    requires_explicit_operator_approval: bool = True
    future_live_write_allowed: bool = False
    live_write_blocked_reason: str = LIVE_WRITE_BLOCKED_REASON
    staging_paths_inside_workspace: bool = False
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

    def to_manifest_dict(self) -> Dict[str, Any]:
        return {
            "verdict": self.verdict,
            "workspace": self.workspace,
            "staging_path": self.staging_path,
            "operator_approved_staging_manifest_path": (
                self.operator_approved_staging_manifest_path
            ),
            "operator_approved_staging_manifest_valid_json": (
                self.operator_approved_staging_manifest_valid_json
            ),
            "promotion_bundle_path": self.promotion_bundle_path,
            "promotion_manifest_path": self.promotion_manifest_path,
            "promotion_manifest_sha256": self.promotion_manifest_sha256,
            "operator_handoff_path": self.operator_handoff_path,
            "operator_handoff_sha256": self.operator_handoff_sha256,
            "operator_approval_gate_path": self.operator_approval_gate_path,
            "operator_approval_gate_sha256": self.operator_approval_gate_sha256,
            "approval_token_phrase": self.approval_token_phrase,
            "approval_gate_verdict": self.approval_gate_verdict,
            "ready_for_operator_approved_staging": (
                self.ready_for_operator_approved_staging
            ),
            "ready_for_live_memory_write": self.ready_for_live_memory_write,
            "future_live_write_allowed": self.future_live_write_allowed,
            "requires_explicit_operator_approval": (
                self.requires_explicit_operator_approval
            ),
            "operator_approval_valid": self.operator_approval_valid,
            "tamper_evidence_verdict": self.tamper_evidence_verdict,
            "all_tamper_cases_detected": self.all_tamper_cases_detected,
            "promotion_item_count": self.promotion_item_count,
            "approved_candidate_count": self.approved_candidate_count,
            "edited_candidate_count": self.edited_candidate_count,
            "excluded_rejected_count": self.excluded_rejected_count,
            "staged_items": self.staged_items,
            "staging_readme_path": self.staging_readme_path,
            "staging_readme_sha256": self.staging_readme_sha256,
            "live_write_blocked_reason": self.live_write_blocked_reason,
            "staging_paths_inside_workspace": self.staging_paths_inside_workspace,
            "operator_required": self.operator_required,
            "dry_run": self.dry_run,
            "local_only": self.local_only,
            "model_called": self.model_called,
            "embeddings_used": self.embeddings_used,
            "live_memory_written": self.live_memory_written,
            "live_vector_db_written": self.live_vector_db_written,
            "account_api_network_accessed": self.account_api_network_accessed,
            "autonomy_enabled": self.autonomy_enabled,
            "errors": self.errors,
        }


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


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


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


def _write_json(path: Path, payload: Dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return path


def _build_staged_items(
    promotion_items: Sequence[Dict[str, Any]],
    *,
    handoff_sha256: str,
    approval_gate_sha256: str,
) -> List[Dict[str, Any]]:
    staged_items: List[Dict[str, Any]] = []
    for item in promotion_items:
        decision_type = str(item.get("decision_type") or "")
        if decision_type == "rejected":
            continue
        staged_items.append(
            {
                "candidate_id": str(item.get("candidate_id") or ""),
                "decision_id": str(item.get("decision_id") or ""),
                "decision_type": decision_type,
                "source_type": str(item.get("source_type") or ""),
                "promoted_text": str(item.get("promoted_text") or ""),
                "promoted_text_sha256": str(item.get("promoted_text_sha256") or ""),
                "candidate_sha256": str(item.get("candidate_sha256") or ""),
                "source_handoff_sha256": handoff_sha256,
                "source_approval_gate_sha256": approval_gate_sha256,
                "ready_for_operator_approved_staging": True,
                "ready_for_live_memory_write": False,
                "requires_explicit_operator_approval": True,
                "live_memory_written": False,
                "live_vector_db_written": False,
            }
        )
    return staged_items


def _write_readme(readme_path: Path, report: ApprovedPromotionOperatorApprovedStagingReport) -> str:
    lines = [
        "# Approved Promotion Operator-Approved Staging",
        "",
        "This dry-run staging package is created only after a valid operator",
        "handoff and a valid explicit operator approval. It is not a live",
        "memory write.",
        "",
        "## Approval token",
        "",
        f"`{APPROVAL_TOKEN_PHRASE}`",
        "",
        "## Staging checklist",
        "",
        "- Promotion bundle passed tamper evidence.",
        "- Operator handoff passed operator review.",
        "- Explicit approval token matched the current handoff hash.",
        "- Approved and edited items are ready for operator-approved dry-run staging.",
        "- Rejected items remain excluded.",
        "- Live memory writing remains blocked.",
        "- Vector DB writing remains blocked.",
        "- Future live promotion still requires a separate milestone.",
        "",
        "## Hashes",
        "",
        f"- Promotion manifest SHA-256: `{report.promotion_manifest_sha256}`",
        f"- Operator handoff SHA-256: `{report.operator_handoff_sha256}`",
        f"- Approval gate SHA-256: `{report.operator_approval_gate_sha256}`",
        "",
        "## Safety",
        "",
        "- Missing or invalid approval fails closed and does not create PASS staging.",
        "- Valid approval allows dry-run staging only.",
        "- `ready_for_operator_approved_staging` is `true` only after valid approval.",
        "- `ready_for_live_memory_write` remains `false`.",
        "- `future_live_write_allowed` remains `false`.",
        "- Live runtime memory writing is not implemented or enabled.",
        "- Vector DB writing is not implemented or enabled.",
        "- No models, embeddings, live accounts, API/network access, UI actions, or routes are used.",
        "- `elysia/api/server.py`, `project_guardian/core.py`, and `config/autonomy.json` remain untouched.",
        "",
        "## Current artifacts",
        "",
        f"- Staging manifest: `{report.operator_approved_staging_manifest_path}`",
        f"- Approval gate verdict: `{report.approval_gate_verdict}`",
        f"- Tamper-evidence verdict: `{report.tamper_evidence_verdict}`",
        f"- Live-write blocked reason: `{report.live_write_blocked_reason}`",
    ]
    body = "\n".join(lines) + "\n"
    readme_path.write_text(body, encoding="utf-8", newline="\n")
    return _sha256_text(body)


def _assemble_operator_approved_staging(
    workspace: Path,
    gate_report: Any,
) -> ApprovedPromotionOperatorApprovedStagingReport:
    report = ApprovedPromotionOperatorApprovedStagingReport(
        verdict="FAIL",
        workspace=str(workspace.resolve()),
        workspace_preserved=True,
        autonomy_enabled=_read_autonomy_enabled(),
    )
    if report.autonomy_enabled:
        report.errors.append(
            "Autonomy is enabled; approved promotion operator-approved staging smoke is blocked."
        )
        return report

    report.approval_gate_verdict = str(getattr(gate_report, "verdict", "FAIL") or "FAIL")
    report.operator_handoff_path = str(getattr(gate_report, "operator_handoff_path", "") or "")
    report.operator_approval_gate_path = str(
        getattr(gate_report, "operator_approval_gate_path", "") or ""
    )
    report.operator_handoff_sha256 = str(
        getattr(gate_report, "operator_handoff_sha256", "") or ""
    )
    approval_artifact_path = Path(str(getattr(gate_report, "approval_artifact_path", "") or ""))

    if report.approval_gate_verdict != "PASS":
        report.errors.append(
            "Approval gate did not pass; refusing to create PASS operator-approved staging."
        )
        return report
    if not bool(getattr(gate_report, "ready_for_operator_approved_staging", False)):
        report.errors.append("Approval gate is not ready for operator-approved staging.")
        return report
    if not bool(getattr(gate_report, "valid_approval_passes_dry_run_staging", False)):
        report.errors.append("Valid dry-run approval did not pass; refusing PASS staging.")
        return report

    if not approval_artifact_path.is_file():
        report.errors.append("Missing approval artifact; refusing PASS staging.")
        return report
    approval_verdict, approval_errors = _evaluate_approval_artifact(
        approval_artifact_path,
        expected_handoff_sha256=report.operator_handoff_sha256,
    )
    report.operator_approval_valid = approval_verdict == "PASS"
    if not report.operator_approval_valid:
        report.errors.extend(approval_errors or ["invalid_operator_approval"])
        report.errors.append("Missing or invalid approval must not create PASS staging.")
        return report

    operator_handoff_path = Path(report.operator_handoff_path)
    operator_approval_gate_path = Path(report.operator_approval_gate_path)
    if not operator_handoff_path.is_file() or not operator_approval_gate_path.is_file():
        report.errors.append("Handoff or approval-gate JSON is missing.")
        return report

    report.operator_approval_gate_sha256 = _sha256_file(operator_approval_gate_path)
    if not report.operator_handoff_sha256:
        report.operator_handoff_sha256 = _sha256_file(operator_handoff_path)
    report.operator_handoff_hash_present = bool(report.operator_handoff_sha256)
    report.approval_gate_hash_present = bool(report.operator_approval_gate_sha256)

    handoff = _load_json(operator_handoff_path)
    report.promotion_bundle_path = str(handoff.get("promotion_bundle_path") or "")
    report.promotion_manifest_path = str(handoff.get("promotion_manifest_path") or "")
    report.promotion_manifest_sha256 = str(handoff.get("promotion_manifest_sha256") or "")
    report.promotion_manifest_hash_present = bool(report.promotion_manifest_sha256)
    report.tamper_evidence_verdict = str(handoff.get("tamper_evidence_verdict") or "UNKNOWN")
    report.all_tamper_cases_detected = bool(handoff.get("all_tamper_cases_detected"))
    report.promotion_item_count = int(handoff.get("promotion_item_count") or 0)
    report.approved_candidate_count = int(handoff.get("approved_candidate_count") or 0)
    report.edited_candidate_count = int(handoff.get("edited_candidate_count") or 0)
    report.excluded_rejected_count = int(handoff.get("excluded_rejected_count") or 0)

    promotion_items = [
        item for item in handoff.get("promotion_items") or [] if isinstance(item, dict)
    ]
    report.staged_items = _build_staged_items(
        promotion_items,
        handoff_sha256=report.operator_handoff_sha256,
        approval_gate_sha256=report.operator_approval_gate_sha256,
    )
    report.approved_candidate_included = any(
        item.get("decision_type") == "approved" for item in report.staged_items
    )
    report.edited_candidate_included = any(
        item.get("decision_type") == "edited" for item in report.staged_items
    )
    report.edited_promoted_text_preserved = any(
        item.get("decision_type") == "edited"
        and EDITED_TEXT_MARKER in str(item.get("promoted_text") or "")
        for item in report.staged_items
    )
    report.rejected_candidate_excluded = all(
        item.get("decision_type") != "rejected" for item in report.staged_items
    ) and not any(item.get("decision_type") == "rejected" for item in promotion_items)

    staging_dir = workspace / STAGING_DIRNAME
    staging_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = staging_dir / STAGING_MANIFEST_FILENAME
    readme_path = staging_dir / STAGING_README_FILENAME
    report.staging_path = str(staging_dir.resolve())
    report.operator_approved_staging_manifest_path = str(manifest_path.resolve())
    report.staging_readme_path = str(readme_path.resolve())

    report.ready_for_live_memory_write = False
    report.future_live_write_allowed = False
    report.ready_for_operator_approved_staging = (
        report.operator_approval_valid
        and report.approval_gate_verdict == "PASS"
        and report.tamper_evidence_verdict == "PASS"
        and report.all_tamper_cases_detected
        and report.promotion_item_count == 2
        and report.excluded_rejected_count == 1
        and report.approved_candidate_included
        and report.edited_candidate_included
        and report.edited_promoted_text_preserved
        and report.rejected_candidate_excluded
        and report.promotion_manifest_hash_present
        and report.operator_handoff_hash_present
        and report.approval_gate_hash_present
        and report.approval_token_phrase == APPROVAL_TOKEN_PHRASE
    )

    report.staging_readme_sha256 = _write_readme(readme_path, report)
    report.staging_readme_created = readme_path.is_file()
    if (
        report.staging_readme_created
        and APPROVAL_TOKEN_PHRASE not in readme_path.read_text(encoding="utf-8")
    ):
        report.errors.append("Approval token phrase is not documented in staging README.")

    inspected_paths = [
        staging_dir,
        manifest_path,
        readme_path,
        operator_handoff_path,
        operator_approval_gate_path,
        approval_artifact_path,
    ]
    if report.promotion_bundle_path:
        inspected_paths.append(Path(report.promotion_bundle_path))
    if report.promotion_manifest_path:
        inspected_paths.append(Path(report.promotion_manifest_path))
    report.staging_paths_inside_workspace = all(
        _path_inside_workspace(path, workspace) for path in inspected_paths
    )

    report.artifact_paths = {
        "staging_dir": report.staging_path,
        "operator_approved_staging_manifest": report.operator_approved_staging_manifest_path,
        "staging_readme": report.staging_readme_path,
        "operator_handoff": report.operator_handoff_path,
        "operator_approval_gate": report.operator_approval_gate_path,
        "promotion_bundle": report.promotion_bundle_path,
        "promotion_manifest": report.promotion_manifest_path,
        "valid_approval_artifact": str(approval_artifact_path.resolve()),
    }

    checks = {
        "approval_gate_verdict_pass": report.approval_gate_verdict == "PASS",
        "operator_approval_valid": report.operator_approval_valid,
        "tamper_evidence_verdict_pass": report.tamper_evidence_verdict == "PASS",
        "all_tamper_cases_detected": report.all_tamper_cases_detected,
        "promotion_item_count": report.promotion_item_count == 2,
        "excluded_rejected_count": report.excluded_rejected_count == 1,
        "approved_candidate_included": report.approved_candidate_included,
        "edited_candidate_included": report.edited_candidate_included,
        "edited_promoted_text_preserved": report.edited_promoted_text_preserved,
        "rejected_candidate_excluded": report.rejected_candidate_excluded,
        "promotion_manifest_hash_present": report.promotion_manifest_hash_present,
        "operator_handoff_hash_present": report.operator_handoff_hash_present,
        "approval_gate_hash_present": report.approval_gate_hash_present,
        "approval_token_phrase_recorded": report.approval_token_phrase == APPROVAL_TOKEN_PHRASE,
        "ready_for_operator_approved_staging": report.ready_for_operator_approved_staging,
        "not_ready_for_live_memory_write": not report.ready_for_live_memory_write,
        "future_live_write_blocked": not report.future_live_write_allowed,
        "explicit_operator_approval_required": report.requires_explicit_operator_approval,
        "live_write_blocked_reason_present": bool(report.live_write_blocked_reason),
        "staging_readme_created": report.staging_readme_created,
        "staging_readme_hash_present": bool(report.staging_readme_sha256),
        "staging_paths_inside_workspace": report.staging_paths_inside_workspace,
        "staged_item_count": len(report.staged_items) == 2,
    }
    for check_name, passed in checks.items():
        if not passed:
            report.errors.append(f"{check_name} failed")

    for flag_name in (
        "model_called",
        "embeddings_used",
        "live_memory_written",
        "live_vector_db_written",
        "account_api_network_accessed",
        "autonomy_enabled",
    ):
        if getattr(report, flag_name):
            report.errors.append(f"{flag_name} unexpectedly true.")

    report.verdict = "PASS" if not report.errors else "FAIL"
    if report.verdict != "PASS":
        report.ready_for_operator_approved_staging = False
        _write_json(manifest_path, report.to_manifest_dict())
        try:
            loaded = _load_json(manifest_path)
            report.operator_approved_staging_manifest_valid_json = (
                isinstance(loaded, dict) and loaded.get("verdict") != "PASS"
            )
        except (OSError, json.JSONDecodeError, ValueError):
            report.operator_approved_staging_manifest_valid_json = False
        return report

    _write_json(manifest_path, report.to_manifest_dict())
    try:
        loaded_manifest = _load_json(manifest_path)
        report.operator_approved_staging_manifest_valid_json = (
            isinstance(loaded_manifest, dict) and loaded_manifest.get("verdict") == "PASS"
        )
    except (OSError, json.JSONDecodeError, ValueError):
        report.operator_approved_staging_manifest_valid_json = False
    if not report.operator_approved_staging_manifest_valid_json:
        report.errors.append("Operator-approved staging manifest JSON is invalid.")
        report.verdict = "FAIL"
        report.ready_for_operator_approved_staging = False
        _write_json(manifest_path, report.to_manifest_dict())
        return report
    _write_json(manifest_path, report.to_manifest_dict())
    return report


def _build_operator_approved_staging(
    workspace: Path,
) -> ApprovedPromotionOperatorApprovedStagingReport:
    report = ApprovedPromotionOperatorApprovedStagingReport(
        verdict="FAIL",
        workspace=str(workspace.resolve()),
        workspace_preserved=True,
        autonomy_enabled=_read_autonomy_enabled(),
    )
    if report.autonomy_enabled:
        report.errors.append(
            "Autonomy is enabled; approved promotion operator-approved staging smoke is blocked."
        )
        return report

    gate_report = run_memory_review_approved_promotion_operator_approval_gate_smoke(
        base_dir=workspace,
        keep_temp=True,
    )
    return _assemble_operator_approved_staging(workspace, gate_report)


def run_memory_review_approved_promotion_operator_approved_staging_smoke(
    *,
    base_dir: Path | None = None,
    keep_temp: bool = False,
) -> ApprovedPromotionOperatorApprovedStagingReport:
    """Build and validate a dry-run operator-approved staging package."""
    owned_temp = base_dir is None
    workspace = (
        Path(tempfile.mkdtemp(prefix="elysia_memory_operator_approved_staging_"))
        if owned_temp
        else _reject_dangerous_base(Path(base_dir))
    )
    workspace.mkdir(parents=True, exist_ok=True)
    try:
        report = _build_operator_approved_staging(workspace)
        report.workspace_preserved = (not owned_temp) or keep_temp
        return report
    finally:
        if owned_temp and not keep_temp:
            shutil.rmtree(workspace, ignore_errors=True)


def format_operator_approved_staging_summary(
    report: ApprovedPromotionOperatorApprovedStagingReport,
) -> str:
    lines = [
        "Memory review approved promotion operator-approved staging smoke",
        "=" * 67,
        f"Verdict: {report.verdict}",
        f"Workspace: {report.workspace}",
        f"Workspace preserved: {report.workspace_preserved}",
        f"Staging path: {report.staging_path}",
        f"Staging manifest: {report.operator_approved_staging_manifest_path}",
        f"Staging README: {report.staging_readme_path}",
        "",
        "Staging checks:",
        f"  operator-approved staging manifest valid JSON: {report.operator_approved_staging_manifest_valid_json}",
        f"  approval_gate_verdict: {report.approval_gate_verdict}",
        f"  operator_approval_valid: {report.operator_approval_valid}",
        f"  tamper_evidence_verdict: {report.tamper_evidence_verdict}",
        f"  promotion_item_count: {report.promotion_item_count}",
        f"  ready_for_operator_approved_staging: {report.ready_for_operator_approved_staging}",
        f"  ready_for_live_memory_write: {report.ready_for_live_memory_write}",
        f"  future_live_write_allowed: {report.future_live_write_allowed}",
        f"  staging paths inside workspace: {report.staging_paths_inside_workspace}",
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
        description=(
            "Run local-only Memory review approved promotion operator-approved staging smoke."
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
        report = run_memory_review_approved_promotion_operator_approved_staging_smoke(
            base_dir=args.base_dir,
            keep_temp=args.keep_temp,
        )
    except ValueError as exc:
        report = ApprovedPromotionOperatorApprovedStagingReport(
            verdict="FAIL",
            workspace=str(args.base_dir or ""),
            workspace_preserved=False,
            autonomy_enabled=_read_autonomy_enabled(),
            errors=[str(exc)],
        )

    if args.json:
        print(json.dumps(report.to_dict(), indent=2, ensure_ascii=False))
    else:
        print(format_operator_approved_staging_summary(report))
    return 0 if report.verdict == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
