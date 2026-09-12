#!/usr/bin/env python3
"""Dry-run/local smoke producing a final approved-promotion readiness packet.

This smoke rebuilds the current valid dry-run safety chain in a temporary
workspace, confirms those clean inputs still pass, then writes one operator
packet summarizing staged items, approval proof, tamper proof, live-write
blockade proof, remaining blocked status, and the future explicit milestone
required before any live write path may exist. It never writes live runtime
memory, never writes vector DB files, and never calls models, embeddings,
networks, live accounts, or UI routes.
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
from typing import Any, Dict, List, Sequence

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from run_memory_review_approved_promotion_live_write_blockade_smoke import (  # noqa: E402
    LIVE_WRITE_DENIAL_REASON,
    VECTOR_WRITE_DENIAL_REASON,
)
from run_memory_review_approved_promotion_live_write_blockade_tamper_evidence_smoke import (  # noqa: E402
    run_memory_review_approved_promotion_live_write_blockade_tamper_evidence_smoke,
)
from run_memory_review_approved_promotion_operator_approved_staging_smoke import (  # noqa: E402
    APPROVAL_TOKEN_PHRASE,
    EDITED_TEXT_MARKER,
)
from run_memory_review_approved_promotion_operator_approved_staging_tamper_evidence_smoke import (  # noqa: E402
    audit_operator_approved_staging_manifest,
)

PACKET_DIRNAME = "approved_promotion_final_readiness_packet"
PACKET_JSON_FILENAME = "final_readiness_packet.json"
PACKET_README_FILENAME = "FINAL_READINESS_README.md"
STAGING_RECEIPT_DIRNAME = "ap_ste_receipt"
STAGING_RECEIPT_FILENAME = "staging_tamper_evidence_receipt.json"
BLOCKADE_TAMPER_DIRNAME = "ap_lwbte_receipt"
BLOCKADE_TAMPER_FILENAME = "live_write_blockade_tamper_evidence_report.json"

REQUIRED_SAFETY_CHAIN_STAGES = (
    "promotion_bundle",
    "promotion_tamper_evidence",
    "operator_handoff",
    "operator_approval_gate",
    "operator_approved_staging",
    "staging_tamper_evidence",
    "live_write_blockade",
    "live_write_blockade_tamper_evidence",
)

OPERATOR_NEXT_STEPS = [
    "This packet is final dry-run readiness only.",
    "It does not authorize live memory writes.",
    "It does not authorize vector DB writes.",
    (
        "A separate explicit future milestone is required before any live "
        "write path can be designed or implemented."
    ),
]


@dataclass
class FinalPromotionReadinessPacketReport:
    verdict: str
    workspace: str
    packet_path: str = ""
    packet_json_path: str = ""
    packet_json_valid: bool = False
    packet_readme_path: str = ""
    packet_readme_sha256: str = ""
    source_bundle_path: str = ""
    source_bundle_sha256: str = ""
    source_promotion_manifest_sha256: str = ""
    source_operator_handoff_sha256: str = ""
    source_approval_gate_sha256: str = ""
    source_staging_manifest_sha256: str = ""
    source_staging_tamper_evidence_sha256: str = ""
    source_live_write_blockade_sha256: str = ""
    source_live_write_blockade_tamper_evidence_sha256: str = ""
    approval_token_phrase: str = APPROVAL_TOKEN_PHRASE
    promotion_item_count: int = 0
    approved_candidate_count: int = 0
    edited_candidate_count: int = 0
    excluded_rejected_count: int = 0
    ready_for_operator_review: bool = False
    ready_for_operator_approved_staging: bool = False
    ready_for_live_memory_write: bool = False
    future_live_write_allowed: bool = False
    requires_explicit_operator_approval: bool = True
    requires_future_live_write_milestone: bool = True
    live_write_blocked_reason: str = LIVE_WRITE_DENIAL_REASON
    vector_db_write_blocked_reason: str = VECTOR_WRITE_DENIAL_REASON
    approved_items: List[Dict[str, Any]] = field(default_factory=list)
    safety_chain: Dict[str, str] = field(default_factory=dict)
    operator_next_steps: List[str] = field(default_factory=list)
    dry_run: bool = True
    local_only: bool = True
    model_called: bool = False
    embeddings_used: bool = False
    live_memory_written: bool = False
    live_vector_db_written: bool = False
    account_api_network_accessed: bool = False
    autonomy_enabled: bool = False
    errors: List[str] = field(default_factory=list)
    workspace_preserved: bool = False
    artifact_paths: Dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def to_packet_dict(self) -> Dict[str, Any]:
        return {
            "verdict": self.verdict,
            "workspace": self.workspace,
            "packet_path": self.packet_path,
            "packet_json_path": self.packet_json_path,
            "packet_json_valid": self.packet_json_valid,
            "packet_readme_path": self.packet_readme_path,
            "packet_readme_sha256": self.packet_readme_sha256,
            "source_bundle_path": self.source_bundle_path,
            "source_bundle_sha256": self.source_bundle_sha256,
            "source_promotion_manifest_sha256": self.source_promotion_manifest_sha256,
            "source_operator_handoff_sha256": self.source_operator_handoff_sha256,
            "source_approval_gate_sha256": self.source_approval_gate_sha256,
            "source_staging_manifest_sha256": self.source_staging_manifest_sha256,
            "source_staging_tamper_evidence_sha256": (
                self.source_staging_tamper_evidence_sha256
            ),
            "source_live_write_blockade_sha256": self.source_live_write_blockade_sha256,
            "source_live_write_blockade_tamper_evidence_sha256": (
                self.source_live_write_blockade_tamper_evidence_sha256
            ),
            "approval_token_phrase": self.approval_token_phrase,
            "promotion_item_count": self.promotion_item_count,
            "approved_candidate_count": self.approved_candidate_count,
            "edited_candidate_count": self.edited_candidate_count,
            "excluded_rejected_count": self.excluded_rejected_count,
            "ready_for_operator_review": self.ready_for_operator_review,
            "ready_for_operator_approved_staging": (
                self.ready_for_operator_approved_staging
            ),
            "ready_for_live_memory_write": self.ready_for_live_memory_write,
            "future_live_write_allowed": self.future_live_write_allowed,
            "requires_explicit_operator_approval": (
                self.requires_explicit_operator_approval
            ),
            "requires_future_live_write_milestone": (
                self.requires_future_live_write_milestone
            ),
            "live_write_blocked_reason": self.live_write_blocked_reason,
            "vector_db_write_blocked_reason": self.vector_db_write_blocked_reason,
            "approved_items": self.approved_items,
            "safety_chain": self.safety_chain,
            "operator_next_steps": self.operator_next_steps,
            "dry_run": self.dry_run,
            "local_only": self.local_only,
            "model_called": self.model_called,
            "embeddings_used": self.embeddings_used,
            "live_memory_written": self.live_memory_written,
            "live_vector_db_written": self.live_vector_db_written,
            "account_api_network_accessed": self.account_api_network_accessed,
            "autonomy_enabled": self.autonomy_enabled,
            "errors": self.errors,
        }


def _repo_root() -> Path:
    return PROJECT_ROOT.resolve()


def _read_autonomy_enabled() -> bool:
    path = _repo_root() / "config" / "autonomy.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return True
    return bool(payload.get("enabled"))


def _reject_dangerous_base(base_dir: Path) -> Path:
    if not str(base_dir).strip():
        raise ValueError("base_dir must not be empty")
    resolved = base_dir.expanduser().resolve()
    repo_root = _repo_root()
    home = Path.home().resolve()
    if resolved == resolved.anchor or resolved == Path(resolved.anchor):
        raise ValueError("Refusing to use a drive root as base_dir")
    if resolved == home:
        raise ValueError("Refusing to use the home directory as base_dir")
    if resolved == repo_root:
        raise ValueError("Refusing to use the repository root as base_dir")
    return resolved


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _path_inside_workspace(path: Path, workspace: Path) -> bool:
    try:
        path.resolve().relative_to(workspace.resolve())
    except ValueError:
        return False
    return True


def _write_json(path: Path, payload: Dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=False) + "\n", encoding="utf-8")
    return path


def _load_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _require_file(path: Path, label: str, errors: List[str]) -> bool:
    if path.is_file():
        return True
    errors.append(f"missing_{label}: {path}")
    return False


def _write_readme(readme_path: Path, report: FinalPromotionReadinessPacketReport) -> str:
    lines = [
        "# Final Approved Promotion Readiness Packet",
        "",
        "This packet is the dry-run final operator summary of the approved-promotion",
        "safety chain. It does not enable or perform live memory or vector DB writes.",
        "",
        f"Verdict: `{report.verdict}`",
        "",
        "## What would be promoted?",
        "",
        f"- Promotion item count: `{report.promotion_item_count}`",
        f"- Approved candidate count: `{report.approved_candidate_count}`",
        f"- Edited candidate count: `{report.edited_candidate_count}`",
        f"- Excluded rejected count: `{report.excluded_rejected_count}`",
        "",
    ]
    for item in report.approved_items:
        lines.extend(
            [
                f"- `{item.get('decision_type')}` `{item.get('candidate_id')}`: "
                f"{item.get('promoted_text')}",
            ]
        )
    lines.extend(
        [
            "",
            "## Why is it approved?",
            "",
            f"- Approval token phrase: `{report.approval_token_phrase}`",
            f"- Ready for operator review: `{report.ready_for_operator_review}`",
            "- Ready for operator-approved staging: "
            f"`{report.ready_for_operator_approved_staging}`",
            "- Requires explicit operator approval: "
            f"`{report.requires_explicit_operator_approval}`",
            "",
            "## What hashes prove it was not tampered with?",
            "",
            f"- Bundle: `{report.source_bundle_sha256}`",
            f"- Promotion manifest: `{report.source_promotion_manifest_sha256}`",
            f"- Operator handoff: `{report.source_operator_handoff_sha256}`",
            f"- Approval gate: `{report.source_approval_gate_sha256}`",
            f"- Staging manifest: `{report.source_staging_manifest_sha256}`",
            "- Staging tamper evidence: "
            f"`{report.source_staging_tamper_evidence_sha256}`",
            f"- Live-write blockade: `{report.source_live_write_blockade_sha256}`",
            "- Live-write blockade tamper evidence: "
            f"`{report.source_live_write_blockade_tamper_evidence_sha256}`",
            "",
            "## What safety checks passed?",
            "",
        ]
    )
    for stage in REQUIRED_SAFETY_CHAIN_STAGES:
        lines.append(f"- `{stage}`: `{report.safety_chain.get(stage, 'UNKNOWN')}`")
    lines.extend(
        [
            "",
            "## Why is live writing still blocked?",
            "",
            f"- Ready for live memory write: `{report.ready_for_live_memory_write}`",
            f"- Future live write allowed: `{report.future_live_write_allowed}`",
            "- Requires future live-write milestone: "
            f"`{report.requires_future_live_write_milestone}`",
            f"- Live write blocked reason: {report.live_write_blocked_reason}",
            f"- Vector DB write blocked reason: {report.vector_db_write_blocked_reason}",
            "",
            "## Operator next steps",
            "",
        ]
    )
    for step in report.operator_next_steps:
        lines.append(f"- {step}")
    lines.extend(
        [
            "",
            "## Safety",
            "",
            "- This packet is dry-run only.",
            "- Live memory writing remains blocked.",
            "- Vector DB writing remains blocked.",
            "- No live memory or vector write path is implemented.",
            "- Future live write requires a separate explicit milestone.",
            "- Models, embeddings, accounts, and network are not called.",
            "- `elysia/api/server.py`, `project_guardian/core.py`, and",
            "  `config/autonomy.json` are untouched.",
            "",
        ]
    )
    readme_path.parent.mkdir(parents=True, exist_ok=True)
    readme_path.write_text("\n".join(lines), encoding="utf-8")
    return _sha256_file(readme_path)


def _build_approved_items(staging_manifest: Dict[str, Any]) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    for raw in staging_manifest.get("staged_items") or []:
        if not isinstance(raw, dict):
            continue
        items.append(
            {
                "candidate_id": raw.get("candidate_id"),
                "decision_id": raw.get("decision_id"),
                "decision_type": raw.get("decision_type"),
                "source_type": raw.get("source_type"),
                "promoted_text": raw.get("promoted_text"),
                "promoted_text_sha256": raw.get("promoted_text_sha256"),
                "ready_for_live_memory_write": bool(
                    raw.get("ready_for_live_memory_write")
                ),
                "live_memory_written": bool(raw.get("live_memory_written")),
                "live_vector_db_written": bool(raw.get("live_vector_db_written")),
            }
        )
    return items


def _build_packet(workspace: Path, *, workspace_preserved: bool) -> FinalPromotionReadinessPacketReport:
    errors: List[str] = []
    report = FinalPromotionReadinessPacketReport(
        verdict="FAIL",
        workspace=str(workspace.resolve()),
        workspace_preserved=workspace_preserved,
        autonomy_enabled=_read_autonomy_enabled(),
        operator_next_steps=list(OPERATOR_NEXT_STEPS),
        live_write_blocked_reason=LIVE_WRITE_DENIAL_REASON,
        vector_db_write_blocked_reason=VECTOR_WRITE_DENIAL_REASON,
    )
    if report.autonomy_enabled:
        errors.append("autonomy_enabled: config/autonomy.json enabled is not false")
        report.errors = errors
        return report

    blockade_tamper = (
        run_memory_review_approved_promotion_live_write_blockade_tamper_evidence_smoke(
            base_dir=workspace,
            keep_temp=True,
        )
    )
    if blockade_tamper.verdict != "PASS":
        errors.append(
            "live_write_blockade_tamper_evidence_failed: "
            + "; ".join(blockade_tamper.errors)
        )

    blockade_report_path = Path(blockade_tamper.clean_blockade_report_path)
    staging_manifest_path = Path(
        blockade_tamper.artifact_paths.get("clean_source_staging_manifest", "")
    )
    if not _require_file(blockade_report_path, "live_write_blockade_report", errors):
        report.errors = errors
        return report
    if not _require_file(staging_manifest_path, "staging_manifest", errors):
        report.errors = errors
        return report

    blockade_report = _load_json(blockade_report_path)
    staging_manifest = _load_json(staging_manifest_path)
    staging_audit_verdict, staging_audit_errors = audit_operator_approved_staging_manifest(
        staging_manifest_path
    )

    bundle_dir = workspace / "approved_promotion_bundle"
    bundle_readme = bundle_dir / "README.md"
    promotion_manifest = bundle_dir / "promotion_manifest.json"
    handoff_path = (
        workspace / "approved_promotion_operator_handoff" / "operator_handoff.json"
    )
    gate_path = (
        workspace
        / "approved_promotion_operator_approval_gate"
        / "operator_approval_gate.json"
    )
    promotion_tamper_dir = workspace / "approved_promotion_tamper_evidence"

    for path, label in (
        (bundle_dir, "promotion_bundle_dir"),
        (bundle_readme, "promotion_bundle_readme"),
        (promotion_manifest, "promotion_manifest"),
        (handoff_path, "operator_handoff"),
        (gate_path, "operator_approval_gate"),
    ):
        if label.endswith("_dir"):
            if not path.is_dir():
                errors.append(f"missing_{label}: {path}")
        else:
            _require_file(path, label, errors)

    staging_receipt_path = workspace / STAGING_RECEIPT_DIRNAME / STAGING_RECEIPT_FILENAME
    _write_json(
        staging_receipt_path,
        {
            "verdict": staging_audit_verdict,
            "source_staging_manifest_path": str(staging_manifest_path.resolve()),
            "source_staging_tamper_evidence_verdict": blockade_report.get(
                "source_staging_tamper_evidence_verdict"
            ),
            "errors": staging_audit_errors,
            "dry_run": True,
            "local_only": True,
            "live_memory_written": False,
            "live_vector_db_written": False,
        },
    )
    blockade_tamper_path = workspace / BLOCKADE_TAMPER_DIRNAME / BLOCKADE_TAMPER_FILENAME
    _write_json(blockade_tamper_path, blockade_tamper.to_dict())

    approved_items = _build_approved_items(staging_manifest)
    decision_types = [str(item.get("decision_type") or "") for item in approved_items]
    promoted_texts = [str(item.get("promoted_text") or "") for item in approved_items]
    approved_included = "approved" in decision_types
    edited_included = "edited" in decision_types
    edited_text_preserved = any(EDITED_TEXT_MARKER in text for text in promoted_texts)
    rejected_excluded = "rejected" not in decision_types
    excluded_rejected = int(blockade_report.get("excluded_rejected_count") or 0)

    safety_chain = {
        "promotion_bundle": (
            "PASS" if promotion_manifest.is_file() and bundle_readme.is_file() else "FAIL"
        ),
        "promotion_tamper_evidence": (
            "PASS"
            if str(blockade_report.get("tamper_evidence_verdict")) == "PASS"
            and promotion_tamper_dir.is_dir()
            else "FAIL"
        ),
        "operator_handoff": "PASS" if handoff_path.is_file() else "FAIL",
        "operator_approval_gate": (
            "PASS"
            if str(blockade_report.get("approval_gate_verdict")) == "PASS"
            and gate_path.is_file()
            else "FAIL"
        ),
        "operator_approved_staging": (
            "PASS" if bool(blockade_report.get("clean_staging_valid")) else "FAIL"
        ),
        "staging_tamper_evidence": (
            "PASS"
            if staging_audit_verdict == "PASS"
            and str(blockade_report.get("source_staging_tamper_evidence_verdict"))
            == "PASS"
            else "FAIL"
        ),
        "live_write_blockade": (
            "PASS" if str(blockade_report.get("verdict")) == "PASS" else "FAIL"
        ),
        "live_write_blockade_tamper_evidence": (
            "PASS"
            if blockade_tamper.verdict == "PASS"
            and blockade_tamper.all_tamper_cases_detected
            else "FAIL"
        ),
    }

    report.source_bundle_path = str(bundle_dir.resolve()) if bundle_dir.is_dir() else ""
    report.source_bundle_sha256 = _sha256_file(bundle_readme) if bundle_readme.is_file() else ""
    report.source_promotion_manifest_sha256 = (
        _sha256_file(promotion_manifest) if promotion_manifest.is_file() else ""
    )
    report.source_operator_handoff_sha256 = (
        _sha256_file(handoff_path) if handoff_path.is_file() else ""
    )
    report.source_approval_gate_sha256 = _sha256_file(gate_path) if gate_path.is_file() else ""
    report.source_staging_manifest_sha256 = _sha256_file(staging_manifest_path)
    report.source_staging_tamper_evidence_sha256 = _sha256_file(staging_receipt_path)
    report.source_live_write_blockade_sha256 = _sha256_file(blockade_report_path)
    report.source_live_write_blockade_tamper_evidence_sha256 = _sha256_file(
        blockade_tamper_path
    )
    report.approval_token_phrase = APPROVAL_TOKEN_PHRASE
    report.promotion_item_count = int(blockade_report.get("promotion_item_count") or 0)
    report.approved_candidate_count = int(
        blockade_report.get("approved_candidate_count") or 0
    )
    report.edited_candidate_count = int(blockade_report.get("edited_candidate_count") or 0)
    report.excluded_rejected_count = excluded_rejected
    report.ready_for_operator_review = True
    report.ready_for_operator_approved_staging = bool(
        blockade_report.get("ready_for_operator_approved_staging")
    )
    report.ready_for_live_memory_write = False
    report.future_live_write_allowed = False
    report.requires_explicit_operator_approval = True
    report.requires_future_live_write_milestone = True
    report.approved_items = approved_items
    report.safety_chain = safety_chain

    hash_fields = (
        report.source_bundle_sha256,
        report.source_promotion_manifest_sha256,
        report.source_operator_handoff_sha256,
        report.source_approval_gate_sha256,
        report.source_staging_manifest_sha256,
        report.source_staging_tamper_evidence_sha256,
        report.source_live_write_blockade_sha256,
        report.source_live_write_blockade_tamper_evidence_sha256,
    )
    if any(len(value) != 64 for value in hash_fields):
        errors.append("missing_or_invalid_source_hash")
    if not approved_included:
        errors.append("approved_item_missing")
    if not edited_included:
        errors.append("edited_item_missing")
    if not edited_text_preserved:
        errors.append("edited_promoted_text_not_preserved")
    if not rejected_excluded:
        errors.append("rejected_item_included")
    if report.promotion_item_count != 2:
        errors.append(f"promotion_item_count={report.promotion_item_count}")
    if report.excluded_rejected_count != 1:
        errors.append(f"excluded_rejected_count={report.excluded_rejected_count}")
    if report.ready_for_operator_approved_staging is not True:
        errors.append("ready_for_operator_approved_staging is not true")
    if any(value != "PASS" for value in safety_chain.values()):
        missing = [name for name, value in safety_chain.items() if value != "PASS"]
        errors.append("safety_chain_failed: " + ", ".join(missing))
    if bool(blockade_report.get("ready_for_live_memory_write")):
        errors.append("ready_for_live_memory_write=true")
    if bool(blockade_report.get("future_live_write_allowed")):
        errors.append("future_live_write_allowed=true")
    if not report.live_write_blocked_reason.strip():
        errors.append("missing_live_write_blocked_reason")
    if not report.vector_db_write_blocked_reason.strip():
        errors.append("missing_vector_db_write_blocked_reason")
    if report.operator_next_steps != list(OPERATOR_NEXT_STEPS):
        errors.append("operator_next_steps_mismatch")

    packet_dir = workspace / PACKET_DIRNAME
    packet_json_path = packet_dir / PACKET_JSON_FILENAME
    packet_readme_path = packet_dir / PACKET_README_FILENAME
    report.packet_path = str(packet_dir.resolve())
    report.packet_json_path = str(packet_json_path.resolve())
    report.packet_readme_path = str(packet_readme_path.resolve())
    report.verdict = "PASS" if not errors else "FAIL"
    report.errors = errors
    report.packet_readme_sha256 = _write_readme(packet_readme_path, report)
    _write_json(packet_json_path, report.to_packet_dict())
    try:
        loaded = _load_json(packet_json_path)
        report.packet_json_valid = isinstance(loaded, dict) and loaded.get("verdict") == report.verdict
    except json.JSONDecodeError:
        report.packet_json_valid = False
        errors.append("packet_json_invalid")
        report.errors = errors
        report.verdict = "FAIL"
        _write_json(packet_json_path, report.to_packet_dict())

    if not _path_inside_workspace(packet_dir, workspace):
        errors.append("packet_path_outside_workspace")
        report.errors = errors
        report.verdict = "FAIL"

    report.artifact_paths = {
        "packet_dir": report.packet_path,
        "packet_json": report.packet_json_path,
        "packet_readme": report.packet_readme_path,
        "source_bundle": report.source_bundle_path,
        "source_promotion_manifest": str(promotion_manifest.resolve())
        if promotion_manifest.is_file()
        else "",
        "source_operator_handoff": str(handoff_path.resolve()) if handoff_path.is_file() else "",
        "source_approval_gate": str(gate_path.resolve()) if gate_path.is_file() else "",
        "source_staging_manifest": str(staging_manifest_path.resolve()),
        "source_staging_tamper_receipt": str(staging_receipt_path.resolve()),
        "source_live_write_blockade": str(blockade_report_path.resolve()),
        "source_live_write_blockade_tamper": str(blockade_tamper_path.resolve()),
    }
    return report


def run_memory_review_approved_promotion_final_readiness_packet_smoke(
    *,
    base_dir: Path | None = None,
    keep_temp: bool = False,
) -> FinalPromotionReadinessPacketReport:
    """Build the dry-run final approved-promotion readiness packet."""
    owned_temp = base_dir is None
    workspace = (
        Path(tempfile.mkdtemp(prefix="elysia_frp_"))
        if owned_temp
        else _reject_dangerous_base(Path(base_dir))
    )
    workspace.mkdir(parents=True, exist_ok=True)
    try:
        report = _build_packet(
            workspace,
            workspace_preserved=(not owned_temp) or keep_temp,
        )
        report.workspace_preserved = (not owned_temp) or keep_temp
        return report
    finally:
        if owned_temp and not keep_temp:
            shutil.rmtree(workspace, ignore_errors=True)


def format_operator_summary(report: FinalPromotionReadinessPacketReport) -> str:
    lines = [
        "Memory review approved promotion final readiness packet smoke",
        "=" * 64,
        f"Verdict: {report.verdict}",
        f"Workspace: {report.workspace}",
        f"Packet path: {report.packet_path}",
        f"Packet JSON valid: {report.packet_json_valid}",
        f"Promotion item count: {report.promotion_item_count}",
        f"Excluded rejected count: {report.excluded_rejected_count}",
        f"Ready for live memory write: {report.ready_for_live_memory_write}",
        f"Future live write allowed: {report.future_live_write_allowed}",
        "",
        "Safety chain:",
    ]
    for stage in REQUIRED_SAFETY_CHAIN_STAGES:
        lines.append(f"  {stage}: {report.safety_chain.get(stage, 'UNKNOWN')}")
    lines.extend(
        [
            "",
            "Safety:",
            f"  dry_run: {report.dry_run}",
            f"  local_only: {report.local_only}",
            f"  model_called: {report.model_called}",
            f"  embeddings_used: {report.embeddings_used}",
            f"  live_memory_written: {report.live_memory_written}",
            f"  live_vector_db_written: {report.live_vector_db_written}",
            f"  account_api_network_accessed: {report.account_api_network_accessed}",
            f"  autonomy_enabled: {report.autonomy_enabled}",
        ]
    )
    if report.errors:
        lines.extend(["", "Errors:"])
        lines.extend(f"  - {error}" for error in report.errors)
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Run local-only Memory review approved promotion final readiness "
            "packet smoke."
        ),
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON to stdout")
    parser.add_argument("--base-dir", type=Path, default=None)
    parser.add_argument("--keep-temp", action="store_true")
    args = parser.parse_args(argv)
    try:
        report = run_memory_review_approved_promotion_final_readiness_packet_smoke(
            base_dir=args.base_dir,
            keep_temp=args.keep_temp,
        )
    except ValueError as exc:
        report = FinalPromotionReadinessPacketReport(
            verdict="FAIL",
            workspace=str(args.base_dir or ""),
            errors=[str(exc)],
            autonomy_enabled=_read_autonomy_enabled(),
        )
    if args.json:
        print(json.dumps(report.to_dict(), indent=2))
    else:
        print(format_operator_summary(report))
    return 0 if report.verdict == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
