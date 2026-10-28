"""RAG: responde perguntas usando só os trechos dos documentos do usuário.

Fluxo: pergunta -> embedding -> trechos mais próximos -> prompt com os trechos -> LLM.
"""

import re
import sqlite3
from dataclasses import dataclass, field

import numpy as np

from garantiafacil import embeddings
from garantiafacil.documentos import dividir_em_trechos

# Lição medida: com "responda exatamente 'Não encontrei...' se não estiver nos trechos", o modelo
# local (3B) recusava até perguntas cuja resposta estava no trecho. Um prompt mais brando, que só
# manda recusar quando "nenhum trecho trata do assunto", respondeu certo.
SISTEMA = (
    "Você ajuda a consultar termos de garantia. Responda à pergunta com base nos trechos "
    "fornecidos, em português, de forma curta e direta, citando o número do trecho, como [1]. "
    "Cite apenas números de trechos que existem. "
    "Só diga 'Não encontrei essa informação nos documentos.' se nenhum trecho tratar do assunto."
)

SEM_DOCUMENTOS = "Ainda não há documentos indexados. Adicione um manual ou termo de garantia."


@dataclass
class TrechoEncontrado:
    fonte: str
    pagina: int
    texto: str
    similaridade: float
    produto_id: int | None


@dataclass
class Resposta:
    texto: str
    trechos: list[TrechoEncontrado]
    citacoes_invalidas: list[int] = field(default_factory=list)  # números citados que não existem


def achar_citacoes_invalidas(texto: str, total_trechos: int) -> list[int]:
    """Números citados como [n] que não correspondem a nenhum trecho enviado ao modelo.
    Modelos inventam citações; por isso conferimos em vez de confiar."""
    citados = {int(n) for n in re.findall(r"\[(\d+)\]", texto)}
    return sorted(n for n in citados if not 1 <= n <= total_trechos)


def montar_prompt(pergunta: str, trechos: list[TrechoEncontrado]) -> str:
    """Numera os trechos para o modelo poder citá-los, e põe a pergunta no fim."""
    blocos = [
        f"[{i}] (fonte: {t.fonte}, página {t.pagina})\n{t.texto}" for i, t in enumerate(trechos, 1)
    ]
    return "Trechos dos documentos:\n\n" + "\n\n".join(blocos) + f"\n\nPergunta: {pergunta}"


class BaseConhecimento:
    def __init__(
        self,
        conexao: sqlite3.Connection,
        gerar_embedding=embeddings.gerar_embedding,
        nome_modelo=embeddings.nome_modelo,
    ):
        self.conexao = conexao
        self._gerar_embedding = gerar_embedding
        self._nome_modelo = nome_modelo

    def indexar(
        self, fonte: str, paginas: list[tuple[int, str]], produto_id: int | None = None
    ) -> int:
        """Divide o documento em trechos, gera o embedding de cada um e guarda.
        Reindexar a mesma fonte para o mesmo produto substitui a anterior.
        Devolve quantos trechos foram guardados."""
        trechos = dividir_em_trechos(paginas)
        # Gera todos os vetores antes de mexer no banco: se o Ollama falhar no meio,
        # a indexação anterior continua intacta.
        vetores = [self._gerar_embedding(t.texto) for t in trechos]

        self.remover_fonte(fonte, produto_id)
        modelo = self._nome_modelo()
        self.conexao.executemany(
            "INSERT INTO trechos (produto_id, fonte, pagina, texto, modelo, vetor) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            [
                (produto_id, fonte, t.pagina, t.texto, modelo, np.asarray(v, np.float32).tobytes())
                for t, v in zip(trechos, vetores)
            ],
        )
        self.conexao.commit()
        return len(trechos)

    def remover_fonte(self, fonte: str, produto_id: int | None = None) -> None:
        self.conexao.execute(
            "DELETE FROM trechos WHERE fonte = ? AND produto_id IS ?", (fonte, produto_id)
        )
        self.conexao.commit()

    def listar_fontes(self) -> list[tuple[str, int | None, int]]:
        """[(fonte, produto_id, quantidade de trechos)]"""
        linhas = self.conexao.execute(
            "SELECT fonte, produto_id, COUNT(*) AS n FROM trechos GROUP BY fonte, produto_id "
            "ORDER BY fonte"
        ).fetchall()
        return [(l["fonte"], l["produto_id"], l["n"]) for l in linhas]

    def tem_documentos(self, produto_id: int) -> bool:
        """O produto tem algum documento próprio (termo de garantia, manual) indexado?"""
        linha = self.conexao.execute(
            "SELECT 1 FROM trechos WHERE produto_id = ? AND modelo = ? LIMIT 1",
            (produto_id, self._nome_modelo()),
        ).fetchone()
        return linha is not None

    def fonte_indexada(self, fonte: str, produto_id: int | None = None) -> bool:
        """Esta fonte já está indexada (com o modelo de embeddings atual)?"""
        linha = self.conexao.execute(
            "SELECT 1 FROM trechos WHERE fonte = ? AND produto_id IS ? AND modelo = ? LIMIT 1",
            (fonte, produto_id, self._nome_modelo()),
        ).fetchone()
        return linha is not None

    def buscar(
        self,
        pergunta: str,
        produto_id: int | None = None,
        k: int = 4,
        so_gerais: bool = False,
    ) -> list[TrechoEncontrado]:
        """Os `k` trechos mais próximos da pergunta.

        - `so_gerais=True`: só documentos gerais (como o CDC);
        - `produto_id`: documentos daquele produto e os gerais;
        - nenhum dos dois: todos os documentos."""
        vetor_pergunta = self._gerar_embedding(pergunta, consulta=True)

        if so_gerais:
            filtro, parametros = "AND produto_id IS NULL", ()
        elif produto_id is not None:
            filtro, parametros = "AND (produto_id = ? OR produto_id IS NULL)", (produto_id,)
        else:
            filtro, parametros = "", ()

        linhas = self.conexao.execute(
            f"SELECT * FROM trechos WHERE modelo = ? {filtro}",
            (self._nome_modelo(), *parametros),
        ).fetchall()

        encontrados = [
            TrechoEncontrado(
                fonte=l["fonte"],
                pagina=l["pagina"],
                texto=l["texto"],
                similaridade=embeddings.similaridade(
                    vetor_pergunta, np.frombuffer(l["vetor"], dtype=np.float32)
                ),
                produto_id=l["produto_id"],
            )
            for l in linhas
        ]
        encontrados.sort(key=lambda t: t.similaridade, reverse=True)
        return encontrados[:k]

    def responder(
        self,
        pergunta: str,
        llm,
        produto_id: int | None = None,
        k: int = 4,
        so_gerais: bool = False,
    ) -> Resposta:
        trechos = self.buscar(pergunta, produto_id, k, so_gerais)
        if not trechos:
            return Resposta(SEM_DOCUMENTOS, [])

        # Temperatura 0: queremos fidelidade aos trechos, não criatividade.
        texto = llm.perguntar(montar_prompt(pergunta, trechos), sistema=SISTEMA, temperatura=0)
        texto = texto.strip()
        return Resposta(texto, trechos, achar_citacoes_invalidas(texto, len(trechos)))
