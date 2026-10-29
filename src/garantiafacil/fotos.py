"""Escolha da foto do produto: de um arquivo ou tirada na hora pela câmera.

Só a origem escolhida vale. Quem enviou um arquivo e depois trocou para a câmera não quer que a foto
antiga do arquivo seja salva, então o que sobrou na outra origem é ignorado."""

SEM_FOTO = "Sem foto"
ARQUIVO = "Enviar arquivo"
CAMERA = "Tirar foto"
ORIGENS = [SEM_FOTO, ARQUIVO, CAMERA]

NOME_FOTO_DA_CAMERA = "foto-camera.jpg"  # a câmera do navegador entrega JPEG, sem nome próprio


def foto_escolhida(origem: str, arquivo, camera) -> tuple[str, bytes] | None:
    """(nome, bytes) da foto da origem escolhida, ou None se não escolheu ou ainda não enviou/tirou.

    `arquivo` e `camera` são o que o Streamlit devolve (objetos com `name` e `getvalue()`) ou None."""
    if origem == ARQUIVO and arquivo is not None:
        return arquivo.name, arquivo.getvalue()
    if origem == CAMERA and camera is not None:
        return NOME_FOTO_DA_CAMERA, camera.getvalue()
    return None
