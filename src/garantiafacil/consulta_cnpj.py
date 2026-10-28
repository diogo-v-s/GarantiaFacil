"""Consulta a razão social de um CNPJ na BrasilAPI (serviço público e gratuito).

Só o CNPJ da empresa emitente sai da máquina; nenhum dado pessoal é enviado."""

import json
import urllib.error
import urllib.request

URL = "https://brasilapi.com.br/api/cnpj/v1/{cnpj}"


def buscar_razao_social(cnpj: str, timeout: float = 10.0) -> str | None:
    """Devolve a razão social ou None se a consulta falhar (sem internet, CNPJ inexistente...)."""
    requisicao = urllib.request.Request(
        URL.format(cnpj=cnpj), headers={"User-Agent": "garantiafacil-estudo"}
    )
    try:
        with urllib.request.urlopen(requisicao, timeout=timeout) as resposta:
            dados = json.load(resposta)
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
        return None
    return (dados.get("razao_social") or "").strip() or None
