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
    # Plurals are only folded where both forms are explicitly high-confidence.
    # Blanket trailing-s reduction conflated proper nouns (Atlas -> Atla).
    "vault": ("vault", "vaults"),
}
_EQUIVALENTS = {
    variant: canonical
    for canonical, variants in _EQUIVALENT_GROUPS.items()
    for variant in variants
}
def normalize_retrieval_term(term: str) -> str:
    """Use only explicit, high-confidence local vocabulary equivalences.

    Inferring a singular from a trailing "s" is unsafe for place/person names,
    brand names and technical identifiers. A missed paraphrase is preferable to
    presenting a different person's or place's fact as the requested one.
    Additional aliases require positive AND hard-negative retrieval tests.
    No LLM inference, external calls, data writes or source-text rewriting.
    """
    word = term.casefold()
    return _EQUIVALENTS.get(word, word)
