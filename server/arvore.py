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
) -> dict[str, Any] | None:
    """Transforma o nó cru da sonda no nó público, cortando com honestidade."""
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
    if bruto.get("acao"):
        no["acao"] = str(bruto["acao"])[:60]
    caixa = bruto.get("caixa")
    if isinstance(caixa, (list, tuple)) and len(caixa) == 4:
        try:
            no["caixa"] = [int(valor) for valor in caixa]
        except (TypeError, ValueError):
            pass

    filhos: list[dict[str, Any]] = []
    if profundidade < maxima:
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
            )
            if normalizado is None:
                break
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
    return resultado


def ler(
    alvo: str = "foco",
    *,
    profundidade: int = PROFUNDIDADE_PADRAO,
    limite: int = LIMITE_PADRAO,
    leitor: Leitor | None = None,
    tempo: float = 25.0,
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
    return _ler_com_sonda(alvo, prof, lim, tempo)


def _ler_com_leitor(leitor: Leitor, alvo: str, profundidade: int, limite: int) -> dict[str, Any]:
    janela = _escolher_janela(leitor, alvo)
    bruto = leitor.ler_janela(janela["handle"], profundidade, limite)
    bruto.setdefault("janela", janela)
    return montar(bruto, profundidade, limite)


def _escolher_janela(leitor: Leitor, alvo: str) -> dict[str, Any]:
    pedido = (alvo or "foco").strip()
    if pedido.lower() in {"foco", "focused", ""}:
        janela = leitor.janela_em_foco()
        if not janela:
            raise ArvoreError("não achei a janela em foco — clique na janela que quer examinar e tente de novo.")
        return janela
    janelas = leitor.janelas()
    if not janelas:
        raise ArvoreError("não achei nenhuma janela aberta.")
    procurado = pedido.lower()
    achadas = [item for item in janelas if procurado in str(item.get("titulo", "")).lower()]
    if not achadas:
        achadas = [item for item in janelas if procurado in str(item.get("processo", "")).lower()]
    if not achadas:
        titulos = "; ".join(str(item.get("titulo"))[:40] for item in janelas[:8])
        raise ArvoreError(f"nenhuma janela com “{pedido}”. Abertas agora: {titulos}.")
    return achadas[0]


def _ler_com_sonda(alvo: str, profundidade: int, limite: int, tempo: float) -> dict[str, Any]:
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
    """Árvore em texto, para o chat — indentada e com o `ref` quando existe."""
    if linhas is None:
        linhas = []
    if not no:
        return "\n".join(linhas) or "(vazio)"
    prefixo = "  " * profundidade
    nome = f" “{no['nome']}”" if no.get("nome") else ""
    ref = f"  {no['ref']}" if no.get("ref") else ""
    linhas.append(f"{prefixo}{no.get('papel')}{nome}{ref}")
    for filho in no.get("filhos") or []:
        desenhar(filho, profundidade + 1, linhas)
    return "\n".join(linhas)


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
    if not resultado.get("completo", True):
        cabeca += " " + str(resultado.get("aviso") or "Leitura parcial.")
    return cabeca
