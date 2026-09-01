import os

BOT_NAME = "drogasil"

SPIDER_MODULES = ["spiders"]
NEWSPIDER_MODULE = "spiders"

# robots.txt also returns a 403 from Akamai -- not a real disallow rule
ROBOTSTXT_OBEY = False

CONCURRENT_REQUESTS_PER_DOMAIN = 1
DOWNLOAD_DELAY = 4

from scrapy.settings.default_settings import RETRY_EXCEPTIONS as _DEFAULT_RETRY_EXCEPTIONS
from scrapy.settings.default_settings import RETRY_HTTP_CODES as _DEFAULT_RETRY_HTTP_CODES

RETRY_TIMES = 3
RETRY_HTTP_CODES = _DEFAULT_RETRY_HTTP_CODES + [403]
RETRY_EXCEPTIONS = _DEFAULT_RETRY_EXCEPTIONS + ["playwright._impl._errors.TimeoutError"]

CLOSESPIDER_ERRORCOUNT = 10

DOWNLOAD_HANDLERS = {
    "http": "scrapy_playwright.handler.ScrapyPlaywrightDownloadHandler",
    "https": "scrapy_playwright.handler.ScrapyPlaywrightDownloadHandler",
}
TWISTED_REACTOR = "twisted.internet.asyncioreactor.AsyncioSelectorReactor"

PLAYWRIGHT_BROWSER_TYPE = "firefox"

SCRAPER_BROWSER_ENGINE = os.environ.get("SCRAPER_BROWSER_ENGINE", "playwright")

if SCRAPER_BROWSER_ENGINE == "camoufox":
    from camoufox.utils import launch_options as camoufox_launch_options

    PLAYWRIGHT_LAUNCH_OPTIONS = camoufox_launch_options(
        headless=True,
        humanize=True,
        os=["macos", "windows"],
        enable_cache=True,
    )
    PLAYWRIGHT_CONTEXTS = {}
else:
    PLAYWRIGHT_LAUNCH_OPTIONS = {
        "headless": True,
        "firefox_user_prefs": {
            "dom.webdriver.enabled": False,
            "marionette.enabled": False,
            "pdfjs.disabled": False,
            "intl.accept_languages": "pt-BR, pt, en-US, en",
        },
    }
    PLAYWRIGHT_CONTEXTS = {
        "default": {
            "locale": "pt-BR",
            "viewport": {"width": 1280, "height": 720},
        }
    }

PLAYWRIGHT_DEFAULT_NAVIGATION_TIMEOUT = 30_000
PLAYWRIGHT_PROCESS_REQUEST_HEADERS = None

FEED_EXPORT_ENCODING = "utf-8"
