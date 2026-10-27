"""Cópia de segurança do que importa — e prova de que ela abre.

O pedido veio em forma de medo: *“e se eu perder tudo?”*. O JARVIS guarda
documentos, livros, repositórios baixados e a própria memória em `storage/`. Esta
camada empacota isso em um `.zip` com data no nome, hash ao lado, e um teste de
integridade na hora de criar — backup que não abre não é backup.

O que entra:

- tudo em `storage/` (documentos, livros, catálogo, agenda, memória do agente);
- opcionalmente `storage/repos` (os repositórios baixados), que costuma ser a
  maior parte — por isso vem desligado.

O que **não** entra, de propósito: `.venv`, `node_modules`, `__pycache__`, `.git`,
a própria pasta de backups (senão o arquivo engordaria a cada rodada) e links
simbólicos.

O destino pode ser outro disco ou o Drive (`G:\\Meu Drive\\JARVIS-backups`). Se o
destino for o mesmo disco do `storage`, o texto avisa: cópia no mesmo disco não
protege contra disco morto.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any

from . import dados as dados_locais

VERSAO = "0.60.4"

IGNORAR = {".venv", "node_modules", "__pycache__", ".git", ".pytest_cache", "backups", ".mypy_cache"}
NOME_BACKUP = "jarvis-dados-{quando}.zip"
MANIFESTO = "manifest.json"
MAX_BYTES_PADRAO = 2 * 1024 * 1024 * 1024
TETO_ARQUIVO = 512 * 1024 * 1024


class BackupError(Exception):
    """Recusa: nada foi compactado ou restaurado."""


def _raiz(raiz: Path | None) -> Path:
    return Path(raiz) if raiz is not None else Path(dados_locais.raiz())


def _destino(destino: str | Path | None, raiz: Path) -> Path:
    bruto = (str(destino).strip() if destino else "") or str(raiz / "backups")
    alvo = Path(bruto).expanduser()
    if not alvo.is_absolute():
        alvo = raiz / alvo
    return alvo


def _livre_gb(caminho: Path) -> float | None:
    alvo = caminho
    while not alvo.exists() and alvo != alvo.parent:
        alvo = alvo.parent
    try:
        return round(shutil.disk_usage(alvo).free / (1024**3), 1)
    except OSError:
        return None


def _arquivos(raiz: Path, destino: Path, incluir_repos: bool) -> tuple[list[Path], list[dict[str, str]]]:
    """Lista o que entra, com o motivo de cada exclusão — sem varrer o que não deve."""
    entram: list[Path] = []
    ignorados: list[dict[str, str]] = []
    try:
        destino_real = destino.resolve()
    except OSError:
        destino_real = destino
    for item in sorted(raiz.rglob("*")):
        try:
            relativo = item.relative_to(raiz)
        except ValueError:
            continue
        partes = set(relativo.parts)
        if partes & IGNORAR:
            continue
        if item.is_symlink():
            ignorados.append({"caminho": relativo.as_posix(), "motivo": "link simbólico"})
            continue
        if not item.is_file():
            continue
        if not incluir_repos and relativo.parts[:1] == ("repos",):
            continue
        try:
            if destino_real in item.resolve().parents:
                ignorados.append({"caminho": relativo.as_posix(), "motivo": "está dentro do destino"})
                continue
            tamanho = item.stat().st_size
        except OSError:
            ignorados.append({"caminho": relativo.as_posix(), "motivo": "não consegui medir"})
            continue
        if tamanho > TETO_ARQUIVO:
            ignorados.append(
                {"caminho": relativo.as_posix(), "motivo": f"acima de {TETO_ARQUIVO // (1024**2)} MB"}
            )
            continue
        entram.append(item)
    return entram, ignorados


def planejar(
    *,
    raiz: Path | None = None,
    destino: str = "",
    incluir_repos: bool = False,
    agora: datetime | None = None,
) -> dict[str, Any]:
    """Diz o que entraria, quanto pesa e se o destino tem espaço. Não copia nada."""
    base = _raiz(raiz)
    if not base.exists():
        raise BackupError(f"A raiz de dados não existe: {base}")
    alvo = _destino(destino, base)
    arquivos, ignorados = _arquivos(base, alvo, incluir_repos)
    total = 0
    maiores: list[dict[str, Any]] = []
    for arquivo in arquivos:
        try:
            tamanho = arquivo.stat().st_size
        except OSError:
            continue
        total += tamanho
        maiores.append({"caminho": arquivo.relative_to(base).as_posix(), "bytes": tamanho})
    maiores.sort(key=lambda item: item["bytes"], reverse=True)
    livre = _livre_gb(alvo)
    mesmo_disco = False
    try:
        mesmo_disco = alvo.resolve().anchor.upper() == base.resolve().anchor.upper()
    except OSError:
        pass
    avisos: list[str] = []
    if mesmo_disco:
        avisos.append(
            "O destino está no mesmo disco dos dados: protege contra apagar sem querer, "
            "não contra o disco morrer. Um pendrive ou o Drive resolve."
        )
    if livre is not None and total / (1024**3) > livre * 0.8:
        avisos.append(f"O backup ({total / (1024**3):.1f} GB) quase não cabe nos {livre:g} GB livres do destino.")
    if not arquivos:
        avisos.append("Não há arquivo para copiar nessa raiz.")
    return {
        "raiz": str(base),
        "destino": str(alvo),
        "arquivos": len(arquivos),
        "bytes": total,
        "gb": round(total / (1024**3), 2),
        "maiores": maiores[:8],
        "ignorados": ignorados[:20],
        "livre_gb": livre,
        "mesmo_disco": mesmo_disco,
        "avisos": avisos,
        "incluir_repos": incluir_repos,
        "resposta": (
            f"{len(arquivos)} arquivo(s), {total / (1024**2):.1f} MB, para {alvo}."
            if arquivos
            else "Nada para copiar."
        ),
    }


def criar(
    *,
    raiz: Path | None = None,
    destino: str = "",
    incluir_repos: bool = False,
    max_bytes: int = MAX_BYTES_PADRAO,
    agora: datetime | None = None,
) -> dict[str, Any]:
    """Cria o `.zip` com manifesto e SHA-256, e confere se ele abre."""
    momento = (agora or datetime.now()).replace(microsecond=0)
    plano = planejar(raiz=raiz, destino=destino, incluir_repos=incluir_repos, agora=momento)
    base = Path(plano["raiz"])
    alvo = Path(plano["destino"])
    if not plano["arquivos"]:
        raise BackupError("Não há arquivo para copiar.")
    if plano["bytes"] > max_bytes:
        raise BackupError(
            f"O backup passaria de {max_bytes // (1024**2)} MB. Ligue `incluir_repos` só quando precisar, "
            "ou aumente o teto com consciência do espaço."
        )
    alvo.mkdir(parents=True, exist_ok=True)
    nome = NOME_BACKUP.format(quando=momento.strftime("%Y%m%d-%H%M%S"))
    arquivo = alvo / nome
    if arquivo.exists():
        arquivo = alvo / nome.replace(".zip", f"-{momento.strftime('%f')[:3]}.zip")
    manifesto = {
        "versao": VERSAO,
        "criado_em": momento.isoformat(),
        "raiz": str(base),
        "incluir_repos": incluir_repos,
        "arquivos": plano["arquivos"],
        "bytes": plano["bytes"],
    }
    digest = hashlib.sha256()
    copiados = 0
    try:
        with zipfile.ZipFile(arquivo, "w", compression=zipfile.ZIP_DEFLATED, allowZip64=True) as pacote:
            pacote.writestr(MANIFESTO, json.dumps(manifesto, ensure_ascii=False, indent=2))
            for caminho in _arquivos(base, alvo, incluir_repos)[0]:
                relativo = caminho.relative_to(base).as_posix()
                pacote.write(caminho, arcname=relativo)
                copiados += 1
            ruim = pacote.testzip()
            if ruim is not None:
                raise BackupError(f"O arquivo saiu corrompido em “{ruim}”; apaguei o backup.")
    except OSError as exc:
        arquivo.unlink(missing_ok=True)
        raise BackupError(f"Não consegui escrever o backup: {type(exc).__name__}.") from exc
    except BackupError:
        arquivo.unlink(missing_ok=True)
        raise
    with open(arquivo, "rb") as aberto:
        while bloco := aberto.read(1024 * 1024):
            digest.update(bloco)
    sha = digest.hexdigest()
    (alvo / f"{arquivo.name}.sha256").write_text(f"{sha}  {arquivo.name}\n", encoding="utf-8")
    (alvo / f"{arquivo.name}.json").write_text(
        json.dumps({**manifesto, "sha256": sha, "zip_bytes": arquivo.stat().st_size}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return {
        "arquivo": str(arquivo),
        "sha256": sha,
        "bytes": arquivo.stat().st_size,
        "arquivos": copiados,
        "destino": str(alvo),
        "abre": True,
        "resposta": (
            f"Backup criado: {arquivo.name} — {copiados} arquivo(s), "
            f"{arquivo.stat().st_size / (1024**2):.1f} MB, sha256 {sha[:16]}…"
        ),
    }


def listar(*, raiz: Path | None = None, destino: str = "") -> dict[str, Any]:
    base = _raiz(raiz)
    alvo = _destino(destino, base)
    if not alvo.exists():
        return {"destino": str(alvo), "backups": [], "total": 0, "resposta": "Ainda não há backup nessa pasta."}
    itens: list[dict[str, Any]] = []
    for arquivo in sorted(alvo.glob("jarvis-dados-*.zip"), reverse=True):
        try:
            tamanho = arquivo.stat().st_size
        except OSError:
            continue
        itens.append(
            {
                "arquivo": arquivo.name,
                "caminho": str(arquivo),
                "mb": round(tamanho / (1024**2), 1),
                "quando": datetime.fromtimestamp(arquivo.stat().st_mtime).strftime("%d/%m/%Y %H:%M"),
            }
        )
    return {
        "destino": str(alvo),
        "backups": itens,
        "total": len(itens),
        "resposta": f"{len(itens)} backup(s) em {alvo}." if itens else "Ainda não há backup nessa pasta.",
    }


def restaurar(
    arquivo: str,
    *,
    destino: str,
    raiz: Path | None = None,
) -> dict[str, Any]:
    """Extrai para uma pasta **nova**; nunca sobrescreve o que está em uso."""
    base = _raiz(raiz)
    origem = Path(arquivo).expanduser()
    if not origem.is_absolute():
        origem = _destino("", base) / arquivo
    if not origem.is_file():
        raise BackupError(f"Backup não encontrado: {origem}")
    if not (destino or "").strip():
        raise BackupError("Informe a pasta de destino da restauração (uma pasta nova, vazia).")
    alvo = Path(destino).expanduser()
    if not alvo.is_absolute():
        alvo = base / alvo
    if alvo.exists() and any(alvo.iterdir()):
        raise BackupError(
            f"A pasta {alvo} não está vazia. Restaurar por cima do que está em uso é como "
            "apagar o original; escolha uma pasta nova."
        )
    try:
        with zipfile.ZipFile(origem) as pacote:
            nomes = pacote.namelist()
            for nome in nomes:
                destino_item = (alvo / nome).resolve()
                if not str(destino_item).startswith(str(alvo.resolve())):
                    raise BackupError(f"O backup tem caminho que sai da pasta: “{nome}”.")
            ruim = pacote.testzip()
            if ruim is not None:
                raise BackupError(f"O backup está corrompido em “{ruim}”.")
            alvo.mkdir(parents=True, exist_ok=True)
            pacote.extractall(alvo)
    except zipfile.BadZipFile as exc:
        raise BackupError("O arquivo não é um .zip válido.") from exc
    return {
        "arquivo": str(origem),
        "destino": str(alvo),
        "itens": len(nomes),
        "resposta": f"Restaurei {len(nomes)} item(ns) em {alvo}. Nada do que estava em uso foi tocado.",
    }
