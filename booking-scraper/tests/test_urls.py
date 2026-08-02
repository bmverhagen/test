from booking_scraper.models import SearchQuery
from booking_scraper.urls import build_nflt, build_nflt_chips, build_search_url


def test_default_nflt_uses_corrected_capla_codes():
    chips = build_nflt_chips(SearchQuery())
    assert "review_score=90" in chips
    assert "mealplan=1" in chips
    assert "hotelfacility=433" in chips  # zwembad
    assert "roomfacility=17" in chips  # balkon
    assert "fc=2" in chips  # gratis annuleren
    assert "oos=1" in chips  # alleen beschikbaar
    assert "popular_activities=2" not in chips  # oude foutieve pool-code
    assert "roomfacility=32" not in chips  # oude foutieve balkon-code
    assert "price=0-167-1" in chips


def test_extra_filters_and_stars_cities():
    query = SearchQuery(
        spa=True,
        sauna=True,
        free_cancellation=True,
        parking=True,
        stars=(3, 4),
        property_types=("hotels", "bnb"),
        cities=("freiburg",),
        extra_filters=("view", "wifi"),
        balcony_or_terrace=True,
        balcony=False,
    )
    chips = build_nflt_chips(query)
    assert "hotelfacility=54" in chips
    assert "popular_activities=10" in chips
    assert "fc=2" in chips
    assert "hotelfacility=2" in chips
    assert "class=3" in chips and "class=4" in chips
    assert "ht_id=204" in chips and "ht_id=208" in chips
    assert "uf=-1771505" in chips
    assert "roomfacility=81" in chips
    assert "hotelfacility=107" in chips
    assert "roomfacility=17" in chips and "roomfacility=123" in chips


def test_search_url_contains_core_params():
    url = build_search_url(SearchQuery())
    assert "dest_id=1477" in url
    assert "dest_type=region" in url
    assert "checkin=2026-08-26" in url
    assert "checkout=2026-08-29" in url
    assert "selected_currency=EUR" in url
    assert "order=price" in url
    assert "roomfacility%3D17" in url or "roomfacility=17" in url
    assert "group_adults=2" in url
    assert "group_children=1" in url
    assert "age=2" in url


def test_search_url_multiple_child_ages():
    url = build_search_url(SearchQuery(children=2, children_ages=(2, 5)))
    assert "group_children=2" in url
    assert url.count("age=") == 2
    assert "age=2" in url and "age=5" in url


def test_offset_appended():
    url = build_search_url(SearchQuery(), offset=25)
    assert "offset=25" in url


def test_raw_nflt_preserved():
    nflt = build_nflt(
        SearchQuery(
            raw_nflt=("oos=1",),
            swimming_pool=False,
            balcony=False,
            breakfast=False,
            free_cancellation=False,
            available_only=False,
            min_review_score=0,
            apply_price_chip=False,
        )
    )
    assert nflt == "oos=1"
