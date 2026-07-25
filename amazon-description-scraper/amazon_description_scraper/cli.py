"""CLI for Amazon product description scraping + endpoint probing."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .endpoints import probe_endpoints, probe_to_dict
from .models import MARKETPLACES, ProviderName
from .parser import extract_asin
from .scraper import DescriptionScraper
from .storage import write_csv, write_json


def _read_asins(args: argparse.Namespace) -> list[str]:
    values: list[str] = []
    values.extend(args.asins or [])
    if args.file:
        text = Path(args.file).read_text(encoding="utf-8")
        for line in text.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            # support csv with asin in first column
            values.append(line.split(",")[0].strip().strip('"'))
    if args.stdin:
        for line in sys.stdin:
            line = line.strip()
            if line:
                values.append(line.split(",")[0].strip().strip('"'))
    return values


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="amazon-description-scraper",
        description=(
            "Scrape Amazon product descriptions as fast as possible. "
            "Default provider fetches /dp/{ASIN} HTML (only free source that "
            "contains descriptions). Prefer paapi/rainforest/keepa/generic_json "
            "to plug into JSON APIs without parsing HTML."
        ),
    )
    sub = parser.add_subparsers(dest="command", required=True)

    scrape = sub.add_parser("scrape", help="Fetch descriptions for one or more ASINs")
    scrape.add_argument("asins", nargs="*", help="ASINs or /dp/ URLs")
    scrape.add_argument("-f", "--file", help="Text/CSV file with ASINs (one per line)")
    scrape.add_argument("--stdin", action="store_true", help="Read ASINs from stdin")
    scrape.add_argument(
        "-m",
        "--marketplace",
        default="nl",
        choices=sorted(MARKETPLACES),
        help="Amazon marketplace domain (default: nl)",
    )
    scrape.add_argument(
        "-p",
        "--provider",
        default=ProviderName.HTML.value,
        choices=[p.value for p in ProviderName],
        help="Data source (default: html)",
    )
    scrape.add_argument("-o", "--output", help="Output file (.json or .csv)")
    scrape.add_argument(
        "--format",
        choices=("json", "csv"),
        default="json",
        help="Stdout/file format when --output has no useful extension",
    )
    scrape.add_argument(
        "--workers",
        type=int,
        default=8,
        help="Concurrent workers for HTML/JSON fetches (default: 8)",
    )
    scrape.add_argument(
        "--delay",
        type=float,
        default=0.0,
        help="Optional per-request delay in seconds (per worker)",
    )
    scrape.add_argument("--api-key", help="API key for rainforest/keepa/generic_json")
    scrape.add_argument(
        "--endpoint-url",
        help="URL template for generic_json, with {asin}/{domain}/{host}/{api_key}",
    )
    scrape.add_argument(
        "--json-map",
        help="Field map for generic_json, e.g. title=product.title,description=product.description",
    )
    scrape.add_argument("--paapi-access-key", help="PA-API access key")
    scrape.add_argument("--paapi-secret-key", help="PA-API secret key")
    scrape.add_argument("--paapi-partner-tag", help="PA-API partner tag")
    scrape.add_argument("-q", "--quiet", action="store_true")

    probe = sub.add_parser(
        "probe-endpoints",
        help="Probe Amazon endpoints for an ASIN and report which carry descriptions",
    )
    probe.add_argument("asin", help="ASIN or product URL")
    probe.add_argument(
        "-m",
        "--marketplace",
        default="nl",
        choices=sorted(MARKETPLACES),
    )
    probe.add_argument("-o", "--output", help="Optional JSON output path")

    return parser


def _cmd_scrape(args: argparse.Namespace) -> int:
    asins = _read_asins(args)
    if not asins:
        print("No ASINs provided. Pass ASINs, --file, or --stdin.", file=sys.stderr)
        return 2

    scraper = DescriptionScraper(
        marketplace=args.marketplace,
        provider=args.provider,
        workers=args.workers,
        delay=args.delay,
        api_key=args.api_key,
        endpoint_url=args.endpoint_url,
        json_map=args.json_map,
        paapi_access_key=args.paapi_access_key,
        paapi_secret_key=args.paapi_secret_key,
        paapi_partner_tag=args.paapi_partner_tag,
    )
    products = scraper.fetch_many(asins)

    fmt = args.format
    if args.output:
        suffix = Path(args.output).suffix.lower()
        if suffix == ".csv":
            fmt = "csv"
        elif suffix == ".json":
            fmt = "json"

    if args.output:
        path = Path(args.output)
        if fmt == "csv":
            write_csv(path, products)
        else:
            write_json(path, products, marketplace=args.marketplace, provider=args.provider)
        if not args.quiet:
            ok = sum(1 for p in products if not p.error)
            print(f"Wrote {ok}/{len(products)} products to {path}", file=sys.stderr)
    else:
        if fmt == "csv":
            write_csv(sys.stdout, products)
        else:
            json.dump(
                [p.to_dict() for p in products],
                sys.stdout,
                ensure_ascii=False,
                indent=2,
            )
            sys.stdout.write("\n")

    errors = [p for p in products if p.error]
    return 1 if errors and len(errors) == len(products) else 0


def _cmd_probe(args: argparse.Namespace) -> int:
    asin = extract_asin(args.asin)
    if not asin:
        print(f"Could not parse ASIN from {args.asin!r}", file=sys.stderr)
        return 2
    from .models import resolve_marketplace

    marketplace = resolve_marketplace(args.marketplace)
    probes = probe_endpoints(marketplace, asin)
    payload = {
        "asin": asin,
        "marketplace": marketplace.domain,
        "endpoints": [probe_to_dict(p) for p in probes],
        "summary": {
            "with_description_markers": [
                p.name for p in probes if p.has_description_markers
            ],
            "recommendation": (
                "Use /dp/{ASIN} HTML, or plug into paapi/rainforest/keepa/generic_json. "
                "No free Amazon JSON description endpoint found."
            ),
        },
    }
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    if args.output:
        Path(args.output).write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "scrape":
        return _cmd_scrape(args)
    if args.command == "probe-endpoints":
        return _cmd_probe(args)
    parser.error(f"Unknown command {args.command}")
    return 2
