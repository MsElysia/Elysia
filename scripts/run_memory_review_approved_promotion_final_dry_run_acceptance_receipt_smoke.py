#!/usr/bin/env python3
"""Dry-run/local smoke writing a final dry-run acceptance receipt.

This smoke rebuilds the verified final-readiness packet, packet tamper
evidence, operator acceptance gate, and acceptance-gate tamper evidence in a
temporary workspace, then writes a local receipt proving the operator accepted
the final dry-run readiness packet only. It never authorizes live memory
writes, vector DB writes, or live-write design, and never calls models,
embeddings, networks, live accounts, or UI routes.
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

from run_memory_review_approved_promotion_final_readiness_operator_acceptance_gate_smoke import (  # noqa: E402
    ACCEPTANCE_PHRASE,
    LIVE_WRITE_BLOCKED_REASON,
    VECTOR_WRITE_BLOCKED_REASON,
)
from run_memory_review_approved_promotion_final_readiness_operator_acceptance_gate_tamper_evidence_smoke import (  # noqa: E402
    run_memory_review_approved_promotion_final_readiness_operator_acceptance_gate_tamper_evidence_smoke,
)

RECEIPT_DIRNAME = "approved_promotion_final_dry_run_acceptance_receipt"
RECEIPT_JSON_FILENAME = "final_dry_run_acceptance_receipt.json"
RECEIPT_README_FILENAME = "FINAL_DRY_RUN_ACCEPTANCE_RECEIPT.md"
GATE_TAMPER_DIRNAME = (
    "approved_promotion_final_readiness_operator_acceptance_gate_tamper_evidence"
)
GATE_TAMPER_FILENAME = "operator_acceptance_gate_tamper_evidence.json"

ACCEPTED_CHECKPOINT_TAG = (
    "memory_review_approved_promotion_final_readiness_operator_acceptance_gate_tamper_evidence_clean_1"
)
ACCEPTED_CHECKPOINT_HASH = "a6ceaf4d944751c665ecbdc32a6d4c9d0c862949"
ACCEPTED_CHECKPOINT_MESSAGE = (
    "feat(local): add approved promotion final acceptance gate tamper evidence"
)

OPERATOR_NEXT_STEPS = [
    "Final dry-run readiness is accepted.",
    "Live memory writes remain blocked.",
    "Vector DB writes remain blocked.",
    "Future live-write design requires a separate explicit campaign.",
    (
        "Future live-write implementation requires a separate explicit "
        "campaign after design approval."
    ),
]

REQUIRED_RECEIPT_FIELDS = (
    "verdict",
    "workspace",
    "receipt_path",
    "receipt_json_path",
    "receipt_json_valid",
    "receipt_readme_path",
    "receipt_readme_sha256",
    "operator_acceptance_phrase",
    "operator_acceptance_phrase_valid",
    "accepted_checkpoint_tag",
    "accepted_checkpoint_hash",
    "accepted_checkpoint_message",
    "source_final_readiness_packet_sha256",
    "source_final_readiness_packet_tamper_evidence_sha256",
    "source_operator_acceptance_gate_sha256",
    "source_operator_acceptance_gate_tamper_evidence_sha256",
    "final_readiness_packet_verdict",
    "final_readiness_packet_tamper_evidence_verdict",
    "operator_acceptance_gate_verdict",
    "operator_acceptance_gate_tamper_evidence_verdict",
    "accepted_for_final_dry_run_readiness",
    "accepted_for_live_memory_write",
    "accepted_for_vector_db_write",
    "ready_for_future_live_write_design",
    "requires_separate_live_write_campaign",
    "requires_separate_operator_approval_for_live_write",
    "live_memory_write_allowed",
    "vector_db_write_allowed",
    "live_write_blocked_reason",
    "vector_db_write_blocked_reason",
    "operator_next_steps",
    "dry_run",
    "local_only",
    "model_called",
    "embeddings_used",
    "live_memory_written",
    "live_vector_db_written",
    "account_api_network_accessed",
    "autonomy_enabled",
    "errors",
)


@dataclass
class FinalDryRunAcceptanceReceiptReport:
    verdict: str
    workspace: str
    receipt_path: str = ""
    receipt_json_path: str = ""
    receipt_json_valid: bool = False
    receipt_readme_path: str = ""
    receipt_readme_sha256: str = ""
    operator_acceptance_phrase: str = ACCEPTANCE_PHRASE
    operator_acceptance_phrase_valid: bool = False
    accepted_checkpoint_tag: str = ACCEPTED_CHECKPOINT_TAG
    accepted_checkpoint_hash: str = ACCEPTED_CHECKPOINT_HASH
    accepted_checkpoint_message: str = ACCEPTED_CHECKPOINT_MESSAGE
    source_final_readiness_packet_sha256: str = ""
    source_final_readiness_packet_tamper_evidence_sha256: str = ""
    source_operator_acceptance_gate_sha256: str = ""
    source_operator_acceptance_gate_tamper_evidence_sha256: str = ""
    final_readiness_packet_verdict: str = "UNKNOWN"
    final_readiness_packet_tamper_evidence_verdict: str = "UNKNOWN"
    operator_acceptance_gate_verdict: str = "UNKNOWN"
    operator_acceptance_gate_tamper_evidence_verdict: str = "UNKNOWN"
    accepted_for_final_dry_run_readiness: bool = False
    accepted_for_live_memory_write: bool = False
    accepted_for_vector_db_write: bool = False
    ready_for_future_live_write_design: bool = False
    requires_separate_live_write_campaign: bool = True
    requires_separate_operator_approval_for_live_write: bool = True
    live_memory_write_allowed: bool = False
    vector_db_write_allowed: bool = False
    live_write_blocked_reason: str = LIVE_WRITE_BLOCKED_REASON
    vector_db_write_blocked_reason: str = VECTOR_WRITE_BLOCKED_REASON
    operator_next_steps: List[str] = field(default_factory=lambda: list(OPERATOR_NEXT_STEPS))
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

    def to_receipt_dict(self) -> Dict[str, Any]:
        return {field_name: getattr(self, field_name) for field_name in REQUIRED_RECEIPT_FIELDS}


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


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    digest.update(path.read_bytes())
    return digest.hexdigest()


def _write_json(path: Path, payload: Dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return path


def _load_json(path: Path) -> Dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"JSON root is not an object: {path}")
    return payload


def _write_readme(path: Path, report: FinalDryRunAcceptanceReceiptReport) -> Path:
    lines = [
        "# Final Dry-Run Acceptance Receipt",
        "",
        "Final dry-run readiness acceptance receipt exists. It records",
        f"`{ACCEPTANCE_PHRASE}`. It accepts dry-run readiness only.",
        "",
        "It does not authorize live memory writes. It does not authorize",
        "vector DB writes. It does not authorize live-write design.",
        "Future live-write design requires a separate explicit campaign.",
        "Future live-write implementation requires a separate explicit",
        "campaign after design approval. Models/embeddings/accounts/network",
        "are not called. `elysia/api/server.py`, `project_guardian/core.py`,",
        "and `config/autonomy.json` are untouched.",
        "",
        "## Recorded acceptance",
        "",
        f"- Phrase: `{report.operator_acceptance_phrase}`",
        f"- Phrase valid: `{str(report.operator_acceptance_phrase_valid).lower()}`",
        f"- Accepted checkpoint tag: `{report.accepted_checkpoint_tag}`",
        f"- Accepted checkpoint hash: `{report.accepted_checkpoint_hash}`",
        f"- Accepted checkpoint message: `{report.accepted_checkpoint_message}`",
        "",
        "## Source hashes",
        "",
        f"- Final readiness packet: `{report.source_final_readiness_packet_sha256}`",
        (
            "- Final readiness packet tamper evidence: "
            f"`{report.source_final_readiness_packet_tamper_evidence_sha256}`"
        ),
        f"- Operator acceptance gate: `{report.source_operator_acceptance_gate_sha256}`",
        (
            "- Operator acceptance gate tamper evidence: "
            f"`{report.source_operator_acceptance_gate_tamper_evidence_sha256}`"
        ),
        "",
        "## Authorization",
        "",
        f"- accepted_for_final_dry_run_readiness: `{str(report.accepted_for_final_dry_run_readiness).lower()}`",
        f"- accepted_for_live_memory_write: `{str(report.accepted_for_live_memory_write).lower()}`",
        f"- accepted_for_vector_db_write: `{str(report.accepted_for_vector_db_write).lower()}`",
        f"- ready_for_future_live_write_design: `{str(report.ready_for_future_live_write_design).lower()}`",
        f"- requires_separate_live_write_campaign: `{str(report.requires_separate_live_write_campaign).lower()}`",
        (
            "- requires_separate_operator_approval_for_live_write: "
            f"`{str(report.requires_separate_operator_approval_for_live_write).lower()}`"
        ),
        f"- live_memory_write_allowed: `{str(report.live_memory_write_allowed).lower()}`",
        f"- vector_db_write_allowed: `{str(report.vector_db_write_allowed).lower()}`",
        "",
        "## Operator next steps",
        "",
    ]
    lines.extend(f"- {step}" for step in report.operator_next_steps)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    return path


def _validate_required_values(report: FinalDryRunAcceptanceReceiptReport) -> List[str]:
    errors: List[str] = []
    if report.operator_acceptance_phrase != ACCEPTANCE_PHRASE:
        errors.append("operator_acceptance_phrase is not the required phrase")
    if report.operator_acceptance_phrase_valid is not True:
        errors.append("operator_acceptance_phrase_valid is not true")
    if report.accepted_checkpoint_tag != ACCEPTED_CHECKPOINT_TAG:
        errors.append("accepted_checkpoint_tag is not the required tag")
    if report.accepted_checkpoint_hash != ACCEPTED_CHECKPOINT_HASH:
        errors.append("accepted_checkpoint_hash is not the required hash")
    for field_name in (
        "source_final_readiness_packet_sha256",
        "source_final_readiness_packet_tamper_evidence_sha256",
        "source_operator_acceptance_gate_sha256",
        "source_operator_acceptance_gate_tamper_evidence_sha256",
        "receipt_readme_sha256",
    ):
        value = str(getattr(report, field_name) or "")
        if len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
            errors.append(f"{field_name} is not a sha256 hex digest")
    if report.final_readiness_packet_verdict != "PASS":
        errors.append("final_readiness_packet_verdict is not PASS")
    if report.final_readiness_packet_tamper_evidence_verdict != "PASS":
        errors.append("final_readiness_packet_tamper_evidence_verdict is not PASS")
    if report.operator_acceptance_gate_verdict != "PASS":
        errors.append("operator_acceptance_gate_verdict is not PASS")
    if report.operator_acceptance_gate_tamper_evidence_verdict != "PASS":
        errors.append("operator_acceptance_gate_tamper_evidence_verdict is not PASS")
    if report.accepted_for_final_dry_run_readiness is not True:
        errors.append("accepted_for_final_dry_run_readiness is not true")
    if report.accepted_for_live_memory_write is not False:
        errors.append("accepted_for_live_memory_write is not false")
    if report.accepted_for_vector_db_write is not False:
        errors.append("accepted_for_vector_db_write is not false")
    if report.ready_for_future_live_write_design is not False:
        errors.append("ready_for_future_live_write_design is not false")
    if report.requires_separate_live_write_campaign is not True:
        errors.append("requires_separate_live_write_campaign is not true")
    if report.requires_separate_operator_approval_for_live_write is not True:
        errors.append("requires_separate_operator_approval_for_live_write is not true")
    if report.live_memory_write_allowed is not False:
        errors.append("live_memory_write_allowed is not false")
    if report.vector_db_write_allowed is not False:
        errors.append("vector_db_write_allowed is not false")
    if not report.live_write_blocked_reason:
        errors.append("live_write_blocked_reason is missing")
    if not report.vector_db_write_blocked_reason:
        errors.append("vector_db_write_blocked_reason is missing")
    joined_steps = " ".join(report.operator_next_steps).lower()
    for marker in (
        "final dry-run readiness is accepted",
        "live memory writes remain blocked",
        "vector db writes remain blocked",
        "future live-write design requires a separate explicit campaign",
        "future live-write implementation requires a separate explicit campaign after design approval",
    ):
        if marker not in joined_steps:
            errors.append(f"operator_next_steps missing: {marker}")
    if report.dry_run is not True:
        errors.append("dry_run is not true")
    if report.local_only is not True:
        errors.append("local_only is not true")
    for field_name in (
        "model_called",
        "embeddings_used",
        "live_memory_written",
        "live_vector_db_written",
        "account_api_network_accessed",
        "autonomy_enabled",
    ):
        if getattr(report, field_name) is not False:
            errors.append(f"{field_name} is not false")
    return errors


def _build_receipt(
    workspace: Path,
    *,
    workspace_preserved: bool,
) -> FinalDryRunAcceptanceReceiptReport:
    report = FinalDryRunAcceptanceReceiptReport(
        verdict="FAIL",
        workspace=str(workspace.resolve()),
        workspace_preserved=workspace_preserved,
        autonomy_enabled=_read_autonomy_enabled(),
    )
    if report.autonomy_enabled:
        report.errors.append(
            "Autonomy is enabled; final dry-run acceptance receipt smoke is blocked."
        )
        return report

    tamper_report = (
        run_memory_review_approved_promotion_final_readiness_operator_acceptance_gate_tamper_evidence_smoke(
            base_dir=workspace,
            keep_temp=True,
        )
    )
    report.operator_acceptance_gate_tamper_evidence_verdict = tamper_report.verdict
    report.operator_acceptance_gate_verdict = tamper_report.clean_gate_verdict
    if tamper_report.verdict != "PASS":
        report.errors.append(
            "Operator acceptance gate tamper evidence smoke did not pass: "
            + "; ".join(tamper_report.errors)
        )
        return report
    if tamper_report.clean_gate_verdict != "PASS":
        report.errors.append("Clean operator acceptance gate report did not pass.")
        return report

    gate_report_path = Path(tamper_report.clean_gate_report_path)
    if not gate_report_path.is_file():
        report.errors.append(f"missing_gate_report: {gate_report_path}")
        return report
    gate_report = _load_json(gate_report_path)
    report.final_readiness_packet_verdict = str(
        gate_report.get("clean_packet_verdict") or "UNKNOWN"
    )
    report.final_readiness_packet_tamper_evidence_verdict = str(
        gate_report.get("packet_tamper_evidence_verdict") or "UNKNOWN"
    )
    if report.final_readiness_packet_verdict != "PASS":
        report.errors.append("Final readiness packet did not pass.")
        return report
    if report.final_readiness_packet_tamper_evidence_verdict != "PASS":
        report.errors.append("Final readiness packet tamper evidence did not pass.")
        return report

    packet_path = Path(str(gate_report.get("source_final_readiness_packet_path") or ""))
    packet_tamper_path = Path(
        str(gate_report.get("source_final_readiness_tamper_evidence_path") or "")
    )
    if not packet_path.is_file():
        report.errors.append(f"missing_packet: {packet_path}")
        return report
    if not packet_tamper_path.is_file():
        report.errors.append(f"missing_packet_tamper: {packet_tamper_path}")
        return report

    gate_tamper_path = workspace / GATE_TAMPER_DIRNAME / GATE_TAMPER_FILENAME
    _write_json(gate_tamper_path, tamper_report.to_dict())

    report.source_final_readiness_packet_sha256 = _sha256_file(packet_path)
    report.source_final_readiness_packet_tamper_evidence_sha256 = _sha256_file(
        packet_tamper_path
    )
    report.source_operator_acceptance_gate_sha256 = _sha256_file(gate_report_path)
    report.source_operator_acceptance_gate_tamper_evidence_sha256 = _sha256_file(
        gate_tamper_path
    )

    report.operator_acceptance_phrase = ACCEPTANCE_PHRASE
    report.operator_acceptance_phrase_valid = True
    report.accepted_checkpoint_tag = ACCEPTED_CHECKPOINT_TAG
    report.accepted_checkpoint_hash = ACCEPTED_CHECKPOINT_HASH
    report.accepted_checkpoint_message = ACCEPTED_CHECKPOINT_MESSAGE
    report.accepted_for_final_dry_run_readiness = True
    report.accepted_for_live_memory_write = False
    report.accepted_for_vector_db_write = False
    report.ready_for_future_live_write_design = False
    report.requires_separate_live_write_campaign = True
    report.requires_separate_operator_approval_for_live_write = True
    report.live_memory_write_allowed = False
    report.vector_db_write_allowed = False
    report.live_write_blocked_reason = str(
        gate_report.get("live_write_blocked_reason") or LIVE_WRITE_BLOCKED_REASON
    )
    report.vector_db_write_blocked_reason = str(
        gate_report.get("vector_db_write_blocked_reason") or VECTOR_WRITE_BLOCKED_REASON
    )
    report.operator_next_steps = list(OPERATOR_NEXT_STEPS)

    receipt_dir = workspace / RECEIPT_DIRNAME
    receipt_json_path = receipt_dir / RECEIPT_JSON_FILENAME
    receipt_readme_path = receipt_dir / RECEIPT_README_FILENAME
    report.receipt_path = str(receipt_dir.resolve())
    report.receipt_json_path = str(receipt_json_path.resolve())
    report.receipt_readme_path = str(receipt_readme_path.resolve())
    _write_readme(receipt_readme_path, report)
    report.receipt_readme_sha256 = _sha256_file(receipt_readme_path)

    validation_errors = _validate_required_values(report)
    report.errors = validation_errors
    report.verdict = "PASS" if not validation_errors else "FAIL"

    _write_json(receipt_json_path, report.to_receipt_dict())
    try:
        loaded = _load_json(receipt_json_path)
        report.receipt_json_valid = isinstance(loaded, dict) and loaded.get("verdict") == report.verdict
        missing_fields = [
            field_name for field_name in REQUIRED_RECEIPT_FIELDS if field_name not in loaded
        ]
        if missing_fields:
            report.receipt_json_valid = False
            report.errors.append("receipt missing fields: " + ", ".join(missing_fields))
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        report.receipt_json_valid = False
        report.errors.append(f"receipt_json_invalid: {exc}")
    if not report.receipt_json_valid:
        report.verdict = "FAIL"
        if "receipt JSON is invalid" not in report.errors:
            report.errors.append("receipt JSON is invalid")
    _write_json(receipt_json_path, report.to_receipt_dict())

    report.artifact_paths = {
        "receipt_dir": report.receipt_path,
        "receipt_json": report.receipt_json_path,
        "receipt_readme": report.receipt_readme_path,
        "packet_json": str(packet_path.resolve()),
        "packet_tamper_json": str(packet_tamper_path.resolve()),
        "gate_json": str(gate_report_path.resolve()),
        "gate_tamper_json": str(gate_tamper_path.resolve()),
    }
    return report


def run_memory_review_approved_promotion_final_dry_run_acceptance_receipt_smoke(
    *,
    base_dir: Path | None = None,
    keep_temp: bool = False,
) -> FinalDryRunAcceptanceReceiptReport:
    """Build the dry-run chain and write a local acceptance receipt."""
    owned_temp = base_dir is None
    workspace = (
        Path(tempfile.mkdtemp(prefix="elysia_fdrar_"))
        if owned_temp
        else _reject_dangerous_base(Path(base_dir))
    )
    workspace.mkdir(parents=True, exist_ok=True)
    try:
        try:
            report = _build_receipt(
                workspace,
                workspace_preserved=(not owned_temp) or keep_temp,
            )
        except Exception as exc:
            report = FinalDryRunAcceptanceReceiptReport(
                verdict="FAIL",
                workspace=str(workspace.resolve()),
                workspace_preserved=(not owned_temp) or keep_temp,
                autonomy_enabled=_read_autonomy_enabled(),
                errors=[f"acceptance_receipt_build_failed: {exc}"],
            )
        report.workspace_preserved = (not owned_temp) or keep_temp
        return report
    finally:
        if owned_temp and not keep_temp:
            shutil.rmtree(workspace, ignore_errors=True)


def format_operator_summary(report: FinalDryRunAcceptanceReceiptReport) -> str:
    lines = [
        "Memory review approved promotion final dry-run acceptance receipt smoke",
        "=" * 74,
        f"Verdict: {report.verdict}",
        f"Workspace: {report.workspace}",
        f"Receipt JSON: {report.receipt_json_path}",
        f"Receipt README: {report.receipt_readme_path}",
        f"Phrase: {report.operator_acceptance_phrase}",
        f"Phrase valid: {report.operator_acceptance_phrase_valid}",
        f"Accepted checkpoint: {report.accepted_checkpoint_tag}",
        f"Accepted hash: {report.accepted_checkpoint_hash}",
        f"Accepted for final dry-run readiness: {report.accepted_for_final_dry_run_readiness}",
        f"Live memory write allowed: {report.live_memory_write_allowed}",
        f"Vector DB write allowed: {report.vector_db_write_allowed}",
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
    if report.errors:
        lines.extend(["", "Errors:"])
        lines.extend(f"  - {error}" for error in report.errors)
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Run local-only Memory review approved promotion final dry-run "
            "acceptance receipt smoke."
        ),
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON to stdout")
    parser.add_argument("--base-dir", type=Path, default=None)
    parser.add_argument("--keep-temp", action="store_true")
    args = parser.parse_args(argv)
    try:
        report = run_memory_review_approved_promotion_final_dry_run_acceptance_receipt_smoke(
            base_dir=args.base_dir,
            keep_temp=args.keep_temp,
        )
    except (ValueError, OSError) as exc:
        report = FinalDryRunAcceptanceReceiptReport(
            verdict="FAIL",
            workspace=str(args.base_dir or ""),
            errors=[str(exc)],
            autonomy_enabled=_read_autonomy_enabled(),
        )
    if args.json:
        print(json.dumps(report.to_dict(), indent=2, ensure_ascii=False))
    else:
        print(format_operator_summary(report))
    return 0 if report.verdict == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
