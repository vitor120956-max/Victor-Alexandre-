"""Testes da camada editorial inspirada em cathrynlavery/diagram-design (MIT, 2026).

Tudo é estático: nenhum script do upstream (verify-geometry, self_check,
lint-render, export_svg, export_png) é instalado, chamado ou executado, e nenhum
navegador é aberto. As fixtures são pedidos, tokens, HTML e geometria em texto.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from server.app import create_app
from server.editorial import (
    ACESSIBILIDADE,
    ANTIPADROES,
    DETALHES,
    EditorialError,
    PADROES,
    PAPEIS,
    PLATEIAS,
    PRESETS,
    RAMPAS,
    REGRAS_CONECTOR,
    TIPOS,
    checar_conectores,
    checar_entrega,
    editorial_catalog,
    escolher_tipo,
    lint_editorial,
    planejar_importacao,
    resolver_marca,
)
from server.skill_registry import build_registry

PEDIDO_FILA = (
    "O leitor precisa entender por que o webhook de pagamento entra numa fila e "
    "espera o worker livre, e o que acontece quando a fila enche."
)

MARCA_CLEAN = """paper=#f5f5f5
paper-2=#ececec
ink=#2d3142
muted=#4f5d75
soft=#5a6580
rule=rgba(45,49,66,0.12)
rule-solid=#bfc0c0
accent=#bf4520
accent-tint=rgba(191,69,32,0.08)
link=#2e5aa8"""

MARCA_FRACA = """paper=#f5f5f5
ink=#2d3142
soft=#8a8f9e
accent=#f7591f"""

HTML_CLEAN = """<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8"><title>Fila de webhooks</title>
<style>
:root{--paper:#f5f5f5;--ink:#2d3142;--muted:#4f5d75;--soft:#5a6580;--accent:#bf4520}
body{background:var(--paper);color:var(--ink);font-family:'Geist',system-ui,sans-serif}
.diagram-container{width:100%;overflow-x:auto}
svg{width:100%;min-width:960px;display:block}
.node-name{font-family:'Geist',system-ui,sans-serif;font-size:12px;font-weight:600}
.sublabel{font-family:'Geist Mono',ui-monospace,monospace;font-size:9px}
.arrow-label{font-family:'Geist Mono',ui-monospace,monospace;font-size:8px}
@media print{.diagram-container{overflow-x:visible}svg{min-width:0}}
</style></head>
<body><div class="diagram-container">
<svg viewBox="0 0 960 600" role="img" aria-labelledby="fila-title fila-desc" xmlns="http://www.w3.org/2000/svg">
<title id="fila-title">Fila de webhooks do pagamento</title>
<desc id="fila-desc">Webhooks entram numa fila limitada e um worker único processa cada um antes de liberar o recibo.</desc>
<defs><marker id="arrow" markerWidth="8" markerHeight="6" refX="7" refY="3" orient="auto"><polygon points="0 0, 8 3, 0 6" fill="#4f5d75"/></marker></defs>
<rect x="0" y="0" width="960" height="600" fill="#f5f5f5"/>
<rect x="200" y="200" width="200" height="48" rx="6" fill="#f5f5f5"/>
<rect x="200" y="200" width="200" height="48" rx="6" fill="#ececec" stroke="#2d3142" stroke-width="1"/>
<text x="300" y="228" class="node-name" text-anchor="middle">Fila de webhooks</text>
<path d="M 400 224 H 600" stroke="#4f5d75" fill="none" marker-end="url(#arrow)"/>
<rect x="250" y="196" width="36" height="12" rx="2" fill="#f5f5f5"/>
<text x="268" y="205" class="arrow-label" text-anchor="middle" letter-spacing="0.06em">CONSOME</text>
</svg></div></body></html>"""

HTML_DIRTY = """<!doctype html>
<html><head><style>
body{font-family:JetBrains Mono, monospace}
.card{box-shadow:0 8px 24px rgba(0,0,0,.3);border-radius:24px;background:#0a0a2e}
.glow{filter:drop-shadow(0 0 18px cyan)}
.grid{display:grid;grid-template-columns:repeat(3,1fr)}
.v{writing-mode:vertical-rl}
</style></head>
<body><svg viewBox="0 0 960 600">
<rect x="10" y="10" width="200" height="80" rx="6" fill="#2d3142"/>
<rect x="10" y="110" width="200" height="80" rx="6" fill="#2d3142"/>
<rect x="10" y="210" width="200" height="80" rx="6" fill="#2d3142"/>
<rect x="10" y="310" width="200" height="80" rx="6" fill="#2d3142"/>
<rect x="10" y="410" width="200" height="80" rx="6" fill="#2d3142"/>
<text x="700" y="300" font-size="8">LEGEND</text>
<text x="20" y="40" font-size="8">ENVIA</text>
<img src="https://cdn.example.com/logo.png" alt="">
</svg></body></html>"""

CONECTORES_CLEAN = """[
 {"id":"a","de":{"x":100,"y":100,"w":160,"h":48,"lado":"direita"},
  "para":{"x":400,"y":100,"w":160,"h":48,"lado":"esquerda"},
  "pontos":[[260,124],[400,124]],"rotulo":"ENVIA","mascara":{"x":300,"y":100,"w":52,"h":12},"raio":8},
 {"id":"b","de":{"x":100,"y":220,"w":160,"h":48},
  "para":{"x":400,"y":220,"w":160,"h":48},
  "pontos":[[260,244],[330,244],[330,300],[400,300]],"raio":8},
 {"id":"c","de":{"x":100,"y":340,"w":160,"h":48},
  "para":{"x":400,"y":340,"w":160,"h":48},
  "pontos":[[260,364],[400,364]],"tracejado":true}
]"""

CONECTORES_DIRTY = """[
 {"id":"diag","pontos":[[100,100],[300,250]]},
 {"id":"rot","pontos":[[100,400],[500,400]],"rotulo":"PROCESSA O EVENTO INTEIRO",
  "mascara":{"x":260,"y":396,"w":200,"h":12}},
 {"id":"masc","pontos":[[600,100],[900,100]],"rotulo":"GRAVA","mascara":{"x":660,"y":92,"w":60,"h":12},
  "nosDepois":[{"x":680,"y":80,"w":80,"h":40}]},
 {"id":"meio","pontos":[[100,520],[900,520]],"rotulo":"ATRAVESSA","cruzaCaixa":1,"setaNaIntermediaria":true},
 {"id":"curto","pontos":[[100,560],[400,560]],"raio":4}
]"""

MERMAID = """flowchart LR
  A[Cliente] -->|POST /v2| B[Gateway]
  B --> C[Pedidos]
  C --> D[(Postgres)]
  D --> E[(Réplica)]
  E --> F[Relatórios]
  F --> G[Cache quente]
  G --> H[Fila]
  H --> I[Worker]
  I --> A
"""

MERMAID_COM_FOLHAS = """flowchart LR
  A[Cliente] --> B[Gateway]
  B --> C[Pedidos]
  C --> D[(Postgres)]
  A --> E[Métrica]
  A --> F[Log de acesso]
  B --> G[Nota adesiva]
  C --> H[CI]
  B --> I[Tracing]
"""

DRAWIO = """<mxfile host="app.diagrams.net"><diagram id="p" name="Page-1"><mxGraphModel><root>
<mxCell id="0"/><mxCell id="1" parent="0"/>
<mxCell id="2" value="Cliente" vertex="1" parent="1"/>
<mxCell id="3" value="Gateway" vertex="1" parent="1"/>
<mxCell id="4" value="Pedidos" vertex="1" parent="1"/>
<mxCell id="5" value="Core" vertex="1" parent="1"/>
<mxCell id="6" value="Postgres" vertex="1" parent="5"/>
<mxCell id="7" value="Cache" vertex="1" parent="5"/>
<mxCell id="8" edge="1" parent="1" source="2" target="3"/>
<mxCell id="9" edge="1" parent="1" source="3" target="4"/>
</root></mxGraphModel></diagram></mxfile>"""

EXCALIDRAW = """{"type":"excalidraw","elements":[
 {"id":"a","type":"rectangle"},{"id":"b","type":"ellipse"},
 {"id":"t1","type":"text","text":"Cliente","containerId":"a"},
 {"id":"t2","type":"text","text":"Servidor","containerId":"b"},
 {"id":"e1","type":"arrow","startBinding":{"elementId":"a"},"endBinding":{"elementId":"b"}}
]}"""


@pytest.fixture()
def client(tmp_path) -> TestClient:
    return TestClient(create_app(registry=build_registry(tmp_path / "files")))


def kinds(result: dict) -> set[str]:
    return {item["kind"] for item in result["findings"]}


# ------------------------------------------------------------------ catálogo


def test_catalog_covers_the_upstream_vocabulary() -> None:
    catalogo = editorial_catalog()
    assert len(catalogo["tipos"]) == 45
    assert len(catalogo["padroes"]) == 9
    assert len(catalogo["papeis"]) == len(PAPEIS) == 11
    assert len(catalogo["anti_padroes"]) == 12
    assert len(catalogo["presets"]) == 10
    assert len(catalogo["conector"]) == 6
    assert len(catalogo["acessibilidade"]) == 6
    assert len(catalogo["variantes"]) == 6
    assert catalogo["contraste"] == {"texto": 4.5, "marca": 3.0}
    assert catalogo["executado"] is False
    assert catalogo["fonte"] == "cathrynlavery/diagram-design (MIT)"


def test_catalog_keeps_the_type_budgets_of_the_upstream() -> None:
    por_id = {item["id"]: item for item in editorial_catalog()["tipos"]}
    assert por_id["arquitetura"]["nos"] == 8
    assert por_id["linha"]["nos"] == 5
    assert por_id["dispersao"]["nos"] == 30
    assert por_id["raia"]["nos"] == 9
    assert por_id["camadas"]["nos"] == 6
    assert all(item["arestas"] >= 0 for item in por_id.values())
    assert "slopegraph" in por_id["linha"]["uso"]
    assert "beeswarm" in por_id["dispersao"]["uso"]


def test_presets_are_divisible_by_four_and_ramps_match() -> None:
    for chave, dados in PRESETS.items():
        if dados["w"]:
            assert dados["w"] % 4 == 0 and dados["h"] % 4 == 0, chave
        assert dados["rampa"] in RAMPAS
    assert PRESETS["slide-16x9"]["rampa"] == "presentation"
    assert RAMPAS["presentation"]["nome"] == 16
    assert RAMPAS["standard"]["nome"] == 12
    assert RAMPAS["print"]["titulo"] == 32


def test_conector_and_accessibility_rules_are_declared() -> None:
    assert [regra["id"] for regra in REGRAS_CONECTOR] == [1, 2, 3, 4, 5, 6]
    assert "6–10px" in REGRAS_CONECTOR[1]["regra"]
    assert "12px" in REGRAS_CONECTOR[3]["regra"]
    assert "4,3" in REGRAS_CONECTOR[4]["regra"]
    assert len(ACESSIBILIDADE) == 6
    assert "role=\"img\"" in ACESSIBILIDADE[0]["regra"]
    assert len(DETALHES) == 3 and DETALHES["faithful"]["nos"] == 24


# ---------------------------------------------------------------------- tipo


def test_type_selection_uses_the_pattern_before_the_visual_type() -> None:
    resultado = escolher_tipo(pedido=PEDIDO_FILA, plateia="engenharia", destino="deck", nos=6, modo="ultra")
    assert resultado["padrao"] == "fila"
    assert resultado["tipo"] == PADROES["fila"]["tipo"]
    assert resultado["preset"] == "slide-16x9"
    assert resultado["plano"][0] == "padrão: fila"
    assert resultado["metrics"]["teto"] <= 9
    assert resultado["questions"]
    assert resultado["executed"] is False
    assert "Recibo" not in resultado["markdown"]


def test_type_selection_is_deterministic() -> None:
    primeiro = escolher_tipo(pedido=PEDIDO_FILA, plateia="", destino="docs", nos=5, modo="full")
    segundo = escolher_tipo(pedido=PEDIDO_FILA, plateia="", destino="docs", nos=5, modo="full")
    assert primeiro["markdown"] == segundo["markdown"]


def test_type_selection_flags_a_budget_overflow() -> None:
    resultado = escolher_tipo(pedido=PEDIDO_FILA, plateia="", destino="blog", nos=26, modo="full")
    assert "acima-do-orcamento" in kinds(resultado)
    assert resultado["counts"]["must"] >= 1


def test_type_selection_suggests_a_table_for_lists() -> None:
    resultado = escolher_tipo(pedido="Listar os campos do cadastro de cliente", plateia="", destino="docs", nos=4, modo="full")
    assert "tabela-basta" in kinds(resultado)


def test_type_selection_reports_an_unknown_request() -> None:
    resultado = escolher_tipo(pedido="Organizar o pensamento sobre o trimestre", plateia="", destino="", nos=0, modo="full")
    assert "tipo-indefinido" in kinds(resultado)
    assert resultado["metrics"]["confianca"] == "baixa"


def test_type_selection_maps_the_destination_to_a_preset() -> None:
    assert escolher_tipo(pedido=PEDIDO_FILA, plateia="", destino="figma", nos=9, modo="lite")["preset"] == "fit"
    assert escolher_tipo(pedido=PEDIDO_FILA, plateia="", destino="print", nos=9, modo="lite")["preset"] == "print-a4-landscape"
    assert escolher_tipo(pedido=PEDIDO_FILA, plateia="", destino="linkedin", nos=9, modo="lite")["preset"] == "social-og"


def test_type_selection_rejects_short_requests() -> None:
    with pytest.raises(EditorialError):
        escolher_tipo(pedido="fila", plateia="", destino="", nos=1, modo="full")
    with pytest.raises(EditorialError):
        escolher_tipo(pedido=PEDIDO_FILA, plateia="", destino="", nos=500, modo="full")


def test_lite_mode_hides_optional_findings() -> None:
    cheio = escolher_tipo(pedido=PEDIDO_FILA, plateia="", destino="deck", nos=5, modo="full")
    leve = escolher_tipo(pedido=PEDIDO_FILA, plateia="", destino="deck", nos=5, modo="lite")
    assert cheio["counts"]["total"] >= leve["counts"]["total"]
    assert all(item["group"] == "must" for item in leve["findings"])


# --------------------------------------------------------------------- marca


def test_brand_tokens_resolve_and_pass_contrast() -> None:
    resultado = resolver_marca(marca=MARCA_CLEAN, escuro=False, modo="full")
    tokens = resultado["tokens"]
    assert tokens["paper"] == "#f5f5f5"
    assert tokens["ink"] == "#2d3142"
    assert tokens["accent"] == "#bf4520"
    assert resultado["metrics"]["falhas"] == 0
    assert resultado["metrics"]["tokens"] == 11
    assert resultado["metrics"]["tema"] == "claro"
    acento = next(item for item in resultado["rows"] if item["papel"] == "accent")
    assert acento["contraste"] == pytest.approx(4.71, abs=0.02)


def test_brand_tokens_flag_low_contrast_and_propose_a_fix() -> None:
    resultado = resolver_marca(marca=MARCA_FRACA, escuro=False, modo="full")
    falhas = {item["papel"]: item for item in resultado["rows"] if item["situacao"] == "falha"}
    assert set(falhas) == {"soft", "accent"}
    assert falhas["accent"]["contraste"] < 4.5
    assert falhas["accent"]["proposto"].startswith("#")
    assert resultado["tokens"]["accent"] == falhas["accent"]["proposto"]
    assert "contraste" in kinds(resultado)
    assert resultado["counts"]["must"] == 2


def test_brand_tokens_handle_the_dark_theme() -> None:
    resultado = resolver_marca(marca="paper=#2d3142\nink=#f5f5f5", escuro=True, modo="full")
    assert resultado["metrics"]["tema"] == "escuro"
    assert resultado["tokens"]["accent"] == "#f08a59"
    assert resultado["metrics"]["falhas"] == 0


def test_brand_tokens_reject_unknown_roles_and_bad_colors() -> None:
    desconhecido = resolver_marca(marca="paper=#f5f5f5\nbrand=#ff0000", escuro=False, modo="full")
    assert "papel-desconhecido" in kinds(desconhecido)
    with pytest.raises(EditorialError):
        resolver_marca(marca="paper=vermelho", escuro=False, modo="full")
    with pytest.raises(EditorialError):
        resolver_marca(marca="   ", escuro=False, modo="full")
    with pytest.raises(EditorialError):
        resolver_marca(marca="paper=#f5f5f5", escuro=False, modo="turbo")


# ---------------------------------------------------------------------- lint


def test_lint_accepts_a_clean_editorial_file() -> None:
    resultado = lint_editorial(html=HTML_CLEAN, modo="full")
    assert resultado["counts"]["must"] == 0
    assert resultado["counts"]["total"] == 0
    assert resultado["metrics"]["obrigatorios"] == 0


def test_lint_finds_the_generic_patterns() -> None:
    resultado = lint_editorial(html=HTML_DIRTY, modo="full")
    achados = kinds(resultado)
    assert {"sombra", "raio-grande", "jetbrains", "caixas-iguais", "legenda-solta"} <= achados
    assert "externo" in achados
    assert resultado["counts"]["must"] >= 2


def test_lint_requires_accessible_svg() -> None:
    resultado = lint_editorial(html="<html><body><svg viewBox='0 0 10 10'><title>x</title></svg></body></html>", modo="full")
    assert "sem-role" in kinds(resultado)


def test_lint_counts_an_accent_flood() -> None:
    html = "<svg role=\"img\">" + "".join(
        f"<rect x=\"{i * 10}\" y=\"0\" width=\"8\" height=\"8\" fill=\"accent\"/>" for i in range(5)
    ) + "</svg>"
    resultado = lint_editorial(html=html, modo="full")
    assert "acento-demais" in kinds(resultado)


def test_lint_rejects_diagonals_and_short_input() -> None:
    diagonal = lint_editorial(html="<svg role=\"img\"><line x1=\"0\" y1=\"0\" x2=\"40\" y2=\"60\"/></svg>", modo="full")
    assert "diagonal" in kinds(diagonal)
    reta = lint_editorial(html="<svg role=\"img\"><line x1=\"0\" y1=\"20\" x2=\"40\" y2=\"20\"/></svg>", modo="full")
    assert "diagonal" not in kinds(reta)
    with pytest.raises(EditorialError):
        lint_editorial(html="<svg/>", modo="full")


# ----------------------------------------------------------------- conector


def test_connectors_accept_orthogonal_geometry() -> None:
    resultado = checar_conectores(conectores=CONECTORES_CLEAN, modo="full")
    assert resultado["counts"]["must"] == 0, [item["kind"] for item in resultado["findings"]]
    assert resultado["metrics"]["conectores"] == 3
    assert resultado["metrics"]["diagonais"] == 0
    assert resultado["metrics"]["tracejados"] == 1


def test_connectors_flag_every_rule_break() -> None:
    resultado = checar_conectores(conectores=CONECTORES_DIRTY, modo="full")
    achados = kinds(resultado)
    assert {"diagonal", "rotulo-longo", "sem-mascara", "mascara-sobre-no", "transito",
            "seta-intermediaria", "raio-pequeno"} <= achados
    assert resultado["counts"]["must"] >= 4


def test_connectors_measure_the_label_gap() -> None:
    html = '[{"id":"x","pontos":[[0,100],[300,100]],"rotulo":"GRAVA","mascara":{"x":120,"y":96,"w":40,"h":12}}]'
    resultado = checar_conectores(conectores=html, modo="full")
    assert "folga-rotulo" in kinds(resultado)
    assert resultado["counts"]["must"] >= 1
    ok = '[{"id":"x","pontos":[[0,100],[300,100]],"rotulo":"GRAVA","mascara":{"x":120,"y":82,"w":40,"h":12}}]'
    assert "folga-rotulo" not in kinds(checar_conectores(conectores=ok, modo="full"))


def test_connectors_flag_parallel_overlap_and_fan() -> None:
    sobreposto = """[
     {"id":"a","pontos":[[0,100],[400,100]]},
     {"id":"b","pontos":[[0,104],[400,104]]}
    ]"""
    assert "sobreposicao" in kinds(checar_conectores(conectores=sobreposto, modo="full"))
    leque = """[
     {"id":"a","de":{"x":0,"y":0,"w":100,"h":40,"lado":"direita"},"para":{"x":300,"y":0,"w":100,"h":40},"pontos":[[100,20],[300,20]]},
     {"id":"b","de":{"x":0,"y":0,"w":100,"h":40,"lado":"direita"},"para":{"x":300,"y":80,"w":100,"h":40},
      "pontos":[[100,26],[200,26],[200,100],[300,100]]}
    ]"""
    resultado = checar_conectores(conectores=leque, modo="full")
    assert "leque" in kinds(resultado)


def test_connectors_reject_bad_payloads() -> None:
    with pytest.raises(EditorialError):
        checar_conectores(conectores="{nao é json", modo="full")
    with pytest.raises(EditorialError):
        checar_conectores(conectores="[]", modo="full")
    with pytest.raises(EditorialError):
        checar_conectores(conectores='{"conectores": []}', modo="full")
    sem_geometria = checar_conectores(conectores='[{"id":"a"}]', modo="full")
    assert "sem-geometria" in kinds(sem_geometria)


# ----------------------------------------------------------------- importar


def test_import_builds_a_fidelity_ledger() -> None:
    resultado = planejar_importacao(fonte=MERMAID_COM_FOLHAS, formato="mermaid", tamanho="doc-inline",
                                    detalhe="simplified", plateia="mixed", modo="full")
    assert resultado["metrics"]["origem_nos"] == 9
    assert resultado["metrics"]["nos"] <= 7
    assert resultado["ledger"]
    assert all(corte["passo"] >= 1 for corte in resultado["ledger"])
    assert "Recibo de fidelidade" in resultado["markdown"]
    assert resultado["executed"] is False


def test_import_escalates_when_the_graph_cannot_shrink() -> None:
    resultado = planejar_importacao(fonte=MERMAID, formato="mermaid", tamanho="doc-inline",
                                    detalhe="simplified", plateia="executive", modo="full")
    assert resultado["metrics"]["origem_nos"] == 9
    assert resultado["metrics"]["origem_arestas"] == 9
    assert resultado["digest"]["dividir"] is True
    assert resultado["ledger"] == []
    assert "acima-do-teto" in kinds(resultado)


def test_import_keeps_every_node_under_faithful() -> None:
    resultado = planejar_importacao(fonte=MERMAID, formato="mermaid", tamanho="doc-wide",
                                    detalhe="faithful", plateia="engineer", modo="full")
    assert resultado["metrics"]["nos"] == 9
    assert resultado["ledger"] == []
    assert "zonas-obrigatorias" not in kinds(resultado)


def test_import_detects_repeated_labels_and_technical_names() -> None:
    repetido = "flowchart LR\n  A[Worker] --> B[Fila]\n  C[Worker] --> B\n"
    resultado = planejar_importacao(fonte=repetido, formato="mermaid", tamanho="doc-inline",
                                    detalhe="faithful", plateia="engineer", modo="full")
    assert "rotulos-iguais" in kinds(resultado)
    tecnico = "flowchart LR\n  A[Auth :8443] --> B[(Postgres /v2)]\n"
    executivo = planejar_importacao(fonte=tecnico, formato="mermaid", tamanho="doc-inline",
                                    detalhe="balanced", plateia="executive", modo="full")
    assert "plateia-tecnica" in kinds(executivo)


def test_import_reads_drawio_and_excalidraw() -> None:
    drawio = planejar_importacao(fonte=DRAWIO, formato="drawio", tamanho="doc-inline",
                                 detalhe="balanced", plateia="mixed", modo="full")
    assert drawio["metrics"]["origem_nos"] == 6
    assert drawio["metrics"]["origem_arestas"] == 2
    excalidraw = planejar_importacao(fonte=EXCALIDRAW, formato="excalidraw", tamanho="fit",
                                    detalhe="balanced", plateia="engineer", modo="full")
    assert excalidraw["metrics"]["origem_nos"] == 2
    assert excalidraw["metrics"]["origem_arestas"] == 1


def test_import_flags_compressed_drawio_and_bad_formats() -> None:
    comprimido = '<mxfile><diagram id="x">7VZNbxNBDN2dGmJ0ZXh0IHF1ZSBu428gc2UgbGVlIGRlIGZvcm1hIGFsZ3VtYQ==</diagram></mxfile>'
    resultado = planejar_importacao(fonte=comprimido, formato="drawio", tamanho="doc-inline",
                                    detalhe="balanced", plateia="mixed", modo="full")
    assert "comprimido" in kinds(resultado)
    with pytest.raises(EditorialError):
        planejar_importacao(fonte="<html/>", formato="drawio", tamanho="doc-inline",
                            detalhe="balanced", plateia="mixed", modo="full")
    with pytest.raises(EditorialError):
        planejar_importacao(fonte="sequenceDiagram\n", formato="mermaid", tamanho="doc-inline",
                            detalhe="balanced", plateia="mixed", modo="full")
    with pytest.raises(EditorialError):
        planejar_importacao(fonte="{}", formato="excalidraw", tamanho="doc-inline",
                            detalhe="balanced", plateia="mixed", modo="full")


def test_import_dials_are_validated() -> None:
    with pytest.raises(EditorialError):
        planejar_importacao(fonte=MERMAID, formato="mermaid", tamanho="a4", detalhe="balanced",
                            plateia="mixed", modo="full")
    with pytest.raises(EditorialError):
        planejar_importacao(fonte=MERMAID, formato="mermaid", tamanho="fit", detalhe="ultra",
                            plateia="mixed", modo="full")
    with pytest.raises(EditorialError):
        planejar_importacao(fonte=MERMAID, formato="mermaid", tamanho="fit", detalhe="balanced",
                            plateia="cto", modo="full")
    with pytest.raises(EditorialError):
        planejar_importacao(fonte=MERMAID, formato="pdf", tamanho="fit", detalhe="balanced",
                            plateia="mixed", modo="full")
    assert PLATEIAS["executive"]["sublabel"] == "nenhum"


# ------------------------------------------------------------------ entrega


def test_delivery_accepts_the_contract() -> None:
    resultado = checar_entrega(html=HTML_CLEAN, preset="doc-inline", modo="full")
    assert resultado["counts"]["must"] == 0, [item["kind"] for item in resultado["findings"]]
    assert resultado["metrics"]["preset"] == "doc-inline"
    assert resultado["metrics"]["rampa"] == "standard"
    assert len(resultado["rows"]) == 6


def test_delivery_checks_the_accessible_svg() -> None:
    sem_nome = HTML_CLEAN.replace('role="img" aria-labelledby="fila-title fila-desc"', "")
    resultado = checar_entrega(html=sem_nome, preset="doc-inline", modo="full")
    assert {"sem-role", "sem-aria"} <= kinds(resultado)
    quebrado = HTML_CLEAN.replace('aria-labelledby="fila-title fila-desc"', 'aria-labelledby="x-title x-desc"')
    assert "aria-quebrado" in kinds(checar_entrega(html=quebrado, preset="doc-inline", modo="full"))
    geometria = HTML_CLEAN.replace(
        "Webhooks entram numa fila limitada",
        "Caixa à esquerda e retângulo acima",
    )
    assert "desc-geometria" in kinds(checar_entrega(html=geometria, preset="doc-inline", modo="full"))


def test_delivery_checks_the_preset_and_the_canvas() -> None:
    slide = checar_entrega(html=HTML_CLEAN, preset="slide-16x9", modo="full")
    assert {"viewbox-preset", "rampa-errada"} <= kinds(slide)
    sem_wrapper = checar_entrega(html=HTML_CLEAN.replace("overflow-x:auto", "overflow:hidden"), preset="doc-inline", modo="full")
    assert "sem-wrapper" in kinds(sem_wrapper)
    sem_print = checar_entrega(html=HTML_CLEAN.replace("@media print{.diagram-container{overflow-x:visible}svg{min-width:0}}", ""),
                               preset="doc-inline", modo="full")
    assert "print-sem-regra" in kinds(sem_print)


def test_delivery_rejects_external_images_and_uncontrolled_motion() -> None:
    resultado = checar_entrega(html=HTML_CLEAN.replace("</svg>", "</svg><img src='x.png'>"), preset="doc-inline", modo="full")
    assert "imagem-externa" in kinds(resultado)
    animado = HTML_CLEAN.replace("</svg>", "</svg><script>const a=1</script>")
    achados = kinds(checar_entrega(html=animado, preset="doc-inline", modo="full"))
    assert {"motion-sem-estatico", "sem-reduced-motion"} <= achados


def test_delivery_skips_the_min_width_for_fit() -> None:
    somente_svg = '<svg viewBox="0 0 960 600" role="img" aria-labelledby="t d"><title id="t">A</title><desc id="d">B</desc></svg>'
    justo = checar_entrega(html=somente_svg, preset="doc-inline", modo="full")
    assert "sem-min-width" in kinds(justo)
    derivado = checar_entrega(html=somente_svg, preset="fit", modo="full")
    assert "sem-min-width" not in kinds(derivado)
    assert "viewbox-preset" not in kinds(derivado)


def test_delivery_rejects_bad_input() -> None:
    with pytest.raises(EditorialError):
        checar_entrega(html=HTML_CLEAN, preset="a4", modo="full")
    with pytest.raises(EditorialError):
        checar_entrega(html="<div>sem svg, mas com texto suficiente para passar do mínimo exigido</div>",
                       preset="doc-inline", modo="full")


# ------------------------------------------------------------------------ API


def test_health_reports_the_new_version_and_skill_count(client: TestClient) -> None:
    health = client.get("/api/health").json()
    assert health["version"] == "0.60.0"
    assert health["skills"] == 288


def test_api_runs_every_editorial_skill(client: TestClient) -> None:
    tipo = client.post("/api/skills/editorial.tipo/execute", json={"parameters": {
        "pedido": PEDIDO_FILA, "plateia": "engenharia", "destino": "deck", "nos": 6,
    }}).json()
    assert tipo["ok"] is True
    assert tipo["result"]["padrao"] == "fila"

    marca = client.post("/api/skills/editorial.marca/execute", json={"parameters": {"marca": MARCA_CLEAN}}).json()
    assert marca["ok"] is True
    assert marca["result"]["metrics"]["falhas"] == 0

    lint = client.post("/api/skills/editorial.lint/execute", json={"parameters": {"html": HTML_CLEAN}}).json()
    assert lint["ok"] is True
    assert lint["result"]["counts"]["total"] == 0

    conector = client.post("/api/skills/editorial.conector/execute", json={"parameters": {
        "conectores": CONECTORES_CLEAN,
    }}).json()
    assert conector["ok"] is True
    assert conector["result"]["metrics"]["conectores"] == 3

    importar = client.post("/api/skills/editorial.importar/execute", json={"parameters": {
        "fonte": MERMAID_COM_FOLHAS, "formato": "mermaid", "detalhe": "simplified", "tamanho": "slide-16x9",
        "plateia": "executive",
    }}).json()
    assert importar["ok"] is True
    assert importar["result"]["ledger"]

    entrega = client.post("/api/skills/editorial.entrega/execute", json={"parameters": {
        "html": HTML_CLEAN, "preset": "doc-inline",
    }}).json()
    assert entrega["ok"] is True
    assert entrega["result"]["metrics"]["rampa"] == "standard"

    catalogo = client.post("/api/skills/editorial.catalogo/execute", json={"parameters": {}}).json()
    assert catalogo["ok"] is True
    assert len(catalogo["result"]["tipos"]) == 45


def test_api_is_read_only_and_rejects_bad_parameters(client: TestClient) -> None:
    lint = client.post("/api/skills/editorial.lint/execute", json={"parameters": {"html": HTML_CLEAN}}).json()
    assert lint["result"]["executed"] is False
    assert lint["result"]["readOnly"] is True

    desconhecido = client.post("/api/skills/editorial.conector/execute", json={"parameters": {"conectores": "{}"}})
    assert desconhecido.json()["ok"] is False

    marca_ruim = client.post("/api/skills/editorial.marca/execute", json={"parameters": {"marca": "ink=vermelho"}})
    assert marca_ruim.json()["ok"] is False

    modo_ruim = client.post("/api/skills/editorial.tipo/execute", json={"parameters": {
        "pedido": PEDIDO_FILA, "modo": "turbo",
    }})
    assert modo_ruim.json()["ok"] is False

    campo_extra = client.post("/api/skills/editorial.entrega/execute", json={"parameters": {
        "html": HTML_CLEAN, "preset": "doc-inline", "navegador": True,
    }})
    assert campo_extra.json()["ok"] is False


CICLO_COM_BANCO = """flowchart LR
  A[Cliente] --> B[Gateway]
  B --> C[Conta]
  C --> D[Carrinho]
  D --> E[Checkout]
  E --> F[Pedido]
  F --> G[Cobrança]
  G --> H[Fatura]
  H --> A
  H --> PG[(Postgres)]
"""


def test_import_never_cuts_a_data_store_to_fit() -> None:
    """Banco é essencial: se só sobra ele para cortar, o diagrama divide em vez de perder o dado."""
    resultado = planejar_importacao(fonte=CICLO_COM_BANCO, formato="mermaid", tamanho="doc-inline",
                                    detalhe="simplified", plateia="mixed", modo="full")
    assert resultado["metrics"]["origem_nos"] == 9
    assert resultado["ledger"] == []
    assert resultado["digest"]["dividir"] is True
    assert "acima-do-teto" in kinds(resultado)


def test_import_prefers_cross_cutting_infra_over_the_store() -> None:
    fonte = CICLO_COM_BANCO.replace("  H --> PG[(Postgres)]\n", "  H --> PG[(Postgres)]\n  H --> L[Log de acesso]\n")
    resultado = planejar_importacao(fonte=fonte, formato="mermaid", tamanho="doc-inline",
                                    detalhe="simplified", plateia="mixed", modo="full")
    assert [corte["corta"] for corte in resultado["ledger"]] == ["infraestrutura transversal"]
    assert resultado["digest"]["dividir"] is True
