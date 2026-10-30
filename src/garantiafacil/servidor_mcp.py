"""Servidor MCP do TáGuardado: expõe a consulta aos produtos para qualquer cliente MCP.

MCP (Model Context Protocol) é um padrão para um programa de IA (Claude Desktop, Claude Code...) usar
ferramentas de outro programa. Aqui o TáGuardado é o servidor: as mesmas ferramentas de consulta que
o nosso agente usa passam a poder ser chamadas de fora, com o cliente MCP no lugar do nosso chat.

Só LEITURA, de propósito. As ações que alteram dados (cadastrar, excluir, alterar) dependem do cartão
de confirmação do app, e um cliente MCP não tem esse cartão: o modelo gravaria sem o usuário ver.

Quem é o usuário: o servidor roda na sua máquina, por stdio, e usa a conta indicada em
TAGUARDADO_EMAIL. Não há senha porque só quem já tem acesso à máquina (e ao banco) consegue iniciá-lo;
por isso ele não serve para ficar exposto na rede.

Para usar com o Claude Code:
  claude mcp add taguardado -e TAGUARDADO_EMAIL=seu@email.com -- \
      uv --directory C:/KBs/GarantiaFacil run python -m garantiafacil.servidor_mcp"""

import functools
import os
import sys
from datetime import date

from mcp.server.mcpserver import MCPServer

from garantiafacil.db import conectar
from garantiafacil.ferramentas_cadastro import criar_ferramentas
from garantiafacil.repositorio import Repositorio
from garantiafacil.usuarios import Usuarios

INSTRUCOES = (
    "Consulta os produtos e as garantias cadastrados no TáGuardado pelo usuário: o que vence logo, "
    "detalhes de um produto, quanto foi gasto. Os dados vêm só do cadastro; o servidor não sabe o que "
    "a garantia de um produto cobre e não altera nada."
)


def _no_laco_do_servidor(funcao):
    """O MCP roda função comum numa thread à parte, e a conexão do SQLite só vale na thread que a criou.
    Como `async`, a ferramenta roda no laço do servidor, a mesma thread da conexão. As consultas são
    locais e rápidas, então não há problema em bloquear o laço por esse instante."""

    @functools.wraps(
        funcao
    )  # preserva nome e tipos: o MCP monta o esquema dos parâmetros a partir deles
    async def embrulho(*args, **kwargs):
        return funcao(*args, **kwargs)

    return embrulho


def criar_servidor(repositorio, hoje: date | None = None) -> MCPServer:
    """Um servidor com as ferramentas de consulta ligadas a um repositório (os produtos de um usuário)."""
    servidor = MCPServer("taguardado", instructions=INSTRUCOES)
    for ferramenta in criar_ferramentas(repositorio, hoje):
        # O MCP monta o esquema dos parâmetros a partir das anotações de tipo da função
        servidor.tool(name=ferramenta.nome, description=ferramenta.descricao)(
            _no_laco_do_servidor(ferramenta.funcao)
        )
    return servidor


def main() -> None:
    email = os.getenv("TAGUARDADO_EMAIL", "").strip()
    if not email:
        sys.exit("Defina TAGUARDADO_EMAIL com o e-mail da conta do TáGuardado.")
    conexao = conectar()
    usuario = Usuarios(conexao).obter_por_email(email)
    if usuario is None:
        sys.exit(f"Não há conta com o e-mail {email}.")
    # No stdio a saída padrão é o canal do protocolo: nada pode ser impresso nela, só em stderr
    criar_servidor(Repositorio(conexao, usuario.id)).run("stdio")


if __name__ == "__main__":
    main()
