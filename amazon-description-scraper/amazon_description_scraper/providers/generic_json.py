"""Generic JSON product API adapter.

Point `--endpoint-url` at any GET endpoint that returns JSON. Placeholders:

  {asin}   — product ASIN
  {domain} — marketplace domain (nl, com, de, ...)
  {host}   — marketplace host (www.amazon.nl)

Default JSON field mapping (override with --json-map):

  asin, title, brand, description, feature_bullets, aplus_text, url

Example Rainforest-compatible call via generic provider:

  --provider generic_json \\
  --endpoint-url 'https://api.rainforestapi.com/request?api_key=KEY&type=product&amazon_domain=amazon.{domain}&asin={asin}' \\
  --json-map 'title=product.title,description=product.description,feature_bullets=product.feature_bullets,brand=product.brand,url=product.link'
"""

from __future__ import annotations

from typing import Any

from ..fetcher import Fetcher
from ..models import Marketplace, ProductDescription, ProviderName
from .base import Provider

DEFAULT_MAP = {
    "title": "title",
    "brand": "brand",
    "description": "description",
    "feature_bullets": "feature_bullets",
    "aplus_text": "aplus_text",
    "url": "url",
}


def parse_json_map(raw: str | None) -> dict[str, str]:
    mapping = dict(DEFAULT_MAP)
    if not raw:
        return mapping
    for part in raw.split(","):
        part = part.strip()
        if not part or "=" not in part:
            continue
        key, path = part.split("=", 1)
        mapping[key.strip()] = path.strip()
    return mapping


def dig(data: Any, path: str) -> Any:
    cur: Any = data
    for part in path.split("."):
        if cur is None:
            return None
        if isinstance(cur, dict):
            cur = cur.get(part)
        elif isinstance(cur, list) and part.isdigit():
            idx = int(part)
            cur = cur[idx] if idx < len(cur) else None
        else:
            return None
    return cur


class GenericJsonProvider(Provider):
    name = ProviderName.GENERIC_JSON.value

    def __init__(
        self,
        endpoint_url: str,
        json_map: dict[str, str] | None = None,
        api_key: str | None = None,
        fetcher: Fetcher | None = None,
    ) -> None:
        if not endpoint_url:
            raise ValueError("generic_json provider requires --endpoint-url")
        self.endpoint_url = endpoint_url
        self.json_map = json_map or dict(DEFAULT_MAP)
        self.api_key = api_key
        self.fetcher = fetcher or Fetcher()

    def fetch(self, asin: str, marketplace: Marketplace) -> ProductDescription:
        url = self.endpoint_url.format(
            asin=asin,
            domain=marketplace.domain,
            host=marketplace.host,
            api_key=self.api_key or "",
        )
        headers = {}
        if self.api_key and "{api_key}" not in self.endpoint_url:
            headers["Authorization"] = f"Bearer {self.api_key}"
        data = self.fetcher.fetch_json(url, headers=headers or None)
        return self._parse(data, asin=asin, marketplace=marketplace)

    def _parse(
        self, data: Any, *, asin: str, marketplace: Marketplace
    ) -> ProductDescription:
        def get(field: str) -> Any:
            path = self.json_map.get(field)
            return dig(data, path) if path else None

        bullets = get("feature_bullets") or []
        if isinstance(bullets, str):
            bullets = [b.strip() for b in bullets.split("\n") if b.strip()]
        elif not isinstance(bullets, list):
            bullets = []

        return ProductDescription(
            asin=asin,
            marketplace=marketplace.domain,
            url=get("url") or marketplace.product_url(asin),
            title=get("title"),
            brand=get("brand"),
            feature_bullets=[str(b).strip() for b in bullets if str(b).strip()],
            description=get("description"),
            aplus_text=get("aplus_text"),
            provider=self.name,
        )
