"""Biblioteca: aprender com livros, vídeos e pesquisas — sem modelo nenhum.

O JARVIS já lia uma página da web. O que faltava era memória de longo curso: o
livro que você comprou, a legenda do vídeo que explicou a coisa, a pesquisa que
você fez ontem. Esta camada transforma esses arquivos em **seções pesquisáveis**
e responde citando fonte, seção e página — sem resumir com modelo, sem inventar.

O caminho é sempre o mesmo:

1. **importar** — PDF, DOCX, EPUB, TXT/MD/RST, imagem e legenda (VTT/SRT) viram
   seções com título, texto e página; PDF escaneado e foto passam pelo OCR;
2. **buscar** — BM25 sobre as seções de todas as fontes, com cobertura calculada
   (quantas palavras do pedido realmente apareceram);
3. **correlacionar** — termos que aparecem em duas ou mais fontes, e pares que
   andam juntos dentro da mesma seção;
4. **fichar** — um `SKILL.md` determinístico por fonte: sumário, termos, números
   e citações com referência.

O que **não** existe aqui: geração de texto por modelo, tradução, resumo
abstrativo e "entender" o livro. A resposta é o trecho real, recortado, com a
referência ao lado. Se a biblioteca não cobre o assunto, a camada diz isso.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
import shutil
import zipfile
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from html import unescape
from pathlib import Path
from typing import Any, Iterable

from . import dados, ocr, video
from .texto import frases, normalizar, palavras, todas_as_palavras

MAX_ARQUIVO = 60 * 1024 * 1024
MAX_CARACTERES = 4_000_000
MAX_PARTES = 4_000
TAMANHO_SECAO = 1_400
TAMANHO_MINIMO = 180
LIMITE_TRECHO = 1_200
LIMITE_CONTEXTO = 2_600
MAX_EXPORTAR = 2_000_000

FORMATOS = {
    ".pdf": "livro",
    ".epub": "livro",
    ".docx": "documento",
    ".txt": "documento",
    ".md": "documento",
    ".markdown": "documento",
    ".rst": "documento",
    ".vtt": "video",
    ".srt": "video",
    ".png": "imagem",
    ".jpg": "imagem",
    ".jpeg": "imagem",
    ".webp": "imagem",
    ".bmp": "imagem",
    ".tif": "imagem",
    ".tiff": "imagem",
}


class BibliotecaError(ValueError):
    """Fonte que não dá para importar ou consultar."""


def _pasta() -> Path:
    return dados.raiz() / "biblioteca"


def _indice_arquivo() -> Path:
    return _pasta() / "indice.json"


def _agora() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _slug(titulo: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", normalizar(titulo)).strip("-")[:60] or "fonte"
    resumo = hashlib.sha1(titulo.encode("utf-8")).hexdigest()[:6]
    return f"{base}-{resumo}"


# ------------------------------------------------------------------ leitores

def _ler_pdf(caminho: Path) -> list[tuple[int | None, str]]:
    try:
        from pypdf import PdfReader
    except ImportError as exc:  # pragma: no cover - dependência declarada
        raise BibliotecaError("Falta o pacote `pypdf` para ler PDF.") from exc
    try:
        leitor = PdfReader(str(caminho))
    except Exception as exc:
        raise BibliotecaError(f"PDF ilegível ou protegido ({type(exc).__name__}).") from exc
    paginas: list[tuple[int | None, str]] = []
    for numero, pagina in enumerate(leitor.pages, start=1):
        try:
            texto = pagina.extract_text() or ""
        except Exception:
            texto = ""
        if texto.strip():
            paginas.append((numero, texto))
    return paginas


def _ler_docx(caminho: Path) -> list[tuple[int | None, str]]:
    try:
        from docx import Document
    except ImportError as exc:  # pragma: no cover - dependência declarada
        raise BibliotecaError("Falta o pacote `python-docx` para ler DOCX.") from exc
    try:
        documento = Document(str(caminho))
    except Exception as exc:
        raise BibliotecaError(f"DOCX ilegível ({type(exc).__name__}).") from exc
    texto = "\n".join(paragrafo.text for paragrafo in documento.paragraphs if paragrafo.text.strip())
    return [(None, texto)]


def _limpar_html(bloco: str) -> str:
    sem_script = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", bloco)
    sem_tag = re.sub(r"(?s)<[^>]+>", " ", sem_script)
    return re.sub(r"[ \t\u00a0]+", " ", unescape(sem_tag)).strip()


def _ler_epub(caminho: Path) -> list[tuple[int | None, str]]:
    try:
        pacote = zipfile.ZipFile(caminho)
    except zipfile.BadZipFile as exc:
        raise BibliotecaError("EPUB inválido.") from exc
    with pacote:
        try:
            container = pacote.read("META-INF/container.xml").decode("utf-8", "replace")
        except KeyError as exc:
            raise BibliotecaError("EPUB sem container.xml.") from exc
        achado = re.search(r'full-path="([^"]+)"', container)
        if not achado:
            raise BibliotecaError("EPUB sem caminho de pacote.")
        opf_path = achado.group(1)
        opf = pacote.read(opf_path).decode("utf-8", "replace")
        base = opf_path.rsplit("/", 1)[0] if "/" in opf_path else ""
        manifesto = {
            item_id: href
            for item_id, href in re.findall(r'<item[^>]*id="([^"]+)"[^>]*href="([^"]+)"', opf)
        }
        ordem = re.findall(r'<itemref[^>]*idref="([^"]+)"', opf)
        blocos: list[tuple[int | None, str]] = []
        for posicao, item_id in enumerate(ordem, start=1):
            href = manifesto.get(item_id)
            if not href:
                continue
            caminho_item = f"{base}/{href}" if base else href
            try:
                bruto = pacote.read(caminho_item).decode("utf-8", "replace")
            except KeyError:
                continue
            texto = _limpar_html(bruto)
            if texto:
                blocos.append((posicao, texto))
        return blocos


def _ler_legenda(caminho: Path) -> list[tuple[int | None, str]]:
    bruto = caminho.read_text(encoding="utf-8", errors="replace")
    linhas: list[str] = []
    for linha in bruto.splitlines():
        limpa = linha.strip()
        if not limpa:
            continue
        if limpa.upper().startswith("WEBVTT"):
            continue
        if re.fullmatch(r"\d+", limpa):
            continue
        if re.search(r"\d{2}:\d{2}(:\d{2})?[.,]\d{3}\s*-->", limpa):
            continue
        if limpa.startswith(("NOTE", "STYLE", "REGION")):
            continue
        linhas.append(re.sub(r"<[^>]+>", "", limpa))
    texto = " ".join(linhas)
    # Legenda automática repete o final de uma fala no começo da outra.
    return [(None, texto)]


def _ler_simples(caminho: Path) -> list[tuple[int | None, str]]:
    bruto = caminho.read_bytes()[: MAX_CARACTERES * 2]
    if b"\x00" in bruto[:4096]:
        raise BibliotecaError("Arquivo binário: não é texto.")
    return [(None, bruto.decode("utf-8", errors="replace"))]


def _ler_imagem(caminho: Path) -> list[tuple[int | None, str]]:
    """Foto de página, print ou digitalização: só OCR resolve."""
    try:
        texto = ocr.extrair_imagem(caminho.read_bytes())
    except ocr.OcrError as exc:
        raise BibliotecaError(str(exc)) from exc
    if not texto.strip():
        raise BibliotecaError("O OCR não achou texto nesta imagem.")
    return [(None, texto)]


def _ler(caminho: Path, sufixo: str) -> list[tuple[int | None, str]]:
    if sufixo == ".pdf":
        return _ler_pdf(caminho)
    if sufixo == ".docx":
        return _ler_docx(caminho)
    if sufixo == ".epub":
        return _ler_epub(caminho)
    if sufixo in {".vtt", ".srt"}:
        return _ler_legenda(caminho)
    if FORMATOS.get(sufixo) == "imagem":
        return _ler_imagem(caminho)
    return _ler_simples(caminho)


# ------------------------------------------------------------------- seções

_TITULO_MD = re.compile(r"^#{1,6}\s+(.+)$")
_TITULO_NUMERADO = re.compile(r"^(?:\d+(?:\.\d+)*\.?|[IVXLCDM]+\.)\s+([A-ZÁÉÍÓÚÂÊÔÃÕÇ][^.]{3,80})$")
_TITULO_MAIUSCULO = re.compile(r"^([A-ZÁÉÍÓÚÂÊÔÃÕÇ0-9][A-ZÁÉÍÓÚÂÊÔÃÕÇ0-9 ,:;'\-\u2014]{5,70})$")


def _cortar(texto: str, tamanho: int = TAMANHO_SECAO) -> list[str]:
    """Quebra por parágrafo, juntando até o tamanho — nunca no meio da palavra."""
    paragrafos = [re.sub(r"\s+", " ", bloco).strip() for bloco in re.split(r"\n{2,}", texto)]
    partes: list[str] = []
    atual = ""
    for paragrafo in paragrafos:
        if not paragrafo:
            continue
        if len(atual) + len(paragrafo) + 2 <= tamanho:
            atual = f"{atual}\n\n{paragrafo}".strip()
            continue
        if atual:
            partes.append(atual)
        if len(paragrafo) <= tamanho:
            atual = paragrafo
            continue
        inicio = 0
        while inicio < len(paragrafo):
            corte = paragrafo.rfind(" ", inicio, inicio + tamanho)
            if corte <= inicio:
                corte = inicio + tamanho
            partes.append(paragrafo[inicio:corte].strip())
            inicio = corte
        atual = ""
    if atual:
        partes.append(atual)
    return [parte for parte in partes if len(parte) >= TAMANHO_MINIMO] or [texto[:tamanho]]


def _secoes_dos_blocos(blocos: Iterable[tuple[int | None, str]]) -> list[dict[str, Any]]:
    """Corta por título e por página; seção com título do autor é respeitada.

    Um parágrafo solto abaixo do tamanho mínimo não vira seção própria: ele entra
    na seção vizinha da mesma página. Título explícito (markdown, "CAPÍTULO",
    "1.2 Título") vale como divisão mesmo em texto curto.
    """
    brutos: list[dict[str, Any]] = []
    titulo_atual = ""
    pagina_atual: int | None = None
    acumulado: list[str] = []

    def fechar() -> None:
        nonlocal acumulado
        corpo = "\n\n".join(pedaco for pedaco in acumulado if pedaco.strip()).strip()
        if corpo:
            brutos.append(
                {"titulo": titulo_atual, "texto": corpo, "pagina": pagina_atual, "explicito": bool(titulo_atual)}
            )
        acumulado = []

    for pagina, texto in blocos:
        if acumulado and pagina != pagina_atual:
            fechar()
        pagina_atual = pagina
        for linha in texto.splitlines():
            limpa = linha.strip()
            if not limpa:
                continue
            achado = _TITULO_MD.match(limpa) or _TITULO_NUMERADO.match(limpa) or _TITULO_MAIUSCULO.match(limpa)
            if achado and len(limpa) < 90:
                fechar()
                titulo_atual = (achado.group(1) if achado.groups() else limpa).strip()
                continue
            acumulado.append(limpa)
    if acumulado:
        fechar()

    secoes: list[dict[str, Any]] = []
    pendente: dict[str, Any] | None = None
    for bloco in brutos:
        if pendente is not None and pendente["pagina"] == bloco["pagina"] and not bloco["explicito"]:
            bloco = {
                **bloco,
                "texto": pendente["texto"] + "\n\n" + bloco["texto"],
                "titulo": bloco["titulo"] or pendente["titulo"],
            }
            pendente = None
        if len(bloco["texto"]) < TAMANHO_MINIMO and not bloco["explicito"]:
            # Bloco curto de outra página não pode engolir o pendente anterior.
            if pendente is not None and pendente["pagina"] != bloco["pagina"] and len(pendente["texto"]) >= 60:
                secoes.append(pendente)
            pendente = bloco
            continue
        if pendente is not None and secoes and secoes[-1]["pagina"] == pendente["pagina"]:
            secoes[-1]["texto"] += "\n\n" + pendente["texto"]
            pendente = None
        secoes.append(bloco)
    if pendente is not None:
        if secoes and secoes[-1]["pagina"] == pendente["pagina"]:
            secoes[-1]["texto"] += "\n\n" + pendente["texto"]
        elif len(pendente["texto"]) >= 60:
            secoes.append(pendente)

    if not secoes:
        bruto = "\n\n".join(texto for _, texto in blocos)
        for indice, pedaco in enumerate(_cortar(bruto), start=1):
            secoes.append({"texto": pedaco, "titulo": f"Parte {indice}", "pagina": None, "explicito": False})

    for indice, secao in enumerate(secoes[:MAX_PARTES], start=1):
        secao["ordem"] = indice
        secao["titulo"] = (secao.get("titulo") or f"Parte {indice}").strip()[:120]
        secao["texto"] = secao["texto"][:4000]
        secao.pop("explicito", None)
    return secoes[:MAX_PARTES]


def _tokens_de(texto: str) -> dict[str, int]:
    return dict(Counter(todas_as_palavras(texto)))


# -------------------------------------------------------------------- índice

def _ler_indice() -> list[dict[str, Any]]:
    try:
        dados_ = json.loads(_indice_arquivo().read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    return [item for item in dados_ if isinstance(item, dict)] if isinstance(dados_, list) else []


def _gravar_indice(fontes: Iterable[dict[str, Any]]) -> None:
    _pasta().mkdir(parents=True, exist_ok=True)
    alvo = _indice_arquivo()
    temporario = alvo.with_suffix(".tmp")
    temporario.write_text(json.dumps(list(fontes), ensure_ascii=False, indent=2), encoding="utf-8")
    temporario.replace(alvo)


def listar() -> list[dict[str, Any]]:
    """Fontes na biblioteca, da mais recente para a mais antiga."""
    return sorted(_ler_indice(), key=lambda item: item.get("criado_em", ""), reverse=True)


def obter(slug: str) -> dict[str, Any]:
    for item in _ler_indice():
        if item.get("slug") == slug:
            return item
    raise BibliotecaError("Fonte não encontrada na biblioteca.")


def _arquivo_da_fonte(slug: str) -> Path:
    return _pasta() / "fontes" / f"{slug}.json"


def _carregar_partes(slug: str) -> list[dict[str, Any]]:
    caminho = _arquivo_da_fonte(slug)
    try:
        dados_ = json.loads(caminho.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise BibliotecaError("Arquivo da fonte corrompido; importe de novo.") from exc
    return [item for item in dados_.get("partes", []) if isinstance(item, dict)]


def _gravar_fonte(slug: str, fonte: dict[str, Any], partes: list[dict[str, Any]]) -> None:
    pasta = _pasta() / "fontes"
    pasta.mkdir(parents=True, exist_ok=True)
    alvo = pasta / f"{slug}.json"
    temporario = alvo.with_suffix(".tmp")
    temporario.write_text(
        json.dumps({"fonte": fonte, "partes": partes}, ensure_ascii=False),
        encoding="utf-8",
    )
    temporario.replace(alvo)


# ------------------------------------------------------------------ importar

def _nome_de(caminho: Path) -> str:
    return re.sub(r"[_]+", " ", caminho.stem).strip() or caminho.name


def importar(
    caminho: str | Path,
    *,
    titulo: str = "",
    tipo: str = "auto",
    origem: str = "",
    usar_ocr: bool = True,
) -> dict[str, Any]:
    """Lê um arquivo e grava as seções. Não move nem apaga o original."""
    alvo = Path(caminho).expanduser()
    if not alvo.is_file():
        raise BibliotecaError("Arquivo não encontrado para importar.")
    tamanho = alvo.stat().st_size
    if tamanho > MAX_ARQUIVO:
        raise BibliotecaError(f"Arquivo acima de {MAX_ARQUIVO // (1024 * 1024)} MB.")
    sufixo = alvo.suffix.lower()
    if sufixo not in FORMATOS:
        raise BibliotecaError(
            "Formato não suportado. Aceito: " + ", ".join(sorted(FORMATOS)) + "."
        )
    blocos = _ler(alvo, sufixo)
    texto_total = sum(len(texto) for _, texto in blocos)

    # PDF escaneado devolve quase nada de texto: aí o OCR entra, se existir.
    if sufixo == ".pdf" and usar_ocr and ocr.precisa_ocr("".join(t for _, t in blocos), max(1, len(blocos))):
        try:
            blocos = ocr.extrair_pdf(alvo)
        except ocr.OcrError as exc:
            raise BibliotecaError(
                "Este PDF não tem texto (página escaneada). " + str(exc)
            ) from exc
        texto_total = sum(len(texto) for _, texto in blocos)

    if not blocos:
        raise BibliotecaError("Não saiu texto do arquivo (digitalizado sem OCR?).")
    categoria = tipo if tipo != "auto" else FORMATOS[sufixo]
    return _registrar(
        titulo=titulo or _nome_de(alvo),
        blocos=blocos,
        categoria=categoria,
        origem=origem or alvo.name,
        caracteres=texto_total,
    )


def importar_texto(titulo: str, texto: str, *, tipo: str = "pesquisa", origem: str = "") -> dict[str, Any]:
    """Fonte que já é texto: nota de pesquisa, transcrição colada, artigo salvo."""
    limpo = (texto or "").strip()
    if len(limpo) < TAMANHO_MINIMO:
        raise BibliotecaError("Texto curto demais para virar fonte (mínimo 180 caracteres).")
    blocos = [(None, limpo[:MAX_CARACTERES])]
    return _registrar(
        titulo=titulo,
        blocos=blocos,
        categoria=tipo or "pesquisa",
        origem=origem or "texto colado",
        caracteres=len(limpo),
    )


def _registrar(
    *,
    titulo: str,
    blocos: list[tuple[int | None, str]],
    categoria: str,
    origem: str,
    caracteres: int,
) -> dict[str, Any]:
    secoes = _secoes_dos_blocos(blocos)
    if not secoes:
        raise BibliotecaError("Nenhuma seção aproveitável no material.")
    for secao in secoes:
        secao["tokens"] = _tokens_de(secao["texto"])
    slug = _slug(titulo)
    fonte = {
        "slug": slug,
        "titulo": titulo.strip()[:160] or slug,
        "tipo": categoria,
        "origem": origem[:200],
        "criado_em": _agora(),
        "caracteres": caracteres,
        "secoes": len(secoes),
    }
    _gravar_fonte(slug, fonte, secoes)
    outras = [item for item in _ler_indice() if item.get("slug") != slug]
    _gravar_indice([fonte, *outras])
    return {**fonte, "total_palavras": sum(len(palavras(secao["texto"])) for secao in secoes)}


def importar_video(
    url: str,
    *,
    buscar: Any = None,
    titulo: str = "",
) -> dict[str, Any]:
    """Baixa a legenda do YouTube e importa como fonte do tipo "video".

    Só funciona com a rede liberada (`JARVIS_HOST_REDE=1`), igual às skills de
    sistema: nada aqui sai para a internet por acidente.
    """
    if os.environ.get("JARVIS_HOST_REDE", "0") != "1":
        raise BibliotecaError(
            "Rede desligada. Suba a API com JARVIS_HOST_REDE=1 para baixar a legenda do YouTube."
        )
    try:
        baixada = video.legenda(url, buscar=buscar)
    except video.VideoError as exc:
        raise BibliotecaError(str(exc)) from exc
    fonte = importar_texto(
        titulo or baixada["titulo"],
        baixada["texto"],
        tipo="video",
        origem=baixada["url"],
    )
    return {**fonte, "video_id": baixada["video_id"], "idioma": baixada["idioma"]}


def remover(slug: str) -> bool:
    fontes = _ler_indice()
    if not any(item.get("slug") == slug for item in fontes):
        return False
    _arquivo_da_fonte(slug).unlink(missing_ok=True)
    _gravar_indice([item for item in fontes if item.get("slug") != slug])
    return True


# ---------------------------------------------------------------------- busca

def _partes_com_fonte() -> list[tuple[dict[str, Any], dict[str, Any]]]:
    itens: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for fonte in _ler_indice():
        try:
            partes = _carregar_partes(str(fonte.get("slug")))
        except BibliotecaError:
            continue
        for parte in partes:
            itens.append((fonte, parte))
    return itens


def _bm25(consulta: list[str], documentos: list[dict[str, Any]], k1: float = 1.5, b: float = 0.75) -> list[float]:
    """BM25 clássico sobre os tokens já gravados em cada seção."""
    total = len(documentos) or 1
    tamanho_medio = sum(len(doc["tokens_lista"]) for doc in documentos) / total or 1.0
    frequencia_documento: Counter[str] = Counter()
    for documento in documentos:
        for termo in set(documento["tokens_lista"]):
            frequencia_documento[termo] += 1

    notas: list[float] = []
    for documento in documentos:
        tokens = documento["tokens"]
        tamanho = len(documento["tokens_lista"])
        nota = 0.0
        for termo in consulta:
            aparicoes = tokens.get(termo, 0)
            if not aparicoes:
                continue
            idf = math.log(1 + (total - frequencia_documento[termo] + 0.5) / (frequencia_documento[termo] + 0.5))
            nota += idf * (aparicoes * (k1 + 1)) / (
                aparicoes + k1 * (1 - b + b * tamanho / tamanho_medio)
            )
        notas.append(nota)
    return notas


def _vizinhas(partes: list[dict[str, Any]], alvo: dict[str, Any]) -> dict[str, Any]:
    """Título da seção anterior e da seguinte, para situar o trecho no livro."""
    for indice, parte in enumerate(partes):
        if parte.get("ordem") == alvo.get("ordem"):
            antes = partes[indice - 1].get("titulo") if indice > 0 else None
            depois = partes[indice + 1].get("titulo") if indice + 1 < len(partes) else None
            return {"antes": antes, "depois": depois}
    return {"antes": None, "depois": None}


def buscar(consulta: str, limite: int = 5) -> list[dict[str, Any]]:
    """Seções mais parecidas com o pedido, com cobertura e referência."""
    termos = palavras(consulta)
    if not termos:
        return []
    itens = _partes_com_fonte()
    if not itens:
        return []
    por_fonte: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for fonte_, parte_ in itens:
        por_fonte[str(fonte_.get("slug"))].append(parte_)
    documentos = [
        {"tokens": parte.get("tokens") or {}, "tokens_lista": list((parte.get("tokens") or {}).keys())}
        for _, parte in itens
    ]
    notas = _bm25(termos, documentos)

    achados: list[dict[str, Any]] = []
    for (fonte, parte), nota in zip(itens, notas):
        if nota <= 0:
            continue
        tokens = parte.get("tokens") or {}
        presentes = [termo for termo in termos if tokens.get(termo)]
        cobertura = len(presentes) / len(termos)
        if not presentes:
            continue
        achados.append(
            {
                "slug": fonte.get("slug"),
                "fonte": fonte.get("titulo"),
                "tipo": fonte.get("tipo"),
                "secao": parte.get("titulo"),
                "ordem": parte.get("ordem"),
                "pagina": parte.get("pagina"),
                "score": round(nota, 3),
                "cobertura": round(cobertura, 3),
                "termos": presentes[:8],
                "trecho": _recorte(parte.get("texto") or "", presentes),
                "contexto": _recorte(parte.get("texto") or "", presentes, limite=LIMITE_CONTEXTO),
                "vizinhas": _vizinhas(por_fonte.get(str(fonte.get("slug")), []), parte),
            }
        )
    achados.sort(key=lambda item: (item["cobertura"], item["score"]), reverse=True)
    return achados[:limite]


def _recorte(texto: str, termos: list[str], limite: int = LIMITE_TRECHO) -> str:
    """Devolve o pedaço em volta do primeiro termo encontrado, não o começo seco."""
    normalizado = normalizar(texto)
    posicao = -1
    for termo in termos:
        achado = normalizado.find(termo)
        if achado != -1 and (posicao == -1 or achado < posicao):
            posicao = achado
    if posicao == -1 or len(texto) <= limite:
        return texto[:limite].strip()
    inicio = max(0, posicao - limite // 3)
    fim = min(len(texto), inicio + limite)
    trecho = texto[inicio:fim].strip()
    if inicio > 0:
        trecho = "…" + trecho
    if fim < len(texto):
        trecho = trecho + "…"
    return trecho


def _referencia(achado: dict[str, Any]) -> str:
    pedacos = [str(achado.get("fonte") or "fonte")]
    if achado.get("secao"):
        pedacos.append(f"seção “{achado['secao']}”")
    if achado.get("pagina"):
        pedacos.append(f"página {achado['pagina']}")
    return " · ".join(pedacos)


def responder(consulta: str, limite: int = 3) -> dict[str, Any] | None:
    """Resposta pronta para o chat: trechos reais + referência, ou `None`."""
    achados = buscar(consulta, limite=limite)
    if not achados:
        return None
    melhor = achados[0]
    termos = palavras(consulta)
    minimo = 1 if len(termos) <= 2 else 2
    if melhor["cobertura"] < 0.5 or len(melhor["termos"]) < minimo:
        return None

    linhas = [
        f"Na biblioteca, “{melhor['fonte']}” ({_referencia(melhor).split(' · ', 1)[-1]}) fala disso:",
        "",
        melhor["trecho"],
    ]
    outras = [item for item in achados[1:] if item["slug"] != melhor["slug"]][:2]
    if outras:
        linhas.append("")
        linhas.append("Também aparece em:")
        for item in outras:
            linhas.append(f"- {_referencia(item)}")
    return {
        "resposta": "\n".join(linhas),
        "achados": achados,
        "cobertura": melhor["cobertura"],
        "fonte": melhor["fonte"],
        "slug": melhor["slug"],
    }


# --------------------------------------------------------------- correlações

def correlacoes(termo: str = "", limite: int = 12) -> list[dict[str, Any]]:
    """Termos que aparecem em 2+ fontes e, para um termo dado, seus vizinhos."""
    itens = _partes_com_fonte()
    if not itens:
        return []

    por_termo: dict[str, set[str]] = defaultdict(set)
    secoes_por_termo: Counter[str] = Counter()
    for fonte, parte in itens:
        for palavra_ in (parte.get("tokens") or {}):
            por_termo[palavra_].add(str(fonte.get("slug")))
            secoes_por_termo[palavra_] += 1

    if termo:
        alvo = [palavra_ for palavra_ in palavras(termo)]
        vizinhos: Counter[str] = Counter()
        for fonte, parte in itens:
            tokens = parte.get("tokens") or {}
            if not any(tokens.get(palavra_) for palavra_ in alvo):
                continue
            for palavra_, quantidade in tokens.items():
                if palavra_ not in alvo:
                    vizinhos[palavra_] += quantidade
        return [
            {
                "termo": palavra_,
                "forca": quantidade,
                "fontes": sorted(por_termo.get(palavra_, set())),
            }
            for palavra_, quantidade in vizinhos.most_common(limite)
        ]

    candidatos = [
        {
            "termo": palavra_,
            "fontes": sorted(fontes),
            "secoes": secoes_por_termo[palavra_],
        }
        for palavra_, fontes in por_termo.items()
        if len(fontes) >= 2
    ]
    candidatos.sort(key=lambda item: (len(item["fontes"]), item["secoes"]), reverse=True)
    return candidatos[:limite]


# -------------------------------------------------------------------- ficha

def digest(slug: str) -> dict[str, Any]:
    """`SKILL.md` determinístico da fonte: sumário, termos, números e citações."""
    fonte = obter(slug)
    partes = _carregar_partes(slug)
    if not partes:
        raise BibliotecaError("Fonte sem seções gravadas.")

    contagem: Counter[str] = Counter()
    for parte in partes:
        for palavra_, quantidade in (parte.get("tokens") or {}).items():
            contagem[palavra_] += quantidade
    termos = contagem.most_common(15)

    numeros: list[tuple[str, str]] = []
    for parte in partes:
        for frase in frases(parte.get("texto") or ""):
            if re.search(r"\d", frase) and len(frase) < 220:
                numeros.append((frase, str(parte.get("titulo"))))
            if len(numeros) >= 6:
                break
        if len(numeros) >= 6:
            break

    citacoes: list[tuple[str, str, int | None]] = []
    for parte in partes:
        for frase in frases(parte.get("texto") or ""):
            if 80 <= len(frase) <= 260:
                citacoes.append((frase, str(parte.get("titulo")), parte.get("pagina")))
            if len(citacoes) >= 5:
                break
        if len(citacoes) >= 5:
            break

    linhas = [
        "---",
        f"name: {fonte.get('slug')}",
        f"description: Ficha determinística de “{fonte.get('titulo')}” gerada pela biblioteca local.",
        "---",
        "",
        f"# {fonte.get('titulo')}",
        "",
        f"Fonte do tipo **{fonte.get('tipo')}**, {fonte.get('secoes')} seções, "
        f"{fonte.get('caracteres'):,} caracteres.".replace(",", "."),
        "",
        "## Sumário",
        "",
    ]
    for parte in partes[:40]:
        pagina = f" (p. {parte['pagina']})" if parte.get("pagina") else ""
        linhas.append(f"{parte.get('ordem')}. {parte.get('titulo')}{pagina}")

    linhas += ["", "## Termos mais frequentes", ""]
    linhas.append(", ".join(f"{termo} ({quantos})" for termo, quantos in termos))

    if numeros:
        linhas += ["", "## Números e regras citados", ""]
        for frase, secao in numeros:
            linhas.append(f"- {frase} — *{secao}*")

    if citacoes:
        linhas += ["", "## Passagens para conferir", ""]
        for frase, secao, pagina in citacoes:
            onde = f"{secao}, p. {pagina}" if pagina else secao
            linhas.append(f"> {frase}\n> — {onde}")

    linhas += [
        "",
        "---",
        "",
        "Ficha montada por regra (seção, termo, número), sem modelo de linguagem.",
        "Cada linha acima existe no texto original e pode ser conferida na fonte.",
    ]
    return {
        "slug": slug,
        "titulo": fonte.get("titulo"),
        "markdown": "\n".join(linhas),
        "termos": [{"termo": termo, "ocorrencias": quantos} for termo, quantos in termos],
        "secoes": len(partes),
    }


def _primeira_linha(texto: str, limite: int = 140) -> str:
    for frase in frases(texto):
        limpa = " ".join(frase.split())
        if len(limpa) >= 20:
            return limpa[:limite] + ("…" if len(limpa) > limite else "")
    return " ".join(texto.split())[:limite]


def sumario(slug: str, limite: int = 80) -> dict[str, Any]:
    """Índice da fonte: cada seção com página, tamanho, começo e termos."""
    fonte = obter(slug)
    partes = _carregar_partes(slug)
    if not partes:
        raise BibliotecaError("Fonte sem seções gravadas.")
    capitulos: list[dict[str, Any]] = []
    for parte in partes[:limite]:
        texto = (parte.get("texto") or "").strip()
        capitulos.append(
            {
                "ordem": parte.get("ordem"),
                "titulo": parte.get("titulo"),
                "pagina": parte.get("pagina"),
                "caracteres": len(texto),
                "comeca_com": _primeira_linha(texto),
                "termos": [termo for termo, _ in Counter(todas_as_palavras(texto)).most_common(5)],
            }
        )
    paginas = [parte.get("pagina") for parte in partes if isinstance(parte.get("pagina"), int)]
    return {
        "slug": slug,
        "titulo": fonte.get("titulo"),
        "tipo": fonte.get("tipo"),
        "secoes": len(partes),
        "mostradas": len(capitulos),
        "pagina_inicial": min(paginas) if paginas else None,
        "pagina_final": max(paginas) if paginas else None,
        "capitulos": capitulos,
    }


def exportar(slug: str, *, incluir_texto: bool = True) -> dict[str, Any]:
    """Grava a fonte como `.md` (ficha + texto) em `storage/biblioteca/exportadas`."""
    ficha = digest(slug)
    fonte = obter(slug)
    partes = _carregar_partes(slug)
    linhas = [ficha["markdown"]]
    truncado = False
    if incluir_texto:
        linhas += ["", "---", "", f"# Texto completo — {fonte.get('titulo')}", ""]
        total = 0
        for parte in partes:
            marca = f"## {parte.get('ordem')}. {parte.get('titulo')}"
            if parte.get("pagina"):
                marca += f" (p. {parte['pagina']})"
            bloco = [marca, "", (parte.get("texto") or "").strip(), ""]
            total += len("\n".join(bloco))
            if total > MAX_EXPORTAR:
                truncado = True
                linhas += ["", "> Texto cortado no limite de 2 MB; a ficha acima está completa."]
                break
            linhas += bloco
    pasta = _pasta() / "exportadas"
    pasta.mkdir(parents=True, exist_ok=True)
    alvo = pasta / f"{slug}.md"
    conteudo = "\n".join(linhas).strip() + "\n"
    alvo.write_text(conteudo, encoding="utf-8")
    return {
        "slug": slug,
        "titulo": fonte.get("titulo"),
        "arquivo": str(alvo),
        "bytes": len(conteudo.encode("utf-8")),
        "inclui_texto": incluir_texto,
        "truncado": truncado,
    }


def gravar_digest(slug: str) -> Path:
    """Grava a ficha em `storage/biblioteca/fichas/<slug>/SKILL.md`."""
    resultado = digest(slug)
    pasta = _pasta() / "fichas" / slug
    pasta.mkdir(parents=True, exist_ok=True)
    alvo = pasta / "SKILL.md"
    alvo.write_text(resultado["markdown"], encoding="utf-8")
    return alvo
