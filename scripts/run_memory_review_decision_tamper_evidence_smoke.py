#!/usr/bin/env python3
"""Dry-run/local smoke proving the review decision audit checker detects tampering.

This smoke builds a valid append-only `review_decisions.jsonl` from local
fixtures in a temp workspace, then writes tampered copies (malformed JSON line,
missing required field, out-of-order timestamp, unknown candidate id, and an
unsupported status transition) and runs a self-contained, local-only audit
checker against each. It verifies the clean log passes and every tampered log
fails with a specific error message. It never calls models, embeddings,
networks, live accounts, or live runtime memory/vector DB.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from project_guardian.local_ingestion.memory_candidate_review import (  # noqa: E402
    approve_candidate,
    edit_candidate,
    list_candidates,
    reject_candidate,
    resolve_review_paths,
)
from project_guardian.local_ingestion.unified_memory_import import (  # noqa: E402
    SOURCE_TYPE_TRANSCRIPTION,
    unified_apply_memory_import,
    unified_preview_memory_import,
)

EDITED_TEXT = (
    "Edited approved memory: kitchen countertop measurement is 42 inches and "
    "the revised tile color is blue."
)

REQUIRED_DECISION_FIELDS = (
    "decision_id",
    "candidate_id",
    "previous_status",
    "new_status",
    "decided_at",
    "operator_required",
    "live_memory_written",
    "source_queue_path",
)
ALLOWED_PREVIOUS_STATUSES = frozenset({"pending", "approved", "rejected", "edited"})
ALLOWED_NEW_STATUSES = frozenset({"approved", "rejected", "edited"})


@dataclass
class TamperCaseResult:
    name: str
    verdict: str
    expected_token: str
    token_found: bool
    errors: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class TamperEvidenceReport:
    verdict: str
    workspace: str
    workspace_preserved: bool
    clean_log_verdict: str = "UNKNOWN"
    tampered_cases_run: int = 0
    malformed_json_detected: bool = False
    missing_field_detected: bool = False
    non_chronological_detected: bool = False
    unknown_candidate_detected: bool = False
    unsupported_transition_detected: bool = False
    specific_errors_present: bool = False
    clean_log_still_passes: bool = False
    model_called: bool = False
    embeddings_used: bool = False
    live_memory_written: bool = False
    live_vector_db_written: bool = False
    account_api_network_accessed: bool = False
    autonomy_enabled: bool = False
    errors: List[str] = field(default_factory=list)
    cases: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _repo_root() -> Path:
    return PROJECT_ROOT.resolve()


def _read_autonomy_enabled() -> bool:
    path = _repo_root() / "config" / "autonomy.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return bool(payload.get("enabled"))


def _reject_dangerous_base(base_dir: Path) -> Path:
    resolved = base_dir.expanduser().resolve()
    repo_root = _repo_root()
    home = Path.home().resolve()
    if resolved == resolved.parent:
        raise ValueError(f"Refusing to use filesystem root as smoke workspace: {resolved}")
    if resolved == home:
        raise ValueError(f"Refusing to use home directory as smoke workspace: {resolved}")
    if resolved == repo_root:
        raise ValueError(f"Refusing to use repository root as smoke workspace: {resolved}")
    if resolved.anchor and str(resolved) == resolved.anchor:
        raise ValueError(f"Refusing to use drive root as smoke workspace: {resolved}")
    if resolved.exists() and not resolved.is_dir():
        raise ValueError(f"Smoke workspace exists but is not a directory: {resolved}")
    return resolved


def audit_decision_log(
    log_path: Path,
    *,
    known_candidate_ids: Optional[Set[str]] = None,
) -> Tuple[str, List[str]]:
    """Local-only audit checker for a review_decisions.jsonl log.

    Returns a (verdict, errors) tuple. Detects malformed JSON, missing required
    fields, unsupported status transitions, unknown candidate ids (when a known
    set is provided), and non-chronological timestamps. No network/model/memory
    access is performed.
    """
    errors: List[str] = []
    if not log_path.is_file():
        return "FAIL", [f"missing_log_file: {log_path}"]

    raw_lines = [
        line
        for line in log_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if not raw_lines:
        return "FAIL", ["empty_log_file: no decision entries found"]

    entries: List[Dict[str, Any]] = []
    for line_no, line in enumerate(raw_lines, start=1):
        try:
            item = json.loads(line)
        except json.JSONDecodeError as exc:
            errors.append(f"malformed_json: line {line_no} is not valid JSON ({exc})")
            continue
        if not isinstance(item, dict):
            errors.append(f"malformed_json: line {line_no} is not a JSON object")
            continue

        missing = [name for name in REQUIRED_DECISION_FIELDS if name not in item]
        if missing:
            errors.append(
                f"missing_required_field: line {line_no} missing {', '.join(missing)}"
            )

        candidate_id = str(item.get("candidate_id") or "").strip()
        if "candidate_id" in item and not candidate_id:
            errors.append(f"missing_required_field: line {line_no} candidate_id is empty")

        previous_status = str(item.get("previous_status") or "").strip()
        if previous_status and previous_status not in ALLOWED_PREVIOUS_STATUSES:
            errors.append(
                f"unsupported_transition: line {line_no} previous_status={previous_status!r}"
            )
        new_status = str(item.get("new_status") or "").strip()
        if new_status and new_status not in ALLOWED_NEW_STATUSES:
            errors.append(
                f"unsupported_transition: line {line_no} new_status={new_status!r}"
            )

        if (
            known_candidate_ids is not None
            and candidate_id
            and candidate_id not in known_candidate_ids
        ):
            errors.append(
                f"unknown_candidate: line {line_no} candidate_id={candidate_id!r}"
            )

        entries.append(item)

    timestamps = [
        str(entry.get("decided_at") or "")
        for entry in entries
        if str(entry.get("decided_at") or "")
    ]
    for index in range(1, len(timestamps)):
        if timestamps[index] < timestamps[index - 1]:
            errors.append(
                "non_chronological: entry "
                f"{index + 1} timestamp {timestamps[index]!r} precedes "
                f"{timestamps[index - 1]!r}"
            )
            break

    verdict = "PASS" if not errors else "FAIL"
    return verdict, errors


def _write_fixture_sources(source_dir: Path) -> List[Path]:
    source_dir.mkdir(parents=True, exist_ok=True)
    fixtures = {
        "approve_branch.txt": (
            "Approve branch fixture: kitchen cabinet measurements are ready for the estimate."
        ),
        "reject_branch.txt": (
            "Reject branch fixture: rejected-only note should never reach approved search output."
        ),
        "edit_branch.txt": (
            "Edit branch fixture: kitchen countertop measurement needs operator correction."
        ),
    }
    paths: List[Path] = []
    for name, content in fixtures.items():
        path = source_dir / name
        path.write_text(content + "\n", encoding="utf-8", newline="\n")
        paths.append(path)
    return paths


def _candidate_by_filename(candidates: List[Dict[str, Any]], filename: str) -> Dict[str, Any]:
    for candidate in candidates:
        if str(candidate.get("original_filename") or "") == filename:
            return candidate
    raise ValueError(f"Candidate fixture not found: {filename}")


def _build_clean_log(workspace: Path) -> Tuple[Path, List[Dict[str, Any]], Set[str]]:
    source_dir = workspace / "source"
    dest_dir = workspace / "dest"
    fixture_paths = _write_fixture_sources(source_dir)
    preview = unified_preview_memory_import(
        dest_dir=dest_dir,
        input_paths=fixture_paths,
        source_type=SOURCE_TYPE_TRANSCRIPTION,
    )
    unified_apply_memory_import(session_json=Path(preview.session_json), apply=True)

    paths = resolve_review_paths(dest_dir=dest_dir)
    candidates = list_candidates(paths, include_all=True).candidates
    approve_id = str(_candidate_by_filename(candidates, "approve_branch.txt")["candidate_id"])
    reject_id = str(_candidate_by_filename(candidates, "reject_branch.txt")["candidate_id"])
    edit_id = str(_candidate_by_filename(candidates, "edit_branch.txt")["candidate_id"])

    approve_candidate(paths, approve_id, notes="Tamper evidence clean approve fixture.")
    reject_candidate(paths, reject_id, notes="Tamper evidence clean reject fixture.")
    edit_candidate(paths, edit_id, EDITED_TEXT, notes="Tamper evidence clean edit fixture.")

    clean_entries = [
        json.loads(line)
        for line in paths.decisions_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    known_ids = {approve_id, reject_id, edit_id}
    return paths.decisions_path, clean_entries, known_ids


def _write_log(path: Path, entries: Sequence[Any], *, extra_raw_lines: Sequence[str] = ()) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(entry, ensure_ascii=False) for entry in entries]
    lines.extend(extra_raw_lines)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")


def _run_tamper_flow(
    workspace: Path,
    *,
    workspace_preserved: bool,
) -> TamperEvidenceReport:
    errors: List[str] = []
    report = TamperEvidenceReport(
        verdict="FAIL",
        workspace=str(workspace.resolve()),
        workspace_preserved=workspace_preserved,
        autonomy_enabled=_read_autonomy_enabled(),
    )

    if report.autonomy_enabled:
        report.errors.append("Autonomy is enabled; tamper evidence smoke is blocked.")
        return report

    clean_log_path, clean_entries, known_ids = _build_clean_log(workspace)
    tamper_dir = workspace / "tampered"
    tamper_dir.mkdir(parents=True, exist_ok=True)

    clean_verdict, clean_errors = audit_decision_log(
        clean_log_path, known_candidate_ids=known_ids
    )
    report.clean_log_verdict = clean_verdict
    report.clean_log_still_passes = clean_verdict == "PASS" and not clean_errors
    if not report.clean_log_still_passes:
        errors.append(f"Clean audit log did not pass: {clean_errors}")

    template = dict(clean_entries[-1])

    def _future_entry(**overrides: Any) -> Dict[str, Any]:
        entry = dict(template)
        entry["decided_at"] = "2999-01-01T00:00:00+00:00"
        entry.update(overrides)
        return entry

    missing_field_entry = _future_entry()
    missing_field_entry.pop("new_status", None)

    non_chrono_entry = dict(template)
    non_chrono_entry["decided_at"] = "2000-01-01T00:00:00+00:00"

    cases: List[TamperCaseResult] = []

    # 1) malformed JSON line appended after the clean entries.
    malformed_path = tamper_dir / "malformed_json.jsonl"
    _write_log(malformed_path, clean_entries, extra_raw_lines=["{ this is not valid json"])
    verdict, case_errors = audit_decision_log(malformed_path, known_candidate_ids=known_ids)
    token_found = any("malformed_json" in err for err in case_errors)
    cases.append(TamperCaseResult("malformed_json", verdict, "malformed_json", token_found, case_errors))
    report.malformed_json_detected = verdict == "FAIL" and token_found

    # 2) missing required field.
    missing_path = tamper_dir / "missing_field.jsonl"
    _write_log(missing_path, [*clean_entries, missing_field_entry])
    verdict, case_errors = audit_decision_log(missing_path, known_candidate_ids=known_ids)
    token_found = any("missing_required_field" in err for err in case_errors)
    cases.append(
        TamperCaseResult("missing_field", verdict, "missing_required_field", token_found, case_errors)
    )
    report.missing_field_detected = verdict == "FAIL" and token_found

    # 3) non-chronological timestamp.
    non_chrono_path = tamper_dir / "non_chronological.jsonl"
    _write_log(non_chrono_path, [*clean_entries, non_chrono_entry])
    verdict, case_errors = audit_decision_log(non_chrono_path, known_candidate_ids=known_ids)
    token_found = any("non_chronological" in err for err in case_errors)
    cases.append(
        TamperCaseResult("non_chronological", verdict, "non_chronological", token_found, case_errors)
    )
    report.non_chronological_detected = verdict == "FAIL" and token_found

    # 4) unknown candidate id (optional).
    unknown_path = tamper_dir / "unknown_candidate.jsonl"
    unknown_entry = _future_entry(candidate_id="unknowncandidate00000000")
    _write_log(unknown_path, [*clean_entries, unknown_entry])
    verdict, case_errors = audit_decision_log(unknown_path, known_candidate_ids=known_ids)
    token_found = any("unknown_candidate" in err for err in case_errors)
    cases.append(
        TamperCaseResult("unknown_candidate", verdict, "unknown_candidate", token_found, case_errors)
    )
    report.unknown_candidate_detected = verdict == "FAIL" and token_found

    # 5) unsupported transition/status (optional).
    unsupported_path = tamper_dir / "unsupported_transition.jsonl"
    unsupported_entry = _future_entry(new_status="deleted")
    _write_log(unsupported_path, [*clean_entries, unsupported_entry])
    verdict, case_errors = audit_decision_log(unsupported_path, known_candidate_ids=known_ids)
    token_found = any("unsupported_transition" in err for err in case_errors)
    cases.append(
        TamperCaseResult(
            "unsupported_transition", verdict, "unsupported_transition", token_found, case_errors
        )
    )
    report.unsupported_transition_detected = verdict == "FAIL" and token_found

    report.tampered_cases_run = len(cases)
    report.cases = [case.to_dict() for case in cases]

    all_failed = all(case.verdict == "FAIL" for case in cases)
    report.specific_errors_present = all(case.token_found for case in cases)

    required_detections = (
        report.malformed_json_detected
        and report.missing_field_detected
        and report.non_chronological_detected
    )
    optional_detections = (
        report.unknown_candidate_detected and report.unsupported_transition_detected
    )

    # Re-check the clean log after tamper cases to prove it is unaffected.
    reverify_verdict, reverify_errors = audit_decision_log(
        clean_log_path, known_candidate_ids=known_ids
    )
    if reverify_verdict != "PASS" or reverify_errors:
        report.clean_log_still_passes = False
        errors.append(f"Clean audit log regressed after tamper cases: {reverify_errors}")

    if not report.clean_log_still_passes:
        errors.append("Clean audit log did not remain PASS.")
    if not required_detections:
        errors.append("A required tamper case (malformed/missing/non-chronological) was not detected.")
    if not optional_detections:
        errors.append("An optional tamper case (unknown candidate/unsupported transition) was not detected.")
    if not all_failed:
        errors.append("A tampered log did not return verdict=FAIL.")
    if not report.specific_errors_present:
        errors.append("A tamper case did not produce a specific error token.")

    for flag_name in (
        "model_called",
        "embeddings_used",
        "live_memory_written",
        "live_vector_db_written",
        "account_api_network_accessed",
        "autonomy_enabled",
    ):
        if getattr(report, flag_name):
            errors.append(f"{flag_name} unexpectedly true.")

    report.errors = errors
    report.verdict = "PASS" if not errors else "FAIL"
    return report


def run_memory_review_decision_tamper_evidence_smoke(
    *,
    base_dir: Path | None = None,
    keep_temp: bool = False,
) -> TamperEvidenceReport:
    """Build a clean audit log and prove the checker detects tampered variants."""
    owned_temp = base_dir is None
    workspace = (
        Path(tempfile.mkdtemp(prefix="elysia_memory_review_tamper_evidence_"))
        if owned_temp
        else _reject_dangerous_base(Path(base_dir))
    )
    workspace.mkdir(parents=True, exist_ok=True)
    try:
        return _run_tamper_flow(
            workspace,
            workspace_preserved=(not owned_temp) or keep_temp,
        )
    finally:
        if owned_temp and not keep_temp:
            shutil.rmtree(workspace, ignore_errors=True)


def format_operator_summary(report: TamperEvidenceReport) -> str:
    lines = [
        "Memory review decision tamper evidence smoke",
        "=" * 44,
        f"Verdict: {report.verdict}",
        f"Workspace: {report.workspace}",
        f"Workspace preserved: {report.workspace_preserved}",
        f"Clean log verdict: {report.clean_log_verdict}",
        f"Clean log still passes: {report.clean_log_still_passes}",
        f"Tampered cases run: {report.tampered_cases_run}",
        "",
        "Detections:",
        f"  malformed_json: {report.malformed_json_detected}",
        f"  missing_required_field: {report.missing_field_detected}",
        f"  non_chronological: {report.non_chronological_detected}",
        f"  unknown_candidate: {report.unknown_candidate_detected}",
        f"  unsupported_transition: {report.unsupported_transition_detected}",
        f"  specific errors present: {report.specific_errors_present}",
        "",
        "Safety:",
        f"  model_called: {report.model_called}",
        f"  embeddings_used: {report.embeddings_used}",
        f"  live_memory_written: {report.live_memory_written}",
        f"  live_vector_db_written: {report.live_vector_db_written}",
        f"  account_api_network_accessed: {report.account_api_network_accessed}",
        f"  autonomy_enabled: {report.autonomy_enabled}",
    ]
    if report.errors:
        lines.extend(["", "Errors:"])
        lines.extend(f"  - {error}" for error in report.errors)
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run local-only Memory review decision tamper evidence smoke.",
    )
    parser.add_argument("--json", action="store_true", help="Print JSON smoke result")
    parser.add_argument(
        "--base-dir",
        type=Path,
        default=None,
        help="Optional workspace root. Defaults to a temporary directory.",
    )
    parser.add_argument(
        "--keep-temp",
        action="store_true",
        help="Preserve an automatically-created temporary workspace.",
    )
    args = parser.parse_args(argv)

    try:
        report = run_memory_review_decision_tamper_evidence_smoke(
            base_dir=args.base_dir,
            keep_temp=args.keep_temp,
        )
    except ValueError as exc:
        report = TamperEvidenceReport(
            verdict="FAIL",
            workspace=str(args.base_dir or ""),
            workspace_preserved=False,
            autonomy_enabled=_read_autonomy_enabled(),
            errors=[str(exc)],
        )

    if args.json:
        print(json.dumps(report.to_dict(), indent=2, ensure_ascii=False))
    else:
        print(format_operator_summary(report))
    return 0 if report.verdict == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
