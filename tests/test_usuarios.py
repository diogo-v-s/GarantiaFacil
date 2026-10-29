from datetime import datetime, timedelta, timezone

import pytest

from garantiafacil.db import conectar
from garantiafacil.modelos import TipoPessoa
from garantiafacil.usuarios import (
    ErroDeCadastro,
    Usuarios,
    conferir_senha,
    gerar_hash,
)


@pytest.fixture
def usuarios():
    return Usuarios(conectar(":memory:"))


def test_hash_nao_guarda_a_senha_e_muda_a_cada_vez():
    primeiro, segundo = gerar_hash("minha-senha-123"), gerar_hash("minha-senha-123")

    assert "minha-senha-123" not in primeiro
    assert primeiro != segundo  # o sal é aleatório: mesma senha, hashes diferentes


def test_conferir_senha_certa_e_errada():
    guardado = gerar_hash("minha-senha-123")

    assert conferir_senha("minha-senha-123", guardado)
    assert not conferir_senha("minha-senha-124", guardado)
    assert not conferir_senha("", guardado)


def test_hash_corrompido_nao_confere_nem_quebra():
    assert not conferir_senha("x", "isto não é um hash")
    assert not conferir_senha("x", "md5$1$2$3$4$5")
    assert not conferir_senha("x", "")


def test_criar_e_entrar(usuarios):
    criado = usuarios.criar("  Ana@Exemplo.com ", "senha-segura-1", " Ana Souza ")

    assert (criado.email, criado.nome) == ("ana@exemplo.com", "Ana Souza")
    entrou = usuarios.autenticar("ANA@exemplo.com", "senha-segura-1")  # e-mail sem distinguir caixa
    assert entrou == criado


def test_senha_errada_e_email_inexistente_dao_o_mesmo_resultado(usuarios):
    usuarios.criar("ana@exemplo.com", "senha-segura-1", "Ana")

    assert usuarios.autenticar("ana@exemplo.com", "outra-senha-1") is None
    assert usuarios.autenticar("ninguem@exemplo.com", "senha-segura-1") is None


def test_o_banco_guarda_so_o_hash(usuarios):
    usuarios.criar("ana@exemplo.com", "senha-segura-1", "Ana")

    [linha] = usuarios.conexao.execute("SELECT senha_hash FROM usuarios").fetchall()
    assert "senha-segura-1" not in linha["senha_hash"]
    assert linha["senha_hash"].startswith("scrypt$")


@pytest.mark.parametrize(
    "email, senha, nome, trecho",
    [
        ("sem-arroba", "senha-segura-1", "Ana", "e-mail"),
        ("ana@", "senha-segura-1", "Ana", "e-mail"),
        ("ana@exemplo.com", "curta", "Ana", "senha"),
        ("ana@exemplo.com", "senha-segura-1", "   ", "nome"),
    ],
)
def test_dados_invalidos_sao_recusados_com_mensagem(usuarios, email, senha, nome, trecho):
    with pytest.raises(ErroDeCadastro, match=trecho):
        usuarios.criar(email, senha, nome)


def test_email_repetido_e_recusado_mesmo_com_outra_caixa(usuarios):
    usuarios.criar("ana@exemplo.com", "senha-segura-1", "Ana")

    with pytest.raises(ErroDeCadastro, match="Já existe"):
        usuarios.criar("ANA@exemplo.com", "outra-senha-99", "Outra Ana")


# ---------- perfil PF/PJ ----------

@pytest.fixture
def ana(usuarios):
    return usuarios.criar("ana@exemplo.com", "senha-segura-1", "Ana")


def test_conta_nova_nao_tem_perfil_preenchido(ana):
    assert ana.tipo is None and ana.documento == "" and ana.telefone == ""


def test_perfil_pessoa_fisica(usuarios, ana):
    salvo = usuarios.atualizar_perfil(
        ana.id, TipoPessoa.FISICA, " Ana Souza ", "529.982.247-25", telefone="(11) 91234-5678"
    )

    assert salvo.tipo is TipoPessoa.FISICA
    assert (salvo.nome, salvo.documento, salvo.telefone) == ("Ana Souza", "52998224725", "11912345678")
    assert salvo.email == "ana@exemplo.com"  # o e-mail é o login e não muda aqui
    assert usuarios.autenticar("ana@exemplo.com", "senha-segura-1") == salvo  # perfil volta no login


def test_perfil_pessoa_juridica_guarda_nome_fantasia(usuarios, ana):
    salvo = usuarios.atualizar_perfil(
        ana.id, TipoPessoa.JURIDICA, "Ana Comércio LTDA", "11.222.333/0001-81", " Loja da Ana "
    )

    assert salvo.tipo is TipoPessoa.JURIDICA
    assert (salvo.nome, salvo.documento, salvo.nome_fantasia) == (
        "Ana Comércio LTDA", "11222333000181", "Loja da Ana",
    )  # fmt: skip


def test_voltar_para_pessoa_fisica_descarta_o_nome_fantasia(usuarios, ana):
    usuarios.atualizar_perfil(ana.id, TipoPessoa.JURIDICA, "Ana LTDA", "11222333000181", "Loja")

    salvo = usuarios.atualizar_perfil(ana.id, TipoPessoa.FISICA, "Ana", "52998224725", "Loja")

    assert salvo.nome_fantasia == ""


@pytest.mark.parametrize(
    "tipo, documento, trecho",
    [
        (TipoPessoa.FISICA, "529.982.247-24", "CPF inválido"),
        (TipoPessoa.FISICA, "11.222.333/0001-81", "CPF inválido"),  # CNPJ no lugar do CPF
        (TipoPessoa.JURIDICA, "529.982.247-25", "CNPJ inválido"),  # CPF no lugar do CNPJ
        (TipoPessoa.JURIDICA, "", "CNPJ inválido"),
    ],
)
def test_documento_invalido_ou_do_tipo_errado_e_recusado(usuarios, ana, tipo, documento, trecho):
    with pytest.raises(ErroDeCadastro, match=trecho):
        usuarios.atualizar_perfil(ana.id, tipo, "Ana", documento)


def test_nome_vazio_e_telefone_incompleto_sao_recusados(usuarios, ana):
    with pytest.raises(ErroDeCadastro, match="seu nome"):
        usuarios.atualizar_perfil(ana.id, TipoPessoa.FISICA, "  ", "52998224725")
    with pytest.raises(ErroDeCadastro, match="razão social"):
        usuarios.atualizar_perfil(ana.id, TipoPessoa.JURIDICA, "", "11222333000181")
    with pytest.raises(ErroDeCadastro, match="Telefone"):
        usuarios.atualizar_perfil(ana.id, TipoPessoa.FISICA, "Ana", "52998224725", telefone="1234")


def test_perfil_recusado_nao_altera_o_que_estava_salvo(usuarios, ana):
    usuarios.atualizar_perfil(ana.id, TipoPessoa.FISICA, "Ana Souza", "52998224725")

    with pytest.raises(ErroDeCadastro):
        usuarios.atualizar_perfil(ana.id, TipoPessoa.FISICA, "Outro Nome", "00000000000")

    assert usuarios.obter(ana.id).nome == "Ana Souza"


def test_banco_com_usuarios_antigos_ganha_as_colunas_do_perfil(tmp_path):
    import sqlite3

    from garantiafacil.db import conectar

    caminho = tmp_path / "antigo.db"
    antigo = sqlite3.connect(caminho)
    antigo.executescript(
        "CREATE TABLE usuarios (id INTEGER PRIMARY KEY AUTOINCREMENT, email TEXT NOT NULL UNIQUE, "
        "senha_hash TEXT NOT NULL, nome TEXT NOT NULL, criado_em TEXT NOT NULL DEFAULT "
        "(datetime('now')));"
        f"INSERT INTO usuarios (email, senha_hash, nome) VALUES ('a@a.com', '{gerar_hash('x' * 8)}', 'Ana');"
    )
    antigo.commit()
    antigo.close()

    usuarios = Usuarios(conectar(caminho))

    assert usuarios.obter(1).tipo is None
    assert usuarios.atualizar_perfil(1, TipoPessoa.FISICA, "Ana", "52998224725").documento == "52998224725"


# ---------- manter conectado ----------

def test_sessao_devolve_o_usuario_dono_do_token(usuarios, ana):
    token = usuarios.criar_sessao(ana.id)

    assert usuarios.usuario_da_sessao(token) == ana


def test_sessao_com_token_desconhecido_ou_vazio_nao_entra(usuarios, ana):
    usuarios.criar_sessao(ana.id)

    assert usuarios.usuario_da_sessao("token-inventado") is None
    assert usuarios.usuario_da_sessao("") is None
    assert usuarios.usuario_da_sessao(None) is None


def test_sessao_expira(usuarios, ana):
    agora = datetime(2026, 10, 29, tzinfo=timezone.utc)
    token = usuarios.criar_sessao(ana.id, dias=30, agora=agora)

    assert usuarios.usuario_da_sessao(token, agora + timedelta(days=29)) == ana
    assert usuarios.usuario_da_sessao(token, agora + timedelta(days=30)) is None


def test_encerrar_sessao_invalida_o_token(usuarios, ana):
    token = usuarios.criar_sessao(ana.id)

    usuarios.encerrar_sessao(token)

    assert usuarios.usuario_da_sessao(token) is None


def test_o_banco_nao_guarda_o_token_so_o_hash(usuarios, ana):
    token = usuarios.criar_sessao(ana.id)

    [linha] = usuarios.conexao.execute("SELECT token_hash FROM sessoes").fetchall()
    assert token not in linha["token_hash"] and len(linha["token_hash"]) == 64


def test_cada_sessao_tem_o_proprio_token_e_sessoes_vencidas_somem(usuarios, ana):
    velha = datetime(2026, 1, 1, tzinfo=timezone.utc)
    usuarios.criar_sessao(ana.id, dias=1, agora=velha)

    primeiro, segundo = usuarios.criar_sessao(ana.id), usuarios.criar_sessao(ana.id)

    assert primeiro != segundo
    total = usuarios.conexao.execute("SELECT COUNT(*) FROM sessoes").fetchone()[0]
    assert total == 2  # a de janeiro foi limpa na criação da próxima


def test_sessao_some_junto_com_a_conta(usuarios, ana):
    token = usuarios.criar_sessao(ana.id)

    usuarios.conexao.execute("DELETE FROM usuarios WHERE id = ?", (ana.id,))

    assert usuarios.usuario_da_sessao(token) is None
