"""Isolation helpers for ELY-153 security regression tests.

Intercepts configuration/credential persistence and external side effects.
Does not authorize, start autonomy, open network listeners, or contact providers.
"""

from __future__ import annotations

import builtins
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any, Callable, List, Optional, Sequence, Tuple

# Synthetic / fictional only — never real credentials.
SYNTHETIC_TOKEN = "synthetic-token-do-not-use"
UNTRUSTED_ORIGIN = "https://untrusted.example.invalid"
TARGET_SHA = "821b9f4459eb888ad79d7845a8826a9f6cb94e3e"

# Dashboard routes that accept social/provider credential material.
CREDENTIAL_ROUTES: Tuple[Tuple[str, dict], ...] = (
    ("/api/learning/link-facebook", {"token": SYNTHETIC_TOKEN}),
    ("/api/learning/link-twitter", {"token": SYNTHETIC_TOKEN}),
)


@dataclass
class SideEffectRecorder:
    """Records intercepted privileged side effects; never performs them."""

    config_writes: List[Tuple[str, str]] = field(default_factory=list)
    credential_writes: List[Tuple[str, str]] = field(default_factory=list)
    open_writes: List[Tuple[str, str]] = field(default_factory=list)
    mkdir_calls: List[str] = field(default_factory=list)
    env_mutations: List[Tuple[str, Optional[str]]] = field(default_factory=list)
    external_connect_attempts: List[str] = field(default_factory=list)
    privileged_socket_handler_runs: int = 0
    worker_starts: int = 0
    provider_starts: int = 0

    @property
    def persistence_count(self) -> int:
        return len(self.config_writes) + len(self.credential_writes) + len(self.open_writes)

    def fail_if_persistence(self, message: str = "persistent configuration/credential write intercepted") -> None:
        if self.persistence_count:
            raise AssertionError(
                f"{message}: count={self.persistence_count} "
                f"config={self.config_writes!r} open={self.open_writes!r} cred={self.credential_writes!r}"
            )


@dataclass
class RecordingFakeRegistry:
    """Fake ModuleRegistry: records submissions; never executes tasks."""

    submissions: List[dict] = field(default_factory=list)
    queue: List[dict] = field(default_factory=list)
    execution_callbacks: List[Callable[..., Any]] = field(default_factory=list)
    route_task_calls: int = 0

    async def route_task(self, task: dict) -> dict:
        self.route_task_calls += 1
        self.submissions.append(dict(task))
        self.queue.append(dict(task))
        for cb in list(self.execution_callbacks):
            cb(task)
        # Intentionally do not execute real work.
        return {"success": True, "task_id": "synthetic-not-executed", "blocked": True}

    @property
    def submission_count(self) -> int:
        return len(self.submissions)


class IsolationGuard:
    """Context manager that intercepts writes / env changes before they execute."""

    def __init__(self, recorder: Optional[SideEffectRecorder] = None):
        self.recorder = recorder or SideEffectRecorder()
        self._orig_write_text = Path.write_text
        self._orig_open = builtins.open
        self._orig_mkdir = Path.mkdir
        self._orig_environ_setitem = os.environ.__setitem__
        self._orig_environ_pop = os.environ.pop
        self._orig_putenv = os.putenv
        self._orig_unsetenv = getattr(os, "unsetenv", None)

    def __enter__(self) -> SideEffectRecorder:
        recorder = self.recorder

        def write_text(path_self: Path, data: Any, *args: Any, **kwargs: Any) -> None:
            text = data if isinstance(data, str) else str(data)
            target = str(path_self)
            entry = (target, text)
            if "auto_learning" in target or "token" in text.lower() or SYNTHETIC_TOKEN in text:
                recorder.credential_writes.append(entry)
            else:
                recorder.config_writes.append(entry)
            # Do not perform the write.
            return None

        def tracking_open(file, mode="r", *args, **kwargs):
            mode_s = mode if isinstance(mode, str) else str(mode)
            if any(flag in mode_s for flag in ("w", "a", "x", "+")):
                recorder.open_writes.append((str(file), mode_s))
                # Block write; raise so callers cannot dump secrets via file handles.
                raise PermissionError(f"ELY-153 isolation blocked write open: {file!s} mode={mode_s}")
            return self._orig_open(file, mode, *args, **kwargs)

        def mkdir(path_self: Path, *args: Any, **kwargs: Any) -> None:
            recorder.mkdir_calls.append(str(path_self))
            # Allow in-memory test tmp dirs if explicitly under /tmp/ely153-*, else block config dirs.
            target = str(path_self)
            if target.endswith("config") or target.endswith(os.path.join("", "config")) or "/config" in target.replace("\\", "/"):
                return None  # pretend success without creating
            return self._orig_mkdir(path_self, *args, **kwargs)

        def env_setitem(key, value):
            recorder.env_mutations.append((str(key), str(value)))
            raise PermissionError(f"ELY-153 isolation blocked environ set: {key}")

        def env_pop(key, *args, **kwargs):
            recorder.env_mutations.append((str(key), None))
            raise PermissionError(f"ELY-153 isolation blocked environ pop: {key}")

        def putenv(key, value):
            recorder.env_mutations.append((str(key), str(value)))
            raise PermissionError(f"ELY-153 isolation blocked putenv: {key}")

        Path.write_text = write_text  # type: ignore[method-assign]
        builtins.open = tracking_open  # type: ignore[assignment]
        Path.mkdir = mkdir  # type: ignore[method-assign]
        os.environ.__setitem__ = env_setitem  # type: ignore[method-assign]
        os.environ.pop = env_pop  # type: ignore[method-assign]
        os.putenv = putenv  # type: ignore[assignment]
        if self._orig_unsetenv is not None:

            def unsetenv(key):
                recorder.env_mutations.append((str(key), None))
                raise PermissionError(f"ELY-153 isolation blocked unsetenv: {key}")

            os.unsetenv = unsetenv  # type: ignore[assignment]

        return recorder

    def __exit__(self, exc_type, exc, tb) -> None:
        Path.write_text = self._orig_write_text  # type: ignore[method-assign]
        builtins.open = self._orig_open  # type: ignore[assignment]
        Path.mkdir = self._orig_mkdir  # type: ignore[method-assign]
        os.environ.__setitem__ = self._orig_environ_setitem  # type: ignore[method-assign]
        os.environ.pop = self._orig_environ_pop  # type: ignore[method-assign]
        os.putenv = self._orig_putenv  # type: ignore[assignment]
        if self._orig_unsetenv is not None:
            os.unsetenv = self._orig_unsetenv  # type: ignore[assignment]


def install_fake_auto_learning(monkeypatch=None) -> ModuleType:
    """Provide a no-I/O auto_learning stub so credential routes can be exercised safely."""
    import sys

    fake = ModuleType("project_guardian.auto_learning")

    def load_learning_config():
        return {
            "facebook_access_token": "",
            "twitter_bearer_token": "",
            "use_headless_browser": False,
        }

    fake.load_learning_config = load_learning_config  # type: ignore[attr-defined]
    sys.modules["project_guardian.auto_learning"] = fake
    if monkeypatch is not None:
        monkeypatch.setitem(sys.modules, "project_guardian.auto_learning", fake)
    return fake


def build_isolated_panel(registry: Optional[RecordingFakeRegistry] = None):
    """Load UIControlPanel via the isolated dashboard verification loader."""
    from tests.dashboard_panel_loader import UIControlPanel

    if registry is None:
        orchestrator = None
    else:
        orchestrator = SimpleNamespace(
            module_registry=registry,
            _load_autonomy_config=lambda: {
                "enabled": False,
                "allowed_actions": [],
                "max_actions_per_hour": 0,
            },
            _last_autonomy_result=None,
            run_autonomous_cycle=lambda: (_ for _ in ()).throw(
                AssertionError("autonomy worker/provider must not start")
            ),
        )
    panel = UIControlPanel(orchestrator=orchestrator, host="127.0.0.1", port=5999)
    return panel


def assert_denied(status_code: int) -> None:
    assert status_code in (401, 403), (
        f"expected unauthenticated denial HTTP 401/403, got {status_code}"
    )


_SCRIPT_SRC_RE = re.compile(
    r"""<script\b[^>]*\bsrc\s*=\s*["']([^"']+)["']""",
    re.IGNORECASE,
)
_IMPORT_RE = re.compile(
    r"""\bimport\s*\(\s*["'](https?://[^"']+)["']\s*\)""",
    re.IGNORECASE,
)


def extract_script_sources(html: str) -> List[str]:
    return _SCRIPT_SRC_RE.findall(html)


def extract_remote_dynamic_imports(html: str) -> List[str]:
    return _IMPORT_RE.findall(html)


def is_remote_url(url: str) -> bool:
    u = (url or "").strip().lower()
    return u.startswith("http://") or u.startswith("https://") or u.startswith("//")
