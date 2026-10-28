"""Converte o HTML do CDC (Lei 8.078/1990, versão compilada do Planalto) em texto limpo.

Como obter o HTML (a conexão exige HTTP/1.1):
    curl --http1.1 -L -A "Mozilla/5.0" -o cdc.htm \
        https://www.planalto.gov.br/ccivil_03/leis/l8078compilado.htm

Uso:
    uv run python scripts/preparar_cdc.py cdc.htm docs/conhecimento/cdc.txt

A lei é texto oficial (domínio público, Lei 9.610/1998, art. 8º). O resultado é um artigo por
parágrafo, sem as notas de alteração legislativa, que só atrapalhariam a busca.
"""

import re
import sys
from html.parser import HTMLParser
from pathlib import Path

CABECALHO = (
    "CÓDIGO DE DEFESA DO CONSUMIDOR (Lei nº 8.078, de 11 de setembro de 1990)\n"
    "Fonte: https://www.planalto.gov.br/ccivil_03/leis/l8078compilado.htm (texto compilado)\n"
)

# Notas do tipo "(Redação dada pela Lei nº ...)", "(Incluído pela ...)", "(Vide ...)"
NOTAS = re.compile(
    r"\((?:Redação dada|Incluíd[oa]|Vide|Vetado|Revogad[oa]|Regulamento|Vigência|Renumerad[oa]"
    r"|Produção de efeito)[^)]*\)",
    re.IGNORECASE,
)

BLOCOS = {"p", "div", "br", "tr", "li", "h1", "h2", "h3", "h4", "table"}


class Extrator(HTMLParser):
    def __init__(self):
        super().__init__()
        self.partes: list[str] = []
        self._ignorar = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "strike", "s", "del"):  # strike = texto revogado
            self._ignorar += 1
        elif tag in BLOCOS:
            self.partes.append("\n")

    def handle_endtag(self, tag):
        if tag in ("script", "style", "strike", "s", "del"):
            self._ignorar -= 1
        elif tag in BLOCOS:
            self.partes.append("\n")

    def handle_data(self, dados):
        if not self._ignorar:
            self.partes.append(dados)


def converter(html: str) -> str:
    extrator = Extrator()
    extrator.feed(html)
    texto = "".join(extrator.partes).replace("\xa0", " ")
    texto = NOTAS.sub("", texto)

    linhas = [re.sub(r"[ \t]+", " ", linha).strip() for linha in texto.splitlines()]
    linhas = [linha for linha in linhas if linha]

    # Um parágrafo (separado por linha em branco) por artigo e por título/capítulo/seção.
    saida: list[str] = []
    for linha in linhas:
        if re.match(r"^(Art\.|TÍTULO|CAPÍTULO|Seção|Subseção)\b", linha):
            saida.append("")
        saida.append(linha)

    # Descarta o que vem antes do preâmbulo/primeiro título.
    texto_final = "\n".join(saida).strip()
    inicio = texto_final.find("TÍTULO I")
    return texto_final[inicio:] if inicio > 0 else texto_final


def main():
    origem, destino = Path(sys.argv[1]), Path(sys.argv[2])
    texto = converter(origem.read_bytes().decode("cp1252", errors="replace"))
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(CABECALHO + "\n" + texto + "\n", encoding="utf-8")
    artigos = len(re.findall(r"^Art\.", texto, re.MULTILINE))
    print(f"{destino}: {len(texto)} caracteres, {artigos} artigos")


if __name__ == "__main__":
    main()
