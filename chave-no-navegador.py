#!/usr/bin/env python3
"""Criar a chave de IA pelo navegador, com o JARVIS clicando.

## O que isto faz — e o que não faz

A chave **não está** na página de chaves: o OpenRouter mostra o valor uma única
vez, no instante da criação, e depois só o prefixo mascarado. Não existe ler a
chave que já existe — por isso este script não promete isso.

O que ele faz é o caminho de **criar uma nova**, em passos medidos:

    --auto --autorizar      abre o site, cria, copia e grava — o comando único
    --abrir                 abre a página de chaves no seu navegador
    --ver                   LÊ a página e diz quais botões existem (não clica)
    --pegar                 lê a área de transferência e grava no .env
    --criar --autorizar     clica "Create Key", dá um nome, cria e copia

O `--auto` pega o provedor do `.env` (ou de `--provedor`) e abre **o site dele**:
openrouter.ai/keys, console.groq.com/keys, aistudio.google.com/apikey e assim
por diante. Se os botões não estiverem na árvore de acessibilidade, ele não
termina em erro: deixa a página aberta, diz o que falta clicar e fica esperando
a chave aparecer na área de transferência.

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
    return _gravar(modulo, chave)


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


def _esperar_pagina(alvo: str, segundos: float = 25.0):
    """Espera a janela do navegador aparecer **e** ser a página de chaves.

    Abrir o navegador não é instantâneo, e a primeira leitura de uma janela
    recém-aberta costuma vir pobre (o Chrome liga a árvore quando percebe um
    programa de acessibilidade olhando). Ler uma vez e desistir seria medir o
    navegador no meio do espirro.

    Se nenhuma janela for a página de chaves, devolve a última leitura — quem
    chamou mostra o diagnóstico dela em vez de inventar que a página não abriu.
    """
    from server import arvore, arvore_windows, chave_web

    fim = time.time() + segundos
    ultima = None
    while True:
        for janela in _janelas_do_alvo(alvo)[:3]:
            try:
                bruto = arvore_windows.ler_janela(int(janela["handle"]), 8, 1500)
            except Exception:  # noqa: BLE001 - janela que fechou no meio
                continue
            montada = arvore.montar(bruto, 8, 1500, com_caminho=True)
            ultima = (janela, montada)
            if chave_web.e_pagina_de_chaves(montada):
                return janela, montada
        if time.time() >= fim:
            break
        time.sleep(1.0)
    if ultima:
        return ultima
    raise PassoError(
        "o navegador não abriu nenhuma janela a tempo. A página abriu em outro lugar?"
    )


def _criar_e_copiar(
    args, modulo, janela, montada, dados, *, mouse: bool, primeiro_mouse: bool, anterior: str
) -> str | None:
    """Os quatro cliques e a cópia. Devolve a chave, ou `None` dizendo onde parou."""
    from server import chave_web

    nome = args.nome or chave_web.nome_sugerido()

    # 1. Create Key
    achados = chave_web.procurar(montada, chave_web.PADROES_CRIAR)
    if not achados:
        print("  1. NÃO DEI: o botão de criar não está na árvore desta janela.")
        return None
    botao = achados[0]
    print(f"  1. clicando em “{botao.get('nome')}”…")
    try:
        print(f"     {_descrever_clique(_clicar(janela, botao, mouse=mouse, primeiro_mouse=primeiro_mouse))}")
    except PassoError as exc:
        print(f"  1. NÃO DEI: {exc}")
        return None
    time.sleep(1.5)

    # 2. nome (quando o diálogo pede)
    try:
        janela, campo, _ = _esperar_elemento(args.alvo, chave_web.PADROES_NOME, segundos=8)
        print(f"  2. escrevendo o nome “{nome}” em “{campo.get('nome')}”…")
        print(f"     {_descrever_clique(_clicar(janela, campo, 'digitar', nome, mouse=mouse, primeiro_mouse=primeiro_mouse))}")
        time.sleep(0.8)
    except PassoError:
        print("  2. não apareceu campo de nome — seguindo (alguns fluxos não pedem).")

    # 3. o botão do diálogo (“Create”, curto)
    try:
        janela, criar, montada = _esperar_elemento(args.alvo, chave_web.PADROES_CONFIRMAR, segundos=8)
        print(f"  3. clicando em “{criar.get('nome')}” para criar…")
        print(f"     {_descrever_clique(_clicar(janela, criar, mouse=mouse, primeiro_mouse=primeiro_mouse))}")
        time.sleep(2.0)
    except PassoError as exc:
        print(f"  3. NÃO DEI: {exc}")
        print("  A chave pode ter ficado criada e não copiada. Veja no navegador.")
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
        janela, copiar, _ = _esperar_elemento(args.alvo, chave_web.PADROES_COPIAR, segundos=6)
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
        primeiro_mouse=args.mouse,
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

    chave = ""
    try:
        janela, montada = _esperar_pagina(args.alvo, segundos=args.espera_pagina)
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
                primeiro_mouse=args.mouse,
                anterior=anterior,
            ) or ""
        else:
            print("  2. a página abriu, mas os botões não estão na árvore de acessibilidade.")
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


if __name__ == "__main__":
    raise SystemExit(main())
