from __future__ import annotations

from .runner import BooliCrawlerOptions, BooliCrawlerRunner


def crawl_booli(
    max_pages: int = 10,
    start_page: int = 1,
    output_dir: str | None = None,
    delay_seconds: float = 1.0,
    concurrent_requests: int = 2,
    headless: bool = True,
    debug: bool = False,
    stats_only: bool = False,
    config_file: str | None = None,
) -> str:
    """Run the Booli spider programmatically and return the output directory."""

    options = BooliCrawlerOptions(
        max_pages=max_pages,
        start_page=start_page,
        output_dir=output_dir,
        delay_seconds=delay_seconds,
        concurrent_requests=concurrent_requests,
        headless=headless,
        debug=debug,
        stats_only=stats_only,
        config_file=config_file,
    )

    runner = BooliCrawlerRunner(options)
    return runner.run()


__all__ = ["crawl_booli", "BooliCrawlerOptions", "BooliCrawlerRunner"]
