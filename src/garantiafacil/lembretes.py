"""Lembretes que o usuário programa para um produto, por exemplo "levar na assistência dia 5", e os
avisos de vencimento que ele já marcou como lidos.

Não confundir com o aviso de vencimento da garantia, que é automático e não fica guardado
(ver `avisos.py`). Os dois aparecem juntos no sininho (ver `notificacoes.py`)."""

import sqlite3
from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class Lembrete:
    id: int
    produto_id: int
    data: date  # quando avisar
    texto: str
    concluido: bool = False


class Lembretes:
    """Os lembretes de UM usuário, como o Repositorio faz com os produtos."""

    def __init__(self, conexao: sqlite3.Connection, usuario_id: int):
        self.conexao = conexao
        self.usuario_id = usuario_id

    def adicionar(self, produto_id: int, data: date, texto: str) -> Lembrete:
        texto = texto.strip()
        if not texto:
            raise ValueError("O lembrete precisa de um texto.")
        dono = self.conexao.execute(
            "SELECT 1 FROM produtos WHERE id = ? AND usuario_id = ?", (produto_id, self.usuario_id)
        ).fetchone()
        if dono is None:  # não existe ou é de outro usuário
            raise ValueError("Produto não encontrado.")
        cursor = self.conexao.execute(
            "INSERT INTO lembretes (usuario_id, produto_id, data, texto) VALUES (?, ?, ?, ?)",
            (self.usuario_id, produto_id, data.isoformat(), texto),
        )
        self.conexao.commit()
        return Lembrete(cursor.lastrowid, produto_id, data, texto)

    def pendentes(self) -> list[Lembrete]:
        """Os ainda não concluídos, do mais próximo ao mais distante."""
        linhas = self.conexao.execute(
            "SELECT * FROM lembretes WHERE usuario_id = ? AND concluido = 0 ORDER BY data, id",
            (self.usuario_id,),
        ).fetchall()
        return [
            Lembrete(l["id"], l["produto_id"], date.fromisoformat(l["data"]), l["texto"]) for l in linhas
        ]

    def concluir(self, lembrete_id: int) -> None:
        self.conexao.execute(
            "UPDATE lembretes SET concluido = 1 WHERE id = ? AND usuario_id = ?",
            (lembrete_id, self.usuario_id),
        )
        self.conexao.commit()


class NotificacoesLidas:
    """Os avisos de vencimento que o usuário já marcou como lidos (os lembretes saem da lista ao
    serem concluídos, então só os avisos precisam disto)."""

    def __init__(self, conexao: sqlite3.Connection, usuario_id: int):
        self.conexao = conexao
        self.usuario_id = usuario_id

    def chaves(self) -> set[str]:
        linhas = self.conexao.execute(
            "SELECT chave FROM notificacoes_lidas WHERE usuario_id = ?", (self.usuario_id,)
        ).fetchall()
        return {linha["chave"] for linha in linhas}

    def marcar(self, produto_id: int, chave: str) -> None:
        dono = self.conexao.execute(
            "SELECT 1 FROM produtos WHERE id = ? AND usuario_id = ?", (produto_id, self.usuario_id)
        ).fetchone()
        if dono is None:  # não existe ou é de outro usuário
            return
        self.conexao.execute(
            "INSERT OR IGNORE INTO notificacoes_lidas (usuario_id, produto_id, chave) VALUES (?, ?, ?)",
            (self.usuario_id, produto_id, chave),
        )
        self.conexao.commit()
