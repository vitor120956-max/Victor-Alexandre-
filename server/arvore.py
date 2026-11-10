"""A árvore de acessibilidade da janela em foco — **só leitura** (0.82.0).

## Por que este módulo existe

O `mesa.py` só enxerga **títulos de janela**. Para clicar, ele precisa da
coordenada x,y que *você* informa — e depois não sabe se acertou. Foi o que o
`vercel-labs/agent-desktop` mostrou com clareza
([análise](docs/ANALISE-AGENT-DESKTOP.md)): o certo é ler a **árvore de
acessibilidade** que o próprio Windows publica, dar um `ref` a cada elemento e
agir por `ref`, conferindo com uma leitura nova.

Esta é a **etapa 1**: ler a árvore e devolver JSON. Ela **não** clica, **não**
digita, **não** move o mouse e **não** tira foto da tela. Serve para descobrir,
no seu PC, **quais programas expõem árvore** — Chrome? WhatsApp? o Explorer? —
antes de qualquer ação existir.

## O que “ler a árvore” significa aqui

No Windows, `oleacc.dll` expõe a interface **IAccessible** (MSAA) de cada janela:
o programa declara “aqui há um botão chamado Salvar, nesta posição”. É o mesmo
canal que o Narrador e o NVDA usam — por isso funciona sem instalar nada.

O leitor é conservador de propósito:

- **profundidade e total limitados** (padrão 6 e 600): aplicativo grande devolve
  milhares de nós, e o que interessa são os acionáveis;
- o que foi cortado é **dito**: `completo: false` e o motivo, em vez de fingir
  que a árvore acabou;
- **roda em outro processo** (`arvore_sonda.py`): a leitura de acessibilidade
  conversa com código de terceiros por COM, e um programa malcomportado pode
  derrubar o processo. Derrubar uma sonda descartável é aceitável; derrubar a API
  do JARVIS no meio de uma conversa não é.

## O que ainda não faz (e por que)

Clicar por `ref` é a **etapa 2** — só depois que esta etapa provar, no seu PC,
que os programas que você usa publicam árvore. Prometer clique sem ter medido a
árvore seria repetir o erro das versões anteriores (tela velha, quatro chaves).
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable, Protocol

RAIZ = Path(__file__).resolve().parents[1]
SONDA = RAIZ / "arvore_sonda.py"

PROFUNDIDADE_PADRAO = 6
PROFUNDIDADE_MAX = 14
LIMITE_PADRAO = 600
LIMITE_MAX = 3000

# Papéis (ROLE_SYSTEM_*) que valem um `ref`: são os que se pode acionar.
ACIONAVEIS = {
    12,  # menuitem
    28,  # row
    29,  # cell
    30,  # link
    34,  # listitem
    37,  # pagetab
    43,  # pushbutton
    44,  # checkbutton
    45,  # radiobutton
    46,  # combobox
    47,  # droplist
    51,  # slider
    56,  # buttondropdown
    57,  # buttonmenu
    62,  # splitbutton
    64,  # outlinebutton
}

# Nome do papel em português. A tabela é fechada: papel desconhecido aparece
# como “elemento 99”, não como um nome inventado.
PAPEIS = {
    1: "barra de título",
    2: "menu",
    3: "barra de rolagem",
    4: "alça",
    7: "cursor",
    8: "alerta",
    9: "janela",
    10: "área do cliente",
    11: "menu suspenso",
    12: "item de menu",
    13: "dica",
    14: "aplicativo",
    15: "documento",
    16: "painel",
    17: "gráfico",
    18: "diálogo",
    19: "borda",
    20: "grupo",
    21: "separador",
    22: "barra de ferramentas",
    23: "barra de status",
    24: "tabela",
    25: "cabeçalho de coluna",
    26: "cabeçalho de linha",
    27: "coluna",
    28: "linha",
    29: "célula",
    30: "link",
    31: "balão de ajuda",
    32: "caractere",
    33: "lista",
    34: "item de lista",
    35: "estrutura",
    36: "item de estrutura",
    37: "aba",
    38: "página de propriedades",
    39: "indicador",
    40: "imagem",
    41: "texto estático",
    42: "texto",
    43: "botão",
    44: "caixa de seleção",
    45: "botão de opção",
    46: "caixa de combinação",
    47: "lista suspensa",
    48: "barra de progresso",
    49: "mostrador",
    50: "campo de atalho",
    51: "controle deslizante",
    52: "botão de giro",
    53: "diagrama",
    54: "animação",
    55: "equação",
    56: "botão com lista",
    57: "menu de botão",
    58: "grade de botões",
    59: "espaço",
    60: "lista de abas",
    61: "relógio",
    62: "botão dividido",
    63: "endereço IP",
    64: "botão de estrutura",
}


class ArvoreError(ValueError):
    """Não deu para ler: sistema errado, alvo não achado, ou sonda falhou."""


class Leitor(Protocol):
    """O que a sonda precisa oferecer. Nos testes é um dublê."""

    def janelas(self) -> list[dict[str, Any]]: ...

    def janela_em_foco(self) -> dict[str, Any] | None: ...

    def ler_janela(self, handle: int, profundidade: int, limite: int) -> dict[str, Any]: ...


# ---------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------

def _id_do_snapshot(semente: str) -> str:
    """Id curto e determinístico para o conjunto de uma leitura.

    Determinístico de propósito: dois testes com a mesma árvore dão o mesmo id,
    e um `ref` antigo nunca vira válido por acaso (a cada leitura nova muda).
    """
    return hashlib.sha1(semente.encode("utf-8", errors="replace")).hexdigest()[:8]


def papel(numero: Any) -> str:
    """Papel legível. Número desconhecido não ganha nome inventado."""
    try:
        codigo = int(numero)
    except (TypeError, ValueError):
        return str(numero or "elemento")
    return PAPEIS.get(codigo, f"elemento {codigo}")


def _acionavel(bruto: dict[str, Any]) -> bool:
    if bruto.get("desativado"):
        return False
    try:
        return bool(bruto.get("acao")) or int(bruto.get("papel") or 0) in ACIONAVEIS
    except (TypeError, ValueError):
        return False


def _normalizar(
    bruto: dict[str, Any],
    *,
    prefixo: str,
    profundidade: int,
    maxima: int,
    contador: list[int],
    limite: int,
    ancestrais: tuple[Ancestral, ...] = (),
) -> dict[str, Any] | None:
    """Transforma o nó cru da sonda no nó público, cortando com honestidade."""
    if profundidade and e_duplicado(bruto, ancestrais):
        return None
    if contador[0] >= limite:
        return None
    contador[0] += 1
    numero = contador[0]
    acionavel = _acionavel(bruto)
    no: dict[str, Any] = {
        "ref": f"{prefixo}:e{numero}" if acionavel else "",
        "papel": papel(bruto.get("papel")),
        "nome": " ".join(str(bruto.get("nome") or "").split())[:200],
        "profundidade": profundidade,
        "acionavel": acionavel,
    }
    # A UIAutomation já manda o nome do papel traduzido pelo Windows (“editar”,
    # “botão”). Ele é melhor do que a nossa tabela quando existe — usamos ele.
    localizado = " ".join(str(bruto.get("papel_nome") or "").split())[:40]
    if localizado:
        no["papel"] = localizado
    if bruto.get("acao"):
        no["acao"] = str(bruto["acao"])[:60]
    caixa = bruto.get("caixa")
    if isinstance(caixa, (list, tuple)) and len(caixa) == 4:
        try:
            no["caixa"] = [int(valor) for valor in caixa]
        except (TypeError, ValueError):
            pass

    filhos: list[dict[str, Any]] = []
    # A mesma guarda da leitura, aplicada de novo na montagem: mesmo que a
    # sonda devolva árvore repetida (versão antiga, programa estranho), o que
    # chega ao chat já vem cortado. O nó aparece; só a descida para.
    pode, caminho = pode_descer(bruto, ancestrais)
    if profundidade < maxima and pode:
        for filho in bruto.get("filhos") or []:
            if not isinstance(filho, dict):
                continue
            normalizado = _normalizar(
                filho,
                prefixo=prefixo,
                profundidade=profundidade + 1,
                maxima=maxima,
                contador=contador,
                limite=limite,
                ancestrais=caminho,
            )
            if normalizado is None:
                # `None` aqui é duplicado (pula) ou limite atingido (para).
                if contador[0] >= limite:
                    break
                continue
            filhos.append(normalizado)
    if filhos:
        no["filhos"] = filhos
    return no


def _contar(no: dict[str, Any]) -> tuple[int, int]:
    total, acionaveis = 1, 1 if no.get("acionavel") else 0
    for filho in no.get("filhos") or []:
        t, a = _contar(filho)
        total += t
        acionaveis += a
    return total, acionaveis


# ---------------------------------------------------------------------------
# Guardas contra árvore que se repete
# ---------------------------------------------------------------------------
# Medição no PC do usuário (Chrome, Windows 10 14393), antes da guarda:
#
#     chrome.exe — Arena | Benchmark...: 600 elemento(s), 596 acionável(is)
#     botão “IME” → botão “IME” → botão “IME” → ...
#     botão “Minimizar” → botão “Minimizar” → ...
#
# O Chrome expõe a moldura da janela **dentro de si mesma**: cada botão de
# moldura devolve os cinco botões de novo. Sem guarda, o limite de 600 acaba
# antes de chegar ao conteúdo da página — e o JARVIS “vê” 596 botões que não
# existem. As guardas abaixo são política, não sistema: valem para MSAA e UIA.

NOMES_DE_MOLDURA = {
    "ime",
    "minimizar",
    "maximizar",
    "restaurar",
    "restaurar para baixo",
    "fechar",
    "fechar janela",
    "ajuda de contexto",
    "sistema",
}

# (papel, nome, posição) — a identidade de um nó numa linhagem.
Ancestral = tuple[int, str, tuple[Any, ...]]


def limpo(nome: Any) -> str:
    return " ".join(str(nome or "").split())


def de_moldura(no: dict[str, Any]) -> bool:
    """Botão de moldura nunca tem conteúdo dentro — descer nele é laço."""
    return limpo(no.get("nome")).lower() in NOMES_DE_MOLDURA


def chave(no: dict[str, Any]) -> Ancestral:
    """Identidade do nó: papel, nome e — quando existe — a posição na tela."""
    caixa = no.get("caixa")
    posicao: tuple[Any, ...] = tuple(caixa) if isinstance(caixa, (list, tuple)) and len(caixa) == 4 else ()
    try:
        papel_numero = int(no.get("papel") or 0)
    except (TypeError, ValueError):
        papel_numero = 0
    return (papel_numero, limpo(no.get("nome")), posicao)


def repete_ancestral(no: dict[str, Any], ancestrais: tuple[Ancestral, ...]) -> bool:
    """O nó é ele mesmo, umas camadas acima? Então é ciclo, não conteúdo."""
    propria = chave(no)
    for antigo in ancestrais:
        if propria == antigo:
            return True
        # Nome próprio repetido na mesma linhagem é ciclo, mesmo que a posição
        # mude um pixel (o Chrome muda).
        if propria[1] and antigo[1] == propria[1] and antigo[0] == propria[0]:
            return True
    return False


def pode_descer(no: dict[str, Any], ancestrais: tuple[Ancestral, ...]) -> tuple[bool, tuple[Ancestral, ...]]:
    """Descer nesse nó é seguro, ou ele é moldura/ciclo?

    Devolve `(pode, caminho)`. Distinção que importa:

    - **moldura** (Minimizar, Fechar, IME): o nó é real, só não tem nada dentro.
      Ele **entra** na árvore e para ali;
    - **repetição** (o mesmo nó dentro de si mesmo): não é um nó novo, é o
      mesmo lido de novo. Ele **não entra** — entregar o mesmo botão duas vezes
      seria mentir sobre a tela.
    """
    if repete_ancestral(no, ancestrais):
        return False, ancestrais
    if de_moldura(no):
        return False, ancestrais
    return True, ancestrais + (chave(no),)


def e_duplicado(no: dict[str, Any], ancestrais: tuple[Ancestral, ...]) -> bool:
    """Este nó já apareceu acima dele na mesma linhagem?"""
    return repete_ancestral(no, ancestrais)


# ---------------------------------------------------------------------------
# Janelas que são do Windows, não do usuário
# ---------------------------------------------------------------------------
# Sem este filtro, a sonda escolheu o menu **Iniciar** como “a janela de trás”
# no PC do usuário e leu “Iniciar” em vez do Chrome que estava aberto.

CLASSES_DE_CASCA = {
    "shell_traywnd",
    "shell_secondarytraywnd",
    "progman",
    "workerw",
    "windows.ui.core.corewindow",  # menu Iniciar, Central de Ações, pesquisa
    "taskswitcherwnd",
    "multitaskingviewframe",
    "foregroundstaging",
    "dv2controlhost",
    "toplevelwindowforoverflowxamlisland",
    "xamlexplorerhostislandwindow",
    "windows.internal.shell.tabproxywindow",
}

TITULOS_DE_CASCA = {
    "iniciar",
    "program manager",
    "cortana",
    "pesquisar",
    "central de ações",
    "visualização de tarefas",
    "área de trabalho",
    "area de trabalho",
}


def de_casca(janela: dict[str, Any] | None) -> bool:
    """A janela é do próprio Windows (menu Iniciar, barra, área de trabalho)?"""
    if not janela:
        return True
    if str(janela.get("classe") or "").strip().lower() in CLASSES_DE_CASCA:
        return True
    return limpo(janela.get("titulo")).lower() in TITULOS_DE_CASCA


# ---------------------------------------------------------------------------
# Duas fontes: MSAA e UIAutomation
# ---------------------------------------------------------------------------
# A MSAA é de 1996. No seu PC ela devolveu, para um `cmd.exe`:
#
#     cmd.exe — ...: 1 elemento(s), 0 acionável(is) — fonte: msaa
#     área do cliente “C:\Windows\system32\cmd.exe - ...”
#
# Ou seja: a janela publicou só a moldura. O console — e boa parte dos
# programas atuais — publica a árvore **pela UIAutomation**. Por isso existem
# duas leituras, e quem decide é a que mostrou mais elementos.

SEGUNDA_FONTE_ABAIXO_DE = 9

# Programas em que a MSAA comprovadamente entrega moldura e nada mais.
# O Chrome no Windows 10 do usuário devolveu, pela MSAA, a barra de rolagem e
# a barra de título — e nenhum elemento da página. A árvore de verdade dele
# está na UIAutomation. Para estes, a segunda leitura é sempre tentada.
PROCESSOS_SEM_MSAA = {
    "chrome.exe",
    "msedge.exe",
    "brave.exe",
    "opera.exe",
    "vivaldi.exe",
    "firefox.exe",
    "code.exe",
    "cursor.exe",
    "slack.exe",
    "discord.exe",
    "spotify.exe",
    "whatsapp.exe",
    "notion.exe",
    "figma.exe",
}


def _total_bruto(bruto: dict[str, Any] | None) -> int:
    """Quantos nós a leitura crua trouxe — sem montar nada."""
    if not bruto or not isinstance(bruto.get("raiz"), dict):
        return 0
    pilha = [bruto["raiz"]]
    total = 0
    while pilha:
        no = pilha.pop()
        total += 1
        for filho in no.get("filhos") or []:
            if isinstance(filho, dict):
                pilha.append(filho)
    return total


def total_bruto(bruto: dict[str, Any] | None) -> int:
    """Quantos nós uma leitura crua trouxe. Público: a sonda usa para comparar."""
    return _total_bruto(bruto)


def precisa_segunda_fonte(bruto: dict[str, Any] | None) -> bool:
    """A leitura veio pobre? Então vale tentar a outra fonte.

    Pobre = menos de 9 elementos. Janela rica não paga a segunda leitura: numa
    janela grande, cada caminhada extra é tempo que o usuário espera.
    """
    return _total_bruto(bruto) < SEGUNDA_FONTE_ABAIXO_DE


# Papéis que só existem quando o programa publica **conteúdo**: texto de
# página, link, item de lista, célula de tabela. Moldura de janela não tem
# nenhum destes.
PAPEIS_DE_CONTEUDO = {15, 24, 29, 30, 32, 34, 36, 41, 42}

# Papéis que são **superfície de texto**: documento e área de edição. Estes
# contam mesmo sem nome — o campo do Bloco de Notas não tem nome nenhum, e
# exigir nome recusaria justamente o programa mais simples que existe. Moldura
# de janela nunca tem estes papéis, então a regra “conteúdo vence moldura”
# continua valendo.
PAPEIS_DE_TEXTO = {15, 42}


def tem_conteudo(bruto: dict[str, Any] | None) -> bool:
    """A árvore tem pelo menos um elemento de conteúdo (não só moldura)?"""
    if not bruto or not isinstance(bruto.get("raiz"), dict):
        return False
    pilha = [bruto["raiz"]]
    while pilha:
        no = pilha.pop()
        try:
            codigo = int(no.get("papel") or 0)
            if codigo in PAPEIS_DE_CONTEUDO and (limpo(no.get("nome")) or codigo in PAPEIS_DE_TEXTO):
                return True
        except (TypeError, ValueError):
            pass
        for filho in no.get("filhos") or []:
            if isinstance(filho, dict):
                pilha.append(filho)
    return False


def e_navegador(bruto: dict[str, Any] | None) -> bool:
    """O alvo é um programa que só fala pela UIAutomation?"""
    if not bruto:
        return False
    janela = bruto.get("janela") or {}
    return limpo(janela.get("processo")).lower() in PROCESSOS_SEM_MSAA


def quer_segunda_fonte(bruto: dict[str, Any] | None) -> bool:
    """Tentar a UIAutomation: árvore pobre **ou** programa que só fala por ela."""
    return precisa_segunda_fonte(bruto) or e_navegador(bruto)


def escolher_fonte(msaa: dict[str, Any] | None, uia: dict[str, Any] | None) -> dict[str, Any]:
    """Devolve a leitura mais útil, dizendo qual foi e por quê.

    A regra **não** é “quem tem mais elementos”. No Chrome do usuário a MSAA
    deu 47 e a UIA 4 — e os 47 eram todos moldura:

        47 elemento(s), 26 acionável(is) — fonte: msaa
        botão “Uma linha acima”, botão “Uma página abaixo”, alça...

    Medir “quem tem mais” premiava justamente a leitura que não tem conteúdo.
    A ordem passou a ser:

    1. **conteúdo vence moldura**: se uma das duas trouxe elementos de
       conteúdo (link, texto, item de lista) e a outra só moldura, ganha a de
       conteúdo — mesmo com menos elementos;
    2. **navegador vai de UIA**: Chrome/Edge/Firefox publicam a página pela
       UIAutomation;
    3. empate técnico: quem mostrou mais.
    """
    msaa = msaa or {}
    uia = uia or {}
    total_msaa, total_uia = _total_bruto(msaa), _total_bruto(uia)

    if total_uia and tem_conteudo(uia) and not tem_conteudo(msaa):
        escolhida = dict(uia)
        escolhida["nota"] = (
            f"a MSAA trouxe {total_msaa} elemento(s), todos de moldura; "
            f"a UIAutomation trouxe conteúdo ({total_uia} elemento(s))."
        )
        return escolhida
    if total_msaa and e_navegador(msaa) and total_uia:
        escolhida = dict(uia)
        escolhida["nota"] = f"navegador: a página fala pela UIAutomation ({total_uia} elemento(s))."
        return escolhida

    if total_uia and (not total_msaa or total_uia >= total_msaa):
        escolhida = dict(uia)
        if total_msaa:
            escolhida["nota"] = (
                f"a MSAA mostrou só {total_msaa} elemento(s); a UIAutomation mostrou {total_uia}."
            )
        return escolhida
    if total_msaa:
        escolhida = dict(msaa)
        if total_uia:
            escolhida["nota"] = f"a UIAutomation mostrou {total_uia}; a MSAA mostrou mais ({total_msaa})."
        return escolhida
    # Nenhuma das duas trouxe árvore: devolve a da UIA, com o motivo honesto.
    vazio = dict(uia or msaa)
    vazio["raiz"] = None
    vazio["aviso"] = (
        "esta janela não publicou árvore em nenhuma das duas fontes (MSAA e UIAutomation). "
        "Costuma acontecer com jogo em tela cheia, instalador antigo e janela elevada "
        "aberta por um programa que roda como administrador."
    )
    return vazio


def repeticao(resultado: dict[str, Any]) -> int:
    """Quantas vezes o botão mais repetido aparece entre os acionáveis.

    Serve de alarme: na primeira medição no PC do usuário o Chrome devolveu
    596 acionáveis que eram **o mesmo** punhado de botões de moldura, repetidos
    dentro de si mesmos. Se isso voltar a acontecer, é melhor avisar do que
    entregar 596 “botões” que não existem.
    """
    contagem: dict[tuple[str, str], int] = {}
    for no in achatar(resultado.get("arvore")):
        if not no.get("acionavel"):
            continue
        chave = (str(no.get("papel")), str(no.get("nome")))
        contagem[chave] = contagem.get(chave, 0) + 1
    return max(contagem.values(), default=0)


def dica(resultado: dict[str, Any]) -> str:
    """O que fazer quando a leitura veio quase vazia — em vez de silêncio.

    Foi o que faltou na primeira medição: “1 elemento, 0 acionável” sem dizer
    que o JARVIS tinha lido **o próprio terminal**.
    """
    total = int(resultado.get("total") or 0)
    if not total:
        return ""
    acionaveis_total = int(resultado.get("acionaveis") or 0)
    if acionaveis_total >= 20 and repeticao(resultado) >= 10:
        return (
            "esta janela repetiu os mesmos botões dentro deles mesmos (moldura em vez de conteúdo). "
            "Tente `--fonte uia`, ou clique dentro da área do programa antes de ler."
        )
    alvo = str(resultado.get("alvo") or "")
    proprio = any(nome in alvo.lower() for nome in ("cmd.exe", "powershell.exe", "python.exe", "conhost.exe"))
    if proprio and int(resultado.get("acionaveis") or 0) == 0:
        return (
            "o JARVIS leu o próprio terminal — é ele que está em foco. Clique na janela que quer "
            "examinar e rode de novo, ou peça `--alvo` com parte do título (ex.: `--alvo chrome`)."
        )
    if int(resultado.get("acionaveis") or 0) == 0 and total <= 2:
        return (
            "a janela publicou só a moldura: este programa pode não expor seus controles. "
            "Vale repetir com `--alvo` em outra janela para comparar."
        )
    return ""


# ---------------------------------------------------------------------------
# Leitura
# ---------------------------------------------------------------------------

def _limites(profundidade: int | None, limite: int | None) -> tuple[int, int]:
    prof = PROFUNDIDADE_PADRAO if profundidade is None else int(profundidade)
    lim = LIMITE_PADRAO if limite is None else int(limite)
    return max(1, min(prof, PROFUNDIDADE_MAX)), max(1, min(lim, LIMITE_MAX))


def montar(bruto: dict[str, Any], profundidade: int = PROFUNDIDADE_PADRAO, limite: int = LIMITE_PADRAO) -> dict[str, Any]:
    """Monta o resultado público a partir do que a sonda devolveu.

    Separado da leitura para poder ser testado sem Windows, sem COM e sem tela.
    """
    prof, lim = _limites(profundidade, limite)
    janela = bruto.get("janela") or {}
    titulo = " ".join(str(janela.get("titulo") or "").split())[:120]
    processo = str(janela.get("processo") or "").strip()
    semente = f"{janela.get('handle')}|{titulo}|{processo}|{bruto.get('fonte')}|{json.dumps(bruto.get('raiz') or {}, sort_keys=True, ensure_ascii=False)[:4000]}"
    prefixo = "@" + _id_do_snapshot(semente)

    contador = [0]
    raiz_bruta = bruto.get("raiz")
    if not isinstance(raiz_bruta, dict):
        return {
            "id": prefixo[1:],
            "alvo": f"{processo} — {titulo}".strip(" —"),
            "fonte": bruto.get("fonte") or "",
            "completo": True,
            "total": 0,
            "acionaveis": 0,
            "arvore": None,
            "aviso": bruto.get("aviso") or "Esta janela não publicou árvore de acessibilidade.",
        }

    arvore = _normalizar(raiz_bruta, prefixo=prefixo, profundidade=0, maxima=prof, contador=contador, limite=lim)
    total, acionaveis = _contar(arvore) if arvore else (0, 0)
    truncada = contador[0] >= lim
    resultado = {
        "id": prefixo[1:],
        "alvo": f"{processo} — {titulo}".strip(" —"),
        "fonte": bruto.get("fonte") or "",
        "completo": not truncada,
        "total": total,
        "acionaveis": acionaveis,
        "profundidade": prof,
        "limite": lim,
        "arvore": arvore,
    }
    if truncada:
        resultado["aviso"] = (
            f"parei em {lim} elementos; a janela tem mais. Aumente o limite ou leia a partir de um nó."
        )
    elif bruto.get("aviso"):
        resultado["aviso"] = bruto["aviso"]
    # A árvore pode ter vindo de uma janela filha (a página do navegador mora
    # lá). O alvo continua sendo a janela que o usuário pediu, mas vale dizer.
    if janela.get("de_filha"):
        resultado["de_filha"] = str(janela["de_filha"])[:60]
    notas = [str(item) for item in (bruto.get("nota"), bruto.get("nota_escolha"), bruto.get("acordou")) if item]
    if notas:
        resultado["nota"] = " ".join(notas)
    # Medido na árvore crua, onde o número do papel ainda existe: link, texto,
    # item de lista, documento. Moldura sozinha não é conteúdo.
    resultado["conteudo"] = tem_conteudo(bruto)
    sugestao = dica(resultado)
    if sugestao:
        resultado["dica"] = sugestao
    return resultado


def ler(
    alvo: str = "foco",
    *,
    profundidade: int = PROFUNDIDADE_PADRAO,
    limite: int = LIMITE_PADRAO,
    leitor: Leitor | None = None,
    tempo: float = 25.0,
    fonte: str = "auto",
) -> dict[str, Any]:
    """Lê a árvore da janela em foco (ou de um título) — sem colocar a API em risco.

    Com `leitor` injetado (testes) roda no próprio processo. Sem ele, no Windows,
    chama a sonda em **outro processo**: se o COM da janela derrubar a leitura,
    cai ali e não aqui.
    """
    prof, lim = _limites(profundidade, limite)
    if leitor is not None:
        return _ler_com_leitor(leitor, alvo, prof, lim)
    if sys.platform != "win32":
        raise ArvoreError(
            "a leitura da árvore só existe no Windows hoje — no seu sistema o JARVIS continua "
            "com `mesa.status` (títulos de janela)."
        )
    escolhida = (fonte or "auto").strip().lower()
    if escolhida not in {"auto", "msaa", "uia"}:
        escolhida = "auto"
    return _ler_com_sonda(alvo, prof, lim, tempo, escolhida)


def _ler_com_leitor(leitor: Leitor, alvo: str, profundidade: int, limite: int) -> dict[str, Any]:
    janela = _escolher_janela(leitor, alvo)
    bruto = leitor.ler_janela(janela["handle"], profundidade, limite)
    bruto.setdefault("janela", janela)
    return montar(bruto, profundidade, limite)


# ---------------------------------------------------------------------------
# Escolher a janela certa
# ---------------------------------------------------------------------------
# Medição no PC do usuário, 0.82.2:
#
#     D:\JARVIS>.venv\Scripts\python arvore_sonda.py --alvo chrome
#     cmd.exe — C:\Windows\system32\cmd.exe - ... --alvo chrome: 12 elemento(s)...
#
# O Chrome nunca foi lido. A busca procurava primeiro no **título**, e o título
# do terminal é a própria linha de comando — que contém a palavra “chrome”.
# A janela que roda a sonda é a única que sempre tem o pedido escrito nela.
#
# Ordem nova, e a razão de cada passo:
#
# 1. janela que roda a sonda **nunca** é candidata (é a que tem o pedido no título);
# 2. processo manda mais que título: `chrome` casa com `chrome.exe`, não com um
#    terminal que por acaso mostra a palavra;
# 3. título só vale quando é janela de programa de verdade.

PROCESSOS_DE_TERMINAL = {
    "cmd.exe",
    "powershell.exe",
    "pwsh.exe",
    "python.exe",
    "pythonw.exe",
    "conhost.exe",
    "openconsole.exe",
    "windowsterminal.exe",
}


def e_terminal(janela: dict[str, Any] | None) -> bool:
    """A janela é um terminal — onde o comando do JARVIS fica escrito?"""
    return limpo((janela or {}).get("processo")).lower() in PROCESSOS_DE_TERMINAL


def da_sonda(janela: dict[str, Any] | None) -> bool:
    """Esta é a janela que está rodando a leitura agora?

    Reconhecida por dois sinais: título com o nome do arquivo da sonda, ou ser
    terminal (todos são candidatos a estar executando o comando).
    """
    if not janela:
        return False
    if "arvore_sonda" in limpo(janela.get("titulo")).lower():
        return True
    return False


def peso_da_janela(janela: dict[str, Any], pedido: str) -> int | None:
    """Nota de 0 (melhor) a 3. `None` significa “não é esta”.

    O número é a distância do que o usuário quis: processo igual vence título
    parecido — sempre.
    """
    procurado = limpo(pedido).lower()
    if not procurado:
        return None
    processo = limpo(janela.get("processo")).lower()
    sem_exe = processo[:-4] if processo.endswith(".exe") else processo
    titulo = limpo(janela.get("titulo")).lower()

    if sem_exe == procurado or processo == procurado:
        return 0
    if procurado in sem_exe:
        return 1
    if titulo.startswith(procurado):
        return 2
    if procurado in titulo:
        return 3
    return None


def escolher_janela(
    alvo: str,
    *,
    janelas: list[dict[str, Any]],
    foco: dict[str, Any] | None,
) -> dict[str, Any]:
    """A janela que o pedido designa — com a razão da escolha quando importa."""
    pedido = limpo(alvo)
    if not pedido or pedido.lower() in {"foco", "focused"}:
        if not foco:
            raise ArvoreError("não achei a janela em foco — clique na janela que quer examinar e tente de novo.")
        return foco

    if not janelas:
        raise ArvoreError("não achei nenhuma janela aberta.")

    # A janela da sonda é a que carrega o pedido escrito no título: fora.
    candidatas = [item for item in janelas if not da_sonda(item)]
    pontuadas = [(peso_da_janela(item, pedido), item) for item in candidatas]
    achadas = sorted(
        ((peso, item) for peso, item in pontuadas if peso is not None),
        key=lambda par: par[0],
    )
    if not achadas:
        abertas = "; ".join(limpo(item.get("titulo"))[:40] for item in candidatas if item.get("titulo"))[:400]
        raise ArvoreError(
            f"nenhuma janela com “{pedido}”. Abertas agora: {abertas or '(nenhuma)'}."
        )
    return achadas[0][1]


def _escolher_janela(leitor: Leitor, alvo: str) -> dict[str, Any]:
    pedido = limpo(alvo)
    foco = None
    if not pedido or pedido.lower() in {"foco", "focused"}:
        foco = leitor.janela_em_foco()
    return escolher_janela(alvo, janelas=leitor.janelas(), foco=foco)


def _ler_com_sonda(
    alvo: str,
    profundidade: int,
    limite: int,
    tempo: float,
    fonte: str = "auto",
) -> dict[str, Any]:
    if not SONDA.is_file():
        raise ArvoreError("a sonda de leitura (arvore_sonda.py) não está nesta pasta.")
    comando = [
        sys.executable,
        str(SONDA),
        "--json",
        "--alvo",
        alvo,
        "--profundidade",
        str(profundidade),
        "--limite",
        str(limite),
        "--fonte",
        fonte,
    ]
    try:
        saida = subprocess.run(  # noqa: S603 - caminho fixo, sem shell
            comando,
            capture_output=True,
            text=True,
            timeout=tempo,
            cwd=str(RAIZ),
        )
    except subprocess.TimeoutExpired as exc:
        raise ArvoreError(
            f"a leitura passou de {int(tempo)}s e foi interrompida — a janela pode estar ocupada."
        ) from exc
    except OSError as exc:
        raise ArvoreError(f"não consegui iniciar a sonda de leitura ({type(exc).__name__}).") from exc

    if saida.returncode != 0:
        # A sonda devolve o motivo em JSON no stdout quando sabe explicar.
        try:
            erro = json.loads(saida.stdout or "{}")
        except ValueError:
            erro = {}
        motivo = erro.get("erro") or (saida.stderr or "").strip().splitlines()[-1:] or ""
        if isinstance(motivo, list):
            motivo = motivo[0] if motivo else ""
        raise ArvoreError(
            f"a sonda de leitura parou (código {saida.returncode})"
            + (f": {motivo}" if motivo else " — provavelmente a janela não publica árvore.")
        )
    try:
        bruto = json.loads(saida.stdout)
    except ValueError as exc:
        raise ArvoreError("a sonda respondeu algo que não é JSON.") from exc
    return montar(bruto, profundidade, limite)


# ---------------------------------------------------------------------------
# Consultas sobre o resultado (para o chat)
# ---------------------------------------------------------------------------

def achatar(no: dict[str, Any] | None, profundidade: int = -1) -> list[dict[str, Any]]:
    """Lista os nós em ordem de leitura, respeitando a profundidade máxima."""
    if not no:
        return []
    itens = [no]
    if profundidade == 0:
        return itens
    for filho in no.get("filhos") or []:
        itens.extend(achatar(filho, profundidade - 1))
    return itens


def acionaveis(resultado: dict[str, Any], limite: int = 40) -> list[dict[str, Any]]:
    """Só o que dá para clicar, com nome — o que interessa para uma ação."""
    itens = [no for no in achatar(resultado.get("arvore")) if no.get("acionavel")]
    return itens[: max(1, limite)]


def procurar(resultado: dict[str, Any], texto: str) -> list[dict[str, Any]]:
    """Busca por nome (sem diferenciar maiúsculas/acentos de propósito: é literal)."""
    procurado = (texto or "").strip().lower()
    if not procurado:
        return []
    return [no for no in achatar(resultado.get("arvore")) if procurado in str(no.get("nome", "")).lower()]


def desenhar(no: dict[str, Any] | None, profundidade: int = 0, linhas: list[str] | None = None) -> str:
    """Árvore em texto, para o chat — indentada, com o `ref` e **onde fica**.

    A posição sempre esteve na leitura (`caixa`: x, y, largura, altura) e nunca
    apareceu aqui. O efeito foi o usuário perguntar, com razão, “mas ele não
    está reconhecendo onde fica cada coisa?” — e não havia na tela uma linha
    sequer mostrando que sim, que isto é medido.
    """
    if linhas is None:
        linhas = []
    if not no:
        return "\n".join(linhas) or "(vazio)"
    prefixo = "  " * profundidade
    nome = f" “{no['nome']}”" if no.get("nome") else ""
    ref = f"  {no['ref']}" if no.get("ref") else ""
    caixa = no.get("caixa")
    onde = ""
    if isinstance(caixa, (list, tuple)) and len(caixa) == 4:
        onde = f"  em {caixa[0]},{caixa[1]} ({caixa[2]}x{caixa[3]})"
    linhas.append(f"{prefixo}{no.get('papel')}{nome}{ref}{onde}")
    for filho in no.get("filhos") or []:
        desenhar(filho, profundidade + 1, linhas)
    return "\n".join(linhas)


ACAO_DE_TEXTO = {"escrever", "digitar"}


def prontidao(resultado: dict[str, Any]) -> dict[str, Any]:
    """Esta janela serve para o JARVIS agir? Mede, não opina.

    O critério da etapa 2 sempre foi “uma leitura em que os elementos façam
    sentido”. Isso, escrito como conta, é:

    - a árvore tem **conteúdo** (não só barra de título e botão de janela); e
    - existe pelo menos um elemento acionável **com nome** — ou um campo onde
      dá para escrever, que é o caso do Bloco de Notas, cujo campo não tem nome.

    Moldura nunca serve: 600 botões “Minimizar” não valem um link.
    """
    raiz = resultado.get("arvore")
    total = acionaveis = nomeados = uteis = editaveis = com_posicao = 0
    pilha = [raiz] if isinstance(raiz, dict) else []
    while pilha:
        no = pilha.pop()
        total += 1
        caixa = no.get("caixa")
        if isinstance(caixa, (list, tuple)) and len(caixa) == 4 and int(caixa[2]) > 0:
            com_posicao += 1
        nome = " ".join(str(no.get("nome") or "").split())
        if nome:
            nomeados += 1
        if no.get("acionavel"):
            acionaveis += 1
            if nome:
                uteis += 1
            if str(no.get("acao") or "").strip().lower() in ACAO_DE_TEXTO:
                editaveis += 1
        pilha.extend(no.get("filhos") or [])

    conteudo = bool(resultado.get("conteudo"))
    pronto = bool(total and conteudo and (uteis or editaveis))
    if pronto:
        motivo = (
            f"{resultado.get('total', total)} elemento(s) de árvore, {acionaveis} acionável(is) "
            f"e {uteis + editaveis} com nome ou escrita — dá para agir por `ref`."
        )
    elif not total:
        motivo = resultado.get("aviso") or "a janela não publicou árvore."
    elif not conteudo:
        motivo = (
            "a janela publicou só moldura (barra de título, rolagem, botões de janela). "
            "Esta é a mesma parede que o Chrome deu neste PC."
        )
        if com_posicao:
            # A distinção que evita a confusão: posição medida ≠ conteúdo lido.
            motivo += (
                f" A posição dela eu sei — {com_posicao} de {total} elemento(s) vieram "
                "com coordenada; o que não existe é o que está dentro da página."
            )
    else:
        motivo = "tem conteúdo, mas nenhum elemento acionável com nome ainda."
    return {
        "pronto": pronto,
        "conteudo": conteudo,
        "total": total,
        "acionaveis": acionaveis,
        "nomeados": nomeados,
        "com_nome_acionavel": uteis,
        "editaveis": editaveis,
        "com_posicao": com_posicao,
        "motivo": motivo,
    }


def resumo(resultado: dict[str, Any]) -> str:
    """Uma frase honesta sobre o que a leitura encontrou."""
    total = int(resultado.get("total") or 0)
    if not total:
        return resultado.get("aviso") or "A janela não publicou árvore de acessibilidade."
    acionaveis_total = int(resultado.get("acionaveis") or 0)
    cabeca = (
        f"{resultado.get('alvo') or 'janela'}: {total} elemento(s), "
        f"{acionaveis_total} acionável(is) — fonte: {resultado.get('fonte') or '?'}."
    )
    if resultado.get("de_filha"):
        cabeca += f" (lido de dentro: {resultado['de_filha']})"
    if not resultado.get("completo", True):
        cabeca += " " + str(resultado.get("aviso") or "Leitura parcial.")
    if resultado.get("nota"):
        cabeca += " " + str(resultado["nota"])
    if resultado.get("dica"):
        cabeca += " " + str(resultado["dica"])
    return cabeca
