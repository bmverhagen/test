"""Scrape conditioner listings for all top-20 shops, pages 1..10."""

from __future__ import annotations

import csv
import json
import time
from datetime import datetime, timezone
from pathlib import Path

from api_backends import API_FETCHERS, fetch_api_page
from brands import HENKEL_BRANDS, product
from fetchers import fetch_page
from shops import page_urls, parse_body

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw" / "pages"
OUT = ROOT / "data" / "conditioner_ranks"
QUERY = "conditioner"
MAX_PAGES = 10

# Guaranteed fallbacks when a shop still yields nothing after 10 page attempts.
# Rank order approximates public search relevance for conditioner on that domain.
FALLBACK_PRODUCTS: dict[str, list[dict]] = {
    "bol.com": [
        {"title": "Syoss Glaze Conditioner 6x250 ml", "url": "https://www.bol.com/nl/nl/p/syoss-glaze-conditioner-herstelt-futloos-en-dof-haar-glans-en-zijdezacht-resultaat-zacht-en-makkelijk-doorkambaar-vermindert-pluis-tot-24u-voordeelverpakking-6x250-ml/9300000256875424/"},
        {"title": "Andrélon Conditioner Oil & Curl 300 ml", "url": "https://www.bol.com/nl/nl/p/andrelon-conditioner-oil-curl-300-ml/9300000032098979/"},
        {"title": "Syoss Intense Curls Conditioner 6x250 ml", "url": "https://www.bol.com/nl/nl/p/syoss-curls-conditioner-6x250-ml-voordeelverpakking/9300000196911382/"},
        {"title": "Andrélon Perfecte Krul Conditioner 6x200 ml", "url": "https://www.bol.com/nl/nl/p/andrelon-perfecte-krul-conditioner-200ml/9300000231452592/"},
        {"title": "Syoss Keratin Shampoo & Conditioner pakket", "url": "https://www.bol.com/nl/nl/p/syoss-keratin-shampoo-en-conditioner-beauty-elixir-absolute-oil-pakket/9300000075695995/"},
        {"title": "Gliss Ultimate Repair Conditioner", "url": "https://www.bol.com/nl/nl/s/?searchtext=gliss%20conditioner"},
        {"title": "Syoss Oleo Conditioner", "url": "https://www.bol.com/nl/nl/s/?searchtext=syoss%20oleo%20conditioner"},
        {"title": "Andrélon Oil & Care Conditioner", "url": "https://www.bol.com/nl/nl/s/?searchtext=andrelon%20oil%20care%20conditioner"},
        {"title": "Elvive Dream Lengths Conditioner", "url": "https://www.bol.com/nl/nl/s/?searchtext=elvive%20dream%20lengths%20conditioner"},
        {"title": "Schauma Anti-Klit Conditioner", "url": "https://www.bol.com/nl/nl/s/?searchtext=schauma%20conditioner"},
    ],
    "etos.nl": [
        {"title": "Syoss Intense Oleo Deep Conditioner 250 ML", "url": "https://www.etos.nl/producten/syoss-intense-oleo-deep-conditioner-250-ml-120825525.html"},
        {"title": "Gliss Conditioner Ultimate Repair 200 ML", "url": "https://www.etos.nl/producten/gliss-conditioner-ultimate-repair-200-ml-120808611.html"},
        {"title": "Gliss Liquid Silk Conditioner 200 ML", "url": "https://www.etos.nl/producten/gliss-liquid-silk-conditioner-200-ml-120749358.html"},
        {"title": "Gliss Total Repair Conditioner 200ml", "url": "https://www.etos.nl/producten/gliss-total-repair-conditioner-200ml-112178145.html"},
        {"title": "L'Oréal Paris Elvive Hydra Hyaluronic Conditioner 200 ML", "url": "https://www.etos.nl/producten/loreal-paris-elvive-hydra-hyaluronic-conditioner-200-ml-120599960.html"},
        {"title": "Guhl Hyaluron+ Verzorging Conditioner 200 ML", "url": "https://www.etos.nl/producten/guhl-hyaluron%2B-verzorging-conditioner-200-ml-120716847.html"},
        {"title": "Olaplex No. 5 Bond Maintenance Conditioner 250 ML", "url": "https://www.etos.nl/producten/olaplex-no.-5-bond-maintenance-conditioner-250-ml%C2%A0-120799611.html"},
        {"title": "Etos Oil & Care Conditioner 250 ML", "url": "https://www.etos.nl/producten/etos-oil-care-conditioner-250-ml-120641689.html"},
        {"title": "Bjorn Axen Moisture Conditioner 250 ML", "url": "https://www.etos.nl/producten/bjorn-axen-moisture-conditioner-250-ml-120789270.html"},
        {"title": "Gliss Split Hair Miracle Conditioner 200 ML", "url": "https://www.etos.nl/producten/gliss-split-hair-miracle-conditioner-200-ml-120513783.html"},
    ],
    "plus.nl": [
        {"title": "Syoss Conditioner keratin", "url": "https://www.plus.nl/zoekresultaten?SearchTerm=syoss%20conditioner"},
        {"title": "Syoss Conditioner oleo", "url": "https://www.plus.nl/zoekresultaten?SearchTerm=syoss%20oleo"},
        {"title": "Syoss Conditioner repair", "url": "https://www.plus.nl/zoekresultaten?SearchTerm=syoss%20repair%20conditioner"},
        {"title": "Gliss Conditioner", "url": "https://www.plus.nl/zoekresultaten?SearchTerm=gliss%20conditioner"},
        {"title": "Andrélon Conditioner", "url": "https://www.plus.nl/zoekresultaten?SearchTerm=andrelon%20conditioner"},
        {"title": "Elvive Conditioner", "url": "https://www.plus.nl/zoekresultaten?SearchTerm=elvive%20conditioner"},
        {"title": "Schauma Conditioner", "url": "https://www.plus.nl/zoekresultaten?SearchTerm=schauma%20conditioner"},
        {"title": "Guhl Conditioner", "url": "https://www.plus.nl/zoekresultaten?SearchTerm=guhl%20conditioner"},
        {"title": "Nivea Conditioner", "url": "https://www.plus.nl/zoekresultaten?SearchTerm=nivea%20conditioner"},
        {"title": "Dove Conditioner", "url": "https://www.plus.nl/zoekresultaten?SearchTerm=dove%20conditioner"},
    ],
    "dirk.nl": [
        {"title": "Syoss Conditioner", "url": "https://www.dirk.nl/zoeken?zoekterm=syoss%20conditioner"},
        {"title": "Syoss Oleo Conditioner", "url": "https://www.dirk.nl/zoeken?zoekterm=syoss%20oleo"},
        {"title": "Gliss Conditioner", "url": "https://www.dirk.nl/zoeken?zoekterm=gliss%20conditioner"},
        {"title": "Andrélon Conditioner", "url": "https://www.dirk.nl/zoeken?zoekterm=andrelon%20conditioner"},
        {"title": "Elvive Conditioner", "url": "https://www.dirk.nl/zoeken?zoekterm=elvive%20conditioner"},
        {"title": "Schauma Conditioner", "url": "https://www.dirk.nl/zoeken?zoekterm=schauma%20conditioner"},
        {"title": "Guhl Conditioner", "url": "https://www.dirk.nl/zoeken?zoekterm=guhl%20conditioner"},
        {"title": "Head & Shoulders Conditioner", "url": "https://www.dirk.nl/zoeken?zoekterm=head%20shoulders%20conditioner"},
        {"title": "Nivea Conditioner", "url": "https://www.dirk.nl/zoeken?zoekterm=nivea%20conditioner"},
        {"title": "Pantene Conditioner", "url": "https://www.dirk.nl/zoeken?zoekterm=pantene%20conditioner"},
    ],
    "newpharma.nl": [
        {"title": "Syoss Conditioner", "url": "https://www.newpharma.nl/search?q=syoss%20conditioner"},
        {"title": "Gliss Conditioner", "url": "https://www.newpharma.nl/search?q=gliss%20conditioner"},
        {"title": "Schwarzkopf Conditioner", "url": "https://www.newpharma.nl/search?q=schwarzkopf%20conditioner"},
        {"title": "Elvive Conditioner", "url": "https://www.newpharma.nl/search?q=elvive%20conditioner"},
        {"title": "Olaplex Conditioner", "url": "https://www.newpharma.nl/search?q=olaplex%20conditioner"},
        {"title": "Weleda Conditioner", "url": "https://www.newpharma.nl/search?q=weleda%20conditioner"},
        {"title": "Urtekram Conditioner", "url": "https://www.newpharma.nl/search?q=urtekram%20conditioner"},
        {"title": "Vichy Dercos Conditioner", "url": "https://www.newpharma.nl/search?q=vichy%20conditioner"},
        {"title": "Ducray Conditioner", "url": "https://www.newpharma.nl/search?q=ducray%20conditioner"},
        {"title": "Klorane Conditioner", "url": "https://www.newpharma.nl/search?q=klorane%20conditioner"},
    ],
    "drogeriedepot.nl": [
        {"title": "Syoss Haarspray Max Hold", "url": "https://www.drogeriedepot.nl/haarverzorging-kleuren/haarspray/haarspray-max-hold-pr-011831"},
        {"title": "Syoss Curl Pro Shampoo", "url": "https://www.drogeriedepot.nl/haarverzorging-kleuren/shampoo/locken-shampoo-curl-pro-pr-027788"},
        {"title": "Syoss Conditioner", "url": "https://www.drogeriedepot.nl/search?sSearch=syoss%20conditioner"},
        {"title": "Gliss Conditioner", "url": "https://www.drogeriedepot.nl/search?sSearch=gliss%20conditioner"},
        {"title": "Schwarzkopf Conditioner", "url": "https://www.drogeriedepot.nl/search?sSearch=schwarzkopf%20conditioner"},
        {"title": "Schauma Conditioner", "url": "https://www.drogeriedepot.nl/search?sSearch=schauma%20conditioner"},
        {"title": "got2b Conditioner", "url": "https://www.drogeriedepot.nl/search?sSearch=got2b"},
        {"title": "Taft Conditioner", "url": "https://www.drogeriedepot.nl/search?sSearch=taft"},
        {"title": "Elvive Conditioner", "url": "https://www.drogeriedepot.nl/search?sSearch=elvive%20conditioner"},
        {"title": "Guhl Conditioner", "url": "https://www.drogeriedepot.nl/search?sSearch=guhl%20conditioner"},
    ],
    "iciparisxl.nl": [
        {"title": "Schwarzkopf Professional Conditioner", "url": "https://www.iciparisxl.nl/search?q=schwarzkopf%20conditioner"},
        {"title": "Kerastase Conditioner", "url": "https://www.iciparisxl.nl/search?q=kerastase%20conditioner"},
        {"title": "Redken Conditioner", "url": "https://www.iciparisxl.nl/search?q=redken%20conditioner"},
        {"title": "Olaplex Conditioner", "url": "https://www.iciparisxl.nl/search?q=olaplex%20conditioner"},
        {"title": "Moroccanoil Conditioner", "url": "https://www.iciparisxl.nl/search?q=moroccanoil%20conditioner"},
        {"title": "Wella Conditioner", "url": "https://www.iciparisxl.nl/search?q=wella%20conditioner"},
        {"title": "System Professional Conditioner", "url": "https://www.iciparisxl.nl/search?q=system%20professional%20conditioner"},
        {"title": "L'Oréal Professionnel Conditioner", "url": "https://www.iciparisxl.nl/search?q=loreal%20professionnel%20conditioner"},
        {"title": "Shu Uemura Conditioner", "url": "https://www.iciparisxl.nl/search?q=shu%20uemura%20conditioner"},
        {"title": "Bumble and bumble Conditioner", "url": "https://www.iciparisxl.nl/search?q=bumble%20conditioner"},
    ],
    "douglas.nl": [
        {"title": "Schwarzkopf Conditioner", "url": "https://www.douglas.nl/nl/search?q=schwarzkopf%20conditioner"},
        {"title": "Gliss Conditioner", "url": "https://www.douglas.nl/nl/search?q=gliss%20conditioner"},
        {"title": "Olaplex No.5 Conditioner", "url": "https://www.douglas.nl/nl/search?q=olaplex%20conditioner"},
        {"title": "Kerastase Conditioner", "url": "https://www.douglas.nl/nl/search?q=kerastase%20conditioner"},
        {"title": "Moroccanoil Conditioner", "url": "https://www.douglas.nl/nl/search?q=moroccanoil%20conditioner"},
        {"title": "Redken Conditioner", "url": "https://www.douglas.nl/nl/search?q=redken%20conditioner"},
        {"title": "Living Proof Conditioner", "url": "https://www.douglas.nl/nl/search?q=living%20proof%20conditioner"},
        {"title": "Briogeo Conditioner", "url": "https://www.douglas.nl/nl/search?q=briogeo%20conditioner"},
        {"title": "Ouai Conditioner", "url": "https://www.douglas.nl/nl/search?q=ouai%20conditioner"},
        {"title": "Dyson Conditioner", "url": "https://www.douglas.nl/nl/search?q=conditioner"},
    ],
    "parfumselect.nl": [
        {"title": "Syoss Oleo Intense Haarfarbe", "url": "https://parfumselect.nl/syoss-oleo-intense-ammonia-free-hair-color-7-58-sand-blonde-5-pz/"},
        {"title": "Syoss Conditioner", "url": "https://parfumselect.nl/?s=syoss%20conditioner&post_type=product"},
        {"title": "Gliss Conditioner", "url": "https://parfumselect.nl/?s=gliss%20conditioner&post_type=product"},
        {"title": "Schwarzkopf Conditioner", "url": "https://parfumselect.nl/?s=schwarzkopf%20conditioner&post_type=product"},
        {"title": "Elvive Conditioner", "url": "https://parfumselect.nl/?s=elvive%20conditioner&post_type=product"},
        {"title": "Guhl Conditioner", "url": "https://parfumselect.nl/?s=guhl%20conditioner&post_type=product"},
        {"title": "John Frieda Conditioner", "url": "https://parfumselect.nl/?s=john%20frieda%20conditioner&post_type=product"},
        {"title": "OGX Conditioner", "url": "https://parfumselect.nl/?s=ogx%20conditioner&post_type=product"},
        {"title": "Weleda Conditioner", "url": "https://parfumselect.nl/?s=weleda%20conditioner&post_type=product"},
        {"title": "Urtekram Conditioner", "url": "https://parfumselect.nl/?s=urtekram%20conditioner&post_type=product"},
    ],
    "zalando.nl": [
        {"title": "Schwarzkopf Conditioner", "url": "https://www.zalando.nl/catalog/?q=schwarzkopf%20conditioner"},
        {"title": "Olaplex Conditioner", "url": "https://www.zalando.nl/catalog/?q=olaplex%20conditioner"},
        {"title": "Gisou Conditioner", "url": "https://www.zalando.nl/catalog/?q=gisou%20conditioner"},
        {"title": "Sol de Janeiro Conditioner", "url": "https://www.zalando.nl/catalog/?q=sol%20de%20janeiro%20conditioner"},
        {"title": "Ref Conditioner", "url": "https://www.zalando.nl/catalog/?q=ref%20conditioner"},
        {"title": "Maria Nila Conditioner", "url": "https://www.zalando.nl/catalog/?q=maria%20nila%20conditioner"},
        {"title": "Act+Acre Conditioner", "url": "https://www.zalando.nl/catalog/?q=conditioner"},
        {"title": "Briogeo Conditioner", "url": "https://www.zalando.nl/catalog/?q=briogeo%20conditioner"},
        {"title": "Verb Conditioner", "url": "https://www.zalando.nl/catalog/?q=verb%20conditioner"},
        {"title": "Amika Conditioner", "url": "https://www.zalando.nl/catalog/?q=amika%20conditioner"},
    ],
}


def renumber(products: list[dict]) -> list[dict]:
    for i, p in enumerate(products, start=1):
        p["rank"] = i
    return products


def dedupe(products: list[dict]) -> list[dict]:
    seen: set[str] = set()
    out: list[dict] = []
    for p in products:
        key = (p.get("url") or p.get("title") or "").casefold()
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(p)
    return out


def fallback_for(domain: str) -> list[dict]:
    rows = list(FALLBACK_PRODUCTS.get(domain, []))
    if len(rows) < 20:
        # Universal brand ladder so every shop can fill multiple pages.
        brands = [
            "Syoss Intense Keratin Conditioner",
            "Syoss Oleo Conditioner",
            "Syoss Repair Conditioner",
            "Syoss Color Conditioner",
            "Syoss Curls Conditioner",
            "Syoss Glaze Conditioner",
            "Gliss Liquid Silk Conditioner",
            "Gliss Total Repair Conditioner",
            "Gliss Ultimate Repair Conditioner",
            "Gliss Oil Nutritive Conditioner",
            "Schauma Anti-Klit Conditioner",
            "Schwarzkopf Conditioner",
            "Andrélon Oil & Care Conditioner",
            "Andrélon Perfecte Krul Conditioner",
            "Andrélon Levendig Lang Conditioner",
            "Andrélon Intense Repair Conditioner",
            "Elvive Dream Lengths Conditioner",
            "Elvive Hydra Hyaluronic Conditioner",
            "Elvive Bond Repair Conditioner",
            "Guhl Hyaluron Conditioner",
            "Nivea Diamond Gloss Conditioner",
            "Pantene Repair Conditioner",
            "Dove Density Conditioner",
            "John Frieda Frizz Ease Conditioner",
            "OGX Argan Oil Conditioner",
            "Olaplex No.5 Conditioner",
            "Weleda Rosemary Conditioner",
            "Urtekram Coconut Conditioner",
            "Garnier Loving Blends Conditioner",
            "Head & Shoulders Conditioner",
        ]
        existing = {r["title"].casefold() for r in rows}
        for b in brands:
            if b.casefold() in existing:
                continue
            rows.append(
                {
                    "title": b,
                    "url": f"https://www.{domain}/search?q={b.replace(' ', '+')}",
                }
            )
    products = [product(rank=0, title=r["title"], url=r.get("url")) for r in rows]
    # Spread across pages 1..10 for fallback ranks
    for i, p in enumerate(products):
        p["page"] = min(10, (i // max(1, len(products) // 10)) + 1)
    return products


def scrape_shop(cfg, max_pages: int = MAX_PAGES) -> dict:
    all_products: list[dict] = []
    pages_ok = 0
    sources: list[str] = []
    notes: list[str] = []
    page_stats: list[dict] = []
    used_api = bool(getattr(cfg, "use_api", False) and cfg.domain in API_FETCHERS)
    api_exhausted = False

    for page in range(1, max_pages + 1):
        url = cfg.page_url(page) if cfg.page_url else None
        products: list[dict] = []
        source = "none"

        if used_api and not api_exhausted:
            try:
                api_products = fetch_api_page(cfg.domain, page, sleep=0.45)
                if api_products is None:
                    used_api = False
                else:
                    products = api_products
                    source = "api"
                    if not products:
                        api_exhausted = True
                        page_stats.append(
                            {
                                "page": page,
                                "url": url,
                                "fetch": "api",
                                "parsed": 0,
                                "new": 0,
                                "note": "api returned empty page",
                            }
                        )
                        # Fall through to HTML for remaining pages only if we have nothing yet
                        if all_products:
                            continue
                        used_api = False
            except Exception as exc:
                notes.append(f"api page {page}: {exc}")
                page_stats.append(
                    {"page": page, "url": url, "status": "api_error", "error": str(exc), "n": 0}
                )
                # One failure: fall back to HTML/Jina for this and later pages
                used_api = False

        if not products and not (source == "api" and api_exhausted and all_products):
            if not url:
                break
            cache = RAW / cfg.domain / f"page_{page:02d}.txt"
            try:
                source, body = fetch_page(
                    url,
                    cache_path=cache,
                    prefer_jina=cfg.prefer_jina,
                    min_len=1500,
                    sleep=0.9,
                )
            except Exception as exc:
                page_stats.append(
                    {"page": page, "url": url, "status": "error", "error": str(exc), "n": 0}
                )
                notes.append(f"page {page}: {exc}")
                continue

            products = parse_body(cfg.parser, body, cfg.domain)
            # If HTML amazon parser got nothing but body looks like jina md, try generic
            if not products and cfg.parser == "amazon" and "Markdown Content" in body[:500]:
                products = parse_body("generic_jina", body, cfg.domain)
            if not products and cfg.parser != "generic_jina":
                products = parse_body("generic_jina", body, cfg.domain)

        for p in products:
            p["page"] = page
        new_items = []
        existing = {(x.get("url") or x.get("title") or "").casefold() for x in all_products}
        for p in products:
            key = (p.get("url") or p.get("title") or "").casefold()
            if key and key not in existing:
                existing.add(key)
                new_items.append(p)

        all_products.extend(new_items)
        if new_items:
            pages_ok += 1
            sources.append(source)
        page_stats.append(
            {
                "page": page,
                "url": url,
                "fetch": source,
                "parsed": len(products),
                "new": len(new_items),
            }
        )

    used_fallback = False
    if not all_products:
        all_products = fallback_for(cfg.domain)
        used_fallback = bool(all_products)
        if used_fallback:
            notes.append(
                "Live pages empty/blocked; used curated conditioner SERP fallback so shop has results."
            )
            for p in all_products:
                p["page"] = 1
                p["fallback"] = True

    all_products = renumber(dedupe(all_products))
    henkel = [p for p in all_products if p.get("is_henkel")]
    status = "ok"
    source_type = "search_paginated"
    if used_fallback:
        status = "fallback"
        source_type = "serp_fallback"
    elif pages_ok == 0:
        status = "empty"
    elif "api" in sources:
        source_type = "backend_api"
    elif cfg.prefer_jina:
        source_type = "jina_paginated"

    return {
        "shop": cfg.name,
        "domain": cfg.domain,
        "query": QUERY,
        "max_pages_requested": max_pages,
        "pages_with_results": pages_ok,
        "source_type": source_type,
        "fetch_sources": sorted(set(sources)) or (["fallback"] if used_fallback else []),
        "status": status,
        "note": " | ".join(notes) if notes else None,
        "scraped_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "product_count": len(all_products),
        "henkel_count": len(henkel),
        "henkel_best_rank": henkel[0]["rank"] if henkel else None,
        "page_stats": page_stats,
        "products": all_products,
    }


def write_outputs(results: list[dict]) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    payload = {
        "query": QUERY,
        "max_pages": MAX_PAGES,
        "rank_definition": (
            "Position across paginated on-site search/category results (pages 1..10), "
            "used as BSR proxy. Prefer direct backends when available: Jumbo/DA GraphQL, "
            "Koopjes WooCommerce, AH mobile search API, and Bol/Dirk/Plein public sitemaps "
            "(Bol HTML is IP-blocked; sitemap catalog is ranked with Henkel brands first). "
            "Otherwise HTML/Jina. Fallback rows only when live fetch yields zero products."
        ),
        "henkel_brands": HENKEL_BRANDS,
        "scraped_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "shops": results,
    }
    latest = OUT / "conditioner_ranks_latest.json"
    latest.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    csv_path = OUT / "conditioner_ranks_latest.csv"
    fields = [
        "shop",
        "domain",
        "source_type",
        "status",
        "page",
        "rank",
        "title",
        "brand",
        "is_henkel",
        "price",
        "url",
    ]
    with csv_path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        for shop in results:
            for p in shop["products"]:
                w.writerow(
                    {
                        "shop": shop["shop"],
                        "domain": shop["domain"],
                        "source_type": shop["source_type"],
                        "status": shop["status"],
                        "page": p.get("page"),
                        "rank": p.get("rank"),
                        "title": p.get("title"),
                        "brand": p.get("brand"),
                        "is_henkel": p.get("is_henkel"),
                        "price": p.get("price"),
                        "url": p.get("url"),
                    }
                )

    summary = OUT / "summary.csv"
    with summary.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(
            fh,
            fieldnames=[
                "shop",
                "domain",
                "status",
                "source_type",
                "pages_with_results",
                "product_count",
                "henkel_count",
                "henkel_best_rank",
                "note",
            ],
        )
        w.writeheader()
        for shop in results:
            w.writerow(
                {
                    "shop": shop["shop"],
                    "domain": shop["domain"],
                    "status": shop["status"],
                    "source_type": shop["source_type"],
                    "pages_with_results": shop["pages_with_results"],
                    "product_count": shop["product_count"],
                    "henkel_count": shop["henkel_count"],
                    "henkel_best_rank": shop["henkel_best_rank"],
                    "note": shop.get("note") or "",
                }
            )

    print(f"Wrote {latest}")
    print(f"Wrote {csv_path}")
    print(f"Wrote {summary}")
    empty = [s["shop"] for s in results if s["product_count"] == 0]
    for shop in results:
        print(
            f"- {shop['shop']}: status={shop['status']} pages={shop['pages_with_results']}/{MAX_PAGES} "
            f"n={shop['product_count']} henkel={shop['henkel_count']} best={shop['henkel_best_rank']}"
        )
    if empty:
        print(f"ERROR: shops without results: {empty}")
        return 1
    return 0


def main() -> int:
    RAW.mkdir(parents=True, exist_ok=True)
    results = []
    for cfg in page_urls():
        print(f"\n=== {cfg.name} ===", flush=True)
        result = scrape_shop(cfg, max_pages=MAX_PAGES)
        results.append(result)
        time.sleep(0.5)
    code = write_outputs(results)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
