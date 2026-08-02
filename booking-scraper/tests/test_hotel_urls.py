from booking_scraper.models import SearchQuery
from booking_scraper.urls import (
    build_hotel_url,
    build_stay_url,
    hotel_path_slug,
    localize_hotel_url,
)


def test_build_hotel_url_uses_lang_infix():
    url = build_hotel_url("anna", country_code="de", lang="nl")
    assert url == "https://www.booking.com/hotel/de/anna.nl.html"


def test_localize_hotel_url_adds_nl():
    assert (
        localize_hotel_url("https://www.booking.com/hotel/de/anna.html")
        == "https://www.booking.com/hotel/de/anna.nl.html"
    )
    assert (
        localize_hotel_url("https://www.booking.com/hotel/de/anna.nl.html")
        == "https://www.booking.com/hotel/de/anna.nl.html"
    )


def test_build_stay_url_has_occupancy_and_locale():
    url = build_stay_url(
        "https://www.booking.com/hotel/de/anna.html",
        SearchQuery(),
    )
    assert "/hotel/de/anna.nl.html?" in url
    assert "checkin=2026-08-26" in url
    assert "checkout=2026-08-29" in url
    assert "group_adults=2" in url
    assert "group_children=1" in url
    assert "age=2" in url
    assert "lang=nl" in url


def test_hotel_path_slug():
    assert hotel_path_slug("https://www.booking.com/hotel/de/anna.nl.html") == "de/anna"
    assert hotel_path_slug("https://www.booking.com/hotel/de/anna.html") == "de/anna"
