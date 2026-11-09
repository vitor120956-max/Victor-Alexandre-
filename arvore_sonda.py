#!/usr/bin/env python3
"""Sonda de leitura da árvore de acessibilidade — roda **fora** da API.

Por que um arquivo separado: ler a árvore significa chamar código de outro
programa por COM. Se esse programa travar, quem trava é este processo — que é
descartável — e não o JARVIS no meio da conversa.

Uso (Windows):

    py arvore_sonda.py                      # janela em foco, em texto
    py arvore_sonda.py --janelas            # o que está aberto
    py arvore_sonda.py --alvo chrome        # janela cujo título tem "chrome"
    py arvore_sonda.py --json --limite 200  # JSON para o JARVIS

Só leitura: nada é clicado, digitado ou movido.
"""
from __future__ import annotations

import argparse
import json
import sys


def _falhar(mensagem: str, codigo: int = 1) -> int:
    print(json.dumps({"erro": mensagem}, ensure_ascii=False))
    return codigo


def principal(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Lê a árvore de acessibilidade de uma janela (somente leitura).")
    parser.add_argument("--alvo", default="foco", help="“foco” (padrão) ou parte do título do processo/janela.")
    parser.add_argument("--profundidade", type=int, default=6, help="Até onde descer (1 a 14).")
    parser.add_argument("--limite", type=int, default=600, help="Máximo de elementos lidos (1 a 3000).")
    parser.add_argument("--json", action="store_true", help="Devolve JSON cru para o JARVIS.")
    parser.add_argument("--janelas", action="store_true", help="Só lista as janelas abertas.")
    args = parser.parse_args(argv)

    if sys.platform != "win32":
        return _falhar("a leitura da árvore só existe no Windows hoje.")

    try:
        from server import arvore_windows as leitor
    except Exception as exc:  # noqa: BLE001 - qualquer falha de import é motivo de saída limpa
        return _falhar(f"não consegui carregar o leitor do Windows ({type(exc).__name__}).")

    if args.janelas:
        lista = leitor.janelas()
        if args.json:
            print(json.dumps({"janelas": lista}, ensure_ascii=False))
        else:
            for item in lista:
                print(f"{item.get('processo') or '?':24} {item.get('titulo') or '(sem título)'}")
        return 0

    from server import arvore

    try:
        janela = arvore._escolher_janela(leitor, args.alvo)  # noqa: SLF001 - a mesma escolha da API
    except arvore.ArvoreError as exc:
        return _falhar(str(exc))

    try:
        bruto = leitor.ler_janela(
            janela["handle"],
            max(1, min(args.profundidade, arvore.PROFUNDIDADE_MAX)),
            max(1, min(args.limite, arvore.LIMITE_MAX)),
        )
    except Exception as exc:  # noqa: BLE001 - COM de terceiros: nunca vazar stack
        return _falhar(f"a leitura da janela falhou ({type(exc).__name__}).")
    bruto.setdefault("janela", janela)

    if args.json:
        print(json.dumps(bruto, ensure_ascii=False))
        return 0

    montada = arvore.montar(bruto, args.profundidade, args.limite)
    print(arvore.resumo(montada))
    print()
    print(arvore.desenhar(montada.get("arvore")))
    return 0


if __name__ == "__main__":
    raise SystemExit(principal())
