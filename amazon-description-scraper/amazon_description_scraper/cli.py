"""CLI for Amazon product description scraping + endpoint probing."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .endpoints import probe_endpoints, probe_to_dict
from .models import MARKETPLACES, ProviderName
from .parser import extract_asin
from .pipeline import BulkPipeline
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
        default=ProviderName.SOFT.value,
        choices=[p.value for p in ProviderName],
        help=(
            "Data source (default: soft = twister-first + DP fallback, "
            "sequential-safe for ~100 products without captcha)"
        ),
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
        default=None,
        help="Concurrent workers (default: 1 for soft, 8 for others)",
    )
    scrape.add_argument(
        "--delay",
        type=float,
        default=None,
        help="Per-request delay in seconds (default: 0.55 for soft, 0 for others)",
    )
    scrape.add_argument(
        "--no-cache",
        action="store_true",
        help="Bypass caches with Cache-Control + unique query param (soft always on)",
    )
    scrape.add_argument(
        "--no-warm",
        action="store_true",
        help="Skip storefront session warm-up",
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

    bulk = sub.add_parser(
        "bulk",
        help=(
            "Iterative pass-1 turbo pipeline (default): ajaxv2→dimension→aw→dp, "
            "retry failures with the same pass-1 settings until 100%; "
            "use --fast for aggressive single pass"
        ),
    )
    bulk.add_argument("asins", nargs="*", help="ASINs or /dp/ URLs")
    bulk.add_argument("-f", "--file", required=False, help="File with ASINs (one per line)")
    bulk.add_argument("--stdin", action="store_true")
    bulk.add_argument(
        "-m",
        "--marketplace",
        default="nl",
        choices=sorted(MARKETPLACES),
    )
    bulk.add_argument(
        "-o",
        "--output",
        required=True,
        help="Output JSON/CSV path (checkpoint written alongside)",
    )
    bulk.add_argument(
        "--engine",
        choices=("turbo", "soft"),
        default="turbo",
        help="Fetch engine (default turbo)",
    )
    bulk.add_argument(
        "--workers",
        type=int,
        default=None,
        help="Parallel workers (default 12 stable turbo / 24 --fast / 5 soft)",
    )
    bulk.add_argument(
        "--spacing",
        type=float,
        default=None,
        help="Min seconds between request starts (default 0.05 stable / 0.02 --fast)",
    )
    bulk.add_argument(
        "--delay",
        type=float,
        default=None,
        help="Alias for --spacing (legacy)",
    )
    bulk.add_argument(
        "--checkpoint-every",
        type=int,
        default=50,
        help="Write checkpoint every N successful new items (default 50)",
    )
    bulk.add_argument(
        "--max",
        type=int,
        default=None,
        dest="max_items",
        help="Only process first N ASINs (for staged stress tests)",
    )
    bulk.add_argument(
        "--no-resume",
        action="store_true",
        help="Ignore existing checkpoint and start clean",
    )
    bulk.add_argument(
        "--safe",
        action="store_true",
        help="Sequential soft mode (workers=1, spacing=0.55) — slowest, max stability",
    )
    bulk.add_argument(
        "--fast",
        action="store_true",
        help="Aggressive single-pass turbo (w24/s0.02) — faster, may drop below 100%",
    )
    bulk.add_argument(
        "--max-passes",
        type=int,
        default=20,
        help=(
            "Max pass-1 iterations over remaining failures "
            "(default 20; --fast forces 1). Output reports iterations needed."
        ),
    )
    bulk.add_argument(
        "--stream-retries",
        action="store_true",
        help=(
            "Two-phase stream: full-worker first try, then low-concurrency "
            "tail with per-ASIN backoff (faster 100% than batched passes)"
        ),
    )
    bulk.add_argument(
        "--max-retries",
        type=int,
        default=5,
        help="Max requeues per ASIN in --stream-retries mode (default 5 → 6 tries)",
    )
    bulk.add_argument(
        "--allow-duplicates",
        action="store_true",
        help=(
            "Fetch every input line even if ASIN repeats (no-cache each time). "
            "Useful for 10k speed tests with a smaller unique seed list."
        ),
    )

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
        no_cache=args.no_cache,
        warm_session=not args.no_warm,
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


def _cmd_bulk(args: argparse.Namespace) -> int:
    asins = _read_asins(args)
    if not asins:
        print("No ASINs provided. Pass ASINs, --file, or --stdin.", file=sys.stderr)
        return 2
    stable = not args.fast
    if args.safe:
        engine = "soft"
        workers = 1
        spacing = 0.55
        max_passes = 1
        stable = True
    else:
        engine = args.engine
        if args.workers is not None:
            workers = args.workers
        elif engine == "turbo":
            workers = 24 if args.fast else 12
        else:
            workers = 5
        if args.delay is not None:
            spacing = args.delay
        elif args.spacing is not None:
            spacing = args.spacing
        elif engine == "turbo":
            spacing = 0.02 if args.fast else 0.05
        else:
            spacing = 0.12
        max_passes = 1 if args.fast else max(1, args.max_passes)
    stream_retries = bool(getattr(args, "stream_retries", False)) and not args.fast
    max_retries = max(0, int(getattr(args, "max_retries", 5)))
    pipeline = BulkPipeline(
        marketplace=args.marketplace,
        spacing=spacing,
        workers=workers,
        checkpoint_every=args.checkpoint_every,
        engine=engine,
        max_passes=max_passes,
        max_retries=max_retries,
        stream_retries=stream_retries,
        stable=stable and engine == "turbo",
    )
    stats = pipeline.run(
        asins,
        output=args.output,
        resume=not args.no_resume,
        max_items=args.max_items,
        allow_duplicates=bool(args.allow_duplicates),
    )
    rate = (stats.ok / stats.total) if stats.total else 0
    if stream_retries:
        print(
            f"stream_retries max_retries={max_retries} ok={stats.ok}/{stats.total} "
            f"fail={stats.failed} success_rate={rate:.1%} "
            f"requeues={stats.retries} elapsed={stats.elapsed:.1f}s",
            file=sys.stderr,
        )
    else:
        print(
            f"iterations_needed={stats.passes} ok={stats.ok}/{stats.total} "
            f"fail={stats.failed} success_rate={rate:.1%}",
            file=sys.stderr,
        )
    # Stable mode requires 100%; fast mode tolerates >=95%.
    threshold = 1.0 if (stable and engine == "turbo") else 0.95
    return 0 if rate + 1e-12 >= threshold else 1


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
                "Free path: turbo bulk uses ajaxv2 → /gp/aw/d → /dp (no light JSON "
                "without captcha/tokens found). Soft sequential for safest ~100. "
                "For scale without blocks: paapi/rainforest/keepa/generic_json."
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
    if args.command == "bulk":
        return _cmd_bulk(args)
    if args.command == "probe-endpoints":
        return _cmd_probe(args)
    parser.error(f"Unknown command {args.command}")
    return 2
