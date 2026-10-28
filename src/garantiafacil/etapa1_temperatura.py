"""Etapa 1: efeito da temperatura.

Rode com: uv run python -m garantiafacil.etapa1_temperatura
"""

from garantiafacil.llm import criar_llm

PERGUNTA = "Em uma frase, qual o prazo do CDC para reclamar de defeito em produto durável?"
SISTEMA = "Você explica direitos do consumidor brasileiro em linguagem simples."


def main():
    llm = criar_llm()

    for temperatura in (0.0, 1.0):
        print(f"\n=== temperatura {temperatura} ===")
        for i in range(1, 4):
            resposta = llm.perguntar(PERGUNTA, sistema=SISTEMA, temperatura=temperatura)
            print(f"{i}) {resposta.strip()}")


if __name__ == "__main__":
    main()
