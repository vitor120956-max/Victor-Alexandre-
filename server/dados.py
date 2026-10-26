"""Onde ficam os dados: `storage/` ao lado do projeto ou o caminho de `JARVIS_DADOS`.

O motivo é concreto: o projeto cabe num pendrive de 8 GB, a biblioteca de livros
e repositórios não. Em vez de espalhar caminho fixo pelo servidor, tudo que grava
passa a perguntar aqui — e a resposta pode morar em outro disco.

- **padrão**: `<projeto>/storage`;
- **`JARVIS_DADOS`**: caminho absoluto (ou relativo ao projeto) usado no lugar;
- a variável é lida na hora, depois do `.env` carregado, e aplicada por
  `apontar()` antes de a API começar a servir.

Nada aqui move arquivo: quem move é `mover-dados.py`, de propósito, para a cópia
ser uma decisão sua com progresso na tela.
"""
from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Any

PROJETO = Path(__file__).resolve().parent.parent
VARIAVEL = "JARVIS_DADOS"

# Áreas conhecidas, na ordem em que o relatório mostra.
AREAS = (
    ("user-files", "documentos da área isolada"),
    ("biblioteca", "livros, vídeos e pesquisas"),
    ("repos", "repositórios baixados"),
    ("agente-local", "skills criadas e histórico"),
    ("host-downloads", "quarentena de downloads"),
    ("evolucao", "ensaios e backups"),
)


def raiz() -> Path:
    """Pasta de dados em uso — sem criar nada."""
    valor = (os.environ.get(VARIAVEL) or "").strip()
    if not valor:
        return PROJETO / "storage"
    caminho = Path(valor).expanduser()
    return caminho if caminho.is_absolute() else PROJETO / caminho


def area(nome: str) -> Path:
    return raiz() / nome


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
        arquivos, total = _medir(raiz_atual / nome)
        medido.append(
            {
                "nome": nome,
                "descricao": descricao,
                "existe": (raiz_atual / nome).exists(),
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
        "no_projeto": no_projeto,
        "areas": medido,
        "bytes_total": sum(item["bytes"] for item in medido),
        "arquivos_total": sum(item["arquivos"] for item in medido),
        "disco_livre": livre,
        "disco_total": total_disco,
    }


def apontar() -> Path:
    """Reaponta os módulos que guardam caminho em constante de importação.

    Só age quando `JARVIS_DADOS` está definida: sem a variável, cada módulo
    segue no padrão e os testes que trocam caminho por `monkeypatch` continuam
    valendo.
    """
    raiz_atual = raiz()
    if not (os.environ.get(VARIAVEL) or "").strip():
        return raiz_atual

    from . import elevacao, evolucao, repos, sistema  # import tardio: evita ciclo

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
            setattr(modulo, "PASTA_REPOS", raiz_atual / "repos")
        if hasattr(modulo, "INDICE") and modulo is repos:
            setattr(modulo, "INDICE", raiz_atual / "repos" / "indice.json")
    return raiz_atual
