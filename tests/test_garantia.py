from datetime import date

from garantiafacil.garantia import (
    data_vencimento,
    dias_restantes,
    somar_meses,
    status_garantia,
)
from garantiafacil.modelos import Produto


def produto(data_compra: date, meses: int) -> Produto:
    return Produto(nome="Geladeira", loja="Loja X", data_compra=data_compra, prazo_garantia_meses=meses)


def test_somar_meses_simples():
    assert somar_meses(date(2026, 1, 10), 3) == date(2026, 4, 10)


def test_somar_meses_virada_de_ano():
    assert somar_meses(date(2026, 11, 15), 3) == date(2027, 2, 15)


def test_somar_meses_dia_inexistente_usa_ultimo_dia():
    assert somar_meses(date(2026, 1, 31), 1) == date(2026, 2, 28)
    assert somar_meses(date(2024, 1, 31), 1) == date(2024, 2, 29)  # ano bissexto


def test_data_vencimento():
    assert data_vencimento(produto(date(2026, 1, 10), 12)) == date(2027, 1, 10)


def test_dias_restantes_negativo_quando_vencida():
    p = produto(date(2025, 1, 1), 6)  # vence 2025-07-01
    assert dias_restantes(p, hoje=date(2025, 7, 11)) == -10


def test_status_vigente():
    p = produto(date(2026, 1, 1), 12)
    assert status_garantia(p, hoje=date(2026, 2, 1)) == "vigente"


def test_status_vence_em_breve():
    p = produto(date(2026, 1, 1), 12)  # vence 2027-01-01
    assert status_garantia(p, hoje=date(2026, 12, 20)) == "vence_em_breve"


def test_status_vence_hoje_ainda_vale():
    p = produto(date(2026, 1, 1), 12)
    assert status_garantia(p, hoje=date(2027, 1, 1)) == "vence_em_breve"


def test_status_vencida():
    p = produto(date(2026, 1, 1), 12)
    assert status_garantia(p, hoje=date(2027, 1, 2)) == "vencida"


def test_contar_por_status():
    from garantiafacil.garantia import contar_por_status

    hoje = date(2026, 6, 1)

    def produto(compra: date, meses: int = 12) -> Produto:
        return Produto(nome="x", loja="y", data_compra=compra, prazo_garantia_meses=meses)

    produtos = [
        produto(date(2026, 1, 1)),  # vence em 01/01/2027: vigente
        produto(date(2025, 6, 20)),  # vence em 20/06/2026: faltam 19 dias
        produto(date(2025, 1, 1)),  # venceu em 01/01/2026
    ]

    assert contar_por_status(produtos, hoje) == {"vigente": 1, "vence_em_breve": 1, "vencida": 1}
