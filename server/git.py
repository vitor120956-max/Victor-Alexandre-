"""Git só de leitura: ver o que mudou, sem tocar no repositório.

A pergunta foi “dá para ele usar o git?”. Dá — mas **ler**, não escrever. Esta
camada roda apenas quatro consultas, cada uma com os argumentos fixos no código:

| Skill | Comando | Para quê |
|---|---|---|
| `git.status` | `git status --porcelain=v1 -b` | branch, à frente/atrás, o que mudou |
| `git.log` | `git log -n N --pretty=…` | últimos commits, com hash e data |
| `git.diff` | `git diff` / `git diff --staged` | o que mudou, com teto de texto |
| `git.remoto` | `git remote -v` + upstream | de onde vem e para onde vai |

O que esta camada **não** aceita, por desenho: `commit`, `push`, `pull`, `clone`,
`checkout`, `reset`, `clean`, `merge`, `rebase` — nem como texto livre. Não existe
campo para argumento: o usuário escolhe a consulta, não a linha de comando.

O repositório precisa estar dentro de um lugar conhecido: a pasta do projeto, a
raiz de dados ou `storage/repos`. Fora disso, recusa — para não virar um executor
de Git em qualquer pasta da máquina.

Tudo roda com `shell=False`, `GIT_TERMINAL_PROMPT=0` (nunca pede senha) e teto de
20 segundos.
"""
from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path
from typing import Any, Sequence

from . import dados as dados_locais

VERSAO = "0.61.8"

PROJETO = Path(__file__).resolve().parent.parent
TIMEOUT = 20
MAX_TEXTO = 20_000
MAX_LINHAS = 200

REF_SEGURA = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_./~^-]{0,79}$")


class GitError(Exception):
    """Recusa do leitor de Git: nada foi executado."""


def _raizes(raizes: Sequence[Path] | None) -> list[Path]:
    if raizes is not None:
        return [Path(item).resolve() for item in raizes]
    try:
        dados = Path(dados_locais.raiz()).resolve()
    except OSError:
        dados = PROJETO
    return [PROJETO.resolve(), dados]


def repositorio(caminho: str = "", raizes: Sequence[Path] | None = None) -> Path:
    """Acha a raiz do repositório e confere se ela está num lugar permitido."""
    bruto = (caminho or "").strip()
    alvo = Path(bruto).expanduser() if bruto else PROJETO
    try:
        alvo = alvo.resolve()
    except OSError as exc:
        raise GitError("Caminho inválido.") from exc
    if not alvo.exists():
        raise GitError(f"A pasta não existe: {alvo}")
    if not alvo.is_dir():
        raise GitError(f"Isso é um arquivo, não uma pasta: {alvo}")
    if not (alvo / ".git").exists():
        raise GitError(
            f"{alvo} não é um repositório Git (não tem .git). "
            "Aponte para a pasta do JARVIS, para a raiz de dados ou para storage/repos."
        )
    permitidas = _raizes(raizes)
    if not any(alvo == raiz or raiz in alvo.parents for raiz in permitidas):
        nomes = ", ".join(str(raiz) for raiz in permitidas)
        raise GitError(f"Repositório fora dos lugares permitidos ({nomes}).")
    return alvo


def _rodar(repo: Path, args: list[str]) -> str:
    try:
        resultado = subprocess.run(
            ["git", "-C", str(repo), *args],
            capture_output=True,
            text=True,
            timeout=TIMEOUT,
            shell=False,
            env={
                **os.environ,
                "GIT_TERMINAL_PROMPT": "0",
                "GIT_PAGER": "cat",
                "LC_ALL": "C.UTF-8",
            },
        )
    except FileNotFoundError as exc:
        raise GitError("O `git` não está instalado nesta máquina.") from exc
    except subprocess.TimeoutExpired as exc:
        raise GitError(f"O Git demorou mais de {TIMEOUT}s e foi interrompido.") from exc
    if resultado.returncode != 0:
        erro = (resultado.stderr or resultado.stdout or "").strip().splitlines()
        motivo = erro[0][:200] if erro else f"código {resultado.returncode}"
        raise GitError(f"O Git recusou: {motivo}")
    return resultado.stdout


def status(caminho: str = "", *, raizes: Sequence[Path] | None = None) -> dict[str, Any]:
    """Branch atual, à frente/atrás do remoto e a lista do que mudou."""
    repo = repositorio(caminho, raizes)
    linhas = _rodar(repo, ["status", "--porcelain=v1", "-b"]).splitlines()
    branch = ""
    a_frente = 0
    atras = 0
    arquivos: list[dict[str, str]] = []
    for linha in linhas:
        if linha.startswith("## "):
            cabeca = linha[3:]
            branch = cabeca.split("...")[0].strip()
            achado = re.search(r"\[(.+?)\]", cabeca)
            if achado:
                if frente := re.search(r"ahead (\d+)", achado.group(1)):
                    a_frente = int(frente.group(1))
                if atraso := re.search(r"behind (\d+)", achado.group(1)):
                    atras = int(atraso.group(1))
            continue
        if len(linha) < 4:
            continue
        codigo = linha[:2].strip()
        arquivos.append({"estado": codigo, "caminho": linha[3:][:300]})
    return {
        "repositorio": str(repo),
        "branch": branch,
        "a_frente": a_frente,
        "atras": atras,
        "arquivos": arquivos[:MAX_LINHAS],
        "total": len(arquivos),
        "limpo": not arquivos,
        "resposta": (
            f"Branch {branch or '(sem nome)'}: nada modificado."
            if not arquivos
            else f"Branch {branch or '(sem nome)'}: {len(arquivos)} arquivo(s) modificado(s)."
        ),
    }


def log(
    caminho: str = "",
    *,
    limite: int = 10,
    raizes: Sequence[Path] | None = None,
) -> dict[str, Any]:
    """Últimos commits — hash curto, data, autor e assunto."""
    repo = repositorio(caminho, raizes)
    quantos = max(1, min(int(limite), 50))
    saida = _rodar(
        repo,
        ["log", f"-n{quantos}", "--pretty=format:%h%x09%ad%x09%an%x09%s", "--date=short"],
    )
    commits = []
    for linha in saida.splitlines():
        partes = linha.split("\t")
        if len(partes) >= 4:
            commits.append({"hash": partes[0], "data": partes[1], "autor": partes[2], "assunto": partes[3][:200]})
    return {
        "repositorio": str(repo),
        "commits": commits,
        "total": len(commits),
        "resposta": f"{len(commits)} commit(s) em {repo.name}.",
    }


def diff(
    caminho: str = "",
    *,
    arquivo: str = "",
    staged: bool = False,
    limite: int = MAX_TEXTO,
    raizes: Sequence[Path] | None = None,
) -> dict[str, Any]:
    """O que mudou — resumo por arquivo e o patch, cortado no teto."""
    repo = repositorio(caminho, raizes)
    args = ["diff", "--no-color"]
    if staged:
        args.append("--staged")
    alvo = (arquivo or "").strip()
    if alvo:
        if ".." in alvo or alvo.startswith(("/", "-")):
            raise GitError("Caminho de arquivo inválido para o diff.")
        args += ["--", alvo[:300]]
    resumo = _rodar(repo, args + ["--stat"])
    patch = _rodar(repo, args)
    teto = max(500, min(int(limite), MAX_TEXTO))
    return {
        "repositorio": str(repo),
        "staged": bool(staged),
        "resumo": resumo[-4_000:],
        "patch": patch[:teto],
        "cortado": len(patch) > teto,
        "vazio": not patch.strip(),
        "resposta": "Nada mudado." if not patch.strip() else resumo.strip()[:1_000],
    }


def remoto(caminho: str = "", *, raizes: Sequence[Path] | None = None) -> dict[str, Any]:
    """De onde vem e para onde vai — sem fazer `fetch`."""
    repo = repositorio(caminho, raizes)
    saida = _rodar(repo, ["remote", "-v"])
    remotos: dict[str, dict[str, str]] = {}
    for linha in saida.splitlines():
        partes = linha.split()
        if len(partes) < 3:
            continue
        nome, url, tipo = partes[0], partes[1], partes[2].strip("()")
        remotos.setdefault(nome, {})[tipo] = url
    upstream = ""
    try:
        upstream = _rodar(repo, ["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"]).strip()
    except GitError:
        upstream = ""
    return {
        "repositorio": str(repo),
        "remotos": remotos,
        "upstream": upstream,
        "resposta": (
            f"Remoto: {', '.join(remotos)}. Upstream: {upstream or 'nenhum'}."
            if remotos
            else "Este repositório não tem remoto configurado."
        ),
    }
