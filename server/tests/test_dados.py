"""Testes da raiz de dados (0.42.0): o projeto no pendrive, os dados no disco grande."""
from __future__ import annotations

from pathlib import Path

import pytest

from server import dados, elevacao, evolucao, repos, sistema


@pytest.fixture(autouse=True)
def sem_variavel(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(dados.VARIAVEL, raising=False)


def test_raiz_padrao_e_storage_do_projeto() -> None:
    assert dados.raiz() == dados.PROJETO / "storage"
    assert dados.area("biblioteca") == dados.PROJETO / "storage" / "biblioteca"


def test_raiz_respeita_caminho_absoluto(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv(dados.VARIAVEL, str(tmp_path / "dados"))
    assert dados.raiz() == tmp_path / "dados"


def test_raiz_aceita_caminho_relativo_ao_projeto(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(dados.VARIAVEL, "dados-teste")
    assert dados.raiz() == dados.PROJETO / "dados-teste"


def test_relatorio_mede_areas(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv(dados.VARIAVEL, str(tmp_path))
    (tmp_path / "biblioteca" / "fontes").mkdir(parents=True)
    (tmp_path / "biblioteca" / "fontes" / "a.json").write_text("x" * 500, encoding="utf-8")
    (tmp_path / "repos" / "r").mkdir(parents=True)
    (tmp_path / "repos" / "r" / "README.md").write_text("y" * 300, encoding="utf-8")

    relatorio = dados.relatorio()
    areas = {item["nome"]: item for item in relatorio["areas"]}
    assert areas["biblioteca"]["arquivos"] == 1
    assert areas["biblioteca"]["bytes"] == 500
    assert areas["repos"]["arquivos"] == 1
    assert relatorio["arquivos_total"] == 2
    assert relatorio["bytes_total"] == 800
    assert relatorio["configurada"] is True
    assert relatorio["no_projeto"] is False
    assert relatorio["disco_livre"] >= 0


def test_relatorio_sem_variavel_aponta_para_o_padrao() -> None:
    relatorio = dados.relatorio()
    assert relatorio["raiz"] == str(dados.PROJETO / "storage")
    assert relatorio["configurada"] is False
    assert relatorio["no_projeto"] is True


def test_apontar_sem_variavel_nao_mexe_em_nada() -> None:
    antes = (sistema.STORAGE, repos.PASTA_REPOS, evolucao.STORAGE, elevacao.STORAGE)
    dados.apontar()
    assert (sistema.STORAGE, repos.PASTA_REPOS, evolucao.STORAGE, elevacao.STORAGE) == antes


def test_apontar_com_variavel_troca_as_constantes(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    alvo = tmp_path / "disco-grande"
    monkeypatch.setenv(dados.VARIAVEL, str(alvo))
    original = (sistema.STORAGE, sistema.TOKEN_ARQUIVO, repos.PASTA_REPOS, evolucao.STORAGE, elevacao.STORAGE)
    try:
        dados.apontar()
        assert sistema.STORAGE == alvo
        assert sistema.TOKEN_ARQUIVO == alvo / "host-token.txt"
        assert sistema.QUARENTENA == alvo / "host-downloads"
        assert repos.PASTA_REPOS == alvo / "repos"
        assert repos.INDICE == alvo / "repos" / "indice.json"
        assert evolucao.STORAGE == alvo
        assert elevacao.STORAGE == alvo
    finally:
        (
            sistema.STORAGE,
            sistema.TOKEN_ARQUIVO,
            repos.PASTA_REPOS,
            evolucao.STORAGE,
            elevacao.STORAGE,
        ) = original
        sistema.QUARENTENA = original[0] / "host-downloads"
        repos.INDICE = original[2] / "indice.json"
