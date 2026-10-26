"""Busca na web em várias fontes, sem chave de API e sem token de host.

O JARVIS precisa achar coisa sem pedir senha a cada pergunta. Este módulo só
**lê** páginas públicas: não grava arquivo, não executa nada, não fala com a
máquina onde roda. Por isso não pede token — a trava que continua valendo é
`JARVIS_HOST_REDE=1`, ligada por quem instalou.

Fontes, em ordem de quem responde mais:

- **duckduckgo** — HTML de `html.duckduckgo.com` (sem chave, sujeito a bloqueio);
- **wikipedia** — API oficial `pt.wikipedia.org/w/api.php` (JSON, estável);
- **youtube** — página de resultados, para achar vídeo e legenda depois.

`auto` consulta as três e intercala os resultados, para uma fonte bloqueada não
apagar a resposta das outras. Cada item carrega de qual fonte veio: o chat
mostra a etiqueta, e o usuário sabe se aquilo é vídeo, verbete ou site.
"""
from __future__ import annotations

import json
import re
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import quote_plus, urlparse
from urllib.request import Request, urlopen

FONTES = ("duckduckgo", "wikipedia", "youtube")
AGENTE = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) JarvisLocal/1.0"
TIMEOUT = 20
MAX_PAGINA = 4 * 1024 * 1024

DOMINIOS_BLOQUEADOS = (".local", ".internal", ".localhost", ".home.arpa")
REDES_PRIVADAS = ("127.", "10.", "192.168.", "169.254.", "0.")


class BuscaError(ValueError):
    """Nenhuma fonte respondeu — o chat traduz isso para linguagem de gente."""


Baixar = Callable[[str], str]


def _baixar(url: str) -> str:
    pedido = Request(
        url,
        headers={
            "User-Agent": AGENTE,
            "Accept": "text/html,application/json;q=0.9,*/*;q=0.8",
            "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.7",
        },
    )
    try:
        with urlopen(pedido, timeout=TIMEOUT) as resposta:
            dados = resposta.read(MAX_PAGINA + 1)
    except HTTPError as exc:
        raise BuscaError(f"HTTP {exc.code} em {urlparse(url).hostname}") from exc
    except (URLError, OSError) as exc:
        raise BuscaError(f"falha de rede em {urlparse(url).hostname}: {type(exc).__name__}") from exc
    if len(dados) > MAX_PAGINA:
        raise BuscaError("página grande demais")
    return dados.decode("utf-8", errors="replace")


def baixar_texto(url: str) -> str:
    """Baixa uma página ou arquivo de texto com as mesmas travas da busca.

    Público porque outras camadas (importar habilidade) precisam do mesmo
    cuidado: só http(s), sem endereço privado, com teto de tamanho.
    """
    return _baixar(_url_publica(url))


def _limpar(texto: str) -> str:
    sem_tag = re.sub(r"(?s)<[^>]+>", " ", texto or "")
    trocas = {
        "&nbsp;": " ", "&amp;": "&", "&lt;": "<", "&gt;": ">", "&quot;": '"',
        "&#39;": "'", "&apos;": "'", "&#x27;": "'", "&hellip;": "…",
    }
    for de, para in trocas.items():
        sem_tag = sem_tag.replace(de, para)
    return re.sub(r"\s+", " ", sem_tag).strip()


def _url_publica(url: str) -> str:
    """Só devolve link http(s) de host público; o resto vira string vazia."""
    bruto = (url or "").strip()
    if bruto.startswith("//"):
        bruto = "https:" + bruto
    partes = urlparse(bruto)
    if partes.scheme not in {"http", "https"}:
        return ""
    host = (partes.hostname or "").lower()
    if not host or host.endswith(DOMINIOS_BLOQUEADOS) or host.startswith(REDES_PRIVADAS):
        return ""
    return bruto[:500]


# ---------------------------------------------------------------- duckduckgo

_RE_DDG = re.compile(r'<a[^>]+class="result__a"[^>]+href="([^"]+)"[^>]*>(.*?)</a>', re.S)
_RE_UDDG = re.compile(r"uddg=([^&]+)")


def duckduckgo(consulta: str, limite: int, baixar: Baixar) -> list[dict[str, Any]]:
    html = baixar("https://html.duckduckgo.com/html/?q=" + quote_plus(consulta))
    itens: list[dict[str, Any]] = []
    for achado in _RE_DDG.finditer(html):
        if len(itens) >= limite:
            break
        destino = achado.group(1)
        if "uddg=" in destino:
            from urllib.parse import unquote

            trecho = _RE_UDDG.search(destino)
            if trecho:
                destino = unquote(trecho.group(1))
        url = _url_publica(destino)
        titulo = _limpar(achado.group(2))[:200]
        if url and titulo:
            itens.append({"titulo": titulo, "url": url, "fonte": "duckduckgo", "tipo": "site"})
    return itens


# ----------------------------------------------------------------- wikipedia

def wikipedia(consulta: str, limite: int, baixar: Baixar) -> list[dict[str, Any]]:
    url = (
        "https://pt.wikipedia.org/w/api.php?action=query&list=search&format=json&utf8=1"
        f"&srlimit={limite}&srsearch={quote_plus(consulta)}"
    )
    bruto = baixar(url)
    try:
        dados = json.loads(bruto)
    except json.JSONDecodeError as exc:
        raise BuscaError("a Wikipedia devolveu algo que não é JSON") from exc
    achados = ((dados.get("query") or {}).get("search") or [])
    itens: list[dict[str, Any]] = []
    for item in achados[:limite]:
        titulo = str(item.get("title") or "").strip()
        if not titulo:
            continue
        resumo = _limpar(str(item.get("snippet") or ""))[:300]
        itens.append(
            {
                "titulo": titulo,
                "url": "https://pt.wikipedia.org/wiki/" + quote_plus(titulo.replace(" ", "_")),
                "fonte": "wikipedia",
                "tipo": "verbete",
                "resumo": resumo,
            }
        )
    return itens


# ------------------------------------------------------------------- youtube

_RE_VIDEO_ID = re.compile(r'"videoId":"([A-Za-z0-9_-]{11})"')
_RE_TITULO_VIDEO = re.compile(
    r'"videoRenderer":\{"videoId":"([A-Za-z0-9_-]{11})".{0,400}?"title":\{"runs":\[\{"text":"(.*?)"\}',
    re.S,
)
_RE_CANAL = re.compile(
    r'"videoRenderer":\{"videoId":"([A-Za-z0-9_-]{11})".{0,1200}?"ownerText":\{"runs":\[\{"text":"(.*?)"',
    re.S,
)


def youtube(consulta: str, limite: int, baixar: Baixar) -> list[dict[str, Any]]:
    html = baixar("https://www.youtube.com/results?search_query=" + quote_plus(consulta) + "&hl=pt")
    titulos: dict[str, str] = {}
    for achado in _RE_TITULO_VIDEO.finditer(html):
        video_id, texto = achado.group(1), achado.group(2)
        if video_id not in titulos:
            titulos[video_id] = _decodificar_json(texto)[:200]
    canais: dict[str, str] = {}
    for achado in _RE_CANAL.finditer(html):
        canais.setdefault(achado.group(1), _decodificar_json(achado.group(2))[:120])
    itens: list[dict[str, Any]] = []
    for video_id in _RE_VIDEO_ID.findall(html):
        if len(itens) >= limite:
            break
        if video_id in {item["video_id"] for item in itens}:
            continue
        titulo = titulos.get(video_id)
        if not titulo:
            continue
        canal = canais.get(video_id, "")
        itens.append(
            {
                "titulo": titulo if not canal else f"{titulo} — {canal}",
                "url": f"https://www.youtube.com/watch?v={video_id}",
                "fonte": "youtube",
                "tipo": "vídeo",
                "video_id": video_id,
            }
        )
    return itens


def _decodificar_json(texto: str) -> str:
    """Desescapa `\\u00e9` e `\\"` do JSON embutido na página do YouTube."""
    try:
        return json.loads('"' + texto.replace('"', '\\"') + '"')
    except json.JSONDecodeError:
        return texto.replace('\\"', '"')


# ----------------------------------------------------------------- orquestra

BUSCADORES: dict[str, Callable[[str, int, Baixar], list[dict[str, Any]]]] = {
    "duckduckgo": duckduckgo,
    "wikipedia": wikipedia,
    "youtube": youtube,
}


def _intercalar(listas: list[list[dict[str, Any]]], limite: int) -> list[dict[str, Any]]:
    """Rodízio entre as fontes: uma bloqueada não engole as outras."""
    saida: list[dict[str, Any]] = []
    vistos: set[str] = set()
    indice = 0
    while len(saida) < limite and any(indice < len(lista) for lista in listas):
        for lista in listas:
            if len(saida) >= limite:
                break
            if indice < len(lista):
                item = lista[indice]
                chave = item.get("url") or item.get("titulo", "")
                if chave and chave not in vistos:
                    vistos.add(chave)
                    saida.append(item)
        indice += 1
    return saida


def buscar(
    consulta: str,
    *,
    limite: int = 8,
    fonte: str = "auto",
    baixar: Baixar | None = None,
) -> dict[str, Any]:
    """Procura em uma fonte ou em todas. Devolve o que respondeu e o que falhou."""
    termo = (consulta or "").strip()
    if len(termo) < 2:
        raise BuscaError("Escreva o que devo procurar (pelo menos 2 letras).")
    escolhida = (fonte or "auto").strip().lower()
    if escolhida not in ("auto", *FONTES):
        raise BuscaError(f"Fonte inválida: use auto, {', '.join(FONTES)}.")

    limite = max(1, min(int(limite), 25))
    funcao_baixar = baixar or _baixar
    alvos = list(FONTES) if escolhida == "auto" else [escolhida]

    # Em `auto` cada fonte contribui com uma fatia; sozinha, com tudo.
    fatia = limite if escolhida != "auto" else max(1, -(-limite // len(alvos)))
    listas: list[list[dict[str, Any]]] = []
    respondeu: list[str] = []
    falhas: list[str] = []
    for nome in alvos:
        try:
            itens = BUSCADORES[nome](termo, fatia, funcao_baixar)
        except BuscaError as exc:
            falhas.append(f"{nome}: {exc}")
            continue
        except Exception as exc:  # página mudou de formato, JSON estranho etc.
            falhas.append(f"{nome}: {type(exc).__name__}")
            continue
        if itens:
            respondeu.append(nome)
        listas.append(itens)

    resultados = _intercalar(listas, limite)
    if not resultados and falhas and len(falhas) == len(alvos):
        raise BuscaError("Nenhuma fonte respondeu: " + "; ".join(falhas))
    return {
        "consulta": termo,
        "fonte": escolhida,
        "resultados": resultados,
        "responderam": respondeu,
        "falhas": falhas,
    }
