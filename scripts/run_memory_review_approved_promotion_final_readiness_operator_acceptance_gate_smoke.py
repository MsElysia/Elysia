#!/usr/bin/env python3
"""Dry-run/local smoke proving final readiness needs explicit operator acceptance.

This smoke rebuilds a valid final readiness packet and its tamper evidence,
then requires a separate local acceptance artifact before the packet can be
treated as operator-accepted dry-run readiness. Missing, invalid, or
mismatched acceptance fails closed. Valid acceptance accepts final dry-run
readiness only. It never authorizes live memory writes, vector DB writes,
future live-write design, models, embeddings, networks, live accounts, UI
routes, or background work.
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
from typing import Any, Dict, List, Sequence, Tuple

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from run_memory_review_approved_promotion_final_readiness_packet_tamper_evidence_smoke import (  # noqa: E402
    run_memory_review_approved_promotion_final_readiness_packet_tamper_evidence_smoke,
)

GATE_DIRNAME = "approved_promotion_final_readiness_operator_acceptance_gate"
GATE_REPORT_FILENAME = "operator_acceptance_gate.json"
GATE_README_FILENAME = "OPERATOR_ACCEPTANCE_GATE_README.md"
ACCEPTANCE_ARTIFACT_FILENAME = "operator_acceptance.json"
TAMPER_EVIDENCE_DIRNAME = "approved_promotion_final_readiness_packet_tamper_evidence"
TAMPER_EVIDENCE_FILENAME = "final_readiness_packet_tamper_evidence.json"
ACCEPTANCE_PHRASE = "ACCEPT_FINAL_DRY_RUN_READINESS_PACKET_ONLY"

REQUIRED_ACCEPTANCE_CASES = (
    "missing_acceptance_artifact",
    "invalid_acceptance_phrase",
    "mismatched_packet_hash",
    "mismatched_tamper_evidence_hash",
    "tamper_evidence_not_pass",
    "acceptance_claims_live_memory_write",
    "acceptance_claims_vector_db_write",
    "valid_final_dry_run_acceptance",
)
INVALID_ACCEPTANCE_CASES = REQUIRED_ACCEPTANCE_CASES[:-1]

LIVE_WRITE_BLOCKED_REASON = (
    "Live memory write remains blocked. Operator acceptance of the final "
    "dry-run readiness packet does not authorize live memory writes. A "
    "separate explicit live-write campaign is required before any live "
    "memory write path may exist."
)
VECTOR_WRITE_BLOCKED_REASON = (
    "Vector DB write remains blocked. Operator acceptance of the final "
    "dry-run readiness packet does not authorize vector DB writes. A "
    "separate explicit live-write campaign is required before any vector "
    "DB write path may exist."
)


@dataclass
class AcceptanceCaseResult:
    case_name: str
    expected_verdict: str
    actual_verdict: str
    detected: bool
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class FinalReadinessOperatorAcceptanceGateReport:
    verdict: str
    workspace: str
    gate_path: str = ""
    gate_report_path: str = ""
    gate_report_valid_json: bool = False
    acceptance_phrase: str = ACCEPTANCE_PHRASE
    acceptance_phrase_valid: bool = False
    acceptance_artifact_present: bool = False
    acceptance_artifact_sha256: str = ""
    source_final_readiness_packet_path: str = ""
    source_final_readiness_packet_sha256: str = ""
    source_final_readiness_tamper_evidence_path: str = ""
    source_final_readiness_tamper_evidence_sha256: str = ""
    packet_tamper_evidence_verdict: str = "UNKNOWN"
    clean_packet_verdict: str = "UNKNOWN"
    operator_acceptance_valid: bool = False
    accepted_for_final_dry_run_readiness: bool = False
    accepted_for_live_memory_write: bool = False
    accepted_for_vector_db_write: bool = False
    ready_for_future_live_write_design: bool = False
    requires_separate_live_write_campaign: bool = True
    live_memory_write_allowed: bool = False
    vector_db_write_allowed: bool = False
    live_write_blocked_reason: str = LIVE_WRITE_BLOCKED_REASON
    vector_db_write_blocked_reason: str = VECTOR_WRITE_BLOCKED_REASON
    acceptance_cases: List[Dict[str, Any]] = field(default_factory=list)
    acceptance_case_count: int = 0
    all_invalid_acceptance_cases_failed_closed: bool = False
    valid_acceptance_passed_dry_run_only: bool = False
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
    workspace_preserved: bool = False
    gate_readme_path: str = ""
    acceptance_paths_inside_workspace: bool = False
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


def _path_inside_workspace(path: Path, workspace: Path) -> bool:
    try:
        path.resolve().relative_to(workspace.resolve())
        return True
    except ValueError:
        return False


def _load_json(path: Path) -> Dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"JSON file does not contain an object: {path}")
    return payload


def _write_json(path: Path, payload: Dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return path


def _acceptance_payload(
    *,
    packet_sha256: str,
    tamper_sha256: str,
    packet_path: str,
    tamper_path: str,
    phrase: str = ACCEPTANCE_PHRASE,
    accepted_for_final_dry_run_readiness: bool = True,
    accepted_for_live_memory_write: bool = False,
    accepted_for_vector_db_write: bool = False,
    ready_for_future_live_write_design: bool = False,
    requires_separate_live_write_campaign: bool = True,
    live_memory_write_allowed: bool = False,
    vector_db_write_allowed: bool = False,
    dry_run: bool = True,
    local_only: bool = True,
) -> Dict[str, Any]:
    return {
        "acceptance_id": "operator-acceptance-final-dry-run-readiness",
        "acceptance_phrase": phrase,
        "source_final_readiness_packet_path": packet_path,
        "source_final_readiness_packet_sha256": packet_sha256,
        "source_final_readiness_tamper_evidence_path": tamper_path,
        "source_final_readiness_tamper_evidence_sha256": tamper_sha256,
        "accepted_for_final_dry_run_readiness": accepted_for_final_dry_run_readiness,
        "accepted_for_live_memory_write": accepted_for_live_memory_write,
        "accepted_for_vector_db_write": accepted_for_vector_db_write,
        "ready_for_future_live_write_design": ready_for_future_live_write_design,
        "requires_separate_live_write_campaign": requires_separate_live_write_campaign,
        "live_memory_write_allowed": live_memory_write_allowed,
        "vector_db_write_allowed": vector_db_write_allowed,
        "dry_run": dry_run,
        "local_only": local_only,
    }


def _evaluate_acceptance_artifact(
    acceptance_path: Path,
    *,
    expected_packet_sha256: str,
    expected_tamper_sha256: str,
    packet_path: Path,
    tamper_evidence_path: Path,
) -> Tuple[str, List[str]]:
    errors: List[str] = []
    if not acceptance_path.is_file():
        return "FAIL", [f"missing_acceptance_artifact: {acceptance_path}"]

    try:
        acceptance = _load_json(acceptance_path)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        return "FAIL", [f"invalid_acceptance_artifact: {exc}"]

    required_fields = (
        "acceptance_id",
        "acceptance_phrase",
        "source_final_readiness_packet_sha256",
        "source_final_readiness_tamper_evidence_sha256",
        "accepted_for_final_dry_run_readiness",
        "accepted_for_live_memory_write",
        "accepted_for_vector_db_write",
        "ready_for_future_live_write_design",
        "requires_separate_live_write_campaign",
        "live_memory_write_allowed",
        "vector_db_write_allowed",
        "dry_run",
        "local_only",
    )
    missing_fields = [name for name in required_fields if name not in acceptance]
    if missing_fields:
        errors.append("missing_acceptance_field: " + ", ".join(missing_fields))

    if acceptance.get("acceptance_phrase") != ACCEPTANCE_PHRASE:
        errors.append("invalid_acceptance_phrase")

    actual_packet_sha256 = (
        _sha256_file(packet_path) if packet_path.is_file() else ""
    )
    actual_tamper_sha256 = (
        _sha256_file(tamper_evidence_path) if tamper_evidence_path.is_file() else ""
    )
    if (
        acceptance.get("source_final_readiness_packet_sha256") != expected_packet_sha256
        or actual_packet_sha256 != expected_packet_sha256
    ):
        errors.append("mismatched_packet_hash")
    if (
        acceptance.get("source_final_readiness_tamper_evidence_sha256")
        != expected_tamper_sha256
        or actual_tamper_sha256 != expected_tamper_sha256
    ):
        errors.append("mismatched_tamper_evidence_hash")

    tamper_verdict = ""
    if tamper_evidence_path.is_file():
        try:
            tamper_payload = _load_json(tamper_evidence_path)
            tamper_verdict = str(tamper_payload.get("verdict") or "")
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            errors.append(f"invalid_tamper_evidence_artifact: {exc}")
    if tamper_verdict != "PASS":
        errors.append("tamper_evidence_not_pass")

    if acceptance.get("accepted_for_live_memory_write") is True:
        errors.append("acceptance_claims_live_memory_write")
    if acceptance.get("accepted_for_vector_db_write") is True:
        errors.append("acceptance_claims_vector_db_write")
    if acceptance.get("live_memory_write_allowed") is True:
        errors.append("live_memory_write_must_remain_false")
    if acceptance.get("vector_db_write_allowed") is True:
        errors.append("vector_db_write_must_remain_false")
    if acceptance.get("ready_for_future_live_write_design") is True:
        errors.append("future_live_write_design_must_remain_false")
    if acceptance.get("requires_separate_live_write_campaign") is not True:
        errors.append("separate_live_write_campaign_required")
    if acceptance.get("accepted_for_final_dry_run_readiness") is not True:
        errors.append("final_dry_run_readiness_not_accepted")
    if acceptance.get("dry_run") is not True:
        errors.append("dry_run_must_be_true")
    if acceptance.get("local_only") is not True:
        errors.append("local_only_must_be_true")

    for flag_name in (
        "model_called",
        "embeddings_used",
        "live_memory_written",
        "live_vector_db_written",
        "account_api_network_accessed",
        "autonomy_enabled",
    ):
        if acceptance.get(flag_name) is True:
            errors.append(f"{flag_name}_must_remain_false")

    return ("PASS" if not errors else "FAIL"), errors


def _case_result(
    *,
    case_name: str,
    expected_verdict: str,
    acceptance_path: Path,
    expected_packet_sha256: str,
    expected_tamper_sha256: str,
    packet_path: Path,
    tamper_evidence_path: Path,
) -> AcceptanceCaseResult:
    actual_verdict, errors = _evaluate_acceptance_artifact(
        acceptance_path,
        expected_packet_sha256=expected_packet_sha256,
        expected_tamper_sha256=expected_tamper_sha256,
        packet_path=packet_path,
        tamper_evidence_path=tamper_evidence_path,
    )
    valid = actual_verdict == "PASS"
    return AcceptanceCaseResult(
        case_name=case_name,
        expected_verdict=expected_verdict,
        actual_verdict=actual_verdict,
        detected=actual_verdict == expected_verdict,
        details={
            "acceptance_artifact_path": str(acceptance_path.resolve()),
            "operator_acceptance_valid": valid,
            "accepted_for_final_dry_run_readiness": valid,
            "accepted_for_live_memory_write": False,
            "accepted_for_vector_db_write": False,
            "ready_for_future_live_write_design": False,
            "requires_separate_live_write_campaign": True,
            "live_memory_write_allowed": False,
            "vector_db_write_allowed": False,
            "errors": errors,
        },
    )


def _write_readme(
    readme_path: Path,
    report: FinalReadinessOperatorAcceptanceGateReport,
) -> None:
    lines = [
        "# Approved Promotion Final Readiness Operator Acceptance Gate",
        "",
        "This dry-run gate proves that a verified final readiness packet and its",
        "tamper evidence remain blocked until an explicit local operator",
        "acceptance artifact is present, valid, and bound to the current packet",
        "and tamper-evidence hashes.",
        "",
        "## Acceptance phrase",
        "",
        f"`{ACCEPTANCE_PHRASE}`",
        "",
        "The phrase is valid only with:",
        "",
        "- `accepted_for_final_dry_run_readiness`: `true`",
        "- `accepted_for_live_memory_write`: `false`",
        "- `accepted_for_vector_db_write`: `false`",
        "- `ready_for_future_live_write_design`: `false`",
        "- `requires_separate_live_write_campaign`: `true`",
        "- `live_memory_write_allowed`: `false`",
        "- `vector_db_write_allowed`: `false`",
        "- packet and tamper-evidence SHA-256 values matching the current files",
        "- packet tamper evidence verdict `PASS`",
        "",
        "## Fail-closed cases",
        "",
        "- Missing acceptance artifact fails closed.",
        "- Invalid acceptance phrase fails closed.",
        "- Mismatched packet hash fails closed.",
        "- Mismatched tamper-evidence hash fails closed.",
        "- Tamper evidence not PASS fails closed.",
        "- Acceptance claiming live memory write fails closed.",
        "- Acceptance claiming vector DB write fails closed.",
        "",
        "## Safety",
        "",
        "- Valid acceptance only accepts final dry-run readiness.",
        "- Valid acceptance does not authorize live memory writes.",
        "- Valid acceptance does not authorize vector DB writes.",
        "- Future live write still requires a separate explicit campaign.",
        "- Models/embeddings/accounts/network are not called.",
        "- `elysia/api/server.py`, `project_guardian/core.py`, and `config/autonomy.json` remain untouched.",
        "",
        "## Current artifacts",
        "",
        f"- Packet JSON: `{report.source_final_readiness_packet_path}`",
        f"- Packet SHA-256: `{report.source_final_readiness_packet_sha256}`",
        f"- Tamper-evidence JSON: `{report.source_final_readiness_tamper_evidence_path}`",
        f"- Tamper-evidence SHA-256: `{report.source_final_readiness_tamper_evidence_sha256}`",
        f"- Gate JSON: `{report.gate_report_path}`",
        f"- Valid acceptance artifact SHA-256: `{report.acceptance_artifact_sha256}`",
    ]
    readme_path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")


def _build_operator_acceptance_gate(
    workspace: Path,
) -> FinalReadinessOperatorAcceptanceGateReport:
    report = FinalReadinessOperatorAcceptanceGateReport(
        verdict="FAIL",
        workspace=str(workspace.resolve()),
        workspace_preserved=True,
        autonomy_enabled=_read_autonomy_enabled(),
    )
    if report.autonomy_enabled:
        report.errors.append(
            "Autonomy is enabled; final readiness operator acceptance gate smoke is blocked."
        )
        return report

    tamper_report = run_memory_review_approved_promotion_final_readiness_packet_tamper_evidence_smoke(
        base_dir=workspace,
        keep_temp=True,
    )
    report.clean_packet_verdict = tamper_report.clean_packet_verdict
    report.packet_tamper_evidence_verdict = tamper_report.verdict
    if tamper_report.verdict != "PASS":
        report.errors.append(
            "Final readiness packet tamper evidence smoke did not pass: "
            + "; ".join(tamper_report.errors)
        )
        return report
    if report.clean_packet_verdict != "PASS":
        report.errors.append("Clean final readiness packet did not pass.")
        return report

    packet_path = Path(tamper_report.clean_packet_json_path)
    if not packet_path.is_file():
        report.errors.append(f"Clean final readiness packet was not created: {packet_path}")
        return report

    tamper_dir = workspace / TAMPER_EVIDENCE_DIRNAME
    tamper_evidence_path = tamper_dir / TAMPER_EVIDENCE_FILENAME
    _write_json(tamper_evidence_path, tamper_report.to_dict())

    report.source_final_readiness_packet_path = str(packet_path.resolve())
    report.source_final_readiness_packet_sha256 = _sha256_file(packet_path)
    report.source_final_readiness_tamper_evidence_path = str(
        tamper_evidence_path.resolve()
    )
    report.source_final_readiness_tamper_evidence_sha256 = _sha256_file(
        tamper_evidence_path
    )

    gate_dir = workspace / GATE_DIRNAME
    cases_dir = gate_dir / "acceptance_cases"
    gate_dir.mkdir(parents=True, exist_ok=True)
    cases_dir.mkdir(parents=True, exist_ok=True)

    gate_report_path = gate_dir / GATE_REPORT_FILENAME
    readme_path = gate_dir / GATE_README_FILENAME
    valid_acceptance_path = gate_dir / ACCEPTANCE_ARTIFACT_FILENAME
    missing_acceptance_path = cases_dir / "missing_acceptance_artifact.json"
    invalid_phrase_path = cases_dir / "invalid_acceptance_phrase.json"
    mismatched_packet_path = cases_dir / "mismatched_packet_hash.json"
    mismatched_tamper_path = cases_dir / "mismatched_tamper_evidence_hash.json"
    tamper_not_pass_acceptance_path = cases_dir / "tamper_evidence_not_pass.json"
    live_claim_path = cases_dir / "acceptance_claims_live_memory_write.json"
    vector_claim_path = cases_dir / "acceptance_claims_vector_db_write.json"
    fail_tamper_path = cases_dir / "tamper_evidence_not_pass_source.json"

    packet_sha = report.source_final_readiness_packet_sha256
    tamper_sha = report.source_final_readiness_tamper_evidence_sha256
    packet_path_text = report.source_final_readiness_packet_path
    tamper_path_text = report.source_final_readiness_tamper_evidence_path

    _write_json(
        invalid_phrase_path,
        _acceptance_payload(
            packet_sha256=packet_sha,
            tamper_sha256=tamper_sha,
            packet_path=packet_path_text,
            tamper_path=tamper_path_text,
            phrase="INVALID_FINAL_DRY_RUN_READINESS_TOKEN",
        ),
    )
    _write_json(
        mismatched_packet_path,
        _acceptance_payload(
            packet_sha256="0" * 64,
            tamper_sha256=tamper_sha,
            packet_path=packet_path_text,
            tamper_path=tamper_path_text,
        ),
    )
    _write_json(
        mismatched_tamper_path,
        _acceptance_payload(
            packet_sha256=packet_sha,
            tamper_sha256="0" * 64,
            packet_path=packet_path_text,
            tamper_path=tamper_path_text,
        ),
    )
    fail_tamper_payload = tamper_report.to_dict()
    fail_tamper_payload["verdict"] = "FAIL"
    _write_json(fail_tamper_path, fail_tamper_payload)
    fail_tamper_sha = _sha256_file(fail_tamper_path)
    _write_json(
        tamper_not_pass_acceptance_path,
        _acceptance_payload(
            packet_sha256=packet_sha,
            tamper_sha256=fail_tamper_sha,
            packet_path=packet_path_text,
            tamper_path=str(fail_tamper_path.resolve()),
        ),
    )
    _write_json(
        live_claim_path,
        _acceptance_payload(
            packet_sha256=packet_sha,
            tamper_sha256=tamper_sha,
            packet_path=packet_path_text,
            tamper_path=tamper_path_text,
            accepted_for_live_memory_write=True,
        ),
    )
    _write_json(
        vector_claim_path,
        _acceptance_payload(
            packet_sha256=packet_sha,
            tamper_sha256=tamper_sha,
            packet_path=packet_path_text,
            tamper_path=tamper_path_text,
            accepted_for_vector_db_write=True,
        ),
    )
    _write_json(
        valid_acceptance_path,
        _acceptance_payload(
            packet_sha256=packet_sha,
            tamper_sha256=tamper_sha,
            packet_path=packet_path_text,
            tamper_path=tamper_path_text,
        ),
    )

    case_results = [
        _case_result(
            case_name="missing_acceptance_artifact",
            expected_verdict="FAIL",
            acceptance_path=missing_acceptance_path,
            expected_packet_sha256=packet_sha,
            expected_tamper_sha256=tamper_sha,
            packet_path=packet_path,
            tamper_evidence_path=tamper_evidence_path,
        ),
        _case_result(
            case_name="invalid_acceptance_phrase",
            expected_verdict="FAIL",
            acceptance_path=invalid_phrase_path,
            expected_packet_sha256=packet_sha,
            expected_tamper_sha256=tamper_sha,
            packet_path=packet_path,
            tamper_evidence_path=tamper_evidence_path,
        ),
        _case_result(
            case_name="mismatched_packet_hash",
            expected_verdict="FAIL",
            acceptance_path=mismatched_packet_path,
            expected_packet_sha256=packet_sha,
            expected_tamper_sha256=tamper_sha,
            packet_path=packet_path,
            tamper_evidence_path=tamper_evidence_path,
        ),
        _case_result(
            case_name="mismatched_tamper_evidence_hash",
            expected_verdict="FAIL",
            acceptance_path=mismatched_tamper_path,
            expected_packet_sha256=packet_sha,
            expected_tamper_sha256=tamper_sha,
            packet_path=packet_path,
            tamper_evidence_path=tamper_evidence_path,
        ),
        _case_result(
            case_name="tamper_evidence_not_pass",
            expected_verdict="FAIL",
            acceptance_path=tamper_not_pass_acceptance_path,
            expected_packet_sha256=packet_sha,
            expected_tamper_sha256=fail_tamper_sha,
            packet_path=packet_path,
            tamper_evidence_path=fail_tamper_path,
        ),
        _case_result(
            case_name="acceptance_claims_live_memory_write",
            expected_verdict="FAIL",
            acceptance_path=live_claim_path,
            expected_packet_sha256=packet_sha,
            expected_tamper_sha256=tamper_sha,
            packet_path=packet_path,
            tamper_evidence_path=tamper_evidence_path,
        ),
        _case_result(
            case_name="acceptance_claims_vector_db_write",
            expected_verdict="FAIL",
            acceptance_path=vector_claim_path,
            expected_packet_sha256=packet_sha,
            expected_tamper_sha256=tamper_sha,
            packet_path=packet_path,
            tamper_evidence_path=tamper_evidence_path,
        ),
        _case_result(
            case_name="valid_final_dry_run_acceptance",
            expected_verdict="PASS",
            acceptance_path=valid_acceptance_path,
            expected_packet_sha256=packet_sha,
            expected_tamper_sha256=tamper_sha,
            packet_path=packet_path,
            tamper_evidence_path=tamper_evidence_path,
        ),
    ]

    cases_by_name = {case.case_name: case for case in case_results}
    report.gate_path = str(gate_dir.resolve())
    report.gate_report_path = str(gate_report_path.resolve())
    report.gate_readme_path = str(readme_path.resolve())
    report.acceptance_cases = [case.to_dict() for case in case_results]
    report.acceptance_case_count = len(case_results)
    report.acceptance_artifact_present = valid_acceptance_path.is_file()
    report.acceptance_artifact_sha256 = (
        _sha256_file(valid_acceptance_path) if report.acceptance_artifact_present else ""
    )
    report.acceptance_phrase_valid = (
        report.acceptance_artifact_present
        and _load_json(valid_acceptance_path).get("acceptance_phrase") == ACCEPTANCE_PHRASE
    )

    invalid_failed_closed = all(
        cases_by_name[name].actual_verdict == "FAIL" and cases_by_name[name].detected
        for name in INVALID_ACCEPTANCE_CASES
    )
    valid_case = cases_by_name["valid_final_dry_run_acceptance"]
    valid_passed_dry_run_only = (
        valid_case.actual_verdict == "PASS"
        and valid_case.detected
        and valid_case.details["accepted_for_final_dry_run_readiness"] is True
        and valid_case.details["accepted_for_live_memory_write"] is False
        and valid_case.details["accepted_for_vector_db_write"] is False
        and valid_case.details["live_memory_write_allowed"] is False
        and valid_case.details["vector_db_write_allowed"] is False
        and valid_case.details["ready_for_future_live_write_design"] is False
    )
    report.all_invalid_acceptance_cases_failed_closed = invalid_failed_closed
    report.valid_acceptance_passed_dry_run_only = valid_passed_dry_run_only
    report.operator_acceptance_valid = valid_passed_dry_run_only
    report.accepted_for_final_dry_run_readiness = valid_passed_dry_run_only
    report.accepted_for_live_memory_write = False
    report.accepted_for_vector_db_write = False
    report.ready_for_future_live_write_design = False
    report.requires_separate_live_write_campaign = True
    report.live_memory_write_allowed = False
    report.vector_db_write_allowed = False

    tracked_paths = (
        gate_dir,
        cases_dir,
        gate_report_path,
        readme_path,
        valid_acceptance_path,
        missing_acceptance_path,
        invalid_phrase_path,
        mismatched_packet_path,
        mismatched_tamper_path,
        tamper_not_pass_acceptance_path,
        live_claim_path,
        vector_claim_path,
        fail_tamper_path,
        packet_path,
        tamper_evidence_path,
    )
    report.acceptance_paths_inside_workspace = all(
        _path_inside_workspace(path, workspace)
        for path in tracked_paths
        if path.exists() or path == missing_acceptance_path
    )

    report.artifact_paths = {
        "gate_dir": report.gate_path,
        "gate_report": report.gate_report_path,
        "gate_readme": report.gate_readme_path,
        "valid_acceptance_artifact": str(valid_acceptance_path.resolve()),
        "clean_packet_json": report.source_final_readiness_packet_path,
        "tamper_evidence_json": report.source_final_readiness_tamper_evidence_path,
        "missing_acceptance_artifact": str(missing_acceptance_path.resolve()),
        "invalid_acceptance_phrase": str(invalid_phrase_path.resolve()),
        "mismatched_packet_hash": str(mismatched_packet_path.resolve()),
        "mismatched_tamper_evidence_hash": str(mismatched_tamper_path.resolve()),
        "tamper_evidence_not_pass": str(tamper_not_pass_acceptance_path.resolve()),
        "acceptance_claims_live_memory_write": str(live_claim_path.resolve()),
        "acceptance_claims_vector_db_write": str(vector_claim_path.resolve()),
    }

    _write_readme(readme_path, report)

    checks = {
        "clean_packet_pass": report.clean_packet_verdict == "PASS",
        "packet_tamper_evidence_pass": report.packet_tamper_evidence_verdict == "PASS",
        "acceptance_case_count": report.acceptance_case_count == len(REQUIRED_ACCEPTANCE_CASES),
        "all_required_cases_present": {case.case_name for case in case_results}
        == set(REQUIRED_ACCEPTANCE_CASES),
        "all_cases_detected": all(case.detected for case in case_results),
        "all_invalid_acceptance_cases_failed_closed": report.all_invalid_acceptance_cases_failed_closed,
        "valid_acceptance_passed_dry_run_only": report.valid_acceptance_passed_dry_run_only,
        "operator_acceptance_valid": report.operator_acceptance_valid,
        "accepted_for_final_dry_run_readiness": report.accepted_for_final_dry_run_readiness,
        "not_accepted_for_live_memory_write": not report.accepted_for_live_memory_write,
        "not_accepted_for_vector_db_write": not report.accepted_for_vector_db_write,
        "future_live_write_design_blocked": not report.ready_for_future_live_write_design,
        "separate_live_write_campaign_required": report.requires_separate_live_write_campaign,
        "live_memory_write_blocked": not report.live_memory_write_allowed,
        "vector_db_write_blocked": not report.vector_db_write_allowed,
        "live_write_blocked_reason_present": bool(report.live_write_blocked_reason),
        "vector_db_write_blocked_reason_present": bool(report.vector_db_write_blocked_reason),
        "acceptance_phrase_valid": report.acceptance_phrase_valid,
        "acceptance_artifact_present": report.acceptance_artifact_present,
        "packet_hash_present": len(report.source_final_readiness_packet_sha256) == 64,
        "tamper_hash_present": len(report.source_final_readiness_tamper_evidence_sha256)
        == 64,
        "acceptance_paths_inside_workspace": report.acceptance_paths_inside_workspace,
        "readme_created": readme_path.is_file(),
    }
    for check_name, passed in checks.items():
        if not passed:
            report.errors.append(f"{check_name} failed")

    for flag_name in (
        "model_called",
        "embeddings_used",
        "live_memory_written",
        "live_vector_db_written",
        "account_api_network_accessed",
        "autonomy_enabled",
    ):
        if getattr(report, flag_name):
            report.errors.append(f"{flag_name} unexpectedly true.")

    report.verdict = "PASS" if not report.errors else "FAIL"
    _write_json(gate_report_path, report.to_dict())
    try:
        loaded_report = _load_json(gate_report_path)
        report.gate_report_valid_json = isinstance(loaded_report, dict)
    except (OSError, json.JSONDecodeError, ValueError):
        report.gate_report_valid_json = False
    if not report.gate_report_valid_json:
        report.errors.append("Operator acceptance gate JSON is invalid.")
        report.verdict = "FAIL"
    _write_json(gate_report_path, report.to_dict())
    return report


def run_memory_review_approved_promotion_final_readiness_operator_acceptance_gate_smoke(
    *,
    base_dir: Path | None = None,
    keep_temp: bool = False,
) -> FinalReadinessOperatorAcceptanceGateReport:
    """Build and validate a dry-run final readiness operator acceptance gate."""
    owned_temp = base_dir is None
    workspace = (
        Path(tempfile.mkdtemp(prefix="elysia_fr_accept_gate_"))
        if owned_temp
        else _reject_dangerous_base(Path(base_dir))
    )
    workspace.mkdir(parents=True, exist_ok=True)
    try:
        try:
            report = _build_operator_acceptance_gate(workspace)
        except Exception as exc:
            report = FinalReadinessOperatorAcceptanceGateReport(
                verdict="FAIL",
                workspace=str(workspace.resolve()),
                workspace_preserved=(not owned_temp) or keep_temp,
                autonomy_enabled=_read_autonomy_enabled(),
                errors=[f"acceptance_gate_build_failed: {exc}"],
            )
        report.workspace_preserved = (not owned_temp) or keep_temp
        return report
    finally:
        if owned_temp and not keep_temp:
            shutil.rmtree(workspace, ignore_errors=True)


def format_operator_acceptance_gate_summary(
    report: FinalReadinessOperatorAcceptanceGateReport,
) -> str:
    lines = [
        "Memory review approved promotion final readiness operator acceptance gate smoke",
        "=" * 78,
        f"Verdict: {report.verdict}",
        f"Workspace: {report.workspace}",
        f"Workspace preserved: {report.workspace_preserved}",
        f"Gate path: {report.gate_path}",
        f"Gate JSON: {report.gate_report_path}",
        f"Clean packet verdict: {report.clean_packet_verdict}",
        f"Packet tamper evidence verdict: {report.packet_tamper_evidence_verdict}",
        "",
        "Acceptance gate checks:",
        f"  acceptance phrase: {report.acceptance_phrase}",
        f"  acceptance phrase valid: {report.acceptance_phrase_valid}",
        f"  acceptance artifact present: {report.acceptance_artifact_present}",
        f"  acceptance case count: {report.acceptance_case_count}",
        f"  all invalid cases failed closed: {report.all_invalid_acceptance_cases_failed_closed}",
        f"  valid acceptance passed dry-run only: {report.valid_acceptance_passed_dry_run_only}",
        f"  operator_acceptance_valid: {report.operator_acceptance_valid}",
        f"  accepted_for_final_dry_run_readiness: {report.accepted_for_final_dry_run_readiness}",
        f"  accepted_for_live_memory_write: {report.accepted_for_live_memory_write}",
        f"  accepted_for_vector_db_write: {report.accepted_for_vector_db_write}",
        f"  requires_separate_live_write_campaign: {report.requires_separate_live_write_campaign}",
        f"  live_memory_write_allowed: {report.live_memory_write_allowed}",
        f"  vector_db_write_allowed: {report.vector_db_write_allowed}",
        "",
        "Safety:",
        f"  operator_required: {report.operator_required}",
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
            "Run local-only Memory review approved promotion final readiness "
            "operator acceptance gate smoke."
        ),
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
        report = run_memory_review_approved_promotion_final_readiness_operator_acceptance_gate_smoke(
            base_dir=args.base_dir,
            keep_temp=args.keep_temp,
        )
    except (ValueError, OSError) as exc:
        report = FinalReadinessOperatorAcceptanceGateReport(
            verdict="FAIL",
            workspace=str(args.base_dir or ""),
            workspace_preserved=False,
            autonomy_enabled=_read_autonomy_enabled(),
            errors=[str(exc)],
        )

    if args.json:
        print(json.dumps(report.to_dict(), indent=2, ensure_ascii=False))
    else:
        print(format_operator_acceptance_gate_summary(report))
    return 0 if report.verdict == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
