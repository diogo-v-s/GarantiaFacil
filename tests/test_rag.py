import numpy as np
import pytest

from garantiafacil.db import conectar
from garantiafacil.rag import SEM_DOCUMENTOS, SISTEMA, BaseConhecimento, montar_prompt


def embedding_falso(texto: str, consulta: bool = False) -> np.ndarray:
    """Dublê: 'tela' e 'prazo/meses' são as duas dimensões de significado."""
    t = texto.lower()
    return np.array(
        [1.0 if "tela" in t else 0.0, 1.0 if ("prazo" in t or "meses" in t) else 0.0, 0.1],
        dtype=np.float32,
    )


class LlmFalso:
    def __init__(self, resposta="Resposta pronta [1]."):
        self.resposta = resposta
        self.chamadas = []

    def perguntar(self, prompt, sistema=None, temperatura=None):
        self.chamadas.append({"prompt": prompt, "sistema": sistema, "temperatura": temperatura})
        return self.resposta


@pytest.fixture
def base():
    return BaseConhecimento(conectar(":memory:"), embedding_falso, lambda: "falso")


def inserir_produto(base) -> int:
    cursor = base.conexao.execute(
        "INSERT INTO produtos (nome, loja, data_compra, prazo_garantia_meses) "
        "VALUES ('Celular', 'Loja', '2026-01-01', 12)"
    )
    return cursor.lastrowid


DOC_TELA = [(1, "A tela quebrada não é coberta pela garantia.")]
DOC_PRAZO = [(2, "O prazo de garantia é de 12 meses a partir da compra.")]


def test_indexar_devolve_quantidade_e_lista_fontes(base):
    assert base.indexar("termo.txt", DOC_TELA) == 1
    assert base.listar_fontes() == [("termo.txt", None, 1)]


def test_buscar_ordena_pela_proximidade(base):
    base.indexar("a.txt", DOC_PRAZO)
    base.indexar("b.txt", DOC_TELA)

    trechos = base.buscar("a tela está coberta?")

    assert [t.fonte for t in trechos] == ["b.txt", "a.txt"]
    assert trechos[0].similaridade > trechos[1].similaridade


def test_buscar_respeita_o_limite_k(base):
    for i in range(5):
        base.indexar(f"doc{i}.txt", DOC_TELA)

    assert len(base.buscar("tela", k=3)) == 3


def test_filtro_por_produto_inclui_documentos_gerais(base):
    produto_a = inserir_produto(base)
    produto_b = inserir_produto(base)
    base.indexar("manual_a.txt", DOC_TELA, produto_id=produto_a)
    base.indexar("manual_b.txt", DOC_TELA, produto_id=produto_b)
    base.indexar("cdc.txt", DOC_PRAZO)  # geral

    fontes = {t.fonte for t in base.buscar("tela", produto_id=produto_a)}

    assert fontes == {"manual_a.txt", "cdc.txt"}


def test_sem_filtro_considera_todos(base):
    produto = inserir_produto(base)
    base.indexar("manual.txt", DOC_TELA, produto_id=produto)
    base.indexar("cdc.txt", DOC_PRAZO)

    assert {t.fonte for t in base.buscar("tela")} == {"manual.txt", "cdc.txt"}


def test_reindexar_a_mesma_fonte_substitui(base):
    base.indexar("termo.txt", DOC_TELA)
    base.indexar("termo.txt", DOC_PRAZO)

    assert base.listar_fontes() == [("termo.txt", None, 1)]
    assert "prazo" in base.buscar("prazo")[0].texto


def test_falha_no_embedding_preserva_a_indexacao_anterior():
    chamadas = {"n": 0}

    def quebra_na_segunda(texto, consulta=False):
        chamadas["n"] += 1
        if chamadas["n"] > 1:
            raise ConnectionError("Ollama caiu")
        return embedding_falso(texto, consulta)

    base = BaseConhecimento(conectar(":memory:"), quebra_na_segunda, lambda: "falso")
    base.indexar("termo.txt", DOC_TELA)

    with pytest.raises(ConnectionError):
        base.indexar("termo.txt", DOC_PRAZO)

    assert base.listar_fontes() == [("termo.txt", None, 1)]  # a versão antiga continua lá


def test_vetores_de_outro_modelo_sao_ignorados():
    modelo = {"nome": "a"}
    base = BaseConhecimento(conectar(":memory:"), embedding_falso, lambda: modelo["nome"])
    base.indexar("termo.txt", DOC_TELA)

    modelo["nome"] = "b"

    assert base.buscar("tela") == []


def test_responder_monta_prompt_numerado_e_usa_temperatura_zero(base):
    base.indexar("termo.txt", DOC_TELA)
    llm = LlmFalso()

    resposta = base.responder("A tela quebrada é coberta?", llm)

    chamada = llm.chamadas[0]
    assert "[1] (fonte: termo.txt, página 1)" in chamada["prompt"]
    assert "A tela quebrada não é coberta" in chamada["prompt"]
    assert chamada["prompt"].endswith("Pergunta: A tela quebrada é coberta?")
    assert chamada["sistema"] == SISTEMA
    assert chamada["temperatura"] == 0
    assert resposta.texto == "Resposta pronta [1]."
    assert [t.fonte for t in resposta.trechos] == ["termo.txt"]


def test_responder_sem_documentos_nao_chama_o_llm(base):
    llm = LlmFalso()

    resposta = base.responder("qualquer coisa", llm)

    assert resposta.texto == SEM_DOCUMENTOS
    assert llm.chamadas == []


def test_excluir_produto_apaga_os_trechos_dele(base):
    produto = inserir_produto(base)
    base.indexar("manual.txt", DOC_TELA, produto_id=produto)
    base.conexao.execute("PRAGMA foreign_keys = ON")

    base.conexao.execute("DELETE FROM produtos WHERE id = ?", (produto,))

    assert base.listar_fontes() == []


def test_montar_prompt_numera_a_partir_de_1():
    from garantiafacil.rag import TrechoEncontrado

    trechos = [
        TrechoEncontrado("a.txt", 1, "primeiro", 0.9, None),
        TrechoEncontrado("b.pdf", 4, "segundo", 0.8, None),
    ]

    prompt = montar_prompt("Pergunta?", trechos)

    assert "[1] (fonte: a.txt, página 1)\nprimeiro" in prompt
    assert "[2] (fonte: b.pdf, página 4)\nsegundo" in prompt


def test_citacoes_validas_nao_geram_alerta(base):
    base.indexar("termo.txt", DOC_TELA)

    resposta = base.responder("tela?", LlmFalso("Não cobre [1]."))

    assert resposta.citacoes_invalidas == []


def test_citacao_de_trecho_inexistente_e_detectada(base):
    base.indexar("termo.txt", DOC_TELA)  # só 1 trecho

    resposta = base.responder("tela?", LlmFalso("Não cobre [1] e também [4]."))

    assert resposta.citacoes_invalidas == [4]


def test_achar_citacoes_invalidas():
    from garantiafacil.rag import achar_citacoes_invalidas

    assert achar_citacoes_invalidas("texto sem citação", 3) == []
    assert achar_citacoes_invalidas("[1] [2] [3]", 3) == []
    assert achar_citacoes_invalidas("[0] [2] [5] [5]", 3) == [0, 5]


def test_fonte_indexada(base):
    produto = inserir_produto(base)
    assert not base.fonte_indexada("cdc.txt")

    base.indexar("cdc.txt", DOC_PRAZO)
    base.indexar("manual.txt", DOC_TELA, produto_id=produto)

    assert base.fonte_indexada("cdc.txt")
    assert not base.fonte_indexada("cdc.txt", produto_id=produto)
    assert base.fonte_indexada("manual.txt", produto_id=produto)


def test_buscar_so_gerais_ignora_documentos_de_produto(base):
    produto = inserir_produto(base)
    base.indexar("cdc.txt", DOC_PRAZO)
    base.indexar("manual.txt", DOC_TELA, produto_id=produto)

    assert {t.fonte for t in base.buscar("tela", so_gerais=True)} == {"cdc.txt"}


def test_tem_documentos_do_produto(base):
    com_termo, sem_termo = inserir_produto(base), inserir_produto(base)
    base.indexar("manual.txt", DOC_TELA, produto_id=com_termo)

    assert base.tem_documentos(com_termo)
    assert not base.tem_documentos(sem_termo)
