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


# --- o caminho exato do bug de 0.61.7 ---------------------------------------

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
    """O contrato que o bug da 0.61.7 quebrou: o caminho mora em `download`."""
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
            "OK\tUSB\tSAMSUNG Mobile USB Composite Device\tUSB\\VID_04E8&PID_6860\\R58M1\tSamsung Electronics Co., Ltd.\n"
            "Error\tUSB\tSAMSUNG Mobile USB Composite Device\tUSB\\VID_04E8&PID_6861\\R58M2\tSamsung Electronics Co., Ltd.\n"
            "OK\tUSB\tSAMSUNG Mobile USB Composite Device\tUSB\\VID_04E8&PID_6860\\R58M1\tSamsung Electronics Co., Ltd.\n"
        ), ""

    resultado = C.windows_ve(rodar=rodar)
    assert resultado["consulta"] is True
    assert resultado["visivel"] is True
    assert resultado["com_problema"] is True
    assert len(resultado["dispositivos"]) == 2  # linha repetida não conta
    assert resultado["telefones"][0]["vid"] == "04e8"
    assert "driver" in resultado["resumo"].lower()


def test_sonda_sem_aparelho_nao_inventa_driver(monkeypatch):
    monkeypatch.setattr(C.os, "name", "nt")
    monkeypatch.setattr(C.sys, "platform", "win32")
    resultado = C.windows_ve(rodar=lambda argumentos: (0, "", ""))
    assert resultado["consulta"] is True
    assert resultado["dispositivos"] == []
    assert resultado["telefones"] == []
    assert resultado["visivel"] is False
    assert resultado["com_problema"] is False
    assert resultado["resumo"] == "O Windows não vê nenhum aparelho na USB."


def _sonda(telefones=(), genericos=(), problema=False, desconhecidos=(), comparacao=None):
    sonda = {
        "consulta": True,
        "dispositivos": [*telefones, *genericos, *desconhecidos],
        "telefones": list(telefones),
        "genericos": list(genericos),
        "desconhecidos": list(desconhecidos),
        "visivel": bool(telefones),
        "com_problema": problema,
    }
    if comparacao is not None:
        sonda["comparacao"] = comparacao
    return sonda


def test_plano_vazio_muda_o_primeiro_passo_quando_a_sonda_responde():
    visivel = _sonda([{"status": "OK", "classe": "USB", "nome": "SAMSUNG Mobile", "vid": "04e8"}])
    driver = _sonda([{"status": "Error", "classe": "USB", "nome": "SAMSUNG Mobile", "vid": "04e8"}], problema=True)
    nada = _sonda()

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


# --- celular.status mede o aparelho (0.60.8) ---------------------------------

def _status_handler_com(monkeypatch, medido):
    from server import skill_registry

    monkeypatch.setattr(skill_registry.celular, "estado", lambda **_k: medido)
    registro = skill_registry.build_registry(Path("/tmp/status-files") / "files")
    import asyncio

    return asyncio.run(registro.execute("celular.status", {}, False))


def test_status_conectado_e_autorizado_diz_o_proximo_passo(monkeypatch):
    resultado = _status_handler_com(
        monkeypatch,
        {
            "ferramentas": {"completo": True, "adb": "C:\\J\\adb.exe", "scrcpy": "C:\\J\\scrcpy.exe"},
            "executado": True,
            "codigo": 0,
            "aparelhos": [{"serial": "R58M12ABC", "estado": "device", "model": "SM-G610M"}],
            "situacao": "autorizado",
        },
    )
    assert resultado["situacao"] == "autorizado"
    assert "R58M12ABC" in resultado["resposta"]
    assert "celular.espelhar" in resultado["proximo_passo"]


def test_status_com_tudo_pronto_mas_sem_cabo_nao_diz_tudo_pronto(monkeypatch):
    """O bug da 0.61.7: respondia "Tudo pronto" com o celular desligado na gaveta."""
    resultado = _status_handler_com(
        monkeypatch,
        {
            "ferramentas": {"completo": True, "adb": "a", "scrcpy": "s"},
            "executado": True,
            "codigo": 0,
            "aparelhos": [],
            "situacao": "vazio",
            "windows": {"consulta": True, "visivel": False, "com_problema": False, "dispositivos": [], "resumo": "O Windows não vê nenhum aparelho na USB."},
        },
    )
    assert resultado["situacao"] == "vazio"
    assert "tudo pronto" not in resultado["resposta"].lower()
    assert "cabo" in resultado["proximo_passo"].lower()


def test_status_sem_cabo_mas_com_windows_cego_manda_trocar_cabo(monkeypatch):
    resultado = C.resumo(
        {
            "ferramentas": {"completo": True, "adb": "a", "scrcpy": "s"},
            "executado": True,
            "codigo": 0,
            "aparelhos": [],
            "situacao": "vazio",
            "windows": _sonda(),
        }
    )
    assert "Windows também não vê" in resultado["titulo"]
    assert "cabo" in resultado["proximo_passo"]


def test_status_com_usb_generico_nao_culpa_a_depuracao():
    """O bug da 0.61.7: webcam com nome de driver generico virava "o celular"."""
    generico = {"status": "OK", "classe": "USB", "nome": "USB Composite Device", "vid": "", "fabricante": "(Generic USB Hub)"}
    resultado = C.resumo(
        {
            "ferramentas": {"completo": True, "adb": "a", "scrcpy": "s"},
            "executado": True,
            "codigo": 0,
            "aparelhos": [],
            "situacao": "vazio",
            "windows": _sonda(genericos=[generico]),
        }
    )
    assert "não é o celular" in resultado["titulo"]
    assert "nenhum é o celular" in resultado["proximo_passo"]
    assert "eu comparo" in resultado["proximo_passo"]  # 0.61.7: sem pedir anotação
    assert "VID" not in resultado["titulo"]


def test_status_com_samsung_de_verdade_manda_ligar_depuracao():
    samsung = {"status": "OK", "classe": "USB", "nome": "SAMSUNG Mobile USB Composite Device", "vid": "04e8"}
    resultado = C.resumo(
        {
            "ferramentas": {"completo": True, "adb": "a", "scrcpy": "s"},
            "executado": True,
            "codigo": 0,
            "aparelhos": [],
            "situacao": "vazio",
            "windows": _sonda([samsung]),
        }
    )
    assert "Depuração USB" in resultado["titulo"]
    assert "04E8" in resultado["resposta"]


def test_vid_da_samsung_desempatou_nome_generico():
    """VID vem do hardware: nao depende do driver instalado."""
    assert C.e_aparelho({"nome": "USB Composite Device", "vid": "04e8"}) is True
    assert C.e_aparelho({"nome": "USB Composite Device", "vid": "1bcf"}) is False
    assert C.e_aparelho({"nome": "USB Composite Device", "vid": "", "fabricante": "Samsung Electronics"}) is True
    assert C.e_aparelho({"nome": "MTP", "vid": ""}) is True
    assert C.e_aparelho({"nome": "USB Composite Device", "vid": ""}) is False


def test_status_sem_cabo_com_driver_ruim_manda_instalar_driver(monkeypatch):
    resultado = C.resumo(
        {
            "ferramentas": {"completo": True, "adb": "a", "scrcpy": "s"},
            "executado": True,
            "codigo": 0,
            "aparelhos": [],
            "situacao": "vazio",
            "windows": _sonda([{"status": "Error", "classe": "USB", "nome": "SAMSUNG Mobile", "vid": "04e8"}], problema=True),
        }
    )
    assert "driver" in resultado["titulo"].lower()
    assert "Samsung USB Driver" in resultado["proximo_passo"]


def test_status_sem_cabo_mas_windows_vendo_manda_ligar_depuracao():
    resultado = C.resumo(
        {
            "ferramentas": {"completo": True, "adb": "a", "scrcpy": "s"},
            "executado": True,
            "codigo": 0,
            "aparelhos": [],
            "situacao": "vazio",
            "windows": _sonda([{"status": "OK", "classe": "USB", "nome": "SAMSUNG Mobile", "vid": "04e8"}]),
        }
    )
    assert "Depuração USB" in resultado["titulo"]
    assert "celular.plano" in resultado["proximo_passo"]


def test_status_nao_autorizado_explica_o_toque():
    resultado = C.resumo(
        {
            "ferramentas": {"completo": True, "adb": "a", "scrcpy": "s"},
            "executado": True,
            "codigo": 0,
            "aparelhos": [{"serial": "ABC", "estado": "unauthorized"}],
            "situacao": "nao-autorizado",
        }
    )
    assert "não autorizado" in resultado["resposta"]
    assert "Permitir" in resultado["proximo_passo"]


def test_status_quando_o_adb_falha_nao_culpa_a_trava():
    resultado = C.resumo(
        {
            "ferramentas": {"completo": True, "adb": "a", "scrcpy": "s"},
            "executado": True,
            "codigo": 1,
            "motivo": "adb server version (40) doesn't match this client",
            "aparelhos": [],
        }
    )
    assert resultado["situacao"] == "erro-adb"
    assert "adb" in resultado["titulo"].lower()
    assert "JARVIS_HOST_CELULAR" not in resultado["resposta"]


def test_samsung_com_nome_generico_e_driver_faltando():
    """VID 04E8 + nome genérico = Samsung reconhecida sem o driver dela."""
    generico = {"status": "OK", "classe": "USB", "nome": "USB Composite Device", "vid": "04e8"}
    completo = {"status": "OK", "classe": "USB", "nome": "SAMSUNG Mobile USB Composite Device", "vid": "04e8"}
    assert C.sem_driver_samsung([generico]) is True
    assert C.sem_driver_samsung([completo]) is False
    assert C.sem_driver_samsung([]) is False
    assert C.sem_driver_samsung([{"nome": "USB Composite Device", "vid": "1bcf"}]) is False

    resultado = C.resumo(
        {
            "ferramentas": {"completo": True, "adb": "a", "scrcpy": "s"},
            "executado": True,
            "codigo": 0,
            "aparelhos": [],
            "situacao": "vazio",
            "windows": _sonda([generico]),
        }
    )
    assert "driver" in resultado["titulo"].lower()
    assert "Samsung USB Driver" in resultado["proximo_passo"]
    assert "VID_04E8" in resultado["proximo_passo"]
    assert C._plano_vazio(_sonda([generico]))[0]["titulo"].startswith("1. Reconhecido")


def test_lista_da_usb_marca_quem_e_celular():
    sonda = _sonda(
        [{"status": "OK", "classe": "USB", "nome": "SAMSUNG Mobile", "vid": "04e8"}],
        [{"status": "OK", "classe": "USB", "nome": "USB Composite Device", "vid": ""}],
    )
    texto = C._linhas_da_usb(sonda)
    linhas = texto.splitlines()
    assert "celular" in linhas[0]
    assert "não é Samsung" in linhas[1]
    assert "VID_04E8" in linhas[0]


def test_status_mostra_a_lista_com_vid_no_chat(monkeypatch):
    from server import skill_registry

    sonda = _sonda([{"status": "OK", "classe": "USB", "nome": "SAMSUNG Mobile", "vid": "04e8"}])
    medido = {
        "ferramentas": {"completo": True, "adb": "a", "scrcpy": "s"},
        "executado": True,
        "codigo": 0,
        "aparelhos": [],
        "situacao": "vazio",
        "windows": sonda,
    }
    monkeypatch.setattr(skill_registry.celular, "estado", lambda **_k: medido)
    import asyncio

    resultado = asyncio.run(skill_registry.build_registry(Path("/tmp/vid") / "files").execute("celular.status", {}, False))
    assert "VID_04E8" in resultado["resposta"]
    assert "celular" in resultado["resposta"]


# --- 0.61.7: a porta viu algo / a lista não mudou ---------------------------

DESCONHECIDO = {
    "status": "Error",
    "classe": "USB",
    "nome": "Dispositivo USB desconhecido (Falha na solicitação do descritor)",
    "instance": "USB\\VID_0000&PID_0000\\5&2A0F",
    "vid": "0000",
    "fabricante": "(Standard USB Host Controller)",
    "problema": "CM_PROB_FAILED_START",
}


def test_limpar_sonda_le_o_codigo_do_problema():
    itens = C._limpar_sonda(
        ["Error\tUSB\tDispositivo USB desconhecido\tUSB\\VID_0000&PID_0000\\1\t(Generic)\tCM_PROB_FAILED_START",
         "OK\tUSB\tUSB Root Hub\tUSB\\ROOT_HUB30\\2\t(Generic)\tCM_PROB_NONE"]
    )
    assert itens[0]["problema"] == "CM_PROB_FAILED_START"
    assert itens[1]["problema"] == ""  # "sem problema" não é problema
    assert itens[0]["vid"] == "0000"


def test_sonda_nao_descarta_a_lista_depois_de_dez_itens():
    """O teto antigo de 10 escondia justamente o que mudou entre duas checagens."""
    linhas = [f"OK\tUSB\tHub {i}\tUSB\\HUB{i}\\1\t(Generic)\tCM_PROB_NONE" for i in range(14)]
    assert len(C._limpar_sonda(linhas)) == 14


def test_identifica_o_dispositivo_que_o_windows_nao_conseguiu_ler():
    assert C.e_desconhecido(DESCONHECIDO) is True
    assert C.e_desconhecido({"nome": "Unknown USB Device (Device Descriptor Request Failed)"}) is True
    assert C.e_desconhecido({"nome": "USB Composite Device"}) is False
    assert C.e_desconhecido({"nome": "USB Root Hub"}) is False


def test_sonda_com_desconhecido_nao_culpa_driver_nem_depuracao(monkeypatch, raiz):
    monkeypatch.setattr(C.os, "name", "nt")
    monkeypatch.setattr(C.sys, "platform", "win32")
    linha = (
        "Error\tUSB\tDispositivo USB desconhecido (Falha na solicitação do descritor)\t"
        "USB\\VID_0000&PID_0000\\5&2A0F\t(Standard)\tCM_PROB_FAILED_START"
    )
    resultado = C.windows_ve(rodar=lambda _argumentos: (0, linha + "\n", ""))

    assert resultado["desconhecidos"] and not resultado["telefones"]
    assert "NÃO conseguiu identificar" in resultado["resumo"]
    assert "cabo só de carga" in resultado["resumo"]


def test_comparacao_guarda_a_primeira_lista(raiz):
    sonda = {"dispositivos": [{"nome": "USB Root Hub", "instance": "USB\\ROOT_HUB\\1", "vid": ""}]}
    comparacao = C.comparar_com_ultima(sonda)

    assert comparacao["primeira"] is True
    assert "Guarda" in comparacao["frase"] or "Guardei" in comparacao["frase"]
    guardado = C._ler_ultima_sonda()
    assert guardado["dispositivos"][0]["nome"] == "USB Root Hub"


def test_comparacao_ve_que_a_lista_nao_mudou(raiz):
    sonda = {"dispositivos": [{"nome": "USB Root Hub", "instance": "USB\\ROOT_HUB\\1", "vid": ""}]}
    C.comparar_com_ultima(sonda)
    segunda = C.comparar_com_ultima(sonda)

    assert segunda["primeira"] is False
    assert segunda["mudou"] is False
    assert "idêntica" in segunda["frase"]
    assert "não viu nada novo" in segunda["frase"]


def test_comparacao_mostra_o_que_entrou_e_o_que_saiu(raiz):
    hub = {"nome": "USB Root Hub", "instance": "USB\\ROOT_HUB\\1", "vid": ""}
    celular = {"nome": "SAMSUNG Mobile USB Composite Device", "instance": "USB\\VID_04E8&PID_6860\\ABC", "vid": "04e8"}
    C.comparar_com_ultima({"dispositivos": [hub]})

    entrou = C.comparar_com_ultima({"dispositivos": [hub, celular]})
    assert entrou["mudou"] is True
    assert entrou["novos"][0]["vid"] == "04e8"
    assert "entrou" in entrou["frase"] and "SAMSUNG" in entrou["frase"]

    saiu = C.comparar_com_ultima({"dispositivos": [hub]})
    assert saiu["mudou"] is True
    assert "saiu" in saiu["frase"]


def test_comparacao_sobrevive_a_arquivo_corrompido(raiz):
    arquivo = C._arquivo_da_sonda()
    arquivo.parent.mkdir(parents=True, exist_ok=True)
    arquivo.write_text("{isto não é json", encoding="utf-8")

    comparacao = C.comparar_com_ultima({"dispositivos": []})
    assert comparacao["primeira"] is True


def test_plano_comeca_pelo_fisico_quando_a_porta_viu_algo_mas_nao_identificou():
    plano = C._plano_vazio(_sonda(desconhecidos=[DESCONHECIDO]))
    primeiro = plano[0]

    assert "não conversou" in primeiro["titulo"]
    assert any("cabo" in comando for comando in primeiro["comandos"])
    assert "Depuração USB não mudam nada" in primeiro["nota"]


def test_plano_diz_que_a_lista_esta_identica_quando_nada_mudou():
    generico = {"status": "OK", "classe": "USB", "nome": "USB Mass Storage Device", "vid": "058f"}
    comparacao = {
        "primeira": False,
        "mudou": False,
        "novos": [],
        "saidos": [],
        "quando": "2026-10-28T21:38:00",
        "frase": "idêntica",
    }
    plano = C._plano_vazio(_sonda(genericos=[generico], comparacao=comparacao))

    assert "idêntica" in plano[0]["titulo"]
    assert "21:38" in plano[0]["titulo"]


def test_status_mostra_a_comparacao_no_chat(ligado, monkeypatch):
    adb = ligado / "adb.exe"
    adb.write_text("x", encoding="utf-8")
    monkeypatch.setattr(C, "ferramentas", lambda: {"adb": str(adb), "scrcpy": "x", "completo": True})
    monkeypatch.setenv("JARVIS_HOST_CELULAR", "1")

    def sonda(rodar=None):
        return {
            "consulta": True,
            "dispositivos": [],
            "telefones": [],
            "genericos": [],
            "desconhecidos": [],
            "visivel": False,
            "com_problema": False,
            "resumo": "O Windows não vê nenhum aparelho na USB.",
        }

    monkeypatch.setattr(C, "windows_ve", sonda)
    medido = C.estado(rodar=lambda _argumentos: (0, "List of devices attached\n\n", ""))
    assert medido["windows"]["comparacao"]["primeira"] is True

    resposta = C.resumo(medido)
    assert "Guarda" in resposta["resposta"] or "Guardei" in resposta["resposta"]


def test_nome_do_desconhecido_nao_gasta_a_linha_com_o_parenteses():
    assert C._descrever(DESCONHECIDO) == "Dispositivo USB desconhecido"


def test_codigo_do_windows_vira_palavra_que_se_entende():
    linha = C._linhas_da_usb({"dispositivos": [DESCONHECIDO]})
    assert "driver não iniciou" in linha
    assert "CM_PROB_FAILED_START" not in linha
    assert "VID_0000" not in linha
    assert "não identificado" in linha


def test_comparacao_avisa_quando_o_que_entrou_e_o_desconhecido(raiz):
    hub = {"nome": "USB Root Hub", "instance": "USB\\ROOT_HUB\\1", "vid": ""}
    C.comparar_com_ultima({"dispositivos": [hub]})
    comparacao = C.comparar_com_ultima({"dispositivos": [hub, DESCONHECIDO]})

    assert "não identificou o que era" in comparacao["frase"]
    assert "cabo" in comparacao["frase"]


def test_comparacao_avisa_quando_o_celular_apareceu(raiz):
    hub = {"nome": "USB Root Hub", "instance": "USB\\ROOT_HUB\\1", "vid": ""}
    celular = {"nome": "SAMSUNG Mobile USB Composite Device", "instance": "USB\\VID_04E8&PID_6860\\A", "vid": "04e8"}
    C.comparar_com_ultima({"dispositivos": [hub]})
    comparacao = C.comparar_com_ultima({"dispositivos": [hub, celular]})

    assert "O celular apareceu na USB" in comparacao["frase"]


# --- 0.61.7: a rede local responde "dá para acessar pelo Wi-Fi?" -------------

ARP_WINDOWS = """
Interface: 192.168.0.10 --- 0x6
  Internet Address      Physical Address      Type
  192.168.0.1           b0-4e-26-11-22-33     dynamic
  192.168.0.12          8c-77-12-aa-bb-cc     dynamic
  192.168.0.50          00-11-22-33-44-55     dynamic
  192.168.1.7           aa-bb-cc-dd-ee-ff     dynamic
"""


def test_le_a_tabela_arp_do_windows_e_do_linux():
    iphone = C._ler_arp(ARP_WINDOWS)
    assert iphone["192.168.0.12"] == "8c:77:12:aa:bb:cc"

    linux = "192.168.0.12     0x1   0x2    8c:77:12:aa:bb:cc     *        eth0"
    assert C._ler_arp(linux)["192.168.0.12"] == "8c:77:12:aa:bb:cc"


def test_marca_prefixo_samsung_sem_afirmar_o_que_nao_sabe():
    assert C._fabricante_do_mac("8c:77:12:aa:bb:cc") == "prefixo Samsung"
    assert C._fabricante_do_mac("00:11:22:33:44:55") == ""


def test_rede_recusa_quando_a_camada_esta_desligada(raiz):
    medido = C.rede(rodar=lambda _a: (0, ARP_WINDOWS, ""), tocar=lambda _p: None, ip_local="192.168.0.10")
    assert medido["executado"] is False
    assert "desligado" in medido["motivo"]
    resposta = C.resumo_da_rede(medido)
    assert resposta["titulo"] == "Não deu para olhar a rede"


def test_rede_so_olha_a_propria_faixa_e_nao_a_si_mesma(ligado, monkeypatch):
    monkeypatch.setattr(C, "_portas_abertas", lambda hosts: {ip: [] for ip in hosts})
    monkeypatch.setattr(C, "_gethostbyaddr", lambda ip: "Galaxy-J7" if ip.endswith(".12") else "")
    medido = C.rede(
        rodar=lambda _a: (0, ARP_WINDOWS, ""),
        tocar=lambda _p: None,
        ip_local="192.168.0.10",
    )

    assert medido["executado"] is True
    assert medido["rede"] == "192.168.0.0/24"
    ips = [host["ip"] for host in medido["hosts"]]
    assert "192.168.1.7" not in ips          # outra faixa
    assert "192.168.0.10" not in ips         # o próprio PC
    assert ips == ["192.168.0.1", "192.168.0.12", "192.168.0.50"]  # ordem numérica
    assert medido["hosts"][1]["nome"] == "Galaxy-J7"


def _medido_rede(hosts, com_adb=()):
    return {"executado": True, "pc": "192.168.0.10", "rede": "192.168.0.0/24", "hosts": hosts, "com_adb": list(com_adb)}


def test_rede_sem_porta_aberta_explica_que_wifi_nao_substitui_o_cabo():
    host = {"ip": "192.168.0.12", "mac": "8c:77:12:aa:bb:cc", "nome": "Galaxy-J7", "fabricante": "prefixo Samsung", "portas": [], "servicos": []}
    resposta = C.resumo_da_rede(_medido_rede([host]))

    assert resposta["titulo"] == "A rede não dá acesso ao celular"
    assert "adb tcpip 5555" in resposta["resposta"]
    assert "não substitui o cabo" in resposta["resposta"]
    assert "derrubar o Wi-Fi" in resposta["resposta"].lower() or "Derrubar o Wi-Fi" in resposta["resposta"]


def test_rede_com_5555_aberta_manda_conectar():
    host = {"ip": "192.168.0.12", "mac": "8c:77:12:aa:bb:cc", "nome": "Galaxy-J7", "fabricante": "prefixo Samsung", "portas": [5555], "servicos": ["adb sem fio"]}
    resposta = C.resumo_da_rede(_medido_rede([host], com_adb=[host]))

    assert "adb por rede" in resposta["titulo"]
    assert "adb connect 192.168.0.12:5555" in resposta["resposta"]


def test_rede_sem_ninguem_aponta_wifi_de_visitante():
    resposta = C.resumo_da_rede(_medido_rede([]))
    assert resposta["titulo"] == "Ninguém respondeu na rede"
    assert "mesmo Wi-Fi" in resposta["proximo_passo"]


def test_rede_lista_porta_com_nome_do_servico():
    host = {"ip": "192.168.0.20", "mac": "aa:bb:cc:dd:ee:ff", "nome": "", "fabricante": "", "portas": [8080, 9000], "servicos": ["servidor HTTP de app", "servidor de app"]}
    resposta = C.resumo_da_rede(_medido_rede([host]))
    assert "8080 (servidor HTTP de app)" in resposta["resposta"]


def test_a_skill_de_rede_esta_no_registro(tmp_path):
    from server.skill_registry import build_registry

    registro = build_registry(tmp_path)
    definicao = registro.get("celular.rede")
    assert definicao is not None
    # só leitura: não pede confirmação nem declara efeito colateral
    assert getattr(definicao, "requires_confirmation", False) is False


# --- 0.61.7: o que apareceu na varredura de casa -----------------------------

ARP_DA_CASA = """
Interface: 192.168.15.8 --- 0x4
  Internet Address      Physical Address      Type
  192.168.15.1          2c-4d-54-11-22-33     dynamic
  192.168.15.5          00-11-22-33-44-55     dynamic
  192.168.15.12         3c-5a-37-aa-bb-cc     dynamic
  192.168.15.22         8c-77-12-dd-ee-ff     dynamic
  192.168.15.255        ff-ff-ff-ff-ff-ff     static
  192.168.15.0          01-00-5e-00-00-fb     static
"""


def test_broadcast_e_endereco_de_rede_nao_sao_dispositivos():
    """A 0.61.7 listava `192.168.15.255` como "dispositivo que respondeu"."""
    assert C._endereco_de_dispositivo("192.168.15.22", "8c:77:12:dd:ee:ff") is True
    assert C._endereco_de_dispositivo("192.168.15.255", "ff:ff:ff:ff:ff:ff") is False
    assert C._endereco_de_dispositivo("192.168.15.0", "01:00:5e:00:00:fb") is False
    assert C._endereco_de_dispositivo("224.0.0.1", "01:00:5e:00:00:01") is False


def test_nome_que_e_o_proprio_ip_nao_e_nome():
    """`gethostbyaddr` devolve o IP quando não resolve — a linha saía repetida."""
    assert C._nome_util("192.168.15.12", "192.168.15.12") == ""
    assert C._nome_util("192.168.15.12", "") == ""
    assert C._nome_util("192.168.15.22", "A34") == "A34"


def test_a_varredura_da_casa_mostra_mac_e_nao_conta_broadcast(ligado, monkeypatch):
    monkeypatch.setattr(C, "_portas_abertas", lambda hosts: {ip: [] for ip in hosts})

    def nome(ip):
        return "192.168.15.12" if ip.endswith(".12") else ("A34" if ip.endswith(".22") else "")

    monkeypatch.setattr(C, "_gethostbyaddr", nome)
    medido = C.rede(rodar=lambda _a: (0, ARP_DA_CASA, ""), tocar=lambda _p: None, ip_local="192.168.15.8")

    ips = [host["ip"] for host in medido["hosts"]]
    assert ips == ["192.168.15.1", "192.168.15.5", "192.168.15.12", "192.168.15.22"]
    nomes = {host["ip"]: host["nome"] for host in medido["hosts"]}
    assert nomes["192.168.15.12"] == ""
    assert nomes["192.168.15.22"] == "A34"

    resposta = C.resumo_da_rede(medido)
    assert "8c:77:12:dd:ee:ff" in resposta["resposta"]
    assert "[prefixo Samsung]" in resposta["resposta"]
    assert ".255" not in resposta["resposta"]
    assert "192.168.15.12 192.168.15.12" not in resposta["resposta"]


def test_a_frase_dos_aparelhos_na_rede_chega_na_skill(tmp_path):
    """"quais dispositivos estão na rede local" ficou presa em 0,47 na 0.61.7."""
    from server.agente_local import entrada_de_skill, pesquisar
    from server.skill_registry import build_registry

    registro = build_registry(tmp_path)
    entradas = [entrada_de_skill(item) for item in registro.list()]
    for frase in (
        "quais dispositivos estao na rede local",
        "quais aparelhos estao conectados no wifi",
        "da para acessar o celular pelo wifi sem cabo",
    ):
        ranking = pesquisar(frase, entradas)
        assert ranking[0]["entrada"].skill_id == "celular.rede", frase
        assert ranking[0]["score"] >= 0.5, (frase, ranking[0]["score"])
    # e o pedido de status continua indo para a skill de status
    assert pesquisar("status do celular", entradas)[0]["entrada"].skill_id == "celular.status"


# --- 0.61.7: o A34 provou a porta; o J7 não apareceu -------------------------

A34 = "OK\tUSB\tUSB Composite Device\tUSB\\VID_04E8&PID_6860\\R58M9\tSamsung Electronics Co., Ltd.\tCM_PROB_NONE\tSM-A346B"
J7 = "OK\tUSB\tUSB Composite Device\tUSB\\VID_04E8&PID_6860\\R28M1\tSamsung Electronics Co., Ltd.\tCM_PROB_NONE\tSM-G610M"


def test_a_sonda_le_o_modelo_do_aparelho():
    itens = C._limpar_sonda([A34, J7])
    assert [item["modelo"] for item in itens] == ["SM-A346B", "SM-G610M"]


def test_modelo_de_outro_fabricante_nao_e_apresentado_como_modelo():
    """O mesmo campo traz caminho interno do Windows em webcam/hub."""
    itens = C._limpar_sonda(
        ["OK\tUSB\tWebcam\tUSB\\VID_046D&PID_0825\\A\tLogitech\tCM_PROB_NONE\t\\Device\\USBPDO-3",
         "OK\tUSB\tLeitor\tUSB\\VID_046D&PID_0825\\B\tLogitech\tCM_PROB_NONE\tSM-A346B"]
    )
    assert itens[0]["modelo"] == ""   # caminho interno do Windows
    assert itens[1]["modelo"] == ""   # modelo de Samsung em aparelho de outra marca


def test_o_modelo_aparece_na_linha_do_chat():
    itens = C._limpar_sonda([A34])
    linha = C._linhas_da_usb({"dispositivos": itens})
    assert "SM-A346B" in linha
    assert "celular" in linha


def test_o_que_ja_apareceu_fica_guardado(ligado):
    itens = C._limpar_sonda([A34])
    C.registrar_aparelhos(itens)

    vistos = C.aparelhos_ja_vistos()
    assert vistos[0]["modelo"] == "SM-A346B"
    assert "porta já viu um Samsung" in C._frase_do_que_ja_passou()
    assert "SM-A346B" in C._frase_do_que_ja_passou()


def test_memoria_so_conta_samsung(ligado):
    generico = C._limpar_sonda(
        ["OK\tUSB\tUSB Mass Storage Device\tUSB\\VID_058F&PID_6366\\X\tAlcor\tCM_PROB_NONE\t"]
    )
    C.registrar_aparelhos(generico)
    assert C.aparelhos_ja_vistos() == []
    assert C._frase_do_que_ja_passou() == ""


def test_nada_aparecendo_depois_do_a34_nao_culpa_o_pc(ligado, monkeypatch):
    """O caso real: A34 entrou, J7 (cabo só-carga) não entrou e a lista ficou igual."""
    C.registrar_aparelhos(C._limpar_sonda([A34]))
    resposta = C.resumo(
        {
            "ferramentas": {"completo": True, "adb": "a", "scrcpy": "s"},
            "executado": True,
            "codigo": 0,
            "aparelhos": [],
            "situacao": "vazio",
            "windows": _sonda(),
        }
    )
    assert resposta["titulo"] == "Nenhum aparelho no adb — e o Windows também não vê"
    assert "porta já viu um Samsung" in resposta["proximo_passo"]
    assert "SM-A346B" in resposta["proximo_passo"]
    assert "cabo de dados ou o conector" in resposta["proximo_passo"]
    # e a tela bloqueada não entra como suspeita
    assert "Tela bloqueada não é causa" in resposta["proximo_passo"]


def test_tela_bloqueada_nao_aparece_como_causa_em_nenhum_texto():
    texto = (RAIZ_TESTE := __import__("pathlib").Path(__file__).resolve().parents[2] / "server" / "celular.py").read_text(encoding="utf-8")
    assert "Tela bloqueada NÃO explica" in texto
    assert "o aparelho aparece na USB" in texto


def test_plano_manda_testar_o_cabo_em_outro_aparelho_igual():
    plano = C._plano_vazio(_sonda())
    comandos = " ".join(plano[0]["comandos"])
    assert "MESMO cabo em outro aparelho" in comandos
    assert "vigiar-usb.bat" in comandos


def test_a_memoria_da_porta_aparece_tambem_quando_ha_dispositivo_generico(ligado):
    C.registrar_aparelhos(C._limpar_sonda([A34]))
    generico = {"status": "OK", "classe": "USB", "nome": "USB Mass Storage Device", "vid": "058f", "modelo": ""}
    resposta = C.resumo(
        {
            "ferramentas": {"completo": True, "adb": "a", "scrcpy": "s"},
            "executado": True,
            "codigo": 0,
            "aparelhos": [],
            "situacao": "vazio",
            "windows": _sonda(genericos=[generico]),
        }
    )
    assert "porta já viu um Samsung" in resposta["proximo_passo"]


# --- 0.61.7: histórico do Windows e vigia atenta -----------------------------

EVENTOS = (
    "09:27:26\t400\tMicrosoft-Windows-Kernel-PnP\tDevice USB\\ROOT_HUB\\1 was configured\n"
    "09:27:31\t20001\tMicrosoft-Windows-UserPnp\tDriver installed for USB Composite Device\n"
    "09:27:33\t441\tMicrosoft-Windows-Kernel-PnP\tDevice USB\\VID_04E8&PID_6860\\R58M9 could not be started\n"
)


def test_le_uma_linha_de_evento_do_log():
    evento = C._linha_de_evento("09:27:33\t441\tMicrosoft-Windows-Kernel-PnP\tDevice falhou")
    assert evento["hora"] == "09:27:33"
    assert evento["codigo"] == "441"
    assert "falhou" in evento["mensagem"]
    assert C._linha_de_evento("linha sem tabulação") is None


def test_historico_recusa_fora_do_windows(ligado):
    medido = C.eventos(rodar=lambda _a: (0, "", ""))
    assert medido["executado"] is False
    assert "Windows" in medido["motivo"]


def _medido_eventos(linhas, minutos=30):
    return {
        "executado": True,
        "minutos": minutos,
        "eventos": [e for e in (C._linha_de_evento(l) for l in linhas) if e],
        "total": len(linhas),
        "com_aparelho": [e for e in (C._linha_de_evento(l) for l in linhas) if e and C._menciona_aparelho(e)],
    }


def test_historico_avisa_quando_o_aparelho_apareceu_mesmo_rapido():
    resposta = C.resumo_de_eventos(_medido_eventos(EVENTOS.splitlines()))
    assert "mesmo que por pouco tempo" in resposta["titulo"]
    assert "menos que o intervalo" in resposta["resposta"]
    assert "vigiar-usb-atento.bat" in resposta["proximo_passo"]


def test_historico_sem_aparelho_reforca_cabo_ou_conector():
    so_pc = [EVENTOS.splitlines()[0], EVENTOS.splitlines()[1]]
    resposta = C.resumo_de_eventos(_medido_eventos(so_pc))
    assert resposta["titulo"] == "Nenhum evento citando o celular"
    assert "cabo" in resposta["proximo_passo"]


def test_historico_vazio_nao_inventa():
    resposta = C.resumo_de_eventos(_medido_eventos([]))
    assert resposta["titulo"] == "Nenhum evento de USB no período"


def test_a_skill_de_historico_esta_no_registro(tmp_path):
    from server.skill_registry import build_registry

    registro = build_registry(tmp_path)
    assert registro.get("celular.eventos") is not None


def test_vigia_atenta_existe_e_olha_mais_rapido():
    from pathlib import Path as _Path

    raiz = _Path(__file__).resolve().parents[2]
    bat = (raiz / "vigiar-usb-atento.bat").read_text(encoding="utf-8", errors="replace")
    assert "vigiar-usb.ps1" in bat
    assert "-Intervalo 400" in bat
    assert "-Minutos 10" in bat


def test_vigia_padrao_aponta_para_o_modo_atento():
    from pathlib import Path as _Path

    raiz = _Path(__file__).resolve().parents[2]
    ps1 = (raiz / "vigiar-usb.ps1").read_text(encoding="utf-8", errors="replace")
    assert "vigiar-usb-atento.bat" in ps1
    assert "500" in ps1 or "400" in ps1


def test_vigia_grava_log_e_diz_onde():
    from pathlib import Path as _Path

    raiz = _Path(__file__).resolve().parents[2]
    ps1 = (raiz / "vigiar-usb.ps1").read_text(encoding="utf-8", errors="replace")
    assert "vigia-" in ps1
    assert "Add-Content" in ps1
    assert "storage\\celular" in ps1
