"""Write scrape reports to CSV, JSON, or plain text."""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path
from typing import IO

from .models import ScrapeReport

__all__ = ["FORMATS", "write_report"]

FORMATS = ("csv", "json", "txt")


def _write_csv(report: ScrapeReport, stream: IO[str]) -> None:
    writer = csv.writer(stream)
    writer.writerow(["brand", "product_mentions", "sources"])
    for record in report.brands:
        writer.writerow([record.name, record.product_mentions, "|".join(record.sources)])


def _write_json(report: ScrapeReport, stream: IO[str]) -> None:
    json.dump(report.to_dict(), stream, indent=2, ensure_ascii=False)
    stream.write("\n")


def _write_txt(report: ScrapeReport, stream: IO[str]) -> None:
    for record in report.brands:
        stream.write(f"{record.name}\n")


_WRITERS = {"csv": _write_csv, "json": _write_json, "txt": _write_txt}


def write_report(report: ScrapeReport, output: Path | None, fmt: str) -> None:
    """Write *report* to *output* (or stdout when *output* is None)."""
    if fmt not in _WRITERS:
        raise ValueError(f"Unknown format {fmt!r}; expected one of {FORMATS}")
    writer = _WRITERS[fmt]
    if output is None:
        writer(report, sys.stdout)
    else:
        output.parent.mkdir(parents=True, exist_ok=True)
        with output.open("w", encoding="utf-8", newline="") as stream:
            writer(report, stream)
