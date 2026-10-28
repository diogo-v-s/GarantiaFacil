"""Etapa 5: RAG de ponta a ponta com um termo de garantia de exemplo.

Rode com: uv run python -m garantiafacil.etapa5_rag
"""

from pathlib import Path

from garantiafacil.db import conectar
from garantiafacil.documentos import extrair_paginas
from garantiafacil.llm import criar_llm
from garantiafacil.rag import BaseConhecimento

DOCUMENTO = Path(__file__).resolve().parents[2] / "docs" / "exemplos" / "termo-garantia-exemplo.txt"

PERGUNTAS = [
    "A garantia cobre tela quebrada?",
    "Quanto tempo dura a garantia da bateria?",
    "Preciso da nota fiscal para acionar a garantia?",
    "Posso usar o aparelho em viagens internacionais?",  # não está no documento
]


def main():
    base = BaseConhecimento(conectar(":memory:"))  # banco temporário, só para a demonstração
    llm = criar_llm()

    paginas = extrair_paginas(DOCUMENTO.name, DOCUMENTO.read_bytes())
    print(f"Documento indexado em {base.indexar(DOCUMENTO.name, paginas)} trechos.\n")

    for pergunta in PERGUNTAS:
        resposta = base.responder(pergunta, llm)
        print(f"PERGUNTA: {pergunta}")
        print(f"RESPOSTA: {resposta.texto}")
        if resposta.citacoes_invalidas:
            print(f"   ALERTA: citou trechos inexistentes {resposta.citacoes_invalidas}")
        for i, t in enumerate(resposta.trechos, 1):
            print(f"   [{i}] similaridade {t.similaridade:.2f} | {t.texto[:70]!r}...")
        print()


if __name__ == "__main__":
    main()
