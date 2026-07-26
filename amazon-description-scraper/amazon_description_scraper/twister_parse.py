"""Parse Amazon UI streaming-JSON from /gp/twister/dimension."""

from __future__ import annotations

import json
import re
from typing import Any

__all__ = ["extract_feature_html", "parse_twister_stream", "stitch_feature_html"]

# Feature fragments that carry description-related markup.
_DESC_FEATURES = (
    "title_feature_div",
    "bylineInfo_feature_div",
    "featurebullets_feature_div",
    "productDescription_feature_div",
    "productOverview_feature_div",
    "aplus_feature_div",
    "aplus3p_feature_div",
    "dpx-aplus-product-description_feature_div",
    "dpx-aplus-3p-product-description_feature_div",
    "bookDescription_feature_div",
    "importantInformation_feature_div",
)


def parse_twister_stream(raw: str) -> dict[str, Any]:
    """Split Amazon `&&&`-delimited streaming JSON into FeatureName -> Value."""
    features: dict[str, Any] = {}
    for part in raw.split("&&&"):
        part = part.strip()
        if not part:
            continue
        try:
            obj = json.loads(part)
        except json.JSONDecodeError:
            match = re.search(r"\{.*\}", part, re.S)
            if not match:
                continue
            try:
                obj = json.loads(match.group(0))
            except json.JSONDecodeError:
                continue
        if not isinstance(obj, dict):
            continue
        name = obj.get("FeatureName")
        if not name:
            continue
        features[str(name)] = obj.get("Value")
    return features


def _first_html(value: Any) -> str | None:
    stack: list[Any] = [value]
    while stack:
        cur = stack.pop()
        if isinstance(cur, str) and "<" in cur and ("</" in cur or "/>" in cur or "<div" in cur or "<span" in cur):
            return cur
        if isinstance(cur, dict):
            stack.extend(cur.values())
        elif isinstance(cur, list):
            stack.extend(cur)
    return None


def extract_feature_html(features: dict[str, Any]) -> dict[str, str]:
    """Return FeatureName -> HTML string for fragments that contain markup."""
    out: dict[str, str] = {}
    for name, value in features.items():
        html = _first_html(value)
        if html:
            out[name] = html
    return out


def stitch_feature_html(features: dict[str, Any], *, asin: str) -> str:
    """Build a minimal HTML document from the useful twister feature fragments."""
    html_map = extract_feature_html(features)
    chunks: list[str] = [
        "<!doctype html><html><head>",
        f"<meta name=\"description\" content=\"asin {asin}\"/>",
        "</head><body>",
    ]
    # Prefer known description features first; append any aplus* leftovers.
    ordered = [name for name in _DESC_FEATURES if name in html_map]
    for name, html in html_map.items():
        if name in ordered:
            continue
        if "aplus" in name.lower() or "description" in name.lower():
            ordered.append(name)
    for name in ordered:
        chunks.append(f"<!-- {name} -->")
        chunks.append(html_map[name])
    chunks.append("</body></html>")
    return "\n".join(chunks)
