# Moltbook-first bounded social session: observe, artifact memory, drafts, gated speak.

from __future__ import annotations

import json
import logging
import re
import time
import urllib.parse
from collections import Counter
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .continuity import (
    apply_operator_continuity_notes,
    load_continuity,
    persist_session_continuity,
    stable_thread_key,
)
from .filters import filter_text_chunks, split_findings_into_chunks, sponsored_risk_score
from .memory import append_jsonl, ensure_social_data_dir
from .ranking import (
    build_participant_rows,
    build_rank_context_for_draft,
    extract_handles_from_urls,
    extract_speaker_names,
    handle_from_moltbook_url,
    load_campaign_corpus_text,
    recurrence_counts_for_handles,
    score_thread_quality,
)

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = PROJECT_ROOT / "config" / "social_intelligence.json"

_STOPWORDS = frozenset(
    """
    the and for that this with from have were was are not but what all can has had
    their one our out day get use her she him his how its may new now see two way who
    boy did its let put say too any use very when your about into than then them these
    some such will just like over also back only know take year good make well work
    """.split()
)


def _load_json(path: Path) -> Optional[Dict[str, Any]]:
    if not path.exists():
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.warning("social_intelligence: could not load %s: %s", path, e)
        return None


def load_social_config() -> Dict[str, Any]:
    loaded = _load_json(CONFIG_PATH) or {}
    defaults: Dict[str, Any] = {
        "version": 1,
        "environments": {
            "moltbook": {
                "modes": {"observe": True, "draft": True, "speak": False},
            }
        },
        "default_environment": "moltbook",
        "sponsored_risk_threshold": 0.42,
        "speak": {
            "enabled": False,
            "max_posts_per_hour": 2,
            "allowlisted_host_suffixes": ["moltbook.com"],
            "queue_outbound_to_disk": True,
        },
        "campaign_ids": {
            "observe": ["cmp_social_intel", "cmp_learning_loop"],
            "draft": ["cmp_social_intel"],
            "speak": ["cmp_social_intel"],
        },
        "memory": {
            "max_thread_lines": 400,
            "max_profile_lines": 250,
            "max_draft_lines": 200,
            "max_rankings_lines": 500,
        },
        "human_ranking": {
            "low_person_score_skip_threshold": 0.24,
            "low_likely_human_skip_threshold": 0.34,
            "high_value_followup_thread_floor": 0.45,
            "high_value_followup_person_floor": 0.58,
            "high_value_followup_human_floor": 0.55,
        },
        "continuity": {
            "stale_days": 21,
            "max_contacts": 400,
            "max_threads": 250,
            "low_yield_score_threshold": 0.28,
            "low_yield_human_threshold": 0.35,
            "low_yield_streak_for_dead_end": 3,
            "followup_mix_floor": 0.38,
        },
    }
    out = {**defaults, **{k: v for k, v in loaded.items() if k != "environments"}}
    envs = dict(defaults.get("environments") or {})
    if isinstance(loaded.get("environments"), dict):
        for k, v in loaded["environments"].items():
            if isinstance(v, dict):
                envs[k] = {**envs.get(k, {}), **v}
    out["environments"] = envs
    for key in ("speak", "memory", "campaign_ids", "human_ranking", "continuity"):
        if isinstance(loaded.get(key), dict) and isinstance(out.get(key), dict):
            out[key] = {**out[key], **loaded[key]}
    return out


def _env_modes(cfg: Dict[str, Any], environment: str) -> Dict[str, bool]:
    env = (cfg.get("environments") or {}).get(environment) or {}
    m = env.get("modes") or {}
    return {
        "observe": bool(m.get("observe", True)),
        "draft": bool(m.get("draft", True)),
        "speak": bool(m.get("speak", False)),
    }


def _recurring_topics(texts: List[str], *, top_n: int = 12) -> List[str]:
    c: Counter[str] = Counter()
    for t in texts:
        for w in re.findall(r"[a-zA-Z][a-zA-Z\-]{2,}", (t or "").lower()):
            if w in _STOPWORDS or len(w) < 4:
                continue
            c[w] += 1
    return [w for w, _ in c.most_common(top_n)]


def _profile_heuristic_urls(urls: List[str]) -> List[Dict[str, Any]]:
    """Light URL shape hints for profile-like pages (no DOM — bounded stack)."""
    out: List[Dict[str, Any]] = []
    for u in urls:
        low = (u or "").lower()
        if not low or "moltbook" not in low:
            continue
        score = 0.35
        reasons: List[str] = []
        if re.search(r"/@[\w\-]+", low) or "/user/" in low or "/users/" in low or "/profile" in low:
            score += 0.35
            reasons.append("path_profile_shape")
        path = urllib.parse.urlparse(low).path or ""
        depth = path.count("/")
        if 2 <= depth <= 5 and len(path) > 3:
            score += 0.1
            reasons.append("mid_depth_path")
        score = min(1.0, score)
        if score >= 0.5:
            out.append({"url": u[:500], "trust_hint": round(score, 3), "signals": reasons})
    return out[:20]


def _trust_from_steps(filtered_chunks: List[str], step_scores: List[float]) -> float:
    if not filtered_chunks and not step_scores:
        return 0.4
    avg_rel = sum(step_scores) / max(1, len(step_scores))
    # lower sponsored residue in kept text → bump trust slightly
    if filtered_chunks:
        risks = [sponsored_risk_score(c) for c in filtered_chunks[:30]]
        clean = 1.0 - (sum(risks) / max(1, len(risks)))
    else:
        clean = 0.5
    return round(min(1.0, max(0.15, 0.35 * clean + 0.45 * min(1.0, avg_rel + 0.2))), 3)


def _draft_with_optional_llm(
    guardian: Any,
    *,
    summary: str,
    topics: List[str],
    goal: str,
    rank_context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    rc = rank_context or {}
    primary = (rc.get("primary_contact") or {}).get("display") or ""
    prioritize = [str(x) for x in (rc.get("prioritize_displays") or []) if x][:5]
    pri_line = (
        "Prioritize thoughtful replies toward: " + ", ".join(prioritize) + ".\n"
        if prioritize
        else ""
    )
    deprio = rc.get("deprioritize_note")
    if deprio:
        pri_line += f"Selection note: {deprio}.\n"
    ts = rc.get("thread_score")
    if ts is not None:
        pri_line += f"Thread quality score (heuristic): {ts}.\n"
    hints = rc.get("continuity_hints")
    if hints:
        pri_line += "Continuity (pre-session): " + "; ".join(str(h) for h in hints) + ".\n"

    user_summary = (
        f"Goal: {goal[:400]}\n\n{pri_line}"
        f"Topics spotted: {', '.join(topics[:10])}\n\nDiscussion notes:\n{summary[:3500]}"
    )
    if primary:
        reply = (
            f"Hi {primary} — thanks for the concrete detail in the thread. "
            "If you had to pick one next experiment with the smallest time cost, what would it be?"
        )
        outreach = (
            f"Hi {primary} — I appreciated your angle on {topics[0] if topics else 'this thread'}. "
            "Would you be open to one specific question about how you validated the approach?"
        )
    else:
        reply = (
            "Thanks for sharing this — I'm trying to understand the main constraint you're solving. "
            "Could you say more about what you've already tried?"
        )
        outreach = (
            "Hi — I came across your thread on "
            + (topics[0] if topics else "this topic")
            + " and would value your perspective on one narrow question if you have a moment."
        )
    questions = [
        "What would a successful outcome look like for you here?",
        "Is there a specific part of the thread you want reactions on?",
        "Who else in this community should be looped in?",
    ]
    llm_fn = getattr(guardian, "_llm_completion", None) if guardian is not None else None
    if callable(llm_fn):
        try:
            prompt = (
                "You help draft bounded, non-spammy forum replies. "
                "Prefer addressing higher-value human participants first; avoid promo or bot-like voices. "
                "Given the notes below, output JSON with keys: reply_draft, outreach_draft, "
                "follow_up_questions (array of 3 short strings), user_summary (one paragraph). "
                "No selling, no affiliate tone, no urgency tricks.\n\n"
                + user_summary[:6000]
            )
            raw = llm_fn([{"role": "user", "content": prompt}], max_tokens=500)
            text = raw if isinstance(raw, str) else str(raw)
            m = re.search(r"\{[\s\S]*\}", text)
            if m:
                data = json.loads(m.group())
                return {
                    "reply_drafts": [str(data.get("reply_draft") or reply)[:1200]],
                    "outreach_drafts": [str(data.get("outreach_draft") or outreach)[:1200]],
                    "follow_up_questions": list(data.get("follow_up_questions") or questions)[:5],
                    "user_summary": str(data.get("user_summary") or user_summary[:800])[:2000],
                    "source": "llm",
                }
        except Exception as e:
            logger.debug("social_intelligence llm draft fallback: %s", e)
    return {
        "reply_drafts": [reply],
        "outreach_drafts": [outreach],
        "follow_up_questions": questions,
        "user_summary": user_summary[:2000],
        "source": "template",
    }


def _record_campaigns(cfg: Dict[str, Any], phase: str, note: str) -> None:
    ids = list((cfg.get("campaign_ids") or {}).get(phase) or [])
    if not ids:
        return
    try:
        from ..mission_autonomy import MissionAutonomyStore

        store = MissionAutonomyStore()
        if not store.enabled:
            return
        for cid in ids:
            store.record_campaign_progress(cid, note[:400], advance=True)
    except Exception as e:
        logger.debug("social_intelligence campaign hook: %s", e)


def _speak_rate_path() -> Path:
    return ensure_social_data_dir() / "speak_rate_state.json"


def _check_speak_rate(max_per_hour: int) -> Tuple[bool, str]:
    if max_per_hour <= 0:
        return False, "max_posts_per_hour_zero"
    p = _speak_rate_path()
    bucket = time.strftime("%Y-%m-%dT%H", time.gmtime())
    data: Dict[str, Any] = {"bucket": bucket, "count": 0}
    if p.exists():
        try:
            data = {**data, **json.loads(p.read_text(encoding="utf-8"))}
        except Exception:
            pass
    if data.get("bucket") != bucket:
        data = {"bucket": bucket, "count": 0}
    if int(data.get("count") or 0) >= max_per_hour:
        return False, "rate_limited"
    return True, "ok"


def _increment_speak_rate() -> None:
    p = _speak_rate_path()
    bucket = time.strftime("%Y-%m-%dT%H", time.gmtime())
    data: Dict[str, Any] = {"bucket": bucket, "count": 0}
    if p.exists():
        try:
            data = {**data, **json.loads(p.read_text(encoding="utf-8"))}
        except Exception:
            pass
    if data.get("bucket") != bucket:
        data = {"bucket": bucket, "count": 0}
    data["count"] = int(data.get("count") or 0) + 1
    p.write_text(json.dumps(data), encoding="utf-8")


def _host_allowed(url: str, suffixes: List[str]) -> bool:
    try:
        host = (urllib.parse.urlparse(url).hostname or "").lower()
    except Exception:
        return False
    return any(host == s or host.endswith("." + s) for s in suffixes)


def run_moltbook_social_session(
    guardian: Optional[Any],
    payload: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Observe Moltbook via existing bounded browse, filter sponsored chunks, save artifacts, optional drafts.
    Never posts unless speak is explicitly enabled (separate attempt_social_speak).
    """
    p = dict(payload or {})
    cfg = load_social_config()
    environment = str(p.get("environment") or cfg.get("default_environment") or "moltbook").strip()
    if environment != "moltbook":
        return {"success": False, "error": "only_moltbook_supported_in_this_pass", "result": {}}

    modes = _env_modes(cfg, environment)
    if isinstance(p.get("modes"), dict):
        for k, v in p["modes"].items():
            if k in modes:
                modes[k] = bool(v)
    threshold = float(p.get("sponsored_risk_threshold") or cfg.get("sponsored_risk_threshold") or 0.42)
    mem = cfg.get("memory") or {}

    goal = str(p.get("goal") or p.get("task") or p.get("query") or "").strip()
    if not goal:
        return {"success": False, "error": "missing_goal", "result": {}}

    if not modes.get("observe"):
        logger.info("social_observe_summary skipped observe_mode_disabled env=%s", environment)
        return {"success": True, "result": {"skipped": True, "reason": "observe_disabled"}}

    from ..bounded_browser.moltbook import MOLTBOOK_DEFAULT_START_URL, browse_moltbook

    start_url = str(p.get("start_url") or p.get("url") or MOLTBOOK_DEFAULT_START_URL).strip()
    memory_core = getattr(guardian, "memory", None) if guardian is not None else None

    try:
        browse_result = browse_moltbook(goal, start_url=start_url, memory_core=memory_core)
    except RuntimeError as e:
        return {"success": False, "error": "playwright_unavailable", "result": {"detail": str(e)[:500]}}
    except ValueError as e:
        return {"success": False, "error": str(e), "result": {}}

    mem_lines = {
        "thread": int(mem.get("max_thread_lines") or 400),
        "profile": int(mem.get("max_profile_lines") or 250),
        "draft": int(mem.get("max_draft_lines") or 200),
        "rankings": int(mem.get("max_rankings_lines") or 500),
    }

    all_chunks: List[str] = []
    step_scores: List[float] = []
    sponsored_skipped = 0
    total_raw_chunks = 0
    for step in browse_result.steps:
        step_scores.append(float(getattr(step, "relevance_score", 0.0) or 0.0))
        chunks = split_findings_into_chunks(step.key_findings or "")
        total_raw_chunks += len(chunks)
        kept, skip = filter_text_chunks(chunks, threshold=threshold)
        sponsored_skipped += skip
        all_chunks.extend(kept)

    if sponsored_skipped:
        logger.info(
            "sponsored_content_skipped chunks=%s threshold=%.2f",
            sponsored_skipped,
            threshold,
        )

    topics = _recurring_topics(all_chunks)
    summary_text = "\n\n".join(all_chunks[:24])[:8000]
    trust = _trust_from_steps(all_chunks, step_scores)
    relevance = round(min(1.0, sum(step_scores) / max(1, len(step_scores))), 3) if step_scores else 0.4

    hr_cfg = cfg.get("human_ranking") or {}
    low_ps = float(hr_cfg.get("low_person_score_skip_threshold") or 0.24)
    low_lh = float(hr_cfg.get("low_likely_human_skip_threshold") or 0.34)
    hi_tf = float(hr_cfg.get("high_value_followup_thread_floor") or 0.45)
    hi_pf = float(hr_cfg.get("high_value_followup_person_floor") or 0.58)
    hi_hf = float(hr_cfg.get("high_value_followup_human_floor") or 0.55)
    cont_cfg = cfg.get("continuity") or {}

    stable_key = stable_thread_key(list(browse_result.visited_urls), goal)
    state = load_continuity()
    apply_operator_continuity_notes(state, p.get("continuity_notes"))
    contact_priors_start = deepcopy(state.get("contacts", {}))
    thread_prior_raw = state.get("threads", {}).get(stable_key)
    thread_prior = dict(thread_prior_raw) if thread_prior_raw else None

    campaign_corpus = load_campaign_corpus_text()
    recurrence = recurrence_counts_for_handles()
    for u in browse_result.visited_urls:
        h = handle_from_moltbook_url(str(u))
        if h:
            recurrence[h] = recurrence.get(h, 0) + 1

    ranked_people = build_participant_rows(
        urls=list(browse_result.visited_urls),
        chunks=all_chunks,
        recurrence=recurrence,
        campaign_corpus=campaign_corpus,
        goal=goal,
        contact_priors=contact_priors_start,
        continuity_cfg=cont_cfg,
        now_ts=time.time(),
    )
    handles_now = extract_handles_from_urls(list(browse_result.visited_urls))
    names_now = extract_speaker_names(summary_text)
    participant_hint = max(
        len(ranked_people),
        len(handles_now),
        len(names_now),
        1 if all_chunks else 0,
    )

    thread_id = f"thr_{int(time.time())}_{hash(summary_text) & 0xFFFF:x}"

    thread_rank = score_thread_quality(
        all_chunks=all_chunks,
        step_scores=step_scores,
        topics=topics,
        goal=goal,
        sponsored_skipped=sponsored_skipped,
        total_raw_chunks=total_raw_chunks,
        participant_count=participant_hint,
        campaign_corpus=campaign_corpus,
        thread_prior=thread_prior,
    )
    thread_score = float(thread_rank["thread_score"])

    for person_row in ranked_people:
        logger.info(
            "social_person_ranked id=%s person_score=%.3f thread=%.3f",
            str(person_row.get("id"))[:48],
            float(person_row.get("person_score") or 0.0),
            thread_score,
        )
        logger.info(
            "likely_human_scored id=%s confidence=%.3f",
            str(person_row.get("id"))[:48],
            float(person_row.get("likely_human") or 0.0),
        )
        ps = float(person_row.get("person_score") or 0.0)
        lh = float(person_row.get("likely_human") or 0.0)
        if ps < low_ps and lh < low_lh:
            logger.info(
                "low_signal_profile_skipped id=%s person_score=%.3f likely_human=%.3f",
                str(person_row.get("id"))[:48],
                ps,
                lh,
            )
        if (
            thread_score >= hi_tf
            and ps >= hi_pf
            and lh >= hi_hf
        ):
            logger.info(
                "high_value_followup_candidate id=%s person_score=%.3f likely_human=%.3f thread_score=%.3f",
                str(person_row.get("id"))[:48],
                ps,
                lh,
                thread_score,
            )

    why = (
        "Ranked for human-like discussion signals vs promo/bot heuristics; aligned with mission campaign text overlap."
    )
    suggested_next = str(
        thread_rank.get("suggested_next_interaction")
        or "Review drafts with operator; prioritize highest-ranked humans over promo-like voices."
    )

    prioritize_ids = [str(x.get("id") or "") for x in ranked_people[:3] if x.get("id")]
    continuity_snap = persist_session_continuity(
        state=state,
        stable_key=stable_key,
        thread_id=thread_id,
        ranked_people=ranked_people,
        thread_rank=dict(thread_rank),
        modes=modes,
        now_ts=time.time(),
        cfg=cont_cfg,
        human_ranking_cfg=hr_cfg,
        prioritize_ids=prioritize_ids,
    )
    th_cont = continuity_snap.get("thread") or {}
    if th_cont.get("next_follow_up_hint"):
        suggested_next = str(th_cont.get("next_follow_up_hint"))[:600]

    logger.info(
        "social_thread_ranked thread_id=%s score=%.3f mix=%.3f reasons=%s",
        thread_id,
        thread_score,
        float(thread_rank.get("likely_discussion_human_mix") or 0.0),
        thread_rank.get("thread_rank_reasons"),
    )

    contact_snap = continuity_snap.get("contacts") or {}
    ranking_record = {
        "ts": time.time(),
        "kind": "session_ranks",
        "thread_id": thread_id,
        "environment": environment,
        "thread_score": thread_score,
        "likely_discussion_human_mix": thread_rank.get("likely_discussion_human_mix"),
        "thread_rank_reasons": thread_rank.get("thread_rank_reasons"),
        "suggested_next_interaction": thread_rank.get("suggested_next_interaction"),
        "continuity": continuity_snap,
        "participants": [
            {
                "id": x.get("id"),
                "display": x.get("display"),
                "person_score": x.get("person_score"),
                "likely_human": x.get("likely_human"),
                "relevance_reasons": x.get("relevance_reasons"),
                "suggested_next_interaction": x.get("suggested_next_interaction"),
                "continuity": contact_snap.get(str(x.get("id") or "")),
            }
            for x in ranked_people
        ],
    }
    append_jsonl("rankings.jsonl", ranking_record, max_lines=mem_lines["rankings"])

    rank_context = build_rank_context_for_draft(
        thread_rank=thread_rank,
        participants=ranked_people,
        contact_priors=contact_priors_start,
    )

    enriched_ranked = []
    for x in ranked_people[:12]:
        cid = str(x.get("id") or "")
        enriched_ranked.append({**x, "continuity": contact_snap.get(cid)})

    thread_record = {
        "ts": time.time(),
        "kind": "thread",
        "id": thread_id,
        "environment": environment,
        "goal": goal[:500],
        "visited_urls": list(browse_result.visited_urls)[:40],
        "topics_recurring": topics,
        "trust_score": trust,
        "relevance_score": relevance,
        "thread_score": thread_score,
        "likely_discussion_human_mix": thread_rank.get("likely_discussion_human_mix"),
        "thread_rank_reasons": thread_rank.get("thread_rank_reasons"),
        "participant_count_hint": participant_hint,
        "ranked_participants": enriched_ranked,
        "continuity": th_cont,
        "summary": summary_text[:6000],
        "why_matters": why,
        "suggested_next_interaction": suggested_next,
        "sponsored_chunks_skipped": sponsored_skipped,
        "stop_reason": browse_result.stop_reason,
    }
    append_jsonl("threads.jsonl", thread_record, max_lines=mem_lines["thread"])
    logger.info(
        "social_thread_saved id=%s pages=%s skipped_sponsored=%s topics=%s",
        thread_id,
        len(browse_result.steps),
        sponsored_skipped,
        topics[:5],
    )
    logger.info(
        "social_observe_summary env=%s pages=%s urls=%s topics=%s trust=%.2f rel=%.2f",
        environment,
        len(browse_result.steps),
        len(browse_result.visited_urls),
        topics[:8],
        trust,
        relevance,
    )

    profiles = _profile_heuristic_urls(list(browse_result.visited_urls))
    for pr in profiles:
        ph = handle_from_moltbook_url(str(pr.get("url") or ""))
        rank_match = next((x for x in ranked_people if x.get("id") == ph), None) if ph else None
        pr_rec = {
            "ts": time.time(),
            "kind": "profile_hint",
            "environment": environment,
            "thread_id": thread_id,
            **pr,
            "relevance_score": relevance,
            "thread_score": thread_score,
            "why_matters": "Profile-shaped URL for recurring-participant tracking.",
            "suggested_next_interaction": "Open read-only later to refine summary when operator approves.",
        }
        if rank_match:
            pr_rec["person_score"] = rank_match.get("person_score")
            pr_rec["likely_human"] = rank_match.get("likely_human")
            pr_rec["relevance_reasons"] = rank_match.get("relevance_reasons")
            pr_rec["suggested_next_interaction"] = rank_match.get("suggested_next_interaction")
        if ph and contact_snap.get(ph):
            pr_rec["continuity"] = contact_snap.get(ph)
        append_jsonl("profiles.jsonl", pr_rec, max_lines=mem_lines["profile"])
        logger.info(
            "social_profile_scored url=%s trust_hint=%s",
            (pr.get("url") or "")[:120],
            pr.get("trust_hint"),
        )

    drafts: Optional[Dict[str, Any]] = None
    if modes.get("draft"):
        drafts = _draft_with_optional_llm(
            guardian,
            summary=summary_text,
            topics=topics,
            goal=goal,
            rank_context=rank_context,
        )
        draft_pack = {
            "ts": time.time(),
            "kind": "draft_pack",
            "thread_id": thread_id,
            "environment": environment,
            "drafts": drafts,
            "rank_context": rank_context,
            "auto_post": False,
        }
        append_jsonl("drafts.jsonl", draft_pack, max_lines=mem_lines["draft"])
        logger.info(
            "social_reply_drafted thread_id=%s source=%s",
            thread_id,
            (drafts or {}).get("source"),
        )
        _record_campaigns(cfg, "draft", f"social draft_pack for {thread_id}")

    _record_campaigns(cfg, "observe", f"social observe {thread_id} pages={len(browse_result.steps)}")

    result: Dict[str, Any] = {
        "environment": environment,
        "modes_used": modes,
        "thread_id": thread_id,
        "summary": summary_text[:4000],
        "topics_recurring": topics,
        "trust_score": trust,
        "relevance_score": relevance,
        "thread_score": thread_score,
        "likely_discussion_human_mix": thread_rank.get("likely_discussion_human_mix"),
        "thread_rank_reasons": thread_rank.get("thread_rank_reasons"),
        "ranked_participants": enriched_ranked,
        "rank_context": rank_context,
        "continuity": continuity_snap,
        "why_matters": why,
        "suggested_next_interaction": suggested_next,
        "sponsored_chunks_skipped": sponsored_skipped,
        "visited_urls": list(browse_result.visited_urls)[:30],
        "profile_hints": profiles[:10],
        "drafts": drafts,
        "pages_visited": len(browse_result.steps),
        "stop_reason": browse_result.stop_reason,
    }
    return {"success": True, "result": result}


def attempt_social_speak(
    guardian: Optional[Any],
    payload: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Gated outbound path: default blocked. When enabled, queues text and applies rate limits + allowlist.
    Does not drive login or post via browser in this pass.
    """
    _ = guardian
    p = dict(payload or {})
    cfg = load_social_config()
    speak_cfg = cfg.get("speak") or {}
    env_modes = _env_modes(cfg, str(p.get("environment") or cfg.get("default_environment") or "moltbook"))
    global_speak = bool(speak_cfg.get("enabled"))
    text = str(p.get("text") or p.get("body") or "").strip()
    kind = str(p.get("kind") or "reply")[:40]
    target_url = str(p.get("target_url") or p.get("url") or "").strip()

    if not env_modes.get("speak") and not p.get("force_speak"):
        logger.info("social_post_blocked reason=mode_speak_disabled")
        return {"success": False, "error": "speak_mode_disabled", "blocked": True}
    if not global_speak and not p.get("force_speak"):
        logger.info("social_post_blocked reason=config_speak_disabled")
        return {"success": False, "error": "speak_disabled_in_config", "blocked": True}
    if not text:
        logger.info("social_post_blocked reason=empty_body")
        return {"success": False, "error": "missing_text", "blocked": True}

    suffixes = list(speak_cfg.get("allowlisted_host_suffixes") or ["moltbook.com"])
    if target_url and not _host_allowed(target_url, suffixes):
        logger.info("social_post_blocked reason=host_not_allowlisted url=%s", target_url[:120])
        return {"success": False, "error": "target_not_allowlisted", "blocked": True}

    max_ph = int(speak_cfg.get("max_posts_per_hour") or 2)
    ok, rsn = _check_speak_rate(max_ph)
    if not ok:
        logger.info("social_post_blocked reason=%s", rsn)
        return {"success": False, "error": rsn, "blocked": True}

    if speak_cfg.get("queue_outbound_to_disk", True):
        rec = {
            "ts": time.time(),
            "kind": kind,
            "text": text[:8000],
            "target_url": target_url[:800],
            "environment": p.get("environment") or cfg.get("default_environment"),
            "status": "queued",
            "note": "operator_approval_required_no_auto_post",
        }
        append_jsonl("outbound_queue.jsonl", rec, max_lines=500)
        _increment_speak_rate()
        logger.info(
            "social_outbound_queued kind=%s chars=%s (full text in data/social_intelligence/outbound_queue.jsonl)",
            kind,
            len(text),
        )
        _record_campaigns(cfg, "speak", f"queued outbound {kind}")
        return {"success": True, "queued": True, "result": rec}

    _increment_speak_rate()
    return {"success": True, "queued": False, "result": {"text": text[:500]}}


def run_social_intel_for_capability(
    guardian: Any,
    payload: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Builtin tool entry: same as run_moltbook_social_session (+ optional speak sub-action)."""
    p = dict(payload or {})
    action = str(p.get("action") or "observe").strip().lower()
    if action in ("speak", "post", "queue_outbound"):
        return attempt_social_speak(guardian, p)
    return run_moltbook_social_session(guardian, p)
