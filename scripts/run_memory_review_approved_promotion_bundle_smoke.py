#!/usr/bin/env python3
"""Dry-run/local smoke producing an operator approved-promotion bundle.

This smoke stages local fixture candidates, runs approve/edit/reject review
decisions in a temp workspace, then writes an ``approved_promotion_bundle/``
directory with a machine-readable promotion manifest and operator README.
Approved and edited candidates are included; rejected candidates are excluded.
It never calls models, embeddings, networks, live accounts, or live runtime
memory/vector DB.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import tempfile
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from project_guardian.local_ingestion.memory_candidate_review import (  # noqa: E402
    approve_candidate,
    edit_candidate,
    find_latest_edited_text_path,
    list_candidates,
    load_all_decisions,
    load_latest_decisions,
    load_queue_candidates,
    reject_candidate,
    resolve_review_paths,
)
from project_guardian.local_ingestion.unified_memory_import import (  # noqa: E402
    SOURCE_TYPE_TRANSCRIPTION,
    unified_apply_memory_import,
    unified_preview_memory_import,
)

BUNDLE_DIRNAME = "approved_promotion_bundle"
MANIFEST_FILENAME = "promotion_manifest.json"
README_FILENAME = "README.md"

EDITED_TEXT = (
    "Edited approved memory: kitchen countertop measurement is 42 inches and "
    "the revised tile color is blue."
)


@dataclass
class ApprovedPromotionBundleReport:
    verdict: str
    workspace: str
    workspace_preserved: bool
    bundle_path: str = ""
    promotion_manifest_path: str = ""
    promotion_manifest_valid_json: bool = False
    approved_candidate_included: bool = False
    edited_candidate_included: bool = False
    edited_text_preserved: bool = False
    original_text_preserved_for_edit: bool = False
    rejected_candidate_excluded: bool = False
    promotion_item_count: int = 0
    excluded_rejected_count: int = 0
    promotion_items_have_review_links: bool = False
    promotion_items_have_hashes: bool = False
    bundle_paths_inside_workspace: bool = False
    manifest_hash_present: bool = False
    operator_required: bool = True
    dry_run: bool = True
    local_only: bool = True
    model_called: bool = False
    embeddings_used: bool = False
    live_memory_written: bool = False
    live_vector_db_written: bool = False
    account_api_network_accessed: bool = False
    autonomy_enabled: bool = False
    errors: List[str] = field(default_factory=list)
    artifact_paths: Dict[str, str] = field(default_factory=dict)

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
    if not str(base_dir).strip():
        raise ValueError("Refusing to use empty smoke workspace path.")
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


def _sha256_bytes(data: bytes) -> str:
    digest = hashlib.sha256()
    digest.update(data)
    return digest.hexdigest()


def _sha256_file(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _sha256_text(text: str) -> str:
    return _sha256_bytes(text.encode("utf-8"))


def _path_inside_workspace(path: Path, workspace: Path) -> bool:
    try:
        path.resolve().relative_to(workspace.resolve())
        return True
    except ValueError:
        return False


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


def _read_source_text(candidate: Dict[str, Any]) -> str:
    source_path = Path(str(candidate.get("source_text_path") or ""))
    if not source_path.is_file():
        raise ValueError(f"Candidate source text not found: {source_path}")
    return source_path.read_text(encoding="utf-8").strip()


def _run_review_fixture_flow(workspace: Path) -> tuple[Path, Dict[str, str], Dict[str, str]]:
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

    approve_candidate(paths, approve_id, notes="Promotion bundle smoke approve fixture.")
    reject_candidate(paths, reject_id, notes="Promotion bundle smoke reject fixture.")
    edit_candidate(
        paths,
        edit_id,
        EDITED_TEXT,
        notes="Promotion bundle smoke edit fixture.",
    )
    approve_candidate(
        paths,
        edit_id,
        notes="Promotion bundle smoke approve edited fixture.",
        force=True,
    )

    return dest_dir, {
        "approve": approve_id,
        "reject": reject_id,
        "edit": edit_id,
    }, {
        "approve": "approve_branch.txt",
        "reject": "reject_branch.txt",
        "edit": "edit_branch.txt",
    }


def _build_promotion_items(
    *,
    paths: Any,
    fixture_ids: Dict[str, str],
) -> tuple[List[Dict[str, Any]], int, int, int]:
    candidates = load_queue_candidates(paths.queue_path)
    candidates_by_id = {str(item["candidate_id"]): item for item in candidates}
    latest = load_latest_decisions(paths.decisions_path)
    all_decisions = load_all_decisions(paths.decisions_path)

    approved_count = 0
    edited_count = 0
    rejected_count = 0
    promotion_items: List[Dict[str, Any]] = []

    reject_id = fixture_ids["reject"]
    if str(latest.get(reject_id, {}).get("new_status")) == "rejected":
        rejected_count = 1

    for key in ("approve", "edit"):
        candidate_id = fixture_ids[key]
        decision = latest.get(candidate_id)
        if not decision or str(decision.get("new_status")) != "approved":
            continue

        candidate = candidates_by_id[candidate_id]
        original_text = _read_source_text(candidate)
        edited_text_path = find_latest_edited_text_path(candidate_id, all_decisions)
        text_was_edited = bool(edited_text_path)
        if text_was_edited:
            promoted_text = Path(edited_text_path).read_text(encoding="utf-8").strip()
            decision_type = "edited"
            edited_count += 1
        else:
            promoted_text = original_text
            decision_type = "approved"
            approved_count += 1

        promotion_items.append(
            {
                "candidate_id": candidate_id,
                "decision_id": str(decision.get("decision_id") or ""),
                "decision_type": decision_type,
                "source_type": str(candidate.get("source_type") or SOURCE_TYPE_TRANSCRIPTION),
                "original_text": original_text,
                "promoted_text": promoted_text,
                "text_was_edited": text_was_edited,
                "source_queue_path": str(paths.queue_path.resolve()),
                "review_decision_log_path": str(paths.decisions_path.resolve()),
                "candidate_sha256": str(candidate.get("source_sha256") or _sha256_text(original_text)),
                "promoted_text_sha256": _sha256_text(promoted_text),
                "ready_for_future_promotion": True,
                "live_memory_written": False,
                "live_vector_db_written": False,
                "operator_required": True,
            }
        )

    return promotion_items, approved_count, edited_count, rejected_count


def _write_readme(bundle_dir: Path, manifest: Dict[str, Any]) -> Path:
    readme_path = bundle_dir / README_FILENAME
    lines = [
        "# Approved Promotion Bundle",
        "",
        "Dry-run/local operator bundle for memory candidates ready for future promotion.",
        "",
        f"- Workspace: `{manifest.get('workspace', '')}`",
        f"- Bundle path: `{manifest.get('bundle_path', '')}`",
        f"- Promotion items: `{manifest.get('promotion_item_count', 0)}`",
        f"- Excluded rejected: `{manifest.get('excluded_rejected_count', 0)}`",
        "",
        "## Included candidates",
        "",
    ]
    for item in manifest.get("promotion_items") or []:
        lines.append(
            f"- `{item.get('candidate_id')}` ({item.get('decision_type')}) "
            f"edited={item.get('text_was_edited')}"
        )
    lines.extend(
        [
            "",
            "## Audit references",
            "",
            f"- Review queue: `{manifest.get('source_queue_path', '')}`",
            f"- Review decisions log: `{manifest.get('review_decisions_log_path', '')}`",
            f"- Review decisions SHA-256: `{manifest.get('review_decisions_log_sha256', '')}`",
            "",
            "Recovery inspection evidence is covered separately by the recovery",
            "inspection bundle smoke; this bundle references review decision audit trails only.",
            "",
            "## Safety",
            "",
            f"- dry_run: `{manifest.get('dry_run')}`",
            f"- local_only: `{manifest.get('local_only')}`",
            f"- operator_required: `{manifest.get('operator_required')}`",
            f"- live_memory_written: `{manifest.get('live_memory_written')}`",
            f"- live_vector_db_written: `{manifest.get('live_vector_db_written')}`",
            "",
            "This bundle is for operator inspection only. It does not write live runtime",
            "memory or vector DB data.",
        ]
    )
    readme_path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    return readme_path


def _build_promotion_bundle(workspace: Path) -> ApprovedPromotionBundleReport:
    errors: List[str] = []
    report = ApprovedPromotionBundleReport(
        verdict="FAIL",
        workspace=str(workspace.resolve()),
        workspace_preserved=True,
        autonomy_enabled=_read_autonomy_enabled(),
    )
    if report.autonomy_enabled:
        report.errors.append("Autonomy is enabled; approved promotion bundle smoke is blocked.")
        return report

    dest_dir, fixture_ids, _fixture_names = _run_review_fixture_flow(workspace)
    paths = resolve_review_paths(dest_dir=dest_dir)
    promotion_items, approved_count, edited_count, rejected_count = _build_promotion_items(
        paths=paths,
        fixture_ids=fixture_ids,
    )

    bundle_dir = workspace / BUNDLE_DIRNAME
    bundle_dir.mkdir(parents=True, exist_ok=True)
    report.bundle_path = str(bundle_dir.resolve())

    candidate_source_hashes = {
        str(item["candidate_id"]): str(item["candidate_sha256"])
        for item in promotion_items
    }
    decisions_log_sha256 = _sha256_file(paths.decisions_path)

    manifest_without_hash: Dict[str, Any] = {
        "verdict": "PASS",
        "workspace": report.workspace,
        "bundle_path": report.bundle_path,
        "approved_candidate_count": approved_count,
        "edited_candidate_count": edited_count,
        "rejected_candidate_count": rejected_count,
        "promotion_item_count": len(promotion_items),
        "excluded_rejected_count": rejected_count,
        "promotion_items": promotion_items,
        "source_queue_path": str(paths.queue_path.resolve()),
        "review_decisions_log_path": str(paths.decisions_path.resolve()),
        "review_decisions_log_sha256": decisions_log_sha256,
        "candidate_source_hashes": candidate_source_hashes,
        "operator_required": True,
        "dry_run": True,
        "local_only": True,
        "model_called": False,
        "embeddings_used": False,
        "live_memory_written": False,
        "live_vector_db_written": False,
        "account_api_network_accessed": False,
        "autonomy_enabled": False,
        "errors": [],
    }
    manifest_bytes = (
        json.dumps(manifest_without_hash, indent=2, ensure_ascii=False) + "\n"
    ).encode("utf-8")
    manifest_hash = _sha256_bytes(manifest_bytes)
    manifest: Dict[str, Any] = dict(manifest_without_hash)
    manifest["promotion_manifest_sha256"] = manifest_hash

    manifest_path = bundle_dir / MANIFEST_FILENAME
    manifest_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    readme_path = _write_readme(bundle_dir, manifest)

    report.promotion_manifest_path = str(manifest_path.resolve())
    report.promotion_manifest_valid_json = True
    try:
        loaded = json.loads(manifest_path.read_text(encoding="utf-8"))
        report.promotion_manifest_valid_json = isinstance(loaded, dict)
        manifest = loaded
    except json.JSONDecodeError:
        report.promotion_manifest_valid_json = False
        errors.append("Promotion manifest is not valid JSON.")

    approve_id = fixture_ids["approve"]
    edit_id = fixture_ids["edit"]
    reject_id = fixture_ids["reject"]
    items_by_id = {str(item["candidate_id"]): item for item in manifest.get("promotion_items") or []}

    report.approved_candidate_included = approve_id in items_by_id
    report.edited_candidate_included = edit_id in items_by_id
    report.rejected_candidate_excluded = reject_id not in items_by_id
    report.promotion_item_count = int(manifest.get("promotion_item_count") or 0)
    report.excluded_rejected_count = int(manifest.get("excluded_rejected_count") or 0)

    edited_item = items_by_id.get(edit_id)
    if edited_item:
        report.edited_text_preserved = edited_item.get("promoted_text") == EDITED_TEXT
        report.original_text_preserved_for_edit = (
            "Edit branch fixture" in str(edited_item.get("original_text") or "")
            and edited_item.get("promoted_text") != edited_item.get("original_text")
        )

    report.promotion_items_have_review_links = all(
        bool(item.get("decision_id"))
        and bool(item.get("review_decision_log_path"))
        and bool(item.get("source_queue_path"))
        for item in manifest.get("promotion_items") or []
    )
    report.promotion_items_have_hashes = all(
        bool(item.get("candidate_sha256")) and bool(item.get("promoted_text_sha256"))
        for item in manifest.get("promotion_items") or []
    )
    report.manifest_hash_present = bool(manifest.get("promotion_manifest_sha256"))

    path_checks = (
        bundle_dir,
        manifest_path,
        readme_path,
        paths.queue_path,
        paths.decisions_path,
    )
    report.bundle_paths_inside_workspace = all(
        _path_inside_workspace(path, workspace) for path in path_checks
    )

    report.artifact_paths = {
        "bundle_dir": report.bundle_path,
        "promotion_manifest": report.promotion_manifest_path,
        "promotion_readme": str(readme_path.resolve()),
        "review_queue": str(paths.queue_path.resolve()),
        "review_decisions": str(paths.decisions_path.resolve()),
    }

    if not bundle_dir.is_dir():
        errors.append("Promotion bundle directory was not created.")
    if not manifest_path.is_file():
        errors.append("Promotion manifest was not created.")
    if not report.promotion_manifest_valid_json:
        errors.append("Promotion manifest is not valid JSON.")
    if not report.approved_candidate_included:
        errors.append("Approved fixture candidate was not included in promotion bundle.")
    if not report.edited_candidate_included:
        errors.append("Edited fixture candidate was not included in promotion bundle.")
    if not report.edited_text_preserved:
        errors.append("Edited candidate promoted text was not preserved.")
    if not report.original_text_preserved_for_edit:
        errors.append("Edited candidate original text was not preserved separately.")
    if not report.rejected_candidate_excluded:
        errors.append("Rejected fixture candidate was not excluded.")
    if report.excluded_rejected_count < 1:
        errors.append("Rejected exclusion count is missing.")
    if report.promotion_item_count != approved_count + edited_count:
        errors.append("Promotion item count does not equal approved + edited counts.")
    if report.promotion_item_count != 2:
        errors.append("Expected exactly two promotion items for fixture flow.")
    if not report.promotion_items_have_review_links:
        errors.append("Promotion items are missing review decision links.")
    if not report.promotion_items_have_hashes:
        errors.append("Promotion items are missing hashes.")
    if not report.manifest_hash_present:
        errors.append("Promotion manifest hash is missing.")
    if not report.bundle_paths_inside_workspace:
        errors.append("One or more bundle paths are outside the temp workspace.")
    if manifest.get("review_decisions_log_sha256") != _sha256_file(paths.decisions_path):
        errors.append("Review decisions log hash does not match file.")
    for item in manifest.get("promotion_items") or []:
        if item.get("promoted_text_sha256") != _sha256_text(str(item.get("promoted_text") or "")):
            errors.append(
                f"Promoted text hash mismatch for candidate {item.get('candidate_id')}."
            )

    report.operator_required = bool(manifest.get("operator_required"))
    report.dry_run = bool(manifest.get("dry_run"))
    report.local_only = bool(manifest.get("local_only"))

    for flag_name in (
        "model_called",
        "embeddings_used",
        "live_memory_written",
        "live_vector_db_written",
        "account_api_network_accessed",
        "autonomy_enabled",
    ):
        if getattr(report, flag_name) or manifest.get(flag_name):
            errors.append(f"{flag_name} unexpectedly true.")

    report.errors = errors
    report.verdict = "PASS" if not errors else "FAIL"
    return report


def run_memory_review_approved_promotion_bundle_smoke(
    *,
    base_dir: Path | None = None,
    keep_temp: bool = False,
) -> ApprovedPromotionBundleReport:
    """Build a dry-run operator approved-promotion bundle after review decisions."""
    owned_temp = base_dir is None
    workspace = (
        Path(tempfile.mkdtemp(prefix="elysia_memory_approved_promotion_bundle_"))
        if owned_temp
        else _reject_dangerous_base(Path(base_dir))
    )
    workspace.mkdir(parents=True, exist_ok=True)
    try:
        report = _build_promotion_bundle(workspace)
        report.workspace_preserved = (not owned_temp) or keep_temp
        return report
    finally:
        if owned_temp and not keep_temp:
            shutil.rmtree(workspace, ignore_errors=True)


def format_operator_summary(report: ApprovedPromotionBundleReport) -> str:
    lines = [
        "Memory review approved promotion bundle smoke",
        "=" * 50,
        f"Verdict: {report.verdict}",
        f"Workspace: {report.workspace}",
        f"Workspace preserved: {report.workspace_preserved}",
        f"Bundle path: {report.bundle_path}",
        f"Promotion manifest: {report.promotion_manifest_path}",
        "",
        "Bundle checks:",
        f"  manifest valid JSON: {report.promotion_manifest_valid_json}",
        f"  approved candidate included: {report.approved_candidate_included}",
        f"  edited candidate included: {report.edited_candidate_included}",
        f"  edited text preserved: {report.edited_text_preserved}",
        f"  original text preserved for edit: {report.original_text_preserved_for_edit}",
        f"  rejected candidate excluded: {report.rejected_candidate_excluded}",
        f"  promotion item count: {report.promotion_item_count}",
        f"  excluded rejected count: {report.excluded_rejected_count}",
        f"  promotion items have review links: {report.promotion_items_have_review_links}",
        f"  promotion items have hashes: {report.promotion_items_have_hashes}",
        f"  bundle paths inside workspace: {report.bundle_paths_inside_workspace}",
        f"  manifest hash present: {report.manifest_hash_present}",
        f"  operator_required: {report.operator_required}",
        f"  dry_run: {report.dry_run}",
        f"  local_only: {report.local_only}",
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
        description="Run local-only Memory review approved promotion bundle smoke.",
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
        report = run_memory_review_approved_promotion_bundle_smoke(
            base_dir=args.base_dir,
            keep_temp=args.keep_temp,
        )
    except ValueError as exc:
        report = ApprovedPromotionBundleReport(
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
