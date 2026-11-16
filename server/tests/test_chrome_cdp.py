"""O protocolo do Chrome, testado sem Chrome (0.91.27).

Duas metades, e nenhuma delas precisa de navegador:

1. **o transporte** — aperto de mão WebSocket, quadros mascarados, resposta
   casada por `id`. Aqui há um servidor falso numa thread: ele faz o papel do
   Chrome do outro lado do fio. Se o JARVIS mandar um quadro malformado, o
   servidor falso não entende e o teste falha;
2. **o JavaScript injetado** — o texto que vai para a página roda no `node`
   em cima de uma página falsa (OpenRouter **mais** a moldura da janela com os
   títulos repetidos e o balão “Restaurar páginas?” que apareceram no print de
   16/11). É a parte que não dá para descobrir no PC do dono sem gastar uma
   rodada: um erro de seletor ou de sintaxe aparece aqui.
"""
from __future__ import annotations

import base64
import hashlib
import importlib.util
import json
import shutil
import socket
import struct
import subprocess
import threading
from pathlib import Path

import pytest

from server import chrome_cdp

RAIZ = Path(__file__).resolve().parents[2]
HARNESS = Path(__file__).resolve().parent / "cdp_pagina_falsa.js"


def _script():
    spec = importlib.util.spec_from_file_location("chave_no_navegador_cdp", RAIZ / "chave-no-navegador.py")
    modulo = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(modulo)
    return modulo


# ---------------------------------------------------------------------------
# Um Chrome falso atrás de um socket
# ---------------------------------------------------------------------------

def _desmascarar(cabecalho: bytes, carga: bytes) -> bytes:
    return bytes(b ^ cabecalho[i % 4] for i, b in enumerate(carga))


def _ler_quadro(conexao: socket.socket) -> tuple[int, str]:
    """Lê um quadro do cliente (sempre mascarado) e devolve (opcode, texto)."""
    primeiro, segundo = conexao.recv(2)
    tamanho = segundo & 0x7F
    if tamanho == 126:
        tamanho = struct.unpack(">H", conexao.recv(2))[0]
    elif tamanho == 127:
        tamanho = struct.unpack(">Q", conexao.recv(8))[0]
    mascara = conexao.recv(4)
    carga = b""
    while len(carga) < tamanho:
        carga += conexao.recv(tamanho - len(carga))
    return primeiro & 0x0F, _desmascarar(mascara, carga).decode("utf-8")


def _mandar_quadro(conexao: socket.socket, texto: str) -> None:
    """Resposta do servidor: sem máscara, é o que o protocolo exige dele."""
    carga = texto.encode("utf-8")
    cabecalho = bytearray([0x81])
    if len(carga) < 126:
        cabecalho.append(len(carga))
    else:
        cabecalho.append(126)
        cabecalho += struct.pack(">H", len(carga))
    conexao.sendall(bytes(cabecalho) + carga)


class ChromeFalso:
    """Um processo escutando: aceita o aperto de mão e responde aos comandos."""

    def __init__(self, respostas: dict[str, dict]) -> None:
        self.respostas = respostas
        self.recebidos: list[dict] = []
        self.erro = ""
        self.porta = 0
        self._servidor = socket.socket()
        self._servidor.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._servidor.bind(("127.0.0.1", 0))
        self._servidor.listen(1)
        self.porta = self._servidor.getsockname()[1]
        self._parar = threading.Event()
        self._fio = threading.Thread(target=self._atender, daemon=True)
        self._fio.start()

    def endereco(self) -> str:
        return f"ws://127.0.0.1:{self.porta}/devtools/page/1"

    def _atender(self) -> None:
        try:
            conexao, _ = self._servidor.accept()
        except OSError:
            return
        with conexao:
            pedido = b""
            while b"\r\n\r\n" not in pedido:
                pedaco = conexao.recv(4096)
                if not pedaco:
                    return
                pedido += pedaco
            chave = ""
            for linha in pedido.decode("latin-1").split("\r\n"):
                if linha.lower().startswith("sec-websocket-key:"):
                    chave = linha.split(":", 1)[1].strip()
            aceite = base64.b64encode(
                hashlib.sha1((chave + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11").encode()).digest()
            ).decode()
            conexao.sendall(
                (
                    "HTTP/1.1 101 Switching Protocols\r\n"
                    "Upgrade: websocket\r\nConnection: Upgrade\r\n"
                    f"Sec-WebSocket-Accept: {aceite}\r\n\r\n"
                ).encode()
            )
            while not self._parar.is_set():
                try:
                    opcode, bruto = _ler_quadro(conexao)
                except OSError:
                    return
                if opcode == 0x8:  # o cliente fechou: nada a responder
                    return
                if opcode == 0x9:  # ping
                    continue
                mensagem = json.loads(bruto)
                self.recebidos.append(mensagem)
                resposta = self.respostas.get(mensagem.get("method") or "", {})
                _mandar_quadro(conexao, json.dumps({"id": mensagem.get("id"), **resposta}))

    def fechar(self) -> None:
        self._parar.set()
        try:
            self._servidor.close()
        except OSError:
            pass


# ---------------------------------------------------------------------------
# Transporte
# ---------------------------------------------------------------------------

def test_a_porta_fechada_nao_derruba_o_programa():
    """Sem Chrome de controle, `porta_aberta` diz não — não levanta exceção."""
    with socket.socket() as sonda:
        sonda.bind(("127.0.0.1", 0))
        porta = sonda.getsockname()[1]
    assert chrome_cdp.porta_aberta(porta) is False
    assert chrome_cdp.alvos(porta) == []
    assert chrome_cdp.achar_alvo(porta, "openrouter") is None


def test_o_comando_vai_e_a_resposta_volta_pelo_mesmo_id():
    falso = ChromeFalso({"Runtime.evaluate": {"result": {"result": {"value": "pong"}}}})
    try:
        sessao = chrome_cdp.Sessao({"webSocketDebuggerUrl": falso.endereco()})
        assert sessao.javascript("1+1") == "pong"
        sessao.fechar()
    finally:
        falso.fechar()
    assert falso.recebidos, "o servidor falso não recebeu nenhum comando"
    pedido = falso.recebidos[0]
    assert pedido["method"] == "Runtime.evaluate"
    assert pedido["params"]["expression"] == "1+1"
    assert pedido["params"]["returnByValue"] is True


def test_o_erro_do_chrome_chega_em_portugues_e_nao_trava():
    falso = ChromeFalso({"Runtime.evaluate": {"error": {"message": "Cannot read properties"}}})
    try:
        sessao = chrome_cdp.Sessao({"webSocketDebuggerUrl": falso.endereco()})
        with pytest.raises(chrome_cdp.CdpError) as erro:
            sessao.javascript("1+1")
        sessao.fechar()
    finally:
        falso.fechar()
    assert "Cannot read properties" in str(erro.value)


def test_a_excecao_do_javascript_da_pagina_e_apontada_como_tal():
    falso = ChromeFalso(
        {"Runtime.evaluate": {"result": {"exceptionDetails": {"text": "Uncaught TypeError: x"}}}}
    )
    try:
        sessao = chrome_cdp.Sessao({"webSocketDebuggerUrl": falso.endereco()})
        with pytest.raises(chrome_cdp.CdpError) as erro:
            sessao.javascript("x()")
        sessao.fechar()
    finally:
        falso.fechar()
    assert "JavaScript da página" in str(erro.value)


def test_endereco_de_controle_ausente_e_erro_com_explicacao():
    with pytest.raises(chrome_cdp.CdpError) as erro:
        chrome_cdp.Sessao({"url": "https://openrouter.ai/settings/keys"})
    assert "webSocketDebuggerUrl" in str(erro.value)


def test_a_lista_de_paginas_le_so_abas_de_pagina():
    """`/json/list` pode trazer iframes e service workers: só a página interessa."""
    import http.server
    import threading as _threading

    corpo = json.dumps(
        [
            {"type": "page", "url": "https://openrouter.ai/settings/keys", "webSocketDebuggerUrl": "ws://x/1"},
            {"type": "service_worker", "url": "chrome-extension://abc/worker.js", "webSocketDebuggerUrl": "ws://x/2"},
            {"type": "iframe", "url": "https://ads.example", "webSocketDebuggerUrl": "ws://x/3"},
        ]
    ).encode()

    class Mao(http.server.BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802 - nome exigido pela biblioteca
            if self.path != "/json/list":
                self.send_response(404)
                self.end_headers()
                return
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(corpo)))
            self.end_headers()
            self.wfile.write(corpo)

        def log_message(self, *_args):
            return

    servidor = http.server.HTTPServer(("127.0.0.1", 0), Mao)
    fio = _threading.Thread(target=servidor.serve_forever, daemon=True)
    fio.start()
    try:
        paginas = chrome_cdp.alvos(servidor.server_address[1])
        assert [p["type"] for p in paginas] == ["page"]
        achada = chrome_cdp.achar_alvo(servidor.server_address[1], "openrouter")
        assert achada and "openrouter" in achada["url"]
        assert chrome_cdp.achar_alvo(servidor.server_address[1], "github") is None
    finally:
        servidor.shutdown()
        servidor.server_close()


# ---------------------------------------------------------------------------
# O JavaScript injetado, rodando de verdade no node
# ---------------------------------------------------------------------------

def _node() -> str:
    caminho = shutil.which("node")
    if not caminho:
        pytest.skip("node não está instalado nesta máquina")
    return caminho


def _rodar_js(ordens: list[tuple], ambiente: dict[str, str] | None = None) -> list:
    """Monta a bancada, roda no node e devolve o que cada ordem respondeu."""
    import tempfile

    script = _script()
    linhas = []
    for ordem in ordens:
        argumentos = ", ".join(json.dumps(item) for item in ordem)
        linhas.append(f"console.log(JSON.stringify(window.__JARVIS({argumentos})));")
    fonte = "\n".join([HARNESS.read_text(), script._CDP_AJUDA, *linhas])
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8") as arquivo:
        arquivo.write(fonte)
        caminho = arquivo.name
    try:
        import os

        saida = subprocess.run(
            [_node(), caminho],
            capture_output=True,
            text=True,
            timeout=60,
            env={**os.environ, **(ambiente or {})},
        )
    finally:
        Path(caminho).unlink(missing_ok=True)
    assert saida.returncode == 0, saida.stderr[-1500:]
    return [json.loads(linha) for linha in saida.stdout.strip().splitlines() if linha.strip()]


def test_o_javascript_injetado_e_sintaxe_valida_e_le_a_pagina():
    """A ordem `pronta` responde com o endereço, o texto e se há painel."""
    estado = _rodar_js([("pronta",)])[0]
    assert estado["tem_painel"] is False
    # O texto do body inclui a moldura — de propósito: é o que a página falsa tem.
    assert "restaurar páginas?" in estado["texto"]  # o texto vem normalizado
    assert "api keys" in estado["texto"]


def test_o_clique_acha_o_botao_da_pagina_com_a_moldura_na_frente():
    """16/11: com títulos repetidos e o balão na leitura, o clique não abria nada.

    Aqui a moldura está na página falsa, e o clique tem de continuar indo no
    botão “New key” — quem escolhe pelo texto e não pela posição não se engana.
    """
    respostas = _rodar_js([("clicar", "New key"), ("pronta",)])
    assert respostas[0] is True, "o clique não achou o botão da página"
    assert respostas[1]["tem_painel"] is True, "o painel não abriu depois do clique"


def test_o_painel_nasce_com_uma_unica_caixa_de_texto_e_o_nome_entra_nela():
    respostas = _rodar_js(
        [
            ("clicar", "New key"),
            ("digitar", "nome", "jarvis-teste"),
            ("texto",),
        ]
    )
    assert respostas[1] is True, "não achei a caixa do nome no painel"
    assert "jarvis-teste" in respostas[2]


def test_a_lista_de_expiracao_abre_e_oferece_o_no_expiration():
    respostas = _rodar_js(
        [
            ("clicar", "New key"),
            ("clicar", "Select expiration"),
            ("opcoes",),
        ]
    )
    assert respostas[1] is True, "o campo de expiração não abriu"
    assert "No expiration" in respostas[2]


def test_a_chave_e_lida_do_texto_da_pagina_so_depois_de_criar():
    """A chave só aparece no texto depois do “Create” — e sai inteira, 73 letras."""
    antes = _rodar_js([("chave",)])[0]
    depois = _rodar_js(
        [
            ("clicar", "New key"),
            ("digitar", "nome", "jarvis-teste"),
            ("clicar", "Create"),
            ("chave",),
        ]
    )[-1]
    assert antes == ""
    assert depois.startswith("sk-or-v1-")
    assert len(depois) == 73


def test_a_chave_dentro_de_um_campo_tambem_e_encontrada():
    """O site pode mostrar a chave num `<input>` — `innerText` não a veria."""
    depois = _rodar_js(
        [
            ("clicar", "New key"),
            ("digitar", "nome", "jarvis-teste"),
            ("clicar", "Create"),
            ("chave",),
        ],
        ambiente={"CDP_CHAVE_NO_CAMPO": "1"},
    )[-1]
    assert depois.startswith("sk-or-v1-")
    assert len(depois) == 73


def test_um_texto_que_nao_existe_na_pagina_nao_clica_em_nada():
    assert _rodar_js([("clicar", "Botao Que Nao Existe")])[0] is False


def test_o_select_nativo_e_usado_quando_existe():
    """Se o campo for um `<select>` de verdade, nem precisa abrir a lista."""
    import tempfile

    script = _script()
    fonte = "\n".join(
        [
            HARNESS.read_text(),
            script._CDP_AJUDA,
            # Um <select> como o painel poderia usar, pendurado na página falsa.
            "document.body._filhos[0]._filhos[0]._filhos.push({"
            "tagName: 'SELECT', _attrs: new Map(), style: {},"
            "getAttribute: () => null, hasAttribute: () => false,"
            "getBoundingClientRect: () => ({width: 9, height: 9}),"
            "dispatchEvent: () => true,"
            "options: [{text: '1 day', value: '1'}, {text: 'No expiration', value: 'no'}]"
            "});",
            "console.log(JSON.stringify(window.__JARVIS('select', 'No expiration')));",
        ]
    )
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8") as arquivo:
        arquivo.write(fonte)
        caminho = arquivo.name
    try:
        saida = subprocess.run([_node(), caminho], capture_output=True, text=True, timeout=60)
    finally:
        Path(caminho).unlink(missing_ok=True)
    assert saida.returncode == 0, saida.stderr[-1200:]
    assert json.loads(saida.stdout.strip()) is True


def test_sem_select_nativo_a_ordem_diz_que_nao_achou():
    """Página sem `<select>`: `select` devolve False em vez de estourar."""
    assert _rodar_js([("select", "No expiration")])[0] is False
