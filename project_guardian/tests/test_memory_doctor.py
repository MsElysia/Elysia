# project_guardian/tests/test_memory_doctor.py

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from project_guardian.local_ingestion.memory_candidate_review import (
    reject_candidate,
    resolve_review_paths,
)
from project_guardian.local_ingestion.memory_candidates import (
    MEMORY_CANDIDATES_SUBDIR,
    REVIEW_QUEUE_FILENAME,
)
from project_guardian.local_ingestion.memory_diagnostics import (
    EMPTY_WORKSPACE,
    HAS_CONTEXT_BUNDLE,
    HAS_PENDING_REVIEW,
    NEEDS_ATTENTION,
    READY_FOR_IMPORT,
    create_memory_demo_workspace,
    run_memory_doctor,
)
from project_guardian.local_ingestion.unified_memory_import import (
    SOURCE_TYPE_TRANSCRIPTION,
    unified_apply_memory_import,
    unified_preview_memory_import,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_missing_workspace_reports_empty_without_writing(tmp_path):
    dest = tmp_path / "missing"
    report = run_memory_doctor(dest)
    assert report.verdict == EMPTY_WORKSPACE
    assert report.exists is False
    assert report.pending_candidates_count == 0
    assert report.model_called is False
    assert not dest.exists()


def test_demo_apply_without_pipeline_is_ready_for_import(tmp_path):
    dest = tmp_path / "demo"
    create_memory_demo_workspace(dest_dir=dest, apply=True)
    report = run_memory_doctor(dest)
    assert report.verdict == READY_FOR_IMPORT
    assert report.import_ready_file_count == 3
    assert report.pending_candidates_count == 0


def test_staged_candidates_report_pending_review(tmp_path):
    dest = tmp_path / "workspace"
    source = tmp_path / "source.txt"
    source.write_text("Customer asked for a drywall quote.", encoding="utf-8")
    preview = unified_preview_memory_import(
        dest_dir=dest,
        input_paths=[source],
        source_type=SOURCE_TYPE_TRANSCRIPTION,
    )
    unified_apply_memory_import(session_json=Path(preview.session_json), apply=True)

    report = run_memory_doctor(dest)

    assert report.verdict == HAS_PENDING_REVIEW
    assert report.import_session_count == 1
    assert report.pending_candidates_count == 1
    assert report.approved_memory_count is None


def test_final_decisions_remove_pending_count_and_count_rejections(tmp_path):
    dest = tmp_path / "workspace"
    source = tmp_path / "source.txt"
    source.write_text("Customer asked for a drywall quote.", encoding="utf-8")
    preview = unified_preview_memory_import(
        dest_dir=dest,
        input_paths=[source],
        source_type=SOURCE_TYPE_TRANSCRIPTION,
    )
    unified_apply_memory_import(session_json=Path(preview.session_json), apply=True)
    paths = resolve_review_paths(dest_dir=dest)
    candidate_id = json.loads(
        (dest / MEMORY_CANDIDATES_SUBDIR / REVIEW_QUEUE_FILENAME)
        .read_text(encoding="utf-8")
        .strip()
    )["candidate_id"]
    reject_candidate(paths, candidate_id)

    report = run_memory_doctor(dest)

    assert report.pending_candidates_count == 0
    assert report.review_decisions_count == 1
    assert report.rejected_decisions_count == 1


def test_pipeline_workspace_reports_context_bundle_and_counts(tmp_path):
    dest = tmp_path / "demo"
    create_memory_demo_workspace(dest_dir=dest, apply=True, run_pipeline=True)

    report = run_memory_doctor(dest)

    assert report.verdict == HAS_CONTEXT_BUNDLE
    assert report.import_session_count == 1
    assert report.chatgpt_import_session_count == 1
    assert report.email_import_session_count == 1
    assert report.pending_candidates_count == 0
    assert report.approved_decisions_count >= 3
    assert report.approved_export_exists
    assert report.approved_memory_store_exists
    assert report.approved_memory_count >= 3
    assert report.context_bundle_files_exist
    assert report.model_called is False
    assert report.embeddings_used is False
    assert report.live_memory_written is False


def test_malformed_optional_jsonl_warns_without_hard_failure(tmp_path):
    dest = tmp_path / "workspace"
    queue = dest / MEMORY_CANDIDATES_SUBDIR / REVIEW_QUEUE_FILENAME
    queue.parent.mkdir(parents=True)
    queue.write_text('{"candidate_id": "ok", "review_status": "pending"}\nnot-json\n', encoding="utf-8")

    report = run_memory_doctor(dest)

    assert report.verdict == NEEDS_ATTENTION
    assert report.pending_candidates_count == 1
    assert report.warnings
    assert "Malformed JSON" in report.warnings[0]


def test_memory_doctor_json_cli(tmp_path):
    dest = tmp_path / "demo"
    create_memory_demo_workspace(dest_dir=dest, apply=True)

    result = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts" / "memory_doctor.py"),
            "--dest-dir",
            str(dest),
            "--json",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(result.stdout)
    assert payload["verdict"] == READY_FOR_IMPORT
    assert payload["model_called"] is False
    assert payload["embeddings_used"] is False
    assert payload["live_memory_written"] is False
