"""Planted FIFO metadata.json must not block unified proposal open paths.

Uses a disposable proposals directory, fictional records, and no live providers.
Named-pipe creation requires os.mkfifo; Windows execution is not claimed here.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

import pytest

from elysia.config import RuntimeConfig
from elysia.core.proposal_system import (
    ProposalSystem,
    ProposalValidator,
    _is_openable_metadata,
)
from elysia.runtime import ElysiaRuntime

pytestmark = pytest.mark.skipif(
    not hasattr(os, "mkfifo"), reason="named pipes are unavailable on this platform"
)

_TIMEOUT = 1.0


def _write_fictional_proposal(root: Path, proposal_id: str, status: str = "research") -> Path:
    proposal_dir = root / proposal_id
    proposal_dir.mkdir(parents=True)
    metadata = {
        "proposal_id": proposal_id,
        "title": "Fictional in-root proposal",
        "status": status,
        "created_by": "probe",
        "created_at": "2026-11-09T00:00:00Z",
        "history": [],
    }
    (proposal_dir / "metadata.json").write_text(
        json.dumps(metadata, indent=2), encoding="utf-8"
    )
    return proposal_dir


def _plant_fifo_proposal(root: Path, proposal_id: str) -> Path:
    proposal_dir = root / proposal_id
    proposal_dir.mkdir(parents=True)
    os.mkfifo(proposal_dir / "metadata.json")
    return proposal_dir


def _runtime(tmp_path: Path) -> ElysiaRuntime:
    cfg = RuntimeConfig(
        mode="core",
        env="dev",
        proposals_root=tmp_path / "proposals",
        enable_api=False,
        enable_webscout=False,
        log_level="ERROR",
    )
    return ElysiaRuntime(cfg)


def _wait_for_heartbeat(runtime: ElysiaRuntime, timeout: float = 2.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        events = [
            evt
            for evt in runtime.event_bus.get_recent_events(limit=50)
            if evt.get("source") == "runtime" and evt.get("type") == "heartbeat"
        ]
        if events:
            return events[0]
        time.sleep(0.01)
    return None


def _bounded(fn):
    started = time.perf_counter()
    result = fn()
    elapsed = time.perf_counter() - started
    assert elapsed < _TIMEOUT, f"open path blocked for {elapsed:.3f}s"
    return result


def test_helper_rejects_fifo_and_accepts_regular(tmp_path):
    regular = _write_fictional_proposal(tmp_path, "fictional-regular-20261109")
    fifo_dir = _plant_fifo_proposal(tmp_path, "fictional-fifo-20261109")
    fifo_meta = fifo_dir / "metadata.json"

    assert fifo_meta.exists() is True
    assert fifo_meta.is_symlink() is False
    assert _is_openable_metadata(fifo_meta) is False
    assert _is_openable_metadata(regular / "metadata.json") is True
    assert _is_openable_metadata(tmp_path / "missing" / "metadata.json") is False


def test_list_and_get_omit_fifo_and_keep_regular(tmp_path):
    root = tmp_path / "proposals"
    root.mkdir()
    _write_fictional_proposal(root, "fictional-regular-20261109")
    fifo_dir = _plant_fifo_proposal(root, "fictional-fifo-20261109")
    fifo_before = (fifo_dir / "metadata.json").exists()
    ps = ProposalSystem(proposals_root=root, enable_watcher=False)
    try:
        listed = _bounded(ps.list_proposals)
        fifo_got = _bounded(lambda: ps.get_proposal("fictional-fifo-20261109"))
        regular_got = _bounded(lambda: ps.get_proposal("fictional-regular-20261109"))
        filtered = _bounded(lambda: ps.list_proposals(status_filter="research"))

        assert [item["proposal_id"] for item in listed] == ["fictional-regular-20261109"]
        assert fifo_got is None
        assert regular_got is not None
        assert regular_got["status"] == "research"
        assert [item["proposal_id"] for item in filtered] == ["fictional-regular-20261109"]
        assert (fifo_dir / "metadata.json").exists() is fifo_before
    finally:
        ps.shutdown()


def test_validator_rejects_fifo_without_opening(tmp_path):
    root = tmp_path / "proposals"
    root.mkdir()
    regular = _write_fictional_proposal(root, "fictional-regular-20261109")
    fifo_dir = _plant_fifo_proposal(root, "fictional-fifo-20261109")
    validator = ProposalValidator(root)

    fifo_ok, fifo_error = _bounded(lambda: validator.validate_proposal(fifo_dir))
    regular_ok, regular_error = _bounded(lambda: validator.validate_proposal(regular))

    assert fifo_ok is False
    assert "regular file" in (fifo_error or "")
    assert regular_ok is True
    assert regular_error is None


def test_authorized_transition_skips_fifo_and_updates_regular(tmp_path):
    root = tmp_path / "proposals"
    root.mkdir()
    _write_fictional_proposal(root, "fictional-regular-20261109")
    fifo_dir = _plant_fifo_proposal(root, "fictional-fifo-20261109")
    fifo_stat_before = os.lstat(fifo_dir / "metadata.json")
    ps = ProposalSystem(proposals_root=root, enable_watcher=False)
    try:
        fifo_ok, fifo_error = _bounded(
            lambda: ps.transition_status(
                "fictional-fifo-20261109", "design", actor="fictional-actor"
            )
        )
        regular_ok, regular_error = _bounded(
            lambda: ps.transition_status(
                "fictional-regular-20261109", "design", actor="fictional-actor"
            )
        )
        stored = ps.get_proposal("fictional-regular-20261109")
        fifo_stat_after = os.lstat(fifo_dir / "metadata.json")

        assert fifo_ok is False
        assert fifo_error == "Proposal not found"
        assert regular_ok is True
        assert regular_error is None
        assert stored is not None
        assert stored["status"] == "design"
        assert stored["last_updated_by"] == "fictional-actor"
        assert fifo_stat_after.st_ino == fifo_stat_before.st_ino
        assert fifo_stat_after.st_mode == fifo_stat_before.st_mode
    finally:
        ps.shutdown()


def test_invalid_transition_on_regular_leaves_disk_unchanged(tmp_path):
    root = tmp_path / "proposals"
    root.mkdir()
    _write_fictional_proposal(root, "fictional-invalid-20261109", "research")
    _plant_fifo_proposal(root, "fictional-fifo-20261109")
    before = (root / "fictional-invalid-20261109" / "metadata.json").read_text(
        encoding="utf-8"
    )
    ps = ProposalSystem(proposals_root=root, enable_watcher=False)
    try:
        ok, error = _bounded(
            lambda: ps.transition_status(
                "fictional-invalid-20261109", "approved", actor="fictional-actor"
            )
        )
        stored = ps.get_proposal("fictional-invalid-20261109")
        after = (root / "fictional-invalid-20261109" / "metadata.json").read_text(
            encoding="utf-8"
        )

        assert ok is False
        assert "Invalid transition" in (error or "")
        assert stored is not None
        assert stored["status"] == "research"
        assert after == before
    finally:
        ps.shutdown()


def test_runtime_start_heartbeat_and_stop_with_fifo_plant(tmp_path):
    root = tmp_path / "proposals"
    root.mkdir()
    _write_fictional_proposal(root, "fictional-regular-20261109")
    _plant_fifo_proposal(root, "fictional-fifo-20261109")
    runtime = _runtime(tmp_path)
    runtime.start()
    try:
        first = _wait_for_heartbeat(runtime)
        listed = _bounded(runtime.proposal_system.list_proposals)
        ok, error = runtime.proposal_system.transition_status(
            "fictional-regular-20261109", "design", actor="fictional-actor"
        )
        stored = runtime.proposal_system.get_proposal("fictional-regular-20261109")
        status = runtime.get_status()

        assert first is not None
        assert [item["proposal_id"] for item in listed] == ["fictional-regular-20261109"]
        assert first["payload"]["proposals"] == 1
        assert ok is True
        assert error is None
        assert stored is not None
        assert stored["status"] == "design"
        assert status["running"] is True
    finally:
        runtime.stop()

    assert runtime.get_status()["running"] is False
    assert runtime._heartbeat_thread is not None
    assert not runtime._heartbeat_thread.is_alive()
