"""Testes do backup — zip de verdade, em pasta temporária, sem tocar em dado do usuário."""
from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest

from server import backup


@pytest.fixture()
def raiz(tmp_path):
    base = tmp_path / "dados"
    (base / "docs").mkdir(parents=True)
    (base / "docs" / "contrato.txt").write_text("texto do contrato", encoding="utf-8")
    (base / "node_modules").mkdir()
    (base / "node_modules" / "lixo.js").write_text("nao entra", encoding="utf-8")
    (base / ".venv").mkdir()
    (base / ".venv" / "python.exe").write_bytes(b"\x00" * 10)
    return base


def test_planejar_conta_e_ignora_lixo(raiz):
    plano = backup.planejar(raiz=raiz, destino=str(raiz / "backups"))
    assert plano["arquivos"] == 1
    assert plano["bytes"] == len("texto do contrato")
    assert plano["mesmo_disco"] is True
    assert any("mesmo disco" in aviso for aviso in plano["avisos"])


def test_planejar_sem_arquivo_avisa(tmp_path):
    vazia = tmp_path / "vazia"
    vazia.mkdir()
    plano = backup.planejar(raiz=vazia, destino=str(tmp_path / "b"))
    assert plano["arquivos"] == 0
    assert plano["avisos"]


def test_criar_gera_zip_com_manifesto_e_hash(raiz):
    destino = raiz / "backups"
    resultado = backup.criar(raiz=raiz, destino=str(destino))
    arquivo = Path(resultado["arquivo"])
    assert arquivo.exists()
    assert len(resultado["sha256"]) == 64
    assert resultado["abre"] is True
    with zipfile.ZipFile(arquivo) as pacote:
        assert pacote.testzip() is None
        nomes = pacote.namelist()
        assert backup.MANIFESTO in nomes
        assert "docs/contrato.txt" in nomes
        assert not any("node_modules" in nome for nome in nomes)
        manifesto = json.loads(pacote.read(backup.MANIFESTO))
        assert manifesto["arquivos"] == 1
    assert (destino / f"{arquivo.name}.sha256").exists()
    assert (destino / f"{arquivo.name}.json").exists()


def test_criar_respeita_o_teto(raiz):
    with pytest.raises(backup.BackupError) as erro:
        backup.criar(raiz=raiz, destino=str(raiz / "backups"), max_bytes=1)
    assert "teto" in str(erro.value).lower() or "MB" in str(erro.value)


def test_listar_backups(raiz):
    backup.criar(raiz=raiz, destino=str(raiz / "backups"))
    lista = backup.listar(raiz=raiz)
    assert lista["total"] == 1
    assert lista["backups"][0]["arquivo"].startswith("jarvis-dados-")


def test_restaurar_extrai_em_pasta_nova(raiz, tmp_path):
    resultado = backup.criar(raiz=raiz, destino=str(raiz / "backups"))
    novo = tmp_path / "restaurado"
    volta = backup.restaurar(resultado["arquivo"], destino=str(novo))
    assert volta["itens"] >= 2
    assert (novo / "docs" / "contrato.txt").read_text(encoding="utf-8") == "texto do contrato"


def test_restaurar_recusa_pasta_ocupada(raiz, tmp_path):
    resultado = backup.criar(raiz=raiz, destino=str(raiz / "backups"))
    ocupada = tmp_path / "ocupada"
    ocupada.mkdir()
    (ocupada / "arquivo.txt").write_text("já existe", encoding="utf-8")
    with pytest.raises(backup.BackupError):
        backup.restaurar(resultado["arquivo"], destino=str(ocupada))


def test_restaurar_recusa_arquivo_que_nao_e_zip(raiz, tmp_path):
    falso = tmp_path / "falso.zip"
    falso.write_text("não é zip", encoding="utf-8")
    with pytest.raises(backup.BackupError):
        backup.restaurar(str(falso), destino=str(tmp_path / "saida"))


def test_restaurar_recusa_caminho_que_escapa(raiz, tmp_path):
    malicioso = tmp_path / "malicioso.zip"
    with zipfile.ZipFile(malicioso, "w") as pacote:
        pacote.writestr("../fora.txt", "x")
    with pytest.raises(backup.BackupError):
        backup.restaurar(str(malicioso), destino=str(tmp_path / "saida"))
