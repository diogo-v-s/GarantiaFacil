"""Modelos de dados do projeto."""

from dataclasses import dataclass
from datetime import date
from enum import Enum


class Categoria(str, Enum):
    """Domínio padronizado de categorias (em Java seria um `enum`). O valor é o texto que vai
    para o banco e para a tela; herdar de `str` deixa comparar e gravar direto como texto."""

    ELETRODOMESTICOS = "Eletrodomésticos"
    ELETRONICOS = "Eletrônicos"
    FERRAMENTAS = "Ferramentas"


class TipoDocumento(str, Enum):
    """Tipos de documento guardados em um produto. Termo e manual também alimentam as
    respostas da aba Perguntas; a nota fiscal só fica guardada."""

    NOTA_FISCAL = "Nota fiscal"
    TERMO_GARANTIA = "Termo de garantia"
    MANUAL = "Manual"


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
    categoria: Categoria | None = None  # opcional: produtos antigos não têm
    foto: str | None = None  # caminho da foto do produto; sem foto, a tela usa a imagem da categoria
    id: int | None = None  # None até ser salvo no banco


@dataclass
class Comprovante:
    """Documento (nota fiscal, termo de garantia, manual) ligado a um produto."""

    produto_id: int
    nome_original: str
    caminho: str
    tipo: TipoDocumento = TipoDocumento.NOTA_FISCAL
    id: int | None = None
