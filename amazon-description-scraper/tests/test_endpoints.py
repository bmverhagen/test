from amazon_description_scraper.endpoints import (
    KEEPA_DOMAIN_CODES,
    aod_ajax_url,
    completion_url,
    mobile_aw_url,
    paapi_host,
    product_html_url,
    twister_ajaxv2_url,
    twister_dimension_url,
)
from amazon_description_scraper.models import resolve_marketplace


def test_endpoint_builders():
    mp = resolve_marketplace("nl")
    assert product_html_url(mp, "B0B4WQXL21").endswith("/dp/B0B4WQXL21")
    assert "aodAjaxMain" in aod_ajax_url(mp, "B0B4WQXL21")
    assert "completion.amazon.nl" in completion_url(mp, "B0B4WQXL21")
    tw = twister_dimension_url(mp, "B0B4WQXL21")
    assert "twister/dimension" in tw and "asinList=B0B4WQXL21" in tw
    v2 = twister_ajaxv2_url(mp, "B0B4WQXL21")
    assert "twister/ajaxv2" in v2 and "asinList=B0B4WQXL21" in v2
    aw = mobile_aw_url(mp, "B0B4WQXL21")
    assert "/gp/aw/d/B0B4WQXL21" in aw
    assert paapi_host(mp) == "webservices.amazon.de"
    assert KEEPA_DOMAIN_CODES["nl"] == 13
