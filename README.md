# Retailers Product Scraper

Scrapy + Playwright(/Camoufox) scrapers that collect rated (star-reviewed)
products from Brazilian retailer sites into CSV, one project per retailer.
Both sit behind Akamai; the browser-automation approach and anti-bot
findings are documented in `magazine_luiza/README.md` and reused as-is.

- [`magazine_luiza/`](magazine_luiza/) -- Magazine Luiza (started with Nivea)
- [`drogasil/`](drogasil/) -- Drogasil (started with Nivea)

## Setup

One shared virtual environment at the repo root, used by both projects:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r magazine_luiza/requirements.txt
python -m camoufox fetch  # optional, only for SCRAPER_BROWSER_ENGINE=camoufox
```

Then `cd` into whichever project you want to run (`scrapy.cfg` marks each
one's own root) and see that project's README for its spider arguments.
