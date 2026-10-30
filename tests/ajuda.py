"""Apoio dos testes que precisam de um Repositorio (que sempre pertence a um usuário)."""

from garantiafacil.db import conectar
from garantiafacil.usuarios import Usuarios


def banco_com_usuario(caminho=":memory:", email="teste@exemplo.com"):
    """Abre o banco, cria um usuário e devolve (conexao, usuario_id), pronto para
    `Repositorio(*banco_com_usuario(), ...)`."""
    conexao = conectar(caminho)
    existente = conexao.execute("SELECT id FROM usuarios WHERE email = ?", (email,)).fetchone()
    usuario_id = existente["id"] if existente else Usuarios(conexao).criar(email, "senha-de-teste", "Teste").id
    return conexao, usuario_id


def adotar_orfaos(repo) -> None:
    """Bancos anteriores ao login têm produtos sem dono (invisíveis). Os testes de migração
    entregam esses produtos ao usuário do repositório para poder conferir os dados."""
    repo.conexao.execute("UPDATE produtos SET usuario_id = ? WHERE usuario_id IS NULL", (repo.usuario_id,))
    repo.conexao.commit()


def compra_para_vencer_em(vencimento, meses=12):
    """Data de compra que faz a cobertura total (fabricante + garantia legal) acabar em `vencimento`.
    Evita refazer a conta de cabeça nos testes de vencimento."""
    from datetime import timedelta

    from garantiafacil.garantia import GARANTIA_LEGAL_DIAS, somar_meses

    return somar_meses(vencimento - timedelta(days=GARANTIA_LEGAL_DIAS), -meses)
