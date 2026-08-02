"""Hotel-page Capla helpers: room description + amenity balcony detection."""

from __future__ import annotations

import logging
from dataclasses import dataclass, replace
from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

from .balcony import balcony_from_room, text_mentions_balcony
from .capla import CaplaStore, extract_capla_store
from .fetcher import FetchError, PlaywrightFetcher
from .models import PropertyResult

logger = logging.getLogger(__name__)


def hotel_url_with_dates(
    url: str, *, checkin: str | None = None, checkout: str | None = None
) -> str:
    """Ensure hotel URLs carry stay dates so Capla exposes matching rooms."""
    if not url or (not checkin and not checkout):
        return url
    parts = urlparse(url)
    query = parse_qs(parts.query, keep_blank_values=True)
    if checkin:
        query["checkin"] = [checkin]
    if checkout:
        query["checkout"] = [checkout]
    # flatten for urlencode
    flat = [(k, v) for k, values in query.items() for v in values]
    return urlunparse(parts._replace(query=urlencode(flat)))


@dataclass(frozen=True)
class RoomDetails:
    unit_id: int
    name: str
    description: str
    amenities: tuple[dict[str, Any], ...]


def parse_room_details_from_store(store: dict[str, Any]) -> dict[int, RoomDetails]:
    """Map unitId → RoomDetails from a hotel-page Capla Apollo store."""
    capla = CaplaStore(store)
    out: dict[int, RoomDetails] = {}

    for key, value in store.items():
        if not isinstance(key, str) or not key.startswith("RoomTranslation:"):
            continue
        try:
            unit_id = int(key.split(":", 1)[1])
        except ValueError:
            continue
        if not isinstance(value, dict):
            continue

        name = str(value.get("name") or "")
        description = str(value.get("description") or "")
        amenities: list[dict[str, Any]] = []

        room_data = store.get(f"RoomData:{unit_id}")
        if isinstance(room_data, dict):
            for ref in room_data.get("amenities") or []:
                facility = capla.resolve(ref)
                if not isinstance(facility, dict):
                    continue
                amenities.append(
                    {
                        "id": facility.get("id"),
                        "name": facility.get("name"),
                        "slug": facility.get("slug") or facility.get("name"),
                    }
                )

        out[unit_id] = RoomDetails(
            unit_id=unit_id,
            name=name,
            description=description,
            amenities=tuple(amenities),
        )
    return out


def parse_room_details_from_html(html: str) -> dict[int, RoomDetails]:
    store = extract_capla_store(html)
    if not store:
        return {}
    return parse_room_details_from_store(store)


def _norm_name(value: str | None) -> str:
    return " ".join((value or "").casefold().split())


def _match_room(
    rooms: dict[int, RoomDetails], prop: PropertyResult
) -> RoomDetails | None:
    if prop.unit_id is not None and prop.unit_id in rooms:
        return rooms[prop.unit_id]
    target = _norm_name(prop.room_name)
    if not target:
        return None
    for room in rooms.values():
        if _norm_name(room.name) == target:
            return room
    # Soft match only when the search name is contained in a longer hotel name
    # (e.g. "deluxe" ⊂ "deluxe heritage"), not the reverse (avoids
    # "deluxe kamer" matching "grand deluxe kamer").
    for room in rooms.values():
        name = _norm_name(room.name)
        if target and target in name and len(target) >= 8:
            return room
    return None


def enrich_property_balcony(
    prop: PropertyResult, rooms: dict[int, RoomDetails]
) -> PropertyResult:
    """Update balcony flags using hotel-page room description/amenities."""
    if prop.room_mentions_balcony and prop.balcony_source:
        return prop

    if text_mentions_balcony(prop.room_name):
        return replace(
            prop,
            room_mentions_balcony=True,
            balcony_source=prop.balcony_source or "kamernaam",
        )

    room = _match_room(rooms, prop)
    if room is None:
        return replace(
            prop,
            balcony_source=prop.balcony_source or "kamer-niet-gevonden",
        )

    evidence = balcony_from_room(
        name=room.name or prop.room_name,
        description=room.description,
        amenities=room.amenities,
    )
    return replace(
        prop,
        room_name=prop.room_name or room.name or None,
        room_mentions_balcony=evidence.has_balcony,
        balcony_source=evidence.source,
    )


def enrich_properties_with_hotel_pages(
    properties: list[PropertyResult],
    fetcher: PlaywrightFetcher,
    *,
    only_missing: bool = True,
    checkin: str | None = None,
    checkout: str | None = None,
) -> list[PropertyResult]:
    """Fetch hotel pages for properties lacking name-level balcony evidence."""
    cache: dict[str, dict[int, RoomDetails]] = {}
    enriched: list[PropertyResult] = []

    for prop in properties:
        if only_missing and prop.room_mentions_balcony:
            enriched.append(
                replace(prop, balcony_source=prop.balcony_source or "kamernaam")
            )
            continue
        if not prop.url:
            enriched.append(
                replace(prop, balcony_source=prop.balcony_source or "onbekend")
            )
            continue

        fetch_url = hotel_url_with_dates(
            prop.url, checkin=checkin, checkout=checkout
        )
        if fetch_url not in cache:
            try:
                html = fetcher.fetch_hotel_html(fetch_url)
                cache[fetch_url] = parse_room_details_from_html(html)
                logger.info(
                    "Hotel Capla rooms for %s: %s",
                    prop.name,
                    len(cache[fetch_url]),
                )
            except FetchError as exc:
                logger.warning("Hotel enrich failed for %s: %s", prop.name, exc)
                cache[fetch_url] = {}

        enriched.append(enrich_property_balcony(prop, cache[fetch_url]))

    return enriched
