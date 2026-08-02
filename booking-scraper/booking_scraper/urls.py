"""Build Booking.com search URLs and filter chips."""

from __future__ import annotations

from urllib.parse import urlencode

from .filters import (
    REVIEW_SCORE_CHIPS,
    city_chips,
    property_type_chips,
    resolve_aliases,
    star_chips,
)
from .models import SearchQuery

SEARCH_BASE = "https://www.booking.com/searchresults.nl.html"


def build_nflt_chips(query: SearchQuery) -> list[str]:
    """Compose ordered unique ``nflt`` chips for ``query``."""
    chips: list[str] = []

    if query.raw_nflt:
        # Explicit override / extension path.
        chips.extend(chip.strip() for chip in query.raw_nflt if chip.strip())

    score_key = max(
        (threshold for threshold in REVIEW_SCORE_CHIPS if threshold <= query.min_review_score),
        default=None,
    )
    if score_key is not None and query.min_review_score > 0:
        chips.append(REVIEW_SCORE_CHIPS[score_key])

    named: list[str] = []
    if query.breakfast:
        named.append("breakfast")
    if query.good_breakfast:
        named.append("good_breakfast")
    if query.swimming_pool:
        named.append("pool")
    if query.balcony_or_terrace:
        named.append("balcony_or_terrace")
    else:
        if query.balcony:
            named.append("balcony")
        if query.terrace:
            named.append("terrace")
    if query.free_cancellation:
        named.append("free_cancellation")
    if query.available_only:
        named.append("available_only")
    if query.parking:
        named.append("parking")
    if query.spa:
        named.append("spa")
    if query.sauna:
        named.append("sauna")
    if query.pets_allowed:
        named.append("pets")

    chips.extend(resolve_aliases(named))
    chips.extend(resolve_aliases(query.extra_filters))
    chips.extend(star_chips(query.stars))
    chips.extend(property_type_chips(query.property_types))
    chips.extend(city_chips(query.cities))

    # Booking budget slider is per night. Cap roughly; exact total is client-side.
    if (
        query.apply_price_chip
        and query.max_total_price is not None
        and query.nights > 0
    ):
        per_night_cap = max(1, int(query.max_total_price / query.nights) + 1)
        chips.append(f"price=0-{per_night_cap}-1")

    # Deduplicate, preserve order.
    seen: set[str] = set()
    unique: list[str] = []
    for chip in chips:
        if chip and chip not in seen:
            seen.add(chip)
            unique.append(chip)
    return unique


def build_nflt(query: SearchQuery) -> str:
    """Compose the semicolon-delimited ``nflt`` filter string."""
    return ";".join(build_nflt_chips(query))


def build_search_url(query: SearchQuery, *, offset: int = 0) -> str:
    """Return a Booking.com searchresults URL for ``query``."""
    params: dict[str, str | int] = {
        "ss": query.destination,
        "ssne": query.destination,
        "ssne_untouched": query.destination,
        "dest_id": query.dest_id,
        "dest_type": query.dest_type,
        "checkin": query.checkin,
        "checkout": query.checkout,
        "group_adults": query.adults,
        "req_adults": query.adults,
        "no_rooms": query.rooms,
        "group_children": query.children,
        "req_children": query.children,
        "selected_currency": query.currency,
        "lang": query.lang,
        "order": query.order,
    }
    nflt = build_nflt(query)
    if nflt:
        params["nflt"] = nflt
    if offset:
        params["offset"] = offset
    return f"{SEARCH_BASE}?{urlencode(params)}"
