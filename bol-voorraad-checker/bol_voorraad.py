#!/usr/bin/env python3
"""
Bol.com voorraadchecker via de winkelwagenmethode.

Gebruik:
  python bol_voorraad.py 9300000123456789
  python bol_voorraad.py --batch products.txt --out results.jsonl
  python bol_voorraad.py --collect 100 --batch-run --out results.jsonl
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable, Optional
from urllib.parse import parse_qs, unquote, urlparse

PRODUCT_ID_RE = re.compile(r"(?:/p/[^/]+/)?(\d{8,})/?")
PRODUCT_HREF_RE = re.compile(r"/nl/nl/p/[^\"/]+/(\d{10,})/")
OFFER_UID_RE = re.compile(
    r"offerUid[=:\\\"]+([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})",
    re.I,
)
DEFAULT_MAX_QUANTITY = 500
BASE_URL = "https://www.bol.com"

GQL_CREATE_BASKET = "sha256:587bd5a0f944a4e357df5de83516531decad277bad12a62b526ba0026289a19e"
GQL_UPDATE_QTY = "sha256:5df627c26015f5cda417ddcd412378957176a5db7975e541126b76a67bbf1255"
GQL_REMOVE_ITEM = "sha256:5b9f05c3be3e4f607eedcdb5623410ea1c042032396d93d21fcf209a56f598a7"

BLOCKED_RESOURCE_TYPES = {"image", "media", "font", "stylesheet"}
BLOCKED_URL_SNIPPETS = (
    "google-analytics",
    "googletagmanager",
    "facebook.net",
    "hotjar",
    "mopinion",
    "rudderstack",
    "doubleclick",
    "adservice",
    "sentry.io",
)

CART_JS = """
async (cfg) => {
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
        extensions: { persistedQuery: { version: 1, sha256Hash: hash } },
      }),
    });
    const text = await response.text();
    let json = null;
    try { json = JSON.parse(text); } catch {}
    return { status: response.status, json, text };
  };

  let basketId = cfg.basketId || null;
  if (!basketId) {
    const created = await gql(cfg.hashes.createBasket, 'CreateBasket', {});
    basketId = created.json?.data?.basket?.createBasketV2?.id;
    if (!basketId) {
      return { ok: false, error: 'Geen basketId van bol.com ontvangen', created };
    }
  }

  const readState = async () => {
    const resp = await fetch('/nl/rnwy/basket/state', {
      credentials: 'include', headers: restHeaders,
    });
    const text = await resp.text();
    try { return JSON.parse(text); } catch {
      return { itemRows: [], _raw: text.slice(0, 200), _status: resp.status };
    }
  };

  const clearBasket = async () => {
    const state = await readState();
    for (const row of (state.itemRows || [])) {
      // Probeer beide bekende variable-shapes; RemoveItem is niet altijd stabiel.
      await gql(cfg.hashes.removeItem, 'RemoveItem', {
        removeItemInput: { basketId, itemId: row.id },
      });
      await gql(cfg.hashes.removeItem, 'RemoveItem', {
        input: { basketId, itemId: row.id },
      });
    }
  };

  if (cfg.clearFirst) {
    await clearBasket();
  }

  const addOnce = async () => fetch('/nl/rnwy/basket/v2/items', {
    method: 'POST',
    credentials: 'include',
    headers: restHeaders,
    body: JSON.stringify({
      globalId: cfg.productId,
      quantity: 1,
      offerUid: cfg.offerUid,
    }),
  });

  let addResp = await addOnce();
  let addText = await addResp.text();
  if (addResp.status === 409 || addResp.status === 400) {
    // Oud item botst: leegmaken en opnieuw toevoegen.
    await clearBasket();
    addResp = await addOnce();
    addText = await addResp.text();
  }
  if (addResp.status >= 400) {
    return { ok: false, error: `Toevoegen mislukt (${addResp.status}): ${addText}`, basketId };
  }

  let itemId = null;
  try { itemId = JSON.parse(addText).itemId; } catch {}
  let state = await readState();
  if (!itemId) {
    itemId = (state.itemRows || [])[0]?.id;
  }
  // Als er meerdere rijen zijn, kies de gevraagde; anders fout.
  const matching = (state.itemRows || []).find(
    (row) => String(row.productId) === String(cfg.productId)
  );
  if (matching) {
    itemId = matching.id;
  } else {
    const stateProductId = (state.itemRows || [])[0]?.productId;
    if (stateProductId && String(stateProductId) !== String(cfg.productId)) {
      await clearBasket();
      addResp = await addOnce();
      addText = await addResp.text();
      if (addResp.status >= 400) {
        return {
          ok: false,
          error: `Winkelwagen bevat ander product (${stateProductId}) dan gevraagd (${cfg.productId})`,
          basketId,
        };
      }
      try { itemId = JSON.parse(addText).itemId; } catch { itemId = null; }
      state = await readState();
      const again = (state.itemRows || []).find(
        (row) => String(row.productId) === String(cfg.productId)
      );
      if (again) {
        itemId = again.id;
      } else {
        const still = (state.itemRows || [])[0]?.productId;
        return {
          ok: false,
          error: `Winkelwagen bevat ander product (${still}) dan gevraagd (${cfg.productId})`,
          basketId,
        };
      }
    }
  }
  if (!itemId) {
    return { ok: false, error: 'Geen itemId na toevoegen aan winkelwagen', addText, basketId };
  }

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

  const updatedBasket = update.json?.data?.basket?.updateItemQuantityV2;
  let available =
    updatedBasket?.items?.[0]?.quantity ??
    updatedBasket?.quantity ??
    null;
  let title = updatedBasket?.items?.[0]?.sellingOffer?.product?.title || null;
  let outState = updatedBasket || null;

  if (available == null) {
    outState = await (await fetch('/nl/rnwy/basket/state', {
      credentials: 'include', headers: restHeaders,
    })).json();
    available = (outState.itemRows || [])[0]?.quantity ?? null;
    title = (outState.itemRows || [])[0]?.productTitle || title;
  }

  if (available == null) {
    return { ok: false, error: 'Geen voorraadaantal ontvangen', update, state: outState, basketId };
  }

  if (cfg.cleanup) {
    await gql(cfg.hashes.removeItem, 'RemoveItem', {
      removeItemInput: { basketId, itemId },
    });
  }

  return {
    ok: true,
    basketId,
    itemId,
    available,
    title,
    stockAdjusted: Number(available) < Number(cfg.maxQuantity),
    state: outState,
  };
}
"""


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
    elapsed_seconds: Optional[float] = None
    error: Optional[str] = None
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
    if result.error:
        return (
            f"Product-id: {result.product_id}\n"
            f"Fout      : {result.error}\n"
            f"Duur      : {result.elapsed_seconds:.1f}s"
            if result.elapsed_seconds is not None
            else f"Product-id: {result.product_id}\nFout      : {result.error}"
        )
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
    if result.elapsed_seconds is not None:
        lines.append(f"Duur      : {result.elapsed_seconds:.1f}s")
    return "\n".join(lines)


def load_products(path: Path) -> list[str]:
    items: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        items.append(line)
    return items


class BolStockChecker:
    def __init__(
        self,
        *,
        max_quantity: int = DEFAULT_MAX_QUANTITY,
        country: str = "nl",
        headless: bool = True,
        block_resources: bool = True,
        delay_seconds: float = 0.15,
    ) -> None:
        self.max_quantity = max_quantity
        self.country = country.lower()
        self.headless = headless
        self.block_resources = block_resources
        self.delay_seconds = delay_seconds

    def _import_camoufox(self):
        try:
            from camoufox.sync_api import Camoufox
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError(
                "Ontbrekende dependency: camoufox\n"
                "Installeer met: pip install -r requirements.txt && camoufox fetch"
            ) from exc
        return Camoufox

    def _product_url(self, product_id: str, source: str) -> str:
        parsed = urlparse(source)
        if parsed.scheme and parsed.netloc and "/p/" in parsed.path:
            return source
        return f"{BASE_URL}/{self.country}/nl/p/product/{product_id}/"

    def _page_ok(self, page: Any) -> bool:
        try:
            content_len = len(page.content())
            title = (page.title() or "").strip().lower()
            return content_len >= 40000 and title not in {"bol", ""}
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

    def _setup_page(self, page: Any) -> None:
        if not self.block_resources:
            return

        def _route(route: Any) -> None:
            request = route.request
            url = request.url.lower()
            if request.resource_type in BLOCKED_RESOURCE_TYPES:
                return route.abort()
            if "media.s-bol.com" in url:
                return route.abort()
            if any(snippet in url for snippet in BLOCKED_URL_SNIPPETS):
                return route.abort()
            return route.continue_()

        page.route("**/*", _route)

    def _goto_ok(self, page: Any, url: str, attempts: int = 3) -> None:
        last_len = 0
        for _ in range(attempts):
            page.goto(url, wait_until="domcontentloaded", timeout=60000)
            last_len = len(page.content())
            if last_len < 20000:
                continue
            if self._page_ok(page):
                self._dismiss_consent(page)
                return
        raise BolBlockedError(
            f"Pagina geblokkeerd of onbruikbaar ({url}, {last_len} bytes)."
        )

    def _extract_offer_from_html(self, html: str, product_id: str) -> tuple[str, Optional[str]]:
        pattern = re.compile(
            rf'href="(/{self.country}/order/basket/addItems\.html[^"]*productId={product_id}[^"]*)"',
            re.I,
        )
        matches = pattern.findall(html)
        if matches:
            add_url = unquote(matches[0].replace("&amp;", "&"))
            query = parse_qs(urlparse(add_url).query)
            offer_uid = (query.get("offerUid") or [None])[0]
            if offer_uid:
                return offer_uid, self._title_from_html(html)

        found = OFFER_UID_RE.findall(html)
        if not found:
            raise RuntimeError(
                "Geen offerUid gevonden op de productpagina. "
                "Product is mogelijk niet (meer) bestelbaar."
            )
        return found[0], self._title_from_html(html)

    @staticmethod
    def _title_from_html(html: str) -> Optional[str]:
        title_match = re.search(r"<title>(.*?)</title>", html, flags=re.I | re.S)
        if not title_match:
            return None
        title = re.sub(r"\s+", " ", title_match.group(1)).strip()
        return re.sub(r"\s*\|\s*bol\s*$", "", title, flags=re.I)

    def _result_from_raw(
        self,
        *,
        product_id: str,
        found_offer: str,
        title: Optional[str],
        raw: dict[str, Any],
        started: float,
        include_raw: bool,
    ) -> StockResult:
        if not raw.get("ok"):
            return StockResult(
                product_id=product_id,
                offer_uid=found_offer,
                available=None,
                requested=self.max_quantity,
                capped_at_max=False,
                stock_adjusted=False,
                product_title=title,
                error=raw.get("error") or "Onbekende fout",
                elapsed_seconds=round(time.perf_counter() - started, 2),
            )

        available = raw.get("available")
        stock_adjusted = bool(raw.get("stockAdjusted"))
        if available is not None and int(available) < self.max_quantity:
            stock_adjusted = True

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
            message=(
                f"Bol.com leverde {available} i.p.v. {self.max_quantity} stuks."
                if stock_adjusted and available is not None
                else None
            ),
            elapsed_seconds=round(time.perf_counter() - started, 2),
            raw_basket=raw.get("state") if include_raw else None,
        )

    def _check_on_page(
        self,
        page: Any,
        product: str,
        *,
        offer_uid: Optional[str] = None,
        cleanup: bool = True,
        include_raw: bool = False,
        basket_id: Optional[str] = None,
    ) -> tuple[StockResult, Optional[str]]:
        started = time.perf_counter()
        product_id = extract_product_id(product)
        explicit_offer = extract_offer_uid(product, offer_uid)
        product_url = self._product_url(product_id, product)

        try:
            self._goto_ok(page, product_url, attempts=3)
            html = page.content()
            if explicit_offer:
                found_offer = explicit_offer
                title = self._title_from_html(html)
            else:
                found_offer, title = self._extract_offer_from_html(html, product_id)

            payload = {
                "productId": product_id,
                "offerUid": found_offer,
                "maxQuantity": self.max_quantity,
                "country": self.country,
                "basketId": basket_id,
                "hashes": {
                    "createBasket": GQL_CREATE_BASKET,
                    "updateQty": GQL_UPDATE_QTY,
                    "removeItem": GQL_REMOVE_ITEM,
                },
                "cleanup": cleanup,
                # Bij hergebruikte sessie eerst proberen leeg te maken.
                "clearFirst": bool(basket_id),
            }
            raw = page.evaluate(CART_JS, payload)
            result = self._result_from_raw(
                product_id=product_id,
                found_offer=found_offer,
                title=title,
                raw=raw,
                started=started,
                include_raw=include_raw,
            )
            return result, raw.get("basketId") or basket_id
        except Exception as exc:  # noqa: BLE001
            return (
                StockResult(
                    product_id=product_id,
                    offer_uid=explicit_offer or "",
                    available=None,
                    requested=self.max_quantity,
                    capped_at_max=False,
                    stock_adjusted=False,
                    error=str(exc),
                    elapsed_seconds=round(time.perf_counter() - started, 2),
                ),
                basket_id,
            )

    def check_stock(
        self,
        product: str,
        *,
        offer_uid: Optional[str] = None,
        cleanup: bool = True,
        include_raw: bool = False,
    ) -> StockResult:
        Camoufox = self._import_camoufox()
        with Camoufox(
            headless=self.headless,
            os="windows",
            locale="nl-NL",
            humanize=False,
        ) as browser:
            page = browser.new_page()
            self._setup_page(page)
            result, _ = self._check_on_page(
                page,
                product,
                offer_uid=offer_uid,
                cleanup=cleanup,
                include_raw=include_raw,
            )
        if result.error:
            raise RuntimeError(result.error)
        return result

    def collect_product_ids(self, page: Any, limit: int = 100) -> list[str]:
        seeds = [
            f"{BASE_URL}/{self.country}/nl/l/speelgoed/12974/",
            f"{BASE_URL}/{self.country}/nl/l/computers-tablets/20032/",
            f"{BASE_URL}/{self.country}/nl/l/tuin/14582/",
            f"{BASE_URL}/{self.country}/nl/l/huishouden-woonaccessoires/14035/",
            f"{BASE_URL}/{self.country}/nl/l/baby/11279/",
            f"{BASE_URL}/{self.country}/nl/l/sport-vrije-tijd/12382/",
            f"{BASE_URL}/{self.country}/nl/l/elektronica/20004/",
            f"{BASE_URL}/{self.country}/nl/s/?searchtext=lego",
            f"{BASE_URL}/{self.country}/nl/s/?searchtext=airpods",
            f"{BASE_URL}/{self.country}/nl/s/?searchtext=pannen",
            f"{BASE_URL}/{self.country}/nl/s/?searchtext=boormachine",
            f"{BASE_URL}/{self.country}/nl/s/?searchtext=yoga+mat",
        ]
        found: list[str] = []
        seen: set[str] = set()
        for seed in seeds:
            if len(found) >= limit:
                break
            for page_no in range(1, 6):
                if len(found) >= limit:
                    break
                url = seed
                if "searchtext=" in seed:
                    url = f"{seed}&page={page_no}" if page_no > 1 else seed
                else:
                    url = f"{seed}?page={page_no}" if page_no > 1 else seed
                try:
                    page.goto(url, wait_until="domcontentloaded", timeout=60000)
                except Exception:
                    continue
                if len(page.content()) < 20000:
                    # retry once
                    try:
                        page.goto(url, wait_until="domcontentloaded", timeout=60000)
                    except Exception:
                        continue
                if not self._page_ok(page):
                    continue
                self._dismiss_consent(page)
                ids = PRODUCT_HREF_RE.findall(page.content())
                for pid in ids:
                    if pid not in seen:
                        seen.add(pid)
                        found.append(pid)
                        if len(found) >= limit:
                            break
        return found[:limit]

    def check_batch(
        self,
        products: Iterable[str],
        *,
        cleanup: bool = True,
        include_raw: bool = False,
        out_path: Optional[Path] = None,
        progress: bool = True,
        refresh_every: int = 10,
        max_block_streak: int = 2,
    ) -> list[StockResult]:
        """Batch-check. Gebruikt een verse browser-context per product zodat de
        winkelwagen niet blijft hangen (RemoveItem is onbetrouwbaar)."""
        Camoufox = self._import_camoufox()
        products_list = list(products)
        results: list[StockResult] = []
        started_all = time.perf_counter()
        block_streak = 0

        out_file = None
        if out_path is not None:
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_file = out_path.open("w", encoding="utf-8")

        browser_cm = None
        browser = None

        def open_browser() -> tuple[Any, Any]:
            cm = Camoufox(
                headless=self.headless,
                os="windows",
                locale="nl-NL",
                humanize=False,
            )
            b = cm.__enter__()
            return cm, b

        def close_browser() -> None:
            nonlocal browser_cm, browser
            if browser_cm is not None:
                try:
                    browser_cm.__exit__(None, None, None)
                except Exception:
                    pass
            browser_cm = None
            browser = None

        def check_one(product: str) -> StockResult:
            assert browser is not None
            context = browser.new_context()
            page = context.new_page()
            self._setup_page(page)
            try:
                result, _ = self._check_on_page(
                    page,
                    product,
                    cleanup=cleanup,
                    include_raw=include_raw,
                    basket_id=None,
                )
                return result
            finally:
                try:
                    context.close()
                except Exception:
                    pass

        def is_blocked(result: StockResult) -> bool:
            if not result.error:
                return False
            err = result.error.lower()
            return (
                "geblokkeerd" in err
                or "403" in result.error
                or "xsrf" in err
                or "onbruikbaar" in err
            )

        try:
            browser_cm, browser = open_browser()

            for idx, product in enumerate(products_list, start=1):
                if idx > 1 and (idx - 1) % refresh_every == 0:
                    if progress:
                        print(f"Sessie-refresh na {idx - 1} producten...", flush=True)
                    close_browser()
                    time.sleep(2.5)
                    browser_cm, browser = open_browser()

                result = check_one(product)

                if is_blocked(result):
                    block_streak += 1
                    backoff = min(12.0, 2.0 * block_streak)
                    if progress:
                        print(
                            f"Blokkade ({block_streak}): backoff {backoff:.0f}s + retry",
                            flush=True,
                        )
                    time.sleep(backoff)
                    if block_streak >= max_block_streak:
                        close_browser()
                        time.sleep(2.0)
                        browser_cm, browser = open_browser()
                    result = check_one(product)
                    if is_blocked(result):
                        block_streak += 1
                    else:
                        block_streak = 0
                else:
                    block_streak = 0

                results.append(result)

                if out_file is not None:
                    out_file.write(
                        json.dumps(result.as_public_dict(), ensure_ascii=False) + "\n"
                    )
                    out_file.flush()

                if progress:
                    status = (
                        f"voorraad={result.available}"
                        if result.error is None
                        else f"FOUT={result.error[:80]}"
                    )
                    print(
                        f"[{idx}/{len(products_list)}] {result.product_id} "
                        f"{status} ({result.elapsed_seconds}s)",
                        flush=True,
                    )

                if self.delay_seconds > 0 and idx < len(products_list):
                    time.sleep(self.delay_seconds)
        finally:
            close_browser()
            if out_file is not None:
                out_file.close()

        if progress:
            ok = sum(1 for r in results if r.error is None and r.available is not None)
            elapsed = round(time.perf_counter() - started_all, 2)
            print(
                f"Klaar: {ok}/{len(results)} ok in {elapsed}s "
                f"(avg {elapsed / max(len(results), 1):.2f}s/product)",
                flush=True,
            )
        return results


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Bepaal bol.com-voorraad via de winkelwagenmethode (max. 500)."
    )
    parser.add_argument(
        "product",
        nargs="?",
        help="Product-URL of product-id (niet nodig bij --batch/--collect)",
    )
    parser.add_argument("--offer-uid", default=None, help="Optionele offerUid (UUID)")
    parser.add_argument(
        "--max-quantity",
        type=int,
        default=DEFAULT_MAX_QUANTITY,
        help=f"Aantal in winkelwagen (default: {DEFAULT_MAX_QUANTITY})",
    )
    parser.add_argument("--country", choices=("nl", "be"), default="nl")
    parser.add_argument("--json", action="store_true", help="Output als JSON")
    parser.add_argument("--include-raw", action="store_true")
    parser.add_argument("--keep-in-cart", action="store_true")
    parser.add_argument("--headed", action="store_true")
    parser.add_argument("--no-block-resources", action="store_true")
    parser.add_argument(
        "--batch",
        type=Path,
        help="Bestand met product-ids/URLs (één per regel)",
    )
    parser.add_argument(
        "--collect",
        type=int,
        help="Verzamel N product-ids van bol.com-categorieën/zoekpagina's",
    )
    parser.add_argument(
        "--batch-run",
        action="store_true",
        help="Na --collect meteen batch-voorraadcheck doen",
    )
    parser.add_argument(
        "--out",
        type=Path,
        help="Schrijf resultaten naar JSONL (bij batch)",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=0.15,
        help="Pauze tussen batch-items in seconden (default: 0.15)",
    )
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    checker = BolStockChecker(
        max_quantity=args.max_quantity,
        country=args.country,
        headless=not args.headed,
        block_resources=not args.no_block_resources,
        delay_seconds=args.delay,
    )

    # Collect and/or batch mode.
    if args.collect or args.batch:
        products: list[str] = []
        if args.batch:
            products = load_products(args.batch)

        if args.collect:
            Camoufox = checker._import_camoufox()
            with Camoufox(
                headless=not args.headed,
                os="windows",
                locale="nl-NL",
                humanize=False,
            ) as browser:
                page = browser.new_page()
                checker._setup_page(page)
                collected = checker.collect_product_ids(page, limit=args.collect)
            print(f"Verzameld: {len(collected)} product-ids", flush=True)
            if args.batch:
                # merge unique
                seen = set(products)
                for pid in collected:
                    if pid not in seen:
                        products.append(pid)
                        seen.add(pid)
            else:
                products = collected
            collect_out = (
                Path(str(args.out) + ".products.txt")
                if args.out
                else Path("products.txt")
            )
            collect_out.write_text("\n".join(products) + "\n", encoding="utf-8")
            print(f"Productlijst: {collect_out}", flush=True)
            if not args.batch_run and args.batch is None:
                return 0

        if args.batch or args.batch_run:
            if not products:
                print("Geen producten om te checken.", file=sys.stderr)
                return 2
            out = args.out or Path("results.jsonl")
            results = checker.check_batch(
                products,
                cleanup=not args.keep_in_cart,
                include_raw=args.include_raw,
                out_path=out,
                progress=True,
            )
            summary = {
                "total": len(results),
                "ok": sum(1 for r in results if r.error is None and r.available is not None),
                "errors": sum(1 for r in results if r.error is not None),
                "out": str(out),
            }
            print(json.dumps(summary, ensure_ascii=False), flush=True)
            return 0 if summary["ok"] > 0 else 1

    if not args.product:
        parser.error("product is verplicht zonder --batch/--collect")

    try:
        extract_product_id(args.product)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2

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
