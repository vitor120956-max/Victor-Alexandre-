"""As ações que antes eram só leitura — agora com efeito, e com trava (0.92.0).

O dono olhou a lista de `docs/NAO-FAZ.md` e respondeu:

    adicione essas coisas arrume oq tiver q ser arrumado

A lista dizia “não faz por decisão”: escritório não chama o Google, correio não
envia e-mail, navegador não abre aba, carreira não envia candidatura,
portabilidade não converte, estúdio não renderiza, diagramas não desenham
Mermaid, agência não executa agente, memória é lexical, Reversa não descompila,
enxuto não roda teste, submissão não publica. Todas essas eram escolhas de
recorte — o recorte mudou.

## A regra que continua de pé

Efeito real sem trava é como o projeto não funciona. Então:

1. **tudo exige `JARVIS_ACOES=1`** — sem a variável, cada ação devolve o plano
   e a frase de como ligar, sem tocar em nada;
2. **tudo exige confirmação** (`confirmed=true` na rota / `executar=true` na
   skill), como as outras camadas com efeito;
3. **nada de shell livre**: cada ferramenta externa recebe uma lista de
   argumentos montada aqui, com caminhos resolvidos dentro da área do JARVIS;
4. **nada de credencial em resposta**: senha de SMTP e token nunca voltam no
   JSON, nem em mensagem de erro;
5. **quando falta o que fazer o efeito** (SMTP, token do Google, `jadx`,
   `pandoc`…), a resposta **diz o que instalar/configurar** e não finge.

## O que cada ação faz de verdade

| ação | como |
|---|---|
| `enviar_email` | `smtplib` com TLS, remetente e servidor do `.env` |
| `google_*` | REST do Google com o token OAuth de `JARVIS_GOOGLE_TOKEN` |
| `abrir_url` | navegador padrão do sistema (`webbrowser`) |
| `converter` | `pandoc`, LibreOffice, `ffmpeg`, ImageMagick — tabela fechada |
| `mermaid_svg` | renderizador próprio de fluxograma (sem Puppeteer) |
| `dot_svg` | Graphviz, quando instalado |
| `descompilar` | `jadx` ou `apktool`, com teto de tempo e de saída |
| `rodar_testes` | `pytest`/`npm test` dentro da pasta pedida, com timeout |
| `publicar_pr` | API do GitHub com `JARVIS_GITHUB_TOKEN` |
| `embedding` | endpoint de embeddings do provedor configurado |
| `executar_agente` | o maestro (`server/maestro.py`) rodando o plano |
"""
from __future__ import annotations

import base64
import hashlib
import json
import math
import os
import re
import shutil
import smtplib
import subprocess
import webbrowser
from email.message import EmailMessage
from email.utils import formatdate, make_msgid
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlparse
from urllib.request import Request, urlopen

FLAG = "JARVIS_ACOES"
TIMEOUT_FERRAMENTA = 600
LIMITE_SAIDA = 20_000
LIMITE_CORPO_EMAIL = 200_000
LIMITE_ANEXO = 25_000_000
MAX_DESTINATARIOS = 10

EMAIL = re.compile(r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$")
ARQUIVO_SEGURO = re.compile(r"^[A-Za-z0-9._\- ]{1,120}$")


class AcoesError(ValueError):
    """Erro esperado, em português, seguro para mostrar na tela."""


# ---------------------------------------------------------------------------
# Trava
# ---------------------------------------------------------------------------

def ligado() -> bool:
    return (os.getenv(FLAG) or "0").strip() == "1"


def exigir_ligado(acao: str) -> None:
    if ligado():
        return
    raise AcoesError(
        f"“{acao}” mexe fora do JARVIS e está desligada. Ligue com JARVIS_ACOES=1 no `.env` "
        "e reinicie a API — sem isso eu só mostro o plano."
    )


def _texto(valor: str | None, *, campo: str, limite: int) -> str:
    limpo = (valor or "").strip()
    if "\r" in limpo or "\n" in limpo:
        raise AcoesError(f"O campo “{campo}” não aceita quebra de linha.")
    if len(limpo) > limite:
        raise AcoesError(f"O campo “{campo}” passa de {limite} caracteres.")
    return limpo


def _arquivo_local(caminho: str, raiz: Path, *, campo: str = "arquivo") -> Path:
    """Um arquivo **dentro** da área do JARVIS — nada de caminho de fora."""
    bruto = (caminho or "").strip()
    if not bruto or "/" in bruto.replace("\\", "/") and ".." in bruto:
        raise AcoesError(f"Informe o {campo} pelo nome, dentro da área do JARVIS.")
    alvo = (raiz / bruto).resolve()
    base = raiz.resolve()
    if base != alvo and base not in alvo.parents:
        raise AcoesError(f"O {campo} precisa estar dentro de {base.name}/.")
    if not alvo.is_file() or alvo.is_symlink():
        raise AcoesError(f"Não achei o {campo} “{bruto}”.")
    return alvo


# ---------------------------------------------------------------------------
# Estado: o que dá para fazer nesta máquina
# ---------------------------------------------------------------------------

def _tem(ferramenta: str) -> str | None:
    return shutil.which(ferramenta)


def smtp_configurado() -> bool:
    return bool(os.getenv("JARVIS_SMTP_HOST") and os.getenv("JARVIS_SMTP_REMETENTE"))


def estado() -> dict[str, Any]:
    """O que existe agora — para a pessoa não descobrir no meio da execução."""
    return {
        "ligado": ligado(),
        "trava": FLAG,
        "email": {
            "configurado": smtp_configurado(),
            "host": os.getenv("JARVIS_SMTP_HOST", ""),
            "remetente": os.getenv("JARVIS_SMTP_REMETENTE", ""),
            "tls": (os.getenv("JARVIS_SMTP_TLS", "1") or "1") == "1",
            "falta": [] if smtp_configurado() else [
                "JARVIS_SMTP_HOST", "JARVIS_SMTP_USUARIO", "JARVIS_SMTP_SENHA", "JARVIS_SMTP_REMETENTE",
            ],
        },
        "google": {
            "configurado": bool(os.getenv("JARVIS_GOOGLE_TOKEN")),
            "falta": [] if os.getenv("JARVIS_GOOGLE_TOKEN") else ["JARVIS_GOOGLE_TOKEN"],
        },
        "github": {
            "configurado": bool(os.getenv("JARVIS_GITHUB_TOKEN")),
            "falta": [] if os.getenv("JARVIS_GITHUB_TOKEN") else ["JARVIS_GITHUB_TOKEN"],
        },
        "ferramentas": {
            nome: bool(_tem(nome))
            for nome in (
                "pandoc", "soffice", "libreoffice", "ffmpeg", "convert", "magick",
                "dot", "jadx", "apktool", "node", "npm",
            )
        },
        "embeddings": {
            "configurado": bool(os.getenv("JARVIS_AI_API_KEY") and os.getenv("JARVIS_AI_BASE_URL")),
            "modelo": os.getenv("JARVIS_EMBEDDINGS_MODEL", "text-embedding-3-small"),
        },
    }


# ---------------------------------------------------------------------------
# 1. Correio: enviar e-mail de verdade
# ---------------------------------------------------------------------------

def enviar_email(
    *,
    para: str | list[str],
    assunto: str,
    corpo: str,
    anexos: list[str] | None = None,
    raiz: Path | None = None,
    confirmado: bool = False,
) -> dict[str, Any]:
    """Manda o e-mail pelo SMTP do `.env`. Sem confirmação, devolve o plano."""
    destinos = [para] if isinstance(para, str) else list(para)
    destinos = [_texto(item, campo="para", limite=200) for item in destinos]
    destinos = [item for item in destinos if item]
    if not destinos:
        raise AcoesError("Diga para quem enviar (um e-mail por vez, até 10).")
    if len(destinos) > MAX_DESTINATARIOS:
        raise AcoesError(f"São no máximo {MAX_DESTINATARIOS} destinatários por envio.")
    for item in destinos:
        if not EMAIL.match(item):
            raise AcoesError(f"“{item}” não parece um e-mail válido.")
    assunto = _texto(assunto, campo="assunto", limite=200)
    if not assunto:
        raise AcoesError("O assunto não pode ficar vazio.")
    if len(corpo) > LIMITE_CORPO_EMAIL:
        raise AcoesError(f"O corpo passa de {LIMITE_CORPO_EMAIL:,} caracteres.")
    anexados: list[str] = []
    caminhos: list[Path] = []
    for nome in anexos or []:
        if raiz is None:
            raise AcoesError("Para anexar, informe a área de arquivos do JARVIS.")
        alvo = _arquivo_local(nome, raiz)
        if alvo.stat().st_size > LIMITE_ANEXO:
            raise AcoesError(f"O anexo “{alvo.name}” passa de {LIMITE_ANEXO // 1_000_000} MB.")
        caminhos.append(alvo)
        anexados.append(alvo.name)

    # O plano sai mesmo sem SMTP: mostrar o que vai ser enviado é útil antes de
    # configurar, e a falta aparece como `falta` em vez de esconder o recado.
    plano = {
        "executado": False,
        "para": destinos,
        "assunto": assunto,
        "anexos": anexados,
        "servidor": os.getenv("JARVIS_SMTP_HOST", ""),
        "o_que_fazer": "Confirme o envio (confirmed=true) para mandar de verdade.",
    }
    if not smtp_configurado():
        faltam = [
            nome
            for nome in ("JARVIS_SMTP_HOST", "JARVIS_SMTP_USUARIO", "JARVIS_SMTP_SENHA", "JARVIS_SMTP_REMETENTE")
            if not os.getenv(nome)
        ]
        recado = (
            "Falta o SMTP no `.env`: "
            + ", ".join(faltam)
            + ". No Gmail, a senha é a “senha de app”, não a do login."
        )
        if not confirmado:
            return {**plano, "executado": False, "falta": faltam, "aviso": recado}
        raise AcoesError(recado)

    mensagem = EmailMessage()
    mensagem["From"] = os.environ["JARVIS_SMTP_REMETENTE"]
    mensagem["To"] = ", ".join(destinos)
    mensagem["Subject"] = assunto
    mensagem["Date"] = formatdate(localtime=True)
    mensagem["Message-ID"] = make_msgid(domain="jarvis.local")
    mensagem.set_content(corpo)
    for alvo in caminhos:
        mensagem.add_attachment(
            alvo.read_bytes(), maintype="application", subtype="octet-stream", filename=alvo.name
        )

    if not confirmado:
        return plano
    exigir_ligado("enviar e-mail")

    host = os.environ["JARVIS_SMTP_HOST"].strip()
    porta = int(os.getenv("JARVIS_SMTP_PORTA", "587") or "587")
    usuario = os.getenv("JARVIS_SMTP_USUARIO", "").strip()
    senha = os.getenv("JARVIS_SMTP_SENHA", "")
    usar_tls = (os.getenv("JARVIS_SMTP_TLS", "1") or "1") == "1"
    try:
        with smtplib.SMTP(host, porta, timeout=30) as servidor:
            servidor.ehlo()
            if usar_tls:
                servidor.starttls()
                servidor.ehlo()
            if usuario:
                servidor.login(usuario, senha)
            servidor.send_message(mensagem)
    except (smtplib.SMTPException, OSError) as exc:
        # A mensagem de erro do SMTP pode conter o endereço — nunca a senha.
        raise AcoesError(
            f"O servidor {host}:{porta} recusou o envio ({type(exc).__name__}). "
            "Confira host, porta, e a senha de app (no Gmail, a senha normal não serve)."
        ) from exc

    return {
        "executado": True,
        "para": destinos,
        "assunto": assunto,
        "anexos": anexados,
        "servidor": host,
        "mensagem": f"Enviado para {len(destinos)} destinatário(s).",
    }


# ---------------------------------------------------------------------------
# 2. Escritório: chamar o Google de verdade
# ---------------------------------------------------------------------------

GOOGLE_HOSTS = {"gmail.googleapis.com", "www.googleapis.com", "sheets.googleapis.com"}


def _google(pedido: Request, *, o_que: str) -> dict[str, Any]:
    token = (os.getenv("JARVIS_GOOGLE_TOKEN") or "").strip()
    if not token:
        raise AcoesError(
            "Falta JARVIS_GOOGLE_TOKEN no `.env`. Gere em https://developers.google.com/oauthplayground "
            "com os escopos de Gmail/Drive/Calendar/Sheets que você vai usar."
        )
    pedido.add_header("Authorization", f"Bearer {token}")
    pedido.add_header("Content-Type", "application/json")
    try:
        with urlopen(pedido, timeout=30) as resposta:  # noqa: S310 - host fechado abaixo
            if urlparse(pedido.full_url).hostname not in GOOGLE_HOSTS:
                raise AcoesError("Endereço fora da lista do Google.")
            return json.loads(resposta.read().decode("utf-8") or "{}")
    except HTTPError as exc:
        detalhe = ""
        try:
            detalhe = json.loads(exc.read().decode("utf-8")).get("error", {}).get("message", "")
        except (ValueError, OSError):
            detalhe = ""
        raise AcoesError(
            f"O Google recusou {o_que} (HTTP {exc.code})"
            + (f": {detalhe}" if detalhe else ".")
            + " Confira os escopos do token e se ele não venceu."
        ) from exc
    except (URLError, OSError) as exc:
        raise AcoesError(f"Não consegui falar com o Google ({type(exc).__name__}).") from exc


def google_email(*, para: str, assunto: str, corpo: str, confirmado: bool = False) -> dict[str, Any]:
    """Manda e-mail pelo Gmail (API), usando o token OAuth do `.env`."""
    for item, campo in ((para, "para"), (assunto, "assunto")):
        _texto(item, campo=campo, limite=200)
    if not EMAIL.match(para.strip()):
        raise AcoesError(f"“{para}” não parece um e-mail válido.")
    plano = {"executado": False, "para": para, "assunto": assunto, "via": "Gmail API"}
    if not confirmado:
        plano["o_que_fazer"] = "Confirme o envio para mandar pelo Gmail."
        return plano
    exigir_ligado("enviar pelo Gmail")

    bruto = (
        f"To: {para}\r\nSubject: {assunto}\r\nMIME-Version: 1.0\r\n"
        "Content-Type: text/plain; charset=UTF-8\r\n\r\n"
        f"{corpo}"
    )
    codificado = base64.urlsafe_b64encode(bruto.encode("utf-8")).decode("ascii")
    dados = json.dumps({"raw": codificado}).encode("utf-8")
    pedido = Request(
        "https://gmail.googleapis.com/gmail/v1/users/me/messages/send",
        data=dados,
        method="POST",
    )
    resposta = _google(pedido, o_que="o envio")
    return {"executado": True, "para": para, "assunto": assunto, "id": resposta.get("id", "")}


def google_listar(*, pasta: str = "", limite: int = 20) -> dict[str, Any]:
    """Lista arquivos do Drive (ou mensagens do Gmail, com `pasta="gmail"`)."""
    exigir_ligado("consultar o Google")
    limite = max(1, min(int(limite), 100))
    if pasta.lower() == "gmail":
        pedido = Request(
            "https://gmail.googleapis.com/gmail/v1/users/me/messages?"
            f"maxResults={limite}",
            method="GET",
        )
        resposta = _google(pedido, o_que="a listagem")
        itens = resposta.get("messages", [])
        return {"executado": True, "origem": "gmail", "itens": itens, "quantidade": len(itens)}

    consulta = quote(f"'{pasta}' in parents and trashed = false") if pasta else quote("trashed = false")
    pedido = Request(
        "https://www.googleapis.com/drive/v3/files?"
        f"q={consulta}&pageSize={limite}&fields=files(id,name,mimeType,size)",
        method="GET",
    )
    resposta = _google(pedido, o_que="a listagem")
    arquivos = resposta.get("files", [])
    return {"executado": True, "origem": "drive", "itens": arquivos, "quantidade": len(arquivos)}


def google_evento(*, titulo: str, inicio: str, fim: str, confirmado: bool = False) -> dict[str, Any]:
    """Cria um evento no calendário principal (ISO 8601, com fuso)."""
    _texto(titulo, campo="titulo", limite=200)
    for valor, campo in ((inicio, "inicio"), (fim, "fim")):
        if not re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(:\d{2})?([+-]\d{2}:\d{2}|Z)?$", valor.strip()):
            raise AcoesError(f"“{campo}” precisa ser data e hora ISO 8601 (ex.: 2026-11-20T19:00:00-03:00).")
    plano = {"executado": False, "titulo": titulo, "inicio": inicio, "fim": fim}
    if not confirmado:
        plano["o_que_fazer"] = "Confirme para criar o evento no calendário principal."
        return plano
    exigir_ligado("criar evento no Google")
    corpo = json.dumps(
        {
            "summary": titulo,
            "start": {"dateTime": inicio.strip()},
            "end": {"dateTime": fim.strip()},
        }
    ).encode("utf-8")
    pedido = Request(
        "https://www.googleapis.com/calendar/v3/calendars/primary/events",
        data=corpo,
        method="POST",
    )
    resposta = _google(pedido, o_que="a criação do evento")
    return {"executado": True, "titulo": titulo, "id": resposta.get("id", ""), "link": resposta.get("htmlLink", "")}


def google_planilha(*, planilha: str, aba: str, valores: list[list[str]], confirmado: bool = False) -> dict[str, Any]:
    """Acrescenta linhas numa planilha (A1 notation simples)."""
    if not re.match(r"^[A-Za-z0-9_\-]{10,120}$", planilha.strip()):
        raise AcoesError("O ID da planilha tem cara errada (use o trecho entre /d/ e /edit da URL).")
    aba = _texto(aba or "A1", campo="aba", limite=60)
    if not valores or len(valores) > 500:
        raise AcoesError("Mande de 1 a 500 linhas por vez.")
    plano = {"executado": False, "planilha": planilha, "aba": aba, "linhas": len(valores)}
    if not confirmado:
        plano["o_que_fazer"] = "Confirme para acrescentar as linhas na planilha."
        return plano
    exigir_ligado("escrever no Google Sheets")
    faixa = quote(f"{aba}!A1")
    corpo = json.dumps({"values": valores}).encode("utf-8")
    pedido = Request(
        f"https://sheets.googleapis.com/v4/spreadsheets/{planilha}/values/{faixa}:append"
        "?valueInputOption=RAW&insertDataOption=INSERT_ROWS",
        data=corpo,
        method="POST",
    )
    resposta = _google(pedido, o_que="a escrita na planilha")
    return {"executado": True, "planilha": planilha, "aba": aba, "atualizadas": resposta.get("updates", {})}


# ---------------------------------------------------------------------------
# 3. Navegador: abrir a aba de verdade
# ---------------------------------------------------------------------------

def abrir_url(url: str, *, confirmado: bool = False) -> dict[str, Any]:
    """Abre no navegador padrão — só http/https, sem credencial embutida."""
    endereco = (url or "").strip()
    partes = urlparse(endereco)
    if partes.scheme not in {"http", "https"} or not partes.hostname:
        raise AcoesError("Só abro endereço http/https completo (ex.: https://exemplo.com).")
    if partes.username or partes.password:
        raise AcoesError("Endereço com usuário e senha embutidos não é aberto.")
    plano = {"executado": False, "url": endereco}
    if not confirmado:
        plano["o_que_fazer"] = "Confirme para abrir esta aba no navegador padrão."
        return plano
    exigir_ligado("abrir o navegador")
    try:
        aberto = webbrowser.open(endereco, new=2)
    except (OSError, webbrowser.Error) as exc:
        raise AcoesError(f"O sistema não abriu o navegador ({type(exc).__name__}).") from exc
    if not aberto:
        raise AcoesError(
            "Nenhum navegador padrão respondeu. Abra este endereço na mão: " + endereco
        )
    return {"executado": True, "url": endereco, "mensagem": "Aberto no navegador padrão."}


# ---------------------------------------------------------------------------
# 4. Portabilidade: converter arquivo de verdade
# ---------------------------------------------------------------------------

# (origem, destino) → (ferramenta, argumentos). `{entrada}` e `{saida}` são
# substituídos por caminhos resolvidos aqui; nada de texto livre na linha.
CONVERSOES: dict[tuple[str, str], tuple[str, tuple[str, ...]]] = {
    ("md", "pdf"): ("pandoc", ("{entrada}", "-o", "{saida}")),
    ("md", "docx"): ("pandoc", ("{entrada}", "-o", "{saida}")),
    ("md", "html"): ("pandoc", ("{entrada}", "-o", "{saida}", "--standalone")),
    ("docx", "pdf"): ("soffice", ("--headless", "--convert-to", "pdf", "--outdir", "{pasta}", "{entrada}")),
    ("docx", "md"): ("pandoc", ("{entrada}", "-o", "{saida}")),
    ("html", "pdf"): ("soffice", ("--headless", "--convert-to", "pdf", "--outdir", "{pasta}", "{entrada}")),
    ("png", "jpg"): ("magick", ("{entrada}", "{saida}")),
    ("jpg", "png"): ("magick", ("{entrada}", "{saida}")),
    ("wav", "mp3"): ("ffmpeg", ("-y", "-i", "{entrada}", "{saida}")),
    ("mp4", "mp3"): ("ffmpeg", ("-y", "-i", "{entrada}", "-vn", "{saida}")),
    ("mov", "mp4"): ("ffmpeg", ("-y", "-i", "{entrada}", "{saida}")),
}


def conversoes_possiveis() -> list[dict[str, Any]]:
    """A tabela fechada, marcando o que esta máquina consegue rodar agora."""
    itens = []
    for (origem, destino), (ferramenta, _) in sorted(CONVERSOES.items()):
        alternativa = "magick" if ferramenta == "magick" and _tem("convert") else ferramenta
        itens.append(
            {
                "de": origem,
                "para": destino,
                "ferramenta": ferramenta,
                "disponivel": bool(_tem(alternativa)),
            }
        )
    return itens


def converter(
    *,
    origem: str,
    formato: str,
    raiz: Path,
    saida: str = "",
    confirmado: bool = False,
) -> dict[str, Any]:
    """Converte um arquivo da área do JARVIS pela tabela fechada."""
    de = Path((origem or "").strip()).suffix.lower().lstrip(".")
    para = (formato or "").strip().lower().lstrip(".")
    chave = (de, para)
    if chave not in CONVERSOES:
        opcoes = ", ".join(f"{a}→{b}" for a, b in sorted(CONVERSOES))
        raise AcoesError(f"Não converto {de or '?'} → {para or '?'}. A tabela é: {opcoes}.")
    alvo = _arquivo_local(origem, raiz, campo="arquivo")
    ferramenta, argumentos = CONVERSOES[chave]

    nome_saida = (saida or f"{alvo.stem}.{para}").strip()
    if not ARQUIVO_SEGURO.match(nome_saida):
        nome_saida = f"{alvo.stem}.{para}"
    destino = (alvo.parent / nome_saida).resolve()
    if raiz.resolve() not in destino.parents:
        raise AcoesError("A saída precisa ficar dentro da área do JARVIS.")
    if destino.suffix.lower() != f".{para}":
        raise AcoesError(f"O nome de saída precisa terminar em .{para}.")

    executavel = ferramenta
    if ferramenta == "magick" and not _tem("magick") and _tem("convert"):
        executavel = "convert"
    if not _tem(executavel):
        raise AcoesError(
            f"Falta o “{ferramenta}” nesta máquina. Instale e rode de novo — "
            "eu não converto “mais ou menos”."
        )

    plano = {
        "executado": False,
        "de": de,
        "para": para,
        "ferramenta": executavel,
        "saida": destino.name,
        "bytes": alvo.stat().st_size,
    }
    if not confirmado:
        plano["o_que_fazer"] = f"Confirme para rodar {executavel} e gravar {destino.name}."
        return plano
    exigir_ligado("converter arquivo")

    montados = [
        item.format(entrada=str(alvo), saida=str(destino), pasta=str(destino.parent))
        for item in argumentos
    ]
    try:
        resultado = subprocess.run(  # noqa: S603 - argv fechado, sem shell
            [executavel, *montados],
            capture_output=True,
            text=True,
            timeout=TIMEOUT_FERRAMENTA,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise AcoesError(f"“{executavel}” não terminou ({type(exc).__name__}).") from exc
    if resultado.returncode != 0 or not destino.is_file():
        raise AcoesError(
            f"“{executavel}” falhou (código {resultado.returncode}): "
            + (resultado.stderr or resultado.stdout or "sem mensagem")[:400]
        )
    return {
        "executado": True,
        "de": de,
        "para": para,
        "ferramenta": executavel,
        "saida": destino.name,
        "bytes": destino.stat().st_size,
    }


# ---------------------------------------------------------------------------
# 5. Diagramas: desenhar de verdade
# ---------------------------------------------------------------------------

def _nos_do_mermaid(texto: str) -> tuple[list[tuple[str, str]], list[tuple[str, str, str]], str]:
    """Lê `flowchart`/`graph` simples: nós, arestas e direção.

    Suporta o que se escreve no dia a dia — `A[Texto] --> B(Outro)` — e recusa o
    resto com a lista do que entende, em vez de desenhar pela metade.
    """
    linhas = [linha.strip() for linha in texto.splitlines() if linha.strip()]
    if not linhas:
        raise AcoesError("O diagrama está vazio.")
    cabecalho = linhas[0].lower()
    if not (cabecalho.startswith("flowchart") or cabecalho.startswith("graph")):
        raise AcoesError(
            "Hoje eu desenho `flowchart`/`graph` do Mermaid. Sequência, classe e gantt ainda não."
        )
    direcao = "TD"
    partes = linhas[0].split()
    if len(partes) > 1 and partes[1].upper() in {"TD", "TB", "LR", "RL", "BT"}:
        direcao = partes[1].upper()
    if direcao == "TB":
        direcao = "TD"

    nos: dict[str, str] = {}
    arestas: list[tuple[str, str, str]] = []

    def extrair(rotulo: str) -> tuple[str, str]:
        achado = re.fullmatch(r"([A-Za-z0-9_\-]+)\s*(?:\[(.*?)\]|\((.*?)\)|\{(.*?)\})?", rotulo.strip())
        if not achado:
            raise AcoesError(f"Não entendi o nó “{rotulo}”. Use A[Texto] ou só A.")
        nome = achado.group(1)
        texto_no = achado.group(2) or achado.group(3) or achado.group(4) or nome
        return nome, texto_no.strip().strip('"')

    def registrar(nome: str, rotulo: str) -> None:
        # Nó já nomeado antes (`B[Pedido] --> C[Pago]`) não perde o rótulo quando
        # aparece solto depois (`B --> D`). Sem isto, a segunda linha apagava o
        # texto do nó — defeito achado pelo teste em 0.92.0.
        if nome not in nos or (rotulo != nome and nos[nome] == nome):
            nos[nome] = rotulo

    for linha in linhas[1:]:
        if linha.startswith("%%") or linha.startswith("style") or linha.startswith("classDef"):
            continue
        pedacos = re.split(r"\s*(-->|---|==>|\.->|-.->)\s*", linha)
        if len(pedacos) >= 3:
            # `A --> B --> C` vira duas arestas, em vez de virar erro.
            for indice in range(0, len(pedacos) - 2, 2):
                esquerda, seta, direita = pedacos[indice], pedacos[indice + 1], pedacos[indice + 2]
                origem, rotulo_origem = extrair(esquerda)
                destino, rotulo_destino = extrair(direita)
                registrar(origem, rotulo_origem)
                registrar(destino, rotulo_destino)
                arestas.append((origem, destino, seta))
        else:
            nome, rotulo = extrair(linha)
            registrar(nome, rotulo)

    if not nos:
        raise AcoesError("O diagrama não tem nenhum nó.")
    return list(nos.items()), arestas, direcao


def mermaid_svg(texto: str, *, confirmado: bool = False, raiz: Path | None = None, nome: str = "") -> dict[str, Any]:
    """Desenha um fluxograma Mermaid em SVG — sem navegador, sem `mmdc`."""
    nos, arestas, direcao = _nos_do_mermaid(texto)
    largura_no, altura_no, espaco = 180, 56, 46
    if direcao in {"LR", "RL"}:
        posicoes = {nome: (indice * (largura_no + espaco) + 20, 20) for indice, (nome, _) in enumerate(nos)}
        largura = 40 + len(nos) * (largura_no + espaco)
        altura = 120
    else:
        posicoes = {nome: (40, indice * (altura_no + espaco) + 20) for indice, (nome, _) in enumerate(nos)}
        largura = largura_no + 80
        altura = 40 + len(nos) * (altura_no + espaco)

    def escapar(valor: str) -> str:
        return (
            valor.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")
        )

    pedacos = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{largura}" height="{altura}" '
        f'viewBox="0 0 {largura} {altura}" role="img" aria-label="Diagrama">',
        '<defs><marker id="seta" markerWidth="10" markerHeight="10" refX="8" refY="3" orient="auto">'
        '<path d="M0,0 L0,6 L9,3 z" fill="#94a3b8"/></marker></defs>',
        '<rect width="100%" height="100%" fill="#0b1120"/>',
    ]
    for origem, destino, _ in arestas:
        x1, y1 = posicoes[origem]
        x2, y2 = posicoes[destino]
        if direcao in {"LR", "RL"}:
            inicio = (x1 + largura_no, y1 + altura_no / 2)
            fim = (x2, y2 + altura_no / 2)
        else:
            inicio = (x1 + largura_no / 2, y1 + altura_no)
            fim = (x2 + largura_no / 2, y2)
        pedacos.append(
            f'<line x1="{inicio[0]}" y1="{inicio[1]}" x2="{fim[0]}" y2="{fim[1]}" '
            'stroke="#94a3b8" stroke-width="2" marker-end="url(#seta)"/>'
        )
    for nome_no, rotulo in nos:
        x, y = posicoes[nome_no]
        pedacos.append(
            f'<rect x="{x}" y="{y}" width="{largura_no}" height="{altura_no}" rx="10" '
            'fill="#111c33" stroke="#3b82f6" stroke-width="2"/>'
        )
        pedacos.append(
            f'<text x="{x + largura_no / 2}" y="{y + altura_no / 2 + 5}" text-anchor="middle" '
            'font-family="Inter, Arial, sans-serif" font-size="14" fill="#e2e8f0">'
            f"{escapar(rotulo)}</text>"
        )
    pedacos.append("</svg>")
    svg = "".join(pedacos)

    plano = {
        "executado": False,
        "nos": len(nos),
        "arestas": len(arestas),
        "bytes": len(svg.encode("utf-8")),
        "svg": svg if len(svg) < 4_000 else svg[:4_000] + "…",
    }
    if not confirmado:
        plano["o_que_fazer"] = "Confirme para gravar o SVG na área do JARVIS."
        return plano
    exigir_ligado("desenhar diagrama")
    if raiz is None:
        raise AcoesError("Para gravar o SVG, informe a área de arquivos do JARVIS.")
    nome_seguro = ARQUIVO_SEGURO.match(nome or "") and nome or "diagrama.svg"
    if not nome_seguro.lower().endswith(".svg"):
        nome_seguro = f"{Path(nome_seguro).stem or 'diagrama'}.svg"
    destino = (raiz / nome_seguro).resolve()
    if raiz.resolve() not in destino.parents and destino.parent != raiz.resolve():
        raise AcoesError("A saída precisa ficar dentro da área do JARVIS.")
    destino.write_text(svg, encoding="utf-8")
    return {**plano, "executado": True, "saida": destino.name, "bytes": destino.stat().st_size}


def dot_svg(texto: str, *, confirmado: bool = False, raiz: Path | None = None, nome: str = "diagrama.svg") -> dict[str, Any]:
    """Desenha DOT com o Graphviz (`dot -Tsvg`), quando ele está instalado."""
    if not (texto or "").strip().startswith(("digraph", "graph")):
        raise AcoesError("O texto precisa começar com `digraph`/`graph`.")
    if len(texto) > 60_000:
        raise AcoesError("O DOT passa de 60 mil caracteres.")
    if not _tem("dot"):
        raise AcoesError("Falta o Graphviz (`dot`) nesta máquina. Instale e rode de novo.")
    plano = {"executado": False, "ferramenta": "dot", "linhas": len(texto.splitlines())}
    if not confirmado:
        plano["o_que_fazer"] = "Confirme para rodar o Graphviz e gravar o SVG."
        return plano
    exigir_ligado("desenhar DOT")
    if raiz is None:
        raise AcoesError("Para gravar o SVG, informe a área de arquivos do JARVIS.")
    try:
        resultado = subprocess.run(  # noqa: S603 - argv fechado
            ["dot", "-Tsvg"], input=texto, capture_output=True, text=True, timeout=60, check=False
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise AcoesError(f"O Graphviz não terminou ({type(exc).__name__}).") from exc
    if resultado.returncode != 0:
        raise AcoesError("O Graphviz recusou o DOT: " + (resultado.stderr or "")[:400])
    destino = (raiz / (Path(nome).stem or "diagrama")).with_suffix(".svg")
    destino.write_text(resultado.stdout, encoding="utf-8")
    return {"executado": True, "saida": destino.name, "bytes": destino.stat().st_size}


# ---------------------------------------------------------------------------
# 6. Reversa: descompilar de verdade
# ---------------------------------------------------------------------------

def ferramentas_reversa() -> dict[str, Any]:
    return {
        "jadx": bool(_tem("jadx")),
        "apktool": bool(_tem("apktool")),
        "unzip": bool(_tem("unzip") or shutil.which("python")),
    }


def descompilar(
    *,
    arquivo: str,
    raiz: Path,
    destino: str = "",
    ferramenta: str = "jadx",
    confirmado: bool = False,
) -> dict[str, Any]:
    """Descompila APK/DEX em pasta separada — `jadx` ou `apktool`, nada além."""
    alvo = _arquivo_local(arquivo, raiz, campo="APK")
    if alvo.suffix.lower() not in {".apk", ".dex", ".jar", ".aab", ".xapk"}:
        raise AcoesError("A descompilação aceita APK, AAB, APKS, XAPK, JAR ou DEX.")
    escolhida = (ferramenta or "jadx").strip().lower()
    if escolhida not in {"jadx", "apktool"}:
        raise AcoesError("A ferramenta é `jadx` (código Java) ou `apktool` (recursos e smali).")
    if not _tem(escolhida):
        raise AcoesError(
            f"Falta o `{escolhida}` nesta máquina. jadx: github.com/skylot/jadx (zip, sem instalador); "
            "apktool: apktool.org. Depois de instalar, rode de novo."
        )
    nome_pasta = ARQUIVO_SEGURO.match(destino or "") and (destino or "") or f"{alvo.stem}-{escolhida}"
    pasta = (raiz / Path(nome_pasta).stem).resolve()
    if raiz.resolve() not in pasta.parents:
        raise AcoesError("A saída precisa ficar dentro da área do JARVIS.")

    plano = {
        "executado": False,
        "ferramenta": escolhida,
        "apk": alvo.name,
        "saida": str(pasta.relative_to(raiz.resolve())),
        "aviso": "Descompilar não executa o app: o resultado é código e recursos no disco.",
    }
    if not confirmado:
        plano["o_que_fazer"] = f"Confirme para rodar o {escolhida} e gravar em {pasta.name}/."
        return plano
    exigir_ligado("descompilar APK")

    if escolhida == "jadx":
        comando = ["jadx", "-d", str(pasta), "--no-res", str(alvo)]
    else:
        comando = ["apktool", "d", "-f", "-o", str(pasta), str(alvo)]
    try:
        resultado = subprocess.run(  # noqa: S603 - argv fechado
            comando, capture_output=True, text=True, timeout=TIMEOUT_FERRAMENTA, check=False
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise AcoesError(f"“{escolhida}” não terminou ({type(exc).__name__}).") from exc
    if resultado.returncode != 0 or not pasta.is_dir():
        raise AcoesError(
            f"“{escolhida}” falhou (código {resultado.returncode}): "
            + (resultado.stderr or resultado.stdout or "")[:400]
        )
    arquivos = sum(1 for _ in pasta.rglob("*") if _.is_file())
    bytes_totais = sum(item.stat().st_size for item in pasta.rglob("*") if item.is_file())
    return {
        **plano,
        "executado": True,
        "arquivos": arquivos,
        "bytes": bytes_totais,
        "mensagem": f"{arquivos} arquivos gravados em {pasta.name}/.",
    }


# ---------------------------------------------------------------------------
# 7. Enxuto: rodar teste de verdade
# ---------------------------------------------------------------------------

COMANDOS_DE_TESTE = {
    "pytest": ["pytest", "-q", "--maxfail=5"],
    "pytest-full": ["pytest", "-q"],
    "npm": ["npm", "test", "--silent"],
}


def rodar_testes(
    *,
    pasta: str,
    raiz: Path,
    comando: str = "pytest",
    timeout: int = TIMEOUT_FERRAMENTA,
    confirmado: bool = False,
) -> dict[str, Any]:
    """Roda a suíte de uma pasta **dentro** da área do JARVIS e devolve a saída."""
    base = (raiz / (pasta or ".")).resolve()
    if raiz.resolve() != base and raiz.resolve() not in base.parents:
        raise AcoesError("A pasta do projeto precisa estar dentro da área do JARVIS.")
    if not base.is_dir():
        raise AcoesError(f"Não achei a pasta “{pasta}”.")
    escolhido = (comando or "pytest").strip()
    if escolhido not in COMANDOS_DE_TESTE:
        raise AcoesError(f"Comando de teste fora da lista: use {', '.join(COMANDOS_DE_TESTE)}.")
    argumentos = COMANDOS_DE_TESTE[escolhido]
    if not _tem(argumentos[0]):
        raise AcoesError(
            f"“{argumentos[0]}” não está no PATH desta máquina. "
            + ("Instale com: .venv\\Scripts\\pip install pytest" if argumentos[0] == "pytest" else "Instale o Node.js.")
        )
    if not (base / "package.json").is_file() and escolhido.startswith("npm"):
        raise AcoesError("A pasta não tem `package.json` — não há suíte npm para rodar.")

    plano = {"executado": False, "pasta": str(base.relative_to(raiz.resolve())), "comando": escolhido}
    if not confirmado:
        plano["o_que_fazer"] = f"Confirme para rodar “{' '.join(argumentos)}” nessa pasta."
        return plano
    exigir_ligado("rodar testes")

    try:
        resultado = subprocess.run(  # noqa: S603 - argv fechado
            argumentos,
            cwd=base,
            capture_output=True,
            text=True,
            timeout=max(30, min(int(timeout), 3600)),
            check=False,
        )
    except subprocess.TimeoutExpired:
        raise AcoesError(f"A suíte passou de {timeout} s e foi interrompida.") from None
    except OSError as exc:
        raise AcoesError(f"Não consegui rodar o teste ({type(exc).__name__}).") from exc

    saida = (resultado.stdout or "") + (("\n" + resultado.stderr) if resultado.stderr else "")
    return {
        **plano,
        "executado": True,
        "codigo": resultado.returncode,
        "passou": resultado.returncode == 0,
        "saida": saida[:LIMITE_SAIDA],
        "cortada": len(saida) > LIMITE_SAIDA,
        "mensagem": "A suíte passou." if resultado.returncode == 0 else f"A suíte falhou (código {resultado.returncode}).",
    }


# ---------------------------------------------------------------------------
# 8. Submissão: publicar de verdade (branch + PR no GitHub)
# ---------------------------------------------------------------------------

_PACOTE = re.compile(r"^[A-Za-z][A-Za-z0-9_]*(\.[A-Za-z][A-Za-z0-9_]*)+$")


def _exigir_pacote(pacote: str) -> str:
    """Nome de pacote Android — e só isso. É o que entra na linha de comando."""
    limpo = (pacote or "").strip()
    if not _PACOTE.match(limpo) or len(limpo) > 160:
        raise AcoesError(
            "Nome de pacote inválido. Use o nome do app como o Android conhece, "
            "ex.: com.whatsapp — não o nome de exibição."
        )
    return limpo


def _exigir_celular(acao: str) -> tuple[str, str]:
    """Devolve (adb, serial) ou explica o que falta. Nunca inventa aparelho."""
    from . import anatomia, celular

    if not celular.ligado():
        raise AcoesError(
            "O controle do celular está desligado. Acrescente `set JARVIS_HOST_CELULAR=1` no "
            "iniciar-jarvis.bat, feche e abra de novo."
        )
    try:
        adb = anatomia._adb()  # noqa: SLF001
    except Exception as exc:  # noqa: BLE001 - a frase do módulo já é a boa
        raise AcoesError(str(exc)) from exc
    conectados = [a for a in anatomia.aparelhos() if a.get("estado") == "device"]
    if not conectados:
        raise AcoesError(
            f"“{acao}” precisa do aparelho conectado e autorizado. Confira o cabo (de dados), "
            "a Depuração USB ligada e o toque em “Permitir” na tela."
        )
    return adb, conectados[0]["serial"]


def _celular_rodar(adb: str, serial: str, argumentos: list[str], timeout: int = 120) -> dict[str, Any]:
    from . import anatomia

    codigo, saida, erro = anatomia._rodar([adb, "-s", serial, *argumentos], timeout=timeout)  # noqa: SLF001
    texto = (saida or "").strip()
    return {
        "codigo": codigo,
        "saida": texto[:4000],
        "erro": (erro or "").strip()[:4000],
        "ok": codigo == 0,
    }


def celular_abrir_app(pacote: str, *, confirmado: bool = False) -> dict[str, Any]:
    """Abre um app **já instalado** no celular do dono.

    `am start` só inicia uma atividade existente; não instala, não altera app e
    não pede conta. O pacote passa por regex antes de virar argumento.
    """
    nome = _exigir_pacote(pacote)
    exigir_ligado("abrir app no celular")
    if not confirmado:
        return {
            "plano": f"abrir {nome}",
            "comando": "am start -n <pacote>/<atividade>",
            "nota": "Sem `confirmed: true` nada é aberto no aparelho.",
        }
    adb, serial = _exigir_celular("abrir app")
    # `monkey` é o jeito padrão de abrir sem saber o nome da atividade; é leitura
    # de pacote, não execução de código do app.
    resultado = _celular_rodar(adb, serial, ["shell", "monkey", "-p", nome, "-c", "android.intent.category.LAUNCHER", "1"])
    if not resultado["ok"]:
        raise AcoesError(
            f"O Android não abriu {nome}. Confira se o app está instalado "
            f"(`pm list packages | grep {nome}`). Resposta: {resultado['erro'] or resultado['saida']}"
        )
    return {"aberto": nome, "aparelho": serial, "saida": resultado["saida"][:600]}


def celular_fechar_app(pacote: str, *, confirmado: bool = False) -> dict[str, Any]:
    """Fecha (força a parada) um app. O dono perde o que não estava salvo."""
    nome = _exigir_pacote(pacote)
    exigir_ligado("fechar app no celular")
    if not confirmado:
        return {
            "plano": f"fechar {nome}",
            "aviso": "Fechar descarta o que não estava salvo dentro do app. Nada mais é apagado.",
            "nota": "Sem `confirmed: true` nada é fechado no aparelho.",
        }
    adb, serial = _exigir_celular("fechar app")
    resultado = _celular_rodar(adb, serial, ["shell", "am", "force-stop", nome])
    if not resultado["ok"]:
        raise AcoesError(f"O Android não fechou {nome}: {resultado['erro'] or resultado['saida']}")
    return {"fechado": nome, "aparelho": serial}


def celular_instalar_apk(arquivo: str, raiz: Path, *, confirmado: bool = False) -> dict[str, Any]:
    """Instala um APK que **já está** na área do JARVIS — por `adb install`."""
    alvo = _arquivo_local(arquivo, raiz, campo="APK")
    if alvo.suffix.lower() != ".apk":
        raise AcoesError("A instalação aceita só `.apk`. App de iPhone (`.ipa`) não roda no Android.")
    exigir_ligado("instalar app no celular")
    if not confirmado:
        return {
            "plano": f"instalar {alvo.name} em {alvo.stat().st_size / 1e6:.1f} MB",
            "nota": "Sem `confirmed: true` nada é instalado no aparelho. O Android ainda pode pedir "
            "“Instalar apps desconhecidos” na tela.",
        }
    adb, serial = _exigir_celular("instalar app")
    resultado = _celular_rodar(
        adb, serial, ["install", "-r", str(alvo)], timeout=600
    )
    if not resultado["ok"] or "Success" not in resultado["saida"]:
        raise AcoesError(
            "O Android recusou a instalação. As causas comuns: “Instalar apps desconhecidos” "
            f"desligado para o app que pediu, APK de outra arquitetura ou assinatura diferente. "
            f"Resposta: {resultado['saida'] or resultado['erro']}"
        )
    return {"instalado": alvo.name, "aparelho": serial, "saida": resultado["saida"][:400]}


def _github(metodo: str, caminho: str, corpo: dict[str, Any] | None = None) -> dict[str, Any]:
    token = (os.getenv("JARVIS_GITHUB_TOKEN") or "").strip()
    if not token:
        raise AcoesError(
            "Falta JARVIS_GITHUB_TOKEN no `.env` (fine-grained token com permissão de "
            "Contents e Pull requests no repositório)."
        )
    dados = json.dumps(corpo).encode("utf-8") if corpo is not None else None
    pedido = Request(f"https://api.github.com{caminho}", data=dados, method=metodo)
    pedido.add_header("Authorization", f"Bearer {token}")
    pedido.add_header("Accept", "application/vnd.github+json")
    pedido.add_header("Content-Type", "application/json")
    pedido.add_header("User-Agent", "jarvis-local")
    try:
        with urlopen(pedido, timeout=30) as resposta:  # noqa: S310 - host fixo
            return json.loads(resposta.read().decode("utf-8") or "{}")
    except HTTPError as exc:
        detalhe = ""
        try:
            detalhe = json.loads(exc.read().decode("utf-8")).get("message", "")
        except (ValueError, OSError):
            detalhe = ""
        raise AcoesError(
            f"O GitHub recusou (HTTP {exc.code})" + (f": {detalhe}" if detalhe else ".")
        ) from exc
    except (URLError, OSError) as exc:
        raise AcoesError(f"Não consegui falar com o GitHub ({type(exc).__name__}).") from exc


def publicar_pr(
    *,
    repositorio: str,
    branch: str,
    base: str,
    titulo: str,
    corpo: str,
    arquivos: dict[str, str],
    confirmado: bool = False,
) -> dict[str, Any]:
    """Cria branch, comita os arquivos e abre o PR — com o token do `.env`.

    `arquivos` é `{caminho: conteúdo de texto}`. Nada de binário: binário se
    publica pelo `git`, não por JSON.
    """
    if not re.fullmatch(r"[A-Za-z0-9_.\-]+/[A-Za-z0-9_.\-]+", repositorio or ""):
        raise AcoesError("O repositório vai no formato dono/projeto.")
    for valor, campo in ((branch, "branch"), (base, "base"), (titulo, "titulo")):
        _texto(valor, campo=campo, limite=200)
    if not re.fullmatch(r"[A-Za-z0-9._\-/]{1,120}", branch):
        raise AcoesError("Nome de branch inválido.")
    if not arquivos:
        raise AcoesError("Diga pelo menos um arquivo para publicar.")
    for caminho, conteudo in arquivos.items():
        if ".." in caminho or caminho.startswith("/") or len(conteudo) > 200_000:
            raise AcoesError(f"Arquivo inválido para publicação: {caminho}")

    plano = {
        "executado": False,
        "repositorio": repositorio,
        "branch": branch,
        "base": base,
        "titulo": titulo,
        "arquivos": sorted(arquivos),
    }
    if not confirmado:
        plano["o_que_fazer"] = "Confirme para criar a branch, comitar e abrir o PR de verdade."
        return plano
    exigir_ligado("publicar pull request")

    referencia = _github("GET", f"/repos/{repositorio}/git/ref/heads/{base}")
    sha_base = referencia["object"]["sha"]
    commit_base = _github("GET", f"/repos/{repositorio}/git/commits/{sha_base}")
    tree_base = commit_base["tree"]["sha"]

    entradas = []
    for caminho, conteudo in arquivos.items():
        blob = _github(
            "POST",
            f"/repos/{repositorio}/git/blobs",
            {"content": conteudo, "encoding": "utf-8"},
        )
        entradas.append({"path": caminho, "mode": "100644", "type": "blob", "sha": blob["sha"]})
    arvore = _github(
        "POST",
        f"/repos/{repositorio}/git/trees",
        {"base_tree": tree_base, "tree": entradas},
    )
    commit = _github(
        "POST",
        f"/repos/{repositorio}/git/commits",
        {"message": titulo, "tree": arvore["sha"], "parents": [sha_base]},
    )
    try:
        _github(
            "POST",
            f"/repos/{repositorio}/git/refs",
            {"ref": f"refs/heads/{branch}", "sha": commit["sha"]},
        )
    except AcoesError:
        # A branch já existe: move para o commit novo em vez de falhar.
        _github(
            "PATCH",
            f"/repos/{repositorio}/git/refs/heads/{branch}",
            {"sha": commit["sha"], "force": True},
        )
    pull = _github(
        "POST",
        f"/repos/{repositorio}/pulls",
        {"title": titulo, "head": branch, "base": base, "body": corpo},
    )
    return {
        **plano,
        "executado": True,
        "commit": commit["sha"][:12],
        "numero": pull.get("number"),
        "url": pull.get("html_url", ""),
        "mensagem": f"PR #{pull.get('number')} aberto.",
    }


# ---------------------------------------------------------------------------
# 9. Memória: embedding de verdade (quando há provedor)
# ---------------------------------------------------------------------------

def _vetor(texto: str) -> list[float]:
    """Vetor determinístico local — usado só quando não há provedor.

    Não é embedding de modelo: é um “saco de palavras” com hash, suficiente
    para ordenar por semelhança lexical e **declarado como tal** na resposta.
    """
    dimensoes = 256
    vetor = [0.0] * dimensoes
    for palavra in re.findall(r"[a-z0-9áàâãéêíóôõúç]{2,}", texto.lower()):
        indice = int(hashlib.sha256(palavra.encode("utf-8")).hexdigest()[:8], 16) % dimensoes
        vetor[indice] += 1.0
    norma = math.sqrt(sum(valor * valor for valor in vetor)) or 1.0
    return [valor / norma for valor in vetor]


def embedding(texto: str) -> dict[str, Any]:
    """Vetor do texto: do provedor se houver chave, senão hash local declarado."""
    limpo = (texto or "").strip()
    if not limpo:
        raise AcoesError("Diga o texto para calcular o vetor.")
    if len(limpo) > 8_000:
        raise AcoesError("O texto passa de 8 mil caracteres.")
    chave = (os.getenv("JARVIS_AI_API_KEY") or "").split(",")[0].strip()
    base = (os.getenv("JARVIS_AI_BASE_URL") or "").strip().rstrip("/")
    if chave and base:
        modelo = os.getenv("JARVIS_EMBEDDINGS_MODEL", "text-embedding-3-small")
        pedido = Request(
            f"{base}/embeddings",
            data=json.dumps({"model": modelo, "input": limpo}).encode("utf-8"),
            method="POST",
        )
        pedido.add_header("Authorization", f"Bearer {chave}")
        pedido.add_header("Content-Type", "application/json")
        try:
            with urlopen(pedido, timeout=30) as resposta:  # noqa: S310 - base do .env
                dados = json.loads(resposta.read().decode("utf-8"))
            vetor = dados["data"][0]["embedding"]
            return {"fonte": "provedor", "modelo": modelo, "dimensoes": len(vetor), "vetor": vetor}
        except (HTTPError, URLError, OSError, KeyError, ValueError) as exc:
            # Não inventa: devolve o local e diz por que o provedor não respondeu.
            motivo = f"o provedor não respondeu ({type(exc).__name__})"
    else:
        motivo = "sem provedor configurado"
    vetor = _vetor(limpo)
    return {
        "fonte": "local-hash",
        "modelo": "saco-de-palavras (256 dimensões)",
        "motivo": motivo,
        "dimensoes": len(vetor),
        "vetor": vetor,
    }


def similaridade(a: str, b: str) -> dict[str, Any]:
    """Cosseno entre dois textos — com o mesmo caminho do `embedding`."""
    primeiro = embedding(a)
    segundo = embedding(b)
    if primeiro["fonte"] != segundo["fonte"]:
        raise AcoesError("Os dois vetores vieram de fontes diferentes; não comparo.")
    va, vb = primeiro["vetor"], segundo["vetor"]
    if len(va) != len(vb):
        raise AcoesError("Vetores de tamanhos diferentes.")
    produto = sum(x * y for x, y in zip(va, vb))
    na = math.sqrt(sum(x * x for x in va)) or 1.0
    nb = math.sqrt(sum(y * y for y in vb)) or 1.0
    return {
        "fonte": primeiro["fonte"],
        "cosseno": round(produto / (na * nb), 4),
        "dimensoes": len(va),
    }


# ---------------------------------------------------------------------------
# 10. Agência: executar o agente de verdade
# ---------------------------------------------------------------------------

async def executar_agente(
    *,
    pedido: str,
    registry: Any,
    autorizar: bool = False,
    limite_passos: int = 6,
) -> dict[str, Any]:
    """Planeja com o maestro e **executa** os passos, com travas.

    Para onde deve parar: passo com efeito sem autorização, passo sem dado,
    passo que falha. E no máximo `limite_passos` — agente sem teto é laço.
    """
    from . import maestro

    texto = (pedido or "").strip()
    if not texto:
        raise AcoesError("Diga o que o agente deve fazer.")
    plano = maestro.planejar(texto, registry=registry)
    if not plano.get("passos"):
        raise AcoesError(
            "Não achei procedimento para esse pedido. O maestro trabalha com rotinas "
            "declaradas (conserto, limpeza, análise) — descreva o objetivo com essas palavras."
        )
    if len(plano["passos"]) > limite_passos:
        raise AcoesError(
            f"O plano tem {len(plano['passos'])} passos; o teto por execução é {limite_passos}."
        )
    if autorizar:
        exigir_ligado("executar agente")
    resultado = await maestro.executar(plano, registry=registry, autorizar=autorizar)
    return {
        "executado": bool(resultado.get("completo")),
        "plano": plano,
        "resultado": resultado,
        "texto": maestro.texto_da_execucao(resultado),
    }


# ---------------------------------------------------------------------------
# 6. Estúdio: compilar tokens e montar a prévia
# ---------------------------------------------------------------------------

def _escrita_segura(raiz: Path | None, nome: str, padrao: str, extensao: str) -> Path:
    if raiz is None:
        raise AcoesError("Para gravar o arquivo, informe a área de arquivos do JARVIS.")
    base = (nome or "").strip() or padrao
    if not ARQUIVO_SEGURO.match(base):
        base = padrao
    if not base.lower().endswith(extensao):
        base = f"{Path(base).stem or Path(padrao).stem}{extensao}"
    destino = (raiz / base).resolve()
    if raiz.resolve() not in destino.parents:
        raise AcoesError("A saída precisa ficar dentro da área do JARVIS.")
    return destino


def estudio_tokens(
    texto: str,
    *,
    confirmado: bool = False,
    raiz: Path | None = None,
    nome: str = "tokens.css",
) -> dict[str, Any]:
    """Compila a sua tabela de tokens no `tokens.css` do contrato fechado.

    O esquema tem 56 slots (`studio.SCHEMA_TOKENS`). O que você não declarou fica
    faltando — não vira valor inventado.
    """
    from .studio import compilar_tokens  # import tardio: o módulo é grande

    try:
        resultado = compilar_tokens(texto)
    except ValueError as exc:  # StudioError é ValueError
        raise AcoesError(str(exc)) from exc
    plano = {
        "executado": False,
        **{chave: valor for chave, valor in resultado.items() if chave != "css"},
        "css": resultado["css"][:4_000],
        "bytes": len(resultado["css"].encode("utf-8")),
    }
    if not confirmado:
        plano["o_que_fazer"] = "Confirme para gravar o tokens.css na área do JARVIS."
        return plano
    exigir_ligado("compilar tokens")
    destino = _escrita_segura(raiz, nome, "tokens.css", ".css")
    destino.write_text(resultado["css"], encoding="utf-8")
    return {**plano, "executado": True, "saida": destino.name, "bytes": destino.stat().st_size}


def estudio_previa(
    *,
    tokens: str = "",
    css: str = "",
    titulo: str = "",
    confirmado: bool = False,
    raiz: Path | None = None,
    nome: str = "previa.html",
) -> dict[str, Any]:
    """Monta o HTML de arquivo único com os tokens aplicados.

    Quem desenha é o navegador. Não há rasterização, captura de tela nem publicação
    — o arquivo é gravado e você abre.
    """
    from .studio import compilar_tokens, montar_previa

    if not (tokens or "").strip() and not (css or "").strip():
        raise AcoesError("Informe a tabela de tokens ou um `tokens.css` já compilado.")
    if (tokens or "").strip():
        try:
            css = compilar_tokens(tokens)["css"]
        except ValueError as exc:
            raise AcoesError(str(exc)) from exc
    try:
        pagina = montar_previa(css=css, titulo=titulo or "Prévia do design system")
    except ValueError as exc:
        raise AcoesError(str(exc)) from exc
    plano = {
        "executado": False,
        "caracteres": pagina["caracteres"],
        "nota": pagina["nota"],
        "html": pagina["html"][:2_000] + ("…" if pagina["caracteres"] > 2_000 else ""),
    }
    if not confirmado:
        plano["o_que_fazer"] = "Confirme para gravar a prévia .html na área do JARVIS."
        return plano
    exigir_ligado("montar a prévia do estúdio")
    destino = _escrita_segura(raiz, nome, "previa.html", ".html")
    destino.write_text(pagina["html"], encoding="utf-8")
    return {
        **plano,
        "executado": True,
        "saida": destino.name,
        "bytes": destino.stat().st_size,
        "como_abrir": f"Abra {destino.name} na pasta de arquivos do JARVIS — o navegador desenha.",
    }


# ---------------------------------------------------------------------------
# 7. Carreira: a candidatura sai de verdade
# ---------------------------------------------------------------------------

def carreira_candidatar(
    *,
    vaga: str,
    curriculo: str,
    destino: str,
    cv: str = "",
    perfil: str = "",
    pesquisa: str = "",
    assunto: str = "",
    confirmado: bool = False,
    raiz: Path | None = None,
) -> dict[str, Any]:
    """Monta a carta com `career.draft_letter` e envia por e-mail com o CV anexo.

    A carta só sai se o próprio módulo disser que está pronta (`pronto: true`):
    carta com placeholder ou com número sem fonte não vira candidatura.
    """
    from .career import draft_letter  # import tardio

    if not EMAIL.match((destino or "").strip()):
        raise AcoesError("Informe o e-mail de destino da candidatura.")
    pedido: dict[str, Any] = {"vaga": vaga, "curriculo": curriculo}
    if perfil.strip():
        pedido["perfil"] = perfil
    if pesquisa.strip():
        pedido["pesquisa"] = pesquisa
    try:
        carta = draft_letter(pedido)
    except ValueError as exc:
        raise AcoesError(str(exc)) from exc
    metrics = carta.get("metrics") or {}
    if not metrics.get("pronto"):
        bloqueios = [
            item.get("detalhe") or item.get("codigo")
            for item in metrics.get("checagens") or []
            if not item.get("ok")
        ]
        raise AcoesError(
            "A carta ainda não está pronta para enviar"
            + (f": {'; '.join(str(item) for item in bloqueios[:4])}" if bloqueios else ".")
            + " Peça a carta completa em `carreira.carta` antes de candidatar."
        )
    corpo = str(metrics.get("rascunho") or "").strip()
    if not corpo:
        raise AcoesError("A carta saiu vazia — nada seria enviado.")
    anexos = [cv] if (cv or "").strip() else []
    envio = enviar_email(
        para=[destino.strip()],
        assunto=(assunto or "").strip() or "Candidatura",
        corpo=corpo,
        anexos=anexos,
        raiz=raiz,
        confirmado=confirmado,
    )
    return {
        **envio,
        "carta": {"caracteres": metrics.get("caracteres"), "pronto": True},
        "anexos": envio.get("anexos", []),
            "aviso": (
            "Quem aperta o botão de enviar é você: esta ação só faz sentido quando o "
            "anúncio traz um e-mail. Formulário web e ATS continuam sendo preenchidos à mão."
        ),
    }
