"""Acesso aos dados: salvar, listar, buscar e excluir produtos e comprovantes."""

import sqlite3
import uuid
from datetime import date
from pathlib import Path

import numpy as np

from garantiafacil import embeddings
from garantiafacil.db import PASTA_DADOS
from garantiafacil.modelos import Comprovante, Produto


def _linha_para_produto(linha: sqlite3.Row) -> Produto:
    return Produto(
        id=linha["id"],
        nome=linha["nome"],
        loja=linha["loja"],
        data_compra=date.fromisoformat(linha["data_compra"]),
        prazo_garantia_meses=linha["prazo_garantia_meses"],
        valor=linha["valor"],
        observacoes=linha["observacoes"],
    )


def _texto_para_indexar(produto: Produto) -> str:
    """O que representa o significado do produto. A loja fica de fora: só adiciona ruído."""
    return f"{produto.nome}. {produto.observacoes}".strip()


class Repositorio:
    def __init__(
        self,
        conexao: sqlite3.Connection,
        pasta_comprovantes: Path = PASTA_DADOS / "comprovantes",
        gerar_embedding=embeddings.gerar_embedding,
        nome_modelo=embeddings.nome_modelo,
    ):
        self.conexao = conexao
        self.pasta_comprovantes = Path(pasta_comprovantes)
        self._gerar_embedding = gerar_embedding  # injetável: os testes usam um embedding falso
        self._nome_modelo = nome_modelo

    # ---------- produtos ----------

    def adicionar(self, produto: Produto) -> Produto:
        # Os "?" evitam SQL injection: nunca monte SQL concatenando texto do usuário.
        cursor = self.conexao.execute(
            "INSERT INTO produtos (nome, loja, data_compra, prazo_garantia_meses, valor, observacoes) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                produto.nome,
                produto.loja,
                produto.data_compra.isoformat(),
                produto.prazo_garantia_meses,
                produto.valor,
                produto.observacoes,
            ),
        )
        self.conexao.commit()
        produto.id = cursor.lastrowid
        self._indexar(produto)
        return produto

    def obter(self, produto_id: int) -> Produto | None:
        linha = self.conexao.execute(
            "SELECT * FROM produtos WHERE id = ?", (produto_id,)
        ).fetchone()
        return _linha_para_produto(linha) if linha else None

    def listar(self) -> list[Produto]:
        linhas = self.conexao.execute("SELECT * FROM produtos ORDER BY data_compra DESC").fetchall()
        return [_linha_para_produto(linha) for linha in linhas]

    def buscar(self, texto: str) -> list[Produto]:
        """Busca por palavra no nome, loja ou observações (LIKE).
        Limitação: só acha o texto literal. 'geladeira' não acha 'refrigerador'.
        Na etapa 4, a busca semântica resolve isso."""
        padrao = f"%{texto.strip()}%"
        linhas = self.conexao.execute(
            "SELECT * FROM produtos "
            "WHERE nome LIKE ? OR loja LIKE ? OR observacoes LIKE ? "
            "ORDER BY data_compra DESC",
            (padrao, padrao, padrao),
        ).fetchall()
        return [_linha_para_produto(linha) for linha in linhas]

    # ---------- busca por significado ----------

    def _indexar(self, produto: Produto) -> bool:
        """Calcula e guarda o embedding do produto. Se o Ollama estiver fora do ar, o produto
        continua salvo e `reindexar()` completa depois. Devolve se conseguiu indexar."""
        try:
            vetor = self._gerar_embedding(_texto_para_indexar(produto))
        except Exception:
            return False
        self.conexao.execute(
            "INSERT OR REPLACE INTO embeddings (produto_id, modelo, vetor) VALUES (?, ?, ?)",
            (produto.id, self._nome_modelo(), np.asarray(vetor, dtype=np.float32).tobytes()),
        )
        self.conexao.commit()
        return True

    def reindexar(self) -> int:
        """Indexa os produtos que não têm embedding (ou que têm de outro modelo).
        Devolve quantos foram indexados."""
        linhas = self.conexao.execute(
            "SELECT p.* FROM produtos p LEFT JOIN embeddings e ON e.produto_id = p.id "
            "WHERE e.produto_id IS NULL OR e.modelo != ?",
            (self._nome_modelo(),),
        ).fetchall()
        return sum(self._indexar(_linha_para_produto(linha)) for linha in linhas)

    def buscar_semantico(
        self, consulta: str, limite: int = 5, minimo: float = 0.5
    ) -> list[tuple[Produto, float]]:
        """Produtos ordenados pela proximidade de significado com a consulta.

        Devolve pares (produto, similaridade de 0 a 1), só com similaridade >= `minimo`.
        'geladeira' acha 'Refrigerador', que a busca por texto não acha."""
        if not consulta.strip():
            return []
        vetor_consulta = self._gerar_embedding(consulta.strip(), consulta=True)

        linhas = self.conexao.execute(
            "SELECT p.*, e.vetor FROM produtos p JOIN embeddings e ON e.produto_id = p.id "
            "WHERE e.modelo = ?",
            (self._nome_modelo(),),
        ).fetchall()

        resultados = []
        for linha in linhas:
            vetor = np.frombuffer(linha["vetor"], dtype=np.float32)
            nota = embeddings.similaridade(vetor_consulta, vetor)
            if nota >= minimo:
                resultados.append((_linha_para_produto(linha), nota))

        resultados.sort(key=lambda par: par[1], reverse=True)
        return resultados[:limite]

    def excluir(self, produto_id: int) -> None:
        for comprovante in self.listar_comprovantes(produto_id):
            Path(comprovante.caminho).unlink(missing_ok=True)
        self.conexao.execute("DELETE FROM produtos WHERE id = ?", (produto_id,))
        self.conexao.commit()

    # ---------- comprovantes ----------

    def adicionar_comprovante(
        self, produto_id: int, nome_original: str, conteudo: bytes
    ) -> Comprovante:
        pasta = self.pasta_comprovantes / str(produto_id)
        pasta.mkdir(parents=True, exist_ok=True)

        # Path(...).name descarta qualquer pasta no nome; o uuid evita nomes repetidos.
        nome_seguro = Path(nome_original).name
        caminho = pasta / f"{uuid.uuid4().hex[:8]}_{nome_seguro}"
        caminho.write_bytes(conteudo)

        cursor = self.conexao.execute(
            "INSERT INTO comprovantes (produto_id, nome_original, caminho) VALUES (?, ?, ?)",
            (produto_id, nome_seguro, str(caminho)),
        )
        self.conexao.commit()
        return Comprovante(
            id=cursor.lastrowid,
            produto_id=produto_id,
            nome_original=nome_seguro,
            caminho=str(caminho),
        )

    def listar_comprovantes(self, produto_id: int) -> list[Comprovante]:
        linhas = self.conexao.execute(
            "SELECT * FROM comprovantes WHERE produto_id = ? ORDER BY id", (produto_id,)
        ).fetchall()
        return [
            Comprovante(
                id=linha["id"],
                produto_id=linha["produto_id"],
                nome_original=linha["nome_original"],
                caminho=linha["caminho"],
            )
            for linha in linhas
        ]
