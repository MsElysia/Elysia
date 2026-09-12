"""Heuristics for tuning context_pipeline.json from runtime counters (see scripts/)."""
from __future__ import annotations

import json
from typing import Any, Dict, List, Tuple


def _num(x: Any, default: float = 0.0) -> float:
    try:
        return float(x)
    except (TypeError, ValueError):
        return default


def _int(x: Any, default: int = 0) -> int:
    try:
        return int(x)
    except (TypeError, ValueError):
        return default


def recommend_context_pipeline_patch(
    cp: Dict[str, Any],
    cfg: Dict[str, Any],
    *,
    min_cycles: int = 8,
) -> Tuple[List[str], Dict[str, Any]]:
    """
    Given context_pipeline_runtime_status (cp) and current context_pipeline config (cfg),
    return (notes, patch) where patch only contains keys safe to auto-merge.
    """
    notes: List[str] = []
    patch: Dict[str, Any] = {}

    counters = cp.get("counters") if isinstance(cp.get("counters"), dict) else {}
    cycles = _int(counters.get("cycles"), 0)
    fallback_rate = _num(cp.get("fallback_rate"), 0.0)
    timeout_rate = _num(cp.get("timeout_rate"), 0.0)

    last = cp.get("last_packet_status") if isinstance(cp.get("last_packet_status"), dict) else {}
    notes.append(f"cycles={cycles} fallback_rate={fallback_rate:.4f} timeout_rate={timeout_rate:.4f}")
    if last:
        notes.append(
            "last_packet_status: "
            + json.dumps(last, separators=(",", ":"), ensure_ascii=False)[:240]
        )

    if cycles < min_cycles:
        notes.append(
            f"Not enough decision cycles yet (need >= {min_cycles}). "
            "Let the loop run longer, then re-run this script."
        )
        return notes, patch

    loc = _num(cfg.get("local_timeout_sec"), 60.0)
    emb = _num(cfg.get("embedding_http_timeout_sec"), 30.0)
    online = _num(cfg.get("online_timeout_sec"), 75.0)

    ollama_err = _int(counters.get("error_ollama_unavailable"), 0)
    inv = _int(counters.get("error_invalid_packet"), 0)
    other = _int(counters.get("error_other"), 0)
    timeouts = _int(counters.get("error_timeout"), 0)

    if ollama_err > 0 and ollama_err >= max(3, cycles // 4):
        notes.append(
            "Many 'ollama_unavailable' outcomes: start/repair Ollama and the local model; "
            "raising timeouts alone usually will not fix this."
        )

    if timeout_rate >= 0.22:
        bump = 35.0
        new_loc = min(120.0, loc + bump)
        if new_loc > loc + 0.5:
            patch["local_timeout_sec"] = int(round(new_loc))
            notes.append(
                f"High timeout_rate ({timeout_rate:.2%}): propose local_timeout_sec "
                f"{int(loc)} -> {patch['local_timeout_sec']} (cap 120)."
            )
        if emb < 45.0 and timeouts > 0:
            patch["embedding_http_timeout_sec"] = int(min(60.0, max(emb, 40.0)))
            notes.append(
                f"Timeouts seen with embedding_http_timeout_sec={int(emb)}; "
                f"propose -> {patch['embedding_http_timeout_sec']}."
            )
    elif timeout_rate >= 0.10:
        bump = 18.0
        new_loc = min(120.0, loc + bump)
        if new_loc > loc + 0.5:
            patch["local_timeout_sec"] = int(round(new_loc))
            notes.append(
                f"Elevated timeout_rate ({timeout_rate:.2%}): propose local_timeout_sec "
                f"{int(loc)} -> {patch['local_timeout_sec']}."
            )

    if inv >= max(2, cycles // 5) and "local_timeout_sec" not in patch:
        notes.append(
            "Several 'invalid_packet' errors: check Ollama model output / logs; "
            "reducing retrieval size slightly can help (max_total_retrieved_items, caps)."
        )

    if other >= max(2, cycles // 5) and timeout_rate < 0.05:
        notes.append(
            "Non-timeout 'other' errors present: inspect logs for [PromptPacket] and pipeline_ms=."
        )

    if fallback_rate <= 0.05 and timeout_rate <= 0.02 and cycles >= 30:
        notes.append(
            "Telemetry looks healthy (low fallback and timeout). No timeout increases needed; "
            "optional: trim local_timeout_sec slightly for snappiness only if you measure latency."
        )

    if patch.get("local_timeout_sec") and online < patch["local_timeout_sec"] + 10:
        patch["online_timeout_sec"] = int(min(180.0, patch["local_timeout_sec"] + 25))
        notes.append(
            f"Align online_timeout_sec with longer local build: propose -> {patch['online_timeout_sec']}."
        )

    if not patch and cycles >= min_cycles:
        notes.append("No automatic JSON patch proposed; review notes above.")

    return notes, patch
