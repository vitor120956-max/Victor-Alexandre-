"""Testes do leitor de Git — só leitura, argumentos fixos, repositório permitido."""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from server import git

TEM_GIT = bool(subprocess.run(["git", "--version"], capture_output=True).returncode == 0)
precisa_git = pytest.mark.skipif(not TEM_GIT, reason="git não instalado nesta máquina")


def _repo(caminho: Path) -> Path:
    caminho.mkdir(parents=True, exist_ok=True)
    for args in (
        ["init", "-q"],
        ["config", "user.email", "teste@exemplo.local"],
        ["config", "user.name", "Teste"],
    ):
        subprocess.run(["git", "-C", str(caminho), *args], check=True, capture_output=True)
    (caminho / "a.txt").write_text("um\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(caminho), "add", "."], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(caminho), "commit", "-qm", "primeiro"], check=True, capture_output=True)
    return caminho


@precisa_git
def test_status_repositorio_limpo(tmp_path):
    repo = _repo(tmp_path / "repo")
    dados = git.status(str(repo), raizes=[tmp_path])
    assert dados["limpo"] is True
    assert dados["total"] == 0
    assert dados["branch"]


@precisa_git
def test_status_mostra_modificado(tmp_path):
    repo = _repo(tmp_path / "repo")
    (repo / "a.txt").write_text("dois\n", encoding="utf-8")
    (repo / "novo.txt").write_text("novo\n", encoding="utf-8")
    dados = git.status(str(repo), raizes=[tmp_path])
    caminhos = {item["caminho"] for item in dados["arquivos"]}
    assert "a.txt" in caminhos and "novo.txt" in caminhos
    assert dados["limpo"] is False


@precisa_git
def test_log_lista_commits(tmp_path):
    repo = _repo(tmp_path / "repo")
    dados = git.log(str(repo), raizes=[tmp_path], limite=5)
    assert dados["commits"][0]["assunto"] == "primeiro"
    assert len(dados["commits"][0]["hash"]) >= 7


@precisa_git
def test_diff_mostra_o_patch(tmp_path):
    repo = _repo(tmp_path / "repo")
    (repo / "a.txt").write_text("dois\n", encoding="utf-8")
    dados = git.diff(str(repo), raizes=[tmp_path])
    assert "+dois" in dados["patch"]
    assert dados["vazio"] is False


@precisa_git
def test_diff_de_arquivo_especifico(tmp_path):
    repo = _repo(tmp_path / "repo")
    (repo / "a.txt").write_text("dois\n", encoding="utf-8")
    (repo / "b.txt").write_text("b\n", encoding="utf-8")
    dados = git.diff(str(repo), arquivo="a.txt", raizes=[tmp_path])
    assert "+dois" in dados["patch"] and "b.txt" not in dados["patch"]


@precisa_git
def test_remoto_sem_remoto(tmp_path):
    repo = _repo(tmp_path / "repo")
    dados = git.remoto(str(repo), raizes=[tmp_path])
    assert dados["remotos"] == {}
    assert "não tem remoto" in dados["resposta"]


@precisa_git
def test_repositorio_fora_dos_lugares_permitidos(tmp_path):
    repo = _repo(tmp_path / "fora" / "repo")
    with pytest.raises(git.GitError):
        git.status(str(repo), raizes=[tmp_path / "permitida"])


def test_pasta_sem_git_recusa(tmp_path):
    with pytest.raises(git.GitError):
        git.status(str(tmp_path), raizes=[tmp_path])


def test_diff_recusa_caminho_suspeito(tmp_path):
    with pytest.raises(git.GitError):
        git.diff(str(tmp_path), arquivo="../etc/passwd", raizes=[tmp_path])


def test_projeto_real_e_repositorio():
    dados = git.status()
    assert dados["repositorio"].endswith("Victor-Alexandre-")
