"""Testes do GitHub público: ficha, pastas, arquivo e busca — tudo com dublê."""
from __future__ import annotations

import base64
from pathlib import Path
from typing import Any

import pytest

from server import github


def resposta(mapa: dict[str, dict[str, Any]]):
    vistas: list[str] = []

    def baixar(url: str) -> dict[str, Any]:
        vistas.append(url)
        for chave, valor in mapa.items():
            if chave in url:
                return valor
        raise github.GithubError(f"sem dublê para {url}")

    baixar.vistas = vistas  # type: ignore[attr-defined]
    return baixar


REPO = {
    "description": "Agentes de navegador",
    "stargazers_count": 1234,
    "language": "TypeScript",
    "license": {"spdx_id": "MIT"},
    "default_branch": "main",
    "pushed_at": "2026-01-02T03:04:05Z",
    "size": 512,
    "archived": False,
    "html_url": "https://github.com/vercel-labs/agent-skills",
    "topics": ["skills", "agent"],
}


def test_repo_resume_a_ficha():
    ficha = github.repo("vercel-labs/agent-skills", baixar=resposta({"/repos/": REPO}))
    assert ficha["repositorio"] == "vercel-labs/agent-skills"
    assert ficha["estrelas"] == 1234
    assert ficha["licenca"] == "MIT"
    assert ficha["branch_padrao"] == "main"


def test_repo_aceita_endereco_completo():
    vistas: list[str] = []

    def baixar(url: str) -> dict[str, Any]:
        vistas.append(url)
        return REPO

    github.repo("https://github.com/vercel-labs/agent-skills.git", baixar=baixar)
    assert vistas == ["https://api.github.com/repos/vercel-labs/agent-skills"]


def test_repo_nome_invalido_e_recusado():
    with pytest.raises(github.GithubError):
        github.repo("sem-barra", baixar=resposta({}))


def test_arquivos_ordenam_pasta_primeiro():
    itens = [
        {"name": "SKILL.md", "type": "file", "size": 10, "path": "SKILL.md"},
        {"name": "skills", "type": "dir", "size": 0, "path": "skills"},
    ]
    lista = github.arquivos("a/b", baixar=resposta({"/contents/": {"itens": itens}}))
    assert [item["nome"] for item in lista] == ["skills", "SKILL.md"]
    assert lista[0]["tipo"] == "pasta"


def test_arquivos_aceitam_arquivo_unico():
    bruto = {"type": "file", "name": "SKILL.md", "path": "SKILL.md", "size": 42}
    itens = github.arquivos("a/b", "SKILL.md", baixar=resposta({"/contents/": bruto}))
    assert itens == [{"nome": "SKILL.md", "tipo": "arquivo", "tamanho": 42, "caminho": "SKILL.md"}]


def test_arquivo_decodifica_base64():
    conteudo = base64.b64encode("# Habilidade\n\nFaça assim.\n".encode()).decode()
    bruto = {
        "type": "file",
        "path": "skills/x/SKILL.md",
        "size": 24,
        "encoding": "base64",
        "content": conteudo,
        "html_url": "https://github.com/a/b/blob/main/skills/x/SKILL.md",
    }
    lido = github.arquivo("a/b", "skills/x/SKILL.md", baixar=resposta({"/contents/": bruto}))
    assert lido["texto"].startswith("# Habilidade")
    assert lido["cortado"] is False
    assert lido["url"].endswith("skills/x/SKILL.md")


def test_arquivo_corta_no_limite():
    conteudo = base64.b64encode(("a" * 200).encode()).decode()
    bruto = {"type": "file", "path": "x.md", "size": 200, "encoding": "base64", "content": conteudo}
    lido = github.arquivo("a/b", "x.md", baixar=resposta({"/contents/": bruto}), limite=50)
    assert len(lido["texto"]) == 50
    assert lido["cortado"] is True


def test_pasta_nao_e_arquivo():
    with pytest.raises(github.GithubError):
        github.arquivo("a/b", "skills", baixar=resposta({"/contents/": {"type": "dir"}}))


def test_arquivo_vazio_e_recusado():
    bruto = {"type": "file", "path": "x.md", "size": 0, "encoding": "base64", "content": ""}
    with pytest.raises(github.GithubError):
        github.arquivo("a/b", "x.md", baixar=resposta({"/contents/": bruto}))


def test_busca_ordena_e_limita():
    bruto = {
        "items": [
            {"full_name": f"a/r{i}", "description": "x", "stargazers_count": 100 - i, "html_url": "u"}
            for i in range(8)
        ]
    }
    achados = github.buscar("agent skills", limite=3, baixar=resposta({"/search/repositories": bruto}))
    assert len(achados) == 3
    assert achados[0]["repositorio"] == "a/r0"


def test_busca_curta_e_recusada():
    with pytest.raises(github.GithubError):
        github.buscar("a", baixar=resposta({}))


def test_limite_de_pedidos_por_hora_tem_mensagem_clara():
    def baixar(_url: str) -> dict[str, Any]:
        raise github.GithubError(
            "O GitHub recusou por limite de pedidos (60 por hora, sem token). Espere um pouco e tente de novo."
        )

    with pytest.raises(github.GithubError) as erro:
        github.repo("a/b", baixar=baixar)
    assert "60 por hora" in str(erro.value)


def test_modulo_nao_esta_no_gitignore():
    raiz = Path(__file__).resolve().parents[2]
    ignorados = {linha.strip() for linha in (raiz / ".gitignore").read_text(encoding="utf-8").splitlines()}
    assert "server/github.py" not in ignorados


def test_arvore_filtra_pelo_sufixo():
    bruto = {
        "tree": [
            {"type": "blob", "path": "skills/a/SKILL.md"},
            {"type": "blob", "path": "skills/b/SKILL.md"},
            {"type": "blob", "path": "README.md"},
            {"type": "tree", "path": "skills"},
        ]
    }
    caminhos = github.arvore("a/b", sufixo="SKILL.md", baixar=resposta({"/git/trees/": bruto}))
    assert caminhos == ["skills/a/SKILL.md", "skills/b/SKILL.md"]


def test_arvore_respeita_o_limite():
    bruto = {"tree": [{"type": "blob", "path": f"s/{i}/SKILL.md"} for i in range(10)]}
    assert len(github.arvore("a/b", sufixo="SKILL.md", limite=3, baixar=resposta({"/git/trees/": bruto}))) == 3
