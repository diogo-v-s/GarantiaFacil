"""Camada única de acesso ao LLM.

O resto do projeto chama `criar_llm().perguntar(...)` e não sabe qual provedor responde.
Para trocar de provedor, mude LLM_PROVIDER no .env.
"""

import os

from dotenv import load_dotenv

load_dotenv()  # lê o arquivo .env para as variáveis de ambiente


class OllamaLlm:
    """Modelo rodando local, via Ollama."""

    def __init__(self, modelo: str):
        self.modelo = modelo

    def perguntar(
        self, prompt: str, sistema: str | None = None, temperatura: float | None = None
    ) -> str:
        import ollama

        mensagens = []
        if sistema:
            mensagens.append({"role": "system", "content": sistema})
        mensagens.append({"role": "user", "content": prompt})

        # No Ollama, parâmetros de geração vão dentro de "options"
        opcoes = {}
        if temperatura is not None:
            opcoes["temperature"] = temperatura

        resposta = ollama.chat(model=self.modelo, messages=mensagens, options=opcoes)
        return resposta.message.content


class ClaudeLlm:
    """Claude, via API da Anthropic."""

    def __init__(self, modelo: str):
        self.modelo = modelo

    def perguntar(
        self, prompt: str, sistema: str | None = None, temperatura: float | None = None
    ) -> str:
        import anthropic

        client = anthropic.Anthropic()  # usa ANTHROPIC_API_KEY do ambiente

        # Na API da Anthropic, a temperatura é um argumento direto (0 a 1)
        extras = {}
        if temperatura is not None:
            extras["temperature"] = temperatura

        resposta = client.messages.create(
            model=self.modelo,
            max_tokens=1024,
            system=sistema or "",
            messages=[{"role": "user", "content": prompt}],
            **extras,
        )
        return resposta.content[0].text


def criar_llm():
    """Escolhe o provedor conforme LLM_PROVIDER (padrão: ollama)."""
    provedor = os.getenv("LLM_PROVIDER", "ollama").lower()
    if provedor == "claude":
        return ClaudeLlm(os.getenv("CLAUDE_MODEL", "claude-haiku-5-5"))
    return OllamaLlm(os.getenv("OLLAMA_MODEL", "llama3.2:3b"))
