from dataclasses import dataclass


@dataclass
class ProdutoItem:
    termo_busca: str
    titulo: str
    vendido_por: str
    preco_normal: float | None
    preco_pix: float | None
    estrelas: float | None
    avaliacoes: int | None
    marca: str
    referencia: str
    linha: str
    modelo: str
    quantidade: str
    url: str
