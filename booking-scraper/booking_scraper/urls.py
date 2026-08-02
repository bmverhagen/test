"""Build Booking.com search URLs and filter chips."""

from __future__ import annotations

from urllib.parse import urlencode

from .models import SearchQuery

SEARCH_BASE = "https://www.booking.com/searchresults.nl.html"

# Observed Booking.com nflt filter codes (storefront UI → URL).
REVIEW_SCORE_FILTER = {
    9.0: "review_score=90",
    8.0: "review_score=80",
    7.0: "review_score=70",
    6.0: "review_score=60",
}
MEALPLAN_BREAKFAST = "mealplan=1"
POOL_FILTER = "popular_activities=2"
BALCONY_FILTER = "roomfacility=32"


def build_nflt(query: SearchQuery) -> str:
    """Compose the semicolon-delimited ``nflt`` filter string."""
    chips: list[str] = []

    score_key = max(
        (threshold for threshold in REVIEW_SCORE_FILTER if threshold <= query.min_review_score),
        default=None,
    )
    if score_key is not None:
        chips.append(REVIEW_SCORE_FILTER[score_key])
    if query.breakfast:
        chips.append(MEALPLAN_BREAKFAST)
    if query.swimming_pool:
        chips.append(POOL_FILTER)
    if query.balcony:
        chips.append(BALCONY_FILTER)

    # Booking's budget slider is per night. Cap roughly so the total stay
    # can stay under max_total_price; exact total is filtered client-side.
    if query.max_total_price is not None and query.nights > 0:
        per_night_cap = int(query.max_total_price / query.nights) + 1
        chips.append(f"price=0-{per_night_cap}-1")

    return ";".join(chips)


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
        "nflt": build_nflt(query),
    }
    if offset:
        params["offset"] = offset
    return f"{SEARCH_BASE}?{urlencode(params)}"
