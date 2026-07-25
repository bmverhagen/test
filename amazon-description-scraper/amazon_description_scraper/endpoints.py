"""Known Amazon / third-party endpoints for product data.

## Live findings (amazon.nl, 2026-07)

Amazon has **no free unauthenticated batch JSON API** that returns descriptions
for 100 ASINs in one call. What works:

| Endpoint | Size | Description? | Bulk? | Notes |
|---|---|---|---|---|
| `/gp/twister/dimension?isDimensionSlotsAjax=1&asinList={ASIN}&vs=1` | ~0.7–0.9 MB streaming JSON | **Yes** (feature div HTML) | 1 ASIN only | Best free path. Multi-ASIN `asinList` → 404 |
| `/dp/{ASIN}` | ~0.7–1.4 MB HTML | **Yes** | 1 ASIN | Fallback when twister 404s |
| `/gp/product/ajax/aodAjaxMain/?asin=` | ~35 KB | No (offers) | 1 ASIN | |
| Twister multi-ASIN / POST batch | 404 | No | — | Does not work on NL |
| `completion.amazon.*/suggestions` | tiny JSON | No | — | Autocomplete only |
| Legacy `experienceId=productDescriptionSection` | 404 | No | — | Gone |

### Soft bulk strategy (validated)

100 ASINs, **no captcha**, **no HTTP cache** (`Cache-Control` + `_=<nonce>`):

1. Warm session on `https://www.amazon.nl/`
2. Per ASIN: try **twister** first, fall back to **`/dp`**
3. `workers=1`, delay ≈ 0.55s, retry on captcha
4. Result: **100/100 OK in ~196s** (74 twister / 26 dp)

`workers>=3` from a datacenter IP quickly triggers captchas/404s.

### Plug-in JSON APIs (true no-block at scale)

1. **PA-API 5.0** — official; max 10 ASINs / GetItems; features only
2. **Rainforest** — `type=product` (set cache bypass in their dashboard/API if needed)
3. **Keepa** — product object; tokens per request
4. **generic_json** — any GET URL with `{asin}` placeholders
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .fetcher import Fetcher
from .models import Marketplace


@dataclass(frozen=True)
class EndpointProbe:
    name: str
    url: str
    status_code: int | None
    bytes: int
    content_type: str | None
    has_description_markers: bool
    notes: str


_DESC_MARKERS = (
    "feature-bullets",
    "featurebullets_feature_div",
    "productDescription",
    "featurebullets",
    '"description"',
    "aboutThisItem",
)


def product_html_url(marketplace: Marketplace, asin: str) -> str:
    return marketplace.product_url(asin)


def twister_dimension_url(marketplace: Marketplace, asin: str) -> str:
    return (
        f"{marketplace.base_url}/gp/twister/dimension"
        f"?isDimensionSlotsAjax=1&asinList={asin}&vs=1"
    )


def aod_ajax_url(marketplace: Marketplace, asin: str) -> str:
    return f"{marketplace.base_url}/gp/product/ajax/aodAjaxMain/?asin={asin}&pc=dp"


def twister_ajax_url(marketplace: Marketplace, asin: str) -> str:
    return (
        f"{marketplace.base_url}/gp/product/ajax/twisterDimensionSlotsDefault"
        f"?asin={asin}&Type=JSON"
    )


def completion_url(marketplace: Marketplace, asin: str) -> str:
    host = marketplace.host.replace("www.", "completion.")
    return f"https://{host}/api/2017/suggestions?limit=1&prefix={asin}&alias=aps"


def rainforest_url(asin: str, amazon_domain: str, api_key: str) -> str:
    return (
        "https://api.rainforestapi.com/request"
        f"?api_key={api_key}&type=product&amazon_domain=amazon.{amazon_domain}&asin={asin}"
    )


def keepa_url(asin: str, domain_code: int, api_key: str) -> str:
    return (
        f"https://api.keepa.com/product?key={api_key}&domain={domain_code}"
        f"&asin={asin}&stats=0"
    )


KEEPA_DOMAIN_CODES: dict[str, int] = {
    "com": 1,
    "co.uk": 2,
    "de": 3,
    "fr": 4,
    "it": 8,
    "es": 9,
    "nl": 13,
}


def paapi_host(marketplace: Marketplace) -> str:
    if marketplace.domain in {"com", "ca", "com.mx", "com.br"}:
        return "webservices.amazon.com"
    if marketplace.domain in {"co.jp", "com.au"}:
        return "webservices.amazon.co.jp"
    return "webservices.amazon.de"


def probe_endpoints(
    marketplace: Marketplace,
    asin: str,
    fetcher: Fetcher | None = None,
) -> list[EndpointProbe]:
    """Hit known endpoints and report whether description markers appear."""
    client = fetcher or Fetcher(
        language=f"{marketplace.language},en;q=0.8",
        max_retries=1,
        backoff=0.8,
    )
    candidates: list[tuple[str, str, str]] = [
        (
            "twister_dimension",
            twister_dimension_url(marketplace, asin),
            "Streaming JSON feature divs — best free description path (1 ASIN)",
        ),
        ("dp_html", product_html_url(marketplace, asin), "Full DP HTML fallback"),
        ("aod_ajax", aod_ajax_url(marketplace, asin), "Offers only; not product description"),
        ("twister_slots", twister_ajax_url(marketplace, asin), "Variant slots; not description"),
        ("completion", completion_url(marketplace, asin), "Autocomplete JSON; not description"),
        (
            "twister_multi_asin",
            twister_dimension_url(marketplace, f"{asin},B000000000"),
            "Multi-ASIN batch — expected 404 on amazon.nl",
        ),
    ]

    results: list[EndpointProbe] = []
    for name, url, notes in candidates:
        try:
            response = client._session.get(
                url,
                headers=client._headers(),
                timeout=client.timeout,
            )
            body = response.text or ""
            results.append(
                EndpointProbe(
                    name=name,
                    url=url,
                    status_code=response.status_code,
                    bytes=len(response.content or b""),
                    content_type=response.headers.get("Content-Type"),
                    has_description_markers=any(m in body for m in _DESC_MARKERS),
                    notes=notes,
                )
            )
        except Exception as exc:  # noqa: BLE001 - probe should never crash
            results.append(
                EndpointProbe(
                    name=name,
                    url=url,
                    status_code=None,
                    bytes=0,
                    content_type=None,
                    has_description_markers=False,
                    notes=f"{notes} | error: {exc}",
                )
            )
    return results


def probe_to_dict(probe: EndpointProbe) -> dict[str, Any]:
    return {
        "name": probe.name,
        "url": probe.url,
        "status_code": probe.status_code,
        "bytes": probe.bytes,
        "content_type": probe.content_type,
        "has_description_markers": probe.has_description_markers,
        "notes": probe.notes,
    }
