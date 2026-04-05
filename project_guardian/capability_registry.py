# project_guardian/capability_registry.py
# Runtime capability map for orchestration: modules, tools, APIs, agents — refreshed for Mistral.

from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
SNAPSHOT_PATH = DATA_DIR / "capability_snapshot.json"
UNDERSTANDING_PATH = DATA_DIR / "system_understanding_report.json"
OUTCOMES_PATH = DATA_DIR / "capability_outcomes.jsonl"
SCOREBOARD_PATH = DATA_DIR / "capability_scoreboard.json"
USAGE_LOG_PATH = DATA_DIR / "capability_usage_log.jsonl"
USAGE_STATS_PATH = DATA_DIR / "capability_usage_stats.json"

_list_tools_keyerror_keys_logged: set[str] = set()
_toolsurface_empty_log_ts: float = 0.0
_toolsurface_empty_last_sig: str = ""


def collect_tool_registry_surface_diag(
    tr: Any,
    *,
    listed_count: int,
    storage_before_ensure: Optional[int] = None,
    storage_after_ensure: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Single compact diagnostic: raw storage vs listed active vs revoked tracking + filter hint.
    listed_count comes from coerce_tool_registry_name_list (post-filter surface list).
    """
    out: Dict[str, Any] = {
        "registry_id": None,
        "registry_class": None,
        "storage_before_ensure": storage_before_ensure,
        "storage_after_ensure": storage_after_ensure,
        "tools_map_count": None,
        "storage_entries": None,
        "active_listed": listed_count,
        "revoked_ids_tracked": None,
        "filter_reason": "",
    }
    if tr is None:
        out["filter_reason"] = "no_tool_registry_module"
        return out
    out["registry_id"] = id(tr)
    out["registry_class"] = type(tr).__name__
    try:
        if hasattr(tr, "tools_map"):
            out["tools_map_count"] = len(tr.tools_map())
    except Exception:
        pass
    if hasattr(tr, "tool_registry_diagnostic_counts"):
        try:
            d = tr.tool_registry_diagnostic_counts()
            if isinstance(d, dict):
                out["storage_entries"] = d.get("storage_entries")
                out["revoked_ids_tracked"] = d.get("revoked_ids_tracked")
        except Exception:
            pass
    if out["storage_entries"] is None:
        try:
            t = getattr(tr, "tools", None)
            if isinstance(t, dict):
                out["storage_entries"] = len(t)
        except Exception:
            out["storage_entries"] = 0
    if out["revoked_ids_tracked"] is None:
        try:
            r = getattr(tr, "revoked", None)
            if isinstance(r, set):
                out["revoked_ids_tracked"] = len(r)
        except Exception:
            out["revoked_ids_tracked"] = 0
    se = int(out.get("storage_entries") or 0)
    al = int(out.get("active_listed") or 0)
    if se == 0 and al == 0:
        out["filter_reason"] = "never_registered_in_storage"
    elif se > 0 and al == 0:
        out["filter_reason"] = "listed_empty_storage_nonempty"
    else:
        out["filter_reason"] = "ok"
    return out


def _maybe_log_toolsurface_empty_diag(
    tool_surface_reason: str,
    plugin_has_key: bool,
    diag: Dict[str, Any],
) -> None:
    """One throttled warning when tools=0 with counts (avoid log spam)."""
    global _toolsurface_empty_log_ts, _toolsurface_empty_last_sig
    if tool_surface_reason != "list_tools_returned_empty":
        return
    try:
        win = float(os.environ.get("ELYSIA_TOOLSURFACE_EMPTY_LOG_MIN_SEC", "120"))
    except ValueError:
        win = 120.0
    sig = json.dumps(
        {
            "r": tool_surface_reason,
            "id": diag.get("registry_id"),
            "pre": diag.get("storage_before_ensure"),
            "post": diag.get("storage_after_ensure"),
            "s": diag.get("storage_entries"),
            "a": diag.get("active_listed"),
            "v": diag.get("revoked_ids_tracked"),
            "f": diag.get("filter_reason"),
            "k": plugin_has_key,
        },
        sort_keys=True,
    )
    now = time.time()
    if now - _toolsurface_empty_log_ts < max(30.0, win) and sig == _toolsurface_empty_last_sig:
        return
    _toolsurface_empty_log_ts = now
    _toolsurface_empty_last_sig = sig
    logger.warning(
        "[Orchestration] toolsurface: tools=0 reason=%s plugin_has_key=%s id=%s cls=%s pre_ensure=%s post_ensure=%s "
        "map=%s raw=%s active=%s revoked=%s filter=%s",
        tool_surface_reason,
        plugin_has_key,
        diag.get("registry_id"),
        diag.get("registry_class"),
        diag.get("storage_before_ensure"),
        diag.get("storage_after_ensure"),
        diag.get("tools_map_count"),
        diag.get("storage_entries"),
        diag.get("active_listed"),
        diag.get("revoked_ids_tracked"),
        diag.get("filter_reason"),
    )


def coerce_tool_registry_name_list(tr: Any, max_names: int = 40) -> Tuple[List[str], str]:
    """
    Normalize tool_registry.list_tools() to tool name strings.
    Handles dict vs list returns; never subscripts dict with a slice (that raises KeyError(slice)).
    Returns (names, diagnostic_suffix) where diagnostic is for toolsurface logging.
    """
    global _list_tools_keyerror_keys_logged
    if tr is None or not hasattr(tr, "list_tools"):
        return [], ""
    raw: Any = None
    try:
        raw = tr.list_tools()
    except KeyError as ke:
        keyrepr = repr(ke.args[0]) if ke.args else "?"
        if keyrepr not in _list_tools_keyerror_keys_logged:
            _list_tools_keyerror_keys_logged.add(keyrepr)
            logger.warning(
                "[Orchestration] list_tools KeyError missing_key=%s offending_type=list_tools_returned_%s",
                keyrepr,
                type(raw).__name__ if raw is not None else "unavailable",
            )
        return [], f"KeyError:{keyrepr}"
    except Exception as e:
        return [], type(e).__name__

    try:
        if isinstance(raw, dict):
            return [str(k) for k in list(raw.keys())[:max_names]], ""
        if isinstance(raw, (list, tuple)):
            return [str(x) for x in raw[:max_names]], ""
        if raw is None:
            return [], ""
        return [str(raw)][:1], ""
    except KeyError as ke:
        keyrepr = repr(ke.args[0]) if ke.args else "?"
        if keyrepr not in _list_tools_keyerror_keys_logged:
            _list_tools_keyerror_keys_logged.add(keyrepr)
            logger.warning(
                "[Orchestration] list_tools normalize KeyError missing_key=%s item_type=%s",
                keyrepr,
                type(raw).__name__,
            )
        return [], f"KeyError:{keyrepr}"
    except Exception as e:
        return [], type(e).__name__


# Map plugin/module names to autonomy actions (when applicable)
_PLUGIN_SUGGESTED_ACTION: Dict[str, str] = {
    "longterm_planner": "work_on_objective",
    "fractalmind": "fractalmind_planning",
    "tool_registry": "tool_registry_pulse",
    "harvest_engine": "harvest_income_report",
    "income_generator": "income_modules_pulse",
    "wallet": "income_modules_pulse",
    "financial_manager": "income_modules_pulse",
    "task_router": "tool_registry_pulse",
    "mutation": "consider_mutation",
    "dreams": "consider_dream_cycle",
    "learning": "consider_learning",
}


def _capability_intent_bonuses(text: str) -> Dict[str, float]:
    """Lightweight intent tags → extra score per capability type."""
    t = (text or "").lower()
    bonuses: Dict[str, float] = {}
    if any(k in t for k in ("search", "lookup", "find", "query", "fetch", "crawl")):
        bonuses["tool"] = bonuses.get("tool", 0.0) + 1.1
    if any(k in t for k in ("plan", "objective", "strategy", "roadmap", "schedule")):
        bonuses["module"] = bonuses.get("module", 0.0) + 0.9
    if any(k in t for k in ("analy", "review", "audit", "inspect", "debug")):
        bonuses["registered"] = bonuses.get("registered", 0.0) + 0.55
        bonuses["module"] = bonuses.get("module", 0.0) + 0.35
    if any(k in t for k in ("generat", "write", "compose", "draft", "create")):
        bonuses["tool"] = bonuses.get("tool", 0.0) + 0.45
        bonuses["api"] = bonuses.get("api", 0.0) + 0.35
    if any(k in t for k in ("financial", "income", "revenue", "budget", "profit", "wallet")):
        bonuses["module"] = bonuses.get("module", 0.0) + 1.0
    if any(k in t for k in ("web", "http", "url", "browser", "site")):
        bonuses["tool"] = bonuses.get("tool", 0.0) + 0.85
    return bonuses


def describe_available_capabilities(snapshot: Optional[Dict[str, Any]] = None, max_chars: int = 4000) -> str:
    """Human/machine summary for prompts (used by Mistral pre-decision recon)."""
    if not snapshot:
        return "[capabilities] snapshot not yet built; prefer code_analysis or tool_registry_pulse."
    lines = [
        f"generated_at={snapshot.get('generated_at', '?')}",
        f"module_registry_count={snapshot.get('module_registry_count', 0)}",
        f"plugins={','.join(snapshot.get('plugin_module_names', [])[:25])}",
        f"tool_registry_tools={snapshot.get('tool_registry_count', 0)}",
        f"consensus_agents={snapshot.get('consensus_agent_count', 0)}",
        f"apis={snapshot.get('api_summary', '')}",
        f"deps={snapshot.get('deps_digest', '')}",
        f"recon_objective={snapshot.get('recon_objective', '')[:200]}",
        f"memory_hint={snapshot.get('memory_recon_hint', '')[:300]}",
    ]
    scored = snapshot.get("scored_candidates") or []
    if scored:
        lines.append("candidate_scores (action:usefulness~cost):")
        for row in scored[:12]:
            lines.append(
                f"  - {row.get('action')}: u={row.get('usefulness', 0):.2f} "
                f"c={row.get('cost', 0):.2f} r={row.get('risk', 0):.2f} mod={row.get('maps_to_module', '')}"
            )
    out = "\n".join(lines)
    return out[:max_chars]


def _safe_list_py_files(root: Path, limit: int = 35) -> List[str]:
    out: List[str] = []
    if not root.is_dir():
        return out
    try:
        for p in sorted(root.rglob("*.py")):
            try:
                rel = p.relative_to(PROJECT_ROOT)
            except ValueError:
                continue
            parts = rel.parts
            if parts and parts[0] in ("tests", ".venv", "venv", "node_modules", "organized_project"):
                continue
            out.append(str(rel).replace("\\", "/"))
            if len(out) >= limit:
                break
    except Exception as e:
        logger.debug("source scan: %s", e)
    return out


class CapabilityRegistry:
    """Structured capability map; throttled refresh; JSON/jsonl persistence."""

    def __init__(self) -> None:
        self._snapshot: Dict[str, Any] = {}
        self._last_refresh_ts: float = 0.0
        self._cycle_api_used: int = 0
        self._cycle_api_max: int = 2
        self._chat_api_used: int = 0
        self._chat_api_max: int = 8
        self._api_cooldown_until: Dict[str, float] = {}
        self._usage_stats_cache: Dict[str, Dict[str, Any]] = {}
        self._usage_stats_mtime: float = 0.0
        DATA_DIR.mkdir(parents=True, exist_ok=True)

    def reset_chat_api_budget(self, max_calls: int = 8) -> None:
        self._chat_api_used = 0
        self._chat_api_max = max(0, int(max_calls))

    def try_consume_chat_api_slot(self) -> bool:
        if self._chat_api_used >= self._chat_api_max:
            return False
        self._chat_api_used += 1
        return True

    def begin_decision_cycle(self, max_api_calls: int = 2) -> None:
        self._cycle_api_used = 0
        self._cycle_api_max = max(0, int(max_api_calls))

    def try_consume_api_slot(self) -> bool:
        if self._cycle_api_used >= self._cycle_api_max:
            return False
        self._cycle_api_used += 1
        return True

    def is_api_in_cooldown(self, provider: str) -> bool:
        return time.time() < float(self._api_cooldown_until.get(provider, 0.0))

    def note_api_failure(self, provider: str, cooldown_sec: float = 120.0) -> None:
        self._api_cooldown_until[provider] = time.time() + max(30.0, float(cooldown_sec))

    def _load_usage_stats(self) -> Dict[str, Dict[str, Any]]:
        """Merge scoreboard + tail of capability_usage_log for success_rate / last_used."""
        try:
            lm = USAGE_LOG_PATH.stat().st_mtime if USAGE_LOG_PATH.exists() else 0.0
            sm = USAGE_STATS_PATH.stat().st_mtime if USAGE_STATS_PATH.exists() else 0.0
            mtime = max(lm, sm)
            if self._usage_stats_cache and mtime <= self._usage_stats_mtime and SCOREBOARD_PATH.exists():
                return self._usage_stats_cache
        except Exception:
            pass
        stats: Dict[str, Dict[str, Any]] = {}
        try:
            if SCOREBOARD_PATH.exists():
                with open(SCOREBOARD_PATH, "r", encoding="utf-8") as f:
                    sb = json.load(f)
                for act, row in (sb.get("actions") or {}).items():
                    ok = int(row.get("ok", 0) or 0)
                    fail = int(row.get("fail", 0) or 0)
                    tot = ok + fail
                    stats[f"action:{act}"] = {
                        "ok": ok,
                        "fail": fail,
                        "success_rate": (ok / tot) if tot else 0.5,
                        "last_used": row.get("last_used"),
                        "fail_ratio": (fail / tot) if tot else 0.0,
                    }
        except Exception as e:
            logger.debug("usage stats scoreboard: %s", e)
        try:
            if USAGE_LOG_PATH.exists():
                with open(USAGE_LOG_PATH, "r", encoding="utf-8") as f:
                    lines = f.readlines()[-400:]
                for line in lines:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        rec = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    cid = rec.get("capability_id") or rec.get("action") or ""
                    if not cid:
                        continue
                    key = str(cid)
                    st = stats.setdefault(key, {"ok": 0, "fail": 0, "success_rate": 0.5, "last_used": None})
                    if rec.get("success"):
                        st["ok"] = int(st.get("ok", 0)) + 1
                    else:
                        st["fail"] = int(st.get("fail", 0)) + 1
                    tot = st["ok"] + st["fail"]
                    st["success_rate"] = (st["ok"] / tot) if tot else 0.5
                    st["fail_ratio"] = (st["fail"] / tot) if tot else 0.0
                    st["last_used"] = rec.get("ts") or st.get("last_used")
        except Exception as e:
            logger.debug("usage stats log: %s", e)
        try:
            if USAGE_STATS_PATH.exists():
                with open(USAGE_STATS_PATH, "r", encoding="utf-8") as f:
                    bundle = json.load(f)
                for cid, row in (bundle.get("capabilities") or {}).items():
                    ok = int(row.get("success", 0) or 0)
                    fail = int(row.get("failure", 0) or 0)
                    tot = ok + fail
                    stats[str(cid)] = {
                        "ok": ok,
                        "fail": fail,
                        "success_rate": (ok / tot) if tot else 0.5,
                        "last_used": row.get("last_used"),
                        "latency_ema_ms": float(row.get("latency_ema_ms", 0) or 0),
                        "fail_ratio": float(row.get("fail_ratio", 0) or ((fail / tot) if tot else 0.0)),
                    }
        except Exception as e:
            logger.debug("usage stats file: %s", e)
        self._usage_stats_cache = stats
        try:
            lm = USAGE_LOG_PATH.stat().st_mtime if USAGE_LOG_PATH.exists() else 0.0
            sm = USAGE_STATS_PATH.stat().st_mtime if USAGE_STATS_PATH.exists() else 0.0
            self._usage_stats_mtime = max(lm, sm)
        except Exception:
            self._usage_stats_mtime = 0.0
        return stats

    def log_capability_usage(
        self,
        *,
        task: str,
        capability_id: str,
        capability_type: str,
        success: bool,
        quality: float,
        latency_ms: float,
        extra: Optional[Dict[str, Any]] = None,
    ) -> None:
        rec = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "task": (task or "")[:500],
            "capability_id": capability_id,
            "capability_type": capability_type,
            "success": success,
            "quality_heuristic": round(max(0.0, min(1.0, float(quality))), 3),
            "latency_ms": round(float(latency_ms), 2),
            **(extra or {}),
        }
        try:
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            with open(USAGE_LOG_PATH, "a", encoding="utf-8") as f:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        except Exception as e:
            logger.debug("capability_usage_log: %s", e)
        self._usage_stats_cache.clear()
        self._merge_usage_stats_json(capability_id, success, latency_ms=latency_ms)

    def _merge_usage_stats_json(
        self, capability_id: str, success: bool, latency_ms: Optional[float] = None
    ) -> None:
        """Lightweight rolling counts per capability_id (complements jsonl)."""
        cid = (capability_id or "unknown").strip() or "unknown"
        try:
            data: Dict[str, Any] = {}
            if USAGE_STATS_PATH.exists():
                with open(USAGE_STATS_PATH, "r", encoding="utf-8") as f:
                    data = json.load(f)
        except Exception:
            data = {}
        caps = data.setdefault("capabilities", {})
        cur = caps.get(cid, {"success": 0, "failure": 0})
        if success:
            cur["success"] = int(cur.get("success", 0)) + 1
        else:
            cur["failure"] = int(cur.get("failure", 0)) + 1
        cur["last_used"] = datetime.now(timezone.utc).isoformat()
        if latency_ms is not None:
            try:
                lm = float(latency_ms)
                ema = float(cur.get("latency_ema_ms", lm) or lm)
                cur["latency_ema_ms"] = round(0.85 * ema + 0.15 * lm, 2)
            except (TypeError, ValueError):
                pass
        tot = int(cur.get("success", 0)) + int(cur.get("failure", 0))
        fail = int(cur.get("failure", 0))
        cur["fail_ratio"] = round(fail / max(1, tot), 4)
        caps[cid] = cur
        data["updated_at"] = datetime.now(timezone.utc).isoformat()
        try:
            with open(USAGE_STATS_PATH, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.debug("capability_usage_stats: %s", e)

    def _build_capability_entries(self, guardian: Any, snapshot: Dict[str, Any]) -> List[Dict[str, Any]]:
        entries: List[Dict[str, Any]] = []
        stats = self._load_usage_stats()

        for name in snapshot.get("plugin_module_names") or []:
            sid = f"module:{name}"
            st = stats.get(sid) or stats.get(f"action:{_PLUGIN_SUGGESTED_ACTION.get(name, '')}") or {}
            entries.append(
                {
                    "name": name,
                    "type": "module",
                    "description": f"Plugin module '{name}' registered on guardian._modules",
                    "interface": f"guardian._modules['{name}']",
                    "health": "ok",
                    "last_used": st.get("last_used"),
                    "success_rate": float(st.get("success_rate", 0.5) or 0.5),
                    "suggested_action": _PLUGIN_SUGGESTED_ACTION.get(name, "code_analysis"),
                    "callable": "capability_execution.execute_capability_kind",
                    "input_schema": {"task": "str", "query": "str", "name_format": f"module:{name}"},
                }
            )

        for agent in snapshot.get("consensus_agents") or []:
            aid = f"agent:{agent}"
            st = stats.get(aid) or {}
            entries.append(
                {
                    "name": str(agent),
                    "type": "agent",
                    "description": f"Consensus agent '{agent}'",
                    "interface": "guardian.consensus.agents",
                    "health": "ok",
                    "last_used": st.get("last_used"),
                    "success_rate": float(st.get("success_rate", 0.5) or 0.5),
                    "suggested_action": "continue_mission",
                }
            )

        for ar in snapshot.get("architect_registry") or []:
            nm = str(ar.get("name") or "").strip()
            if not nm:
                continue
            role = str(ar.get("role") or "")
            ifaces = ar.get("exposed_interfaces") or []
            if isinstance(ifaces, list):
                iface_s = ",".join(str(x) for x in ifaces[:12])
            else:
                iface_s = str(ifaces)
            rid = f"architect:{nm}"
            st = stats.get(rid) or {}
            entries.append(
                {
                    "name": nm,
                    "type": "registered",
                    "description": f"Architect ModuleArchitect entry role={role} interfaces={iface_s[:200]}",
                    "interface": "ArchitectCore.module_architect.modules",
                    "health": "ok",
                    "last_used": st.get("last_used"),
                    "success_rate": float(st.get("success_rate", 0.5) or 0.5),
                    "suggested_action": "tool_registry_pulse",
                }
            )

        mods = getattr(guardian, "_modules", None) or {}
        tr = mods.get("tool_registry") if isinstance(mods, dict) else None
        if tr is not None:
            tool_names, _ = (
                coerce_tool_registry_name_list(tr, 40)
                if hasattr(tr, "list_tools")
                else ([], "")
            )
            for tn in tool_names:
                desc = f"Registered tool '{tn}'"
                health = "ok"
                if hasattr(tr, "get_tool_metadata"):
                    meta = tr.get_tool_metadata(tn)
                    if meta is not None:
                        desc = getattr(meta, "description", desc) or desc
                        prov = getattr(meta, "provider", "") or ""
                        envn = getattr(meta, "api_key_env", None)
                        if envn and not os.getenv(str(envn)):
                            health = "no_key"
                tid = f"tool:{tn}"
                st = stats.get(tid) or {}
                entries.append(
                    {
                        "name": tn,
                        "type": "tool",
                        "description": (desc or "")[:300],
                        "interface": f"tool_registry.call_tool('{tn}', ...)",
                        "health": health,
                        "last_used": st.get("last_used"),
                        "success_rate": float(st.get("success_rate", 0.5) or 0.5),
                        "suggested_action": "tool_registry_pulse",
                        "callable": "capability_execution.execute_capability_kind",
                        "input_schema": {"method": "str", "kwargs": "object", "name_format": f"tool:{tn}"},
                    }
                )

        api_flags = snapshot.get("api_keys_present") or {}
        for label, on in api_flags.items():
            if label == "mistral_ollama":
                continue
            hid = f"api:{label}"
            st = stats.get(hid) or {}
            entries.append(
                {
                    "name": label,
                    "type": "api",
                    "description": f"External API flag {label}",
                    "interface": "multi_api_router.select_best_api / env",
                    "health": "ok" if on else "no_key",
                    "last_used": st.get("last_used"),
                    "success_rate": float(st.get("success_rate", 0.5) or 0.5),
                    "suggested_action": "consider_prompt_evolution",
                }
            )

        return entries

    def get_relevant_capabilities(
        self,
        task_description: str,
        guardian: Any,
        snapshot: Optional[Dict[str, Any]] = None,
        top_k: int = 15,
    ) -> List[Dict[str, Any]]:
        """Rank modules/agents/tools/APIs for a task (keyword + success_rate + type heuristics)."""
        snap = snapshot if snapshot is not None else self._snapshot
        if not snap:
            return []
        text = (task_description or "").lower()
        tokens = {t for t in "".join(ch if ch.isalnum() or ch.isspace() else " " for ch in text).split() if len(t) > 2}

        entries = [e for e in self._build_capability_entries(guardian, snap) if e.get("type") != "api"]
        stats = self._load_usage_stats()
        intent_map = _capability_intent_bonuses(text)
        ranked: List[Dict[str, Any]] = []
        for e in entries:
            blob = f"{e['name']} {e['description']} {e['type']} {e.get('suggested_action', '')}".lower()
            kw_hits = sum(1 for t in tokens if t in blob)
            type_bonus = 0.0
            if e["type"] == "tool" and any(k in text for k in ("tool", "call", "fetch", "api", "search", "run")):
                type_bonus += 1.5
            if e["type"] == "module" and any(k in text for k in ("plan", "task", "objective", "income", "harvest", "mutat")):
                type_bonus += 1.0
            if e["type"] == "registered" and any(k in text for k in ("architect", "module", "registry", "interface", "plan")):
                type_bonus += 0.6
            if e.get("health") == "no_key":
                type_bonus -= 2.0
            et = e["type"]
            nm = str(e["name"])
            if et == "module":
                sid = f"module:{nm}"
            elif et == "tool":
                sid = f"tool:{nm}"
            elif et == "agent":
                sid = f"agent:{nm}"
            elif et == "registered":
                sid = f"architect:{nm}"
            elif et == "api":
                sid = f"api:{nm}"
            else:
                sid = f"{et}:{nm}"
            st = stats.get(sid) or {}
            intent_bonus = float(intent_map.get(e["type"], 0.0))
            sr = float(st.get("success_rate", e.get("success_rate", 0.5)) or 0.5)
            mem_boost = (sr - 0.5) * 2.5
            latency_ema = float(st.get("latency_ema_ms", 0) or 0) or 200.0
            latency_penalty = min(1.25, max(0.0, (latency_ema - 160.0) / 450.0))
            fail_ratio = float(st.get("fail_ratio", 0) or 0)
            failure_penalty = fail_ratio * 2.4
            recent_bonus = 0.0
            lu = st.get("last_used") or e.get("last_used")
            if lu:
                try:
                    lut = str(lu).replace("Z", "+00:00")
                    dt = datetime.fromisoformat(lut)
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=timezone.utc)
                    if (datetime.now(timezone.utc) - dt).total_seconds() < 3600:
                        recent_bonus = 0.32
                except Exception:
                    pass
            score = (
                kw_hits * 1.1
                + type_bonus
                + mem_boost
                + intent_bonus
                + recent_bonus
                - failure_penalty
                - latency_penalty
            )
            ee = dict(e)
            ee["match_score"] = round(score, 3)
            ranked.append(ee)
        ranked.sort(key=lambda x: -x["match_score"])
        return ranked[: max(5, top_k)]

    def action_is_executable(self, action: str, guardian: Any) -> bool:
        """True if autonomy action has required runtime (Guardian core or wired _modules)."""
        a = (action or "").strip()
        if not a or a == "continue_monitoring":
            return True
        mods = getattr(guardian, "_modules", None) or {}
        if a in ("mission_deadline", "continue_mission"):
            return hasattr(guardian, "missions") and guardian.missions is not None
        if a == "execute_task":
            return hasattr(guardian, "tasks") and guardian.tasks is not None
        if a == "process_queue":
            return getattr(guardian, "elysia_loop", None) is not None
        if a == "consider_learning":
            return True
        if a == "consider_dream_cycle":
            return getattr(guardian, "dreams", None) is not None
        if a == "consider_prompt_evolution":
            return getattr(guardian, "prompt_evolver", None) is not None
        if a == "rebuild_vector":
            return hasattr(guardian, "memory") and guardian.memory is not None
        if a == "consider_adversarial_learning":
            return True
        if a == "fractalmind_planning":
            return bool(mods.get("fractalmind"))
        if a == "harvest_income_report":
            return bool(mods.get("harvest_engine"))
        if a == "income_modules_pulse":
            return bool(mods.get("income_generator") or mods.get("wallet") or mods.get("financial_manager"))
        if a == "tool_registry_pulse":
            return bool(mods.get("tool_registry"))
        if a == "work_on_objective":
            return bool(mods.get("longterm_planner"))
        if a == "code_analysis":
            return getattr(guardian, "analysis_engine", None) is not None
        if a == "consider_mutation":
            return hasattr(guardian, "mutation") and guardian.mutation is not None
        if a == "question_probe":
            return True
        if a == "execute_self_task":
            return True
        if a.startswith("use_capability/tool/"):
            return bool(mods.get("tool_registry"))
        if a.startswith("use_capability/module/"):
            sub = a.split("/", 2)[-1] if a.count("/") >= 2 else ""
            return bool(sub) and sub in mods
        return True

    def capability_entry_to_action(self, entry: Dict[str, Any], guardian: Any) -> str:
        from .capability_execution import capability_action_string

        t = entry.get("type")
        nm = str(entry.get("name") or "").strip()
        if not nm:
            return ""
        mods = getattr(guardian, "_modules", None) or {}
        if t == "tool":
            return capability_action_string("tool", nm)
        if t == "module" and nm in mods:
            return capability_action_string("module", nm)
        return ""

    def append_dynamic_capability_candidates(
        self,
        candidates: List[Dict[str, Any]],
        ranked: List[Dict[str, Any]],
        guardian: Any,
        decider_cfg: Dict[str, Any],
        max_n: int = 6,
    ) -> None:
        if not decider_cfg.get("orchestration_dynamic_capability_actions", True):
            return
        existing = {c.get("action") for c in candidates}
        n_added = 0
        for r in ranked:
            if n_added >= max_n:
                break
            act = self.capability_entry_to_action(r, guardian)
            if not act or act in existing:
                continue
            if not self.action_is_executable(act, guardian):
                continue
            ms = float(r.get("match_score") or 0.0)
            candidates.append(
                {
                    "action": act,
                    "source": "capability_router",
                    "reason": f"Direct capability: {r.get('name')} ({r.get('type')})",
                    "priority_score": min(9.5, 2.4 + min(4.5, ms * 0.45)),
                    "can_auto_execute": True,
                    "metadata": {
                        "capability_exec_kind": r.get("type"),
                        "capability_exec_name": r.get("name"),
                    },
                }
            )
            existing.add(act)
            n_added += 1

    def boost_candidates_for_relevance(
        self,
        candidates: List[Dict[str, Any]],
        ranked: List[Dict[str, Any]],
        top_n: int = 8,
        boost_scale: float = 3.0,
        guardian: Any = None,
    ) -> None:
        """Raise priority_score when an autonomy action matches a top-ranked capability."""
        if not ranked or not candidates:
            return
        by_action: Dict[str, float] = {}
        for r in ranked[:top_n]:
            act = r.get("suggested_action") or ""
            if not act:
                continue
            ms = float(r.get("match_score") or 0.0)
            by_action[act] = max(by_action.get(act, 0.0), ms)
            if guardian is not None:
                act_uc = self.capability_entry_to_action(r, guardian)
                if act_uc:
                    by_action[act_uc] = max(by_action.get(act_uc, 0.0), ms)
        for c in candidates:
            act = c.get("action") or ""
            if act in by_action:
                add = boost_scale * min(1.2, by_action[act] / 4.0)
                c["priority_score"] = c.get("priority_score", 0) + add
                c["_capability_registry_boost"] = True

    def refresh_if_due(self, guardian: Any, min_interval_sec: float = 45.0) -> Dict[str, Any]:
        now = time.time()
        if self._snapshot and (now - self._last_refresh_ts) < min_interval_sec:
            return self._snapshot
        return self.refresh(guardian)

    def refresh(self, guardian: Any) -> Dict[str, Any]:
        try:
            from .capabilities import get_capabilities
        except Exception:
            def get_capabilities() -> Dict[str, Any]:
                return {}

        reg_status: Dict[str, Any] = {}
        try:
            if hasattr(guardian, "module_registry") and guardian.module_registry:
                reg_status = guardian.module_registry.get_registry_status()
        except Exception as e:
            logger.debug("module_registry status: %s", e)

        mods = getattr(guardian, "_modules", None) or {}
        plugin_names = sorted(mods.keys()) if isinstance(mods, dict) else []

        tool_names: List[str] = []
        tool_count = 0
        tool_list_exc: str = ""
        tr = mods.get("tool_registry") if isinstance(mods, dict) else None
        storage_before: Optional[int] = None
        storage_after: Optional[int] = None
        if tr is not None:
            try:
                td = getattr(tr, "tools", None)
                if isinstance(td, dict):
                    storage_before = len(td)
            except Exception:
                pass
        if tr is not None and hasattr(tr, "ensure_minimal_builtin_tools"):
            try:
                tr.ensure_minimal_builtin_tools()
            except Exception:
                pass
        if tr is not None:
            try:
                td = getattr(tr, "tools", None)
                if isinstance(td, dict):
                    storage_after = len(td)
            except Exception:
                pass
        if tr is not None and hasattr(tr, "list_tools"):
            tool_names, tool_list_exc = coerce_tool_registry_name_list(tr, 40)
            tool_count = len(tool_names)
        tool_diag = collect_tool_registry_surface_diag(
            tr,
            listed_count=tool_count,
            storage_before_ensure=storage_before,
            storage_after_ensure=storage_after,
        )

        consensus_agents: List[str] = []
        try:
            if hasattr(guardian, "consensus") and hasattr(guardian.consensus, "agents"):
                consensus_agents = list(getattr(guardian.consensus, "agents", {}).keys())
        except Exception:
            pass

        caps = get_capabilities()
        deps_digest = ",".join(
            f"{k}:{'Y' if (v or {}).get('available') else 'N'}"
            for k, v in sorted(caps.items())[:20]
        )

        try:
            from .cloud_api_state import anthropic_key_loaded, openai_key_loaded

            _oa = openai_key_loaded()
            _an = anthropic_key_loaded()
        except Exception:
            _oa = bool(os.getenv("OPENAI_API_KEY"))
            _an = bool(os.getenv("ANTHROPIC_API_KEY"))
        api_flags = {
            "openai_key": _oa,
            "anthropic_key": _an,
            "twitter_bearer": bool(os.getenv("TWITTER_BEARER_TOKEN")),
            "mistral_ollama": True,
        }
        api_summary = (
            f"openai={'on' if api_flags['openai_key'] else 'off'};"
            f"anthropic={'on' if api_flags['anthropic_key'] else 'off'};"
            f"twitter={'on' if api_flags['twitter_bearer'] else 'off'}"
        )

        recon_objective = ""
        try:
            am = guardian.missions.get_active_missions()
            if am:
                recon_objective = str(am[0].get("name", ""))[:240]
        except Exception:
            pass
        if not recon_objective and mods.get("longterm_planner"):
            try:
                planner = mods["longterm_planner"]
                raw = getattr(planner, "objectives", {})
                seq = list(raw.values()) if isinstance(raw, dict) else []
                for o in seq:
                    st = str((o or {}).get("status", "")).lower() if isinstance(o, dict) else ""
                    if "active" in st:
                        recon_objective = str((o or {}).get("name", ""))[:240]
                        break
            except Exception:
                pass

        startup_thin = False
        try:
            from .startup_runtime_guard import startup_memory_thin_mode_active

            startup_thin = bool(startup_memory_thin_mode_active(guardian))
        except Exception:
            startup_thin = False

        memory_recon_hint = ""
        if not startup_thin:
            try:
                mem = getattr(guardian, "memory", None)
                if mem and hasattr(mem, "recall_last"):
                    rm = mem.recall_last(6) or []
                    bits = []
                    for m in rm[:6]:
                        if isinstance(m, dict):
                            bits.append(str(m.get("thought", ""))[:120])
                        else:
                            bits.append(str(m)[:120])
                    memory_recon_hint = " | ".join(bits)
            except Exception:
                pass

        pending_tasks = 0
        if not startup_thin:
            try:
                if hasattr(guardian, "tasks") and hasattr(guardian.tasks, "list_tasks"):
                    pending_tasks = len(
                        [
                            t
                            for t in (guardian.tasks.list_tasks() or [])
                            if str((t or {}).get("status", "")).lower() in ("pending", "open")
                        ]
                    )
            except Exception:
                pass

        py_sample: List[str] = [] if startup_thin else _safe_list_py_files(PROJECT_ROOT / "project_guardian", limit=30)

        architect_registry: List[Dict[str, Any]] = []
        if not startup_thin:
            try:
                us = getattr(guardian, "_unified_system", None)
                arch = getattr(us, "architect", None) if us else None
                ma = getattr(arch, "module_architect", None) if arch else None
                raw_ar = getattr(ma, "modules", None) or {}
                for reg_name, reg_meta in raw_ar.items():
                    if isinstance(reg_meta, dict):
                        architect_registry.append(
                            {
                                "name": str(reg_name),
                                "role": reg_meta.get("role", ""),
                                "exposed_interfaces": reg_meta.get("exposed_interfaces") or [],
                                "version": reg_meta.get("version", ""),
                            }
                        )
            except Exception as e:
                logger.debug("architect_registry snapshot: %s", e)

        generated_at = datetime.now(timezone.utc).isoformat()
        self._snapshot = {
            "generated_at": generated_at,
            "module_registry": reg_status,
            "module_registry_count": int(reg_status.get("total_modules", 0) or len(reg_status.get("module_names", []) or [])),
            "plugin_module_names": plugin_names,
            "tool_registry_count": tool_count,
            "tool_registry_names": tool_names,
            "tool_registry_diag": tool_diag,
            "consensus_agent_count": len(consensus_agents),
            "consensus_agents": consensus_agents[:30],
            "api_keys_present": api_flags,
            "api_summary": api_summary,
            "dependency_capabilities": {k: bool((v or {}).get("available")) for k, v in caps.items()},
            "deps_digest": deps_digest[:500],
            "recon_objective": recon_objective,
            "memory_recon_hint": memory_recon_hint[:800],
            "pending_tasks_estimate": pending_tasks,
            "source_files_sample": py_sample,
            "architect_registry": architect_registry,
            "architect_registry_count": len(architect_registry),
            "orchestration_note": (
                "Priority: internal modules/adapters → plugin agents (_modules) → external APIs (when keys on) → local Mistral. "
                "Prefer tool_registry_pulse / code_analysis when capabilities unknown. "
                "Do not spam APIs; use when retrieval, embeddings, or stronger generation is needed."
            ),
        }
        self._last_refresh_ts = time.time()

        try:
            from .multi_api_router import select_best_api

            self._snapshot["api_routing_hints"] = {
                "embedding": select_best_api("embedding", registry=self, reserve_slot=False),
                "reasoning": select_best_api("reasoning", quality_requirement="high", registry=self, reserve_slot=False),
                "simple": select_best_api("simple", cost_sensitivity="high", registry=self, reserve_slot=False),
            }
        except Exception as e:
            logger.debug("api_routing_hints: %s", e)

        report = {
            "generated_at": generated_at,
            "registered_adapters": reg_status.get("module_names", []),
            "plugins": plugin_names,
            "tools": tool_names,
            "consensus_agents": consensus_agents,
            "apis": api_flags,
            "pending_tasks_estimate": pending_tasks,
            "project_guardian_py_sample": py_sample,
        }
        try:
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            with open(SNAPSHOT_PATH, "w", encoding="utf-8") as f:
                json.dump(self._snapshot, f, indent=2, ensure_ascii=False)
            with open(UNDERSTANDING_PATH, "w", encoding="utf-8") as f:
                json.dump(report, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.debug("capability snapshot write: %s", e)

        if tr is None:
            tool_surface_reason = "no_tool_registry_module"
        elif not hasattr(tr, "list_tools"):
            tool_surface_reason = "tool_registry_missing_list_tools"
        elif tool_list_exc:
            tool_surface_reason = f"list_tools_exc:{tool_list_exc}"
        elif tool_count == 0:
            tool_surface_reason = "list_tools_returned_empty"
        else:
            tool_surface_reason = "ok"

        logger.info(
            "[Orchestration] capability map refreshed: modules=%d plugins=%d tools=%d agents=%d%s",
            self._snapshot["module_registry_count"],
            len(plugin_names),
            tool_count,
            len(consensus_agents),
            " thin=1" if startup_thin else "",
        )
        if tool_count == 0:
            if tool_surface_reason == "list_tools_returned_empty":
                _maybe_log_toolsurface_empty_diag(
                    tool_surface_reason,
                    "tool_registry" in plugin_names,
                    tool_diag,
                )
            else:
                logger.warning(
                    "[Orchestration] toolsurface: tools=0 reason=%s plugin_has_key=%s",
                    tool_surface_reason,
                    "tool_registry" in plugin_names,
                )
        return self._snapshot

    def understanding_ready(self) -> bool:
        sn = self._snapshot
        if not sn.get("generated_at"):
            return False
        return int(sn.get("module_registry_count", 0)) >= 3

    def score_candidates(
        self,
        candidates: List[Dict[str, Any]],
        snapshot: Dict[str, Any],
        module_cooldowns: Dict[str, Any],
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """Attach orchestration scores; return (enriched_candidates, score_rows_for_mistral)."""
        action_to_module = {
            "consider_learning": "learning",
            "consider_dream_cycle": "dreams",
            "consider_prompt_evolution": "prompt_evolver",
            "rebuild_vector": "memory",
            "consider_adversarial_learning": "adversarial_self_learning",
            "execute_task": "tasks",
            "work_on_objective": "longterm_planner",
            "fractalmind_planning": "fractalmind",
            "harvest_income_report": "harvest_engine",
            "income_modules_pulse": "income",
            "tool_registry_pulse": "tool_registry",
            "code_analysis": "analysis_engine",
            "consider_mutation": "mutation",
            "question_probe": "exploration",
            "continue_mission": "missions",
            "execute_self_task": "self_tasking",
        }
        rows: List[Dict[str, Any]] = []
        plugins = set(snapshot.get("plugin_module_names") or [])
        tool_n = int(snapshot.get("tool_registry_count") or 0)

        for c in candidates:
            act = c.get("action") or ""
            mod = action_to_module.get(act, "")
            if act.startswith("use_capability/module/"):
                mod = act.split("/", 2)[-1]
            elif act.startswith("use_capability/tool/"):
                mod = "tool_registry"
            cooldown_m = float(module_cooldowns.get(mod, 0) or 0) if mod else 0.0
            base_pri = float(c.get("priority_score", 0) or 0)
            usefulness = base_pri * 0.15 + 0.35
            if mod in plugins or mod in ("memory", "tasks", "mutation", "trust", "safety", "consensus"):
                usefulness += 0.25
            if act == "tool_registry_pulse" and tool_n == 0:
                usefulness += 0.2
            if act in ("code_analysis", "tool_registry_pulse") and not self.understanding_ready():
                usefulness += 0.35
            try:
                from .planner_readiness import harvest_zero_yield_priority_factor

                usefulness *= harvest_zero_yield_priority_factor(act)
            except Exception:
                pass
            cost = 0.15 + min(0.4, cooldown_m * 0.02)
            if act in ("execute_task", "work_on_objective"):
                cost += 0.15
            risk = 0.2 if act == "consider_mutation" else 0.1
            if act == "execute_task":
                risk += 0.1
            c["_orchestration"] = {
                "usefulness": round(usefulness, 3),
                "cost": round(cost, 3),
                "risk": round(risk, 3),
                "expected_value": round(usefulness - cost - risk * 0.5, 3),
                "maps_to_module": mod,
            }
            rows.append(
                {
                    "action": act,
                    "usefulness": c["_orchestration"]["usefulness"],
                    "cost": c["_orchestration"]["cost"],
                    "risk": c["_orchestration"]["risk"],
                    "expected_value": c["_orchestration"]["expected_value"],
                    "maps_to_module": mod,
                }
            )
        rows.sort(key=lambda r: -r["expected_value"])
        return candidates, rows

    def log_outcome(
        self,
        *,
        action: str,
        success: bool,
        latency_ms: float,
        extra: Optional[Dict[str, Any]] = None,
    ) -> None:
        rec = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "action": action,
            "success": success,
            "latency_ms": round(latency_ms, 2),
            **(extra or {}),
        }
        try:
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            with open(OUTCOMES_PATH, "a", encoding="utf-8") as f:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        except Exception as e:
            logger.debug("capability_outcomes log: %s", e)
        self._update_scoreboard(action, success)

    def _update_scoreboard(self, action: str, success: bool) -> None:
        try:
            data: Dict[str, Any] = {}
            if SCOREBOARD_PATH.exists():
                with open(SCOREBOARD_PATH, "r", encoding="utf-8") as f:
                    data = json.load(f)
        except Exception:
            data = {}
        actions = data.setdefault("actions", {})
        cur = actions.get(action, {"ok": 0, "fail": 0})
        cur["ok" if success else "fail"] = int(cur.get("ok" if success else "fail", 0)) + 1
        cur["last_used"] = datetime.now(timezone.utc).isoformat()
        actions[action] = cur
        data["updated_at"] = datetime.now(timezone.utc).isoformat()
        try:
            with open(SCOREBOARD_PATH, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.debug("scoreboard: %s", e)
