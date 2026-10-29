import json
import sys
import types
from datetime import date

import pytest

from garantiafacil.agente import Chamada, Ferramenta, PassoLlm, executar_agente, executar_ferramenta
from garantiafacil.db import conectar
from garantiafacil.ferramentas_cadastro import criar_ferramentas
from garantiafacil.modelos import Categoria, Produto
from garantiafacil.repositorio import Repositorio
from tests.ajuda import banco_com_usuario

HOJE = date(2026, 6, 1)


class LlmRoteirizado:
    """Dublê: devolve passos pré-definidos e guarda as mensagens que recebeu."""

    def __init__(self, *passos):
        self.passos = list(passos)
        self.recebidas = []

    def passo(self, mensagens, ferramentas, sistema=None):
        self.recebidas.append(list(mensagens))
        return self.passos.pop(0)


def somar(a: int, b: int) -> int:
    return a + b


SOMAR = Ferramenta(
    "somar", "soma dois números", {"a": {"type": "integer"}, "b": {"type": "integer"}}, somar,
    obrigatorios=("a", "b"),
)


# ---------- laço do agente ----------


def test_agente_executa_a_ferramenta_e_devolve_a_resposta_final():
    llm = LlmRoteirizado(
        PassoLlm("", [Chamada("1", "somar", {"a": 2, "b": 3})]),
        PassoLlm("A soma é 5.", []),
    )

    resposta = executar_agente(llm, "quanto é 2+3?", [SOMAR], "sistema")

    assert resposta.texto == "A soma é 5." and resposta.completo
    assert [(c.nome, c.resultado) for c in resposta.consultas] == [("somar", "5")]
    # o 2º passo recebeu o resultado da ferramenta de volta
    assert llm.recebidas[1][-1]["papel"] == "resultado" and llm.recebidas[1][-1]["conteudo"] == "5"


def test_ferramenta_inexistente_vira_erro_e_nao_derruba_o_agente():
    llm = LlmRoteirizado(PassoLlm("", [Chamada("1", "voar", {})]), PassoLlm("Não consegui.", []))

    resposta = executar_agente(llm, "voe", [SOMAR], "s")

    assert "não existe" in resposta.consultas[0].resultado
    assert resposta.texto == "Não consegui."


def test_argumento_errado_vira_erro_para_o_modelo_tentar_de_novo():
    resultado = executar_ferramenta({"somar": SOMAR}, Chamada("1", "somar", {"a": 1, "c": 2}))

    assert "erro" in json.loads(resultado)


def test_agente_para_ao_estourar_o_maximo_de_passos():
    sempre_chama = [PassoLlm("", [Chamada(str(i), "somar", {"a": 1, "b": 1})]) for i in range(10)]

    resposta = executar_agente(LlmRoteirizado(*sempre_chama), "?", [SOMAR], "s", max_passos=3)

    assert not resposta.completo and len(resposta.consultas) == 3


# ---------- ferramentas do cadastro ----------


@pytest.fixture
def repo(tmp_path):
    repo = Repositorio(
        *banco_com_usuario(), tmp_path, gerar_embedding=lambda *a, **k: None, nome_modelo=lambda: "f"
    )
    repo._indexar = lambda produto: True  # sem embeddings nos testes
    cadastros = [
        ("Geladeira Brastemp", date(2026, 1, 1), 12, Categoria.ELETRODOMESTICOS),  # até 01/01/2027
        ("Moto G60", date(2025, 6, 20), 12, Categoria.ELETRONICOS),  # até 20/06/2026: 19 dias
        ("Xbox Series S", date(2025, 1, 1), 12, Categoria.ELETRONICOS),  # venceu em 01/01/2026
    ]
    for nome, compra, meses, categoria in cadastros:
        repo.adicionar(
            Produto(nome=nome, loja="Loja", data_compra=compra, prazo_garantia_meses=meses,
                    categoria=categoria)  # fmt: skip
        )
    return repo


def ferramenta(repo, nome):
    return next(f for f in criar_ferramentas(repo, HOJE) if f.nome == nome).funcao


def test_listar_em_garantia_inclui_a_que_vence_em_breve(repo):
    resultado = ferramenta(repo, "listar_produtos")(status="em_garantia")

    assert {p["nome"] for p in resultado["produtos"]} == {"Geladeira Brastemp", "Moto G60"}


def test_listar_vencidas_e_por_categoria(repo):
    listar = ferramenta(repo, "listar_produtos")

    assert [p["nome"] for p in listar(status="vencida")["produtos"]] == ["Xbox Series S"]
    assert listar(categoria="eletronicos")["total"] == 2  # sem acento e minúsculas também vale


def test_listar_com_filtro_invalido_devolve_erro_com_as_opcoes(repo):
    listar = ferramenta(repo, "listar_produtos")

    assert "erro" in listar(status="qualquer")
    assert "erro" in listar(categoria="Comidas")


def test_resumo_traz_datas_formatadas_e_a_situacao_em_texto(repo):
    listar = ferramenta(repo, "listar_produtos")
    [moto] = listar(status="vencendo_em_breve")["produtos"]
    [xbox] = listar(status="vencida")["produtos"]

    assert moto["garantia_ate"] == "20/06/2026" and moto["situacao"] == "faltam 19 dias para vencer"
    assert xbox["situacao"] == "já venceu"  # sem número: o modelo local lia errado


def test_vencimentos_proximos_respeita_a_janela(repo):
    proximos = ferramenta(repo, "vencimentos_proximos")

    assert [p["nome"] for p in proximos(dias=30)["produtos"]] == ["Moto G60"]
    assert proximos(dias=5)["total"] == 0
    assert proximos(dias="30")["total"] == 1  # modelos às vezes mandam número como texto


def test_detalhes_do_produto_e_casos_de_erro(repo):
    detalhes = ferramenta(repo, "detalhes_produto")

    assert detalhes("geladeira")["prazo_garantia_meses"] == 12
    assert "erro" in detalhes("televisão")
    repo.adicionar(
        Produto(nome="Moto G20", loja="L", data_compra=HOJE, prazo_garantia_meses=12)
    )
    assert set(detalhes("moto")["opcoes"]) == {"Moto G60", "Moto G20"}


# ---------- tradução para cada provedor ----------


def _falso_ollama(monkeypatch, resposta):
    capturado = {}

    def chat(**kwargs):
        capturado.update(kwargs)
        return resposta

    monkeypatch.setitem(sys.modules, "ollama", types.SimpleNamespace(chat=chat))
    return capturado


def test_ollama_traduz_mensagens_e_le_as_chamadas(monkeypatch):
    from garantiafacil.llm import OllamaLlm

    chamada = types.SimpleNamespace(
        function=types.SimpleNamespace(name="somar", arguments={"a": 1, "b": 2})
    )
    resposta = types.SimpleNamespace(
        message=types.SimpleNamespace(content="", tool_calls=[chamada])
    )
    capturado = _falso_ollama(monkeypatch, resposta)
    anterior = Chamada("0", "somar", {"a": 1, "b": 2})
    mensagens = [
        {"papel": "usuario", "texto": "soma"},
        {"papel": "assistente", "texto": "", "chamadas": [anterior]},
        {"papel": "resultado", "chamada": anterior, "conteudo": "3"},
    ]

    passo = OllamaLlm("m").passo(mensagens, [SOMAR], sistema="sis")

    assert [m["role"] for m in capturado["messages"]] == ["system", "user", "assistant", "tool"]
    assert capturado["messages"][2]["tool_calls"][0]["function"]["name"] == "somar"
    assert capturado["tools"][0]["function"]["parameters"]["required"] == ["a", "b"]
    assert passo.chamadas == [Chamada("0", "somar", {"a": 1, "b": 2})]


def test_claude_agrupa_os_resultados_e_devolve_o_id_da_chamada(monkeypatch):
    from garantiafacil.llm import ClaudeLlm

    capturado = {}
    bloco_texto = types.SimpleNamespace(type="text", text="ok")
    bloco_uso = types.SimpleNamespace(type="tool_use", id="toolu_9", name="somar", input={"a": 1, "b": 1})

    class ClienteFalso:
        def __init__(self):
            self.messages = types.SimpleNamespace(create=self.create)

        def create(self, **kwargs):
            capturado.update(kwargs)
            return types.SimpleNamespace(content=[bloco_texto, bloco_uso])

    monkeypatch.setitem(sys.modules, "anthropic", types.SimpleNamespace(Anthropic=ClienteFalso))
    c1, c2 = Chamada("t1", "somar", {"a": 1, "b": 1}), Chamada("t2", "somar", {"a": 2, "b": 2})
    mensagens = [
        {"papel": "usuario", "texto": "soma"},
        {"papel": "assistente", "texto": "", "chamadas": [c1, c2]},
        {"papel": "resultado", "chamada": c1, "conteudo": "2"},
        {"papel": "resultado", "chamada": c2, "conteudo": "4"},
    ]

    passo = ClaudeLlm("m").passo(mensagens, [SOMAR], sistema="sis")

    ultima = capturado["messages"][-1]
    assert ultima["role"] == "user" and [b["tool_use_id"] for b in ultima["content"]] == ["t1", "t2"]
    assert capturado["messages"][1]["content"][0]["type"] == "tool_use"  # sem bloco de texto vazio
    assert capturado["tools"][0]["input_schema"]["properties"].keys() == {"a", "b"}
    assert passo.texto == "ok" and passo.chamadas == [Chamada("toolu_9", "somar", {"a": 1, "b": 1})]
