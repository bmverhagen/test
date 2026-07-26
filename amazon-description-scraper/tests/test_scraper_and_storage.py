import json
from pathlib import Path

from amazon_description_scraper.models import ProductDescription
from amazon_description_scraper.scraper import DescriptionScraper
from amazon_description_scraper.storage import write_csv, write_json


def test_fetch_many_preserves_order(monkeypatch):
    scraper = DescriptionScraper(marketplace="nl", provider="html", workers=4)

    def fake_fetch_one(asin: str) -> ProductDescription:
        return ProductDescription(
            asin=asin,
            marketplace="nl",
            url=f"https://www.amazon.nl/dp/{asin}",
            title=asin,
            feature_bullets=["x"],
            provider="html",
        )

    monkeypatch.setattr(scraper, "fetch_one", fake_fetch_one)
    asins = ["B000000001", "B000000002", "B000000003"]
    products = scraper.fetch_many(asins)
    assert [p.asin for p in products] == asins


def test_storage_roundtrip(tmp_path: Path):
    products = [
        ProductDescription(
            asin="B000000001",
            marketplace="nl",
            url="https://www.amazon.nl/dp/B000000001",
            title="Demo",
            feature_bullets=["a", "b"],
            description="desc",
            provider="html",
        )
    ]
    json_path = tmp_path / "out.json"
    csv_path = tmp_path / "out.csv"
    write_json(json_path, products, marketplace="nl", provider="html")
    write_csv(csv_path, products)
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert payload["total"] == 1
    assert payload["products"][0]["best_description"]
    csv_text = csv_path.read_text(encoding="utf-8")
    assert "B000000001" in csv_text
    assert "a | b" in csv_text
