"""Small local-only lexical normalization shared by Elysia's memory retrieval.

This is intentionally not semantic reasoning: the vocabulary is finite, and
ambiguous concepts such as porch/deck or stain/finish remain distinct.
It changes *search matching*, never the original memory text or citations.
"""
from __future__ import annotations


_EQUIVALENT_GROUPS = {
    "cost": ("cost", "costs", "price", "prices", "priced", "pricing"),
    "stored": ("stored", "kept", "keeping", "storing"),
    "picture": ("picture", "pictures", "photo", "photos", "photograph", "photographs"),
    "repair": ("repair", "repairs", "repaired", "fix", "fixes", "fixed"),
    "purchase": ("purchase", "purchases", "purchased", "buy", "buys", "buying", "bought"),
}
_EQUIVALENTS = {
    variant: canonical
    for canonical, variants in _EQUIVALENT_GROUPS.items()
    for variant in variants
}
_PLURAL_INVARIANTS = frozenset({
    "series", "species", "news", "analysis", "status", "glass",
})


def normalize_retrieval_term(term: str) -> str:
    """Conservatively normalize a single already-tokenized English word.

    No cross-term expansion, LLM inference, external calls, or data writes.
    Do not introduce broad place/object equivalence without negative tests.
    """
    word = term.casefold()
    mapped = _EQUIVALENTS.get(word)
    if mapped is not None:
        return mapped
    if word in _PLURAL_INVARIANTS:
        return word
    if len(word) < 5:
        return word
    if word.endswith("ies") and len(word) > 5:
        word = word[:-3] + "y"
    elif word.endswith(("sses", "ches", "shes", "xes", "zes")):
        word = word[:-2]
    elif word.endswith("s") and not word.endswith(("ss", "us", "is")):
        word = word[:-1]
    return _EQUIVALENTS.get(word, word)
