from datetime import date

import pytest

from garantiafacil.avisos import (
    DIAS_PADRAO,
    avisos_de_vencimento,
    dias_para_texto,
    normalizar_dias,
    quando,
    texto_para_dias,
)
from garantiafacil.modelos import Produto
from tests.ajuda import compra_para_vencer_em

HOJE = date(2026, 10, 28)


def produto(nome, dias_para_vencer: int) -> Produto:
    """Produto que vence daqui a `dias_para_vencer` dias (compra em meses cheios de 12)."""
    from datetime import timedelta

    return Produto(
        nome=nome, loja="Loja", data_compra=compra_para_vencer_em(HOJE + timedelta(days=dias_para_vencer)),
        prazo_garantia_meses=12,
    )  # fmt: skip


def test_normalizar_tira_repeticao_e_valores_fora_do_limite():
    assert normalizar_dias([7, 30, 7, 0, -5, 400, 15]) == (30, 15, 7)
    assert normalizar_dias([]) == ()


def test_texto_do_banco_vai_e_volta():
    assert dias_para_texto((7, 30)) == "30,7"
    assert texto_para_dias("30,7") == (30, 7)
    assert texto_para_dias("") == ()  # escolheu não receber avisos
    assert texto_para_dias(None) == DIAS_PADRAO  # nunca escolheu
    assert texto_para_dias("30,x,,7") == (30, 7)  # lixo é ignorado


def test_avisos_dentro_da_maior_antecedencia_em_ordem():
    produtos = [produto("Longe", 200), produto("TV", 20), produto("Furadeira", 3), produto("Vencida", -4)]

    avisos = avisos_de_vencimento(produtos, HOJE, (30, 7))

    assert [(a.produto.nome, a.dias) for a in avisos] == [("Furadeira", 3), ("TV", 20)]


def test_urgente_so_dentro_da_menor_antecedencia():
    avisos = avisos_de_vencimento([produto("TV", 20), produto("Furadeira", 7)], HOJE, (30, 7))

    assert [(a.produto.nome, a.urgente) for a in avisos] == [("Furadeira", True), ("TV", False)]


def test_com_uma_so_antecedencia_nada_e_urgente():
    avisos = avisos_de_vencimento([produto("TV", 2)], HOJE, (30,))

    assert [a.urgente for a in avisos] == [False]


def test_limites_da_janela_hoje_entra_e_o_ultimo_dia_tambem():
    produtos = [produto("Hoje", 0), produto("No limite", 30), produto("Passou", 31)]

    nomes = [a.produto.nome for a in avisos_de_vencimento(produtos, HOJE, (30, 7))]

    assert nomes == ["Hoje", "No limite"]


def test_sem_antecedencia_escolhida_nao_avisa():
    assert avisos_de_vencimento([produto("TV", 1)], HOJE, ()) == []


@pytest.mark.parametrize("dias, texto", [(0, "vence hoje"), (1, "vence amanhã"), (15, "faltam 15 dias")])
def test_frase_do_prazo(dias, texto):
    assert quando(dias) == texto
