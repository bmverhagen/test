#!/usr/bin/env python3
"""
Bol.com voorraadchecker via de winkelwagenmethode.

Werking:
  1. Productpagina openen (Camoufox, tegen botbescherming)
  2. Product in de winkelwagen zetten
  3. Aantal via GraphQL verhogen naar 500
  4. Werkelijk beschikbare hoeveelheid uitlezen

Gebruik:
  python bol_voorraad.py https://www.bol.com/nl/nl/p/.../9300000123456789/
  python bol_voorraad.py 9300000123456789
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
import uuid
from dataclasses import asdict, dataclass
from typing import Any, Optional
from urllib.parse import parse_qs, unquote, urlparse

PRODUCT_ID_RE = re.compile(r"(?:/p/[^/]+/)?(\d{8,})/?")
DEFAULT_MAX_QUANTITY = 500
BASE_URL = "https://www.bol.com"

# Persisted GraphQL operation hashes from bol.com basket frontend.
GQL_CREATE_BASKET = "sha256:587bd5a0f944a4e357df5de83516531decad277bad12a62b526ba0026289a19e"
GQL_UPDATE_QTY = "sha256:5df627c26015f5cda417ddcd412378957176a5db7975e541126b76a67bbf1255"
GQL_BASKET_QUERY = "sha256:c11bc67b62925f011430e3e7f1b697476946a2e609fe4a7e660b1c918eeb7765"
GQL_REMOVE_ITEM = "sha256:5b9f05c3be3e4f607eedcdb5623410ea1c042032396d93d21fcf209a56f598a7"


@dataclass
class StockResult:
    product_id: str
    offer_uid: str
    available: Optional[int]
    requested: int
    capped_at_max: bool
    stock_adjusted: bool
    product_title: Optional[str] = None
    message: Optional[str] = None
    raw_basket: Optional[dict[str, Any]] = None

    def as_public_dict(self) -> dict[str, Any]:
        data = asdict(self)
        if data.get("raw_basket") is None:
            data.pop("raw_basket", None)
        return data


class BolBlockedError(RuntimeError):
    """Bol.com weigert of blokkeert de sessie."""


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


def extract_offer_uid(value: str, explicit: Optional[str]) -> Optional[str]:
    if explicit:
        return explicit
    parsed = urlparse(value)
    if not (parsed.scheme and parsed.netloc):
        return None
    query = parse_qs(parsed.query)
    for key in ("offerUid", "offeruid", "offerId"):
        if key in query and query[key]:
            return query[key][0]
    return None


def format_human(result: StockResult) -> str:
    lines = []
    if result.product_title:
        lines.append(f"Product   : {result.product_title}")
    lines.append(f"Product-id: {result.product_id}")
    lines.append(f"Offer-uid : {result.offer_uid}")
    if result.available is None:
        lines.append("Voorraad  : onbekend")
    else:
        suffix = ""
        if result.available >= result.requested and not result.stock_adjusted:
            suffix = f" (mogelijk >= {result.requested}; bol toont max. {result.requested})"
        elif result.stock_adjusted:
            suffix = " (aangepast door bol.com na limiet/voorraadcheck)"
        lines.append(f"Voorraad  : {result.available}{suffix}")
    lines.append(f"Opgevraagd : {result.requested}")
    if result.message:
        lines.append(f"Melding   : {result.message}")
    return "\n".join(lines)


class BolStockChecker:
    def __init__(
        self,
        *,
        max_quantity: int = DEFAULT_MAX_QUANTITY,
        country: str = "nl",
        headless: bool = True,
        warmup_retries: int = 5,
    ) -> None:
        self.max_quantity = max_quantity
        self.country = country.lower()
        self.headless = headless
        self.warmup_retries = warmup_retries

    def _product_url(self, product_id: str, source: str) -> str:
        parsed = urlparse(source)
        if parsed.scheme and parsed.netloc and "/p/" in parsed.path:
            return source
        return f"{BASE_URL}/{self.country}/nl/p/product/{product_id}/"

    def _page_ok(self, page: Any) -> bool:
        try:
            content = page.content()
            title = (page.title() or "").strip().lower()
            return len(content) >= 50000 and title not in {"bol", ""}
        except Exception:
            return False

    def _dismiss_consent(self, page: Any) -> None:
        try:
            page.evaluate(
                """() => {
                  document.querySelectorAll(
                    '[role="dialog"], .overlay, [class*="overlay"], [class*="consent"]'
                  ).forEach((el) => el.remove());
                  document.body.style.overflow = 'auto';
                }"""
            )
        except Exception:
            pass

    def _warmup(self, page: Any) -> None:
        candidates = [
            f"{BASE_URL}/{self.country}/nl/l/computers-tablets/20032/",
            f"{BASE_URL}/{self.country}/nl/l/speelgoed/12974/",
            f"{BASE_URL}/{self.country}/nl/s/?searchtext=lego",
        ]
        last_error = None
        for _ in range(self.warmup_retries):
            for url in candidates:
                try:
                    page.goto(url, wait_until="domcontentloaded", timeout=120000)
                    time.sleep(4)
                    if self._page_ok(page):
                        self._dismiss_consent(page)
                        return
                except Exception as exc:  # noqa: BLE001
                    last_error = exc
            time.sleep(1)
        raise BolBlockedError(
            "Kon geen bruikbare bol.com-sessie starten (botbescherming). "
            f"Laatste fout: {last_error}"
        )

    def _extract_offer_from_html(self, html: str, product_id: str) -> tuple[str, Optional[str]]:
        # Prefer add-to-cart links for this product.
        pattern = re.compile(
            rf'href="(/{self.country}/order/basket/addItems\.html[^"]*productId={product_id}[^"]*)"',
            re.I,
        )
        matches = pattern.findall(html)
        if not matches:
            matches = re.findall(
                rf'href="(/{self.country}/order/basket/addItems\.html[^"]+)"', html, flags=re.I
            )
        if not matches:
            raise RuntimeError(
                "Geen offerUid gevonden op de productpagina. "
                "Product is mogelijk niet (meer) bestelbaar."
            )
        add_url = unquote(matches[0].replace("&amp;", "&"))
        query = parse_qs(urlparse(add_url).query)
        offer_uid = (query.get("offerUid") or [None])[0]
        if not offer_uid:
            raise RuntimeError("addItems-link zonder offerUid gevonden")
        title_match = re.search(r"<title>(.*?)</title>", html, flags=re.I | re.S)
        title = None
        if title_match:
            title = re.sub(r"\s+", " ", title_match.group(1)).strip()
            title = re.sub(r"\s*\|\s*bol\s*$", "", title, flags=re.I)
        return offer_uid, title

    def check_stock(
        self,
        product: str,
        *,
        offer_uid: Optional[str] = None,
        cleanup: bool = True,
        include_raw: bool = False,
    ) -> StockResult:
        try:
            from camoufox.sync_api import Camoufox
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError(
                "Ontbrekende dependency: camoufox\n"
                "Installeer met: pip install -r requirements.txt && camoufox fetch"
            ) from exc

        product_id = extract_product_id(product)
        explicit_offer = extract_offer_uid(product, offer_uid)
        product_url = self._product_url(product_id, product)

        with Camoufox(headless=self.headless, os="windows", locale="nl-NL", humanize=True) as browser:
            page = browser.new_page()
            self._warmup(page)

            page.goto(product_url, wait_until="domcontentloaded", timeout=120000)
            time.sleep(4)
            if not self._page_ok(page):
                # Fallback: zoek product via search en open eerste match.
                page.goto(
                    f"{BASE_URL}/{self.country}/nl/s/?searchtext={product_id}",
                    wait_until="domcontentloaded",
                    timeout=120000,
                )
                time.sleep(4)
                html = page.content()
                href = re.search(
                    rf'href="(/{self.country}/nl/p/[^"/]+/{product_id}/)"', html
                )
                if not href:
                    raise BolBlockedError("Productpagina kon niet geladen worden.")
                page.goto(
                    BASE_URL + href.group(1),
                    wait_until="domcontentloaded",
                    timeout=120000,
                )
                time.sleep(4)
                if not self._page_ok(page):
                    raise BolBlockedError("Productpagina geblokkeerd door bol.com.")

            self._dismiss_consent(page)
            html = page.content()
            if explicit_offer:
                found_offer = explicit_offer
                title_match = re.search(r"<title>(.*?)</title>", html, flags=re.I | re.S)
                title = (
                    re.sub(r"\s*\|\s*bol\s*$", "", re.sub(r"\s+", " ", title_match.group(1)).strip(), flags=re.I)
                    if title_match
                    else None
                )
            else:
                found_offer, title = self._extract_offer_from_html(html, product_id)

            # Zorg dat basket frontend/cookies warm zijn.
            page.goto(
                f"{BASE_URL}/{self.country}/nl/basket/",
                wait_until="domcontentloaded",
                timeout=120000,
            )
            time.sleep(2)
            self._dismiss_consent(page)

            payload = {
                "productId": product_id,
                "offerUid": found_offer,
                "maxQuantity": self.max_quantity,
                "country": self.country,
                "hashes": {
                    "createBasket": GQL_CREATE_BASKET,
                    "updateQty": GQL_UPDATE_QTY,
                    "basketQuery": GQL_BASKET_QUERY,
                    "removeItem": GQL_REMOVE_ITEM,
                },
                "cleanup": cleanup,
            }

            raw = page.evaluate(
                """async (cfg) => {
                  const xsrfMatch = document.cookie.match(/(?:^|; )XSRF-TOKEN=([^;]+)/);
                  const xsrf = xsrfMatch ? decodeURIComponent(xsrfMatch[1]) : '';
                  const pageId = crypto.randomUUID();

                  const restHeaders = {
                    'Accept': 'application/json',
                    'Content-Type': 'application/json;charset=UTF-8',
                    'X-Requested-With': 'XMLHttpRequest',
                  };
                  if (xsrf) restHeaders['X-XSRF-TOKEN'] = xsrf;

                  const gql = async (hash, operationName, variables = {}) => {
                    const response = await fetch('/api/graphql', {
                      method: 'POST',
                      credentials: 'include',
                      headers: {
                        'accept': 'application/graphql-response+json, application/graphql+json, application/json, text/event-stream, multipart/mixed',
                        'content-type': 'application/json',
                        'x-xsrf-token': xsrf,
                        'bol-app-country': cfg.country.toUpperCase(),
                        'bol-client-app-name': 'basket-web-fe',
                        'bol-app-operation-name': operationName,
                        'bol-client-page-id': pageId,
                        'm2-page-id': pageId,
                      },
                      body: JSON.stringify({
                        operationName,
                        variables,
                        extensions: {
                          persistedQuery: { version: 1, sha256Hash: hash },
                        },
                      }),
                    });
                    const text = await response.text();
                    let json = null;
                    try { json = JSON.parse(text); } catch {}
                    return { status: response.status, json, text };
                  };

                  // Bestaande basket ophalen of aanmaken.
                  let basketId = null;
                  const basketQuery = await gql(cfg.hashes.basketQuery, 'Basket', {});
                  const baskets = basketQuery.json?.data?.me?.baskets;
                  if (Array.isArray(baskets) && baskets[0]?.id) basketId = baskets[0].id;
                  else if (baskets?.id) basketId = baskets.id;

                  if (!basketId) {
                    const created = await gql(cfg.hashes.createBasket, 'CreateBasket', {});
                    basketId = created.json?.data?.basket?.createBasketV2?.id;
                  }
                  if (!basketId) {
                    return { ok: false, error: 'Geen basketId van bol.com ontvangen', basketQuery };
                  }

                  // Leeg bestaande items best-effort.
                  let state = await (await fetch('/nl/rnwy/basket/state', {
                    credentials: 'include', headers: restHeaders,
                  })).json();
                  for (const row of (state.itemRows || [])) {
                    await gql(cfg.hashes.removeItem, 'RemoveItem', {
                      removeItemInput: { basketId, itemId: row.id },
                    });
                  }

                  // Product toevoegen via REST basket API.
                  const addResp = await fetch('/nl/rnwy/basket/v2/items', {
                    method: 'POST',
                    credentials: 'include',
                    headers: restHeaders,
                    body: JSON.stringify({
                      globalId: cfg.productId,
                      quantity: 1,
                      offerUid: cfg.offerUid,
                    }),
                  });
                  const addText = await addResp.text();
                  if (addResp.status >= 400) {
                    return { ok: false, error: `Toevoegen mislukt (${addResp.status}): ${addText}` };
                  }

                  state = await (await fetch('/nl/rnwy/basket/state', {
                    credentials: 'include', headers: restHeaders,
                  })).json();
                  const itemId = (state.itemRows || [])[0]?.id;
                  if (!itemId) {
                    return { ok: false, error: 'Geen itemId na toevoegen aan winkelwagen', addText, state };
                  }

                  // Aantal naar max verhogen via GraphQL.
                  const update = await gql(cfg.hashes.updateQty, 'UpdateItemQuantity', {
                    input: { basketId, itemId, quantity: cfg.maxQuantity },
                  });
                  if (update.status >= 400 || update.json?.errors) {
                    return {
                      ok: false,
                      error: `Aantal wijzigen mislukt: ${update.text}`,
                      itemId,
                      basketId,
                    };
                  }

                  state = await (await fetch('/nl/rnwy/basket/state', {
                    credentials: 'include', headers: restHeaders,
                  })).json();
                  const messages = await (await fetch('/nl/rnwy/basket/messages', {
                    credentials: 'include', headers: restHeaders,
                  })).json();

                  if (cfg.cleanup) {
                    await gql(cfg.hashes.removeItem, 'RemoveItem', {
                      removeItemInput: { basketId, itemId },
                    });
                  }

                  const row = (state.itemRows || [])[0] || {};
                  return {
                    ok: true,
                    basketId,
                    itemId,
                    available: row.quantity ?? null,
                    title: row.productTitle || null,
                    state,
                    messages,
                    update,
                  };
                }""",
                payload,
            )

        if not raw.get("ok"):
            raise RuntimeError(raw.get("error") or "Onbekende fout tijdens voorraadcheck")

        available = raw.get("available")
        messages = (raw.get("messages") or {}).get("messages") or []
        stock_adjusted = any(
            msg.get("messageKey")
            in {
                "ITEM_STOCK_NOT_ENOUGH",
                "ITEM_QUANTITY_LIMIT_REACHED",
                "ITEM_QUANTITY_LIMIT_REACHED_GPC",
                "RestrictedItemQuantityChanged",
            }
            for msg in messages
        )
        message = None
        for msg in messages:
            if msg.get("messageBody"):
                message = msg["messageBody"]
                break

        return StockResult(
            product_id=product_id,
            offer_uid=found_offer,
            available=int(available) if available is not None else None,
            requested=self.max_quantity,
            capped_at_max=bool(
                available is not None
                and int(available) >= self.max_quantity
                and not stock_adjusted
            ),
            stock_adjusted=stock_adjusted,
            product_title=raw.get("title") or title,
            message=message,
            raw_basket=raw.get("state") if include_raw else None,
        )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Bepaal bol.com-voorraad via de winkelwagenmethode (max. 500)."
    )
    parser.add_argument("product", help="Product-URL of product-id")
    parser.add_argument(
        "--offer-uid",
        default=None,
        help="Optionele offerUid (UUID) van een specifieke verkoper",
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
    parser.add_argument("--json", action="store_true", help="Output als JSON")
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
        "--headed",
        action="store_true",
        help="Toon browser venster (niet headless)",
    )
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        extract_product_id(args.product)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    checker = BolStockChecker(
        max_quantity=args.max_quantity,
        country=args.country,
        headless=not args.headed,
    )

    try:
        result = checker.check_stock(
            args.product,
            offer_uid=args.offer_uid,
            cleanup=not args.keep_in_cart,
            include_raw=args.include_raw,
        )
    except BolBlockedError as exc:
        print(str(exc), file=sys.stderr)
        return 3
    except Exception as exc:  # noqa: BLE001
        print(f"Fout: {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(result.as_public_dict(), ensure_ascii=False, indent=2))
    else:
        print(format_human(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
