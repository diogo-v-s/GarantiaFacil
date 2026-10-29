from datetime import date

from garantiafacil.extracao import DadosNota
from garantiafacil.pipeline_nota import ler_nota as _ler_nota
from tests.test_chave_acesso import montar_chave


def ler_nota(imagem, **dependencias):
    """Por padrão desliga o plano B (leitura da chave impressa pela IA) nos testes."""
    dependencias.setdefault("ler_impressa", lambda *_: None)
    return _ler_nota(imagem, **dependencias)


class LlmFalso:
    def __init__(self, resposta: DadosNota):
        self.resposta = resposta

    def extrair(self, prompt, imagem, formato, sistema=None, tipo_midia="image/jpeg"):
        return self.resposta


def ia(**campos) -> LlmFalso:
    base = {
        "loja": "Loja da IA", "produto": "Notebook", "detalhes": "", "categoria": "Eletrônicos",
        "data_compra": "12/08/2026", "valor": 100.0,
    }  # fmt: skip
    return LlmFalso(DadosNota(**{**base, **campos}))


def sem_qr(_imagem):
    return None


def com_chave(chave: str):
    return lambda _imagem: chave


def test_sem_chave_usa_so_a_ia_e_avisa():
    r = ler_nota(b"x", llm=ia(), ler_chave=sem_qr)

    assert (r.loja, r.produto, r.valor) == ("Loja da IA", "Notebook", 100.0)
    assert r.data_compra == date(2026, 8, 12)
    assert len(r.avisos) == 1 and "não encontrada" in r.avisos[0]


def test_com_chave_a_loja_vem_do_cnpj():
    consultas = []

    def consultar(cnpj):
        consultas.append(cnpj)
        return "RAZAO SOCIAL REAL LTDA"

    r = ler_nota(
        b"x",
        llm=ia(),
        ler_chave=com_chave(montar_chave(aamm="2608", cnpj="11222333000181")),
        consultar_cnpj=consultar,
    )

    assert consultas == ["11222333000181"]
    assert r.loja == "RAZAO SOCIAL REAL LTDA"
    assert r.data_compra == date(2026, 8, 12)  # mês e ano conferem: mantém o dia da IA


def test_mes_divergente_usa_o_da_chave_e_mantem_o_dia_da_ia():
    r = ler_nota(
        b"x",
        llm=ia(data_compra="26/03/2022"),
        ler_chave=com_chave(montar_chave(aamm="2208")),
        consultar_cnpj=lambda cnpj: "LOJA",
    )

    assert r.data_compra == date(2022, 8, 26)
    assert any("não pôde ser confirmado" in a for a in r.avisos)


def test_data_ilegivel_usa_dia_1_do_mes_da_chave():
    r = ler_nota(
        b"x",
        llm=ia(data_compra="ontem"),
        ler_chave=com_chave(montar_chave(aamm="2209")),
        consultar_cnpj=lambda cnpj: "LOJA",
    )

    assert r.data_compra == date(2022, 9, 1)


def test_dia_da_ia_inexistente_no_mes_da_chave_vira_dia_1():
    # IA leu 31/03, mas a chave diz fevereiro: 31 não existe em fevereiro.
    r = ler_nota(
        b"x",
        llm=ia(data_compra="31/03/2026"),
        ler_chave=com_chave(montar_chave(aamm="2602")),
        consultar_cnpj=lambda cnpj: "LOJA",
    )

    assert r.data_compra == date(2026, 2, 1)


def test_cnpj_nao_consultado_mantem_loja_da_ia():
    r = ler_nota(
        b"x",
        llm=ia(),
        ler_chave=com_chave(montar_chave(aamm="2608")),
        consultar_cnpj=lambda cnpj: None,
    )

    assert r.loja == "Loja da IA"
    assert any("não consegui consultar" in a for a in r.avisos)


def test_chave_invalida_e_tratada_como_ausente():
    r = ler_nota(b"x", llm=ia(), ler_chave=com_chave("1" * 44), consultar_cnpj=lambda c: "X")

    assert r.loja == "Loja da IA"
    assert "não encontrada" in r.avisos[0]


def test_qr_ilegivel_usa_chave_impressa_lida_pela_ia():
    chave = montar_chave(aamm="2608", cnpj="11222333000181")

    r = ler_nota(
        b"x",
        llm=ia(),
        ler_chave=sem_qr,
        ler_impressa=lambda imagem, tipo, llm: chave,
        consultar_cnpj=lambda cnpj: "RAZAO SOCIAL REAL LTDA",
    )

    assert r.loja == "RAZAO SOCIAL REAL LTDA"
    assert any("texto impresso" in a for a in r.avisos)


def test_chave_impressa_com_digito_errado_e_descartada():
    # A IA "leu" 44 dígitos, mas um deles está trocado: o dígito verificador pega.
    valida = montar_chave()
    errada = valida[:10] + ("0" if valida[10] != "0" else "1") + valida[11:]

    r = ler_nota(
        b"x",
        llm=ia(),
        ler_chave=sem_qr,
        ler_impressa=lambda imagem, tipo, llm: errada,
        consultar_cnpj=lambda cnpj: "NAO DEVERIA CHAMAR",
    )

    assert r.loja == "Loja da IA"
    assert "não encontrada" in r.avisos[0]


def test_qr_valido_nao_aciona_a_leitura_pela_ia():
    chamadas = []

    def ler_impressa(imagem, tipo, llm):
        chamadas.append(1)
        return None

    ler_nota(
        b"x",
        llm=ia(),
        ler_chave=com_chave(montar_chave(aamm="2608")),
        ler_impressa=ler_impressa,
        consultar_cnpj=lambda cnpj: "LOJA",
    )

    assert chamadas == []


def test_detalhes_e_categoria_da_ia_vao_para_o_resultado():
    llm = ia(produto="Smartphone Moto E13", detalhes=" Vermelho, 64GB ", categoria="Eletrônicos")

    resultado = ler_nota(b"img", llm=llm, ler_chave=sem_qr)

    assert resultado.produto == "Smartphone Moto E13"
    assert resultado.detalhes == "Vermelho, 64GB"
    assert resultado.categoria.value == "Eletrônicos"


def test_data_ilegivel_sem_chave_avisa_que_usa_a_de_hoje():
    r = ler_nota(b"x", llm=ia(data_compra="ontem"), ler_chave=sem_qr)

    assert r.data_compra is None
    assert any("data da compra" in a for a in r.avisos)
