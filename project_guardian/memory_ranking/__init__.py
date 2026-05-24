"""Canonical advisory memory ranking (does not replace ``MemoryCore`` / ``memory.py``).

Import from ``project_guardian.memory_ranking``. The module ``project_guardian.brain.memory_ranking``
re-exports the same API for backward compatibility only (no second implementation).
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from .ranking import (
    MemoryCompressionProposal,
    MemoryRankingConfig,
    MemoryRankingInput,
    MemoryRankingReport,
    MemoryScores,
    RankedMemory,
    build_ranking_report,
    clear_memory_ranking_config_cache,
    get_memory_ranking_config,
    memory_dict_to_input,
    optional_remember_extras_for_pipeline,
    propose_memory_compression,
    rank_memories,
    redact_memory_text,
    review_memory_scores_with_llm,
    score_memory,
    should_retain_full_memory,
    summarize_memory_for_compression,
)
from .visibility import (
    build_memory_ranking_summary,
    load_memory_ranking_visibility,
    summarize_compression_proposal,
    summarize_ranked_memory,
)

__all__ = [
    "MemoryCompressionProposal",
    "MemoryRankingConfig",
    "MemoryRankingInput",
    "MemoryRankingReport",
    "MemoryScores",
    "RankedMemory",
    "build_ranking_report",
    "build_memory_ranking_summary",
    "clear_memory_ranking_config_cache",
    "get_memory_ranking_config",
    "load_memory_ranking_config",
    "load_memory_ranking_visibility",
    "memory_dict_to_input",
    "optional_remember_extras_for_pipeline",
    "propose_compression_from_dicts",
    "propose_memory_compression",
    "rank_memories",
    "rank_memories_from_snippets",
    "redact_memory_text",
    "review_memory_scores_with_llm",
    "score_memory",
    "should_retain_full_memory",
    "summarize_memory_for_compression",
    "summarize_compression_proposal",
    "summarize_ranked_memory",
]


def load_memory_ranking_config() -> Dict[str, Any]:
    """Flat dict for diagnostics and legacy callers; ``deletion_enabled`` is always false in v1."""
    c = get_memory_ranking_config()
    return {
        "enabled": c.enabled,
        "dry_run": c.dry_run,
        "deletion_enabled": False,
        "allow_delete_proposals": c.allow_delete_proposals,
        "max_raw_memory_chars": c.max_raw_memory_chars,
        "compression_threshold": c.compression_threshold,
        "archive_threshold": c.archive_threshold,
        "delete_threshold": c.delete_threshold,
        "weights": dict(c.weights),
    }


def propose_compression_from_dicts(
    memories: List[Dict[str, Any]],
    *,
    cfg: Optional[MemoryRankingConfig] = None,
    current_goal_text: str = "",
    context: Optional[Dict[str, Any]] = None,
) -> MemoryRankingReport:
    """Rank dict-shaped memory rows and return proposals (read-only)."""
    from . import ranking as _rk

    ctx = dict(context or {})
    c = cfg or get_memory_ranking_config()
    now = _rk._parse_iso(str(ctx["now"])) if ctx.get("now") else None
    items = [memory_dict_to_input(m, i) for i, m in enumerate(memories)]
    return build_ranking_report(items, c, current_goal_text=current_goal_text, now=now)


def rank_memories_from_snippets(
    snippets: List[str],
    cfg: MemoryRankingConfig,
    *,
    current_goal_text: str = "",
) -> List[RankedMemory]:
    """Helper for BrainPipeline: score plain-string recall snippets."""
    items = [
        MemoryRankingInput(memory_id=f"snippet-{i}", text=str(s or ""), length_chars=len(s or ""))
        for i, s in enumerate(snippets)
    ]
    return rank_memories(items, cfg, current_goal_text=current_goal_text)
