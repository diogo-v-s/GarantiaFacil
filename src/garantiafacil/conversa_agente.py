"""Chat sem classificador: um agente só decide tudo (experimento da etapa 10).

No chat atual (`conversa.py`), uma chamada ao LLM classifica a pergunta (cadastro, lei ou produto)
e o código escolhe o caminho. Aqui não há classificação: o agente recebe as ferramentas do cadastro
mais `consultar_documentos` (o RAG como ferramenta) e decide sozinho o que usar.

Tem a mesma interface de `Conversa` (`responder`, `produto_atual`, `reiniciar`), então a avaliação
roda os mesmos casos nos dois."""

import os
from dataclasses import dataclass, field
from datetime import date

from garantiafacil.agente import Ferramenta, executar_agente
from garantiafacil.assistencias import ErroDeBusca, buscar_assistencias, localizar_cidade
from garantiafacil.conversa import CONSULTA_GARANTIA_LEGAL, Conversa, Mensagem, trechos_por_resposta
from garantiafacil.ferramentas_cadastro import criar_ferramentas, sistema_agente
from garantiafacil.localizar import localizar_produto
from garantiafacil.modelos import Produto
from garantiafacil.rag import BaseConhecimento, TrechoEncontrado

FERRAMENTAS_DO_CADASTRO = {
    "listar_produtos", "vencimentos_proximos", "detalhes_produto", "total_gasto", "onde_acionar_garantia",
}  # fmt: skip
MENSAGENS_NO_HISTORICO = 6  # as últimas 3 trocas bastam para "e da TV?"


def sistema_conversa(hoje: date | None, produto_atual: Produto | None) -> str:
    assunto = (
        f"\nProduto em discussão: '{produto_atual.nome}'. Perguntas curtas de seguimento, como "
        "'e o prazo?' ou 'e a assistência?', são sobre ele."
        if produto_atual
        else ""
    )
    return (
        sistema_agente(hoje)
        + "\n\nAlém do cadastro, você consulta os documentos: o termo de garantia de cada produto e o "
        "Código de Defesa do Consumidor (CDC). Use consultar_documentos para:\n"
        "- perguntas sobre direitos e prazos da lei (sem informar produto);\n"
        "- o que a garantia, o termo, a cobertura ou a assistência de UM produto cobre ou exige "
        "(informando o produto). Isso vale em lugar da regra acima de que você não sabe a cobertura.\n"
        "Se a pergunta é sobre a cobertura de um produto e o usuário não disse de qual, e não há produto "
        "em discussão, NÃO chame ferramenta: pergunte 'De qual produto você está falando?' e liste os "
        "produtos cadastrados numerados (use listar_produtos para saber quais são).\n"
        "Responda com base só nos trechos devolvidos, em português, em no máximo 5 linhas, sem repetir a "
        "pergunta. Nunca escreva a palavra 'trecho' nem marcadores como [1]. Se a ferramenta devolver "
        "'aviso', siga a instrução dele.\n"
        "Se o usuário perguntar ONDE acionar a garantia, onde levar o produto ou que assistência procurar, "
        "use onde_acionar_garantia com o produto e a cidade dele. Se ele não disse a cidade, pergunte "
        "'Em qual cidade?' sem chamar a ferramenta. Liste só os lugares devolvidos, com nome, endereço, "
        "telefone e distância, exatamente como vieram; onde estiver 'não informado', diga que não "
        "consta no mapa. Nunca invente telefone nem endereço e termine avisando que os dados do mapa "
        "podem estar incompletos."
        + assunto
    )


def modo_do_chat() -> str:
    """'agente' (um agente decide tudo) ou 'classificador' (o chat com a pergunta classificada antes).

    Vem de CHAT_MODO no .env. Sem ele: agente com o Claude, que acertou 93% na avaliação sem
    classificar; classificador com o Ollama, onde o agente ainda não foi medido."""
    escolhido = os.getenv("CHAT_MODO", "").strip().lower()
    if escolhido in ("agente", "classificador"):
        return escolhido
    claude = os.getenv("LLM_PROVIDER", "ollama").lower() == "claude"
    return "agente" if claude else "classificador"


def criar_conversa(repositorio, base: BaseConhecimento, llm, hoje: date | None = None):
    """A conversa do app, no modo escolhido (ver `modo_do_chat`)."""
    classe = ConversaAgente if modo_do_chat() == "agente" else Conversa
    return classe(repositorio, base, llm, hoje=hoje)


@dataclass
class _UsoDeDocumentos:
    """O que consultar_documentos fez na pergunta atual (para saber por onde a resposta passou)."""

    trechos: list[TrechoEncontrado] = field(default_factory=list)
    sem_termo: bool = False


class ConversaAgente:
    def __init__(self, repositorio, base: BaseConhecimento, llm, hoje: date | None = None):
        self.repositorio = repositorio
        self.base = base
        self.llm = llm
        self.hoje = hoje
        self.produto_atual: Produto | None = None
        self.historico: list[dict] = []

    def reiniciar(self) -> None:
        self.produto_atual = None
        self.historico = []

    def responder(self, mensagem: str) -> Mensagem:
        mensagem = mensagem.strip()
        uso = _UsoDeDocumentos()
        ferramentas = criar_ferramentas(self.repositorio, self.hoje) + [
            self._ferramenta_documentos(uso),
            self._ferramenta_assistencias(),
        ]

        resposta = executar_agente(
            self.llm,
            mensagem,
            ferramentas,
            sistema_conversa(self.hoje, self.produto_atual),
            historico=self.historico,
        )

        self._atualizar_assunto(resposta)
        self.historico += [
            {"papel": "usuario", "texto": mensagem},
            {"papel": "assistente", "texto": resposta.texto, "chamadas": []},
        ]
        self.historico = self.historico[-MENSAGENS_NO_HISTORICO:]
        return Mensagem(
            texto=resposta.texto,
            trechos=uso.trechos,
            produto=self.produto_atual,
            consultas=resposta.consultas,
            rota=self._rota(resposta, uso),
        )

    # ---------- ferramenta de documentos ----------

    def _ferramenta_documentos(self, uso: _UsoDeDocumentos) -> Ferramenta:
        def consultar_documentos(pergunta: str, produto: str | None = None) -> dict:
            if not produto:
                trechos = self.base.buscar(pergunta, so_gerais=True, k=trechos_por_resposta())
                aviso = None
            else:
                produtos = self.repositorio.listar()
                achados = localizar_produto(produto, produtos)
                if not achados:
                    return {"erro": f"nenhum produto parecido com '{produto}'",
                            "produtos": [p.nome for p in produtos]}  # fmt: skip
                if len(achados) > 1:
                    return {"erro": "mais de um produto parecido", "opcoes": [p.nome for p in achados]}
                escolhido = achados[0]
                self.produto_atual = escolhido
                if self.base.tem_documentos(escolhido.id):
                    trechos = self.base.buscar(
                        f"{escolhido.nome}: {pergunta}", escolhido.id, trechos_por_resposta()
                    )
                    aviso = None
                else:
                    trechos = self._trechos_da_garantia_legal(pergunta)
                    uso.sem_termo = True
                    aviso = (
                        f"'{escolhido.nome}' não tem termo de garantia cadastrado. Comece a resposta com "
                        f"'Não há termo de garantia cadastrado para {escolhido.nome}. Pelo CDC:' e explique "
                        "o que a lei prevê."
                    )
            uso.trechos = trechos
            resultado = {"trechos": [{"fonte": t.fonte, "texto": t.texto} for t in trechos]}
            if aviso:
                resultado["aviso"] = aviso
            return resultado

        return Ferramenta(
            nome="consultar_documentos",
            funcao=consultar_documentos,
            descricao=(
                "Busca nos documentos: o termo de garantia do produto (se informar o produto) e o CDC. "
                "Use para a lei ('quanto tempo tenho para reclamar') e para o que a garantia de um "
                "produto cobre, exclui ou exige (assistência, perda de garantia, o que levar)."
            ),
            parametros={
                "pergunta": {"type": "string", "description": "a dúvida do usuário, com as palavras dele"},
                "produto": {
                    "type": "string",
                    "description": "nome do produto, se a pergunta é sobre a garantia de um produto "
                    "específico; omita para perguntas gerais da lei",
                },
            },
            obrigatorios=("pergunta",),
        )

    # ---------- ferramenta de assistências ----------

    def _ferramenta_assistencias(self) -> Ferramenta:
        def onde_acionar_garantia(produto: str, cidade: str, marca: str | None = None) -> dict:
            achados = localizar_produto(produto, self.repositorio.listar())
            if len(achados) != 1:
                return {"erro": "produto não identificado", "opcoes": [p.nome for p in achados]}
            escolhido = achados[0]
            self.produto_atual = escolhido
            try:
                local = localizar_cidade(cidade)
                if local is None:
                    return {"erro": f"não encontrei a cidade '{cidade}'; peça cidade e estado"}
                lugares = buscar_assistencias(local, escolhido.categoria, marca)
            except ErroDeBusca as erro:
                return {"erro": str(erro)}
            return {
                "produto": escolhido.nome,
                "perto_de": local.nome,
                "total": len(lugares),
                "lugares": [
                    {"nome": a.nome, "endereco": a.endereco, "telefone": a.telefone,
                     "distancia_km": a.distancia_km, "marca_confere": a.marca_confere}
                    for a in lugares
                ],  # fmt: skip
            }

        return Ferramenta(
            nome="onde_acionar_garantia",
            funcao=onde_acionar_garantia,
            descricao=(
                "Procura no mapa assistências e lojas perto de uma cidade que podem atender o produto. "
                "Use para 'onde aciono a garantia', 'onde levo a TV', 'tem assistência perto de mim'. "
                "Demora até 1 minuto na primeira busca de uma cidade."
            ),
            parametros={
                "produto": {"type": "string", "description": "nome do produto cadastrado"},
                "cidade": {"type": "string", "description": "cidade (e estado) do usuário"},
                "marca": {"type": "string", "description": "marca do produto, se souber; omita se não"},
            },
            obrigatorios=("produto", "cidade"),
        )

    def _trechos_da_garantia_legal(self, pergunta: str) -> list[TrechoEncontrado]:
        """Produto sem termo: busca a garantia legal direto, além da pergunta (mesma lógica do chat atual)."""
        trechos = self.base.buscar(CONSULTA_GARANTIA_LEGAL, so_gerais=True, k=2)
        for trecho in self.base.buscar(pergunta, so_gerais=True, k=2):
            if len(trechos) < trechos_por_resposta() and all(t.texto != trecho.texto for t in trechos):
                trechos.append(trecho)
        return trechos

    # ---------- o que a pergunta usou ----------

    def _atualizar_assunto(self, resposta) -> None:
        """Se uma ferramenta do cadastro tratou de um produto só, ele vira o assunto da conversa."""
        produtos = self.repositorio.listar()
        for consulta in resposta.consultas:
            if consulta.nome == "detalhes_produto":
                achados = localizar_produto(str(consulta.argumentos.get("nome", "")), produtos)
                if len(achados) == 1:
                    self.produto_atual = achados[0]
        if not any(c.nome == "detalhes_produto" for c in resposta.consultas):
            citados = [p for p in produtos if p.nome.lower() in resposta.texto.lower()]
            if len(citados) == 1 and any(c.nome in FERRAMENTAS_DO_CADASTRO for c in resposta.consultas):
                self.produto_atual = citados[0]

    @staticmethod
    def _rota(resposta, uso: _UsoDeDocumentos) -> str:
        """Equivale às rotas do chat com classificador, para a avaliação comparar os dois."""
        if not uso.trechos and resposta.texto.startswith(("De qual produto", "Encontrei mais de um")):
            return "esclarecimento"  # pode ter listado os produtos antes de perguntar
        if any(c.nome in FERRAMENTAS_DO_CADASTRO for c in resposta.consultas):
            return "agente"
        if uso.trechos:
            if uso.sem_termo:
                return "sem_termo"
            return "documentos_produto" if any(t.produto_id is not None for t in uso.trechos) else "cdc"
        return "esclarecimento" if "?" in resposta.texto else "outra"
