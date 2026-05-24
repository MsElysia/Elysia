# project_guardian/self_improvement
"""Human-in-the-loop self-improvement proposals (no autonomous code mutation)."""

from __future__ import annotations

from .prompt_export import (
    ALLOWED_TARGETS,
    build_proposal_prompt,
    normalize_target,
    proposal_prompt_to_dict,
    sanitize_prompt_text,
)
from .proposal_queue import (
    SelfImprovementProposal,
    append_legacy_brain_row,
    append_proposal,
    count_proposals_for_trace,
    create_proposal,
    create_proposal_from_brain_learning,
    get_default_proposal_queue,
    get_proposal,
    list_proposals,
    load_latest_proposals,
    proposal_from_dict,
    proposal_to_dict,
    rank_proposals,
    reset_default_proposal_queue_for_tests,
    sanitize_proposal,
    update_proposal_status,
)

__all__ = [
    "ALLOWED_TARGETS",
    "SelfImprovementProposal",
    "build_proposal_prompt",
    "normalize_target",
    "proposal_prompt_to_dict",
    "sanitize_prompt_text",
    "append_legacy_brain_row",
    "append_proposal",
    "count_proposals_for_trace",
    "create_proposal",
    "create_proposal_from_brain_learning",
    "get_default_proposal_queue",
    "get_proposal",
    "list_proposals",
    "load_latest_proposals",
    "proposal_from_dict",
    "proposal_to_dict",
    "rank_proposals",
    "reset_default_proposal_queue_for_tests",
    "sanitize_proposal",
    "update_proposal_status",
]
