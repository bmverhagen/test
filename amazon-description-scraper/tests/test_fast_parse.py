from amazon_description_scraper.fast_parse import fast_parse_html


def test_fast_parse_extracts_title_and_bullets():
    html = """
    <html><body>
      <span id="productTitle">Turbo Brush Pro</span>
      <a id="bylineInfo">Merk: TurboCo</a>
      <div id="feature-bullets"><ul>
        <li><span class="a-list-item">Cleans deeply every day</span></li>
        <li><span class="a-list-item">Soft bristles for gums</span></li>
      </ul></div>
    </body></html>
    """
    product = fast_parse_html(
        html,
        asin="B000000001",
        marketplace="nl",
        url="https://www.amazon.nl/dp/B000000001",
        provider="turbo/twister",
    )
    assert product.title == "Turbo Brush Pro"
    assert product.brand == "TurboCo"
    assert len(product.feature_bullets) == 2
    assert product.provider == "turbo/twister"
