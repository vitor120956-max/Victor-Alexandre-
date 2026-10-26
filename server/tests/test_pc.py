"""Testes da camada do PC — nada aqui abre programa de verdade."""
from __future__ import annotations

from pathlib import Path

import pytest

from server import pc


@pytest.fixture(autouse=True)
def _ligado(monkeypatch):
    monkeypatch.setenv(pc.AMBIENTE, "1")
    monkeypatch.setattr(pc.sys, "platform", "win32")


def test_programas_lista_sem_executar(monkeypatch):
    monkeypatch.delenv(pc.AMBIENTE, raising=False)
    lista = pc.programas()
    assert lista["ligado"] is False
    assert {item["nome"] for item in lista["programas"]} >= {"notepad", "calc", "cmd", "powershell"}
    assert {item["nome"] for item in lista["comandos"]} >= {"ip", "sistema", "processos"}


def test_abrir_programa_resolve_apelido():
    chamados: list[str] = []
    resultado = pc.abrir_programa("bloco de notas", abrir=chamados.append)
    assert chamados == ["notepad.exe"]
    assert resultado["programa"] == "notepad"
    assert "Bloco de notas" in resultado["resposta"]


def test_abrir_programa_recusa_fora_da_lista():
    with pytest.raises(pc.PcError) as erro:
        pc.abrir_programa("meu programa secreto", abrir=lambda exe: None)
    assert "notepad" in str(erro.value)


def test_abrir_programa_sem_o_windows_recusa(monkeypatch):
    monkeypatch.setattr(pc.sys, "platform", "linux")
    with pytest.raises(pc.PcError):
        pc.abrir_programa("notepad", abrir=lambda exe: None)


def test_abrir_programa_com_executavel_ausente():
    def abrir(exe: str) -> None:
        raise FileNotFoundError(exe)

    with pytest.raises(pc.PcError):
        pc.abrir_programa("calc", abrir=abrir)


def test_abrir_programa_desligado(monkeypatch):
    monkeypatch.delenv(pc.AMBIENTE, raising=False)
    with pytest.raises(pc.PcError) as erro:
        pc.abrir_programa("notepad", abrir=lambda exe: None)
    assert "JARVIS_HOST_PC" in str(erro.value)


def _casa(monkeypatch, tmp_path: Path) -> Path:
    casa = tmp_path / "casa"
    (casa / "Downloads").mkdir(parents=True)
    monkeypatch.setattr(pc.Path, "home", classmethod(lambda cls: casa))
    monkeypatch.setattr(pc.dados, "raiz", lambda: tmp_path / "storage")
    (tmp_path / "storage").mkdir()
    return casa


def test_abrir_arquivo_abre_pdf_do_downloads(monkeypatch, tmp_path: Path):
    casa = _casa(monkeypatch, tmp_path)
    arquivo = casa / "Downloads" / "contrato.pdf"
    arquivo.write_bytes(b"%PDF-1.4")
    chamados: list[str] = []
    resultado = pc.abrir_arquivo("Downloads/contrato.pdf" if False else str(arquivo), abrir=chamados.append)
    assert chamados == [str(arquivo.resolve())]
    assert resultado["nome"] == "contrato.pdf"


def test_abrir_arquivo_recusa_fora_das_pastas(monkeypatch, tmp_path: Path):
    _casa(monkeypatch, tmp_path)
    with pytest.raises(pc.PcError):
        pc.abrir_arquivo("/etc/passwd", abrir=lambda caminho: None)


def test_abrir_arquivo_recusa_executavel(monkeypatch, tmp_path: Path):
    casa = _casa(monkeypatch, tmp_path)
    arquivo = casa / "Downloads" / "instalador.exe"
    arquivo.write_bytes(b"MZ")
    with pytest.raises(pc.PcError) as erro:
        pc.abrir_arquivo(str(arquivo), abrir=lambda caminho: None)
    assert "executável" in str(erro.value)


def test_abrir_arquivo_recusa_extensao_desconhecida(monkeypatch, tmp_path: Path):
    casa = _casa(monkeypatch, tmp_path)
    arquivo = casa / "Downloads" / "coisa.xyz"
    arquivo.write_text("x", encoding="utf-8")
    with pytest.raises(pc.PcError):
        pc.abrir_arquivo(str(arquivo), abrir=lambda caminho: None)


def test_abrir_arquivo_inexistente(monkeypatch, tmp_path: Path):
    _casa(monkeypatch, tmp_path)
    with pytest.raises(pc.PcError):
        pc.abrir_arquivo(str(tmp_path / "storage" / "nao-existe.pdf"), abrir=lambda caminho: None)


def test_rodar_comando_devolve_saida():
    def executar(linha: list[str]):
        assert linha == ["ipconfig"]
        return 0, "Adaptador Ethernet: 192.168.0.10", ""

    resultado = pc.rodar_comando("ip", executar=executar)
    assert "192.168.0.10" in resultado["saida"]
    assert resultado["codigo"] == 0
    assert "Endereços de rede" in resultado["resposta"]


def test_rodar_comando_recusa_fora_da_lista():
    with pytest.raises(pc.PcError) as erro:
        pc.rodar_comando("rm -rf /", executar=lambda linha: (0, "", ""))
    assert "ip" in str(erro.value)


def test_rodar_comando_corta_saida_gigante():
    resultado = pc.rodar_comando("sistema", executar=lambda linha: (0, "x" * 10_000, ""))
    assert len(resultado["saida"]) <= pc.MAX_SAIDA + 40
    assert resultado["saida"].endswith("(saída cortada)")


def test_rodar_comando_usa_erro_quando_nao_ha_saida():
    resultado = pc.rodar_comando("processos", executar=lambda linha: (1, "", "acesso negado"))
    assert resultado["saida"] == "acesso negado"
    assert resultado["codigo"] == 1


def test_rodar_comando_desligado(monkeypatch):
    monkeypatch.delenv(pc.AMBIENTE, raising=False)
    with pytest.raises(pc.PcError):
        pc.rodar_comando("ip", executar=lambda linha: (0, "", ""))


def test_comando_nao_aceita_linha_livre():
    """A lista é fechada: o usuário escolhe o nome, nunca a linha."""
    for tentativa in ("ip; rm -rf /", "ipconfig /all", "powershell -c calc", "notepad", "cmd /c del *"):
        with pytest.raises(pc.PcError):
            pc.rodar_comando(tentativa, executar=lambda linha: (0, "", ""))
