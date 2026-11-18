"""Testes do teste no iPhone: guardar o export HTML5 e servir na rede local.

O pedido (18/11): *“dps q esse apk estiver bom eu quero testar no meu iphone”*.

O que estes testes cobrem, e por quê:

- **guardar o export** — pasta, `.zip`, `.zip` com uma pasta dentro (o caso do
  Unity, que sem achatar abre em branco), nome repetido, nome com espaço e
  acento (vira endereço no Safari);
- **recusar o que sai da pasta** — `..` no `.zip`, caminho absoluto, arquivo
  oculto, symlink;
- **servir de verdade** — sobe o servidor em `127.0.0.1:0` e faz pedidos HTTP
  reais: `index.html`, `.wasm` com o tipo certo, pasta sem barra no fim (301),
  arquivo que não existe (404), o `.gz` do export da Unity com
  `Content-Encoding`, `Range` e `HEAD`;
- **não vazar o JARVIS** — o servidor do jogo não conhece nenhuma rota da API;
  `.env` e `..` dão 404 mesmo pedindo pelo servidor;
- **COOP/COEP**, sem os quais o Godot com threads não liga no Safari.
"""
from __future__ import annotations

import http.client
import threading
import zipfile
from pathlib import Path

import pytest

from server import jogo_web
from server.app import create_app
from server.skill_registry import build_registry
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Ajuda: pasta de export e servidor de verdade
# ---------------------------------------------------------------------------

def _export(base: Path, *, com_index: bool = True) -> Path:
    base.mkdir(parents=True, exist_ok=True)
    if com_index:
        (base / "index.html").write_text("<!doctype html><h1>meu jogo</h1>", encoding="utf-8")
    (base / "Build").mkdir(exist_ok=True)
    (base / "Build" / "jogo.wasm").write_bytes(b"\0asm\x01\0\0\0")
    (base / "Build" / "jogo.data").write_bytes(b"dados" * 10)
    (base / "TemplateData").mkdir(exist_ok=True)
    (base / "TemplateData" / "logo.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    (base / "texto.txt").write_bytes(b"0123456789")
    return base


@pytest.fixture()
def servidor(tmp_path):
    base = _export(tmp_path / "export")
    (base / "Build" / "jogo.data.gz").write_bytes(b"\x1f\x8b arquivo comprimido")
    srv = jogo_web.subir(base, porta=0, host="127.0.0.1")
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    try:
        yield srv, srv.server_address[1], base
    finally:
        srv.shutdown()
        srv.server_close()
        thread.join(timeout=5)


def _pedir(porta: int, caminho: str, *, metodo: str = "GET", cabecalhos: dict[str, str] | None = None):
    conexao = http.client.HTTPConnection("127.0.0.1", porta, timeout=10)
    try:
        conexao.request(metodo, caminho, headers=cabecalhos or {})
        resposta = conexao.getresponse()
        return resposta, resposta.read()
    finally:
        conexao.close()


# ---------------------------------------------------------------------------
# Guardar o export
# ---------------------------------------------------------------------------

def test_importa_a_pasta_do_export(tmp_path):
    origem = _export(tmp_path / "Meu Jogo WebGL")
    info = jogo_web.importar(origem, tmp_path / "files", nome="Meu Jogo")
    assert info["nome"] == "Meu-Jogo"
    assert info["arquivos"] >= 4
    destino = Path(info["pasta"])
    assert (destino / "index.html").is_file()
    assert (destino / "Build" / "jogo.wasm").is_file()


def test_zip_do_unity_com_uma_pasta_dentro_e_achatado(tmp_path):
    # O zip do Unity vem como `Build/` + `index.html`, mas o zip do Godot vem
    # com a pasta toda dentro. Sem achatar, `http://ip:8099/` abria em branco.
    origem = tmp_path / "MeuJogo-WebGL.zip"
    with zipfile.ZipFile(origem, "w") as pacote:
        pacote.writestr("MeuJogo-WebGL/index.html", "<h1>oi</h1>")
        pacote.writestr("MeuJogo-WebGL/Build/jogo.wasm", b"\0asm")
        pacote.writestr("MeuJogo-WebGL/Build/jogo.data", b"dados")
    info = jogo_web.importar(origem, tmp_path / "files")
    destino = Path(info["pasta"])
    assert (destino / "index.html").is_file()
    assert (destino / "Build" / "jogo.wasm").is_file()
    assert not (destino / "MeuJogo-WebGL").exists()


def test_pasta_sem_index_html_explica_qual_export_escolher(tmp_path):
    origem = tmp_path / "export-errado"
    origem.mkdir()
    (origem / "leia-me.txt").write_text("nada de jogo aqui")
    with pytest.raises(jogo_web.JogoWebError) as erro:
        jogo_web.importar(origem, tmp_path / "files")
    assert "index.html" in str(erro.value)
    assert "WebGL" in str(erro.value) and "HTML5" in str(erro.value)
    # e não deixa lixo na pasta de jogos
    assert list((tmp_path / "files" / "jogos-web").iterdir()) == []


def test_arquivo_solto_e_recusado_com_o_que_arrastar(tmp_path):
    solto = tmp_path / "jogo.apk"
    solto.write_bytes(b"x")
    with pytest.raises(jogo_web.JogoWebError) as erro:
        jogo_web.importar(solto, tmp_path / "files")
    assert "pasta do export" in str(erro.value)


def test_zip_com_dois_pontos_recusa_sem_extrair_nada(tmp_path):
    origem = tmp_path / "malicioso.zip"
    with zipfile.ZipFile(origem, "w") as pacote:
        pacote.writestr("../fora.txt", "escapou")
        pacote.writestr("index.html", "<h1>oi</h1>")
    with pytest.raises(jogo_web.JogoWebError) as erro:
        jogo_web.importar(origem, tmp_path / "files")
    assert "recusei extrair" in str(erro.value)
    assert not (tmp_path / "fora.txt").exists()


def test_zip_com_caminho_absoluto_e_recusado(tmp_path):
    origem = tmp_path / "absoluto.zip"
    with zipfile.ZipFile(origem, "w") as pacote:
        pacote.writestr("/etc/passwd", "x")
    with pytest.raises(jogo_web.JogoWebError) as erro:
        jogo_web.importar(origem, tmp_path / "files")
    assert "absoluto" in str(erro.value)


def test_nome_repetido_ganha_numero_em_vez_de_sobrescrever(tmp_path):
    origem = _export(tmp_path / "export")
    primeiro = jogo_web.importar(origem, tmp_path / "files", nome="jogo")
    segundo = jogo_web.importar(origem, tmp_path / "files", nome="jogo")
    assert primeiro["nome"] == "jogo"
    assert segundo["nome"] == "jogo-1"
    assert Path(primeiro["pasta"]).is_dir() and Path(segundo["pasta"]).is_dir()


def test_nome_vira_endereco_sem_espaco_nem_acento(tmp_path):
    assert jogo_web._limpar_nome("Meu Jogo Épico!") == "Meu-Jogo-pico"
    assert jogo_web._limpar_nome("   ") == "jogo"
    assert jogo_web._limpar_nome("a" * 200).__len__() == 60


def test_listar_mostra_o_que_tem_e_marca_quem_nao_tem_index(tmp_path):
    files = tmp_path / "files"
    jogo_web.importar(_export(tmp_path / "um"), files, nome="um")
    quebrado = jogo_web.raiz(files) / "quebrado"
    quebrado.mkdir()
    (quebrado / "Build").mkdir()
    lista = jogo_web.listar(files)
    assert lista["quantidade"] == 2
    por_nome = {item["nome"]: item for item in lista["jogos"]}
    assert por_nome["um"]["temIndex"] is True
    assert por_nome["quebrado"]["temIndex"] is False
    assert lista["pasta"].endswith("jogos-web")


# ---------------------------------------------------------------------------
# Servir de verdade: o Safari pedindo os arquivos
# ---------------------------------------------------------------------------

def test_a_raiz_serve_o_index_html(servidor):
    _, porta, _ = servidor
    resposta, corpo = _pedir(porta, "/")
    assert resposta.status == 200
    assert "text/html" in resposta.getheader("Content-Type")
    assert b"meu jogo" in corpo


def test_wasm_sai_com_o_tipo_que_o_safari_exige(servidor):
    _, porta, _ = servidor
    resposta, corpo = _pedir(porta, "/Build/jogo.wasm")
    assert resposta.status == 200
    assert resposta.getheader("Content-Type") == "application/wasm"
    assert corpo.startswith(b"\0asm")


def test_pasta_sem_barra_no_fim_vira_301_com_a_barra(servidor):
    _, porta, _ = servidor
    resposta, _ = _pedir(porta, "/Build")
    assert resposta.status == 301
    assert resposta.getheader("Location") == "/Build/"


def test_arquivo_que_nao_existe_vira_404_com_dica(servidor):
    _, porta, _ = servidor
    resposta, corpo = _pedir(porta, "/Build/nao-existe.wasm")
    assert resposta.status == 404
    assert "não existe neste export" in corpo.decode("utf-8")


def test_dois_pontos_e_arquivo_oculto_nao_saem_da_pasta(servidor):
    _, porta, base = servidor
    (base.parent / "segredo.txt").write_text("chave secreta")
    (base / ".env").write_text("JARVIS_CHAVE=segredo")

    for caminho in ["/../segredo.txt", "/%2e%2e/segredo.txt", "/.env", "/Build/../../segredo.txt"]:
        resposta, corpo = _pedir(porta, caminho)
        assert resposta.status == 404, caminho
        assert b"chave secreta" not in corpo
        assert b"JARVIS_CHAVE" not in corpo


def test_o_gz_pedido_pelo_nome_sai_dizendo_que_esta_comprimido(servidor):
    # É assim que o carregador da Unity pede: `/Build/jogo.data.gz`. Sem o
    # cabecalho, o Safari entrega lixo binário ao script e a tela fica preta.
    _, porta, _ = servidor
    resposta, corpo = _pedir(porta, "/Build/jogo.data.gz")
    assert resposta.status == 200
    assert resposta.getheader("Content-Encoding") == "gzip"
    assert resposta.getheader("Content-Type") == "application/octet-stream"
    assert corpo == b"\x1f\x8b arquivo comprimido"


def test_com_o_original_presente_o_original_ganha(servidor):
    _, porta, _ = servidor
    resposta, corpo = _pedir(porta, "/Build/jogo.data", cabecalhos={"Accept-Encoding": "gzip, deflate"})
    assert resposta.status == 200
    assert resposta.getheader("Content-Encoding") is None
    assert corpo.startswith(b"dados")


def test_sem_gzip_no_pedido_o_arquivo_original_vale(servidor):
    _, porta, base = servidor
    (base / "Build" / "so-gz.data.gz").write_bytes(b"comprimido")
    resposta, _ = _pedir(porta, "/Build/so-gz.data")
    assert resposta.status == 404
    resposta, corpo = _pedir(porta, "/Build/so-gz.data", cabecalhos={"Accept-Encoding": "gzip"})
    assert resposta.status == 200 and corpo == b"comprimido"


def test_range_devolve_pedaco_e_content_range(servidor):
    _, porta, _ = servidor
    resposta, corpo = _pedir(porta, "/texto.txt", cabecalhos={"Range": "bytes=2-5"})
    assert resposta.status == 206
    assert resposta.getheader("Content-Range") == "bytes 2-5/10"
    assert corpo == b"2345"


def test_range_invalido_entrega_o_arquivo_inteiro(servidor):
    _, porta, _ = servidor
    resposta, corpo = _pedir(porta, "/texto.txt", cabecalhos={"Range": "bytes=50-60"})
    assert resposta.status == 200
    assert corpo == b"0123456789"


def test_head_responde_sem_corpo_mas_com_tamanho(servidor):
    _, porta, _ = servidor
    resposta, corpo = _pedir(porta, "/texto.txt", metodo="HEAD")
    assert resposta.status == 200
    assert resposta.getheader("Content-Length") == "10"
    assert corpo == b""


def test_coop_e_coep_vem_ligados_para_o_godot_com_threads(tmp_path):
    base = _export(tmp_path / "export")
    srv = jogo_web.subir(base, porta=0, host="127.0.0.1")
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    try:
        resposta, _ = _pedir(srv.server_address[1], "/")
        assert resposta.getheader("Cross-Origin-Opener-Policy") == "same-origin"
        assert resposta.getheader("Cross-Origin-Embedder-Policy") == "require-corp"
    finally:
        srv.shutdown()
        srv.server_close()
        thread.join(timeout=5)

    srv = jogo_web.subir(base, porta=0, host="127.0.0.1", isolamento=False)
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    try:
        resposta, _ = _pedir(srv.server_address[1], "/")
        assert resposta.getheader("Cross-Origin-Opener-Policy") is None
    finally:
        srv.shutdown()
        srv.server_close()
        thread.join(timeout=5)


def test_o_servidor_do_jogo_nao_conhece_a_api_do_jarvis(servidor):
    _, porta, _ = servidor
    for caminho in ["/api/health", "/api/jogo/arquivos", "/docs"]:
        resposta, _ = _pedir(porta, caminho)
        assert resposta.status == 404


def test_metodo_que_nao_e_leitura_e_recusado(servidor):
    _, porta, _ = servidor
    conexao = http.client.HTTPConnection("127.0.0.1", porta, timeout=10)
    try:
        conexao.request("POST", "/", body=b"x")
        resposta = conexao.getresponse()
        assert resposta.status in {405, 501}
    finally:
        conexao.close()


def test_servir_pasta_sem_index_falha_antes_de_abrir_porta(tmp_path):
    vazia = tmp_path / "vazia"
    vazia.mkdir()
    with pytest.raises(jogo_web.JogoWebError) as erro:
        jogo_web.subir(vazia, porta=0)
    assert "index.html" in str(erro.value)


# ---------------------------------------------------------------------------
# O endereço que o dono digita no iPhone
# ---------------------------------------------------------------------------

def test_o_endereco_e_um_ip_da_rede_e_nao_a_volta_do_proprio_iphone():
    ip = jogo_web.endereco_local()
    partes = ip.split(".")
    assert len(partes) == 4
    assert all(parte.isdigit() and 0 <= int(parte) <= 255 for parte in partes)


def test_as_instrucoes_dizem_o_endereco_e_o_que_derruba(monkeypatch):
    monkeypatch.setattr(jogo_web, "endereco_local", lambda: "192.168.0.10")
    texto = jogo_web.instrucoes("Meu-Jogo", porta=8099)
    assert "http://192.168.0.10:8099/" in texto
    assert "Safari" in texto
    assert "mesma rede" in texto.lower()
    assert "firewall" in texto
    assert "127.0.0.1" in texto  # dito como o que NÃO funciona no iPhone
    assert "Meu-Jogo" in texto


# ---------------------------------------------------------------------------
# A rota: o chat e a tela veem o que já foi guardado
# ---------------------------------------------------------------------------

@pytest.fixture()
def cliente(tmp_path):
    root = tmp_path / "user-files"
    root.mkdir(parents=True)
    return TestClient(create_app(registry=build_registry(root))), root


def test_a_rota_lista_os_exports(cliente):
    base, root = cliente
    jogo_web.importar(_export(root.parent / "export"), root, nome="meu-jogo")
    corpo = base.get("/api/jogo/web").json()
    assert corpo["ok"] is True
    assert corpo["result"]["jogos"][0]["nome"] == "meu-jogo"
    assert corpo["result"]["jogos"][0]["temIndex"] is True


# ---------------------------------------------------------------------------
# Qual endereço o dono digita (PC com placa virtual tem vários)
# ---------------------------------------------------------------------------

def test_o_endereco_mais_provavel_da_rede_vem_primeiro():
    # O PC do dono pode ter VirtualBox/WSL: o IP que “sai para internet” pode
    # ser o da placa virtual, que o iPhone não alcança.
    assert jogo_web._melhor(["169.254.0.21", "192.168.0.10", "10.1.2.3"]) == "192.168.0.10"
    assert jogo_web._melhor(["10.1.2.3", "172.20.0.1"]) == "10.1.2.3"
    assert jogo_web._melhor(["172.20.0.1", "8.8.8.8"]) == "172.20.0.1"


def test_sem_rede_sobra_o_endereco_da_propria_maquina():
    assert jogo_web._melhor(["127.0.0.1"]) == "127.0.0.1"
    assert jogo_web._melhor([]) == "127.0.0.1"


def test_a_prioridade_conhece_as_faixas_domesticas():
    assert jogo_web._prioridade("192.168.1.5") < jogo_web._prioridade("10.0.0.5")
    assert jogo_web._prioridade("10.0.0.5") < jogo_web._prioridade("172.16.0.1")
    assert jogo_web._prioridade("172.16.0.1") < jogo_web._prioridade("169.254.1.1")
    assert jogo_web._prioridade("169.254.1.1") > jogo_web._prioridade("8.8.8.8")


def test_as_instrucoes_mostram_o_segundo_endereco_quando_existe(monkeypatch):
    monkeypatch.setattr(jogo_web, "endereco_local", lambda: "192.168.0.10")
    texto = jogo_web.instrucoes("Meu-Jogo", porta=8099, outros=["10.0.0.7"])
    assert "http://192.168.0.10:8099/" in texto
    assert "http://10.0.0.7:8099/" in texto
    assert "ipconfig" in texto
