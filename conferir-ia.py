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


# 0.91.31 — o `difflib` que ficava aqui escolhia pelo nome mais PARECIDO, e o
# mais parecido com `deepseek/deepseek-chat-v3-0324:free` eram os `deepseek`
# pagos. A escolha agora é `server/escolha_modelo.py`: grátis primeiro, nada de
# ferramenta (embedding, áudio, imagem) e uma família que conversa bem.


def _conta_gratuita(base: str) -> bool:
    """A conta é gratuita? Só o OpenRouter sabe dizer — e é leitura, não gasta."""
    if "openrouter" not in (base or "").lower():
        return False
    try:
        from server import chaves, openrouter_api

        lista = chaves.separar_chaves(chaves.ler_valor("JARVIS_AI_API_KEY"))
        if not lista:
            return False
        estado = openrouter_api.estado_da_chave(lista[0])
    except Exception:  # noqa: BLE001 - saber a conta é um extra
        return False
    return bool(estado.get("is_free_tier"))


def _backup_do_env() -> Path | None:
    """Uma cópia do `.env` antes de mexer — o dono pediu backup antes, sempre."""
    from server import chaves

    origem = chaves.env_path()
    if not origem.is_file():
        return None
    from datetime import datetime

    destino = origem.with_name(f".env.antes-{datetime.now().strftime('%Y%m%d-%H%M%S')}")
    destino.write_bytes(origem.read_bytes())
    return destino


def _gravar_modelo(novo: str) -> tuple[bool, str]:
    """Troca só a linha do modelo no `.env`, com backup. Devolve (deu?, aviso)."""
    from server import chaves

    origem = chaves.env_path()
    try:
        texto = origem.read_bytes().decode("utf-8", errors="replace") if origem.is_file() else ""
        backup = _backup_do_env()
        chaves.gravar(chaves.definir(texto, "JARVIS_AI_MODEL", novo))
    except OSError as exc:
        return False, f"não consegui gravar o .env ({exc})"
    aviso = f" (cópia do antigo em {backup.name})" if backup else ""
    return True, aviso


def _corrigir_modelo(disponiveis: list[str], atual: str, so_gratis: bool) -> str:
    """Escolhe um modelo que existe **e responde**, testa e grava. Devolve o escolhido.

    Escolher no papel não basta: a lista diz o que existe, não o que responde.
    Por isso cada candidato leva uma chamada de 8 tokens antes de virar `.env` —
    e o primeiro que responde é o que entra.
    """
    from server import chaves, escolha_modelo

    candidatos = escolha_modelo.candidatos(disponiveis, limite=8, atual=atual)
    if so_gratis:
        gratuitos = [nome for nome in candidatos if escolha_modelo.e_gratis(nome)]
        if gratuitos:
            candidatos = gratuitos
        else:
            print("  (nenhum modelo :free na lista — vou testar os outros, mas eles gastam crédito)")
    candidatos = candidatos[:3]
    if not candidatos:
        print("  Não há nenhum modelo de conversa na lista que o provedor devolveu.")
        return ""

    print()
    print("  Escolhendo um modelo que exista hoje (teste de 8 tokens em cada um):")
    for nome in candidatos:
        print(f"    testando {nome} …", end=" ", flush=True)
        try:
            resultado = chaves.testar_modelo(nome)
        except Exception as exc:  # noqa: BLE001 - qualquer falha vira motivo
            print(f"não deu ({type(exc).__name__})")
            continue
        if not resultado.get("ok"):
            print(f"não ({resultado.get('motivo') or resultado.get('codigo')})")
            continue
        print("respondeu.")
        deu, aviso = _gravar_modelo(nome)
        if not deu:
            print(f"  {aviso}")
            return ""
        print(f"  Gravei JARVIS_AI_MODEL={nome}{aviso}")
        print("  Só essa linha mudou; o resto do .env ficou igual.")
        return nome
    print()
    print("  Nenhum dos testados respondeu. Rode de novo em um minuto:")
    print("    .venv\\Scripts\\python conferir-ia.py --corrigir")
    return ""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Confere provedor, modelo e chave da IA.")
    parser.add_argument(
        "--testar",
        action="store_true",
        help="Além de listar, manda um pedido de 8 tokens para ver se a chave responde.",
    )
    parser.add_argument("--json", action="store_true", help="Saída de máquina.")
    parser.add_argument(
        "--corrigir",
        action="store_true",
        help="Se o modelo do .env não existe mais, escolhe um que existe, testa e grava.",
    )
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

    # A chave inválida vem ANTES de qualquer chamada de rede: perguntar ao
    # provedor com uma chave que não é chave devolve 400 ou 401, e as duas
    # mandam a pessoa investigar o lugar errado.
    problemas = list(estado.get("suspeitas") or [])
    if problemas:
        for aviso in problemas:
            print(f"  ATENÇÃO: {aviso}")
        print()
        print("  Isso é a causa, e não é o modelo: a chave gravada não é uma chave.")
        print("  Para gravar de novo:")
        print("    .venv\\Scripts\\python configurar-chave.py")
        print("  No console do Windows 10, cole com o BOTÃO DIREITO do mouse —")
        print("  Ctrl+V aqui não cola, ele escreve um caractere invisível na chave.")
        print("  Se preferir a tela do JARVIS: Configurações → Chaves de IA → colar → salvar.")
        return 1

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
            from server import escolha_modelo

            # 0.91.31 — o `difflib` sugeria o nome mais PARECIDO, e os mais
            # parecidos com `…-v3-0324:free` eram os pagos. Numa conta gratuita
            # isso trocava um 404 por um 402. Agora: grátis primeiro, e nada de
            # ferramenta (embedding, áudio, imagem).
            so_gratis = _conta_gratuita(base)
            print(f"  NÃO  o modelo “{modelo}” NÃO está na lista.")
            sugestoes = escolha_modelo.sugestoes(disponiveis, modelo, so_gratis=so_gratis)
            if sugestoes:
                print("  Use um destes:" if not so_gratis else "  Use um destes (grátis, porque a sua conta é gratuita):")
                for nome in sugestoes:
                    print(f"    {nome}")
            print()
            print("  O nome do modelo muda sem aviso. Troque no cartão Modelos de IA")
            print("  (ou no .env, JARVIS_AI_MODEL) — ou deixe eu escolher e testar:")
            print("    .venv\\Scripts\\python conferir-ia.py --corrigir")
            if args.corrigir:
                escolhido = _corrigir_modelo(disponiveis, modelo, so_gratis)
                if escolhido:
                    modelo = escolhido
                    print(f"  Seguindo com “{modelo}”.")

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
