from amazon_description_scraper.models import resolve_marketplace
from amazon_description_scraper.providers.generic_json import (
    GenericJsonProvider,
    dig,
    parse_json_map,
)


def test_dig_and_json_map():
    data = {"product": {"title": "X", "feature_bullets": ["a", "b"]}}
    assert dig(data, "product.title") == "X"
    mapping = parse_json_map("title=product.title,feature_bullets=product.feature_bullets")
    assert mapping["title"] == "product.title"


def test_generic_provider_parse(monkeypatch):
    marketplace = resolve_marketplace("nl")
    provider = GenericJsonProvider(
        endpoint_url="https://example.test/{asin}",
        json_map=parse_json_map(
            "title=product.title,description=product.description,"
            "feature_bullets=product.feature_bullets,brand=product.brand"
        ),
    )

    def fake_fetch_json(url, headers=None):
        assert "B00TESTASIN" in url
        return {
            "product": {
                "title": "Test Product",
                "brand": "Acme",
                "description": "Long description here",
                "feature_bullets": ["One", "Two"],
            }
        }

    monkeypatch.setattr(provider.fetcher, "fetch_json", fake_fetch_json)
    product = provider.fetch("B00TESTASIN", marketplace)
    assert product.title == "Test Product"
    assert product.brand == "Acme"
    assert product.description == "Long description here"
    assert product.feature_bullets == ["One", "Two"]
    assert product.provider == "generic_json"
