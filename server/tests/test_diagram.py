"""Testes dos diagramas inspirados em tt-a1i/archify (MIT, 2026).

Tudo é estático: nenhum CLI `archify.mjs`, `archify.zip`, plugin de agente,
template de 786 KB, captura de Chrome ou renderer do upstream é instalado,
baixado ou executado. As fixtures declaram o IR em JSON puro.
"""
from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from server.app import create_app
from server.diagram import (
    FORMATS,
    MAX_NODES,
    PRESETS,
    TYPES,
    VARIANTS,
    DiagramError,
    _skeleton,
    build,
    build_from_text,
    diagram_delivery,
    diagram_layout,
    diagram_legend,
    diagram_library,
    diagram_render,
    diagram_spec,
    diagram_type,
    legend_entries,
    render,
)
from server.skill_registry import build_registry

ARCH = {
    "tipo": "arquitetura",
    "titulo": "Plataforma de pagamentos",
    "subtitulo": "Do navegador ao razão, com uma fronteira de confiança.",
    "saida": "pagamentos.html",
    "componentes": [
        {"id": "app", "rotulo": "Aplicativo", "tipo": "frontend", "subrotulo": "checkout"},
        {"id": "api", "rotulo": "API", "tipo": "backend", "subrotulo": "regras"},
        {"id": "db", "rotulo": "Razão", "tipo": "database", "subrotulo": "fonte da verdade"},
    ],
    "conexoes": [
        {"de": "app", "para": "api", "rotulo": "HTTPS"},
        {"de": "api", "para": "db", "rotulo": "SQL"},
    ],
    "fronteiras": [{"id": "interno", "rotulo": "Rede interna", "membros": ["api", "db"]}],
    "cartoes": [{"cor": "cyan", "titulo": "Contrato", "itens": ["Toda chamada usa HTTPS."]}],
}

TREE = {
    "tipo": "arvore",
    "titulo": "Módulos do produto",
    "nos": [
        {"id": "raiz", "rotulo": "Produto"},
        {"id": "conta", "rotulo": "Conta", "pai": "raiz"},
        {"id": "cobranca", "rotulo": "Cobrança", "pai": "raiz"},
        {"id": "fatura", "rotulo": "Fatura", "pai": "cobranca"},
    ],
}

SEQUENCE = {
    "tipo": "sequencia",
    "titulo": "Requisição com cache miss",
    "participantes": [
        {"id": "app", "rotulo": "Aplicativo", "tipo": "frontend"},
        {"id": "api", "rotulo": "API", "tipo": "backend"},
        {"id": "db", "rotulo": "Banco", "tipo": "database"},
    ],
    "mensagens": [
        {"de": "app", "para": "api", "rotulo": "GET /pedido"},
        {"de": "api", "para": "db", "rotulo": "SELECT"},
        {"de": "db", "para": "api", "rotulo": "linhas", "variante": "dashed"},
        {"de": "api", "para": "app", "rotulo": "200 OK", "variante": "dashed"},
    ],
}

WATERFALL = {
    "tipo": "cascata",
    "titulo": "Checkout lento",
    "subtitulo": "Tempos ilustrativos de um pedido real.",
    "unidade": "ms",
    "trechos": [
        {"id": "req", "nome": "POST /checkout", "inicio": 0, "fim": 1200},
        {"id": "db", "nome": "consulta", "inicio": 100, "fim": 420, "pai": "req"},
        {"id": "pgto", "nome": "cobrança", "inicio": 430, "fim": 1100, "pai": "req"},
    ],
}

TIMELINE = {
    "tipo": "linha do tempo",
    "titulo": "Incidente de cobrança",
    "raias": [{"id": "produto", "rotulo": "Produto"}, {"id": "resposta", "rotulo": "Resposta"}],
    "eventos": [
        {"id": "deploy", "quando": "2026-10-01T10:00:00-03:00", "titulo": "Deploy v2.4", "raia": "produto", "tipo": "change"},
        {"id": "erro", "quando": "2026-10-01T10:14:00-03:00", "titulo": "Cobrança em dobro", "raia": "produto", "tipo": "alert"},
        {"id": "rollback", "quando": "2026-10-01T10:21:00-03:00", "titulo": "Rollback", "raia": "resposta", "tipo": "recovery"},
    ],
}

UPSTREAM = {
    "schema_version": 1,
    "diagram_type": "workflow",
    "meta": {"title": "Agent Tool Call", "output": "agent.html", "animation": "trace", "quality_profile": "showcase"},
    "lanes": [{"id": "ui", "label": "Interface"}, {"id": "agent", "label": "Agente"}],
    "nodes": [
        {"id": "user", "lane": "ui", "col": 0, "type": "external", "label": "User"},
        {"id": "chat", "lane": "ui", "col": 1, "type": "frontend", "label": "Chat"},
        {"id": "loop", "lane": "agent", "col": 2, "type": "backend", "label": "Loop"},
    ],
    "edges": [
        {"id": "e1", "from": "user", "to": "chat"},
        {"id": "e2", "from": "chat", "to": "loop", "label": "tool call"},
    ],
    "cards": [{"dot": "cyan", "title": "Contrato", "items": ["Lanes posicionam os nós."]}],
}


def spec_of(raw: dict) -> object:
    return build(json.loads(json.dumps(raw)))


def codes(findings: list[dict]) -> list[str]:
    return [item["kind"] for item in findings]


# ------------------------------------------------------------------ roteador

@pytest.mark.parametrize(
    "pedido,esperado",
    [
        ("arquitetura do sistema de pagamentos com fronteira de confiança", "architecture"),
        ("fluxo de aprovação de compras com reprovação", "workflow"),
        ("sequência de chamadas do login com ida e volta", "sequence"),
        ("pipeline de dados com linhagem e eventos", "dataflow"),
        ("ciclo de vida do pedido com estados e retentativa", "lifecycle"),
        ("esquema de tabelas com chave estrangeira e cardinalidade", "erd"),
        ("estrutura de pastas do repositório", "tree"),
        ("classes com herança e interface", "class"),
        ("linha do tempo do incidente de ontem", "timeline"),
        ("onde o tempo foi num checkout lento", "waterfall"),
    ],
)
def test_router_escolhe_o_tipo(pedido: str, esperado: str) -> None:
    result = diagram_type(pedido=pedido)
    assert result["tipo"] == esperado
    assert result["esqueleto"]["tipo"] == esperado


def test_router_devolve_dez_candidatos_e_esqueleto_valido() -> None:
    result = diagram_type(pedido="fluxo de aprovação de compras")
    assert len(result["candidatos"]) == 5
    assert len(result["rows"]) == 10
    assert result["esquema"]["no"]
    validated = diagram_spec(especificacao=json.dumps(result["esqueleto"], ensure_ascii=False))
    assert validated["counts"]["must"] == 0


def test_router_avisa_pedido_sem_sinal() -> None:
    result = diagram_type(pedido="quero explicar uma coisa qualquer")
    assert "sem-sinal" in codes(result["findings"])
    assert result["metrics"]["pontuacao"] == 0


def test_router_avisa_ambiguidade_e_desempata() -> None:
    result = diagram_type(pedido="estrutura de pastas do repositório")
    assert result["tipo"] == "tree"
    assert "ambiguidade" in codes(result["findings"]) or result["metrics"]["candidatos"] == 1


def test_router_recusa_pedido_curto() -> None:
    with pytest.raises(DiagramError):
        diagram_type(pedido="oi")


def test_router_detalhe_invalido_vira_aviso() -> None:
    result = diagram_type(pedido="arquitetura do sistema", detalhe="profundo")
    assert "detalhe" in codes(result["findings"])


# ---------------------------------------------------------------- validação

def test_especificacao_valida_conta_tudo() -> None:
    result = diagram_spec(especificacao=json.dumps(ARCH, ensure_ascii=False))
    assert result["counts"]["must"] == 0
    assert result["contagens"] == {"nos": 3, "arestas": 2, "regioes": 1, "cartoes": 1, "avisos": 1}
    assert result["normalizado"]["tipo"] == "architecture"
    assert result["executed"] is False and result["readOnly"] is True


def test_titulo_ausente_bloqueia() -> None:
    raw = {"tipo": "arquitetura", "componentes": [{"id": "a", "rotulo": "A"}]}
    result = diagram_spec(especificacao=json.dumps(raw))
    assert "sem-titulo" in codes(result["findings"])


def test_id_duplicado_bloqueia() -> None:
    raw = dict(ARCH)
    raw["componentes"] = [{"id": "a", "rotulo": "A"}, {"id": "a", "rotulo": "B"}]
    result = diagram_spec(especificacao=json.dumps(raw))
    assert "id-duplicado" in codes(result["findings"])


def test_aresta_orfa_bloqueia() -> None:
    raw = dict(ARCH)
    raw["conexoes"] = [{"de": "app", "para": "fantasma"}]
    result = diagram_spec(especificacao=json.dumps(raw))
    assert "aresta-orfa" in codes(result["findings"])


def test_tipo_desconhecido_levanta_erro() -> None:
    with pytest.raises(DiagramError):
        diagram_spec(especificacao='{"tipo": "gantt", "titulo": "x"}')


def test_json_invalido_levanta_erro_com_linha() -> None:
    with pytest.raises(DiagramError) as exc:
        build_from_text('{"tipo": "arquitetura",}')
    assert "linha" in str(exc.value)


def test_cerca_de_codigo_e_aceita() -> None:
    fenced = "```json\n" + json.dumps(ARCH, ensure_ascii=False) + "\n```"
    assert diagram_spec(especificacao=fenced)["tipo"] == "architecture"


def test_arvore_sem_raiz_bloqueia() -> None:
    raw = {"tipo": "arvore", "titulo": "x", "nos": [
        {"id": "a", "rotulo": "A", "pai": "b"},
        {"id": "b", "rotulo": "B", "pai": "a"},
    ]}
    result = diagram_spec(especificacao=json.dumps(raw))
    assert "ciclo" in codes(result["findings"]) or "sem-raiz" in codes(result["findings"])


def test_arvore_com_pai_inexistente_bloqueia() -> None:
    raw = {"tipo": "arvore", "titulo": "x", "nos": [
        {"id": "a", "rotulo": "A"},
        {"id": "b", "rotulo": "B", "pai": "z"},
    ]}
    assert "pai-ausente" in codes(diagram_spec(especificacao=json.dumps(raw))["findings"])


def test_ciclo_de_vida_com_caminho_invalido() -> None:
    raw = dict(SEQUENCE)
    raw = {"tipo": "lifecycle", "titulo": "x", "caminhoPrincipal": ["a", "z"], "estados": [
        {"id": "a", "rotulo": "A", "tipo": "start"},
        {"id": "b", "rotulo": "B", "tipo": "success"},
    ], "transicoes": [{"de": "a", "para": "b"}]}
    assert "caminho-invalido" in codes(diagram_spec(especificacao=json.dumps(raw))["findings"])


def test_cascata_invertida_bloqueia() -> None:
    raw = dict(WATERFALL)
    raw["trechos"] = [{"id": "a", "nome": "A", "inicio": 500, "fim": 100}]
    assert "trecho-invertido" in codes(diagram_spec(especificacao=json.dumps(raw))["findings"])


def test_linha_do_tempo_descarta_data_invalida() -> None:
    raw = dict(TIMELINE)
    raw["eventos"] = [
        {"id": "ok", "quando": "2026-10-01T10:00:00-03:00", "titulo": "Vale"},
        {"id": "ruim", "quando": "ontem à tarde", "titulo": "Não vale"},
    ]
    result = diagram_spec(especificacao=json.dumps(raw))
    assert "data-invalida" in codes(result["findings"])
    assert result["contagens"]["nos"] == 1


def test_rotulo_fundo_e_bloqueado_no_limite_duro() -> None:
    raw = dict(ARCH)
    raw["componentes"] = [{"id": "a", "rotulo": "x" * 60}]
    raw["conexoes"] = []
    result = diagram_spec(especificacao=json.dumps(raw))
    assert "rotulo-limite" in codes(result["findings"])


def test_acima_do_teto_de_nos_bloqueia() -> None:
    raw = {"tipo": "arquitetura", "titulo": "x", "componentes": [
        {"id": f"c{index}", "rotulo": f"C{index}"} for index in range(MAX_NODES + 1)
    ]}
    assert "nos-demais" in codes(diagram_spec(especificacao=json.dumps(raw))["findings"])


def test_saida_sem_html_bloqueia() -> None:
    raw = dict(ARCH)
    raw["saida"] = "pagamentos.pdf"
    assert "saida-nao-html" in codes(diagram_spec(especificacao=json.dumps(raw))["findings"])


def test_cartoes_acima_do_teto_viram_aviso() -> None:
    raw = dict(ARCH)
    raw["cartoes"] = [{"cor": "cyan", "titulo": f"C{index}", "itens": ["x"]} for index in range(6)]
    assert "cartoes-demais" in codes(diagram_spec(especificacao=json.dumps(raw))["findings"])


def test_ir_do_upstream_e_convertido() -> None:
    spec = spec_of(UPSTREAM)
    assert spec.kind == "workflow"
    assert spec.title == "Agent Tool Call"
    assert len(spec.nodes) == 3
    assert spec.quality == "vitrine"
    assert any("archify" in note for note in spec.notes)


def test_ir_pt_br_com_acentos_no_tipo() -> None:
    raw = dict(SEQUENCE)
    raw["tipo"] = "sequência"
    assert spec_of(raw).kind == "sequence"


# ------------------------------------------------------------------- layout

def test_layout_coloca_tudo_dentro_do_canvas() -> None:
    spec = spec_of(ARCH)
    assert spec.width >= 320 and spec.height >= 240
    for node in spec.nodes:
        assert 0 <= node.x and node.x + node.w <= spec.width
        assert 0 <= node.y and node.y + node.h <= spec.height


def test_layout_e_deterministico() -> None:
    first, second = spec_of(ARCH), spec_of(ARCH)
    assert [(n.id, n.x, n.y) for n in first.nodes] == [(n.id, n.x, n.y) for n in second.nodes]


def test_layout_de_arvore_tem_um_pai_por_no() -> None:
    spec = spec_of(TREE)
    parents = [node.parent for node in spec.nodes if node.parent]
    assert len(parents) == len(set(node.id for node in spec.nodes)) - 1


def test_layout_mede_cruzamento_em_grafo_ruim() -> None:
    raw = {
        "tipo": "arquitetura", "titulo": "Cruzado",
        "componentes": [
            {"id": "b", "rotulo": "B", "faixa": 0, "coluna": 1},
            {"id": "a", "rotulo": "A", "faixa": 2, "coluna": 0},
            {"id": "c", "rotulo": "C", "faixa": 2, "coluna": 2},
            {"id": "d", "rotulo": "D", "faixa": 3, "coluna": 1},
        ],
        "conexoes": [
            {"de": "a", "para": "c", "rotulo": "vai"},
            {"de": "b", "para": "d", "rotulo": "volta"},
        ],
    }
    result = diagram_layout(especificacao=json.dumps(raw))
    assert result["metricas"]["cruzamentos"] >= 1
    assert "cruzamento" in codes(result["findings"])


def test_layout_avisa_folga_de_rotulo() -> None:
    raw = {
        "tipo": "erd", "titulo": "Chaves",
        "entidades": [
            {"id": "a", "rotulo": "a", "linha": 0, "coluna": 0},
            {"id": "b", "rotulo": "b", "linha": 0, "coluna": 1},
        ],
        "relacionamentos": [{"de": "a", "para": "b", "rotulo": "uma relação com nome longo demais"}],
    }
    result = diagram_layout(especificacao=json.dumps(raw))
    assert result["metricas"]["rotulosApertados"] >= 1


def test_layout_de_sequencia_tem_canais() -> None:
    spec = spec_of(SEQUENCE)
    assert spec.width >= 1000
    assert spec.layout["axis"]["bottom"] > spec.layout["axis"]["top"]


def test_layout_de_cascata_escala_barras() -> None:
    spec = spec_of(WATERFALL)
    assert spec.layout["scale"]["max"] == 1200
    widths = {node.id: node.w for node in spec.nodes}
    assert widths["req"] > widths["pgto"] > widths["db"]


# ------------------------------------------------------------------ desenho

@pytest.mark.parametrize("tipo", list(TYPES))
def test_desenho_de_todos_os_tipos(tipo: str) -> None:
    result = diagram_render(especificacao=json.dumps(_skeleton(tipo), ensure_ascii=False), formato="html")
    assert result["formato"] == "html"
    assert result["conteudo"].startswith("<!DOCTYPE html>")
    assert "<svg" in result["conteudo"]
    assert "http" not in result["conteudo"].replace("http://www.w3.org/2000/svg", "")


def test_html_escapa_rotulo() -> None:
    raw = dict(ARCH)
    raw["componentes"] = [{"id": "a", "rotulo": "<script>alert(1)</script>", "tipo": "backend"}]
    raw["conexoes"] = []
    html = render(spec_of(raw), "html")
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html


def test_svg_e_xml_autocontido() -> None:
    svg = render(spec_of(ARCH), "svg")
    assert svg.startswith('<?xml version="1.0"')
    assert svg.count("<svg") == 1 and svg.rstrip().endswith("</svg>")


def test_mermaid_por_tipo() -> None:
    assert render(spec_of(ARCH), "mermaid").startswith("flowchart")
    assert render(spec_of(SEQUENCE), "mermaid").startswith("sequenceDiagram")
    assert render(spec_of(TREE), "mermaid").startswith("flowchart TD")
    lifecycle = build(_skeleton("lifecycle"))
    assert render(lifecycle, "mermaid").startswith("stateDiagram-v2")
    waterfall = render(spec_of(WATERFALL), "mermaid")
    assert waterfall.startswith("gantt") and "dateFormat" in waterfall


def test_texto_e_dot() -> None:
    assert "RAZÃO" in render(spec_of(ARCH), "ascii").upper()
    dot = render(spec_of(ARCH), "dot")
    assert dot.startswith("digraph") and "->" in dot


def test_formato_invalido_levanta_erro() -> None:
    with pytest.raises(DiagramError):
        diagram_render(especificacao=json.dumps(ARCH), formato="pdf")


def test_preview_corta_conteudo_longo() -> None:
    result = diagram_render(especificacao=json.dumps(_skeleton("class")), formato="html")
    assert "corte de prévia" in result["markdown"]
    assert len(result["conteudo"]) > 4_000
    assert result["bytes"] == len(result["conteudo"].encode("utf-8"))


def test_todos_os_formatos_tem_rotulo() -> None:
    assert set(FORMATS) == {"html", "svg", "mermaid", "ascii", "dot"}


# -------------------------------------------------------- legenda e contrato

def test_legenda_automatica_lista_so_o_usado() -> None:
    entries = legend_entries(spec_of(SEQUENCE))
    assert [entry["variante"] for entry in entries] == ["default", "dashed"]


def test_legenda_oculta_gera_aviso() -> None:
    raw = dict(SEQUENCE)
    raw["legenda"] = "oculta"
    result = diagram_legend(especificacao=json.dumps(raw, ensure_ascii=False))
    assert "legenda-oculta" in codes(result["findings"])


def test_legenda_transparente_sobre_presets() -> None:
    result = diagram_legend(tipo="erd")
    assert len(result["presets"]) == len(PRESETS)
    for preset in result["presets"]:
        assert float(preset["contraste"].split(":")[0]) >= 7


def test_preset_desconhecido_bloqueia() -> None:
    result = diagram_legend(tipo="erd", preset="neon")
    assert "preset-desconhecido" in codes(result["findings"])


def test_variantes_cobrem_as_seis_relacoes_uml() -> None:
    assert {"dependency", "association", "inheritance", "realization", "composition", "aggregation"} <= set(VARIANTS)


def test_entrega_roda_os_gates_em_ordem() -> None:
    result = diagram_delivery(especificacao=json.dumps(ARCH, ensure_ascii=False))
    assert [gate["gate"] for gate in result["gates"]] == [
        "validar", "entregar", "checar", "navegador", "revisao-visual",
    ]
    assert result["gates"][0]["status"] == "passou"
    assert result["gates"][3]["status"] == "nao-executado"
    assert result["visualReview"] == "not-requested"
    assert result["parouEm"] == ""


def test_entrega_para_no_primeiro_gate_falho() -> None:
    raw = {"tipo": "arquitetura", "titulo": "", "componentes": []}
    result = diagram_delivery(especificacao=json.dumps(raw))
    assert result["parouEm"] == "validar"
    assert result["gates"][1]["status"] == "falhou"
    assert result["gates"][1]["evidencia"].startswith("Não renderizado")


def test_entrega_com_revisao_pedida_e_captura() -> None:
    result = diagram_delivery(
        especificacao=json.dumps(ARCH, ensure_ascii=False), checagem_visual="pedida", captura="sim"
    )
    assert result["visualReview"] == "requested"
    assert any(gate["gate"] == "captura" for gate in result["gates"])


def test_entrega_sem_captura_nao_promete_captura() -> None:
    result = diagram_delivery(especificacao=json.dumps(ARCH, ensure_ascii=False))
    assert "captura" not in [gate["gate"] for gate in result["gates"]]
    assert any("captura" in item.lower() for item in result["limitations"])


# ---------------------------------------------------------------- biblioteca

def test_biblioteca_tem_os_dez_tipos() -> None:
    result = diagram_library()
    assert len(result["tipos"]) == 10
    assert result["metrics"] == {"tipos": 10, "nos": 7, "presets": 4, "formatos": 5}
    assert len(result["variantes"]) == len(VARIANTS)


def test_biblioteca_declara_limites() -> None:
    limits = diagram_library()["limites"]
    assert limits["nos"] == MAX_NODES
    assert limits["cartoes"] == 4


# ---------------------------------------------------------------------- API

def test_api_executa_skills_de_diagrama() -> None:
    client = TestClient(create_app())
    skills = client.get("/api/skills").json()["skills"]
    assert {"diagram.type", "diagram.spec", "diagram.layout", "diagram.render", "diagram.legend", "diagram.delivery", "diagram.library"} <= {
        skill["id"] for skill in skills
    }
    response = client.post("/api/skills/diagram.type/execute", json={"parameters": {"pedido": "fluxo de aprovação de compras"}})
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["result"]["tipo"] == "workflow"
    assert body["result"]["executed"] is False


def test_api_devolve_erro_legivel() -> None:
    client = TestClient(create_app())
    response = client.post("/api/skills/diagram.spec/execute", json={"parameters": {"especificacao": "nope"}})
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is False
    assert "JSON inválido" in body["error"]["message"]


def test_api_valida_parametros() -> None:
    client = TestClient(create_app())
    response = client.post("/api/skills/diagram.render/execute", json={"parameters": {"especificacao": "{}", "formato": "pdf"}})
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is False and body["error"]["code"] == "SKILL_ERROR"
    assert "formato" in body["error"]["message"].lower()
    assert client.post("/api/skills/diagram.render/execute", json={"parameters": "x"}).status_code == 422


def test_registro_tem_cento_e_vinte_e_sete_skills() -> None:
    registry = build_registry(__import__("pathlib").Path("."))
    assert len(registry.list()) == 176
