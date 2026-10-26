"""Onde ficam os dados: `storage/` ao lado do projeto ou o caminho de `JARVIS_DADOS`.

O motivo é concreto: o projeto cabe num pendrive de 8 GB, a biblioteca de livros
e repositórios não. Em vez de espalhar caminho fixo pelo servidor, tudo que grava
passa a perguntar aqui — e a resposta pode morar em outro disco.

- **padrão**: `<projeto>/storage`;
- **`JARVIS_DADOS`**: caminho absoluto (ou relativo ao projeto) usado no lugar;
- **`JARVIS_BIBLIOTECA`** e **`JARVIS_REPOS`**: movem **só** os livros e os
  repositórios. É assim que o Google Drive entra sem que o estado do agente
  (histórico, fila, skills criadas) seja regravado a cada resposta dentro de
  uma pasta sincronizada;
- as variáveis são lidas na hora, depois do `.env` carregado, e aplicadas por
  `apontar()` antes de a API começar a servir.

Nada aqui move arquivo: quem move é `mover-dados.py`, de propósito, para a cópia
ser uma decisão sua com progresso na tela.
"""
from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path
from typing import Any

PROJETO = Path(__file__).resolve().parent.parent
VARIAVEL = "JARVIS_DADOS"
VARIAVEL_BIBLIOTECA = "JARVIS_BIBLIOTECA"
VARIAVEL_REPOS = "JARVIS_REPOS"
VARIAVEL_DRIVE = "JARVIS_DRIVE"

# Nomes que aparecem no caminho quando a pasta está dentro do Google Drive.
MARCAS_DRIVE = ("google drive", "googledrive", "google-drive", "meu drive", "my drive")

# Áreas conhecidas, na ordem em que o relatório mostra.
AREAS = (
    ("user-files", "documentos da área isolada"),
    ("biblioteca", "livros, vídeos e pesquisas"),
    ("repos", "repositórios baixados"),
    ("agente-local", "skills criadas e histórico"),
    ("host-downloads", "quarentena de downloads"),
    ("evolucao", "ensaios e backups"),
)


def _resolver(variavel: str, padrao: Path) -> Path:
    valor = (os.environ.get(variavel) or "").strip()
    if not valor:
        return padrao
    caminho = Path(valor).expanduser()
    return caminho if caminho.is_absolute() else PROJETO / caminho


def raiz() -> Path:
    """Pasta de dados em uso — sem criar nada."""
    return _resolver(VARIAVEL, PROJETO / "storage")


def biblioteca() -> Path:
    """Onde ficam livros, fichas e exportadas. Pode ser uma pasta do Drive."""
    return _resolver(VARIAVEL_BIBLIOTECA, raiz() / "biblioteca")


def repositorios() -> Path:
    """Onde ficam os repositórios baixados. Pode ser uma pasta do Drive."""
    return _resolver(VARIAVEL_REPOS, raiz() / "repos")


def caminho(nome: str) -> Path:
    """Caminho efetivo de uma área, respeitando as variáveis específicas."""
    if nome == "biblioteca":
        return biblioteca()
    if nome == "repos":
        return repositorios()
    return raiz() / nome


def area(nome: str) -> Path:
    return caminho(nome)


def no_drive(caminho_: Path | str) -> bool:
    """Diz se um caminho está dentro de uma pasta sincronizada pelo Drive."""
    texto = str(caminho_).lower().replace("\\", "/")
    return any(marca in texto for marca in MARCAS_DRIVE)


def detectar_drive(casa: Path | None = None) -> Path | None:
    """Acha a pasta do Google Drive instalado nesta máquina, sem chutar demais.

    O app do Drive usa `Google Drive` (antigo) ou `My Drive`/`Meu Drive` dentro
    de uma unidade virtual. A variável `JARVIS_DRIVE` tem prioridade quando o
    usuário apontou a pasta na mão.
    """
    explicito = (os.environ.get(VARIAVEL_DRIVE) or "").strip()
    if explicito:
        caminho_ = Path(explicito).expanduser()
        return caminho_ if caminho_.is_dir() else None

    casa = casa if casa is not None else Path.home()
    candidatos: list[Path] = []
    for base in (casa / "Google Drive", casa / "GoogleDrive", casa / "Drive"):
        # o app do Drive cria <base>/Meu Drive; a subpasta é a raiz de verdade
        candidatos.extend([base / "Meu Drive", base / "My Drive", base])
    if sys.platform == "win32":
        for letra in "GHIJKLMNOPQRSTUVWXYZ":
            for nome in ("Google Drive", "My Drive", "Meu Drive"):
                candidatos.append(Path(f"{letra}:/") / nome)
    vistos: set[str] = set()
    for candidato in candidatos:
        chave = str(candidato).lower()
        if chave in vistos:
            continue
        vistos.add(chave)
        try:
            if candidato.is_dir():
                return candidato
        except OSError:
            continue
    return None


def garantir() -> Path:
    raiz().mkdir(parents=True, exist_ok=True)
    return raiz()


def _medir(pasta: Path) -> tuple[int, int]:
    arquivos = 0
    total = 0
    if not pasta.exists():
        return 0, 0
    for item in pasta.rglob("*"):
        if item.is_file():
            arquivos += 1
            try:
                total += item.stat().st_size
            except OSError:
                pass
    return arquivos, total


def relatorio() -> dict[str, Any]:
    """Tamanho de cada área, espaço livre do disco e se está fora do projeto."""
    raiz_atual = raiz()
    medido = []
    for nome, descricao in AREAS:
        pasta = caminho(nome)
        arquivos, total = _medir(pasta)
        medido.append(
            {
                "nome": nome,
                "descricao": descricao,
                "caminho": str(pasta),
                "existe": pasta.exists(),
                "no_drive": no_drive(pasta),
                "arquivos": arquivos,
                "bytes": total,
            }
        )
    try:
        uso = shutil.disk_usage(raiz_atual)
        livre = uso.free
        total_disco = uso.total
    except OSError:
        livre = total_disco = 0
    try:
        no_projeto = raiz_atual.resolve() == (PROJETO / "storage").resolve()
    except OSError:
        no_projeto = False
    return {
        "raiz": str(raiz_atual),
        "padrao": str(PROJETO / "storage"),
        "variavel": VARIAVEL,
        "configurada": bool((os.environ.get(VARIAVEL) or "").strip()),
        "biblioteca": str(biblioteca()),
        "repositorios": str(repositorios()),
        "biblioteca_variavel": VARIAVEL_BIBLIOTECA,
        "repos_variavel": VARIAVEL_REPOS,
        "drive_detectado": str(detectar_drive() or ""),
        "no_projeto": no_projeto,
        "areas": medido,
        "bytes_total": sum(item["bytes"] for item in medido),
        "arquivos_total": sum(item["arquivos"] for item in medido),
        "disco_livre": livre,
        "disco_total": total_disco,
    }


def apontar() -> Path:
    """Reaponta os módulos que guardam caminho em constante de importação.

    Só age quando alguma das variáveis (`JARVIS_DADOS`, `JARVIS_BIBLIOTECA`,
    `JARVIS_REPOS`) está definida: sem elas, cada módulo segue no padrão e os
    testes que trocam caminho por `monkeypatch` continuam valendo.

    A biblioteca não precisa de remendo: `biblioteca._pasta()` pergunta o
    caminho a `dados.biblioteca()` a cada chamada.
    """
    raiz_atual = raiz()
    tem_dados = bool((os.environ.get(VARIAVEL) or "").strip())
    tem_biblioteca = bool((os.environ.get(VARIAVEL_BIBLIOTECA) or "").strip())
    tem_repos = bool((os.environ.get(VARIAVEL_REPOS) or "").strip())
    if not (tem_dados or tem_biblioteca or tem_repos):
        return raiz_atual

    from . import elevacao, evolucao, repos, sistema
    pasta_repos = repositorios() if (tem_repos or tem_biblioteca) else raiz_atual / "repos"

    if tem_repos or tem_biblioteca:
        setattr(repos, "PASTA_REPOS", pasta_repos)
        setattr(repos, "INDICE", pasta_repos / "indice.json")
    if not tem_dados:
        return raiz_atual

    for modulo in (sistema, evolucao, elevacao, repos):
        if hasattr(modulo, "STORAGE"):
            setattr(modulo, "STORAGE", raiz_atual)
        if hasattr(modulo, "TOKEN_ARQUIVO"):
            setattr(modulo, "TOKEN_ARQUIVO", raiz_atual / "host-token.txt")
        if hasattr(modulo, "QUARENTENA"):
            setattr(modulo, "QUARENTENA", raiz_atual / "host-downloads")
        if hasattr(modulo, "AUDITORIA"):
            nome = "host-audit.jsonl"
            if modulo is evolucao:
                nome = "evolucao/audit.jsonl"
            setattr(modulo, "AUDITORIA", raiz_atual / nome)
        if hasattr(modulo, "PASTA_REPOS"):
            setattr(modulo, "PASTA_REPOS", pasta_repos)
        if hasattr(modulo, "INDICE") and modulo is repos:
            setattr(modulo, "INDICE", pasta_repos / "indice.json")
    return raiz_atual
