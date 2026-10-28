"""Mede só o classificador do chat (sem responder), nos casos de uma mensagem da avaliação.

Uso: uv run python -m avaliacao.classificador

Serve para separar "o classificador errou o caminho" de "o caminho certo respondeu mal"."""

from avaliacao.casos import CASOS
from garantiafacil.conversa import SISTEMA_ANALISE, Analise
from garantiafacil.llm import criar_llm


def caminho_esperado(rota) -> str | None:
    """cadastro / lei / produto, ou None quando qualquer um serve (esclarecimento)."""
    aceitas = (rota,) if isinstance(rota, str) else tuple(rota)
    if "agente" in aceitas and len(aceitas) == 1:
        return "cadastro"
    if aceitas == ("cdc",):
        return "lei"
    if set(aceitas) <= {"documentos_produto", "sem_termo"}:
        return "produto"
    return None


def caminho_obtido(analise: Analise) -> str:
    return analise.assunto


def main():
    llm = criar_llm()
    casos = [c for c in CASOS if len(c.mensagens) == 1 and caminho_esperado(c.rota) and not c.opcional]
    certos = 0
    erros_por_tipo: dict[str, int] = {}
    for caso in casos:
        analise = llm.estruturar(caso.mensagens[0], Analise, sistema=SISTEMA_ANALISE)
        esperado, obtido = caminho_esperado(caso.rota), caminho_obtido(analise)
        ok = esperado == obtido
        certos += ok
        if not ok:
            erros_por_tipo[f"{esperado}->{obtido}"] = erros_por_tipo.get(f"{esperado}->{obtido}", 0) + 1
        print(("OK   " if ok else "ERRO ") + f"{caso.id:<26} esperado={esperado:<9} obtido={obtido}", flush=True)
    print(f"\nClassificador: {certos}/{len(casos)} ({certos / len(casos):.0%})")
    for tipo, n in sorted(erros_por_tipo.items()):
        print(f"  erros {tipo}: {n}")


if __name__ == "__main__":
    main()
