"""Serialize scrape reports to JSON, CSV, table or bookmarks."""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path
from typing import TextIO, Literal

from .bookmarks import write_bookmarks, write_bookmarks_markdown
from .models import SearchReport

FormatName = Literal["json", "csv", "table", "bookmarks", "bookmarks-md"]


def write_json(report: SearchReport, stream: TextIO) -> None:
    json.dump(report.to_dict(), stream, ensure_ascii=False, indent=2)
    stream.write("\n")


def write_csv(report: SearchReport, stream: TextIO) -> None:
    fieldnames = [
        "rank",
        "name",
        "location",
        "review_score",
        "review_count",
        "price_total",
        "price_per_night",
        "currency",
        "breakfast_included",
        "room_mentions_balcony",
        "balcony_source",
        "free_cancellation",
        "free_cancellation_until",
        "is_available",
        "room_name",
        "unit_id",
        "url",
    ]
    writer = csv.DictWriter(stream, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    for prop in report.properties:
        writer.writerow(prop.to_dict())


def write_table(report: SearchReport, stream: TextIO) -> None:
    max_price = (
        f"{report.query.max_total_price:g}"
        if report.query.max_total_price is not None
        else "∞"
    )
    stream.write(
        f"# {report.result_header or 'Booking.com resultaten'}\n"
        f"# Check-in {report.query.checkin} → check-out {report.query.checkout} "
        f"({report.query.nights} nachten)\n"
        f"# Filters: score>={report.query.min_review_score}, "
        f"totaal<={max_price} {report.query.currency}, "
        f"ontbijt={report.query.breakfast}, zwembad={report.query.swimming_pool}, "
        f"balkon={report.query.balcony}, terras={report.query.terrace}, "
        f"gratis_annuleren={report.query.free_cancellation}, "
        f"alleen_beschikbaar={report.query.available_only}\n"
        f"# nflt: {report.nflt or '(geen)'}\n"
        f"# Matches: {len(report.properties)} / {report.cards_seen} kaarten "
        f"({report.pages_scraped} pagina's)\n\n"
    )
    if not report.properties:
        stream.write("Geen accommodaties gevonden die aan alle criteria voldoen.\n")
        return

    for prop in report.properties:
        score = f"{prop.review_score:.1f}" if prop.review_score is not None else "?"
        total = f"€{prop.price_total:.0f}" if prop.price_total is not None else "?"
        night = (
            f"€{prop.price_per_night:.0f}/nacht"
            if prop.price_per_night is not None
            else ""
        )
        location = prop.location or "?"
        if prop.room_mentions_balcony:
            balcony = f"balkon ja ({prop.balcony_source or 'kamernaam'})"
        elif prop.balcony_source:
            balcony = f"balkon nee ({prop.balcony_source})"
        else:
            balcony = "balkon via filter"
        stream.write(
            f"{prop.rank or '-':>3}. {prop.name}\n"
            f"     {location} | score {score}"
            f"{f' ({prop.review_count} reviews)' if prop.review_count else ''}"
            f" | {total} totaal {night}\n"
            f"     {prop.room_name or 'kamer onbekend'} | ontbijt="
            f"{'ja' if prop.breakfast_included else 'nee'} | {balcony} | "
            f"annuleerbaar={'ja' if prop.free_cancellation else 'nee'} | "
            f"beschikbaar={'ja' if prop.is_available else 'nee'}\n"
            f"     {prop.url}\n\n"
        )


def write_report(
    report: SearchReport,
    *,
    output: Path | None = None,
    fmt: FormatName = "table",
) -> None:
    if output is None:
        stream: TextIO = sys.stdout
        _dispatch(report, stream, fmt)
        return

    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8", newline="") as stream:
        _dispatch(report, stream, fmt)


def _dispatch(report: SearchReport, stream: TextIO, fmt: FormatName) -> None:
    if fmt == "json":
        write_json(report, stream)
    elif fmt == "csv":
        write_csv(report, stream)
    elif fmt == "table":
        write_table(report, stream)
    elif fmt == "bookmarks":
        write_bookmarks(report, stream)
    elif fmt == "bookmarks-md":
        write_bookmarks_markdown(report, stream)
    else:  # pragma: no cover
        raise ValueError(f"Unsupported format: {fmt}")
