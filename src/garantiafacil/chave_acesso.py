"""Chave de acesso da NF-e / NFC-e: 44 dígitos com estrutura fixa e dígito verificador.

Posições: UF (2) | AAMM (4) | CNPJ do emitente (14) | modelo (2) | série (3) | número (9) |
tipo de emissão (1) | código numérico (8) | dígito verificador (1).
"""

import re
from dataclasses import dataclass

_PADRAO_44_DIGITOS = re.compile(r"(?<!\d)(\d{44})(?!\d)")


@dataclass(frozen=True)
class ChaveAcesso:
    chave: str
    uf: str
    ano: int
    mes: int
    cnpj: str
    modelo: str
    serie: str
    numero: str


def calcular_dv(base: str) -> int:
    """Dígito verificador (módulo 11) dos 43 primeiros dígitos.

    Pesos de 2 a 9, repetindo, da direita para a esquerda."""
    soma = 0
    peso = 2
    for digito in reversed(base):
        soma += int(digito) * peso
        peso = 2 if peso == 9 else peso + 1
    resto = soma % 11
    return 0 if resto < 2 else 11 - resto


def buscar_chave(texto: str) -> str | None:
    """Procura 44 dígitos seguidos em um texto (por exemplo, a URL do QR code).
    Aceita espaços entre os dígitos, como a chave aparece impressa na nota."""
    sem_espacos = re.sub(r"(?<=\d)[ .]+(?=\d)", "", texto)
    achado = _PADRAO_44_DIGITOS.search(sem_espacos)
    return achado.group(1) if achado else None


def interpretar(chave: str | None) -> ChaveAcesso | None:
    """Valida e decompõe a chave. Devolve None se não tiver 44 dígitos, se o dígito
    verificador não bater ou se o mês for impossível (sinal de leitura errada)."""
    if not chave or not re.fullmatch(r"\d{44}", chave):
        return None
    if calcular_dv(chave[:43]) != int(chave[43]):
        return None

    mes = int(chave[4:6])
    if not 1 <= mes <= 12:
        return None

    return ChaveAcesso(
        chave=chave,
        uf=chave[0:2],
        ano=2000 + int(chave[2:4]),
        mes=mes,
        cnpj=chave[6:20],
        modelo=chave[20:22],
        serie=chave[22:25],
        numero=chave[25:34],
    )
