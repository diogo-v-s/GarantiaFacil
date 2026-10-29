"""Interface web (Streamlit).

Rode com: uv run streamlit run src/garantiafacil/app.py
"""

import html
import threading
from datetime import date
from pathlib import Path

import streamlit as st

from garantiafacil.conversa import Conversa, Mensagem
from garantiafacil.db import conectar
from garantiafacil.documentos import extrair_paginas
from garantiafacil.garantia import (
    contar_por_status,
    data_vencimento,
    dias_restantes,
    status_garantia,
)
from garantiafacil.llm import criar_llm
from garantiafacil.imagens import imagem_padrao
from garantiafacil.modelos import Categoria, Produto, TipoDocumento
from garantiafacil.pipeline_nota import ler_nota
from garantiafacil.rag import BaseConhecimento, limpar_citacoes
from garantiafacil.repositorio import Repositorio

EXTENSOES_IMAGEM = {".png", ".jpg", ".jpeg", ".webp"}

CAMINHO_CDC = Path(__file__).resolve().parents[2] / "docs" / "conhecimento" / "cdc.txt"
FONTE_CDC = CAMINHO_CDC.name

NOME_APP = "TáGuardado"
PASTA_ASSETS = Path(__file__).resolve().parent / "assets"
LOGO = PASTA_ASSETS / "logo.png"
ICONE = PASTA_ASSETS / "icone.png"  # ícone da aba do navegador

PAGINA_LISTA = "📦  Meus produtos"
PAGINA_CADASTRO = "➕  Cadastrar"
PAGINA_PERGUNTAS = "💬  Perguntas"
PAGINAS = [PAGINA_LISTA, PAGINA_CADASTRO, PAGINA_PERGUNTAS]

# status -> (classe de cor, título, texto antes da data)
VISUAL_STATUS = {
    "vigente": ("ok", "🛡️ Em garantia", "Vence em"),
    "vence_em_breve": ("aviso", "⏳ Vence em breve", "Vence em"),
    "vencida": ("vencida", "⛔ Garantia vencida", "Venceu em"),
}

FILTROS_STATUS = ["todos", "vigente", "vence_em_breve", "vencida"]
ROTULO_FILTRO = {
    "todos": "Todos",
    "vigente": "Dentro da garantia",
    "vence_em_breve": "Vencendo em breve",
    "vencida": "Garantia vencida",
}
ORDENACOES = ["Data da compra", "Vencimento", "Nome"]
TODAS_CATEGORIAS = "Todas as categorias"

ESTILO = """
<style>
/* sidebar */
[data-testid="stSidebar"] { border-right: 1px solid #eceffa; }
[data-testid="stSidebar"] [role="radiogroup"] { gap: 4px; }
[data-testid="stSidebar"] [role="radiogroup"] label {
    padding: 10px 14px; border-radius: 10px; width: 100%; cursor: pointer;
}
[data-testid="stSidebar"] [role="radiogroup"] label:hover { background: #f1f4ff; }
[data-testid="stSidebar"] [role="radiogroup"] label:has(input:checked) {
    background: #eaefff; color: #2f45f5; font-weight: 600;
}
[data-testid="stSidebar"] [role="radiogroup"] label > div > div:first-child:not(:has(p)) {
    display: none;  /* bolinha do radio */
}
[data-testid="stSidebar"] [data-testid="stImage"] {  /* logo */
    display: flex; justify-content: center; width: 100% !important; padding: 0 0 14px 0;
}
[data-testid="stSidebar"] [data-testid="stFullScreenFrame"] {
    display: flex; justify-content: center;
}
[data-testid="stSidebarUserContent"] { padding-top: 1.5rem; }
[data-testid="stSidebar"] [data-testid="stImage"] img { margin: 0 auto; }

/* títulos */
.titulo-pagina { font-size: 2rem !important; font-weight: 800; margin: 0; line-height: 1.2; }
.subtitulo-pagina { color: #5b6080; margin: 2px 0 18px 0; }

/* cartões de resumo */
.cartao {
    display: flex; align-items: center; gap: 14px; background: #fff; border: 1px solid #eceffa;
    border-radius: 16px; padding: 18px 20px; box-shadow: 0 2px 10px rgba(47, 69, 245, 0.04);
}
.cartao .icone {
    width: 52px; height: 52px; border-radius: 14px; display: flex; align-items: center;
    justify-content: center; font-size: 1.5rem; flex: none;
}
.cartao .numero { font-size: 1.7rem; font-weight: 800; line-height: 1.1; }
.cartao .legenda { color: #5b6080; font-size: 0.9rem; }
.icone.azul { background: #eaf0ff; } .icone.verde { background: #e6f7ee; }
.icone.amarelo { background: #fff3dc; } .icone.vermelho { background: #fde8ea; }

/* linha do produto */
[data-testid="stVerticalBlockBorderWrapper"] {
    background: #fff; border-radius: 14px; border-color: #eceffa;
}
/* miniatura (foto do comprovante) quadrada, só na 1ª coluna da linha do produto */
[data-testid="stColumn"]:first-child [data-testid="stImage"] img {
    width: 56px; height: 56px; object-fit: cover; border-radius: 12px;
}
.miniatura {
    width: 56px; height: 56px; border-radius: 12px; background: #f1f4ff; display: flex;
    align-items: center; justify-content: center; font-size: 1.7rem;
}
.nome-produto { font-weight: 700; font-size: 1.02rem; }
.loja-produto { color: #5b6080; font-size: 0.9rem; }
.selo {
    display: inline-block; padding: 4px 12px; border-radius: 999px; font-size: 0.82rem;
    font-weight: 600; background: #eaefff; color: #2f45f5;
}
.celula .rotulo { display: block; color: #7a7fa0; font-size: 0.8rem; }
.celula .valor { font-weight: 600; }
.status { border-radius: 12px; padding: 8px 14px; }
.status .titulo { font-weight: 700; display: block; }
.status .data { font-size: 0.82rem; opacity: 0.8; }
.status.ok { background: #e6f7ee; color: #17784a; }
.status.aviso { background: #fff3dc; color: #a35f00; }
.status.vencida { background: #fde8ea; color: #bf2236; }
</style>
"""


@st.cache_resource  # cria a conexão uma vez só e reaproveita entre as interações
def obter_repositorio() -> Repositorio:
    return Repositorio(conectar(check_same_thread=False))


def formatar_data(d: date) -> str:
    return d.strftime("%d/%m/%Y")


def formatar_mes(d: date) -> str:
    return d.strftime("%m/%Y")


def _ir_para(pagina: str):
    st.session_state["pagina"] = pagina


def cabecalho(titulo: str, subtitulo: str):
    st.markdown(
        f'<div class="titulo-pagina">{html.escape(titulo)}</div>'
        f'<div class="subtitulo-pagina">{html.escape(subtitulo)}</div>',
        unsafe_allow_html=True,
    )


def tela_cadastro(repo: Repositorio):
    cabecalho("Cadastrar produto", "Registre a compra e acompanhe o prazo da garantia.")

    # O uploader fica fora do formulário para o botão "Ler nota" funcionar antes de salvar.
    # A chave muda a cada cadastro salvo, o que "limpa" o uploader.
    chave_upload = st.session_state.setdefault("upload_n", 0)
    arquivos = st.file_uploader(
        "Nota fiscal ou cupom (foto ou PDF)",
        type=["pdf", "png", "jpg", "jpeg", "webp"],
        accept_multiple_files=True,
        key=f"upload_{chave_upload}",
    )

    imagens = [a for a in arquivos if Path(a.name).suffix.lower() in EXTENSOES_IMAGEM]
    if imagens and st.button("📷 Ler nota fiscal com IA"):
        with st.spinner("Lendo a nota (no Ollama local pode levar um minuto)..."):
            try:
                st.session_state["sugestao"] = ler_nota(
                    imagens[0].getvalue(), tipo_midia=imagens[0].type
                )
            except Exception as erro:  # modelo fora do ar, imagem ruim, JSON inválido...
                st.error(f"Não consegui ler a nota: {erro}")

    sugestao = st.session_state.get("sugestao")
    if sugestao:
        st.info("Dados lidos da nota. Confira e corrija antes de salvar: a IA pode errar.")
        for aviso in sugestao.avisos:
            st.caption(f"• {aviso}")

    with st.form("cadastro", clear_on_submit=True):
        nome = st.text_input("Produto *", value=(sugestao.produto if sugestao else "") or "")
        coluna_loja, coluna_categoria = st.columns(2)
        loja = coluna_loja.text_input("Loja *", value=(sugestao.loja if sugestao else "") or "")
        categoria = coluna_categoria.selectbox(
            "Categoria", list(Categoria), index=None, placeholder="Escolha uma categoria",
            format_func=lambda c: c.value,
        )
        coluna1, coluna2, coluna3 = st.columns(3)
        data_compra = coluna1.date_input(
            "Data da compra",
            value=(sugestao.data_compra if sugestao else None) or date.today(),
            format="DD/MM/YYYY",
        )
        prazo = coluna2.number_input("Garantia (meses)", min_value=1, max_value=120, value=12)
        valor = coluna3.number_input(
            "Valor (R$)",
            min_value=0.0,
            step=10.0,
            format="%.2f",
            value=float((sugestao.valor if sugestao else 0) or 0),
        )
        foto = st.file_uploader(
            "Foto do produto (opcional; sem foto, usamos a imagem da categoria)",
            type=["png", "jpg", "jpeg", "webp"],
        )
        observacoes = st.text_area("Observações")
        enviado = st.form_submit_button("Salvar", type="primary")

    if not enviado:
        return

    if not nome.strip() or not loja.strip():
        st.error("Preencha o produto e a loja.")
        return

    produto = repo.adicionar(
        Produto(
            nome=nome.strip(),
            loja=loja.strip(),
            data_compra=data_compra,
            prazo_garantia_meses=int(prazo),
            valor=valor or None,
            observacoes=observacoes.strip(),
            categoria=categoria,
        )
    )
    for arquivo in arquivos:
        repo.adicionar_comprovante(
            produto.id, arquivo.name, arquivo.getvalue(), TipoDocumento.NOTA_FISCAL
        )
    if foto:
        repo.salvar_foto(produto.id, foto.name, foto.getvalue())

    # O Streamlit já desenhou o menu nesta execução: guardamos a mensagem e a página de destino
    # no session_state (sobrevivem ao rerun) e rodamos a tela de novo.
    st.session_state.pop("sugestao", None)
    st.session_state["upload_n"] += 1
    st.session_state["ir_para"] = PAGINA_LISTA
    st.session_state["mensagem_sucesso"] = (
        f"'{produto.nome}' cadastrado. Garantia até {formatar_data(data_vencimento(produto))}."
    )
    st.rerun()


def guardar_documento(repo: Repositorio, base: BaseConhecimento, produto: Produto, arquivo, tipo):
    """Guarda o arquivo e, se for termo ou manual com texto, indexa para a aba Perguntas."""
    aviso = ""
    if tipo != TipoDocumento.NOTA_FISCAL:
        eh_imagem = Path(arquivo.name).suffix.lower() in EXTENSOES_IMAGEM
        paginas = [] if eh_imagem else extrair_paginas(arquivo.name, arquivo.getvalue())
        if paginas:
            try:
                with st.spinner("Indexando (gera um vetor por trecho)..."):
                    base.indexar(arquivo.name, paginas, produto.id)
            except Exception as erro:  # Ollama fora do ar, modelo não baixado...
                st.error(f"Não consegui indexar, o documento não foi guardado: {erro}")
                return
        else:
            aviso = " Não achei texto nele, então não será usado nas respostas (só PDF com texto ou .txt)."

    repo.adicionar_comprovante(produto.id, arquivo.name, arquivo.getvalue(), tipo)
    st.session_state["documento_n"] = st.session_state.get("documento_n", 0) + 1  # limpa o uploader
    st.session_state["mensagem_sucesso"] = f"{tipo.value} '{arquivo.name}' guardado.{aviso}"
    st.rerun()


def mostrar_detalhes(repo: Repositorio, base: BaseConhecimento, produto: Produto):
    """Conteúdo do 'Detalhes e documentos' de um produto."""
    dias = dias_restantes(produto)
    if dias >= 0:
        st.write(f"**Restam:** {dias} dias")
    else:
        st.write(f"**Venceu há:** {-dias} dias")
    if produto.valor:
        st.write(f"**Valor:** R$ {produto.valor:,.2f}")
    if produto.observacoes:
        st.write(f"**Observações:** {produto.observacoes}")

    nova_categoria = st.selectbox(
        "Categoria",
        list(Categoria),
        index=list(Categoria).index(produto.categoria) if produto.categoria else None,
        placeholder="Sem categoria",
        format_func=lambda c: c.value,
        key=f"categoria_{produto.id}",
    )
    if nova_categoria != produto.categoria:
        repo.atualizar_categoria(produto.id, nova_categoria)
        st.rerun()

    st.markdown("**Foto do produto**")
    nova_foto = st.file_uploader(
        "Enviar ou trocar a foto",
        type=["png", "jpg", "jpeg", "webp"],
        key=f"foto_{produto.id}_{st.session_state.get('foto_n', 0)}",
    )
    if nova_foto and st.button("Salvar foto", key=f"salvar_foto_{produto.id}"):
        repo.salvar_foto(produto.id, nova_foto.name, nova_foto.getvalue())
        st.session_state["foto_n"] = st.session_state.get("foto_n", 0) + 1  # limpa o uploader
        st.rerun()

    st.markdown("**Documentos**")
    documentos = repo.listar_comprovantes(produto.id)
    indexados = {fonte for fonte, produto_id, _ in base.listar_fontes() if produto_id == produto.id}
    if not documentos and not indexados:
        st.caption("Nenhum documento ainda.")
    for documento in documentos:
        caminho = Path(documento.caminho)
        rotulo = f"{documento.tipo.value}: {documento.nome_original}"
        if not caminho.exists():
            st.warning(f"Arquivo não encontrado: {rotulo}")
        elif caminho.suffix.lower() in EXTENSOES_IMAGEM:
            st.image(str(caminho), caption=rotulo, width=300)
        else:
            st.download_button(
                f"⬇ {rotulo}", data=caminho.read_bytes(), file_name=documento.nome_original,
                key=f"download_{documento.id}",
            )
        if documento.nome_original in indexados:
            st.caption("Usado nas respostas da aba Perguntas.")
    guardados = {d.nome_original for d in documentos}
    for fonte in sorted(indexados - guardados):  # termos indexados antes de guardarmos o arquivo
        st.caption(f"📄 {fonte} (usado nas respostas; arquivo não guardado)")

    tipo = st.selectbox(
        "Tipo do novo documento", list(TipoDocumento), format_func=lambda t: t.value,
        key=f"tipo_{produto.id}",
    )
    documento_novo = st.file_uploader(
        "Adicionar documento (PDF, imagem ou texto)",
        type=["pdf", "png", "jpg", "jpeg", "webp", "txt", "md"],
        key=f"documento_{produto.id}_{st.session_state.get('documento_n', 0)}",
    )
    if documento_novo and st.button("Salvar documento", key=f"salvar_documento_{produto.id}"):
        guardar_documento(repo, base, produto, documento_novo, tipo)


    if st.button("Excluir produto", key=f"excluir_{produto.id}"):
        repo.excluir(produto.id)
        st.rerun()


def _celula(rotulo: str, valor: str) -> str:
    return (
        f'<div class="celula"><span class="rotulo">{html.escape(rotulo)}</span>'
        f'<span class="valor">{html.escape(valor)}</span></div>'
    )


def linha_produto(
    repo: Repositorio, base: BaseConhecimento, produto: Produto, similaridade: float | None
):
    classe, titulo, prefixo = VISUAL_STATUS[status_garantia(produto)]
    miniatura = produto.foto if produto.foto and Path(produto.foto).exists() else None

    with st.container(border=True):
        c_foto, c_nome, c_cat, c_data, c_prazo, c_status = st.columns(
            [0.9, 3, 1.8, 1.7, 1.4, 2.6], vertical_alignment="center"
        )
        if miniatura:
            c_foto.image(miniatura, width=56)
        else:
            c_foto.markdown(
                f'<div class="miniatura">{imagem_padrao(produto.categoria)}</div>',
                unsafe_allow_html=True,
            )

        extra = f" · similaridade {similaridade:.2f}" if similaridade is not None else ""
        c_nome.markdown(
            f'<div class="nome-produto">{html.escape(produto.nome)}</div>'
            f'<div class="loja-produto">{html.escape(produto.loja)}{extra}</div>',
            unsafe_allow_html=True,
        )
        if produto.categoria:
            c_cat.markdown(
                f'<span class="selo">{html.escape(produto.categoria.value)}</span>',
                unsafe_allow_html=True,
            )
        c_data.markdown(
            _celula("Data da compra", formatar_data(produto.data_compra)), unsafe_allow_html=True
        )
        c_prazo.markdown(
            _celula("Garantia", f"{produto.prazo_garantia_meses} meses"), unsafe_allow_html=True
        )
        c_status.markdown(
            f'<div class="status {classe}"><span class="titulo">{titulo}</span>'
            f'<span class="data">{prefixo} {formatar_mes(data_vencimento(produto))}</span></div>',
            unsafe_allow_html=True,
        )

        with st.expander("Detalhes e documentos"):
            mostrar_detalhes(repo, base, produto)


def cartao(icone: str, cor: str, numero: int, legenda: str) -> str:
    return (
        f'<div class="cartao"><div class="icone {cor}">{icone}</div><div>'
        f'<div class="numero">{numero}</div><div class="legenda">{legenda}</div></div></div>'
    )


def tela_lista(repo: Repositorio, base: BaseConhecimento):
    coluna_titulo, coluna_botao = st.columns([5, 1.3], vertical_alignment="center")
    with coluna_titulo:
        cabecalho(
            "Meus produtos",
            "Organize suas notas fiscais, acompanhe a garantia e tire dúvidas com o assistente.",
        )
    coluna_botao.button(
        "＋ Novo produto", type="primary", use_container_width=True,
        on_click=_ir_para, args=(PAGINA_CADASTRO,),
    )

    todos = repo.listar()
    contagem = contar_por_status(todos)
    c1, c2, c3, c4 = st.columns(4)
    c1.markdown(cartao("📦", "azul", len(todos), "Produtos cadastrados"), unsafe_allow_html=True)
    c2.markdown(cartao("🛡️", "verde", contagem["vigente"], "Dentro da garantia"), unsafe_allow_html=True)
    c3.markdown(
        cartao("⏳", "amarelo", contagem["vence_em_breve"], "Vencendo em breve"),
        unsafe_allow_html=True,
    )
    c4.markdown(cartao("⛔", "vermelho", contagem["vencida"], "Garantia vencida"), unsafe_allow_html=True)
    st.write("")

    coluna_busca, coluna_tipo = st.columns([3, 2], vertical_alignment="bottom")
    texto = coluna_busca.text_input(
        "Buscar", placeholder="Buscar produtos, notas ou lojas...", label_visibility="collapsed"
    )
    por_significado = coluna_tipo.radio(
        "Tipo de busca", ["Pelo texto", "Pelo significado"], horizontal=True,
        label_visibility="collapsed",
    ) == "Pelo significado"

    similaridades: dict[int, float] = {}
    if texto.strip() and por_significado:
        try:
            with st.spinner("Buscando pelo significado..."):
                repo.reindexar()  # indexa o que ainda não tem vetor (produtos antigos)
                resultados = repo.buscar_semantico(texto)
        except Exception as erro:  # Ollama fora do ar, modelo não baixado...
            st.error(f"A busca pelo significado falhou: {erro}")
            return
        produtos = [produto for produto, _ in resultados]
        similaridades = {produto.id: nota for produto, nota in resultados}
    elif texto.strip():
        produtos = repo.buscar(texto)
    else:
        produtos = todos

    contagem_busca = contar_por_status(produtos)
    contagens = {"todos": len(produtos), **contagem_busca}
    coluna_filtro, coluna_ordem, coluna_categoria = st.columns([4, 1.4, 1.6], vertical_alignment="bottom")
    filtro = coluna_filtro.segmented_control(
        "Status",
        FILTROS_STATUS,
        default="todos",
        format_func=lambda f: f"{ROTULO_FILTRO[f]} ({contagens[f]})",
        label_visibility="collapsed",
        key="filtro_status",
    ) or "todos"
    ordenacao = coluna_ordem.selectbox("Ordenar por", ORDENACOES)
    opcao_categoria = coluna_categoria.selectbox(
        "Filtrar por", [TODAS_CATEGORIAS, *[c.value for c in Categoria]]
    )

    if filtro != "todos":
        produtos = [p for p in produtos if status_garantia(p) == filtro]
    if opcao_categoria != TODAS_CATEGORIAS:
        produtos = [p for p in produtos if p.categoria and p.categoria.value == opcao_categoria]
    if not similaridades:  # na busca por significado, a ordem é a da similaridade
        if ordenacao == "Vencimento":
            produtos = sorted(produtos, key=data_vencimento)
        elif ordenacao == "Nome":
            produtos = sorted(produtos, key=lambda p: p.nome.lower())
        else:
            produtos = sorted(produtos, key=lambda p: p.data_compra, reverse=True)

    if not produtos:
        st.info("Nenhum produto encontrado.")
        return

    for produto in produtos:
        linha_produto(repo, base, produto, similaridades.get(produto.id))


@st.cache_resource  # roda uma vez por servidor: a thread começa quando o app abre
def iniciar_indexacao_cdc() -> dict:
    """Indexa o CDC em segundo plano (na primeira vez, ou se o modelo de embeddings mudou),
    para já estar pronto quando o usuário fizer a primeira pergunta.

    A thread usa a própria conexão com o banco: uma conexão SQLite não deve ser compartilhada
    entre a indexação e as telas ao mesmo tempo."""
    estado: dict = {"erro": None}

    def trabalho():
        try:
            base = BaseConhecimento(conectar())
            if base.fonte_indexada(FONTE_CDC):
                return
            if not CAMINHO_CDC.exists():
                raise FileNotFoundError(f"Arquivo do CDC não encontrado: {CAMINHO_CDC}")
            base.indexar(FONTE_CDC, extrair_paginas(CAMINHO_CDC.name, CAMINHO_CDC.read_bytes()))
        except Exception as erro:  # Ollama fora do ar, modelo de embeddings não baixado...
            estado["erro"] = str(erro)

    estado["thread"] = threading.Thread(target=trabalho, daemon=True)
    estado["thread"].start()
    return estado


def mostrar_mensagem(papel: str, conteudo):
    with st.chat_message(papel):
        if papel == "user":
            st.markdown(conteudo)
            return

        mensagem: Mensagem = conteudo
        st.markdown(limpar_citacoes(mensagem.texto))
        if mensagem.produto:
            st.caption(f"Produto considerado: {mensagem.produto.nome}")
        if mensagem.citacoes_invalidas:
            numeros = ", ".join(f"[{n}]" for n in mensagem.citacoes_invalidas)
            st.warning(f"A IA citou {numeros}, que não existe(m). Esta resposta pode não ser confiável.")


def tela_perguntas(repo: Repositorio, base: BaseConhecimento, indexacao: dict):
    cabecalho("Como posso ajudar?", "Pergunte sobre suas garantias e seus direitos de consumidor.")

    if "conversa" not in st.session_state:
        st.session_state["conversa"] = Conversa(repo, base, criar_llm())
        st.session_state["historico"] = []
    conversa: Conversa = st.session_state["conversa"]
    historico: list = st.session_state["historico"]

    if historico and st.button("Novo assunto"):
        conversa.reiniciar()
        historico.clear()
        st.rerun()

    for papel, conteudo in historico:
        mostrar_mensagem(papel, conteudo)

    entrada = st.chat_input("Ex.: a garantia cobre tela quebrada?")
    if not entrada:
        return

    historico.append(("user", entrada))
    mostrar_mensagem("user", entrada)
    try:
        with st.spinner("Pensando..."):
            indexacao["thread"].join()  # só espera se o CDC ainda estiver sendo indexado
            if indexacao["erro"]:
                raise RuntimeError(f"não consegui indexar o CDC: {indexacao['erro']}")
            resposta = conversa.responder(entrada)
    except Exception as erro:  # Ollama fora do ar, modelo não baixado...
        st.error(f"Não consegui responder: {erro}")
        return

    historico.append(("assistant", resposta))
    mostrar_mensagem("assistant", resposta)


def main():
    st.set_page_config(page_title=NOME_APP, page_icon=str(ICONE), layout="wide")
    st.markdown(ESTILO, unsafe_allow_html=True)

    repo = obter_repositorio()
    base = BaseConhecimento(repo.conexao)
    indexacao = iniciar_indexacao_cdc()

    # Navegação pedida por código (ex.: depois de salvar): precisa acontecer antes de o menu
    # ser desenhado, porque o Streamlit não deixa mudar um widget depois que ele existe.
    if "ir_para" in st.session_state:
        st.session_state["pagina"] = st.session_state.pop("ir_para")

    with st.sidebar:
        st.image(str(LOGO), width=140)
        pagina = st.radio("Menu", PAGINAS, key="pagina", label_visibility="collapsed")

    mensagem = st.session_state.pop("mensagem_sucesso", None)  # mostra uma vez só
    if mensagem:
        st.success(mensagem)

    if pagina == PAGINA_CADASTRO:
        tela_cadastro(repo)
    elif pagina == PAGINA_PERGUNTAS:
        tela_perguntas(repo, base, indexacao)
    else:
        tela_lista(repo, base)


main()
