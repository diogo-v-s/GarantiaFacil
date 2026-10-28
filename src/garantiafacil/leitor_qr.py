"""Lê o QR code de uma foto de nota fiscal e devolve os 44 dígitos da chave de acesso."""

import cv2
import numpy as np

from garantiafacil.chave_acesso import buscar_chave


def ler_chave_do_qr(imagem: bytes) -> str | None:
    """Devolve a chave (texto de 44 dígitos) ou None se não houver QR legível na foto.

    Tenta a imagem original e versões ampliadas em tons de cinza, porque fotos de celular
    costumam deixar o QR pequeno."""
    pixels = cv2.imdecode(np.frombuffer(imagem, np.uint8), cv2.IMREAD_COLOR)
    if pixels is None:
        return None

    cinza = cv2.cvtColor(pixels, cv2.COLOR_BGR2GRAY)
    detector = cv2.QRCodeDetector()

    for escala in (1.0, 1.5, 2.0):
        tentativa = (
            cinza
            if escala == 1.0
            else cv2.resize(cinza, None, fx=escala, fy=escala, interpolation=cv2.INTER_CUBIC)
        )
        texto, _, _ = detector.detectAndDecode(tentativa)
        chave = buscar_chave(texto or "")
        if chave:
            return chave
    return None
