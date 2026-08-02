from io import StringIO

from booking_scraper.bookmarks import stay_url, write_bookmarks, write_bookmarks_markdown
from booking_scraper.models import PropertyResult, SearchQuery, SearchReport


def _report() -> SearchReport:
    prop = PropertyResult(
        name="House of Happiness",
        url="https://www.booking.com/hotel/de/house-of-happiness.html",
        location="Schluchsee",
        review_score=9.1,
        review_count=10,
        room_name="Budget",
        price_per_night=134.0,
        price_total=404.0,
        currency="EUR",
        breakfast_included=True,
        room_mentions_balcony=True,
        free_cancellation=True,
        free_cancellation_until="2026-08-24T22:00:00Z",
        is_available=True,
    )
    query = SearchQuery()
    return SearchReport(
        query=query,
        search_url="https://www.booking.com/searchresults.nl.html",
        properties=[prop],
        pages_scraped=1,
        cards_seen=1,
        scraped_at="2026-08-02T00:00:00+00:00",
        nflt="fc=2;oos=1",
    )


def test_stay_url_includes_dates():
    report = _report()
    url = stay_url(report.properties[0], report.query)
    assert "/hotel/de/house-of-happiness.nl.html?" in url
    assert "checkin=2026-08-26" in url
    assert "checkout=2026-08-29" in url
    assert "group_adults=2" in url
    assert "group_children=1" in url
    assert "age=2" in url
    assert "lang=nl" in url


def test_write_netscape_bookmarks():
    buf = StringIO()
    write_bookmarks(_report(), buf)
    html = buf.getvalue()
    assert "NETSCAPE-Bookmark-file-1" in html
    assert "House of Happiness" in html
    assert "checkin=2026-08-26" in html


def test_write_bookmarks_markdown():
    buf = StringIO()
    write_bookmarks_markdown(_report(), buf)
    md = buf.getvalue()
    assert "[House of Happiness]" in md
    assert "gratis annuleerbaar" in md
