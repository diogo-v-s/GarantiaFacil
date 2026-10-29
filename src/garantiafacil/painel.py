"""Cálculos do painel: quanto foi gasto, em quê, e o que vence nos próximos meses.

São funções puras (recebem os produtos e a data de hoje), sem Streamlit nem banco, para dar para
testar. A tela só desenha o que sai daqui."""

from dataclasses import dataclass
from datetime import date, timedelta

from garantiafacil.garantia import (
    data_vencimento,
    dias_restantes,
    somar_meses,
    status_garantia,
)
from garantiafacil.modelos import Produto

SEM_CATEGORIA = "Sem categoria"
_MESES = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"]


@dataclass
class Resumo:
    produtos: int
    total_gasto: float  # soma só dos produtos com valor informado
    sem_valor: int  # produtos que ficaram fora da soma
    valor_sob_garantia: float  # valor dos produtos com garantia ainda valendo
    vencem_em_breve: int  # faltam até DIAS_ALERTA dias


def resumo(produtos: list[Produto], hoje: date) -> Resumo:
    com_valor = [p for p in produtos if p.valor]
    return Resumo(
        produtos=len(produtos),
        total_gasto=sum(p.valor for p in com_valor),
        sem_valor=len(produtos) - len(com_valor),
        valor_sob_garantia=sum(p.valor for p in com_valor if status_garantia(p, hoje) != "vencida"),
        vencem_em_breve=sum(1 for p in produtos if status_garantia(p, hoje) == "vence_em_breve"),
    )


def gasto_por_categoria(produtos: list[Produto]) -> list[tuple[str, float]]:
    """(categoria, total gasto), do maior para o menor. Produto sem valor não entra; produto sem
    categoria entra como 'Sem categoria'."""
    totais: dict[str, float] = {}
    for produto in produtos:
        if not produto.valor:
            continue
        nome = produto.categoria.value if produto.categoria else SEM_CATEGORIA
        totais[nome] = totais.get(nome, 0.0) + produto.valor
    return sorted(totais.items(), key=lambda par: par[1], reverse=True)


def rotulo_mes(mes: date) -> str:
    return f"{_MESES[mes.month - 1]}/{mes.year % 100:02d}"


def vencimentos_por_mes(
    produtos: list[Produto], hoje: date, meses: int = 12
) -> list[tuple[date, int]]:
    """Quantas garantias vencem em cada um dos próximos `meses` meses, a começar pelo atual
    (meses sem vencimento aparecem com 0, para a linha do tempo não ter buracos). Garantia que
    já venceu não entra. Cada mês é o dia 1."""
    primeiro = hoje.replace(day=1)
    janela = [somar_meses(primeiro, i) for i in range(meses)]
    contagem = {mes: 0 for mes in janela}
    for produto in produtos:
        vencimento = data_vencimento(produto)
        if vencimento < hoje:
            continue
        mes = vencimento.replace(day=1)
        if mes in contagem:
            contagem[mes] += 1
    return list(contagem.items())


def proximos_vencimentos(
    produtos: list[Produto], hoje: date, dias: int = 90
) -> list[tuple[Produto, date, int]]:
    """(produto, data de vencimento, dias que faltam) das garantias que vencem nos próximos
    `dias` dias, da mais próxima para a mais distante. Hoje conta."""
    limite = hoje + timedelta(days=dias)
    achados = [
        (p, data_vencimento(p), dias_restantes(p, hoje))
        for p in produtos
        if hoje <= data_vencimento(p) <= limite
    ]
    return sorted(achados, key=lambda trio: trio[1])


def formatar_real(valor: float) -> str:
    """1234.5 -> 'R$ 1.234,50' (separadores do Brasil, sem depender do idioma do sistema)."""
    texto = f"{valor:,.2f}".replace(",", "#").replace(".", ",").replace("#", ".")
    return f"R$ {texto}"

