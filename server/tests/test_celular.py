"""Testes da camada do celular — nenhum deles toca num aparelho de verdade."""
from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from server import celular as C


@pytest.fixture()
def raiz(tmp_path, monkeypatch):
    monkeypatch.setenv("JARVIS_DADOS", str(tmp_path))
    monkeypatch.setattr(C.shutil, "which", lambda _nome: None)
    return tmp_path


@pytest.fixture()
def ligado(raiz, monkeypatch):
    monkeypatch.setenv(C.AMBIENTE, "1")
    return raiz


def _fingir_ferramentas(raiz: Path) -> tuple[Path, Path]:
    adb = raiz / "ferramentas" / "platform-tools" / "adb.exe"
    scrcpy = raiz / "ferramentas" / "scrcpy" / "scrcpy.exe"
    adb.parent.mkdir(parents=True, exist_ok=True)
    scrcpy.parent.mkdir(parents=True, exist_ok=True)
    adb.write_bytes(b"x")
    scrcpy.write_bytes(b"x")
    return adb, scrcpy


# --- ferramentas -------------------------------------------------------------

def test_sem_ferramentas_diz_o_que_falta(raiz):
    info = C.ferramentas()
    assert info["completo"] is False
    assert info["adb"] == "" and info["scrcpy"] == ""
    assert len(info["faltando"]) == 2
    assert "celular.preparar" in info["nota"]


def test_ferramentas_achadas_na_pasta_do_projeto(raiz):
    adb, scrcpy = _fingir_ferramentas(raiz)
    info = C.ferramentas()
    assert info["completo"] is True
    assert Path(info["adb"]) == adb
    assert Path(info["scrcpy"]) == scrcpy


def test_ferramentas_nao_executa_nada(raiz, monkeypatch):
    def explodir(*_args, **_kwargs):
        raise AssertionError("ferramentas() não pode executar processo")

    monkeypatch.setattr(C.subprocess, "run", explodir)
    monkeypatch.setattr(C.subprocess, "Popen", explodir)
    C.ferramentas()


# --- leitura do adb ----------------------------------------------------------

def test_parsear_dispositivos_autorizado():
    saida = (
        "List of devices attached\n"
        "R58M12345\tdevice usb:1-1 product:on7xelte model:SM_G610F device:on7xelte transport_id:3\n"
    )
    itens = C.parsear_dispositivos(saida)
    assert itens == [
        {
            "serial": "R58M12345",
            "estado": "device",
            "product": "on7xelte",
            "model": "SM_G610F",
            "device": "on7xelte",
            "transport_id": "3",
        }
    ]


def test_parsear_dispositivos_nao_autorizado():
    itens = C.parsear_dispositivos("List of devices attached\nABC123\tunauthorized\n")
    assert itens[0]["estado"] == "unauthorized"
    assert C.situacao_de(itens) == "nao-autorizado"


def test_parsear_dispositivos_vazio():
    assert C.parsear_dispositivos("List of devices attached\n\n") == []
    assert C.situacao_de([]) == "vazio"


def test_estado_sem_a_permissao_nao_roda(ligado, monkeypatch):
    _fingir_ferramentas(ligado)
    monkeypatch.delenv(C.AMBIENTE, raising=False)

    def explodir(*_a, **_k):
        raise AssertionError("não pode executar com a variável desligada")

    resultado = C.estado(rodar=explodir)
    assert resultado["executado"] is False
    assert C.AMBIENTE in resultado["motivo"]


def test_estado_com_a_permissao_le_o_aparelho(ligado):
    _fingir_ferramentas(ligado)
    chamadas = []

    def rodar(argumentos):
        chamadas.append(argumentos)
        return 0, "List of devices attached\nR58M\tdevice model:SM_G610F\n", ""

    resultado = C.estado(rodar=rodar)
    assert resultado["executado"] is True
    assert resultado["situacao"] == "autorizado"
    assert chamadas[0][1:] == ["devices", "-l"]


def test_estado_sem_adb_avisa_para_preparar(raiz):
    resultado = C.estado()
    assert resultado["executado"] is False
    assert "celular.preparar" in resultado["motivo"]


def test_estado_com_erro_do_adb_devolve_motivo(ligado):
    _fingir_ferramentas(ligado)
    resultado = C.estado(rodar=lambda _a: (1, "", "error: cannot connect to daemon"))
    assert resultado["executado"] is True
    assert "daemon" in resultado["motivo"]


# --- plano -------------------------------------------------------------------

def test_plano_sem_ferramentas_manda_baixar(raiz):
    resultado = C.plano("auto")
    assert resultado["situacao"] == "sem-ferramentas"
    assert "celular.preparar" in resultado["resposta"]
    assert "scrcpy" in resultado["resposta"]


def test_plano_desligado(ligado, monkeypatch):
    _fingir_ferramentas(ligado)
    monkeypatch.delenv(C.AMBIENTE, raising=False)
    resultado = C.plano("auto")
    assert resultado["situacao"] == "desligado"
    assert C.AMBIENTE in resultado["resposta"]


def test_plano_nao_autorizado_traz_a_sequencia_de_teclas(ligado):
    _fingir_ferramentas(ligado)
    resultado = C.plano("nao-autorizado")
    texto = resultado["resposta"]
    assert resultado["situacao"] == "nao-autorizado"
    assert "scrcpy --otg" in texto
    assert "Tab, Enter, Tab, Tab, Enter" in texto
    assert "locksettings clear" in texto
    assert resultado["total"] == 5


def test_plano_vazio_fala_de_tela_de_teste_e_frp():
    texto = C.plano("vazio")["resposta"]
    assert "BLOCKED BY FRP LOCK" in texto
    assert "tela de teste" in texto
    assert "TalkBack" in texto


def test_plano_autorizado_aponta_o_espelhamento(ligado):
    _fingir_ferramentas(ligado)
    resultado = C.plano("auto", rodar=lambda _a: (0, "List of devices attached\nR58M\tdevice\n", ""))
    assert resultado["situacao"] == "autorizado"
    assert "scrcpy" in resultado["resposta"]
    assert "celular.puxar" in resultado["resposta"]


def test_plano_recovery_resgata_arquivos():
    texto = C.plano("recovery")["resposta"]
    assert "adb pull /sdcard" in texto


def test_plano_recusa_estado_inventado():
    with pytest.raises(C.CelularError):
        C.plano("ligado-no-wifi")


def test_plano_termina_lembrando_o_limite():
    texto = C.plano("vazio")["resposta"]
    assert "Permitir depuração USB" in texto


# --- espelhar ----------------------------------------------------------------

def test_espelhar_sem_permissao_recusa(raiz, monkeypatch):
    monkeypatch.delenv(C.AMBIENTE, raising=False)
    with pytest.raises(C.CelularError):
        C.espelhar(abrir=lambda _a: None)


def test_espelhar_sem_scrcpy_recusa(ligado):
    with pytest.raises(C.CelularError) as erro:
        C.espelhar(abrir=lambda _a: None)
    assert "celular.preparar" in str(erro.value)


def test_espelhar_monta_o_comando(ligado):
    _fingir_ferramentas(ligado)
    abertos = []
    resultado = C.espelhar(abrir=lambda argumentos: abertos.append(argumentos))
    assert abertos and abertos[0][0].endswith("scrcpy.exe")
    assert "--turn-screen-off" in abertos[0]
    assert resultado["aberto"] is True
    assert "--turn-screen-off" in resultado["comando"]


def test_espelhar_com_gravacao(ligado):
    _fingir_ferramentas(ligado)
    resultado = C.espelhar(gravar=True, desligar_painel=False, abrir=lambda _a: None)
    assert "--record" in resultado["comando"]
    assert "--turn-screen-off" not in resultado["comando"]


# --- puxar -------------------------------------------------------------------

def test_puxar_sem_permissao_recusa(raiz, monkeypatch):
    monkeypatch.delenv(C.AMBIENTE, raising=False)
    with pytest.raises(C.CelularError):
        C.puxar(rodar=lambda _a: (0, "", ""))


def test_puxar_recusa_data_e_fora_da_lista(ligado):
    _fingir_ferramentas(ligado)
    for proibida in ("data", "/data", "system", "../"):
        with pytest.raises(C.CelularError):
            C.pastas_para_puxar([proibida])


def test_puxar_usa_pastas_padrao(ligado, tmp_path):
    _fingir_ferramentas(ligado)
    comandos = []

    def rodar(argumentos):
        comandos.append(argumentos)
        return 0, "1 file pulled", ""

    resultado = C.puxar(rodar=rodar)
    assert resultado["total"] == 5
    assert resultado["ok"] == 5
    assert [c[2] for c in comandos] == [
        "/sdcard/DCIM",
        "/sdcard/Pictures",
        "/sdcard/Download",
        "/sdcard/Documents",
        "/sdcard/WhatsApp",
    ]
    assert all(Path(c[3]).is_dir() for c in comandos)


def test_puxar_respeita_apelido_de_pasta(ligado):
    _fingir_ferramentas(ligado)
    assert C.pastas_para_puxar(["camera", "fotos do zap".replace("fotos do zap", "whatsapp")]) == [
        "DCIM/Camera",
        "WhatsApp",
    ]


def test_puxar_recusa_destino_fora_da_raiz(ligado):
    _fingir_ferramentas(ligado)
    with pytest.raises(C.CelularError):
        C.puxar(["DCIM"], "/etc/jarvis", rodar=lambda _a: (0, "", ""))


def test_puxar_marca_o_que_falhou(ligado):
    _fingir_ferramentas(ligado)

    def rodar(argumentos):
        if argumentos[2].endswith("WhatsApp"):
            return 1, "", "adb: error: failed to stat remote object"
        return 0, "ok", ""

    resultado = C.puxar(["DCIM", "WhatsApp"], rodar=rodar)
    assert resultado["ok"] == 1
    assert resultado["itens"][1]["ok"] is False
    assert "failed" in resultado["itens"][1]["saida"]


# --- preparar ----------------------------------------------------------------

def test_extrair_recusa_zip_slip(tmp_path):
    zipe = tmp_path / "mal.zip"
    with zipfile.ZipFile(zipe, "w") as pacote:
        pacote.writestr("../../fora.txt", "x")
    with pytest.raises(C.CelularError):
        C._extrair(zipe, tmp_path / "destino")


def test_url_do_scrcpy_escolhe_o_zip_do_windows():
    def abrir(_url):
        return {
            "tag_name": "v3.3.1",
            "assets": [
                {"name": "scrcpy-linux-v3.3.1.tar.gz", "browser_download_url": "https://x/linux"},
                {"name": "scrcpy-win64-v3.3.1.zip", "browser_download_url": "https://x/win"},
            ],
        }

    escolhido = C.url_do_scrcpy(abrir=abrir)
    assert escolhido["url"] == "https://x/win"
    assert escolhido["versao"] == "v3.3.1"


def test_url_do_scrcpy_sem_asset_explica():
    with pytest.raises(C.CelularError) as erro:
        C.url_do_scrcpy(abrir=lambda _u: {"tag_name": "v1", "assets": []})
    assert "sistema.baixar" in str(erro.value)


def test_preparar_baixa_extrai_e_nao_executa(ligado, tmp_path):
    def fabricar_zip(destino: Path, membro: str) -> Path:
        caminho = destino / f"{membro}.zip"
        destino.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(caminho, "w") as pacote:
            pacote.writestr(f"{membro}/binario.exe", "x")
            pacote.writestr(f"{membro}/LEIA.txt", "ok")
        return caminho

    zips = tmp_path / "quarentena"
    zips.mkdir()
    baixados = {"n": 0}

    def baixar(url, autorizacao=""):
        baixados["n"] += 1
        nome = "platform-tools" if "google" in url else "scrcpy"
        caminho = fabricar_zip(zips, nome)
        return {"arquivo": str(caminho), "sha256": "abc", "bytes": 10}

    resultado = C.preparar(
        baixar=baixar,
        resolver_scrcpy=lambda: {"url": "https://github/scrcpy.zip", "versao": "v9"},
    )
    assert baixados["n"] == 2
    assert (ligado / "ferramentas" / "platform-tools" / "LEIA.txt").is_file()
    assert (ligado / "ferramentas" / "scrcpy" / "LEIA.txt").is_file()
    assert resultado["baixados"][0]["sha256"] == "abc"
    assert resultado["baixados"][0]["extraido"] > 0


def test_preparar_sem_download_recusa(ligado):
    def baixar(url, autorizacao=""):
        return {"arquivo": str(ligado / "nao-existe.zip")}

    with pytest.raises(C.CelularError):
        C.preparar(baixar=baixar, resolver_scrcpy=lambda: {"url": "https://x/y.zip"})


# --- registro ----------------------------------------------------------------

def test_registro_tem_as_cinco_skills():
    from server.skill_registry import build_registry

    registro = build_registry(Path("/tmp/nao-usado") / "files")
    ids = {item["id"] for item in registro.list()}
    assert {"celular.status", "celular.plano", "celular.espelhar", "celular.puxar", "celular.preparar"} <= ids


def test_skill_de_plano_responde_pelo_registro():
    import asyncio

    from server.skill_registry import build_registry

    registro = build_registry(Path("/tmp/nao-usado") / "files")
    resultado = asyncio.run(registro.execute("celular.plano", {"estado": "vazio"}))
    assert resultado["situacao"] == "vazio"
    assert "BLOCKED BY FRP LOCK" in resultado["resposta"]


# --- banner e avisos ---------------------------------------------------------

def test_banner_mostra_o_estado_do_celular(capsys, tmp_path, monkeypatch):
    """O banner precisa dizer se a camada do celular está ligada."""
    from fastapi.testclient import TestClient

    from server.app import create_app
    from server.skill_registry import build_registry

    monkeypatch.setenv("JARVIS_DADOS", str(tmp_path))
    monkeypatch.setenv("JARVIS_HOST_CELULAR", "1")
    monkeypatch.setenv("JARVIS_HOST_PC", "0")
    aplicacao = create_app(registry=build_registry(tmp_path / "files"))
    with TestClient(aplicacao):
        pass
    saida = capsys.readouterr().out
    assert "celular=ligado" in saida
    assert "pc=desligado" in saida


def test_nenhum_modulo_tem_escape_invalido():
    """`\\S`, `\\M`, `\\D` em docstring viram SyntaxWarning no Python novo."""
    import warnings
    from pathlib import Path

    raiz = Path(__file__).resolve().parents[2] / "server"
    ruins = []
    for arquivo in sorted(raiz.rglob("*.py")):
        texto = arquivo.read_text(encoding="utf-8")
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("error", SyntaxWarning)
                warnings.simplefilter("error", DeprecationWarning)
                compile(texto, str(arquivo), "exec")
        except (SyntaxWarning, DeprecationWarning) as exc:
            ruins.append(f"{arquivo.name}: {exc}")
    assert ruins == [], "\n".join(ruins)


# --- configurar-celular.py ---------------------------------------------------

def _carregar_configurador():
    """Importa o script da raiz sem depender do nome do módulo."""
    import importlib.util
    from pathlib import Path

    caminho = Path(__file__).resolve().parents[2] / "configurar-celular.py"
    especificacao = importlib.util.spec_from_file_location("configurar_celular", caminho)
    modulo = importlib.util.module_from_spec(especificacao)
    especificacao.loader.exec_module(modulo)
    return modulo


def test_configurador_troca_o_valor_sem_duplicar():
    modulo = _carregar_configurador()
    texto, antes, depois = modulo.ajustar("JARVIS_HOST_REDE=0\nJARVIS_HOST_CELULAR=0\nOUTRA=1\n")
    linhas = texto.splitlines()
    assert "JARVIS_HOST_REDE=1" in linhas
    assert "JARVIS_HOST_CELULAR=1" in linhas
    assert "JARVIS_HOST_REDE=0" not in linhas
    assert linhas.count("JARVIS_HOST_REDE=1") == 1
    assert "OUTRA=1" in linhas
    assert antes["JARVIS_HOST_REDE"] == "JARVIS_HOST_REDE=0"
    assert depois["JARVIS_HOST_CELULAR"] == "JARVIS_HOST_CELULAR=1"


def test_configurador_acrescenta_o_que_falta():
    modulo = _carregar_configurador()
    texto, antes, _ = modulo.ajustar("OUTRA=1\n")
    assert "OUTRA=1" in texto
    assert "JARVIS_HOST_REDE=1" in texto
    assert "JARVIS_HOST_CELULAR=1" in texto
    assert antes["JARVIS_HOST_REDE"] == "(não existia)"


def test_configurador_ignora_comentario_com_a_chave():
    modulo = _carregar_configurador()
    texto, _, _ = modulo.ajustar("# JARVIS_HOST_REDE=0\n")
    linhas = [l for l in texto.splitlines() if l.startswith("JARVIS_HOST_REDE")]
    assert linhas == ["JARVIS_HOST_REDE=1"]
    assert "# JARVIS_HOST_REDE=0" in texto


def test_configurador_e_idempotente():
    modulo = _carregar_configurador()
    primeira, _, _ = modulo.ajustar("JARVIS_HOST_REDE=0\n")
    segunda, _, _ = modulo.ajustar(primeira)
    assert primeira == segunda


def test_configurador_grava_crlf_sem_bom(tmp_path):
    modulo = _carregar_configurador()
    alvo = tmp_path / ".env"
    modulo._gravar(alvo, "A=1\nB=2\n")
    dados = alvo.read_bytes()
    assert not dados.startswith(b"\xef\xbb\xbf")
    assert dados.count(b"\n") == dados.count(b"\r\n") == 2


def test_configurador_le_arquivo_com_bom(tmp_path):
    modulo = _carregar_configurador()
    alvo = tmp_path / ".env"
    alvo.write_bytes(b"\xef\xbb\xbfJARVIS_HOST_REDE=0\r\n")
    texto = modulo._ler(alvo)
    assert texto.startswith("JARVIS_HOST_REDE=0")
    _, antes, _ = modulo.ajustar(texto)
    assert antes["JARVIS_HOST_REDE"] == "JARVIS_HOST_REDE=0"


# --- layout real dos zips (scrcpy vem com a versão no nome) ------------------

def test_acha_scrcpy_em_pasta_com_versao_no_nome(raiz):
    """O zip oficial extrai em `scrcpy-win64-v3.3.1/`; a busca tem de achar."""
    versionada = raiz / "ferramentas" / "scrcpy-win64-v3.3.1"
    versionada.mkdir(parents=True)
    (versionada / "scrcpy.exe").write_bytes(b"x")
    encontrado = C._achar(C.SCRCPY_NOMES)
    assert encontrado is not None
    assert encontrado.name == "scrcpy.exe"
    assert C.ferramentas()["scrcpy"] != ""


def test_achar_prefere_o_caminho_canonico(raiz):
    canonica = raiz / "ferramentas" / "scrcpy"
    canonica.mkdir(parents=True)
    (canonica / "scrcpy.exe").write_bytes(b"x")
    versao = raiz / "ferramentas" / "scrcpy-win64-v9"
    versao.mkdir()
    (versao / "scrcpy.exe").write_bytes(b"x")
    assert C._achar(C.SCRCPY_NOMES).parent.name == "scrcpy"


def test_normalizar_renomeia_a_pasta_para_o_nome_canonico(raiz):
    versionada = raiz / "ferramentas" / "scrcpy-win64-v3.3.1"
    versionada.mkdir(parents=True)
    (versionada / "scrcpy.exe").write_bytes(b"x")
    (versionada / "aviso.txt").write_text("junto", encoding="utf-8")
    pasta = C.normalizar("scrcpy", C.SCRCPY_NOMES)
    assert pasta == raiz / "ferramentas" / "scrcpy"
    assert (pasta / "scrcpy.exe").is_file()
    assert (pasta / "aviso.txt").is_file()
    assert not versionada.exists()


def test_normalizar_nao_mexe_quando_ja_esta_certo(raiz):
    canonica = raiz / "ferramentas" / "platform-tools"
    canonica.mkdir(parents=True)
    (canonica / "adb.exe").write_bytes(b"x")
    assert C.normalizar("platform-tools", C.ADB_NOMES) == canonica
    assert (canonica / "adb.exe").is_file()


def test_preparar_deixa_o_layout_que_as_skills_enxergam(ligado):
    """Depois do preparo, `ferramentas()` tem de dizer completo."""
    def fabricar(destino: Path, pasta: str, nome_exe: str) -> Path:
        caminho = destino / f"{pasta}.zip"
        destino.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(caminho, "w") as pacote:
            pacote.writestr(f"{pasta}/{nome_exe}", "x")
        return caminho

    quarentena = ligado / "quarentena"
    quarentena.mkdir()

    def baixar(url, autorizacao=""):
        if "google" in url:
            caminho = fabricar(quarentena, "platform-tools", "adb.exe")
        else:
            caminho = fabricar(quarentena, "scrcpy-win64-v3.3.1", "scrcpy.exe")
        return {"arquivo": str(caminho), "sha256": "abc", "bytes": 10}

    resultado = C.preparar(baixar=baixar, resolver_scrcpy=lambda: {"url": "https://g/scrcpy.zip"})
    assert resultado["ferramentas"]["completo"] is True, resultado["ferramentas"]
    assert resultado["ferramentas"]["adb"].endswith("adb.exe")
    assert resultado["ferramentas"]["scrcpy"].endswith("scrcpy.exe")
    assert "Nada foi executado" in resultado["resposta"]


def test_configurador_liga_o_modo_dono():
    modulo = _carregar_configurador()
    texto, _, depois = modulo.ajustar("")
    assert "JARVIS_HOST_CONFIAR_LOCAL=1" in texto
    assert depois["JARVIS_HOST_CONFIAR_LOCAL"] == "JARVIS_HOST_CONFIAR_LOCAL=1"


# --- o caminho exato do bug de 0.60.7 ---------------------------------------

def test_preparar_com_token_acentuado_recusa_com_explicacao(ligado, monkeypatch):
    """`hmac.compare_digest` levanta TypeError com acento; aqui vira mensagem."""
    from server import sistema

    monkeypatch.setattr(sistema, "token_host", lambda: "abc123XYZ_ok-token")
    monkeypatch.delenv("JARVIS_HOST_CONFIAR_LOCAL", raising=False)
    with pytest.raises(sistema.SistemaError) as erro:
        sistema.baixar(url="https://example.com/x.zip", autorizacao="não, pode")
    texto = str(erro.value)
    assert "compar" not in texto.lower()
    assert "não é um token" in texto


def test_preparar_sem_token_explica_que_nao_veio_da_maquina(ligado, monkeypatch):
    from server import sistema

    monkeypatch.setattr(sistema, "token_host", lambda: "abc123XYZ_ok-token")
    monkeypatch.delenv("JARVIS_HOST_CONFIAR_LOCAL", raising=False)
    monkeypatch.delenv("JARVIS_HOST_EXIGIR_TOKEN_LOCAL", raising=False)
    with pytest.raises(sistema.SistemaError) as erro:
        sistema.baixar(url="https://example.com/x.zip", autorizacao="")
    assert "não veio da própria máquina" in str(erro.value)


def test_preparar_sem_token_com_trava_local_explica_a_trava(ligado, monkeypatch):
    from server import sistema

    monkeypatch.setattr(sistema, "token_host", lambda: "abc123XYZ_ok-token")
    monkeypatch.delenv("JARVIS_HOST_CONFIAR_LOCAL", raising=False)
    monkeypatch.setenv("JARVIS_HOST_EXIGIR_TOKEN_LOCAL", "1")
    with pytest.raises(sistema.SistemaError) as erro:
        sistema.baixar(url="https://example.com/x.zip", autorizacao="")
    assert "JARVIS_HOST_EXIGIR_TOKEN_LOCAL" in str(erro.value)


def test_agente_nao_tira_token_da_frase():
    from server import agente_local

    schema = {
        "properties": {
            "autorizacao": {"type": "string"},
            "arquivo": {"type": "string"},
        },
        "required": [],
    }
    valores, _ = agente_local.extrair_parametros("sim, pode", schema)
    assert "autorizacao" not in valores

    explicitos = agente_local.parametros_explicitos("autorizacao=sim pode", schema)
    assert "autorizacao" not in explicitos


def test_atualizar_bat_avisa_para_fechar_a_api_antes():
    raiz = Path(__file__).resolve().parents[2]
    texto = (raiz / "atualizar.bat").read_text(encoding="utf-8", errors="replace")
    # o aviso tem de vir ANTES do robocopy, senao copia com arquivo em uso
    aviso = texto.index("feche a janela da API")
    copia = texto.index("robocopy")
    assert aviso < copia
    assert "Ctrl+C" not in texto


def test_nenhum_texto_de_atalho_manda_digitar_ctrl_c():
    """Quem usa o JARVIS fecha a janela; Ctrl+C digitado no prompt nao existe."""
    raiz = Path(__file__).resolve().parents[2]
    alvos = ["configurar-celular.py", "iniciar.py", "mover-dados.py", "atualizar.bat"]
    for nome in alvos:
        texto = (raiz / nome).read_text(encoding="utf-8", errors="replace")
        assert "Ctrl+C" not in texto, nome


# --- contrato com o sistema.baixar de verdade --------------------------------

class _Resposta:
    """Imita o que `urllib` devolve: contexto, read em blocos e headers."""

    def __init__(self, conteudo: bytes) -> None:
        self._conteudo = conteudo
        self._posicao = 0
        self.headers = {"content-type": "application/zip"}

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def read(self, tamanho: int = -1) -> bytes:
        if tamanho < 0:
            tamanho = len(self._conteudo) - self._posicao
        bloco = self._conteudo[self._posicao : self._posicao + tamanho]
        self._posicao += len(bloco)
        return bloco


def _zip_em_memoria(pasta: str, executavel: str) -> bytes:
    import io

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as pacote:
        pacote.writestr(f"{pasta}/{executavel}", "x")
        pacote.writestr(f"{pasta}/LEIA.txt", "ok")
    return buffer.getvalue()


def test_sistema_baixar_guarda_o_arquivo_em_download(ligado, monkeypatch):
    """O contrato que o bug da 0.60.7 quebrou: o caminho mora em `download`."""
    from server import sistema

    monkeypatch.setattr(sistema, "_exigir_rede", lambda *_a, **_k: None)
    monkeypatch.setattr(sistema, "_url_segura", lambda url: url)
    monkeypatch.setattr(sistema, "_auditar", lambda *_a, **_k: None)
    monkeypatch.setattr(
        sistema, "urlopen", lambda *_a, **_k: _Resposta(_zip_em_memoria("platform-tools", "adb.exe"))
    )
    resultado = sistema.baixar(url="https://dl.google.com/android/repository/platform-tools.zip")
    assert "arquivo" not in resultado  # é envelope, não o bônus
    assert resultado["download"]["arquivo"].endswith(".zip")
    assert Path(resultado["download"]["arquivo"]).is_file()


def test_preparar_com_o_sistema_baixar_de_verdade(ligado, monkeypatch):
    """O teste que faltava: preparar lendo o retorno real de `sistema.baixar`."""
    from server import sistema

    zips = {
        "platform-tools": _zip_em_memoria("platform-tools", "adb.exe"),
        "scrcpy": _zip_em_memoria("scrcpy-win64-v3", "scrcpy.exe"),
    }

    def urlopen(pedido, timeout=None):
        url = getattr(pedido, "full_url", str(pedido))
        return _Resposta(zips["scrcpy"] if "github" in url else zips["platform-tools"])

    monkeypatch.setattr(sistema, "_exigir_rede", lambda *_a, **_k: None)
    monkeypatch.setattr(sistema, "_url_segura", lambda url: url)
    monkeypatch.setattr(sistema, "_auditar", lambda *_a, **_k: None)
    monkeypatch.setattr(sistema, "urlopen", urlopen)

    resultado = C.preparar(
        resolver_scrcpy=lambda: {"url": "https://github.com/x/scrcpy-win64-v3.zip", "versao": "v3"},
    )
    ferramentas = resultado["ferramentas"]
    assert ferramentas["completo"] is True, resultado
    assert Path(ferramentas["adb"]).is_file()
    assert Path(ferramentas["scrcpy"]).is_file()
    assert len(resultado["baixados"]) == 2
    assert all(item["sha256"] for item in resultado["baixados"])


def test_mensagem_de_download_sem_arquivo_diz_o_caminho(ligado, tmp_path):
    sumido = tmp_path / "nao-existe" / "platform-tools.zip"

    def baixar(url, autorizacao=""):
        return {"download": {"arquivo": str(sumido)}}

    with pytest.raises(C.CelularError) as erro:
        C.preparar(baixar=baixar, resolver_scrcpy=lambda: {"url": "https://x/y.zip"})
    assert str(sumido) in str(erro.value)
    assert "host-downloads" in str(erro.value)


def test_preparar_apaga_o_zip_depois_de_extrair(ligado):
    """90 MB no pendrive não podem ficar de enfeite na quarentena."""
    zips = ligado / "quarentena"
    zips.mkdir(parents=True, exist_ok=True)
    criados: list[Path] = []

    def baixar(url, autorizacao=""):
        pasta, exe = ("platform-tools", "adb.exe") if "google" in url else ("scrcpy-win64-v9", "scrcpy.exe")
        caminho = zips / f"{pasta}.zip"
        with zipfile.ZipFile(caminho, "w") as pacote:
            pacote.writestr(f"{pasta}/{exe}", "x")
        criados.append(caminho)
        return {"download": {"arquivo": str(caminho), "sha256": "abc", "bytes": 10}}

    C.preparar(baixar=baixar, resolver_scrcpy=lambda: {"url": "https://github/scrcpy.zip"})
    assert criados and all(not caminho.exists() for caminho in criados)


# --- sonda do Windows: cabo/driver/depuração, três respostas diferentes ------

def test_sonda_recusa_fora_do_windows():
    resultado = C.windows_ve()
    assert resultado["consulta"] is False
    assert "Windows" in resultado["motivo"]


def test_sonda_le_o_que_o_powershell_devolveu(monkeypatch):
    monkeypatch.setattr(C.os, "name", "nt")
    monkeypatch.setattr(C.sys, "platform", "win32")

    def rodar(argumentos):
        assert argumentos[0] == "powershell"
        return 0, (
            "OK|USB|SAMSUNG Mobile USB Composite Device\n"
            "Error|USB|MTP\n"
            "OK|USB|SAMSUNG Mobile USB Composite Device\n"
        ), ""

    resultado = C.windows_ve(rodar=rodar)
    assert resultado["consulta"] is True
    assert resultado["visivel"] is True
    assert resultado["com_problema"] is True
    assert len(resultado["dispositivos"]) == 2  # linha repetida não conta
    assert "driver" in resultado["resumo"].lower()


def test_sonda_sem_aparelho_nao_inventa_driver(monkeypatch):
    monkeypatch.setattr(C.os, "name", "nt")
    monkeypatch.setattr(C.sys, "platform", "win32")
    resultado = C.windows_ve(rodar=lambda argumentos: (0, "", ""))
    assert resultado == {
        "consulta": True,
        "dispositivos": [],
        "visivel": False,
        "com_problema": False,
        "resumo": "O Windows não vê nenhum aparelho na USB.",
    }


def test_plano_vazio_muda_o_primeiro_passo_quando_a_sonda_responde():
    visivel = {"consulta": True, "visivel": True, "com_problema": False, "dispositivos": [{"status": "OK", "classe": "USB", "nome": "SAMSUNG Mobile"}]}
    driver = {"consulta": True, "visivel": True, "com_problema": True, "dispositivos": [{"status": "Error", "classe": "USB", "nome": "MTP"}]}
    nada = {"consulta": True, "visivel": False, "com_problema": False, "dispositivos": []}

    assert "cabo e porta estão bons" in C._plano_vazio(visivel)[0]["titulo"].lower()
    assert "driver" in C._plano_vazio(driver)[0]["titulo"].lower()
    assert "nada aparece" in C._plano_vazio(nada)[0]["titulo"].lower()
    # o passo "abra o Gerenciador de Dispositivos" sai quando a sonda já respondeu
    assert all("Gerenciador" not in passo["titulo"] for passo in C._plano_vazio(visivel))
    # e continua lá quando não há sonda
    assert any("Windows vê" in passo["titulo"] for passo in C._plano_vazio())


def test_status_sonda_o_windows_so_quando_o_adb_nao_ve_nada(ligado, monkeypatch):
    from pathlib import Path as _Path

    adb = ligado / "adb.exe"
    adb.write_text("x", encoding="utf-8")
    monkeypatch.setattr(C, "ferramentas", lambda: {"adb": str(adb), "scrcpy": "x", "completo": True})
    monkeypatch.setenv("JARVIS_HOST_CELULAR", "1")
    monkeypatch.setattr(C, "windows_ve", lambda rodar=None: {"consulta": True, "visivel": True, "com_problema": False, "dispositivos": []})

    vazio = C.estado(rodar=lambda argumentos: (0, "List of devices attached\n\n", ""))
    assert vazio["situacao"] == "vazio"
    assert vazio["windows"]["visivel"] is True

    cheio = C.estado(
        rodar=lambda argumentos: (0, "List of devices attached\nABC123\tdevice product:on7xelte\n", "")
    )
    assert cheio["situacao"] == "autorizado"
    assert "windows" not in cheio  # não pergunta o que não precisa


def test_status_derruba_adb_de_outra_versao_e_tenta_de_novo(ligado, monkeypatch):
    adb = ligado / "adb.exe"
    adb.write_text("x", encoding="utf-8")
    monkeypatch.setattr(C, "ferramentas", lambda: {"adb": str(adb), "scrcpy": "x", "completo": True})
    monkeypatch.setenv("JARVIS_HOST_CELULAR", "1")
    monkeypatch.setattr(C, "windows_ve", lambda rodar=None: {"consulta": False, "dispositivos": []})
    chamadas: list[list[str]] = []

    def rodar(argumentos):
        chamadas.append(argumentos)
        if argumentos[1] == "kill-server":
            return 0, "", ""
        if len(chamadas) == 1:
            return 1, "", "adb server version (40) doesn't match this client (41); killing..."
        return 0, "List of devices attached\nXYZ9000\tdevice product:on7xelte\n", ""

    resultado = C.estado(rodar=rodar)
    assert resultado["situacao"] == "autorizado"
    assert chamadas[1][1] == "kill-server"
