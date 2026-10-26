"""Testes do `drive_setup` (0.48.0): o JARVIS configurando o Drive sem susto."""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from server import dados, drive_setup, repos


@pytest.fixture(autouse=True)
def limpo(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    for nome in (dados.VARIAVEL, dados.VARIAVEL_BIBLIOTECA, dados.VARIAVEL_REPOS, dados.VARIAVEL_DRIVE):
        monkeypatch.delenv(nome, raising=False)
    monkeypatch.setenv(dados.VARIAVEL, str(tmp_path / "storage"))
    monkeypatch.setattr(drive_setup, "ENV", tmp_path / "storage" / ".env")
    monkeypatch.setattr(drive_setup, "ENV_EXEMPLO", tmp_path / "storage" / ".env.example")
    (tmp_path / "storage" / "biblioteca" / "fontes").mkdir(parents=True)
    (tmp_path / "storage" / "biblioteca" / "fontes" / "livro.json").write_text("{}", encoding="utf-8")
    (tmp_path / "storage" / "repos" / "r").mkdir(parents=True)
    (tmp_path / "storage" / "repos" / "r" / "README.md").write_text("# r", encoding="utf-8")
    (tmp_path / "storage" / "historico.json").write_text("[]", encoding="utf-8")


@pytest.fixture()
def drive(tmp_path: Path) -> Path:
    pasta = tmp_path / "Google Drive" / "Meu Drive"
    pasta.mkdir(parents=True)
    return pasta


def test_estado_sem_drive_nao_inventa_caminho() -> None:
    retrato = drive_setup.estado()
    assert retrato["detectado"] is False
    assert retrato["drive"] == ""
    assert retrato["configurado"] is False
    assert retrato["total_arquivos"] == 2


def test_estado_conta_o_que_esta_no_pc(drive: Path) -> None:
    retrato = drive_setup.estado(drive)
    areas = {item["nome"]: item for item in retrato["areas"]}
    assert retrato["detectado"] is True
    assert areas["biblioteca"]["arquivos"] == 1
    assert areas["repos"]["arquivos"] == 1
    assert areas["biblioteca"]["ja_no_drive"] == 0
    assert areas["biblioteca"]["configurada"] is False
    assert areas["biblioteca"]["destino"].endswith("JARVIS-DADOS/biblioteca")


def test_estado_mostra_o_que_o_env_aponta(drive: Path, tmp_path: Path) -> None:
    drive_setup.ENV.write_text(
        f"{dados.VARIAVEL_BIBLIOTECA}={drive / 'JARVIS-DADOS' / 'biblioteca'}\r\n",
        encoding="utf-8",
    )
    retrato = drive_setup.estado(drive)
    assert retrato["env"]["biblioteca"].endswith("biblioteca")
    assert retrato["env"]["repos"] == ""


def test_planejar_nao_cria_nada(drive: Path, tmp_path: Path) -> None:
    plano = drive_setup.planejar(drive)
    assert plano["modo"] == "usar"
    assert plano["total_arquivos"] == 2
    assert any("copiar 1 arquivos" in passo for passo in plano["passos"])
    assert not (drive / "JARVIS-DADOS").exists()
    assert not drive_setup.ENV.exists()


def test_planejar_sem_drive_recusa_com_instrucao() -> None:
    with pytest.raises(drive_setup.DriveError) as erro:
        drive_setup.planejar()
    assert "Google Drive" in str(erro.value)


def test_aplicar_copia_e_grava_o_env_em_crlf(drive: Path, tmp_path: Path) -> None:
    resultado = drive_setup.aplicar(drive, ao_vivo=False)
    assert resultado["modo"] == "usar"
    assert resultado["copiados"] == 2
    assert (drive / "JARVIS-DADOS" / "biblioteca" / "fontes" / "livro.json").is_file()
    assert (drive / "JARVIS-DADOS" / "repos" / "r" / "README.md").is_file()
    bruto = drive_setup.ENV.read_bytes()
    assert bruto.count(b"\n") == bruto.count(b"\r\n")
    assert b"JARVIS_BIBLIOTECA=" in bruto and b"JARVIS_REPOS=" in bruto


def test_aplicar_nao_leva_o_estado_do_agente(drive: Path, tmp_path: Path) -> None:
    drive_setup.aplicar(drive, ao_vivo=False)
    base = drive / "JARVIS-DADOS"
    assert not (base / "historico.json").exists()
    assert (tmp_path / "storage" / "historico.json").is_file()


def test_aplicar_nao_apaga_a_origem(drive: Path, tmp_path: Path) -> None:
    drive_setup.aplicar(drive, ao_vivo=False)
    assert (tmp_path / "storage" / "biblioteca" / "fontes" / "livro.json").is_file()
    assert (tmp_path / "storage" / "repos" / "r" / "README.md").is_file()


def test_aplicar_preserva_o_resto_do_env(drive: Path) -> None:
    drive_setup.ENV.write_text("JARVIS_HOST_REDE=0\r\nJARVIS_DADOS=\r\n", encoding="utf-8")
    drive_setup.aplicar(drive, ao_vivo=False)
    texto = drive_setup.ENV.read_text(encoding="utf-8")
    assert "JARVIS_HOST_REDE=0" in texto
    assert "JARVIS_DADOS=" in texto


def test_aplicar_duas_vezes_nao_duplica_linha(drive: Path) -> None:
    drive_setup.aplicar(drive, ao_vivo=False)
    # segunda vez: as variáveis ainda não estão no ambiente, mas o .env já aponta
    drive_setup.aplicar(drive, ao_vivo=False)
    texto = drive_setup.ENV.read_text(encoding="utf-8")
    assert texto.count("JARVIS_BIBLIOTECA=") == 1
    assert texto.count("JARVIS_REPOS=") == 1


def test_aplicar_sem_drive_recusa(drive: Path) -> None:
    with pytest.raises(drive_setup.DriveError):
        drive_setup.aplicar(None, ao_vivo=False)


def test_aplicar_area_vazia_so_aponta(drive: Path, tmp_path: Path) -> None:
    import shutil

    shutil.rmtree(tmp_path / "storage" / "biblioteca")
    resultado = drive_setup.aplicar(drive, ao_vivo=False)
    situacoes = {item["nome"]: item["situacao"] for item in resultado["areas"]}
    assert situacoes["biblioteca"] == "vazia: só apontada"
    assert (drive / "JARVIS-DADOS" / "biblioteca").is_dir()


def test_desfazer_tira_as_linhas_e_nao_apaga_arquivo(drive: Path) -> None:
    drive_setup.aplicar(drive, ao_vivo=False)
    copiado = drive / "JARVIS-DADOS" / "biblioteca" / "fontes" / "livro.json"
    resultado = drive_setup.aplicar(drive, modo="desfazer", ao_vivo=False)
    assert resultado["alterou_env"] is True
    texto = drive_setup.ENV.read_text(encoding="utf-8")
    assert "JARVIS_BIBLIOTECA=" not in texto
    assert copiado.is_file()


def test_aplicar_ao_vivo_troca_o_caminho_nesta_sessao(drive: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    antes = dict(os.environ)
    original = (repos.PASTA_REPOS, repos.INDICE)
    try:
        drive_setup.aplicar(drive, ao_vivo=True)
        assert dados.biblioteca() == drive / "JARVIS-DADOS" / "biblioteca"
        assert repos.PASTA_REPOS == drive / "JARVIS-DADOS" / "repos"
    finally:
        os.environ.clear()
        os.environ.update(antes)
        repos.PASTA_REPOS, repos.INDICE = original


# --------------------------------------------------- limite de banda (0.48.0)

class RegistroFalso:
    """Imita o `winreg` sem tocar em registro nenhum."""

    def __init__(self, valores: dict[str, int] | None = None) -> None:
        self.valores = dict(valores or {})
        self.gravados: list[tuple[str, int]] = []
        self.apagados: list[str] = []

    def ler(self, nome: str) -> int | None:
        return self.valores.get(nome)

    def gravar(self, nome: str, valor: int) -> None:
        self.valores[nome] = valor
        self.gravados.append((nome, valor))

    def apagar(self, nome: str) -> None:
        self.valores.pop(nome, None)
        self.apagados.append(nome)


def test_banda_sem_registro_nao_quebra() -> None:
    retrato = drive_setup.banda()
    assert retrato["suportado"] is False
    assert "Windows" in retrato["motivo"]


def test_aplicar_banda_grava_os_dois_valores() -> None:
    reg = RegistroFalso()
    resultado = drive_setup.aplicar_banda(1000, 500, simulado=reg)
    assert reg.valores == {"BandwidthRxKBPS": 1000, "BandwidthTxKBPS": 500}
    assert resultado["depois"] == {"download_kbps": 1000, "upload_kbps": 500}
    assert resultado["antes"] == {"download_kbps": 0, "upload_kbps": 0}
    assert "HKEY_CURRENT_USER" in resultado["chave"]


def test_aplicar_banda_zero_remove_o_limite() -> None:
    reg = RegistroFalso({"BandwidthRxKBPS": 1000, "BandwidthTxKBPS": 500})
    resultado = drive_setup.aplicar_banda(0, 0, simulado=reg)
    assert reg.valores == {}
    assert resultado["depois"] == {"download_kbps": 0, "upload_kbps": 0}
    assert "Limite removido" in resultado["mensagem"]


def test_aplicar_banda_recusa_valor_absurdo() -> None:
    reg = RegistroFalso()
    with pytest.raises(drive_setup.DriveError):
        drive_setup.aplicar_banda(200_000_000, 500, simulado=reg)
    with pytest.raises(drive_setup.DriveError):
        drive_setup.aplicar_banda(-1, 500, simulado=reg)
    assert reg.gravados == []


def test_aplicar_banda_recusa_texto() -> None:
    reg = RegistroFalso()
    with pytest.raises(drive_setup.DriveError):
        drive_setup.aplicar_banda("1000", 500, simulado=reg)  # type: ignore[arg-type]


def test_planejar_banda_nao_grava() -> None:
    reg = RegistroFalso({"BandwidthRxKBPS": 2000})
    plano = drive_setup.planejar_banda(1000, 500, simulado=reg)
    assert plano["planejado"] is True
    assert plano["antes"]["download_kbps"] == 2000
    assert plano["depois"] == {"download_kbps": 1000, "upload_kbps": 500}
    assert reg.gravados == []


def test_banda_mostra_o_que_ja_estava_gravado() -> None:
    retrato = drive_setup.banda(RegistroFalso({"BandwidthRxKBPS": 800}))
    assert retrato["download_kbps"] == 800
    assert retrato["upload_kbps"] == 0
    assert retrato["limitado"] is True


# ------------------------------------------------------ o Drive ainda está lá?

def test_estado_avisa_quando_a_pasta_do_drive_sumiu(drive: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    sumida = tmp_path / "Google Drive" / "JARVIS-DADOS" / "biblioteca"
    monkeypatch.setenv(dados.VARIAVEL_BIBLIOTECA, str(sumida))
    retrato = drive_setup.estado(drive, processos=["chrome.exe"])
    assert any("não está lá agora" in aviso for aviso in retrato["avisos"])


def test_estado_avisa_quando_sobrou_arquivo_na_pasta_antiga(drive: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    drive_setup.aplicar(drive, ao_vivo=False)
    monkeypatch.setenv(dados.VARIAVEL_BIBLIOTECA, str(drive / "JARVIS-DADOS" / "biblioteca"))
    retrato = drive_setup.estado(drive)
    assert any("Sobraram 1 arquivo" in aviso for aviso in retrato["avisos"])


def test_estado_sem_problema_nao_inventa_aviso(
    drive: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    import shutil

    # a pasta local antiga é a do JARVIS_DADOS do teste, nunca a do projeto
    shutil.rmtree(tmp_path / "storage" / "biblioteca", ignore_errors=True)
    monkeypatch.setenv(dados.VARIAVEL_BIBLIOTECA, str(drive / "JARVIS-DADOS" / "biblioteca"))
    (drive / "JARVIS-DADOS" / "biblioteca" / "fontes").mkdir(parents=True, exist_ok=True)
    (drive / "JARVIS-DADOS" / "biblioteca" / "fontes" / "a.json").write_text("{}", encoding="utf-8")
    retrato = drive_setup.estado(drive)
    assert retrato["avisos"] == []


def test_drive_aberto_reconhece_o_processo() -> None:
    assert drive_setup.drive_aberto(["chrome.exe", "googledrivefs.exe"]) is True
    assert drive_setup.drive_aberto(["chrome.exe"]) is False


# ------------------------------------- abrir/fechar o app (0.48.0) no Windows

def test_fechar_exige_windows(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(drive_setup.os, "name", "posix")
    with pytest.raises(drive_setup.DriveError):
        drive_setup.fechar(confirmar=True)


def test_fechar_sem_confirmar_so_avisa(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(drive_setup.os, "name", "nt")
    chamadas: list[list[str]] = []
    resultado = drive_setup.fechar(
        processos=["googledrivefs.exe"], correr=lambda cmd, **_: chamadas.append(cmd) or (0, ""), confirmar=False
    )
    assert resultado["vai_fechar"] is True
    assert "G:" in resultado["aviso"]
    assert chamadas == []


def test_fechar_mata_so_o_processo_do_drive(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(drive_setup.os, "name", "nt")
    chamadas: list[list[str]] = []
    lista = ["googledrivefs.exe"]

    def correr(cmd, **_):
        chamadas.append(cmd)
        lista.clear()  # simula o processo morrendo
        return 0, ""

    resultado = drive_setup.fechar(processos=lista, correr=correr, confirmar=True)
    assert chamadas and chamadas[0][0] == "taskkill"
    assert "GoogleDriveFS.exe" in chamadas[0]
    assert "/F" in chamadas[0]
    assert resultado["fechado"] is True


def test_fechar_quando_ja_esta_fechado_nao_roda_nada(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(drive_setup.os, "name", "nt")
    chamadas: list[list[str]] = []
    resultado = drive_setup.fechar(
        processos=["chrome.exe"], correr=lambda cmd, **_: chamadas.append(cmd) or (0, ""), confirmar=True
    )
    assert resultado["ja_estava"] is True
    assert chamadas == []


def test_achar_executavel_pega_a_versao_mais_nova(tmp_path: Path) -> None:
    for versao in ("110.0.3.0", "109.0.2.0", "111.0.1.0"):
        pasta = tmp_path / versao
        pasta.mkdir()
        (pasta / "GoogleDriveFS.exe").write_text("x", encoding="utf-8")
    achado = drive_setup.achar_executavel([tmp_path])
    assert achado is not None
    assert achado.parent.name == "111.0.1.0"


def test_achar_executavel_sem_pasta_devolve_none(tmp_path: Path) -> None:
    assert drive_setup.achar_executavel([tmp_path / "nao-existe"]) is None


def test_abrir_usa_o_executavel_encontrado(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(drive_setup.os, "name", "nt")
    monkeypatch.setattr(drive_setup, "drive_aberto", lambda *_: False)
    pasta = tmp_path / "112.0.0.0"
    pasta.mkdir()
    exe = pasta / "GoogleDriveFS.exe"
    exe.write_text("x", encoding="utf-8")
    chamadas: list[tuple[list[str], bool]] = []

    def correr(cmd, escondido=False):
        chamadas.append((cmd, escondido))
        return 0, ""

    resultado = drive_setup.abrir(correr=correr, raizes=[tmp_path])
    assert chamadas == [([str(exe)], True)]
    assert resultado["aberto"] is True
    assert "G:" in resultado["mensagem"]


def test_abrir_sem_executavel_explica(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(drive_setup.os, "name", "nt")
    monkeypatch.setattr(drive_setup, "drive_aberto", lambda *_: False)
    with pytest.raises(drive_setup.DriveError) as erro:
        drive_setup.abrir(correr=lambda *a, **k: (0, ""), raizes=[tmp_path])
    assert "menu Iniciar" in str(erro.value)


def test_abrir_quando_ja_aberto_nao_roda_nada(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(drive_setup.os, "name", "nt")
    monkeypatch.setattr(drive_setup, "drive_aberto", lambda *_: True)
    chamadas: list[Any] = []
    resultado = drive_setup.abrir(correr=lambda *a, **k: chamadas.append(a), raizes=[])
    assert resultado["ja_estava"] is True
    assert chamadas == []
