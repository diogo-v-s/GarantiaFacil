import cv2
import numpy as np
import pytest

from garantiafacil.leitor_qr import ler_chave_do_qr
from tests.test_chave_acesso import montar_chave

pytestmark = pytest.mark.skipif(
    not hasattr(cv2, "QRCodeEncoder"), reason="esta versão do OpenCV não gera QR code"
)


def png_com_qr(texto: str) -> bytes:
    """Gera uma imagem com margem branca e o QR code, como num cupom fotografado."""
    qr = cv2.QRCodeEncoder.create().encode(texto)
    qr = cv2.resize(qr, None, fx=6, fy=6, interpolation=cv2.INTER_NEAREST)
    tela = np.full((qr.shape[0] + 200, qr.shape[1] + 200), 255, np.uint8)
    tela[100 : 100 + qr.shape[0], 100 : 100 + qr.shape[1]] = qr
    ok, buffer = cv2.imencode(".png", tela)
    assert ok
    return buffer.tobytes()


def test_le_chave_de_qr_com_url():
    chave = montar_chave()
    imagem = png_com_qr(f"https://exemplo.gov.br/nfce?p={chave}|2|1|1|HASH")

    assert ler_chave_do_qr(imagem) == chave


def test_qr_sem_chave_devolve_none():
    assert ler_chave_do_qr(png_com_qr("https://exemplo.com")) is None


def test_imagem_invalida_devolve_none():
    assert ler_chave_do_qr(b"isto nao e uma imagem") is None
