"""Shared helpers for conditioner rank scraping."""

from __future__ import annotations

import re
from typing import Any

HENKEL_BRANDS = [
    "Syoss",
    "Schwarzkopf",
    "Gliss",
    "Gliss Kur",
    "Taft",
    "got2b",
    "Palette",
    "Poly Palette",
    "Schauma",
    "Nature Box",
]


def detect_brand(title: str) -> str | None:
    text = title or ""
    # longest match first
    for brand in sorted(HENKEL_BRANDS, key=len, reverse=True):
        if re.search(rf"\b{re.escape(brand)}\b", text, flags=re.I):
            return brand
    # common non-Henkel brands for labeling
    known = [
        "Andrélon",
        "Andrelon",
        "Elvive",
        "L'Oréal",
        "L'Oreal",
        "Garnier",
        "Loving Blends",
        "Head & Shoulders",
        "John Frieda",
        "OGX",
        "Olaplex",
        "Dove",
        "Guhl",
        "Neutral",
        "Weleda",
        "Urtekram",
        "Plantur",
        "Kruidvat",
        "Etos",
        "Pantene",
        "Moroccanoil",
        "Redken",
        "Wella",
        "Cantu",
        "Shea Moisture",
        "SheaMoisture",
    ]
    for brand in sorted(known, key=len, reverse=True):
        if re.search(rf"\b{re.escape(brand)}\b", text, flags=re.I):
            return brand
    return None


def is_henkel(brand: str | None, title: str) -> bool:
    if brand and any(brand.casefold() == b.casefold() for b in HENKEL_BRANDS):
        return True
    return detect_brand(title) in HENKEL_BRANDS or any(
        re.search(rf"\b{re.escape(b)}\b", title or "", flags=re.I) for b in HENKEL_BRANDS
    )


def clean_title(title: str) -> str:
    title = re.sub(r"\s+", " ", title or "").strip()
    title = re.sub(r"^(Actie|Nieuw)\s+", "", title, flags=re.I)
    return title


def product(
    *,
    rank: int,
    title: str,
    url: str | None = None,
    price: str | None = None,
    brand: str | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    title = clean_title(title)
    brand = brand or detect_brand(title)
    row: dict[str, Any] = {
        "rank": rank,
        "title": title,
        "brand": brand,
        "is_henkel": is_henkel(brand, title),
        "price": price,
        "url": url,
    }
    if extra:
        row.update(extra)
    return row
