"""Falar com o Chrome pelo protocolo dele (CDP) — sem depender da árvore de acessibilidade.

Por que existe (0.91.27). Doze versões tentaram ler a página do OpenRouter pela
árvore de acessibilidade do Windows. O diagnóstico de 16/11 mostrou que a
mesma janela passava de **85 elementos para 3** em segundos, e que nem o sinal
de leitor de tela nem a vista crua seguravam a página publicada. Ler a tela,
nessa máquina, é loteria.

O Chrome tem uma porta de controle **própria**, a mesma que o F12 usa: o
DevTools Protocol. Com ela o programa não lê pixels nem árvore de
acessibilidade: ele pergunta à página quais são os elementos e recebe a
resposta em texto. É determinístico.

Duas condições, e as duas são verdades do Chrome (não escolhas nossas):

- o Chrome precisa ser **iniciado** com `--remote-debugging-port=9222` — a
  porta não abre num Chrome que já estava rodando. É o `chrome-cdp.bat` que
  faz isso;
- o protocolo é **WebSocket**. Este arquivo tem o mínimo dele: aperto de mão,
  envio e leitura de quadros de texto. Nada de biblioteca externa — o JARVIS
  é instalado por zip, sem internet.

O que este módulo **não** faz: não interpreta a página, não clica em nada por
conta própria e não conhece OpenRouter. Ele só transporta comandos.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import socket
import struct
import time
import urllib.request
from typing import Any

PORTA_PADRAO = 9222


class CdpError(RuntimeError):
    """Não deu para falar com o Chrome — com o motivo em português."""


# ---------------------------------------------------------------------------
# Descoberta: quais páginas o Chrome tem abertas
# ---------------------------------------------------------------------------

def porta_aberta(porta: int = PORTA_PADRAO, segundos: float = 0.5) -> bool:
    """A porta de depuração está aceitando conexão?"""
    try:
        with socket.create_connection(("127.0.0.1", int(porta)), timeout=segundos):
            return True
    except OSError:
        return False


def alvos(porta: int = PORTA_PADRAO, segundos: float = 3.0) -> list[dict[str, Any]]:
    """As páginas abertas, como o próprio Chrome as descreve.

    Devolve `[]` quando a porta não responde — quem chama decide o que dizer.
    """
    endereco = f"http://127.0.0.1:{int(porta)}/json/list"
    try:
        with urllib.request.urlopen(endereco, timeout=segundos) as resposta:  # noqa: S310 - localhost
            dados = json.loads(resposta.read().decode("utf-8", "replace"))
    except Exception:  # noqa: BLE001 - porta fechada, Chrome sem o modo, etc.
        return []
    if not isinstance(dados, list):
        return []
    return [item for item in dados if isinstance(item, dict) and item.get("type") == "page"]


def achar_alvo(porta: int = PORTA_PADRAO, trecho: str = "", segundos: float = 0.0) -> dict[str, Any] | None:
    """A primeira página cujo endereço contém `trecho` (ou a primeira, sem trecho)."""
    fim = time.time() + max(0.0, segundos)
    while True:
        paginas = alvos(porta)
        for pagina in paginas:
            if not trecho or trecho.lower() in str(pagina.get("url") or "").lower():
                return pagina
        if time.time() >= fim:
            return None
        time.sleep(0.5)


# ---------------------------------------------------------------------------
# WebSocket mínimo — o transporte do CDP
# ---------------------------------------------------------------------------

class WebSocket:
    """O mínimo de WebSocket para o CDP: texto para fora, texto para dentro."""

    def __init__(self, endereco: str, segundos: float = 10.0) -> None:
        from urllib.parse import urlparse

        partes = urlparse(endereco)
        if partes.scheme != "ws" or not partes.hostname:
            raise CdpError(f"endereço de WebSocket inválido: {endereco!r}")
        self.host = partes.hostname
        self.porta = int(partes.port or 80)
        self.caminho = partes.path or "/"
        if partes.query:
            self.caminho += "?" + partes.query
        try:
            self.conexao = socket.create_connection((self.host, self.porta), timeout=segundos)
        except OSError as exc:
            raise CdpError(f"não consegui abrir a conexão com o Chrome ({exc}).") from exc
        self.conexao.settimeout(segundos)
        self._aperto_de_mao()
        self._resto = b""

    # ------------------------------------------------------------ aperto de mão
    def _aperto_de_mao(self) -> None:
        chave = base64.b64encode(os.urandom(16)).decode()
        pedido = (
            f"GET {self.caminho} HTTP/1.1\r\n"
            f"Host: {self.host}:{self.porta}\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {chave}\r\n"
            "Sec-WebSocket-Version: 13\r\n"
            "\r\n"
        )
        self.conexao.sendall(pedido.encode())
        resposta = b""
        while b"\r\n\r\n" not in resposta:
            pedaco = self.conexao.recv(4096)
            if not pedaco:
                raise CdpError("o Chrome fechou a conexão durante o aperto de mão.")
            resposta += pedaco
            if len(resposta) > 65536:
                raise CdpError("resposta grande demais no aperto de mão do WebSocket.")
        cabecalho, _, resto = resposta.partition(b"\r\n\r\n")
        if b" 101 " not in cabecalho.split(b"\r\n")[0]:
            raise CdpError(
                "o Chrome recusou a conexão de controle: "
                + cabecalho.split(b"\r\n")[0].decode("latin-1", "replace")
            )
        esperado = base64.b64encode(
            hashlib.sha1((chave + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11").encode()).digest()
        )
        if esperado.lower() not in cabecalho.lower():
            raise CdpError("o Chrome respondeu ao WebSocket sem a chave certa (proxy no meio?).")
        self._resto = resto

    # ------------------------------------------------------------------ envio
    def enviar(self, texto: str) -> None:
        """Um quadro de texto, mascarado como o protocolo exige do cliente."""
        carga = texto.encode("utf-8")
        cabecalho = bytearray([0x81])  # FIN + texto
        tamanho = len(carga)
        if tamanho < 126:
            cabecalho.append(0x80 | tamanho)
        elif tamanho < (1 << 16):
            cabecalho.append(0x80 | 126)
            cabecalho += struct.pack(">H", tamanho)
        else:
            cabecalho.append(0x80 | 127)
            cabecalho += struct.pack(">Q", tamanho)
        mascara = os.urandom(4)
        cabecalho += mascara
        mascarada = bytes(b ^ mascara[i % 4] for i, b in enumerate(carga))
        self.conexao.sendall(bytes(cabecalho) + mascarada)

    # ------------------------------------------------------------------ leitura
    def _ler_exato(self, quantos: int) -> bytes:
        dados = self._resto
        self._resto = b""
        while len(dados) < quantos:
            pedaco = self.conexao.recv(max(4096, quantos - len(dados)))
            if not pedaco:
                raise CdpError("o Chrome fechou a conexão de controle.")
            dados += pedaco
        sobra = dados[quantos:]
        self._resto = sobra
        return dados[:quantos]

    def receber(self) -> str | None:
        """O próximo quadro de texto; `None` quando o Chrome mandou fechar."""
        while True:
            primeiro, segundo = self._ler_exato(2)
            opcode = primeiro & 0x0F
            mascarado = bool(segundo & 0x80)
            tamanho = segundo & 0x7F
            if tamanho == 126:
                tamanho = struct.unpack(">H", self._ler_exato(2))[0]
            elif tamanho == 127:
                tamanho = struct.unpack(">Q", self._ler_exato(8))[0]
            mascara = self._ler_exato(4) if mascarado else b""
            carga = self._ler_exato(tamanho) if tamanho else b""
            if mascarado:
                carga = bytes(b ^ mascara[i % 4] for i, b in enumerate(carga))
            if opcode == 0x8:  # fechar
                return None
            if opcode == 0x9:  # ping → pong
                self.conexao.sendall(bytes([0x8A, 0x80]) + os.urandom(4))
                continue
            if opcode in (0x1, 0x0, 0x2):
                return carga.decode("utf-8", "replace")

    def fechar(self) -> None:
        try:
            self.conexao.sendall(bytes([0x88, 0x80]) + os.urandom(4))
        except OSError:
            pass
        try:
            self.conexao.close()
        except OSError:
            pass


# ---------------------------------------------------------------------------
# Uma sessão de comandos
# ---------------------------------------------------------------------------

class Sessao:
    """Fala CDP com **uma** página. `chamar` devolve o `result` do comando."""

    def __init__(self, pagina: dict[str, Any], segundos: float = 15.0) -> None:
        endereco = str(pagina.get("webSocketDebuggerUrl") or "")
        if not endereco:
            raise CdpError("a página não expôs endereço de controle (webSocketDebuggerUrl).")
        self.ws = WebSocket(endereco, segundos=segundos)
        self._id = 0
        self.ultimo_erro = ""

    def chamar(self, metodo: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        self._id += 1
        pedido = {"id": self._id, "method": metodo, "params": params or {}}
        self.ws.enviar(json.dumps(pedido))
        while True:
            bruto = self.ws.receber()
            if bruto is None:
                raise CdpError("o Chrome fechou a conexão no meio do comando.")
            try:
                mensagem = json.loads(bruto)
            except ValueError:
                continue
            if mensagem.get("id") != self._id:
                continue  # evento da página, não é resposta
            if "error" in mensagem:
                self.ultimo_erro = json.dumps(mensagem["error"], ensure_ascii=False)[:300]
                raise CdpError(f"o Chrome recusou “{metodo}”: {self.ultimo_erro}")
            resultado = mensagem.get("result") or {}
            if resultado.get("exceptionDetails"):
                detalhe = resultado["exceptionDetails"]
                texto = (detalhe.get("exception") or {}).get("description") or detalhe.get("text") or ""
                raise CdpError(f"o JavaScript da página falhou: {str(texto)[:300]}")
            return resultado

    def javascript(self, expressao: str, segundos_limite: float = 10.0) -> Any:
        """Avalia uma expressão e devolve o valor (por valor, não por referência)."""
        resultado = self.chamar(
            "Runtime.evaluate",
            {
                "expression": expressao,
                "returnByValue": True,
                "awaitPromise": False,
                "userGesture": True,
                "timeout": int(segundos_limite * 1000),
            },
        )
        return (resultado.get("result") or {}).get("value")

    def fechar(self) -> None:
        self.ws.fechar()
