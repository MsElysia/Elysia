#!/usr/bin/env python3
"""Run the RC-required Windows intelligence pytest slice.

Excludes known-legacy tests/test_task_execution.py (GuardianCore singleton
failures outside the Windows intel path). Does not start Ollama, BATs,
providers, or autonomy.
"""
from __future__ import annotations

import subprocess
import sys

RC_REQUIRED = [
    "tests/test_windows_sync_status.py",
    "tests/test_tool_registry_key_persistence.py",
    "tests/test_document_ingestion_workflow.py",
    "tests/test_local_memory_chat_pilot.py",
    "tests/test_capability_awareness.py",
    "tests/test_capability_composition.py",
    "tests/test_local_documents_search.py",
    "tests/test_structured_field_extraction.py",
    "tests/test_extract_records.py",
    "tests/test_adaptive_replan.py",
    "tests/test_composition_outcome_feedback.py",
    "tests/test_comparable_outcome_learning.py",
    "tests/test_conversation_continuity.py",
    "tests/test_operator_task_state.py",
    "tests/test_task_step_completion.py",
    "tests/test_document_task_execution.py",
    "tests/test_contained_startup.py",
    "tests/test_restricted_runtime_adapter.py",
    "tests/test_control_panel_restricted_runtime.py",
    "tests/test_dashboard_plan_progress.py",
]


def main() -> int:
    cmd = [
        sys.executable,
        "-B",
        "-m",
        "pytest",
        "--noconftest",
        "-q",
        "-rs",
        "-p",
        "no:cacheprovider",
        # Preserve Windows symlink privilege cases as unverified outside privileged hosts.
        "-k",
        "not symlink_escape_skipped and not directory_symlink_escape_skipped",
        *RC_REQUIRED,
    ]
    print("+", " ".join(cmd), flush=True)
    return subprocess.call(cmd)


if __name__ == "__main__":
    raise SystemExit(main())
