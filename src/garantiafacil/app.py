"""Interface web (Streamlit).

Rode com: uv run streamlit run src/garantiafacil/app.py
"""

import threading
from datetime import date
from pathlib import Path

import streamlit as st

from garantiafacil.db import conectar
from garantiafacil.conversa import Conversa, Mensagem
from garantiafacil.documentos import extrair_paginas
from garantiafacil.garantia import data_vencimento, dias_restantes, status_garantia
from garantiafacil.llm import criar_llm
from garantiafacil.modelos import Produto
from garantiafacil.pipeline_nota import ler_nota
from garantiafacil.rag import BaseConhecimento
from garantiafacil.repositorio import Repositorio

EXTENSOES_IMAGEM = {".png", ".jpg", ".jpeg", ".webp"}

CAMINHO_CDC = Path(__file__).resolve().parents[2] / "docs" / "conhecimento" / "cdc.txt"
FONTE_CDC = CAMINHO_CDC.name

ROTULO_STATUS = {
    "vigente": "🟢 Vigente",
    "vence_em_breve": "🟡 Vence em breve",
    "vencida": "🔴 Vencida",
}


@st.cache_resource  # cria a conexão uma vez só e reaproveita entre as interações
def obter_repositorio() -> Repositorio:
    return Repositorio(conectar(check_same_thread=False))


def formatar_data(d: date) -> str:
    return d.strftime("%d/%m/%Y")


def tela_cadastro(repo: Repositorio):
    st.subheader("Cadastrar produto")

    # O uploader fica fora do formulário para o botão "Ler nota" funcionar antes de salvar.
    # A chave muda a cada cadastro salvo, o que "limpa" o uploader.
    chave_upload = st.session_state.setdefault("upload_n", 0)
    arquivos = st.file_uploader(
        "Comprovantes (nota fiscal, fotos, PDF)",
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
        loja = st.text_input("Loja *", value=(sugestao.loja if sugestao else "") or "")
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
        observacoes = st.text_area("Observações")
        enviado = st.form_submit_button("Salvar")

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
        )
    )
    for arquivo in arquivos:
        repo.adicionar_comprovante(produto.id, arquivo.name, arquivo.getvalue())

    # O Streamlit desenha as abas na mesma execução: a lista já foi desenhada antes deste save.
    # Guardamos a mensagem no session_state (sobrevive ao rerun) e rodamos a tela de novo.
    st.session_state.pop("sugestao", None)
    st.session_state["upload_n"] += 1
    st.session_state["mensagem_sucesso"] = (
        f"'{produto.nome}' cadastrado. Garantia até {formatar_data(data_vencimento(produto))}."
    )
    st.rerun()


def mostrar_produto(repo: Repositorio, base: BaseConhecimento, produto: Produto):
    status = status_garantia(produto)
    dias = dias_restantes(produto)
    titulo = f"{ROTULO_STATUS[status]} · {produto.nome} ({produto.loja})"

    with st.expander(titulo):
        st.write(f"**Compra:** {formatar_data(produto.data_compra)}")
        st.write(f"**Garantia até:** {formatar_data(data_vencimento(produto))}")
        if dias >= 0:
            st.write(f"**Restam:** {dias} dias")
        else:
            st.write(f"**Venceu há:** {-dias} dias")
        if produto.valor:
            st.write(f"**Valor:** R$ {produto.valor:,.2f}")
        if produto.observacoes:
            st.write(f"**Observações:** {produto.observacoes}")

        for comprovante in repo.listar_comprovantes(produto.id):
            caminho = Path(comprovante.caminho)
            if not caminho.exists():
                st.warning(f"Arquivo não encontrado: {comprovante.nome_original}")
            elif caminho.suffix.lower() in EXTENSOES_IMAGEM:
                st.image(str(caminho), caption=comprovante.nome_original, width=300)
            else:
                st.download_button(
                    f"Baixar {comprovante.nome_original}",
                    data=caminho.read_bytes(),
                    file_name=comprovante.nome_original,
                    key=f"download_{comprovante.id}",
                )

        st.markdown("**Termo de garantia ou manual** (usado nas respostas da aba Perguntas)")
        for fonte, produto_id, total in base.listar_fontes():
            if produto_id == produto.id:
                st.caption(f"📄 {fonte} · {total} trechos")

        termo = st.file_uploader(
            "Adicionar termo ou manual (PDF ou texto)",
            type=["pdf", "txt", "md"],
            key=f"termo_{produto.id}",
        )
        if termo and st.button("Indexar documento", key=f"indexar_{produto.id}"):
            paginas = extrair_paginas(termo.name, termo.getvalue())
            if not paginas:
                st.error(
                    "Não encontrei texto neste arquivo. PDFs escaneados (só imagem) ainda não são lidos."
                )
            else:
                try:
                    with st.spinner("Indexando (gera um vetor por trecho)..."):
                        total = base.indexar(termo.name, paginas, produto.id)
                    st.success(f"'{termo.name}' indexado em {total} trechos.")
                except Exception as erro:  # Ollama fora do ar, modelo não baixado...
                    st.error(f"Não consegui indexar: {erro}")

        if st.button("Excluir produto", key=f"excluir_{produto.id}"):
            repo.excluir(produto.id)
            st.rerun()


def tela_lista(repo: Repositorio, base: BaseConhecimento):
    st.subheader("Meus produtos")
    coluna_busca, coluna_tipo = st.columns([3, 2])
    texto = coluna_busca.text_input("Buscar", placeholder="Ex.: geladeira, celular, notebook")
    por_significado = coluna_tipo.radio(
        "Tipo de busca", ["Pelo texto", "Pelo significado"], horizontal=True
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
        produtos = repo.listar()

    if not produtos:
        st.info("Nenhum produto encontrado.")
        return

    for produto in produtos:
        if produto.id in similaridades:
            st.caption(f"Similaridade com a busca: {similaridades[produto.id]:.2f}")
        mostrar_produto(repo, base, produto)


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
        st.markdown(mensagem.texto)
        if mensagem.produto:
            st.caption(f"Produto considerado: {mensagem.produto.nome}")
        if mensagem.citacoes_invalidas:
            numeros = ", ".join(f"[{n}]" for n in mensagem.citacoes_invalidas)
            st.warning(f"A IA citou {numeros}, que não existe(m) nos trechos. Confira nas fontes.")
        if mensagem.trechos:
            with st.expander(f"Trechos usados ({len(mensagem.trechos)})"):
                for i, trecho in enumerate(mensagem.trechos, 1):
                    st.markdown(
                        f"**[{i}] {trecho.fonte}, página {trecho.pagina}** "
                        f"· similaridade {trecho.similaridade:.2f}"
                    )
                    st.text(trecho.texto)


def tela_perguntas(repo: Repositorio, base: BaseConhecimento, indexacao: dict):
    st.subheader("Como posso ajudar?")
    st.caption("Pergunte sobre suas garantias e seus direitos de consumidor.")

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
    st.set_page_config(page_title="GarantiaFácil", page_icon="🧾")
    st.title("🧾 GarantiaFácil")

    repo = obter_repositorio()
    base = BaseConhecimento(repo.conexao)
    indexacao = iniciar_indexacao_cdc()

    mensagem = st.session_state.pop("mensagem_sucesso", None)  # mostra uma vez só
    if mensagem:
        st.success(mensagem)

    aba_lista, aba_cadastro, aba_perguntas = st.tabs(["Meus produtos", "Cadastrar", "Perguntas"])
    with aba_lista:
        tela_lista(repo, base)
    with aba_cadastro:
        tela_cadastro(repo)
    with aba_perguntas:
        tela_perguntas(repo, base, indexacao)


main()
