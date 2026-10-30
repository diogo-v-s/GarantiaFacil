from datetime import date

from garantiafacil.garantia import (
    GARANTIA_LEGAL_DIAS,
    data_vencimento,
    dias_restantes,
    fim_garantia_fabricante,
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


def test_fim_do_prazo_do_fabricante():
    assert fim_garantia_fabricante(produto(date(2026, 1, 10), 12)) == date(2027, 1, 10)


def test_garantia_legal_soma_90_dias_depois_da_do_fabricante():
    # CDC art. 50: a contratual é complementar à legal, então os prazos se somam
    assert GARANTIA_LEGAL_DIAS == 90
    assert data_vencimento(produto(date(2026, 1, 10), 12)) == date(2027, 4, 10)


def test_depois_do_fabricante_ainda_vale_a_garantia_legal():
    p = produto(date(2026, 1, 1), 12)  # fabricante até 01/01/2027, legal até 01/04/2027

    assert status_garantia(p, hoje=date(2027, 1, 2)) == "vigente"  # o fabricante já acabou
    assert dias_restantes(p, hoje=date(2027, 1, 2)) == 89


def test_dias_restantes_negativo_quando_vencida():
    p = produto(date(2025, 1, 1), 6)  # fabricante até 01/07/2025, tudo até 29/09/2025
    assert dias_restantes(p, hoje=date(2025, 10, 9)) == -10


def test_status_vigente():
    p = produto(date(2026, 1, 1), 12)
    assert status_garantia(p, hoje=date(2026, 2, 1)) == "vigente"


def test_status_vence_em_breve():
    p = produto(date(2026, 1, 1), 12)  # tudo até 01/04/2027
    assert status_garantia(p, hoje=date(2027, 3, 20)) == "vence_em_breve"


def test_status_vence_hoje_ainda_vale():
    p = produto(date(2026, 1, 1), 12)
    assert status_garantia(p, hoje=date(2027, 4, 1)) == "vence_em_breve"


def test_status_vencida():
    p = produto(date(2026, 1, 1), 12)
    assert status_garantia(p, hoje=date(2027, 4, 2)) == "vencida"


def test_contar_por_status():
    from garantiafacil.garantia import contar_por_status

    hoje = date(2026, 6, 1)

    def produto(compra: date, meses: int = 12) -> Produto:
        return Produto(nome="x", loja="y", data_compra=compra, prazo_garantia_meses=meses)

    produtos = [
        produto(date(2026, 1, 1)),  # tudo até 01/04/2027: vigente
        produto(date(2025, 3, 10)),  # fabricante até 10/03/2026, legal até 08/06/2026: faltam 7 dias
        produto(date(2025, 1, 1)),  # tudo até 01/04/2026: vencida
    ]

    assert contar_por_status(produtos, hoje) == {"vigente": 1, "vence_em_breve": 1, "vencida": 1}
