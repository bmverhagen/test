from pathlib import Path

from booking_scraper.parser import parse_result_count, parse_search_results

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


def test_parse_result_count():
    assert parse_result_count("Zwarte Woud: 25 accommodaties gevonden") == 25
    assert parse_result_count("312 properties found") == 312
    assert parse_result_count(None) is None


def test_ohne_balkon_flagged_false():
    html = FIXTURE.read_text(encoding="utf-8")
    properties, _ = parse_search_results(html)
    panorama = next(p for p in properties if "Panorama" in p.name)
    assert panorama.room_mentions_balcony is False
    # Prefer visible "Huidige prijs" over sr_pri_blocks cents in the URL.
    assert panorama.price_total == 400.0
