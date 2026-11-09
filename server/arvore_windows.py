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


def _no(ponteiro: int, filho: int, profundidade: int, maxima: int, orcamento: _Orcamento) -> dict[str, Any] | None:
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

    for ponteiro_filho, id_filho in _filhos(ponteiro, orcamento.restante):
        usar = ponteiro_filho or ponteiro
        criado = _no(usar, id_filho, profundidade + 1, maxima, orcamento)
        if criado is None:
            break
        no.setdefault("filhos", []).append(criado)
        if ponteiro_filho:
            _liberar(ponteiro_filho)
    return no


def ler_janela(handle: int, profundidade: int = 6, limite: int = 600) -> dict[str, Any]:
    """Lê a árvore de uma janela. Sem árvore, devolve `raiz: None` e o motivo."""
    janela = _janela(int(handle))
    ponteiro = _abrir(int(handle))
    if not ponteiro:
        return {
            "janela": janela,
            "raiz": None,
            "fonte": "msaa",
            "aviso": (
                "esta janela não publica árvore de acessibilidade (ou está minimizada). "
                "Restaurada na tela, a maioria dos programas publica."
            ),
        }
    try:
        raiz = _no(ponteiro, CHILDID_SELF, 0, max(1, int(profundidade)), _Orcamento(int(limite)))
    finally:
        _liberar(ponteiro)
    return {"janela": janela, "raiz": raiz, "fonte": "msaa"}


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
        # A MSAA existe desde o Windows 2000; a UIA (usada pelo app do Narrador
        # mais novo) melhorou muito no 8/10. 1809 é o piso que o agent-desktop
        # exige — citado aqui como referência, não como exigência nossa.
        "msaa": True,
        "nota": (
            "leitura pela MSAA (oleacc), sem instalar nada. Programas modernos publicam "
            "árvore melhor; aplicativos antigos e jogos podem não publicar."
        ),
    }
