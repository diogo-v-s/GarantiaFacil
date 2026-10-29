from datetime import date
from pathlib import Path

import numpy as np
import pytest

from garantiafacil.db import conectar
from garantiafacil.modelos import Categoria, Produto
from garantiafacil.repositorio import Repositorio
from tests.ajuda import adotar_orfaos, banco_com_usuario


def embedding_falso(texto: str, consulta: bool = False) -> np.ndarray:
    """Dublê do modelo de embeddings: agrupa por categoria, sem chamar o Ollama.
    Geladeira e refrigerador compartilham o mesmo 'significado'."""
    texto = texto.lower()
    if "geladeira" in texto or "refrigerador" in texto:
        return np.array([1, 0, 0], dtype=np.float32)
    if "notebook" in texto:
        return np.array([0, 1, 0], dtype=np.float32)
    return np.array([0, 0, 1], dtype=np.float32)


@pytest.fixture
def repo(tmp_path):
    """Repositório novo para cada teste: banco em memória e comprovantes numa pasta temporária."""
    return Repositorio(
        *banco_com_usuario(),
        pasta_comprovantes=tmp_path / "comprovantes",
        gerar_embedding=embedding_falso,
        nome_modelo=lambda: "falso",
    )


def novo_produto(nome="Geladeira Brastemp", loja="Magazine", observacoes="") -> Produto:
    return Produto(
        nome=nome,
        loja=loja,
        data_compra=date(2026, 3, 5),
        prazo_garantia_meses=12,
        valor=3499.90,
        observacoes=observacoes,
    )


def test_adicionar_e_obter(repo):
    salvo = repo.adicionar(novo_produto())
    assert salvo.id is not None

    lido = repo.obter(salvo.id)
    assert lido == salvo


def test_obter_inexistente_retorna_none(repo):
    assert repo.obter(999) is None


def test_listar_ordena_pela_compra_mais_recente(repo):
    antigo = novo_produto("Antigo")
    antigo.data_compra = date(2025, 1, 1)
    repo.adicionar(antigo)
    repo.adicionar(novo_produto("Novo"))

    assert [p.nome for p in repo.listar()] == ["Novo", "Antigo"]


def test_buscar_por_nome_loja_e_observacao(repo):
    repo.adicionar(novo_produto("Geladeira", "Magazine"))
    repo.adicionar(novo_produto("Notebook", "Kabum", observacoes="comprado para o trabalho"))

    assert [p.nome for p in repo.buscar("gelad")] == ["Geladeira"]
    assert [p.nome for p in repo.buscar("kabum")] == ["Notebook"]
    assert [p.nome for p in repo.buscar("trabalho")] == ["Notebook"]
    assert repo.buscar("televisão") == []


def test_buscar_nao_acha_sinonimo(repo):
    """Documenta a limitação do LIKE, que a busca semântica (etapa 4) vai resolver."""
    repo.adicionar(novo_produto("Refrigerador"))
    assert repo.buscar("geladeira") == []


def test_comprovante_salva_arquivo_e_registro(repo):
    produto = repo.adicionar(novo_produto())
    comprovante = repo.adicionar_comprovante(produto.id, "nota.pdf", b"conteudo")

    assert comprovante.nome_original == "nota.pdf"
    assert repo.listar_comprovantes(produto.id) == [comprovante]
    with open(comprovante.caminho, "rb") as arquivo:
        assert arquivo.read() == b"conteudo"


def test_comprovante_descarta_pasta_do_nome(repo):
    produto = repo.adicionar(novo_produto())
    comprovante = repo.adicionar_comprovante(produto.id, "../../fora/nota.pdf", b"x")
    assert comprovante.nome_original == "nota.pdf"


def test_excluir_remove_produto_comprovantes_e_arquivos(repo):
    from pathlib import Path

    produto = repo.adicionar(novo_produto())
    comprovante = repo.adicionar_comprovante(produto.id, "nota.pdf", b"x")

    repo.excluir(produto.id)

    assert repo.obter(produto.id) is None
    assert repo.listar_comprovantes(produto.id) == []
    assert not Path(comprovante.caminho).exists()


# ---------- busca por significado ----------


def test_busca_semantica_acha_sinonimo(repo):
    repo.adicionar(novo_produto("Refrigerador Brastemp"))
    repo.adicionar(novo_produto("Notebook Dell"))

    resultado = repo.buscar_semantico("geladeira")

    assert [(p.nome, round(nota, 2)) for p, nota in resultado] == [("Refrigerador Brastemp", 1.0)]


def test_busca_semantica_respeita_o_minimo(repo):
    repo.adicionar(novo_produto("Notebook Dell"))

    assert repo.buscar_semantico("geladeira", minimo=0.5) == []
    assert len(repo.buscar_semantico("geladeira", minimo=0.0)) == 1


def test_busca_semantica_respeita_o_limite_e_ordena(repo):
    repo.adicionar(novo_produto("Geladeira A"))
    repo.adicionar(novo_produto("Geladeira B"))
    repo.adicionar(novo_produto("Geladeira C"))

    assert len(repo.buscar_semantico("geladeira", limite=2)) == 2


def test_busca_semantica_com_consulta_vazia(repo):
    repo.adicionar(novo_produto("Geladeira"))
    assert repo.buscar_semantico("   ") == []


def test_produto_e_salvo_mesmo_se_o_embedding_falhar(tmp_path):
    def quebrado(texto, consulta=False):
        raise ConnectionError("Ollama fora do ar")

    repo = Repositorio(
        *banco_com_usuario(),
        pasta_comprovantes=tmp_path,
        gerar_embedding=quebrado,
        nome_modelo=lambda: "falso",
    )

    salvo = repo.adicionar(novo_produto("Geladeira"))

    assert repo.obter(salvo.id) is not None
    assert repo.conexao.execute("SELECT COUNT(*) FROM embeddings").fetchone()[0] == 0


def test_reindexar_completa_o_que_faltou(tmp_path):
    ligado = {"ok": False}

    def instavel(texto, consulta=False):
        if not ligado["ok"]:
            raise ConnectionError("Ollama fora do ar")
        return embedding_falso(texto, consulta)

    repo = Repositorio(
        *banco_com_usuario(),
        pasta_comprovantes=tmp_path,
        gerar_embedding=instavel,
        nome_modelo=lambda: "falso",
    )
    repo.adicionar(novo_produto("Geladeira"))
    assert repo.reindexar() == 0  # ainda fora do ar

    ligado["ok"] = True
    assert repo.reindexar() == 1
    assert repo.reindexar() == 0  # nada mais a fazer
    assert len(repo.buscar_semantico("refrigerador")) == 1


def test_reindexar_refaz_quando_o_modelo_muda(tmp_path):
    modelo = {"nome": "modelo-a"}
    repo = Repositorio(
        *banco_com_usuario(),
        pasta_comprovantes=tmp_path,
        gerar_embedding=embedding_falso,
        nome_modelo=lambda: modelo["nome"],
    )
    repo.adicionar(novo_produto("Geladeira"))
    assert repo.buscar_semantico("geladeira", minimo=0.0) != []

    modelo["nome"] = "modelo-b"
    assert repo.buscar_semantico("geladeira", minimo=0.0) == []  # vetores do modelo antigo não servem
    assert repo.reindexar() == 1
    assert repo.buscar_semantico("geladeira", minimo=0.0) != []


def test_excluir_remove_o_embedding(repo):
    salvo = repo.adicionar(novo_produto("Geladeira"))
    repo.excluir(salvo.id)

    assert repo.conexao.execute("SELECT COUNT(*) FROM embeddings").fetchone()[0] == 0


# ---------- categoria ----------


def test_categoria_e_gravada_e_lida(repo):
    from garantiafacil.modelos import Categoria

    produto = novo_produto()
    produto.categoria = Categoria.ELETRODOMESTICOS
    salvo = repo.adicionar(produto)

    assert repo.obter(salvo.id).categoria is Categoria.ELETRODOMESTICOS


def test_categoria_e_opcional(repo):
    salvo = repo.adicionar(novo_produto())

    assert repo.obter(salvo.id).categoria is None


def test_banco_recusa_categoria_fora_do_dominio(repo):
    import sqlite3

    salvo = repo.adicionar(novo_produto())

    with pytest.raises(sqlite3.IntegrityError):
        repo.conexao.execute("UPDATE produtos SET categoria = 'Roupas' WHERE id = ?", (salvo.id,))


def test_banco_antigo_sem_coluna_categoria_e_migrado(tmp_path):
    import sqlite3

    caminho = tmp_path / "antigo.db"
    antigo = sqlite3.connect(caminho)
    antigo.execute(
        "CREATE TABLE produtos (id INTEGER PRIMARY KEY AUTOINCREMENT, nome TEXT NOT NULL, "
        "loja TEXT NOT NULL, data_compra TEXT NOT NULL, prazo_garantia_meses INTEGER NOT NULL, "
        "valor REAL, observacoes TEXT NOT NULL DEFAULT '')"
    )
    antigo.execute(
        "INSERT INTO produtos (nome, loja, data_compra, prazo_garantia_meses) "
        "VALUES ('Xbox', 'Loja', '2026-01-01', 12)"
    )
    antigo.commit()
    antigo.close()

    repo = Repositorio(*banco_com_usuario(caminho), gerar_embedding=embedding_falso, nome_modelo=lambda: "f")
    adotar_orfaos(repo)

    [produto] = repo.listar()
    assert produto.nome == "Xbox" and produto.categoria is None


def test_atualizar_categoria_de_produto_existente(repo):
    from garantiafacil.modelos import Categoria

    salvo = repo.adicionar(novo_produto())

    repo.atualizar_categoria(salvo.id, Categoria.FERRAMENTAS)
    assert repo.obter(salvo.id).categoria is Categoria.FERRAMENTAS

    repo.atualizar_categoria(salvo.id, None)
    assert repo.obter(salvo.id).categoria is None


# ---------- foto e tipo de documento ----------


def test_foto_do_produto_e_salva_e_trocada(repo):
    salvo = repo.adicionar(novo_produto())
    assert repo.obter(salvo.id).foto is None

    primeira = repo.salvar_foto(salvo.id, "a.jpg", b"1")
    segunda = repo.salvar_foto(salvo.id, "b.jpg", b"2")

    assert repo.obter(salvo.id).foto == segunda
    assert not Path(primeira).exists()  # a foto anterior é apagada
    assert Path(segunda).read_bytes() == b"2"


def test_excluir_produto_apaga_a_foto(repo):
    salvo = repo.adicionar(novo_produto())
    caminho = repo.salvar_foto(salvo.id, "a.jpg", b"1")

    repo.excluir(salvo.id)

    assert not Path(caminho).exists()


def test_documento_guarda_o_tipo_e_o_padrao_e_nota_fiscal(repo):
    from garantiafacil.modelos import TipoDocumento

    salvo = repo.adicionar(novo_produto())
    repo.adicionar_comprovante(salvo.id, "cupom.jpg", b"x")
    repo.adicionar_comprovante(salvo.id, "termo.pdf", b"y", TipoDocumento.TERMO_GARANTIA)

    tipos = [c.tipo for c in repo.listar_comprovantes(salvo.id)]

    assert tipos == [TipoDocumento.NOTA_FISCAL, TipoDocumento.TERMO_GARANTIA]


def test_banco_antigo_com_comprovantes_sem_tipo_e_migrado(tmp_path):
    import sqlite3

    from garantiafacil.modelos import TipoDocumento

    caminho = tmp_path / "antigo.db"
    antigo = sqlite3.connect(caminho)
    antigo.executescript(
        "CREATE TABLE produtos (id INTEGER PRIMARY KEY AUTOINCREMENT, nome TEXT NOT NULL, "
        "loja TEXT NOT NULL, data_compra TEXT NOT NULL, prazo_garantia_meses INTEGER NOT NULL, "
        "valor REAL, observacoes TEXT NOT NULL DEFAULT '');"
        "CREATE TABLE comprovantes (id INTEGER PRIMARY KEY AUTOINCREMENT, produto_id INTEGER "
        "NOT NULL, nome_original TEXT NOT NULL, caminho TEXT NOT NULL);"
        "INSERT INTO produtos (nome, loja, data_compra, prazo_garantia_meses) "
        "VALUES ('Xbox', 'Loja', '2026-01-01', 12);"
        "INSERT INTO comprovantes (produto_id, nome_original, caminho) VALUES (1, 'n.jpg', 'x');"
    )
    antigo.commit()
    antigo.close()

    repo = Repositorio(*banco_com_usuario(caminho), gerar_embedding=embedding_falso, nome_modelo=lambda: "f")
    adotar_orfaos(repo)

    assert repo.listar()[0].foto is None
    assert repo.listar_comprovantes(1)[0].tipo is TipoDocumento.NOTA_FISCAL


def test_banco_com_regra_antiga_de_categorias_e_reconstruido_sem_perder_dados(tmp_path):
    import sqlite3

    from garantiafacil.modelos import Categoria

    caminho = tmp_path / "antigo.db"
    antigo = sqlite3.connect(caminho)
    antigo.executescript(
        "CREATE TABLE produtos (id INTEGER PRIMARY KEY AUTOINCREMENT, nome TEXT NOT NULL, "
        "loja TEXT NOT NULL, data_compra TEXT NOT NULL, prazo_garantia_meses INTEGER NOT NULL, "
        "valor REAL, observacoes TEXT NOT NULL DEFAULT '', "
        "categoria TEXT CHECK (categoria IN ('Eletrodomésticos', 'Eletrônicos', 'Ferramentas')), "
        "foto TEXT);"
        "CREATE TABLE embeddings (produto_id INTEGER PRIMARY KEY REFERENCES produtos(id) "
        "ON DELETE CASCADE, modelo TEXT NOT NULL, vetor BLOB NOT NULL);"
        "INSERT INTO produtos (nome, loja, data_compra, prazo_garantia_meses, categoria, foto) "
        "VALUES ('Furadeira', 'Loja', '2026-01-01', 12, 'Ferramentas', 'f.jpg');"
        "INSERT INTO produtos (nome, loja, data_compra, prazo_garantia_meses) "
        "VALUES ('Xbox', 'Loja', '2026-02-01', 12);"
        "INSERT INTO embeddings VALUES (1, 'm', x'00');"
    )
    antigo.commit()
    antigo.close()

    repo = Repositorio(*banco_com_usuario(caminho), gerar_embedding=embedding_falso, nome_modelo=lambda: "f")
    adotar_orfaos(repo)

    furadeira = repo.obter(1)
    assert furadeira.categoria is Categoria.FERRAMENTAS and furadeira.foto == "f.jpg"
    assert repo.obter(2).categoria is None
    repo.atualizar_categoria(2, Categoria.OUTROS)  # a regra nova aceita as categorias novas
    assert repo.obter(2).categoria is Categoria.OUTROS

    # as ligações com as outras tabelas continuam valendo (exclusão em cascata)
    assert repo.conexao.execute("SELECT COUNT(*) FROM embeddings").fetchone()[0] == 1
    repo.excluir(1)
    assert repo.conexao.execute("SELECT COUNT(*) FROM embeddings").fetchone()[0] == 0


def test_reconstruir_so_acontece_uma_vez(tmp_path):
    caminho = tmp_path / "novo.db"
    conectar(caminho).close()

    conexao = conectar(caminho)  # segunda abertura: a regra já está atual, nada a refazer

    assert conexao.execute("SELECT name FROM sqlite_master WHERE name = 'produtos_novo'").fetchone() is None


# ---------- dados separados por usuário ----------


def dois_repositorios(tmp_path):
    """Dois usuários no MESMO banco, cada um com o seu repositório."""
    from garantiafacil.usuarios import Usuarios

    conexao, ana = banco_com_usuario(email="ana@exemplo.com")
    bia = Usuarios(conexao).criar("bia@exemplo.com", "senha-de-teste", "Bia").id
    base = dict(pasta_comprovantes=tmp_path, gerar_embedding=embedding_falso, nome_modelo=lambda: "f")
    return Repositorio(conexao, ana, **base), Repositorio(conexao, bia, **base)


def test_cada_usuario_ve_so_os_proprios_produtos(tmp_path):
    ana, bia = dois_repositorios(tmp_path)
    produto_da_ana = ana.adicionar(novo_produto("Geladeira da Ana"))
    bia.adicionar(novo_produto("Notebook da Bia"))

    assert [p.nome for p in ana.listar()] == ["Geladeira da Ana"]
    assert [p.nome for p in bia.listar()] == ["Notebook da Bia"]
    assert bia.obter(produto_da_ana.id) is None  # nem pelo id
    assert bia.buscar("Geladeira") == []
    nomes_semantico = [p.nome for p, _ in bia.buscar_semantico("geladeira", minimo=0.0)]
    assert "Geladeira da Ana" not in nomes_semantico  # minimo=0 devolve tudo que ela tem


def test_usuario_nao_altera_nem_apaga_produto_de_outro(tmp_path):
    ana, bia = dois_repositorios(tmp_path)
    produto = ana.adicionar(novo_produto("Geladeira da Ana"))

    bia.atualizar_categoria(produto.id, Categoria.FERRAMENTAS)
    bia.excluir(produto.id)

    assert ana.obter(produto.id) is not None
    assert ana.obter(produto.id).categoria is None


def test_usuario_nao_anexa_arquivo_em_produto_de_outro(tmp_path):
    ana, bia = dois_repositorios(tmp_path)
    produto = ana.adicionar(novo_produto())

    with pytest.raises(LookupError):
        bia.adicionar_comprovante(produto.id, "nota.pdf", b"x")
    with pytest.raises(LookupError):
        bia.salvar_foto(produto.id, "foto.png", b"x")
    assert bia.listar_comprovantes(produto.id) == []


def test_produto_sem_dono_nao_aparece_para_ninguem(repo):
    repo.conexao.execute(
        "INSERT INTO produtos (nome, loja, data_compra, prazo_garantia_meses) "
        "VALUES ('Antigo', 'Loja', '2026-01-01', 12)"
    )
    repo.conexao.commit()

    assert repo.listar() == [] and repo.buscar("Antigo") == []


def test_excluir_remove_a_pasta_do_produto(repo, tmp_path):
    produto = repo.adicionar(novo_produto())
    repo.adicionar_comprovante(produto.id, "nota.pdf", b"x")
    pasta = tmp_path / "comprovantes" / str(produto.id)
    assert pasta.exists()

    repo.excluir(produto.id)

    assert not pasta.exists()
