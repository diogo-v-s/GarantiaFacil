"""Etapa 4: o que é um embedding e como medir proximidade de significado.

Rode com: uv run python -m garantiafacil.etapa4_embeddings
"""

from garantiafacil.embeddings import gerar_embedding, similaridade

CONSULTA = "geladeira"

CANDIDATOS = [
    "Refrigerador Brastemp Frost Free 375L",
    "Freezer horizontal 300 litros",
    "Notebook Dell Inspiron",
    "Celular Motorola Moto G60",
    "Máquina de lavar roupa",
    "Banana prata",
]


def main():
    vetor_consulta = gerar_embedding(CONSULTA, consulta=True)
    print(f"Um embedding é isto: {len(vetor_consulta)} números. Os 5 primeiros de '{CONSULTA}':")
    print(vetor_consulta[:5], "\n")

    print(f"Similaridade com '{CONSULTA}' (de 0 a 1):\n")
    resultados = []
    for texto in CANDIDATOS:
        resultados.append((similaridade(vetor_consulta, gerar_embedding(texto)), texto))

    for nota, texto in sorted(resultados, reverse=True):
        print(f"  {nota:.3f}  {texto}")


if __name__ == "__main__":
    main()
