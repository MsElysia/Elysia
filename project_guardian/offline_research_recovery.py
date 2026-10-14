"""Offline, source-linked research recovery using existing Auto-Learning and Issue #95 memory.

Development-only. There is deliberately NO HTTP client, background worker, model,
config/credential lookup, or GuardianCore construction here. The caller supplies
both allowed source URLs and a synchronous controlled-response fetch function.
This module is not an internet-search service or Windows-pilot integration.
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit


class OfflineResearchError(ValueError):
    """Invalid input, unavailable source, or untrustworthy persisted evidence."""


_IDENTITY_KIND = "offline-research-evidence-v1"
_LABEL = re.compile(r"^\s*([A-Za-z][A-Za-z0-9 _-]{2,48})\s*:\s*(.{3,300})\s*$")
_WORDS = re.compile(r"[a-z0-9]{3,}")


def _source_identity(url: str, session_id: str, retrieved_at: str, reliability: str) -> str:
    return json.dumps(
        {"kind": _IDENTITY_KIND, "url": url, "session_id": session_id,
         "retrieved_at": retrieved_at, "declared_reliability": reliability},
        sort_keys=True, separators=(",", ":"),
    )


def _metadata(record: dict) -> dict | None:
    try:
        m = json.loads(record["source_identity"])
    except (KeyError, TypeError, ValueError):
        return None
    if type(m) is not dict or m.get("kind") != _IDENTITY_KIND:
        return None
    if not all(type(m.get(k)) is str and m[k] for k in
               ("url", "session_id", "retrieved_at", "declared_reliability")):
        raise OfflineResearchError("invalid persisted research provenance")
    return m


def _validate_url(url: str) -> None:
    if type(url) is not str or len(url) > 2048 or any(c.isspace() for c in url):
        raise OfflineResearchError("invalid source URL")
    parts = urlsplit(url)
    if (parts.scheme != "https" or not parts.hostname or parts.username or
            parts.password or parts.port not in (None, 443)):
        raise OfflineResearchError("offline research requires explicit HTTPS source URL")
    if parts.hostname.lower() in ("localhost",) or parts.hostname.endswith(".local"):
        raise OfflineResearchError("local-network URL is not a research source")


def _claim_lines(text: str) -> dict[str, set[str]]:
    """Extract *source claims*, not validated facts or instructions."""
    claims: dict[str, set[str]] = {}
    for line in text.splitlines()[:250]:
        match = _LABEL.fullmatch(line)
        if match:
            key = " ".join(match.group(1).lower().split())
            value = " ".join(match.group(2).lower().split())
            claims.setdefault(key, set()).add(value)
    return claims


def _conflicts(items: list[dict]) -> list[dict]:
    values: dict[str, dict[str, set[str]]] = {}
    for item in items:
        for label, options in _claim_lines(item["text"]).items():
            for value in options:
                values.setdefault(label, {}).setdefault(value, set()).add(item["url"])
    return [
        {"claim_label": label, "status": "potential_conflict",
         "alternatives": [{"value": value, "urls": sorted(urls)}
                          for value, urls in sorted(variants.items())]}
        for label, variants in sorted(values.items()) if len(variants) > 1
    ]


def run_offline_research(
    *, subject: str, question: str, sources: list[dict], fetch,
    dest_dir: Path, session_id: str, max_sources: int = 5,
    max_bytes: int = 64000,
) -> dict:
    """Run one bounded controlled-source research session, no implicit networking.

    fetch(url) must return {"raw_bytes": bytes, "text": extracted_plain_text}.
    Only raw exact bytes enter existing persistent memory intelligence. The
    extraction text is used solely for source selection/conflict flagging.
    Every source identity embeds URL, retrieval time and session provenance.
    """
    if not callable(fetch):
        raise OfflineResearchError("explicit controlled fetch function required")
    if not (type(subject) is str and subject.strip() and type(question) is str and
            question.strip() and type(session_id) is str and
            re.fullmatch(r"[A-Za-z0-9_-]{1,80}", session_id)):
        raise OfflineResearchError("subject, question and bounded session_id required")
    if type(max_sources) is not int or not 1 <= max_sources <= 8:
        raise OfflineResearchError("invalid source budget")
    if type(max_bytes) is not int or not 128 <= max_bytes <= 65536:
        raise OfflineResearchError("invalid byte budget")
    if type(sources) is not list:
        raise OfflineResearchError("sources must be an explicit list")
    dest = Path(dest_dir).resolve()
    if not dest.exists() or not dest.is_dir():
        raise OfflineResearchError("explicit existing isolated destination required")

    # Deliberately use the existing legacy relevance helper, not another scorer.
    from project_guardian.auto_learning import _topic_overlap
    from project_guardian.local_ingestion.apply_transaction import ApplyTransaction, destination_lock
    from project_guardian.local_ingestion.memory_intelligence import (
        load_memory_intelligence_records, persist_source_intelligence,
    )
    subject_terms = sorted(set(_WORDS.findall(subject.casefold())))
    if not subject_terms:
        raise OfflineResearchError("subject must contain searchable words")

    plan = []
    for source in sources[:max_sources]:
        if type(source) is not dict:
            raise OfflineResearchError("invalid source descriptor")
        url, reliability = source.get("url"), source.get("reliability", "unassessed")
        _validate_url(url)
        if reliability not in ("high", "medium", "low", "unassessed"):
            raise OfflineResearchError("invalid declared reliability")
        plan.append({"url": url, "declared_reliability": reliability})
    if len({p["url"] for p in plan}) != len(plan):
        raise OfflineResearchError("duplicate planned source URLs")

    report = {"subject": subject, "question": question, "session_id": session_id,
              "status": "controlled_offline_only", "plan": plan,
              "accepted": [], "rejected": [], "unavailable": [], "conflicts": [],
              "steps": 0, "stop_reason": "source_budget_or_exhausted"}
    seen_text: set[str] = set()
    accepted_text: list[dict] = []
    with destination_lock(dest, write=True):
        existing = load_memory_intelligence_records(dest)
        for record in existing:
            if _metadata(record):
                seen_text.add(str(record["source_sha256"]))
        for spec in plan:
            report["steps"] += 1
            url = spec["url"]
            try:
                page = fetch(url)
            except Exception as exc:
                report["unavailable"].append({"url": url, "reason": type(exc).__name__})
                continue
            if type(page) is not dict or type(page.get("raw_bytes")) is not bytes or type(page.get("text")) is not str:
                report["unavailable"].append({"url": url, "reason": "malformed_response"})
                continue
            raw, text = page["raw_bytes"], page["text"]
            if not 1 <= len(raw) <= max_bytes:
                report["unavailable"].append({"url": url, "reason": "source_size_limit"})
                continue
            try:
                if not raw.decode("utf-8").strip():
                    raise UnicodeError("empty source")
            except UnicodeError:
                report["unavailable"].append({"url": url, "reason": "invalid_utf8"})
                continue
            if _topic_overlap(text, subject_terms) < len(subject_terms):
                report["rejected"].append({"url": url, "reason": "irrelevant"})
                continue
            digest = hashlib.sha256(raw).hexdigest()
            if digest in seen_text:
                report["rejected"].append({"url": url, "reason": "duplicate"})
                continue
            when = datetime.now(timezone.utc).isoformat()
            identity = _source_identity(url, session_id, when, spec["declared_reliability"])
            tx = ApplyTransaction(dest)
            try:
                outcome = persist_source_intelligence(
                    dest_dir=dest, raw_bytes=raw, source_identity=identity,
                    canonical_tags=[subject], tag_hints=[question],
                    transaction=tx,
                )
                tx.commit()
            except BaseException:
                tx.abort()
                raise
            seen_text.add(digest)
            report["accepted"].append({"url": url, "source_id": outcome.source_id,
                                       "sha256": digest, "retrieved_at": when,
                                       "declared_reliability": spec["declared_reliability"]})
            accepted_text.append({"url": url, "text": text})
    report["conflicts"] = _conflicts(accepted_text)
    if not report["accepted"]:
        report["stop_reason"] = "no_new_relevant_evidence"
    return report


def recall_offline_research(dest_dir: Path, question: str, *, limit: int = 10) -> dict:
    """Reopen existing evidence via the Issue #95 validated read-only query."""
    if not (type(question) is str and question.strip() and
            type(limit) is int and 1 <= limit <= 20):
        raise OfflineResearchError("invalid recall query")
    from project_guardian.local_ingestion.memory_intelligence import (
        expand_persisted_highlight, load_memory_intelligence_records,
        query_memory_intelligence,
    )
    records = load_memory_intelligence_records(dest_dir)
    linked = {rec["source_id"]: (meta, rec)
              for rec in records if (meta := _metadata(rec))}
    hits = query_memory_intelligence(dest_dir, question, limit=100, validate_summaries=True)
    results = []
    observed = []
    seen_sources = set()
    for hit in hits:
        info = linked.get(hit["source_id"])
        if not info:
            continue
        meta, record = info
        if hit["source_id"] not in seen_sources and hit["highlights"]:
            original = expand_persisted_highlight(dest_dir, hit["highlights"][0]["highlight_id"])
            observed.append({"url": meta["url"], "text": original["raw_source"]})
            seen_sources.add(hit["source_id"])
        results.append({
            "source_id": hit["source_id"], "url": meta["url"],
            "retrieved_at": meta["retrieved_at"],
            "declared_reliability": meta["declared_reliability"],
            "source_sha256": record["source_sha256"],
            "summary": hit["summary"], "recall_reasons": hit["recall_reasons"],
            "highlight_ids": [x["highlight_id"] for x in hit["highlights"]],
            "status": "source_evidence_not_verified_fact",
        })
        if len(results) == limit:
            break
    return {"status": "source_evidence" if results else "unavailable",
            "results": results, "conflicts": _conflicts(observed)}
