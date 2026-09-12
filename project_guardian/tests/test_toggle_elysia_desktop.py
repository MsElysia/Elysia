"""toggle_elysia_desktop.py lives at repo root; tests cover --stop-only and argv parsing."""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import toggle_elysia_desktop as t  # noqa: E402


def test_stop_only_when_backend_down_returns_zero() -> None:
    with patch.object(t, "probe_backend_alive", return_value=False):
        assert t.main(["--stop-only"]) == 0


def test_stop_only_when_backend_up_shutdown_ok() -> None:
    with patch.object(t, "probe_backend_alive", return_value=True), patch.object(
        t, "_post_shutdown", return_value=(True, "ok")
    ):
        assert t.main(["--stop-only"]) == 0


def test_default_when_backend_down_starts_unified() -> None:
    with patch.object(t, "probe_backend_alive", return_value=False), patch(
        "toggle_elysia_desktop.subprocess.Popen"
    ) as popen_mock, patch("toggle_elysia_desktop.os.name", "nt"):
        assert t.main([]) == 0
    popen_mock.assert_called_once()


def test_main_none_uses_argv_tail(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "argv", ["toggle_elysia_desktop.py", "--stop-only"])
    with patch.object(t, "probe_backend_alive", return_value=False):
        assert t.main(None) == 0
