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
    # 0.94.2 — o nome do arquivo levava o **serial do aparelho** (RXCW400ZV3F),
    # que é identificador do dono. O modelo basta para reconhecer o relatório.
    modelo = (relatorio.get("titulo") or "").split("·")[0].strip() or "aparelho"
    seguro = "".join(c if c.isalnum() or c in "-_" else "-" for c in modelo)[:40]
    destino = pasta / f"{seguro}-{carimbo}.json"
    destino.write_text(json.dumps(relatorio, ensure_ascii=False, indent=2), encoding="utf-8")
    return destino


def _empacotar(relatorio: dict, destino_relatorio: Path) -> Path:
    """O `.zip` das leituras cruas, ao lado do `relatorio.json`."""
    from server import varredura

    alvo = destino_relatorio.with_suffix(".zip")
    return varredura.empacotar_leituras(relatorio, alvo)


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
    parser.add_argument(
        "--refazer",
        metavar="ARQUIVO.zip",
        default="",
        help=(
            "Não toca no celular: refaz o relatório a partir do .zip do `--pacote`. "
            "É assim que um defeito é reproduzido sem ter o aparelho na mão."
        ),
    )
    parser.add_argument(
        "--pacote",
        action="store_true",
        help=(
            "Guarda também as leituras cruas do `adb`, num .zip que NÃO tem nada pessoal "
            "(sem nome, sem conta, sem arquivo de mídia). É o que permite refazer o "
            "diagnóstico exato no PC de quem escreve o JARVIS, sem pedir outro print."
        ),
    )
    parser.add_argument(
        "--completo",
        action="store_true",
        help="Em vez do scanner: a passagem completa (anatomia + scanner + pastas e partições).",
    )
    argumentos = parser.parse_args(argv)

    _ambiente()
    sys.path.insert(0, str(RAIZ))

    from server import diagnostico_celular as dc

    if argumentos.refazer:
        from server import varredura

        try:
            refeito = varredura.refazer_de_pacote(argumentos.refazer)
        except (OSError, ValueError) as exc:
            print()
            print("  Não consegui refazer a partir deste arquivo:")
            print(f"    {exc}")
            print()
            return 1
        if argumentos.json:
            print(json.dumps(refeito, ensure_ascii=False, indent=2))
        else:
            print(varredura.em_texto(refeito))
        return 0

    if argumentos.completo:
        from server import varredura

        # 0.92.9 — a varredura completa também pergunta o que o dono vê. Era o
        # único caminho que não perguntava, e justamente o do duplo clique: a
        # fila de suspeitas da 0.92.4 ficava de fora do caminho mais fácil.
        marcados_completo = [
            parte.strip() for parte in (argumentos.sintomas or "").split(",") if parte.strip()
        ]
        if not marcados_completo and not argumentos.sem_perguntas and not argumentos.json:
            marcados_completo = _perguntar_sintomas()

        try:
            relatorio_completo = varredura.varrer(
                argumentos.serial, sintomas=marcados_completo
            )
        except varredura.VarreduraError as exc:
            print()
            print("  A varredura não conseguiu ler o aparelho:")
            print(f"    {exc}")
            print()
            return 1
        publico = varredura.so_publico(relatorio_completo)
        if argumentos.json:
            print(json.dumps(publico, ensure_ascii=False, indent=2))
        else:
            print(varredura.em_texto(publico))
        if not argumentos.sem_arquivo:
            try:
                destino_completo = _salvar(publico)
                print(f"  Relatório salvo em: {destino_completo}")
                if argumentos.pacote:
                    pacote = _empacotar(relatorio_completo, destino_completo)
                    print(f"  Pacote para mandar: {pacote}")
                    print("  (não tem nome, conta nem arquivo seu: só as respostas do `adb`)")
                print()
            except OSError as exc:
                print(f"  (Não consegui salvar o relatório: {exc})")
        return 0

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
            if argumentos.pacote:
                print(f"  Pacote para mandar: {_empacotar(relatorio, destino)}")
                print("  (não tem nome, conta nem arquivo seu: só as respostas do `adb`)")
            else:
                print("  Mande este arquivo se quiser comparar depois — ele não tem nada pessoal.")
            print()
        except OSError as exc:
            print(f"  (Não consegui salvar o relatório: {exc})")
            print()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
