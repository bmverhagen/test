"""Parse Booking.com Capla Apollo store (SSR backend payload).

Booking searchresults pages hydrate from an embedded Apollo cache in:

    <script type="application/json" data-capla-store-data>...</script>

That store is the same GraphQL ``searchQueries.search`` payload served by
``POST /dml/graphql`` — a direct backend view of the listings, without DOM
card scraping.
"""

from __future__ import annotations

import json
import re
from typing import Any

from bs4 import BeautifulSoup

from .models import PropertyResult
from .parser import _BALCONY_RE, _NO_BALCONY_RE

CAPLA_STORE_SELECTOR = 'script[data-capla-store-data]'
CAPLA_CONTEXT_SELECTOR = "script[data-capla-application-context]"
GRAPHQL_ENDPOINT = "https://www.booking.com/dml/graphql"


def extract_capla_store(html: str) -> dict[str, Any] | None:
    """Return the parsed Capla Apollo store, or ``None`` if absent."""
    soup = BeautifulSoup(html, "lxml")
    script = soup.select_one(CAPLA_STORE_SELECTOR)
    if not script or not script.string:
        return None
    try:
        data = json.loads(script.string)
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def extract_capla_context(html: str) -> dict[str, Any] | None:
    """Return Capla application context (csrfToken, affiliate, pageviewId...)."""
    soup = BeautifulSoup(html, "lxml")
    script = soup.select_one(CAPLA_CONTEXT_SELECTOR)
    if not script or not script.string:
        return None
    try:
        data = json.loads(script.string)
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


class CaplaStore:
    """Thin helper around Booking's normalized Apollo cache."""

    def __init__(self, store: dict[str, Any]) -> None:
        self.store = store

    def resolve(self, node: Any) -> Any:
        if isinstance(node, dict) and "__ref" in node:
            return self.store.get(node["__ref"])
        return node

    def search_node(self) -> dict[str, Any] | None:
        root = self.store.get("ROOT_QUERY") or {}
        queries = root.get("searchQueries")
        if not isinstance(queries, dict):
            return None
        for key, value in queries.items():
            if key.startswith("search(") and isinstance(value, dict):
                return value
        return None

    def result_total(self) -> int | None:
        search = self.search_node()
        if not search:
            return None
        pagination = self.resolve(search.get("pagination")) or {}
        total = pagination.get("nbResultsTotal")
        return int(total) if isinstance(total, int) else None


def _money(node: Any) -> tuple[float | None, str | None]:
    if not isinstance(node, dict):
        return None, None
    amount = node.get("amountUnformatted")
    currency = node.get("currency")
    if isinstance(amount, (int, float)):
        return round(float(amount), 2), currency if isinstance(currency, str) else None
    return None, None


def _text(node: Any) -> str | None:
    if isinstance(node, str):
        return node
    if isinstance(node, dict):
        for key in ("text", "translation", "name"):
            value = node.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
            if isinstance(value, dict):
                nested = _text(value)
                if nested:
                    return nested
    return None


def _room_mentions_balcony(room_name: str | None) -> bool:
    if not room_name:
        return False
    if _NO_BALCONY_RE.search(room_name):
        return False
    return bool(_BALCONY_RE.search(room_name))


def parse_capla_store(store: dict[str, Any]) -> tuple[list[PropertyResult], str | None]:
    """Parse properties from a Capla Apollo store dict."""
    capla = CaplaStore(store)
    search = capla.search_node()
    if not search:
        return [], None

    total = capla.result_total()
    header = f"{total} accommodaties gevonden" if total is not None else None
    properties: list[PropertyResult] = []

    for index, item_ref in enumerate(search.get("results") or [], start=1):
        item = capla.resolve(item_ref) or {}
        if not isinstance(item, dict):
            continue

        display = capla.resolve(item.get("displayName")) or {}
        name = _text(display)
        bpd = capla.resolve(item.get("basicPropertyData")) or {}
        if not name:
            name = bpd.get("pageName")
        if not name:
            continue

        loc = capla.resolve(item.get("location")) or {}
        location = None
        if isinstance(loc, dict):
            location = loc.get("displayLocation") or loc.get("popularFreeDistrictName")
        if not location:
            bpd_loc = capla.resolve(bpd.get("location")) or {}
            if isinstance(bpd_loc, dict):
                location = bpd_loc.get("city")

        reviews = capla.resolve(bpd.get("reviews")) or {}
        review_score = None
        review_count = None
        if isinstance(reviews, dict):
            raw_score = reviews.get("totalScore")
            if isinstance(raw_score, (int, float)):
                review_score = float(raw_score)
            raw_count = reviews.get("reviewsCount") or reviews.get("totalCount")
            if isinstance(raw_count, int):
                review_count = raw_count

        price_info = capla.resolve(item.get("priceDisplayInfoIrene")) or {}
        display_price = capla.resolve(price_info.get("displayPrice")) or {}
        stay = capla.resolve(display_price.get("amountPerStay")) or {}
        night = capla.resolve(price_info.get("averagePricePerNight")) or {}
        price_total, currency = _money(stay)
        price_per_night, night_currency = _money(night)
        currency = currency or night_currency or "EUR"

        meal = capla.resolve(item.get("mealPlanIncluded")) or {}
        meal_text = _text(meal) or ""
        meal_type = str(meal.get("mealPlanType") or "")
        breakfast = bool(
            re.search(r"ontbijt|breakfast", meal_text, re.I)
            or re.search(r"breakfast", meal_type, re.I)
        )

        units = capla.resolve(item.get("matchingUnitConfigurations")) or {}
        common = capla.resolve(units.get("commonConfiguration")) or {}
        room_name = _text(common) if isinstance(common, dict) else None

        page_name = bpd.get("pageName")
        country = None
        bpd_loc = capla.resolve(bpd.get("location")) or {}
        if isinstance(bpd_loc, dict):
            country = bpd_loc.get("countryCode")
        url = ""
        if isinstance(page_name, str) and page_name:
            cc = (country or "de").lower()
            url = f"https://www.booking.com/hotel/{cc}/{page_name}.html"

        properties.append(
            PropertyResult(
                name=name,
                url=url,
                location=location if isinstance(location, str) else None,
                review_score=review_score,
                review_count=review_count,
                room_name=room_name,
                price_per_night=price_per_night,
                price_total=price_total,
                currency=currency,
                breakfast_included=breakfast,
                room_mentions_balcony=_room_mentions_balcony(room_name),
                rank=index,
            )
        )

    return properties, header


def parse_capla_html(html: str) -> tuple[list[PropertyResult], str | None] | None:
    """Parse Capla store from HTML, or return ``None`` when store is missing."""
    store = extract_capla_store(html)
    if store is None:
        return None
    return parse_capla_store(store)
