#!/usr/bin/env python3
"""Criar a chave de IA pelo navegador, com o JARVIS clicando.

## O que isto faz — e o que não faz

A chave **não está** na página de chaves: o OpenRouter mostra o valor uma única
vez, no instante da criação, e depois só o prefixo mascarado. Não existe ler a
chave que já existe — por isso este script não promete isso.

O que ele faz é o caminho de **criar uma nova**, em passos medidos:

    --auto --autorizar      abre o site, entra se preciso, cria, copia e grava
    --abrir                 abre a página de chaves no seu navegador
    --ver                   LÊ a página e diz quais botões existem (não clica)
    --pegar                 lê a área de transferência e grava no .env
    --criar --autorizar     clica "Create Key", dá um nome, cria e copia

O `--auto` pega o provedor do `.env` (ou de `--provedor`) e abre **o site dele**:
openrouter.ai/keys, console.groq.com/keys, aistudio.google.com/apikey e assim
por diante.

## As três páginas (medido nas telas do dono, 0.91.14)

Abrir `openrouter.ai/keys` sem sessão **não** cai na página de chaves: cai em
“Sign In | OpenRouter”. Clicar no Google abre a escolha de conta; só depois da
conta é que aparece “API keys” com o botão “New key”. São três páginas na mesma
janela, e o JARVIS tem de saber em qual está antes de clicar em qualquer coisa:

    página de login  → clica no Google
    escolha de conta → clica na conta do dono (`--conta` ou `JARVIS_CONTA_GOOGLE`)
    página de chaves → clica em “New key”, nomeia, cria, copia

Se os botões não estiverem na árvore de acessibilidade, ele não termina em erro:
deixa a página aberta, diz o que falta clicar e fica esperando a chave aparecer
na área de transferência.

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
from datetime import datetime
import sys
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parent

# Onde fica lembrado o e-mail da conta do Google usada para entrar no site.
# Sem isso, a tela de escolha de conta (que lista mais de uma) faria o JARVIS
# perguntar em toda execução — ou pior, chutar.
CONTA_GOOGLE = "JARVIS_CONTA_GOOGLE"


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


# A leitura de estreia é rasa de propósito (rápida, 8 níveis). O diálogo de
# criação, porém, é um painel no fim do documento: no PC do dono ele abriu e a
# leitura rasa não o viu. Para achar o painel, a leitura vai fundo.
PROFUNDA, TETO_FUNDO = 14, 3000


def _ler_janela(alvo: str, profundidade: int = 8, limite: int = 1500):
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
    bruto = arvore_windows.ler_janela(int(janela["handle"]), profundidade, limite)
    montada = arvore.montar(bruto, profundidade, limite, com_caminho=True)
    return janela, montada


# Abaixo disto a leitura não chegou na página: veio a **moldura** do Chrome
# (“Chrome Legacy Window”, o título da aba, botões da barra). Medido na tela do
# dono: com o painel aberto, a leitura automática escolheu a moldura e trouxe
# 3 nomes — e o script disse que o diálogo não estava lá.
LEITURA_POBRE = 8


def _nomes(montada: dict) -> int:
    """Quantos elementos com nome a leitura trouxe — o tamanho da “cara” da página."""
    from server import chave_web

    return len(chave_web.elementos(montada))


def _ler_pela_fonte(handle: int, profundidade: int, limite: int, fonte: str = "auto") -> dict:
    """Uma leitura, por uma fonte escolhida. `auto` deixa o Windows decidir."""
    from server import arvore, arvore_windows

    if fonte == "auto":
        bruto = arvore_windows.ler_janela(handle, profundidade, limite)
    else:
        bruto = arvore_windows.ler_janela(handle, profundidade, limite, fonte=fonte)
    return arvore.montar(bruto, profundidade, limite, com_caminho=True)


def _reler(janela: dict, profundidade: int = 8, limite: int = 1500):
    """Relê **esta** janela (pelo handle), não “a janela do chrome”.

    Duas coisas que esta função garante, e cada uma custou uma execução no PC
    do dono:

    1. **o handle é a identidade.** A cada passo o código escolhia de novo a
       janela pelo nome; com duas janelas do Chrome abertas — a sua e a do
       site —, um passo podia ler (e clicar) na errada;
    2. **leitura pobre é lida de novo, pelas duas fontes.** O Chrome moderno
       publica a página pela UIAutomation; a MSAA devolve só a moldura. Se a
       escolha automática cair na moldura (3 nomes), a página some da leitura —
       e o script conclui “não apareceu”. Aqui, quando isso acontece, as fontes
       são medidas na mão e fica a que mostrou a página.
    """
    from server import arvore_windows

    handle = int(janela.get("handle") or 0)
    if not handle or not arvore_windows.janela_muda(handle):
        raise PassoError("a janela do navegador foi fechada no meio do caminho.")
    montada = _ler_pela_fonte(handle, profundidade, limite, "auto")
    if _nomes(montada) >= LEITURA_POBRE:
        return janela, montada
    for fonte in ("uia", "msaa"):
        try:
            tentativa = _ler_pela_fonte(handle, profundidade, limite, fonte)
        except Exception:  # noqa: BLE001 - COM de terceiros: uma fonte pode cair
            continue
        if _nomes(tentativa) > _nomes(montada):
            montada = tentativa
    return janela, montada


def _clicar(
    janela: dict,
    no: dict,
    acao: str = "clicar",
    texto: str = "",
    *,
    mouse: bool = False,
    primeiro_mouse: bool = False,
) -> dict:
    """Clica num nó **da leitura que o encontrou** (ref antigo não serve).

    Antes da 0.91.10 o resultado era descartado: se o clique não saía, o script
    seguia para o passo seguinte e culpava o passo errado. Agora quem não
    executou vira `PassoError` com o motivo que o Windows deu.
    """
    from server import arvore_windows

    nome = str(no.get("nome") or "")[:60]
    try:
        feito = arvore_windows.executar_ref(
            int(janela["handle"]),
            no["caminho"],
            acao,
            texto,
            no.get("caixa"),
            mouse=mouse,
            primeiro_mouse=primeiro_mouse,
        )
    except Exception as exc:  # noqa: BLE001 - COM de terceiros
        raise PassoError(
            f"não consegui clicar em “{nome}” ({type(exc).__name__})."
        ) from exc
    if not feito.get("executou"):
        motivo = str(feito.get("motivo") or "o Windows não disse o motivo.")
        raise PassoError(f"“{nome}” não aceitou o clique: {motivo}")
    return feito


def _descrever_clique(feito: dict) -> str:
    """Como o clique saiu — com o mouse ou pela ação do elemento."""
    como = str(feito.get("como") or "")
    if como.startswith("clique físico"):
        voltou = " o cursor voltou para onde estava." if feito.get("cursor_voltou") else ""
        return f"{como}.{voltou}"
    return como or "feito"


def _esperar_elemento(janela: dict, padroes: tuple[str, ...], segundos: float = 12.0):
    """Relê **esta** janela até o elemento aparecer. Devolve (janela, nó, árvore).

    Recebe a janela (handle) e não o nome: com duas janelas do Chrome abertas,
    procurar pelo nome podia ler a errada — e o botão que está numa não existe
    na outra.
    """
    from server import chave_web

    fim = time.time() + segundos
    ultima = ""
    while True:
        try:
            janela, montada = _reler(janela, PROFUNDA, TETO_FUNDO)
        except PassoError:
            raise
        achados = chave_web.procurar(montada, padroes)
        if achados:
            return janela, achados[0], montada
        ultima = _diagnostico_da_leitura(montada)
        if time.time() >= fim:
            raise PassoError(f"não apareceu “{padroes[0]}” em {int(segundos)}s nesta leitura. {ultima}")
        time.sleep(0.8)


def passo_ver(args) -> int:
    from server import chave_web

    janela, montada = _ler_janela(args.alvo)
    estado = chave_web.onde_estou(montada, conta=args.conta)
    print(chave_web.texto_do_estado(estado))
    dados = chave_web.diagnostico(montada)
    print(chave_web.texto_do_diagnostico(dados))
    print()
    if dados["pode_clicar_com_mouse"]:
        print("  Dá para clicar com o mouse: SIM — há botão com posição medida na tela.")
    elif dados["pode_criar"] or dados["pode_copiar"]:
        print("  Dá para clicar com o mouse: não — achei o botão, mas sem posição na tela.")
    print("  Nada foi clicado: isto é só leitura.")
    return 0


# ---------------------------------------------------- a área de transferência
#
# Tudo o que acontece depois do clique passa por aqui. Duas regras que parecem
# detalhe e não são:
#
# 1. **Guardar o que já estava lá.** Se o dono copiou uma chave ontem e deixou
#    na área, ler "a primeira chave que aparecer" gravaria a chave errada. Só
#    vale o texto que **mudou** desde que este comando começou.
# 2. **Não confiar no primeiro instante.** Depois do Ctrl+C o Windows leva um
#    pedaço de segundo para entregar; por isso a espera é um laço, não um `sleep`.

def _texto_da_area() -> str:
    """O texto cru da área de transferência — vazio quando não dá para ler."""
    from server import area_transferencia

    try:
        return area_transferencia.ler(tentativas=2, espera=0.05)
    except Exception:  # noqa: BLE001 - qualquer falha aqui é "ainda não deu"
        return ""


def _chave_no_texto(modulo, texto: str) -> str:
    """A chave que está dentro de um texto (a página inteira também serve)."""
    try:
        chaves = modulo.chaves_do_texto(modulo.sem_controle(texto or ""))
    except Exception:  # noqa: BLE001
        return ""
    return chaves[0] if chaves else ""


def _esperar_chave(modulo, anterior: str, segundos: float = 90.0) -> tuple[str, str] | None:
    """Espera aparecer na área uma chave diferente da que já estava lá."""
    fim = time.time() + segundos
    while True:
        texto = _texto_da_area()
        if texto and texto.strip() != (anterior or "").strip():
            chave = _chave_no_texto(modulo, texto)
            if chave:
                return texto, chave
        if time.time() >= fim:
            return None
        time.sleep(0.7)


def _copiar_pela_pagina(janela: dict) -> bool:
    """Ctrl+A e Ctrl+C na janela do navegador — o plano B do botão Copiar.

    Por que existe: o botão “Copy” pode não estar na árvore, mas o texto da
    página está sempre lá. Depois de criar, a chave aparece escrita na tela;
    selecionar tudo e copiar traz a página inteira, e a chave sai dela pela
    mesma régua que lê chave de arquivo. Não lê imagem, não adivinha pixel.
    """
    from server import arvore_windows, mesa

    try:
        if not arvore_windows.trazer_para_frente(int(janela["handle"])):
            return False
        if not arvore_windows.teclado_na_janela(int(janela["handle"])):
            return False
        mesa.teclar("ctrl+a")
        time.sleep(0.15)
        mesa.teclar("ctrl+c")
        return True
    except Exception:  # noqa: BLE001
        return False


def passo_pegar(args) -> int:
    """A chave que você copiou no site → `.env`. Sem digitar nada."""
    modulo = _modulo_do_configurador()
    try:
        limpo, chave = modulo.chave_da_area_de_transferencia()
    except RuntimeError as exc:
        print(f"  NÃO DEU: {exc}")
        print("  Copie a chave no site (botão COPIAR) e rode `--pegar` de novo.")
        return 1
    print(modulo.descrever_area(limpo, chave))
    atual = _chave_do_env(modulo)
    if atual and atual == chave:
        # Aconteceu no PC do dono: o `--auto` falhou, ele apertou Ctrl+C, disse
        # “n” no aviso do .bat, o `--pegar` achou a chave **velha** na área de
        # transferência e o .bat anunciou “a chave está no .env”. Estava — a
        # velha. Aqui a frase passa a ser verdadeira.
        print("  Essa chave é a MESMA que já estava no .env — nada mudou.")
        print("  Se você acabou de criar uma, o COPIAR não chegou a copiá-la.")
        print("  Clique em COPIAR no site e rode `--pegar` de novo.")
        return 0
    return _gravar(modulo, chave)


def _chave_do_env(modulo) -> str:
    """A chave que está gravada hoje — para não anunciar como nova a que já era."""
    try:
        if not modulo.ENV.is_file():
            return ""
        texto = modulo.ler_texto(modulo.ENV)
        return (modulo.ler_valor(texto, modulo.CHAVE) or "").strip()
    except Exception:  # noqa: BLE001 - comparar é conveniência, não requisito
        return ""


def _avisar_jarvis_aberto() -> bool:
    """Manda a API que já está rodando reler o `.env` — sem reiniciar.

    O servidor lê o `.env` uma vez, no start. Gravar a chave por fora da tela
    deixava a tela mostrando a chave antiga até fechar e abrir. Se a API não
    estiver no ar, isso não é erro: o próximo start lê o arquivo novo.
    """
    import json
    import urllib.request

    for porta in (8000, 8001):
        pedido = urllib.request.Request(
            f"http://127.0.0.1:{porta}/api/ai/recarregar",
            data=b"{}",
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(pedido, timeout=1.5) as resposta:  # noqa: S310 - endereço fixo local
                return bool(json.loads(resposta.read().decode("utf-8")).get("ok"))
        except Exception:  # noqa: BLE001 - API desligada não é falha de gravar
            continue
    return False


def _gravar(modulo, chave: str) -> int:
    """Grava a chave **sem perguntar nada** quando o provedor já está escolhido.

    A 0.91.10 mandava tudo pelo `principal()`, que é o questionário da primeira
    configuração: provedor, base, modelo. Com o `.env` já montado — o caso de
    quem está só trocando a chave —, esse questionário fazia o duplo clique
    parar esperando Enter em três perguntas que já tinham resposta. Aqui:
    provedor já gravado → troca só a chave; primeira vez → aí sim pergunta.
    """
    texto = modulo.ler_texto(modulo.ENV) if modulo.ENV.is_file() else modulo.texto_base()
    provedor = (modulo.ler_valor(texto, "JARVIS_AI_PROVIDER") or "").strip()
    if provedor:
        texto = modulo.definir(texto, modulo.CHAVE, chave)
        destino = modulo.gravar(texto)
        print(f"\n  Gravado em {destino}")
        print(f"  provedor: {provedor}")
        print(f"  chave:    {modulo.mascarar(chave)}")
        print("\n  As outras linhas do .env ficaram como estavam.")
        if _avisar_jarvis_aberto():
            print("  O JARVIS que já está aberto passou a usar esta chave agora.")
        else:
            print("  O JARVIS não está aberto: ele vai ler esta chave quando abrir.")
        return 0
    codigo = modulo.principal(["--chave", chave])
    if codigo != 0:
        print("  A chave foi lida, mas não deu para gravar no .env — veja acima.")
    return codigo


def _provedor_do_env(modulo) -> tuple[str, str]:
    """(provedor, base) que já estão no `.env` — o `--auto` usa os dois."""
    texto = modulo.ler_texto(modulo.ENV) if modulo.ENV.is_file() else modulo.texto_base()
    return (
        (modulo.ler_valor(texto, "JARVIS_AI_PROVIDER") or "").strip(),
        (modulo.ler_valor(texto, "JARVIS_AI_BASE_URL") or "").strip(),
    )


def _janelas_do_alvo(alvo: str) -> list[dict]:
    """Janelas que podem ser a página aberta, da mais provável para a menos.

    Por que não basta a escolha de sempre: quando o Chrome já está aberto, o
    link abre numa aba da **janela que estava em foco** — e a escolha padrão,
    que decide pelo processo, empatava todas as janelas do Chrome e podia ler a
    errada (a do e-mail do dono, por exemplo). Aqui a janela em foco vem
    primeiro, e o resto mantém a ordem da escolha de sempre.
    """
    from server import arvore, arvore_windows

    try:
        janelas = arvore_windows.janelas()
        foco = arvore_windows.janela_em_foco() or {}
    except Exception:  # noqa: BLE001 - COM de terceiros
        return []
    handle_foco = int(foco.get("handle") or 0)
    pontuadas = []
    for item in janelas:
        peso = arvore.peso_da_janela(item, alvo)
        if peso is None:
            continue
        pontuadas.append((peso, 0 if int(item.get("handle") or 0) == handle_foco else 1, item))
    pontuadas.sort(key=lambda tripla: (tripla[0], tripla[1]))
    return [item for _peso, _foco, item in pontuadas]


def _ler_janelas(
    alvo: str, maximo: int = 3, profundidade: int = 8, limite: int = 1500
) -> list[tuple[dict, dict]]:
    """Lê as janelas do navegador (até `maximo`), a que está em foco primeiro."""
    from server import arvore, arvore_windows

    leituras: list[tuple[dict, dict]] = []
    for janela in _janelas_do_alvo(alvo)[:maximo]:
        try:
            bruto = arvore_windows.ler_janela(int(janela["handle"]), profundidade, limite)
        except Exception:  # noqa: BLE001 - janela que fechou no meio
            continue
        leituras.append((janela, arvore.montar(bruto, profundidade, limite, com_caminho=True)))
    return leituras


def _conta_do_env(modulo) -> str:
    texto = modulo.ler_texto(modulo.ENV) if modulo.ENV.is_file() else modulo.texto_base()
    return (modulo.ler_valor(texto, CONTA_GOOGLE) or "").strip()


def _guardar_conta(modulo, email: str) -> bool:
    """Lembra a conta escolhida no `.env` — perguntar uma vez é útil, duas é chatice."""
    if not email:
        return False
    try:
        texto = modulo.ler_texto(modulo.ENV) if modulo.ENV.is_file() else modulo.texto_base()
        modulo.gravar(modulo.definir(texto, CONTA_GOOGLE, email))
        return True
    except Exception:  # noqa: BLE001 - lembrar é conveniência, não requisito
        return False


def _perguntar_conta(contas: list[dict]) -> dict | None:
    """Pergunta qual conta, quando a tela mostra mais de uma e ninguém disse qual.

    Escolher no chute a conta errada é pior do que perguntar: entrar na conta de
    outra pessoa da casa criaria uma chave na conta errada.
    """
    if len(contas) == 1:
        return contas[0]
    if not contas or not sys.stdin or not sys.stdin.isatty():
        return None
    print("  Achei mais de uma conta do Google. Qual é a sua?")
    for numero, conta in enumerate(contas[:6], start=1):
        print(f"    {numero}. {conta['nome']}")
    try:
        escolha = input("  Número (Enter para eu não escolher): ").strip()
    except (EOFError, KeyboardInterrupt):
        return None
    if not escolha.isdigit():
        return None
    indice = int(escolha) - 1
    return contas[indice] if 0 <= indice < len(contas) else None


# Depois de clicar, a página leva alguns segundos para trocar. Sem esta pausa o
# JARVIS clicaria no mesmo botão duas vezes — e no Google isso abre duas janelas
# de login, que é pior do que esperar.
ESPERA_DEPOIS_DO_CLIQUE = 3.0


def _tentar_entrar(args, estados: list[tuple[dict, dict, dict]], tentativas: dict) -> bool:
    """Um passo do login: clicar em “Google” ou na conta. Devolve se agiu."""
    from server import chave_web

    ultimo_em = tentativas.setdefault("ultimo_em", {})
    agora = time.time()

    # 1. escolha de conta do Google
    for janela, montada, estado in estados:
        if estado["estado"] != chave_web.ESTADO_GOOGLE or tentativas["conta"] >= 3:
            continue
        if agora - ultimo_em.get(chave_web.ESTADO_GOOGLE, -1e9) < ESPERA_DEPOIS_DO_CLIQUE:
            return True
        escolhida = estado.get("conta_escolhida")
        if escolhida is None:
            escolhida = _perguntar_conta(estado.get("contas") or [])
            if escolhida:
                _guardar_conta(_modulo_do_configurador(), escolhida["email"])
        if not escolhida:
            tentativas["conta"] += 1
            print("  escolha de conta: não sei qual é a sua — clique nela que eu sigo.")
            return True
        print(f"  escolha de conta: clicando em “{escolhida['nome']}”…")
        try:
            _clicar(
                janela,
                escolhida["no"],
                mouse=not args.sem_mouse,
                primeiro_mouse=not args.sem_mouse,
            )
        except PassoError as exc:
            print(f"    não deu: {exc}")
        tentativas["conta"] += 1
        ultimo_em[chave_web.ESTADO_GOOGLE] = agora
        return True

    # 2. tela de login do provedor → botão do Google
    for janela, montada, estado in estados:
        if estado["estado"] != chave_web.ESTADO_LOGIN or tentativas["google"] >= 3:
            continue
        if agora - ultimo_em.get(chave_web.ESTADO_LOGIN, -1e9) < ESPERA_DEPOIS_DO_CLIQUE:
            return True
        botoes = chave_web.procurar(montada, chave_web.PADROES_GOOGLE)
        if not botoes:
            tentativas["google"] += 1
            print("  tela de login: não achei o botão do Google — clique nele que eu sigo.")
            return True
        print("  tela de login: entrando pelo Google…")
        try:
            _clicar(
                janela,
                botoes[0],
                mouse=not args.sem_mouse,
                primeiro_mouse=not args.sem_mouse,
            )
        except PassoError as exc:
            print(f"    não deu: {exc}")
        tentativas["google"] += 1
        ultimo_em[chave_web.ESTADO_LOGIN] = agora
        return True
    return False


def _levar_ate_as_chaves(args, conta: str | None = None, segundos: float | None = None) -> tuple[dict, dict]:
    """Leva a janela do navegador até a página de chaves, atravessando o login.

    Medido nas telas do dono (0.91.14): abrir `openrouter.ai/keys` sem sessão cai
    em **Sign In**; o Google abre a **escolha de conta**; só depois aparece
    **API keys**. Três páginas na mesma janela — e o JARVIS tem de saber em qual
    está antes de clicar em qualquer coisa.
    """
    from server import chave_web

    # Sem conta dita aqui, vale a que veio na linha de comando (`--conta`).
    if conta is None:
        conta = str(getattr(args, "conta", "") or "")
    limite = time.time() + (args.espera_pagina if segundos is None else segundos)
    tentativas = {"google": 0, "conta": 0, "ultimo_em": {}}
    ultimo: dict | None = None
    while True:
        leituras = _ler_janelas(args.alvo)
        estados = [(janela, montada, chave_web.onde_estou(montada, conta=conta)) for janela, montada in leituras]
        for janela, montada, estado in estados:
            ultimo = estado
            if estado["estado"] == chave_web.ESTADO_CHAVES:
                return janela, montada
        if estados:
            _tentar_entrar(args, estados, tentativas)
        if time.time() >= limite:
            break
        time.sleep(1.0)

    if ultimo is None:
        raise PassoError("o navegador não abriu nenhuma janela a tempo. A página abriu em outro lugar?")
    if ultimo["estado"] == chave_web.ESTADO_LOGIN:
        raise PassoError(
            "a página abriu na tela de login e eu não consegui entrar. "
            "Entre você pelo Google (uma vez só) e rode de novo."
        )
    if ultimo["estado"] == chave_web.ESTADO_GOOGLE:
        raise PassoError(
            "estou parado na escolha de conta do Google. Diga qual é a sua com "
            "`--conta seuemail@gmail.com` que eu lembro para as próximas vezes."
        )
    raise PassoError(
        "não cheguei na página de chaves. O que a janela mostrou: "
        + chave_web.texto_do_estado(ultimo)
    )


def _garantir_na_frente(janela: dict, segundos: float = 2.0) -> bool:
    """Põe a janela na frente e **confirma** que ela está — pelo Windows.

    Por que confirmar: `SetForegroundWindow` pode voltar dizendo “ok” e o
    Windows não trocar nada (ele recusa quando quem pede está em segundo
    plano). Sem confirmar, o clique físico cairia numa janela coberta — e o
    primeiro clique só serviria para ativar a janela, não para apertar o botão.
    Era exatamente isso que fazia o “New key” não abrir o painel.
    """
    from server import arvore_windows

    handle = int(janela.get("handle") or 0)
    if not handle:
        return False
    fim = time.time() + segundos
    while True:
        try:
            arvore_windows.trazer_para_frente(handle)
        except Exception:  # noqa: BLE001 - COM de terceiros
            return False
        time.sleep(0.25)
        try:
            foco = arvore_windows.janela_em_foco() or {}
        except Exception:  # noqa: BLE001 - sem como confirmar, não atrapalha
            return True
        if int(foco.get("handle") or 0) == handle:
            return True
        if time.time() >= fim:
            return False


def _esperar_dialogo(args, janela: dict, segundos: float = 35.0, avisar: bool = True):
    """Espera o painel “Create API key” aparecer, com paciência e sem palpite.

    O que mudou depois do PC do dono (0.91.17): ele desistia em 12 segundos e,
    pior, desistia **por causa de uma leitura ruim** — uma passada em que o
    Chrome devolveu só a moldura. Duas correções:

    1. **35 segundos**, com aviso de progresso: carregar a página, ou o painel
       abrir, pode levar mais do que os 12 de antes — e esperar calado parece
       travamento;
    2. **leitura pobre não é resposta.** Cada tentativa relê pela fonte que
       mostra a página (ver `_reler`); só quando o painel não aparece em
       leitura boa é que ele conclui que não abriu.

    As outras janelas do navegador são conferidas a cada três tentativas — o
    clique pode abrir o painel na janela vizinha.
    """
    from server import chave_web

    inicio = time.time()
    fim = inicio + segundos
    if avisar:
        print(f"     esperando o painel abrir (até {int(segundos)}s; a página pode estar carregando)…")
    ultima = (janela, _reler(janela, PROFUNDA, TETO_FUNDO)[1])
    tentativa = 0
    while True:
        if chave_web.e_dialogo_de_criacao(ultima[1]):
            return ultima
        if time.time() >= fim:
            break
        tentativa += 1
        if tentativa % 3 == 0:
            for outra, montada_outra in _ler_janelas(
                args.alvo, profundidade=PROFUNDA, limite=TETO_FUNDO
            ):
                if int(outra.get("handle") or 0) == int(janela.get("handle") or 0):
                    continue
                if chave_web.e_dialogo_de_criacao(montada_outra):
                    return outra, montada_outra
        ultima = (janela, _reler(janela, PROFUNDA, TETO_FUNDO)[1])
        if tentativa % 4 == 0:
            print(
                f"     ainda procurando… ({int(time.time() - inicio)}s) — "
                f"a leitura trouxe {_nomes(ultima[1])} elementos."
            )
        time.sleep(1.0)
    relatorio = _gravar_relatorio(janela)
    raise PassoError(_diagnostico_da_leitura(ultima[1]) + relatorio["recado"])


def _gravar_relatorio(janela: dict, extra: list[str] | None = None) -> dict:
    """Grava, na pasta do JARVIS, o que cada fonte de leitura mostrou.

    Por que um arquivo: quando a leitura falha, a tela mostra só o veredito. O
    relatório guarda as três leituras — quantos elementos cada uma trouxe, o
    aviso delas e os primeiros nomes — que é o que permite descobrir a causa
    sem adivinhar.
    """
    from server import chave_web

    linhas = [
        "JARVIS — por que a leitura não achou o painel “Create API key”",
        f"quando: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}",
        f"janela: {str(janela.get('titulo') or '')!r} (handle {janela.get('handle')})",
        "",
    ]
    if extra:
        # O que cada clique tentou fazer. Quando o painel não abre, a pergunta
        # “o clique saiu?” se responde aqui, e não no chute.
        linhas.append("tentativas de clique:")
        linhas.extend(f"  {linha}" for linha in extra)
        linhas.append("")
    handle = int(janela.get("handle") or 0)
    for fonte in ("auto", "uia", "msaa"):
        try:
            montada = _ler_pela_fonte(handle, PROFUNDA, TETO_FUNDO, fonte)
        except Exception as exc:  # noqa: BLE001 - é diagnóstico, não pode derrubar
            linhas.append(f"{fonte:4}: erro {type(exc).__name__}: {exc}")
            linhas.append("")
            continue
        nos = chave_web.elementos(montada)
        linhas.append(
            f"{fonte:4}: {len(nos)} elemento(s) com nome, {montada.get('total')} nó(s), "
            f"fonte relatada {montada.get('fonte')!r}"
        )
        for chave in ("aviso", "nota", "de_filha", "dica"):
            valor = str(montada.get(chave) or "").strip()
            if valor:
                linhas.append(f"      {chave}: {valor}")
        if nos:
            linhas.append(
                "      primeiros: " + ", ".join(str(n.get("nome") or "")[:40] for n in nos[:40])
            )
        linhas.append("")
    caminho = Path(__file__).resolve().parent / "chave-leitura.txt"
    try:
        caminho.write_text("\n".join(linhas), encoding="utf-8")
    except OSError:
        return {"arquivo": "", "recado": ""}
    return {"arquivo": str(caminho), "recado": f" Detalhes em {caminho.name}."}


def _diagnostico_da_leitura(montada: dict, quantos: int = 12) -> str:
    """O que a leitura viu, em uma frase — para o dono poder mandar de volta.

    “o diálogo não apareceu” não diz nada a quem está olhando a tela com o
    diálogo aberto. Dizer quantos elementos vieram e quais os primeiros nomes
    transforma o mistério em uma linha copiável.
    """
    from server import chave_web

    nomes = [str(no.get("nome") or "")[:28] for no in chave_web.elementos(montada)[:quantos]]
    total = len(chave_web.elementos(montada))
    aviso = str(montada.get("aviso") or "").strip()
    texto = (
        f"o painel não apareceu na leitura ({total} elementos com nome, "
        f"fonte {montada.get('fonte') or '?'}, {montada.get('total')} nós"
    )
    texto += f"; os primeiros: {', '.join(nomes)})." if nomes else ")."
    if total < LEITURA_POBRE:
        texto += (
            " A leitura veio pobre — isso é a moldura do Chrome, não a página: "
            "pode ser a página ainda carregando ou o painel ainda abrindo."
        )
    if aviso:
        texto += f" Aviso da leitura: {aviso}"
    return texto


ROTULOS_DO_CRIAR = ("create", "criar", "confirmar", "confirm", "salvar", "save")


def _botao_de_criar(montada: dict) -> dict | None:
    """O botão que cria, e **não** o título do painel.

    “Create API key” também contém “create”. Quando o botão está apagado (o
    caso em que ele é justamente o que interessa), o título passava na frente na
    ordenação — e o script “clicava” no título e dizia que tinha tentado criar.
    Aqui o rótulo tem de ser **exatamente** criar/confirmar/salvar.
    """
    from server import chave_web

    for no in chave_web.procurar(montada, chave_web.PADROES_CONFIRMAR):
        if chave_web.normalizar(str(no.get("nome") or "")) in ROTULOS_DO_CRIAR:
            return no
    return None


def _esperar_botao_criar(janela: dict, segundos: float = 8.0):
    """Relê até o botão de criar aparecer. Devolve (janela, botão, árvore)."""
    fim = time.time() + segundos
    while True:
        janela, montada = _reler(janela, PROFUNDA, TETO_FUNDO)
        botao = _botao_de_criar(montada)
        if botao is not None:
            return janela, botao, montada
        if time.time() >= fim:
            ultima = _diagnostico_da_leitura(montada)
            raise PassoError(f"não achei o botão “Create” nesta leitura. {ultima}")
        time.sleep(0.8)


def _esperar_pagina_pronta(args, janela: dict, montada: dict, segundos: float = 18.0):
    """Espera a página parar de mudar antes de clicar em “New key”.

    Medido no PC do dono (0.91.17): a página abriu ainda carregando, o clique
    caiu num botão que a página trocou em seguida, e o painel nunca abriu —
    “ele tentou antes de a página ficar pronta”, nas palavras do dono.

    O sinal de “pronta” aqui é simples e não depende de palpite: o botão de
    criar está na leitura **e** duas leituras seguidas trazem praticamente os
    mesmos elementos. Não é garantia de fim de carregamento; é o suficiente
    para não clicar num botão que vai sumir.
    """
    from server import chave_web

    fim = time.time() + segundos
    anterior = -1
    avisou = False
    while True:
        agora = _nomes(montada)
        tem_botao = bool(chave_web.procurar(montada, chave_web.PADROES_CRIAR))
        if tem_botao and agora >= LEITURA_POBRE and abs(agora - anterior) <= 2:
            return janela, montada
        if time.time() >= fim:
            return janela, montada  # segue com o que há: quem clica diz o que deu
        if not avisou:
            print("     a página ainda está carregando — espero ela parar antes de clicar.")
            avisou = True
        anterior = agora
        time.sleep(1.0)
        janela, montada = _reler(janela, 8, 1500)


def _abrir_lista(
    janela: dict, montada, campo, *, mouse: bool, primeiro_mouse: bool, segundos: float = 5.0
):
    """Clica num campo de lista e devolve as opções que apareceram.

    Lista suspensa não muda nome de nada: ela **acrescenta** nós à janela. É
    comparando a leitura de antes com a de depois que se acham as opções — sem
    saber como o site as desenha. A leitura vai fundo: as opções moram no fim
    do documento, como o próprio diálogo.
    """
    from server import chave_web

    try:
        _clicar(janela, campo, mouse=mouse, primeiro_mouse=primeiro_mouse)
    except PassoError as exc:
        raise PassoError(f"não abri a lista “{campo.get('nome')}”: {exc}") from exc

    fim = time.time() + segundos
    while True:
        janela, depois = _reler(janela, PROFUNDA, TETO_FUNDO)
        opcoes = chave_web.nomes_novos(montada, depois)
        if opcoes:
            return janela, depois, opcoes
        if time.time() >= fim:
            return janela, depois, []
        time.sleep(0.6)


def _preencher_uma_lista(
    janela: dict,
    montada: dict,
    padroes: tuple[str, ...],
    regra,
    rotulo: str,
    *,
    mouse: bool,
    primeiro_mouse: bool,
) -> tuple[dict, str]:
    """Abre a lista do diálogo, escolhe pela regra e devolve (leitura nova, escolha).

    Devolve `(montada, "")` quando não achou o campo ou não deu para escolher —
    quem chama diz o que ficou faltando, em vez de fingir que preencheu.
    """
    from server import chave_web

    campos = chave_web.procurar(montada, padroes)
    if not campos:
        print(f"     {rotulo}: não achei o campo nesta tela.")
        return montada, ""
    campo = campos[0]
    print(f"     {rotulo}: abrindo “{str(campo.get('nome') or '')[:40]}”…")
    try:
        janela, aberta, opcoes = _abrir_lista(
            janela, montada, campo, mouse=mouse, primeiro_mouse=primeiro_mouse
        )
    except PassoError as exc:
        print(f"     {rotulo}: {exc}")
        return montada, ""

    nomes = [str(opcao.get("nome") or "") for opcao in opcoes]
    escolha = regra(nomes)
    if not escolha:
        print(f"     {rotulo}: a lista abriu com {len(nomes)} opções e nenhuma serve — deixei como estava.")
        return aberta, ""
    alvo = next((opcao for opcao in opcoes if str(opcao.get("nome") or "") == escolha), None)
    if alvo is None:
        return aberta, ""
    print(f"     {rotulo}: escolhendo “{escolha}”.")
    try:
        _clicar(janela, alvo, mouse=mouse, primeiro_mouse=primeiro_mouse)
    except PassoError as exc:
        print(f"     {rotulo}: não consegui clicar na opção ({exc}).")
        return aberta, ""
    time.sleep(0.5)
    return _reler(janela, PROFUNDA, TETO_FUNDO)[1], escolha


def _digitar_substituindo(janela: dict, texto: str) -> bool:
    """`Ctrl+A` e depois digita — troca o conteúdo do campo em vez de somar.

    Serve para o caso em que a primeira escrita pode ter ido para outro lugar:
    sem o `Ctrl+A`, tentar de novo escreveria “jarvis-testejarvis-teste”.
    """
    from server import arvore_windows, mesa

    handle = int(janela.get("handle") or 0)
    if not handle or not _garantir_na_frente(janela):
        return False
    try:
        if not arvore_windows.teclado_na_janela(handle):
            return False
        mesa.teclar("ctrl+a")
        mesa.digitar(texto)
        return True
    except Exception:  # noqa: BLE001 - último degrau, não requisito
        return False


def _digitar_na_janela(janela: dict, texto: str) -> bool:
    """Digita com o teclado na janela **depois de conferir que ela está na frente**.

    Só serve quando o foco já está no campo certo — que é o caso do diálogo de
    criação, onde o cursor nasce dentro do “Name”. Se o teclado não estiver na
    janela do navegador, não digita às cegas: devolve `False`.
    """
    from server import arvore_windows, mesa

    try:
        handle = int(janela.get("handle") or 0)
        if not arvore_windows.trazer_para_frente(handle):
            return False
        if not arvore_windows.teclado_na_janela(handle):
            return False
        mesa.digitar(texto)
        return True
    except Exception:  # noqa: BLE001 - digitar é o último degrau, não requisito
        return False


def _nome_aparece(montada: dict, texto: str) -> bool:
    """O nome digitado aparece na leitura? (uns Chrome publicam o valor, outros não)"""
    from server import chave_web

    alvo = chave_web.normalizar(texto)
    if not alvo:
        return False
    return any(alvo in chave_web.normalizar(str(no.get("nome") or "")) for no in chave_web.elementos(montada))


def _escrever_no_campo(
    janela: dict, campo: dict, texto: str, *, mouse: bool
) -> tuple[bool, str, bool | None]:
    """Digita num campo e **confere**. Devolve (deu certo, como, conferido).

    Três degraus, e o segundo só existe porque o primeiro pode mentir:

    1. **clique no campo + teclado** — é o que uma pessoa faz;
    2. **foco pela árvore** (`accSelect`/`put_accValue`) — quando o clique cai
       num lugar que não aceita foco;
    3. **teclado com a janela na frente** — último recurso, com o diálogo que
       nasce com o cursor no campo.

    Cada degrau devolve `conferido`: `True` (o campo mostra o texto), `False`
    (o campo publica valor e ele é outro) ou `None` (o campo não publica valor).
    Sem esta conferência, o script dizia “escrevendo…” e seguia com o campo
    vazio — foi o que aconteceu no PC do dono.
    """
    tentativas = [
        ("clique no campo + teclado", {"mouse": mouse, "primeiro_mouse": mouse}),
        ("foco pela árvore", {"mouse": False, "primeiro_mouse": False}),
    ]
    for rotulo, opcoes in tentativas:
        try:
            feito = _clicar(janela, campo, "digitar", texto, **opcoes)
        except PassoError as exc:
            print(f"     ({rotulo} não deu: {exc})")
            continue
        conferido = feito.get("conferido")
        if conferido is True:
            return True, rotulo, True
        print(f"     ({rotulo}: {_descrever_clique(feito)}"
              + ("" if conferido is None else " — mas o campo não mostra o texto") + ")")
        if conferido is None:
            # O campo não publica valor: a leitura é o único juiz que sobrou.
            # Se nem ela mostra o texto, **não se repete**: digitar de novo com o
            # cursor no fim do campo escreveria o nome duas vezes. Fica a prova
            # que existe no fim do painel — o botão “Create” acender.
            try:
                _janela, depois = _reler(janela, PROFUNDA, TETO_FUNDO)
            except PassoError:
                depois = None
            if depois is not None and _nome_aparece(depois, texto):
                return True, rotulo, True
            return True, rotulo, None
    if _digitar_na_janela(janela, texto):
        try:
            _janela, depois = _reler(janela, PROFUNDA, TETO_FUNDO)
        except PassoError:
            depois = None
        if depois is not None and _nome_aparece(depois, texto):
            return True, "teclado com a janela na frente", True
        return True, "teclado com a janela na frente", None
    return False, "", False


def _preencher_dialogo(
    janela: dict, montada: dict, nome: str, *, mouse: bool, primeiro_mouse: bool
) -> tuple[dict, dict[str, str]]:
    """Preenche “Create API key” inteiro: nome, expiração e limite.

    Medido na tela do dono: o botão “Create” fica desabilitado enquanto a
    expiração (que tem asterisco) está vazia. Escrever só o nome e clicar em
    Create não cria nada — e antes da 0.91.15 o script dizia que tinha dado
    certo. Aqui cada campo devolve o que foi **conferido**, não o que foi
    tentado.
    """
    from server import chave_web

    preenchidos: dict[str, str] = {}
    nome_conferido = False

    # 1. nome — na **caixa**, não no rótulo ao lado
    campo = chave_web.campo_do_nome(montada)
    if campo is not None:
        print(f"     nome: escrevendo “{nome}” no campo…")
        deu, como, conferido = _escrever_no_campo(janela, campo, nome, mouse=mouse)
        if deu:
            preenchidos["nome"] = nome
            nome_conferido = bool(conferido)
            if conferido:
                print(f"     nome: digitado e conferido ({como}).")
            else:
                print(f"     nome: digitado ({como}) — o campo não publica o valor, então")
                print("           quem confirma é o botão “Create” acender no fim.")
        else:
            print("     nome: NÃO consegui escrever no campo.")
    else:
        print("     nome: a leitura não trouxe nenhuma caixa de texto no painel.")
        if _digitar_na_janela(janela, nome):
            preenchidos["nome"] = nome
            nome_conferido = _nome_aparece(montada, nome)
            print(f"     nome: digitado pelo teclado (“{nome}”).")
        else:
            print("     nome: o teclado não estava na janela — não digitei às cegas.")

    janela, montada = _reler(janela, PROFUNDA, TETO_FUNDO)

    # 2. expiração — o campo que deixava o Create apagado
    montada, prazo = _preencher_uma_lista(
        janela, montada, chave_web.PADROES_EXPIRACAO, chave_web.melhor_expiracao, "expiração",
        mouse=mouse, primeiro_mouse=primeiro_mouse,
    )
    if prazo:
        preenchidos["expiração"] = prazo

    # 3. limite de crédito — não é para caber mais, é para não travar sozinho
    montada, limite = _preencher_uma_lista(
        janela, montada, chave_web.PADROES_LIMITE, chave_web.melhor_limite, "limite",
        mouse=mouse, primeiro_mouse=primeiro_mouse,
    )
    if limite:
        preenchidos["limite"] = limite

    # 4. a prova final é o botão “Create”: apagado = falta campo. Se o nome foi
    #    escrito sem confirmação (o campo não publica valor), ele é o suspeito
    #    número um — e reescrever do zero é barato.
    if "nome" in preenchidos and not nome_conferido:
        try:
            janela, montada = _reler(janela, PROFUNDA, TETO_FUNDO)
        except PassoError:
            return montada, preenchidos
        botao = _botao_de_criar(montada)
        if botao is not None and not botao.get("acionavel"):
            print("     o botão “Create” continua apagado — reescrevo o nome do zero.")
            if _digitar_substituindo(janela, nome):
                print(f"     nome: reescrito (“{nome}”), apagando o que estivesse no campo.")
                janela, montada = _reler(janela, PROFUNDA, TETO_FUNDO)
    return montada, preenchidos


def _criar_e_copiar(
    args, modulo, janela, montada, dados, *, mouse: bool, primeiro_mouse: bool, anterior: str
) -> str | None:
    """Os quatro cliques e a cópia. Devolve a chave, ou `None` dizendo onde parou."""
    from server import chave_web

    nome = args.nome or chave_web.nome_sugerido()

    # 0. a página pronta — a 0.91.16 clicou num botão que a página ainda ia
    #    trocar, e o painel nunca abriu. Clicar cedo demais é o mesmo que não
    #    clicar: o efeito se perde quando a página termina de montar.
    janela, montada = _esperar_pagina_pronta(args, janela, montada)

    # 1. Create Key — com uma escada, porque no Chrome a “ação do elemento”
    #    mente: `accDoDefaultAction` devolve sucesso e a página não faz nada.
    #    Medido no PC do dono (0.91.17): duas esperas de 35 s depois de duas
    #    “ações” que não abriram nada. O que abre o painel é o clique do mouse,
    #    que só era tentado com `--mouse` — e o `.bat` não passa `--mouse`.
    #
    #    A ordem agora é: clique do mouse → clique do mouse outra vez (o
    #    primeiro pode só ativar a janela) → ação do elemento. Cada degrau é
    #    conferido: se o painel abriu, para ali.
    plano = [
        ("mouse", 12.0, "clique do mouse"),
        ("mouse", 12.0, "clique do mouse, segunda vez"),
        ("acao", 10.0, "ação do elemento"),
    ]
    if not mouse:
        plano = [("acao", 20.0, "ação do elemento")]
    falha = None
    cliques: list[str] = []
    # Quantos nomes a página tinha ao achar o botão: é a régua para saber se uma
    # leitura nova “despencou”. Não é um número absoluto — página pequena vale.
    referencia = _nomes(montada)
    for degrau, (estrategia, espera, rotulo) in enumerate(plano, start=1):
        if degrau > 1:
            try:
                janela, montada = _reler(janela, PROFUNDA, TETO_FUNDO)
            except PassoError:
                montada = None
            if montada is not None and chave_web.e_dialogo_de_criacao(montada):
                break
            if montada is None or not chave_web.procurar(montada, chave_web.PADROES_CRIAR):
                break
            if referencia and _nomes(montada) * 2 < referencia:
                # Leitura que despencou: não se sabe o que há na tela, e repetir
                # poderia abrir um painel em cima do outro.
                print("     a leitura despencou — não repito o clique sem saber o que está na tela.")
                break
        achados = chave_web.procurar(montada, chave_web.PADROES_CRIAR) if montada else []
        if not achados:
            print("  1. NÃO DEI: o botão de criar não está na árvore desta janela.")
            return None
        botao = achados[0]
        if estrategia == "mouse" and not _garantir_na_frente(janela):
            print("     não consegui pôr a janela na frente — o clique pode só ativá-la.")
            cliques.append("janela não veio para a frente")
        print(f"  1. clicando em “{botao.get('nome')}” ({rotulo})…")
        try:
            feito = _clicar(
                janela,
                botao,
                mouse=mouse,
                primeiro_mouse=(estrategia == "mouse"),
            )
            print(f"     {_descrever_clique(feito)}")
            cliques.append(f"{rotulo}: {_descrever_clique(feito)}")
        except PassoError as exc:
            # Clique **recusado** é outra coisa de clique que não abriu nada: o
            # Windows disse não (janela coberta, ponto fora). Repetir do mesmo
            # jeito não muda a resposta — para aqui e diz o motivo, como desde
            # a 0.91.10.
            print(f"  1. NÃO DEI: {exc}")
            cliques.append(f"{rotulo}: {exc}")
            _gravar_relatorio(janela, extra=[f"clique {item}" for item in cliques])
            return None
        time.sleep(1.2)

        # 2. o diálogo inteiro: nome, expiração e limite de crédito.
        #    Medido na tela do dono: sem a expiração (que tem asterisco) o botão
        #    “Create” fica desabilitado, e clicar nele não cria nada.
        try:
            janela, montada = _esperar_dialogo(args, janela, segundos=espera, avisar=(degrau == 1))
            break
        except PassoError as exc:
            falha = exc
            continue
    if falha is not None and (montada is None or not chave_web.e_dialogo_de_criacao(montada)):
        # Sem o diálogo não há o que preencher: seguir daqui faria o passo 3
        # achar o botão “New key” da página e clicar nele outra vez, e o
        # relatório diria “criei” sem ter criado nada.
        # O relatório é reescrito com a escada de cliques dentro (o recado do
        # arquivo já vem na mensagem de `falha`).
        _gravar_relatorio(janela, extra=[f"clique {item}" for item in cliques])
        print(f"  2. NÃO DEI: {falha}")
        print("     Nada foi criado. O clique não abriu o painel — isso não é mais leitura:")
        print("     a página foi lida inteira e o botão estava nela. Feche o que estiver na")
        print("     frente do Chrome (eu coloco a janela na frente, mas o Windows recusa")
        print("     enquanto outro programa tem o foco) e rode de novo.")
        return None
    print("  2. preenchendo o diálogo:")
    montada, preenchidos = _preencher_dialogo(
        janela, montada, nome, mouse=mouse, primeiro_mouse=primeiro_mouse
    )
    antes = _nomes(montada)
    # O nome entra na conta: sem ele o “Create” também fica apagado, e a
    # mensagem tem de dizer **qual** campo faltou.
    faltando = [campo for campo in ("nome", "expiração", "limite") if campo not in preenchidos]
    if "expiração" in faltando:
        print("     AVISO: sem a expiração o botão Create costuma ficar apagado.")
        print("     Se a chave não nascer, escolha a expiração você mesmo e rode `--pegar`.")

    # 3. o botão do diálogo (“Create”, curto) — e a conferência de que fechou
    try:
        janela, criar, montada = _esperar_botao_criar(janela, segundos=8)
        if not criar.get("acionavel"):
            # Botão apagado = os três campos não estão preenchidos. Clicar nele
            # não gera erro e não cria nada; o script já fez isso duas vezes e
            # o dono ficou olhando uma tela parada. Aqui ele para e diz o que
            # falta, em vez de esperar o milagre.
            print("  3. o botão “Create” está APAGADO — clicar nele não criaria nada.")
            if faltando:
                print(f"     campos que eu não consegui preencher: {', '.join(faltando)}.")
            else:
                print("     os três campos parecem preenchidos; o site pode exigir algo a mais.")
            _gravar_relatorio(janela, extra=["o botão Create estava desativado (desativado=True na leitura)"])
            print("     Complete no navegador e rode `--pegar`; não precisa refazer o resto.")
            return None
        print(f"  3. clicando em “{criar.get('nome')}” para criar…")
        print(f"     {_descrever_clique(_clicar(janela, criar, mouse=mouse, primeiro_mouse=primeiro_mouse))}")
        time.sleep(2.0)
    except PassoError as exc:
        print(f"  3. NÃO DEI: {exc}")
        print("  A chave pode ter ficado criada e não copiada. Veja no navegador.")
        return None

    # O clique pode ter caído num botão desabilitado: isso não gera erro, o
    # diálogo simplesmente continua aberto. Conferir é o que separa “criei” de
    # “achei que criei”.
    try:
        _janela, depois = _reler(janela, PROFUNDA, TETO_FUNDO)
    except PassoError:
        depois = None
    # Leitura que despencou não prova nada sobre o painel: se antes vinham 43
    # elementos e agora vêm 3, o que falhou foi a leitura — não o clique. Nesse
    # caso não se conclui nem “criou” nem “não criou”: segue para a cópia, e a
    # cópia é quem diz a verdade (chave na área = criou).
    if depois is not None and _nomes(depois) < LEITURA_POBRE and _nomes(depois) * 2 < antes:
        print("  3. a leitura despencou agora; não dá para conferir pelo painel — vou pela cópia.")
        depois = None
    if depois and chave_web.e_dialogo_de_criacao(depois):
        print("  3. o diálogo CONTINUA aberto — a chave não foi criada.")
        if faltando:
            print(f"     campos que eu não consegui preencher: {', '.join(faltando)}.")
        print("     Complete no navegador e rode `--pegar`; não precisa refazer nada.")
        return None

    # 4. copiar — primeiro o texto da página (não depende de botão nenhum),
    #    depois o botão “Copy”, se ele existir.
    #
    # `anterior` vem de **antes do primeiro clique**: se for lido aqui, o texto
    # que o próprio clique em “Create” pôs na área já seria confundido com “o
    # que estava lá”, e a chave nova seria recusada por ser igual à nova.
    copiou = False
    if _copiar_pela_pagina(janela):
        print("  4. copiando o texto da página (Ctrl+A, Ctrl+C)…")
        copiou = True
    else:
        print("  4. não consegui copiar pela página — tentando o botão “Copy”…")
    if copiou:
        achado = _esperar_chave(modulo, anterior, segundos=6)
        if achado:
            return achado[1]
    try:
        janela, copiar, _ = _esperar_elemento(janela, chave_web.PADROES_COPIAR, segundos=6)
        print(f"     clicando em “{copiar.get('nome')}”…")
        print(f"     {_descrever_clique(_clicar(janela, copiar, mouse=mouse, primeiro_mouse=primeiro_mouse))}")
    except PassoError as exc:
        print(f"  4. NÃO DEI: {exc}")
        return None
    achado = _esperar_chave(modulo, anterior, segundos=10)
    return achado[1] if achado else None


def passo_criar(args) -> int:
    """Cria uma chave nova: clica, nomeia, cria e copia. Gated por --autorizar."""
    from server import chave_web

    janela, montada = _ler_janela(args.alvo)
    estado = chave_web.onde_estou(montada, conta=getattr(args, "conta", ""))
    print(chave_web.texto_do_estado(estado))
    dados = chave_web.diagnostico(montada)
    print(chave_web.texto_do_diagnostico(dados))
    print()
    if estado["estado"] in (chave_web.ESTADO_LOGIN, chave_web.ESTADO_GOOGLE):
        print("  Estou numa página de login, não na das chaves — `--criar` não entra sozinho.")
        print("  Use `--auto --autorizar`, que atravessa o login e só então cria.")
        return 1
    if not dados["pode_criar"]:
        print("  Parei aqui: sem o botão de criar na árvore, não há o que clicar.")
        print("  Caminho que funciona sempre: crie no navegador e rode `--pegar`.")
        return 1
    if not args.autorizar:
        print("  Isto VAI CRIAR uma chave nova na sua conta (é uma credencial de verdade).")
        print("  Repita com --autorizar para fazer.")
        return 0

    modulo = _modulo_do_configurador()
    mouse = not args.sem_mouse
    if args.mouse and args.sem_mouse:
        print("  Escolha um: --mouse ou --sem-mouse (os dois juntos não dizem nada).")
        return 2
    _explicar_mouse(mouse, dados)
    print()

    chave = _criar_e_copiar(
        args,
        modulo,
        janela,
        montada,
        dados,
        mouse=mouse,
        primeiro_mouse=mouse,
        anterior=_texto_da_area(),
    )
    if not chave:
        print("\n  Não consegui a chave. Se ela está na tela, clique em COPIAR e rode `--pegar`.")
        return 1
    return _gravar(modulo, chave)


def _explicar_mouse(mouse: bool, dados: dict) -> None:
    if mouse:
        print("  Vou clicar com o mouse nos botões medidos; o cursor volta para onde estava.")
        if not dados.get("pode_clicar_com_mouse"):
            print("  (sem posição medida na leitura, o clique será pela ação do elemento.)")
    else:
        print("  --sem-mouse: só a ação do elemento, o ponteiro não se mexe.")


def passo_auto(args) -> int:
    """O caminho inteiro num comando: abrir → criar → copiar → gravar.

    É o que o dono pediu na 0.91.12: “ele deve abrir os sites onde estão as
    chaves para ele poder copiar e colar na própria pasta”.

    Três coisas que fazem este modo ser honesto:

    - se a criação automática não der, ele **não desiste**: deixa a página
      aberta, diz o que falta clicar e fica esperando a área de transferência;
    - nada é criado sem `--autorizar`;
    - o que já estava copiado antes não é confundido com a chave nova.
    """
    from server import chave_web

    if not args.autorizar:
        print("  Isto VAI CRIAR uma chave nova na sua conta e gravar no .env.")
        print("  Repita com --autorizar para fazer.")
        return 0

    modulo = _modulo_do_configurador()
    provedor, base = _provedor_do_env(modulo)
    provedor = args.provedor or provedor
    if not provedor:
        print("  Não sei qual provedor: o .env não tem nenhum e você não passou --provedor.")
        return 1
    guia = modulo.guia_do_provedor(provedor, base)
    if not guia.get("onde"):
        print(f"  Não sei onde ficam as chaves do provedor “{provedor}”.")
        return 1

    anterior = _texto_da_area()
    print(f"  Provedor: {guia['nome']}")
    print(f"  Página das chaves: {guia['onde']}")
    if _chave_no_texto(modulo, anterior):
        print("  (havia uma chave copiada antes; ela não vai ser confundida com a nova.)")
    print()
    print("  1. abrindo a página no seu navegador…")
    if not modulo.abrir_no_navegador(guia["onde"]):
        print(f"  NÃO DEI: não consegui abrir o navegador. Abra na mão: {guia['onde']}")
        return 1

    conta = (args.conta or _conta_do_env(modulo)).strip()
    if conta:
        print(f"  Conta do Google: {conta}")
    print()

    chave = ""
    try:
        janela, montada = _levar_ate_as_chaves(args, conta=conta)
        if args.conta:
            for item in chave_web.contas_visiveis(montada):
                if chave_web.casar_conta([item], args.conta):
                    _guardar_conta(modulo, item["email"])
                    break
        dados = chave_web.diagnostico(montada)
        if dados["pode_criar"]:
            # A janela é trazida para a frente antes de qualquer clique: o
            # clique físico acerta o que está por cima, e por cima pode estar
            # qualquer coisa do dono.
            from server import arvore_windows

            arvore_windows.trazer_para_frente(int(janela["handle"]))
            print("  2. página aberta. Vou criar a chave sozinho…")
            print()
            mouse = not args.sem_mouse
            _explicar_mouse(mouse, dados)
            chave = _criar_e_copiar(
                args,
                modulo,
                janela,
                montada,
                dados,
                mouse=mouse,
                primeiro_mouse=mouse,
                anterior=anterior,
            ) or ""
        else:
            print("  2. cheguei na página, mas os botões não estão na árvore de acessibilidade.")
            print("     Então eu não clico: eu espero você clicar.")
    except PassoError as exc:
        print(f"  2. NÃO DEI: {exc}")

    if not chave:
        # Plano B, no mesmo comando: o dono clica, o JARVIS lê.
        print()
        print("  No site, com a sua conta:")
        print("     Create Key → dê um nome → Create → clique no botão COPIAR")
        print()
        print(f"  Estou olhando a área de transferência por {int(args.espera_colar)}s…")
        achado = _esperar_chave(modulo, anterior, segundos=args.espera_colar)
        if not achado:
            print("  NÃO DEU: nada novo apareceu na área de transferência.")
            print("  Copie a chave pelo botão e rode `--pegar` — não precisa refazer o resto.")
            return 1
        chave = achado[1]

    print()
    print(f"  Chave na mão: {modulo.mascarar(chave)}")
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
    parser.add_argument(
        "--auto",
        action="store_true",
        help="O caminho inteiro: abre a página, cria, copia e grava. Exige --autorizar.",
    )
    parser.add_argument("--provedor", default="", help="Provedor cujo site abrir (padrão: o do .env).")
    parser.add_argument(
        "--conta",
        default="",
        help="Pedaco do e-mail do Google usado para entrar (fica lembrado no .env).",
    )
    parser.add_argument("--espera-pagina", type=float, default=25.0, help="Segundos esperando a página abrir.")
    parser.add_argument("--espera-colar", type=float, default=120.0, help="Segundos esperando você copiar no site.")
    parser.add_argument("--autorizar", action="store_true", help="Sem isto, --criar só mostra o que faria.")
    parser.add_argument("--nome", default="", help="Nome da chave criada (padrão: jarvis-AAAA-MM-DD).")
    parser.add_argument(
        "--sem-mouse",
        action="store_true",
        help="Não usa o mouse: só a ação do elemento. O padrão do --criar é poder clicar.",
    )
    parser.add_argument(
        "--mouse",
        action="store_true",
        help="(já é o padrão no --criar) Autoriza o clique físico nos botões medidos.",
    )
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
        if args.auto:
            return passo_auto(args)
        if args.pegar:
            return passo_pegar(args)
        if args.criar:
            return passo_criar(args)
        return passo_ver(args)
    except PassoError as exc:
        print(f"  NÃO DEU: {exc}")
        return 1
    except KeyboardInterrupt:
        # Ctrl+C é do dono, não é defeito. Sem isto, o Windows mostrava um
        # traceback de 8 linhas e o `.bat` seguia como se tivesse dado certo.
        print("\n  Interrompido com Ctrl+C. Nada foi gravado.")
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
