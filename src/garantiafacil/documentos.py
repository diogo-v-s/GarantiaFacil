"""Leitura de documentos (PDF e texto) e divisão em trechos para o RAG."""

import io
import re
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Trecho:
    pagina: int
    texto: str


def extrair_paginas(nome_arquivo: str, conteudo: bytes) -> list[tuple[int, str]]:
    """Devolve [(número da página, texto)]. Lista vazia se não houver texto extraível
    (PDF escaneado, que só teria imagem, ou arquivo corrompido)."""
    if Path(nome_arquivo).suffix.lower() == ".pdf":
        from pypdf import PdfReader

        try:
            leitor = PdfReader(io.BytesIO(conteudo))
            paginas = [(i + 1, pagina.extract_text() or "") for i, pagina in enumerate(leitor.pages)]
        except Exception:
            return []
    else:
        paginas = [(1, conteudo.decode("utf-8", errors="replace"))]

    return [(numero, texto) for numero, texto in paginas if texto.strip()]


def _quebrar_paragrafo_grande(paragrafo: str, tamanho: int) -> list[str]:
    """Quebra um parágrafo maior que `tamanho` em frases, sem cortar palavras."""
    pedacos, atual = [], ""
    for frase in re.split(r"(?<=[.!?;])\s+", paragrafo):
        while len(frase) > tamanho:  # frase gigante: corta no último espaço antes do limite
            corte = frase.rfind(" ", 0, tamanho)
            corte = corte if corte > 0 else tamanho
            pedacos.append(frase[:corte].strip())
            frase = frase[corte:].strip()
        if atual and len(atual) + len(frase) + 1 > tamanho:
            pedacos.append(atual)
            atual = frase
        else:
            atual = f"{atual} {frase}".strip()
    if atual:
        pedacos.append(atual)
    return pedacos


def _cauda(texto: str, tamanho: int) -> str:
    """Os últimos `tamanho` caracteres, começando numa palavra inteira."""
    cauda = texto[-tamanho:]
    primeiro_espaco = cauda.find(" ")
    return cauda[primeiro_espaco + 1 :] if 0 <= primeiro_espaco < len(cauda) - 1 else cauda


def dividir_em_trechos(
    paginas: list[tuple[int, str]], tamanho: int = 800, sobreposicao: int = 150
) -> list[Trecho]:
    """Divide o texto em trechos de até ~`tamanho` caracteres, respeitando parágrafos.

    Por que dividir: o embedding de um documento inteiro "dilui" o significado, e o prompt
    do LLM tem limite. Trechos pequenos permitem achar e citar a passagem exata.
    Por que sobreposição: o fim de um trecho se repete no começo do próximo, para que uma
    frase que fica na fronteira não perca o contexto."""
    trechos: list[Trecho] = []

    for numero, texto in paginas:
        paragrafos = [p.strip() for p in re.split(r"\n\s*\n", texto) if p.strip()]
        atual = ""

        for paragrafo in paragrafos:
            paragrafo = re.sub(r"\s*\n\s*", " ", paragrafo)  # quebras de linha viram espaço
            for pedaco in _quebrar_paragrafo_grande(paragrafo, tamanho):
                if atual and len(atual) + len(pedaco) + 2 > tamanho:
                    trechos.append(Trecho(numero, atual))
                    atual = f"{_cauda(atual, sobreposicao)}\n\n{pedaco}"
                else:
                    atual = f"{atual}\n\n{pedaco}".strip()

        if atual:
            trechos.append(Trecho(numero, atual))

    return trechos
