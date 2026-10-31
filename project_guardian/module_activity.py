from __future__ import annotations

import datetime as dt
from typing import Dict, Iterable, Optional, Tuple


_MODULE_ACTIVITY_GROUPS: Dict[str, Tuple[str, ...]] = {
    "income_modules": (
        "income_modules",
        "income",
        "income_generator",
        "wallet",
        "financial_manager",
        "revenue_creator",
    ),
}

_MODULE_ACTIVITY_ALIAS_TO_GROUP: Dict[str, str] = {}
for _group, _aliases in _MODULE_ACTIVITY_GROUPS.items():
    for _alias in _aliases:
        _MODULE_ACTIVITY_ALIAS_TO_GROUP[_alias] = _group


def module_activity_aliases(module_key: Optional[str]) -> Tuple[str, ...]:
    key = str(module_key or "").strip()
    if not key:
        return ()
    group = _MODULE_ACTIVITY_ALIAS_TO_GROUP.get(key, key)
    return _MODULE_ACTIVITY_GROUPS.get(group, (key,))


def _parse_timestamp(raw: object) -> Optional[dt.datetime]:
    if raw is None:
        return None
    try:
        text = str(raw).strip()
        if not text:
            return None
        parsed = dt.datetime.fromisoformat(text.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=dt.datetime.now().astimezone().tzinfo)
        return parsed
    except Exception:
        return None


def get_module_last_activity(
    module_last_invoked: Optional[Dict[str, str]],
    module_key: Optional[str],
) -> Optional[str]:
    used = module_last_invoked or {}
    aliases = module_activity_aliases(module_key)
    if not aliases:
        return None

    best_key: Optional[str] = None
    best_dt: Optional[dt.datetime] = None
    fallback_raw: Optional[str] = None
    for alias in aliases:
        raw = used.get(alias)
        if raw is None:
            continue
        fallback_raw = str(raw)
        parsed = _parse_timestamp(raw)
        if parsed is None:
            continue
        if best_dt is None or parsed > best_dt:
            best_dt = parsed
            best_key = alias
    if best_key is not None:
        return used.get(best_key)
    return fallback_raw


def mark_module_activity(
    module_last_invoked: Dict[str, str],
    module_key: Optional[str],
    when: Optional[dt.datetime] = None,
) -> Optional[str]:
    aliases = module_activity_aliases(module_key)
    if not aliases:
        return None
    moment = when or dt.datetime.now()
    stamp = moment.isoformat()
    for alias in aliases:
        module_last_invoked[alias] = stamp
    return stamp


def activity_age_minutes(
    module_last_invoked: Optional[Dict[str, str]],
    module_key: Optional[str],
    *,
    now: Optional[dt.datetime] = None,
) -> Optional[float]:
    raw = get_module_last_activity(module_last_invoked, module_key)
    parsed = _parse_timestamp(raw)
    if parsed is None:
        return None
    ref = now or dt.datetime.now(dt.timezone.utc)
    if ref.tzinfo is None:
        ref = ref.replace(tzinfo=dt.datetime.now().astimezone().tzinfo)
    return max(0.0, (ref - parsed).total_seconds() / 60.0)


def module_has_recent_activity(
    module_last_invoked: Optional[Dict[str, str]],
    module_key: Optional[str],
    *,
    max_age_minutes: float,
) -> bool:
    age = activity_age_minutes(module_last_invoked, module_key)
    return age is not None and age <= max_age_minutes
