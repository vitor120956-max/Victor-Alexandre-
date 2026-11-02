#!/usr/bin/env python3
"""Gera o `manifest.json` do release — a lista que permite atualização delta.

Rode **antes de cada commit de versão**. O manifesto é o que o JARVIS do usuário
baixa (uns 50 KB) para descobrir quais arquivos mudaram, em vez de baixar o zip
inteiro (~3,5 MB) e copiar 460 arquivos.

    .venv\\Scripts\\python scripts\\gerar-manifesto.py
    .venv/bin/python scripts/gerar-manifesto.py --conferir

`--conferir` não escreve: só diz se o manifesto em disco corresponde aos arquivos
de agora (é o que o teste da suíte faz).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from server import atualizacao  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Gera (ou confere) o manifest.json.")
    parser.add_argument("--conferir", action="store_true", help="Não escreve: só compara com o disco.")
    args = parser.parse_args(argv)

    novo = atualizacao.gerar_manifesto(raiz=RAIZ)
    alvo = RAIZ / atualizacao.NOME_MANIFESTO
    quantos = len(novo["arquivos"])
    bytes_estimados = len(json.dumps(novo, ensure_ascii=False).encode("utf-8"))

    if args.conferir:
        try:
            atual = json.loads(alvo.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            print("manifest.json ausente ou ilegível. Rode sem --conferir.")
            return 1
        if atual.get("arquivos") != novo["arquivos"]:
            diferentes = [
                caminho for caminho in set(atual.get("arquivos") or {}) | set(novo["arquivos"])
                if (atual.get("arquivos") or {}).get(caminho) != novo["arquivos"].get(caminho)
            ]
            print(f"manifest.json está velho: {len(diferentes)} arquivo(s) fora de sincronia.")
            for caminho in sorted(diferentes)[:10]:
                print(f"  - {caminho}")
            return 2
        print(f"manifest.json em dia: {quantos} arquivos.")
        return 0

    alvo.write_text(json.dumps(novo, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"manifest.json escrito: {quantos} arquivos, {bytes_estimados / 1024:.0f} KB, versão {novo['versao']}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
