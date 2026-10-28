"""Embeddings: transformam texto em um vetor de números que representa o significado.

Textos com significado parecido geram vetores parecidos. A Anthropic não tem API de embeddings,
então usamos sempre o Ollama (local e gratuito), mesmo quando o LLM de chat for o Claude.
"""

import os

import numpy as np

MODELO_PADRAO = "bge-m3"  # multilíngue; o nomic-embed-text é fraco em português

# Alguns modelos foram treinados com prefixos que diferenciam o que se busca (a pergunta)
# do que está guardado (o documento). O bge-m3 não usa prefixos.
PREFIXOS = {
    "nomic-embed-text": ("search_query: ", "search_document: "),
}


def nome_modelo() -> str:
    return os.getenv("OLLAMA_MODELO_EMBEDDING", MODELO_PADRAO)


def gerar_embedding(texto: str, consulta: bool = False) -> np.ndarray:
    """Devolve o vetor do texto. `consulta=True` para o texto digitado na busca."""
    import ollama

    modelo = nome_modelo()
    prefixo_consulta, prefixo_documento = PREFIXOS.get(modelo.split(":")[0], ("", ""))
    prefixo = prefixo_consulta if consulta else prefixo_documento
    resposta = ollama.embed(model=modelo, input=prefixo + texto)
    return np.array(resposta.embeddings[0], dtype=np.float32)


def similaridade(a: np.ndarray, b: np.ndarray) -> float:
    """Similaridade de cosseno: 1 = mesma direção (significado igual), 0 = nada a ver.

    Mede o ângulo entre os vetores, ignorando o tamanho deles."""
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))
