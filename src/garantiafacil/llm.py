"""Camada única de acesso ao LLM.

O resto do projeto chama `criar_llm().perguntar(...)` e não sabe qual provedor responde.
Para trocar de provedor, mude LLM_PROVIDER no .env.
"""

import base64
import os

from dotenv import load_dotenv
from pydantic import BaseModel

load_dotenv()  # lê o arquivo .env para as variáveis de ambiente


class OllamaLlm:
    """Modelo rodando local, via Ollama."""

    def __init__(self, modelo: str, modelo_visao: str | None = None):
        self.modelo = modelo
        self.modelo_visao = modelo_visao or modelo  # modelos de texto puro não leem imagem

    def estruturar(
        self, prompt: str, formato: type[BaseModel], sistema: str | None = None
    ) -> BaseModel:
        """Como `extrair`, mas só com texto: devolve a resposta no formato (classe Pydantic) pedido."""
        import ollama

        mensagens = []
        if sistema:
            mensagens.append({"role": "system", "content": sistema})
        mensagens.append({"role": "user", "content": prompt})

        resposta = ollama.chat(
            model=self.modelo,
            messages=mensagens,
            format=formato.model_json_schema(),
            options={"temperature": 0},
        )
        return formato.model_validate_json(resposta.message.content)

    def extrair(
        self,
        prompt: str,
        imagem: bytes,
        formato: type[BaseModel],
        sistema: str | None = None,
        tipo_midia: str = "image/jpeg",  # só o Claude precisa; o Ollama detecta sozinho
    ) -> BaseModel:
        """Lê uma imagem e devolve os dados no formato (classe Pydantic) pedido."""
        import ollama

        mensagens = []
        if sistema:
            mensagens.append({"role": "system", "content": sistema})
        mensagens.append({"role": "user", "content": prompt, "images": [imagem]})

        resposta = ollama.chat(
            model=self.modelo_visao,
            messages=mensagens,
            format=formato.model_json_schema(),  # força a resposta a seguir o schema JSON
            options={"temperature": 0},  # extração de dados pede estabilidade
        )
        return formato.model_validate_json(resposta.message.content)

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

    def estruturar(
        self, prompt: str, formato: type[BaseModel], sistema: str | None = None
    ) -> BaseModel:
        """Como `extrair`, mas só com texto."""
        import anthropic

        client = anthropic.Anthropic()
        resposta = client.messages.create(
            model=self.modelo,
            max_tokens=1024,
            system=sistema or "",
            temperature=0,
            tools=[
                {
                    "name": "registrar_dados",
                    "description": "Registra a resposta no formato pedido.",
                    "input_schema": formato.model_json_schema(),
                }
            ],
            tool_choice={"type": "tool", "name": "registrar_dados"},
            messages=[{"role": "user", "content": prompt}],
        )
        bloco = next(b for b in resposta.content if b.type == "tool_use")
        return formato.model_validate(bloco.input)

    def extrair(
        self,
        prompt: str,
        imagem: bytes,
        formato: type[BaseModel],
        sistema: str | None = None,
        tipo_midia: str = "image/jpeg",
    ) -> BaseModel:
        """Lê uma imagem e devolve os dados no formato (classe Pydantic) pedido.

        No Claude, a saída estruturada é feita por "tool use": definimos uma ferramenta cujo
        schema é o nosso formato e obrigamos o modelo a chamá-la."""
        import anthropic

        client = anthropic.Anthropic()
        resposta = client.messages.create(
            model=self.modelo,
            max_tokens=1024,
            system=sistema or "",
            temperature=0,
            tools=[
                {
                    "name": "registrar_dados",
                    "description": "Registra os dados extraídos da imagem.",
                    "input_schema": formato.model_json_schema(),
                }
            ],
            tool_choice={"type": "tool", "name": "registrar_dados"},
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": tipo_midia,
                                "data": base64.b64encode(imagem).decode(),
                            },
                        },
                        {"type": "text", "text": prompt},
                    ],
                }
            ],
        )
        bloco = next(b for b in resposta.content if b.type == "tool_use")
        return formato.model_validate(bloco.input)

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
    return OllamaLlm(
        os.getenv("OLLAMA_MODEL", "llama3.2:3b"),
        modelo_visao=os.getenv("OLLAMA_MODELO_VISAO", "qwen2.5vl:3b"),
    )
