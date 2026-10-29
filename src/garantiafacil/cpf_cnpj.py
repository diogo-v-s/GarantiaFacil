"""CPF e CNPJ: limpar, validar pelos dígitos verificadores e formatar.

Os dois últimos dígitos (CPF) ou dois últimos (CNPJ) são calculados a partir dos anteriores, com a
mesma ideia do módulo 11 da chave de acesso da nota: multiplica cada dígito por um peso, soma, e o
resto da divisão por 11 define o dígito verificador. Um número digitado errado quase sempre falha
nesse cálculo, e é isso que a validação pega (ela não prova que o documento existe)."""

import re

_PESOS_CNPJ_1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
_PESOS_CNPJ_2 = [6, *_PESOS_CNPJ_1]


def so_digitos(texto: str) -> str:
    return re.sub(r"\D", "", texto or "")


def _digito(digitos: list[int], pesos: list[int]) -> int:
    resto = sum(d * p for d, p in zip(digitos, pesos)) % 11
    return 0 if resto < 2 else 11 - resto


def validar_cpf(texto: str) -> bool:
    cpf = so_digitos(texto)
    if len(cpf) != 11 or len(set(cpf)) == 1:  # 111.111.111-11 passa na conta, mas não existe
        return False
    n = [int(c) for c in cpf]
    primeiro = _digito(n[:9], list(range(10, 1, -1)))
    segundo = _digito(n[:10], list(range(11, 1, -1)))
    return n[9] == primeiro and n[10] == segundo


def validar_cnpj(texto: str) -> bool:
    cnpj = so_digitos(texto)
    if len(cnpj) != 14 or len(set(cnpj)) == 1:
        return False
    n = [int(c) for c in cnpj]
    primeiro = _digito(n[:12], _PESOS_CNPJ_1)
    segundo = _digito(n[:13], _PESOS_CNPJ_2)
    return n[12] == primeiro and n[13] == segundo


def formatar_cpf(texto: str) -> str:
    c = so_digitos(texto)
    return f"{c[:3]}.{c[3:6]}.{c[6:9]}-{c[9:]}" if len(c) == 11 else texto


def formatar_cnpj(texto: str) -> str:
    c = so_digitos(texto)
    return f"{c[:2]}.{c[2:5]}.{c[5:8]}/{c[8:12]}-{c[12:]}" if len(c) == 14 else texto


def formatar_telefone(texto: str) -> str:
    """(11) 91234-5678 ou (11) 1234-5678; outro tamanho volta como veio."""
    t = so_digitos(texto)
    if len(t) == 11:
        return f"({t[:2]}) {t[2:7]}-{t[7:]}"
    if len(t) == 10:
        return f"({t[:2]}) {t[2:6]}-{t[6:]}"
    return texto
