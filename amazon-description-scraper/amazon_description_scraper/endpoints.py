"""Known Amazon / third-party endpoints for product data.

## Live findings (amazon.nl, 2026-07) — endpoint hunt

Amazon has **no free unauthenticated light JSON API** that returns descriptions
without captcha/tokens. Probed 60+ URLs (ACP cards, experienceId ajax, AOD,
reviews widgets, smile/m./api hosts, oembed, print, cross-marketplace, ads
widgets, Keepa graph, …). Only heavy HTML / twister-family responses carry
description markers.

| Endpoint | Size | Description? | Bulk? | Notes |
|---|---|---|---|---|
| `/gp/twister/ajaxv2?asinList={ASIN}&isDimensionSlotsAjax=1&vs=1` | ~0.7 MB | **Yes** | 1 ASIN | Best free primary (≈ twister/dimension, often faster) |
| `/gp/twister/dimension?isDimensionSlotsAjax=1&asinList={ASIN}&vs=1` | ~0.7–0.9 MB | **Yes** | 1 ASIN | Same streaming JSON; multi-ASIN → 404 |
| `/gp/aw/d/{ASIN}` | ~0.65 MB | **Yes** | 1 ASIN | Mobile HTML; high hit-rate; good mid fallback |
| `/dp/{ASIN}` | ~0.7–1.4 MB | **Yes** | 1 ASIN | Desktop HTML final fallback |
| `/gp/product/{ASIN}`, `/gp/product/images/…` | ~dp size | Yes | 1 ASIN | Same heavy HTML family |
| FR/ES/IT twister | ~1 MB | Yes* | 1 ASIN | Works as cross-EU failover; language may differ |
| ACP / experienceId ajax / AOD / reviews widgets | 404/503 | No | — | Need signed tokens or dead |
| `completion.amazon.*` | tiny | No | — | Autocomplete only |
| `api.amazon.nl`, smile/m. hosts | 403 / DNS fail | No | — | |

### Turbo free chain (validated)

80 ASINs @ w16, no HTTP cache:

| Mode | OK | Captcha | Rate |
|---|---|---|---|
| ajaxv2 only | 59/80 | 0 | ~18.5/s |
| aw/d only | 80/80 | 0 | ~11.7/s |
| twister→dp | 79/80 | 0 | ~16.2/s |
| **ajaxv2→aw→dp** | **80/80** | **0** | ~14.9/s |

200 ASINs @ turbo w24: ajaxv2→aw→dp **199/200** vs legacy twister→dp **185/200**.

Note: Amazon 404 pages sometimes contain captcha marker strings — treat
`status != 200` as a miss, not a captcha.

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


def twister_ajaxv2_url(marketplace: Marketplace, asin: str) -> str:
    return (
        f"{marketplace.base_url}/gp/twister/ajaxv2"
        f"?isDimensionSlotsAjax=1&asinList={asin}&vs=1"
    )


def mobile_aw_url(marketplace: Marketplace, asin: str) -> str:
    return f"{marketplace.base_url}/gp/aw/d/{asin}?psc=1&th=1"


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
    base = marketplace.base_url
    candidates: list[tuple[str, str, str]] = [
        (
            "twister_ajaxv2",
            twister_ajaxv2_url(marketplace, asin),
            "Streaming JSON feature divs — best free primary (1 ASIN)",
        ),
        (
            "twister_dimension",
            twister_dimension_url(marketplace, asin),
            "Streaming JSON feature divs — legacy twister path (1 ASIN)",
        ),
        (
            "aw_mobile",
            mobile_aw_url(marketplace, asin),
            "Mobile HTML — high hit-rate mid fallback (~0.65 MB)",
        ),
        ("dp_html", product_html_url(marketplace, asin), "Full DP HTML final fallback"),
        (
            "gp_product",
            f"{base}/gp/product/{asin}",
            "Alias of DP HTML family",
        ),
        ("aod_ajax", aod_ajax_url(marketplace, asin), "Offers only; not product description"),
        (
            "experience_desc",
            f"{base}/gp/product/ajax?asin={asin}&experienceId=productDescriptionSection",
            "Legacy description ajax — usually 404/503",
        ),
        (
            "acp_feature_bullets",
            f"{base}/acp/detailpage/GetFeatureBullets?asin={asin}",
            "ACP cards — need signed tokens → 404",
        ),
        ("twister_slots", twister_ajax_url(marketplace, asin), "Variant slots; not description"),
        ("completion", completion_url(marketplace, asin), "Autocomplete JSON; not description"),
        (
            "twister_multi_asin",
            twister_dimension_url(marketplace, f"{asin},B000000000"),
            "Multi-ASIN batch — expected 404 on amazon.nl",
        ),
        (
            "fr_twister",
            f"https://www.amazon.fr/gp/twister/dimension?isDimensionSlotsAjax=1&asinList={asin}&vs=1",
            "Cross-EU failover (FR language)",
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
