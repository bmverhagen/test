from __future__ import annotations

import re

# Negatieve keywords voor nieuws-sentiment (Nederlands + Engels)
NEGATIVE_KEYWORDS = {
    "crash", "crisis", "decline", "drop", "fall", "plunge", "slump", "tumble",
    "loss", "losses", "miss", "misses", "missed", "warning", "warns", "cut",
    "cuts", "downgrade", "downgrades", "lawsuit", "investigation", "fraud",
    "scandal", "bankruptcy", "default", "recall", "layoff", "layoffs", "fire",
    "fired", "resign", "resigns", "probe", "fine", "fined", "penalty", "weak",
    "disappoint", "disappoints", "disappointing", "bearish", "selloff", "sell-off",
    "correction", "fears", "concern", "concerns", "risk", "risks", "threat",
    "daling", "crash", "verlies", "waarschuwing", "schandaal", "fraude",
    "faillissement", "ontslag", "boete", "zwak", "teleurstellend", "negatief",
    "bear", "short", "underperform", "profit warning", "guidance cut",
}

POSITIVE_KEYWORDS = {
    "surge", "rally", "gain", "gains", "beat", "beats", "upgrade", "upgrades",
    "record", "growth", "profit", "profits", "bullish", "soar", "soars", "jump",
    "jumps", "rise", "rises", "strong", "positive", "outperform", "buy rating",
    "winst", "groei", "stijging", "record",
}


def score_headline(text: str) -> float:
    """
    Sentiment score: -1 (zeer negatief) tot +1 (zeer positief).
    """
    if not text:
        return 0.0

    lower = text.lower()
    words = set(re.findall(r"[a-zà-ÿ']+", lower))

    neg = sum(1 for kw in NEGATIVE_KEYWORDS if kw in lower or kw in words)
    pos = sum(1 for kw in POSITIVE_KEYWORDS if kw in lower or kw in words)

    total = neg + pos
    if total == 0:
        return 0.0
    return (pos - neg) / total


def is_negative_sentiment(text: str, threshold: float = 0.3) -> bool:
    """True als headline negatief genoeg is (score <= -threshold)."""
    return score_headline(text) <= -threshold


def aggregate_sentiment(headlines: list[str]) -> float:
    if not headlines:
        return 0.0
    return sum(score_headline(h) for h in headlines) / len(headlines)
