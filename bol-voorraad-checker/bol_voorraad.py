#!/usr/bin/env python3
"""
Bol.com voorraadchecker via de winkelwagenmethode.

Werking:
  1. Product in de winkelwagen zetten (1 stuk)
  2. Aantal verhogen naar 500
  3. De werkelijk beschikbare hoeveelheid uit de basket-API lezen

Gebruik:
  python bol_voorraad.py https://www.bol.com/nl/nl/p/.../9300000123456789/
  python bol_voorraad.py 9300000123456789
  python bol_voorraad.py 9300000123456789 --offer-id 1234567890
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from dataclasses import asdict, dataclass
from typing import Any, Optional
from urllib.parse import parse_qs, urlparse

try:
    from curl_cffi import requests
except ImportError:  # pragma: no cover
    print(
        "Ontbrekende dependency: curl_cffi\n"
        "Installeer met: pip install -r requirements.txt",
        file=sys.stderr,
    )
    sys.exit(1)


BASE_URL = "https://www.bol.com"
DEFAULT_MAX_QUANTITY = 500
PRODUCT_ID_RE = re.compile(r"(?:/p/[^/]+/)?(\d{8,})/?")


@dataclass
class StockResult:
    product_id: str
    offer_id: int
    available: Optional[int]
    requested: int
    capped_at_max: bool
    quantity_limit_message: bool
    product_title: Optional[str] = None
    raw_basket: Optional[dict[str, Any]] = None

    def as_public_dict(self) -> dict[str, Any]:
        data = asdict(self)
        # Ruwe basket is optioneel en kan groot zijn.
        if data.get("raw_basket") is None:
            data.pop("raw_basket", None)
        return data


class BolBlockedError(RuntimeError):
    """Bol.com weigert de request (bot-bescherming / WAF)."""


class BolStockChecker:
    def __init__(
        self,
        *,
        max_quantity: int = DEFAULT_MAX_QUANTITY,
        timeout: float = 30.0,
        impersonate: str = "chrome131",
        delay_seconds: float = 0.4,
        country: str = "nl",
        proxy: Optional[str] = None,
    ) -> None:
        self.max_quantity = max_quantity
        self.timeout = timeout
        self.delay_seconds = delay_seconds
        self.country = country.lower()
        self.session = requests.Session(impersonate=impersonate)
        if proxy:
            self.session.proxies = {"http": proxy, "https": proxy}
        self.session.headers.update(
            {
                "Accept": "application/json, text/plain, */*",
                "Accept-Language": "nl-NL,nl;q=0.9,en;q=0.8",
                "Origin": BASE_URL,
                "Referer": f"{BASE_URL}/{self.country}/nl/",
            }
        )

    def _url(self, path: str) -> str:
        if not path.startswith("/"):
            path = "/" + path
        return f"{BASE_URL}{path}"

    def _xsrf_headers(self) -> dict[str, str]:
        token = self.session.cookies.get("XSRF-TOKEN")
        headers = {
            "Content-Type": "application/json",
            "X-Requested-With": "XMLHttpRequest",
        }
        if token:
            headers["X-XSRF-TOKEN"] = token
        return headers

    def _raise_if_blocked(self, response: Any, context: str) -> None:
        content_type = (response.headers.get("content-type") or "").lower()
        body_preview = (response.text or "")[:200].lower()
        blocked = response.status_code == 403 or (
            response.status_code == 200
            and "text/html" in content_type
            and ("access denied" in body_preview or "<title>bol</title>" in body_preview)
        )
        if blocked:
            raise BolBlockedError(
                f"Bol.com blokkeert {context} (HTTP {response.status_code}). "
                "Dit gebeurt vaak vanaf datacenter/VPN-IP's door Akamai-botbescherming. "
                "Probeer opnieuw vanaf een gewoon thuisnetwerk of met een residential proxy."
            )

    def bootstrap(self) -> None:
        """Haal sessiecookies op (XSRF, shopping session, e.d.)."""
        # Soft page die vaak wel doorlaat en cookies zet.
        response = self.session.get(
            self._url(f"/{self.country}/nl/m/"),
            headers={"Accept": "text/html,application/xhtml+xml"},
            timeout=self.timeout,
            allow_redirects=True,
        )
        if response.status_code >= 500:
            raise RuntimeError(f"Kon geen bol.com-sessie starten (HTTP {response.status_code})")

        # Extra homepage-poging; mag falen door WAF.
        try:
            self.session.get(
                self._url(f"/{self.country}/nl/"),
                headers={"Accept": "text/html,application/xhtml+xml"},
                timeout=self.timeout,
                allow_redirects=True,
            )
        except Exception:
            pass

    def add_to_cart(self, product_id: str, offer_id: int = 0, quantity: int = 1) -> str:
        payload = {
            "globalId": str(product_id),
            "quantity": int(quantity),
            "retailerOfferId": int(offer_id),
        }
        response = self.session.post(
            self._url(f"/{self.country}/rnwy/basket/v2/items"),
            headers=self._xsrf_headers(),
            json=payload,
            timeout=self.timeout,
        )
        self._raise_if_blocked(response, "toevoegen aan winkelwagen")

        if response.status_code == 500 or not (response.text or "").strip():
            raise RuntimeError(
                "Product kon niet in de winkelwagen gezet worden. "
                "Mogelijk niet (meer) leverbaar, of alleen via een andere offer-id."
            )
        if response.status_code >= 400:
            raise RuntimeError(
                f"Toevoegen mislukt (HTTP {response.status_code}): {response.text[:300]}"
            )

        cart_item_id = (response.text or "").strip().strip('"')
        if not cart_item_id:
            raise RuntimeError("Geen winkelwagen-item-id ontvangen van bol.com")
        return cart_item_id

    def update_quantity(self, cart_item_id: str, quantity: int) -> None:
        response = self.session.patch(
            self._url(f"/{self.country}/rnwy/basket/v2/items/{cart_item_id}"),
            headers=self._xsrf_headers(),
            json={"quantity": int(quantity)},
            timeout=self.timeout,
        )
        self._raise_if_blocked(response, "aantal wijzigen")

        if response.status_code == 400:
            raise RuntimeError(
                "Aantal kon niet gewijzigd worden (bijv. e-book of product zonder voorraadlimiet)."
            )
        if response.status_code >= 400:
            raise RuntimeError(
                f"Aantal wijzigen mislukt (HTTP {response.status_code}): {response.text[:300]}"
            )

    def get_basket_state(self) -> dict[str, Any]:
        response = self.session.get(
            self._url(f"/{self.country}/rnwy/basket/state"),
            headers=self._xsrf_headers(),
            timeout=self.timeout,
        )
        self._raise_if_blocked(response, "winkelwagen ophalen")
        if response.status_code >= 400:
            raise RuntimeError(
                f"Winkelwagen ophalen mislukt (HTTP {response.status_code}): {response.text[:300]}"
            )
        return response.json()

    def has_quantity_limit_message(self) -> bool:
        response = self.session.get(
            self._url(f"/{self.country}/rnwy/basket/messages"),
            headers=self._xsrf_headers(),
            timeout=self.timeout,
        )
        if response.status_code >= 400:
            return False
        try:
            body = response.json()
        except Exception:
            return False

        messages = body.get("messages") or []
        limit_keys = {
            "ITEM_QUANTITY_LIMIT_REACHED",
            "ITEM_QUANTITY_LIMIT_REACHED_GPC",
        }
        return any(msg.get("messageKey") in limit_keys for msg in messages)

    def remove_item(self, cart_item_id: str) -> None:
        response = self.session.delete(
            self._url(f"/{self.country}/rnwy/basket/v2/items/{cart_item_id}"),
            headers=self._xsrf_headers(),
            timeout=self.timeout,
        )
        # Best-effort cleanup; geen harde fout als verwijderen faalt.
        if response.status_code >= 400 and response.status_code != 404:
            return

    def check_stock(
        self,
        product_id: str,
        *,
        offer_id: int = 0,
        cleanup: bool = True,
        include_raw: bool = False,
    ) -> StockResult:
        self.bootstrap()
        time.sleep(self.delay_seconds)

        cart_item_id = self.add_to_cart(product_id, offer_id=offer_id, quantity=1)
        time.sleep(self.delay_seconds)

        self.update_quantity(cart_item_id, self.max_quantity)
        time.sleep(self.delay_seconds)

        basket = self.get_basket_state()
        rows = basket.get("itemRows") or basket.get("items") or []
        if not rows:
            raise RuntimeError("Winkelwagen is leeg na toevoegen; voorraad kon niet bepaald worden.")

        row = rows[0]
        available = row.get("quantity")
        title = None
        product = row.get("product") or {}
        if isinstance(product, dict):
            title = product.get("title") or product.get("name")
        title = title or row.get("title") or row.get("productTitle")

        limit_message = self.has_quantity_limit_message()
        capped = bool(
            available is not None
            and int(available) >= self.max_quantity
            and not limit_message
        )

        if cleanup:
            self.remove_item(cart_item_id)

        return StockResult(
            product_id=str(product_id),
            offer_id=int(offer_id),
            available=int(available) if available is not None else None,
            requested=self.max_quantity,
            capped_at_max=capped,
            quantity_limit_message=limit_message,
            product_title=title,
            raw_basket=basket if include_raw else None,
        )


def extract_product_id(value: str) -> str:
    value = value.strip()
    if value.isdigit():
        return value

    parsed = urlparse(value)
    if parsed.scheme and parsed.netloc:
        match = PRODUCT_ID_RE.search(parsed.path)
        if match:
            return match.group(1)
        raise ValueError(f"Geen product-id gevonden in URL: {value}")

    match = PRODUCT_ID_RE.search(value)
    if match:
        return match.group(1)
    raise ValueError(f"Ongeldige product-id of URL: {value}")


def extract_offer_id(value: str, explicit_offer_id: Optional[int]) -> int:
    if explicit_offer_id is not None:
        return int(explicit_offer_id)

    parsed = urlparse(value)
    if not (parsed.scheme and parsed.netloc):
        return 0

    query = parse_qs(parsed.query)
    for key in ("offerId", "offerid", "retailerOfferId"):
        if key in query and query[key]:
            try:
                return int(query[key][0])
            except ValueError:
                pass
    return 0


def format_human(result: StockResult) -> str:
    lines = []
    if result.product_title:
        lines.append(f"Product : {result.product_title}")
    lines.append(f"Product-id : {result.product_id}")
    if result.offer_id:
        lines.append(f"Offer-id  : {result.offer_id}")
    else:
        lines.append("Offer-id  : 0 (bol.com buy-box / standaard)")

    if result.available is None:
        lines.append("Voorraad  : onbekend")
    else:
        suffix = ""
        if result.available >= result.requested and not result.quantity_limit_message:
            suffix = f" (mogelijk >= {result.requested}; bol toont max. {result.requested})"
        elif result.quantity_limit_message:
            suffix = " (hoeveelheidslimiet-melding aanwezig)"
        lines.append(f"Voorraad  : {result.available}{suffix}")

    lines.append(f"Opgevraagd : {result.requested}")
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Bepaal bol.com-voorraad via de winkelwagenmethode (max. 500)."
    )
    parser.add_argument(
        "product",
        help="Product-URL of product-id (bijv. 9300000123456789)",
    )
    parser.add_argument(
        "--offer-id",
        type=int,
        default=None,
        help="Optionele retailerOfferId voor een specifieke verkoper (default: 0)",
    )
    parser.add_argument(
        "--max-quantity",
        type=int,
        default=DEFAULT_MAX_QUANTITY,
        help=f"Aantal om in de winkelwagen te zetten (default: {DEFAULT_MAX_QUANTITY})",
    )
    parser.add_argument(
        "--country",
        choices=("nl", "be"),
        default="nl",
        help="Landshop: nl of be (default: nl)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output als JSON",
    )
    parser.add_argument(
        "--include-raw",
        action="store_true",
        help="Neem ruwe basket-state op in JSON-output",
    )
    parser.add_argument(
        "--keep-in-cart",
        action="store_true",
        help="Laat het product in de winkelwagen staan na de check",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=0.4,
        help="Pauze tussen API-calls in seconden (default: 0.4)",
    )
    parser.add_argument(
        "--proxy",
        default=None,
        help="Optionele proxy, bijv. http://user:pass@host:port",
    )
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        product_id = extract_product_id(args.product)
        offer_id = extract_offer_id(args.product, args.offer_id)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    checker = BolStockChecker(
        max_quantity=args.max_quantity,
        delay_seconds=args.delay,
        country=args.country,
        proxy=args.proxy,
    )

    try:
        result = checker.check_stock(
            product_id,
            offer_id=offer_id,
            cleanup=not args.keep_in_cart,
            include_raw=args.include_raw,
        )
    except BolBlockedError as exc:
        print(str(exc), file=sys.stderr)
        return 3
    except Exception as exc:
        print(f"Fout: {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(result.as_public_dict(), ensure_ascii=False, indent=2))
    else:
        print(format_human(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
