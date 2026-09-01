import os

BOT_NAME = "magazineluiza"

SPIDER_MODULES = ["magazineluiza.spiders"]
NEWSPIDER_MODULE = "magazineluiza.spiders"

# robots.txt also returns a 403 from Akamai -- not a real disallow rule
ROBOTSTXT_OBEY = False

CONCURRENT_REQUESTS_PER_DOMAIN = 1
DOWNLOAD_DELAY = 4  # 2s consistently triggered a block after ~35 pages (~21 req/min)

# Scrapy + Playwright: see README.md
DOWNLOAD_HANDLERS = {
    "http": "scrapy_playwright.handler.ScrapyPlaywrightDownloadHandler",
    "https": "scrapy_playwright.handler.ScrapyPlaywrightDownloadHandler",
}
TWISTED_REACTOR = "twisted.internet.asyncioreactor.AsyncioSelectorReactor"

PLAYWRIGHT_BROWSER_TYPE = "firefox"

# playwright (default, no extra dependency) or camoufox (heavier, more resilient)
SCRAPER_BROWSER_ENGINE = os.environ.get("SCRAPER_BROWSER_ENGINE", "playwright")

if SCRAPER_BROWSER_ENGINE == "camoufox":
    from camoufox.utils import launch_options as camoufox_launch_options

    PLAYWRIGHT_LAUNCH_OPTIONS = camoufox_launch_options(
        headless=True,
        humanize=True,
        os=["macos", "windows"],
        enable_cache=True,
        # block_images=True was tried and dropped: Camoufox itself warns
        # that blocking images is a known bot signal on major WAFs.
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
PLAYWRIGHT_PROCESS_REQUEST_HEADERS = None  # don't forward Scrapy's User-Agent to the browser

FEED_EXPORT_ENCODING = "utf-8"
