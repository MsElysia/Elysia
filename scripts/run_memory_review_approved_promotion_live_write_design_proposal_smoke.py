#!/usr/bin/env python3
"""Dry-run/local smoke recording the authorized live-write design proposal.

This smoke rebuilds a valid live-write design authorization gate, then writes a
local design-proposal packet bound to that gate and the operator phrase
AUTHORIZE_LIVE_WRITE_DESIGN_PROPOSAL_ONLY. Missing, invalid, or write-claiming
proposals fail closed. A valid proposal records design constraints only. It
never implements live writes, never authorizes live memory or vector DB writes,
and never calls models, embeddings, networks, live accounts, or UI routes.
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

from run_memory_review_approved_promotion_live_write_design_authorization_gate_smoke import (  # noqa: E402
    DESIGN_AUTHORIZATION_PHRASE,
    GATE_DIRNAME,
    GATE_REPORT_FILENAME,
    run_memory_review_approved_promotion_live_write_design_authorization_gate_smoke,
)

PROPOSAL_DIRNAME = "approved_promotion_live_write_design_proposal"
PROPOSAL_JSON_FILENAME = "live_write_design_proposal.json"
PROPOSAL_REPORT_FILENAME = "live_write_design_proposal_report.json"
PROPOSAL_README_FILENAME = "LIVE_WRITE_DESIGN_PROPOSAL.md"

ACCEPTED_CHECKPOINT_TAG = (
    "memory_review_approved_promotion_live_write_design_authorization_gate_clean_1"
)
ACCEPTED_CHECKPOINT_HASH = "a5b4f7ef480bc591fa9ef95d63adc8bf0b64f88a"
ACCEPTED_CHECKPOINT_MESSAGE = (
    "feat(local): add approved promotion live write design authorization gate"
)

LIVE_WRITE_BLOCKED_REASON = (
    "Live memory write remains blocked. A live-write design proposal does not "
    "authorize live memory writes. A separate explicit implementation campaign "
    "and separate operator approval are required before any live memory write "
    "path may exist."
)
VECTOR_WRITE_BLOCKED_REASON = (
    "Vector DB write remains blocked. A live-write design proposal does not "
    "authorize vector DB writes. A separate explicit implementation campaign "
    "and separate operator approval are required before any vector DB write "
    "path may exist."
)
IMPLEMENTATION_BLOCKED_REASON = (
    "Live-write implementation remains blocked. This campaign records a design "
    "proposal only. A separate explicit implementation campaign after design "
    "approval is required before any live-write path may exist."
)

PROPOSAL_SCOPE = (
    "Future live memory writes, if ever implemented, would remain dry-run "
    "blocked by default and would require a later implementation campaign.",
    "Future vector DB writes, if ever implemented, would remain dry-run "
    "blocked by default and would require that same later implementation campaign.",
    "Any later implementation campaign must keep config/autonomy.json enabled=false "
    "unless a separate explicit autonomy campaign is accepted.",
    "Any later implementation campaign must leave project_guardian/core.py and "
    "elysia/api/server.py untouched unless a separate explicit campaign names them.",
    "Any later live write would still require a distinct operator approval phrase "
    "that is not AUTHORIZE_LIVE_WRITE_DESIGN_PROPOSAL_ONLY.",
    "This proposal does not add write APIs, UI routes, POST actions, watchers, "
    "daemons, schedulers, model calls, embedding calls, or network access.",
)
PROPOSAL_NON_GOALS = (
    "Do not implement live memory writes.",
    "Do not implement vector DB writes.",
    "Do not implement the live-write path.",
    "Do not enable autonomy.",
    "Do not call models, embeddings, accounts, or network APIs.",
    "Do not add UI routes, browser fetch, or POST actions.",
)

OPERATOR_NEXT_STEPS = [
    "Live-write design proposal is recorded.",
    "Live memory writes remain blocked.",
    "Vector DB writes remain blocked.",
    "Live-write implementation remains blocked.",
    "Future live-write implementation requires a separate explicit campaign after design approval.",
    "Separate operator approval is still required for live writes.",
]

REQUIRED_PROPOSAL_CASES = (
    "missing_design_proposal_artifact",
    "invalid_design_authorization_phrase",
    "mismatched_gate_hash",
    "gate_not_pass",
    "proposal_claims_live_write_implementation",
    "proposal_claims_live_memory_write",
    "proposal_claims_vector_db_write",
    "proposal_omits_separate_implementation_campaign",
    "valid_design_proposal_only",
)
INVALID_PROPOSAL_CASES = REQUIRED_PROPOSAL_CASES[:-1]

REQUIRED_REPORT_FIELDS = (
    "verdict",
    "workspace",
    "proposal_path",
    "proposal_json_path",
    "proposal_json_valid",
    "proposal_report_path",
    "proposal_report_valid_json",
    "proposal_readme_path",
    "proposal_readme_sha256",
    "design_authorization_phrase",
    "design_authorization_phrase_valid",
    "accepted_checkpoint_tag",
    "accepted_checkpoint_hash",
    "accepted_checkpoint_message",
    "source_live_write_design_authorization_gate_path",
    "source_live_write_design_authorization_gate_sha256",
    "live_write_design_authorization_gate_verdict",
    "authorized_for_live_write_design_proposal",
    "authorized_for_live_write_implementation",
    "authorized_for_live_memory_write",
    "authorized_for_vector_db_write",
    "live_memory_write_allowed",
    "vector_db_write_allowed",
    "live_write_implemented",
    "ready_for_live_write_implementation",
    "requires_separate_live_write_implementation_campaign",
    "requires_separate_operator_approval_for_live_write",
    "live_write_blocked_reason",
    "vector_db_write_blocked_reason",
    "implementation_blocked_reason",
    "proposal_scope",
    "proposal_non_goals",
    "operator_next_steps",
    "proposal_cases",
    "proposal_case_count",
    "all_invalid_proposal_cases_failed_closed",
    "valid_design_proposal_passed_proposal_only",
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
class ProposalCaseResult:
    case_name: str
    expected_verdict: str
    actual_verdict: str
    detected: bool
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class LiveWriteDesignProposalReport:
    verdict: str
    workspace: str
    proposal_path: str = ""
    proposal_json_path: str = ""
    proposal_json_valid: bool = False
    proposal_report_path: str = ""
    proposal_report_valid_json: bool = False
    proposal_readme_path: str = ""
    proposal_readme_sha256: str = ""
    design_authorization_phrase: str = DESIGN_AUTHORIZATION_PHRASE
    design_authorization_phrase_valid: bool = False
    accepted_checkpoint_tag: str = ACCEPTED_CHECKPOINT_TAG
    accepted_checkpoint_hash: str = ACCEPTED_CHECKPOINT_HASH
    accepted_checkpoint_message: str = ACCEPTED_CHECKPOINT_MESSAGE
    source_live_write_design_authorization_gate_path: str = ""
    source_live_write_design_authorization_gate_sha256: str = ""
    live_write_design_authorization_gate_verdict: str = "UNKNOWN"
    authorized_for_live_write_design_proposal: bool = False
    authorized_for_live_write_implementation: bool = False
    authorized_for_live_memory_write: bool = False
    authorized_for_vector_db_write: bool = False
    live_memory_write_allowed: bool = False
    vector_db_write_allowed: bool = False
    live_write_implemented: bool = False
    ready_for_live_write_implementation: bool = False
    requires_separate_live_write_implementation_campaign: bool = True
    requires_separate_operator_approval_for_live_write: bool = True
    live_write_blocked_reason: str = LIVE_WRITE_BLOCKED_REASON
    vector_db_write_blocked_reason: str = VECTOR_WRITE_BLOCKED_REASON
    implementation_blocked_reason: str = IMPLEMENTATION_BLOCKED_REASON
    proposal_scope: List[str] = field(default_factory=lambda: list(PROPOSAL_SCOPE))
    proposal_non_goals: List[str] = field(default_factory=lambda: list(PROPOSAL_NON_GOALS))
    operator_next_steps: List[str] = field(default_factory=lambda: list(OPERATOR_NEXT_STEPS))
    proposal_cases: List[Dict[str, Any]] = field(default_factory=list)
    proposal_case_count: int = 0
    all_invalid_proposal_cases_failed_closed: bool = False
    valid_design_proposal_passed_proposal_only: bool = False
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


def _closed_proposal_details(errors: List[str]) -> Dict[str, Any]:
    return {
        "design_authorization_phrase_valid": False,
        "authorized_for_live_write_design_proposal": False,
        "authorized_for_live_write_implementation": False,
        "authorized_for_live_memory_write": False,
        "authorized_for_vector_db_write": False,
        "live_memory_write_allowed": False,
        "vector_db_write_allowed": False,
        "live_write_implemented": False,
        "ready_for_live_write_implementation": False,
        "requires_separate_live_write_implementation_campaign": True,
        "requires_separate_operator_approval_for_live_write": True,
        "errors": errors,
    }


def _proposal_payload(
    *,
    gate_sha256: str,
    gate_path: str,
    phrase: str = DESIGN_AUTHORIZATION_PHRASE,
    gate_verdict: str = "PASS",
    authorized_for_live_write_design_proposal: bool = True,
    authorized_for_live_write_implementation: bool = False,
    authorized_for_live_memory_write: bool = False,
    authorized_for_vector_db_write: bool = False,
    live_memory_write_allowed: bool = False,
    vector_db_write_allowed: bool = False,
    live_write_implemented: bool = False,
    ready_for_live_write_implementation: bool = False,
    requires_separate_live_write_implementation_campaign: bool = True,
    requires_separate_operator_approval_for_live_write: bool = True,
    dry_run: bool = True,
    local_only: bool = True,
    proposal_scope: Sequence[str] | None = None,
    proposal_non_goals: Sequence[str] | None = None,
) -> Dict[str, Any]:
    return {
        "proposal_id": "live-write-design-proposal-only",
        "design_authorization_phrase": phrase,
        "accepted_checkpoint_tag": ACCEPTED_CHECKPOINT_TAG,
        "accepted_checkpoint_hash": ACCEPTED_CHECKPOINT_HASH,
        "accepted_checkpoint_message": ACCEPTED_CHECKPOINT_MESSAGE,
        "source_live_write_design_authorization_gate_path": gate_path,
        "source_live_write_design_authorization_gate_sha256": gate_sha256,
        "live_write_design_authorization_gate_verdict": gate_verdict,
        "authorized_for_live_write_design_proposal": authorized_for_live_write_design_proposal,
        "authorized_for_live_write_implementation": authorized_for_live_write_implementation,
        "authorized_for_live_memory_write": authorized_for_live_memory_write,
        "authorized_for_vector_db_write": authorized_for_vector_db_write,
        "live_memory_write_allowed": live_memory_write_allowed,
        "vector_db_write_allowed": vector_db_write_allowed,
        "live_write_implemented": live_write_implemented,
        "ready_for_live_write_implementation": ready_for_live_write_implementation,
        "requires_separate_live_write_implementation_campaign": (
            requires_separate_live_write_implementation_campaign
        ),
        "requires_separate_operator_approval_for_live_write": (
            requires_separate_operator_approval_for_live_write
        ),
        "live_write_blocked_reason": LIVE_WRITE_BLOCKED_REASON,
        "vector_db_write_blocked_reason": VECTOR_WRITE_BLOCKED_REASON,
        "implementation_blocked_reason": IMPLEMENTATION_BLOCKED_REASON,
        "proposal_scope": list(proposal_scope if proposal_scope is not None else PROPOSAL_SCOPE),
        "proposal_non_goals": list(
            proposal_non_goals if proposal_non_goals is not None else PROPOSAL_NON_GOALS
        ),
        "operator_next_steps": list(OPERATOR_NEXT_STEPS),
        "dry_run": dry_run,
        "local_only": local_only,
    }


def _evaluate_proposal_artifact(
    proposal_path: Path,
    *,
    expected_gate_sha256: str,
    gate_path: Path,
) -> Tuple[str, List[str]]:
    errors: List[str] = []
    if not proposal_path.is_file():
        return "FAIL", [f"missing_design_proposal_artifact: {proposal_path}"]

    try:
        proposal = _load_json(proposal_path)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        return "FAIL", [f"invalid_design_proposal_artifact: {exc}"]

    required_fields = (
        "proposal_id",
        "design_authorization_phrase",
        "source_live_write_design_authorization_gate_sha256",
        "authorized_for_live_write_design_proposal",
        "authorized_for_live_write_implementation",
        "authorized_for_live_memory_write",
        "authorized_for_vector_db_write",
        "live_memory_write_allowed",
        "vector_db_write_allowed",
        "live_write_implemented",
        "ready_for_live_write_implementation",
        "requires_separate_live_write_implementation_campaign",
        "requires_separate_operator_approval_for_live_write",
        "proposal_scope",
        "proposal_non_goals",
        "dry_run",
        "local_only",
    )
    missing_fields = [name for name in required_fields if name not in proposal]
    if missing_fields:
        errors.append("missing_proposal_field: " + ", ".join(missing_fields))

    if proposal.get("design_authorization_phrase") != DESIGN_AUTHORIZATION_PHRASE:
        errors.append("invalid_design_authorization_phrase")

    actual_gate_sha256 = _sha256_file(gate_path) if gate_path.is_file() else ""
    if (
        proposal.get("source_live_write_design_authorization_gate_sha256")
        != expected_gate_sha256
        or actual_gate_sha256 != expected_gate_sha256
    ):
        errors.append("mismatched_gate_hash")

    gate_verdict = ""
    if gate_path.is_file():
        try:
            gate_payload = _load_json(gate_path)
            gate_verdict = str(gate_payload.get("verdict") or "")
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            errors.append(f"invalid_gate_artifact: {exc}")
    if gate_verdict != "PASS":
        errors.append("gate_not_pass")
    if proposal.get("live_write_design_authorization_gate_verdict") not in (None, "PASS"):
        if proposal.get("live_write_design_authorization_gate_verdict") != "PASS":
            errors.append("gate_not_pass")

    if proposal.get("authorized_for_live_write_implementation") is True:
        errors.append("proposal_claims_live_write_implementation")
    if proposal.get("authorized_for_live_memory_write") is True:
        errors.append("proposal_claims_live_memory_write")
    if proposal.get("authorized_for_vector_db_write") is True:
        errors.append("proposal_claims_vector_db_write")
    if proposal.get("live_memory_write_allowed") is True:
        errors.append("live_memory_write_must_remain_false")
    if proposal.get("vector_db_write_allowed") is True:
        errors.append("vector_db_write_must_remain_false")
    if proposal.get("live_write_implemented") is True:
        errors.append("live_write_must_remain_unimplemented")
    if proposal.get("ready_for_live_write_implementation") is True:
        errors.append("live_write_implementation_must_remain_unready")
    if proposal.get("authorized_for_live_write_design_proposal") is not True:
        errors.append("live_write_design_proposal_not_authorized")
    if proposal.get("requires_separate_live_write_implementation_campaign") is not True:
        errors.append("proposal_omits_separate_implementation_campaign")
    if proposal.get("requires_separate_operator_approval_for_live_write") is not True:
        errors.append("separate_operator_approval_for_live_write_required")
    if proposal.get("dry_run") is not True:
        errors.append("dry_run_must_be_true")
    if proposal.get("local_only") is not True:
        errors.append("local_only_must_be_true")
    scope = proposal.get("proposal_scope")
    if not isinstance(scope, list) or not scope:
        errors.append("proposal_scope_missing")
    non_goals = proposal.get("proposal_non_goals")
    if not isinstance(non_goals, list) or not non_goals:
        errors.append("proposal_non_goals_missing")

    for flag_name in (
        "model_called",
        "embeddings_used",
        "live_memory_written",
        "live_vector_db_written",
        "account_api_network_accessed",
        "autonomy_enabled",
    ):
        if proposal.get(flag_name) is True:
            errors.append(f"{flag_name}_must_remain_false")

    # Deduplicate gate_not_pass if both sources added it.
    deduped: List[str] = []
    for error in errors:
        if error not in deduped:
            deduped.append(error)
    return ("PASS" if not deduped else "FAIL"), deduped


def _case_result(
    *,
    case_name: str,
    expected_verdict: str,
    proposal_path: Path,
    expected_gate_sha256: str,
    gate_path: Path,
) -> ProposalCaseResult:
    actual_verdict, errors = _evaluate_proposal_artifact(
        proposal_path,
        expected_gate_sha256=expected_gate_sha256,
        gate_path=gate_path,
    )
    valid = actual_verdict == "PASS"
    details = _closed_proposal_details(errors)
    details["proposal_artifact_path"] = str(proposal_path.resolve())
    if valid:
        details["design_authorization_phrase_valid"] = True
        details["authorized_for_live_write_design_proposal"] = True
        details["errors"] = []
    return ProposalCaseResult(
        case_name=case_name,
        expected_verdict=expected_verdict,
        actual_verdict=actual_verdict,
        detected=actual_verdict == expected_verdict,
        details=details,
    )


def _write_readme(readme_path: Path, report: LiveWriteDesignProposalReport) -> None:
    lines = [
        "# Approved Promotion Live-Write Design Proposal",
        "",
        "The live-write design proposal exists. This dry-run packet records",
        f"`{DESIGN_AUTHORIZATION_PHRASE}`. It records a design proposal only.",
        "",
        "It does not implement the live-write path. It does not authorize live",
        "memory writes. It does not authorize vector DB writes. Future live-write",
        "implementation requires a separate explicit campaign after design",
        "approval. Separate operator approval is still required for live writes.",
        "Models/embeddings/accounts/network are not called.",
        "`elysia/api/server.py`, `project_guardian/core.py`, and",
        "`config/autonomy.json` are untouched.",
        "",
        "## Recorded authorization",
        "",
        f"- Phrase: `{report.design_authorization_phrase}`",
        f"- Phrase valid: `{str(report.design_authorization_phrase_valid).lower()}`",
        f"- Accepted checkpoint tag: `{report.accepted_checkpoint_tag}`",
        f"- Accepted checkpoint hash: `{report.accepted_checkpoint_hash}`",
        f"- Accepted checkpoint message: `{report.accepted_checkpoint_message}`",
        "",
        "## Source hashes",
        "",
        (
            "- Design authorization gate: "
            f"`{report.source_live_write_design_authorization_gate_sha256}`"
        ),
        f"- Design authorization gate verdict: `{report.live_write_design_authorization_gate_verdict}`",
        "",
        "## Authorization",
        "",
        (
            "- authorized_for_live_write_design_proposal: "
            f"`{str(report.authorized_for_live_write_design_proposal).lower()}`"
        ),
        (
            "- authorized_for_live_write_implementation: "
            f"`{str(report.authorized_for_live_write_implementation).lower()}`"
        ),
        (
            "- authorized_for_live_memory_write: "
            f"`{str(report.authorized_for_live_memory_write).lower()}`"
        ),
        (
            "- authorized_for_vector_db_write: "
            f"`{str(report.authorized_for_vector_db_write).lower()}`"
        ),
        f"- live_memory_write_allowed: `{str(report.live_memory_write_allowed).lower()}`",
        f"- vector_db_write_allowed: `{str(report.vector_db_write_allowed).lower()}`",
        f"- live_write_implemented: `{str(report.live_write_implemented).lower()}`",
        (
            "- ready_for_live_write_implementation: "
            f"`{str(report.ready_for_live_write_implementation).lower()}`"
        ),
        "",
        "## Proposal scope",
        "",
    ]
    lines.extend(f"- {item}" for item in report.proposal_scope)
    lines.extend(["", "## Non-goals", ""])
    lines.extend(f"- {item}" for item in report.proposal_non_goals)
    lines.extend(["", "## Operator next steps", ""])
    lines.extend(f"- {step}" for step in report.operator_next_steps)
    lines.extend(
        [
            "",
            "## Fail-closed cases",
            "",
            "- Missing design proposal artifact fails closed.",
            "- Invalid design authorization phrase fails closed.",
            "- Mismatched gate hash fails closed.",
            "- Gate not PASS fails closed.",
            "- Proposal claiming live-write implementation fails closed.",
            "- Proposal claiming live memory write fails closed.",
            "- Proposal claiming vector DB write fails closed.",
            "- Proposal omitting a separate implementation campaign fails closed.",
        ]
    )
    readme_path.parent.mkdir(parents=True, exist_ok=True)
    readme_path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")


def _build_design_proposal(workspace: Path) -> LiveWriteDesignProposalReport:
    report = LiveWriteDesignProposalReport(
        verdict="FAIL",
        workspace=str(workspace.resolve()),
        workspace_preserved=True,
        autonomy_enabled=_read_autonomy_enabled(),
    )
    if report.autonomy_enabled:
        report.errors.append(
            "Autonomy is enabled; live-write design proposal smoke is blocked."
        )
        return report

    gate_report = run_memory_review_approved_promotion_live_write_design_authorization_gate_smoke(
        base_dir=workspace,
        keep_temp=True,
    )
    report.live_write_design_authorization_gate_verdict = gate_report.verdict
    if gate_report.verdict != "PASS":
        report.errors.append(
            "Live-write design authorization gate smoke did not pass: "
            + "; ".join(gate_report.errors)
        )
        return report
    if gate_report.authorized_for_live_write_design_proposal is not True:
        report.errors.append("Design authorization gate did not authorize a design proposal.")
        return report

    gate_path = Path(gate_report.gate_report_path)
    if not gate_path.is_file():
        fallback = workspace / GATE_DIRNAME / GATE_REPORT_FILENAME
        if fallback.is_file():
            gate_path = fallback
        else:
            report.errors.append(f"Design authorization gate report was not created: {gate_path}")
            return report

    report.source_live_write_design_authorization_gate_path = str(gate_path.resolve())
    report.source_live_write_design_authorization_gate_sha256 = _sha256_file(gate_path)
    report.design_authorization_phrase = DESIGN_AUTHORIZATION_PHRASE
    report.design_authorization_phrase_valid = True
    report.accepted_checkpoint_tag = ACCEPTED_CHECKPOINT_TAG
    report.accepted_checkpoint_hash = ACCEPTED_CHECKPOINT_HASH
    report.accepted_checkpoint_message = ACCEPTED_CHECKPOINT_MESSAGE

    proposal_dir = workspace / PROPOSAL_DIRNAME
    cases_dir = proposal_dir / "proposal_cases"
    proposal_dir.mkdir(parents=True, exist_ok=True)
    cases_dir.mkdir(parents=True, exist_ok=True)

    valid_proposal_path = proposal_dir / PROPOSAL_JSON_FILENAME
    report_path = proposal_dir / PROPOSAL_REPORT_FILENAME
    readme_path = proposal_dir / PROPOSAL_README_FILENAME
    missing_path = cases_dir / "missing_design_proposal_artifact.json"
    invalid_phrase_path = cases_dir / "invalid_design_authorization_phrase.json"
    mismatched_gate_path = cases_dir / "mismatched_gate_hash.json"
    gate_not_pass_proposal_path = cases_dir / "gate_not_pass.json"
    impl_claim_path = cases_dir / "proposal_claims_live_write_implementation.json"
    live_claim_path = cases_dir / "proposal_claims_live_memory_write.json"
    vector_claim_path = cases_dir / "proposal_claims_vector_db_write.json"
    omit_impl_path = cases_dir / "proposal_omits_separate_implementation_campaign.json"
    fail_gate_path = cases_dir / "gate_not_pass_source.json"

    gate_sha = report.source_live_write_design_authorization_gate_sha256
    gate_path_text = report.source_live_write_design_authorization_gate_path

    _write_json(
        invalid_phrase_path,
        _proposal_payload(
            gate_sha256=gate_sha,
            gate_path=gate_path_text,
            phrase="INVALID_LIVE_WRITE_DESIGN_TOKEN",
        ),
    )
    _write_json(
        mismatched_gate_path,
        _proposal_payload(
            gate_sha256="0" * 64,
            gate_path=gate_path_text,
        ),
    )

    fail_gate_payload = _load_json(gate_path)
    fail_gate_payload["verdict"] = "FAIL"
    _write_json(fail_gate_path, fail_gate_payload)
    fail_gate_sha = _sha256_file(fail_gate_path)
    _write_json(
        gate_not_pass_proposal_path,
        _proposal_payload(
            gate_sha256=fail_gate_sha,
            gate_path=str(fail_gate_path.resolve()),
            gate_verdict="FAIL",
        ),
    )
    _write_json(
        impl_claim_path,
        _proposal_payload(
            gate_sha256=gate_sha,
            gate_path=gate_path_text,
            authorized_for_live_write_implementation=True,
        ),
    )
    _write_json(
        live_claim_path,
        _proposal_payload(
            gate_sha256=gate_sha,
            gate_path=gate_path_text,
            authorized_for_live_memory_write=True,
        ),
    )
    _write_json(
        vector_claim_path,
        _proposal_payload(
            gate_sha256=gate_sha,
            gate_path=gate_path_text,
            authorized_for_vector_db_write=True,
        ),
    )
    _write_json(
        omit_impl_path,
        _proposal_payload(
            gate_sha256=gate_sha,
            gate_path=gate_path_text,
            requires_separate_live_write_implementation_campaign=False,
        ),
    )
    _write_json(
        valid_proposal_path,
        _proposal_payload(
            gate_sha256=gate_sha,
            gate_path=gate_path_text,
        ),
    )

    case_results = [
        _case_result(
            case_name="missing_design_proposal_artifact",
            expected_verdict="FAIL",
            proposal_path=missing_path,
            expected_gate_sha256=gate_sha,
            gate_path=gate_path,
        ),
        _case_result(
            case_name="invalid_design_authorization_phrase",
            expected_verdict="FAIL",
            proposal_path=invalid_phrase_path,
            expected_gate_sha256=gate_sha,
            gate_path=gate_path,
        ),
        _case_result(
            case_name="mismatched_gate_hash",
            expected_verdict="FAIL",
            proposal_path=mismatched_gate_path,
            expected_gate_sha256=gate_sha,
            gate_path=gate_path,
        ),
        _case_result(
            case_name="gate_not_pass",
            expected_verdict="FAIL",
            proposal_path=gate_not_pass_proposal_path,
            expected_gate_sha256=fail_gate_sha,
            gate_path=fail_gate_path,
        ),
        _case_result(
            case_name="proposal_claims_live_write_implementation",
            expected_verdict="FAIL",
            proposal_path=impl_claim_path,
            expected_gate_sha256=gate_sha,
            gate_path=gate_path,
        ),
        _case_result(
            case_name="proposal_claims_live_memory_write",
            expected_verdict="FAIL",
            proposal_path=live_claim_path,
            expected_gate_sha256=gate_sha,
            gate_path=gate_path,
        ),
        _case_result(
            case_name="proposal_claims_vector_db_write",
            expected_verdict="FAIL",
            proposal_path=vector_claim_path,
            expected_gate_sha256=gate_sha,
            gate_path=gate_path,
        ),
        _case_result(
            case_name="proposal_omits_separate_implementation_campaign",
            expected_verdict="FAIL",
            proposal_path=omit_impl_path,
            expected_gate_sha256=gate_sha,
            gate_path=gate_path,
        ),
        _case_result(
            case_name="valid_design_proposal_only",
            expected_verdict="PASS",
            proposal_path=valid_proposal_path,
            expected_gate_sha256=gate_sha,
            gate_path=gate_path,
        ),
    ]

    cases_by_name = {case.case_name: case for case in case_results}
    case_dicts = [case.to_dict() for case in case_results]
    report.proposal_path = str(proposal_dir.resolve())
    report.proposal_json_path = str(valid_proposal_path.resolve())
    report.proposal_report_path = str(report_path.resolve())
    report.proposal_readme_path = str(readme_path.resolve())
    report.proposal_cases = case_dicts
    report.proposal_case_count = len(case_results)

    invalid_failed_closed = all(
        cases_by_name[name].actual_verdict == "FAIL" and cases_by_name[name].detected
        for name in INVALID_PROPOSAL_CASES
    )
    valid_case = cases_by_name["valid_design_proposal_only"]
    valid_passed_proposal_only = (
        valid_case.actual_verdict == "PASS"
        and valid_case.detected
        and valid_case.details["authorized_for_live_write_design_proposal"] is True
        and valid_case.details["authorized_for_live_write_implementation"] is False
        and valid_case.details["authorized_for_live_memory_write"] is False
        and valid_case.details["authorized_for_vector_db_write"] is False
        and valid_case.details["live_memory_write_allowed"] is False
        and valid_case.details["vector_db_write_allowed"] is False
        and valid_case.details["live_write_implemented"] is False
        and valid_case.details["ready_for_live_write_implementation"] is False
    )
    report.all_invalid_proposal_cases_failed_closed = invalid_failed_closed
    report.valid_design_proposal_passed_proposal_only = valid_passed_proposal_only
    report.authorized_for_live_write_design_proposal = valid_passed_proposal_only
    report.authorized_for_live_write_implementation = False
    report.authorized_for_live_memory_write = False
    report.authorized_for_vector_db_write = False
    report.live_memory_write_allowed = False
    report.vector_db_write_allowed = False
    report.live_write_implemented = False
    report.ready_for_live_write_implementation = False
    report.requires_separate_live_write_implementation_campaign = True
    report.requires_separate_operator_approval_for_live_write = True

    _write_readme(readme_path, report)
    report.proposal_readme_sha256 = _sha256_file(readme_path)

    report.artifact_paths = {
        "proposal_dir": report.proposal_path,
        "proposal_json": report.proposal_json_path,
        "proposal_report": report.proposal_report_path,
        "proposal_readme": report.proposal_readme_path,
        "gate_json": report.source_live_write_design_authorization_gate_path,
        "missing_design_proposal_artifact": str(missing_path.resolve()),
        "invalid_design_authorization_phrase": str(invalid_phrase_path.resolve()),
        "mismatched_gate_hash": str(mismatched_gate_path.resolve()),
        "gate_not_pass": str(gate_not_pass_proposal_path.resolve()),
        "proposal_claims_live_write_implementation": str(impl_claim_path.resolve()),
        "proposal_claims_live_memory_write": str(live_claim_path.resolve()),
        "proposal_claims_vector_db_write": str(vector_claim_path.resolve()),
        "proposal_omits_separate_implementation_campaign": str(omit_impl_path.resolve()),
    }

    tracked_paths = (
        proposal_dir,
        cases_dir,
        valid_proposal_path,
        report_path,
        readme_path,
        missing_path,
        invalid_phrase_path,
        mismatched_gate_path,
        gate_not_pass_proposal_path,
        impl_claim_path,
        live_claim_path,
        vector_claim_path,
        omit_impl_path,
        fail_gate_path,
        gate_path,
    )
    paths_inside = all(
        _path_inside_workspace(path, workspace)
        for path in tracked_paths
        if path.exists() or path == missing_path
    )

    checks = {
        "gate_pass": report.live_write_design_authorization_gate_verdict == "PASS",
        "proposal_case_count": report.proposal_case_count == len(REQUIRED_PROPOSAL_CASES),
        "all_required_cases_present": {case.case_name for case in case_results}
        == set(REQUIRED_PROPOSAL_CASES),
        "all_cases_detected": all(case.detected for case in case_results),
        "all_invalid_proposal_cases_failed_closed": (
            report.all_invalid_proposal_cases_failed_closed
        ),
        "valid_design_proposal_passed_proposal_only": (
            report.valid_design_proposal_passed_proposal_only
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
        "live_write_unimplemented": not report.live_write_implemented,
        "implementation_unready": not report.ready_for_live_write_implementation,
        "separate_implementation_campaign_required": (
            report.requires_separate_live_write_implementation_campaign
        ),
        "separate_operator_approval_required": (
            report.requires_separate_operator_approval_for_live_write
        ),
        "design_authorization_phrase_valid": report.design_authorization_phrase_valid,
        "gate_hash_present": len(report.source_live_write_design_authorization_gate_sha256)
        == 64,
        "readme_created": readme_path.is_file(),
        "readme_hash_present": len(report.proposal_readme_sha256) == 64,
        "proposal_paths_inside_workspace": paths_inside,
        "accepted_checkpoint_tag": report.accepted_checkpoint_tag == ACCEPTED_CHECKPOINT_TAG,
        "accepted_checkpoint_hash": report.accepted_checkpoint_hash == ACCEPTED_CHECKPOINT_HASH,
        "blocked_reasons_present": bool(report.live_write_blocked_reason)
        and bool(report.vector_db_write_blocked_reason)
        and bool(report.implementation_blocked_reason),
        "proposal_scope_present": bool(report.proposal_scope),
        "proposal_non_goals_present": bool(report.proposal_non_goals),
    }
    for check_name, passed in checks.items():
        if not passed:
            report.errors.append(f"{check_name} failed")

    joined_steps = " ".join(report.operator_next_steps).lower()
    for marker in (
        "live-write design proposal is recorded",
        "live memory writes remain blocked",
        "vector db writes remain blocked",
        "live-write implementation remains blocked",
        "future live-write implementation requires a separate explicit campaign after design approval",
        "separate operator approval is still required for live writes",
    ):
        if marker not in joined_steps:
            report.errors.append(f"operator_next_steps missing: {marker}")

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
    _write_json(report_path, report.to_dict())
    try:
        loaded_report = _load_json(report_path)
        report.proposal_report_valid_json = isinstance(loaded_report, dict)
        missing_fields = [
            field_name for field_name in REQUIRED_REPORT_FIELDS if field_name not in loaded_report
        ]
        if missing_fields:
            report.proposal_report_valid_json = False
            report.errors.append("proposal report missing fields: " + ", ".join(missing_fields))
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        report.proposal_report_valid_json = False
        report.errors.append(f"proposal_report_json_invalid: {exc}")

    try:
        loaded_proposal = _load_json(valid_proposal_path)
        report.proposal_json_valid = (
            isinstance(loaded_proposal, dict)
            and loaded_proposal.get("design_authorization_phrase") == DESIGN_AUTHORIZATION_PHRASE
        )
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        report.proposal_json_valid = False
        report.errors.append(f"proposal_json_invalid: {exc}")

    if not report.proposal_json_valid or not report.proposal_report_valid_json:
        report.verdict = "FAIL"
        if "proposal JSON is invalid" not in report.errors and not report.proposal_json_valid:
            report.errors.append("proposal JSON is invalid")
        if (
            "proposal report JSON is invalid" not in report.errors
            and not report.proposal_report_valid_json
        ):
            report.errors.append("proposal report JSON is invalid")

    if report.errors:
        report.verdict = "FAIL"
    _write_json(report_path, report.to_dict())
    return report


def run_memory_review_approved_promotion_live_write_design_proposal_smoke(
    *,
    base_dir: Path | None = None,
    keep_temp: bool = False,
) -> LiveWriteDesignProposalReport:
    """Build and validate a dry-run live-write design proposal packet."""
    owned_temp = base_dir is None
    workspace = (
        Path(tempfile.mkdtemp(prefix="elysia_lwdp_"))
        if owned_temp
        else _reject_dangerous_base(Path(base_dir))
    )
    workspace.mkdir(parents=True, exist_ok=True)
    try:
        try:
            report = _build_design_proposal(workspace)
        except Exception as exc:
            report = LiveWriteDesignProposalReport(
                verdict="FAIL",
                workspace=str(workspace.resolve()),
                workspace_preserved=(not owned_temp) or keep_temp,
                autonomy_enabled=_read_autonomy_enabled(),
                errors=[f"design_proposal_build_failed: {exc}"],
            )
        report.workspace_preserved = (not owned_temp) or keep_temp
        return report
    finally:
        if owned_temp and not keep_temp:
            shutil.rmtree(workspace, ignore_errors=True)


def format_design_proposal_summary(report: LiveWriteDesignProposalReport) -> str:
    lines = [
        "Memory review approved promotion live-write design proposal smoke",
        "=" * 70,
        f"Verdict: {report.verdict}",
        f"Workspace: {report.workspace}",
        f"Proposal JSON: {report.proposal_json_path}",
        f"Proposal README: {report.proposal_readme_path}",
        f"Phrase: {report.design_authorization_phrase}",
        f"Phrase valid: {report.design_authorization_phrase_valid}",
        f"Accepted checkpoint: {report.accepted_checkpoint_tag}",
        f"Accepted hash: {report.accepted_checkpoint_hash}",
        f"Gate verdict: {report.live_write_design_authorization_gate_verdict}",
        (
            "Authorized for live-write design proposal: "
            f"{report.authorized_for_live_write_design_proposal}"
        ),
        f"Live memory write allowed: {report.live_memory_write_allowed}",
        f"Vector DB write allowed: {report.vector_db_write_allowed}",
        f"Live-write implemented: {report.live_write_implemented}",
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
            "Run local-only Memory review approved promotion live-write "
            "design proposal smoke."
        ),
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON to stdout")
    parser.add_argument("--base-dir", type=Path, default=None)
    parser.add_argument("--keep-temp", action="store_true")
    args = parser.parse_args(argv)
    try:
        report = run_memory_review_approved_promotion_live_write_design_proposal_smoke(
            base_dir=args.base_dir,
            keep_temp=args.keep_temp,
        )
    except (ValueError, OSError) as exc:
        report = LiveWriteDesignProposalReport(
            verdict="FAIL",
            workspace=str(args.base_dir or ""),
            errors=[str(exc)],
            autonomy_enabled=_read_autonomy_enabled(),
        )
    if args.json:
        print(json.dumps(report.to_dict(), indent=2, ensure_ascii=False))
    else:
        print(format_design_proposal_summary(report))
    return 0 if report.verdict == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
