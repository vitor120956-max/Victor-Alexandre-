#!/usr/bin/env python3
"""Sobe o JARVIS sem Node e sem npm — só com Python.

Serve a API e a interface compilada (pasta `web-dist/`, versionada no repositório)
na mesma porta. É o caminho para quem roda de um pendrive lento e não quer
esperar o `npm install`.

Uso:
    py iniciar.py                 # porta 8000
    py iniciar.py --porta 8080
    py iniciar.py --host 0.0.0.0  # expõe na rede local

Nada aqui instala, baixa ou altera arquivo: só sobe o servidor.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
VENV = RAIZ / ".venv"
if (VENV / "Scripts" / "python.exe").is_file() or (VENV / "bin" / "python").is_file():
    # Usa o interpretador do .venv quando este script for chamado com outro Python.
    candidato = VENV / "Scripts" / "python.exe" if os.name == "nt" else VENV / "bin" / "python"
    if Path(sys.executable).resolve() != candidato.resolve() and os.environ.get("JARVIS_SEM_VENV") != "1":
        os.environ["JARVIS_SEM_VENV"] = "1"
        os.execv(str(candidato), [str(candidato), str(Path(__file__).resolve()), *sys.argv[1:]])


def _pasta_da_interface() -> Path | None:
    """`dist` (build local) ou `web-dist` (a interface que vem no zip)."""
    for nome in ("dist", "web-dist"):
        candidata = RAIZ / nome
        if (candidata / "index.html").is_file():
            return candidata
    return None


def _ja_esta_rodando(host: str, porta: int) -> bool:
    """Já existe um JARVIS nessa porta? (evita confundir com 'porta ocupada')."""
    import json  # noqa: PLC0415
    from urllib.error import URLError  # noqa: PLC0415
    from urllib.request import urlopen  # noqa: PLC0415

    alvo = "127.0.0.1" if host in {"0.0.0.0", "::"} else host
    try:
        with urlopen(f"http://{alvo}:{porta}/api/health", timeout=2) as resposta:
            dados = json.loads(resposta.read().decode("utf-8", "replace") or "{}")
    except (URLError, OSError, ValueError):
        return False
    return dados.get("service") == "jarvis-python-api"


def _porta_livre(host: str, porta: int) -> bool:
    import socket  # noqa: PLC0415

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sonda:
        sonda.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sonda.bind(("127.0.0.1" if host in {"0.0.0.0", "::"} else host, porta))
        except OSError:
            return False
    return True


def principal() -> int:
    parser = argparse.ArgumentParser(description="Sobe o JARVIS com Python apenas (sem Node).")
    parser.add_argument("--host", default="127.0.0.1", help="Endereço de escuta (padrão: 127.0.0.1).")
    parser.add_argument("--porta", "--port", dest="porta", type=int, default=8000, help="Porta (padrão: 8000).")
    args = parser.parse_args()

    try:
        import uvicorn  # noqa: PLC0415
    except ImportError:
        pip = r".venv\Scripts\pip" if os.name == "nt" else ".venv/bin/pip"
        print("Faltam as bibliotecas Python. Rode:", file=sys.stderr)
        print("  py -m venv .venv", file=sys.stderr)
        print(f"  {pip} install -r requirements.txt", file=sys.stderr)
        print("", file=sys.stderr)
        print("Se o pip parou com 'Microsoft Visual C++ 14.0 or greater is required':", file=sys.stderr)
        print("  quase sempre é o PyYAML, que entra pelo uvicorn[standard] e não tem", file=sys.stderr)
        print("  wheel para Python 3.15 no Windows. O requirements.txt deste projeto", file=sys.stderr)
        print("  não pede [standard]; se o seu pede, troque a linha do uvicorn por", file=sys.stderr)
        print("  uvicorn>=0.34,<1.0 . Alternativa manual, sem compilar nada:", file=sys.stderr)
        print(f"  {pip} install fastapi uvicorn httpx pydantic python-dotenv", file=sys.stderr)
        print(f"  {pip} install python-docx openpyxl python-pptx pypdf reportlab python-multipart", file=sys.stderr)
        return 1

    if _ja_esta_rodando(args.host, args.porta):
        print()
        print(f"  Já existe uma API respondendo em http://127.0.0.1:{args.porta}")
        print("  Não precisa subir outra: abra o endereço no navegador.")
        print()
        print("  Se essa outra for de uma versão antiga, feche a janela dela")
        print("  (o X) e rode este comando de novo.")
        return 0

    if not _porta_livre(args.host, args.porta):
        print()
        print(f"  A porta {args.porta} está ocupada por outro programa (não é o JARVIS).")
        print(f"  Suba em outra porta:  .venv\\Scripts\\python iniciar.py --porta {args.porta + 1}")
        print("  Depois abra o endereço que aparecer aqui embaixo.")
        return 1

    # A pasta da interface é procurada sem importar o servidor: importar
    # `server.app` executava `create_app()` no import, e a API subia duas vezes
    # (banner duplicado e o dobro de trabalho num pendrive lento).
    interface = _pasta_da_interface()
    onde = interface.name if interface else "ausente"
    print()
    print("JARVIS — modo sem Node")
    print(f"  interface: {onde}")
    print(f"  endereço:  http://{args.host if args.host != '0.0.0.0' else '127.0.0.1'}:{args.porta}")
    print(f"  API:       http://127.0.0.1:{args.porta}/api/health")
    if interface is None:
        print("  AVISO: nenhuma interface compilada encontrada — a API responde, a tela não.")
    print("  Para parar: feche esta janela no X")
    print()

    # "server.app:app" (e não a factory) importa o módulo uma vez e usa a
    # instância que ele já criou. Com a factory, o módulo era importado e
    # `create_app()` rodava de novo: banner duplicado e o dobro do trabalho.
    uvicorn.run("server.app:app", host=args.host, port=args.porta, reload=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(principal())
