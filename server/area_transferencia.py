"""Ler a área de transferência do Windows — sem dependência nova.

Por que isto existe (0.91.21): duas versões seguidas foram perdidas em cima de
**como a chave chega ao `.env`**, não de como ela é usada.

- 0.91.7: a chave gravada era `\\x16abc\\x16` — o `\\x16` é o Ctrl+V, que no
  console do Windows 10 não cola, escreve o caractere.
- Antes disso: seleção manual cortando caractere, chave truncada, chave colada
  duas vezes.

Digitar 73 caracteres num console de 2016 é o problema. Copiar no navegador e
deixar o JARVIS ler da área de transferência elimina a digitação inteira: o que
entra no `.env` é exatamente o que o site colocou lá.

**O que este módulo não faz**: ler tela, ler navegador, procurar segredo em
lugar nenhum. Ele lê **um** item — o que a pessoa acabou de copiar e pediu para
usar — e só quando um comando explícito pede. Não existe leitura automática,
nem em segundo plano, nem por pedido de conversa.

Sem `pywin32`: `ctypes` é biblioteca padrão. Os tipos são declarados à mão
porque no Python 64 bits o retorno de `GetClipboardData` é um ponteiro, e o
padrão do ctypes (`int`, 32 bits) truncaria o handle — o programa então lê
memória inválida e o Windows derruba o processo.
"""
from __future__ import annotations

import sys
import time

CF_UNICODETEXT = 13
_MAXIMO = 20_000


class AreaTransferenciaError(RuntimeError):
    """Não deu para ler — com a razão em português, sem jargão de Win32."""


def disponivel() -> bool:
    return sys.platform == "win32"


def ler(*, tentativas: int = 10, espera: float = 0.05) -> str:
    """O texto da área de transferência. Vazio quando não há texto.

    Tenta algumas vezes: qualquer programa pode estar segurando a área de
    transferência por alguns milissegundos, e nesse instante `OpenClipboard`
    falha. Isso não é erro do usuário e não merece mensagem.
    """
    if not disponivel():
        raise AreaTransferenciaError(
            "a área de transferência só é lida no Windows. Neste sistema, use --chave."
        )

    import ctypes
    from ctypes import wintypes

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

    user32.OpenClipboard.argtypes = [wintypes.HWND]
    user32.OpenClipboard.restype = wintypes.BOOL
    user32.CloseClipboard.argtypes = []
    user32.CloseClipboard.restype = wintypes.BOOL
    user32.IsClipboardFormatAvailable.argtypes = [wintypes.UINT]
    user32.IsClipboardFormatAvailable.restype = wintypes.BOOL
    user32.GetClipboardData.argtypes = [wintypes.UINT]
    user32.GetClipboardData.restype = wintypes.HANDLE
    kernel32.GlobalLock.argtypes = [wintypes.HANDLE]
    kernel32.GlobalLock.restype = wintypes.LPVOID
    kernel32.GlobalUnlock.argtypes = [wintypes.HANDLE]
    kernel32.GlobalUnlock.restype = wintypes.BOOL

    aberto = False
    for _ in range(max(1, tentativas)):
        if user32.OpenClipboard(None):
            aberto = True
            break
        time.sleep(espera)
    if not aberto:
        raise AreaTransferenciaError(
            "outro programa está segurando a área de transferência agora. "
            "Feche a janela que copiou e tente de novo."
        )

    try:
        if not user32.IsClipboardFormatAvailable(CF_UNICODETEXT):
            return ""
        handle = user32.GetClipboardData(CF_UNICODETEXT)
        if not handle:
            return ""
        ponteiro = kernel32.GlobalLock(handle)
        if not ponteiro:
            raise AreaTransferenciaError("o Windows não deixou abrir o texto copiado.")
        try:
            texto = ctypes.wstring_at(ponteiro)
        finally:
            kernel32.GlobalUnlock(handle)
    finally:
        user32.CloseClipboard()

    return (texto or "")[:_MAXIMO]
