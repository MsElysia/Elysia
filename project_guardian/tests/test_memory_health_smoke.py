# project_guardian/tests/test_memory_health_smoke.py

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from project_guardian.local_ingestion.memory_diagnostics import (
    HAS_CONTEXT_BUNDLE,
    run_memory_health_smoke,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_health_smoke_passes_and_cleans_owned_temp():
    report = run_memory_health_smoke()

    assert report.verdict == "PASS"
    assert report.demo_workspace_created
    assert report.doctor_verdict == HAS_CONTEXT_BUNDLE
    assert report.candidates_created >= 3
    assert report.approvals_created >= 3
    assert report.search_result_count >= 1
    assert report.context_bundle_created
    assert report.temp_path is None
    assert report.model_called is False
    assert report.embeddings_used is False
    assert report.live_memory_written is False
    assert report.autonomy_enabled is False


def test_health_smoke_keep_temp_preserves_workspace():
    report = run_memory_health_smoke(keep_temp=True)

    assert report.verdict == "PASS"
    assert report.temp_path is not None
    temp = Path(report.temp_path)
    try:
        assert temp.is_dir()
        assert (temp / "demo_workspace").is_dir()
    finally:
        import shutil

        shutil.rmtree(temp, ignore_errors=True)


def test_health_smoke_json_cli():
    result = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts" / "run_memory_health_smoke.py"),
            "--json",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(result.stdout)
    assert payload["verdict"] == "PASS"
    assert payload["doctor_verdict"] == HAS_CONTEXT_BUNDLE
    assert payload["search_result_count"] >= 1
    assert payload["model_called"] is False
    assert payload["embeddings_used"] is False
    assert payload["live_memory_written"] is False
