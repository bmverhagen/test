"""Hotel-page Capla helpers: room description + amenity balcony detection."""

from __future__ import annotations

import logging
from dataclasses import dataclass, replace
from typing import Any

from .balcony import balcony_from_room, text_mentions_balcony
from .capla import CaplaStore, extract_capla_store
from .fetcher import FetchError, PlaywrightFetcher
from .models import PropertyResult

logger = logging.getLogger(__name__)


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


def _match_room(
    rooms: dict[int, RoomDetails], prop: PropertyResult
) -> RoomDetails | None:
    if prop.unit_id is not None and prop.unit_id in rooms:
        return rooms[prop.unit_id]
    target = (prop.room_name or "").strip().casefold()
    if not target:
        return None
    for room in rooms.values():
        if room.name.strip().casefold() == target:
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

        if prop.url not in cache:
            try:
                html = fetcher.fetch_hotel_html(prop.url)
                cache[prop.url] = parse_room_details_from_html(html)
                logger.info(
                    "Hotel Capla rooms for %s: %s",
                    prop.name,
                    len(cache[prop.url]),
                )
            except FetchError as exc:
                logger.warning("Hotel enrich failed for %s: %s", prop.name, exc)
                cache[prop.url] = {}

        enriched.append(enrich_property_balcony(prop, cache[prop.url]))

    return enriched
