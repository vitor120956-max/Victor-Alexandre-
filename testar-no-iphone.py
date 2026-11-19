#!/usr/bin/env python3
"""Abre o jogo no iPhone: serve o export HTML5 na rede local.

Uso mais fácil (Windows): **arraste a pasta do export WebGL para cima do
`testar-no-iphone.bat`**. Ele guarda o jogo, sobe o servidor e mostra o endereço
que você digita no Safari do iPhone.

Ou, na mão:

    .venv\\Scripts\\python testar-no-iphone.py "C:\\caminho\\MeuJogo-WebGL"
    .venv\\Scripts\\python testar-no-iphone.py meu-jogo.zip
    .venv\\Scripts\\python testar-no-iphone.py --servir Meu-Jogo
    .venv\\Scripts\\python testar-no-iphone.py --lista

O que isto **não** faz: transformar APK em app de iPhone. O iOS só roda app
assinado pela Apple; o caminho de graça é exportar o **mesmo jogo** em HTML5 e
abrir no Safari. Quem exporta é o motor (Unity: WebGL; Godot: Web/HTML5).

Nada sai da pasta do export e a API do JARVIS não é exposta: este processo só
entrega arquivos do jogo.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent


def _ambiente() -> None:
    try:
        from dotenv import load_dotenv
    except Exception:  # noqa: BLE001 - sem python-dotenv, o ambiente ainda vale
        return
    load_dotenv(RAIZ / ".env")


def _raiz_de_arquivos() -> Path:
    """A mesma área que a API usa — para o chat ver o que foi guardado."""
    definida = (os.getenv("JARVIS_FILES_ROOT") or "").strip()
    base = Path(definida).expanduser() if definida else RAIZ / "storage" / "user-files"
    base.mkdir(parents=True, exist_ok=True)
    return base


def _linha(titulo: str = "") -> None:
    print()
    if titulo:
        print(f"  {titulo}")
        print()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Serve o export HTML5 do jogo na rede local para abrir no iPhone.",
    )
    parser.add_argument("export", nargs="?", help="Pasta do export WebGL (ou o .zip dela).")
    parser.add_argument("--servir", metavar="NOME", help="Serve um export que já está guardado.")
    parser.add_argument("--lista", action="store_true", help="Mostra os exports já guardados.")
    parser.add_argument("--nome", help="Nome do jogo na pasta (padrão: o nome da pasta).")
    parser.add_argument("--porta", type=int, default=None, help="Porta (padrão: 8099).")
    args = parser.parse_args(argv)

    _ambiente()
    sys.path.insert(0, str(RAIZ))
    try:
        from server import jogo_web  # noqa: E402
    except Exception as exc:  # noqa: BLE001
        print(f"  Não consegui carregar o servidor do jogo: {exc}")
        print("  Falta alguma biblioteca? Rode o iniciar-jarvis.bat uma vez.")
        return 1

    arquivos = _raiz_de_arquivos()

    if args.lista:
        lista = jogo_web.listar(arquivos)
        _linha("Exports guardados para testar no iPhone:")
        if not lista["jogos"]:
            print("  (nenhum ainda)")
            print()
            print("  Arraste a pasta do export WebGL em cima do testar-no-iphone.bat.")
            return 0
        for item in lista["jogos"]:
            marca = "" if item["temIndex"] else "  [sem index.html — não abre]"
            print(f"  - {item['nome']}  ({item['arquivos']} arquivos, {item['bytes'] / 1e6:.1f} MB){marca}")
        print()
        print("  Para servir um deles:")
        print(f'  .venv\\Scripts\\python testar-no-iphone.py --servir "{lista["jogos"][0]["nome"]}"')
        return 0

    if args.servir:
        base = jogo_web.raiz(arquivos) / args.servir
        if not base.is_dir():
            _linha("Não achei esse export:")
            print(f"  {args.servir}")
            print()
            print("  Veja o que existe com:")
            print("  .venv\\Scripts\\python testar-no-iphone.py --lista")
            return 2
        nome = args.servir
        if not (base / "index.html").is_file():
            _linha("Essa pasta não tem index.html — não é um export HTML5.")
            return 2
    else:
        if not args.export:
            _linha("JARVIS — testar o jogo no iPhone")
            print("  Como usar: arraste a PASTA do export WebGL em cima do")
            print("  testar-no-iphone.bat. O export é o que o motor gera em")
            print("  Unity: Build Settings -> WebGL; Godot: Export -> Web.")
            print()
            print("  O APK não roda no iPhone: o iOS só executa app assinado")
            print("  pela Apple. O mesmo jogo em HTML5 abre no Safari, de graça")
            print("  e pode virar ícone na tela de início (Compartilhar ->")
            print("  Adicionar à Tela de Início), sem App Store e sem custo.")
            print()
            print("  Já tem algum export guardado? Veja:")
            print("  .venv\\Scripts\\python testar-no-iphone.py --lista")
            return 0

        origem = Path(args.export).expanduser()
        if not origem.exists():
            _linha(f"Não achei “{origem}”.")
            print("  Arraste a pasta do export (ou o .zip) em cima do .bat.")
            return 2
        if origem.is_file() and origem.suffix.lower() != ".zip":
            _linha("Isso não é uma pasta de export nem um .zip.")
            print("  No motor, gere o export WebGL/HTML5: é a pasta com o index.html.")
            return 2

        print()
        print(f"  guardando o export: {origem}")
        try:
            info = jogo_web.importar(origem, arquivos, nome=args.nome)
        except jogo_web.JogoWebError as exc:
            _linha("Não deu para guardar o export:")
            print(f"  {exc}")
            return 2
        nome = info["nome"]
        base = Path(info["pasta"])
        print(f"  guardado como “{nome}” ({info['arquivos']} arquivos, {info['bytes'] / 1e6:.1f} MB)")

    porta = args.porta or jogo_web.PORTA_PADRAO
    try:
        servidor = jogo_web.subir(base, porta=porta, registrar=True)
    except jogo_web.JogoWebError as exc:
        _linha(str(exc))
        return 2
    except OSError as exc:
        _linha("Não consegui abrir a porta do servidor do jogo.")
        print(f"  {exc}")
        print()
        print(f"  Se a porta {porta} estiver ocupada, tente outra:")
        print(f"  .venv\\Scripts\\python testar-no-iphone.py --servir {nome} --porta {porta + 1}")
        return 1

    print(jogo_web.instrucoes(nome, porta=porta))
    print("  Se o iPhone não abrir: deixe esta janela aberta e veja se apareceu")
    print("  algum pedido aqui embaixo. Nenhum pedido = o iPhone não chegou no PC.")
    print()
    try:
        servidor.serve_forever(poll_interval=0.5)
    except KeyboardInterrupt:  # pragma: no cover - só quando alguém aperta
        print()
        print("  Servidor do jogo encerrado.")
    finally:
        servidor.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
