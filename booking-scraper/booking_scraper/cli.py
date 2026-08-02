#!/usr/bin/env python3
"""Command-line interface for the Booking.com Zwarte Woud scraper."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from .models import SearchQuery
from .scraper import DEFAULT_DELAY, DEFAULT_MAX_PAGES, BookingScraper
from .storage import write_report
from .urls import build_search_url

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="booking-scraper",
        description=(
            "Zoek overnachtingen op Booking.com in het Zwarte Woud "
            "(standaard: 26–29 augustus 2026, totaal ≤ €500, score 9+, "
            "ontbijt, zwembad, balkon)."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Voorbeelden:\n"
            "  python scrape.py\n"
            "  python scrape.py --format json -o resultaten.json\n"
            "  python scrape.py --from-file tests/fixtures/search_results.html\n"
            "  python scrape.py --max-price 450 --adults 2 --print-url\n"
        ),
    )
    parser.add_argument("--destination", default="Zwarte Woud")
    parser.add_argument("--dest-id", default="1477", help="Booking dest_id (regio Zwarte Woud=1477)")
    parser.add_argument("--dest-type", default="region")
    parser.add_argument("--checkin", default="2026-08-26")
    parser.add_argument("--checkout", default="2026-08-29")
    parser.add_argument("--adults", type=int, default=2)
    parser.add_argument("--children", type=int, default=0)
    parser.add_argument("--rooms", type=int, default=1)
    parser.add_argument("--max-price", type=float, default=500.0, help="Max totaalprijs in EUR")
    parser.add_argument("--min-score", type=float, default=9.0)
    parser.add_argument("--no-breakfast", action="store_true")
    parser.add_argument("--no-pool", action="store_true")
    parser.add_argument("--no-balcony", action="store_true")
    parser.add_argument(
        "--require-room-balcony-text",
        action="store_true",
        help=(
            "Sluit resultaten uit waarbij de getoonde kamer geen balkon/terras "
            "noemt (Booking's balkonfilter geldt op accommodatieniveau)"
        ),
    )
    parser.add_argument("--currency", default="EUR")
    parser.add_argument("--lang", default="nl")
    parser.add_argument("--order", default="price", help="Booking sort order (default: price)")
    parser.add_argument("--pages", type=int, default=DEFAULT_MAX_PAGES)
    parser.add_argument("--delay", type=float, default=DEFAULT_DELAY)
    parser.add_argument(
        "--from-file",
        type=Path,
        help="Parse opgeslagen searchresults HTML i.p.v. live fetch",
    )
    parser.add_argument(
        "--format",
        choices=("table", "json", "csv"),
        default="table",
    )
    parser.add_argument("-o", "--output", type=Path, help="Schrijf output naar bestand")
    parser.add_argument(
        "--print-url",
        action="store_true",
        help="Print alleen de Booking.com zoek-URL en stop",
    )
    parser.add_argument("-v", "--verbose", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    query = SearchQuery(
        destination=args.destination,
        dest_id=args.dest_id,
        dest_type=args.dest_type,
        checkin=args.checkin,
        checkout=args.checkout,
        adults=args.adults,
        children=args.children,
        rooms=args.rooms,
        currency=args.currency,
        lang=args.lang,
        max_total_price=args.max_price,
        min_review_score=args.min_score,
        breakfast=not args.no_breakfast,
        swimming_pool=not args.no_pool,
        balcony=not args.no_balcony,
        order=args.order,
    )

    if query.nights <= 0:
        logger.error("checkout moet na checkin liggen")
        return 2

    search_url = build_search_url(query)
    if args.print_url:
        print(search_url)
        return 0

    scraper = BookingScraper(
        query,
        delay=args.delay,
        max_pages=args.pages,
        require_room_balcony_text=args.require_room_balcony_text,
    )

    if args.from_file:
        html = args.from_file.read_text(encoding="utf-8")
        report = scraper.scrape_html(html, search_url=search_url)
    else:
        logger.info("Zoeken: %s", search_url)
        report = scraper.scrape()

    write_report(report, output=args.output, fmt=args.format)

    if report.errors:
        for err in report.errors:
            logger.warning("%s", err)
        return 1 if not report.properties else 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
