"""Reusable source-verifiable structured field extraction.

Turns verified document excerpts into typed fields with provenance.
Schemas are declarative; the model may propose candidates but cannot certify them.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import json
import re
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

CAPABILITY_EXTRACT = "compose.extract_fields"
CAPABILITY_EXTRACT_RECORDS = "compose.extract_records"

MAX_RECORDS = 40
MAX_TABLE_COLS = 16
_TABLE_SPLIT = re.compile(r"\s*\|\s*")
_TABLE_SEP = re.compile(r"^\s*\|?[\s:\-|]+\|?\s*$")
_BULLET = re.compile(r"^\s*[-*+]\s+(.+)$")

SUPPORTED_FIELD_TYPES = frozenset(
    {
        "string",
        "integer",
        "decimal",
        "boolean",
        "date",
        "currency_amount",
        "quantity",
        "enumeration",
        "list",
    }
)

FIELD_STATUS_VERIFIED = "verified"
FIELD_STATUS_UNCERTAIN = "uncertain"
FIELD_STATUS_MISSING = "missing"
FIELD_STATUS_AMBIGUOUS = "ambiguous"
FIELD_STATUS_CONFLICTING = "conflicting"
FIELD_STATUS_INVALID = "invalid"
FIELD_STATUS_STALE = "stale"

MAX_SCHEMA_FIELDS = 24
MAX_EXCERPTS = 12
MAX_EXCERPT_CHARS = 800
MAX_STRING_LEN = 400
MAX_LIST_ITEMS = 12
MAX_LABELS = 8

_ISO_DATE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})$")
_US_DATE = re.compile(r"^(\d{1,2})/(\d{1,2})/(\d{4})$")
_MONEY = re.compile(
    r"(?<![0-9.])\$?\s*([0-9]{1,7}(?:\.[0-9]{1,2})?)(?![0-9])"
)
_INT = re.compile(r"(?<![0-9.])(-?[0-9]{1,9})(?![0-9.])")
_DEC = re.compile(r"(?<![0-9.])(-?[0-9]{1,9}(?:\.[0-9]{1,6})?)(?![0-9])")
_QTY = re.compile(
    r"(?<![0-9.])([0-9]{1,9}(?:\.[0-9]{1,4})?)\s*([A-Za-z%]{1,12})\b"
)
_BOOL_TRUE = frozenset({"true", "yes", "y", "1"})
_BOOL_FALSE = frozenset({"false", "no", "n", "0"})


class ExtractionError(ValueError):
    pass


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def validate_extraction_schema(raw: Any) -> Dict[str, Any]:
    """Validate a declarative extraction schema (no executable content)."""
    if not isinstance(raw, Mapping):
        raise ExtractionError("schema must be an object")
    for banned in ("code", "eval", "exec", "python", "javascript", "shell"):
        if banned in raw:
            raise ExtractionError(f"schema must not include {banned}")
    fields_raw = raw.get("fields")
    if not isinstance(fields_raw, list) or not fields_raw or len(fields_raw) > MAX_SCHEMA_FIELDS:
        raise ExtractionError(f"schema requires 1..{MAX_SCHEMA_FIELDS} fields")
    seen: set = set()
    fields: List[Dict[str, Any]] = []
    for idx, item in enumerate(fields_raw):
        if not isinstance(item, Mapping):
            raise ExtractionError(f"field {idx} invalid")
        fid = item.get("id")
        if not isinstance(fid, str) or not re.fullmatch(r"[a-z][a-z0-9_]{0,39}", fid):
            raise ExtractionError(f"field {idx} id invalid")
        if fid in seen:
            raise ExtractionError(f"duplicate field id: {fid}")
        seen.add(fid)
        ftype = item.get("type")
        if ftype not in SUPPORTED_FIELD_TYPES:
            raise ExtractionError(f"unsupported field type: {ftype!r}")
        field: Dict[str, Any] = {
            "id": fid,
            "type": ftype,
            "required": bool(item.get("required", True)),
        }
        labels = item.get("labels")
        if labels is not None:
            if not isinstance(labels, list) or len(labels) > MAX_LABELS:
                raise ExtractionError(f"field {fid} labels invalid")
            cleaned = []
            for lab in labels:
                if not isinstance(lab, str) or not lab.strip() or len(lab) > 80:
                    raise ExtractionError(f"field {fid} label invalid")
                cleaned.append(lab.strip())
            field["labels"] = cleaned
        if ftype == "string":
            max_len = item.get("max_length", 120)
            if type(max_len) is not int or not 1 <= max_len <= MAX_STRING_LEN:
                raise ExtractionError(f"field {fid} max_length invalid")
            field["max_length"] = max_len
        elif ftype == "integer":
            for key in ("min", "max"):
                if key in item:
                    if type(item[key]) is not int:
                        raise ExtractionError(f"field {fid} {key} must be int")
                    field[key] = item[key]
        elif ftype == "decimal":
            places = item.get("decimal_places", 2)
            if type(places) is not int or not 0 <= places <= 6:
                raise ExtractionError(f"field {fid} decimal_places invalid")
            field["decimal_places"] = places
        elif ftype == "currency_amount":
            currency = item.get("currency", "USD")
            if currency not in {"USD"}:
                raise ExtractionError(f"field {fid} unsupported currency")
            field["currency"] = currency
        elif ftype == "quantity":
            units = item.get("units")
            if not isinstance(units, list) or not units or len(units) > 24:
                raise ExtractionError(f"field {fid} units required")
            cleaned_u = []
            for u in units:
                if not isinstance(u, str) or not u.strip() or len(u) > 16:
                    raise ExtractionError(f"field {fid} unit invalid")
                cleaned_u.append(u.strip())
            field["units"] = cleaned_u
            field["require_unit"] = bool(item.get("require_unit", True))
        elif ftype == "enumeration":
            values = item.get("values")
            if not isinstance(values, list) or not values or len(values) > 32:
                raise ExtractionError(f"field {fid} values required")
            cleaned_v = []
            for v in values:
                if not isinstance(v, str) or not v.strip() or len(v) > 64:
                    raise ExtractionError(f"field {fid} enum value invalid")
                cleaned_v.append(v.strip())
            field["values"] = cleaned_v
        elif ftype == "list":
            item_type = item.get("item_type")
            if item_type not in SUPPORTED_FIELD_TYPES - {"list"}:
                raise ExtractionError(f"field {fid} item_type invalid")
            max_items = item.get("max_items", 8)
            if type(max_items) is not int or not 1 <= max_items <= MAX_LIST_ITEMS:
                raise ExtractionError(f"field {fid} max_items invalid")
            field["item_type"] = item_type
            field["max_items"] = max_items
            if item_type == "quantity":
                units = item.get("units")
                if isinstance(units, list) and units:
                    field["units"] = [str(u).strip()[:16] for u in units if str(u).strip()][:24]
            if item_type == "enumeration" and isinstance(item.get("values"), list):
                field["values"] = [str(v).strip()[:64] for v in item["values"] if str(v).strip()][:32]
        elif ftype == "date":
            field["allow_ambiguous"] = bool(item.get("allow_ambiguous", True))
        fields.append(field)
    return {"fields": fields}


def normalize_excerpts(raw: Any) -> List[Dict[str, Any]]:
    if not isinstance(raw, list) or not raw or len(raw) > MAX_EXCERPTS:
        raise ExtractionError(f"excerpts must be a list of 1..{MAX_EXCERPTS}")
    out: List[Dict[str, Any]] = []
    for idx, item in enumerate(raw):
        if not isinstance(item, Mapping):
            raise ExtractionError(f"excerpt {idx} invalid")
        text = item.get("excerpt")
        if not isinstance(text, str) or not text.strip():
            raise ExtractionError(f"excerpt {idx} text required")
        text = text.strip()
        if len(text) > MAX_EXCERPT_CHARS:
            text = text[:MAX_EXCERPT_CHARS]
        rel = item.get("relative_path") or item.get("filename") or f"excerpt_{idx}"
        if not isinstance(rel, str) or ".." in rel or len(rel) > 200:
            raise ExtractionError(f"excerpt {idx} relative_path invalid")
        entry = {
            "relative_path": rel.replace("\\", "/"),
            "filename": str(item.get("filename") or rel.split("/")[-1])[:120],
            "excerpt": text,
            "excerpt_sha256": item.get("excerpt_sha256") or _sha(text),
            "source_sha256": item.get("source_sha256"),
            "folder_fingerprint": item.get("folder_fingerprint"),
            "folder_label": item.get("folder_label"),
            "line": item.get("line"),
        }
        if entry["excerpt_sha256"] != _sha(text):
            # Prefer recomputed hash of the stored excerpt body.
            entry["excerpt_sha256"] = _sha(text)
        out.append(entry)
    return out


def _find_labeled_spans(
    excerpts: Sequence[Mapping[str, Any]],
    labels: Sequence[str],
) -> List[Dict[str, Any]]:
    hits: List[Dict[str, Any]] = []
    for ex in excerpts:
        body = ex["excerpt"]
        for label in labels:
            # Label then optional colon then value to end of line.
            pat = re.compile(
                rf"(?im)(?:^|\n)\s*{re.escape(label)}\s*:?\s*(.+?)(?:\n|$)"
            )
            for m in pat.finditer(body):
                value_raw = m.group(1).strip()
                span = m.group(0).strip()
                if not value_raw or not span:
                    continue
                if (
                    span.casefold() not in body.casefold()
                    and value_raw.casefold() not in body.casefold()
                ):
                    continue
                hits.append(
                    {
                        "excerpt": ex,
                        "label": label,
                        "value_raw": value_raw,
                        "source_span": span[:240],
                        "span_sha256": _sha(span[:240]),
                    }
                )
    return hits


def _normalize_scalar(
    ftype: str,
    raw: str,
    field: Mapping[str, Any],
) -> Tuple[Any, str, Optional[str]]:
    """Return (normalized, status_or_ok, note). status 'ok' means ready for verified."""
    text = raw.strip()
    if ftype == "string":
        max_len = int(field.get("max_length") or 120)
        if not text or len(text) > max_len:
            return None, FIELD_STATUS_INVALID, "string length invalid"
        return text, "ok", None
    if ftype == "boolean":
        token = text.casefold().rstrip(".")
        if token in _BOOL_TRUE:
            return True, "ok", None
        if token in _BOOL_FALSE:
            return False, "ok", None
        return None, FIELD_STATUS_INVALID, "boolean not recognized"
    if ftype == "integer":
        m = _INT.search(text.replace(",", ""))
        if not m:
            return None, FIELD_STATUS_INVALID, "integer not found"
        try:
            val = int(m.group(1))
        except ValueError:
            return None, FIELD_STATUS_INVALID, "integer parse failed"
        if "min" in field and val < field["min"]:
            return None, FIELD_STATUS_INVALID, "below min"
        if "max" in field and val > field["max"]:
            return None, FIELD_STATUS_INVALID, "above max"
        return val, "ok", None
    if ftype == "decimal":
        m = _DEC.search(text.replace(",", ""))
        if not m:
            return None, FIELD_STATUS_INVALID, "decimal not found"
        try:
            d = Decimal(m.group(1))
        except InvalidOperation:
            return None, FIELD_STATUS_INVALID, "decimal parse failed"
        places = int(field.get("decimal_places") or 2)
        return format(d.quantize(Decimal(10) ** -places), "f"), "ok", None
    if ftype == "currency_amount":
        m = _MONEY.search(text.replace(",", ""))
        if not m:
            return None, FIELD_STATUS_INVALID, "currency amount not found"
        try:
            d = Decimal(m.group(1))
        except InvalidOperation:
            return None, FIELD_STATUS_INVALID, "currency parse failed"
        if d < 0 or d >= Decimal("10000000"):
            return None, FIELD_STATUS_INVALID, "currency out of range"
        return format(d.quantize(Decimal("0.01")), "f"), "ok", None
    if ftype == "quantity":
        m = _QTY.search(text.replace(",", ""))
        units = [u.casefold() for u in (field.get("units") or [])]
        if m:
            num_s, unit = m.group(1), m.group(2)
            if unit.casefold() not in units:
                if field.get("require_unit", True):
                    return None, FIELD_STATUS_INVALID, f"unit not accepted: {unit}"
            try:
                d = Decimal(num_s)
            except InvalidOperation:
                return None, FIELD_STATUS_INVALID, "quantity parse failed"
            return {
                "value": format(d.normalize(), "f"),
                "unit": unit if unit.casefold() in units else unit,
            }, "ok", None
        # Number without unit
        m2 = _DEC.search(text.replace(",", ""))
        if m2 and not field.get("require_unit", True):
            return {
                "value": m2.group(1),
                "unit": None,
            }, FIELD_STATUS_UNCERTAIN, "quantity missing unit"
        return None, FIELD_STATUS_INVALID, "quantity with unit not found"
    if ftype == "enumeration":
        allowed = {v.casefold(): v for v in (field.get("values") or [])}
        token = text.strip().casefold()
        # Prefer exact whole-token match among allowed.
        for key, original in allowed.items():
            if token == key or token.startswith(key) or key in token.split():
                return original, "ok", None
        return None, FIELD_STATUS_INVALID, "enumeration value not allowed"
    if ftype == "date":
        # Prefer ISO.
        iso = _ISO_DATE.search(text)
        if iso:
            y, mo, d = map(int, iso.groups())
            try:
                date(y, mo, d)
            except ValueError:
                return None, FIELD_STATUS_INVALID, "invalid calendar date"
            return f"{y:04d}-{mo:02d}-{d:02d}", "ok", None
        us = _US_DATE.search(text)
        if us:
            a, b, y = map(int, us.groups())
            # Ambiguous when both parts <= 12.
            if a <= 12 and b <= 12 and a != b:
                if field.get("allow_ambiguous", True):
                    return text.strip()[:40], FIELD_STATUS_AMBIGUOUS, "ambiguous MDY/DMY date"
                return None, FIELD_STATUS_AMBIGUOUS, "ambiguous date rejected"
            # Heuristic US when first > 12 impossible -> DMY, etc. Do not invent.
            if a > 12 and b <= 12:
                # day/month/year
                try:
                    date(y, b, a)
                except ValueError:
                    return None, FIELD_STATUS_INVALID, "invalid calendar date"
                return f"{y:04d}-{b:02d}-{a:02d}", "ok", None
            if b > 12 and a <= 12:
                try:
                    date(y, a, b)
                except ValueError:
                    return None, FIELD_STATUS_INVALID, "invalid calendar date"
                return f"{y:04d}-{a:02d}-{b:02d}", "ok", None
            if field.get("allow_ambiguous", True):
                return text.strip()[:40], FIELD_STATUS_AMBIGUOUS, "ambiguous date form"
            return None, FIELD_STATUS_AMBIGUOUS, "ambiguous date rejected"
        # Named / freeform — keep source form as ambiguous rather than guessing.
        if any(ch.isdigit() for ch in text):
            return text.strip()[:80], FIELD_STATUS_AMBIGUOUS, "non-ISO date retained as source form"
        return None, FIELD_STATUS_INVALID, "date not recognized"
    return None, FIELD_STATUS_INVALID, f"unsupported type {ftype}"


def _field_result(
    *,
    field_id: str,
    status: str,
    normalized: Any = None,
    original: Optional[str] = None,
    source_span: Optional[str] = None,
    excerpt: Optional[Mapping[str, Any]] = None,
    method: str = "none",
    note: Optional[str] = None,
    candidates: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    out: Dict[str, Any] = {
        "field_id": field_id,
        "status": status,
        "normalized_value": normalized,
        "original_source_value": original,
        "source_span": source_span,
        "source_document": (excerpt or {}).get("relative_path"),
        "excerpt_sha256": (excerpt or {}).get("excerpt_sha256"),
        "source_sha256": (excerpt or {}).get("source_sha256"),
        "folder_fingerprint": (excerpt or {}).get("folder_fingerprint"),
        "validation": status == FIELD_STATUS_VERIFIED,
        "extraction_method": method,
        "uncertainty": note,
        "candidates": candidates or [],
    }
    return out


def _verify_span_in_excerpt(span: str, excerpt_text: str) -> bool:
    if not span or not excerpt_text:
        return False
    if span in excerpt_text:
        return True
    return span.casefold() in excerpt_text.casefold()


def extract_field_deterministic(
    field: Mapping[str, Any],
    excerpts: Sequence[Mapping[str, Any]],
) -> Dict[str, Any]:
    fid = field["id"]
    ftype = field["type"]
    labels = field.get("labels") or [fid.replace("_", " ")]
    hits = _find_labeled_spans(excerpts, labels)
    if not hits:
        return _field_result(field_id=fid, status=FIELD_STATUS_MISSING, method="deterministic_label")

    parsed: List[Dict[str, Any]] = []
    for hit in hits:
        if ftype == "list":
            parts = re.split(r"[,;]", hit["value_raw"])
            items = []
            item_type = field.get("item_type") or "string"
            item_field = dict(field)
            item_field["type"] = item_type
            for part in parts[: int(field.get("max_items") or 8)]:
                part = part.strip()
                if not part:
                    continue
                n, s, _ = _normalize_scalar(item_type, part, item_field)
                if s == "ok" and n is not None:
                    items.append(n)
            if not items:
                continue
            norm, st, note = items, "ok", None
        else:
            norm, st, note = _normalize_scalar(ftype, hit["value_raw"], field)
        if st == "ok" and norm is not None:
            if not _verify_span_in_excerpt(hit["source_span"], hit["excerpt"]["excerpt"]):
                continue
            parsed.append(
                {
                    "normalized": norm,
                    "original": hit["value_raw"],
                    "span": hit["source_span"],
                    "excerpt": hit["excerpt"],
                    "note": note,
                }
            )
        elif st in {FIELD_STATUS_AMBIGUOUS, FIELD_STATUS_UNCERTAIN}:
            parsed.append(
                {
                    "normalized": norm,
                    "original": hit["value_raw"],
                    "span": hit["source_span"],
                    "excerpt": hit["excerpt"],
                    "note": note,
                    "status": st,
                }
            )

    if not parsed:
        return _field_result(
            field_id=fid,
            status=FIELD_STATUS_MISSING,
            method="deterministic_label",
            note="label found but value failed type validation",
            candidates=[
                {"original": h["value_raw"], "span": h["source_span"]} for h in hits[:4]
            ],
        )

    # Ambiguous / uncertain single hit
    if len(parsed) == 1 and parsed[0].get("status") in {
        FIELD_STATUS_AMBIGUOUS,
        FIELD_STATUS_UNCERTAIN,
    }:
        p = parsed[0]
        return _field_result(
            field_id=fid,
            status=p["status"],
            normalized=p["normalized"],
            original=p["original"],
            source_span=p["span"],
            excerpt=p["excerpt"],
            method="deterministic_label",
            note=p.get("note"),
        )

    verified_like = [p for p in parsed if not p.get("status")]
    if not verified_like:
        p = parsed[0]
        return _field_result(
            field_id=fid,
            status=p.get("status") or FIELD_STATUS_UNCERTAIN,
            normalized=p["normalized"],
            original=p["original"],
            source_span=p["span"],
            excerpt=p["excerpt"],
            method="deterministic_label",
            note=p.get("note"),
            candidates=[
                {"normalized": x["normalized"], "original": x["original"]} for x in parsed
            ],
        )

    norms = [json.dumps(p["normalized"], sort_keys=True, default=str) for p in verified_like]
    unique = set(norms)
    if len(unique) > 1:
        return _field_result(
            field_id=fid,
            status=FIELD_STATUS_CONFLICTING,
            method="deterministic_label",
            note="multiple distinct labeled values",
            candidates=[
                {
                    "normalized": p["normalized"],
                    "original": p["original"],
                    "source_document": p["excerpt"].get("relative_path"),
                    "source_span": p["span"],
                }
                for p in verified_like[:6]
            ],
        )
    p = verified_like[0]
    return _field_result(
        field_id=fid,
        status=FIELD_STATUS_VERIFIED,
        normalized=p["normalized"],
        original=p["original"],
        source_span=p["span"],
        excerpt=p["excerpt"],
        method="deterministic_label",
    )


def extraction_model_prompt(
    schema: Mapping[str, Any],
    excerpts: Sequence[Mapping[str, Any]],
) -> str:
    compact_ex = [
        {
            "relative_path": e.get("relative_path"),
            "excerpt": e.get("excerpt"),
        }
        for e in excerpts
    ]
    fields = [
        {"id": f["id"], "type": f["type"], "labels": f.get("labels") or []}
        for f in schema.get("fields") or []
    ]
    return (
        "Extract typed fields from the excerpts. Only use text that appears verbatim. "
        "For each field return value and source_span copied from an excerpt. "
        "Do not invent values. Do not claim verification.\n"
        f"Schema fields: {json.dumps(fields, ensure_ascii=True)}\n"
        f"Excerpts: {json.dumps(compact_ex, ensure_ascii=True)}\n"
        'Return JSON only: {"fields":{"field_id":{"value":"...","source_span":"...","relative_path":"..."}}}'
    )


def parse_model_extraction_candidates(raw: str) -> Dict[str, Dict[str, Any]]:
    cleaned = (raw or "").strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    match = re.search(r"\{.*\}", cleaned, flags=re.DOTALL)
    if match:
        cleaned = match.group(0)
    try:
        parsed = json.loads(cleaned)
    except (ValueError, TypeError) as exc:
        raise ExtractionError("model extraction JSON invalid") from exc
    if not isinstance(parsed, dict):
        raise ExtractionError("model extraction payload invalid")
    fields = parsed.get("fields")
    if not isinstance(fields, dict):
        raise ExtractionError("model extraction fields missing")
    out: Dict[str, Dict[str, Any]] = {}
    for key, val in list(fields.items())[:MAX_SCHEMA_FIELDS]:
        if not isinstance(key, str) or not isinstance(val, dict):
            continue
        out[key] = {
            "value": str(val.get("value") or "")[:400],
            "source_span": str(val.get("source_span") or "")[:240],
            "relative_path": str(val.get("relative_path") or "")[:200],
        }
    return out


def apply_model_candidate(
    field: Mapping[str, Any],
    candidate: Mapping[str, Any],
    excerpts: Sequence[Mapping[str, Any]],
) -> Optional[Dict[str, Any]]:
    span = str(candidate.get("source_span") or "").strip()
    value = str(candidate.get("value") or "").strip()
    if not span or not value:
        return None
    rel = str(candidate.get("relative_path") or "")
    matched_ex = None
    for ex in excerpts:
        if rel and ex.get("relative_path") == rel and _verify_span_in_excerpt(span, ex["excerpt"]):
            matched_ex = ex
            break
    if matched_ex is None:
        for ex in excerpts:
            if _verify_span_in_excerpt(span, ex["excerpt"]):
                matched_ex = ex
                break
    if matched_ex is None:
        return None  # invented span
    # Value must appear in the span or excerpt (transformation still host-validated).
    if (
        value.casefold() not in span.casefold()
        and value.casefold() not in matched_ex["excerpt"].casefold()
    ):
        # Allow currency without $ in value.
        digits = re.sub(r"[^0-9.]", "", value)
        if not digits or digits not in span.replace(",", ""):
            return None
    ftype = field["type"]
    if ftype == "list":
        return None  # lists stay deterministic for now
    norm, st, note = _normalize_scalar(ftype, value, field)
    if st == "ok" and norm is not None:
        return _field_result(
            field_id=field["id"],
            status=FIELD_STATUS_VERIFIED,
            normalized=norm,
            original=value,
            source_span=span,
            excerpt=matched_ex,
            method="model_candidate_host_verified",
        )
    if st in {FIELD_STATUS_AMBIGUOUS, FIELD_STATUS_UNCERTAIN}:
        return _field_result(
            field_id=field["id"],
            status=st,
            normalized=norm,
            original=value,
            source_span=span,
            excerpt=matched_ex,
            method="model_candidate_host_verified",
            note=note,
        )
    return None


def extract_fields(
    *,
    schema: Mapping[str, Any],
    excerpts: Sequence[Mapping[str, Any]],
    model: Any = None,
    require_verified_required: bool = True,
) -> Dict[str, Any]:
    """Run deterministic extraction, optionally model-assisted fill for gaps."""
    schema_v = validate_extraction_schema(schema)
    excerpts_v = normalize_excerpts(list(excerpts))
    results: Dict[str, Dict[str, Any]] = {}
    for field in schema_v["fields"]:
        results[field["id"]] = extract_field_deterministic(field, excerpts_v)

    need_model = [
        f
        for f in schema_v["fields"]
        if results[f["id"]]["status"]
        in {FIELD_STATUS_MISSING, FIELD_STATUS_INVALID}
        and f.get("required", True)
    ]
    model_attempted = False
    if need_model and model is not None:
        model_attempted = True
        try:
            from project_guardian.local_memory_chat import canonical

            prompt = extraction_model_prompt(schema_v, excerpts_v)
            raw = model.generate(
                [{"role": "user", "content": prompt}],
                json_mode=True,
            )
            candidates = parse_model_extraction_candidates(raw)
            for field in need_model:
                cand = candidates.get(field["id"])
                if not cand:
                    continue
                applied = apply_model_candidate(field, cand, excerpts_v)
                if applied is not None:
                    results[field["id"]] = applied
        except Exception:
            # Model failure does not invent values; keep deterministic outcomes.
            pass

    verified_count = sum(
        1 for r in results.values() if r["status"] == FIELD_STATUS_VERIFIED
    )
    required_missing = [
        f["id"]
        for f in schema_v["fields"]
        if f.get("required", True)
        and results[f["id"]]["status"] != FIELD_STATUS_VERIFIED
    ]
    ok = not required_missing if require_verified_required else True
    # Surface primary currency for downstream aggregate convenience.
    amount_usd = None
    for f in schema_v["fields"]:
        if f["type"] != "currency_amount":
            continue
        r = results[f["id"]]
        if r["status"] == FIELD_STATUS_VERIFIED and isinstance(r["normalized_value"], str):
            # Prefer fields whose id suggests unit price over total/shipping.
            if amount_usd is None or "unit" in f["id"] or "price" in f["id"]:
                if "total" in f["id"] or "ship" in f["id"]:
                    if amount_usd is None:
                        amount_usd = r["normalized_value"]
                else:
                    amount_usd = r["normalized_value"]
                    if "unit" in f["id"] or f["id"].endswith("_price"):
                        break

    return {
        "ok": ok,
        "capability": CAPABILITY_EXTRACT,
        "fields": results,
        "verified_field_count": verified_count,
        "required_unverified": required_missing,
        "amount_usd": amount_usd,
        "model_attempted": model_attempted,
        "verification_rule": "source_span_and_type_check",
        "created_utc": _utc_now(),
        "note": (
            "Schema validity is not factual correctness. "
            "Only fields with verified source spans are marked verified."
        ),
    }


def get_verified_field_amount(
    extraction: Mapping[str, Any],
    field_id: str,
) -> str:
    fields = extraction.get("fields") if isinstance(extraction.get("fields"), dict) else {}
    entry = fields.get(field_id)
    if not isinstance(entry, dict):
        raise ExtractionError(f"field not found: {field_id}")
    if entry.get("status") != FIELD_STATUS_VERIFIED:
        raise ExtractionError(f"field not verified: {field_id}")
    val = entry.get("normalized_value")
    if not isinstance(val, str) or not re.fullmatch(r"[0-9]{1,7}(?:\.[0-9]{1,2})?", val):
        raise ExtractionError(f"field is not a currency amount: {field_id}")
    return val


def validate_record_schema(raw: Any) -> Dict[str, Any]:
    """Record schema = field schema + optional row filters / key field."""
    base = validate_extraction_schema(raw)
    schema_id = raw.get("schema_id") or "record"
    if not isinstance(schema_id, str) or not re.fullmatch(r"[a-z][a-z0-9_]{0,39}", schema_id):
        raise ExtractionError("schema_id invalid")
    base["schema_id"] = schema_id
    key = raw.get("record_key_field")
    if key is not None:
        ids = {f["id"] for f in base["fields"]}
        if not isinstance(key, str) or key not in ids:
            raise ExtractionError("record_key_field must name a schema field")
        base["record_key_field"] = key
    exclude = raw.get("exclude_row_match")
    if exclude is not None:
        if not isinstance(exclude, list) or len(exclude) > 24:
            raise ExtractionError("exclude_row_match invalid")
        base["exclude_row_match"] = [
            str(x).strip().casefold() for x in exclude if str(x).strip()
        ][:24]
    start_labels = raw.get("record_start_labels")
    if start_labels is not None:
        if not isinstance(start_labels, list) or not start_labels or len(start_labels) > 8:
            raise ExtractionError("record_start_labels invalid")
        cleaned = []
        for lab in start_labels:
            if not isinstance(lab, str) or not lab.strip() or len(lab) > 80:
                raise ExtractionError("record_start_label invalid")
            cleaned.append(lab.strip())
        base["record_start_labels"] = cleaned
    return base


def _split_table_row(line: str) -> List[str]:
    text = line.strip()
    if text.startswith("|"):
        text = text[1:]
    if text.endswith("|"):
        text = text[:-1]
    parts = _TABLE_SPLIT.split(text)
    return [p.strip() for p in parts]


def parse_markdown_tables(text: str) -> List[Dict[str, Any]]:
    """Parse bounded GitHub-style markdown tables from excerpt text."""
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    tables: List[Dict[str, Any]] = []
    i = 0
    while i < len(lines) - 1:
        header_cells = _split_table_row(lines[i])
        sep = lines[i + 1] if i + 1 < len(lines) else ""
        if (
            len(header_cells) >= 2
            and any(h.strip() for h in header_cells)
            and _TABLE_SEP.match(sep or "")
        ):
            col_count = len(header_cells)
            if col_count > MAX_TABLE_COLS:
                raise ExtractionError("table has too many columns")
            rows = []
            j = i + 2
            malformed = False
            while j < len(lines):
                row_line = lines[j]
                if not row_line.strip() or not ("|" in row_line):
                    break
                if _TABLE_SEP.match(row_line):
                    j += 1
                    continue
                cells = _split_table_row(row_line)
                if len(cells) != col_count:
                    malformed = True
                    break
                rows.append(
                    {
                        "line_index": j,
                        "line_text": row_line.strip(),
                        "cells": cells,
                    }
                )
                if len(rows) >= MAX_RECORDS:
                    break
                j += 1
            if malformed:
                tables.append(
                    {
                        "ok": False,
                        "error": "inconsistent_column_count",
                        "headers": header_cells,
                        "header_line": i,
                        "rows": [],
                    }
                )
            else:
                tables.append(
                    {
                        "ok": True,
                        "headers": header_cells,
                        "header_line": i,
                        "rows": rows,
                    }
                )
            i = j
            continue
        i += 1
    return tables


def _header_to_field_map(
    headers: Sequence[str],
    fields: Sequence[Mapping[str, Any]],
) -> Dict[int, str]:
    mapping: Dict[int, str] = {}
    used_fields: set = set()
    for idx, header in enumerate(headers):
        h = header.strip().casefold()
        if not h:
            continue
        best = None
        for field in fields:
            fid = field["id"]
            if fid in used_fields:
                continue
            labels = [fid.replace("_", " ")] + list(field.get("labels") or [])
            for lab in labels:
                if lab.casefold() == h or lab.casefold() in h or h in lab.casefold():
                    best = fid
                    break
            if best:
                break
        if best:
            mapping[idx] = best
            used_fields.add(best)
    return mapping


def _row_excluded(cells: Sequence[str], exclude: Sequence[str]) -> bool:
    blob = " ".join(cells).casefold()
    return any(token and token in blob for token in exclude)


def _cell_field_result(
    field: Mapping[str, Any],
    cell: str,
    *,
    row_line: str,
    excerpt: Mapping[str, Any],
    header: str,
) -> Dict[str, Any]:
    fid = field["id"]
    # Span must be the cell text as it appears in the row line.
    cell_s = cell.strip()
    if not cell_s:
        return _field_result(field_id=fid, status=FIELD_STATUS_MISSING, method="table_cell")
    if cell_s not in row_line and cell_s.casefold() not in row_line.casefold():
        return _field_result(
            field_id=fid,
            status=FIELD_STATUS_INVALID,
            method="table_cell",
            note="cell value not present in row source span",
            original=cell_s,
        )
    norm, st, note = _normalize_scalar(field["type"], cell_s, field)
    span = cell_s
    # Prefer including header association in provenance note.
    if st == "ok" and norm is not None:
        return _field_result(
            field_id=fid,
            status=FIELD_STATUS_VERIFIED,
            normalized=norm,
            original=cell_s,
            source_span=span,
            excerpt=excerpt,
            method="table_cell",
            note=f"column={header}",
        )
    if st in {FIELD_STATUS_AMBIGUOUS, FIELD_STATUS_UNCERTAIN}:
        return _field_result(
            field_id=fid,
            status=st,
            normalized=norm,
            original=cell_s,
            source_span=span,
            excerpt=excerpt,
            method="table_cell",
            note=(note or "") + f"; column={header}",
        )
    return _field_result(
        field_id=fid,
        status=st if st != "ok" else FIELD_STATUS_INVALID,
        normalized=norm,
        original=cell_s,
        source_span=span,
        excerpt=excerpt,
        method="table_cell",
        note=note,
    )


def _stable_record_id(schema_id: str, source: str, location: str, key: str) -> str:
    raw = f"{schema_id}|{source}|{location}|{key}"
    return "rec_" + _sha(raw)[:12]


def extract_records_from_tables(
    schema: Mapping[str, Any],
    excerpts: Sequence[Mapping[str, Any]],
) -> List[Dict[str, Any]]:
    schema_v = validate_record_schema(schema)
    excerpts_v = normalize_excerpts(list(excerpts))
    exclude = schema_v.get("exclude_row_match") or [
        "total",
        "subtotal",
        "shipping",
        "grand total",
    ]
    records: List[Dict[str, Any]] = []
    for ex in excerpts_v:
        tables = parse_markdown_tables(ex["excerpt"])
        for t_idx, table in enumerate(tables):
            if not table.get("ok"):
                continue
            colmap = _header_to_field_map(table["headers"], schema_v["fields"])
            if not colmap:
                continue
            for row in table["rows"]:
                if _row_excluded(row["cells"], exclude):
                    continue
                fields_out: Dict[str, Dict[str, Any]] = {}
                for col_idx, fid in colmap.items():
                    field = next(f for f in schema_v["fields"] if f["id"] == fid)
                    fields_out[fid] = _cell_field_result(
                        field,
                        row["cells"][col_idx],
                        row_line=row["line_text"],
                        excerpt=ex,
                        header=table["headers"][col_idx],
                    )
                # Missing required fields not mapped from headers.
                for field in schema_v["fields"]:
                    if field["id"] not in fields_out:
                        fields_out[field["id"]] = _field_result(
                            field_id=field["id"],
                            status=FIELD_STATUS_MISSING,
                            method="table_cell",
                            note="column not mapped",
                        )
                key_field = schema_v.get("record_key_field")
                key_val = ""
                if key_field and fields_out.get(key_field, {}).get("normalized_value") is not None:
                    key_val = str(fields_out[key_field]["normalized_value"])
                else:
                    key_val = row["line_text"][:80]
                loc = f"table{t_idx}:line{row['line_index']}"
                statuses = {f["status"] for f in fields_out.values()}
                required_ok = all(
                    fields_out[f["id"]]["status"] == FIELD_STATUS_VERIFIED
                    for f in schema_v["fields"]
                    if f.get("required", True)
                )
                if FIELD_STATUS_CONFLICTING in statuses:
                    rec_status = FIELD_STATUS_CONFLICTING
                elif required_ok and FIELD_STATUS_AMBIGUOUS in statuses:
                    rec_status = FIELD_STATUS_AMBIGUOUS
                elif required_ok:
                    rec_status = FIELD_STATUS_VERIFIED
                else:
                    rec_status = FIELD_STATUS_MISSING
                records.append(
                    {
                        "record_id": _stable_record_id(
                            schema_v["schema_id"],
                            str(ex.get("relative_path")),
                            loc,
                            key_val,
                        ),
                        "schema_id": schema_v["schema_id"],
                        "source_document": ex.get("relative_path"),
                        "folder_fingerprint": ex.get("folder_fingerprint"),
                        "excerpt_sha256": ex.get("excerpt_sha256"),
                        "source_sha256": ex.get("source_sha256"),
                        "location": loc,
                        "row_source_span": row["line_text"][:400],
                        "status": rec_status,
                        "fields": fields_out,
                        "structure": "markdown_table",
                    }
                )
                if len(records) >= MAX_RECORDS:
                    return records
    return records


def extract_records_from_labeled_blocks(
    schema: Mapping[str, Any],
    excerpts: Sequence[Mapping[str, Any]],
) -> List[Dict[str, Any]]:
    """Repeated labeled text records separated by blank lines or start labels."""
    schema_v = validate_record_schema(schema)
    excerpts_v = normalize_excerpts(list(excerpts))
    start_labels = schema_v.get("record_start_labels") or []
    if not start_labels:
        # Default to first required field's labels.
        for f in schema_v["fields"]:
            if f.get("required", True):
                start_labels = list(f.get("labels") or [f["id"].replace("_", " ")])
                break
    if not start_labels:
        return []
    records: List[Dict[str, Any]] = []
    for ex in excerpts_v:
        body = ex["excerpt"]
        lines = body.replace("\r\n", "\n").split("\n")
        blocks: List[Tuple[int, List[str]]] = []
        current: List[str] = []
        start_line = 0
        for idx, line in enumerate(lines):
            is_start = False
            for lab in start_labels:
                if re.match(rf"(?i)^\s*{re.escape(lab)}\s*:", line):
                    is_start = True
                    break
            if is_start and current:
                blocks.append((start_line, current))
                current = [line]
                start_line = idx
            elif is_start and not current:
                current = [line]
                start_line = idx
            elif current:
                if not line.strip() and len(current) >= 1:
                    # blank line ends block if we already have content beyond start
                    if len(current) > 1:
                        blocks.append((start_line, current))
                        current = []
                    else:
                        current.append(line)
                else:
                    current.append(line)
        if current:
            blocks.append((start_line, current))

        for b_idx, (line_no, block_lines) in enumerate(blocks):
            block_text = "\n".join(block_lines).strip()
            if not block_text:
                continue
            # Reuse single-record deterministic extraction on a synthetic excerpt.
            mini = [
                {
                    **ex,
                    "excerpt": block_text,
                    "excerpt_sha256": _sha(block_text),
                }
            ]
            single = extract_fields(
                schema={"fields": schema_v["fields"]},
                excerpts=mini,
                require_verified_required=False,
            )
            fields_out = single["fields"]
            key_field = schema_v.get("record_key_field")
            key_val = ""
            if key_field and fields_out.get(key_field, {}).get("normalized_value") is not None:
                key_val = str(fields_out[key_field]["normalized_value"])
            else:
                key_val = block_text.split("\n", 1)[0][:80]
            required_ok = all(
                fields_out[f["id"]]["status"] == FIELD_STATUS_VERIFIED
                for f in schema_v["fields"]
                if f.get("required", True)
            )
            statuses = {f["status"] for f in fields_out.values()}
            if required_ok and FIELD_STATUS_AMBIGUOUS in statuses:
                rec_status = FIELD_STATUS_AMBIGUOUS
            elif required_ok:
                rec_status = FIELD_STATUS_VERIFIED
            else:
                rec_status = FIELD_STATUS_MISSING
            loc = f"block{b_idx}:line{line_no}"
            records.append(
                {
                    "record_id": _stable_record_id(
                        schema_v["schema_id"],
                        str(ex.get("relative_path")),
                        loc,
                        key_val,
                    ),
                    "schema_id": schema_v["schema_id"],
                    "source_document": ex.get("relative_path"),
                    "folder_fingerprint": ex.get("folder_fingerprint"),
                    "excerpt_sha256": ex.get("excerpt_sha256"),
                    "source_sha256": ex.get("source_sha256"),
                    "location": loc,
                    "row_source_span": block_text[:400],
                    "status": rec_status,
                    "fields": fields_out,
                    "structure": "labeled_block",
                }
            )
            if len(records) >= MAX_RECORDS:
                return records
    return records


def extract_records_from_bullets(
    schema: Mapping[str, Any],
    excerpts: Sequence[Mapping[str, Any]],
) -> List[Dict[str, Any]]:
    """Simple bullet lines with pipe- or semicolon-separated values mapped by field order/labels."""
    schema_v = validate_record_schema(schema)
    excerpts_v = normalize_excerpts(list(excerpts))
    records: List[Dict[str, Any]] = []
    fields = schema_v["fields"]
    for ex in excerpts_v:
        lines = ex["excerpt"].replace("\r\n", "\n").split("\n")
        for idx, line in enumerate(lines):
            m = _BULLET.match(line)
            if not m:
                continue
            body = m.group(1).strip()
            # Prefer "Label: value; Label: value" form inside bullet.
            if any(":" in body for _ in [0]):
                mini = [{**ex, "excerpt": body.replace(";", "\n"), "excerpt_sha256": _sha(body)}]
                # Normalize "a: b; c: d" into labeled lines.
                labeled = body.replace(";", "\n")
                mini = [{**ex, "excerpt": labeled, "excerpt_sha256": _sha(labeled)}]
                single = extract_fields(
                    schema={"fields": fields},
                    excerpts=mini,
                    require_verified_required=False,
                )
                fields_out = single["fields"]
            else:
                parts = [p.strip() for p in re.split(r"\s*\|\s*", body) if p.strip()]
                if len(parts) < 1:
                    continue
                fields_out = {}
                for i, field in enumerate(fields):
                    if i >= len(parts):
                        fields_out[field["id"]] = _field_result(
                            field_id=field["id"],
                            status=FIELD_STATUS_MISSING,
                            method="bullet_item",
                        )
                        continue
                    fields_out[field["id"]] = _cell_field_result(
                        field,
                        parts[i],
                        row_line=line,
                        excerpt=ex,
                        header=field["id"],
                    )
            required_ok = all(
                fields_out[f["id"]]["status"] == FIELD_STATUS_VERIFIED
                for f in fields
                if f.get("required", True)
            )
            statuses = {f["status"] for f in fields_out.values()}
            if required_ok and FIELD_STATUS_AMBIGUOUS in statuses:
                rec_status = FIELD_STATUS_AMBIGUOUS
            elif required_ok:
                rec_status = FIELD_STATUS_VERIFIED
            else:
                rec_status = FIELD_STATUS_MISSING
            key_field = schema_v.get("record_key_field")
            key_val = (
                str(fields_out.get(key_field, {}).get("normalized_value") or "")
                if key_field
                else body[:80]
            )
            loc = f"bullet:line{idx}"
            records.append(
                {
                    "record_id": _stable_record_id(
                        schema_v["schema_id"],
                        str(ex.get("relative_path")),
                        loc,
                        key_val,
                    ),
                    "schema_id": schema_v["schema_id"],
                    "source_document": ex.get("relative_path"),
                    "folder_fingerprint": ex.get("folder_fingerprint"),
                    "excerpt_sha256": ex.get("excerpt_sha256"),
                    "source_sha256": ex.get("source_sha256"),
                    "location": loc,
                    "row_source_span": line.strip()[:400],
                    "status": rec_status,
                    "fields": fields_out,
                    "structure": "bullet_list",
                }
            )
            if len(records) >= MAX_RECORDS:
                return records
    return records


def extract_records(
    *,
    schema: Mapping[str, Any],
    excerpts: Sequence[Mapping[str, Any]],
    model: Any = None,
    require_verified_required: bool = True,
    structures: Optional[Sequence[str]] = None,
) -> Dict[str, Any]:
    """Extract multiple typed records from tables, labeled blocks, and/or bullets."""
    schema_v = validate_record_schema(schema)
    allowed = set(structures or ("markdown_table", "labeled_block", "bullet_list"))
    records: List[Dict[str, Any]] = []
    if "markdown_table" in allowed:
        records.extend(extract_records_from_tables(schema_v, excerpts))
    if "labeled_block" in allowed and len(records) < MAX_RECORDS:
        more = extract_records_from_labeled_blocks(schema_v, excerpts)
        # Avoid duplicates by record_id
        seen = {r["record_id"] for r in records}
        for r in more:
            if r["record_id"] not in seen:
                records.append(r)
                seen.add(r["record_id"])
    if "bullet_list" in allowed and len(records) < MAX_RECORDS:
        more = extract_records_from_bullets(schema_v, excerpts)
        seen = {r["record_id"] for r in records}
        for r in more:
            if r["record_id"] not in seen:
                records.append(r)
                seen.add(r["record_id"])

    # Optional model assist only fills missing required fields on incomplete records
    # when deterministic extraction found a row/block but left gaps — still span-checked.
    model_attempted = False
    if model is not None:
        incomplete = [
            r
            for r in records
            if r["status"] != FIELD_STATUS_VERIFIED
        ]
        if incomplete and not records:
            model_attempted = True
            # Model may propose candidate table rows only as hints; host still parses source.
            # We intentionally do not accept invented rows without host table/list structure.
            pass

    # Deduplicate by key field value when conflicting duplicates appear.
    key_field = schema_v.get("record_key_field")
    if key_field:
        by_key: Dict[str, List[Dict[str, Any]]] = {}
        for r in records:
            kv = r.get("fields", {}).get(key_field, {}).get("normalized_value")
            if kv is None:
                continue
            by_key.setdefault(str(kv), []).append(r)
        for kv, group in by_key.items():
            if len(group) < 2:
                continue
            # Same key, different field values => mark conflicting
            payloads = [
                json.dumps(
                    {
                        fid: (f.get("normalized_value"))
                        for fid, f in g.get("fields", {}).items()
                    },
                    sort_keys=True,
                    default=str,
                )
                for g in group
            ]
            if len(set(payloads)) > 1:
                for g in group:
                    g["status"] = FIELD_STATUS_CONFLICTING
                    g["uncertainty"] = "duplicate record key with differing values"

    verified_records = [r for r in records if r["status"] == FIELD_STATUS_VERIFIED]
    if require_verified_required:
        ok = len(verified_records) >= 1 and all(
            r["status"] == FIELD_STATUS_VERIFIED for r in records if r["status"] not in {
                FIELD_STATUS_AMBIGUOUS  # allow ambiguous-only extras? no — require verified set non-empty
            }
        )
        # Success means at least one verified record; incomplete rows may remain flagged.
        ok = len(verified_records) >= 1
    else:
        ok = len(records) >= 1

    return {
        "ok": ok,
        "capability": CAPABILITY_EXTRACT_RECORDS,
        "schema_id": schema_v["schema_id"],
        "records": records[:MAX_RECORDS],
        "verified_record_count": len(verified_records),
        "record_count": len(records),
        "model_attempted": model_attempted,
        "verification_rule": "row_cell_span_and_type_check",
        "created_utc": _utc_now(),
        "note": (
            "Model proposals cannot invent rows. "
            "Only host-parsed table/list structures with verified cell spans are accepted."
        ),
    }


def _numeric_from_field(entry: Mapping[str, Any]) -> Decimal:
    if entry.get("status") != FIELD_STATUS_VERIFIED:
        raise ExtractionError("field not verified for line-item math")
    val = entry.get("normalized_value")
    if isinstance(val, dict) and "value" in val:
        return Decimal(str(val["value"]))
    if isinstance(val, int):
        return Decimal(val)
    if isinstance(val, str) and re.fullmatch(r"[0-9]{1,7}(?:\.[0-9]{1,4})?", val):
        return Decimal(val)
    raise ExtractionError("field is not numeric for line-item math")


def aggregate_record_line_items(
    records: Sequence[Mapping[str, Any]],
    *,
    quantity_field: str,
    unit_price_field: str,
) -> Dict[str, Any]:
    """Deterministic Σ(quantity × unit_price) over verified records only."""
    if not records:
        raise ExtractionError("no records to aggregate")
    total = Decimal("0.00")
    lines = []
    for rec in records:
        if rec.get("status") != FIELD_STATUS_VERIFIED:
            continue
        fields = rec.get("fields") if isinstance(rec.get("fields"), dict) else {}
        q_entry = fields.get(quantity_field)
        p_entry = fields.get(unit_price_field)
        if not isinstance(q_entry, dict) or not isinstance(p_entry, dict):
            raise ExtractionError("line-item fields missing on verified record")
        qty = _numeric_from_field(q_entry)
        price = _numeric_from_field(p_entry)
        ext = (qty * price).quantize(Decimal("0.01"))
        total += ext
        lines.append(
            {
                "record_id": rec.get("record_id"),
                "quantity": format(qty, "f"),
                "unit_price": format(price.quantize(Decimal("0.01")), "f"),
                "extension_usd": format(ext, "f"),
                "source_document": rec.get("source_document"),
                "row_source_span": rec.get("row_source_span"),
            }
        )
    if not lines:
        raise ExtractionError("no verified records eligible for line-item aggregation")
    subtotal = total.quantize(Decimal("0.01"))
    return {
        "ok": True,
        "capability": "compose.aggregate_usd",
        "mode": "record_line_items",
        "currency": "USD",
        "line_items": lines,
        "subtotal_usd": format(subtotal, "f"),
        "label": "verified line-item extension total",
        "verification_rule": "decimal_qty_times_price_sum",
        "created_utc": _utc_now(),
    }
