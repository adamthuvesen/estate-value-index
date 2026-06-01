"""
Scrapy settings for Booli ingestion project
"""

import os

BOT_NAME = "booli_crawler"

SPIDER_MODULES = ["estate_value_index.ingestion.booli.spiders"]
NEWSPIDER_MODULE = "estate_value_index.ingestion.booli.spiders"

# Obey robots.txt rules — respect the target site's crawl directives.
ROBOTSTXT_OBEY = True

# Identify the crawler honestly instead of rotating/spoofing user agents.
USER_AGENT = "booli_crawler (+https://github.com/adamthuvesen/estate-value-index)"

# Configure pipelines
# Note: BigQuery writes handled by processing pipeline (not during scraping)
ITEM_PIPELINES = {
    "estate_value_index.ingestion.booli.pipelines.DuplicateFilterPipeline": 200,
    "estate_value_index.ingestion.booli.pipelines.BooliPipeline": 300,
    "estate_value_index.ingestion.booli.pipelines.DataValidationPipeline": 400,
    "estate_value_index.ingestion.booli.pipelines.JsonWriterPipeline": 500,
    "estate_value_index.ingestion.booli.pipelines.ImageDownloadPipeline": 600,
    "estate_value_index.ingestion.booli.pipelines.StatsPipeline": 700,
    "estate_value_index.ingestion.booli.pipelines.ErrorHandlingPipeline": 800,
}

# Configure downloader middlewares
# Anti-detection middlewares (user-agent rotation, proxy rotation, captcha
# handling) are intentionally omitted — the crawler identifies itself honestly
# and backs off rather than evading bot controls.
DOWNLOADER_MIDDLEWARES = {
    "estate_value_index.ingestion.core.middlewares.BooliDownloaderMiddleware": 400,
    "estate_value_index.ingestion.core.middlewares.SmartRetryMiddleware": 500,
    "estate_value_index.ingestion.core.middlewares.SessionMiddleware": 700,
}

# Configure a delay for requests for the same website (default: 0)
DOWNLOAD_DELAY = 0.5
# The download delay setting will honor only one of:
RANDOMIZE_DOWNLOAD_DELAY = True

# Configure maximum concurrent requests performed by Scrapy (default: 16)
CONCURRENT_REQUESTS = 8
CONCURRENT_REQUESTS_PER_DOMAIN = 4

# Disable cookies (enabled by default)
COOKIES_ENABLED = True

# Disable Telnet Console (enabled by default)
TELNETCONSOLE_ENABLED = False

# Override the default request headers:
DEFAULT_REQUEST_HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "sv-SE,sv;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "DNT": "1",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
}

# Enable or disable spider middlewares
SPIDER_MIDDLEWARES = {
    "estate_value_index.ingestion.core.middlewares.BooliSpiderMiddleware": 543,
}

# Enable AutoThrottle extension if available
AUTOTHROTTLE_ENABLED = True
AUTOTHROTTLE_START_DELAY = 1
AUTOTHROTTLE_MAX_DELAY = 6
AUTOTHROTTLE_TARGET_CONCURRENCY = 2.5
AUTOTHROTTLE_DEBUG = False

# Extensions
EXTENSIONS = {
    "scrapy.extensions.closespider.CloseSpider": 500,
}

# Configure the maximum number of pages to crawl
CLOSESPIDER_ITEMCOUNT = 1000
CLOSESPIDER_PAGECOUNT = 100
CLOSESPIDER_TIMEOUT = 3600  # 1 hour

# Output settings
OUTPUT_DIR = os.getenv("BOOLI_OUTPUT_DIR", "data/raw/booli")
IMAGE_STORE = os.getenv("BOOLI_IMAGE_STORE", "data/images/raw/booli")
DOWNLOAD_IMAGES = False

# BigQuery settings removed - BigQuery writes now handled by processing pipeline
# This avoids streaming buffer conflicts with MERGE operations

# Retry settings — retry only on transient server/network errors. Do not retry
# on 403 (Forbidden) or 429 (Too Many Requests): treat those as the site asking
# us to stop rather than something to push through.
RETRY_TIMES = 3
RETRY_HTTP_CODES = [500, 502, 503, 504, 408]
RETRY_BASE_DELAY = 5.0
RETRY_MAX_DELAY = 300.0

# Logging settings
LOG_LEVEL = "DEBUG"
LOG_FORMAT = "%(levelname)s: %(message)s"
LOG_FILE = os.getenv("BOOLI_LOG_FILE", "logs/ingestion/booli.log")

# Cache settings (for development)
HTTPCACHE_ENABLED = False
HTTPCACHE_EXPIRATION_SECS = 3600
HTTPCACHE_DIR = "cache"

# Selenium settings
SELENIUM_DRIVER_NAME = "chrome"
SELENIUM_DRIVER_EXECUTABLE_PATH = None
SELENIUM_BROWSER_EXECUTABLE_PATH = None
SELENIUM_DRIVER_ARGUMENTS = [
    "--headless",
    "--no-sandbox",
    "--disable-dev-shm-usage",
    "--disable-gpu",
    "--disable-extensions",
    "--disable-plugins",
    "--disable-images",
]

# Request fingerprinting
REQUEST_FINGERPRINTER_IMPLEMENTATION = "2.7"

# Feed exports disabled - using command-line -o flag instead
# FEEDS = {
#     'data/debug_listings.json': {
#         'format': 'json',
#         'encoding': 'utf8',
#         'fields': None,
#         'indent': 2,
#     }
# }

# Booli-specific settings
BOOLI_ENABLE_SCREENSHOTS = False
BOOLI_MAX_PAGES = 50
BOOLI_REQUEST_TIMEOUT = 30

# Database settings (if using database output)
DATABASE_URL = None
DB_SETTINGS = {
    "engine": "postgresql",
    "host": "localhost",
    "port": 5432,
    "database": "booli_scraping",
    "username": "postgres",
    "password": os.getenv("BOOLI_DB_PASSWORD", ""),
}

# Email settings (for notifications)
EMAIL_ENABLED = False
EMAIL_HOST = "smtp.gmail.com"
EMAIL_PORT = 587
EMAIL_FROM = "your-email@gmail.com"
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD", "")
EMAIL_TO = ["admin@example.com"]

# Monitoring settings
MONITOR_ENABLED = False
MONITOR_INTERVAL = 300  # 5 minutes

# Stats collection
STATS_CLASS = "scrapy.statscollectors.MemoryStatsCollector"

# Duplicate filter
DUPEFILTER_CLASS = "scrapy.dupefilters.RFPDupeFilter"
DUPEFILTER_DEBUG = False

# Depth middleware
DEPTH_MIDDLEWARE_ENABLED = False

# URL length limit
URLLENGTH_LIMIT = 2083

# Redirect middleware
REDIRECT_ENABLED = True
REDIRECT_MAX_TIMES = 20
REDIRECT_PRIORITY_ADJUST = +2

# Meta refresh middleware
METAREFRESH_ENABLED = True
METAREFRESH_MAXDELAY = 100

# Custom settings for different environments
try:
    from .local_settings import *
except ImportError:
    pass
