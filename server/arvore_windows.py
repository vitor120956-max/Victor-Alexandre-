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
    no: dict[str, Any] = {
        "papel": _papel(ponteiro, filho),
        "nome": _nome(ponteiro, filho),
    }
    acao = _acao(ponteiro, filho)
    if acao:
        no["acao"] = acao
    caixa = _onde(ponteiro, filho)
    if caixa and caixa[2] > 0 and caixa[3] > 0:
        no["caixa"] = caixa

    if profundidade >= maxima:
        return no
    pode, caminho = arvore.pode_descer(no, ancestrais)
    if not pode:
        return no

    for ponteiro_filho, id_filho in _filhos(ponteiro, orcamento.restante):
        usar = ponteiro_filho or ponteiro
        criado = _no(usar, id_filho, profundidade + 1, maxima, orcamento, caminho)
        if criado is None:
            break
        no.setdefault("filhos", []).append(criado)
        if ponteiro_filho:
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
    if tipo not in TIPOS_ACIONAVEIS:
        return ""
    if tipo == 50004 and _uia_aceita(elemento, PADRAO_VALOR):
        return "escrever"
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


def _ler_uia(janela: dict[str, Any], profundidade: int, limite: int) -> dict[str, Any] | None:
    raiz = _uia_da_janela(int(janela["handle"]))
    if not raiz:
        return None
    walker = _uia_walker()
    try:
        if not walker:
            return None
        arvore = _uia_no(raiz, walker, 0, max(1, int(profundidade)), _Orcamento(int(limite)))
    except Exception:  # noqa: BLE001 - COM de terceiros: nunca propagar
        return None
    finally:
        _liberar(raiz)
        if walker:
            _liberar(walker)
    return {"janela": janela, "raiz": arvore, "fonte": "uia"}


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

    msaa = _ler_msaa(janela, profundidade, limite)
    if pedido == "msaa" or not arvore.precisa_segunda_fonte(msaa):
        return msaa
    return arvore.escolher_fonte(msaa, _ler_uia(janela, profundidade, limite))


def diagnostico() -> dict[str, Any]:
    """Passo a passo do COM, com o retorno de cada chamada.

    Por que existe: a 0.82.1 falhou na UIA **em silêncio** — a mensagem era
    “não devolveu árvore”, e isso não dizia se o problema era o COM, o índice
    de vtable ou a janela. Este relatório responde. É para ser lido por uma
    pessoa, não só por programa.
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

    try:
        _co_iniciar()
        anotar("CoInitializeEx(MTA)", S_OK, "já iniciado ou iniciado agora — os dois servem")
    except Exception as exc:  # noqa: BLE001
        anotar("CoInitializeEx(MTA)", type(exc).__name__, str(exc))

    ponteiro = ctypes.c_void_p(0)
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
        return {"ok": False, "passos": passos, "nota": "o ctypes não conseguiu nem chamar o COM."}

    anotar("CoCreateInstance(IUIAutomation)", criacao, "objeto criado" if ponteiro.value else "sem ponteiro")
    if criacao != S_OK or not ponteiro.value:
        return {
            "ok": False,
            "passos": passos,
            "nota": "a UIAutomation não pôde ser criada neste sistema; a leitura fica só na MSAA.",
        }

    raiz = int(ponteiro.value)
    walker = ctypes.c_void_p(0)
    try:
        funcao = _metodo(raiz, UIA_CONTROL_VIEW_WALKER, [ctypes.POINTER(ctypes.c_void_p)])
        retorno = funcao(raiz, ctypes.byref(walker))
    except Exception as exc:  # noqa: BLE001
        retorno = type(exc).__name__  # type: ignore[assignment]
    anotar("get_ControlViewWalker (índice 14)", retorno, "percorre a árvore de controles")

    janela = janela_em_foco()
    if not janela:
        anotar("GetForegroundWindow", False, "nenhuma janela em foco")
        return {"ok": False, "passos": passos, "nota": "sem janela em foco para testar."}

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

    ok = all(passo["ok"] for passo in passos if passo["passo"].startswith(("CoCreate", "get_Control", "ElementFrom")))
    return {
        "ok": ok,
        "passos": passos,
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
