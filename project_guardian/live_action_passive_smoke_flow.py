"""Passive harmless smoke approval flow glue.

Registers smoke packets with the approval route store for operator review only.
Does not execute smoke, call an executor, or write the target file.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional, Union

from project_guardian.live_action_approval_route import LiveActionApprovalRouteStore
from project_guardian.live_action_smoke_packet import (
    HarmlessSmokePacketResult,
    build_harmless_smoke_approval_packet,
)

_DEFAULT_DRY_RUN_TRACE_SUMMARY: Dict[str, Any] = {
    "outcome": "dry_run_blocked_not_executed",
    "blocked": True,
    "executed": False,
    "safety_verdict": "SAFE",
}


def register_harmless_smoke_packet_for_approval(
    store: LiveActionApprovalRouteStore,
    workspace_root: Union[str, Path],
    *,
    repo_root: Optional[Union[str, Path]] = None,
    expires_at: str,
    dry_run_trace_id: str = "",
    dry_run_trace_summary: Optional[Dict[str, Any]] = None,
) -> HarmlessSmokePacketResult:
    """Build smoke packet and register with passive approval store. No execution."""
    result = build_harmless_smoke_approval_packet(
        workspace_root,
        repo_root=repo_root,
    )
    store.register_packet(
        result.packet,
        expires_at=expires_at,
        dry_run_trace_id=dry_run_trace_id,
        dry_run_trace_summary=dict(dry_run_trace_summary or _DEFAULT_DRY_RUN_TRACE_SUMMARY),
    )
    return result
