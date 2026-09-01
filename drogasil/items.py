from dataclasses import dataclass


@dataclass
class ProductItem:
    search_term: str
    title: str
    sold_by: str
    brand: str
    manufacturer: str
    quantity: str
    ean: str
    sku: str
    category: str
    subcategory: str
    tarja: str
    weight_kg: float | None
    image_url: str
    regular_price: float | None
    sale_price: float | None
    pix_price: float | None
    rating: float | None
    review_count: int | None
    url: str
