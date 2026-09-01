import json

import scrapy
from scrapy_playwright.page import PageMethod

from magazineluiza.items import ProductItem

WAIT_NEXT_DATA = PageMethod(
    "wait_for_selector", "script#__NEXT_DATA__", state="attached", timeout=20000
)


def extract_next_data(response):
    raw = response.css("script#__NEXT_DATA__::text").get()
    return json.loads(raw)


def build_listing_request(term, page, callback):
    # /marcas/ is the official brand catalog, already free of off-brand
    # items (unlike /busca/, which ranks by relevance)
    url = f"https://www.magazineluiza.com.br/marcas/{term}/"
    if page > 1:
        url += f"?page={page}"
    return scrapy.Request(
        url,
        meta={"playwright": True, "playwright_page_methods": [WAIT_NEXT_DATA]},
        callback=callback,
        cb_kwargs={"page": page},
    )


def matches_brand(item, term):
    brand = (item.get("brand") or {}).get("slug", "")
    return brand.lower() == term.lower()


def seller_text(seller):
    sold_by = seller.get("name") or seller.get("description") or ""
    delivered_by = seller.get("deliveryDescription") or ""
    if not sold_by:
        return ""
    if not delivered_by:
        return f"Vendido por {sold_by}"
    if sold_by.strip().lower() == delivered_by.strip().lower():
        return f"Vendido e entregue por {delivered_by}"
    return f"Vendido por {sold_by} e entregue por {delivered_by}"


def factsheet_fields(item):
    for group in item.get("factsheet") or []:
        if group.get("displayName") != "Ficha-Técnica":
            continue
        result = {}
        for element in group.get("elements", []):
            key = element.get("keyName")
            values = element.get("elements") or []
            value = values[0].get("value", "") if values else ""
            if key:
                result[key] = value
        return result
    return {}


class BrandSpider(scrapy.Spider):
    name = "brand"
    allowed_domains = ["magazineluiza.com.br"]

    def __init__(self, term="nivea", start_page="1", max_pages="1", *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.term = term
        self.start_page = int(start_page)
        self.max_pages = int(max_pages)

    async def start(self):
        yield build_listing_request(self.term, page=self.start_page, callback=self.parse_listing)

    def parse_listing(self, response, page):
        data = extract_next_data(response)
        listing = data["props"]["pageProps"]["data"]["brand"]

        relevant_items = [
            item for item in listing["items"]
            if item.get("reviewCount", 0) > 0 and matches_brand(item, self.term)
        ]
        self.logger.info(
            "page %s: %s products, %s rated and matching brand",
            page, len(listing["items"]), len(relevant_items),
        )

        for item in relevant_items:
            product_url = response.urljoin(item["path"])
            yield scrapy.Request(
                product_url,
                meta={"playwright": True, "playwright_page_methods": [WAIT_NEXT_DATA]},
                callback=self.parse_product,
            )

        if page < self.max_pages and page < listing["pagination"]["pages"]:
            yield build_listing_request(self.term, page + 1, callback=self.parse_listing)

    def parse_product(self, response):
        data = extract_next_data(response)
        item = data["props"]["pageProps"]["data"]["item"]

        offer = item["offers"][0]
        seller = offer.get("seller") or {}
        regular_price = offer.get("price")
        pix_price = None
        best_price = offer.get("bestPrice") or {}
        if best_price.get("paymentMethodId") == "pix":
            pix_price = best_price.get("totalAmount")

        rating = item.get("rating") or {}
        factsheet = factsheet_fields(item)

        yield ProductItem(
            search_term=self.term,
            title=item.get("title", ""),
            sold_by=seller_text(seller),
            regular_price=regular_price,
            pix_price=pix_price,
            rating=rating.get("score"),
            review_count=rating.get("count"),
            brand=factsheet.get("Marca", ""),
            reference=factsheet.get("Referência", ""),
            line=factsheet.get("Linha", ""),
            model=factsheet.get("Modelo", ""),
            quantity=factsheet.get("Quantidade", ""),
            url=response.url,
        )
