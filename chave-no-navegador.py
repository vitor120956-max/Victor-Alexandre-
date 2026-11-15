#!/usr/bin/env python3
"""Criar a chave de IA pelo navegador, com o JARVIS clicando.

## O que isto faz — e o que não faz

A chave **não está** na página de chaves: o OpenRouter mostra o valor uma única
vez, no instante da criação, e depois só o prefixo mascarado. Não existe ler a
chave que já existe — por isso este script não promete isso.

O que ele faz é o caminho de **criar uma nova**, em passos medidos:

    --abrir                 abre openrouter.ai/keys no seu navegador
    --ver                   LÊ a página e diz quais botões existem (não clica)
    --pegar                 lê a área de transferência e grava no .env
    --criar --autorizar     clica "Create Key", dá um nome, cria e copia

O `--ver` existe porque a promessa tem de ser medida antes de ser feita: se o
Chrome não publicar o botão na árvore de acessibilidade, o `--criar` não tem
como funcionar, e é melhor saber disso em dois segundos do que em vinte cliques.

`--criar` mexe na sua conta: cria uma credencial de verdade. Ele só roda com
`--autorizar`, diz cada passo antes de dar, e para no primeiro que falhar
dizendo qual foi.

Uso (Windows, na pasta do JARVIS):

    .venv\\Scripts\\python chave-no-navegador.py --abrir
    .venv\\Scripts\\python chave-no-navegador.py --ver
    .venv\\Scripts\\python chave-no-navegador.py --criar --autorizar
    .venv\\Scripts\\python chave-no-navegador.py --pegar

Nada aqui lê tela por imagem, nem guarda a chave em log: ela vai para o `.env`
e aparece só mascarada.
"""
from __future__ import annotations

import argparse
import importlib.util
import sys
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parent


class PassoError(RuntimeError):
    """Um passo não deu — com o nome do passo e o que fazer."""


def _configurar_ambiente() -> None:
    try:
        from dotenv import load_dotenv
    except Exception:  # noqa: BLE001 - sem python-dotenv, o ambiente ainda vale
        return
    load_dotenv(RAIZ / ".env")


def _modulo_do_configurador():
    """Reaproveita gravar/ler/mascarar do `configurar-chave.py` — uma verdade só."""
    caminho = RAIZ / "configurar-chave.py"
    spec = importlib.util.spec_from_file_location("configurar_chave_para_web", caminho)
    modulo = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(modulo)
    return modulo


def _ler_janela(alvo: str):
    """A janela do navegador e a árvore montada — com o erro já em português."""
    from server import arvore, arvore_windows

    try:
        janelas = arvore_windows.janelas()
    except Exception as exc:  # noqa: BLE001 - COM de terceiros
        raise PassoError(f"não consegui listar as janelas ({type(exc).__name__}).") from exc
    foco = arvore_windows.janela_em_foco()
    try:
        janela = arvore_windows.escolher_janela(alvo or "chrome", janelas=janelas, foco=foco)
    except Exception as exc:  # noqa: BLE001
        raise PassoError(
            f"não achei a janela do navegador ({type(exc).__name__}). "
            "Abra openrouter.ai/keys no Chrome e rode de novo."
        ) from exc
    bruto = arvore_windows.ler_janela(int(janela["handle"]), 8, 1500)
    montada = arvore.montar(bruto, 8, 1500, com_caminho=True)
    return janela, montada


def _clicar(janela: dict, no: dict, acao: str = "clicar", texto: str = "") -> dict:
    """Clica num nó **da leitura que o encontrou** (ref antigo não serve)."""
    from server import arvore_windows

    try:
        return arvore_windows.executar_ref(
            int(janela["handle"]),
            no["caminho"],
            acao,
            texto,
            no.get("caixa"),
        )
    except Exception as exc:  # noqa: BLE001 - COM de terceiros
        raise PassoError(
            f"não consegui clicar em “{no.get('nome')}” ({type(exc).__name__})."
        ) from exc


def _esperar_elemento(alvo: str, padroes: tuple[str, ...], segundos: float = 12.0):
    """Relê a janela até o elemento aparecer. Devolve (janela, nó, árvore)."""
    from server import chave_web

    fim = time.time() + segundos
    ultima = ""
    while True:
        janela, montada = _ler_janela(alvo)
        achados = chave_web.procurar(montada, padroes)
        if achados:
            return janela, achados[0], montada
        ultima = chave_web.texto_do_diagnostico(chave_web.diagnostico(montada))
        if time.time() >= fim:
            raise PassoError(
                f"não apareceu “{padroes[0]}” em {int(segundos)}s nestaleitura.\n{ultima}"
            )
        time.sleep(0.8)


def passo_ver(args) -> int:
    from server import chave_web

    janela, montada = _ler_janela(args.alvo)
    dados = chave_web.diagnostico(montada)
    print(chave_web.texto_do_diagnostico(dados))
    print()
    print("  Nada foi clicado: isto é só leitura.")
    return 0


def passo_pegar(args) -> int:
    """A chave que você copiou no site → `.env`. Sem digitar nada."""
    modulo = _modulo_do_configurador()
    try:
        limpo, chave = modulo.chave_da_area_de_transferencia()
    except RuntimeError as exc:
        print(f"  NÃO DEU: {exc}")
        return 1
    print(modulo.descrever_area(limpo, chave))
    return _gravar(modulo, chave)


def _gravar(modulo, chave: str) -> int:
    codigo = modulo.principal(["--chave", chave])
    if codigo != 0:
        print("  A chave foi lida, mas não deu para gravar no .env — veja acima.")
    return codigo


def passo_criar(args) -> int:
    """Cria uma chave nova: clica, nomeia, cria e copia. Gated por --autorizar."""
    from server import chave_web

    janela, montada = _ler_janela(args.alvo)
    dados = chave_web.diagnostico(montada)
    print(chave_web.texto_do_diagnostico(dados))
    print()
    if not dados["pode_criar"]:
        print("  Parei aqui: sem o botão de criar na árvore, não há o que clicar.")
        print("  Caminho que funciona sempre: crie no navegador e rode `--pegar`.")
        return 1
    if not args.autorizar:
        print("  Isto VAI CRIAR uma chave nova na sua conta (é uma credencial de verdade).")
        print("  Repita com --autorizar para fazer.")
        return 0

    modulo = _modulo_do_configurador()
    nome = args.nome or chave_web.nome_sugerido()

    # 1. clicar em "Create Key"
    print(f"  1. clicando em “{dados['criar'][0]}”…")
    _clicar(janela, chave_web.procurar(montada, chave_web.PADROES_CRIAR)[0])
    time.sleep(1.5)

    # 2. dar um nome (se aparecer um campo)
    try:
        janela, campo, _ = _esperar_elemento(args.alvo, chave_web.PADROES_NOME, segundos=8)
        print(f"  2. escrevendo o nome “{nome}” em “{campo.get('nome')}”…")
        _clicar(janela, campo, "digitar", nome)
        time.sleep(0.8)
    except PassoError:
        print("  2. não apareceu campo de nome — seguindo (alguns fluxos não pedem).")

    # 3. confirmar a criação (o botão de criar, de novo, agora no diálogo)
    try:
        janela, criar, montada = _esperar_elemento(args.alvo, chave_web.PADROES_CRIAR, segundos=8)
        print(f"  3. clicando em “{criar.get('nome')}” para criar…")
        _clicar(janela, criar)
        time.sleep(2.0)
    except PassoError as exc:
        print(f"  3. NÃO DEI: {exc}")
        print("  A chave pode ter ficado criada e não copiada. Veja no navegador.")
        return 1

    # 4. copiar (o valor aparece uma vez; o botão de copiar é o caminho seguro)
    try:
        janela, copiar, _ = _esperar_elemento(args.alvo, chave_web.PADROES_COPIAR, segundos=10)
        print(f"  4. clicando em “{copiar.get('nome')}” para copiar a chave…")
        _clicar(janela, copiar)
        time.sleep(0.8)
    except PassoError as exc:
        print(f"  4. NÃO DEI: {exc}")
        print("  Se a chave está na tela, clique em Copiar você mesmo e rode `--pegar`.")
        return 1

    # 5. ler a área de transferência e gravar
    print("  5. lendo a área de transferência…")
    try:
        limpo, chave = modulo.chave_da_area_de_transferencia()
    except RuntimeError as exc:
        print(f"  NÃO DEU: {exc}")
        print("  Clique em Copiar e rode `--pegar`.")
        return 1
    print(modulo.descrever_area(limpo, chave))
    return _gravar(modulo, chave)


def passo_abrir(args) -> int:
    modulo = _modulo_do_configurador()
    guia = modulo.guia_do_provedor("openrouter", "https://openrouter.ai/api/v1")
    if modulo.abrir_no_navegador(guia["onde"]):
        print(f"  Abri {guia['onde']} no seu navegador.")
        print("  Você já está logado: clique em “Create Key”, dê um nome e clique em COPIAR.")
        print("  Depois rode:  .venv\\Scripts\\python chave-no-navegador.py --pegar")
        return 0
    print("  Não consegui abrir o navegador. Abra na mão: openrouter.ai/keys")
    return 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Criar/colher a chave de IA pelo navegador.")
    parser.add_argument("--abrir", action="store_true", help="Abre a página de chaves no navegador.")
    parser.add_argument("--ver", action="store_true", help="Lê a página e diz o que existe. Não clica.")
    parser.add_argument("--pegar", action="store_true", help="Grava a chave que está na área de transferência.")
    parser.add_argument("--criar", action="store_true", help="Tenta criar uma chave nova clicando na página.")
    parser.add_argument("--autorizar", action="store_true", help="Sem isto, --criar só mostra o que faria.")
    parser.add_argument("--nome", default="", help="Nome da chave criada (padrão: jarvis-AAAA-MM-DD).")
    parser.add_argument("--alvo", default="chrome", help="Pedaço do título da janela (padrão: chrome).")
    args = parser.parse_args(argv)

    if sys.platform != "win32":
        print("  Isto só funciona no Windows: é lá que existe a janela e a área de transferência.")
        return 1

    _configurar_ambiente()
    sys.path.insert(0, str(RAIZ))

    try:
        if args.abrir:
            return passo_abrir(args)
        if args.pegar:
            return passo_pegar(args)
        if args.criar:
            return passo_criar(args)
        return passo_ver(args)
    except PassoError as exc:
        print(f"  NÃO DEU: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
