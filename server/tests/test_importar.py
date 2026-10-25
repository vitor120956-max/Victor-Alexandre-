"""Testes da importação da pasta de downloads para a área isolada (0.36.0).

A skill lê uma pasta real da máquina, então cada teste isola o token e a
auditoria num `tmp_path` e usa uma pasta de origem sintética. Nada sai da
sandbox do teste: nenhuma cópia é feita para fora do `tmp_path`.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from server import sistema as S
from server.app import create_app
from server.skill_registry import build_registry


@pytest.fixture(autouse=True)
def estado(tmp_path, monkeypatch):
    monkeypatch.setattr(S, "STORAGE", tmp_path)
    monkeypatch.setattr(S, "TOKEN_ARQUIVO", tmp_path / "host-token.txt")
    monkeypatch.setattr(S, "QUARENTENA", tmp_path / "host-downloads")
    monkeypatch.setattr(S, "AUDITORIA", tmp_path / "host-audit.jsonl")
    yield tmp_path


@pytest.fixture
def token(estado):
    return S.token_host()


@pytest.fixture
def origem(tmp_path):
    pasta = tmp_path / "Downloads"
    pasta.mkdir()
    (pasta / "contrato.pdf").write_bytes(b"%PDF-1.4 conteudo")
    (pasta / "notas.md").write_text("# Notas", encoding="utf-8")
    (pasta / "instalador.exe").write_bytes(b"MZ")
    return pasta


@pytest.fixture
def destino(tmp_path):
    pasta = tmp_path / "user-files"
    pasta.mkdir()
    return pasta


# ---------------------------------------------------------------------------
# Token e origem
# ---------------------------------------------------------------------------


def test_importar_exige_token(destino, origem):
    with pytest.raises(S.SistemaError, match="token"):
        S.importar(destino_root=destino, origem=str(origem), autorizacao="")


def test_importar_recusa_token_errado(destino, origem, token):
    with pytest.raises(S.SistemaError, match="inválido"):
        S.importar(destino_root=destino, origem=str(origem), autorizacao="0" * 20)


def test_importar_recusa_origem_inexistente(destino, token, tmp_path):
    with pytest.raises(S.SistemaError, match="não existe"):
        S.importar(destino_root=destino, origem=str(tmp_path / "nao-existe"), autorizacao=token)


def test_importar_usa_downloads_quando_origem_vazia(destino, token, tmp_path, monkeypatch):
    casa = tmp_path / "casa"
    downloads = casa / "Downloads"
    downloads.mkdir(parents=True)
    (downloads / "recibo.pdf").write_bytes(b"%PDF-1.4")
    monkeypatch.setenv("HOME", str(casa))
    monkeypatch.setenv("USERPROFILE", str(casa))
    dados = S.importar(destino_root=destino, autorizacao=token)
    assert [item["arquivo"] for item in dados["copiados"]] == ["recibo.pdf"]
    assert (destino / "recibo.pdf").exists()


# ---------------------------------------------------------------------------
# Cópia
# ---------------------------------------------------------------------------


def test_importar_copia_formatos_permitidos(destino, origem, token):
    dados = S.importar(destino_root=destino, origem=str(origem), autorizacao=token)
    nomes = sorted(item["arquivo"] for item in dados["copiados"])
    assert nomes == ["contrato.pdf", "notas.md"]
    assert (destino / "contrato.pdf").read_bytes() == b"%PDF-1.4 conteudo"
    assert dados["arquivos"] == 2
    assert dados["bytes"] == sum((origem / nome).stat().st_size for nome in nomes)
    assert dados["executado"] is True


def test_importar_cria_subpasta_de_destino(destino, origem, token):
    dados = S.importar(destino_root=destino, origem=str(origem), destino="importados/2026", autorizacao=token)
    assert (destino / "importados" / "2026" / "contrato.pdf").exists()
    assert all(item["destino"].startswith("importados/2026/") for item in dados["copiados"])


def test_importar_ignora_formato_fora_da_lista(destino, origem, token):
    dados = S.importar(destino_root=destino, origem=str(origem), autorizacao=token)
    assert {"arquivo": "instalador.exe", "motivo": "formato fora da lista permitida"} in dados["ignorados"]
    assert not (destino / "instalador.exe").exists()


def test_importar_aceita_arquivo_unico(destino, origem, token):
    dados = S.importar(destino_root=destino, origem=str(origem / "contrato.pdf"), autorizacao=token)
    assert [item["arquivo"] for item in dados["copiados"]] == ["contrato.pdf"]


def test_importar_simulacao_nao_cria_arquivo(destino, origem, token):
    dados = S.importar(destino_root=destino, origem=str(origem), autorizacao=token, dry_run=True)
    assert dados["dryRun"] is True and dados["executado"] is False
    assert len(dados["copiados"]) == 2
    assert not (destino / "contrato.pdf").exists()


def test_importar_nao_sobrescreve_por_padrao(destino, origem, token):
    (destino / "contrato.pdf").write_bytes(b"antigo")
    dados = S.importar(destino_root=destino, origem=str(origem), autorizacao=token)
    assert (destino / "contrato.pdf").read_bytes() == b"antigo"
    assert {"arquivo": "contrato.pdf", "motivo": "já existe no destino (marque sobrescrever)"} in dados["ignorados"]


def test_importar_sobrescreve_com_confirmacao(destino, origem, token):
    (destino / "contrato.pdf").write_bytes(b"antigo")
    dados = S.importar(destino_root=destino, origem=str(origem), autorizacao=token, sobrescrever=True)
    assert (destino / "contrato.pdf").read_bytes() == b"%PDF-1.4 conteudo"
    assert "contrato.pdf" in [item["arquivo"] for item in dados["copiados"]]


def test_importar_audita_a_copia(destino, origem, token, estado):
    S.importar(destino_root=destino, origem=str(origem), autorizacao=token)
    linha = json.loads((estado / "host-audit.jsonl").read_text(encoding="utf-8").strip().splitlines()[-1])
    assert linha["acao"] == "importar"
    assert linha["arquivos"] == 2


# ---------------------------------------------------------------------------
# Limites e confinamento
# ---------------------------------------------------------------------------


def test_importar_recusa_destino_com_dois_pontos(destino, origem, token):
    with pytest.raises(S.SistemaError, match="Subpasta inválida"):
        S.importar(destino_root=destino, origem=str(origem), destino="../fora", autorizacao=token)


def test_importar_recusa_destino_absoluto(destino, origem, token):
    with pytest.raises(S.SistemaError, match="caminho absoluto"):
        S.importar(destino_root=destino, origem=str(origem), destino="/tmp/fora", autorizacao=token)


def test_importar_recusa_destino_oculto(destino, origem, token):
    with pytest.raises(S.SistemaError, match="Subpasta inválida"):
        S.importar(destino_root=destino, origem=str(origem), destino=".oculto", autorizacao=token)


def test_importar_respeita_limite_por_arquivo(destino, origem, token, monkeypatch):
    monkeypatch.setattr(S, "MAX_IMPORTAR_ARQUIVO", 5)
    dados = S.importar(destino_root=destino, origem=str(origem), autorizacao=token)
    assert dados["copiados"] == []
    assert any("por arquivo" in item["motivo"] for item in dados["ignorados"])


def test_importar_respeita_limite_de_arquivos(destino, origem, token, monkeypatch):
    monkeypatch.setattr(S, "MAX_IMPORTAR_ARQUIVOS", 1)
    dados = S.importar(destino_root=destino, origem=str(origem), autorizacao=token)
    assert dados["arquivos"] == 1
    assert any("limite de 1 arquivos" in item["motivo"] for item in dados["ignorados"])


def test_importar_respeita_limite_do_lote(destino, origem, token, monkeypatch):
    monkeypatch.setattr(S, "MAX_IMPORTAR_BYTES", 20)
    dados = S.importar(destino_root=destino, origem=str(origem), autorizacao=token)
    assert dados["bytes"] <= 20
    assert any("o lote passaria" in item["motivo"] for item in dados["ignorados"])


def test_importar_ignora_link_simbolico(destino, origem, token):
    link = origem / "atalho.pdf"
    try:
        link.symlink_to(origem / "contrato.pdf")
    except (OSError, NotImplementedError):
        pytest.skip("sistema de arquivos sem suporte a link simbólico")
    dados = S.importar(destino_root=destino, origem=str(origem), autorizacao=token)
    assert "atalho.pdf" in [item["arquivo"] for item in dados["ignorados"]]
    assert not (destino / "atalho.pdf").exists()


def test_importar_ignora_ocultos(destino, origem, token):
    (origem / ".oculto.md").write_text("segredo", encoding="utf-8")
    dados = S.importar(destino_root=destino, origem=str(origem), autorizacao=token)
    assert ".oculto.md" not in [item["arquivo"] for item in dados["copiados"]]


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------


@pytest.fixture
def client(tmp_path):
    app = create_app(registry=build_registry(tmp_path / "user-files"))
    return TestClient(app)


def test_api_publica_a_skill_com_confirmacao(client):
    skills = client.get("/api/skills").json()["skills"]
    alvo = next(item for item in skills if item["id"] == "files.import")
    assert alvo["category"] == "Arquivos"
    assert alvo["sideEffects"] is True
    assert alvo["dryRunSupported"] is True
    assert alvo["requiresConfirmation"] is True


def test_api_files_import_exige_confirmacao(client):
    corpo = client.post("/api/skills/files.import/execute", json={"parameters": {"origem": "/nao/existe"}}).json()
    assert corpo["error"]["code"] == "CONFIRMATION_REQUIRED"
