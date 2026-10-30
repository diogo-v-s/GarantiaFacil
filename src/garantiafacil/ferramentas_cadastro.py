"""Ferramentas que o agente usa para consultar os produtos cadastrados.

Cada ferramenta é uma função Python comum. O que o modelo enxerga é só o nome, a descrição e
os parâmetros: por isso as descrições dizem claramente QUANDO usar e O QUE devolve."""

import unicodedata
from datetime import date

from garantiafacil.agente import Ferramenta
from garantiafacil.garantia import data_vencimento, dias_restantes, status_garantia
from garantiafacil.localizar import localizar_produto
from garantiafacil.modelos import Categoria, Produto

# Os status internos são 'vigente', 'vence_em_breve' e 'vencida'. Para o usuário, "garantia
# vigente" inclui a que está para vencer; por isso o filtro 'em_garantia' junta as duas.
FILTROS_STATUS = {
    "em_garantia": {"vigente", "vence_em_breve"},
    "vencendo_em_breve": {"vence_em_breve"},
    "vencida": {"vencida"},
}


def sistema_agente(hoje: date | None = None) -> str:
    hoje = hoje or date.today()
    return (
        "Você é o assistente do TáGuardado e ajuda o usuário a consultar os produtos que ele "
        f"cadastrou e suas garantias. Hoje é {hoje.strftime('%d/%m/%Y')}.\n"
        "Use as ferramentas para obter os dados. Nunca invente produtos, datas ou valores.\n"
        "Você só conhece os dados do cadastro (datas, valores, categorias, documentos guardados). "
        "Você NÃO sabe o que a garantia de um produto cobre; se perguntarem isso, diga que essa "
        "informação não está no cadastro.\n"
        "Para saber o que está na garantia (garantia vigente), chame listar_produtos com "
        "status=em_garantia. Para o que já venceu, status=vencida.\n"
        "Responda direto ao usuário, em português, de forma curta. Liste somente os produtos que "
        "a ferramenta devolveu, cada um com a data em que a garantia vence (dd/mm/aaaa). "
        "Se o total for 0, diga que não há nenhum. Responda só o que foi perguntado: não faça "
        "afirmações sobre produtos que a ferramenta não devolveu."
    )


def _sem_acento(texto: str) -> str:
    decomposto = unicodedata.normalize("NFD", texto.lower())
    return "".join(c for c in decomposto if unicodedata.category(c) != "Mn")


def _situacao(dias: int) -> str:
    # Vencido: sem número de dias. "há 8 dias" virou "8 dias após a compra" no modelo local.
    return f"faltam {dias} dias para vencer" if dias >= 0 else "já venceu"


def _resumo(produto: Produto, hoje: date) -> dict:
    return {
        "nome": produto.nome,
        "loja": produto.loja,
        "categoria": produto.categoria.value if produto.categoria else "sem categoria",
        "data_da_compra": produto.data_compra.strftime("%d/%m/%Y"),
        # Fim de toda a cobertura: prazo do fabricante + 90 dias da garantia legal (CDC)
        "garantia_ate": data_vencimento(produto).strftime("%d/%m/%Y"),
        # Texto em vez de número: com um negativo (-8) o modelo leu "8 dias restantes".
        "situacao": _situacao(dias_restantes(produto, hoje)),
        "status": status_garantia(produto, hoje),
    }


def criar_ferramentas(repositorio, hoje: date | None = None) -> list[Ferramenta]:
    """As ferramentas ligadas a um repositório. `hoje` existe para os testes fixarem a data."""
    hoje = hoje or date.today()

    def listar_produtos(status: str | None = None, categoria: str | None = None) -> dict:
        produtos = repositorio.listar()
        if status:
            if status not in FILTROS_STATUS:
                return {"erro": f"status inválido; use um de {sorted(FILTROS_STATUS)}"}
            produtos = [p for p in produtos if status_garantia(p, hoje) in FILTROS_STATUS[status]]
        if categoria:
            procurada = _sem_acento(categoria)
            valida = [c for c in Categoria if _sem_acento(c.value) == procurada]
            if not valida:
                return {"erro": f"categoria inválida; use uma de {[c.value for c in Categoria]}"}
            produtos = [p for p in produtos if p.categoria == valida[0]]
        return {"total": len(produtos), "produtos": [_resumo(p, hoje) for p in produtos]}

    def vencimentos_proximos(dias: int = 30) -> dict:
        limite = int(dias)
        vencendo = [p for p in repositorio.listar() if 0 <= dias_restantes(p, hoje) <= limite]
        vencendo.sort(key=lambda p: dias_restantes(p, hoje))
        return {"dentro_de_dias": limite, "total": len(vencendo),
                "produtos": [_resumo(p, hoje) for p in vencendo]}  # fmt: skip

    def detalhes_produto(nome: str) -> dict:
        achados = localizar_produto(nome, repositorio.listar())
        if not achados:
            return {"erro": f"nenhum produto parecido com '{nome}'"}
        if len(achados) > 1:
            return {"erro": "mais de um produto parecido", "opcoes": [p.nome for p in achados]}
        produto = achados[0]
        detalhes = _resumo(produto, hoje)
        detalhes["prazo_garantia_meses"] = produto.prazo_garantia_meses
        detalhes["valor"] = produto.valor
        detalhes["observacoes"] = produto.observacoes
        detalhes["documentos"] = [
            f"{d.tipo.value}: {d.nome_original}" for d in repositorio.listar_comprovantes(produto.id)
        ]
        return detalhes

    return [
        Ferramenta(
            nome="listar_produtos",
            funcao=listar_produtos,
            descricao=(
                "Lista os produtos cadastrados pelo usuário, com data de compra, data em que a "
                "garantia vence, dias restantes e status. Use para perguntas como 'quais produtos "
                "eu tenho', 'o que ainda está na garantia' ou 'o que já venceu'. Os filtros são "
                "opcionais; sem filtro devolve todos."
            ),
            parametros={
                "status": {
                    "type": "string",
                    "enum": list(FILTROS_STATUS),
                    "description": "em_garantia = ainda cobre (inclui os que vencem em breve); "
                    "vencendo_em_breve = faltam até 30 dias; vencida = já venceu",
                },
                "categoria": {
                    "type": "string",
                    "enum": [c.value for c in Categoria],
                    "description": "mostra só os produtos desta categoria",
                },
            },
        ),
        Ferramenta(
            nome="vencimentos_proximos",
            funcao=vencimentos_proximos,
            descricao=(
                "Produtos cuja garantia vence nos próximos dias, do que vence primeiro ao último. "
                "Use para 'o que vence logo', 'o que vence este mês'."
            ),
            parametros={
                "dias": {
                    "type": "integer",
                    "description": "janela em dias a partir de hoje; padrão 30",
                }
            },
        ),
        Ferramenta(
            nome="detalhes_produto",
            funcao=detalhes_produto,
            descricao=(
                "Detalhes de UM produto pelo nome: loja, valor, prazo da garantia em meses, data de "
                "vencimento e documentos guardados. Use para 'quando vence a garantia do meu X', "
                "'quanto paguei no X'."
            ),
            parametros={
                "nome": {"type": "string", "description": "nome ou parte do nome do produto"}
            },
            obrigatorios=("nome",),
        ),
    ]
