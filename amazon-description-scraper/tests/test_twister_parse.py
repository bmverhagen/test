import json

from amazon_description_scraper.parser import parse_product_html
from amazon_description_scraper.twister_parse import (
    parse_twister_stream,
    stitch_feature_html,
)


def _stream(*features: dict) -> str:
    parts = [json.dumps({"FeatureName": "request-id-expose", "requestId": "x"})]
    for feature in features:
        parts.append(json.dumps(feature))
    return "\n&&&\n".join(parts)


def test_parse_and_stitch_twister_stream():
    raw = _stream(
        {
            "ASIN": "B000000001",
            "FeatureName": "title_feature_div",
            "Type": "JSON",
            "Value": {
                "content": {
                    "title_feature_div": {
                        "html": '<span id="productTitle">Demo Brush</span>'
                    }
                }
            },
        },
        {
            "ASIN": "B000000001",
            "FeatureName": "featurebullets_feature_div",
            "Type": "JSON",
            "Value": {
                "content": {
                    "featurebullets_feature_div": {
                        "html": (
                            '<div id="feature-bullets"><ul>'
                            '<li><span class="a-list-item">Deep cleaning bristles</span></li>'
                            '<li><span class="a-list-item">Soft on gums daily</span></li>'
                            "</ul></div>"
                        )
                    }
                }
            },
        },
        {
            "ASIN": "B000000001",
            "FeatureName": "productDescription_feature_div",
            "Type": "JSON",
            "Value": {
                "content": {
                    "productDescription_feature_div": {
                        "html": (
                            '<div id="productDescription">'
                            "<p>A longer product description for testing.</p></div>"
                        )
                    }
                }
            },
        },
    )
    features = parse_twister_stream(raw)
    assert "title_feature_div" in features
    html = stitch_feature_html(features, asin="B000000001")
    product = parse_product_html(
        html,
        asin="B000000001",
        marketplace="nl",
        url="https://www.amazon.nl/dp/B000000001",
        provider="twister",
    )
    assert product.title == "Demo Brush"
    assert len(product.feature_bullets) == 2
    assert product.description and "longer product description" in product.description
