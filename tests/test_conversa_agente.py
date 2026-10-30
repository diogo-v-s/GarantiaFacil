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


def chama(nome, **argumentos):
    return PassoLlm("", [Chamada("id1", nome, argumentos)])


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
