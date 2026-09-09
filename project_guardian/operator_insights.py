# project_guardian/operator_insights.py
"""
Read-only bundles for the Control Panel **Insights** tab (self-build RAG, MCP, LLM JSONL traces, log tail).

Kept dependency-light: no Flask imports; safe to call from UI routes.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

_REPO = Path(__file__).resolve().parent.parent
_EXTERNAL_STORAGE_CFG = _REPO / "config" / "external_storage.json"


def _win_drive(p: Path) -> Optional[str]:
    """Best-effort Windows drive letter (e.g. ``F:``) for cross-checking USB vs fallback paths."""
    try:
        r = p.resolve()
    except Exception:
        r = p
    if os.name == "nt" and getattr(r, "drive", None):
        return str(r.drive).upper()
    return None


def build_storage_alignment_bundle() -> Dict[str, Any]:
    """
    Compare configured ``external_storage.json`` with where ``get_learned_storage_path()`` actually wrote.

    Surfaces the common issue: thumb drive unplugged → learned data under ``LOCALAPPDATA`` while
    ``memory_filepath`` still points at ``F:\\...``.
    """
    out: Dict[str, Any] = {
        "config_file": str(_EXTERNAL_STORAGE_CFG),
        "config_exists": _EXTERNAL_STORAGE_CFG.is_file(),
        "warnings": [],
    }
    warnings: List[str] = []

    raw: Dict[str, Any] = {}
    if _EXTERNAL_STORAGE_CFG.is_file():
        try:
            raw = json.loads(_EXTERNAL_STORAGE_CFG.read_text(encoding="utf-8"))
        except Exception as e:
            out["parse_error"] = str(e)[:300]
            warnings.append(f"Could not parse external_storage.json: {e}")
            out["warnings"] = warnings
            return out

    ext_drive_raw = str(raw.get("external_drive") or "").strip()
    mem_fp_raw = str(raw.get("memory_filepath") or "").strip()

    base_exists = False
    base_normalized = ""
    try:
        from .external_storage import normalize_storage_root

        if ext_drive_raw:
            base_normalized = normalize_storage_root(ext_drive_raw)
            base_exists = bool(base_normalized) and Path(base_normalized).exists()
    except Exception as e:
        out["external_drive_resolve_error"] = str(e)[:200]

    out["configured_external_drive"] = ext_drive_raw or None
    out["configured_drive_root_exists"] = base_exists
    out["learned_would_use_fallback"] = bool(ext_drive_raw and base_normalized and not base_exists)

    learned_path: Optional[Path] = None
    try:
        from .auto_learning import get_learned_storage_path

        learned_path = get_learned_storage_path()
        out["learned_root"] = str(learned_path)
        out["learned_root_drive"] = _win_drive(learned_path)
        out["learned_exists"] = learned_path.exists()
    except Exception as e:
        out["learned_error"] = str(e)[:200]

    if mem_fp_raw:
        mp = Path(mem_fp_raw)
        out["memory_filepath"] = mem_fp_raw
        out["memory_filepath_drive"] = _win_drive(mp)
        out["memory_filepath_exists"] = mp.is_file()
        ld = out.get("learned_root_drive")
        md = out.get("memory_filepath_drive")
        if ld and md and ld != md:
            warnings.append(
                f"Drive mismatch: guardian_memory.json is on {md} but learned storage is on {ld} "
                "(often means thumb unplugged → learned fell back to LOCALAPPDATA)."
            )

    if out.get("learned_would_use_fallback"):
        warnings.append(
            "Configured external_drive is not reachable; auto-learning learned/ uses LOCALAPPDATA fallback."
        )

    fp_selfbuild = Path(out.get("learned_root") or "") / "local_ai_selfbuild" / "rag_chunks_latest.jsonl"
    if learned_path:
        rsp = fp_selfbuild.is_file()
        out["rag_chunks_latest_exists_at_learned"] = rsp
        if not rsp:
            warnings.append(
                "No rag_chunks_latest.jsonl under learned local_ai_selfbuild yet — run auto-learning export/embed."
            )

    out["warnings"] = warnings
    out["ok"] = len(warnings) == 0
    return out


def _iso_mtime(p: Path) -> Optional[str]:
    try:
        return datetime.fromtimestamp(p.stat().st_mtime, tz=timezone.utc).astimezone().isoformat(timespec="seconds")
    except OSError:
        return None


def _file_brief(p: Path) -> Dict[str, Any]:
    if not p.is_file():
        return {"exists": False, "path": str(p)}
    try:
        st = p.stat()
        return {
            "exists": True,
            "path": str(p),
            "size_bytes": st.st_size,
            "mtime": _iso_mtime(p),
        }
    except OSError:
        return {"exists": False, "path": str(p), "error": "stat_failed"}


def _tail_text_file(path: Path, *, max_lines: int = 40, max_bytes: int = 320_000) -> List[str]:
    try:
        raw = path.read_bytes()
    except OSError:
        return []
    if len(raw) > max_bytes:
        raw = raw[-max_bytes:]
    lines = raw.decode("utf-8", errors="ignore").splitlines()
    n = max(1, min(200, int(max_lines)))
    return lines[-n:]


def _elysia_unified_log_candidates() -> List[Path]:
    out: List[Path] = []
    out.append(_REPO / "elysia_unified.log")
    for i in range(1, 6):
        out.append(_REPO / f"elysia_unified.log.{i}")
    try:
        from .external_storage import get_configured_external_data_dir

        ext = get_configured_external_data_dir()
        if ext:
            out.append(ext / "logs" / "elysia_unified.log")
            for j in range(1, 4):
                out.append(ext / "logs" / f"elysia_unified.log.{j}")
    except Exception:
        pass
    seen: set = set()
    uniq: List[Path] = []
    for p in out:
        k = str(p)
        if k in seen:
            continue
        seen.add(k)
        uniq.append(p)
    return uniq


def build_selfbuild_bundle() -> Dict[str, Any]:
    try:
        from .auto_learning import get_learned_storage_path, load_learning_config
        from .local_ai_selfbuild_retrieve import effective_selfbuild_rag_inject_params

        learned = get_learned_storage_path()
        cfg = load_learning_config()
    except Exception as e:
        return {"error": str(e)[:300]}
    sb = learned / "local_ai_selfbuild"
    keys = [
        "enabled",
        "interval_hours",
        "local_ai_selfbuild_enabled",
        "local_ai_selfbuild_rag_export_enabled",
        "local_ai_selfbuild_rag_export_each_run",
        "local_ai_selfbuild_embed_enabled",
        "local_ai_selfbuild_embed_each_run",
        "local_ai_selfbuild_rag_inject_enabled",
        "local_ai_selfbuild_rag_inject_min_score",
        "local_ai_selfbuild_rag_inject_top_k",
        "local_ai_selfbuild_rag_inject_max_chars",
        "local_ai_selfbuild_rag_inject_max_index_rows",
        "local_ai_selfbuild_embed_model",
    ]
    flags = {k: cfg.get(k) for k in keys if k in cfg}
    embed_ram_pressure: Dict[str, Any] = {}
    try:
        from .local_ai_selfbuild_corpus import system_ram_used_fraction
        from .monitoring import _load_memory_pressure_config

        mpc = _load_memory_pressure_config()
        frac = system_ram_used_fraction()
        try:
            trig = float(
                mpc.get(
                    "selfbuild_embed_ram_trigger_fraction",
                    mpc.get("memory_pressure_trigger_fraction", 0.88),
                )
            )
        except (TypeError, ValueError):
            trig = 0.88
        embed_ram_pressure = {
            "host_ram_used_fraction": round(frac, 4) if frac is not None else None,
            "trigger_fraction": trig,
            "embed_cap_would_apply": bool(frac is not None and frac >= trig),
            "max_chunks_when_ram_high": int(mpc.get("selfbuild_embed_max_chunks_when_ram_high", 8)),
            "batch_when_ram_high": int(mpc.get("selfbuild_embed_batch_when_ram_high", 2)),
        }
    except Exception as e:
        embed_ram_pressure = {"error": str(e)[:160]}

    artifacts = {
        "rag_chunks_latest.jsonl": _file_brief(sb / "rag_chunks_latest.jsonl"),
        "chunk_embeddings_index.jsonl": _file_brief(sb / "chunk_embeddings_index.jsonl"),
        "chunk_embeddings.f32.bin": _file_brief(sb / "chunk_embeddings.f32.bin"),
    }
    return {
        "learned_root": str(learned),
        "selfbuild_dir": str(sb),
        "selfbuild_dir_exists": sb.is_dir(),
        "artifacts": artifacts,
        "auto_learning_flags": flags,
        "rag_inject_effective": effective_selfbuild_rag_inject_params(cfg),
        "embed_ram_pressure": embed_ram_pressure,
    }


def build_mcp_bundle() -> Dict[str, Any]:
    allow_path = _REPO / "config" / "mcp_capability_allowlist.json"
    servers_path = _REPO / "config" / "mcp_servers.json"
    raw_allow = None
    if allow_path.is_file():
        try:
            raw_allow = json.loads(allow_path.read_text(encoding="utf-8"))
        except Exception:
            raw_allow = {"parse_error": True}
    sdk = False
    try:
        from .mcp_stdio_bridge import mcp_sdk_available

        sdk = mcp_sdk_available()
    except Exception:
        pass
    cap_on = False
    try:
        from .mcp_capability import is_mcp_stdio_capability_enabled

        cap_on = is_mcp_stdio_capability_enabled()
    except Exception:
        pass
    return {
        "mcp_sdk_installed": sdk,
        "chat_mcp_capability_active": cap_on,
        "allowlist_path": str(allow_path),
        "allowlist_exists": allow_path.is_file(),
        "allowlist_enabled": bool((raw_allow or {}).get("enabled")) if isinstance(raw_allow, dict) else False,
        "servers_config_path": str(servers_path),
        "servers_config_exists": servers_path.is_file(),
    }


def build_llm_trace_bundle(*, max_lines: int = 50) -> Dict[str, Any]:
    path_s = (os.environ.get("ELYSIA_LLM_TRACE_JSONL") or "").strip()
    if not path_s:
        return {"enabled": False, "path": None, "lines": [], "note": "Set ELYSIA_LLM_TRACE_JSONL to a .jsonl file to record unified chat traces."}
    p = Path(path_s)
    if not p.is_file():
        return {"enabled": True, "path": str(p), "exists": False, "lines": []}
    lines = _tail_text_file(p, max_lines=max_lines)
    return {"enabled": True, "path": str(p), "exists": True, "line_count": len(lines), "lines": lines}


def build_ollama_runtime_bundle() -> Dict[str, Any]:
    """
    Local Ollama tag resolution + planner startup snapshot for operators.

    ``effective_model`` is what :func:`ollama_model_config.get_canonical_ollama_model` resolves to
    after env override and startup ``set_effective_ollama_model_from_planner`` (pool / same-base).
    """
    out: Dict[str, Any] = {
        "effective_model": "",
        "env_model_override": None,
        "config_file_primary": "",
        "config_pool_sample": [],
        "readiness_label": "unknown",
        "startup": {},
    }
    env_override = None
    for key in ("ELYSIA_OLLAMA_MODEL", "OLLAMA_MODEL"):
        v = (os.environ.get(key) or "").strip()
        if v:
            env_override = f"{key}={v}"
            break
    out["env_model_override"] = env_override

    decider_path = _REPO / "config" / "mistral_decider.json"
    if decider_path.is_file():
        try:
            dc = json.loads(decider_path.read_text(encoding="utf-8"))
            pool = dc.get("ollama_model_pool")
            if isinstance(pool, list) and pool:
                prim = [str(x).strip() for x in pool if str(x).strip()]
                out["config_pool_sample"] = prim[:8]
                out["config_file_primary"] = prim[0] if prim else ""
            else:
                out["config_file_primary"] = str(
                    dc.get("mistral_decider_model") or dc.get("ollama_model") or ""
                ).strip()
        except Exception as e:
            out["config_parse_error"] = str(e)[:200]

    try:
        from .ollama_model_config import get_canonical_ollama_model

        out["effective_model"] = get_canonical_ollama_model(log_once=False)
    except Exception as e:
        out["effective_model_error"] = str(e)[:200]

    try:
        from .planner_readiness import compute_readiness_label, maybe_refresh_model_install_if_stale, snapshot_startup_dict

        maybe_refresh_model_install_if_stale()
        snap = snapshot_startup_dict()
        tags_head = list(snap.get("installed_model_tags") or [])[:12]
        suggest = list(snap.get("suggested_close_tags") or [])[:6]
        out["startup"] = {
            "canonical_ollama_model": snap.get("canonical_ollama_model"),
            "exact_tag_match": snap.get("exact_tag_match"),
            "model_installed": snap.get("model_installed"),
            "ollama_reachable": snap.get("ollama_reachable"),
            "startup_health_ok": snap.get("startup_health_ok"),
            "startup_detail": (snap.get("startup_detail") or "")[:220],
            "planner_inference_ok": snap.get("planner_inference_ok"),
            "installed_model_tags_head": tags_head,
            "suggested_close_tags": suggest,
        }
        out["readiness_label"] = compute_readiness_label()
    except Exception as e:
        out["startup_error"] = str(e)[:240]

    cfg_pri = str(out.get("config_file_primary") or "").strip()
    eff = str(out.get("effective_model") or "").strip()
    if cfg_pri and eff and cfg_pri != eff and not env_override:
        out["resolution_note"] = (
            "Effective tag differs from config primary — likely pool/fallback resolution "
            "(see startup.installed_model_tags_head)."
        )
    else:
        out["resolution_note"] = ""

    return out


def build_parallel_brains_matrix() -> Dict[str, Any]:
    """
    Operator snapshot: unified chat try-order vs task class, multi_api_router picks,
    orchestration parallel pipeline label, and whether Elysia would drop to cloud-only fallback.
    """
    decider_path = _REPO / "config" / "mistral_decider.json"
    unified_router = True
    if decider_path.is_file():
        try:
            unified_router = bool(json.loads(decider_path.read_text(encoding="utf-8")).get("unified_chat_llm_router", True))
        except Exception:
            pass

    scenarios = [
        {"id": "operator_chat", "user_text": "Hello", "task_type": "conversation", "require_autonomy_safe": False},
        {"id": "reasoning_explicit", "user_text": "x", "task_type": "reasoning", "require_autonomy_safe": False},
        {"id": "structured_local_only", "user_text": "condense memory", "task_type": "context_compression", "require_autonomy_safe": False},
        {"id": "autonomy_safe_reasoning", "user_text": "plan next step", "task_type": "planning", "require_autonomy_safe": True},
    ]
    unified_snapshots: List[Dict[str, Any]] = []
    try:
        from .unified_llm_route import snapshot_unified_chat_provider_order

        for sc in scenarios:
            snap = snapshot_unified_chat_provider_order(
                user_text=sc["user_text"],
                task_type=sc.get("task_type"),
                registry=None,
                require_autonomy_safe_reasoning=bool(sc.get("require_autonomy_safe")),
                log_quota_skip=False,
            )
            unified_snapshots.append({"id": sc["id"], **snap})
    except Exception as e:
        unified_snapshots = [{"error": str(e)[:300]}]

    api_matrix: Dict[str, Any] = {}
    try:
        from .multi_api_router import select_best_api

        api_matrix["embedding"] = select_best_api(
            "embedding", registry=None, reserve_slot=False, log_decision=False, record_meter=False
        )
        api_matrix["reasoning"] = select_best_api(
            "reasoning", registry=None, reserve_slot=False, log_decision=False, record_meter=False
        )
        api_matrix["reasoning_autonomy_safe"] = select_best_api(
            "reasoning",
            registry=None,
            reserve_slot=False,
            log_decision=False,
            record_meter=False,
            require_autonomy_safe=True,
        )
        api_matrix["simple"] = select_best_api(
            "simple", registry=None, reserve_slot=False, log_decision=False, record_meter=False
        )
    except Exception as e:
        api_matrix = {"error": str(e)[:240]}

    return {
        "unified_chat_llm_router_enabled": unified_router,
        "cloud_only_when_router_disabled": not unified_router,
        "note": (
            "When unified_chat_llm_router is false, Elysia chat uses cloud-only fallback (no local Ollama ordering). "
            "Autonomy-safe workloads still refuse that path unless the unified router is on."
        ),
        "unified_route_scenarios": unified_snapshots,
        "multi_api_router": api_matrix,
        "orchestration_parallel_pipeline": {
            "pipeline_id": "parallel_compare_and_judge",
            "summary": "Fan-out to two adapters, DeterministicJudge compare, optional ModelJudge if inconclusive.",
        },
    }


def build_rag_log_bundle(*, max_lines: int = 35) -> Dict[str, Any]:
    needle = "selfbuild_rag"
    best: Optional[Tuple[Path, List[str]]] = None
    for cand in _elysia_unified_log_candidates():
        if not cand.is_file():
            continue
        lines = [ln for ln in _tail_text_file(cand, max_lines=400) if needle in ln]
        if not lines:
            continue
        tail = lines[-max_lines:]
        if best is None or len(tail) > len(best[1]):
            best = (cand, tail)
    if best is None:
        return {"lines": [], "note": "No recent log lines containing 'selfbuild_rag' (check elysia_unified.log)."}
    return {"source_log": str(best[0]), "lines": best[1]}


def build_mission_clarity_bundle() -> Dict[str, Any]:
    """
    Operator-facing mission focus (5 items), learning topics/keywords, and self-build corpus alignment.
    """
    ma_path = _REPO / "config" / "mission_autonomy.json"
    core = ""
    focus_missions: List[Dict[str, Any]] = []
    if ma_path.is_file():
        try:
            raw = json.loads(ma_path.read_text(encoding="utf-8"))
        except Exception:
            raw = {}
        core = str(raw.get("core_mission") or "").strip()
        camps = raw.get("campaigns") if isinstance(raw.get("campaigns"), list) else []
        optional_focus = raw.get("operator_focus_missions")
        if isinstance(optional_focus, list) and len(optional_focus) >= 1:
            for item in optional_focus[:5]:
                if isinstance(item, dict):
                    focus_missions.append(
                        {
                            "id": str(item.get("id") or "")[:80],
                            "title": str(item.get("title") or "")[:200],
                            "purpose": str(item.get("purpose") or item.get("one_line") or "")[:320],
                        }
                    )
                elif isinstance(item, str) and item.strip():
                    focus_missions.append({"id": "", "title": item.strip()[:200], "purpose": ""})
        else:
            sorted_camps = sorted(
                [c for c in camps if isinstance(c, dict)],
                key=lambda c: float(c.get("current_priority") or 0.0),
                reverse=True,
            )[:5]
            for c in sorted_camps:
                focus_missions.append(
                    {
                        "id": str(c.get("id") or "")[:80],
                        "title": str(c.get("title") or "")[:200],
                        "purpose": str(c.get("purpose") or "")[:320],
                    }
                )

    try:
        from .auto_learning import load_learning_config

        cfg = load_learning_config()
    except Exception as e:
        cfg = {}

    topics = [str(x) for x in (cfg.get("topics") or []) if str(x).strip()][:28]
    learning_target_terms = [str(x) for x in (cfg.get("learning_target_terms") or []) if str(x).strip()][:24]
    sb_topics = [str(x) for x in (cfg.get("local_ai_selfbuild_topics") or []) if str(x).strip()][:24]

    merged_kw = sorted(
        {str(x).strip().lower() for x in topics + learning_target_terms + sb_topics if str(x).strip()}
    )[:48]

    corpus_alignment: Dict[str, Any] = {}
    try:
        from .auto_learning import get_learned_storage_path
        from .local_ai_selfbuild_corpus import estimate_selfbuild_corpus_mission_alignment

        corpus_alignment = estimate_selfbuild_corpus_mission_alignment(get_learned_storage_path(), cfg)
    except Exception as e:
        corpus_alignment = {"error": str(e)[:240]}

    return {
        "core_mission_excerpt": core[:900] if core else "",
        "focus_missions": focus_missions[:5],
        "learning_topics": topics,
        "learning_target_terms": learning_target_terms,
        "local_ai_selfbuild_topics": sb_topics,
        "merged_guidance_keywords_sample": merged_kw[:36],
        "corpus_keyword_alignment": corpus_alignment,
    }


def _read_search_usage_counters() -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Local month counters for Brave / Tavily (same files as ``WebScoutAgent``)."""
    cfg_dir = _REPO / "config"
    brave_path = cfg_dir / "brave_search_usage.json"
    tavily_path = cfg_dir / "tavily_usage.json"
    brave_lim, tavily_lim = 2000, 1000
    bm = datetime.now(timezone.utc).strftime("%Y-%m")

    def _one(path: Path, lim: int) -> Dict[str, Any]:
        out: Dict[str, Any] = {
            "file": str(path),
            "file_exists": path.is_file(),
            "limit_this_month_estimate": lim,
            "requests_this_month": None,
            "current_month_label": bm,
            "remaining_estimate": None,
        }
        if not path.is_file():
            return out
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            m = str(raw.get("current_month") or "")[:16]
            n = raw.get("requests_this_month")
            try:
                n_int = max(0, int(n))
            except (TypeError, ValueError):
                n_int = 0
            if m != bm:
                n_int = 0
                out["note"] = "counter file stale month — showing 0 until next write"
            out["requests_this_month"] = n_int
            out["remaining_estimate"] = max(0, lim - n_int)
        except Exception as e:
            out["parse_error"] = str(e)[:160]
        return out

    return _one(brave_path, brave_lim), _one(tavily_path, tavily_lim)


def _web_reader_available_quick() -> bool:
    try:
        from .guardian_singleton import get_existing_guardian_core

        gc = get_existing_guardian_core()
        return bool(gc is not None and getattr(gc, "web_reader", None) is not None)
    except Exception:
        return False


def build_api_availability_matrix() -> Dict[str, Any]:
    """
    Best-effort view of configured keys, routing usability, search counters, env-only keys.
    Shown beside the gas meter (no secrets — booleans only).
    """
    providers: List[Dict[str, Any]] = []
    kk: Optional[Any] = None
    try:
        from .api_key_manager import get_api_key_manager

        mgr = get_api_key_manager()
        mgr.load_keys()
        kk = mgr.keys
    except Exception as e:
        providers.append({"id": "key_manager", "label": "APIKeyManager", "configured": False, "detail": str(e)[:200]})

    route: Dict[str, Any] = {}
    prov: Dict[str, Any] = {}
    try:
        from .cloud_api_state import provider_reasoning_truth_snapshot, usable_cloud_routing_snapshot

        route = usable_cloud_routing_snapshot(refresh=True)
        prov = provider_reasoning_truth_snapshot(refresh=True)
    except Exception:
        pass

    def _k(val: Optional[Any]) -> bool:
        return bool((val or "").strip()) if val is not None else False

    def _field(attr: str) -> Optional[Any]:
        if kk is None:
            return None
        return getattr(kk, attr, None)

    brave_u, tav_u = _read_search_usage_counters()
    wr_ok = _web_reader_available_quick()

    providers.extend(
        [
            {
                "id": "openai",
                "label": "OpenAI (ChatGPT API)",
                "key_configured": _k(_field("openai")) or bool((os.environ.get("OPENAI_API_KEY") or "").strip()),
                "routed_usable": bool((route.get("openai") or {}).get("usable_for_routing")),
                "routing_message": ((route.get("openai") or {}).get("routing_block_message")),
            },
            {
                "id": "openrouter",
                "label": "OpenRouter",
                "key_configured": _k(_field("openrouter")) or bool((os.environ.get("OPENROUTER_API_KEY") or "").strip()),
                "routed_usable": bool((prov.get("openrouter") or {}).get("usable")),
                "blocked_reason": (prov.get("openrouter") or {}).get("blocked_reason"),
            },
            {
                "id": "anthropic",
                "label": "Anthropic",
                "key_configured": _k(_field("anthropic")) or bool((os.environ.get("ANTHROPIC_API_KEY") or "").strip()),
                "routed_usable": bool((prov.get("anthropic") or {}).get("usable")),
                "blocked_reason": (prov.get("anthropic") or {}).get("blocked_reason"),
            },
            {
                "id": "huggingface",
                "label": "Hugging Face",
                "key_configured": _k(_field("huggingface"))
                or bool(
                    (os.environ.get("HUGGINGFACE_API_KEY") or "").strip()
                    or (os.environ.get("HF_TOKEN") or "").strip()
                    or (os.environ.get("HUGGINGFACE_HUB_TOKEN") or "").strip()
                ),
                "notes": "Hub discovery + Inference API paths (tokens from env/file).",
            },
            {
                "id": "cohere",
                "label": "Cohere",
                "key_configured": _k(_field("cohere")) or bool((os.environ.get("COHERE_API_KEY") or "").strip()),
                "notes": "Key loaded — dedicated Cohere client not wired in ``project_guardian`` core.",
            },
            {
                "id": "tavily",
                "label": "Tavily Search",
                "key_configured": _k(_field("tavily")) or bool((os.environ.get("TAVILY_API_KEY") or "").strip()),
                "web_reader_present": wr_ok,
                "usage_estimate": tav_u,
            },
            {
                "id": "brave",
                "label": "Brave Search",
                "key_configured": _k(_field("brave_search")) or bool((os.environ.get("BRAVE_SEARCH_API_KEY") or "").strip()),
                "web_reader_present": wr_ok,
                "usage_estimate": brave_u,
            },
        ]
    )

    providers.append(
        {
            "id": "alpha_vantage",
            "label": "Alpha Vantage",
            "key_configured": bool((os.environ.get("ALPHA_VANTAGE_API_KEY") or "").strip()),
            "notes": "Env only in this tree — dedicated market caller not wired in core HarvestEngine.",
        }
    )
    providers.append(
        {
            "id": "replicate",
            "label": "Replicate",
            "key_configured": bool((os.environ.get("REPLICATE_API_KEY") or "").strip()),
            "notes": "Env / key file mapped — SDK HTTP path not present in ``project_guardian`` core.",
        }
    )

    lines: List[str] = []
    lines.append("— configured APIs (no secrets) —")
    for row in providers:
        label = str(row.get("label") or row.get("id") or "?")
        parts = [label]
        if "key_configured" in row:
            parts.append("key✓" if row.get("key_configured") else "key✗")
        if row.get("routed_usable") is True:
            parts.append("route✓")
        elif row.get("routed_usable") is False:
            parts.append("route✗")
        ue = row.get("usage_estimate")
        if isinstance(ue, dict) and ue.get("requests_this_month") is not None:
            rem = ue.get("remaining_estimate")
            lim = ue.get("limit_this_month_estimate")
            parts.append(f"month≈{ue.get('requests_this_month')}/{lim} rem≈{rem}")
        rid = row.get("id")
        if row.get("web_reader_present") is False and rid in ("tavily", "brave"):
            parts.append("WebReader✗")
        elif row.get("web_reader_present") is True and rid in ("tavily", "brave"):
            parts.append("WebReader✓")
        if row.get("notes"):
            parts.append(("note:" + str(row["notes"]))[:140])
        if row.get("routing_message") and row.get("routed_usable") is False:
            parts.append(str(row["routing_message"])[:120])
        elif row.get("blocked_reason"):
            parts.append(str(row["blocked_reason"])[:80])
        lines.append(" ".join(parts))

    return {"providers": providers, "availability_lines": lines, "availability_text": "\n".join(lines)}


def build_api_gas_meter_bundle() -> Dict[str, Any]:
    """
    Session-scoped API usage (transport + router picks) and current availability snapshot.
    Counters reset on process restart; refresh Insights to update.
    """
    try:
        from .api_usage_meter import format_gas_meter_text, snapshot as meter_snapshot
        from .cloud_api_state import provider_reasoning_truth_snapshot, usable_cloud_routing_snapshot
        from .unified_api_budget import snapshot as budget_snapshot, surplus_opportunity_hint

        ms = meter_snapshot()
        prov = provider_reasoning_truth_snapshot(refresh=True)
        route = usable_cloud_routing_snapshot(refresh=True)
        bud = budget_snapshot()
        hint = surplus_opportunity_hint()
        av = build_api_availability_matrix()
        base_txt = format_gas_meter_text(ms)
        summary_txt = base_txt
        if isinstance(bud, dict) and bud.get("enabled"):
            rem = bud.get("remaining_units")
            rem_s = "∞" if rem is None else str(round(float(rem), 1))
            summary_txt += (
                "\nunified_budget: consumed≈"
                + str(bud.get("consumed_units"))
                + " / max="
                + str(bud.get("max_units_per_period"))
                + " rem≈"
                + rem_s
                + " period_sec="
                + str(bud.get("period_seconds"))
            )
        if isinstance(hint.get("suggested_actions"), list) and hint["suggested_actions"]:
            summary_txt += "\n" + str(hint["suggested_actions"][0])[:400]
        return {
            "meter": ms,
            "unified_budget": bud,
            "opportunistic_budget_hint": hint,
            "summary_text": summary_txt,
            "provider_truth": prov,
            "usable_cloud_routing": route,
            "api_availability": av,
            "availability_lines": av.get("availability_lines") or [],
            "availability_text": av.get("availability_text") or "",
        }
    except Exception as e:
        return {"error": str(e)[:240]}


def build_insights_overview(*, trace_lines: int = 40, rag_lines: int = 30) -> Dict[str, Any]:
    alignment = build_storage_alignment_bundle()
    hints = [
        "Set ELYSIA_LLM_TRACE_JSONL for per-completion JSON (Langfuse-style).",
        "Self-build artifacts live under learned/.../local_ai_selfbuild/.",
        "MCP: copy config examples, pip install mcp, enable allowlist for elysia_mcp_tool in chat.",
        "Mission clarity: tune topics in config/auto_learning.json; optional operator_focus_missions in mission_autonomy.json.",
    ]
    for w in alignment.get("warnings") or []:
        hints.insert(0, f"Storage: {w}")
    ollama_rt = build_ollama_runtime_bundle()
    su = ollama_rt.get("startup") or {}
    if su.get("ollama_reachable") and not su.get("model_installed"):
        hints.insert(
            0,
            "Ollama is reachable but the effective model tag is not installed — run `ollama pull <tag>` or fix mistral_decider.json pool.",
        )
    elif not su.get("ollama_reachable") and su:
        hints.insert(0, "Ollama unreachable — check OLLAMA_BASE_URL / service running.")
    return {
        "generated_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        "storage_alignment": alignment,
        "ollama_runtime": ollama_rt,
        "api_gas_meter": build_api_gas_meter_bundle(),
        "selfbuild": build_selfbuild_bundle(),
        "parallel_brains": build_parallel_brains_matrix(),
        "mission_clarity": build_mission_clarity_bundle(),
        "mcp": build_mcp_bundle(),
        "llm_traces": build_llm_trace_bundle(max_lines=trace_lines),
        "rag_unified_log": build_rag_log_bundle(max_lines=rag_lines),
        "hints": hints[:12],
    }
