# Drogasil Product Scraper

A Scrapy project that collects rated (star-reviewed) products from Drogasil
brand-listing pages -- starting with Nivea -- into a CSV file. Shares the
Scrapy + Playwright(/Camoufox) setup from the sibling `magazine_luiza`
project: same Akamai edge (confirmed via the `errors.edgesuite.net` 403
page and the robots.txt block), same browser tuning.

Status: **work in progress**. Listing + product parsing, the rating filter
and CSV export are built and tested (19 items, 0 errors on a small run).

## How this site differs from Magazine Luiza

- **No rating on the listing page.** Drogasil's listing JSON (`__NEXT_DATA__`
  -> `pageProps.pageProps.results.products`) has no review/rating field at
  all, so products can't be pre-filtered before opening them (unlike Magazine
  Luiza's `reviewCount`). Every matching-brand product from the listing gets
  opened; items without a rating are dropped after the fact.
- **The rating isn't in `__NEXT_DATA__` either.** It comes from a third-party
  widget (Vurdere) that injects its own `<script type="application/ld+json">`
  `AggregateRating` node into the DOM after the page settles. The spider
  waits for `__NEXT_DATA__`, scrolls, then waits ~6s before reading the page,
  which reliably surfaces it (verified by hand before writing the spider).
- **Pricing and product data** come from `productData` (`price_aux.value_from`
  /`value_to`, `liveComposition.livePrice.pixPrice`, and a flat
  `custom_attributes` list keyed by `attribute_code` -- e.g. `marca`,
  `fabricante`, `quantidade`).
- **No marketplace seller text.** Drogasil sells directly (`is3p: false` on
  most items); `sold_by` is "Drogasil" unless a product is flagged as
  third-party.

## Running it

```bash
scrapy crawl brand -a category=beleza -a brand=Nivea -a start_page=1 -a max_pages=1 -o outputs/nivea.csv
SCRAPER_BROWSER_ENGINE=camoufox scrapy crawl brand -a category=beleza -a brand=Nivea -o outputs/nivea.csv  # fallback engine
```

`category` is the site section in the URL (`drogasil.com.br/{category}.html`)
and has to match wherever that brand's products actually live -- `beleza`
for Nivea; a different brand may sit under a different category.

`outputs/` is not committed (see `.gitignore`); only a synthetic example is
in this README.

```csv
search_term,title,sold_by,brand,manufacturer,quantity,regular_price,sale_price,pix_price,rating,review_count,url
Nivea,Creme Facial EXEMPLO Antissinais Q10 Power Dia 50g,Drogasil,Nivea,Beiersdorf,50g,58.99,49.55,,4.7,36,https://www.drogasil.com.br/exemplo-produto.html
```
