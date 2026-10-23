"""Diagramas como código, inspirados em tt-a1i/archify (MIT, 2026).

Implementação própria e determinística. Nenhum CLI, renderer, template de
786 KB, captura de Chrome, plugin de agente ou pacote do upstream é instalado
ou executado. As skills leem uma especificação JSON declarada — ou um pedido em
texto — e devolvem: o tipo certo com justificativa, o esqueleto, os achados
estruturais, um HTML autocontido com SVG, e a exportação Mermaid/ASCII/DOT.

O recorte é o que sobrevive sem navegador: o roteador de tipos, a validação do
IR, as regras medidas de layout, o desenho determinístico e os gates estáticos.
"""
from __future__ import annotations

import html
import json
import math
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from .review import common, finalize, finding
from .studio import contrast_ratio

MAX_SPEC_CHARS = 200_000
MAX_NODES = 40
MAX_EDGES = 120
MAX_CARDS = 4
MAX_LABEL = 44
WARN_LABEL = 28
WARN_SUBLABEL = 44
MAX_EDGE_LABEL = 28


class DiagramError(ValueError):
    """Erro esperado de diagrama, seguro para o usuário."""


# ---------------------------------------------------------------- vocabulário

NODE_TYPES: dict[str, tuple[str, str]] = {
    "frontend": ("Interface", "#38bdf8"),
    "backend": ("Serviço", "#4ade80"),
    "database": ("Banco", "#fbbf24"),
    "cloud": ("Nuvem", "#a78bfa"),
    "security": ("Segurança", "#fb7185"),
    "messagebus": ("Mensageria", "#fb923c"),
    "external": ("Externo", "#94a3b8"),
}
NODE_ALIASES = {
    "ui": "frontend", "web": "frontend", "cliente": "frontend", "app": "frontend",
    "api": "backend", "servico": "backend", "serviço": "backend", "servidor": "backend",
    "db": "database", "banco": "database", "store": "database", "armazenamento": "database",
    "infra": "cloud", "nuvem": "cloud", "cloud": "cloud",
    "auth": "security", "seguranca": "security", "segurança": "security", "gateway": "security",
    "fila": "messagebus", "queue": "messagebus", "bus": "messagebus", "evento": "messagebus",
    "externo": "external", "external": "external", "ator": "external", "usuario": "external",
    "usuário": "external", "pessoa": "external",
}
for _key in NODE_TYPES:
    NODE_ALIASES.setdefault(_key, _key)

LIFECYCLE_TYPES: dict[str, tuple[str, str]] = {
    "start": ("Início", "#94a3b8"),
    "active": ("Ativo", "#38bdf8"),
    "waiting": ("Espera", "#fbbf24"),
    "decision": ("Decisão", "#a78bfa"),
    "success": ("Sucesso", "#4ade80"),
    "failure": ("Falha", "#fb7185"),
    "neutral": ("Neutro", "#cbd5e1"),
    "external": ("Externo", "#94a3b8"),
}
LIFECYCLE_ALIASES = {
    "inicio": "start", "início": "start", "comeco": "start", "começo": "start",
    "ativo": "active", "andamento": "active", "processando": "active",
    "espera": "waiting", "aguardando": "waiting", "pendente": "waiting",
    "decisao": "decision", "decisão": "decision", "escolha": "decision",
    "sucesso": "success", "concluido": "success", "concluído": "success", "ok": "success",
    "falha": "failure", "erro": "failure", "cancelado": "failure",
    "neutro": "neutral", "externo": "external",
}
for _key in LIFECYCLE_TYPES:
    LIFECYCLE_ALIASES.setdefault(_key, _key)

CLASS_KINDS = {
    "class": ("Classe", "#38bdf8"),
    "abstract": ("Abstrata", "#a78bfa"),
    "interface": ("Interface", "#22d3ee"),
    "enum": ("Enum", "#fbbf24"),
    "record": ("Registro", "#4ade80"),
}
REL_KINDS = {
    "dependency": ("Dependência", "tracejada", "#94a3b8"),
    "association": ("Associação", "linha", "#cbd5e1"),
    "inheritance": ("Herança", "triângulo vazio", "#a78bfa"),
    "realization": ("Realização", "triângulo vazio tracejado", "#22d3ee"),
    "composition": ("Composição", "losango cheio", "#fb7185"),
    "aggregation": ("Agregação", "losango vazio", "#fb923c"),
}
TIMELINE_KINDS = {
    "default": ("Evento", "#94a3b8"),
    "change": ("Mudança", "#38bdf8"),
    "alert": ("Alerta", "#fb7185"),
    "action": ("Ação", "#fbbf24"),
    "recovery": ("Recuperação", "#4ade80"),
}
WATERFALL_STATUS = {
    "ok": ("OK", "#4ade80"),
    "error": ("Erro", "#fb7185"),
    "cancelled": ("Cancelado", "#fbbf24"),
    "incomplete": ("Incompleto", "#94a3b8"),
}

TYPES: dict[str, dict[str, Any]] = {
    "architecture": {
        "label": "Arquitetura", "use": "componentes, serviços, fronteiras de confiança e implantação",
        "arrays": ("components",), "optional": ("boundaries", "connections"),
        "node_kind": "componente", "budget": 24, "row_label": "faixa",
    },
    "workflow": {
        "label": "Fluxo de trabalho", "use": "processos, aprovações, runbooks, chamadas de ferramenta",
        "arrays": ("lanes", "nodes", "edges"), "optional": ("phases", "groups", "mainPath", "cards"),
        "node_kind": "etapa", "budget": 20, "row_label": "raia",
    },
    "sequence": {
        "label": "Sequência", "use": "cadeia de chamadas, ciclo de requisição, ida e volta",
        "arrays": ("participants", "messages"), "optional": ("segments", "activations", "cards"),
        "node_kind": "participante", "budget": 8, "row_label": "participante",
    },
    "dataflow": {
        "label": "Fluxo de dados", "use": "pipeline, ETL/ELT, linhagem, eventos e consumo",
        "arrays": ("stages", "nodes", "flows"), "optional": ("cards",),
        "node_kind": "nó", "budget": 22, "row_label": "estágio",
    },
    "lifecycle": {
        "label": "Ciclo de vida", "use": "estados, transições, retentativas e estados terminais",
        "arrays": ("states", "transitions"), "optional": ("mainPath", "cards"),
        "node_kind": "estado", "budget": 14, "row_label": "linha",
    },
    "erd": {
        "label": "Entidades", "use": "tabelas, atributos, chaves e cardinalidade",
        "arrays": ("entities",), "optional": ("relationships", "cards"),
        "node_kind": "entidade", "budget": 9, "row_label": "linha",
    },
    "tree": {
        "label": "Árvore", "use": "hierarquia de um pai só: repositório, módulos, capacidades",
        "arrays": ("nodes",), "optional": ("cards",),
        "node_kind": "nó", "budget": 40, "row_label": "nível",
    },
    "class": {
        "label": "Tipos", "use": "classes, interfaces, membros e relações entre tipos",
        "arrays": ("types",), "optional": ("relationships", "cards"),
        "node_kind": "tipo", "budget": 9, "row_label": "linha",
    },
    "timeline": {
        "label": "Linha do tempo", "use": "incidentes, releases e eventos datados num relógio",
        "arrays": ("events",), "optional": ("lanes", "cards"),
        "node_kind": "evento", "budget": 22, "row_label": "raia",
    },
    "waterfall": {
        "label": "Cascata", "use": "onde o tempo foi: durações, sobreposição e aninhamento",
        "arrays": ("spans",), "optional": ("cards",),
        "node_kind": "trecho", "budget": 16, "row_label": "linha",
    },
}
TYPE_ALIASES = {
    "arquitetura": "architecture", "architecture": "architecture", "sistema": "architecture",
    "fluxo": "workflow", "workflow": "workflow", "processo": "workflow", "etapas": "workflow",
    "sequencia": "sequence", "sequência": "sequence", "sequence": "sequence", "chamadas": "sequence",
    "dados": "dataflow", "dataflow": "dataflow", "linhagem": "dataflow", "pipeline": "dataflow",
    "estado": "lifecycle", "lifecycle": "lifecycle", "ciclo": "lifecycle",
    "erd": "erd", "entidades": "erd", "tabelas": "erd", "esquema": "erd",
    "arvore": "tree", "árvore": "tree", "tree": "tree", "hierarquia": "tree",
    "classe": "class", "classes": "class", "class": "class", "tipos": "class",
    "timeline": "timeline", "linha do tempo": "timeline", "historico": "timeline", "histórico": "timeline",
    "waterfall": "waterfall", "cascata": "waterfall", "tempo": "waterfall", "duracao": "waterfall",
}
for _key in TYPES:
    TYPE_ALIASES.setdefault(_key, _key)

SCOPE_ALIASES = {
    "sistema": "architecture", "componentes": "architecture", "infra": "architecture",
    "processo": "workflow", "passos": "workflow", "aprovacao": "workflow", "aprovação": "workflow",
    "troca": "sequence", "mensagens": "sequence", "api": "sequence",
    "dados": "dataflow", "pipeline": "dataflow", "eventos": "dataflow",
    "estado": "lifecycle", "status": "lifecycle", "transicoes": "lifecycle", "transições": "lifecycle",
    "tabelas": "erd", "banco": "erd", "esquema": "erd",
    "estrutura": "tree", "pastas": "tree", "modulos": "tree", "módulos": "tree",
    "tipos": "class", "heranca": "class", "herança": "class",
    "quando": "timeline", "incidente": "timeline", "historico": "timeline",
    "duracao": "waterfall", "latencia": "waterfall", "latência": "waterfall",
}

PLAN_SIGNALS: dict[str, tuple[str, ...]] = {
    "architecture": ("sistema", "servico", "serviços", "componente", "infraestrutura", "deploy", "implantacao", "implantação", "modulo", "módulo", "repositorio", "repositório", "fronteira", "monolito", "microsservico", "microsserviço"),
    "workflow": ("processo", "etapa", "passo", "aprovacao", "aprovação", "runbook", "procedimento", "checklist", "aprovador", "tramitacao", "tramitação", "solicitacao", "solicitação"),
    "sequence": ("chamada", "requisicao", "requisição", "request", "resposta", "troca", "mensagem", "protocolo", "ida e volta", "timeout", "retorno", "handshake"),
    "dataflow": ("dados", "pipeline", "etl", "linhagem", "evento", "stream", "ingestao", "ingestão", "consumo", "analytics", "warehouse", "tabela fato"),
    "lifecycle": ("estado", "status", "transicao", "transição", "ciclo de vida", "retentativa", "retry", "terminal", "fila", "aprovado", "reprovado"),
    "erd": ("tabela", "coluna", "chave estrangeira", "chave primaria", "chave primária", "cardinalidade", "esquema", "banco relacional", "entidade", "relacionamento"),
    "tree": ("arvore", "árvore", "hierarquia", "decomposicao", "decomposição", "organograma", "pastas", "diretorio", "diretório", "submodulo", "submódulo"),
    "class": ("classe", "interface", "heranca", "herança", "polimorfismo", "poo", "tipo abstrato", "implementa", "composicao", "composição"),
    "timeline": ("quando", "historico", "histórico", "incidente", "linha do tempo", "data", "hora", "release", "postmortem", "cronologia"),
    "waterfall": ("duracao", "duração", "latencia", "latência", "tempo gasto", "onde o tempo", "tempo foi", "span", "gargalo", "demora", "lento", "lentidao", "lentidão", "sobreposicao", "sobreposição", "milissegundos", "ms"),
}
for _key, _meta in TYPES.items():
    PLAN_SIGNALS.setdefault(_key, ())

ARRAY_ALIASES = {
    "components": ("components", "componentes", "nodes", "nos", "nós"),
    "connections": ("connections", "conexoes", "conexões", "edges", "arestas", "flows", "fluxos"),
}


def _norm(value: Any) -> str:
    """Minúsculas sem acento, para comparar termos do pedido e do esquema."""
    text = unicodedata.normalize("NFKD", _text(value))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return " ".join(text.lower().split())


def _mode(mode: str) -> None:
    if mode not in {"lite", "full", "ultra"}:
        raise DiagramError("Nível inválido: use lite, full ou ultra.")


def _text(value: Any) -> str:
    return "" if value is None else str(value)


def _squash(value: Any) -> str:
    return " ".join(_text(value).split())


def _label(value: Any) -> str:
    return _squash(value)


def _kind_of(raw: str, aliases: dict[str, str], fallback: str) -> str:
    return aliases.get(_norm(raw), fallback)


# ------------------------------------------------------------------- modelo

@dataclass
class Node:
    id: str
    label: str
    sublabel: str = ""
    kind: str = "backend"
    tag: str = ""
    row: int = 0
    col: int = 0
    parent: str = ""
    members: list[str] = field(default_factory=list)
    at: str = ""
    start: float = 0.0
    end: float = 0.0
    x: float = 0.0
    y: float = 0.0
    w: float = 120.0
    h: float = 54.0
    color: str = "#94a3b8"
    depth: int = 0


@dataclass
class Link:
    src: str
    dst: str
    label: str = ""
    variant: str = "default"
    points: list[tuple[float, float]] = field(default_factory=list)
    marked: bool = True


@dataclass
class Region:
    id: str
    label: str
    kind: str = "lane"
    row: int = 0
    col: int = 0
    members: list[str] = field(default_factory=list)
    x: float = 0.0
    y: float = 0.0
    w: float = 0.0
    h: float = 0.0


@dataclass
class Card:
    dot: str
    title: str
    items: list[str] = field(default_factory=list)


@dataclass
class Spec:
    kind: str
    title: str = ""
    subtitle: str = ""
    output: str = ""
    locale: str = "pt-BR"
    animation: str = "traco"
    preset: str = "classico"
    quality: str = "padrao"
    legend: str = "auto"
    evidence: str = ""
    unit: str = "ms"
    direction: str = "baixo"
    nodes: list[Node] = field(default_factory=list)
    links: list[Link] = field(default_factory=list)
    regions: list[Region] = field(default_factory=list)
    cards: list[Card] = field(default_factory=list)
    issues: list[dict[str, str]] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    layout: dict[str, Any] = field(default_factory=dict)
    width: float = 0.0
    height: float = 0.0

    def node(self, node_id: str) -> Node | None:
        return next((node for node in self.nodes if node.id == node_id), None)


def _issue(
    spec: Spec,
    group: str,
    kind: str,
    title: str,
    location: str,
    what: str,
    problem: str,
    fix: str,
    if_skipped: str,
) -> None:
    spec.issues.append(
        {
            "group": group,
            "kind": kind,
            "title": title,
            "location": location,
            "what": what,
            "problem": problem,
            "fix": fix,
            "ifSkipped": if_skipped,
        }
    )


def _to_finding(item: dict[str, str]) -> dict[str, Any]:
    return finding(
        item["group"], item["kind"], item["title"], item["location"],
        item["what"], item["problem"], item["fix"], item["ifSkipped"],
    )


def _first(raw: dict[str, Any], *keys: str, default: Any = None) -> Any:
    for key in keys:
        if key in raw and raw[key] not in (None, ""):
            return raw[key]
    return default


def _list(raw: dict[str, Any], *keys: str) -> list[Any]:
    value = _first(raw, *keys, default=[])
    return list(value) if isinstance(value, list) else []


def _num(value: Any, fallback: float = 0.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return fallback
    return number if math.isfinite(number) else fallback


def _slug(value: str) -> str:
    base = _norm(value).replace(" ", "-")
    base = re.sub(r"[^a-z0-9_-]+", "-", base).strip("-")
    return base[:48] or "diagrama"


def _label_width(text: str) -> float:
    return max(120.0, min(240.0, 26 + 7.2 * len(_squash(text))))


def _box_height(node: Node) -> float:
    base = 50 if not node.sublabel else 64
    if node.tag:
        base += 8
    if node.members:
        base += 14 * min(len(node.members), 8) + 10
    return float(base)


def _color(kind: str) -> str:
    return NODE_TYPES.get(kind, LIFECYCLE_TYPES.get(kind, CLASS_KINDS.get(kind, (kind, "#94a3b8"))))[1]


# --------------------------------------------------------------- leitura

_PRESETS = {
    "classico": "classico", "classic": "classico", "clássico": "classico",
    "sinal": "sinal", "signal": "sinal", "signal-flow": "sinal",
    "planta": "planta", "blueprint": "planta",
    "editorial": "editorial",
}
_LEGENDS = {"auto": "auto", "tudo": "tudo", "all": "tudo", "oculta": "oculta", "hidden": "oculta", "none": "oculta"}
_ANIMATIONS = {"traco": "traco", "trace": "traco", "nenhuma": "nenhuma", "none": "nenhuma"}
_QUALITIES = {"padrao": "padrao", "standard": "padrao", "vitrine": "vitrine", "showcase": "vitrine"}
_DIRECTIONS = {"direita": "direita", "right": "direita", "baixo": "baixo", "down": "baixo"}


def read_spec(raw: dict[str, Any]) -> Spec:
    """Lê o IR em PT-BR ou o IR do archify e devolve um modelo comum."""
    if not isinstance(raw, dict):
        raise DiagramError("A especificação precisa ser um objeto JSON.")

    raw_type = _first(raw, "tipo", "type", "diagram_type", default="")
    kind = TYPE_ALIASES.get(_norm(raw_type), "")
    if not kind:
        raise DiagramError(
            "Tipo de diagrama ausente ou desconhecido. Use um destes: " + ", ".join(TYPES) + "."
        )

    meta = raw.get("meta") if isinstance(raw.get("meta"), dict) else {}
    spec = Spec(
        kind=kind,
        title=_squash(_first(raw, "titulo", "title", default=meta.get("title", ""))),
        subtitle=_squash(_first(raw, "subtitulo", "subtitle", default=meta.get("subtitle", ""))),
        output=_squash(_first(raw, "saida", "output", default=meta.get("output", ""))),
        locale=_squash(_first(raw, "idioma", "locale", default=meta.get("locale", "pt-BR"))) or "pt-BR",
        animation=_ANIMATIONS.get(_norm(_first(raw, "animacao", "animation", default=meta.get("animation", "traco"))), "traco"),
        preset=_PRESETS.get(_norm(_first(raw, "preset", "visual_preset", default=meta.get("visual_preset", "classico"))), "classico"),
        quality=_QUALITIES.get(_norm(_first(raw, "qualidade", "quality_profile", default=meta.get("quality_profile", "padrao"))), "padrao"),
        legend=_LEGENDS.get(_norm(_first(raw, "legenda", "legend", default="auto")), "auto"),
        evidence=_squash(_first(raw, "evidencia", "evidence", default=meta.get("evidence", ""))),
        unit=_squash(_first(raw, "unidade", "unit", default=meta.get("unit", "ms"))) or "ms",
    )
    if isinstance(_first(raw, "legenda", "legend", default=None), dict):
        spec.legend = _LEGENDS.get(_norm(raw["legenda"].get("modo") or raw["legenda"].get("mode")), "auto")
    layout = raw.get("layout") if isinstance(raw.get("layout"), dict) else {}
    spec.direction = _DIRECTIONS.get(
        _norm(_first(layout, "direction", default=raw.get("direcao", "baixo"))), "baixo"
    )
    spec.layout = layout

    if raw.get("meta") or raw.get("diagram_type"):
        spec.notes.append("IR do archify reconhecido e convertido para o modelo do JARVIS.")

    _read_cards(spec, raw)
    reader = _READERS[kind]
    reader(spec, raw, meta)
    return spec


def _read_cards(spec: Spec, raw: dict[str, Any]) -> None:
    for index, item in enumerate(_list(raw, "cartoes", "cards")):
        if not isinstance(item, dict):
            continue
        dot = _norm(_first(item, "cor", "dot", default="slate"))
        spec.cards.append(
            Card(
                dot=dot if dot in CARD_DOTS else "slate",
                title=_squash(_first(item, "titulo", "title", default=f"Cartão {index + 1}")),
                items=[_squash(entry) for entry in _list(item, "itens", "items") if _squash(entry)],
            )
        )


def _read_architecture(spec: Spec, raw: dict[str, Any], meta: dict[str, Any]) -> None:
    band_order = {"external": 0, "frontend": 1, "backend": 2, "security": 2, "messagebus": 3, "database": 4, "cloud": 4}
    entries = _list(raw, "componentes", "components", "nodes", "nos")
    per_band: dict[int, int] = {}
    bands: set[int] = set()
    derived: list[tuple[int, Node]] = []
    for index, item in enumerate(entries):
        if not isinstance(item, dict):
            continue
        node_id = _squash(_first(item, "id", "componente", default=f"c{index + 1}"))
        node = Node(id=node_id, label=_label(_first(item, "rotulo", "label", "nome", default=node_id)))
        node.sublabel = _squash(_first(item, "subrotulo", "sublabel", "descricao", "descrição", default=""))
        raw_kind = _norm(_first(item, "tipo", "type", "componentType", default="backend"))
        node.kind = NODE_ALIASES.get(raw_kind, "backend")
        node.color = _color(node.kind)
        node.tag = _squash(_first(item, "etiqueta", "tag", default=""))
        explicit_band = _first(item, "faixa", "band", "row", "linha", default=None)
        explicit_col = _first(item, "coluna", "col", default=None)
        if explicit_band is not None:
            node.row = int(_num(explicit_band))
        else:
            node.row = band_order.get(node.kind, 2)
        if explicit_col is not None:
            node.col = int(_num(explicit_col))
        else:
            node.col = per_band.get(node.row, 0)
            per_band[node.row] = node.col + 1
        bands.add(node.row)
        derived.append((node.row, node))
        spec.nodes.append(node)
    if entries:
        ordered = sorted(bands)
        remap = {band: index for index, band in enumerate(ordered)}
        for band, node in derived:
            node.row = remap[band]
        if any(_first(item, "faixa", "band", default=None) is None for item in entries if isinstance(item, dict)):
            spec.notes.append("Faixas derivadas do tipo de componente na ordem externo → interface → serviço → banco.")

    for index, item in enumerate(_list(raw, "fronteiras", "boundaries")):
        if not isinstance(item, dict):
            continue
        spec.regions.append(
            Region(
                id=_squash(_first(item, "id", default=f"b{index + 1}")),
                label=_squash(_first(item, "rotulo", "label", default="Fronteira")),
                kind="boundary",
                members=[_squash(member) for member in _list(item, "membros", "members")],
            )
        )

    for index, item in enumerate(_list(raw, "conexoes", "connections", "edges", "links")):
        if not isinstance(item, dict):
            continue
        spec.links.append(
            Link(
                src=_squash(_first(item, "de", "from", "source", default="")),
                dst=_squash(_first(item, "para", "to", "target", default="")),
                label=_squash(_first(item, "rotulo", "label", default="")),
                variant=_squash(_first(item, "variante", "variant", default="default")),
            )
        )


def _read_workflow(spec: Spec, raw: dict[str, Any], meta: dict[str, Any]) -> None:
    lanes = _list(raw, "raias", "lanes")
    for index, lane in enumerate(lanes):
        if isinstance(lane, dict):
            spec.regions.append(
                Region(
                    id=_squash(_first(lane, "id", default=f"l{index + 1}")),
                    label=_squash(_first(lane, "rotulo", "label", default=f"Raia {index + 1}")),
                    kind="lane", row=index,
                )
            )
    spec.layout["lane_count"] = max(1, len(spec.regions))
    for index, item in enumerate(_list(raw, "etapas", "nodes", "nos")):
        if not isinstance(item, dict):
            continue
        node_id = _squash(_first(item, "id", default=f"n{index + 1}"))
        lane = _squash(_first(item, "raia", "lane", default=spec.regions[0].id if spec.regions else ""))
        row = next((region.row for region in spec.regions if region.id == lane), 0)
        node = Node(
            id=node_id,
            label=_label(_first(item, "rotulo", "label", default=node_id)),
            sublabel=_squash(_first(item, "subrotulo", "sublabel", default="")),
            tag=_squash(_first(item, "etiqueta", "tag", default="")),
            row=row,
        )
        spec.layout.setdefault("lane_of", {})[node_id] = lane
        node.kind = NODE_ALIASES.get(_norm(_first(item, "tipo", "type", default="backend")), "backend")
        if _norm(_first(item, "tipo", "type", default="")) in {"start", "success", "failure", "decision"}:
            node.kind = "external"
            node.tag = node.tag or LIFECYCLE_TYPES.get(_norm(item.get("type")), ("", ""))[0]
        node.color = _color(node.kind)
        node.col = int(_num(_first(item, "coluna", "col", default=index), index))
        spec.nodes.append(node)
    for index, item in enumerate(_list(raw, "fases", "phases")):
        if not isinstance(item, dict):
            continue
        spec.regions.append(
            Region(
                id=_squash(_first(item, "id", default=f"p{index + 1}")),
                label=_squash(_first(item, "rotulo", "label", default="")),
                kind="phase", col=int(_num(_first(item, "deCol", "fromCol", default=index), index)),
            )
        )
    for index, item in enumerate(_list(raw, "conexoes", "edges", "links")):
        if not isinstance(item, dict):
            continue
        spec.links.append(
            Link(
                src=_squash(_first(item, "de", "from", "source", default="")),
                dst=_squash(_first(item, "para", "to", "target", default="")),
                label=_squash(_first(item, "rotulo", "label", default="")),
                variant=_squash(_first(item, "variante", "variant", "role", default="default")),
            )
        )


def _read_sequence(spec: Spec, raw: dict[str, Any], meta: dict[str, Any]) -> None:
    participants = _list(raw, "participantes", "participants")
    for index, item in enumerate(participants):
        if not isinstance(item, dict):
            continue
        node_id = _squash(_first(item, "id", default=f"p{index + 1}"))
        node = Node(
            id=node_id,
            label=_label(_first(item, "rotulo", "label", default=node_id)),
            sublabel=_squash(_first(item, "subrotulo", "sublabel", default="")),
            col=index,
        )
        node.kind = NODE_ALIASES.get(_norm(_first(item, "tipo", "type", default="backend")), "backend")
        node.color = _color(node.kind)
        spec.nodes.append(node)
    messages = _list(raw, "mensagens", "messages")
    if not messages:
        messages = _list(raw, "etapas", "steps")
    for index, item in enumerate(messages):
        if not isinstance(item, dict):
            continue
        spec.links.append(
            Link(
                src=_squash(_first(item, "de", "from", "source", default="")),
                dst=_squash(_first(item, "para", "to", "target", default="")),
                label=_squash(_first(item, "rotulo", "label", default="")),
                variant=_squash(_first(item, "variante", "variant", "tipo", "type", default="default")),
            )
        )
    spec.layout["messages"] = len(spec.links)
    for index, item in enumerate(_list(raw, "segmentos", "segments")):
        if not isinstance(item, dict):
            continue
        spec.regions.append(
            Region(
                id=_squash(_first(item, "id", default=f"s{index + 1}")),
                label=_squash(_first(item, "rotulo", "label", default="")),
                kind="segment", row=index,
                members=[_squash(item.get("de", index))],
            )
        )
    activations = _list(raw, "ativacoes", "activations")
    if activations:
        spec.layout["activations"] = len(activations)


def _read_dataflow(spec: Spec, raw: dict[str, Any], meta: dict[str, Any]) -> None:
    stages = _list(raw, "estagios", "stages")
    for index, stage in enumerate(stages):
        label = _squash(stage.get("rotulo") or stage.get("label") if isinstance(stage, dict) else stage)
        spec.regions.append(Region(id=f"stage-{index}", label=label or f"Estágio {index + 1}", kind="stage", col=index))
    for index, item in enumerate(_list(raw, "elementos", "nodes", "nos")):
        if not isinstance(item, dict):
            continue
        node_id = _squash(_first(item, "id", default=f"n{index + 1}"))
        node = Node(
            id=node_id,
            label=_label(_first(item, "rotulo", "label", default=node_id)),
            sublabel=_squash(_first(item, "subrotulo", "sublabel", default="")),
            tag=_squash(_first(item, "etiqueta", "tag", default="")),
            col=int(_num(_first(item, "estagio", "stage", default=0))),
            row=int(_num(_first(item, "linha", "row", default=0))),
        )
        node.kind = NODE_ALIASES.get(_norm(_first(item, "tipo", "type", default="backend")), "backend")
        node.color = _color(node.kind)
        spec.nodes.append(node)
    for index, item in enumerate(_list(raw, "fluxos", "flows", "edges", "links")):
        if not isinstance(item, dict):
            continue
        spec.links.append(
            Link(
                src=_squash(_first(item, "de", "from", "source", default="")),
                dst=_squash(_first(item, "para", "to", "target", default="")),
                label=_squash(_first(item, "rotulo", "label", default="")),
                variant=_squash(_first(item, "variante", "variant", default="default")),
            )
        )


def _read_lifecycle(spec: Spec, raw: dict[str, Any], meta: dict[str, Any]) -> None:
    for index, item in enumerate(_list(raw, "estados", "states")):
        if not isinstance(item, dict):
            continue
        node_id = _squash(_first(item, "id", default=f"e{index + 1}"))
        raw_kind = _norm(_first(item, "tipo", "type", default="active"))
        kind = LIFECYCLE_ALIASES.get(raw_kind, "active")
        node = Node(
            id=node_id,
            label=_label(_first(item, "rotulo", "label", default=node_id)),
            sublabel=_squash(_first(item, "subrotulo", "sublabel", default="")),
            tag=_squash(_first(item, "etiqueta", "tag", default="")),
            kind=kind,
        )
        node.color = _color(kind)
        spec.nodes.append(node)
    for index, item in enumerate(_list(raw, "transicoes", "transitions")):
        if not isinstance(item, dict):
            continue
        spec.links.append(
            Link(
                src=_squash(_first(item, "de", "from", "source", default="")),
                dst=_squash(_first(item, "para", "to", "target", default="")),
                label=_squash(_first(item, "rotulo", "label", default="")),
                variant=_squash(_first(item, "variante", "variant", default="default")),
            )
        )
    path = [_squash(item) for item in _list(raw, "caminhoPrincipal", "mainPath") if _squash(item)]
    spec.layout["main_path"] = path


def _read_erd(spec: Spec, raw: dict[str, Any], meta: dict[str, Any]) -> None:
    entities = _list(raw, "entidades", "entities")
    explicit = any(isinstance(item, dict) and _first(item, "linha", "row") is not None for item in entities)
    for index, item in enumerate(entities):
        if not isinstance(item, dict):
            continue
        node_id = _squash(_first(item, "id", default=f"e{index + 1}"))
        node = Node(
            id=node_id,
            label=_label(_first(item, "rotulo", "label", default=node_id)),
            sublabel=_squash(_first(item, "subrotulo", "sublabel", default="")),
            tag=_squash(_first(item, "etiqueta", "tag", default="")),
            row=int(_num(_first(item, "linha", "row", default=index // 3 if not explicit else 0))),
            col=int(_num(_first(item, "coluna", "col", default=index % 3 if not explicit else 0))),
            kind="database",
        )
        node.color = _color("database")
        for attribute in _list(item, "atributos", "attributes", "columns"):
            if isinstance(attribute, dict):
                key = _squash(_first(attribute, "chave", "key", default=""))
                marker = {"pk": "PK", "uk": "UK", "fk": "FK"}.get(key.lower(), "")
                name = _squash(_first(attribute, "nome", "name", default=""))
                atype = _squash(_first(attribute, "tipo", "type", default=""))
                line = f"{name}  {atype}".strip()
                if marker:
                    line = f"{marker} {line}"
                node.members.append(line)
            elif attribute:
                node.members.append(_squash(attribute))
        spec.nodes.append(node)
    for index, item in enumerate(_list(raw, "relacionamentos", "relationships")):
        if not isinstance(item, dict):
            continue
        src_card = _squash(_first(item, "cardinalidadeDe", "fromCardinality", default=""))
        dst_card = _squash(_first(item, "cardinalidadePara", "toCardinality", default=""))
        spec.links.append(
            Link(
                src=_squash(_first(item, "de", "from", default="")),
                dst=_squash(_first(item, "para", "to", default="")),
                label=_squash(_first(item, "rotulo", "label", default="")) or f"{src_card or '*'} → {dst_card or '*'}",
                variant="default",
            )
        )


def _read_tree(spec: Spec, raw: dict[str, Any], meta: dict[str, Any]) -> None:
    for index, item in enumerate(_list(raw, "nos", "nodes")):
        if not isinstance(item, dict):
            continue
        node_id = _squash(_first(item, "id", default=f"n{index + 1}"))
        spec.nodes.append(
            Node(
                id=node_id,
                label=_label(_first(item, "rotulo", "label", default=node_id)),
                sublabel=_squash(_first(item, "subrotulo", "sublabel", default="")),
                tag=_squash(_first(item, "etiqueta", "tag", default="")),
                parent=_squash(_first(item, "pai", "parent", default="")),
                kind="cloud",
                color=_color("cloud"),
            )
        )
    roots = [node.id for node in spec.nodes if not node.parent]
    if len(roots) != 1:
        _issue(
            spec, "must", "uma-raiz", "Árvore com uma raiz", "nos",
            f"{len(roots)} nós sem pai.",
            "Uma árvore declara exatamente um nó raiz; dois pais possíveis viram grafo.",
            "Deixe um único nó sem `pai` e ligue os demais a ele.",
            "O desenho deixa de ser hierarquia e perde a leitura por nível.",
        )


def _read_class(spec: Spec, raw: dict[str, Any], meta: dict[str, Any]) -> None:
    types = _list(raw, "tipos", "types")
    explicit = any(isinstance(item, dict) and _first(item, "linha", "row") is not None for item in types)
    for index, item in enumerate(types):
        if not isinstance(item, dict):
            continue
        node_id = _squash(_first(item, "id", default=f"t{index + 1}"))
        raw_kind = _norm(_first(item, "tipo", "kind", default="class"))
        node = Node(
            id=node_id,
            label=_label(_first(item, "rotulo", "label", default=node_id)),
            sublabel=_squash(_first(item, "subrotulo", "sublabel", default="")),
            row=int(_num(_first(item, "linha", "row", default=index // 3 if not explicit else 0))),
            col=int(_num(_first(item, "coluna", "col", default=index % 3 if not explicit else 0))),
            kind=raw_kind if raw_kind in CLASS_KINDS else "class",
        )
        node.color = _color(node.kind) if node.kind in CLASS_KINDS else NODE_TYPES["external"][1]
        for attribute in _list(item, "atributos", "attributes"):
            if isinstance(attribute, dict):
                visibility = _squash(_first(attribute, "visibilidade", "visibility", default="private"))
                symbol = {"public": "+", "private": "-", "protected": "#", "package": "~"}.get(visibility, "-")
                node.members.append(
                    f"{symbol} {_squash(_first(attribute, 'nome', 'name', default=''))}"
                    f" : {_squash(_first(attribute, 'tipo', 'type', default=''))}".strip()
                )
            elif attribute:
                node.members.append(_squash(attribute))
        for method in _list(item, "metodos", "methods"):
            if isinstance(method, dict):
                visibility = _squash(_first(method, "visibilidade", "visibility", default="public"))
                symbol = {"public": "+", "private": "-", "protected": "#", "package": "~"}.get(visibility, "+")
                name = _squash(_first(method, "nome", "name", default=""))
                params = _squash(_first(method, "parametros", "parameters", default=""))
                returns = _squash(_first(method, "retorno", "returns", default=""))
                line = f"{symbol} {name}({params})"
                node.members.append(f"{line} : {returns}".strip() if returns else line)
            elif method:
                node.members.append(_squash(method))
        spec.nodes.append(node)
    for index, item in enumerate(_list(raw, "relacionamentos", "relationships")):
        if not isinstance(item, dict):
            continue
        raw_kind = _norm(_first(item, "tipo", "kind", default="association"))
        if raw_kind not in REL_KINDS:
            _issue(
                spec, "should", "relacao-desconhecida", "Relação fora do vocabulário", f"tipos/{index}",
                f"Tipo `{raw_kind}`.",
                "Só seis relações têm notação UML estável aqui.",
                "Use dependency, association, inheritance, realization, composition ou aggregation.",
                "A linha perde o marcador e passa a sugerir outra semântica.",
            )
            raw_kind = "association"
        spec.links.append(
            Link(
                src=_squash(_first(item, "de", "from", default="")),
                dst=_squash(_first(item, "para", "to", default="")),
                label=_squash(_first(item, "rotulo", "label", default="")) or REL_KINDS[raw_kind][0],
                variant=raw_kind,
            )
        )


def _parse_time(value: Any) -> datetime | None:
    text = _text(value).strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def _read_timeline(spec: Spec, raw: dict[str, Any], meta: dict[str, Any]) -> None:
    for index, lane in enumerate(_list(raw, "raias", "lanes")):
        if isinstance(lane, dict):
            spec.regions.append(
                Region(
                    id=_squash(_first(lane, "id", default=f"l{index + 1}")),
                    label=_squash(_first(lane, "rotulo", "label", default=f"Raia {index + 1}")),
                    kind="lane", row=index,
                )
            )
    for index, item in enumerate(_list(raw, "eventos", "events")):
        if not isinstance(item, dict):
            continue
        lane = _squash(_first(item, "raia", "lane", default=""))
        row = next((region.row for region in spec.regions if region.id == lane), 0)
        when = _squash(_first(item, "quando", "at", "data", default=""))
        if not _parse_time(when):
            _issue(
                spec, "must", "data-invalida", "Evento sem data legível", f"eventos/{index}",
                f"`{when or 'vazio'}`.",
                "A linha do tempo posiciona o evento pelo instante; sem data ele não tem lugar.",
                "Use ISO 8601 com fuso, por exemplo 2026-10-01T10:00:00-03:00.",
                "O evento é descartado do desenho.",
            )
        node = Node(
            id=_squash(_first(item, "id", default=f"ev{index + 1}")),
            label=_label(_first(item, "titulo", "title", "rotulo", "label", default=f"Evento {index + 1}")),
            sublabel=_squash(_first(item, "detalhe", "detail", default="")),
            tag=TIMELINE_KINDS.get(_norm(_first(item, "tipo", "kind", default="default")), TIMELINE_KINDS["default"])[0],
            at=when,
            row=row,
            kind=_norm(_first(item, "tipo", "kind", default="default")),
            col=index,
        )
        node.color = TIMELINE_KINDS.get(node.kind, TIMELINE_KINDS["default"])[1]
        spec.nodes.append(node)
    _timeline_notes(spec, meta)


def _timeline_notes(spec: Spec, meta: dict[str, Any]) -> None:
    if _norm(meta.get("evidence", spec.evidence)) == "illustrative":
        spec.notes.append("Timing ilustrativo: o cabeçalho precisa dizer isso.")


def _read_waterfall(spec: Spec, raw: dict[str, Any], meta: dict[str, Any]) -> None:
    spans = _list(raw, "trechos", "spans")
    parents: dict[str, str] = {}
    for index, item in enumerate(spans):
        if not isinstance(item, dict):
            continue
        node_id = _squash(_first(item, "id", default=f"s{index + 1}"))
        start = _num(_first(item, "inicio", "start", default=0))
        end = _num(_first(item, "fim", "end", default=start))
        node = Node(
            id=node_id,
            label=_label(_first(item, "nome", "name", "rotulo", "label", default=node_id)),
            sublabel=_squash(_first(item, "servico", "service", default="")),
            tag=_squash(_first(item, "detalhe", "detail", default="")),
            start=start,
            end=end,
            parent=_squash(_first(item, "pai", "parent", default="")),
            kind=_norm(_first(item, "status", default="ok")),
            row=index,
        )
        parents[node_id] = node.parent
        node.color = WATERFALL_STATUS.get(node.kind, WATERFALL_STATUS["ok"])[1]
        spec.nodes.append(node)
    for node in spec.nodes:
        depth = 0
        parent = node.parent
        seen: set[str] = set()
        while parent and parent in parents and parent not in seen:
            seen.add(parent)
            depth += 1
            parent = parents[parent]
        node.depth = min(depth, 6)


_READERS = {
    "architecture": _read_architecture,
    "workflow": _read_workflow,
    "sequence": _read_sequence,
    "dataflow": _read_dataflow,
    "lifecycle": _read_lifecycle,
    "erd": _read_erd,
    "tree": _read_tree,
    "class": _read_class,
    "timeline": _read_timeline,
    "waterfall": _read_waterfall,
}


# ------------------------------------------------------------ validação

def validate_spec(spec: Spec) -> list[dict[str, str]]:
    if not spec.title:
        _issue(spec, "must", "sem-titulo", "Diagrama sem título", "titulo",
               "O campo obrigatório não veio.",
               "Sem título o leitor não sabe qual pergunta o desenho responde.",
               "Declare `titulo` com o recorte, não com o tipo de diagrama.",
               "O artefato não passa no gate de entrega.")
    elif len(spec.title) > 72:
        _issue(spec, "should", "titulo-longo", "Título acima do orçamento", "titulo",
               f"{len(spec.title)} caracteres.",
               "Acima de 72 o título quebra em duas linhas no cabeçalho e empurra o desenho.",
               "Corte para uma frase de até 72 caracteres e mova o resto para `subtitulo`.",
               "O primeiro bloco de leitura perde hierarquia.")
    if not spec.output:
        _issue(spec, "should", "sem-saida", "Sem caminho de saída", "saida",
               "`saida` não declarado.",
               "O contrato de entrega grava um HTML portátil; sem caminho o arquivo fica implícito.",
               "Declare `saida` como caminho POSIX relativo terminando em `.html`.",
               "A entrega depende de combinação manual e o artefato se perde.")
    elif not spec.output.lower().endswith(".html"):
        _issue(spec, "must", "saida-nao-html", "Saída que não é HTML", "saida",
               f"`{spec.output}`.",
               "O contrato exige um arquivo HTML autocontido para abrir sem servidor.",
               "Termine o caminho em `.html`.",
               "O artefato deixa de ser portátil.")

    ids: dict[str, int] = {}
    for node in spec.nodes:
        if node.id in ids:
            _issue(spec, "must", "id-duplicado", "Identificador duplicado", f"nos/{node.id}",
                   node.id,
                   "Dois nós com o mesmo id tornam arestas e regiões ambíguas.",
                   "Renomeie um dos nós; ids aceitam letras, números, hífen e sublinhado.",
                   "A segunda ocorrência é ignorada pelo desenho.")
        ids[node.id] = ids.get(node.id, 0) + 1
        if not node.id or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]*", node.id):
            _issue(spec, "must", "id-invalido", "Identificador fora do padrão", f"nos/{node.id}",
                   f"`{node.id}`.",
                   "O padrão começa com letra e segue com letras, números, hífen ou sublinhado.",
                   "Ajuste o id; ele aparece nas arestas e no DOT exportado.",
                   "Rotas e referências apontam para o vazio.")
        if not node.label:
            _issue(spec, "must", "rotulo-vazio", "Nó sem rótulo", f"nos/{node.id}",
                   node.id,
                   "Um retângulo vazio não informa nada e ocupa espaço.",
                   "Dê ao nó um rótulo curto e específico.",
                   "O desenho perde um fato que o leitor precisava.")

    if not spec.nodes:
        _issue(spec, "must", "sem-nos", "Diagrama sem nós", TYPES[spec.kind]["node_kind"],
               "O array principal veio vazio.",
               "O tipo escolhido exige pelo menos um nó para desenhar.",
               f"Preencha `{TYPES[spec.kind]['arrays'][0]}` com um nó por item.",
               "Não há desenho para entregar.")
    elif len(spec.nodes) > MAX_NODES:
        _issue(spec, "must", "nos-demais", "Nós acima do teto", TYPES[spec.kind]["node_kind"],
               f"{len(spec.nodes)} nós.",
               f"Acima de {MAX_NODES} o desenho deixa de ser lido de relance e vira inventário.",
               "Divida em dois diagramas ou agrupe capacidades em um nó de subsistema.",
               "O leitor desiste antes da metade.")
    elif len(spec.nodes) > TYPES[spec.kind]["budget"]:
        _issue(spec, "should", "acima-do-orcamento", "Acima do orçamento do tipo",
               TYPES[spec.kind]["node_kind"],
               f"{len(spec.nodes)} nós para um orçamento de {TYPES[spec.kind]['budget']}.",
               f"{TYPES[spec.kind]['label']} é lido em uma passada; acima disso a rota vira teia.",
               "Separe o mecanismo perguntado do resto e leve o resto para um cartão.",
               "O desenho continua correto, mas perde a leitura de relance.")

    long_labels = [node for node in spec.nodes if len(node.label) > WARN_LABEL]
    for node in long_labels[:3]:
        _issue(spec, "should", "rotulo-longo", "Rótulo acima da folga", f"nos/{node.id}",
               f"`{node.label}` ({len(node.label)}).",
               "Acima de 28 caracteres o nó cresce e come a folga do rótulo da aresta.",
               "Corte para duas ou três palavras e leve o detalhe ao subrótulo.",
               "As linhas encostam no texto e a rota fica ilegível.")
    for node in [node for node in spec.nodes if len(node.sublabel) > WARN_SUBLABEL][:3]:
        _issue(spec, "should", "subrotulo-longo", "Sub-rótulo acima da folga", f"nos/{node.id}",
               f"{len(node.sublabel)} caracteres.",
               "Sub-rótulos longos definem a largura do nó e reduzem a densidade útil.",
               "Resuma em até 44 caracteres; o resto pertence a um cartão.",
               "O desenho fica largo e o texto encolhe.")
    if any(len(node.label) > MAX_LABEL for node in spec.nodes):
        _issue(spec, "must", "rotulo-limite", "Rótulo acima do limite duro", TYPES[spec.kind]["node_kind"],
               f"Limite de {MAX_LABEL} caracteres.",
               "Acima do limite o motor não consegue manter a folga mínima entre nós.",
               "Corte o rótulo ou transforme o texto longo em sub-rótulo.",
               "O nó é truncado no desenho.")

    if len(spec.cards) > MAX_CARDS:
        _issue(spec, "should", "cartoes-demais", "Cartões acima do teto", "cartoes",
               f"{len(spec.cards)} cartões.",
               "Cartões respondem perguntas extras; em excesso competem com o diagrama.",
               f"Fique com {MAX_CARDS} cartões e mova o resto para o texto da entrega.",
               "O rodapé vira mural e o desenho deixa de ser o centro.")

    if spec.kind == "tree":
        for node in spec.nodes:
            if node.parent and node.parent not in ids:
                _issue(spec, "must", "pai-ausente", "Pai inexistente na árvore", f"nos/{node.id}",
                       f"`{node.parent}`.",
                       "A hierarquia exige que todo pai exista no mesmo documento.",
                       "Corrija o id do pai ou remova o campo para o nó ser raiz.",
                       "O ramo some do desenho.")
        if spec.nodes and not any(not node.parent for node in spec.nodes):
            _issue(spec, "must", "sem-raiz", "Árvore sem raiz", "nos",
                   "Todos os nós têm pai.",
                   "Sem raiz não há nível zero; o ciclo não pode ser desenhado como árvore.",
                   "Remova o `pai` de um nó de topo.",
                   "O layout não encontra ponto de partida.")
        elif _tree_has_cycle(spec):
            _issue(spec, "must", "ciclo", "Ciclo na hierarquia", "nos",
                   "Um nó alcança a si mesmo seguindo os pais.",
                   "Árvore é aciclica por definição; ciclo é grafo, não hierarquia.",
                   "Quebre o ciclo ou troque para o tipo `architecture` com conexões.",
                   "A profundidade não converge.")

    seen_links: set[tuple[str, str, str]] = set()
    for index, link in enumerate(spec.links):
        location = f"arestas/{index + 1}"
        if not link.src or not link.dst:
            _issue(spec, "must", "aresta-incompleta", "Aresta sem as duas pontas", location,
                   f"`{link.src or '?'} → {link.dst or '?'}`.",
                   "Toda relação nomeia origem e destino.",
                   "Preencha `de` e `para` com ids declarados.",
                   "A relação desaparece do desenho.")
            continue
        missing = [end for end in (link.src, link.dst) if end not in ids]
        if missing:
            _issue(spec, "must", "aresta-orfa", "Aresta aponta para id inexistente", location,
                   f"`{link.src} → {link.dst}` (falta {', '.join(missing)}).",
                   "O desenho não inventa pontas; a relação fica sem traço.",
                   "Declare o nó ausente ou corrija o id na aresta.",
                   "O leitor perde a relação que o texto prometia.")
            continue
        if link.src == link.dst:
            _issue(spec, "should", "auto-laco", "Relação de um nó com ele mesmo", location,
                   link.src,
                   "Laço próprio só se justifica em sequência com nota, e mesmo lá confunde.",
                   "Descreva a repetição em uma nota no nó ou em um cartão.",
                   "O traço volta sobre si e parece erro de desenho.")
        key = (link.src, link.dst, link.label)
        if key in seen_links:
            _issue(spec, "should", "aresta-repetida", "Aresta repetida", location,
                   f"`{link.src} → {link.dst}`.",
                   "Duas linhas idênticas dobram a espessura e sugerem duas relações.",
                   "Deixe uma só ou diferencie protocolo, condição ou assíncrono no rótulo.",
                   "A espessura mente sobre a quantidade de relações.")
        seen_links.add(key)
        if len(link.label) > MAX_EDGE_LABEL:
            _issue(spec, "should", "rotulo-aresta-longo", "Rótulo de aresta acima do orçamento", location,
                   f"{len(link.label)} caracteres.",
                   "Cada caractere a mais exige 6,5 px de folga entre as caixas.",
                   "Corte para 28 caracteres ou menos e deixe o detalhe no cartão.",
                   "O rótulo encosta nas caixas e a rota perde leitura.")
        if link.variant not in {"default", "emphasis", "security", "dashed", "return"} | set(REL_KINDS):
            _issue(spec, "nice", "variante-nova", "Variante fora do vocabulário", location,
                   f"`{link.variant}`.",
                   "Quatro variantes têm legenda automática; a quinta precisa de rótulo explícito.",
                   "Use default, emphasis, security ou dashed, ou declare a legenda.",
                   "A linha perde o significado na legenda.")

    if spec.kind == "lifecycle":
        path = spec.layout.get("main_path") or []
        invalid = [item for item in path if item not in ids]
        if invalid:
            _issue(spec, "must", "caminho-invalido", "Caminho principal aponta para estado ausente", "caminhoPrincipal",
                   ", ".join(invalid),
                   "O caminho principal é a espinha do desenho e precisa existir.",
                   "Corrija os ids ou remova o passo.",
                   "O desenho perde a ordem que o leitor segue.")
        if not path:
            _issue(spec, "should", "sem-caminho", "Ciclo sem caminho principal declarado", "caminhoPrincipal",
                   "`caminhoPrincipal` veio vazio.",
                   "Sem caminho o layout escolhe a ordem e a narrativa deixa de ser autoral.",
                   "Liste os estados do caminho feliz em ordem.",
                   "O desenho fica correto, mas sem narrativa única.")
    if spec.kind == "waterfall":
        for node in spec.nodes:
            if node.end < node.start:
                _issue(spec, "must", "trecho-invertido", "Trecho termina antes de começar", f"trechos/{node.id}",
                       f"{node.start} → {node.end}.",
                       "Duração negativa não existe e quebra a escala.",
                       "Corrija o fim ou o início.",
                       "O trecho é omitido da cascata.")
        if spec.evidence and _norm(spec.evidence) != "illustrative":
            _issue(spec, "nice", "evidencia", "Evidência declarada", "evidencia",
                   f"`{spec.evidence}`.",
                   "Medido e ilustrativo não podem ter o mesmo cabeçalho.",
                   "Use `evidencia: \"ilustrativo\"` quando os números forem de exemplo.",
                   "O leitor toma exemplo por medição.")
    if spec.kind == "timeline" and any(not _parse_time(node.at) for node in spec.nodes):
        spec.nodes = [node for node in spec.nodes if _parse_time(node.at)]
        if not spec.nodes:
            _issue(spec, "must", "sem-eventos", "Linha do tempo sem eventos datados", "eventos",
                   "Nenhum evento tem data ISO legível.",
                   "A linha do tempo existe para ordenar instantes.",
                   "Corrija as datas para ISO 8601 com fuso.",
                   "Não há eixo para desenhar.")
    return spec.issues


def _tree_has_cycle(spec: Spec) -> bool:
    parents = {node.id: node.parent for node in spec.nodes}
    for node in spec.nodes:
        seen: set[str] = set()
        current = node.id
        while current and current in parents and current not in seen:
            seen.add(current)
            current = parents[current]
        if current in seen:
            return True
    return False


# --------------------------------------------------------------- layout

PAD = 44.0
GAP_X = 68.0
GAP_Y = 34.0
HEADER = 86.0
CONTENT_W = 1152.0


def _size(node: Node, min_w: float = 120.0) -> None:
    node.w = max(min_w, _label_width(node.label), min(240.0, 22 + 6.1 * len(node.sublabel)) if node.sublabel else 0)
    node.h = _box_height(node)


def _place_row(spec: Spec, nodes: list[Node], y: float, left: float, right: float, gap: float = GAP_X) -> float:
    total = sum(node.w for node in nodes) + gap * (len(nodes) - 1)
    width = right - left
    start = left + max(0.0, (width - total) / 2)
    height = max((node.h for node in nodes), default=0.0)
    for node in nodes:
        node.x = start
        node.y = y
        node.h = height
        start += node.w + gap
    return y + height


def _layout_grid(spec: Spec, left: float = PAD, right: float = PAD + CONTENT_W, top: float = HEADER) -> None:
    rows: dict[int, list[Node]] = {}
    for node in spec.nodes:
        _size(node)
        rows.setdefault(node.row, []).append(node)
    y = top
    for index in sorted(rows):
        y = _place_row(spec, rows[index], y, left, right) + GAP_Y
    spec.height = y - GAP_Y + PAD


def _layout_architecture(spec: Spec) -> None:
    _layout_grid(spec)


def _layout_workflow(spec: Spec) -> None:
    lane_count = max(1, int(spec.layout.get("lane_count", 1)))
    gutters = [region for region in spec.regions if region.kind == "lane"]
    gutter = 140.0 if gutters else 0.0
    cols = sorted({node.col for node in spec.nodes}) or [0]
    col_w: dict[int, float] = {}
    for node in spec.nodes:
        _size(node)
        col_w[node.col] = max(col_w.get(node.col, 0.0), node.w)
    x_of: dict[int, float] = {}
    x = PAD + gutter
    for col in cols:
        x_of[col] = x
        x += col_w[col] + GAP_X
    row_h: dict[int, float] = {}
    for node in spec.nodes:
        row_h[node.row] = max(row_h.get(node.row, 0.0), node.h)
    y_of: dict[int, float] = {}
    y = HEADER
    for row in range(lane_count):
        y_of[row] = y
        y += row_h.get(row, 74.0) + 46
    for node in spec.nodes:
        node.x = x_of.get(node.col, PAD + gutter)
        node.y = y_of.get(node.row, HEADER) + 12
    spec.width = max(PAD + CONTENT_W, x - GAP_X + PAD)
    spec.height = y + PAD - 10
    for region in gutters:
        region.x = PAD
        region.y = y_of.get(region.row, HEADER)
        region.w = spec.width - 2 * PAD
        region.h = row_h.get(region.row, 74.0) + 34


def _layout_dataflow(spec: Spec) -> None:
    stages = [region for region in spec.regions if region.kind == "stage"]
    cols = sorted({node.col for node in spec.nodes}) or [0]
    col_w: dict[int, float] = {}
    for node in spec.nodes:
        _size(node)
        col_w[node.col] = max(col_w.get(node.col, 0.0), node.w)
    x_of: dict[int, float] = {}
    x = PAD
    for col in cols:
        x_of[col] = x
        x += col_w[col] + 64
    rows = sorted({node.row for node in spec.nodes}) or [0]
    row_h: dict[int, float] = {}
    for node in spec.nodes:
        row_h[node.row] = max(row_h.get(node.row, 0.0), node.h)
    y_of: dict[int, float] = {}
    y = HEADER + 24
    for row in rows:
        y_of[row] = y
        y += row_h.get(row, 60.0) + 34
    for node in spec.nodes:
        node.x = x_of.get(node.col, PAD) + max(0.0, (col_w.get(node.col, node.w) - node.w) / 2)
        node.y = y_of.get(node.row, HEADER + 24)
    spec.width = max(PAD + CONTENT_W, x - 64 + PAD)
    spec.height = y + PAD
    for region in stages:
        region.x = x_of.get(region.col, PAD) - 24
        region.w = col_w.get(region.col, 120.0) + 48
        region.y = HEADER
        region.h = spec.height - HEADER - PAD + 10


def _layout_sequence(spec: Spec) -> None:
    count = max(1, len(spec.nodes))
    step = 232.0
    width = max(PAD + CONTENT_W, PAD + 60 + step * (count - 1) + 168 + PAD)
    for index, node in enumerate(spec.nodes):
        _size(node, min_w=132)
        node.x = PAD + 60 + index * step
        node.y = HEADER + 12
        node.w = min(168.0, node.w + 16)
        node.col = index
    total = len(spec.links)
    base = HEADER + 118
    gap = 30.0 if total > 14 else 44.0
    for index, link in enumerate(spec.links):
        src = spec.node(link.src)
        dst = spec.node(link.dst)
        y = base + index * gap
        if src and dst:
            link.points = [(src.x + src.w / 2, y), (dst.x + dst.w / 2, y)]
        link.marked = True
    bottom = base + (total - 1) * gap + 46 if total else base + 40
    spec.layout["axis"] = {"top": HEADER + 84, "bottom": bottom}
    spec.width = width
    spec.height = bottom + 62


def _layout_lifecycle(spec: Spec) -> None:
    path = [_squash(item) for item in spec.layout.get("main_path", []) if _squash(item)]
    known = {node.id: node for node in spec.nodes}
    if not path and spec.nodes:
        starts = [node.id for node in spec.nodes if node.kind == "start"] or [spec.nodes[0].id]
        current = starts[0]
        visited: set[str] = set()
        while current and current in known and current not in visited:
            visited.add(current)
            path.append(current)
            nxt = next((link.dst for link in spec.links if link.src == current and link.dst not in visited), "")
            current = nxt
        for node in spec.nodes:
            if node.id not in path:
                path.append(node.id)
    rest = [node.id for node in spec.nodes if node.id not in path]
    order = path + rest
    per_row = min(4, max(3, len(order)))
    width_span = CONTENT_W
    cell = width_span / per_row
    for index, node_id in enumerate(order):
        node = known.get(node_id)
        if not node:
            continue
        _size(node)
        row = index // per_row
        col = index % per_row if row % 2 == 0 else per_row - 1 - (index % per_row)
        node.row = row
        node.col = col
        node.x = PAD + col * cell + max(0.0, (cell - GAP_X - node.w) / 2)
        node.y = HEADER + row * 118
    spec.width = PAD * 2 + CONTENT_W
    spec.height = HEADER + ((len(order) - 1) // per_row + 1) * 118 + PAD if order else 320


def _layout_tree(spec: Spec) -> None:
    children: dict[str, list[Node]] = {}
    root: Node | None = None
    for node in spec.nodes:
        _size(node, min_w=136)
        if node.parent:
            children.setdefault(node.parent, []).append(node)
        elif root is None:
            root = node
    if root is None:
        spec.height = 280
        return
    horizontal = spec.direction == "direita"

    slots: dict[str, int] = {}
    counter = [0]

    def walk(node: Node, level: int) -> None:
        node.depth = level
        kids = children.get(node.id, [])
        if horizontal:
            slots[node.id] = counter[0]
            counter[0] += 1
        if not kids:
            if not horizontal:
                slots[node.id] = counter[0]
                counter[0] += 1
            return
        for kid in kids:
            walk(kid, level + 1)
        if not horizontal:
            slots[node.id] = (slots[kids[0].id] + slots[kids[-1].id]) / 2

    walk(root, 0)
    max_w = max(node.w for node in spec.nodes)
    max_h = max(node.h for node in spec.nodes)
    if horizontal:
        for node in spec.nodes:
            node.x = PAD + node.depth * (max_w + 84)
            node.y = HEADER + slots.get(node.id, 0) * (max_h + 26)
        spec.width = PAD * 2 + (max(node.depth for node in spec.nodes) + 1) * (max_w + 84)
        spec.height = HEADER + counter[0] * (max_h + 26) + PAD
    else:
        for node in spec.nodes:
            node.x = PAD + slots.get(node.id, 0) * (max_w + 28) + (max_w - node.w) / 2
            node.y = HEADER + node.depth * (max_h + 62)
        spec.width = max(PAD + CONTENT_W, PAD * 2 + counter[0] * (max_w + 28))
        spec.height = HEADER + (max(node.depth for node in spec.nodes) + 1) * (max_h + 62) + PAD


def _layout_pairs(spec: Spec) -> None:
    cols = sorted({node.col for node in spec.nodes}) or [0]
    rows = sorted({node.row for node in spec.nodes}) or [0]
    col_w = {col: 0.0 for col in cols}
    row_h = {row: 0.0 for row in rows}
    for node in spec.nodes:
        _size(node, min_w=176)
        col_w[node.col] = max(col_w[node.col], node.w)
        row_h[node.row] = max(row_h[node.row], node.h)
    x_of: dict[int, float] = {}
    x = PAD
    for col in cols:
        x_of[col] = x
        x += col_w[col] + 104
    y_of: dict[int, float] = {}
    y = HEADER
    for row in rows:
        y_of[row] = y
        y += row_h[row] + 30
    for node in spec.nodes:
        node.x = x_of[node.col]
        node.y = y_of[node.row]
    spec.width = max(PAD + CONTENT_W, x - 104 + PAD)
    spec.height = y + PAD


def _layout_timeline(spec: Spec) -> None:
    stamps = [(_parse_time(node.at), node) for node in spec.nodes]
    stamps = [(when, node) for when, node in stamps if when]
    if not stamps:
        spec.height = 300
        return
    start = min(when for when, _ in stamps)
    end = max(when for when, _ in stamps)
    span = max(1.0, (end - start).total_seconds())
    lanes = max(1, len([region for region in spec.regions if region.kind == "lane"]) or 1)
    axis_left, axis_w = PAD + 154, CONTENT_W - 190
    for when, node in stamps:
        _size(node, min_w=150)
        fraction = (when - start).total_seconds() / span
        node.x = axis_left + fraction * axis_w
        node.w = 156.0
        node.h = 46.0
        node.y = HEADER + 54 + node.row * 104
        node.x = min(node.x, PAD + CONTENT_W - node.w)
    spec.layout["time_axis"] = {"left": axis_left, "width": axis_w, "start": start.isoformat(), "end": end.isoformat()}
    spec.width = PAD * 2 + CONTENT_W
    spec.height = HEADER + 54 + lanes * 104 + 64
    for region in [region for region in spec.regions if region.kind == "lane"]:
        region.x = PAD
        region.y = HEADER + 40 + region.row * 104
        region.w = CONTENT_W
        region.h = 100


def _layout_waterfall(spec: Spec) -> None:
    valid = [node for node in spec.nodes if node.end >= node.start]
    if not valid:
        spec.height = 300
        return
    end = max(node.end for node in valid) or 1.0
    left, width = PAD + 230, CONTENT_W - 260
    for node in valid:
        node.w = max(6.0, (node.end - node.start) / end * width)
        node.x = left + node.start / end * width
        node.h = 22.0
        node.y = HEADER + node.row * 38
    spec.layout["scale"] = {"max": end, "left": left, "width": width}
    spec.width = PAD * 2 + CONTENT_W
    spec.height = HEADER + len(valid) * 38 + 56


_LAYOUTS = {
    "architecture": _layout_architecture,
    "workflow": _layout_workflow,
    "sequence": _layout_sequence,
    "dataflow": _layout_dataflow,
    "lifecycle": _layout_lifecycle,
    "erd": _layout_pairs,
    "tree": _layout_tree,
    "class": _layout_pairs,
    "timeline": _layout_timeline,
    "waterfall": _layout_waterfall,
}


def layout_spec(spec: Spec) -> None:
    if not spec.width:
        spec.width = PAD * 2 + CONTENT_W
    _LAYOUTS[spec.kind](spec)
    if spec.width <= 0:
        spec.width = PAD * 2 + CONTENT_W
    _frame_regions(spec)
    if spec.kind in {"architecture", "workflow", "dataflow", "erd", "class", "tree", "lifecycle"}:
        _fit_canvas(spec)


def _fit_canvas(spec: Spec) -> None:
    """Encolhe a largura até a caixa real: canvas vazio derruba o preenchimento."""
    if not spec.nodes:
        return
    min_x = min(node.x for node in spec.nodes)
    shift = PAD - min_x
    if abs(shift) > 0.5:
        for node in spec.nodes:
            node.x += shift
        for region in spec.regions:
            region.x += shift
        for link in spec.links:
            link.points = [(x + shift, y) for x, y in link.points]
    max_x = max(node.x + node.w for node in spec.nodes)
    max_y = max(node.y + node.h for node in spec.nodes)
    for region in spec.regions:
        max_x = max(max_x, region.x + region.w)
        max_y = max(max_y, region.y + region.h)
    spec.width = max(720.0, max_x + PAD)
    spec.height = max(320.0, max_y + PAD)


def _frame_regions(spec: Spec) -> None:
    by_id = {node.id: node for node in spec.nodes}
    for region in spec.regions:
        if region.kind == "lane" and not region.members:
            region.members = [node.id for node in spec.nodes if node.row == region.row]
        elif region.kind == "stage" and not region.members:
            region.members = [node.id for node in spec.nodes if node.col == region.col]
        if region.kind in {"lane", "stage"} and region.w:
            continue
        if region.kind == "boundary":
            members = [by_id[member] for member in region.members if member in by_id]
            if not members:
                continue
            region.x = min(node.x for node in members) - 22
            region.y = min(node.y for node in members) - 30
            region.w = max(node.x + node.w for node in members) - region.x + 22
            region.h = max(node.y + node.h for node in members) - region.y + 20
        elif region.kind == "phase":
            members = [node for node in spec.nodes if node.col >= region.col]
            if not members:
                continue
            region.x = min(node.x for node in members) - 16
            region.y = HEADER - 34
            region.w = max(node.x + node.w for node in members) - region.x + 16
            region.h = spec.height - region.y - PAD + 4


# ------------------------------------------------------------- rotas

def _center(node: Node) -> tuple[float, float]:
    return node.x + node.w / 2, node.y + node.h / 2


def route_links(spec: Spec) -> None:
    by_id = {node.id: node for node in spec.nodes}
    for link in spec.links:
        if link.points:
            continue
        src = by_id.get(link.src)
        dst = by_id.get(link.dst)
        if not src or not dst:
            continue
        (sx, sy), (dx, dy) = _center(src), _center(dst)
        if spec.kind == "lifecycle":
            link.points = _lifecycle_route(src, dst)
            link.marked = True
            continue
        gap_x = dst.x - (src.x + src.w) if dst.x >= src.x else src.x - (dst.x + dst.w)
        gap_y = dst.y - (src.y + src.h) if dst.y >= src.y else src.y - (dst.y + dst.h)
        if gap_x >= gap_y:
            if dx >= sx:
                link.points = [(src.x + src.w, sy), (dst.x, sy)] if abs(sy - dy) < 6 else [
                    (src.x + src.w, sy), (src.x + src.w + 22, sy), (src.x + src.w + 22, dy), (dst.x, dy),
                ]
            else:
                link.points = [(src.x, sy), (dst.x + dst.w, sy)] if abs(sy - dy) < 6 else [
                    (src.x, sy), (src.x - 22, sy), (src.x - 22, dy), (dst.x + dst.w, dy),
                ]
        else:
            if dst.y >= src.y:
                link.points = [(sx, src.y + src.h), (sx, dst.y)] if abs(sx - dx) < 6 else [
                    (sx, src.y + src.h), (sx, src.y + src.h + 20), (dx, src.y + src.h + 20), (dx, dst.y),
                ]
            else:
                link.points = [(sx, src.y), (sx, dst.y + dst.h)] if abs(sx - dx) < 6 else [
                    (sx, src.y), (sx, src.y - 20), (dx, src.y - 20), (dx, dst.y + dst.h),
                ]
        link.marked = True


def _lifecycle_route(src: Node, dst: Node) -> list[tuple[float, float]]:
    """Corredor entre linhas: a linha anda no vazio e sobe na vertical do alvo."""
    sx, dx = src.x + src.w / 2, dst.x + dst.w / 2
    if src.row == dst.row:
        corridor = max(src.y, dst.y) + max(src.h, dst.h) + 16
        if abs(sx - dx) < 2:
            return [(sx, src.y + src.h), (sx, dst.y + dst.h)]
        return [(sx, src.y + src.h), (sx, corridor), (dx, corridor), (dx, dst.y + dst.h)]
    if dst.row > src.row:
        corridor = src.y + src.h + 20
        return [(sx, src.y + src.h), (sx, corridor), (dx, corridor), (dx, dst.y)]
    corridor = src.y - 20
    return [(sx, src.y), (sx, corridor), (dx, corridor), (dx, dst.y + dst.h)]


def _orthogonal(points: list[tuple[float, float]]) -> bool:
    return all(
        abs(points[index][0] - points[index + 1][0]) < 0.5 or abs(points[index][1] - points[index + 1][1]) < 0.5
        for index in range(len(points) - 1)
    )


def _segments(points: list[tuple[float, float]]) -> list[tuple[float, float, float, float]]:
    return [
        (points[index][0], points[index][1], points[index + 1][0], points[index + 1][1])
        for index in range(len(points) - 1)
    ]


def _crosses(a: tuple[float, float, float, float], b: tuple[float, float, float, float]) -> bool:
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    a_h = abs(ay1 - ay2) < 0.5
    b_h = abs(by1 - by2) < 0.5
    if a_h == b_h:
        return False
    if a_h:
        return (
            min(ax1, ax2) + 0.5 < bx1 < max(ax1, ax2) - 0.5
            and min(by1, by2) + 0.5 < ay1 < max(by1, by2) - 0.5
        )
    return (
        min(bx1, bx2) + 0.5 < ax1 < max(bx1, bx2) - 0.5
        and min(ay1, ay2) + 0.5 < by1 < max(ay1, ay2) - 0.5
    )


def _box_hit(segment: tuple[float, float, float, float], node: Node, inset: float = 5.0) -> bool:
    x1, y1, x2, y2 = segment
    left, right = node.x + inset, node.x + node.w - inset
    top, bottom = node.y + inset, node.y + node.h - inset
    if abs(y1 - y2) < 0.5:
        return top < y1 < bottom and min(x1, x2) < right and max(x1, x2) > left
    return left < x1 < right and min(y1, y2) < bottom and max(y1, y2) > top


def diagnose(spec: Spec) -> dict[str, Any]:
    by_id = {node.id: node for node in spec.nodes}
    crossings: list[str] = []
    collisions: list[str] = []
    tight_labels: list[str] = []
    for index, link in enumerate(spec.links):
        for other in spec.links[index + 1:]:
            if spec.kind == "sequence":
                break
            if {link.src, link.dst} & {other.src, other.dst}:
                continue
            if any(_crosses(a, b) for a in _segments(link.points) for b in _segments(other.points)):
                crossings.append(f"{link.src}→{link.dst} × {other.src}→{other.dst}")
        for node in spec.nodes:
            if node.id in {link.src, link.dst}:
                continue
            if any(_box_hit(segment, node) for segment in _segments(link.points)):
                collisions.append(f"{link.src}→{link.dst} sobre {node.id}")
                break
        if len(link.points) == 2 and abs(link.points[0][1] - link.points[1][1]) < 0.5 and link.label:
            gap = abs(link.points[1][0] - link.points[0][0])
            need = 6.5 * len(link.label) + 21
            if gap < need:
                tight_labels.append(f"{link.src}→{link.dst} ({gap:.0f}px de {need:.0f}px)")

    fanout: list[str] = []
    sides: dict[tuple[str, str], int] = {}
    for link in spec.links:
        src, dst = by_id.get(link.src), by_id.get(link.dst)
        if not src or not dst:
            continue
        if abs((src.y + src.h / 2) - (dst.y + dst.h / 2)) < 8:
            sides[(src.id, "direita" if dst.x > src.x else "esquerda")] = sides.get((src.id, "direita" if dst.x > src.x else "esquerda"), 0) + 1
            sides[(dst.id, "esquerda" if dst.x > src.x else "direita")] = sides.get((dst.id, "esquerda" if dst.x > src.x else "direita"), 0) + 1
        else:
            sides[(src.id, "baixo" if dst.y > src.y else "cima")] = sides.get((src.id, "baixo" if dst.y > src.y else "cima"), 0) + 1
            sides[(dst.id, "cima" if dst.y > src.y else "baixo")] = sides.get((dst.id, "cima" if dst.y > src.y else "baixo"), 0) + 1
    for (node_id, side), count in sides.items():
        if spec.kind in {"sequence", "waterfall"}:
            break
        node = by_id.get(node_id)
        if not node or count < 2:
            continue
        need = 32 + 14 * (count - 1)
        available = node.h if side in {"esquerda", "direita"} else node.w
        if available < need:
            fanout.append(f"{node_id}.{side}: {count} ligações em {available:.0f}px (mínimo {need:.0f}px)")

    overlap: list[str] = []
    nodes = spec.nodes
    for index, first in enumerate(nodes):
        for second in nodes[index + 1:]:
            if (
                first.x < second.x + second.w - 1 and second.x < first.x + first.w - 1
                and first.y < second.y + second.h - 1 and second.y < first.y + first.h - 1
            ):
                overlap.append(f"{first.id} × {second.id}")

    outside = [
        node.id for node in spec.nodes
        if node.x < 0 or node.y < 0 or node.x + node.w > spec.width + 1 or node.y + node.h > spec.height + 1
    ]
    if overlap:
        _issue(spec, "must", "sobreposicao", "Caixas sobrepostas", ", ".join(overlap[:4]),
               f"{len(overlap)} par(es).",
               "Dois nós no mesmo pixel escondem rótulo e aresta.",
               "Reduza o número de nós ou distribua em mais uma faixa.",
               "O desenho fica ilegível mesmo com o IR válido.")
    if collisions:
        _issue(spec, "should", "linha-atravessa-no", "Linha atravessa outro nó", ", ".join(collisions[:3]),
               f"{len(collisions)} rota(s).",
               "A linha passa por cima de uma caixa que não é ponta; o leitor lê uma conexão falsa.",
               "Mova a ponta que está fora do caminho principal para um corredor vazio.",
               "A topologia parece diferente da real.")
    if crossings:
        _issue(spec, "should", "cruzamento", "Cruzamentos de aresta", ", ".join(crossings[:3]),
               f"{len(crossings)} cruzamento(s).",
               "Cruzamento custa leitura; não custa verdade, mas perde a passada única.",
               "Reordene as colunas pela conexão real: vizinhos do caminho principal lado a lado.",
               "O leitor precisa seguir linha por linha.")
    if tight_labels:
        _issue(spec, "should", "folga-de-rotulo", "Folga insuficiente para o rótulo da aresta",
               ", ".join(tight_labels[:3]),
               f"{len(tight_labels)} rótulo(s).",
               "A folga mínima é 6,5 px por caractere mais 21 px; abaixo disso o texto encosta.",
               "Encurte o rótulo ou afaste as colunas que a relação atravessa.",
               "O rótulo colide com a borda da caixa.")
    if fanout:
        _issue(spec, "should", "leque", "Leque maior que a lateral do nó", ", ".join(fanout[:3]),
               f"{len(fanout)} lateral(is).",
               "Cada relação a mais na mesma lateral pede 14 px; sem isso as linhas se empilham.",
               "Distribua as pontas em dois lados ou alargue o nó central.",
               "As linhas saem do mesmo ponto e parecem uma só.")
    if outside:
        _issue(spec, "must", "fora-do-canvas", "Nó fora do canvas", ", ".join(outside[:4]),
               f"{len(outside)} nó(s).",
               "O SVG corta o que passa da viewBox.",
               "Recalcule a largura ou reduza o número de colunas.",
               "Parte do diagrama desaparece na entrega.")
    if spec.width > 1240 and not (spec.width <= 1790 and spec.width >= 1.55 * spec.height):
        _issue(spec, "should", "canvas-largo", "Canvas acima da largura legível", "viewBox",
               f"{spec.width:.0f} × {spec.height:.0f} px.",
               "Acima de 1240 px — ou 1790 px se o desenho for pelo menos 1,55× mais largo que alto — o texto cai abaixo do piso de leitura.",
               "Divida em dois diagramas ou reduza colunas.",
               "No desktop o texto fica menor que 8 px e a leitura falha.")

    width = max(1.0, spec.width)
    height = max(1.0, spec.height)
    bbox_w = max((node.x + node.w for node in spec.nodes), default=0) - min((node.x for node in spec.nodes), default=0)
    bbox_h = max((node.y + node.h for node in spec.nodes), default=0) - min((node.y for node in spec.nodes), default=0)
    metrics = {
        "largura": round(spec.width),
        "altura": round(spec.height),
        "nos": len(spec.nodes),
        "arestas": len(spec.links),
        "regioes": len(spec.regions),
        "cruzamentos": len(crossings),
        "colisoes": len(collisions),
        "sobreposicoes": len(overlap),
        "rotulosApertados": len(tight_labels),
        "leques": len(fanout),
        "preenchimento": round(100 * (bbox_w * bbox_h) / (width * height)) if spec.nodes else 0,
        "pisoDeTexto": 8.4,
        "orcamento": TYPES[spec.kind]["budget"],
    }
    spec.layout["metrics"] = metrics
    return metrics


def build(raw: dict[str, Any]) -> Spec:
    spec = read_spec(raw)
    validate_spec(spec)
    layout_spec(spec)
    route_links(spec)
    diagnose(spec)
    return spec


def build_from_text(text: str) -> Spec:
    payload = (text or "").strip()
    if not payload:
        raise DiagramError("Cole a especificação JSON do diagrama.")
    if len(payload) > MAX_SPEC_CHARS:
        raise DiagramError(f"A especificação passa de {MAX_SPEC_CHARS} caracteres.")
    if payload.startswith("```"):
        payload = re.sub(r"^```[a-zA-Z]*\s*\n?", "", payload)
        payload = re.sub(r"\n?```\s*$", "", payload)
    try:
        raw = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise DiagramError(f"JSON inválido na linha {exc.lineno}, coluna {exc.colno}: {exc.msg}.") from exc
    return build(raw)


# ------------------------------------------------------------- desenho

PRESETS: dict[str, dict[str, str]] = {
    "classico": {"label": "Clássico", "paper": "#ffffff", "ink": "#0f172a", "muted": "#64748b",
                 "line": "#94a3b8", "soft": "#f1f5f9", "grid": "transparent", "accent": "#2563eb"},
    "sinal": {"label": "Sinal", "paper": "#071018", "ink": "#e2e8f0", "muted": "#94a3b8",
              "line": "#38bdf8", "soft": "#0f1d2b", "grid": "transparent", "accent": "#38bdf8"},
    "planta": {"label": "Planta", "paper": "#0b1d2a", "ink": "#dbeafe", "muted": "#93c5fd",
               "line": "#60a5fa", "soft": "#0f2840", "grid": "#1e3a5f", "accent": "#60a5fa"},
    "editorial": {"label": "Editorial", "paper": "#fbf7ef", "ink": "#1b1917", "muted": "#78716c",
                  "line": "#a8a29e", "soft": "#f5efe3", "grid": "transparent", "accent": "#b45309"},
}
VARIANTS = {
    "default": ("Fluxo", "#64748b", "solid", 1.6),
    "emphasis": ("Principal", "#2563eb", "solid", 2.6),
    "security": ("Política", "#e11d48", "solid", 2.0),
    "dashed": ("Assíncrono", "#f59e0b", "dashed", 1.8),
    "return": ("Retorno", "#0d9488", "dashed", 1.4),
    "dependency": ("Dependência", "#94a3b8", "dashed", 1.4),
    "association": ("Associação", "#64748b", "solid", 1.6),
    "inheritance": ("Herança", "#7c3aed", "solid", 2.0),
    "realization": ("Realização", "#0891b2", "dashed", 1.8),
    "composition": ("Composição", "#e11d48", "solid", 2.0),
    "aggregation": ("Agregação", "#f59e0b", "solid", 1.8),
}
CARD_DOTS = {"cyan": "#22d3ee", "emerald": "#34d399", "violet": "#a78bfa",
             "amber": "#fbbf24", "rose": "#fb7185", "orange": "#fb923c", "slate": "#94a3b8"}


def _esc(value: Any) -> str:
    return html.escape(_text(value), quote=True)


def _variant_style(variant: str) -> tuple[str, str, float]:
    _, color, dash, width = VARIANTS.get(variant, VARIANTS["default"])
    return color, dash, width


def used_variants(spec: Spec) -> list[str]:
    seen: list[str] = []
    for link in spec.links:
        if link.variant not in seen:
            seen.append(link.variant)
    return seen


def legend_entries(spec: Spec) -> list[dict[str, str]]:
    if spec.legend == "oculta":
        return []
    variants = used_variants(spec)
    if spec.legend == "tudo":
        variants = list(VARIANTS)
    if not variants and spec.nodes:
        variants = ["default"]
    return [
        {
            "variante": variant,
            "rotulo": VARIANTS.get(variant, VARIANTS["default"])[0],
            "cor": VARIANTS.get(variant, VARIANTS["default"])[1],
            "traco": VARIANTS.get(variant, VARIANTS["default"])[2],
        }
        for variant in variants
    ]


def _marker(color: str, ident: str) -> str:
    return (
        f'<marker id="{ident}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" '
        f'orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" fill="{color}"/></marker>'
    )


def _svg(spec: Spec) -> str:
    theme = PRESETS[spec.preset]
    parts: list[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {spec.width:.0f} {spec.height:.0f}" '
        f'width="{spec.width:.0f}" height="{spec.height:.0f}" role="img" aria-label="{_esc(spec.title)}" '
        f'class="jarvis-diagram">',
        "<defs>",
    ]
    for variant in VARIANTS:
        color = VARIANTS[variant][1]
        parts.append(_marker(color, f"arw-{variant}"))
    if theme["grid"] != "transparent":
        parts.append(
            f'<pattern id="grade" width="24" height="24" patternUnits="userSpaceOnUse">'
            f'<path d="M24 0H0V24" fill="none" stroke="{theme["grid"]}" stroke-width="1"/></pattern>'
        )
    parts += [
        "</defs>",
        f'<rect width="{spec.width:.0f}" height="{spec.height:.0f}" fill="{theme["paper"]}"/>',
    ]
    if theme["grid"] != "transparent":
        parts.append(f'<rect width="{spec.width:.0f}" height="{spec.height:.0f}" fill="url(#grade)"/>')
    parts.append(
        f'<text x="{PAD:.0f}" y="38" fill="{theme["ink"]}" font-family="ui-sans-serif, system-ui, sans-serif" '
        f'font-size="19" font-weight="650">{_esc(spec.title)}</text>'
    )
    if spec.subtitle:
        parts.append(
            f'<text x="{PAD:.0f}" y="60" fill="{theme["muted"]}" font-family="ui-sans-serif, system-ui, sans-serif" '
            f'font-size="10.5">{_esc(spec.subtitle[:150])}</text>'
        )
    parts.append(
        f'<text x="{PAD:.0f}" y="{spec.height - 14:.0f}" fill="{theme["muted"]}" '
        f'font-family="ui-monospace, monospace" font-size="8.4">{_esc(spec.kind)} · '
        f'{_esc(PRESETS[spec.preset]["label"])} · JARVIS</text>'
    )
    for region in spec.regions:
        if region.w <= 0 or region.h <= 0:
            continue
        dash = "6 5" if region.kind in {"boundary", "phase"} else "2 6"
        fill = theme["soft"] if region.kind in {"lane", "stage"} else "none"
        parts.append(
            f'<g class="regiao"><rect x="{region.x:.1f}" y="{region.y:.1f}" width="{region.w:.1f}" '
            f'height="{region.h:.1f}" rx="10" fill="{fill}" fill-opacity="0.55" stroke="{theme["line"]}" '
            f'stroke-opacity="0.55" stroke-dasharray="{dash}"/>'
            f'<text x="{region.x + 12:.1f}" y="{region.y + 16:.1f}" fill="{theme["muted"]}" '
            f'font-family="ui-monospace, monospace" font-size="8.6" letter-spacing="0.06em">'
            f'{_esc(region.label.upper())}</text></g>'
        )
    for index, link in enumerate(spec.links):
        if not link.points:
            continue
        color, dash, width = _variant_style(link.variant)
        path = " ".join(f"{x:.1f},{y:.1f}" for x, y in link.points)
        dash_attr = ' stroke-dasharray="5 4"' if dash == "dashed" else (" stroke-dasharray=\"4 4\"" if dash != "solid" else "")
        parts.append(
            f'<g class="liga"><polyline points="{path}" fill="none" stroke="{color}" stroke-width="{width}"'
            f'{dash_attr} marker-end="url(#arw-{link.variant if link.variant in VARIANTS else "default"})" '
            f'stroke-linejoin="round" stroke-linecap="round"/>'
        )
        if link.label:
            lx = sum(point[0] for point in link.points) / len(link.points)
            ly = sum(point[1] for point in link.points) / len(link.points)
            box = 5.1 * len(link.label) + 10
            parts.append(
                f'<rect x="{lx - box / 2:.1f}" y="{ly - 7:.1f}" width="{box:.1f}" height="13" rx="3" '
                f'fill="{theme["paper"]}" fill-opacity="0.92"/>'
                f'<text x="{lx:.1f}" y="{ly + 3:.1f}" text-anchor="middle" fill="{theme["muted"]}" '
                f'font-family="ui-sans-serif, system-ui, sans-serif" font-size="8.4">{_esc(link.label)}</text>'
                f'</g>'
            )
        else:
            parts.append("</g>")
    if spec.kind == "sequence":
        parts += _sequence_decor(spec, theme)
    if spec.kind == "timeline":
        parts += _timeline_decor(spec, theme)
    for node in spec.nodes:
        parts.append(_svg_node(spec, node, theme))
    parts.append("</svg>")
    return "".join(parts)


def _sequence_decor(spec: Spec, theme: dict[str, str]) -> list[str]:
    axis = spec.layout.get("axis", {})
    top = _num(axis.get("top"), HEADER + 84)
    bottom = _num(axis.get("bottom"), spec.height - 60)
    parts: list[str] = []
    for node in spec.nodes:
        x = node.x + node.w / 2
        parts.append(
            f'<line x1="{x:.1f}" y1="{top:.1f}" x2="{x:.1f}" y2="{bottom:.1f}" stroke="{theme["line"]}" '
            f'stroke-opacity="0.45" stroke-dasharray="3 6" stroke-width="1.2"/>'
        )
    return parts


def _timeline_decor(spec: Spec, theme: dict[str, str]) -> list[str]:
    axis = spec.layout.get("time_axis")
    if not axis:
        return []
    y = HEADER + 46
    parts = [
        f'<line x1="{axis["left"]:.0f}" y1="{y:.0f}" x2="{axis["left"] + axis["width"]:.0f}" y2="{y:.0f}" '
        f'stroke="{theme["line"]}" stroke-width="1.4"/>'
    ]
    for node in spec.nodes:
        parts.append(
            f'<line x1="{node.x:.1f}" y1="{y:.1f}" x2="{node.x:.1f}" y2="{node.y:.1f}" '
            f'stroke="{node.color}" stroke-width="1.6"/>'
            f'<circle cx="{node.x:.1f}" cy="{y:.1f}" r="4.6" fill="{node.color}" stroke="{theme["paper"]}" stroke-width="1.6"/>'
        )
    if spec.nodes:
        first = _parse_time(spec.nodes[0].at)
        last = _parse_time(spec.nodes[-1].at)
        if first and last:
            parts.append(
                f'<text x="{axis["left"]:.0f}" y="{y - 12:.0f}" fill="{theme["muted"]}" '
                f'font-family="ui-monospace, monospace" font-size="8.4">{_esc(first.strftime("%d/%m %H:%M"))}</text>'
                f'<text x="{axis["left"] + axis["width"]:.0f}" y="{y - 12:.0f}" text-anchor="end" '
                f'fill="{theme["muted"]}" font-family="ui-monospace, monospace" font-size="8.4">'
                f'{_esc(last.strftime("%d/%m %H:%M"))}</text>'
            )
    return parts


def _svg_node(spec: Spec, node: Node, theme: dict[str, str]) -> str:
    if spec.kind == "waterfall":
        return _waterfall_node(spec, node, theme)
    ink = theme["ink"]
    parts = [
        f'<g class="no" data-id="{_esc(node.id)}">',
        f'<rect x="{node.x:.1f}" y="{node.y:.1f}" width="{node.w:.1f}" height="{node.h:.1f}" rx="9" '
        f'fill="{theme["paper"]}" stroke="{node.color}" stroke-width="1.4"/>',
        f'<rect x="{node.x:.1f}" y="{node.y:.1f}" width="4" height="{node.h:.1f}" rx="2" fill="{node.color}"/>',
        f'<text x="{node.x + 14:.1f}" y="{node.y + 21:.1f}" fill="{ink}" '
        f'font-family="ui-sans-serif, system-ui, sans-serif" font-size="11.4" font-weight="600">'
        f'{_esc(node.label)}</text>',
    ]
    if node.sublabel:
        parts.append(
            f'<text x="{node.x + 14:.1f}" y="{node.y + 35:.1f}" fill="{theme["muted"]}" '
            f'font-family="ui-sans-serif, system-ui, sans-serif" font-size="9.2">{_esc(node.sublabel)}</text>'
        )
    if node.tag:
        box = 5.4 * len(node.tag) + 12
        parts.append(
            f'<rect x="{node.x + node.w - box - 8:.1f}" y="{node.y + 8:.1f}" width="{box:.1f}" height="14" '
            f'rx="7" fill="{node.color}" fill-opacity="0.16"/>'
            f'<text x="{node.x + node.w - box / 2 - 8:.1f}" y="{node.y + 18:.1f}" text-anchor="middle" '
            f'fill="{node.color}" font-family="ui-monospace, monospace" font-size="7.8">{_esc(node.tag)}</text>'
        )
    for index, member in enumerate(node.members[:8]):
        parts.append(
            f'<text x="{node.x + 14:.1f}" y="{node.y + 50 + index * 13:.1f}" fill="{theme["muted"]}" '
            f'font-family="ui-monospace, monospace" font-size="8.8">{_esc(member[:40])}</text>'
        )
    parts.append("</g>")
    return "".join(parts)


def _waterfall_node(spec: Spec, node: Node, theme: dict[str, str]) -> str:
    label_x = PAD + node.depth * 18
    bar_w = max(3.0, node.w)
    duration = node.end - node.start
    readable = f"{duration:.0f} {spec.unit}" if duration else spec.unit
    return (
        f'<g class="no" data-id="{_esc(node.id)}">'
        f'<text x="{label_x:.1f}" y="{node.y + 15:.1f}" fill="{theme["ink"]}" '
        f'font-family="ui-sans-serif, system-ui, sans-serif" font-size="9.8">{_esc(node.label)}</text>'
        f'<text x="{label_x:.1f}" y="{node.y + 27:.1f}" fill="{theme["muted"]}" '
        f'font-family="ui-monospace, monospace" font-size="7.8">{_esc(node.sublabel)}</text>'
        f'<rect x="{node.x:.1f}" y="{node.y:.1f}" width="{bar_w:.1f}" height="{node.h:.1f}" rx="4" '
        f'fill="{node.color}" fill-opacity="0.82"/>'
        f'<text x="{node.x + bar_w + 8:.1f}" y="{node.y + 14:.1f}" fill="{theme["muted"]}" '
        f'font-family="ui-monospace, monospace" font-size="8.2">{_esc(readable)}</text>'
        f'</g>'
    )


def _legend_html(spec: Spec) -> str:
    entries = legend_entries(spec)
    if not entries:
        return ""
    chips = "".join(
        f'<li><span class="traco" style="--cor:{entry["cor"]};'
        f'{"border-top-style:dashed;" if entry["traco"] != "solid" else ""}"></span>{_esc(entry["rotulo"])}</li>'
        for entry in entries
    )
    return f'<ul class="legenda" aria-label="Legenda">{chips}</ul>'


def _cards_html(spec: Spec) -> str:
    if not spec.cards:
        return ""
    cards = []
    for card in spec.cards:
        color = CARD_DOTS.get(card.dot, CARD_DOTS["slate"])
        items = "".join(f"<li>{_esc(item)}</li>" for item in card.items)
        cards.append(
            f'<article class="cartao" style="--dot:{color}"><h3>{_esc(card.title)}</h3><ul>{items}</ul></article>'
        )
    return f'<section class="cartoes">{ "".join(cards) }</section>'


def render_html(spec: Spec) -> str:
    theme = PRESETS[spec.preset]
    animation = spec.animation == "traco"
    tipo = TYPES[spec.kind]["label"]
    chips = [
        f"<span>{_esc(tipo)}</span>",
        f"<span>{_esc(PRESETS[spec.preset]['label'])}</span>",
        f"<span>{_esc(spec.locale)}</span>",
    ]
    if spec.quality == "vitrine":
        chips.append("<span>vitrine</span>")
    if spec.evidence:
        chips.append(f"<span>{_esc(spec.evidence)}</span>")
    motion = (
        "<style>.no,.liga,.regiao{opacity:0;animation:entra .5s ease forwards}"
        ".no{animation-delay:calc(var(--i,0)*40ms)}.liga{animation-delay:.18s}"
        "@keyframes entra{to{opacity:1}}"
        "@media (prefers-reduced-motion: reduce){.no,.liga,.regiao{animation:none;opacity:1}}</style>"
        if animation
        else ""
    )
    return f"""<!DOCTYPE html>
<html lang="{_esc(spec.locale.split('-')[0] or 'pt')}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_esc(spec.title)}</title>
<style>
  :root{{--paper:{theme['paper']};--ink:{theme['ink']};--muted:{theme['muted']};--line:{theme['line']};--soft:{theme['soft']};--accent:{theme['accent']};}}
  *{{box-sizing:border-box}}
  body{{margin:0;background:var(--paper);color:var(--ink);font-family:ui-sans-serif,system-ui,-apple-system,"Segoe UI",sans-serif;}}
  .folha{{max-width:1240px;margin:0 auto;padding:36px 28px 48px}}
  header .tipo{{font-family:ui-monospace,monospace;font-size:11px;letter-spacing:.14em;text-transform:uppercase;color:var(--accent)}}
  header h1{{font-size:clamp(22px,3.2vw,32px);line-height:1.15;margin:10px 0 8px;letter-spacing:-.02em}}
  header p{{margin:0 0 14px;color:var(--muted);font-size:15px;max-width:72ch}}
  .selos{{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:22px}}
  .selos span{{font-family:ui-monospace,monospace;font-size:10px;padding:3px 9px;border:1px solid var(--line);border-radius:999px;color:var(--muted)}}
  .desenho{{border:1px solid var(--line);border-radius:14px;overflow-x:auto;background:var(--paper)}}
  .desenho svg{{display:block;max-width:100%;height:auto;margin:0 auto}}
  .legenda{{list-style:none;display:flex;gap:18px;flex-wrap:wrap;padding:0;margin:18px 0 0;font-size:12.5px;color:var(--muted)}}
  .legenda li{{display:flex;align-items:center;gap:8px}}
  .traco{{width:26px;height:0;border-top:2px solid var(--cor)}}
  .cartoes{{display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:14px;margin-top:26px}}
  .cartao{{border:1px solid var(--line);border-radius:12px;padding:16px 18px;background:var(--soft)}}
  .cartao h3{{margin:0 0 8px;font-size:13px;display:flex;align-items:center;gap:8px}}
  .cartao h3::before{{content:"";width:7px;height:7px;border-radius:50%;background:var(--dot)}}
  .cartao ul{{margin:0;padding-left:16px;color:var(--muted);font-size:12.5px;line-height:1.5}}
  footer{{margin-top:32px;padding-top:14px;border-top:1px solid var(--line);display:flex;gap:14px;justify-content:space-between;flex-wrap:wrap;color:var(--muted);font-size:11px;font-family:ui-monospace,monospace}}
  @media print{{.folha{{max-width:none;padding:12px}} .desenho{{border:none}}}}
</style>
{motion}
</head>
<body>
<div class="folha">
  <header>
    <div class="tipo">{_esc(tipo)} · JARVIS diagramas</div>
    <h1>{_esc(spec.title)}</h1>
    {f"<p>{_esc(spec.subtitle)}</p>" if spec.subtitle else ""}
    <div class="selos">{ "".join(chips) }</div>
  </header>
  <div class="desenho">{_svg(spec)}</div>
  {_legend_html(spec)}
  {_cards_html(spec)}
  <footer><span>{_esc(spec.output or 'diagrama.html')}</span><span>SVG inline · sem runtime · abra sem servidor</span></footer>
</div>
</body>
</html>
"""


def render_svg(spec: Spec) -> str:
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + _svg(spec)


def _mermaid_id(value: str) -> str:
    clean = re.sub(r"[^A-Za-z0-9_]", "_", value)
    return clean if clean and not clean[0].isdigit() else f"n_{clean}"


def render_mermaid(spec: Spec) -> str:
    lines: list[str] = []
    if spec.kind in {"architecture", "workflow", "dataflow"}:
        direction = "LR" if spec.kind != "tree" else "TD"
        lines.append(f"flowchart {direction}")
        members: dict[str, list[str]] = {}
        for region in spec.regions:
            if region.kind in {"boundary", "lane", "stage"} and region.members:
                members[region.id] = region.members
        used: set[str] = set()
        for region in spec.regions:
            ids = members.get(region.id, [])
            if not ids:
                continue
            lines.append(f'  subgraph {region.id}["{region.label}"]')
            for node in spec.nodes:
                if node.id in ids:
                    used.add(node.id)
                    lines.append(f"    {_mermaid_id(node.id)}[\"{node.label}\"]")
            lines.append("  end")
        for node in spec.nodes:
            if node.id not in used:
                lines.append(f"  {_mermaid_id(node.id)}[\"{node.label}\"]")
        for link in spec.links:
            arrow = "-->" if link.variant in {"default", "emphasis"} else "-.->"
            label = f"|{link.label}|" if link.label else ""
            lines.append(f"  {_mermaid_id(link.src)} {arrow}{label} {_mermaid_id(link.dst)}")
    elif spec.kind == "sequence":
        lines.append("sequenceDiagram")
        lines.append("  autonumber")
        for node in spec.nodes:
            lines.append(f"  participant {_mermaid_id(node.id)} as {node.label}")
        for link in spec.links:
            arrow = "-->>" if link.variant in {"dashed", "return"} else "->>"
            lines.append(f"  {_mermaid_id(link.src)}{arrow}{_mermaid_id(link.dst)}: {link.label or 'chamada'}")
    elif spec.kind == "lifecycle":
        lines.append("stateDiagram-v2")
        lines.append("  direction LR")
        for node in spec.nodes:
            lines.append(f'  state "{node.label}" as {_mermaid_id(node.id)}')
        for link in spec.links:
            label = f" : {link.label}" if link.label else ""
            lines.append(f"  {_mermaid_id(link.src)} --> {_mermaid_id(link.dst)}{label}")
    elif spec.kind == "erd":
        lines.append("erDiagram")
        for node in spec.nodes:
            lines.append(f"  {_mermaid_id(node.id).upper()} {{")
            for member in node.members:
                pieces = [piece for piece in member.replace("PK", " ").replace("UK", " ").replace("FK", " ").split() if piece]
                name = pieces[0] if pieces else "campo"
                atype = pieces[1] if len(pieces) > 1 else "texto"
                name = re.sub(r"[^A-Za-z0-9_]", "_", name)
                atype = re.sub(r"[^A-Za-z0-9_]", "_", atype)
                lines.append(f"    {atype} {name}")
            lines.append("  }")
        for link in spec.links:
            lines.append(
                f'  {_mermaid_id(link.src).upper()} ||--o{{ {_mermaid_id(link.dst).upper()} : "{link.label}"'
            )
    elif spec.kind == "tree":
        lines.append("flowchart TD")
        for node in spec.nodes:
            lines.append(f"  {_mermaid_id(node.id)}[\"{node.label}\"]")
        for node in spec.nodes:
            if node.parent:
                lines.append(f"  {_mermaid_id(node.parent)} --> {_mermaid_id(node.id)}")
    elif spec.kind == "class":
        lines.append("classDiagram")
        for node in spec.nodes:
            stereotype = {"interface": "<<interface>>", "abstract": "<<abstract>>", "enum": "<<enum>>", "record": "<<record>>"}.get(node.kind, "")
            lines.append(f"  class {_mermaid_id(node.id)} {{")
            if stereotype:
                lines.append(f"    {stereotype}")
            for member in node.members:
                lines.append(f"    {re.sub(r'[{}]', '', member)}")
            lines.append("  }")
        for link in spec.links:
            arrow = {
                "inheritance": "<|--", "realization": "<|..", "composition": "*--",
                "aggregation": "o--", "dependency": "..>", "association": "-->",
            }.get(link.variant, "-->")
            lines.append(f"  {_mermaid_id(link.src)} {arrow} {_mermaid_id(link.dst)}")
    elif spec.kind == "timeline":
        lines.append("timeline")
        lines.append(f"  title {spec.title}")
        for region in [region for region in spec.regions if region.kind == "lane"]:
            lines.append(f"  section {region.label}")
            for node in spec.nodes:
                if node.row == region.row:
                    when = _parse_time(node.at)
                    stamp = when.strftime("%d/%m %H:%M") if when else "?"
                    lines.append(f"    {stamp} : {node.label}")
        if not spec.regions:
            for node in spec.nodes:
                lines.append(f"    {node.at[:16]} : {node.label}")
    elif spec.kind == "waterfall":
        base = datetime(1970, 1, 1)
        lines.append("gantt")
        lines.append("  dateFormat YYYY-MM-DD HH:mm:ss")
        lines.append("  axisFormat %S")
        lines.append(f"  title {spec.title}")
        for node in spec.nodes:
            start = (base.timestamp() + node.start / 1000)
            end = (base.timestamp() + node.end / 1000)
            fmt = "%Y-%m-%d %H:%M:%S"
            lines.append(
                f"  {node.label.replace(':', ' ')} :{node.kind}, {_mermaid_id(node.id)}, "
                f"{datetime.fromtimestamp(start).strftime(fmt)}, {datetime.fromtimestamp(end).strftime(fmt)}"
            )
    return "\n".join(lines) + "\n"


def render_ascii(spec: Spec) -> str:
    lines: list[str] = [spec.title.upper(), "=" * max(8, min(len(spec.title), 64))]
    if spec.subtitle:
        lines.append(spec.subtitle)
    lines.append("")
    by_id = {node.id: node for node in spec.nodes}
    if spec.kind == "sequence":
        for index, link in enumerate(spec.links, start=1):
            src, dst = by_id.get(link.src), by_id.get(link.dst)
            lines.append(
                f"{index:02d}. {(src.label if src else link.src):<18} -> {(dst.label if dst else link.dst):<18} {link.label}"
            )
    elif spec.kind == "waterfall":
        end = max((node.end for node in spec.nodes), default=1)
        for node in spec.nodes:
            start_at = int(node.start / end * 34)
            length = max(1, int((node.end - node.start) / end * 34))
            lines.append(
                f"{'  ' * node.depth}{node.label[:24]:<24} {' ' * start_at}{'#' * length} "
                f"{node.end - node.start:.0f} {spec.unit}"
            )
    elif spec.kind == "timeline":
        for node in sorted(spec.nodes, key=lambda item: item.at):
            when = _parse_time(node.at)
            stamp = when.strftime("%d/%m %H:%M") if when else node.at
            lines.append(f"{stamp}  [{node.tag or 'evento':<10}] {node.label}")
    elif spec.kind == "tree":
        def walk(node: Node, prefix: str, last: bool) -> None:
            lines.append(f"{prefix}{'└── ' if last else '├── '}{node.label}")
            kids = [item for item in spec.nodes if item.parent == node.id]
            for index, kid in enumerate(kids):
                walk(kid, prefix + ("    " if last else "│   "), index == len(kids) - 1)

        roots = [node for node in spec.nodes if not node.parent]
        for root in roots:
            walk(root, "", True)
    else:
        rows: dict[int, list[Node]] = {}
        for node in spec.nodes:
            rows.setdefault(node.row, []).append(node)
        for row in sorted(rows):
            names = "  ".join(node.label for node in rows[row])
            lines.append(f"[{row:02d}] {names}")
        lines.append("")
        for link in spec.links:
            src, dst = by_id.get(link.src), by_id.get(link.dst)
            if not src or not dst:
                continue
            arrow = "-->" if link.variant in {"default", "emphasis"} else "-.->"
            label = f"  ({link.label})" if link.label else ""
            lines.append(f"{src.label} {arrow} {dst.label}{label}")
    if spec.cards:
        lines.append("")
        for card in spec.cards:
            lines.append(f"* {card.title}")
            lines += [f"  - {item}" for item in card.items]
    return "\n".join(lines) + "\n"


def render_dot(spec: Spec) -> str:
    lines = [f'digraph "{spec.title}" {{', "  graph [rankdir=LR, fontname=\"Helvetica\"];", '  node [shape=box, style="rounded"];']
    for region in spec.regions:
        if region.kind in {"boundary", "lane", "stage"} and region.members:
            lines.append(f'  subgraph cluster_{region.id} {{ label="{region.label}";')
            for member in region.members:
                if any(node.id == member for node in spec.nodes):
                    lines.append(f"    {member};")
            lines.append("  }")
    for node in spec.nodes:
        lines.append(
            f'  {node.id} [label="{node.label}", color="{node.color}"];'
        )
    for link in spec.links:
        style = "dashed" if link.variant in {"dashed", "return", "dependency", "realization"} else "solid"
        lines.append(f'  {link.src} -> {link.dst} [label="{link.label}", style={style}];')
    lines.append("}")
    return "\n".join(lines) + "\n"


FORMATS = {"html": "HTML autocontido", "svg": "SVG", "mermaid": "Mermaid", "ascii": "Texto", "dot": "Graphviz DOT"}


def render(spec: Spec, fmt: str) -> str:
    key = _norm(fmt)
    if key not in FORMATS:
        raise DiagramError("Formato inválido: use html, svg, mermaid, ascii ou dot.")
    if key == "html":
        return render_html(spec)
    if key == "svg":
        return render_svg(spec)
    if key == "mermaid":
        return render_mermaid(spec)
    if key == "ascii":
        return render_ascii(spec)
    return render_dot(spec)


# --------------------------------------------------------------- skills

def _as_json(spec: Spec) -> dict[str, Any]:
    """IR normalizado em PT-BR, para copiar de volta e reproduzir."""
    data: dict[str, Any] = {
        "tipo": spec.kind,
        "titulo": spec.title,
        "subtitulo": spec.subtitle,
        "saida": spec.output or f"{_slug(spec.title)}.html",
        "idioma": spec.locale,
        "animacao": spec.animation,
        "preset": spec.preset,
        "qualidade": spec.quality,
        "legenda": spec.legend,
    }
    if spec.evidence:
        data["evidencia"] = spec.evidence
    key = TYPES[spec.kind]["arrays"][0]
    nodes: list[dict[str, Any]] = []
    for node in spec.nodes:
        item: dict[str, Any] = {"id": node.id, "rotulo": node.label}
        if node.sublabel:
            item["subrotulo"] = node.sublabel
        if node.kind:
            item["tipo"] = node.kind
        if node.tag:
            item["etiqueta"] = node.tag
        if node.members:
            item["atributos" if spec.kind in {"erd", "class"} else "membros"] = node.members
        if spec.kind in {"workflow", "erd", "class"}:
            item["linha"] = node.row
            item["coluna"] = node.col
        if spec.kind == "dataflow":
            item["estagio"] = node.col
            item["linha"] = node.row
        if spec.kind == "tree" and node.parent:
            item["pai"] = node.parent
        if spec.kind == "timeline":
            item["quando"] = node.at
            lane = next((region for region in spec.regions if region.row == node.row and region.kind == "lane"), None)
            if lane:
                item["raia"] = lane.id
        if spec.kind == "waterfall":
            item["inicio"] = node.start
            item["fim"] = node.end
            if node.parent:
                item["pai"] = node.parent
        nodes.append(item)
    data[key] = nodes
    if spec.links:
        links: list[dict[str, Any]] = []
        for link in spec.links:
            item = {"de": link.src, "para": link.dst}
            if link.label:
                item["rotulo"] = link.label
            if link.variant != "default":
                item["variante"] = link.variant
            links.append(item)
        target = {
            "architecture": "conexoes", "workflow": "conexoes", "dataflow": "fluxos",
            "lifecycle": "transicoes", "erd": "relacionamentos", "class": "relacionamentos",
            "sequence": "mensagens",
        }.get(spec.kind, "")
        if target:
            data[target] = links
    if spec.cards:
        data["cartoes"] = [{"cor": card.dot, "titulo": card.title, "itens": card.items} for card in spec.cards]
    return data


def _skeleton(kind: str) -> dict[str, Any]:
    titulo = f"Exemplo de {TYPES[kind]['label'].lower()}"
    base: dict[str, Any] = {
        "tipo": kind, "titulo": titulo, "subtitulo": "Troque os nós pelos fatos reais.",
        "saida": "diagrama.html", "idioma": "pt-BR", "legenda": "auto",
    }
    if kind == "architecture":
        base["componentes"] = [
            {"id": "app", "rotulo": "Aplicativo", "tipo": "frontend", "subrotulo": "interface do usuário"},
            {"id": "api", "rotulo": "API", "tipo": "backend", "subrotulo": "regras do domínio"},
            {"id": "db", "rotulo": "Banco", "tipo": "database", "subrotulo": "fonte da verdade"},
        ]
        base["conexoes"] = [{"de": "app", "para": "api", "rotulo": "HTTPS"}, {"de": "api", "para": "db", "rotulo": "SQL"}]
    elif kind == "workflow":
        base["raias"] = [{"id": "pessoa", "rotulo": "Pessoa"}, {"id": "sistema", "rotulo": "Sistema"}]
        base["etapas"] = [
            {"id": "pedido", "rotulo": "Abre pedido", "raia": "pessoa", "coluna": 0},
            {"id": "checagem", "rotulo": "Checa dados", "raia": "sistema", "coluna": 1},
            {"id": "aprovacao", "rotulo": "Aprova", "raia": "pessoa", "coluna": 2},
        ]
        base["conexoes"] = [
            {"de": "pedido", "para": "checagem", "rotulo": "envia"},
            {"de": "checagem", "para": "aprovacao", "rotulo": "devolve"},
        ]
    elif kind == "sequence":
        base["participantes"] = [
            {"id": "app", "rotulo": "Aplicativo", "tipo": "frontend"},
            {"id": "api", "rotulo": "API", "tipo": "backend"},
            {"id": "db", "rotulo": "Banco", "tipo": "database"},
        ]
        base["mensagens"] = [
            {"de": "app", "para": "api", "rotulo": "GET /pedido"},
            {"de": "api", "para": "db", "rotulo": "SELECT"},
            {"de": "db", "para": "api", "rotulo": "linhas", "variante": "dashed"},
            {"de": "api", "para": "app", "rotulo": "200 OK", "variante": "dashed"},
        ]
    elif kind == "dataflow":
        base["estagios"] = [{"rotulo": "Origem"}, {"rotulo": "Processo"}, {"rotulo": "Destino"}]
        base["elementos"] = [
            {"id": "app", "rotulo": "App", "tipo": "frontend", "estagio": 0, "linha": 0},
            {"id": "fila", "rotulo": "Fila", "tipo": "messagebus", "estagio": 1, "linha": 0},
            {"id": "dw", "rotulo": "Armazém", "tipo": "database", "estagio": 2, "linha": 0},
        ]
        base["fluxos"] = [
            {"de": "app", "para": "fila", "rotulo": "evento"},
            {"de": "fila", "para": "dw", "rotulo": "lote"},
        ]
    elif kind == "lifecycle":
        base["caminhoPrincipal"] = ["rascunho", "revisao", "publicado"]
        base["estados"] = [
            {"id": "rascunho", "rotulo": "Rascunho", "tipo": "start"},
            {"id": "revisao", "rotulo": "Em revisão", "tipo": "waiting"},
            {"id": "publicado", "rotulo": "Publicado", "tipo": "success"},
            {"id": "recusado", "rotulo": "Recusado", "tipo": "failure"},
        ]
        base["transicoes"] = [
            {"de": "rascunho", "para": "revisao", "rotulo": "envia"},
            {"de": "revisao", "para": "publicado", "rotulo": "aprova"},
            {"de": "revisao", "para": "recusado", "rotulo": "recusa"},
        ]
    elif kind == "erd":
        base["entidades"] = [
            {"id": "cliente", "rotulo": "cliente", "linha": 0, "coluna": 0,
             "atributos": [{"nome": "id", "tipo": "bigint", "chave": "pk"}, {"nome": "email", "tipo": "texto", "chave": "uk"}]},
            {"id": "pedido", "rotulo": "pedido", "linha": 0, "coluna": 1,
             "atributos": [{"nome": "id", "tipo": "bigint", "chave": "pk"}, {"nome": "cliente_id", "tipo": "bigint", "chave": "fk"}]},
        ]
        base["relacionamentos"] = [
            {"de": "pedido", "para": "cliente", "rotulo": "feito por", "cardinalidadeDe": "many", "cardinalidadePara": "one"}
        ]
    elif kind == "tree":
        base["nos"] = [
            {"id": "raiz", "rotulo": "Produto"},
            {"id": "conta", "rotulo": "Conta", "pai": "raiz"},
            {"id": "cobranca", "rotulo": "Cobrança", "pai": "raiz"},
        ]
    elif kind == "class":
        base["tipos"] = [
            {"id": "servico", "rotulo": "Servico", "tipo": "class", "linha": 0, "coluna": 0,
             "metodos": [{"nome": "executar", "parametros": "entrada: Dados", "retorno": "Saida"}]},
            {"id": "porta", "rotulo": "Porta", "tipo": "interface", "linha": 0, "coluna": 1},
        ]
        base["relacionamentos"] = [{"de": "servico", "para": "porta", "tipo": "dependency"}]
    elif kind == "timeline":
        base["raias"] = [{"id": "produto", "rotulo": "Produto"}, {"id": "resposta", "rotulo": "Resposta"}]
        base["eventos"] = [
            {"id": "deploy", "quando": "2026-10-01T10:00:00-03:00", "titulo": "Deploy", "raia": "produto", "tipo": "change"},
            {"id": "erro", "quando": "2026-10-01T10:14:00-03:00", "titulo": "Erro em dobro", "raia": "produto", "tipo": "alert"},
            {"id": "rollback", "quando": "2026-10-01T10:21:00-03:00", "titulo": "Rollback", "raia": "resposta", "tipo": "recovery"},
        ]
    else:
        base["unidade"] = "ms"
        base["trechos"] = [
            {"id": "req", "nome": "POST /checkout", "inicio": 0, "fim": 1200},
            {"id": "db", "nome": "consulta", "inicio": 100, "fim": 420, "pai": "req"},
            {"id": "pgto", "nome": "cobrança", "inicio": 430, "fim": 1100, "pai": "req"},
        ]
    return base


def _metrics_of(spec: Spec) -> dict[str, Any]:
    return spec.layout.get("metrics", {})


def _questions_for(spec: Spec) -> list[str]:
    questions = [
        "Qual pergunta o leitor precisa responder olhando o desenho?",
        "Qual é o caminho principal e qual é a ramificação secundária?",
    ]
    if spec.kind in {"architecture", "dataflow"}:
        questions.append("Cada seta tem protocolo, direção e condição declarados?")
    if spec.kind in {"lifecycle", "workflow"}:
        questions.append("Existe falha recuperável com transição de volta desenhada?")
    return questions


def _limitations(spec: Spec | None = None) -> list[str]:
    items = [
        "Não abre navegador, não mede texto renderizado e não tira captura: o piso de 8,4 px é uma estimativa de projeto.",
        "Não lê repositório nem código-fonte: a verdade do desenho é a especificação que você colou.",
        "Não renderiza Mermaid nem Graphviz: exporta texto nesses formatos para outra ferramenta abrir.",
        "Não persiste arquivo: o HTML volta no corpo da resposta para você salvar.",
    ]
    if spec is not None and spec.kind == "waterfall":
        items.append("A escala da cascata é declarada, não medida em produção.")
    return items


def diagram_type(*, pedido: str, plateia: str = "", detalhe: str = "resumo", seed: str = "") -> dict[str, Any]:
    _mode("full")
    text = _norm(pedido)
    if len(text) < 3:
        raise DiagramError("Descreva o que precisa ser explicado em uma frase.")
    if len(pedido) > 4_000:
        raise DiagramError("O pedido passa de 4 000 caracteres.")

    scores = {}
    hits: dict[str, list[str]] = {}
    for kind, signals in PLAN_SIGNALS.items():
        found = [signal for signal in signals if signal in text]
        hits[kind] = found
        scores[kind] = len(found) * 2 + (3 if _norm(TYPES[kind]["label"]) in text else 0)
    ranked = sorted(scores.items(), key=lambda item: (-item[1], list(TYPES).index(item[0])))
    best_score = ranked[0][1]
    winners = [kind for kind, score in ranked if score == best_score]
    kind = winners[0]
    if len(winners) > 1:
        preferences = (
            ("tree", ("pasta", "estrutura", "hierarquia", "modulo", "diretorio", "decomposicao")),
            ("sequence", ("chamada", "requisicao", "request", "handshake", "protocolo")),
            ("lifecycle", ("estado", "status", "transicao", "retry", "retentativa")),
            ("erd", ("tabela", "coluna", "chave", "cardinalidade")),
            ("timeline", ("quando", "incidente", "historico", "cronologia")),
            ("waterfall", ("duracao", "latencia", "gargalo", "demora", "lento")),
            ("dataflow", ("pipeline", "etl", "linhagem", "evento", "stream")),
            ("workflow", ("processo", "etapa", "aprovacao", "runbook")),
        )
        for candidate, terms in preferences:
            if candidate in winners and any(term in text for term in terms):
                kind = candidate
                break

    findings: list[dict[str, Any]] = []
    if best_score == 0:
        findings.append(finding(
            "should", "sem-sinal", "Pedido sem sinal de tipo", pedido[:60],
            "Nenhuma palavra do pedido casa com o vocabulário dos dez tipos.",
            "Sem sinal, o roteador escolhe pela ordem do catálogo e pode errar a pergunta.",
            "Diga o que o desenho precisa mostrar: componentes, estados, chamadas, dados, tabelas, tempo.",
            "A escolha sai plausível, mas não justificada pelo pedido.",
        ))
    if len(winners) > 1:
        findings.append(finding(
            "should", "ambiguidade", "Mais de um tipo cabe no pedido", ", ".join(winners[:3]),
            f"Empate em {best_score} ponto(s): {', '.join(TYPES[item]['label'] for item in winners[:3])}.",
            "Dois desenhos respondem perguntas diferentes; juntar os dois em um só confunde.",
            "Escolha pela pergunta: estrutura → arquitetura; ordem no tempo → sequência ou ciclo de vida.",
            "O desenho mistura duas narrativas e perde a passada única.",
        ))
    if _norm(detalhe) not in {"resumo", "detalhe"}:
        findings.append(finding(
            "nice", "detalhe", "Profundidade fora do vocabulário", detalhe[:40],
            f"`{detalhe}` não é resumo nem detalhe.",
            "O nível decide se o esqueleto vem com um ou três nós por etapa.",
            "Use `resumo` ou `detalhe`.",
            "O esqueleto sai no recorte padrão.",
        ))

    findings, counts, verdict, _ = finalize(findings, "ultra", _questions_for(build({"tipo": kind, "titulo": "x", **_skeleton(kind)})))
    rows = [
        {
            "tipo": item,
            "rotulo": TYPES[item]["label"],
            "pontos": scores[item],
            "sinais": ", ".join(hits[item][:6]) or "—",
            "pergunta": TYPES[item]["use"],
        }
        for item, _ in ranked
    ]
    result = common(
        analysis="roteiro de tipo",
        mode="full",
        title=f"Roteiro de tipo: {TYPES[kind]['label']}",
        summary=[
            f"O pedido aponta para **{TYPES[kind]['label']}** ({kind}), com {scores[kind]} ponto(s) de sinal.",
            f"Esse tipo responde: {TYPES[kind]['use']}.",
            f"Orçamento confortável: até {TYPES[kind]['budget']} {TYPES[kind]['node_kind']}s em uma passada.",
        ],
        findings=findings,
        counts=counts,
        verdict=verdict,
        questions=[],
        rows=rows,
        metrics={"tipo": kind, "pontuacao": scores[kind], "candidatos": len(winners)},
        limitations=[
            "O roteador lê palavras do pedido; não entende ironia, contexto de conversa ou imagem.",
            "O esqueleto é um ponto de partida, não um inventário da sua realidade.",
            "Nenhum diagrama é desenhado nesta skill: ela só escolhe o tipo e entrega a forma inicial.",
        ],
    )
    result.update({
        "tipo": kind,
        "rotulo": TYPES[kind]["label"],
        "porQue": TYPES[kind]["use"],
        "candidatos": rows[:5],
        "esquema": {
            "arrays": list(TYPES[kind]["arrays"]),
            "opcional": list(TYPES[kind]["optional"]),
            "no": TYPES[kind]["node_kind"],
            "orcamento": TYPES[kind]["budget"],
        },
        "esqueleto": _skeleton(kind),
        "proximo": "Cole o esqueleto em diagram.spec, troque os nós pelos fatos reais e valide.",
    })
    return result


def diagram_spec(*, especificacao: str, modo: str = "full") -> dict[str, Any]:
    _mode(modo)
    spec = build_from_text(especificacao)
    findings, counts, verdict, questions = finalize(
        [_to_finding(item) for item in spec.issues], modo, _questions_for(spec)
    )
    rows = [
        {
            "id": node.id,
            "rotulo": node.label,
            "tipo": node.kind,
            "linha": node.row,
            "coluna": node.col,
            "detalhe": node.sublabel or node.tag or "—",
            "membros": len(node.members),
        }
        for node in spec.nodes
    ]
    metrics = _metrics_of(spec)
    result = common(
        analysis="validação do IR",
        mode=modo,
        title=f"Validação: {spec.title or 'diagrama sem título'}",
        summary=[
            f"Tipo **{TYPES[spec.kind]['label']}** ({spec.kind}) com {len(spec.nodes)} nó(s), "
            f"{len(spec.links)} relação(ões), {len(spec.regions)} região(ões) e {len(spec.cards)} cartão(ões).",
            f"Canvas de {metrics.get('largura', 0)} × {metrics.get('altura', 0)} px e orçamento de "
            f"{TYPES[spec.kind]['budget']} nós.",
            "A estrutura é acíclica, os ids são únicos e as pontas existem." if counts["must"] == 0
            else "Há bloqueio estrutural: corrija os achados obrigatórios antes de desenhar.",
        ],
        findings=findings,
        counts=counts,
        verdict=verdict,
        questions=questions,
        rows=rows,
        metrics=metrics,
        limitations=_limitations(spec),
    )
    result.update({
        "tipo": spec.kind,
        "titulo": spec.title,
        "contagens": {
            "nos": len(spec.nodes),
            "arestas": len(spec.links),
            "regioes": len(spec.regions),
            "cartoes": len(spec.cards),
            "avisos": len(spec.notes),
        },
        "avisos": spec.notes,
        "normalizado": _as_json(spec),
    })
    return result


def diagram_layout(*, especificacao: str, modo: str = "full") -> dict[str, Any]:
    _mode(modo)
    spec = build_from_text(especificacao)
    findings, counts, verdict, questions = finalize(
        [_to_finding(item) for item in spec.issues], modo, _questions_for(spec)
    )
    rows = [
        {
            "id": node.id,
            "x": round(node.x),
            "y": round(node.y),
            "largura": round(node.w),
            "altura": round(node.h),
            "linha": node.row,
            "coluna": node.col,
        }
        for node in spec.nodes
    ]
    metrics = _metrics_of(spec)
    sections = ["", "## Rotas", ""]
    for link in spec.links:
        points = " → ".join(f"({x:.0f},{y:.0f})" for x, y in link.points)
        sections.append(f"- `{link.src}` → `{link.dst}`: {points or 'sem rota'} {f'· {link.label}' if link.label else ''}")
    sections += [
        "", "## Regiões", "",
        *[
            f"- **{region.label}** ({region.kind}): {region.x:.0f},{region.y:.0f} · {region.w:.0f}×{region.h:.0f}"
            for region in spec.regions
        ],
        "", "## Mapa em texto", "", "```", render_ascii(spec).rstrip(), "```",
    ]
    result = common(
        analysis="layout medido",
        mode=modo,
        title=f"Layout: {spec.title or 'diagrama'}",
        summary=[
            f"Canvas de {metrics.get('largura', 0)} × {metrics.get('altura', 0)} px com "
            f"{metrics.get('preenchimento', 0)}% de preenchimento.",
            f"{metrics.get('cruzamentos', 0)} cruzamento(s), {metrics.get('colisoes', 0)} linha(s) sobre caixa, "
            f"{metrics.get('sobreposicoes', 0)} sobreposição(ões) e {metrics.get('rotulosApertados', 0)} "
            f"rótulo(s) sem folga.",
            "O roteamento é ortogonal e determinístico: as mesmas coordenadas voltam sempre.",
        ],
        findings=findings,
        counts=counts,
        verdict=verdict,
        questions=questions,
        rows=rows,
        metrics=metrics,
        limitations=_limitations(spec),
        extra_sections=sections,
    )
    result.update({
        "tipo": spec.kind,
        "grade": rows,
        "mapa": render_ascii(spec),
        "metricas": metrics,
        "regioes": [
            {"id": region.id, "rotulo": region.label, "tipo": region.kind,
             "x": round(region.x), "y": round(region.y),
             "largura": round(region.w), "altura": round(region.h)}
            for region in spec.regions
        ],
    })
    return result


def diagram_render(*, especificacao: str, formato: str = "html", modo: str = "full") -> dict[str, Any]:
    _mode(modo)
    spec = build_from_text(especificacao)
    key = _norm(formato) or "html"
    if key not in FORMATS:
        raise DiagramError("Formato inválido: use html, svg, mermaid, ascii ou dot.")
    content = render(spec, key)
    findings, counts, verdict, questions = finalize(
        [_to_finding(item) for item in spec.issues], modo, _questions_for(spec)
    )
    preview = content if len(content) <= 4_000 else content[:4_000] + "\n… (corte de prévia; use o conteúdo completo no painel)"
    sections = ["", f"## {FORMATS[key]}", "", "```" + ("html" if key == "html" else key), preview, "```"]
    result = common(
        analysis=f"entrega em {key}",
        mode=modo,
        title=f"Desenho: {spec.title or 'diagrama'}",
        summary=[
            f"{FORMATS[key]} com {len(content):,} caracteres.".replace(",", "."),
            f"{len(spec.nodes)} nó(s), {len(spec.links)} relação(ões) e {len(legend_entries(spec))} item(ns) de legenda.",
            "HTML: SVG inline, CSS embutido, zero dependência externa e abertura sem servidor." if key == "html"
            else f"{FORMATS[key]} exportado para abrir em outra ferramenta.",
        ],
        findings=findings,
        counts=counts,
        verdict=verdict,
        questions=questions,
        rows=[{"item": entry["rotulo"], "variante": entry["variante"], "traco": entry["traco"]} for entry in legend_entries(spec)],
        metrics=_metrics_of(spec),
        limitations=_limitations(spec),
        extra_sections=sections,
    )
    result.update({
        "tipo": spec.kind,
        "formato": key,
        "rotuloFormato": FORMATS[key],
        "saida": spec.output or f"{_slug(spec.title)}.html",
        "conteudo": content,
        "bytes": len(content.encode("utf-8")),
        "legenda": legend_entries(spec),
        "aviso": "O conteúdo completo está em `conteudo`; o markdown mostra só a prévia."
        if len(content) > 4_000 else "",
    })
    return result


def diagram_legend(
    *, tipo: str = "", preset: str = "", legenda: str = "", especificacao: str = "", modo: str = "full"
) -> dict[str, Any]:
    _mode(modo)
    findings: list[dict[str, Any]] = []
    spec: Spec | None = None
    if especificacao.strip():
        spec = build_from_text(especificacao)
        tipo = tipo or spec.kind
    kind = TYPE_ALIASES.get(_norm(tipo), "")
    if tipo and not kind:
        findings.append(finding(
            "must", "tipo-desconhecido", "Tipo fora do catálogo", tipo[:40],
            f"`{tipo}` não é um dos dez tipos.",
            "A legenda muda de vocabulário conforme o tipo; sem tipo não há rótulo honesto.",
            "Use: " + ", ".join(TYPES) + ".",
            "A legenda sai genérica e pode mentir sobre a linha.",
        ))
        kind = "architecture"
    kind = kind or "architecture"

    preset_key = _PRESETS.get(_norm(preset), "") if preset else ""
    if preset and not preset_key:
        findings.append(finding(
            "must", "preset-desconhecido", "Preset fora do catálogo", preset[:40],
            f"`{preset}` não existe.",
            "Cada preset muda papel, tinta e acento; um nome livre não tem cor definida.",
            "Use classico, sinal, planta ou editorial.",
            "O desenho cai no clássico sem avisar.",
        ))
    preset_key = preset_key or (spec.preset if spec else "classico")

    legend_key = _LEGENDS.get(_norm(legenda), "") if legenda else ""
    if legenda and not legend_key:
        findings.append(finding(
            "should", "legenda-desconhecida", "Modo de legenda fora do vocabulário", legenda[:40],
            f"`{legenda}` não é auto, tudo nem oculta.",
            "O modo decide se a legenda lista só as variantes usadas ou todas.",
            "Use auto, tudo ou oculta.",
            "A legenda cai em automático.",
        ))
    legend_key = legend_key or (spec.legend if spec else "auto")

    if spec is not None:
        variants = used_variants(spec)
        if legend_key == "oculta" and len(variants) > 1:
            findings.append(finding(
                "should", "legenda-oculta", "Legenda oculta com várias variantes", "legenda",
                f"{len(variants)} variantes em uso: {', '.join(variants)}.",
                "Sem legenda o leitor não sabe se a linha tracejada é assíncrono, retorno ou política.",
                "Use `auto` para listar as variantes usadas ou escreva o significado no rótulo da aresta.",
                "A linha perde o significado que o autor conhecia.",
            ))
        if legend_key == "auto" and not variants:
            findings.append(finding(
                "nice", "sem-variantes", "Sem relações para legendar", "conexoes",
                "O diagrama não tem arestas.",
                "Legenda vazia ocupa espaço sem informar.",
                "Deixe `oculta` ou adicione as relações que importam.",
                "O rodapé fica com uma faixa em branco.",
            ))
        if spec.animation == "traco" and len(spec.nodes) > 24:
            findings.append(finding(
                "should", "movimento-demais", "Movimento em desenho denso", "animacao",
                f"{len(spec.nodes)} nós com traço animado.",
                "Movimento com dono único: em desenho denso a animação vira ruído e atrasa a leitura.",
                "Use `animacao: \"nenhuma\"` ou anime só o caminho principal.",
                "O leitor espera o desenho terminar para começar a ler.",
            ))

    findings, counts, verdict, questions = finalize(findings, modo, _questions_for(spec or build({"tipo": kind, "titulo": "x", **_skeleton(kind)})))
    theme = PRESETS[preset_key]
    presets = [
        {"preset": key, "rotulo": value["label"], "papel": value["paper"], "tinta": value["ink"],
         "acento": value["accent"], "contraste": f"{contrast_ratio(value['ink'], value['paper']):.1f}:1"}
        for key, value in PRESETS.items()
    ]
    variants = [
        {"variante": key, "rotulo": value[0], "cor": value[1], "traco": value[2], "peso": value[3]}
        for key, value in VARIANTS.items()
    ]
    result = common(
        analysis="legenda e presets",
        mode=modo,
        title=f"Legenda: {TYPES[kind]['label']}",
        summary=[
            f"Tipo **{TYPES[kind]['label']}**, preset **{theme['label']}** e legenda **{legend_key}**.",
            f"Contraste de tinta sobre papel: {contrast_ratio(theme['ink'], theme['paper']):.1f}:1 "
            f"({'passa' if contrast_ratio(theme['ink'], theme['paper']) >= 7 else 'atenção'} para texto pequeno).",
            "A legenda automática só lista as variantes que o desenho realmente usa.",
        ],
        findings=findings,
        counts=counts,
        verdict=verdict,
        questions=questions,
        rows=variants,
        metrics={"tipo": kind, "preset": preset_key, "legenda": legend_key, "variantes": len(used_variants(spec)) if spec else 0},
        limitations=[
            "O contraste mede tinta sobre papel, não texto sobre preenchimento de nó nem sobre gradiente.",
            "A legenda cobre as variantes de relação; não substitui rótulo de aresta quando o sentido é específico.",
            "Presets mudam cor; não mudam a topologia nem a verdade do desenho.",
        ],
    )
    result.update({
        "tipo": kind,
        "preset": preset_key,
        "entradas": legend_entries(spec) if spec else [
            {"variante": key, "rotulo": value[0], "cor": value[1], "traco": value[2]} for key, value in VARIANTS.items()
        ],
        "presets": presets,
        "politicaDeMovimento": {
            "padrao": "traco com preferência de movimento reduzido respeitada",
            "denso": "acima de 24 nós, prefira nenhuma",
            "dono": "um único dono do movimento: o traço das relações; nós não pulsam",
        },
    })
    return result


def diagram_delivery(
    *, especificacao: str, modo: str = "full", checagem_visual: str = "nao-solicitada", captura: str = "nao"
) -> dict[str, Any]:
    _mode(modo)
    spec = build_from_text(especificacao)
    metrics = _metrics_of(spec)
    visual = "requested" if _norm(checagem_visual) in {"pedida", "requested", "sim"} else "not-requested"
    wants_capture = _norm(captura) in {"sim", "requested", "pedida"}

    gates: list[dict[str, Any]] = []

    def gate(name: str, label: str, status: str, evidence: str) -> dict[str, Any]:
        return {"gate": name, "rotulo": label, "status": status, "evidencia": evidence}

    structural = [item for item in spec.issues if item["group"] == "must"]
    gates.append(gate(
        "validar", "Validar o IR",
        "falhou" if structural else "passou",
        f"{len(structural)} bloqueio(s) estrutural(is)." if structural
        else f"{len(spec.nodes)} nós, {len(spec.links)} relações, ids únicos e pontas resolvidas.",
    ))
    if structural:
        for item in structural[:3]:
            gates[-1]["evidencia"] += f" {item['title']}: {item['fix']}"
    html = render_html(spec) if not structural else ""
    gates.append(gate(
        "entregar", "Renderizar o HTML",
        "falhou" if structural else "passou",
        "Não renderizado: o IR não passou no gate anterior." if structural
        else f"HTML autocontido com {len(html.encode('utf-8')):,} bytes e SVG inline.".replace(",", "."),
    ))
    measured = [item for item in spec.issues if item["group"] == "should"]
    blocking = [item for item in measured if item["kind"] in {"sobreposicao", "fora-do-canvas"}]
    gates.append(gate(
        "checar", "Checar a geometria",
        "falhou" if blocking else ("passou com ressalvas" if measured else "passou"),
        f"{metrics.get('cruzamentos', 0)} cruzamento(s), {metrics.get('colisoes', 0)} colisão(ões), "
        f"{metrics.get('rotulosApertados', 0)} rótulo(s) apertado(s), {metrics.get('sobreposicoes', 0)} sobreposição(ões).",
    ))
    gates.append(gate(
        "navegador", "Checar no navegador",
        "nao-executado",
        "Sem navegador nesta máquina: piso de texto e overflow horizontal não foram medidos de verdade.",
    ))
    gates.append(gate(
        "revisao-visual", "Revisão visual humana",
        "nao-solicitada" if visual == "not-requested" else "pendente",
        "Ninguém olhou o desenho além das regras estáticas."
        if visual == "not-requested" else "Pedida: abra o HTML e confira legenda, rótulos e densidade.",
    ))
    if wants_capture:
        gates.append(gate(
            "captura", "Captura de tela",
            "nao-executado",
            "Captura não é feita por esta skill; use o navegador com o HTML salvo.",
        ))

    stopped = next((item["gate"] for item in gates if item["status"] == "falhou"), "")
    summary = {
        "titulo": spec.title,
        "tipo": spec.kind,
        "saida": spec.output or f"{_slug(spec.title)}.html",
        "gates": {item["gate"]: item["status"] for item in gates},
        "parouEm": stopped,
        "visualReview": visual,
        "metricas": metrics,
    }
    blocking_findings = [item for item in gates if item["status"] == "falhou"]
    findings = []
    if structural:
        for item in structural[:6]:
            findings.append(finding(
                "must", item["kind"], item["title"], item["location"], item["what"],
                item["problem"], item["fix"], item["ifSkipped"],
            ))
    elif blocking_findings:
        findings.append(finding(
            "must", "gate", "Gate falhou", stopped or "entrega",
            "Uma etapa do contrato não passou.",
            "O contrato para no primeiro gate falho: não se entrega o que não passou.",
            "Corrija a etapa apontada e rode de novo.",
            "O artefato é publicado com um defeito conhecido.",
        ))
    elif measured:
        findings.append(finding(
            "should", "ressalvas", "Entrega com ressalvas medidas", "checar",
            f"{len(measured)} achado(s) não bloqueante(s).",
            "O desenho é válido, mas cruzamentos ou folgas indicam leitura pior que o necessário.",
            "Uma rodada de reposicionamento resolve; só posições e tamanhos mudam.",
            "O leitor gasta mais tempo seguindo linha por linha.",
        ))
    findings, counts, verdict, questions = finalize(findings, modo, [])
    rows = [
        {"gate": item["gate"], "rotulo": item["rotulo"], "status": item["status"], "evidencia": item["evidencia"]}
        for item in gates
    ]
    result = common(
        analysis="contrato de entrega",
        mode=modo,
        title=f"Entrega: {spec.title or 'diagrama'}",
        summary=[
            f"Gate final: **{gates[2]['status']}**. Parada em: **{stopped or 'nenhum'}**.",
            f"Arquivo sugerido: `{summary['saida']}` com {metrics.get('largura', 0)} × {metrics.get('altura', 0)} px.",
            f"Revisão visual: **{visual}**. O contrato não finge ter olhado o desenho.",
        ],
        findings=findings,
        counts=counts,
        verdict=verdict,
        questions=questions,
        rows=rows,
        metrics={"gates": len(gates), "falhas": sum(1 for item in gates if item["status"] == "falhou")},
        limitations=[
            "Os gates são estáticos: não abrem navegador, não medem texto renderizado e não tiram captura.",
            "A rodada de reposicionamento é sugerida, não aplicada: esta skill não move nós por você.",
            "Aprovação humana não é substituída por nenhum gate.",
        ],
    )
    result.update({"gates": gates, "parouEm": stopped, "visualReview": visual, "resumo": summary})
    return result


def diagram_library() -> dict[str, Any]:
    rows = [
        {
            "tipo": key,
            "rotulo": value["label"],
            "pergunta": value["use"],
            "arrays": ", ".join(value["arrays"]),
            "opcional": ", ".join(value["optional"]) or "—",
            "orcamento": value["budget"],
        }
        for key, value in TYPES.items()
    ]
    result = common(
        analysis="catálogo de diagramas",
        mode="full",
        title="Catálogo de diagramas",
        summary=[
            "Dez tipos, cada um com um IR próprio e um orçamento de nós declarado.",
            "Sete tipos de nó, oito estados de ciclo de vida, cinco tipos de classe e seis relações.",
            "Quatro presets, quatro variantes de relação, cinco formatos de saída e um contrato de entrega em gates.",
        ],
        findings=[],
        counts={"must": 0, "should": 0, "nice": 0, "total": 0},
        verdict="Nenhum bloqueio pelas regras estáticas.",
        questions=[],
        rows=rows,
        metrics={"tipos": len(TYPES), "nos": len(NODE_TYPES), "presets": len(PRESETS), "formatos": len(FORMATS)},
        limitations=_limitations(),
    )
    result.update({
        "tipos": rows,
        "nos": [
            {"tipo": key, "rotulo": value[0], "cor": value[1]} for key, value in NODE_TYPES.items()
        ],
        "ciclo": [
            {"tipo": key, "rotulo": value[0], "cor": value[1]} for key, value in LIFECYCLE_TYPES.items()
        ],
        "classes": [
            {"tipo": key, "rotulo": value[0], "cor": value[1]} for key, value in CLASS_KINDS.items()
        ],
        "relacoes": [
            {"tipo": key, "rotulo": value[0], "notacao": value[1]} for key, value in REL_KINDS.items()
        ],
        "variantes": [
            {"variante": key, "rotulo": value[0], "cor": value[1], "traco": value[2]} for key, value in VARIANTS.items()
        ],
        "presets": [
            {"preset": key, "rotulo": value["label"], "papel": value["paper"], "tinta": value["ink"], "acento": value["accent"]}
            for key, value in PRESETS.items()
        ],
        "formatos": [{"formato": key, "rotulo": value} for key, value in FORMATS.items()],
        "limites": {
            "especificacao": MAX_SPEC_CHARS,
            "nos": MAX_NODES,
            "arestas": MAX_EDGES,
            "rotulo": MAX_LABEL,
            "subrotulo": WARN_SUBLABEL,
            "cartoes": MAX_CARDS,
            "rotuloAresta": MAX_EDGE_LABEL,
        },
    })
    return result
