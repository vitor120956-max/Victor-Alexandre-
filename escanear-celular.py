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
    # 0.95.4 — o nome do arquivo levava o **serial do aparelho** (RXCW400ZV3F),
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


def _instalar_driver(como_json: bool) -> int:
    """Baixa e instala o driver do celular — o passo que o dono não faz à mão.

    0.95.4 — nasceu de um pedido literal: *"pq vc nao faz javris instalar para
    mim"*. O dono não digita comando de terminal e não caça arquivo em site.

    O `.env` é lido no começo (`_ambiente()`), então basta a linha lá dentro; o
    `.bat` não precisa exportar nada. E o caminho de saída é sempre uma frase com
    o que fazer em seguida, não um stack trace.
    """
    from server import sistema

    # 0.95.4 — antes de baixar 33 MB, pergunte ao Windows se já está lá.
    # O dono roda `.bat` em sequência; não pode pagar o download toda vez.
    estado = sistema.driver_instalado("samsung")
    if estado.get("instalado"):
        if como_json:
            print(json.dumps({"ja_instalado": True, **estado}, ensure_ascii=False, indent=2))
            return 0
        print()
        print("  O driver já está instalado neste PC — não baixei nada.")
        print(f"    ({estado.get('como_sei', '')})")
        for nome in estado.get("dispositivos", []):
            print(f"    • {nome}")
        print()
        print("  Então o que falta não é o driver. Rode o escanear-celular.bat de novo")
        print("  e, se o aparelho não aparecer, o problema é cabo, porta ou a tela")
        print("  bloqueada na hora do aviso de depuração — não a instalação.")
        print()
        return 0

    try:
        feito = sistema.driver_do_celular(fabricante="samsung", confirmado=True)
    except sistema.SistemaError as exc:
        if como_json:
            print(json.dumps({"erro": str(exc)}, ensure_ascii=False, indent=2))
            return 1
        print()
        print("  Não consegui instalar o driver:")
        print(f"    {exc}")
        print()
        if "JARVIS_HOST_REDE" in str(exc) or "Rede desligada" in str(exc):
            print("  Para mim isso é a linha JARVIS_HOST_REDE=1 no .env —")
            print("  e o mesmo para JARVIS_HOST_INSTALAR=1. Depois rode de novo.")
        elif "Windows" in str(exc):
            print("  O driver é do Windows; este computador não precisa dele.")
        print()
        return 1

    if como_json:
        print(json.dumps(feito, ensure_ascii=False, indent=2))
        return 0
    print()
    print("  Driver instalado no PC. O celular não recebeu nada.")
    print(f"    arquivo: {feito.get('baixado', {}).get('bytes', 0) / 1_048_576:.1f} MB,"
          f" sha256 {str(feito.get('baixado', {}).get('sha256', ''))[:16]}...")
    print()
    print("  Agora, para o `adb` enxergar o aparelho:")
    print("    1. desconecte o cabo e conecte de novo (celular desbloqueado);")
    print("    2. toque em \"Permitir\" no aviso de depuração USB;")
    print("    3. rode o escanear-celular.bat de novo.")
    print()
    return 0


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
        "--driver",
        action="store_true",
        help=(
            "Instala o Samsung USB Driver no PC, sem passo manual: é o que faz o `adb` "
            "enxergar o aparelho quando o Windows só mostra a pasta (MTP). Instala NO PC, "
            "nada no celular. Exige JARVIS_HOST_REDE=1 e JARVIS_HOST_INSTALAR=1 no .env."
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

    if argumentos.driver:
        return _instalar_driver(argumentos.json)

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
