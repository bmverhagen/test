from pathlib import Path

from booking_scraper.parser import parse_search_results

FIXTURE = Path(__file__).parent / "fixtures" / "search_results.html"


def test_parse_fixture_cards():
    html = FIXTURE.read_text(encoding="utf-8")
    properties, header = parse_search_results(html)

    assert header and "Zwarte Woud" in header
    assert len(properties) == 3

    first = properties[0]
    assert first.name == "La Uffheimoise"
    assert first.review_score == 9.2
    assert first.breakfast_included is True
    assert first.price_total == 165.0
    assert first.price_per_night == 55.0
    assert first.url.startswith("https://www.booking.com/hotel/")
    assert first.location == "Uffheim"


def test_ohne_balkon_flagged_false():
    html = FIXTURE.read_text(encoding="utf-8")
    properties, _ = parse_search_results(html)
    panorama = next(p for p in properties if "Panorama" in p.name)
    assert panorama.room_mentions_balcony is False
    assert panorama.price_total == 399.53
