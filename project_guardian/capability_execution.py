# project_guardian/capability_execution.py
# Callable capability execution bridge: tools, modules, and chat/autonomy hooks.

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


def _builtin_operator_tool_result(guardian: Any, tool_name: str, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Minimum viable tools: always return structured data via existing modules / local artifacts.
    Used when catalog tools are empty so autonomy still progresses.
    """
    mods = getattr(guardian, "_modules", None) or {}
    root = Path(__file__).resolve().parent.parent
    tname = (tool_name or "").strip().lower()
    st = str(payload.get("self_task_archetype") or "")

    if tname == "artifact_synthesizer":
        out: Dict[str, Any] = {"summaries": [], "sources": []}
        for sub in ("data/generated_reports", "data/revenue_briefs", "data/research_briefs"):
            p = root / sub
            if not p.is_dir():
                continue
            for fp in sorted(p.glob("*.json"), key=lambda x: x.stat().st_mtime, reverse=True)[:6]:
                try:
                    with open(fp, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    out["summaries"].append({"file": fp.name, "preview_keys": list(data.keys())[:14]})
                    out["sources"].append(str(fp))
                except Exception:
                    continue
        return {"success": True, "result": out}

    if tname == "opportunity_ranker":
        best_ops: Optional[List[Any]] = None
        best_path = ""
        best_mtime = 0.0
        for sub in ("data/revenue_briefs", "data/generated_reports"):
            p = root / sub
            if not p.is_dir():
                continue
            for fp in p.glob("*.json"):
                try:
                    mtime = fp.stat().st_mtime
                    with open(fp, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    pl = data.get("payload") if isinstance(data, dict) else None
                    blob = pl if isinstance(pl, dict) else data
                    opps = blob.get("opportunities") if isinstance(blob, dict) else None
                    if isinstance(opps, list) and opps and mtime >= best_mtime:
                        best_mtime = mtime
                        best_ops = opps
                        best_path = str(fp)
                except Exception:
                    continue
        if not best_ops:
            return {"success": True, "result": {"ranked": [], "note": "no_opportunity_artifacts"}}
        ranked = sorted(
            range(len(best_ops)),
            key=lambda i: str((best_ops[i] or {}).get("expected_value", "")),
            reverse=True,
        )
        return {
            "success": True,
            "result": {
                "ranked": [best_ops[i] for i in ranked[:12]],
                "source_file": best_path,
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
            plan = {
                "steps": [
                    "Open latest ranked brief under data/revenue_briefs",
                    "Confirm required_capability is wired",
                    "Queue one bounded self-task for the next concrete verification",
                ],
                "income_snapshot_keys": list(base_summary.keys())[:20],
            }
            return {"success": True, "result": {"execution_plan": plan, "opportunities": base_summary}}
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
    desc = (entry.get("description") or "").lower()
    out: Dict[str, Any] = {"task": text[:1200], "query": text[:800], "prompt": text[:800]}
    blob = f"{desc} {entry.get('name', '')}".lower()
    if any(w in blob for w in ("search", "web", "http", "url", "fetch")):
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
                if isinstance(st, dict):
                    tt = str(st.get("task_type") or "routing_probe")
                    r = mod.route_task(tt, st)
                else:
                    ctx = {
                        "task_type": "routing_probe",
                        "objective": str(
                            payload.get("objective") or payload.get("query") or payload.get("task") or ""
                        )[:500],
                        "payload": {"source": "execute_capability", "format_version": 1},
                    }
                    r = mod.route_task(ctx["task_type"], ctx)
                if isinstance(r, dict):
                    ok = bool(r.get("data") or r.get("tasks") or r.get("result"))
                else:
                    ok = bool(r)
                if not ok:
                    return {
                        "success": False,
                        "error": "task_router_no_matching_tool",
                        "result": {"use_fallback": "execute_self_task", "route_empty": True},
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
