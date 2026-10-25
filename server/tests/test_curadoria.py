"""Testes do motor de curadoria inspirado em hesreallyhim/awesome-claude-code.

O upstream é CC BY-NC-ND 4.0: nada do catálogo curado, das descrições ou das
categorias dele é reproduzido aqui. O que os testes cobrem é o mecanismo —
schema de 12 colunas, elegibilidade, validação da entrada, agrupamento, README,
ticker e higiene — rodando sobre um catálogo de exemplo.
"""
from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from server.app import create_app
from server.curadoria import (
    CATEGORIAS,
    COLUNAS,
    CuradoriaError,
    auditar_descricao,
    auditar_higiene,
    comparar_ticker,
    curadoria_catalogo,
    gerar_readme,
    montar_catalogo,
    validar_entrada,
)
from server.skill_registry import build_registry

HOJE = "2026-10-23"

CSV = """id,nome,categoria,subcategoria,link,autor,link_autor,ativo,adicionado_em,checado_em,descricao,estagnado
4f1a2b3c,Fluxo de skills,Skills e comandos,Revisão de código,https://github.com/exemplo/fluxo,Ana Lima,https://github.com/analima,TRUE,2026-05-01,2026-09-20,Revisa o diff antes do merge e registra a decisão.,FALSE
9e8d7c6b,Memória local,Memória e contexto,,https://github.com/exemplo/memoria,Beto Sá,https://github.com/betosa,TRUE,2026-04-11,2026-08-01,Guarda decisões entre sessões em arquivo local.,FALSE
11223344,Trilha de custo,Observabilidade,Custo e uso,https://github.com/exemplo/trilha,Carla Dias,https://github.com/carladias,TRUE,2026-06-02,2026-10-01,Soma o custo por sessão e mostra as chamadas mais caras.,FALSE
"""


@pytest.fixture(scope="module")
def client(tmp_path_factory: pytest.TempPathFactory) -> TestClient:
    return TestClient(create_app(registry=build_registry(tmp_path_factory.mktemp("curadoria"))))


def kinds(resultado: dict) -> set[str]:
    return {achado["kind"] for achado in resultado["findings"]}


# ------------------------------------------------------------------ entrada


def test_entry_is_eligible_by_age() -> None:
    entrada = validar_entrada(
        nome="Fluxo de skills", link="https://github.com/exemplo/fluxo",
        autor="Ana Lima", link_autor="https://github.com/analima",
        categoria="Skills e comandos", subcategoria="Revisão de código",
        descricao="Revisa o diff antes do merge e registra a decisão.",
        licenca="MIT", dias_desde_o_primeiro_commit=40,
        commits_depois_do_primeiro_dia=12, estrelas=7, hoje=HOJE, semente="x",
    )
    assert entrada["elegivel"] is True
    assert entrada["counts"]["must"] == 0
    assert entrada["metrics"]["regra"] == "idade"
    assert entrada["executado"] is False
    assert entrada["readOnly"] is True


def test_entry_line_has_twelve_columns_and_an_opaque_id() -> None:
    entrada = validar_entrada(
        nome="Fluxo de skills", link="https://github.com/exemplo/fluxo",
        autor="Ana Lima", link_autor="https://github.com/analima",
        categoria="Skills e comandos", descricao="Revisa o diff antes do merge.",
        licenca="MIT", dias_desde_o_primeiro_commit=40,
        commits_depois_do_primeiro_dia=3, hoje=HOJE,
    )
    assert len(entrada["linha"].split(",")) == len(COLUNAS) == 12
    assert len(entrada["id"]) == 8
    assert all(c in "0123456789abcdef" for c in entrada["id"])
    assert entrada["linha"].startswith(entrada["id"] + ",")
    assert entrada["linha"].endswith(",FALSE")


def test_entry_id_is_deterministic_with_a_seed() -> None:
    def montar() -> str:
        return validar_entrada(
            nome="Fluxo de skills", link="https://github.com/exemplo/fluxo",
            autor="Ana Lima", link_autor="https://github.com/analima",
            categoria="Skills e comandos", descricao="Revisa o diff antes do merge.",
            licenca="MIT", dias_desde_o_primeiro_commit=40,
            commits_depois_do_primeiro_dia=3, hoje=HOJE, semente="mesma",
        )["id"]

    assert montar() == montar()


def test_entry_is_ineligible_before_fourteen_days() -> None:
    entrada = validar_entrada(
        nome="Projeto novo", link="https://github.com/exemplo/novo",
        autor="Ana Lima", link_autor="https://github.com/analima",
        categoria="Comece aqui", descricao="Faz uma coisa pequena e clara.",
        licenca="MIT", dias_desde_o_primeiro_commit=10,
        commits_depois_do_primeiro_dia=9, estrelas=3, hoje=HOJE,
    )
    assert entrada["elegivel"] is False
    assert "inelegivel" in kinds(entrada)
    assert entrada["metrics"]["regra"] == "nenhuma"


def test_entry_with_age_but_no_activity_is_rejected() -> None:
    entrada = validar_entrada(
        nome="Projeto parado", link="https://github.com/exemplo/parado",
        autor="Ana Lima", link_autor="https://github.com/analima",
        categoria="Comece aqui", descricao="Faz uma coisa pequena e clara.",
        licenca="MIT", dias_desde_o_primeiro_commit=20,
        commits_depois_do_primeiro_dia=0, hoje=HOJE,
    )
    assert entrada["elegivel"] is False
    assert "sem-atividade" in kinds(entrada)


def test_entry_can_be_eligible_by_stars_alone() -> None:
    entrada = validar_entrada(
        nome="Projeto popular", link="https://github.com/exemplo/popular",
        autor="Ana Lima", link_autor="https://github.com/analima",
        categoria="Comece aqui", descricao="Faz uma coisa pequena e clara.",
        licenca="MIT", dias_desde_o_primeiro_commit=3,
        commits_depois_do_primeiro_dia=1, estrelas=100, hoje=HOJE,
    )
    assert entrada["elegivel"] is True
    assert entrada["metrics"]["regra"] == "estrelas"


def test_entry_rejects_links_that_break_markdown() -> None:
    ruim = validar_entrada(
        nome="Projeto X", link="http://exemplo.com/x",
        autor="Ana Lima", link_autor="https://github.com/analima",
        categoria="Comece aqui", descricao="Faz uma coisa pequena e clara.",
        licenca="MIT", dias_desde_o_primeiro_commit=40,
        commits_depois_do_primeiro_dia=2, hoje=HOJE,
    )
    assert "url-invalida" in kinds(ruim)

    aspas = validar_entrada(
        nome="Projeto X", link='https://exemplo.com/x"<img>',
        autor="Ana Lima", link_autor="https://github.com/analima",
        categoria="Comece aqui", descricao="Faz uma coisa pequena e clara.",
        licenca="MIT", dias_desde_o_primeiro_commit=40,
        commits_depois_do_primeiro_dia=2, hoje=HOJE,
    )
    assert "url-invalida" in kinds(aspas)


def test_entry_rejects_unknown_closed_and_orphan_categories() -> None:
    base = dict(nome="Projeto X", link="https://exemplo.com/x", autor="Ana Lima",
                link_autor="https://github.com/analima", descricao="Faz uma coisa clara.",
                licenca="MIT", dias_desde_o_primeiro_commit=40,
                commits_depois_do_primeiro_dia=2, hoje=HOJE)

    desconhecida = validar_entrada(categoria="Cripto", **base)
    assert "categoria-desconhecida" in kinds(desconhecida)

    fechada = validar_entrada(categoria="Coleções", **base)
    assert "categoria-fechada" in kinds(fechada)

    orfa = validar_entrada(categoria="Skills e comandos", subcategoria="Deploy", **base)
    assert "subcategoria-orfa" in kinds(orfa)


def test_entry_flags_license_access_and_description_style() -> None:
    entrada = validar_entrada(
        nome="Marketing GPT", link="https://exemplo.com/mkt",
        autor="Ana Lima", link_autor="https://github.com/analima",
        categoria="Comece aqui",
        descricao="O melhor e mais revolucionário jeito de você turbinar seu fluxo! 🚀",
        licenca="desconhecida", dias_desde_o_primeiro_commit=60,
        commits_depois_do_primeiro_dia=5, exige_cadastro=True, hoje=HOJE,
    )
    achados = kinds(entrada)
    assert "descricao-emoji" in achados
    assert "descricao-exclamacao" in achados
    assert "descricao-segunda-pessoa" in achados
    assert "descricao-pitch" in achados
    assert "licenca-ausente" in achados
    assert "acesso-bloqueado" in achados


def test_entry_detects_duplicate_link() -> None:
    entrada = validar_entrada(
        nome="Outro nome", link="https://github.com/Exemplo/Fluxo",
        autor="Ana Lima", link_autor="https://github.com/analima",
        categoria="Skills e comandos", descricao="Revisa o diff antes do merge.",
        licenca="MIT", dias_desde_o_primeiro_commit=40,
        commits_depois_do_primeiro_dia=2, hoje=HOJE,
        existentes="https://github.com/exemplo/fluxo|Fluxo de skills",
    )
    assert "duplicata-link" in kinds(entrada)


def test_entry_requires_all_six_fields() -> None:
    entrada = validar_entrada(
        nome="", link="", autor="", link_autor="", categoria="",
        descricao="", dias_desde_o_primeiro_commit=40,
        commits_depois_do_primeiro_dia=1, hoje=HOJE,
    )
    campos = [achado for achado in entrada["findings"] if achado["kind"] == "campo-obrigatorio"]
    assert len(campos) == 5  # nome, link, autor, link do autor, descrição
    assert "categoria-obrigatoria" in kinds(entrada)  # a categoria é o sexto campo


def test_entry_rejects_out_of_range_numbers() -> None:
    with pytest.raises(CuradoriaError):
        validar_entrada(
            nome="Projeto X", link="https://exemplo.com/x", autor="Ana",
            link_autor="https://exemplo.com/a", categoria="Comece aqui",
            descricao="Faz uma coisa clara.", dias_desde_o_primeiro_commit=99_999,
        )
    with pytest.raises(CuradoriaError):
        validar_entrada(
            nome="Projeto X", link="https://exemplo.com/x", autor="Ana",
            link_autor="https://exemplo.com/a", categoria="Comece aqui",
            descricao="Faz uma coisa clara.", hoje="23/10/2026",
        )


def test_entry_in_lite_mode_keeps_only_blockers() -> None:
    entrada = validar_entrada(
        nome="Projeto novo", link="https://github.com/exemplo/novo",
        autor="Ana Lima", link_autor="https://github.com/analima",
        categoria="Comece aqui", descricao="Faz uma coisa pequena e clara.",
        dias_desde_o_primeiro_commit=4, commits_depois_do_primeiro_dia=1,
        hoje=HOJE, modo="lite",
    )
    assert entrada["counts"]["should"] == 0 and entrada["counts"]["nice"] == 0
    assert entrada["questions"] == []


def test_description_check_is_shared_with_hygiene() -> None:
    assert auditar_descricao("Guarda decisões entre sessões em arquivo local.") == []
    kinds_fortes = {item["kind"] for item in auditar_descricao("O melhor app do mundo para você!")}
    assert {"descricao-pitch", "descricao-segunda-pessoa", "descricao-exclamacao"} <= kinds_fortes


# ----------------------------------------------------------------- catálogo


def test_catalog_groups_in_configuration_order() -> None:
    catalogo = montar_catalogo(csv_texto=CSV, hoje=HOJE)
    nomes = [item["nome"] for item in catalogo["arvore"]]
    esperado = [item["nome"] for item in CATEGORIAS]
    assert nomes == esperado
    assert catalogo["metrics"]["linhas"] == 3
    assert catalogo["metrics"]["vazias"] == len(esperado) - 3
    assert catalogo["metrics"]["subcategorias"] == sum(len(item["subcategorias"]) for item in CATEGORIAS)
    assert catalogo["metrics"]["nunca_checados"] == 0
    revisao = next(item for item in catalogo["arvore"] if item["nome"] == "Skills e comandos")
    assert [linha["nome"] for linha in revisao["subcategorias"][0]["linhas"]] == ["Fluxo de skills"]


def test_catalog_reads_the_english_header_and_warns_on_extra_columns() -> None:
    traduzido = CSV.replace(
        "id,nome,categoria,subcategoria,link,autor,link_autor,ativo,adicionado_em,checado_em,descricao,estagnado",
        "ID,Display Name,Category,Sub-Category,Link,Author Name,Author Link,Active,Date Added,Last Checked,Description,Stale,Nota",
    )
    catalogo = montar_catalogo(csv_texto=traduzido, hoje=HOJE)
    assert catalogo["metrics"]["linhas"] == 3
    assert "coluna-ignorada" in kinds(catalogo)


def test_catalog_rejects_a_missing_column() -> None:
    with pytest.raises(CuradoriaError):
        montar_catalogo(csv_texto="id,nome,categoria\n1,X,Y\n", hoje=HOJE)
    with pytest.raises(CuradoriaError):
        montar_catalogo(csv_texto="", hoje=HOJE)
    with pytest.raises(CuradoriaError):
        montar_catalogo(csv_texto=CSV.splitlines()[0] + "\n", hoje=HOJE)


def test_catalog_flags_unknown_and_orphan_categories() -> None:
    extra = CSV + (
        "55667788,Fora do mapa,Cripto,,https://exemplo.com/fora,Ana,https://exemplo.com/ana,"
        "TRUE,2026-01-01,2026-09-01,Faz algo fora da configuração.,FALSE\n"
        "99aabbcc,Órfã,Observabilidade,Alertas,https://exemplo.com/orfa,Ana,https://exemplo.com/ana,"
        "TRUE,2026-01-01,2026-09-01,Fica numa subcategoria que não existe.,FALSE\n"
    )
    catalogo = montar_catalogo(csv_texto=extra, hoje=HOJE)
    achados = kinds(catalogo)
    assert "categoria-desconhecida" in achados
    assert "subcategoria-orfa" in achados
    assert catalogo["arvore"][-1]["desconhecida"] is True
    assert catalogo["metrics"]["desconhecidas"] == 1


def test_catalog_flags_stale_and_never_checked_rows() -> None:
    extra = CSV + (
        "aabbccdd,Velho,Coleções,,https://exemplo.com/velho,Ana,https://exemplo.com/ana,"
        "TRUE,2025-01-01,,Faz algo que ninguém checou ainda.,TRUE\n"
    )
    catalogo = montar_catalogo(csv_texto=extra, hoje=HOJE)
    achados = kinds(catalogo)
    assert "estagnados" in achados
    assert "nunca-checados" in achados
    assert catalogo["metrics"]["estagnados"] == 1


def test_catalog_accepts_custom_configuration() -> None:
    config = json.dumps({"categorias": [
        {"nome": "Ferramentas", "subcategorias": [{"nome": "CLI"}]},
        {"nome": "Arquivo", "submetivel": False},
    ]})
    catalogo = montar_catalogo(
        csv_texto="id,nome,categoria,subcategoria,link,autor,link_autor,ativo,"
                  "adicionado_em,checado_em,descricao,estagnado\n"
                  "11223344,ripgrep,Ferramentas,CLI,https://exemplo.com/rg,Ana,"
                  "https://exemplo.com/ana,TRUE,2026-01-01,2026-09-01,Busca rápido.,FALSE\n",
        categorias=config, hoje=HOJE,
    )
    assert [item["nome"] for item in catalogo["arvore"]] == ["Ferramentas", "Arquivo"]
    assert catalogo["arvore"][1]["total"] == 0
    assert "categoria-vazia" in kinds(catalogo)

    with pytest.raises(CuradoriaError):
        montar_catalogo(csv_texto=CSV, categorias="{não é json", hoje=HOJE)
    with pytest.raises(CuradoriaError):
        montar_catalogo(csv_texto=CSV, categorias=json.dumps({"categorias": []}), hoje=HOJE)


# ------------------------------------------------------------------- README


def test_readme_has_summary_anchors_and_one_line_per_resource() -> None:
    readme = gerar_readme(csv_texto=CSV, hoje=HOJE)
    markdown = readme["markdown"]
    assert markdown.startswith("# Recursos escolhidos")
    assert "[Skills e comandos](#skills-e-comandos)" in markdown
    assert "[Skills e comandos › Revisão de código](#skills-e-comandos-revisao-de-codigo)" in markdown
    assert "**3 recursos** em 9 categorias · 3 ativos · atualizado em 2026-10-23**" not in markdown
    assert "- [Fluxo de skills](https://github.com/exemplo/fluxo) — Revisa o diff antes do merge e registra a decisão." in markdown
    assert markdown.count("[Fluxo de skills]") == 1
    assert readme["metrics"]["secoes"] == 5
    assert "# Memória e contexto" in markdown


def test_readme_uses_the_title_and_intro() -> None:
    readme = gerar_readme(csv_texto=CSV, titulo="Lista do time", intro="Só entra o que já roda.", hoje=HOJE)
    assert readme["markdown"].startswith("# Lista do time")
    assert "Só entra o que já roda." in readme["markdown"]
    with pytest.raises(CuradoriaError):
        gerar_readme(csv_texto=CSV, titulo="T" * 91, hoje=HOJE)


def test_readme_suffixes_repeated_anchors() -> None:
    extra = CSV + (
        "ddeeff00,Outra,Skills e comandos,Testes,https://exemplo.com/outra,Ana,https://exemplo.com/ana,"
        "TRUE,2026-01-01,2026-09-01,Cobre o caminho de erro.,FALSE\n"
    )
    readme = gerar_readme(csv_texto=extra, hoje=HOJE)
    assert "(#skills-e-comandos-testes)" in readme["markdown"]


def test_readme_escapes_brackets_and_pipes() -> None:
    extra = CSV.replace("Fluxo de skills", "Fluxo [beta] | novo")
    readme = gerar_readme(csv_texto=extra, hoje=HOJE)
    assert "Fluxo \\[beta\\] \\| novo" in readme["markdown"]


def test_readme_skips_empty_sections() -> None:
    readme = gerar_readme(csv_texto=CSV, hoje=HOJE)
    assert "# Qualidade e revisão" not in readme["markdown"]


# ------------------------------------------------------------------- ticker


def test_ticker_ranks_movement_and_reports_new_and_gone() -> None:
    resultado = comparar_ticker(
        anterior="repo,stars\nexemplo/um,10\nexemplo/dois,50\nexemplo/tres,7\n",
        atual="repo,stars\nexemplo/um,14\nexemplo/dois,49\nexemplo/quatro,3\n",
    )
    assert resultado["metrics"]["comum"] == 2
    assert resultado["metrics"]["novos"] == 1
    assert resultado["metrics"]["sairam"] == 1
    assert [linha["repo"] for linha in resultado["rows"][:2]] == ["exemplo/um", "exemplo/quatro"]
    um = next(linha for linha in resultado["rows"] if linha["repo"] == "exemplo/um")
    assert um["delta"] == 4 and um["percentual"] == 40.0


def test_ticker_excludes_product_imitations_and_source_copies() -> None:
    resultado = comparar_ticker(
        anterior="repo,stars\nalguem/claude-code,900\nalguem/meu-source-code,800\nbons/um,10\n",
        atual="repo,stars\nalguem/claude-code,950\nalguem/meu-source-code,850\nbons/um,12\n",
    )
    assert resultado["metrics"]["excluidos"] == 2
    assert [linha["repo"] for linha in resultado["rows"]] == ["bons/um"]
    assert "protecao-ativa" in kinds(resultado)
    assert {item["repo"] for item in resultado["excluidos"]} == {"alguem/claude-code", "alguem/meu-source-code"}


def test_ticker_accepts_custom_protections() -> None:
    protecoes = json.dumps({"nomes_completos": ["exemplo/um"]})
    resultado = comparar_ticker(
        anterior="exemplo/um,10\n", atual="exemplo/um,12\n", protecoes=protecoes,
    )
    assert resultado["metrics"]["excluidos"] == 1
    with pytest.raises(CuradoriaError):
        comparar_ticker(anterior="exemplo/um,10", atual="exemplo/um,12", protecoes="[]")


def test_ticker_rejects_bad_snapshots() -> None:
    with pytest.raises(CuradoriaError):
        comparar_ticker(anterior="", atual="exemplo/um,10")
    with pytest.raises(CuradoriaError):
        comparar_ticker(anterior="exemplo/um,dez", atual="exemplo/um,10")
    with pytest.raises(CuradoriaError):
        comparar_ticker(anterior="sem-barra,10", atual="exemplo/um,10")


def test_ticker_flags_identical_or_disjoint_snapshots() -> None:
    igual = comparar_ticker(anterior="exemplo/um,10\n", atual="exemplo/um,10\n")
    assert igual["metrics"]["subiram"] == 0
    assert "sem-crescimento" in kinds(igual)

    disjunto = comparar_ticker(anterior="exemplo/um,10\n", atual="exemplo/dois,10\n")
    assert "snapshots-distintos" in kinds(disjunto)


# ------------------------------------------------------------------ higiene


def test_hygiene_passes_on_a_clean_catalog() -> None:
    higiene = auditar_higiene(csv_texto=CSV, hoje=HOJE, dias_para_checar=90)
    assert higiene["counts"]["must"] == 0
    assert higiene["metrics"]["linhas"] == 3


def test_hygiene_finds_duplicates_bad_ids_and_dates() -> None:
    sujo = CSV + (
        "4f1a2b3c,Sem link,Comece aqui,,ftp://exemplo.com/x,Ana,https://exemplo.com/ana,"
        "TRUE,01/01/2026,,Repete o ID de outra linha com link inválido.,FALSE\n"
    )
    higiene = auditar_higiene(csv_texto=sujo, hoje=HOJE)
    achados = kinds(higiene)
    assert "id-duplicado" in achados
    assert "link-invalido" in achados
    assert "data-invalida" in achados
    assert "sem-checagem" in achados


def test_hygiene_flags_repeated_links_and_names() -> None:
    sujo = CSV + (
        "55667788,Fluxo de skills,Skills e comandos,Testes,https://github.com/exemplo/fluxo,"
        "Ana,https://exemplo.com/ana,TRUE,2026-01-01,2026-09-01,Outra linha com o mesmo link.,FALSE\n"
    )
    higiene = auditar_higiene(csv_texto=sujo, hoje=HOJE)
    achados = kinds(higiene)
    assert "link-duplicado" in achados
    assert "nome-duplicado" in achados


def test_hygiene_flags_old_checks_and_stale_without_a_date() -> None:
    extra = CSV + (
        "ddeeff00,Algo,Comece aqui,,https://exemplo.com/algo,Ana,https://exemplo.com/ana,"
        "TRUE,2025-01-01,2025-02-01,Faz algo que ninguém revisita.,FALSE\n"
        "ddeeff11,Outro,Comece aqui,,https://exemplo.com/outro,Ana,https://exemplo.com/ana,"
        "TRUE,2025-01-01,,Marcado como estagnado sem checagem.,TRUE\n"
    )
    higiene = auditar_higiene(csv_texto=extra, hoje=HOJE, dias_para_checar=90)
    achados = kinds(higiene)
    assert "checagem-antiga" in achados
    assert "estagnado-sem-checagem" in achados


def test_hygiene_rejects_an_out_of_range_interval() -> None:
    with pytest.raises(CuradoriaError):
        auditar_higiene(csv_texto=CSV, hoje=HOJE, dias_para_checar=0)


# --------------------------------------------------------------------- API


def test_health_reports_the_new_version_and_skill_count(client: TestClient) -> None:
    health = client.get("/api/health").json()
    assert health["version"] == "0.37.2"
    assert health["skills"] == 209


def test_api_runs_every_curadoria_skill(client: TestClient) -> None:
    entrada = client.post("/api/skills/curadoria.entrada/execute", json={"parameters": {
        "nome": "Fluxo de skills", "link": "https://github.com/exemplo/fluxo",
        "autor": "Ana Lima", "link_autor": "https://github.com/analima",
        "categoria": "Skills e comandos", "subcategoria": "Revisão de código",
        "descricao": "Revisa o diff antes do merge e registra a decisão.",
        "licenca": "MIT", "dias_desde_o_primeiro_commit": 40,
        "commits_depois_do_primeiro_dia": 12, "hoje": HOJE, "semente": "api",
    }}).json()
    assert entrada["ok"] is True
    assert entrada["result"]["elegivel"] is True

    catalogo = client.post("/api/skills/curadoria.catalogo/execute", json={"parameters": {
        "csv": CSV, "hoje": HOJE,
    }}).json()
    assert catalogo["ok"] is True
    assert catalogo["result"]["metrics"]["linhas"] == 3

    readme = client.post("/api/skills/curadoria.readme/execute", json={"parameters": {
        "csv": CSV, "hoje": HOJE,
    }}).json()
    assert readme["ok"] is True
    assert readme["result"]["markdown"].startswith("# Recursos escolhidos")

    ticker = client.post("/api/skills/curadoria.ticker/execute", json={"parameters": {
        "anterior": "exemplo/um,10\n", "atual": "exemplo/um,12\n",
    }}).json()
    assert ticker["ok"] is True
    assert ticker["result"]["metrics"]["subiram"] == 1

    higiene = client.post("/api/skills/curadoria.higiene/execute", json={"parameters": {
        "csv": CSV, "hoje": HOJE,
    }}).json()
    assert higiene["ok"] is True
    assert higiene["result"]["counts"]["must"] == 0

    regras = client.post("/api/skills/curadoria.regras/execute", json={"parameters": {}}).json()
    assert regras["ok"] is True
    assert len(regras["result"]["colunas"]) == 12
    assert regras["result"]["licenca"]["id"] == "CC BY-NC-ND 4.0"


def test_api_is_read_only_and_rejects_bad_parameters(client: TestClient) -> None:
    readme = client.post("/api/skills/curadoria.readme/execute", json={"parameters": {"csv": CSV}}).json()
    assert readme["result"]["executed"] is False
    assert readme["result"]["readOnly"] is True
    assert readme["result"]["executado"] is False

    ruim = client.post("/api/skills/curadoria.catalogo/execute", json={"parameters": {
        "csv": "id,nome\n1,X\n",
    }}).json()
    assert ruim["ok"] is False
    assert ruim["error"]["code"] == "SKILL_ERROR"

    extra = client.post("/api/skills/curadoria.entrada/execute", json={"parameters": {
        "nome": "X", "link": "https://exemplo.com/x", "autor": "A",
        "link_autor": "https://exemplo.com/a", "categoria": "Comece aqui",
        "descricao": "Faz algo claro.", "escrever": True,
    }}).json()
    assert extra["ok"] is False


def test_catalog_registry_lists_six_rules() -> None:
    catalogo = curadoria_catalogo()
    assert len(catalogo["colunas"]) == 12
    assert {item["id"] for item in catalogo["elegibilidade"]} == {
        "idade", "desenvolvimento", "estrelas", "um-por-vez",
    }
    assert len(catalogo["higiene"]) == 10
    assert catalogo["executado"] is False
