from datetime import date

from garantiafacil.lembretes import Lembrete, Lembretes
from garantiafacil.modelos import Produto
from garantiafacil.notificacoes import montar_notificacoes
from tests.ajuda import banco_com_usuario, compra_para_vencer_em

HOJE = date(2026, 6, 1)


def produto(nome: str, dias_para_vencer: int, id: int) -> Produto:
    vencimento = date.fromordinal(HOJE.toordinal() + dias_para_vencer)
    return Produto(nome, "Loja", compra_para_vencer_em(vencimento), 12, id=id)


def test_garantia_perto_do_fim_vira_notificacao_de_vencimento():
    notificacoes = montar_notificacoes([produto("Moto G60", 30, 1)], [], HOJE, (30, 7))

    assert [n.texto for n in notificacoes] == ["A garantia de Moto G60 vence em 30 dias."]
    assert notificacoes[0].tipo == "vencimento"


def test_garantia_longe_do_fim_nao_aparece():
    assert montar_notificacoes([produto("TV", 200, 1)], [], HOJE, (30, 7)) == []


def test_lembrete_so_aparece_quando_a_data_chega():
    tv = produto("Smart TV", 200, 7)
    lembretes = [
        Lembrete(1, 7, date(2026, 6, 1), "levar na assistência"),
        Lembrete(2, 7, date(2026, 6, 2), "ainda no futuro"),
    ]

    notificacoes = montar_notificacoes([tv], lembretes, HOJE, (30, 7))

    assert [n.texto for n in notificacoes] == [
        "Lembrete de Smart TV: levar na assistência (marcado para hoje)."
    ]
    assert notificacoes[0].lembrete_id == 1


def test_lembrete_atrasado_continua_aparecendo_e_vem_antes_dos_vencimentos():
    produtos = [produto("Moto G60", 10, 1), produto("Smart TV", 200, 2)]
    lembretes = [Lembrete(5, 2, date(2026, 5, 28), "levar na assistência")]

    tipos = [n.tipo for n in montar_notificacoes(produtos, lembretes, HOJE, (30, 7))]

    assert tipos == ["lembrete", "vencimento"]


def test_lembrete_de_produto_que_nao_existe_mais_e_ignorado():
    lembretes = [Lembrete(1, 99, date(2026, 5, 1), "x")]

    assert montar_notificacoes([], lembretes, HOJE, (30, 7)) == []


# ---------- guardar e ler lembretes ----------


def test_lembretes_guarda_lista_e_conclui(tmp_path):
    from garantiafacil.repositorio import Repositorio
    from tests.test_conversa import embedding_falso, novo

    conexao, usuario_id = banco_com_usuario()
    repo = Repositorio(conexao, usuario_id, tmp_path, gerar_embedding=embedding_falso, nome_modelo=lambda: "f")
    tv = repo.adicionar(novo("Smart TV"))
    lembretes = Lembretes(conexao, usuario_id)

    tarde = lembretes.adicionar(tv.id, date(2026, 6, 10), "  ligar para a assistência ")
    cedo = lembretes.adicionar(tv.id, date(2026, 6, 5), "levar a TV")

    assert [l.texto for l in lembretes.pendentes()] == ["levar a TV", "ligar para a assistência"]
    lembretes.concluir(cedo.id)
    assert [l.id for l in lembretes.pendentes()] == [tarde.id]


def test_lembrete_some_junto_com_o_produto(tmp_path):
    from garantiafacil.repositorio import Repositorio
    from tests.test_conversa import embedding_falso, novo

    conexao, usuario_id = banco_com_usuario()
    repo = Repositorio(conexao, usuario_id, tmp_path, gerar_embedding=embedding_falso, nome_modelo=lambda: "f")
    tv = repo.adicionar(novo("Smart TV"))
    lembretes = Lembretes(conexao, usuario_id)
    lembretes.adicionar(tv.id, date(2026, 6, 5), "levar a TV")

    repo.excluir(tv.id)

    assert lembretes.pendentes() == []


def test_nao_cria_lembrete_para_produto_de_outro_usuario_nem_sem_texto(tmp_path):
    import pytest

    from garantiafacil.repositorio import Repositorio
    from tests.test_conversa import embedding_falso, novo

    conexao, usuario_id = banco_com_usuario()
    repo = Repositorio(conexao, usuario_id, tmp_path, gerar_embedding=embedding_falso, nome_modelo=lambda: "f")
    tv = repo.adicionar(novo("Smart TV"))

    with pytest.raises(ValueError):
        Lembretes(conexao, usuario_id + 1).adicionar(tv.id, date(2026, 6, 5), "x")  # outro usuário
    with pytest.raises(ValueError):
        Lembretes(conexao, usuario_id).adicionar(tv.id, date(2026, 6, 5), "   ")


# ---------- avisos já lidos ----------


def test_aviso_lido_some_da_lista():
    moto = produto("Moto G60", 30, 1)
    [aviso] = montar_notificacoes([moto], [], HOJE, (30, 7))

    depois = montar_notificacoes([moto], [], HOJE, (30, 7), lidas={aviso.chave})

    assert depois == []


def test_aviso_lido_volta_ao_entrar_na_faixa_mais_urgente():
    antes = produto("Moto G60", 20, 1)  # 20 dias: faixa de 30
    [aviso_de_30] = montar_notificacoes([antes], [], HOJE, (30, 7))
    depois = produto("Moto G60", 5, 1)  # mesma garantia vista 15 dias depois: 5 dias, faixa de 7

    notificacoes = montar_notificacoes([depois], [], HOJE, (30, 7), lidas={aviso_de_30.chave})

    assert [n.texto for n in notificacoes] == ["A garantia de Moto G60 vence em 5 dias."]
    assert notificacoes[0].urgente


def test_aviso_lido_volta_se_a_data_de_vencimento_mudar():
    [aviso] = montar_notificacoes([produto("Moto G60", 20, 1)], [], HOJE, (30, 7))
    prazo_maior = produto("Moto G60", 25, 1)  # outra data de vencimento, mesma faixa

    assert montar_notificacoes([prazo_maior], [], HOJE, (30, 7), lidas={aviso.chave}) != []


def test_notificacoes_lidas_guarda_e_ignora_produto_de_outro_usuario(tmp_path):
    from garantiafacil.lembretes import NotificacoesLidas
    from garantiafacil.repositorio import Repositorio
    from tests.test_conversa import embedding_falso, novo

    conexao, usuario_id = banco_com_usuario()
    repo = Repositorio(conexao, usuario_id, tmp_path, gerar_embedding=embedding_falso, nome_modelo=lambda: "f")
    tv = repo.adicionar(novo("Smart TV"))
    lidas = NotificacoesLidas(conexao, usuario_id)

    lidas.marcar(tv.id, "vencimento:1:2026-07-01:30")
    lidas.marcar(tv.id, "vencimento:1:2026-07-01:30")  # repetir não duplica nem dá erro
    NotificacoesLidas(conexao, usuario_id + 1).marcar(tv.id, "vencimento:de-outro")  # produto alheio

    assert lidas.chaves() == {"vencimento:1:2026-07-01:30"}
    assert NotificacoesLidas(conexao, usuario_id + 1).chaves() == set()
