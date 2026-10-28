"""Pipeline híbrido de leitura de nota fiscal: regras onde há dado exato, IA no resto.

1. A IA (visão) lê produto, loja, data e valor da foto.
2. Se achamos a chave de acesso (QR code da foto), ela corrige o que dá para provar:
   o CNPJ vira o nome da loja e o mês/ano substituem os da IA se divergirem.
3. Os avisos dizem ao usuário o que foi confirmado e o que precisa conferir.
"""

import calendar
from dataclasses import dataclass, field
from datetime import date

from garantiafacil.chave_acesso import ChaveAcesso, interpretar
from garantiafacil.consulta_cnpj import buscar_razao_social
from garantiafacil.extracao import extrair_dados_nota, ler_chave_impressa
from garantiafacil.leitor_qr import ler_chave_do_qr


@dataclass
class ResultadoNota:
    loja: str
    produto: str
    data_compra: date | None
    valor: float
    avisos: list[str] = field(default_factory=list)


def reconciliar_data(data_ia: date | None, chave: ChaveAcesso) -> tuple[date, str | None]:
    """Mês e ano da chave valem mais que os da IA. O dia só vem da IA."""
    if data_ia and (data_ia.year, data_ia.month) == (chave.ano, chave.mes):
        return data_ia, None

    ultimo_dia = calendar.monthrange(chave.ano, chave.mes)[1]
    dia = data_ia.day if data_ia and data_ia.day <= ultimo_dia else 1
    aviso = (
        f"Mês e ano ({chave.mes:02d}/{chave.ano}) vêm da chave de acesso; "
        "o dia não pôde ser confirmado. Confira a data."
    )
    return date(chave.ano, chave.mes, dia), aviso


def ler_nota(
    imagem: bytes,
    tipo_midia: str = "image/jpeg",
    llm=None,
    ler_chave=ler_chave_do_qr,
    ler_impressa=ler_chave_impressa,
    consultar_cnpj=buscar_razao_social,
) -> ResultadoNota:
    """As dependências externas (`llm`, `ler_chave`, `ler_impressa`, `consultar_cnpj`)
    podem ser trocadas nos testes."""
    ia = extrair_dados_nota(imagem, tipo_midia, llm)
    resultado = ResultadoNota(
        loja=ia.loja, produto=ia.produto, data_compra=ia.data(), valor=ia.valor
    )

    # Primeiro o QR code (exato e rápido); se falhar, a IA lê a chave impressa. Nos dois casos
    # o dígito verificador decide se a leitura serve.
    chave = interpretar(ler_chave(imagem))
    origem_chave = "do QR code"
    if chave is None:
        chave = interpretar(ler_impressa(imagem, tipo_midia, llm))
        origem_chave = "do texto impresso (validada pelo dígito verificador)"

    if chave is None:
        resultado.avisos.append(
            "Chave de acesso não encontrada (QR code ilegível ou cortado e a leitura do texto "
            "falhou): todos os dados vêm só da IA. Confira com atenção."
        )
        return resultado
    resultado.avisos.append(f"Chave de acesso lida {origem_chave}.")

    razao_social = consultar_cnpj(chave.cnpj)
    if razao_social:
        resultado.loja = razao_social
        resultado.avisos.append("Loja confirmada pelo CNPJ da chave de acesso.")
    else:
        resultado.avisos.append(
            "Chave de acesso lida, mas não consegui consultar o nome da loja pelo CNPJ; "
            "mantive o nome lido pela IA."
        )

    resultado.data_compra, aviso_data = reconciliar_data(resultado.data_compra, chave)
    resultado.avisos.append(aviso_data or "Mês e ano da data conferem com a chave de acesso.")
    return resultado
