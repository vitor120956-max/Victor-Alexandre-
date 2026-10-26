"""GitHub público, sem Git instalado e sem token: ler repositório, arquivo e buscar.

A pergunta que abriu esta camada foi “dá para ele usar o GitHub?”. Usar, no
sentido que interessa aqui, é **ler**: achar repositório, ver o que tem dentro,
pegar o texto de um arquivo e trazer para a conversa. É isso que a API pública
do GitHub entrega sem chave nenhuma — com um limite honesto de **60 pedidos por
hora por endereço IP**, e só para conteúdo público.

O que esta camada **não** faz: não clona, não dá `push`, não abre *issue*, não
mexe em repositório privado, não usa o Copilot. Copilot é serviço de modelo
pago: exige assinatura e token, e o projeto é sem chave de IA por decisão sua.
Para clonar um repositório público inteiro existe `repos.baixar` (o `.zip`);
esta camada é para **espiar** — e para achar o `SKILL.md` que vira habilidade em
`habilidades.importar`.
"""
from __future__ import annotations

import base64
import binascii
import json
import re
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

API = "https://api.github.com"
AGENTE = "jarvis-github/1.0 (+local)"
TIMEOUT = 20
MAX_RESPOSTA = 2 * 1024 * 1024
MAX_ARQUIVO = 30_000
LIMITE_BUSCA = 10

BaixarJson = Callable[[str], dict[str, Any]]


class GithubError(ValueError):
    """O GitHub não respondeu, recusou ou o nome do repositório está errado."""


def _json(url: str) -> dict[str, Any]:
    pedido = Request(
        url,
        headers={
            "User-Agent": AGENTE,
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    try:
        with urlopen(pedido, timeout=TIMEOUT) as resposta:
            bruto = resposta.read(MAX_RESPOSTA + 1)
    except HTTPError as exc:
        if exc.code == 404:
            raise GithubError("O GitHub não achou isso (404). Confira dono/repositório e o caminho.") from exc
        if exc.code in {403, 429}:
            raise GithubError(
                "O GitHub recusou por limite de pedidos (60 por hora, sem token). Espere um pouco e tente de novo."
            ) from exc
        raise GithubError(f"O GitHub respondeu HTTP {exc.code}.") from exc
    except (URLError, OSError) as exc:
        raise GithubError(f"Sem resposta do GitHub: {type(exc).__name__}.") from exc
    if len(bruto) > MAX_RESPOSTA:
        raise GithubError("Resposta grande demais para ler.")
    try:
        dados = json.loads(bruto.decode("utf-8", errors="replace"))
    except ValueError as exc:
        raise GithubError("O GitHub devolveu algo que não é JSON.") from exc
    if not isinstance(dados, dict):
        raise GithubError("Resposta do GitHub em formato inesperado.")
    return dados


_RE_REPO = re.compile(r"^[A-Za-z0-9_.-]{1,100}/[A-Za-z0-9_.-]{1,100}$")


def _partes(repositorio: str) -> tuple[str, str]:
    limpo = (repositorio or "").strip().strip("/")
    limpo = re.sub(r"^https?://(?:www\.)?github\.com/", "", limpo, flags=re.I)
    limpo = limpo.removesuffix(".git")
    if not _RE_REPO.match(limpo):
        raise GithubError("Escreva o repositório como `dono/repositorio`.")
    dono, nome = limpo.split("/", 1)
    return dono, nome


def _url_repo(dono: str, nome: str, sufixo: str = "") -> str:
    return f"{API}/repos/{quote(dono)}/{quote(nome)}{sufixo}"


# ------------------------------------------------------------------ repositório

def repo(repositorio: str, *, baixar: BaixarJson | None = None) -> dict[str, Any]:
    """Ficha do repositório: o que é, quantas estrelas, linguagem, licença."""
    dono, nome = _partes(repositorio)
    fetch = baixar or _json
    bruto = fetch(_url_repo(dono, nome))
    licenca = (bruto.get("license") or {}).get("spdx_id") or ""
    return {
        "repositorio": f"{dono}/{nome}",
        "descricao": (bruto.get("description") or "")[:300],
        "estrelas": int(bruto.get("stargazers_count") or 0),
        "linguagem": bruto.get("language") or "",
        "licenca": "" if licenca == "NOASSERTION" else licenca,
        "branch_padrao": bruto.get("default_branch") or "",
        "atualizado_em": bruto.get("pushed_at") or bruto.get("updated_at") or "",
        "tamanho_kb": int(bruto.get("size") or 0),
        "arquivado": bool(bruto.get("archived")),
        "url": bruto.get("html_url") or f"https://github.com/{dono}/{nome}",
        "topicos": [str(item) for item in (bruto.get("topics") or [])][:10],
    }


def arquivos(
    repositorio: str,
    caminho: str = "",
    *,
    ref: str = "",
    baixar: BaixarJson | None = None,
) -> list[dict[str, Any]]:
    """Lista o que tem numa pasta do repositório (uma pasta por vez)."""
    dono, nome = _partes(repositorio)
    fetch = baixar or _json
    alvo = (caminho or "").strip().strip("/")
    url = _url_repo(dono, nome, f"/contents/{quote(alvo)}" if alvo else "/contents/")
    if ref:
        url += f"?ref={quote(ref)}"
    bruto = fetch(url)
    itens = bruto.get("itens") if isinstance(bruto.get("itens"), list) else None
    if itens is None:
        # A API devolve um objeto só quando o caminho é um arquivo.
        if bruto.get("type") == "file":
            return [
                {
                    "nome": bruto.get("name") or alvo,
                    "tipo": "arquivo",
                    "tamanho": int(bruto.get("size") or 0),
                    "caminho": bruto.get("path") or alvo,
                }
            ]
        raise GithubError("O GitHub não devolveu uma lista de arquivos para esse caminho.")
    saida = []
    for item in itens:
        if not isinstance(item, dict):
            continue
        tipo = {"dir": "pasta", "file": "arquivo", "symlink": "link", "submodule": "submódulo"}.get(
            str(item.get("type") or ""), str(item.get("type") or "?")
        )
        saida.append(
            {
                "nome": str(item.get("name") or ""),
                "tipo": tipo,
                "tamanho": int(item.get("size") or 0),
                "caminho": str(item.get("path") or ""),
            }
        )
    return sorted(saida, key=lambda item: (item["tipo"] != "pasta", item["nome"].lower()))


def arquivo(
    repositorio: str,
    caminho: str,
    *,
    ref: str = "",
    baixar: BaixarJson | None = None,
    limite: int = MAX_ARQUIVO,
) -> dict[str, Any]:
    """Texto de um arquivo do repositório, decodificado do base64 da API."""
    alvo = (caminho or "").strip().strip("/")
    if not alvo:
        raise GithubError("Diga o caminho do arquivo, por exemplo `SKILL.md`.")
    dono, nome = _partes(repositorio)
    fetch = baixar or _json
    url = _url_repo(dono, nome, f"/contents/{quote(alvo)}")
    if ref:
        url += f"?ref={quote(ref)}"
    bruto = fetch(url)
    if bruto.get("type") == "dir":
        raise GithubError("Esse caminho é uma pasta; peça `github.arquivos` para listar o conteúdo.")
    conteudo = bruto.get("content") or ""
    if bruto.get("encoding") == "base64" and conteudo:
        try:
            texto = base64.b64decode(conteudo).decode("utf-8", errors="replace")
        except (binascii.Error, ValueError) as exc:
            raise GithubError("O conteúdo do arquivo não decodificou como texto.") from exc
    else:
        texto = str(conteudo)
    if not texto.strip():
        raise GithubError("O arquivo veio vazio (ou é binário).")
    return {
        "repositorio": f"{dono}/{nome}",
        "caminho": bruto.get("path") or alvo,
        "url": bruto.get("html_url") or "",
        "bytes": int(bruto.get("size") or len(texto)),
        "texto": texto[:limite],
        "cortado": len(texto) > limite,
    }


def arvore(
    repositorio: str,
    *,
    ref: str = "",
    baixar: BaixarJson | None = None,
    limite: int = 400,
    sufixo: str = "",
) -> list[str]:
    """Caminhos de arquivo do repositório inteiro, de uma vez (árvore recursiva).

    Serve para achar onde estão os `SKILL.md` de um repositório de habilidades,
    sem baixar o `.zip` e sem clonar. `sufixo` filtra pelo fim do caminho.
    """
    dono, nome = _partes(repositorio)
    fetch = baixar or _json
    alvo = (ref or "HEAD").strip()
    bruto = fetch(_url_repo(dono, nome, f"/git/trees/{quote(alvo)}?recursive=1"))
    itens = bruto.get("tree") if isinstance(bruto.get("tree"), list) else []
    caminhos = [
        str(item.get("path"))
        for item in itens
        if isinstance(item, dict)
        and item.get("type") == "blob"
        and item.get("path")
        and (not sufixo or str(item.get("path")).lower().endswith(sufixo.lower()))
    ]
    return caminhos[:limite]


def buscar(consulta: str, *, limite: int = 5, baixar: BaixarJson | None = None) -> list[dict[str, Any]]:
    """Procura repositório público por palavra — ordenado por estrelas."""
    termo = (consulta or "").strip()
    if len(termo) < 2:
        raise GithubError("Escreva o que procurar (pelo menos 2 caracteres).")
    quantos = max(1, min(int(limite), LIMITE_BUSCA))
    fetch = baixar or _json
    bruto = fetch(f"{API}/search/repositories?q={quote(termo)}&sort=stars&order=desc&per_page={quantos}")
    itens = bruto.get("items") if isinstance(bruto.get("items"), list) else []
    saida: list[dict[str, Any]] = []
    for item in itens[:quantos]:
        if not isinstance(item, dict) or not item.get("full_name"):
            continue
        saida.append(
            {
                "repositorio": str(item["full_name"]),
                "descricao": (item.get("description") or "")[:200],
                "estrelas": int(item.get("stargazers_count") or 0),
                "linguagem": item.get("language") or "",
                "url": item.get("html_url") or "",
            }
        )
    return saida
