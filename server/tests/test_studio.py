"""Testes do estúdio de design inspirado em nexu-io/open-design (Apache-2.0).

Tudo é estático: nenhum daemon, CLI, plugin, MCP, runtime de agente, Docker ou
provedor do upstream é instalado, chamado ou executado. As fixtures declaram
manifesto, prosa, tokens, pares de contraste, notas e HTML em texto.
"""
from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from server.app import create_app
from server.skill_registry import build_registry
from server.studio import (
    CANONICAL_SCHEMA,
    DIMENSIONS,
    SCHEMA_TOKENS,
    StudioError,
    audit_artifact,
    audit_contrast,
    audit_contract,
    contrast_ratio,
    critique,
    design_reference,
    luminance,
)

MANIFEST = json.dumps(
    {
        "schemaVersion": CANONICAL_SCHEMA,
        "id": "acme-papel",
        "name": "Acme Papel",
        "category": "SaaS",
        "description": "Sistema editorial de papel quente para times pequenos.",
        "source": {"type": "bundled", "origin": "acme"},
        "files": {"design": "DESIGN.md", "tokens": "tokens.css"},
    },
    ensure_ascii=False,
)

DESIGN = """# Acme Papel
## Tema
Editorial, papel quente e contraste alto; nada de gradiente nem de brilho solto.
## Cor
Acento único em verde profundo, fundo branco quente e texto quase preto.
## Tipografia
Display serifada, corpo sans humanista e mono apenas para números e código.
## Espaçamento
Grade de 4px; seções com respiro generoso no desktop e compacto no celular.
## Componentes
Botão primário sólido, secundário com anel de 1px e foco sempre visível.
## Movimento
Entrada de 200ms com ease-out forte, saída de 140ms e alternativa reduzida.
## Acessibilidade
Texto normal a 4.5:1, texto grande a 3:1, foco visível e navegação por teclado.
## Antíteses
Sem gradiente roxo, sem emoji como ícone, sem métrica inventada e sem placeholder.
"""

TOKENS = """:root {
  --bg: #faf9f6; --surface: #ffffff; --surface-warm: #f5f1ea;
  --fg: #18181b; --fg-2: #27272a; --muted: #57534e; --meta: #78716c;
  --border: #e7e5e4; --border-soft: #f0efed;
  --accent: #0f766e; --accent-on: #ffffff; --accent-hover: #115e59; --accent-active: #134e4a;
  --success: #16a34a; --warn: #ca8a04; --danger: #dc2626;
  --font-display: "Fraunces", serif; --font-body: "Inter", sans-serif; --font-mono: ui-monospace, monospace;
  --text-xs: 12px; --text-sm: 14px; --text-base: 16px; --text-lg: 18px;
  --text-xl: 22px; --text-2xl: 28px; --text-3xl: 40px; --text-4xl: 56px;
  --leading-body: 1.6; --leading-tight: 1.1; --tracking-display: -0.02em;
  --space-1: 4px; --space-2: 8px; --space-3: 12px; --space-4: 16px;
  --space-5: 20px; --space-6: 24px; --space-8: 32px; --space-12: 48px;
  --section-y-desktop: 96px; --section-y-tablet: 64px; --section-y-phone: 48px;
  --radius-sm: 8px; --radius-md: 12px; --radius-lg: 16px; --radius-pill: 9999px;
  --elev-flat: none; --elev-ring: 0 0 0 1px var(--border);
  --elev-raised: 0 2px 8px rgba(0, 0, 0, 0.08); --focus-ring: 0 0 0 3px var(--accent);
  --motion-fast: 150ms; --motion-base: 200ms; --ease-standard: cubic-bezier(0.23, 1, 0.32, 1);
  --container-max: 1120px; --container-gutter-desktop: 32px;
  --container-gutter-tablet: 24px; --container-gutter-phone: 16px;
}
[data-theme="dark"] {
  --bg: #111113; --fg: #fafafa; --surface: #18181b; --border: #27272a; --muted: #a1a1aa;
}
.card { padding: var(--space-4); border: 1px solid var(--border); background: var(--surface); }
.button { background: var(--accent); color: var(--accent-on); transition: background var(--motion-fast) var(--ease-standard); }
@media (prefers-reduced-motion: reduce) { .button { transition: none; } }
"""

CRITIQUE = """filosofia | 8 | O chrome mantém vol.04 e o kicker em .serif em todas as páginas, sem misturar registros.
hierarquia | 6 | Na página 3 o `.stat` usa 40px e o h1 usa 42px, então os dois competem pelo primeiro olhar.
detalhe | 5 | A coluna direita da página 8 começa 2vh acima da esquerda; `.callout` usa margem 3vh e a figura não.
funcao | 9 | A navegação por teclado funciona em todas as páginas e o formulário de contato conclui em 12px de foco visível.
inovacao | 4 | Nenhum movimento tipográfico próprio: o `.deck` poderia ser de qualquer agência de 2024.
"""

KEEP = "- A capa em .cover usa a serif no tamanho certo\n- O ritmo de 200ms no hover está consistente\n- A paleta de papel quente sustenta as fotos"
FIX = "- Igualar a base das colunas na página 8\n- Reduzir o peso do número em .stat na página 3\n- Unificar a legenda mono e sans em .caption"
WINS = "- Trocar o flex por grid na página 4 (10 min)\n- Ajustar o tracking do kicker para 0.08em (5 min)\n- Alinhar a margem do .callout com a figura (15 min)"

CLICHES = """<!doctype html>
<html><head><title>Plataforma</title>
<style>
:root { --accent: #0f766e; }
.hero { background: linear-gradient(90deg, #3b82f6, #06b6d4); }
h1 { font-family: Inter, sans-serif; }
.card { border-left: 4px solid #7c3aed; }
.btn { background: #6366f1; transition: transform 150ms ease-in; }
.label { text-transform: uppercase; }
</style></head>
<body><h1>Plataforma ✨</h1><p>10x faster deploys com 99.9% uptime.</p>
<img src="https://cdn.example.com/a.png"><p>Lorem ipsum dolor sit amet.</p>
<a href="https://x.com" target="_blank">Rede</a>
<iframe src="https://x"></iframe>
<script src="https://cdn.example.com/x.js"></script>
</body></html>"""

CLEAN_ARTIFACT = """<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8"><title>Acme Papel</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
:root { --bg: #faf9f6; --fg: #18181b; --accent: #0f766e; --surface: #ffffff; --border: #e7e5e4; }
.hero { background: var(--bg); color: var(--fg); }
h1 { font-family: "Fraunces", serif; letter-spacing: -0.02em; }
.card { border: 1px solid var(--border); padding: var(--space-4); }
.label { text-transform: uppercase; letter-spacing: 0.08em; }
@media (prefers-reduced-motion: reduce) { .hero { animation: none; } }
</style></head>
<body><h1>Acme</h1><img src="a.png" alt="Produto em uso">
<section><div class="card"><p>Entrega em 12 minutos por semana.</p></div></section>
</body></html>"""


@pytest.fixture()
def client(tmp_path) -> TestClient:
    return TestClient(create_app(registry=build_registry(tmp_path / "files")))


def kinds(result: dict) -> set[str]:
    return {item["kind"] for item in result["findings"]}


# ------------------------------------------------------------------ contrato


def test_contract_accepts_a_complete_package() -> None:
    result = audit_contract(manifest=MANIFEST, design=DESIGN, tokens=TOKENS)
    assert result["counts"] == {"must": 0, "should": 0, "nice": 0, "total": 0}
    assert result["metrics"] == {
        "tokensDeclared": 56, "requiredFound": 56, "requiredTotal": 56,
        "headings": 8, "themes": 1, "rawColors": 0, "manifest": True,
    }
    assert result["executed"] is False
    assert result["readOnly"] is True
    assert result["analysis"] == "contract"
    assert "## Slots por grupo" in result["markdown"]
    assert len(result["rows"]) == 14


def test_contract_rejects_broken_manifests() -> None:
    broken = audit_contract(manifest="{ \"schemaVersion\": ", tokens=TOKENS)
    assert "manifest-json" in kinds(broken)

    not_object = audit_contract(manifest="[]", tokens=TOKENS)
    assert "manifest-object" in kinds(not_object)

    payload = json.loads(MANIFEST)
    payload["schemaVersion"] = "od-design-system-project/v2"
    payload["id"] = "Acme Studio"
    payload["files"] = {"design": "docs/DESIGN.md", "tokens": "../tokens.css"}
    invalid = audit_contract(manifest=json.dumps(payload, ensure_ascii=False), tokens=TOKENS)
    assert {"manifest-schema", "manifest-id", "manifest-design-path", "manifest-unsafe-path"} <= kinds(invalid)


def test_contract_flags_manifest_metadata_as_nice() -> None:
    payload = json.loads(MANIFEST)
    for key in ("name", "category", "description", "source"):
        payload.pop(key)
    result = audit_contract(manifest=json.dumps(payload), tokens=TOKENS)
    assert {"manifest-name", "manifest-category", "manifest-description", "manifest-source"} <= kinds(result)
    assert result["counts"]["must"] == 0


def test_contract_requires_substantive_design() -> None:
    thin = "# Marca\n## Tema\nCurto.\n## Cor\nVerde.\n## Tipografia\nSerif.\n"
    result = audit_contract(design=thin, tokens=TOKENS)
    assert "design-sections" in kinds(result)
    assert "design-empty-section" in kinds(result)

    placeholder = DESIGN.replace("contraste alto", "TODO: contraste alto")
    assert "design-placeholder" in kinds(audit_contract(design=placeholder, tokens=TOKENS))

    no_h1 = DESIGN.split("\n", 1)[1]
    assert "design-h1" in kinds(audit_contract(design=no_h1, tokens=TOKENS))


def test_contract_checks_the_token_schema() -> None:
    missing = TOKENS.replace("--accent-hover: #115e59;", "").replace("--space-12: 48px;", "")
    result = audit_contract(tokens=missing)
    assert "missing-tokens" in kinds(result)
    assert result["metrics"]["requiredFound"] == 54

    empty = TOKENS.replace("--font-mono: ui-monospace, monospace;", "--font-mono: ;")
    assert "empty-token" in kinds(audit_contract(tokens=empty))

    undefined = TOKENS.replace("background: var(--surface);", "background: var(--surface-raised);")
    assert "undefined-token" in kinds(audit_contract(tokens=undefined))

    raw = TOKENS.replace("border: 1px solid var(--border);", "border: 1px solid #d6d3d1;")
    result = audit_contract(tokens=raw)
    assert "raw-color" in kinds(result)
    assert result["metrics"]["rawColors"] == 1


def test_contract_checks_theme_parity_and_depth() -> None:
    shallow = TOKENS.replace('[data-theme="dark"] {\n  --bg: #111113; --fg: #fafafa; --surface: #18181b; --border: #27272a; --muted: #a1a1aa;\n}',
                             '[data-theme="dark"] { --bg: #111113; --fg: #fafafa; }')
    result = audit_contract(tokens=shallow)
    assert "theme-shallow" in kinds(result)

    without_fg = TOKENS.replace('[data-theme="dark"] {\n  --bg: #111113; --fg: #fafafa;', '[data-theme="dark"] {\n  --bg: #111113;')
    assert "theme-parity" in kinds(audit_contract(tokens=without_fg))


def test_contract_checks_motion_defaults() -> None:
    no_reduced = TOKENS.replace('@media (prefers-reduced-motion: reduce) { .button { transition: none; } }\n', "")
    assert "reduced-motion" in kinds(audit_contract(tokens=no_reduced))

    scale_zero = TOKENS.replace(".button { background", ".button { transform: scale(0); background")
    assert "scale-zero" in kinds(audit_contract(tokens=scale_zero))

    ease_in = TOKENS.replace("transition: background var(--motion-fast) var(--ease-standard);",
                             "transition: background var(--motion-fast) ease-in;")
    assert "ease-in" in kinds(audit_contract(tokens=ease_in))

    weak_ease = TOKENS.replace("--ease-standard: cubic-bezier(0.23, 1, 0.32, 1);", "--ease-standard: linear;")
    assert "ease-standard-weak" in kinds(audit_contract(tokens=weak_ease))


def test_contract_flags_unknown_and_unused_tokens() -> None:
    unknown = TOKENS.replace("--container-max: 1120px;", "--container-max: 1120px; --brand-sparkle: #ff00aa;")
    result = audit_contract(tokens=unknown)
    assert {"unknown-token", "unused-token"} <= kinds(result)
    assert result["counts"]["must"] == 0

    used_extension = TOKENS.replace(
        "--container-max: 1120px;", "--container-max: 1120px; --brand-sparkle: #ff00aa;"
    ).replace(".card {", ".card { color: var(--brand-sparkle);")
    result = audit_contract(tokens=used_extension)
    assert "unknown-token" in kinds(result)
    assert "unused-token" not in kinds(result)

    documented = DESIGN + "\nO token `--brand-sparkle` existe para o realce de lançamento.\n"
    result = audit_contract(design=documented, tokens=unknown)
    assert "unknown-token" not in kinds(result)


def test_contract_requires_tokens_when_prose_or_manifest_exists() -> None:
    result = audit_contract(design=DESIGN, manifest=MANIFEST)
    assert "tokens-missing" in kinds(result)
    assert "design-missing" not in kinds(result)

    only_tokens = audit_contract(tokens=TOKENS)
    assert "design-missing" in kinds(only_tokens)
    assert only_tokens["counts"]["must"] == 0


def test_contract_modes_and_limits() -> None:
    lite = audit_contract(design=DESIGN.split("\n", 1)[1], tokens=TOKENS, mode="lite")
    assert {item["group"] for item in lite["findings"]} <= {"must"}
    assert "design-h1" not in kinds(lite)

    ultra = audit_contract(manifest=MANIFEST, design=DESIGN, tokens=TOKENS, mode="ultra")
    assert len(ultra["questions"]) == 3

    with pytest.raises(StudioError):
        audit_contract(tokens=TOKENS, mode="turbo")
    with pytest.raises(StudioError):
        audit_contract()
    with pytest.raises(StudioError):
        audit_contract(manifest=" " * 20_001, tokens=TOKENS)
    with pytest.raises(StudioError):
        audit_contract(tokens=":root {" + " " * 120_001 + "}", mode="lite")


# ----------------------------------------------------------------- contraste


def test_contrast_measures_aa_aaa_and_large_text() -> None:
    pairs = """# rótulo | frente | fundo | tamanho
Corpo | #18181b | #faf9f6 | corpo
Secundário | #78716c | #faf9f6 | corpo
Botão | #ffffff | #0f766e | corpo
Rodapé | #a1a1aa | #fafafa | corpo
Herói | #8a8a8a | #ffffff | grande
"""
    result = audit_contrast(pairs=pairs)
    rows = {row["label"]: row for row in result["rows"]}
    assert rows["Corpo"]["level"] == "AAA"
    assert rows["Botão"]["level"] == "AA"
    assert rows["Herói"]["aa"] == 3.0
    assert rows["Herói"]["level"] == "AA"
    assert rows["Rodapé"]["level"] == "reprovado"
    assert result["metrics"] == {
        "pairs": 5, "failAA": 1, "passAAA": 1, "minRatio": 2.46, "worst": "Rodapé",
    }
    assert "contrast-fail" in kinds(result)
    assert "contrast-aaa" in kinds(result)

    lite = audit_contrast(pairs=pairs, mode="lite")
    assert {item["group"] for item in lite["findings"]} == {"must"}


@pytest.mark.parametrize(
    ("foreground", "background", "ratio"),
    [("#000000", "#ffffff", 21.0), ("#777777", "#ffffff", 4.48), ("#0f766e", "#ffffff", 5.47)],
)
def test_contrast_ratio_matches_wcag_examples(foreground: str, background: str, ratio: float) -> None:
    assert round(contrast_ratio(foreground, background), 2) == pytest.approx(ratio, abs=0.01)
    assert 0.0 <= luminance(background) <= 1.0


def test_contrast_reports_invalid_and_incomplete_pairs() -> None:
    pairs = """Bom | #18181b | #faf9f6 | corpo
Sem fundo | #18181b | | corpo
Hex inválido | #ggg | #ffffff | corpo
Rgb | rgb(0,0,0) | #ffffff | corpo
"""
    result = audit_contrast(pairs=pairs)
    assert {"missing-color", "invalid-color"} <= kinds(result)
    assert result["metrics"]["pairs"] == 1
    assert result["metrics"]["failAA"] == 0

    with pytest.raises(StudioError):
        audit_contrast(pairs="a | #000 | #fff | corpo | extra")
    with pytest.raises(StudioError):
        audit_contrast(pairs="  ")


# ------------------------------------------------------------------- crítica


def test_critique_accepts_a_complete_report() -> None:
    result = critique(entries=CRITIQUE, keep=KEEP, fix=FIX, quick_wins=WINS)
    assert result["counts"]["must"] == 0
    assert result["counts"]["should"] == 0
    assert result["metrics"] == {
        "dimensions": 5, "mean": 6.4, "weakest": "inovacao",
        "weakestScore": 4, "keep": 3, "fix": 3, "quickWins": 3,
    }
    assert [item["axis"] for item in result["radar"]] == [key for key, *_ in DIMENSIONS]
    assert [item["band"] for item in result["radar"]] == ["Forte", "Funcional", "Funcional", "Excepcional", "Quebrado"]
    assert result["bands"][0] == {"low": 0, "high": 4, "label": "Quebrado"}
    assert result["keep"] == [line.lstrip("- ") for line in KEEP.split("\n")]
    assert "Eixo mais fraco: Inovação com 4/10 (Quebrado)." in result["verdict"]
    assert result["executed"] is False


def test_critique_requires_all_five_dimensions_with_evidence() -> None:
    missing = "\n".join(line for line in CRITIQUE.split("\n") if not line.startswith("inovacao"))
    result = critique(entries=missing, keep=KEEP, fix=FIX, quick_wins=WINS)
    assert "missing-dimension" in kinds(result)
    assert any("Inovação" in item["what"] for item in result["findings"] if item["kind"] == "missing-dimension")
    assert result["verdict"].startswith("Faltam 1 nota")

    unknown = CRITIQUE + "originalidade | 7 | Um momento em .pullquote na página 2 merecia nota e não estava no contrato.\n"
    assert "unknown-dimension" in kinds(critique(entries=unknown, keep=KEEP, fix=FIX, quick_wins=WINS))

    duplicated = CRITIQUE + "função | 7 | O `.form` conclui em 12px de foco e mensagens claras no envio.\n"
    assert "duplicate-dimension" in kinds(critique(entries=duplicated, keep=KEEP, fix=FIX, quick_wins=WINS))

    bad_score = CRITIQUE.replace("| 8 |", "| 11 |", 1)
    assert "invalid-score" in kinds(critique(entries=bad_score, keep=KEEP, fix=FIX, quick_wins=WINS))

    thin = CRITIQUE.replace(
        "O chrome mantém vol.04 e o kicker em .serif em todas as páginas, sem misturar registros.",
        "Parece inconsistente.",
    )
    assert "thin-evidence" in kinds(critique(entries=thin, keep=KEEP, fix=FIX, quick_wins=WINS))

    no_citation = CRITIQUE.replace(
        "Nenhum movimento tipográfico próprio: o `.deck` poderia ser de qualquer agência de 2024.",
        "Nenhum movimento tipográfico próprio e o deck poderia ser de qualquer agência de 2024.",
    )
    assert "no-citation" in kinds(critique(entries=no_citation, keep=KEEP, fix=FIX, quick_wins=WINS))


def test_critique_flags_inflation_and_missing_weak_axis() -> None:
    inflated = """filosofia | 9 | O `.chrome` mantém vol.04 em todas as páginas, sem misturar registros editoriais.
hierarquia | 9 | O `.hero` usa 64px e o h2 usa 24px, então a ordem de leitura é inequívoca.
detalhe | 9 | As colunas da página 8 alinham na mesma base e o `.callout` segue a margem da figura.
funcao | 9 | O `.form` conclui em 12px de foco visível e o teclado percorre os campos na ordem certa.
inovacao | 9 | A `.pullquote` da página 2 desloca o eixo e vira o momento próprio do deck.
"""
    result = critique(entries=inflated, keep=KEEP, fix=FIX, quick_wins=WINS)
    assert {"grade-inflation", "no-weak-axis"} <= kinds(result)
    assert "média 9.0" in result["findings"][0]["location"] or result["metrics"]["mean"] == 9.0


def test_critique_checks_actions_and_quick_wins() -> None:
    short = critique(entries=CRITIQUE, keep="- Um item", fix="", quick_wins="")
    assert {"manter-short", "corrigir-short", "ganhos rápidos-short"} <= kinds(short)

    slow = WINS + "\n- Refatorar o layout inteiro (45 min)"
    result = critique(entries=CRITIQUE, keep=KEEP, fix=FIX, quick_wins=slow)
    assert "win-out-of-range" in kinds(result)

    untimed = WINS + "\n- Ajustar o espaçamento do rodapé"
    assert "win-without-time" in kinds(critique(entries=CRITIQUE, keep=KEEP, fix=FIX, quick_wins=untimed))


def test_critique_modes_and_errors() -> None:
    lite = critique(entries="filosofia | 7 | Evidência curta.\n", keep=KEEP, fix=FIX, quick_wins=WINS, mode="lite")
    assert {item["group"] for item in lite["findings"]} <= {"must"}
    assert lite["questions"] == []

    ultra = critique(entries=CRITIQUE, keep=KEEP, fix=FIX, quick_wins=WINS, mode="ultra")
    assert len(ultra["questions"]) == 3

    with pytest.raises(StudioError):
        critique(entries=CRITIQUE, keep=KEEP, fix=FIX, quick_wins=WINS, mode="rapido")
    with pytest.raises(StudioError):
        critique(entries="  ")
    with pytest.raises(StudioError):
        critique(entries="filosofia | 7 | ok | extra")


# ------------------------------------------------------------------ artefato


def test_artifact_flags_the_lexical_cliches() -> None:
    result = audit_artifact(artifact=CLICHES)
    assert {
        "trust-gradient", "indigo-accent", "emoji-icon", "invented-metric", "filler-copy",
        "sans-display", "external-js", "missing-alt", "no-reduced-motion",
        "raw-color", "blank-noopener", "caps-no-tracking", "external-image",
        "left-accent", "iframe-sandbox",
    } <= kinds(result)
    assert result["metrics"]["scripts"] == 1
    assert result["metrics"]["images"] == 1
    assert result["metrics"]["styles"] == 1
    assert result["counts"]["must"] >= 8
    assert result["verdict"].startswith("Corrija 1")


def test_artifact_flags_purple_gradient_and_structure_gaps() -> None:
    purple = '<div style="background: linear-gradient(135deg, #8b5cf6, #a855f7)"></div>'
    result = audit_artifact(artifact=purple)
    assert {"purple-gradient", "no-doctype", "no-title", "no-viewport"} <= kinds(result)
    assert "trust-gradient" not in kinds(result)

    no_lang = '<!doctype html><html><head><title>Ok</title><meta name="viewport" content="width=device-width"></head><body></body></html>'
    assert "no-lang" in kinds(audit_artifact(artifact=no_lang))


def test_artifact_accepts_a_clean_single_file() -> None:
    result = audit_artifact(artifact=CLEAN_ARTIFACT)
    assert result["counts"]["total"] == 0, result["findings"]
    assert result["metrics"] == {
        "characters": len(CLEAN_ARTIFACT), "lines": CLEAN_ARTIFACT.count("\n") + 1,
        "styles": 1, "scripts": 0, "images": 1, "sections": 1, "rules": 0,
    }
    assert result["executed"] is False


def test_artifact_flags_external_dependencies() -> None:
    css = '<!doctype html><html lang="pt-BR"><head><title>T</title><meta name="viewport" content="width=device-width"><link rel="stylesheet" href="https://cdn.example.com/a.css"></head><body></body></html>'
    assert "external-css" in kinds(audit_artifact(artifact=css))

    imported = '<!doctype html><html lang="pt-BR"><head><title>T</title><meta name="viewport" content="width=device-width"><style>@import url("https://fonts.example.com/x.css");</style></head><body></body></html>'
    assert "external-import" in kinds(audit_artifact(artifact=imported))

    script = '<!doctype html><html lang="pt-BR"><head><title>T</title><meta name="viewport" content="width=device-width"></head><body><script src="https://cdn.example.com/a.js"></script></body></html>'
    assert "external-js" in kinds(audit_artifact(artifact=script))

    iframe = '<!doctype html><html lang="pt-BR"><head><title>T</title><meta name="viewport" content="width=device-width"></head><body><iframe src="https://x.example"></iframe></body></html>'
    assert "iframe-sandbox" in kinds(audit_artifact(artifact=iframe))

    handler = '<!doctype html><html lang="pt-BR"><head><title>T</title><meta name="viewport" content="width=device-width"></head><body><button onclick="go()">Ir</button></body></html>'
    assert "inline-handler" in kinds(audit_artifact(artifact=handler))

    quotes = '<!doctype html><html lang="pt-BR"><head><title>T</title><meta name="viewport" content="width=device-width"></head><body><code>echo “oi”</code></body></html>'
    assert "smart-quotes" in kinds(audit_artifact(artifact=quotes))


def test_artifact_modes_and_limits() -> None:
    lite = audit_artifact(artifact=CLICHES, mode="lite")
    assert {item["group"] for item in lite["findings"]} <= {"must"}
    assert lite["questions"] == []

    ultra = audit_artifact(artifact=CLEAN_ARTIFACT, mode="ultra")
    assert len(ultra["questions"]) == 3

    with pytest.raises(StudioError):
        audit_artifact(artifact=CLICHES, mode="turbo")
    with pytest.raises(StudioError):
        audit_artifact(artifact="   ")
    with pytest.raises(StudioError):
        audit_artifact(artifact="x" * 200_001, mode="lite")


# ---------------------------------------------------------------- referência


def test_reference_documents_the_schema() -> None:
    reference = design_reference()
    assert reference["schemaVersion"] == CANONICAL_SCHEMA
    assert reference["metrics"] == {"slots": 56, "groups": 14, "dimensions": 5, "bands": 4}
    assert len(SCHEMA_TOKENS) == 56
    assert {item["key"] for item in reference["groups"]} == {
        "surface", "text", "border", "accent", "semantic", "fonts", "scale", "rhythm",
        "space", "section", "radius", "elevation", "motion", "layout",
    }
    assert reference["bands"][-1]["label"] == "Excepcional"
    assert reference["executed"] is False
    assert reference["readOnly"] is True


# ---------------------------------------------------------------------- API


def test_api_exposes_the_studio_catalog_and_reference(client: TestClient) -> None:
    health = client.get("/api/health").json()
    assert health["version"] == "0.17.0"
    assert health["skills"] == 93

    catalog = client.get("/api/skills").json()["skills"]
    studio = {skill["id"] for skill in catalog if skill["id"].startswith("studio.")}
    assert studio == {
        "studio.contract", "studio.contrast", "studio.critique",
        "studio.artifact", "studio.defaults",
    }

    baseline = client.post("/api/skills/studio.defaults/execute", json={"parameters": {}})
    assert baseline.status_code == 200
    assert baseline.json()["result"]["metrics"]["slots"] == 56


def test_api_executes_studio_skills_without_side_effects(client: TestClient) -> None:
    contract = client.post(
        "/api/skills/studio.contract/execute",
        json={"parameters": {"manifest": MANIFEST, "design": DESIGN, "tokens": TOKENS}},
    ).json()
    assert contract["ok"] is True
    assert contract["result"]["counts"]["must"] == 0
    assert contract["result"]["executed"] is False

    contrast = client.post(
        "/api/skills/studio.contrast/execute",
        json={"parameters": {"pairs": "Corpo | #18181b | #faf9f6 | corpo\nRodapé | #a1a1aa | #fafafa | grande"}},
    ).json()
    assert contrast["ok"] is True
    assert contrast["result"]["metrics"]["pairs"] == 2

    critique_body = client.post(
        "/api/skills/studio.critique/execute",
        json={"parameters": {"entries": CRITIQUE, "keep": KEEP, "fix": FIX, "quickWins": WINS}},
    ).json()
    assert critique_body["ok"] is True
    assert critique_body["result"]["metrics"]["quickWins"] == 3

    artifact = client.post(
        "/api/skills/studio.artifact/execute",
        json={"parameters": {"artifact": CLEAN_ARTIFACT}},
    ).json()
    assert artifact["ok"] is True
    assert artifact["result"]["counts"]["total"] == 0


def test_api_rejects_invalid_studio_parameters(client: TestClient) -> None:
    invalid_mode = client.post(
        "/api/skills/studio.contract/execute",
        json={"parameters": {"tokens": TOKENS, "mode": "turbo"}},
    )
    assert invalid_mode.json()["ok"] is False
    assert "mode" in invalid_mode.json()["error"]["message"]

    empty = client.post("/api/skills/studio.contrast/execute", json={"parameters": {"pairs": "  "}})
    assert empty.json()["ok"] is False

    bad_pair = client.post(
        "/api/skills/studio.contrast/execute",
        json={"parameters": {"pairs": "a | #000 | #fff | corpo | extra"}},
    )
    assert bad_pair.json()["ok"] is False
    assert "no máximo 4" in bad_pair.json()["error"]["message"]

    missing_field = client.post("/api/skills/studio.artifact/execute", json={"parameters": {}})
    assert missing_field.json()["ok"] is False
