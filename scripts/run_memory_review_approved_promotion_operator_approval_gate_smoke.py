#!/usr/bin/env python3
"""Dry-run/local smoke proving operator approval is explicit and handoff-bound.

This smoke builds the existing approved-promotion operator handoff, then checks
that the handoff cannot advance to operator-approved staging unless a local
approval artifact contains the expected dry-run token and references the current
handoff hash. It never writes live runtime memory, vector DB data, models,
embeddings, networks, live accounts, UI actions, or background work.
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
from typing import Any, Dict, List, Sequence, Tuple

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from run_memory_review_approved_promotion_operator_handoff_smoke import (  # noqa: E402
    run_memory_review_approved_promotion_operator_handoff_smoke,
)

APPROVAL_GATE_DIRNAME = "approved_promotion_operator_approval_gate"
APPROVAL_GATE_FILENAME = "operator_approval_gate.json"
APPROVAL_GATE_README_FILENAME = "APPROVAL_GATE_README.md"
APPROVAL_ARTIFACT_FILENAME = "operator_approval.json"
APPROVAL_TOKEN_PHRASE = "APPROVE_DRY_RUN_MEMORY_PROMOTION_STAGING_ONLY"
APPROVAL_SCOPE = "dry_run_memory_promotion_staging_only"

LIVE_WRITE_BLOCKED_REASON = (
    "Live memory writing remains intentionally not implemented or enabled in "
    "this dry-run approved-promotion operator approval gate campaign."
)


@dataclass
class ApprovalCaseResult:
    case_name: str
    expected_verdict: str
    actual_verdict: str
    detected: bool
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ApprovedPromotionOperatorApprovalGateReport:
    verdict: str
    workspace: str
    workspace_preserved: bool
    approval_gate_path: str = ""
    operator_approval_gate_path: str = ""
    operator_approval_gate_valid_json: bool = False
    approval_gate_readme_path: str = ""
    approval_gate_readme_created: bool = False
    handoff_path: str = ""
    operator_handoff_path: str = ""
    operator_handoff_sha256: str = ""
    handoff_ready_for_operator_review: bool = False
    handoff_ready_for_live_memory_write: bool = False
    approval_artifact_path: str = ""
    approval_case_count: int = 0
    approval_cases: List[Dict[str, Any]] = field(default_factory=list)
    missing_approval_fails_closed: bool = False
    invalid_token_fails_closed: bool = False
    mismatched_handoff_hash_fails_closed: bool = False
    stale_approval_fails_closed: bool = False
    valid_approval_passes_dry_run_staging: bool = False
    ready_for_operator_approved_staging: bool = False
    ready_for_live_memory_write: bool = False
    requires_explicit_operator_approval: bool = True
    future_live_write_allowed: bool = False
    live_write_blocked_reason: str = LIVE_WRITE_BLOCKED_REASON
    approval_scope: str = APPROVAL_SCOPE
    approval_token_phrase_documented: bool = False
    approval_paths_inside_workspace: bool = False
    default_state_blocked: bool = True
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


def _load_json(path: Path) -> Dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"JSON file does not contain an object: {path}")
    return payload


def _approval_payload(
    *,
    handoff_sha256: str,
    token: str = APPROVAL_TOKEN_PHRASE,
    scope: str = APPROVAL_SCOPE,
    approved_for_dry_run_staging: bool = True,
    approved_for_live_memory_write: bool = False,
    dry_run: bool = True,
    local_only: bool = True,
    handoff_id: str | None = None,
) -> Dict[str, Any]:
    current_handoff_id = handoff_id if handoff_id is not None else handoff_sha256
    return {
        "approval_id": "operator-approval-dry-run-staging",
        "handoff_id": current_handoff_id,
        "handoff_sha256": handoff_sha256,
        "operator_approval_token": token,
        "approval_scope": scope,
        "approved_for_dry_run_staging": approved_for_dry_run_staging,
        "approved_for_live_memory_write": approved_for_live_memory_write,
        "requires_explicit_operator_approval": True,
        "dry_run": dry_run,
        "local_only": local_only,
    }


def _write_json(path: Path, payload: Dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return path


def _write_approval_artifact(path: Path, payload: Dict[str, Any]) -> Path:
    return _write_json(path, payload)


def _evaluate_approval_artifact(
    approval_path: Path,
    *,
    expected_handoff_sha256: str,
) -> Tuple[str, List[str]]:
    errors: List[str] = []
    if not approval_path.is_file():
        return "FAIL", [f"missing_approval_artifact: {approval_path}"]

    try:
        approval = _load_json(approval_path)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        return "FAIL", [f"invalid_approval_artifact: {exc}"]

    required_fields = (
        "approval_id",
        "handoff_id",
        "handoff_sha256",
        "operator_approval_token",
        "approval_scope",
        "approved_for_dry_run_staging",
        "approved_for_live_memory_write",
        "requires_explicit_operator_approval",
        "dry_run",
        "local_only",
    )
    missing_fields = [field_name for field_name in required_fields if field_name not in approval]
    if missing_fields:
        errors.append("missing_approval_field: " + ", ".join(missing_fields))

    if approval.get("operator_approval_token") != APPROVAL_TOKEN_PHRASE:
        errors.append("invalid_approval_token")
    if approval.get("handoff_sha256") != expected_handoff_sha256:
        errors.append("mismatched_handoff_hash")
    if approval.get("handoff_id") != expected_handoff_sha256:
        errors.append("stale_or_mismatched_handoff_id")
    if approval.get("approval_scope") != APPROVAL_SCOPE:
        errors.append("invalid_approval_scope")
    if approval.get("approved_for_dry_run_staging") is not True:
        errors.append("dry_run_staging_not_approved")
    if approval.get("approved_for_live_memory_write") is not False:
        errors.append("live_memory_write_must_remain_false")
    if approval.get("requires_explicit_operator_approval") is not True:
        errors.append("explicit_operator_approval_not_required")
    if approval.get("dry_run") is not True:
        errors.append("dry_run_must_be_true")
    if approval.get("local_only") is not True:
        errors.append("local_only_must_be_true")

    for flag_name in (
        "model_called",
        "embeddings_used",
        "live_memory_written",
        "live_vector_db_written",
        "account_api_network_accessed",
        "autonomy_enabled",
    ):
        if approval.get(flag_name) is True:
            errors.append(f"{flag_name}_must_remain_false")

    return ("PASS" if not errors else "FAIL"), errors


def _case_result(
    *,
    case_name: str,
    expected_verdict: str,
    approval_path: Path,
    expected_handoff_sha256: str,
) -> ApprovalCaseResult:
    actual_verdict, errors = _evaluate_approval_artifact(
        approval_path,
        expected_handoff_sha256=expected_handoff_sha256,
    )
    ready_for_staging = actual_verdict == "PASS"
    return ApprovalCaseResult(
        case_name=case_name,
        expected_verdict=expected_verdict,
        actual_verdict=actual_verdict,
        detected=actual_verdict == expected_verdict,
        details={
            "approval_artifact_path": str(approval_path.resolve()),
            "ready_for_operator_approved_staging": ready_for_staging,
            "ready_for_live_memory_write": False,
            "future_live_write_allowed": False,
            "errors": errors,
        },
    )


def _write_readme(readme_path: Path, report: ApprovedPromotionOperatorApprovalGateReport) -> None:
    lines = [
        "# Approved Promotion Operator Approval Gate",
        "",
        "This dry-run gate proves that an operator handoff remains blocked until",
        "an explicit local approval artifact references the current handoff hash.",
        "",
        "## Approval token",
        "",
        f"`{APPROVAL_TOKEN_PHRASE}`",
        "",
        "The token is valid only with:",
        "",
        f"- `approval_scope`: `{APPROVAL_SCOPE}`",
        "- `approved_for_dry_run_staging`: `true`",
        "- `approved_for_live_memory_write`: `false`",
        "- `dry_run`: `true`",
        "- `local_only`: `true`",
        "- `handoff_sha256` and `handoff_id` matching the current handoff hash",
        "",
        "## Fail-closed cases",
        "",
        "- Missing approval artifact or token fails closed.",
        "- Invalid approval token fails closed.",
        "- Mismatched handoff hash fails closed.",
        "- Stale or mismatched handoff id fails closed.",
        "",
        "## Safety",
        "",
        "- Valid approval allows dry-run staging only.",
        "- Valid approval does not allow live memory writing.",
        "- Live runtime memory writing is not implemented or enabled.",
        "- Vector DB writing is not implemented or enabled.",
        "- No models, embeddings, live accounts, API/network access, UI actions, or routes are used.",
        "- `elysia/api/server.py`, `project_guardian/core.py`, and `config/autonomy.json` remain untouched.",
        "",
        "## Current artifacts",
        "",
        f"- Handoff JSON: `{report.operator_handoff_path}`",
        f"- Handoff SHA-256: `{report.operator_handoff_sha256}`",
        f"- Approval gate JSON: `{report.operator_approval_gate_path}`",
        f"- Valid approval artifact: `{report.approval_artifact_path}`",
    ]
    readme_path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")


def _build_operator_approval_gate(
    workspace: Path,
) -> ApprovedPromotionOperatorApprovalGateReport:
    report = ApprovedPromotionOperatorApprovalGateReport(
        verdict="FAIL",
        workspace=str(workspace.resolve()),
        workspace_preserved=True,
        autonomy_enabled=_read_autonomy_enabled(),
    )
    if report.autonomy_enabled:
        report.errors.append(
            "Autonomy is enabled; approved promotion operator approval gate smoke is blocked."
        )
        return report

    handoff_report = run_memory_review_approved_promotion_operator_handoff_smoke(
        base_dir=workspace,
        keep_temp=True,
    )
    report.handoff_path = handoff_report.handoff_path
    report.operator_handoff_path = handoff_report.operator_handoff_path
    report.handoff_ready_for_operator_review = bool(
        getattr(handoff_report, "ready_for_operator_review", False)
    )
    report.handoff_ready_for_live_memory_write = bool(
        getattr(handoff_report, "ready_for_live_memory_write", False)
    )
    if handoff_report.verdict != "PASS":
        report.errors.append(
            "Operator handoff smoke did not pass: " + "; ".join(handoff_report.errors)
        )
        return report
    if not report.handoff_ready_for_operator_review:
        report.errors.append("Operator handoff is not ready for operator review.")
    if report.handoff_ready_for_live_memory_write:
        report.errors.append("Operator handoff unexpectedly ready for live memory write.")

    operator_handoff_path = Path(report.operator_handoff_path)
    report.operator_handoff_sha256 = _sha256_file(operator_handoff_path)

    gate_dir = workspace / APPROVAL_GATE_DIRNAME
    cases_dir = gate_dir / "approval_cases"
    gate_dir.mkdir(parents=True, exist_ok=True)
    cases_dir.mkdir(parents=True, exist_ok=True)

    gate_path = gate_dir / APPROVAL_GATE_FILENAME
    readme_path = gate_dir / APPROVAL_GATE_README_FILENAME
    valid_approval_path = workspace / APPROVAL_ARTIFACT_FILENAME
    missing_approval_path = cases_dir / "missing_operator_approval.json"
    invalid_token_path = cases_dir / "invalid_token_operator_approval.json"
    mismatched_hash_path = cases_dir / "mismatched_handoff_hash_operator_approval.json"
    stale_handoff_path = cases_dir / "stale_handoff_id_operator_approval.json"

    _write_approval_artifact(
        invalid_token_path,
        _approval_payload(
            handoff_sha256=report.operator_handoff_sha256,
            token="INVALID_DRY_RUN_MEMORY_PROMOTION_TOKEN",
        ),
    )
    _write_approval_artifact(
        mismatched_hash_path,
        _approval_payload(
            handoff_sha256="0" * 64,
            handoff_id="0" * 64,
        ),
    )
    _write_approval_artifact(
        stale_handoff_path,
        _approval_payload(
            handoff_sha256=report.operator_handoff_sha256,
            handoff_id="stale-handoff-id",
        ),
    )
    _write_approval_artifact(
        valid_approval_path,
        _approval_payload(handoff_sha256=report.operator_handoff_sha256),
    )

    case_results = [
        _case_result(
            case_name="missing_approval",
            expected_verdict="FAIL",
            approval_path=missing_approval_path,
            expected_handoff_sha256=report.operator_handoff_sha256,
        ),
        _case_result(
            case_name="invalid_approval_token",
            expected_verdict="FAIL",
            approval_path=invalid_token_path,
            expected_handoff_sha256=report.operator_handoff_sha256,
        ),
        _case_result(
            case_name="mismatched_handoff_hash",
            expected_verdict="FAIL",
            approval_path=mismatched_hash_path,
            expected_handoff_sha256=report.operator_handoff_sha256,
        ),
        _case_result(
            case_name="stale_handoff_id",
            expected_verdict="FAIL",
            approval_path=stale_handoff_path,
            expected_handoff_sha256=report.operator_handoff_sha256,
        ),
        _case_result(
            case_name="valid_explicit_dry_run_approval",
            expected_verdict="PASS",
            approval_path=valid_approval_path,
            expected_handoff_sha256=report.operator_handoff_sha256,
        ),
    ]

    cases_by_name = {case.case_name: case for case in case_results}
    report.approval_gate_path = str(gate_dir.resolve())
    report.operator_approval_gate_path = str(gate_path.resolve())
    report.approval_gate_readme_path = str(readme_path.resolve())
    report.approval_artifact_path = str(valid_approval_path.resolve())
    report.approval_cases = [case.to_dict() for case in case_results]
    report.approval_case_count = len(case_results)
    report.missing_approval_fails_closed = (
        cases_by_name["missing_approval"].actual_verdict == "FAIL"
        and cases_by_name["missing_approval"].detected
    )
    report.invalid_token_fails_closed = (
        cases_by_name["invalid_approval_token"].actual_verdict == "FAIL"
        and cases_by_name["invalid_approval_token"].detected
    )
    report.mismatched_handoff_hash_fails_closed = (
        cases_by_name["mismatched_handoff_hash"].actual_verdict == "FAIL"
        and cases_by_name["mismatched_handoff_hash"].detected
    )
    report.stale_approval_fails_closed = (
        cases_by_name["stale_handoff_id"].actual_verdict == "FAIL"
        and cases_by_name["stale_handoff_id"].detected
    )
    report.valid_approval_passes_dry_run_staging = (
        cases_by_name["valid_explicit_dry_run_approval"].actual_verdict == "PASS"
        and cases_by_name["valid_explicit_dry_run_approval"].detected
    )
    report.ready_for_operator_approved_staging = (
        report.handoff_ready_for_operator_review
        and not report.handoff_ready_for_live_memory_write
        and report.valid_approval_passes_dry_run_staging
    )
    report.ready_for_live_memory_write = False
    report.future_live_write_allowed = False
    report.default_state_blocked = report.missing_approval_fails_closed

    report.approval_paths_inside_workspace = all(
        _path_inside_workspace(path, workspace)
        for path in (
            gate_dir,
            cases_dir,
            gate_path,
            readme_path,
            valid_approval_path,
            missing_approval_path,
            invalid_token_path,
            mismatched_hash_path,
            stale_handoff_path,
            operator_handoff_path,
            Path(report.handoff_path),
        )
    )

    report.artifact_paths = {
        "approval_gate_dir": report.approval_gate_path,
        "operator_approval_gate": report.operator_approval_gate_path,
        "approval_gate_readme": report.approval_gate_readme_path,
        "operator_handoff": report.operator_handoff_path,
        "valid_approval_artifact": report.approval_artifact_path,
        "missing_approval_artifact": str(missing_approval_path.resolve()),
        "invalid_token_approval_artifact": str(invalid_token_path.resolve()),
        "mismatched_handoff_hash_approval_artifact": str(mismatched_hash_path.resolve()),
        "stale_handoff_id_approval_artifact": str(stale_handoff_path.resolve()),
    }

    _write_readme(readme_path, report)
    report.approval_gate_readme_created = readme_path.is_file()
    report.approval_token_phrase_documented = (
        report.approval_gate_readme_created
        and APPROVAL_TOKEN_PHRASE in readme_path.read_text(encoding="utf-8")
    )

    checks = {
        "handoff_ready_for_operator_review": report.handoff_ready_for_operator_review,
        "handoff_not_ready_for_live_memory_write": not report.handoff_ready_for_live_memory_write,
        "operator_handoff_hash_present": bool(report.operator_handoff_sha256),
        "approval_case_count": report.approval_case_count == 5,
        "all_cases_detected": all(case["detected"] for case in report.approval_cases),
        "missing_approval_fails_closed": report.missing_approval_fails_closed,
        "invalid_token_fails_closed": report.invalid_token_fails_closed,
        "mismatched_handoff_hash_fails_closed": report.mismatched_handoff_hash_fails_closed,
        "stale_approval_fails_closed": report.stale_approval_fails_closed,
        "valid_approval_passes_dry_run_staging": report.valid_approval_passes_dry_run_staging,
        "ready_for_operator_approved_staging": report.ready_for_operator_approved_staging,
        "not_ready_for_live_memory_write": not report.ready_for_live_memory_write,
        "future_live_write_blocked": not report.future_live_write_allowed,
        "explicit_operator_approval_required": report.requires_explicit_operator_approval,
        "live_write_blocked_reason_present": bool(report.live_write_blocked_reason),
        "approval_token_phrase_documented": report.approval_token_phrase_documented,
        "approval_paths_inside_workspace": report.approval_paths_inside_workspace,
        "readme_created": report.approval_gate_readme_created,
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
    _write_json(gate_path, report.to_dict())
    try:
        loaded_report = _load_json(gate_path)
        report.operator_approval_gate_valid_json = isinstance(loaded_report, dict)
    except (OSError, json.JSONDecodeError, ValueError):
        report.operator_approval_gate_valid_json = False
    if not report.operator_approval_gate_valid_json:
        report.errors.append("Operator approval gate JSON is invalid.")
        report.verdict = "FAIL"
    _write_json(gate_path, report.to_dict())
    return report


def run_memory_review_approved_promotion_operator_approval_gate_smoke(
    *,
    base_dir: Path | None = None,
    keep_temp: bool = False,
) -> ApprovedPromotionOperatorApprovalGateReport:
    """Build and validate a dry-run operator approval gate package."""
    owned_temp = base_dir is None
    workspace = (
        Path(tempfile.mkdtemp(prefix="elysia_memory_operator_approval_gate_"))
        if owned_temp
        else _reject_dangerous_base(Path(base_dir))
    )
    workspace.mkdir(parents=True, exist_ok=True)
    try:
        report = _build_operator_approval_gate(workspace)
        report.workspace_preserved = (not owned_temp) or keep_temp
        return report
    finally:
        if owned_temp and not keep_temp:
            shutil.rmtree(workspace, ignore_errors=True)


def format_operator_approval_gate_summary(
    report: ApprovedPromotionOperatorApprovalGateReport,
) -> str:
    lines = [
        "Memory review approved promotion operator approval gate smoke",
        "=" * 69,
        f"Verdict: {report.verdict}",
        f"Workspace: {report.workspace}",
        f"Workspace preserved: {report.workspace_preserved}",
        f"Approval gate path: {report.approval_gate_path}",
        f"Approval gate JSON: {report.operator_approval_gate_path}",
        f"Approval artifact: {report.approval_artifact_path}",
        f"Operator handoff JSON: {report.operator_handoff_path}",
        "",
        "Approval gate checks:",
        f"  operator approval gate valid JSON: {report.operator_approval_gate_valid_json}",
        f"  approval case count: {report.approval_case_count}",
        f"  missing approval fails closed: {report.missing_approval_fails_closed}",
        f"  invalid token fails closed: {report.invalid_token_fails_closed}",
        f"  mismatched handoff hash fails closed: {report.mismatched_handoff_hash_fails_closed}",
        f"  stale approval fails closed: {report.stale_approval_fails_closed}",
        f"  valid approval passes dry-run staging: {report.valid_approval_passes_dry_run_staging}",
        f"  ready_for_operator_approved_staging: {report.ready_for_operator_approved_staging}",
        f"  ready_for_live_memory_write: {report.ready_for_live_memory_write}",
        f"  future_live_write_allowed: {report.future_live_write_allowed}",
        f"  approval paths inside workspace: {report.approval_paths_inside_workspace}",
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
            "Run local-only Memory review approved promotion operator approval gate smoke."
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
        report = run_memory_review_approved_promotion_operator_approval_gate_smoke(
            base_dir=args.base_dir,
            keep_temp=args.keep_temp,
        )
    except ValueError as exc:
        report = ApprovedPromotionOperatorApprovalGateReport(
            verdict="FAIL",
            workspace=str(args.base_dir or ""),
            workspace_preserved=False,
            autonomy_enabled=_read_autonomy_enabled(),
            errors=[str(exc)],
        )

    if args.json:
        print(json.dumps(report.to_dict(), indent=2, ensure_ascii=False))
    else:
        print(format_operator_approval_gate_summary(report))
    return 0 if report.verdict == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
