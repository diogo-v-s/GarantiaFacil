"""O que o sininho mostra: avisos de vencimento (automáticos) e lembretes programados (que já chegaram).

São funções puras (recebem os dados e a data de hoje), sem Streamlit nem banco."""

from dataclasses import dataclass
from datetime import date

from garantiafacil.avisos import Aviso, avisos_de_vencimento, normalizar_dias
from garantiafacil.lembretes import Lembrete
from garantiafacil.modelos import Produto


@dataclass(frozen=True)
class Notificacao:
    tipo: str  # "vencimento" ou "lembrete"
    texto: str
    urgente: bool
    lembrete_id: int | None = None  # só nos lembretes: o "Lido" conclui o lembrete
    produto_id: int | None = None  # só nos avisos de vencimento
    chave: str | None = None  # só nos avisos: identifica o aviso para marcá-lo como lido


def _vence(dias: int) -> str:
    if dias == 0:
        return "vence hoje"
    if dias == 1:
        return "vence amanhã"
    return f"vence em {dias} dias"


def _quando_do_lembrete(data: date, hoje: date) -> str:
    return "hoje" if data == hoje else f"{data:%d/%m}, atrasado"


def chave_do_aviso(aviso: Aviso, dias_aviso) -> str:
    """Identifica o aviso por produto, data de vencimento e faixa de antecedência. Quem leu o aviso de
    30 dias volta a ser avisado ao entrar na faixa de 7, e também se a data de vencimento mudar."""
    faixa = min(d for d in normalizar_dias(dias_aviso) if aviso.dias <= d)
    return f"vencimento:{aviso.produto.id}:{aviso.vencimento.isoformat()}:{faixa}"


def montar_notificacoes(
    produtos: list[Produto],
    lembretes: list[Lembrete],
    hoje: date,
    dias_aviso,
    lidas: frozenset[str] | set[str] = frozenset(),
) -> list[Notificacao]:
    """Lembretes cuja data chegou (os atrasados primeiro, pois ainda não foram resolvidos) e depois as
    garantias perto do fim, da mais próxima à mais distante. Lembrete de data futura ainda não aparece,
    e os avisos cuja chave está em `lidas` ficam de fora."""
    por_id = {p.id: p for p in produtos}
    notificacoes = [
        Notificacao(
            "lembrete",
            f"Lembrete de {por_id[l.produto_id].nome}: {l.texto} (marcado para {_quando_do_lembrete(l.data, hoje)}).",
            urgente=True,
            lembrete_id=l.id,
        )
        for l in sorted(lembretes, key=lambda l: l.data)
        if l.data <= hoje and l.produto_id in por_id
    ]
    for aviso in avisos_de_vencimento(produtos, hoje, dias_aviso):
        chave = chave_do_aviso(aviso, dias_aviso)
        if chave in lidas:
            continue
        notificacoes.append(
            Notificacao(
                "vencimento",
                f"A garantia de {aviso.produto.nome} {_vence(aviso.dias)}.",
                urgente=aviso.urgente,
                produto_id=aviso.produto.id,
                chave=chave,
            )
        )
    return notificacoes
