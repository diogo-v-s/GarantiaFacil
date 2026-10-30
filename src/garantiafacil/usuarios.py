"""Usuários: cadastro, senha com hash e autenticação.

A senha nunca é guardada. Guardamos um hash: o resultado de uma função de mão única. Para conferir
o login, calculamos o hash da senha digitada e comparamos com o guardado; quem roubar o banco não
consegue voltar do hash para a senha. Duas defesas importantes:
  - sal (salt): um texto aleatório próprio de cada usuário, misturado à senha antes do hash, para
    que duas pessoas com a mesma senha não tenham o mesmo hash;
  - função lenta (scrypt): calcular um hash leva uma fração de segundo de propósito, o que torna
    inviável testar bilhões de senhas por segundo (o que faria um atacante com SHA-256 puro)."""

import base64
import hashlib
import hmac
import os
import re
import secrets
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from garantiafacil.avisos import DIAS_PADRAO, dias_para_texto, normalizar_dias, texto_para_dias
from garantiafacil.cpf_cnpj import so_digitos, validar_cnpj, validar_cpf
from garantiafacil.modelos import TipoPessoa

TAMANHO_MINIMO_SENHA = 8
DURACAO_SESSAO_DIAS = 30  # "manter conectado"
_PADRAO_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_SCRYPT = {"n": 2**14, "r": 8, "p": 1}  # custo da conta; guardado no hash para poder mudar depois


class ErroDeCadastro(ValueError):
    """Dado inválido ao criar a conta; a mensagem pode ser mostrada ao usuário."""


@dataclass
class Usuario:
    id: int
    email: str
    nome: str  # nome da pessoa (PF) ou razão social (PJ)
    tipo: TipoPessoa | None = None  # None até o usuário preencher o perfil
    documento: str = ""  # CPF ou CNPJ, só dígitos
    nome_fantasia: str = ""
    telefone: str = ""  # só dígitos
    avisar_dias: tuple[int, ...] = DIAS_PADRAO  # antecedência dos avisos de vencimento


def _linha_para_usuario(linha: sqlite3.Row) -> Usuario:
    return Usuario(
        id=linha["id"],
        email=linha["email"],
        nome=linha["nome"],
        tipo=TipoPessoa(linha["tipo"]) if linha["tipo"] else None,
        documento=linha["documento"] or "",
        nome_fantasia=linha["nome_fantasia"] or "",
        telefone=linha["telefone"] or "",
        avisar_dias=texto_para_dias(linha["avisar_dias"]),
    )


def _derivar(senha: str, sal: bytes, n: int, r: int, p: int) -> bytes:
    return hashlib.scrypt(senha.encode("utf-8"), salt=sal, n=n, r=r, p=p, dklen=32)


def gerar_hash(senha: str) -> str:
    """Formato: scrypt$n$r$p$sal$hash (sal e hash em base64)."""
    sal = os.urandom(16)
    resultado = _derivar(senha, sal, **_SCRYPT)
    return "$".join(
        [
            "scrypt",
            str(_SCRYPT["n"]),
            str(_SCRYPT["r"]),
            str(_SCRYPT["p"]),
            base64.b64encode(sal).decode(),
            base64.b64encode(resultado).decode(),
        ]
    )


def conferir_senha(senha: str, hash_guardado: str) -> bool:
    try:
        algoritmo, n, r, p, sal, esperado = hash_guardado.split("$")
        if algoritmo != "scrypt":
            return False
        calculado = _derivar(senha, base64.b64decode(sal), int(n), int(r), int(p))
        # compare_digest compara em tempo constante: um == vazaria, pelo tempo de resposta,
        # quantos bytes do início estão certos.
        return hmac.compare_digest(calculado, base64.b64decode(esperado))
    except (ValueError, TypeError):
        return False


# Hash de uma senha qualquer, calculado uma vez. Quando o e-mail não existe, conferimos a senha
# contra ele só para gastar o mesmo tempo: senão a demora revelaria quais e-mails têm conta.
_HASH_FALSO = gerar_hash("senha-que-ninguem-usa")


def _hash_token(token: str) -> str:
    # SHA-256 basta aqui: o token tem 256 bits aleatórios, então não há "senha fraca" para adivinhar
    # (a lentidão do scrypt só importa para senhas escolhidas por pessoas).
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def normalizar_email(email: str) -> str:
    return email.strip().lower()


class Usuarios:
    def __init__(self, conexao: sqlite3.Connection):
        self.conexao = conexao

    def criar(self, email: str, senha: str, nome: str) -> Usuario:
        email = normalizar_email(email)
        nome = nome.strip()
        if not _PADRAO_EMAIL.match(email):
            raise ErroDeCadastro("Informe um e-mail válido.")
        if not nome:
            raise ErroDeCadastro("Informe o seu nome.")
        if len(senha) < TAMANHO_MINIMO_SENHA:
            raise ErroDeCadastro(f"A senha precisa ter pelo menos {TAMANHO_MINIMO_SENHA} caracteres.")

        try:
            cursor = self.conexao.execute(
                "INSERT INTO usuarios (email, senha_hash, nome) VALUES (?, ?, ?)",
                (email, gerar_hash(senha), nome),
            )
        except sqlite3.IntegrityError:  # a coluna email é UNIQUE
            raise ErroDeCadastro("Já existe uma conta com esse e-mail.") from None
        self.conexao.commit()
        return Usuario(id=cursor.lastrowid, email=email, nome=nome)

    def autenticar(self, email: str, senha: str) -> Usuario | None:
        """Devolve o usuário se e-mail e senha conferem; None em qualquer outro caso (a tela
        mostra a mesma mensagem para e-mail inexistente e senha errada, para não revelar qual)."""
        linha = self.conexao.execute(
            "SELECT * FROM usuarios WHERE email = ?", (normalizar_email(email),)
        ).fetchone()
        if linha is None:
            conferir_senha(senha, _HASH_FALSO)
            return None
        if not conferir_senha(senha, linha["senha_hash"]):
            return None
        return _linha_para_usuario(linha)

    def obter_por_email(self, email: str) -> Usuario | None:
        linha = self.conexao.execute(
            "SELECT * FROM usuarios WHERE email = ?", (normalizar_email(email),)
        ).fetchone()
        return _linha_para_usuario(linha) if linha else None

    def obter(self, usuario_id: int) -> Usuario | None:
        linha = self.conexao.execute(
            "SELECT * FROM usuarios WHERE id = ?", (usuario_id,)
        ).fetchone()
        return _linha_para_usuario(linha) if linha else None

    # ---------- manter conectado ----------

    def criar_sessao(
        self, usuario_id: int, dias: int = DURACAO_SESSAO_DIAS, agora: datetime | None = None
    ) -> str:
        """Cria uma sessão de longa duração e devolve o token (que vai para o cookie do
        navegador). O banco só guarda o hash dele."""
        agora = agora or datetime.now(timezone.utc)
        self.conexao.execute("DELETE FROM sessoes WHERE expira_em <= ?", (agora.isoformat(),))
        token = secrets.token_urlsafe(32)
        self.conexao.execute(
            "INSERT INTO sessoes (usuario_id, token_hash, expira_em) VALUES (?, ?, ?)",
            (usuario_id, _hash_token(token), (agora + timedelta(days=dias)).isoformat()),
        )
        self.conexao.commit()
        return token

    def usuario_da_sessao(self, token: str | None, agora: datetime | None = None) -> Usuario | None:
        """O usuário dono do token, ou None se não existir, estiver expirado ou foi encerrado."""
        if not token:
            return None
        linha = self.conexao.execute(
            "SELECT u.*, s.expira_em FROM sessoes s JOIN usuarios u ON u.id = s.usuario_id "
            "WHERE s.token_hash = ?",
            (_hash_token(token),),
        ).fetchone()
        agora = agora or datetime.now(timezone.utc)
        if linha is None or datetime.fromisoformat(linha["expira_em"]) <= agora:
            return None
        return _linha_para_usuario(linha)

    def encerrar_sessao(self, token: str | None) -> None:
        if token:
            self.conexao.execute("DELETE FROM sessoes WHERE token_hash = ?", (_hash_token(token),))
            self.conexao.commit()

    def atualizar_avisos(self, usuario_id: int, dias) -> Usuario:
        """Grava com quantos dias de antecedência o usuário quer ser avisado (vazio = nenhum aviso)."""
        self.conexao.execute(
            "UPDATE usuarios SET avisar_dias = ? WHERE id = ?", (dias_para_texto(dias), usuario_id)
        )
        self.conexao.commit()
        return self.obter(usuario_id)

    def atualizar_perfil(
        self,
        usuario_id: int,
        tipo: TipoPessoa,
        nome: str,
        documento: str,
        nome_fantasia: str = "",
        telefone: str = "",
    ) -> Usuario:
        """Grava o perfil depois de validar. `nome` é o nome (PF) ou a razão social (PJ). O e-mail
        não muda aqui: é o login. Documento e telefone são guardados só com os dígitos."""
        nome = nome.strip()
        rotulo = "a razão social" if tipo is TipoPessoa.JURIDICA else "o seu nome"
        if not nome:
            raise ErroDeCadastro(f"Informe {rotulo}.")

        documento = so_digitos(documento)
        if tipo is TipoPessoa.FISICA and not validar_cpf(documento):
            raise ErroDeCadastro("CPF inválido. Confira os números.")
        if tipo is TipoPessoa.JURIDICA and not validar_cnpj(documento):
            raise ErroDeCadastro("CNPJ inválido. Confira os números.")

        telefone = so_digitos(telefone)
        if telefone and len(telefone) not in (10, 11):
            raise ErroDeCadastro("Telefone inválido: informe o DDD e o número.")

        # Nome fantasia só existe para empresa; ao voltar para PF ele é descartado.
        fantasia = nome_fantasia.strip() if tipo is TipoPessoa.JURIDICA else ""
        self.conexao.execute(
            "UPDATE usuarios SET tipo = ?, nome = ?, documento = ?, nome_fantasia = ?, telefone = ? "
            "WHERE id = ?",
            (tipo.value, nome, documento, fantasia, telefone, usuario_id),
        )
        self.conexao.commit()
        return self.obter(usuario_id)
