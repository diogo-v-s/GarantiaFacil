"""Etapa 1: primeira chamada ao LLM.

Rode com: uv run python -m garantiafacil.etapa1_primeira_chamada
"""

from garantiafacil.llm import criar_llm


def main():
    llm = criar_llm()
    print(f"Provedor: {type(llm).__name__} | modelo: {llm.modelo}\n")

    sistema = "Você é um assistente que explica direitos do consumidor brasileiro em linguagem simples."
    pergunta = "Qual o minimo de garantia um produto comprado em loja e novo, deve ter?"

    print(llm.perguntar(pergunta))


if __name__ == "__main__":
    main()
