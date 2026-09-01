import os

BOT_NAME = "magazineluiza"

SPIDER_MODULES = ["magazineluiza.spiders"]
NEWSPIDER_MODULE = "magazineluiza.spiders"

# robots.txt tambem retorna 403 do Akamai -- nao e uma regra de disallow real
ROBOTSTXT_OBEY = False

CONCURRENT_REQUESTS_PER_DOMAIN = 1
DOWNLOAD_DELAY = 4  # 2s levava a bloqueio apos ~35 paginas seguidas (~21 req/min)

# Scrapy + Playwright: ver README.md
DOWNLOAD_HANDLERS = {
    "http": "scrapy_playwright.handler.ScrapyPlaywrightDownloadHandler",
    "https": "scrapy_playwright.handler.ScrapyPlaywrightDownloadHandler",
}
TWISTED_REACTOR = "twisted.internet.asyncioreactor.AsyncioSelectorReactor"

PLAYWRIGHT_BROWSER_TYPE = "firefox"

# playwright (padrao, sem dependencia extra) ou camoufox (mais pesado, mais resiliente)
SCRAPER_BROWSER_ENGINE = os.environ.get("SCRAPER_BROWSER_ENGINE", "playwright")

if SCRAPER_BROWSER_ENGINE == "camoufox":
    from camoufox.utils import launch_options as camoufox_launch_options

    PLAYWRIGHT_LAUNCH_OPTIONS = camoufox_launch_options(
        headless=True,
        humanize=True,
        os=["macos", "windows"],
        enable_cache=True,
        # block_images=True foi testado e removido: o proprio Camoufox avisa
        # que bloquear imagem e um sinal de bot pra WAFs como o Akamai.
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
PLAYWRIGHT_PROCESS_REQUEST_HEADERS = None  # nao repassar o User-Agent do Scrapy pro navegador

FEED_EXPORT_ENCODING = "utf-8"
