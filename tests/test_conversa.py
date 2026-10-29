from datetime import date

import numpy as np
import pytest

from garantiafacil.conversa import Analise, Conversa, localizar_produto
from garantiafacil.db import conectar
from garantiafacil.modelos import Produto
from garantiafacil.rag import BaseConhecimento
from garantiafacil.repositorio import Repositorio
from tests.ajuda import banco_com_usuario


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
        self.sistemas = []
        self.analises = 0

    def estruturar(self, prompt, formato, sistema=None):
        self.analises += 1
        return self.classificar(prompt)

    def perguntar(self, prompt, sistema=None, temperatura=None):
        self.prompts.append(prompt)
        self.sistemas.append(sistema)
        return "Resposta [1]."


def sempre(precisa: bool, citado: str = ""):
    return lambda _mensagem: Analise(assunto="produto" if precisa else "lei", produto_citado=citado)


def novo(nome: str) -> Produto:
    return Produto(nome=nome, loja="Loja", data_compra=date(2026, 1, 1), prazo_garantia_meses=12)


@pytest.fixture
def ambiente(tmp_path, monkeypatch):
    """Banco com 2 produtos, o CDC (geral) e o termo do Moto G60. Sem busca semântica de produto."""
    repo = Repositorio(
        *banco_com_usuario(), tmp_path, gerar_embedding=embedding_falso, nome_modelo=lambda: "f"
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

    assert "Não entendi qual produto" in resposta.texto
    assert c.pergunta_pendente == "A garantia cobre tela quebrada?"


def test_pergunta_nova_durante_o_esclarecimento_abandona_a_pendente(ambiente):
    analises = iter([Analise(assunto="produto", produto_citado=""),
                     Analise(assunto="lei", produto_citado="")])
    c, llm = conversa(ambiente, lambda _m: next(analises))
    c.responder("A garantia cobre tela quebrada?")

    resposta = c.responder("Qual o prazo do CDC para defeito?")

    assert {t.fonte for t in resposta.trechos} == {"cdc.txt"}
    assert c.pergunta_pendente is None


def test_produto_sem_termo_avisa_que_usou_so_o_cdc(ambiente):
    c, _ = conversa(ambiente, sempre(True, "geladeira brastemp"))

    resposta = c.responder("Quanto tempo de garantia?")

    assert resposta.produto.nome == "Geladeira Brastemp 375L"
    assert "Não há termo de garantia cadastrado" in resposta.texto
    assert {t.fonte for t in resposta.trechos} == {"cdc.txt"}


def test_sem_produtos_cadastrados_responde_com_o_cdc_e_avisa(tmp_path):
    repo = Repositorio(
        *banco_com_usuario(), tmp_path, gerar_embedding=embedding_falso, nome_modelo=lambda: "f"
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


# ---------- pergunta sobre o cadastro (agente) ----------


def test_pergunta_sobre_o_cadastro_vai_para_o_agente(ambiente):
    from garantiafacil.agente import Chamada, PassoLlm

    repo, base, *_ = ambiente
    llm = LlmFalso(lambda _m: Analise(assunto="cadastro", produto_citado=""))
    passos = iter(
        [
            PassoLlm("", [Chamada("1", "listar_produtos", {"status": "em_garantia"})]),
            PassoLlm("Você tem 2 produtos na garantia.", []),
        ]
    )
    llm.passo = lambda mensagens, ferramentas, sistema=None: next(passos)
    c = Conversa(repo, base, llm)

    resposta = c.responder("Quais produtos meus ainda estão na garantia?")

    assert resposta.texto == "Você tem 2 produtos na garantia."
    assert [q.nome for q in resposta.consultas] == ["listar_produtos"]
    assert '"total"' in resposta.consultas[0].resultado
    assert llm.prompts == []  # não passou pelo RAG
    assert c.pergunta_pendente is None


# ---------- produto sem termo: garantia legal do CDC ----------


def test_produto_sem_termo_explica_a_garantia_legal_do_cdc(ambiente):
    from garantiafacil.conversa import SISTEMA_SEM_TERMO

    c, llm = conversa(ambiente, sempre(True, "geladeira brastemp"))

    resposta = c.responder("O que a garantia cobre?")

    assert resposta.texto.startswith("Não há termo de garantia cadastrado para 'Geladeira Brastemp 375L'")
    assert llm.sistemas == [SISTEMA_SEM_TERMO]  # prompt próprio: explicar o que a lei prevê
    assert {t.fonte for t in resposta.trechos} == {"cdc.txt"}


def test_resposta_do_agente_sobre_um_produto_vira_o_assunto_da_conversa(ambiente):
    from garantiafacil.agente import PassoLlm

    repo, base, *_ = ambiente
    llm = LlmFalso(lambda _m: Analise(assunto="cadastro", produto_citado=""))
    llm.passo = lambda mensagens, ferramentas, sistema=None: PassoLlm(
        "Só a Geladeira Brastemp 375L está na garantia.", []
    )
    c = Conversa(repo, base, llm)

    c.responder("Qual produto ainda tem garantia?")

    assert c.produto_atual.nome == "Geladeira Brastemp 375L"


def test_resposta_do_agente_com_varios_produtos_nao_define_o_assunto(ambiente):
    from garantiafacil.agente import PassoLlm

    repo, base, *_ = ambiente
    llm = LlmFalso(lambda _m: Analise(assunto="cadastro", produto_citado=""))
    llm.passo = lambda mensagens, ferramentas, sistema=None: PassoLlm(
        "Você tem a Geladeira Brastemp 375L e o MOTO G60 128GB - AZUL.", []
    )
    c = Conversa(repo, base, llm)

    c.responder("Quais produtos eu tenho?")

    assert c.produto_atual is None


def test_referencia_que_nao_bate_com_nome_segue_no_produto_da_conversa(ambiente):
    c, llm = conversa(ambiente, sempre(True, "esse aparelho"))
    c.produto_atual = ambiente[2]  # o Moto G60 já é o assunto

    resposta = c.responder("e o que a garantia desse aparelho cobre?")

    assert resposta.produto.nome == "MOTO G60 128GB - AZUL"
    assert "De qual produto" not in resposta.texto


# ---------- rede de segurança: pergunta "geral" que na verdade era sobre um produto ----------


def test_pergunta_geral_sem_resposta_no_cdc_pergunta_se_e_de_um_produto(ambiente):
    from garantiafacil.rag import NAO_ENCONTREI

    c, llm = conversa(ambiente, sempre(False))
    respostas = iter([NAO_ENCONTREI, "Resposta [1]."])
    llm.perguntar = lambda prompt, sistema=None, temperatura=None: next(respostas)

    pergunta = c.responder("o que a garantia do celular cobria?")

    assert "Não achei isso nas leis" in pergunta.texto and "MOTO G60 128GB - AZUL" in pergunta.texto
    assert c.pergunta_pendente == "o que a garantia do celular cobria?"

    resposta = c.responder("o moto g60")

    assert resposta.produto.nome == "MOTO G60 128GB - AZUL"


def test_pergunta_geral_sem_resposta_usa_o_produto_da_conversa_se_houver(ambiente):
    from garantiafacil.rag import NAO_ENCONTREI

    c, llm = conversa(ambiente, sempre(False))
    c.produto_atual = ambiente[2]
    respostas = iter([NAO_ENCONTREI, "Resposta [1]."])
    llm.perguntar = lambda prompt, sistema=None, temperatura=None: next(respostas)

    resposta = c.responder("o que a garantia cobria?")

    assert resposta.produto.nome == "MOTO G60 128GB - AZUL"
    assert c.pergunta_pendente is None


def test_cadastro_e_produto_ao_mesmo_tempo_vai_para_os_documentos_e_nao_para_o_agente(ambiente):
    repo, base, *_ = ambiente
    llm = LlmFalso(
        lambda _m: Analise(assunto="produto", produto_citado="geladeira brastemp")
    )
    llm.passo = lambda *a, **k: pytest.fail("não devia chamar o agente")
    c = Conversa(repo, base, llm)

    resposta = c.responder("o que a garantia desse produto cobre?")

    assert resposta.texto.startswith("Não há termo de garantia cadastrado")
    assert resposta.consultas == []


# ---------- escolher o produto pelo número ----------


def test_opcoes_vem_numeradas(ambiente):
    c, _ = conversa(ambiente, sempre(True))

    pergunta = c.responder("A garantia cobre tela quebrada?")

    for i, produto in enumerate(c.opcoes_pendentes, 1):
        assert f"{i}. {produto.nome}" in pergunta.texto


def test_responder_com_o_numero_escolhe_a_opcao(ambiente):
    c, _ = conversa(ambiente, sempre(True))
    c.responder("A garantia cobre tela quebrada?")
    segundo = c.opcoes_pendentes[1]

    resposta = c.responder("2")

    assert resposta.produto.nome == segundo.nome and c.pergunta_pendente is None


@pytest.mark.parametrize("fala", ["o 1", "número 1", "o primeiro", "a primeira", "1."])
def test_formas_de_dizer_a_posicao(ambiente, fala):
    c, _ = conversa(ambiente, sempre(True))
    c.responder("A garantia cobre tela quebrada?")
    primeiro = c.opcoes_pendentes[0]

    assert c.responder(fala).produto.nome == primeiro.nome


def test_numero_fora_das_opcoes_pergunta_de_novo_com_dica(ambiente):
    c, _ = conversa(ambiente, sempre(True))
    c.responder("A garantia cobre tela quebrada?")

    resposta = c.responder("9")

    assert "Responda com o nome ou com o número" in resposta.texto
    assert c.pergunta_pendente == "A garantia cobre tela quebrada?"


def test_numero_dentro_do_nome_do_produto_nao_vira_posicao(ambiente):
    c, _ = conversa(ambiente, sempre(True))
    c.responder("A garantia cobre tela quebrada?")

    assert c.responder("moto g60").produto.nome == "MOTO G60 128GB - AZUL"  # o 60 não é a opção 60


def test_referencia_vaga_nao_troca_o_produto_por_busca_de_significado(ambiente, monkeypatch):
    repo, base, moto, geladeira = ambiente
    # a busca por significado acharia a geladeira para "desse produto"...
    monkeypatch.setattr(repo, "buscar_semantico", lambda *a, **k: [(geladeira, 0.9)])
    c, _ = conversa(ambiente, sempre(True, "desse produto"))
    c.produto_atual = moto  # ...mas o assunto da conversa é o Moto G60

    resposta = c.responder("o que a garantia desse produto cobre?")

    assert resposta.produto.nome == "MOTO G60 128GB - AZUL"


def test_sem_produto_em_discussao_a_busca_por_significado_ainda_vale(ambiente, monkeypatch):
    repo, base, moto, geladeira = ambiente
    monkeypatch.setattr(repo, "buscar_semantico", lambda *a, **k: [(geladeira, 0.9)])
    c, _ = conversa(ambiente, sempre(True, "eletrodoméstico"))

    resposta = c.responder("o que a garantia do eletrodoméstico cobre?")

    assert resposta.produto.nome == "Geladeira Brastemp 375L"


# ---------- regra para perguntas claramente de cadastro ----------


@pytest.mark.parametrize(
    "frase",
    [
        "quando vence a garantia do LP KODAK?",
        "O que vence nos próximos 60 dias?",
        "quais produtos já venceram a garantia?",
        "quanto paguei no Xbox?",
        "quando comprei a furadeira?",
    ],
)
def test_frases_com_sinal_claro_de_cadastro_vao_para_o_agente_mesmo_se_o_classificador_erra(ambiente, frase):
    from garantiafacil.agente import PassoLlm

    repo, base, *_ = ambiente
    llm = LlmFalso(sempre(True, "xbox"))  # o classificador "errou": disse produto
    llm.passo = lambda mensagens, ferramentas, sistema=None: PassoLlm("Dados do cadastro.", [])
    c = Conversa(repo, base, llm)

    resposta = c.responder(frase)

    assert resposta.texto == "Dados do cadastro."
    assert llm.prompts == []  # não passou pelo RAG


@pytest.mark.parametrize(
    "frase",
    [
        "o que a garantia do notebook cobre?",
        "posso reclamar se a garantia venceu?",
        "o que diz a lei sobre garantia vencida?",
        "a assistência atende depois que vence?",
        "A garantia cobre tela quebrada?",
    ],
)
def test_cobertura_lei_e_condicao_ficam_com_o_classificador(ambiente, frase):
    from garantiafacil.conversa import _fala_do_cadastro

    assert not _fala_do_cadastro(frase)


def test_trechos_por_resposta_depende_do_provedor(monkeypatch):
    from garantiafacil.conversa import trechos_por_resposta

    monkeypatch.setenv("LLM_PROVIDER", "claude")
    assert trechos_por_resposta() == 5
    monkeypatch.setenv("LLM_PROVIDER", "ollama")
    assert trechos_por_resposta() == 3
    monkeypatch.delenv("LLM_PROVIDER")
    assert trechos_por_resposta() == 3
