"""Build Booking.com search URLs and filter chips."""

from __future__ import annotations

import re
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

from .filters import (
    REVIEW_SCORE_CHIPS,
    city_chips,
    property_type_chips,
    resolve_aliases,
    star_chips,
)
from .models import SearchQuery

SEARCH_BASE = "https://www.booking.com/searchresults.nl.html"
_HOTEL_PATH_RE = re.compile(
    r"^(/hotel/[a-z]{2}/[^/]+?)(?:\.[a-z]{2})?\.html$",
    re.I,
)


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


def _children_ages(query: SearchQuery) -> tuple[int, ...]:
    """Return child ages; fall back to repeating 0 when only a count is set."""
    if query.children_ages:
        return query.children_ages
    if query.children > 0:
        return tuple(0 for _ in range(query.children))
    return ()


def build_hotel_url(
    page_name: str,
    *,
    country_code: str = "de",
    lang: str = "nl",
) -> str:
    """Build a locale hotel URL (``/hotel/de/name.nl.html``)."""
    cc = (country_code or "de").lower()
    slug = page_name.strip().removesuffix(".html")
    # pageName never includes the language infix; strip if present.
    slug = re.sub(r"\.[a-z]{2}$", "", slug, flags=re.I)
    lang = (lang or "nl").lower()
    return f"https://www.booking.com/hotel/{cc}/{slug}.{lang}.html"


def localize_hotel_url(url: str, *, lang: str = "nl") -> str:
    """Ensure a hotel URL uses the ``.{lang}.html`` path Booking expects."""
    if not url:
        return url
    parts = urlparse(url)
    match = _HOTEL_PATH_RE.match(parts.path or "")
    if not match:
        return url
    lang = (lang or "nl").lower()
    path = f"{match.group(1)}.{lang}.html"
    return urlunparse(parts._replace(path=path))


def hotel_path_slug(url: str) -> str | None:
    """Return ``country/pageName`` slug from a hotel URL, if parseable."""
    if not url:
        return None
    parts = urlparse(url)
    match = _HOTEL_PATH_RE.match(parts.path or "")
    if not match:
        return None
    # group1 = /hotel/de/pageName
    return match.group(1).removeprefix("/hotel/").lower()


def stay_query_params(query: SearchQuery) -> list[tuple[str, str]]:
    """Canonical query params for a bookable hotel deep link."""
    ages = _children_ages(query)
    child_count = len(ages) if ages else query.children
    params: list[tuple[str, str]] = [
        ("checkin", query.checkin),
        ("checkout", query.checkout),
        ("group_adults", str(query.adults)),
        ("req_adults", str(query.adults)),
        ("no_rooms", str(query.rooms)),
        ("group_children", str(child_count)),
        ("req_children", str(child_count)),
        ("selected_currency", query.currency),
        ("lang", query.lang),
    ]
    for age in ages:
        params.append(("age", str(age)))
    return params


def build_stay_url(hotel_url: str, query: SearchQuery) -> str:
    """Hotel deep link with dates, occupancy and locale path."""
    if not hotel_url:
        return ""
    localized = localize_hotel_url(hotel_url, lang=query.lang)
    parts = urlparse(localized)
    # Keep affiliate bits from DOM hrefs when present; overwrite stay params.
    existing = parse_qs(parts.query, keep_blank_values=True)
    keep_keys = ("aid", "label", "sid", "dist")
    merged: list[tuple[str, str]] = []
    for key in keep_keys:
        for value in existing.get(key) or ():
            merged.append((key, value))
    # Drop stale age/occupancy from source URL, then apply query.
    merged.extend(stay_query_params(query))
    return urlunparse(parts._replace(query=urlencode(merged)))


def build_search_url(query: SearchQuery, *, offset: int = 0) -> str:
    """Return a Booking.com searchresults URL for ``query``."""
    ages = _children_ages(query)
    child_count = len(ages) if ages else query.children
    params: dict[str, str | int | list[int]] = {
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
        "group_children": child_count,
        "req_children": child_count,
        "selected_currency": query.currency,
        "lang": query.lang,
        "order": query.order,
    }
    if ages:
        params["age"] = list(ages)
    nflt = build_nflt(query)
    if nflt:
        params["nflt"] = nflt
    if offset:
        params["offset"] = offset
    return f"{SEARCH_BASE}?{urlencode(params, doseq=True)}"
