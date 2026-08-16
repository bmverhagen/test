"""Automatische attribuut-frase extractie uit Amazon-titels.

Geen curated taxonomie: phrases ontstaan uit n-grams die genoeg in de
long-tail catalogus voorkomen. Merknamen en verpakkingsruis worden
weggefilterd zodat clusters op productattributen landen (ingredient,
format, concern), niet op brand of pack-size.
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from dataclasses import dataclass

TOKEN_RE = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)?", re.I)
# "150ml", "60ct", "2pk" etc. — verpakkingsruis, geen attribuut
SIZE_RE = re.compile(r"^\d+(?:ml|g|kg|oz|l|lt|liter|ct|pcs|pk|pack)?$", re.I)

# Generieke catalogus-ruis (EN + NL + units). Geen product-attributen.
STOPWORDS = {
    "a", "an", "the", "and", "or", "for", "with", "of", "to", "in", "on",
    "by", "from", "into", "new", "best", "pack", "set", "kit", "pcs", "pc",
    "ml", "oz", "g", "kg", "l", "liter", "piece", "pieces", "count", "ct",
    "size", "large", "small", "medium", "x", "xxl", "xl", "s", "m",
    "shampoo", "conditioner", "hair", "haar", "product", "products",
    "men", "women", "unisex", "adult", "kids", "baby", "amazon", "brand",
    "official", "original", "premium", "professional", "salon", "formula",
    "classic", "fresh", "daily", "care", "verzorging", "voor", "met", "en",
    "de", "het", "een", "van", "tegen", "extra", "strong", "soft",
    "deep", "clean", "smooth", "hold", "soft", "duo", "mist", "drops",
    "treatment", "mask", "cream", "oil", "spray", "rinse",  # te generiek als unigram-brug
    "beauty", "vegan", "organic", "natural",
}

# Eerste woord van veel beauty-titels is het merk — die strippen we apart.
# Demo-merken + veelvoorkomende echte merken zodat clusters niet op brand landen.
KNOWN_BRANDS = {
    "novellia", "kuralux", "herbastra", "vionne", "tressano", "lumeya",
    "capellio", "nordhaar", "silkero", "botanera", "riva", "maneful",
    "aurelia", "driftwood", "pebbly", "solara", "nimbus", "oriva",
    "olaplex", "mielle", "ogx", "garnier", "loreal", "redken", "amika",
    "batiste", "cerave", "ouai", "gisou", "verb", "moroccanoil",
}


@dataclass(frozen=True)
class PhraseStats:
    phrase: str
    asin_count: int
    asins: frozenset[str]


def tokenize(title: str) -> list[str]:
    tokens = [t.lower() for t in TOKEN_RE.findall(title)]
    # Strip leading brand token if known
    if tokens and tokens[0] in KNOWN_BRANDS:
        tokens = tokens[1:]
    # Tweede token soms "Beauty"/"Beauty"-achtig merkdeel ("Riva Beauty")
    if tokens and tokens[0] in KNOWN_BRANDS:
        tokens = tokens[1:]
    out: list[str] = []
    for t in tokens:
        if t in STOPWORDS or SIZE_RE.match(t) or len(t) <= 1:
            continue
        out.append(t)
    return out


def ngrams(tokens: list[str], n: int) -> list[str]:
    if len(tokens) < n:
        return []
    return [" ".join(tokens[i : i + n]) for i in range(len(tokens) - n + 1)]


def extract_candidate_phrases(title: str) -> set[str]:
    """Unigrams + bigrams + trigrams uit één titel (na stopword/brand filter)."""
    tokens = tokenize(title)
    phrases: set[str] = set(tokens)
    phrases.update(ngrams(tokens, 2))
    phrases.update(ngrams(tokens, 3))
    return phrases


def build_phrase_index(
    asins: dict[str, dict],
    *,
    min_df: int = 3,
    max_df_ratio: float = 0.45,
) -> dict[str, PhraseStats]:
    """Bouw phrase → ASINs index; filter te zeldzaam én te generiek."""
    phrase_asins: dict[str, set[str]] = defaultdict(set)
    for asin, meta in asins.items():
        for phrase in extract_candidate_phrases(meta["title"]):
            phrase_asins[phrase].add(asin)

    n = max(len(asins), 1)
    max_df = max(min_df, int(n * max_df_ratio))
    kept: dict[str, PhraseStats] = {}
    for phrase, members in phrase_asins.items():
        df = len(members)
        if df < min_df or df > max_df:
            continue
        # Unigrams die alleen als deel van een sterkere bigram voorkomen mogen blijven;
        # we laten ze staan — clustering aggregeert later.
        kept[phrase] = PhraseStats(phrase=phrase, asin_count=df, asins=frozenset(members))
    return kept


def asin_phrase_map(
    asins: dict[str, dict], phrases: dict[str, PhraseStats]
) -> dict[str, set[str]]:
    """ASIN → set van phrases die op die titel matchen."""
    out: dict[str, set[str]] = defaultdict(set)
    for phrase, stats in phrases.items():
        for asin in stats.asins:
            out[asin].add(phrase)
    return out
