"""Leitor da árvore de acessibilidade no Windows — `ctypes` puro, sem instalar nada.

Fala com **MSAA** (`oleacc.dll`, a mesma interface que o Narrador e o NVDA usam):
cada janela publica seus elementos com papel, nome, posição e ação padrão. Não
tira foto, não lê pixel, não move o mouse, não clica.

## Por que é conservador

Este arquivo conversa por COM com **código de outra pessoa** (o programa que
você tem aberto). Um aplicativo malcomportado pode travar a chamada ou derrubar
o processo. Por isso:

- todo acesso é embrulhado em `try/except`;
- profundidade, total de nós e tempo são limitados;
- **no JARVIS ele não roda dentro da API**: `arvore.py` chama `arvore_sonda.py`
  num processo separado, com tempo limite. Se a janela derrubar a leitura, cai a
  sonda — que é descartável — e não o JARVIS.

## O que é lido

| campo | de onde vem |
|---|---|
| `papel` | `get_accRole` (ROLE_SYSTEM_* numérico) |
| `nome` | `get_accName` |
| `acao` | `get_accDefaultAction` (“Clicar”, “Abrir”…) |
| `caixa` | `accLocation` (x, y, largura, altura) |
| `filhos` | `AccessibleChildren`, em ordem de leitura |

Nada disso altera a janela. Só `get_*`, `accLocation` e `AccessibleChildren`.
"""
from __future__ import annotations

import ctypes
import sys
import time
from typing import Any

if sys.platform != "win32":  # pragma: no cover - importado só no Windows
    raise ImportError("arvore_windows só existe no Windows")

from ctypes import wintypes  # noqa: E402

from server import arvore  # noqa: E402 - política de leitura, sem dependência circular

# ---------------------------------------------------------------------------
# Bibliotecas
# ---------------------------------------------------------------------------
user32 = ctypes.WinDLL("user32", use_last_error=True)
oleacc = ctypes.WinDLL("oleacc", use_last_error=True)
oleaut32 = ctypes.WinDLL("oleaut32")
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

HRESULT = ctypes.c_long

VT_I4 = 3
VT_DISPATCH = 9
OBJID_CLIENT = 0xFFFFFFFC
CHILDID_SELF = 0
S_OK = 0

# {618736E0-3C3D-11CF-810C-00AA00389B71}
class GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", wintypes.DWORD),
        ("Data2", wintypes.WORD),
        ("Data3", wintypes.WORD),
        ("Data4", ctypes.c_ubyte * 8),
    ]


IID_IAccessible = GUID(
    0x618736E0, 0x3C3D, 0x11CF, (ctypes.c_ubyte * 8)(0x81, 0x0C, 0x00, 0xAA, 0x00, 0x38, 0x9B, 0x71)
)


class VARIANT(ctypes.Structure):
    """VARIANT de 24 bytes (x64). Só os campos que a MSAA usa."""

    _fields_ = [
        ("vt", ctypes.c_ushort),
        ("r1", ctypes.c_ushort),
        ("r2", ctypes.c_ushort),
        ("r3", ctypes.c_ushort),
        ("valor", ctypes.c_ulonglong),
        ("valor2", ctypes.c_ulonglong),
    ]


# Índices da vtable de IAccessible (depois dos 3 de IUnknown e 4 de IDispatch).
GET_ACC_CHILD_COUNT = 8
GET_ACC_NAME = 10
GET_ACC_ROLE = 13
GET_ACC_DEFAULT_ACTION = 20
ACC_LOCATION = 22
GET_ACC_STATE = 14
STATE_SYSTEM_READONLY = 0x40
IUNKNOWN_RELEASE = 2


def _tabela(ponteiro: int) -> Any:
    return ctypes.cast(ponteiro, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p)))[0]


def _metodo(ponteiro: int, indice: int, tipos: list[Any]) -> Any:
    endereco = _tabela(ponteiro)[indice]
    return ctypes.WINFUNCTYPE(HRESULT, ctypes.c_void_p, *tipos)(endereco)


def _var_filho(indice: int = CHILDID_SELF) -> VARIANT:
    valor = VARIANT()
    valor.vt = VT_I4
    valor.valor = indice
    return valor


def _bstr(valor: Any) -> str:
    """BSTR de saída → str, liberando a memória que o provedor alocou."""
    if not valor:
        return ""
    try:
        return ctypes.cast(valor, ctypes.c_wchar_p).value or ""
    finally:
        try:
            oleaut32.SysFreeString(ctypes.c_void_p(valor))
        except Exception:  # noqa: BLE001 - liberar nunca pode derrubar a leitura
            pass


def _inteiro(ponteiro: int, indice: int, tipo_saida: Any = VARIANT) -> Any:
    """Chama um método que devolve VARIANT por referência (role, state)."""
    saida = tipo_saida()
    try:
        funcao = _metodo(ponteiro, indice, [ctypes.POINTER(tipo_saida)])
        if funcao(ponteiro, ctypes.byref(saida)) != S_OK:
            return None
        return saida
    except Exception:  # noqa: BLE001 - COM de terceiros: nunca propagar
        return None


# ---------------------------------------------------------------------------
# Janelas
# ---------------------------------------------------------------------------

WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000


def _titulo(hwnd: int) -> str:
    tamanho = user32.GetWindowTextLengthW(hwnd)
    if tamanho <= 0:
        return ""
    buffer = ctypes.create_unicode_buffer(tamanho + 1)
    user32.GetWindowTextW(hwnd, buffer, tamanho + 1)
    return buffer.value.strip()


def _classe(hwnd: int) -> str:
    buffer = ctypes.create_unicode_buffer(256)
    try:
        user32.GetClassNameW(hwnd, buffer, 256)
    except Exception:  # noqa: BLE001
        return ""
    return buffer.value


def _processo(hwnd: int) -> str:
    """Nome do executável dono da janela — `notepad.exe`, `chrome.exe`…"""
    pid = wintypes.DWORD(0)
    try:
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    except Exception:  # noqa: BLE001
        return ""
    if not pid.value:
        return ""
    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid.value)
    if not handle:
        return ""
    try:
        buffer = ctypes.create_unicode_buffer(1024)
        tamanho = wintypes.DWORD(1024)
        if not kernel32.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(tamanho)):
            return ""
        return buffer.value.rsplit("\\", 1)[-1]
    except Exception:  # noqa: BLE001
        return ""
    finally:
        kernel32.CloseHandle(handle)


def _caixa(hwnd: int) -> list[int]:
    retangulo = wintypes.RECT()
    try:
        if user32.GetWindowRect(hwnd, ctypes.byref(retangulo)):
            return [
                int(retangulo.left),
                int(retangulo.top),
                int(retangulo.right - retangulo.left),
                int(retangulo.bottom - retangulo.top),
            ]
    except Exception:  # noqa: BLE001
        pass
    return []


def _janela(hwnd: int) -> dict[str, Any]:
    return {
        "handle": int(hwnd),
        "titulo": _titulo(hwnd),
        "classe": _classe(hwnd),
        "processo": _processo(hwnd),
        "caixa": _caixa(hwnd),
    }


def janelas() -> list[dict[str, Any]]:
    """Janelas visíveis de primeiro nível, com título — a lista de “o que está aberto”."""
    achadas: list[dict[str, Any]] = []

    def visitar(hwnd: int, _parametro: int) -> bool:
        try:
            if not user32.IsWindowVisible(hwnd):
                return True
            if not _titulo(hwnd):
                return True
            achadas.append(_janela(hwnd))
        except Exception:  # noqa: BLE001
            pass
        return True

    try:
        user32.EnumWindows(WNDENUMPROC(visitar), 0)
    except Exception:  # noqa: BLE001
        return achadas
    return achadas


def de_casca(janela: dict[str, Any]) -> bool:
    """A janela é do próprio Windows? A lista mora em `arvore.py`."""
    return arvore.de_casca(janela)


def janelas_de_programas() -> list[dict[str, Any]]:
    """Só as janelas de programas de verdade — para escolher “a janela de trás”."""
    return [item for item in janelas() if not arvore.de_casca(item)]


def janela_em_foco() -> dict[str, Any] | None:
    try:
        hwnd = user32.GetForegroundWindow()
    except Exception:  # noqa: BLE001
        return None
    if not hwnd:
        return None
    return _janela(hwnd)


# ---------------------------------------------------------------------------
# IAccessible
# ---------------------------------------------------------------------------

def _abrir(hwnd: int) -> int:
    """Ponteiro de IAccessible para a janela. 0 quando o programa não publica árvore."""
    ponteiro = ctypes.c_void_p(0)
    try:
        resultado = oleacc.AccessibleObjectFromWindow(
            wintypes.HWND(hwnd),
            wintypes.DWORD(OBJID_CLIENT),
            ctypes.byref(IID_IAccessible),
            ctypes.byref(ponteiro),
        )
    except Exception:  # noqa: BLE001
        return 0
    if resultado != S_OK or not ponteiro.value:
        return 0
    return int(ponteiro.value)


def _liberar(ponteiro: int) -> None:
    try:
        funcao = _metodo(ponteiro, IUNKNOWN_RELEASE, [])
        funcao(ponteiro)
    except Exception:  # noqa: BLE001
        pass


def _filhos(ponteiro: int, teto: int) -> list[tuple[int, int]]:
    """Filhos de um nó: `(ponteiro, child_id)` — ponteiro 0 quando é filho simples."""
    total = ctypes.c_long(0)
    try:
        funcao = _metodo(ponteiro, GET_ACC_CHILD_COUNT, [ctypes.POINTER(ctypes.c_long)])
        if funcao(ponteiro, ctypes.byref(total)) != S_OK or total.value <= 0:
            return []
    except Exception:  # noqa: BLE001
        return []

    quantos = min(int(total.value), max(0, teto))
    if quantos <= 0:
        return []
    vetor = (VARIANT * quantos)()
    obtidos = ctypes.c_long(0)
    try:
        funcao = oleacc.AccessibleChildren
        funcao.argtypes = [
            ctypes.c_void_p,
            ctypes.c_long,
            ctypes.c_long,
            ctypes.POINTER(VARIANT),
            ctypes.POINTER(ctypes.c_long),
        ]
        funcao.restype = HRESULT
        if funcao(ponteiro, 0, quantos, vetor, ctypes.byref(obtidos)) != S_OK:
            return []
    except Exception:  # noqa: BLE001
        return []

    achados: list[tuple[int, int]] = []
    for indice in range(int(obtidos.value)):
        item = vetor[indice]
        if item.vt == VT_DISPATCH and item.valor:
            achados.append((int(item.valor), CHILDID_SELF))
        elif item.vt == VT_I4:
            achados.append((0, int(item.valor)))
    return achados


def _nome(ponteiro: int, filho: int) -> str:
    try:
        funcao = _metodo(ponteiro, GET_ACC_NAME, [VARIANT, ctypes.POINTER(ctypes.c_void_p)])
        saida = ctypes.c_void_p(0)
        if funcao(ponteiro, _var_filho(filho), ctypes.byref(saida)) != S_OK:
            return ""
        return _bstr(saida.value)
    except Exception:  # noqa: BLE001
        return ""


def _acao(ponteiro: int, filho: int) -> str:
    try:
        funcao = _metodo(ponteiro, GET_ACC_DEFAULT_ACTION, [VARIANT, ctypes.POINTER(ctypes.c_void_p)])
        saida = ctypes.c_void_p(0)
        if funcao(ponteiro, _var_filho(filho), ctypes.byref(saida)) != S_OK:
            return ""
        return _bstr(saida.value)
    except Exception:  # noqa: BLE001
        return ""


def _papel(ponteiro: int, filho: int) -> int:
    try:
        funcao = _metodo(ponteiro, GET_ACC_ROLE, [VARIANT, ctypes.POINTER(VARIANT)])
        saida = VARIANT()
        if funcao(ponteiro, _var_filho(filho), ctypes.byref(saida)) != S_OK:
            return 0
        return int(saida.valor) if saida.vt == VT_I4 else 0
    except Exception:  # noqa: BLE001
        return 0


def _somente_leitura(ponteiro: int, filho: int) -> bool:
    """O elemento é só de leitura? (STATE_SYSTEM_READONLY)

    Precisa existir porque “texto” não quer dizer “onde se escreve”: um painel
    de log também é papel de texto e recusa a digitação. Prometer escrita ali
    seria mentira na árvore.
    """
    try:
        funcao = _metodo(ponteiro, GET_ACC_STATE, [VARIANT, ctypes.POINTER(VARIANT)])
        saida = VARIANT()
        if funcao(ponteiro, _var_filho(filho), ctypes.byref(saida)) != S_OK:
            return False
        return bool(int(saida.valor) & STATE_SYSTEM_READONLY) if saida.vt == VT_I4 else False
    except Exception:  # noqa: BLE001
        return False


# ROLE_SYSTEM_DOCUMENT e ROLE_SYSTEM_TEXT: onde se escreve, quando a janela
# deixa. Sem isso o Bloco de Notas fica sem `ref` no lugar que importa — os
# únicos acionáveis eram Minimizar, Maximizar e Fechar.
PAPEIS_DE_ESCRITA = {15, 42}


def _acao_de_escrita(ponteiro: int, filho: int, papel: int, caixa: list[int]) -> str:
    if papel not in PAPEIS_DE_ESCRITA or not caixa or caixa[2] <= 0 or caixa[3] <= 0:
        return ""
    if _somente_leitura(ponteiro, filho):
        return ""
    return "digitar"


def _onde(ponteiro: int, filho: int) -> list[int]:
    try:
        funcao = _metodo(
            ponteiro,
            ACC_LOCATION,
            [ctypes.POINTER(ctypes.c_long)] * 4 + [VARIANT],
        )
        esquerda, topo, largura, altura = (ctypes.c_long(0) for _ in range(4))
        if (
            funcao(
                ponteiro,
                ctypes.byref(esquerda),
                ctypes.byref(topo),
                ctypes.byref(largura),
                ctypes.byref(altura),
                _var_filho(filho),
            )
            != S_OK
        ):
            return []
        return [int(esquerda.value), int(topo.value), int(largura.value), int(altura.value)]
    except Exception:  # noqa: BLE001
        return []


class _Orcamento:
    """Teto de nós por leitura: janela enorme não pode virar minuto de espera."""

    def __init__(self, limite: int) -> None:
        self.restante = max(1, int(limite))

    def gastar(self) -> bool:
        if self.restante <= 0:
            return False
        self.restante -= 1
        return True


# As guardas contra árvore que se repete moram em `arvore.py` — são política,
# não sistema, e por isso podem ser testadas fora do Windows. Aqui só se lê.

def _atributos(ponteiro: int, filho: int, papel: int = 0) -> dict[str, Any]:
    """O que se lê de qualquer elemento, simples ou objeto — só consulta."""
    extras: dict[str, Any] = {}
    acao = _acao(ponteiro, filho)
    caixa = _onde(ponteiro, filho)
    if caixa and caixa[2] > 0 and caixa[3] > 0:
        extras["caixa"] = caixa
    # Sem ação padrão, mas é onde se escreve? Então a ação é digitar. Isto é o
    # que dá `ref` ao campo do Bloco de Notas.
    if not acao:
        acao = _acao_de_escrita(ponteiro, filho, papel, caixa)
    if acao:
        extras["acao"] = acao
    return extras


def _no(
    ponteiro: int,
    filho: int,
    profundidade: int,
    maxima: int,
    orcamento: _Orcamento,
    ancestrais: tuple[arvore.Ancestral, ...] = (),
) -> dict[str, Any] | None:
    if not orcamento.gastar():
        return None
    codigo = _papel(ponteiro, filho)
    no: dict[str, Any] = {
        "papel": codigo,
        "nome": _nome(ponteiro, filho),
    }
    acao = _acao(ponteiro, filho)
    caixa = _onde(ponteiro, filho)
    if caixa and caixa[2] > 0 and caixa[3] > 0:
        no["caixa"] = caixa
    if not acao:
        acao = _acao_de_escrita(ponteiro, filho, codigo, caixa)
    if acao:
        no["acao"] = acao

    if profundidade >= maxima:
        return no
    pode, caminho = arvore.pode_descer(no, ancestrais)
    if not pode:
        return no

    for ponteiro_filho, id_filho in _filhos(ponteiro, orcamento.restante):
        # **Só se desce em filho que tem ponteiro próprio.**
        #
        # Isto já esteve errado, e era a causa de TODA a repetição vista no PC
        # do usuário (0.82.3):
        #
        #     botão “Uma linha acima”
        #       botão “Uma linha acima”
        #         botão “Uma página acima”
        #           botão “Uma linha acima” ...
        #
        # A MSAA tem dois tipos de filho: os que são um objeto COM de verdade
        # (VT_DISPATCH, com ponteiro) e os “simples” (VT_I4, só um número). Para
        # os simples, `get_accChildCount` **no pai** devolve os filhos do pai —
        # não do filho. Reusar o ponteiro do pai (o `or ponteiro` que estava aqui)
        # pedia ao pai os próprios filhos, de novo e de novo, até o limite.
        #
        # O certo: elemento simples não tem filhos acessíveis. Ele entra na
        # árvore (o nome e o papel são lidos normalmente — isso funciona), mas
        # a descida para ali.
        if not ponteiro_filho:
            papel_filho = _papel(ponteiro, id_filho)
            no.setdefault("filhos", []).append(
                {
                    "papel": papel_filho,
                    "nome": _nome(ponteiro, id_filho),
                    **_atributos(ponteiro, id_filho, papel_filho),
                }
            )
            continue
        criado = _no(ponteiro_filho, CHILDID_SELF, profundidade + 1, maxima, orcamento, caminho)
        if criado is None:
            _liberar(ponteiro_filho)
            break
        no.setdefault("filhos", []).append(criado)
        _liberar(ponteiro_filho)
    return no


# ---------------------------------------------------------------------------
# UIAutomation — a segunda fonte (0.82.1)
# ---------------------------------------------------------------------------
# Por que existe, com a medição na mão: no seu PC a primeira leitura devolveu
#
#     cmd.exe — ...: 1 elemento(s), 0 acionável(is) — fonte: msaa
#     área do cliente “C:\Windows\system32\cmd.exe - ...”
#
# O console (e boa parte dos programas de hoje: Bloco de Notas do Windows 11,
# apps WinUI, pedaços do Chrome) NÃO publica botões pela MSAA — ela é de 1996.
# Publica pela **UIAutomation**, a árvore nova que o Narrador também usa.
#
# Continua só leitura: `GetFirstChildElement`, `GetNextSiblingElement`, `get_*`
# e `GetCurrentPattern` — este último só para **perguntar** se o elemento aceita
# ação. Nenhum método de agir é chamado.

ole32 = ctypes.WinDLL("ole32", use_last_error=True)

CLSCTX_INPROC_SERVER = 1
COINIT_MULTITHREADED = 0

# {FF48DBA4-60EF-4201-AA87-54103EEF594E} — CLSID_CUIAutomation
CLSID_CUIAutomation = GUID(
    0xFF48DBA4, 0x60EF, 0x4201,
    (ctypes.c_ubyte * 8)(0xAA, 0x87, 0x54, 0x10, 0x3E, 0xEF, 0x59, 0x4E),
)
# {30CBE57D-D9D0-452A-AB13-7AC5AC4825EE} — IID_IUIAutomation
IID_IUIAutomation = GUID(
    0x30CBE57D, 0xD9D0, 0x452A,
    (ctypes.c_ubyte * 8)(0xAB, 0x13, 0x7A, 0xC5, 0xAC, 0x48, 0x25, 0xEE),
)

# Índices de vtable. **Estes números já estiveram errados.**
#
# A primeira versão contava como se a vtable começasse em `CompareElements`,
# esquecendo que QueryInterface, AddRef e Release ocupam 0, 1 e 2. O resultado,
# no PC do usuário, foi:
#
#     .venv\Scripts\python arvore_sonda.py --fonte uia
#     a UIAutomation não devolveu árvore para esta janela.
#
# Ou seja: chamava `GetRootElementBuildCache` no lugar de `ElementFromHandle`.
# O erro era **uniforme** — todos os índices três acima do certo. Conferido
# contra a ordem de `uiautomationclient.h`:
#
#   IUIAutomation:        3 CompareElements, 4 CompareRuntimeIds, 5 GetRootElement,
#                         6 ElementFromHandle, 7 ElementFromPoint, 8 GetFocusedElement,
#                         13 CreateTreeWalker, 14 get_ControlViewWalker
#   IUIAutomationElement: 16 GetCurrentPattern, 21 get_CurrentControlType,
#                         22 get_CurrentLocalizedControlType, 23 get_CurrentName,
#                         28 get_CurrentIsEnabled, 38 get_CurrentIsOffscreen,
#                         43 get_CurrentBoundingRectangle
#   ...TreeWalker:        3 GetParentElement, 4 GetFirstChildElement,
#                         5 GetLastChildElement, 6 GetNextSiblingElement
UIA_ELEMENT_FROM_HANDLE = 6
UIA_CONTROL_VIEW_WALKER = 14
UIA_EL_GET_PATTERN = 16
UIA_EL_GET_CONTROL_TYPE = 21
UIA_EL_GET_LOCALIZED_TYPE = 22
UIA_EL_GET_NAME = 23
UIA_EL_GET_IS_ENABLED = 28
UIA_EL_GET_IS_OFFSCREEN = 38
UIA_EL_GET_RECT = 43
UIA_WALKER_FIRST_CHILD = 4
UIA_WALKER_NEXT_SIBLING = 6

# PATTERNID é inteiro, não GUID.
PADRAO_INVOCAR = 10000
PADRAO_VALOR = 10002
PADRAO_EXPANDIR = 10005
PADRAO_SELECIONAR = 10008
PADRAO_MARCAR = 10013

# CONTROLTYPEID → ROLE_SYSTEM_*, para o resto do JARVIS ver o mesmo vocabulário.
PAPEL_UIA = {
    50001: 16,  # calendário
    50002: 44,  # caixa de seleção
    50003: 46,  # caixa de combinação
    50004: 42,  # campo de edição
    50005: 30,  # link
    50006: 40,  # imagem
    50007: 34,  # item de lista
    50008: 33,  # lista
    50009: 2,   # menu
    50010: 2,   # barra de menu
    50011: 12,  # item de menu
    50012: 48,  # barra de progresso
    50013: 45,  # botão de opção
    50014: 3,   # barra de rolagem
    50015: 51,  # controle deslizante
    50016: 52,  # botão de giro
    50017: 23,  # barra de status
    50018: 60,  # lista de abas
    50019: 37,  # aba
    50020: 41,  # texto
    50021: 22,  # barra de ferramentas
    50022: 13,  # dica
    50023: 35,  # estrutura
    50024: 36,  # item de estrutura
    50025: 16,  # personalizado
    50026: 20,  # grupo
    50027: 4,   # alça
    50028: 24,  # grade de dados
    50029: 29,  # item de dados
    50030: 15,  # documento
    50031: 62,  # botão dividido
    50032: 9,   # janela
    50033: 16,  # painel
    50034: 25,  # cabeçalho
    50035: 25,  # item de cabeçalho
    50036: 24,  # tabela
    50037: 1,   # barra de título
    50038: 21,  # separador
    50000: 43,  # botão
}

# Só estes tipos valem a pergunta "aceita ação?" — perguntar em texto estático
# custaria uma chamada por elemento, e janela grande tem centenas.
TIPOS_ACIONAVEIS = {
    50000,  # botão
    50002,  # caixa de seleção
    50003,  # caixa de combinação
    50004,  # campo de edição
    50005,  # link
    50007,  # item de lista
    50011,  # item de menu
    50013,  # botão de opção
    50015,  # controle deslizante
    50019,  # aba
    50024,  # item de estrutura
    50029,  # item de dados
    50031,  # botão dividido
}

_uia: int = 0
_uia_tentada = False


def _co_iniciar() -> None:
    try:
        ole32.CoInitializeEx(None, COINIT_MULTITHREADED)
    except Exception:  # noqa: BLE001 - já inicializado ou COM indisponível
        pass


def _uia_obter() -> int:
    """Ponteiro de IUIAutomation, criado uma vez. 0 quando a UIA não responde."""
    global _uia, _uia_tentada
    if _uia or _uia_tentada:
        return _uia
    _uia_tentada = True
    _co_iniciar()
    ponteiro = ctypes.c_void_p(0)
    try:
        # restype explícito: sem ele o ctypes devolve `int` de 32 bits e um
        # HRESULT de erro pode parecer sucesso. Custou uma rodada descobrir.
        ole32.CoCreateInstance.restype = ctypes.c_long
        ole32.CoCreateInstance.argtypes = [
            ctypes.POINTER(GUID),
            ctypes.c_void_p,
            wintypes.DWORD,
            ctypes.POINTER(GUID),
            ctypes.POINTER(ctypes.c_void_p),
        ]
        criacao = ole32.CoCreateInstance(
            ctypes.byref(CLSID_CUIAutomation),
            None,
            CLSCTX_INPROC_SERVER,
            ctypes.byref(IID_IUIAutomation),
            ctypes.byref(ponteiro),
        )
    except Exception:  # noqa: BLE001 - COM de terceiros: nunca propagar
        return 0
    if criacao != S_OK:
        return 0
    _uia = int(ponteiro.value or 0)
    return _uia


def _uia_da_janela(hwnd: int) -> int:
    raiz = _uia_obter()
    if not raiz:
        return 0
    elemento = ctypes.c_void_p(0)
    try:
        funcao = _metodo(raiz, UIA_ELEMENT_FROM_HANDLE, [wintypes.HWND, ctypes.POINTER(ctypes.c_void_p)])
        if funcao(raiz, wintypes.HWND(hwnd), ctypes.byref(elemento)) != S_OK:
            return 0
    except Exception:  # noqa: BLE001
        return 0
    return int(elemento.value or 0)


def _uia_walker() -> int:
    raiz = _uia_obter()
    if not raiz:
        return 0
    ponteiro = ctypes.c_void_p(0)
    try:
        funcao = _metodo(raiz, UIA_CONTROL_VIEW_WALKER, [ctypes.POINTER(ctypes.c_void_p)])
        if funcao(raiz, ctypes.byref(ponteiro)) != S_OK:
            return 0
    except Exception:  # noqa: BLE001
        return 0
    return int(ponteiro.value or 0)


def _uia_texto(elemento: int, indice: int) -> str:
    try:
        funcao = _metodo(elemento, indice, [ctypes.POINTER(ctypes.c_void_p)])
        saida = ctypes.c_void_p(0)
        if funcao(elemento, ctypes.byref(saida)) != S_OK:
            return ""
        return _bstr(saida.value)
    except Exception:  # noqa: BLE001
        return ""


def _uia_inteiro(elemento: int, indice: int) -> int | None:
    try:
        funcao = _metodo(elemento, indice, [ctypes.POINTER(ctypes.c_int)])
        saida = ctypes.c_int(0)
        if funcao(elemento, ctypes.byref(saida)) != S_OK:
            return None
        return int(saida.value)
    except Exception:  # noqa: BLE001
        return None


def _uia_caixa(elemento: int) -> list[int]:
    try:
        funcao = _metodo(elemento, UIA_EL_GET_RECT, [ctypes.POINTER(wintypes.RECT)])
        retangulo = wintypes.RECT()
        if funcao(elemento, ctypes.byref(retangulo)) != S_OK:
            return []
        largura = int(retangulo.right - retangulo.left)
        altura = int(retangulo.bottom - retangulo.top)
        if largura <= 0 or altura <= 0:
            return []
        return [int(retangulo.left), int(retangulo.top), largura, altura]
    except Exception:  # noqa: BLE001
        return []


def _uia_aceita(elemento: int, identificador: int) -> bool:
    """O elemento aceita este padrão? Só pergunta — não invoca nada."""
    try:
        funcao = _metodo(elemento, UIA_EL_GET_PATTERN, [ctypes.c_int, ctypes.POINTER(ctypes.c_void_p)])
        saida = ctypes.c_void_p(0)
        if funcao(elemento, identificador, ctypes.byref(saida)) != S_OK:
            return False
        if saida.value:
            _liberar(int(saida.value))
        return True
    except Exception:  # noqa: BLE001
        return False


def _uia_acao(elemento: int, tipo: int) -> str:
    """Nome curto do que o elemento aceita — o equivalente ao get_accDefaultAction."""
    # Onde se escreve: campo de edição e **documento**. O documento não está em
    # TIPOS_ACIONAVEIS (não se “clica” nele), mas é onde a digitação entra —
    # foi o que faltou para o campo do Bloco de Notas ganhar `ref`.
    if tipo in (50004, 50030) and _uia_aceita(elemento, PADRAO_VALOR):
        return "escrever"
    if tipo not in TIPOS_ACIONAVEIS:
        return ""
    if _uia_aceita(elemento, PADRAO_INVOCAR):
        return "clicar"
    if _uia_aceita(elemento, PADRAO_MARCAR):
        return "marcar"
    if _uia_aceita(elemento, PADRAO_EXPANDIR):
        return "abrir"
    if _uia_aceita(elemento, PADRAO_SELECIONAR):
        return "selecionar"
    return ""


def _uia_filho(walker: int, elemento: int) -> int:
    try:
        funcao = _metodo(walker, UIA_WALKER_FIRST_CHILD, [ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p)])
        saida = ctypes.c_void_p(0)
        if funcao(walker, elemento, ctypes.byref(saida)) != S_OK:
            return 0
        return int(saida.value or 0)
    except Exception:  # noqa: BLE001
        return 0


def _uia_irmao(walker: int, elemento: int) -> int:
    try:
        funcao = _metodo(walker, UIA_WALKER_NEXT_SIBLING, [ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p)])
        saida = ctypes.c_void_p(0)
        if funcao(walker, elemento, ctypes.byref(saida)) != S_OK:
            return 0
        return int(saida.value or 0)
    except Exception:  # noqa: BLE001
        return 0


def _uia_no(
    elemento: int,
    walker: int,
    profundidade: int,
    maxima: int,
    orcamento: _Orcamento,
    ancestrais: tuple[arvore.Ancestral, ...] = (),
) -> dict[str, Any] | None:
    """Um nó da árvore UIA — mesma forma do nó MSAA, para o resto não notar."""
    if not orcamento.gastar():
        return None
    tipo = _uia_inteiro(elemento, UIA_EL_GET_CONTROL_TYPE) or 0
    no: dict[str, Any] = {
        "papel": PAPEL_UIA.get(tipo, 0),
        "nome": _uia_texto(elemento, UIA_EL_GET_NAME),
    }
    # O nome do papel vem traduzido do próprio Windows (“botão”, “editar”).
    localizado = _uia_texto(elemento, UIA_EL_GET_LOCALIZED_TYPE)
    if localizado:
        no["papel_nome"] = localizado
    if _uia_inteiro(elemento, UIA_EL_GET_IS_ENABLED) == 0:
        no["desativado"] = True
    caixa = _uia_caixa(elemento)
    if caixa:
        no["caixa"] = caixa
    acao = _uia_acao(elemento, tipo)
    if acao:
        no["acao"] = acao

    if profundidade >= maxima:
        return no
    # As mesmas guardas da MSAA: moldura é folha, e ciclo para.
    pode, caminho = arvore.pode_descer(no, ancestrais)
    if not pode:
        return no

    filho = _uia_filho(walker, elemento)
    while filho:
        proximo = _uia_irmao(walker, filho)
        parar = False
        try:
            if _uia_inteiro(filho, UIA_EL_GET_IS_OFFSCREEN) != 1:
                criado = _uia_no(filho, walker, profundidade + 1, maxima, orcamento, caminho)
                if criado is None:
                    parar = True
                else:
                    no.setdefault("filhos", []).append(criado)
            elif orcamento.restante <= 0:
                parar = True
        finally:
            _liberar(filho)
        if parar:
            if proximo:
                _liberar(proximo)
            break
        filho = proximo
    return no


# ---------------------------------------------------------------------------
# Janelas filhas — onde a página do navegador realmente mora (0.82.5)
# ---------------------------------------------------------------------------
# Medição no PC do usuário (Chrome, Windows 10 14393), depois de consertar a
# repetição:
#
#     chrome.exe — Arena | Benchmark...: 47 elemento(s), 26 acionável(is) — fonte: msaa.
#     a UIAutomation mostrou 4; a MSAA mostrou mais (47).
#
# Os 47 são todos moldura: barra de título, barra de rolagem, “alça”. Nenhum
# item da página. E a UIA, lida a partir do HWND de topo, deu 4.
#
# O motivo é a arquitetura do Chrome: a página não é um elemento da janela de
# topo, é uma **janela filha** (`Chrome_RenderWidgetHostHWND`) — outro processo,
# outro modelo de acessibilidade. `ElementFromHandle` na janela de topo enxerga
# a moldura; quem tem a página é a janela filha.
#
# Por isso a leitura da UIA agora também desce nas janelas filhas.

EnumChildProc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

# Teto de janelas filhas examinadas: navegador costuma ter de 3 a 10.
# Quanto esperar antes de reler uma janela que respondeu só moldura. Curto de
# propósito: é a janela ligando a acessibilidade, não um programa carregando.
PAUSA_DE_DESPERTO = 0.4

FILHAS_MAXIMAS = 24


def janelas_filhas(handle: int, limite: int = FILHAS_MAXIMAS) -> list[dict[str, Any]]:
    """Janelas filhas de uma janela — onde vivem páginas, editores e documentos."""
    achadas: list[dict[str, Any]] = []

    def visitar(hwnd: int, _parametro: int) -> bool:
        if len(achadas) >= limite:
            return False
        try:
            classe = _classe(hwnd)
            titulo = _titulo(hwnd)
            if not classe and not titulo:
                return True
            achadas.append({"handle": int(hwnd), "classe": classe, "titulo": titulo})
        except Exception:  # noqa: BLE001
            pass
        return True

    try:
        user32.EnumChildWindows(wintypes.HWND(int(handle)), EnumChildProc(visitar), 0)
    except Exception:  # noqa: BLE001
        return achadas
    return achadas


# Classes conhecidas por carregar o conteúdo de um programa. Ler estas primeiro
# evita gastar o orçamento de nós com a moldura.
CLASSES_DE_CONTEUDO = (
    "chrome_renderwidgethosthwnd",
    "chrome_widgetwin_0",
    "mozillawindowclass",
    "internet explorer_server",
    "richedit",
    "scintilla",
    "edit",
    "webview",
    "document",
)


def _e_conteudo(classe: str) -> bool:
    limpa = (classe or "").strip().lower()
    return any(marca in limpa for marca in CLASSES_DE_CONTEUDO)


def _ler_uia_da_janela(hwnd: int, profundidade: int, limite: int) -> dict[str, Any] | None:
    """Lê a UIA de **um** HWND. Separado para poder ser somado na varredura."""
    raiz = _uia_da_janela(int(hwnd))
    if not raiz:
        return None
    walker = _uia_walker()
    try:
        if not walker:
            return None
        arvore_no = _uia_no(raiz, walker, 0, max(1, int(profundidade)), _Orcamento(int(limite)))
    except Exception:  # noqa: BLE001 - COM de terceiros: nunca propagar
        return None
    finally:
        _liberar(raiz)
        if walker:
            _liberar(walker)
    return arvore_no


def varrer_uia(handle: int, profundidade: int, limite: int) -> dict[str, Any] | None:
    """Lê a UIA da janela **e** das filhas; fica com a que tem conteúdo.

    Ler só a janela de topo devolvia 4 elementos no Chrome. A página está na
    janela filha — esta função é o que a traz.
    """
    janelas = [{"handle": int(handle), "classe": _classe(int(handle)), "titulo": _titulo(int(handle))}]
    filhas = janelas_filhas(int(handle))
    # Conteúdo primeiro: o orçamento de nós vai para a página, não para a moldura.
    filhas.sort(key=lambda item: 0 if _e_conteudo(item.get("classe", "")) else 1)
    janelas.extend(filhas)

    melhor: dict[str, Any] | None = None
    melhor_total = 0
    examinadas = 0
    for candidata in janelas:
        if examinadas >= FILHAS_MAXIMAS:
            break
        examinadas += 1
        arvore_no = _ler_uia_da_janela(int(candidata["handle"]), profundidade, max(1, int(limite)))
        if arvore_no is None:
            continue
        total = arvore.total_bruto({"raiz": arvore_no})
        if total > melhor_total:
            melhor_total = total
            melhor = {
                "janela": {
                    "handle": int(candidata["handle"]),
                    "titulo": candidata.get("titulo") or _titulo(int(handle)),
                    "classe": candidata.get("classe") or "",
                    "processo": _processo(int(handle)),
                },
                "raiz": arvore_no,
                "fonte": "uia",
            }
    return melhor


def _ler_uia(janela: dict[str, Any], profundidade: int, limite: int) -> dict[str, Any] | None:
    """UIA da janela e das filhas — a página do navegador está na filha."""
    achada = varrer_uia(int(janela["handle"]), profundidade, limite)
    if not achada:
        return None
    # O usuário pediu a janela X: o `alvo` continua sendo X, mesmo que a árvore
    # tenha vindo de uma janela filha dela.
    janela_final = dict(janela)
    if achada["janela"].get("handle") != janela.get("handle"):
        janela_final["de_filha"] = achada["janela"].get("classe") or "janela filha"
    achada["janela"] = janela_final
    return achada


def varrer_msaa(handle: int, profundidade: int, limite: int) -> dict[str, Any]:
    """MSAA da janela **e** das filhas; fica com a de conteúdo ou a maior.

    A 0.82.5 varria as filhas só na UIA. Mas o Chrome publica a página pela
    MSAA da janela filha (`Chrome_RenderWidgetHostHWND`) em muitas versões —
    e a leitura da janela de topo, sozinha, nunca chega lá.
    """
    principal = {"handle": int(handle), "titulo": _titulo(int(handle)), "classe": _classe(int(handle))}
    melhor = _ler_msaa(principal, profundidade, limite)
    melhor_total = arvore.total_bruto(melhor)
    melhor_conteudo = arvore.tem_conteudo(melhor)
    # Janela já rica: não vale pagar a leitura das filhas. Pobre ou só moldura:
    # é nelas que a página está.
    if melhor_conteudo and melhor_total >= 9:
        return melhor

    filhas = janelas_filhas(int(handle))
    filhas.sort(key=lambda item: 0 if _e_conteudo(item.get("classe", "")) else 1)
    for filha in filhas[:FILHAS_MAXIMAS]:
        try:
            tentativa = _ler_msaa(filha, profundidade, limite)
        except Exception:  # noqa: BLE001 - COM de terceiros
            continue
        total = arvore.total_bruto(tentativa)
        conteudo = arvore.tem_conteudo(tentativa)
        # Mesma regra de `arvore.escolher_fonte`: conteúdo vence moldura.
        if conteudo and not melhor_conteudo:
            melhor, melhor_total, melhor_conteudo = tentativa, total, True
        elif not (melhor_conteudo and not conteudo) and total > melhor_total:
            melhor, melhor_total, melhor_conteudo = tentativa, total, conteudo
        # Achou conteúdo: não paga a leitura das outras 23 janelas filhas.
        # As classes de conteúdo vêm primeiro na ordem, então a página é esta.
        if conteudo:
            break

    # O alvo continua sendo a janela pedida; só anotamos de onde veio.
    competente = melhor.get("janela", {}).get("handle")
    if competente is not None and int(competente) != int(handle):
        classe_filha = str(melhor.get("janela", {}).get("classe") or "janela filha")
        melhor["janela"] = dict(principal)
        melhor["janela"]["de_filha"] = classe_filha
    return melhor


def _ler_msaa(janela: dict[str, Any], profundidade: int, limite: int) -> dict[str, Any]:
    ponteiro = _abrir(int(janela["handle"]))
    if not ponteiro:
        return {
            "janela": janela,
            "raiz": None,
            "fonte": "msaa",
            "aviso": (
                "esta janela não publica árvore pela MSAA (ou está minimizada). "
                "A leitura pela UIAutomation foi tentada em seguida."
            ),
        }
    try:
        raiz = _no(ponteiro, CHILDID_SELF, 0, max(1, int(profundidade)), _Orcamento(int(limite)))
    finally:
        _liberar(ponteiro)
    return {"janela": janela, "raiz": raiz, "fonte": "msaa"}


def ler_janela(
    handle: int,
    profundidade: int = 6,
    limite: int = 600,
    fonte: str = "auto",
) -> dict[str, Any]:
    """Lê a árvore de uma janela. Sem árvore, devolve `raiz: None` e o motivo.

    `fonte`: `auto` (padrão — MSAA e, se ela vier pobre, UIAutomation), `msaa`
    ou `uia`. No `auto`, quem decide é a leitura que mostrou mais elementos.
    """
    janela = _janela(int(handle))
    pedido = (fonte or "auto").strip().lower()

    if pedido == "uia":
        bruto = _ler_uia(janela, profundidade, limite)
        if bruto:
            return bruto
        return {
            "janela": janela,
            "raiz": None,
            "fonte": "uia",
            "aviso": (
                "a UIAutomation não devolveu árvore para esta janela. "
                "Rode `arvore_sonda.py --diagnostico` para ver em qual passo o COM parou."
            ),
        }

    resultado = _ler_auto(janela, profundidade, limite, pedido)
    if pedido != "auto" or arvore.tem_conteudo(resultado):
        return resultado

    # A janela respondeu só moldura. Em navegador isso costuma ser o
    # **primeiro** estado: o Chrome liga a árvore da página quando percebe um
    # programa de acessibilidade olhando, e não instantaneamente. Medido no PC
    # do usuário: a primeira leitura deu 3 elementos sem conteúdo; a segunda,
    # na mesma janela e sem tocar em nada, deu 104 com conteúdo.
    #
    # Pagar uma segunda leitura (0,4 s) é barato perto de dizer que a janela
    # não tem nada.
    time.sleep(PAUSA_DE_DESPERTO)
    segunda = _ler_auto(janela, profundidade, limite, pedido)
    if arvore.tem_conteudo(segunda) or arvore.total_bruto(segunda) > arvore.total_bruto(resultado):
        segunda["acordou"] = (
            "esta janela só publicou o conteúdo na segunda leitura — é o caso do "
            "navegador, que liga a acessibilidade quando percebe alguém lendo."
        )
        return segunda
    return resultado


def _ler_auto(
    janela: dict[str, Any],
    profundidade: int,
    limite: int,
    pedido: str,
) -> dict[str, Any]:
    """Uma passada da leitura automática: MSAA e, se valer, UIAutomation."""
    msaa = varrer_msaa(int(janela["handle"]), profundidade, limite)
    msaa["janela"] = dict(
        janela,
        **({"de_filha": msaa["janela"]["de_filha"]} if msaa["janela"].get("de_filha") else {}),
    )
    if pedido == "msaa" or not arvore.quer_segunda_fonte(msaa):
        return msaa
    return arvore.escolher_fonte(msaa, _ler_uia(janela, profundidade, limite))


def diagnostico(alvo: str = "foco", handle: int | None = None) -> dict[str, Any]:
    """Passo a passo do COM, com o retorno de cada chamada.

    Por que existe: a 0.82.1 falhou na UIA **em silêncio** — a mensagem era
    “não devolveu árvore”, e isso não dizia se o problema era o COM, o índice
    de vtable ou a janela. Este relatório responde. É para ser lido por uma
    pessoa, não só por programa.

    `alvo` respeita a mesma escolha da leitura. Isto já esteve errado: o
    diagnóstico usava sempre a janela em foco, e no PC do usuário
    `--alvo chrome --diagnostico` mediu o **terminal** —

        janela                     msaa  uia   conteudo
        ConsoleWindowClass            1    12   nenhum

    — e respondeu “nenhum” para o Chrome sem nunca ter olhado o Chrome.

    **A ordem da medição importa.** Na 0.82.6 a tabela media a MSAA *depois*
    de a UIA já ter aberto a mesma janela, e no Chrome ela veio com 4
    elementos, não os 47 que a leitura da 0.82.4 encontrou. Agora a MSAA é
    medida primeiro, e o veredito é a leitura de verdade (`ler_janela`) — as
    mesmas funções que o JARVIS usa, na mesma ordem.
    """
    passos: list[dict[str, Any]] = []

    def anotar(nome: str, retorno: Any, detalhe: str = "") -> None:
        codigo = int(retorno) if isinstance(retorno, int) else None
        passos.append(
            {
                "passo": nome,
                "retorno": codigo if codigo is not None else str(retorno),
                "hex": f"0x{codigo & 0xFFFFFFFF:08X}" if codigo is not None else "",
                "ok": codigo == S_OK if codigo is not None else bool(retorno),
                "detalhe": detalhe,
            }
        )

    # 1) Qual janela. Só user32 aqui — nenhum COM foi aberto ainda.
    if handle is not None:
        # A sonda já escolheu (com a mesma `escolher_janela` da leitura, mais o
        # desvio do terminal). Escolher de novo aqui poderia cair em outra janela.
        janela = _janela(int(handle))
    else:
        try:
            janela = arvore.escolher_janela(alvo, janelas=janelas(), foco=janela_em_foco())
        except arvore.ArvoreError as exc:
            anotar("escolher janela", False, str(exc)[:120])
            return {"ok": False, "passos": passos, "nota": str(exc)}
    anotar(
        "escolher janela",
        S_OK,
        f"alvo “{alvo}” → {janela.get('processo') or '?'} — {str(janela.get('titulo') or '')[:60]}",
    )

    # 2) A tabela: a janela pedida e as filhas dela.
    medidas = [{"handle": int(janela["handle"]), "classe": _classe(int(janela["handle"])), "filha": False}]
    for filha in janelas_filhas(int(janela["handle"]), limite=12):
        medidas.append({"handle": int(filha["handle"]), "classe": filha.get("classe"), "filha": True})

    varredura: list[dict[str, Any]] = []
    for item in medidas:
        varredura.append(
            {
                "classe": item.get("classe") or "(sem classe)",
                "titulo": _titulo(int(item["handle"]))[:50],
                "processo": _processo(int(item["handle"])),
                "filha": bool(item.get("filha")),
            }
        )

    # 3) MSAA de todas elas, antes de a UIA tocar em qualquer uma.
    try:
        _co_iniciar()
    except Exception:  # noqa: BLE001 - a MSAA avisa sozinha se não der
        pass
    for linha, item in zip(varredura, medidas):
        try:
            bruto = _ler_msaa({"handle": item["handle"]}, 6, 400)
            linha["msaa"] = arvore.total_bruto(bruto)
            linha["msaa_conteudo"] = arvore.tem_conteudo(bruto)
        except Exception:  # noqa: BLE001 - COM de terceiros
            linha["msaa"], linha["msaa_conteudo"] = 0, False

    # 4) O veredito é a leitura de verdade — não uma segunda implementação dela.
    veredito: dict[str, Any] = {"fonte": "", "total": 0, "conteudo": False, "de_filha": ""}
    try:
        escolhida = ler_janela(int(janela["handle"]), 6, 400)
        veredito = {
            "fonte": str(escolhida.get("fonte") or ""),
            "total": arvore.total_bruto(escolhida),
            "conteudo": arvore.tem_conteudo(escolhida),
            "de_filha": str((escolhida.get("janela") or {}).get("de_filha") or ""),
        }
    except Exception as exc:  # noqa: BLE001 - COM de terceiros
        veredito["erro"] = type(exc).__name__
    anotar(
        "leitura final (como a sonda lê)",
        S_OK if veredito["conteudo"] else "sem conteúdo",
        f"fonte: {veredito['fonte'] or '?'} — {veredito['total']} elemento(s)"
        + (f", lido de dentro: {veredito['de_filha']}" if veredito.get("de_filha") else ""),
    )

    # 5) O COM da UIAutomation, passo a passo.
    try:
        _co_iniciar()
        anotar("CoInitializeEx(MTA)", S_OK, "já iniciado ou iniciado agora — os dois servem")
    except Exception as exc:  # noqa: BLE001
        anotar("CoInitializeEx(MTA)", type(exc).__name__, str(exc))

    ponteiro = ctypes.c_void_p(0)
    uia_ok = False
    criacao: Any = -1
    try:
        ole32.CoCreateInstance.restype = ctypes.c_long
        criacao = ole32.CoCreateInstance(
            ctypes.byref(CLSID_CUIAutomation),
            None,
            CLSCTX_INPROC_SERVER,
            ctypes.byref(IID_IUIAutomation),
            ctypes.byref(ponteiro),
        )
    except Exception as exc:  # noqa: BLE001
        anotar("CoCreateInstance(IUIAutomation)", type(exc).__name__, str(exc))
        criacao = -1

    if criacao == S_OK and ponteiro.value:
        uia_ok = True
        anotar("CoCreateInstance(IUIAutomation)", criacao, "objeto criado")
        raiz = int(ponteiro.value)
        walker = ctypes.c_void_p(0)
        try:
            funcao = _metodo(raiz, UIA_CONTROL_VIEW_WALKER, [ctypes.POINTER(ctypes.c_void_p)])
            retorno = funcao(raiz, ctypes.byref(walker))
        except Exception as exc:  # noqa: BLE001
            retorno = type(exc).__name__  # type: ignore[assignment]
        anotar("get_ControlViewWalker (índice 14)", retorno, "percorre a árvore de controles")

        elemento = ctypes.c_void_p(0)
        try:
            funcao = _metodo(raiz, UIA_ELEMENT_FROM_HANDLE, [wintypes.HWND, ctypes.POINTER(ctypes.c_void_p)])
            retorno = funcao(raiz, wintypes.HWND(int(janela["handle"])), ctypes.byref(elemento))
        except Exception as exc:  # noqa: BLE001
            retorno = type(exc).__name__  # type: ignore[assignment]
        anotar(
            "ElementFromHandle (índice 6)",
            retorno,
            f"janela: {janela.get('titulo') or janela.get('processo') or janela.get('handle')}",
        )
        if elemento.value:
            tipo = _uia_inteiro(int(elemento.value), UIA_EL_GET_CONTROL_TYPE)
            nome = _uia_texto(int(elemento.value), UIA_EL_GET_NAME)
            anotar("get_CurrentControlType", S_OK if tipo is not None else "falhou", f"tipo={tipo}")
            anotar("get_CurrentName", S_OK if nome else "vazio", f"nome={nome[:60]!r}")
            _liberar(int(elemento.value))
    else:
        anotar("CoCreateInstance(IUIAutomation)", criacao, "sem ponteiro — a leitura fica só na MSAA")

    # 6) A coluna da UIA, agora que ela está aberta.
    for linha, item in zip(varredura, medidas):
        try:
            no = _ler_uia_da_janela(int(item["handle"]), 6, 400)
            linha["uia"] = arvore.total_bruto({"raiz": no}) if no else 0
            linha["uia_conteudo"] = arvore.tem_conteudo({"raiz": no}) if no else False
        except Exception:  # noqa: BLE001 - COM de terceiros
            linha["uia"], linha["uia_conteudo"] = 0, False

    com_conteudo = [linha for linha in varredura if linha.get("uia_conteudo") or linha.get("msaa_conteudo")]
    anotar(
        f"varredura de janelas ({len(varredura)})",
        S_OK if com_conteudo else "sem conteúdo",
        f"{len(com_conteudo)} janela(s) entregaram conteúdo de verdade (não só moldura)",
    )

    ok = all(passo["ok"] for passo in passos if passo["passo"].startswith(("CoCreate", "get_Control", "ElementFrom")))
    return {
        "ok": ok,
        "janela": {chave: janela.get(chave) for chave in ("handle", "titulo", "classe", "processo")},
        "uia": uia_ok,
        "veredito": veredito,
        "passos": passos,
        "varredura": varredura,
        "nota": (
            "todos os passos responderam: a UIAutomation está disponível nesta máquina."
            if ok
            else "algum passo falhou — o retorno mostra qual. 0x80004005 = falha genérica; "
            "0x80070005 = acesso negado (janela elevada)."
        ),
    }


def estado() -> dict[str, Any]:
    """O que este sistema oferece — sem prometer o que não foi medido."""
    try:
        versao = sys.getwindowsversion()
        build = int(versao.build)
    except Exception:  # noqa: BLE001
        build = 0
    return {
        "sistema": "Windows",
        "build": build,
        # A MSAA existe desde o Windows 2000; a UIA (a árvore que o Narrador usa)
        # melhorou muito no 8/10. 1809 é o piso que o agent-desktop exige —
        # citado como referência, não como exigência nossa.
        "msaa": True,
        "uia": _uia_obter() != 0,
        "nota": (
            "duas fontes, sem instalar nada: MSAA (oleacc) e UIAutomation (uiautomationcore). "
            "A segunda é a que os programas de hoje publicam — o console, por exemplo, só aparece nela. "
            "Jogos e instaladores antigos podem não publicar em nenhuma."
        ),
    }


# ---------------------------------------------------------------------------
# Agir por ref — a etapa 2 (0.86.0)
# ---------------------------------------------------------------------------
# O que este bloco faz: navega até o elemento pelo **caminho** que a leitura
# guardou (qual filho, em cada nível) e pede a ação ao próprio elemento.
#
# O que ele não faz: mover o mouse. A ação vem de `accDoDefaultAction` (MSAA)
# ou do padrão de invocação (UIA). No PC do usuário a tela não responde a
# toque e não há mouse USB — clique por coordenada seria o único caminho que
# não funciona ali. Quando o elemento só aceita clique físico, a resposta diz
# isso, em vez de fingir que agiu.

# Índices da vtable de IAccessible, conferidos contra oleacc.h:
#   get_accDefaultAction 20, accSelect 21, accLocation 22, accNavigate 23,
#   accHitTest 24, accDoDefaultAction 25, put_accName 26, put_accValue 27.
#
# A 0.86.0 usava 21 para `accDoDefaultAction` e 23 para `accSelect` — um a mais
# e outro a menos. Resultado: o "foco" chamava `accNavigate` (que devolve
# S_FALSE) e o JARVIS dizia "o elemento recusou o foco". Não era o Bloco de
# Notas recusando: era o número errado. Corrigido na 0.87.1.
ACC_SELECT = 21
ACC_DO_DEFAULT_ACTION = 25
PUT_ACC_VALUE = 27
GET_ACC_VALUE = 11
SELFLAG_TAKEFOCUS = 0x1
SELFLAG_TAKESELECTION = 0x2
VT_BSTR = 8


def _navegar(ponteiro: int, caminho: list[int]) -> tuple[int, int]:
    """Desce a árvore pelo caminho. Devolve `(ponteiro, child_id)` do alvo.

    O ponteiro devolvido é o **dono** do elemento: para filho simples (VT_I4) é
    o pai, com o `child_id` do filho — é assim que a MSAA endereça.
    """
    atual, filho = int(ponteiro), CHILDID_SELF
    for posicao in caminho:
        lista = _filhos(atual, max(1, int(posicao) + 1))
        if posicao >= len(lista):
            raise ValueError(f"o caminho saiu da árvore no nível {posicao}.")
        novo_ponteiro, novo_filho = lista[int(posicao)]
        if novo_ponteiro:
            if atual != int(ponteiro) or filho != CHILDID_SELF:
                _liberar(atual)
            atual = novo_ponteiro
            filho = CHILDID_SELF
        else:
            # Filho simples: continua endereçado pelo pai.
            filho = novo_filho
    return atual, filho


def _selecionar(ponteiro: int, filho: int) -> int:
    """`accSelect(TAKEFOCUS|TAKESELECTION)` — devolve o HRESULT cru.

    Não move o mouse. S_OK é sucesso; S_FALSE quer dizer "fez, mas não como eu
    pedi", e é tratado como tentativa a confirmar pelo foco real.
    """
    try:
        funcao = _metodo(ponteiro, ACC_SELECT, [ctypes.c_long, VARIANT])
        return int(funcao(ponteiro, SELFLAG_TAKEFOCUS | SELFLAG_TAKESELECTION, _var_filho(filho)))
    except Exception:  # noqa: BLE001
        return -1


def _focar(ponteiro: int, filho: int) -> bool:
    """Pede o foco ao elemento. Não move o mouse."""
    return _selecionar(ponteiro, filho) in (S_OK, 1)


class _INFO_GUI(ctypes.Structure):
    """`GUITHREADINFO`: onde o teclado está indo, de verdade."""

    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("hwndActive", wintypes.HWND),
        ("hwndFocus", wintypes.HWND),
        ("hwndCapture", wintypes.HWND),
        ("hwndMenuOwner", wintypes.HWND),
        ("hwndMoveSize", wintypes.HWND),
        ("hwndCaret", wintypes.HWND),
        ("rcCaret", ctypes.c_long * 4),
    ]


def foco_de_agora(handle: int) -> int:
    """HWND que está com o teclado na thread da janela. 0 quando não dá para ver.

    Existe porque "pedi o foco" e "o foco veio" são coisas diferentes. Antes de
    digitar, o JARVIS confere de quem é o teclado — se não for da janela alvo,
    ele não digita nada em vez de escrever no programa errado.
    """
    try:
        thread = user32.GetWindowThreadProcessId(wintypes.HWND(int(handle)), None)
        if not thread:
            return 0
        info = _INFO_GUI()
        info.cbSize = ctypes.sizeof(_INFO_GUI)
        if not user32.GetGUIThreadInfo(thread, ctypes.byref(info)):
            return 0
        return int(info.hwndFocus or 0)
    except Exception:  # noqa: BLE001
        return 0


def _pertence(hwnd: int, ascendente: int) -> bool:
    """`hwnd` é a janela `ascendente` ou está dentro dela?"""
    atual = int(hwnd)
    for _ in range(64):
        if not atual:
            return False
        if atual == int(ascendente):
            return True
        atual = int(user32.GetParent(wintypes.HWND(atual)) or 0)
    return False


def _teclado_esta_na_janela(handle: int) -> bool:
    """Confirma que o teclado está dentro da janela alvo antes de digitar."""
    hwnd = foco_de_agora(handle)
    return bool(hwnd) and _pertence(hwnd, handle)


def _valor(ponteiro: int, filho: int) -> str:
    """Texto que o elemento publica como valor (o conteúdo do campo)."""
    try:
        funcao = _metodo(ponteiro, GET_ACC_VALUE, [VARIANT, ctypes.POINTER(ctypes.c_void_p)])
        saida = ctypes.c_void_p(0)
        if funcao(ponteiro, _var_filho(filho), ctypes.byref(saida)) != S_OK:
            return ""
        return _bstr(saida.value)
    except Exception:  # noqa: BLE001
        return ""


def _por_valor(ponteiro: int, filho: int, texto: str) -> bool:
    """`put_accValue` — escreve no valor do campo, sem teclado e sem foco.

    É o terceiro degrau: quando o campo não aceita foco nem seleção, a MSAA
    ainda deixa escrever no valor. Substitui o conteúdo, por isso só é usado
    quando o campo está vazio — sobrescrever o que a pessoa escreveu seria
    "dar certo" destruindo trabalho.
    """
    bstr = None
    try:
        oleaut32.SysAllocString.restype = ctypes.c_void_p
        oleaut32.SysAllocString.argtypes = [ctypes.c_wchar_p]
        bstr = oleaut32.SysAllocString(texto)
        if not bstr:
            return False
        valor = VARIANT()
        valor.vt = VT_BSTR
        valor.valor = int(bstr)
        funcao = _metodo(ponteiro, PUT_ACC_VALUE, [VARIANT, ctypes.c_void_p])
        return int(funcao(ponteiro, _var_filho(filho), ctypes.c_void_p(int(bstr)))) == S_OK
    except Exception:  # noqa: BLE001
        return False
    finally:
        if bstr:
            try:
                oleaut32.SysFreeString(ctypes.c_void_p(int(bstr)))
            except Exception:  # noqa: BLE001
                pass


def _conferir(alvo: int, filho: int, texto: str) -> bool | None:
    """Depois de digitar, o campo mostra o texto? `None` = não publica valor.

    "Mandei as teclas" e "o texto entrou" são coisas diferentes. Sem esta
    conferência, o JARVIS diria "Feito" sem saber — e quem está na frente da
    tela descobre sozinho que não era verdade.
    """
    try:
        time.sleep(0.2)
        visto = _valor(alvo, filho)
    except Exception:  # noqa: BLE001
        return None
    if not visto:
        return None
    return texto.strip() in " ".join(visto.split())


def _digitar_em(alvo: int, filho: int, handle: int, texto: str) -> dict[str, Any]:
    """Os três degraus da escrita, do mais natural ao mais direto.

    1. foco no elemento exato (accSelect) e teclado — é o que um humano faz;
    2. foco no dono (o campo inteiro) e teclado — quando o texto é filho simples;
    3. `put_accValue` no valor do campo — sem foco, só quando ele está vazio.

    O teclado só é usado quando o próprio Windows confirma que o foco está
    dentro da janela alvo. Se não está, o JARVIS não digita às cegas.
    """
    limites: list[str] = []

    estado = _selecionar(alvo, filho)
    if estado in (S_OK, 1):
        if _teclado_esta_na_janela(handle):
            from server import mesa

            mesa.digitar(texto)
            return {
                "executou": True,
                "como": "foco + teclado",
                "caracteres": len(texto),
                "conferido": _conferir(alvo, filho, texto),
            }
        limites.append("o foco não veio (o Windows diz que o teclado está em outra janela)")
    elif estado >= 0:
        limites.append(f"accSelect devolveu 0x{estado & 0xFFFFFFFF:08X}")
    else:
        limites.append("accSelect falhou")

    if filho != CHILDID_SELF:
        estado = _selecionar(alvo, CHILDID_SELF)
        if estado in (S_OK, 1) and _teclado_esta_na_janela(handle):
            from server import mesa

            mesa.digitar(texto)
            return {
                "executou": True,
                "como": "foco no campo + teclado",
                "caracteres": len(texto),
                "conferido": _conferir(alvo, filho, texto),
            }
        limites.append("o campo inteiro também não aceitou foco")

    atual = _valor(alvo, filho)
    if atual.strip():
        limites.append("o campo já tem texto e eu não sobrescrevo o que não escrevi")
    elif _por_valor(alvo, filho, texto) and _valor(alvo, filho).strip():
        return {
            "executou": True,
            "como": "valor do campo (put_accValue, sem teclado)",
            "caracteres": len(texto),
            "conferido": True,
        }
    else:
        limites.append("o campo não aceita escrita por valor (put_accValue)")

    return {
        "executou": False,
        "como": "nenhum",
        "motivo": "; ".join(limites) + ". Nada foi digitado.",
    }


def executar_ref(
    handle: int,
    caminho: list[int],
    acao: str,
    texto: str = "",
    caixa: list[int] | None = None,
) -> dict[str, Any]:
    """Executa `clicar` ou `digitar` num elemento, pelo caminho da leitura.

    Devolve `executou`, `como` e — quando não deu — `motivo` com a saída.
    `handle` é a janela de onde o caminho veio: se ela mudou, a navegação não
    acha o alvo e isso é dito, não improvisado.
    """
    pedido = (acao or "clicar").strip().lower()
    if pedido == "escrever":
        pedido = "digitar"
    if not janela_muda(handle):
        return {"executou": False, "como": "nenhum", "motivo": "a janela não está mais aberta."}

    ponteiro = _abrir(int(handle))
    if not ponteiro:
        return {
            "executou": False,
            "como": "nenhum",
            "motivo": "esta janela não publica árvore pela MSAA agora — a leitura pode ter vindo da UIAutomation.",
        }
    try:
        alvo, filho = _navegar(ponteiro, [int(item) for item in caminho])
    except Exception as exc:  # noqa: BLE001
        _liberar(ponteiro)
        return {"executou": False, "como": "nenhum", "motivo": f"não achei o elemento: {exc}"}

    try:
        nome = _nome(alvo, filho)[:60]
        if pedido == "digitar":
            feito = _digitar_em(alvo, filho, int(handle), texto)
            feito["elemento"] = nome
            return feito

        funcao = _metodo(alvo, ACC_DO_DEFAULT_ACTION, [VARIANT])
        codigo = funcao(alvo, _var_filho(filho))
        if codigo == S_OK:
            return {"executou": True, "como": "ação padrão do elemento", "elemento": nome}
        # Sem ação padrão: tenta dar foco (é o que um clique faria) e diz.
        if _focar(alvo, filho):
            return {
                "executou": True,
                "como": "foco (o elemento não tem ação padrão)",
                "elemento": nome,
            }
        return {
            "executou": False,
            "como": "nenhum",
            "motivo": (
                f"“{nome}” não tem ação padrão nem aceita foco (accDoDefaultAction devolveu 0x{codigo & 0xFFFFFFFF:08X})"
                + (f" — o centro dele é {caixa[0] + caixa[2] // 2},{caixa[1] + caixa[3] // 2}." if caixa else ".")
                + " Um clique físico resolveria; eu não movo o mouse sem você pedir."
            ),
        }
    finally:
        if alvo != ponteiro:
            _liberar(alvo)
        _liberar(ponteiro)


def janela_muda(handle: int) -> bool:
    """A janela ainda existe?"""
    try:
        return bool(user32.IsWindow(wintypes.HWND(int(handle))))
    except Exception:  # noqa: BLE001
        return False


def escolher_janela(alvo: str, *, janelas: list[dict[str, Any]], foco: dict[str, Any] | None) -> dict[str, Any]:
    """Atalho para a escolha de janela de `arvore` — usado pela sonda de agir."""
    return arvore.escolher_janela(alvo, janelas=janelas, foco=foco)
