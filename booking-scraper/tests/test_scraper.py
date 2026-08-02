from pathlib import Path

from booking_scraper.models import SearchQuery
from booking_scraper.scraper import BookingScraper, dedupe_properties, matches_query
from booking_scraper.parser import parse_search_results

FIXTURE = Path(__file__).parent / "fixtures" / "search_results.html"


def test_scrape_html_filters_by_max_price():
    html = FIXTURE.read_text(encoding="utf-8")
    scraper = BookingScraper(SearchQuery(max_total_price=200))
    report = scraper.scrape_html(html)

    assert report.cards_seen == 3
    assert report.properties
    assert all(p.price_total is not None and p.price_total <= 200 for p in report.properties)
    assert report.properties[0].name == "La Uffheimoise"


def test_require_room_balcony_text():
    html = FIXTURE.read_text(encoding="utf-8")
    scraper = BookingScraper(
        SearchQuery(max_total_price=500),
        require_room_balcony_text=True,
    )
    report = scraper.scrape_html(html)
    assert all(p.room_mentions_balcony for p in report.properties)


def test_matches_query_rejects_missing_total():
    props, _ = parse_search_results(FIXTURE.read_text(encoding="utf-8"))
    prop = props[0]
    assert matches_query(prop, SearchQuery(max_total_price=500)) is True
    assert matches_query(prop, SearchQuery(max_total_price=100)) is False


def test_dedupe_properties_by_url():
    props, _ = parse_search_results(FIXTURE.read_text(encoding="utf-8"))
    duplicated = props + props
    assert len(dedupe_properties(duplicated)) == len(props)
