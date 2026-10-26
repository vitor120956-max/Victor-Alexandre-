"""Mouse e teclado do próprio PC — só quando o dono autoriza, e com freio.

O JARVIS não tem tela própria: para *ver* o que acontece, ele olha os títulos
das janelas; para *agir*, move o cursor, clica e digita. Não existe dependência
nova para isso: `ctypes` fala direto com a API do Windows.

O que este módulo **não** faz:

- não lê tela (não faz captura de imagem nem OCR de janela alheia);
- não roda comando nem abre arquivo (isso é `sistema.*`, com allowlist);
- não adivinha onde clicar: quem pede dá a coordenada, que é conferida contra o
  tamanho real da tela.

O freio que importa é o **pânico por movimento**: antes de cada passo, o módulo
compara a posição do cursor com a que ele mesmo deixou. Se mudou — quer dizer
que a mão do dono está no mouse —, ele **para na hora** e devolve o que fez até
ali. É o mesmo `FAILSAFE` do pyautogui, sem instalar o pyautogui.
"""
from __future__ import annotations

import ctypes
import time
from typing import Any, Protocol

LARGURA_PADRAO = (1920, 1080)
MAX_PASSOS = 200
PAUSA_PADRAO = 0.004


class MesaError(ValueError):
    """Ação recusada: fora da tela, sistema errado, ou mouse tomado pelo dono."""


class Backend(Protocol):
    """O mínimo que o Windows precisa oferecer. Nos testes é um dublê."""

    def posicao(self) -> tuple[int, int]: ...

    def tamanho(self) -> tuple[int, int]: ...

    def mover(self, x: int, y: int) -> None: ...

    def clicar(self, botao: str, vezes: int) -> None: ...

    def teclar(self, nome: str) -> None: ...

    def digitar(self, texto: str) -> None: ...

    def janelas(self) -> list[str]: ...

    def focar(self, trecho: str) -> str: ...

    def dormir(self, segundos: float) -> None: ...


# ------------------------------------------------------------------ Windows

class _Ponto(ctypes.Structure):
    """`POINT` do Windows."""

    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


class _Windows:
    """Implementação real, via `ctypes`. Só é construída no Windows."""

    def __init__(self) -> None:
        self._user32 = ctypes.windll.user32
        self._user32.SetCursorPos.argtypes = [ctypes.c_int, ctypes.c_int]
        self._user32.SetCursorPos.restype = ctypes.c_bool
        self._user32.GetCursorPos.argtypes = [ctypes.POINTER(_Ponto)]
        self._user32.GetSystemMetrics.argtypes = [ctypes.c_int]
        self._user32.SetForegroundWindow.argtypes = [ctypes.c_void_p]
        self._user32.mouse_event.argtypes = [
            ctypes.c_uint, ctypes.c_uint, ctypes.c_uint, ctypes.c_uint, ctypes.c_void_p
        ]
        self._user32.keybd_event.argtypes = [ctypes.c_ubyte, ctypes.c_ubyte, ctypes.c_uint, ctypes.c_void_p]

    def posicao(self) -> tuple[int, int]:
        ponto = _Ponto()
        self._user32.GetCursorPos(ctypes.byref(ponto))
        return int(ponto.x), int(ponto.y)

    def tamanho(self) -> tuple[int, int]:
        return int(self._user32.GetSystemMetrics(0)), int(self._user32.GetSystemMetrics(1))

    def mover(self, x: int, y: int) -> None:
        if not self._user32.SetCursorPos(int(x), int(y)):
            raise MesaError("O Windows recusou mover o cursor (sessão sem área de trabalho?).")

    def clicar(self, botao: str, vezes: int) -> None:
        marcas = {"esquerdo": (0x0002, 0x0004), "direito": (0x0008, 0x0010), "meio": (0x0020, 0x0040)}
        baixo, cima = marcas[botao]
        for _ in range(max(1, vezes)):
            self._user32.mouse_event(baixo, 0, 0, 0, 0)
            self._user32.mouse_event(cima, 0, 0, 0, 0)

    def teclar(self, nome: str) -> None:
        codigo = TECLAS.get(nome.lower())
        if codigo is None:
            raise MesaError(f"Tecla desconhecida: {nome}. Aceito: {', '.join(sorted(TECLAS))}.")
        if len(codigo) == 1:
            self._user32.keybd_event(codigo[0], 0, 0, 0)
            self._user32.keybd_event(codigo[0], 0, 0x0002, 0)
            return
        modificador, tecla = codigo
        self._user32.keybd_event(modificador, 0, 0, 0)
        self._user32.keybd_event(tecla, 0, 0, 0)
        self._user32.keybd_event(tecla, 0, 0x0002, 0)
        self._user32.keybd_event(modificador, 0, 0x0002, 0)

    def digitar(self, texto: str) -> None:
        for caractere in texto:
            self._user32.keybd_event(0, ord(caractere), 0x0004, 0)
            self._user32.keybd_event(0, ord(caractere), 0x0004 | 0x0002, 0)

    def janelas(self) -> list[str]:
        titulos: list[str] = []
        processo = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)

        def visitar(janela, _parametro):
            if not self._user32.IsWindowVisible(janela):
                return True
            tamanho = self._user32.GetWindowTextLengthW(janela)
            if tamanho <= 0:
                return True
            buffer = ctypes.create_unicode_buffer(tamanho + 1)
            self._user32.GetWindowTextW(janela, buffer, tamanho + 1)
            if buffer.value.strip():
                titulos.append(buffer.value.strip())
            return True

        self._user32.EnumWindows(processo(visitar), 0)
        return titulos

    def focar(self, trecho: str) -> str:
        alvo = (trecho or "").strip().lower()
        if not alvo:
            raise MesaError("Diga qual janela focar (um pedaço do título).")
        encontrada: list[Any] = []

        processo = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)

        def visitar(janela, _parametro):
            if not self._user32.IsWindowVisible(janela):
                return True
            tamanho = self._user32.GetWindowTextLengthW(janela)
            if tamanho <= 0:
                return True
            buffer = ctypes.create_unicode_buffer(tamanho + 1)
            self._user32.GetWindowTextW(janela, buffer, tamanho + 1)
            titulo = buffer.value.strip()
            if titulo and alvo in titulo.lower():
                encontrada.append((janela, titulo))
                return False
            return True

        self._user32.EnumWindows(processo(visitar), 0)
        if not encontrada:
            raise MesaError(f"Nenhuma janela com “{trecho}” no título está aberta.")
        janela, titulo = encontrada[0]
        self._user32.SetForegroundWindow(janela)
        return titulo

    def dormir(self, segundos: float) -> None:
        time.sleep(segundos)


# Códigos de tecla que valem a pena ("v" é Virtual-Key, não ASCII).
TECLAS: dict[str, tuple[int, ...] | tuple[int]] = {
    "enter": (0x0D,),
    "tab": (0x09,),
    "esc": (0x1B,),
    "sublinhado": (0x5F,),
    "backspace": (0x08,),
    "espaco": (0x20,),
    "seta_esquerda": (0x25,),
    "seta_cima": (0x26,),
    "seta_direita": (0x27,),
    "seta_baixo": (0x28,),
    "delete": (0x2E,),
    "home": (0x24,),
    "fim": (0x23,),
    "page_up": (0x21,),
    "page_down": (0x22,),
    "ctrl+c": (0x11, 0x43),
    "ctrl+v": (0x11, 0x56),
    "ctrl+x": (0x11, 0x58),
    "ctrl+z": (0x11, 0x5A),
    "ctrl+s": (0x11, 0x53),
    "ctrl+a": (0x11, 0x41),
    "alt+f4": (0x12, 0x73),
    "win": (0x5B,),
}


def _backend_padrao() -> Backend:
    import os

    if os.name != "nt":
        raise MesaError(
            "Mouse e teclado só existem no Windows. Aqui não há tela para controlar."
        )
    return _Windows()


# ------------------------------------------------------------------ operações

def _conferir(x: int, y: int, tamanho: tuple[int, int]) -> tuple[int, int]:
    largura, altura = tamanho
    if not (0 <= x < largura and 0 <= y < altura):
        raise MesaError(
            f"A posição ({x}, {y}) está fora da tela ({largura}x{altura}). Nada foi movido."
        )
    return int(x), int(y)


def _passos(origem: tuple[int, int], destino: tuple[int, int], duracao: float) -> list[tuple[int, int]]:
    distancia = max(abs(destino[0] - origem[0]), abs(destino[1] - origem[1]))
    quantidade = max(1, min(int(duracao / PAUSA_PADRAO) + 1, MAX_PASSOS, distancia or 1))
    return [
        (
            round(origem[0] + (destino[0] - origem[0]) * i / quantidade),
            round(origem[1] + (destino[1] - origem[1]) * i / quantidade),
        )
        for i in range(1, quantidade + 1)
    ]


def status(backend: Backend | None = None) -> dict[str, Any]:
    """Onde está o cursor, o tamanho da tela e as janelas abertas. Não mexe em nada."""
    if backend is None:
        try:
            backend = _backend_padrao()
        except MesaError as exc:
            return {"suportado": False, "motivo": str(exc), "x": 0, "y": 0, "largura": 0, "altura": 0, "janelas": []}
    largura, altura = backend.tamanho()
    x, y = backend.posicao()
    return {
        "suportado": True,
        "x": x,
        "y": y,
        "largura": largura,
        "altura": altura,
        "janelas": backend.janelas()[:30],
    }


def mover(
    x: int,
    y: int,
    *,
    duracao: float = 0.25,
    backend: Backend | None = None,
    failsafe: bool = True,
) -> dict[str, Any]:
    """Leva o cursor até (x, y) em passos curtos. Para se o dono mexer o mouse."""
    backend = backend or _backend_padrao()
    largura, altura = backend.tamanho()
    destino = _conferir(int(x), int(y), (largura, altura))
    origem = backend.posicao()
    caminho = _passos(origem, destino, max(0.0, float(duracao)))
    ultimo = origem
    for passo in caminho:
        if failsafe and backend.posicao() != ultimo:
            return {
                "acao": "mover",
                "interrompido": True,
                "motivo": "Você mexeu o mouse; parei para não clicar em outra coisa.",
                "de": list(origem),
                "parou_em": list(backend.posicao()),
                "alvo": list(destino),
            }
        backend.mover(*passo)
        ultimo = passo
        backend.dormir(PAUSA_PADRAO)
    return {"acao": "mover", "interrompido": False, "de": list(origem), "para": list(destino)}


def clicar(
    x: int | None = None,
    y: int | None = None,
    *,
    botao: str = "esquerdo",
    vezes: int = 1,
    backend: Backend | None = None,
    failsafe: bool = True,
) -> dict[str, Any]:
    """Clica onde estiver (sem coordenada) ou move antes e clica."""
    backend = backend or _backend_padrao()
    if botao not in {"esquerdo", "direito", "meio"}:
        raise MesaError("Botão inválido: use esquerdo, direito ou meio.")
    if not 1 <= int(vezes) <= 3:
        raise MesaError("Cliques por vez: entre 1 e 3.")
    movido = None
    if x is not None and y is not None:
        movido = mover(x, y, backend=backend, failsafe=failsafe)
        if movido.get("interrompido"):
            return {**movido, "acao": "clicar", "clicou": False}
    antes = backend.posicao()
    backend.clicar(botao, int(vezes))
    return {
        "acao": "clicar",
        "clicou": True,
        "botao": botao,
        "vezes": int(vezes),
        "em": list(antes),
        "movido": movido is not None,
    }


def digitar(texto: str, *, backend: Backend | None = None) -> dict[str, Any]:
    """Digita no campo que estiver em foco. Acentos vão por `KEYEVENTF_UNICODE`."""
    backend = backend or _backend_padrao()
    limpo = (texto or "").strip()
    if not limpo:
        raise MesaError("Nada para digitar.")
    if len(limpo) > 2_000:
        raise MesaError("Texto grande demais para digitar (limite de 2.000 caracteres).")
    backend.digitar(limpo)
    return {"acao": "digitar", "caracteres": len(limpo), "amostra": limpo[:60]}


def teclar(nome: str, *, backend: Backend | None = None) -> dict[str, Any]:
    """Aperta uma tecla ou atalho (`enter`, `tab`, `ctrl+c`, `alt+f4`…)."""
    backend = backend or _backend_padrao()
    chave = (nome or "").strip().lower()
    if chave not in TECLAS:
        raise MesaError(f"Tecla desconhecida: {nome}. Aceito: {', '.join(sorted(TECLAS))}.")
    backend.teclar(chave)
    return {"acao": "teclar", "tecla": chave}


def focar(trecho: str, *, backend: Backend | None = None) -> dict[str, Any]:
    """Traz para a frente a primeira janela cujo título contenha o trecho."""
    backend = backend or _backend_padrao()
    titulo = backend.focar(trecho)
    return {"acao": "focar", "janela": titulo}
