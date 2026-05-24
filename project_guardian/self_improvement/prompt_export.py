# project_guardian/self_improvement/prompt_export.py
"""Review-only export of self-improvement proposals as copyable Cursor/Codex prompts."""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Tuple, Union

from project_guardian.brain.trace_visibility import redact_sensitive
from project_guardian.self_improvement.proposal_queue import (
    SelfImprovementProposal,
    sanitize_proposal,
)

ALLOWED_TARGETS = frozenset({"cursor", "codex"})

_TRACE_BLOCK_KEYS = frozenset(
    {
        "think_decide_act_trace",
        "tda_trace",
        "raw_trace",
        "trace",
        "transitions",
        "execution",
        "run_context",
        "unified_export",
        "brain_trace",
    }
)

_SAFETY_CONSTRAINTS: Tuple[str, ...] = (
    "Do not wire autonomy or enable autonomous execution loops.",
    "Do not enable live execution unless the operator explicitly requests it.",
    "Do not apply unrelated changes or drive-by refactors.",
    "Run relevant tests for the touched areas and report results.",
    "Provide a clear implementation report when finished.",
)

_DELIVERABLES: Tuple[str, ...] = (
    "Files changed (with brief purpose per file).",
    "Tests added or changed.",
    "Commands run and their pass/fail results.",
    "Failures, blockers, or incomplete items.",
    "Safety confirmation (no autonomy/live execution enabled).",
)

_MAX_PROMPT_CHARS = 48_000


def normalize_target(target: str) -> str:
    t = str(target or "cursor").strip().lower()
    if t not in ALLOWED_TARGETS:
        raise ValueError(f"unknown_target:{t}")
    return t


def sanitize_prompt_text(text: str, *, max_len: int = 8000) -> str:
    """Redact secrets and normalize text for inclusion in an export prompt."""
    if text is None:
        return ""
    s = str(redact_sensitive(str(text)))
    s = s.replace("\x00", "")
    s = re.sub(r"\r\n?", "\n", s)
    return s.strip()[:max_len]


def _raw_evidence(proposal: Union[SelfImprovementProposal, Dict[str, Any]]) -> Dict[str, Any]:
    if isinstance(proposal, SelfImprovementProposal):
        ev = proposal.evidence
    elif isinstance(proposal, dict):
        ev = proposal.get("evidence")
    else:
        ev = None
    return ev if isinstance(ev, dict) else {}


def _proposal_as_dict(
    proposal: Union[SelfImprovementProposal, Dict[str, Any]],
) -> Dict[str, Any]:
    if isinstance(proposal, SelfImprovementProposal):
        return sanitize_proposal(proposal, for_api=True)
    if isinstance(proposal, dict):
        return dict(proposal)
    raise TypeError("proposal must be SelfImprovementProposal or dict")


def _trace_fields_were_stripped(proposal: Union[SelfImprovementProposal, Dict[str, Any]]) -> bool:
    return any(str(k).lower() in _TRACE_BLOCK_KEYS for k in _raw_evidence(proposal))


def _format_evidence_for_export(evidence: Any) -> str:
    if not isinstance(evidence, dict):
        return sanitize_prompt_text(str(evidence or ""), max_len=4000)
    clean: Dict[str, Any] = {}
    for k, v in evidence.items():
        key = str(k)
        if key.lower() in _TRACE_BLOCK_KEYS:
            continue
        if isinstance(v, dict) and any(str(x).lower() in _TRACE_BLOCK_KEYS for x in v):
            continue
        if isinstance(v, str):
            clean[key] = sanitize_prompt_text(v, max_len=2000)
        elif isinstance(v, (int, float, bool)) or v is None:
            clean[key] = v
        elif isinstance(v, list):
            clean[key] = [
                sanitize_prompt_text(str(x), max_len=500) if isinstance(x, str) else x
                for x in v[:40]
            ]
    if not clean:
        return "(no exportable evidence — raw traces omitted)"
    return sanitize_prompt_text(json.dumps(clean, indent=2, ensure_ascii=False), max_len=6000)


def _format_file_list(files: Any) -> str:
    if not files:
        return "(none listed)"
    lines = [sanitize_prompt_text(str(f), max_len=500) for f in list(files)[:80]]
    return "\n".join(f"- {line}" for line in lines if line)


def _collect_warnings(d: Dict[str, Any], *, stripped_trace_keys: bool) -> List[str]:
    warnings: List[str] = []
    if stripped_trace_keys:
        warnings.append("Raw Brain/TDA trace fields were omitted from this export.")
    risk = str(d.get("risk_level") or "").lower()
    if risk in ("high", "blocked"):
        warnings.append(f"Proposal risk_level is {risk!r}; review carefully before implementing.")
    blocked = sanitize_prompt_text(str(d.get("blocked_reason") or ""), max_len=500)
    if blocked:
        warnings.append(f"blocked_reason: {blocked}")
    if d.get("requires_human_review"):
        warnings.append("requires_human_review is true.")
    return warnings


def build_proposal_prompt(
    proposal: Union[SelfImprovementProposal, Dict[str, Any]],
    *,
    target: str = "cursor",
) -> str:
    """Build a copyable implementation prompt (text only; no execution)."""
    tgt = normalize_target(target)
    d = _proposal_as_dict(proposal)

    title = sanitize_prompt_text(str(d.get("title") or "Untitled proposal"), max_len=500)
    problem = sanitize_prompt_text(str(d.get("problem_summary") or ""), max_len=8000)
    proposed = sanitize_prompt_text(str(d.get("proposed_change") or ""), max_len=8000)
    benefit = sanitize_prompt_text(str(d.get("expected_benefit") or ""), max_len=4000)
    evidence = _format_evidence_for_export(d.get("evidence"))
    files = _format_file_list(d.get("affected_files"))
    risk = sanitize_prompt_text(str(d.get("risk_level") or "unknown"), max_len=64)
    priority = d.get("priority_score", "")
    category = sanitize_prompt_text(str(d.get("category") or ""), max_len=64)
    proposal_id = sanitize_prompt_text(str(d.get("proposal_id") or ""), max_len=128)

    lines: List[str] = [
        f"# Self-improvement proposal: {title}",
        "",
        f"**Proposal ID:** `{proposal_id}`",
        f"**Category:** {category or 'unknown'}",
        f"**Risk level:** {risk}",
        f"**Priority score:** {priority}",
        "",
        "## Problem summary",
        problem or "(not provided)",
        "",
        "## Evidence",
        evidence,
        "",
        "## Proposed change",
        proposed or "(not provided)",
        "",
        "## Expected benefit",
        benefit or "(not provided)",
        "",
        "## Affected files",
        files,
        "",
        "## Constraints",
    ]
    for c in _SAFETY_CONSTRAINTS:
        lines.append(f"- {c}")

    lines.extend(["", "## Deliverables (implementation report)"])
    for item in _DELIVERABLES:
        lines.append(f"- {item}")

    if tgt == "cursor":
        lines.extend(
            [
                "",
                "## Cursor agent instructions",
                "You are working in the **Elysia / Project Guardian** monorepo.",
                "Read surrounding code and match existing patterns before changing anything.",
                "Consider related modules, config under `config/`, and existing tests under `project_guardian/tests/`.",
                "Prefer the smallest change that satisfies the proposed improvement.",
                "After implementation, run targeted pytest for affected areas and "
                "`python scripts/run_safe_stack_smoke_tests.py` when the safe stack may be impacted.",
            ]
        )
    else:
        lines.extend(
            [
                "",
                "## Codex agent instructions",
                "Implement the proposed change with a **test-driven, minimal-diff** approach.",
                "Add or update pytest under `project_guardian/tests/` for new behavior.",
                "Suggested verification:",
                "```",
                "python -m pytest project_guardian/tests/<relevant_test_file>.py -q",
                "python scripts/run_safe_stack_smoke_tests.py",
                "```",
                "Do not expand scope beyond this proposal.",
            ]
        )

    lines.extend(
        [
            "",
            "---",
            "_Export only. This prompt does not apply code, run shell commands, or mutate the repo._",
        ]
    )

    prompt = "\n".join(lines)
    if len(prompt) > _MAX_PROMPT_CHARS:
        prompt = prompt[:_MAX_PROMPT_CHARS] + "\n\n[truncated for export safety]"
    return prompt


def proposal_prompt_to_dict(
    proposal: Union[SelfImprovementProposal, Dict[str, Any]],
    *,
    target: str = "cursor",
) -> Dict[str, Any]:
    """API-shaped export payload for a single proposal."""
    tgt = normalize_target(target)
    d = _proposal_as_dict(proposal)
    stripped_trace = _trace_fields_were_stripped(proposal)
    warnings = _collect_warnings(d, stripped_trace_keys=stripped_trace)
    prompt = build_proposal_prompt(d, target=tgt)

    # Post-check: no raw trace blobs in final prompt text
    lower = prompt.lower()
    for forbidden in ("think_decide_act_trace", '"tda_trace"', "raw_trace"):
        if forbidden in lower:
            warnings.append(f"Export scrubbed forbidden trace token: {forbidden}")

    return {
        "proposal_id": str(d.get("proposal_id") or ""),
        "target": tgt,
        "prompt": prompt,
        "copy_safe": True,
        "warnings": warnings,
    }
