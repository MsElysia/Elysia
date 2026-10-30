"""Durable conversation + task continuity for the contained Windows pilot.

Conversation records and continuity checkpoints are separate from durable
restricted-fact memory. Checkpoints are untrusted reconstructed context, never
authorization. Temporary tool grants are never persisted.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
import os
import re
import threading
import uuid
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence


SCHEMA_CONVERSATION = "elysia.conversation.v1"
SCHEMA_CHECKPOINT = "elysia.continuity-checkpoint.v1"
DEFAULT_CONTEXT_BUDGET_TOKENS = 1800  # conservative usable budget for small local models
DEFAULT_RESPONSE_RESERVE = 512
DEFAULT_SYSTEM_RESERVE = 400
DEFAULT_ROLLOVER_RATIO = 0.72
CHARS_PER_TOKEN = 4  # documented conservative estimate
MAX_MESSAGES_RETAINED = 200
MAX_CHECKPOINT_BYTES = 12000
MAX_RECENT_RAW_MESSAGES = 8


class ContinuityError(ValueError):
    pass


class StaleTaskEditError(ContinuityError):
    """Competing edit: expected checkpoint revision no longer matches."""


NO_OUTSTANDING_STEPS = "No outstanding steps"


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=True, separators=(",", ":"))


def _new_step_id() -> str:
    return "step_" + uuid.uuid4().hex[:12]


SUPPORTED_STEP_CAPABILITIES = frozenset({"calculator.labor"})


def _normalize_labor_arguments(raw: Any) -> Dict[str, Any]:
    if not isinstance(raw, dict):
        raise ContinuityError("calculator.labor arguments must be an object")
    rate = raw.get("hourly_rate_usd")
    if isinstance(rate, (int, float)) and not isinstance(rate, bool):
        rate_s = format(Decimal(str(rate)).normalize(), "f")
    elif isinstance(rate, str) and re.fullmatch(r"[0-9]{1,4}(?:\.[0-9]{1,2})?", rate.strip()):
        rate_s = rate.strip()
    else:
        raise ContinuityError("hourly_rate_usd must be a USD amount")
    args: Dict[str, Any] = {"hourly_rate_usd": rate_s}
    for key, limit in (("painters", 100), ("days", 366), ("hours_per_day", 24)):
        value = raw.get(key)
        if type(value) is bool:
            raise ContinuityError(f"invalid {key}")
        if type(value) is int:
            num = value
        elif type(value) is float and value.is_integer():
            num = int(value)
        elif isinstance(value, str) and re.fullmatch(r"[1-9][0-9]{0,3}", value.strip()):
            num = int(value.strip())
        else:
            raise ContinuityError(f"invalid {key}")
        if not 1 <= num <= limit:
            raise ContinuityError(f"{key} out of range")
        args[key] = num
    return args


def _normalize_task_steps(raw: Any) -> List[Dict[str, Any]]:
    steps: List[Dict[str, Any]] = []
    if not isinstance(raw, list):
        return steps
    for idx, item in enumerate(raw[:40]):
        if not isinstance(item, dict):
            continue
        step_id = item.get("step_id")
        description = item.get("description")
        if not isinstance(step_id, str) or not re.fullmatch(r"step_[a-f0-9]{12}", step_id):
            continue
        if not isinstance(description, str) or not description.strip():
            continue
        status = item.get("status") if item.get("status") in {"pending", "completed"} else "pending"
        capability = item.get("capability")
        if capability is not None and capability not in SUPPORTED_STEP_CAPABILITIES:
            capability = None
        step = {
            "step_id": step_id,
            "description": description.strip()[:400],
            "status": status,
            "order": idx,
            "completed_utc": item.get("completed_utc") if status == "completed" else None,
            "completion_source": item.get("completion_source") if status == "completed" else None,
            "completed_at_revision": item.get("completed_at_revision")
            if status == "completed"
            else None,
            "capability": capability,
            "arguments": item.get("arguments") if isinstance(item.get("arguments"), dict) else None,
            "expected_result_type": item.get("expected_result_type"),
            "verification_rule": item.get("verification_rule"),
            "execution_status": item.get("execution_status")
            if item.get("execution_status") in {"none", "succeeded", "failed"}
            else "none",
            "verification_status": item.get("verification_status")
            if item.get("verification_status") in {"none", "verified", "failed"}
            else "none",
            "execution_receipt_id": item.get("execution_receipt_id"),
            "last_failure_category": item.get("last_failure_category"),
            "result_reference": item.get("result_reference")
            if isinstance(item.get("result_reference"), dict)
            else None,
            "execution_history": [
                h for h in (item.get("execution_history") or []) if isinstance(h, dict)
            ][:12],
        }
        steps.append(step)
    return steps


def _sync_lists_from_task_steps(record: Dict[str, Any]) -> None:
    steps = _normalize_task_steps(record.get("task_steps"))
    record["task_steps"] = steps
    record["outstanding_steps"] = [
        s["description"] for s in steps if s.get("status") == "pending"
    ]
    completed = [s["description"] for s in steps if s.get("status") == "completed"]
    # Preserve any non-step completed_work notes while preferring structured completions.
    prior = [
        c
        for c in (record.get("completed_work") or [])
        if isinstance(c, str) and c.strip() and c.strip() not in completed
    ]
    record["completed_work"] = (completed + prior)[:20]


def _rebuild_pending_steps(
    existing: Sequence[Mapping[str, Any]],
    pending_descriptions: Sequence[str],
) -> List[Dict[str, Any]]:
    """Keep completed steps; rebuild pending list reusing IDs when descriptions match."""
    completed = [
        dict(s)
        for s in existing
        if isinstance(s, dict) and s.get("status") == "completed"
    ]
    pending_pool = [
        dict(s)
        for s in existing
        if isinstance(s, dict) and s.get("status") == "pending"
    ]
    used_ids: set[str] = set()
    new_pending: List[Dict[str, Any]] = []
    for desc in pending_descriptions:
        match = None
        for candidate in pending_pool:
            if candidate["step_id"] in used_ids:
                continue
            if candidate.get("description") == desc:
                match = candidate
                break
        if match is None:
            match = {
                "step_id": _new_step_id(),
                "description": desc,
                "status": "pending",
                "completed_utc": None,
                "completion_source": None,
                "completed_at_revision": None,
                "capability": None,
                "arguments": None,
                "execution_status": "none",
                "verification_status": "none",
                "execution_history": [],
            }
        else:
            match["description"] = desc
            match["status"] = "pending"
            match["completed_utc"] = None
            match["completion_source"] = None
            match["completed_at_revision"] = None
            # Preserve capability binding and prior execution evidence.
        used_ids.add(match["step_id"])
        new_pending.append(match)
    merged = completed + new_pending
    for idx, step in enumerate(merged):
        step["order"] = idx
    return merged


def estimate_tokens(text: str) -> int:
    """Conservative char/4 estimate when a tokenizer is unavailable."""
    if not text:
        return 0
    return max(1, (len(text) + CHARS_PER_TOKEN - 1) // CHARS_PER_TOKEN)


def configured_context_budget_tokens() -> int:
    raw = os.environ.get("ELYSIA_CONTEXT_BUDGET_TOKENS", "").strip()
    if not raw:
        return DEFAULT_CONTEXT_BUDGET_TOKENS
    try:
        value = int(raw)
    except ValueError:
        return DEFAULT_CONTEXT_BUDGET_TOKENS
    return max(256, min(value, 8192))


def _atomic_write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    data = json.dumps(payload, indent=2, ensure_ascii=True) + "\n"
    tmp.write_text(data, encoding="utf-8")
    # Windows-friendly replace
    os.replace(str(tmp), str(path))
    # Readback verification
    loaded = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict) or loaded.get("schema") != payload.get("schema"):
        raise ContinuityError("checkpoint/conversation readback failed")


def _safe_title(text: str) -> str:
    cleaned = " ".join((text or "").strip().split())
    if not cleaned:
        return "Untitled conversation"
    return cleaned[:80]


@dataclass
class ConversationStore:
    root: Path

    def __post_init__(self) -> None:
        self.root = Path(self.root)
        self.root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        index = self.root / "index.json"
        if not index.exists():
            _atomic_write_json(
                index,
                {"schema": "elysia.conversation-index.v1", "conversations": []},
            )

    def _conv_dir(self, conversation_id: str) -> Path:
        if not re.fullmatch(r"conv_[a-f0-9]{16}", conversation_id or ""):
            raise ContinuityError("invalid conversation id")
        return self.root / conversation_id

    def _conv_path(self, conversation_id: str) -> Path:
        return self._conv_dir(conversation_id) / "conversation.json"

    def _checkpoint_path(self, conversation_id: str) -> Path:
        return self._conv_dir(conversation_id) / "checkpoint.json"

    def list_conversations(self) -> List[Dict[str, Any]]:
        with self._lock:
            index = json.loads((self.root / "index.json").read_text(encoding="utf-8"))
            rows = index.get("conversations") or []
            return [r for r in rows if isinstance(r, dict)]

    def create(
        self,
        *,
        title: str = "",
        objective: str = "",
        completion_condition: str = "",
        constraints: Optional[Sequence[str]] = None,
    ) -> Dict[str, Any]:
        conversation_id = "conv_" + uuid.uuid4().hex[:16]
        now = _utc_now()
        record = {
            "schema": SCHEMA_CONVERSATION,
            "conversation_id": conversation_id,
            "title": _safe_title(title or objective or "Conversation"),
            "objective": (objective or "").strip()[:800],
            "completion_condition": (completion_condition or "").strip()[:400],
            "constraints": [str(c).strip()[:200] for c in (constraints or []) if str(c).strip()][:12],
            "confirmed_facts": [],
            "assumptions": [],
            "memory_refs": [],
            "completed_work": [],
            "outstanding_steps": [],
            "task_steps": [],
            "status": "active",
            "next_safe_action": "",
            "advancement_needs_review": False,
            "unresolved_questions": [],
            "messages": [],
            "checkpoint_revision": 0,
            "created_utc": now,
            "updated_utc": now,
            "last_rollover_utc": None,
            "operator_task_state": {
                "locked": False,
                "outstanding_steps": False,
                "next_safe_action": False,
                "updated_utc": None,
                "source": None,
            },
            "authorization_note": "No tool authorization is stored with this conversation.",
        }
        with self._lock:
            d = self._conv_dir(conversation_id)
            d.mkdir(parents=True, exist_ok=True)
            _atomic_write_json(self._conv_path(conversation_id), record)
            self._upsert_index(record)
        return record

    def get(self, conversation_id: str) -> Dict[str, Any]:
        with self._lock:
            path = self._conv_path(conversation_id)
            if not path.is_file():
                raise ContinuityError("conversation not found")
            data = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(data, dict) or data.get("schema") != SCHEMA_CONVERSATION:
                raise ContinuityError("malformed conversation record")
            if data.get("conversation_id") != conversation_id:
                raise ContinuityError("conversation identity mismatch")
            return data

    def get_checkpoint(self, conversation_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            path = self._checkpoint_path(conversation_id)
            if not path.is_file():
                return None
            data = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(data, dict) or data.get("schema") != SCHEMA_CHECKPOINT:
                raise ContinuityError("malformed checkpoint")
            if data.get("conversation_id") != conversation_id:
                raise ContinuityError("checkpoint identity mismatch")
            return data

    def update_task_fields(self, conversation_id: str, updates: Mapping[str, Any]) -> Dict[str, Any]:
        """Host-side field merge. Operator-locked next/outstanding cannot be overwritten here."""
        with self._lock:
            record = self._load_unlocked(conversation_id)
            ops = record.get("operator_task_state") if isinstance(record.get("operator_task_state"), dict) else {}
            for key in (
                "objective",
                "completion_condition",
                "next_safe_action",
                "status",
                "title",
            ):
                if key in updates and isinstance(updates[key], str):
                    if key == "next_safe_action" and ops.get("next_safe_action"):
                        # Explicit operator correction wins over model/host summaries.
                        continue
                    record[key] = updates[key].strip()[:800]
            for key in (
                "constraints",
                "confirmed_facts",
                "assumptions",
                "completed_work",
                "outstanding_steps",
                "unresolved_questions",
                "memory_refs",
            ):
                if key in updates and isinstance(updates[key], list):
                    if key == "outstanding_steps" and ops.get("outstanding_steps"):
                        continue
                    cleaned = []
                    for item in updates[key][:20]:
                        if isinstance(item, str) and item.strip():
                            cleaned.append(item.strip()[:400])
                        elif isinstance(item, dict):
                            # memory_refs may be {fact_id, revision} without statement text required
                            ref = {}
                            if isinstance(item.get("fact_id"), str):
                                ref["fact_id"] = item["fact_id"][:64]
                            if "revision" in item:
                                try:
                                    ref["revision"] = int(item["revision"])
                                except (TypeError, ValueError):
                                    pass
                            if ref:
                                cleaned.append(ref)
                    record[key] = cleaned
            # Structured task_steps are operator-controlled; never accept model/host merges.
            updates_dict = dict(updates)
            updates_dict.pop("task_steps", None)
            record["updated_utc"] = _utc_now()
            _atomic_write_json(self._conv_path(conversation_id), record)
            self._upsert_index(record)
            return record

    def commit_operator_task_state(
        self,
        conversation_id: str,
        *,
        expected_revision: int,
        outstanding_steps: Optional[Sequence[str]] = None,
        next_safe_action: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Authoritative operator edit of outstanding steps / next action.

        Requires expected_revision to match the current checkpoint revision (0 if none).
        Commits conversation fields then writes a new durable checkpoint with readback.
        Idempotent when the same operator state is already committed at that revision+1.
        """
        if not isinstance(expected_revision, int) or expected_revision < 0:
            raise ContinuityError("expected_revision must be a non-negative integer")
        if outstanding_steps is None and next_safe_action is None:
            raise ContinuityError("nothing to save")

        cleaned_steps: Optional[List[str]] = None
        if outstanding_steps is not None:
            if not isinstance(outstanding_steps, (list, tuple)):
                raise ContinuityError("outstanding_steps must be a list")
            cleaned_steps = []
            for item in list(outstanding_steps)[:20]:
                if not isinstance(item, str) or not item.strip():
                    raise ContinuityError("outstanding_steps entries must be non-empty strings")
                if len(item.strip()) > 400:
                    raise ContinuityError("outstanding_steps entry too long")
                cleaned_steps.append(item.strip())

        cleaned_next: Optional[str] = None
        if next_safe_action is not None:
            if not isinstance(next_safe_action, str):
                raise ContinuityError("next_safe_action must be a string")
            cleaned_next = next_safe_action.strip()
            if not cleaned_next:
                raise ContinuityError("next_safe_action must be non-empty")
            if len(cleaned_next) > 800:
                raise ContinuityError("next_safe_action too long")

        with self._lock:
            record = self._load_unlocked(conversation_id)
            current_rev = int(record.get("checkpoint_revision") or 0)
            existing = None
            cpath = self._checkpoint_path(conversation_id)
            if cpath.is_file():
                try:
                    existing = json.loads(cpath.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    existing = None

            # Idempotent retry after a successful commit whose response was lost:
            # current is already expected_revision+1 with matching operator content.
            if current_rev == expected_revision + 1 and isinstance(existing, dict):
                if (
                    int(existing.get("revision") or 0) == expected_revision + 1
                    and existing.get("reason") == "operator_task_edit"
                    and existing.get("task_state_source") == "operator"
                ):
                    same_steps = (
                        cleaned_steps is None
                        or list(existing.get("outstanding_steps") or []) == cleaned_steps
                    )
                    same_next = (
                        cleaned_next is None
                        or (existing.get("next_safe_action") or "") == cleaned_next
                    )
                    if same_steps and same_next:
                        return {
                            "conversation": record,
                            "checkpoint": existing,
                            "idempotent": True,
                            "saved": True,
                        }
                raise StaleTaskEditError(
                    f"stale task edit: expected revision {expected_revision}, current is {current_rev}"
                )
            if current_rev != expected_revision:
                raise StaleTaskEditError(
                    f"stale task edit: expected revision {expected_revision}, current is {current_rev}"
                )

            # Mutate in memory only until the checkpoint write succeeds.
            if cleaned_steps is not None:
                existing_steps = _normalize_task_steps(record.get("task_steps"))
                record["task_steps"] = _rebuild_pending_steps(existing_steps, cleaned_steps)
                _sync_lists_from_task_steps(record)
            if cleaned_next is not None:
                record["next_safe_action"] = cleaned_next
                record["advancement_needs_review"] = False
            now = _utc_now()
            prior_ops = (
                record.get("operator_task_state")
                if isinstance(record.get("operator_task_state"), dict)
                else {}
            )
            record["operator_task_state"] = {
                "locked": True,
                "outstanding_steps": True
                if cleaned_steps is not None
                else bool(prior_ops.get("outstanding_steps")),
                "next_safe_action": True
                if cleaned_next is not None
                else bool(prior_ops.get("next_safe_action")),
                "updated_utc": now,
                "source": "operator",
            }
            record["updated_utc"] = now

            return self._persist_operator_mutation_unlocked(
                record,
                previous=existing if isinstance(existing, dict) else None,
                reason="operator_task_edit",
                require_outstanding=cleaned_steps,
            )

    def complete_operator_step(
        self,
        conversation_id: str,
        *,
        step_id: str,
        expected_revision: int,
    ) -> Dict[str, Any]:
        """Mark one pending step completed by stable ID and safely advance next action."""
        if not isinstance(step_id, str) or not re.fullmatch(r"step_[a-f0-9]{12}", step_id):
            raise ContinuityError("invalid step_id")
        if not isinstance(expected_revision, int) or expected_revision < 0:
            raise ContinuityError("expected_revision must be a non-negative integer")

        with self._lock:
            record = self._load_unlocked(conversation_id)
            current_rev = int(record.get("checkpoint_revision") or 0)
            existing = None
            cpath = self._checkpoint_path(conversation_id)
            if cpath.is_file():
                try:
                    existing = json.loads(cpath.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    existing = None

            # Idempotent retry: same step already completed at expected_revision+1.
            if current_rev == expected_revision + 1 and isinstance(existing, dict):
                if (
                    int(existing.get("revision") or 0) == expected_revision + 1
                    and existing.get("reason") == "operator_step_complete"
                ):
                    done = existing.get("last_completed_step") or {}
                    if isinstance(done, dict) and done.get("step_id") == step_id:
                        return {
                            "conversation": record,
                            "checkpoint": existing,
                            "idempotent": True,
                            "saved": True,
                            "advanced": bool(existing.get("advanced_next_action")),
                            "advancement_needs_review": bool(
                                existing.get("advancement_needs_review")
                            ),
                        }
                raise StaleTaskEditError(
                    f"stale task edit: expected revision {expected_revision}, current is {current_rev}"
                )
            if current_rev != expected_revision:
                raise StaleTaskEditError(
                    f"stale task edit: expected revision {expected_revision}, current is {current_rev}"
                )

            steps = _normalize_task_steps(record.get("task_steps"))
            # Bootstrap structured steps from legacy outstanding_steps when needed.
            if not steps and record.get("outstanding_steps"):
                legacy = [
                    str(s).strip()
                    for s in (record.get("outstanding_steps") or [])
                    if isinstance(s, str) and str(s).strip()
                ]
                steps = _rebuild_pending_steps([], legacy)
                record["task_steps"] = steps
                _sync_lists_from_task_steps(record)
                steps = _normalize_task_steps(record.get("task_steps"))

            target = next((s for s in steps if s["step_id"] == step_id), None)
            if target is None:
                raise ContinuityError("step not found")
            if target.get("status") == "completed":
                # Already complete at this revision — no duplicate history.
                raise ContinuityError("step already completed")

            now = _utc_now()
            next_rev = current_rev + 1
            target["status"] = "completed"
            target["completed_utc"] = now
            target["completion_source"] = "operator"
            target["completed_at_revision"] = next_rev
            for idx, step in enumerate(steps):
                if step["step_id"] == step_id:
                    steps[idx] = target
                    break
            record["task_steps"] = steps
            _sync_lists_from_task_steps(record)

            current_next = (record.get("next_safe_action") or "").strip()
            completed_desc = target["description"]
            pending = [s for s in steps if s.get("status") == "pending"]
            linked = (
                not current_next
                or current_next == completed_desc
                or current_next == NO_OUTSTANDING_STEPS
            )
            advanced = False
            needs_review = False
            if linked:
                if pending:
                    record["next_safe_action"] = pending[0]["description"]
                    advanced = True
                    needs_review = False
                else:
                    record["next_safe_action"] = NO_OUTSTANDING_STEPS
                    advanced = True
                    needs_review = False
            else:
                # Preserve unrelated operator next action.
                needs_review = True
                advanced = False
            record["advancement_needs_review"] = needs_review

            prior_ops = (
                record.get("operator_task_state")
                if isinstance(record.get("operator_task_state"), dict)
                else {}
            )
            record["operator_task_state"] = {
                "locked": True,
                "outstanding_steps": True,
                "next_safe_action": True if advanced or prior_ops.get("next_safe_action") else True,
                "updated_utc": now,
                "source": "operator",
            }
            record["updated_utc"] = now

            result = self._persist_operator_mutation_unlocked(
                record,
                previous=existing if isinstance(existing, dict) else None,
                reason="operator_step_complete",
                require_outstanding=None,
                extra_checkpoint_fields={
                    "last_completed_step": {
                        "step_id": step_id,
                        "description": completed_desc,
                        "completion_source": "operator",
                        "completed_utc": now,
                    },
                    "advanced_next_action": advanced,
                    "advancement_needs_review": needs_review,
                },
            )
            result["advanced"] = advanced
            result["advancement_needs_review"] = needs_review
            result["completed_step"] = {
                "step_id": step_id,
                "description": completed_desc,
                "completion_source": "operator",
                "completed_utc": now,
            }
            return result

    def bind_operator_step(
        self,
        conversation_id: str,
        *,
        step_id: str,
        expected_revision: int,
        capability: str,
        arguments: Mapping[str, Any],
    ) -> Dict[str, Any]:
        """Attach a supported capability binding to a pending step."""
        if capability not in SUPPORTED_STEP_CAPABILITIES:
            raise ContinuityError("unsupported step capability")
        if not isinstance(step_id, str) or not re.fullmatch(r"step_[a-f0-9]{12}", step_id):
            raise ContinuityError("invalid step_id")
        if not isinstance(expected_revision, int) or expected_revision < 0:
            raise ContinuityError("expected_revision must be a non-negative integer")
        cleaned_args = _normalize_labor_arguments(arguments)

        with self._lock:
            record, existing, current_rev = self._revision_gate_unlocked(
                conversation_id,
                expected_revision=expected_revision,
                idempotent_reason="operator_step_bind",
                idempotent_match=lambda ckpt: (
                    isinstance(ckpt.get("last_bound_step"), dict)
                    and ckpt["last_bound_step"].get("step_id") == step_id
                    and ckpt["last_bound_step"].get("capability") == capability
                    and ckpt["last_bound_step"].get("arguments") == cleaned_args
                ),
            )
            if record.get("_idempotent_hit"):
                return {
                    "conversation": {k: v for k, v in record.items() if k != "_idempotent_hit"},
                    "checkpoint": existing,
                    "idempotent": True,
                    "saved": True,
                }

            steps = _normalize_task_steps(record.get("task_steps"))
            target = next((s for s in steps if s["step_id"] == step_id), None)
            if target is None:
                raise ContinuityError("step not found")
            if target.get("status") != "pending":
                raise ContinuityError("only pending steps can be bound")
            target["capability"] = capability
            target["arguments"] = cleaned_args
            target["expected_result_type"] = "usd_total"
            target["verification_rule"] = "deterministic_recompute"
            target["execution_status"] = "none"
            target["verification_status"] = "none"
            target["last_failure_category"] = None
            for idx, step in enumerate(steps):
                if step["step_id"] == step_id:
                    steps[idx] = target
                    break
            record["task_steps"] = steps
            _sync_lists_from_task_steps(record)
            now = _utc_now()
            record["operator_task_state"] = {
                "locked": True,
                "outstanding_steps": True,
                "next_safe_action": bool(
                    (record.get("operator_task_state") or {}).get("next_safe_action")
                ),
                "updated_utc": now,
                "source": "operator",
            }
            record["updated_utc"] = now
            return self._persist_operator_mutation_unlocked(
                record,
                previous=existing if isinstance(existing, dict) else None,
                reason="operator_step_bind",
                require_outstanding=None,
                extra_checkpoint_fields={
                    "last_bound_step": {
                        "step_id": step_id,
                        "capability": capability,
                        "arguments": cleaned_args,
                    }
                },
            )

    def execute_verified_bound_step(
        self,
        conversation_id: str,
        *,
        step_id: str,
        expected_revision: int,
        authorize_calculator: bool,
        authorize_record_completion: bool,
        execution_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Execute calculator.labor for a bound step, verify, and durably complete."""
        from project_guardian.local_memory_chat import calculate_local

        if not authorize_calculator:
            raise ContinuityError("calculator execution not authorized for this request")
        if not authorize_record_completion:
            raise ContinuityError("recording completion not authorized for this request")
        if not isinstance(step_id, str) or not re.fullmatch(r"step_[a-f0-9]{12}", step_id):
            raise ContinuityError("invalid step_id")
        if not isinstance(expected_revision, int) or expected_revision < 0:
            raise ContinuityError("expected_revision must be a non-negative integer")
        if execution_id is None:
            execution_id = "exec_" + uuid.uuid4().hex[:16]
        elif not isinstance(execution_id, str) or not re.fullmatch(
            r"exec_[a-f0-9]{16}", execution_id
        ):
            raise ContinuityError("invalid execution_id")

        with self._lock:
            record, existing, current_rev = self._revision_gate_unlocked(
                conversation_id,
                expected_revision=expected_revision,
                idempotent_reason="operator_verified_execution",
                idempotent_match=lambda ckpt: (
                    isinstance(ckpt.get("last_execution_receipt"), dict)
                    and ckpt["last_execution_receipt"].get("execution_id") == execution_id
                ),
            )
            if record.get("_idempotent_hit"):
                clean = {k: v for k, v in record.items() if k != "_idempotent_hit"}
                return {
                    "conversation": clean,
                    "checkpoint": existing,
                    "idempotent": True,
                    "saved": True,
                    "executed": True,
                    "verified": True,
                    "receipt": existing.get("last_execution_receipt") if existing else None,
                    "advanced": bool((existing or {}).get("advanced_next_action")),
                    "advancement_needs_review": bool(
                        (existing or {}).get("advancement_needs_review")
                    ),
                }

            steps = _normalize_task_steps(record.get("task_steps"))
            target = next((s for s in steps if s["step_id"] == step_id), None)
            if target is None:
                raise ContinuityError("step not found")
            if target.get("status") != "pending":
                raise ContinuityError("step is not pending")
            if target.get("capability") != "calculator.labor":
                raise ContinuityError("step is not bound to calculator.labor")
            try:
                args = _normalize_labor_arguments(target.get("arguments") or {})
            except ContinuityError as exc:
                target["execution_status"] = "failed"
                target["verification_status"] = "failed"
                target["last_failure_category"] = "invalid_arguments"
                raise ContinuityError(str(exc)) from exc

            expression = (
                f"{args['hourly_rate_usd']} * {args['painters']} * "
                f"{args['days']} * {args['hours_per_day']}"
            )
            try:
                total = calculate_local(expression)
            except ValueError as exc:
                target["execution_status"] = "failed"
                target["verification_status"] = "failed"
                target["last_failure_category"] = "tool_exception"
                for idx, step in enumerate(steps):
                    if step["step_id"] == step_id:
                        steps[idx] = target
                        break
                record["task_steps"] = steps
                # Do not advance revision on tool failure — leave pending, no success claim.
                raise ContinuityError(f"calculator failed: {exc}") from exc

            # Independent verification: recompute expected product.
            expected = (
                Decimal(args["hourly_rate_usd"])
                * Decimal(args["painters"])
                * Decimal(args["days"])
                * Decimal(args["hours_per_day"])
            )
            expected_s = format(expected.normalize(), "f")
            if total != expected_s:
                target["execution_status"] = "failed"
                target["verification_status"] = "failed"
                target["last_failure_category"] = "incorrect_result"
                raise ContinuityError("calculator result failed independent verification")

            now = _utc_now()
            next_rev = current_rev + 1
            receipt = {
                "execution_id": execution_id,
                "step_id": step_id,
                "capability": "calculator.labor",
                "verified": True,
                "result": total,
                "currency": "USD",
                "expression": expression,
                "checkpoint_revision": next_rev,
                "created_utc": now,
                "verification_rule": "deterministic_recompute",
            }
            history = list(target.get("execution_history") or [])
            history.append(
                {
                    "execution_id": execution_id,
                    "result": total,
                    "verified": True,
                    "created_utc": now,
                    "checkpoint_revision": next_rev,
                }
            )
            target["execution_history"] = history[-12:]
            target["execution_status"] = "succeeded"
            target["verification_status"] = "verified"
            target["execution_receipt_id"] = execution_id
            target["result_reference"] = {
                "execution_id": execution_id,
                "result": total,
                "currency": "USD",
            }
            target["last_failure_category"] = None
            target["status"] = "completed"
            target["completed_utc"] = now
            target["completion_source"] = "operator_verified_execution"
            target["completed_at_revision"] = next_rev
            target["arguments"] = args

            for idx, step in enumerate(steps):
                if step["step_id"] == step_id:
                    steps[idx] = target
                    break
            record["task_steps"] = steps
            _sync_lists_from_task_steps(record)

            current_next = (record.get("next_safe_action") or "").strip()
            completed_desc = target["description"]
            pending = [s for s in steps if s.get("status") == "pending"]
            linked = (
                not current_next
                or current_next == completed_desc
                or current_next == NO_OUTSTANDING_STEPS
            )
            advanced = False
            needs_review = False
            if linked:
                record["next_safe_action"] = (
                    pending[0]["description"] if pending else NO_OUTSTANDING_STEPS
                )
                advanced = True
            else:
                needs_review = True
            record["advancement_needs_review"] = needs_review
            record["operator_task_state"] = {
                "locked": True,
                "outstanding_steps": True,
                "next_safe_action": True,
                "updated_utc": now,
                "source": "operator",
            }
            record["updated_utc"] = now

            # Stash recoverable receipt before checkpoint so a failed write can be reconciled.
            pending_path = self._conv_dir(conversation_id) / f"{execution_id}.pending.json"
            try:
                _atomic_write_json(
                    pending_path,
                    {
                        "schema": "elysia.execution-pending.v1",
                        "receipt": receipt,
                        "step_id": step_id,
                        "expected_revision": expected_revision,
                    },
                )
            except Exception:
                raise ContinuityError(
                    "could not preserve recoverable execution state before checkpoint"
                )

            try:
                result = self._persist_operator_mutation_unlocked(
                    record,
                    previous=existing if isinstance(existing, dict) else None,
                    reason="operator_verified_execution",
                    require_outstanding=None,
                    extra_checkpoint_fields={
                        "last_completed_step": {
                            "step_id": step_id,
                            "description": completed_desc,
                            "completion_source": "operator_verified_execution",
                            "completed_utc": now,
                        },
                        "last_execution_receipt": receipt,
                        "advanced_next_action": advanced,
                        "advancement_needs_review": needs_review,
                    },
                )
            except ContinuityError as exc:
                raise ContinuityError(
                    f"calculation succeeded but completion was not durably recorded: {exc}; "
                    f"recoverable execution_id={execution_id}"
                ) from exc

            try:
                if pending_path.is_file():
                    pending_path.unlink()
            except OSError:
                pass

            result.update(
                {
                    "executed": True,
                    "verified": True,
                    "receipt": receipt,
                    "advanced": advanced,
                    "advancement_needs_review": needs_review,
                    "completed_step": {
                        "step_id": step_id,
                        "description": completed_desc,
                        "completion_source": "operator_verified_execution",
                        "completed_utc": now,
                    },
                }
            )
            return result

    def reopen_operator_step(
        self,
        conversation_id: str,
        *,
        step_id: str,
        expected_revision: int,
    ) -> Dict[str, Any]:
        """Operator reopens a completed step without destroying prior execution evidence."""
        if not isinstance(step_id, str) or not re.fullmatch(r"step_[a-f0-9]{12}", step_id):
            raise ContinuityError("invalid step_id")
        if not isinstance(expected_revision, int) or expected_revision < 0:
            raise ContinuityError("expected_revision must be a non-negative integer")

        with self._lock:
            record, existing, current_rev = self._revision_gate_unlocked(
                conversation_id,
                expected_revision=expected_revision,
                idempotent_reason="operator_step_reopen",
                idempotent_match=lambda ckpt: (
                    isinstance(ckpt.get("last_reopened_step"), dict)
                    and ckpt["last_reopened_step"].get("step_id") == step_id
                ),
            )
            if record.get("_idempotent_hit"):
                return {
                    "conversation": {k: v for k, v in record.items() if k != "_idempotent_hit"},
                    "checkpoint": existing,
                    "idempotent": True,
                    "saved": True,
                }

            steps = _normalize_task_steps(record.get("task_steps"))
            target = next((s for s in steps if s["step_id"] == step_id), None)
            if target is None:
                raise ContinuityError("step not found")
            if target.get("status") != "completed":
                raise ContinuityError("only completed steps can be reopened")

            prior_completion = {
                "step_id": step_id,
                "description": target["description"],
                "completed_utc": target.get("completed_utc"),
                "completion_source": target.get("completion_source"),
                "completed_at_revision": target.get("completed_at_revision"),
                "execution_receipt_id": target.get("execution_receipt_id"),
                "result_reference": target.get("result_reference"),
            }
            # Preserve history; clear active completion flags.
            target["status"] = "pending"
            target["completed_utc"] = None
            target["completion_source"] = None
            target["completed_at_revision"] = None
            # Keep receipt id / history / result_reference as evidence; do not rerun.
            target["execution_status"] = target.get("execution_status") or "none"
            target["verification_status"] = target.get("verification_status") or "none"
            history = list(target.get("execution_history") or [])
            history.append(
                {
                    "event": "reopened",
                    "prior_completion": prior_completion,
                    "created_utc": _utc_now(),
                }
            )
            target["execution_history"] = history[-12:]

            for idx, step in enumerate(steps):
                if step["step_id"] == step_id:
                    steps[idx] = target
                    break
            record["task_steps"] = steps
            _sync_lists_from_task_steps(record)

            current_next = (record.get("next_safe_action") or "").strip()
            pending = [s for s in steps if s.get("status") == "pending"]
            # Safe recalculation only when next was tracking the list head / no-outstanding.
            linked = (
                not current_next
                or current_next == NO_OUTSTANDING_STEPS
                or current_next
                in {
                    s["description"]
                    for s in steps
                    if s.get("status") == "completed"
                }
                or current_next == target["description"]
            )
            needs_review = False
            if linked and pending:
                # Prefer reopened step as next when it is first pending; else first pending.
                record["next_safe_action"] = pending[0]["description"]
                needs_review = False
            elif linked and not pending:
                record["next_safe_action"] = NO_OUTSTANDING_STEPS
            else:
                needs_review = True
            record["advancement_needs_review"] = needs_review
            now = _utc_now()
            record["operator_task_state"] = {
                "locked": True,
                "outstanding_steps": True,
                "next_safe_action": True,
                "updated_utc": now,
                "source": "operator",
            }
            record["updated_utc"] = now
            result = self._persist_operator_mutation_unlocked(
                record,
                previous=existing if isinstance(existing, dict) else None,
                reason="operator_step_reopen",
                require_outstanding=None,
                extra_checkpoint_fields={
                    "last_reopened_step": {
                        "step_id": step_id,
                        "description": target["description"],
                        "prior_completion": prior_completion,
                    },
                    "advancement_needs_review": needs_review,
                },
            )
            result["reopened_step"] = {
                "step_id": step_id,
                "description": target["description"],
                "prior_completion": prior_completion,
            }
            result["advancement_needs_review"] = needs_review
            return result

    def _revision_gate_unlocked(
        self,
        conversation_id: str,
        *,
        expected_revision: int,
        idempotent_reason: str,
        idempotent_match,
    ) -> tuple[Dict[str, Any], Optional[Dict[str, Any]], int]:
        record = self._load_unlocked(conversation_id)
        current_rev = int(record.get("checkpoint_revision") or 0)
        existing = None
        cpath = self._checkpoint_path(conversation_id)
        if cpath.is_file():
            try:
                existing = json.loads(cpath.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                existing = None
        if current_rev == expected_revision + 1 and isinstance(existing, dict):
            if (
                int(existing.get("revision") or 0) == expected_revision + 1
                and existing.get("reason") == idempotent_reason
                and idempotent_match(existing)
            ):
                record["_idempotent_hit"] = True
                return record, existing, current_rev
            raise StaleTaskEditError(
                f"stale task edit: expected revision {expected_revision}, current is {current_rev}"
            )
        if current_rev != expected_revision:
            raise StaleTaskEditError(
                f"stale task edit: expected revision {expected_revision}, current is {current_rev}"
            )
        return record, existing, current_rev

    def _persist_operator_mutation_unlocked(
        self,
        record: Dict[str, Any],
        *,
        previous: Optional[Dict[str, Any]],
        reason: str,
        require_outstanding: Optional[List[str]],
        extra_checkpoint_fields: Optional[Mapping[str, Any]] = None,
    ) -> Dict[str, Any]:
        conversation_id = record["conversation_id"]
        cpath = self._checkpoint_path(conversation_id)
        checkpoint = self._build_checkpoint(record, reason=reason)
        checkpoint["task_state_source"] = "operator"
        checkpoint["operator_authored"] = {
            "outstanding_steps": bool(
                (record.get("operator_task_state") or {}).get("outstanding_steps")
            ),
            "next_safe_action": bool(
                (record.get("operator_task_state") or {}).get("next_safe_action")
            ),
        }
        if extra_checkpoint_fields:
            for key, value in extra_checkpoint_fields.items():
                checkpoint[key] = value
        content_for_hash = {
            k: v
            for k, v in checkpoint.items()
            if k not in {"created_utc", "revision", "reason", "content_sha256"}
        }
        checkpoint["content_sha256"] = hashlib.sha256(
            _canonical(content_for_hash).encode("utf-8")
        ).hexdigest()
        encoded = _canonical(checkpoint).encode("utf-8")
        if len(encoded) > MAX_CHECKPOINT_BYTES:
            raise ContinuityError("checkpoint too large; continuity cannot be preserved reliably")
        try:
            _atomic_write_json(cpath, checkpoint)
        except Exception:
            if previous is not None and cpath.is_file():
                raise ContinuityError(
                    "checkpoint persistence failed; previous checkpoint retained"
                )
            raise ContinuityError("checkpoint persistence failed")
        loaded = json.loads(cpath.read_text(encoding="utf-8"))
        if loaded.get("content_sha256") != checkpoint.get("content_sha256"):
            if previous is not None:
                _atomic_write_json(cpath, previous)
            raise ContinuityError("checkpoint readback mismatch")
        if loaded.get("next_safe_action") != record.get("next_safe_action"):
            if previous is not None:
                _atomic_write_json(cpath, previous)
            raise ContinuityError("operator next action readback failed")
        if require_outstanding is not None and list(
            loaded.get("outstanding_steps") or []
        ) != require_outstanding:
            if previous is not None:
                _atomic_write_json(cpath, previous)
            raise ContinuityError("operator outstanding steps readback failed")
        if list(loaded.get("task_steps") or []) != list(record.get("task_steps") or []):
            if previous is not None:
                _atomic_write_json(cpath, previous)
            raise ContinuityError("task steps readback failed")

        record["checkpoint_revision"] = checkpoint["revision"]
        record["updated_utc"] = _utc_now()
        try:
            _atomic_write_json(self._conv_path(conversation_id), record)
            self._upsert_index(record)
        except Exception:
            raise ContinuityError(
                "checkpoint saved but conversation record write failed; retry with same edit"
            )
        return {
            "conversation": record,
            "checkpoint": checkpoint,
            "idempotent": False,
            "saved": True,
        }

    def append_message(
        self,
        conversation_id: str,
        *,
        role: str,
        content: str,
        kind: str = "chat",
    ) -> Dict[str, Any]:
        if role not in {"user", "assistant", "system"}:
            raise ContinuityError("invalid message role")
        text = (content or "").strip()
        if not text or len(text) > 8000:
            raise ContinuityError("invalid message content")
        with self._lock:
            record = self._load_unlocked(conversation_id)
            messages = list(record.get("messages") or [])
            msg = {
                "message_id": "msg_" + uuid.uuid4().hex[:12],
                "role": role,
                "content": text,
                "kind": kind,
                "ts": _utc_now(),
            }
            messages.append(msg)
            if len(messages) > MAX_MESSAGES_RETAINED:
                # Keep original earlier messages in a side archive file, do not destroy.
                archive = self._conv_dir(conversation_id) / "messages_archive.jsonl"
                overflow = messages[:-MAX_MESSAGES_RETAINED]
                with archive.open("a", encoding="utf-8") as fh:
                    for row in overflow:
                        fh.write(json.dumps(row, ensure_ascii=True) + "\n")
                messages = messages[-MAX_MESSAGES_RETAINED:]
            record["messages"] = messages
            if role == "user" and not record.get("objective"):
                record["objective"] = text[:800]
                if record.get("title") in ("", "Untitled conversation", "Conversation"):
                    record["title"] = _safe_title(text)
            record["updated_utc"] = _utc_now()
            _atomic_write_json(self._conv_path(conversation_id), record)
            self._upsert_index(record)
            return record

    def write_checkpoint(
        self,
        conversation_id: str,
        *,
        reason: str,
        force: bool = False,
    ) -> Dict[str, Any]:
        """Build and atomically persist a continuity checkpoint with readback."""
        with self._lock:
            record = self._load_unlocked(conversation_id)
            previous = None
            cpath = self._checkpoint_path(conversation_id)
            if cpath.is_file():
                try:
                    previous = json.loads(cpath.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    previous = None
            checkpoint = self._build_checkpoint(record, reason=reason)
            encoded = _canonical(checkpoint).encode("utf-8")
            if len(encoded) > MAX_CHECKPOINT_BYTES:
                raise ContinuityError("checkpoint too large; continuity cannot be preserved reliably")
            # Idempotent: identical content keeps prior revision without duplicating progress.
            if (
                not force
                and isinstance(previous, dict)
                and previous.get("content_sha256") == checkpoint.get("content_sha256")
            ):
                return previous
            try:
                _atomic_write_json(cpath, checkpoint)
            except Exception:
                # Failed write must not destroy previous valid checkpoint.
                if previous is not None and cpath.is_file():
                    raise ContinuityError(
                        "checkpoint persistence failed; previous checkpoint retained"
                    )
                raise ContinuityError("checkpoint persistence failed")
            # Verify readback identity
            loaded = json.loads(cpath.read_text(encoding="utf-8"))
            if loaded.get("content_sha256") != checkpoint.get("content_sha256"):
                if previous is not None:
                    _atomic_write_json(cpath, previous)
                raise ContinuityError("checkpoint readback mismatch")
            record["checkpoint_revision"] = checkpoint["revision"]
            record["updated_utc"] = _utc_now()
            if reason == "rollover":
                record["last_rollover_utc"] = record["updated_utc"]
            _atomic_write_json(self._conv_path(conversation_id), record)
            self._upsert_index(record)
            return checkpoint

    def assemble_model_context(
        self,
        conversation_id: str,
        user_message: str,
        *,
        memory_bundle: Optional[Mapping[str, Any]] = None,
        system_text: str = "",
        budget_tokens: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Bounded context for Ollama: checkpoint + recent messages within budget."""
        budget = int(budget_tokens or configured_context_budget_tokens())
        reserve = DEFAULT_RESPONSE_RESERVE + DEFAULT_SYSTEM_RESERVE
        usable = max(64, budget - reserve)
        record = self.get(conversation_id)
        checkpoint = self.get_checkpoint(conversation_id)
        messages = list(record.get("messages") or [])
        # Threshold: create checkpoint before rollover if approaching budget.
        projected = self._project_tokens(
            system_text=system_text,
            user_message=user_message,
            memory_bundle=memory_bundle,
            recent=messages[-MAX_RECENT_RAW_MESSAGES:],
            checkpoint=checkpoint,
        )
        rolled = False
        if projected > int(usable * DEFAULT_ROLLOVER_RATIO) or projected > usable:
            checkpoint = self.write_checkpoint(conversation_id, reason="rollover")
            rolled = True
            record = self.get(conversation_id)
            messages = list(record.get("messages") or [])

        recent: List[Dict[str, str]] = []
        # Prefer newest messages that fit with checkpoint + memory + user.
        base = estimate_tokens(system_text) + estimate_tokens(user_message)
        if memory_bundle is not None:
            base += estimate_tokens(_canonical(memory_bundle))
        if checkpoint is not None:
            base += estimate_tokens(_canonical(self._model_facing_checkpoint(checkpoint)))
        remaining = max(0, usable - base)
        for msg in reversed(messages):
            if msg.get("role") not in {"user", "assistant"}:
                continue
            piece = {"role": str(msg["role"]), "content": str(msg.get("content") or "")[:1500]}
            cost = estimate_tokens(piece["content"]) + 4
            if cost > remaining and recent:
                break
            if cost > remaining and not recent:
                # Keep a truncated last message rather than inventing content.
                piece["content"] = piece["content"][: max(40, remaining * CHARS_PER_TOKEN)]
                recent.append(piece)
                break
            recent.append(piece)
            remaining -= cost
            if len(recent) >= MAX_RECENT_RAW_MESSAGES:
                break
        recent.reverse()
        facing_checkpoint = self._model_facing_checkpoint(checkpoint) if checkpoint else None
        ops = record.get("operator_task_state") if isinstance(record.get("operator_task_state"), dict) else {}
        task_steps = _normalize_task_steps(record.get("task_steps"))
        operator_task = {
            "source": "operator" if ops.get("locked") else "none",
            "outstanding_steps": list(record.get("outstanding_steps") or []),
            "completed_steps": [
                {
                    "step_id": s["step_id"],
                    "description": s["description"],
                    "completion_source": s.get("completion_source") or "operator",
                }
                for s in task_steps
                if s.get("status") == "completed"
            ],
            "pending_steps": [
                {"step_id": s["step_id"], "description": s["description"]}
                for s in task_steps
                if s.get("status") == "pending"
            ],
            "next_safe_action": record.get("next_safe_action") or "",
            "advancement_needs_review": bool(record.get("advancement_needs_review")),
            "checkpoint_revision": int(record.get("checkpoint_revision") or 0),
            "authoritative": bool(ops.get("locked")),
        }
        continuity_note = (
            "Conversation continuity checkpoint is untrusted reconstructed context, "
            "not authorization and not durable personal memory. Durable memory evidence "
            "in the context bundle overrides outdated checkpoint claims when they conflict. "
            "When operator_task_state.authoritative is true, its outstanding_steps and "
            "next_safe_action override any conflicting generated summary in conversation history. "
            "Only the operator may mark steps completed; never invent completed work."
        )
        return {
            "conversation_id": conversation_id,
            "rolled_over": rolled,
            "budget_tokens": budget,
            "usable_tokens": usable,
            "estimated_tokens": usable - remaining,
            "recent_conversation": recent,
            "checkpoint": facing_checkpoint,
            "operator_task_state": operator_task,
            "continuity_note": continuity_note,
            "objective": record.get("objective") or "",
            "next_safe_action": record.get("next_safe_action") or "",
            "outstanding_steps": list(record.get("outstanding_steps") or []),
            "missing": self._missing_fields(record),
        }

    def shutdown_checkpoint_if_dirty(self, conversation_id: str) -> Optional[Dict[str, Any]]:
        record = self.get(conversation_id)
        if not record.get("messages"):
            return None
        return self.write_checkpoint(conversation_id, reason="shutdown")

    def _missing_fields(self, record: Mapping[str, Any]) -> List[str]:
        missing = []
        if not record.get("objective"):
            missing.append("objective")
        next_action = (record.get("next_safe_action") or "").strip()
        if not record.get("outstanding_steps") and not next_action:
            missing.append("next_step")
        return missing

    def _build_checkpoint(self, record: Mapping[str, Any], *, reason: str) -> Dict[str, Any]:
        revision = int(record.get("checkpoint_revision") or 0) + 1
        messages = list(record.get("messages") or [])
        source_ids = [m.get("message_id") for m in messages[-12:] if isinstance(m, dict)]
        ops = record.get("operator_task_state") if isinstance(record.get("operator_task_state"), dict) else {}
        body = {
            "schema": SCHEMA_CHECKPOINT,
            "conversation_id": record["conversation_id"],
            "revision": revision,
            "reason": reason,
            "title": record.get("title"),
            "objective": record.get("objective") or "",
            "completion_condition": record.get("completion_condition") or "",
            "constraints": list(record.get("constraints") or [])[:12],
            "confirmed_facts": list(record.get("confirmed_facts") or [])[:20],
            "assumptions": list(record.get("assumptions") or [])[:12],
            "completed_work": list(record.get("completed_work") or [])[:20],
            "outstanding_steps": list(record.get("outstanding_steps") or [])[:20],
            "task_steps": _normalize_task_steps(record.get("task_steps")),
            "next_safe_action": record.get("next_safe_action") or "",
            "advancement_needs_review": bool(record.get("advancement_needs_review")),
            "unresolved_questions": list(record.get("unresolved_questions") or [])[:12],
            "memory_refs": list(record.get("memory_refs") or [])[:20],
            "status": record.get("status") or "active",
            "source_message_ids": [s for s in source_ids if isinstance(s, str)],
            "created_utc": _utc_now(),
            "trust": "untrusted_reconstructed_context",
            "authorization_state": "none",
            "task_state_source": "operator" if ops.get("locked") else "derived",
            "operator_authored": {
                "outstanding_steps": bool(ops.get("outstanding_steps")),
                "next_safe_action": bool(ops.get("next_safe_action")),
            },
        }
        # Hash without mutable timestamp for idempotency of content.
        content_for_hash = {k: v for k, v in body.items() if k not in {"created_utc", "revision", "reason"}}
        body["content_sha256"] = hashlib.sha256(_canonical(content_for_hash).encode("utf-8")).hexdigest()
        return body

    def _model_facing_checkpoint(self, checkpoint: Mapping[str, Any]) -> Dict[str, Any]:
        # Strip hashes/internal ids that are unnecessary for the model; keep provenance refs.
        return {
            "schema": SCHEMA_CHECKPOINT,
            "conversation_id": checkpoint.get("conversation_id"),
            "revision": checkpoint.get("revision"),
            "objective": checkpoint.get("objective"),
            "constraints": checkpoint.get("constraints"),
            "confirmed_facts": checkpoint.get("confirmed_facts"),
            "assumptions": checkpoint.get("assumptions"),
            "completed_work": checkpoint.get("completed_work"),
            "outstanding_steps": checkpoint.get("outstanding_steps"),
            "task_steps": checkpoint.get("task_steps") or [],
            "next_safe_action": checkpoint.get("next_safe_action"),
            "advancement_needs_review": bool(checkpoint.get("advancement_needs_review")),
            "unresolved_questions": checkpoint.get("unresolved_questions"),
            "memory_refs": checkpoint.get("memory_refs"),
            "status": checkpoint.get("status"),
            "task_state_source": checkpoint.get("task_state_source") or "derived",
            "operator_authored": checkpoint.get("operator_authored") or {},
            "trust": "untrusted_reconstructed_context",
            "authorization_state": "none",
        }

    def _project_tokens(
        self,
        *,
        system_text: str,
        user_message: str,
        memory_bundle: Optional[Mapping[str, Any]],
        recent: Sequence[Mapping[str, Any]],
        checkpoint: Optional[Mapping[str, Any]],
    ) -> int:
        total = estimate_tokens(system_text) + estimate_tokens(user_message)
        if memory_bundle is not None:
            total += estimate_tokens(_canonical(memory_bundle))
        if checkpoint is not None:
            total += estimate_tokens(_canonical(checkpoint))
        for msg in recent:
            total += estimate_tokens(str(msg.get("content") or "")) + 4
        return total

    def _load_unlocked(self, conversation_id: str) -> Dict[str, Any]:
        path = self._conv_path(conversation_id)
        if not path.is_file():
            raise ContinuityError("conversation not found")
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or data.get("schema") != SCHEMA_CONVERSATION:
            raise ContinuityError("malformed conversation record")
        return data

    def _upsert_index(self, record: Mapping[str, Any]) -> None:
        index_path = self.root / "index.json"
        index = json.loads(index_path.read_text(encoding="utf-8"))
        rows = [r for r in (index.get("conversations") or []) if isinstance(r, dict)]
        rows = [r for r in rows if r.get("conversation_id") != record.get("conversation_id")]
        rows.insert(
            0,
            {
                "conversation_id": record.get("conversation_id"),
                "title": record.get("title"),
                "objective": (record.get("objective") or "")[:120],
                "status": record.get("status"),
                "updated_utc": record.get("updated_utc"),
                "checkpoint_revision": record.get("checkpoint_revision") or 0,
            },
        )
        index = {
            "schema": "elysia.conversation-index.v1",
            "conversations": rows[:100],
        }
        _atomic_write_json(index_path, index)


def resolve_conversation_root(disposable_root: Path | str) -> Path:
    root = Path(disposable_root) / "conversations"
    root.mkdir(parents=True, exist_ok=True)
    return root
