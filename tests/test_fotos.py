from garantiafacil.fotos import (
    ARQUIVO,
    CAMERA,
    NOME_FOTO_DA_CAMERA,
    SEM_FOTO,
    foto_escolhida,
)


class Enviado:
    """Dublê do que o Streamlit devolve (UploadedFile): tem nome e conteúdo."""

    def __init__(self, conteudo: bytes, name: str = "foto.png"):
        self.name = name
        self._conteudo = conteudo

    def getvalue(self) -> bytes:
        return self._conteudo


def test_arquivo_escolhido_devolve_nome_e_conteudo():
    assert foto_escolhida(ARQUIVO, Enviado(b"abc", "geladeira.png"), None) == ("geladeira.png", b"abc")


def test_camera_escolhida_usa_nome_proprio():
    assert foto_escolhida(CAMERA, None, Enviado(b"xyz", "camera_input.jpg")) == (NOME_FOTO_DA_CAMERA, b"xyz")


def test_sem_foto_ignora_tudo():
    assert foto_escolhida(SEM_FOTO, Enviado(b"a"), Enviado(b"b")) is None


def test_so_a_origem_escolhida_conta():
    # enviou um arquivo, depois trocou para a câmera e ainda não tirou: não salva o arquivo velho
    assert foto_escolhida(CAMERA, Enviado(b"arquivo antigo"), None) is None
    assert foto_escolhida(ARQUIVO, None, Enviado(b"foto da camera")) is None


def test_origem_escolhida_mas_nada_enviado():
    assert foto_escolhida(ARQUIVO, None, None) is None
    assert foto_escolhida(CAMERA, None, None) is None
