"""Conversa sobre garantia: responde com o CDC e, quando a pergunta depende de um produto,
pergunta de qual produto o usuário fala e usa o termo de garantia dele.

Fluxo de cada mensagem:
  1. Se estávamos esperando o produto, a mensagem é a resposta a "de qual produto?".
  2. Senão, a IA classifica a pergunta: é geral (lei) ou depende de um produto?
  3. Geral: responde só com os documentos gerais (CDC).
     Depende de produto: usa o produto citado; se não houver, o do assunto atual;
     se também não houver, pergunta.
"""

import os
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date
from typing import Literal

from pydantic import BaseModel, Field

from garantiafacil.agente import Consulta, executar_agente
from garantiafacil.ferramentas_cadastro import criar_ferramentas, sistema_agente
from garantiafacil.localizar import localizar_produto
from garantiafacil.modelos import Produto
from garantiafacil.rag import NAO_ENCONTREI, BaseConhecimento, TrechoEncontrado

SISTEMA_ANALISE = (
    "Você classifica a pergunta de um usuário que guarda as notas e garantias dos produtos que comprou.\n"
    "assunto = cadastro: pergunta sobre os produtos que ele cadastrou (quais tem, quando comprou, "
    "quando vence a garantia, quanto pagou, o que vence nos próximos dias).\n"
    "assunto = lei: pergunta geral sobre direitos do consumidor ou prazos da lei.\n"
    "assunto = produto: pergunta sobre o que a garantia, o termo, a cobertura ou a assistência de "
    "um produto específico dele.\n"
    "produto_citado = o nome ou a descrição do produto, copiado das palavras do usuário; vazio se "
    "ele não citou nenhum.\n\n"
    "Exemplos:\n"
    "'Que produtos eu já cadastrei?' -> cadastro\n"
    "'Em que dia vence a garantia do meu fogão?' -> cadastro\n"
    "'Qual foi o preço que paguei no monitor?' -> cadastro\n"
    "'Algum aparelho meu está com a garantia acabando?' -> cadastro\n"
    "'O que vai vencer este mês?' -> cadastro\n"
    "'Qual dos meus aparelhos perde a garantia primeiro?' -> cadastro\n"
    "'Em quantos dias posso me arrepender de uma compra?' -> lei\n"
    "'O que o código do consumidor diz sobre propaganda enganosa?' -> lei\n"
    "'Até quando posso exigir conserto de um produto estragado?' -> lei\n"
    "'O termo do meu fogão cobre queimadura na mesa?' -> produto\n"
    "'O liquidificador tem assistência em qualquer cidade?' -> produto\n"
    "'O que a garantia do meu ventilador não cobre?' -> produto"
)

# Menos trechos = prompt menor = resposta mais rápida, mas o modelo vê menos contexto.
# O modelo local roda na CPU e fica lento com prompt grande; o Claude lê 5 trechos sem custo de tempo.
TRECHOS_OLLAMA = 3
TRECHOS_CLAUDE = 5


def trechos_por_resposta() -> int:
    """Quantos trechos entregar ao modelo, conforme o provedor (LLM_PROVIDER no .env)."""
    claude = os.getenv("LLM_PROVIDER", "ollama").lower() == "claude"
    return TRECHOS_CLAUDE if claude else TRECHOS_OLLAMA

# Resposta do usuário que é só a posição de uma opção: "2", "o 2", "número 2", "o primeiro".
_ORDINAIS = {"primeiro": 1, "primeira": 1, "segundo": 2, "segunda": 2, "terceiro": 3, "terceira": 3,
             "quarto": 4, "quarta": 4, "quinto": 5, "quinta": 5}  # fmt: skip
_RESPOSTA_POSICAO = re.compile(
    r"^(?:(?:o|a|numero|opcao|n)\s*)?(?:(?P<n>\d+)|(?P<ord>" + "|".join(_ORDINAIS) + r"))$"
)

# Produto sem termo de garantia: vale a garantia legal do CDC. A pergunta do usuário
# ("o que a garantia cobre?") nem sempre acha os artigos certos (medimos: trouxe o art. 50 em vez
# dos arts. 18 e 26), então buscamos a garantia legal direto, além da pergunta.
CONSULTA_GARANTIA_LEGAL = (
    "vício do produto: prazo para reclamar de produto durável noventa dias, substituição, "
    "conserto ou restituição do valor pago"
)

SISTEMA_SEM_TERMO = (
    "O produto do usuário não tem termo de garantia cadastrado, então vale a garantia legal do "
    "Código de Defesa do Consumidor. Com base nos trechos, explique em português o que a lei "
    "prevê sobre a pergunta (defeitos, prazos para reclamar, o que o consumidor pode exigir), "
    "citando o número do trecho, como [1], só no fim da frase. Nunca escreva a palavra "
    "'trecho' no texto da resposta. Responda em no máximo 5 linhas, sem repetir a "
    "pergunta e sem introdução. Cite apenas números de trechos que existem. "
    "Se os trechos não tratarem exatamente da pergunta, explique o que a lei garante em geral. "
    "Não diga que não encontrou."
)


class Analise(BaseModel):
    """Classificação da pergunta, numa escolha de 3 opções.

    Antes eram dois campos sim/não (sobre_cadastro e precisa_produto) e o modelo local caía no
    "não" nos dois: acertava 64% dos casos da avaliação. Com uma escolha entre 3 opções, 77%
    (medido com exemplos que não repetem os casos de teste). Campos obrigatórios, como sempre."""

    assunto: Literal["cadastro", "lei", "produto"] = Field(
        description=(
            "cadastro = pede dados dos produtos que o usuário cadastrou (quais, datas, valores, o que "
            "vence); lei = pergunta geral sobre direitos do consumidor, sem citar um produto dele; "
            "produto = pergunta o que a garantia ou o termo de UM produto específico cobre ou exige"
        )
    )
    produto_citado: str = Field(
        description="Produto citado pelo usuário, nas palavras dele; vazio se não citou"
    )

    @property
    def sobre_cadastro(self) -> bool:
        return self.assunto == "cadastro"

    @property
    def precisa_produto(self) -> bool:
        return self.assunto == "produto"

@dataclass
class Mensagem:
    texto: str
    trechos: list[TrechoEncontrado] = field(default_factory=list)
    citacoes_invalidas: list[int] = field(default_factory=list)
    produto: Produto | None = None  # produto usado na resposta, se houve
    consultas: list[Consulta] = field(default_factory=list)  # ferramentas que o agente usou
    rota: str | None = None  # só o chat sem classificador preenche; senão a avaliação deduz do resto


_SINAIS_DE_CADASTRO = re.compile(
    r"\b(vence|vencem|venceu|venceram|vencimento|comprei|paguei|gastei|cadastrei)\b"
)
# Com estas palavras a pergunta é de cobertura, de lei ou condicional: fica com o classificador.
_SINAIS_DE_OUTRO_ASSUNTO = re.compile(
    r"\b(cobre|cobrir|cobertura|assistencia|lei|codigo|cdc|direito|direitos|posso|se)\b"
)


def _fala_do_cadastro(mensagem: str) -> bool:
    """A mensagem tem um verbo claro de dado cadastrado (vence, comprei, paguei...) e nada que
    indique cobertura, lei ou condição?"""
    texto = _normalizar(mensagem)
    return bool(_SINAIS_DE_CADASTRO.search(texto)) and not _SINAIS_DE_OUTRO_ASSUNTO.search(texto)


def _normalizar(texto: str) -> str:
    """Minúsculas e sem acento ('Número' -> 'numero')."""
    decomposto = unicodedata.normalize("NFD", texto.lower())
    return "".join(c for c in decomposto if unicodedata.category(c) != "Mn")


class Conversa:
    def __init__(self, repositorio, base: BaseConhecimento, llm, hoje: date | None = None):
        self.repositorio = repositorio
        self.base = base
        self.llm = llm
        self.hoje = hoje  # None = data de hoje; a avaliação fixa uma data para repetir os resultados
        self.pergunta_pendente: str | None = None  # aguardando o usuário dizer o produto
        self.produto_atual: Produto | None = None  # assunto da conversa
        self.opcoes_pendentes: list[Produto] = []  # as opções numeradas da última pergunta

    def reiniciar(self) -> None:
        self.pergunta_pendente = None
        self.produto_atual = None
        self.opcoes_pendentes = []

    # ---------- entrada ----------

    def responder(self, mensagem: str) -> Mensagem:
        mensagem = mensagem.strip()
        produtos = self.repositorio.listar()

        if self.pergunta_pendente:
            retorno = self._resolver_produto_pendente(mensagem, produtos)
            if retorno is not None:
                return retorno
            # a mensagem era uma pergunta nova: segue o fluxo normal

        analise = self.llm.estruturar(self._prompt_analise(mensagem), Analise, sistema=SISTEMA_ANALISE)
        if analise.assunto != "cadastro" and _fala_do_cadastro(mensagem):
            # O classificador local oscila ("quando vence a garantia do LP KODAK?" saiu como
            # produto e respondeu com o CDC). Palavras como "vence" e "paguei" não deixam dúvida.
            analise = Analise(assunto="cadastro", produto_citado=analise.produto_citado)
        # "cadastro" e "produto" são exclusivos: "o que a garantia desse produto cobre?" é de termo
        # e lei, e o agente só conhece o cadastro (quando eram dois sim/não, inventava a cobertura).
        if analise.sobre_cadastro:
            return self._responder_cadastro(mensagem)
        if not analise.precisa_produto:
            resposta = self._responder(mensagem, so_gerais=True)
            if produtos and resposta.texto.startswith(NAO_ENCONTREI):
                # Rede de segurança: o classificador local erra, e a pergunta pode ser sobre um
                # produto ("o que a garantia do celular cobria?"). O CDC não respondeu, então
                # tentamos com o produto da conversa ou perguntamos qual é.
                if self.produto_atual is not None:
                    return self._responder_sobre(mensagem, self.produto_atual)
                return self._perguntar_produto(
                    mensagem, produtos, [],
                    intro="Não achei isso nas leis. A pergunta é sobre algum dos seus produtos? Qual?",
                )  # fmt: skip
            return resposta

        produto = self.produto_atual
        if analise.produto_citado.strip():
            # Com um produto já em discussão, só vale casar pelo nome: a busca por significado
            # trocava o assunto em silêncio ("desse produto" virava o iPhone; caso ctx-02).
            if produto is not None:
                candidatos = localizar_produto(analise.produto_citado, produtos)
            else:
                candidatos = self._candidatos(analise.produto_citado, produtos)
            if len(candidatos) == 1:
                produto = self.produto_atual = candidatos[0]
            elif not candidatos and produto is not None:
                pass  # "dessa lente": nada bate com o nome, então segue no produto da conversa
            else:
                return self._perguntar_produto(mensagem, produtos, candidatos)

        if produto is None:
            if not produtos:
                aviso = "Você ainda não tem produtos cadastrados, então respondi só com o CDC.\n\n"
                return self._responder(mensagem, so_gerais=True, aviso=aviso)
            return self._perguntar_produto(mensagem, produtos, [])

        return self._responder_sobre(mensagem, produto)

    # ---------- passos ----------

    def _prompt_analise(self, mensagem: str) -> str:
        """Sozinha, 'e o prazo?' parece geral. Com o produto da conversa no prompt, o
        classificador entende que é sobre ele."""
        if self.produto_atual is None:
            return mensagem
        return (
            f"(A conversa é sobre o produto '{self.produto_atual.nome}'. Perguntas curtas de "
            f"seguimento, como 'e o prazo?', são sobre ele.)\nMensagem: {mensagem}"
        )

    def _responder_cadastro(self, pergunta: str) -> Mensagem:
        """Pergunta sobre os produtos cadastrados: o agente consulta o banco com ferramentas."""
        resposta = executar_agente(
            self.llm,
            pergunta,
            criar_ferramentas(self.repositorio, self.hoje),
            sistema_agente(self.hoje),
        )
        # Se a resposta fala de um produto só, ele vira o assunto: "e o que a garantia dessa
        # lente cobre?" na pergunta seguinte já sabe de qual produto se trata.
        citados = [p for p in self.repositorio.listar() if p.nome.lower() in resposta.texto.lower()]
        if len(citados) == 1:
            self.produto_atual = citados[0]
        return Mensagem(texto=resposta.texto, consultas=resposta.consultas)

    def _resolver_produto_pendente(self, mensagem: str, produtos: list[Produto]) -> Mensagem | None:
        """Trata a mensagem como resposta a 'de qual produto?'. Devolve None se for uma
        pergunta nova (tem '?' e não identifica nenhum produto)."""
        escolhido = self._escolha_por_posicao(mensagem)
        candidatos = [escolhido] if escolhido else self._candidatos(mensagem, produtos)

        if len(candidatos) == 1:
            pergunta, self.pergunta_pendente = self.pergunta_pendente, None
            self.produto_atual = candidatos[0]
            return self._responder_sobre(pergunta, candidatos[0])

        if not candidatos and "?" in mensagem:
            self.pergunta_pendente = None
            return None

        intro = None
        if not candidatos:
            intro = "Não entendi qual produto. Responda com o nome ou com o número:"
        return self._perguntar_produto(self.pergunta_pendente, produtos, candidatos, intro=intro)

    def _candidatos(self, texto: str, produtos: list[Produto]) -> list[Produto]:
        """Primeiro por palavras em comum; se nada bater, tenta por significado."""
        achados = localizar_produto(texto, produtos)
        if achados:
            return achados

        semanticos = self.repositorio.buscar_semantico(texto, limite=2, minimo=0.55)
        if len(semanticos) == 1 or (
            len(semanticos) == 2 and semanticos[0][1] - semanticos[1][1] >= 0.05
        ):
            return [semanticos[0][0]]
        return [produto for produto, _ in semanticos]

    def _perguntar_produto(
        self,
        pergunta: str,
        produtos: list[Produto],
        candidatos: list[Produto],
        intro: str | None = None,
    ) -> Mensagem:
        self.pergunta_pendente = pergunta
        if len(candidatos) > 1:
            opcoes = candidatos
            intro = "Encontrei mais de um produto parecido. Qual deles?"
        else:
            opcoes = produtos
            intro = intro or "De qual produto você está falando?"
        self.opcoes_pendentes = list(opcoes)
        # Numeradas: dá para responder "2" ou "o primeiro", sem depender de o nome bater.
        lista = "\n".join(f"{i}. {p.nome}" for i, p in enumerate(opcoes, 1))
        return Mensagem(f"{intro}\n\n{lista}")

    def _escolha_por_posicao(self, mensagem: str) -> Produto | None:
        """'2', 'o 2', 'número 2', 'o primeiro', 'a segunda' -> a opção correspondente."""
        texto = _normalizar(mensagem).strip(" .!")
        achado = _RESPOSTA_POSICAO.match(texto)
        if not achado:
            return None
        posicao = int(achado.group("n")) if achado.group("n") else _ORDINAIS[achado.group("ord")]
        if 1 <= posicao <= len(self.opcoes_pendentes):
            return self.opcoes_pendentes[posicao - 1]
        return None

    def _responder_sobre(self, pergunta: str, produto: Produto) -> Mensagem:
        if not self.base.tem_documentos(produto.id):
            return self._responder_sem_termo(pergunta, produto)
        return self._responder(pergunta, produto=produto)

    def _responder_sem_termo(self, pergunta: str, produto: Produto) -> Mensagem:
        """Sem termo cadastrado: avisa e explica o que o CDC prevê (garantia legal)."""
        trechos = self.base.buscar(CONSULTA_GARANTIA_LEGAL, so_gerais=True, k=2)
        for trecho in self.base.buscar(pergunta, so_gerais=True, k=2):
            if len(trechos) < trechos_por_resposta() and all(t.texto != trecho.texto for t in trechos):
                trechos.append(trecho)
        resposta = self.base.responder_com_trechos(pergunta, self.llm, trechos, SISTEMA_SEM_TERMO)
        aviso = f"Não há termo de garantia cadastrado para '{produto.nome}'. Pelo CDC:\n\n"
        return Mensagem(
            texto=aviso + resposta.texto,
            trechos=resposta.trechos,
            citacoes_invalidas=resposta.citacoes_invalidas,
            produto=produto,
        )

    def _responder(
        self,
        pergunta: str,
        produto: Produto | None = None,
        so_gerais: bool = False,
        aviso: str = "",
    ) -> Mensagem:
        # Perguntas de seguimento ("e o prazo?") não dizem de que se trata: a busca leva o nome do
        # produto junto, senão acha trechos do CDC em vez do termo dele (caso ctx-03 da avaliação).
        consulta = f"{produto.nome}: {pergunta}" if produto else pergunta
        trechos = self.base.buscar(
            consulta, produto.id if produto else None, trechos_por_resposta(), so_gerais
        )
        resposta = self.base.responder_com_trechos(pergunta, self.llm, trechos)
        return Mensagem(
            texto=aviso + resposta.texto,
            trechos=resposta.trechos,
            citacoes_invalidas=resposta.citacoes_invalidas,
            produto=produto,
        )
