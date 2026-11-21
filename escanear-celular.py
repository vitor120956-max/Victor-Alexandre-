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


def _perguntar_sintomas() -> list[str]:
    """Pergunta o que a pessoa vê, uma por uma, com número para teclar.

    É a parte que muda a resposta: “a tela trava” e “a tela se mexe sozinha” são
    causas diferentes, e só quem está com o aparelho na mão sabe qual é. Sem
    teclado (ou com `--sem-perguntas`), o scanner segue só com o que mediu.
    """
    from server import diagnostico_celular as dc

    if not sys.stdin.isatty():
        return []
    marcar = ["tela-prende", "frame-lento", "se-mexe-sozinho", "so-para-apagar-tela", "esquenta"]
    print("  Antes de medir, o que você vê no aparelho?")
    print()
    for indice, chave in enumerate(marcar, start=1):
        print(f"    {indice}. {dc.SINTOMAS[chave]['pergunta']}")
    print()
    print("  Digite os números separados por espaço (Enter vazio = não responder).")
    try:
        resposta = input("  > ").strip()
    except (EOFError, KeyboardInterrupt):
        return []
    escolhidos: list[str] = []
    for pedaco in resposta.replace(",", " ").split():
        if pedaco.isdigit() and 1 <= int(pedaco) <= len(marcar):
            chave = marcar[int(pedaco) - 1]
            if chave not in escolhidos:
                escolhidos.append(chave)
    return escolhidos


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Scanner do celular: mede e diz o que está errado.")
    parser.add_argument("serial", nargs="?", default="", help="Serial do `adb devices`; vazio usa o primeiro autorizado.")
    parser.add_argument("--json", action="store_true", help="Imprime o JSON em vez do texto.")
    parser.add_argument("--sem-arquivo", action="store_true", help="Não salva o relatório em storage/diagnosticos.")
    parser.add_argument(
        "--sintomas",
        default="",
        help="Ids separados por vírgula (tela-prende,frame-lento,se-mexe-sozinho,so-para-apagar-tela,esquenta).",
    )
    parser.add_argument("--sem-perguntas", action="store_true", help="Não pergunta nada; só mede.")
    argumentos = parser.parse_args(argv)

    _ambiente()
    sys.path.insert(0, str(RAIZ))

    from server import diagnostico_celular as dc

    marcados = [parte.strip() for parte in argumentos.sintomas.split(",") if parte.strip()]
    if not marcados and not argumentos.sem_perguntas and not argumentos.json:
        marcados = _perguntar_sintomas()

    try:
        relatorio = dc.diagnosticar_por_sintoma(marcados, argumentos.serial)
    except dc.DiagnosticoError as exc:
        print()
        print("  O scanner não conseguiu ler o aparelho:")
        print(f"    {exc}")
        print()
        print("  Nada foi alterado no celular. Resolva o aviso acima e rode de novo.")
        print()
        return 1

    if not marcados:
        relatorio.pop("sintomas", None)

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
