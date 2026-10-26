"""Leva os dados do JARVIS para um disco com espaço, sem editor de texto.

O projeto cabe num pendrive. A biblioteca de livros, os repositórios baixados e
as fichas não cabem — e o disco do projeto pode ser justamente o pequeno.

Este script:

1. mostra onde os dados estão e quanto ocupam (por área);
2. pergunta o destino (ou usa `--destino C:\\JARVIS-DADOS`);
3. copia com contagem de progresso;
4. confere arquivo por arquivo (quantidade e bytes);
5. grava `JARVIS_DADOS=<destino>` no `.env`, em CRLF;
6. diz o que fazer depois — e **não apaga** a pasta antiga.

Uso:
    .venv\\Scripts\\python mover-dados.py                 (pergunta o destino)
    .venv\\Scripts\\python mover-dados.py --destino C:\\JARVIS-DADOS
    .venv\\Scripts\\python mover-dados.py --ver           (só mostra o estado)
"""
from __future__ import annotations

import argparse
import os
import re
import shutil
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
STORAGE = RAIZ / "storage"
ENV = RAIZ / ".env"
VARIAVEL = "JARVIS_DADOS"

AREAS = (
    ("user-files", "documentos"),
    ("biblioteca", "livros, vídeos e pesquisas"),
    ("repos", "repositórios baixados"),
    ("agente-local", "skills criadas"),
    ("host-downloads", "quarentena de downloads"),
    ("evolucao", "ensaios e backups"),
)


def medir(pasta: Path) -> tuple[int, int]:
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


def mb(bytes_: int) -> str:
    return f"{bytes_ / 1e6:.1f} MB"


def ler_valor(texto: str, nome: str) -> str | None:
    achado = re.search(rf"(?m)^\s*{re.escape(nome)}\s*=(.*)$", texto)
    return achado.group(1).strip() if achado else None


def definir(texto: str, nome: str, valor: str) -> str:
    linha = f"{nome}={valor}"
    padrao = rf"(?m)^\s*{re.escape(nome)}\s*=.*$"
    if re.search(padrao, texto):
        return re.sub(padrao, lambda _: linha, texto, count=1)
    separador = "" if texto.endswith(("\n", "\r\n")) or not texto else "\n"
    return f"{texto}{separador}{linha}\n"


def gravar_env(valor: str) -> Path:
    base = ENV if ENV.is_file() else RAIZ / ".env.example"
    texto = base.read_text(encoding="utf-8") if base.is_file() else ""
    atualizado = definir(texto, VARIAVEL, valor)
    ENV.write_bytes(atualizado.replace("\r\n", "\n").replace("\n", "\r\n").encode("utf-8"))
    return ENV


def mostrar_estado() -> tuple[Path, int, int]:
    configurada = os.environ.get(VARIAVEL, "").strip()
    raiz_dados = Path(configurada).expanduser() if configurada else STORAGE
    if ENV.is_file():
        do_env = ler_valor(ENV.read_text(encoding="utf-8", errors="replace"), VARIAVEL)
        if do_env:
            raiz_dados = Path(do_env).expanduser()
    print(f"Pasta de dados em uso : {raiz_dados}")
    print(f"Origem do valor       : {'JARVIS_DADOS' if raiz_dados != STORAGE else 'padrão (storage ao lado do projeto)'}")

    total_arquivos = 0
    total_bytes = 0
    for nome, descricao in AREAS:
        arquivos, bytes_ = medir(raiz_dados / nome)
        total_arquivos += arquivos
        total_bytes += bytes_
        if arquivos:
            print(f"  {nome:<16} {arquivos:>6} arquivos  {mb(bytes_):>10}  ({descricao})")
    print(f"  {'total':<16} {total_arquivos:>6} arquivos  {mb(total_bytes):>10}")
    try:
        uso = shutil.disk_usage(raiz_dados)
        print(f"Disco da pasta atual  : {uso.free / 1e9:.1f} GB livres de {uso.total / 1e9:.1f} GB")
    except OSError:
        pass
    return raiz_dados, total_arquivos, total_bytes


def copiar(origem: Path, destino: Path) -> None:
    destino.mkdir(parents=True, exist_ok=True)
    for nome, descricao in AREAS:
        pasta = origem / nome
        if not pasta.exists():
            continue
        arquivos, bytes_ = medir(pasta)
        print(f"Copiando {nome} ({arquivos} arquivos, {mb(bytes_)}) — {descricao} ...")
        shutil.copytree(pasta, destino / nome, dirs_exist_ok=True)
    for solto in origem.glob("*.json*"):
        if solto.is_file():
            shutil.copy2(solto, destino / solto.name)


def conferir(origem: Path, destino: Path) -> bool:
    ok = True
    for nome, _ in AREAS:
        a, ba = medir(origem / nome)
        b, bb = medir(destino / nome)
        marca = "ok" if (a, ba) == (b, bb) else "DIFERENTE"
        if (a, ba) != (b, bb):
            ok = False
        print(f"  {nome:<16} origem {a:>6}/{mb(ba):>10}  destino {b:>6}/{mb(bb):>10}  {marca}")
    return ok


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Copia os dados do JARVIS para outro disco e aponta o .env para lá.",
    )
    parser.add_argument("--destino", help="Pasta de destino, por exemplo C:\\JARVIS-DADOS")
    parser.add_argument("--ver", action="store_true", help="Só mostra o estado atual.")
    argumentos = parser.parse_args(argv)

    raiz_dados, arquivos, bytes_ = mostrar_estado()
    if argumentos.ver:
        return 0

    if arquivos == 0:
        print("\nNão há dados para mover ainda. Use o JARVIS primeiro ou rode com --ver.")
        return 0

    destino_texto = argumentos.destino
    if not destino_texto:
        if not (sys.stdin and sys.stdin.isatty()):
            print("\nInforme o destino: mover-dados.py --destino C:\\JARVIS-DADOS")
            return 1
        destino_texto = input(
            "\nPasta de destino (ex.: C:\\JARVIS-DADOS): "
        ).strip()
    if not destino_texto:
        print("Nada informado; encerrando sem mexer em nada.")
        return 1

    destino = Path(destino_texto).expanduser()
    if not destino.is_absolute():
        print("O destino precisa ser caminho absoluto, como C:\\JARVIS-DADOS.")
        return 1
    if raiz_dados.resolve() in destino.resolve().parents or destino.resolve() == raiz_dados.resolve():
        print("O destino está dentro da pasta atual; escolha outro disco ou outra pasta.")
        return 1
    if destino.exists() and any(destino.iterdir()):
        print(f"A pasta {destino} já tem arquivos. Use uma pasta nova para não misturar.")
        return 1
    try:
        livre = shutil.disk_usage(destino.parent if destino.parent.exists() else Path(destino.anchor)).free
    except OSError:
        livre = 0
    if livre and livre < bytes_ * 1.1:
        print(f"Espaço insuficiente: precisa de {mb(bytes_)}, há {mb(livre)} livres.")
        return 1

    print(f"\nCopiando {arquivos} arquivos ({mb(bytes_)}) para {destino} ...")
    copiar(raiz_dados, destino)

    print("\nConferindo:")
    if not conferir(raiz_dados, destino):
        print("\nA conferência falhou. Nada foi apagado e o .env NÃO foi alterado.")
        return 2

    caminho_env = gravar_env(str(destino))
    print(f"\nPronto. O .env foi atualizado em {caminho_env}:")
    print(f"  {VARIAVEL}={destino}")
    print("\nAgora:")
    print("  1. feche a API (Ctrl+C na janela do iniciar.py) e suba de novo;")
    print("  2. confira em http://127.0.0.1:8000/api/health e rode a skill armazenamento.status;")
    print(f"  3. só depois de ver tudo funcionando, apague a pasta antiga: {raiz_dados}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
