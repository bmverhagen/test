"""Amazon Product Advertising API 5.0 (GetItems) adapter.

Official JSON API — no HTML. Requires Amazon Associates credentials:

  PAAPI_ACCESS_KEY
  PAAPI_SECRET_KEY
  PAAPI_PARTNER_TAG

Docs: https://webservices.amazon.com/paapi5/documentation/
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
from datetime import datetime, timezone
from typing import Any

import requests

from ..endpoints import paapi_host
from ..models import Marketplace, ProductDescription, ProviderName
from .base import Provider

_SERVICE = "ProductAdvertisingAPI"
_TARGET = "com.amazon.paapi5.v1.ProductAdvertisingAPIv1.GetItems"
_RESOURCES = [
    "ItemInfo.Title",
    "ItemInfo.Features",
    "ItemInfo.ProductInfo",
    "ItemInfo.ByLineInfo",
    "ItemInfo.ContentInfo",
    "ItemInfo.TechnicalInfo",
    "ItemInfo.ManufactureInfo",
]


class PaapiProvider(Provider):
    name = ProviderName.PAAPI.value

    def __init__(
        self,
        access_key: str | None = None,
        secret_key: str | None = None,
        partner_tag: str | None = None,
        session: requests.Session | None = None,
    ) -> None:
        self.access_key = access_key or os.environ.get("PAAPI_ACCESS_KEY")
        self.secret_key = secret_key or os.environ.get("PAAPI_SECRET_KEY")
        self.partner_tag = partner_tag or os.environ.get("PAAPI_PARTNER_TAG")
        if not (self.access_key and self.secret_key and self.partner_tag):
            raise ValueError(
                "PA-API needs PAAPI_ACCESS_KEY, PAAPI_SECRET_KEY and PAAPI_PARTNER_TAG "
                "(or pass them explicitly)"
            )
        self._session = session or requests.Session()

    def fetch(self, asin: str, marketplace: Marketplace) -> ProductDescription:
        host = paapi_host(marketplace)
        path = "/paapi5/getitems"
        payload = {
            "ItemIds": [asin],
            "Resources": _RESOURCES,
            "PartnerTag": self.partner_tag,
            "PartnerType": "Associates",
            "Marketplace": marketplace.host.removeprefix("www."),
        }
        body = json.dumps(payload)
        headers = self._sign_headers(host=host, path=path, body=body)
        response = self._session.post(
            f"https://{host}{path}",
            data=body.encode("utf-8"),
            headers=headers,
            timeout=20,
        )
        if response.status_code != 200:
            return ProductDescription(
                asin=asin,
                marketplace=marketplace.domain,
                url=marketplace.product_url(asin),
                provider=self.name,
                error=f"PA-API HTTP {response.status_code}: {response.text[:300]}",
            )
        return self._parse(response.json(), asin=asin, marketplace=marketplace)

    def _parse(
        self, data: dict[str, Any], *, asin: str, marketplace: Marketplace
    ) -> ProductDescription:
        result_items = (data.get("ItemsResult") or {}).get("Items") or []
        if not result_items:
            errors = data.get("Errors") or (data.get("ItemsResult") or {}).get("Errors")
            return ProductDescription(
                asin=asin,
                marketplace=marketplace.domain,
                url=marketplace.product_url(asin),
                provider=self.name,
                error=f"PA-API returned no items: {errors}",
            )
        item = result_items[0]
        info = item.get("ItemInfo") or {}
        title = ((info.get("Title") or {}).get("DisplayValue"))
        features = (info.get("Features") or {}).get("DisplayValues") or []
        brand = ((info.get("ByLineInfo") or {}).get("Brand") or {}).get("DisplayValue")
        # PA-API has no long-form product description resource; features are the
        # closest official structured equivalent.
        return ProductDescription(
            asin=item.get("ASIN") or asin,
            marketplace=marketplace.domain,
            url=item.get("DetailPageURL") or marketplace.product_url(asin),
            title=title,
            brand=brand,
            feature_bullets=[str(f).strip() for f in features if str(f).strip()],
            description=None,
            provider=self.name,
        )

    def _sign_headers(self, *, host: str, path: str, body: str) -> dict[str, str]:
        """AWS Signature Version 4 for PA-API."""
        assert self.access_key and self.secret_key
        region = "us-east-1" if host.endswith(".com") else "eu-west-1"
        if host.endswith(".co.jp"):
            region = "us-west-2"

        now = datetime.now(timezone.utc)
        amz_date = now.strftime("%Y%m%dT%H%M%SZ")
        date_stamp = now.strftime("%Y%m%d")
        content_type = "application/json; charset=utf-8"
        payload_hash = hashlib.sha256(body.encode("utf-8")).hexdigest()

        canonical_headers = (
            f"content-encoding:amz-1.0\n"
            f"content-type:{content_type}\n"
            f"host:{host}\n"
            f"x-amz-date:{amz_date}\n"
            f"x-amz-target:{_TARGET}\n"
        )
        signed_headers = "content-encoding;content-type;host;x-amz-date;x-amz-target"
        canonical_request = "\n".join(
            [
                "POST",
                path,
                "",
                canonical_headers,
                signed_headers,
                payload_hash,
            ]
        )
        credential_scope = f"{date_stamp}/{region}/{_SERVICE}/aws4_request"
        string_to_sign = "\n".join(
            [
                "AWS4-HMAC-SHA256",
                amz_date,
                credential_scope,
                hashlib.sha256(canonical_request.encode("utf-8")).hexdigest(),
            ]
        )
        signing_key = _signing_key(self.secret_key, date_stamp, region, _SERVICE)
        signature = hmac.new(
            signing_key, string_to_sign.encode("utf-8"), hashlib.sha256
        ).hexdigest()
        authorization = (
            f"AWS4-HMAC-SHA256 Credential={self.access_key}/{credential_scope}, "
            f"SignedHeaders={signed_headers}, Signature={signature}"
        )
        return {
            "Content-Type": content_type,
            "Content-Encoding": "amz-1.0",
            "Host": host,
            "X-Amz-Date": amz_date,
            "X-Amz-Target": _TARGET,
            "Authorization": authorization,
            # unused but kept for debugging
            "X-Amz-Content-Sha256": payload_hash,
            "Content-Length": str(len(body.encode("utf-8"))),
            "User-Agent": "amazon-description-scraper/0.1",
        }


def _sign(key: bytes, msg: str) -> bytes:
    return hmac.new(key, msg.encode("utf-8"), hashlib.sha256).digest()


def _signing_key(secret_key: str, date_stamp: str, region: str, service: str) -> bytes:
    k_date = _sign(("AWS4" + secret_key).encode("utf-8"), date_stamp)
    k_region = _sign(k_date, region)
    k_service = _sign(k_region, service)
    return _sign(k_service, "aws4_request")
