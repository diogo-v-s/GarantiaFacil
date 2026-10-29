"""Extração de dados de uma foto de nota fiscal usando um LLM com visão."""

import re
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field

from garantiafacil.chave_acesso import buscar_chave
from garantiafacil.llm import criar_llm
from garantiafacil.modelos import Categoria

# Uma escolha entre opções fechadas (como o classificador do chat): o modelo é obrigado a decidir.
CategoriaLida = Literal[tuple(c.value for c in Categoria)]  # type: ignore[valid-type]

# Atenção: campos opcionais (`str | None`) e a instrução "use null se não souber" faziam o modelo
# local devolver null em quase tudo. Campos obrigatórios e instruções positivas funcionaram bem.
# O usuário sempre confere os dados no formulário, então um campo errado é corrigível.
SISTEMA = (
    "Você lê fotos de notas fiscais e cupons brasileiros e extrai os dados com precisão, "
    "copiando o texto como está escrito no documento."
)

PROMPT = "Extraia os dados desta nota fiscal."


class DadosNota(BaseModel):
    """Formato que o LLM é obrigado a seguir. As descrições orientam o modelo."""

    loja: str = Field(description="Nome da empresa que emitiu o documento (razão social do emitente)")
    produto: str = Field(
        description="Nome curto do item vendido: marca, tipo e modelo, sem cor, quantidade, "
        "código ou texto de rodapé (se houver vários itens, o de maior valor). "
        "Ex.: 'Smartphone Motorola Moto E13'"
    )
    detalhes: str = Field(
        description="Só características do próprio item que ficaram fora do nome (cor, "
        "capacidade, tamanho, código do produto), copiadas como estão. NÃO inclua preço, "
        "quantidade, pagamento, impostos nem dados da nota. Texto vazio se não sobrou nada"
    )
    categoria: CategoriaLida = Field(
        description="Categoria do item vendido. Use Outros se não for claramente de uma das "
        "outras (ex.: lentes de óculos, material de escritório)"
    )
    data_compra: str = Field(description="Data de emissão, como aparece no documento")
    valor: float = Field(description="Valor total da nota em reais, com ponto como decimal")

    def categoria_padrao(self) -> Categoria:
        return Categoria(self.categoria)

    def data(self) -> date | None:
        """Converte o texto da data para `date`; None se o modelo devolveu algo inválido.

        Aceita DD/MM/AAAA (o formato das notas brasileiras) e AAAA-MM-DD, com ou sem hora
        depois ("30/09/2026 17:15:41"): procura a data dentro do texto."""
        texto = self.data_compra.strip()
        for padrao, formato in ((r"\d{2}/\d{2}/\d{4}", "%d/%m/%Y"), (r"\d{4}-\d{2}-\d{2}", "%Y-%m-%d")):
            achado = re.search(padrao, texto)
            if not achado:
                continue
            try:
                return datetime.strptime(achado.group(), formato).date()
            except ValueError:
                continue
        return None


class ChaveLida(BaseModel):
    chave: str = Field(
        description="Os 44 dígitos do campo CHAVE DE ACESSO, na ordem em que aparecem, sem espaços"
    )


def ler_chave_impressa(imagem: bytes, tipo_midia: str = "image/jpeg", llm=None) -> str | None:
    """Pede à IA para ler a chave de acesso impressa. Pode errar dígitos: quem chama deve
    validar com `chave_acesso.interpretar`, que confere o dígito verificador."""
    llm = llm or criar_llm()
    lida = llm.extrair(
        "Leia a chave de acesso (44 dígitos) desta nota fiscal.",
        imagem,
        ChaveLida,
        sistema=SISTEMA,
        tipo_midia=tipo_midia,
    )
    return buscar_chave(lida.chave)


def extrair_dados_nota(imagem: bytes, tipo_midia: str = "image/jpeg", llm=None) -> DadosNota:
    """Recebe os bytes da imagem e devolve os dados lidos. `llm` pode ser injetado nos testes."""
    llm = llm or criar_llm()
    return llm.extrair(PROMPT, imagem, DadosNota, sistema=SISTEMA, tipo_midia=tipo_midia)
