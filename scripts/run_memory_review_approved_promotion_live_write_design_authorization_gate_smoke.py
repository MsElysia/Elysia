#!/usr/bin/env python3
"""Dry-run/local smoke proving live-write design needs an explicit authorization phrase.

This smoke rebuilds a valid final dry-run acceptance receipt and its tamper
evidence, then requires a separate local design-authorization artifact before
a future live-write design proposal may be started. Missing, invalid, or
mismatched authorization fails closed. Valid authorization authorizes
design-proposal work only. It never authorizes live-write implementation,
live memory writes, vector DB writes, models, embeddings, networks, live
accounts, UI routes, or background work.
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

from run_memory_review_approved_promotion_final_dry_run_acceptance_receipt_smoke import (  # noqa: E402
    RECEIPT_DIRNAME,
    RECEIPT_JSON_FILENAME,
)
from run_memory_review_approved_promotion_final_dry_run_acceptance_receipt_tamper_evidence_smoke import (  # noqa: E402
    run_memory_review_approved_promotion_final_dry_run_acceptance_receipt_tamper_evidence_smoke,
)

GATE_DIRNAME = "approved_promotion_live_write_design_authorization_gate"
GATE_REPORT_FILENAME = "live_write_design_authorization_gate.json"
GATE_README_FILENAME = "LIVE_WRITE_DESIGN_AUTHORIZATION_GATE.md"
AUTHORIZATION_ARTIFACT_FILENAME = "live_write_design_authorization.json"
RECEIPT_TAMPER_DIRNAME = (
    "approved_promotion_final_dry_run_acceptance_receipt_tamper_evidence"
)
RECEIPT_TAMPER_FILENAME = "final_dry_run_acceptance_receipt_tamper_evidence.json"
DESIGN_AUTHORIZATION_PHRASE = "AUTHORIZE_LIVE_WRITE_DESIGN_PROPOSAL_ONLY"

REQUIRED_AUTHORIZATION_CASES = (
    "missing_design_authorization_artifact",
    "invalid_design_authorization_phrase",
    "mismatched_receipt_hash",
    "mismatched_receipt_tamper_hash",
    "receipt_not_pass",
    "receipt_tamper_not_pass",
    "authorization_claims_live_write_implementation",
    "authorization_claims_live_memory_write",
    "authorization_claims_vector_db_write",
    "valid_design_proposal_authorization_only",
)
INVALID_AUTHORIZATION_CASES = REQUIRED_AUTHORIZATION_CASES[:-1]


@dataclass
class AuthorizationCaseResult:
    case_name: str
    expected_verdict: str
    actual_verdict: str
    detected: bool
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class LiveWriteDesignAuthorizationGateReport:
    verdict: str
    workspace: str
    gate_path: str = ""
    gate_report_path: str = ""
    gate_report_valid_json: bool = False
    design_authorization_phrase: str = DESIGN_AUTHORIZATION_PHRASE
    design_authorization_phrase_valid: bool = False
    design_authorization_artifact_present: bool = False
    design_authorization_artifact_sha256: str = ""
    source_final_dry_run_acceptance_receipt_path: str = ""
    source_final_dry_run_acceptance_receipt_sha256: str = ""
    source_final_dry_run_acceptance_receipt_tamper_evidence_path: str = ""
    source_final_dry_run_acceptance_receipt_tamper_evidence_sha256: str = ""
    final_dry_run_acceptance_receipt_verdict: str = "UNKNOWN"
    final_dry_run_acceptance_receipt_tamper_evidence_verdict: str = "UNKNOWN"
    accepted_for_final_dry_run_readiness: bool = False
    authorized_for_live_write_design_proposal: bool = False
    authorized_for_live_write_implementation: bool = False
    authorized_for_live_memory_write: bool = False
    authorized_for_vector_db_write: bool = False
    live_memory_write_allowed: bool = False
    vector_db_write_allowed: bool = False
    ready_for_future_live_write_design: bool = False
    requires_separate_live_write_design_campaign: bool = True
    requires_separate_live_write_implementation_campaign: bool = True
    requires_separate_operator_approval_for_live_write: bool = True
    design_authorization_cases: List[Dict[str, Any]] = field(default_factory=list)
    authorization_cases: List[Dict[str, Any]] = field(default_factory=list)
    authorization_case_count: int = 0
    all_invalid_authorization_cases_failed_closed: bool = False
    valid_design_authorization_passed_design_only: bool = False
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
    authorization_paths_inside_workspace: bool = False
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


def _closed_authorization_details(errors: List[str]) -> Dict[str, Any]:
    return {
        "design_authorization_phrase_valid": False,
        "authorized_for_live_write_design_proposal": False,
        "authorized_for_live_write_implementation": False,
        "authorized_for_live_memory_write": False,
        "authorized_for_vector_db_write": False,
        "live_memory_write_allowed": False,
        "vector_db_write_allowed": False,
        "ready_for_future_live_write_design": False,
        "requires_separate_live_write_design_campaign": True,
        "requires_separate_live_write_implementation_campaign": True,
        "requires_separate_operator_approval_for_live_write": True,
        "errors": errors,
    }


def _authorization_payload(
    *,
    receipt_sha256: str,
    tamper_sha256: str,
    receipt_path: str,
    tamper_path: str,
    phrase: str = DESIGN_AUTHORIZATION_PHRASE,
    authorized_for_live_write_design_proposal: bool = True,
    authorized_for_live_write_implementation: bool = False,
    authorized_for_live_memory_write: bool = False,
    authorized_for_vector_db_write: bool = False,
    live_memory_write_allowed: bool = False,
    vector_db_write_allowed: bool = False,
    ready_for_future_live_write_design: bool = True,
    requires_separate_live_write_design_campaign: bool = True,
    requires_separate_live_write_implementation_campaign: bool = True,
    requires_separate_operator_approval_for_live_write: bool = True,
    accepted_for_final_dry_run_readiness: bool = True,
    receipt_verdict: str = "PASS",
    tamper_verdict: str = "PASS",
    dry_run: bool = True,
    local_only: bool = True,
) -> Dict[str, Any]:
    return {
        "authorization_id": "live-write-design-proposal-authorization",
        "design_authorization_phrase": phrase,
        "source_final_dry_run_acceptance_receipt_path": receipt_path,
        "source_final_dry_run_acceptance_receipt_sha256": receipt_sha256,
        "source_final_dry_run_acceptance_receipt_tamper_evidence_path": tamper_path,
        "source_final_dry_run_acceptance_receipt_tamper_evidence_sha256": tamper_sha256,
        "final_dry_run_acceptance_receipt_verdict": receipt_verdict,
        "final_dry_run_acceptance_receipt_tamper_evidence_verdict": tamper_verdict,
        "accepted_for_final_dry_run_readiness": accepted_for_final_dry_run_readiness,
        "authorized_for_live_write_design_proposal": authorized_for_live_write_design_proposal,
        "authorized_for_live_write_implementation": authorized_for_live_write_implementation,
        "authorized_for_live_memory_write": authorized_for_live_memory_write,
        "authorized_for_vector_db_write": authorized_for_vector_db_write,
        "live_memory_write_allowed": live_memory_write_allowed,
        "vector_db_write_allowed": vector_db_write_allowed,
        "ready_for_future_live_write_design": ready_for_future_live_write_design,
        "requires_separate_live_write_design_campaign": requires_separate_live_write_design_campaign,
        "requires_separate_live_write_implementation_campaign": (
            requires_separate_live_write_implementation_campaign
        ),
        "requires_separate_operator_approval_for_live_write": (
            requires_separate_operator_approval_for_live_write
        ),
        "dry_run": dry_run,
        "local_only": local_only,
    }


def _evaluate_authorization_artifact(
    authorization_path: Path,
    *,
    expected_receipt_sha256: str,
    expected_tamper_sha256: str,
    receipt_path: Path,
    tamper_evidence_path: Path,
) -> Tuple[str, List[str]]:
    errors: List[str] = []
    if not authorization_path.is_file():
        return "FAIL", [f"missing_design_authorization_artifact: {authorization_path}"]

    try:
        authorization = _load_json(authorization_path)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        return "FAIL", [f"invalid_design_authorization_artifact: {exc}"]

    required_fields = (
        "authorization_id",
        "design_authorization_phrase",
        "source_final_dry_run_acceptance_receipt_sha256",
        "source_final_dry_run_acceptance_receipt_tamper_evidence_sha256",
        "authorized_for_live_write_design_proposal",
        "authorized_for_live_write_implementation",
        "authorized_for_live_memory_write",
        "authorized_for_vector_db_write",
        "live_memory_write_allowed",
        "vector_db_write_allowed",
        "ready_for_future_live_write_design",
        "requires_separate_live_write_design_campaign",
        "requires_separate_live_write_implementation_campaign",
        "requires_separate_operator_approval_for_live_write",
        "dry_run",
        "local_only",
    )
    missing_fields = [name for name in required_fields if name not in authorization]
    if missing_fields:
        errors.append("missing_authorization_field: " + ", ".join(missing_fields))

    if authorization.get("design_authorization_phrase") != DESIGN_AUTHORIZATION_PHRASE:
        errors.append("invalid_design_authorization_phrase")

    actual_receipt_sha256 = _sha256_file(receipt_path) if receipt_path.is_file() else ""
    actual_tamper_sha256 = (
        _sha256_file(tamper_evidence_path) if tamper_evidence_path.is_file() else ""
    )
    if (
        authorization.get("source_final_dry_run_acceptance_receipt_sha256")
        != expected_receipt_sha256
        or actual_receipt_sha256 != expected_receipt_sha256
    ):
        errors.append("mismatched_receipt_hash")
    if (
        authorization.get("source_final_dry_run_acceptance_receipt_tamper_evidence_sha256")
        != expected_tamper_sha256
        or actual_tamper_sha256 != expected_tamper_sha256
    ):
        errors.append("mismatched_receipt_tamper_hash")

    receipt_verdict = ""
    if receipt_path.is_file():
        try:
            receipt_payload = _load_json(receipt_path)
            receipt_verdict = str(receipt_payload.get("verdict") or "")
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            errors.append(f"invalid_receipt_artifact: {exc}")
    if receipt_verdict != "PASS":
        errors.append("receipt_not_pass")

    tamper_verdict = ""
    if tamper_evidence_path.is_file():
        try:
            tamper_payload = _load_json(tamper_evidence_path)
            tamper_verdict = str(tamper_payload.get("verdict") or "")
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            errors.append(f"invalid_receipt_tamper_artifact: {exc}")
    if tamper_verdict != "PASS":
        errors.append("receipt_tamper_not_pass")

    if authorization.get("authorized_for_live_write_implementation") is True:
        errors.append("authorization_claims_live_write_implementation")
    if authorization.get("authorized_for_live_memory_write") is True:
        errors.append("authorization_claims_live_memory_write")
    if authorization.get("authorized_for_vector_db_write") is True:
        errors.append("authorization_claims_vector_db_write")
    if authorization.get("live_memory_write_allowed") is True:
        errors.append("live_memory_write_must_remain_false")
    if authorization.get("vector_db_write_allowed") is True:
        errors.append("vector_db_write_must_remain_false")
    if authorization.get("authorized_for_live_write_design_proposal") is not True:
        errors.append("live_write_design_proposal_not_authorized")
    if authorization.get("ready_for_future_live_write_design") is not True:
        errors.append("future_live_write_design_not_marked_ready")
    if authorization.get("requires_separate_live_write_design_campaign") is not True:
        errors.append("separate_live_write_design_campaign_required")
    if authorization.get("requires_separate_live_write_implementation_campaign") is not True:
        errors.append("separate_live_write_implementation_campaign_required")
    if authorization.get("requires_separate_operator_approval_for_live_write") is not True:
        errors.append("separate_operator_approval_for_live_write_required")
    if authorization.get("dry_run") is not True:
        errors.append("dry_run_must_be_true")
    if authorization.get("local_only") is not True:
        errors.append("local_only_must_be_true")

    for flag_name in (
        "model_called",
        "embeddings_used",
        "live_memory_written",
        "live_vector_db_written",
        "account_api_network_accessed",
        "autonomy_enabled",
    ):
        if authorization.get(flag_name) is True:
            errors.append(f"{flag_name}_must_remain_false")

    return ("PASS" if not errors else "FAIL"), errors


def _case_result(
    *,
    case_name: str,
    expected_verdict: str,
    authorization_path: Path,
    expected_receipt_sha256: str,
    expected_tamper_sha256: str,
    receipt_path: Path,
    tamper_evidence_path: Path,
) -> AuthorizationCaseResult:
    actual_verdict, errors = _evaluate_authorization_artifact(
        authorization_path,
        expected_receipt_sha256=expected_receipt_sha256,
        expected_tamper_sha256=expected_tamper_sha256,
        receipt_path=receipt_path,
        tamper_evidence_path=tamper_evidence_path,
    )
    valid = actual_verdict == "PASS"
    details = _closed_authorization_details(errors)
    details["authorization_artifact_path"] = str(authorization_path.resolve())
    if valid:
        details["design_authorization_phrase_valid"] = True
        details["authorized_for_live_write_design_proposal"] = True
        details["ready_for_future_live_write_design"] = True
        details["errors"] = []
    return AuthorizationCaseResult(
        case_name=case_name,
        expected_verdict=expected_verdict,
        actual_verdict=actual_verdict,
        detected=actual_verdict == expected_verdict,
        details=details,
    )


def _write_readme(
    readme_path: Path,
    report: LiveWriteDesignAuthorizationGateReport,
) -> None:
    lines = [
        "# Approved Promotion Live-Write Design Authorization Gate",
        "",
        "The live-write design authorization gate exists. This dry-run gate",
        "proves that a verified final dry-run acceptance receipt and its tamper",
        "evidence remain blocked from even beginning a future live-write design",
        "proposal until an explicit local design-only authorization artifact is",
        "present, valid, and bound to the current receipt hashes.",
        "",
        "It records `AUTHORIZE_LIVE_WRITE_DESIGN_PROPOSAL_ONLY`. It authorizes",
        "design-proposal readiness only after verification. It does not",
        "authorize live-write implementation. It does not authorize live memory",
        "writes. It does not authorize vector DB writes. Future live-write",
        "design still requires a separate design-proposal campaign. Future",
        "live-write implementation requires a separate explicit campaign after",
        "design approval. Models/embeddings/accounts/network are not called.",
        "`elysia/api/server.py`, `project_guardian/core.py`, and",
        "`config/autonomy.json` are untouched. server.py, core.py, and",
        "config/autonomy.json are untouched.",
        "",
        "## Design-only phrase",
        "",
        f"`{DESIGN_AUTHORIZATION_PHRASE}`",
        "",
        "`ready_for_future_live_write_design=true` means only that a separate",
        "future design-proposal campaign may be started after this gate is",
        "verified. It does not mean design is implemented. It does not mean",
        "live writes are allowed.",
        "",
        "The phrase is valid only with:",
        "",
        "- `authorized_for_live_write_design_proposal`: `true`",
        "- `authorized_for_live_write_implementation`: `false`",
        "- `authorized_for_live_memory_write`: `false`",
        "- `authorized_for_vector_db_write`: `false`",
        "- `live_memory_write_allowed`: `false`",
        "- `vector_db_write_allowed`: `false`",
        "- `ready_for_future_live_write_design`: `true`",
        "- `requires_separate_live_write_design_campaign`: `true`",
        "- `requires_separate_live_write_implementation_campaign`: `true`",
        "- `requires_separate_operator_approval_for_live_write`: `true`",
        "- receipt and receipt-tamper SHA-256 values matching the current files",
        "- receipt and receipt-tamper verdicts `PASS`",
        "- `dry_run`: `true`",
        "- `local_only`: `true`",
        "",
        "## Fail-closed cases",
        "",
        "- Missing design authorization artifact fails closed.",
        "- Invalid design authorization phrase fails closed.",
        "- Mismatched receipt hash fails closed.",
        "- Mismatched receipt tamper hash fails closed.",
        "- Receipt not PASS fails closed.",
        "- Receipt tamper not PASS fails closed.",
        "- Authorization claiming live-write implementation fails closed.",
        "- Authorization claiming live memory write fails closed.",
        "- Authorization claiming vector DB write fails closed.",
        "",
        "## Current artifacts",
        "",
        f"- Receipt JSON: `{report.source_final_dry_run_acceptance_receipt_path}`",
        f"- Receipt SHA-256: `{report.source_final_dry_run_acceptance_receipt_sha256}`",
        (
            "- Receipt tamper JSON: "
            f"`{report.source_final_dry_run_acceptance_receipt_tamper_evidence_path}`"
        ),
        (
            "- Receipt tamper SHA-256: "
            f"`{report.source_final_dry_run_acceptance_receipt_tamper_evidence_sha256}`"
        ),
        f"- Gate JSON: `{report.gate_report_path}`",
        (
            "- Valid design authorization artifact SHA-256: "
            f"`{report.design_authorization_artifact_sha256}`"
        ),
    ]
    readme_path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")


def _build_design_authorization_gate(
    workspace: Path,
) -> LiveWriteDesignAuthorizationGateReport:
    report = LiveWriteDesignAuthorizationGateReport(
        verdict="FAIL",
        workspace=str(workspace.resolve()),
        workspace_preserved=True,
        autonomy_enabled=_read_autonomy_enabled(),
    )
    if report.autonomy_enabled:
        report.errors.append(
            "Autonomy is enabled; live-write design authorization gate smoke is blocked."
        )
        return report

    tamper_report = (
        run_memory_review_approved_promotion_final_dry_run_acceptance_receipt_tamper_evidence_smoke(
            base_dir=workspace,
            keep_temp=True,
        )
    )
    report.final_dry_run_acceptance_receipt_verdict = tamper_report.clean_receipt_verdict
    report.final_dry_run_acceptance_receipt_tamper_evidence_verdict = tamper_report.verdict
    if tamper_report.verdict != "PASS":
        report.errors.append(
            "Final dry-run acceptance receipt tamper evidence smoke did not pass: "
            + "; ".join(tamper_report.errors)
        )
        return report
    if report.final_dry_run_acceptance_receipt_verdict != "PASS":
        report.errors.append("Clean final dry-run acceptance receipt did not pass.")
        return report

    receipt_path = Path(tamper_report.clean_receipt_json_path)
    if not receipt_path.is_file():
        fallback = workspace / RECEIPT_DIRNAME / RECEIPT_JSON_FILENAME
        if fallback.is_file():
            receipt_path = fallback
        else:
            report.errors.append(f"Clean acceptance receipt was not created: {receipt_path}")
            return report

    tamper_dir = workspace / RECEIPT_TAMPER_DIRNAME
    tamper_evidence_path = tamper_dir / RECEIPT_TAMPER_FILENAME
    _write_json(tamper_evidence_path, tamper_report.to_dict())

    report.source_final_dry_run_acceptance_receipt_path = str(receipt_path.resolve())
    report.source_final_dry_run_acceptance_receipt_sha256 = _sha256_file(receipt_path)
    report.source_final_dry_run_acceptance_receipt_tamper_evidence_path = str(
        tamper_evidence_path.resolve()
    )
    report.source_final_dry_run_acceptance_receipt_tamper_evidence_sha256 = _sha256_file(
        tamper_evidence_path
    )
    report.accepted_for_final_dry_run_readiness = True

    gate_dir = workspace / GATE_DIRNAME
    cases_dir = gate_dir / "authorization_cases"
    gate_dir.mkdir(parents=True, exist_ok=True)
    cases_dir.mkdir(parents=True, exist_ok=True)

    gate_report_path = gate_dir / GATE_REPORT_FILENAME
    readme_path = gate_dir / GATE_README_FILENAME
    valid_auth_path = gate_dir / AUTHORIZATION_ARTIFACT_FILENAME
    missing_auth_path = cases_dir / "missing_design_authorization_artifact.json"
    invalid_phrase_path = cases_dir / "invalid_design_authorization_phrase.json"
    mismatched_receipt_path = cases_dir / "mismatched_receipt_hash.json"
    mismatched_tamper_path = cases_dir / "mismatched_receipt_tamper_hash.json"
    receipt_not_pass_auth_path = cases_dir / "receipt_not_pass.json"
    receipt_tamper_not_pass_auth_path = cases_dir / "receipt_tamper_not_pass.json"
    impl_claim_path = cases_dir / "authorization_claims_live_write_implementation.json"
    live_claim_path = cases_dir / "authorization_claims_live_memory_write.json"
    vector_claim_path = cases_dir / "authorization_claims_vector_db_write.json"
    fail_receipt_path = cases_dir / "receipt_not_pass_source.json"
    fail_tamper_path = cases_dir / "receipt_tamper_not_pass_source.json"

    receipt_sha = report.source_final_dry_run_acceptance_receipt_sha256
    tamper_sha = report.source_final_dry_run_acceptance_receipt_tamper_evidence_sha256
    receipt_path_text = report.source_final_dry_run_acceptance_receipt_path
    tamper_path_text = report.source_final_dry_run_acceptance_receipt_tamper_evidence_path

    _write_json(
        invalid_phrase_path,
        _authorization_payload(
            receipt_sha256=receipt_sha,
            tamper_sha256=tamper_sha,
            receipt_path=receipt_path_text,
            tamper_path=tamper_path_text,
            phrase="INVALID_LIVE_WRITE_DESIGN_TOKEN",
        ),
    )
    _write_json(
        mismatched_receipt_path,
        _authorization_payload(
            receipt_sha256="0" * 64,
            tamper_sha256=tamper_sha,
            receipt_path=receipt_path_text,
            tamper_path=tamper_path_text,
        ),
    )
    _write_json(
        mismatched_tamper_path,
        _authorization_payload(
            receipt_sha256=receipt_sha,
            tamper_sha256="0" * 64,
            receipt_path=receipt_path_text,
            tamper_path=tamper_path_text,
        ),
    )

    fail_receipt_payload = _load_json(receipt_path)
    fail_receipt_payload["verdict"] = "FAIL"
    _write_json(fail_receipt_path, fail_receipt_payload)
    fail_receipt_sha = _sha256_file(fail_receipt_path)
    _write_json(
        receipt_not_pass_auth_path,
        _authorization_payload(
            receipt_sha256=fail_receipt_sha,
            tamper_sha256=tamper_sha,
            receipt_path=str(fail_receipt_path.resolve()),
            tamper_path=tamper_path_text,
            receipt_verdict="FAIL",
        ),
    )

    fail_tamper_payload = tamper_report.to_dict()
    fail_tamper_payload["verdict"] = "FAIL"
    _write_json(fail_tamper_path, fail_tamper_payload)
    fail_tamper_sha = _sha256_file(fail_tamper_path)
    _write_json(
        receipt_tamper_not_pass_auth_path,
        _authorization_payload(
            receipt_sha256=receipt_sha,
            tamper_sha256=fail_tamper_sha,
            receipt_path=receipt_path_text,
            tamper_path=str(fail_tamper_path.resolve()),
            tamper_verdict="FAIL",
        ),
    )
    _write_json(
        impl_claim_path,
        _authorization_payload(
            receipt_sha256=receipt_sha,
            tamper_sha256=tamper_sha,
            receipt_path=receipt_path_text,
            tamper_path=tamper_path_text,
            authorized_for_live_write_implementation=True,
        ),
    )
    _write_json(
        live_claim_path,
        _authorization_payload(
            receipt_sha256=receipt_sha,
            tamper_sha256=tamper_sha,
            receipt_path=receipt_path_text,
            tamper_path=tamper_path_text,
            authorized_for_live_memory_write=True,
        ),
    )
    _write_json(
        vector_claim_path,
        _authorization_payload(
            receipt_sha256=receipt_sha,
            tamper_sha256=tamper_sha,
            receipt_path=receipt_path_text,
            tamper_path=tamper_path_text,
            authorized_for_vector_db_write=True,
        ),
    )
    _write_json(
        valid_auth_path,
        _authorization_payload(
            receipt_sha256=receipt_sha,
            tamper_sha256=tamper_sha,
            receipt_path=receipt_path_text,
            tamper_path=tamper_path_text,
        ),
    )

    case_results = [
        _case_result(
            case_name="missing_design_authorization_artifact",
            expected_verdict="FAIL",
            authorization_path=missing_auth_path,
            expected_receipt_sha256=receipt_sha,
            expected_tamper_sha256=tamper_sha,
            receipt_path=receipt_path,
            tamper_evidence_path=tamper_evidence_path,
        ),
        _case_result(
            case_name="invalid_design_authorization_phrase",
            expected_verdict="FAIL",
            authorization_path=invalid_phrase_path,
            expected_receipt_sha256=receipt_sha,
            expected_tamper_sha256=tamper_sha,
            receipt_path=receipt_path,
            tamper_evidence_path=tamper_evidence_path,
        ),
        _case_result(
            case_name="mismatched_receipt_hash",
            expected_verdict="FAIL",
            authorization_path=mismatched_receipt_path,
            expected_receipt_sha256=receipt_sha,
            expected_tamper_sha256=tamper_sha,
            receipt_path=receipt_path,
            tamper_evidence_path=tamper_evidence_path,
        ),
        _case_result(
            case_name="mismatched_receipt_tamper_hash",
            expected_verdict="FAIL",
            authorization_path=mismatched_tamper_path,
            expected_receipt_sha256=receipt_sha,
            expected_tamper_sha256=tamper_sha,
            receipt_path=receipt_path,
            tamper_evidence_path=tamper_evidence_path,
        ),
        _case_result(
            case_name="receipt_not_pass",
            expected_verdict="FAIL",
            authorization_path=receipt_not_pass_auth_path,
            expected_receipt_sha256=fail_receipt_sha,
            expected_tamper_sha256=tamper_sha,
            receipt_path=fail_receipt_path,
            tamper_evidence_path=tamper_evidence_path,
        ),
        _case_result(
            case_name="receipt_tamper_not_pass",
            expected_verdict="FAIL",
            authorization_path=receipt_tamper_not_pass_auth_path,
            expected_receipt_sha256=receipt_sha,
            expected_tamper_sha256=fail_tamper_sha,
            receipt_path=receipt_path,
            tamper_evidence_path=fail_tamper_path,
        ),
        _case_result(
            case_name="authorization_claims_live_write_implementation",
            expected_verdict="FAIL",
            authorization_path=impl_claim_path,
            expected_receipt_sha256=receipt_sha,
            expected_tamper_sha256=tamper_sha,
            receipt_path=receipt_path,
            tamper_evidence_path=tamper_evidence_path,
        ),
        _case_result(
            case_name="authorization_claims_live_memory_write",
            expected_verdict="FAIL",
            authorization_path=live_claim_path,
            expected_receipt_sha256=receipt_sha,
            expected_tamper_sha256=tamper_sha,
            receipt_path=receipt_path,
            tamper_evidence_path=tamper_evidence_path,
        ),
        _case_result(
            case_name="authorization_claims_vector_db_write",
            expected_verdict="FAIL",
            authorization_path=vector_claim_path,
            expected_receipt_sha256=receipt_sha,
            expected_tamper_sha256=tamper_sha,
            receipt_path=receipt_path,
            tamper_evidence_path=tamper_evidence_path,
        ),
        _case_result(
            case_name="valid_design_proposal_authorization_only",
            expected_verdict="PASS",
            authorization_path=valid_auth_path,
            expected_receipt_sha256=receipt_sha,
            expected_tamper_sha256=tamper_sha,
            receipt_path=receipt_path,
            tamper_evidence_path=tamper_evidence_path,
        ),
    ]

    cases_by_name = {case.case_name: case for case in case_results}
    case_dicts = [case.to_dict() for case in case_results]
    report.gate_path = str(gate_dir.resolve())
    report.gate_report_path = str(gate_report_path.resolve())
    report.gate_readme_path = str(readme_path.resolve())
    report.authorization_cases = case_dicts
    report.design_authorization_cases = case_dicts
    report.authorization_case_count = len(case_results)
    report.design_authorization_artifact_present = valid_auth_path.is_file()
    report.design_authorization_artifact_sha256 = (
        _sha256_file(valid_auth_path) if report.design_authorization_artifact_present else ""
    )
    report.design_authorization_phrase_valid = (
        report.design_authorization_artifact_present
        and _load_json(valid_auth_path).get("design_authorization_phrase")
        == DESIGN_AUTHORIZATION_PHRASE
    )

    invalid_failed_closed = all(
        cases_by_name[name].actual_verdict == "FAIL" and cases_by_name[name].detected
        for name in INVALID_AUTHORIZATION_CASES
    )
    valid_case = cases_by_name["valid_design_proposal_authorization_only"]
    valid_passed_design_only = (
        valid_case.actual_verdict == "PASS"
        and valid_case.detected
        and valid_case.details["authorized_for_live_write_design_proposal"] is True
        and valid_case.details["authorized_for_live_write_implementation"] is False
        and valid_case.details["authorized_for_live_memory_write"] is False
        and valid_case.details["authorized_for_vector_db_write"] is False
        and valid_case.details["live_memory_write_allowed"] is False
        and valid_case.details["vector_db_write_allowed"] is False
        and valid_case.details["ready_for_future_live_write_design"] is True
    )
    report.all_invalid_authorization_cases_failed_closed = invalid_failed_closed
    report.valid_design_authorization_passed_design_only = valid_passed_design_only
    report.authorized_for_live_write_design_proposal = valid_passed_design_only
    report.authorized_for_live_write_implementation = False
    report.authorized_for_live_memory_write = False
    report.authorized_for_vector_db_write = False
    report.live_memory_write_allowed = False
    report.vector_db_write_allowed = False
    report.ready_for_future_live_write_design = valid_passed_design_only
    report.requires_separate_live_write_design_campaign = True
    report.requires_separate_live_write_implementation_campaign = True
    report.requires_separate_operator_approval_for_live_write = True

    tracked_paths = (
        gate_dir,
        cases_dir,
        gate_report_path,
        readme_path,
        valid_auth_path,
        missing_auth_path,
        invalid_phrase_path,
        mismatched_receipt_path,
        mismatched_tamper_path,
        receipt_not_pass_auth_path,
        receipt_tamper_not_pass_auth_path,
        impl_claim_path,
        live_claim_path,
        vector_claim_path,
        fail_receipt_path,
        fail_tamper_path,
        receipt_path,
        tamper_evidence_path,
    )
    report.authorization_paths_inside_workspace = all(
        _path_inside_workspace(path, workspace)
        for path in tracked_paths
        if path.exists() or path == missing_auth_path
    )

    report.artifact_paths = {
        "gate_dir": report.gate_path,
        "gate_report": report.gate_report_path,
        "gate_readme": report.gate_readme_path,
        "valid_design_authorization_artifact": str(valid_auth_path.resolve()),
        "receipt_json": report.source_final_dry_run_acceptance_receipt_path,
        "receipt_tamper_json": report.source_final_dry_run_acceptance_receipt_tamper_evidence_path,
        "missing_design_authorization_artifact": str(missing_auth_path.resolve()),
        "invalid_design_authorization_phrase": str(invalid_phrase_path.resolve()),
        "mismatched_receipt_hash": str(mismatched_receipt_path.resolve()),
        "mismatched_receipt_tamper_hash": str(mismatched_tamper_path.resolve()),
        "receipt_not_pass": str(receipt_not_pass_auth_path.resolve()),
        "receipt_tamper_not_pass": str(receipt_tamper_not_pass_auth_path.resolve()),
        "authorization_claims_live_write_implementation": str(impl_claim_path.resolve()),
        "authorization_claims_live_memory_write": str(live_claim_path.resolve()),
        "authorization_claims_vector_db_write": str(vector_claim_path.resolve()),
    }

    _write_readme(readme_path, report)

    checks = {
        "receipt_pass": report.final_dry_run_acceptance_receipt_verdict == "PASS",
        "receipt_tamper_pass": report.final_dry_run_acceptance_receipt_tamper_evidence_verdict
        == "PASS",
        "authorization_case_count": report.authorization_case_count
        == len(REQUIRED_AUTHORIZATION_CASES),
        "all_required_cases_present": {case.case_name for case in case_results}
        == set(REQUIRED_AUTHORIZATION_CASES),
        "all_cases_detected": all(case.detected for case in case_results),
        "all_invalid_authorization_cases_failed_closed": (
            report.all_invalid_authorization_cases_failed_closed
        ),
        "valid_design_authorization_passed_design_only": (
            report.valid_design_authorization_passed_design_only
        ),
        "authorized_for_live_write_design_proposal": (
            report.authorized_for_live_write_design_proposal
        ),
        "not_authorized_for_live_write_implementation": (
            not report.authorized_for_live_write_implementation
        ),
        "not_authorized_for_live_memory_write": not report.authorized_for_live_memory_write,
        "not_authorized_for_vector_db_write": not report.authorized_for_vector_db_write,
        "live_memory_write_blocked": not report.live_memory_write_allowed,
        "vector_db_write_blocked": not report.vector_db_write_allowed,
        "ready_for_future_live_write_design": report.ready_for_future_live_write_design,
        "separate_live_write_design_campaign_required": (
            report.requires_separate_live_write_design_campaign
        ),
        "separate_live_write_implementation_campaign_required": (
            report.requires_separate_live_write_implementation_campaign
        ),
        "separate_operator_approval_for_live_write_required": (
            report.requires_separate_operator_approval_for_live_write
        ),
        "design_authorization_phrase_valid": report.design_authorization_phrase_valid,
        "design_authorization_artifact_present": report.design_authorization_artifact_present,
        "receipt_hash_present": len(report.source_final_dry_run_acceptance_receipt_sha256)
        == 64,
        "receipt_tamper_hash_present": len(
            report.source_final_dry_run_acceptance_receipt_tamper_evidence_sha256
        )
        == 64,
        "authorization_paths_inside_workspace": report.authorization_paths_inside_workspace,
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
        report.errors.append("Live-write design authorization gate JSON is invalid.")
        report.verdict = "FAIL"
    _write_json(gate_report_path, report.to_dict())
    return report


def run_memory_review_approved_promotion_live_write_design_authorization_gate_smoke(
    *,
    base_dir: Path | None = None,
    keep_temp: bool = False,
) -> LiveWriteDesignAuthorizationGateReport:
    """Build and validate a dry-run live-write design authorization gate."""
    owned_temp = base_dir is None
    workspace = (
        Path(tempfile.mkdtemp(prefix="elysia_lwdag_"))
        if owned_temp
        else _reject_dangerous_base(Path(base_dir))
    )
    workspace.mkdir(parents=True, exist_ok=True)
    try:
        try:
            report = _build_design_authorization_gate(workspace)
        except Exception as exc:
            report = LiveWriteDesignAuthorizationGateReport(
                verdict="FAIL",
                workspace=str(workspace.resolve()),
                workspace_preserved=(not owned_temp) or keep_temp,
                autonomy_enabled=_read_autonomy_enabled(),
                errors=[f"design_authorization_gate_build_failed: {exc}"],
            )
        report.workspace_preserved = (not owned_temp) or keep_temp
        return report
    finally:
        if owned_temp and not keep_temp:
            shutil.rmtree(workspace, ignore_errors=True)


def format_design_authorization_gate_summary(
    report: LiveWriteDesignAuthorizationGateReport,
) -> str:
    lines = [
        "Memory review approved promotion live-write design authorization gate smoke",
        "=" * 78,
        f"Verdict: {report.verdict}",
        f"Workspace: {report.workspace}",
        f"Workspace preserved: {report.workspace_preserved}",
        f"Gate path: {report.gate_path}",
        f"Gate JSON: {report.gate_report_path}",
        f"Receipt verdict: {report.final_dry_run_acceptance_receipt_verdict}",
        (
            "Receipt tamper evidence verdict: "
            f"{report.final_dry_run_acceptance_receipt_tamper_evidence_verdict}"
        ),
        "",
        "Design authorization gate checks:",
        f"  design authorization phrase: {report.design_authorization_phrase}",
        f"  design authorization phrase valid: {report.design_authorization_phrase_valid}",
        f"  design authorization artifact present: {report.design_authorization_artifact_present}",
        f"  authorization case count: {report.authorization_case_count}",
        f"  all invalid cases failed closed: {report.all_invalid_authorization_cases_failed_closed}",
        (
            "  valid design authorization passed design-only: "
            f"{report.valid_design_authorization_passed_design_only}"
        ),
        (
            "  authorized_for_live_write_design_proposal: "
            f"{report.authorized_for_live_write_design_proposal}"
        ),
        (
            "  authorized_for_live_write_implementation: "
            f"{report.authorized_for_live_write_implementation}"
        ),
        f"  authorized_for_live_memory_write: {report.authorized_for_live_memory_write}",
        f"  authorized_for_vector_db_write: {report.authorized_for_vector_db_write}",
        f"  ready_for_future_live_write_design: {report.ready_for_future_live_write_design}",
        (
            "  requires_separate_live_write_design_campaign: "
            f"{report.requires_separate_live_write_design_campaign}"
        ),
        (
            "  requires_separate_live_write_implementation_campaign: "
            f"{report.requires_separate_live_write_implementation_campaign}"
        ),
        (
            "  requires_separate_operator_approval_for_live_write: "
            f"{report.requires_separate_operator_approval_for_live_write}"
        ),
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
            "Run local-only Memory review approved promotion live-write "
            "design authorization gate smoke."
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
        report = run_memory_review_approved_promotion_live_write_design_authorization_gate_smoke(
            base_dir=args.base_dir,
            keep_temp=args.keep_temp,
        )
    except (ValueError, OSError) as exc:
        report = LiveWriteDesignAuthorizationGateReport(
            verdict="FAIL",
            workspace=str(args.base_dir or ""),
            workspace_preserved=False,
            autonomy_enabled=_read_autonomy_enabled(),
            errors=[str(exc)],
        )

    if args.json:
        print(json.dumps(report.to_dict(), indent=2, ensure_ascii=False))
    else:
        print(format_design_authorization_gate_summary(report))
    return 0 if report.verdict == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
