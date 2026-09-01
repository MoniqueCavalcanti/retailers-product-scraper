import json
from urllib.parse import quote

import scrapy
from scrapy_playwright.page import PageMethod

from items import ProductItem

WAIT_NEXT_DATA = PageMethod(
    "wait_for_selector", "script#__NEXT_DATA__", state="attached", timeout=20000
)

# The star rating comes from a third-party widget (Vurdere) that injects its
# own <script type="application/ld+json"> tag into the DOM after the page
# settles -- it isn't part of Next.js's own __NEXT_DATA__. A scroll plus a
# few seconds of wait reliably makes it appear (verified by hand first).
WAIT_PRODUCT = [
    WAIT_NEXT_DATA,
    PageMethod("evaluate", "window.scrollTo(0, document.body.scrollHeight / 2)"),
    PageMethod("wait_for_timeout", 6000),
]


def extract_next_data(response):
    raw = response.css("script#__NEXT_DATA__::text").get()
    return json.loads(raw)


def find_aggregate_rating(response):
    for raw in response.css('script[type="application/ld+json"]::text').getall():
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            continue
        nodes = data if isinstance(data, list) else [data]
        for node in nodes:
            if isinstance(node, dict) and node.get("@type") == "AggregateRating":
                return node
    return None


def custom_attribute(product_data, code):
    for attr in product_data.get("custom_attributes") or []:
        if attr.get("attribute_code") != code:
            continue
        values = attr.get("value")
        if values:
            return values[0].get("label", "")
        strings = attr.get("value_string") or []
        return strings[0] if strings else ""
    return ""


def seller_text(product_data):
    if not product_data.get("is3p"):
        return "Drogasil"
    seller = product_data.get("seller") or {}
    return seller.get("name") or "Terceiro"


def build_listing_request(category, brand, page, callback):
    url = f"https://www.drogasil.com.br/{category}.html?p={page}&facets=filters.Marca%3A{quote(brand)}"
    return scrapy.Request(
        url,
        meta={"playwright": True, "playwright_page_methods": [WAIT_NEXT_DATA]},
        callback=callback,
        cb_kwargs={"page": page},
    )


class BrandSpider(scrapy.Spider):
    name = "brand"
    allowed_domains = ["drogasil.com.br"]

    def __init__(self, category="beleza", brand="Nivea", start_page="1", max_pages="1", *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.category = category
        self.brand = brand
        self.start_page = int(start_page)
        self.max_pages = int(max_pages)

    async def start(self):
        yield build_listing_request(self.category, self.brand, page=self.start_page, callback=self.parse_listing)

    def parse_listing(self, response, page):
        data = extract_next_data(response)
        inner = data["props"]["pageProps"]["pageProps"]
        products = inner["results"]["products"]

        matching = [p for p in products if (p.get("brand") or "").lower() == self.brand.lower()]
        self.logger.info(
            "page %s: %s products, %s matching brand",
            page, len(products), len(matching),
        )

        for product in matching:
            product_url = response.urljoin(product["url"])
            yield scrapy.Request(
                product_url,
                meta={"playwright": True, "playwright_page_methods": WAIT_PRODUCT},
                callback=self.parse_product,
            )

        if page < self.max_pages and page < inner["metadata"]["pages"]:
            yield build_listing_request(self.category, self.brand, page + 1, callback=self.parse_listing)

    def parse_product(self, response):
        rating_node = find_aggregate_rating(response)
        if rating_node is None:
            self.logger.debug("skipping (no rating): %s", response.url)
            return

        data = extract_next_data(response)
        product_data = data["props"]["pageProps"]["productData"]

        price_aux = product_data.get("price_aux") or {}
        live_price = ((product_data.get("liveComposition") or {}).get("livePrice") or {})

        yield ProductItem(
            search_term=self.brand,
            title=product_data.get("name", ""),
            sold_by=seller_text(product_data),
            brand=custom_attribute(product_data, "marca"),
            manufacturer=custom_attribute(product_data, "fabricante"),
            quantity=custom_attribute(product_data, "quantidade"),
            regular_price=price_aux.get("value_from"),
            sale_price=price_aux.get("value_to"),
            pix_price=live_price.get("pixPrice"),
            rating=float(rating_node["ratingValue"]) if rating_node.get("ratingValue") else None,
            review_count=int(rating_node["reviewCount"]) if rating_node.get("reviewCount") else None,
            url=response.url,
        )
