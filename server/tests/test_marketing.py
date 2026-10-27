"""Testes do marketing mensurável inspirado em coreyhaines31/marketingskills (MIT).

Nada do upstream é executado, clonado ou copiado: as fixtures são números de
funil, URLs de campanha, textos de e-mail e HTML de página, e as contas são
feitas em Python sobre eles. Nenhuma plataforma de anúncio é consultada.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from server.app import create_app
from server.marketing import (
    MEDIUMS,
    PLATAFORMAS,
    MarketingError,
    auditar_email,
    auditar_seo,
    auditar_utm,
    calcular_orcamento,
    dimensionar_teste,
    marketing_catalogo,
    revisar_anuncio,
)
from server.skill_registry import build_registry

# ------------------------------------------------------------------ fixtures

ORCAMENTO = dict(
    orcamento=30_000.0, cpm=28.0, ctr=1.8, cvr=6.0, fechamento=22.0,
    ticket=199.0, margem=78.0, modelo="assinatura", vida_util_meses=18.0,
)

URLS_LIMPA = (
    "https://exemplo.com/preco?utm_source=linkedin&utm_medium=creator&"
    "utm_campaign=lancamento-2026-10&utm_content=hero-cta"
)

EMAIL_LIMPO = dict(
    assunto="O relatório de outubro está pronto",
    preview="Cinco páginas com o que mudou no funil e o que fazer nesta semana.",
    corpo=(
        "O relatório de outubro está pronto.\n\n"
        "Ele traz a queda de conversão da página de preço e as três hipóteses que "
        "testamos para explicar o recuo.\n\n"
        "A leitura leva oito minutos.\n\n"
        "Abra o relatório no link."
    ),
    cta="Abrir o relatório",
    tipo="lifecycle",
)


def _pagina_limpa() -> str:
    corpo = " ".join(["conteúdo"] * 320)
    return f"""<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8">
<title>Como calcular o preço de um plano SaaS em 2026</title>
<meta name="description" content="Um método para calcular o preço de um plano SaaS a partir de valor percebido, custo e disposição a pagar, com uma planilha de exemplo para copiar.">
<link rel="canonical" href="https://exemplo.com/preco-saas">
<script type="application/ld+json">{{"@context":"https://schema.org","@type":"Article","headline":"Preço de SaaS"}}</script>
</head><body>
<h1>Como calcular o preço de um plano SaaS</h1>
<p>O preço de um plano SaaS sai de três números: valor percebido, custo de servir e disposição a pagar do segmento. Comece pelo valor e use o custo como piso, nunca como ponto de partida.</p>
<h2>Qual é o custo de servir cada cliente?</h2>
<p>{corpo}</p>
<img src="grafico.png" alt="Gráfico de disposição a pagar por segmento" width="800" height="450">
<a href="/blog/preco">Outro texto sobre preço</a>
<a href="https://exemplo.com/contato">Fale com o time</a>
<a href="https://developers.google.com/search">Fonte: documentação de busca</a>
</body></html>"""


@pytest.fixture(scope="module")
def client(tmp_path_factory: pytest.TempPathFactory) -> TestClient:
    return TestClient(create_app(registry=build_registry(tmp_path_factory.mktemp("marketing"))))


def kinds(resultado: dict) -> set[str]:
    return {achado["kind"] for achado in resultado["findings"]}


# ----------------------------------------------------------------- orçamento


def test_budget_funnel_multiplies_each_step() -> None:
    plano = calcular_orcamento(**ORCAMENTO)
    metrics = plano["metrics"]
    assert metrics["impressoes"] == pytest.approx(1_071_428.57, rel=1e-6)
    assert metrics["cliques"] == pytest.approx(19_285.71, rel=1e-5)
    assert metrics["leads"] == pytest.approx(1_157.14, rel=1e-4)
    assert metrics["clientes"] == pytest.approx(254.571, rel=1e-4)
    assert metrics["cac"] == pytest.approx(117.85, rel=1e-3)
    assert metrics["roas"] == pytest.approx(1.689, rel=1e-3)
    assert plano["executado"] is False
    assert plano["readOnly"] is True


def test_budget_payback_and_ltv_follow_the_margin() -> None:
    plano = calcular_orcamento(**ORCAMENTO)
    metrics = plano["metrics"]
    retorno = 199 * 0.78
    assert metrics["payback_meses"] == pytest.approx(round(metrics["cac"] / retorno, 2))
    assert metrics["ltv"] == pytest.approx(retorno * 18, rel=1e-6)
    assert metrics["ltv_cac"] == pytest.approx(metrics["ltv"] / metrics["cac"], abs=1e-2)
    assert metrics["margem_bruta"] == pytest.approx(metrics["receita"] * 0.78, rel=1e-6)


def test_budget_flags_a_channel_that_loses_money() -> None:
    plano = calcular_orcamento(**{**ORCAMENTO, "cpm": 200.0, "ctr": 0.4, "cvr": 2.0, "fechamento": 5.0})
    assert "roas-abaixo-de-1" in kinds(plano)
    assert "cac-acima-do-ltv" in kinds(plano)
    assert plano["counts"]["must"] >= 2


def test_budget_rejects_implausible_rates_and_accepts_them_as_findings() -> None:
    plano = calcular_orcamento(**{**ORCAMENTO, "ctr": 40.0, "cvr": 90.0})
    achados = kinds(plano)
    assert "ctr-alto" in achados
    assert "cvr-alto" in achados


def test_budget_target_cac_shows_the_lever() -> None:
    plano = calcular_orcamento(**{**ORCAMENTO, "cac_alvo": 60.0})
    assert plano["counts"]["must"] == 0
    assert len(plano["sensibilidade"]) == 3
    ctr = next(item for item in plano["sensibilidade"] if item["alavanca"] == "CTR")
    assert ctr["necessario"] != ctr["atual"]
    assert "cac-alvo-distante" in kinds(plano)


def test_budget_by_arr_goal() -> None:
    plano = calcular_orcamento(**{**ORCAMENTO, "meta_arr": 1_200_000.0, "arpc": 189.0, "retencao_anual": 88.0})
    meta = plano["meta"]
    esperado = ((1_200_000 / (189 * 12)) * plano["metrics"]["cac"]) / 0.88
    assert meta["orcamento_necessario"] == pytest.approx(round(esperado, 2), rel=1e-3)
    assert meta["gap"] == pytest.approx(round(meta["orcamento_necessario"] - 30_000, 2), rel=1e-3)
    assert "meta-sem-verba" in kinds(plano)


def test_budget_rejects_bad_input() -> None:
    for troca in ({"orcamento": 0}, {"cpm": 0}, {"ctr": 120}, {"margem": 0}, {"modelo": "freemium"},
                  {"moeda": "JPY"}, {"ticket": -1}):
        with pytest.raises(MarketingError):
            calcular_orcamento(**{**ORCAMENTO, **troca})
    with pytest.raises(MarketingError):
        calcular_orcamento(**{**ORCAMENTO, "meta_arr": 1000.0})


def test_budget_in_lite_mode_keeps_blockers_only() -> None:
    plano = calcular_orcamento(**{**ORCAMENTO, "ctr": 40.0, "modo": "lite"})
    assert plano["counts"]["should"] == 0
    assert plano["questions"] == []


# --------------------------------------------------------------------- teste


def test_sample_size_matches_the_standard_two_proportion_calculation() -> None:
    teste = dimensionar_teste(baseline=10.0, mde=20.0, trafego_diario=5_000.0)
    assert 3_750 <= teste["metrics"]["por_variante"] <= 3_950
    assert teste["metrics"]["total"] == teste["metrics"]["por_variante"] * 2
    assert teste["metrics"]["dias"] == 2
    assert teste["metrics"]["minimo"] == 7


def test_sample_size_grows_when_the_effect_shrinks() -> None:
    grande = dimensionar_teste(baseline=5.0, mde=50.0, trafego_diario=1_000.0)["metrics"]["por_variante"]
    medio = dimensionar_teste(baseline=5.0, mde=20.0, trafego_diario=1_000.0)["metrics"]["por_variante"]
    pequeno = dimensionar_teste(baseline=5.0, mde=5.0, trafego_diario=1_000.0)["metrics"]["por_variante"]
    assert grande < medio < pequeno


def test_test_rejects_a_design_that_does_not_fit() -> None:
    teste = dimensionar_teste(baseline=3.0, mde=20.0, trafego_diario=120.0, exposicao=50.0)
    assert teste["metrics"]["viavel"] is False
    assert "inviavel" in kinds(teste)
    assert teste["counts"]["must"] == 1


def test_test_requires_a_full_business_cycle() -> None:
    b2b = dimensionar_teste(baseline=3.0, mde=20.0, trafego_diario=4_000.0, exposicao=80.0, tipo="b2b")
    assert b2b["metrics"]["minimo"] == 14
    assert "curto-demais" in kinds(b2b)
    b2c = dimensionar_teste(baseline=3.0, mde=20.0, trafego_diario=4_000.0, exposicao=80.0, tipo="b2c")
    assert b2c["metrics"]["minimo"] == 7
    assert "curto-demais" not in kinds(b2c)


def test_test_adjusts_alpha_for_many_variants() -> None:
    teste = dimensionar_teste(baseline=5.0, mde=20.0, trafego_diario=20_000.0, variantes=4)
    assert teste["metrics"]["alfa_ajustado"] == pytest.approx(0.05 / 3, abs=1e-5)
    assert "muitas-variantes" in kinds(teste)
    duas = dimensionar_teste(baseline=5.0, mde=20.0, trafego_diario=20_000.0, variantes=2)
    assert teste["metrics"]["por_variante"] > duas["metrics"]["por_variante"]


def test_test_rejects_bad_input() -> None:
    for troca in ({"baseline": 0}, {"baseline": 100}, {"mde": 0}, {"trafego_diario": 0},
                  {"variantes": 1}, {"variantes": 7}, {"alfa": 0.6}, {"poder": 0.4},
                  {"exposicao": 0}, {"tipo": "b2g"}):
        with pytest.raises(MarketingError):
            dimensionar_teste(**{"baseline": 5.0, "mde": 10.0, "trafego_diario": 1000.0, **troca})


# ----------------------------------------------------------------------- utm


def test_clean_campaign_url_passes() -> None:
    resultado = auditar_utm(urls=URLS_LIMPA)
    assert resultado["counts"]["must"] == 0
    assert resultado["rows"][0]["status"] == "ok"
    assert resultado["metrics"]["ok"] == 1


def test_utm_normalizes_case_and_separator() -> None:
    resultado = auditar_utm(urls=(
        "https://exemplo.com/preco?utm_source=LinkedIn&utm_medium=Creator&"
        "utm_campaign=Lancamento_2026&utm_content=hero_CTA"
    ))
    assert "maiuscula" in kinds(resultado)
    assert "separador" in kinds(resultado)
    canonica = resultado["rows"][0]["canonica"]
    assert "utm_source=linkedin" in canonica and "utm_campaign=lancamento-2026" in canonica


def test_utm_flags_missing_required_parameters() -> None:
    resultado = auditar_utm(urls="https://exemplo.com/?utm_source=newsletter&utm_medium=newsletter")
    assert "utm-incompleta" in kinds(resultado)
    assert resultado["rows"][0]["status"] == "corrigir"


def test_utm_flags_personal_data() -> None:
    resultado = auditar_utm(urls=(
        "https://exemplo.com/?utm_source=email&utm_medium=email&utm_campaign=base&"
        "utm_content=ana.lima%40exemplo.com"
    ))
    assert "pii-email" in kinds(resultado)


def test_utm_does_not_mistake_a_date_for_a_phone() -> None:
    resultado = auditar_utm(urls=(
        "https://exemplo.com/?utm_source=parceiro&utm_medium=podcast&utm_campaign=2026-10-23"
    ))
    assert "pii-telefone" not in kinds(resultado)


def test_utm_flags_repeated_key_and_missing_scheme() -> None:
    repetida = auditar_utm(urls=(
        "https://exemplo.com/?utm_source=google&utm_source=meta&utm_medium=cpc&utm_campaign=x"
    ))
    assert "chave-repetida" in kinds(repetida)

    sem_esquema = auditar_utm(urls="exemplo.com/landing?utm_source=a&utm_medium=cpc&utm_campaign=b")
    assert "sem-esquema" in kinds(sem_esquema)
    assert sem_esquema["rows"][0]["status"] == "inválida"


def test_utm_flags_duplicates_and_unknown_medium() -> None:
    resultado = auditar_utm(urls=f"{URLS_LIMPA}\n{URLS_LIMPA}")
    assert "duplicada" in kinds(resultado)

    novo = auditar_utm(urls="https://exemplo.com/?utm_source=x&utm_medium=inventado&utm_campaign=y")
    assert "medium-novo" in kinds(novo)


def test_utm_rejects_an_empty_list() -> None:
    with pytest.raises(MarketingError):
        auditar_utm(urls="   \n  ")


def test_utm_catalog_lists_the_mediums() -> None:
    assert "newsletter" in MEDIUMS and "creator" in MEDIUMS


# --------------------------------------------------------------------- email


def test_clean_email_passes() -> None:
    resultado = auditar_email(**EMAIL_LIMPO)
    assert resultado["counts"]["must"] == 0
    assert resultado["metrics"]["assunto"] == len(EMAIL_LIMPO["assunto"])


def test_email_flags_long_subject_and_preview_that_repeats() -> None:
    resultado = auditar_email(**{
        **EMAIL_LIMPO,
        "assunto": "Um assunto longo demais para caber no celular e que continua por muito tempo ainda",
        "preview": "Um assunto longo demais para caber no celular",
    })
    assert "assunto-longo" in kinds(resultado)
    assert "preview-repete" in kinds(resultado)


def test_email_flags_generated_text_tells() -> None:
    resultado = auditar_email(**{
        **EMAIL_LIMPO,
        "corpo": (
            "Espero que este e-mail o encontre bem.\n\n"
            "Não é só uma planilha, é um novo jeito de trabalhar. Sem reunião, sem retrabalho, sem espera.\n\n"
            "O resultado? Mais tempo.\n\nClique aqui para ver."
        ),
    })
    achados = kinds(resultado)
    assert "abertura-generica" in achados
    assert "tell-contraste" in achados
    assert "lista-de-negacao" in achados
    assert "tell-pergunta-respondida" in achados


def test_email_flags_spam_and_missing_action() -> None:
    spam = auditar_email(**{**EMAIL_LIMPO, "assunto": "Ganhe dinheiro fácil hoje", "corpo": "Ganhe dinheiro fácil com este método. " * 3})
    assert "spam" in kinds(spam)

    sem_acao = auditar_email(**{**EMAIL_LIMPO, "corpo": "Um aviso curto sobre a manutenção de sábado.", "cta": ""})
    assert "sem-cta" in kinds(sem_acao)


def test_email_requires_unsubscribe_in_lifecycle_html() -> None:
    html = "<html><body><p>Conteúdo</p></body></html>"
    sem = auditar_email(**{**EMAIL_LIMPO, "html": html})
    assert "sem-descadastro" in kinds(sem)
    com = auditar_email(**{**EMAIL_LIMPO, "html": "<html><body><a href='/unsubscribe'>Descadastrar</a></body></html>"})
    assert "sem-descadastro" not in kinds(com)


def test_email_flags_fake_reply_on_cold_outreach() -> None:
    resultado = auditar_email(**{**EMAIL_LIMPO, "assunto": "Re: proposta", "tipo": "cold"})
    assert "assunto-falso" in kinds(resultado)


def test_email_rejects_bad_input() -> None:
    with pytest.raises(MarketingError):
        auditar_email(assunto="", corpo="Um corpo suficientemente longo para passar.")
    with pytest.raises(MarketingError):
        auditar_email(assunto="Oi", corpo="curto")
    with pytest.raises(MarketingError):
        auditar_email(assunto="Oi", corpo="Um corpo suficientemente longo para passar.", tipo="promo")


# ----------------------------------------------------------------------- seo


def test_clean_page_has_no_blockers() -> None:
    pagina = auditar_seo(html=_pagina_limpa(), palavra_chave="preço", url="https://exemplo.com/preco-saas")
    assert pagina["counts"]["must"] == 0
    metrics = pagina["metrics"]
    assert metrics["h1"] == 1
    assert metrics["sem_alt"] == 0
    assert metrics["jsonld"] == 1
    assert metrics["links_internos"] == 1
    assert metrics["links_externos"] == 2


def test_page_flags_titles_headings_and_alt() -> None:
    ruim = """<html><body><h1>Planos</h1><h3>Pulei o h2</h3>
    <img src="a.png"><a href="/x">x</a></body></html>"""
    resultado = auditar_seo(html=ruim)
    achados = kinds(resultado)
    assert "sem-title" in achados
    assert "sem-description" in achados
    assert "img-sem-alt" in achados
    assert "salto-de-nivel" in achados


def test_page_flags_cross_domain_canonical() -> None:
    html = _pagina_limpa().replace(
        'href="https://exemplo.com/preco-saas"', 'href="https://outro.com/preco-saas"'
    )
    resultado = auditar_seo(html=html, url="https://exemplo.com/preco-saas")
    assert "canonical-cruzado" in kinds(resultado)
    assert resultado["counts"]["must"] >= 1


def test_page_flags_invalid_jsonld() -> None:
    html = _pagina_limpa().replace(
        '{"@context":"https://schema.org","@type":"Article","headline":"Preço de SaaS"}',
        '{"@type":"Article"}',
    )
    assert "jsonld-invalido" in kinds(auditar_seo(html=html))


def test_page_flags_missing_keyword_and_direct_answer() -> None:
    html = _pagina_limpa().replace(
        "O preço de um plano SaaS sai de três números",
        "A definição de valor sai de três números",
    ).replace("preço", "valor")
    resultado = auditar_seo(html=html, palavra_chave="preço")
    achados = kinds(resultado)
    assert "chave-fora-do-title" in achados
    assert "chave-fora-do-h1" in achados


def test_page_rejects_html_too_short() -> None:
    with pytest.raises(MarketingError):
        auditar_seo(html="<html></html>")


# ------------------------------------------------------------------ anúncio


def test_google_ad_within_limits_passes() -> None:
    resultado = revisar_anuncio(
        plataforma="google",
        titulos="\n".join([
            "Automatize o funil de vendas",
            "Teste grátis por 14 dias",
            "Painel único para o time",
            "Relatório sem planilha",
        ]),
        descricoes="\n".join([
            "Organize leads, propostas e follow-up em um painel só, sem planilha paralela.",
            "Comece em cinco minutos e veja o funil inteiro no mesmo lugar, com histórico.",
        ]),
        url_final="https://exemplo.com/x?utm_content=pesquisa-marca",
    )
    assert resultado["counts"]["must"] == 0
    assert resultado["metrics"]["acima_do_limite"] == 0


def test_ad_counts_the_exact_overflow() -> None:
    resultado = revisar_anuncio(
        plataforma="meta",
        texto_principal="x" * 130,
        titulos="y" * 45,
        descricoes="z" * 35,
        url_final="https://exemplo.com/x",
    )
    longos = {achado["kind"]: achado["location"] for achado in resultado["findings"] if achado["kind"].endswith("-longo")}
    assert "5" in longos["texto_principal-longo"]
    assert "5" in longos["titulos-longo"]
    assert resultado["metrics"]["acima_do_limite"] == 3


def test_ad_requires_minimum_pieces() -> None:
    resultado = revisar_anuncio(plataforma="google", titulos="Um título só", url_final="https://exemplo.com")
    assert "titulos-faltando" in kinds(resultado)
    assert "descricoes-faltando" in kinds(resultado)


def test_ad_rejects_unverifiable_claims() -> None:
    resultado = revisar_anuncio(
        plataforma="linkedin",
        texto_principal="O melhor CRM do mercado, número 1 em satisfação.",
        titulos="Dobro de vendas garantido",
        url_final="https://exemplo.com",
    )
    achados = kinds(resultado)
    assert "claim-melhor-da-categoria" in achados
    assert "claim-numero-um" in achados
    assert "claim-garantia" in achados
    assert resultado["counts"]["must"] >= 1


def test_ad_rejects_bad_platform_and_empty_copy() -> None:
    with pytest.raises(MarketingError):
        revisar_anuncio(plataforma="tiktok", titulos="a")
    with pytest.raises(MarketingError):
        revisar_anuncio(plataforma="meta")


def test_ad_catalog_has_three_platforms() -> None:
    assert set(PLATAFORMAS) == {"google", "meta", "linkedin"}


# --------------------------------------------------------------------- API


def test_health_reports_the_new_version_and_skill_count(client: TestClient) -> None:
    health = client.get("/api/health").json()
    assert health["version"] == "0.60.2"
    assert health["skills"] == 288


def test_api_runs_every_marketing_skill(client: TestClient) -> None:
    orcamento = client.post("/api/skills/marketing.orcamento/execute", json={"parameters": ORCAMENTO}).json()
    assert orcamento["ok"] is True
    assert orcamento["result"]["metrics"]["roas"] > 1

    teste = client.post("/api/skills/marketing.teste/execute", json={"parameters": {
        "baseline": 10, "mde": 20, "trafego_diario": 5000,
    }}).json()
    assert teste["ok"] is True
    assert teste["result"]["metrics"]["por_variante"] > 3000

    utm = client.post("/api/skills/marketing.utm/execute", json={"parameters": {"urls": URLS_LIMPA}}).json()
    assert utm["ok"] is True
    assert utm["result"]["counts"]["must"] == 0

    email = client.post("/api/skills/marketing.email/execute", json={"parameters": EMAIL_LIMPO}).json()
    assert email["ok"] is True
    assert email["result"]["counts"]["must"] == 0

    seo = client.post("/api/skills/marketing.seo/execute", json={"parameters": {
        "html": _pagina_limpa(), "palavra_chave": "preço", "url": "https://exemplo.com/preco-saas",
    }}).json()
    assert seo["ok"] is True
    assert seo["result"]["metrics"]["h1"] == 1

    anuncio = client.post("/api/skills/marketing.anuncio/execute", json={"parameters": {
        "plataforma": "meta", "texto_principal": "Painel único para o funil inteiro, sem planilha.",
        "titulos": "Veja o funil inteiro", "url_final": "https://exemplo.com/x",
    }}).json()
    assert anuncio["ok"] is True
    assert anuncio["result"]["metrics"]["plataforma"] == "meta"

    regras = client.post("/api/skills/marketing.regras/execute", json={"parameters": {}}).json()
    assert regras["ok"] is True
    assert len(regras["result"]["plataformas"]) == 3
    assert len(regras["result"]["amostra"]) == 4


def test_api_is_read_only_and_reports_bad_parameters(client: TestClient) -> None:
    plano = client.post("/api/skills/marketing.orcamento/execute", json={"parameters": ORCAMENTO}).json()
    assert plano["result"]["executed"] is False
    assert plano["result"]["readOnly"] is True
    assert plano["result"]["executado"] is False

    ruim = client.post("/api/skills/marketing.teste/execute", json={"parameters": {
        "baseline": 0, "mde": 10, "trafego_diario": 100,
    }}).json()
    assert ruim["ok"] is False
    assert ruim["error"]["code"] == "SKILL_ERROR"

    extra = client.post("/api/skills/marketing.utm/execute", json={"parameters": {
        "urls": URLS_LIMPA, "conta": "x",
    }}).json()
    assert extra["ok"] is False


def test_catalog_matches_the_sample_calculation() -> None:
    catalogo = marketing_catalogo()
    linha = next(item for item in catalogo["amostra"] if item["baseline"] == 3)
    teste = dimensionar_teste(baseline=3.0, mde=20.0, trafego_diario=1000.0)
    assert linha["lift_20"] == teste["metrics"]["por_variante"]
    assert len(catalogo["integridade"]) == 6
    assert catalogo["executado"] is False


def test_utm_row_status_only_blocks_on_must_and_should(client):
    """`nice` é sugestão: a linha continua pronta; caixa alta e separador não."""
    resposta = client.post(
        "/api/skills/marketing.utm/execute",
        json={"parameters": {"urls": (
            "https://exemplo.com/a?utm_source=LinkedIn&utm_medium=creator&utm_campaign=c1&utm_content=x"
            "\nhttps://exemplo.com/b?utm_source=newsletter&utm_medium=newsletter&utm_campaign=c1"
        )}},
    )
    corpo = resposta.json()["result"]
    assert [linha["status"] for linha in corpo["rows"]] == ["corrigir", "ok"]
    assert corpo["metrics"]["corrigir"] == 1
    assert corpo["metrics"]["ok"] == 1
