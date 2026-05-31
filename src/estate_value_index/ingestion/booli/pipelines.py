import json
import os
from datetime import datetime

from itemadapter import ItemAdapter
from scrapy import signals

from estate_value_index.ingestion.booli.normalization import (
    clean_text,
    ensure_list,
    to_bool,
    to_float,
    to_int,
)

_UNRECOGNISED_TOKEN_LOG_LIMIT = 20


class BooliPipeline:
    """Main pipeline for processing Booli items"""

    def __init__(self):
        # (field, value) pairs we have already logged this run, plus a counter
        # for the closing summary. See close_spider.
        self._unrecognised_seen: set[tuple[str, object]] = set()
        self._unrecognised_counts: dict[tuple[str, object], int] = {}

    def open_spider(self, spider):  # noqa: D401 - Scrapy hook
        self._unrecognised_seen = set()
        self._unrecognised_counts = {}

    def close_spider(self, spider):  # noqa: D401 - Scrapy hook
        if self._unrecognised_counts:
            summary = ", ".join(
                f"{field}={value!r}:{count}"
                for (field, value), count in sorted(self._unrecognised_counts.items())
            )
            spider.logger.warning("Unrecognised boolean tokens summary: %s", summary)

    def process_item(self, item, spider):
        """Process and validate items"""
        adapter = ItemAdapter(item)

        # Basic validation
        if not adapter.get("listing_id"):
            spider.logger.warning(f"Missing listing_id for item: {dict(adapter)}")
            return None

        # Clean up text fields
        text_fields = ("address", "area", "municipality", "property_type", "description")
        for field in text_fields:
            adapter[field] = clean_text(adapter.get(field))

        float_fields = ("living_area",)
        int_fields = (
            "listing_price",
            "sold_price",
            "price_per_sqm",
            "monthly_fee",
            "rooms",
            "construction_year",
            "days_on_market",
            "price_change",
            "floor",
            "source_page",
        )

        for field in float_fields:
            raw_value = adapter.get(field)
            converted = to_float(raw_value)
            if raw_value is not None and converted is None:
                spider.logger.warning(f"Could not convert {field} to float: {raw_value}")
            adapter[field] = converted

        for field in int_fields:
            raw_value = adapter.get(field)
            converted = to_int(raw_value)
            if raw_value is not None and converted is None:
                spider.logger.warning(f"Could not convert {field} to integer: {raw_value}")
            adapter[field] = converted

        for field in ("balcony", "elevator"):
            raw_value = adapter.get(field)
            converted = to_bool(raw_value)
            if converted is None and raw_value is not None and raw_value != "":
                # Don't fall back to bool(raw_value) — bool('no') is True, which
                # silently corrupts amenity features. Keep the value nullable
                # and log enough to surface HTML format changes.
                key = (field, raw_value)
                self._unrecognised_counts[key] = self._unrecognised_counts.get(key, 0) + 1
                if (
                    key not in self._unrecognised_seen
                    and len(self._unrecognised_seen) < _UNRECOGNISED_TOKEN_LOG_LIMIT
                ):
                    self._unrecognised_seen.add(key)
                    spider.logger.warning(
                        "Unrecognised boolean token for %s: %r (listing_id=%s)",
                        field,
                        raw_value,
                        adapter.get("listing_id"),
                    )
            adapter[field] = converted

        adapter["images"] = ensure_list(adapter.get("images"))

        spider.logger.debug(f"Processed item: {adapter['listing_id']}")
        return item


class JsonWriterPipeline:
    """Pipeline to write items to JSON files"""

    def __init__(self, output_dir="data/raw/booli"):
        self.output_dir = output_dir
        self.file_handles = {}

    @classmethod
    def from_crawler(cls, crawler):
        output_dir = crawler.settings.get("OUTPUT_DIR", "data")
        return cls(output_dir=output_dir)

    def open_spider(self, spider):
        """Create output directory and file handles"""
        if not os.path.exists(self.output_dir):
            os.makedirs(self.output_dir)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        # Listings file - use .jsonl extension for JSONL format
        listings_file = os.path.join(self.output_dir, f"booli_listings_{timestamp}.jsonl")
        self.file_handles["listings"] = open(listings_file, "w", encoding="utf-8")

        spider.logger.info(f"Writing listings to: {listings_file}")

    def close_spider(self, spider):
        """Close file handles"""
        for handle in self.file_handles.values():
            handle.close()
        spider.logger.info("JSON files closed")

    def process_item(self, item, spider):
        """Write item to appropriate JSON file"""
        adapter = ItemAdapter(item)

        # Determine file type based on item type
        if "BooliListingItem" in str(type(item)):
            file_key = "listings"
        else:
            spider.logger.warning(f"Unknown item type: {type(item)}")
            return item

        # Write JSON line. Flush so a `kill -9` mid-crawl preserves all
        # already-emitted records (no fsync, no atomic rename — just a flush).
        line = json.dumps(adapter.asdict(), ensure_ascii=False, default=str)
        self.file_handles[file_key].write(line + "\n")
        self.file_handles[file_key].flush()

        return item


class DataValidationPipeline:
    """Pipeline to validate data quality and completeness"""

    def process_item(self, item, spider):
        """Validate item data quality"""
        adapter = ItemAdapter(item)

        # Check for required fields
        required_fields = ["listing_id", "url", "scraped_at"]
        for field in required_fields:
            if not adapter.get(field):
                spider.logger.error(
                    f"Missing required field '{field}' in item: {adapter.get('listing_id')}"
                )

        # Validate price ranges
        for price_field in ["listing_price", "sold_price"]:
            price_val = to_int(adapter.get(price_field))
            if price_val is not None:
                if price_val < 100000 or price_val > 50000000:  # SEK range
                    spider.logger.warning(
                        f"Unusual {price_field} value: {price_val} for listing {adapter.get('listing_id')}"
                    )

        # Validate area ranges
        living_area = to_float(adapter.get("living_area"))
        if living_area is not None:
            if living_area < 10 or living_area > 500:  # m² range
                spider.logger.warning(
                    f"Unusual living area: {living_area} for listing {adapter.get('listing_id')}"
                )

        # Validate room count
        rooms = to_int(adapter.get("rooms"))
        if rooms is not None:
            if rooms < 1 or rooms > 10:
                spider.logger.warning(
                    f"Unusual room count: {rooms} for listing {adapter.get('listing_id')}"
                )

        return item


class DuplicateFilterPipeline:
    """Pipeline to filter out duplicate listings"""

    def __init__(self):
        self.seen_ids = set()

    def process_item(self, item, spider):
        """Filter out duplicate listings"""
        adapter = ItemAdapter(item)
        listing_id = adapter.get("listing_id")

        if listing_id in self.seen_ids:
            spider.logger.info(f"Duplicate listing filtered: {listing_id}")
            from scrapy.exceptions import DropItem

            raise DropItem(f"Duplicate listing: {listing_id}")
        else:
            self.seen_ids.add(listing_id)
            return item


class ImageDownloadPipeline:
    """Pipeline to download and process images"""

    def __init__(self, download_images=False, image_store="images"):
        self.download_images = download_images
        self.image_store = image_store

    @classmethod
    def from_crawler(cls, crawler):
        download_images = crawler.settings.getbool("DOWNLOAD_IMAGES", False)
        image_store = crawler.settings.get("IMAGE_STORE", "images")
        return cls(download_images=download_images, image_store=image_store)

    def open_spider(self, spider):
        """Create image directory"""
        if self.download_images and not os.path.exists(self.image_store):
            os.makedirs(self.image_store)

    def process_item(self, item, spider):
        """Process images if enabled"""
        if not self.download_images:
            return item

        adapter = ItemAdapter(item)
        listing_id = adapter.get("listing_id")
        images = adapter.get("images", [])

        if images and listing_id:
            spider.logger.info(f"Downloaded {len(images)} images for listing {listing_id}")

        return item


class StatsPipeline:
    """Pipeline to collect statistics about scraped data"""

    def __init__(self):
        self.items_count = 0
        self.listings_count = 0
        self.errors_count = 0
        self.last_log_time = None

    @classmethod
    def from_crawler(cls, crawler):
        pipeline = cls()
        crawler.signals.connect(pipeline.spider_closed, signal=signals.spider_closed)
        return pipeline

    def process_item(self, item, spider):
        """Count items"""
        self.items_count += 1

        if "BooliListingItem" in str(type(item)):
            self.listings_count += 1

        # Log progress every 10 items
        if self.items_count % 10 == 0:
            self._log_progress(spider)

        return item

    def _log_progress(self, spider):
        """Log current progress."""
        current_time = datetime.now()

        if self.last_log_time:
            time_diff = current_time - self.last_log_time
            rate = 10 / time_diff.total_seconds() if time_diff.total_seconds() > 0 else 0
            spider.logger.info(
                f"Progress: {self.listings_count} listings processed ({rate:.1f}/sec)"
            )

        self.last_log_time = current_time

    def spider_closed(self, spider):
        """Log final statistics"""
        spider.logger.info("Final scraping statistics:")
        spider.logger.info(f"  Total items processed: {self.items_count}")
        spider.logger.info(f"  Listings scraped: {self.listings_count}")
        spider.logger.info("Crawl completed successfully!")


class ErrorHandlingPipeline:
    """Pipeline for handling and logging errors"""

    def process_item(self, item, spider):
        """Log successful item processing"""
        adapter = ItemAdapter(item)
        listing_id = adapter.get("listing_id")

        if listing_id:
            spider.logger.debug(f"Successfully processed item: {listing_id}")

        return item

    def close_spider(self, spider):
        """Log final summary"""
        spider.logger.info(f"Scraping completed for spider: {spider.name}")
