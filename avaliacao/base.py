"""Base de teste fixa da avaliação: sempre os mesmos produtos, datas e valores.

Fica em data/avaliacao.db (ignorado pelo git), separada do banco do usuário. A primeira vez leva
alguns minutos, porque indexa o CDC com embeddings reais; depois é reaproveitada."""

from datetime import date
from pathlib import Path

from garantiafacil.db import RAIZ, conectar
from garantiafacil.documentos import extrair_paginas
from garantiafacil.modelos import Categoria, Produto
from garantiafacil.rag import BaseConhecimento
from garantiafacil.repositorio import Repositorio

# Os vencimentos dependem da data: a avaliação fixa "hoje" para os resultados se repetirem.
HOJE = date(2026, 10, 28)

CAMINHO_BANCO = RAIZ / "data" / "avaliacao.db"
CAMINHO_CDC = RAIZ / "docs" / "conhecimento" / "cdc.txt"
CAMINHO_TERMO_TV = Path(__file__).parent / "termos" / "termo-tv-samsung.txt"

# nome, loja, data da compra, meses de garantia, valor, categoria  -> situação em HOJE
PRODUTOS = [
    ("Geladeira Brastemp 375L", "Magazine Luiza", date(2026, 3, 10), 12, 3499.90, Categoria.ELETRODOMESTICOS),  # vence 10/03/2027
    ("Smart TV Samsung 50", "Casas Bahia", date(2025, 12, 15), 12, 2899.00, Categoria.ELETRONICOS),  # vence 15/12/2026 (48 dias)
    ("Furadeira Bosch", "Leroy Merlin", date(2025, 11, 20), 12, 459.90, Categoria.FERRAMENTAS),  # vence 20/11/2026 (23 dias)
    ("iPhone 15", "Apple Store", date(2025, 3, 22), 12, 7299.00, Categoria.ELETRONICOS),  # venceu 22/03/2026
    ("Notebook Dell Inspiron 15", "Dell", date(2026, 10, 1), 12, 4150.00, Categoria.ELETRONICOS),  # vence 01/10/2027
]  # fmt: skip


def montar(caminho: Path = CAMINHO_BANCO) -> tuple[Repositorio, BaseConhecimento]:
    """Abre (e completa, se faltar algo) a base de avaliação."""
    repo = Repositorio(conectar(caminho, check_same_thread=False))
    base = BaseConhecimento(repo.conexao)

    if not repo.listar():
        for nome, loja, compra, meses, valor, categoria in PRODUTOS:
            repo.adicionar(
                Produto(nome=nome, loja=loja, data_compra=compra, prazo_garantia_meses=meses,
                        valor=valor, categoria=categoria)  # fmt: skip
            )

    if not base.fonte_indexada("cdc.txt"):
        print("Indexando o CDC na base de avaliação (alguns minutos, só na primeira vez)...", flush=True)
        base.indexar("cdc.txt", extrair_paginas("cdc.txt", CAMINHO_CDC.read_bytes()))

    tv = next(p for p in repo.listar() if p.nome.startswith("Smart TV"))
    if not base.tem_documentos(tv.id):
        base.indexar(
            CAMINHO_TERMO_TV.name, extrair_paginas(CAMINHO_TERMO_TV.name, CAMINHO_TERMO_TV.read_bytes()), tv.id
        )
    return repo, base
