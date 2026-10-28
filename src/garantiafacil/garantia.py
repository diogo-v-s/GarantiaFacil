"""Regras de negócio da garantia: vencimento, dias restantes e status."""

import calendar
from datetime import date, timedelta

from garantiafacil.modelos import Produto

DIAS_ALERTA = 30  # "vence em breve" = faltam até 30 dias


def somar_meses(data: date, meses: int) -> date:
    """Soma meses a uma data. Se o dia não existir no mês de destino, usa o último dia
    (31/jan + 1 mês = 28 ou 29/fev)."""
    indice = data.month - 1 + meses
    ano = data.year + indice // 12
    mes = indice % 12 + 1
    ultimo_dia = calendar.monthrange(ano, mes)[1]
    return date(ano, mes, min(data.day, ultimo_dia))


def data_vencimento(produto: Produto) -> date:
    return somar_meses(produto.data_compra, produto.prazo_garantia_meses)


def dias_restantes(produto: Produto, hoje: date | None = None) -> int:
    """Negativo quando a garantia já venceu."""
    hoje = hoje or date.today()
    return (data_vencimento(produto) - hoje).days


def status_garantia(produto: Produto, hoje: date | None = None) -> str:
    """Retorna 'vencida', 'vence_em_breve' ou 'vigente'."""
    dias = dias_restantes(produto, hoje)
    if dias < 0:
        return "vencida"
    if dias <= DIAS_ALERTA:
        return "vence_em_breve"
    return "vigente"


def contar_por_status(produtos: list[Produto], hoje: date | None = None) -> dict[str, int]:
    """Quantos produtos há em cada status, para os cartões de resumo da tela."""
    contagem = {"vigente": 0, "vence_em_breve": 0, "vencida": 0}
    for produto in produtos:
        contagem[status_garantia(produto, hoje)] += 1
    return contagem


def vence_ate(produto: Produto, limite: date) -> bool:
    return date.today() <= data_vencimento(produto) <= limite


def proximos_vencimentos(produtos: list[Produto], dias: int = DIAS_ALERTA) -> list[Produto]:
    """Produtos que vencem nos próximos `dias` dias, do mais próximo ao mais distante."""
    limite = date.today() + timedelta(days=dias)
    return sorted(
        (p for p in produtos if vence_ate(p, limite)),
        key=data_vencimento,
    )
