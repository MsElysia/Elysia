"""get_status must not count planted FIFO metadata.json folders as in-root.

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
from elysia.core.proposal_system import ProposalSystem
from elysia.runtime import ElysiaRuntime, _is_countable_metadata

pytestmark = pytest.mark.skipif(
    not hasattr(os, "mkfifo"), reason="named pipes are unavailable on this platform"
)

_TIMEOUT = 1.0


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


def _write_fictional_proposal(root: Path, proposal_id: str, status: str = "research") -> Path:
    proposal_dir = root / proposal_id
    proposal_dir.mkdir(parents=True)
    metadata = {
        "proposal_id": proposal_id,
        "title": "Fictional in-root proposal",
        "status": status,
        "created_by": "probe",
        "created_at": "2026-11-11T00:00:00Z",
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


def _attach_proposals(runtime: ElysiaRuntime, root: Path) -> ProposalSystem:
    runtime.proposal_system = ProposalSystem(proposals_root=root, enable_watcher=False)
    return runtime.proposal_system


def test_helper_rejects_fifo_and_accepts_regular(tmp_path):
    regular = _write_fictional_proposal(tmp_path, "fictional-regular-20261111")
    fifo_dir = _plant_fifo_proposal(tmp_path, "fictional-fifo-20261111")
    fifo_meta = fifo_dir / "metadata.json"

    assert fifo_meta.exists() is True
    assert fifo_meta.is_symlink() is False
    assert fifo_meta.is_fifo() is True
    assert _is_countable_metadata(fifo_meta) is False
    assert _is_countable_metadata(regular / "metadata.json") is True
    assert _is_countable_metadata(tmp_path / "missing" / "metadata.json") is False


def test_get_status_omits_fifo_and_keeps_regular(tmp_path):
    root = tmp_path / "proposals"
    root.mkdir()
    _write_fictional_proposal(root, "fictional-regular-20261111")
    fifo_dir = _plant_fifo_proposal(root, "fictional-fifo-20261111")
    fifo_before = os.lstat(fifo_dir / "metadata.json")
    runtime = _runtime(tmp_path)
    ps = _attach_proposals(runtime, root)
    try:
        started = time.perf_counter()
        status = runtime.get_status()
        elapsed = time.perf_counter() - started

        assert elapsed < _TIMEOUT, f"get_status blocked for {elapsed:.3f}s"
        assert status["proposal_count"] == 1
        assert status["running"] is False
        fifo_after = os.lstat(fifo_dir / "metadata.json")
        assert fifo_after.st_ino == fifo_before.st_ino
        assert fifo_after.st_mode == fifo_before.st_mode
    finally:
        ps.shutdown()


def test_started_runtime_skips_fifo_planted_after_start(tmp_path):
    root = tmp_path / "proposals"
    root.mkdir()
    _write_fictional_proposal(root, "fictional-regular-20261111")
    runtime = _runtime(tmp_path)
    runtime.start()
    fifo_dir = None
    try:
        assert runtime.get_status()["running"] is True
        assert runtime.get_status()["proposal_count"] == 1

        fifo_dir = _plant_fifo_proposal(root, "fictional-fifo-20261111")
        started = time.perf_counter()
        status = runtime.get_status()
        elapsed = time.perf_counter() - started

        assert elapsed < _TIMEOUT, f"get_status blocked for {elapsed:.3f}s"
        assert status["running"] is True
        assert status["proposal_count"] == 1
        assert (fifo_dir / "metadata.json").exists() is True
        assert (fifo_dir / "metadata.json").is_file() is False
    finally:
        runtime.stop()
        assert runtime.get_status()["running"] is False
        if runtime._heartbeat_thread is not None:
            assert runtime._heartbeat_thread.is_alive() is False


def test_started_runtime_still_completes_authorized_status_transition(tmp_path):
    proposal_id = "fictional-status-transition-20261111"
    root = tmp_path / "proposals"
    root.mkdir()
    _write_fictional_proposal(root, proposal_id)
    runtime = _runtime(tmp_path)
    runtime.start()
    fifo_dir = None
    try:
        ok, error = runtime.proposal_system.transition_status(
            proposal_id, "design", actor="fictional-actor"
        )
        fifo_dir = _plant_fifo_proposal(root, "fictional-fifo-20261111")
        stored = runtime.proposal_system.get_proposal(proposal_id)
        status = runtime.get_status()

        assert ok is True
        assert error is None
        assert stored is not None
        assert stored["status"] == "design"
        assert stored["last_updated_by"] == "fictional-actor"
        assert status["running"] is True
        assert status["proposal_count"] == 1
        assert (fifo_dir / "metadata.json").is_fifo() is True
    finally:
        runtime.stop()


def test_invalid_transition_on_running_runtime_leaves_disk_unchanged(tmp_path):
    proposal_id = "fictional-status-invalid-20261111"
    _write_fictional_proposal(tmp_path / "proposals", proposal_id, "research")
    before = (tmp_path / "proposals" / proposal_id / "metadata.json").read_text(
        encoding="utf-8"
    )
    runtime = _runtime(tmp_path)
    runtime.start()
    try:
        ok, error = runtime.proposal_system.transition_status(
            proposal_id, "approved", actor="fictional-actor"
        )
        stored = runtime.proposal_system.get_proposal(proposal_id)
        after = (tmp_path / "proposals" / proposal_id / "metadata.json").read_text(
            encoding="utf-8"
        )

        assert runtime.get_status()["running"] is True
        assert runtime.get_status()["proposal_count"] == 1
        assert ok is False
        assert "Invalid transition" in (error or "")
        assert stored is not None
        assert stored["status"] == "research"
        assert after == before
    finally:
        runtime.stop()


def test_empty_proposals_root_reports_zero(tmp_path):
    (tmp_path / "proposals").mkdir()
    runtime = _runtime(tmp_path)
    runtime.start()
    try:
        status = runtime.get_status()
        assert status["running"] is True
        assert status["proposal_count"] == 0
    finally:
        runtime.stop()
