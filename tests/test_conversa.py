from datetime import date

import numpy as np
import pytest

from garantiafacil.conversa import Analise, Conversa, localizar_produto
from garantiafacil.db import conectar
from garantiafacil.modelos import Produto
from garantiafacil.rag import BaseConhecimento
from garantiafacil.repositorio import Repositorio


def embedding_falso(texto: str, consulta: bool = False) -> np.ndarray:
    t = texto.lower()
    return np.array(
        [1.0 if "tela" in t else 0.0, 1.0 if ("prazo" in t or "dias" in t) else 0.0, 0.1],
        dtype=np.float32,
    )


class LlmFalso:
    """Dublê: a classificação vem de uma função; a resposta é fixa e o prompt fica registrado."""

    def __init__(self, classificar):
        self.classificar = classificar
        self.prompts = []
        self.analises = 0

    def estruturar(self, prompt, formato, sistema=None):
        self.analises += 1
        return self.classificar(prompt)

    def perguntar(self, prompt, sistema=None, temperatura=None):
        self.prompts.append(prompt)
        return "Resposta [1]."


def sempre(precisa: bool, citado: str = ""):
    return lambda _mensagem: Analise(precisa_produto=precisa, produto_citado=citado)


def novo(nome: str) -> Produto:
    return Produto(nome=nome, loja="Loja", data_compra=date(2026, 1, 1), prazo_garantia_meses=12)


@pytest.fixture
def ambiente(tmp_path, monkeypatch):
    """Banco com 2 produtos, o CDC (geral) e o termo do Moto G60. Sem busca semântica de produto."""
    repo = Repositorio(
        conectar(":memory:"), tmp_path, gerar_embedding=embedding_falso, nome_modelo=lambda: "f"
    )
    monkeypatch.setattr(repo, "buscar_semantico", lambda *a, **k: [])
    moto = repo.adicionar(novo("MOTO G60 128GB - AZUL"))
    geladeira = repo.adicionar(novo("Geladeira Brastemp 375L"))

    base = BaseConhecimento(repo.conexao, embedding_falso, lambda: "f")
    base.indexar("cdc.txt", [(1, "O prazo para reclamar de defeito é de 90 dias.")])
    base.indexar("termo-moto.txt", [(1, "A tela quebrada não é coberta pela garantia.")], moto.id)
    return repo, base, moto, geladeira


def conversa(ambiente, classificar) -> tuple[Conversa, LlmFalso]:
    repo, base, *_ = ambiente
    llm = LlmFalso(classificar)
    return Conversa(repo, base, llm), llm


# ---------- localizar_produto ----------


def test_localizar_por_palavras_ignorando_acento_e_caixa():
    produtos = [novo("Refrigerador Brastemp"), novo("Notebook Dell")]

    assert [p.nome for p in localizar_produto("o REFRIGERADOR da brastemp", produtos)] == [
        "Refrigerador Brastemp"
    ]


def test_localizar_escolhe_o_de_mais_palavras_em_comum():
    produtos = [novo("Celular Samsung A54"), novo("MOTO G60 128GB - AZUL")]

    # 'celular' bate com o primeiro, mas 'moto' e 'g60' batem com o segundo
    assert [p.nome for p in localizar_produto("o celular moto g60", produtos)] == [
        "MOTO G60 128GB - AZUL"
    ]


def test_localizar_empate_devolve_todos_e_nada_devolve_vazio():
    produtos = [novo("Moto G60"), novo("Moto G20")]

    assert len(localizar_produto("moto", produtos)) == 2
    assert localizar_produto("televisão", produtos) == []


# ---------- pergunta geral ----------


def test_pergunta_geral_usa_so_documentos_gerais(ambiente):
    c, llm = conversa(ambiente, sempre(False))

    resposta = c.responder("Qual o prazo do CDC para defeito?")

    assert {t.fonte for t in resposta.trechos} == {"cdc.txt"}
    assert resposta.produto is None
    assert c.pergunta_pendente is None


# ---------- pergunta de produto ----------


def test_sem_produto_pergunta_de_qual_e_depois_responde_com_o_termo(ambiente):
    c, llm = conversa(ambiente, sempre(True))

    pergunta = c.responder("A garantia cobre tela quebrada?")

    assert "De qual produto" in pergunta.texto
    assert "MOTO G60 128GB - AZUL" in pergunta.texto and "Geladeira Brastemp 375L" in pergunta.texto
    assert llm.prompts == []  # ainda não consultou os documentos

    resposta = c.responder("o celular moto g60")

    assert resposta.produto.nome == "MOTO G60 128GB - AZUL"
    assert "termo-moto.txt" in {t.fonte for t in resposta.trechos}
    assert "A garantia cobre tela quebrada?" in llm.prompts[0]  # a pergunta original foi retomada
    assert c.pergunta_pendente is None


def test_produto_citado_na_pergunta_nao_gera_pergunta_de_volta(ambiente):
    c, llm = conversa(ambiente, sempre(True, "moto g60"))

    resposta = c.responder("A garantia do moto g60 cobre tela quebrada?")

    assert resposta.produto.nome == "MOTO G60 128GB - AZUL"
    assert "De qual produto" not in resposta.texto


def test_pergunta_seguinte_reaproveita_o_produto_da_conversa(ambiente):
    c, llm = conversa(ambiente, sempre(True))
    c.responder("A garantia cobre tela quebrada?")
    c.responder("moto g60")

    resposta = c.responder("e o prazo?")

    assert resposta.produto.nome == "MOTO G60 128GB - AZUL"
    assert "De qual produto" not in resposta.texto


def test_produto_ambiguo_pergunta_qual_deles(ambiente):
    repo, base, *_ = ambiente
    repo.adicionar(novo("MOTO G20"))
    c, _ = conversa(ambiente, sempre(True))

    c.responder("A garantia cobre tela quebrada?")
    resposta = c.responder("moto")

    assert "mais de um" in resposta.texto
    assert "MOTO G60 128GB - AZUL" in resposta.texto and "MOTO G20" in resposta.texto
    assert c.pergunta_pendente is not None

    final = c.responder("o g20")
    assert final.produto.nome == "MOTO G20"


def test_resposta_que_nao_identifica_produto_pergunta_de_novo(ambiente):
    c, _ = conversa(ambiente, sempre(True))
    c.responder("A garantia cobre tela quebrada?")

    resposta = c.responder("sei lá")

    assert "De qual produto" in resposta.texto
    assert c.pergunta_pendente == "A garantia cobre tela quebrada?"


def test_pergunta_nova_durante_o_esclarecimento_abandona_a_pendente(ambiente):
    analises = iter([Analise(precisa_produto=True, produto_citado=""),
                     Analise(precisa_produto=False, produto_citado="")])
    c, llm = conversa(ambiente, lambda _m: next(analises))
    c.responder("A garantia cobre tela quebrada?")

    resposta = c.responder("Qual o prazo do CDC para defeito?")

    assert {t.fonte for t in resposta.trechos} == {"cdc.txt"}
    assert c.pergunta_pendente is None


def test_produto_sem_termo_avisa_que_usou_so_o_cdc(ambiente):
    c, _ = conversa(ambiente, sempre(True, "geladeira brastemp"))

    resposta = c.responder("Quanto tempo de garantia?")

    assert resposta.produto.nome == "Geladeira Brastemp 375L"
    assert "ainda não tem termo de garantia" in resposta.texto
    assert {t.fonte for t in resposta.trechos} == {"cdc.txt"}


def test_sem_produtos_cadastrados_responde_com_o_cdc_e_avisa(tmp_path):
    repo = Repositorio(
        conectar(":memory:"), tmp_path, gerar_embedding=embedding_falso, nome_modelo=lambda: "f"
    )
    base = BaseConhecimento(repo.conexao, embedding_falso, lambda: "f")
    base.indexar("cdc.txt", [(1, "O prazo é de 90 dias.")])
    c = Conversa(repo, base, LlmFalso(sempre(True)))

    resposta = c.responder("A garantia cobre tela quebrada?")

    assert "não tem produtos cadastrados" in resposta.texto
    assert {t.fonte for t in resposta.trechos} == {"cdc.txt"}


def test_reiniciar_limpa_o_assunto(ambiente):
    c, _ = conversa(ambiente, sempre(True))
    c.responder("A garantia cobre tela quebrada?")
    c.responder("moto g60")

    c.reiniciar()

    assert c.produto_atual is None and c.pergunta_pendente is None
    assert "De qual produto" in c.responder("A garantia cobre tela quebrada?").texto
