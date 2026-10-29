import pytest

from garantiafacil.cpf_cnpj import (
    formatar_cnpj,
    formatar_cpf,
    formatar_telefone,
    so_digitos,
    validar_cnpj,
    validar_cpf,
)


@pytest.mark.parametrize("cpf", ["529.982.247-25", "52998224725", "  529 982 247 25 "])
def test_cpf_valido_com_ou_sem_pontuacao(cpf):
    assert validar_cpf(cpf)


@pytest.mark.parametrize(
    "cpf",
    ["529.982.247-24", "529.982.247-26", "111.111.111-11", "000.000.000-00", "1234", "", "abc"],
)
def test_cpf_invalido(cpf):
    assert not validar_cpf(cpf)


@pytest.mark.parametrize("cnpj", ["11.222.333/0001-81", "11222333000181"])
def test_cnpj_valido(cnpj):
    assert validar_cnpj(cnpj)


@pytest.mark.parametrize(
    "cnpj", ["11.222.333/0001-82", "00.000.000/0000-00", "11111111111111", "123", ""]
)
def test_cnpj_invalido(cnpj):
    assert not validar_cnpj(cnpj)


def test_digito_trocado_em_qualquer_posicao_e_pego():
    valido = "52998224725"
    for i in range(11):
        errado = valido[:i] + str((int(valido[i]) + 1) % 10) + valido[i + 1 :]
        assert not validar_cpf(errado), errado


def test_formatacao():
    assert formatar_cpf("52998224725") == "529.982.247-25"
    assert formatar_cnpj("11222333000181") == "11.222.333/0001-81"
    assert formatar_telefone("11912345678") == "(11) 91234-5678"
    assert formatar_telefone("1112345678") == "(11) 1234-5678"
    assert formatar_cpf("123") == "123"  # tamanho errado: devolve como veio
    assert so_digitos("(11) 91234-5678") == "11912345678"
