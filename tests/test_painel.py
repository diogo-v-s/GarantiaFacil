from datetime import date

from garantiafacil.modelos import Categoria, Produto
from garantiafacil.painel import (
    SEM_CATEGORIA,
    formatar_real,
    gasto_por_categoria,
    proximos_vencimentos,
    resumo,
    rotulo_mes,
    vencimentos_por_mes,
)

HOJE = date(2026, 10, 28)


def produto(nome, compra, meses=12, valor=None, categoria=None) -> Produto:
    return Produto(
        nome=nome, loja="Loja", data_compra=compra, prazo_garantia_meses=meses,
        valor=valor, categoria=categoria,
    )  # fmt: skip


def catalogo():
    return [
        produto("TV", date(2026, 3, 1), valor=3000.0, categoria=Categoria.ELETRONICOS),  # vence 01/03/2027
        produto("Celular", date(2025, 11, 20), valor=2000.0, categoria=Categoria.ELETRONICOS),  # vence 20/11/2026
        produto("Furadeira", date(2025, 10, 28), valor=500.0, categoria=Categoria.FERRAMENTAS),  # vence hoje
        produto("Geladeira", date(2025, 1, 10), valor=4000.0, categoria=Categoria.ELETRODOMESTICOS),  # vencida
        produto("Cadeira", date(2026, 9, 1), valor=None),  # sem valor e sem categoria; vence 01/09/2027
    ]  # fmt: skip


def test_resumo():
    r = resumo(catalogo(), HOJE)

    assert r.produtos == 5
    assert r.total_gasto == 9500.0
    assert r.sem_valor == 1
    assert r.valor_sob_garantia == 5500.0  # TV + celular + furadeira; a geladeira já venceu
    assert r.vencem_em_breve == 2  # furadeira (hoje) e celular (23 dias)


def test_resumo_sem_produtos():
    r = resumo([], HOJE)

    assert (r.produtos, r.total_gasto, r.sem_valor, r.valor_sob_garantia) == (0, 0, 0, 0)


def test_gasto_por_categoria_ordenado_e_sem_o_que_nao_tem_valor():
    assert gasto_por_categoria(catalogo()) == [
        ("Eletrônicos", 5000.0),
        ("Eletrodomésticos", 4000.0),
        ("Ferramentas", 500.0),
    ]


def test_gasto_sem_categoria_aparece_como_tal():
    produtos = [produto("Coisa", HOJE, valor=10.0), produto("TV", HOJE, valor=5.0, categoria=Categoria.ELETRONICOS)]

    assert gasto_por_categoria(produtos) == [(SEM_CATEGORIA, 10.0), ("Eletrônicos", 5.0)]


def test_vencimentos_por_mes_tem_12_meses_sem_buracos():
    meses = vencimentos_por_mes(catalogo(), HOJE)

    assert len(meses) == 12
    assert meses[0][0] == date(2026, 10, 1) and meses[-1][0] == date(2027, 9, 1)  # cruza o ano
    contagem = {mes: n for mes, n in meses}
    assert contagem[date(2026, 10, 1)] == 1  # furadeira, hoje
    assert contagem[date(2026, 11, 1)] == 1  # celular
    assert contagem[date(2027, 3, 1)] == 1  # TV
    assert contagem[date(2027, 9, 1)] == 1  # cadeira (último mês da janela)
    assert contagem[date(2027, 1, 1)] == 0  # mês sem vencimento continua na lista
    assert sum(contagem.values()) == 4  # a geladeira vencida não entra


def test_vencimento_depois_da_janela_nao_entra():
    longe = produto("Sofá", HOJE, meses=60)

    assert sum(n for _, n in vencimentos_por_mes([longe], HOJE)) == 0


def test_proximos_vencimentos_ordenados_com_hoje_incluido():
    achados = proximos_vencimentos(catalogo(), HOJE, dias=90)

    assert [(p.nome, dias) for p, _, dias in achados] == [("Furadeira", 0), ("Celular", 23)]
    assert achados[1][1] == date(2026, 11, 20)


def test_proximos_vencimentos_respeita_a_janela():
    assert [p.nome for p, _, _ in proximos_vencimentos(catalogo(), HOJE, dias=10)] == ["Furadeira"]
    assert proximos_vencimentos([], HOJE) == []


def test_formatacao():
    assert formatar_real(1234.5) == "R$ 1.234,50"
    assert formatar_real(0) == "R$ 0,00"
    assert formatar_real(1234567.891) == "R$ 1.234.567,89"
    assert rotulo_mes(date(2026, 11, 1)) == "nov/26"
    assert rotulo_mes(date(2027, 1, 1)) == "jan/27"
