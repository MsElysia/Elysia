"""Deterministic painting-estimate assembly and draft verification.

Cross-step evidence flows from verified document-search and calculator receipts.
Financial arithmetic is Decimal-only. Model drafts are post-checked; they never
certify their own figures.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
from datetime import datetime, timezone
import hashlib
import json
import re
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple


CAPABILITY_ASSEMBLE = "estimate.assemble"
CAPABILITY_DRAFT = "estimate.draft"
SCOPE_ASSEMBLE = "estimate.assemble"
SCOPE_DRAFT = "estimate.draft"

MISSING_COST_CATEGORIES = (
    "markup / profit",
    "taxes",
    "overhead",
    "equipment rental",
    "contingency",
    "permits / fees",
)

_MONEY_RE = re.compile(r"(?<![0-9.])([0-9]{1,7}(?:\.[0-9]{1,2})?)(?![0-9])")
_DRAFT_BANNER = "DRAFT / NOT APPROVED FOR CUSTOMER DELIVERY"


class EstimateWorkflowError(ValueError):
    pass


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _dec(value: Any) -> Decimal:
    try:
        if isinstance(value, Decimal):
            d = value
        elif isinstance(value, (int, float)) and not isinstance(value, bool):
            d = Decimal(str(value))
        elif isinstance(value, str) and re.fullmatch(
            r"[0-9]{1,7}(?:\.[0-9]{1,2})?", value.strip()
        ):
            d = Decimal(value.strip())
        else:
            raise EstimateWorkflowError("invalid USD amount")
    except (InvalidOperation, EstimateWorkflowError) as exc:
        raise EstimateWorkflowError("invalid USD amount") from exc
    if d < 0 or d >= Decimal("10000000"):
        raise EstimateWorkflowError("USD amount out of range")
    return d.quantize(Decimal("0.01"))


def money_str(value: Decimal) -> str:
    return format(value.quantize(Decimal("0.01")), "f")


def extract_amount_usd_from_required(required_substring: Optional[str]) -> Optional[str]:
    """When the bind criteria pin an exact money token, treat it as the amount."""
    if not isinstance(required_substring, str):
        return None
    token = required_substring.strip()
    if re.fullmatch(r"[0-9]{1,7}(?:\.[0-9]{1,2})?", token):
        return money_str(_dec(token))
    return None


def build_cross_step_link(
    *,
    conversation_id: str,
    step: Mapping[str, Any],
    checkpoint_revision: int,
) -> Dict[str, Any]:
    """Small source-linked result representation for downstream steps."""
    ref = step.get("result_reference") if isinstance(step.get("result_reference"), dict) else {}
    return {
        "conversation_id": conversation_id,
        "step_id": step.get("step_id"),
        "capability": step.get("capability"),
        "execution_receipt_id": step.get("execution_receipt_id") or ref.get("execution_id"),
        "result_type": ref.get("result_type") or step.get("expected_result_type"),
        "result_value": ref.get("amount_usd") or ref.get("result"),
        "amount_usd": ref.get("amount_usd") or (
            ref.get("result") if step.get("capability") == "calculator.labor" else None
        ),
        "source_reference": ref.get("top_relative_path") or ref.get("folder_label"),
        "source_fingerprint": ref.get("folder_fingerprint") or ref.get("source_sha256"),
        "verification_state": step.get("verification_status"),
        "checkpoint_revision": checkpoint_revision,
        "stale": bool(ref.get("stale")),
    }


def collect_verified_links(
    conversation_id: str,
    steps: Sequence[Mapping[str, Any]],
    *,
    checkpoint_revision: int,
) -> List[Dict[str, Any]]:
    links = []
    for step in steps:
        if step.get("status") != "completed":
            continue
        if step.get("verification_status") != "verified":
            continue
        links.append(
            build_cross_step_link(
                conversation_id=conversation_id,
                step=step,
                checkpoint_revision=checkpoint_revision,
            )
        )
    return links


def resolve_upstream_amount(
    steps: Sequence[Mapping[str, Any]],
    step_id: str,
    *,
    expected_capability: str,
) -> Tuple[str, Dict[str, Any]]:
    target = next((s for s in steps if s.get("step_id") == step_id), None)
    if target is None:
        raise EstimateWorkflowError(f"upstream step not found: {step_id}")
    if target.get("status") != "completed":
        raise EstimateWorkflowError(f"upstream step is not completed: {step_id}")
    if target.get("verification_status") != "verified":
        raise EstimateWorkflowError(f"upstream step is not verified: {step_id}")
    if target.get("capability") != expected_capability:
        raise EstimateWorkflowError(
            f"upstream step capability mismatch: expected {expected_capability}"
        )
    ref = target.get("result_reference") if isinstance(target.get("result_reference"), dict) else {}
    if ref.get("stale"):
        raise EstimateWorkflowError(
            f"upstream step result is stale and must be reverified: {step_id}"
        )
    amount = ref.get("amount_usd")
    if amount is None and expected_capability == "calculator.labor":
        amount = ref.get("result")
    if amount is None:
        raise EstimateWorkflowError(
            f"upstream step has no verified amount_usd: {step_id}"
        )
    return money_str(_dec(amount)), {
        "step_id": step_id,
        "capability": expected_capability,
        "execution_receipt_id": target.get("execution_receipt_id") or ref.get("execution_id"),
        "amount_usd": money_str(_dec(amount)),
        "source_reference": ref.get("top_relative_path") or ref.get("folder_label"),
        "source_fingerprint": ref.get("folder_fingerprint"),
        "verification_state": "verified",
    }


def assemble_estimate_subtotal(
    *,
    material_usd: str,
    labor_usd: str,
    material_link: Mapping[str, Any],
    labor_link: Mapping[str, Any],
) -> Dict[str, Any]:
    """Deterministic materials + labor subtotal. Not a customer bid."""
    material = _dec(material_usd)
    labor = _dec(labor_usd)
    subtotal = (material + labor).quantize(Decimal("0.01"))
    return {
        "ok": True,
        "capability": CAPABILITY_ASSEMBLE,
        "currency": "USD",
        "components": {
            "materials": money_str(material),
            "labor": money_str(labor),
            "materials_plus_labor_subtotal": money_str(subtotal),
        },
        "subtotal_usd": money_str(subtotal),
        "label": "materials + labor subtotal (not a final customer bid)",
        "missing_cost_categories": list(MISSING_COST_CATEGORIES),
        "inputs": {
            "material": dict(material_link),
            "labor": dict(labor_link),
        },
        "verification_rule": "deterministic_decimal_sum",
        "created_utc": _utc_now(),
    }


def draft_system_prompt() -> str:
    return (
        "You prepare a fictional painting-estimate DRAFT from verified host numbers only. "
        f"Every draft must begin with the exact banner line: {_DRAFT_BANNER}. "
        "Use only the provided verified amounts and source references. "
        "Do not invent markup, taxes, overhead, contingency, or other costs; list them as missing. "
        "Do not change verified figures. "
        'Return JSON {"draft":"..."} only.'
    )


def build_draft_user_payload(
    *,
    objective: str,
    assembled: Mapping[str, Any],
    scope_notes: str = "",
) -> Dict[str, Any]:
    return {
        "objective": objective,
        "verified_components": assembled.get("components"),
        "subtotal_usd": assembled.get("subtotal_usd"),
        "subtotal_label": assembled.get("label"),
        "missing_cost_categories": assembled.get("missing_cost_categories"),
        "material_source": (assembled.get("inputs") or {}).get("material"),
        "labor_source": (assembled.get("inputs") or {}).get("labor"),
        "scope_notes": scope_notes or "Limited to supported inputs only.",
        "required_banner": _DRAFT_BANNER,
        "instructions": (
            "Include project description, scope limited to supported inputs, materials with "
            "source filename if available, labor assumptions summary pointing at verified total, "
            "subtotal, missing cost categories, assumptions requiring operator review, and sources."
        ),
    }


def verify_draft_amounts(
    draft: str,
    *,
    materials_usd: str,
    labor_usd: str,
    subtotal_usd: str,
) -> Dict[str, Any]:
    """Reject drafts that omit required verified figures or invent conflicting totals."""
    if not isinstance(draft, str) or not draft.strip():
        raise EstimateWorkflowError("draft is empty")
    text = draft.strip()
    if _DRAFT_BANNER not in text:
        raise EstimateWorkflowError("draft missing required DRAFT banner")
    def _present(amount: str) -> bool:
        if amount in text:
            return True
        # Accept whole-dollar forms without trailing .00
        if amount.endswith(".00") and amount[:-3] in text:
            return True
        return False

    needed = {
        "materials": money_str(_dec(materials_usd)),
        "labor": money_str(_dec(labor_usd)),
        "subtotal": money_str(_dec(subtotal_usd)),
    }
    missing = [k for k, v in needed.items() if not _present(v)]
    if missing:
        raise EstimateWorkflowError(
            "draft omitted verified amount(s): " + ", ".join(missing)
        )
    # Flag invented money tokens that are not the verified three (allow formatting variants).
    allowed = {needed["materials"], needed["labor"], needed["subtotal"]}
    # Also allow integer forms without trailing .00
    for v in list(allowed):
        if v.endswith(".00"):
            allowed.add(v[:-3])
    invented = []
    allowed_norms = {money_str(_dec(a)) for a in allowed}
    for token in _MONEY_RE.findall(text.replace(",", "")):
        norm = money_str(_dec(token))
        if norm in allowed_norms:
            continue
        # Allow small operational counts/rates (painters, days, hours, hourly rate).
        # Flag only large currency-like inventions that are not verified totals.
        if Decimal(token) < Decimal("100"):
            continue
        invented.append(norm)
    invented = sorted(set(invented))
    if invented:
        raise EstimateWorkflowError(
            "draft introduced unsupported figure(s): " + ", ".join(invented[:8])
        )
    return {
        "ok": True,
        "verified_amounts_present": needed,
        "draft_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "char_count": len(text),
    }


def parse_model_draft(raw: str) -> str:
    cleaned = (raw or "").strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    try:
        parsed = json.loads(cleaned)
    except (ValueError, TypeError) as exc:
        raise EstimateWorkflowError("model did not return JSON draft") from exc
    if not isinstance(parsed, dict) or not isinstance(parsed.get("draft"), str):
        raise EstimateWorkflowError("model draft payload invalid")
    draft = parsed["draft"].strip()
    if not draft or len(draft) > 8000:
        raise EstimateWorkflowError("model draft length invalid")
    return draft


def mark_dependent_steps_stale(
    steps: List[Dict[str, Any]],
    *,
    changed_step_id: str,
) -> List[str]:
    """When an upstream verified step is reopened/changed, stale assemble/draft dependents."""
    stale_ids: List[str] = []
    for step in steps:
        if step.get("capability") not in {CAPABILITY_ASSEMBLE, CAPABILITY_DRAFT}:
            continue
        args = step.get("arguments") if isinstance(step.get("arguments"), dict) else {}
        depends = {
            args.get("material_step_id"),
            args.get("labor_step_id"),
            args.get("assemble_step_id"),
        }
        if changed_step_id not in depends:
            continue
        ref = step.get("result_reference")
        if not isinstance(ref, dict):
            ref = {}
        ref = dict(ref)
        ref["stale"] = True
        ref["stale_reason"] = f"upstream changed: {changed_step_id}"
        step["result_reference"] = ref
        if step.get("status") == "completed":
            step["verification_status"] = "failed"
            step["last_failure_category"] = "upstream_stale"
        stale_ids.append(str(step.get("step_id")))
    return stale_ids
