#!/usr/bin/env python3
"""Passa o scanner no celular e mostra o resultado no console (0.92.3).

Uso mais fácil (Windows): **dê dois cliques em `escanear-celular.bat`**.

Ou, na mão:

    .venv\\Scripts\\python escanear-celular.py            # primeiro aparelho autorizado
    .venv\\Scripts\\python escanear-celular.py ABC123     # serial específico
    .venv\\Scripts\\python escanear-celular.py --json     # para guardar/copiar

O que ele faz: lê o aparelho por `adb` (**só leitura**), mede armazenamento,
memória, bateria, temperatura, patch de segurança, processos, travamentos e
ajustes, e transforma isso em **achados** — cada um com a medida, a causa, o
passo a passo e o limite. Salva o mesmo relatório em
`storage/diagnosticos/<serial>-<data>.json` para o dono mandar junto ou comparar
depois.

O que ele **não** faz: não desinstala, não limpa cache, não muda ajuste, não
reinicia e não usa root. Quem mexe no aparelho é você, na tela dele.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

RAIZ = Path(__file__).resolve().parent


def _ambiente() -> None:
    try:
        from dotenv import load_dotenv
    except Exception:  # noqa: BLE001 - sem python-dotenv, o ambiente ainda vale
        return
    load_dotenv(RAIZ / ".env")


def _pasta() -> Path:
    import os

    base = os.getenv("JARVIS_FILES_ROOT") or os.getenv("JARVIS_DATA_ROOT")
    return Path(base) / "diagnosticos" if base else RAIZ / "storage" / "diagnosticos"


def _salvar(relatorio: dict) -> Path:
    pasta = _pasta()
    pasta.mkdir(parents=True, exist_ok=True)
    carimbo = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    serial = (relatorio.get("serial") or "aparelho").replace("/", "-").replace(":", "-")
    destino = pasta / f"{serial}-{carimbo}.json"
    destino.write_text(json.dumps(relatorio, ensure_ascii=False, indent=2), encoding="utf-8")
    return destino


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Scanner do celular: mede e diz o que está errado.")
    parser.add_argument("serial", nargs="?", default="", help="Serial do `adb devices`; vazio usa o primeiro autorizado.")
    parser.add_argument("--json", action="store_true", help="Imprime o JSON em vez do texto.")
    parser.add_argument("--sem-arquivo", action="store_true", help="Não salva o relatório em storage/diagnosticos.")
    argumentos = parser.parse_args(argv)

    _ambiente()
    sys.path.insert(0, str(RAIZ))

    from server import diagnostico_celular as dc

    try:
        relatorio = dc.diagnosticar(argumentos.serial)
    except dc.DiagnosticoError as exc:
        print()
        print("  O scanner não conseguiu ler o aparelho:")
        print(f"    {exc}")
        print()
        print("  Nada foi alterado no celular. Resolva o aviso acima e rode de novo.")
        print()
        return 1

    if argumentos.json:
        print(json.dumps(relatorio, ensure_ascii=False, indent=2))
    else:
        print(dc.em_texto(relatorio))

    if not argumentos.sem_arquivo:
        try:
            destino = _salvar(relatorio)
            print(f"  Relatório salvo em: {destino}")
            print("  Mande este arquivo se quiser comparar depois — ele não tem nada pessoal.")
            print()
        except OSError as exc:
            print(f"  (Não consegui salvar o relatório: {exc})")
            print()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
