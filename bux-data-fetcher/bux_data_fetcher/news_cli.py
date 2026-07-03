#!/usr/bin/env python3
"""CLI voor het ophalen van historisch nieuws via scraping."""

from __future__ import annotations

import argparse
import logging
import sys

from tqdm import tqdm

from .config import load_config
from .instruments import Instrument, fetch_all_instruments
from .news.scraper import fetch_news_for_instrument
from .news.storage import load_news_progress, save_news, save_news_progress
from .storage import load_instruments, save_instruments
from .ticker_mapper import bulk_isin_to_yahoo

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


def cmd_fetch_news(args: argparse.Namespace) -> int:
    config = load_config(years=args.years, output_dir=args.output)

    instruments = load_instruments(config)
    if not instruments:
        logger.info("Geen instrumenten cache, ophalen...")
        instruments = fetch_all_instruments(config)
        save_instruments(instruments, config)

    if args.limit:
        instruments = instruments[: args.limit]

    ticker_map = bulk_isin_to_yahoo(instruments, config)
    completed = load_news_progress(config)
    total_articles = 0

    for instrument in tqdm(instruments, desc="Nieuws scrapen"):
        if not args.force and instrument.isin in completed:
            continue

        try:
            articles = fetch_news_for_instrument(
                instrument,
                config,
                yahoo_ticker=ticker_map.get(instrument.isin),
                years=args.years,
                langs=args.lang.split(",") if args.lang else ["en-US"],
            )
            path = save_news(articles, config, instrument.isin)
            if path:
                total_articles += len(articles)
                completed.add(instrument.isin)
                save_news_progress(config, completed)
        except Exception as exc:
            logger.error("Nieuws ophalen mislukt voor %s: %s", instrument.isin, exc)

    print(f"\nKlaar: {len(completed)} instrumenten, {total_articles} artikelen deze run")
    print(f"Nieuws directory: {config.output_dir / 'news'}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Scrape historisch stock nieuws via Google News RSS (+ Yahoo Finance)."
    )
    parser.add_argument("--years", type=int, default=2, help="Jaren historie (default: 2)")
    parser.add_argument("--output", default="./data", help="Output directory")
    parser.add_argument("--limit", type=int, default=None, help="Beperk aantal instrumenten")
    parser.add_argument("--force", action="store_true", help="Overschrijf bestaande news data")
    parser.add_argument(
        "--lang",
        default="en-US",
        help="Google News taal/locale, komma-gescheiden (bijv. en-US,nl-NL,de-DE)",
    )
    parser.add_argument("-v", "--verbose", action="store_true")

    args = parser.parse_args(argv)
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    return cmd_fetch_news(args)


if __name__ == "__main__":
    sys.exit(main())
