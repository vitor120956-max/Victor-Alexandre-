"""Testes do catálogo de habilidades de terceiros (CSV → índice → importação)."""
from __future__ import annotations

from pathlib import Path

import pytest

from server import catalogo

CSV = """rank,skill,vendor,repo_url,url,category,description,install
1,frontend-design,anthropics,https://github.com/anthropics/skills,https://skills.sh/a,"design-media","Design de front-end, com vírgula",npx skills add a
2,web-design-guidelines,vercel-labs,https://github.com/vercel-labs/agent-skills,,design-media,Diretrizes de interface,
2,web-design-guidelines,vercel-labs,https://github.com/vercel-labs/agent-skills,,design-media,duplicada,
7,nano-banana-pro,steipete,,https://clawhub.ai/steipete/skills/nano-banana-pro,design-media,Gera imagem,
9,tdd,mattpocock,https://github.com/mattpocock/skills,,dev-programming,Testes primeiro,
"""


@pytest.fixture()
def planilha(tmp_path: Path) -> Path:
    caminho = tmp_path / "skills.csv"
    caminho.write_text(CSV, encoding="utf-8-sig")
    return caminho


def test_interpretar_normaliza_e_remove_duplicata(planilha: Path):
    itens = catalogo.interpretar_csv(planilha.read_text(encoding="utf-8-sig"))
    assert [item["skill"] for item in itens] == [
        "frontend-design",
        "web-design-guidelines",
        "nano-banana-pro",
        "tdd",
    ]
    assert itens[0]["description"] == "Design de front-end, com vírgula"


def test_carregar_guarda_e_resume(planilha: Path, tmp_path: Path):
    resumo = catalogo.carregar(planilha, raiz=tmp_path)
    assert resumo["total"] == 4
    assert resumo["por_categoria"] == {"design-media": 3, "dev-programming": 1}
    assert resumo["por_fornecedor"]["anthropics"] == 1
    assert (tmp_path / catalogo.ARQUIVO).exists()


def test_csv_sem_coluna_skill_recusa(tmp_path: Path):
    arquivo = tmp_path / "x.csv"
    arquivo.write_text("rank,nome\n1,a\n", encoding="utf-8")
    with pytest.raises(catalogo.CatalogoError):
        catalogo.interpretar_csv(arquivo.read_text(encoding="utf-8"))


def test_csv_vazio_recusa():
    with pytest.raises(catalogo.CatalogoError):
        catalogo.interpretar_csv("")


def test_csv_com_ponto_e_virgula(tmp_path: Path):
    texto = "rank;skill;repo_url;vendor;category\n1;tdd;https://github.com/a/b;mattpocock;dev-programming\n"
    itens = catalogo.interpretar_csv(texto)
    assert itens[0]["skill"] == "tdd"


def test_filtrar_por_categoria_e_fornecedor(planilha: Path, tmp_path: Path):
    catalogo.carregar(planilha, raiz=tmp_path)
    assert catalogo.filtrar(tmp_path, categoria="design")["total"] == 3
    assert catalogo.filtrar(tmp_path, fornecedor="mattpocock")["total"] == 1
    assert catalogo.filtrar(tmp_path, de_rank=2, ate_rank=7)["total"] == 2


def test_filtrar_sem_catalogo_ensina(tmp_path: Path):
    with pytest.raises(catalogo.CatalogoError) as erro:
        catalogo.filtrar(tmp_path)
    assert "catalogo-skills.csv" in str(erro.value)


def test_filtrar_vazio_devolve_zero(planilha: Path, tmp_path: Path):
    catalogo.carregar(planilha, raiz=tmp_path)
    assert catalogo.filtrar(tmp_path, texto="inexistente")["total"] == 0


def test_endereco_da_skill_usa_a_arvore(monkeypatch, planilha: Path, tmp_path: Path):
    catalogo._arvores.clear()
    monkeypatch.setattr(
        catalogo.github,
        "arvore",
        lambda *a, **k: ["skills/composition-patterns/SKILL.md", "skills/web-design-guidelines/SKILL.md"],
    )
    url = catalogo._endereco_da_skill("https://github.com/vercel-labs/agent-skills", "web-design-guidelines")
    assert url == "https://raw.githubusercontent.com/vercel-labs/agent-skills/HEAD/skills/web-design-guidelines/SKILL.md"


def test_importar_do_catalogo_uma_a_uma(monkeypatch, planilha: Path, tmp_path: Path):
    catalogo.carregar(planilha, raiz=tmp_path)
    catalogo._arvores.clear()
    arvores = {
        "anthropics/skills": ["skills/frontend-design/SKILL.md"],
        "vercel-labs/agent-skills": ["skills/web-design-guidelines/SKILL.md"],
    }
    monkeypatch.setattr(catalogo.github, "arvore", lambda repo, **k: arvores.get(repo, []))

    def baixar(url: str) -> str:
        return "---\nname: " + url.split("/")[-2] + "\n---\n# Guia\n\nFaça.\n"

    resultado = catalogo.importar(tmp_path, quantos=3, categoria="design", baixar=baixar)
    assert resultado["tentadas"] == 3
    assert [item["slug"] for item in resultado["importadas"]] == ["frontend-design", "web-design-guidelines"]
    assert [falha["skill"] for falha in resultado["falhas"]] == ["nano-banana-pro"]


def test_importar_respeita_o_teto_de_dez(monkeypatch, planilha: Path, tmp_path: Path):
    catalogo.carregar(planilha, raiz=tmp_path)
    monkeypatch.setattr(catalogo.github, "arvore", lambda *a, **k: [])
    resultado = catalogo.importar(tmp_path, quantos=50, baixar=lambda url: "# X\n\nY\n")
    assert resultado["tentadas"] <= catalogo.MAX_IMPORTAR


def test_linha_sem_repositorio_volta_como_falha(monkeypatch, planilha: Path, tmp_path: Path):
    catalogo.carregar(planilha, raiz=tmp_path)
    monkeypatch.setattr(catalogo.github, "arvore", lambda *a, **k: [])
    resultado = catalogo.importar(tmp_path, quantos=1, texto="nano-banana-pro", baixar=lambda url: "# X\n\nY\n")
    assert resultado["falhas"][0]["skill"] == "nano-banana-pro"


def test_skill_fora_da_arvore_nao_baixa_o_repositorio(monkeypatch, planilha: Path, tmp_path: Path):
    catalogo.carregar(planilha, raiz=tmp_path)
    catalogo._arvores.clear()
    monkeypatch.setattr(catalogo.github, "arvore", lambda *a, **k: ["skills/outra/SKILL.md"])
    baixados: list[str] = []

    def baixar(url: str) -> str:
        baixados.append(url)
        return "# X\n\nY\n"

    resultado = catalogo.importar(tmp_path, quantos=2, categoria="design", baixar=baixar)
    assert resultado["importadas"] == []
    assert "não achei a pasta" in resultado["falhas"][0]["erro"]
    assert baixados == []


def test_arvore_indisponivel_tenta_o_repositorio(monkeypatch, planilha: Path, tmp_path: Path):
    catalogo.carregar(planilha, raiz=tmp_path)
    catalogo._arvores.clear()

    def falha(*_a, **_k):
        raise catalogo.github.GithubError("limite")

    monkeypatch.setattr(catalogo.github, "arvore", falha)
    resultado = catalogo.importar(tmp_path, quantos=1, texto="tdd", baixar=lambda url: "# TDD\n\nTeste.\n")
    assert resultado["falhas"] == []
    assert resultado["importadas"][0]["repo_url"] == "https://github.com/mattpocock/skills"


def test_falha_de_linha_de_plataforma_traz_o_comando(monkeypatch, tmp_path: Path):
    csv_texto = (
        "rank,skill,repo_url,url,install,category\n"
        "9,nano-banana-pro,,https://clawhub.ai/x/nano-banana-pro,openclaw skills install @x/nano-banana-pro,design-media\n"
    )
    arquivo = tmp_path / "skills.csv"
    arquivo.write_text(csv_texto, encoding="utf-8")
    catalogo.carregar(arquivo, raiz=tmp_path)
    resultado = catalogo.importar(tmp_path, quantos=1, baixar=lambda url: "# X\n\nY\n")
    falha = resultado["falhas"][0]
    assert falha["install"] == "openclaw skills install @x/nano-banana-pro"


# ------------------------------------------------- tópico do GitHub (0.53.0)

REPOS = [
    {"repositorio": "anthropics/skills", "descricao": "Public repository for Agent Skills", "estrelas": 10},
    {"repositorio": "vazio/repo", "descricao": "design sem skill", "estrelas": 5},
]
ARVORES = {
    "anthropics/skills": ["skills/frontend-design/SKILL.md", "README.md"],
    "vazio/repo": ["README.md"],
}


def _topico(tmp_path: Path, **extra):
    return catalogo.topico(
        "agent-skills",
        raiz=tmp_path,
        repos=2,
        consultar=lambda consulta, limite=0: REPOS,
        arvore=lambda repo, **k: ARVORES.get(repo, []),
        **extra,
    )


def test_topico_le_repos_e_acha_as_skills(tmp_path: Path):
    resumo = _topico(tmp_path)
    assert resumo["total"] == 1
    assert resumo["repos_com_skill"] == 1
    assert resumo["sem_skill"] == ["vazio/repo"]
    assert resumo["por_categoria"] == {"ai-agent": 1}
    linha = catalogo.ler(tmp_path)[0]
    assert linha["skill"] == "frontend-design"
    assert linha["vendor"] == "anthropics"
    assert linha["url"].endswith("/skills/frontend-design/SKILL.md")


def test_topico_soma_ao_catalogo_existente(tmp_path: Path):
    planilha = tmp_path / "skills.csv"
    planilha.write_text(
        "rank,skill,repo_url,category\n9,tdd,https://github.com/mattpocock/skills,dev-programming\n",
        encoding="utf-8",
    )
    catalogo.carregar(planilha, raiz=tmp_path)
    resumo = _topico(tmp_path)
    assert resumo["total"] == 2
    assert [item["skill"] for item in catalogo.ler(tmp_path)] == ["tdd", "frontend-design"]


def test_topico_nao_repete_na_segunda_leitura(tmp_path: Path):
    _topico(tmp_path)
    resumo = _topico(tmp_path)
    assert resumo["total"] == 1
    assert resumo["adicionadas"] == 1


def test_topico_usa_a_lista_guardada_quando_o_github_falha(tmp_path: Path):
    def falha(*_a, **_k):
        raise catalogo.github.GithubError("limite de 60 por hora")

    resumo = catalogo.topico(
        "agent-skills",
        raiz=tmp_path,
        repos=3,
        consultar=falha,
        arvore=lambda repo, **k: [f"skills/{repo.split('/')[-1]}/SKILL.md"],
    )
    assert "lista guardada" in resumo["aviso"]
    assert resumo["total"] >= 1


def test_topico_sem_rede_e_sem_lista_recusa(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(catalogo, "_sementes", lambda tema: [])

    def falha(*_a, **_k):
        raise catalogo.github.GithubError("sem rede")

    with pytest.raises(catalogo.CatalogoError):
        catalogo.topico(raiz=tmp_path, consultar=falha, arvore=lambda *a, **k: [])
