#!/usr/bin/env python3
"""Analisa o APK do seu jogo e diz o que melhorar — no console, sem abrir a tela.

Uso mais fácil (Windows): **arraste o APK para cima do `analisar-jogo.bat`**.
Ele copia o arquivo para a pasta de jogos do JARVIS e roda isto aqui.

Ou, na mão:

    .venv\\Scripts\\python analisar-jogo.py "C:\\caminho\\meu-jogo.apk"
    .venv\\Scripts\\python analisar-jogo.py --lista

Pode arrastar **dois (ou mais) de uma vez**: cada APK ganha a **própria pasta**
em `storage/user-files/jogos/<nome-do-jogo>/`, com o APK, o `analise.txt` e o
`analise.json` juntos — um jogo por pasta, para dois testes não se misturarem.

O que ele lê: o `AndroidManifest.xml` binário (pacote, versão, SDKs, permissões,
flags), o motor (Unity, Godot, Unreal…), as arquiteturas embaladas, onde o
tamanho está e a assinatura. Nada é descompactado em disco, nada é executado e
nada sai da sua máquina.
"""
from __future__ import annotations

import argparse
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Analisa o APK do jogo e diz o que melhorar.")
    # 0.91.41 — dois APKs de uma vez: o `%~1` do .bat entregava só o primeiro e
    # o segundo era ignorado em silêncio. Agora entram todos os arrastados.
    parser.add_argument(
        "arquivos",
        nargs="*",
        help="Um ou mais APKs (arraste todos de uma vez sobre o .bat).",
    )
    parser.add_argument("--lista", action="store_true", help="Mostra os jogos já enviados.")
    parser.add_argument(
        "--comparar",
        action="store_true",
        help="Compara os dois primeiros (antes/depois do mesmo jogo).",
    )
    args, sobras = parser.parse_known_args(argv)
    if sobras and not args.arquivos:
        print(f"  Esta cópia não conhece: {' '.join(sobras)}")
        print("  Rode o atualizar.bat e tente de novo.")
        return 2

    _ambiente()
    sys.path.insert(0, str(RAIZ))
    from server import jogo  # noqa: E402

    if args.lista or not args.arquivos:
        lista = jogo.listar(_pasta_de_jogos().parent)
        print("  Jogos já na pasta do JARVIS (um por pasta):")
        if not lista["jogos"]:
            print("    (nenhum ainda)")
            print()
            print("  Arraste o APK (ou dois) para cima deste arquivo, ou rode:")
            print('    .venv\\Scripts\\python analisar-jogo.py "C:\\caminho\\meu-jogo.apk"')
            return 0
        # O nome do arquivo NÃO passa por troca de ponto por vírgula: antes a
        # formatação de número pegava a linha toda e saía “build-teste-1,apk”.
        for parte in lista["partes"]:
            marca = "analisado" if parte["analisado"] else "sem análise ainda"
            tamanho = f"{parte['bytes'] / 1e6:.1f} MB".replace(".", ",")
            # 0.91.45 — a pasta pode ter só OBB (o APK ainda não chegou):
            # `apks[0]` estourava o índice e o .bat morria antes de listar.
            dentro = ", ".join(parte["apks"] + [f"OBB: {nome}" for nome in parte.get("obbs", [])])
            print(f"    {parte['nome']}/ — {dentro or '(vazia)'} — {tamanho} ({marca})")
        soltos = [item for item in lista["jogos"] if not item["parte"]]
        for item in soltos:
            tamanho = f"{item['bytes'] / 1e6:.1f} MB".replace(".", ",")
            print(f"    {item['nome']} — {tamanho} (solto, formato antigo)")
        print()
        print("  Para analisar um deles, mande no JARVIS:  analisar jogo <pasta>/<arquivo>.apk")
        if len(lista["partes"]) > 1:
            print("  Ou todos de uma vez:  analisar os dois jogos")
        return 0

    origens: list[Path] = []
    for bruto in args.arquivos:
        origem = Path(bruto).expanduser()
        if not origem.is_file():
            print(f"  Não achei o arquivo: {origem}")
            print("  Dica: arraste o APK para cima do analisar-jogo.bat, sem digitar caminho.")
            return 1
        if origem.suffix.lower() not in jogo.EXTENSOES:
            print(f"  “{origem.name}” não é APK. Envie o arquivo que termina em .apk.")
            return 1
        origens.append(origem)

    if len(origens) > 1:
        print(f"  JARVIS — analisar {len(origens)} APKs, um de cada vez")
    else:
        print(f"  JARVIS — analisar o jogo {origens[0].name}")
    print()

    resultados: list[dict] = []
    falhas = 0
    for indice, origem in enumerate(origens, start=1):
        if len(origens) > 1:
            print(f"  [{indice}/{len(origens)}] {origem.name}")
        try:
            guardado = jogo.guardar(origem, _pasta_de_jogos().parent)
        except (jogo.JogoError, OSError) as exc:
            print(f"  NÃO deu para analisar: {exc}")
            falhas += 1
            continue
        relatorio = guardado["relatorio"]
        print()
        print(relatorio["texto"])
        print()
        onde = "já estava guardado em" if not guardado["novo"] else "guardado em"
        print(f"  {onde}: {guardado['pasta']}")
        print(f"    {guardado['apk']} · analise.txt · analise.json")
        print()
        resultados.append(guardado)

    if not resultados:
        return 1

    if args.comparar and len(resultados) >= 2:
        print()
        comparacao = jogo.comparar(
            Path(resultados[0]["pasta"]) / resultados[0]["apk"],
            Path(resultados[1]["pasta"]) / resultados[1]["apk"],
        )
        comparacao["texto"] = jogo.texto_comparacao(comparacao)
        print(comparacao["texto"])
        print()
        destino = jogo.guardar_comparacao(_pasta_de_jogos().parent, comparacao)
        print(f"  comparação guardada em: {destino}")
        print()

    if len(resultados) > 1:
        print("  Cada APK tem a pasta dele. Para pedir de novo pelo chat:")
        for item in resultados:
            print(f"    analisar jogo {item['parte']}/{item['apk']}")
        print("  Ou os dois de uma vez:  analisar os dois jogos")
    else:
        item = resultados[0]
        print("  Para pedir de novo pelo chat, a pasta e o arquivo são estes:")
        print(f"    analisar jogo {item['parte']}/{item['apk']}")
    print()
    return 1 if falhas else 0


if __name__ == "__main__":
    raise SystemExit(main())
