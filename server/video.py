"""Legenda de vídeo do YouTube: baixar o texto que já existe, sem modelo.

O YouTube publica a transcrição em `captionTracks` dentro da própria página do
vídeo. Esta camada lê a página, escolhe a faixa no idioma pedido, baixa o
`json3` e devolve texto puro — que a biblioteca importa como fonte do tipo
"video".

O que **não** existe aqui: transcrição de áudio. Vídeo sem legenda (nem
automática) não tem o que baixar, e a camada diz isso em vez de fingir.

O acesso é frágil por natureza: o YouTube muda o HTML, pede consentimento de
cookie e às vezes entrega página sem as faixas. Por isso a busca é injetável
(`buscar=`), o erro é explícito e nada é tentado em laço infinito.
"""
from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from typing import Any, Callable
from urllib.parse import parse_qs, urlparse

AGENTE = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Jarvis/0.43"
TIMEOUT = 20
IDIOMAS = ("pt-BR", "pt-br", "pt", "en", "en-US", "es")

_RX_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")
_RX_PLAYER = re.compile(r"ytInitialPlayerResponse\s*=\s*(\{.*?\})\s*;\s*(?:var|</script>)", re.S)
_CHAVE_FAIXAS = '"captionTracks"'


class VideoError(ValueError):
    """Link inválido, vídeo sem legenda ou página que não veio."""


def id_do_video(url: str) -> str:
    """Aceita `watch?v=`, `youtu.be/`, `/shorts/`, `/embed/` e o ID puro."""
    bruto = (url or "").strip()
    if _RX_ID.match(bruto):
        return bruto
    try:
        partes = urlparse(bruto if "://" in bruto else f"https://{bruto}")
    except ValueError as exc:
        raise VideoError("Endereço de vídeo inválido.") from exc
    host = (partes.hostname or "").lower()
    if "youtu.be" in host:
        candidato = partes.path.lstrip("/").split("/")[0]
        if _RX_ID.match(candidato):
            return candidato
    consulta = parse_qs(partes.query)
    if consulta.get("v"):
        candidato = consulta["v"][0]
        if _RX_ID.match(candidato):
            return candidato
    achado = re.search(r"/(?:shorts|embed|live)/([A-Za-z0-9_-]{11})", partes.path)
    if achado:
        return achado.group(1)
    raise VideoError("Não achei o ID do vídeo no link. Use o endereço completo do YouTube.")


def _buscar_padrao(url: str, timeout: int = TIMEOUT) -> str:
    pedido = urllib.request.Request(
        url,
        headers={
            "User-Agent": AGENTE,
            "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
            "Cookie": "CONSENT=YES+cb; SOCS=CAI",
        },
    )
    try:
        with urllib.request.urlopen(pedido, timeout=timeout) as resposta:
            bruto = resposta.read(6 * 1024 * 1024)
    except urllib.error.HTTPError as exc:
        raise VideoError(f"O YouTube respondeu {exc.code}.") from exc
    except urllib.error.URLError as exc:
        raise VideoError("Sem acesso ao YouTube: verifique a internet.") from exc
    return bruto.decode("utf-8", errors="replace")


def _titulo(html: str) -> str:
    for padrao in (
        r'"title"\s*:\s*"([^"]{3,160})"\s*,\s*"lengthSeconds"',
        r"<title>([^<]{3,160})</title>",
    ):
        achado = re.search(padrao, html)
        if achado:
            return achado.group(1).replace("\\u0026", "&").strip()
    return "Vídeo do YouTube"


def _lista_apos(html: str, chave: str, limite: int = 400_000) -> str:
    """Arranca o array JSON que vem depois de `chave`, contando colchetes.

    Regex não dá conta: dentro de `baseUrl` há `[` e `]` escapados de outro
    jeito e o array é longo. Contar colchetes fora de string é confiável.
    """
    posicao = html.find(chave)
    if posicao < 0:
        return ""
    inicio = html.find("[", posicao + len(chave))
    if inicio < 0:
        return ""
    profundidade = 0
    em_string = False
    escape = False
    for indice in range(inicio, min(len(html), inicio + limite)):
        caractere = html[indice]
        if em_string:
            if escape:
                escape = False
            elif caractere == "\\":
                escape = True
            elif caractere == '"':
                em_string = False
            continue
        if caractere == '"':
            em_string = True
        elif caractere == "[":
            profundidade += 1
        elif caractere == "]":
            profundidade -= 1
            if profundidade == 0:
                return html[inicio : indice + 1]
    return ""


def _faixas(html: str) -> list[dict[str, Any]]:
    """`captionTracks` do player: objeto inteiro e, se falhar, o array cru."""
    candidatos: list[str] = []
    inteiro = _RX_PLAYER.search(html)
    if inteiro:
        try:
            dados = json.loads(inteiro.group(1))
        except json.JSONDecodeError:
            dados = {}
        faixas = (
            dados.get("captions", {})
            .get("playerCaptionsTracklistRenderer", {})
            .get("captionTracks")
        )
        if isinstance(faixas, list) and faixas:
            return [item for item in faixas if isinstance(item, dict)]
    candidatos.append(_lista_apos(html, _CHAVE_FAIXAS))
    for bruto in candidatos:
        if not bruto:
            continue
        try:
            faixas = json.loads(bruto)
        except json.JSONDecodeError:
            continue
        if isinstance(faixas, list) and faixas:
            return [item for item in faixas if isinstance(item, dict)]
    return []


def _escolher(faixas: list[dict[str, Any]]) -> dict[str, Any] | None:
    def idioma(faixa: dict[str, Any]) -> str:
        return str(faixa.get("languageCode") or "")

    for desejado in IDIOMAS:
        for faixa in faixas:
            if idioma(faixa).lower() == desejado.lower():
                return faixa
    return faixas[0] if faixas else None


def _texto_do_json3(bruto: str) -> str:
    try:
        dados = json.loads(bruto)
    except json.JSONDecodeError:
        return _texto_do_xml(bruto)
    linhas: list[str] = []
    for evento in dados.get("events") or []:
        pedacos = [seg.get("utf8", "") for seg in evento.get("segs") or []]
        linha = "".join(pedacos).strip()
        if linha:
            linhas.append(linha)
    return " ".join(linhas)


def _texto_do_xml(bruto: str) -> str:
    pedacos = re.findall(r"<text[^>]*>(.*?)</text>", bruto, re.S)
    limpos = [re.sub(r"<[^>]+>", "", pedaco) for pedaco in pedacos]
    texto = " ".join(item.strip() for item in limpos if item.strip())
    return (
        texto.replace("&amp;", "&")
        .replace("&#39;", "'")
        .replace("&quot;", '"')
        .replace("&lt;", "<")
        .replace("&gt;", ">")
    )


def legenda(
    url: str,
    *,
    buscar: Callable[[str], str] | None = None,
    idiomas: tuple[str, ...] = IDIOMAS,
) -> dict[str, Any]:
    """Baixa a legenda e devolve texto puro, título e idioma."""
    video_id = id_do_video(url)
    buscar_html = buscar or _buscar_padrao
    pagina = buscar_html(f"https://www.youtube.com/watch?v={video_id}&hl=pt")

    if "consent" in pagina[:4000].lower() and "captionTracks" not in pagina:
        raise VideoError("O YouTube pediu consentimento de cookie; abra o vídeo uma vez no navegador e tente de novo.")

    faixas = _faixas(pagina)
    if not faixas:
        raise VideoError(
            "Este vídeo não tem legenda publicada (nem automática). "
            "Sem legenda não há o que baixar — o JARVIS não transcreve áudio."
        )
    escolhida = _escolher(faixas)
    if escolhida is None:
        raise VideoError("Não consegui escolher a faixa de legenda do vídeo.")

    base = str(escolhida.get("baseUrl") or "")
    if not base:
        raise VideoError("A faixa de legenda veio sem endereço.")
    separador = "&" if "?" in base else "?"
    bruto = buscar_html(f"{base}{separador}fmt=json3")
    texto = _texto_do_json3(bruto).strip()
    if not texto:
        texto = _texto_do_xml(bruto).strip()
    if not texto:
        raise VideoError("A legenda veio vazia.")

    return {
        "video_id": video_id,
        "url": f"https://www.youtube.com/watch?v={video_id}",
        "titulo": _titulo(pagina),
        "idioma": str(escolhida.get("languageCode") or "?"),
        "automatica": bool(escolhida.get("kind")) and escolhida.get("kind") == "asr",
        "texto": re.sub(r"\s+", " ", texto),
        "caracteres": len(texto),
        "faixas": [str(item.get("languageCode") or "?") for item in faixas][:8],
    }
