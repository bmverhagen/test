"""Parse Booking.com search-results HTML into structured properties."""

from __future__ import annotations

import re
from urllib.parse import parse_qs, urlparse, urlunparse

from bs4 import BeautifulSoup, Tag

from .models import PropertyResult

_PRICE_RE = re.compile(r"€\s*([\d.,]+)")
_SCORE_RE = re.compile(r"(\d+[.,]\d+)")
_COUNT_RE = re.compile(r"([\d.]+)\s*beoordelingen", re.I)
_LOCATION_RE = re.compile(
    r"(?:^|\n)([^\n]+?)\s*\n?\s*Toon op kaart",
    re.I,
)
_BALCONY_RE = re.compile(r"\b(balkon|balcony|terras|terrace)\b", re.I)
_NO_BALCONY_RE = re.compile(r"\b(ohne balkon|zonder balkon|no balcony|without balcony)\b", re.I)
_PRI_CENTS_RE = re.compile(r"sr_pri_blocks=[^&]*?_(\d+)(?:&|$)")
_RESULT_COUNT_RE = re.compile(
    r"([\d.\s]+)\s*(?:accommodaties|properties|stays|resultaten|results)\b",
    re.I,
)


def parse_result_count(header: str | None) -> int | None:
    """Extract the total result count from a search header title."""
    if not header:
        return None
    match = _RESULT_COUNT_RE.search(header.replace("\xa0", " "))
    if not match:
        return None
    digits = re.sub(r"\D", "", match.group(1))
    return int(digits) if digits else None


def _parse_euro(text: str | None) -> float | None:
    if not text:
        return None
    cleaned = text.replace("\xa0", " ").replace(".", "").replace(",", ".")
    try:
        return float(cleaned)
    except ValueError:
        return None


def _clean_url(href: str | None) -> str:
    if not href:
        return ""
    parsed = urlparse(href)
    return urlunparse((parsed.scheme, parsed.netloc, parsed.path, "", "", ""))


def _price_total_from_link(href: str | None) -> float | None:
    if not href:
        return None
    match = _PRI_CENTS_RE.search(href)
    if not match:
        # Fallback: last numeric segment after double underscore.
        qs = parse_qs(urlparse(href).query)
        blocks = qs.get("sr_pri_blocks", [""])[0]
        if "__" in blocks:
            cents = blocks.rsplit("__", 1)[-1]
            if cents.isdigit():
                return int(cents) / 100.0
        return None
    return int(match.group(1)) / 100.0


def _extract_prices(card_text: str, href: str | None) -> tuple[float | None, float | None]:
    amounts = [_parse_euro(m.group(1)) for m in _PRICE_RE.finditer(card_text)]
    amounts = [a for a in amounts if a is not None]

    per_night: float | None = None
    if re.search(r"per\s*nacht", card_text, re.I):
        night_chunk = re.split(r"Per\s*nacht", card_text, maxsplit=1, flags=re.I)[-1]
        night_match = _PRICE_RE.search(night_chunk)
        if night_match:
            per_night = _parse_euro(night_match.group(1))

    # Prefer the visible stay total Booking shows to guests.
    total: float | None = None
    for pattern in (
        r"Huidige prijs\s*€\s*([\d.,]+)",
        r"Prijs\s*€\s*([\d.,]+)",
        r"Current price\s*€\s*([\d.,]+)",
        r"Price\s*€\s*([\d.,]+)",
    ):
        price_match = re.search(pattern, card_text, re.I)
        if price_match:
            total = _parse_euro(price_match.group(1))
            break

    if total is None:
        total = _price_total_from_link(href)
    if total is None and amounts:
        # Nightly first, stay total later — take the max as stay total.
        total = max(amounts)

    if per_night is None and amounts:
        per_night = min(amounts)

    return per_night, total


def _extract_score(score_text: str | None) -> tuple[float | None, int | None]:
    if not score_text:
        return None, None
    score_match = _SCORE_RE.search(score_text)
    score = _parse_euro(score_match.group(1)) if score_match else None
    count_match = _COUNT_RE.search(score_text.replace("\xa0", " "))
    count: int | None = None
    if count_match:
        raw = count_match.group(1).replace(".", "")
        if raw.isdigit():
            count = int(raw)
    return score, count


def _extract_location(card_text: str, card: Tag | None = None) -> str | None:
    if card is not None:
        for anchor in card.select("a"):
            text = anchor.get_text(" ", strip=True)
            if re.search(r"toon op kaart|show on map", text, re.I):
                location = re.sub(
                    r"\s*(Toon op kaart|Show on map)\s*$",
                    "",
                    text,
                    flags=re.I,
                ).strip()
                if location:
                    return location

    match = _LOCATION_RE.search(card_text)
    if not match:
        return None
    location = match.group(1).strip()
    location = re.sub(r"^Opent in nieuw venster\s*", "", location).strip()
    if location.casefold() in {"opent in nieuw venster", "show on map"}:
        return None
    return location or None


def _room_mentions_balcony(room_name: str | None, card_text: str) -> bool:
    haystack = f"{room_name or ''}\n{card_text}"
    if _NO_BALCONY_RE.search(haystack):
        return False
    return bool(_BALCONY_RE.search(haystack))


def parse_search_results(html: str) -> tuple[list[PropertyResult], str | None]:
    """Parse Booking searchresults HTML.

    Prefers the Capla Apollo store (``data-capla-store-data``) — the same JSON
    tree as ``POST /dml/graphql`` — and falls back to DOM property cards.
    """
    from .capla import parse_capla_html

    capla = parse_capla_html(html)
    if capla is not None and capla[0]:
        properties, header = capla
        soup = BeautifulSoup(html, "lxml")
        header_el = soup.select_one('[data-testid="header-title"], h1')
        if header_el:
            header = header_el.get_text(" ", strip=True) or header
        return properties, header

    return parse_dom_cards(html)


def parse_dom_cards(html: str) -> tuple[list[PropertyResult], str | None]:
    """Parse visible ``property-card`` DOM nodes (fallback)."""
    soup = BeautifulSoup(html, "lxml")
    header_el = soup.select_one('[data-testid="header-title"], h1')
    header = header_el.get_text(" ", strip=True) if header_el else None

    properties: list[PropertyResult] = []
    for index, card in enumerate(soup.select('[data-testid="property-card"]'), start=1):
        title_el = card.select_one('[data-testid="title"]')
        name = title_el.get_text(" ", strip=True) if title_el else None
        if not name:
            continue

        link_el = card.select_one('a[data-testid="title-link"], a[href*="/hotel/"]')
        href = link_el.get("href") if link_el else None
        if href and href.startswith("/"):
            href = "https://www.booking.com" + href

        address_el = card.select_one('[data-testid="address"]')
        card_text = card.get_text("\n", strip=True)
        location = (
            address_el.get_text(" ", strip=True)
            if address_el
            else _extract_location(card_text, card)
        )

        score_el = card.select_one('[data-testid="review-score"]')
        score_text = score_el.get_text(" ", strip=True) if score_el else None
        review_score, review_count = _extract_score(score_text)

        room_el = card.select_one(
            '[data-testid="recommended-units"], [data-testid="recommended-unit"]'
        )
        room_name = None
        if room_el:
            room_name = room_el.get_text("\n", strip=True).split("\n", 1)[0].strip()

        per_night, total = _extract_prices(card_text, href)
        breakfast = bool(re.search(r"inclusief ontbijt|breakfast included", card_text, re.I))
        free_cancellation = bool(
            re.search(
                r"gratis annuleren|free cancellation|kostenloos annuleren",
                card_text,
                re.I,
            )
        )
        sold_out = bool(re.search(r"uitverkocht|sold out", card_text, re.I))

        properties.append(
            PropertyResult(
                name=name,
                url=_clean_url(href),
                location=location,
                review_score=review_score,
                review_count=review_count,
                room_name=room_name,
                price_per_night=per_night,
                price_total=total,
                currency="EUR",
                breakfast_included=breakfast,
                room_mentions_balcony=_room_mentions_balcony(room_name, card_text),
                rank=index,
                free_cancellation=free_cancellation,
                is_available=not sold_out and total is not None,
            )
        )

    return properties, header
