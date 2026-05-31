import inspect
import logging
import random

from scrapy import signals
from scrapy.downloadermiddlewares.retry import RetryMiddleware
from scrapy.exceptions import IgnoreRequest, NotConfigured
from twisted.internet import reactor
from twisted.internet.task import deferLater

# Scrapy 2.11/2.12: RetryMiddleware._retry(self, request, reason, spider)
# Scrapy 2.13+:     RetryMiddleware._retry(self, request, reason)
_RETRY_TAKES_SPIDER = "spider" in inspect.signature(RetryMiddleware._retry).parameters

try:
    from fake_useragent import UserAgent  # type: ignore
except ModuleNotFoundError:
    UserAgent = None


class BooliSpiderMiddleware:
    """Spider middleware for Booli-specific processing."""

    @classmethod
    def from_crawler(cls, crawler):
        s = cls()
        crawler.signals.connect(s.spider_opened, signal=signals.spider_opened)
        return s

    def process_spider_input(self, response, spider):
        return None

    def process_spider_output(self, response, result, spider):
        yield from result

    def process_spider_exception(self, response, exception, spider):
        spider.logger.error(f"Spider exception: {exception} for URL: {response.url}")

    def process_start_requests(self, start_requests, spider):
        yield from start_requests

    def spider_opened(self, spider):
        spider.logger.info("Spider opened: %s", spider.name)


class RotateUserAgentMiddleware:
    """Middleware to rotate User-Agent headers"""

    def __init__(self, user_agent_list=None, use_fake_useragent=True):
        self.user_agent_list = user_agent_list or []
        self.use_fake_useragent = use_fake_useragent

        self.ua = None
        if use_fake_useragent and UserAgent:
            try:
                self.ua = UserAgent()
            except Exception:
                logging.warning("Could not initialize fake-useragent, falling back to static list")
        elif use_fake_useragent and not UserAgent:
            logging.warning("fake-useragent package not available, using static user agents")

    @classmethod
    def from_crawler(cls, crawler):
        user_agent_list = crawler.settings.getlist("USER_AGENT_LIST")
        use_fake_useragent = crawler.settings.getbool("USE_FAKE_USERAGENT", True)

        if not user_agent_list and not use_fake_useragent:
            raise NotConfigured("No user agents configured")

        return cls(user_agent_list=user_agent_list, use_fake_useragent=use_fake_useragent)

    def process_request(self, request, spider):
        # Get random user agent
        if self.ua and self.use_fake_useragent:
            try:
                ua = self.ua.random
            except Exception:
                ua = self.get_static_user_agent()
        else:
            ua = self.get_static_user_agent()

        request.headers["User-Agent"] = ua
        return None

    def get_static_user_agent(self):
        """Get user agent from static list"""
        default_agents = [
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Firefox/121.0",
        ]

        agents = self.user_agent_list if self.user_agent_list else default_agents
        return random.choice(agents)


class ProxyMiddleware:
    """Middleware for proxy rotation (optional)"""

    def __init__(self, proxy_list=None):
        self.proxy_list = proxy_list or []

    @classmethod
    def from_crawler(cls, crawler):
        proxy_list = crawler.settings.getlist("PROXY_LIST", [])
        return cls(proxy_list=proxy_list)

    def process_request(self, request, spider):
        if self.proxy_list:
            proxy = random.choice(self.proxy_list)
            request.meta["proxy"] = proxy
            spider.logger.debug(f"Using proxy: {proxy}")
        return None


class BooliDownloaderMiddleware:
    """Custom downloader middleware for Booli-specific handling"""

    def __init__(self, settings):
        self.enable_screenshots = settings.getbool("BOOLI_ENABLE_SCREENSHOTS", False)
        self._active_requests = 0
        self._peak_requests = 0

    @classmethod
    def from_crawler(cls, crawler):
        return cls(crawler.settings)

    def process_request(self, request, spider):
        # Add Swedish language headers for better results
        request.headers.update(
            {
                "Accept-Language": "sv-SE,sv;q=0.9,en;q=0.8",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
                "Accept-Encoding": "gzip, deflate, br",
                "DNT": "1",
                "Connection": "keep-alive",
                "Upgrade-Insecure-Requests": "1",
            }
        )

        slot = request.meta.get("booli_slot")
        if slot == "search":
            delay = random.uniform(0.25, 0.5)
        else:
            delay = random.uniform(0.05, 0.2)

        self._active_requests += 1
        if self._active_requests > self._peak_requests:
            self._peak_requests = self._active_requests
        spider.crawler.stats.set_value("booli/concurrency/current", self._active_requests)
        spider.crawler.stats.set_value("booli/concurrency/peak", self._peak_requests)

        spider.logger.debug(f"Applying downloader delay of {delay:.2f}s for {request.url}")
        return deferLater(reactor, delay, lambda: None)

    def process_response(self, request, response, spider):
        if self._active_requests > 0:
            self._active_requests -= 1
            spider.crawler.stats.set_value("booli/concurrency/current", self._active_requests)

        if response.status == 403:
            spider.logger.warning(f"403 Forbidden for URL: {request.url}")

        elif response.status == 429:
            spider.logger.warning(f"429 Too Many Requests for URL: {request.url}")

            max_retries = spider.crawler.settings.getint("RETRY_TIMES", 3)
            retries = request.meta.get("booli_429_retries", 0) + 1
            if retries > max_retries:
                spider.logger.error(
                    f"429 retries exhausted ({retries}/{max_retries}) for {request.url}"
                )
                raise IgnoreRequest(f"429 retries exhausted for {request.url}")

            delay = random.uniform(30, 60)
            spider.logger.info(
                f"Backing off for {delay:.1f}s before re-issuing {request.url} "
                f"(attempt {retries}/{max_retries})"
            )
            new_request = request.replace(dont_filter=True)
            new_request.meta["booli_429_retries"] = retries
            return deferLater(reactor, delay, lambda: new_request)

        elif response.status in [500, 502, 503, 504]:
            spider.logger.warning(f"Server error {response.status} for URL: {request.url}")

        return response

    def process_exception(self, request, exception, spider):
        if self._active_requests > 0:
            self._active_requests -= 1
            spider.crawler.stats.set_value("booli/concurrency/current", self._active_requests)
        spider.logger.error(f"Request exception: {exception} for URL: {request.url}")
        return None


class SmartRetryMiddleware(RetryMiddleware):
    """Enhanced retry middleware with exponential backoff"""

    def __init__(self, settings):
        super().__init__(settings)
        self.base_delay = settings.getfloat("RETRY_BASE_DELAY", 5.0)
        self.max_delay = settings.getfloat("RETRY_MAX_DELAY", 60.0)

    @classmethod
    def from_crawler(cls, crawler):
        return cls(crawler.settings)

    def process_response(self, request, response, spider):
        if response.status in self.retry_http_codes:
            reason = response_status_message(response.status)

            # Calculate exponential backoff delay
            retry_times = request.meta.get("retry_times", 0) + 1
            delay = min(self.base_delay * (2**retry_times), self.max_delay)

            spider.logger.info(
                f"Retrying {request.url} (attempt {retry_times}) after {delay:.1f}s delay"
            )

            def _retry_operation():
                if _RETRY_TAKES_SPIDER:
                    result = self._retry(request, reason, spider)
                else:
                    result = self._retry(request, reason)
                if result is None:
                    raise IgnoreRequest(f"retries exhausted: {reason}")
                return result

            return deferLater(reactor, delay, _retry_operation)

        return response


class AntiCaptchaMiddleware:
    """Detect CAPTCHA-like responses and log them for follow-up."""

    _CAPTCHA_INDICATORS = ("captcha", "recaptcha", "cloudflare", "ray id", "blocked", "robot")

    def process_response(self, request, response, spider):
        response_text = response.text.lower() if hasattr(response, "text") else ""
        if any(indicator in response_text for indicator in self._CAPTCHA_INDICATORS):
            spider.logger.warning(f"Potential CAPTCHA detected on {request.url}")
        return response


class SessionMiddleware:
    """Middleware to maintain session state"""

    def __init__(self):
        self.session_data = {}

    def process_request(self, request, spider):
        # Add session cookies if available
        spider_session = self.session_data.get(spider.name, {})
        if spider_session.get("cookies"):
            request.cookies.update(spider_session["cookies"])

        return None

    def process_response(self, request, response, spider):
        # Store session cookies
        if spider.name not in self.session_data:
            self.session_data[spider.name] = {}

        if hasattr(response, "cookies"):
            self.session_data[spider.name]["cookies"] = dict(response.cookies)

        return response


def response_status_message(status):
    """Get human-readable status message"""
    status_messages = {
        403: "Forbidden",
        404: "Not Found",
        429: "Too Many Requests",
        500: "Internal Server Error",
        502: "Bad Gateway",
        503: "Service Unavailable",
        504: "Gateway Timeout",
    }
    return status_messages.get(status, f"HTTP {status}")
