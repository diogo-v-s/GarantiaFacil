"""Roda a avaliação do chat.

Uso (na pasta do projeto):
    uv run python -m avaliacao.rodar                 # todos os casos
    uv run python -m avaliacao.rodar --filtro cad    # só os que têm 'cad' no id ou no tipo
    uv run python -m avaliacao.rodar --limite 5      # só os 5 primeiros (teste rápido)

O provedor vem do .env (LLM_PROVIDER). O resultado é gravado em avaliacao/resultados/."""

import argparse
import json
from dataclasses import asdict
from datetime import date
from pathlib import Path

from avaliacao.base import HOJE, montar
from avaliacao.casos import CASOS
from garantiafacil.avaliacao import avaliar_caso, formatar, resumir
from garantiafacil.conversa import Conversa
from garantiafacil.llm import criar_llm

PASTA_RESULTADOS = Path(__file__).parent / "resultados"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--filtro", help="texto que deve aparecer no id ou no tipo do caso")
    parser.add_argument("--limite", type=int, help="roda só os N primeiros casos")
    argumentos = parser.parse_args()

    casos = [c for c in CASOS if not argumentos.filtro or argumentos.filtro in c.id + c.tipo]
    if argumentos.limite:
        casos = casos[: argumentos.limite]

    repo, base = montar()
    llm = criar_llm()
    modelo = getattr(llm, "modelo", "desconhecido")

    resultados = []
    for i, caso in enumerate(casos, 1):
        resultado = avaliar_caso(caso, lambda: Conversa(repo, base, llm, hoje=HOJE))
        resultados.append(resultado)
        marca = "OK  " if resultado.passou else "FALHA"
        print(f"[{i}/{len(casos)}] {marca} {caso.id} ({resultado.segundos:.0f}s)", flush=True)
        if not resultado.passou:
            print("        " + "; ".join(resultado.falhas), flush=True)

    resumo = resumir(resultados)
    print("\n" + formatar(resumo))

    PASTA_RESULTADOS.mkdir(exist_ok=True)
    parcial = "_parcial" if (argumentos.filtro or argumentos.limite) else ""  # não sobrescreve a rodada completa
    nome_arquivo = f"{date.today().isoformat()}_{modelo.replace(':', '-').replace('/', '-')}{parcial}.json"
    caminho = PASTA_RESULTADOS / nome_arquivo
    caminho.write_text(
        json.dumps(
            {
                "modelo": modelo,
                "data_simulada": HOJE.isoformat(),
                "nota": f"{resumo.acertos}/{resumo.total}",
                "resultados": [asdict(r) for r in resultados],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"\nResultado gravado em {caminho}")


if __name__ == "__main__":
    main()
