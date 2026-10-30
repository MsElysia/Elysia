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


# --- Bounded adaptive step evaluation and replanning (host-controlled) ---

OUTCOME_VERIFIED_SUCCESS = "verified_success"
OUTCOME_TOOL_OK_INSUFFICIENT = "tool_ok_insufficient_evidence"
OUTCOME_MISSING_INFORMATION = "missing_information"
OUTCOME_AMBIGUOUS = "ambiguous_information"
OUTCOME_CONFLICTING = "conflicting_evidence"
OUTCOME_STALE_UPSTREAM = "stale_upstream"
OUTCOME_UNAVAILABLE_CAPABILITY = "unavailable_capability"
OUTCOME_AUTHORIZATION_REQUIRED = "authorization_required"
OUTCOME_RECOVERABLE_FAILURE = "recoverable_failure"
OUTCOME_TERMINAL_FAILURE = "terminal_failure"
OUTCOME_NOT_EXECUTED = "not_executed"

MAX_REPLAN_ATTEMPTS = 3
MAX_REPLAN_ALTERNATIVES = 4

_DETERMINISTIC_CAPS = frozenset(
    {
        "calculator.labor",
        CAPABILITY_AGGREGATE,
        CAPABILITY_EXTRACT,
        CAPABILITY_EXTRACT_RECORDS,
        CAPABILITY_ASSEMBLE,
    }
)
_MODEL_ASSISTED_CAPS = frozenset(
    {
        "local.documents.search",
        CAPABILITY_SYNTHESIZE,
        CAPABILITY_DRAFT,
    }
)


def capability_selection_metadata(capability: str) -> Dict[str, Any]:
    """Known selection factors only; reliability stays unknown unless measured elsewhere."""
    cap = str(capability or "")
    known = {c["capability"] for c in list_composable_capabilities()}
    available = cap in known
    deterministic = cap in _DETERMINISTIC_CAPS
    model_assisted = cap in _MODEL_ASSISTED_CAPS
    return {
        "capability": cap,
        "available": available,
        "authorization_required": True,
        "data_locality": "local" if available else "unknown",
        "privacy": "local_only" if available else "unknown",
        "reliability": "unknown",
        "estimated_cost": "unknown",
        "estimated_latency": "lower_when_deterministic" if deterministic else "unknown",
        "verification_potential": (
            "high" if deterministic else ("medium" if model_assisted else "unknown")
        ),
        "prefers_deterministic": deterministic,
        "model_assisted": model_assisted,
    }


def evaluate_step_outcome(
    step: Mapping[str, Any],
    *,
    expected_outcome: Optional[str] = None,
    available_capabilities: Optional[Sequence[Any]] = None,
) -> Dict[str, Any]:
    """Host evaluation of whether a step satisfies its objective (no model trust)."""
    if not isinstance(step, Mapping):
        raise CompositionError("step must be an object")
    cap = step.get("capability")
    available = _capability_name_set(available_capabilities or list_composable_capabilities())
    if cap and available and cap not in available:
        return {
            "met": False,
            "category": OUTCOME_UNAVAILABLE_CAPABILITY,
            "reason": f"capability unavailable: {cap}",
            "expected_outcome": (expected_outcome or "")[:400] or None,
            "replanning_recommended": True,
            "authorization_granted": False,
        }

    ref = step.get("result_reference") if isinstance(step.get("result_reference"), dict) else {}
    if ref.get("stale") or step.get("last_failure_category") == "upstream_stale":
        return {
            "met": False,
            "category": OUTCOME_STALE_UPSTREAM,
            "reason": str(ref.get("stale_reason") or "upstream evidence is stale"),
            "expected_outcome": (expected_outcome or "")[:400] or None,
            "replanning_recommended": True,
            "authorization_granted": False,
        }

    status = step.get("status")
    verification = step.get("verification_status")
    execution = step.get("execution_status")
    failure = step.get("last_failure_category")

    def _field_status_hits() -> Tuple[List[str], List[str]]:
        fields = ref.get("fields") if isinstance(ref.get("fields"), dict) else None
        records = ref.get("records") if isinstance(ref.get("records"), list) else None
        conflict_hits: List[str] = []
        ambiguous_hits: List[str] = []
        if fields:
            for fid, fval in fields.items():
                if not isinstance(fval, dict):
                    continue
                st = fval.get("status")
                if st == "conflicting":
                    conflict_hits.append(str(fid))
                elif st == "ambiguous":
                    ambiguous_hits.append(str(fid))
        if records:
            for rec in records:
                if not isinstance(rec, dict):
                    continue
                if rec.get("status") == "conflicting":
                    conflict_hits.append(str(rec.get("record_id") or "record"))
                elif rec.get("status") == "ambiguous":
                    ambiguous_hits.append(str(rec.get("record_id") or "record"))
                rec_fields = rec.get("fields") if isinstance(rec.get("fields"), dict) else {}
                for fid, fval in rec_fields.items():
                    if isinstance(fval, dict) and fval.get("status") == "conflicting":
                        conflict_hits.append(f"{rec.get('record_id')}.{fid}")
                    if isinstance(fval, dict) and fval.get("status") == "ambiguous":
                        ambiguous_hits.append(f"{rec.get('record_id')}.{fid}")
        return conflict_hits, ambiguous_hits

    conflict_hits, ambiguous_hits = _field_status_hits()
    if conflict_hits:
        return {
            "met": False,
            "category": OUTCOME_CONFLICTING,
            "reason": "conflicting observations retained: " + ", ".join(conflict_hits[:8]),
            "expected_outcome": (expected_outcome or "")[:400] or None,
            "replanning_recommended": True,
            "authorization_granted": False,
        }
    if ambiguous_hits and not (status == "completed" and verification == "verified"):
        return {
            "met": False,
            "category": OUTCOME_AMBIGUOUS,
            "reason": "ambiguous fields remain: " + ", ".join(ambiguous_hits[:8]),
            "expected_outcome": (expected_outcome or "")[:400] or None,
            "replanning_recommended": True,
            "authorization_granted": False,
        }

    if status == "completed" and verification == "verified":
        if ambiguous_hits:
            return {
                "met": False,
                "category": OUTCOME_AMBIGUOUS,
                "reason": "ambiguous fields remain: " + ", ".join(ambiguous_hits[:8]),
                "expected_outcome": (expected_outcome or "")[:400] or None,
                "replanning_recommended": True,
                "authorization_granted": False,
            }
        return {
            "met": True,
            "category": OUTCOME_VERIFIED_SUCCESS,
            "reason": "step completed with host-verified result",
            "expected_outcome": (expected_outcome or "")[:400] or None,
            "replanning_recommended": False,
            "authorization_granted": False,
        }

    if execution == "succeeded" and verification == "failed":
        if failure == "evidence_criteria_unmet":
            return {
                "met": False,
                "category": OUTCOME_TOOL_OK_INSUFFICIENT,
                "reason": "tool succeeded but evidence criteria were unmet",
                "expected_outcome": (expected_outcome or "")[:400] or None,
                "replanning_recommended": True,
                "authorization_granted": False,
                "failure_category": failure,
            }
        if failure in {"incorrect_result", "invalid_arguments"}:
            return {
                "met": False,
                "category": OUTCOME_RECOVERABLE_FAILURE,
                "reason": f"host rejected intermediate result ({failure})",
                "expected_outcome": (expected_outcome or "")[:400] or None,
                "replanning_recommended": True,
                "authorization_granted": False,
                "failure_category": failure,
            }
        return {
            "met": False,
            "category": OUTCOME_TOOL_OK_INSUFFICIENT,
            "reason": "tool operation succeeded without verified task evidence",
            "expected_outcome": (expected_outcome or "")[:400] or None,
            "replanning_recommended": True,
            "authorization_granted": False,
            "failure_category": failure,
        }

    if execution == "failed":
        if failure == "tool_exception":
            return {
                "met": False,
                "category": OUTCOME_RECOVERABLE_FAILURE,
                "reason": "tool raised a recoverable exception",
                "expected_outcome": (expected_outcome or "")[:400] or None,
                "replanning_recommended": True,
                "authorization_granted": False,
                "failure_category": failure,
            }
        return {
            "met": False,
            "category": OUTCOME_TERMINAL_FAILURE
            if failure in {"unauthorized", "policy_denied"}
            else OUTCOME_RECOVERABLE_FAILURE,
            "reason": f"execution failed ({failure or 'unknown'})",
            "expected_outcome": (expected_outcome or "")[:400] or None,
            "replanning_recommended": failure not in {"unauthorized", "policy_denied"},
            "authorization_granted": False,
            "failure_category": failure,
        }

    if execution in {None, "none"} and verification in {None, "none"}:
        return {
            "met": False,
            "category": OUTCOME_NOT_EXECUTED,
            "reason": "step has not been executed",
            "expected_outcome": (expected_outcome or "")[:400] or None,
            "replanning_recommended": False,
            "authorization_granted": False,
        }

    return {
        "met": False,
        "category": OUTCOME_MISSING_INFORMATION,
        "reason": "required verified evidence is not present",
        "expected_outcome": (expected_outcome or "")[:400] or None,
        "replanning_recommended": True,
        "authorization_granted": False,
    }


def rank_replan_candidates(
    candidates: Sequence[Mapping[str, Any]],
    *,
    available_capabilities: Optional[Sequence[Any]] = None,
) -> List[Dict[str, Any]]:
    """Order alternatives using known metadata only (no invented success rates)."""
    available = _capability_name_set(available_capabilities or list_composable_capabilities())
    ranked: List[Dict[str, Any]] = []
    for raw in list(candidates)[:MAX_REPLAN_ALTERNATIVES]:
        if not isinstance(raw, Mapping):
            continue
        cap = raw.get("capability")
        if not isinstance(cap, str) or cap not in available:
            continue
        meta = capability_selection_metadata(cap)
        score = 0
        if meta["available"]:
            score += 10
        if meta["prefers_deterministic"]:
            score += 5
        if meta["verification_potential"] == "high":
            score += 3
        elif meta["verification_potential"] == "medium":
            score += 1
        # Penalize repeating the exact same capability+notes without change.
        ranked.append(
            {
                "capability": cap,
                "expected_outcome": str(raw.get("expected_outcome") or "")[:400],
                "notes": str(raw.get("notes") or "")[:200],
                "depends_on": [
                    d
                    for d in (raw.get("depends_on") or [])
                    if isinstance(d, int) and d >= 0
                ][:8],
                "selection": meta,
                "usefulness_score": score,
                "reliability": "unknown",
            }
        )
    ranked.sort(key=lambda c: (-int(c["usefulness_score"]), c["capability"]))
    return ranked


def compose_replan_prompt(
    goal: str,
    *,
    evaluation: Mapping[str, Any],
    verified_progress: Sequence[Mapping[str, Any]],
    failed_attempt: Optional[Mapping[str, Any]] = None,
    available_capabilities: Optional[Sequence[Any]] = None,
    constraints: Optional[Sequence[str]] = None,
    prior_attempt_summaries: Optional[Sequence[str]] = None,
) -> str:
    caps = list_composable_capabilities()
    if available_capabilities:
        allowed = _capability_name_set(available_capabilities)
        caps = [c for c in caps if c["capability"] in allowed] or caps
    catalog = "\n".join(f"- {c['capability']}: {c['role']}" for c in caps)
    progress_lines = []
    for link in list(verified_progress)[:8]:
        if not isinstance(link, Mapping):
            continue
        progress_lines.append(
            f"- verified {link.get('capability')}: "
            f"{link.get('result_value') or link.get('source_reference') or 'ok'}"
        )
    progress_block = "\n".join(progress_lines) or "- (none yet)"
    failed = failed_attempt if isinstance(failed_attempt, Mapping) else {}
    prior = [
        str(p)[:200]
        for p in (prior_attempt_summaries or [])
        if isinstance(p, str) and p.strip()
    ][:MAX_REPLAN_ATTEMPTS]
    constraint_lines = [
        str(c)[:200] for c in (constraints or []) if str(c).strip()
    ][:8]
    return (
        "The operator goal is unchanged. A prior authorized step did not satisfy the "
        "objective. Propose a bounded alternative plan using only listed capabilities. "
        "Do not change the goal, grant authorization, invent evidence, or claim "
        "completion. Prefer deterministic local capabilities when they can fully "
        "satisfy the need. Do not repeat the identical failing approach.\n"
        f"Available capabilities:\n{catalog}\n\n"
        f"Goal (immutable): {goal.strip()[:800]}\n"
        f"Failure category: {evaluation.get('category')}\n"
        f"Failure reason: {str(evaluation.get('reason') or '')[:400]}\n"
        f"Failed capability: {failed.get('capability')}\n"
        f"Failed step description: {str(failed.get('description') or '')[:300]}\n"
        f"Verified progress:\n{progress_block}\n"
        f"Prior replan attempts:\n"
        + ("\n".join(f"- {p}" for p in prior) or "- (none)")
        + "\n"
        f"Operator constraints:\n"
        + ("\n".join(f"- {c}" for c in constraint_lines) or "- (none)")
        + "\n\n"
        'Return JSON only: {"objective":"...","revision_reason":"...","steps":['
        '{"capability":"...","expected_outcome":"...","depends_on":[],"notes":""}]}'
    )


def validate_replan_proposal(
    proposal: Mapping[str, Any],
    *,
    original_objective: str,
    available_capabilities: Sequence[Any],
    evaluation: Mapping[str, Any],
    prior_attempt_count: int = 0,
    failed_capability: Optional[str] = None,
) -> Dict[str, Any]:
    """Validate a model replan; preserve objective; grant no authority."""
    if prior_attempt_count >= MAX_REPLAN_ATTEMPTS:
        raise CompositionError(
            f"replan attempt limit reached ({MAX_REPLAN_ATTEMPTS}); operator blocker required"
        )
    if not isinstance(evaluation, Mapping) or evaluation.get("met") is True:
        raise CompositionError("replan requires a failed step evaluation")
    if not evaluation.get("replanning_recommended", True):
        raise CompositionError("evaluation does not recommend replanning")

    # Objective must remain the original operator goal (model cannot redefine it).
    forced = dict(proposal) if isinstance(proposal, Mapping) else {}
    forced["objective"] = (original_objective or "").strip()[:800]
    if not forced["objective"]:
        raise CompositionError("original objective required for replan")

    validated = validate_proposed_plan(forced, available_capabilities)
    steps = list(validated["steps"])
    if len(steps) > MAX_REPLAN_ALTERNATIVES + 2:
        raise CompositionError("replan has too many steps")

    # Reject blind identical single-step retry of the same failing capability.
    if (
        failed_capability
        and len(steps) == 1
        and steps[0]["capability"] == failed_capability
        and not str(steps[0].get("notes") or "").strip()
    ):
        raise CompositionError(
            "replan must not blindly retry the same failing capability without a changed approach"
        )

    revision_reason = ""
    if isinstance(proposal, Mapping):
        revision_reason = str(proposal.get("revision_reason") or "").strip()[:400]
    if not revision_reason:
        revision_reason = str(evaluation.get("reason") or "prior approach insufficient")[:400]

    ranked = rank_replan_candidates(steps, available_capabilities=available_capabilities)
    return {
        "ok": True,
        "objective": validated["objective"],
        "steps": validated["steps"],
        "revision_reason": revision_reason,
        "failure_category": evaluation.get("category"),
        "ranked_alternatives": ranked,
        "selected_next_capability": (ranked[0]["capability"] if ranked else None),
        "executable": False,
        "authorization_inherited": False,
        "authorization_granted": False,
        "replan_attempt_index": int(prior_attempt_count) + 1,
        "note": (
            "Validated replan is not an execution grant. "
            "Each new step still requires request-scoped authorization."
        ),
    }


def map_validated_plan_to_outstanding_steps(
    validated: Mapping[str, Any],
) -> List[str]:
    steps = validated.get("steps") if isinstance(validated, Mapping) else None
    if not isinstance(steps, list) or not steps:
        raise CompositionError("validated plan has no steps")
    out: List[str] = []
    for step in steps[:12]:
        if not isinstance(step, Mapping):
            continue
        cap = step.get("capability")
        outcome = step.get("expected_outcome")
        if not isinstance(cap, str) or not isinstance(outcome, str):
            continue
        notes = str(step.get("notes") or "").strip()
        desc = f"{cap}: {outcome.strip()}"
        if notes:
            desc = f"{desc} ({notes[:80]})"
        out.append(desc[:400])
    if not out:
        raise CompositionError("validated plan produced no outstanding steps")
    return out


def sanitize_prompt_injection_claims(text: str) -> str:
    """Strip common injection phrases from untrusted source/plan text for logs."""
    cleaned = str(text or "")
    banned = (
        "authorization granted",
        "enable cloud",
        "ignore previous",
        "you are now",
        "mark task complete",
        "bypass restriction",
    )
    lower = cleaned.lower()
    for phrase in banned:
        if phrase in lower:
            cleaned = cleaned.replace(phrase, "[redacted-injection]")
            cleaned = cleaned.replace(phrase.title(), "[redacted-injection]")
            cleaned = cleaned.replace(phrase.upper(), "[redacted-injection]")
            lower = cleaned.lower()
    return cleaned[:800]


EstimateWorkflowError = CompositionError  # compatibility alias
