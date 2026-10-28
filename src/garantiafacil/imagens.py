"""Imagens padrão dos produtos, usadas quando o usuário não envia uma foto.

São ícones SVG (desenho em texto, sem arquivo de imagem), um por categoria. Produto sem
categoria usa a caixa."""

from garantiafacil.modelos import Categoria

_TRACO = 'fill="none" stroke="#2f45f5" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"'


def _svg(desenho: str) -> str:
    return f'<svg viewBox="0 0 64 64" width="40" height="40" xmlns="http://www.w3.org/2000/svg" {_TRACO}>{desenho}</svg>'


_GELADEIRA = _svg(
    '<rect x="18" y="8" width="28" height="48" rx="5"/>'
    '<line x1="18" y1="28" x2="46" y2="28"/>'
    '<line x1="24" y1="16" x2="24" y2="22"/>'
    '<line x1="24" y1="34" x2="24" y2="44"/>'
)
_TELEVISAO = _svg(
    '<rect x="8" y="14" width="48" height="30" rx="4"/>'
    '<line x1="22" y1="52" x2="42" y2="52"/>'
    '<line x1="32" y1="44" x2="32" y2="52"/>'
)
_MARTELO = _svg(
    '<g transform="rotate(45 32 32)">'
    '<rect x="29" y="22" width="6" height="34" rx="2"/>'
    '<rect x="17" y="10" width="30" height="12" rx="3"/></g>'
)
_CAIXA = _svg(
    '<path d="M32 8 L54 19 V45 L32 56 L10 45 V19 Z"/>'
    '<path d="M10 19 L32 30 L54 19"/><line x1="32" y1="30" x2="32" y2="56"/>'
)

_CAMISETA = _svg(
    '<path d="M22 10 L10 18 L16 27 L22 24 V54 H42 V24 L48 27 L54 18 L42 10 '
    'C40 15 24 15 22 10 Z"/>'
)
_SOFA = _svg(
    '<rect x="14" y="14" width="36" height="18" rx="5"/>'
    '<rect x="8" y="30" width="48" height="16" rx="5"/>'
    '<line x1="16" y1="46" x2="16" y2="53"/><line x1="48" y1="46" x2="48" y2="53"/>'
)
_URSO = _svg(
    '<circle cx="32" cy="35" r="16"/><circle cx="19" cy="21" r="6"/><circle cx="45" cy="21" r="6"/>'
    '<circle cx="26" cy="32" r="1.5"/><circle cx="38" cy="32" r="1.5"/><circle cx="32" cy="40" r="3"/>'
)
_CARRO = _svg(
    '<path d="M8 42 V34 C8 32 9 31 11 30 L18 20 H42 L50 30 H54 C56 30 57 32 57 34 V42 Z"/>'
    '<line x1="31" y1="20" x2="31" y2="30"/>'
    '<circle cx="20" cy="44" r="6"/><circle cx="45" cy="44" r="6"/>'
)
_ETIQUETA = _svg(
    '<path d="M10 34 L34 10 H52 V28 L28 52 Z"/><circle cx="43" cy="19" r="3"/>'
)

IMAGEM_PADRAO = {
    Categoria.ELETRODOMESTICOS: _GELADEIRA,
    Categoria.ELETRONICOS: _TELEVISAO,
    Categoria.FERRAMENTAS: _MARTELO,
    Categoria.VESTUARIO: _CAMISETA,
    Categoria.MOVEIS: _SOFA,
    Categoria.BRINQUEDOS: _URSO,
    Categoria.AUTOMOTIVO: _CARRO,
    Categoria.OUTROS: _ETIQUETA,
}


def imagem_padrao(categoria: Categoria | None) -> str:
    """SVG (texto) da imagem padrão da categoria; a caixa se não houver categoria."""
    return IMAGEM_PADRAO.get(categoria, _CAIXA)
