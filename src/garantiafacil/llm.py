"""Camada única de acesso ao LLM.

O resto do projeto chama `criar_llm().perguntar(...)` e não sabe qual provedor responde.
Para trocar de provedor, mude LLM_PROVIDER no .env.
"""

import base64
import os

from dotenv import load_dotenv
from pydantic import BaseModel

from garantiafacil.agente import Chamada, PassoLlm

load_dotenv()  # lê o arquivo .env para as variáveis de ambiente

# Máximo de tokens por resposta no Ollama: na CPU cada token custa caro e as respostas devem
# ser curtas. Remover o limite (ou subir) quando o chat passar para o Claude.
LIMITE_RESPOSTA_OLLAMA = 250


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
        opcoes = {"num_predict": LIMITE_RESPOSTA_OLLAMA}
        if temperatura is not None:
            opcoes["temperature"] = temperatura

        resposta = ollama.chat(model=self.modelo, messages=mensagens, options=opcoes)
        return resposta.message.content

    def passo(self, mensagens: list[dict], ferramentas: list, sistema: str | None = None) -> PassoLlm:
        """Uma volta do agente: o modelo responde com texto ou pede ferramentas.

        `mensagens` está no formato neutro de agente.py; aqui é traduzido para o do Ollama."""
        import ollama

        convertidas = [{"role": "system", "content": sistema}] if sistema else []
        for m in mensagens:
            if m["papel"] == "usuario":
                convertidas.append({"role": "user", "content": m["texto"]})
            elif m["papel"] == "assistente":
                msg = {"role": "assistant", "content": m["texto"]}
                if m["chamadas"]:
                    msg["tool_calls"] = [
                        {"function": {"name": c.nome, "arguments": c.argumentos}}
                        for c in m["chamadas"]
                    ]
                convertidas.append(msg)
            else:  # resultado de uma ferramenta
                convertidas.append(
                    {"role": "tool", "content": m["conteudo"], "tool_name": m["chamada"].nome}
                )

        resposta = ollama.chat(
            model=self.modelo,
            messages=convertidas,
            tools=[
                {
                    "type": "function",
                    "function": {
                        "name": f.nome,
                        "description": f.descricao,
                        "parameters": f.schema(),
                    },
                }
                for f in ferramentas
            ],
            options={"temperature": 0, "num_predict": LIMITE_RESPOSTA_OLLAMA},
        )
        chamadas = [
            # o Ollama não dá id às chamadas; usamos a posição
            Chamada(id=str(i), nome=c.function.name, argumentos=dict(c.function.arguments or {}))
            for i, c in enumerate(resposta.message.tool_calls or [])
        ]
        return PassoLlm(resposta.message.content or "", chamadas)


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

        # `temperatura` é ignorada: os modelos Claude 5 não aceitam esse parâmetro (o SDK 2.x
        # nem o expõe). Só o Ollama a usa.
        resposta = client.messages.create(
            model=self.modelo,
            max_tokens=1024,
            system=sistema or "",
            messages=[{"role": "user", "content": prompt}],
        )
        # O Claude 5 pode devolver blocos de raciocínio antes do texto: pega só os de texto.
        return "".join(b.text for b in resposta.content if b.type == "text")

    def passo(self, mensagens: list[dict], ferramentas: list, sistema: str | None = None) -> PassoLlm:
        """Uma volta do agente com o Claude (tool use).

        Diferença para o Ollama: o Claude exige que cada resultado volte com o id da chamada
        (`tool_use_id`) e dentro de uma mensagem do usuário."""
        import anthropic

        convertidas: list[dict] = []
        for m in mensagens:
            if m["papel"] == "usuario":
                convertidas.append({"role": "user", "content": m["texto"]})
            elif m["papel"] == "assistente":
                blocos = [{"type": "text", "text": m["texto"]}] if m["texto"].strip() else []
                blocos += [
                    {"type": "tool_use", "id": c.id, "name": c.nome, "input": c.argumentos}
                    for c in m["chamadas"]
                ]
                convertidas.append({"role": "assistant", "content": blocos})
            else:
                bloco = {
                    "type": "tool_result",
                    "tool_use_id": m["chamada"].id,
                    "content": m["conteudo"],
                }
                anterior = convertidas[-1]
                if anterior["role"] == "user" and isinstance(anterior["content"], list):
                    anterior["content"].append(bloco)  # vários resultados, uma só mensagem
                else:
                    convertidas.append({"role": "user", "content": [bloco]})

        resposta = anthropic.Anthropic().messages.create(
            model=self.modelo,
            max_tokens=1024,
            system=sistema or "",
            tools=[
                {"name": f.nome, "description": f.descricao, "input_schema": f.schema()}
                for f in ferramentas
            ],
            messages=convertidas,
        )
        texto = "".join(b.text for b in resposta.content if b.type == "text")
        chamadas = [
            Chamada(id=b.id, nome=b.name, argumentos=dict(b.input))
            for b in resposta.content
            if b.type == "tool_use"
        ]
        return PassoLlm(texto, chamadas)


def criar_llm():
    """Escolhe o provedor conforme LLM_PROVIDER (padrão: ollama)."""
    provedor = os.getenv("LLM_PROVIDER", "ollama").lower()
    if provedor == "claude":
        return ClaudeLlm(os.getenv("CLAUDE_MODEL", "claude-haiku-5-5"))
    return OllamaLlm(
        os.getenv("OLLAMA_MODEL", "llama3.2:3b"),
        modelo_visao=os.getenv("OLLAMA_MODELO_VISAO", "qwen2.5vl:3b"),
    )
