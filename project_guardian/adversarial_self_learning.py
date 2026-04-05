# project_guardian/adversarial_self_learning.py
# Closed-loop behavioral driver: adversarial self-learning for weakness discovery,
# decision refinement, and self-improvement. Event-driven triggers + structured
# findings + downstream consumers + priority influence + outcome tracking.
# Findings use lifecycle states: open -> remediation_in_progress -> task_completed_unverified
# -> resolved_verified (only after verification passes). Task completion alone does NOT
# mark resolved.

import datetime
import json
import logging
import time
import uuid
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

logger = logging.getLogger(__name__)

# --- Finding lifecycle states ---
FINDING_STATE_OPEN = "open"
FINDING_STATE_REMEDIATION_IN_PROGRESS = "remediation_in_progress"
FINDING_STATE_TASK_COMPLETED_UNVERIFIED = "task_completed_unverified"
FINDING_STATE_RESOLVED_VERIFIED = "resolved_verified"
FINDING_STATE_REPEATED_UNRESOLVED = "repeated_unresolved"

# --- Structured finding types ---
FINDING_TYPE_REPEATED_FAILURE = "repeated_failure"
FINDING_TYPE_CLEANUP_ANOMALY = "cleanup_control_anomaly"
FINDING_TYPE_NOISY_LEARNING = "noisy_learning_pattern"
FINDING_TYPE_DEGRADED_VECTOR = "degraded_vector_state"
FINDING_TYPE_STARTUP_WEAKNESS = "startup_configuration_weakness"
FINDING_TYPE_TASK_CONTRADICTION = "task_outcome_contradiction"

# --- Event triggers (throttle keys) ---
TRIGGER_REPEATED_ERROR = "repeated_error"
TRIGGER_CLEANUP_ANOMALY = "cleanup_anomaly"
TRIGGER_VECTOR_DEGRADED = "vector_degraded"
TRIGGER_STARTUP_WARNINGS = "startup_warnings"
TRIGGER_BAD_LEARNING_SESSION = "bad_learning_session"
TRIGGER_PERIODIC = "periodic"

_EVENT_THROTTLE_SEC = 300  # 5 min between same trigger type
_OPERATIONAL_POLICY_PATH = Path(__file__).parent.parent / "config" / "adversarial_policy_recommendations.json"
_VERIFY_RECENT_WINDOW = 30  # memories to check for repeated_failure verification
_VERIFY_LEARNING_WINDOW = 10  # recent learning sessions for noisy_learning verification


@dataclass
class AdversarialFinding:
    """Structured finding with full metadata and lifecycle."""
    finding_id: str
    type: str
    severity: str  # low, medium, high, critical
    source: str
    evidence: Dict[str, Any]
    recommended_action: str
    auto_actionable: bool
    summary: str
    created_at: str
    created_task_ids: List[int] = field(default_factory=list)
    triggered_by: str = ""
    # Lifecycle: open -> remediation_in_progress -> task_completed_unverified -> resolved_verified
    # repeated_unresolved = same finding recurred after task completion
    state: str = FINDING_STATE_OPEN
    state_changed_at: Optional[str] = None
    recurrence_count: int = 1
    last_seen_at: Optional[str] = None
    # Legacy compat
    resolved: bool = False
    resolved_at: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        # Keep resolved in sync with state for backwards compat
        d["resolved"] = self.state == FINDING_STATE_RESOLVED_VERIFIED
        d["resolved_at"] = self.state_changed_at if self.state == FINDING_STATE_RESOLVED_VERIFIED else None
        return d


def _verify_repeated_failure(guardian, finding: Dict) -> bool:
    """Resolved only if same failure has not recurred in recent window."""
    memory = getattr(guardian, "memory", None)
    if not memory:
        return False
    sample = (finding.get("evidence") or {}).get("sample", "")[:80]
    if not sample:
        return False
    recent = _get_recent_memories(memory, "error", limit=_VERIFY_RECENT_WINDOW)
    matches = [m for m in recent if (m.get("thought") or "")[:80] == sample]
    return len(matches) < 2


def _verify_degraded_vector(guardian) -> bool:
    """Resolved only if vector_degraded=false and rebuild_pending=false."""
    if not hasattr(guardian, "get_startup_operational_state"):
        return False
    try:
        op = guardian.get_startup_operational_state()
        return not op.get("vector_degraded", True) and not op.get("vector_rebuild_pending", True)
    except Exception:
        return False


def _verify_cleanup_anomaly(guardian) -> bool:
    """Resolved only if subsequent cleanup no longer shows anomaly (pressure_no_op reset)."""
    mon = getattr(guardian, "monitor", None)
    if not mon or not hasattr(mon, "_pressure_no_op_count"):
        return False
    return getattr(mon, "_pressure_no_op_count", 999) == 0


def _verify_noisy_learning(guardian) -> bool:
    """Resolved only if later learning sessions improved (recent learning memories)."""
    memory = getattr(guardian, "memory", None)
    if not memory:
        return False
    learning = _get_recent_memories(memory, "learning", limit=_VERIFY_LEARNING_WINDOW)
    if len(learning) < 2:
        return True  # No recent noisy pattern
    low = [m for m in learning if (m.get("priority") or 0.5) < 0.4]
    return len(low) < len(learning) * 0.5  # Improved: fewer than half low-priority


def verify_finding(guardian, finding_id: str) -> bool:
    """
    Run verification for a finding. Returns True iff the underlying weakness is gone.
    Only call for findings in task_completed_unverified or remediation_in_progress.
    """
    reg = _ensure_registry(guardian)
    by_id = reg.get("findings_by_id", {})
    f = by_id.get(finding_id)
    if not f or f.get("state") not in (
        FINDING_STATE_TASK_COMPLETED_UNVERIFIED,
        FINDING_STATE_REMEDIATION_IN_PROGRESS,
    ):
        return False
    ftype = f.get("type", "")
    if ftype == FINDING_TYPE_REPEATED_FAILURE:
        return _verify_repeated_failure(guardian, f)
    if ftype == FINDING_TYPE_DEGRADED_VECTOR:
        return _verify_degraded_vector(guardian)
    if ftype == FINDING_TYPE_CLEANUP_ANOMALY:
        return _verify_cleanup_anomaly(guardian)
    if ftype == FINDING_TYPE_NOISY_LEARNING:
        return _verify_noisy_learning(guardian)
    # task_outcome_contradiction, startup_configuration_weakness: no auto-verify
    return False


def _get_recent_memories(memory, category: Optional[str] = None, limit: int = 50) -> List[Dict]:
    if not memory or not hasattr(memory, "get_recent_memories"):
        return []
    try:
        recent = memory.get_recent_memories(limit=limit, category=category, load_if_needed=True)
        return list(recent)[:limit]
    except Exception:
        return []


def _ensure_registry(guardian) -> Dict[str, Any]:
    """Get or create adversarial registry on guardian."""
    if not hasattr(guardian, "_adversarial_registry"):
        guardian._adversarial_registry = {
            "unresolved": [],  # finding_id list
            "findings_by_id": {},
            "dedup_key_to_id": {},  # dedup_key -> finding_id for escalation
            "trigger_throttle": {},  # trigger -> last_ts
        }
    reg = guardian._adversarial_registry
    reg.setdefault("dedup_key_to_id", {})
    return reg


def _should_throttle(guardian, trigger: str) -> bool:
    reg = _ensure_registry(guardian)
    last = reg.get("trigger_throttle", {}).get(trigger, 0)
    return (time.time() - last) < _EVENT_THROTTLE_SEC


def _record_trigger(guardian, trigger: str) -> None:
    reg = _ensure_registry(guardian)
    if "trigger_throttle" not in reg:
        reg["trigger_throttle"] = {}
    reg["trigger_throttle"][trigger] = time.time()


def _finding_dedup_key(f: "AdversarialFinding") -> str:
    """Stable key for dedup/escalation: type + source + normalized evidence fingerprint."""
    ev = f.evidence or {}
    sample = (ev.get("sample") or ev.get("sample_thought") or "")[:50]
    skip = ev.get("skip_count", 0)
    count = ev.get("count", 0)
    low = ev.get("low_count", 0)
    # For degraded_vector/startup, use type+source only
    if f.type == FINDING_TYPE_DEGRADED_VECTOR or f.type == FINDING_TYPE_STARTUP_WEAKNESS:
        return f"{f.type}:{f.source}"
    return f"{f.type}:{f.source}:{sample}:{skip}:{count}:{low}"


def _escalate_severity(sev: str) -> str:
    if sev == "low":
        return "medium"
    if sev == "medium":
        return "high"
    return "critical"


def _make_finding(
    type: str,
    severity: str,
    source: str,
    evidence: Dict[str, Any],
    recommended_action: str,
    auto_actionable: bool,
    summary: str,
    triggered_by: str = "",
    recurrence_count: int = 1,
    last_seen_at: Optional[str] = None,
) -> AdversarialFinding:
    now = datetime.datetime.now().isoformat()
    return AdversarialFinding(
        finding_id=f"adv_{uuid.uuid4().hex[:12]}",
        type=type,
        severity=severity,
        source=source,
        evidence=evidence,
        recommended_action=recommended_action,
        auto_actionable=auto_actionable,
        summary=summary,
        created_at=now,
        triggered_by=triggered_by,
        recurrence_count=recurrence_count,
        last_seen_at=last_seen_at or now,
    )


def _analyze_repeated_failures(memories: List[Dict]) -> List[AdversarialFinding]:
    findings = []
    errors = [m for m in memories if m.get("category") == "error"]
    if len(errors) < 2:
        return []
    seen: Dict[str, List] = {}
    for e in errors:
        thought = (e.get("thought") or "")[:80]
        if thought not in seen:
            seen[thought] = []
        seen[thought].append(e)
    for prefix, group in seen.items():
        if len(group) >= 2:
            findings.append(_make_finding(
                type=FINDING_TYPE_REPEATED_FAILURE,
                severity="high" if len(group) >= 4 else "medium",
                source="memory",
                evidence={"count": len(group), "sample": group[0].get("thought", "")[:200]},
                recommended_action="investigate_repeated_failure",
                auto_actionable=True,
                summary=f"Repeated failure ({len(group)}x): {prefix[:60]}...",
            ))
    return findings


def _analyze_cleanup_anomalies(memories: List[Dict]) -> List[AdversarialFinding]:
    cleanup = [m for m in memories if "cleanup" in (m.get("thought") or "").lower() or "consolidat" in (m.get("thought") or "").lower() or m.get("category") == "monitoring"]
    skips = [m for m in cleanup if "skip" in (m.get("thought") or "").lower()]
    if len(skips) >= 3:
        return [_make_finding(
            type=FINDING_TYPE_CLEANUP_ANOMALY,
            severity="medium",
            source="memory",
            evidence={"skip_count": len(skips)},
            recommended_action="review_cleanup_threshold",
            auto_actionable=True,
            summary=f"Multiple cleanup skips ({len(skips)}); memory pressure or threshold mismatch",
        )]
    return []


def _analyze_noisy_learning(memories: List[Dict]) -> List[AdversarialFinding]:
    learning = [m for m in memories if m.get("category") == "learning"]
    if not learning:
        return []
    low = [m for m in learning if (m.get("priority") or 0.5) < 0.4]
    if len(low) >= 5 and len(low) >= len(learning) * 0.5:
        return [_make_finding(
            type=FINDING_TYPE_NOISY_LEARNING,
            severity="medium",
            source="memory",
            evidence={"low_count": len(low), "total": len(learning)},
            recommended_action="review_learning_admission",
            auto_actionable=True,
            summary=f"Noisy learning: {len(low)}/{len(learning)} low-priority; tighten filters",
        )]
    return []


def _analyze_task_outcomes(tasks: List[Dict]) -> List[AdversarialFinding]:
    if not tasks:
        return []
    failed = [t for t in tasks if t.get("status") in ("failed", "cancelled") or t.get("completed") is False]
    if len(failed) >= 3:
        return [_make_finding(
            type=FINDING_TYPE_TASK_CONTRADICTION,
            severity="medium",
            source="tasks",
            evidence={"failed_count": len(failed)},
            recommended_action="review_task_queue",
            auto_actionable=True,
            summary=f"Multiple unresolved tasks ({len(failed)}); reprioritization needed",
        )]
    return []


def _inject_finding_from_event(finding: AdversarialFinding, guardian, context: Dict) -> Optional[AdversarialFinding]:
    """Inject a single finding from an event (e.g. vector degraded, startup warnings)."""
    reg = _ensure_registry(guardian)
    reg.setdefault("findings_by_id", {})[finding.finding_id] = finding.to_dict()
    reg.setdefault("unresolved", []).append(finding.finding_id)
    if len(reg["unresolved"]) > 50:
        reg["unresolved"] = reg["unresolved"][-50:]
    return finding


def trigger_adversarial_on_event(
    guardian,
    triggered_by: str,
    context: Optional[Dict[str, Any]] = None,
) -> Optional[Dict[str, Any]]:
    """
    Event-driven trigger. Call when specific events occur.
    Throttled per trigger type. Returns result dict or None if throttled.
    """
    if _should_throttle(guardian, triggered_by):
        logger.debug("[Adversarial] Event %s throttled", triggered_by)
        return None
    _record_trigger(guardian, triggered_by)
    ctx = context or {}

    memory = getattr(guardian, "memory", None)
    if not memory:
        return None

    findings: List[AdversarialFinding] = []

    if triggered_by == TRIGGER_REPEATED_ERROR:
        recent = _get_recent_memories(memory, "error", limit=30)
        findings = _analyze_repeated_failures(recent)
    elif triggered_by == TRIGGER_CLEANUP_ANOMALY:
        recent = _get_recent_memories(memory, None, limit=80)
        findings = _analyze_cleanup_anomalies(recent)
        if not findings and ctx.get("skip_count", 0) >= 2:
            findings = [_make_finding(
                type=FINDING_TYPE_CLEANUP_ANOMALY,
                severity="medium",
                source="monitoring",
                evidence=ctx,
                recommended_action="review_cleanup_threshold",
                auto_actionable=True,
                summary=f"Repeated cleanup no-op ({ctx.get('skip_count', 0)} skips); threshold/context mismatch",
                triggered_by=triggered_by,
            )]
    elif triggered_by == TRIGGER_VECTOR_DEGRADED:
        findings = [_make_finding(
            type=FINDING_TYPE_DEGRADED_VECTOR,
            severity="high",
            source="operational_state",
            evidence=ctx,
            recommended_action="prioritize_vector_rebuild",
            auto_actionable=True,
            summary="Vector memory degraded or rebuild pending",
            triggered_by=triggered_by,
        )]
    elif triggered_by == TRIGGER_STARTUP_WARNINGS:
        findings = [_make_finding(
            type=FINDING_TYPE_STARTUP_WEAKNESS,
            severity="medium",
            source="startup_verification",
            evidence=ctx,
            recommended_action="review_startup_config",
            auto_actionable=False,
            summary="Startup completed with warnings",
            triggered_by=triggered_by,
        )]
    elif triggered_by == TRIGGER_BAD_LEARNING_SESSION:
        fetched = ctx.get("fetched", 0)
        rejected = ctx.get("rejected", 0)
        admitted = ctx.get("admitted", 0)
        if fetched > 0 and rejected > 0:
            ratio = rejected / fetched
            if ratio >= 0.7 or (admitted == 0 and fetched >= 3):
                findings = [_make_finding(
                    type=FINDING_TYPE_NOISY_LEARNING,
                    severity="medium",
                    source="auto_learning",
                    evidence=ctx,
                    recommended_action="tighten_learning_filters",
                    auto_actionable=True,
                    summary=f"Bad learning session: {rejected}/{fetched} rejected, {admitted} admitted",
                    triggered_by=triggered_by,
                )]

    if not findings:
        return None

    return _apply_findings(guardian, findings, triggered_by)


def _run_verification_pass(guardian) -> int:
    """Verify task_completed_unverified findings. Returns count newly verified."""
    reg = _ensure_registry(guardian)
    by_id = reg.get("findings_by_id", {})
    verified_count = 0
    for fid, f in list(by_id.items()):
        if f.get("state") != FINDING_STATE_TASK_COMPLETED_UNVERIFIED:
            continue
        if verify_finding(guardian, fid):
            record_finding_resolution(guardian, fid, resolved=True, verified=True)
            verified_count += 1
    return verified_count


def _apply_findings(guardian, findings: List[AdversarialFinding], triggered_by: str) -> Dict[str, Any]:
    """Apply findings: dedup/escalation, memory, tasks, downstream consumers, registry."""
    memory = getattr(guardian, "memory", None)
    tasks_engine = getattr(guardian, "tasks", None)
    reg = _ensure_registry(guardian)
    dedup = reg.get("dedup_key_to_id", {})
    by_id = reg.get("findings_by_id", {})

    # Dedup/escalation: update existing instead of creating duplicate
    to_apply: List[Tuple[AdversarialFinding, bool]] = []  # (finding, is_update)
    for f in findings:
        dk = _finding_dedup_key(f)
        existing_id = dedup.get(dk)
        if existing_id and existing_id in by_id:
            ex = by_id[existing_id]
            ex_state = ex.get("state", FINDING_STATE_OPEN)
            if ex_state == FINDING_STATE_RESOLVED_VERIFIED:
                # Resolved in past - same issue recurred; treat as new
                to_apply.append((f, False))
                dedup[dk] = f.finding_id
            else:
                # Update existing: bump recurrence, escalate if needed
                ex["recurrence_count"] = ex.get("recurrence_count", 1) + 1
                ex["last_seen_at"] = datetime.datetime.now().isoformat()
                if ex["recurrence_count"] >= 3:
                    ex["severity"] = _escalate_severity(ex.get("severity", "medium"))
                    ex["state"] = FINDING_STATE_REPEATED_UNRESOLVED
                # Reconstruct finding for downstream - use existing
                existing_f = AdversarialFinding(
                    finding_id=ex["finding_id"], type=ex["type"], severity=ex["severity"],
                    source=ex["source"], evidence=ex.get("evidence", {}),
                    recommended_action=ex.get("recommended_action", ""),
                    auto_actionable=ex.get("auto_actionable", False), summary=ex.get("summary", ""),
                    created_at=ex.get("created_at", ""), created_task_ids=ex.get("created_task_ids", []),
                    triggered_by=ex.get("triggered_by", ""), state=ex.get("state", FINDING_STATE_OPEN),
                    state_changed_at=ex.get("state_changed_at"), recurrence_count=ex.get("recurrence_count", 1),
                    last_seen_at=ex.get("last_seen_at"), resolved=ex.get("resolved", False),
                    resolved_at=ex.get("resolved_at"),
                )
                to_apply.append((existing_f, True))
                continue
        else:
            to_apply.append((f, False))
            dedup[dk] = f.finding_id

    # Prune dedup entries for resolved findings
    for fid in list(by_id.keys()):
        f = by_id[fid]
        if f.get("state") == FINDING_STATE_RESOLVED_VERIFIED:
            for k, v in list(dedup.items()):
                if v == fid:
                    del dedup[k]
                    break

    to_apply = to_apply[:5]
    result = {
        "findings_count": len(to_apply),
        "top_weakness": to_apply[0][0].summary if to_apply else None,
        "top_type": to_apply[0][0].type if to_apply else None,
        "top_severity": to_apply[0][0].severity if to_apply else None,
        "tasks_created": 0,
        "memory_entries_written": 0,
        "last_run": datetime.datetime.now().isoformat(),
        "triggered_by": triggered_by,
        "findings": [f[0].to_dict() for f in to_apply],
    }

    for f, is_update in to_apply:
        fd = f.to_dict()
        fid = f.finding_id
        reg["findings_by_id"][fid] = fd
        if fid not in reg["unresolved"] and fd.get("state") != FINDING_STATE_RESOLVED_VERIFIED:
            reg["unresolved"].append(fid)
        if len(reg["unresolved"]) > 50:
            reg["unresolved"] = reg["unresolved"][-50:]

        summ = f.summary
        sev = f.severity
        ftype = f.type
        rec = f.recommended_action
        ev = f.evidence
        auto = f.auto_actionable
        created_tasks = f.created_task_ids

        if memory and not is_update:
            try:
                memory.remember(
                    f"[Adversarial Finding] {ftype}: {summ}",
                    category="adversarial_finding",
                    priority=0.9 if sev in ("high", "critical") else 0.7,
                    metadata={
                        "finding_id": fid,
                        "finding_type": ftype,
                        "severity": sev,
                        "recommended_action": rec,
                        "evidence": ev,
                        "auto_actionable": auto,
                        "triggered_by": triggered_by,
                    },
                )
                result["memory_entries_written"] += 1
            except Exception as e:
                logger.debug("Adversarial memory write: %s", e)

        if auto and sev in ("high", "critical", "medium") and tasks_engine and not created_tasks:
            try:
                t = tasks_engine.create_task(
                    name=f"Adversarial: {rec}",
                    description=summ,
                    priority=0.85 if sev in ("high", "critical") else 0.75,
                    category="adversarial",
                )
                result["tasks_created"] += 1
                reg["findings_by_id"][fid]["created_task_ids"] = reg["findings_by_id"][fid].get("created_task_ids", []) + [t.get("id")]
                reg["findings_by_id"][fid]["state"] = FINDING_STATE_REMEDIATION_IN_PROGRESS
                reg["findings_by_id"][fid]["state_changed_at"] = datetime.datetime.now().isoformat()
            except Exception as e:
                logger.debug("Adversarial task create: %s", e)

        if sev in ("high", "critical"):
            _write_policy_recommendation(f)

        if ftype == FINDING_TYPE_REPEATED_FAILURE and getattr(guardian, "prompt_evolver", None):
            _feed_hardening_to_prompt_evolver(guardian, f)

    _run_verification_pass(guardian)

    guardian._adversarial_last_run = result
    logger.info(
        "[Adversarial Self-Learning] Event %s: findings=%d top=%s tasks=%d",
        triggered_by, result["findings_count"],
        (result["top_weakness"] or "")[:50], result["tasks_created"],
    )
    return result


def _write_policy_recommendation(f: AdversarialFinding) -> None:
    try:
        _OPERATIONAL_POLICY_PATH.parent.mkdir(parents=True, exist_ok=True)
        data = []
        if _OPERATIONAL_POLICY_PATH.exists():
            try:
                with open(_OPERATIONAL_POLICY_PATH, "r") as fp:
                    data = json.load(fp)
            except Exception:
                pass
        data.append({
            "finding_id": f.finding_id,
            "type": f.type,
            "severity": f.severity,
            "recommended_action": f.recommended_action,
            "summary": f.summary,
            "created_at": f.created_at,
        })
        with open(_OPERATIONAL_POLICY_PATH, "w") as fp:
            json.dump(data[-100:], fp, indent=2)
    except Exception as e:
        logger.debug("Policy recommendation write: %s", e)


def _feed_hardening_to_prompt_evolver(guardian, f: AdversarialFinding) -> None:
    """Feed repeated-failure finding as hardening context to prompt evolver."""
    pe = getattr(guardian, "prompt_evolver", None)
    if not pe or not hasattr(pe, "records"):
        return
    try:
        # Store hardening hint for next evolution
        if not hasattr(pe, "_adversarial_hardening_hints"):
            pe._adversarial_hardening_hints = []
        pe._adversarial_hardening_hints.append({
            "finding_id": f.finding_id,
            "summary": f.summary,
            "created_at": f.created_at,
        })
        if len(pe._adversarial_hardening_hints) > 10:
            pe._adversarial_hardening_hints = pe._adversarial_hardening_hints[-10:]
    except Exception as e:
        logger.debug("Prompt evolver hardening: %s", e)


def _is_active_state(state: str) -> bool:
    """Active = not resolved_verified."""
    return state != FINDING_STATE_RESOLVED_VERIFIED


def get_recent_findings(guardian, unresolved_only: bool = True, active_states_only: bool = True) -> List[Dict[str, Any]]:
    """Return recent findings for get_next_action to consult. Active = open, remediation, task_completed_unverified, repeated_unresolved."""
    reg = getattr(guardian, "_adversarial_registry", None)
    if not reg:
        return []
    by_id = reg.get("findings_by_id", {})
    ids = reg.get("unresolved", []) if unresolved_only else list(by_id.keys())
    out = []
    for fid in ids[-20:]:
        if fid in by_id:
            f = by_id[fid]
            if unresolved_only and f.get("resolved"):
                continue
            if active_states_only and not _is_active_state(f.get("state", FINDING_STATE_OPEN)):
                continue
            out.append(f)
    return out


def get_execution_policy_effect(guardian) -> Dict[str, Any]:
    """
    Stronger policy effects from severe findings. Beyond score nudging.
    Returns: { suppress_actions: [], gate_actions: {gated_action: required_first}, bias_toward: [] }
    gate_actions format: {"consider_learning": "rebuild_vector"} means consider_learning is blocked
    until rebuild_vector is done (i.e. when required action is in candidates, gated action is blocked).
    """
    findings = get_recent_findings(guardian, unresolved_only=True, active_states_only=True)
    out: Dict[str, Any] = {"suppress_actions": [], "gate_actions": {}, "bias_toward": []}

    for f in findings:
        t = f.get("type", "")
        sev = f.get("severity", "")
        if sev not in ("high", "critical"):
            continue

        if t == FINDING_TYPE_NOISY_LEARNING and sev in ("high", "critical"):
            out["suppress_actions"].append("consider_learning")

        if t == FINDING_TYPE_DEGRADED_VECTOR and sev in ("high", "critical"):
            out["gate_actions"]["consider_learning"] = "rebuild_vector"
            out["gate_actions"]["consider_dream_cycle"] = "rebuild_vector"
            out["bias_toward"].append("rebuild_vector")

        if t == FINDING_TYPE_REPEATED_FAILURE and sev in ("high", "critical"):
            out["bias_toward"].extend(["execute_task", "consider_adversarial_learning"])
            out["suppress_actions"].extend(["consider_learning", "consider_dream_cycle"])

    out["suppress_actions"] = list(set(out["suppress_actions"]))
    out["bias_toward"] = list(dict.fromkeys(out["bias_toward"]))  # preserve order, dedup
    return out


def get_active_gates(guardian) -> Dict[str, str]:
    """Return currently active gates: {gated_action: required_action}."""
    policy = get_execution_policy_effect(guardian)
    return policy.get("gate_actions", {})


def apply_execution_policy_to_candidates(
    candidates: List[Dict[str, Any]],
    policy: Dict[str, Any],
    log_fn: Optional[Any] = None,
) -> Tuple[List[Dict[str, Any]], List[Tuple[str, str]]]:
    """
    Enforce suppress_actions and gate_actions on candidates.
    Returns (filtered_candidates, gated_out) where gated_out is [(action, reason), ...].
    Gate logic: if gated_action requires required_action, and required_action is in candidates,
    remove gated_action (block until required is done).
    """
    gate_actions = policy.get("gate_actions", {})
    suppress = set(policy.get("suppress_actions", []))
    candidate_actions = {c.get("action") for c in candidates}

    # 1. Apply suppression
    filtered = [c for c in candidates if c.get("action") not in suppress]

    # 2. Apply gating: remove gated actions when their required action is available
    gated_out: List[Tuple[str, str]] = []
    for gated_action, required_action in gate_actions.items():
        if required_action not in candidate_actions:
            continue  # Required not available - gate not enforceable, keep gated
        filtered_before = len(filtered)
        filtered = [c for c in filtered if c.get("action") != gated_action]
        if len(filtered) < filtered_before:
            reason = f"gated_by:{required_action}"
            gated_out.append((gated_action, reason))
            if log_fn:
                log_fn(f"Gate: {gated_action} blocked (requires {required_action} first)")

    return filtered, gated_out


def get_finding_priority_boost(action: str, findings: List[Dict]) -> float:
    """
    Return priority boost/reduction for an action based on findings.
    Positive = boost, negative = reduce.
    """
    boost = 0.0
    for f in findings:
        t = f.get("type", "")
        rec = f.get("recommended_action", "")
        sev = f.get("severity", "")
        if t == FINDING_TYPE_REPEATED_FAILURE and action in ("execute_task", "consider_adversarial_learning"):
            if "investigate" in rec or "diagnosis" in rec:
                boost += 1.5
        if t == FINDING_TYPE_NOISY_LEARNING and action == "consider_learning":
            boost -= 1.0
        if t == FINDING_TYPE_DEGRADED_VECTOR and action in ("rebuild_vector", "consider_adversarial_learning", "execute_task"):
            if "vector" in rec:
                boost += 2.0
        if t == FINDING_TYPE_CLEANUP_ANOMALY and action in ("consider_adversarial_learning", "execute_task"):
            boost += 1.0
    return boost


def record_task_completed(guardian, finding_id: str) -> None:
    """
    Called when an adversarial task completes. Does NOT mark resolved.
    Transitions: open/remediation_in_progress -> task_completed_unverified.
    Verification must pass separately to reach resolved_verified.
    """
    reg = _ensure_registry(guardian)
    by_id = reg.get("findings_by_id", {})
    if finding_id not in by_id:
        return
    now = datetime.datetime.now().isoformat()
    by_id[finding_id]["state"] = FINDING_STATE_TASK_COMPLETED_UNVERIFIED
    by_id[finding_id]["state_changed_at"] = now
    by_id[finding_id]["resolved"] = False
    by_id[finding_id]["resolved_at"] = None
    logger.info("[Adversarial] Finding %s -> task_completed_unverified (awaiting verification)", finding_id)


def record_finding_resolution(guardian, finding_id: str, resolved: bool = True, verified: bool = False) -> None:
    """
    Mark finding as resolved. Use verified=True only when verification passed.
    If resolved=True but verified=False, we still treat as task_completed_unverified
    for policy purposes - no auto-resolve without verification.
    """
    reg = _ensure_registry(guardian)
    by_id = reg.get("findings_by_id", {})
    if finding_id not in by_id:
        return
    now = datetime.datetime.now().isoformat()
    if resolved and verified:
        by_id[finding_id]["state"] = FINDING_STATE_RESOLVED_VERIFIED
        by_id[finding_id]["state_changed_at"] = now
        by_id[finding_id]["resolved"] = True
        by_id[finding_id]["resolved_at"] = now
        if finding_id in reg.get("unresolved", []):
            reg["unresolved"] = [x for x in reg["unresolved"] if x != finding_id]
        logger.info("[Adversarial] Finding %s -> resolved_verified", finding_id)
    elif not resolved:
        by_id[finding_id]["state"] = FINDING_STATE_REPEATED_UNRESOLVED
        by_id[finding_id]["state_changed_at"] = now
        by_id[finding_id]["resolved"] = False
        by_id[finding_id]["resolved_at"] = None


def run_adversarial_cycle(guardian, triggered_by: str = TRIGGER_PERIODIC) -> Dict[str, Any]:
    """Full analysis cycle. Used by autonomy and post-startup."""
    memory = getattr(guardian, "memory", None)
    tasks_engine = getattr(guardian, "tasks", None)
    if not memory:
        return {"findings_count": 0, "top_weakness": None, "tasks_created": 0, "memory_entries_written": 0, "last_run": None, "triggered_by": triggered_by}

    recent = _get_recent_memories(memory, None, limit=100)
    learning = _get_recent_memories(memory, "learning", limit=30)
    active_tasks = []
    if tasks_engine and hasattr(tasks_engine, "get_active_tasks"):
        try:
            active_tasks = tasks_engine.get_active_tasks()
        except Exception:
            pass

    findings: List[AdversarialFinding] = []
    findings.extend(_analyze_repeated_failures(recent))
    findings.extend(_analyze_cleanup_anomalies(recent))
    findings.extend(_analyze_noisy_learning(learning))
    findings.extend(_analyze_task_outcomes(active_tasks))

    seen = set()
    unique = []
    for f in findings:
        key = f"{f.type}:{f.summary[:50]}"
        if key not in seen:
            seen.add(key)
            unique.append(f)
    findings = sorted(unique, key=lambda x: (0 if x.severity == "critical" else 1 if x.severity == "high" else 2, x.created_at), reverse=True)

    if not findings:
        guardian._adversarial_last_run = {
            "findings_count": 0, "top_weakness": None, "tasks_created": 0, "memory_entries_written": 0,
            "last_run": datetime.datetime.now().isoformat(), "triggered_by": triggered_by, "findings": [],
        }
        return guardian._adversarial_last_run

    return _apply_findings(guardian, findings, triggered_by)


def get_adversarial_status(guardian) -> Dict[str, Any]:
    """Expanded visibility: last run, open/unverified/resolved counts, top_active_finding."""
    last = getattr(guardian, "_adversarial_last_run", None)
    reg = getattr(guardian, "_adversarial_registry", None)
    by_id = reg.get("findings_by_id", {}) if reg else {}

    open_count = sum(1 for f in by_id.values() if f.get("state") == FINDING_STATE_OPEN)
    remediation_count = sum(1 for f in by_id.values() if f.get("state") == FINDING_STATE_REMEDIATION_IN_PROGRESS)
    unverified_count = sum(1 for f in by_id.values() if f.get("state") == FINDING_STATE_TASK_COMPLETED_UNVERIFIED)
    resolved_count = sum(1 for f in by_id.values() if f.get("state") == FINDING_STATE_RESOLVED_VERIFIED)
    repeated_count = sum(1 for f in by_id.values() if f.get("state") == FINDING_STATE_REPEATED_UNRESOLVED)

    active = [f for f in by_id.values() if _is_active_state(f.get("state", FINDING_STATE_OPEN))]
    top_active = None
    if active:
        active.sort(key=lambda x: (0 if x.get("severity") == "critical" else 1 if x.get("severity") == "high" else 2, x.get("last_seen_at") or ""), reverse=True)
        top_active = active[0].get("summary", "")[:80]

    active_gates = get_active_gates(guardian) if guardian else {}

    base = {
        "last_run": last.get("last_run") if last else None,
        "findings_count": last.get("findings_count", 0) if last else 0,
        "top_weakness": last.get("top_weakness") if last else None,
        "top_type": last.get("top_type") if last else None,
        "top_severity": last.get("top_severity") if last else None,
        "tasks_created": last.get("tasks_created", 0) if last else 0,
        "memory_entries_written": last.get("memory_entries_written", 0) if last else 0,
        "last_triggered_by": last.get("triggered_by") if last else None,
        "open_findings_count": open_count,
        "unverified_completed_findings_count": unverified_count,
        "resolved_verified_findings_count": resolved_count,
        "unresolved_findings_count": open_count + remediation_count + unverified_count + repeated_count,
        "top_active_finding": top_active,
        "active_gates": active_gates,
    }
    return base
