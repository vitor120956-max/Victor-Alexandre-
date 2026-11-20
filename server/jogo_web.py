"""Testar o jogo no iPhone: o caminho que não precisa de Mac, conta Apple nem US$ 99.

O pedido (18/11), logo depois da análise do APK:

    ta bom e dps q esse apk estiver bom eu quero testar no meu iphone

**APK não roda em iPhone.** Não é limitação do JARVIS: o iOS só executa app
assinado pela Apple. Nenhum programa instala um `.apk` num iPhone — o formato,
a loja e a assinatura são outros.

O caminho de graça é este: o **mesmo jogo** exportado em HTML5/WebGL roda no
Safari do iPhone, sem Mac, sem conta de desenvolvedor e sem publicar nada. Este
módulo serve essa pasta na rede local:

- guarda o export em `files_root/jogos-web/<nome>/` (pasta ou `.zip`);
- sobe um servidor HTTP mínimo em `0.0.0.0:<porta>` só de arquivos estáticos;
- manda `Content-Encoding` para os `.gz`/`.br` que o export da Unity gera
  (sem isso a Unity WebGL baixa 404 e a tela fica preta);
- aceita `Range`, para áudio e vídeo do jogo funcionarem;
- manda COOP/COEP, que o export com *threads* do Godot exige;
- prepara o **ícone na tela de início** do iPhone (0.91.40): injeta
  `apple-touch-icon`, `apple-mobile-web-app-capable` e um `manifest` na página
  servida, sem tocar no arquivo do export no disco.

## Ícone na tela de início ≠ app assinado

“Baixar no iPhone” tem dois sentidos, e só um deles é de graça:

- **ícone na tela de início** (o que este módulo faz): o Safari abre em tela
  cheia, sem a barra do navegador, com ícone próprio. Custa zero e não precisa
  de conta Apple;
- **app assinado** (`.ipa`, TestFlight, App Store): exige conta **Apple
  Developer** (US$ 99/ano) e um Mac (ou build na nuvem) para assinar. Nenhum
  programa no Windows transforma um APK em `.ipa`.

## As regras

1. **A API do JARVIS não abre.** O servidor do jogo é outro processo, em outra
   porta, e só devolve arquivos da pasta exportada — ele não conhece chave,
   `.env`, biblioteca nem nenhuma rota do projeto.
2. **Nada sai da pasta.** `..`, caminho absoluto, arquivo oculto e symlink são
   recusados — o teste cobre cada um.
3. **Nada é convertido.** Isto não transforma APK em app de iPhone; isto serve
   o export HTML5 que o motor gera. Quem converte o projeto é o motor.
"""
from __future__ import annotations

import html
import json
import os
import secrets
import shutil
import socket
import struct
import zipfile
import zlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import unquote, urlsplit

PORTA_PADRAO = 8099
MAXIMO_BYTES = 500_000_000
MAX_ARQUIVOS = 20_000

# O iPhone e o PC precisam falar a mesma língua de arquivo: estes tipos são os
# que um export de jogo pede, e o resto vira binário.
TIPOS: dict[str, str] = {
    ".html": "text/html; charset=utf-8",
    ".htm": "text/html; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".mjs": "text/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".wasm": "application/wasm",
    ".data": "application/octet-stream",
    ".pck": "application/octet-stream",
    ".unityweb": "application/octet-stream",
    ".mem": "application/octet-stream",
    ".symbols": "application/octet-stream",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".gif": "image/gif",
    ".svg": "image/svg+xml",
    ".ico": "image/x-icon",
    ".mp3": "audio/mpeg",
    ".ogg": "audio/ogg",
    ".wav": "audio/wav",
    ".mp4": "video/mp4",
    ".webm": "video/webm",
    ".woff": "font/woff",
    ".woff2": "font/woff2",
    ".ttf": "font/ttf",
    ".otf": "font/otf",
}


class JogoWebError(ValueError):
    """Erro esperado, em português, seguro para mostrar na tela."""


# ---------------------------------------------------------------------------
# Onde ficam os exports HTML5
# ---------------------------------------------------------------------------

def raiz(files_root: Path) -> Path:
    """A pasta dos exports web, dentro da área isolada do JARVIS."""
    destino = files_root.resolve() / "jogos-web"
    destino.mkdir(parents=True, exist_ok=True)
    return destino


def _limpar_nome(nome: str) -> str:
    """Um nome que serve de pasta e de endereço no Safari, sem espaço nem acento."""
    limpo = []
    for letra in nome.strip():
        if letra.isalnum() and letra.isascii():
            limpo.append(letra)
        elif letra in {"-", "_", "."}:
            limpo.append(letra)
        else:
            limpo.append("-")
    texto = "".join(limpo).strip("-._")
    while "--" in texto:
        texto = texto.replace("--", "-")
    return texto[:60] or "jogo"


def _nome_unico(base: Path, nome: str) -> str:
    candidato = nome
    contador = 1
    while (base / candidato).exists():
        candidato = f"{nome}-{contador}"
        contador += 1
    return candidato


def _achatar(pasta: Path) -> None:
    """Export que veio dentro de uma pasta só (o caso do `.zip`) sobe um nível.

    Sem isso, o endereço no iPhone vira `/MeuJogo-WebGL/` e o jogo abre em
    branco quando alguém digita só o IP.
    """
    if (pasta / "index.html").is_file():
        return
    filhos = [item for item in pasta.iterdir() if item.is_dir() and not item.name.startswith(".")]
    if len(filhos) != 1:
        return
    unico = filhos[0]
    if not (unico / "index.html").is_file():
        return
    for item in list(unico.iterdir()):
        shutil.move(str(item), str(pasta / item.name))
    unico.rmdir()


def _entrada_segura(nome_entrada: str) -> PurePosixPath:
    valor = nome_entrada.replace("\\", "/")
    pure = PurePosixPath(valor)
    if pure.is_absolute() or "\x00" in valor:
        raise JogoWebError("O .zip tem um caminho absoluto — recusei extrair.")
    if any(parte in {"..", ""} or parte.startswith(".") for parte in pure.parts):
        raise JogoWebError("O .zip tem “..” ou arquivo oculto — recusei extrair.")
    return pure


def _extrair_zip(origem: Path, destino: Path) -> None:
    """Extrai com teto de tamanho e sem deixar entrada escapar da pasta."""
    total = 0
    try:
        with zipfile.ZipFile(origem) as pacote:
            itens = pacote.infolist()
            if len(itens) > MAX_ARQUIVOS:
                raise JogoWebError(
                    f"O .zip tem {len(itens)} arquivos; o limite é {MAX_ARQUIVOS}."
                )
            for item in itens:
                pure = _entrada_segura(item.filename)
                if item.is_dir():
                    (destino / pure).mkdir(parents=True, exist_ok=True)
                    continue
                total += item.file_size
                if total > MAXIMO_BYTES:
                    raise JogoWebError(
                        f"O export passa de {MAXIMO_BYTES // 1_000_000} MB descompactado."
                    )
                alvo = destino / pure
                alvo.parent.mkdir(parents=True, exist_ok=True)
                with pacote.open(item) as entrada, alvo.open("wb") as saida:
                    shutil.copyfileobj(entrada, saida, 1_000_000)
    except zipfile.BadZipFile as exc:
        raise JogoWebError("O arquivo não é um .zip válido.") from exc


def _copiar_pasta(origem: Path, destino: Path) -> None:
    total = 0
    arquivos = 0
    for caminho in sorted(origem.rglob("*")):
        relativo = caminho.relative_to(origem)
        if any(parte.startswith(".") for parte in relativo.parts):
            continue
        if caminho.is_symlink():
            continue
        if caminho.is_dir():
            (destino / relativo).mkdir(parents=True, exist_ok=True)
            continue
        arquivos += 1
        if arquivos > MAX_ARQUIVOS:
            raise JogoWebError(f"A pasta tem mais de {MAX_ARQUIVOS} arquivos.")
        total += caminho.stat().st_size
        if total > MAXIMO_BYTES:
            raise JogoWebError(f"O export passa de {MAXIMO_BYTES // 1_000_000} MB.")
        (destino / relativo).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(caminho, destino / relativo)


def importar(origem: Path, files_root: Path, nome: str | None = None) -> dict[str, Any]:
    """Guarda o export (pasta ou `.zip`) na pasta de jogos web do JARVIS."""
    origem = Path(origem).expanduser()
    if not origem.exists():
        raise JogoWebError(f"Não achei “{origem}”.")
    if origem.is_symlink():
        raise JogoWebError("Esse caminho é um atalho; arraste a pasta de verdade.")
    if origem.is_file() and origem.suffix.lower() != ".zip":
        raise JogoWebError(
            "Arraste a pasta do export HTML5 (ou o .zip dela). Um arquivo solto não é um jogo."
        )

    base = raiz(files_root)
    bruto = nome or (origem.stem if origem.is_file() else origem.name)
    final = _nome_unico(base, _limpar_nome(bruto))
    temporario = base / f".importando-{os.getpid()}-{secrets.token_hex(4)}"
    temporario.mkdir(parents=True, exist_ok=False)
    try:
        if origem.is_file():
            _extrair_zip(origem, temporario)
        else:
            _copiar_pasta(origem, temporario)
        _achatar(temporario)
        if not (temporario / "index.html").is_file():
            raise JogoWebError(
                "Não achei `index.html` no export. No motor, o destino é “WebGL” (Unity) "
                "ou “Web/HTML5” (Godot) — é essa pasta que tem o index.html."
            )
        destino = base / final
        temporario.rename(destino)
    except Exception:
        shutil.rmtree(temporario, ignore_errors=True)
        raise

    dados = _medir(destino)
    return {"nome": final, "pasta": str(destino), **dados}


def _medir(pasta: Path) -> dict[str, Any]:
    arquivos = 0
    total = 0
    for caminho in pasta.rglob("*"):
        if caminho.is_file() and not caminho.is_symlink():
            arquivos += 1
            total += caminho.stat().st_size
    return {"arquivos": arquivos, "bytes": total}


def pastas(files_root: Path) -> list[Path]:
    base = raiz(files_root)
    itens = []
    for caminho in sorted(base.iterdir()):
        if not caminho.is_dir() or caminho.is_symlink() or caminho.name.startswith("."):
            continue
        itens.append(caminho)
    return itens


def listar(files_root: Path, porta: int = PORTA_PADRAO) -> dict[str, Any]:
    """Os exports já guardados, com o endereço que se abre no iPhone.

    0.92.1 — o endereço vai junto: antes a tela do jogo não sabia o IP da
    máquina, e a instrução ficava só no `.bat`. É o mesmo cálculo do
    `instrucoes()`, então o número na tela e o do console não divergem.
    """
    base = raiz(files_root)
    jogos = []
    for caminho in pastas(files_root):
        dados = _medir(caminho)
        jogos.append(
            {
                "nome": caminho.name,
                "pasta": str(caminho),
                "temIndex": (caminho / "index.html").is_file(),
                **dados,
            }
        )
    endereco = endereco_local()
    return {
        "pasta": str(base),
        "quantidade": len(jogos),
        "jogos": jogos,
        "porta": porta,
        "endereco": f"http://{endereco}:{porta}/",
    }


# ---------------------------------------------------------------------------
# Servidor: só arquivos desta pasta, nada do resto do JARVIS
# ---------------------------------------------------------------------------

def _resolver(base: Path, relativo: str) -> Path:
    """Um caminho dentro do export — ou erro. `..`, oculto e symlink não passam."""
    partes: list[str] = []
    for parte in relativo.replace("\\", "/").split("/"):
        if parte in {"", "."}:
            continue
        if "\x00" in parte or parte == ".." or parte.startswith("."):
            raise JogoWebError("Caminho inválido.")
        partes.append(parte)
    atual = base
    for parte in partes:
        atual = atual / parte
        if atual.is_symlink():
            raise JogoWebError("Caminho inválido.")
    alvo = base.joinpath(*partes)
    resolvido = alvo.resolve()
    if resolvido != base and base not in resolvido.parents:
        raise JogoWebError("Caminho inválido.")
    return alvo


# ---------------------------------------------------------------------------
# O ícone da tela de início (0.91.40)
#
# “Baixar no iPhone” como ícone: o iOS não lê SVG nem usa o favicon da página
# para isso — ele quer um PNG de 180x180 em `apple-touch-icon`. O export não
# traz um, então o ícone é desenhado aqui, sem Pillow e sem arquivo extra.
# ---------------------------------------------------------------------------

_CORES = ((12, 18, 34), (58, 76, 150))  # fundo: azul-noite
_COR_MARCA = (96, 232, 214)  # triângulo de “play”: verde-água

_CACHE_ICONE: dict[int, bytes] = {}


def _bloco_png(tipo: bytes, dados: bytes) -> bytes:
    return struct.pack(">I", len(dados)) + tipo + dados + struct.pack(">I", zlib.crc32(tipo + dados) & 0xFFFFFFFF)


def _distancia_ao_segmento(px: float, py: float, x1: float, y1: float, x2: float, y2: float) -> float:
    """Distância do ponto ao **segmento** (não à reta que o contém).

    A primeira versão usava a distância à reta: fora do triângulo, o
    prolongamento de cada aresta virava uma linha atravessando o ícone
    inteiro — apareceu no primeiro PNG gerado.
    """
    dx, dy = x2 - x1, y2 - y1
    if dx == 0 and dy == 0:
        return ((px - x1) ** 2 + (py - y1) ** 2) ** 0.5
    t = ((px - x1) * dx + (py - y1) * dy) / (dx * dx + dy * dy)
    t = max(0.0, min(1.0, t))
    ex, ey = x1 + t * dx, y1 + t * dy
    return ((px - ex) ** 2 + (py - ey) ** 2) ** 0.5


def _distancia_ao_triangulo(px: float, py: float, ax: float, ay: float, bx: float, by: float, cx: float, cy: float) -> float:
    """Distância com sinal: negativa dentro. Serve para a borda não serrilhar."""
    def lado(x1: float, y1: float, x2: float, y2: float) -> float:
        return (px - x2) * (y1 - y2) - (x1 - x2) * (py - y2)

    d1, d2, d3 = lado(ax, ay, bx, by), lado(bx, by, cx, cy), lado(cx, cy, ax, ay)
    if (d1 >= 0 and d2 >= 0 and d3 >= 0) or (d1 <= 0 and d2 <= 0 and d3 <= 0):
        return -1.0
    return min(
        _distancia_ao_segmento(px, py, ax, ay, bx, by),
        _distancia_ao_segmento(px, py, bx, by, cx, cy),
        _distancia_ao_segmento(px, py, cx, cy, ax, ay),
    )


def icone_png(tamanho: int = 180) -> bytes:
    """O ícone do jogo: fundo em gradiente e o triângulo de “play”."""
    if tamanho in _CACHE_ICONE:
        return _CACHE_ICONE[tamanho]
    ax, ay, bx, by, cx, cy = 0.34, 0.22, 0.34, 0.78, 0.78, 0.50
    borda = 1.5 / tamanho  # meia-largura do suavizado, em fração
    (r0, g0, b0), (r1, g1, b1) = _CORES
    linhas: list[bytes] = []
    for y in range(tamanho):
        linha = bytearray()
        vy = (y + 0.5) / tamanho
        for x in range(tamanho):
            vx = (x + 0.5) / tamanho
            t = (vx * 0.35 + vy * 0.65)
            fundo = (
                int(r0 + (r1 - r0) * t),
                int(g0 + (g1 - g0) * t),
                int(b0 + (b1 - b0) * t),
            )
            d = _distancia_ao_triangulo(vx, vy, ax, ay, bx, by, cx, cy)
            cobertura = 0.0
            if d <= -borda:
                cobertura = 1.0
            elif d < borda:
                cobertura = (borda - d) / (2 * borda)
            if cobertura > 0:
                cor = tuple(
                    int(round(fundo[i] + (_COR_MARCA[i] - fundo[i]) * cobertura)) for i in range(3)
                )
            else:
                cor = fundo
            linha += bytes(cor)
        linhas.append(bytes(linha))
    dados = b"".join(b"\x00" + linha for linha in linhas)
    png = b"\x89PNG\r\n\x1a\n"
    png += _bloco_png(b"IHDR", struct.pack(">IIBBBBB", tamanho, tamanho, 8, 2, 0, 0, 0))
    png += _bloco_png(b"IDAT", zlib.compress(dados, 9))
    png += _bloco_png(b"IEND", b"")
    _CACHE_ICONE[tamanho] = png
    return png


def manifest(nome: str) -> dict[str, Any]:
    """O `manifest.webmanifest` do jogo — usado por Android e por Safari novo."""
    return {
        "name": nome,
        "short_name": nome[:12],
        "start_url": "/",
        "scope": "/",
        "display": "standalone",
        "orientation": "any",
        "background_color": "#0c1222",
        "theme_color": "#12172a",
        "icons": [
            {"src": "/jarvis-icone-180.png", "sizes": "180x180", "type": "image/png", "purpose": "any"},
            {"src": "/jarvis-icone-512.png", "sizes": "512x512", "type": "image/png", "purpose": "any"},
        ],
    }


_MARCA_PWA = "data-jarvis-pwa"


def _injetar_pwa(original: bytes, nome: str) -> bytes:
    """Mete as tags do ícone no `index.html` servido — o arquivo do disco não muda.

    Safari usa `apple-touch-icon`; o `manifest` serve para o resto. A marca
    `data-jarvis-pwa` impede que uma página que já veio preparada ganhe tudo
    duas vezes.
    """
    texto = original.decode("utf-8", errors="replace")
    if _MARCA_PWA in texto:
        return original
    titulo = html.escape(nome, quote=True)
    tags = (
        f'<link rel="apple-touch-icon" sizes="180x180" href="/jarvis-icone-180.png" {_MARCA_PWA}>'
        f'<link rel="icon" type="image/png" href="/jarvis-icone-180.png" {_MARCA_PWA}>'
        f'<link rel="manifest" href="/manifest.webmanifest" {_MARCA_PWA}>'
        f'<meta name="apple-mobile-web-app-capable" content="yes" {_MARCA_PWA}>'
        f'<meta name="mobile-web-app-capable" content="yes" {_MARCA_PWA}>'
        f'<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent" {_MARCA_PWA}>'
        f'<meta name="apple-mobile-web-app-title" content="{titulo}" {_MARCA_PWA}>'
        f'<meta name="application-name" content="{titulo}" {_MARCA_PWA}>'
        f'<meta name="theme-color" content="#12172a" {_MARCA_PWA}>'
    )
    minusculo = texto.lower()
    if "</head>" in minusculo:
        corte = minusculo.index("</head>")
        texto = texto[:corte] + tags + texto[corte:]
    elif "<body" in minusculo:
        corte = minusculo.index("<body")
        texto = texto[:corte] + tags + texto[corte:]
    else:
        texto = tags + texto
    return texto.encode("utf-8")


def _tipo(nome: str) -> str:
    return TIPOS.get(Path(nome).suffix.lower(), "application/octet-stream")


def _alvo(base: Path, caminho: str, aceita: str) -> tuple[Path | None, str | None, str | None, bool]:
    """(arquivo, codificação, nome lógico, precisa barra no fim)."""
    try:
        candidato = _resolver(base, unquote(caminho).lstrip("/"))
    except (JogoWebError, OSError, ValueError):
        return None, None, None, False
    if candidato.is_dir():
        # A barra no fim muda o que o navegador resolve como caminho relativo:
        # sem ela, `/Build` faria a página pedir `/jogo.js` em vez de
        # `/Build/jogo.js`. O 301 vale para toda pasta — inclusive a que não
        # tem index, que depois responde 404 explicando onde olhar.
        if not caminho.endswith("/"):
            return None, None, None, True
        indice = candidato / "index.html"
        if indice.is_file() and not indice.is_symlink():
            return indice, None, "index.html", False
        return None, None, None, False
    if candidato.is_file() and not candidato.is_symlink():
        # A Unity pede `jogo.data.gz` pelo nome. Entregar o arquivo sem dizer
        # que ele está comprimido faz o carregador receber lixo binário — o
        # Safari mostra “Unable to parse” e a tela fica preta.
        if candidato.suffix == ".gz":
            return candidato, "gzip", candidato.stem, False
        if candidato.suffix == ".br":
            return candidato, "br", candidato.stem, False
        return candidato, None, candidato.name, False
    # Export da Unity costuma vir só com `.gz`/`.br`: o servidor de teste do
    # próprio motor manda o arquivo comprimido no lugar do original.
    for sufixo, codificacao in ((".br", "br"), (".gz", "gzip")):
        alternativo = Path(str(candidato) + sufixo)
        if alternativo.is_file() and not alternativo.is_symlink() and codificacao in aceita:
            return alternativo, codificacao, candidato.name, False
    return None, None, None, False


def _intervalo(cabecalho: str, tamanho: int) -> tuple[int, int] | None:
    """Lê `Range: bytes=a-b`. Faixa inválida devolve o arquivo inteiro."""
    if not cabecalho.startswith("bytes=") or tamanho <= 0:
        return None
    faixa = cabecalho[len("bytes=") :].split(",")[0].strip()
    try:
        if faixa.startswith("-"):
            quantidade = int(faixa[1:] or 0)
            if quantidade <= 0:
                return None
            inicio, fim = max(0, tamanho - quantidade), tamanho - 1
        else:
            inicio_txt, _, fim_txt = faixa.partition("-")
            inicio = int(inicio_txt or 0)
            fim = int(fim_txt) if fim_txt else tamanho - 1
    except ValueError:
        return None
    if inicio < 0 or inicio > fim or inicio >= tamanho:
        return None
    return inicio, min(fim, tamanho - 1)


_PAGINA_404 = (
    "<!doctype html><meta charset='utf-8'><title>JARVIS — jogo</title>"
    "<body style='font-family:system-ui,sans-serif;padding:2rem;line-height:1.5'>"
    "<h1>Arquivo não encontrado</h1>"
    "<p><code>{caminho}</code> não existe neste export.</p>"
    "<p>Se o jogo abriu em branco, olhe a janela do <b>testar-no-iphone.bat</b> no PC: "
    "ela mostra cada arquivo que o iPhone pediu.</p>"
    "</body>"
)


class _Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "JARVIS-jogo"

    def log_message(self, formato: str, *args: Any) -> None:
        """Silêncio: o console do dono mostra só o que interessa."""

    def log_request(self, code: Any = "-", size: Any = "-") -> None:
        """Cada pedido do iPhone aparece no console — é o diagnóstico barato.

        Nenhum pedido aqui embaixo quer dizer que o iPhone não chegou no PC:
        rede diferente, firewall ou Wi-Fi de visitante.
        """
        if getattr(self.server, "registrar", False):
            print(f"  pedido: {self.command} {self.path} -> {code}", flush=True)

    @property
    def _base(self) -> Path:
        return self.server.base  # type: ignore[attr-defined]

    @property
    def _isolamento(self) -> bool:
        return bool(getattr(self.server, "isolamento", True))

    @property
    def _pwa(self) -> bool:
        return bool(getattr(self.server, "pwa", False))

    def _virtual(self, caminho: str) -> tuple[bytes, str] | None:
        """O ícone e o manifesto: gerados aqui, não existem no disco do export."""
        if not self._pwa:
            return None
        nome = getattr(self.server, "nome", "jogo")
        if caminho == "/jarvis-icone-180.png":
            return icone_png(180), "image/png"
        if caminho == "/jarvis-icone-512.png":
            return icone_png(512), "image/png"
        if caminho in {"/manifest.webmanifest", "/manifest.json"}:
            corpo = json.dumps(manifest(nome), ensure_ascii=False).encode("utf-8")
            return corpo, "application/manifest+json; charset=utf-8"
        return None

    def do_GET(self) -> None:  # noqa: N802 - nome exigido pelo BaseHTTPRequestHandler
        self._servir(com_corpo=True)

    def do_HEAD(self) -> None:  # noqa: N802
        self._servir(com_corpo=False)

    def _servir(self, *, com_corpo: bool) -> None:
        caminho = urlsplit(self.path).path or "/"
        aceita = self.headers.get("Accept-Encoding", "") or ""
        virtual = self._virtual(caminho)
        if virtual is not None:
            corpo, tipo = virtual
            self.send_response(200)
            self.send_header("Content-Type", tipo)
            self.send_header("Content-Length", str(len(corpo)))
            self.send_header("Cache-Control", "no-store")
            if self._isolamento:
                self.send_header("Cross-Origin-Opener-Policy", "same-origin")
                self.send_header("Cross-Origin-Embedder-Policy", "require-corp")
            self.send_header("Connection", "close")
            self.end_headers()
            if com_corpo:
                self.wfile.write(corpo)
            return

        arquivo, codificacao, nome_logico, precisa_barra = _alvo(self._base, caminho, aceita)

        if precisa_barra:
            self.send_response(301)
            self.send_header("Location", caminho + "/")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return

        if arquivo is None or nome_logico is None:
            corpo = _PAGINA_404.format(caminho=html.escape(caminho)).encode("utf-8")
            self.send_response(404)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(corpo)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("Connection", "close")
            self.end_headers()
            if com_corpo:
                self.wfile.write(corpo)
            return

        try:
            tamanho = arquivo.stat().st_size
        except OSError:
            self.send_error(500, "Não consegui ler o arquivo")
            return

        # 0.91.40 — o índice sai com as tags do ícone, mas o arquivo no disco
        # continua intacto; por isso a página é montada em memória e a faixa
        # (`Range`) não vale para ela.
        conteudo: bytes | None = None
        if self._pwa and nome_logico == "index.html" and not codificacao:
            try:
                original = arquivo.read_bytes()
            except OSError:
                original = b""
            if original:
                novo = _injetar_pwa(original, getattr(self.server, "nome", "jogo"))
                if novo != original:
                    conteudo = novo
                    tamanho = len(conteudo)

        # Faixa em arquivo comprimido é faixa do comprimido, não do conteúdo:
        # o navegador montaria um arquivo corrompido. Nesse caso, inteiro.
        faixa = (
            None
            if codificacao or conteudo is not None
            else _intervalo(self.headers.get("Range", "") or "", tamanho)
        )
        inicio, fim = faixa if faixa else (0, tamanho - 1)
        enviar = 0 if tamanho == 0 else fim - inicio + 1

        self.send_response(206 if faixa else 200)
        self.send_header("Content-Type", _tipo(nome_logico))
        self.send_header("Content-Length", str(enviar))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Accept-Ranges", "bytes")
        if codificacao:
            self.send_header("Content-Encoding", codificacao)
        if faixa:
            self.send_header("Content-Range", f"bytes {inicio}-{fim}/{tamanho}")
        if self._isolamento:
            # O export com threads (Godot 4) só liga com estas duas cabeças.
            self.send_header("Cross-Origin-Opener-Policy", "same-origin")
            self.send_header("Cross-Origin-Embedder-Policy", "require-corp")
        self.send_header("Connection", "close")
        self.end_headers()

        if not com_corpo or enviar == 0:
            return
        if conteudo is not None:
            try:
                self.wfile.write(conteudo)
            except (BrokenPipeError, ConnectionResetError):
                return
            return
        try:
            with arquivo.open("rb") as fh:
                fh.seek(inicio)
                restante = enviar
                while restante > 0:
                    pedaco = fh.read(min(65536, restante))
                    if not pedaco:
                        break
                    self.wfile.write(pedaco)
                    restante -= len(pedaco)
        except (BrokenPipeError, ConnectionResetError):
            # O Safari fechou a conexão (trocou de página, jogo já carregou).
            return


class ServidorJogo(ThreadingHTTPServer):
    """HTTP mínimo, `daemon` para o Ctrl+C não ficar preso em conexão aberta."""

    daemon_threads = True
    allow_reuse_address = True

    def __init__(
        self,
        endereco: tuple[str, int],
        base: Path,
        isolamento: bool = True,
        registrar: bool = False,
        pwa: bool = True,
    ) -> None:
        self.base = Path(base).resolve()
        self.nome = self.base.name
        self.isolamento = isolamento
        self.registrar = registrar
        self.pwa = pwa
        super().__init__(endereco, _Handler)


def subir(
    base: Path,
    porta: int = PORTA_PADRAO,
    host: str = "0.0.0.0",
    isolamento: bool = True,
    registrar: bool = False,
    pwa: bool = True,
) -> ServidorJogo:
    """Sobe o servidor do export. `porta=0` deixa o sistema escolher (testes)."""
    pasta = Path(base)
    if not (pasta / "index.html").is_file():
        raise JogoWebError("Essa pasta não tem index.html — não é um export HTML5.")
    return ServidorJogo(
        (host, porta), pasta, isolamento=isolamento, registrar=registrar, pwa=pwa
    )


def _prioridade(ip: str) -> int:
    """Quanto mais provável ser a rede do Wi-Fi, menor o número.

    PC com VirtualBox/VMware/WSL tem várias placas: o IP que “sai para
    internet” pode ser o da placa virtual, que o iPhone não alcança. Por isso
    a ordem é por faixa de rede doméstica, e o resto fica no fim.
    """
    if ip.startswith("192.168."):
        return 0
    if ip.startswith("10."):
        return 1
    if ip.startswith("172."):
        try:
            segundo = int(ip.split(".")[1])
        except (IndexError, ValueError):
            return 5
        return 2 if 16 <= segundo <= 31 else 5
    if ip.startswith("169.254."):
        return 9
    return 5


def _melhor(ips: list[str]) -> str:
    """O endereço mais provável de ser a rede local. Função pura: o teste cobra."""
    validos = [ip for ip in ips if ip and not ip.startswith("127.")]
    if not validos:
        return "127.0.0.1"
    return sorted(dict.fromkeys(validos), key=_prioridade)[0]


def enderecos_locais() -> list[str]:
    """Os IPv4 deste PC, do mais provável ao menos (não envia nada)."""
    vistos: list[str] = []
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ip = str(info[4][0])
            if ip not in vistos:
                vistos.append(ip)
    except OSError:
        pass
    soquete = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        soquete.connect(("8.8.8.8", 80))
        ip = str(soquete.getsockname()[0])
        if ip not in vistos:
            vistos.insert(0, ip)
    except OSError:
        pass
    finally:
        soquete.close()
    return sorted(dict.fromkeys(vistos), key=_prioridade)


def endereco_local() -> str:
    """O IP deste PC na rede local (não envia nada: só pergunta a rota)."""
    return _melhor(enderecos_locais())


def instrucoes(
    nome: str,
    porta: int = PORTA_PADRAO,
    ip: str | None = None,
    outros: list[str] | None = None,
) -> str:
    """O que o dono faz no iPhone, em texto de console."""
    endereco = ip or endereco_local()
    if outros is None:
        outros = [item for item in enderecos_locais() if item != endereco and _prioridade(item) < 9]
    linhas = [
        "",
        "  Abra no iPhone, no Safari, com ele na MESMA rede Wi-Fi deste PC:",
        "",
        f"      http://{endereco}:{porta}/",
        "",
    ]
    if outros:
        linhas += [
            f"  Se não abrir, tente o outro endereço deste PC: http://{outros[0]}:{porta}/",
            "  (para ver todos: abra o Prompt e digite  ipconfig )",
            "",
        ]
    linhas += [
        "  Para ficar como APP no iPhone (sem App Store, sem custo):",
        "    1. abra o endereço acima no Safari;",
        "    2. toque em Compartilhar (o quadrado com a seta para cima);",
        "    3. escolha “Adicionar à Tela de Início”.",
        "    Vira um ícone com o jogo e abre em tela cheia, sem a barra do Safari.",
        "",
        "  Detalhes que fazem diferença:",
        "    - se o Windows perguntar do firewall, marque “Redes particulares”;",
        "    - Wi-Fi de visitante (ou “isolamento de clientes” no roteador) bloqueia;",
        "    - o endereço 127.0.0.1 NÃO funciona no iPhone: ele é o próprio iPhone;",
        "    - deixe esta janela aberta enquanto testa. Para parar: feche no X.",
        "",
        f"  Jogo servido: {nome}",
        "",
    ]
    return "\n".join(linhas)
