"""Avaliação do chat: roda casos fixos de pergunta e mede quanto o chat acerta.

Ideia central: em vez de "parece melhor", ter um número. Cada `Caso` diz o que se espera
(por onde a pergunta deve passar, qual ferramenta, o que a resposta deve ou não conter).
`avaliar_caso` roda a conversa e confere cada expectativa; `resumir` agrega as notas.

Mede o COMPORTAMENTO do chat (roteamento e conteúdo), não a beleza do texto.
"""

import statistics
import time
import unicodedata
from dataclasses import dataclass, field


@dataclass
class Caso:
    id: str
    tipo: str  # grupo do relatório: cadastro, lei, termo, sem_termo, esclarecimento, contexto...
    mensagens: list[str]  # a conversa; a nota vale para a resposta à ÚLTIMA mensagem
    rota: str | tuple[str, ...]  # por onde deve passar (uma, ou várias aceitas)
    ferramenta: str | tuple[str, ...] | None = None  # ferramenta(s) aceitas do agente
    argumentos: dict | None = None  # subconjunto esperado dos argumentos da ferramenta
    contem: tuple[str, ...] = ()  # todas devem aparecer na resposta
    contem_algum: tuple[str, ...] = ()  # pelo menos uma deve aparecer
    nao_contem: tuple[str, ...] = ()  # nenhuma pode aparecer (ex.: a frase de uma alucinação)
    produto: str | None = None  # trecho do nome do produto que deve ser o assunto ao final
    opcional: bool = False  # não entra na nota geral (ex.: depende do exercício total_gasto)


@dataclass
class Resultado:
    caso: str
    tipo: str
    passou: bool
    falhas: list[str]
    rota: str
    ferramentas: list[tuple[str, dict]]
    texto: str
    segundos: float
    opcional: bool = False
    produto: str | None = None


ROTAS = ("agente", "cdc", "documentos_produto", "sem_termo", "esclarecimento", "outra")

_PREFIXOS_ESCLARECIMENTO = ("De qual produto", "Encontrei mais de um", "Não achei isso nas leis")


def rota_da(mensagem) -> str:
    """Por onde a resposta passou, deduzido do que ela devolveu.

    agente: consultou o cadastro com ferramentas; esclarecimento: perguntou de qual produto;
    sem_termo: produto sem termo, respondeu com o CDC; documentos_produto: usou o termo do
    produto; cdc: respondeu só com as leis."""
    if mensagem.rota:
        return mensagem.rota
    if mensagem.consultas:
        return "agente"
    texto = mensagem.texto
    if texto.startswith(_PREFIXOS_ESCLARECIMENTO):
        return "esclarecimento"
    if texto.startswith("Não há termo de garantia cadastrado"):
        return "sem_termo"
    if any(t.produto_id is not None for t in mensagem.trechos):
        return "documentos_produto"
    if mensagem.trechos:
        return "cdc"
    return "outra"


def _normalizar(texto: str) -> str:
    """Minúsculas e sem acento, para comparar texto sem se importar com 'não' x 'nao'."""
    decomposto = unicodedata.normalize("NFD", texto.lower())
    return "".join(c for c in decomposto if unicodedata.category(c) != "Mn")


def _como_tupla(valor) -> tuple:
    if valor is None:
        return ()
    return (valor,) if isinstance(valor, str) else tuple(valor)


def _argumentos_batem(esperados: dict, obtidos: dict) -> bool:
    return all(_normalizar(str(obtidos.get(k))) == _normalizar(str(v)) for k, v in esperados.items())


def conferir(caso: Caso, mensagem, produto_atual) -> list[str]:
    """Lista de falhas (vazia = o caso passou)."""
    falhas = []

    rota = rota_da(mensagem)
    aceitas = _como_tupla(caso.rota)
    if rota not in aceitas:
        falhas.append(f"rota: esperava {' ou '.join(aceitas)}, foi {rota}")

    if caso.ferramenta:
        aceitas_f = _como_tupla(caso.ferramenta)
        usadas = [c for c in mensagem.consultas if c.nome in aceitas_f]
        if not usadas:
            nomes = [c.nome for c in mensagem.consultas] or ["nenhuma"]
            falhas.append(f"ferramenta: esperava {' ou '.join(aceitas_f)}, usou {', '.join(nomes)}")
        elif caso.argumentos and not any(_argumentos_batem(caso.argumentos, c.argumentos) for c in usadas):
            falhas.append(f"argumentos: esperava {caso.argumentos}, usou {[c.argumentos for c in usadas]}")

    texto = _normalizar(mensagem.texto)
    for trecho in caso.contem:
        if _normalizar(trecho) not in texto:
            falhas.append(f"faltou na resposta: {trecho!r}")
    if caso.contem_algum and not any(_normalizar(t) in texto for t in caso.contem_algum):
        falhas.append(f"faltou qualquer um de: {list(caso.contem_algum)}")
    for trecho in caso.nao_contem:
        if _normalizar(trecho) in texto:
            falhas.append(f"não devia aparecer: {trecho!r}")

    if mensagem.citacoes_invalidas:
        falhas.append(f"citação inventada: {mensagem.citacoes_invalidas}")

    if caso.produto:
        nome = produto_atual.nome if produto_atual else ""
        if _normalizar(caso.produto) not in _normalizar(nome):
            falhas.append(f"assunto: esperava {caso.produto!r}, ficou {nome or 'nenhum'!r}")

    return falhas


def avaliar_caso(caso: Caso, criar_conversa) -> Resultado:
    """Roda a conversa do caso do zero e confere a resposta à última mensagem.

    `criar_conversa` devolve uma `Conversa` nova (sem memória de outros casos)."""
    conversa = criar_conversa()
    inicio = time.perf_counter()
    mensagem = None
    erro = None
    try:
        for fala in caso.mensagens:
            mensagem = conversa.responder(fala)
    except Exception as e:  # modelo fora do ar, JSON inválido... conta como falha, não derruba tudo
        erro = f"{type(e).__name__}: {e}"
    segundos = time.perf_counter() - inicio

    if erro or mensagem is None:
        return Resultado(caso.id, caso.tipo, False, [f"erro: {erro}"], "erro", [], "", segundos, caso.opcional)

    falhas = conferir(caso, mensagem, conversa.produto_atual)
    return Resultado(
        caso=caso.id,
        tipo=caso.tipo,
        passou=not falhas,
        falhas=falhas,
        rota=rota_da(mensagem),
        ferramentas=[(c.nome, c.argumentos) for c in mensagem.consultas],
        texto=mensagem.texto,
        segundos=segundos,
        opcional=caso.opcional,
        produto=conversa.produto_atual.nome if conversa.produto_atual else None,
    )


@dataclass
class Resumo:
    total: int
    acertos: int
    por_tipo: dict[str, tuple[int, int]]  # tipo -> (acertos, total)
    tempo_medio: float
    tempo_maximo: float
    falhas: list[Resultado] = field(default_factory=list)
    opcionais: list[Resultado] = field(default_factory=list)

    @property
    def nota(self) -> float:
        return self.acertos / self.total if self.total else 0.0


def resumir(resultados: list[Resultado]) -> Resumo:
    obrigatorios = [r for r in resultados if not r.opcional]
    por_tipo: dict[str, tuple[int, int]] = {}
    for r in obrigatorios:
        acertos, total = por_tipo.get(r.tipo, (0, 0))
        por_tipo[r.tipo] = (acertos + r.passou, total + 1)
    tempos = [r.segundos for r in obrigatorios] or [0.0]
    return Resumo(
        total=len(obrigatorios),
        acertos=sum(r.passou for r in obrigatorios),
        por_tipo=por_tipo,
        tempo_medio=statistics.mean(tempos),
        tempo_maximo=max(tempos),
        falhas=[r for r in obrigatorios if not r.passou],
        opcionais=[r for r in resultados if r.opcional],
    )


def formatar(resumo: Resumo) -> str:
    linhas = [
        f"Nota: {resumo.acertos}/{resumo.total} ({resumo.nota:.0%})",
        f"Tempo por caso: média {resumo.tempo_medio:.0f}s, máximo {resumo.tempo_maximo:.0f}s",
        "",
        "Por tipo:",
    ]
    for tipo, (acertos, total) in sorted(resumo.por_tipo.items()):
        linhas.append(f"  {tipo:<16} {acertos}/{total}")
    if resumo.falhas:
        linhas += ["", "Falhas:"]
        for r in resumo.falhas:
            linhas.append(f"  [{r.caso}] " + "; ".join(r.falhas))
    if resumo.opcionais:
        linhas += ["", "Opcionais (fora da nota):"]
        for r in resumo.opcionais:
            linhas.append(f"  [{r.caso}] {'ok' if r.passou else 'falhou: ' + '; '.join(r.falhas)}")
    return "\n".join(linhas)
