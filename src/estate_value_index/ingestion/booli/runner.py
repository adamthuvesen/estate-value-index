"""Helpers to run Booli spiders from CLI or programmatically."""

from __future__ import annotations

import os
import time
from dataclasses import dataclass

from scrapy.crawler import CrawlerProcess
from scrapy.settings import Settings
from scrapy.utils.project import get_project_settings


@dataclass
class BooliCrawlerOptions:
    """Runtime options for the Booli crawler."""

    max_pages: int = 10
    start_page: int = 1
    output_dir: str | None = None
    delay_seconds: float = 1.0
    concurrent_requests: int = 2
    headless: bool = True
    debug: bool = False
    stats_only: bool = False
    config_file: str | None = None


class BooliCrawlerRunner:
    """Encapsulates crawler setup and execution."""

    def __init__(self, options: BooliCrawlerOptions):
        self.options = options

    def run(self) -> str:
        opts = self.options
        settings = self._prepare_settings(opts)

        resolved_output_dir = settings.get("OUTPUT_DIR")
        self._prepare_directories(resolved_output_dir)

        print("Starting Booli crawl...")
        print(f"   Pages: {opts.start_page}..{opts.max_pages}")
        print(f"   Output directory: {resolved_output_dir}")
        print(f"   Delay: {opts.delay_seconds}s, Concurrent: {opts.concurrent_requests}")
        print(f"   Headless: {opts.headless}, Debug: {opts.debug}")
        print(f"   Stats only: {opts.stats_only}")
        print()

        start_time = time.time()

        process = CrawlerProcess(settings)
        process.crawl(
            "booli",
            max_pages=opts.max_pages,
            start_page=opts.start_page,
            config_file=opts.config_file,
        )
        process.start()

        duration = time.time() - start_time
        print()
        print("Booli crawl completed!")
        print(f"Duration: {duration:.1f} seconds")
        print(f"Output directory: {resolved_output_dir}")

        return resolved_output_dir

    @staticmethod
    def _prepare_directories(output_dir: str) -> None:
        os.makedirs(output_dir, exist_ok=True)
        os.makedirs(os.getenv("BOOLI_IMAGE_STORE", "data/images/raw/booli"), exist_ok=True)
        os.makedirs(
            os.path.dirname(os.getenv("BOOLI_LOG_FILE", "logs/ingestion/booli.log")), exist_ok=True
        )

    @staticmethod
    def _prepare_settings(options: BooliCrawlerOptions) -> Settings:
        settings = get_project_settings()

        settings.set("SPIDER_MODULES", ["estate_value_index.ingestion.booli.spiders"])

        resolved_output_dir = options.output_dir or os.getenv("BOOLI_OUTPUT_DIR", "data/raw/booli")
        settings.set("OUTPUT_DIR", resolved_output_dir)
        settings.set("DOWNLOAD_DELAY", options.delay_seconds)
        settings.set("CONCURRENT_REQUESTS", options.concurrent_requests)
        settings.set("CLOSESPIDER_PAGECOUNT", 5000)

        if options.debug:
            settings.set("LOG_LEVEL", "DEBUG")

        selenium_args = list(settings.get("SELENIUM_DRIVER_ARGUMENTS", []) or [])
        if options.headless:
            if "--headless" not in selenium_args:
                selenium_args.append("--headless")
        else:
            if "--headless" in selenium_args:
                selenium_args.remove("--headless")
        settings.set("SELENIUM_DRIVER_ARGUMENTS", selenium_args)

        if options.stats_only:
            stats_pipelines = {
                "estate_value_index.ingestion.booli.pipelines.DataValidationPipeline": 300,
                "estate_value_index.ingestion.booli.pipelines.DuplicateFilterPipeline": 400,
                "estate_value_index.ingestion.booli.pipelines.StatsPipeline": 800,
            }
            settings.set("ITEM_PIPELINES", stats_pipelines)

        return settings


__all__ = ["BooliCrawlerOptions", "BooliCrawlerRunner"]
