# project_guardian/tests/test_memory_demo_workspace.py

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from project_guardian.local_ingestion.memory_diagnostics import (
    HAS_CONTEXT_BUNDLE,
    MemoryDiagnosticsError,
    create_memory_demo_workspace,
    run_memory_doctor,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_demo_workspace_dry_run_does_not_write(tmp_path):
    dest = tmp_path / "demo"

    report = create_memory_demo_workspace(dest_dir=dest)

    assert report.verdict == "DRY_RUN"
    assert report.applied is False
    assert report.pipeline_run is False
    assert report.files_written == []
    assert len(report.planned_files) == 4
    assert not dest.exists()


def test_demo_workspace_apply_writes_only_under_dest(tmp_path):
    dest = tmp_path / "demo"

    report = create_memory_demo_workspace(dest_dir=dest, apply=True)

    assert report.verdict == "PASS"
    assert report.applied is True
    assert report.pipeline_run is False
    assert len(report.files_written) == 4
    for raw in report.files_written:
        path = Path(raw)
        assert path.is_file()
        path.relative_to(dest.resolve())
    assert (dest / "README.md").is_file()
    assert (dest / "sample_inputs" / "transcription" / "demo_transcript.txt").is_file()
    assert (dest / "sample_inputs" / "chatgpt" / "conversations.json").is_file()
    assert (dest / "sample_inputs" / "email" / "demo_email.eml").is_file()


def test_run_pipeline_requires_apply(tmp_path):
    with pytest.raises(MemoryDiagnosticsError, match="requires --apply"):
        create_memory_demo_workspace(dest_dir=tmp_path / "demo", run_pipeline=True)


def test_demo_workspace_rejects_repo_root_destination():
    with pytest.raises(MemoryDiagnosticsError, match="repository root"):
        create_memory_demo_workspace(dest_dir=REPO_ROOT)


def test_demo_pipeline_creates_review_export_store_search_and_context(tmp_path):
    dest = tmp_path / "demo"

    report = create_memory_demo_workspace(dest_dir=dest, apply=True, run_pipeline=True)
    doctor = run_memory_doctor(dest)

    assert report.verdict == "PASS"
    assert report.pipeline_run is True
    assert report.candidates_created >= 3
    assert report.approvals_created >= 3
    assert report.approved_export_created
    assert report.approved_memory_store_created
    assert report.approved_memory_count >= 3
    assert report.search_result_count >= 1
    assert report.context_bundle_created
    assert doctor.verdict == HAS_CONTEXT_BUNDLE
    assert report.model_called is False
    assert report.embeddings_used is False
    assert report.live_memory_written is False
    assert report.autonomy_enabled is False


def test_demo_workspace_cli_apply_run_pipeline(tmp_path):
    dest = tmp_path / "demo"
    result = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts" / "create_memory_demo_workspace.py"),
            "--dest-dir",
            str(dest),
            "--apply",
            "--run-pipeline",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(result.stdout)
    assert payload["verdict"] == "PASS"
    assert payload["pipeline_run"] is True
    assert payload["candidates_created"] >= 3
    assert payload["model_called"] is False
    assert payload["embeddings_used"] is False
    assert payload["live_memory_written"] is False
