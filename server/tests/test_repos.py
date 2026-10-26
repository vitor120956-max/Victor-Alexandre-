"""Testes da camada de repositórios (0.45.0).

Nenhum teste chama o GitHub: o download é injetado e o `.zip` é montado na
memória. A única execução real é um `python script.py` de uma linha, dentro da
pasta temporária.
"""
from __future__ import annotations

import io
import json
import sys
import zipfile
from pathlib import Path

import pytest

from server import repos
from server.repos import (
    ReposError,
    analisar,
    baixar_repo,
    executar_no_repo,
    exigir_autorizacao,
    ler_arquivo,
    listar,
    parse_url,
    remover_repo,
    slug_de,
    sugestao_de_uso,
)


def _zip(arquivos: dict[str, str | bytes], topo: str = "repo-master") -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as pacote:
        for nome, conteudo in arquivos.items():
            pacote.writestr(f"{topo}/{nome}" if topo else nome, conteudo)
    return buffer.getvalue()


@pytest.fixture()
def pasta(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    raiz = tmp_path / "repos"
    raiz.mkdir()
    monkeypatch.setattr(repos, "PASTA_REPOS", raiz)
    monkeypatch.setattr(repos, "INDICE", raiz / "indice.json")
    return raiz


# ------------------------------------------------------------------ endereço

@pytest.mark.parametrize(
    "entrada,esperado",
    [
        ("https://github.com/virgiliojr94/book-to-skill", ("virgiliojr94", "book-to-skill", None)),
        ("github.com/dono/repo", ("dono", "repo", None)),
        ("dono/repo", ("dono", "repo", None)),
        ("https://github.com/dono/repo.git", ("dono", "repo", None)),
        ("https://github.com/dono/repo/", ("dono", "repo", None)),
        ("git@github.com:dono/repo.git", ("dono", "repo", None)),
        ("https://github.com/dono/repo/tree/dev", ("dono", "repo", "dev")),
        ("https://github.com/dono/repo/tree/feat/x", ("dono", "repo", "feat/x")),
    ],
)
def test_parse_url_aceita_as_formas_comuns(entrada: str, esperado: tuple[str, str, str | None]) -> None:
    assert parse_url(entrada) == esperado


@pytest.mark.parametrize(
    "entrada",
    ["https://gitlab.com/dono/repo", "https://github.com/somentenome", "", "   "],
)
def test_parse_url_recusa_o_que_nao_sabe_baixar(entrada: str) -> None:
    with pytest.raises(ReposError):
        parse_url(entrada)


def test_parse_url_recusa_travessia_de_pasta() -> None:
    with pytest.raises(ReposError):
        parse_url("dono/../outro")


def test_slug_e_estavel_e_sem_acento() -> None:
    assert slug_de("VirgilioJR94", "Book-To-Skill") == "virgiliojr94--book-to-skill"
    assert slug_de("Dono", "ação") == "dono--acao"


# ------------------------------------------------------------- autorização

@pytest.mark.parametrize("texto", ["sim", "Sim, pode baixar", "autorizo", "confirmo, pode copiar"])
def test_autorizacao_aceita_formas_ditas(texto: str) -> None:
    exigir_autorizacao(texto)


@pytest.mark.parametrize("texto", ["", "   ", "talvez", "não sei"])
def test_autorizacao_recusa_silencio(texto: str) -> None:
    with pytest.raises(ReposError):
        exigir_autorizacao(texto)


# ----------------------------------------------------------------- extração

def test_baixar_repo_extrai_achata_e_registra(pasta: Path) -> None:
    pacote = _zip(
        {
            "README.md": "# Projeto legal\n\nFaz uma coisa.\n",
            "requirements.txt": "requests>=2.0\npytest\n",
            "pacote/__main__.py": "print('oi')\n",
            "pyproject.toml": "[project]\nname='x'\n\n[project.scripts]\njx = 'pacote:main'\n",
        }
    )
    resultado = baixar_repo(
        "https://github.com/Dono/Repo", autorizacao="sim, pode baixar", baixar=lambda _url: pacote
    )

    assert resultado["slug"] == "dono--repo"
    assert resultado["arquivos"] == 4
    assert (pasta / "dono--repo" / "README.md").is_file()
    assert (pasta / "dono--repo" / "pacote" / "__main__.py").is_file()
    assert resultado["readme"]["titulo"] == "Projeto legal"
    assert resultado["linguagens"][0]["nome"] == "Python"
    comandos = [item["comando"] for item in resultado["entradas"]]
    assert "python -m pacote" in comandos
    assert "jx" in comandos
    assert listar()[0]["slug"] == "dono--repo"
    assert "Linguagem principal" in resultado["sugestao"]


def test_baixar_repo_exige_autorizacao(pasta: Path) -> None:
    with pytest.raises(ReposError):
        baixar_repo("dono/repo", autorizacao="", baixar=lambda _url: b"")
    assert listar() == []


def test_baixar_repo_recusa_zip_invalido(pasta: Path) -> None:
    with pytest.raises(ReposError, match="não é um .zip"):
        baixar_repo("dono/repo", autorizacao="sim", baixar=lambda _url: b"nao e zip")


def test_extracao_recusa_travessia(pasta: Path) -> None:
    pacote = _zip({"a.txt": "ok"}, topo="")
    buffer = io.BytesIO(pacote)
    with zipfile.ZipFile(buffer, "a") as extra:
        extra.writestr("../escapou.txt", "ruim")
    with pytest.raises(ReposError, match="Caminho recusado"):
        baixar_repo("dono/repo", autorizacao="sim", baixar=lambda _url: buffer.getvalue())
    assert not (pasta.parent / "escapou.txt").exists()


def test_extracao_recusa_link_simbolico(pasta: Path) -> None:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as pacote:
        info = zipfile.ZipInfo("repo-master/link")
        info.external_attr = (0o120777 & 0xFFFF) << 16
        pacote.writestr(info, "alvo")
    with pytest.raises(ReposError, match="link simbólico"):
        baixar_repo("dono/repo", autorizacao="sim", baixar=lambda _url: buffer.getvalue())


def test_extracao_respeita_teto_de_arquivos(pasta: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(repos, "MAX_ARQUIVOS", 2)
    pacote = _zip({"a.txt": "1", "b.txt": "2", "c.txt": "3"})
    with pytest.raises(ReposError, match="acima do teto"):
        baixar_repo("dono/repo", autorizacao="sim", baixar=lambda _url: pacote)


def test_baixar_de_novo_substitui_em_vez_de_duplicar(pasta: Path) -> None:
    primeiro = _zip({"README.md": "# Um\n"})
    segundo = _zip({"README.md": "# Dois\n", "novo.txt": "x"})
    baixar_repo("dono/repo", autorizacao="sim", baixar=lambda _url: primeiro)
    resultado = baixar_repo("dono/repo", autorizacao="sim", baixar=lambda _url: segundo)

    assert resultado["readme"]["titulo"] == "Dois"
    assert len(listar()) == 1
    assert (pasta / "dono--repo" / "novo.txt").is_file()
    assert not (pasta / "dono--repo" / "velho.txt").exists()


def test_download_com_falha_nao_deixa_pasta_pela_metade(pasta: Path) -> None:
    def explode(_url: str) -> bytes:
        raise RuntimeError("sem rede")

    with pytest.raises(ReposError, match="Falha ao baixar"):
        baixar_repo("dono/repo", autorizacao="sim", baixar=explode)
    assert not any(item.is_dir() for item in pasta.iterdir())


# ------------------------------------------------------------------- análise

def test_analisar_detecta_scripts_e_makefile(pasta: Path) -> None:
    projeto = pasta / "manual"
    (projeto / "src").mkdir(parents=True)
    (projeto / "package.json").write_text(
        json.dumps({"scripts": {"dev": "vite", "test": "vitest"}, "dependencies": {"react": "18"}}),
        encoding="utf-8",
    )
    (projeto / "Makefile").write_text("build:\n\tpython -m build\n\nlint:\n\techo ok\n", encoding="utf-8")
    (projeto / "src" / "app.ts").write_text("export const a = 1\n", encoding="utf-8")

    meta = analisar(projeto)
    comandos = [item["comando"] for item in meta["entradas"]]
    assert "npm run dev" in comandos
    assert "npm run test" in comandos
    assert "make build" in comandos
    assert meta["linguagens"][0]["nome"] in {"TypeScript", "JSON"}
    assert meta["dependencias"][0]["arquivo"] == "package.json"


def test_analisar_reconhece_skill_md(pasta: Path) -> None:
    projeto = pasta / "com-skill"
    (projeto / "skill").mkdir(parents=True)
    (projeto / "skill" / "SKILL.md").write_text("---\nname: x\n---\n", encoding="utf-8")
    meta = analisar(projeto)
    assert meta["tem_skill"] is True
    assert meta["skills"] == ["skill/SKILL.md"]


def test_analisar_pasta_inexistente_recusa(pasta: Path) -> None:
    with pytest.raises(ReposError):
        analisar(pasta / "nao-existe")


# --------------------------------------------------------------------- leitura

def test_ler_arquivo_de_dentro(pasta: Path) -> None:
    baixar_repo(
        "dono/repo", autorizacao="sim", baixar=lambda _url: _zip({"README.md": "# Oi\n\nconteudo\n"})
    )
    lido = ler_arquivo("dono--repo", "README.md")
    assert lido["conteudo"].startswith("# Oi")
    assert lido["caminho"] == "README.md"


@pytest.mark.parametrize("caminho", ["../indice.json", "/etc/passwd", "../../x"])
def test_ler_arquivo_nao_escapa_da_pasta(pasta: Path, caminho: str) -> None:
    baixar_repo("dono/repo", autorizacao="sim", baixar=lambda _url: _zip({"README.md": "# Oi\n"}))
    with pytest.raises(ReposError, match="fora da pasta"):
        ler_arquivo("dono--repo", caminho)


def test_ler_arquivo_recusa_binario(pasta: Path) -> None:
    baixar_repo(
        "dono/repo", autorizacao="sim", baixar=lambda _url: _zip({"dados.bin": b"\x00\x01\x02"})
    )
    with pytest.raises(ReposError, match="binário"):
        ler_arquivo("dono--repo", "dados.bin")


def test_ler_arquivo_de_repo_nao_baixado(pasta: Path) -> None:
    with pytest.raises(ReposError, match="não está na pasta"):
        ler_arquivo("ninguem--nada", "README.md")


# ------------------------------------------------------------------- execução

def test_executar_exige_autorizacao(pasta: Path) -> None:
    baixar_repo("dono/repo", autorizacao="sim", baixar=lambda _url: _zip({"main.py": "print('oi')\n"}))
    with pytest.raises(ReposError, match="autorização"):
        executar_no_repo("dono--repo", f"{Path(sys.executable).name} main.py")


def test_executar_recusa_comando_com_shell(pasta: Path) -> None:
    baixar_repo("dono/repo", autorizacao="sim", baixar=lambda _url: _zip({"main.py": "print(1)\n"}))
    with pytest.raises(ReposError, match="shell"):
        executar_no_repo("dono--repo", "python main.py && echo oi", autorizacao="sim")


def test_executar_recusa_interpretador_fora_da_lista(pasta: Path) -> None:
    baixar_repo("dono/repo", autorizacao="sim", baixar=lambda _url: _zip({"main.py": "print(1)\n"}))
    with pytest.raises(ReposError, match="Só posso rodar"):
        executar_no_repo("dono--repo", "bash main.py", autorizacao="sim")


def test_executar_roda_python_de_verdade(pasta: Path) -> None:
    baixar_repo(
        "dono/repo",
        autorizacao="sim",
        baixar=lambda _url: _zip({"main.py": "print('rodou', 2 + 2)\n"}),
    )
    resultado = executar_no_repo("dono--repo", "python main.py", autorizacao="sim, pode executar")
    assert resultado["ok"] is True
    assert resultado["codigo"] == 0
    assert "rodou 4" in resultado["saida"]


def test_executar_devolve_erro_do_programa(pasta: Path) -> None:
    baixar_repo(
        "dono/repo",
        autorizacao="sim",
        baixar=lambda _url: _zip({"main.py": "raise SystemExit(3)\n"}),
    )
    resultado = executar_no_repo("dono--repo", "python main.py", autorizacao="sim")
    assert resultado["ok"] is False
    assert resultado["codigo"] == 3


def test_ambiente_nao_leva_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JARVIS_HOST_TOKEN", "segredo")
    monkeypatch.setenv("MINHA_API_KEY", "chave")
    monkeypatch.setenv("PATH_SEGURO", "ok")
    ambiente = repos._ambiente_limpo()
    assert "JARVIS_HOST_TOKEN" not in ambiente
    assert "MINHA_API_KEY" not in ambiente
    assert ambiente.get("PATH_SEGURO") == "ok"


# ------------------------------------------------------------- remoção e texto

def test_remover_repo_apaga_pasta_e_indice(pasta: Path) -> None:
    baixar_repo("dono/repo", autorizacao="sim", baixar=lambda _url: _zip({"README.md": "# x\n"}))
    assert remover_repo("dono--repo") is True
    assert not (pasta / "dono--repo").exists()
    assert listar() == []
    assert remover_repo("dono--repo") is False


def test_sugestao_avisa_que_nada_foi_executado(pasta: Path) -> None:
    pacote = _zip({"README.md": "# Livro\n", "main.py": "print(1)\n"})
    resultado = baixar_repo("dono/repo", autorizacao="sim", baixar=lambda _url: pacote)
    assert "Entradas prováveis" in resultado["sugestao"]
    assert "Nada foi instalado nem executado" in resultado["sugestao"]


def test_sugestao_sem_entrada_declarada(pasta: Path) -> None:
    meta = {"linguagens": [{"nome": "Markdown", "arquivos": 3}], "entradas": [], "dependencias": []}
    texto = sugestao_de_uso(meta)
    assert "Não achei entrada declarada" in texto


def test_titulo_em_h1_de_html_do_readme(pasta: Path) -> None:
    baixar_repo(
        "dono/repo",
        autorizacao="sim",
        baixar=lambda _url: _zip({"README.md": '<p align="center"><img src="x.webp"></p>\n<h1 align="center">Meu Projeto</h1>\n\nFaz algo.\n'}),
    )
    assert listar()[0]["readme"]["titulo"] == "Meu Projeto"


def test_ler_arquivo_grande_corta_em_vez_de_recusar(pasta: Path) -> None:
    baixar_repo(
        "dono/repo",
        autorizacao="sim",
        baixar=lambda _url: _zip({"grande.md": "x" * 5_000}),
    )
    lido = ler_arquivo("dono--repo", "grande.md", limite=200)
    assert len(lido["conteudo"]) == 200
    assert lido["truncado"] is True
