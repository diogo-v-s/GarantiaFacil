"""Conversa sobre garantia: responde com o CDC e, quando a pergunta depende de um produto,
pergunta de qual produto o usuário fala e usa o termo de garantia dele.

Fluxo de cada mensagem:
  1. Se estávamos esperando o produto, a mensagem é a resposta a "de qual produto?".
  2. Senão, a IA classifica a pergunta: é geral (lei) ou depende de um produto?
  3. Geral: responde só com os documentos gerais (CDC).
     Depende de produto: usa o produto citado; se não houver, o do assunto atual;
     se também não houver, pergunta.
"""

import re
import unicodedata
from dataclasses import dataclass, field

from pydantic import BaseModel, Field

from garantiafacil.modelos import Produto
from garantiafacil.rag import BaseConhecimento, TrechoEncontrado

SISTEMA_ANALISE = (
    "Você classifica perguntas de um usuário que consulta garantias de produtos que comprou.\n"
    "- precisa_produto = true quando a pergunta só pode ser respondida sabendo de QUAL produto "
    "o usuário fala (o que a garantia do produto cobre, o prazo do aparelho dele, bateria, "
    "tela, assistência técnica do produto).\n"
    "- precisa_produto = false quando for uma pergunta geral sobre direitos do consumidor ou "
    "sobre a lei, sem depender de um produto específico.\n"
    "- produto_citado = o nome ou descrição do produto, copiado das palavras do usuário. "
    "Deixe vazio se ele não citou nenhum produto.\n\n"
    "Exemplos:\n"
    "'A garantia cobre tela quebrada?' -> precisa_produto true, produto_citado ''\n"
    "'A garantia do meu celular Moto G60 cobre a bateria?' -> true, 'celular Moto G60'\n"
    "'Qual o prazo do CDC para reclamar de defeito?' -> false, ''\n"
    "'Posso desistir de uma compra feita pela internet?' -> false, ''"
)

# Menos trechos = prompt menor = resposta mais rápida na CPU, mas o modelo vê menos contexto.
# Era 5; voltar a 5 (ou mais) quando o chat passar para o Claude.
TRECHOS_POR_RESPOSTA = 3

_PALAVRAS_VAZIAS = {
    "de", "da", "do", "das", "dos", "o", "a", "os", "as", "um", "uma", "meu", "minha",
    "no", "na", "com", "para", "por", "e",
}  # fmt: skip


class Analise(BaseModel):
    """Classificação da pergunta. Campos obrigatórios: com null opcional o modelo local
    deixava tudo vazio (mesma lição da leitura de nota fiscal)."""

    precisa_produto: bool = Field(
        description="true se a resposta depende de qual produto específico o usuário tem"
    )
    produto_citado: str = Field(
        description="Produto citado pelo usuário, nas palavras dele; vazio se não citou"
    )


@dataclass
class Mensagem:
    texto: str
    trechos: list[TrechoEncontrado] = field(default_factory=list)
    citacoes_invalidas: list[int] = field(default_factory=list)
    produto: Produto | None = None  # produto usado na resposta, se houve


def _tokens(texto: str) -> set[str]:
    """Palavras minúsculas e sem acento, sem as palavras vazias ('de', 'o', 'meu'...)."""
    sem_acento = unicodedata.normalize("NFD", texto.lower())
    sem_acento = "".join(c for c in sem_acento if unicodedata.category(c) != "Mn")
    return set(re.findall(r"[a-z0-9]+", sem_acento)) - _PALAVRAS_VAZIAS


def localizar_produto(texto: str, produtos: list[Produto]) -> list[Produto]:
    """Produtos cujo nome mais se parece com o texto, pelas palavras em comum.

    Devolve vários se houver empate no topo (ambíguo) e lista vazia se nenhuma palavra bater.
    Casamento por palavras, e não por significado, porque 'Moto G60' não é reconhecido como
    'celular' pelo modelo de embeddings."""
    palavras = _tokens(texto)
    pontuados = [(len(palavras & _tokens(p.nome)), p) for p in produtos]
    melhor = max((n for n, _ in pontuados), default=0)
    if melhor == 0:
        return []
    return [p for n, p in pontuados if n == melhor]


class Conversa:
    def __init__(self, repositorio, base: BaseConhecimento, llm):
        self.repositorio = repositorio
        self.base = base
        self.llm = llm
        self.pergunta_pendente: str | None = None  # aguardando o usuário dizer o produto
        self.produto_atual: Produto | None = None  # assunto da conversa

    def reiniciar(self) -> None:
        self.pergunta_pendente = None
        self.produto_atual = None

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
        if not analise.precisa_produto:
            return self._responder(mensagem, so_gerais=True)

        produto = self.produto_atual
        if analise.produto_citado.strip():
            candidatos = self._candidatos(analise.produto_citado, produtos)
            if len(candidatos) == 1:
                produto = self.produto_atual = candidatos[0]
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

    def _resolver_produto_pendente(self, mensagem: str, produtos: list[Produto]) -> Mensagem | None:
        """Trata a mensagem como resposta a 'de qual produto?'. Devolve None se for uma
        pergunta nova (tem '?' e não identifica nenhum produto)."""
        candidatos = self._candidatos(mensagem, produtos)

        if len(candidatos) == 1:
            pergunta, self.pergunta_pendente = self.pergunta_pendente, None
            self.produto_atual = candidatos[0]
            return self._responder_sobre(pergunta, candidatos[0])

        if not candidatos and "?" in mensagem:
            self.pergunta_pendente = None
            return None

        return self._perguntar_produto(self.pergunta_pendente, produtos, candidatos)

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
        self, pergunta: str, produtos: list[Produto], candidatos: list[Produto]
    ) -> Mensagem:
        self.pergunta_pendente = pergunta
        if len(candidatos) > 1:
            opcoes = [p.nome for p in candidatos]
            intro = "Encontrei mais de um produto parecido. Qual deles?"
        else:
            opcoes = [p.nome for p in produtos]
            intro = "De qual produto você está falando?"
        lista = "\n".join(f"- {nome}" for nome in opcoes)
        return Mensagem(f"{intro}\n\n{lista}")

    def _responder_sobre(self, pergunta: str, produto: Produto) -> Mensagem:
        aviso = ""
        if not self.base.tem_documentos(produto.id):
            aviso = (
                f"'{produto.nome}' ainda não tem termo de garantia ou manual cadastrado, "
                "então respondi só com o CDC.\n\n"
            )
        return self._responder(pergunta, produto=produto, aviso=aviso)

    def _responder(
        self,
        pergunta: str,
        produto: Produto | None = None,
        so_gerais: bool = False,
        aviso: str = "",
    ) -> Mensagem:
        resposta = self.base.responder(
            pergunta,
            self.llm,
            produto_id=produto.id if produto else None,
            k=TRECHOS_POR_RESPOSTA,
            so_gerais=so_gerais,
        )
        return Mensagem(
            texto=aviso + resposta.texto,
            trechos=resposta.trechos,
            citacoes_invalidas=resposta.citacoes_invalidas,
            produto=produto,
        )
