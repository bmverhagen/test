"""Booking.com ``nflt`` filter chips and named aliases.

Codes are taken from the Capla store ``search.filters`` payload for
Zwarte Woud (dest_id=1477). Important corrections vs older docs:

- Balkon = ``roomfacility=17`` (not 32)
- Terras = ``roomfacility=123``
- Zwembad = ``hotelfacility=433`` (not ``popular_activities=2``)
- Sauna = ``popular_activities=10``
"""

from __future__ import annotations

import json
from functools import lru_cache
from importlib import resources
from pathlib import Path
from typing import Iterable

# Named aliases → one or more nflt chips.
FILTER_ALIASES: dict[str, tuple[str, ...]] = {
    # Score
    "score_9": ("review_score=90",),
    "score_8": ("review_score=80",),
    "score_7": ("review_score=70",),
    "score_6": ("review_score=60",),
    # Meals
    "breakfast": ("mealplan=1",),
    "half_board": ("mealplan=9",),
    "all_inclusive": ("mealplan=3",),
    "kitchen": ("mealplan=999",),
    "good_breakfast": ("rated_high=1",),
    # Facilities
    "pool": ("hotelfacility=433",),
    "parking": ("hotelfacility=2",),
    "wifi": ("hotelfacility=107",),
    "spa": ("hotelfacility=54",),
    "gym": ("hotelfacility=11",),
    "restaurant": ("hotelfacility=3",),
    "hot_tub": ("hotelfacility=63",),
    "ev_charger": ("hotelfacility=182",),
    "wheelchair": ("hotelfacility=185",),
    "front_desk_24h": ("hotelfacility=8",),
    "sauna": ("popular_activities=10",),
    # Room
    "balcony": ("roomfacility=17",),
    "terrace": ("roomfacility=123",),
    "balcony_or_terrace": ("roomfacility=17", "roomfacility=123"),
    "private_bathroom": ("roomfacility=38",),
    "bathtub": ("roomfacility=5",),
    "view": ("roomfacility=81",),
    "washing_machine": ("roomfacility=34",),
    "coffee_maker": ("roomfacility=120",),
    "kitchenette": ("roomfacility=999",),
    # Booking conditions
    "free_cancellation": ("fc=2",),
    "no_credit_card": ("fc=4",),
    "available_only": ("oos=1",),
    # Stay type
    "pets": ("stay_type=1",),
    "adults_only": ("stay_type=2",),
    "travel_proud": ("stay_type=4",),
    # Property type
    "hotels": ("ht_id=204",),
    "apartments": ("ht_id=201",),
    "bnb": ("ht_id=208",),
    "guest_houses": ("ht_id=216",),
    "holiday_homes": ("ht_id=220",),
    "villas": ("ht_id=213",),
    "entire_place": ("privacy_type=3",),
    # Bed preference
    "twin_beds": ("tdb=2",),
    "double_bed": ("tdb=3",),
    "king_bed": ("tdb=5",),
    "super_king_bed": ("tdb=6",),
    # Sustainability
    "sustainable": ("SustainablePropertyLevelFilter=4",),
}

PROPERTY_TYPES: dict[str, str] = {
    "apartments": "ht_id=201",
    "hostels": "ht_id=203",
    "hotels": "ht_id=204",
    "motels": "ht_id=205",
    "resorts": "ht_id=206",
    "bnb": "ht_id=208",
    "farm_stays": "ht_id=210",
    "holiday_parks": "ht_id=212",
    "villas": "ht_id=213",
    "campsites": "ht_id=214",
    "boats": "ht_id=215",
    "guest_houses": "ht_id=216",
    "holiday_homes": "ht_id=220",
    "lodges": "ht_id=221",
    "homestays": "ht_id=222",
    "country_houses": "ht_id=223",
}

REVIEW_SCORE_CHIPS: dict[float, str] = {
    9.0: "review_score=90",
    8.0: "review_score=80",
    7.0: "review_score=70",
    6.0: "review_score=60",
}

# Popular cities in/near Black Forest (uf= city filters from Capla).
CITY_FILTERS: dict[str, str] = {
    "baden-baden": "uf=-1743083",
    "freiburg": "uf=-1771505",
    "freudenstadt": "uf=-1771789",
    "karlsruhe": "uf=-1803994",
    "pforzheim": "uf=-1842944",
    "rust": "uf=-1854104",
    "titisee-neustadt": "uf=-1874960",
    "triberg": "uf=-1875833",
    "villingen-schwenningen": "uf=-1879835",
    "bad-wildbad": "uf=-1888060",
    "basel": "uf=-2551183",
    "feldberg": "uf=-1769232",
    "baiersbronn": "uf=-1743393",
    "offenburg": "uf=-1839098",
}


@lru_cache(maxsize=1)
def load_filter_catalog() -> list[dict[str, str]]:
    """Load the Capla-derived filter catalog shipped with the package."""
    try:
        root = resources.files("booking_scraper").joinpath("data/filter_catalog.json")
        payload = json.loads(root.read_text(encoding="utf-8"))
    except Exception:
        path = Path(__file__).with_name("data") / "filter_catalog.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
    return list(payload.get("chips") or [])


def resolve_alias(name: str) -> tuple[str, ...]:
    """Resolve a friendly filter name to nflt chip(s)."""
    key = name.strip().lower().replace(" ", "_").replace("-", "_")
    if key in FILTER_ALIASES:
        return FILTER_ALIASES[key]
    # Allow raw chips: roomfacility=17
    if "=" in name:
        return (name.strip(),)
    raise KeyError(
        f"Onbekende filter {name!r}. Gebruik --list-filters voor aliases/chips."
    )


def resolve_aliases(names: Iterable[str]) -> list[str]:
    chips: list[str] = []
    seen: set[str] = set()
    for name in names:
        for chip in resolve_alias(name):
            if chip not in seen:
                seen.add(chip)
                chips.append(chip)
    return chips


def star_chips(stars: Iterable[int]) -> list[str]:
    chips = []
    for star in stars:
        if star < 1 or star > 5:
            raise ValueError(f"Sterren moeten 1–5 zijn, kreeg {star}")
        chips.append(f"class={star}")
    return chips


def property_type_chips(types: Iterable[str]) -> list[str]:
    chips = []
    for raw in types:
        key = raw.strip().lower().replace(" ", "_").replace("-", "_")
        if key in PROPERTY_TYPES:
            chips.append(PROPERTY_TYPES[key])
        elif raw.startswith("ht_id="):
            chips.append(raw)
        else:
            raise KeyError(
                f"Onbekend accommodatietype {raw!r}. "
                f"Kies uit: {', '.join(sorted(PROPERTY_TYPES))}"
            )
    return chips


def city_chips(cities: Iterable[str]) -> list[str]:
    chips = []
    for raw in cities:
        key = raw.strip().lower().replace(" ", "-")
        if key in CITY_FILTERS:
            chips.append(CITY_FILTERS[key])
        elif raw.startswith("uf="):
            chips.append(raw)
        else:
            raise KeyError(
                f"Onbekende stad {raw!r}. "
                f"Kies uit: {', '.join(sorted(CITY_FILTERS))} of raw uf=..."
            )
    return chips


def format_filter_help() -> str:
    """Human-readable list of aliases and catalog chips."""
    lines = ["Named aliases:"]
    for name, chips in sorted(FILTER_ALIASES.items()):
        lines.append(f"  {name:<22} → {', '.join(chips)}")
    lines.append("")
    lines.append("Property types (--property-type): " + ", ".join(sorted(PROPERTY_TYPES)))
    lines.append("Cities (--city): " + ", ".join(sorted(CITY_FILTERS)))
    lines.append("")
    lines.append(f"Capla catalog chips ({len(load_filter_catalog())}):")
    for item in load_filter_catalog():
        lines.append(f"  {item['chip']:<40} {item.get('label') or ''}")
    return "\n".join(lines)
