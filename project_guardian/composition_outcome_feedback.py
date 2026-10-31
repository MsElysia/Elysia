"""Durable host-verified composition outcome feedback (not personal memory).

Stores bounded execution outcomes for evidence-based capability ranking.
Model claims, documents, and conversation text cannot manufacture entries.
Authorization is never granted or inherited from this store.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
import re
import threading
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple


SCHEMA = "elysia.composition-outcome-feedback.v1"
DEFAULT_MIN_ATTEMPTS = 10
DEFAULT_MIN_TASK_INSTANCES = 3
# Cap correlated retries within one task instance so one conversation cannot dominate.
DEFAULT_MAX_OBSERVATIONS_PER_INSTANCE = 2
MAX_ENTRIES = 2000
_EXEC_ID_RE = re.compile(r"^exec_[a-f0-9]{16}$")
_CAP_RE = re.compile(r"^[a-z][a-z0-9_.-]{1,79}$")

# Capability → output types it can satisfy (general, not profession-specific).
CAPABILITY_OUTPUT_TYPES: Dict[str, frozenset] = {
    "local.documents.search": frozenset({"document_excerpts"}),
    "calculator.labor": frozenset({"usd_amount"}),
    "compose.extract_fields": frozenset({"structured_fields"}),
    "compose.extract_records": frozenset({"structured_records"}),
    "compose.aggregate_usd": frozenset({"usd_aggregate"}),
    "compose.synthesize": frozenset({"grounded_draft", "grounded_summary"}),
    "estimate.assemble": frozenset({"usd_aggregate"}),
    "estimate.draft": frozenset({"grounded_draft"}),
}

CAPABILITY_DEFAULT_INPUT: Dict[str, str] = {
    "local.documents.search": "free_text",
    "calculator.labor": "numeric",
    "compose.extract_fields": "labeled_text",
    "compose.extract_records": "markdown_table",
    "compose.aggregate_usd": "numeric",
    "compose.synthesize": "free_text",
    "estimate.assemble": "numeric",
    "estimate.draft": "free_text",
}

CAPABILITY_VERIFICATION: Dict[str, str] = {
    "local.documents.search": "evidence_criteria",
    "calculator.labor": "deterministic_recompute",
    "compose.extract_fields": "source_span",
    "compose.extract_records": "source_span",
    "compose.aggregate_usd": "deterministic_recompute",
    "compose.synthesize": "grounded_amounts",
    "estimate.assemble": "deterministic_recompute",
    "estimate.draft": "grounded_amounts",
}

# Normalized failure classes for operator-facing diagnostics.
FAILURE_CLASS_UNAVAILABLE = "unavailable_dependency"
FAILURE_CLASS_UNAUTHORIZED = "unauthorized_request"
FAILURE_CLASS_INVALID_INPUT = "invalid_input"
FAILURE_CLASS_UNSUCCESSFUL = "unsuccessful_execution"
FAILURE_CLASS_INSUFFICIENT_EVIDENCE = "insufficient_evidence"
FAILURE_CLASS_ENVIRONMENT = "environment_outage"


class OutcomeFeedbackError(ValueError):
    pass


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def resolve_outcome_feedback_root(disposable_root: Path | str) -> Path:
    root = Path(disposable_root)
    return root / "data" / "composition_outcome_feedback"


def _atomic_write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    backup = path.with_suffix(path.suffix + ".bak")
    tmp = path.with_suffix(path.suffix + ".tmp")
    data = json.dumps(payload, indent=2, ensure_ascii=True) + "\n"
    previous: Optional[str] = None
    if path.is_file():
        try:
            previous = path.read_text(encoding="utf-8")
            backup.write_text(previous, encoding="utf-8")
        except OSError:
            previous = None
    try:
        tmp.write_text(data, encoding="utf-8")
        os.replace(str(tmp), str(path))
        loaded = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(loaded, dict) or loaded.get("schema") != payload.get("schema"):
            raise OutcomeFeedbackError("outcome store readback failed")
    except Exception:
        # Restore prior content if present so a bad write cannot wipe history.
        if previous is not None:
            try:
                path.write_text(previous, encoding="utf-8")
            except OSError:
                if backup.is_file():
                    try:
                        os.replace(str(backup), str(path))
                    except OSError:
                        pass
        raise


def normalize_failure_class(failure_category: Optional[str]) -> Optional[str]:
    if not failure_category:
        return None
    key = str(failure_category).strip().lower()
    mapping = {
        "evidence_criteria_unmet": FAILURE_CLASS_INSUFFICIENT_EVIDENCE,
        "tool_ok_insufficient_evidence": FAILURE_CLASS_INSUFFICIENT_EVIDENCE,
        "missing_information": FAILURE_CLASS_INSUFFICIENT_EVIDENCE,
        "ambiguous_information": FAILURE_CLASS_INSUFFICIENT_EVIDENCE,
        "conflicting_evidence": FAILURE_CLASS_INSUFFICIENT_EVIDENCE,
        "invalid_arguments": FAILURE_CLASS_INVALID_INPUT,
        "incorrect_result": FAILURE_CLASS_UNSUCCESSFUL,
        "tool_exception": FAILURE_CLASS_UNSUCCESSFUL,
        "recoverable_failure": FAILURE_CLASS_UNSUCCESSFUL,
        "terminal_failure": FAILURE_CLASS_UNSUCCESSFUL,
        "unauthorized": FAILURE_CLASS_UNAUTHORIZED,
        "authorization_required": FAILURE_CLASS_UNAUTHORIZED,
        "policy_denied": FAILURE_CLASS_UNAUTHORIZED,
        "unavailable_capability": FAILURE_CLASS_UNAVAILABLE,
        "upstream_stale": FAILURE_CLASS_ENVIRONMENT,
        "stale_upstream": FAILURE_CLASS_ENVIRONMENT,
    }
    return mapping.get(key, FAILURE_CLASS_UNSUCCESSFUL)


def _entry_id(
    receipt_id: str,
    capability: str,
    task_class: str,
    success: bool,
    comparison_key: str = "",
) -> str:
    raw = (
        f"{receipt_id}|{capability}|{task_class}|{comparison_key}|"
        f"{int(bool(success))}"
    )
    return "out_" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:20]


def _threshold_from_env(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or not str(raw).strip():
        return default
    try:
        return max(1, int(raw))
    except ValueError:
        return default


def build_strategy_context(
    capability: Optional[str],
    *,
    step: Optional[Mapping[str, Any]] = None,
    explicit: Optional[Mapping[str, Any]] = None,
    conversation: Optional[Mapping[str, Any]] = None,
    completion_condition_met: Optional[bool] = None,
) -> Dict[str, Any]:
    """Build comparable-strategy context from host-known fields only."""
    cap = str(capability or "")
    exp = explicit if isinstance(explicit, Mapping) else {}
    step = step if isinstance(step, Mapping) else {}
    conv = conversation if isinstance(conversation, Mapping) else {}

    required_output = exp.get("required_output_type")
    if not isinstance(required_output, str) or not required_output.strip():
        outs = CAPABILITY_OUTPUT_TYPES.get(cap)
        required_output = sorted(outs)[0] if outs else None
    else:
        required_output = required_output.strip()[:40]

    input_structure = exp.get("input_structure")
    if not isinstance(input_structure, str) or not input_structure.strip():
        args = step.get("arguments") if isinstance(step.get("arguments"), dict) else {}
        # Infer from bound arguments when present.
        if isinstance(args.get("schema"), dict) and (
            args.get("schema", {}).get("record_key_field")
            or "extract_records" in cap
        ):
            input_structure = "markdown_table"
        elif "extract_fields" in cap:
            input_structure = "labeled_text"
        else:
            input_structure = CAPABILITY_DEFAULT_INPUT.get(cap)
    else:
        input_structure = input_structure.strip()[:40]

    verification_mode = exp.get("verification_mode")
    if not isinstance(verification_mode, str) or not verification_mode.strip():
        verification_mode = CAPABILITY_VERIFICATION.get(cap)
    else:
        verification_mode = verification_mode.strip()[:40]

    task_class = exp.get("task_class")
    if not isinstance(task_class, str) or not task_class.strip():
        task_class = _infer_task_class(cap, step)
    else:
        task_class = task_class.strip()[:80]

    completion = exp.get("completion_condition")
    if not isinstance(completion, str) or not completion.strip():
        completion = str(conv.get("completion_condition") or "").strip()[:200] or None
    else:
        completion = completion.strip()[:200]

    ctx = {
        "task_class": task_class,
        "required_output_type": required_output,
        "input_structure": input_structure,
        "verification_mode": verification_mode,
        "completion_condition": completion,
        "completion_condition_met": completion_condition_met,
        "capability_applicability": sorted(CAPABILITY_OUTPUT_TYPES.get(cap) or []),
    }
    ctx["comparison_key"] = comparison_key_for(ctx)
    ctx["context_complete"] = bool(
        ctx["required_output_type"]
        and ctx["input_structure"]
        and ctx["verification_mode"]
        and ctx["task_class"]
    )
    return ctx


def comparison_key_for(ctx: Mapping[str, Any]) -> str:
    parts = [
        str(ctx.get("task_class") or ""),
        str(ctx.get("required_output_type") or ""),
        str(ctx.get("input_structure") or ""),
        str(ctx.get("verification_mode") or ""),
    ]
    raw = "|".join(parts)
    return "ck_" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def capability_satisfies_output(capability: str, required_output_type: Optional[str]) -> bool:
    if not required_output_type:
        return False
    outs = CAPABILITY_OUTPUT_TYPES.get(str(capability or ""))
    if not outs:
        return False
    return required_output_type in outs


def contexts_comparable(a: Mapping[str, Any], b: Mapping[str, Any]) -> bool:
    """True only when both contexts describe the same required outcome family."""
    if not a or not b:
        return False
    if not a.get("context_complete") or not b.get("context_complete"):
        return False
    return (
        a.get("required_output_type") == b.get("required_output_type")
        and a.get("input_structure") == b.get("input_structure")
        and a.get("verification_mode") == b.get("verification_mode")
        and a.get("task_class") == b.get("task_class")
    )


class OutcomeFeedbackStore:
    """Bounded durable outcome store keyed by host execution receipt ids."""

    def __init__(
        self,
        root: Path | str,
        *,
        min_attempts: Optional[int] = None,
        min_task_instances: Optional[int] = None,
        max_observations_per_instance: Optional[int] = None,
    ) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.path = self.root / "store.json"
        self.min_attempts = max(
            1,
            int(
                min_attempts
                if min_attempts is not None
                else _threshold_from_env("ELYSIA_OUTCOME_MIN_ATTEMPTS", DEFAULT_MIN_ATTEMPTS)
            ),
        )
        self.min_task_instances = max(
            1,
            int(
                min_task_instances
                if min_task_instances is not None
                else _threshold_from_env(
                    "ELYSIA_OUTCOME_MIN_TASK_INSTANCES", DEFAULT_MIN_TASK_INSTANCES
                )
            ),
        )
        self.max_observations_per_instance = max(
            1,
            int(
                max_observations_per_instance
                if max_observations_per_instance is not None
                else DEFAULT_MAX_OBSERVATIONS_PER_INSTANCE
            ),
        )
        self._lock = threading.Lock()
        if not self.path.exists():
            self._write_store(self._empty_store())

    def _empty_store(self) -> Dict[str, Any]:
        return {
            "schema": SCHEMA,
            "created_utc": _utc_now(),
            "updated_utc": _utc_now(),
            "min_attempts_for_reliability": self.min_attempts,
            "min_task_instances_for_reliability": self.min_task_instances,
            "entries": [],
            "authorization_note": (
                "Outcome feedback never grants tool authorization or activates capabilities."
            ),
        }

    def _load(self) -> Dict[str, Any]:
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            # Corrupt primary: try backup, else re-init empty without claiming history.
            backup = self.path.with_suffix(self.path.suffix + ".bak")
            if backup.is_file():
                try:
                    raw = json.loads(backup.read_text(encoding="utf-8"))
                    if isinstance(raw, dict) and raw.get("schema") == SCHEMA:
                        _atomic_write_json(self.path, raw)
                        return raw
                except (OSError, json.JSONDecodeError, OutcomeFeedbackError):
                    pass
            empty = self._empty_store()
            empty["recovery_note"] = f"reinitialized after corrupt store: {exc}"[:200]
            try:
                _atomic_write_json(self.path, empty)
            except Exception:
                pass
            return empty
        if not isinstance(raw, dict) or raw.get("schema") != SCHEMA:
            empty = self._empty_store()
            empty["recovery_note"] = "reinitialized after schema mismatch"
            try:
                _atomic_write_json(self.path, empty)
            except Exception:
                pass
            return empty
        entries = raw.get("entries")
        if not isinstance(entries, list):
            raw["entries"] = []
        return raw

    def _write_store(self, store: Mapping[str, Any]) -> None:
        payload = dict(store)
        payload["schema"] = SCHEMA
        payload["updated_utc"] = _utc_now()
        _atomic_write_json(self.path, payload)

    def export_store(self) -> Dict[str, Any]:
        with self._lock:
            store = self._load()
            return {
                "schema": store.get("schema"),
                "updated_utc": store.get("updated_utc"),
                "entry_count": len(store.get("entries") or []),
                "min_attempts_for_reliability": self.min_attempts,
                "min_task_instances_for_reliability": self.min_task_instances,
                "authorization_note": store.get("authorization_note"),
                "entries": list(store.get("entries") or [])[:MAX_ENTRIES],
                "authorization_granted": False,
            }

    def ingest_receipt(
        self,
        receipt: Mapping[str, Any],
        *,
        step: Optional[Mapping[str, Any]] = None,
        evaluation: Optional[Mapping[str, Any]] = None,
        conversation_id: Optional[str] = None,
        duration_ms: Optional[int] = None,
        task_class: Optional[str] = None,
        strategy_context: Optional[Mapping[str, Any]] = None,
        conversation: Optional[Mapping[str, Any]] = None,
        require_host_path: bool = False,
    ) -> Dict[str, Any]:
        """Ingest a host execution receipt. Rejects fabricated / model-only claims."""
        if not isinstance(receipt, Mapping):
            raise OutcomeFeedbackError("receipt must be an object")
        # Absolute rejection of authority claims in untrusted payloads.
        for banned in (
            "authorization_granted",
            "authorization_inherited",
            "token",
            "password",
            "credential",
            "api_key",
        ):
            if banned in receipt and receipt.get(banned) not in (None, False, "none"):
                raise OutcomeFeedbackError(
                    f"receipt must not carry authority or secret field: {banned}"
                )

        receipt_id = receipt.get("execution_id") or receipt.get("receipt_id")
        if not isinstance(receipt_id, str) or not _EXEC_ID_RE.fullmatch(receipt_id):
            raise OutcomeFeedbackError("host receipt requires valid execution_id")

        # External/API ingest must prove the receipt came from a host execution path.
        if require_host_path and receipt.get("host_execution_path") is not True:
            raise OutcomeFeedbackError(
                "external ingest requires host_execution_path provenance"
            )

        capability = receipt.get("capability")
        if not isinstance(capability, str) and isinstance(step, Mapping):
            capability = step.get("capability")
        if not isinstance(capability, str) or not _CAP_RE.fullmatch(capability):
            raise OutcomeFeedbackError("capability identifier required")

        # Only host-verified success or host-recorded failure may be stored.
        verified = receipt.get("verified") is True
        outcome = receipt.get("outcome") if isinstance(receipt.get("outcome"), dict) else {}
        success_flag = outcome.get("success")
        if success_flag is None:
            success_flag = verified
        # Model cannot assert success without verified=True on the receipt.
        if success_flag is True and verified is not True:
            raise OutcomeFeedbackError(
                "success claims require host verified=True on the receipt"
            )
        if outcome.get("provenance") == "model_claim":
            raise OutcomeFeedbackError("model-generated outcome claims are rejected")
        # Successful task learning requires completion evaluation when a condition exists.
        completion_met = None
        if isinstance(evaluation, Mapping) and "met" in evaluation:
            completion_met = bool(evaluation.get("met"))
        if success_flag is True and completion_met is False:
            raise OutcomeFeedbackError(
                "verified tool success with unmet completion condition cannot count as strategy success"
            )

        failure_category = None
        if isinstance(step, Mapping):
            failure_category = step.get("last_failure_category")
        if failure_category is None and isinstance(evaluation, Mapping):
            failure_category = evaluation.get("category")
        if failure_category is None:
            failure_category = outcome.get("failure_category")
        if not success_flag and not failure_category:
            failure_category = "unsuccessful_execution"

        # Environmental / auth failures should not poison strategy quality scores.
        failure_class = normalize_failure_class(
            str(failure_category) if failure_category else None
        )
        counts_toward_reliability = True
        if failure_class in {
            FAILURE_CLASS_UNAUTHORIZED,
            FAILURE_CLASS_UNAVAILABLE,
            FAILURE_CLASS_ENVIRONMENT,
        }:
            counts_toward_reliability = False

        explicit_ctx = dict(strategy_context) if isinstance(strategy_context, Mapping) else {}
        if task_class and "task_class" not in explicit_ctx:
            explicit_ctx["task_class"] = task_class
        ctx = build_strategy_context(
            capability,
            step=step,
            explicit=explicit_ctx,
            conversation=conversation,
            completion_condition_met=completion_met,
        )
        tc = str(ctx.get("task_class") or "unspecified")[:80]
        ck = str(ctx.get("comparison_key") or "")

        task_instance = None
        if isinstance(conversation_id, str) and conversation_id.strip():
            task_instance = conversation_id.strip()[:40]
        elif isinstance(receipt.get("conversation_id"), str):
            task_instance = str(receipt.get("conversation_id"))[:40]

        dur = duration_ms
        if dur is None and isinstance(receipt.get("duration_ms"), int):
            dur = receipt.get("duration_ms")
        if dur is not None:
            if not isinstance(dur, int) or dur < 0 or dur > 3_600_000:
                raise OutcomeFeedbackError("duration_ms out of bounds")

        # Strategy success for ranking: host verified AND completion not explicitly unmet.
        strategy_success = bool(success_flag and verified and completion_met is not False)

        entry = {
            "entry_id": _entry_id(
                receipt_id, capability, tc, strategy_success, comparison_key=ck
            ),
            "receipt_id": receipt_id,
            "capability": capability,
            "task_class": tc,
            "comparison_key": ck,
            "strategy_context": {
                "required_output_type": ctx.get("required_output_type"),
                "input_structure": ctx.get("input_structure"),
                "verification_mode": ctx.get("verification_mode"),
                "completion_condition": ctx.get("completion_condition"),
                "completion_condition_met": completion_met,
                "context_complete": ctx.get("context_complete"),
            },
            "task_instance_id": task_instance,
            "success": strategy_success,
            "verification_status": "verified" if verified else "failed",
            "failure_category": str(failure_category)[:80] if failure_category else None,
            "failure_class": failure_class,
            "counts_toward_reliability": counts_toward_reliability,
            "duration_ms": dur,
            "recovery": (
                str(outcome.get("recovery"))[:80]
                if isinstance(outcome.get("recovery"), str)
                else None
            ),
            "provenance": "host_verified_receipt",
            "host_execution_path": True,
            "created_utc": _utc_now(),
        }

        with self._lock:
            store = self._load()
            entries = [
                e for e in (store.get("entries") or []) if isinstance(e, dict)
            ]
            # Idempotent: same receipt_id + capability + task_class + success.
            for existing in entries:
                if existing.get("entry_id") == entry["entry_id"]:
                    return {
                        "ingested": False,
                        "idempotent": True,
                        "entry": existing,
                        "authorization_granted": False,
                    }
                # Conflicting record for same receipt_id with different success.
                if (
                    existing.get("receipt_id") == receipt_id
                    and existing.get("capability") == capability
                    and existing.get("success") != entry["success"]
                ):
                    raise OutcomeFeedbackError(
                        "conflicting outcome for the same receipt_id"
                    )
            entries.append(entry)
            if len(entries) > MAX_ENTRIES:
                entries = entries[-MAX_ENTRIES:]
            store["entries"] = entries
            self._write_store(store)
            return {
                "ingested": True,
                "idempotent": False,
                "entry": entry,
                "authorization_granted": False,
            }

    def _independent_observations(
        self, entries: Sequence[Mapping[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Cap correlated retries per task instance; keep most recent observations."""
        by_instance: Dict[str, List[Dict[str, Any]]] = {}
        for e in entries:
            if not isinstance(e, dict):
                continue
            inst = e.get("task_instance_id") or f"anon:{e.get('receipt_id')}"
            by_instance.setdefault(str(inst), []).append(dict(e))
        independent: List[Dict[str, Any]] = []
        for group in by_instance.values():
            group.sort(key=lambda x: str(x.get("created_utc") or ""))
            independent.extend(group[-self.max_observations_per_instance :])
        return independent

    def stats_for(
        self,
        capability: str,
        *,
        task_class: Optional[str] = None,
        comparison_key: Optional[str] = None,
        strategy_context: Optional[Mapping[str, Any]] = None,
    ) -> Dict[str, Any]:
        ctx = strategy_context if isinstance(strategy_context, Mapping) else None
        ck = comparison_key
        if not ck and ctx:
            ck = ctx.get("comparison_key") or comparison_key_for(ctx)
        with self._lock:
            store = self._load()
            entries = [
                e
                for e in (store.get("entries") or [])
                if isinstance(e, dict)
                and e.get("capability") == capability
                and e.get("provenance") == "host_verified_receipt"
            ]
        if ck:
            entries = [e for e in entries if e.get("comparison_key") == ck]
        elif task_class:
            # Without a comparison key, task-class alone is insufficient for measured
            # cross-capability ranking; still allow scoped diagnostics.
            entries = [e for e in entries if e.get("task_class") == task_class]
        quality = [
            e
            for e in entries
            if e.get("counts_toward_reliability") is not False
        ]
        quality = self._independent_observations(quality)
        successes = [e for e in quality if e.get("success") is True]
        failures = [e for e in quality if e.get("success") is not True]
        instances = {
            e.get("task_instance_id")
            for e in quality
            if isinstance(e.get("task_instance_id"), str) and e.get("task_instance_id")
        }
        durations = [
            int(e["duration_ms"])
            for e in quality
            if isinstance(e.get("duration_ms"), int)
        ]
        sample_size = len(quality)
        context_ok = bool(ck) and (
            not ctx or ctx.get("context_complete") is not False
        )
        evidence_sufficient = bool(
            context_ok
            and sample_size >= self.min_attempts
            and len(instances) >= self.min_task_instances
        )
        return {
            "capability": capability,
            "task_class": (ctx or {}).get("task_class") or task_class or "any",
            "comparison_key": ck,
            "sample_size": sample_size,
            "raw_entry_count": len(entries),
            "verified_success_count": len(successes),
            "failure_count": len(failures),
            "task_instance_count": len(instances),
            "evidence_sufficient": evidence_sufficient,
            "reliability": ("measured" if evidence_sufficient else "unknown"),
            "observed_success_rate_numerator": (
                len(successes) if evidence_sufficient else None
            ),
            "observed_success_rate_denominator": (
                sample_size if evidence_sufficient else None
            ),
            "mean_duration_ms": (
                int(sum(durations) / len(durations)) if durations else None
            ),
            "failure_class_counts": _count_failure_classes(failures),
            "min_attempts_required": self.min_attempts,
            "min_task_instances_required": self.min_task_instances,
            "max_observations_per_instance": self.max_observations_per_instance,
            "authorization_granted": False,
        }

    def rank_capabilities(
        self,
        candidates: Sequence[Any],
        *,
        available_capabilities: Optional[Sequence[Any]] = None,
        task_class: Optional[str] = None,
        permitted: Optional[Sequence[str]] = None,
        strategy_context: Optional[Mapping[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """Rank only comparable alternatives for a required outcome family."""
        from project_guardian.capability_composition import (
            capability_selection_metadata,
            list_composable_capabilities,
        )

        def _names(seq: Optional[Sequence[Any]]) -> set:
            names: set = set()
            if not seq:
                return names
            for item in seq:
                if isinstance(item, str):
                    names.add(item)
                elif isinstance(item, Mapping) and isinstance(item.get("capability"), str):
                    names.add(item["capability"])
            return names

        available = _names(available_capabilities) or {
            c["capability"] for c in list_composable_capabilities()
        }
        allowed = _names(permitted) if permitted is not None else None

        req_ctx = None
        if isinstance(strategy_context, Mapping) and strategy_context:
            req_ctx = {
                "task_class": strategy_context.get("task_class") or task_class,
                "required_output_type": strategy_context.get("required_output_type"),
                "input_structure": strategy_context.get("input_structure"),
                "verification_mode": strategy_context.get("verification_mode"),
                "completion_condition": strategy_context.get("completion_condition"),
            }
            req_ctx["comparison_key"] = comparison_key_for(req_ctx)
            req_ctx["context_complete"] = bool(
                req_ctx.get("required_output_type")
                and req_ctx.get("input_structure")
                and req_ctx.get("verification_mode")
                and req_ctx.get("task_class")
            )

        context_complete = bool(req_ctx and req_ctx.get("context_complete"))
        required_output = (req_ctx or {}).get("required_output_type")

        ranked: List[Dict[str, Any]] = []
        skipped_noncomparable: List[str] = []
        for raw in candidates:
            if isinstance(raw, str):
                cap = raw
                extra: Dict[str, Any] = {}
            elif isinstance(raw, Mapping):
                cap = raw.get("capability")
                extra = dict(raw)
            else:
                continue
            if not isinstance(cap, str):
                continue
            if allowed is not None and cap not in allowed:
                continue
            if cap not in available:
                continue
            meta = capability_selection_metadata(cap)
            if not meta.get("available"):
                continue

            # When a required outcome is specified, exclude non-applicable capabilities
            # from historical competition entirely.
            if required_output and not capability_satisfies_output(cap, required_output):
                skipped_noncomparable.append(cap)
                continue

            cap_ctx = build_strategy_context(
                cap,
                explicit={
                    **(req_ctx or {}),
                    "task_class": (req_ctx or {}).get("task_class") or task_class,
                    "required_output_type": required_output
                    or (req_ctx or {}).get("required_output_type"),
                },
            )
            comparable = True
            if context_complete:
                comparable = contexts_comparable(req_ctx or {}, cap_ctx)
            else:
                # Incomplete request context → suitability only.
                comparable = False

            stats = self.stats_for(
                cap,
                task_class=(req_ctx or {}).get("task_class") or task_class,
                comparison_key=cap_ctx.get("comparison_key") if comparable else None,
                strategy_context=cap_ctx if comparable else None,
            )
            # If contexts aren't comparable, force unknown reliability.
            if not comparable:
                stats = dict(stats)
                stats["evidence_sufficient"] = False
                stats["reliability"] = "unknown"
                stats["observed_success_rate_numerator"] = None
                stats["observed_success_rate_denominator"] = None

            suitability = 0
            if meta.get("prefers_deterministic"):
                suitability += 5
            if meta.get("verification_potential") == "high":
                suitability += 3
            elif meta.get("verification_potential") == "medium":
                suitability += 1

            history_bonus = 0
            rationale_parts = [
                "available and permitted",
                f"suitability_score={suitability}",
            ]
            if not context_complete:
                rationale_parts.append(
                    "strategy context incomplete; reliability unknown"
                )
            elif not comparable:
                rationale_parts.append(
                    "not comparable to requested outcome family; history ignored"
                )
            elif stats["evidence_sufficient"]:
                num = int(stats["observed_success_rate_numerator"] or 0)
                den = int(stats["observed_success_rate_denominator"] or 1)
                history_bonus = (num * 100) // den
                rationale_parts.append(
                    f"measured comparable history {num}/{den} across "
                    f"{stats['task_instance_count']} task instances "
                    f"(key={stats.get('comparison_key')})"
                )
            else:
                rationale_parts.append(
                    "reliability unknown "
                    f"(need {stats['min_attempts_required']} independent attempts across "
                    f"{stats['min_task_instances_required']} task instances; "
                    f"have {stats['sample_size']}/{stats['task_instance_count']})"
                )
                if meta.get("prefers_deterministic"):
                    rationale_parts.append("prefer deterministic until measured")

            latency_note = "unknown"
            if stats.get("mean_duration_ms") is not None:
                latency_note = f"mean_duration_ms={stats['mean_duration_ms']}"
                if stats["evidence_sufficient"] and comparable:
                    history_bonus += max(
                        0, 20 - min(20, int(stats["mean_duration_ms"]) // 500)
                    )

            total = suitability * 10 + (
                history_bonus if stats["evidence_sufficient"] and comparable else 0
            )
            ranked.append(
                {
                    "capability": cap,
                    "expected_outcome": str(extra.get("expected_outcome") or "")[:400],
                    "notes": str(extra.get("notes") or "")[:200],
                    "depends_on": [
                        d
                        for d in (extra.get("depends_on") or [])
                        if isinstance(d, int) and d >= 0
                    ][:8],
                    "selection": meta,
                    "stats": stats,
                    "strategy_context": {
                        "required_output_type": cap_ctx.get("required_output_type"),
                        "input_structure": cap_ctx.get("input_structure"),
                        "verification_mode": cap_ctx.get("verification_mode"),
                        "task_class": cap_ctx.get("task_class"),
                        "comparison_key": cap_ctx.get("comparison_key"),
                        "context_complete": cap_ctx.get("context_complete"),
                        "comparable_to_request": comparable and context_complete,
                    },
                    "usefulness_score": total,
                    "suitability_score": suitability,
                    "history_bonus": (
                        history_bonus if stats["evidence_sufficient"] and comparable else 0
                    ),
                    "reliability": stats["reliability"],
                    "evidence_sufficient": bool(
                        stats["evidence_sufficient"] and comparable
                    ),
                    "recommendation_basis": (
                        "measured_history"
                        if stats["evidence_sufficient"] and comparable
                        else "current_suitability"
                    ),
                    "rationale": "; ".join(rationale_parts),
                    "latency_note": latency_note,
                    "skipped_noncomparable_capabilities": skipped_noncomparable[:12],
                    "authorization_granted": False,
                }
            )
        ranked.sort(
            key=lambda c: (
                -int(c["usefulness_score"]),
                -int(c["suitability_score"]),
                c["capability"],
            )
        )
        return ranked


def _count_failure_classes(failures: Sequence[Mapping[str, Any]]) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for e in failures:
        key = str(e.get("failure_class") or "unsuccessful_execution")
        counts[key] = counts.get(key, 0) + 1
    return counts


def _infer_task_class(capability: Optional[str], step: Mapping[str, Any]) -> str:
    cap = str(capability or "")
    desc = str(step.get("description") or "").lower()
    if "extract_records" in cap or "table" in desc or "inventory" in desc:
        return "structured_table_extraction"
    if "extract_fields" in cap:
        return "structured_field_extraction"
    if "documents.search" in cap:
        return "authorized_document_retrieval"
    if "aggregate" in cap or "calculator" in cap:
        return "deterministic_calculation"
    if "synthesize" in cap or "draft" in cap:
        return "grounded_synthesis"
    return "general_composition"


def ingest_host_step_outcome(
    store: OutcomeFeedbackStore,
    *,
    receipt: Mapping[str, Any],
    step: Optional[Mapping[str, Any]] = None,
    conversation_id: Optional[str] = None,
    duration_ms: Optional[int] = None,
    evaluation: Optional[Mapping[str, Any]] = None,
    strategy_context: Optional[Mapping[str, Any]] = None,
    conversation: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """Convenience wrapper used by ConversationStore; never raises into callers."""
    try:
        # Mark as originating from the trusted execute path.
        enriched = dict(receipt)
        enriched["host_execution_path"] = True
        return store.ingest_receipt(
            enriched,
            step=step,
            conversation_id=conversation_id,
            duration_ms=duration_ms,
            evaluation=evaluation,
            strategy_context=strategy_context,
            conversation=conversation,
            require_host_path=False,
        )
    except OutcomeFeedbackError as exc:
        return {
            "ingested": False,
            "error": str(exc)[:200],
            "authorization_granted": False,
        }
