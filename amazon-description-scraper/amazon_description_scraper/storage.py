"""Serialize scrape results to JSON / CSV."""

from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import IO, Iterable, TextIO

from .models import ProductDescription

CSV_FIELDS = [
    "asin",
    "marketplace",
    "url",
    "title",
    "brand",
    "feature_bullets",
    "description",
    "aplus_text",
    "best_description",
    "meta_description",
    "provider",
    "source_bytes",
    "error",
]


def write_json(
    target: Path | str,
    products: Iterable[ProductDescription],
    *,
    marketplace: str,
    provider: str,
) -> None:
    items = list(products)
    payload = {
        "scraped_at": datetime.now(timezone.utc).isoformat(),
        "marketplace": marketplace,
        "provider": provider,
        "total": len(items),
        "products": [p.to_dict() for p in items],
    }
    Path(target).write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def write_csv(target: Path | str | TextIO, products: Iterable[ProductDescription]) -> None:
    close = False
    if isinstance(target, (str, Path)):
        handle: IO[str] = Path(target).open("w", encoding="utf-8", newline="")
        close = True
    else:
        handle = target

    try:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS, extrasaction="ignore")
        writer.writeheader()
        for product in products:
            row = product.to_dict()
            row["feature_bullets"] = " | ".join(product.feature_bullets)
            writer.writerow({k: row.get(k) for k in CSV_FIELDS})
    finally:
        if close:
            handle.close()
