"""Agente: um laço em que o LLM decide quando chamar ferramentas (funções Python nossas).

Cada volta do laço:
  1. mandamos ao LLM a conversa e a lista de ferramentas;
  2. ele responde com texto final OU pede para chamar ferramentas;
  3. se pediu, executamos as funções, devolvemos os resultados e voltamos ao passo 1.

Este módulo não conhece nenhum provedor: cada LLM (Ollama, Claude) implementa só
`passo(mensagens, ferramentas, sistema)`, que faz UMA volta e devolve um `PassoLlm`.
"""

import json
from dataclasses import dataclass, field
from typing import Any, Callable

MAX_PASSOS = 5  # trava de segurança: um modelo confuso poderia chamar ferramentas sem parar


@dataclass
class Ferramenta:
    """Uma função que o LLM pode pedir para executar."""

    nome: str
    descricao: str  # é isto que o modelo lê para decidir quando usar a ferramenta
    parametros: dict[str, dict]  # nome -> schema JSON, ex.: {"type": "integer", "description": "..."}
    funcao: Callable[..., Any]
    obrigatorios: tuple[str, ...] = ()

    def schema(self) -> dict:
        return {
            "type": "object",
            "properties": self.parametros,
            "required": list(self.obrigatorios),
        }


@dataclass
class Chamada:
    """Um pedido do LLM: 'execute a ferramenta X com estes argumentos'."""

    id: str  # o Claude exige devolver o resultado com o mesmo id; o Ollama não usa
    nome: str
    argumentos: dict


@dataclass
class PassoLlm:
    texto: str
    chamadas: list[Chamada]


@dataclass
class Consulta:
    """Registro de uma ferramenta que foi executada, para mostrar ao usuário."""

    nome: str
    argumentos: dict
    resultado: str


@dataclass
class RespostaAgente:
    texto: str
    consultas: list[Consulta] = field(default_factory=list)
    completo: bool = True  # False se estourou MAX_PASSOS sem uma resposta final


def executar_ferramenta(ferramentas: dict[str, Ferramenta], chamada: Chamada) -> str:
    """Roda a ferramenta pedida e devolve o resultado como texto JSON.

    Erros (ferramenta inexistente, argumento errado) não derrubam o agente: viram o próprio
    resultado, e o modelo vê o erro e pode tentar de novo."""
    ferramenta = ferramentas.get(chamada.nome)
    if ferramenta is None:
        return json.dumps({"erro": f"ferramenta '{chamada.nome}' não existe"}, ensure_ascii=False)
    try:
        resultado = ferramenta.funcao(**chamada.argumentos)
    except Exception as erro:  # modelos erram nomes e tipos de argumentos
        return json.dumps({"erro": f"{type(erro).__name__}: {erro}"}, ensure_ascii=False)
    return json.dumps(resultado, ensure_ascii=False, default=str)


def executar_agente(
    llm,
    pergunta: str,
    ferramentas: list[Ferramenta],
    sistema: str,
    max_passos: int = MAX_PASSOS,
    historico: list[dict] | None = None,
) -> RespostaAgente:
    """`historico`: mensagens anteriores da conversa (só texto, no formato neutro), para perguntas
    de seguimento como 'e da TV?'. Sem ele, cada pergunta começa do zero."""
    por_nome = {f.nome: f for f in ferramentas}
    mensagens: list[dict] = [*(historico or []), {"papel": "usuario", "texto": pergunta}]
    consultas: list[Consulta] = []

    for _ in range(max_passos):
        passo = llm.passo(mensagens, ferramentas, sistema)
        if not passo.chamadas:
            return RespostaAgente(passo.texto.strip(), consultas)

        mensagens.append({"papel": "assistente", "texto": passo.texto, "chamadas": passo.chamadas})
        for chamada in passo.chamadas:
            resultado = executar_ferramenta(por_nome, chamada)
            consultas.append(Consulta(chamada.nome, chamada.argumentos, resultado))
            mensagens.append({"papel": "resultado", "chamada": chamada, "conteudo": resultado})

    return RespostaAgente(
        "Não consegui concluir a consulta. Tente perguntar de outro jeito.", consultas, completo=False
    )
