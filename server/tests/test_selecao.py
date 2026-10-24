"""Testes da camada de seleção de skills."""
from __future__ import annotations

import json

import pytest

from server import selecao
from server.selecao import (
    MAX_ENTRADAS,
    MAX_RESULTADOS,
    MAX_SKILLS,
    SelecaoError,
    auditar_catalogo,
    ler_brief,
    montar_plano,
    recomendar,
    selecao_catalogo,
    validar_stack,
)

CATALOGO = [
    {
        "id": "stripe-billing",
        "path": "skills/stripe-billing",
        "category": "api-integration",
        "name": "stripe-billing",
        "description": "Cobra assinatura com Stripe, webhook de pagamento e checkout seguro do pedido.",
        "risk": "critical",
        "source": "community",
        "date_added": "2026-01-02",
        "plugin": {"targets": {"claude": "supported", "codex": "supported"}, "setup": {"type": "none", "summary": "", "docs": None}, "reasons": []},
    },
    {
        "id": "stripe-cobranca",
        "path": "skills/stripe-cobranca",
        "category": "api-integration",
        "name": "stripe-cobranca",
        "description": "Cobra assinatura com Stripe e webhook de pagamento do checkout.",
        "risk": "critical",
        "source": "community",
        "date_added": "2026-01-03",
        "plugin": {"targets": {"claude": "supported", "codex": "supported"}, "setup": {"type": "none", "summary": "", "docs": None}, "reasons": []},
    },
    {
        "id": "nextjs-app",
        "path": "skills/nextjs-app",
        "category": "web-development",
        "name": "nextjs-app",
        "description": "Estrutura app router em Next.js com React, paginação e teste de componente.",
        "risk": "safe",
        "source": "community",
        "date_added": "2026-01-04",
        "plugin": {"targets": {"claude": "supported", "codex": "supported"}, "setup": {"type": "none", "summary": "", "docs": None}, "reasons": []},
    },
    {
        "id": "supabase-schema",
        "path": "skills/supabase-schema",
        "category": "data",
        "name": "supabase-schema",
        "description": "Cria schema, migração e política de acesso no banco Supabase.",
        "risk": "safe",
        "source": "personal",
        "date_added": "2026-01-05",
        "plugin": {"targets": {"claude": "supported"}, "setup": {"type": "manual", "summary": "rodar supabase link", "docs": None}, "reasons": []},
    },
    {
        "id": "lgpd-audit",
        "path": "skills/lgpd-audit",
        "category": "security",
        "name": "lgpd-audit",
        "description": "Revisa tratamento de dado pessoal, base legal e retenção sob LGPD.",
        "risk": "offensive",
        "source": "community",
        "date_added": "2026-01-06",
        "plugin": {"targets": {"claude": "supported", "codex": "supported"}, "setup": {"type": "none", "summary": "", "docs": None}, "reasons": []},
    },
    {
        "id": "vercel-deploy",
        "path": "skills/vercel-deploy",
        "category": "devops",
        "name": "vercel-deploy",
        "description": "Publica deploy na Vercel com rollback e variável de ambiente.",
        "risk": "safe",
        "source": "community",
        "date_added": "2026-01-07",
        "plugin": {"targets": {"claude": "supported", "codex": "supported"}, "setup": {"type": "none", "summary": "", "docs": None}, "reasons": []},
    },
    {
        "id": "pixel-design",
        "path": "skills/pixel-design",
        "category": "design",
        "name": "pixel-design",
        "description": "Desenha tela responsiva com foco em acessibilidade e contraste.",
        "risk": "safe",
        "source": "community",
        "date_added": "2026-01-08",
        "plugin": {"targets": {"codex": "supported"}, "setup": {"type": "none", "summary": "", "docs": None}, "reasons": []},
    },
]

BRIEF = (
    "Preciso de uma API de cobrança com Stripe para um SaaS em Next.js, com teste de integração, "
    "deploy na Vercel e conformidade com LGPD. O sucesso é fechar o checkout em menos de 3 segundos. "
    "A equipe tem dois devs e o prazo é de seis semanas."
)

TEXTO = json.dumps(CATALOGO, ensure_ascii=False)


# --- briefing ---------------------------------------------------------------


def test_brief_reconhece_dimensoes_entregaveis_e_restricoes():
    resultado = ler_brief(brief=BRIEF)
    metrics = resultado["metrics"]
    assert metrics["dimensoes"] >= 4
    assert metrics["entregaveis"] >= 1
    assert metrics["restricoes"] >= 2
    assert metrics["tem_criterio"] == 1
    assert metrics["tem_publico"] == 1
    assert resultado["counts"]["must"] == 0


def test_brief_curto_bloqueia():
    resultado = ler_brief(brief="Entregue uma api de cobrança com teste e capricho.")
    assert "brief-curto" in [item["kind"] for item in resultado["findings"]]


def test_brief_sem_objetivo_bloqueia():
    resultado = ler_brief(brief="Preciso daquilo que conversamos ontem, com urgência e capricho.")
    assert "brief-sem-objetivo" in [item["kind"] for item in resultado["findings"]]


def test_brief_recusa_texto_menor_que_quarenta():
    with pytest.raises(SelecaoError, match="40 caracteres"):
        ler_brief(brief="curto demais")


def test_brief_recusa_modo_invalido():
    with pytest.raises(SelecaoError, match="Modo inválido"):
        ler_brief(brief=BRIEF, modo="turbo")


def test_brief_lite_so_devolve_bloqueios():
    resultado = ler_brief(brief="Preciso daquilo que conversamos ontem, com urgência e capricho.", modo="lite")
    assert all(item["group"] == "must" for item in resultado["findings"])
    assert resultado["counts"]["should"] == 0


def test_brief_rows_trazem_a_palavra_que_casou():
    resultado = ler_brief(brief=BRIEF)
    dimensoes = {row["chave"] for row in resultado["rows"]}
    assert "integracoes" in dimensoes
    linha = next(row for row in resultado["rows"] if row["chave"] == "integracoes")
    assert "stripe" in linha["evidencia"] or "api" in linha["evidencia"]


# --- busca ------------------------------------------------------------------


def test_busca_coloca_a_skill_de_cobranca_no_topo():
    resultado = recomendar(brief=BRIEF, catalogo=TEXTO)
    assert resultado["rows"][0]["skill"] in {"stripe-billing", "stripe-cobranca"}
    assert resultado["metrics"]["resultados"] == len(resultado["rows"]) >= 5


def test_busca_filtra_por_categoria():
    resultado = recomendar(brief=BRIEF, catalogo=TEXTO, categoria="security")
    assert [row["skill"] for row in resultado["rows"]] == ["lgpd-audit"]


def test_busca_filtra_por_risco():
    resultado = recomendar(brief=BRIEF, catalogo=TEXTO, risco="critical")
    assert {row["skill"] for row in resultado["rows"]} == {"stripe-billing", "stripe-cobranca"}


def test_busca_filtra_por_alvo():
    resultado = recomendar(brief=BRIEF, catalogo=TEXTO, alvo="codex")
    assert "supabase-schema" not in {row["skill"] for row in resultado["rows"]}


def test_busca_sem_resultado_por_filtro_bloqueia():
    resultado = recomendar(brief=BRIEF, catalogo=TEXTO, categoria="inexistente")
    kinds = [item["kind"] for item in resultado["findings"]]
    assert "filtro-sem-resultado" in kinds
    assert resultado["counts"]["must"] >= 1


def test_busca_sem_termo_em_comum_bloqueia():
    resultado = recomendar(brief="xilofone xilofone xilofone", catalogo=TEXTO)
    kinds = [item["kind"] for item in resultado["findings"]]
    assert "nenhum-resultado" in kinds
    assert resultado["rows"] == []


def test_busca_recusa_catalogo_vazio():
    with pytest.raises(SelecaoError, match="nenhuma entrada"):
        recomendar(brief=BRIEF, catalogo="[]")


def test_busca_recusa_json_invalido():
    with pytest.raises(SelecaoError, match="JSON inválido"):
        recomendar(brief=BRIEF, catalogo='[{"id": "x",}]')


def test_busca_recusa_limite_fora_da_faixa():
    with pytest.raises(SelecaoError, match="limite"):
        recomendar(brief=BRIEF, catalogo=TEXTO, limite=MAX_RESULTADOS + 1)


def test_busca_aceita_linhas_compactas():
    linhas = "cobranca | pagamentos | strpe checkout e webhook de assinatura\nschema | dados | migracao do banco"
    resultado = recomendar(brief=BRIEF, catalogo=linhas)
    assert resultado["rows"][0]["skill"] == "cobranca"


def test_busca_aceita_linha_com_risco():
    linhas = "cobranca | pagamentos | critical | stripe checkout e webhook\nschema | dados | safe | migracao do banco"
    resultado = recomendar(brief=BRIEF, catalogo=linhas, risco="critical")
    assert [row["skill"] for row in resultado["rows"]] == ["cobranca"]
    assert resultado["rows"][0]["risco"] == "critical"


def test_busca_avisa_empate_tecnico():
    iguais = [
        {"id": "a", "category": "x", "name": "a", "description": "cobra assinatura stripe", "risk": "safe", "plugin": {"targets": {}}},
        {"id": "b", "category": "x", "name": "b", "description": "cobra assinatura stripe", "risk": "safe", "plugin": {"targets": {}}},
    ]
    resultado = recomendar(brief="preciso cobrar assinatura no stripe", catalogo=json.dumps(iguais))
    assert "empate-no-topo" in [item["kind"] for item in resultado["findings"]]


def test_busca_conta_dimensoes_cobertas():
    resultado = recomendar(brief=BRIEF, catalogo=TEXTO, limite=50)
    assert resultado["metrics"]["cobertas"] <= resultado["metrics"]["dimensoes"]
    assert resultado["metrics"]["cobertas"] >= 3


# --- stack ------------------------------------------------------------------


def test_stack_valida_sem_bloqueio():
    manifesto = json.dumps({"skills": ["stripe-billing", "nextjs-app", "supabase-schema", "lgpd-audit", "vercel-deploy"]})
    resultado = validar_stack(brief=BRIEF, skills=manifesto, catalogo=TEXTO)
    kinds = [item["kind"] for item in resultado["findings"]]
    assert "skill-inexistente" not in kinds
    assert "lacuna-de-dimensao" not in kinds
    assert resultado["metrics"]["validas"] == 5


def test_stack_aponta_id_inexistente():
    resultado = validar_stack(brief=BRIEF, skills='["stripe-billing", "fantasma"]', catalogo=TEXTO)
    achado = next(item for item in resultado["findings"] if item["kind"] == "skill-inexistente")
    assert "fantasma" in achado["location"]
    assert resultado["metrics"]["validas"] == 1


def test_stack_aponta_id_repetido():
    resultado = validar_stack(brief=BRIEF, skills='["stripe-billing", "stripe-billing"]', catalogo=TEXTO)
    assert "id-repetido" in [item["kind"] for item in resultado["findings"]]


def test_stack_declara_lacuna_de_dimensao():
    resultado = validar_stack(brief=BRIEF, skills='["nextjs-app"]', catalogo=TEXTO)
    achado = next(item for item in resultado["findings"] if item["kind"] == "lacuna-de-dimensao")
    assert "Testes e qualidade" in achado["location"] or "Integrações" in achado["location"]
    assert "## Lacunas declaradas" in resultado["markdown"]


def test_stack_aponta_sobreposicao():
    resultado = validar_stack(brief=BRIEF, skills='["stripe-billing", "stripe-cobranca"]', catalogo=TEXTO)
    assert resultado["metrics"]["sobrepostas"] == 1
    assert "sobreposicao" in [item["kind"] for item in resultado["findings"]]


def test_stack_soma_risco_e_estoura_o_limite():
    resultado = validar_stack(brief=BRIEF, skills='["stripe-billing", "stripe-cobranca", "lgpd-audit"]', catalogo=TEXTO)
    assert resultado["metrics"]["pontos_risco"] == 8
    assert "risco-alto" in [item["kind"] for item in resultado["findings"]]
    alto = validar_stack(brief=BRIEF, skills='["stripe-billing"]', catalogo=TEXTO, limite_risco=10)
    assert "risco-alto" not in [item["kind"] for item in alto["findings"]]


def test_stack_aponta_alvo_incompativel():
    resultado = validar_stack(brief=BRIEF, skills='["supabase-schema", "pixel-design"]', catalogo=TEXTO, alvo="codex")
    assert "alvo-incompativel" in [item["kind"] for item in resultado["findings"]]


def test_stack_aponta_setup_manual():
    resultado = validar_stack(brief=BRIEF, skills='["supabase-schema"]', catalogo=TEXTO)
    assert "setup-manual" in [item["kind"] for item in resultado["findings"]]


def test_stack_sem_evidencia_e_opcional():
    resultado = validar_stack(brief=BRIEF, skills='["nextjs-app"]', catalogo=TEXTO)
    achado = next(item for item in resultado["findings"] if item["kind"] == "sem-evidencia")
    assert achado["group"] == "nice"


def test_stack_sem_brief_bloqueia():
    resultado = validar_stack(brief="", skills='["nextjs-app"]', catalogo=TEXTO)
    assert "sem-brief" in [item["kind"] for item in resultado["findings"]]


def test_stack_sem_id_valido_bloqueia():
    resultado = validar_stack(brief=BRIEF, skills='["a", "b"]', catalogo=TEXTO)
    kinds = [item["kind"] for item in resultado["findings"]]
    assert "stack-vazia" in kinds
    assert "skill-inexistente" in kinds


def test_stack_acima_do_teto_bloqueia():
    resultado = validar_stack(brief=BRIEF, skills='["a", "b", "c"]', catalogo=TEXTO, max_skills=2)
    assert "stack-acima-do-limite" in [item["kind"] for item in resultado["findings"]]


def test_stack_recusa_catalogo_sem_entrada():
    with pytest.raises(SelecaoError, match="nenhuma entrada"):
        validar_stack(brief=BRIEF, skills='["a"]', catalogo="[]")


def test_stack_aceita_manifesto_com_lista_de_objetos():
    manifesto = json.dumps({"skills": [{"id": "nextjs-app", "rationale": "base"}]})
    resultado = validar_stack(brief=BRIEF, skills=manifesto, catalogo=TEXTO)
    assert resultado["metrics"]["validas"] == 1
    assert "sem-evidencia" not in [item["kind"] for item in resultado["findings"]]


# --- plano ------------------------------------------------------------------


def test_plano_ordena_as_fases_pela_dimensao():
    manifesto = json.dumps({"skills": ["vercel-deploy", "stripe-billing", "nextjs-app", "supabase-schema"]})
    resultado = montar_plano(brief=BRIEF, skills=manifesto, catalogo=TEXTO)
    dimensoes = [row["dimensao"] for row in resultado["rows"]]
    assert dimensoes[0] == "Linguagens e frameworks"
    assert dimensoes[-1] == "Deploy e operação"
    assert resultado["metrics"]["fases"] == 4


def test_plano_depende_da_fase_anterior():
    manifesto = json.dumps({"skills": ["vercel-deploy", "nextjs-app"]})
    resultado = montar_plano(brief=BRIEF, skills=manifesto, catalogo=TEXTO)
    fases = {row["fase"]: row for row in resultado["rows"]}
    assert fases[1]["depende"] == "—"
    assert fases[2]["depende"] == "1"


def test_plano_exige_portao_para_skill_critica():
    manifesto = json.dumps({"skills": ["stripe-billing", "nextjs-app"]})
    resultado = montar_plano(brief=BRIEF, skills=manifesto, catalogo=TEXTO)
    assert "risco-sem-portao" in [item["kind"] for item in resultado["findings"]]
    com_portao = montar_plano(brief=BRIEF + " Com revisão e aprovação antes do deploy.", skills=manifesto, catalogo=TEXTO)
    assert "risco-sem-portao" not in [item["kind"] for item in com_portao["findings"]]


def test_plano_aponta_dimensao_descoberta():
    resultado = montar_plano(brief=BRIEF, skills='["nextjs-app"]', catalogo=TEXTO)
    assert "plano-descoberto" in [item["kind"] for item in resultado["findings"]]


def test_plano_ignora_id_inexistente_e_avisa():
    resultado = montar_plano(brief=BRIEF, skills='["nextjs-app", "fantasma"]', catalogo=TEXTO)
    assert "skill-inexistente" in [item["kind"] for item in resultado["findings"]]
    assert all(row["skill"] != "fantasma" for row in resultado["rows"])


def test_plano_sem_catalogo_usa_os_ids():
    resultado = montar_plano(brief=BRIEF, skills="nextjs-app\nvercel-deploy")
    assert len(resultado["rows"]) == 2
    assert resultado["counts"]["must"] == 0


def test_plano_curto_avisa_quando_ha_uma_fase():
    resultado = montar_plano(brief=BRIEF, skills='["nextjs-app"]', catalogo=TEXTO)
    assert "plano-curto" in [item["kind"] for item in resultado["findings"]]


def test_plano_recusa_brief_curto():
    with pytest.raises(SelecaoError, match="20 caracteres"):
        montar_plano(brief="curto", skills='["nextjs-app"]', catalogo=TEXTO)


# --- catálogo ---------------------------------------------------------------


def _entrada(identificador: str, **campos):
    base = {
        "id": identificador,
        "path": f"skills/{identificador}",
        "category": "development",
        "name": identificador,
        "description": "Faz uma coisa útil e específica.",
        "risk": "safe",
        "source": "community",
        "plugin": {"targets": {"claude": "supported", "codex": "supported"}, "setup": {"type": "none"}, "reasons": []},
    }
    base.update(campos)
    return base


def test_catalogo_limpo_nao_bloqueia():
    resultado = auditar_catalogo(catalogo=json.dumps([_entrada("a"), _entrada("b")]))
    assert resultado["counts"]["must"] == 0
    assert resultado["metrics"]["entradas"] == 2


def test_catalogo_aponta_campos_quebrados():
    entradas = [
        _entrada("a", description=""),
        _entrada("a"),
        _entrada("b", name="outro-nome"),
        _entrada("c", path="outro/c"),
        _entrada("d", risk="unknown"),
        _entrada("e", description=" ".join(["palavra"] * 45)),
        _entrada("f", plugin={"targets": {}, "setup": {"type": "manual"}}),
    ]
    resultado = auditar_catalogo(catalogo=json.dumps(entradas))
    kinds = {item["kind"] for item in resultado["findings"]}
    assert {"sem-descricao", "id-duplicado", "id-diferente-do-nome", "path-fora-do-padrao"} <= kinds
    assert {"risco-indefinido", "descricao-longa", "alvo-ausente", "setup-manual"} <= kinds
    assert resultado["metrics"]["duplicados"] == 1
    assert resultado["metrics"]["sem_descricao"] == 1


def test_catalogo_aponta_risco_critico_dominante():
    entradas = [_entrada("a", risk="critical"), _entrada("b", risk="critical"), _entrada("c")]
    resultado = auditar_catalogo(catalogo=json.dumps(entradas))
    assert "risco-critico-alto" in [item["kind"] for item in resultado["findings"]]
    assert resultado["metrics"]["criticos"] == 2


def test_catalogo_conta_categorias_e_fontes():
    entradas = [_entrada("a", category="data"), _entrada("b", category="data"), _entrada("c", category="security")]
    resultado = auditar_catalogo(catalogo=json.dumps(entradas))
    assert resultado["metrics"]["categorias"] == 2
    assert "categoria-unica" in [item["kind"] for item in resultado["findings"]]


def test_catalogo_trunca_acima_do_teto(monkeypatch):
    monkeypatch.setattr(selecao, "MAX_ENTRADAS", 2)
    resultado = auditar_catalogo(catalogo=json.dumps([_entrada("a"), _entrada("b"), _entrada("c")]))
    assert resultado["metrics"]["entradas"] == 2
    assert any("truncado" in item for item in resultado["limitations"])


# --- catálogo de regras -----------------------------------------------------


def test_regras_publicam_as_dez_dimensoes():
    catalogo = selecao_catalogo()
    assert len(catalogo["dimensoes"]) == 10
    assert catalogo["busca"]["k1"] == 1.2
    assert catalogo["busca"]["b"] == 0.75
    assert catalogo["stack"]["max_skills"] == MAX_SKILLS
    assert catalogo["stack"]["sobreposicao"] == selecao.SOBREPOSICAO
    assert len(catalogo["catalogo"]["regras"]) == 9
    assert catalogo["limites"]["entradas"] == MAX_ENTRADAS
    assert catalogo["executado"] is False
    assert any("BM25" in item for item in catalogo["deixado_de_fora"])


# --- cobertura --------------------------------------------------------------


def test_cobertura_mapeia_as_dimensoes_do_briefing():
    from server.selecao import mapear_cobertura

    resultado = mapear_cobertura(brief=BRIEF, catalogo=TEXTO)
    chaves = {row["chave"] for row in resultado["rows"]}
    assert {"linguagens", "integracoes", "qualidade", "seguranca", "operacao"} <= chaves
    assert resultado["metrics"]["entradas"] == len(CATALOGO)
    assert resultado["metrics"]["lacunas"] == 0
    linha = next(row for row in resultado["rows"] if row["chave"] == "integracoes")
    assert linha["skills"] >= 2
    assert "stripe" in linha["candidatas"]


def test_cobertura_aponta_dimensao_sem_skill():
    from server.selecao import mapear_cobertura

    sem_dados = [entrada for entrada in CATALOGO if entrada["id"] != "supabase-schema"]
    brief = (
        "Preciso de um schema de banco com migração e política de acesso para guardar pedido e cliente, "
        "com critério de sucesso em latência e prazo de quatro semanas."
    )
    resultado = mapear_cobertura(brief=brief, catalogo=json.dumps(sem_dados, ensure_ascii=False))
    assert resultado["metrics"]["lacunas"] >= 1
    assert "dimensao-sem-skill" in [item["kind"] for item in resultado["findings"]]


def test_cobertura_recusa_briefing_sem_dimensao():
    from server.selecao import mapear_cobertura

    with pytest.raises(SelecaoError, match="dez dimensões"):
        mapear_cobertura(brief="Quero algo bonito que funcione bem e agrade todo mundo.", catalogo=TEXTO)


def test_cobertura_recusa_limite_fora_da_faixa():
    from server.selecao import mapear_cobertura

    with pytest.raises(SelecaoError, match="limite por dimensão"):
        mapear_cobertura(brief=BRIEF, catalogo=TEXTO, limite_por_dimensao=11)


def test_cobertura_conta_percentual_do_catalogo():
    from server.selecao import mapear_cobertura

    resultado = mapear_cobertura(brief=BRIEF, catalogo=TEXTO)
    for linha in resultado["rows"]:
        assert 0 <= linha["cobertura"] <= 100
