# project_guardian/auto_learning.py
"""
Auto-Learning: Background data gathering on AI, income, and other topics.
Stores learned and compressed content on the thumb drive.
Quality gates: only high-quality items are admitted to long-term memory;
all items may be archived to disk for reference.
"""

import hashlib
import json
import logging
import os
import re
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple
from urllib.parse import quote

logger = logging.getLogger(__name__)

# Fail-closed when auto-learning has no autonomy-safe completion API; never use operator chat_with_llm.
AUTONOMY_LEARNING_NO_SAFE_LLM_PATH = "no_autonomy_safe_llm_path"


def _autonomy_learning_disabled_llm_callback(_msg: str, **_kwargs: Any) -> Tuple[str, str]:
    """Learning must not downgrade to operator-facing chat routing."""
    return ("", AUTONOMY_LEARNING_NO_SAFE_LLM_PATH)


def make_learning_llm_callback(system_ref: Any) -> Callable[..., Tuple[str, str]]:
    """
    LLM shim for ``run_learning_session`` / compression: plain ``(msg,)`` callers keep working,
    while :func:`compress_with_llm` can pass ``structured_role`` + ``prompt_extra``.
    """
    if hasattr(system_ref, "_autonomy_llm_completion"):
        def cb(msg: str, **kwargs: Any) -> Tuple[str, str]:
            max_t = int(kwargs.get("max_tokens") or 300)
            sr = kwargs.get("structured_role")
            sr_clean = str(sr).strip() if sr is not None and str(sr).strip() else None
            mod = str(kwargs.get("module_name") or "planner")
            ag = kwargs.get("agent_name")
            ag_kw = None if ag is None or str(ag).strip() == "" else (ag if isinstance(ag, str) else str(ag))
            return system_ref._autonomy_llm_completion(
                [{"role": "user", "content": msg}],
                max_t,
                module_name=mod,
                agent_name=ag_kw,
                prompt_extra=kwargs.get("prompt_extra"),
                structured_role=sr_clean,
                skip_capability_preamble=bool(sr_clean),
            )

        return cb
    if hasattr(system_ref, "_llm_completion"):
        def cb2(msg: str, **kwargs: Any) -> Tuple[str, str]:
            max_t = int(kwargs.get("max_tokens") or 300)
            sr = kwargs.get("structured_role")
            sr_clean = str(sr).strip() if sr is not None and str(sr).strip() else None
            mod = str(kwargs.get("module_name") or "planner")
            ag = kwargs.get("agent_name")
            ag_kw = None if ag is None or str(ag).strip() == "" else (ag if isinstance(ag, str) else str(ag))
            return system_ref._llm_completion(
                [{"role": "user", "content": msg}],
                max_t,
                module_name=mod,
                agent_name=ag_kw,
                prompt_extra=kwargs.get("prompt_extra"),
                structured_role=sr_clean,
                skip_capability_preamble=bool(sr_clean),
                require_autonomy_safe_reasoning=True,
            )

        return cb2
    return _autonomy_learning_disabled_llm_callback


# Source trust tiers: higher = more trusted, lower admission threshold
SOURCE_TRUST_TIERS = {
    "chatgpt": "high",
    "web": "medium",
    "rss": "medium",
    "wikipedia": "medium",
    "google": "medium",
    "moltbook": "medium",
    "reddit": "low",
    "facebook": "low",
    "twitter": "low",
}
# Default trust for unknown sources
DEFAULT_TRUST = "low"
WIKIPEDIA_BLOCK_COOLDOWN_SEC = 6 * 3600
REDDIT_BLOCK_COOLDOWN_SEC = 2 * 3600
CHATLOG_REVISIT_COOLDOWN_HOURS = 18.0
# Goal-matched chatlogs already processed today: require a longer quiet window before revisiting (reduces same-day churn).
CHATLOG_SAME_DAY_REVISIT_MIN_HOURS = 22.0
_WIKIPEDIA_BLOCK_UNTIL_TS = 0.0
_REDDIT_BLOCK_UNTIL_TS_BY_KEY: Dict[str, float] = {}

# Generic RSS/spam title patterns (reject)
TITLE_SPAM_PATTERNS = [
    r"^\[.*\]\s*$",
    r"^\.\.\.$",
    r"^(untitled|no title|n/a|---)$",
    r"^\s*https?://",
]

# Generic titles: do not use for title-based cross-session dedup (too many false positives)
GENERIC_TITLE_FOR_DEDUP = frozenset({
    "untitled", "no title", "n/a", "---", "...", "untitled document",
    "new post", "article", "blog post", "rss item", "feed item",
})
DEDUP_SNIPPET_LEN = 80

# Memory categories for admission gating (only operational + selected strategic admitted by default)
MEMORY_CATEGORY_OPERATIONAL = "operational"
MEMORY_CATEGORY_STRATEGIC = "strategic"
MEMORY_CATEGORY_CONVERSATIONAL = "conversational"
MEMORY_CATEGORY_CREATIVE = "creative"
MEMORY_CATEGORY_SPECULATIVE = "speculative"

# Patterns that indicate non-operational content (reject unless explicitly strategic/operational)
REJECT_LOW_VALUE_PATTERNS = [
    (r"\b(image|img|prompt|style|generate|dall-e|midjourney|stablediffusion)\b", "image_prompt"),
    (r"\b(chat summary|conversation summary|discussion about|we discussed|we talked)\b", "chat_summary"),
    (r"\b(what if|hypothetically|imagine|suppose|speculative|in theory)\b", "speculative"),
    (r"\b(style generation|art style|visual style|aesthetic)\b", "style_generation"),
    (r"\b(broad summary|general discussion|off-topic chat)\b", "generic_conversation"),
]
# Patterns that boost operational score (code, failures, fixes, module behavior, task outcomes)
OPERATIONAL_BOOST_PATTERNS = [
    (r"\b(code|bug|fix|failure|error|exception|runtime|deploy)\b", 2),
    (r"\b(module|guardian|elysia|memory|consolidat|trim)\b", 1),
    (r"\b(task outcome|task complete|mission progress)\b", 2),
    (r"\b(user priority|operator said|critical for)\b", 1),
]
WEAK_CONTENT_THRESHOLD = 60  # compressed < this = "weak content", title is main signal
MIN_LEXICAL_OVERLAP_RATIO = 0.5  # for snippet overlap check

# Default topics and sources
DEFAULT_TOPICS = ["AI", "artificial intelligence", "machine learning", "income", "passive income", "automation", "technology"]
REDDIT_SUBREDDIT_ALIASES = {
    "artificialintelligence": "artificial",
}
DEFAULT_REDDIT_SUBS = ["MachineLearning", "artificial", "passive_income", "SideProject", "Entrepreneur", "automation"]
# Round-1 empty-plan fallback in ``run_mistral_chained_learning_session`` only (not general sessions).
# Broader ``DEFAULT_REDDIT_SUBS`` / config ``reddit_subs`` often include monetization/low-signal subs that are too noisy on boot.
CHAINED_EMPTY_PLAN_REDDIT_SEEDS = ["MachineLearning", "artificial", "LocalLLaMA"]
DEFAULT_RSS_FEEDS = [
    "https://feeds.feedburner.com/TechCrunch",
    "https://www.wired.com/feed/rss",
    "https://machinelearningmastery.com/feed/",
]
# Facebook: page IDs or usernames (e.g. "Meta", "TechCrunch"). Requires facebook_access_token in config or FACEBOOK_ACCESS_TOKEN env.
DEFAULT_FACEBOOK_PAGES: List[str] = []
# X (Twitter): search queries for recent tweets. Requires twitter_bearer_token in config or TWITTER_BEARER_TOKEN env.
DEFAULT_TWITTER_SEARCH_QUERIES: List[str] = []
DEFAULT_CHATLOG_GOAL_TERMS = ["Elysia goals", "set goals", "next steps"]
CHAINED_CONTEXT_BASE_MAX_CHARS = 4200
CHAINED_CONTEXT_TOTAL_MAX_CHARS = 5600
CHAINED_CONTEXT_MAX_ROUND_SUMMARIES = 4
DEFAULT_CHAINED_MAX_CHATLOGS = 6
DEFAULT_CHAINED_CHATLOG_BACKFILL_CAP = 2
DEFAULT_CHAINED_CHATLOG_REVISIT_CAP = 3
DEFAULT_CHAINED_CHATLOG_LLM_RERANK_TOP_N = 4
DEFAULT_CHAINED_SOCIAL_REPEAT_COOLDOWN_HOURS = 24
CHAINED_SOCIAL_SEEN_FILENAME = ".chained_social_seen.json"
CHAINED_MOLTBOOK_STATE_FILENAME = ".chained_moltbook_state.json"
DEFAULT_CHAINED_MOLTBOOK_COOLDOWN_HOURS = 24
CHAINED_LEARNING_INTERNAL_TERMS = ("elysia", "project guardian")
# Planner strings that center on identity / fictional communities rather than grounded operator work.
CHAINED_PLAN_SELF_REF_REGEXES = [
    re.compile(r"\b(self[- ]aware|sentien|conscious(?:ness)?)\b.{0,48}\b(ai|llm|agent|model)\b", re.I),
    re.compile(r"\b(ai beings|agi community|hallucinated|simulated society)\b", re.I),
    re.compile(r"\bwho am i\b", re.I),
    re.compile(r"\belysia's (?:soul|consciousness|identity|community)\b", re.I),
    re.compile(r"\b(lore|origin story).{0,40}\belysia\b", re.I),
]
CHAINED_LEARNING_DISCOVERY_REDDIT_SUBS = [
    "MachineLearning",
    "ArtificialIntelligence",
    "LocalLLaMA",
    "OpenAI",
    "ChatGPT",
    "singularity",
    "selfhosted",
    "compsci",
    "deeplearning",
    "automation",
]
CHAINED_LEARNING_WIKI_TOPIC_MAP = {
    "ai": "Artificial intelligence",
    "artificial intelligence": "Artificial intelligence",
    "machine learning": "Machine learning",
    "llm": "Large language model",
    "large language model": "Large language model",
    "automation": "Automation",
    "api": "API",
    "compute": "Cloud computing",
    "technology": "Technology",
}
CHAINED_QUERY_SIGNAL_PATTERNS = [
    (r"\bcustomer complaints?\b", 4),
    (r"\bpain points?\b", 4),
    (r"\bservice ideas?\b", 3),
    (r"\bapi grants?\b", 3),
    (r"\bcompute credits?\b", 3),
    (r"\bautomation\b", 2),
    (r"\bai agents?\b", 1),
]
CHATLOG_ACTIONABLE_PATTERNS = [
    (r"\bset goals?\b", 5),
    (r"\bnext steps?\b", 5),
    (r"\bneed(?:s|ed)? to\b", 4),
    (r"\bshould\b", 2),
    (r"\bplan(?:ning|ned)?\b", 3),
    (r"\bpriority|priorities\b", 4),
    (r"\bservice(?: idea| offer)?\b", 3),
    (r"\bcustomer complaints?\b", 4),
    (r"\bpain points?\b", 4),
    (r"\bcompute\b", 3),
    (r"\bapi\b", 2),
    (r"\bautomation\b", 3),
    (r"\boperator\b", 3),
    (r"\bship(?:ping|ped)?\b", 3),
    (r"\bfix(?:es|ed)?\b", 3),
    (r"\bimplement(?:ed|ation)?\b", 3),
    (r"\bworkflow\b", 2),
    (r"\brevenue|income|pricing|offer\b", 3),
    (r"\bgrants?|credits?\b", 2),
]
CHATLOG_WEAK_SEARCH_TERMS = frozenset({
    "elysia",
    "project guardian",
    "projectguardian",
    "guardian core",
    "autonomy",
    "income",
})
# Fenced blocks / obvious code shapes in ChatGPT exports (boost ranking, not weak-term overlap).
CHATLOG_CODE_SIGNAL_PATTERNS = [
    (r"```[a-z0-9]*\s*\n", 10),
    (r"\n```", 4),
    (r"\bdef\s+\w+\s*\(", 7),
    (r"\bclass\s+\w+\s*[:\(]", 6),
    (r"\bimport\s+[a-zA-Z0-9_.]+\b", 5),
    (r"\bfrom\s+\w+\s+import\b", 5),
    (r"\b(public\s+static|private\s+static|function\s+\w+\s*\()", 5),
    (r"\b(const|let|var)\s+\w+\s*=", 3),
    (r"\basync\s+function\b", 4),
]
# Injected first so long chatlog_goal_terms lists do not crowd out Elysia/Guardian/code proxies.
CHATLOG_ALWAYS_RANK_TERMS = (
    "elysia",
    "project guardian",
    "projectguardian",
    "python",
    "typescript",
    "javascript",
)
CHATLOG_GENERIC_PENALTY_PATTERNS = [
    (r"\bfictional self-aware ai\b", 6),
    (r"\bself-aware ai\b", 4),
    (r"\bconscious(?:ness)?\b", 3),
    (r"\bsentien(?:ce|t)\b", 3),
    (r"\bphilosoph(?:y|ical)\b", 3),
    (r"\broleplay\b", 4),
    (r"\bstory|lore|origin story|poem\b", 4),
    (r"\bwho is elysia\b", 4),
    (r"\bimagine\b", 2),
    (r"\bwhat if\b", 3),
]
SOCIAL_DEMAND_PATTERNS = [
    (r"\bcomplain(?:t|ts|ing)?\b", 3),
    (r"\bpain points?\b", 3),
    (r"\bfrustrat(?:ed|ing|ion)\b", 2),
    (r"\bmanual(?:ly)?\b", 2),
    (r"\btime[- ]?consuming\b", 2),
    (r"\bbottleneck\b", 2),
    (r"\bneed(?:s|ed)?\b", 1),
    (r"\blooking for\b", 1),
    (r"\banyone know\b", 1),
    (r"\bwish (?:there was|someone)\b", 2),
    (r"\bautomate\b", 2),
    (r"\bworkflow\b", 1),
    (r"\bapi grants?\b", 2),
    (r"\bcompute credits?\b", 2),
    (r"\bhiring\b", 1),
    (r"\bhard to hire\b", 2),
    (r"\bstruggl\w* to hire\b", 2),
    (r"\bcan't find\b", 2),
    (r"\brequest for\b", 2),
    (r"\bfeature request\b", 2),
    (r"\bmissing\b", 1),
    (r"\bworkaround\b", 2),
    (r"\bservice gap\b", 3),
    (r"\bno good tool\b", 2),
]
SOCIAL_LOW_SIGNAL_PATTERNS = [
    (r"\bas i work with\b", 3),
    (r"\bi built\b", 2),
    (r"\bmy tool\b", 2),
    (r"\bcheck out\b", 2),
    (r"\bnewsletter\b", 2),
    (r"\bdm me\b", 2),
    (r"\bfollow me\b", 2),
    (r"\bhere's what i learned\b", 1),
]
# Generic AI hype / launch threads — penalize vs. complaint / hiring / tooling pain signals.
SOCIAL_GENERIC_CHATTER_PATTERNS = [
    (r"\b(new model|gpt-4|gpt-5|gpt4|gpt5|chatgpt|claude|llama\s*3|gemini)\b.*\b(launch|released|drop|shipping)\b", 3),
    (r"\bexcited to announce\b", 2),
    (r"\bfollow (?:us|me) (?:on|for)\b", 2),
    (r"\bintroducing our\b", 2),
    (r"\bstate of ai\b", 2),
    (r"\bai newsletter\b", 2),
    (r"\b100x\b", 1),
    (r"\bagi is (?:here|near)\b", 2),
]


def get_learned_storage_path(config: Optional[Dict] = None) -> Path:
    """Resolve learned data path on thumb drive; falls back to LOCALAPPDATA if drive unavailable."""
    try:
        from .external_storage import normalize_storage_root
        cfg_path = Path(__file__).parent.parent / "config" / "external_storage.json"
        if cfg_path.exists():
            with open(cfg_path, "r") as f:
                ext = json.load(f)
            base = normalize_storage_root((ext.get("external_drive") or "").strip())
            if base and Path(base).exists():
                out = Path(base) / "ProjectGuardian" / "memory" / "learned"
                out.mkdir(parents=True, exist_ok=True)
                return out
            if base:
                logger.debug(f"[Auto-Learning] External drive {base} not available, using local storage")
    except Exception as e:
        logger.debug(f"External storage config: {e}")
    fallback = Path(os.environ.get("LOCALAPPDATA", ".")) / "ProjectGuardian" / "learned"
    fallback.mkdir(parents=True, exist_ok=True)
    return fallback


def get_chatlogs_path() -> Path:
    """ChatGPT/personal conversation files; falls back to LOCALAPPDATA if drive unavailable."""
    try:
        from .external_storage import normalize_storage_root
        cfg_path = Path(__file__).parent.parent / "config" / "external_storage.json"
        if cfg_path.exists():
            with open(cfg_path, "r") as f:
                ext = json.load(f)
            base = normalize_storage_root((ext.get("external_drive") or "").strip())
            if base and Path(base).exists():
                out = Path(base) / "ProjectGuardian" / "memory" / "personal" / "chatlogs"
                out.mkdir(parents=True, exist_ok=True)
                return out
    except Exception:
        pass
    fallback = Path(os.environ.get("LOCALAPPDATA", ".")) / "ProjectGuardian" / "personal" / "chatlogs"
    fallback.mkdir(parents=True, exist_ok=True)
    return fallback


def resolve_chatlog_search_terms(
    topics: Optional[List[str]] = None,
    *,
    cfg: Optional[Dict[str, Any]] = None,
    explicit_terms: Optional[List[str]] = None,
) -> List[str]:
    """Stable ordered goal terms for ranking ChatGPT exports."""
    actionable_terms: List[str] = []
    neutral_terms: List[str] = []
    weak_terms: List[str] = []
    seen: set[str] = set()
    sources = [
        explicit_terms or [],
        (cfg or {}).get("chatlog_goal_terms") or [],
        (cfg or {}).get("chatlog_search_terms") or [],
        DEFAULT_CHATLOG_GOAL_TERMS,
        topics or [],
    ]
    for raw_terms in sources:
        for raw in raw_terms:
            term = re.sub(r"\s+", " ", str(raw or "").strip())
            if len(term) < 3:
                continue
            key = term.lower()
            if key in seen:
                continue
            seen.add(key)
            term_out = term[:80]
            if key in CHATLOG_WEAK_SEARCH_TERMS:
                weak_terms.append(term_out)
            elif any(re.search(pattern, key) for pattern, _ in CHATLOG_ACTIONABLE_PATTERNS):
                actionable_terms.append(term_out)
            else:
                neutral_terms.append(term_out)
    out = actionable_terms + neutral_terms
    weak_room = max(0, 24 - len(out))
    if len(out) < 10:
        out.extend(weak_terms[:weak_room])
    elif not actionable_terms and weak_room > 0:
        out.extend(weak_terms[: min(2, weak_room)])
    injected: List[str] = []
    blob = " ".join(str(x or "").lower() for x in out)
    blob_nospace = re.sub(r"\s+", "", blob)
    for raw in CHATLOG_ALWAYS_RANK_TERMS:
        term = re.sub(r"\s+", " ", str(raw or "").strip())
        if len(term) < 3:
            continue
        key = term.lower()
        if key in seen:
            continue
        if key == "elysia" and "elysia" in blob:
            continue
        if key == "project guardian" and "project guardian" in blob:
            continue
        if key == "projectguardian" and (
            "projectguardian" in blob_nospace or "project guardian" in blob
        ):
            continue
        seen.add(key)
        injected.append(term[:80])
    if injected:
        out = injected + out
    return out[:24]


def _normalized_learning_phrase(raw: Any, *, max_chars: int = 120) -> str:
    text = re.sub(r"\s+", " ", str(raw or "").strip())
    text = re.sub(r"^[#@]+", "", text)
    return text[:max_chars]


def _canonicalize_reddit_subreddit(raw: Any) -> str:
    sub = re.sub(r"[^A-Za-z0-9_]", "", str(raw or "").strip())[:50]
    if not sub:
        return ""
    alias = REDDIT_SUBREDDIT_ALIASES.get(sub.lower())
    return alias if alias else sub


def _text_signal_score(text: str, patterns: List[Tuple[str, int]]) -> int:
    lower = (text or "").lower()
    return sum(weight for pattern, weight in patterns if re.search(pattern, lower))


def _is_internal_only_learning_phrase(text: str) -> bool:
    lowered = text.lower()
    if not any(term in lowered for term in CHAINED_LEARNING_INTERNAL_TERMS):
        return False
    return not any(re.search(pattern, lowered) for pattern, _ in CHAINED_QUERY_SIGNAL_PATTERNS)


def _build_learning_query_terms(
    topics: Optional[List[str]],
    cfg: Optional[Dict[str, Any]],
    seed_twitter_queries: Optional[List[str]],
) -> List[str]:
    terms: List[str] = []
    seen: set[str] = set()
    sources = [
        topics or [],
        (cfg or {}).get("topics") or [],
        (cfg or {}).get("learning_target_terms") or [],
        seed_twitter_queries or [],
        (cfg or {}).get("twitter_search_queries") or [],
    ]
    for raw_terms in sources:
        for raw in raw_terms:
            phrase = _normalized_learning_phrase(raw, max_chars=80)
            if len(phrase) < 3:
                continue
            key = phrase.lower()
            if key in seen:
                continue
            seen.add(key)
            if key not in CHAINED_LEARNING_INTERNAL_TERMS:
                terms.append(phrase)
            for token in re.split(r"[^\w]+", phrase.lower()):
                if len(token) < 4 or token in seen or token in {"elysia", "project", "guardian"}:
                    continue
                seen.add(token)
                terms.append(token)
    return terms[:40]


def learning_run_duplicate_saturated(session: Dict[str, Any]) -> bool:
    """True when rejections are mostly prior-corpus duplicates (low-yield), not adversarial noise."""
    rej = int(session.get("rejected") or 0)
    if rej <= 0:
        return False
    bd = session.get("rejection_breakdown")
    if isinstance(bd, dict):
        dup = int(bd.get("cross_session_duplicate") or 0)
        if dup / rej >= 0.65:
            return True
    csd = int(session.get("cross_session_duplicates") or 0)
    if csd >= max(4, int(0.55 * rej)):
        return True
    return False


def _chained_plan_target_self_referential(text: str, *, whitelist: Optional[set[str]] = None) -> bool:
    raw = _normalized_learning_phrase(text, max_chars=220).strip()
    if not raw:
        return False
    lowered = raw.lower()
    if whitelist and lowered in whitelist:
        return False
    if any(term in lowered for term in CHAINED_LEARNING_INTERNAL_TERMS):
        return True
    for rx in CHAINED_PLAN_SELF_REF_REGEXES:
        if rx.search(lowered):
            return True
    return False


def _score_learning_query(query: str, query_terms: List[str]) -> int:
    text = _normalized_learning_phrase(query, max_chars=90)
    lowered = text.lower()
    score = 0
    words = [w for w in re.split(r"[^\w]+", lowered) if w]
    if 2 <= len(words) <= 7:
        score += 1
    elif len(words) > 10:
        score -= 1
    if any(term in lowered for term in query_terms):
        score += 2
    for pattern, bonus in CHAINED_QUERY_SIGNAL_PATTERNS:
        if re.search(pattern, lowered):
            score += bonus
    if _is_internal_only_learning_phrase(text):
        score -= 6
    if re.search(r"[(){}\[\]]", text):
        score -= 1
    if "roadmap" in lowered and any(term in lowered for term in CHAINED_LEARNING_INTERNAL_TERMS):
        score -= 2
    return score


def _best_seed_learning_queries(
    seed_twitter_queries: Optional[List[str]],
    cfg: Optional[Dict[str, Any]],
    query_terms: List[str],
    *,
    limit: int,
) -> List[str]:
    candidates: List[Tuple[int, int, str]] = []
    raw_queries = list(seed_twitter_queries or []) + list((cfg or {}).get("twitter_search_queries") or [])
    seen: set[str] = set()
    for idx, raw in enumerate(raw_queries):
        text = _normalized_learning_phrase(raw, max_chars=90)
        if len(text) < 3:
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        score = _score_learning_query(text, query_terms)
        if score < 2:
            continue
        candidates.append((score, -idx, text))
    candidates.sort(reverse=True)
    return [text for _, _, text in candidates[:limit]]


def _allowed_chained_reddit_subs(
    cfg: Optional[Dict[str, Any]],
    default_reddit_subs: Optional[List[str]],
) -> Dict[str, str]:
    allowed: Dict[str, str] = {}
    sources = [
        CHAINED_EMPTY_PLAN_REDDIT_SEEDS,
        CHAINED_LEARNING_DISCOVERY_REDDIT_SUBS,
        (cfg or {}).get("reddit_subs") or [],
        default_reddit_subs or [],
    ]
    for raw_terms in sources:
        for raw in raw_terms:
            sub = _canonicalize_reddit_subreddit(raw)
            if not sub:
                continue
            allowed.setdefault(sub.lower(), sub)
    return allowed


def _best_seed_reddit_subs(
    cfg: Optional[Dict[str, Any]],
    allowed_subs: Dict[str, str],
    *,
    limit: int,
) -> List[str]:
    raw_override = (cfg or {}).get("mistral_chained_empty_plan_reddit_subs")
    seed_source = raw_override if isinstance(raw_override, list) and raw_override else CHAINED_EMPTY_PLAN_REDDIT_SEEDS
    out: List[str] = []
    seen: set[str] = set()
    for raw in seed_source:
        sub = _canonicalize_reddit_subreddit(raw)
        canon = allowed_subs.get(sub.lower())
        if not canon or canon.lower() in seen:
            continue
        seen.add(canon.lower())
        out.append(canon)
    return out[:limit]


def _fallback_wikipedia_titles(
    topics: Optional[List[str]],
    cfg: Optional[Dict[str, Any]],
    *,
    limit: int,
) -> List[str]:
    out: List[str] = []
    seen: set[str] = set()
    raw_terms = list(topics or []) + list((cfg or {}).get("topics") or [])
    for raw in raw_terms:
        phrase = _normalized_learning_phrase(raw, max_chars=80).lower()
        if not phrase:
            continue
        for needle, title in CHAINED_LEARNING_WIKI_TOPIC_MAP.items():
            if needle in phrase and title not in seen:
                seen.add(title)
                out.append(title)
    if not out:
        out = ["Artificial intelligence", "Large language model"]
    return out[:limit]


def _chained_social_item_signal_score(item: Dict[str, Any], topics: Optional[List[str]]) -> int:
    combined = " ".join(
        str(item.get(key) or "")
        for key in ("title", "text")
    )
    lower = combined.lower()
    demand_score = _text_signal_score(lower, SOCIAL_DEMAND_PATTERNS)
    low_signal_penalty = _text_signal_score(lower, SOCIAL_LOW_SIGNAL_PATTERNS)
    chatter_penalty = _text_signal_score(lower, SOCIAL_GENERIC_CHATTER_PATTERNS)
    topic_hits = min(3, sum(1 for topic in (topics or []) if str(topic).strip() and str(topic).lower() in lower))
    operational_score = sum(bonus for pattern, bonus in OPERATIONAL_BOOST_PATTERNS if re.search(pattern, lower, re.I))
    engagement_score = 0
    score = 0
    score += demand_score
    score += topic_hits
    score += operational_score

    if item.get("source") == "twitter":
        metrics = item.get("public_metrics") if isinstance(item.get("public_metrics"), dict) else {}
        engagement = int(metrics.get("like_count", 0) or 0) + int(metrics.get("reply_count", 0) or 0) + int(metrics.get("retweet_count", 0) or 0)
        if engagement >= 5:
            engagement_score = 2
        elif engagement >= 2:
            engagement_score = 1
    elif item.get("source") == "reddit":
        if int(item.get("num_comments", 0) or 0) >= 3:
            engagement_score += 1
        if int(item.get("score", 0) or 0) >= 4:
            engagement_score += 1
    score += engagement_score

    score -= low_signal_penalty
    score -= chatter_penalty
    if len(lower.strip()) < 60:
        score -= 1
    item["_signal_components"] = {
        "demand": demand_score,
        "topics": topic_hits,
        "operational": operational_score,
        "engagement": engagement_score,
        "low_signal_penalty": low_signal_penalty,
        "chatter_penalty": chatter_penalty,
    }
    return score


def _should_collect_chained_social_item(item: Dict[str, Any], topics: Optional[List[str]]) -> bool:
    source = str(item.get("source") or "").lower()
    if source not in {"twitter", "reddit"}:
        return True
    combined = " ".join(
        str(item.get(key) or "")
        for key in ("title", "text")
    )
    score = _chained_social_item_signal_score(item, topics)
    item["signal_score"] = score
    components = item.get("_signal_components") if isinstance(item.get("_signal_components"), dict) else {}
    demand_like = int(components.get("demand", 0) or 0) + int(components.get("operational", 0) or 0) + int(components.get("engagement", 0) or 0)
    low_signal_penalty = int(components.get("low_signal_penalty", 0) or 0)
    operational_component = int(components.get("operational", 0) or 0)
    engagement_component = int(components.get("engagement", 0) or 0)
    category, _ = _classify_content_category(combined)
    if category == MEMORY_CATEGORY_CONVERSATIONAL and low_signal_penalty >= 2 and operational_component == 0 and engagement_component == 0:
        return False
    if low_signal_penalty >= 2 and demand_like < 3:
        return False
    if demand_like == 0:
        return False
    if category == MEMORY_CATEGORY_CONVERSATIONAL and demand_like < 3:
        return False
    return score >= 2


def sanitize_chained_learning_plan(
    plan: Dict[str, Any],
    *,
    topics: Optional[List[str]],
    cfg: Optional[Dict[str, Any]],
    seed_twitter_queries: Optional[List[str]],
    default_reddit_subs: Optional[List[str]],
    per_source_cap: int,
) -> Dict[str, Any]:
    plan = dict(plan or {})
    plan.setdefault("google_queries", [])
    query_terms = _build_learning_query_terms(topics, cfg, seed_twitter_queries)
    reddit_allow = _allowed_chained_reddit_subs(cfg, default_reddit_subs)
    max_twitter = max(1, min(per_source_cap, 2))
    max_reddit = max(1, min(per_source_cap, 3))
    max_wiki = max(1, min(per_source_cap, 2))
    max_google = max(1, min(per_source_cap, 2))

    notes: List[str] = []
    wl_raw = (cfg or {}).get("mistral_chained_plan_self_ref_whitelist") or []
    self_ref_whitelist: set[str] = set()
    for x in wl_raw:
        key = _normalized_learning_phrase(str(x), max_chars=220).strip().lower()
        if key:
            self_ref_whitelist.add(key)

    twitter_queries: List[Tuple[int, int, str]] = []
    seen_twitter: set[str] = set()
    for idx, raw in enumerate(plan.get("twitter_queries") or []):
        text = _normalized_learning_phrase(raw, max_chars=90)
        if len(text) < 3:
            continue
        key = text.lower()
        if key in seen_twitter:
            continue
        seen_twitter.add(key)
        if _chained_plan_target_self_referential(text, whitelist=self_ref_whitelist):
            notes.append(f"drop_twitter_self_ref:{text[:26]}")
            continue
        score = _score_learning_query(text, query_terms)
        if score < 2:
            notes.append(f"drop_twitter:{text[:30]}")
            continue
        twitter_queries.append((score, -idx, text))
    twitter_queries.sort(reverse=True)
    twitter_clean = [text for _, _, text in twitter_queries[:max_twitter]]
    if not twitter_clean:
        twitter_clean = _best_seed_learning_queries(
            seed_twitter_queries,
            cfg,
            query_terms,
            limit=max_twitter,
        )
        if twitter_clean:
            notes.append("twitter_seed_fallback")

    reddit_new: List[str] = []
    seen_new: set[str] = set()
    for raw in plan.get("reddit_subreddits_new") or []:
        sub = re.sub(r"[^A-Za-z0-9_]", "", str(raw or "").strip())[:50]
        if not sub:
            continue
        canon = reddit_allow.get(sub.lower())
        if not canon:
            notes.append(f"drop_subreddit:{sub[:24]}")
            continue
        if canon.lower() in seen_new:
            continue
        seen_new.add(canon.lower())
        reddit_new.append(canon)
    reddit_new = reddit_new[:max_reddit]

    reddit_searches: List[Dict[str, str]] = []
    seen_search: set[str] = set()
    for spec in plan.get("reddit_searches") or []:
        if not isinstance(spec, dict):
            continue
        sub = re.sub(r"[^A-Za-z0-9_]", "", str(spec.get("subreddit", "")).strip())[:50]
        query = _normalized_learning_phrase(spec.get("q", ""), max_chars=120)
        canon = reddit_allow.get(sub.lower())
        if not canon or len(query) < 3:
            continue
        if _chained_plan_target_self_referential(query, whitelist=self_ref_whitelist):
            notes.append(f"drop_reddit_search_self_ref:{query[:26]}")
            continue
        if _score_learning_query(query, query_terms) < 2:
            notes.append(f"drop_reddit_search:{query[:30]}")
            continue
        key = f"{canon.lower()}::{query.lower()}"
        if key in seen_search:
            continue
        seen_search.add(key)
        reddit_searches.append({"subreddit": canon, "q": query})
    reddit_searches = reddit_searches[:max_reddit]
    if not reddit_new and not reddit_searches:
        reddit_new = _best_seed_reddit_subs(cfg, reddit_allow, limit=max_reddit)
        if reddit_new:
            notes.append("reddit_seed_fallback")

    wiki_titles: List[str] = []
    seen_wiki: set[str] = set()
    for raw in plan.get("wikipedia_titles") or []:
        title = _normalized_learning_phrase(raw, max_chars=120)
        lowered = title.lower()
        if len(title) < 3:
            continue
        if any(term in lowered for term in CHAINED_LEARNING_INTERNAL_TERMS):
            notes.append(f"drop_wiki:{title[:30]}")
            continue
        if _chained_plan_target_self_referential(title, whitelist=self_ref_whitelist):
            notes.append(f"drop_wiki_self_ref:{title[:30]}")
            continue
        if "self-aware" in lowered or "(" in title or ")" in title:
            notes.append(f"drop_wiki:{title[:30]}")
            continue
        if title.lower() in seen_wiki:
            continue
        seen_wiki.add(title.lower())
        wiki_titles.append(title)
    if not wiki_titles:
        wiki_titles = _fallback_wikipedia_titles(topics, cfg, limit=max_wiki)
        if wiki_titles:
            notes.append("wiki_topic_fallback")
    wiki_titles = wiki_titles[:max_wiki]

    google_queries: List[str] = []
    seen_google: set[str] = set()
    for raw in plan.get("google_queries") or []:
        gq = _normalized_learning_phrase(raw, max_chars=200)
        if len(gq) < 4:
            continue
        kl = gq.lower()
        if kl in seen_google:
            continue
        seen_google.add(kl)
        if _chained_plan_target_self_referential(gq, whitelist=self_ref_whitelist):
            notes.append(f"drop_google_self_ref:{gq[:26]}")
            continue
        if _score_learning_query(gq, query_terms) < 2:
            notes.append(f"drop_google:{gq[:30]}")
            continue
        google_queries.append(gq)
    google_queries = google_queries[:max_google]

    reasoning = _normalized_learning_phrase(plan.get("reasoning", ""), max_chars=320)
    if notes:
        notes_text = ", ".join(notes[:6])
        reasoning = (reasoning + " | sanitized: " + notes_text).strip(" |")[:500]

    return {
        "twitter_queries": twitter_clean,
        "reddit_subreddits_new": reddit_new,
        "reddit_searches": reddit_searches,
        "wikipedia_titles": wiki_titles,
        "google_queries": google_queries,
        "reasoning": reasoning,
    }


def _compose_chained_learning_context(
    base_context: str,
    round_summaries: Optional[List[str]],
    *,
    base_chars: int = CHAINED_CONTEXT_BASE_MAX_CHARS,
    max_chars: int = CHAINED_CONTEXT_TOTAL_MAX_CHARS,
) -> str:
    base = str(base_context or "").strip()
    summaries = [str(s).strip() for s in (round_summaries or []) if str(s).strip()][-CHAINED_CONTEXT_MAX_ROUND_SUMMARIES:]
    parts: List[str] = []
    if base:
        parts.append(base[:base_chars])
    if summaries:
        summary_block = "\n\n".join(summaries)
        if parts:
            min_keep = 2200
            avail = max_chars - len(parts[0]) - 2
            if avail < 1400:
                keep = max(min_keep, max_chars - min(len(summary_block), 3200) - 2)
                parts[0] = parts[0][:keep]
        joined_len = len("\n\n".join(parts)) if parts else 0
        avail = max_chars - joined_len - (2 if parts else 0)
        if avail > 0:
            if len(summary_block) > avail:
                summary_block = "...\n" + summary_block[-max(0, avail - 4):]
            parts.append(summary_block)
    out = "\n\n".join(p for p in parts if p).strip()
    return out[:max_chars]


def _summarize_chained_learning_round(round_index: int, reasoning: str, items: List[Dict[str, Any]]) -> str:
    title_blob = "; ".join(
        f'{item.get("source")}:{str(item.get("title") or "")[:48]}'
        for item in items[:18]
    )
    lines = [f"--- After round {round_index + 1} ---"]
    if reasoning:
        lines.append("Planner: " + reasoning[:220])
    lines.append("Fetched titles: " + (title_blob if title_blob else "none"))
    return "\n".join(lines)


def _load_processed_chatlog_state(processed_path: Optional[Path]) -> Dict[str, str]:
    if not processed_path or not processed_path.exists():
        return {}
    try:
        with open(processed_path, "r", encoding="utf-8") as f:
            raw = json.load(f)
    except Exception:
        return {}
    if isinstance(raw, dict):
        state: Dict[str, str] = {}
        for key, value in raw.items():
            name = str(key or "").strip()
            if not name:
                continue
            state[name] = str(value or "").strip()
        return state
    if isinstance(raw, list):
        return {str(name): "" for name in raw if str(name).strip()}
    return {}


def _save_processed_chatlog_state(processed_path: Optional[Path], state: Dict[str, str]) -> None:
    if not processed_path:
        return
    try:
        processed_path.parent.mkdir(parents=True, exist_ok=True)
        trimmed_items = list(state.items())[-2000:]
        with open(processed_path, "w", encoding="utf-8") as f:
            json.dump(dict(trimmed_items), f)
    except Exception as e:
        logger.debug(f"Save processed list: {e}")


def _load_chained_social_seen_state(state_path: Optional[Path]) -> Dict[str, str]:
    if not state_path or not state_path.exists():
        return {}
    try:
        with open(state_path, "r", encoding="utf-8") as f:
            raw = json.load(f)
    except Exception:
        return {}
    records = raw.get("records", raw) if isinstance(raw, dict) else {}
    if not isinstance(records, dict):
        return {}
    state: Dict[str, str] = {}
    for key, value in records.items():
        name = str(key or "").strip()
        if not name:
            continue
        if isinstance(value, dict):
            ts = str(value.get("last_seen") or value.get("seen_at") or "").strip()
        else:
            ts = str(value or "").strip()
        if ts:
            state[name] = ts
    return state


def _prune_chained_social_seen_state(state: Dict[str, str], *, cooldown_hours: float) -> Dict[str, str]:
    if not state:
        return {}
    cutoff = _utc_now() - timedelta(hours=max(1.0, cooldown_hours) * 2)
    kept: List[Tuple[str, str]] = []
    for key, value in state.items():
        dt = _parse_utc(value)
        if dt is None:
            continue
        if dt >= cutoff:
            kept.append((key, value))
    if len(kept) > 4000:
        kept = kept[-4000:]
    return dict(kept)


def _save_chained_social_seen_state(state_path: Optional[Path], state: Dict[str, str]) -> None:
    if not state_path:
        return
    try:
        state_path.parent.mkdir(parents=True, exist_ok=True)
        trimmed_items = list(state.items())[-4000:]
        with open(state_path, "w", encoding="utf-8") as f:
            json.dump({"version": 1, "records": dict(trimmed_items)}, f)
    except Exception as e:
        logger.debug("Save chained social seen state: %s", e)


def _load_chained_moltbook_state(state_path: Optional[Path]) -> Dict[str, str]:
    if not state_path or not state_path.exists():
        return {}
    try:
        with open(state_path, "r", encoding="utf-8") as f:
            raw = json.load(f)
    except Exception:
        return {}
    if not isinstance(raw, dict):
        return {}
    return {
        "last_collected_at": str(raw.get("last_collected_at") or "").strip(),
        "last_title": str(raw.get("last_title") or "").strip(),
    }


def _save_chained_moltbook_state(state_path: Optional[Path], *, last_collected_at: str, last_title: str) -> None:
    if not state_path:
        return
    try:
        state_path.parent.mkdir(parents=True, exist_ok=True)
        with open(state_path, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "version": 1,
                    "last_collected_at": last_collected_at,
                    "last_title": (last_title or "")[:160],
                },
                f,
            )
    except Exception as e:
        logger.debug("Save chained Moltbook state: %s", e)


def _chained_moltbook_allowed(state: Dict[str, str], *, cooldown_hours: float) -> bool:
    if cooldown_hours <= 0:
        return True
    dt = _parse_utc(str(state.get("last_collected_at") or ""))
    if dt is None:
        return True
    return (_utc_now() - dt) >= timedelta(hours=max(0.0, cooldown_hours))


def _chained_social_origin_key(item: Dict[str, Any]) -> str:
    source = str(item.get("source") or "").lower()
    if source == "twitter":
        query_norm = _normalize_title(str(item.get("query") or ""), max_len=120)
        return f"twitter:q:{query_norm or 'recent'}"
    if source == "reddit":
        subreddit = _canonicalize_reddit_subreddit(str(item.get("subreddit") or "")) or "unknown"
        mode = str(item.get("reddit_mode") or "").lower()
        if mode == "search":
            query_norm = _normalize_title(str(item.get("reddit_query") or ""), max_len=120)
            return f"reddit:search:{subreddit}:{query_norm or 'search'}"
        return f"reddit:new:{subreddit}"
    return source or "unknown"


def _chained_social_recent_keys(item: Dict[str, Any]) -> List[str]:
    source = str(item.get("source") or "").lower()
    if source not in {"twitter", "reddit"}:
        return []
    keys: List[str] = []
    origin = _chained_social_origin_key(item)
    title_norm = _normalize_title(item.get("title") or item.get("text") or "", max_len=140)
    snippet_norm = _snippet_norm(item.get("text") or item.get("title") or "")
    url_norm = re.sub(r"\s+", "", str(item.get("url") or "").strip().lower())[:240]
    if title_norm:
        keys.append(f"{source}|title:{title_norm}")
        keys.append(f"{origin}|title:{title_norm}")
    if url_norm:
        keys.append(f"{source}|url:{url_norm}")
    elif title_norm and snippet_norm:
        keys.append(f"{source}|fp:{_fingerprint(title_norm + '|' + snippet_norm, max_len=280)}")
    seen: set[str] = set()
    out: List[str] = []
    for key in keys:
        if key and key not in seen:
            seen.add(key)
            out.append(key)
    return out


def _chained_social_recent_repeat_key(
    item: Dict[str, Any],
    seen_state: Dict[str, str],
    *,
    cooldown_hours: float,
) -> str:
    if cooldown_hours <= 0 or not seen_state:
        return ""
    cutoff = _utc_now() - timedelta(hours=max(0.0, cooldown_hours))
    for key in _chained_social_recent_keys(item):
        dt = _parse_utc(seen_state.get(key) or "")
        if dt is not None and dt >= cutoff:
            return key
    return ""


def _mark_chained_social_item_seen(item: Dict[str, Any], seen_state: Dict[str, str], *, seen_at: Optional[str] = None) -> None:
    stamp = (seen_at or "").strip() or (_utc_now().strftime("%Y-%m-%dT%H:%M:%S") + "Z")
    for key in _chained_social_recent_keys(item):
        seen_state[key] = stamp


def _chatlog_revisit_allowed(
    last_selected_at: str,
    *,
    cooldown_hours: float,
    same_day_min_hours: float = CHATLOG_SAME_DAY_REVISIT_MIN_HOURS,
) -> bool:
    if not last_selected_at:
        return True
    dt = _parse_utc(last_selected_at)
    if dt is None:
        return True
    now = _utc_now()
    delta = now - dt
    base_ok = delta >= timedelta(hours=max(0.0, cooldown_hours))
    if not base_ok:
        return False
    # Same calendar day (UTC): clamp harder so repeated goal-matched files do not churn before archive.
    if dt.date() == now.date():
        return delta >= timedelta(hours=max(float(cooldown_hours), float(same_day_min_hours)))
    return True


def _chatlog_actionability_stats(text: str, matched_terms: Optional[List[str]] = None) -> Dict[str, Any]:
    lower = (text or "").lower()
    actionable_score = _text_signal_score(lower, CHATLOG_ACTIONABLE_PATTERNS)
    generic_penalty = _text_signal_score(lower, CHATLOG_GENERIC_PENALTY_PATTERNS)
    matched_actionable_terms = 0
    for term in matched_terms or []:
        needle = str(term or "").strip().lower()
        if not needle:
            continue
        if any(token in needle for token in ("goal", "next step", "plan", "priority", "service", "complaint", "compute", "api", "automation", "operator", "income", "revenue")):
            matched_actionable_terms += 1
    operational_bonus = sum(bonus for pattern, bonus in OPERATIONAL_BOOST_PATTERNS if re.search(pattern, lower, re.I))
    category, _ = _classify_content_category(text)
    category_bonus = {
        MEMORY_CATEGORY_OPERATIONAL: 4,
        MEMORY_CATEGORY_STRATEGIC: 3,
        MEMORY_CATEGORY_CONVERSATIONAL: -2,
        MEMORY_CATEGORY_CREATIVE: -4,
        MEMORY_CATEGORY_SPECULATIVE: -4,
    }.get(category, 0)
    if actionable_score >= 8:
        generic_penalty = max(0, generic_penalty - 2)
    if category == MEMORY_CATEGORY_CONVERSATIONAL and actionable_score <= 2:
        generic_penalty += 2
    priority_score = actionable_score + operational_bonus + category_bonus + matched_actionable_terms - generic_penalty
    return {
        "actionable_score": actionable_score,
        "matched_actionable_terms": matched_actionable_terms,
        "operational_bonus": operational_bonus,
        "generic_penalty": generic_penalty,
        "category": category,
        "priority_score": priority_score,
    }


def _chatlog_match_stats(text: str, search_terms: Optional[List[str]]) -> Tuple[int, List[str], int, Dict[str, Any]]:
    if not search_terms:
        return 0, [], 10**9, _chatlog_actionability_stats(text, [])
    lower = text.lower()
    score = 0
    matched_terms: List[str] = []
    first_pos = 10**9
    for raw_term in search_terms:
        term = str(raw_term or "").strip()
        if len(term) < 3:
            continue
        needle = term.lower()
        hits = lower.count(needle)
        if hits <= 0:
            continue
        matched_terms.append(term)
        if needle in CHATLOG_WEAK_SEARCH_TERMS:
            term_weight = 4
        elif any(re.search(pattern, needle) for pattern, _ in CHATLOG_ACTIONABLE_PATTERNS):
            term_weight = 16
        else:
            term_weight = 12
        score += term_weight + min(hits, 6)
        pos = lower.find(needle)
        if pos >= 0:
            first_pos = min(first_pos, pos)
    code_boost = _text_signal_score(lower, CHATLOG_CODE_SIGNAL_PATTERNS)
    if code_boost:
        score += min(40, int(code_boost * 1.15))
    matched_terms = matched_terms[:8]
    return score, matched_terms, first_pos, _chatlog_actionability_stats(text, matched_terms)


def _chatlog_sort_key(entry: Dict[str, Any]) -> Tuple[int, int, int, int, float]:
    llm_priority = int(entry.get("llm_priority", 0) or 0)
    llm_actionable = 1 if entry.get("llm_actionable") else 0
    return (
        -(int(entry.get("priority_score", 0) or 0)),
        -llm_priority,
        -llm_actionable,
        int(entry.get("first_pos", 10**9) or 10**9),
        -float(entry.get("mtime", 0.0) or 0.0),
    )


def _extract_json_object_blob(text: str) -> str:
    raw = (text or "").strip()
    if not raw:
        return ""
    if raw.startswith("{") and raw.endswith("}"):
        return raw
    match = re.search(r"\{.*\}", raw, re.S)
    return match.group(0) if match else ""


def _rerank_chatlog_candidates_with_local_mistral(
    entries: List[Dict[str, Any]],
    search_terms: Optional[List[str]],
    llm_reranker: Optional[Any],
    *,
    top_n: int,
) -> None:
    if top_n <= 0 or not entries or not search_terms or llm_reranker is None or not hasattr(llm_reranker, "complete_chat"):
        return
    ranked = sorted(entries, key=_chatlog_sort_key)
    candidates = ranked[: max(1, min(len(ranked), int(top_n)))]
    payload_candidates = []
    for entry in candidates:
        payload_candidates.append(
            {
                "file": str(entry.get("path").name if entry.get("path") else entry.get("file") or ""),
                "matched_terms": list(entry.get("matched_terms") or []),
                "deterministic_priority": int(entry.get("priority_score", 0) or 0),
                "category": str(entry.get("category") or ""),
                "preview": str(entry.get("focus_excerpt") or "")[:900],
            }
        )
    if not payload_candidates:
        return
    prompt = (
        "Return JSON only with shape {\"rankings\": [{\"file\": str, \"actionable\": bool, "
        "\"priority\": 0-5, \"category\": str, \"reason\": str}]}. "
        "Favor operator-useful goals, next steps, services, complaints, compute/API plans, fixes, and shipping work. "
        "Penalize generic Elysia identity/consciousness/philosophy mentions unless they also contain concrete actions.\n\n"
        f"search_terms={json.dumps(list(search_terms)[:12], ensure_ascii=False)}\n"
        f"candidates={json.dumps(payload_candidates, ensure_ascii=False)}"
    )
    try:
        reply = llm_reranker.complete_chat(
            messages=[{"role": "user", "content": prompt}],
            max_tokens=700,
            temperature=0.1,
            module_name="planner",
            task_text="Rerank chatlog candidates for actionable operator-relevant goal recovery. Return JSON only.",
            task_type="chatlog_rerank",
        )
        from .module_prompt_registry import validate_module_llm_output

        vd = validate_module_llm_output("memory", "chatlog_reranking", None, reply or "")
        if not vd.get("valid"):
            logger.debug(
                "Chatlog local rerank skipped: structured validation failed errors=%s",
                vd.get("errors"),
            )
            return
        reply = vd.get("normalized_text") or reply
        blob = _extract_json_object_blob(reply)
        if not blob:
            return
        parsed = json.loads(blob)
    except Exception as e:
        logger.debug("Chatlog local rerank skipped: %s", e)
        return
    rankings = parsed.get("rankings") if isinstance(parsed, dict) else None
    if not isinstance(rankings, list):
        return
    by_file = {
        str(entry.get("path").name if entry.get("path") else entry.get("file") or ""): entry
        for entry in candidates
    }
    for item in rankings:
        if not isinstance(item, dict):
            continue
        name = str(item.get("file") or "").strip()
        entry = by_file.get(name)
        if entry is None:
            continue
        actionable = bool(item.get("actionable"))
        try:
            priority = int(item.get("priority", 0) or 0)
        except (TypeError, ValueError):
            priority = 0
        priority = max(0, min(5, priority))
        category = str(item.get("category") or "").strip().lower()[:40]
        reason = str(item.get("reason") or "").strip()[:180]
        bonus = priority + (2 if actionable else -3)
        if category in {"operational", "strategic"}:
            bonus += 1
        elif category in {"generic", "conversational", "creative", "speculative"}:
            bonus -= 1
        entry["llm_actionable"] = actionable
        entry["llm_priority"] = priority
        entry["llm_category"] = category
        entry["llm_reason"] = reason
        entry["priority_score"] = int(entry.get("priority_score", 0) or 0) + max(-4, min(8, bonus))


def _wikipedia_temporarily_blocked() -> bool:
    return _WIKIPEDIA_BLOCK_UNTIL_TS > time.time()


def _set_wikipedia_block_cooldown(seconds: int = WIKIPEDIA_BLOCK_COOLDOWN_SEC) -> None:
    global _WIKIPEDIA_BLOCK_UNTIL_TS
    _WIKIPEDIA_BLOCK_UNTIL_TS = max(_WIKIPEDIA_BLOCK_UNTIL_TS, time.time() + max(60, seconds))


def _is_wikipedia_robot_block(status_code: int, response_text: str) -> bool:
    if status_code != 403:
        return False
    lower = (response_text or "").lower()
    return "robot policy" in lower or "wikimedia.org if you need higher volumes" in lower


def _reddit_cooldown_key(subreddit: str, query: Optional[str] = None) -> str:
    sub = _canonicalize_reddit_subreddit(subreddit)
    if query:
        return f"search:{sub}:{str(query).strip().lower()[:120]}"
    return f"sub:{sub}"


def _reddit_temporarily_blocked(subreddit: str, query: Optional[str] = None) -> bool:
    key = _reddit_cooldown_key(subreddit, query=query)
    until = float(_REDDIT_BLOCK_UNTIL_TS_BY_KEY.get(key, 0.0) or 0.0)
    return until > time.time()


def _set_reddit_block_cooldown(
    subreddit: str,
    *,
    query: Optional[str] = None,
    seconds: int = REDDIT_BLOCK_COOLDOWN_SEC,
) -> None:
    key = _reddit_cooldown_key(subreddit, query=query)
    _REDDIT_BLOCK_UNTIL_TS_BY_KEY[key] = max(
        float(_REDDIT_BLOCK_UNTIL_TS_BY_KEY.get(key, 0.0) or 0.0),
        time.time() + max(60, seconds),
    )


def _is_reddit_blocked_status(status_code: int, response_text: str) -> bool:
    if status_code != 403:
        return False
    low = (response_text or "").lower()
    return "blocked" in low or "forbidden" in low or "whoa there" in low


def _extract_chatlog_focus_text(
    text: str,
    matched_terms: Optional[List[str]],
    *,
    max_chars: int,
) -> str:
    if not matched_terms:
        return text[:max_chars]
    lower = text.lower()
    windows: List[Tuple[int, int]] = []
    for term in matched_terms[:4]:
        needle = str(term or "").strip().lower()
        if not needle:
            continue
        pos = lower.find(needle)
        if pos < 0:
            continue
        start = max(0, pos - 320)
        end = min(len(text), pos + len(needle) + 520)
        if windows and start <= windows[-1][1] + 80:
            prev_start, prev_end = windows[-1]
            windows[-1] = (prev_start, max(prev_end, end))
        else:
            windows.append((start, end))
    if not windows:
        return text[:max_chars]
    chunks: List[str] = []
    for start, end in windows[:4]:
        chunk = text[start:end].strip()
        if not chunk:
            continue
        if start > 0:
            chunk = "... " + chunk
        if end < len(text):
            chunk = chunk + " ..."
        chunks.append(chunk)
    focused = "\n\n".join(chunks)
    return focused[:max_chars] if focused else text[:max_chars]


def _rank_chatlog_files(
    chatlogs_path: Path,
    *,
    max_files: int,
    processed_state: Optional[Dict[str, str]] = None,
    search_terms: Optional[List[str]] = None,
    revisit_cooldown_hours: float = CHATLOG_REVISIT_COOLDOWN_HOURS,
    max_backfill_files: Optional[int] = None,
    max_revisit_files: Optional[int] = None,
    llm_reranker: Optional[Any] = None,
    llm_rerank_top_n: int = 0,
) -> List[Dict[str, Any]]:
    def _chatlog_mtime(p: Path) -> float:
        try:
            return float(p.stat().st_mtime)
        except OSError:
            return 0.0

    chat_files = sorted(
        {p.resolve() for p in chatlogs_path.glob("*.txt")}
        | {p.resolve() for p in chatlogs_path.glob("*.md")},
        key=_chatlog_mtime,
        reverse=True,
    )
    files = chat_files
    processed_state = processed_state or {}
    processed = set(processed_state.keys())
    backfill_limit = max_files if max_backfill_files is None else max(0, min(max_files, int(max_backfill_files)))
    revisit_limit = max_files if max_revisit_files is None else max(0, min(max_files, int(max_revisit_files)))
    if not search_terms:
        return [
            {
                "path": fpath,
                "matched_terms": [],
                "search_strategy": "recent",
                "score": 0,
                "mtime": fpath.stat().st_mtime,
            }
            for fpath in files
            if str(fpath.name) not in processed
        ][:backfill_limit]

    matched: List[Dict[str, Any]] = []
    matched_revisit: List[Dict[str, Any]] = []
    backfill: List[Dict[str, Any]] = []
    for fpath in files:
        is_processed = str(fpath.name) in processed
        try:
            text = fpath.read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            logger.debug("Chatlog rank failed %s: %s", fpath.name, e)
            continue
        score, matched_terms, first_pos, action_stats = _chatlog_match_stats(text, search_terms)
        focus_excerpt = _extract_chatlog_focus_text(
            text,
            matched_terms,
            max_chars=1400,
        )
        entry = {
            "path": fpath,
            "matched_terms": matched_terms,
            "search_strategy": "goal_match" if matched_terms else "recent_backfill",
            "score": score,
            "first_pos": first_pos,
            "mtime": fpath.stat().st_mtime,
            "focus_excerpt": focus_excerpt,
            **action_stats,
        }
        if matched_terms:
            if is_processed:
                if _chatlog_revisit_allowed(
                    processed_state.get(str(fpath.name), ""),
                    cooldown_hours=revisit_cooldown_hours,
                ):
                    entry["search_strategy"] = "goal_match_revisit"
                    matched_revisit.append(entry)
            else:
                matched.append(entry)
        else:
            if not is_processed:
                backfill.append(entry)

    matched.sort(key=_chatlog_sort_key)
    matched_revisit.sort(key=_chatlog_sort_key)
    _rerank_chatlog_candidates_with_local_mistral(
        matched,
        search_terms,
        llm_reranker,
        top_n=llm_rerank_top_n,
    )
    _rerank_chatlog_candidates_with_local_mistral(
        matched_revisit,
        search_terms,
        llm_reranker,
        top_n=llm_rerank_top_n,
    )
    matched.sort(key=_chatlog_sort_key)
    matched_revisit.sort(key=_chatlog_sort_key)
    selected = matched[:max_files]
    remaining = max_files - len(selected)
    if remaining > 0 and revisit_limit > 0:
        selected.extend(matched_revisit[: min(remaining, revisit_limit)])
    remaining = max_files - len(selected)
    if remaining > 0 and backfill_limit > 0:
        selected.extend(backfill[: min(remaining, backfill_limit)])
    return selected


def fetch_chatlogs(
    chatlogs_path: Path,
    max_files: int = 20,
    processed_path: Optional[Path] = None,
    search_terms: Optional[List[str]] = None,
    revisit_cooldown_hours: float = CHATLOG_REVISIT_COOLDOWN_HOURS,
    max_backfill_files: Optional[int] = None,
    max_revisit_files: Optional[int] = None,
    llm_reranker: Optional[Any] = None,
    llm_rerank_top_n: int = 0,
) -> List[Dict[str, Any]]:
    """Read ChatGPT conversation ``.txt`` / ``.md`` files from personal/chatlogs. Tracks processed to avoid duplicates."""
    items = []
    if not chatlogs_path.exists():
        return items
    processed_state = _load_processed_chatlog_state(processed_path)
    selected_at = _utc_now().strftime("%Y-%m-%dT%H:%M:%S") + "Z"
    ranked_files = _rank_chatlog_files(
        chatlogs_path,
        max_files=max_files,
        processed_state=processed_state,
        search_terms=search_terms,
        revisit_cooldown_hours=revisit_cooldown_hours,
        max_backfill_files=max_backfill_files,
        max_revisit_files=max_revisit_files,
        llm_reranker=llm_reranker,
        llm_rerank_top_n=llm_rerank_top_n,
    )
    for ranked in ranked_files:
        fpath = ranked["path"]
        try:
            text = fpath.read_text(encoding="utf-8", errors="replace")
            focused_text = _extract_chatlog_focus_text(
                text,
                ranked.get("matched_terms"),
                max_chars=15000,
            )
            if len(focused_text.strip()) < 50:
                continue
            items.append({
                "source": "chatgpt",
                "title": fpath.stem,
                "text": focused_text,
                "url": "",
                "file": str(fpath.name),
                "matched_terms": list(ranked.get("matched_terms") or []),
                "search_strategy": str(ranked.get("search_strategy") or "recent"),
            })
            processed_state[str(fpath.name)] = selected_at
        except Exception as e:
            logger.debug(f"Chatlog read failed {fpath.name}: {e}")
    if items:
        _save_processed_chatlog_state(processed_path, processed_state)
        logger.info(
            "[Auto-Learning] ChatGPT conversation ingest: %d file(s) with Elysia/Guardian/code-relevant excerpts "
            "(paths under chatlogs; see matched_terms per item)",
            len(items),
        )
    return items[:max_files]


def fetch_reddit(subreddit: str, limit: int = 5, max_retries: int = 2) -> List[Dict[str, Any]]:
    """Fetch posts from Reddit (public JSON API, no auth). Retries on transient failure."""
    items = []
    subreddit = _canonicalize_reddit_subreddit(subreddit)
    if not subreddit:
        return items
    if _reddit_temporarily_blocked(subreddit):
        logger.info("Reddit fetch skipped during cooldown: r/%s", subreddit)
        return items
    for attempt in range(max_retries + 1):
        try:
            import httpx
            url = f"https://www.reddit.com/r/{subreddit}/new.json?limit={limit}"
            with httpx.Client(timeout=15, follow_redirects=True) as client:
                r = client.get(url, headers={"User-Agent": "Elysia-Learning/1.0"})
                if _is_reddit_blocked_status(r.status_code, r.text):
                    _set_reddit_block_cooldown(subreddit)
                    logger.warning(
                        "Reddit blocked (403); cooling down r/%s for %.0f sec",
                        subreddit,
                        REDDIT_BLOCK_COOLDOWN_SEC,
                    )
                    return items
                if r.status_code != 200:
                    if attempt < max_retries:
                        time.sleep(1 + attempt)
                        continue
                    return items
                data = r.json()
            for child in data.get("data", {}).get("children", [])[:limit]:
                post = child.get("data", {})
                title = post.get("title", "")
                selftext = (post.get("selftext") or "")[:2000]
                items.append({
                    "source": "reddit",
                    "subreddit": subreddit,
                    "title": title,
                    "text": selftext or title,
                    "url": f"https://reddit.com{post.get('permalink', '')}",
                    "created_utc": post.get("created_utc"),
                    "score": int(post.get("score", 0) or 0),
                    "num_comments": int(post.get("num_comments", 0) or 0),
                    "upvote_ratio": post.get("upvote_ratio"),
                })
            return items
        except Exception as e:
            logger.warning(f"Reddit fetch failed for r/{subreddit} (attempt {attempt + 1}): {e}")
            if attempt < max_retries:
                time.sleep(1 + attempt)
            else:
                return items
    return items


def peek_chatlogs_context(
    chatlogs_path: Path,
    max_files: int = 5,
    max_chars_per_file: int = 2500,
    search_terms: Optional[List[str]] = None,
    max_backfill_files: Optional[int] = None,
    max_revisit_files: Optional[int] = None,
) -> str:
    """Read recent ChatGPT export ``.txt`` / ``.md`` files for LLM planning context (does not touch processed markers)."""
    if not chatlogs_path.exists():
        return ""
    chunks: List[str] = []
    ranked_files = _rank_chatlog_files(
        chatlogs_path,
        max_files=max_files,
        processed_state=None,
        search_terms=search_terms,
        max_backfill_files=max_backfill_files,
        max_revisit_files=max_revisit_files,
    )
    for ranked in ranked_files:
        fpath = ranked["path"]
        try:
            text = fpath.read_text(encoding="utf-8", errors="replace")
            focused_text = _extract_chatlog_focus_text(
                text,
                ranked.get("matched_terms"),
                max_chars=max_chars_per_file,
            )
            if ranked.get("matched_terms"):
                label = f"--- {fpath.name} | matches: {', '.join((ranked.get('matched_terms') or [])[:4])} ---"
            else:
                label = f"--- {fpath.name} ---"
            text = focused_text
            if len(text.strip()) >= 40:
                chunks.append(f"{label}\n{text.strip()}")
        except Exception as e:
            logger.debug("peek_chatlogs_context %s: %s", fpath.name, e)
    return "\n\n".join(chunks)[:14000]


def fetch_reddit_search(subreddit: str, query: str, limit: int = 5, max_retries: int = 2) -> List[Dict[str, Any]]:
    """Search within a subreddit (public JSON)."""
    items: List[Dict[str, Any]] = []
    subreddit = _canonicalize_reddit_subreddit(subreddit)
    q = (query or "").strip()[:300]
    if not subreddit or not q:
        return items
    if _reddit_temporarily_blocked(subreddit, query=q):
        logger.info("Reddit search skipped during cooldown: r/%s q=%s", subreddit, q[:40])
        return items
    q_enc = quote(q, safe="")
    for attempt in range(max_retries + 1):
        try:
            import httpx
            url = f"https://www.reddit.com/r/{subreddit}/search.json?q={q_enc}&restrict_sr=on&sort=relevance&limit={limit}"
            with httpx.Client(timeout=15, follow_redirects=True) as client:
                r = client.get(url, headers={"User-Agent": "Elysia-Learning/1.0"})
                if _is_reddit_blocked_status(r.status_code, r.text):
                    _set_reddit_block_cooldown(subreddit, query=q)
                    logger.warning(
                        "Reddit search blocked (403); cooling down r/%s q=%s for %.0f sec",
                        subreddit,
                        q[:40],
                        REDDIT_BLOCK_COOLDOWN_SEC,
                    )
                    return items
                if r.status_code != 200:
                    if attempt < max_retries:
                        time.sleep(1 + attempt)
                        continue
                    return items
                data = r.json()
            for child in data.get("data", {}).get("children", [])[:limit]:
                post = child.get("data", {})
                title = post.get("title", "")
                selftext = (post.get("selftext") or "")[:2000]
                items.append({
                    "source": "reddit",
                    "subreddit": subreddit,
                    "title": title,
                    "text": selftext or title,
                    "url": f"https://reddit.com{post.get('permalink', '')}",
                    "created_utc": post.get("created_utc"),
                    "reddit_mode": "search",
                    "reddit_query": q,
                    "score": int(post.get("score", 0) or 0),
                    "num_comments": int(post.get("num_comments", 0) or 0),
                    "upvote_ratio": post.get("upvote_ratio"),
                })
            return items
        except Exception as e:
            logger.warning("Reddit search failed r/%s q=%s (attempt %d): %s", subreddit, q[:40], attempt + 1, e)
            if attempt < max_retries:
                time.sleep(1 + attempt)
    return items


def _learning_google_cse_credentials(cfg: Optional[Dict[str, Any]] = None) -> Tuple[Optional[str], Optional[str]]:
    """Google Programmable Search (Custom Search JSON API): key + cx engine id."""
    cfg = cfg or {}
    key = (
        (os.environ.get("GOOGLE_CUSTOM_SEARCH_API_KEY") or "").strip()
        or str(cfg.get("google_custom_search_api_key") or "").strip()
    )
    cx = (
        (os.environ.get("GOOGLE_CUSTOM_SEARCH_ENGINE_ID") or os.environ.get("GOOGLE_CSE_ID") or "").strip()
        or str(cfg.get("google_custom_search_engine_id") or "").strip()
    )
    return (key or None, cx or None)


def fetch_google_custom_search(
    query: str,
    *,
    cfg: Optional[Dict[str, Any]] = None,
    limit: int = 5,
    max_retries: int = 1,
) -> List[Dict[str, Any]]:
    """
    Official Google Custom Search JSON API (https://developers.google.com/custom-search/v1/overview).
    Requires API key + search engine id (cx). No scraping of google.com/html.
    """
    out: List[Dict[str, Any]] = []
    q = (query or "").strip()[:240]
    if not q:
        return out
    cfg = cfg or load_learning_config()
    api_key, cx = _learning_google_cse_credentials(cfg)
    if not api_key or not cx:
        logger.debug("[Auto-Learning] Google CSE skipped (set GOOGLE_CUSTOM_SEARCH_API_KEY + GOOGLE_CUSTOM_SEARCH_ENGINE_ID or auto_learning.json)")
        return out
    lim = max(1, min(10, int(limit)))
    try:
        import httpx

        url = "https://www.googleapis.com/customsearch/v1"
        params = {"key": api_key, "cx": cx, "q": q, "num": lim}
        for attempt in range(max_retries + 1):
            try:
                with httpx.Client(timeout=20, follow_redirects=True) as client:
                    r = client.get(url, params=params)
                if r.status_code == 403:
                    logger.warning("Google CSE HTTP 403 (quota or API not enabled): %s", q[:50])
                    return out
                if r.status_code != 200:
                    if attempt < max_retries:
                        time.sleep(1.0)
                        continue
                    logger.debug("Google CSE HTTP %s for %s", r.status_code, q[:40])
                    return out
                data = r.json()
                break
            except Exception as e:
                if attempt < max_retries:
                    time.sleep(1.0)
                    continue
                logger.warning("Google CSE request failed: %s", e)
                return out
    except ImportError:
        logger.debug("Google CSE: httpx not available")
        return out

    for it in (data.get("items") or [])[:lim]:
        if not isinstance(it, dict):
            continue
        title = (it.get("title") or "").strip()[:300]
        snippet = (it.get("snippet") or "").strip()[:1200]
        link = (it.get("link") or "").strip()[:500]
        if not title and not snippet:
            continue
        text = snippet or title
        if link:
            text = f"{text}\n{link}".strip()
        out.append(
            {
                "source": "google",
                "title": title or (link[:80] if link else "Google result"),
                "text": text,
                "url": link,
                "google_query": q[:200],
            }
        )
    if out:
        logger.info("[Auto-Learning] Google CSE: %d hit(s) for query=%s", len(out), q[:70])
    return out


def search_wikipedia_titles_for_query(query: str, limit: int = 3) -> List[str]:
    """Resolve free-text query to English Wikipedia page titles via MediaWiki search API."""
    q = (query or "").strip()[:280]
    if not q or _wikipedia_temporarily_blocked():
        return []
    lim = max(1, min(8, int(limit)))
    try:
        import httpx

        api = "https://en.wikipedia.org/w/api.php"
        params = {
            "action": "query",
            "format": "json",
            "list": "search",
            "srsearch": q,
            "srlimit": lim,
            "srnamespace": "0",
        }
        ua = "ElysiaGuardian/1.0 (local learning; Python httpx)"
        with httpx.Client(timeout=12, follow_redirects=True) as client:
            r = client.get(api, params=params, headers={"User-Agent": ua})
        if _is_wikipedia_robot_block(r.status_code, r.text):
            _set_wikipedia_block_cooldown()
            return []
        if r.status_code != 200:
            return []
        hits = (r.json().get("query") or {}).get("search") or []
        titles: List[str] = []
        for h in hits:
            if isinstance(h, dict):
                t = (h.get("title") or "").strip()
                if t and t not in titles:
                    titles.append(t)
        return titles[:lim]
    except Exception as e:
        logger.debug("Wikipedia title search failed: %s", e)
        return []


def fetch_wikipedia_summary(title: str, max_retries: int = 2) -> Optional[Dict[str, Any]]:
    """Fetch English Wikipedia extract for one page title (MediaWiki Action API)."""
    raw = (title or "").strip()
    if not raw or len(raw) > 200:
        return None
    if _wikipedia_temporarily_blocked():
        logger.info("Wikipedia fetch skipped during robot-policy cooldown: %s", raw[:60])
        return None
    slug = raw.replace(" ", "_")
    path_enc = quote(slug, safe="")
    ua = "ElysiaGuardian/1.0 (local learning; Python httpx)"
    for attempt in range(max_retries + 1):
        try:
            import httpx
            api = "https://en.wikipedia.org/w/api.php"
            params = {
                "action": "query",
                "format": "json",
                "prop": "extracts",
                "exintro": "true",
                "explaintext": "true",
                "titles": raw,
            }
            with httpx.Client(timeout=12, follow_redirects=True) as client:
                r = client.get(api, params=params, headers={"User-Agent": ua})
                if _is_wikipedia_robot_block(r.status_code, r.text):
                    _set_wikipedia_block_cooldown()
                    logger.warning("Wikipedia blocked by robot policy; cooling down requests for %.0f sec", WIKIPEDIA_BLOCK_COOLDOWN_SEC)
                    return None
                if r.status_code != 200:
                    if attempt < max_retries:
                        time.sleep(1 + attempt)
                        continue
                    return None
                data = r.json()
            pages = (data.get("query") or {}).get("pages") or {}
            if not pages:
                return None
            page = next(iter(pages.values()))
            if page.get("missing") or "invalid" in page:
                return None
            extract = (page.get("extract") or "").strip()
            if not extract:
                return None
            resolved_title = page.get("title") or raw
            page_url = f"https://en.wikipedia.org/wiki/{path_enc}"
            return {
                "source": "wikipedia",
                "title": resolved_title,
                "text": extract[:12000],
                "url": page_url,
            }
        except Exception as e:
            logger.warning("Wikipedia fetch failed for %s (attempt %d): %s", raw[:60], attempt + 1, e)
            if attempt < max_retries:
                time.sleep(1 + attempt)
    return None


def _element_text(el) -> str:
    """Extract all text from an XML element (including children). Handles CDATA and nested content."""
    if el is None:
        return ""
    return "".join(el.itertext()).strip() if hasattr(el, "itertext") else (el.text or "").strip()


def _find_by_local_name(parent, local_name: str):
    """Find child element by local name, ignoring XML namespace. Handles namespaced feeds."""
    if parent is None:
        return None
    for child in parent:
        tag = getattr(child, "tag", "")
        name = tag.split("}")[-1] if "}" in str(tag) else tag
        if name == local_name:
            return child
    return None


def _iter_entries(root) -> list:
    """Find item/entry elements regardless of namespace."""
    result = []
    for elem in root.iter():
        tag = getattr(elem, "tag", "")
        name = tag.split("}")[-1] if "}" in str(tag) else tag
        if name in ("item", "entry"):
            result.append(elem)
    return result


def _strip_html(text: str, max_len: int = 2000) -> str:
    """Remove HTML tags and normalize whitespace. Fallback: regex if no BeautifulSoup."""
    if not text:
        return ""
    try:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(text[:max_len * 2], "html.parser")
        for tag in soup(["script", "style"]):
            tag.decompose()
        out = soup.get_text(separator=" ", strip=True)
    except ImportError:
        import re
        out = re.sub(r"<[^>]+>", " ", text)
        out = re.sub(r"\s+", " ", out).strip()
    return out[:max_len]


def fetch_rss(feed_url: str, limit: int = 5, max_retries: int = 2) -> List[Dict[str, Any]]:
    """Fetch items from RSS feed. Retries on transient failure.
    Extracts text from nested/HTML content so entries are not empty."""
    items = []
    for attempt in range(max_retries + 1):
        try:
            import httpx
            with httpx.Client(timeout=15) as client:
                r = client.get(feed_url, headers={"User-Agent": "Elysia-Learning/1.0"})
                if r.status_code != 200:
                    if attempt < max_retries:
                        time.sleep(1 + attempt)
                        continue
                    return items
                xml = r.text
            import xml.etree.ElementTree as ET
            root = ET.fromstring(xml)
            entries = _iter_entries(root)
            for item in entries[:limit]:
                title_el = _find_by_local_name(item, "title")
                link_el = _find_by_local_name(item, "link")
                desc_el = _find_by_local_name(item, "encoded") or _find_by_local_name(item, "description") or _find_by_local_name(item, "summary") or _find_by_local_name(item, "content")
                title = _element_text(title_el)
                link = (link_el.text or "").strip() if link_el is not None else ""
                if not link and link_el is not None:
                    link = (link_el.get("href") or "").strip()
                raw_desc = _element_text(desc_el)
                desc = _strip_html(raw_desc) if raw_desc else ""
                text = (desc or title or f"RSS item from {feed_url[:50]}")[:2000]
                items.append({
                    "source": "rss",
                    "feed": feed_url[:80],
                    "title": title or "Untitled",
                    "text": text,
                    "url": link,
                })
            return items
        except Exception as e:
            logger.warning(f"RSS fetch failed for {feed_url[:50]} (attempt {attempt + 1}): {e}")
            if attempt < max_retries:
                time.sleep(1 + attempt)
            else:
                return items
    return items


def fetch_facebook(
    page_id_or_username: str,
    access_token: str,
    limit: int = 5,
    max_retries: int = 2,
) -> List[Dict[str, Any]]:
    """Fetch public posts from a Facebook Page via Graph API.
    page_id_or_username: Page ID or username (e.g. 'Meta', 'TechCrunch').
    access_token: App access token (app_id|app_secret) or user/page token with pages_read_engagement.
    """
    items: List[Dict[str, Any]] = []
    if not access_token or not page_id_or_username.strip():
        return items
    page = page_id_or_username.strip()
    url = (
        f"https://graph.facebook.com/v18.0/{page}/published_posts"
        f"?fields=message,created_time,permalink_url&limit={min(limit, 25)}&access_token={access_token}"
    )
    for attempt in range(max_retries + 1):
        try:
            import httpx
            with httpx.Client(timeout=15) as client:
                r = client.get(url, headers={"User-Agent": "Elysia-Learning/1.0"})
                if r.status_code != 200:
                    data = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
                    err = data.get("error", {}).get("message", r.text[:200])
                    logger.warning("Facebook fetch failed for %s: %s", page, err)
                    if attempt < max_retries:
                        time.sleep(1 + attempt)
                        continue
                    return items
                data = r.json()
            for node in data.get("data", [])[:limit]:
                msg = (node.get("message") or "").strip()
                if not msg:
                    continue
                items.append({
                    "source": "facebook",
                    "page": page,
                    "title": msg[:80] + ("..." if len(msg) > 80 else ""),
                    "text": msg[:15000],
                    "url": node.get("permalink_url") or "",
                    "created_time": node.get("created_time", ""),
                })
            return items
        except Exception as e:
            logger.warning("Facebook fetch error for %s (attempt %d): %s", page, attempt + 1, e)
            if attempt < max_retries:
                time.sleep(1 + attempt)
    return items


_TWITTER_LOGGED_MAX_RESULTS = False


def fetch_twitter(
    query: str,
    bearer_token: str,
    limit: int = 10,
    max_retries: int = 2,
) -> List[Dict[str, Any]]:
    """Fetch recent public tweets from X (Twitter) via API v2 search. Requires Bearer Token (App-only)."""
    global _TWITTER_LOGGED_MAX_RESULTS
    items: List[Dict[str, Any]] = []
    if not bearer_token or not query.strip():
        return items
    q = query.strip()
    # Recent search requires max_results between 10 and 100 (API rejects e.g. 3).
    max_results = max(10, min(int(limit), 100))
    if not _TWITTER_LOGGED_MAX_RESULTS:
        _TWITTER_LOGGED_MAX_RESULTS = True
        logger.info("[Twitter] Recent search clamping max_results to %s (API v2 valid range 10–100)", max_results)
    url = (
        "https://api.twitter.com/2/tweets/search/recent"
        f"?query={quote(q)}"
        f"&max_results={max_results}"
        "&tweet.fields=created_at,public_metrics"
    )
    for attempt in range(max_retries + 1):
        try:
            import httpx
            with httpx.Client(timeout=15) as client:
                r = client.get(
                    url,
                    headers={
                        "Authorization": f"Bearer {bearer_token.strip()}",
                        "User-Agent": "Elysia-Learning/1.0",
                    },
                )
                if r.status_code != 200:
                    err_msg = r.text[:200]
                    try:
                        data = r.json()
                        err_msg = data.get("errors", [{}])[0].get("detail", err_msg) if data.get("errors") else err_msg
                    except Exception:
                        pass
                    logger.warning("Twitter fetch failed for query %s: %s", q[:50], err_msg)
                    if attempt < max_retries:
                        time.sleep(1 + attempt)
                        continue
                    return items
                data = r.json()
            for node in data.get("data", [])[:limit]:
                text = (node.get("text") or "").strip()
                if not text:
                    continue
                items.append({
                    "source": "twitter",
                    "query": q[:80],
                    "title": text[:80] + ("..." if len(text) > 80 else ""),
                    "text": text[:15000],
                    "url": f"https://twitter.com/i/status/{node.get('id', '')}",
                    "created_at": node.get("created_at", ""),
                    "public_metrics": node.get("public_metrics") or {},
                })
            return items
        except Exception as e:
            logger.warning("Twitter fetch error for %s (attempt %d): %s", q[:50], attempt + 1, e)
            if attempt < max_retries:
                time.sleep(1 + attempt)
    return items


def _playwright_available() -> bool:
    """Return True if Playwright is installed (import-only check)."""
    try:
        from playwright.sync_api import sync_playwright  # noqa: F401
        return True
    except ImportError:
        return False


def fetch_web_url_headless(url: str, max_length: int = 15000, timeout_ms: int = 15000) -> Optional[Dict[str, Any]]:
    """Fetch and extract text from a web URL using a headless browser (Playwright). Use for JS-heavy or bot-blocking sites."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        logger.debug("Playwright not installed; cannot use headless browser")
        return None
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            try:
                page = browser.new_page()
                page.set_extra_http_headers({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"})
                page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
                time.sleep(1.5)  # Allow basic JS to run
                text = page.evaluate("() => document.body ? document.body.innerText : ''")
                if not text or len(text.strip()) < 50:
                    text = page.content() or ""
                    import re
                    text = re.sub(r"<[^>]+>", " ", text)
                    text = re.sub(r"\s+", " ", text).strip()
                browser.close()
            except Exception as e:
                try:
                    browser.close()
                except Exception:
                    pass
                raise e
        text = (text or "")[:max_length]
        if len(text.strip()) < 50:
            return None
        title = url.split("/")[-1].split("?")[0] or "Web page"
        return {"source": "web", "url": url, "title": title, "text": text}
    except Exception as e:
        logger.warning("Headless fetch failed for %s: %s", url[:60], e)
        return None


def fetch_web_url(url: str, max_length: int = 15000, max_retries: int = 2, use_headless: bool = False) -> Optional[Dict[str, Any]]:
    """Fetch and extract text from a web URL. If use_headless=True and Playwright is available, use headless browser."""
    if use_headless:
        try:
            if _playwright_available():
                result = fetch_web_url_headless(url, max_length=max_length)
                if result:
                    return result
        except Exception as e:
            logger.debug("Headless fetch failed, falling back to HTTP: %s", e)
    for attempt in range(max_retries + 1):
        try:
            import httpx
            r = httpx.get(url, headers={"User-Agent": "Elysia-Learning/1.0"}, timeout=15, follow_redirects=True)
            if r.status_code != 200:
                if attempt < max_retries:
                    time.sleep(1 + attempt)
                    continue
                return None
            html = r.text
            try:
                from bs4 import BeautifulSoup
                soup = BeautifulSoup(html, "html.parser")
                for tag in soup(["script", "style"]):
                    tag.decompose()
                text = soup.get_text(separator="\n", strip=True)[:max_length]
            except ImportError:
                import re
                text = re.sub(r"<[^>]+>", " ", html)
                text = re.sub(r"\s+", " ", text).strip()[:max_length]
            if len(text.strip()) < 50:
                return None
            return {"source": "web", "url": url, "title": url.split("/")[-1] or "Web page", "text": text}
        except Exception as e:
            logger.warning(f"Web fetch failed for {url[:60]} (attempt {attempt + 1}): {e}")
            if attempt < max_retries:
                time.sleep(1 + attempt)
    return None


def fetch_moltbook_for_auto_learning(
    topics: List[str],
    *,
    goal_override: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Bounded read-only browse of moltbook.com (same stack as elysia_moltbook_browser).
    Produces one learning item per successful session for the auto-learning pipeline.
    """
    try:
        from .bounded_browser.moltbook import MOLTBOOK_DEFAULT_START_URL, browse_moltbook
    except Exception as e:
        logger.debug("[Auto-Learning] Moltbook import skipped: %s", e)
        return []

    topic_hint = ", ".join(str(t) for t in (topics or [])[:8]) if topics else "AI, technology, community"
    goal = goal_override or (
        "Read-only scan of Moltbook for visible headlines, posts, and themes. "
        f"Focus on content related to: {topic_hint}. Extract factual on-page text only."
    )

    try:
        result = browse_moltbook(goal, start_url=MOLTBOOK_DEFAULT_START_URL)
    except RuntimeError as e:
        logger.warning("[Auto-Learning] Moltbook browse unavailable (install Playwright?): %s", e)
        return []
    except Exception as e:
        logger.warning("[Auto-Learning] Moltbook browse failed: %s", e)
        return []

    lines: List[str] = []
    for s in result.steps:
        u = (s.url or "")[:220]
        t = (s.title or "").strip()
        k = (s.key_findings or "").strip()
        if t or k:
            lines.append(f"---\nURL: {u}\nTitle: {t}\n{k}")
    body = "\n".join(lines).strip()
    if len(body) < 40:
        body = " ".join((s.key_findings or "").strip() for s in result.steps).strip()
    if len(body) < 30:
        logger.info("[Auto-Learning] Moltbook session produced thin text; skipping archive item")
        return []

    title = "Moltbook browse session"
    for s in result.steps:
        ft = (s.title or "").strip()
        if ft:
            title = f"Moltbook: {ft}"[:120]
            break

    # Helps topic relevance scoring match configured learning topics.
    body = f"{body}\n\n[Learning topics: {topic_hint}]"

    logger.info(
        "[Auto-Learning] Moltbook bounded browse session pages=%d stop=%s",
        len(result.visited_urls),
        (result.stop_reason or "")[:80],
    )

    return [
        {
            "source": "moltbook",
            "url": result.start_url,
            "title": title,
            "text": body[:12000],
            "moltbook_stop_reason": result.stop_reason,
            "moltbook_pages_visited": len(result.visited_urls),
        }
    ]


def _classify_content_category(combined: str) -> Tuple[str, int]:
    """
    Classify content into operational, strategic, conversational, creative, speculative.
    Returns (category, rejection_penalty). Penalty > 0 means likely reject.
    Operational/strategic content overrides low-value patterns (e.g. "we discussed the code fix").
    """
    lower = combined.lower()
    operational_score = sum(b for p, b in OPERATIONAL_BOOST_PATTERNS if re.search(p, lower, re.I))
    # Prioritize operational: if clearly operational, admit even if it mentions chat/conversation
    if operational_score >= 2:
        return MEMORY_CATEGORY_OPERATIONAL, 0
    if operational_score >= 1:
        return MEMORY_CATEGORY_STRATEGIC, 0
    for pat, tag in REJECT_LOW_VALUE_PATTERNS:
        if re.search(pat, lower, re.I):
            if tag in ("image_prompt", "style_generation"):
                return MEMORY_CATEGORY_CREATIVE, 3
            if tag in ("chat_summary", "generic_conversation"):
                return MEMORY_CATEGORY_CONVERSATIONAL, 2
            if tag == "speculative":
                return MEMORY_CATEGORY_SPECULATIVE, 2
    return MEMORY_CATEGORY_CONVERSATIONAL, 1


def _topic_overlap(text: str, topics: List[str]) -> int:
    """Count how many topic keywords appear in text (case-insensitive)."""
    if not text or not topics:
        return 0
    lower = text.lower()
    return sum(1 for t in topics if t.lower() in lower)


def _fingerprint(text: str, max_len: int = 200) -> str:
    """Short fingerprint for deduplication."""
    normalized = re.sub(r"\s+", " ", (text or "").strip())[:max_len]
    return hashlib.sha256(normalized.encode("utf-8", errors="replace")).hexdigest()[:16]


def _normalize_title(title: str, max_len: int = 100) -> str:
    """Normalize title for cross-session dedup (lower, trim, truncate)."""
    return re.sub(r"\s+", " ", (title or "").strip())[:max_len].lower()


def _snippet_norm(text: str, max_len: int = DEDUP_SNIPPET_LEN) -> str:
    """Normalized prefix of compressed text for secondary dedup comparison."""
    return re.sub(r"\s+", " ", (text or "").strip())[:max_len].lower()


def _is_generic_title_for_dedup(title_norm: str) -> bool:
    """Return True if title should not be used for title-based cross-session dedup."""
    if not title_norm or len(title_norm) < 15:
        return True
    if title_norm in GENERIC_TITLE_FOR_DEDUP:
        return True
    if re.match(r"^\[.*\]\s*$", title_norm) or re.match(r"^\s*https?://", title_norm):
        return True
    return False


def _utc_now() -> datetime:
    """Current UTC time for dedup timestamps."""
    return datetime.now(timezone.utc)


def _parse_utc(s: str) -> Optional[datetime]:
    """Parse ISO timestamp to UTC datetime. Handles Z suffix and naive strings."""
    if not s:
        return None
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


DEDUP_INDEX_FILENAME = ".learning_dedup_index.json"
DEDUP_LOCK_FILENAME = ".learning_dedup_index.lock"
DEFAULT_DEDUP_WINDOW_DAYS = 30
MIN_TITLE_LEN_FOR_DEDUP = 15
STALE_LOCK_SECONDS = 300


def _acquire_dedup_lock(storage_path: Path) -> bool:
    """Acquire advisory lock for dedup index. Returns True if acquired."""
    lock_path = storage_path / DEDUP_LOCK_FILENAME
    storage_path.mkdir(parents=True, exist_ok=True)
    for _ in range(30):
        try:
            if lock_path.exists():
                age = time.time() - lock_path.stat().st_mtime
                if age > STALE_LOCK_SECONDS:
                    lock_path.unlink(missing_ok=True)
            fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.close(fd)
            return True
        except FileExistsError:
            time.sleep(0.2)
        except OSError:
            break
    return False


def _release_dedup_lock(storage_path: Path) -> None:
    """Release advisory lock."""
    lock_path = storage_path / DEDUP_LOCK_FILENAME
    try:
        lock_path.unlink(missing_ok=True)
    except Exception:
        pass


def load_dedup_index(
    storage_path: Path,
    dedup_window_days: int,
) -> Tuple[Dict[str, Dict[str, Any]], int]:
    """
    Load the persisted dedup index, prune records outside the window.
    Uses UTC timestamps and datetime arithmetic for pruning.
    Returns (by_fingerprint, pruned_count).
    """
    path = storage_path / DEDUP_INDEX_FILENAME
    by_fp: Dict[str, Dict[str, Any]] = {}
    pruned = 0
    if not path.exists():
        return by_fp, 0
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        logger.debug(f"[Auto-Learning] Dedup index load failed: {e}")
        return by_fp, 0
    records = data.get("records", data) if isinstance(data, dict) else (data if isinstance(data, list) else [])
    if not isinstance(records, list):
        return by_fp, 0
    cutoff = _utc_now() - timedelta(days=dedup_window_days)
    for r in records:
        if not isinstance(r, dict):
            continue
        fp = r.get("fp") or r.get("fingerprint")
        if not fp:
            continue
        last_seen = _parse_utc(r.get("last_seen") or "")
        if last_seen is not None and last_seen < cutoff:
            pruned += 1
            continue
        last_str = r.get("last_seen", "")
        first_str = r.get("first_seen", "")
        by_fp[fp] = {
            "fp": fp,
            "title_norm": (r.get("title_norm") or "")[:100],
            "snippet_norm": (r.get("snippet_norm") or "")[:DEDUP_SNIPPET_LEN],
            "first_seen": first_str,
            "last_seen": last_str,
            "source": (r.get("source") or "unknown")[:50],
            "admitted_to_memory": bool(r.get("admitted_to_memory")),
        }
    return by_fp, pruned


def save_dedup_index(
    storage_path: Path,
    by_fp: Dict[str, Dict[str, Any]],
    dedup_window_days: int,
) -> int:
    """
    Prune old records, write the dedup index atomically.
    Uses file lock when available; re-reads latest state before final write to reduce lost updates.
    Returns number of records pruned.
    """
    cutoff = _utc_now() - timedelta(days=dedup_window_days)
    to_keep: Dict[str, Dict[str, Any]] = {}
    pruned = 0
    for fp, r in by_fp.items():
        last_seen = _parse_utc(r.get("last_seen") or "")
        if last_seen is not None and last_seen < cutoff:
            pruned += 1
            continue
        to_keep[fp] = r

    path = storage_path / DEDUP_INDEX_FILENAME
    locked = _acquire_dedup_lock(storage_path)
    try:
        if locked and path.exists():
            try:
                with open(path, "r", encoding="utf-8") as f:
                    fresh = json.load(f)
                fresh_records = fresh.get("records", [])
                if isinstance(fresh_records, list):
                    for r in fresh_records:
                        if not isinstance(r, dict):
                            continue
                        fp = r.get("fp") or r.get("fingerprint")
                        if not fp:
                            continue
                        ls = _parse_utc(r.get("last_seen") or "")
                        if ls is not None and ls < cutoff:
                            pruned += 1
                            continue
                        if fp not in to_keep:
                            to_keep[fp] = r
                        else:
                            ls_ours = _parse_utc(to_keep[fp].get("last_seen") or "")
                            if ls and ls_ours and ls > ls_ours:
                                to_keep[fp]["last_seen"] = r["last_seen"]
                            to_keep[fp]["admitted_to_memory"] = to_keep[fp].get("admitted_to_memory", False) or r.get("admitted_to_memory", False)
            except Exception as e:
                logger.debug(f"[Auto-Learning] Dedup re-read before save: {e}")
        storage_path.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump({"version": 2, "records": list(to_keep.values())}, f, ensure_ascii=False, indent=None)
            tmp.replace(path)
        except Exception as e:
            logger.debug(f"[Auto-Learning] Dedup index save failed: {e}")
            if tmp.exists():
                try:
                    tmp.unlink()
                except Exception:
                    pass
        return pruned
    finally:
        if locked:
            _release_dedup_lock(storage_path)


def _build_dedup_lookup(by_fp: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    """
    Build lookup structures for cross-session duplicate detection.
    Returns dict with: fp_set, by_source_title (source -> {title_norm -> record}), by_fp.
    """
    fp_set = set(by_fp.keys())
    by_source_title: Dict[str, Dict[str, Any]] = {}
    for r in by_fp.values():
        src = (r.get("source") or "unknown")[:50]
        tn = (r.get("title_norm") or "").strip()
        if tn and len(tn) >= MIN_TITLE_LEN_FOR_DEDUP and tn not in GENERIC_TITLE_FOR_DEDUP:
            if src not in by_source_title:
                by_source_title[src] = {}
            by_source_title[src][tn] = r
    return {"fp_set": fp_set, "by_source_title": by_source_title, "by_fp": by_fp}


def _lexical_overlap_ratio(a: str, b: str) -> float:
    """Simple word overlap ratio (Jaccard-like) between two normalized strings."""
    if not a or not b:
        return 0.0
    wa = set(re.split(r"\s+", a))
    wb = set(re.split(r"\s+", b))
    if not wa:
        return 0.0
    return len(wa & wb) / len(wa)


def is_cross_session_duplicate(
    fp: str,
    title_norm: str,
    snippet_norm: str,
    source: str,
    compressed_len: int,
    dedup_lookup: Dict[str, Any],
) -> Tuple[bool, str]:
    """
    Check if item is a cross-session duplicate.
    Returns (is_duplicate, match_type) where match_type is "fingerprint", "title_source", "weak_content", "snippet_overlap", or "".
    Fingerprint match is high-confidence. Title-based only when stricter conditions hold.
    """
    fp_set = dedup_lookup.get("fp_set") or set()
    by_source_title = dedup_lookup.get("by_source_title") or {}
    by_fp = dedup_lookup.get("by_fp") or {}

    if fp and fp in fp_set:
        return True, "fingerprint"

    if _is_generic_title_for_dedup(title_norm):
        return False, ""

    weak_content = compressed_len < WEAK_CONTENT_THRESHOLD
    src = (source or "unknown").lower()

    if src in by_source_title and title_norm in by_source_title[src]:
        rec = by_source_title[src][title_norm]
        if weak_content:
            return True, "title_source_weak"
        snippet_prev = (rec.get("snippet_norm") or "").strip()
        if snippet_norm and snippet_prev and _lexical_overlap_ratio(snippet_norm, snippet_prev) >= MIN_LEXICAL_OVERLAP_RATIO:
            return True, "title_source_snippet"
        return True, "title_source"

    if weak_content and title_norm:
        for src2, titles in by_source_title.items():
            if title_norm in titles:
                return True, "weak_content"

    return False, ""


def score_learned_item(
    item: Dict[str, Any],
    topics: List[str],
    session_titles: set,
    session_fingerprints: set,
) -> Dict[str, Any]:
    """
    Score a learned item for admission to long-term memory.
    Returns structured result: {admit, reason, score, trust_tier, relevance, ...}
    """
    compressed = (item.get("compressed") or item.get("text") or "").strip()
    title = (item.get("title") or "").strip()
    source = (item.get("source") or "unknown").lower()
    trust_tier = SOURCE_TRUST_TIERS.get(source, DEFAULT_TRUST)

    result: Dict[str, Any] = {
        "admit": False,
        "reason": "",
        "trust_tier": trust_tier,
        "relevance": 0,
        "reuse_potential": 0,
        "content_ok": False,
        "topic_ok": False,
        "trust_ok": False,
        "not_duplicate": False,
        "category": "",
    }

    # A. Minimum content quality
    combined = f"{title} {compressed}"
    if len(compressed) < 30:
        result["reason"] = "too_short"
        result["category"], _ = _classify_content_category(combined)
        return result
    if title and len(compressed) < 80 and compressed.lower().replace(title.lower(), "").strip() in ("", "...", "-"):
        result["reason"] = "title_only"
        result["category"], _ = _classify_content_category(combined)
        return result
    for pat in TITLE_SPAM_PATTERNS:
        if re.match(pat, (title or "").strip(), re.I):
            result["reason"] = "generic_title"
            result["category"], _ = _classify_content_category(combined)
            return result
    result["content_ok"] = True

    # B. Topic relevance (skip check if no topics configured)
    category, rejection_penalty = _classify_content_category(combined)
    result["category"] = category
    relevance = _topic_overlap(combined, topics) if topics else 1
    result["relevance"] = relevance
    if not topics or relevance >= 1:
        result["topic_ok"] = True
    else:
        result["reason"] = "low_relevance"
        return result

    # Bb. Low-value rejection (category already set above for logging)
    result["rejection_penalty"] = rejection_penalty
    operational_boost = sum(b for p, b in OPERATIONAL_BOOST_PATTERNS if re.search(p, combined.lower(), re.I))
    result["reuse_potential"] = min(3, relevance + (2 if operational_boost >= 2 else 1 if operational_boost >= 1 else 0))
    if rejection_penalty >= 2:
        result["reason"] = f"low_value_{category}"
        return result

    # C. Source trust (stricter for low-trust sources)
    result["trust_ok"] = True
    result["trust_tier"] = trust_tier

    # D. Deduplication
    fp = _fingerprint(compressed)
    title_norm = (title or "")[:100].lower()
    if title_norm in session_titles or fp in session_fingerprints:
        result["reason"] = "duplicate"
        return result
    result["not_duplicate"] = True

    # E. Reuse potential / execution value (penalize generic, one-off, no execution value)
    if result["reuse_potential"] < 1 and rejection_penalty >= 1:
        result["reason"] = "no_execution_value"
        return result
    result["admit"] = True
    result["reason"] = "passed"
    return result


def should_ingest_learned_item(
    item: Dict[str, Any],
    topics: List[str],
    config: Dict[str, Any],
    session_titles: set,
    session_fingerprints: set,
    caps: Dict[str, int],
    dedup_lookup: Optional[Dict[str, Any]] = None,
) -> Tuple[bool, str, Dict[str, Any]]:
    """
    Determine if an item should be admitted to long-term memory.
    Returns (admit, rejection_reason, score_info).
    dedup_lookup: from _build_dedup_lookup() for cross-session duplicate check.
    """
    score_info = score_learned_item(item, topics, session_titles, session_fingerprints)

    if not score_info["admit"]:
        return False, score_info["reason"], score_info

    # Cross-session duplicate check (fingerprint = high confidence; title-based = stricter rules)
    if dedup_lookup:
        compressed = (item.get("compressed") or item.get("text") or "").strip()
        fp = _fingerprint(compressed)
        title_norm = _normalize_title(item.get("title") or "")
        snippet_norm = _snippet_norm(compressed)
        source = (item.get("source") or "unknown").lower()
        is_dup, match_type = is_cross_session_duplicate(
            fp, title_norm, snippet_norm, source, len(compressed), dedup_lookup
        )
        if is_dup:
            return False, "cross_session_duplicate", {**score_info, "dedup_match_type": match_type}

    source = (item.get("source") or "unknown").lower()
    trust = score_info["trust_tier"]

    # Config gates
    allow_reddit_social = config.get("allow_reddit_into_memory", False)
    if trust == "low" and not allow_reddit_social:
        return False, "low_trust", score_info

    min_relevance = config.get("min_relevance_score", 2)
    if score_info["relevance"] < min_relevance:
        return False, "low_relevance", score_info

    min_reuse = config.get("min_reuse_potential", 1)
    if score_info.get("reuse_potential", 0) < min_reuse:
        return False, "low_reuse_potential", score_info

    # Category gating: only operational and (optionally) strategic admitted by default
    allow_strategic = config.get("allow_strategic_into_memory", False)
    category = score_info.get("category", MEMORY_CATEGORY_CONVERSATIONAL)
    if category not in (MEMORY_CATEGORY_OPERATIONAL, MEMORY_CATEGORY_STRATEGIC):
        return False, f"category_{category}", score_info
    if category == MEMORY_CATEGORY_STRATEGIC and not allow_strategic:
        return False, "strategic_not_allowed", score_info

    # Session caps
    if caps.get("memory_admitted", 0) >= caps.get("max_memory_per_session", 20):
        return False, "session_cap", score_info
    per_source = caps.get("per_source", {})
    if per_source.get(source, 0) >= caps.get("max_per_source_memory", 5):
        return False, "source_cap", score_info

    return True, "passed", score_info


def _priority_for_admitted(trust_tier: str, relevance: int) -> float:
    """Assign priority by trust and relevance. Higher = more important."""
    base = {"high": 0.65, "medium": 0.55, "low": 0.45}.get(trust_tier, 0.45)
    if relevance >= 3:
        base += 0.1
    elif relevance >= 2:
        base += 0.05
    return min(0.9, max(0.35, base))


def compress_with_llm(
    text: str,
    llm_callback: Optional[Callable[..., tuple]],
    *,
    module_name: str,
    agent_name: Optional[str] = None,
) -> str:
    """Compress/summarize text via LLM if available."""
    if not llm_callback or len(text) <= 400:
        return text[:500] + ("..." if len(text) > 500 else "")
    try:
        from .llm.prompted_call import log_prompted_call, prepare_prompted_bundle, require_prompt_profile

        mod, ag, _ = require_prompt_profile(
            module_name, agent_name, caller="compress_with_llm", allow_legacy=False
        )

        _b = prepare_prompted_bundle(
            module_name=mod,
            agent_name=ag,
            task_text="Summarize in 2-4 sentences; preserve key facts about AI, income, or technology.",
            context={"source_excerpt": text[:3000]},
            caller="compress_with_llm",
        )
        prompt = _b["prompt_text"]
        log_prompted_call(
            module_name=mod,
            agent_name=ag,
            task_type="compress_with_llm",
            provider="callback",
            model=None,
            bundle_meta=_b["meta"],
            prompt_length=len(prompt),
            legacy_prompt_path=False,
        )
        struct_kwargs = {
            "structured_role": "sequential_processing:accumulated_context_compression",
            "prompt_extra": {
                "task_type": "compress_with_llm",
                "task": {
                    "registry_prompt_anchor": prompt[:12000],
                    "source_excerpt": text[:3000],
                    "instruction_short": (
                        "Summarize in 2-4 sentences; preserve key facts about AI, income, or technology."
                    ),
                },
            },
            "module_name": mod,
            "agent_name": ag if ag else None,
            "max_tokens": 520,
        }
        used_kwargs = False
        try:
            reply, err = llm_callback(prompt, **struct_kwargs)
            used_kwargs = True
        except TypeError:
            reply, err = llm_callback(prompt)

        if reply and not err:
            raw = reply.strip()
            if used_kwargs:
                from .module_prompt_registry import validate_module_llm_output

                vd = validate_module_llm_output(
                    "sequential_processing",
                    "accumulated_context_compression",
                    None,
                    raw,
                )
                if vd.get("valid"):
                    pdata = vd.get("data") or {}
                    cx = ""
                    if isinstance(pdata, dict):
                        cx = str(pdata.get("compressed_text") or "").strip()
                    if cx:
                        return cx[:800]
                return raw[:800]
            return raw[:800]
    except Exception as e:
        logger.debug(f"LLM compress failed: {e}")
    return text[:500] + ("..." if len(text) > 500 else "")


OPPORTUNITY_EXTRACTIONS_FILENAME = "opportunity_extractions.jsonl"


def _append_opportunity_extractions(
    storage_path: Path,
    admitted_items: List[Dict[str, Any]],
    topics: List[str],
) -> None:
    """Lightweight ranked opportunities from a good learning run (disk artifact; no UI)."""
    if not admitted_items:
        return
    storage_path.mkdir(parents=True, exist_ok=True)
    out_path = storage_path / OPPORTUNITY_EXTRACTIONS_FILENAME
    topic_blob = ", ".join(str(t) for t in (topics or [])[:8])
    ranked: List[Dict[str, Any]] = []
    for row in sorted(
        admitted_items,
        key=lambda r: float(r.get("relevance") or 0),
        reverse=True,
    )[:12]:
        rel = float(row.get("relevance") or 0)
        conf = max(0.15, min(0.92, 0.28 + 0.12 * rel))
        src = str(row.get("source") or "unknown")
        user_seg = "operator_chat" if src == "chatgpt" else "public_or_unknown"
        ranked.append(
            {
                "problem": str(row.get("title") or "")[:240],
                "affected_user": user_seg,
                "evidence_source": src,
                "evidence_excerpt": str(row.get("compressed") or "")[:360],
                "possible_service": f"Research / tooling aligned to topics: {topic_blob}"[:220],
                "confidence": round(conf, 3),
            }
        )
    record = {
        "learned_at": datetime.now().isoformat(),
        "opportunities": ranked,
    }
    try:
        with open(out_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception as e:
        logger.debug("opportunity_extractions write: %s", e)


def finalize_learned_collection(
    collected: List[Dict[str, Any]],
    storage_path: Path,
    topics: List[str],
    memory: Optional[Any] = None,
    sources_count: int = 1,
) -> Dict[str, Any]:
    """Archive learned items, run admission gates, update dedup index and memory."""
    cfg = load_learning_config()
    max_archived = int(cfg.get("max_archived_per_session", 100))
    max_memory_per_session = int(cfg.get("max_memory_per_session", 20))
    max_per_source_memory = int(cfg.get("max_per_source_memory", 5))
    dedup_window_days = int(cfg.get("dedup_window_days", DEFAULT_DEDUP_WINDOW_DAYS))

    fetched = len(collected)
    if not collected:
        logger.info("[Auto-Learning] Session complete: fetched=0 (no items collected)")
        return {
            "fetched": 0,
            "archived": 0,
            "admitted": 0,
            "rejected": 0,
            "cross_session_duplicates": 0,
            "fingerprint_duplicates": 0,
            "title_match_duplicates": 0,
            "dedup_records_pruned": 0,
            "rejection_breakdown": {},
            "sources": 0,
            "memory": 0,
            "file": "",
            "message": "No items collected",
            "max_admitted_relevance": 0.0,
            "followup_seeds": [],
            "local_ai_selfbuild_appended": 0,
        }

    to_archive = collected[:max_archived] if fetched > max_archived else collected
    archived_count = len(to_archive)

    storage_path.mkdir(parents=True, exist_ok=True)
    date_str = datetime.now().strftime("%Y-%m-%d")
    out_file = storage_path / f"learned_{date_str}.jsonl"

    dedup_by_fp, dedup_load_pruned = load_dedup_index(storage_path, dedup_window_days)
    dedup_lookup = _build_dedup_lookup(dedup_by_fp)

    session_titles: set = set()
    session_fingerprints: set = set()
    caps: Dict[str, Any] = {
        "memory_admitted": 0,
        "max_memory_per_session": max_memory_per_session,
        "max_per_source_memory": max_per_source_memory,
        "per_source": {},
    }
    rejection_breakdown: Dict[str, int] = {}
    admitted_count = 0
    memory_saved_count = 0
    cross_session_duplicates = 0
    fingerprint_duplicates = 0
    title_match_duplicates = 0
    records_to_add: List[Tuple[str, str, str, str, bool]] = []
    admitted_items: List[Dict[str, Any]] = []
    try:
        from .local_ai_selfbuild_corpus import maybe_append_local_ai_selfbuild_row as _append_local_selfbuild_row
    except ImportError:
        _append_local_selfbuild_row = None  # type: ignore[misc,assignment]
    local_selfbuild_corpus_fps: set = set()
    local_selfbuild_appended = 0

    with open(out_file, "a", encoding="utf-8") as f:
        for item in to_archive:
            item["learned_at"] = datetime.now().isoformat()
            src = (item.get("source") or "unknown").lower()
            title = (item.get("title") or "Untitled")[:80]
            compressed = (item.get("compressed") or item.get("text") or "")[:1200]
            fp = _fingerprint(compressed)
            title_norm = _normalize_title(title)
            snippet_norm = _snippet_norm(compressed)

            admit, reject_reason, score_info = should_ingest_learned_item(
                item, topics, cfg, session_titles, session_fingerprints, caps, dedup_lookup
            )

            if reject_reason == "cross_session_duplicate":
                cross_session_duplicates += 1
                match_type = score_info.get("dedup_match_type", "")
                if match_type == "fingerprint":
                    fingerprint_duplicates += 1
                elif match_type:
                    title_match_duplicates += 1

            arch_meta = {
                "learned_at": item["learned_at"],
                "source": src,
                "source_type": src,
                "source_trust_tier": score_info.get("trust_tier", "low"),
                "relevance": score_info.get("relevance", 0),
                "archived_only": not admit,
            }
            if admit:
                cat = score_info.get("category", MEMORY_CATEGORY_OPERATIONAL)
                arch_meta["ingestion_reason"] = "operational" if cat == MEMORY_CATEGORY_OPERATIONAL else "strategic"
                arch_meta["category"] = cat
                arch_meta["archived_only"] = False
                admitted_count += 1
                admitted_items.append(
                    {
                        "title": title,
                        "source": src,
                        "compressed": compressed[:800],
                        "relevance": float(score_info.get("relevance") or 0),
                        "trust_tier": score_info.get("trust_tier", "low"),
                    }
                )
                session_titles.add((title or "")[:100].lower())
                session_fingerprints.add(fp)
                caps["memory_admitted"] += 1
                caps["per_source"][src] = caps["per_source"].get(src, 0) + 1
                logger.info("[Auto-Learning] Admitted (category=%s): %.60s...", cat, (title or compressed)[:60])
                if _append_local_selfbuild_row is not None:
                    try:
                        if _append_local_selfbuild_row(
                            storage_path=storage_path,
                            item=item,
                            score_info=score_info,
                            session_topics=topics,
                            cfg=cfg,
                            recent_fingerprints=local_selfbuild_corpus_fps,
                        ):
                            local_selfbuild_appended += 1
                    except Exception as e:
                        logger.debug("[local_ai_selfbuild] %s", e)
            else:
                arch_meta["rejection_reason"] = reject_reason
                arch_meta["category"] = score_info.get("category", "")
                rejection_breakdown[reject_reason] = rejection_breakdown.get(reject_reason, 0) + 1
                logger.info(
                    "[Auto-Learning] Rejected (category=%s, reason=%s): %.60s...",
                    score_info.get("category", ""), reject_reason, (title or compressed)[:60],
                )

            item["_arch_meta"] = arch_meta
            f.write(json.dumps(item, ensure_ascii=False) + "\n")
            records_to_add.append((fp, title_norm, snippet_norm, src, admit))

            if admit and memory and hasattr(memory, "remember"):
                try:
                    priority = _priority_for_admitted(
                        score_info.get("trust_tier", "low"),
                        score_info.get("relevance", 1),
                    )
                    thought = f"[Learned/{src}] {title}: {compressed}"
                    ing_reason = arch_meta.get("ingestion_reason", "operational")
                    memory.remember(
                        thought,
                        category="learning",
                        priority=priority,
                        metadata={
                            "source": src,
                            "source_type": src,
                            "source_trust_tier": score_info.get("trust_tier", "low"),
                            "relevance_score": score_info.get("relevance", 0),
                            "ingestion_reason": ing_reason,
                            "content_category": score_info.get("category", MEMORY_CATEGORY_OPERATIONAL),
                            "learned_at": item["learned_at"],
                            "archived_only": False,
                            "previously_unseen": True,
                        },
                    )
                    memory_saved_count += 1
                except Exception as e:
                    logger.debug("Memory pipe failed: %s", e)
                    rejection_breakdown["memory_error"] = rejection_breakdown.get("memory_error", 0) + 1

    now_iso = _utc_now().strftime("%Y-%m-%dT%H:%M:%S") + "Z"
    for fp, title_norm, snippet_norm, src, admitted in records_to_add:
        if fp in dedup_by_fp:
            dedup_by_fp[fp]["last_seen"] = now_iso
            dedup_by_fp[fp]["admitted_to_memory"] = dedup_by_fp[fp].get("admitted_to_memory", False) or admitted
            if snippet_norm:
                dedup_by_fp[fp]["snippet_norm"] = snippet_norm
        else:
            dedup_by_fp[fp] = {
                "fp": fp,
                "title_norm": title_norm,
                "snippet_norm": snippet_norm,
                "first_seen": now_iso,
                "last_seen": now_iso,
                "source": src,
                "admitted_to_memory": admitted,
            }
    dedup_save_pruned = save_dedup_index(storage_path, dedup_by_fp, dedup_window_days)
    dedup_records_pruned = dedup_load_pruned + dedup_save_pruned

    rejected_count = archived_count - admitted_count
    dup_sat = learning_run_duplicate_saturated(
        {
            "rejected": rejected_count,
            "rejection_breakdown": rejection_breakdown,
            "cross_session_duplicates": cross_session_duplicates,
        }
    )
    if dup_sat and rejected_count > 0:
        logger.info(
            "[Auto-Learning] Session duplicate-saturated (low-yield): rejected=%d cross_session_duplicate=%s in breakdown",
            rejected_count,
            rejection_breakdown.get("cross_session_duplicate", 0),
        )
    top_rejections = ", ".join(
        f"{k}:{v}" for k, v in sorted(rejection_breakdown.items(), key=lambda x: -x[1])[:5]
    )
    logger.info(
        "[Auto-Learning] Session complete: fetched=%d archived=%d admitted=%d rejected=%d cross_session_duplicates=%d (fp=%d title=%d) dedup_pruned=%d top_rejections=%s",
        fetched, archived_count, admitted_count, rejected_count, cross_session_duplicates,
        fingerprint_duplicates, title_match_duplicates, dedup_records_pruned, top_rejections or "none",
    )

    if admitted_count >= 2 and not dup_sat:
        _append_opportunity_extractions(storage_path, admitted_items, topics)

    web_count = sum(1 for i in to_archive if i.get("source") == "web")
    max_admitted_relevance = 0.0
    if admitted_items:
        max_admitted_relevance = max(float(x.get("relevance") or 0) for x in admitted_items)
    followup_seeds = sorted(
        list(admitted_items),
        key=lambda x: float(x.get("relevance") or 0),
        reverse=True,
    )[:5]
    return {
        "fetched": fetched,
        "archived": archived_count,
        "admitted": admitted_count,
        "rejected": rejected_count,
        "cross_session_duplicates": cross_session_duplicates,
        "fingerprint_duplicates": fingerprint_duplicates,
        "title_match_duplicates": title_match_duplicates,
        "dedup_records_pruned": dedup_records_pruned,
        "rejection_breakdown": rejection_breakdown,
        "sources": sources_count,
        "chatlogs": sum(1 for i in to_archive if i.get("source") == "chatgpt"),
        "web_pages": web_count,
        "memory": memory_saved_count,
        "file": str(out_file),
        "saved": archived_count,
        "memory_count": memory_saved_count,
        "max_admitted_relevance": max_admitted_relevance,
        "followup_seeds": followup_seeds,
        "local_ai_selfbuild_appended": local_selfbuild_appended,
    }


def maybe_run_high_value_learning_expansion(
    *,
    session_result: Dict[str, Any],
    storage_path: Path,
    topics: List[str],
    cfg: Dict[str, Any],
    llm_callback: Optional[Callable[[str], tuple]],
    memory: Optional[Any],
    twitter_bearer_token: Optional[str],
    default_reddit_sub: str,
) -> Dict[str, Any]:
    """
    After a session admits high-signal items, fan out to additional sources: Google Programmable Search
    (when API credentials are set), Wikipedia search hits, Reddit in-sub search, and Twitter (when configured).
    Results go through the same admission pipeline as the main session.
    """
    if not bool(cfg.get("high_value_expansion_enabled", True)):
        return {"skipped": True, "reason": "disabled"}
    admitted = int(session_result.get("admitted") or 0)
    if admitted < int(cfg.get("high_value_expansion_min_admitted", 1)):
        return {"skipped": True, "reason": "below_min_admitted"}
    max_rel = float(session_result.get("max_admitted_relevance") or 0.0)
    thr = float(cfg.get("high_value_expansion_min_relevance", 3))
    bulk_thr = int(cfg.get("high_value_expansion_bulk_admitted", 4))
    if max_rel < thr and admitted < bulk_thr:
        return {"skipped": True, "reason": "below_relevance_threshold"}
    seeds = session_result.get("followup_seeds") or []
    if not isinstance(seeds, list) or not seeds:
        return {"skipped": True, "reason": "no_seeds"}

    collected: List[Dict[str, Any]] = []
    max_queries = int(cfg.get("high_value_expansion_max_queries", 3))
    max_queries = max(1, min(5, max_queries))
    per_branch = int(cfg.get("high_value_expansion_per_branch_cap", 3))
    per_branch = max(1, min(8, per_branch))
    queries_made: set[str] = set()
    sub = re.sub(r"[^A-Za-z0-9_]", "", (default_reddit_sub or "MachineLearning").strip())[:50] or "MachineLearning"

    for seed in seeds[:max_queries]:
        if not isinstance(seed, dict):
            continue
        title = str(seed.get("title") or "").strip()
        comp = str(seed.get("compressed") or "")[:360]
        blob = f"{title} {comp}".strip()
        if len(blob) < 12:
            continue
        q = re.sub(r"\s+", " ", blob)[:220]
        kl = q.lower()
        if kl in queries_made:
            continue
        queries_made.add(kl)

        for gitem in fetch_google_custom_search(q, cfg=cfg, limit=per_branch):
            gitem["compressed"] = compress_with_llm(gitem.get("text", ""), llm_callback, module_name="summarizer")
            gitem["expansion_pass"] = "high_value"
            collected.append(gitem)

        for wt in search_wikipedia_titles_for_query(q, limit=2):
            witem = fetch_wikipedia_summary(wt)
            if witem:
                witem["compressed"] = compress_with_llm(witem.get("text", ""), llm_callback, module_name="summarizer")
                witem["expansion_pass"] = "high_value"
                collected.append(witem)

        short_q = q[:180]
        for item in fetch_reddit_search(sub, short_q, limit=per_branch):
            item["compressed"] = compress_with_llm(item.get("text", ""), llm_callback, module_name="summarizer")
            item["expansion_pass"] = "high_value"
            collected.append(item)

        if twitter_bearer_token:
            tw_q = (title or q)[:200]
            if tw_q.strip():
                for item in fetch_twitter(tw_q, twitter_bearer_token, limit=min(2, per_branch)):
                    item["compressed"] = compress_with_llm(item.get("text", ""), llm_callback, module_name="summarizer")
                    item["expansion_pass"] = "high_value"
                    collected.append(item)

    if not collected:
        return {"skipped": True, "reason": "no_expansion_items"}

    logger.info(
        "[Auto-Learning] High-value expansion: %d raw item(s) from %d seed(s); compress complete",
        len(collected),
        min(len(seeds), max_queries),
    )
    fin = finalize_learned_collection(collected, storage_path, topics, memory, sources_count=5)
    fin["high_value_expansion"] = True
    return fin


def run_learning_session(
    storage_path: Path,
    topics: List[str],
    reddit_subs: List[str],
    rss_feeds: List[str],
    chatlogs_path: Optional[Path] = None,
    web_urls: Optional[List[str]] = None,
    facebook_pages: Optional[List[str]] = None,
    facebook_access_token: Optional[str] = None,
    twitter_search_queries: Optional[List[str]] = None,
    twitter_bearer_token: Optional[str] = None,
    use_headless_for_web: Optional[bool] = None,
    max_per_source: int = 5,
    max_chatlogs: int = 20,
    llm_callback: Optional[Callable[[str], tuple]] = None,
    memory: Optional[Any] = None,
    chatlog_search_terms: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Run one learning session: fetch Reddit, RSS, ChatGPT chatlogs, web URLs, Moltbook (bounded), Facebook, X (Twitter); compress; store.
    Items are archived to disk; only those passing quality gates are admitted to long-term memory.
    When use_headless_for_web is True and Playwright is available, web URLs are fetched via headless browser.
    """
    cfg = load_learning_config()
    if use_headless_for_web is None:
        use_headless_for_web = bool(cfg.get("use_headless_browser", False))
    vol = float(cfg.get("learning_query_volume_scale", 0.65))
    vol = max(0.25, min(1.0, vol))
    max_per_source = max(1, int(max_per_source * vol))
    resolved_chatlog_terms = resolve_chatlog_search_terms(
        topics,
        cfg=cfg,
        explicit_terms=chatlog_search_terms,
    )

    collected = []
    if web_urls:
        for url in web_urls[:5]:
            item = fetch_web_url(url.strip(), use_headless=use_headless_for_web and _playwright_available())
            if item:
                item["compressed"] = compress_with_llm(item.get("text", ""), llm_callback, module_name="summarizer")
                collected.append(item)
    if cfg.get("enable_moltbook_auto_learn", True):
        for item in fetch_moltbook_for_auto_learning(topics):
            item["compressed"] = compress_with_llm(item.get("text", ""), llm_callback, module_name="summarizer")
            collected.append(item)
    # ChatGPT conversation files (from import_chatgpt_export)
    if chatlogs_path:
        processed_marker = storage_path / ".processed_chatlogs.json"
        for item in fetch_chatlogs(
            chatlogs_path,
            max_files=max_chatlogs,
            processed_path=processed_marker,
            search_terms=resolved_chatlog_terms,
        ):
            item["compressed"] = compress_with_llm(item.get("text", ""), llm_callback, module_name="summarizer")
            collected.append(item)
    # Reddit
    for sub in reddit_subs:
        for item in fetch_reddit(sub, limit=max_per_source):
            item["compressed"] = compress_with_llm(item.get("text", ""), llm_callback, module_name="summarizer")
            collected.append(item)
    # RSS
    for feed in rss_feeds:
        for item in fetch_rss(feed, limit=max_per_source):
            item["compressed"] = compress_with_llm(item.get("text", ""), llm_callback, module_name="summarizer")
            collected.append(item)
    # Facebook (requires facebook_access_token in config or FACEBOOK_ACCESS_TOKEN env)
    if facebook_pages and facebook_access_token:
        for page in facebook_pages:
            page = page.strip()
            if not page:
                continue
            for item in fetch_facebook(page, facebook_access_token, limit=max_per_source):
                item["compressed"] = compress_with_llm(item.get("text", ""), llm_callback, module_name="summarizer")
                collected.append(item)
    # X (Twitter) – requires twitter_bearer_token in config or TWITTER_BEARER_TOKEN env
    if twitter_search_queries and twitter_bearer_token:
        for q in twitter_search_queries:
            q = q.strip()
            if not q:
                continue
            for item in fetch_twitter(q, twitter_bearer_token, limit=max_per_source):
                item["compressed"] = compress_with_llm(item.get("text", ""), llm_callback, module_name="summarizer")
                collected.append(item)
    sources_count = (
        (1 if chatlogs_path else 0)
        + len(reddit_subs)
        + len(rss_feeds)
        + (1 if web_urls else 0)
        + (1 if cfg.get("enable_moltbook_auto_learn", True) else 0)
        + (len(facebook_pages) if (facebook_pages and facebook_access_token) else 0)
        + (len(twitter_search_queries) if (twitter_search_queries and twitter_bearer_token) else 0)
    )
    return finalize_learned_collection(collected, storage_path, topics, memory, sources_count=sources_count or 1)


def run_mistral_chained_learning_session(
    storage_path: Path,
    topics: List[str],
    memory: Optional[Any],
    llm_callback: Optional[Callable[[str], tuple]],
    chatlogs_path: Optional[Path],
    twitter_bearer_token: Optional[str],
    default_reddit_subs: List[str],
    max_rounds: Optional[int] = None,
    per_source_cap: Optional[int] = None,
    seed_twitter_queries: Optional[List[str]] = None,
    chatlog_search_terms: Optional[List[str]] = None,
    disable_chatlog_rerank: bool = False,
) -> Dict[str, Any]:
    """
    Use local Mistral (Ollama) to choose X, Reddit, and Wikipedia targets round-by-round.
    Starts from ChatGPT export text (peek + ingested chatlog files), optional memory snippets,
    then each round's fetches are summarized for the next plan.
    """
    cfg = load_learning_config()
    rounds = int(max_rounds if max_rounds is not None else cfg.get("mistral_chained_max_rounds", 3))
    rounds = max(1, min(8, rounds))
    cap = int(per_source_cap if per_source_cap is not None else cfg.get("mistral_chained_per_source_cap", 3))
    cap = max(1, min(10, cap))
    chained_max_chatlogs = int(cfg.get("mistral_chained_max_chatlogs", min(int(cfg.get("max_chatlogs", 15)), DEFAULT_CHAINED_MAX_CHATLOGS)))
    chained_max_chatlogs = max(0, min(200, chained_max_chatlogs))
    raw_chatlog_backfill_cap = cfg.get("mistral_chained_chatlog_backfill_cap")
    if raw_chatlog_backfill_cap is None:
        raw_chatlog_backfill_cap = DEFAULT_CHAINED_CHATLOG_BACKFILL_CAP
    chained_chatlog_backfill_cap = int(raw_chatlog_backfill_cap)
    chained_chatlog_backfill_cap = max(0, min(chained_max_chatlogs, chained_chatlog_backfill_cap))
    raw_chatlog_revisit_cap = cfg.get("mistral_chained_chatlog_revisit_cap")
    if raw_chatlog_revisit_cap is None:
        raw_chatlog_revisit_cap = DEFAULT_CHAINED_CHATLOG_REVISIT_CAP
    chained_chatlog_revisit_cap = int(raw_chatlog_revisit_cap)
    chained_chatlog_revisit_cap = max(0, min(chained_max_chatlogs, chained_chatlog_revisit_cap))
    raw_chatlog_llm_rerank_top_n = cfg.get("mistral_chained_chatlog_llm_rerank_top_n")
    if raw_chatlog_llm_rerank_top_n is None:
        raw_chatlog_llm_rerank_top_n = DEFAULT_CHAINED_CHATLOG_LLM_RERANK_TOP_N
    chained_chatlog_llm_rerank_top_n = int(raw_chatlog_llm_rerank_top_n)
    chained_chatlog_llm_rerank_top_n = max(0, min(chained_max_chatlogs, chained_chatlog_llm_rerank_top_n))
    if disable_chatlog_rerank:
        chained_chatlog_llm_rerank_top_n = 0
    raw_moltbook_cooldown_hours = cfg.get("mistral_chained_moltbook_cooldown_hours")
    if raw_moltbook_cooldown_hours is None:
        raw_moltbook_cooldown_hours = DEFAULT_CHAINED_MOLTBOOK_COOLDOWN_HOURS
    chained_moltbook_cooldown_hours = float(raw_moltbook_cooldown_hours)
    raw_social_repeat_cooldown_hours = cfg.get("mistral_chained_social_repeat_cooldown_hours")
    if raw_social_repeat_cooldown_hours is None:
        raw_social_repeat_cooldown_hours = DEFAULT_CHAINED_SOCIAL_REPEAT_COOLDOWN_HOURS
    social_repeat_cooldown_hours = float(raw_social_repeat_cooldown_hours)
    seed_twitter_queries = list(seed_twitter_queries or cfg.get("twitter_search_queries") or [])
    resolved_chatlog_terms = resolve_chatlog_search_terms(
        topics,
        cfg=cfg,
        explicit_terms=chatlog_search_terms,
    )

    try:
        from .mistral_engine import MistralEngine
        from .ollama_model_config import get_canonical_ollama_model
        from .planner_readiness import should_short_circuit_verify_ollama_for_bad_tag

        _cm = get_canonical_ollama_model(log_once=False)
        if should_short_circuit_verify_ollama_for_bad_tag(_cm)[0]:
            logger.info(
                "[Chained learning] Skipping Mistral chain (canonical tag not an exact installed model; fix ELYSIA_OLLAMA_MODEL)",
            )
            return {
                "fetched": 0,
                "archived": 0,
                "admitted": 0,
                "rejected": 0,
                "cross_session_duplicates": 0,
                "mistral_chained_error": "skipped_bad_local_ollama_tag",
                "file": "",
                "memory_count": 0,
            }

        engine = MistralEngine(model=_cm)
    except Exception as e:
        logger.warning("[Chained learning] Mistral unavailable (%s); use flat learning session instead.", e)
        return {
            "fetched": 0,
            "archived": 0,
            "admitted": 0,
            "rejected": 0,
            "cross_session_duplicates": 0,
            "mistral_chained_error": str(e),
            "file": "",
            "memory_count": 0,
        }

    collected: List[Dict[str, Any]] = []
    chained_social_seen_path = storage_path / CHAINED_SOCIAL_SEEN_FILENAME
    chained_moltbook_state_path = storage_path / CHAINED_MOLTBOOK_STATE_FILENAME
    chained_social_seen_state = (
        _prune_chained_social_seen_state(
            _load_chained_social_seen_state(chained_social_seen_path),
            cooldown_hours=social_repeat_cooldown_hours,
        )
        if social_repeat_cooldown_hours > 0
        else {}
    )
    chained_social_seen_dirty = False
    if chatlogs_path and chained_max_chatlogs > 0:
        processed_marker = storage_path / ".processed_chatlogs.json"
        for item in fetch_chatlogs(
            chatlogs_path,
            max_files=chained_max_chatlogs,
            processed_path=processed_marker,
            search_terms=resolved_chatlog_terms,
            max_backfill_files=chained_chatlog_backfill_cap,
            max_revisit_files=chained_chatlog_revisit_cap,
            llm_reranker=(None if disable_chatlog_rerank else engine),
            llm_rerank_top_n=chained_chatlog_llm_rerank_top_n,
        ):
            item["compressed"] = compress_with_llm(item.get("text", ""), llm_callback, module_name="summarizer")
            collected.append(item)

    if cfg.get("enable_moltbook_auto_learn", True):
        moltbook_state = _load_chained_moltbook_state(chained_moltbook_state_path)
        if _chained_moltbook_allowed(moltbook_state, cooldown_hours=chained_moltbook_cooldown_hours):
            moltbook_items = fetch_moltbook_for_auto_learning(topics)
            if moltbook_items:
                collected_at = _utc_now().strftime("%Y-%m-%dT%H:%M:%S") + "Z"
                last_title = ""
                for item in moltbook_items:
                    item["compressed"] = compress_with_llm(item.get("text", ""), llm_callback, module_name="summarizer")
                    item["mistral_round"] = -1
                    collected.append(item)
                    last_title = str(item.get("title") or "")[:160]
                _save_chained_moltbook_state(
                    chained_moltbook_state_path,
                    last_collected_at=collected_at,
                    last_title=last_title,
                )
        else:
            logger.info(
                "[Chained learning] skipped Moltbook during cooldown title=%s",
                str(moltbook_state.get("last_title") or "")[:80] or "recent_session",
            )

    parts: List[str] = []
    if chatlogs_path and chained_max_chatlogs > 0:
        peek_chatlog_files = max(1, min(3, chained_max_chatlogs))
        peek = peek_chatlogs_context(
            chatlogs_path,
            max_files=peek_chatlog_files,
            search_terms=resolved_chatlog_terms,
            max_backfill_files=min(chained_chatlog_backfill_cap, 1),
            max_revisit_files=min(chained_chatlog_revisit_cap, 2),
        )
        if peek:
            parts.append("ChatGPT exports (snippets for planning):\n" + peek)
    if topics:
        parts.append("Config topics: " + ", ".join(str(t) for t in topics[:16]))
    if memory:
        try:
            if hasattr(memory, "recall_last"):
                rm = memory.recall_last(8)
                lines = []
                for m in (rm or [])[:8]:
                    if isinstance(m, dict):
                        lines.append(str(m.get("thought", ""))[:220])
                    else:
                        lines.append(str(m)[:220])
                if lines:
                    parts.append("Recent memory:\n" + "\n".join(lines))
        except Exception as e:
            logger.debug("Chained learning memory context: %s", e)

    base_context = "\n\n".join(parts)
    round_summaries: List[str] = []
    context = _compose_chained_learning_context(base_context, round_summaries)
    seen_tw: set = set()
    seen_rd: set = set()
    seen_wiki: set = set()
    seen_google: set = set()
    # Do not use ``default_reddit_subs`` here: callers pass the general configured list (often includes
    # passive_income / entrepreneur-style subs). Empty-plan recovery should stay tight (see CHAINED_EMPTY_PLAN_REDDIT_SEEDS).
    override_subs = cfg.get("mistral_chained_empty_plan_reddit_subs")
    if isinstance(override_subs, list) and any(str(s).strip() for s in override_subs):
        seed_raw = override_subs
    else:
        seed_raw = CHAINED_EMPTY_PLAN_REDDIT_SEEDS
    seeds_sub = [re.sub(r"[^A-Za-z0-9_]", "", str(s).strip())[:50] for s in seed_raw if str(s).strip()][:5]
    _ = default_reddit_subs  # API param; round-1 empty-plan uses ``seeds_sub`` from CHAINED_EMPTY_PLAN_* / config override.

    for r in range(rounds):
        plan = engine.suggest_learning_targets(
            context,
            r,
            {
                "twitter": list(seen_tw)[-35:],
                "reddit_search": list(seen_rd)[-35:],
                "wikipedia": list(seen_wiki)[-35:],
                "google": list(seen_google)[-35:],
            },
            module_name="planner",
        )
        if plan:
            sanitized_plan = sanitize_chained_learning_plan(
                plan,
                topics=topics,
                cfg=cfg,
                seed_twitter_queries=seed_twitter_queries,
                default_reddit_subs=default_reddit_subs,
                per_source_cap=cap,
            )
            if sanitized_plan != plan:
                logger.info("[Chained learning] sanitized round %d plan", r + 1)
            plan = sanitized_plan
        reasoning = (plan.get("reasoning") or "")[:500]
        logger.info("[Chained learning] round %d/%d Mistral: %s", r + 1, rounds, reasoning)
        round_items: List[Dict[str, Any]] = []

        empty_plan = not plan or not any([
            plan.get("twitter_queries"),
            plan.get("reddit_subreddits_new"),
            plan.get("reddit_searches"),
            plan.get("wikipedia_titles"),
            plan.get("google_queries"),
        ])
        if empty_plan:
            if r == 0:
                plan = {
                    # Broad Twitter seeds are especially noisy during startup when Mistral
                    # explicitly declined to plan; keep the fallback to lower-noise sources.
                    "twitter_queries": [],
                    "reddit_subreddits_new": seeds_sub[:cap] if seeds_sub else ["MachineLearning"],
                    "reddit_searches": [],
                    "wikipedia_titles": ["Artificial intelligence", "Large language model"][:cap],
                    "google_queries": [],
                    "reasoning": "fallback: reddit/wiki config seeds / defaults",
                }
                logger.info("[Chained learning] using seed fallback for round 1")
            else:
                logger.info("[Chained learning] empty plan after round 1 — stopping early")
                break

        for q in (plan.get("twitter_queries") or [])[:cap]:
            qn = (q or "").strip()[:200]
            if not qn or not twitter_bearer_token:
                continue
            kl = qn.lower()
            if kl in seen_tw:
                continue
            seen_tw.add(kl)
            for item in fetch_twitter(qn, twitter_bearer_token, limit=cap):
                if not _should_collect_chained_social_item(item, topics):
                    logger.info(
                        "[Chained learning] skipped low-signal twitter item score=%s title=%s",
                        item.get("signal_score", ""),
                        str(item.get("title") or "")[:70],
                    )
                    continue
                repeat_key = _chained_social_recent_repeat_key(
                    item,
                    chained_social_seen_state,
                    cooldown_hours=social_repeat_cooldown_hours,
                )
                if repeat_key:
                    logger.info(
                        "[Chained learning] skipped recent twitter repeat key=%s title=%s",
                        repeat_key[:90],
                        str(item.get("title") or "")[:70],
                    )
                    continue
                _mark_chained_social_item_seen(item, chained_social_seen_state)
                chained_social_seen_dirty = True
                item["compressed"] = compress_with_llm(item.get("text", ""), llm_callback, module_name="summarizer")
                item["mistral_round"] = r
                collected.append(item)
                round_items.append(item)

        for sub in (plan.get("reddit_subreddits_new") or [])[:cap]:
            subn = re.sub(r"[^A-Za-z0-9_]", "", (sub or "").strip())[:50]
            if not subn:
                continue
            key = f"new:{subn.lower()}"
            if key in seen_rd:
                continue
            seen_rd.add(key)
            for item in fetch_reddit(subn, limit=cap):
                if not _should_collect_chained_social_item(item, topics):
                    logger.info(
                        "[Chained learning] skipped low-signal reddit item score=%s title=%s",
                        item.get("signal_score", ""),
                        str(item.get("title") or "")[:70],
                    )
                    continue
                repeat_key = _chained_social_recent_repeat_key(
                    item,
                    chained_social_seen_state,
                    cooldown_hours=social_repeat_cooldown_hours,
                )
                if repeat_key:
                    logger.info(
                        "[Chained learning] skipped recent reddit repeat key=%s title=%s",
                        repeat_key[:90],
                        str(item.get("title") or "")[:70],
                    )
                    continue
                _mark_chained_social_item_seen(item, chained_social_seen_state)
                chained_social_seen_dirty = True
                item["compressed"] = compress_with_llm(item.get("text", ""), llm_callback, module_name="summarizer")
                item["mistral_round"] = r
                collected.append(item)
                round_items.append(item)

        for spec in (plan.get("reddit_searches") or [])[:cap]:
            if not isinstance(spec, dict):
                continue
            subn = re.sub(r"[^A-Za-z0-9_]", "", str(spec.get("subreddit", "")).strip())[:50]
            qn = str(spec.get("q", "")).strip()[:300]
            if not subn or not qn:
                continue
            key = f"search:{subn.lower()}:{qn.lower()}"
            if key in seen_rd:
                continue
            seen_rd.add(key)
            for item in fetch_reddit_search(subn, qn, limit=cap):
                if not _should_collect_chained_social_item(item, topics):
                    logger.info(
                        "[Chained learning] skipped low-signal reddit-search item score=%s title=%s",
                        item.get("signal_score", ""),
                        str(item.get("title") or "")[:70],
                    )
                    continue
                repeat_key = _chained_social_recent_repeat_key(
                    item,
                    chained_social_seen_state,
                    cooldown_hours=social_repeat_cooldown_hours,
                )
                if repeat_key:
                    logger.info(
                        "[Chained learning] skipped recent reddit-search repeat key=%s title=%s",
                        repeat_key[:90],
                        str(item.get("title") or "")[:70],
                    )
                    continue
                _mark_chained_social_item_seen(item, chained_social_seen_state)
                chained_social_seen_dirty = True
                item["compressed"] = compress_with_llm(item.get("text", ""), llm_callback, module_name="summarizer")
                item["mistral_round"] = r
                collected.append(item)
                round_items.append(item)

        for title in (plan.get("wikipedia_titles") or [])[:cap]:
            tn = (title or "").strip()[:200]
            if not tn:
                continue
            if tn.lower() in seen_wiki:
                continue
            seen_wiki.add(tn.lower())
            witem = fetch_wikipedia_summary(tn)
            if witem:
                witem["compressed"] = compress_with_llm(witem.get("text", ""), llm_callback, module_name="summarizer")
                witem["mistral_round"] = r
                collected.append(witem)
                round_items.append(witem)

        if bool(cfg.get("mistral_chained_google_enabled", True)):
            for gq in (plan.get("google_queries") or [])[:cap]:
                gn = (gq or "").strip()[:220]
                if not gn:
                    continue
                gkl = gn.lower()
                if gkl in seen_google:
                    continue
                seen_google.add(gkl)
                for gitem in fetch_google_custom_search(gn, cfg=cfg, limit=cap):
                    gitem["compressed"] = compress_with_llm(gitem.get("text", ""), llm_callback, module_name="summarizer")
                    gitem["mistral_round"] = r
                    collected.append(gitem)
                    round_items.append(gitem)

        round_summaries.append(_summarize_chained_learning_round(r, reasoning, round_items))
        context = _compose_chained_learning_context(base_context, round_summaries)

    if social_repeat_cooldown_hours > 0 and (chained_social_seen_dirty or chained_social_seen_state):
        _save_chained_social_seen_state(
            chained_social_seen_path,
            _prune_chained_social_seen_state(
                chained_social_seen_state,
                cooldown_hours=social_repeat_cooldown_hours,
            ),
        )

    sc = max(1, rounds + (1 if chatlogs_path else 0))
    out = finalize_learned_collection(collected, storage_path, topics or [], memory, sources_count=sc)
    out["mistral_chained_rounds"] = rounds
    out["mistral_chained"] = True
    return out


# In-memory normalization ranges (aligned with config_validator)
_LEARNING_CONFIG_INT_DEFAULTS = {
    "min_relevance_score": (2, 0, 10),
    "min_reuse_potential": (1, 0, 5),
    "max_archived_per_session": (100, 10, 500),
    "max_memory_per_session": (20, 1, 100),
    "max_per_source_memory": (5, 1, 50),
    "dedup_window_days": (30, 1, 365),
    "max_chatlogs": (20, 0, 500),
    "mistral_chained_max_chatlogs": (DEFAULT_CHAINED_MAX_CHATLOGS, 0, 200),
    "mistral_chained_chatlog_backfill_cap": (DEFAULT_CHAINED_CHATLOG_BACKFILL_CAP, 0, 50),
    "mistral_chained_chatlog_revisit_cap": (DEFAULT_CHAINED_CHATLOG_REVISIT_CAP, 0, 50),
    "mistral_chained_chatlog_llm_rerank_top_n": (DEFAULT_CHAINED_CHATLOG_LLM_RERANK_TOP_N, 0, 20),
    "mistral_chained_moltbook_cooldown_hours": (DEFAULT_CHAINED_MOLTBOOK_COOLDOWN_HOURS, 0, 168),
    "mistral_chained_social_repeat_cooldown_hours": (DEFAULT_CHAINED_SOCIAL_REPEAT_COOLDOWN_HOURS, 0, 168),
    "max_per_source": (3, 1, 50),
    "mistral_chained_max_rounds": (3, 1, 8),
    "mistral_chained_per_source_cap": (3, 1, 10),
}
_LEARNING_CONFIG_FLOAT_DEFAULTS = {
    "interval_hours": (6.0, 0.5, 24),
    "learning_query_volume_scale": (0.65, 0.25, 1.0),
}
_LEARNING_CONFIG_BOOL_SAFE_DEFAULTS = {
    "allow_reddit_into_memory": False,
    "allow_strategic_into_memory": False,
    "mistral_chained_learning": False,
}


def _normalize_learning_config(cfg: Dict[str, Any]) -> Dict[str, Any]:
    """Apply safe normalization in-memory. Never returns values that weaken quality gates.
    Invalid booleans use safe default (no truthy coercion)."""
    out = dict(cfg)
    for key, (default, min_val, max_val) in _LEARNING_CONFIG_INT_DEFAULTS.items():
        try:
            v = int(out.get(key)) if out.get(key) is not None else None
        except (TypeError, ValueError):
            v = None
        if v is None:
            out[key] = default
        elif v < min_val or v > max_val:
            out[key] = max(min_val, min(max_val, v))
    for key, (default, min_val, max_val) in _LEARNING_CONFIG_FLOAT_DEFAULTS.items():
        try:
            v = float(out.get(key)) if out.get(key) is not None else None
        except (TypeError, ValueError):
            v = None
        if v is None:
            out[key] = default
        elif v < min_val or v > max_val:
            out[key] = max(min_val, min(max_val, v))
    for key, default in _LEARNING_CONFIG_BOOL_SAFE_DEFAULTS.items():
        v = out.get(key)
        if v is None or not isinstance(v, bool):
            out[key] = default
    # Moltbook auto-learn defaults ON (bounded browser; disable via auto_learning.json).
    v_molt = out.get("enable_moltbook_auto_learn")
    if v_molt is None:
        out["enable_moltbook_auto_learn"] = True
    elif isinstance(v_molt, bool):
        pass
    elif isinstance(v_molt, (int, float)):
        out["enable_moltbook_auto_learn"] = bool(int(v_molt))
    else:
        out["enable_moltbook_auto_learn"] = str(v_molt).strip().lower() in ("1", "true", "yes", "on")
    return out


def load_learning_config() -> Dict[str, Any]:
    """Load auto_learning.json if present. Returns normalized config with safe defaults."""
    cfg_path = Path(__file__).parent.parent / "config" / "auto_learning.json"
    cfg: Dict[str, Any] = {}
    if cfg_path.exists():
        try:
            with open(cfg_path, "r") as f:
                cfg = json.load(f)
        except Exception as e:
            logger.debug(f"auto_learning.json: {e}")
    return _normalize_learning_config(cfg)


class AutoLearningScheduler:
    """Background scheduler for auto-learning."""

    def __init__(
        self,
        system_ref=None,
        interval_hours: float = 6.0,
        storage_path: Optional[Path] = None,
        chatlogs_path: Optional[Path] = None,
        topics: Optional[List[str]] = None,
        reddit_subs: Optional[List[str]] = None,
        rss_feeds: Optional[List[str]] = None,
        max_chatlogs: int = 20,
    ):
        cfg = load_learning_config()
        self.system_ref = system_ref
        iv = interval_hours if interval_hours and interval_hours != 6 else (cfg.get("interval_hours") or 6)
        self.interval_sec = max(3600, iv * 3600)  # min 1 hour
        self.storage_path = storage_path or get_learned_storage_path()
        self.chatlogs_path = chatlogs_path or get_chatlogs_path()
        self.max_chatlogs = cfg.get("max_chatlogs") or max_chatlogs
        self.topics = topics or cfg.get("topics") or DEFAULT_TOPICS
        self.reddit_subs = reddit_subs or cfg.get("reddit_subs") or DEFAULT_REDDIT_SUBS
        self.rss_feeds = rss_feeds or cfg.get("rss_feeds") or DEFAULT_RSS_FEEDS
        self.facebook_pages = cfg.get("facebook_page_ids") or DEFAULT_FACEBOOK_PAGES
        self.facebook_access_token = cfg.get("facebook_access_token") or os.environ.get("FACEBOOK_ACCESS_TOKEN") or ""
        self.twitter_search_queries = cfg.get("twitter_search_queries") or DEFAULT_TWITTER_SEARCH_QUERIES
        self.twitter_bearer_token = cfg.get("twitter_bearer_token") or os.environ.get("TWITTER_BEARER_TOKEN") or ""
        raw_web = cfg.get("web_urls") or []
        self.web_urls = [u.strip() for u in raw_web if isinstance(u, str) and u.strip().startswith(("http://", "https://"))][:5]
        self.max_per_source = cfg.get("max_per_source", 3)
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._last_run: Optional[datetime] = None
        self._bad_session_cooldown_until: Optional[float] = None
        self._bad_session_streak: int = 0

    def _startup_guard_reason(self, cfg: Dict[str, Any]) -> Optional[str]:
        if not self.system_ref:
            return None
        guardian = getattr(self.system_ref, "guardian", None)
        if guardian is None:
            return None
        try:
            from .startup_runtime_guard import (
                early_runtime_budget_active,
                startup_age_sec,
                startup_memory_thin_mode_active,
            )
        except Exception:
            return None

        if early_runtime_budget_active(guardian):
            return "early_runtime_budget"
        if startup_memory_thin_mode_active(guardian):
            return "memory_thin"

        if self._last_run is None:
            try:
                min_uptime = int(cfg.get("auto_learning_startup_min_uptime_sec", 300))
            except Exception:
                min_uptime = 300
            age = startup_age_sec(guardian)
            if age is not None and age < max(30, min_uptime):
                try:
                    from .planner_readiness import compute_readiness_label

                    lbl = compute_readiness_label()
                except Exception:
                    lbl = "unknown"
                if lbl != "ready":
                    return f"startup_not_settled:{lbl}"
        return None

    @staticmethod
    def _log_learning_run_status(status: str, reason: str) -> None:
        logger.info("[Auto-Learning] run_status=%s reason=%s", status, reason)

    def _get_llm_callback(self) -> Optional[Callable[..., tuple]]:
        if not self.system_ref:
            return None
        return make_learning_llm_callback(self.system_ref)

    def _get_memory(self):
        """Get GuardianCore memory from system_ref so learned content flows into the main system."""
        if not self.system_ref:
            return None
        guardian = getattr(self.system_ref, "guardian", None)
        return getattr(guardian, "memory", None) if guardian else None

    def _run_once(self) -> None:
        try:
            now = time.time()
            if self._bad_session_cooldown_until is not None and now < self._bad_session_cooldown_until:
                self._log_learning_run_status("skipped", "bad_session_cooldown")
                return
            llm = self._get_llm_callback()
            memory = self._get_memory()
            cfg = load_learning_config()
            guard_reason = self._startup_guard_reason(cfg)
            if guard_reason:
                self._log_learning_run_status("deferred", guard_reason)
                return
            startup_thin_mode = False
            if self.system_ref and getattr(self.system_ref, "guardian", None) is not None:
                try:
                    from .startup_runtime_guard import startup_memory_thin_mode_active

                    startup_thin_mode = startup_memory_thin_mode_active(self.system_ref.guardian)
                except Exception:
                    startup_thin_mode = False
            if cfg.get("mistral_chained_learning") is True:
                result = run_mistral_chained_learning_session(
                    storage_path=self.storage_path,
                    topics=self.topics,
                    memory=memory,
                    llm_callback=llm,
                    chatlogs_path=self.chatlogs_path,
                    twitter_bearer_token=self.twitter_bearer_token or None,
                    default_reddit_subs=self.reddit_subs,
                    seed_twitter_queries=self.twitter_search_queries,
                    disable_chatlog_rerank=startup_thin_mode,
                )
                if result.get("mistral_chained_error"):
                    self._log_learning_run_status("guarded", f"chained_unavailable:{result.get('mistral_chained_error')}")
                    logger.info("[Auto-Learning] Chained learning unavailable; running standard session")
                    result = run_learning_session(
                        storage_path=self.storage_path,
                        topics=self.topics,
                        reddit_subs=self.reddit_subs,
                        rss_feeds=self.rss_feeds,
                        chatlogs_path=self.chatlogs_path,
                        web_urls=self.web_urls if self.web_urls else None,
                        facebook_pages=self.facebook_pages if self.facebook_access_token else None,
                        facebook_access_token=self.facebook_access_token or None,
                        twitter_search_queries=self.twitter_search_queries if self.twitter_bearer_token else None,
                        twitter_bearer_token=self.twitter_bearer_token or None,
                        max_per_source=self.max_per_source,
                        max_chatlogs=self.max_chatlogs,
                        llm_callback=llm,
                        memory=memory,
                    )
            else:
                result = run_learning_session(
                    storage_path=self.storage_path,
                    topics=self.topics,
                    reddit_subs=self.reddit_subs,
                    rss_feeds=self.rss_feeds,
                    chatlogs_path=self.chatlogs_path,
                    web_urls=self.web_urls if self.web_urls else None,
                    facebook_pages=self.facebook_pages if self.facebook_access_token else None,
                    facebook_access_token=self.facebook_access_token or None,
                    twitter_search_queries=self.twitter_search_queries if self.twitter_bearer_token else None,
                    twitter_bearer_token=self.twitter_bearer_token or None,
                    max_per_source=self.max_per_source,
                    max_chatlogs=self.max_chatlogs,
                    llm_callback=llm,
                    memory=memory,
                )
            self._last_run = datetime.now()
            if result.get("fetched", 0) == 0:
                self._log_learning_run_status("skipped", "no_items_fetched")
                logger.info("[Auto-Learning] Session complete: no items fetched")
            else:
                self._log_learning_run_status("ok", "fetched_items")
                logger.debug(
                    "[Auto-Learning] Result: fetched=%d archived=%d admitted=%d rejected=%d",
                    result.get("fetched", 0), result.get("archived", 0),
                    result.get("admitted", 0), result.get("rejected", 0),
                )
            ex: Optional[Dict[str, Any]] = None
            try:
                rd0 = (self.reddit_subs[0] if self.reddit_subs else "MachineLearning")
                ex = maybe_run_high_value_learning_expansion(
                    session_result=result,
                    storage_path=self.storage_path,
                    topics=self.topics,
                    cfg=cfg,
                    llm_callback=llm,
                    memory=memory,
                    twitter_bearer_token=self.twitter_bearer_token or None,
                    default_reddit_sub=str(rd0),
                )
                if ex and not ex.get("skipped"):
                    logger.info(
                        "[Auto-Learning] High-value expansion admitted=%s fetched=%s",
                        ex.get("admitted"),
                        ex.get("fetched"),
                    )
            except Exception as e:
                logger.debug("[Auto-Learning] high-value expansion: %s", e)
            try:
                from .local_ai_selfbuild_corpus import (
                    export_selfbuild_chunk_embeddings,
                    rebuild_local_ai_selfbuild_rag_chunks,
                    should_run_selfbuild_embed_export,
                    should_run_selfbuild_rag_export,
                )

                exp_sb = int((ex or {}).get("local_ai_selfbuild_appended") or 0) if (ex and not ex.get("skipped")) else 0
                sb_appended = int(result.get("local_ai_selfbuild_appended") or 0) + exp_sb
                rstats: Dict[str, Any] = {}
                if should_run_selfbuild_rag_export(cfg, self.storage_path, corpus_rows_appended_session=sb_appended):
                    rstats = rebuild_local_ai_selfbuild_rag_chunks(self.storage_path, cfg)
                    if rstats.get("ok"):
                        logger.info(
                            "[Auto-Learning] local_ai_selfbuild RAG chunks=%s corpus_rows=%s",
                            rstats.get("chunks_written"),
                            rstats.get("corpus_rows_scanned"),
                        )
                rag_ok = bool(rstats.get("ok"))
                if should_run_selfbuild_embed_export(
                    cfg,
                    self.storage_path,
                    rag_rebuilt_ok=rag_ok,
                    corpus_rows_appended_session=sb_appended,
                ):
                    em = export_selfbuild_chunk_embeddings(self.storage_path, cfg)
                    n_emb = int(em.get("rows_appended") or 0)
                    if n_emb > 0:
                        logger.info(
                            "[Auto-Learning] local_ai_selfbuild embeddings appended=%d model=%s",
                            n_emb,
                            em.get("model"),
                        )
            except Exception as e:
                logger.debug("[Auto-Learning] local_ai_selfbuild RAG/embed: %s", e)
            # Event-driven adversarial: bad learning session (high rejection, noisy)
            try:
                guardian = getattr(self.system_ref, "guardian", None) if self.system_ref else None
                if guardian:
                    from .adversarial_self_learning import trigger_adversarial_on_event
                    from .adversarial_self_learning import TRIGGER_BAD_LEARNING_SESSION
                    adv_result = trigger_adversarial_on_event(guardian, TRIGGER_BAD_LEARNING_SESSION, result)
                    dup_sat = learning_run_duplicate_saturated(result)
                    if dup_sat and result.get("fetched", 0) > 0:
                        self._log_learning_run_status("ok", "duplicate_saturated_low_yield")
                        logger.info("[Auto-Learning] Skipping bad-session cooldown (duplicate-saturated run)")
                        self._bad_session_streak = 0
                    elif adv_result and result.get("fetched", 0) > 0:
                        ratio = result.get("rejected", 0) / max(1, result["fetched"])
                        if ratio >= 0.7 or (result.get("admitted", 0) == 0 and result["fetched"] >= 3):
                            cfg_path = Path(__file__).parent.parent / "config" / "memory_pressure.json"
                            cooldown_min = 90
                            mult = 1.0
                            if cfg_path.exists():
                                try:
                                    with open(cfg_path, "r") as f:
                                        pc = json.load(f)
                                    cooldown_min = pc.get("bad_learning_session_cooldown_minutes", 90)
                                    mult = float(pc.get("bad_learning_streak_cooldown_multiplier", 3.0))
                                except Exception:
                                    pass
                            self._bad_session_streak = getattr(self, "_bad_session_streak", 0) + 1
                            if self._bad_session_streak >= 2:
                                cooldown_min = int(cooldown_min * mult)
                            self._bad_session_cooldown_until = time.time() + (cooldown_min * 60)
                            self._log_learning_run_status("bad", "high_rejection_or_zero_admit")
                            logger.info(
                                "[Auto-Learning] Bad session cooldown: %d min (streak=%s)",
                                cooldown_min,
                                self._bad_session_streak,
                            )
                        else:
                            self._bad_session_streak = 0
            except Exception as ae:
                logger.debug("Adversarial learning trigger: %s", ae)
        except Exception as e:
            logger.warning("[Auto-Learning] Session failed: %s", e)

    def _loop(self) -> None:
        while self._running:
            self._run_once()
            for _ in range(int(self.interval_sec)):
                if not self._running:
                    break
                time.sleep(1)

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True, name="AutoLearning")
        self._thread.start()
        logger.info("[Auto-Learning] Started (interval=%.1fh, storage=%s)", self.interval_sec / 3600, self.storage_path)

    def stop(self) -> None:
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)
        logger.info("[Auto-Learning] Stopped")
