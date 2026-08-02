from booking_scraper.balcony import balcony_from_room, text_mentions_balcony
from booking_scraper.models import PropertyResult
from booking_scraper.rooms import (
    RoomDetails,
    enrich_property_balcony,
    hotel_url_with_dates,
    parse_room_details_from_store,
)


def test_text_mentions_balcony_and_negatives():
    assert text_mentions_balcony("Kamer met balkon")
    assert text_mentions_balcony("Suite with terrace")
    assert not text_mentions_balcony("Panorama Room ohne Balkon")
    assert not text_mentions_balcony("Budget Tweepersoonskamer")


def test_balcony_from_description():
    evidence = balcony_from_room(
        name="Budget Tweepersoonskamer",
        description="Deze kamer heeft een badkamer en een balkon met uitzicht.",
    )
    assert evidence.has_balcony is True
    assert evidence.source == "omschrijving"


def test_balcony_from_amenity_id():
    evidence = balcony_from_room(
        name="Budget Tweepersoonskamer",
        description="Comfortabele kamer.",
        amenities=[{"id": 17, "slug": "balcony", "name": "Balcony"}],
    )
    assert evidence.has_balcony is True
    assert evidence.source.startswith("kenmerk:")


def test_balcony_from_terrace_amenity():
    evidence = balcony_from_room(
        amenities=[{"id": 123, "slug": "terrace"}],
    )
    assert evidence.has_balcony is True


def test_enrich_property_uses_description_and_amenities():
    prop = PropertyResult(
        name="House of Happiness",
        url="https://www.booking.com/hotel/de/house-of-happiness.html",
        location="Schluchsee",
        review_score=9.1,
        review_count=10,
        room_name="Budget Tweepersoonskamer",
        price_per_night=134.0,
        price_total=404.0,
        currency="EUR",
        breakfast_included=True,
        room_mentions_balcony=False,
        unit_id=42,
    )
    rooms = {
        42: RoomDetails(
            unit_id=42,
            name="Budget Tweepersoonskamer",
            description="Lichte kamer met balkon.",
            amenities=({"id": 17, "slug": "balcony"},),
        )
    }
    enriched = enrich_property_balcony(prop, rooms)
    assert enriched.room_mentions_balcony is True
    assert enriched.balcony_source == "omschrijving"


def test_hotel_url_with_dates():
    url = hotel_url_with_dates(
        "https://www.booking.com/hotel/de/x.html",
        checkin="2026-08-26",
        checkout="2026-08-29",
        adults=2,
        children_ages=(2,),
    )
    assert "checkin=2026-08-26" in url
    assert "checkout=2026-08-29" in url
    assert "group_adults=2" in url
    assert "group_children=1" in url
    assert "age=2" in url


def test_parse_room_details_from_hotel_store():
    store = {
        "RoomTranslation:99": {
            "name": "Deluxe",
            "description": "Met terras aan de tuin.",
        },
        "RoomData:99": {
            "amenities": [{"__ref": "BaseFacility:123"}],
        },
        "BaseFacility:123": {"id": 123, "name": "Terrace", "slug": "terrace"},
    }
    rooms = parse_room_details_from_store(store)
    assert 99 in rooms
    assert "terras" in rooms[99].description.lower()
    assert rooms[99].amenities[0]["id"] == 123
