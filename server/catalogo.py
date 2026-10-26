"""Catálogo de habilidades de terceiros: ler a planilha e importar por linha.

O usuário exportou uma tabela de 100 habilidades (skills.sh, clawhub, skillhub)
com colunas `rank, skill, repo_url, vendor, category…` e perguntou o que fazer
com ela. Esta camada transforma a tabela em algo utilizável:

- **carregar** — lê o CSV (vírgula ou ponto e vírgula, com ou sem BOM), confere
  as colunas, tira duplicata e guarda em `storage/catalogo.json`;
- **listar** — filtra por fornecedor, categoria, faixa de rank ou palavra;
- **importar** — pega as linhas escolhidas e usa `habilidades.importar` para
  trazer o `SKILL.md` de cada uma, achando o caminho certo pela árvore do
  repositório no GitHub (a mesma skill pode morar em `skills/<nome>` ou em
  `skills/engineering/<nome>`).

Sem token nenhum. O limite real é o do GitHub público: **60 pedidos por hora**,
então a importação é feita em levas pequenas, com o que faltou devolvido.
"""
from __future__ import annotations

import csv
import io
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from . import dados, github, habilidades

ARQUIVO = "catalogo.json"
MAX_LINHAS = 2_000
MAX_IMPORTAR = 10
Baixar = Callable[[str], str]


class CatalogoError(ValueError):
    """Planilha sem coluna obrigatória, vazia ou ilegível."""


# ------------------------------------------------------------------- planilha

def _ler_texto(origem: Path | str) -> str:
    caminho = Path(origem).expanduser()
    try:
        bruto = caminho.read_bytes()
    except OSError as exc:
        raise CatalogoError(f"Não consegui abrir {caminho}: {exc}") from exc
    for codificacao in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            return bruto.decode(codificacao)
        except UnicodeDecodeError:
            continue
    return bruto.decode("utf-8", errors="replace")


def interpretar_csv(texto: str) -> list[dict[str, Any]]:
    """Normaliza a tabela colada/exportada em linhas utilizáveis."""
    limpo = (texto or "").lstrip("\ufeff")
    if not limpo.strip():
        raise CatalogoError("A planilha veio vazia.")
    if limpo.lower().startswith("sep="):
        limpo = limpo.split("\n", 1)[1] if "\n" in limpo else ""
    primeira = limpo.splitlines()[0] if limpo.splitlines() else ""
    delimitador = ";" if primeira.count(";") > primeira.count(",") else ","
    leitor = csv.DictReader(io.StringIO(limpo), delimiter=delimitador)
    if not leitor.fieldnames:
        raise CatalogoError("A planilha não tem cabeçalho.")
    colunas = {nome.strip().lower(): nome for nome in leitor.fieldnames if nome}
    if "skill" not in colunas:
        raise CatalogoError("A planilha precisa da coluna `skill` (nome da habilidade).")
    if not ({"repo_url", "url"} & set(colunas)):
        raise CatalogoError("A planilha precisa de `repo_url` ou `url`.")

    vistos: set[tuple[str, str]] = set()
    itens: list[dict[str, Any]] = []
    for numero, linha in enumerate(leitor, start=2):
        if len(itens) >= MAX_LINHAS:
            break
        def valor(nome: str) -> str:
            original = colunas.get(nome)
            return " ".join(str(linha.get(original) or "").split()) if original else ""
        nome = valor("skill")
        if not nome:
            continue
        repo = valor("repo_url")
        url = valor("url")
        if not repo and "github.com" in url:
            repo = re.sub(r"/(blob|tree)/.*$", "", url)
        chave = (repo.lower(), nome.lower())
        if chave in vistos:
            continue
        vistos.add(chave)
        rank = valor("rank")
        itens.append(
            {
                "rank": int(rank) if rank.isdigit() else numero - 1,
                "skill": nome[:80],
                "vendor": valor("vendor")[:80],
                "repo_url": repo[:300],
                "url": url[:300],
                "category": valor("category")[:40],
                "platform": valor("platform")[:40],
                "description": valor("description")[:300],
                "install": valor("install")[:300],
            }
        )
    if not itens:
        raise CatalogoError("Nenhuma linha válida: todas sem `skill` ou sem endereço.")
    itens.sort(key=lambda item: item["rank"])
    return itens


def carregar(origem: Path | str, raiz: Path | None = None) -> dict[str, Any]:
    """Lê a planilha, normaliza e guarda — devolve o resumo do que entrou."""
    itens = interpretar_csv(_ler_texto(origem))
    pasta = Path(raiz) if raiz else dados.raiz()
    pasta.mkdir(parents=True, exist_ok=True)
    (pasta / ARQUIVO).write_text(
        json.dumps(
            {"carregado_em": datetime.now(timezone.utc).isoformat(), "total": len(itens), "itens": itens},
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    por_categoria: dict[str, int] = {}
    por_fornecedor: dict[str, int] = {}
    for item in itens:
        por_categoria[item["category"] or "sem categoria"] = por_categoria.get(item["category"] or "sem categoria", 0) + 1
        por_fornecedor[item["vendor"] or "sem fornecedor"] = por_fornecedor.get(item["vendor"] or "sem fornecedor", 0) + 1
    return {
        "total": len(itens),
        "arquivo": str(pasta / ARQUIVO),
        "por_categoria": dict(sorted(por_categoria.items(), key=lambda par: -par[1])[:15]),
        "por_fornecedor": dict(sorted(por_fornecedor.items(), key=lambda par: -par[1])[:15]),
        "primeiras": itens[:5],
    }


def ler(raiz: Path | None = None) -> list[dict[str, Any]]:
    pasta = Path(raiz) if raiz else dados.raiz()
    try:
        bruto = json.loads((pasta / ARQUIVO).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    itens = bruto.get("itens") if isinstance(bruto, dict) else bruto
    return [item for item in (itens or []) if isinstance(item, dict) and item.get("skill")]


def filtrar(
    raiz: Path | None = None,
    *,
    fornecedor: str = "",
    categoria: str = "",
    texto: str = "",
    de_rank: int = 0,
    ate_rank: int = 0,
    limite: int = 30,
) -> dict[str, Any]:
    """Filtra o catálogo já carregado. Sem catálogo, ensina a carregar."""
    itens = ler(raiz)
    if not itens:
        raise CatalogoError(
            "Nenhum catálogo carregado. Salve o CSV em `storage/catalogo-skills.csv` e peça "
            "“carrega o catálogo de skills”."
        )
    alvo_texto = (texto or "").strip().lower()
    selecionados = []
    for item in itens:
        if fornecedor and fornecedor.lower() not in (item.get("vendor") or "").lower():
            continue
        if categoria and categoria.lower() not in (item.get("category") or "").lower():
            continue
        if de_rank and int(item.get("rank") or 0) < de_rank:
            continue
        if ate_rank and int(item.get("rank") or 0) > ate_rank:
            continue
        if alvo_texto and alvo_texto not in f"{item.get('skill')} {item.get('description')}".lower():
            continue
        selecionados.append(item)
    return {"total": len(selecionados), "mostrando": min(limite, len(selecionados)), "itens": selecionados[:limite]}


# ------------------------------------------------------------------ importar

_arvores: dict[str, list[str]] = {}


def _dono_repo(repo_url: str) -> str:
    """`https://github.com/a/b` → `a/b`; vazio quando não é repositório do GitHub."""
    limpo = (repo_url or "").strip().rstrip("/")
    limpo = re.sub(r"^https?://(?:www\.)?github\.com/", "", limpo)
    partes = limpo.split("/")
    if len(partes) < 2 or not all(partes[:2]) or " " in limpo:
        return ""
    return "/".join(partes[:2])


def _caminhos_do_repo(repo: str) -> list[str] | None:
    """Caminhos de `SKILL.md` no repositório; `None` quando a consulta falhou."""
    chave = repo.lower()
    if chave not in _arvores:
        try:
            _arvores[chave] = github.arvore(repo, sufixo="SKILL.md", limite=400)
        except github.GithubError:
            _arvores[chave] = None
    return _arvores[chave]


def _pasta_de(caminho: str) -> str:
    pasta = caminho.rsplit("/", 1)[0] if "/" in caminho else ""
    return re.sub(r"[^a-z0-9]+", "-", pasta.rsplit("/", 1)[-1].lower()).strip("-")


def _caminho_da_skill(caminhos: list[str], skill: str) -> str:
    """O `SKILL.md` cuja pasta tem o mesmo nome da habilidade (ou o da raiz)."""
    alvo = re.sub(r"[^a-z0-9]+", "-", skill.lower()).strip("-")
    for caminho in caminhos:
        if _pasta_de(caminho) == alvo:
            return caminho
    return "SKILL.md" if "SKILL.md" in caminhos else ""


def _endereco_da_skill(repo_url: str, skill: str) -> str:
    """Endereço cru do `SKILL.md` daquela habilidade dentro do repositório."""
    repo = _dono_repo(repo_url)
    if not repo:
        return ""
    caminho = _caminho_da_skill(_caminhos_do_repo(repo) or [], skill)
    return f"https://raw.githubusercontent.com/{repo}/HEAD/{caminho}" if caminho else ""


def _sem_importacao(item: dict[str, Any], erro: str) -> dict[str, str]:
    """Falha de uma linha — com o comando da plataforma quando não há repositório."""
    falha = {"skill": item["skill"], "erro": erro}
    if item.get("install"):
        falha["install"] = str(item["install"])[:200]
    return falha


def importar(
    raiz: Path | None = None,
    *,
    quantos: int = 5,
    fornecedor: str = "",
    categoria: str = "",
    texto: str = "",
    de_rank: int = 0,
    ate_rank: int = 0,
    baixar: Baixar | None = None,
) -> dict[str, Any]:
    """Importa as habilidades escolhidas do catálogo, uma a uma, sem derrubar as outras."""
    escolhidos = filtrar(
        raiz,
        fornecedor=fornecedor,
        categoria=categoria,
        texto=texto,
        de_rank=de_rank,
        ate_rank=ate_rank,
        limite=max(1, min(int(quantos), MAX_IMPORTAR)),
    )
    importadas: list[dict[str, Any]] = []
    falhas: list[dict[str, str]] = []
    usados: set[str] = set()
    for item in escolhidos["itens"]:
        repo_url = item.get("repo_url") or ""
        url = _endereco_da_skill(repo_url, item["skill"])
        if not url and repo_url:
            repo = _dono_repo(repo_url)
            if repo and _caminhos_do_repo(repo) is None:
                # A árvore não respondeu (limite do GitHub): deixa o importador
                # tentar o repositório inteiro antes de desistir.
                url = repo_url
            elif repo:
                falhas.append(
                    _sem_importacao(item, f"não achei a pasta `{item['skill']}` em {repo}")
                )
                continue
        if not url:
            falhas.append(_sem_importacao(item, "linha sem endereço de repositório"))
            continue
        try:
            ficha = habilidades.importar(url, raiz=raiz, baixar=baixar, nome=item["skill"], evitar=usados)
        except habilidades.HabilidadeError as exc:
            falhas.append(_sem_importacao(item, str(exc)[:200]))
            continue
        usados.add(ficha["slug"])
        ficha["rank"] = item.get("rank")
        ficha["repo_url"] = repo_url
        ficha["vendor"] = item.get("vendor") or ""
        importadas.append(ficha)
    return {
        "tentadas": len(escolhidos["itens"]),
        "importadas": importadas,
        "falhas": falhas,
        "total_no_catalogo": escolhidos["total"],
        "restantes": max(0, escolhidos["total"] - len(escolhidos["itens"])),
        "limite_por_chamada": MAX_IMPORTAR,
    }
