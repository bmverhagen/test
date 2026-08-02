#!/usr/bin/env python3
"""Command-line interface for the Booking.com Zwarte Woud scraper."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from .filters import format_filter_help
from .models import SearchQuery
from .scraper import DEFAULT_DELAY, DEFAULT_MAX_PAGES, BookingScraper
from .storage import write_report
from .urls import build_nflt, build_search_url

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


def _csv_ints(value: str) -> list[int]:
    return [int(part.strip()) for part in value.split(",") if part.strip()]


def _csv_strs(value: str) -> list[str]:
    return [part.strip() for part in value.split(",") if part.strip()]


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
            "  python scrape.py --filter spa,sauna,parking --free-cancellation\n"
            "  python scrape.py --stars 3,4 --property-type hotels,bnb --city freiburg\n"
            "  python scrape.py --nflt 'hotelfacility=433;roomfacility=17'\n"
            "  python scrape.py --list-filters\n"
        ),
    )

    dest = parser.add_argument_group("Bestemming & data")
    dest.add_argument("--destination", default="Zwarte Woud")
    dest.add_argument("--dest-id", default="1477", help="Booking dest_id (Zwarte Woud=1477)")
    dest.add_argument("--dest-type", default="region")
    dest.add_argument("--checkin", default="2026-08-26")
    dest.add_argument("--checkout", default="2026-08-29")
    dest.add_argument("--adults", type=int, default=2)
    dest.add_argument("--children", type=int, default=0)
    dest.add_argument("--rooms", type=int, default=1)
    dest.add_argument("--currency", default="EUR")
    dest.add_argument("--lang", default="nl")
    dest.add_argument(
        "--order",
        default="price",
        help="Sortering: price, popularity, bayesian_review_score, ...",
    )

    price = parser.add_argument_group("Prijs & score")
    price.add_argument("--max-price", type=float, default=500.0, help="Max totaalprijs EUR")
    price.add_argument("--min-price", type=float, default=None, help="Min totaalprijs EUR")
    price.add_argument("--min-score", type=float, default=9.0)
    price.add_argument(
        "--no-price-chip",
        action="store_true",
        help="Geen Booking per-nacht price= chip; alleen client-side prijsfilter",
    )

    meals = parser.add_argument_group("Maaltijden")
    meals.add_argument("--no-breakfast", action="store_true")
    meals.add_argument(
        "--good-breakfast",
        action="store_true",
        help="Filter rated_high=1 (erg goed ontbijt)",
    )

    fac = parser.add_argument_group("Faciliteiten & kamer")
    fac.add_argument("--no-pool", action="store_true", help="Zwembad-filter uit (hotelfacility=433)")
    fac.add_argument("--no-balcony", action="store_true", help="Balkon-filter uit (roomfacility=17)")
    fac.add_argument("--terrace", action="store_true", help="Terras (roomfacility=123)")
    fac.add_argument(
        "--balcony-or-terrace",
        action="store_true",
        help="Balkon of terras (roomfacility=17 + 123)",
    )
    fac.add_argument("--parking", action="store_true")
    fac.add_argument("--spa", action="store_true")
    fac.add_argument("--sauna", action="store_true")
    fac.add_argument("--pets", action="store_true", help="Huisdieren toegestaan")
    fac.add_argument("--free-cancellation", action="store_true")
    fac.add_argument(
        "--filter",
        dest="extra_filters",
        default="",
        help="Comma-separated aliases/chips, bv. spa,sauna,view,wifi,kitchen",
    )
    fac.add_argument(
        "--require-room-balcony-text",
        action="store_true",
        help=(
            "Client-side: getoonde kamer moet balkon/terras hebben "
            "(kamernaam, omschrijving of kenmerk via hotelpagina)"
        ),
    )
    fac.add_argument(
        "--enrich-rooms",
        action="store_true",
        help=(
            "Haal hotelpagina's op om balkon te checken in omschrijving + kenmerken "
            "(niet alleen kamernaam)"
        ),
    )

    prop = parser.add_argument_group("Type & locatie")
    prop.add_argument(
        "--stars",
        default="",
        help="Sterren, komma-gescheiden (bv. 3,4,5 → class=3;class=4;class=5)",
    )
    prop.add_argument(
        "--property-type",
        default="",
        help="bv. hotels,apartments,bnb,guest_houses,holiday_homes",
    )
    prop.add_argument(
        "--city",
        default="",
        help="bv. freiburg,baden-baden,titisee-neustadt,rust",
    )

    advanced = parser.add_argument_group("Geavanceerd")
    advanced.add_argument(
        "--nflt",
        default="",
        help="Raw nflt chips (; of , gescheiden), worden toegevoegd aan de query",
    )
    advanced.add_argument(
        "--list-filters",
        action="store_true",
        help="Toon alle named aliases + Capla-catalogus en stop",
    )
    advanced.add_argument("--pages", type=int, default=DEFAULT_MAX_PAGES)
    advanced.add_argument("--delay", type=float, default=DEFAULT_DELAY)
    advanced.add_argument("--from-file", type=Path)
    advanced.add_argument("--format", choices=("table", "json", "csv"), default="table")
    advanced.add_argument("-o", "--output", type=Path)
    advanced.add_argument("--print-url", action="store_true")
    advanced.add_argument("--print-nflt", action="store_true", help="Print alleen nflt-string")
    advanced.add_argument("-v", "--verbose", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    if args.list_filters:
        print(format_filter_help())
        return 0

    try:
        stars = tuple(_csv_ints(args.stars)) if args.stars else ()
        property_types = tuple(_csv_strs(args.property_type)) if args.property_type else ()
        cities = tuple(_csv_strs(args.city)) if args.city else ()
        extra = tuple(_csv_strs(args.extra_filters)) if args.extra_filters else ()
        raw = tuple(
            part.strip()
            for part in args.nflt.replace(",", ";").split(";")
            if part.strip()
        )
    except (ValueError, KeyError) as exc:
        logger.error("%s", exc)
        return 2

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
        min_total_price=args.min_price,
        min_review_score=args.min_score,
        breakfast=not args.no_breakfast,
        good_breakfast=args.good_breakfast,
        swimming_pool=not args.no_pool,
        balcony=not args.no_balcony and not args.balcony_or_terrace,
        terrace=args.terrace and not args.balcony_or_terrace,
        balcony_or_terrace=args.balcony_or_terrace,
        free_cancellation=args.free_cancellation,
        parking=args.parking,
        spa=args.spa,
        sauna=args.sauna,
        pets_allowed=args.pets,
        stars=stars,
        property_types=property_types,
        cities=cities,
        extra_filters=extra,
        raw_nflt=raw,
        order=args.order,
        apply_price_chip=not args.no_price_chip,
    )

    if query.nights <= 0:
        logger.error("checkout moet na checkin liggen")
        return 2

    try:
        nflt = build_nflt(query)
        search_url = build_search_url(query)
    except KeyError as exc:
        logger.error("%s", exc)
        return 2

    if args.print_nflt:
        print(nflt)
        return 0
    if args.print_url:
        print(search_url)
        return 0

    scraper = BookingScraper(
        query,
        delay=args.delay,
        max_pages=args.pages,
        require_room_balcony_text=args.require_room_balcony_text,
        enrich_rooms=args.enrich_rooms,
    )

    if args.from_file:
        html = args.from_file.read_text(encoding="utf-8")
        report = scraper.scrape_html(html, search_url=search_url)
    else:
        logger.info("nflt=%s", nflt)
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
