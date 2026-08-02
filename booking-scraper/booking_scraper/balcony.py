"""Shared balcony/terrace detection from room name, description and amenities."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .parser import _BALCONY_RE, _NO_BALCONY_RE

# Booking facility ids from Capla BaseFacility / roomfacility chips.
BALCONY_FACILITY_IDS = frozenset({17, 123})  # balkon, terras
BALCONY_FACILITY_SLUGS = frozenset(
    {
        "balcony",
        "terrace",
        "patio",
        "french balcony",
        "french-balcony",
        "balkon",
        "terras",
    }
)


@dataclass(frozen=True)
class BalconyEvidence:
    has_balcony: bool
    source: str  # kamernaam | omschrijving | kenmerk:<slug> | geen


def text_mentions_balcony(text: str | None) -> bool:
    if not text:
        return False
    if _NO_BALCONY_RE.search(text):
        return False
    return bool(_BALCONY_RE.search(text))


def balcony_from_room(
    *,
    name: str | None = None,
    description: str | None = None,
    amenities: list[dict[str, Any]] | tuple[dict[str, Any], ...] | None = None,
) -> BalconyEvidence:
    """Decide balcony presence from name, description and amenity list."""
    if text_mentions_balcony(name):
        return BalconyEvidence(True, "kamernaam")
    if text_mentions_balcony(description):
        return BalconyEvidence(True, "omschrijving")
    for amenity in amenities or ():
        aid = amenity.get("id")
        try:
            aid_int = int(aid) if aid is not None else None
        except (TypeError, ValueError):
            aid_int = None
        slug = str(amenity.get("slug") or amenity.get("name") or "").strip().lower()
        if aid_int in BALCONY_FACILITY_IDS or slug in BALCONY_FACILITY_SLUGS:
            return BalconyEvidence(True, f"kenmerk:{slug or aid_int}")
        if text_mentions_balcony(slug):
            return BalconyEvidence(True, f"kenmerk:{slug}")
    return BalconyEvidence(False, "geen")
