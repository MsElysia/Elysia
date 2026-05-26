# project_guardian/brain/memory_ranking.py
"""Backward compatibility: re-exports the canonical ``project_guardian.memory_ranking`` API.

Prefer ``from project_guardian.memory_ranking import ...`` in new code.
"""

from project_guardian.memory_ranking import (
    MemoryCompressionProposal,
    MemoryRankingConfig,
    MemoryRankingInput,
    MemoryRankingReport,
    MemoryScores,
    RankedMemory,
    build_ranking_report,
    clear_memory_ranking_config_cache,
    get_memory_ranking_config,
    load_memory_ranking_config,
    memory_dict_to_input,
    optional_remember_extras_for_pipeline,
    propose_compression_from_dicts,
    propose_memory_compression,
    rank_memories,
    rank_memories_from_snippets,
    redact_memory_text,
    review_memory_scores_with_llm,
    score_memory,
    should_retain_full_memory,
    summarize_memory_for_compression,
)

__all__ = [
    "MemoryCompressionProposal",
    "MemoryRankingConfig",
    "MemoryRankingInput",
    "MemoryRankingReport",
    "MemoryScores",
    "RankedMemory",
    "build_ranking_report",
    "clear_memory_ranking_config_cache",
    "get_memory_ranking_config",
    "load_memory_ranking_config",
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
]
