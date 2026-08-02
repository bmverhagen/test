from pathlib import Path

from booking_scraper.capla import (
    GRAPHQL_ENDPOINT,
    extract_capla_context,
    extract_capla_store,
    parse_capla_html,
    parse_capla_store,
)
from booking_scraper.parser import parse_search_results

CAPLA_HTML = Path(__file__).parent / "fixtures" / "capla_search_results.html"
DOM_FIXTURE = Path(__file__).parent / "fixtures" / "search_results.html"


def test_graphql_endpoint_constant():
    assert GRAPHQL_ENDPOINT.endswith("/dml/graphql")


def test_extract_capla_store_and_context():
    html = CAPLA_HTML.read_text(encoding="utf-8")
    store = extract_capla_store(html)
    assert store is not None
    assert "ROOT_QUERY" in store

    ctx = extract_capla_context(html)
    assert ctx is not None
    assert ctx["csrfToken"] == "test-csrf"


def test_parse_capla_properties():
    html = CAPLA_HTML.read_text(encoding="utf-8")
    parsed = parse_capla_html(html)
    assert parsed is not None
    properties, header = parsed
    assert header and "25" in header
    assert len(properties) == 2

    first = properties[0]
    assert first.name == "La Uffheimoise"
    assert first.price_total == 165.0
    assert first.price_per_night == 55.0
    assert first.review_score == 9.2
    assert first.review_count == 6
    assert first.breakfast_included is True
    assert first.location == "Uffheim"
    assert first.url.endswith("/hotel/fr/la-uffheimoise.nl.html")
    assert first.room_name == "Standaard Tweepersoonskamer met Ventilator"
    assert first.unit_id == 1654248501
    assert first.latitude == 47.648835
    assert first.longitude == 7.439321
    assert first.free_cancellation is True
    assert first.is_available is True
    assert first.free_cancellation_until is not None


def test_parse_search_results_prefers_capla():
    html = CAPLA_HTML.read_text(encoding="utf-8")
    properties, header = parse_search_results(html)
    assert any(p.name == "La Uffheimoise" and p.price_total == 165.0 for p in properties)
    # Prefer visible page header when present.
    assert header and ("Zwarte Woud" in header or "25" in header)


def test_fixture_without_capla_still_parses_dom():
    html = DOM_FIXTURE.read_text(encoding="utf-8")
    assert extract_capla_store(html) is None
    properties, header = parse_search_results(html)
    assert properties
    assert header and "Zwarte Woud" in header


def test_parse_capla_store_direct():
    import json

    store = json.loads(
        (Path(__file__).parent / "fixtures" / "capla_store_mini.json").read_text(
            encoding="utf-8"
        )
    )
    properties, _ = parse_capla_store(store)
    assert properties[0].name == "La Uffheimoise"
