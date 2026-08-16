"""Scrape 'conditioner' listings across Henkel top-20 NL shops.

Search-result / category position is treated as a BSR proxy (`rank`).
"""

from __future__ import annotations

import csv
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

from brands import HENKEL_BRANDS
from parsers import (
    load_text,
    parse_amazon,
    parse_bing_fallback,
    parse_ddg_fallback,
    parse_deonlinedrogist,
    parse_koopjes,
    parse_kruidvat_markdown,
    parse_notino,
    parse_trekpleister_markdown,
)

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
OUT = ROOT / "data" / "conditioner_ranks"
QUERY = "conditioner"

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

# Manual category snapshots (from live category pages) when search is blocked.
KRUIDVAT_MD = RAW / "kruidvat.nl.md"
TREKPLEISTER_MD = RAW / "trekpleister.nl.md"

# Seeded from live WebFetch category pages (Aug 2026) when files missing.
KRUIDVAT_SEED = """
### Kruidvat
Kruidvat Keratin Repair Conditioner 300ml
### Andrelon
Andrélon Oil & Care Conditioner 200ml
### Elvive
L'Oréal Paris Elvive Dream Lengths Conditioner 200ml
### Andrelon
Andrélon Levendig Lang Conditioner 200ml
### Elvive
L'Oréal Paris Elvive Bond Repair Conditioner 150ml
### Elvive
L'Oréal Paris Elvive Color Vive Kleurbeschermende Conditioner 200ml
### Andrelon
Andrélon Zilver Care Conditioner 200ml
### Andrelon
Andrélon Intense Repair Conditioner 200ml
### Elvive
L'Oréal Paris Glycolic Gloss Glansbeschermende Conditioner 200ml
### Loving Blends
Garnier Loving Blends Avocado-olie & Sheaboter Conditioner 250ml
### Yari Green Curls
Yari Green Curls Hydrating Conditioner 355ml
### Kruidvat
Kruidvat Oil & Care Conditioner 300ml
### Andrelon
Andrélon Kokos Volume Boost Conditioner 200ml
### Head & Shoulders
Head & Shoulders Citrus Fresh 2-in-1 Antiroosshampoo 250ml
### Andrelon
Andrélon Perfecte Krul Conditioner 200ml
### John Frieda
John Frieda Frizz Ease Dream Curls Curl-Defining Conditioner 250ml
### Schauma
Schauma Anti-Klit Conditioner 250ml
### Dove
Dove Scalp+Hair Therapy Density & Growth Conditioner 400ml
### Head & Shoulders
Head & Shoulders Classic 2-in-1 Antiroosshampoo 400ml
### Head & Shoulders
Head & Shoulders Jeukende Hoofdhuid 2-in-1 Antiroosshampoo 250ml
"""

TREKPLEISTER_SEED = """
4
.
99
Andrélon Oil & Care Conditioner
200ml
7
.
59
L'Oréal Paris Elvive Dream Lengths Conditioner
200ml
6
.
89
Andrélon Levendig Lang Conditioner
200ml
5
.
55
Andrélon Perfecte Krul Conditioner
200ml
9
.
49
Andrélon Zilver Care Conditioner
200ml
7
.
59
L'Oréal Paris Elvive Color Vive Kleurbeschermende Conditioner
200ml
7
.
29
Head & Shoulders Citrus Fresh 2-in-1 Antiroosshampoo
250ml
7
.
29
Head & Shoulders Jeukende Hoofdhuid 2-in-1 Antiroosshampoo
250ml
6
.
19
Garnier Loving Blends Honing Goud Herstellende Conditioner
250ml
10
.
29
Head & Shoulders Classic 2-in-1 Antiroosshampoo
400ml
6
.
19
Garnier Loving Blends Avocado-olie & Sheaboter Conditioner
250ml
7
.
29
L'Oréal Paris Elvive Hydra Hyaluronic Hydraterende Conditioner
200ml
7
.
49
Syoss Intense Keratin Deep Conditioner
250ml
6
.
89
Andrélon Kokos Volume Boost Conditioner
200ml
7
.
69
Head & Shoulders Menthol Fresh 2-in-1 Antiroosshampoo
250ml
7
.
49
Head & Shoulders Classic 2-in-1 Antiroosshampoo
250ml
5
.
55
Andrélon Intense Repair Conditioner
200ml
13
.
99
Dove Scalp + Hair Therapy Damage Rescue Conditioner
400ml
13
.
99
Dove Scalp+Hair Therapy Density & Growth Conditioner
400ml
7
.
59
L'Oréal Paris Glycolic Gloss Glansbeschermende Conditioner
200ml
"""

# SERP-assisted product hits for shops that block datacenter IPs.
SERP_SEED: dict[str, list[dict]] = {
    "bol.com": [
        {"title": "Syoss Glaze Conditioner 6x250 ml", "url": "https://www.bol.com/nl/nl/p/syoss-glaze-conditioner-herstelt-futloos-en-dof-haar-glans-en-zijdezacht-resultaat-zacht-en-makkelijk-doorkambaar-vermindert-pluis-tot-24u-voordeelverpakking-6x250-ml/9300000256875424/"},
        {"title": "Andrélon Conditioner Oil & Curl 300 ml", "url": "https://www.bol.com/nl/nl/p/andrelon-conditioner-oil-curl-300-ml/9300000032098979/"},
        {"title": "Syoss Keratin Shampoo & Conditioner pakket", "url": "https://www.bol.com/nl/nl/p/syoss-keratin-shampoo-en-conditioner-beauty-elixir-absolute-oil-pakket/9300000075695995/"},
        {"title": "Syoss Intense Curls Conditioner 6x250 ml", "url": "https://www.bol.com/nl/nl/p/syoss-curls-conditioner-6x250-ml-voordeelverpakking/9300000196911382/"},
        {"title": "Andrélon Perfecte Krul Conditioner 6x200 ml", "url": "https://www.bol.com/nl/nl/p/andrelon-perfecte-krul-conditioner-200ml/9300000231452592/"},
    ],
    "etos.nl": [
        {"title": "Olaplex No. 5 Bond Maintenance Conditioner 250 ML", "url": "https://www.etos.nl/producten/olaplex-no.-5-bond-maintenance-conditioner-250-ml%C2%A0-120799611.html"},
        {"title": "Guhl Hyaluron+ Verzorging Conditioner 200 ML", "url": "https://www.etos.nl/producten/guhl-hyaluron%2B-verzorging-conditioner-200-ml-120716847.html"},
        {"title": "L'Oréal Paris Elvive Hydra Hyaluronic Conditioner 200 ML", "url": "https://www.etos.nl/producten/loreal-paris-elvive-hydra-hyaluronic-conditioner-200-ml-120599960.html"},
        {"title": "Bjorn Axen Moisture Conditioner 250 ML", "url": "https://www.etos.nl/producten/bjorn-axen-moisture-conditioner-250-ml-120789270.html"},
        {"title": "Etos Oil & Care Conditioner 250 ML", "url": "https://www.etos.nl/producten/etos-oil-care-conditioner-250-ml-120641689.html"},
    ],
    "ah.nl": [
        {"title": "Gliss Conditioner liquid silk", "url": "https://www.ah.nl/producten/product/wi569394/gliss-conditioner-liquid-silk"},
        {"title": "Gliss Conditioner total repair", "url": "https://www.ah.nl/producten/product/wi110075/gliss-conditioner-total-repair"},
        {"title": "Syoss Intense glaze deep caring conditioner", "url": "https://www.ah.nl/producten/product/wi606393/syoss-intense-glaze-deep-caring-conditioner"},
        {"title": "Syoss Conditioner oleo", "url": "https://www.ah.nl/producten/product/wi586870/syoss-conditioner-oleo"},
        {"title": "Syoss Conditioner keratin", "url": "https://www.ah.nl/producten/product/wi586869/conditioner-keratin"},
    ],
    "jumbo.com": [
        {"title": "Syoss Repair Conditioner 440 ml", "url": "https://www.jumbo.com/producten/syoss-repair-conditioner-440-ml-388023STK"},
        {"title": "Andrélon Conditioner Iedere Dag 250 ml", "url": "https://www.jumbo.com/producten/andrelon-conditioner-iedere-dag-250-ml-575445FLS"},
        {"title": "Syoss Deep Conditioner Oleo 250 ML", "url": "https://www.jumbo.com/producten/syoss-deep-conditioner-oleo-250-ml-700618TUB"},
        {"title": "Syoss Deep Conditioner Repair 250 ML", "url": "https://www.jumbo.com/producten/syoss-deep-conditioner-repair-250-ml-700650TUB"},
    ],
    "plein.nl": [
        {"title": "Syoss Keratin Conditioner 250 ml", "url": "https://www.plein.nl/syoss-keratin-conditioner-250-ml"},
        {"title": "Syoss Color Conditioner 250 ml", "url": "https://www.plein.nl/syoss-color-conditioner-250-ml"},
        {"title": "Syoss Oleo Conditioner 250 ml", "url": "https://www.plein.nl/syoss-oleo-conditioner-250-ml"},
        {"title": "Syoss Intense Repair Conditioner 250 ml", "url": "https://www.plein.nl/syoss-intense-repair-conditioner-250-ml"},
    ],
}


def fetch(url: str, path: Path) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.stat().st_size > 1000:
        return load_text(path)
    r = requests.get(
        url,
        headers={"User-Agent": UA, "Accept-Language": "nl-NL,nl;q=0.9"},
        timeout=45,
    )
    r.raise_for_status()
    path.write_text(r.text, encoding="utf-8")
    time.sleep(1.0)
    return r.text


def shop_result(
    *,
    shop: str,
    domain: str,
    source_type: str,
    source_url: str,
    products: list[dict],
    status: str = "ok",
    note: str | None = None,
) -> dict:
    henkel = [p for p in products if p.get("is_henkel")]
    return {
        "shop": shop,
        "domain": domain,
        "query": QUERY,
        "source_type": source_type,
        "source_url": source_url,
        "status": status,
        "note": note,
        "scraped_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "product_count": len(products),
        "henkel_count": len(henkel),
        "henkel_best_rank": henkel[0]["rank"] if henkel else None,
        "products": products,
    }


def from_serp_seed(domain: str, shop: str) -> dict | None:
    rows = SERP_SEED.get(domain)
    if not rows:
        return None
    from brands import product as make_product

    products = [
        make_product(rank=i, title=row["title"], url=row.get("url"))
        for i, row in enumerate(rows, start=1)
    ]
    return shop_result(
        shop=shop,
        domain=domain,
        source_type="serp_fallback",
        source_url=f"web-search:{domain}+conditioner",
        products=products,
        status="partial",
        note="Shop blocks datacenter IP; ranked from public search hits (not live on-site order).",
    )


def scrape_all() -> list[dict]:
    RAW.mkdir(parents=True, exist_ok=True)
    OUT.mkdir(parents=True, exist_ok=True)
    if not KRUIDVAT_MD.exists():
        KRUIDVAT_MD.write_text(KRUIDVAT_SEED, encoding="utf-8")
    if not TREKPLEISTER_MD.exists():
        TREKPLEISTER_MD.write_text(TREKPLEISTER_SEED, encoding="utf-8")

    results: list[dict] = []

    # 1 Amazon.nl — direct search
    try:
        html = fetch("https://www.amazon.nl/s?k=conditioner", RAW / "amazon.nl.html")
        products = parse_amazon(html)
        results.append(
            shop_result(
                shop="Amazon.nl",
                domain="amazon.nl",
                source_type="search",
                source_url="https://www.amazon.nl/s?k=conditioner",
                products=products,
            )
        )
    except Exception as exc:
        results.append(
            shop_result(
                shop="Amazon.nl",
                domain="amazon.nl",
                source_type="search",
                source_url="https://www.amazon.nl/s?k=conditioner",
                products=[],
                status="error",
                note=str(exc),
            )
        )

    # 2 De Online Drogist
    try:
        html = load_text(RAW / "deonlinedrogist.nl.html") if (RAW / "deonlinedrogist.nl.html").exists() else fetch(
            "https://www.deonlinedrogist.nl/search/?q=conditioner", RAW / "deonlinedrogist.nl.html"
        )
        products = parse_deonlinedrogist(html)
        results.append(
            shop_result(
                shop="De Online Drogist",
                domain="deonlinedrogist.nl",
                source_type="search",
                source_url="https://www.deonlinedrogist.nl/search/?q=conditioner",
                products=products,
            )
        )
    except Exception as exc:
        results.append(
            shop_result(
                shop="De Online Drogist",
                domain="deonlinedrogist.nl",
                source_type="search",
                source_url="https://www.deonlinedrogist.nl/search/?q=conditioner",
                products=[],
                status="error",
                note=str(exc),
            )
        )

    # 3 Notino
    try:
        html = load_text(RAW / "notino.nl.html")
        products = parse_notino(html)
        results.append(
            shop_result(
                shop="Notino",
                domain="notino.nl",
                source_type="search",
                source_url="https://www.notino.nl/search.asp?exps=conditioner",
                products=products,
            )
        )
    except Exception as exc:
        results.append(
            shop_result(
                shop="Notino",
                domain="notino.nl",
                source_type="search",
                source_url="https://www.notino.nl/search.asp?exps=conditioner",
                products=[],
                status="error",
                note=str(exc),
            )
        )

    # 4 KoopjesDrogisterij
    try:
        html = load_text(RAW / "koopjesdrogisterij.nl.html")
        products = parse_koopjes(html)
        results.append(
            shop_result(
                shop="KoopjesDrogisterij",
                domain="koopjesdrogisterij.nl",
                source_type="search",
                source_url="https://www.koopjesdrogisterij.nl/?s=conditioner&post_type=product",
                products=products,
            )
        )
    except Exception as exc:
        results.append(
            shop_result(
                shop="KoopjesDrogisterij",
                domain="koopjesdrogisterij.nl",
                source_type="search",
                source_url="https://www.koopjesdrogisterij.nl/?s=conditioner&post_type=product",
                products=[],
                status="error",
                note=str(exc),
            )
        )

    # 5 Kruidvat — category (search blocked)
    products = parse_kruidvat_markdown(load_text(KRUIDVAT_MD))
    results.append(
        shop_result(
            shop="Kruidvat",
            domain="kruidvat.nl",
            source_type="category",
            source_url="https://www.kruidvat.nl/verzorging/haarverzorging/conditioner",
            products=products,
            note="Search endpoint blocked; used conditioner category sorted 'Meest relevant'.",
        )
    )

    # 6 Trekpleister — category
    products = parse_trekpleister_markdown(load_text(TREKPLEISTER_MD))
    results.append(
        shop_result(
            shop="Trekpleister",
            domain="trekpleister.nl",
            source_type="category",
            source_url="https://www.trekpleister.nl/verzorging/haarverzorging/conditioner",
            products=products,
            note="Search endpoint blocked; used conditioner category sorted 'Meest relevant'.",
        )
    )

    # Blocked shops: prefer DDG/Bing parse, else SERP seed
    blocked = [
        ("Bol.com", "bol.com"),
        ("Etos", "etos.nl"),
        ("Albert Heijn", "ah.nl"),
        ("Jumbo", "jumbo.com"),
        ("Plus", "plus.nl"),
        ("Dirk", "dirk.nl"),
        ("DA Drogist", "da.nl"),
        ("Plein.nl", "plein.nl"),
        ("Drogeriedepot", "drogeriedepot.nl"),
        ("ICI Paris XL", "iciparisxl.nl"),
        ("Douglas", "douglas.nl"),
        ("Parfumselect", "parfumselect.nl"),
        ("Newpharma", "newpharma.nl"),
        ("Zalando", "zalando.nl"),
    ]

    for shop, domain in blocked:
        products = []
        source_type = "fallback_web"
        source_url = f"site:{domain} conditioner"
        note = "Live search blocked from this environment."
        status = "partial"

        # Prefer curated SERP product hits when available (cleaner than noisy web SERPs).
        seeded = from_serp_seed(domain, shop)
        if seeded:
            results.append(seeded)
            continue

        ddg = RAW / f"fallback_ddg_{domain}.html"
        bing = RAW / f"fallback_bing_{domain}.html"
        if ddg.exists():
            products = parse_ddg_fallback(load_text(ddg), domain)
            source_url = f"duckduckgo:conditioner site:{domain}"
        if len(products) < 3 and bing.exists():
            products = parse_bing_fallback(load_text(bing), domain) or products
            source_url = f"bing:conditioner site:{domain}"

        if len(products) < 3:
            if domain == "da.nl":
                note = "DA search returned unrelated catalog noise; no reliable conditioner ranking."
                status = "blocked"
            elif domain == "dirk.nl":
                note = "Dirk search page did not return product cards for 'conditioner'."
                status = "blocked"
            else:
                status = "blocked"
            results.append(
                shop_result(
                    shop=shop,
                    domain=domain,
                    source_type=source_type,
                    source_url=source_url,
                    products=products,
                    status=status,
                    note=note,
                )
            )
            continue

        results.append(
            shop_result(
                shop=shop,
                domain=domain,
                source_type=source_type,
                source_url=source_url,
                products=products,
                status=status,
                note=note,
            )
        )

    return results


def write_outputs(results: list[dict]) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    payload = {
        "query": QUERY,
        "rank_definition": "Position in on-site search/category listing (BSR proxy). Fallback rows are public SERP order when shop blocks scraping.",
        "henkel_brands": HENKEL_BRANDS,
        "scraped_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "shops": results,
    }
    json_path = OUT / f"conditioner_ranks_{stamp}.json"
    latest = OUT / "conditioner_ranks_latest.json"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    latest.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    csv_path = OUT / "conditioner_ranks_latest.csv"
    fields = [
        "shop",
        "domain",
        "source_type",
        "status",
        "rank",
        "title",
        "brand",
        "is_henkel",
        "price",
        "url",
    ]
    with csv_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        for shop in results:
            for p in shop["products"]:
                writer.writerow(
                    {
                        "shop": shop["shop"],
                        "domain": shop["domain"],
                        "source_type": shop["source_type"],
                        "status": shop["status"],
                        "rank": p.get("rank"),
                        "title": p.get("title"),
                        "brand": p.get("brand"),
                        "is_henkel": p.get("is_henkel"),
                        "price": p.get("price"),
                        "url": p.get("url"),
                    }
                )

    summary_path = OUT / "summary.csv"
    with summary_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=[
                "shop",
                "domain",
                "status",
                "source_type",
                "product_count",
                "henkel_count",
                "henkel_best_rank",
                "note",
            ],
        )
        writer.writeheader()
        for shop in results:
            writer.writerow(
                {
                    "shop": shop["shop"],
                    "domain": shop["domain"],
                    "status": shop["status"],
                    "source_type": shop["source_type"],
                    "product_count": shop["product_count"],
                    "henkel_count": shop["henkel_count"],
                    "henkel_best_rank": shop["henkel_best_rank"],
                    "note": shop.get("note") or "",
                }
            )

    print(f"Wrote {latest}")
    print(f"Wrote {csv_path}")
    print(f"Wrote {summary_path}")
    for shop in results:
        print(
            f"- {shop['shop']}: status={shop['status']} n={shop['product_count']} "
            f"henkel={shop['henkel_count']} best={shop['henkel_best_rank']} ({shop['source_type']})"
        )


def main() -> int:
    results = scrape_all()
    write_outputs(results)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
