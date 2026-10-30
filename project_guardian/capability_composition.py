"""General-purpose capability composition: aggregate, synthesize, plan validation.

Domain-specific labels (painting, events, research) are optional configuration,
not hardcoded workflow modules. Verified upstream receipts remain authoritative.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
from datetime import datetime, timezone
import hashlib
import json
import re
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple


CAPABILITY_AGGREGATE = "compose.aggregate_usd"
CAPABILITY_SYNTHESIZE = "compose.synthesize"
CAPABILITY_EXTRACT = "compose.extract_fields"
CAPABILITY_EXTRACT_RECORDS = "compose.extract_records"
# Compatibility aliases retained for the painting-estimate adapter.
CAPABILITY_ASSEMBLE = "estimate.assemble"
CAPABILITY_DRAFT = "estimate.draft"

COMPOSITION_CAPABILITIES = frozenset(
    {
        CAPABILITY_AGGREGATE,
        CAPABILITY_SYNTHESIZE,
        CAPABILITY_EXTRACT,
        CAPABILITY_EXTRACT_RECORDS,
        CAPABILITY_ASSEMBLE,
        CAPABILITY_DRAFT,
    }
)

DEFAULT_DRAFT_BANNER = "DRAFT / NOT APPROVED FOR CUSTOMER DELIVERY"
_MONEY_RE = re.compile(r"(?<![0-9.])([0-9]{1,7}(?:\.[0-9]{1,2})?)(?![0-9])")
_STEP_ID_RE = re.compile(r"^step_[a-f0-9]{12}$")

# Optional domain templates — configuration, not orchestration.
DOMAIN_TEMPLATES: Dict[str, Dict[str, Any]] = {
    "painting_estimate": {
        "missing_categories": (
            "markup / profit",
            "taxes",
            "overhead",
            "equipment rental",
            "contingency",
            "permits / fees",
        ),
        "bundle_label": "materials + labor subtotal (not a final customer bid)",
        "banner": DEFAULT_DRAFT_BANNER,
        "draft_mode": "draft",
    },
    "event_budget": {
        "missing_categories": (
            "contingency",
            "taxes",
            "gratuity",
            "insurance",
            "overtime staffing",
        ),
        "bundle_label": "event line-item subtotal (not a final approved budget)",
        "banner": DEFAULT_DRAFT_BANNER,
        "draft_mode": "summary",
    },
    "research_comparison": {
        "missing_categories": (),
        "bundle_label": None,
        "banner": "COMPARISON DRAFT / SOURCE-GROUNDED ONLY",
        "draft_mode": "comparison",
    },
}


class CompositionError(ValueError):
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
            raise CompositionError("invalid USD amount")
    except (InvalidOperation, CompositionError) as exc:
        raise CompositionError("invalid USD amount") from exc
    if d < 0 or d >= Decimal("10000000"):
        raise CompositionError("USD amount out of range")
    return d.quantize(Decimal("0.01"))


def money_str(value: Decimal) -> str:
    return format(value.quantize(Decimal("0.01")), "f")


def extract_amount_usd_from_required(required_substring: Optional[str]) -> Optional[str]:
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
    ref = step.get("result_reference") if isinstance(step.get("result_reference"), dict) else {}
    amount = ref.get("amount_usd")
    if amount is None and step.get("capability") == "calculator.labor":
        amount = ref.get("result")
    return {
        "conversation_id": conversation_id,
        "step_id": step.get("step_id"),
        "capability": step.get("capability"),
        "execution_receipt_id": step.get("execution_receipt_id") or ref.get("execution_id"),
        "result_type": ref.get("result_type") or step.get("expected_result_type"),
        "result_value": amount or ref.get("result"),
        "amount_usd": amount,
        "source_reference": ref.get("top_relative_path") or ref.get("folder_label"),
        "source_fingerprint": ref.get("folder_fingerprint") or ref.get("source_sha256"),
        "verification_state": step.get("verification_status"),
        "checkpoint_revision": checkpoint_revision,
        "stale": bool(ref.get("stale")),
        "excerpts_note": ref.get("result") if step.get("capability") == "local.documents.search" else None,
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
    expected_capability: Optional[str] = None,
    field_id: Optional[str] = None,
) -> Tuple[str, Dict[str, Any]]:
    """Resolve a verified USD amount from any completed upstream step."""
    target = next((s for s in steps if s.get("step_id") == step_id), None)
    if target is None:
        raise CompositionError(f"upstream step not found: {step_id}")
    if target.get("status") != "completed":
        raise CompositionError(f"upstream step is not completed: {step_id}")
    if target.get("verification_status") != "verified":
        raise CompositionError(f"upstream step is not verified: {step_id}")
    if expected_capability and target.get("capability") != expected_capability:
        raise CompositionError(
            f"upstream step capability mismatch: expected {expected_capability}"
        )
    ref = target.get("result_reference") if isinstance(target.get("result_reference"), dict) else {}
    if ref.get("stale"):
        raise CompositionError(
            f"upstream step result is stale and must be reverified: {step_id}"
        )
    amount = None
    label = ref.get("component_label") or ref.get("result_type")
    source_ref = ref.get("top_relative_path") or ref.get("folder_label")
    if field_id and target.get("capability") == CAPABILITY_EXTRACT:
        fields = ref.get("fields") if isinstance(ref.get("fields"), dict) else {}
        entry = fields.get(field_id)
        if not isinstance(entry, dict) or entry.get("status") != "verified":
            raise CompositionError(f"extracted field not verified: {field_id}")
        amount = entry.get("normalized_value")
        label = field_id
        source_ref = entry.get("source_document") or source_ref
    if amount is None:
        amount = ref.get("amount_usd")
    if amount is None and target.get("capability") == "calculator.labor":
        amount = ref.get("result")
    if amount is None and target.get("capability") in {
        CAPABILITY_AGGREGATE,
        CAPABILITY_ASSEMBLE,
    }:
        amount = ref.get("result") or ref.get("subtotal_usd")
    if amount is None and target.get("capability") == CAPABILITY_EXTRACT and not field_id:
        amount = ref.get("amount_usd")
    if amount is None:
        raise CompositionError(f"upstream step has no verified amount_usd: {step_id}")
    return money_str(_dec(amount)), {
        "step_id": step_id,
        "capability": target.get("capability"),
        "execution_receipt_id": target.get("execution_receipt_id") or ref.get("execution_id"),
        "amount_usd": money_str(_dec(amount)),
        "source_reference": source_ref,
        "source_fingerprint": ref.get("folder_fingerprint"),
        "verification_state": "verified",
        "label": label,
        "field_id": field_id,
    }


def resolve_upstream_evidence(
    steps: Sequence[Mapping[str, Any]],
    step_id: str,
) -> Dict[str, Any]:
    """Resolve verified non-amount evidence (excerpts, aggregates, drafts metadata)."""
    target = next((s for s in steps if s.get("step_id") == step_id), None)
    if target is None:
        raise CompositionError(f"upstream step not found: {step_id}")
    if target.get("status") != "completed":
        raise CompositionError(f"upstream step is not completed: {step_id}")
    if target.get("verification_status") != "verified":
        raise CompositionError(f"upstream step is not verified: {step_id}")
    ref = target.get("result_reference") if isinstance(target.get("result_reference"), dict) else {}
    if ref.get("stale"):
        raise CompositionError(f"upstream step result is stale: {step_id}")
    return {
        "step_id": step_id,
        "capability": target.get("capability"),
        "description": target.get("description"),
        "execution_receipt_id": target.get("execution_receipt_id") or ref.get("execution_id"),
        "result_type": ref.get("result_type"),
        "result": ref.get("result"),
        "amount_usd": ref.get("amount_usd"),
        "components": ref.get("components"),
        "fields": ref.get("fields"),
        "excerpts": ref.get("excerpts"),
        "top_relative_path": ref.get("top_relative_path"),
        "folder_label": ref.get("folder_label"),
        "source_fingerprint": ref.get("folder_fingerprint"),
        "verification_state": "verified",
    }


def aggregate_usd_amounts(
    *,
    components: Sequence[Mapping[str, Any]],
    bundle_label: str = "verified amount subtotal",
    missing_categories: Optional[Sequence[str]] = None,
    capability: str = CAPABILITY_AGGREGATE,
) -> Dict[str, Any]:
    """Deterministic Decimal sum of verified component amounts."""
    if not components or len(components) > 12:
        raise CompositionError("aggregate requires 1..12 verified components")
    labeled: Dict[str, str] = {}
    total = Decimal("0.00")
    inputs: Dict[str, Any] = {}
    for idx, comp in enumerate(components):
        amount = _dec(comp.get("amount_usd"))
        label = str(comp.get("label") or f"item_{idx + 1}").strip()[:40] or f"item_{idx + 1}"
        if label in labeled:
            label = f"{label}_{idx + 1}"
        labeled[label] = money_str(amount)
        total += amount
        inputs[label] = dict(comp)
    subtotal = total.quantize(Decimal("0.01"))
    return {
        "ok": True,
        "capability": capability,
        "currency": "USD",
        "components": labeled,
        "subtotal_usd": money_str(subtotal),
        "label": bundle_label,
        "missing_cost_categories": list(missing_categories or []),
        "inputs": inputs,
        "verification_rule": "deterministic_decimal_sum",
        "created_utc": _utc_now(),
    }


def assemble_estimate_subtotal(
    *,
    material_usd: str,
    labor_usd: str,
    material_link: Mapping[str, Any],
    labor_link: Mapping[str, Any],
) -> Dict[str, Any]:
    """Painting-estimate compatibility wrapper around aggregate_usd_amounts."""
    tmpl = DOMAIN_TEMPLATES["painting_estimate"]
    return aggregate_usd_amounts(
        components=[
            {**dict(material_link), "amount_usd": material_usd, "label": "materials"},
            {**dict(labor_link), "amount_usd": labor_usd, "label": "labor"},
        ],
        bundle_label=str(tmpl["bundle_label"]),
        missing_categories=list(tmpl["missing_categories"]),
        capability=CAPABILITY_ASSEMBLE,
    )


def synthesize_system_prompt(
    *,
    mode: str,
    banner: str,
    required_amounts: Optional[Sequence[str]] = None,
) -> str:
    mode = (mode or "summary").casefold()
    if mode == "comparison":
        task = (
            "Compare the provided verified document evidence. List agreements and "
            "differences. Cite filenames. Do not invent quotes or conclusions beyond evidence."
        )
    elif mode == "draft":
        task = (
            "Prepare a readable DRAFT using only verified host numbers and sources. "
            "List missing cost categories explicitly; do not invent them as values."
        )
    else:
        task = (
            "Prepare a grounded summary using only verified host evidence and amounts. "
            "Distinguish facts, calculations, and missing information."
        )
    amount_rule = ""
    if required_amounts:
        listed = ", ".join(str(a) for a in required_amounts)
        amount_rule = (
            f" Include these exact USD amounts and no other totals over 100: {listed}."
        )
    return (
        f"{task} Every output must begin with the exact banner line: {banner}."
        f"{amount_rule} "
        "Do not invent tool permissions, currency totals, or verified results. "
        'Return JSON {"draft":"..."} only.'
    )


def build_synthesize_payload(
    *,
    objective: str,
    evidence: Sequence[Mapping[str, Any]],
    aggregated: Optional[Mapping[str, Any]] = None,
    mode: str = "summary",
    banner: str = DEFAULT_DRAFT_BANNER,
    scope_notes: str = "",
) -> Dict[str, Any]:
    return {
        "objective": objective,
        "mode": mode,
        "verified_evidence": list(evidence),
        "verified_aggregate": aggregated,
        "scope_notes": scope_notes or "Limited to supported verified inputs only.",
        "required_banner": banner,
        "instructions": (
            "Cite source filenames/relative paths when present. "
            "If amounts are provided, include them exactly. "
            "State what is missing or unsupported rather than inventing it."
        ),
    }


# Painting-compatible aliases.
def draft_system_prompt() -> str:
    tmpl = DOMAIN_TEMPLATES["painting_estimate"]
    return synthesize_system_prompt(mode="draft", banner=str(tmpl["banner"]))


def build_draft_user_payload(
    *,
    objective: str,
    assembled: Mapping[str, Any],
    scope_notes: str = "",
) -> Dict[str, Any]:
    tmpl = DOMAIN_TEMPLATES["painting_estimate"]
    evidence = []
    inputs = assembled.get("inputs") or {}
    for key, link in inputs.items():
        if isinstance(link, dict):
            evidence.append({"role": key, **link})
    return build_synthesize_payload(
        objective=objective,
        evidence=evidence,
        aggregated=assembled,
        mode="draft",
        banner=str(tmpl["banner"]),
        scope_notes=scope_notes,
    )


def _amount_present(text: str, amount: str) -> bool:
    if amount in text:
        return True
    if amount.endswith(".00") and amount[:-3] in text:
        return True
    return False


def verify_synthesize_output(
    draft: str,
    *,
    banner: str,
    required_amounts: Optional[Sequence[str]] = None,
    required_phrases: Optional[Sequence[str]] = None,
    allow_large_invented: bool = False,
) -> Dict[str, Any]:
    if not isinstance(draft, str) or not draft.strip():
        raise CompositionError("draft is empty")
    text = draft.strip()
    if banner not in text:
        raise CompositionError("draft missing required banner")
    needed_amounts = [money_str(_dec(a)) for a in (required_amounts or [])]
    missing_amt = [a for a in needed_amounts if not _amount_present(text, a)]
    if missing_amt:
        raise CompositionError(
            "draft omitted verified amount(s): " + ", ".join(missing_amt)
        )
    missing_phrases = []
    for phrase in required_phrases or []:
        if not isinstance(phrase, str) or not phrase.strip():
            continue
        if phrase.casefold() not in text.casefold():
            missing_phrases.append(phrase)
    if missing_phrases:
        raise CompositionError(
            "draft omitted required source phrase(s): " + ", ".join(missing_phrases[:8])
        )
    if needed_amounts and not allow_large_invented:
        allowed = set(needed_amounts)
        for v in list(allowed):
            if v.endswith(".00"):
                allowed.add(v[:-3])
        allowed_norms = {money_str(_dec(a)) for a in allowed}
        invented = []
        for token in _MONEY_RE.findall(text.replace(",", "")):
            norm = money_str(_dec(token))
            if norm in allowed_norms:
                continue
            if Decimal(token) < Decimal("100"):
                continue
            invented.append(norm)
        invented = sorted(set(invented))
        if invented:
            raise CompositionError(
                "draft introduced unsupported figure(s): " + ", ".join(invented[:8])
            )
    return {
        "ok": True,
        "verified_amounts_present": {
            f"amount_{i}": a for i, a in enumerate(needed_amounts)
        },
        "required_phrases_present": list(required_phrases or []),
        "draft_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "char_count": len(text),
    }


def verify_draft_amounts(
    draft: str,
    *,
    materials_usd: str,
    labor_usd: str,
    subtotal_usd: str,
) -> Dict[str, Any]:
    """Painting-estimate compatibility wrapper."""
    tmpl = DOMAIN_TEMPLATES["painting_estimate"]
    return verify_synthesize_output(
        draft,
        banner=str(tmpl["banner"]),
        required_amounts=[materials_usd, labor_usd, subtotal_usd],
    )


def host_grounded_summary_draft(
    *,
    banner: str,
    evidence: Sequence[Mapping[str, Any]],
    aggregated: Optional[Mapping[str, Any]] = None,
    required_phrases: Optional[Sequence[str]] = None,
    required_amounts: Optional[Sequence[str]] = None,
) -> str:
    """Deterministic fallback draft from verified host evidence only."""
    lines = [banner, "Host-assembled grounded summary (model draft rejected)."]
    for ev in evidence:
        path = ev.get("top_relative_path") or ev.get("folder_label") or "source"
        amount = ev.get("amount_usd")
        # Only cite short verified summaries — never dump hashes or free-form blobs
        # that could introduce digit sequences rejected by amount postchecks.
        if amount:
            lines.append(f"- {path}: verified amount USD {amount}")
        else:
            lines.append(f"- {path}: verified evidence")
    if aggregated:
        comps = aggregated.get("components") or {}
        for label, amount in comps.items():
            # Avoid embedding opaque record ids that may contain digit runs.
            label_s = str(label)
            if label_s.startswith("rec_"):
                label_s = "line_item"
            lines.append(f"- {label_s}: USD {amount}")
        if aggregated.get("subtotal_usd"):
            lines.append(f"Verified subtotal USD {aggregated['subtotal_usd']}")
        missing = aggregated.get("missing_cost_categories") or []
        if missing:
            lines.append(
                "Missing / not included: "
                + ", ".join(str(m) for m in missing[:8] if not re.search(r"\d{3,}", str(m)))
            )
    for amount in required_amounts or []:
        token = str(amount)
        if token and token not in "\n".join(lines):
            lines.append(f"Verified amount USD {token}")
    for phrase in required_phrases or []:
        if phrase and phrase not in "\n".join(lines):
            # Phrases must be short source names/tokens, not numeric blobs.
            if re.fullmatch(r"[A-Za-z0-9._\- /]{1,120}", str(phrase)):
                lines.append(f"Source reference: {phrase}")
    return "\n".join(lines)


def parse_model_draft(raw: str) -> str:
    cleaned = (raw or "").strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    try:
        parsed = json.loads(cleaned)
    except (ValueError, TypeError) as exc:
        raise CompositionError("model did not return JSON draft") from exc
    if not isinstance(parsed, dict) or not isinstance(parsed.get("draft"), str):
        raise CompositionError("model draft payload invalid")
    draft = parsed["draft"].strip()
    if not draft or len(draft) > 8000:
        raise CompositionError("model draft length invalid")
    return draft


def _dependency_ids(args: Mapping[str, Any]) -> set:
    deps = set()
    for key in (
        "material_step_id",
        "labor_step_id",
        "assemble_step_id",
        "aggregate_step_id",
    ):
        val = args.get(key)
        if isinstance(val, str):
            deps.add(val)
    for key in ("source_step_ids", "evidence_step_ids"):
        raw = args.get(key)
        if isinstance(raw, list):
            deps.update(x for x in raw if isinstance(x, str))
    comps = args.get("components")
    if isinstance(comps, list):
        for item in comps:
            if isinstance(item, dict) and isinstance(item.get("step_id"), str):
                deps.add(item["step_id"])
    line_items = args.get("line_items")
    if isinstance(line_items, dict) and isinstance(line_items.get("record_step_id"), str):
        deps.add(line_items["record_step_id"])
    return deps


def mark_dependent_steps_stale(
    steps: List[Dict[str, Any]],
    *,
    changed_step_id: str,
) -> List[str]:
    stale_ids: List[str] = []
    for step in steps:
        if step.get("capability") not in COMPOSITION_CAPABILITIES:
            continue
        args = step.get("arguments") if isinstance(step.get("arguments"), dict) else {}
        if changed_step_id not in _dependency_ids(args):
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


def list_composable_capabilities() -> List[Dict[str, str]]:
    """Registry-facing catalog for plan proposal (not operational proof)."""
    return [
        {
            "capability": "local.documents.search",
            "role": "retrieve authorized local document excerpts",
        },
        {
            "capability": "calculator.labor",
            "role": "deterministic labor USD calculation",
        },
        {
            "capability": "compose.extract_fields",
            "role": "extract typed fields from verified document excerpts",
        },
        {
            "capability": "compose.extract_records",
            "role": "extract multiple typed table/list records from verified excerpts",
        },
        {
            "capability": "compose.aggregate_usd",
            "role": "sum verified USD amounts from upstream steps",
        },
        {
            "capability": "compose.synthesize",
            "role": "grounded summary/comparison/draft from verified evidence",
        },
        {
            "capability": "estimate.assemble",
            "role": "painting-compatible materials+labor subtotal adapter",
        },
        {
            "capability": "estimate.draft",
            "role": "painting-compatible draft adapter from assemble",
        },
    ]


def _capability_name_set(available_capabilities: Sequence[Any]) -> set:
    names: set = set()
    for item in available_capabilities:
        if isinstance(item, str):
            names.add(item)
        elif isinstance(item, Mapping) and isinstance(item.get("capability"), str):
            names.add(item["capability"])
    return names


def compose_plan_prompt(
    goal: str,
    available_capabilities: Sequence[Any],
) -> str:
    caps = list_composable_capabilities()
    if available_capabilities:
        allowed = _capability_name_set(available_capabilities)
        caps = [c for c in caps if c["capability"] in allowed] or caps
    catalog = "\n".join(f"- {c['capability']}: {c['role']}" for c in caps)
    return (
        "Propose a short capability plan for the operator goal below. "
        "Use only listed capabilities. Do not claim authorization or invent results.\n"
        f"Available capabilities:\n{catalog}\n\n"
        f"Goal: {goal.strip()[:800]}\n\n"
        'Return JSON only: {"objective":"...","steps":['
        '{"capability":"...","expected_outcome":"...","depends_on":[],"notes":""}]}'
    )


def parse_model_plan_json(raw: str) -> Optional[Dict[str, Any]]:
    cleaned = (raw or "").strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    # Prefer first JSON object if prose surrounds it.
    match = re.search(r"\{.*\}", cleaned, flags=re.DOTALL)
    if match:
        cleaned = match.group(0)
    try:
        parsed = json.loads(cleaned)
    except (ValueError, TypeError):
        return None
    if not isinstance(parsed, dict):
        return None
    return parsed


def validate_proposed_plan(
    proposal: Mapping[str, Any],
    available_capabilities: Sequence[Any],
) -> Dict[str, Any]:
    """Validate a model-proposed plan against the capability registry (no execution)."""
    if not isinstance(proposal, Mapping):
        raise CompositionError("plan must be an object")
    objective = proposal.get("objective")
    if not isinstance(objective, str) or not objective.strip():
        raise CompositionError("plan objective is required")
    steps = proposal.get("steps")
    if not isinstance(steps, list) or not steps or len(steps) > 12:
        raise CompositionError("plan requires 1..12 steps")
    available = _capability_name_set(available_capabilities)
    if not available:
        available = {c["capability"] for c in list_composable_capabilities()}
    validated = []
    for idx, raw in enumerate(steps):
        if not isinstance(raw, dict):
            raise CompositionError(f"plan step {idx} invalid")
        cap = raw.get("capability")
        if not isinstance(cap, str) or cap not in available:
            raise CompositionError(
                f"plan step {idx} capability unavailable or unknown: {cap!r}"
            )
        outcome = raw.get("expected_outcome")
        if not isinstance(outcome, str) or not outcome.strip():
            raise CompositionError(f"plan step {idx} expected_outcome required")
        validated.append(
            {
                "order": idx,
                "capability": cap,
                "expected_outcome": outcome.strip()[:400],
                "depends_on": [
                    d
                    for d in (raw.get("depends_on") or [])
                    if isinstance(d, int) and 0 <= d < idx
                ][:8],
                "notes": str(raw.get("notes") or "")[:200],
            }
        )
    return {
        "ok": True,
        "objective": objective.strip()[:800],
        "steps": validated,
        "executable": False,
        "authorization_inherited": False,
        "note": "Plan validation is not execution authorization.",
    }


def recordable_outcome(
    *,
    capability: str,
    task_class: str,
    success: bool,
    failure_category: Optional[str] = None,
    recovery: Optional[str] = None,
) -> Dict[str, Any]:
    """Safe outcome metadata for existing execution-evidence machinery."""
    return {
        "capability": capability,
        "task_class": str(task_class or "unspecified")[:80],
        "success": bool(success),
        "failure_category": failure_category,
        "recovery": recovery,
        "created_utc": _utc_now(),
    }


EstimateWorkflowError = CompositionError  # compatibility alias
