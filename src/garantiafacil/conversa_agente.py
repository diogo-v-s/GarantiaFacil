"""Chat sem classificador: um agente só decide tudo (experimento da etapa 10).

No chat atual (`conversa.py`), uma chamada ao LLM classifica a pergunta (cadastro, lei ou produto)
e o código escolhe o caminho. Aqui não há classificação: o agente recebe as ferramentas do cadastro
mais `consultar_documentos` (o RAG como ferramenta) e decide sozinho o que usar.

Tem a mesma interface de `Conversa` (`responder`, `produto_atual`, `reiniciar`), então a avaliação
roda os mesmos casos nos dois."""

import os
from dataclasses import dataclass, field
from collections.abc import Callable
from datetime import date, datetime

from garantiafacil.agente import Ferramenta, executar_agente
from garantiafacil.assistencias import ErroDeBusca, buscar_assistencias, localizar_cidade
from garantiafacil.conversa import CONSULTA_GARANTIA_LEGAL, Conversa, Mensagem, trechos_por_resposta
from garantiafacil.ferramentas_cadastro import _achar_categoria, criar_ferramentas, sistema_agente
from garantiafacil.lembretes import Lembretes
from garantiafacil.localizar import localizar_produto
from garantiafacil.modelos import Categoria, Produto
from garantiafacil.painel import formatar_real
from garantiafacil.rag import BaseConhecimento, TrechoEncontrado

FERRAMENTAS_DO_CADASTRO = {
    "listar_produtos", "vencimentos_proximos", "detalhes_produto", "total_gasto", "onde_acionar_garantia",
    "propor_cadastro", "propor_exclusao", "propor_alteracao", "propor_lembrete", "listar_lembretes",
}  # fmt: skip
MENSAGENS_NO_HISTORICO = 6  # as últimas 3 trocas bastam para "e da TV?"


def sistema_conversa(hoje: date | None, produto_atual: Produto | None) -> str:
    assunto = (
        f"\nProduto em discussão: '{produto_atual.nome}'. Perguntas curtas de seguimento, como "
        "'e o prazo?' ou 'e a assistência?', são sobre ele."
        if produto_atual
        else ""
    )
    return (
        sistema_agente(hoje)
        + "\n\nAlém do cadastro, você consulta os documentos: o termo de garantia de cada produto e o "
        "Código de Defesa do Consumidor (CDC). Use consultar_documentos para:\n"
        "- perguntas sobre direitos e prazos da lei (sem informar produto);\n"
        "- o que a garantia, o termo, a cobertura ou a assistência de UM produto cobre ou exige "
        "(informando o produto). Isso vale em lugar da regra acima de que você não sabe a cobertura.\n"
        "Se a pergunta é sobre a cobertura de um produto e o usuário não disse de qual, e não há produto "
        "em discussão, NÃO chame ferramenta: pergunte 'De qual produto você está falando?' e liste os "
        "produtos cadastrados numerados (use listar_produtos para saber quais são).\n"
        "Responda com base só nos trechos devolvidos, em português, em no máximo 5 linhas, sem repetir a "
        "pergunta. Nunca escreva a palavra 'trecho' nem marcadores como [1]. Se a ferramenta devolver "
        "'aviso', siga a instrução dele.\n"
        "Se o usuário perguntar ONDE acionar a garantia, onde levar o produto ou que assistência procurar, "
        "use onde_acionar_garantia com o produto e a cidade dele. Se ele não disse a cidade, pergunte "
        "'Em qual cidade?' sem chamar a ferramenta. Liste só os lugares devolvidos, com nome, endereço, "
        "telefone e distância, exatamente como vieram; onde estiver 'não informado', diga que não "
        "consta no mapa. Nunca invente telefone nem endereço e termine avisando que os dados do mapa "
        "podem estar incompletos.\n"
        "Se o usuário pedir para CADASTRAR um produto, use propor_cadastro. Ela NÃO grava: só prepara o "
        "cadastro para o usuário confirmar nos botões que aparecem abaixo da sua resposta. Faltando nome, "
        "loja, data da compra ou prazo da garantia, pergunte o que falta, sem chamar a ferramenta e sem "
        "inventar. Depois de propor, diga em uma frase que o cadastro está pronto para conferir e confirmar. "
        "Nunca diga que já cadastrou.\n"
        "Para EXCLUIR um produto use propor_exclusao, e para mudar a categoria ou o prazo da garantia "
        "use propor_alteracao. Também só preparam: o usuário confirma nos botões. Se não ficou claro qual "
        "produto, pergunte. Nunca diga que já excluiu ou alterou.\n"
        "Para PROGRAMAR um lembrete ligado a um produto (ex.: 'me lembra de levar a TV na assistência dia "
        "5/11') use propor_lembrete, que também só prepara e o usuário confirma nos botões; precisa do "
        "produto, da data e do texto. Para saber que lembretes existem, use listar_lembretes."
        + assunto
    )


def _ler_data(texto: str) -> date | None:
    """Aceita dd/mm/aaaa (como o usuário escreve) e aaaa-mm-dd; None se não for uma data válida."""
    for formato in ("%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(texto.strip(), formato).date()
        except ValueError:
            continue
    return None


def modo_do_chat() -> str:
    """'agente' (um agente decide tudo) ou 'classificador' (o chat com a pergunta classificada antes).

    Vem de CHAT_MODO no .env. Sem ele: agente com o Claude, que acertou 93% na avaliação sem
    classificar; classificador com o Ollama, onde o agente ainda não foi medido."""
    escolhido = os.getenv("CHAT_MODO", "").strip().lower()
    if escolhido in ("agente", "classificador"):
        return escolhido
    claude = os.getenv("LLM_PROVIDER", "ollama").lower() == "claude"
    return "agente" if claude else "classificador"


def criar_conversa(repositorio, base: BaseConhecimento, llm, hoje: date | None = None):
    """A conversa do app, no modo escolhido (ver `modo_do_chat`)."""
    classe = ConversaAgente if modo_do_chat() == "agente" else Conversa
    return classe(repositorio, base, llm, hoje=hoje)


@dataclass
class AcaoPendente:
    """Algo que o agente propôs mudar (excluir, alterar) e que só acontece se o usuário confirmar."""

    descricao: str  # o que vai acontecer, para mostrar no cartão
    executar: Callable[[], str]  # faz a mudança e devolve a frase do resultado


@dataclass
class _UsoDeDocumentos:
    """O que consultar_documentos fez na pergunta atual (para saber por onde a resposta passou)."""

    trechos: list[TrechoEncontrado] = field(default_factory=list)
    sem_termo: bool = False


class ConversaAgente:
    def __init__(self, repositorio, base: BaseConhecimento, llm, hoje: date | None = None):
        self.repositorio = repositorio
        self.base = base
        self.llm = llm
        self.hoje = hoje
        self.produto_atual: Produto | None = None
        self.historico: list[dict] = []
        self.proposta: Produto | None = None  # cadastro preparado pelo agente, à espera do usuário
        self.acao: AcaoPendente | None = None  # exclusão ou alteração à espera do usuário

    def reiniciar(self) -> None:
        self.produto_atual = None
        self.historico = []
        self.proposta = None
        self.acao = None

    def confirmar_acao(self) -> str:
        """Faz a exclusão ou alteração proposta. Só o código chama isto (botão), nunca o modelo."""
        resultado = self.acao.executar()
        self.acao = None
        self._lembrar("Confirmei a ação.", resultado)
        return resultado

    def cancelar_acao(self) -> None:
        self.acao = None
        self._lembrar("Cancelei a ação.", "Tudo bem, não mudei nada.")

    def confirmar_proposta(self) -> Produto:
        """Grava o cadastro proposto. Só o código chama isto (botão Confirmar), nunca o modelo."""
        produto = self.repositorio.adicionar(self.proposta)
        self.proposta = None
        self.produto_atual = produto
        self._lembrar("Confirmei o cadastro.", f"Cadastrei '{produto.nome}'.")
        return produto

    def cancelar_proposta(self) -> None:
        self.proposta = None
        self._lembrar("Cancelei o cadastro.", "Tudo bem, não cadastrei nada.")

    def _lembrar(self, usuario: str, assistente: str) -> None:
        """Registra uma troca no histórico para o agente saber o que aconteceu fora da conversa."""
        self.historico += [
            {"papel": "usuario", "texto": usuario},
            {"papel": "assistente", "texto": assistente, "chamadas": []},
        ]
        self.historico = self.historico[-MENSAGENS_NO_HISTORICO:]

    def responder(self, mensagem: str) -> Mensagem:
        mensagem = mensagem.strip()
        uso = _UsoDeDocumentos()
        ferramentas = criar_ferramentas(self.repositorio, self.hoje) + [
            self._ferramenta_documentos(uso),
            self._ferramenta_assistencias(),
            self._ferramenta_cadastro(),
            *self._ferramentas_de_acao(),
            *self._ferramentas_de_lembrete(),
        ]

        resposta = executar_agente(
            self.llm,
            mensagem,
            ferramentas,
            sistema_conversa(self.hoje, self.produto_atual),
            historico=self.historico,
        )

        self._atualizar_assunto(resposta)
        self.historico += [
            {"papel": "usuario", "texto": mensagem},
            {"papel": "assistente", "texto": resposta.texto, "chamadas": []},
        ]
        self.historico = self.historico[-MENSAGENS_NO_HISTORICO:]
        return Mensagem(
            texto=resposta.texto,
            trechos=uso.trechos,
            produto=self.produto_atual,
            consultas=resposta.consultas,
            rota=self._rota(resposta, uso),
        )

    # ---------- ferramenta de documentos ----------

    def _ferramenta_documentos(self, uso: _UsoDeDocumentos) -> Ferramenta:
        def consultar_documentos(pergunta: str, produto: str | None = None) -> dict:
            if not produto:
                trechos = self.base.buscar(pergunta, so_gerais=True, k=trechos_por_resposta())
                aviso = None
            else:
                produtos = self.repositorio.listar()
                achados = localizar_produto(produto, produtos)
                if not achados:
                    return {"erro": f"nenhum produto parecido com '{produto}'",
                            "produtos": [p.nome for p in produtos]}  # fmt: skip
                if len(achados) > 1:
                    return {"erro": "mais de um produto parecido", "opcoes": [p.nome for p in achados]}
                escolhido = achados[0]
                self.produto_atual = escolhido
                if self.base.tem_documentos(escolhido.id):
                    trechos = self.base.buscar(
                        f"{escolhido.nome}: {pergunta}", escolhido.id, trechos_por_resposta()
                    )
                    aviso = None
                else:
                    trechos = self._trechos_da_garantia_legal(pergunta)
                    uso.sem_termo = True
                    aviso = (
                        f"'{escolhido.nome}' não tem termo de garantia cadastrado. Comece a resposta com "
                        f"'Não há termo de garantia cadastrado para {escolhido.nome}. Pelo CDC:' e explique "
                        "o que a lei prevê."
                    )
            uso.trechos = trechos
            resultado = {"trechos": [{"fonte": t.fonte, "texto": t.texto} for t in trechos]}
            if aviso:
                resultado["aviso"] = aviso
            return resultado

        return Ferramenta(
            nome="consultar_documentos",
            funcao=consultar_documentos,
            descricao=(
                "Busca nos documentos: o termo de garantia do produto (se informar o produto) e o CDC. "
                "Use para a lei ('quanto tempo tenho para reclamar') e para o que a garantia de um "
                "produto cobre, exclui ou exige (assistência, perda de garantia, o que levar)."
            ),
            parametros={
                "pergunta": {"type": "string", "description": "a dúvida do usuário, com as palavras dele"},
                "produto": {
                    "type": "string",
                    "description": "nome do produto, se a pergunta é sobre a garantia de um produto "
                    "específico; omita para perguntas gerais da lei",
                },
            },
            obrigatorios=("pergunta",),
        )

    # ---------- ferramenta de cadastro (só propõe) ----------

    def _ferramenta_cadastro(self) -> Ferramenta:
        def propor_cadastro(
            nome: str,
            loja: str,
            data_compra: str,
            prazo_garantia_meses: int,
            valor: float | None = None,
            categoria: str | None = None,
        ) -> dict:
            data = _ler_data(data_compra)
            if data is None:
                return {"erro": f"data inválida: '{data_compra}'; peça a data no formato dd/mm/aaaa"}
            if data > (self.hoje or date.today()):
                return {"erro": "a data da compra está no futuro; confirme com o usuário"}
            meses = int(prazo_garantia_meses)
            if meses <= 0:
                return {"erro": "o prazo da garantia deve ser de pelo menos 1 mês"}
            escolhida = None
            if categoria:
                escolhida = _achar_categoria(categoria)
                if escolhida is None:
                    return {"erro": f"categoria inválida; use uma de {[c.value for c in Categoria]}"}
            if any(p.nome.lower() == nome.strip().lower() and p.data_compra == data
                   for p in self.repositorio.listar()):  # fmt: skip
                return {"erro": f"já existe '{nome}' comprado em {data:%d/%m/%Y}; não repita o cadastro"}
            self.acao = None  # só uma coisa pendente por vez
            self.proposta = Produto(
                nome=nome.strip(), loja=loja.strip(), data_compra=data, prazo_garantia_meses=meses,
                valor=float(valor) if valor is not None else None, categoria=escolhida,
            )  # fmt: skip
            return {
                "status": "aguardando a confirmação do usuário nos botões; nada foi gravado",
                "nome": self.proposta.nome,
                "loja": self.proposta.loja,
                "data_da_compra": f"{data:%d/%m/%Y}",
                "prazo_garantia_meses": meses,
                "valor": formatar_real(self.proposta.valor) if self.proposta.valor is not None else "não informado",
                "categoria": escolhida.value if escolhida else "sem categoria",
            }  # fmt: skip

        return Ferramenta(
            nome="propor_cadastro",
            funcao=propor_cadastro,
            descricao=(
                "Prepara o cadastro de um produto novo para o usuário confirmar. NÃO grava nada. Use quando "
                "ele pedir para cadastrar, adicionar ou registrar uma compra. Exige nome, loja, data e prazo."
            ),
            parametros={
                "nome": {"type": "string", "description": "nome do produto, como o usuário disse"},
                "loja": {"type": "string", "description": "loja onde comprou"},
                "data_compra": {"type": "string", "description": "data da compra, dd/mm/aaaa"},
                "prazo_garantia_meses": {"type": "integer", "description": "prazo da garantia em meses"},
                "valor": {"type": "number", "description": "valor pago em reais; omita se não souber"},
                "categoria": {
                    "type": "string",
                    "enum": [c.value for c in Categoria],
                    "description": "categoria; omita se não souber",
                },
            },
            obrigatorios=("nome", "loja", "data_compra", "prazo_garantia_meses"),
        )

    # ---------- ferramentas de excluir e alterar (só propõem) ----------

    def _produto_unico(self, texto: str) -> tuple[Produto | None, dict | None]:
        """O produto que o texto indica, ou o erro (sem achar, ou mais de um) para devolver ao agente."""
        achados = localizar_produto(texto, self.repositorio.listar())
        if not achados:
            return None, {"erro": f"nenhum produto parecido com '{texto}'"}
        if len(achados) > 1:
            return None, {"erro": "mais de um produto parecido", "opcoes": [p.nome for p in achados]}
        return achados[0], None

    def _propor(self, descricao: str, executar: Callable[[], str]) -> dict:
        self.proposta = None  # só uma coisa pendente por vez
        self.acao = AcaoPendente(descricao, executar)
        return {"status": "aguardando a confirmação do usuário nos botões; nada foi alterado",
                "o_que_vai_acontecer": descricao}  # fmt: skip

    def _ferramentas_de_acao(self) -> list[Ferramenta]:
        repositorio = self.repositorio

        def propor_exclusao(produto: str) -> dict:
            escolhido, erro = self._produto_unico(produto)
            if erro:
                return erro

            def excluir() -> str:
                repositorio.excluir(escolhido.id)
                if self.produto_atual and self.produto_atual.id == escolhido.id:
                    self.produto_atual = None
                return f"Excluí '{escolhido.nome}'."

            return self._propor(
                f"Excluir '{escolhido.nome}' (comprado em {escolhido.data_compra:%d/%m/%Y}). "
                "Apaga também a foto e os documentos dele. Não dá para desfazer.",
                excluir,
            )

        def propor_alteracao(
            produto: str, categoria: str | None = None, prazo_garantia_meses: int | None = None
        ) -> dict:
            escolhido, erro = self._produto_unico(produto)
            if erro:
                return erro
            if not categoria and prazo_garantia_meses is None:
                return {"erro": "diga o que mudar: a categoria ou o prazo da garantia"}
            nova_categoria = None
            if categoria:
                nova_categoria = _achar_categoria(categoria)
                if nova_categoria is None:
                    return {"erro": f"categoria inválida; use uma de {[c.value for c in Categoria]}"}
            if prazo_garantia_meses is not None and int(prazo_garantia_meses) <= 0:
                return {"erro": "o prazo da garantia deve ser de pelo menos 1 mês"}

            mudancas = []
            if nova_categoria:
                antes = escolhido.categoria.value if escolhido.categoria else "sem categoria"
                mudancas.append(f"categoria de {antes} para {nova_categoria.value}")
            if prazo_garantia_meses is not None:
                mudancas.append(f"prazo da garantia de {escolhido.prazo_garantia_meses} para {int(prazo_garantia_meses)} meses")

            def alterar() -> str:
                if nova_categoria:
                    repositorio.atualizar_categoria(escolhido.id, nova_categoria)
                if prazo_garantia_meses is not None:
                    repositorio.atualizar_prazo(escolhido.id, int(prazo_garantia_meses))
                return f"Alterei '{escolhido.nome}': {'; '.join(mudancas)}."

            return self._propor(f"Em '{escolhido.nome}': {'; '.join(mudancas)}.", alterar)

        return [
            Ferramenta(
                nome="propor_exclusao",
                funcao=propor_exclusao,
                descricao=(
                    "Prepara a exclusão de UM produto para o usuário confirmar. NÃO exclui nada. Use quando "
                    "ele pedir para apagar, excluir ou remover um produto."
                ),
                parametros={"produto": {"type": "string", "description": "nome ou parte do nome do produto"}},
                obrigatorios=("produto",),
            ),
            Ferramenta(
                nome="propor_alteracao",
                funcao=propor_alteracao,
                descricao=(
                    "Prepara a mudança da categoria e/ou do prazo da garantia (em meses) de UM produto, para o "
                    "usuário confirmar. NÃO altera nada. Só estes dois campos podem ser mudados."
                ),
                parametros={
                    "produto": {"type": "string", "description": "nome ou parte do nome do produto"},
                    "categoria": {
                        "type": "string",
                        "enum": [c.value for c in Categoria],
                        "description": "nova categoria; omita para não mudar",
                    },
                    "prazo_garantia_meses": {
                        "type": "integer",
                        "description": "novo prazo em meses; omita para não mudar",
                    },
                },
                obrigatorios=("produto",),
            ),
        ]

    # ---------- lembretes ----------

    def _ferramentas_de_lembrete(self) -> list[Ferramenta]:
        lembretes = Lembretes(self.repositorio.conexao, self.repositorio.usuario_id)
        hoje = self.hoje or date.today()

        def propor_lembrete(produto: str, data: str, texto: str) -> dict:
            escolhido, erro = self._produto_unico(produto)
            if erro:
                return erro
            quando = _ler_data(data)
            if quando is None:
                return {"erro": f"data inválida: '{data}'; peça a data no formato dd/mm/aaaa"}
            if quando < hoje:
                return {"erro": "essa data já passou; peça uma data de hoje em diante"}
            if not texto.strip():
                return {"erro": "diga o que lembrar"}

            def criar() -> str:
                lembretes.adicionar(escolhido.id, quando, texto)
                return f"Lembrete criado: {texto.strip()} ({escolhido.nome}, {quando:%d/%m/%Y})."

            return self._propor(
                f"Lembrar em {quando:%d/%m/%Y}, sobre '{escolhido.nome}': {texto.strip()}.", criar
            )

        def listar_lembretes() -> dict:
            nomes = {p.id: p.nome for p in self.repositorio.listar()}
            pendentes = [
                {"produto": nomes[l.produto_id], "data": f"{l.data:%d/%m/%Y}", "texto": l.texto}
                for l in lembretes.pendentes()
                if l.produto_id in nomes
            ]
            return {"total": len(pendentes), "lembretes": pendentes}

        return [
            Ferramenta(
                nome="propor_lembrete",
                funcao=propor_lembrete,
                descricao=(
                    "Prepara um lembrete programado para um produto, para o usuário confirmar. NÃO grava "
                    "nada. Use para 'me lembra de levar a TV na assistência dia 5/11'. Exige produto, data "
                    "(dd/mm/aaaa, de hoje em diante: hoje vale) e o texto."
                ),
                parametros={
                    "produto": {"type": "string", "description": "nome ou parte do nome do produto"},
                    "data": {"type": "string", "description": "dia do lembrete, dd/mm/aaaa"},
                    "texto": {"type": "string", "description": "o que lembrar, em poucas palavras"},
                },
                obrigatorios=("produto", "data", "texto"),
            ),
            Ferramenta(
                nome="listar_lembretes",
                funcao=listar_lembretes,
                descricao="Lista os lembretes programados que ainda não foram concluídos, com produto e data.",
                parametros={},
            ),
        ]

    # ---------- ferramenta de assistências ----------

    def _ferramenta_assistencias(self) -> Ferramenta:
        def onde_acionar_garantia(produto: str, cidade: str, marca: str | None = None) -> dict:
            achados = localizar_produto(produto, self.repositorio.listar())
            if len(achados) != 1:
                return {"erro": "produto não identificado", "opcoes": [p.nome for p in achados]}
            escolhido = achados[0]
            self.produto_atual = escolhido
            try:
                local = localizar_cidade(cidade)
                if local is None:
                    return {"erro": f"não encontrei a cidade '{cidade}'; peça cidade e estado"}
                lugares = buscar_assistencias(local, escolhido.categoria, marca)
            except ErroDeBusca as erro:
                return {"erro": str(erro)}
            return {
                "produto": escolhido.nome,
                "perto_de": local.nome,
                "total": len(lugares),
                "lugares": [
                    {"nome": a.nome, "endereco": a.endereco, "telefone": a.telefone,
                     "distancia_km": a.distancia_km, "marca_confere": a.marca_confere}
                    for a in lugares
                ],  # fmt: skip
            }

        return Ferramenta(
            nome="onde_acionar_garantia",
            funcao=onde_acionar_garantia,
            descricao=(
                "Procura no mapa assistências e lojas perto de uma cidade que podem atender o produto. "
                "Use para 'onde aciono a garantia', 'onde levo a TV', 'tem assistência perto de mim'. "
                "Demora até 1 minuto na primeira busca de uma cidade."
            ),
            parametros={
                "produto": {"type": "string", "description": "nome do produto cadastrado"},
                "cidade": {"type": "string", "description": "cidade (e estado) do usuário"},
                "marca": {"type": "string", "description": "marca do produto, se souber; omita se não"},
            },
            obrigatorios=("produto", "cidade"),
        )

    def _trechos_da_garantia_legal(self, pergunta: str) -> list[TrechoEncontrado]:
        """Produto sem termo: busca a garantia legal direto, além da pergunta (mesma lógica do chat atual)."""
        trechos = self.base.buscar(CONSULTA_GARANTIA_LEGAL, so_gerais=True, k=2)
        for trecho in self.base.buscar(pergunta, so_gerais=True, k=2):
            if len(trechos) < trechos_por_resposta() and all(t.texto != trecho.texto for t in trechos):
                trechos.append(trecho)
        return trechos

    # ---------- o que a pergunta usou ----------

    def _atualizar_assunto(self, resposta) -> None:
        """Se uma ferramenta do cadastro tratou de um produto só, ele vira o assunto da conversa."""
        produtos = self.repositorio.listar()
        for consulta in resposta.consultas:
            if consulta.nome == "detalhes_produto":
                achados = localizar_produto(str(consulta.argumentos.get("nome", "")), produtos)
                if len(achados) == 1:
                    self.produto_atual = achados[0]
        if not any(c.nome == "detalhes_produto" for c in resposta.consultas):
            citados = [p for p in produtos if p.nome.lower() in resposta.texto.lower()]
            if len(citados) == 1 and any(c.nome in FERRAMENTAS_DO_CADASTRO for c in resposta.consultas):
                self.produto_atual = citados[0]

    @staticmethod
    def _rota(resposta, uso: _UsoDeDocumentos) -> str:
        """Equivale às rotas do chat com classificador, para a avaliação comparar os dois."""
        if not uso.trechos and resposta.texto.startswith(("De qual produto", "Encontrei mais de um")):
            return "esclarecimento"  # pode ter listado os produtos antes de perguntar
        if any(c.nome in FERRAMENTAS_DO_CADASTRO for c in resposta.consultas):
            return "agente"
        if uso.trechos:
            if uso.sem_termo:
                return "sem_termo"
            return "documentos_produto" if any(t.produto_id is not None for t in uso.trechos) else "cdc"
        return "esclarecimento" if "?" in resposta.texto else "outra"
