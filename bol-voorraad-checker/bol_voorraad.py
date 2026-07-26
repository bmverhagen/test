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
  // Minimale backend-flow (~0.5–0.9s met offer-cache):
  // CreateBasket || add(qty=1) parallel → UpdateItemQuantity(500) → quantity uit GraphQL.
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

  const readState = async () => {
    const resp = await fetch('/nl/rnwy/basket/state', {
      credentials: 'include', headers: restHeaders,
    });
    const text = await resp.text();
    try { return JSON.parse(text); } catch {
      return { itemRows: [] };
    }
  };

  let basketId = cfg.basketId || null;
  const createP = basketId
    ? Promise.resolve(null)
    : gql(cfg.hashes.createBasket, 'CreateBasket', {});
  const addP = fetch('/nl/rnwy/basket/v2/items', {
    method: 'POST',
    credentials: 'include',
    headers: restHeaders,
    body: JSON.stringify({
      globalId: cfg.productId,
      quantity: 1,
      offerUid: cfg.offerUid,
    }),
  }).then(async (r) => ({ status: r.status, text: await r.text() }));

  const [created, add] = await Promise.all([createP, addP]);
  if (!basketId) {
    basketId = created?.json?.data?.basket?.createBasketV2?.id;
    if (!basketId) {
      return { ok: false, error: 'Geen basketId van bol.com ontvangen', created };
    }
  }

  let itemId = null;
  try { itemId = JSON.parse(add.text).itemId; } catch {}
  if (!itemId) {
    const state = await readState();
    itemId = (state.itemRows || []).find(
      (row) => String(row.productId) === String(cfg.productId)
    )?.id || null;
  }
  if (!itemId) {
    return {
      ok: false,
      error: `Toevoegen mislukt (${add.status}): ${add.text}`,
      basketId,
    };
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
  const items = updatedBasket?.items || [];
  // Match op itemId (betrouwbaar); productId in GraphQL is vaak anders gevormd.
  let item = items.find((i) => i?.id === itemId) || null;
  if (!item) {
    item = items.find(
      (i) => String(i?.sellingOffer?.offerUid || '') === String(cfg.offerUid)
    ) || null;
  }

  let available = item?.quantity ?? null;
  let title = item?.sellingOffer?.product?.title || null;
  let outState = updatedBasket || null;

  if (available == null) {
    outState = await readState();
    const row = (outState.itemRows || []).find(
      (r) => String(r.productId) === String(cfg.productId)
    );
    available = row?.quantity ?? null;
    title = row?.productTitle || title;
  }

  if (available == null) {
    return { ok: false, error: 'Geen voorraadaantal ontvangen', update, state: outState, basketId };
  }

  if (cfg.cleanup) {
    // Fire-and-forget: niet op kritieke pad.
    gql(cfg.hashes.removeItem, 'RemoveItem', {
      input: { basketId, itemId },
    }).catch(() => null);
  }

  return {
    ok: true,
    basketId,
    itemId,
    available,
    title,
    path: 'parallel-create-add-update',
    stockAdjusted: Number(available) < Number(cfg.maxQuantity),
    state: outState,
  };
}
"""

CART_BATCH_JS = """
async (cfg) => {
  // Turbo-chunk: hergebruik basket, 403-retry, rotate zonder basket te verliezen.
  // Optioneel: RemoveItem fire-and-forget overlap met volgende add (cleanup).
  const xsrfMatch = document.cookie.match(/(?:^|; )XSRF-TOKEN=([^;]+)/);
  const xsrf = xsrfMatch ? decodeURIComponent(xsrfMatch[1]) : '';
  const rootPageId = crypto.randomUUID();
  const restHeaders = {
    'Accept': 'application/json',
    'Content-Type': 'application/json;charset=UTF-8',
    'X-Requested-With': 'XMLHttpRequest',
  };
  if (xsrf) restHeaders['X-XSRF-TOKEN'] = xsrf;

  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  const isBlocked = (status, text) =>
    status === 403 || status === 429 || /<!DOCTYPE html>/i.test(text || '');

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
        'bol-client-page-id': crypto.randomUUID(),
        'm2-page-id': rootPageId,
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

  const addItem = (p) => fetch('/nl/rnwy/basket/v2/items', {
    method: 'POST',
    credentials: 'include',
    headers: restHeaders,
    body: JSON.stringify({
      globalId: p.productId,
      quantity: 1,
      offerUid: p.offerUid,
    }),
  }).then(async (r) => ({ status: r.status, text: await r.text() }));

  const readState = async () => {
    const resp = await fetch('/nl/rnwy/basket/state', {
      credentials: 'include', headers: restHeaders,
    });
    const text = await resp.text();
    try { return JSON.parse(text); } catch { return { itemRows: [] }; }
  };

  const ensureBasket = async () => {
    const created = await gql(cfg.hashes.createBasket, 'CreateBasket', {});
    if (isBlocked(created.status, created.text)) {
      return { basketId: null, blocked: true, created };
    }
    const id = created?.json?.data?.basket?.createBasketV2?.id || null;
    return { basketId: id, blocked: false, created };
  };

  let basketId = cfg.basketId || null;
  const rotateEvery = cfg.rotateEvery || 25;
  const out = [];
  const tAll = performance.now();
  let pendingRemove = Promise.resolve(null);
  let sinceRotate = 0;
  let consecBlocks = 0;

  if (!basketId) {
    const ensured = await ensureBasket();
    basketId = ensured.basketId;
    if (!basketId) {
      return {
        ok: false,
        blocked: !!ensured.blocked,
        error: 'Geen basketId van bol.com ontvangen',
        totalMs: Math.round(performance.now() - tAll),
        results: cfg.products.map((p) => ({
          productId: p.productId,
          offerUid: p.offerUid,
          ok: false,
          error: ensured.blocked
            ? 'Geblokkeerd bij CreateBasket (403/429)'
            : 'Geen basketId van bol.com ontvangen',
          ms: 0,
        })),
      };
    }
  }

  for (let i = 0; i < cfg.products.length; i++) {
    const p = cfg.products[i];
    const t0 = performance.now();
    sinceRotate += 1;
    if (sinceRotate > rotateEvery) {
      // Alleen wisselen als create lukt — oude basket behouden bij block.
      const ensured = await ensureBasket();
      if (ensured.basketId) {
        basketId = ensured.basketId;
        sinceRotate = 1;
      }
    }

    const runOnce = async () => {
      // Kritieke pad = add + update. RemoveItem is puur fire-and-forget
      // (niet awaiten — scheelt ~50–150ms/product zonder accuracy-verlies).
      const add = await addItem(p);

      if (isBlocked(add.status, add.text)) {
        return { blocked: true, error: `Toevoegen mislukt (${add.status})` };
      }

      let itemId = null;
      try { itemId = JSON.parse(add.text).itemId; } catch {}
      if (!itemId && add.status === 409) {
        // Item bestaat al → state raadplegen
        const state = await readState();
        itemId = (state.itemRows || []).find(
          (row) => String(row.productId) === String(p.productId)
        )?.id || null;
      }
      if (!itemId) {
        return {
          blocked: false,
          error: `Toevoegen mislukt (${add.status}): ${add.text.slice(0, 160)}`,
        };
      }

      const update = await gql(cfg.hashes.updateQty, 'UpdateItemQuantity', {
        input: { basketId, itemId, quantity: cfg.maxQuantity },
      });
      if (isBlocked(update.status, update.text)) {
        return { blocked: true, error: 'Aantal wijzigen geblokkeerd (403/429)', itemId };
      }
      if (update.status >= 400 || update.json?.errors) {
        return {
          blocked: false,
          error: `Aantal wijzigen mislukt: ${update.text.slice(0, 160)}`,
          itemId,
        };
      }

      const items = update.json?.data?.basket?.updateItemQuantityV2?.items || [];
      let item = items.find((x) => x?.id === itemId) || null;
      if (!item) {
        item = items.find(
          (x) => String(x?.sellingOffer?.offerUid || '') === String(p.offerUid)
        ) || null;
      }
      let available = item?.quantity ?? null;
      let title = item?.sellingOffer?.product?.title || null;
      if (available == null) {
        const state = await readState();
        const row = (state.itemRows || []).find(
          (r) => String(r.productId) === String(p.productId)
        );
        available = row?.quantity ?? null;
        title = row?.productTitle || title;
      }
      if (available == null) {
        return { blocked: false, error: 'Geen voorraadaantal ontvangen', itemId };
      }

      if (cfg.cleanup) {
        // Niet awaiten — volgende add mag meteen starten.
        pendingRemove = gql(cfg.hashes.removeItem, 'RemoveItem', {
          input: { basketId, itemId },
        }).catch(() => null);
      }

      return {
        blocked: false,
        ok: true,
        available,
        title,
        itemId,
        stockAdjusted: Number(available) < Number(cfg.maxQuantity),
      };
    };

    try {
      // Bij aanhoudende 403: chunk meteen afbreken (Python doet cooldown-pass).
      if (consecBlocks >= 2) {
        out.push({
          productId: p.productId,
          offerUid: p.offerUid,
          ok: false,
          error: 'Geblokkeerd (chunk afgebroken)',
          ms: Math.round(performance.now() - t0),
          basketId,
          blocked: true,
        });
        continue;
      }

      let result = await runOnce();
      if (result.blocked && consecBlocks < 1) {
        await sleep(cfg.blockBackoffMs || 1500);
        const ensured = await ensureBasket();
        if (ensured.basketId) basketId = ensured.basketId;
        result = await runOnce();
      }
      if (result.ok) {
        consecBlocks = 0;
        out.push({
          productId: p.productId,
          offerUid: p.offerUid,
          ok: true,
          available: result.available,
          title: result.title,
          basketId,
          itemId: result.itemId,
          ms: Math.round(performance.now() - t0),
          stockAdjusted: result.stockAdjusted,
        });
      } else {
        if (result.blocked) consecBlocks += 1;
        else consecBlocks = 0;
        out.push({
          productId: p.productId,
          offerUid: p.offerUid,
          ok: false,
          error: result.error || 'Onbekende fout',
          ms: Math.round(performance.now() - t0),
          basketId,
          itemId: result.itemId || null,
          blocked: !!result.blocked,
        });
      }
    } catch (e) {
      out.push({
        productId: p.productId,
        offerUid: p.offerUid,
        ok: false,
        error: String(e),
        ms: Math.round(performance.now() - t0),
        basketId,
      });
    }
    if (cfg.delayMs > 0 && i + 1 < cfg.products.length) {
      await sleep(cfg.delayMs);
    }
  }

  try { await pendingRemove; } catch {}

  const blockedN = out.filter((r) => r.blocked).length;
  return {
    ok: true,
    basketId,
    blocked: blockedN > 0,
    totalMs: Math.round(performance.now() - tAll),
    results: out,
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


def _chunked(items: list[str], n: int) -> list[list[str]]:
    if n <= 1:
        return [items]
    n = min(n, max(len(items), 1))
    size = (len(items) + n - 1) // n
    return [items[i : i + size] for i in range(0, len(items), size)]


def load_offer_cache(path: Optional[Path]) -> dict[str, str]:
    if path is None or not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    if not isinstance(data, dict):
        return {}
    return {str(k): str(v) for k, v in data.items() if k and v}


def save_offer_cache(path: Optional[Path], cache: dict[str, str]) -> None:
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(cache, ensure_ascii=False, indent=0, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _batch_worker(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Subprocess-worker voor parallelle batch (eigen Camoufox-proces)."""
    if payload.get("stagger_seconds"):
        time.sleep(float(payload["stagger_seconds"]))
    cache_path = Path(payload["offer_cache"]) if payload.get("offer_cache") else None
    checker = BolStockChecker(
        max_quantity=payload["max_quantity"],
        country=payload["country"],
        headless=payload["headless"],
        block_resources=payload["block_resources"],
        delay_seconds=payload["delay_seconds"],
        offer_cache=load_offer_cache(cache_path),
        offer_cache_path=cache_path,
        proxy=payload.get("proxy"),
    )
    if payload.get("turbo"):
        results = checker.check_batch_turbo(
            payload["products"],
            cleanup=payload["cleanup"],
            out_path=None,
            progress=payload.get("progress", False),
        )
    else:
        results = checker.check_batch(
            payload["products"],
            cleanup=payload["cleanup"],
            include_raw=payload["include_raw"],
            out_path=None,
            progress=payload.get("progress", False),
            refresh_every=payload["refresh_every"],
            max_block_streak=payload["max_block_streak"],
            isolated=payload["isolated"],
            workers=1,
            turbo=False,
        )
    return [r.as_public_dict() for r in results]



class BolStockChecker:
    def __init__(
        self,
        *,
        max_quantity: int = DEFAULT_MAX_QUANTITY,
        country: str = "nl",
        headless: bool = True,
        block_resources: bool = True,
        delay_seconds: float = 0.0,
        offer_cache: Optional[dict[str, str]] = None,
        offer_cache_path: Optional[Path] = None,
        proxy: Optional[str] = None,
    ) -> None:
        self.max_quantity = max_quantity
        self.country = country.lower()
        self.headless = headless
        self.block_resources = block_resources
        self.delay_seconds = delay_seconds
        self.offer_cache: dict[str, str] = dict(offer_cache or {})
        self.offer_cache_path = offer_cache_path
        self.proxy = proxy
        # Vernieuw basketId na N items zodat GraphQL niet traag wordt op volle carts.
        self.basket_rotate_every = 25
        # Turbo: grotere chunks, minimale pauze — FF-remove houdt cart licht.
        self.turbo_chunk_size = 50
        self.turbo_chunk_pause = 0.0

    def _import_camoufox(self):
        try:
            from camoufox.sync_api import Camoufox
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError(
                "Ontbrekende dependency: camoufox\n"
                "Installeer met: pip install -r requirements.txt && camoufox fetch"
            ) from exc
        return Camoufox

    def _camoufox_kwargs(self) -> dict[str, Any]:
        kwargs: dict[str, Any] = {
            "headless": self.headless,
            "os": "windows",
            "locale": "nl-NL",
            "humanize": False,
        }
        if self.proxy:
            # Playwright/Camoufox: {"server": "http://host:port", ...}
            server = self.proxy
            proxy_opts: dict[str, str] = {"server": server}
            if "@" in server and "://" in server:
                # http://user:pass@host:port
                scheme, rest = server.split("://", 1)
                creds, host = rest.rsplit("@", 1)
                if ":" in creds:
                    user, pwd = creds.split(":", 1)
                    proxy_opts = {
                        "server": f"{scheme}://{host}",
                        "username": user,
                        "password": pwd,
                    }
            kwargs["proxy"] = proxy_opts
        return kwargs

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

    def _load_product_html(
        self, page: Any, url: str, product_id: str, attempts: int = 2
    ) -> str:
        """Snellere productload: commit + korte poll tot offerUid; fail-fast bij block."""
        last_len = 0
        for attempt in range(attempts):
            wait = "commit" if attempt == 0 else "domcontentloaded"
            page.goto(url, wait_until=wait, timeout=45000)
            # Eerst kort wachten op groei; ~9KB = Akamai-blockpage.
            t0 = time.perf_counter()
            html = page.content()
            last_len = len(html)
            stable_small = 0
            while time.perf_counter() - t0 < 3.5:
                html = page.content()
                last_len = len(html)
                if last_len >= 20000 and "offerUid" in html:
                    self._dismiss_consent(page)
                    return html
                if last_len < 15000:
                    stable_small += 1
                    if stable_small >= 4 and time.perf_counter() - t0 > 0.6:
                        break  # blockpage — volgende poging
                else:
                    stable_small = 0
                time.sleep(0.08)
            if last_len >= 20000 and "offerUid" in html:
                self._dismiss_consent(page)
                return html
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
        if not explicit_offer:
            explicit_offer = self.offer_cache.get(product_id)
        product_url = self._product_url(product_id, product)

        try:
            session_ready = bool(
                page.evaluate(
                    """() => location.hostname.endsWith('bol.com')
                      && document.cookie.includes('XSRF-TOKEN')
                      && document.documentElement.outerHTML.length > 20000"""
                )
            )
            if explicit_offer and session_ready:
                found_offer = explicit_offer
                title = None
            elif explicit_offer:
                # Eerste hit: echte productpagina voor Akamai-cookies, daarna cart-only.
                html = self._load_product_html(page, product_url, product_id, attempts=2)
                found_offer = explicit_offer
                title = self._title_from_html(html)
            else:
                html = self._load_product_html(page, product_url, product_id, attempts=2)
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
                "clearFirst": False,
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
            if result.error is None and found_offer:
                self.offer_cache[product_id] = found_offer
                if self.offer_cache_path is not None:
                    save_offer_cache(self.offer_cache_path, self.offer_cache)
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
        with Camoufox(**self._camoufox_kwargs()) as browser:
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
        cleanup: bool = False,
        include_raw: bool = False,
        out_path: Optional[Path] = None,
        progress: bool = True,
        refresh_every: int = 25,
        max_block_streak: int = 2,
        isolated: bool = False,
        workers: int = 1,
        turbo: bool = False,
    ) -> list[StockResult]:
        """Batch via directe basket-API's.

        turbo=True: hele chunk in één JS-evaluate (snelst zonder extra IP's).
        workers>1: parallelle browsers; op 1 IP liever 2 + stagger, of proxies.
        """
        products_list = list(products)
        if workers > 1 and len(products_list) > 1:
            return self._check_batch_parallel(
                products_list,
                cleanup=cleanup,
                include_raw=include_raw,
                out_path=out_path,
                progress=progress,
                refresh_every=refresh_every,
                max_block_streak=max_block_streak,
                isolated=isolated,
                workers=workers,
                turbo=turbo,
            )
        if turbo:
            return self.check_batch_turbo(
                products_list,
                cleanup=cleanup,
                out_path=out_path,
                progress=progress,
            )
        return self._check_batch_serial(
            products_list,
            cleanup=cleanup,
            include_raw=include_raw,
            out_path=out_path,
            progress=progress,
            refresh_every=refresh_every,
            max_block_streak=max_block_streak,
            isolated=isolated,
        )

    def _turbo_warm(self, page: Any, candidates: list[str]) -> bool:
        """Warm Akamai-sessie; True bij succes."""
        for warm_id in candidates:
            try:
                warm_url = f"{BASE_URL}/{self.country}/nl/p/product/{warm_id}/"
                self._load_product_html(page, warm_url, warm_id, attempts=2)
                return True
            except Exception:  # noqa: BLE001
                time.sleep(1.2)
        try:
            page.goto(
                f"{BASE_URL}/{self.country}/nl/",
                wait_until="domcontentloaded",
                timeout=60000,
            )
            time.sleep(2.0)
            page.goto(
                f"{BASE_URL}/{self.country}/nl/s/?searchtext=voorraad",
                wait_until="domcontentloaded",
                timeout=60000,
            )
            time.sleep(1.5)
            return self._page_ok(page) or True
        except Exception:  # noqa: BLE001
            return False

    def _row_to_stock_result(self, row: dict[str, Any]) -> StockResult:
        pid = str(row.get("productId") or "")
        offer = str(row.get("offerUid") or self.offer_cache.get(pid) or "")
        if row.get("ok") and row.get("available") is not None:
            available = int(row["available"])
            stock_adjusted = bool(row.get("stockAdjusted")) or available < self.max_quantity
            self.offer_cache[pid] = offer
            return StockResult(
                product_id=pid,
                offer_uid=offer,
                available=available,
                requested=self.max_quantity,
                capped_at_max=available >= self.max_quantity and not stock_adjusted,
                stock_adjusted=stock_adjusted,
                product_title=row.get("title"),
                elapsed_seconds=round((row.get("ms") or 0) / 1000.0, 2),
                message=(
                    f"Bol.com leverde {available} i.p.v. {self.max_quantity} stuks."
                    if stock_adjusted
                    else None
                ),
            )
        return StockResult(
            product_id=pid,
            offer_uid=offer,
            available=None,
            requested=self.max_quantity,
            capped_at_max=False,
            stock_adjusted=False,
            error=row.get("error") or "Onbekende fout",
            elapsed_seconds=round((row.get("ms") or 0) / 1000.0, 2),
        )

    def check_batch_turbo(
        self,
        products: Iterable[str],
        *,
        cleanup: bool = False,
        out_path: Optional[Path] = None,
        progress: bool = True,
    ) -> list[StockResult]:
        """Snelste single-browser batch: warmup + chunked JS-loops met 403-herstel."""
        Camoufox = self._import_camoufox()
        products_list = list(products)
        started_all = time.perf_counter()
        prepared: list[dict[str, str]] = []
        results_by_id: dict[str, StockResult] = {}

        missing: list[str] = []
        for product in products_list:
            pid = extract_product_id(product)
            offer = extract_offer_uid(product, None) or self.offer_cache.get(pid)
            if offer:
                prepared.append({"productId": pid, "offerUid": offer})
            else:
                missing.append(product)

        with Camoufox(**self._camoufox_kwargs()) as browser:
            page = browser.new_page()
            self._setup_page(page)

            warm_candidates = [p["productId"] for p in prepared] + [
                extract_product_id(p) for p in missing
            ]
            # Deduplicate while preserving order
            seen_warm: set[str] = set()
            warm_list = []
            for wid in warm_candidates:
                if wid not in seen_warm:
                    seen_warm.add(wid)
                    warm_list.append(wid)

            if not self._turbo_warm(page, warm_list[:16]):
                err = "Turbo warmup mislukt (Akamai)"
                results = [
                    StockResult(
                        product_id=extract_product_id(p),
                        offer_uid=self.offer_cache.get(extract_product_id(p), ""),
                        available=None,
                        requested=self.max_quantity,
                        capped_at_max=False,
                        stock_adjusted=False,
                        error=err,
                        elapsed_seconds=0.0,
                    )
                    for p in products_list
                ]
                if progress:
                    print(err, flush=True)
                if out_path is not None:
                    out_path.parent.mkdir(parents=True, exist_ok=True)
                    with out_path.open("w", encoding="utf-8") as out_file:
                        for result in results:
                            out_file.write(
                                json.dumps(result.as_public_dict(), ensure_ascii=False)
                                + "\n"
                            )
                return results

            for product in missing:
                pid = extract_product_id(product)
                try:
                    html = self._load_product_html(
                        page,
                        self._product_url(pid, product),
                        pid,
                        attempts=2,
                    )
                    offer, _title = self._extract_offer_from_html(html, pid)
                    self.offer_cache[pid] = offer
                    prepared.append({"productId": pid, "offerUid": offer})
                except Exception as exc:  # noqa: BLE001
                    results_by_id[pid] = StockResult(
                        product_id=pid,
                        offer_uid="",
                        available=None,
                        requested=self.max_quantity,
                        capped_at_max=False,
                        stock_adjusted=False,
                        error=f"OfferUid niet gevonden: {exc}",
                        elapsed_seconds=0.0,
                    )

            by_id = {p["productId"]: p for p in prepared}
            ordered = [
                by_id[extract_product_id(p)]
                for p in products_list
                if extract_product_id(p) in by_id
            ]

            chunk_size = max(1, int(self.turbo_chunk_size))
            if progress:
                print(
                    f"Turbo-batch: {len(ordered)} producten in chunks van {chunk_size} "
                    f"(cache-hits={len(ordered) - len(missing)})",
                    flush=True,
                )

            basket_id: Optional[str] = None
            done = 0
            pending_retry: list[dict[str, str]] = []
            chunks = [
                ordered[i : i + chunk_size] for i in range(0, len(ordered), chunk_size)
            ]
            block_streak = 0

            def _is_block_row(row: dict[str, Any]) -> bool:
                err = str(row.get("error") or "")
                return bool(
                    row.get("blocked")
                    or "403" in err
                    or "429" in err
                    or "Geblokkeerd" in err
                    or "basketId" in err
                )

            def _eval_chunk(
                chunk_products: list[dict[str, str]],
                *,
                use_basket: Optional[str],
                backoff_ms: int,
            ) -> tuple[list[dict[str, Any]], Optional[str]]:
                raw_eval = page.evaluate(
                    CART_BATCH_JS,
                    {
                        "products": chunk_products,
                        "maxQuantity": self.max_quantity,
                        "country": self.country,
                        "basketId": use_basket,
                        "rotateEvery": self.basket_rotate_every,
                        "delayMs": int(self.delay_seconds * 1000),
                        "blockBackoffMs": backoff_ms,
                        "hashes": {
                            "createBasket": GQL_CREATE_BASKET,
                            "updateQty": GQL_UPDATE_QTY,
                            "removeItem": GQL_REMOVE_ITEM,
                        },
                        "cleanup": cleanup,
                    },
                )
                return list(raw_eval.get("results") or []), raw_eval.get("basketId") or use_basket

            chunk_idx = 0
            while chunk_idx < len(chunks):
                chunk = chunks[chunk_idx]
                rows, basket_id = _eval_chunk(chunk, use_basket=basket_id, backoff_ms=1200)
                failed = [r for r in rows if not r.get("ok") and _is_block_row(r)]
                ok_n = sum(1 for r in rows if r.get("ok"))

                if failed and ok_n == 0:
                    block_streak += 1
                    # Hele rest + deze chunk naar eind-pass — niet elk chunk verbranden.
                    pending_retry.extend(
                        by_id[str(r["productId"])]
                        for r in failed
                        if str(r["productId"]) in by_id
                    )
                    for later in chunks[chunk_idx + 1 :]:
                        pending_retry.extend(later)
                    if progress:
                        print(
                            f"Chunk {chunk_idx + 1}/{len(chunks)}: volledig geblokkeerd → "
                            f"skip rest, {len(pending_retry)} naar eind-pass",
                            flush=True,
                        )
                    break
                elif failed:
                    block_streak = 0
                    if progress:
                        print(
                            f"Chunk {chunk_idx + 1}/{len(chunks)}: "
                            f"{len(failed)} geblokkeerd → korte retry",
                            flush=True,
                        )
                    time.sleep(3.0)
                    self._turbo_warm(
                        page,
                        [str(r["productId"]) for r in failed] + warm_list[:3],
                    )
                    retry_products = [
                        by_id[str(r["productId"])]
                        for r in failed
                        if str(r["productId"]) in by_id
                    ]
                    # Hergebruik basket als die nog bestaat; forceer geen create.
                    rows2, basket_id = _eval_chunk(
                        retry_products, use_basket=basket_id, backoff_ms=2500
                    )
                    by_retry = {str(r.get("productId")): r for r in rows2}
                    new_rows = []
                    for r in rows:
                        pid = str(r.get("productId"))
                        if pid in by_retry:
                            new_rows.append(by_retry[pid])
                        else:
                            new_rows.append(r)
                    rows = new_rows
                    still = [r for r in rows if not r.get("ok") and _is_block_row(r)]
                    pending_retry.extend(
                        by_id[str(r["productId"])]
                        for r in still
                        if str(r["productId"]) in by_id
                    )
                else:
                    block_streak = 0

                pending_ids = {p["productId"] for p in pending_retry}
                for row in rows:
                    if not row.get("ok") and _is_block_row(row):
                        if str(row.get("productId")) in pending_ids:
                            continue
                    result = self._row_to_stock_result(row)
                    results_by_id[result.product_id] = result
                    done += 1
                    if progress:
                        status = (
                            f"voorraad={result.available}"
                            if result.error is None
                            else f"FOUT={str(result.error)[:80]}"
                        )
                        print(
                            f"[{done}/{len(ordered)}] {result.product_id} "
                            f"{status} ({result.elapsed_seconds}s)",
                            flush=True,
                        )

                chunk_idx += 1
                if chunk_idx < len(chunks):
                    pause = self.turbo_chunk_pause
                    if failed:
                        pause = max(pause, 1.5)
                    if pause > 0:
                        time.sleep(pause)

            # Eind-pass: alle geblokkeerde items in herstelrondes met verse page.
            if pending_retry:
                seen_r: set[str] = set()
                uniq_retry: list[dict[str, str]] = []
                for p in pending_retry:
                    if p["productId"] not in seen_r:
                        seen_r.add(p["productId"])
                        uniq_retry.append(p)
                remaining = uniq_retry
                for pass_n in range(1, 4):
                    if not remaining:
                        break
                    if progress:
                        print(
                            f"Eind-pass {pass_n}: {len(remaining)} items "
                            f"(cooldown {15 * pass_n}s + nieuwe page)",
                            flush=True,
                        )
                    time.sleep(15 * pass_n)
                    try:
                        page.close()
                    except Exception:  # noqa: BLE001
                        pass
                    page = browser.new_page()
                    self._setup_page(page)
                    self._turbo_warm(
                        page,
                        [p["productId"] for p in remaining[:8]] + warm_list[:4],
                    )
                    basket_id = None
                    still: list[dict[str, str]] = []
                    for i in range(0, len(remaining), chunk_size):
                        part = remaining[i : i + chunk_size]
                        rows, basket_id = _eval_chunk(
                            part, use_basket=basket_id, backoff_ms=3000
                        )
                        for row in rows:
                            result = self._row_to_stock_result(row)
                            results_by_id[result.product_id] = result
                            if result.error is not None and _is_block_row(row):
                                pid = result.product_id
                                if pid in by_id:
                                    still.append(by_id[pid])
                            if progress:
                                status = (
                                    f"voorraad={result.available}"
                                    if result.error is None
                                    else f"FOUT={str(result.error)[:80]}"
                                )
                                print(
                                    f"[retry{pass_n}] {result.product_id} {status} "
                                    f"({result.elapsed_seconds}s)",
                                    flush=True,
                                )
                        if i + chunk_size < len(remaining):
                            time.sleep(1.5 + pass_n)
                    remaining = still

        results = []
        for product in products_list:
            pid = extract_product_id(product)
            if pid in results_by_id:
                results.append(results_by_id[pid])
            else:
                results.append(
                    StockResult(
                        product_id=pid,
                        offer_uid=self.offer_cache.get(pid, ""),
                        available=None,
                        requested=self.max_quantity,
                        capped_at_max=False,
                        stock_adjusted=False,
                        error="Geen resultaat",
                        elapsed_seconds=0.0,
                    )
                )

        if self.offer_cache_path is not None:
            save_offer_cache(self.offer_cache_path, self.offer_cache)

        if out_path is not None:
            out_path.parent.mkdir(parents=True, exist_ok=True)
            with out_path.open("w", encoding="utf-8") as out_file:
                for result in results:
                    out_file.write(
                        json.dumps(result.as_public_dict(), ensure_ascii=False) + "\n"
                    )

        if progress:
            ok = sum(1 for r in results if r.error is None and r.available is not None)
            elapsed = round(time.perf_counter() - started_all, 2)
            print(
                f"Klaar: {ok}/{len(results)} ok in {elapsed}s "
                f"(avg {elapsed / max(len(results), 1):.2f}s/product, "
                f"throughput {len(results) / max(elapsed, 0.01):.2f}/s)",
                flush=True,
            )
        return results

    def _check_batch_parallel(
        self,
        products_list: list[str],
        *,
        cleanup: bool,
        include_raw: bool,
        out_path: Optional[Path],
        progress: bool,
        refresh_every: int,
        max_block_streak: int,
        isolated: bool,
        workers: int,
        turbo: bool = False,
    ) -> list[StockResult]:
        from concurrent.futures import ProcessPoolExecutor, as_completed

        chunks = _chunked(products_list, workers)
        if progress:
            print(
                f"Parallel batch: {len(products_list)} producten, "
                f"{len(chunks)} workers"
                + (" [turbo]" if turbo else ""),
                flush=True,
            )
        started_all = time.perf_counter()
        payloads = [
            {
                "products": chunk,
                "max_quantity": self.max_quantity,
                "country": self.country,
                "headless": self.headless,
                "block_resources": self.block_resources,
                "delay_seconds": self.delay_seconds,
                "cleanup": cleanup,
                "include_raw": include_raw,
                "refresh_every": refresh_every,
                "max_block_streak": max_block_streak,
                "isolated": isolated,
                "progress": False,
                "turbo": turbo,
                "proxy": self.proxy,
                # Stagger starts to reduce same-IP Akamai collisions.
                "stagger_seconds": idx * 8.0,
                "offer_cache": str(self.offer_cache_path)
                if self.offer_cache_path
                else None,
                "index": idx,
            }
            for idx, chunk in enumerate(chunks)
        ]

        chunk_results: dict[int, list[dict[str, Any]]] = {}
        with ProcessPoolExecutor(max_workers=len(chunks)) as pool:
            futures = {
                pool.submit(_batch_worker, {k: v for k, v in p.items() if k != "index"}): p["index"]
                for p in payloads
            }
            for fut in as_completed(futures):
                idx = futures[fut]
                chunk_results[idx] = fut.result()
                if progress:
                    ok = sum(1 for r in chunk_results[idx] if r.get("error") is None)
                    print(
                        f"Worker {idx + 1}/{len(chunks)} klaar: "
                        f"{ok}/{len(chunk_results[idx])} ok",
                        flush=True,
                    )

        ordered_dicts: list[dict[str, Any]] = []
        for idx in range(len(chunks)):
            ordered_dicts.extend(chunk_results.get(idx, []))

        results = [
            StockResult(
                product_id=d["product_id"],
                offer_uid=d.get("offer_uid") or "",
                available=d.get("available"),
                requested=d.get("requested") or self.max_quantity,
                capped_at_max=bool(d.get("capped_at_max")),
                stock_adjusted=bool(d.get("stock_adjusted")),
                product_title=d.get("product_title"),
                message=d.get("message"),
                elapsed_seconds=d.get("elapsed_seconds"),
                error=d.get("error"),
                raw_basket=d.get("raw_basket"),
            )
            for d in ordered_dicts
        ]

        if out_path is not None:
            out_path.parent.mkdir(parents=True, exist_ok=True)
            with out_path.open("w", encoding="utf-8") as out_file:
                for result in results:
                    out_file.write(
                        json.dumps(result.as_public_dict(), ensure_ascii=False) + "\n"
                    )

        if progress:
            ok = sum(1 for r in results if r.error is None and r.available is not None)
            elapsed = round(time.perf_counter() - started_all, 2)
            print(
                f"Klaar: {ok}/{len(results)} ok in {elapsed}s "
                f"(avg {elapsed / max(len(results), 1):.2f}s/product, "
                f"throughput {len(results) / max(elapsed, 0.01):.2f}/s)",
                flush=True,
            )
        return results

    def _check_batch_serial(
        self,
        products_list: list[str],
        *,
        cleanup: bool = False,
        include_raw: bool = False,
        out_path: Optional[Path] = None,
        progress: bool = True,
        refresh_every: int = 25,
        max_block_streak: int = 2,
        isolated: bool = False,
    ) -> list[StockResult]:
        Camoufox = self._import_camoufox()
        results: list[StockResult] = []
        started_all = time.perf_counter()
        block_streak = 0
        basket_id: Optional[str] = None

        out_file = None
        if out_path is not None:
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_file = out_path.open("w", encoding="utf-8")

        browser_cm = None
        browser = None
        page = None

        def open_browser() -> tuple[Any, Any, Any]:
            cm = Camoufox(**self._camoufox_kwargs())
            b = cm.__enter__()
            p = b.new_page()
            self._setup_page(p)
            return cm, b, p

        def close_browser() -> None:
            nonlocal browser_cm, browser, page, basket_id
            if browser_cm is not None:
                try:
                    browser_cm.__exit__(None, None, None)
                except Exception:
                    pass
            browser_cm = None
            browser = None
            page = None
            basket_id = None

        def check_one(product: str) -> StockResult:
            nonlocal basket_id
            assert browser is not None
            if isolated:
                context = browser.new_context()
                p = context.new_page()
                self._setup_page(p)
                try:
                    result, _ = self._check_on_page(
                        p,
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

            assert page is not None
            result, basket_id = self._check_on_page(
                page,
                product,
                cleanup=cleanup,
                include_raw=include_raw,
                basket_id=basket_id,
            )
            return result

        def is_blocked(result: StockResult) -> bool:
            if not result.error:
                return False
            err = result.error.lower()
            return (
                "geblokkeerd" in err
                or "403" in result.error
                or "xsrf" in err
                or "onbruikbaar" in err
                or "aantal wijzigen mislukt" in err
                or "geen basketid" in err
            )

        try:
            browser_cm, browser, page = open_browser()

            for idx, product in enumerate(products_list, start=1):
                if idx > 1 and (idx - 1) % refresh_every == 0:
                    if progress:
                        print(f"Sessie-refresh na {idx - 1} producten...", flush=True)
                    close_browser()
                    time.sleep(1.5)
                    browser_cm, browser, page = open_browser()
                elif (
                    idx > 1
                    and basket_id is not None
                    and (idx - 1) % max(self.basket_rotate_every, 1) == 0
                ):
                    # Frisse basket houdt UpdateItemQuantity snel.
                    basket_id = None

                result = check_one(product)

                if is_blocked(result):
                    block_streak += 1
                    backoff = min(20.0, 2.0 * block_streak)
                    if progress:
                        print(
                            f"Blokkade ({block_streak}): backoff {backoff:.0f}s + retry",
                            flush=True,
                        )
                    time.sleep(backoff)
                    if block_streak >= max_block_streak:
                        close_browser()
                        time.sleep(1.5)
                        browser_cm, browser, page = open_browser()
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
        default=0.0,
        help="Pauze tussen batch-items in seconden (default: 0)",
    )
    parser.add_argument(
        "--isolated",
        action="store_true",
        help="Batch: verse browser-context per product (langzamer, meer isolatie)",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=1,
        help="Parallelle browser-workers (met --proxy of stagger; default 1)",
    )
    parser.add_argument(
        "--fast",
        action="store_true",
        help="Snelheidspreset: chunked turbo + offer-cache + delay=0 (workers>1 alleen met --proxy)",
    )
    parser.add_argument(
        "--turbo",
        action="store_true",
        help="Hele batch in één browser JS-loop (minder overhead)",
    )
    parser.add_argument(
        "--offer-cache",
        type=Path,
        default=None,
        help="JSON-cache productId→offerUid (slaat HTML-stap over bij hits)",
    )
    parser.add_argument(
        "--proxy",
        default=None,
        help="Proxy URL, bv. http://user:pass@host:port (nodig voor echte parallelle snelheid)",
    )
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    workers = args.workers
    delay = args.delay
    keep_in_cart = args.keep_in_cart
    offer_cache_path = args.offer_cache
    turbo = args.turbo
    if args.fast:
        delay = 0.0
        # Cleanup aan: RemoveItem fire-and-forget (kritieke pad = add+update).
        keep_in_cart = False
        turbo = True
        # Zonder proxy: 1 turbo-worker is stabieler; met proxy mag workers>1.
        if workers <= 1 and args.proxy:
            workers = 2
        elif workers <= 1:
            workers = 1
        if offer_cache_path is None:
            offer_cache_path = Path("offer_cache.json")

    checker = BolStockChecker(
        max_quantity=args.max_quantity,
        country=args.country,
        headless=not args.headed,
        block_resources=not args.no_block_resources,
        delay_seconds=delay,
        offer_cache=load_offer_cache(offer_cache_path),
        offer_cache_path=offer_cache_path,
        proxy=args.proxy,
    )

    # Collect and/or batch mode.
    if args.collect or args.batch:
        products: list[str] = []
        if args.batch:
            products = load_products(args.batch)

        if args.collect:
            Camoufox = checker._import_camoufox()
            with Camoufox(**checker._camoufox_kwargs()) as browser:
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
                cleanup=not keep_in_cart,
                include_raw=args.include_raw,
                out_path=out,
                progress=True,
                isolated=args.isolated,
                workers=max(1, workers),
                turbo=turbo,
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
            cleanup=not keep_in_cart,
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
