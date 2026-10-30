"""Chat sem classificador: o agente decide as ferramentas. O LLM é um dublê com passos roteirizados."""

from datetime import date

import pytest

from garantiafacil.agente import Chamada, PassoLlm
from garantiafacil.conversa_agente import ConversaAgente
from garantiafacil.modelos import Produto
from garantiafacil.rag import BaseConhecimento
from garantiafacil.repositorio import Repositorio
from tests.ajuda import banco_com_usuario
from tests.test_conversa import embedding_falso, novo


class LlmRoteirizado:
    def __init__(self, *passos):
        self.passos = list(passos)
        self.recebidas = []
        self.sistemas = []

    def passo(self, mensagens, ferramentas, sistema=None):
        self.recebidas.append(list(mensagens))
        self.sistemas.append(sistema)
        return self.passos.pop(0)


def chama(ferramenta, /, **argumentos):
    return PassoLlm("", [Chamada("id1", ferramenta, argumentos)])


def texto(frase):
    return PassoLlm(frase, [])


@pytest.fixture
def ambiente(tmp_path):
    repo = Repositorio(
        *banco_com_usuario(), tmp_path, gerar_embedding=embedding_falso, nome_modelo=lambda: "f"
    )
    moto = repo.adicionar(novo("MOTO G60 128GB - AZUL"))
    repo.adicionar(novo("Geladeira Brastemp 375L"))
    base = BaseConhecimento(repo.conexao, embedding_falso, lambda: "f")
    base.indexar("cdc.txt", [(1, "O prazo para reclamar de defeito é de 90 dias.")])
    base.indexar("termo-moto.txt", [(1, "A tela quebrada não é coberta pela garantia.")], moto.id)
    return repo, base


def conversa(ambiente, *passos):
    repo, base = ambiente
    llm = LlmRoteirizado(*passos)
    return ConversaAgente(repo, base, llm, hoje=date(2026, 6, 1)), llm


def test_pergunta_da_lei_busca_so_o_cdc(ambiente):
    c, _ = conversa(ambiente, chama("consultar_documentos", pergunta="prazo para reclamar"), texto("90 dias."))

    resposta = c.responder("Quanto tempo tenho para reclamar?")

    assert resposta.rota == "cdc"
    assert [t.fonte for t in resposta.trechos] == ["cdc.txt"]


def test_pergunta_de_um_produto_com_termo_usa_o_termo_dele_e_vira_o_assunto(ambiente):
    c, _ = conversa(
        ambiente, chama("consultar_documentos", pergunta="tela quebrada", produto="moto"), texto("Não cobre.")
    )

    resposta = c.responder("A garantia da moto cobre tela quebrada?")

    assert resposta.rota == "documentos_produto"
    assert "termo-moto.txt" in [t.fonte for t in resposta.trechos]
    assert c.produto_atual.nome.startswith("MOTO")


def test_produto_sem_termo_manda_avisar_e_usa_a_garantia_legal(ambiente):
    c, llm = conversa(
        ambiente, chama("consultar_documentos", pergunta="o que cobre", produto="geladeira"), texto("ok")
    )

    resposta = c.responder("O que a garantia da geladeira cobre?")

    assert resposta.rota == "sem_termo"
    resultado = resposta.consultas[0].resultado
    assert "Não há termo de garantia cadastrado para Geladeira Brastemp 375L" in resultado


def test_produto_que_nao_existe_devolve_erro_com_os_nomes_para_o_agente_perguntar(ambiente):
    c, _ = conversa(
        ambiente,
        chama("consultar_documentos", pergunta="cobertura", produto="celular"),
        texto("De qual produto você está falando?\n\n1. MOTO G60 128GB - AZUL"),
    )

    resposta = c.responder("o que a garantia do celular cobria?")

    assert "nenhum produto parecido" in resposta.consultas[0].resultado
    assert resposta.rota == "esclarecimento"


def test_pergunta_do_cadastro_usa_as_ferramentas_do_cadastro(ambiente):
    c, _ = conversa(ambiente, chama("listar_produtos"), texto("Você tem 2 produtos."))

    assert c.responder("quais produtos eu tenho?").rota == "agente"


def test_a_segunda_pergunta_recebe_o_historico_e_o_produto_em_discussao(ambiente):
    c, llm = conversa(
        ambiente,
        chama("consultar_documentos", pergunta="tela", produto="moto"),
        texto("Não cobre."),
        texto("O prazo é de 12 meses."),
    )
    c.responder("A garantia da moto cobre tela quebrada?")

    c.responder("e o prazo?")

    ultima = llm.recebidas[-1]
    assert [m["papel"] for m in ultima] == ["usuario", "assistente", "usuario"]
    assert ultima[-1]["texto"] == "e o prazo?"
    assert "Produto em discussão: 'MOTO G60 128GB - AZUL'" in llm.sistemas[-1]


def test_reiniciar_esquece_o_assunto_e_o_historico(ambiente):
    c, _ = conversa(ambiente, chama("consultar_documentos", pergunta="x", produto="moto"), texto("ok"))
    c.responder("A garantia da moto cobre algo?")

    c.reiniciar()

    assert c.produto_atual is None and c.historico == []


# ---------- escolha do modo (CHAT_MODO) ----------


@pytest.mark.parametrize(
    "chat_modo, provedor, esperado",
    [
        ("", "claude", "agente"),  # padrão com o Claude
        ("", "ollama", "classificador"),  # padrão com o Ollama (agente ainda não medido nele)
        ("classificador", "claude", "classificador"),  # a chave manda
        ("AGENTE", "ollama", "agente"),  # sem diferença de maiúsculas
        ("qualquer coisa", "claude", "agente"),  # valor inválido cai no padrão
    ],
)
def test_modo_do_chat(monkeypatch, chat_modo, provedor, esperado):
    from garantiafacil.conversa_agente import modo_do_chat

    monkeypatch.setenv("CHAT_MODO", chat_modo)
    monkeypatch.setenv("LLM_PROVIDER", provedor)

    assert modo_do_chat() == esperado


def test_criar_conversa_devolve_a_classe_do_modo(ambiente, monkeypatch):
    from garantiafacil.conversa import Conversa
    from garantiafacil.conversa_agente import criar_conversa

    repo, base = ambiente
    monkeypatch.setenv("CHAT_MODO", "classificador")
    assert type(criar_conversa(repo, base, None)) is Conversa
    monkeypatch.setenv("CHAT_MODO", "agente")
    assert type(criar_conversa(repo, base, None)) is ConversaAgente


# ---------- cadastro com confirmação: o agente só propõe, quem grava é o botão ----------

PROPOSTA = dict(
    nome="Liquidificador Philips", loja="Casas Bahia", data_compra="10/05/2026",
    prazo_garantia_meses=12, valor=250, categoria="Eletrodomésticos",
)  # fmt: skip


def test_propor_cadastro_nao_grava_nada_ate_confirmar(ambiente):
    repo, _ = ambiente
    antes = len(repo.listar())
    c, _ = conversa(ambiente, chama("propor_cadastro", **PROPOSTA), texto("Pronto para confirmar."))

    resposta = c.responder("Cadastra um liquidificador Philips, Casas Bahia, 10/05/2026, 12 meses, R$ 250")

    assert resposta.rota == "agente"
    assert len(repo.listar()) == antes
    assert c.proposta.nome == "Liquidificador Philips"
    assert c.proposta.data_compra == date(2026, 5, 10)

    salvo = c.confirmar_proposta()

    assert len(repo.listar()) == antes + 1
    assert salvo.id is not None and salvo.valor == 250
    assert c.proposta is None and c.produto_atual.nome == "Liquidificador Philips"


def test_cancelar_descarta_a_proposta(ambiente):
    repo, _ = ambiente
    antes = len(repo.listar())
    c, _ = conversa(ambiente, chama("propor_cadastro", **PROPOSTA), texto("Pronto."))
    c.responder("Cadastra o liquidificador")

    c.cancelar_proposta()

    assert c.proposta is None
    assert len(repo.listar()) == antes


def test_agente_fica_sabendo_da_confirmacao_na_proxima_pergunta(ambiente):
    c, llm = conversa(ambiente, chama("propor_cadastro", **PROPOSTA), texto("Pronto."), texto("Sim, cadastrado."))
    c.responder("Cadastra o liquidificador")
    c.confirmar_proposta()

    c.responder("Ficou cadastrado?")

    textos = [m["texto"] for m in llm.recebidas[-1]]
    assert "Cadastrei 'Liquidificador Philips'." in textos


@pytest.mark.parametrize(
    "mudanca",
    [
        {"data_compra": "31/02/2026"},  # data que não existe
        {"data_compra": "10/05/2027"},  # no futuro (hoje é 01/06/2026 nos testes)
        {"prazo_garantia_meses": 0},
        {"categoria": "Joias"},
    ],
)
def test_propostas_invalidas_viram_erro_e_nao_criam_proposta(ambiente, mudanca):
    c, _ = conversa(ambiente, chama("propor_cadastro", **{**PROPOSTA, **mudanca}), texto("Preciso corrigir."))

    resposta = c.responder("Cadastra o liquidificador")

    assert c.proposta is None
    assert "erro" in resposta.consultas[0].resultado


def test_nao_propoe_produto_repetido(ambiente):
    # a moto do ambiente foi comprada em 01/01/2026
    c, _ = conversa(
        ambiente,
        chama("propor_cadastro", **{**PROPOSTA, "nome": "moto g60 128gb - azul", "data_compra": "01/01/2026"}),
        texto("Já existe."),
    )

    resposta = c.responder("Cadastra a moto")

    assert c.proposta is None
    assert "já existe" in resposta.consultas[0].resultado


# ---------- excluir e alterar com confirmação ----------


def nomes(repo):
    return [p.nome for p in repo.listar()]


def test_excluir_so_acontece_ao_confirmar(ambiente):
    repo, _ = ambiente
    c, _ = conversa(ambiente, chama("propor_exclusao", produto="geladeira"), texto("Confirme a exclusão."))

    resposta = c.responder("Exclui a geladeira")

    assert resposta.rota == "agente"
    assert "Geladeira Brastemp 375L" in nomes(repo)  # nada mudou ainda
    assert "Geladeira Brastemp 375L" in c.acao.descricao

    assert c.confirmar_acao() == "Excluí 'Geladeira Brastemp 375L'."
    assert "Geladeira Brastemp 375L" not in nomes(repo)
    assert c.acao is None


def test_cancelar_a_exclusao_nao_apaga_nada(ambiente):
    repo, _ = ambiente
    c, _ = conversa(ambiente, chama("propor_exclusao", produto="geladeira"), texto("Confirme."))
    c.responder("Exclui a geladeira")

    c.cancelar_acao()

    assert c.acao is None
    assert "Geladeira Brastemp 375L" in nomes(repo)


def test_alterar_categoria_e_prazo_so_ao_confirmar(ambiente):
    repo, _ = ambiente
    c, _ = conversa(
        ambiente,
        chama("propor_alteracao", produto="moto", categoria="Eletrônicos", prazo_garantia_meses=24),
        texto("Confirme a alteração."),
    )

    c.responder("Muda a moto para eletrônicos com 24 meses de garantia")

    moto = next(p for p in repo.listar() if p.nome.startswith("MOTO"))
    assert moto.categoria is None and moto.prazo_garantia_meses == 12  # ainda como antes
    assert "sem categoria para Eletrônicos" in c.acao.descricao
    assert "de 12 para 24 meses" in c.acao.descricao

    c.confirmar_acao()

    moto = next(p for p in repo.listar() if p.nome.startswith("MOTO"))
    assert moto.categoria.value == "Eletrônicos" and moto.prazo_garantia_meses == 24


@pytest.mark.parametrize(
    "ferramenta, argumentos",
    [
        ("propor_exclusao", {"produto": "fone de ouvido"}),  # não existe
        ("propor_alteracao", {"produto": "moto"}),  # sem dizer o que mudar
        ("propor_alteracao", {"produto": "moto", "categoria": "Joias"}),
        ("propor_alteracao", {"produto": "moto", "prazo_garantia_meses": 0}),
    ],
)
def test_pedidos_invalidos_viram_erro_e_nao_criam_acao(ambiente, ferramenta, argumentos):
    c, _ = conversa(ambiente, chama(ferramenta, **argumentos), texto("Não consegui."))

    resposta = c.responder("faz isso")

    assert c.acao is None
    assert "erro" in resposta.consultas[0].resultado


def test_so_uma_coisa_pendente_por_vez(ambiente):
    c, _ = conversa(
        ambiente,
        chama("propor_cadastro", **PROPOSTA), texto("Confirme o cadastro."),
        chama("propor_exclusao", produto="geladeira"), texto("Confirme a exclusão."),
    )  # fmt: skip
    c.responder("Cadastra o liquidificador")
    assert c.proposta is not None

    c.responder("Na verdade, exclui a geladeira")

    assert c.proposta is None and c.acao is not None


# ---------- lembretes programados ----------


def pendentes(repo):
    from garantiafacil.lembretes import Lembretes

    return Lembretes(repo.conexao, repo.usuario_id).pendentes()


def test_lembrete_so_e_criado_ao_confirmar(ambiente):
    repo, _ = ambiente
    c, _ = conversa(
        ambiente,
        chama("propor_lembrete", produto="moto", data="05/06/2026", texto="levar na assistência"),
        texto("Confirme o lembrete."),
    )

    resposta = c.responder("Me lembra de levar a moto na assistência dia 05/06")

    assert resposta.rota == "agente"
    assert pendentes(repo) == []  # só propôs
    assert "05/06/2026" in c.acao.descricao and "MOTO G60" in c.acao.descricao

    c.confirmar_acao()

    [lembrete] = pendentes(repo)
    assert lembrete.texto == "levar na assistência" and lembrete.data == date(2026, 6, 5)


def test_cancelar_nao_cria_lembrete(ambiente):
    repo, _ = ambiente
    c, _ = conversa(
        ambiente,
        chama("propor_lembrete", produto="moto", data="05/06/2026", texto="levar"),
        texto("Confirme."),
    )
    c.responder("Me lembra de levar a moto dia 05/06")

    c.cancelar_acao()

    assert pendentes(repo) == []


@pytest.mark.parametrize(
    "argumentos",
    [
        {"produto": "moto", "data": "31/02/2026", "texto": "x"},  # data que não existe
        {"produto": "moto", "data": "20/05/2026", "texto": "x"},  # já passou (hoje é 01/06/2026)
        {"produto": "moto", "data": "05/06/2026", "texto": "   "},  # sem texto
        {"produto": "fone de ouvido", "data": "05/06/2026", "texto": "x"},  # produto que não existe
    ],
)
def test_lembretes_invalidos_viram_erro_e_nao_criam_acao(ambiente, argumentos):
    c, _ = conversa(ambiente, chama("propor_lembrete", **argumentos), texto("Não consegui."))

    resposta = c.responder("Me lembra de algo")

    assert c.acao is None
    assert "erro" in resposta.consultas[0].resultado


def test_listar_lembretes_mostra_os_pendentes(ambiente):
    from garantiafacil.lembretes import Lembretes

    repo, _ = ambiente
    moto = next(p for p in repo.listar() if p.nome.startswith("MOTO"))
    Lembretes(repo.conexao, repo.usuario_id).adicionar(moto.id, date(2026, 6, 5), "levar na assistência")
    c, _ = conversa(ambiente, chama("listar_lembretes"), texto("Você tem 1 lembrete."))

    resposta = c.responder("Que lembretes eu tenho?")

    assert "levar na assistência" in resposta.consultas[0].resultado
    assert "05/06/2026" in resposta.consultas[0].resultado
