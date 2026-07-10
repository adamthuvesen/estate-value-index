import json
from datetime import UTC, datetime
from pathlib import Path

import scrapy

from estate_value_index.ingestion.booli.extractors import (
    BooliExtractionMixins,
    extract_sold_price_from_text,
)
from estate_value_index.ingestion.booli.items import BooliListingItem
from estate_value_index.ingestion.booli.parsers import (
    listing_ids_from_links,
    resolve_listing_links,
)
from estate_value_index.ingestion.booli.urls import extract_listing_id

# Re-export for tests importing from spiders.booli
__all__ = ["BooliSpider", "extract_sold_price_from_text"]


class BooliSpider(BooliExtractionMixins, scrapy.Spider):
    name = "booli"
    allowed_domains = ["booli.se"]

    def __init__(self, max_pages=None, config_file=None, start_page=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.max_pages = int(max_pages) if max_pages else 10
        self.start_page = int(start_page) if start_page else 1
        self.scraped_listings = set()
        self.current_page = 0
        self.pages_processed = 0  # Track actual pages processed
        self.total_listings_found = 0
        self.total_listings_processed = 0
        self.total_duplicate_links = 0
        self.progress_log_interval = int(kwargs.get("progress_interval", 10) or 10)
        self.start_time = datetime.now()
        self.last_processed_page = None
        self.build_id = None
        # parents[5] lands on the repo root; keep the runtime cache out of the
        # source package, under the repo data/ dir. The parent dir is created
        # lazily when the build ID is first persisted.
        repo_root = Path(__file__).resolve().parents[5]
        self.build_id_cache_path = str(repo_root / "data" / "cache" / "booli_build_id.txt")
        # Enable debug logging for testing
        self.debug_extraction = kwargs.get("debug_extraction", False)

        # Load configuration
        self.config = self._load_config(config_file)
        self.base_url = self.config.get("crawler_settings", {}).get(
            "base_url", "https://www.booli.se/sok/till-salu"
        )
        self.search_params = self._build_search_params()

        self.logger.info(
            f"Initializing Booli spider with start_page={self.start_page}, max_pages={self.max_pages}"
        )

    def _load_config(self, config_file=None):
        """Load configuration from JSON file"""
        explicit_config = config_file is not None
        if not config_file:
            # Default to booli config in ingestion/config/booli.json
            # spiders/booli.py is at .../ingestion/booli/spiders/; parents[2] is ingestion/.
            config_file = str(Path(__file__).resolve().parents[2] / "config" / "booli.json")

        try:
            with open(config_file, encoding="utf-8") as f:
                config = json.load(f)
                self.logger.info(f"Loaded configuration from: {config_file}")
                return config
        except FileNotFoundError as exc:
            if explicit_config:
                raise FileNotFoundError(f"Booli config file not found: {config_file}") from exc
            self.logger.warning(f"Config file not found: {config_file}. Using default parameters.")
            return self._default_config()
        except json.JSONDecodeError as e:
            if explicit_config:
                raise ValueError(f"Invalid JSON in Booli config file: {config_file}") from e
            self.logger.error(f"Invalid JSON in config file: {e}. Using default parameters.")
            return self._default_config()

    def _default_config(self):
        """Default configuration for Booli sold prices"""
        return {
            "site": "booli",
            "search_parameters": {
                "maxSoldPrice": "9000000",
                "minSoldPrice": "4000000",
                "maxLivingArea": "80",
                "minLivingArea": "40",
                "maxRooms": "4",
                "minRooms": "2",
                "areaIds": "115353,115341,115350,115347,869737,115349,115348,115351,115354,115346",
                "minSoldDate": "2023-01-01",
            },
            "location_mappings": {
                "1": "Stockholms kommun",
                "115353": "Kungsholmen",
                "115341": "Vasastan",
                "115350": "Östermalm",
                "115347": "Södermalm",
                "869737": "Norrmalm",
                "115349": "Gamla Stan",
                "115348": "Djurgården",
                "115351": "Södermalm",
                "115354": "Hammarby",
                "115346": "Skanstull",
            },
            "crawler_settings": {
                "max_pages": 10,
                "base_url": "https://www.booli.se/sok/slutpriser",
            },
        }

    def _build_search_params(self):
        """Build search parameters from configuration"""
        return self.config.get("search_parameters", {})

    def _build_search_url(self, page=1):
        """Construct the Booli search URL with query parameters and page number."""
        params = []
        for key, value in self.search_params.items():
            params.append(f"{key}={value}")
        if page:
            params.append(f"page={page}")
        return f"{self.base_url}?{'&'.join(params)}"

    custom_settings = {
        "CONCURRENT_REQUESTS": 8,
        "CONCURRENT_REQUESTS_PER_DOMAIN": 4,
        "DOWNLOAD_DELAY": 0.5,
        "RANDOMIZE_DOWNLOAD_DELAY": True,
        "AUTOTHROTTLE_TARGET_CONCURRENCY": 2.5,
    }

    def start_requests(self):
        """Generate initial search request"""
        # Build URL with parameters using explicit page number
        search_url = self._build_search_url(page=self.start_page)

        self.logger.info(f"Starting Booli crawl with URL: {search_url}")
        self.logger.info(f"Will crawl until page: {self.max_pages}")
        self.logger.info(f"Base URL: {self.base_url}")
        self.logger.info(f"Search params: {self.search_params}")

        yield scrapy.Request(
            url=search_url,
            callback=self.parse_search_results,
            meta={"page": self.start_page, "booli_slot": "search"},
            headers=self._default_http_headers(),
        )

    async def start(self):
        for request in self.start_requests():
            yield request

    def parse_search_results(self, response):
        """Parse search results page and extract listing URLs"""
        current_page = response.meta.get("page", 1)
        self._record_search_page_seen(response, current_page)

        listing_links = self._search_listing_links(response, current_page)
        annons_count, bostad_count = self._count_listing_link_types(listing_links)
        dom_inventory = self._search_dom_inventory(response)
        listing_ids = listing_ids_from_links(listing_links)
        unique_ids = set(listing_ids)
        duplicates_on_page = sum(1 for lid in unique_ids if lid in self.scraped_listings)

        self.total_duplicate_links += duplicates_on_page
        self.total_listings_found += len(listing_links)
        self._log_search_page_summary(
            current_page=current_page,
            listing_links=listing_links,
            unique_ids=unique_ids,
            duplicates_on_page=duplicates_on_page,
            annons_count=annons_count,
            bostad_count=bostad_count,
            dom_inventory=dom_inventory,
            response_url=response.url,
        )
        self._record_search_page_stats(
            current_page=current_page,
            listing_count=len(listing_links),
            unique_count=len(unique_ids),
            duplicates_on_page=duplicates_on_page,
            annons_count=annons_count,
            bostad_count=bostad_count,
        )

        yield from self._listing_requests(response, listing_links, current_page)

        next_request = self._next_search_page_request(current_page)
        if next_request is not None:
            yield next_request

    def _record_search_page_seen(self, response, current_page):
        self.logger.info(f"Processing page {current_page}/{self.max_pages}")
        self.logger.debug(f"Page URL: {response.url} (status {response.status})")
        self.crawler.stats.inc_value("booli/pages_seen", 1)
        self.pages_processed += 1

    def _search_listing_links(self, response, current_page):
        listing_links = resolve_listing_links(response)
        if listing_links:
            return listing_links

        self.logger.warning(
            f"No listing anchors found on page {current_page} "
            f"(status {response.status}); attempting Next.js fallback"
        )
        return self._fetch_listings_from_next_data(current_page)

    def _count_listing_link_types(self, listing_links):
        annons_count = sum(1 for link in listing_links if "/annons/" in link)
        bostad_count = sum(1 for link in listing_links if "/bostad/" in link)
        return annons_count, bostad_count

    def _search_dom_inventory(self, response):
        return {
            "containers": len(response.css("li.search-page__module-container article").getall()),
            "ad_wrappers": len(
                response.css("li.search-page__horizontal-space-container.ad-wrapper").getall()
            ),
            "sponsored": len(response.xpath("//*[contains(., 'Sponsrad artikel')]").getall()),
        }

    def _log_search_page_summary(
        self,
        *,
        current_page,
        listing_links,
        unique_ids,
        duplicates_on_page,
        annons_count,
        bostad_count,
        dom_inventory,
        response_url,
    ):
        self.logger.info(
            f"Found {len(listing_links)} listing anchors (annons: {annons_count}, bostad: {bostad_count}), "
            f"{len(unique_ids)} unique IDs on page {current_page} (seen before on this run: {duplicates_on_page}); "
            f"total anchors seen: {self.total_listings_found}"
        )
        self.logger.debug(
            f"Page {current_page} DOM inventory → containers: {dom_inventory['containers']}, "
            f"ad wrappers: {dom_inventory['ad_wrappers']}, sponsored: {dom_inventory['sponsored']}"
        )
        self.logger.debug(f"Response URL: {response_url}")
        if listing_links:
            self.logger.debug(f"Sample listing links: {listing_links[:3]}")
        else:
            self.logger.warning(
                f"No '/annons/' links extracted on page {current_page}. Will continue pagination until max_pages."
            )

    def _record_search_page_stats(
        self,
        *,
        current_page,
        listing_count,
        unique_count,
        duplicates_on_page,
        annons_count,
        bostad_count,
    ):
        self.crawler.stats.set_value(f"booli/page_{current_page}/anchors", listing_count)
        self.crawler.stats.set_value(f"booli/page_{current_page}/unique_ids", unique_count)
        self.crawler.stats.set_value(
            f"booli/page_{current_page}/duplicates_seen", duplicates_on_page
        )
        self.crawler.stats.set_value(f"booli/page_{current_page}/annons_links", annons_count)
        self.crawler.stats.set_value(f"booli/page_{current_page}/bostad_links", bostad_count)
        self.crawler.stats.inc_value("booli/anchors_total", listing_count)
        self.crawler.stats.inc_value("booli/unique_ids_total", unique_count)
        self.crawler.stats.inc_value("booli/duplicates_total", duplicates_on_page)

    def _listing_requests(self, response, listing_links, current_page):
        for listing_url in listing_links:
            try:
                request = self._listing_request(response, listing_url, current_page)
                if request is not None:
                    yield request
            except Exception as e:
                self.logger.warning(f"Error processing listing {listing_url}: {e}")
                continue

    def _listing_request(self, response, listing_url, current_page):
        if listing_url.startswith("/"):
            listing_url = response.urljoin(listing_url)

        listing_id = extract_listing_id(listing_url)

        if listing_id and listing_id not in self.scraped_listings:
            self.scraped_listings.add(listing_id)
            return scrapy.Request(
                url=listing_url,
                callback=self.parse_listing,
                meta={
                    "listing_id": listing_id,
                    "booli_slot": "detail",
                    "source_page": current_page,
                },
                headers=self._default_http_headers(),
            )

        self.crawler.stats.inc_value("booli/dedup_skipped", 1)
        return None

    def _next_search_page_request(self, current_page):
        try:
            if self.pages_processed >= self.max_pages:
                self.logger.info(f"Reached max pages limit ({self.max_pages})")
                return None
            else:
                next_page = current_page + 1
                next_url = self._build_search_url(page=next_page)
                self.logger.info(
                    f"Following pagination to page {next_page} via direct URL: {next_url}"
                )
                return scrapy.Request(
                    url=next_url,
                    callback=self.parse_search_results,
                    meta={"page": next_page, "booli_slot": "search"},
                    headers=self._default_http_headers(),
                )
        except Exception as e:
            self.logger.error(f"Pagination error on page {current_page}: {e}")
            import traceback

            self.logger.error(traceback.format_exc())
            raise

    def parse_listing(self, response):
        """Parse individual listing page"""
        listing_id = response.meta.get("listing_id")
        source_page = response.meta.get("source_page")
        if source_page is not None:
            self.last_processed_page = source_page

        try:
            self._hydrate_blocked_listing(response, listing_id)
            self.total_listings_processed += 1
            self._log_listing_start(listing_id, source_page, response.url)

            item = self._build_listing_item(response, listing_id, source_page)
            self._log_listing_success(item, listing_id, source_page)
            self._log_missing_listing_fields(item, listing_id)
            self._record_listing_stats(item)

            if (
                self.progress_log_interval > 0
                and self.total_listings_processed % self.progress_log_interval == 0
            ):
                self._log_progress()

            yield item

        except Exception as e:
            self.logger.error(f"Error parsing listing {listing_id}: {e}")

    def _hydrate_blocked_listing(self, response, listing_id):
        if not self._needs_next_data_fallback(response):
            return

        lid = listing_id or extract_listing_id(response.url)
        record = self._fetch_property_data_from_next(response.url, str(lid) if lid else "")
        if isinstance(record, dict) and record:
            response.meta["_booli_property_data"] = record

    def _needs_next_data_fallback(self, response) -> bool:
        page_text_snapshot = response.text or ""
        return (
            response.status in (401, 403, 429, 202)
            or "JavaScript is disabled" in page_text_snapshot
            or "AwsWafIntegration" in page_text_snapshot
        )

    def _log_listing_start(self, listing_id, source_page, url):
        if source_page is not None:
            self.logger.info(
                f"Processing listing {self.total_listings_processed} (ID: {listing_id}) "
                f"from page {source_page} - {url}"
            )
        else:
            self.logger.info(
                f"Processing listing {self.total_listings_processed} (ID: {listing_id}) - {url}"
            )

    def _build_listing_item(self, response, listing_id, source_page):
        item = BooliListingItem()
        item["listing_id"] = listing_id
        item["url"] = response.url
        item["scraped_at"] = datetime.now(UTC).isoformat()
        if source_page is not None:
            item["source_page"] = source_page

        listing_price = self._sanitize_price(self.extract_listing_price(response))
        sold_price = self._sanitize_price(self.extract_sold_price(response))

        item["listing_price"] = listing_price
        item["sold_price"] = sold_price
        item["address"] = self.extract_address(response)
        item["area"] = self.extract_area(response)
        item["municipality"] = self.extract_municipality(response)
        item["living_area"] = self.extract_living_area(response)
        item["rooms"] = self.extract_rooms(response)
        item["property_type"] = self.extract_property_type(response)
        item["construction_year"] = self.extract_construction_year(response)
        item["monthly_fee"] = self.extract_monthly_fee(response)
        item["price_per_sqm"] = self.extract_price_per_sqm(response)
        item["floor"] = self.extract_floor(response)
        item["elevator"] = self.extract_elevator(response)
        item["balcony"] = self.extract_balcony(response)
        item["sold_date"] = self.extract_sold_date(response)
        item["days_on_market"] = self.extract_days_on_market(response)
        item["price_change"] = self._resolve_price_change(
            listing_price, sold_price, self.extract_price_change(response)
        )
        item["description"] = self.extract_description(response)
        item["images"] = self.extract_images(response)
        return item

    def _resolve_price_change(self, listing_price, sold_price, extracted_change):
        if listing_price is not None and sold_price is not None:
            return sold_price - listing_price
        return extracted_change

    def _log_listing_success(self, item, listing_id, source_page):
        if source_page is not None:
            self.logger.info(
                f"Successfully scraped listing {listing_id} (page {source_page}): "
                f"{item.get('address', 'Unknown address')}"
            )
        else:
            self.logger.info(
                f"Successfully scraped listing {listing_id}: {item.get('address', 'Unknown address')}"
            )

    def _log_missing_listing_fields(self, item, listing_id):
        if item.get("listing_price") is None:
            self.logger.debug(f"Listing {listing_id} missing listing_price")
        if item.get("sold_price") is None:
            self.logger.debug(f"Listing {listing_id} missing sold_price")
        if item.get("living_area") is None:
            self.logger.debug(f"Listing {listing_id} missing living_area")
        if item.get("rooms") is None:
            self.logger.debug(f"Listing {listing_id} missing rooms")

    def _record_listing_stats(self, item):
        try:
            self.crawler.stats.inc_value("booli/listings_yielded", 1)
            if item.get("listing_price") is None:
                self.crawler.stats.inc_value("booli/missing/listing_price", 1)
            if item.get("sold_price") is None:
                self.crawler.stats.inc_value("booli/missing/sold_price", 1)
            if item.get("price_per_sqm") is None:
                self.crawler.stats.inc_value("booli/missing/price_per_sqm", 1)
            if item.get("sold_date") is None:
                self.crawler.stats.inc_value("booli/missing/sold_date", 1)
        except Exception:
            pass

    def _log_progress(self):
        """Log aggregate scraping progress to the console."""
        elapsed = (datetime.now() - self.start_time).total_seconds() or 1.0
        rate = self.total_listings_processed / elapsed
        pages_seen = self.pages_processed
        page_progress = f"{pages_seen}/{self.max_pages}" if self.max_pages else str(pages_seen)
        message = (
            "Progress: "
            f"Listings {self.total_listings_processed} (rate {rate:.2f}/s), "
            f"pages {page_progress} (last {self.last_processed_page}), "
            f"duplicates skipped {self.total_duplicate_links}"
        )
        self.logger.info(message)

        # Mirror to stdout for CLI runs where log formatting may differ
        print(
            f"[Booli] Listings {self.total_listings_processed} (rate {rate:.2f}/s) | "
            f"Pages {page_progress} (last {self.last_processed_page}) | "
            f"Duplicates {self.total_duplicate_links}",
            flush=True,
        )
