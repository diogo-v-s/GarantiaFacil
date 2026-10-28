"""Encontrar produtos pelo nome, por palavras em comum (sem acento, sem 'de', 'o', 'meu'...)."""

import re
import unicodedata

from garantiafacil.modelos import Produto

_PALAVRAS_VAZIAS = {
    "de", "da", "do", "das", "dos", "o", "a", "os", "as", "um", "uma", "meu", "minha",
    "no", "na", "com", "para", "por", "e",
}  # fmt: skip


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
