"""Servidor MCP: um cliente MCP em memória (sem processo nem rede) conversa com ele."""

import asyncio
import json
from datetime import date

import pytest
from mcp import Client

from garantiafacil.modelos import Categoria, Produto
from garantiafacil.repositorio import Repositorio
from garantiafacil.servidor_mcp import criar_servidor
from garantiafacil.usuarios import Usuarios
from tests.ajuda import banco_com_usuario
from tests.test_conversa import embedding_falso


@pytest.fixture
def servidor(tmp_path):
    repo = Repositorio(
        *banco_com_usuario(),
        tmp_path,
        gerar_embedding=embedding_falso,
        nome_modelo=lambda: "f",
    )
    repo.adicionar(
        Produto(
            "Geladeira Brastemp",
            "Casas Bahia",
            date(2026, 1, 10),
            12,
            3000.0,
            categoria=Categoria.ELETRODOMESTICOS,
        )
    )
    repo.adicionar(
        Produto(
            "Furadeira Bosch",
            "Leroy Merlin",
            date(2026, 2, 1),
            6,
            400.0,
            categoria=Categoria.FERRAMENTAS,
        )
    )
    return criar_servidor(repo, hoje=date(2026, 6, 1))


def chamar(servidor, ferramenta, argumentos=None) -> dict:
    async def rodar():
        async with Client(servidor) as cliente:
            resultado = await cliente.call_tool(ferramenta, argumentos or {})
            return json.loads(resultado.content[0].text)

    return asyncio.run(rodar())


def test_expoe_so_ferramentas_de_leitura(servidor):
    async def nomes():
        async with Client(servidor) as cliente:
            return {t.name for t in (await cliente.list_tools()).tools}

    assert asyncio.run(nomes()) == {
        "listar_produtos",
        "vencimentos_proximos",
        "detalhes_produto",
        "total_gasto",
    }


def test_lista_os_produtos_do_usuario(servidor):
    dados = chamar(servidor, "listar_produtos")

    assert dados["total"] == 2
    assert {p["nome"] for p in dados["produtos"]} == {
        "Geladeira Brastemp",
        "Furadeira Bosch",
    }


def test_parametros_chegam_a_ferramenta(servidor):
    dados = chamar(servidor, "listar_produtos", {"categoria": "Ferramentas"})

    assert [p["nome"] for p in dados["produtos"]] == ["Furadeira Bosch"]


def test_total_gasto_pelo_mcp(servidor):
    assert chamar(servidor, "total_gasto")["total_gasto"] == "R$ 3.400,00"


def test_obter_usuario_por_email_ignora_caixa_e_espacos():
    conexao, usuario_id = banco_com_usuario()
    usuarios = Usuarios(conexao)
    email = conexao.execute(
        "SELECT email FROM usuarios WHERE id = ?", (usuario_id,)
    ).fetchone()["email"]

    assert usuarios.obter_por_email(f"  {email.upper()} ").id == usuario_id
    assert usuarios.obter_por_email("ninguem@exemplo.com") is None
