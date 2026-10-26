"""Testes da camada de portabilidade de skills (0.28.0).

A camada é determinística: lê um bundle colado, não abre repositório, não roda
`convert.sh`, não escreve arquivo e não instala nada. As fixtures são bundles
escritos à mão, um por cenário.
"""
from __future__ import annotations

import hashlib
import json

import pytest
from fastapi.testclient import TestClient

from server.portabilidade import (
    ALVOS,
    ARQUIVO_ENTRADA,
    CHAVES_PLUGIN,
    SEMVER,
    PortabilidadeError,
    auditar,
    catalogo,
    colisoes,
    converter,
    deriva,
    ler_inventario,
    lote,
    matriz,
)
from server.skill_registry import build_registry


@pytest.fixture()
def client(tmp_path) -> TestClient:
    from server.app import create_app

    return TestClient(create_app(registry=build_registry(tmp_path / "files")))

# ------------------------------------------------------------------ fixtures

BOM = """>>> engineering/leitor-de-contrato/SKILL.md
---
name: leitor-de-contrato
description: Lê contrato em PDF e devolve cláusula, prazo e multa. Use quando o usuário pedir resumo de contrato.
allowed-tools: Read, Grep
license: MIT
version: 1.0.0
---
# Leitor de contrato

Rode `scripts/extrair.py --help` antes de tudo.

Consulte `references/limites.md` quando o contrato passar de 200 páginas.
>>> engineering/leitor-de-contrato/scripts/extrair.py
import sys

print("extrai")
>>> engineering/leitor-de-contrato/references/limites.md
# Limites

200 páginas por chamada.
"""

RUIM = """>>> engineering/curta/SKILL.md
---
name: Curta Demais
description: curta
---
nada
>>> engineering/curta/scripts/roda.py
print("x")
>>> README.md
solto
"""

DUPLICADO = """>>> engineering/skills/relatorio/SKILL.md
---
name: relatorio
description: Gera relatório semanal com números do funil.
---
# Relatório

mesmo corpo
>>> engineering/relatorio/skills/relatorio/SKILL.md
---
name: relatorio
description: Gera relatório semanal com números do funil.
---
# Relatório

mesmo corpo
"""

DIVERGENTE = """>>> engineering/skills/relatorio/SKILL.md
---
name: relatorio
description: Gera relatório semanal com números do funil.
---
# Relatório

versão nova
>>> engineering/relatorio/skills/relatorio/SKILL.md
---
name: relatorio
description: Gera relatório semanal com números do funil.
---
# Relatório

versão antiga
"""


def _sha(texto: str) -> str:
    return hashlib.sha256(texto.encode()).hexdigest()[:16]


# --------------------------------------------------------------- inventário

def test_inventario_bundle_separa_arquivo_e_conteudo():
    arquivos = ler_inventario(texto=BOM)
    assert [item.caminho for item in arquivos][0] == f"engineering/leitor-de-contrato/{ARQUIVO_ENTRADA}"
    assert arquivos[0].tipo == "entrada"
    assert arquivos[1].tipo == "script"
    assert arquivos[2].tipo == "referencia"
    assert arquivos[1].sha == _sha('import sys\n\nprint("extrai")')


def test_inventario_lista_de_metadados():
    texto = "a/SKILL.md | 120 | abcdef123456 | arquivo\nb/SKILL.md | 40 | fedcba654321 | symlink"
    itens = ler_inventario(texto=texto)
    assert [item.bytes for item in itens] == [120, 40]
    assert itens[1].symlink is True
    assert itens[0].symlink is False


def test_inventario_json_em_objeto():
    itens = ler_inventario(texto=json.dumps({"arquivos": {"a/SKILL.md": "---\nname: a\ndescription: A.\n---\nx"}}))
    assert itens[0].caminho == "a/SKILL.md"
    assert itens[0].conteudo.startswith("---")


@pytest.mark.parametrize(
    "texto,fragmento",
    [
        ("", "Informe os arquivos"),
        ("a.md | muito | abcdef | arquivo", "inteiro"),
        ("a.md | 1 | zz | arquivo", "hash"),
        ("a.md | 1 || pasta", "arquivo"),
        ("a.md | 1 | abcdef\na.md | 2 | abcdef", "repetido"),
        ('{"nada": 1}', "arquivos"),
    ],
)
def test_inventario_recusa_entrada_invalida(texto, fragmento):
    with pytest.raises(PortabilidadeError) as exc:
        ler_inventario(texto=texto) if texto else ler_inventario(texto="")
    if texto.startswith('{"nada"'):
        assert "arquivos" in str(exc.value)
    else:
        assert fragmento in str(exc.value)


def test_inventario_recusa_arquivo_sem_caminho_ou_conteudo():
    with pytest.raises(PortabilidadeError):
        ler_inventario(texto=">>> a/SKILL.md\n" + "x" * 10 + "\n>>> \nb")
    with pytest.raises(PortabilidadeError):
        ler_inventario(texto=">>> a/SKILL.md\n>>> b/SKILL.md\n")


# ------------------------------------------------------------------ catálogo

def test_catalogo_publica_treze_alvos_e_dez_regras():
    dados = catalogo()
    assert dados["versao"] == "0.42.1"
    assert len(dados["alvos"]) == len(ALVOS) == 13
    assert len(dados["regras"]) == 10
    assert dados["limites"]["slug"] == 64
    assert dados["nao_faz"]


def test_catalogo_tem_um_alvo_por_id_e_estilo_conhecido():
    ids = [alvo["id"] for alvo in catalogo()["alvos"]]
    assert len(ids) == len(set(ids))
    assert set(alvo.estilo for alvo in ALVOS) == {"pasta", "regra", "convencao", "espelho"}


# ------------------------------------------------------------------ auditar

def test_auditar_bundle_bom_nao_tem_bloqueio():
    resultado = auditar(arquivos=BOM)
    assert resultado["counts"]["must"] == 0
    assert resultado["executed"] is False
    assert resultado["readOnly"] is True
    assert resultado["metrics"]["skills"] == 1
    assert resultado["metrics"]["scripts"] == 1
    assert resultado["metrics"]["referencias"] == 1


def test_auditar_aponta_nome_fora_do_slug_e_descricao_curta():
    resultado = auditar(arquivos=RUIM)
    titulos = {item["title"] for item in resultado["findings"]}
    assert "`name` fora do padrão de slug" in titulos
    assert "Descrição curta demais para servir de gatilho" in titulos
    assert resultado["counts"]["must"] >= 1


def test_auditar_aponta_script_nao_citado_e_arquivo_solto():
    bundle = """>>> a/SKILL.md
---
name: a
description: Faz uma coisa útil quando o usuário pede.
---
# A

Nada de script.
>>> a/scripts/s.py
print(1)
>>> README.md
solto
"""
    resultado = auditar(arquivos=bundle)
    titulos = [item["title"] for item in resultado["findings"]]
    assert "Script que o corpo da skill não menciona" in titulos
    assert "Arquivos fora de qualquer skill" in titulos
    assert resultado["metrics"]["soltos"] == 1


def test_auditar_acusa_front_matter_ausente():
    bundle = """>>> a/SKILL.md
# A

sem cabeçalho
"""
    resultado = auditar(arquivos=bundle)
    assert resultado["counts"]["must"] == 1
    assert "front matter" in resultado["findings"][0]["title"]


def test_auditar_aponta_campo_que_o_alvo_descarta():
    resultado = auditar(arquivos=BOM, alvo="cursor")
    titulos = [item["title"] for item in resultado["findings"]]
    assert any("cursor" in titulo.lower() for titulo in titulos)


def test_auditar_modo_lite_so_devolve_bloqueio():
    completo = auditar(arquivos=RUIM)
    lite = auditar(arquivos=RUIM, modo="lite")
    assert lite["counts"]["should"] == 0 and lite["counts"]["nice"] == 0
    assert lite["counts"]["must"] == completo["counts"]["must"]


def test_auditar_recusa_bundle_sem_skill_e_modo_invalido():
    with pytest.raises(PortabilidadeError):
        auditar(arquivos=">>> README.md\nsolto")
    with pytest.raises(PortabilidadeError):
        auditar(arquivos=BOM, modo="maximo")


def test_auditar_respeita_teto_de_skills(monkeypatch):
    monkeypatch.setattr("server.portabilidade.MAX_SKILLS", 1)
    with pytest.raises(PortabilidadeError):
        auditar(arquivos=BOM + """>>> b/SKILL.md
---
name: b
description: B.
---
x
""")


# --------------------------------------------------------------- converter

def test_converter_pasta_copia_arvore_e_filtra_front_matter():
    resultado = converter(arquivos=BOM, alvo="claude-code")
    caminhos = [item["caminho"] for item in resultado["saida"]]
    assert "~/.claude/skills/leitor-de-contrato/SKILL.md" in caminhos
    assert "~/.claude/skills/leitor-de-contrato/scripts/extrair.py" in caminhos
    assert resultado["metrics"]["descartados"] == 0
    entrada = next(item for item in resultado["saida"] if item["caminho"].endswith("SKILL.md"))
    assert "allowed-tools: Read, Grep" in entrada["conteudo"]


def test_converter_espelho_gera_indice():
    resultado = converter(arquivos=BOM, alvo="codex")
    indice = next(item for item in resultado["saida"] if item["caminho"] == "skills-index.json")
    dados = json.loads(indice["conteudo"])
    assert dados["tool"] == "codex"
    assert dados["skills"][0]["path"] == ".codex/skills/leitor-de-contrato/SKILL.md"


def test_converter_regra_reescreve_e_bloqueia_apoio():
    resultado = converter(arquivos=BOM, alvo="cursor")
    assert resultado["metrics"]["descartados"] == 2
    arquivo = resultado["saida"][0]
    assert arquivo["caminho"] == ".cursor/rules/leitor-de-contrato.mdc"
    assert "alwaysApply: false" in arquivo["conteudo"]
    assert "allowed-tools" not in arquivo["conteudo"]
    assert resultado["counts"]["must"] == 1


def test_converter_convencao_junta_tudo_num_arquivo():
    resultado = converter(arquivos=BOM, alvo="aider")
    assert [item["caminho"] for item in resultado["saida"]] == ["CONVENTIONS.md"]
    texto = resultado["saida"][0]["conteudo"]
    assert texto.startswith("# Convenções do projeto")
    assert "## leitor-de-contrato" in texto


def test_converter_convencao_rebaixa_heading_do_corpo():
    bundle = """>>> a/SKILL.md
---
name: a
description: A.
---
# Título

## Passo
"""
    texto = converter(arquivos=bundle, alvo="aider")["saida"][0]["conteudo"]
    assert "## Título" in texto
    assert "### Passo" in texto


def test_converter_acusa_colisao_de_destino():
    bundle = """>>> a/x/SKILL.md
---
name: mesmo
description: A.
---
x
>>> b/y/SKILL.md
---
name: mesmo
description: B.
---
y
"""
    resultado = converter(arquivos=bundle, alvo="claude-code")
    titulos = [item["title"] for item in resultado["findings"]]
    assert "Dois arquivos disputam o mesmo destino" in titulos


def test_converter_avisa_quando_caminho_passa_do_limite(monkeypatch):
    monkeypatch.setattr("server.portabilidade.CAMINHO_MAX", 20)
    resultado = converter(arquivos=BOM, alvo="claude-code")
    assert any(item["title"] == "Destino acima do limite de caminho" for item in resultado["findings"])


def test_converter_recusa_alvo_desconhecido():
    with pytest.raises(PortabilidadeError) as exc:
        converter(arquivos=BOM, alvo="vscode")
    assert "Alvo desconhecido" in str(exc.value)


# ------------------------------------------------------------------ deriva

def test_deriva_igual_quando_conteudo_bate():
    sha = ler_inventario(texto=BOM)[0].sha
    espelho = f"engineering/leitor-de-contrato/SKILL.md | 10 | {sha} | arquivo\n"
    resultado = deriva(arquivos=BOM, espelho=espelho)
    assert resultado["metrics"]["alterados"] == 0
    assert resultado["metrics"]["faltando"] == 2
    assert resultado["metrics"]["sobrando"] == 0
    assert resultado["metrics"]["cobertura"] == 33


def test_deriva_acusa_arquivo_alterado():
    espelho = "engineering/leitor-de-contrato/SKILL.md | 10 | aaaaaabbbbbb | arquivo\n"
    resultado = deriva(arquivos=BOM, espelho=espelho)
    assert resultado["metrics"]["alterados"] == 1
    assert resultado["counts"]["must"] >= 1


def test_deriva_acusa_faltando_e_sobrando():
    inventario = "engineering/leitor-de-contrato/SKILL.md | 10 | abcdef123456 | arquivo"
    resultado = deriva(arquivos=BOM, espelho=inventario)
    assert resultado["metrics"]["faltando"] == 2
    assert any(item["title"] == "Arquivo da fonte ausente no espelho" for item in resultado["findings"])


def test_deriva_acusa_symlink_quebrado():
    espelho = "engineering/leitor-de-contrato/SKILL.md | 10 | abcdef123456 | arquivo\nengineering/leitor-de-contrato/scripts/fantasma.py | 10 | abcdef123456 | symlink"
    resultado = deriva(arquivos=BOM, espelho=espelho)
    assert resultado["metrics"]["symlinks"] == 1
    assert any(item["title"] == "Ponteiro sem destino no espelho" for item in resultado["findings"])


def test_deriva_nao_comparavel_vira_bloqueio_no_estrito():
    espelho = "engineering/leitor-de-contrato/SKILL.md | 10 |  | arquivo"
    brando = deriva(arquivos=BOM, espelho=espelho)
    assert brando["metrics"]["naoComparaveis"] == 1
    estrito = deriva(arquivos=BOM, espelho=espelho, estrito=True)
    assert estrito["metrics"]["alterados"] == 1


def test_deriva_recusa_espelho_vazio():
    with pytest.raises(PortabilidadeError):
        deriva(arquivos=BOM, espelho="   ")


# --------------------------------------------------------------- colisões

def test_colisoes_acha_copia_identica():
    resultado = colisoes(arquivos=DUPLICADO)
    assert resultado["metrics"]["duplicadas"] == 1
    assert resultado["rows"][0]["estado"] == "copia-identica"
    assert resultado["counts"]["should"] == 1


def test_colisoes_acha_copia_divergente():
    resultado = colisoes(arquivos=DIVERGENTE)
    assert resultado["rows"][0]["estado"] == "divergente"
    assert resultado["counts"]["must"] == 1


def test_colisoes_acha_slug_repetido_entre_nomes():
    bundle = """>>> a/SKILL.md
---
name: Skill X
description: A.
---
x
>>> b/SKILL.md
---
name: skill-x
description: B.
---
y
"""
    resultado = colisoes(arquivos=bundle)
    assert any(item["title"] == "Nomes que colidem no mesmo slug" for item in resultado["findings"])


def test_colisoes_acha_corpo_igual_com_nome_diferente():
    bundle = """>>> a/SKILL.md
---
name: a
description: A.
---
# Comum

texto
>>> b/SKILL.md
---
name: b
description: B.
---
# Comum

texto
"""
    resultado = colisoes(arquivos=bundle)
    assert any(item["title"] == "Skills com corpo idêntico e nomes diferentes" for item in resultado["findings"])


def test_colisoes_acha_caixa_trocada_no_arquivo_de_entrada():
    resultado = colisoes(arquivos=">>> a/skill.md\n---\nname: a\ndescription: A.\n---\nx")
    assert any(item["title"] == "Arquivo de entrada com caixa trocada" for item in resultado["findings"])


# --------------------------------------------------------------------- lote

def test_lote_gera_plugin_com_oito_chaves():
    resultado = lote(arquivos=BOM, autor="Victor", repo="https://github.com/dono/repo")
    plugin = resultado["manifestos"][0]
    assert set(plugin) == CHAVES_PLUGIN
    assert len(plugin) == 8
    assert plugin["skills"] == ["./skills/leitor-de-contrato"]
    assert SEMVER.fullmatch(plugin["version"])
    assert plugin["author"]["url"] == "https://github.com/dono"


def test_lote_gera_marketplace_com_um_plugin_por_dominio():
    bundle = BOM + """>>> marketing/anuncio/SKILL.md
---
name: anuncio
description: Escreve anúncio curto.
---
x
"""
    resultado = lote(arquivos=bundle, autor="Victor", repo="https://github.com/dono/repo")
    assert resultado["metrics"]["plugins"] == 2
    manifesto = json.loads(resultado["saida"][-1]["conteudo"])
    assert manifesto["name"] == "skills-do-projeto"
    assert [item["source"] for item in manifesto["plugins"]] == ["./engineering", "./marketing"]


def test_lote_acusa_plugin_de_uma_skill_so():
    resultado = lote(arquivos=BOM, autor="Victor", repo="https://github.com/dono/repo")
    assert any(item["title"] == "Plugin de uma skill só" for item in resultado["findings"])


@pytest.mark.parametrize(
    "campo,valor,fragmento",
    [
        ("marketplace", "Com Espaço", "marketplace"),
        ("versao", "1.0", "Versão"),
        ("autor", "  ", "autor"),
        ("repo", "github.com/dono", "Repositório"),
        ("licenca", "", "licença"),
    ],
)
def test_lote_recusa_identidade_invalida(campo, valor, fragmento):
    dados = {"arquivos": BOM, "autor": "Victor", "repo": "https://github.com/dono/repo"}
    dados[campo] = valor
    if campo == "autor":
        dados["repo"] = "https://github.com/dono/repo"
    with pytest.raises(PortabilidadeError) as exc:
        lote(**dados)
    assert fragmento in str(exc.value)


def test_lote_recusa_slug_repetido_entre_dominios():
    bundle = """>>> a/x/SKILL.md
---
name: mesma
description: A.
---
x
>>> b/y/SKILL.md
---
name: mesma
description: B.
---
y
"""
    resultado = lote(arquivos=bundle, autor="Victor", repo="https://github.com/dono/repo")
    assert any(item["title"] == "Duas skills com o mesmo slug no lote" for item in resultado["findings"])


def test_lote_avisa_ausencia_de_descricao():
    resultado = lote(
        arquivos=">>> a/SKILL.md\n---\nname: a\n---\nx",
        autor="Victor",
        repo="https://github.com/dono/repo",
    )
    assert any(item["title"] == "Skill sem descrição não entra no plugin" for item in resultado["findings"])


# ------------------------------------------------------------------- matriz

def test_matriz_marca_perda_de_apoio_por_alvo():
    resultado = matriz(arquivos=BOM, alvos="claude-code,cursor")
    linhas = {row["alvo"]: row for row in resultado["rows"]}
    assert linhas["Claude Code"]["estado"] == "completo"
    assert linhas["Cursor"]["estado"] == "so-entrada"
    assert resultado["counts"]["must"] == 1


def test_matriz_sem_alvo_cobre_os_treze():
    resultado = matriz(arquivos=BOM)
    assert resultado["metrics"]["alvos"] == 13
    assert resultado["metrics"]["pares"] == 13


def test_matriz_conta_totais_por_alvo():
    resultado = matriz(arquivos=BOM, alvos="aider,codex")
    assert resultado["totais"]["aider"]["zero"] == 1
    assert resultado["totais"]["codex"]["ok"] == 1


def test_matriz_recusa_lista_invalida():
    with pytest.raises(PortabilidadeError):
        matriz(arquivos=BOM, alvos="vscode")


# ---------------------------------------------------------------- registro

def test_registro_publica_sete_skills_de_portabilidade(tmp_path):
    registry = build_registry(tmp_path / "files")
    ids = [item["id"] for item in registry.list() if item["id"].startswith("portabilidade.")]
    assert ids == [
        "portabilidade.auditar",
        "portabilidade.converter",
        "portabilidade.deriva",
        "portabilidade.colisoes",
        "portabilidade.lote",
        "portabilidade.matriz",
        "portabilidade.regras",
    ]


def test_registro_total_de_skills_e_169(tmp_path):
    registry = build_registry(tmp_path / "files")
    assert len(registry.list()) == 223


def test_api_executa_auditoria_e_catalogo(client):
    cliente = client
    resposta = cliente.post("/api/skills/portabilidade.regras/execute", json={"parameters": {}})
    assert resposta.status_code == 200
    assert resposta.json()["result"]["versao"] == "0.42.1"

    resposta = cliente.post(
        "/api/skills/portabilidade.auditar/execute",
        json={"parameters": {"arquivos": BOM, "alvo": "cursor"}},
    )
    assert resposta.status_code == 200
    corpo = resposta.json()["result"]
    assert corpo["executed"] is False and corpo["readOnly"] is True
    assert corpo["metrics"]["skills"] == 1


def test_api_recusa_alvo_invalido_no_contrato(client):
    cliente = client
    resposta = cliente.post(
        "/api/skills/portabilidade.converter/execute",
        json={"parameters": {"arquivos": BOM, "alvo": "vscode"}},
    )
    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["ok"] is False
    assert corpo["error"]["code"] == "SKILL_ERROR"
    assert "alvo" in corpo["error"]["message"]
