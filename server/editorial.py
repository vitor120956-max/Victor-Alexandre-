"""Camada editorial de diagramas — seleção, marca, conector, lint, importação e entrega.

Inspirado em cathrynlavery/diagram-design (MIT, 2026). Implementação própria e
determinística: nada do upstream é instalado, renderizado ou baixado. O que entra
aqui é o **contrato editorial** que o `/diagramas` (IR → layout → SVG) não cobre:

* qual dos 45 tipos responde ao pedido, e por qual padrão semântico;
* como a marca vira papéis semânticos com contraste WCAG verificado;
* as seis regras obrigatórias de conector, medidas na geometria;
* os anti-padrões que fazem um desenho parecer genérico;
* a importação de draw.io/Mermaid/Excalidraw como *redesenho* com recibo de fidelidade;
* o contrato de entrega: preset de tamanho, rampa tipográfica e SVG acessível.
"""
from __future__ import annotations

import json
import math
import re
import unicodedata
from typing import Any

from .review import common, finalize, finding

VERSAO = "0.36.4"
MAX_TEXTO = 60_000
MAX_NOS = 400


class EditorialError(ValueError):
    """Erro de entrada do vocabulário editorial; a API devolve 200 com `ok:false`."""


# --------------------------------------------------------------- 45 tipos

TIPOS: dict[str, dict[str, Any]] = {
    "arquitetura": {
        "nome": "Arquitetura", "familia": "arquitetura", "nos": 8, "arestas": 10,
        "uso": "Componentes e conexões num retrato único.",
        "chaves": ("componente", "serviço", "servico", "api", "backend", "frontend", "banco",
                   "cache", "fila", "arquitetura", "microsserviço", "microsservico"),
    },
    "delta-arquitetura": {
        "nome": "Delta de arquitetura", "familia": "arquitetura", "nos": 8, "arestas": 10,
        "uso": "Mudança estrutural entre topologias antes/depois, com livro de mudanças.",
        "chaves": ("antes e depois", "delta", "mudança de topologia", "mudanca de topologia",
                   "migração", "migracao", "o que mudou"),
    },
    "estado-atual-ti": {
        "nome": "Estado atual de TI", "familia": "arquitetura", "nos": 9, "arestas": 10,
        "uso": "Panorama legado por fase ou departamento.",
        "chaves": ("legado", "estado atual", "sistemas antigos", "modernização", "modernizacao", "ti"),
    },
    "fluxograma": {
        "nome": "Fluxograma", "familia": "fluxo", "nos": 9, "arestas": 12,
        "uso": "Lógica de decisão com ramos.",
        "chaves": ("decisão", "decisao", "se ", "senão", "senao", "condição", "condicao",
                   "ramo", "fluxo", "processo decisório", "processo decisorio"),
    },
    "sequencia": {
        "nome": "Sequência", "familia": "fluxo", "nos": 5, "arestas": 12,
        "uso": "Mensagens ordenadas no tempo entre atores.",
        "chaves": ("sequência", "sequencia", "chamada", "requisição", "requisicao", "request",
                   "oauth", "handshake", "atores", "mensagens"),
    },
    "maquina-estado": {
        "nome": "Máquina de estados", "familia": "fluxo", "nos": 9, "arestas": 12,
        "uso": "Estados, transições e guardas.",
        "chaves": ("estado", "estados", "transição", "transicao", "máquina", "maquina", "ciclo de vida"),
    },
    "er": {
        "nome": "ER / modelo de dados", "familia": "dados", "nos": 8, "arestas": 10,
        "uso": "Entidades, campos e relacionamentos.",
        "chaves": ("entidade", "modelo de dados", "relacionamento", "er", "tabelas", "campos"),
    },
    "linha-tempo": {
        "nome": "Linha do tempo", "familia": "processo", "nos": 9, "arestas": 6,
        "uso": "Eventos posicionados no tempo.",
        "chaves": ("linha do tempo", "timeline", "eventos", "histórico", "historico", "marcos"),
    },
    "raia": {
        "nome": "Raia (swimlane)", "familia": "processo", "nos": 9, "arestas": 10,
        "uso": "Processo entre áreas, com passagens de bastão.",
        "chaves": ("raia", "swimlane", "áreas", "areas", "times", "handoff", "passagem"),
    },
    "quadrante": {
        "nome": "Quadrante", "familia": "comparação", "nos": 12, "arestas": 0,
        "uso": "Posicionamento em dois eixos / priorização.",
        "chaves": ("quadrante", "priorização", "priorizacao", "esforço", "esforco", "impacto",
                   "2x2", "dois eixos"),
    },
    "radar": {
        "nome": "Radar", "familia": "comparação", "nos": 9, "arestas": 0,
        "uso": "Várias entidades pontuadas em 3–5 critérios.",
        "chaves": ("radar", "teia", "critérios", "criterios", "perfil", "comparação multidimensional"),
    },
    "polar": {
        "nome": "Polar", "familia": "comparação", "nos": 9, "arestas": 0,
        "uso": "Série quantitativa em categorias cíclicas.",
        "chaves": ("polar", "radial", "categorias cíclicas", "sazonalidade", "meses"),
    },
    "loop": {
        "nome": "Loop / flywheel", "familia": "processo", "nos": 8, "arestas": 10,
        "uso": "Ciclo que se reforça, com um hub acumulando estado.",
        "chaves": ("loop", "ciclo", "flywheel", "reforço", "reforco", "volta ao início", "volta ao inicio"),
    },
    "aninhado": {
        "nome": "Aninhado", "familia": "hierarquia", "nos": 9, "arestas": 6,
        "uso": "Hierarquia por contenção / escopo.",
        "chaves": ("aninhado", "nested", "contém", "contem", "escopo", "dentro de", "fronteira"),
    },
    "arvore": {
        "nome": "Árvore", "familia": "hierarquia", "nos": 12, "arestas": 12,
        "uso": "Pai → filhos.",
        "chaves": ("árvore", "arvore", "hierarquia", "pai", "filhos", "decomposição", "decomposicao"),
    },
    "organograma": {
        "nome": "Organograma", "familia": "hierarquia", "nos": 12, "arestas": 12,
        "uso": "Propriedade, reporte, roteamento e escalada.",
        "chaves": ("organograma", "org chart", "reporte", "escalada", "equipe", "quem responde"),
    },
    "camadas": {
        "nome": "Camadas", "familia": "hierarquia", "nos": 6, "arestas": 6,
        "uso": "Níveis de abstração empilhados.",
        "chaves": ("camadas", "stack", "abstração", "abstracao", "níveis", "niveis", "pilha"),
    },
    "explodido": {
        "nome": "Explodido axonométrico", "familia": "objeto", "nos": 5, "arestas": 0,
        "uso": "Partes de um objeto separadas num eixo.",
        "chaves": ("explodido", "exploded", "desmontagem", "teardown", "unboxing", "peças", "pecas"),
    },
    "planta": {
        "nome": "Planta axonométrica", "familia": "objeto", "nos": 8, "arestas": 0,
        "uso": "Um andar ou terreno visto de cima e de lado.",
        "chaves": ("planta", "andar", "salas", "escritório", "escritorio", "campus", "terreno", "pavimento"),
    },
    "venn": {
        "nome": "Venn", "familia": "comparação", "nos": 3, "arestas": 0,
        "uso": "Sobreposição entre conjuntos.",
        "chaves": ("venn", "interseção", "intersecao", "sobreposição", "sobreposicao", "conjuntos"),
    },
    "piramide": {
        "nome": "Pirâmide / funil", "familia": "hierarquia", "nos": 6, "arestas": 0,
        "uso": "Hierarquia ranqueada ou queda de conversão.",
        "chaves": ("pirâmide", "piramide", "funil", "conversão", "conversao", "drop-off", "ranking"),
    },
    "barras": {
        "nome": "Barras", "familia": "comparação", "nos": 8, "arestas": 0,
        "uso": "Comparação quantitativa entre categorias.",
        "chaves": ("barras", "bar", "comparação numérica", "comparacao numerica", "categorias"),
    },
    "cascata": {
        "nome": "Cascata (waterfall)", "familia": "comparação", "nos": 8, "arestas": 0,
        "uso": "Total inicial até total final por contribuições assinadas.",
        "chaves": ("cascata", "waterfall", "ponte", "orçamento", "orcamento", "headcount", "variação", "variacao"),
    },
    "treemap": {
        "nome": "Treemap", "familia": "comparação", "nos": 8, "arestas": 0,
        "uso": "Parte-de-um-todo onde o tamanho relativo é a história.",
        "chaves": ("treemap", "parte de um todo", "área", "area", "proporção", "proporcao"),
    },
    "mapa-calor": {
        "nome": "Mapa de calor", "familia": "comparação", "nos": 12, "arestas": 0,
        "uso": "Valor por célula em linha × coluna.",
        "chaves": ("mapa de calor", "heatmap", "célula", "celula", "linha e coluna", "matriz de valores"),
    },
    "linha": {
        "nome": "Linha", "familia": "comparação", "nos": 5, "arestas": 0,
        "uso": "Tendências contínuas no tempo. Variantes de eixo: slopegraph (dois retratos), ridgeline (distribuições), streamgraph (séries empilhadas), bump (posição).",
        "chaves": ("linha", "tendência", "tendencia", "série temporal", "serie temporal", "evolução", "evolucao",
                   "slopegraph", "ridgeline", "streamgraph", "bump"),
    },
    "gantt": {
        "nome": "Gantt", "familia": "processo", "nos": 12, "arestas": 0,
        "uso": "Tarefas e fases numa linha do tempo.",
        "chaves": ("gantt", "cronograma", "tarefas no tempo", "fases", "prazo"),
    },
    "dispersao": {
        "nome": "Dispersão", "familia": "comparação", "nos": 30, "arestas": 0,
        "uso": "Correlação ou distribuição de duas variáveis. Variantes de eixo: bolha/bubble (terceira variável no tamanho), enxame/beeswarm (um ponto por item).",
        "chaves": ("dispersão", "dispersao", "scatter", "correlação", "correlacao", "outlier", "bolha", "bubble", "beeswarm", "enxame"),
    },
    "alto-nivel": {
        "nome": "Alto nível", "familia": "arquitetura", "nos": 9, "arestas": 10,
        "uso": "Stack de dados ponta a ponta num cluster.",
        "chaves": ("alto nível", "alto nivel", "stack completa", "ponta a ponta", "cluster"),
    },
    "processo": {
        "nome": "Processo", "familia": "processo", "nos": 9, "arestas": 12,
        "uso": "Workflow sequencial multiator com entrega de dados.",
        "chaves": ("processo", "etapas", "workflow", "multiator", "aprovador", "etapa",
                   "aprovação", "aprovacao", "handoff", "passa por"),
    },
    "medalhao": {
        "nome": "Medalhão", "familia": "dados", "nos": 8, "arestas": 8,
        "uso": "Armazenamento em tiers com qualidade e política de acesso.",
        "chaves": ("medalhão", "medalhao", "bronze", "prata", "ouro", "tiers", "camadas de dados"),
    },
    "fluxo-dados": {
        "nome": "Fluxo de dados", "familia": "dados", "nos": 9, "arestas": 10,
        "uso": "Quem faz o quê em cada passo do pipeline.",
        "chaves": ("fluxo de dados", "pipeline", "etl", "elt", "ingestão", "ingestao", "transformação"),
    },
    "integracao-dp": {
        "nome": "Integração de plataforma de dados", "familia": "dados", "nos": 9, "arestas": 12,
        "uso": "Topologia de integração: fontes → núcleo → consumidores.",
        "chaves": ("integração de dados", "integracao de dados", "fontes e consumidores", "plataforma de dados"),
    },
    "matriz-seguranca": {
        "nome": "Matriz de segurança", "familia": "dados", "nos": 12, "arestas": 0,
        "uso": "Permissões por papel e componente.",
        "chaves": ("matriz de segurança", "matriz de seguranca", "permissões por papel", "permissoes por papel",
                   "quem pode ler", "rbac"),
    },
    "sankey": {
        "nome": "Sankey", "familia": "dados", "nos": 8, "arestas": 12,
        "uso": "Quantidade que se divide e se junta; largura = valor.",
        "chaves": ("sankey", "divide", "se junta", "largura", "fluxo de valor", "alocação"),
    },
    "espinha-peixe": {
        "nome": "Espinha de peixe", "familia": "processo", "nos": 6, "arestas": 6,
        "uso": "Causas agrupadas de um efeito observado.",
        "chaves": ("espinha de peixe", "ishikawa", "causa raiz", "causas", "efeito"),
    },
    "wardley": {
        "nome": "Mapa de Wardley", "familia": "comparação", "nos": 9, "arestas": 12,
        "uso": "Cadeia de valor contra evolução: construir, comprar, o que se move.",
        "chaves": ("wardley", "cadeia de valor", "evolução", "evolucao", "commodity", "construir ou comprar"),
    },
    "kanban": {
        "nome": "Kanban", "familia": "processo", "nos": 12, "arestas": 4,
        "uso": "Trabalho em andamento por estado, com limites e bloqueios.",
        "chaves": ("kanban", "wip", "em andamento", "bloqueado", "colunas", "backlog"),
    },
    "jornada": {
        "nome": "Jornada do usuário", "familia": "processo", "nos": 9, "arestas": 4,
        "uso": "O que a pessoa faz em cada estágio e como se sente.",
        "chaves": ("jornada", "user journey", "sentimento", "estágios", "estagios", "experiência do usuário"),
    },
    "blueprint": {
        "nome": "Service blueprint", "familia": "processo", "nos": 9, "arestas": 6,
        "uso": "Frontstage e backstage na mesma grade, com linha de visibilidade.",
        "chaves": ("blueprint", "frontstage", "backstage", "linha de visibilidade", "atendimento"),
    },
    "implantacao": {
        "nome": "Implantação", "familia": "arquitetura", "nos": 6, "arestas": 8,
        "uso": "Onde o software roda: zonas, hosts, artefatos, réplicas, portas.",
        "chaves": ("implantação", "implantacao", "deploy", "zonas", "hosts", "réplicas", "replicas", "portas"),
    },
    "dependencia": {
        "nome": "Grafo de dependências", "familia": "arquitetura", "nos": 9, "arestas": 12,
        "uso": "O que depende de quê, com fan-in e ciclos.",
        "chaves": ("dependência", "dependencia", "depende de", "fan-in", "ciclo", "grafo"),
    },
    "uml-classe": {
        "nome": "UML de classes", "familia": "dados", "nos": 8, "arestas": 10,
        "uso": "Classes, operações, herança e composição.",
        "chaves": ("uml", "classe", "classes", "herança", "heranca", "composição", "composicao", "operação"),
    },
    "story-map": {
        "nome": "Story map", "familia": "processo", "nos": 9, "arestas": 4,
        "uso": "Espinha narrativa fatiada em releases, com a linha de corte.",
        "chaves": ("story map", "histórias", "historias", "releases", "fatiamento", "backbone"),
    },
    "esquema-bd": {
        "nome": "Esquema de banco", "familia": "dados", "nos": 8, "arestas": 10,
        "uso": "Tabelas físicas: tipos SQL, restrições, índices, FKs por coluna.",
        "chaves": ("esquema", "schema", "sql", "tabela física", "tabela fisica", "chave estrangeira", "índice"),
    },
}

# ------------------------------------------------------------------ padrões

PADROES: dict[str, dict[str, Any]] = {
    "fila": {
        "nome": "Fila / gargalo de entrada",
        "leitor": "Muitas chegadas competindo por capacidade finita.",
        "tipo": "fluxo-dados",
        "chaves": ("fila", "gargalo", "chegada", "capacidade", "espera", "backlog", "limite de vazão"),
        "orcamento": "≤5 fontes, ≤5 posições de fila, 1 gargalo, 2 desfechos",
        "anti": "pipeline de largura igual que esconde a contenção; setas fundidas antes de rastreáveis",
    },
    "estagios": {
        "nome": "Estágios com slots semânticos",
        "leitor": "Perguntas, entradas, controles e saídas repetidos em cada estágio.",
        "tipo": "processo",
        "chaves": ("estágio", "estagio", "etapa", "slot", "governança", "governanca", "formulário", "formulario"),
        "orcamento": "≤6 estágios, 4 slots por estágio",
        "anti": "estágios com nomes diferentes para o mesmo papel; slot vazio",
    },
    "entrada-estruturada": {
        "nome": "Entrada livre → artefato estruturado",
        "leitor": "Uma conversa vira registro durável.",
        "tipo": "fluxo-dados",
        "chaves": ("conversa", "texto livre", "structured", "estruturado", "artefato", "transcrição", "transcricao"),
        "orcamento": "≤4 passos, 1 artefato final",
        "anti": "mostrar o modelo como caixa mágica; omitir o que é descartado",
    },
    "traços-política": {
        "nome": "Traços pareados de política",
        "leitor": "Por que duas decisões diferem e onde divergem primeiro.",
        "tipo": "fluxograma",
        "chaves": ("política", "politica", "regra", "passou", "falhou", "skipped", "divergência", "divergencia"),
        "orcamento": "2 traços, ≤7 passos cada",
        "anti": "um traço só; divergência sem marcador",
    },
    "estrada": {
        "nome": "Estrada segura",
        "leitor": "Quais rotas cruzam uma fronteira de confiança e quais são bloqueadas.",
        "tipo": "arquitetura",
        "chaves": ("fronteira", "confiança", "confianca", "permitido", "proibido", "ingresso", "trust boundary"),
        "orcamento": "≤2 fronteiras, ≤8 nós",
        "anti": "fronteira desenhada como caixa comum; rota proibida com seta igual",
    },
    "catálogo-controles": {
        "nome": "Catálogo de controles",
        "leitor": "Quais controles valem em cada superfície de aplicação.",
        "tipo": "camadas",
        "chaves": ("controle", "controles", "conformidade", "auditoria", "superfície", "superficie"),
        "orcamento": "≤6 camadas, 1 controle por célula",
        "anti": "controle repetido em toda camada; camada sem superfície",
    },
    "defesas": {
        "nome": "Camadas compensatórias",
        "leitor": "Como defesas reduzem risco e qual risco sobra.",
        "tipo": "camadas",
        "chaves": ("defesa", "defesas", "risco residual", "mitigação", "mitigacao", "compensatória", "compensatoria"),
        "orcamento": "≤5 camadas, risco residual explícito",
        "anti": "defesa sem risco que ela cobre; risco residual escondido",
    },
    "blocos": {
        "nome": "Decomposição rastreável em blocos",
        "leitor": "Em que subelementos o sistema se divide, cada um citável.",
        "tipo": "arvore",
        "chaves": ("bloco", "blocos", "subelemento", "citável", "citavel", "decomposição rastreável",
                   "decomposicao rastreavel", "id"),
        "orcamento": "≤4 níveis, ≤12 nós, I/O por bloco",
        "anti": "bloco sem I/O declarado; id sem vínculo",
    },
    "ciclo-vida": {
        "nome": "Mapa de fases do ciclo de vida",
        "leitor": "Como um sujeito percorre fases, esperas, retentativas e desfechos.",
        "tipo": "maquina-estado",
        "chaves": ("fase", "fases", "ciclo de vida", "retentativa", "cancelamento", "terminal", "espera"),
        "orcamento": "≤7 estados, 1 caminho feliz, desfechos explícitos",
        "anti": "fase sem saída; terminal que volta",
    },
}

# ------------------------------------------------------------------- marca

PAPEIS: dict[str, dict[str, str]] = {
    "paper": {"claro": "#f5f5f5", "escuro": "#2d3142", "uso": "Fundo da página e preenchimento padrão", "texto": False},
    "paper-2": {"claro": "#ececec", "escuro": "#393e53", "uso": "Fundo do contêiner, preenchimento secundário", "texto": False},
    "ink": {"claro": "#2d3142", "escuro": "#f5f5f5", "uso": "Texto e traço primário", "texto": True},
    "ink-strong": {"claro": "#111111", "escuro": "#111111", "uso": "Texto de alto contraste sobre preenchimento de acento", "texto": True, "sobre": "accent"},
    "muted": {"claro": "#4f5d75", "escuro": "#bfc0c0", "uso": "Texto secundário e seta padrão", "texto": True},
    "soft": {"claro": "#5a6580", "escuro": "#949eb2", "uso": "Sublabel e rótulo de fronteira", "texto": True},
    "rule": {"claro": "rgba(45,49,66,0.12)", "escuro": "rgba(245,245,245,0.12)", "uso": "Fio de borda", "texto": False},
    "rule-solid": {"claro": "#bfc0c0", "escuro": "rgba(191,192,192,0.25)", "uso": "Borda forte, linha de base", "texto": False},
    "accent": {"claro": "#bf4520", "escuro": "#f08a59", "uso": "Foco: 1–2 elementos por diagrama", "texto": True},
    "accent-tint": {"claro": "rgba(191,69,32,0.08)", "escuro": "rgba(240,138,89,0.10)", "uso": "Preenchimento de caixa com borda de acento", "texto": False},
    "link": {"claro": "#2e5aa8", "escuro": "#739fdf", "uso": "Chamadas HTTP/API, setas externas", "texto": True},
}

FONTES: dict[str, dict[str, str]] = {
    "title": {"familia": "Instrument Serif", "tamanho": "1.75rem", "peso": "400", "uso": "H1 da página"},
    "node-name": {"familia": "Geist (sans)", "tamanho": "12px", "peso": "600", "uso": "Rótulo legível por gente"},
    "sublabel": {"familia": "Geist Mono", "tamanho": "9px", "peso": "400", "uso": "Porta, protocolo, URL, tipo de campo"},
    "eyebrow": {"familia": "Geist Mono", "tamanho": "7–8px", "peso": "500, 0.18em, caixa alta", "uso": "Etiqueta de tipo e eixo"},
    "arrow-label": {"familia": "Geist Mono", "tamanho": "8px", "peso": "400, 0.06em", "uso": "Anotação de seta"},
    "callout": {"familia": "Instrument Serif itálico", "tamanho": "14px", "peso": "400", "uso": "Aparte editorial"},
}

CONTRASTE_TEXTO = 4.5
CONTRASTE_MARCA = 3.0

# ------------------------------------------------------------------ presets

PRESETS: dict[str, dict[str, Any]] = {
    "doc-inline": {"w": 960, "h": 600, "rampa": "standard", "uso": "Diagrama na largura do corpo do texto"},
    "doc-wide": {"w": 1280, "h": 720, "rampa": "standard", "uso": "Documentação de largura total"},
    "slide-16x9": {"w": 1280, "h": 720, "rampa": "presentation", "uso": "Slide projetado"},
    "slide-4x3": {"w": 1024, "h": 768, "rampa": "presentation", "uso": "Template de slide antigo"},
    "social-og": {"w": 1200, "h": 632, "rampa": "presentation", "uso": "Cartão de link"},
    "social-square": {"w": 1080, "h": 1080, "rampa": "presentation", "uso": "Post de feed"},
    "print-a4-landscape": {"w": 1120, "h": 792, "rampa": "print", "uso": "A4 paisagem"},
    "print-a3-landscape": {"w": 1584, "h": 1120, "rampa": "print", "uso": "A3 paisagem"},
    "print-letter-landscape": {"w": 1056, "h": 816, "rampa": "print", "uso": "Carta paisagem"},
    "fit": {"w": 0, "h": 0, "rampa": "standard", "uso": "Derivado do conteúdo; sem moldura fixa"},
}

RAMPAS: dict[str, dict[str, Any]] = {
    "standard": {"titulo": 28, "nome": 12, "sublabel": 9, "rotulo": 8, "eyebrow": 8, "caixa": 48, "folga": 24,
                 "tamanhos": {12, 9, 8, 28}},
    "presentation": {"titulo": 40, "nome": 16, "sublabel": 12, "rotulo": 12, "eyebrow": 8, "caixa": 64, "folga": 40,
                     "tamanhos": {40, 16, 12, 8}},
    "print": {"titulo": 32, "nome": 12, "sublabel": 9, "rotulo": 8, "eyebrow": 8, "caixa": 48, "folga": 24,
              "tamanhos": {32, 12, 9, 8}},
}

ESSENCIAL = re.compile(
    r"(?i)\b(banco|base|postgres|postgresql|mysql|mariadb|sqlite|oracle|mongo|mongodb|dynamo|redis|"
    r"memcached|s3|bucket|blob|storage|tabela|table|db|fila|queue|kafka|rabbit|pubsub|warehouse)\b"
)

DETALHES: dict[str, dict[str, Any]] = {
    "faithful": {"nos": 24, "arestas": 32, "sublabel": "todo port, protocolo e versão", "rotulo": "Fiel"},
    "balanced": {"nos": 12, "arestas": 16, "sublabel": "técnico em até 4 nós", "rotulo": "Equilibrado"},
    "simplified": {"nos": 7, "arestas": 9, "sublabel": "nenhum", "rotulo": "Simplificado"},
}

PLATEIAS: dict[str, dict[str, Any]] = {
    "engineer": {"nome": "Engenharia", "no": "nome exato do serviço", "sublabel": "protocolo, porta, versão",
                 "rotulo": "POST /v2/orders", "nunca": "verbo vago como “conecta com”"},
    "mixed": {"nome": "Misto", "no": "nome do componente, sigla expandida", "sublabel": "tecnologia só quando muda a decisão",
              "rotulo": "verbo simples: verifica, grava, avisa", "nunca": "porta, versão, codinome interno"},
    "executive": {"nome": "Executiva", "no": "capacidade e resultado", "sublabel": "nenhum",
                  "rotulo": "verbo de negócio: aprova, paga", "nunca": "fornecedor, infraestrutura, protocolo"},
}

ANTIPADROES: list[dict[str, str]] = [
    {"id": "brilho", "titulo": "Modo escuro com brilho ciano/roxo",
     "regex": r"(#0[0-9a-f]{2}ff|#00ffff|cyan|magenta|purple).{0,80}(glow|drop-shadow|filter:\s*blur)",
     "porque": "Parece técnico sem nenhuma decisão de design.", "correcao": "Papel neutro e um único acento."},
    {"id": "sombra", "titulo": "Sombra em qualquer elemento",
     "regex": r"box-shadow|drop-shadow|filter:\s*drop-shadow",
     "porque": "Sombra está fora; borda está dentro.", "correcao": "Troque por fio de 1px e raio 4–8."},
    {"id": "raio-grande", "titulo": "Raio grande em caixa",
     "regex": r"\brx=\"(1[2-9]|[2-9]\d)\"|border-radius:\s*(1[2-9]|[2-9]\d)px",
     "porque": "Caixa arredondada demais achata a hierarquia.", "correcao": "Use raio 4, 6 ou 8."},
    {"id": "mono-total", "titulo": "Mono como fonte geral",
     "regex": r"font-family:\s*[^;\"']*(mono|JetBrains)[^;\"']*;?\s*[^}]*\n?[^}]*\b(body|\.node-name|h1)\b",
     "porque": "Mono é para conteúdo técnico: porta, comando, URL.", "correcao": "Nome em sans; sublabel em mono."},
    {"id": "jetbrains", "titulo": "JetBrains Mono",
     "regex": r"JetBrains\s*Mono",
     "porque": "É o atalho de “fonte de dev” que o guia recusa.", "correcao": "Geist Mono ou a mono da marca."},
    {"id": "caixas-iguais", "titulo": "Todas as caixas idênticas",
     "regex": r"(?s)(<rect[^>]*rx=\"6\"[^>]*>\s*){5,}",
     "porque": "Apaga a hierarquia: tudo parece do mesmo peso.", "correcao": "Varie tratamento por papel: foco, serviço, armazenamento."},
    {"id": "legenda-solta", "titulo": "Legenda dentro da área do desenho",
     "regex": r"(?is)<svg[^>]*viewBox=\"0 0 [\d.]+ ([\d.]+)\"[^>]*>.*?<text[^>]*\by=\"([\d.]+)\"[^>]*>\s*LEGEND\s*</text>",
     "porque": "Colide com os nós e come o espaço do desenho.", "correcao": "Faixa horizontal no rodapé, com 60px reservados e fio de separação."},
    {"id": "rotulo-sem-mascara", "titulo": "Rótulo de seta sem máscara",
     "regex": r"(?is)<text[^>]*font-size=\"8\"[^>]*>\s*[A-Z][A-Z0-9_ ]{1,13}\s*</text>",
     "porque": "A linha atravessa o texto e o rótulo deixa de ser legível.", "correcao": "Retângulo opaco com a cor do papel atrás do rótulo."},
    {"id": "texto-vertical", "titulo": "Texto vertical na seta",
     "regex": r"writing-mode:\s*(vertical|sideways)",
     "porque": "Ilegível e sem ganho de espaço real.", "correcao": "Rótulo horizontal ao lado do segmento."},
    {"id": "cartoes-iguais", "titulo": "Três cartões de resumo iguais",
     "regex": r"grid-template-columns:\s*repeat\(3,\s*1fr\)",
     "porque": "Grade genérica: nada diz o que importa mais.", "correcao": "Larguras diferentes, ex. 1.1fr 1fr 0.9fr."},
    {"id": "acento-demais", "titulo": "Acento em muitos elementos",
     "regex": r"(?:stroke|fill)=\"\{?accent\}?\"",
     "conta": 3,
     "porque": "Acento em 5 nós apaga o sinal; o foco é 1–2.", "correcao": "Deixe 1–2 elementos em acento e o resto em ink/muted."},
    {"id": "diagonal", "titulo": "Conector diagonal",
     "regex": r"<line[^>]*x1=\"(\d+)\"[^>]*y1=\"(\d+)\"[^>]*x2=\"(\d+)\"[^>]*y2=\"(\d+)\"",
     "porque": "Diagonal é falha automática: só cotovelo ortogonal.", "correcao": "Path ortogonal com r=8."},
]

REGRAS_CONECTOR: list[dict[str, str]] = [
    {"id": 1, "titulo": "Ortogonal obrigatório",
     "regra": "Todo segmento entre nós fora do mesmo eixo é cotovelo de 90° com r=8 (r=6 mínimo). Linha reta só quando os dois extremos compartilham x ou y.",
     "falha": "Conector diagonal."},
    {"id": 2, "titulo": "Folga do rótulo",
     "regra": "O rótulo (≤14 caracteres, caixa alta, centrado no segmento) fica sobre máscara opaca e deixa 6–10px visíveis até o traço.",
     "falha": "Rótulo encostado, cortado ou sobre a própria linha."},
    {"id": 3, "titulo": "Sem sobreposição",
     "regra": "Dois conectores não compartilham traço. Paralelos ficam a ≥12px; cruzamento único usa ponte.",
     "falha": "Traços empilhados ou indistinguíveis."},
    {"id": 4, "titulo": "Leque no ponto de encaixe",
     "regra": "Conectores na mesma borda têm pontos distintos, espaçados ≥12px, em L·k/(N+1).",
     "falha": "Dois conectores no mesmo ponto, ou um escondendo o outro."},
    {"id": 5, "titulo": "Sem trânsito atrás de caixa",
     "regra": "Conector não passa atrás de caixa que não seja origem nem destino; se for geométrico inevitável, traço tracejado (4,3), rótulo na ponta visível e sem seta na caixa intermediária.",
     "falha": "Linha cruza uma caixa e some atrás do preenchimento."},
    {"id": 6, "titulo": "Máscara antes do nó",
     "regra": "A máscara do rótulo não pode sobrepor um nó desenhado depois. Máscara inteiramente dentro do nó é etiqueta e vale.",
     "falha": "Rótulo cortado pela borda do nó."},
]

ACESSIBILIDADE: list[dict[str, str]] = [
    {"id": 1, "regra": "`<svg>` com `role=\"img\"` e `aria-labelledby` apontando para título e descrição existentes."},
    {"id": 2, "regra": "`<title>` é o primeiro filho de `<svg>`, antes de `<defs>`."},
    {"id": 3, "regra": "IDs prefixados por diagrama e variante (`loop-title`, `loop-dark-desc`); `title`/`desc` puros são proibidos."},
    {"id": 4, "regra": "`<title>` é o nome curto do assunto, com até ~60 caracteres."},
    {"id": 5, "regra": "`<desc>` é uma frase sobre o conteúdo, não sobre a geometria."},
    {"id": 6, "regra": "SVG só decorativo leva `aria-hidden=\"true\"`."},
]

ESCADA: list[dict[str, str]] = [
    {"passo": "1", "corta": "Células decorativas", "detalhe": "Nota adesiva, texto solto, bloco de título, legenda da própria fonte."},
    {"passo": "2", "corta": "Duplicatas exatas", "detalhe": "N workers/replicas/shards iguais viram um nó rotulado `Worker ×N`."},
    {"passo": "3", "corta": "Clusters de folhas", "detalhe": "Contêiner cujos filhos são todos folha colapsa no contêiner."},
    {"passo": "4", "corta": "Sumidouros de grau 1", "detalhe": "Monitoração, bucket de log, camada de arquivo."},
    {"passo": "5", "corta": "Infraestrutura transversal", "detalhe": "Log, métrica, segredo, CI. Em `simplified` sai sem perguntar."},
    {"passo": "6", "corta": "Divide em visão geral + detalhe", "detalhe": "Acima do teto, divida em vez de encolher."},
]

DESTINOS: dict[str, dict[str, str]] = {
    "blog": {"preset": "doc-inline", "formato": "html", "detalhe": "balanced"},
    "readme": {"preset": "doc-inline", "formato": "html", "detalhe": "balanced"},
    "docs": {"preset": "doc-wide", "formato": "html", "detalhe": "faithful"},
    "wiki": {"preset": "doc-wide", "formato": "png", "detalhe": "balanced"},
    "deck": {"preset": "slide-16x9", "formato": "png", "detalhe": "simplified"},
    "slides": {"preset": "slide-16x9", "formato": "png", "detalhe": "simplified"},
    "figma": {"preset": "fit", "formato": "svg", "detalhe": "faithful"},
    "social": {"preset": "social-og", "formato": "png", "detalhe": "simplified"},
    "linkedin": {"preset": "social-og", "formato": "png", "detalhe": "simplified"},
    "print": {"preset": "print-a4-landscape", "formato": "png", "detalhe": "balanced"},
    "pdf": {"preset": "print-a4-landscape", "formato": "png", "detalhe": "balanced"},
}


# ------------------------------------------------------------------ utilidades

def _norm(texto: str) -> str:
    base = "".join(c for c in unicodedata.normalize("NFD", str(texto)) if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", base).lower().strip()


def _contem(texto: str, termo: str) -> bool:
    """Casa o termo por palavra inteira: `id` não pode casar dentro de `pedido`."""
    alvo = _norm(termo)
    if len(alvo) < 3:
        return False
    return re.search(r"(?<![0-9a-z])" + re.escape(alvo) + r"(?![0-9a-z])", texto) is not None


def _linhas(texto: str) -> list[str]:
    return [linha.strip() for linha in str(texto).splitlines() if linha.strip() and not linha.strip().startswith("#")]


def _modo(modo: str) -> None:
    if modo not in {"lite", "full", "ultra"}:
        raise EditorialError("Modo inválido: use lite, full ou ultra.")


# ------------------------------------------------------------------ contraste

def _hex(valor: str) -> tuple[int, int, int] | None:
    achado = re.fullmatch(r"#([0-9a-fA-F]{3}|[0-9a-fA-F]{6})", valor.strip())
    if not achado:
        return None
    bruto = achado.group(1)
    if len(bruto) == 3:
        bruto = "".join(c * 2 for c in bruto)
    return int(bruto[0:2], 16), int(bruto[2:4], 16), int(bruto[4:6], 16)


def _rgba(valor: str) -> tuple[tuple[int, int, int], float] | None:
    achado = re.fullmatch(r"rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*(?:,\s*([\d.]+)\s*)?\)", valor.strip())
    if not achado:
        return None
    alfa = float(achado.group(4)) if achado.group(4) is not None else 1.0
    return (int(achado.group(1)), int(achado.group(2)), int(achado.group(3))), max(0.0, min(alfa, 1.0))


def _rgb(valor: str) -> tuple[tuple[int, int, int], float] | None:
    cor = _rgba(valor)
    if cor:
        return cor
    achado = _hex(valor)
    return (achado, 1.0) if achado else None


def _compor(cor: tuple[int, int, int], alfa: float, fundo: tuple[int, int, int]) -> tuple[int, int, int]:
    return tuple(int(round(c * alfa + f * (1 - alfa))) for c, f in zip(cor, fundo))  # type: ignore[return-value]


def _luminancia(cor: tuple[int, int, int]) -> float:
    canais = []
    for canal in cor:
        valor = canal / 255
        canais.append(valor / 12.92 if valor <= 0.03928 else ((valor + 0.055) / 1.055) ** 2.4)
    return 0.2126 * canais[0] + 0.7152 * canais[1] + 0.0722 * canais[2]


def _contraste(a: tuple[int, int, int], b: tuple[int, int, int]) -> float:
    la, lb = _luminancia(a), _luminancia(b)
    claro, escuro = max(la, lb), min(la, lb)
    return round((claro + 0.05) / (escuro + 0.05), 2)


def _ajustar(cor: tuple[int, int, int], fundo: tuple[int, int, int], alvo: float) -> tuple[int, int, int]:
    """Escurece (ou clareia, em fundo escuro) até bater o alvo, em passos de 4%."""
    escuro = _luminancia(fundo) < 0.4
    atual = cor
    for _ in range(60):
        if _contraste(atual, fundo) >= alvo:
            break
        fator = 1.04 if escuro else 0.92
        atual = tuple(max(0, min(255, int(round(c * fator)))) for c in atual)  # type: ignore[assignment]
    return atual


def _hex_de(cor: tuple[int, int, int]) -> str:
    return "#{:02x}{:02x}{:02x}".format(*cor)


# ------------------------------------------------------------------ 1. tipo

def escolher_tipo(*, pedido: str, plateia: str, destino: str, nos: int, modo: str) -> dict[str, Any]:
    _modo(modo)
    pedido = pedido.strip()
    if len(pedido) < 8:
        raise EditorialError("Descreva em uma frase o que o leitor precisa entender.")
    if nos < 0 or nos > MAX_NOS:
        raise EditorialError(f"Informe o número de nós entre 0 e {MAX_NOS}.")
    texto = _norm(pedido)
    achados: list[dict[str, Any]] = []

    pontuacao: list[tuple[int, str]] = []
    for chave, dados in TIPOS.items():
        pontos = sum(1 for termo in dados["chaves"] if _contem(texto, termo))
        if pontos:
            pontuacao.append((pontos, chave))
    pontuacao.sort(key=lambda item: (-item[0], item[1]))

    padrao_id = ""
    padrao_pontos: list[tuple[int, str]] = []
    for chave, dados in PADROES.items():
        pontos = sum(1 for termo in dados["chaves"] if _contem(texto, termo))
        if pontos:
            padrao_pontos.append((pontos, chave))
    padrao_pontos.sort(key=lambda item: (-item[0], item[1]))
    if padrao_pontos:
        padrao_id = padrao_pontos[0][1]

    if pontuacao:
        tipo_id = pontuacao[0][1]
        confianca = "alta" if pontuacao[0][0] >= 2 else "média"
    elif padrao_id:
        tipo_id = PADROES[padrao_id]["tipo"]
        confianca = "média"
    else:
        tipo_id = "arquitetura"
        confianca = "baixa"
        achados.append(finding(
            "should", "tipo-indefinido", "Nenhum tipo reconhecido no pedido", pedido[:60],
            "O pedido não casou com o vocabulário dos 45 tipos nem com os nove padrões; caiu em arquitetura.",
            "Sem tipo declarado, o desenho fica genérico.",
            "Diga o que o leitor precisa entender: componentes, ordem, estados, dados ou tempo.",
            "O desenho responde a outra pergunta.",
        ))
    if padrao_id and padrao_pontos[0][0] >= 2:
        tipo_id = PADROES[padrao_id]["tipo"]

    tipo = TIPOS[tipo_id]
    teto = tipo["nos"]
    if padrao_id:
        teto = min(teto, 9)
    if nos > teto:
        achados.append(finding(
            "must", "acima-do-orcamento", "Nós acima do orçamento do tipo",
            f"{nos} nós > {teto}",
            f"{tipo['nome']} comporta até {teto} nós antes de virar fiação.",
            "Acima do teto o leitor para de ler o desenho e passa a decifrá-lo.",
            "Divida em visão geral + detalhe, ou suba o nível de abstração.",
            "O desenho vira um diagrama de ligação, não um esquema.",
        ))
    elif nos > 9:
        achados.append(finding(
            "should", "sem-zona", "Mais de nove nós sem zona",
            f"{nos} nós",
            "Acima de 9 nós todo nó precisa pertencer a uma zona rotulada (2–4 zonas).",
            "Sem zona, 20 nós são um mapa de fiação.",
            "Agrupe em 2–4 zonas com fio de borda e rótulo em mono caixa alta.",
            "O desenho perde a hierarquia.",
        ))
    if nos >= 1 and "tabela" not in texto and len(pontuacao) and pontuacao[0][0] == 1:
        achados.append(finding(
            "nice", "confirmar-tipo", "Escolha por uma palavra só",
            tipo["nome"],
            "O tipo foi escolhido por um único termo do pedido.",
            "Um sinônimo trocado muda o tipo e o layout.",
            "Confirme o tipo antes de desenhar, ou diga o eixo dominante.",
            "Você recebe um layout que não responde à pergunta.",
        ))
    tabela = re.search(r"\b(lista|listar|ranking|atributos|campos|comparação de valores|tabela)\b", texto)
    if tabela:
        achados.append(finding(
            "should", "tabela-basta", "Talvez uma tabela resolva",
            tabela.group(1),
            "O pedido fala de lista ou atributo, que uma tabela comunica melhor.",
            "Desenhar o que cabe numa tabela gasta espaço e atenção.",
            "Use tabela para atributos; reserve o desenho para topologia, ordem ou tempo.",
            "O leitor compara valores pior do que numa tabela.",
        ))
    if len(pedido) < 25:
        achados.append(finding(
            "nice", "pedido-curto", "Pedido curto demais para decidir",
            f"{len(pedido)} caracteres",
            "Uma frase curta não diz o eixo dominante.",
            "O tipo escolhido pode ser o segundo melhor.",
            "Acrescente quem lê e o que deve acontecer depois de olhar.",
            "O desenho acerta o tema e erra a pergunta.",
        ))

    destino_chave = _norm(destino)
    destino_dados = DESTINOS.get(destino_chave, {})
    for termo, dados in DESTINOS.items():
        if termo in destino_chave:
            destino_dados = dados
            break
    preset = destino_dados.get("preset", "doc-inline")
    formato = destino_dados.get("formato", "html")
    detalhe = destino_dados.get("detalhe", "balanced")
    if destino.strip() and not destino_dados:
        achados.append(finding(
            "nice", "destino-desconhecido", "Destino fora da lista",
            destino[:60],
            "Use blog, readme, docs, wiki, deck, figma, social, print ou pdf.",
            "Sem destino, o preset e a rampa ficam no padrão.",
            "Declare o destino para fixar viewBox e rampa tipográfica.",
            "O desenho é exportado no tamanho errado.",
        ))
    if preset in PRESETS and PRESETS[preset]["w"]:
        largura = PRESETS[preset]["w"]
        if nos > 0 and nos > 12 and RAMPAS[PRESETS[preset]["rampa"]]["nome"] >= 16:
            achados.append(finding(
                "should", "rampa-vs-nos", "Rampa grande com muitos nós",
                f"{nos} nós em {preset}",
                "Nome a 16px em caixa de 64px come o canvas.",
                "O layout não cabe e o detalhe contradiz o tamanho.",
                "Baixe um nível de detalhe em vez de encolher a tipografia.",
                "O texto fica ilegível projetado.",
            ))
        if nos and largura and nos > largura // 100 and nos <= teto:
            achados.append(finding(
                "nice", "densidade", "Densidade alta para a largura",
                f"{nos} nós em {largura}px",
                "Densidade-alvo é 4/10: completa, sem precisar de guia.",
                "O desenho passa a exigir explicação verbal.",
                "Corte nós ou divida em dois.",
                "O leitor desiste antes de terminar.",
            ))

    plano = [f"tipo: {tipo_id}", f"preset: {preset}", f"detalhe: {detalhe}", f"formato: {formato}"]
    if padrao_id:
        plano.insert(0, f"padrão: {padrao_id}")
    metrics = {
        "candidatos": len(pontuacao),
        "nos": nos,
        "teto": teto,
        "padrao": padrao_id or "—",
        "preset": preset,
        "confianca": confianca,
    }
    perguntas = ["Qual é a prova de que o leitor entendeu: ele refaz o desenho de memória?"]
    if padrao_id:
        perguntas.append(f"O padrão `{PADROES[padrao_id]['nome']}` precisa mesmo dos primitivos próprios, ou o tipo puro basta?")
    achados, counts, veredito, perguntas = finalize(achados, modo, perguntas)
    extra = ["", "## Escolha", ""]
    extra += [f"- **Tipo:** {tipo['nome']} (`{tipo_id}`) — {tipo['uso']}"]
    if padrao_id:
        padrao = PADROES[padrao_id]
        extra += [f"- **Padrão:** {padrao['nome']} — {padrao['leitor']}",
                  f"  - Orçamento do padrão: {padrao['orcamento']}",
                  f"  - Anti-padrões: {padrao['anti']}"]
    extra += [f"- **Orçamento:** ≤{teto} nós, ≤{tipo['arestas']} arestas, ≤2 acentos, ≤2 chamadas",
              f"- **Preset:** {preset} · rampa {RAMPAS[PRESETS[preset]['rampa']]['nome']}",
              f"- **Detalhe:** {detalhe} · **Formato:** {formato}",
              "", "## Antes de desenhar", "",
              "Declare o tipo, o padrão (se houver), o preset e o que o orçamento vai cortar. Se a pessoa estiver por perto, deixe ela redirecionar antes do desenho.",
              ""]
    if len(pontuacao) > 1:
        extra += ["## Outros candidatos", ""]
        for pontos, chave in pontuacao[1:4]:
            extra += [f"- `{chave}` ({TIPOS[chave]['nome']}) — {pontos} termo(s)"]
        extra += [""]
    return {
        **common(
            analysis="editorial.tipo",
            mode=modo,
            title="Tipo e padrão",
            summary=[
                f"Tipo: {tipo['nome']} · confiança {confianca}.",
                f"Orçamento: {teto} nós para {nos} declarados.",
                f"Preset {preset} com rampa {RAMPAS[PRESETS[preset]['rampa']]['nome']}.",
            ],
            findings=achados,
            counts=counts,
            verdict=veredito,
            questions=perguntas,
            rows=[
                {"id": chave, "nome": dados["nome"], "familia": dados["familia"],
                 "nos": dados["nos"], "uso": dados["uso"]}
                for chave, dados in TIPOS.items()
            ],
            metrics=metrics,
            limitations=LIMITES_TIPO,
            extra_sections=extra,
        ),
        "tipo": tipo_id,
        "nome": tipo["nome"],
        "padrao": padrao_id,
        "plano": plano,
        "preset": preset,
        "executado": False,
    }


LIMITES_TIPO = [
    "A escolha é lexical: casa termos do pedido com o vocabulário dos 45 tipos, sem julgar o conteúdo.",
    "O orçamento vem da documentação pública do upstream em outubro de 2026; tipos novos ou variantes podem mudar.",
    "O preset é sugerido pelo destino declarado, não medido contra o conteúdo real.",
    "Nada é desenhado aqui: o plano é texto para revisar antes de gerar o SVG.",
]


# ------------------------------------------------------------------ 2. marca

def resolver_marca(*, marca: str, escuro: bool, modo: str) -> dict[str, Any]:
    _modo(modo)
    linhas = _linhas(marca)
    if not linhas:
        raise EditorialError("Informe ao menos o fundo e a tinta: `paper=#f5f5f5` e `ink=#2d3142`.")
    if len(linhas) > 40:
        raise EditorialError("Mais de 40 tokens; revise a lista.")
    tema = "escuro" if escuro else "claro"
    valores: dict[str, str] = {}
    achados: list[dict[str, Any]] = []
    for linha in linhas:
        chave, separador, valor = linha.partition("=")
        if not separador:
            chave, separador, valor = linha.partition(":")
        if not separador:
            raise EditorialError(f"Token sem valor: `{linha}`.")
        nome = chave.strip().lower()
        if nome not in PAPEIS:
            achados.append(finding(
                "must", "papel-desconhecido", "Papel semântico desconhecido", nome,
                "O desenho referencia papéis, não hex.",
                f"`{nome}` não existe na lista de papéis.",
                "Use " + ", ".join(sorted(PAPEIS)) + ".",
                "O token fica órfão e o desenho cai no padrão.",
            ))
            continue
        if _rgb(valor.strip()) is None:
            raise EditorialError(f"Cor inválida em `{linha}`: use #rgb, #rrggbb ou rgba().")
        valores[nome] = valor.strip()

    fundo_bruto = valores.get("paper") or PAPEIS["paper"][tema]
    fundo = _rgb(fundo_bruto)
    assert fundo is not None
    fundo_rgb = _compor(fundo[0], fundo[1], (255, 255, 255))

    linhas_saida: list[dict[str, Any]] = []
    for nome, dados in PAPEIS.items():
        bruto = valores.get(nome, dados[tema])
        cor = _rgb(bruto)
        assert cor is not None
        if dados.get("sobre") == "accent":
            acento = _rgb(valores.get("accent", PAPEIS["accent"][tema]))
            assert acento is not None
            fundo_do_papel = _compor(acento[0], 0.85, fundo_rgb)
        else:
            fundo_do_papel = fundo_rgb
        efetiva = _compor(cor[0], cor[1], fundo_do_papel)
        razao = _contraste(efetiva, fundo_do_papel)
        alvo = CONTRASTE_TEXTO if dados["texto"] else 0.0
        situacao = "ok" if razao >= alvo else ("falha" if alvo else "livre")
        proposto = ""
        if dados["texto"] and razao < alvo:
            nova = _ajustar(cor[0], fundo_do_papel, CONTRASTE_TEXTO)
            proposto = _hex_de(nova)
            razao_nova = _contraste(nova, fundo_do_papel)
            achados.append(finding(
                "must", "contraste", f"Contraste baixo em `{nome}`", f"{bruto} → {razao:.2f}:1",
                f"O papel `{nome}` carrega texto e precisa de {alvo}:1 sobre o fundo.",
                f"Com {razao:.2f}:1 o texto some em tamanho pequeno e no projetor.",
                f"Use `{proposto}` ({razao_nova:.2f}:1) ou escureça/clareie o valor da marca.",
                "O leitor não consegue ler o rótulo.",
            ))
        linhas_saida.append({
            "papel": nome, "valor": bruto, "tema": tema, "texto": dados["texto"],
            "contraste": razao, "minimo": alvo, "situacao": situacao, "proposto": proposto,
        })

    for obrigatorio in ("ink",):
        if obrigatorio not in valores:
            achados.append(finding(
                "should", "token-ausente", "Token obrigatório ausente", obrigatorio,
                "Tinta é o texto primário; sem ela o desenho usa o padrão.",
                "O contraste foi verificado contra um valor que você não declarou.",
                "Declare o `ink` da marca.",
                "O desenho parece quase seu.",
            ))
    accent = valores.get("accent", "")
    if accent:
        achado = next(item for item in linhas_saida if item["papel"] == "accent")
        if achado["contraste"] >= CONTRASTE_TEXTO:
            achados.append(finding(
                "nice", "acento-forte", "Acento serve como texto e como traço", accent,
                "Um acento com 4.5:1 pode ser usado em rótulo, não só em borda.",
                "Isso simplifica a decisão: um valor só para foco e rótulo de acento.",
                "Mantenha como está; verifique no fundo escuro também.",
                "Nenhum problema.",
            ))

    metrics = {
        "tokens": len(linhas_saida),
        "declarados": len(valores),
        "falhas": sum(1 for item in linhas_saida if item["situacao"] == "falha"),
        "texto": sum(1 for item in linhas_saida if item["texto"]),
        "tema": tema,
    }
    perguntas = ["A marca tem um segundo fundo (cartão, faixa) onde o contraste muda?"]
    achados, counts, veredito, perguntas = finalize(achados, modo, perguntas)
    extra = ["", "## Tokens resolvidos", ""]
    for item in linhas_saida:
        marca_ok = "ok" if item["situacao"] == "ok" else ("falha" if item["situacao"] == "falha" else "—")
        proposta = f" → **{item['proposto']}**" if item["proposto"] else ""
        extra += [f"- `{item['papel']}` = `{item['valor']}`{proposta} · {item['contraste']:.2f}:1 · {marca_ok}"]
    extra += ["", "## Tipografia", ""]
    for nome, dados in FONTES.items():
        extra += [f"- **{nome}**: {dados['familia']} {dados['tamanho']} · peso {dados['peso']} — {dados['uso']}"]
    extra += ["", "## Contrato de contraste", "",
              f"- Texto, inclusive `soft`, `link` e `accent` usados como texto: {CONTRASTE_TEXTO}:1.",
              f"- Marca essencial (linha, seta, borda, ponto de dado): {CONTRASTE_MARCA}:1.",
              "- Cor translúcida é composta sobre o papel antes de medir.",
              "- Sobre `paper-2` ou dentro de `accent-tint`, meça contra essa superfície, não contra o papel.",
              ""]
    if any(item["proposto"] for item in linhas_saida):
        extra += ["## Aplicar", "", "Substitua os valores marcados com `→` no guia de estilo e recalcule o contraste do fundo escuro."]
        extra += [""]
    return {
        **common(
            analysis="editorial.marca",
            mode=modo,
            title="Marca em papéis semânticos",
            summary=[
                f"{len(linhas_saida)} papéis no tema {tema}; {metrics['falhas']} abaixo do contraste mínimo.",
                "O desenho referencia `accent`, não `#bf4520`: trocar o token muda todos os diagramas.",
                f"Texto precisa de {CONTRASTE_TEXTO}:1; marca essencial, de {CONTRASTE_MARCA}:1.",
            ],
            findings=achados,
            counts=counts,
            verdict=veredito,
            questions=perguntas,
            rows=linhas_saida,
            metrics=metrics,
            limitations=LIMITES_MARCA,
            extra_sections=extra,
        ),
        "tokens": {item["papel"]: item["proposto"] or item["valor"] for item in linhas_saida},
        "executado": False,
    }


LIMITES_MARCA = [
    "O contraste é WCAG 2.x calculado sobre o papel declarado; opacidade herdada e fundo de imagem não são simulados.",
    "A proposta de ajuste muda a luminosidade, não o matiz: a cor da marca é preservada, a legibilidade não é negociável.",
    "Nenhum site é acessado: os tokens vêm do texto que você cola.",
    "A verificação de fonte pública (`getComputedStyle`) é do upstream com navegador; aqui não há navegador.",
]


# ------------------------------------------------------------------ 3. lint

def lint_editorial(*, html: str, modo: str) -> dict[str, Any]:
    _modo(modo)
    if len(html.strip()) < 40:
        raise EditorialError("Cole o HTML ou o SVG do diagrama.")
    if len(html) > MAX_TEXTO:
        raise EditorialError(f"O arquivo passa de {MAX_TEXTO:,} caracteres.".replace(",", "."))

    achados: list[dict[str, Any]] = []
    for item in ANTIPADROES:
        achado = re.search(item["regex"], html, re.I | re.S)
        if not achado:
            continue
        if item["id"] == "acento-demais":
            total = len(re.findall(item["regex"], html, re.I))
            if total < item.get("conta", 3):
                continue
            achados.append(finding(
                "must", "acento-demais", item["titulo"], f"{total} ocorrências",
                item["porque"], "O acento deixa de apontar foco.", item["correcao"],
                "O leitor não sabe onde olhar primeiro.",
            ))
            continue
        if item["id"] == "legenda-solta":
            altura_svg = float(achado.group(1))
            y_legenda = float(achado.group(2))
            if y_legenda >= altura_svg - 60:
                continue
            achados.append(finding(
                "should", "legenda-solta", item["titulo"], f"y={y_legenda:g} de {altura_svg:g}",
                item["porque"], "A faixa reservada é o rodapé de 60px.", item["correcao"],
                "A legenda disputa espaço com os nós.",
            ))
            continue
        if item["id"] == "diagonal":
            grupos = achado.groups()
            if len(grupos) == 4:
                x1, y1, x2, y2 = (float(valor) for valor in grupos)
                if abs(x1 - x2) < 0.5 or abs(y1 - y2) < 0.5:
                    continue
            achados.append(finding(
                "must", "diagonal", item["titulo"], f"linha {achado.group(0)[:60]}",
                item["porque"], "Seta diagonal é falha automática do contrato de conector.", item["correcao"],
                "O desenho parece colagem, não esquema.",
            ))
            continue
        achados.append(finding(
            "should", item["id"], item["titulo"], achado.group(0)[:60].replace("\n", " "),
            item["porque"], "O padrão é reconhecido como genérico.", item["correcao"],
            "O desenho passa a parecer template.",
        ))

    mono = len(re.findall(r"font-family[^;\"']*mono", html, re.I))
    total_fontes = max(1, len(re.findall(r"font-family", html, re.I)))
    if mono and mono / total_fontes > 0.7 and total_fontes >= 5:
        achados.append(finding(
            "must", "mono-total", "Mono domina as fontes", f"{mono}/{total_fontes}",
            "Mono é para conteúdo técnico, não para nome de componente.",
            "Tudo fica com o mesmo tom de terminal.",
            "Nome de nó em sans; sublabel em mono.",
            "A hierarquia tipográfica desaparece.",
        ))
    if "role=\"img\"" not in html and "role='img'" not in html:
        achados.append(finding(
            "must", "sem-role", "SVG sem papel de imagem", "<svg>",
            "O contrato acessível exige `role=\"img\"` no `<svg>` do diagrama.",
            "O leitor de tela anuncia um gráfico genérico, sem nome.",
            "Acrescente `role=\"img\"` e `aria-labelledby` com título e descrição.",
            "O diagrama é invisível para quem usa leitor de tela.",
        ))
    externos = re.findall(r"(?:src|href)=\"(https?://[^\"]+)\"", html)
    fora = [url for url in externos if "fonts.googleapis.com" not in url and "fonts.gstatic.com" not in url]
    if fora:
        achados.append(finding(
            "must", "externo", "Recurso externo no arquivo", fora[0][:80],
            "O arquivo é autossuficiente: SVG inline, sem imagem externa.",
            f"{len(fora)} referência(s) externa(s) quebram offline.",
            "Incorpore o recurso ou remova.",
            "O desenho abre quebrado sem rede.",
        ))
    if re.search(r"<script\s+src=", html):
        achados.append(finding(
            "should", "script-externo", "Script de fora no arquivo", "script src",
            "Movimento opcional usa um controlador único, embutido.",
            "Script externo muda o arquivo a cada abertura.",
            "Embuta o controlador revisado ou remova o movimento.",
            "O arquivo deixa de ser determinístico.",
        ))

    metrics = {
        "caracteres": len(html),
        "achados": len(achados),
        "obrigatorios": sum(1 for item in achados if item["group"] == "must"),
        "fontes": total_fontes,
        "mono": mono,
    }
    perguntas = ["O desenho continua legível em preto e branco, sem a cor de acento?"]
    achados, counts, veredito, perguntas = finalize(achados, modo, perguntas)
    extra = ["", "## Os doze anti-padrões", ""]
    for item in ANTIPADROES:
        extra += [f"- **{item['titulo']}** — {item['porque']} Correção: {item['correcao']}"]
    extra += [""]
    return {
        **common(
            analysis="editorial.lint",
            mode=modo,
            title="Lint editorial",
            summary=[
                f"{metrics['achados']} achado(s) em {metrics['caracteres']:,} caracteres.".replace(",", "."),
                "O lint lê o arquivo como texto: não renderiza, não executa e não busca rede.",
                "Sombra, raio grande, mono total, rótulo sem máscara e diagonal são os mais comuns.",
            ],
            findings=achados,
            counts=counts,
            verdict=veredito,
            questions=perguntas,
            rows=[{"id": item["id"], "titulo": item["titulo"], "porque": item["porque"]} for item in ANTIPADROES],
            metrics=metrics,
            limitations=LIMITES_LINT,
            extra_sections=extra,
        ),
        "anti_padroes": [item["id"] for item in ANTIPADROES],
        "executado": False,
    }


LIMITES_LINT = [
    "O lint é lexical e por expressão regular; ele não mede posição real nem substitui o render.",
    "Um padrão pode aparecer em contexto legítimo (por exemplo `box-shadow` numa nota do upstream); o achado é revisável.",
    "O upstream roda `lint-render.py` com navegador; aqui não há navegador nem captura.",
]


# ------------------------------------------------------------------ 4. conector

def _retangulo(dado: Any) -> dict[str, float] | None:
    if not isinstance(dado, dict):
        return None
    try:
        return {chave: float(dado[chave]) for chave in ("x", "y", "w", "h")}
    except (KeyError, TypeError, ValueError):
        return None


def _pontos(conector: dict[str, Any]) -> list[tuple[float, float]]:
    pontos: list[tuple[float, float]] = []
    for item in conector.get("pontos") or []:
        if isinstance(item, (list, tuple)) and len(item) >= 2:
            pontos.append((float(item[0]), float(item[1])))
    if len(pontos) < 2:
        de, para = _retangulo(conector.get("de")), _retangulo(conector.get("para"))
        if de and para:
            pontos = [(de["x"] + de["w"] / 2, de["y"] + de["h"] / 2),
                      (para["x"] + para["w"] / 2, para["y"] + para["h"] / 2)]
    return pontos


def _segmentos(pontos: list[tuple[float, float]]) -> list[tuple[tuple[float, float], tuple[float, float]]]:
    return list(zip(pontos, pontos[1:]))


def _diagonal(segmento: tuple[tuple[float, float], tuple[float, float]]) -> bool:
    (x1, y1), (x2, y2) = segmento
    return abs(x1 - x2) > 0.5 and abs(y1 - y2) > 0.5


def _distancia_ponto_segmento(ponto: tuple[float, float],
                             segmento: tuple[tuple[float, float], tuple[float, float]]) -> float:
    (x, y) = ponto
    (x1, y1), (x2, y2) = segmento
    dx, dy = x2 - x1, y2 - y1
    if dx == 0 and dy == 0:
        return math.hypot(x - x1, y - y1)
    t = max(0.0, min(1.0, ((x - x1) * dx + (y - y1) * dy) / (dx * dx + dy * dy)))
    px, py = x1 + t * dx, y1 + t * dy
    return math.hypot(x - px, y - py)


def _distancia_horizontal(mascara: dict[str, float], segmento: tuple[tuple[float, float], tuple[float, float]]) -> float:
    (x1, y1), (x2, y2) = segmento
    topo, base = mascara["y"], mascara["y"] + mascara["h"]
    esquerda, direita = mascara["x"], mascara["x"] + mascara["w"]
    if abs(y1 - y2) < 0.5:
        centro = (esquerda + direita) / 2
        if not (x1 - 1 <= centro <= x2 + 1 or x2 - 1 <= centro <= x1 + 1):
            return min(math.hypot(esquerda - x1, topo - y1), math.hypot(direita - x2, base - y2))
        return min(abs(y1 - base), abs(y1 - topo))
    centro_y = (topo + base) / 2
    if not (y1 - 1 <= centro_y <= y2 + 1 or y2 - 1 <= centro_y <= y1 + 1):
        return min(math.hypot(esquerda - x1, topo - y1), math.hypot(direita - x2, base - y2))
    return min(abs(x1 - direita), abs(x1 - esquerda))


def _sobrepoe(a: dict[str, float], b: dict[str, float]) -> bool:
    return (a["x"] < b["x"] + b["w"] and b["x"] < a["x"] + a["w"]
            and a["y"] < b["y"] + b["h"] and b["y"] < a["y"] + a["h"])


def _dentro(a: dict[str, float], b: dict[str, float]) -> bool:
    return (a["x"] >= b["x"] - 0.5 and a["y"] >= b["y"] - 0.5
            and a["x"] + a["w"] <= b["x"] + b["w"] + 0.5 and a["y"] + a["h"] <= b["y"] + b["h"] + 0.5)


def checar_conectores(*, conectores: str, modo: str) -> dict[str, Any]:
    _modo(modo)
    bruto = conectores.strip()
    if not bruto:
        raise EditorialError("Cole a lista de conectores em JSON.")
    try:
        dados = json.loads(bruto)
    except json.JSONDecodeError as erro:
        raise EditorialError(f"JSON inválido: {erro.msg} (linha {erro.lineno}).") from erro
    if isinstance(dados, dict):
        dados = dados.get("conectores", [])
    if not isinstance(dados, list) or not dados:
        raise EditorialError("A lista de conectores está vazia.")
    if len(dados) > 200:
        raise EditorialError("Mais de 200 conectores; divida o diagrama.")

    achados: list[dict[str, Any]] = []
    rows: list[dict[str, Any]] = []
    tracos: list[tuple[str, tuple[tuple[float, float], tuple[float, float]]]] = []
    encaixes: dict[tuple[str, str], list[float]] = {}

    for indice, item in enumerate(dados, start=1):
        if not isinstance(item, dict):
            raise EditorialError(f"O conector {indice} precisa ser um objeto.")
        ident = str(item.get("id") or f"c{indice}")
        pontos = _pontos(item)
        if len(pontos) < 2:
            achados.append(finding(
                "must", "sem-geometria", "Conector sem geometria", ident,
                "Cada conector precisa de `de`/`para` ou de `pontos`.",
                "Sem coordenadas, nenhuma regra pode ser medida.",
                "Informe `de` e `para` como `{x,y,w,h}` ou `pontos` como lista de pares.",
                "O contrato de conector não se aplica.",
            ))
            continue
        segmentos = _segmentos(pontos)
        diagonais = [seg for seg in segmentos if _diagonal(seg)]
        if diagonais:
            achados.append(finding(
                "must", "diagonal", "Conector diagonal", ident,
                "Regra 1: só cotovelo ortogonal entre nós fora do mesmo eixo.",
                f"{len(diagonais)} segmento(s) fora do eixo.",
                "Rota em L com raio 8; reta só quando compartilham x ou y.",
                "A seta parece colagem e não é rastreável.",
            ))
        raio = item.get("raio")
        if raio is not None:
            try:
                raio_valor = float(raio)
            except (TypeError, ValueError):
                raio_valor = 0.0
            if raio_valor and raio_valor < 6:
                achados.append(finding(
                    "should", "raio-pequeno", "Raio de canto pequeno", f"{raio_valor:g}",
                    "O cotovelo mínimo é 6; o padrão é 8.",
                    "Canto apertado vira quina e perde a leitura de curva.",
                    "Use r=8 (r=6 no aperto).",
                    "O conector parece uma linha quebrada.",
                ))

        rotulo = str(item.get("rotulo") or "").strip()
        mascara = _retangulo(item.get("mascara"))
        if rotulo:
            if len(rotulo) > 14:
                achados.append(finding(
                    "should", "rotulo-longo", "Rótulo acima de 14 caracteres", rotulo[:30],
                    "Rótulo de seta é curto, em caixa alta, centrado no segmento.",
                    f"{len(rotulo)} caracteres.",
                    "Encurte para ≤14; o detalhe vai na sublabel do nó.",
                    "O rótulo cobre a linha que devia explicar.",
                ))
            if rotulo != rotulo.upper():
                achados.append(finding(
                    "nice", "rotulo-caixa", "Rótulo fora de caixa alta", rotulo[:30],
                    "A caixa alta diferencia rótulo de nome de nó.",
                    "Minúscula compete com o nome do componente.",
                    "Use caixa alta.",
                    "O leitor confunde rótulo com nome.",
                ))
            if mascara is None:
                achados.append(finding(
                    "must", "sem-mascara", "Rótulo sem máscara opaca", ident,
                    "Regra 2: a máscara impede a linha de atravessar o texto.",
                    "Sem máscara o traço corta o rótulo.",
                    "Retângulo com a cor do papel atrás do rótulo.",
                    "O rótulo fica ilegível.",
                ))
            else:
                distancias = [_distancia_horizontal(mascara, seg) for seg in segmentos]
                folga = min(distancias) if distancias else 0.0
                if folga < 6 or folga > 10:
                    achados.append(finding(
                        "must" if folga < 6 else "should", "folga-rotulo",
                        "Folga do rótulo fora de 6–10px", f"{ident}: {folga:.1f}px",
                        "Regra 2: 6 a 10px visíveis entre máscara e traço.",
                        "Abaixo de 6 o rótulo encosta na seta; acima de 10 ele se descola e perde o dono.",
                        "Ajuste a máscara para deixar 8px.",
                        "O leitor não liga o rótulo à linha.",
                    ))
                for depois in item.get("nosDepois") or []:
                    caixa = _retangulo(depois)
                    if caixa and _sobrepoe(mascara, caixa) and not _dentro(mascara, caixa):
                        achados.append(finding(
                            "must", "mascara-sobre-no", "Máscara sobre nó desenhado depois", ident,
                            "Regra 6: o nó cobre a máscara e o texto fica cortado.",
                            "O rótulo encosta na borda do nó.",
                            "Mova o rótulo para um trecho de canvas aberto.",
                            "Sobra um fragmento de texto na borda.",
                        ))
                        break

        tracejado = bool(item.get("tracejado"))
        cruzadas = item.get("cruzaCaixa")
        if cruzadas:
            if not tracejado:
                achados.append(finding(
                    "must", "transito", "Conector atravessa caixa intermediária", ident,
                    "Regra 5: não passar atrás de caixa que não é origem nem destino.",
                    f"Atravessa {cruzadas} sem tracejado.",
                    "Rerote; se for inevitável, use `stroke-dasharray=\"4,3\"` e rótulo na ponta visível.",
                    "A caixa come o traço e a seta some.",
                ))
            if item.get("setaNaIntermediaria"):
                achados.append(finding(
                    "must", "seta-intermediaria", "Seta aponta para caixa intermediária", ident,
                    "A seta resolve no destino verdadeiro, nunca na caixa atravessada.",
                    "O leitor acha que a caixa do meio é o destino.",
                    "Remova o marcador do trecho intermediário.",
                    "O fluxo é lido errado.",
                ))

        for chave in ("de", "para"):
            caixa = _retangulo(item.get(chave))
            if not caixa:
                continue
            lado = str((item.get(chave) or {}).get("lado") or "").strip().lower()
            if not lado:
                continue
            if lado in {"direita", "esquerda", "right", "left"}:
                coordenada = caixa["y"] + caixa["h"] / 2
            else:
                coordenada = caixa["x"] + caixa["w"] / 2
            chave_encaixe = (str(item.get("caixa") or chave), lado)
            encaixes.setdefault(chave_encaixe, []).append(coordenada)

        for seg in segmentos:
            tracos.append((ident, seg))
        rows.append({
            "id": ident, "segmentos": len(segmentos), "diagonais": len(diagonais),
            "rotulo": rotulo or "—", "tracejado": tracejado,
        })

    for chave, posicoes in encaixes.items():
        posicoes.sort()
        for anterior, atual in zip(posicoes, posicoes[1:]):
            if atual - anterior < 12:
                achados.append(finding(
                    "must", "leque", "Encaixes próximos demais na mesma borda",
                    f"{chave[0]} · {chave[1]} · {atual - anterior:.1f}px",
                    "Regra 4: cada conector tem ponto próprio, ≥12px do vizinho, em L·k/(N+1).",
                    "Dois conectores no mesmo ponto escondem um ao outro.",
                    "Distribua os pontos ao longo da borda.",
                    "Não dá para ver quantas setas saem dali.",
                ))
                break

    for indice, (ident, seg) in enumerate(tracos):
        for outro_id, outro in tracos[indice + 1:]:
            if ident == outro_id:
                continue
            (a1, a2), (b1, b2) = seg, outro
            horizontal = abs(a1[1] - a2[1]) < 0.5 and abs(b1[1] - b2[1]) < 0.5
            vertical = abs(a1[0] - a2[0]) < 0.5 and abs(b1[0] - b2[0]) < 0.5
            if horizontal and abs(a1[1] - b1[1]) < 12 and not (
                max(a1[0], a2[0]) < min(b1[0], b2[0]) or max(b1[0], b2[0]) < min(a1[0], a2[0])
            ):
                achados.append(finding(
                    "must", "sobreposicao", "Conectores paralelos sobrepostos",
                    f"{ident} × {outro_id}",
                    "Regra 3: paralelos ficam a ≥12px; cruzamento único usa ponte.",
                    f"Traços a {abs(a1[1] - b1[1]):.1f}px no mesmo trecho.",
                    "Afaste a rota em 12px ou use ponte no cruzamento.",
                    "As duas setas viram uma só.",
                ))
            elif vertical and abs(a1[0] - b1[0]) < 12 and not (
                max(a1[1], a2[1]) < min(b1[1], b2[1]) or max(b1[1], b2[1]) < min(a1[1], a2[1])
            ):
                achados.append(finding(
                    "must", "sobreposicao", "Conectores paralelos sobrepostos",
                    f"{ident} × {outro_id}",
                    "Regra 3: paralelos ficam a ≥12px.",
                    f"Traços a {abs(a1[0] - b1[0]):.1f}px no mesmo trecho.",
                    "Afaste a rota em 12px.",
                    "As duas setas viram uma só.",
                ))

    metrics = {
        "conectores": len(rows),
        "segmentos": len(tracos),
        "diagonais": sum(1 for item in rows for _ in range(item["diagonais"])),
        "rotulados": sum(1 for item in rows if item["rotulo"] != "—"),
        "tracejados": sum(1 for item in rows if item["tracejado"]),
    }
    perguntas = ["Algum conector pode simplesmente sumir porque o layout já diz a relação?"]
    achados, counts, veredito, perguntas = finalize(achados, modo, perguntas)
    extra = ["", "## As seis regras", ""]
    for regra in REGRAS_CONECTOR:
        extra += [f"{regra['id']}. **{regra['titulo']}** — {regra['regra']}",
                  f"   - Falha quando: {regra['falha']}"]
    extra += [""]
    return {
        **common(
            analysis="editorial.conector",
            mode=modo,
            title="Geometria dos conectores",
            summary=[
                f"{metrics['conectores']} conector(es), {metrics['segmentos']} segmento(s), "
                f"{metrics['rotulados']} com rótulo.",
                "As seis regras são medidas na coordenada: diagonal, folga, sobreposição, leque, trânsito e máscara.",
                "Sem renderização: a conta é feita sobre a geometria que você declara.",
            ],
            findings=achados,
            counts=counts,
            verdict=veredito,
            questions=perguntas,
            rows=rows,
            metrics=metrics,
            limitations=LIMITES_CONECTOR,
            extra_sections=extra,
        ),
        "conectores": rows,
        "executado": False,
    }


LIMITES_CONECTOR = [
    "A checagem usa as coordenadas declaradas; ela não lê o SVG renderizado nem resolve `<use>`.",
    "Curvas de canto são tratadas como segmentos retos: o raio é conferido pelo valor declarado, não medido.",
    "Ponte/hop não é verificada: o cruzamento é detectado, a solução fica com quem desenha.",
]


# ------------------------------------------------------------------ 5. importar

NO = r"[A-Za-z0-9_](?:[A-Za-z0-9_.\-]*[A-Za-z0-9_])?"
FORMA = r"(?:\[\([^\]]*\)\]|\[\[[^\]]*\]\]|\{\{[^}]*\}\}|\[[^\]]*\]|\(\([^)]*\)\)|\([^)]*\)|\{[^}]*\}|>[^\]]*\])"
NO_NA_FORMA = re.compile(rf"(?<![A-Za-z0-9_.\-])({NO})\s*({FORMA})")
SETA_FLUXO = re.compile(
    rf"(?<![A-Za-z0-9_.\-])({NO})\s*(?:{FORMA})?\s*"
    rf"(?:<-->|<--|-->|---|==>|==|-{{1,2}}\.->|--x|--o|~~~|--|-{{1,2}}\.-)\s*"
    rf"(?:\|[^|]*\|\s*)?({NO})\s*(?:{FORMA})?"
)
SETA_ER = re.compile(rf"^\s*({NO})\s+[|o{{}}]*--+[|o{{}}]*\s+({NO})\b")
TAREFA_GANTT = re.compile(r"^(.+?)\s*:\s*[^,]+,\s*([A-Za-z0-9_\-]+)\s*,")
SETA_SEQ = re.compile(rf"^({NO})\s*(?:-{{1,2}}>>|-->>|-->|-{{1,2}}x|-{{1,2}}\))\s*({NO})\s*:")
PARTICIPANTE = re.compile(rf"^(?:participant|actor)\s+({NO})(?:\s+as\s+(.+))?$", re.I)
CABECALHO = re.compile(r"^(flowchart|graph|sequencediagram|classdiagram|statediagram|erdiagram|gantt)\b", re.I)
PARADA = re.compile(
    r"^(note|loop|alt|else|opt|par|and|rect|activate|deactivate|autonumber|title|style|linkstyle|"
    r"classdef|direction|acctitle|accdescr|click)\b", re.I)


def _rotulo_limpo(valor: str) -> str:
    texto = re.sub(r"^[\[\(\{>]+|[\]\)\}>]+$", "", valor.strip())
    texto = re.sub(r"<br\s*/?>", " ", texto, flags=re.I)
    texto = re.sub(r"<[^>]+>", "", texto)
    return re.sub(r"\s+", " ", texto).strip()


def _ler_mermaid(texto: str) -> dict[str, Any]:
    linhas = texto.splitlines()
    tipo = ""
    for linha in linhas:
        limpo = linha.strip().lower()
        if re.match(r"^(flowchart|graph)\b", limpo):
            tipo = "flowchart"
        elif limpo.startswith("sequencediagram"):
            tipo = "sequence"
        elif limpo.startswith("classdiagram"):
            tipo = "class"
        elif limpo.startswith("statediagram"):
            tipo = "state"
        elif limpo.startswith("erdiagram"):
            tipo = "er"
        elif limpo.startswith("gantt"):
            tipo = "gantt"
        if tipo:
            break
    if not tipo:
        raise EditorialError("Bloco Mermaid não reconhecido: use flowchart, sequenceDiagram, classDiagram, stateDiagram, erDiagram ou gantt.")

    nos: dict[str, str] = {}
    arestas: list[tuple[str, str]] = []
    containers: list[dict[str, Any]] = []
    pilha: list[str] = []
    anotacoes = 0
    estilo = 0

    for linha in linhas:
        limpo = linha.strip()
        if not limpo or limpo.startswith("%%"):
            continue
        baixo = limpo.lower()
        if baixo.startswith("subgraph"):
            nome = _rotulo_limpo(limpo.split(None, 1)[1]) if " " in limpo else limpo
            containers.append({"id": nome, "filhos": []})
            pilha.append(nome)
            continue
        if re.match(r"^end\b", baixo):
            if pilha:
                pilha.pop()
            continue
        if PARADA.match(limpo):
            if re.match(r"^(note|title|acctitle|accdescr|autonumber)\b", baixo):
                anotacoes += 1
            continue
        if CABECALHO.match(limpo):
            continue

        if tipo == "state":
            limpo = re.sub(r"\[\*\]\s*(?=-->)", "INICIO ", limpo)
            limpo = re.sub(r"(?<=-->)\s*\[\*\]", " FIM", limpo)
            limpo = re.sub(r"(?<=-->>)\s*\[\*\]", " FIM", limpo)
        if tipo == "er":
            achado_er = SETA_ER.match(limpo)
            if achado_er:
                origem, destino = achado_er.groups()
                nos.setdefault(origem, origem)
                nos.setdefault(destino, destino)
                arestas.append((origem, destino))
                continue
        if tipo == "gantt":
            achado_tarefa = TAREFA_GANTT.match(limpo)
            if achado_tarefa:
                tarefa = achado_tarefa.group(1).strip()
                nos[achado_tarefa.group(2)] = _rotulo_limpo(tarefa) or tarefa
                continue
            if baixo.startswith("section"):
                continue
        if tipo == "sequence":
            achado_seq = SETA_SEQ.match(limpo)
            if achado_seq:
                origem, destino = achado_seq.groups()
                nos.setdefault(origem, origem)
                nos.setdefault(destino, destino)
                arestas.append((origem, destino))
                continue
            achado_part = PARTICIPANTE.match(limpo)
            if achado_part:
                nos[achado_part.group(1)] = (achado_part.group(2) or achado_part.group(1)).strip()
            continue

        for achado in NO_NA_FORMA.finditer(limpo):
            ident, forma = achado.group(1), achado.group(2)
            if ident == "subgraph":
                continue
            rotulo = _rotulo_limpo(forma) or ident
            nos[ident] = rotulo
            if pilha and containers and ident not in containers[-1]["filhos"]:
                containers[-1]["filhos"].append(ident)
        for achado in SETA_FLUXO.finditer(limpo):
            origem, destino = achado.group(1), achado.group(2)
            for ident in (origem, destino):
                nos.setdefault(ident, ident)
                if pilha and containers and ident not in containers[-1]["filhos"]:
                    containers[-1]["filhos"].append(ident)
            arestas.append((origem, destino))

    pseudo = {"INICIO": "início", "FIM": "fim"}
    nos = {pseudo.get(chave, chave): (pseudo.get(valor, valor) if isinstance(valor, str) else valor)
           for chave, valor in nos.items() if chave != "subgraph"}
    arestas = [(pseudo.get(a, a), pseudo.get(b, b)) for a, b in arestas]
    return {"formato": "mermaid", "tipo": tipo, "nos": nos,
            "arestas": arestas, "containers": containers, "anotacoes": anotacoes}


def _ler_drawio(texto: str) -> dict[str, Any]:
    if "<mxfile" not in texto and "<mxGraphModel" not in texto:
        raise EditorialError("Arquivo draw.io sem `<mxfile>` nem `<mxGraphModel>`.")
    comprimido = bool(re.search(r"<diagram[^>]*>\s*[A-Za-z0-9+/=]{40,}", texto))
    bruto: dict[str, dict[str, Any]] = {}
    for achado in re.finditer(r"<mxCell\b([^>]*)>", texto):
        atributos = achado.group(1)
        ident = re.search(r'\bid="([^"]*)"', atributos)
        if not ident:
            continue
        valor = re.search(r'\bvalue="([^"]*)"', atributos)
        rotulo = re.sub(r"<[^>]+>", "", valor.group(1)).strip() if valor else ""
        pai = re.search(r'\bparent="([^"]*)"', atributos)
        origem = re.search(r'\bsource="([^"]*)"', atributos)
        destino = re.search(r'\btarget="([^"]*)"', atributos)
        bruto[ident.group(1)] = {
            "id": ident.group(1),
            "rotulo": rotulo,
            "vertice": bool(re.search(r'\bvertex="1"', atributos)),
            "aresta": bool(re.search(r'\bedge="1"', atributos)),
            "pai": pai.group(1) if pai else "",
            "origem": origem.group(1) if origem else "",
            "destino": destino.group(1) if destino else "",
        }
    nos = {chave: item["rotulo"] or chave for chave, item in bruto.items() if item["vertice"]}
    arestas = [(item["origem"], item["destino"]) for item in bruto.values()
               if item["aresta"] and item["origem"] in nos and item["destino"] in nos]
    containers: list[dict[str, Any]] = []
    for chave, item in bruto.items():
        if not item["vertice"]:
            continue
        filhos = [filho for filho, outro in bruto.items() if outro["vertice"] and outro["pai"] == chave]
        if len(filhos) >= 2:
            containers.append({"id": item["rotulo"] or chave, "filhos": filhos})
    return {"formato": "drawio", "tipo": "graph", "nos": nos, "arestas": arestas,
            "containers": containers, "comprimido": comprimido, "anotacoes": 0}


def _ler_excalidraw(texto: str) -> dict[str, Any]:
    try:
        dados = json.loads(texto)
    except json.JSONDecodeError as erro:
        raise EditorialError(f"JSON do Excalidraw inválido: {erro.msg}.") from erro
    elementos = dados.get("elements") if isinstance(dados, dict) else dados
    if not isinstance(elementos, list):
        raise EditorialError("Cena Excalidraw sem lista `elements`.")
    nos: dict[str, str] = {}
    arestas: list[tuple[str, str]] = []
    textos: dict[str, str] = {}
    for elemento in elementos:
        if not isinstance(elemento, dict):
            continue
        ident = str(elemento.get("id", ""))
        tipo = str(elemento.get("type", ""))
        if tipo == "text":
            textos[ident] = str(elemento.get("text", ""))
        elif tipo in {"rectangle", "ellipse", "diamond"}:
            nos[ident] = ident
    for elemento in elementos:
        if not isinstance(elemento, dict) or elemento.get("type") != "arrow":
            continue
        origem = str(elemento.get("startBinding", {}).get("elementId", "")) if isinstance(elemento.get("startBinding"), dict) else ""
        destino = str(elemento.get("endBinding", {}).get("elementId", "")) if isinstance(elemento.get("endBinding"), dict) else ""
        if origem and destino:
            arestas.append((origem, destino))
    for elemento in elementos:
        if not isinstance(elemento, dict) or elemento.get("type") != "text":
            continue
        container = elemento.get("containerId")
        if container and str(container) in nos:
            nos[str(container)] = str(elemento.get("text", "")) or str(container)
    return {"formato": "excalidraw", "tipo": "graph", "nos": nos, "arestas": arestas, "containers": []}


def _digest(fonte: dict[str, Any], detalhe: str) -> dict[str, Any]:
    nos = dict(fonte["nos"])
    arestas = list(fonte["arestas"])
    grau: dict[str, int] = {chave: 0 for chave in nos}
    for origem, destino in arestas:
        grau[origem] = grau.get(origem, 0) + 1
        grau[destino] = grau.get(destino, 0) + 1
    limite = DETALHES[detalhe]
    cortes: list[dict[str, Any]] = []

    def remover(chave: str, motivo: str) -> None:
        if chave in nos:
            cortes.append({"passo": len(cortes) + 1, "corta": motivo, "item": nos[chave] or chave})
            nos.pop(chave, None)

    if len(nos) > limite["nos"]:
        for chave in list(nos):
            if re.search(r"(?i)nota|todo|legenda|sticky|watermark|t[ií]tulo", nos[chave] or ""):
                remover(chave, "célula decorativa")
            if len(nos) <= limite["nos"]:
                break
    if len(nos) > limite["nos"]:
        vistos: dict[str, list[str]] = {}
        for chave, rotulo in nos.items():
            vistos.setdefault(_norm(rotulo), []).append(chave)
        for rotulo, chaves in vistos.items():
            if rotulo and len(chaves) > 1 and len(nos) > limite["nos"]:
                manter = chaves[0]
                nos[manter] = f"{nos[manter]} ×{len(chaves)}"
                for chave in chaves[1:]:
                    remover(chave, f"duplicata de `{nos[manter]}`")
    if len(nos) > limite["nos"]:
        for chave in list(nos):
            if len(nos) <= limite["nos"]:
                break
            if re.search(r"(?i)log|metric|observ|monitor|trace|secret|ci\b|pipeline de build", nos[chave] or ""):
                remover(chave, "infraestrutura transversal")
    if len(nos) > limite["nos"]:
        for chave in list(nos):
            if len(nos) <= limite["nos"]:
                break
            if grau.get(chave, 0) == 1 and not ESSENCIAL.search(nos[chave] or ""):
                remover(chave, "folha sem papel no recorte")
    arestas = [(a, b) for a, b in arestas if a in nos and b in nos]
    dividir = len(nos) > limite["nos"]
    return {
        "nos": len(nos),
        "arestas": len(arestas),
        "origem_nos": len(fonte["nos"]),
        "origem_arestas": len(fonte["arestas"]),
        "cortes": cortes,
        "dividir": dividir,
        "excedente": max(0, len(nos) - limite["nos"]),
    }


def planejar_importacao(*, fonte: str, formato: str, tamanho: str, detalhe: str,
                        plateia: str, modo: str) -> dict[str, Any]:
    _modo(modo)
    if formato not in {"drawio", "mermaid", "excalidraw"}:
        raise EditorialError("Formato de origem: drawio, mermaid ou excalidraw.")
    if detalhe not in DETALHES:
        raise EditorialError("Detalhe: faithful, balanced ou simplified.")
    if plateia not in PLATEIAS:
        raise EditorialError("Plateia: engineer, mixed ou executive.")
    if tamanho not in PRESETS:
        raise EditorialError("Tamanho: " + ", ".join(sorted(PRESETS)) + ".")
    if not fonte.strip():
        raise EditorialError("Cole o arquivo de origem.")
    if len(fonte) > MAX_TEXTO:
        raise EditorialError("A origem passa de 60 000 caracteres; recorte o arquivo.")

    if formato == "mermaid":
        lido = _ler_mermaid(fonte)
    elif formato == "drawio":
        lido = _ler_drawio(fonte)
    else:
        lido = _ler_excalidraw(fonte)

    achados: list[dict[str, Any]] = []
    if not lido["nos"]:
        if lido.get("comprimido"):
            achados.append(finding(
                "must", "comprimido", "Payload comprimido no draw.io", "diagram",
                "O draw.io guarda o grafo em base64 comprimido dentro de `<diagram>`.",
                "O texto colado não traz os `<mxCell>` legíveis, então nenhum nó foi lido.",
                "Exporte como `.drawio` não comprimido ou cole o XML do modelo.",
                "A importação vê zero nós.",
            ))
        else:
            raise EditorialError("Nenhum nó encontrado na origem. Confira o formato e o recorte colado.")

    digest = _digest(lido, detalhe)
    if lido.get("comprimido") and lido["nos"]:
        achados.append(finding(
            "should", "comprimido", "Payload comprimido no draw.io", "diagram",
            "O draw.io guarda o grafo em base64 comprimido dentro de `<diagram>`.",
            "O texto colado pode estar sem os `<mxCell>` legíveis.",
            "Exporte como `.drawio` não comprimido ou cole o XML do modelo.",
            "A importação perde nós sem avisar.",
        ))
    if digest["dividir"]:
        achados.append(finding(
            "must", "acima-do-teto", "Origem acima do teto do detalhe",
            f"{digest['excedente']} nó(s) acima",
            f"`{detalhe}` comporta {DETALHES[detalhe]['nos']} nós.",
            "Cortar além da escada esconde componente sem avisar.",
            "Divida em visão geral + detalhe por zona, ou use `faithful` com zonas.",
            "O desenho mente sobre o que existe.",
        ))
    if detalhe == "faithful" and digest["nos"] > 9:
        achados.append(finding(
            "should", "zonas-obrigatorias", "Acima de nove nós exige zona", f"{digest['nos']} nós",
            "`faithful` passa do orçamento universal de propósito, mas só com zona.",
            "Sem zona, 20 nós são um mapa de fiação.",
            "Agrupe em 2–4 zonas rotuladas com fio de borda.",
            "O leitor não sabe por onde começar.",
        ))
    if detalhe == "simplified" and digest["arestas"] > DETALHES["simplified"]["arestas"]:
        achados.append(finding(
            "should", "arestas-acima", "Arestas acima do teto", f"{digest['arestas']} > {DETALHES['simplified']['arestas']}",
            "Simplificado guarda a capacidade e a sequência, não a fiação.",
            "Aresta demais refaz o problema que o detalhe devia resolver.",
            "Una capacidades e mostre a sequência.",
            "O desenho volta a ser fiação.",
        ))
    rotulos = [rotulo for rotulo in lido["nos"].values() if rotulo]
    if len(rotulos) != len(set(rotulos)):
        achados.append(finding(
            "nice", "rotulos-iguais", "Rótulos repetidos na origem", f"{len(rotulos) - len(set(rotulos))} repetido(s)",
            "Rótulo repetido esconde que são componentes distintos.",
            "O leitor acha que é o mesmo nó.",
            "Sufixe com a zona ou o número da réplica.",
            "Dois componentes parecem um.",
        ))
    if plateia == "executive" and any(re.search(r":\d+|/v\d|https?://", rotulo) for rotulo in rotulos):
        achados.append(finding(
            "should", "plateia-tecnica", "Rótulo técnico para plateia executiva", "porta/versão/URL",
            "Para executivo o nome é capacidade e resultado.",
            "Porta e versão não ajudam a decidir.",
            "Renomeie para o resultado: “Sign-in” em vez de “Auth :8443”.",
            "A plateia para de ler.",
        ))
    if plateia != "engineer" and any(re.search(r"[a-z]+-\d{2}\b", rotulo) for rotulo in rotulos):
        achados.append(finding(
            "nice", "codinome", "Codinome na origem", "ex.: svc-04",
            "Não invente explicação para um identificador.",
            "Sem o significado, o rótulo não comunica.",
            "Mantenha o identificador e pergunte o nome de negócio.",
            "Você inventa um nome que não existe.",
        ))

    preset = PRESETS[tamanho]
    rampa = RAMPAS[preset["rampa"]]
    metrics = {
        "origem_nos": digest["origem_nos"],
        "origem_arestas": digest["origem_arestas"],
        "nos": digest["nos"],
        "arestas": digest["arestas"],
        "cortes": len(digest["cortes"]),
        "detalhe": detalhe,
        "tamanho": tamanho,
        "plateia": plateia,
        "rampa": preset["rampa"],
        "nome": rampa["nome"],
    }
    perguntas = ["Qual trecho da origem é o caminho principal que não pode ser cortado?"]
    if digest["cortes"]:
        perguntas.append("Os cortes da escada podem ser vistos por quem conhece a origem?")
    achados, counts, veredito, perguntas = finalize(achados, modo, perguntas)

    extra = ["", "## Recibo de fidelidade", ""]
    extra += [f"Detalhe: {detalhe} · {digest['origem_nos']} nós na origem → {digest['nos']} desenhados"]
    if digest["cortes"]:
        for corte in digest["cortes"][:12]:
            extra += [f"- Passo {corte['passo']} ({corte['corta']}): {corte['item']}"]
    else:
        extra += ["- Nenhum corte: a origem cabe no teto do detalhe."]
    extra += ["", "## Os quatro discos", "",
              f"- **Formato:** html (o svg e o png saem do html, nunca à mão)",
              f"- **Tamanho:** {tamanho} → viewBox `0 0 {preset['w']} {preset['h']}` · rampa {rampa['nome']}",
              f"- **Detalhe:** {detalhe} → ≤{DETALHES[detalhe]['nos']} nós, ≤{DETALHES[detalhe]['arestas']} arestas",
              f"- **Plateia:** {PLATEIAS[plateia]['nome']} → nome “{PLATEIAS[plateia]['no']}”, rótulo “{PLATEIAS[plateia]['rotulo']}”, nunca {PLATEIAS[plateia]['nunca']}",
              "", "## Escada de degradação", ""]
    for passo in ESCADA:
        extra += [f"{passo['passo']}. **{passo['corta']}** — {passo['detalhe']}"]
    extra += ["", "## O que nunca atravessa", "",
              "Coordenada da origem, paleta da origem, fonte da origem, o emaranhado de conectores do draw.io, o layout automático do Mermaid e a geometria à mão do Excalidraw.",
              "", "## O que sempre atravessa", "",
              "Componentes, relações, agrupamento e direção.",
              ""]
    rows = [{"id": chave, "rotulo": rotulo} for chave, rotulo in list(lido["nos"].items())[:60]]
    return {
        **common(
            analysis="editorial.importar",
            mode=modo,
            title="Redesenho com recibo",
            summary=[
                f"{digest['origem_nos']} nós e {digest['origem_arestas']} arestas lidos de {formato}.",
                f"Desenho: {digest['nos']} nós e {digest['arestas']} arestas em `{detalhe}`.",
                f"Tamanho {tamanho} ({rampa['nome']}) para plateia {PLATEIAS[plateia]['nome']}.",
            ],
            findings=achados,
            counts=counts,
            verdict=veredito,
            questions=perguntas,
            rows=rows,
            metrics=metrics,
            limitations=LIMITES_IMPORTAR,
            extra_sections=extra,
        ),
        "digest": digest,
        "ledger": digest["cortes"],
        "executado": False,
    }


LIMITES_IMPORTAR = [
    "O parser lê texto: Mermaid por linha, draw.io por `<mxCell>`, Excalidraw por `elements`. Não renderiza nem abre arquivo.",
    "O draw.io comprimido é detectado, não descomprimido: sem descompressão, a importação pede o XML do modelo.",
    "A escada corta por rótulo, grau e palavra-chave; o julgamento de qual caminho é principal continua humano.",
    "Posição, cor e fonte da origem são descartadas de propósito: o resultado é redesenho, não conversão.",
]


# ------------------------------------------------------------------ 6. entrega

def _atributo(tag: str, nome: str) -> str:
    achado = re.search(rf"\b{re.escape(nome)}\s*=\s*\"([^\"]*)\"", tag)
    return achado.group(1) if achado else ""


def checar_entrega(*, html: str, preset: str, modo: str) -> dict[str, Any]:
    _modo(modo)
    if preset not in PRESETS:
        raise EditorialError("Preset: " + ", ".join(sorted(PRESETS)) + ".")
    if len(html.strip()) < 60:
        raise EditorialError("Cole o HTML do diagrama.")
    if len(html) > MAX_TEXTO:
        raise EditorialError("O arquivo passa de 60 000 caracteres.")

    achados: list[dict[str, Any]] = []
    svg = re.search(r"<svg\b[^>]*>", html, re.I)
    if not svg:
        raise EditorialError("Nenhum `<svg>` no arquivo: o diagrama precisa ser inline.")
    tag = svg.group(0)
    ids = set(re.findall(r'\bid="([^"]+)"', html))

    if _atributo(tag, "role") != "img":
        achados.append(finding(
            "must", "sem-role", "SVG sem `role=\"img\"`", "<svg>",
            "O contrato acessível começa no papel de imagem.",
            "O leitor de tela não anuncia a figura.",
            "Acrescente `role=\"img\"`.",
            "O diagrama é invisível para tecnologia assistiva.",
        ))
    rotulado = _atributo(tag, "aria-labelledby").split()
    if not rotulado:
        achados.append(finding(
            "must", "sem-aria", "SVG sem `aria-labelledby`", "<svg>",
            "O nome acessível precisa apontar para título e descrição.",
            "Sem nome, a figura é anunciada como “gráfico”.",
            "Aponte para `<slug>-title` e `<slug>-desc`.",
            "O usuário de leitor de tela não sabe o que é.",
        ))
    else:
        faltando = [ident for ident in rotulado if ident not in ids]
        if faltando:
            achados.append(finding(
                "must", "aria-quebrado", "`aria-labelledby` sem destino", ", ".join(faltando),
                "Um ID que não existe não dá nome a nada.",
                "O atributo aponta para o vazio.",
                "Crie os elementos ou corrija o ID.",
                "A acessibilidade parece feita e não está.",
            ))
    corpo = html[svg.end():]
    primeiro = re.search(r"<(\w+)", corpo.lstrip()[:400])
    if not primeiro or primeiro.group(1).lower() != "title":
        achados.append(finding(
            "must", "title-depois", "`<title>` não é o primeiro filho", primeiro.group(1) if primeiro else "—",
            "Tecnologia assistiva pode ignorar um título colocado depois de `<defs>`.",
            "O nome da figura fica instável entre leitores.",
            "Mova `<title>` para logo após a abertura de `<svg>`.",
            "Alguns leitores não anunciam o nome.",
        ))
    titulo = re.search(r"<title[^>]*>(.*?)</title>", html, re.S | re.I)
    desc = re.search(r"<desc[^>]*>(.*?)</desc>", html, re.S | re.I)
    if not titulo or not titulo.group(1).strip():
        achados.append(finding(
            "must", "sem-title", "`<title>` vazio", "<title>",
            "O título é o nome curto do assunto, até ~60 caracteres.",
            "Sem título, a figura não tem nome.",
            "Preencha com o assunto, não com o tipo de desenho.",
            "O leitor de tela anuncia “imagem sem nome”.",
        ))
    elif len(titulo.group(1).strip()) > 60:
        achados.append(finding(
            "should", "title-longo", "`<title>` acima de 60 caracteres", f"{len(titulo.group(1).strip())}",
            "O nome curto cabe numa leitura.",
            "Título longo é truncado no anúncio.",
            "Encurte; o detalhe vai na descrição.",
            "O nome é cortado.",
        ))
    if not desc or not desc.group(1).strip():
        achados.append(finding(
            "must", "sem-desc", "`<desc>` vazio", "<desc>",
            "A descrição diz o conteúdo em uma frase.",
            "Sem descrição, sobra só o nome.",
            "Descreva o que o diagrama mostra, não a geometria.",
            "O leitor não recebe o conteúdo.",
        ))
    elif re.search(r"(?i)\b(retângulo|caixa|à esquerda|a esquerda|acima|abaixo)\b", desc.group(1)):
        achados.append(finding(
            "should", "desc-geometria", "`<desc>` narra geometria", desc.group(1).strip()[:60],
            "A descrição fala do conteúdo com as palavras de quem não vê.",
            "“Caixa à esquerda” não comunica nada sem a imagem.",
            "Troque por: quem faz o quê e em que ordem.",
            "A descrição não substitui a imagem.",
        ))
    for ident in ("title", "desc"):
        if re.search(rf'\bid="{ident}"', html):
            achados.append(finding(
                "must", "id-puro", f"ID `{ident}` sem prefixo", f'id="{ident}"',
                "Dois diagramas na mesma página colidem no ID.",
                "O segundo é anunciado com o nome do primeiro.",
                "Prefixe com o slug: `<slug>-{0}`.".format(ident),
                "O nome acessível troca entre figuras.",
            ))

    viewbox = _atributo(tag, "viewBox")
    dados_preset = PRESETS[preset]
    if viewbox:
        partes = [parte.strip() for parte in re.split(r"[\s,]+", viewbox) if parte.strip()]
        if len(partes) == 4:
            try:
                _, _, largura, altura = (float(parte) for parte in partes)
            except ValueError:
                largura = altura = -1.0
            if largura > 0:
                fora_grade = [valor for valor in (largura, altura) if valor % 4]
                if fora_grade:
                    achados.append(finding(
                        "should", "fora-da-grade", "viewBox fora do múltiplo de 4",
                        f"{largura:g}×{altura:g}",
                        "Origem, largura, altura, folga e padding dividem por 4.",
                        f"{len(fora_grade)} dimensão(ões) fora da grade.",
                        "Arredonde para o próximo múltiplo de 4.",
                        "As folgas ficam com meio pixel e o fio serrilha.",
                    ))
                if preset != "fit" and (abs(largura - dados_preset["w"]) > 0.5 or abs(altura - dados_preset["h"]) > 0.5):
                    achados.append(finding(
                        "must", "viewbox-preset", "viewBox diferente do preset",
                        f"{largura:g}×{altura:g} ≠ {dados_preset['w']}×{dados_preset['h']}",
                        f"O preset `{preset}` fixa o viewBox.",
                        "Exportar no tamanho errado corta ou sobra margem.",
                        f"Use `0 0 {dados_preset['w']} {dados_preset['h']}`.",
                        "O diagrama sai com faixa branca ou cortado.",
                    ))
    else:
        achados.append(finding(
            "must", "sem-viewbox", "SVG sem `viewBox`", "<svg>",
            "Sem viewBox o SVG não escala.",
            "O desenho cresce ou encolhe sem controle.",
            "Declare `viewBox=\"0 0 W H\"` com o preset.",
            "O layout quebra em tela estreita.",
        ))

    largura_preset = dados_preset["w"]
    minimo = re.search(r"min-width:\s*(\d+)px", html)
    if preset == "fit":
        minimo = None
    elif not minimo:
        achados.append(finding(
            "must", "sem-min-width", "Sem `min-width` no SVG", "css",
            "O `min-width` é a largura do viewBox do preset.",
            "Sem ele, o desenho encolhe e leva a rampa tipográfica junto.",
            f"Use `min-width: {largura_preset}px`.",
            "No celular o texto fica ilegível.",
        ))
    elif abs(int(minimo.group(1)) - largura_preset) > 0:
        achados.append(finding(
            "must", "min-width-divergente", "`min-width` diferente do viewBox",
            f"{minimo.group(1)}px ≠ {largura_preset}px",
            "O mínimo precisa ser a largura do viewBox em uso.",
            "Abaixo disso o desenho reduz e a tipografia reduz com ele.",
            f"Use {largura_preset}px.",
            "A rampa prometida não é a que aparece.",
        ))
    if not re.search(r"overflow-x:\s*auto", html):
        achados.append(finding(
            "must", "sem-wrapper", "Sem contêiner com rolagem local", "css",
            "O SVG largo precisa de um invólucro que role sozinho.",
            "Sem ele a página inteira rola de lado, ou um `overflow: hidden` corta o desenho.",
            "`<div class=\"diagram-container\">` com `width:100%;overflow-x:auto`.",
            "Os nós da direita somem.",
        ))
    if re.search(r"overflow-x:\s*auto", html) and not re.search(r"@media\s+print", html):
        achados.append(finding(
            "should", "print-sem-regra", "Sem liberação na impressão", "@media print",
            "Papel não tem barra de rolagem: na impressão, o invólucro corta.",
            "O diagrama impresso perde a parte que rolaria.",
            "Em `@media print`, use `overflow-x: visible` e `min-width: 0`.",
            "O PDF sai cortado.",
        ))
    if re.search(r"@media\s+print", html):
        pos_svg = html.find("svg {")
        pos_print = html.find("@media print")
        if pos_print != -1 and pos_svg != -1 and pos_print < pos_svg:
            achados.append(finding(
                "should", "ordem-print", "Regra de impressão antes da regra do SVG", "@media print",
                "O seletor de mídia não adiciona especificidade.",
                "Uma regra posterior vence e a impressão volta a cortar.",
                "Mova o bloco `@media print` para depois da regra do SVG.",
                "A correção não vale nada.",
            ))

    tamanhos = {float(valor) for valor in re.findall(r"font-size:\s*([\d.]+)px", html)}
    permitidos = set(RAMPAS[dados_preset["rampa"]]["tamanhos"])
    excecoes = {7, 8, 9, 10, 11, 14, 22, 24, 5, 6}
    fora = sorted(valor for valor in tamanhos if valor not in permitidos and valor not in excecoes)
    if fora:
        achados.append(finding(
            "should", "fora-da-rampa", "Tamanho de fonte fora da rampa", ", ".join(f"{valor:g}" for valor in fora),
            f"A rampa `{dados_preset['rampa']}` usa {sorted(permitidos)}.",
            "Tamanho avulso quebra a hierarquia e não é exceção declarada.",
            "Use um valor da rampa, ou uma exceção nomeada (rótulo denso, nome de série).",
            "A tipografia deixa de ser sistema.",
        ))
    if preset.startswith("slide") and 12 in tamanhos and 16 not in tamanhos:
        achados.append(finding(
            "must", "rampa-errada", "Rampa padrão num slide", "12px em preset de slide",
            "Slide projetado usa 16px para nome de nó.",
            "12px no projetor fica ilegível da última fileira.",
            f"Use a rampa presentation: {sorted(RAMPAS['presentation']['tamanhos'])}.",
            "Ninguém lê o diagrama na sala.",
        ))

    imagens = re.findall(r"<img\b[^>]*>", html)
    if imagens:
        achados.append(finding(
            "must", "imagem-externa", "Imagem no arquivo", f"{len(imagens)} <img>",
            "O arquivo é autossuficiente: SVG inline, sem imagem externa.",
            "Imagem externa quebra offline e no export.",
            "Incorpore como SVG inline ou remova.",
            "O desenho abre com ícone quebrado.",
        ))
    if re.search(r"<script\b", html):
        motion = re.search(r"data-frame=\"static\"", html)
        if not motion:
            achados.append(finding(
                "should", "motion-sem-estatico", "Movimento sem quadro estático", "<script>",
                "Movimento é opcional: o quadro estático completo vem primeiro.",
                "Sem o quadro estático, `prefers-reduced-motion` perde o conteúdo.",
                "Garanta o quadro completo em `data-frame=\"static\"`.",
                "Quem pede menos movimento vê um desenho vazio.",
            ))
        if not re.search(r"prefers-reduced-motion", html):
            achados.append(finding(
                "must", "sem-reduced-motion", "Movimento sem `prefers-reduced-motion`", "css",
                "Quem pede menos movimento recebe o quadro completo e os controles escondidos.",
                "Animação sem essa consulta ignora a preferência do sistema.",
                "Acrescente a consulta e esconda os controles nela.",
                "O desenho anima contra a vontade do usuário.",
            ))

    metrics = {
        "caracteres": len(html),
        "preset": preset,
        "rampa": dados_preset["rampa"],
        "tamanhos": len(tamanhos),
        "imagens": len(imagens),
        "achados": len(achados),
    }
    perguntas = ["O diagrama continua inteiro com a fonte do sistema, sem Google Fonts?"]
    achados, counts, veredito, perguntas = finalize(achados, modo, perguntas)
    extra = ["", "## Contrato acessível", ""]
    for criterio in ACESSIBILIDADE:
        extra += [f"{criterio['id']}. {criterio['regra']}"]
    extra += ["", "## Preset", "",
              f"- viewBox `0 0 {dados_preset['w']} {dados_preset['h']}` · rampa {dados_preset['rampa']}",
              f"- `min-width: {dados_preset['w']}px` dentro de um invólucro com `overflow-x: auto`",
              f"- Títulos da rampa: {RAMPAS[dados_preset['rampa']]['titulo']}px; nome {RAMPAS[dados_preset['rampa']]['nome']}px; "
              f"sublabel {RAMPAS[dados_preset['rampa']]['sublabel']}px",
              "- Papel não rola: em `@media print`, `overflow-x: visible` e `min-width: 0`, depois da regra do SVG.",
              ""]
    rows = [{"criterio": item["id"], "regra": item["regra"]} for item in ACESSIBILIDADE]
    return {
        **common(
            analysis="editorial.entrega",
            mode=modo,
            title="Contrato de entrega",
            summary=[
                f"Preset {preset} ({dados_preset['rampa']}); {metrics['tamanhos']} tamanhos de fonte.",
                "Acessibilidade, viewBox, min-width, invólucro e impressão são verificados no texto.",
                "O arquivo é autossuficiente: SVG inline, sem imagem externa; movimento é opcional.",
            ],
            findings=achados,
            counts=counts,
            verdict=veredito,
            questions=perguntas,
            rows=rows,
            metrics=metrics,
            limitations=LIMITES_ENTREGA,
            extra_sections=extra,
        ),
        "preset": preset,
        "executado": False,
    }


LIMITES_ENTREGA = [
    "A checagem lê o texto: não renderiza, não mede sobreposição real nem abre navegador.",
    "A rampa é conferida por `font-size` declarado; tamanho herdado de CSS externo não é visto.",
    "O upstream roda `self_check.py` e `lint-render.py` com render; aqui a garantia é contratual.",
]


# ------------------------------------------------------------------ catálogo

def editorial_catalog() -> dict[str, Any]:
    return {
        "fonte": "cathrynlavery/diagram-design (MIT)",
        "versao": VERSAO,
        "principio": "O melhor movimento é a exclusão: cada nó ganha o lugar, e o acento aponta 1–2 coisas.",
        "tipos": [
            {"id": chave, "nome": valor["nome"], "familia": valor["familia"],
             "nos": valor["nos"], "arestas": valor["arestas"], "uso": valor["uso"]}
            for chave, valor in sorted(TIPOS.items())
        ],
        "padroes": [
            {"id": chave, "nome": valor["nome"], "leitor": valor["leitor"],
             "tipo": valor["tipo"], "orcamento": valor["orcamento"], "anti": valor["anti"]}
            for chave, valor in sorted(PADROES.items())
        ],
        "papeis": [
            {"nome": chave, "claro": valor["claro"], "escuro": valor["escuro"],
             "uso": valor["uso"], "texto": valor["texto"]}
            for chave, valor in sorted(PAPEIS.items())
        ],
        "fontes": [
            {"papel": chave, **valor} for chave, valor in FONTES.items()
        ],
        "presets": [
            {"id": chave, **valor} for chave, valor in PRESETS.items()
        ],
        "rampas": [
            {"id": chave, **valor} for chave, valor in RAMPAS.items()
        ],
        "detalhes": [
            {"id": chave, **valor} for chave, valor in DETALHES.items()
        ],
        "plateias": [
            {"id": chave, **valor} for chave, valor in PLATEIAS.items()
        ],
        "variantes": [
            {"id": "slopegraph", "de": "linha", "uso": "Mudança entre exatamente dois retratos."},
            {"id": "ridgeline", "de": "linha", "uso": "Uma distribuição por série, empilhada."},
            {"id": "streamgraph", "de": "linha", "uso": "Séries empilhadas com fluxo contínuo."},
            {"id": "bump", "de": "linha", "uso": "Movimento de posição entre retratos."},
            {"id": "bolha", "de": "dispersao", "uso": "Terceira variável no tamanho do ponto."},
            {"id": "enxame", "de": "dispersao", "uso": "Um ponto por item, sem sobrepor."},
        ],
        "anti_padroes": [{"id": item["id"], "titulo": item["titulo"], "porque": item["porque"],
                          "correcao": item["correcao"]} for item in ANTIPADROES],
        "conector": REGRAS_CONECTOR,
        "acessibilidade": ACESSIBILIDADE,
        "escada": ESCADA,
        "destinos": [{"destino": chave, **valor} for chave, valor in DESTINOS.items()],
        "contraste": {"texto": CONTRASTE_TEXTO, "marca": CONTRASTE_MARCA},
        "executado": False,
    }
