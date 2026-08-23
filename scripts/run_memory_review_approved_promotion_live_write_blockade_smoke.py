#!/usr/bin/env python3
"""Dry-run/local smoke proving a clean staging package cannot write live memory.

This smoke builds a valid operator-approved staging package from local fixtures,
validates the clean package and its staging tamper-evidence checker, then
records simulated live-memory and vector-DB write requests and denies them
before any write occurs. It never calls a live memory writer, never creates
runtime memory files, never creates vector DB files, and never calls models,
embeddings, networks, live accounts, or UI routes.
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

from run_memory_review_approved_promotion_operator_approved_staging_smoke import (  # noqa: E402
    run_memory_review_approved_promotion_operator_approved_staging_smoke,
)
from run_memory_review_approved_promotion_operator_approved_staging_tamper_evidence_smoke import (  # noqa: E402
    audit_operator_approved_staging_manifest,
)

BLOCKADE_DIRNAME = "approved_promotion_live_write_blockade"
BLOCKADE_REPORT_FILENAME = "live_write_blockade_report.json"
BLOCKADE_README_FILENAME = "LIVE_WRITE_BLOCKADE_README.md"
FORBIDDEN_MEMORY_RELATIVE = "forbidden_live_writes/runtime_memory.jsonl"
FORBIDDEN_VECTOR_RELATIVE = "forbidden_live_writes/vector_db.index"

LIVE_WRITE_DENIAL_REASON = (
    "Live memory write is blocked because this campaign only proves dry-run "
    "staging safety. A separate explicit future milestone is required before "
    "any live memory or vector DB write path may exist."
)
VECTOR_WRITE_DENIAL_REASON = (
    "Vector DB write is blocked because this campaign only proves dry-run "
    "staging safety. A separate explicit future milestone is required before "
    "any live memory or vector DB write path may exist."
)


@dataclass
class ApprovedPromotionLiveWriteBlockadeReport:
    verdict: str
    workspace: str
    blockade_path: str = ""
    live_write_blockade_report_path: str = ""
    live_write_blockade_report_valid_json: bool = False
    source_staging_manifest_path: str = ""
    source_staging_manifest_sha256: str = ""
    source_staging_tamper_evidence_verdict: str = "UNKNOWN"
    clean_staging_valid: bool = False
    operator_approval_valid: bool = False
    approval_gate_verdict: str = "UNKNOWN"
    tamper_evidence_verdict: str = "UNKNOWN"
    ready_for_operator_approved_staging: bool = False
    ready_for_live_memory_write: bool = False
    future_live_write_allowed: bool = False
    live_memory_write_requested: bool = False
    live_memory_write_allowed: bool = False
    live_memory_write_denied: bool = False
    live_memory_write_denial_reason: str = ""
    live_memory_write_attempted: bool = False
    live_memory_write_performed: bool = False
    live_memory_write_path: str = ""
    live_memory_write_path_created: bool = False
    vector_db_write_requested: bool = False
    vector_db_write_allowed: bool = False
    vector_db_write_denied: bool = False
    vector_db_write_denial_reason: str = ""
    vector_db_write_attempted: bool = False
    vector_db_write_performed: bool = False
    vector_db_write_path: str = ""
    vector_db_write_path_created: bool = False
    runtime_memory_files_created: int = 0
    vector_db_files_created: int = 0
    promotion_item_count: int = 0
    approved_candidate_count: int = 0
    edited_candidate_count: int = 0
    excluded_rejected_count: int = 0
    approved_candidate_included: bool = False
    edited_candidate_included: bool = False
    rejected_candidate_excluded: bool = False
    operator_required: bool = True
    requires_future_live_write_milestone: bool = True
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
    blockade_readme_path: str = ""
    artifact_paths: Dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def to_report_dict(self) -> Dict[str, Any]:
        return {
            "verdict": self.verdict,
            "workspace": self.workspace,
            "blockade_path": self.blockade_path,
            "live_write_blockade_report_path": self.live_write_blockade_report_path,
            "live_write_blockade_report_valid_json": (
                self.live_write_blockade_report_valid_json
            ),
            "source_staging_manifest_path": self.source_staging_manifest_path,
            "source_staging_manifest_sha256": self.source_staging_manifest_sha256,
            "source_staging_tamper_evidence_verdict": (
                self.source_staging_tamper_evidence_verdict
            ),
            "clean_staging_valid": self.clean_staging_valid,
            "operator_approval_valid": self.operator_approval_valid,
            "approval_gate_verdict": self.approval_gate_verdict,
            "tamper_evidence_verdict": self.tamper_evidence_verdict,
            "ready_for_operator_approved_staging": (
                self.ready_for_operator_approved_staging
            ),
            "ready_for_live_memory_write": self.ready_for_live_memory_write,
            "future_live_write_allowed": self.future_live_write_allowed,
            "live_memory_write_requested": self.live_memory_write_requested,
            "live_memory_write_allowed": self.live_memory_write_allowed,
            "live_memory_write_denied": self.live_memory_write_denied,
            "live_memory_write_denial_reason": self.live_memory_write_denial_reason,
            "live_memory_write_attempted": self.live_memory_write_attempted,
            "live_memory_write_performed": self.live_memory_write_performed,
            "live_memory_write_path": self.live_memory_write_path,
            "live_memory_write_path_created": self.live_memory_write_path_created,
            "vector_db_write_requested": self.vector_db_write_requested,
            "vector_db_write_allowed": self.vector_db_write_allowed,
            "vector_db_write_denied": self.vector_db_write_denied,
            "vector_db_write_denial_reason": self.vector_db_write_denial_reason,
            "vector_db_write_attempted": self.vector_db_write_attempted,
            "vector_db_write_performed": self.vector_db_write_performed,
            "vector_db_write_path": self.vector_db_write_path,
            "vector_db_write_path_created": self.vector_db_write_path_created,
            "runtime_memory_files_created": self.runtime_memory_files_created,
            "vector_db_files_created": self.vector_db_files_created,
            "promotion_item_count": self.promotion_item_count,
            "approved_candidate_count": self.approved_candidate_count,
            "edited_candidate_count": self.edited_candidate_count,
            "excluded_rejected_count": self.excluded_rejected_count,
            "approved_candidate_included": self.approved_candidate_included,
            "edited_candidate_included": self.edited_candidate_included,
            "rejected_candidate_excluded": self.rejected_candidate_excluded,
            "operator_required": self.operator_required,
            "requires_future_live_write_milestone": (
                self.requires_future_live_write_milestone
            ),
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


def _load_json(path: Path) -> Dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"JSON file does not contain an object: {path}")
    return payload


def deny_live_memory_write_request(requested_path: Path) -> Dict[str, Any]:
    """Record a live-memory write request and deny it before any write."""
    return {
        "requested": True,
        "allowed": False,
        "denied": True,
        "attempted": False,
        "performed": False,
        "path": str(requested_path),
        "path_created": requested_path.exists(),
        "denial_reason": LIVE_WRITE_DENIAL_REASON,
    }


def deny_vector_db_write_request(requested_path: Path) -> Dict[str, Any]:
    """Record a vector-DB write request and deny it before any write."""
    return {
        "requested": True,
        "allowed": False,
        "denied": True,
        "attempted": False,
        "performed": False,
        "path": str(requested_path),
        "path_created": requested_path.exists(),
        "denial_reason": VECTOR_WRITE_DENIAL_REASON,
    }


def _write_readme(readme_path: Path, report: ApprovedPromotionLiveWriteBlockadeReport) -> None:
    lines = [
        "# Approved Promotion Live-Write Blockade",
        "",
        "This dry-run report proves that a clean, untampered, operator-approved",
        "staging package still cannot write live memory or vector DB data.",
        "",
        "## Result",
        "",
        f"- Clean staging validates as `{'PASS' if report.clean_staging_valid else 'FAIL'}`.",
        f"- Staging tamper evidence validates as `{report.source_staging_tamper_evidence_verdict}`.",
        f"- Promotion tamper evidence validates as `{report.tamper_evidence_verdict}`.",
        "- Live memory write request is denied.",
        "- Vector DB write request is denied.",
        "- No live memory write is attempted.",
        "- No vector DB write is attempted.",
        "- No runtime memory file is created.",
        "- No vector DB file is created.",
        "",
        "## Denial reasons",
        "",
        f"- Live memory: {report.live_memory_write_denial_reason}",
        f"- Vector DB: {report.vector_db_write_denial_reason}",
        "",
        "## Safety",
        "",
        "- Live memory writing is not implemented or enabled.",
        "- Vector DB writing is not implemented or enabled.",
        "- Future live write requires a separate explicit milestone.",
        "- This campaign does not call models.",
        "- This campaign does not call embeddings.",
        "- This campaign does not use live accounts.",
        "- This campaign does not add UI actions or routes.",
        "- `elysia/api/server.py`, `project_guardian/core.py`, and `config/autonomy.json` remain untouched.",
        "",
        f"- `ready_for_operator_approved_staging`: `{str(report.ready_for_operator_approved_staging).lower()}`",
        f"- `ready_for_live_memory_write`: `{str(report.ready_for_live_memory_write).lower()}`",
        f"- `future_live_write_allowed`: `{str(report.future_live_write_allowed).lower()}`",
        f"- `requires_future_live_write_milestone`: `{str(report.requires_future_live_write_milestone).lower()}`",
    ]
    readme_path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")


def _build_live_write_blockade(
    workspace: Path,
) -> ApprovedPromotionLiveWriteBlockadeReport:
    report = ApprovedPromotionLiveWriteBlockadeReport(
        verdict="FAIL",
        workspace=str(workspace.resolve()),
        workspace_preserved=True,
        autonomy_enabled=_read_autonomy_enabled(),
        requires_future_live_write_milestone=True,
        ready_for_live_memory_write=False,
        future_live_write_allowed=False,
    )
    if report.autonomy_enabled:
        report.errors.append(
            "Autonomy is enabled; approved promotion live-write blockade smoke is blocked."
        )
        return report

    staging_report = run_memory_review_approved_promotion_operator_approved_staging_smoke(
        base_dir=workspace,
        keep_temp=True,
    )
    report.source_staging_manifest_path = str(
        getattr(staging_report, "operator_approved_staging_manifest_path", "") or ""
    )
    report.operator_approval_valid = bool(
        getattr(staging_report, "operator_approval_valid", False)
    )
    report.approval_gate_verdict = str(
        getattr(staging_report, "approval_gate_verdict", "UNKNOWN") or "UNKNOWN"
    )
    report.tamper_evidence_verdict = str(
        getattr(staging_report, "tamper_evidence_verdict", "UNKNOWN") or "UNKNOWN"
    )
    report.ready_for_operator_approved_staging = bool(
        getattr(staging_report, "ready_for_operator_approved_staging", False)
    )
    report.promotion_item_count = int(getattr(staging_report, "promotion_item_count", 0) or 0)
    report.approved_candidate_count = int(
        getattr(staging_report, "approved_candidate_count", 0) or 0
    )
    report.edited_candidate_count = int(
        getattr(staging_report, "edited_candidate_count", 0) or 0
    )
    report.excluded_rejected_count = int(
        getattr(staging_report, "excluded_rejected_count", 0) or 0
    )
    report.approved_candidate_included = bool(
        getattr(staging_report, "approved_candidate_included", False)
    )
    report.edited_candidate_included = bool(
        getattr(staging_report, "edited_candidate_included", False)
    )
    report.rejected_candidate_excluded = bool(
        getattr(staging_report, "rejected_candidate_excluded", False)
    )

    staging_manifest_path = Path(report.source_staging_manifest_path)
    if staging_report.verdict != "PASS" or not staging_manifest_path.is_file():
        report.errors.append(
            "Operator-approved staging package did not validate as PASS; "
            "refusing to treat the package as live-write ready."
        )
        report.clean_staging_valid = False
    else:
        report.source_staging_manifest_sha256 = _sha256_file(staging_manifest_path)
        staging_audit_verdict, staging_audit_errors = audit_operator_approved_staging_manifest(
            staging_manifest_path
        )
        report.source_staging_tamper_evidence_verdict = staging_audit_verdict
        report.clean_staging_valid = (
            staging_report.verdict == "PASS"
            and staging_audit_verdict == "PASS"
            and not staging_audit_errors
            and bool(getattr(staging_report, "operator_approved_staging_manifest_valid_json", False))
        )
        if not report.clean_staging_valid:
            report.errors.append(
                "Clean staging tamper-evidence validation did not pass: "
                + "; ".join(staging_audit_errors)
            )

    memory_path = workspace / FORBIDDEN_MEMORY_RELATIVE
    vector_path = workspace / FORBIDDEN_VECTOR_RELATIVE
    report.live_memory_write_path = str(memory_path)
    report.vector_db_write_path = str(vector_path)

    memory_denial = deny_live_memory_write_request(memory_path)
    report.live_memory_write_requested = bool(memory_denial["requested"])
    report.live_memory_write_allowed = bool(memory_denial["allowed"])
    report.live_memory_write_denied = bool(memory_denial["denied"])
    report.live_memory_write_denial_reason = str(memory_denial["denial_reason"])
    report.live_memory_write_attempted = bool(memory_denial["attempted"])
    report.live_memory_write_performed = bool(memory_denial["performed"])
    report.live_memory_write_path_created = memory_path.exists()

    vector_denial = deny_vector_db_write_request(vector_path)
    report.vector_db_write_requested = bool(vector_denial["requested"])
    report.vector_db_write_allowed = bool(vector_denial["allowed"])
    report.vector_db_write_denied = bool(vector_denial["denied"])
    report.vector_db_write_denial_reason = str(vector_denial["denial_reason"])
    report.vector_db_write_attempted = bool(vector_denial["attempted"])
    report.vector_db_write_performed = bool(vector_denial["performed"])
    report.vector_db_write_path_created = vector_path.exists()

    report.runtime_memory_files_created = 1 if memory_path.exists() else 0
    report.vector_db_files_created = 1 if vector_path.exists() else 0
    report.live_memory_written = False
    report.live_vector_db_written = False

    blockade_dir = workspace / BLOCKADE_DIRNAME
    blockade_dir.mkdir(parents=True, exist_ok=True)
    report_path = blockade_dir / BLOCKADE_REPORT_FILENAME
    readme_path = blockade_dir / BLOCKADE_README_FILENAME
    report.blockade_path = str(blockade_dir.resolve())
    report.live_write_blockade_report_path = str(report_path.resolve())
    report.blockade_readme_path = str(readme_path.resolve())

    checks = {
        "clean_staging_valid": report.clean_staging_valid,
        "operator_approval_valid": report.operator_approval_valid,
        "approval_gate_verdict_pass": report.approval_gate_verdict == "PASS",
        "tamper_evidence_verdict_pass": report.tamper_evidence_verdict == "PASS",
        "source_staging_tamper_evidence_pass": (
            report.source_staging_tamper_evidence_verdict == "PASS"
        ),
        "ready_for_operator_approved_staging": report.ready_for_operator_approved_staging,
        "not_ready_for_live_memory_write": not report.ready_for_live_memory_write,
        "future_live_write_blocked": not report.future_live_write_allowed,
        "requires_future_live_write_milestone": report.requires_future_live_write_milestone,
        "live_memory_write_requested": report.live_memory_write_requested,
        "live_memory_write_denied": report.live_memory_write_denied,
        "live_memory_write_not_allowed": not report.live_memory_write_allowed,
        "live_memory_write_not_attempted": not report.live_memory_write_attempted,
        "live_memory_write_not_performed": not report.live_memory_write_performed,
        "live_memory_write_path_not_created": not report.live_memory_write_path_created,
        "vector_db_write_requested": report.vector_db_write_requested,
        "vector_db_write_denied": report.vector_db_write_denied,
        "vector_db_write_not_allowed": not report.vector_db_write_allowed,
        "vector_db_write_not_attempted": not report.vector_db_write_attempted,
        "vector_db_write_not_performed": not report.vector_db_write_performed,
        "vector_db_write_path_not_created": not report.vector_db_write_path_created,
        "runtime_memory_files_zero": report.runtime_memory_files_created == 0,
        "vector_db_files_zero": report.vector_db_files_created == 0,
        "denial_reason_present": bool(report.live_memory_write_denial_reason),
        "future_milestone_mentioned": "separate" in report.live_memory_write_denial_reason
        and "milestone" in report.live_memory_write_denial_reason,
        "promotion_item_count": report.promotion_item_count == 2,
        "excluded_rejected_count": report.excluded_rejected_count == 1,
        "approved_candidate_included": report.approved_candidate_included,
        "edited_candidate_included": report.edited_candidate_included,
        "rejected_candidate_excluded": report.rejected_candidate_excluded,
        "blockade_paths_inside_workspace": all(
            _path_inside_workspace(path, workspace)
            for path in (blockade_dir, report_path, readme_path, memory_path, vector_path)
        ),
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
    _write_readme(readme_path, report)
    _write_json(report_path, report.to_report_dict())
    try:
        loaded = _load_json(report_path)
        report.live_write_blockade_report_valid_json = (
            isinstance(loaded, dict) and loaded.get("verdict") == report.verdict
        )
    except (OSError, json.JSONDecodeError, ValueError):
        report.live_write_blockade_report_valid_json = False
        report.errors.append("Live-write blockade report JSON is invalid.")
        report.verdict = "FAIL"
    _write_json(report_path, report.to_report_dict())

    report.artifact_paths = {
        "blockade_dir": report.blockade_path,
        "live_write_blockade_report": report.live_write_blockade_report_path,
        "live_write_blockade_readme": report.blockade_readme_path,
        "source_staging_manifest": report.source_staging_manifest_path,
        "forbidden_live_memory_path": report.live_memory_write_path,
        "forbidden_vector_db_path": report.vector_db_write_path,
    }
    return report


def run_memory_review_approved_promotion_live_write_blockade_smoke(
    *,
    base_dir: Path | None = None,
    keep_temp: bool = False,
) -> ApprovedPromotionLiveWriteBlockadeReport:
    """Build clean staging and prove live memory/vector writes stay denied."""
    owned_temp = base_dir is None
    workspace = (
        Path(tempfile.mkdtemp(prefix="elysia_lwb_"))
        if owned_temp
        else _reject_dangerous_base(Path(base_dir))
    )
    workspace.mkdir(parents=True, exist_ok=True)
    try:
        report = _build_live_write_blockade(workspace)
        report.workspace_preserved = (not owned_temp) or keep_temp
        return report
    finally:
        if owned_temp and not keep_temp:
            shutil.rmtree(workspace, ignore_errors=True)


def format_live_write_blockade_summary(
    report: ApprovedPromotionLiveWriteBlockadeReport,
) -> str:
    lines = [
        "Memory review approved promotion live-write blockade smoke",
        "=" * 61,
        f"Verdict: {report.verdict}",
        f"Workspace: {report.workspace}",
        f"Workspace preserved: {report.workspace_preserved}",
        f"Blockade path: {report.blockade_path}",
        f"Blockade report: {report.live_write_blockade_report_path}",
        "",
        "Blockade checks:",
        f"  clean_staging_valid: {report.clean_staging_valid}",
        f"  source_staging_tamper_evidence_verdict: {report.source_staging_tamper_evidence_verdict}",
        f"  tamper_evidence_verdict: {report.tamper_evidence_verdict}",
        f"  approval_gate_verdict: {report.approval_gate_verdict}",
        f"  operator_approval_valid: {report.operator_approval_valid}",
        f"  ready_for_operator_approved_staging: {report.ready_for_operator_approved_staging}",
        f"  ready_for_live_memory_write: {report.ready_for_live_memory_write}",
        f"  future_live_write_allowed: {report.future_live_write_allowed}",
        f"  live_memory_write_denied: {report.live_memory_write_denied}",
        f"  vector_db_write_denied: {report.vector_db_write_denied}",
        f"  runtime_memory_files_created: {report.runtime_memory_files_created}",
        f"  vector_db_files_created: {report.vector_db_files_created}",
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
            "Run local-only Memory review approved promotion live-write blockade smoke."
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
        report = run_memory_review_approved_promotion_live_write_blockade_smoke(
            base_dir=args.base_dir,
            keep_temp=args.keep_temp,
        )
    except ValueError as exc:
        report = ApprovedPromotionLiveWriteBlockadeReport(
            verdict="FAIL",
            workspace=str(args.base_dir or ""),
            workspace_preserved=False,
            autonomy_enabled=_read_autonomy_enabled(),
            errors=[str(exc)],
        )

    if args.json:
        print(json.dumps(report.to_dict(), indent=2, ensure_ascii=False))
    else:
        print(format_live_write_blockade_summary(report))
    return 0 if report.verdict == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
