"""Interface web (Streamlit).

Rode com: uv run streamlit run src/garantiafacil/app.py
"""

import base64
import html
import threading
from dataclasses import replace
from datetime import date
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st

from garantiafacil.conversa import Conversa, Mensagem
from garantiafacil.db import conectar
from garantiafacil.documentos import extrair_paginas
from garantiafacil.fotos import ARQUIVO, CAMERA, ORIGENS, SEM_FOTO, foto_escolhida
from garantiafacil.garantia import (
    DIAS_ALERTA,
    GARANTIA_LEGAL_DIAS,
    contar_por_status,
    data_vencimento,
    dias_restantes,
    fim_garantia_fabricante,
    status_garantia,
)
from garantiafacil.avisos import OPCOES_DIAS, avisos_de_vencimento, quando
from garantiafacil.cpf_cnpj import formatar_cnpj, formatar_cpf, formatar_telefone
from garantiafacil.llm import criar_llm
from garantiafacil.imagens import imagem_padrao
from garantiafacil.modelos import Categoria, Produto, TipoDocumento, TipoPessoa
from garantiafacil.painel import (
    formatar_real,
    gasto_por_categoria,
    proximos_vencimentos,
    resumo,
    rotulo_mes,
    vencimentos_por_mes,
)
from garantiafacil.pipeline_nota import ler_nota
from garantiafacil.prazo_termo import sugerir_prazo
from garantiafacil.rag import BaseConhecimento, limpar_citacoes
from garantiafacil.repositorio import Repositorio
from garantiafacil.usuarios import DURACAO_SESSAO_DIAS, ErroDeCadastro, Usuarios

EXTENSOES_IMAGEM = {".png", ".jpg", ".jpeg", ".webp"}

CAMINHO_CDC = Path(__file__).resolve().parents[2] / "docs" / "conhecimento" / "cdc.txt"
FONTE_CDC = CAMINHO_CDC.name

NOME_COOKIE = "taguardado_sessao"  # cookie do "manter conectado"
NOME_APP = "TáGuardado"
PASTA_ASSETS = Path(__file__).resolve().parent / "assets"
LOGO = PASTA_ASSETS / "logo.png"
ICONE = PASTA_ASSETS / "icone.png"  # ícone da aba do navegador

PAGINA_LISTA = "📦  Meus produtos"
PAGINA_PAINEL = "📊  Painel"
PAGINA_CADASTRO = "➕  Cadastrar"
PAGINA_PERGUNTAS = "💬  Perguntas"
PAGINAS = [PAGINA_LISTA, PAGINA_PAINEL, PAGINA_CADASTRO, PAGINA_PERGUNTAS]
ALTURA_QUADRO = 380  # os dois quadros de gráfico do painel têm a mesma altura

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

# As duas paletas das nossas cores (as do próprio Streamlit vêm do .streamlit/config.toml). O mesmo
# nome de variável existe nas duas: o CSS só usa var(--nome), e o tema ativo decide o valor.
PALETAS = {
    "claro": {
        "primaria": "#2f45f5", "destaque": "#2f45f5", "card": "#ffffff", "borda": "#eceffa",
        "texto-suave": "#5b6080", "texto-fraco": "#7a7fa0", "hover": "#f1f4ff",
        "selecionado": "#eaefff", "chip-azul": "#eaf0ff", "degrade-fim": "#f7f9ff",
        "borda-azul": "#dfe6ff", "tracejado": "#cfd6f6", "ok": "#17784a", "ok-bg": "#e6f7ee",
        "ok-solido": "#17784a", "aviso": "#a35f00", "aviso-bg": "#fff3dc", "erro": "#bf2236",
        "erro-bg": "#fde8ea", "logo-fundo": "transparent", "logo-respiro": "0",
        "grafico": "#2f45f5", "grafico-texto": "#1b1e3a",
    },
    "escuro": {
        "primaria": "#5468ff", "destaque": "#8d9bff", "card": "#1a1e38", "borda": "#2a2f55",
        "texto-suave": "#a4a9c9", "texto-fraco": "#8a8fb0", "hover": "#232850",
        "selecionado": "#2a3270", "chip-azul": "#232a5c", "degrade-fim": "#151935",
        "borda-azul": "#2d3566", "tracejado": "#3a4172", "ok": "#5fd49b", "ok-bg": "#12382a",
        "ok-solido": "#1f9d63", "aviso": "#f5b94a", "aviso-bg": "#3d2f10", "erro": "#ff7b8a",
        "erro-bg": "#3d1820", "logo-fundo": "#ffffff", "logo-respiro": "6px",
        "grafico": "#7b8cff", "grafico-texto": "#e8eaf6",
    },
}


def _tema_escuro() -> bool:
    """O tema ativo no Streamlit (sistema ou escolha do usuário no menu ⋮ do canto da tela)."""
    try:
        return st.context.theme.type == "dark"
    except Exception:  # versão sem esse recurso, ou fora de uma sessão
        return False


def _cores() -> dict:
    return PALETAS["escuro" if _tema_escuro() else "claro"]


def estilo() -> str:
    variaveis = "; ".join(f"--{nome}: {valor}" for nome, valor in _cores().items())
    return f"<style>:root {{ {variaveis}; }}</style>" + ESTILO


ESTILO = """
<style>
/* sidebar */
[data-testid="stSidebar"] { border-right: 1px solid var(--borda); }
[data-testid="stSidebar"] [role="radiogroup"] { gap: 4px; }
[data-testid="stSidebar"] [role="radiogroup"] label {
    padding: 10px 14px; border-radius: 10px; width: 100%; cursor: pointer;
}
[data-testid="stSidebar"] [role="radiogroup"] label:hover { background: var(--hover); }
[data-testid="stSidebar"] [role="radiogroup"] label:has(input:checked) {
    background: var(--selecionado); color: var(--destaque); font-weight: 600;
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
/* A logo sobe para o topo: o cabeçalho da barra (que só guarda o botão de recolher) sai do fluxo. */
[data-testid="stSidebarHeader"] {
    position: absolute; top: 0; right: 0; width: auto; height: auto; padding: 0.5rem; z-index: 2;
}
[data-testid="stSidebarContent"] { display: flex; flex-direction: column; }
[data-testid="stSidebarUserContent"] {
    flex: 1; display: flex; flex-direction: column; padding: 1rem 1rem 0.75rem;
}
[data-testid="stSidebarUserContent"] > div { flex: 1; display: flex; flex-direction: column; }
[data-testid="stSidebarUserContent"] > div > [data-testid="stVerticalBlock"] { flex: 1; }
/* Rodapé fixo na base da barra: nome do usuário (abre um menu) e botão de sair. */
[data-testid="stLayoutWrapper"]:has(> .st-key-rodape_usuario) { margin-top: auto; }
.st-key-rodape_usuario { border-top: 1px solid var(--borda); padding-top: 12px; gap: 0.5rem; }
.st-key-rodape_usuario [data-testid="stPopover"] button {
    border: none; background: transparent; justify-content: flex-start; box-shadow: none;
}
.st-key-rodape_usuario [data-testid="stPopover"] button:hover { background: var(--hover); }
.st-key-rodape_usuario [data-testid="stBaseButton-secondary"] { border: none; background: transparent; }
[data-testid="stSidebar"] [data-testid="stImage"] img { margin: 0 auto; }
.logo-img, [data-testid="stSidebar"] [data-testid="stImage"] img {
    background: var(--logo-fundo); border-radius: 14px; padding: var(--logo-respiro); box-sizing: border-box;
}

/* títulos */
.titulo-pagina { font-size: 2rem !important; font-weight: 800; margin: 0; line-height: 1.2; }
.subtitulo-pagina { color: var(--texto-suave); margin: 2px 0 18px 0; }

/* cartões de resumo */
.cartao {
    display: flex; align-items: center; gap: 14px; background: var(--card); border: 1px solid var(--borda);
    border-radius: 16px; padding: 18px 20px; box-shadow: 0 2px 10px rgba(47, 69, 245, 0.04);
}
.cartao .icone {
    width: 52px; height: 52px; border-radius: 14px; display: flex; align-items: center;
    justify-content: center; font-size: 1.5rem; flex: none;
}
.cartao .numero { font-size: clamp(1.1rem, 1.3vw, 1.7rem); font-weight: 800; line-height: 1.1; white-space: nowrap; }
.cartao .legenda { color: var(--texto-suave); font-size: 0.9rem; }
.icone.azul { background: var(--chip-azul); } .icone.verde { background: var(--ok-bg); }
.icone.amarelo { background: var(--aviso-bg); } .icone.vermelho { background: var(--erro-bg); }

/* painel */
.titulo-secao { font-weight: 700; font-size: 1.05rem; }
.sub-secao { color: var(--texto-fraco); font-size: 0.85rem; margin-bottom: 6px; }
.linha-vencimento {
    display: flex; justify-content: space-between; align-items: center; gap: 12px;
    padding: 10px 0; border-top: 1px solid var(--borda);
}
.linha-vencimento .quando { border-radius: 999px; padding: 4px 12px; font-size: 0.82rem; font-weight: 600; white-space: nowrap; }
.quando.ok { background: var(--ok-bg); color: var(--ok); }
.quando.aviso { background: var(--aviso-bg); color: var(--aviso); }
.quando.urgente { background: var(--erro-bg); color: var(--erro); }

/* estados vazios e primeiro acesso */
.vazio {
    text-align: center; background: var(--card); border: 1px dashed var(--tracejado); border-radius: 16px;
    padding: 32px 24px; margin: 12px 0;
}
.vazio .icone-grande { font-size: 2.3rem; }
.vazio .titulo-vazio { font-weight: 700; font-size: 1.15rem; margin-top: 4px; }
.vazio .texto-vazio { color: var(--texto-suave); max-width: 540px; margin: 6px auto 0; }
.boas-vindas {
    background: linear-gradient(135deg, var(--chip-azul), var(--degrade-fim)); border: 1px solid var(--borda-azul);
    border-radius: 18px; padding: 22px 28px; margin-bottom: 16px;
}
.boas-vindas .titulo-bv { font-size: 1.4rem; font-weight: 800; }
.boas-vindas .texto-bv { color: var(--texto-suave); margin-top: 4px; }
.numero-passo {
    display: inline-flex; align-items: center; justify-content: center; width: 28px; height: 28px;
    border-radius: 50%; background: var(--primaria); color: #fff; font-weight: 700; font-size: 0.9rem;
    margin-right: 8px;
}
.numero-passo.feito { background: var(--ok-solido); }
.titulo-passo { font-weight: 700; font-size: 1.02rem; }

/* linha do produto */
[data-testid="stVerticalBlockBorderWrapper"] {
    background: var(--card); border-radius: 14px; border-color: var(--borda);
}
/* miniatura (foto do comprovante) quadrada, só na 1ª coluna da linha do produto */
[data-testid="stColumn"]:first-child [data-testid="stImage"] img {
    width: 56px; height: 56px; object-fit: cover; border-radius: 12px;
}
.miniatura {
    color: var(--destaque);
    width: 56px; height: 56px; border-radius: 12px; background: var(--hover); display: flex;
    align-items: center; justify-content: center; font-size: 1.7rem;
}
.nome-produto { font-weight: 700; font-size: 1.02rem; }
.loja-produto { color: var(--texto-suave); font-size: 0.9rem; }
.selo {
    display: inline-block; padding: 4px 12px; border-radius: 999px; font-size: 0.82rem;
    font-weight: 600; background: var(--selecionado); color: var(--destaque);
}
.celula .rotulo { display: block; color: var(--texto-fraco); font-size: 0.8rem; }
.celula .valor { font-weight: 600; }
.status { border-radius: 12px; padding: 8px 14px; }
.status .titulo { font-weight: 700; display: block; }
.status .data { font-size: 0.82rem; opacity: 0.8; }
.status.ok { background: var(--ok-bg); color: var(--ok); }
.status.aviso { background: var(--aviso-bg); color: var(--aviso); }
.status.vencida { background: var(--erro-bg); color: var(--erro); }
</style>
"""


@st.cache_resource  # cria a conexão uma vez só e reaproveita entre as interações
def obter_conexao():
    return conectar(check_same_thread=False)


def formatar_data(d: date) -> str:
    return d.strftime("%d/%m/%Y")


def formatar_mes(d: date) -> str:
    return d.strftime("%m/%Y")


def _sair():
    """Callback do botão Sair: encerra o "manter conectado" (no banco e no navegador) e esquece
    tudo da sessão (usuário, conversa, rascunhos)."""
    Usuarios(obter_conexao()).encerrar_sessao(st.context.cookies.get(NOME_COOKIE))
    st.session_state.clear()
    st.session_state["limpar_cookie"] = True  # a tela de acesso apaga o cookie do navegador


def _definir_cookie(valor: str, dias: int):
    """Grava (ou, com dias=0, apaga) o cookie no navegador. O Streamlit não tem API para isso,
    então rodamos um pequeno JavaScript na própria página. O token é só letras, números, '-' e '_'."""
    # SameSite=Strict: o navegador não manda o cookie em requisições vindas de outros sites.
    # Secure: só em https (no deploy). Não dá para marcar HttpOnly a partir do JavaScript.
    st.html(
        f"""<script>
        document.cookie = "{NOME_COOKIE}={valor}; max-age={dias * 86400}; path=/; SameSite=Strict"
            + (location.protocol === "https:" ? "; Secure" : "");
        </script>""",
        unsafe_allow_javascript=True,
    )


def _abrir_preferencias():
    st.session_state.pop("tela_perfil", None)
    st.session_state["tela_preferencias"] = True
    st.session_state["pagina"] = None  # menu sem item marcado (mesmo motivo do perfil, abaixo)


def _abrir_perfil():
    st.session_state.pop("tela_preferencias", None)
    st.session_state["tela_perfil"] = True
    # Menu sem item marcado enquanto o perfil está aberto: o Streamlit só avisa quando a seleção
    # MUDA, e clicar no item que já estava marcado não faria nada (o usuário ficaria preso no perfil).
    st.session_state["pagina"] = None


def _fechar_tela_da_conta():
    st.session_state.pop("tela_perfil", None)
    st.session_state.pop("tela_preferencias", None)


def _logo_html(largura: int) -> str:
    dados = base64.b64encode(LOGO.read_bytes()).decode()
    return (
        f'<div style="text-align:center;margin-bottom:8px">'
        f'<img class="logo-img" src="data:image/png;base64,{dados}" width="{largura}"></div>'
    )


def tela_acesso(usuarios: Usuarios):
    """Entrar ou criar conta. Sem usuário na sessão, nada mais do app é desenhado."""
    st.markdown(
        "<style>[data-testid='stSidebar'], [data-testid='stSidebarCollapsedControl']"
        " { display: none; }</style>",
        unsafe_allow_html=True,
    )
    _, centro, _ = st.columns([1, 1.3, 1])
    with centro:
        st.markdown(_logo_html(190), unsafe_allow_html=True)
        st.markdown(
            '<div class="subtitulo-pagina" style="text-align:center;margin-bottom:16px">'
            "Suas notas e garantias, sempre à mão.</div>",
            unsafe_allow_html=True,
        )
        aba_entrar, aba_criar = st.tabs(["Entrar", "Criar conta"])

        with aba_entrar, st.form("entrar"):
            email = st.text_input("E-mail")
            senha = st.text_input("Senha", type="password")
            manter = st.checkbox(
                "Manter conectado",
                help=f"Você continua conectado neste navegador por {DURACAO_SESSAO_DIAS} dias, "
                "mesmo fechando a página. Não marque em computador de outras pessoas.",
            )
            if st.form_submit_button("Entrar", type="primary", use_container_width=True):
                usuario = usuarios.autenticar(email, senha)
                if usuario is None:
                    # A mesma mensagem para e-mail inexistente e senha errada: não revela qual.
                    st.error("E-mail ou senha incorretos.")
                else:
                    st.session_state["usuario"] = usuario
                    if manter:  # o cookie é gravado na próxima tela, depois do st.rerun()
                        st.session_state["cookie_para_gravar"] = usuarios.criar_sessao(usuario.id)
                    st.rerun()

        with aba_criar, st.form("criar_conta"):
            nome = st.text_input("Nome")
            email = st.text_input("E-mail", key="email_novo")
            senha = st.text_input("Senha (mínimo 8 caracteres)", type="password", key="senha_nova")
            repetida = st.text_input("Repita a senha", type="password")
            if st.form_submit_button("Criar conta", type="primary", use_container_width=True):
                if senha != repetida:
                    st.error("As senhas não são iguais.")
                else:
                    try:
                        st.session_state["usuario"] = usuarios.criar(email, senha, nome)
                    except ErroDeCadastro as erro:
                        st.error(str(erro))
                    else:
                        st.rerun()


def tela_perfil(usuarios: Usuarios, usuario):
    """Dados do usuário como pessoa física ou jurídica. O e-mail é o login e não muda aqui."""
    cabecalho("Meu perfil", "Seus dados como pessoa física ou como empresa.")

    # O tipo fica fora do formulário: trocar PF/PJ precisa redesenhar os campos na hora.
    # (Dentro de um st.form, nada reage até clicar no botão.)
    tipo = st.radio(
        "Tipo de conta",
        list(TipoPessoa),
        index=list(TipoPessoa).index(usuario.tipo or TipoPessoa.FISICA),
        format_func=lambda t: t.value,
        horizontal=True,
    )
    juridica = tipo is TipoPessoa.JURIDICA
    mesmo_tipo = usuario.tipo is tipo  # só reaproveita os dados salvos se o tipo não mudou
    formatar_documento = formatar_cnpj if juridica else formatar_cpf

    with st.form("perfil"):
        nome = st.text_input(
            "Razão social *" if juridica else "Nome completo *",
            value=usuario.nome,
            key=f"perfil_nome_{tipo.name}",
        )
        if juridica:
            nome_fantasia = st.text_input(
                "Nome fantasia",
                value=usuario.nome_fantasia if mesmo_tipo else "",
                key="perfil_fantasia",
            )
        else:
            nome_fantasia = ""
        coluna_documento, coluna_telefone = st.columns(2)
        documento = coluna_documento.text_input(
            "CNPJ *" if juridica else "CPF *",
            value=formatar_documento(usuario.documento) if mesmo_tipo else "",
            placeholder="00.000.000/0000-00" if juridica else "000.000.000-00",
            key=f"perfil_documento_{tipo.name}",
        )
        telefone = coluna_telefone.text_input(
            "Telefone",
            value=formatar_telefone(usuario.telefone),
            placeholder="(11) 91234-5678",
            key="perfil_telefone",
        )
        st.text_input("E-mail (usado no login)", value=usuario.email, disabled=True)
        enviado = st.form_submit_button("Salvar perfil", type="primary")

    if not enviado:
        return
    try:
        st.session_state["usuario"] = usuarios.atualizar_perfil(
            usuario.id, tipo, nome, documento, nome_fantasia, telefone
        )
    except ErroDeCadastro as erro:
        st.error(str(erro))
        return
    st.session_state["mensagem_sucesso"] = "Perfil salvo."
    st.rerun()


def tela_preferencias(usuarios: Usuarios, usuario):
    """Preferências do usuário. Por enquanto: com quanta antecedência avisar dos vencimentos."""
    cabecalho("Preferências", "Ajuste o app do seu jeito.")
    with st.form("preferencias"):
        st.markdown("**Avisos de vencimento**")
        dias = st.multiselect(
            "Avisar quando faltarem",
            OPCOES_DIAS,
            default=[d for d in usuario.avisar_dias if d in OPCOES_DIAS],
            format_func=lambda d: f"{d} dia" if d == 1 else f"{d} dias",
            help="A faixa de avisos da página Meus produtos mostra as garantias que vencem dentro da "
            "maior antecedência escolhida, e destaca em vermelho as que entraram na menor.",
        )
        st.caption("Sem nenhuma escolha, o app não mostra avisos.")
        enviado = st.form_submit_button("Salvar preferências", type="primary")
    st.caption("🌓 O tema (claro ou escuro) se troca no menu ⋮, no canto superior direito da tela.")

    if not enviado:
        return
    st.session_state["usuario"] = usuarios.atualizar_avisos(usuario.id, dias)
    st.session_state["mensagem_sucesso"] = "Preferências salvas."
    st.rerun()


def _ir_para(pagina: str):
    st.session_state["pagina"] = pagina
    _fechar_tela_da_conta()  # sai do perfil ou das preferências, se estava numa delas


def cabecalho(titulo: str, subtitulo: str):
    st.markdown(
        f'<div class="titulo-pagina">{html.escape(titulo)}</div>'
        f'<div class="subtitulo-pagina">{html.escape(subtitulo)}</div>',
        unsafe_allow_html=True,
    )


def _concluir_cadastro(salvos: list[Produto]):
    """Fim do cadastro (uma nota ou a fila toda): limpa o estado, avisa e volta para a lista."""
    # O Streamlit já desenhou o menu nesta execução: guardamos a mensagem e a página de destino
    # no session_state (sobrevivem ao rerun) e rodamos a tela de novo.
    for chave in ("fila_assinatura", "fila_pos", "fila_leituras", "fila_salvos"):
        st.session_state.pop(chave, None)
    st.session_state["upload_n"] += 1  # chave nova = uploader vazio
    st.session_state["ir_para"] = PAGINA_LISTA
    if len(salvos) == 1:
        st.session_state["mensagem_sucesso"] = (
            f"'{salvos[0].nome}' cadastrado. Garantia até {formatar_data(data_vencimento(salvos[0]))}."
        )
    elif salvos:
        st.session_state["mensagem_sucesso"] = f"{len(salvos)} produtos cadastrados."
    st.rerun()


def _ler_notas_da_fila(arquivos: list):
    """Lê com a IA as notas que são imagem e ainda não foram lidas (PDF fica para preencher à mão).
    O resultado de cada uma (ou o erro) fica em `fila_leituras`, pela posição do arquivo."""
    leituras: dict = st.session_state["fila_leituras"]
    pendentes = [
        i for i, a in enumerate(arquivos)
        if Path(a.name).suffix.lower() in EXTENSOES_IMAGEM and i not in leituras
    ]  # fmt: skip
    progresso = st.progress(0.0, text="Lendo as notas...")
    for passo, i in enumerate(pendentes):
        progresso.progress(passo / len(pendentes), text=f"Lendo a nota {passo + 1} de {len(pendentes)}...")
        try:
            leituras[i] = ler_nota(arquivos[i].getvalue(), tipo_midia=arquivos[i].type)
        except Exception as erro:  # modelo fora do ar, imagem ruim, JSON inválido...
            leituras[i] = str(erro)
    progresso.empty()


def tela_cadastro(repo: Repositorio):
    cabecalho("Cadastrar produto", "Registre a compra e acompanhe o prazo da garantia.")

    # O uploader fica fora do formulário para o botão "Ler notas" funcionar antes de salvar.
    # A chave muda a cada cadastro concluído, o que "limpa" o uploader.
    chave_upload = st.session_state.setdefault("upload_n", 0)
    arquivos = st.file_uploader(
        "Notas fiscais ou cupons (foto ou PDF)",
        type=["pdf", "png", "jpg", "jpeg", "webp"],
        accept_multiple_files=True,
        key=f"upload_{chave_upload}",
        help="Cada arquivo é a nota de um produto. Envie várias para cadastrar de uma vez: "
        "você confere e salva uma por vez.",
    )

    # A fila tem uma nota por arquivo. Se a seleção mudar, recomeça do primeiro.
    assinatura = tuple((a.name, a.size) for a in arquivos)
    if st.session_state.get("fila_assinatura") != assinatura:
        st.session_state["fila_assinatura"] = assinatura
        st.session_state["fila_pos"] = 0
        st.session_state["fila_leituras"] = {}
        st.session_state["fila_salvos"] = []
    pos: int = st.session_state["fila_pos"]
    salvos: list[Produto] = st.session_state["fila_salvos"]
    total = len(arquivos)

    imagens = [a for a in arquivos if Path(a.name).suffix.lower() in EXTENSOES_IMAGEM]
    if imagens and st.button("📷 Ler a nota com IA" if total == 1 else f"📷 Ler as {len(imagens)} notas com IA"):
        _ler_notas_da_fila(arquivos)

    arquivo = arquivos[pos] if total else None
    leitura = st.session_state["fila_leituras"].get(pos)
    sugestao = leitura if not isinstance(leitura, str) else None

    if total > 1:
        st.progress(pos / total, text=f"Nota {pos + 1} de {total}: {arquivo.name}")
        if salvos:
            st.caption(f"✔ {len(salvos)} já cadastrado(s) nesta leva.")
    if isinstance(leitura, str):
        st.error(f"Não consegui ler esta nota: {leitura}. Preencha os dados à mão.")
    elif sugestao:
        st.info("Dados lidos da nota. Confira e corrija antes de salvar: a IA pode errar.")
        for aviso in sugestao.avisos:
            st.caption(f"• {aviso}")

    # A chave de cada campo muda com a nota (pos) e com a leitura da IA. Com `key`, o Streamlit guarda
    # o valor do campo e ignora um `value=` novo: sem isso, o formulário continuaria vazio depois
    # de ler a nota, e o que foi digitado numa nota apareceria na seguinte.
    sufixo = f"{chave_upload}_{pos}_{'ia' if sugestao else 'manual'}"
    # A foto vem antes do formulário e a chave não tem 'ia'/'manual': ler a nota não pode apagar a
    # foto que o usuário já escolheu.
    foto = seletor_de_foto(
        f"cadastro_{chave_upload}_{pos}", "Foto do produto (opcional; sem foto, usamos a imagem da categoria)"
    )
    with st.form(f"cadastro_{sufixo}", clear_on_submit=True):
        nome = st.text_input(
            "Produto *", value=(sugestao.produto if sugestao else "") or "", key=f"nome_{sufixo}"
        )
        coluna_loja, coluna_categoria = st.columns(2)
        loja = coluna_loja.text_input(
            "Loja *", value=(sugestao.loja if sugestao else "") or "", key=f"loja_{sufixo}"
        )
        categoria = coluna_categoria.selectbox(
            "Categoria", list(Categoria), placeholder="Escolha uma categoria",
            index=list(Categoria).index(sugestao.categoria) if sugestao and sugestao.categoria else None,
            format_func=lambda c: c.value, key=f"categoria_{sufixo}",
        )  # fmt: skip
        coluna1, coluna2, coluna3 = st.columns(3)
        data_compra = coluna1.date_input(
            "Data da compra",
            value=(sugestao.data_compra if sugestao else None) or date.today(),
            format="DD/MM/YYYY",
            key=f"data_{sufixo}",
        )
        prazo = coluna2.number_input(
            "Garantia (meses)", min_value=1, max_value=120, value=12, key=f"prazo_{sufixo}"
        )
        valor = coluna3.number_input(
            "Valor (R$)",
            min_value=0.0,
            step=10.0,
            format="%.2f",
            value=float((sugestao.valor if sugestao else 0) or 0),
            key=f"valor_{sufixo}",
        )
        observacoes = st.text_area(
            "Observações", value=sugestao.detalhes if sugestao else "", key=f"obs_{sufixo}"
        )
        coluna_salvar, coluna_pular, _ = st.columns([1, 1.4, 4])
        enviado = coluna_salvar.form_submit_button("Salvar", type="primary")
        pulou = total > 1 and coluna_pular.form_submit_button("Pular esta nota")

    if pulou:
        if pos + 1 < total:
            st.session_state["fila_pos"] = pos + 1
            st.rerun()
        _concluir_cadastro(salvos)
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
    if arquivo:
        repo.adicionar_comprovante(
            produto.id, arquivo.name, arquivo.getvalue(), TipoDocumento.NOTA_FISCAL
        )
    if foto:
        repo.salvar_foto(produto.id, *foto)
    salvos.append(produto)

    if pos + 1 < total:  # ainda há notas na fila: segue para a próxima
        st.session_state["fila_pos"] = pos + 1
        st.rerun()
    _concluir_cadastro(salvos)


def _ler_prazo_do_termo(produto: Produto, paginas: list[tuple[int, str]]) -> str:
    """Pede à IA o prazo de garantia que o termo informa. Se for diferente do cadastro, guarda a
    sugestão para a tela de detalhes. Devolve um texto para o aviso depois do upload."""
    try:
        with st.spinner("Lendo o prazo de garantia do termo..."):
            sugestao = sugerir_prazo(paginas)
    except Exception:  # IA fora do ar etc.: o prazo é um extra, o termo continua guardado
        return ""
    if sugestao is None:
        return " Não encontrei o prazo de garantia no termo."
    if sugestao.meses == produto.prazo_garantia_meses:
        return f" O prazo do termo ({sugestao.meses} meses) confere com o cadastro."
    st.session_state[f"sugestao_prazo_{produto.id}"] = sugestao
    return (
        f" O termo informa {sugestao.meses} meses e o cadastro tem {produto.prazo_garantia_meses}: "
        "veja a sugestão nos detalhes do produto."
    )


def _sugestao_de_prazo(repo: Repositorio, produto: Produto):
    """Caixa 'o termo diz X meses, usar?' dos detalhes do produto (só se houver sugestão)."""
    chave = f"sugestao_prazo_{produto.id}"
    sugestao = st.session_state.get(chave)
    if sugestao is None:
        return
    if sugestao.meses == produto.prazo_garantia_meses:  # já aplicado (ou igual): some
        st.session_state.pop(chave, None)
        return
    novo_vencimento = data_vencimento(replace(produto, prazo_garantia_meses=sugestao.meses))
    with st.container(border=True):
        st.markdown(f"💡 **O termo de garantia informa {sugestao.meses} meses** (o cadastro tem {produto.prazo_garantia_meses}).")
        st.caption(f"“{sugestao.trecho}”")
        st.caption(f"Com {sugestao.meses} meses, a garantia passa a vencer em {formatar_data(novo_vencimento)}.")
        coluna_usar, coluna_ignorar, _ = st.columns([1.6, 1, 3])
        if coluna_usar.button(f"Usar {sugestao.meses} meses", key=f"usar_prazo_{produto.id}", type="primary"):
            repo.atualizar_prazo(produto.id, sugestao.meses)
            st.session_state.pop(chave, None)
            st.rerun()
        if coluna_ignorar.button("Ignorar", key=f"ignorar_prazo_{produto.id}"):
            st.session_state.pop(chave, None)
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
            if tipo == TipoDocumento.TERMO_GARANTIA:
                aviso += _ler_prazo_do_termo(produto, paginas)
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
    st.caption(
        f"Garantia do fabricante: {produto.prazo_garantia_meses} meses, até "
        f"{formatar_data(fim_garantia_fabricante(produto))}. Depois dela, a garantia legal do CDC "
        f"({GARANTIA_LEGAL_DIAS} dias) segue valendo até {formatar_data(data_vencimento(produto))}."
    )
    if produto.valor:
        st.write(f"**Valor:** R$ {produto.valor:,.2f}")
    if produto.observacoes:
        st.write(f"**Observações:** {produto.observacoes}")
    _sugestao_de_prazo(repo, produto)

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

    nova_foto = seletor_de_foto(
        f"detalhe_{produto.id}_{st.session_state.get('foto_n', 0)}", "Foto do produto (enviar ou trocar)"
    )
    if nova_foto and st.button("Salvar foto", key=f"salvar_foto_{produto.id}"):
        repo.salvar_foto(produto.id, *nova_foto)
        st.session_state["foto_n"] = st.session_state.get("foto_n", 0) + 1  # chave nova: limpa o seletor
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


def seletor_de_foto(chave: str, rotulo: str) -> tuple[str, bytes] | None:
    """Foto do produto: sem foto, de um arquivo ou tirada pela câmera. Devolve (nome, bytes) ou None.

    A câmera só aparece quando o usuário a escolhe: se ficasse sempre na tela, o navegador pediria
    permissão da câmera toda vez que a página abrisse. Fica fora de st.form de propósito: dentro
    dele, nada reage (nem o troca-troca de origem) até clicar no botão do formulário."""
    origem = st.segmented_control(
        rotulo, ORIGENS, default=SEM_FOTO, key=f"foto_origem_{chave}"
    ) or SEM_FOTO  # fmt: skip
    arquivo = camera = None
    if origem == ARQUIVO:
        arquivo = st.file_uploader(
            "Escolha a foto", type=["png", "jpg", "jpeg", "webp"],
            key=f"foto_arquivo_{chave}", label_visibility="collapsed",
        )  # fmt: skip
    elif origem == CAMERA:
        camera = st.camera_input(
            "Tire a foto do produto", key=f"foto_camera_{chave}", label_visibility="collapsed"
        )
    return foto_escolhida(origem, arquivo, camera)


def estado_vazio(icone: str, titulo: str, texto: str):
    """Aviso amigável para quando não há nada para mostrar (em vez de uma frase seca)."""
    st.markdown(
        f'<div class="vazio"><div class="icone-grande">{icone}</div>'
        f'<div class="titulo-vazio">{html.escape(titulo)}</div>'
        f'<div class="texto-vazio">{html.escape(texto)}</div></div>',
        unsafe_allow_html=True,
    )


def _primeiro_nome(usuario) -> str:
    return (usuario.nome_fantasia or usuario.nome).split()[0]


def tela_boas_vindas(usuario):
    """Primeiro acesso (ainda sem produtos): três passos para começar, cada um com o seu botão."""
    st.markdown(
        f'<div class="boas-vindas"><div class="titulo-bv">👋 Bem-vindo ao {NOME_APP}, '
        f"{html.escape(_primeiro_nome(usuario))}!</div>"
        '<div class="texto-bv">Guarde suas notas fiscais e nunca mais perca o prazo de uma garantia. '
        "Comece por aqui:</div></div>",
        unsafe_allow_html=True,
    )
    perfil_feito = usuario.tipo is not None
    passos = [
        ("1", "Cadastre sua primeira nota", False,
         "Envie a foto ou o PDF da nota fiscal. A IA lê os dados e você só confere.",
         "Cadastrar nota", _ir_para, (PAGINA_CADASTRO,), True),
        ("2", "Complete seu perfil", perfil_feito,
         "Diga se você é pessoa física ou empresa e informe seu CPF ou CNPJ.",
         "Revisar perfil" if perfil_feito else "Completar perfil", _abrir_perfil, (), False),
        ("3", "Tire dúvidas com o assistente", False,
         "Pergunte sobre garantias e sobre os seus direitos de consumidor.",
         "Abrir o assistente", _ir_para, (PAGINA_PERGUNTAS,), False),
    ]  # fmt: skip
    for coluna, (numero, titulo, feito, texto, botao, acao, args, destaque) in zip(
        st.columns(3), passos
    ):
        with coluna, st.container(border=True, height=210):
            marca = "✔" if feito else numero
            st.markdown(
                f'<span class="numero-passo{" feito" if feito else ""}">{marca}</span>'
                f'<span class="titulo-passo">{html.escape(titulo)}</span>',
                unsafe_allow_html=True,
            )
            st.caption(texto)
            st.button(
                botao, on_click=acao, args=args, key=f"passo_{numero}",
                type="primary" if destaque else "secondary", use_container_width=True,
            )  # fmt: skip


MAXIMO_NA_FAIXA = 5


def faixa_de_avisos(produtos: list[Produto], usuario):
    """Garantias perto do fim, conforme a antecedência escolhida nas Preferências."""
    avisos = avisos_de_vencimento(produtos, date.today(), usuario.avisar_dias)
    if not avisos:
        return
    with st.container(border=True):
        st.markdown(
            f'<div class="titulo-secao">🔔 Garantias para ficar de olho ({len(avisos)})</div>'
            f'<div class="sub-secao">Vencem em até {max(usuario.avisar_dias)} dias</div>',
            unsafe_allow_html=True,
        )
        for aviso in avisos[:MAXIMO_NA_FAIXA]:
            classe = "urgente" if aviso.urgente else "aviso"
            st.markdown(
                f'<div class="linha-vencimento"><div><span class="nome-produto">{html.escape(aviso.produto.nome)}</span>'
                f'<div class="loja-produto">{html.escape(aviso.produto.loja)} · vence em {formatar_data(aviso.vencimento)}</div></div>'
                f'<span class="quando {classe}">{quando(aviso.dias)}</span></div>',
                unsafe_allow_html=True,
            )
        if len(avisos) > MAXIMO_NA_FAIXA:
            st.caption(f"…e mais {len(avisos) - MAXIMO_NA_FAIXA}. Veja todas no Painel.")
    st.write("")


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
    if not todos:  # primeiro acesso: nada de cartões zerados nem filtros, só os primeiros passos
        tela_boas_vindas(st.session_state["usuario"])
        return

    faixa_de_avisos(todos, st.session_state["usuario"])

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
        estado_vazio(
            "🔍", "Nenhum produto encontrado",
            "Nada combina com a busca ou com os filtros escolhidos. "
            'Tente outro termo ou escolha "Todos" e "Todas as categorias".',
        )  # fmt: skip
        return

    for produto in produtos:
        linha_produto(repo, base, produto, similaridades.get(produto.id))


def _grafico_gasto(gastos: list[tuple[str, float]]) -> alt.Chart:
    """Barras horizontais, da maior para a menor, com o valor escrito na ponta de cada uma."""
    dados = pd.DataFrame(
        [{"categoria": nome, "total": total, "texto": formatar_real(total)} for nome, total in gastos]
    )
    barras = alt.Chart(dados).mark_bar(color=_cores()["grafico"], size=18, cornerRadiusEnd=4).encode(
        y=alt.Y("categoria:N", sort="-x", title=None, axis=alt.Axis(labelLimit=180, ticks=False, domain=False)),
        x=alt.X("total:Q", title=None, axis=None, scale=alt.Scale(domain=[0, gastos[0][1] * 1.45])),
        tooltip=[alt.Tooltip("categoria:N", title="Categoria"), alt.Tooltip("texto:N", title="Gasto")],
    )  # fmt: skip
    rotulos = barras.mark_text(align="left", dx=6, color=_cores()["grafico-texto"], fontSize=12).encode(text="texto:N")
    return (barras + rotulos).properties(height=34 * len(gastos) + 8).configure_view(strokeWidth=0)


def _grafico_vencimentos(meses: list[tuple[date, int]]) -> alt.Chart:
    """Colunas por mês (os meses sem vencimento ficam vazios) e a quantidade em cima de cada uma."""
    dados = pd.DataFrame([{"mes": rotulo_mes(mes), "quantidade": n} for mes, n in meses])
    colunas = alt.Chart(dados).mark_bar(
        color=_cores()["grafico"], size=22, cornerRadiusTopLeft=4, cornerRadiusTopRight=4
    ).encode(
        x=alt.X("mes:N", sort=None, title=None, axis=alt.Axis(labelAngle=0, ticks=False, domain=False)),
        y=alt.Y("quantidade:Q", title=None, axis=alt.Axis(tickMinStep=1, format="d", grid=True, domain=False)),
        tooltip=[alt.Tooltip("mes:N", title="Mês"), alt.Tooltip("quantidade:Q", title="Garantias que vencem")],
    )  # fmt: skip
    rotulos = (
        colunas.mark_text(dy=-8, color=_cores()["grafico-texto"], fontSize=12)
        .encode(text="quantidade:Q")
        .transform_filter("datum.quantidade > 0")
    )
    return (colunas + rotulos).properties(height=260).configure_view(strokeWidth=0)


def tela_painel(repo: Repositorio):
    cabecalho("Painel", "Quanto você gastou, em quê, e o que vence nos próximos meses.")
    produtos = repo.listar()
    if not produtos:
        estado_vazio(
            "📊", "O painel ainda está vazio",
            "Cadastre seus produtos, de preferência com o valor, para ver quanto você gastou, "
            "em quê e quando cada garantia termina.",
        )  # fmt: skip
        st.button("＋ Cadastrar produto", type="primary", on_click=_ir_para, args=(PAGINA_CADASTRO,))
        return

    hoje = date.today()
    r = resumo(produtos, hoje)
    c1, c2, c3, c4 = st.columns(4)
    c1.markdown(cartao("💰", "azul", formatar_real(r.total_gasto), "Total investido"), unsafe_allow_html=True)
    c2.markdown(
        cartao("🛡️", "verde", formatar_real(r.valor_sob_garantia), "Valor sob garantia"),
        unsafe_allow_html=True,
    )
    c3.markdown(
        cartao("⏳", "amarelo", r.vencem_em_breve, f"Vencem em até {DIAS_ALERTA} dias"),
        unsafe_allow_html=True,
    )
    c4.markdown(cartao("📦", "azul", r.produtos, "Produtos cadastrados"), unsafe_allow_html=True)
    if r.sem_valor:
        st.caption(
            f"{r.sem_valor} produto(s) sem valor informado não entram nos totais em reais. "
            "Preencha o valor nos detalhes para incluí-los."
        )
    st.write("")

    coluna_gasto, coluna_tempo = st.columns(2)
    with coluna_gasto, st.container(border=True, height=ALTURA_QUADRO):
        st.markdown(
            '<div class="titulo-secao">Gasto por categoria</div>'
            '<div class="sub-secao">Quanto você investiu em cada tipo de produto</div>',
            unsafe_allow_html=True,
        )
        gastos = gasto_por_categoria(produtos)
        if gastos:
            st.altair_chart(_grafico_gasto(gastos), use_container_width=True)
        else:
            st.caption("Nenhum produto tem valor informado ainda.")

    with coluna_tempo, st.container(border=True, height=ALTURA_QUADRO):
        st.markdown(
            '<div class="titulo-secao">Vencimentos nos próximos 12 meses</div>'
            '<div class="sub-secao">Quantas garantias terminam em cada mês</div>',
            unsafe_allow_html=True,
        )
        meses = vencimentos_por_mes(produtos, hoje)
        if any(n for _, n in meses):
            st.altair_chart(_grafico_vencimentos(meses), use_container_width=True)
        else:
            st.caption("Nenhuma garantia vence nos próximos 12 meses.")

    with st.container(border=True):
        st.markdown(
            '<div class="titulo-secao">O que perde a garantia em breve</div>'
            '<div class="sub-secao">Próximos 90 dias, do mais próximo ao mais distante</div>',
            unsafe_allow_html=True,
        )
        proximos = proximos_vencimentos(produtos, hoje, dias=90)
        if not proximos:
            st.caption("Nenhuma garantia vence nos próximos 90 dias. 🎉")
        for produto, vencimento, dias in proximos:
            classe = "aviso" if dias <= DIAS_ALERTA else "ok"
            quando = "vence hoje" if dias == 0 else f"faltam {dias} dias"
            st.markdown(
                f'<div class="linha-vencimento"><div><span class="nome-produto">{html.escape(produto.nome)}</span>'
                f'<div class="loja-produto">{html.escape(produto.loja)} · vence em {formatar_data(vencimento)}</div></div>'
                f'<span class="quando {classe}">{quando}</span></div>',
                unsafe_allow_html=True,
            )


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


def _sugerir(pergunta: str):
    st.session_state["pergunta_sugerida"] = pergunta


def _sugestoes_de_perguntas(repo: Repositorio):
    """Chat vazio: ideias de pergunta, clicáveis. As que falam do cadastro só aparecem se houver
    produtos, para não levar o usuário a uma resposta de 'você não tem nada cadastrado'."""
    estado_vazio(
        "💬", "Pergunte o que quiser sobre garantias",
        "Eu consulto o Código de Defesa do Consumidor, o termo de garantia dos seus produtos "
        "e o seu cadastro. Algumas ideias para começar:",
    )  # fmt: skip
    ideias = [
        "Em quantos dias posso desistir de uma compra feita pela internet?",
        "Meu produto deu defeito. O que a lei diz que eu posso fazer?",
    ]
    produtos = repo.listar()
    if produtos:
        ideias += [
            "Quais garantias vencem nos próximos 30 dias?",
            f"Quando vence a garantia do meu {produtos[0].nome}?",
        ]
    for coluna, (i, ideia) in zip(st.columns(2) * 2, enumerate(ideias)):
        coluna.button(ideia, on_click=_sugerir, args=(ideia,), key=f"ideia_{i}", use_container_width=True)
    if not produtos:
        st.caption("Cadastre um produto para também poder perguntar sobre as suas garantias.")


def tela_perguntas(repo: Repositorio, base: BaseConhecimento, indexacao: dict):
    cabecalho("Como posso ajudar?", "Pergunte sobre suas garantias e seus direitos de consumidor.")

    if "conversa" not in st.session_state:
        st.session_state["conversa"] = Conversa(repo, base, criar_llm())
        st.session_state["historico"] = []
    conversa: Conversa = st.session_state["conversa"]
    historico: list = st.session_state["historico"]

    # A caixa de texto fica fixa no rodapé da página, onde quer que seja chamada. Chamamos antes de
    # desenhar para saber se há pergunta nova (digitada ou clicada nas sugestões).
    entrada = st.chat_input("Ex.: a garantia cobre tela quebrada?") or st.session_state.pop(
        "pergunta_sugerida", None
    )

    if historico and st.button("Novo assunto"):
        conversa.reiniciar()
        historico.clear()
        st.rerun()

    for papel, conteudo in historico:
        mostrar_mensagem(papel, conteudo)

    if not historico and not entrada:
        _sugestoes_de_perguntas(repo)
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


def _pagina():
    st.set_page_config(
        page_title=NOME_APP,
        page_icon=str(ICONE),
        layout="wide",
        menu_items={"About": f"{NOME_APP}: suas notas e garantias, sempre à mão."},
    )
    st.markdown(estilo(), unsafe_allow_html=True)

    conexao = obter_conexao()
    indexacao = iniciar_indexacao_cdc()

    usuario = st.session_state.get("usuario")
    if usuario is None:  # "manter conectado": um cookie válido dispensa o login
        usuario = Usuarios(conexao).usuario_da_sessao(st.context.cookies.get(NOME_COOKIE))
        if usuario:
            st.session_state["usuario"] = usuario
    if usuario is None:
        if st.session_state.pop("limpar_cookie", False):
            _definir_cookie("", 0)
        tela_acesso(Usuarios(conexao))
        return

    token_novo = st.session_state.pop("cookie_para_gravar", None)
    if token_novo:
        _definir_cookie(token_novo, DURACAO_SESSAO_DIAS)

    repo = Repositorio(conexao, usuario.id)  # só enxerga os produtos deste usuário
    base = BaseConhecimento(conexao)

    if not st.session_state.get("avisos_dados"):  # só na primeira tela de cada sessão
        st.session_state["avisos_dados"] = True
        avisos = avisos_de_vencimento(repo.listar(), date.today(), usuario.avisar_dias)
        if avisos:
            primeiro = avisos[0]
            resto = f" e mais {len(avisos) - 1}" if len(avisos) > 1 else ""
            st.toast(
                f"{primeiro.produto.nome}: {quando(primeiro.dias)}{resto}", icon="🔔", duration=8
            )

    # Navegação pedida por código (ex.: depois de salvar): precisa acontecer antes de o menu
    # ser desenhado, porque o Streamlit não deixa mudar um widget depois que ele existe.
    if "ir_para" in st.session_state:
        st.session_state["pagina"] = st.session_state.pop("ir_para")

    with st.sidebar:
        st.image(str(LOGO), width=140)
        st.session_state.setdefault("pagina", PAGINA_LISTA)  # página inicial (o state vence o index)
        pagina = st.radio(
            "Menu", PAGINAS, index=None, key="pagina", label_visibility="collapsed",
            on_change=_fechar_tela_da_conta,
        )  # fmt: skip
        with st.container(key="rodape_usuario"):
            coluna_menu, coluna_sair = st.columns([5, 1], vertical_alignment="center", gap="small")
            with coluna_menu.popover(
                usuario.nome, icon=":material/account_circle:", use_container_width=True
            ):
                st.html(  # HTML, não markdown: o markdown transformaria o e-mail em link azul
                    f'<div style="color:var(--texto-fraco);font-size:0.85rem">{html.escape(usuario.email)}</div>'
                )
                st.button(
                    "Editar perfil", icon=":material/badge:", on_click=_abrir_perfil,
                    use_container_width=True,
                )  # fmt: skip
                st.button(
                    "Preferências", icon=":material/tune:", on_click=_abrir_preferencias,
                    use_container_width=True,
                )  # fmt: skip
            coluna_sair.button("", icon=":material/logout:", on_click=_sair, help="Sair")

    mensagem = st.session_state.pop("mensagem_sucesso", None)  # mostra uma vez só
    if mensagem:
        st.success(mensagem)

    if st.session_state.get("tela_perfil"):
        tela_perfil(Usuarios(conexao), usuario)
    elif st.session_state.get("tela_preferencias"):
        tela_preferencias(Usuarios(conexao), usuario)
    elif pagina == PAGINA_PAINEL:
        tela_painel(repo)
    elif pagina == PAGINA_CADASTRO:
        tela_cadastro(repo)
    elif pagina == PAGINA_PERGUNTAS:
        tela_perguntas(repo, base, indexacao)
    else:
        tela_lista(repo, base)


@st.fragment(run_every=2)
def _vigiar_tema(escuro_usado: bool):
    """Trocar o tema no menu ⋮ muda as cores do Streamlit na hora, mas não executa o script de
    novo, e as nossas cores ficariam no tema antigo. Este trecho invisível confere a cada 2
    segundos: se o tema mudou desde a última execução completa, redesenha a página."""
    if _tema_escuro() != escuro_usado:
        st.rerun()


def main():
    _pagina()
    _vigiar_tema(_tema_escuro())


main()
