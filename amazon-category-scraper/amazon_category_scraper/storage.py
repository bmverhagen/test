"""Write scrape reports to CSV, JSON, or plain text.

Two views are supported: the default aggregated brand view, and a per-product
view (``top`` products with rank, brand, and title) for best-seller style
questions like "top 10 with the brand of each product".
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path
from typing import IO

from .models import ProductEntry, ScrapeReport

__all__ = ["FORMATS", "write_report"]

FORMATS = ("csv", "json", "txt")


def _write_csv(report: ScrapeReport, stream: IO[str]) -> None:
    writer = csv.writer(stream)
    writer.writerow(["brand", "product_mentions", "sources"])
    for record in report.brands:
        writer.writerow([record.name, record.product_mentions, "|".join(record.sources)])


def _write_json(report: ScrapeReport, stream: IO[str]) -> None:
    data = report.to_dict()
    del data["products"]
    json.dump(data, stream, indent=2, ensure_ascii=False)
    stream.write("\n")


def _write_txt(report: ScrapeReport, stream: IO[str]) -> None:
    for record in report.brands:
        stream.write(f"{record.name}\n")


def _top_products(report: ScrapeReport, top: int) -> list[ProductEntry]:
    products = sorted(
        report.products, key=lambda product: product.rank if product.rank is not None else 10**9
    )
    return products[:top] if top > 0 else products


def _write_products_csv(products: list[ProductEntry], stream: IO[str]) -> None:
    writer = csv.writer(stream)
    writer.writerow(["rank", "brand", "title", "asin", "brand_source"])
    for product in products:
        writer.writerow(
            [product.rank, product.brand or "", product.title, product.asin or "", product.brand_source or ""]
        )


def _write_products_json(products: list[ProductEntry], stream: IO[str]) -> None:
    data = [
        {
            "rank": product.rank,
            "brand": product.brand,
            "title": product.title,
            "asin": product.asin,
            "brand_source": product.brand_source,
        }
        for product in products
    ]
    json.dump(data, stream, indent=2, ensure_ascii=False)
    stream.write("\n")


def _write_products_txt(products: list[ProductEntry], stream: IO[str]) -> None:
    for product in products:
        rank = f"#{product.rank}" if product.rank is not None else "-"
        stream.write(f"{rank}\t{product.brand or '?'}\t{product.title}\n")


_WRITERS = {"csv": _write_csv, "json": _write_json, "txt": _write_txt}
_PRODUCT_WRITERS = {
    "csv": _write_products_csv,
    "json": _write_products_json,
    "txt": _write_products_txt,
}


def write_report(report: ScrapeReport, output: Path | None, fmt: str, top: int | None = None) -> None:
    """Write *report* to *output* (or stdout when *output* is None).

    With ``top`` set, the per-product view is written (limited to the first
    *top* products by rank; 0 means all) instead of the aggregated brand view.
    """
    if fmt not in _WRITERS:
        raise ValueError(f"Unknown format {fmt!r}; expected one of {FORMATS}")

    def write(stream: IO[str]) -> None:
        if top is None:
            _WRITERS[fmt](report, stream)
        else:
            _PRODUCT_WRITERS[fmt](_top_products(report, top), stream)

    if output is None:
        write(sys.stdout)
    else:
        output.parent.mkdir(parents=True, exist_ok=True)
        with output.open("w", encoding="utf-8", newline="") as stream:
            write(stream)
