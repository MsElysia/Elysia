# Lightweight contact/thread progression (bounded JSON store; no CRM, no auto-post).

from __future__ import annotations

import hashlib
import json
import logging
import re
import time
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .memory import ensure_social_data_dir

logger = logging.getLogger(__name__)

CONTINUITY_FILENAME = "continuity.json"

_DEFAULT_CONTACT: Dict[str, Any] = {
    "first_seen_at": None,
    "last_seen_at": None,
    "interaction_count": 0,
    "last_thread_id": "",
    "last_draft_at": None,
    "response_observed": False,
    "follow_up_status": "none",
    "relationship_stage": "new",
    "consecutive_low_yield": 0,
    "last_peak_person_score": 0.0,
    # Downstream outcome feedback (operator / pipeline; not inferred from browse alone)
    "successful_followups": 0,
    "ignored_followups": 0,
    "last_response_at": None,
    "response_quality": 0.0,
    "useful_outcome_count": 0,
}

_DEFAULT_THREAD: Dict[str, Any] = {
    "first_seen_at": None,
    "last_seen_at": None,
    "revisit_count": 0,
    "useful_followup_candidate": False,
    "follow_up_reason": "",
    "next_follow_up_hint": "",
    "last_observed_thread_id": "",
    "last_thread_score": 0.0,
    "useful_revisit_count": 0,
    "ignored_revisit_count": 0,
    "last_useful_at": None,
}


def stable_thread_key(visited_urls: List[str], goal: str) -> str:
    norm = sorted({(u or "").strip().lower() for u in (visited_urls or [])[:18] if u})
    joined = "|".join(norm)[:2400]
    g = re.sub(r"\s+", " ", (goal or "").lower().strip())[:180]
    h = hashlib.sha256(f"{joined}||{g}".encode("utf-8")).hexdigest()[:26]
    return f"tk_{h}"


def _continuity_path() -> Path:
    return ensure_social_data_dir() / CONTINUITY_FILENAME


def load_continuity() -> Dict[str, Any]:
    p = _continuity_path()
    if not p.exists():
        return {"version": 1, "contacts": {}, "threads": {}}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception as e:
        logger.warning("continuity: could not load %s: %s", p, e)
        return {"version": 1, "contacts": {}, "threads": {}}
    if not isinstance(data, dict):
        return {"version": 1, "contacts": {}, "threads": {}}
    data.setdefault("version", 1)
    data.setdefault("contacts", {})
    data.setdefault("threads", {})
    if not isinstance(data["contacts"], dict):
        data["contacts"] = {}
    if not isinstance(data["threads"], dict):
        data["threads"] = {}
    return data


def _prune_state(state: Dict[str, Any], max_contacts: int, max_threads: int) -> None:
    contacts: Dict[str, Any] = state.get("contacts") or {}
    if len(contacts) > max_contacts:
        items = sorted(
            contacts.items(),
            key=lambda kv: float((kv[1] or {}).get("last_seen_at") or 0),
        )
        drop = len(items) - max_contacts
        for k, _ in items[:drop]:
            contacts.pop(k, None)
    threads: Dict[str, Any] = state.get("threads") or {}
    if len(threads) > max_threads:
        items = sorted(
            threads.items(),
            key=lambda kv: float((kv[1] or {}).get("last_seen_at") or 0),
        )
        drop = len(items) - max_threads
        for k, _ in items[:drop]:
            threads.pop(k, None)


def save_continuity(state: Dict[str, Any], *, max_contacts: int, max_threads: int) -> None:
    _prune_state(state, max_contacts, max_threads)
    p = _continuity_path()
    tmp = p.with_suffix(".tmp")
    out = {"version": 1, "contacts": state.get("contacts") or {}, "threads": state.get("threads") or {}}
    tmp.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(p)


def _norm_contact_id(cid: str) -> str:
    c = (cid or "").strip()
    if c.startswith("@"):
        return "@" + c[1:].lower()
    return c


def apply_continuity_outcomes(
    state: Dict[str, Any],
    outcomes: Optional[Dict[str, Any]],
    now_ts: float,
    cfg: Dict[str, Any],
) -> bool:
    """
    Apply operator-reported outcomes (follow-up success/ignore, response quality, useful thread revisits).
    Mutates state; persists when anything changed. Returns whether a save ran.
    """
    if not isinstance(outcomes, dict) or not outcomes:
        return False
    contacts = state.setdefault("contacts", {})
    threads = state.setdefault("threads", {})
    changed = False

    for raw_id, patch in (outcomes.get("contacts") or {}).items():
        if not isinstance(patch, dict):
            continue
        cid = _norm_contact_id(str(raw_id))
        if not cid:
            continue
        c = {**_DEFAULT_CONTACT, **deepcopy(contacts.get(cid, {}))}
        touched = False

        if patch.get("followup_succeeded") is True:
            c["successful_followups"] = int(c.get("successful_followups") or 0) + 1
            touched = True
            logger.info(
                "social_followup_succeeded id=%s total=%s",
                cid[:48],
                c["successful_followups"],
            )
        if patch.get("followup_ignored") is True:
            c["ignored_followups"] = int(c.get("ignored_followups") or 0) + 1
            touched = True
            logger.info(
                "social_followup_ignored id=%s total=%s",
                cid[:48],
                c["ignored_followups"],
            )
        if patch.get("response_observed") is True:
            c["last_response_at"] = now_ts
            c["response_observed"] = True
            touched = True
            logger.info("social_response_observed id=%s", cid[:48])
        rq = patch.get("response_quality")
        if isinstance(rq, (int, float)) and 0.0 <= float(rq) <= 1.0:
            old = float(c.get("response_quality") or 0.0)
            c["response_quality"] = round(0.45 * old + 0.55 * float(rq), 3)
            touched = True
        if patch.get("useful_outcome") is True:
            c["useful_outcome_count"] = int(c.get("useful_outcome_count") or 0) + 1
            touched = True

        if touched:
            contacts[cid] = c
            changed = True

    for tk, patch in (outcomes.get("threads") or {}).items():
        if not isinstance(patch, dict) or not str(tk).strip():
            continue
        key = str(tk).strip()
        t = {**_DEFAULT_THREAD, **deepcopy(threads.get(key, {}))}
        touched = False
        if patch.get("useful_revisit") is True:
            t["useful_revisit_count"] = int(t.get("useful_revisit_count") or 0) + 1
            t["last_useful_at"] = now_ts
            touched = True
            logger.info(
                "social_thread_useful_revisit stable_key=%s count=%s",
                key[:36],
                t["useful_revisit_count"],
            )
        if patch.get("ignored_revisit") is True:
            t["ignored_revisit_count"] = int(t.get("ignored_revisit_count") or 0) + 1
            touched = True
        if touched:
            threads[key] = t
            changed = True

    if changed:
        save_continuity(
            state,
            max_contacts=int(cfg.get("max_contacts") or 400),
            max_threads=int(cfg.get("max_threads") or 250),
        )
    return changed


def apply_operator_continuity_notes(state: Dict[str, Any], notes: Optional[Dict[str, Any]]) -> None:
    if not isinstance(notes, dict):
        return
    contacts = state.setdefault("contacts", {})
    for cid, patch in notes.items():
        if not isinstance(patch, dict) or not cid:
            continue
        base = {**_DEFAULT_CONTACT, **deepcopy(contacts.get(cid, {}))}
        if patch.get("response_observed") is True:
            base["response_observed"] = True
        if str(patch.get("follow_up_status") or "").strip():
            base["follow_up_status"] = str(patch.get("follow_up_status")).strip()[:40]
        contacts[cid] = base


def days_between(now_ts: float, prior_ts: Optional[float]) -> float:
    if prior_ts is None or float(prior_ts) <= 0:
        return 0.0
    return max(0.0, (float(now_ts) - float(prior_ts)) / 86400.0)


def adjust_person_for_continuity(
    row: Dict[str, Any],
    *,
    prior: Dict[str, Any],
    now_ts: float,
    cfg: Dict[str, Any],
) -> Dict[str, Any]:
    """Mutates row person_score / likely_human / relevance_reasons; logs stale / recurrence / dead-end penalty."""
    stale_days = float(cfg.get("stale_days") or 21)

    ps = float(row.get("person_score") or 0.0)
    lh = float(row.get("likely_human") or 0.0)
    reasons = list(row.get("relevance_reasons") or [])
    pid = str(row.get("id") or "")

    ic = int(prior.get("interaction_count") or 0)
    stage = str(prior.get("relationship_stage") or "new")
    last_seen = prior.get("last_seen_at")
    gap_days = days_between(now_ts, float(last_seen) if last_seen is not None else None)

    if stage == "dead_end":
        ps *= 0.38
        lh *= 0.42
        reasons.append("continuity_dead_end_deprioritized")
    elif gap_days >= stale_days and ic >= 2:
        ps *= 0.84
        lh *= 0.9
        reasons.append("continuity_stale_contact")
        logger.info("social_contact_stale id=%s gap_days=%.1f prior_ic=%s", pid[:48], gap_days, ic)

    if ic >= 2 and stage != "dead_end" and ps >= 0.32:
        boost = min(0.12, 0.04 + 0.01 * min(ic, 8))
        ps = min(1.0, ps + boost)
        reasons.append("continuity_recurrence_boost")
        logger.info("social_recurrence_boost id=%s prior_ic=%s boost=%.3f", pid[:48], ic, boost)
    elif ic >= 1 and stage != "dead_end" and ps >= 0.35:
        ps = min(1.0, ps + 0.03)
        reasons.append("continuity_seen_before")

    if prior.get("response_observed") and stage != "dead_end":
        ps = min(1.0, ps + 0.05)
        reasons.append("continuity_prior_response_observed")

    sf = int(prior.get("successful_followups") or 0)
    ig = int(prior.get("ignored_followups") or 0)
    uo = int(prior.get("useful_outcome_count") or 0)
    rq = float(prior.get("response_quality") or 0.0)
    if stage != "dead_end" and sf >= 2 and uo >= 1:
        ob = min(0.09, 0.022 * min(sf, 6) + 0.018 * min(uo, 5))
        ps = min(1.0, ps + ob)
        reasons.append("outcome_reward_high_value_human")
        if sf >= 3 and uo >= 2:
            logger.info(
                "social_contact_promoted id=%s successful_followups=%s useful_outcomes=%s response_quality=%.2f",
                pid[:48],
                sf,
                uo,
                rq,
            )
    if ig >= 4 and sf <= 1:
        ps *= 0.82
        lh *= 0.9
        reasons.append("outcome_ignore_penalty")
        logger.info(
            "social_contact_demoted id=%s ignored_followups=%s successful_followups=%s",
            pid[:48],
            ig,
            sf,
        )
    if rq >= 0.55 and stage != "dead_end":
        ps = min(1.0, ps + 0.035 * rq)
        reasons.append("outcome_response_quality_signal")

    row["person_score"] = round(min(1.0, max(0.0, ps)), 3)
    row["likely_human"] = round(min(1.0, max(0.0, lh)), 3)
    row["relevance_reasons"] = reasons
    return row


def apply_thread_prior_to_rank(
    thread_rank: Dict[str, Any],
    *,
    thread_prior: Optional[Dict[str, Any]],
    cfg: Dict[str, Any],
) -> Dict[str, Any]:
    if not thread_prior:
        return thread_rank
    ts = float(thread_rank.get("thread_score") or 0.0)
    tr = list(thread_rank.get("thread_rank_reasons") or [])

    rc = int(thread_prior.get("revisit_count") or 0)
    if rc > 0:
        boost = min(0.08, 0.025 * min(rc, 5))
        ts += boost
        tr.append("continuity_thread_revisit")

    uur = int(thread_prior.get("useful_revisit_count") or 0)
    iur = int(thread_prior.get("ignored_revisit_count") or 0)
    if uur > 0:
        extra = min(float(cfg.get("thread_outcome_useful_cap") or 0.1), 0.017 * min(uur, 8))
        ts += extra
        tr.append("outcome_useful_thread_revisits")
    if iur >= max(2, uur + 2):
        drag = min(0.08, 0.018 * min(iur - max(0, uur), 8))
        ts -= drag
        tr.append("outcome_thread_ignore_drag")

    thread_rank = {**thread_rank, "thread_score": round(min(1.0, max(0.0, ts)), 3), "thread_rank_reasons": tr}
    return thread_rank


def merge_contact_after_session(
    prior: Dict[str, Any],
    *,
    person_row: Dict[str, Any],
    thread_id: str,
    now_ts: float,
    drafted_top: bool,
    cfg: Dict[str, Any],
) -> Tuple[Dict[str, Any], bool]:
    """
    Returns (new_contact_dict, progressed_flag).
    progressed_flag: first touch, stage change, or milestone interaction counts.
    """
    low_ps = float(cfg.get("low_yield_score_threshold") or 0.28)
    low_lh = float(cfg.get("low_yield_human_threshold") or 0.35)
    streak_dead = int(cfg.get("low_yield_streak_for_dead_end") or 3)
    stale_days = float(cfg.get("stale_days") or 21)

    c = {**_DEFAULT_CONTACT, **deepcopy(prior)}
    prev_ic = int(c.get("interaction_count") or 0)
    prev_stage = str(c.get("relationship_stage") or "new")
    prev_fu = str(c.get("follow_up_status") or "none")

    gap_days = days_between(
        now_ts,
        float(c.get("last_seen_at") or 0) if c.get("last_seen_at") is not None else None,
    )

    if c["first_seen_at"] is None:
        c["first_seen_at"] = now_ts
    c["last_seen_at"] = now_ts
    c["interaction_count"] = prev_ic + 1
    c["last_thread_id"] = thread_id[:120]
    c["last_peak_person_score"] = max(
        float(c.get("last_peak_person_score") or 0.0),
        float(person_row.get("person_score") or 0.0),
    )

    ps = float(person_row.get("person_score") or 0.0)
    lh = float(person_row.get("likely_human") or 0.0)
    if ps < low_ps and lh < low_lh:
        c["consecutive_low_yield"] = int(c.get("consecutive_low_yield") or 0) + 1
    else:
        c["consecutive_low_yield"] = 0

    new_stage: str
    if prev_stage == "dead_end" and ps >= 0.45 and lh >= 0.42:
        new_stage = "emerging"
        c["consecutive_low_yield"] = 0
    elif int(c["consecutive_low_yield"]) >= streak_dead:
        new_stage = "dead_end"
        if prev_stage != "dead_end":
            logger.info(
                "social_dead_end_deprioritized id=%s streak=%s",
                str(person_row.get("id") or "")[:48],
                c["consecutive_low_yield"],
            )
    elif gap_days >= stale_days and prev_ic >= 1:
        new_stage = "stale"
    else:
        ic = int(c["interaction_count"])
        if ic == 1:
            new_stage = "new"
        elif ic <= 3:
            new_stage = "emerging"
        elif ic <= 7:
            new_stage = "recurring"
        else:
            if float(c.get("last_peak_person_score") or 0.0) >= 0.58:
                new_stage = "trusted"
            else:
                new_stage = "recurring"
    c["relationship_stage"] = new_stage

    if drafted_top:
        c["last_draft_at"] = now_ts
        if prev_fu in ("none", "ignored", ""):
            c["follow_up_status"] = "drafted"

    new_ic = int(c["interaction_count"])
    new_fu = str(c.get("follow_up_status") or "none")
    progressed = (
        prev_ic == 0
        or new_stage != prev_stage
        or new_fu != prev_fu
        or new_ic in (2, 4, 8)
    )
    return c, progressed


def merge_thread_after_session(
    prior: Optional[Dict[str, Any]],
    *,
    stable_key: str,
    thread_id: str,
    thread_rank: Dict[str, Any],
    now_ts: float,
    hi_tf: float,
    mix_floor: float,
) -> Dict[str, Any]:
    t = {**_DEFAULT_THREAD, **deepcopy(prior or {})}
    if t.get("first_seen_at") is None:
        t["first_seen_at"] = now_ts
    t["last_seen_at"] = now_ts
    t["revisit_count"] = int(t.get("revisit_count") or 0) + 1
    t["last_observed_thread_id"] = thread_id[:120]
    ts = float(thread_rank.get("thread_score") or 0.0)
    mix = float(thread_rank.get("likely_discussion_human_mix") or 0.0)
    t["last_thread_score"] = ts
    useful = ts >= hi_tf and mix >= mix_floor
    t["useful_followup_candidate"] = bool(useful)
    reasons = list(thread_rank.get("thread_rank_reasons") or [])
    t["follow_up_reason"] = "; ".join(reasons[:6])[:500]
    t["next_follow_up_hint"] = str(thread_rank.get("suggested_next_interaction") or "")[:500]
    t["stable_key"] = stable_key
    return t


def persist_session_continuity(
    *,
    state: Dict[str, Any],
    stable_key: str,
    thread_id: str,
    ranked_people: List[Dict[str, Any]],
    thread_rank: Dict[str, Any],
    modes: Dict[str, bool],
    now_ts: float,
    cfg: Dict[str, Any],
    human_ranking_cfg: Dict[str, Any],
    prioritize_ids: List[str],
) -> Dict[str, Any]:
    """
    Updates state in memory and saves.
    Returns snapshot for thread_record + participant continuity blobs post-save.
    """
    hi_tf = float(human_ranking_cfg.get("high_value_followup_thread_floor") or 0.45)
    mix_floor = float(cfg.get("followup_mix_floor") or 0.38)

    contacts = state.setdefault("contacts", {})
    threads = state.setdefault("threads", {})
    prior_thread = threads.get(stable_key)

    merged_thread = merge_thread_after_session(
        prior_thread,
        stable_key=stable_key,
        thread_id=thread_id,
        thread_rank=thread_rank,
        now_ts=now_ts,
        hi_tf=hi_tf,
        mix_floor=mix_floor,
    )
    threads[stable_key] = {k: v for k, v in merged_thread.items() if k != "stable_key"}

    if merged_thread.get("useful_followup_candidate"):
        logger.info(
            "social_followup_candidate stable_key=%s revisit=%s thread_score=%.3f",
            stable_key[:32],
            merged_thread.get("revisit_count"),
            float(thread_rank.get("thread_score") or 0.0),
        )

    draft_on = bool(modes.get("draft"))
    prio = set(prioritize_ids)
    for row in ranked_people:
        pid = str(row.get("id") or "")
        if not pid:
            continue
        prior = contacts.get(pid, {})
        drafted = draft_on and pid in prio
        new_c, progressed = merge_contact_after_session(
            prior,
            person_row=row,
            thread_id=thread_id,
            now_ts=now_ts,
            drafted_top=drafted,
            cfg=cfg,
        )
        contacts[pid] = new_c
        if progressed:
            logger.info(
                "social_contact_progressed id=%s interactions=%s stage=%s follow_up=%s",
                pid[:48],
                new_c.get("interaction_count"),
                new_c.get("relationship_stage"),
                new_c.get("follow_up_status"),
            )

    save_continuity(
        state,
        max_contacts=int(cfg.get("max_contacts") or 400),
        max_threads=int(cfg.get("max_threads") or 250),
    )

    contact_snapshots = {
        str(r.get("id") or ""): deepcopy(contacts.get(str(r.get("id") or ""), {}))
        for r in ranked_people
        if r.get("id")
    }

    thread_public = {k: v for k, v in merged_thread.items() if k != "stable_key"}
    return {
        "thread": {
            "stable_thread_key": stable_key,
            **{k: thread_public.get(k) for k in (
                "first_seen_at",
                "last_seen_at",
                "revisit_count",
                "useful_followup_candidate",
                "follow_up_reason",
                "next_follow_up_hint",
                "useful_revisit_count",
                "ignored_revisit_count",
                "last_useful_at",
                "last_thread_score",
            )},
        },
        "contacts": contact_snapshots,
    }


def sort_participants_for_draft_targeting(
    participants: List[Dict[str, Any]],
    contact_priors: Dict[str, Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """
    Re-order ranked participants to bias drafts toward proven high-value humans (outcome fields).
    """
    if not participants:
        return participants

    def weight(row: Dict[str, Any]) -> float:
        pid = str(row.get("id") or "")
        pri = contact_priors.get(pid, {}) if pid else {}
        sf = int(pri.get("successful_followups") or 0)
        ig = int(pri.get("ignored_followups") or 0)
        uo = int(pri.get("useful_outcome_count") or 0)
        rq = float(pri.get("response_quality") or 0.0)
        base = float(row.get("person_score") or 0.0) * float(row.get("likely_human") or 0.0)
        mult = 1.0 + 0.055 * min(sf, 7) + 0.075 * min(uo, 6) + 0.11 * rq - 0.065 * min(ig, 8)
        return base * max(0.38, mult)

    return sorted(participants, key=lambda r: -weight(r))
