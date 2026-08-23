#!/usr/bin/env python3
"""Dry-run/local smoke proving final readiness packets detect tampering.

This smoke builds a valid final readiness packet from local fixtures, validates
the clean packet as PASS, then writes isolated corrupted packet copies and
checks that each one returns FAIL with a specific error token. It never calls
models, embeddings, networks, live accounts, UI routes, or live runtime
memory/vector DB.
"""

from __future__ import annotations

import argparse
import copy
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

from run_memory_review_approved_promotion_final_readiness_packet_smoke import (  # noqa: E402
    APPROVAL_TOKEN_PHRASE,
    EDITED_TEXT_MARKER,
    PACKET_DIRNAME,
    PACKET_JSON_FILENAME,
    PACKET_README_FILENAME,
    REQUIRED_SAFETY_CHAIN_STAGES,
    run_memory_review_approved_promotion_final_readiness_packet_smoke,
)

REQUIRED_PACKET_FIELDS = (
    "verdict",
    "workspace",
    "packet_path",
    "packet_json_path",
    "packet_readme_path",
    "packet_readme_sha256",
    "source_bundle_path",
    "source_bundle_sha256",
    "source_promotion_manifest_sha256",
    "source_operator_handoff_sha256",
    "source_approval_gate_sha256",
    "source_staging_manifest_sha256",
    "source_staging_tamper_evidence_sha256",
    "source_live_write_blockade_sha256",
    "source_live_write_blockade_tamper_evidence_sha256",
    "approval_token_phrase",
    "promotion_item_count",
    "approved_candidate_count",
    "edited_candidate_count",
    "excluded_rejected_count",
    "ready_for_operator_review",
    "ready_for_operator_approved_staging",
    "ready_for_live_memory_write",
    "future_live_write_allowed",
    "requires_explicit_operator_approval",
    "requires_future_live_write_milestone",
    "live_write_blocked_reason",
    "vector_db_write_blocked_reason",
    "approved_items",
    "safety_chain",
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

UNSAFE_PACKET_METADATA = (
    ("dry_run", False, "dry_run=false"),
    ("local_only", False, "local_only=false"),
    ("model_called", True, "model_called=true"),
    ("embeddings_used", True, "embeddings_used=true"),
    ("live_memory_written", True, "live_memory_written=true"),
    ("live_vector_db_written", True, "live_vector_db_written=true"),
    ("account_api_network_accessed", True, "account_api_network_accessed=true"),
    ("autonomy_enabled", True, "autonomy_enabled=true"),
)

REQUIRED_TAMPER_CASES = (
    "malformed_json",
    "missing_required_packet_field",
    "packet_readme_hash_mismatch",
    "source_bundle_hash_mismatch",
    "source_promotion_manifest_hash_mismatch",
    "source_operator_handoff_hash_mismatch",
    "source_approval_gate_hash_mismatch",
    "source_staging_manifest_hash_mismatch",
    "source_staging_tamper_evidence_hash_mismatch",
    "source_live_write_blockade_hash_mismatch",
    "source_live_write_blockade_tamper_evidence_hash_mismatch",
    "approval_token_phrase_missing",
    "approved_item_removed",
    "edited_item_removed",
    "edited_promoted_text_changed",
    "rejected_item_included",
    "promotion_item_count_mismatch",
    "excluded_rejected_count_mismatch",
    "safety_chain_missing_stage",
    "safety_chain_stage_failed",
    "ready_for_operator_review_false",
    "ready_for_operator_approved_staging_false",
    "ready_for_live_memory_write_true",
    "future_live_write_allowed_true",
    "requires_explicit_operator_approval_false",
    "requires_future_live_write_milestone_false",
    "live_write_blocked_reason_missing",
    "vector_db_write_blocked_reason_missing",
    "operator_next_steps_missing_future_milestone",
    "unsafe_metadata",
)

SOURCE_HASH_SPECS = (
    ("source_bundle_sha256", "source_bundle_hash_mismatch", "bundle_readme"),
    (
        "source_promotion_manifest_sha256",
        "source_promotion_manifest_hash_mismatch",
        "promotion_manifest",
    ),
    (
        "source_operator_handoff_sha256",
        "source_operator_handoff_hash_mismatch",
        "operator_handoff",
    ),
    (
        "source_approval_gate_sha256",
        "source_approval_gate_hash_mismatch",
        "approval_gate",
    ),
    (
        "source_staging_manifest_sha256",
        "source_staging_manifest_hash_mismatch",
        "staging_manifest",
    ),
    (
        "source_staging_tamper_evidence_sha256",
        "source_staging_tamper_evidence_hash_mismatch",
        "staging_tamper_receipt",
    ),
    (
        "source_live_write_blockade_sha256",
        "source_live_write_blockade_hash_mismatch",
        "live_write_blockade",
    ),
    (
        "source_live_write_blockade_tamper_evidence_sha256",
        "source_live_write_blockade_tamper_evidence_hash_mismatch",
        "live_write_blockade_tamper",
    ),
)


@dataclass
class TamperCaseResult:
    case_name: str
    expected_verdict: str
    actual_verdict: str
    detected: bool
    detected_error_type: str
    details: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class FinalReadinessPacketTamperEvidenceReport:
    verdict: str
    workspace: str
    clean_packet_verdict: str = "UNKNOWN"
    tamper_case_count: int = 0
    tamper_cases: List[Dict[str, Any]] = field(default_factory=list)
    all_tamper_cases_detected: bool = False
    detected_error_types: List[str] = field(default_factory=list)
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
    clean_packet_path: str = ""
    clean_packet_json_path: str = ""
    clean_packet_still_passes: bool = False
    tamper_paths_inside_workspace: bool = False
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
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path


def _write_raw(path: Path, raw: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(raw, encoding="utf-8")
    return path


def _source_paths(workspace: Path, packet: Dict[str, Any]) -> Dict[str, Path]:
    root = Path(str(packet.get("workspace") or workspace)).resolve()
    readme = Path(str(packet.get("packet_readme_path") or ""))
    if not readme.is_file():
        readme = root / PACKET_DIRNAME / PACKET_README_FILENAME
    bundle = Path(str(packet.get("source_bundle_path") or root / "approved_promotion_bundle"))
    return {
        "packet_readme": readme,
        "bundle_readme": bundle / "README.md",
        "promotion_manifest": bundle / "promotion_manifest.json",
        "operator_handoff": (
            root / "approved_promotion_operator_handoff" / "operator_handoff.json"
        ),
        "approval_gate": (
            root
            / "approved_promotion_operator_approval_gate"
            / "operator_approval_gate.json"
        ),
        "staging_manifest": (
            root
            / "approved_promotion_operator_approved_staging"
            / "operator_approved_staging_manifest.json"
        ),
        "staging_tamper_receipt": (
            root / "ap_ste_receipt" / "staging_tamper_evidence_receipt.json"
        ),
        "live_write_blockade": (
            root
            / "approved_promotion_live_write_blockade"
            / "live_write_blockade_report.json"
        ),
        "live_write_blockade_tamper": (
            root
            / "ap_lwbte_receipt"
            / "live_write_blockade_tamper_evidence_report.json"
        ),
    }


def audit_final_readiness_packet(packet_path: Path) -> Tuple[str, List[str]]:
    """Local-only checker for a final readiness packet JSON file."""
    errors: List[str] = []
    if not packet_path.is_file():
        return "FAIL", [f"missing_packet_file: {packet_path}"]

    try:
        packet = json.loads(packet_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return "FAIL", [f"malformed_json: packet is not valid JSON ({exc})"]

    if not isinstance(packet, dict):
        return "FAIL", ["malformed_json: packet root is not a JSON object"]

    missing_fields = [
        field_name for field_name in REQUIRED_PACKET_FIELDS if field_name not in packet
    ]
    if missing_fields:
        errors.append("missing_required_packet_field: missing " + ", ".join(missing_fields))

    workspace = Path(str(packet.get("workspace") or packet_path.parent.parent))
    sources = _source_paths(workspace, packet)

    recorded_readme = str(packet.get("packet_readme_sha256") or "")
    if sources["packet_readme"].is_file() and recorded_readme:
        actual_readme = _sha256_file(sources["packet_readme"])
        if recorded_readme != actual_readme:
            errors.append(
                "packet_readme_hash_mismatch: packet_readme_sha256 does not match file"
            )

    for field_name, token, source_key in SOURCE_HASH_SPECS:
        recorded = str(packet.get(field_name) or "")
        source_path = sources[source_key]
        if field_name not in packet or not recorded or not source_path.is_file():
            continue
        if recorded != _sha256_file(source_path):
            errors.append(f"{token}: {field_name} does not match file")

    token_phrase = str(packet.get("approval_token_phrase") or "").strip()
    if "approval_token_phrase" in packet and token_phrase != APPROVAL_TOKEN_PHRASE:
        errors.append("approval_token_phrase_missing: approval_token_phrase is missing")

    items = packet.get("approved_items")
    if isinstance(items, list):
        types = [str(item.get("decision_type") or "") for item in items if isinstance(item, dict)]
        texts = [str(item.get("promoted_text") or "") for item in items if isinstance(item, dict)]
        if "approved" not in types:
            errors.append("approved_item_removed: approved item is missing")
        if "edited" not in types:
            errors.append("edited_item_removed: edited item is missing")
        if "edited" in types and not any(EDITED_TEXT_MARKER in text for text in texts):
            errors.append("edited_promoted_text_changed: edited promoted text was changed")
        if "rejected" in types:
            errors.append("rejected_item_included: rejected item is included")

    if (
        "promotion_item_count" in packet
        and int(packet.get("promotion_item_count") or 0) != 2
    ):
        errors.append(
            "promotion_item_count_mismatch: "
            f"promotion_item_count={packet.get('promotion_item_count')}"
        )
    if (
        "excluded_rejected_count" in packet
        and int(packet.get("excluded_rejected_count") or 0) != 1
    ):
        errors.append(
            "excluded_rejected_count_mismatch: "
            f"excluded_rejected_count={packet.get('excluded_rejected_count')}"
        )

    chain = packet.get("safety_chain")
    if isinstance(chain, dict):
        missing_stages = [stage for stage in REQUIRED_SAFETY_CHAIN_STAGES if stage not in chain]
        if missing_stages:
            errors.append(
                "safety_chain_missing_stage: missing " + ", ".join(missing_stages)
            )
        failed_stages = [
            stage
            for stage in REQUIRED_SAFETY_CHAIN_STAGES
            if stage in chain and str(chain.get(stage) or "") != "PASS"
        ]
        if failed_stages:
            errors.append(
                "safety_chain_stage_failed: " + ", ".join(failed_stages)
            )

    if (
        "ready_for_operator_review" in packet
        and packet.get("ready_for_operator_review") is not True
    ):
        errors.append("ready_for_operator_review_false: ready_for_operator_review is not true")
    if (
        "ready_for_operator_approved_staging" in packet
        and packet.get("ready_for_operator_approved_staging") is not True
    ):
        errors.append(
            "ready_for_operator_approved_staging_false: "
            "ready_for_operator_approved_staging is not true"
        )
    if packet.get("ready_for_live_memory_write") is True:
        errors.append("ready_for_live_memory_write_true: ready_for_live_memory_write=true")
    if packet.get("future_live_write_allowed") is True:
        errors.append("future_live_write_allowed_true: future_live_write_allowed=true")
    if (
        "requires_explicit_operator_approval" in packet
        and packet.get("requires_explicit_operator_approval") is not True
    ):
        errors.append(
            "requires_explicit_operator_approval_false: "
            "requires_explicit_operator_approval is not true"
        )
    if (
        "requires_future_live_write_milestone" in packet
        and packet.get("requires_future_live_write_milestone") is not True
    ):
        errors.append(
            "requires_future_live_write_milestone_false: "
            "requires_future_live_write_milestone is not true"
        )

    if "live_write_blocked_reason" in packet and not str(
        packet.get("live_write_blocked_reason") or ""
    ).strip():
        errors.append("live_write_blocked_reason_missing: live_write_blocked_reason is empty")
    if "vector_db_write_blocked_reason" in packet and not str(
        packet.get("vector_db_write_blocked_reason") or ""
    ).strip():
        errors.append(
            "vector_db_write_blocked_reason_missing: vector_db_write_blocked_reason is empty"
        )

    next_steps = packet.get("operator_next_steps")
    if "operator_next_steps" in packet:
        joined = " ".join(str(step) for step in next_steps) if isinstance(next_steps, list) else ""
        if "milestone" not in joined.lower():
            errors.append(
                "operator_next_steps_missing_future_milestone: "
                "operator_next_steps does not require a future milestone"
            )

    for field_name, unsafe_value, label in UNSAFE_PACKET_METADATA:
        if field_name in packet and packet.get(field_name) is unsafe_value:
            errors.append(f"unsafe_metadata: packet {label}")

    verdict = "PASS" if not errors else "FAIL"
    return verdict, errors


def _copy_packet(packet: Dict[str, Any]) -> Dict[str, Any]:
    return copy.deepcopy(packet)


def _error_type(error: str) -> str:
    return error.split(":", 1)[0].strip()


def _first_item_of_type(packet: Dict[str, Any], decision_type: str) -> Dict[str, Any] | None:
    for item in packet.get("approved_items") or []:
        if isinstance(item, dict) and item.get("decision_type") == decision_type:
            return item
    return None


def _load_clean_packet(workspace: Path) -> Tuple[Path, Dict[str, Any], Dict[str, str]]:
    packet_report = run_memory_review_approved_promotion_final_readiness_packet_smoke(
        base_dir=workspace,
        keep_temp=True,
    )
    if packet_report.verdict != "PASS":
        raise ValueError(
            "Final readiness packet smoke did not pass while building clean packet: "
            + "; ".join(packet_report.errors)
        )
    packet_path = Path(packet_report.packet_json_path)
    if not packet_path.is_file():
        raise ValueError(f"Clean final readiness packet was not created: {packet_path}")
    packet = json.loads(packet_path.read_text(encoding="utf-8"))
    artifact_paths = {
        "clean_packet_dir": packet_report.packet_path,
        "clean_packet_json": str(packet_path.resolve()),
        "clean_packet_readme": str(Path(packet_report.packet_readme_path).resolve()),
    }
    return packet_path, packet, artifact_paths


def _run_tamper_flow(
    workspace: Path,
    *,
    workspace_preserved: bool,
) -> FinalReadinessPacketTamperEvidenceReport:
    errors: List[str] = []
    case_paths: Dict[str, str] = {}
    report = FinalReadinessPacketTamperEvidenceReport(
        verdict="FAIL",
        workspace=str(workspace.resolve()),
        workspace_preserved=workspace_preserved,
        autonomy_enabled=_read_autonomy_enabled(),
    )
    if report.autonomy_enabled:
        report.errors.append(
            "Autonomy is enabled; final readiness packet tamper evidence smoke is blocked."
        )
        return report

    clean_packet_path, clean_packet, artifact_paths = _load_clean_packet(workspace)
    report.clean_packet_json_path = str(clean_packet_path.resolve())
    report.clean_packet_path = artifact_paths.get("clean_packet_dir", "")
    tamper_dir = workspace / "tampered_final_readiness_packets"
    tamper_dir.mkdir(parents=True, exist_ok=True)

    clean_verdict, clean_errors = audit_final_readiness_packet(clean_packet_path)
    report.clean_packet_verdict = clean_verdict
    report.clean_packet_still_passes = clean_verdict == "PASS" and not clean_errors
    if not report.clean_packet_still_passes:
        errors.append(f"Clean final readiness packet did not pass: {clean_errors}")

    cases: List[TamperCaseResult] = []

    def _record_case(name: str, expected_token: str, path: Path) -> None:
        verdict, case_errors = audit_final_readiness_packet(path)
        token_found = any(expected_token in error for error in case_errors)
        detected_types = [_error_type(error) for error in case_errors]
        detected_error_type = expected_token if token_found else (
            detected_types[0] if detected_types else ""
        )
        cases.append(
            TamperCaseResult(
                case_name=name,
                expected_verdict="FAIL",
                actual_verdict=verdict,
                detected=verdict == "FAIL" and token_found,
                detected_error_type=detected_error_type,
                details=case_errors,
            )
        )
        case_paths[name] = str(path.resolve())

    malformed_path = tamper_dir / "malformed_json_packet.json"
    _write_raw(malformed_path, "{ this is not valid json\n")
    _record_case("malformed_json", "malformed_json", malformed_path)

    missing_field = _copy_packet(clean_packet)
    missing_field.pop("workspace", None)
    missing_field_path = tamper_dir / "missing_required_packet_field.json"
    _write_json(missing_field_path, missing_field)
    _record_case("missing_required_packet_field", "missing_required_packet_field", missing_field_path)

    readme_mismatch = _copy_packet(clean_packet)
    readme_mismatch["packet_readme_sha256"] = "0" * 64
    readme_mismatch_path = tamper_dir / "packet_readme_hash_mismatch.json"
    _write_json(readme_mismatch_path, readme_mismatch)
    _record_case("packet_readme_hash_mismatch", "packet_readme_hash_mismatch", readme_mismatch_path)

    for field_name, token, _source_key in SOURCE_HASH_SPECS:
        mutated = _copy_packet(clean_packet)
        mutated[field_name] = "0" * 64
        mutated_path = tamper_dir / f"{token}.json"
        _write_json(mutated_path, mutated)
        _record_case(token, token, mutated_path)

    missing_token = _copy_packet(clean_packet)
    missing_token["approval_token_phrase"] = ""
    missing_token_path = tamper_dir / "approval_token_phrase_missing.json"
    _write_json(missing_token_path, missing_token)
    _record_case("approval_token_phrase_missing", "approval_token_phrase_missing", missing_token_path)

    approved_removed = _copy_packet(clean_packet)
    approved_removed["approved_items"] = [
        item
        for item in approved_removed.get("approved_items") or []
        if item.get("decision_type") != "approved"
    ]
    approved_removed_path = tamper_dir / "approved_item_removed.json"
    _write_json(approved_removed_path, approved_removed)
    _record_case("approved_item_removed", "approved_item_removed", approved_removed_path)

    edited_removed = _copy_packet(clean_packet)
    edited_removed["approved_items"] = [
        item
        for item in edited_removed.get("approved_items") or []
        if item.get("decision_type") != "edited"
    ]
    edited_removed_path = tamper_dir / "edited_item_removed.json"
    _write_json(edited_removed_path, edited_removed)
    _record_case("edited_item_removed", "edited_item_removed", edited_removed_path)

    edited_changed = _copy_packet(clean_packet)
    edited_item = _first_item_of_type(edited_changed, "edited")
    if edited_item is not None:
        edited_item["promoted_text"] = "Silently altered promoted text"
    edited_changed_path = tamper_dir / "edited_promoted_text_changed.json"
    _write_json(edited_changed_path, edited_changed)
    _record_case("edited_promoted_text_changed", "edited_promoted_text_changed", edited_changed_path)

    rejected_included = _copy_packet(clean_packet)
    template = _first_item_of_type(rejected_included, "approved") or {}
    rejected_included.setdefault("approved_items", []).append(
        {
            **template,
            "candidate_id": "rejected-final-readiness-tamper-candidate",
            "decision_type": "rejected",
            "promoted_text": "Rejected candidate should stay excluded.",
        }
    )
    rejected_included_path = tamper_dir / "rejected_item_included.json"
    _write_json(rejected_included_path, rejected_included)
    _record_case("rejected_item_included", "rejected_item_included", rejected_included_path)

    count_mismatch = _copy_packet(clean_packet)
    count_mismatch["promotion_item_count"] = 3
    count_mismatch_path = tamper_dir / "promotion_item_count_mismatch.json"
    _write_json(count_mismatch_path, count_mismatch)
    _record_case("promotion_item_count_mismatch", "promotion_item_count_mismatch", count_mismatch_path)

    excluded_mismatch = _copy_packet(clean_packet)
    excluded_mismatch["excluded_rejected_count"] = 0
    excluded_mismatch_path = tamper_dir / "excluded_rejected_count_mismatch.json"
    _write_json(excluded_mismatch_path, excluded_mismatch)
    _record_case(
        "excluded_rejected_count_mismatch",
        "excluded_rejected_count_mismatch",
        excluded_mismatch_path,
    )

    missing_stage = _copy_packet(clean_packet)
    chain = dict(missing_stage.get("safety_chain") or {})
    chain.pop("live_write_blockade", None)
    missing_stage["safety_chain"] = chain
    missing_stage_path = tamper_dir / "safety_chain_missing_stage.json"
    _write_json(missing_stage_path, missing_stage)
    _record_case("safety_chain_missing_stage", "safety_chain_missing_stage", missing_stage_path)

    failed_stage = _copy_packet(clean_packet)
    failed_chain = dict(failed_stage.get("safety_chain") or {})
    failed_chain["live_write_blockade"] = "FAIL"
    failed_stage["safety_chain"] = failed_chain
    failed_stage_path = tamper_dir / "safety_chain_stage_failed.json"
    _write_json(failed_stage_path, failed_stage)
    _record_case("safety_chain_stage_failed", "safety_chain_stage_failed", failed_stage_path)

    review_false = _copy_packet(clean_packet)
    review_false["ready_for_operator_review"] = False
    review_false_path = tamper_dir / "ready_for_operator_review_false.json"
    _write_json(review_false_path, review_false)
    _record_case("ready_for_operator_review_false", "ready_for_operator_review_false", review_false_path)

    staging_false = _copy_packet(clean_packet)
    staging_false["ready_for_operator_approved_staging"] = False
    staging_false_path = tamper_dir / "ready_for_operator_approved_staging_false.json"
    _write_json(staging_false_path, staging_false)
    _record_case(
        "ready_for_operator_approved_staging_false",
        "ready_for_operator_approved_staging_false",
        staging_false_path,
    )

    ready_live = _copy_packet(clean_packet)
    ready_live["ready_for_live_memory_write"] = True
    ready_live_path = tamper_dir / "ready_for_live_memory_write_true.json"
    _write_json(ready_live_path, ready_live)
    _record_case("ready_for_live_memory_write_true", "ready_for_live_memory_write_true", ready_live_path)

    future_allowed = _copy_packet(clean_packet)
    future_allowed["future_live_write_allowed"] = True
    future_allowed_path = tamper_dir / "future_live_write_allowed_true.json"
    _write_json(future_allowed_path, future_allowed)
    _record_case("future_live_write_allowed_true", "future_live_write_allowed_true", future_allowed_path)

    approval_false = _copy_packet(clean_packet)
    approval_false["requires_explicit_operator_approval"] = False
    approval_false_path = tamper_dir / "requires_explicit_operator_approval_false.json"
    _write_json(approval_false_path, approval_false)
    _record_case(
        "requires_explicit_operator_approval_false",
        "requires_explicit_operator_approval_false",
        approval_false_path,
    )

    milestone_false = _copy_packet(clean_packet)
    milestone_false["requires_future_live_write_milestone"] = False
    milestone_false_path = tamper_dir / "requires_future_live_write_milestone_false.json"
    _write_json(milestone_false_path, milestone_false)
    _record_case(
        "requires_future_live_write_milestone_false",
        "requires_future_live_write_milestone_false",
        milestone_false_path,
    )

    memory_reason_missing = _copy_packet(clean_packet)
    memory_reason_missing["live_write_blocked_reason"] = ""
    memory_reason_path = tamper_dir / "live_write_blocked_reason_missing.json"
    _write_json(memory_reason_path, memory_reason_missing)
    _record_case(
        "live_write_blocked_reason_missing",
        "live_write_blocked_reason_missing",
        memory_reason_path,
    )

    vector_reason_missing = _copy_packet(clean_packet)
    vector_reason_missing["vector_db_write_blocked_reason"] = ""
    vector_reason_path = tamper_dir / "vector_db_write_blocked_reason_missing.json"
    _write_json(vector_reason_path, vector_reason_missing)
    _record_case(
        "vector_db_write_blocked_reason_missing",
        "vector_db_write_blocked_reason_missing",
        vector_reason_path,
    )

    next_steps_missing = _copy_packet(clean_packet)
    next_steps_missing["operator_next_steps"] = [
        "This packet is final dry-run readiness only."
    ]
    next_steps_path = tamper_dir / "operator_next_steps_missing_future_milestone.json"
    _write_json(next_steps_path, next_steps_missing)
    _record_case(
        "operator_next_steps_missing_future_milestone",
        "operator_next_steps_missing_future_milestone",
        next_steps_path,
    )

    unsafe = _copy_packet(clean_packet)
    unsafe["dry_run"] = False
    unsafe["local_only"] = False
    unsafe["model_called"] = True
    unsafe["embeddings_used"] = True
    unsafe["live_memory_written"] = True
    unsafe["live_vector_db_written"] = True
    unsafe["account_api_network_accessed"] = True
    unsafe["autonomy_enabled"] = True
    unsafe_path = tamper_dir / "unsafe_metadata.json"
    _write_json(unsafe_path, unsafe)
    _record_case("unsafe_metadata", "unsafe_metadata", unsafe_path)

    report.tamper_cases = [case.to_dict() for case in cases]
    report.tamper_case_count = len(cases)
    report.detected_error_types = sorted(
        {case.detected_error_type for case in cases if case.detected_error_type}
    )
    report.all_tamper_cases_detected = all(case.detected for case in cases) and [
        case.case_name for case in cases
    ] == list(REQUIRED_TAMPER_CASES)
    if not report.all_tamper_cases_detected:
        missing = [
            case.case_name for case in cases if not case.detected
        ]
        extra = [case.case_name for case in cases if case.case_name not in REQUIRED_TAMPER_CASES]
        if [case.case_name for case in cases] != list(REQUIRED_TAMPER_CASES):
            errors.append("required_tamper_case_set_mismatch")
        if missing:
            errors.append("undetected_tamper_cases: " + ", ".join(missing))
        if extra:
            errors.append("unexpected_tamper_cases: " + ", ".join(extra))

    still_clean, still_clean_errors = audit_final_readiness_packet(clean_packet_path)
    report.clean_packet_still_passes = still_clean == "PASS" and not still_clean_errors
    if not report.clean_packet_still_passes:
        errors.append(f"Clean packet no longer passes after tamper copies: {still_clean_errors}")

    report.tamper_paths_inside_workspace = all(
        _path_inside_workspace(Path(path), workspace) for path in case_paths.values()
    )
    if not report.tamper_paths_inside_workspace:
        errors.append("tamper_paths_outside_workspace")

    report.artifact_paths = {
        **artifact_paths,
        "tamper_dir": str(tamper_dir.resolve()),
        **{f"tampered_{name}": path for name, path in case_paths.items()},
    }
    report.errors = errors
    report.verdict = "PASS" if not errors else "FAIL"
    return report


def run_memory_review_approved_promotion_final_readiness_packet_tamper_evidence_smoke(
    *,
    base_dir: Path | None = None,
    keep_temp: bool = False,
) -> FinalReadinessPacketTamperEvidenceReport:
    """Build a clean final readiness packet and prove tampered variants fail."""
    owned_temp = base_dir is None
    workspace = (
        Path(tempfile.mkdtemp(prefix="elysia_frpte_"))
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


def format_operator_summary(report: FinalReadinessPacketTamperEvidenceReport) -> str:
    lines = [
        "Memory review approved promotion final readiness packet tamper evidence smoke",
        "=" * 74,
        f"Verdict: {report.verdict}",
        f"Workspace: {report.workspace}",
        f"Clean packet verdict: {report.clean_packet_verdict}",
        f"Tamper case count: {report.tamper_case_count}",
        f"All tamper cases detected: {report.all_tamper_cases_detected}",
        "",
        "Tamper cases:",
    ]
    for case in report.tamper_cases:
        lines.append(
            f"  {case.get('case_name')}: expected={case.get('expected_verdict')} "
            f"actual={case.get('actual_verdict')} detected={case.get('detected')} "
            f"error_type={case.get('detected_error_type')}"
        )
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
            "packet tamper evidence smoke."
        ),
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON to stdout")
    parser.add_argument("--base-dir", type=Path, default=None)
    parser.add_argument("--keep-temp", action="store_true")
    args = parser.parse_args(argv)
    try:
        report = run_memory_review_approved_promotion_final_readiness_packet_tamper_evidence_smoke(
            base_dir=args.base_dir,
            keep_temp=args.keep_temp,
        )
    except ValueError as exc:
        report = FinalReadinessPacketTamperEvidenceReport(
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
