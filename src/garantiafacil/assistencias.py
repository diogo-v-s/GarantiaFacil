"""Onde acionar a garantia: assistências e lojas perto de uma cidade, com dados do OpenStreetMap.

Duas consultas públicas e gratuitas, sem chave:
  - Nominatim: transforma o nome de uma cidade em coordenadas;
  - Overpass: lista lugares do mapa (lojas, oficinas) num raio ao redor de um ponto.

Os dados são feitos por voluntários e no Brasil são incompletos: muita assistência autorizada não está
no mapa, e telefone e endereço faltam com frequência. Por isso este módulo só repassa o que o mapa
tem ("não informado" quando falta) e nunca completa nada. O Overpass público também é lento (chegou
a levar 1 minuto), então o resultado fica guardado em arquivo por alguns dias.

Quando houver conta paga no Google Places, só a função `buscar_assistencias` precisa mudar."""

import hashlib
import json
import math
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from garantiafacil.modelos import Categoria

URL_NOMINATIM = "https://nominatim.openstreetmap.org/search"
URL_OVERPASS = "https://overpass-api.de/api/interpreter"
USER_AGENT = "garantiafacil-estudo/0.1"  # os dois serviços exigem identificar o app
PASTA_CACHE = Path(__file__).resolve().parents[2] / "data" / "cache_assistencias"
VALIDADE_CACHE_SEGUNDOS = 7 * 24 * 3600
RAIO_PADRAO_METROS = 6000
MAXIMO_DE_RESULTADOS = 10
NAO_INFORMADO = "não informado"

# O que procurar no mapa para cada categoria: pares (chave, valores aceitos) do OpenStreetMap.
ETIQUETAS_POR_CATEGORIA: dict[Categoria, list[tuple[str, str]]] = {
    Categoria.ELETRONICOS: [("craft", "electronics_repair"), ("shop", "electronics|mobile_phone|computer")],
    Categoria.ELETRODOMESTICOS: [("craft", "electronics_repair"), ("shop", "appliance|electronics")],
    Categoria.FERRAMENTAS: [("shop", "doityourself|hardware|tool_hire"), ("craft", "electronics_repair")],
    Categoria.AUTOMOTIVO: [("shop", "car_repair|car|tyres"), ("amenity", "car_repair")],
    Categoria.MOVEIS: [("shop", "furniture")],
}


class ErroDeBusca(Exception):
    """A consulta falhou (sem internet, servidor ocupado). A mensagem é para mostrar ao usuário."""


@dataclass
class Local:
    nome: str
    latitude: float
    longitude: float


@dataclass
class Assistencia:
    nome: str
    endereco: str
    telefone: str
    site: str | None
    distancia_km: float
    marca_confere: bool  # o nome ou a marca do lugar tem a marca procurada


def _sem_acento(texto: str) -> str:
    decomposto = unicodedata.normalize("NFD", texto.lower())
    return "".join(c for c in decomposto if unicodedata.category(c) != "Mn")


def distancia_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Distância em linha reta entre dois pontos (fórmula de haversine)."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 6371 * 2 * math.asin(math.sqrt(a))


def _pedir(url: str, dados: dict | None, timeout: float) -> dict:
    corpo = urllib.parse.urlencode(dados).encode() if dados else None
    requisicao = urllib.request.Request(url, data=corpo, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(requisicao, timeout=timeout) as resposta:
            return json.load(resposta)
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as erro:
        raise ErroDeBusca("O serviço de mapas não respondeu agora. Tente de novo em instantes.") from erro


def _do_cache(chave: str):
    arquivo = PASTA_CACHE / (hashlib.sha1(chave.encode()).hexdigest() + ".json")
    if arquivo.exists() and time.time() - arquivo.stat().st_mtime < VALIDADE_CACHE_SEGUNDOS:
        return arquivo, json.loads(arquivo.read_text(encoding="utf-8"))
    return arquivo, None


def _guardar(arquivo: Path, conteudo) -> None:
    arquivo.parent.mkdir(parents=True, exist_ok=True)
    arquivo.write_text(json.dumps(conteudo, ensure_ascii=False), encoding="utf-8")


def localizar_cidade(texto: str, timeout: float = 15.0) -> Local | None:
    """Coordenadas de uma cidade ou endereço no Brasil; None se o Nominatim não achar."""
    texto = texto.strip()
    if not texto:
        return None
    arquivo, guardado = _do_cache("cidade:" + _sem_acento(texto))
    if guardado is None:
        guardado = _pedir(
            URL_NOMINATIM + "?" + urllib.parse.urlencode(
                {"q": texto, "format": "json", "limit": 1, "countrycodes": "br"}
            ),
            None,
            timeout,
        )
        _guardar(arquivo, guardado)
    if not guardado:
        return None
    primeiro = guardado[0]
    return Local(primeiro["display_name"], float(primeiro["lat"]), float(primeiro["lon"]))


def _consulta_overpass(categoria: Categoria, local: Local, raio_m: int) -> str | None:
    etiquetas = ETIQUETAS_POR_CATEGORIA.get(categoria)
    if not etiquetas:
        return None
    filtros = "".join(
        f'  nwr["{chave}"~"^({valores})$"](around:{raio_m},{local.latitude},{local.longitude});\n'
        for chave, valores in etiquetas
    )
    return f"[out:json][timeout:60];\n(\n{filtros});\nout center tags 300;"


def _endereco(tags: dict) -> str:
    rua = tags.get("addr:street", "")
    numero = tags.get("addr:housenumber", "")
    bairro = tags.get("addr:suburb", "")
    partes = [f"{rua}, {numero}" if rua and numero else rua, bairro]
    return " - ".join(p for p in partes if p) or NAO_INFORMADO


def _interpretar(elementos: list[dict], local: Local, marca: str | None) -> list[Assistencia]:
    procurada = _sem_acento(marca.strip()) if marca else ""
    achados = []
    for elemento in elementos:
        tags = elemento.get("tags", {})
        if not tags.get("name"):
            continue  # lugar sem nome não ajuda o usuário
        centro = elemento.get("center", elemento)  # ways e relations trazem o ponto em "center"
        if "lat" not in centro:
            continue
        achados.append(Assistencia(
            nome=tags["name"],
            endereco=_endereco(tags),
            telefone=tags.get("phone") or tags.get("contact:phone") or NAO_INFORMADO,
            site=tags.get("website") or tags.get("contact:website"),
            distancia_km=round(distancia_km(local.latitude, local.longitude, centro["lat"], centro["lon"]), 1),
            marca_confere=bool(procurada) and procurada in _sem_acento(tags["name"] + " " + tags.get("brand", "")),
        ))  # fmt: skip
    # Quem tem a marca vem primeiro; depois, os mais perto
    achados.sort(key=lambda a: (not a.marca_confere, a.distancia_km))
    return achados[:MAXIMO_DE_RESULTADOS]


def buscar_assistencias(
    local: Local,
    categoria: Categoria | None,
    marca: str | None = None,
    raio_m: int = RAIO_PADRAO_METROS,
    timeout: float = 90.0,
) -> list[Assistencia]:
    """Lugares perto de `local` que podem atender produtos da categoria, os da `marca` primeiro."""
    consulta = _consulta_overpass(categoria, local, raio_m) if categoria else None
    if consulta is None:
        raise ErroDeBusca("Sem categoria definida no produto, não sei que tipo de lugar procurar.")
    arquivo, guardado = _do_cache("overpass:" + consulta)
    if guardado is None:
        guardado = _pedir(URL_OVERPASS, {"data": consulta}, timeout)["elements"]
        _guardar(arquivo, guardado)
    return _interpretar(guardado, local, marca)
