"""Conexão e criação do banco SQLite."""

import sqlite3
from pathlib import Path

from garantiafacil.modelos import Categoria, TipoDocumento


def _valores(enum) -> str:
    return ", ".join(f"'{item.value}'" for item in enum)


# Restrições geradas a partir das enums: o banco só aceita os valores do domínio.
_COLUNA_CATEGORIA = f"categoria TEXT CHECK (categoria IN ({_valores(Categoria)}))"
_COLUNA_FOTO = "foto TEXT"
_COLUNA_TIPO = (
    f"tipo TEXT NOT NULL DEFAULT '{TipoDocumento.NOTA_FISCAL.value}' "
    f"CHECK (tipo IN ({_valores(TipoDocumento)}))"
)

RAIZ = Path(__file__).resolve().parents[2]  # pasta do projeto
PASTA_DADOS = RAIZ / "data"
CAMINHO_BANCO = PASTA_DADOS / "garantiafacil.db"

def _ddl_produtos(nome: str) -> str:
    return f"""
CREATE TABLE IF NOT EXISTS {nome} (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nome TEXT NOT NULL,
    loja TEXT NOT NULL,
    data_compra TEXT NOT NULL,            -- ISO: AAAA-MM-DD
    prazo_garantia_meses INTEGER NOT NULL,
    valor REAL,
    observacoes TEXT NOT NULL DEFAULT '',
    {_COLUNA_CATEGORIA},
    {_COLUNA_FOTO}
);
"""


SCHEMA = f"""
{_ddl_produtos("produtos")}
-- Vetor de significado de cada produto (embedding), guardado como bytes de float32.
-- Guardamos o modelo: se ele mudar, os vetores antigos não servem mais.
CREATE TABLE IF NOT EXISTS embeddings (
    produto_id INTEGER PRIMARY KEY REFERENCES produtos(id) ON DELETE CASCADE,
    modelo TEXT NOT NULL,
    vetor BLOB NOT NULL
);

-- Trechos de manuais e termos de garantia, para o RAG. produto_id NULL = documento geral
-- (vale para qualquer produto, como o Código de Defesa do Consumidor).
CREATE TABLE IF NOT EXISTS trechos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    produto_id INTEGER REFERENCES produtos(id) ON DELETE CASCADE,
    fonte TEXT NOT NULL,
    pagina INTEGER NOT NULL,
    texto TEXT NOT NULL,
    modelo TEXT NOT NULL,
    vetor BLOB NOT NULL
);

CREATE TABLE IF NOT EXISTS comprovantes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    produto_id INTEGER NOT NULL REFERENCES produtos(id) ON DELETE CASCADE,
    nome_original TEXT NOT NULL,
    caminho TEXT NOT NULL,
    {_COLUNA_TIPO}
);
"""


def conectar(
    caminho: str | Path = CAMINHO_BANCO, check_same_thread: bool = True
) -> sqlite3.Connection:
    """Abre o banco (criando arquivo e tabelas se preciso). Use ':memory:' nos testes.

    check_same_thread=False permite usar a mesma conexão em várias threads (o Streamlit faz isso)."""
    if str(caminho) != ":memory:":
        Path(caminho).parent.mkdir(parents=True, exist_ok=True)

    conexao = sqlite3.connect(str(caminho), check_same_thread=check_same_thread)
    conexao.row_factory = sqlite3.Row  # permite acessar colunas por nome: linha["nome"]
    conexao.execute("PRAGMA foreign_keys = ON")
    conexao.executescript(SCHEMA)
    _migrar(conexao)
    return conexao


def _migrar(conexao: sqlite3.Connection) -> None:
    """Bancos criados antes de uma coluna existir não a ganham pelo CREATE TABLE IF NOT EXISTS;
    aqui acrescentamos o que faltar sem perder os dados."""
    _garantir_coluna(conexao, "produtos", "categoria", _COLUNA_CATEGORIA)
    _garantir_coluna(conexao, "produtos", "foto", _COLUNA_FOTO)
    _garantir_coluna(conexao, "comprovantes", "tipo", _COLUNA_TIPO)
    _atualizar_regra_categorias(conexao)


def _garantir_coluna(conexao: sqlite3.Connection, tabela: str, coluna: str, definicao: str) -> None:
    colunas = {linha["name"] for linha in conexao.execute(f"PRAGMA table_info({tabela})")}
    if coluna not in colunas:
        conexao.execute(f"ALTER TABLE {tabela} ADD COLUMN {definicao}")
        conexao.commit()


def _atualizar_regra_categorias(conexao: sqlite3.Connection) -> None:
    """O SQLite não deixa alterar um CHECK existente. Se o banco foi criado com uma lista menor
    de categorias, refazemos a tabela `produtos` (receita oficial do SQLite: criar a nova,
    copiar, apagar a antiga e renomear) com a regra atual, sem perder nenhum dado."""
    linha = conexao.execute(
        "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'produtos'"
    ).fetchone()
    if all(f"'{c.value}'" in linha["sql"] for c in Categoria):
        return

    colunas = "id, nome, loja, data_compra, prazo_garantia_meses, valor, observacoes, categoria, foto"
    # foreign_keys desligado: senão apagar `produtos` apagaria, em cascata, embeddings,
    # trechos e comprovantes. O executescript fecha a transação anterior antes de começar.
    conexao.executescript(
        f"""
        PRAGMA foreign_keys = OFF;
        BEGIN;
        {_ddl_produtos("produtos_novo")}
        INSERT INTO produtos_novo ({colunas}) SELECT {colunas} FROM produtos;
        DROP TABLE produtos;
        ALTER TABLE produtos_novo RENAME TO produtos;
        COMMIT;
        PRAGMA foreign_keys = ON;
        """
    )
