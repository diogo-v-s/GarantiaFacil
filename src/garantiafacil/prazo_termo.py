"""Lê o prazo de garantia que consta num termo de garantia (texto), com a ajuda da IA.

O termo é texto livre ("12 meses", "1 ano", "90 dias", "180 dias após a emissão da nota"), então
quem lê é o LLM, que também converte para meses. Mas a IA pode inventar um número: por isso a
resposta traz a frase de onde ela tirou o prazo, e só aceitamos se essa frase existe mesmo no
texto do termo. Um prazo inventado é pior do que nenhum."""

import re
from dataclasses import dataclass

from pydantic import BaseModel, Field

from garantiafacil.llm import criar_llm

LIMITE_CARACTERES = 6000  # do texto enviado à IA
MESES_MAXIMO = 120  # o mesmo limite do campo "Garantia (meses)" do cadastro

SISTEMA = (
    "Você lê termos de garantia de produtos e informa o prazo de garantia que o termo oferece. "
    "Responda só com o que está escrito no texto; nunca estime nem invente."
)

# Só os parágrafos que falam de prazo vão para a IA: menos texto, menos chance de confundir o
# prazo da garantia com outro número (prazo de entrega, de assistência técnica etc.).
_FALA_DE_PRAZO = re.compile(r"garant|prazo|\bmes(es)?\b|\bano(s)?\b|\bdias?\b", re.IGNORECASE)


class PrazoLido(BaseModel):
    """O que a IA é obrigada a devolver. Campos obrigatórios: com campo opcional, o modelo pequeno
    tendia a responder 'não achei' em tudo."""

    encontrou: bool = Field(description="true se o texto informa um prazo de garantia do produto")
    meses: int = Field(
        description="Prazo total da garantia em MESES. Converta: 1 ano = 12 meses, 90 dias = 3 meses, "
        "180 dias = 6 meses. Se o termo soma garantia legal e do fabricante, informe o total. "
        "Use 0 se não encontrou."
    )
    trecho: str = Field(
        description="A frase do texto que informa o prazo, copiada EXATAMENTE como está escrita. "
        "Vazio se não encontrou."
    )


@dataclass(frozen=True)
class SugestaoPrazo:
    meses: int
    trecho: str


def _normalizar(texto: str) -> str:
    return re.sub(r"\s+", " ", texto).strip().casefold()


def _texto_para_ler(paginas: list[tuple[int, str]]) -> str:
    """Os parágrafos que falam de prazo, na ordem do documento, até o limite de caracteres."""
    escolhidos: list[str] = []
    tamanho = 0
    for _, texto in paginas:
        for paragrafo in re.split(r"\n\s*\n", texto):
            paragrafo = re.sub(r"\s*\n\s*", " ", paragrafo).strip()
            if not paragrafo or not _FALA_DE_PRAZO.search(paragrafo):
                continue
            if tamanho + len(paragrafo) > LIMITE_CARACTERES:
                return "\n\n".join(escolhidos)
            escolhidos.append(paragrafo)
            tamanho += len(paragrafo)
    return "\n\n".join(escolhidos)


def sugerir_prazo(paginas: list[tuple[int, str]], llm=None) -> SugestaoPrazo | None:
    """O prazo (em meses) que o termo informa, com a frase de origem; None se não achou ou se a
    resposta da IA não passou nas conferências (meses fora de 1 a 120, frase que não está no texto)."""
    texto = _texto_para_ler(paginas)
    if not texto:
        return None

    llm = llm or criar_llm()
    lido = llm.estruturar(
        f"Texto do termo de garantia:\n\n{texto}\n\nQual é o prazo de garantia do produto?",
        PrazoLido,
        sistema=SISTEMA,
    )
    if not lido.encontrou or not 1 <= lido.meses <= MESES_MAXIMO:
        return None
    trecho = lido.trecho.strip()
    if not trecho or _normalizar(trecho) not in _normalizar(texto):
        return None
    return SugestaoPrazo(meses=lido.meses, trecho=trecho)
