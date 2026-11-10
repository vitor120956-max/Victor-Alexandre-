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
    py arvore_sonda.py --fonte uia          # força uma das duas fontes

Só leitura: nada é clicado, digitado ou movido.

## 0.82.1 — duas correções que vieram da primeira medição no PC

1. **Não ler a si mesma.** O comando roda dentro de um `cmd.exe`, e a janela em
   foco é justamente esse `cmd`. A primeira medição devolveu o próprio terminal
   — “1 elemento, 0 acionável” — quando o usuário queria ver o programa aberto
   atrás. Agora, se o foco for o terminal, a sonda procura a janela anterior e
   diz que trocou.
2. **Segunda fonte.** O console não publica botões pela MSAA (é de 1996). Ele
   publica pela **UIAutomation**. A leitura agora tenta as duas e fica com a que
   mostrou mais elementos.

## 0.82.3 — a escolha da janela

Na 0.82.2, `--alvo chrome` leu **o terminal**: a busca procurava primeiro no
título, e o título do `cmd` é a linha de comando — que contém a palavra
“chrome”. A janela que roda a sonda é justamente a que sempre carrega o pedido
escrito nela. Agora ela é excluída das candidatas, e processo vence título.
"""
from __future__ import annotations

import argparse
import json
import sys


def _falhar(mensagem: str, codigo: int = 1) -> int:
    print(json.dumps({"erro": mensagem}, ensure_ascii=False))
    return codigo


def _escolher(leitor, alvo: str) -> tuple[dict, str]:
    """Janela a ler + explicação de eventual troca.

    Quem decide o alvo é `arvore.escolher_janela` (a mesma da API): processo
    vence título, e a janela que roda a sonda fica de fora — foi ela que fez
    `--alvo chrome` ler o terminal na 0.82.2.

    Aqui só fica o caso `foco`: se quem está em foco é o terminal, pega a
    primeira janela de programa de verdade — é o que o usuário quis dizer.
    """
    from server import arvore

    pedido = (alvo or "foco").strip().lower()
    if pedido not in {"foco", "focused", ""}:
        return arvore.escolher_janela(alvo, janelas=leitor.janelas(), foco=None), ""

    foco = leitor.janela_em_foco()
    janela = arvore.escolher_janela(alvo, janelas=leitor.janelas(), foco=foco)
    if not arvore.e_terminal(janela):
        return janela, ""

    reais = getattr(leitor, "janelas_de_programas", leitor.janelas)
    candidatas = [
        item
        for item in reais()
        if not arvore.e_terminal(item) and not arvore.da_sonda(item) and item.get("titulo")
    ]
    if not candidatas:
        return janela, (
            "a janela em foco é este terminal e não achei outra aberta — abra o programa "
            "que quer examinar e rode de novo."
        )
    escolhida = candidatas[0]
    return escolhida, (
        f"o foco estava neste terminal; li “{escolhida.get('titulo')}” "
        f"({escolhida.get('processo') or '?'}) em vez dele."
    )


def principal(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Lê a árvore de acessibilidade de uma janela (somente leitura).")
    parser.add_argument("--alvo", default="foco", help="“foco” (padrão) ou parte do título do processo/janela.")
    parser.add_argument("--profundidade", type=int, default=6, help="Até onde descer (1 a 14).")
    parser.add_argument("--limite", type=int, default=600, help="Máximo de elementos lidos (1 a 3000).")
    parser.add_argument(
        "--fonte",
        default="auto",
        choices=("auto", "msaa", "uia"),
        help="auto (padrão): as duas, fica com a que mostrar mais. msaa ou uia: força uma.",
    )
    parser.add_argument("--json", action="store_true", help="Devolve JSON cru para o JARVIS.")
    parser.add_argument("--janelas", action="store_true", help="Só lista as janelas abertas.")
    parser.add_argument(
        "--diagnostico",
        action="store_true",
        help="Testa a UIAutomation passo a passo e mostra o retorno de cada chamada.",
    )
    args = parser.parse_args(argv)

    if sys.platform != "win32":
        return _falhar("a leitura da árvore só existe no Windows hoje.")

    try:
        from server import arvore_windows as leitor
    except Exception as exc:  # noqa: BLE001 - qualquer falha de import é motivo de saída limpa
        return _falhar(f"não consegui carregar o leitor do Windows ({type(exc).__name__}).")

    if args.diagnostico:
        quadro = leitor.diagnostico()
        if args.json:
            print(json.dumps(quadro, ensure_ascii=False, indent=2))
            return 0 if quadro.get("ok") else 1
        for passo in quadro.get("passos", []):
            marca = "ok  " if passo.get("ok") else "FALHA"
            print(f"  [{marca}] {passo.get('passo')}  {passo.get('hex')}  {passo.get('detalhe') or ''}".rstrip())
        print()
        print(quadro.get("nota") or "")
        return 0 if quadro.get("ok") else 1

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
        janela, troca = _escolher(leitor, args.alvo)
    except arvore.ArvoreError as exc:
        return _falhar(str(exc))

    try:
        bruto = leitor.ler_janela(
            janela["handle"],
            max(1, min(args.profundidade, arvore.PROFUNDIDADE_MAX)),
            max(1, min(args.limite, arvore.LIMITE_MAX)),
            fonte=args.fonte,
        )
    except Exception as exc:  # noqa: BLE001 - COM de terceiros: nunca vazar stack
        return _falhar(f"a leitura da janela falhou ({type(exc).__name__}).")
    bruto.setdefault("janela", janela)
    if troca:
        bruto["nota_escolha"] = troca

    if args.json:
        print(json.dumps(bruto, ensure_ascii=False))
        return 0

    montada = arvore.montar(bruto, args.profundidade, args.limite)
    if troca:
        print(troca)
        print()
    print(arvore.resumo(montada))
    print()
    print(arvore.desenhar(montada.get("arvore")))
    return 0


if __name__ == "__main__":
    raise SystemExit(principal())
