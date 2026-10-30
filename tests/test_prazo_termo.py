from garantiafacil.prazo_termo import (
    LIMITE_CARACTERES,
    PrazoLido,
    SugestaoPrazo,
    _texto_para_ler,
    sugerir_prazo,
)

FRASE = "A garantia é de 12 meses, contados da data de emissão da nota fiscal."
TERMO = [
    (1, f"TERMO DE GARANTIA\n\nO produto é fabricado com rigor.\n\n1. Prazo. {FRASE}"),
    (2, "2. Exclusões. Não cobre tela quebrada.\n\nEntrega em até 5 dias úteis."),
]


class LlmFalso:
    """Dublê do LLM: devolve a resposta combinada e guarda o prompt recebido."""

    def __init__(self, resposta: PrazoLido):
        self.resposta = resposta
        self.prompts: list[str] = []

    def estruturar(self, prompt, formato, sistema=None):
        self.prompts.append(prompt)
        return self.resposta


def lido(encontrou=True, meses=12, trecho=FRASE) -> LlmFalso:
    return LlmFalso(PrazoLido(encontrou=encontrou, meses=meses, trecho=trecho))


def test_prazo_com_frase_que_existe_no_termo_e_aceito():
    assert sugerir_prazo(TERMO, lido()) == SugestaoPrazo(12, FRASE)


def test_frase_e_conferida_sem_ligar_para_quebra_de_linha_nem_maiuscula():
    termo = [(1, "A garantia é de 12\nmeses,   contados da DATA de emissão da nota fiscal.")]

    assert sugerir_prazo(termo, lido()) is not None


def test_frase_inventada_e_recusada_mesmo_com_prazo_plausivel():
    assert sugerir_prazo(TERMO, lido(trecho="A garantia vitalícia cobre tudo.")) is None


def test_ia_que_nao_achou_ou_sem_frase_vira_none():
    assert sugerir_prazo(TERMO, lido(encontrou=False, meses=0, trecho="")) is None
    assert sugerir_prazo(TERMO, lido(trecho="")) is None


def test_meses_fora_do_limite_e_recusado():
    assert sugerir_prazo(TERMO, lido(meses=0)) is None
    assert sugerir_prazo(TERMO, lido(meses=121)) is None
    assert sugerir_prazo(TERMO, lido(meses=-3)) is None


def test_so_paragrafos_que_falam_de_prazo_vao_para_a_ia():
    texto = _texto_para_ler(TERMO)

    assert "garantia é de 12 meses" in texto
    assert "fabricado com rigor" not in texto  # não fala de prazo


def test_texto_enorme_e_cortado_no_limite():
    paragrafo = "A garantia vale por muito tempo. " * 30
    termo = [(1, "\n\n".join([paragrafo] * 50))]

    assert len(_texto_para_ler(termo)) <= LIMITE_CARACTERES


def test_termo_sem_nada_sobre_prazo_nem_chama_a_ia():
    llm = lido()

    assert sugerir_prazo([(1, "Parabéns pela compra!")], llm) is None
    assert llm.prompts == []
