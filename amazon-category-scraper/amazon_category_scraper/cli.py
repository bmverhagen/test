#!/usr/bin/env python3
"""Command line interface for the Amazon category brand scraper."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from .fetcher import DEFAULT_MAX_RETRIES, DEFAULT_TIMEOUT, Fetcher
from .models import PageResult
from .parser import parse_category_page, resolve_product_brands
from .scraper import DEFAULT_DELAY, CategoryBrandScraper, merge_pages
from .storage import FORMATS, write_report
from .urls import NotACategoryPageError

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="amazon-category-scraper",
        description=(
            "Extract brand names from Amazon CATEGORY pages (search/browse/best-seller "
            "listings). Product detail pages are rejected and never fetched."
        ),
        epilog=(
            "Examples:\n"
            "  amazon-category-scraper 'https://www.amazon.com/s?rh=n%%3A172282'\n"
            "  amazon-category-scraper 'https://www.amazon.com/b?node=172282' --pages 3 -o brands.csv\n"
            "  amazon-category-scraper 'https://www.amazon.com/zgbs/kitchen/289745/' --top 10\n"
            "  amazon-category-scraper --from-file saved_category_page.html --format json\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "urls",
        nargs="*",
        metavar="CATEGORY_URL",
        help="One or more Amazon category page URLs (/s?..., /b?node=..., /gp/bestsellers/...)",
    )
    parser.add_argument(
        "--from-file",
        type=Path,
        action="append",
        default=[],
        metavar="HTML_FILE",
        help="Parse an already-saved category page HTML file instead of fetching (repeatable)",
    )
    parser.add_argument(
        "--pages",
        type=int,
        default=1,
        help="Max listing pages to follow per category URL (default: 1)",
    )
    parser.add_argument(
        "--top",
        type=int,
        default=None,
        metavar="N",
        help=(
            "Per-product view: output the first N products by rank with the brand "
            "of each product (0 = all) instead of the aggregated brand list"
        ),
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=DEFAULT_DELAY,
        help=f"Base delay in seconds between requests (default: {DEFAULT_DELAY})",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=DEFAULT_TIMEOUT,
        help=f"HTTP timeout in seconds (default: {DEFAULT_TIMEOUT})",
    )
    parser.add_argument(
        "--retries",
        type=int,
        default=DEFAULT_MAX_RETRIES,
        help=f"Retries per page on transient failures (default: {DEFAULT_MAX_RETRIES})",
    )
    parser.add_argument(
        "--user-agent",
        default=None,
        help="Fixed User-Agent header (default: rotate between desktop browsers)",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=None,
        help="Output file (default: print to stdout)",
    )
    parser.add_argument(
        "--format",
        choices=FORMATS,
        default=None,
        help="Output format (default: inferred from --output extension, else csv)",
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="Debug logging")
    return parser


def _resolve_format(args: argparse.Namespace) -> str:
    if args.format:
        return args.format
    if args.output is not None:
        suffix = args.output.suffix.lstrip(".").lower()
        if suffix in FORMATS:
            return suffix
    return "csv"


def _parse_local_files(paths: list[Path]) -> list[PageResult]:
    pages: list[PageResult] = []
    for html_path in paths:
        html = html_path.read_text(encoding="utf-8", errors="replace")
        result = parse_category_page(html, url=str(html_path))
        if result.is_best_seller_list and result.cards_with_brand < result.total_cards:
            # Offline there is no sibling listing to learn brands from, but
            # house brands and conservative title guesses still apply.
            resolve_product_brands(result, [])
        logger.info(
            "Parsed %s: %d product cards, %d with a brand, %d sidebar brands",
            html_path,
            result.total_cards,
            result.cards_with_brand,
            len(result.refinement_brands),
        )
        pages.append(result)
    return pages


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    if not args.urls and not args.from_file:
        build_parser().error("provide at least one CATEGORY_URL or --from-file HTML_FILE")

    pages: list[PageResult] = []
    errors: list[str] = []

    try:
        pages.extend(_parse_local_files(args.from_file))
    except OSError as exc:
        logger.error("Cannot read HTML file: %s", exc)
        return 2

    if args.urls:
        scraper = CategoryBrandScraper(
            fetcher=Fetcher(
                timeout=args.timeout,
                max_retries=args.retries,
                user_agent=args.user_agent,
            ),
            delay=args.delay,
            max_pages=args.pages,
        )
        try:
            fetched_pages, fetch_errors = scraper.collect_pages(args.urls)
        except NotACategoryPageError as exc:
            logger.error("%s", exc)
            return 2
        pages.extend(fetched_pages)
        errors.extend(fetch_errors)

    report = merge_pages(pages, args.urls + [str(p) for p in args.from_file], errors)
    write_report(report, args.output, _resolve_format(args), top=args.top)

    destination = str(args.output) if args.output else "stdout"
    logger.info(
        "Done: %d unique brands from %d page(s) (%d product cards) -> %s",
        len(report.brands),
        report.pages_scraped,
        report.product_cards_seen,
        destination,
    )
    if errors:
        logger.warning("%d page(s) failed; see log above", len(errors))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
