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

    try:
        from server.app import pasta_da_interface  # noqa: PLC0415
    except Exception as exc:  # pragma: no cover - falha de ambiente
        print(f"Não consegui importar o servidor: {exc}", file=sys.stderr)
        return 1

    interface = pasta_da_interface()
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

    uvicorn.run("server.app:create_app", factory=True, host=args.host, port=args.porta, reload=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(principal())
