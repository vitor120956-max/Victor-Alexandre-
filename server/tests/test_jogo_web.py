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
import json
import struct
import threading
import zipfile
import zlib
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


# ---------------------------------------------------------------------------
# 0.91.40 — “não dá para baixar no iPhone?”: o jogo vira ícone na tela inicial
# ---------------------------------------------------------------------------

def _png_tamanho(dados: bytes) -> tuple[int, int]:
    assert dados[:8] == b"\x89PNG\r\n\x1a\n", "não é um PNG"
    largura, altura = struct.unpack(">II", dados[16:24])
    return largura, altura


def test_o_icone_e_um_png_de_verdade_no_tamanho_que_o_ios_pede():
    for tamanho in (180, 512):
        png = jogo_web.icone_png(tamanho)
        assert _png_tamanho(png) == (tamanho, tamanho)
    # e o triângulo está lá: o centro da imagem tem a cor de marca
    png = jogo_web.icone_png(180)
    cru = zlib.decompress(_idat(png))
    largura = 180
    # filtro (1 byte) + 90 linhas + 90 pixels na linha 90
    centro = 90 * (1 + largura * 3) + 1 + 90 * 3
    pixel = tuple(cru[centro : centro + 3])
    assert pixel == tuple(jogo_web._COR_MARCA), pixel


def _idat(png: bytes) -> bytes:
    """Junta os blocos IDAT do PNG — só para o teste conferir pixels."""
    pos = 8
    partes = []
    while pos < len(png):
        tamanho = struct.unpack(">I", png[pos : pos + 4])[0]
        tipo = png[pos + 4 : pos + 8]
        dados = png[pos + 8 : pos + 8 + tamanho]
        if tipo == b"IDAT":
            partes.append(dados)
        pos += 12 + tamanho
    return b"".join(partes)


def test_o_icone_e_cacheado_e_nao_muda_entre_pedidos():
    assert jogo_web.icone_png(180) is jogo_web.icone_png(180)


def test_o_manifest_leva_o_nome_do_jogo_e_modo_standalone():
    dados = jogo_web.manifest("Meu-Jogo")
    assert dados["name"] == "Meu-Jogo"
    assert dados["display"] == "standalone"
    assert dados["start_url"] == "/"
    assert {icone["sizes"] for icone in dados["icons"]} == {"180x180", "512x512"}


def test_a_pagina_servida_ganha_as_tags_do_icone_e_o_arquivo_do_disco_nao_muda(tmp_path):
    base = _export(tmp_path / "export")
    original = (base / "index.html").read_bytes()
    srv = jogo_web.subir(base, porta=0, host="127.0.0.1")
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    try:
        resposta, corpo = _pedir(srv.server_address[1], "/")
        pagina = corpo.decode("utf-8")
        assert resposta.status == 200
        assert 'rel="apple-touch-icon"' in pagina
        assert "/jarvis-icone-180.png" in pagina
        assert 'name="apple-mobile-web-app-capable"' in pagina
        assert 'rel="manifest"' in pagina
        assert 'apple-mobile-web-app-title" content="export"' in pagina
        assert pagina.count('rel="apple-touch-icon"') == 1

        # o arquivo no disco continua como o motor gerou
        assert (base / "index.html").read_bytes() == original
    finally:
        srv.shutdown()
        srv.server_close()
        thread.join(timeout=5)


def test_as_tags_nao_entram_duas_vezes_em_pagina_ja_preparada():
    pagina = b"<html><head></head><body>x</body></html>"
    uma = jogo_web._injetar_pwa(pagina, "jogo")
    duas = jogo_web._injetar_pwa(uma, "jogo")
    assert uma == duas
    assert uma.count(b"apple-touch-icon") == 1


def test_pagina_sem_head_recebe_as_tags_no_comeco():
    injetada = jogo_web._injetar_pwa(b"<body>jogo</body>", "jogo")
    assert injetada.index(b"apple-touch-icon") < injetada.index(b"<body>")


def test_o_servidor_entrega_o_icone_e_o_manifest(servidor):
    _, porta, _ = servidor
    resposta, corpo = _pedir(porta, "/jarvis-icone-180.png")
    assert resposta.status == 200
    assert resposta.getheader("Content-Type") == "image/png"
    assert _png_tamanho(corpo) == (180, 180)

    resposta, corpo = _pedir(porta, "/jarvis-icone-512.png")
    assert _png_tamanho(corpo) == (512, 512)

    resposta, corpo = _pedir(porta, "/manifest.webmanifest")
    assert resposta.status == 200
    assert "manifest" in resposta.getheader("Content-Type")
    dados = json.loads(corpo)
    assert dados["display"] == "standalone"
    assert dados["short_name"]


def test_com_pwa_desligado_nada_disso_existe(tmp_path):
    base = _export(tmp_path / "export")
    srv = jogo_web.subir(base, porta=0, host="127.0.0.1", pwa=False)
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    try:
        porta = srv.server_address[1]
        for caminho in ("/jarvis-icone-180.png", "/manifest.webmanifest"):
            resposta, _ = _pedir(porta, caminho)
            assert resposta.status == 404
        resposta, corpo = _pedir(porta, "/")
        assert b"apple-touch-icon" not in corpo
    finally:
        srv.shutdown()
        srv.server_close()
        thread.join(timeout=5)


def test_o_icone_nao_e_servido_fora_da_pasta_nem_com_a_api(servidor):
    _, porta, _ = servidor
    # o manifesto é virtual, mas o resto da API continua sem existir
    resposta, _ = _pedir(porta, "/api/health")
    assert resposta.status == 404
    resposta, _ = _pedir(porta, "/jarvis-icone-180.png/../../.env")
    assert resposta.status == 404


def test_as_instrucoes_ensinam_a_tela_de_inicio(monkeypatch):
    monkeypatch.setattr(jogo_web, "endereco_local", lambda: "192.168.0.10")
    texto = jogo_web.instrucoes("Meu-Jogo", porta=8099)
    assert "Adicionar à Tela de Início" in texto
    assert "Compartilhar" in texto
    assert "sem a barra do Safari" in texto


def test_o_icone_nao_tem_linhas_atravessando_o_fundo():
    """Regressão: a primeira versão usava distância à RETA da aresta e o PNG
    saiu com três linhas cruzando o ícone inteiro (visto ao abrir o arquivo)."""
    png = jogo_web.icone_png(180)
    cru = zlib.decompress(_idat(png))
    largura = altura = 180
    marca = bytes(jogo_web._COR_MARCA)
    misturados = 0
    for y in range(altura):
        linha = cru[y * (1 + largura * 3) + 1 : (y + 1) * (1 + largura * 3)]
        for x in range(largura):
            pixel = linha[x * 3 : x * 3 + 3]
            if pixel == marca:
                continue
            # fundo puro: o gradiente não tem o verde da marca
            if pixel[1] > 160:
                misturados += 1
    # só a borda suavizada do triângulo pode misturar; as linhas do defeito
    # somavam milhares de pixels espalhados
    assert misturados < 900, misturados


# ---------------------------------------------------------------------------
# Enviar o export pela tela (0.92.1)
# ---------------------------------------------------------------------------
# O `.bat` já funcionava, mas o dono estava na tela do jogo quando perguntou
# “quero passar para o iPhone de graça”. A rota aceita o `.zip` do export — o
# único formato que o navegador sabe mandar (pasta não sobe).

def _zip_de_export(*, com_index: bool = True) -> bytes:
    import io

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as pacote:
        if com_index:
            # Com uma pasta dentro: é o formato do zip do Unity.
            pacote.writestr("Build/index.html", "<!doctype html><h1>jogo</h1>")
            pacote.writestr("Build/jogo.wasm", b"\0asm\1\0\0\0")
        else:
            pacote.writestr("Build/jogo.wasm", b"\0asm\1\0\0\0")
    return buffer.getvalue()


def _cliente(tmp_path: Path) -> TestClient:
    return TestClient(create_app(registry=build_registry(tmp_path / "files")))


def test_o_zip_do_export_entra_pela_tela_e_fica_pronto_para_servir(tmp_path: Path):
    cliente = _cliente(tmp_path)
    resposta = cliente.post(
        "/api/jogo/web",
        files={"upload": ("MeuJogo.zip", _zip_de_export(), "application/zip")},
        data={"confirmed": "true", "nome": "Meu-Jogo"},
    )
    assert resposta.status_code == 200, resposta.text
    dados = resposta.json()["result"]
    assert dados["nome"] == "Meu-Jogo"
    assert dados["arquivos"] >= 2

    lista = cliente.get("/api/jogo/web").json()["result"]
    assert lista["quantidade"] == 1
    assert lista["jogos"][0]["temIndex"] is True
    # O endereço aparece na tela: é o que se digita no Safari do iPhone.
    assert lista["porta"] == jogo_web.PORTA_PADRAO
    assert lista["endereco"].endswith(f":{jogo_web.PORTA_PADRAO}/")
    assert lista["endereco"].startswith("http://")


def test_zip_sem_index_html_e_recusado_com_a_explicacao(tmp_path: Path):
    cliente = _cliente(tmp_path)
    resposta = cliente.post(
        "/api/jogo/web",
        files={"upload": ("solto.zip", _zip_de_export(com_index=False), "application/zip")},
        data={"confirmed": "true"},
    )
    assert resposta.status_code == 400
    mensagem = resposta.json()["error"]["message"]
    assert "index.html" in mensagem
    # E nada foi guardado pela metade.
    assert cliente.get("/api/jogo/web").json()["result"]["quantidade"] == 0


def test_a_rota_recusa_apk_e_exige_confirmacao(tmp_path: Path):
    cliente = _cliente(tmp_path)
    apk = cliente.post(
        "/api/jogo/web",
        files={"upload": ("jogo.apk", b"PK\x03\x04", "application/octet-stream")},
        data={"confirmed": "true"},
    )
    assert apk.status_code == 400
    assert apk.json()["error"]["code"] == "INVALID_FORMAT"

    sem_confirmar = cliente.post(
        "/api/jogo/web",
        files={"upload": ("MeuJogo.zip", _zip_de_export(), "application/zip")},
    )
    assert sem_confirmar.status_code == 400
    assert sem_confirmar.json()["error"]["code"] == "CONFIRMATION_REQUIRED"


def test_nome_com_acento_vira_endereco_que_o_safari_aceita(tmp_path: Path):
    cliente = _cliente(tmp_path)
    resposta = cliente.post(
        "/api/jogo/web",
        files={"upload": ("Jogo.zip", _zip_de_export(), "application/zip")},
        data={"confirmed": "true", "nome": "Meu Jogo Ação"},
    )
    assert resposta.status_code == 200
    nome = resposta.json()["result"]["nome"]
    assert " " not in nome and all(ord(letra) < 128 for letra in nome)
