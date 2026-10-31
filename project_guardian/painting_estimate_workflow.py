"""Painting-estimate compatibility adapter.

Reusable composition lives in capability_composition.py. This module preserves
the prior import surface and painting-specific domain template defaults.
"""
from __future__ import annotations

from project_guardian.capability_composition import (  # noqa: F401
    CAPABILITY_ASSEMBLE,
    CAPABILITY_DRAFT,
    DOMAIN_TEMPLATES,
    CompositionError as EstimateWorkflowError,
    assemble_estimate_subtotal,
    build_cross_step_link,
    build_draft_user_payload,
    collect_verified_links,
    draft_system_prompt,
    extract_amount_usd_from_required,
    mark_dependent_steps_stale,
    money_str,
    parse_model_draft,
    resolve_upstream_amount,
    verify_draft_amounts,
)

# Domain configuration only — not orchestration.
MISSING_COST_CATEGORIES = DOMAIN_TEMPLATES["painting_estimate"]["missing_categories"]
SCOPE_ASSEMBLE = CAPABILITY_ASSEMBLE
SCOPE_DRAFT = CAPABILITY_DRAFT
