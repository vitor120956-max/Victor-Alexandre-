"""Repositórios do GitHub: baixar, guardar, ler e rodar — sem Git instalado.

O pedido que originou esta camada foi curto: "copiar um repositório e usar".
Copiar é fácil; o risco está no resto. Então o desenho separa as três coisas:

- **baixar** — só GitHub público, só `.zip` do `codeload`, com teto de 64 MB,
  4.000 arquivos e 200 MB extraídos; a extração recusa caminho absoluto, `..`,
  drive (`C:`), link simbólico e arquivo acima de 20 MB;
- **entender** — depois de extrair, o repositório é descrito: linguagens,
  dependências, entradas prováveis (`python -m pacote`, `npm run dev`), README e
  se ele traz um `SKILL.md` no padrão Agent Skills;
- **executar** — só com autorização explícita, só um dos interpretadores da
  lista fechada (`python`, `node`, `npm`, `npx`, `make`), sem shell, com o
  diretório de trabalho preso à pasta do repositório, tempo limite e saída
  cortada. O ambiente do processo é limpo de qualquer variável com TOKEN,
  SECRET, KEY, PASS ou JARVIS_.

O que esta camada **não** faz: clonar com Git (a máquina não tem Git), resolver
dependência do repositório por conta própria, instalar pacote, mexer em
repositório privado nem prometer que o projeto roda — ela diz o comando e as
dependências que faltam, e quem decide é você.
"""
from __future__ import annotations

import io
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import unicodedata
import zipfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Callable, Iterable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from . import dados

PROJETO = Path(__file__).resolve().parent.parent
STORAGE = dados.raiz()
# Os repositórios podem morar numa pasta do Drive (`JARVIS_REPOS`).
PASTA_REPOS = dados.repositorios()
INDICE = PASTA_REPOS / "indice.json"

MAX_ZIP = 64 * 1024 * 1024
MAX_ARQUIVOS = 4_000
MAX_EXTRAIDO = 200 * 1024 * 1024
MAX_ARQUIVO = 20 * 1024 * 1024
MAX_TEXTO = 120_000
MAX_ARVORE = 60
MAX_SAIDA = 4_000
TIMEOUT_BAIXAR = 60
TIMEOUT_EXECUTAR = 120
AGENTE = "jarvis-repos/0.41 (+local)"

HOSTS = ("github.com", "www.github.com")
INTERPRETADORES = ("python", "python3", "py", "node", "npm", "npx", "make")
PROIBIDOS_NO_COMANDO = (";", "|", "&", ">", "<", "`", "$(", "\n", "\r")

LINGUAGENS = {
    ".py": "Python", ".js": "JavaScript", ".mjs": "JavaScript", ".cjs": "JavaScript",
    ".jsx": "JavaScript", ".ts": "TypeScript", ".tsx": "TypeScript", ".md": "Markdown",
    ".json": "JSON", ".yml": "YAML", ".yaml": "YAML", ".toml": "TOML", ".sh": "Shell",
    ".ps1": "PowerShell", ".bat": "Batch", ".html": "HTML", ".css": "CSS", ".scss": "CSS",
    ".rs": "Rust", ".go": "Go", ".java": "Java", ".c": "C", ".h": "C", ".cpp": "C++",
    ".hpp": "C++", ".rb": "Ruby", ".php": "PHP", ".ipynb": "Notebook", ".sql": "SQL",
    ".txt": "Texto", ".rst": "Texto", ".xml": "XML", ".svg": "SVG",
}

_RX_DONO = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,99}$")

# Empate no contador é comum em repositório pequeno (1 README, 1 .py). A ordem
# abaixo faz o código aparecer antes de documento e configuração.
PESO_LINGUAGEM = {
    "Python": 0, "JavaScript": 0, "TypeScript": 0, "Rust": 0, "Go": 0, "Java": 0,
    "C": 0, "C++": 0, "Ruby": 0, "PHP": 0, "Shell": 0, "PowerShell": 0, "Batch": 0,
    "SQL": 0, "HTML": 1, "CSS": 1, "Notebook": 1, "JSON": 2, "YAML": 2, "TOML": 2,
    "XML": 2, "SVG": 3, "Markdown": 3, "Texto": 3, "Outros": 4,
}


class ReposError(ValueError):
    """Pedido de repositório que não dá para atender com segurança."""


# ------------------------------------------------------------------ utilidades

def normalizar(texto: str) -> str:
    """Minúsculas, sem acento e com espaço simples."""
    baixo = unicodedata.normalize("NFKD", (texto or "").lower())
    sem_acento = "".join(letra for letra in baixo if not unicodedata.combining(letra))
    return re.sub(r"\s+", " ", sem_acento).strip()


def _agora() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def exigir_autorizacao(autorizacao: str, verbo: str = "baixar") -> None:
    """Aceita só autorização dita na frase — igual às camadas de host."""
    texto = normalizar(autorizacao)
    raizes = ("sim", "autoriz", "pode", "confirm", "baix", "copi", "import", "execut", "rod")
    if not texto or not any(raiz in texto for raiz in raizes):
        raise ReposError(
            f"Para {verbo} preciso da sua autorização escrita. "
            f'Responda algo como "sim, pode {verbo}" e o pedido segue.'
        )


# ------------------------------------------------------------------ endereço

def parse_url(texto: str) -> tuple[str, str, str | None]:
    """Aceita as formas comuns e devolve `(dono, repositório, ref)`.

    Vale `https://github.com/dono/repo`, `dono/repo`, `git@github.com:dono/repo.git`
    e `.../tree/<ref>`. Qualquer outro host é recusado — não é bloqueio de
    segurança, é o único que a camada sabe baixar.
    """
    bruto = (texto or "").strip().strip("<>").strip()
    if not bruto:
        raise ReposError("Diga o repositório: `dono/repo` ou o endereço do GitHub.")

    ref: str | None = None
    if bruto.startswith("git@github.com:"):
        bruto = bruto.split(":", 1)[1]
    elif "://" in bruto:
        resto = bruto.split("://", 1)[1]
        host, _, caminho = resto.partition("/")
        host = host.split("@")[-1].split(":")[0].lower()
        if host not in HOSTS:
            raise ReposError("Só repositório público do GitHub: o endereço precisa ser github.com.")
        bruto = caminho
    elif bruto.lower().startswith(("github.com/", "www.github.com/")):
        bruto = bruto.split("/", 1)[1]

    bruto = bruto.split("?", 1)[0].split("#", 1)[0].strip().rstrip("/")
    if bruto.endswith(".git"):
        bruto = bruto[:-4]
    partes = [parte for parte in bruto.split("/") if parte]
    if len(partes) < 2:
        raise ReposError("O endereço precisa ter dono e repositório, como `virgiliojr94/book-to-skill`.")
    dono, nome = partes[0], partes[1]
    if not _RX_DONO.match(dono) or not _RX_DONO.match(nome):
        raise ReposError("Dono ou nome do repositório com caractere inválido.")
    if ".." in (dono, nome) or dono.startswith(".") or nome.startswith("."):
        raise ReposError("Dono ou nome do repositório não pode começar com ponto.")
    if len(partes) >= 4 and partes[2] == "tree":
        ref = "/".join(partes[3:])
    return dono, nome, ref


def slug_de(dono: str, nome: str) -> str:
    base = normalizar(f"{dono}--{nome}")
    return re.sub(r"[^a-z0-9._-]+", "-", base).strip("-.")[:80] or "repositorio"


# ------------------------------------------------------------------- download

def _baixar_bytes(url: str, limite: int = MAX_ZIP, timeout: int = TIMEOUT_BAIXAR) -> bytes:
    pedido = Request(url, headers={"User-Agent": AGENTE, "Accept": "application/zip"})
    try:
        with urlopen(pedido, timeout=timeout) as resposta:
            tamanho = resposta.headers.get("Content-Length")
            if tamanho and int(tamanho) > limite:
                raise ReposError(f"O arquivo passa de {limite // (1024 * 1024)} MB e não foi baixado.")
            pedacos: list[bytes] = []
            total = 0
            while True:
                pedaco = resposta.read(256 * 1024)
                if not pedaco:
                    break
                total += len(pedaco)
                if total > limite:
                    raise ReposError(f"O download passou de {limite // (1024 * 1024)} MB e foi interrompido.")
                pedacos.append(pedaco)
            return b"".join(pedacos)
    except HTTPError as exc:
        if exc.code == 404:
            raise ReposError("Repositório não encontrado (ou privado). Confira dono e nome.") from exc
        raise ReposError(f"O GitHub respondeu {exc.code}.") from exc
    except URLError as exc:
        raise ReposError("Sem acesso ao GitHub: verifique a internet e a rede liberada.") from exc


def _extrair(zip_bytes: bytes, destino: Path) -> dict[str, Any]:
    """Extrai com freio: sem `..`, sem caminho absoluto, sem link simbólico."""
    try:
        arquivo = zipfile.ZipFile(io.BytesIO(zip_bytes))
    except zipfile.BadZipFile as exc:
        raise ReposError("O que veio do GitHub não é um .zip válido.") from exc

    with arquivo:
        infos = [info for info in arquivo.infolist() if not info.is_dir()]
        if not infos:
            raise ReposError("O repositório veio vazio.")
        if len(infos) > MAX_ARQUIVOS:
            raise ReposError(f"O repositório tem {len(infos)} arquivos, acima do teto de {MAX_ARQUIVOS}.")

        total = 0
        for info in infos:
            nome = info.filename.replace("\\", "/")
            partes = PurePosixPath(nome).parts
            if nome.startswith("/") or ".." in partes or (partes and ":" in partes[0]):
                raise ReposError(f"Caminho recusado no pacote: {nome}")
            modo = (info.external_attr >> 16) & 0o170000
            if modo == 0o120000:
                raise ReposError(f"O pacote traz link simbólico ({nome}); não é extraído.")
            if info.file_size > MAX_ARQUIVO:
                raise ReposError(f"Arquivo grande demais dentro do pacote: {nome}")
            total += info.file_size
            if total > MAX_EXTRAIDO:
                raise ReposError("O conteúdo extraído passa de 200 MB; download recusado.")

        raizes = {info.filename.replace("\\", "/").split("/")[0] for info in infos}
        cortar = len(raizes) == 1 and all("/" in info.filename.replace("\\", "/") for info in infos)

        destino.mkdir(parents=True, exist_ok=True)
        escritos = 0
        for info in infos:
            nome = info.filename.replace("\\", "/")
            if cortar:
                nome = nome.split("/", 1)[1]
            if not nome:
                continue
            alvo = (destino / nome).resolve()
            if destino.resolve() not in alvo.parents and alvo != destino.resolve():
                raise ReposError(f"Caminho escaparia da pasta do repositório: {nome}")
            alvo.parent.mkdir(parents=True, exist_ok=True)
            with arquivo.open(info) as origem, alvo.open("wb") as saida:
                shutil.copyfileobj(origem, saida)
            escritos += 1
        return {"arquivos": escritos, "bytes": total}


# -------------------------------------------------------------------- análise

def _ler_texto(caminho: Path, limite: int = 40_000) -> str:
    try:
        with caminho.open("rb") as fonte:
            bruto = fonte.read(limite)
    except OSError:
        return ""
    if b"\x00" in bruto[:4096]:
        return ""
    return bruto.decode("utf-8", errors="replace")


def _achar_readme(pasta: Path) -> Path | None:
    candidatos = sorted(
        item for item in pasta.iterdir()
        if item.is_file() and item.name.lower().startswith("readme")
    )
    return candidatos[0] if candidatos else None


def _resumo_readme(texto: str, limite: int = 700) -> tuple[str, str]:
    titulo = ""
    linhas: list[str] = []
    for linha in texto.splitlines():
        limpa = linha.strip()
        if not titulo and limpa.startswith("#"):
            titulo = limpa.lstrip("#").strip()
            continue
        if not titulo and "<h1" in limpa.lower():
            achado = re.search(r"<h1[^>]*>(.*?)</h1>", limpa, re.I | re.S)
            if achado:
                titulo = re.sub(r"<[^>]+>", "", achado.group(1)).strip()
        if not limpa or limpa.startswith(("![", "[![", "<img", "<p align", "---", "|")):
            continue
        linhas.append(limpa)
        if len(" ".join(linhas)) > limite:
            break
    resumo = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", " ".join(linhas))
    resumo = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", resumo)
    resumo = re.sub(r"<[^>]+>", "", resumo)
    resumo = re.sub(r"[`*_>#]", "", resumo)
    return titulo, re.sub(r"\s+", " ", resumo).strip()[:limite]


def _dependencias(pasta: Path) -> list[dict[str, Any]]:
    achados: list[dict[str, Any]] = []

    req = pasta / "requirements.txt"
    if req.is_file():
        itens = [
            linha.split("#", 1)[0].strip()
            for linha in _ler_texto(req).splitlines()
            if linha.strip() and not linha.strip().startswith("#")
        ]
        achados.append({"arquivo": "requirements.txt", "itens": itens[:40]})

    pyproject = pasta / "pyproject.toml"
    if pyproject.is_file():
        texto = _ler_texto(pyproject)
        bloco = re.search(r"dependencies\s*=\s*\[(.*?)\]", texto, re.S)
        itens = re.findall(r"[\"']([^\"']+)[\"']", bloco.group(1)) if bloco else []
        nomes = re.findall(r"^([A-Za-z0-9_.\-]+)\s*(?:[<>=!~]|$)", "\n".join(itens), re.M)
        achados.append({"arquivo": "pyproject.toml", "itens": (nomes or itens)[:40]})

    pacote = pasta / "package.json"
    if pacote.is_file():
        try:
            dados = json.loads(_ler_texto(pacote) or "{}")
        except json.JSONDecodeError:
            dados = {}
        itens = sorted({**dados.get("dependencies", {}), **dados.get("devDependencies", {})})
        achados.append({"arquivo": "package.json", "itens": itens[:40]})

    for nome in ("go.mod", "Cargo.toml", "Gemfile", "composer.json"):
        if (pasta / nome).is_file():
            achados.append({"arquivo": nome, "itens": []})
    return [item for item in achados if item["itens"] or item["arquivo"] in {"go.mod", "Cargo.toml"}]


def _scripts_package(pasta: Path) -> list[str]:
    pacote = pasta / "package.json"
    if not pacote.is_file():
        return []
    try:
        dados = json.loads(_ler_texto(pacote) or "{}")
    except json.JSONDecodeError:
        return []
    scripts = dados.get("scripts") or {}
    return [nome for nome in ("start", "dev", "build", "test") if nome in scripts][:4]


def _entradas(pasta: Path) -> list[dict[str, str]]:
    entradas: list[dict[str, str]] = []

    pyproject = pasta / "pyproject.toml"
    if pyproject.is_file():
        texto = _ler_texto(pyproject)
        bloco = re.search(r"\[project\.scripts\](.*?)(?:\n\[|\Z)", texto, re.S)
        if bloco:
            for nome, alvo in re.findall(r"^([A-Za-z0-9_.\-]+)\s*=\s*[\"']([^\"']+)[\"']", bloco.group(1), re.M):
                entradas.append({"comando": nome, "porque": f"script do pyproject → {alvo}"})
    if (pasta / "pyproject.toml").is_file() or (pasta / "setup.py").is_file():
        entradas.append({"comando": "pip install -e .", "porque": "instala o projeto em modo editável"})

    for nome in sorted(pasta.glob("*/__main__.py")):
        modulo = nome.parent.name
        entradas.append({"comando": f"python -m {modulo}", "porque": f"pacote {modulo} tem __main__.py"})
    for nome in ("main.py", "app.py", "cli.py", "run.py"):
        if (pasta / nome).is_file():
            entradas.append({"comando": f"python {nome}", "porque": f"{nome} na raiz"})

    scripts = _scripts_package(pasta)
    if scripts:
        for script in scripts:
            entradas.append({"comando": f"npm run {script}", "porque": f"script '{script}' do package.json"})
    if (pasta / "Makefile").is_file():
        alvos = re.findall(r"^([A-Za-z0-9_][A-Za-z0-9_.-]*)\s*:(?!=)", _ler_texto(pasta / "Makefile"), re.M)
        for alvo in [item for item in alvos if item not in {"all", ".PHONY"}][:3]:
            entradas.append({"comando": f"make {alvo}", "porque": f"alvo '{alvo}' do Makefile"})

    vistos: set[str] = set()
    unicas: list[dict[str, str]] = []
    for entrada in entradas:
        if entrada["comando"] in vistos:
            continue
        vistos.add(entrada["comando"])
        unicas.append(entrada)
    return unicas[:8]


def analisar(pasta: Path, limite_arvore: int = MAX_ARVORE) -> dict[str, Any]:
    """Descreve o que foi baixado: linguagem, dependência, entrada e README."""
    if not pasta.is_dir():
        raise ReposError("Repositório não encontrado na pasta local.")

    arquivos = 0
    total = 0
    contagem: Counter[str] = Counter()
    arvore: list[str] = []
    for item in sorted(pasta.rglob("*")):
        if not item.is_file() or ".git" in item.parts:
            continue
        arquivos += 1
        try:
            total += item.stat().st_size
        except OSError:
            pass
        contagem[LINGUAGENS.get(item.suffix.lower(), "Outros")] += 1
        if len(arvore) < limite_arvore:
            arvore.append(str(item.relative_to(pasta)).replace("\\", "/"))

    readme = _achar_readme(pasta)
    titulo, resumo = ("", "")
    if readme is not None:
        titulo, resumo = _resumo_readme(_ler_texto(readme))

    skills = [str(item.relative_to(pasta)).replace("\\", "/") for item in pasta.rglob("SKILL.md")][:3]

    return {
        "arquivos": arquivos,
        "bytes": total,
        "linguagens": [
            {"nome": nome, "arquivos": quantos}
            for nome, quantos in sorted(
                contagem.items(), key=lambda par: (-par[1], PESO_LINGUAGEM.get(par[0], 5))
            )[:6]
        ],
        "readme": {"arquivo": readme.name if readme else None, "titulo": titulo, "resumo": resumo},
        "dependencias": _dependencias(pasta),
        "entradas": _entradas(pasta),
        "tem_skill": bool(skills),
        "skills": skills,
        "arvore": arvore,
    }


# --------------------------------------------------------------------- índice

def _ler_indice() -> list[dict[str, Any]]:
    try:
        dados = json.loads(INDICE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    return [item for item in dados if isinstance(item, dict)] if isinstance(dados, list) else []


def _gravar_indice(repos: Iterable[dict[str, Any]]) -> None:
    PASTA_REPOS.mkdir(parents=True, exist_ok=True)
    texto = json.dumps(list(repos), ensure_ascii=False, indent=2)
    temporario = INDICE.with_suffix(".tmp")
    temporario.write_text(texto, encoding="utf-8")
    temporario.replace(INDICE)


def listar() -> list[dict[str, Any]]:
    return _ler_indice()


def obter(slug: str) -> dict[str, Any]:
    for item in _ler_indice():
        if item.get("slug") == slug:
            return item
    raise ReposError("Repositório não está na pasta local. Baixe primeiro.")


def baixar_repo(
    url: str,
    *,
    autorizacao: str = "",
    ref: str | None = None,
    baixar: Callable[..., bytes] | None = None,
) -> dict[str, Any]:
    """Baixa, extrai, analisa e registra. Sem Git, sem shell, sem instalar nada."""
    exigir_autorizacao(autorizacao, "baixar")
    dono, nome, ref_url = parse_url(url)
    referencia = ref or ref_url
    sufixo = f"/refs/heads/{referencia}" if referencia else ""
    endereco = f"https://codeload.github.com/{dono}/{nome}/zip{sufixo}" if sufixo else (
        f"https://codeload.github.com/{dono}/{nome}/zip/refs/heads/master"
    )
    buscar = baixar or _baixar_bytes

    try:
        pacote = buscar(endereco)
    except ReposError:
        raise
    except Exception as exc:  # dublê de teste pode levantar qualquer coisa
        raise ReposError(f"Falha ao baixar: {type(exc).__name__}") from exc

    slug = slug_de(dono, nome)
    final = PASTA_REPOS / slug
    temporaria = PASTA_REPOS / f".novo-{slug}"
    antiga = PASTA_REPOS / f".velho-{slug}"
    if temporaria.exists():
        shutil.rmtree(temporaria, ignore_errors=True)

    try:
        info = _extrair(pacote, temporaria)
    except ReposError:
        shutil.rmtree(temporaria, ignore_errors=True)
        raise

    meta = analisar(temporaria)
    if final.exists():
        shutil.rmtree(antiga, ignore_errors=True)
        final.replace(antiga)
    temporaria.replace(final)
    shutil.rmtree(antiga, ignore_errors=True)

    registro = {
        "slug": slug,
        "dono": dono,
        "nome": nome,
        "url": f"https://github.com/{dono}/{nome}",
        "ref": referencia or "padrão",
        "baixado_em": _agora(),
        "pasta": str(final),
        "zip_bytes": len(pacote),
        **info,
        **meta,
    }
    outros = [item for item in _ler_indice() if item.get("slug") != slug]
    _gravar_indice([registro, *outros][:50])
    return {**registro, "sugestao": sugestao_de_uso(registro)}


def sugestao_de_uso(meta: dict[str, Any]) -> str:
    """Texto curto com o que dá para tentar — e o que vai faltar."""
    linhas: list[str] = []
    linguagens = [item["nome"] for item in meta.get("linguagens", []) if item["nome"] != "Outros"]
    if linguagens:
        linhas.append(f"Linguagem principal: {', '.join(linguagens[:3])}.")
    if meta.get("readme", {}).get("titulo"):
        linhas.append(f"README: “{meta['readme']['titulo']}”.")
    entradas = meta.get("entradas") or []
    if entradas:
        linhas.append("Entradas prováveis: " + "; ".join(item["comando"] for item in entradas[:3]) + ".")
    else:
        linhas.append("Não achei entrada declarada (pyproject, package.json, Makefile ou main.py).")
    deps = [item for item in meta.get("dependencias", []) if item.get("itens")]
    if deps:
        nomes = ", ".join(item["itens"][0] for item in deps if item["itens"])[:120]
        linhas.append(f"Dependências declaradas em {', '.join(item['arquivo'] for item in deps)}: {nomes}…")
    if meta.get("tem_skill"):
        linhas.append(f"Traz skill no padrão Agent Skills: {meta['skills'][0]}.")
    linhas.append("Nada foi instalado nem executado. Para rodar algo, peça com autorização explícita.")
    return " ".join(linhas)


def ler_arquivo(slug: str, caminho: str, limite: int = MAX_TEXTO) -> dict[str, Any]:
    """Lê um arquivo de texto de dentro do repositório baixado."""
    registro = obter(slug)
    raiz = (PASTA_REPOS / slug).resolve()
    alvo = (raiz / caminho).resolve()
    if alvo != raiz and raiz not in alvo.parents:
        raise ReposError("Caminho fora da pasta do repositório.")
    if not alvo.is_file():
        raise ReposError("Arquivo não existe nesse repositório.")
    texto = _ler_texto(alvo, limite)
    if not texto:
        raise ReposError("Arquivo binário ou ilegível; não é mostrado.")
    return {
        "slug": slug,
        "caminho": str(alvo.relative_to(raiz)).replace("\\", "/"),
        "tamanho": alvo.stat().st_size,
        "conteudo": texto[:limite],
        "truncado": len(texto) >= limite,
    }


def _ambiente_limpo() -> dict[str, str]:
    return {
        chave: valor for chave, valor in os.environ.items()
        if not re.search(r"TOKEN|SECRET|PASS|KEY|JARVIS_", chave.upper())
    }


def _resolver_executavel(nome: str) -> str | None:
    baixo = nome.lower()
    if baixo in {"python", "python3", "py"}:
        return sys.executable or shutil.which("python")
    achado = shutil.which(baixo)
    if achado:
        return achado
    if os.name == "nt":
        return shutil.which(f"{baixo}.cmd") or shutil.which(f"{baixo}.exe")
    return None


def executar_no_repo(
    slug: str,
    comando: str,
    *,
    autorizacao: str = "",
    timeout: int = TIMEOUT_EXECUTAR,
) -> dict[str, Any]:
    """Roda um comando do repositório: lista fechada, sem shell, com limite."""
    exigir_autorizacao(autorizacao, "executar")
    registro = obter(slug)
    pasta = (PASTA_REPOS / slug).resolve()
    if not pasta.is_dir():
        raise ReposError("A pasta do repositório não existe mais; baixe de novo.")

    linha = (comando or "").strip()
    if not linha:
        raise ReposError("Diga o comando, por exemplo `python -m pacote --help`.")
    for proibido in PROIBIDOS_NO_COMANDO:
        if proibido in linha:
            raise ReposError("O comando tem caractere de shell; aqui não existe shell livre.")
    try:
        partes = shlex.split(linha, posix=True)
    except ValueError as exc:
        raise ReposError("Não consegui ler o comando (aspas fechadas?).") from exc

    primeiro = partes[0].lower()
    if primeiro not in INTERPRETADORES:
        raise ReposError(
            "Só posso rodar com " + ", ".join(INTERPRETADORES) + f". Você pediu `{partes[0]}`."
        )
    executavel = _resolver_executavel(partes[0])
    if executavel is None:
        raise ReposError(f"`{partes[0]}` não está instalado nesta máquina.")
    argv = [executavel, *partes[1:]]

    try:
        processo = subprocess.run(
            argv,
            cwd=str(pasta),
            capture_output=True,
            text=True,
            timeout=max(5, min(timeout, 600)),
            env=_ambiente_limpo(),
            shell=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise ReposError(f"O comando passou de {timeout}s e foi interrompido.") from exc
    except OSError as exc:
        raise ReposError(f"Não consegui iniciar o comando: {type(exc).__name__}") from exc

    saida = (processo.stdout or "")[-MAX_SAIDA:]
    erro = (processo.stderr or "")[-MAX_SAIDA // 2:]
    return {
        "slug": slug,
        "repositorio": registro.get("nome"),
        "comando": linha,
        "codigo": processo.returncode,
        "saida": saida.strip(),
        "erro": erro.strip(),
        "ok": processo.returncode == 0,
    }


def remover_repo(slug: str) -> bool:
    """Apaga a pasta baixada e tira do índice. Nada fora de `storage/repos`."""
    registros = _ler_indice()
    alvo = next((item for item in registros if item.get("slug") == slug), None)
    if alvo is None:
        return False
    pasta = (PASTA_REPOS / slug).resolve()
    raiz = PASTA_REPOS.resolve()
    if pasta != raiz and raiz in pasta.parents and pasta.exists():
        shutil.rmtree(pasta, ignore_errors=True)
    _gravar_indice([item for item in registros if item.get("slug") != slug])
    return True
