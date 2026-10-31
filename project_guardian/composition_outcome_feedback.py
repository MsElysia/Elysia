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
MAX_ENTRIES = 2000
_EXEC_ID_RE = re.compile(r"^exec_[a-f0-9]{16}$")
_CAP_RE = re.compile(r"^[a-z][a-z0-9_.-]{1,79}$")

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


def _entry_id(receipt_id: str, capability: str, task_class: str, success: bool) -> str:
    raw = f"{receipt_id}|{capability}|{task_class}|{int(bool(success))}"
    return "out_" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:20]


class OutcomeFeedbackStore:
    """Bounded durable outcome store keyed by host execution receipt ids."""

    def __init__(
        self,
        root: Path | str,
        *,
        min_attempts: int = DEFAULT_MIN_ATTEMPTS,
        min_task_instances: int = DEFAULT_MIN_TASK_INSTANCES,
    ) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.path = self.root / "store.json"
        self.min_attempts = max(1, int(min_attempts))
        self.min_task_instances = max(1, int(min_task_instances))
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

        tc = task_class
        if not tc and isinstance(outcome.get("task_class"), str):
            tc = outcome.get("task_class")
        if not tc and isinstance(step, Mapping) and isinstance(step.get("capability"), str):
            tc = _infer_task_class(step.get("capability"), step)
        tc = str(tc or "unspecified")[:80]

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

        entry = {
            "entry_id": _entry_id(receipt_id, capability, tc, bool(success_flag)),
            "receipt_id": receipt_id,
            "capability": capability,
            "task_class": tc,
            "task_instance_id": task_instance,
            "success": bool(success_flag and verified),
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

    def stats_for(
        self,
        capability: str,
        *,
        task_class: Optional[str] = None,
    ) -> Dict[str, Any]:
        with self._lock:
            store = self._load()
            entries = [
                e
                for e in (store.get("entries") or [])
                if isinstance(e, dict)
                and e.get("capability") == capability
                and e.get("provenance") == "host_verified_receipt"
            ]
        if task_class:
            # Strict task-class scope: do not let one class's history dominate another.
            entries = [e for e in entries if e.get("task_class") == task_class]
        quality = [e for e in entries if e.get("counts_toward_reliability") is not False]
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
        evidence_sufficient = (
            sample_size >= self.min_attempts
            and len(instances) >= self.min_task_instances
        )
        return {
            "capability": capability,
            "task_class": task_class or "any",
            "sample_size": sample_size,
            "verified_success_count": len(successes),
            "failure_count": len(failures),
            "task_instance_count": len(instances),
            "evidence_sufficient": evidence_sufficient,
            "reliability": (
                "measured" if evidence_sufficient else "unknown"
            ),
            "observed_success_rate_numerator": len(successes) if evidence_sufficient else None,
            "observed_success_rate_denominator": sample_size if evidence_sufficient else None,
            "mean_duration_ms": (
                int(sum(durations) / len(durations)) if durations else None
            ),
            "failure_class_counts": _count_failure_classes(failures),
            "min_attempts_required": self.min_attempts,
            "min_task_instances_required": self.min_task_instances,
            "authorization_granted": False,
        }

    def rank_capabilities(
        self,
        candidates: Sequence[Any],
        *,
        available_capabilities: Optional[Sequence[Any]] = None,
        task_class: Optional[str] = None,
        permitted: Optional[Sequence[str]] = None,
    ) -> List[Dict[str, Any]]:
        """Deterministic ranking: absolute filters first, then measured evidence."""
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

        ranked: List[Dict[str, Any]] = []
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
            # Absolute filters — never outweighed by history.
            if allowed is not None and cap not in allowed:
                continue
            if cap not in available:
                continue
            meta = capability_selection_metadata(cap)
            if not meta.get("available"):
                continue
            stats = self.stats_for(cap, task_class=task_class)
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
            if stats["evidence_sufficient"]:
                # Prefer higher verified success counts; expose sample size.
                num = int(stats["observed_success_rate_numerator"] or 0)
                den = int(stats["observed_success_rate_denominator"] or 1)
                # Integer ranking only — no invented probabilities.
                history_bonus = (num * 100) // den
                rationale_parts.append(
                    f"measured history {num}/{den} across "
                    f"{stats['task_instance_count']} task instances"
                )
            else:
                rationale_parts.append(
                    "reliability unknown "
                    f"(need {stats['min_attempts_required']} attempts across "
                    f"{stats['min_task_instances_required']} task instances; "
                    f"have {stats['sample_size']}/{stats['task_instance_count']})"
                )
                if meta.get("prefers_deterministic"):
                    rationale_parts.append("prefer deterministic until measured")

            latency_note = "unknown"
            if stats.get("mean_duration_ms") is not None:
                latency_note = f"mean_duration_ms={stats['mean_duration_ms']}"
                # Slight preference for lower observed latency when evidence exists.
                if stats["evidence_sufficient"]:
                    history_bonus += max(0, 20 - min(20, int(stats["mean_duration_ms"]) // 500))

            total = suitability * 10 + history_bonus
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
                    "usefulness_score": total,
                    "suitability_score": suitability,
                    "history_bonus": history_bonus if stats["evidence_sufficient"] else 0,
                    "reliability": stats["reliability"],
                    "evidence_sufficient": stats["evidence_sufficient"],
                    "recommendation_basis": (
                        "measured_history"
                        if stats["evidence_sufficient"]
                        else "current_suitability"
                    ),
                    "rationale": "; ".join(rationale_parts),
                    "latency_note": latency_note,
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
) -> Dict[str, Any]:
    """Convenience wrapper used by ConversationStore; never raises into callers."""
    try:
        return store.ingest_receipt(
            receipt,
            step=step,
            conversation_id=conversation_id,
            duration_ms=duration_ms,
            evaluation=evaluation,
        )
    except OutcomeFeedbackError as exc:
        return {
            "ingested": False,
            "error": str(exc)[:200],
            "authorization_granted": False,
        }
