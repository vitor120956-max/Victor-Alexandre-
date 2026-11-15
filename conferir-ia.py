#!/usr/bin/env python3
"""Conferir a IA que o JARVIS está usando — sem gastar cota de geração.

O problema que este arquivo resolve, medido no PC do dono em 0.91.5:

    Parei no passo 3 (conserto.propor): O provedor não respondeu (AIUnavailable):
    o provedor de IA respondeu com HTTP 400.

HTTP 400 quer dizer **pedido recusado** — chave é 401, cota é 429. As duas
causas mais comuns de 400 são o nome do modelo (que envelhece em semanas) e o
tamanho do pedido. Este script pergunta ao provedor quais modelos **esta conta**
vê (`GET /models`, leitura de catálogo, não gasta geração) e compara com o nome
que está no `.env`.

Uso (Windows, na pasta do JARVIS):

    .venv\\Scripts\\python conferir-ia.py
    .venv\\Scripts\\python conferir-ia.py --testar    # manda 8 tokens de verdade

Só lê. Nunca imprime a chave: mostra a máscara, do mesmo jeito que a tela.
"""
from __future__ import annotations

import argparse
import difflib
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent


def _ambiente() -> None:
    """Lê o `.env` da pasta do JARVIS, sem sobrescrever o que já está no ambiente."""
    try:
        from dotenv import load_dotenv
    except Exception:  # noqa: BLE001 - sem python-dotenv, o ambiente ainda vale
        return
    load_dotenv(RAIZ / ".env")


def _parecidos(modelo: str, disponiveis: list[str], quantos: int = 3) -> list[str]:
    return difflib.get_close_matches(modelo, disponiveis, n=quantos, cutoff=0.4)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Confere provedor, modelo e chave da IA.")
    parser.add_argument(
        "--testar",
        action="store_true",
        help="Além de listar, manda um pedido de 8 tokens para ver se a chave responde.",
    )
    parser.add_argument("--json", action="store_true", help="Saída de máquina.")
    args = parser.parse_args(argv)

    _ambiente()
    sys.path.insert(0, str(RAIZ))

    from server import chaves, provedores  # noqa: E402

    estado = chaves.estado()
    modelo = str(estado.get("modelo") or "")
    base = str(estado.get("base") or "")

    print("  JARVIS — conferir a IA")
    print()
    print(f"  provedor:  {estado.get('provedor_id') or estado.get('provedor') or 'nenhum'}")
    print(f"  endereço:  {base or 'nenhum'}")
    print(f"  modelo:    {modelo or 'nenhum'}")
    print(f"  chaves:    {estado.get('quantidade') or 0} configurada(s) {estado.get('mascaradas') or []}")
    print(f"  arquivo:   {estado.get('arquivo')}")
    print()

    if not base or not modelo:
        print("  Não há IA configurada. Abra a tela do JARVIS → Configurações → Modelos de IA,")
        print("  ou rode: .venv\\Scripts\\python configurar-chave.py")
        return 1

    disponiveis: list[str] = []
    lista_ok = False
    motivo_da_lista = ""
    try:
        # `limite` alto de propósito: comparar contra uma lista cortada diria
        # “não está na lista” para um modelo que está — e mandaria a pessoa
        # trocar o nome sem motivo.
        achado = provedores.listar_modelos(limite=10_000)
        itens = achado.get("modelos") or achado.get("items") or []
        disponiveis = [
            str(item.get("id") or item.get("name") or item) if isinstance(item, dict) else str(item)
            for item in itens
        ]
        disponiveis = [nome for nome in disponiveis if nome]
        lista_ok = True
    except Exception as exc:  # noqa: BLE001 - a lista é um extra, não o veredito
        motivo_da_lista = f"{type(exc).__name__}: {exc}"

    if not lista_ok:
        print(f"  LISTA DE MODELOS: não deu ({motivo_da_lista})")
    elif not disponiveis:
        print("  LISTA DE MODELOS: o provedor respondeu sem nenhum modelo.")
    else:
        print(f"  LISTA DE MODELOS: {len(disponiveis)} que a sua chave vê.")
        print("  " + ", ".join(disponiveis[:10]) + (" …" if len(disponiveis) > 10 else ""))
        print()
        if modelo in disponiveis:
            print(f"  OK  o modelo “{modelo}” está na lista.")
        else:
            print(f"  NÃO  o modelo “{modelo}” NÃO está na lista.")
            parecidos = _parecidos(modelo, disponiveis)
            if parecidos:
                print("  Use um destes:")
                for nome in parecidos:
                    print(f"    {nome}")
            print()
            print("  Nos modelos gratuitos, o nome muda sem aviso: “llama-3.3-70b-versatile”")
            print("  não existe no OpenRouter, que usa “meta-llama/llama-3.3-70b-instruct”.")
            print("  Troque no cartão Modelos de IA (ou no .env, JARVIS_AI_MODEL).")

    codigo = 0
    if args.testar:
        print()
        print("  TESTE DE VERDADE (8 tokens por chave)...")
        try:
            teste = chaves.testar()
        except Exception as exc:  # noqa: BLE001 - o teste é o resultado
            print(f"  FALHOU ({type(exc).__name__}): {exc}")
            return 1
        for item in teste.get("resultados") or []:
            marca = "OK  " if item.get("ok") else "NÃO "
            print(f"  {marca} chave {item.get('indice')}: HTTP {item.get('codigo')}")
            if item.get("motivo"):
                print(f"       motivo: {item['motivo']}")
            if item.get("detalhe"):
                print(f"       o provedor disse: “{item['detalhe']}”")
            if item.get("modelo_que_respondeu"):
                print(f"       quem respondeu: {item['modelo_que_respondeu']}")
        if not teste.get("ok"):
            codigo = 1

    print()
    if not estado.get("quantidade"):
        print("  Não há chave nenhuma configurada: é isso que falta, antes de qualquer modelo.")
        return 1
    if lista_ok and disponiveis and modelo not in disponiveis:
        print(f"  Achei o problema: o modelo “{modelo}” não existe neste provedor.")
        print("  Troque o nome (cartão Modelos de IA ou JARVIS_AI_MODEL no .env) e rode de novo.")
        return 1
    if codigo == 0 and lista_ok and modelo in disponiveis:
        print("  Pronto: provedor, modelo e chave estão coerentes.")
    elif codigo == 0:
        print("  Se o JARVIS continuar recusando, rode de novo com --testar para ver o HTTP exato.")
    return codigo


if __name__ == "__main__":
    raise SystemExit(main())
