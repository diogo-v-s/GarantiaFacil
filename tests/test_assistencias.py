import pytest

from garantiafacil import assistencias
from garantiafacil.assistencias import (
    ErroDeBusca,
    Local,
    buscar_assistencias,
    distancia_km,
    localizar_cidade,
)
from garantiafacil.modelos import Categoria

CAMPINAS = Local("Campinas", -22.9056, -47.0596)

ELEMENTOS = [
    {"lat": -22.95, "lon": -47.06, "tags": {"name": "Eletro Longe", "shop": "electronics"}},
    {"lat": -22.906, "lon": -47.060, "tags": {
        "name": "Tecnicell", "craft": "electronics_repair", "phone": "+55 19 3253 3448",
        "addr:street": "Rua dos Bandeirantes", "addr:housenumber": "181"}},
    {"type": "way", "center": {"lat": -22.91, "lon": -47.07}, "tags": {
        "name": "Assistência Samsung", "brand": "Samsung", "contact:phone": "+55 19 0000 0000",
        "website": "https://exemplo.com.br"}},
    {"lat": -22.9, "lon": -47.05, "tags": {"shop": "electronics"}},  # sem nome: descartado
]  # fmt: skip


@pytest.fixture
def sem_rede(tmp_path, monkeypatch):
    """Cache em pasta temporária e nenhuma chamada de verdade; guarda o que foi pedido."""
    monkeypatch.setattr(assistencias, "PASTA_CACHE", tmp_path)
    pedidos = []

    def falso(url, dados, timeout):
        pedidos.append((url, dados))
        if url.startswith(assistencias.URL_NOMINATIM):
            return [{"display_name": "Campinas, SP", "lat": "-22.9", "lon": "-47.06"}]
        return {"elements": ELEMENTOS}

    monkeypatch.setattr(assistencias, "_pedir", falso)
    return pedidos


def test_distancia_de_um_ponto_a_ele_mesmo_e_zero():
    assert distancia_km(-22.9, -47.0, -22.9, -47.0) == 0


def test_distancia_campinas_sao_paulo_fica_perto_de_85_km():
    assert 80 < distancia_km(-22.9056, -47.0596, -23.5505, -46.6333) < 95


def test_ordena_pela_distancia_e_descarta_lugar_sem_nome(sem_rede):
    achadas = buscar_assistencias(CAMPINAS, Categoria.ELETRONICOS)
    assert [a.nome for a in achadas] == ["Tecnicell", "Assistência Samsung", "Eletro Longe"]


def test_marca_procurada_vem_primeiro_mesmo_mais_longe(sem_rede):
    achadas = buscar_assistencias(CAMPINAS, Categoria.ELETRONICOS, marca="samsung")
    assert achadas[0].nome == "Assistência Samsung"
    assert achadas[0].marca_confere
    assert not achadas[1].marca_confere


def test_so_repassa_o_que_o_mapa_tem_e_diz_quando_falta(sem_rede):
    por_nome = {a.nome: a for a in buscar_assistencias(CAMPINAS, Categoria.ELETRONICOS)}
    assert por_nome["Tecnicell"].endereco == "Rua dos Bandeirantes, 181"
    assert por_nome["Tecnicell"].telefone == "+55 19 3253 3448"
    assert por_nome["Assistência Samsung"].telefone == "+55 19 0000 0000"  # contact:phone também vale
    assert por_nome["Assistência Samsung"].endereco == "não informado"
    assert por_nome["Eletro Longe"].telefone == "não informado"


def test_segunda_busca_igual_vem_do_cache(sem_rede):
    buscar_assistencias(CAMPINAS, Categoria.ELETRONICOS)
    buscar_assistencias(CAMPINAS, Categoria.ELETRONICOS)
    assert len(sem_rede) == 1


def test_sem_categoria_ou_com_categoria_sem_regra_explica_e_nao_consulta(sem_rede):
    for categoria in (None, Categoria.VESTUARIO):
        with pytest.raises(ErroDeBusca):
            buscar_assistencias(CAMPINAS, categoria)
    assert sem_rede == []


def test_localiza_cidade_e_guarda_no_cache(sem_rede):
    local = localizar_cidade("Campinas")
    assert (local.latitude, local.longitude) == (-22.9, -47.06)
    localizar_cidade("  CAMPINAS ")  # mesmo texto sem acento e caixa: cache
    assert len(sem_rede) == 1


def test_cidade_vazia_ou_desconhecida_devolve_none(sem_rede, monkeypatch):
    assert localizar_cidade("   ") is None
    monkeypatch.setattr(assistencias, "_pedir", lambda *a: [])
    assert localizar_cidade("Xyzlândia") is None
