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
