#!/usr/bin/env python3
"""Analisa o APK do seu jogo e diz o que melhorar — no console, sem abrir a tela.

Uso mais fácil (Windows): **arraste o APK para cima do `analisar-jogo.bat`**.
Ele copia o arquivo para a pasta de jogos do JARVIS e roda isto aqui.

Ou, na mão:

    .venv\\Scripts\\python analisar-jogo.py "C:\\caminho\\meu-jogo.apk"
    .venv\\Scripts\\python analisar-jogo.py --lista

O que ele lê: o `AndroidManifest.xml` binário (pacote, versão, SDKs, permissões,
flags), o motor (Unity, Godot, Unreal…), as arquiteturas embaladas, onde o
tamanho está e a assinatura. Nada é descompactado em disco, nada é executado e
nada sai da sua máquina.
"""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent


def _ambiente() -> None:
    try:
        from dotenv import load_dotenv
    except Exception:  # noqa: BLE001 - sem python-dotenv, o ambiente ainda vale
        return
    load_dotenv(RAIZ / ".env")


def _pasta_de_jogos() -> Path:
    """A mesma pasta que a API usa — para o chat achar o que o .bat salvou."""
    import os

    definida = (os.getenv("JARVIS_FILES_ROOT") or "").strip()
    base = Path(definida).expanduser() if definida else RAIZ / "storage" / "user-files"
    pasta = base / "jogos"
    pasta.mkdir(parents=True, exist_ok=True)
    return pasta


def _copia_para_jogos(origem: Path) -> Path:
    """Copia o APK para a pasta do JARVIS, sem sobrescrever às cegas."""
    destino = _pasta_de_jogos() / origem.name
    if destino.exists() and destino.stat().st_size == origem.stat().st_size:
        print(f"  (o APK já estava na pasta: {destino})")
        return destino
    if destino.exists():
        contador = 1
        while True:
            alternativo = destino.with_name(f"{destino.stem}-{contador}{destino.suffix}")
            if not alternativo.exists():
                destino = alternativo
                break
            contador += 1
    print(f"  copiando para a pasta de jogos do JARVIS: {destino}")
    shutil.copy2(origem, destino)
    return destino


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Analisa o APK do jogo e diz o que melhorar.")
    parser.add_argument("arquivo", nargs="?", help="Caminho do APK (ou arraste sobre o .bat).")
    parser.add_argument("--lista", action="store_true", help="Mostra os jogos já enviados.")
    args, sobras = parser.parse_known_args(argv)
    if sobras and not args.arquivo:
        print(f"  Esta cópia não conhece: {' '.join(sobras)}")
        print("  Rode o atualizar.bat e tente de novo.")
        return 2

    _ambiente()
    sys.path.insert(0, str(RAIZ))
    from server import jogo  # noqa: E402

    if args.lista or not args.arquivo:
        lista = jogo.listar(_pasta_de_jogos().parent)
        print("  Jogos já na pasta do JARVIS:")
        if not lista["jogos"]:
            print("    (nenhum ainda)")
            print()
            print("  Arraste o APK para cima deste arquivo, ou rode:")
            print('    .venv\\Scripts\\python analisar-jogo.py "C:\\caminho\\meu-jogo.apk"')
            return 0
        for item in lista["jogos"]:
            print(f"    {item['nome']} — {item['bytes'] / 1e6:.1f} MB".replace(".", ","))
        print()
        print("  Para analisar um deles, mande no JARVIS:  analisar jogo <nome>")
        return 0

    origem = Path(args.arquivo).expanduser()
    if not origem.is_file():
        print(f"  Não achei o arquivo: {origem}")
        print("  Dica: arraste o APK para cima do analisar-jogo.bat, sem digitar caminho.")
        return 1
    if origem.suffix.lower() not in jogo.EXTENSOES:
        print(f"  “{origem.name}” não é APK. Envie o arquivo que termina em .apk.")
        return 1

    print(f"  JARVIS — analisar o jogo {origem.name}")
    print()
    destino = _copia_para_jogos(origem)
    try:
        relatorio = jogo.relatar(destino)
    except jogo.JogoError as exc:
        print(f"  NÃO deu para analisar: {exc}")
        return 1
    print()
    print(relatorio["texto"])
    print()
    print("  Para pedir de novo pelo chat, o arquivo já está na pasta:")
    print(f"    analisar jogo {destino.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
