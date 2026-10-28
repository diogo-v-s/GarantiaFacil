"""Modelos de dados do projeto."""

from dataclasses import dataclass
from datetime import date


@dataclass
class Produto:
    """Um produto comprado. `@dataclass` gera construtor, __repr__ e __eq__ automaticamente
    (em Java seria uma `record`)."""

    nome: str
    loja: str
    data_compra: date
    prazo_garantia_meses: int
    valor: float | None = None
    observacoes: str = ""
    id: int | None = None  # None até ser salvo no banco


@dataclass
class Comprovante:
    """Arquivo (nota fiscal, foto, PDF) ligado a um produto."""

    produto_id: int
    nome_original: str
    caminho: str
    id: int | None = None
