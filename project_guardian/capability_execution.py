# project_guardian/capability_execution.py
# Callable capability execution bridge: tools, modules, and chat/autonomy hooks.

from __future__ import annotations

import json
import logging
import re
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

_SAFE_FETCH_MAX_BYTES = 200_000
_SAFE_FETCH_TEXT_PREVIEW = 24_000


def _first_http_url_from_payload(payload: Dict[str, Any]) -> str:
    """Extract the first http(s) URL from common capability payload fields."""
    for key in ("url", "href", "link"):
        value = str(payload.get(key) or "").strip()
        if value.startswith(("http://", "https://")):
            return value
    haystack = " ".join(
        str(payload.get(key) or "")
        for key in ("task", "objective", "query", "prompt", "text")
    )
    match = re.search(r"https?://[^\s<>'\")]+", haystack)
    return match.group(0).rstrip(".,;") if match else ""


def _safe_builtin_web_fetch(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Small read-only HTTP fetch for the builtin web tool."""
    url = _first_http_url_from_payload(payload)
    if not url:
        return {
            "success": False,
            "error": "elysia_builtin_web requires an http(s) URL in url/objective/query/task/prompt",
        }
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        return {"success": False, "error": f"Refusing non-http(s) URL: {url[:120]}"}

    timeout = max(1.0, min(float(payload.get("timeout_sec", 12.0) or 12.0), 30.0))
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "ProjectGuardian-ElysiaBuiltinWeb/1.0",
            "Accept": "text/html,application/json,text/plain;q=0.9,*/*;q=0.5",
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read(_SAFE_FETCH_MAX_BYTES + 1)
            truncated = len(raw) > _SAFE_FETCH_MAX_BYTES
            raw = raw[:_SAFE_FETCH_MAX_BYTES]
            content_type = str(resp.headers.get("Content-Type") or "")
            text = raw.decode("utf-8", errors="replace")
            return {
                "success": True,
                "data": {
                    "url": url,
                    "status_code": getattr(resp, "status", 200),
                    "content_type": content_type,
                    "text": text[:_SAFE_FETCH_TEXT_PREVIEW],
                    "bytes_read": len(raw),
                    "truncated": truncated or len(text) > _SAFE_FETCH_TEXT_PREVIEW,
                },
            }
    except urllib.error.HTTPError as e:
        return {
            "success": False,
            "error": f"HTTP {getattr(e, 'code', '?')} while fetching {url}",
            "status_code": getattr(e, "code", None),
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def _task_router_gate_payload(payload: Dict[str, Any], structured_task: Dict[str, Any]) -> Dict[str, Any]:
    gate_payload = dict(payload)
    gate_payload.update(structured_task)
    nested = structured_task.get("payload")
    if isinstance(nested, dict):
        gate_payload.update(nested)
    return gate_payload


def _task_router_route_metadata_gate(route: Dict[str, Any], payload: Dict[str, Any]) -> Tuple[bool, str]:
    routed_to = str(route.get("routed_to") or "").strip().lower()
    score = route.get("score")
    if not routed_to or score is None:
        return False, "missing_route_or_score"

    if "available_tools" in route:
        try:
            if int(route.get("available_tools") or 0) <= 0:
                return False, "no_strict_capability_match"
        except (TypeError, ValueError):
            return False, "bad_available_tools"

    if routed_to == "elysia_builtin_web" and not _first_http_url_from_payload(payload):
        return False, "web_route_missing_url"
    if routed_to == "elysia_builtin_exec":
        return False, "exec_route_requires_explicit_execution"

    return True, "route_metadata"


def _artifact_search_roots(guardian: Any) -> List[Path]:
    roots: List[Path] = []
    ui_roots = getattr(guardian, "ui_data_roots", None)
    if isinstance(ui_roots, (list, tuple)):
        for root in ui_roots:
            try:
                path = Path(root)
            except Exception:
                continue
            if path not in roots:
                roots.append(path)
    repo_root = Path(__file__).resolve().parent.parent
    if repo_root not in roots:
        roots.append(repo_root)
    return roots


def _iter_operator_artifact_entries(guardian: Any) -> List[Dict[str, Any]]:
    entries: List[Dict[str, Any]] = []
    seen_paths = set()
    contract_defaults = {
        "generated_reports": None,
        "revenue_briefs": "revenue_shortlist",
        "research_briefs": "research_brief",
    }
    for root in _artifact_search_roots(guardian):
        for folder_name, default_contract in contract_defaults.items():
            for folder in (root / folder_name, root / "data" / folder_name):
                if not folder.is_dir():
                    continue
                for fp in sorted(folder.glob("*.json"), key=lambda x: x.stat().st_mtime, reverse=True):
                    sp = str(fp.resolve())
                    if sp in seen_paths:
                        continue
                    seen_paths.add(sp)
                    try:
                        with open(fp, "r", encoding="utf-8") as f:
                            blob = json.load(f)
                    except Exception:
                        continue
                    if not isinstance(blob, dict):
                        continue
                    payload = blob.get("payload")
                    entries.append(
                        {
                            "path": sp,
                            "file_name": fp.name,
                            "contract_id": blob.get("contract_id") or default_contract,
                            "payload": payload if isinstance(payload, dict) else {},
                            "blob": blob,
                            "mtime": fp.stat().st_mtime,
                        }
                    )
    entries.sort(key=lambda item: float(item.get("mtime") or 0.0), reverse=True)
    return entries


def _select_offer_pack_revenue_payload(artifacts: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    best_score = float("-inf")
    best_payload: Optional[Dict[str, Any]] = None
    best_opp: Optional[Dict[str, Any]] = None
    fallback: Optional[Dict[str, Any]] = None
    for item in artifacts:
        if item.get("contract_id") != "revenue_shortlist":
            continue
        payload = item.get("payload")
        if not isinstance(payload, dict):
            continue
        if fallback is None:
            fallback = payload
        opportunities = payload.get("opportunities")
        if not isinstance(opportunities, list):
            continue
        for opp in opportunities:
            if not isinstance(opp, dict):
                continue
            title = str(opp.get("title") or "").strip()
            title_l = title.lower()
            score = 0.0
            if title and not title_l.startswith("revenue angle:"):
                score += 4.0
            if "system optimization" not in title_l:
                score += 1.0
            if any(token in title_l for token in ("audit", "brief", "service", "sprint", "offer", "dashboard")):
                score += 2.0
            expected = str(opp.get("expected_value") or "").strip().lower()
            if expected == "high":
                score += 2.0
            elif expected == "medium":
                score += 1.0
            difficulty = str(opp.get("difficulty") or "").strip().lower()
            if difficulty == "low":
                score += 1.5
            elif difficulty == "medium":
                score += 1.0
            if score > best_score:
                best_score = score
                best_opp = dict(opp)
                best_payload = payload
    if best_opp is not None:
        base = dict(best_payload or {})
        base["opportunities"] = [best_opp]
        return base
    return fallback


def _expected_value_score(value: Any) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value or "").strip().lower()
    if not text:
        return 0.0
    label_scores = {
        "critical": 5.0,
        "very high": 4.5,
        "high": 4.0,
        "medium-high": 3.25,
        "medium": 2.5,
        "visibility": 2.0,
        "low-medium": 1.75,
        "low": 1.0,
        "uncertain": 0.75,
    }
    if text in label_scores:
        return label_scores[text]
    money = re.search(r"\$?\s*([0-9]+(?:\.[0-9]+)?)\s*([kKmM])?", text)
    if money:
        amount = float(money.group(1))
        suffix = (money.group(2) or "").lower()
        if suffix == "k":
            amount *= 1000
        elif suffix == "m":
            amount *= 1_000_000
        if amount >= 1000:
            return 5.0
        if amount >= 250:
            return 4.0
        if amount >= 50:
            return 3.0
        return 1.5
    for label, score in label_scores.items():
        if label in text:
            return score
    return 1.0


def _difficulty_score(value: Any) -> float:
    text = str(value or "").strip().lower()
    if text in ("trivial", "very low"):
        return 2.0
    if text == "low":
        return 1.5
    if text == "medium":
        return 0.8
    if text in ("high", "hard"):
        return -0.6
    if text in ("very high", "blocked"):
        return -1.2
    return 0.0


def _score_revenue_opportunity(opp: Dict[str, Any], mtime: float = 0.0) -> float:
    title = str(opp.get("title") or "").strip().lower()
    capability = str(opp.get("required_capability") or "").strip().lower()
    score = _expected_value_score(opp.get("expected_value")) * 10.0
    score += _difficulty_score(opp.get("difficulty")) * 2.0
    if capability and capability not in ("none", "unknown", "tbd"):
        score += 1.25
    if any(token in title for token in ("offer", "buyer", "service", "sprint", "brief", "dashboard", "audit")):
        score += 1.0
    if title.startswith("revenue angle:"):
        score -= 1.0
    if mtime:
        score += min(1.0, max(0.0, mtime / 4_000_000_000.0))
    return round(score, 4)


def _rank_revenue_opportunities(
    artifacts: List[Dict[str, Any]],
    *,
    limit: int = 12,
) -> Tuple[List[Dict[str, Any]], str]:
    ranked: List[Tuple[float, float, int, Dict[str, Any]]] = []
    for item in artifacts:
        if item.get("contract_id") != "revenue_shortlist":
            continue
        payload = item.get("payload")
        if not isinstance(payload, dict):
            continue
        opportunities = payload.get("opportunities")
        if not isinstance(opportunities, list):
            continue
        mtime = float(item.get("mtime") or 0.0)
        for local_idx, opp in enumerate(opportunities[:24]):
            if not isinstance(opp, dict):
                continue
            candidate = dict(opp)
            candidate.setdefault("source_file", str(item.get("path") or ""))
            candidate["rank_score"] = _score_revenue_opportunity(candidate, mtime)
            ranked.append((float(candidate["rank_score"]), mtime, -local_idx, candidate))
    ranked.sort(key=lambda row: (row[0], row[1], row[2]), reverse=True)
    out = [row[3] for row in ranked[: max(1, min(limit, 24))]]
    source_file = ""
    if out:
        source_file = str(out[0].get("source_file") or "")
    return out, source_file


def _execution_plan_for_opportunity(opp: Dict[str, Any], source_file: str = "") -> Dict[str, Any]:
    title = str(opp.get("title") or "selected opportunity").strip()
    capability = str(opp.get("required_capability") or "").strip() or "operator_review"
    difficulty = str(opp.get("difficulty") or "unknown").strip()
    expected_value = str(opp.get("expected_value") or "unknown").strip()
    steps = [
        f"Review selected opportunity: {title[:120]}",
        f"Verify required capability is available: {capability}",
        "Run one bounded validation task and save the result as an operator artifact",
        "Only move to external posting, payment, or outreach after explicit operator approval",
    ]
    if source_file:
        steps.insert(1, f"Use source artifact: {source_file}")
    return {
        "selected_title": title,
        "required_capability": capability,
        "difficulty": difficulty,
        "expected_value": expected_value,
        "steps": steps,
        "constraints": [
            "no_external_posting_without_operator",
            "no_payment_or_transfer_without_operator",
            "record_artifact_before_next_action",
        ],
    }


def _builtin_elysia_builtin_llm_via_unified(guardian: Any, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Run elysia_builtin_llm through the same stack as internal autonomy/chat (unified router, autonomy-safe when available).
    Used when ``modules['tool_registry']`` is the lightweight core catalog without ``call_tool``.
    """
    us = getattr(guardian, "_unified_system", None)
    if us is None:
        return None
    raw_msgs = payload.get("messages")
    messages: List[Dict[str, str]]
    if isinstance(raw_msgs, list) and raw_msgs:
        messages = []
        for m in raw_msgs:
            if not isinstance(m, dict):
                continue
            role = str(m.get("role") or "user").strip().lower()
            if role not in ("system", "user", "assistant"):
                role = "user"
            content = str(m.get("content") or "")[:12000]
            if content:
                messages.append({"role": role, "content": content})
        if not messages:
            messages = [{"role": "user", "content": "(empty)"}]
    else:
        parts: List[str] = []
        for key in ("prompt", "task", "query", "objective", "user_text", "message", "content"):
            val = payload.get(key)
            if val is not None and str(val).strip():
                parts.append(str(val).strip())
        blob = "\n\n".join(parts).strip()[:12000]
        messages = [{"role": "user", "content": blob or "(empty)"}]
    try:
        mt = int(payload.get("max_tokens") or payload.get("max_output_tokens") or 512)
    except (TypeError, ValueError):
        mt = 512
    mt = max(32, min(8000, mt))
    module_name = str(payload.get("module_name") or "planner")
    agent_raw = payload.get("agent_name")
    agent_name = str(agent_raw) if agent_raw is not None else "orchestrator"
    pe = payload.get("prompt_extra")
    prompt_extra = pe if isinstance(pe, dict) else None
    sr_raw = payload.get("structured_role") or payload.get("structuredRole")
    structured_role = str(sr_raw).strip() if sr_raw is not None and str(sr_raw).strip() else None
    # This bridge is itself the generic LLM capability. Letting unified chat run
    # capability preamble/tool-first selection here can recursively select
    # elysia_builtin_llm again and produce nested "Capability executed" payloads.
    skip_pre = bool(payload.get("skip_capability_preamble", True))
    try:
        if hasattr(us, "_autonomy_llm_completion"):
            reply, err = us._autonomy_llm_completion(
                messages,
                mt,
                module_name=module_name,
                agent_name=agent_name,
                prompt_extra=prompt_extra,
                skip_capability_preamble=skip_pre,
                structured_role=structured_role,
            )
        elif hasattr(us, "_llm_completion"):
            reply, err = us._llm_completion(
                messages,
                mt,
                module_name=module_name,
                agent_name=agent_name,
                prompt_extra=prompt_extra,
                skip_capability_preamble=skip_pre,
                require_autonomy_safe_reasoning=True,
                structured_role=structured_role,
            )
        else:
            return None
    except Exception as e:
        logger.debug("builtin_llm unified: %s", e)
        return {"success": False, "error": str(e)}
    ok = bool((reply or "").strip()) and not (err or "").strip()
    inner = {
        "success": ok,
        "data": reply if ok else "",
        "error": (err or "")[:2000] if not ok else "",
    }
    return {"success": True, "result": inner}


# Real-task task_router executions only (excludes health_probe and probe_like DEBUG paths).
_TASK_ROUTER_GATE_METRICS: Dict[str, Any] = {
    "real_task_events": 0,
    "ok_route_metadata": 0,
    "ok_payload": 0,
    "fail_closed_gate": 0,
    "by_routed_to_on_success": defaultdict(int),  # type: ignore[arg-type]
    "by_task_type": defaultdict(int),  # type: ignore[arg-type]
}
_TASK_ROUTER_METRICS_LOG_EVERY = 25


def _bump_task_router_gate_metrics(
    task_type: str,
    routed_to: Any,
    success_source: str,
    ok: bool,
) -> None:
    m = _TASK_ROUTER_GATE_METRICS
    m["real_task_events"] = int(m["real_task_events"]) + 1
    if ok:
        if success_source == "route_metadata":
            m["ok_route_metadata"] = int(m["ok_route_metadata"]) + 1
        elif success_source == "payload":
            m["ok_payload"] = int(m["ok_payload"]) + 1
        if routed_to is not None and str(routed_to).strip():
            m["by_routed_to_on_success"][str(routed_to)] += 1
    else:
        m["fail_closed_gate"] = int(m["fail_closed_gate"]) + 1
    m["by_task_type"][str(task_type)] += 1
    n = int(m["real_task_events"])
    if n % _TASK_ROUTER_METRICS_LOG_EVERY == 0:
        snap = {
            "real_task_events": m["real_task_events"],
            "ok_route_metadata": m["ok_route_metadata"],
            "ok_payload": m["ok_payload"],
            "fail_closed_gate": m["fail_closed_gate"],
            "by_routed_to_on_success": dict(m["by_routed_to_on_success"]),
            "by_task_type": dict(m["by_task_type"]),
        }
        logger.info("[CapabilityExec] task_router_gate_metrics cumulative=%s", snap)


def get_task_router_gate_metrics_snapshot() -> Dict[str, Any]:
    """Read-only snapshot for tests / diagnostics."""
    m = _TASK_ROUTER_GATE_METRICS
    return {
        "real_task_events": int(m["real_task_events"]),
        "ok_route_metadata": int(m["ok_route_metadata"]),
        "ok_payload": int(m["ok_payload"]),
        "fail_closed_gate": int(m["fail_closed_gate"]),
        "by_routed_to_on_success": dict(m["by_routed_to_on_success"]),
        "by_task_type": dict(m["by_task_type"]),
    }


def reset_task_router_gate_metrics() -> None:
    """Zero cumulative counters (tests / manual diagnostics)."""
    m = _TASK_ROUTER_GATE_METRICS
    m["real_task_events"] = 0
    m["ok_route_metadata"] = 0
    m["ok_payload"] = 0
    m["fail_closed_gate"] = 0
    m["by_routed_to_on_success"] = defaultdict(int)
    m["by_task_type"] = defaultdict(int)


def _builtin_operator_tool_result(guardian: Any, tool_name: str, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Minimum viable tools: always return structured data via existing modules / local artifacts.
    Used when catalog tools are empty so autonomy still progresses.
    """
    mods = getattr(guardian, "_modules", None) or {}
    tname = (tool_name or "").strip().lower()
    st = str(payload.get("self_task_archetype") or "")

    if tname == "artifact_synthesizer":
        artifacts = _iter_operator_artifact_entries(guardian)
        if st in ("package_operator_offer_pack", "package_operator_offer_page"):
            from .self_task_output_contracts import build_offer_pack_from_artifacts

            revenue = _select_offer_pack_revenue_payload(artifacts)
            digest = next(
                (
                    item.get("payload")
                    for item in artifacts
                    if item.get("contract_id") == "learned_digest" and isinstance(item.get("payload"), dict)
                ),
                None,
            )
            improvement = next(
                (
                    item.get("payload")
                    for item in artifacts
                    if item.get("contract_id") in (
                        "system_improvement_proposal",
                        "capability_gap_report",
                        "research_brief",
                    )
                    and isinstance(item.get("payload"), dict)
                ),
                None,
            )
            source_names = [
                str(item.get("file_name") or item.get("path") or "")
                for item in artifacts
                if item.get("contract_id") != "offer_pack"
            ][:8]
            return {
                "success": True,
                "result": build_offer_pack_from_artifacts(
                    revenue_payload=revenue,
                    digest_payload=digest,
                    improvement_payload=improvement,
                    source_names=source_names,
                ),
            }

        out: Dict[str, Any] = {"summaries": [], "sources": []}
        for item in artifacts[:12]:
            blob = item.get("blob")
            if not isinstance(blob, dict):
                continue
            out["summaries"].append(
                {
                    "file": item.get("file_name"),
                    "contract_id": item.get("contract_id"),
                    "preview_keys": list(blob.keys())[:14],
                }
            )
            out["sources"].append(str(item.get("path") or ""))
        return {"success": True, "result": out}

    if tname == "opportunity_ranker":
        artifacts = _iter_operator_artifact_entries(guardian)
        ranked_ops, source_file = _rank_revenue_opportunities(artifacts)
        if not ranked_ops:
            return {"success": True, "result": {"ranked": [], "note": "no_opportunity_artifacts"}}
        return {
            "success": True,
            "result": {
                "ranked": ranked_ops,
                "source_file": source_file,
                "ranking_basis": "expected_value+difficulty+capability+recency",
            },
        }

    if tname == "revenue_executor":
        base_summary: Dict[str, Any] = {}
        ig = mods.get("income_generator")
        if ig and hasattr(ig, "get_income_summary"):
            try:
                s = ig.get_income_summary()
                base_summary = s if isinstance(s, dict) else {"summary": s}
            except Exception:
                pass
        from .self_task_output_contracts import build_revenue_shortlist_from_summary

        if st in ("execute_best_opportunity",):
            artifacts = _iter_operator_artifact_entries(guardian)
            ranked_ops, source_file = _rank_revenue_opportunities(artifacts)
            artifact_backed = bool(ranked_ops)
            if not ranked_ops:
                fallback_shortlist = build_revenue_shortlist_from_summary(base_summary)
                fallback_artifacts = [
                    {
                        "contract_id": "revenue_shortlist",
                        "payload": fallback_shortlist,
                        "path": "income_generator.get_income_summary",
                        "mtime": 0.0,
                    }
                ]
                ranked_ops, source_file = _rank_revenue_opportunities(fallback_artifacts)
            selected = ranked_ops[0] if ranked_ops else {}
            plan = _execution_plan_for_opportunity(selected, source_file)
            plan["income_snapshot_keys"] = list(base_summary.keys())[:20]
            return {
                "success": True,
                "result": {
                    "selected_opportunity": selected,
                    "ranked": ranked_ops[:5],
                    "source_file": source_file,
                    "artifact_backed": artifact_backed,
                    "execution_plan": plan,
                },
            }
        if st in ("generate_execution_plan",):
            return {
                "success": True,
                "result": {
                    "execution_plan": {
                        "phases": ["verify_inputs", "execute_locally", "record_artifact"],
                        "constraints": ["no_external_posting", "no_transfers_without_operator"],
                    }
                },
            }
        return {"success": True, "result": build_revenue_shortlist_from_summary(base_summary)}

    if tname == "elysia_bounded_browser":
        from .bounded_browser.capability import run_bounded_browser_for_capability

        try:
            return run_bounded_browser_for_capability(guardian, payload)
        except Exception as e:
            logger.debug("elysia_bounded_browser: %s", e)
            return {"success": False, "error": str(e)}

    if tname == "elysia_moltbook_browser":
        from .bounded_browser.moltbook import run_moltbook_browser_for_capability

        try:
            return run_moltbook_browser_for_capability(guardian, payload)
        except Exception as e:
            logger.debug("elysia_moltbook_browser: %s", e)
            return {"success": False, "error": str(e)}

    if tname == "elysia_social_intel":
        from .social_intelligence import run_social_intel_for_capability

        try:
            return run_social_intel_for_capability(guardian, payload)
        except Exception as e:
            logger.debug("elysia_social_intel: %s", e)
            return {"success": False, "error": str(e)}

    if tname == "elysia_builtin_web":
        return _safe_builtin_web_fetch(payload)

    if tname == "elysia_builtin_exec":
        return {
            "success": False,
            "error": "elysia_builtin_exec is gated; explicit operator approval is required before running local commands",
            "requires_approval": True,
            "status": "deferred",
        }

    if tname == "elysia_builtin_llm":
        bridged = _builtin_elysia_builtin_llm_via_unified(guardian, payload)
        if bridged is not None:
            return bridged

    if tname == "elysia_mcp_tool":
        from .mcp_capability import run_builtin_mcp_tool

        return run_builtin_mcp_tool(guardian, payload)

    return None


def parse_use_capability_action(action: str) -> Optional[Tuple[str, str]]:
    """Parse use_capability/<kind>/<segment> → (kind, segment)."""
    p = "use_capability/"
    a = (action or "").strip()
    if not a.startswith(p):
        return None
    rest = a[len(p) :]
    if "/" not in rest:
        return None
    kind, seg = rest.split("/", 1)
    kind = kind.strip().lower()
    seg = seg.strip()
    if kind not in ("tool", "module", "api") or not seg:
        return None
    return kind, seg


def _slug_segment(s: str) -> str:
    return "".join(c if c.isalnum() or c in "_-" else "_" for c in (s or ""))[:80]


def capability_action_string(kind: str, name: str) -> str:
    """Stable action id for autonomy / Mistral candidates."""
    k = (kind or "").strip().lower()
    return f"use_capability/{k}/{_slug_segment(name)}"


def resolve_tool_name(guardian: Any, segment: str) -> str:
    """Map slug or segment to a registered tool name when possible."""
    mods = getattr(guardian, "_modules", None) or {}
    tr = mods.get("tool_registry")
    if tr is None or not hasattr(tr, "list_tools"):
        return segment
    try:
        raw = tr.list_tools()
    except Exception:
        return segment
    keys: List[str]
    if isinstance(raw, dict):
        keys = [str(k) for k in raw.keys()]
    elif isinstance(raw, list):
        keys = [str(x) for x in raw]
    else:
        keys = [str(raw)]
    if segment in keys:
        return segment
    seg_l = segment.lower().replace("_", " ")
    for k in keys:
        kl = k.lower().replace(" ", "_")
        if kl == segment.lower():
            return k
        if seg_l and seg_l in k.lower():
            return k
    return segment


def resolve_exec_target(
    guardian: Any,
    action: str,
    metadata: Optional[Dict[str, Any]],
) -> Optional[Tuple[str, str]]:
    """Returns (kind, canonical_name) for execute_capability."""
    meta = metadata or {}
    mk = meta.get("capability_exec_kind")
    mn = meta.get("capability_exec_name")
    if mk and mn:
        return str(mk).lower(), str(mn)
    parsed = parse_use_capability_action(action)
    if not parsed:
        return None
    kind, seg = parsed
    if kind == "tool":
        return "tool", resolve_tool_name(guardian, seg)
    if kind == "module":
        mods = getattr(guardian, "_modules", None) or {}
        if seg in mods:
            return "module", seg
        seg_l = seg.lower()
        for k in mods.keys():
            if str(k).lower() == seg_l or seg_l == str(k).lower().replace(" ", "_"):
                return "module", str(k)
        return "module", seg
    return None


def infer_chat_capability_input(user_text: str, entry: Dict[str, Any]) -> Dict[str, Any]:
    """Lightweight kwargs for tool/module calls from chat."""
    text = (user_text or "").strip()
    if str(entry.get("name") or "").strip().lower() == "elysia_mcp_tool":
        from .mcp_capability import infer_elysia_mcp_tool_chat_input

        out = infer_elysia_mcp_tool_chat_input(text)
        out.setdefault("query", text[:800])
        out.setdefault("task", text[:1200])
        return out
    desc = (entry.get("description") or "").lower()
    out: Dict[str, Any] = {"task": text[:1200], "query": text[:800], "prompt": text[:800]}
    blob = f"{desc} {entry.get('name', '')}".lower()
    if "bounded" in blob and "browser" in blob:
        out["method"] = "bounded_browse"
    elif any(w in blob for w in ("search", "web", "http", "url", "fetch")):
        out["method"] = "search"
    elif any(w in blob for w in ("generate", "write", "compose", "summarize")):
        out["method"] = "execute"
    else:
        out["method"] = "execute"
    return out


def capability_action_is_safe_idle(kind: str, name: str) -> bool:
    """Read-only / local probes suitable for idle exploration."""
    k = (kind or "").lower()
    n = (name or "").strip().lower()
    if k == "module" and n in ("tool_registry", "longterm_planner", "task_router"):
        return True
    return False


def execute_capability_kind(
    guardian: Any,
    kind: str,
    name: str,
    inp: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Execute a single capability by kind/name.
    kind: tool | module (api reserved — not auto-run here).
    """
    payload = dict(inp or {})
    mods = getattr(guardian, "_modules", None) or {}
    k = (kind or "").strip().lower()
    nm = (name or "").strip()

    if k == "api":
        return {"success": False, "error": "api capabilities are routed via LLM/router, not execute_capability"}

    if k == "tool":
        builtin = _builtin_operator_tool_result(guardian, nm, payload)
        if builtin is not None:
            return builtin
        tr = mods.get("tool_registry")
        if tr is None:
            return {"success": False, "error": "tool_registry not wired"}
        method = str(payload.pop("method", None) or "execute")
        try:
            if hasattr(tr, "call_tool"):
                result = tr.call_tool(nm, method, **payload)
            else:
                builtin_fallback = _builtin_operator_tool_result(guardian, nm, {**payload, "method": method})
                if builtin_fallback is not None:
                    return builtin_fallback
                return {"success": False, "error": "tool_registry has no call_tool"}
            ok = bool(result.get("success")) if isinstance(result, dict) else bool(result)
            if not ok:
                builtin = _builtin_operator_tool_result(guardian, nm, payload)
                if builtin is not None:
                    return builtin
            return {"success": ok, "result": result}
        except Exception as e:
            logger.debug("execute_capability tool %s: %s", nm, e)
            builtin = _builtin_operator_tool_result(guardian, nm, payload)
            if builtin is not None:
                return builtin
            return {"success": False, "error": str(e)}

    if k == "module":
        if (nm or "").strip().lower() == "bounded_browser":
            from .bounded_browser.capability import run_bounded_browser_for_capability

            try:
                return run_bounded_browser_for_capability(guardian, payload)
            except Exception as e:
                logger.debug("module bounded_browser: %s", e)
                return {"success": False, "error": str(e)}

        if (nm or "").strip().lower() == "moltbook_browser":
            from .bounded_browser.moltbook import run_moltbook_browser_for_capability

            try:
                return run_moltbook_browser_for_capability(guardian, payload)
            except Exception as e:
                logger.debug("module moltbook_browser: %s", e)
                return {"success": False, "error": str(e)}

        mod = mods.get(nm)
        if mod is None:
            return {"success": False, "error": f"module '{nm}' not in _modules"}
        try:
            if nm == "tool_registry" and hasattr(mod, "list_tools"):
                tools = mod.list_tools()
                st_arch = str(payload.get("self_task_archetype") or "")
                if st_arch == "identify_capability_gaps":
                    from .self_task_output_contracts import build_capability_gap_report_from_tools

                    return {"success": True, "result": build_capability_gap_report_from_tools(tools)}
                if st_arch == "identify_idle_capabilities_with_market_value":
                    from .self_task_output_contracts import build_market_value_opportunities_from_tools

                    return {"success": True, "result": build_market_value_opportunities_from_tools(tools)}
                if st_arch == "generate_system_improvement_brief":
                    from .self_task_output_contracts import (
                        build_capability_gap_report_from_tools,
                        build_system_improvement_from_gaps,
                    )

                    gap = build_capability_gap_report_from_tools(tools)
                    return {"success": True, "result": build_system_improvement_from_gaps(gap)}
                if st_arch == "compare_underused_modules_value":
                    from .self_task_output_contracts import build_compare_underused_modules_research

                    um = list(payload.get("underused_modules") or [])
                    return {
                        "success": True,
                        "result": build_compare_underused_modules_research(um),
                    }
                return {"success": True, "result": {"tools": tools}}
            if nm == "longterm_planner" and hasattr(mod, "objectives"):
                raw = mod.objectives
                seq = list(raw.values()) if isinstance(raw, dict) else (list(raw) if isinstance(raw, list) else [])
                st_arch = str(payload.get("self_task_archetype") or "")
                if st_arch == "evaluate_existing_objectives_for_monetization":
                    from .self_task_output_contracts import build_monetization_from_planner_objectives

                    return {"success": True, "result": build_monetization_from_planner_objectives(seq)}
                return {"success": True, "result": {"objectives_preview": len(seq)}}
            if nm == "task_router" and hasattr(mod, "route_task"):
                st = payload.get("structured_task")
                is_health_probe = False
                route_payload: Dict[str, Any] = dict(payload)
                if isinstance(st, dict):
                    tt = str(st.get("task_type") or "routing_probe")
                    is_health_probe = bool(st.get("_guardian_router_health_probe"))
                    r = mod.route_task(tt, st)
                    route_payload = _task_router_gate_payload(payload, st)
                else:
                    tt = "routing_probe"
                    ctx = {
                        "task_type": "routing_probe",
                        "objective": str(
                            payload.get("objective") or payload.get("query") or payload.get("task") or ""
                        )[:500],
                        "payload": {"source": "execute_capability", "format_version": 1},
                    }
                    r = mod.route_task(ctx["task_type"], ctx)
                    route_payload = _task_router_gate_payload(payload, ctx)
                success_source = "none"
                route_gate_reason = "not_evaluated"
                if isinstance(r, dict):
                    ok_payload = bool(r.get("data") or r.get("tasks") or r.get("result"))
                    ok_route, route_gate_reason = _task_router_route_metadata_gate(r, route_payload)
                    # Health probe: only payload counts as success (diagnostic; route metadata alone is not "work").
                    if is_health_probe:
                        ok = ok_payload
                        success_source = "payload" if ok_payload else "none"
                    else:
                        ok = ok_payload or ok_route
                        if ok_payload:
                            success_source = "payload"
                        elif ok_route:
                            success_source = "route_metadata"
                        else:
                            success_source = "none"
                else:
                    ok = bool(r)
                    success_source = "non_dict_truthy" if ok else "none"
                # Utilization: routing picks a tool id; this path does not call tool_registry.call_tool.
                rd = r if isinstance(r, dict) else {}
                rt = rd.get("routed_to")
                rs = rd.get("score")
                if is_health_probe:
                    logger.debug(
                        "[CapabilityExec] task_router health_probe task_type=%s routed_to=%s score=%s "
                        "ok_gate=%s success_source=%s route_gate_reason=%s (route_metadata_ignored_for_ok)",
                        tt,
                        rt,
                        rs,
                        ok,
                        success_source,
                        route_gate_reason,
                    )
                elif tt == "routing_probe":
                    logger.debug(
                        "[CapabilityExec] task_router probe_like task_type=%s routed_to=%s score=%s "
                        "ok_gate=%s success_source=%s route_gate_reason=%s",
                        tt,
                        rt,
                        rs,
                        ok,
                        success_source,
                        route_gate_reason,
                    )
                else:
                    logger.info(
                        "[CapabilityExec] task_router real_task task_type=%s routed_to=%s route_score=%s "
                        "ok_gate=%s success_source=%s route_gate_reason=%s abandoned_as_empty=%s",
                        tt,
                        rt,
                        rs,
                        ok,
                        success_source,
                        route_gate_reason,
                        not ok,
                    )
                    _bump_task_router_gate_metrics(tt, rt, success_source, ok)
                if not ok:
                    return {
                        "success": False,
                        "error": "task_router_no_matching_tool",
                        "result": {
                            "use_fallback": "execute_self_task",
                            "route_empty": True,
                            "route_blocked_reason": route_gate_reason,
                        },
                    }
                return {"success": ok, "result": r}
            if nm == "harvest_engine" and hasattr(mod, "generate_income_report"):
                rep = mod.generate_income_report(payload.get("source") or "gumroad")
                st_arch = str(payload.get("self_task_archetype") or "")
                if st_arch == "harvest_research_brief":
                    from .self_task_output_contracts import build_research_brief_shell

                    text = str(rep)[:4000]
                    return {
                        "success": True,
                        "result": build_research_brief_shell(
                            "Harvest income report",
                            text,
                            "harvest_engine.generate_income_report",
                        ),
                    }
                if st_arch in ("harvest_metrics_summarize",):
                    from .self_task_output_contracts import build_research_brief_shell

                    text = str(rep)[:4000]
                    return {
                        "success": True,
                        "result": build_research_brief_shell(
                            "Harvest metrics summary",
                            text,
                            "harvest_engine",
                        ),
                    }
                return {"success": True, "result": rep}
            if nm == "income_generator" and hasattr(mod, "get_income_summary"):
                st_arch = str(payload.get("self_task_archetype") or "")
                if st_arch in (
                    "generate_revenue_shortlist",
                    "finance_revenue_shortlist",
                ):
                    from .self_task_output_contracts import build_revenue_shortlist_from_summary

                    s = mod.get_income_summary()
                    sd = s if isinstance(s, dict) else {"summary": s}
                    return {"success": True, "result": build_revenue_shortlist_from_summary(sd)}
                if st_arch == "summarize_monetizable_directions_from_learning":
                    s = mod.get_income_summary()
                    sd = s if isinstance(s, dict) else {"summary": s}
                    return {
                        "success": True,
                        "result": {
                            "top_insights": [
                                f"Local income snapshot keys: {list(sd.keys())[:8]}",
                                "Cross-check idle financial modules vs stated opportunities",
                            ],
                            "why_they_matter": "Operators need monetizable directions without outbound transactions.",
                            "recommended_followup_tasks": [
                                "generate_revenue_shortlist",
                                "create_small_dry_run_offer_ideas",
                            ],
                        },
                    }
                if st_arch == "create_small_dry_run_offer_ideas":
                    from .self_task_output_contracts import build_small_offer_ideas

                    return {"success": True, "result": build_small_offer_ideas()}
                s = mod.get_income_summary()
                return {"success": True, "result": s if isinstance(s, dict) else {"summary": s}}
            if nm == "wallet" and hasattr(mod, "get_balance"):
                b = mod.get_balance()
                return {"success": True, "result": b if isinstance(b, dict) else {"balance": b}}
            if nm == "financial_manager" and hasattr(mod, "get_financial_status"):
                st = mod.get_financial_status()
                return {"success": True, "result": st if isinstance(st, dict) else {"status": st}}
            if hasattr(mod, "health_check"):
                h = mod.health_check()
                return {"success": True, "result": h}
            if hasattr(mod, "get_status"):
                s = mod.get_status()
                return {"success": True, "result": s}
            proc = getattr(mod, "process_task", None)
            if callable(proc):
                task = str(payload.get("task") or payload.get("query") or "")[:2000]
                out = proc(task)
                return {"success": True, "result": out}
            return {
                "success": False,
                "error": f"no safe handler for module '{nm}'",
            }
        except Exception as e:
            logger.debug("execute_capability module %s: %s", nm, e)
            return {"success": False, "error": str(e)}

    return {"success": False, "error": f"unknown kind '{k}'"}


def execute_capability(
    guardian: Any, name: str, input: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Execute by capability name:
    - 'tool:<tool_id>' or 'module:<module_key>'
    - bare name: module key if wired, else treated as tool id.
    """
    n = (name or "").strip()
    inp = dict(input or {})
    if not n:
        return {"success": False, "error": "empty capability name"}
    if ":" in n:
        kind, rest = n.split(":", 1)
        return execute_capability_kind(guardian, kind.strip(), rest.strip(), inp)
    mods = getattr(guardian, "_modules", None) or {}
    if n in mods:
        return execute_capability_kind(guardian, "module", n, inp)
    return execute_capability_kind(guardian, "tool", n, inp)
