from datetime import date

from garantiafacil.extracao import DadosNota, extrair_dados_nota
from garantiafacil.modelos import Categoria


def dados(**campos) -> DadosNota:
    base = {
        "loja": "Loja X", "produto": "Notebook", "detalhes": "", "categoria": "Eletrônicos",
        "data_compra": "2026-03-05", "valor": 100.0,
    }  # fmt: skip
    return DadosNota(**{**base, **campos})


class LlmFalso:
    """Dublê do LLM: devolve sempre os dados combinados, sem chamar modelo nenhum."""

    def __init__(self, resposta: DadosNota):
        self.resposta = resposta
        self.chamadas = []

    def extrair(self, prompt, imagem, formato, sistema=None, tipo_midia="image/jpeg"):
        self.chamadas.append({"formato": formato, "imagem": imagem, "tipo_midia": tipo_midia})
        return self.resposta


def test_extrair_repassa_imagem_e_formato_ao_llm():
    llm = LlmFalso(dados(produto="Geladeira"))

    resultado = extrair_dados_nota(b"bytes", tipo_midia="image/png", llm=llm)

    assert resultado.produto == "Geladeira"
    assert llm.chamadas == [{"formato": DadosNota, "imagem": b"bytes", "tipo_midia": "image/png"}]


def test_data_iso():
    assert dados(data_compra="2026-03-05").data() == date(2026, 3, 5)


def test_data_no_formato_brasileiro():
    assert dados(data_compra="12/08/2026").data() == date(2026, 8, 12)


def test_data_com_hora_depois():
    assert dados(data_compra="30/09/2026 17:15:41").data() == date(2026, 9, 30)
    assert dados(data_compra="2026-09-30T17:15:41").data() == date(2026, 9, 30)


def test_data_invalida_vira_none():
    assert dados(data_compra="2026-13-45").data() is None
    assert dados(data_compra="ontem").data() is None
    assert dados(data_compra="").data() is None


def test_schema_tem_os_campos_obrigatorios():
    campos = {"produto", "detalhes", "categoria", "loja", "data_compra", "valor"}
    esquema = DadosNota.model_json_schema()
    assert set(esquema["properties"]) == campos
    assert set(esquema["required"]) == campos


def test_categoria_do_schema_acompanha_o_dominio():
    esquema = DadosNota.model_json_schema()
    assert set(esquema["properties"]["categoria"]["enum"]) == {c.value for c in Categoria}


def test_categoria_padrao_converte_para_o_dominio():
    assert dados(categoria="Móveis").categoria_padrao() == Categoria.MOVEIS
