import argparse
import os

from .runner import BooliCrawlerOptions, BooliCrawlerRunner


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Booli crawler (module entrypoint)")
    parser.add_argument("--start-page", type=int, default=int(os.getenv("BOOLI_START_PAGE", "1")))
    parser.add_argument("--max-pages", type=int, default=int(os.getenv("BOOLI_MAX_PAGES", "10")))
    parser.add_argument("--concurrent", type=int, default=int(os.getenv("BOOLI_CONCURRENT", "2")))
    parser.add_argument("--delay", type=float, default=float(os.getenv("BOOLI_DELAY", "1")))
    parser.add_argument("--debug", action="store_true", default=bool(os.getenv("BOOLI_DEBUG", "")))
    parser.add_argument("--config-file", type=str, default=os.getenv("BOOLI_CONFIG", None))
    parser.add_argument("--output-dir", type=str, default=os.getenv("BOOLI_OUTPUT_DIR", None))

    args = parser.parse_args()

    options = BooliCrawlerOptions(
        start_page=args.start_page,
        max_pages=args.max_pages,
        concurrent_requests=args.concurrent,
        delay_seconds=args.delay,
        debug=args.debug,
        config_file=args.config_file,
        output_dir=args.output_dir,
    )

    BooliCrawlerRunner(options).run()


if __name__ == "__main__":
    main()
