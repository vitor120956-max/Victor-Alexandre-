"""Testes das habilidades de fora (SKILL.md): puxar, guardar e usar como guia."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from server import habilidades
from server.busca_web import BuscaError

SKILL = """---
name: frontend-design
description: Diretrizes de design de front-end
allowed-tools: Read, Write
version: 1.2
---
# Front-end

Comece pelo contraste e pelo espaçamento.

1. Contraste mínimo de 4.5:1
2. Um acento por tela
"""


def baixar_com(mapa: dict[str, str]):
    chamadas: list[str] = []

    def baixar(url: str) -> str:
        chamadas.append(url)
        if url in mapa:
            return mapa[url]
        raise BuscaError(f"404 em {url}")

    baixar.chamadas = chamadas  # type: ignore[attr-defined]
    return baixar


# --------------------------------------------------------------- endereços


def test_github_blob_vira_raw():
    urls = habilidades.enderecos_candidatos(
        "https://github.com/anthropics/skills/blob/main/skills/frontend-design/SKILL.md"
    )
    assert urls == ["https://raw.githubusercontent.com/anthropics/skills/main/skills/frontend-design/SKILL.md"]


def test_github_tree_aponta_para_o_skill_md():
    urls = habilidades.enderecos_candidatos("https://github.com/vercel-labs/agent-skills/tree/main/skills/browser")
    assert urls[0].endswith("/main/skills/browser/SKILL.md")


def test_repositorio_sem_caminho_tenta_os_lugares_conhecidos():
    urls = habilidades.enderecos_candidatos("https://github.com/vercel-labs/agent-skills")
    assert urls[0] == "https://raw.githubusercontent.com/vercel-labs/agent-skills/HEAD/SKILL.md"
    assert any("/skills/" in url for url in urls)


def test_link_raw_passa_direto():
    url = "https://raw.githubusercontent.com/a/b/main/SKILL.md"
    assert habilidades.enderecos_candidatos(url) == [url]


def test_catalogo_fora_do_github_e_aceito_como_pagina():
    assert habilidades.enderecos_candidatos("https://www.skills.sh/anthropics") == [
        "https://www.skills.sh/anthropics"
    ]


def test_endereco_privado_e_recusado():
    with pytest.raises(habilidades.HabilidadeError):
        habilidades.enderecos_candidatos("http://127.0.0.1:8000/SKILL.md")


def test_link_sem_dono_e_recusado():
    with pytest.raises(habilidades.HabilidadeError):
        habilidades.enderecos_candidatos("https://github.com/github")


# ---------------------------------------------------------------- markdown


def test_front_matter_e_corpo():
    cabecalho, corpo = habilidades.separar_front_matter(SKILL)
    assert cabecalho["name"] == "frontend-design"
    assert cabecalho["allowed-tools"] == "Read, Write"
    assert corpo.startswith("# Front-end")
    assert "Contraste" in corpo


def test_sem_front_matter_usa_o_titulo():
    ficha = habilidades.interpretar("# Browser Agent\n\nNavegue como gente.\n")
    assert ficha["nome"] == "Browser Agent"
    assert ficha["slug"] == "browser-agent"
    assert ficha["descricao"] == "Navegue como gente."


def test_arquivo_vazio_e_recusado():
    with pytest.raises(habilidades.HabilidadeError):
        habilidades.interpretar("---\nname: x\n---\n   \n")


# ---------------------------------------------------------------- importar


def test_importar_guarda_e_devolve_ficha(tmp_path: Path):
    baixar = baixar_com(
        {"https://raw.githubusercontent.com/a/b/main/SKILL.md": SKILL}
    )
    ficha = habilidades.importar("https://github.com/a/b/blob/main/SKILL.md", raiz=tmp_path, baixar=baixar)
    assert ficha["slug"] == "frontend-design"
    assert ficha["novo"] is True
    assert ficha["tamanho"] > 50
    guardado = json.loads((tmp_path / habilidades.ARQUIVO).read_text(encoding="utf-8"))
    assert guardado["habilidades"][0]["nome"] == "frontend-design"


def test_importar_de_novo_atualiza(tmp_path: Path):
    baixar = baixar_com({"https://raw.githubusercontent.com/a/b/main/SKILL.md": SKILL})
    habilidades.importar("https://github.com/a/b/blob/main/SKILL.md", raiz=tmp_path, baixar=baixar)
    segunda = habilidades.importar("https://github.com/a/b/blob/main/SKILL.md", raiz=tmp_path, baixar=baixar)
    assert segunda["novo"] is False
    assert len(habilidades.carregar(tmp_path)) == 1


def test_importar_de_catalogo_segue_o_link_interno(tmp_path: Path):
    vitrine = '<html><a href="https://github.com/x/y/blob/main/skills/grill/SKILL.md">SKILL</a></html>'
    baixar = baixar_com(
        {
            "https://www.skills.sh/mattpocock": vitrine,
            "https://raw.githubusercontent.com/x/y/main/skills/grill/SKILL.md": SKILL,
        }
    )
    ficha = habilidades.importar("https://www.skills.sh/mattpocock", raiz=tmp_path, baixar=baixar)
    assert ficha["url"] == "https://raw.githubusercontent.com/x/y/main/skills/grill/SKILL.md"
    assert ficha["slug"] == "frontend-design"


def test_importar_sem_achar_nada_explica_o_que_fazer(tmp_path: Path):
    baixar = baixar_com({})
    with pytest.raises(habilidades.HabilidadeError) as erro:
        habilidades.importar("https://github.com/a/b", raiz=tmp_path, baixar=baixar)
    assert "Raw" in str(erro.value)


# ------------------------------------------------------------- listar/usar


def test_listar_nao_devolve_o_texto_inteiro(tmp_path: Path):
    baixar = baixar_com({"https://raw.githubusercontent.com/a/b/main/SKILL.md": SKILL})
    habilidades.importar("https://github.com/a/b/blob/main/SKILL.md", raiz=tmp_path, baixar=baixar)
    itens = habilidades.listar(tmp_path)
    assert itens and "texto" not in itens[0]
    assert itens[0]["nome"] == "frontend-design"


def test_guia_por_pedaco_do_nome(tmp_path: Path):
    baixar = baixar_com({"https://raw.githubusercontent.com/a/b/main/SKILL.md": SKILL})
    habilidades.importar("https://github.com/a/b/blob/main/SKILL.md", raiz=tmp_path, baixar=baixar)
    guia = habilidades.guia("frontend", raiz=tmp_path)
    assert "Contraste" in guia["texto"]
    assert guia["cortado"] is False


def test_guia_corta_no_limite(tmp_path: Path):
    baixar = baixar_com({"https://raw.githubusercontent.com/a/b/main/SKILL.md": SKILL})
    habilidades.importar("https://github.com/a/b/blob/main/SKILL.md", raiz=tmp_path, baixar=baixar)
    guia = habilidades.guia("frontend-design", raiz=tmp_path, limite=20)
    assert len(guia["texto"]) == 20
    assert guia["cortado"] is True


def test_guia_de_habilidade_inexistente_ensina_o_comando(tmp_path: Path):
    with pytest.raises(habilidades.HabilidadeError) as erro:
        habilidades.guia("nada-a-ver", raiz=tmp_path)
    assert "importa a habilidade" in str(erro.value)


def test_remover(tmp_path: Path):
    baixar = baixar_com({"https://raw.githubusercontent.com/a/b/main/SKILL.md": SKILL})
    habilidades.importar("https://github.com/a/b/blob/main/SKILL.md", raiz=tmp_path, baixar=baixar)
    assert habilidades.remover("frontend-design", tmp_path) is True
    assert habilidades.listar(tmp_path) == []
    assert habilidades.remover("frontend-design", tmp_path) is False


def test_arquivo_corrompido_nao_derruba_a_lista(tmp_path: Path):
    (tmp_path / habilidades.ARQUIVO).write_text("{ isso não é json", encoding="utf-8")
    assert habilidades.listar(tmp_path) == []


def test_modulo_nao_esta_no_gitignore():
    raiz = Path(__file__).resolve().parents[2]
    ignorados = {linha.strip() for linha in (raiz / ".gitignore").read_text(encoding="utf-8").splitlines()}
    assert "server/habilidades.py" not in ignorados


def test_repositorio_com_pastas_descobre_o_primeiro_skill_md(tmp_path: Path, monkeypatch):
    """`vercel-labs/agent-skills` não tem SKILL.md na raiz: a árvore da API acha."""
    monkeypatch.setattr(
        "server.github.arvore",
        lambda *a, **k: ["skills/composition-patterns/SKILL.md", "skills/react-best-practices/SKILL.md"],
    )
    baixar = baixar_com(
        {
            "https://raw.githubusercontent.com/vercel-labs/agent-skills/HEAD/skills/composition-patterns/SKILL.md": SKILL,
            "https://raw.githubusercontent.com/vercel-labs/agent-skills/HEAD/skills/react-best-practices/SKILL.md": SKILL.replace(
                "frontend-design", "react-best-practices"
            ),
        }
    )
    ficha = habilidades.importar("https://github.com/vercel-labs/agent-skills", raiz=tmp_path, baixar=baixar)
    assert ficha["url"].endswith("composition-patterns/SKILL.md")
    assert len(ficha["outros"]) == 1
    assert ficha["outros"][0].endswith("react-best-practices/SKILL.md")


def test_sem_arvore_e_sem_skill_md_avisa(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("server.github.arvore", lambda *a, **k: [])
    with pytest.raises(habilidades.HabilidadeError):
        habilidades.importar("https://github.com/a/b", raiz=tmp_path, baixar=baixar_com({}))


def test_importar_varias_mantem_as_duas_quando_o_slug_repete(tmp_path: Path):
    baixar = baixar_com(
        {
            "https://raw.githubusercontent.com/a/b/main/x/SKILL.md": "# Skill\n\nUm.\n",
            "https://raw.githubusercontent.com/c/d/main/y/SKILL.md": "# Skill\n\nDois.\n",
        }
    )
    resultado = habilidades.importar_varias(
        "https://github.com/a/b/blob/main/x/SKILL.md e https://github.com/c/d/blob/main/y/SKILL.md",
        raiz=tmp_path,
        baixar=baixar,
    )
    assert [item["slug"] for item in resultado["importadas"]] == ["skill", "skill-2"]
    assert len(habilidades.carregar(tmp_path)) == 2


def test_importar_varias_conta_falhas_e_restantes(tmp_path: Path):
    baixar = baixar_com({"https://raw.githubusercontent.com/a/b/main/x/SKILL.md": SKILL})
    links = "\n".join(
        [
            "https://github.com/a/b/blob/main/x/SKILL.md",
            "https://github.com/a/b/blob/main/nao-existe/SKILL.md",
            "https://github.com/a/b/blob/main/tres/SKILL.md",
        ]
    )
    resultado = habilidades.importar_varias(links, raiz=tmp_path, baixar=baixar, limite=2)
    assert resultado["tentadas"] == 2
    assert len(resultado["importadas"]) == 1
    assert len(resultado["falhas"]) == 1
    assert resultado["restantes"] == 1


def test_importar_varias_sem_link_recusa(tmp_path: Path):
    with pytest.raises(habilidades.HabilidadeError):
        habilidades.importar_varias("nenhum link aqui", raiz=tmp_path)


# -------------------------------------------------- passos e adaptação (0.53.0)

GUIA_MD = """---
name: frontend-design
description: Guia de direção de arte.
---

# Frontend Design

## When to use
Quando a tela precisa de ponto de vista.

## How to use
1. Escolha uma direção ousada e vá até o fim.
2. Use uma escala tipográfica com contraste.
3. Confira o contraste antes de escolher cor.

## Limits
É orientação, não código.
"""


def test_passos_de_le_secao_de_como_usar():
    passos = habilidades.passos_de(GUIA_MD)
    assert passos[0].startswith("Escolha uma direção")
    assert len(passos) == 3


def test_passos_de_cai_para_marcadores_soltos():
    texto = "# Guia\n\n- Primeiro passo bem descrito.\n- Segundo passo também descrito.\n"
    assert len(habilidades.passos_de(texto)) == 2


def test_passos_de_usa_subtitulos_quando_nao_ha_lista():
    texto = "# Guia\n\n## Preparar o ambiente\n\nTexto.\n\n## Rodar os testes\n\nTexto.\n"
    assert habilidades.passos_de(texto) == ["Preparar o ambiente", "Rodar os testes"]


def test_adaptar_vira_skill_local(tmp_path: Path):
    store = tmp_path / "store"
    store.mkdir()
    habilidades.importar("https://github.com/a/b/blob/main/skills/frontend-design/SKILL.md", raiz=store, baixar=lambda url: GUIA_MD)
    agente = tmp_path
    ficha = habilidades.adaptar("frontend-design", raiz=store, pasta_agente=agente)
    assert ficha["skill_local"] == "local.proc-frontend-design"
    assert ficha["passos"] == 3
    assert ficha["criada"] is True
    assert (agente / "agente-local" / "skills.json").exists()

    de_novo = habilidades.adaptar("frontend-design", raiz=store, pasta_agente=agente)
    assert de_novo["criada"] is False


def test_adaptar_recusa_guia_sem_passos(tmp_path: Path):
    store = tmp_path / "store"
    store.mkdir()
    texto = "---\nname: prosa\n---\n\n" + ("Palavra solta em prosa sem lista alguma. " * 30)
    habilidades.importar("https://github.com/a/b/blob/main/skills/prosa/SKILL.md", raiz=store, baixar=lambda url: texto)
    with pytest.raises(habilidades.HabilidadeError):
        habilidades.adaptar("prosa", raiz=store, pasta_agente=tmp_path)
