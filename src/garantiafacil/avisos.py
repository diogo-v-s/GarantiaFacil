"""Avisos de vencimento: quais garantias estão perto do fim, conforme a antecedência que o
usuário escolheu (por exemplo, 30 e 7 dias antes).

São funções puras (recebem os produtos e a data de hoje), sem Streamlit nem banco."""

from dataclasses import dataclass
from datetime import date

from garantiafacil.garantia import data_vencimento, dias_restantes
from garantiafacil.modelos import Produto

DIAS_PADRAO = (30, 7)  # de quem nunca mexeu nas preferências
OPCOES_DIAS = (90, 60, 45, 30, 15, 7, 3, 1)  # o que a tela de preferências oferece
LIMITE_DIAS = 365


def normalizar_dias(dias) -> tuple[int, ...]:
    """Sem repetição, só de 1 a 365, do maior para o menor: (7, 30, 7) vira (30, 7)."""
    validos = {int(d) for d in dias if 1 <= int(d) <= LIMITE_DIAS}
    return tuple(sorted(validos, reverse=True))


def dias_para_texto(dias) -> str:
    """Como vai para o banco: '30,7'. Texto vazio quer dizer 'não avisar'."""
    return ",".join(str(d) for d in normalizar_dias(dias))


def texto_para_dias(texto: str | None) -> tuple[int, ...]:
    """O inverso. None (nunca escolheu) vale o padrão; '' (escolheu não receber) vale nenhum."""
    if texto is None:
        return DIAS_PADRAO
    return normalizar_dias(p for p in texto.split(",") if p.strip().isdigit())


@dataclass(frozen=True)
class Aviso:
    produto: Produto
    vencimento: date
    dias: int  # quantos dias faltam (0 = vence hoje)
    urgente: bool  # dentro da menor antecedência escolhida


def avisos_de_vencimento(produtos: list[Produto], hoje: date, dias_aviso) -> list[Aviso]:
    """As garantias que vencem dentro da maior antecedência escolhida, da mais próxima à mais
    distante. É 'urgente' a que já entrou na menor antecedência (só existe urgência quando o usuário
    escolheu mais de uma: com uma só, todas teriam a mesma urgência)."""
    dias_aviso = normalizar_dias(dias_aviso)
    if not dias_aviso:
        return []
    janela, urgencia = max(dias_aviso), min(dias_aviso)
    avisos = []
    for produto in produtos:
        dias = dias_restantes(produto, hoje)
        if 0 <= dias <= janela:
            urgente = len(dias_aviso) > 1 and dias <= urgencia
            avisos.append(Aviso(produto, data_vencimento(produto), dias, urgente))
    return sorted(avisos, key=lambda aviso: aviso.dias)


def quando(dias: int) -> str:
    if dias == 0:
        return "vence hoje"
    if dias == 1:
        return "vence amanhã"
    return f"faltam {dias} dias"
