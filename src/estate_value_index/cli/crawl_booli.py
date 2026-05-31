"""CLI entrypoint to run the Booli crawler."""

from __future__ import annotations

import argparse
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from argparse import Namespace

from estate_value_index.ingestion.booli.runner import BooliCrawlerOptions, BooliCrawlerRunner


def main(argv: list[str] | None = None, *, args: Namespace | None = None) -> int:
    """Run the Booli crawler. ``args`` takes precedence over ``argv`` when given."""
    if args is None:
        parser = argparse.ArgumentParser(description="Run Booli Real Estate Crawler")
        parser.add_argument("--max-pages", type=int, default=10)
        parser.add_argument("--start-page", type=int, default=1)
        parser.add_argument("--output-dir", type=str, default=None)
        parser.add_argument("--delay", type=float, default=0.1)
        parser.add_argument("--concurrent", type=int, default=4)
        parser.add_argument("--no-headless", dest="headless", action="store_false", default=True)
        parser.add_argument("--debug", action="store_true")
        parser.add_argument("--stats-only", action="store_true")
        parser.add_argument("--config-file", type=str, default=None)
        args = parser.parse_args(argv)

    options = BooliCrawlerOptions(
        max_pages=args.max_pages,
        start_page=args.start_page,
        output_dir=args.output_dir,
        delay_seconds=args.delay,
        concurrent_requests=args.concurrent,
        headless=args.headless,
        debug=args.debug,
        stats_only=args.stats_only,
        config_file=args.config_file,
    )

    out_dir = BooliCrawlerRunner(options).run()

    print("Crawl complete!")
    print(f"Output directory: {out_dir}")
    print(f"Check the latest file: {out_dir}/booli_listings_*.jsonl")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
