#!/usr/bin/env python3
"""CLI voor het ophalen van Bux Zero aandelen en 10-minuten historische data."""

from __future__ import annotations

import argparse
import logging
import sys

from tqdm import tqdm

from .config import load_config
from .historical import fetch_10m_history
from .instruments import fetch_all_instruments
from .storage import (
    is_completed,
    load_instruments,
    load_progress,
    save_candles,
    save_instruments,
    save_progress,
)
from .ticker_mapper import bulk_isin_to_yahoo

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


def cmd_fetch_instruments(args: argparse.Namespace) -> int:
    config = load_config(years=args.years, output_dir=args.output)
    instruments = fetch_all_instruments(config)
    save_instruments(instruments, config)
    print(f"\n{len(instruments)} instrumenten opgeslagen in {config.instruments_path}")
    return 0


def cmd_fetch_history(args: argparse.Namespace) -> int:
    config = load_config(years=args.years, output_dir=args.output)

    instruments = load_instruments(config)
    if not instruments:
        logger.info("Geen instrumenten cache gevonden, ophalen...")
        instruments = fetch_all_instruments(config)
        save_instruments(instruments, config)

    if args.limit:
        instruments = instruments[: args.limit]

    ticker_map = bulk_isin_to_yahoo(instruments, config)
    completed = load_progress(config)
    failed: list[str] = []

    for instrument in tqdm(instruments, desc="Historische data ophalen"):
        if not args.force and is_completed(config, instrument.isin):
            completed.add(instrument.isin)
            continue

        try:
            df = fetch_10m_history(
                instrument,
                config,
                yahoo_symbol=ticker_map.get(instrument.isin),
            )
            path = save_candles(df, config, instrument.isin)
            if path:
                completed.add(instrument.isin)
                logger.info(
                    "%s (%s): %d candles -> %s",
                    instrument.ticker or instrument.isin,
                    instrument.name[:30],
                    len(df),
                    path.name,
                )
            else:
                failed.append(instrument.isin)
                logger.warning("Geen data voor %s (%s)", instrument.isin, instrument.name)
        except Exception as exc:
            failed.append(instrument.isin)
            logger.error("Fout bij %s: %s", instrument.isin, exc)

        save_progress(config, completed)

    print(f"\nKlaar: {len(completed)} instrumenten met data")
    if failed:
        print(f"Mislukt/geen data: {len(failed)} instrumenten")
        if args.verbose:
            for isin in failed:
                print(f"  - {isin}")
    print(f"Data directory: {config.candles_dir}")
    return 0 if not failed else 1


def cmd_fetch_all(args: argparse.Namespace) -> int:
    if cmd_fetch_instruments(args) != 0:
        return 1
    return cmd_fetch_history(args)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Haal alle Bux Zero aandelen en 10-minuten historische data op (2 jaar)."
    )
    parser.add_argument(
        "command",
        choices=["instruments", "history", "all"],
        help="instruments=alleen productlijst, history=alleen candles, all=beide",
    )
    parser.add_argument("--years", type=int, default=2, help="Aantal jaren historie (default: 2)")
    parser.add_argument("--output", default=None, help="Output directory (default: ./data)")
    parser.add_argument("--limit", type=int, default=None, help="Beperk aantal instrumenten (test)")
    parser.add_argument("--force", action="store_true", help="Overschrijf bestaande candle data")
    parser.add_argument("-v", "--verbose", action="store_true", help="Meer logging")

    args = parser.parse_args(argv)
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    commands = {
        "instruments": cmd_fetch_instruments,
        "history": cmd_fetch_history,
        "all": cmd_fetch_all,
    }
    return commands[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
