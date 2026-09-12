#!/usr/bin/env python3
"""Manual operator command: limited-live harmless smoke cycle in isolated temp workspace.

Runs preflight, packet registration, operator APPROVE, triple-gated execution,
content verification, rollback, and cleanup. Does not enable broad autonomy,
does not modify config/autonomy.json, and does not use shell/network/browser/API.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from project_guardian.live_action_approval_route import (  # noqa: E402
    LiveActionApprovalRouteStore,
    compute_packet_content_hash,
    get_approval_packet_detail,
    is_approval_route_executes_smoke_enabled,
    is_live_action_approval_route_enabled,
    record_operator_decision_for_packet,
)
from project_guardian.live_action_executor import (  # noqa: E402
    is_live_executor_enabled,
    rollback_harmless_smoke_write,
)
from project_guardian.live_action_passive_smoke_flow import (  # noqa: E402
    register_harmless_smoke_packet_for_approval,
)
from project_guardian.live_action_readiness import evaluate_live_mode_readiness  # noqa: E402
from project_guardian.live_action_smoke_packet import (  # noqa: E402
    HARMLESS_LIVE_SMOKE_ACTION_ID,
    HARMLESS_LIVE_SMOKE_CONTENT,
    HARMLESS_LIVE_SMOKE_RELATIVE_TARGET,
    HARMLESS_LIVE_SMOKE_TARGET_FILENAME,
)

LIMITED_LIVE_PROFILE_NAME = "operator_approved_harmless_smoke_v1"
_AUTONOMY_CONFIG_PATH = _REPO_ROOT / "config" / "autonomy.json"
_TRIPLE_GATE_ENV = {
    "ELYSIA_LIVE_ACTION_APPROVAL_ROUTE_ENABLED": "true",
    "ELYSIA_LIVE_EXECUTOR_ENABLED": "true",
    "ELYSIA_APPROVAL_ROUTE_EXECUTES_SMOKE": "true",
}


def _empty_summary(profile: str = "") -> Dict[str, Any]:
    return {
        "profile": profile,
        "preflight_passed": False,
        "packet_registered": False,
        "decision_recorded": False,
        "executor_called": False,
        "execution_permitted": False,
        "executed": False,
        "target_path": HARMLESS_LIVE_SMOKE_RELATIVE_TARGET,
        "exact_content_verified": False,
        "rollback_executed": False,
        "rollback_verified": False,
        "autonomy_enabled": False,
        "config_autonomy_enabled": False,
        "readiness_blocked": False,
        "workspace_parent": "",
        "workspace_root": "",
        "workspace_rejected": False,
        "safe": False,
        "errors": [],
    }


def _read_config_autonomy_enabled() -> Tuple[bool, Optional[str]]:
    try:
        payload = json.loads(_AUTONOMY_CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001 - fail closed on any read/parse error
        return False, f"cannot read config/autonomy.json: {exc}"
    return bool(payload.get("enabled") is True), None


def _future_expires_at(*, hours: int = 1) -> str:
    return (datetime.now(timezone.utc) + timedelta(hours=hours)).isoformat()


def _smoke_target(workspace: Path) -> Path:
    return workspace / "live_smoke_workspace" / HARMLESS_LIVE_SMOKE_TARGET_FILENAME


def _get_system_temp_root() -> Path:
    return Path(tempfile.gettempdir()).resolve()


def _is_under_path(child: Path, parent: Path) -> bool:
    try:
        child.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def _is_filesystem_root(path: Path) -> bool:
    resolved = path.resolve()
    return resolved.parent == resolved


def _get_external_storage_dir() -> Optional[Path]:
    try:
        from project_guardian.external_storage import get_configured_external_data_dir

        return get_configured_external_data_dir()
    except Exception:
        return None


def validate_custom_workspace_parent(
    workspace_parent: Union[str, Path],
) -> Tuple[Optional[Path], Optional[str]]:
    """Reject unsafe custom workspace parents before any smoke writes."""
    raw = str(workspace_parent).strip()
    path = Path(raw)

    if not path.is_absolute():
        return None, "unsafe workspace: relative path rejected"

    if _is_filesystem_root(path):
        return None, "unsafe workspace: filesystem root rejected"

    try:
        resolved = path.resolve()
    except OSError as exc:
        return None, f"unsafe workspace: cannot resolve path ({exc})"

    system_temp = _get_system_temp_root()
    if not _is_under_path(resolved, system_temp):
        return None, "unsafe workspace: must be inside system temp directory only"

    try:
        real = Path(os.path.realpath(resolved))
    except OSError:
        real = resolved
    if not _is_under_path(real, system_temp):
        return None, "unsafe workspace: symlink escapes system temp directory"

    repo = _REPO_ROOT.resolve()
    if resolved == repo or _is_under_path(resolved, repo):
        return None, "unsafe workspace: repo root/project path rejected"

    cwd = Path.cwd().resolve()
    if resolved == cwd:
        return None, "unsafe workspace: current working directory rejected"

    home = Path.home().resolve()
    if resolved == home:
        return None, "unsafe workspace: user home directory rejected"

    external = _get_external_storage_dir()
    if external is not None and _is_under_path(resolved, external.resolve()):
        return None, "unsafe workspace: external storage path rejected"

    return resolved, None


def _create_workspace(workspace_parent: Optional[Path] = None) -> Path:
    if workspace_parent is not None:
        workspace = workspace_parent / "isolated_smoke_root"
        workspace.mkdir(parents=True, exist_ok=True)
        return workspace
    temp_root = Path(tempfile.mkdtemp(prefix="elysia_limited_live_smoke_"))
    workspace = temp_root / "isolated_smoke_root"
    workspace.mkdir(parents=True, exist_ok=True)
    return workspace


def _apply_triple_gates() -> None:
    os.environ.update(_TRIPLE_GATE_ENV)


def _triple_gates_open() -> bool:
    return (
        is_live_action_approval_route_enabled()
        and is_live_executor_enabled()
        and is_approval_route_executes_smoke_enabled()
    )


def _repo_escape_paths() -> Tuple[Path, ...]:
    return (
        _REPO_ROOT / HARMLESS_LIVE_SMOKE_TARGET_FILENAME,
        _REPO_ROOT / "live_smoke_workspace" / HARMLESS_LIVE_SMOKE_TARGET_FILENAME,
        _REPO_ROOT / HARMLESS_LIVE_SMOKE_RELATIVE_TARGET,
    )


def run_limited_live_smoke(
    *,
    confirm: bool = False,
    profile: str = "",
    workspace_parent: Optional[Union[str, Path]] = None,
) -> Tuple[Dict[str, Any], int]:
    """Run the limited-live smoke cycle. Returns (summary_dict, exit_code)."""
    summary = _empty_summary(profile=profile)
    errors: List[str] = summary["errors"]

    if not confirm:
        errors.append("missing --confirm-limited-live-smoke")
        return summary, 2

    if profile != LIMITED_LIVE_PROFILE_NAME:
        errors.append(
            f"profile must be {LIMITED_LIVE_PROFILE_NAME!r}; got {profile!r}"
        )
        return summary, 2

    config_enabled, config_error = _read_config_autonomy_enabled()
    if config_error:
        errors.append(config_error)
        return summary, 2
    summary["config_autonomy_enabled"] = config_enabled
    if config_enabled:
        errors.append("config/autonomy.json enabled=true; refusing limited-live smoke")
        return summary, 2

    readiness = evaluate_live_mode_readiness()
    summary["readiness_blocked"] = readiness.status.value == "BLOCKED"
    if readiness.ready_for_limited_live_mode:
        errors.append("readiness unexpectedly grants limited live mode")
        return summary, 2

    _apply_triple_gates()
    if not _triple_gates_open():
        errors.append("triple execution gates are not open after preflight")
        return summary, 2

    validated_parent: Optional[Path] = None
    if workspace_parent is not None:
        summary["workspace_parent"] = str(workspace_parent)
        validated_parent, workspace_error = validate_custom_workspace_parent(
            workspace_parent
        )
        if workspace_error:
            summary["workspace_rejected"] = True
            errors.append(workspace_error)
            return summary, 2

    summary["preflight_passed"] = True
    summary["autonomy_enabled"] = False

    for escape_path in _repo_escape_paths():
        if escape_path.exists():
            errors.append(f"repo escape path already exists before run: {escape_path}")
            return summary, 1

    workspace = _create_workspace(validated_parent)
    summary["workspace_root"] = str(workspace.resolve())
    target = _smoke_target(workspace)
    audit_dir = workspace / "_limited_live_smoke_audit"
    audit_dir.mkdir(parents=True, exist_ok=True)
    store = LiveActionApprovalRouteStore(audit_path=audit_dir / "decisions.jsonl")

    try:
        smoke = register_harmless_smoke_packet_for_approval(
            store,
            workspace,
            repo_root=_REPO_ROOT,
            expires_at=_future_expires_at(),
            dry_run_trace_id="limited-live-smoke-command",
        )
        summary["packet_registered"] = True
        packet_id = smoke.packet.packet_id

        detail, detail_code = get_approval_packet_detail(store, packet_id)
        if detail_code != 200:
            errors.append(f"packet inspect failed with status {detail_code}")
            return summary, 1
        if detail.get("action_id") != HARMLESS_LIVE_SMOKE_ACTION_ID:
            errors.append("packet action_id is not harmless_live_smoke_v1")
            return summary, 1

        decision_body, decision_code = record_operator_decision_for_packet(
            store,
            packet_id,
            {
                "decision": "APPROVE",
                "operator_id": "limited-live-smoke-operator",
                "reason": "operator confirmed limited-live harmless smoke",
                "approved_scope": f"single-file write {HARMLESS_LIVE_SMOKE_RELATIVE_TARGET} only",
                "packet_content_hash": compute_packet_content_hash(smoke.packet),
            },
            route_source="limited_live_smoke_command",
        )
        if decision_code != 200:
            errors.append(f"operator decision failed with status {decision_code}")
            return summary, 1

        summary["decision_recorded"] = bool(decision_body.get("decision_recorded"))
        summary["executor_called"] = bool(decision_body.get("executor_called"))
        summary["execution_permitted"] = bool(decision_body.get("execution_permitted"))
        summary["executed"] = bool(decision_body.get("executed"))

        if not summary["executor_called"]:
            errors.append("executor was not called after APPROVE")
            return summary, 1
        if not summary["execution_permitted"] or not summary["executed"]:
            errors.append("execution was not permitted or did not complete")
            return summary, 1
        if not target.is_file():
            errors.append("smoke target file missing after execution")
            return summary, 1
        if target.read_bytes() != HARMLESS_LIVE_SMOKE_CONTENT:
            errors.append("smoke target content mismatch after execution")
            return summary, 1
        summary["exact_content_verified"] = True

        rollback = rollback_harmless_smoke_write(
            workspace_root=str(workspace),
            target_path=HARMLESS_LIVE_SMOKE_RELATIVE_TARGET,
            rollback_plan_id=HARMLESS_LIVE_SMOKE_ACTION_ID,
            repo_root=str(_REPO_ROOT),
        )
        summary["rollback_executed"] = rollback.status == "ROLLBACK_SUCCEEDED"
        if not summary["rollback_executed"]:
            errors.append(f"rollback failed: {rollback.detail or rollback.failure_code}")
            return summary, 1
        if target.exists():
            errors.append("smoke target still exists after rollback")
            return summary, 1
        summary["rollback_verified"] = True

        for escape_path in _repo_escape_paths():
            if escape_path.exists():
                errors.append(f"repo escape path created during run: {escape_path}")
                return summary, 1

        summary["safe"] = True
        return summary, 0
    except Exception as exc:  # noqa: BLE001 - operator command must surface failure
        errors.append(str(exc))
        if target.exists():
            try:
                rollback_harmless_smoke_write(
                    workspace_root=str(workspace),
                    target_path=HARMLESS_LIVE_SMOKE_RELATIVE_TARGET,
                    rollback_plan_id=HARMLESS_LIVE_SMOKE_ACTION_ID,
                    repo_root=str(_REPO_ROOT),
                )
            except Exception:
                pass
        return summary, 1


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run operator-approved limited-live harmless smoke in an isolated temp workspace."
        )
    )
    parser.add_argument(
        "--profile",
        required=True,
        help=f"Limited live profile name (required: {LIMITED_LIVE_PROFILE_NAME})",
    )
    parser.add_argument(
        "--confirm-limited-live-smoke",
        action="store_true",
        help="Explicit operator confirmation required to run",
    )
    parser.add_argument(
        "--workspace",
        default="",
        help=(
            "Optional parent directory inside the OS system temp directory only "
            "(unsafe paths are rejected before execution)"
        ),
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print machine-readable JSON summary to stdout",
    )
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    args = _build_arg_parser().parse_args(argv)
    workspace_parent = args.workspace.strip() or None
    summary, exit_code = run_limited_live_smoke(
        confirm=bool(args.confirm_limited_live_smoke),
        profile=str(args.profile),
        workspace_parent=workspace_parent,
    )
    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        print("Limited live smoke summary")
        print("=" * 40)
        for key, value in summary.items():
            print(f"{key}: {value}")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
