from dataclasses import dataclass


@dataclass
class ProductItem:
    search_term: str
    title: str
    sold_by: str
    regular_price: float | None
    pix_price: float | None
    rating: float | None
    review_count: int | None
    brand: str
    reference: str
    line: str
    model: str
    quantity: str
    url: str
