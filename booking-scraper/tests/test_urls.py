from booking_scraper.models import SearchQuery
from booking_scraper.urls import build_nflt, build_search_url


def test_default_nflt_contains_required_filters():
    nflt = build_nflt(SearchQuery())
    assert "review_score=90" in nflt
    assert "mealplan=1" in nflt
    assert "popular_activities=2" in nflt
    assert "roomfacility=32" in nflt
    assert "price=0-167-1" in nflt  # 500 / 3 nights + 1


def test_search_url_contains_core_params():
    url = build_search_url(SearchQuery())
    assert "dest_id=1477" in url
    assert "dest_type=region" in url
    assert "checkin=2026-08-26" in url
    assert "checkout=2026-08-29" in url
    assert "selected_currency=EUR" in url
    assert "order=price" in url


def test_offset_appended():
    url = build_search_url(SearchQuery(), offset=25)
    assert "offset=25" in url
