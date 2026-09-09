"""Shared entrypoint helpers for Elysia launchers."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Mapping

TRUTHY_ENV_VALUES = frozenset({"1", "true", "yes", "on"})


def env_flag_enabled(name: str, env: Mapping[str, str] | None = None) -> bool:
    """Return True when an env var is set to a supported truthy value."""
    source = os.environ if env is None else env
    return str(source.get(name, "")).strip().lower() in TRUTHY_ENV_VALUES


@dataclass(frozen=True)
class BackendLaunchDecision:
    """Pure description of how the launcher should proceed."""

    mode: str
    reason: str

    @property
    def should_attach_only(self) -> bool:
        return self.mode == "attach_only"

    @property
    def should_start_backend(self) -> bool:
        return self.mode == "start_backend"


def select_backend_launch_mode(*, force_full_backend: bool, backend_alive: bool) -> BackendLaunchDecision:
    """Choose whether to attach to an existing backend or boot a new one."""
    if force_full_backend:
        return BackendLaunchDecision(mode="start_backend", reason="force_full_backend")
    if backend_alive:
        return BackendLaunchDecision(mode="attach_only", reason="backend_alive")
    return BackendLaunchDecision(mode="start_backend", reason="no_existing_backend")


def render_attach_only_banner(status_url: str) -> str:
    """Build the attach-only console message shown by the legacy launcher."""
    lines = [
        "",
        "=" * 70,
        "ATTACH-ONLY MODE (/status already returned usable JSON)",
        "=" * 70,
        "Something on this machine already answered GET /status like Elysia. "
        "Skipping GuardianCore / full backend boot.",
        f"Status URL: {status_url}/status",
        "If that is NOT Elysia, free the port or set ELYSIA_STATUS_PORT. "
        "To force full boot anyway: set ELYSIA_FORCE_FULL_BACKEND=1 "
        "(see Start_Elysia_Backend.cmd).",
        "=" * 70,
        "",
    ]
    return "\n".join(lines)
