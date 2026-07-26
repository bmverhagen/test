from pathlib import Path

from amazon_description_scraper.parser import extract_asin, parse_product_html

FIXTURE = Path(__file__).parent / "fixtures" / "product_page.html"


def test_extract_asin_from_url_and_bare():
    assert extract_asin("B0B4WQXL21") == "B0B4WQXL21"
    assert extract_asin("https://www.amazon.nl/dp/B0B4WQXL21") == "B0B4WQXL21"
    assert (
        extract_asin("https://www.amazon.nl/Oral-B/dp/B0B4WQXL21/ref=sr_1_1")
        == "B0B4WQXL21"
    )
    assert extract_asin("https://www.amazon.nl/gp/product/B0B4WQXL21") == "B0B4WQXL21"
    assert extract_asin("not-an-asin") is None


def test_parse_fixture_feature_bullets_and_title():
    html = FIXTURE.read_text(encoding="utf-8", errors="replace")
    product = parse_product_html(
        html,
        asin="B0B4WQXL21",
        marketplace="nl",
        url="https://www.amazon.nl/dp/B0B4WQXL21",
    )
    assert product.title and "Oral-B" in product.title
    assert len(product.feature_bullets) >= 3
    assert any("poet" in b.lower() or "reinig" in b.lower() for b in product.feature_bullets)
    assert product.best_description
    assert product.source_bytes and product.source_bytes > 1000


def test_brand_from_dutch_store_byline():
    html = '''
    <html><body>
      <span id="productTitle">Demo</span>
      <a id="bylineInfo">De Oral-B Store openen</a>
      <div id="feature-bullets"><ul><li><span class="a-list-item">Bullet one about cleaning</span></li></ul></div>
    </body></html>
    '''
    product = parse_product_html(
        html, asin="B000000001", marketplace="nl", url="https://www.amazon.nl/dp/B000000001"
    )
    assert product.brand == "Oral-B"
