import json

import scrapy
from scrapy_playwright.page import PageMethod

from magazineluiza.items import ProdutoItem

WAIT_NEXT_DATA = PageMethod(
    "wait_for_selector", "script#__NEXT_DATA__", state="attached", timeout=20000
)


def extrair_next_data(response):
    bruto = response.css("script#__NEXT_DATA__::text").get()
    return json.loads(bruto)


def montar_request_busca(termo, pagina, callback):
    url = f"https://www.magazineluiza.com.br/marcas/{termo}/"
    if pagina > 1:
        url += f"?page={pagina}"
    return scrapy.Request(
        url,
        meta={"playwright": True, "playwright_page_methods": [WAIT_NEXT_DATA]},
        callback=callback,
        cb_kwargs={"pagina": pagina},
    )


def e_da_marca(item, termo):
    marca = (item.get("brand") or {}).get("slug", "")
    return marca.lower() == termo.lower()


def texto_vendedor(vendedor):
    vendido_por = vendedor.get("name") or vendedor.get("description") or ""
    entregue_por = vendedor.get("deliveryDescription") or ""
    if not vendido_por:
        return ""
    if not entregue_por:
        return f"Vendido por {vendido_por}"
    if vendido_por.strip().lower() == entregue_por.strip().lower():
        return f"Vendido e entregue por {entregue_por}"
    return f"Vendido por {vendido_por} e entregue por {entregue_por}"


def ficha_tecnica(item):
    for grupo in item.get("factsheet") or []:
        if grupo.get("displayName") != "Ficha-Técnica":
            continue
        resultado = {}
        for elemento in grupo.get("elements", []):
            chave = elemento.get("keyName")
            valores = elemento.get("elements") or []
            valor = valores[0].get("value", "") if valores else ""
            if chave:
                resultado[chave] = valor
        return resultado
    return {}


class BuscaSpider(scrapy.Spider):
    name = "busca"
    allowed_domains = ["magazineluiza.com.br"]

    def __init__(self, termo="nivea", max_pages="1", *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.termo = termo
        self.max_pages = int(max_pages)

    async def start(self):
        yield montar_request_busca(self.termo, pagina=1, callback=self.parse_busca)

    def parse_busca(self, response, pagina):
        data = extrair_next_data(response)
        busca = data["props"]["pageProps"]["data"]["brand"]  # "brand" na pagina de marca, era "search" na de busca

        relevantes = [
            item for item in busca["items"]
            if item.get("reviewCount", 0) > 0 and e_da_marca(item, self.termo)
        ]
        self.logger.info(
            "pagina %s: %s produtos, %s com estrela e da marca",
            pagina, len(busca["items"]), len(relevantes),
        )

        for item in relevantes:
            url_produto = response.urljoin(item["path"])
            yield scrapy.Request(
                url_produto,
                meta={"playwright": True, "playwright_page_methods": [WAIT_NEXT_DATA]},
                callback=self.parse_produto,
            )

        if pagina < self.max_pages and pagina < busca["pagination"]["pages"]:
            yield montar_request_busca(self.termo, pagina + 1, callback=self.parse_busca)

    def parse_produto(self, response):
        data = extrair_next_data(response)
        item = data["props"]["pageProps"]["data"]["item"]

        oferta = item["offers"][0]
        vendedor = oferta.get("seller") or {}
        preco_normal = oferta.get("price")
        preco_pix = None
        melhor_preco = oferta.get("bestPrice") or {}
        if melhor_preco.get("paymentMethodId") == "pix":
            preco_pix = melhor_preco.get("totalAmount")

        rating = item.get("rating") or {}
        ficha = ficha_tecnica(item)

        yield ProdutoItem(
            termo_busca=self.termo,
            titulo=item.get("title", ""),
            vendido_por=texto_vendedor(vendedor),
            preco_normal=preco_normal,
            preco_pix=preco_pix,
            estrelas=rating.get("score"),
            avaliacoes=rating.get("count"),
            marca=ficha.get("Marca", ""),
            referencia=ficha.get("Referência", ""),
            linha=ficha.get("Linha", ""),
            modelo=ficha.get("Modelo", ""),
            quantidade=ficha.get("Quantidade", ""),
            url=response.url,
        )
