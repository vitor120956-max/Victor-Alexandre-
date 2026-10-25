"""Testes da direção de arte inspirada em Leonxlnx/taste-skill (MIT, 2026).

Tudo é estático: nenhum script Node, navegador, plugin, CLI `npx skills` ou
marketplace do upstream é instalado, chamado ou executado. As fixtures
declaram briefing, argumento, copy, HTML, tells e notas em texto puro.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from server.app import create_app
from server.skill_registry import build_registry
from server.taste import (
    DIRECTIONS,
    JUDGE_DIMENSIONS,
    JUDGE_SIGNALS,
    ROLES,
    SECTORS,
    TONES,
    TasteError,
    audit_argument,
    deal_direction,
    direction_reference,
    judge_page,
)
from server.taste_rules import RULES, TELLS, WAVES, audit_copy, audit_tells, lint_page

BRIEF = (
    "Padaria de fermentação natural na rua das Palmeiras, 7 anos de forno a lenha, "
    "pão de 12 reais e mesa às 9h."
)
SECTIONS = "sobre, vitrine, como-funciona, contato"

CLEAN_CLAIMS = """sobre | A massa descansa 18 horas antes de assar | foto do forno a lenha aceso
vitrine | Sete pães saem do forno às 7h | tabela com nome, farinha e preço de cada pão
como-funciona | A encomenda fecha no dia anterior às 18h | capture do formulário com horário
contato | A padaria fica na rua das Palmeiras, 120 | mapa e horário de terça a domingo"""

CLEAN_HEADLINE = "Pão de fermentação natural"
CLEAN_SUPPORT = "Forno a lenha na rua das Palmeiras, desde 2019."
CLEAN_ACTION = "Ver o cardápio"

CLEAN_COPY = """manchete | Pão de fermentação natural
apoio | Forno a lenha na rua das Palmeiras, desde 2019.
corpo | A massa descansa 18 horas e sai do forno às 7h.
acao | Ver o cardápio
nav | Pães
nav | Forno
nav | Visita
legenda | Mesa às 9h."""

CLEAN_PAGE = """<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8"><title>Padaria Palmeiras</title>
<style>
:root { --bg: #fbfaf8; --ink: #1c1917; --accent: #7c2d12; }
.hero { background: var(--bg); color: var(--ink); padding: 96px 24px; }
.hero h1 { font-family: "Fraunces", Georgia, serif; font-size: clamp(40px, 6vw, 72px); letter-spacing: -0.01em; }
.button { background: var(--accent); color: #ffffff; border-radius: 8px; transition: background 160ms ease-out; }
.button:focus-visible { outline: 3px solid var(--accent); }
figure img { border-radius: 4px; }
</style></head>
<body><header><nav><a href="#paes">Pães</a><a href="#forno">Forno</a><a href="#visita">Visita</a></nav></header>
<main><section class="hero"><h1>Pão de fermentação natural</h1>
<p>Forno a lenha na rua das Palmeiras, desde 2019.</p><a class="button" href="#paes">Ver o cardápio</a></section>
<section id="paes"><h2>O que sai do forno</h2>
<img src="pao.jpg" alt="Pão escuro sobre a mesa"><img src="forno.jpg" alt="Forno a lenha aceso">
<img src="farinha.jpg" alt="Saco de farinha aberto"><img src="balcao.jpg" alt="Balcão da padaria">
<figure><img src="mesa.jpg" alt="Mesa posta"><figcaption>Mesa às 9h.</figcaption></figure>
</section></main></body></html>"""

DIRTY_PAGE = """<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8"><title>Acme</title>
<style>
.hero { background: linear-gradient(90deg, #6366f1, #06b6d4); }
.hero h1 { background-clip: text; -webkit-background-clip: text; font-family: Inter, sans-serif; }
.card { border: 1px solid #e5e7eb; box-shadow: 0 2px 8px rgba(0,0,0,.2); border-radius: 9999px; }
.label { text-transform: uppercase; letter-spacing: .08em; font-family: ui-monospace, monospace; }
.panel { backdrop-filter: blur(12px); }
.cta { transition: all 200ms ease-in; outline: none; }
</style></head>
<body><div class="eyebrow">Field notes</div><h2>01 / Novo</h2>
<p>Lorem ipsum dolor sit amet, plataforma para times modernos.</p><h1>Acme ✨</h1>
<img src="a.png"><div class="card">10x faster</div>
<pre><code>background: linear-gradient(90deg, #6366f1, #fff);</code></pre>
<div data-ui><span class="label">TABELA DE PREÇOS</span></div>
</body></html>"""

APP_PAGE = """<div class="app">
<style>
.mono { font-family: ui-monospace, monospace; }
.row { border-bottom: 1px solid #e5e7eb; }
.step { content: "01 /"; }
.primary { background: #3b82f6; }
</style>
<div class="mono">R$ 12,00</div><div class="row">João Silva</div><div class="step">01 / Enviar</div>
</div>"""

TELL_TEXT = (
    "Não é só uma padaria, é um laboratório. Est. 2024 · 48.5° N. "
    "Rápido. Simples. Seguro. Desbloqueie o sabor com o campo de notas."
)

JUDGE_SCORES = """design | 8 | Margens iguais em 1440 e 390; grid de 12 colunas e respiro constante.
usabilidade | 7 | Foco visível no botão; o formulário conclui em três campos.
criatividade | 5 | A ideia serviria a qualquer padaria da cidade.
conteudo | 8 | Claims com prova e a tabela de preços tem farinha e peso reais."""


@pytest.fixture()
def client(tmp_path) -> TestClient:
    return TestClient(create_app(registry=build_registry(tmp_path / "files")))


def kinds(result: dict) -> set[str]:
    return {item["kind"] for item in result["findings"]}


# ------------------------------------------------------------------- direção


def test_direction_is_deterministic_and_offers_three_options() -> None:
    first = deal_direction(brief=BRIEF, sector="alimentacao", sections=SECTIONS, tone="quente")
    second = deal_direction(brief=BRIEF, sector="alimentacao", sections=SECTIONS, tone="quente")
    assert first["seed"] == second["seed"]
    assert [option["id"] for option in first["options"]] == [option["id"] for option in second["options"]]
    assert len(first["options"]) == 3
    assert first["metrics"]["directions"] == len(DIRECTIONS) == 12
    assert first["options"][0]["id"] in {direction["id"] for direction in DIRECTIONS}
    assert first["sheet"] is None


def test_direction_seed_changes_the_hand() -> None:
    one = deal_direction(brief=BRIEF, sector="alimentacao", sections=SECTIONS, seed="alpha")
    two = deal_direction(brief=BRIEF, sector="alimentacao", sections=SECTIONS, seed="beta")
    assert one["seed"] == "alpha" and two["seed"] == "beta"
    assert [option["id"] for option in one["options"]] != [option["id"] for option in two["options"]]


def test_direction_sheet_covers_every_section_and_slot() -> None:
    dealt = deal_direction(brief=BRIEF, sector="alimentacao", sections=SECTIONS, tone="quente", have="fotografia")
    chosen = dealt["options"][0]["id"]
    result = deal_direction(
        brief=BRIEF, sector="alimentacao", sections=SECTIONS, tone="quente", have="fotografia",
        direction=chosen, redraws="hero | a marca já tem uma foto de capa que não pode ser trocada",
    )
    sheet = result["sheet"]
    assert sheet is not None
    assert [item["role"] for item in sheet["sections"]] == ["sobre", "vitrine", "como-funciona", "contato"]
    assert sheet["palette"]["mode"] == "dealt"
    assert "section:<papel>" in sheet["slots"]
    assert result["metrics"]["redraws"] == 1
    assert result["redraws"][0]["slot"] == "hero"
    assert "Redesenhos registrados" in result["markdown"]


def test_direction_preserves_brand_palette_and_type() -> None:
    dealt = deal_direction(brief=BRIEF, sector="alimentacao", sections=SECTIONS)
    result = deal_direction(
        brief=BRIEF, sector="alimentacao", sections=SECTIONS,
        direction=dealt["options"][0]["id"], keep="paleta, tipografia",
    )
    sheet = result["sheet"]
    assert sheet["palette"]["mode"] == "brand"
    assert "Tipografia da marca preservada" in sheet["type"]
    assert result["metrics"]["keep"] == 2


def test_direction_rejects_redraw_without_a_reason() -> None:
    dealt = deal_direction(brief=BRIEF, sector="alimentacao", sections=SECTIONS)
    result = deal_direction(
        brief=BRIEF, sector="alimentacao", sections=SECTIONS,
        direction=dealt["options"][0]["id"], redraws="palette | não gostei",
    )
    assert "redraw-without-reason" in kinds(result)
    assert result["counts"]["must"] >= 1


def test_direction_flags_vague_brief_and_missing_sections() -> None:
    vague = deal_direction(brief="Padaria moderna e premium", sector="alimentacao")
    assert "vague-brief" in kinds(vague) or "generic-brief" in kinds(vague)
    assert "sections-missing" in kinds(vague)

    minimal = deal_direction(brief="Padaria de fermentação natural na rua das Palmeiras", sections="vitrine")
    assert minimal["counts"]["must"] == 0


def test_direction_flags_unknown_vocabulary_but_still_deals() -> None:
    result = deal_direction(brief=BRIEF, sector="aeroespacial", sections="vitrine", tone="épico", have="holograma", keep="logo")
    assert {"unknown-sector", "unknown-tone", "unknown-asset", "unknown-keep"} <= kinds(result)
    assert len(result["options"]) == 3


def test_direction_accepts_aliases() -> None:
    result = deal_direction(brief=BRIEF, sector="food", sections="menu", tone="warm")
    assert result["metrics"]["sections"] == 1
    assert result["counts"]["must"] == 0


def test_direction_limits() -> None:
    with pytest.raises(TasteError):
        deal_direction(brief="   ", sections="vitrine")
    with pytest.raises(TasteError):
        deal_direction(brief=BRIEF, sections="vitrine", mode="turbo")


# ----------------------------------------------------------------- argumento


def test_argument_accepts_a_complete_argument() -> None:
    result = audit_argument(
        brief=BRIEF, claims=CLEAN_CLAIMS, headline=CLEAN_HEADLINE,
        support=CLEAN_SUPPORT, action=CLEAN_ACTION,
    )
    assert result["counts"] == {"must": 0, "should": 0, "nice": 0, "total": 0}
    assert result["metrics"]["sections"] == 4
    assert result["metrics"]["proofs"] == 4
    assert result["metrics"]["headlineChars"] == len(CLEAN_HEADLINE)


def test_argument_flags_claims_without_proof_and_empty_sections() -> None:
    result = audit_argument(
        brief=BRIEF,
        claims="sobre | A melhor padaria da região |\nvitrine |  | foto do balcão",
        headline="Pão", support="Padaria na rua das Palmeiras.", action="Ver",
    )
    assert {"claim-without-proof", "empty-claim"} <= kinds(result)
    assert any(item["status"] == "sem prova" for item in result["rows"])


def test_argument_flags_numbers_without_a_source() -> None:
    result = audit_argument(
        brief=BRIEF,
        claims="prova | 98% dos clientes voltam | planilha interna de vendas",
        headline="Pão de fermentação natural", support="Forno a lenha na rua das Palmeiras.", action="Ver o cardápio",
    )
    assert "invented-proof" in kinds(result)

    sourced = audit_argument(
        brief=BRIEF,
        claims="prova | 98% dos clientes voltam | pesquisa interna de 2025 com fonte no relatório anual",
        headline="Pão de fermentação natural", support="Forno a lenha na rua das Palmeiras.", action="Ver o cardápio",
    )
    assert "invented-proof" not in kinds(sourced)


def test_argument_measures_the_headline_budget() -> None:
    long = audit_argument(
        brief=BRIEF, claims=CLEAN_CLAIMS,
        headline="Pão de fermentação natural feito com farinha orgânica todas as manhãs",
        support=CLEAN_SUPPORT, action=CLEAN_ACTION,
    )
    assert "long-headline" in kinds(long)
    tight = audit_argument(
        brief=BRIEF, claims=CLEAN_CLAIMS, headline="Pão de fermentação natural da casa",
        support=CLEAN_SUPPORT, action=CLEAN_ACTION,
    )
    assert "headline-tight" in kinds(tight)


def test_argument_flags_forbidden_headline_forms() -> None:
    correction = audit_argument(
        brief=BRIEF, claims=CLEAN_CLAIMS, headline="Não é só uma padaria, é um laboratório",
        support=CLEAN_SUPPORT, action=CLEAN_ACTION,
    )
    assert "correction-copy" in kinds(correction)
    stock = audit_argument(
        brief=BRIEF, claims=CLEAN_CLAIMS, headline="Pão artesanal",
        support="Uma plataforma para times modernos, sem esforço e com qualidade.",
        action="Saiba mais",
    )
    assert {"stock-phrase", "generic-action"} <= kinds(stock)


def test_argument_lite_keeps_only_blockers() -> None:
    result = audit_argument(
        brief=BRIEF, claims=CLEAN_CLAIMS, headline="Pão",
        support=CLEAN_SUPPORT, action="Ver o cardápio", mode="lite",
    )
    assert all(item["group"] == "must" for item in result["findings"])
    assert result["questions"] == []


def test_argument_rejects_empty_and_oversized_input() -> None:
    with pytest.raises(TasteError):
        audit_argument(brief="  ", claims=CLEAN_CLAIMS)
    with pytest.raises(TasteError):
        audit_argument(brief=BRIEF, claims="a | b | c | d")


# ---------------------------------------------------------------------- copy


def test_copy_accepts_a_clean_deck() -> None:
    result = audit_copy(deck=CLEAN_COPY)
    assert result["counts"] == {"must": 0, "should": 0, "nice": 0, "total": 0}
    assert result["metrics"]["pieces"] == 8
    assert result["metrics"]["navLinks"] == 3
    assert result["metrics"]["headlineChars"] == len(CLEAN_HEADLINE)


def test_copy_requires_a_headline_and_bans_the_eyebrow() -> None:
    missing = audit_copy(deck="acao | Ver o cardápio\napoio | Uma padaria na rua das Palmeiras.")
    assert "no-headline" in kinds(missing)
    eyebrow = audit_copy(deck="eyebrow | Field notes\nmanchete | Pão de fermentação natural\nacao | Ver o cardápio")
    assert "eyebrow-banned" in kinds(eyebrow)
    assert eyebrow["counts"]["must"] >= 1


def test_copy_flags_multiple_primary_actions_and_stock_labels() -> None:
    result = audit_copy(deck=(
        "manchete | Pão de fermentação natural\n"
        "acao | Saiba mais\nacao | Ver o cardápio\nacao | Baixar o aplicativo agora\n"
    ))
    assert {"stock-action", "multiple-primary", "action-long"} <= kinds(result)


def test_copy_measures_support_navigation_and_body() -> None:
    body = " ".join(["farinha"] * 45)
    result = audit_copy(deck=(
        "manchete | Pão de fermentação natural\n"
        f"apoio | {' '.join(['longa'] * 26)}\n"
        f"corpo | {body}\n"
        "acao | Ver o cardápio\n"
        "nav | Um\nnav | Dois\nnav | Três\nnav | Quatro\nnav | Cinco\nnav | Seis\n"
    ))
    assert {"support-long", "nav-long"} <= kinds(result)


def test_copy_flags_micro_typography_and_placeholders() -> None:
    result = audit_copy(deck=(
        'manchete | Pão de fermentação natural\n'
        'apoio | O forno "a lenha" da rua das Palmeiras...\n'
        "corpo | Seu texto aqui\n"
        "acao | Ver o cardápio\n"
        "rotulo | FEITO COM MUITO AMOR E TEMPO\n"
    ))
    assert {"straight-quotes", "three-dots", "placeholder-copy", "micro-caps"} <= kinds(result)


def test_copy_rejects_unknown_roles_and_empty_values() -> None:
    result = audit_copy(deck="titulo principal | Pão\nmanchete |  ")
    assert {"unknown-role", "empty-copy"} <= kinds(result)


# ---------------------------------------------------------------------- lint


def test_lint_accepts_a_clean_page() -> None:
    result = lint_page(source=CLEAN_PAGE)
    assert result["counts"]["total"] == 0, result["findings"]
    assert result["metrics"]["h1"] == 1
    assert result["metrics"]["images"] == 5


def test_lint_finds_the_house_rule_offenders() -> None:
    result = lint_page(source=DIRTY_PAGE)
    found = kinds(result)
    assert {"gradient", "gradient-text", "purple", "shadow", "mono", "numbering", "eyebrow", "emoji", "lorem", "hairline", "pill", "glass", "transition-all", "outline-none"} <= found
    assert "default-font" in found
    assert result["metrics"]["must"] >= 2
    # Blocos isentos não contam: o gradiente roxo dentro de <pre><code> e o rótulo em [data-ui].
    assert result["metrics"]["escapes"] >= 2
    assert "micro-label" in found


def test_lint_ignores_a_line_marked_with_the_escape() -> None:
    escaped = '<style>.x { font-family: Inter; } /* taste-skill-ignore */</style><h1>Título</h1>'
    result = lint_page(source=escaped)
    assert "default-font" not in kinds(result)


def test_lint_app_mode_turns_off_density_rules() -> None:
    page = lint_page(source=APP_PAGE)
    app = lint_page(source=APP_PAGE, surface="app")
    assert {"mono", "hairline"} <= kinds(page)
    assert "mono" not in kinds(app)
    assert "hairline" not in kinds(app)
    assert {"placeholder-data", "framework-blue"} <= kinds(app)
    assert app["metrics"]["skipped"] >= 4


def test_lint_requires_a_title_and_four_images() -> None:
    thin = '<html><body><h2>Sem título</h2><img src="a.png"></body></html>'
    result = lint_page(source=thin)
    assert {"no-h1", "few-images"} <= kinds(result)
    assert result["metrics"]["h1"] == 0
    assert result["metrics"]["images"] == 1


def test_lint_limits() -> None:
    with pytest.raises(TasteError):
        lint_page(source="   ")
    with pytest.raises(TasteError):
        lint_page(source="<html></html>", surface="mobile")


# --------------------------------------------------------------------- tells


def test_tells_accepts_neutral_copy() -> None:
    result = audit_tells(text="A massa descansa dezoito horas e sai do forno às sete da manhã.")
    assert result["metrics"]["hits"] == 0
    assert result["verdict"] == "Nenhum tell do registro aparece no material declarado."
    assert result["metrics"]["catalog"] == len(TELLS)


def test_tells_recognises_dated_motifs() -> None:
    result = audit_tells(text=TELL_TEXT)
    found = {row["id"] for row in result["rows"]}
    assert {"not-x-but-y", "est-year", "coordinates", "tricolon", "unlock"} <= found
    assert result["metrics"]["wave2"] >= 3
    assert result["metrics"]["dominant"].startswith("Onda 2")
    assert "Registro completo" in result["markdown"]


def test_tells_filters_by_kind() -> None:
    result = audit_tells(text=TELL_TEXT, kind="texto")
    assert all(row["kind"] == "texto" for row in result["rows"])
    assert len(result["catalog"]) == len(TELLS)
    assert result["metrics"]["unused"] == len(TELLS) - len(result["rows"])


def test_tells_limits() -> None:
    with pytest.raises(TasteError):
        audit_tells(text="  ")
    with pytest.raises(TasteError):
        audit_tells(text="texto", kind="sonoro")


# ---------------------------------------------------------------------- júri


def test_judge_weights_and_applies_caps() -> None:
    result = judge_page(scores=JUDGE_SCORES, signals="serviria-a-qualquer-um | sim\nmenos-de-4-fotos | sim")
    assert result["metrics"]["rawWeighted"] == pytest.approx(7.1)
    assert result["metrics"]["weighted"] == pytest.approx(6.5)
    assert result["metrics"]["final"] == pytest.approx(6.5)
    assert result["metrics"]["capLoss"] == pytest.approx(0.6)
    assert result["metrics"]["band"] == "com ressalvas"
    assert result["metrics"]["weakest"] == "criatividade"
    assert len(result["caps"]) == 2
    assert "6,5" in result["verdict"]


def test_judge_global_cap_limits_the_final_note() -> None:
    scores = """design | 9 | Grid e margens conferidos em três larguras.
usabilidade | 9 | Foco visível e formulário com três campos.
criatividade | 9 | A ideia só existe nesta padaria e em nenhuma outra.
conteudo | 9 | Provas com fonte, data e preço verificados."""
    result = judge_page(scores=scores, signals="faixa-em-branco | sim")
    assert result["metrics"]["weighted"] == pytest.approx(9.0)
    assert result["metrics"]["final"] == pytest.approx(5.0)
    assert result["metrics"]["band"] == "não publicar"
    assert result["metrics"]["capLoss"] == pytest.approx(4.0)


def test_judge_needs_all_four_dimensions() -> None:
    result = judge_page(scores="design | 8 | Margens iguais em 1440 e 390 com respiro.\nusabilidade | 7 | Foco visível no botão principal do herói.")
    assert result["metrics"]["final"] is None
    assert result["metrics"]["dimensions"] == 2
    assert result["counts"]["must"] >= 2
    assert "missing-dimension" in kinds(result)
    assert "Não existe nota parcial" in result["verdict"]


def test_judge_validates_evidence_signals_and_scores() -> None:
    result = judge_page(scores=JUDGE_SCORES, signals="sinal inventado | sim")
    assert "unknown-signal" in kinds(result)
    with pytest.raises(TasteError):
        judge_page(scores=JUDGE_SCORES.replace("| 8 |", "| 12 |", 1))


def test_judge_limits() -> None:
    with pytest.raises(TasteError):
        judge_page(scores="design | abc | evidência com referência")
    invalid_state = judge_page(scores=JUDGE_SCORES, signals="mono | talvez")
    assert "signals-invalid" in kinds(invalid_state)


# ----------------------------------------------------------------- biblioteca


def test_library_lists_the_whole_vocabulary() -> None:
    reference = direction_reference()
    assert reference["metrics"] == {
        "directions": 12, "sectors": 10, "tones": 7, "roles": len(ROLES),
        "assets": 5, "dimensions": 4, "signals": len(JUDGE_SIGNALS), "waves": 3,
    }
    assert len(reference["rows"]) == 12
    assert len(reference["caps"]) == len(JUDGE_SIGNALS)
    assert "Referência completa" in reference["verdict"]
    assert set(JUDGE_DIMENSIONS) == {"design", "usabilidade", "criatividade", "conteudo"}
    assert len(RULES) >= 20 and len(TELLS) >= 20
    assert set(WAVES) == {1, 2, 3}


# ------------------------------------------------------------------------ API


def test_health_reports_the_new_version_and_skill_count(client: TestClient) -> None:
    health = client.get("/api/health").json()
    assert health["version"] == "0.37.6"
    assert health["skills"] == 209


def test_api_runs_every_taste_skill(client: TestClient) -> None:
    direction = client.post("/api/skills/taste.direction/execute", json={"parameters": {
        "brief": BRIEF, "sector": "alimentacao", "sections": SECTIONS, "tone": "quente",
    }}).json()
    assert direction["ok"] is True
    assert len(direction["result"]["options"]) == 3

    argument = client.post("/api/skills/taste.argument/execute", json={"parameters": {
        "brief": BRIEF, "claims": CLEAN_CLAIMS, "headline": CLEAN_HEADLINE,
        "support": CLEAN_SUPPORT, "action": CLEAN_ACTION,
    }}).json()
    assert argument["ok"] is True
    assert argument["result"]["counts"]["total"] == 0

    copy = client.post("/api/skills/taste.copy/execute", json={"parameters": {"deck": CLEAN_COPY}}).json()
    assert copy["ok"] is True
    assert copy["result"]["metrics"]["pieces"] == 8

    lint = client.post("/api/skills/taste.lint/execute", json={"parameters": {"source": CLEAN_PAGE}}).json()
    assert lint["ok"] is True
    assert lint["result"]["counts"]["total"] == 0

    tells = client.post("/api/skills/taste.tells/execute", json={"parameters": {"text": TELL_TEXT}}).json()
    assert tells["ok"] is True
    assert tells["result"]["metrics"]["hits"] >= 4

    judge = client.post("/api/skills/taste.judge/execute", json={"parameters": {
        "scores": JUDGE_SCORES, "signals": "serviria-a-qualquer-um | sim",
    }}).json()
    assert judge["ok"] is True
    assert judge["result"]["metrics"]["final"] == pytest.approx(7.1)

    library = client.post("/api/skills/taste.library/execute", json={"parameters": {}}).json()
    assert library["ok"] is True
    assert library["result"]["metrics"]["directions"] == 12


def test_api_is_read_only_and_rejects_bad_parameters(client: TestClient) -> None:
    lint = client.post("/api/skills/taste.lint/execute", json={"parameters": {"source": CLEAN_PAGE}}).json()
    assert lint["result"]["executed"] is False
    assert lint["result"]["readOnly"] is True

    invalid_mode = client.post("/api/skills/taste.direction/execute", json={"parameters": {
        "brief": BRIEF, "sections": SECTIONS, "mode": "turbo",
    }})
    assert invalid_mode.json()["ok"] is False
    assert "mode" in invalid_mode.json()["error"]["message"]

    bad_surface = client.post("/api/skills/taste.lint/execute", json={"parameters": {"source": CLEAN_PAGE, "surface": "mobile"}})
    assert bad_surface.json()["ok"] is False

    empty_deck = client.post("/api/skills/taste.copy/execute", json={"parameters": {"deck": "   "}})
    assert empty_deck.json()["ok"] is False

    oversized = client.post("/api/skills/taste.argument/execute", json={"parameters": {
        "brief": BRIEF, "claims": "a | b | c | d",
    }})
    assert oversized.json()["ok"] is False
