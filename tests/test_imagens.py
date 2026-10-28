from garantiafacil.imagens import imagem_padrao
from garantiafacil.modelos import Categoria


def test_cada_categoria_tem_imagem_propria():
    imagens = {imagem_padrao(c) for c in Categoria}

    assert len(imagens) == len(Categoria)
    assert all(i.startswith("<svg") for i in imagens)


def test_sem_categoria_usa_a_imagem_de_caixa():
    assert imagem_padrao(None) not in {imagem_padrao(c) for c in Categoria}
