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
    .venv\\Scripts\\python mover-dados.py --drive         (leva só livros e repos
                                                           para o Google Drive)

`--drive` existe porque o Drive é ótimo para arquivo grande e parado (livro,
repositório) e péssimo para arquivo que muda a cada resposta (`historico.json`,
`fila.json`). Ele move **só** `biblioteca` e `repos`, grava `JARVIS_BIBLIOTECA`
e `JARVIS_REPOS` no `.env`, e deixa o estado do agente no disco local.
"""
from __future__ import annotations

import argparse
import os
import re
import shutil
import sys
from pathlib import Path

from server import dados as dados_mod

RAIZ = Path(__file__).resolve().parent
STORAGE = RAIZ / "storage"
ENV = RAIZ / ".env"
VARIAVEL = "JARVIS_DADOS"
VARIAVEL_BIBLIOTECA = "JARVIS_BIBLIOTECA"
VARIAVEL_REPOS = "JARVIS_REPOS"
AREAS_DO_DRIVE = ("biblioteca", "repos")

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
    return gravar_env_varios({VARIAVEL: valor})


def gravar_env_varios(pares: dict[str, str]) -> Path:
    base = ENV if ENV.is_file() else RAIZ / ".env.example"
    texto = base.read_text(encoding="utf-8") if base.is_file() else ""
    atualizado = texto
    for nome, valor in pares.items():
        atualizado = definir(atualizado, nome, valor)
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


def copiar(
    origem: Path,
    destino: Path,
    nomes: tuple[str, ...] | None = None,
    soltos: bool = True,
) -> None:
    destino.mkdir(parents=True, exist_ok=True)
    for nome, descricao in AREAS:
        if nomes is not None and nome not in nomes:
            continue
        pasta = origem / nome
        if not pasta.exists():
            continue
        arquivos, bytes_ = medir(pasta)
        print(f"Copiando {nome} ({arquivos} arquivos, {mb(bytes_)}) — {descricao} ...")
        shutil.copytree(pasta, destino / nome, dirs_exist_ok=True)
    if not soltos:
        return
    for solto in origem.glob("*.json*"):
        if solto.is_file():
            shutil.copy2(solto, destino / solto.name)


def conferir(origem: Path, destino: Path, nomes: tuple[str, ...] | None = None) -> bool:
    ok = True
    for nome, _ in AREAS:
        if nomes is not None and nome not in nomes:
            continue
        a, ba = medir(origem / nome)
        b, bb = medir(destino / nome)
        marca = "ok" if (a, ba) == (b, bb) else "DIFERENTE"
        if (a, ba) != (b, bb):
            ok = False
        print(f"  {nome:<16} origem {a:>6}/{mb(ba):>10}  destino {b:>6}/{mb(bb):>10}  {marca}")
    return ok


def copiar_uma(origem: Path, destino: Path) -> None:
    arquivos, bytes_ = medir(origem)
    print(f"Copiando {origem.name} ({arquivos} arquivos, {mb(bytes_)}) ...")
    destino.mkdir(parents=True, exist_ok=True)
    shutil.copytree(origem, destino, dirs_exist_ok=True)


def conferir_uma(origem: Path, destino: Path) -> bool:
    a, ba = medir(origem)
    b, bb = medir(destino)
    print(f"  origem {a:>6}/{mb(ba):>10}  destino {b:>6}/{mb(bb):>10}  {'ok' if (a, ba) == (b, bb) else 'DIFERENTE'}")
    return (a, ba) == (b, bb)


def pasta_da_area(raiz_dados: Path, nome: str) -> Path:
    """Pasta que o JARVIS usa hoje para a área, respeitando o .env."""
    variavel = {"biblioteca": VARIAVEL_BIBLIOTECA, "repos": VARIAVEL_REPOS}[nome]
    valor = os.environ.get(variavel, "").strip()
    if not valor and ENV.is_file():
        valor = (ler_valor(ENV.read_text(encoding="utf-8", errors="replace"), variavel) or "").strip()
    return Path(valor).expanduser() if valor else raiz_dados / nome


def mover_para_drive(destino_drive: Path, origens: dict[str, Path]) -> int:
    """Leva só biblioteca e repos para o Drive e aponta o .env para lá.

    O estado do agente (historico.json, fila.json, skills.json, host-*) fica
    onde está: esses arquivos mudam a cada resposta e, no Drive, cada gravação
    vira uma sincronização.
    """
    print(f"\nDrive escolhido: {destino_drive}")
    if not destino_drive.is_dir():
        print("Essa pasta não existe. Confira o caminho ou rode com --drive sem argumento.")
        return 1

    base = destino_drive / "JARVIS-DADOS"
    try:
        base.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        print(f"Não consegui criar {base}: {exc}")
        return 1

    mudancas: dict[str, str] = {}
    variaveis = {"biblioteca": VARIAVEL_BIBLIOTECA, "repos": VARIAVEL_REPOS}
    for nome in AREAS_DO_DRIVE:
        origem = origens[nome]
        alvo = base / nome
        try:
            ja_esta = origem.resolve() == alvo.resolve()
        except OSError:
            ja_esta = False
        if ja_esta:
            print(f"\n{nome}: já está no Drive — nada a copiar.")
            mudancas[variaveis[nome]] = str(alvo)
            continue
        arquivos, bytes_ = medir(origem)
        if arquivos == 0:
            print(f"\n{nome}: nada para copiar ainda — só vou apontar a variável.")
        else:
            livre = shutil.disk_usage(destino_drive).free
            if livre < bytes_ * 1.1:
                print(f"\nSem espaço no Drive: precisa de {mb(bytes_)}, há {mb(livre)} livres.")
                print("Nada foi copiado e o .env NÃO foi alterado.")
                return 1
            print(f"\nCopiando {nome}: {arquivos} arquivos, {mb(bytes_)} ...")
            copiar_uma(origem, alvo)
            print("Conferindo:")
            if not conferir_uma(origem, alvo):
                print("\nA conferência falhou. Nada foi apagado e o .env NÃO foi alterado.")
                return 2
        mudancas[variaveis[nome]] = str(alvo)

    caminho_env = gravar_env_varios(mudancas)
    print(f"\nPronto. O .env foi atualizado em {caminho_env}:")
    for nome, valor in mudancas.items():
        print(f"  {nome}={valor}")
    print("\nO que NÃO foi para o Drive (de propósito): historico.json, fila.json,")
    print("skills.json e host-*.json — eles mudam toda hora e fariam o Drive")
    print("sincronizar sem parar.")
    print("\nAgora:")
    print("  1. feche a janela da API no X e suba de novo;")
    print("  2. na interface, rode a skill dados.status e confira os caminhos;")
    print("  3. deixe o Drive em 'Fazer backup' (espelho) só dessa pasta, ou")
    print("     pause a sincronização enquanto o JARVIS estiver indexando livros;")
    print("  4. só depois de ver tudo funcionando, apague as pastas antigas:")
    for nome in AREAS_DO_DRIVE:
        print(f"     {origens[nome]}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Copia os dados do JARVIS para outro disco e aponta o .env para lá.",
    )
    parser.add_argument("--destino", help="Pasta de destino, por exemplo C:\\JARVIS-DADOS")
    parser.add_argument("--ver", action="store_true", help="Só mostra o estado atual.")
    parser.add_argument(
        "--drive",
        nargs="?",
        const="",
        default=None,
        metavar="PASTA",
        help="Leva só biblioteca e repos para o Google Drive (detecta a pasta se omitir).",
    )
    argumentos = parser.parse_args(argv)

    raiz_dados, arquivos, bytes_ = mostrar_estado()
    if argumentos.ver:
        return 0

    if argumentos.drive is not None:
        texto = (argumentos.drive or "").strip()
        if not texto and ENV.is_file():
            texto = (ler_valor(ENV.read_text(encoding="utf-8", errors="replace"), "JARVIS_DRIVE") or "").strip()
        drive = Path(texto).expanduser() if texto else dados_mod.detectar_drive()
        if drive is None:
            print("\nNão achei a pasta do Google Drive.")
            print("Informe na mão: mover-dados.py --drive \"G:\\Meu Drive\"")
            print("Se ainda não instalou, veja docs/GOOGLE-DRIVE.md.")
            return 1
        origens = {}
        for nome in AREAS_DO_DRIVE:
            atual = pasta_da_area(raiz_dados, nome)
            origens[nome] = atual
            print(f"Origem de {nome}: {atual}")
        return mover_para_drive(Path(drive), origens)

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
    print("  1. feche a janela da API no X e suba de novo;")
    print("  2. confira em http://127.0.0.1:8000/api/health e rode a skill armazenamento.status;")
    print(f"  3. só depois de ver tudo funcionando, apague a pasta antiga: {raiz_dados}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
