import pytest

from garantiafacil.rag import achar_citacoes_invalidas, limpar_citacoes


@pytest.mark.parametrize(
    ("original", "esperado"),
    [
        ("O prazo é de 90 dias. [1]", "O prazo é de 90 dias."),
        ("A garantia vale 12 meses [1][2].", "A garantia vale 12 meses."),
        ("Cobre defeitos de fabricação [3], mas não tela quebrada [4].",
         "Cobre defeitos de fabricação, mas não tela quebrada."),
        # a frase que só aponta para o trecho some, e a próxima palavra vira início de frase
        ("De acordo com o trecho [1], o prazo é de 90 dias.", "O prazo é de 90 dias."),
        ("Conforme os trechos [1] e [3], a garantia cobre o painel.", "A garantia cobre o painel."),
        ("Não há termo. Segundo o trecho [2], vale a lei.", "Não há termo. Vale a lei."),
        # sem marcadores, nada muda
        ("O art. 18, § 1º, fala em 30 dias.", "O art. 18, § 1º, fala em 30 dias."),
        ("Lista:\n- 30 dias para não duráveis\n- 90 dias para duráveis",
         "Lista:\n- 30 dias para não duráveis\n- 90 dias para duráveis"),
    ],
)
def test_limpar_citacoes(original, esperado):
    assert limpar_citacoes(original) == esperado


def test_a_checagem_de_citacoes_inventadas_continua_usando_o_texto_original():
    original = "Vale 12 meses. [4]"

    assert achar_citacoes_invalidas(original, total_trechos=3) == [4]  # o aviso depende do marcador
    assert "[4]" not in limpar_citacoes(original)  # mas o usuário não vê o marcador
