"""Shop URL templates and markdown/HTML product parsers for up to 10 pages."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Callable
from urllib.parse import urljoin

from bs4 import BeautifulSoup

try:
    from .brands import product
except ImportError:
    from brands import product


@dataclass
class ShopConfig:
    name: str
    domain: str
    prefer_jina: bool = False
    # page is 1-based
    page_url: Callable[[int], str] | None = None
    parser: str = "auto"  # auto | amazon | dod | notino | koopjes | jina_generic
    # Prefer JSON/GraphQL backend over HTML/Jina when available
    use_api: bool = False


def page_urls() -> list[ShopConfig]:
    q = "conditioner"
    return [
        ShopConfig(
            "Amazon.nl",
            "amazon.nl",
            page_url=lambda p: f"https://www.amazon.nl/s?k={q}&page={p}",
            parser="amazon",
        ),
        ShopConfig(
            "De Online Drogist",
            "deonlinedrogist.nl",
            page_url=lambda p: f"https://www.deonlinedrogist.nl/search/?q={q}&page={p}",
            parser="dod",
        ),
        ShopConfig(
            "Notino",
            "notino.nl",
            prefer_jina=True,
            use_api=True,
            page_url=lambda p: f"https://www.notino.nl/search.asp?exps={q}&f=1-{p}-3649"
            if p > 1
            else f"https://www.notino.nl/search.asp?exps={q}",
            parser="notino_jina",
        ),
        ShopConfig(
            "KoopjesDrogisterij",
            "koopjesdrogisterij.nl",
            prefer_jina=True,
            use_api=True,
            page_url=lambda p: (
                f"https://www.koopjesdrogisterij.nl/?s={q}&post_type=product"
                if p == 1
                else f"https://www.koopjesdrogisterij.nl/page/{p}/?s={q}&post_type=product"
            ),
            parser="koopjes_jina",
        ),
        ShopConfig(
            "Kruidvat",
            "kruidvat.nl",
            prefer_jina=True,
            use_api=True,
            page_url=lambda p: f"https://www.kruidvat.nl/verzorging/haarverzorging/conditioner?currentPage={p}",
            parser="kruidvat_jina",
        ),
        ShopConfig(
            "Trekpleister",
            "trekpleister.nl",
            prefer_jina=True,
            use_api=True,
            page_url=lambda p: f"https://www.trekpleister.nl/verzorging/haarverzorging/conditioner?currentPage={p}",
            parser="trekpleister_jina",
        ),
        ShopConfig(
            "Bol.com",
            "bol.com",
            prefer_jina=True,
            use_api=True,
            page_url=lambda p: f"https://www.bol.com/nl/nl/s/?searchtext={q}%20haar&page={p}",
            parser="bol_jina",
        ),
        ShopConfig(
            "Etos",
            "etos.nl",
            prefer_jina=True,
            use_api=True,
            page_url=lambda p: f"https://www.etos.nl/search/?q={q}&page={p}",
            parser="etos_jina",
        ),
        ShopConfig(
            "Albert Heijn",
            "ah.nl",
            prefer_jina=True,
            use_api=True,
            page_url=lambda p: f"https://www.ah.nl/zoeken?query={q}&page={p}",
            parser="ah_jina",
        ),
        ShopConfig(
            "Jumbo",
            "jumbo.com",
            prefer_jina=True,
            use_api=True,
            page_url=lambda p: f"https://www.jumbo.com/producten/?searchType=keyword&searchTerms={q}&offSet={(p-1)*24}",
            parser="jumbo_jina",
        ),
        ShopConfig(
            "Plus",
            "plus.nl",
            prefer_jina=True,
            use_api=True,
            page_url=lambda p: f"https://www.plus.nl/zoekresultaten?SearchTerm={q}&PageNumber={p}",
            parser="plus_jina",
        ),
        ShopConfig(
            "Dirk",
            "dirk.nl",
            prefer_jina=True,
            use_api=True,
            page_url=lambda p: f"https://www.dirk.nl/producten?zoekterm={q}&page={p}",
            parser="dirk_jina",
        ),
        ShopConfig(
            "DA Drogist",
            "da.nl",
            prefer_jina=True,
            use_api=True,
            page_url=lambda p: f"https://www.da.nl/search?query={q}&page={p}",
            parser="da_jina",
        ),
        ShopConfig(
            "Plein.nl",
            "plein.nl",
            prefer_jina=True,
            use_api=True,
            page_url=lambda p: f"https://www.plein.nl/catalogsearch/result/index/?q={q}&p={p}",
            parser="plein_jina",
        ),
        ShopConfig(
            "Drogeriedepot",
            "drogeriedepot.nl",
            prefer_jina=True,
            use_api=True,
            page_url=lambda p: f"https://www.drogeriedepot.nl/c/Haarverzorging-Kleuren/Conditioner/?p={p}",
            parser="generic_jina",
        ),
        ShopConfig(
            "ICI Paris XL",
            "iciparisxl.nl",
            prefer_jina=True,
            use_api=True,
            page_url=lambda p: (
                f"https://www.iciparisxl.nl/haar/haarverzorging/conditioner/c/050103"
                f"?currentPage={p-1}"
            ),
            parser="generic_jina",
        ),
        ShopConfig(
            "Douglas",
            "douglas.nl",
            prefer_jina=True,
            use_api=True,
            page_url=lambda p: f"https://www.douglas.nl/nl/search?q={q}&page={p}",
            parser="generic_jina",
        ),
        ShopConfig(
            "Parfumselect",
            "parfumselect.nl",
            prefer_jina=True,
            use_api=True,
            page_url=lambda p: f"https://parfumselect.nl/page/{p}/?s={q}&post_type=product"
            if p > 1
            else f"https://parfumselect.nl/?s={q}&post_type=product",
            parser="generic_jina",
        ),
        ShopConfig(
            "Newpharma",
            "newpharma.nl",
            prefer_jina=True,
            use_api=True,
            page_url=lambda p: (
                "https://www.newpharma.nl/cat/schoonheids-en-cosmetica/haarverzorging/"
                f"conditioner-verzorging/12-172-1705.html?page={p}"
            ),
            parser="generic_jina",
        ),
        ShopConfig(
            "Zalando",
            "zalando.nl",
            prefer_jina=True,
            use_api=True,
            page_url=lambda p: f"https://www.zalando.nl/beauty/?q={q}&p={p}",
            parser="generic_jina",
        ),
    ]


def _md_links(text: str) -> list[tuple[str, str]]:
    return re.findall(r"\[([^\]]{3,200})\]\((https?://[^)\s]+)\)", text)


def _clean_md_title(title: str) -> str:
    title = re.sub(r"!\[Image[^\]]*\]", "", title)
    title = re.sub(r"Image\s+\d+:\s*", "", title)
    title = re.sub(r"\s+", " ", title).strip(" -|")
    title = re.sub(r"^(Actie|Nieuw)\s+", "", title, flags=re.I)
    return title.strip()


def parse_amazon(html: str, base: str = "https://www.amazon.nl") -> list[dict]:
    soup = BeautifulSoup(html, "lxml")
    out: list[dict] = []
    seen: set[str] = set()
    for card in soup.select('div[data-component-type="s-search-result"]'):
        asin = card.get("data-asin") or ""
        if not asin or asin in seen:
            continue
        seen.add(asin)
        h2 = card.select_one("h2")
        title = h2.get_text(" ", strip=True) if h2 else ""
        if not title:
            continue
        price_el = card.select_one("span.a-offscreen")
        price = price_el.get_text(strip=True).replace("\xa0", " ") if price_el else None
        href_el = card.select_one(f'a[href*="/dp/{asin}"]')
        url = urljoin(base, href_el["href"].split("?")[0]) if href_el else f"{base}/dp/{asin}"
        out.append(product(rank=0, title=title, url=url, price=price, extra={"sku": asin}))
    return out


def parse_dod(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "lxml")
    for script in soup.select('script[type="application/ld+json"]'):
        try:
            data = json.loads(script.string or "")
        except Exception:
            continue
        if not isinstance(data, dict) or data.get("@type") != "CollectionPage":
            continue
        items = (data.get("mainEntity") or {}).get("itemListElement") or []
        out = []
        for item in items:
            title = item.get("name") or ""
            if title:
                out.append(product(rank=0, title=title, url=item.get("url")))
        if out:
            return out
    # jina/markdown fallback
    return parse_generic_jina(html, domain="deonlinedrogist.nl")


def parse_ah_jina(text: str) -> list[dict]:
    out: list[dict] = []
    seen: set[str] = set()
    # Prefer explicit product URLs
    for title, url in _md_links(text):
        if "/producten/product/wi" not in url:
            continue
        title = _clean_md_title(title)
        if title.startswith("![") or len(title) < 5:
            # derive from slug
            slug = url.rstrip("/").split("/")[-1].replace("-", " ")
            title = slug
        key = url.split("?")[0]
        if key in seen:
            continue
        seen.add(key)
        out.append(product(rank=0, title=title, url=url.split("?")[0]))
    if out:
        return out
    # Image alt titles
    for name in re.findall(r"Image\s+\d+:\s*([^\]\|\n]+)", text):
        name = name.strip()
        if "conditioner" not in name.lower() and "crèmespoeling" not in name.lower():
            continue
        key = name.casefold()
        if key in seen:
            continue
        seen.add(key)
        out.append(product(rank=0, title=name))
    return out


def parse_jumbo_jina(text: str) -> list[dict]:
    out: list[dict] = []
    seen: set[str] = set()
    if "<html" in text[:800].lower():
        soup = BeautifulSoup(text, "lxml")
        for a in soup.select('a[href*="/producten/"]'):
            href = a.get("href") or ""
            if not re.search(r"/producten/.+-\d+[A-Za-z]{2,4}", href):
                continue
            title = a.get_text(" ", strip=True) or href.rstrip("/").split("/")[-1]
            low = (title + href).lower()
            if not any(k in low for k in ("conditioner", "syoss", "gliss", "andrelon", "shampoo", "haar", "schauma")):
                continue
            url = urljoin("https://www.jumbo.com", href.split("?")[0])
            if url in seen:
                continue
            seen.add(url)
            out.append(product(rank=0, title=title, url=url))
        if out:
            return out
    for title, url in _md_links(text):
        if not re.search(r"https://www\.jumbo\.com/producten/.+-\d+[A-Za-z]{2,4}$", url.split("?")[0]):
            continue
        title = _clean_md_title(title)
        if len(title) < 4:
            title = url.rstrip("/").split("/")[-1].rsplit("-", 1)[0].replace("-", " ")
        low = title.lower() + url.lower()
        if not any(k in low for k in ("conditioner", "crèmespoeling", "shampoo", "syoss", "gliss", "andrelon", "haar")):
            if "conditioner" not in url.lower():
                continue
        key = url.split("?")[0]
        if key in seen:
            continue
        seen.add(key)
        out.append(product(rank=0, title=title, url=key))
    return out


def parse_kruidvat_jina(text: str) -> list[dict]:
    out: list[dict] = []
    seen: set[str] = set()
    # product detail urls
    for title, url in _md_links(text):
        if not re.search(r"kruidvat\.nl/.+/p/\d+", url):
            continue
        title = _clean_md_title(title)
        if len(title) < 5 or title.lower() in {"conditioner", "leave-in conditioner"}:
            # use alt from nearby image or slug
            slug = url.split("/p/")[0].rstrip("/").split("/")[-1].replace("-", " ")
            title = slug
        key = url.split("?")[0]
        if key in seen:
            continue
        seen.add(key)
        out.append(product(rank=0, title=title, url=key))
    if out:
        return out
    for name in re.findall(r"Image\s+\d+:\s*([^\]\|\n]+)", text):
        name = name.strip()
        if len(name) < 8:
            continue
        if not any(k in name.lower() for k in ("conditioner", "crème", "spoeling", "2-in-1", "gliss", "syoss")):
            continue
        key = name.casefold()
        if key in seen:
            continue
        seen.add(key)
        out.append(product(rank=0, title=name))
    return out


def parse_trekpleister_jina(text: str) -> list[dict]:
    # same URL shape as Kruidvat (AS Watson)
    out: list[dict] = []
    seen: set[str] = set()
    for title, url in _md_links(text):
        if not re.search(r"trekpleister\.nl/.+/p/\d+", url):
            continue
        title = _clean_md_title(title)
        if len(title) < 5:
            title = url.split("/p/")[0].rstrip("/").split("/")[-1].replace("-", " ")
        key = url.split("?")[0]
        if key in seen:
            continue
        seen.add(key)
        out.append(product(rank=0, title=title, url=key))
    if out:
        return out
    return parse_kruidvat_jina(text.replace("trekpleister", "kruidvat"))


def parse_koopjes_jina(text: str) -> list[dict]:
    if "<html" in text[:800].lower() or "woocommerce" in text.lower():
        soup = BeautifulSoup(text, "lxml")
        out: list[dict] = []
        seen: set[str] = set()
        for h in soup.select(
            "h2, h3, li.product h2, .product-title, .woocommerce-loop-product__title"
        ):
            title = h.get_text(" ", strip=True)
            if not title or len(title) < 4:
                continue
            a = h.find("a", href=True) or h.find_parent("a", href=True)
            url = a["href"] if a else None
            if url and url.startswith("/"):
                url = urljoin("https://www.koopjesdrogisterij.nl", url)
            key = (url or title).casefold()
            if key in seen:
                continue
            seen.add(key)
            out.append(product(rank=0, title=title, url=url))
        if out:
            return out
    out: list[dict] = []
    seen: set[str] = set()
    for title, url in _md_links(text):
        if "koopjesdrogisterij.nl" not in url:
            continue
        if not url.endswith(".html"):
            continue
        title = _clean_md_title(title)
        if len(title) < 6 or title.lower().startswith("adviesprijs"):
            continue
        key = url.split("?")[0]
        if key in seen:
            continue
        seen.add(key)
        out.append(product(rank=0, title=title, url=key))
    return out


def parse_notino_jina(text: str) -> list[dict]:
    out: list[dict] = []
    seen: set[str] = set()
    # Prefer embedded products JSON if present (HTML)
    match = re.search(r'"products"\s*:\s*(\[)', text)
    if match:
        start = match.start(1)
        depth = 0
        end = None
        for idx, ch in enumerate(text[start:], start):
            if ch == "[":
                depth += 1
            elif ch == "]":
                depth -= 1
                if depth == 0:
                    end = idx + 1
                    break
        if end:
            try:
                items = json.loads(text[start:end])
                for item in items:
                    brand = item.get("brandName") or ""
                    name = item.get("name") or ""
                    annotation = item.get("annotation") or ""
                    title = f"{brand} {name} {annotation}".strip()
                    price = (item.get("priceInformation") or {}).get("price")
                    price_s = f"€{price:.2f}".replace(".", ",") if isinstance(price, (int, float)) else None
                    out.append(
                        product(
                            rank=0,
                            title=title,
                            brand=brand or None,
                            url=urljoin("https://www.notino.nl", item.get("url") or ""),
                            price=price_s,
                            extra={"sku": str(item.get("id") or "")},
                        )
                    )
                if out:
                    return out
            except Exception:
                pass
    for title, url in _md_links(text):
        if "/p-" not in url and not re.search(r"/p-\d+", url):
            # notino product paths often /brand/slug/p-123/
            if not re.search(r"notino\.nl/.+/p-\d+", url):
                continue
        title = _clean_md_title(title)
        if "conditioner" not in title.lower() and "condicioner" not in title.lower():
            continue
        key = url.split("?")[0]
        if key in seen:
            continue
        seen.add(key)
        out.append(product(rank=0, title=title, url=key))
    # Image alts
    if not out:
        for name in re.findall(r"Image\s+\d+:\s*([^\]\|\n]+)", text):
            name = _clean_md_title(name)
            if "conditioner" in name.lower() or "condicioner" in name.lower():
                key = name.casefold()
                if key in seen:
                    continue
                seen.add(key)
                out.append(product(rank=0, title=name))
    return out


def parse_da_jina(text: str) -> list[dict]:
    out: list[dict] = []
    seen: set[str] = set()
    if "<html" in text[:1000].lower() or "__NEXT_DATA__" in text:
        soup = BeautifulSoup(text, "lxml")
        for a in soup.select('a[href*="/product/"]'):
            href = a.get("href") or ""
            title = a.get_text(" ", strip=True)
            if len(title) < 3:
                title = href.rstrip("/").split("/")[-1].replace("-", " ")
            url = urljoin("https://www.da.nl", href.split("?")[0])
            if url in seen:
                continue
            seen.add(url)
            out.append(product(rank=0, title=title, url=url))
        if out:
            return out
    for title, url in _md_links(text):
        if "/product/" not in url and "/p/" not in url:
            continue
        title = _clean_md_title(title)
        if len(title) < 4 or title.lower() == "image":
            slug = url.rstrip("/").split("/")[-1]
            title = re.sub(r"-\d+$", "", slug).replace("-", " ")
        key = url.split("?")[0]
        if key in seen:
            continue
        seen.add(key)
        out.append(product(rank=0, title=title, url=key))
    for m in re.finditer(r"##\s+([^\n]{5,120})", text):
        title = m.group(1).strip()
        if title.casefold() in seen:
            continue
        seen.add(title.casefold())
        out.append(product(rank=0, title=title))
    return out


def parse_bol_jina(text: str) -> list[dict]:
    out: list[dict] = []
    seen: set[str] = set()
    for title, url in _md_links(text):
        if "/nl/nl/p/" not in url:
            continue
        title = _clean_md_title(title)
        if "airco" in title.lower() or "aircondition" in title.lower():
            continue
        key = url.split("?")[0]
        if key in seen:
            continue
        seen.add(key)
        out.append(product(rank=0, title=title or key, url=key))
    return out


def parse_etos_jina(text: str) -> list[dict]:
    out: list[dict] = []
    seen: set[str] = set()
    for title, url in _md_links(text):
        if "/producten/" not in url:
            continue
        title = _clean_md_title(title)
        if len(title) < 5:
            title = url.rstrip(".html").split("/")[-1].replace("-", " ")
        key = url.split("?")[0]
        if key in seen:
            continue
        seen.add(key)
        out.append(product(rank=0, title=title, url=key))
    if out:
        return out
    return parse_generic_jina(text, domain="etos.nl")


def parse_plus_jina(text: str) -> list[dict]:
    out = parse_generic_jina(text, domain="plus.nl")
    # Plus often JS-rendered; also accept AH-like product paths if present
    if out:
        return out
    for title, url in _md_links(text):
        if "plus.nl" not in url:
            continue
        if "/product" not in url and "/p/" not in url:
            continue
        out.append(product(rank=0, title=_clean_md_title(title) or url, url=url))
    return out


def parse_dirk_jina(text: str) -> list[dict]:
    return parse_generic_jina(text, domain="dirk.nl")


def parse_plein_jina(text: str) -> list[dict]:
    out: list[dict] = []
    seen: set[str] = set()
    for title, url in _md_links(text):
        if "plein.nl" not in url:
            continue
        # product detail pages are usually /slug without /drogisterij category
        if url.rstrip("/").count("/") < 3:
            continue
        if any(x in url for x in ("/drogisterij/", "/beauty/", "/klantenservice", "/profile", "/catalogsearch")):
            if not re.search(r"conditioner", title, re.I):
                continue
        title = _clean_md_title(title)
        if "conditioner" not in title.lower() and "syoss" not in title.lower():
            # keep product-looking slugs
            if not re.search(r"conditioner|syoss|gliss", url, re.I):
                continue
        key = url.split("?")[0]
        if key in seen or key.rstrip("/") in {"https://www.plein.nl", "https://plein.nl"}:
            continue
        seen.add(key)
        out.append(product(rank=0, title=title or key, url=key))
    return out


def parse_generic_jina(text: str, domain: str = "") -> list[dict]:
    out: list[dict] = []
    seen: set[str] = set()
    for title, url in _md_links(text):
        if domain and domain not in url:
            continue
        title = _clean_md_title(title)
        low = (title + " " + url).lower()
        if "airco" in low or "aircondition" in low:
            continue
        if not any(
            k in low
            for k in (
                "conditioner",
                "condicioner",
                "crèmespoeling",
                "cremespoeling",
                "haarbalsem",
                "syoss",
                "gliss",
                "schwarzkopf",
                "/p/",
                "/product",
                "/dp/",
            )
        ):
            continue
        if len(title) < 4:
            continue
        # skip pure nav labels
        if title.casefold() in {"conditioner", "leave-in conditioner", "producten", "zoeken"}:
            continue
        key = url.split("?")[0]
        if key in seen:
            continue
        seen.add(key)
        out.append(product(rank=0, title=title, url=key))
    if out:
        return out
    for name in re.findall(r"Image\s+\d+:\s*([^\]\|\n]+)", text):
        name = _clean_md_title(name)
        if "conditioner" in name.lower() or "syoss" in name.lower() or "gliss" in name.lower():
            key = name.casefold()
            if key in seen:
                continue
            seen.add(key)
            out.append(product(rank=0, title=name))
    return out


PARSERS = {
    "amazon": parse_amazon,
    "dod": parse_dod,
    "ah_jina": parse_ah_jina,
    "jumbo_jina": parse_jumbo_jina,
    "kruidvat_jina": parse_kruidvat_jina,
    "trekpleister_jina": parse_trekpleister_jina,
    "koopjes_jina": parse_koopjes_jina,
    "notino_jina": parse_notino_jina,
    "da_jina": parse_da_jina,
    "bol_jina": parse_bol_jina,
    "etos_jina": parse_etos_jina,
    "plus_jina": parse_plus_jina,
    "dirk_jina": parse_dirk_jina,
    "plein_jina": parse_plein_jina,
    "generic_jina": parse_generic_jina,
}


def parse_body(parser: str, body: str, domain: str) -> list[dict]:
    fn = PARSERS.get(parser)
    if parser == "generic_jina":
        return parse_generic_jina(body, domain=domain)
    if fn is None:
        return parse_generic_jina(body, domain=domain)
    # parsers with domain arg
    if parser in {"generic_jina"}:
        return fn(body, domain=domain)  # type: ignore[misc]
    return fn(body)
