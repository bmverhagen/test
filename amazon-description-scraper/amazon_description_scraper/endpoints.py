"""Known Amazon / third-party endpoints for product data.

Amazon does **not** expose a public, unauthenticated JSON endpoint that returns
full product descriptions. Probe results (amazon.nl, 2026):

| Endpoint | Size | Has description? |
|---|---|---|
| `/dp/{ASIN}` | ~1.2 MB HTML | Yes (feature bullets, A+, optional #productDescription) |
| `/gp/product/{ASIN}` | ~1.2 MB HTML | Same as `/dp` |
| `/gp/aw/d/{ASIN}` | ~1.2 MB HTML | Same (no longer a light mobile page) |
| `/gp/product/ajax/aodAjaxMain/?asin=` | ~35 KB HTML | No — seller offers only |
| `/gp/product/ajax/twisterDimensionSlotsDefault` | empty / variants | No |
| `completion.amazon.*/api/2017/suggestions` | tiny JSON | No — autocomplete only |
| `/gp/product/ajax?experienceId=productDescriptionSection` | 404 | Gone |
| Marketplace REST `/api/marketplaces/.../products/{ASIN}` | 403/404 | Auth required |

Plug-in JSON APIs that *do* return descriptions without you parsing HTML:

1. **Amazon Product Advertising API 5.0** (`paapi5`) — official; needs Associate
   credentials. ItemInfo.Features ≈ bullet points.
2. **Rainforest API** — `GET https://api.rainforestapi.com/request?type=product`
3. **Keepa API** — product object includes description / features when available
4. Generic scrape-API product endpoints (ScraperAPI, etc.) — same idea: ASIN in,
   JSON out.
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
    "productDescription",
    "featurebullets",
    '"description"',
    "aboutThisItem",
)


def product_html_url(marketplace: Marketplace, asin: str) -> str:
    return marketplace.product_url(asin)


def aod_ajax_url(marketplace: Marketplace, asin: str) -> str:
    return f"{marketplace.base_url}/gp/product/ajax/aodAjaxMain/?asin={asin}&pc=dp"


def twister_ajax_url(marketplace: Marketplace, asin: str) -> str:
    return (
        f"{marketplace.base_url}/gp/product/ajax/twisterDimensionSlotsDefault"
        f"?asin={asin}&Type=JSON"
    )


def completion_url(marketplace: Marketplace, asin: str) -> str:
    # completion host mirrors the storefront TLD.
    host = marketplace.host.replace("www.", "completion.")
    return f"https://{host}/api/2017/suggestions?limit=1&prefix={asin}&alias=aps"


def rainforest_url(asin: str, amazon_domain: str, api_key: str) -> str:
    return (
        "https://api.rainforestapi.com/request"
        f"?api_key={api_key}&type=product&amazon_domain=amazon.{amazon_domain}&asin={asin}"
    )


def keepa_url(asin: str, domain_code: int, api_key: str) -> str:
    # Keepa domain codes: 1=com, 2=co.uk, 3=de, 4=fr, 5=jp, 6=ca, 8=it, 9=es, 13=nl, ...
    return (
        f"https://api.keepa.com/product?key={api_key}&domain={domain_code}"
        f"&asin={asin}&stats=0"
    )


# Keepa domain id for marketplaces we care about.
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
    """PA-API 5 host for a marketplace (EU host covers NL/DE/FR/...)."""
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
        ("dp_html", product_html_url(marketplace, asin), "Full DP HTML — only reliable free source"),
        ("aod_ajax", aod_ajax_url(marketplace, asin), "Offers only; not product description"),
        ("twister_ajax", twister_ajax_url(marketplace, asin), "Variant map; not description"),
        ("completion", completion_url(marketplace, asin), "Autocomplete JSON; not description"),
        (
            "desc_ajax_legacy",
            f"{marketplace.base_url}/gp/product/ajax?asin={asin}&experienceId=productDescriptionSection",
            "Legacy description ajax — expected 404",
        ),
    ]

    results: list[EndpointProbe] = []
    for name, url, notes in candidates:
        try:
            # Soft probe: do not raise on non-200; we only care about shape/size.
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
