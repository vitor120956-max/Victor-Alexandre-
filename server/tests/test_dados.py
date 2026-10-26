"""Testes da raiz de dados (0.51.0): o projeto no pendrive, os dados no disco grande."""
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


# ---------------------------------------------------------------- Google Drive

def _limpar(monkeypatch: pytest.MonkeyPatch) -> None:
    for nome in (dados.VARIAVEL, dados.VARIAVEL_BIBLIOTECA, dados.VARIAVEL_REPOS, dados.VARIAVEL_DRIVE):
        monkeypatch.delenv(nome, raising=False)


def test_biblioteca_respeita_variavel_propria(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _limpar(monkeypatch)
    alvo = tmp_path / "Google Drive" / "Meu Drive" / "JARVIS-DADOS" / "biblioteca"
    monkeypatch.setenv(dados.VARIAVEL_BIBLIOTECA, str(alvo))
    assert dados.biblioteca() == alvo
    assert dados.caminho("biblioteca") == alvo


def test_repositorios_respeitam_variavel_propria(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _limpar(monkeypatch)
    alvo = tmp_path / "Drive" / "repos"
    monkeypatch.setenv(dados.VARIAVEL_REPOS, str(alvo))
    assert dados.repositorios() == alvo
    assert dados.caminho("repos") == alvo


def test_caminho_sem_variavel_segue_a_raiz(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _limpar(monkeypatch)
    monkeypatch.setenv(dados.VARIAVEL, str(tmp_path))
    assert dados.caminho("repos") == tmp_path / "repos"
    assert dados.caminho("agente-local") == tmp_path / "agente-local"


def test_no_drive_reconhece_os_nomes_do_google_drive() -> None:
    assert dados.no_drive(Path("G:/Meu Drive/JARVIS-DADOS/biblioteca")) is True
    assert dados.no_drive(Path(r"C:\Users\Ana\Google Drive\JARVIS-DADOS")) is True
    assert dados.no_drive(Path("/home/ana/GoogleDrive/biblioteca")) is True
    assert dados.no_drive(Path("/home/ana/storage/biblioteca")) is False


def test_detectar_drive_usa_a_variavel_quando_existe(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _limpar(monkeypatch)
    pasta = tmp_path / "Meu Drive"
    pasta.mkdir()
    monkeypatch.setenv(dados.VARIAVEL_DRIVE, str(pasta))
    assert dados.detectar_drive() == pasta


def test_detectar_drive_nao_devolve_a_pasta_do_usuario(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _limpar(monkeypatch)
    # casa vazia: nada de "Drive" aqui dentro, então não há o que detectar
    assert dados.detectar_drive(tmp_path) is None


def test_detectar_drive_acha_a_pasta_no_lugar_de_casa(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _limpar(monkeypatch)
    (tmp_path / "Google Drive" / "Meu Drive").mkdir(parents=True)
    assert dados.detectar_drive(tmp_path) == tmp_path / "Google Drive" / "Meu Drive"


def test_relatorio_marca_o_que_esta_no_drive(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _limpar(monkeypatch)
    monkeypatch.setenv(dados.VARIAVEL, str(tmp_path / "local"))
    monkeypatch.setenv(dados.VARIAVEL_BIBLIOTECA, str(tmp_path / "Google Drive" / "Meu Drive" / "biblioteca"))
    relatorio = dados.relatorio()
    areas = {item["nome"]: item for item in relatorio["areas"]}
    assert areas["biblioteca"]["no_drive"] is True
    assert areas["biblioteca"]["caminho"].endswith("biblioteca")
    assert areas["repos"]["no_drive"] is False
    assert relatorio["biblioteca_variavel"] == dados.VARIAVEL_BIBLIOTECA
    assert relatorio["repos_variavel"] == dados.VARIAVEL_REPOS


def test_apontar_com_repos_no_drive_mexe_so_nos_repos(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _limpar(monkeypatch)
    alvo = tmp_path / "Drive" / "repos"
    monkeypatch.setenv(dados.VARIAVEL_REPOS, str(alvo))
    original = (sistema.STORAGE, repos.PASTA_REPOS, repos.INDICE)
    try:
        dados.apontar()
        assert sistema.STORAGE == original[0]
        assert repos.PASTA_REPOS == alvo
        assert repos.INDICE == alvo / "indice.json"
    finally:
        sistema.STORAGE, repos.PASTA_REPOS, repos.INDICE = original


def test_apontar_com_dados_e_repos_no_drive_mantem_cada_um(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _limpar(monkeypatch)
    raiz_local = tmp_path / "local"
    alvo = tmp_path / "Drive" / "repos"
    monkeypatch.setenv(dados.VARIAVEL, str(raiz_local))
    monkeypatch.setenv(dados.VARIAVEL_REPOS, str(alvo))
    original = (sistema.STORAGE, repos.PASTA_REPOS, repos.INDICE)
    try:
        dados.apontar()
        assert sistema.STORAGE == raiz_local
        assert repos.PASTA_REPOS == alvo
        assert repos.INDICE == alvo / "indice.json"
    finally:
        sistema.STORAGE, repos.PASTA_REPOS, repos.INDICE = original
