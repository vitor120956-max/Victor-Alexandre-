"""Triagem de carreira inspirada em career-ops (MIT, 2026).

Implementação própria e determinística. Nenhum CLI `npx @santifer/career-ops`,
plugin de Claude/Codex, script Node, portal de vagas, navegador, LaTeX ou
chamada de rede do upstream é instalado ou executado. As skills leem o que você
cola — perfil, vaga, currículo, carta, histórias e o funil — e devolvem nota com
evidência declarada, lacunas com mitigação, compatibilidade ATS, auditoria de
texto e plano de entrevista.

O recorte é o que sobrevive sem varredura de portais e sem IA: a triagem com
bandas de importância e níveis de evidência, a linha ética de 4,0, os sinais de
legitimidade da vaga, o placar ATS de pesos fixos, a auditoria de bullets, o
plano de entrevista por requisito e o funil de candidaturas.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Iterable

from .review import common, finalize, finding

MAX_PERFIL = 20_000
MAX_VAGA = 60_000
MAX_CURRICULO = 60_000
MAX_CARTA = 20_000
MAX_HISTORIAS = 40_000
MAX_APLICACOES = 60_000
MAX_ITENS = 60
MAX_LINHA = 400
MAX_TERMOS = 12


class CareerError(ValueError):
    """Erro esperado de carreira, seguro para o usuário."""


# ------------------------------------------------------------ vocabulário

BANDS: dict[str, tuple[str, float]] = {
    "critical": ("Obrigatório", 5.0),
    "high": ("Central", 3.0),
    "meaningful": ("Relevante", 2.0),
    "preferred": ("Diferencial", 1.0),
    "low_signal": ("Genérico", 0.5),
}
BAND_ORDER = tuple(BANDS)
EVIDENCE: dict[str, str] = {
    "stated": "a vaga marca como obrigatório, é o título ou um gate legal",
    "structural": "a estrutura da vaga carrega o peso: seção, repetição ou posição",
    "inferred": "leitura de mercado, sem marcação na vaga",
}
MATCH: dict[str, tuple[str, float]] = {
    "forte": ("Forte", 1.0),
    "parcial": ("Parcial", 0.5),
    "ausente": ("Ausente", 0.0),
    "indefinido": ("Indefinido", 0.5),
}
DIMENSIONS: dict[str, tuple[str, float]] = {
    "aderencia": ("Aderência ao perfil", 0.45),
    "alvo": ("Alinhamento com o alvo", 0.20),
    "comp": ("Remuneração", 0.15),
    "cultura": ("Sinais culturais", 0.10),
    "risco": ("Risco da vaga", 0.10),
}
BANDS_SCORE = (
    (4.5, "aplicar agora", "Sinal verde: o perfil cobre o que a vaga pede."),
    (4.0, "vale aplicar", "Bom encaixe; prepare as lacunas antes de enviar."),
    (3.5, "hesitar", "Encaixe parcial: aplique só se houver um motivo declarado."),
    (0.0, "não aplicar", "Abaixo da linha ética de 4,0; o tempo rende mais em outra vaga."),
)
CONFIDENCE = {
    "alta": "Alta",
    "media": "Média",
    "baixa": "Baixa",
}

SECTIONS = {
    "requisitos": ("requisito", "requisitos", "qualificação", "qualificacoes", "qualificações", "o que esperamos", "o que buscamos", "você precisa", "voce precisa", "necessário", "necessario", "must have", "requirements"),
    "responsabilidades": ("responsabilidade", "responsabilidades", "atribuição", "atribuicoes", "atribuições", "o que você vai fazer", "o que voce vai fazer", "atividades", "desafios", "responsibilities"),
    "diferenciais": ("diferencial", "diferenciais", "desejável", "desejavel", "nice to have", "preferred", "bonus", "plus"),
    "beneficios": ("benefício", "beneficio", "beneficios", "benefícios", "oferecemos", "oferecemos", "perks", "benefits"),
    "empresa": ("sobre a empresa", "sobre nós", "sobre nos", "quem somos", "a empresa", "about us"),
}

MUST_CUES = (
    "obrigatório", "obrigatorio", "imprescindível", "imprescindivel", "exigido",
    "exigência", "exigencia", "requisito", "necessário", "necessario", "must",
    "required", "essential", "é necessário", "e necessario", "indispensável", "indispensavel",
)
PREFERRED_CUES = (
    "desejável", "desejavel", "diferencial", "preferência", "preferencia", "preferred",
    "nice to have", "será um plus", "sera um plus", "bonus", "opcional",
)
GENERIC_TERMS = (
    "proatividade", "proativo", "boa comunicação", "boa comunicacao", "trabalho em equipe",
    "organização", "organizacao", "vontade de aprender", "perfil dinâmico", "perfil dinamico",
    "resiliência", "resiliencia", "foco em resultados", "raciocínio lógico", "raciocinio logico",
)

STOPWORDS = {
    "a", "as", "o", "os", "um", "uma", "uns", "umas", "de", "da", "das", "do", "dos", "em",
    "na", "nas", "no", "nos", "por", "para", "com", "sem", "sob", "sobre", "entre", "e", "ou",
    "que", "se", "como", "ao", "aos", "à", "às", "pelo", "pela", "pelos", "pelas", "seu", "sua",
    "seus", "suas", "este", "esta", "estes", "estas", "esse", "essa", "esses", "essas", "isso",
    "nós", "nos", "você", "voce", "vocês", "voces", "eles", "elas", "ser", "estar", "ter", "haver",
    "foi", "são", "sao", "será", "sera", "tem", "têm", "terá", "tera", "mais", "menos", "muito",
    "muita", "muitos", "muitas", "não", "nao", "sim", "já", "ja", "também", "tambem", "bem", "mal",
    "onde", "quando", "qual", "quais", "quem", "cada", "todos", "todas", "todo", "toda", "outros",
    "outras", "outro", "outra", "através", "atraves", "durante", "após", "apos", "antes", "pode",
    "podem", "deve", "devem", "fazer", "feito", "faz", "fazem", "conhecimento", "conhecimentos",
    "experiência", "experiencia", "experiências", "experiencias", "vaga", "empresa", "time",
    "times", "área", "area", "atividade", "atividades", "requisito", "requisitos", "desejável",
    "desejavel", "profissional", "profissionais", "trabalho", "trabalhar", "dia", "dias", "ano",
    "anos", "mês", "mes", "meses", "semana", "semanas", "hora", "horas", "nível", "nivel",
    "superior", "completo", "cursando", "formação", "formacao", "curso", "cursos", "inglês",
    "ingles", "diferencial", "ser", "estar", "atuar", "atuação", "atuacao", "responsável",
    "responsavel", "realizar", "realização", "realizacao", }

TECH_ALIASES: dict[str, str] = {
    "js": "javascript", "javascript": "javascript", "ts": "typescript", "typescript": "typescript",
    "node": "node.js", "nodejs": "node.js", "node.js": "node.js", "react": "react", "reactjs": "react",
    "vue": "vue", "angular": "angular", "next": "next.js", "nextjs": "next.js",
    "python": "python", "pandas": "pandas", "numpy": "numpy", "django": "django", "flask": "flask",
    "fastapi": "fastapi", "java": "java", "spring": "spring", "kotlin": "kotlin", "golang": "go",
    "go": "go", "rust": "rust", "c#": "c#", "dotnet": ".net", ".net": ".net", "php": "php",
    "sql": "sql", "mysql": "mysql", "postgres": "postgresql", "postgresql": "postgresql",
    "oracle": "oracle", "sqlserver": "sql server", "sql server": "sql server", "mongodb": "mongodb",
    "redis": "redis", "elasticsearch": "elasticsearch", "kafka": "kafka", "rabbitmq": "rabbitmq",
    "aws": "aws", "azure": "azure", "gcp": "gcp", "google cloud": "gcp", "docker": "docker",
    "kubernetes": "kubernetes", "k8s": "kubernetes", "terraform": "terraform", "ansible": "ansible",
    "git": "git", "github": "github", "gitlab": "gitlab", "ci/cd": "ci/cd", "jenkins": "jenkins",
    "linux": "linux", "bash": "bash", "power bi": "power bi", "powerbi": "power bi",
    "tableau": "tableau", "looker": "looker", "excel": "excel", "dbt": "dbt", "airflow": "airflow",
    "spark": "spark", "databricks": "databricks", "snowflake": "snowflake", "bigquery": "bigquery",
    "figma": "figma", "sketch": "sketch", "photoshop": "photoshop", "illustrator": "illustrator",
    "scrum": "scrum", "kanban": "kanban", "okr": "okr", "okrs": "okr", "sap": "sap",
    "salesforce": "salesforce", "hubspot": "hubspot", "lgpd": "lgpd", "gdpr": "gdpr",
    "iso 27001": "iso 27001", "itil": "itil", "cobit": "cobit", "pmp": "pmp", "cfa": "cfa",
    "contabilidade": "contabilidade", "fiscal": "fiscal", "auditoria": "auditoria",
    "enfermagem": "enfermagem", "nutrição": "nutricao", "nutricao": "nutricao",
    "fisioterapia": "fisioterapia", "psicologia": "psicologia", "pedagogia": "pedagogia",
    "direito": "direito", "arquitetura": "arquitetura", "engenharia civil": "engenharia civil",
    "mecânica": "mecanica", "mecanica": "mecanica", "elétrica": "eletrica", "eletrica": "eletrica",
    "logística": "logistica", "logistica": "logistica", "vendas": "vendas", "atendimento": "atendimento",
    "marketing": "marketing", "seo": "seo", "ads": "ads", "copywriting": "copywriting",
}


RED_FLAGS: dict[str, dict[str, Any]] = {
    "faixa-ausente": {
        "nivel": "media", "titulo": "Vaga sem faixa salarial",
        "texto": "O anúncio não declara remuneração.",
        "pergunta": "Qual é a faixa aprovada para este nível?",
    },
    "faixa-larga": {
        "nivel": "media", "titulo": "Faixa salarial larga demais",
        "texto": "A diferença entre o piso e o teto passa de metade do piso.",
        "pergunta": "O teto e o piso valem para este mesmo nível?",
    },
    "pj-para-clt": {
        "nivel": "alta", "titulo": "PJ no lugar de vínculo",
        "texto": "O anúncio fala em PJ, CNPJ ou prestação de serviço para uma rotina de emprego.",
        "pergunta": "O contrato é CLT ou PJ? Quais são os direitos previstos?",
    },
    "taxa-candidato": {
        "nivel": "alta", "titulo": "Cobrança do candidato",
        "texto": "O anúncio menciona taxa, curso pago ou material obrigatório.",
        "pergunta": "Alguma etapa exige pagamento do candidato?",
    },
    "sem-remuneracao": {
        "nivel": "alta", "titulo": "Trabalho sem remuneração",
        "texto": "A vaga profissional aparece sem bolsa, salário ou contrapartida declarada.",
        "pergunta": "A posição é remunerada? Qual é o valor?",
    },
    "jornada-critica": {
        "nivel": "alta", "titulo": "Jornada ou disponibilidade crítica",
        "texto": "O anúncio pede disponibilidade total, 6x1 ou plantão sem folga clara.",
        "pergunta": "Qual é a escala e como ficam os descansos?",
    },
    "exigencia-protegida": {
        "nivel": "alta", "titulo": "Requisito sobre dado protegido",
        "texto": "O anúncio cita idade, estado civil, filhos, aparência, religião ou sexo como requisito.",
        "pergunta": "Esse critério é realmente necessário para a função?",
    },
    "requisito-contraditorio": {
        "nivel": "alta", "titulo": "Requisitos que se contradizem",
        "texto": "Título, senioridade ou modelo de trabalho não combinam com o texto.",
        "pergunta": "A vaga é para qual senioridade e qual modelo?",
    },
    "vaga-antiga": {
        "nivel": "media", "titulo": "Anúncio antigo",
        "texto": "A vaga está publicada há mais de 60 dias.",
        "pergunta": "A posição continua aberta? Quando foi atualizada?",
    },
    "republicada": {
        "nivel": "media", "titulo": "Vaga republicada",
        "texto": "A mesma posição já foi publicada antes.",
        "pergunta": "A vaga foi reaberta ou é uma reposição?",
    },
    "triagem-automatica": {
        "nivel": "media", "titulo": "Triagem automática ou gravação",
        "texto": "O processo menciona IA, vídeo obrigatório ou teste gravado.",
        "pergunta": "Como os dados da triagem são usados e por quanto tempo ficam guardados?",
    },
    "local-incerto": {
        "nivel": "media", "titulo": "Local ou modelo indefinido",
        "texto": "O anúncio não deixa claro se é remoto, híbrido ou presencial.",
        "pergunta": "Qual é o modelo e a base territorial da vaga?",
    },
    "beneficio-vago": {
        "nivel": "baixa", "titulo": "Benefícios vagos",
        "texto": "Os benefícios aparecem sem valores, prazos ou condições.",
        "pergunta": "Quais benefícios são garantidos e a partir de quando?",
    },
}

CLICHES = (
    "apaixonado por", "apaixonada por", "paixão por", "paixao por", "orientado a resultados",
    "orientada a resultados", "proven track record", "track record", "hands-on", "mindset",
    "sinergia", "sinergias", "robusto", "robusta", "inovador", "inovadora", "disruptivo",
    "disruptiva", "seamless", "cutting-edge", "fast-paced", "work hard play hard",
    "vestibular", "família", "familia", "somos uma família", "somos uma familia",
    "dinâmico", "dinamico", "proativo", "proativa", "multitarefa", "multitasking",
    "result-oriented", "self-starter", "guru", "ninja", "rockstar", "jedi",
)

WEAK_OPENERS = (
    "responsável por", "responsavel por", "fui responsável", "fui responsavel",
    "ajudei", "ajudei a", "participei", "participei de", "trabalhei", "trabalhei com",
    "auxiliei", "auxiliei em", "colaborei", "colaborei com", "atuava", "atuava em",
    "era responsável", "era responsavel", "fazia", "realizava", "executava",
)

STRONG_VERBS = (
    "reduzi", "aumentei", "cortei", "liderei", "construí", "construi", "criei", "lancei",
    "migrei", "automatizei", "reorganizei", "implementei", "desenhei", "negociei",
    "escalei", "recuperei", "eliminei", "unifiquei", "medi", "documentei", "treinei",
    "substituí", "substitui", "simplifiquei", "priorizei", "conduzi", "fechei",
    "desenvolvi", "operei", "reconstruí", "reconstrui", "acelerei", "estabilizei",
)

PASSIVE_CUES = ("foi feito", "foram feitos", "foi realizado", "foi realizada", "são feitos", "sao feitos", "é realizado", "e realizado")

ATS_CHECKS: dict[str, dict[str, Any]] = {
    "texto": {"peso": 15, "titulo": "Texto selecionável", "regra": "pelo menos 300 caracteres legíveis"},
    "secoes": {"peso": 20, "titulo": "Cabeçalhos padrão", "regra": "experiência, formação e habilidades reconhecíveis"},
    "contato": {"peso": 15, "titulo": "E-mail no corpo", "regra": "e-mail visível fora de header/footer"},
    "coluna": {"peso": 20, "titulo": "Coluna única", "regra": "sem tabela de layout nem CSS multicoluna"},
    "imagem": {"peso": 10, "titulo": "Sem texto em imagem", "regra": "nenhum conteúdo essencial dentro de imagem"},
    "fonte": {"peso": 10, "titulo": "Fonte comum", "regra": "fonte embutível e amplamente disponível"},
    "utf8": {"peso": 5, "titulo": "UTF-8 declarado", "regra": "meta charset presente"},
    "oculto": {"peso": 5, "titulo": "Sem texto oculto", "regra": "sem display:none, branco no branco ou palavra repetida"},
}
GRADES = ((90, "A"), (80, "B"), (70, "C"), (60, "D"), (0, "F"))

STATES: dict[str, tuple[str, str]] = {
    "avaliada": ("Avaliada", "triagem feita, ainda sem envio"),
    "aplicada": ("Aplicada", "currículo enviado"),
    "respondeu": ("Respondeu", "a empresa entrou em contato"),
    "teste": ("Teste", "desafio técnico ou case em andamento"),
    "entrevista": ("Entrevista", "conversa marcada ou feita"),
    "oferta": ("Oferta", "proposta recebida"),
    "recusada": ("Recusada", "a empresa recusou"),
    "descartada": ("Descartada", "você desistiu ou a vaga fechou"),
    "pulada": ("Pulada", "não aplicável; não envie"),
    "contratada": ("Contratada", "processo terminou com contratação"),
}
STATE_ALIASES: dict[str, str] = {
    "avaliada": "avaliada", "avaliado": "avaliada", "evaluated": "avaliada",
    "aplicada": "aplicada", "aplicado": "aplicada", "applied": "aplicada", "enviada": "aplicada",
    "respondeu": "respondeu", "responded": "respondeu", "retorno": "respondeu",
    "teste": "teste", "assessment": "teste", "desafio": "teste", "case": "teste",
    "entrevista": "entrevista", "interview": "entrevista",
    "oferta": "oferta", "offer": "oferta", "proposta": "oferta",
    "recusada": "recusada", "recusado": "recusada", "rejected": "recusada", "rejeitada": "recusada",
    "descartada": "descartada", "descartado": "descartada", "discarded": "descartada",
    "pulada": "pulada", "pulado": "pulada", "skip": "pulada",
    "contratada": "contratada", "contratado": "contratada", "hired": "contratada",
}
ACTIVE_STATES = {"aplicada", "respondeu", "teste", "entrevista", "oferta"}

QUESTION_BANK = {
    "comportamental": (
        "Conte uma situação concreta em que você trabalhou com {topico}. O que mudou?",
        "Qual foi o erro mais caro que você cometeu em {topico}? O que aprendeu?",
        "Como você convenceu alguém a mudar de ideia sobre {topico}?",
    ),
    "tecnica": (
        "Como você escolheria entre duas abordagens para {topico}?",
        "Qual trade-off você já assumiu em {topico}?",
        "Como você mediria sucesso em {topico} nos primeiros 90 dias?",
    ),
    "gestao": (
        "Como você lidou com prioridades conflitantes em {topico}?",
        "Como você deu um retorno difícil sobre {topico}?",
        "Como você distribuiu trabalho quando {topico} estava atrasado?",
    ),
    "produto": (
        "Como você descobriu que {topico} era o problema certo?",
        "O que você cortaria do escopo para entregar {topico} antes?",
        "Como você mediu o impacto de {topico}?",
    ),
}



# ------------------------------------------------------------ texto

def _norm(value: str) -> str:
    text = unicodedata.normalize("NFKD", value or "")
    return "".join(ch for ch in text if not unicodedata.combining(ch)).lower()


def _clean(value: str, limit: int = 2000) -> str:
    text = re.sub(r"[ \t\r\f\v]+", " ", str(value or "")).strip()
    return text[:limit]


def _lines(text: str) -> list[str]:
    return [_clean(line, 600) for line in str(text or "").splitlines() if _clean(line, 600)]


def _cap(name: str, value: str, limit: int) -> str:
    text = str(value or "")
    if len(text) > limit:
        raise CareerError(
            "O campo {0} tem {1} caracteres; o limite desta skill é {2}. "
            "Recorte o texto e tente de novo.".format(name, len(text), limit)
        )
    return text


def _as_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    text = _norm(str(value)).strip()
    if text in {"true", "sim", "1", "yes", "on"}:
        return True
    if text in {"false", "nao", "0", "no", "off"}:
        return False
    return default


def _as_int(value: Any, default: int, low: int = 0, high: int = 10_000) -> int:
    try:
        number = int(float(value))
    except (TypeError, ValueError):
        return default
    return max(low, min(high, number))


DISPLAY_TERMS = {
    "python": "Python", "javascript": "JavaScript", "typescript": "TypeScript",
    "node": "Node.js", "nodejs": "Node.js", "react": "React", "next": "Next.js",
    "vue": "Vue", "angular": "Angular", "svelte": "Svelte", "java": "Java",
    "kotlin": "Kotlin", "swift": "Swift", "go": "Go", "golang": "Go", "rust": "Rust",
    "ruby": "Ruby", "php": "PHP", "c++": "C++", "c#": "C#", "sql": "SQL",
    "postgres": "PostgreSQL", "postgresql": "PostgreSQL", "mysql": "MySQL",
    "mongodb": "MongoDB", "redis": "Redis", "elasticsearch": "Elasticsearch",
    "aws": "AWS", "gcp": "GCP", "azure": "Azure", "docker": "Docker",
    "kubernetes": "Kubernetes", "terraform": "Terraform", "graphql": "GraphQL",
    "rest": "REST", "api": "API", "apis": "APIs", "html": "HTML", "css": "CSS",
    "git": "Git", "linux": "Linux", "figma": "Figma", "excel": "Excel",
    "power": "Power", "powerbi": "Power BI", "tableau": "Tableau", "looker": "Looker",
    "sap": "SAP", "salesforce": "Salesforce", "hubspot": "HubSpot", "scrum": "Scrum",
    "kanban": "Kanban", "jira": "Jira", "ci/cd": "CI/CD", "tdd": "TDD", "bdd": "BDD",
    "ml": "ML", "ia": "IA", "ai": "IA", "nlp": "NLP", "llm": "LLM", "llms": "LLMs",
    "seo": "SEO", "crm": "CRM", "erp": "ERP", "bi": "BI", "etl": "ETL", "elt": "ELT",
    "qa": "QA", "ux": "UX", "ui": "UI", "pmp": "PMP", "cpa": "CPA", "cfa": "CFA",
}


def _display_term(term: str) -> str:
    return DISPLAY_TERMS.get(term, term)


def _norm_first(text: str) -> str:
    """Minúscula na primeira letra, preservando nomes próprios já conhecidos."""
    clean = _clean(text, 400)
    if not clean:
        return ""
    first = clean.split(" ", 1)[0]
    if _display_term(_norm(first)) != _norm(first) or _norm(first) in DISPLAY_TERMS:
        return clean
    if re.match(r"^[A-ZÁÉÍÓÚÂÊÔÃÕÇ][a-záéíóúâêôãõç]+$", first) and _norm(first) not in {
        "construir", "manter", "modelar", "revisar", "experi", "conheci", "disponi", "lidere", "atuar"
    }:
        return clean
    return clean[:1].lower() + clean[1:]


def _truncate(text: str, limit: int) -> str:
    text = _clean(text, limit + 1)
    if len(text) <= limit:
        return text
    cut = text[: limit - 1].rsplit(" ", 1)[0]
    return (cut or text[: limit - 1]) + "…"


def _sentences(text: str) -> list[str]:
    blocks: list[str] = []
    for line in _lines(text):
        for piece in re.split(r"(?<=[.!?;])\s+", line):
            piece = _clean(piece, 900)
            if len(piece) > 3:
                blocks.append(piece)
    return blocks


def _unique(items: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        key = _norm(item)
        if key and key not in seen:
            seen.add(key)
            out.append(item)
    return out


def _tokens(text: str) -> list[str]:
    raw = re.findall(r"[a-zA-ZÀ-ÿ][a-zA-ZÀ-ÿ0-9+#./-]*", _norm(text))
    return [token.strip(".,;:()[]") for token in raw if len(token) >= 3]


def _content_tokens(text: str) -> list[str]:
    return [token for token in _tokens(text) if token not in STOPWORDS and len(token) >= 4]


def _tech_terms(text: str) -> list[str]:
    low = " " + _norm(text).replace("\n", " ") + " "
    found: list[tuple[int, str]] = []
    for alias in TECH_ALIASES:
        needle = _norm(alias)
        pattern = r"(?<![a-z0-9+#.])" + re.escape(needle) + r"(?![a-z0-9+#])"
        match = re.search(pattern, low)
        if match:
            canonical = TECH_ALIASES[alias]
            if canonical not in [item[1] for item in found]:
                found.append((match.start(), canonical))
    found.sort(key=lambda item: item[0])
    return [canonical for _, canonical in found]


def _keyword_set(text: str) -> set[str]:
    return set(_tech_terms(text)) | set(_content_tokens(text))


def _number_hits(text: str) -> list[str]:
    pattern = r"(?:R\$|US\$|\$|€|£)?\s?\d[\d.,]*\s?(?:%|x|k|mil|milh(?:ão|ao|ões|oes)?|bi|pts?|dias?|horas?|min|ms|s\b|sem|meses?)"
    return [_clean(m.group(0), 40) for m in re.finditer(pattern, text)]


def _has_metric(text: str) -> bool:
    if not re.search(r"\d", text):
        return False
    if _number_hits(text):
        return True
    stripped = re.sub(r"\b(?:19|20)\d{2}\b", " ", text)
    stripped = re.sub(r"\b\d{1,2}/\d{1,2}(?:/\d{2,4})?\b", " ", stripped)
    return bool(re.search(r"\b\d{1,5}\b", stripped))


def _parse_number(raw: str) -> float | None:
    text = _clean(raw, 30).replace(" ", "")
    if not text:
        return None
    text = re.sub(r"[^\d.,kKmM]", "", text)
    if not text:
        return None
    multiplier = 1.0
    if text[-1] in "kK":
        multiplier = 1_000.0
        text = text[:-1]
    elif text[-1] in "mM":
        multiplier = 1_000_000.0
        text = text[:-1]
    if re.fullmatch(r"\d{1,3}(?:,\d{3})+", text):
        text = text.replace(",", "")
    elif re.fullmatch(r"\d{1,3}(?:\.\d{3})+", text):
        text = text.replace(".", "")
    elif "," in text and "." in text:
        if text.rfind(",") > text.rfind("."):
            text = text.replace(".", "").replace(",", ".")
        else:
            text = text.replace(",", "")
    elif "," in text:
        head, _, tail = text.partition(",")
        text = head + "." + tail
    try:
        return float(text) * multiplier
    except ValueError:
        return None


CURRENCY_PATTERNS = (
    ("BRL", r"(?:R\$|brl|reais)"),
    ("USD", r"(?:US\$|usd|dólares|dolares)"),
    ("EUR", r"(?:€|eur|euros)"),
    ("GBP", r"(?:£|gbp|libras)"),
)

COMP_RANGE = re.compile(
    r"(?P<cur>R\$|US\$|\$|€|£)?\s*(?P<low>\d[\d.,]*\s?[kK]?)\s*(?:-|–|—|a|até|ate|to)\s*(?P<cur2>R\$|US\$|\$|€|£)?\s*(?P<high>\d[\d.,]*\s?[kK]?)",
)


def parse_comp(text: str) -> dict[str, Any]:
    """Extrai faixa, moeda e periodicidade sem adivinhar o que não está escrito."""
    raw = _clean(text, 500)
    low_norm = _norm(raw)
    currency = ""
    for code, pattern in CURRENCY_PATTERNS:
        if re.search(pattern, low_norm, re.I):
            currency = code
            break
    if not currency and "$" in low_norm:
        currency = "USD"
    period = ""
    if re.search(r"(?:/|por\s*)(?:mês|mes|month)", low_norm) or re.search(r"\b(?:mensal|monthly)\b", low_norm):
        period = "mês"
    elif re.search(r"\b(?:anual|ano|year|yearly|annual|annually|p\.?a\.?)\b|/\s*(?:ano|year)", low_norm):
        period = "ano"
    elif re.search(r"\b(?:hora|hour|hourly)\b", low_norm):
        period = "hora"
    elif re.search(r"\b(?:semana|week|weekly)\b", low_norm):
        period = "semana"
    match = COMP_RANGE.search(raw)
    low = high = None
    if match:
        low = _parse_number(match.group("low"))
        high = _parse_number(match.group("high"))
        if low is not None and high is not None and low > high:
            low, high = high, low
    else:
        single = re.search(r"(?:R\$|US\$|\$|€|£)\s*(\d[\d.,]*\s?[kK]?)", raw)
        if single:
            low = high = _parse_number(single.group(1))
    return {
        "texto": raw,
        "moeda": currency,
        "periodo": period,
        "piso": low,
        "teto": high,
        "declarada": low is not None and high is not None and period != "",
    }


def _normalize_period(value: Any) -> str:
    text = _norm(str(value or ""))
    if not text:
        return ""
    if re.search(r"mes\b|mensal|month", text):
        return "mês"
    if re.search(r"ano\b|anual|annual|year", text):
        return "ano"
    if "hora" in text or "hour" in text:
        return "hora"
    if "semana" in text or "week" in text:
        return "semana"
    return ""


def comp_yearly(amount: float | None, period: str) -> float | None:
    if amount is None:
        return None
    factor = {"ano": 1.0, "mês": 12.0, "semana": 52.0, "hora": 2080.0}.get(period)
    if not factor:
        return None
    return amount * factor


def _age_days(value: str) -> int | None:
    text = _norm(value).strip()
    if not text:
        return None
    today = date.today()
    match = re.search(r"(\d{4})-(\d{2})-(\d{2})", text)
    if match:
        try:
            return max(0, (today - date(int(match.group(1)), int(match.group(2)), int(match.group(3)))).days)
        except ValueError:
            return None
    match = re.search(r"há\s+(\d+)\s*(dias?|semanas?|meses?|mes)", text)
    if match:
        amount = int(match.group(1))
        unit = match.group(2)
        factor = 1 if unit.startswith("dia") else 7 if unit.startswith("semana") else 30
        return amount * factor
    return None


# ------------------------------------------------------------ perfil



def _yaml_scalar(text: str) -> Any:
    value = text.strip()
    if not value:
        return ""
    if value[0] in "\"'" and value[-1:] == value[0] and len(value) >= 2:
        return value[1:-1]
    low = _norm(value)
    if low in {"true", "sim", "yes"}:
        return True
    if low in {"false", "nao", "no"}:
        return False
    if low in {"null", "~", "none"}:
        return None
    if value.startswith("[") and value.endswith("]"):
        return [_yaml_scalar(part) for part in value[1:-1].split(",") if part.strip()]
    if re.fullmatch(r"-?\d+", value):
        return int(value)
    if re.fullmatch(r"-?\d+\.\d+", value):
        return float(value)
    return value


def parse_yaml_subset(text: str) -> dict[str, Any]:
    """Lê o subconjunto de YAML usado por perfis: mapas indentados, listas e escalares."""
    root: dict[str, Any] = {}
    stack: list[tuple[int, Any]] = [(-1, root)]
    lines = str(text or "").splitlines()
    for raw in lines:
        if not raw.strip() or raw.strip().startswith("#"):
            continue
        indent = len(raw) - len(raw.lstrip(" "))
        line = raw.strip()
        while stack and indent <= stack[-1][0]:
            stack.pop()
        if not stack:
            stack = [(-1, root)]
        parent = stack[-1][1]
        if line.startswith("- "):
            item = line[2:].strip()
            if not isinstance(parent, list):
                continue
            if ":" in item and not item.startswith(("'", '"')):
                key, _, rest = item.partition(":")
                obj: dict[str, Any] = {}
                if rest.strip():
                    obj[key.strip()] = _yaml_scalar(rest)
                parent.append(obj)
                stack.append((indent, obj))
            else:
                parent.append(_yaml_scalar(item))
        elif ":" in line:
            key, _, rest = line.partition(":")
            key = key.strip()
            rest = rest.strip()
            if not isinstance(parent, dict):
                continue
            if rest:
                parent[key] = _yaml_scalar(rest)
            else:
                child: Any = {}
                following = next(
                    (ln for ln in lines[lines.index(raw) + 1:] if ln.strip() and not ln.strip().startswith("#")),
                    "",
                )
                if following.strip().startswith("- "):
                    child = []
                parent[key] = child
                stack.append((indent, child))
    return root


def _walk_values(data: Any, path: str = "") -> list[tuple[str, Any]]:
    out: list[tuple[str, Any]] = []
    if isinstance(data, dict):
        for key, value in data.items():
            out.extend(_walk_values(value, (path + "." + str(key)).strip(".")))
    elif isinstance(data, list):
        for item in data:
            out.extend(_walk_values(item, path))
    else:
        out.append((path, data))
    return out


@dataclass
class Profile:
    nome: str = ""
    titulo: str = ""
    email: str = ""
    local: str = ""
    anos: int = 0
    senioridade: str = ""
    alvo: str = ""
    alvos: list[str] = field(default_factory=list)
    dominios: list[str] = field(default_factory=list)
    palavras: list[str] = field(default_factory=list)
    superpoderes: list[str] = field(default_factory=list)
    provas: list[str] = field(default_factory=list)
    salario_minimo: float | None = None
    alvo_salarial: float | None = None
    moeda: str = ""
    periodo: str = "ano"
    modelo: str = ""
    autorizacao: str = ""
    necessita_visto: bool = False
    pcd: bool = False
    idiomas: dict[str, str] = field(default_factory=dict)
    regras: list[str] = field(default_factory=list)
    campos: dict[str, Any] = field(default_factory=dict)
    origem: str = "texto"


def parse_profile(text: str) -> Profile:
    _cap("perfil", text, MAX_PERFIL)
    data = parse_yaml_subset(text)
    flat: dict[str, Any] = {}
    for path, value in _walk_values(data):
        flat[path] = value
    if not flat:
        return Profile(origem="vazio")

    index: dict[str, Any] = {}

    def index_walk(node: Any) -> None:
        if isinstance(node, dict):
            for key_raw, value_raw in node.items():
                key = str(key_raw)
                if value_raw not in ("", None, [], {}):
                    index.setdefault(key, value_raw)
                index_walk(value_raw)
        elif isinstance(node, list):
            for item in node:
                index_walk(item)

    index_walk(data)

    def pick(*names: str) -> Any:
        for name in names:
            if name in index and index[name] not in ("", None, [], {}):
                return index[name]
            for path, value in flat.items():
                leaf = path.rsplit(".", 1)[-1]
                if leaf == name and value not in ("", None, []):
                    return value
        return None

    def strings(*names: str) -> list[str]:
        value = pick(*names)
        if isinstance(value, list):
            return [_clean(str(item), 200) for item in value if str(item).strip()]
        if isinstance(value, str) and value.strip():
            return [_clean(part, 200) for part in re.split(r"[;|]", value) if part.strip()]
        return []

    profile = Profile(origem="yaml")
    profile.nome = _clean(str(pick("full_name", "nome", "name") or ""), 120)
    profile.titulo = _clean(str(pick("headline", "titulo", "title", "cargo") or ""), 160)
    profile.email = _clean(str(pick("email", "e-mail") or ""), 160)
    profile.local = _clean(str(pick("location", "local", "cidade") or ""), 160)
    anos = pick("years_experience", "anos_experiencia", "anos")
    profile.anos = _as_int(anos, 0, 0, 60)
    profile.senioridade = _clean(str(pick("seniority", "senioridade", "nivel") or ""), 60)
    profile.alvo = _clean(str(pick("target_role", "alvo", "objetivo") or ""), 200)
    profile.alvos = _unique(strings("alvos", "targets", "archetypes") or ([profile.alvo] if profile.alvo else []))
    profile.dominios = _unique(strings("domains", "dominios") + strings("industry", "industria"))
    profile.palavras = _unique(strings("keywords", "palavras_chave", "skills"))
    profile.superpoderes = _unique(strings("superpowers", "superpoderes"))
    profile.provas = _unique(strings("proof_points", "provas", "achievements"))
    minimum = pick("minimum", "salario_minimo", "minimo")
    target = pick("target_range", "alvo_salarial", "faixa_alvo", "target")
    profile.moeda = _clean(str(pick("currency", "moeda") or ""), 8).upper()
    if isinstance(minimum, str):
        profile.salario_minimo = parse_comp(minimum).get("piso")
    elif isinstance(minimum, (int, float)):
        profile.salario_minimo = float(minimum)
    if isinstance(target, str):
        comp = parse_comp(target)
        profile.alvo_salarial = comp.get("teto") or comp.get("piso")
        profile.moeda = profile.moeda or str(comp.get("moeda") or "")
    elif isinstance(target, (int, float)):
        profile.alvo_salarial = float(target)
    profile.periodo = _normalize_period(pick("periodo", "period", "comp_period"))
    if not profile.periodo:
        profile.periodo = str(parse_comp(str(pick("salario_minimo", "minimum", "target_range") or "")).get("periodo") or "")
    profile.modelo = _norm(str(pick("work_model", "modelo", "remote") or ""))
    profile.autorizacao = _clean(str(pick("visa_status", "autorizacao", "work_authorization") or ""), 160)
    profile.necessita_visto = _as_bool(pick("needs_sponsorship", "necessita_visto"), False)
    profile.pcd = _as_bool(pick("pcd", "disability"), False)
    languages = pick("languages", "idiomas")
    if isinstance(languages, dict):
        profile.idiomas = {
            _clean(str(k2), 40): _clean(str(v2), 40)
            for k2, v2 in languages.items() if not isinstance(v2, (dict, list))
        }
    elif isinstance(languages, list):
        for item in languages:
            if isinstance(item, dict):
                for k2, v2 in item.items():
                    profile.idiomas[_clean(str(k2), 40)] = _clean(str(v2), 40)
    rules = strings("dealbreakers", "regras", "nao_negociaveis", "hard_skips")
    for _, value in flat.items():
        if isinstance(value, str) and _norm(value).startswith("dealbreaker"):
            rules.append(_clean(value, 200))
    profile.regras = _unique(rules)
    profile.campos = flat
    if profile.salario_minimo is not None:
        profile.campos["_minimo"] = profile.salario_minimo
    return profile


# ------------------------------------------------------------ currículo

CV_HEADINGS = {
    "experiencia": ("experiência", "experiencia", "experiência profissional", "professional experience", "histórico profissional"),
    "formacao": ("formação", "formacao", "educação", "educacao", "education", "formação acadêmica"),
    "habilidades": ("habilidades", "competências", "competencias", "skills", "tecnologias", "stack"),
    "projetos": ("projetos", "projects", "portfólio", "portfolio"),
    "resumo": ("resumo", "summary", "perfil", "sobre", "objetivo"),
    "idiomas": ("idiomas", "languages"),
    "certificacoes": ("certificações", "certificacoes", "certificados", "cursos", "certifications"),
}


def _heading_key(line: str) -> str | None:
    stripped = _clean(line, 120).strip("#*-• ").rstrip(":").strip()
    low = _norm(stripped)
    for key, names in CV_HEADINGS.items():
        if low in {_norm(name) for name in names}:
            return key
    return None


@dataclass
class Bullet:
    texto: str
    secao: str
    linha: int
    metrica: bool
    verbo: str
    passivo: bool
    cliche: list[str]
    tamanho: int


@dataclass
class Curriculum:
    texto: str
    nome: str = ""
    email: str = ""
    telefone: str = ""
    secoes: dict[str, list[str]] = field(default_factory=dict)
    bullets: list[Bullet] = field(default_factory=list)
    termos: set[str] = field(default_factory=set)
    idiomas: dict[str, str] = field(default_factory=dict)
    metricas: int = 0
    datas: list[str] = field(default_factory=list)


def parse_cv(text: str) -> Curriculum:
    _cap("curriculo", text, MAX_CURRICULO)
    cv = Curriculum(texto=text)
    current = "geral"
    cv.secoes[current] = []
    for index, line in enumerate(_lines(text)):
        key = _heading_key(line)
        if key:
            current = key
            cv.secoes.setdefault(current, [])
            continue
        clean = _clean(line.lstrip("#*-• "), 600)
        if clean:
            cv.secoes.setdefault(current, []).append(clean)
            low = _norm(clean)
            bullet_like = bool(re.match(r"^[•\-*·▪◦]", line.strip())) or (len(clean) > 60 and line.strip()[:1] not in "#|")
            if bullet_like:
                verbos = [v for v in STRONG_VERBS if low.startswith(v)]
                cv.bullets.append(
                    Bullet(
                        texto=clean,
                        secao=current,
                        linha=index + 1,
                        metrica=_has_metric(clean),
                        verbo=verbos[0] if verbos else "",
                        passivo=any(cue in low for cue in PASSIVE_CUES),
                        cliche=[cliche for cliche in CLICHES if _norm(cliche) in low],
                        tamanho=len(clean),
                    )
                )
    for line in _lines(text)[:3]:
        if "@" in line:
            match = re.search(r"[\w.+-]+@[\w-]+\.[\w.]+", line)
            if match:
                cv.email = match.group(0)
            break
    for line in _lines(text)[:6]:
        phone = re.search(r"(?:\+?\d{2}[\s-]?)?\(?\d{2,3}\)?[\s-]?\d{4,5}[\s-]?\d{4}", line)
        if phone and not re.search(r"\b(?:19|20)\d{2}\b", phone.group(0)):
            cv.telefone = phone.group(0)
            break
    first = _lines(text)[0] if _lines(text) else ""
    cv.nome = _clean(first.strip("# "), 120) if len(first) < 60 and "@" not in first and not re.search(r"\d{3}", first) else ""
    cv.termos = _keyword_set(text)
    cv.metricas = sum(1 for bullet in cv.bullets if bullet.metrica)
    cv.datas = re.findall(r"\b(?:19|20)\d{2}\b|(?:jan|fev|mar|abr|mai|jun|jul|ago|set|out|nov|dez)[a-z]*\.?\s*/?\s*(?:19|20)?\d{2}", _norm(text))
    for key in ("idiomas", "languages"):
        for line in cv.secoes.get("idiomas", []):
            parts = re.split(r"[:–-]", line, maxsplit=1)
            if len(parts) == 2:
                cv.idiomas[_clean(parts[0], 40)] = _clean(parts[1], 60)
    return cv


# ------------------------------------------------------------ vaga

COMPANY_TYPES: dict[str, dict[str, Any]] = {
    "bigtech": {
        "rotulo": "Big tech / tecnologia madura", "confiabilidade": "alta",
        "sinais": ("big tech", "multinacional de tecnologia", "faang", "empresa listada",
                   "companhia aberta", "billions", "bilhões em receita", "açõe", "ações na bolsa"),
        "porque": "níveis públicos e banda estruturada costumam acompanhar a faixa anunciada",
    },
    "growth": {
        "rotulo": "Startup em crescimento", "confiabilidade": "media",
        "sinais": ("startup", "scale-up", "série a", "serie a", "série b", "serie b",
                   "venture", "vc-backed", "rodada"),
        "porque": "faixa plausível, mas base, bônus e equity costumam vir misturados",
    },
    "early": {
        "rotulo": "Startup inicial / pré-receita", "confiabilidade": "baixa",
        "sinais": ("pré-receita", "pre-receita", "early stage", "pré-seed", "pre-seed", "seed",
                   "time pequeno", "primeiros funcionários", "primeiros funcionarios"),
        "porque": "escopo e caixa mudam rápido; equity costuma ocupar o lugar de salário",
    },
    "enterprise": {
        "rotulo": "Corporação tradicional", "confiabilidade": "media",
        "sinais": ("multinacional", "grupo empresarial", "holding", "conglomerado", "indústria",
                   "industria", "banco tradicional", "seguradora", "varejo"),
        "porque": "base estável, banda lenta e bônus frequentemente discricionário",
    },
    "agencia": {
        "rotulo": "Agência / consultoria / outsourcing", "confiabilidade": "baixa",
        "sinais": ("agência", "agencia", "consultoria", "outsourcing", "alocação", "alocacao",
                   "alocado em cliente", "body shop", "prestação de serviços", "prestacao de servicos"),
        "porque": "o número pode refletir o contrato com o cliente, não o seu pacote",
    },
    "smb": {
        "rotulo": "PME / negócio local", "confiabilidade": "baixa",
        "sinais": ("pequena empresa", "empresa familiar", "comércio local", "comercio local",
                   "filial", "loja", "restaurante", "clínica", "clinica"),
        "porque": "RH informal e faixa frequentemente dita por orçamento do momento",
    },
    "comissionada": {
        "rotulo": "Vendas / comissão", "confiabilidade": "baixa",
        "sinais": ("comissão", "comissao", "ote", "on-target", "uncapped", "sem teto",
                   "variável", "variavel", "meta de vendas", "100% variável"),
        "porque": "sem base explícita, o número anunciado é cenário, não garantia",
    },
    "recrutadora": {
        "rotulo": "Recrutadora / staffing", "confiabilidade": "media",
        "sinais": ("recrutadora", "consultoria de recrutamento", "headhunter", "staffing",
                   "terceirização", "terceirizacao", "nossa consultoria", "para um cliente"),
        "porque": "a faixa é do cliente e pode mudar na proposta",
    },
    "publico": {
        "rotulo": "Governo / academia / terceiro setor", "confiabilidade": "alta",
        "sinais": ("governo", "prefeitura", "secretaria", "universidade", "instituto federal",
                   "ong", "organização sem fins", "organizacao sem fins", "fundação", "fundacao",
                   "edital", "concurso"),
        "porque": "faixas publicadas, ainda que abaixo do mercado",
    },
    "oss": {
        "rotulo": "Comunidade open source / educação", "confiabilidade": "baixa",
        "sinais": ("open source", "código aberto", "codigo aberto", "comunidade", "foundation",
                   "fundação de software", "bootcamp", "escola de tecnologia"),
        "porque": "entidade empregadora e orçamento raramente aparecem no anúncio",
    },
}
COMP_RELIABILITY = {
    "alta": "Faixa declarada como base ou sustentada por banda pública.",
    "media": "Faixa plausível, mas os componentes não vêm separados.",
    "baixa": "O número pode incluir variável, comissão, subsídio ou um 'até'.",
    "desconhecida": "Sem dado de salário utilizável.",
}


def classify_company(text: str) -> dict[str, Any]:
    low = _norm(text)
    best: tuple[int, str] | None = None
    for key, data in COMPANY_TYPES.items():
        score = sum(1 for signal in data["sinais"] if _norm(signal) in low)
        if score and (best is None or score > best[0]):
            best = (score, key)
    if not best:
        return {
            "tipo": "nao-classificada", "rotulo": "Empresa não classificada",
            "confiabilidade": "baixa",
            "porque": "sem sinal de porte ou modelo no anúncio; trate a faixa como não verificada",
            "evidencia": "",
        }
    data = COMPANY_TYPES[best[1]]
    signal = next((s for s in data["sinais"] if _norm(s) in low), "")
    return {
        "tipo": best[1], "rotulo": data["rotulo"], "confiabilidade": data["confiabilidade"],
        "porque": data["porque"], "evidencia": signal,
    }


@dataclass
class Requirement:
    texto: str
    banda: str = "meaningful"
    evidencia: str = "structural"
    casamento: str = "indefinido"
    prova: list[str] = field(default_factory=list)
    motivo: str = ""
    origem: str = ""


@dataclass
class Job:
    texto: str
    titulo: str = ""
    empresa: str = ""
    local: str = ""
    modelo: str = ""
    senioridade: str = ""
    requisitos: list[Requirement] = field(default_factory=list)
    responsabilidades: list[str] = field(default_factory=list)
    beneficios: list[str] = field(default_factory=list)
    empresa_txt: str = ""
    comp: dict[str, Any] = field(default_factory=dict)
    empresa_tipo: dict[str, Any] = field(default_factory=dict)
    termos: list[str] = field(default_factory=list)
    publicado: int | None = None
    idioma_exigido: str = ""
    sinais: list[dict[str, Any]] = field(default_factory=list)
    legitimidade: str = "cautela"
    legitimidade_nota: int = 0
    bloquear_por_idade: bool = False
    republicada: bool = False
    agencia: bool = False


def _section_of(line: str) -> str | None:
    stripped = _clean(line, 120).strip("#*-• ").rstrip(":").strip()
    if len(stripped) > 70:
        return None
    low = _norm(stripped)
    for key, names in SECTIONS.items():
        for name in names:
            name_norm = _norm(name)
            if low == name_norm or low.startswith(name_norm + " ") or low.endswith(" " + name_norm):
                return key
    return None


def _importance(text: str, section: str, title: str, must: bool, preferred: bool) -> tuple[str, str]:
    low = _norm(text)
    legal = any(term in low for term in ("clt", "pj", "cnpj", "autorização de trabalho", "autorizacao de trabalho",
                                         "visto", "work authorization", "residência", "residencia", "carteira de motorista",
                                         "crm", "oab", "cre", "registro no conselho", "inglês fluente", "ingles fluente",
                                         "inglês avançado", "ingles avancado", "inglês intermediário", "ingles intermediario",
                                         "nivel de ingles", "nível de inglês", "english level"))
    in_title = any(token in _norm(title) for token in _content_tokens(text)[:3]) if title else False
    if must or legal or in_title:
        return "critical", "stated"
    if preferred:
        return "preferred", "stated"
    if section == "requisitos":
        return "high", "structural"
    if section == "responsabilidades":
        return "meaningful", "inferred"
    return "low_signal", "inferred"


def parse_job(text: str) -> Job:
    _cap("vaga", text, MAX_VAGA)
    lines = _lines(text)
    job = Job(texto=text)
    if not lines:
        raise CareerError("A vaga está vazia. Cole o texto do anúncio para a triagem.")

    labeled = {}
    for line in lines[:40]:
        match = re.match(r"^(cargo|vaga|posição|posicao|título|titulo|empresa|company|local|localização|localizacao|modelo|modalidade|publicad[ao]|data)\s*[:\-]\s*(.+)$", line, re.I)
        if match:
            labeled[_norm(match.group(1))] = _clean(match.group(2), 200)
    job.titulo = labeled.get("cargo") or labeled.get("vaga") or labeled.get("posicao") or labeled.get("titulo") or ""
    job.empresa = labeled.get("empresa") or labeled.get("company") or ""
    job.local = labeled.get("local") or labeled.get("localizacao") or ""
    job.modelo = _clean(labeled.get("modelo") or labeled.get("modalidade") or "", 40)
    if not job.titulo:
        candidates = [line for line in lines[:6] if 6 <= len(line) <= 110 and not line.endswith(":")]
        job.titulo = candidates[0].lstrip("# ").strip() if candidates else ""
    if not job.empresa:
        for line in lines[:12]:
            match = re.search(r"(?:na|no|@)\s+([A-Z][\w&.\- ]{2,40})", line)
            if match and not re.search(r"\b(?:vaga|cargo|posição|posicao)\b", _norm(line)):
                job.empresa = _clean(match.group(1), 80)
                break
    low_full = _norm(text)
    if not job.modelo:
        if re.search(r"\bremoto\b|\bremote\b|\bhome office\b|\b100% home\b", low_full):
            job.modelo = "remoto"
        elif "híbrido" in low_full or "hibrido" in low_full or "hybrid" in low_full:
            job.modelo = "híbrido"
        elif "presencial" in low_full or "on-site" in low_full:
            job.modelo = "presencial"

    for level in ("estágio", "estagio", "júnior", "junior", "pleno", "sênior", "senior", "especialista", "lead", "gerente", "diretor"):
        if re.search(r"\b" + re.escape(_norm(level)) + r"\b", low_full):
            job.senioridade = level
            break
    for lang in ("inglês", "ingles", "espanhol", "francês", "frances", "alemão", "alemao", "mandarim"):
        if re.search(r"\b" + re.escape(_norm(lang)) + r"\b.{0,60}\b(?:fluente|avançado|avancado|nativo|intermediário|intermediario|básico|basico|obrigatório|obrigatorio)", low_full):
            job.idioma_exigido = lang

    section = "geral"
    buckets: dict[str, list[tuple[str, str]]] = {"requisitos": [], "responsabilidades": [], "diferenciais": [], "beneficios": [], "empresa": [], "geral": []}
    for line in lines:
        key = _section_of(line)
        if key:
            section = key
            continue
        clean = _clean(line.lstrip("•-*·▪ "), 600)
        if not clean:
            continue
        bullet = bool(re.match(r"^\s*(?:[•\-*·▪◦]|\d+[.)])\s+", line))
        target = section if section in buckets else "geral"
        if not bullet and section == "geral" and _section_of(clean):
            continue
        buckets[target].append((clean, section))

    seen: set[str] = set()
    if job.titulo:
        req = Requirement(texto=job.titulo, banda="critical", evidencia="stated", origem="titulo")
        seen.add(_norm(job.titulo))
        job.requisitos.append(req)
    for clean, sec in buckets["requisitos"] + buckets["diferenciais"] + buckets["responsabilidades"]:
        low = _norm(clean)
        if len(clean) < 4 or len(clean) > 320:
            continue
        if re.match(r"^(?:remunera|salario|salário|publicad|local|modelo|empresa|vaga|cargo|benef|contrat|jornada|horario|horário|data)\s*[:\-]", low):
            continue
        if any(generic in low for generic in GENERIC_TERMS) and len(_content_tokens(clean)) <= 4:
            band, evi = "low_signal", "structural"
        else:
            must = any(cue in low for cue in MUST_CUES) or any(
                stem in low for stem in ("obrigatori", "imprescind", "exigid", "exigênc", "exigenc", "indispens", "requisito"))

            preferred = sec == "diferenciais" or any(cue in low for cue in PREFERRED_CUES)
            band, evi = _importance(clean, sec, job.titulo, must, preferred)
        key = _norm(re.sub(r"[^\w\s]", "", clean))[:120]
        if key in seen:
            continue
        seen.add(key)
        if evi == "inferred" and band in ("critical", "high"):
            band = "meaningful"
        job.requisitos.append(Requirement(texto=clean, banda=band, evidencia=evi, origem=sec))
    job.responsabilidades = [text for text, _ in buckets["responsabilidades"]][:12]
    job.beneficios = [text for text, _ in buckets["beneficios"]][:12]
    job.empresa_txt = " ".join(text for text, _ in buckets["empresa"])[:2000]

    comp_line = ""
    for line in lines:
        low = _norm(line)
        if re.search(r"(?:r\$|us\$|\$|€|£)\s*\d", line) or re.search(r"\b(?:salário|salario|faixa|remuneração|remuneracao|compensation|salary)\b", low):
            if COMP_RANGE.search(line) or re.search(r"\b(?:salário|salario|faixa|remuneração|remuneracao|compensation|salary)\b", low):
                comp_line = line
                break
    job.comp = parse_comp(comp_line or text[:600])
    if job.comp.get("texto"):
        job.comp["texto"] = _clean(job.comp["texto"], 200)
    job.empresa_tipo = classify_company(text)
    if not job.comp.get("declarada"):
        job.comp["confiabilidade"] = "desconhecida"
    else:
        job.comp["confiabilidade"] = job.empresa_tipo["confiabilidade"]
    job.termos = _tech_terms(text)[:30]
    for line in lines[:20]:
        if re.search(r"publicad|postad|posted|atualizad", _norm(line)):
            job.publicado = _age_days(line)
            if job.publicado is not None:
                break
    job.republicada = bool(re.search(r"republic|reabert|nova tentativa|postada novamente", low_full))
    job.agencia = bool(re.search(r"consultoria de recrutamento|recrutadora|headhunter|staffing|alocaç|alocac", low_full))
    job.sinais = _legitimacy(job)
    job.legitimidade_nota = 100 - sum(
        (12 * int(s["peso"]) if s["estado"] == "ruim" else 5 * int(s["peso"]) if s["estado"] == "atencao" else 0)
        for s in job.sinais
    )
    job.legitimidade_nota = max(0, min(100, job.legitimidade_nota))
    job.legitimidade = "alta" if job.legitimidade_nota >= 85 else "cautela" if job.legitimidade_nota >= 60 else "suspeita"
    return job


def _legitimacy(job: Job) -> list[dict[str, Any]]:
    low = _norm(job.texto)
    sinais: list[dict[str, Any]] = []

    def add(code: str, estado: str, peso: int, confianca: str, evidencia: str, leitura: str) -> None:
        data = RED_FLAGS.get(code, {})
        sinais.append({
            "codigo": code, "titulo": data.get("titulo", code), "estado": estado,
            "peso": peso, "confianca": confianca, "evidencia": evidencia,
            "leitura": leitura,
        })

    if job.publicado is None:
        add("idade-incerta", "atencao", 1, "baixa", "",
            "O anúncio não informa data; confirme quando a vaga foi aberta.")
    elif job.publicado > 60:
        add("vaga-antiga", "ruim", 2, "alta", "publicada há {0} dias".format(job.publicado),
            "Anúncio com mais de 60 dias costuma indicar processo parado ou vaga fantasma.")
    elif job.publicado > 30:
        add("vaga-antiga", "atencao", 1, "media", "publicada há {0} dias".format(job.publicado),
            "Entre 30 e 60 dias, vale perguntar se a posição segue aberta.")
    else:
        add("idade-ok", "bom", 0, "alta", "publicada há {0} dias".format(job.publicado),
            "Anúncio recente é o melhor sinal de vaga ativa que um anúncio oferece.")

    if job.republicada:
        add("republicada", "atencao", 2, "media", "texto cita republicação ou reabertura",
            "Repostar a mesma vaga várias vezes costuma indicar dificuldade de fechar o perfil.")

    if job.comp.get("declarada"):
        low_c = job.comp.get("piso") or 0
        high_c = job.comp.get("teto") or 0
        if low_c and high_c:
            width = high_c - low_c
            if width > 0.5 * low_c:
                add("faixa-larga", "atencao", 2, "alta",
                    "{0} a {1} ({2} de largura)".format(low_c, high_c, width),
                    "Faixa mais larga que metade do piso costuma indicar banda ainda em aberto.")
            else:
                add("faixa-ok", "bom", 0, "alta",
                    "{0} a {1}".format(low_c, high_c), "Faixa estreita sugere nível definido.")
    else:
        add("faixa-ausente", "atencao", 1, "media", "nenhuma faixa declarada",
            "A falta de faixa não é má-fé, mas adia a conversa mais importante.")

    if re.search(r"\bpj\b|\bcnpj\b|contrat[oa] como pj|pessoa jur[ií]dica", low):
        add("pj-para-clt", "ruim", 2, "alta", _quote_for(job.texto, ("pj", "cnpj", "pessoa juridica")),
            "PJ com rotina de emprego muda férias, 13º e proteção; confirme antes de avançar.")
    if re.search(r"taxa de (?:inscri|participa)|curso pago|investimento (?:inicial|obrigat)|custa r\$|pague", low):
        add("taxa-candidato", "ruim", 3, "alta", _quote_for(job.texto, ("taxa", "curso", "investimento")),
            "Cobrança de candidato é sinal de alerta; processos legítimos não cobram.")
    if re.search(r"\bsem remunera|não remunerad|nao remunerad|unpaid|volunt[áa]rio sem", low):
        add("sem-remuneracao", "ruim", 3, "alta", _quote_for(job.texto, ("sem remuneracao", "nao remunerado", "unpaid")),
            "Vaga sem contrapartida declarada precisa ser confirmada antes de qualquer entrega.")
    if re.search(r"disponibilidade total|6x1|6 x 1|plantão sem folga|plantao sem folga|dias úteis e fins de semana", low):
        add("jornada-critica", "ruim", 2, "alta", _quote_for(job.texto, ("disponibilidade total", "6x1", "plantao")),
            "Escala pesada é decisão de vida, não detalhe de contrato.")
    if re.search(r"\b(?:idade|estado civil|filhos|aparência|aparencia|religião|religiao|sexo)\b.{0,40}\b(?:entre|acima|abaixo|obrigat)", low):
        add("exigencia-protegida", "ruim", 3, "media", _quote_for(job.texto, ("idade", "estado civil", "filhos", "aparencia")),
            "Critério protegido como requisito é problema do anúncio, não seu.")
    if re.search(r"\b(?:júnior|junior|estágio|estagio)\b", low) and re.search(r"\b(?:[6-9]|10)\+?\s*anos", low):
        add("requisito-contraditorio", "ruim", 2, "alta",
            _quote_for(job.texto, ("junior", "estagio", "anos")),
            "Senioridade e anos exigidos não conversam; pergunte qual é o nível real.")
    if re.search(r"triagem (?:por|com) (?:ia|inteligência artificial)|avaliação automática|avaliacao automatica|vídeo obrigatório|video obrigatorio", low):
        add("triagem-automatica", "atencao", 1, "media", _quote_for(job.texto, ("ia", "automatica", "video")),
            "Pergunte como os dados da triagem são usados e por quanto tempo ficam guardados.")
    if not job.modelo or not job.local:
        add("local-incerto", "atencao", 1, "media", "",
            "Sem modelo e base territorial, o custo de deslocamento fica fora da conta.")
    if job.beneficios and all(len(item) < 40 and not re.search(r"\d", item) for item in job.beneficios[:4]):
        add("beneficio-vago", "atencao", 1, "baixa", "; ".join(_truncate(b, 40) for b in job.beneficios[:3]),
            "Benefício sem valor nem condição não entra no cálculo; peça a lista por escrito.")
    if len(job.termos) >= 3:
        add("especificidade-ok", "bom", 0, "alta", ", ".join(job.termos[:5]),
            "Requisitos técnicos concretos sugerem vaga escrita para uma função real.")
    elif len(_content_tokens(job.texto)) < 35:
        add("especificidade-baixa", "atencao", 2, "media", "",
            "Texto curto e genérico pode ser vaga de captação de currículos.")
    if job.empresa and job.titulo and any(
        word in _norm(job.empresa_txt) for word in _content_tokens(job.titulo)[:2]
    ):
        add("cargo-empresa-ok", "bom", 0, "media", _truncate(job.empresa_txt, 100),
            "O texto conecta o cargo à operação da empresa.")
    return sinais


def _quote_for(text: str, needles: tuple[str, ...]) -> str:
    target = tuple(_norm(n) for n in needles)
    for sentence in _sentences(text):
        low = _norm(sentence)
        if any(needle in low for needle in target):
            return _truncate(sentence, 180)
    return ""


# ------------------------------------------------------------ casamento

def _cv_proof(cv: Curriculum, terms: list[str], limit: int = 2) -> list[str]:
    scored: list[tuple[int, str]] = []
    for line in _lines(cv.texto):
        low = _norm(line)
        hits = sum(1 for term in terms if _norm(term) in low)
        if hits:
            scored.append((hits * 3 + (2 if _has_metric(line) else 0) + (1 if len(line) < 180 else 0), line))
    scored.sort(key=lambda item: item[0], reverse=True)
    return [_truncate(line, 170) for _, line in scored[:limit]]


def match_requirement(req: Requirement, cv: Curriculum, profile: Profile) -> Requirement:
    if len(_clean(cv.texto, MAX_CURRICULO)) < 120:
        req.casamento = "indefinido"
        req.motivo = "sem currículo suficiente para comparar"
        return req
    terms = _tech_terms(req.texto)
    words = [token for token in _content_tokens(req.texto) if token not in {"anos", "experiencia"}]
    low = _norm(req.texto)
    if any(lang in low for lang in ("ingles", "espanhol", "frances", "alemao")):
        languages = dict(cv.idiomas)
        for key_lang, key_level in profile.idiomas.items():
            languages.setdefault(key_lang, key_level)
        for lang, level in languages.items():
            if _norm(lang) in low:
                low_level = _norm(level)
                if any(word in low_level for word in ("fluente", "nativo", "avancado", "avançado", "c2", "c1")):
                    req.casamento = "forte"
                    req.prova = ["{0}: {1}".format(lang, level)]
                    req.motivo = "idioma declarado no currículo no nível pedido"
                    return req
                req.casamento = "parcial"
                req.prova = ["{0}: {1}".format(lang, level)]
                req.motivo = "idioma declarado, mas abaixo do nível pedido"
                return req
    if terms:
        hits = [term for term in terms if term in cv.termos]
        ratio = len(hits) / len(terms)
        req.prova = _cv_proof(cv, hits or terms)
        if ratio >= 0.7:
            req.casamento = "forte"
            req.motivo = "currículo cita {0} de {1}: {2}".format(len(hits), len(terms), ", ".join(hits[:5]))
        elif ratio >= 0.25:
            req.casamento = "parcial"
            req.motivo = "currículo cita {0} de {1}: {2}".format(len(hits), len(terms), ", ".join(hits[:5]))
        else:
            req.casamento = "ausente"
            req.motivo = "nenhuma das ferramentas citadas aparece no currículo"
        return req
    hits = [word for word in words if word in cv.termos]
    ratio = len(hits) / max(1, len(words))
    req.prova = _cv_proof(cv, hits or words)
    if ratio >= 0.5 and hits:
        req.casamento = "forte"
        req.motivo = "vocabulário do requisito aparece no currículo ({0})".format(", ".join(hits[:4]))
    elif ratio >= 0.18 and hits:
        req.casamento = "parcial"
        req.motivo = "há sobreposição parcial ({0})".format(", ".join(hits[:4]))
    else:
        req.casamento = "ausente"
        req.motivo = "o requisito não aparece no texto do currículo"
    return req


def _stem(word: str) -> str:
    return word[:6] if len(word) > 6 else word


def _title_overlap(job: Job, profile: Profile) -> list[str]:
    targets = " ".join(profile.alvos + profile.dominios + profile.palavras + ([profile.alvo] if profile.alvo else []))
    if not targets.strip():
        return []
    job_map = {_stem(word): word for word in _content_tokens(job.titulo + " " + " ".join(job.termos[:8]))}
    target_words = {_stem(word) for word in _content_tokens(targets)}
    tech = {_stem(term) for term in _tech_terms(targets)}
    shared = sorted(set(job_map) & (target_words | tech))
    return [job_map[key] for key in shared if key]


def find_dealbreakers(job: Job, profile: Profile) -> list[dict[str, Any]]:
    hits: list[dict[str, Any]] = []
    sentences = _sentences(job.texto)
    for rule in profile.regras:
        words = [token for token in _content_tokens(rule) if len(token) >= 4]
        if not words:
            continue
        need = 2 if len(words) <= 3 else min(4, max(3, round(len(words) * 0.6)))
        for sentence in sentences:
            low = _norm(sentence)
            if sum(1 for word in words if word in low) >= need:
                hits.append({"regra": rule, "trecho": _truncate(sentence, 220)})
                break
    if profile.salario_minimo and job.comp.get("declarada"):
        same_currency = (not profile.moeda) or profile.moeda == job.comp.get("moeda")
        if profile.periodo:
            top = comp_yearly(job.comp.get("teto"), str(job.comp.get("periodo") or ""))
            floor = comp_yearly(profile.salario_minimo, profile.periodo)
        else:
            top = job.comp.get("teto")
            floor = profile.salario_minimo
        if top is not None and floor is not None and same_currency and top < floor:
            hits.append({
                "regra": "piso salarial de {0:,.0f}".format(profile.salario_minimo),
                "trecho": _truncate(job.comp.get("texto") or "", 220),
            })
    unique: list[dict[str, Any]] = []
    seen: set[str] = set()
    for hit in hits:
        key = _norm(hit["regra"] + hit["trecho"])
        if key not in seen:
            seen.add(key)
            unique.append(hit)
    return unique


def score_job(job: Job, cv: Curriculum, profile: Profile) -> dict[str, Any]:
    for req in job.requisitos:
        match_requirement(req, cv, profile)
    reqs = [req for req in job.requisitos if req.banda in ("critical", "high", "meaningful", "preferred")]
    total = sum(BANDS[req.banda][1] for req in reqs) or 1.0
    credit = sum(BANDS[req.banda][1] * MATCH[req.casamento][1] for req in reqs)
    coverage = credit / total
    aderencia = round(1 + 4 * coverage, 1)
    stops = [req for req in reqs if req.banda == "critical" and req.evidencia == "stated" and req.casamento == "ausente"]
    caps: list[dict[str, Any]] = []
    if stops:
        aderencia = min(aderencia, 2.0)
        caps.append({
            "nota": aderencia,
            "regra": "requisito obrigatório ausente",
            "porque": "a vaga marca como obrigatório algo que o currículo não mostra: {0}".format(_truncate(stops[0].texto, 90)),
        })
    elif sum(1 for req in reqs if req.banda == "high" and req.casamento == "ausente") >= 2:
        aderencia = min(aderencia, 3.5)

    overlap = _title_overlap(job, profile)
    if not (profile.alvos or profile.alvo or profile.dominios or profile.palavras):
        alvo, alvo_evi = 1.0, "unknown"
        alvo_nota = "nenhum alvo declarado no perfil: sem alvo, a vaga não vira prioridade"
    else:
        ratio = len(overlap) / max(1, min(5, len(set(_content_tokens(job.titulo)))) )
        if ratio >= 0.5:
            alvo, alvo_evi = 5.0, "supported"
        elif ratio >= 0.25:
            alvo, alvo_evi = 4.0, "supported"
        elif overlap:
            alvo, alvo_evi = 3.0, "partial"
        else:
            alvo, alvo_evi = 1.0, "unknown"
        alvo_nota = ("termos em comum com o alvo: " + ", ".join(overlap[:6])) if overlap else "nenhum termo do alvo aparece no título ou no texto"

    comp = job.comp
    comp_score, comp_evi, comp_nota = 3.0, "unknown", "sem faixa declarada; a conversa de salário fica para a triagem"
    if comp.get("declarada"):
        if profile.salario_minimo and profile.moeda and comp.get("moeda") and profile.moeda != comp.get("moeda"):
            comp_score, comp_evi = 3.0, "unknown"
            comp_nota = "moedas diferentes ({0} na vaga, {1} no seu piso); converta antes de comparar".format(comp.get("moeda"), profile.moeda)
        elif (comp.get("teto") is not None and profile.salario_minimo
              and (profile.periodo or comp.get("periodo"))):
            target = profile.alvo_salarial or profile.salario_minimo
            if profile.periodo:
                top_cmp = comp_yearly(comp.get("teto"), comp.get("periodo") or "")
                min_cmp = comp_yearly(profile.salario_minimo, profile.periodo)
                target_cmp = comp_yearly(target, profile.periodo)
                escala = "por ano"
            else:
                top_cmp = comp.get("teto")
                min_cmp = profile.salario_minimo
                target_cmp = target
                escala = "no período do anúncio ({0}); seu piso não declara período".format(comp.get("periodo"))
            if top_cmp is not None and min_cmp and target_cmp:
                if top_cmp >= target_cmp * 1.1:
                    comp_score, comp_evi = 5.0, "supported"
                elif top_cmp >= target_cmp:
                    comp_score, comp_evi = 4.5, "supported"
                elif top_cmp >= min_cmp:
                    comp_score, comp_evi = 3.5, "supported"
                else:
                    comp_score, comp_evi = 1.5, "supported"
                comp_nota = "teto {0:,.0f} {1} {2} contra alvo de {3:,.0f}".format(
                    top_cmp, comp.get("moeda") or "", escala, target_cmp)
            else:
                comp_score, comp_evi = 3.5, "partial"
                comp_nota = "faixa declarada, mas período incompatível para comparar com o seu piso"
        else:
            comp_score, comp_evi = 3.5, "partial"
            comp_nota = "faixa declarada ({0}), mas sem piso no perfil para comparar".format(comp.get("texto"))
    if comp.get("confiabilidade") == "baixa" and comp_score > 3.0:
        comp_score = max(1.0, comp_score - 0.5)
        comp_nota += "; empresa do tipo {0}, então trate o número como teto teórico".format(job.empresa_tipo["rotulo"].lower())

    low = _norm(job.texto)
    culture_plus = [
        ("flexibilidade", bool(re.search(r"flexibilidade|horário flexível|horario flexivel|remoto|híbrido|hibrido", low))),
        ("desenvolvimento", bool(re.search(r"plano de carreira|plano de desenvolvimento|orçamento para (?:cursos|forma)|orcamento para (?:cursos|forma)|mentoria", low))),
        ("inclusão", bool(re.search(r"diversidade|inclusão|inclusao|pcd|pessoas com defici|equidade", low))),
        ("benefícios concretos", bool(re.search(r"plano de saúde|plano de saude|vale-refeição|vale-refeicao|auxílio|auxilio|day off|licença", low))),
    ]
    culture_minus = [
        ("linguagem de família", bool(re.search(r"somos (?:uma )?família|somos (?:uma )?familia", low))),
        ("ritmo acelerado sem escopo", bool(re.search(r"fast-paced|ritmo acelerado|ambiente de startup|work hard", low))),
        ("título fantasia", bool(re.search(r"\b(?:ninja|rockstar|guru|jedi|unicórnio|unicornio)\b", low))),
        ("disponibilidade total", bool(re.search(r"disponibilidade total|sem horário fixo|sem horario fixo", low))),
    ]
    culture = 3.0
    for _, hit in culture_plus:
        culture += 1 if hit else 0
    for _, hit in culture_minus:
        culture -= 1 if hit else 0
    culture = max(1.0, min(5.0, float(culture)))
    culture_evi = "supported" if any(hit for _, hit in culture_plus + culture_minus) else "unknown"
    culture_nota = "sinais lidos do texto: " + (", ".join([name for name, hit in culture_plus + culture_minus if hit]) or "nenhum sinal cultural explícito")
    contradiction = any(hit for name, hit in culture_minus if name in ("linguagem de família", "disponibilidade total"))
    if contradiction:
        culture = min(culture, 2.0)

    risk = {"alta": 5.0, "cautela": 3.5, "suspeita": 2.0}[job.legitimidade]
    if job.publicado is not None and job.publicado > 60:
        risk = max(1.0, risk - 0.5)
    if any(s["estado"] == "ruim" and s["peso"] >= 3 for s in job.sinais):
        risk = min(risk, 2.0)
    risk_evi = "supported" if job.publicado is not None and len(job.sinais) >= 4 else "partial"
    risk_nota = "legitimidade {0} ({1}/100) com {2} sinais lidos".format(job.legitimidade, job.legitimidade_nota, len(job.sinais))

    dims = {
        "aderencia": {"nota": aderencia, "evidencia": "supported" if not stops and cv.texto else ("unknown" if not cv.texto else "partial"), "nota_txt": "{0}% do peso dos requisitos coberto".format(round(coverage * 100)), "peso": DIMENSIONS["aderencia"][1]},
        "alvo": {"nota": alvo, "evidencia": alvo_evi, "nota_txt": alvo_nota, "peso": DIMENSIONS["alvo"][1]},
        "comp": {"nota": comp_score, "evidencia": comp_evi, "nota_txt": comp_nota, "peso": DIMENSIONS["comp"][1]},
        "cultura": {"nota": culture, "evidencia": culture_evi, "nota_txt": culture_nota, "peso": DIMENSIONS["cultura"][1]},
        "risco": {"nota": risk, "evidencia": risk_evi, "nota_txt": risk_nota, "peso": DIMENSIONS["risco"][1]},
    }
    base = round(sum(dims[key]["nota"] * DIMENSIONS[key][1] for key in DIMENSIONS), 1)
    dealbreakers = find_dealbreakers(job, profile)
    if dealbreakers:
        caps.append({
            "nota": min(base, 2.0),
            "regra": "regra dura do perfil",
            "porque": "o anúncio bate de frente com: {0}".format(dealbreakers[0]["regra"]),
        })
    if job.legitimidade == "suspeita":
        caps.append({"nota": min(base, 2.5), "regra": "anúncio suspeito", "porque": "sinais de legitimidade abaixo de 60/100; confirme a vaga antes de investir tempo"})
    if contradiction:
        caps.append({"nota": min(base, 3.4), "regra": "contradição cultural", "porque": "o texto promete flexibilidade e pede disponibilidade total (ou usa linguagem de família)"})

    nota = base
    for cap in caps:
        nota = min(nota, cap["nota"])
    nota = round(max(1.0, min(5.0, nota)), 1)
    verdict = next(item for item in BANDS_SCORE if nota >= item[0])

    supported = sum(1 for d in dims.values() if d["evidencia"] == "supported")
    unknown = sum(1 for d in dims.values() if d["evidencia"] == "unknown")
    partial = sum(1 for d in dims.values() if d["evidencia"] == "partial")
    gaps: list[str] = []
    if unknown:
        gaps.append("{0} dimensão(ões) sem evidência: {1}".format(
            unknown, ", ".join(k for k, d in dims.items() if d["evidencia"] == "unknown")))
    if partial:
        gaps.append("{0} dimensão(ões) com evidência parcial: {1}".format(
            partial, ", ".join(k for k, d in dims.items() if d["evidencia"] == "partial")))
    if not cv.texto:
        gaps.append("currículo não fornecido: a aderência não foi medida")
    if not (profile.alvos or profile.alvo):
        gaps.append("alvo profissional não declarado: alinhamento ficou em 1 por falta de referência")
    if not job.comp.get("declarada"):
        gaps.append("faixa salarial ausente no anúncio")
    if stops:
        gaps.append("obrigatório ausente: " + _truncate(stops[0].texto, 100))
    if job.legitimidade == "suspeita":
        gaps.append("legitimidade do anúncio: suspeita")
    if contradiction:
        gaps.append("contradição entre cultura prometida e exigência de disponibilidade")
    if supported == 5:
        confianca = "alta"
    elif not cv.texto or not (profile.alvos or profile.alvo) or unknown >= 2 or contradiction:
        confianca = "baixa"
    else:
        confianca = "media"
    if job.publicado is None and confianca == "alta":
        confianca = "media"

    return {
        "nota": nota,
        "base": base,
        "faixa": verdict[1],
        "leitura": verdict[2],
        "dimensoes": dims,
        "ajustes": caps,
        "confianca": confianca,
        "confianca_rotulo": CONFIDENCE[confianca],
        "score_evidence": {key: dims[key]["evidencia"] for key in dims},
        "confidence_gaps": gaps,
        "stops": [{"texto": req.texto, "banda": req.banda} for req in stops],
        "dealbreakers": dealbreakers,
        "cobertura": round(coverage * 100, 1),
    }


# ------------------------------------------------------------ lacunas e perguntas

def build_gaps(job: Job, cv: Curriculum, profile: Profile, limit: int = 8) -> list[dict[str, Any]]:
    gaps: list[dict[str, Any]] = []
    for req in job.requisitos:
        if req.origem == "titulo":
            continue
        if req.banda not in ("critical", "high") or req.casamento not in ("ausente", "parcial"):
            continue
        terms = _tech_terms(req.texto)
        adjacent = [term for term in terms if term in cv.termos]
        blocker = req.evidencia == "stated" and req.casamento == "ausente"
        risco = "Pedido direto sobre {0} e sem prova no currículo: responda com algo adjacente e diga o que falta.".format(
            _truncate(", ".join(terms) or req.texto, 80))
        if req.casamento == "parcial":
            risco = "A prova é parcial ({0}); se a pergunta vier, ela tende a cobrar profundidade, não presença.".format(
                _truncate(", ".join(adjacent) or req.texto, 80))
        gaps.append({
            "requisito": _truncate(req.texto, 180),
            "banda": req.banda,
            "banda_rotulo": BANDS[req.banda][0],
            "casamento": req.casamento,
            "bloqueio": blocker,
            "adjacente": adjacent,
            "risco": risco,
            "plano": (
                "Escreva uma frase de fronteira: o que você já fez de parecido, o que ainda não fez e como aprendeu algo novo em prazo curto. "
                "Se houver projeto seu que toque o tema, leve o link."
                if not blocker else
                "Requisito marcado como obrigatório: só siga se puder mostrar trabalho adjacente verificável. "
                "Caso contrário, pergunte ao recrutador se a barreira é absoluta antes de investir no processo."
            ),
            "frase_carta": "Traga a experiência mais próxima ({0}) sem dizer que domina o que não domina.".format(
                ", ".join(adjacent[:3]) or "a área vizinha"),
        })
        if len(gaps) >= limit:
            break
    languages = dict(cv.idiomas)
    for key_lang, key_level in profile.idiomas.items():
        languages.setdefault(key_lang, key_level)
    if job.idioma_exigido and not any(_norm(job.idioma_exigido) in _norm(k) for k in languages):
        gaps.append({
            "requisito": "idioma: " + job.idioma_exigido, "banda": "critical", "banda_rotulo": "Obrigatório",
            "casamento": "indefinido", "bloqueio": False, "adjacente": [],
            "risco": "O anúncio pede {0} e o currículo não declara nível; a entrevista pode virar teste de idioma.".format(job.idioma_exigido),
            "plano": "Declare o nível real no currículo e prepare 2 minutos de apresentação no idioma.",
            "frase_carta": "Declare o nível com honestidade; não estime fluência que você não tem.",
        })
    if not job.comp.get("declarada"):
        gaps.append({
            "requisito": "faixa salarial não declarada", "banda": "meaningful", "banda_rotulo": "Relevante",
            "casamento": "indefinido", "bloqueio": False, "adjacente": [],
            "risco": "Sem número, a primeira conversa pode ancorar abaixo do seu piso.",
            "plano": "Leve o piso e o alvo por escrito e peça a faixa aprovada para o nível antes da entrevista técnica.",
            "frase_carta": "Não cite número na carta; guarde a conversa para a triagem.",
        })
    return gaps


def build_questions(job: Job, score: dict[str, Any], cv: Curriculum, profile: Profile) -> list[str]:
    asks: list[str] = []
    if score["dealbreakers"]:
        asks.append("O anúncio quebra sua regra dura: {0}. Avaliar mesmo assim?".format(score["dealbreakers"][0]["regra"]))
        return asks
    if len(_clean(cv.texto, MAX_CURRICULO)) < 200:
        asks.append("Cole seu currículo em texto (ou o trecho de experiências) para medir a aderência de verdade.")
    if not (profile.alvos or profile.alvo):
        asks.append("Qual é o seu alvo profissional em uma frase? Sem alvo, o alinhamento fica em 1.")
    if not profile.salario_minimo:
        asks.append("Qual é o seu piso salarial e o alvo, com moeda? Isso separa 'faixa boa' de 'faixa teórica'.")
    if not job.comp.get("declarada"):
        asks.append("Você tem a faixa aprovada para este nível? O anúncio não informa.")
    if not job.modelo or not job.local:
        asks.append("Qual é o modelo (remoto, híbrido, presencial) e a base territorial da vaga?")
    if job.senioridade in ("estágio", "estagio", "júnior", "junior") and any("anos" in _norm(r.texto) for r in job.requisitos):
        asks.append("A vaga é realmente de entrada? O texto mistura senioridade com anos de experiência.")
    return asks[:5]


def triage_markdown(job: Job, score: dict[str, Any], cv: Curriculum, profile: Profile, gaps: list[dict[str, Any]]) -> str:
    lines = [
        "# Triagem: {0}{1}".format(job.titulo or "vaga sem título", " · " + job.empresa if job.empresa else ""),
        "",
        "**Nota {0}/5 — {1}.** {2}".format(
            ("{0:.1f}".format(score["nota"])).replace(".", ","), score["faixa"], score["leitura"]),
        "Confiança da evidência: **{0}** (base ponderada {1}/5; a nota não é média das dimensões).".format(
            score["confianca_rotulo"], ("{0:.1f}".format(score["base"])).replace(".", ",")),
        "",
        "| Dimensão | Nota | Evidência | Leitura |",
        "| --- | --- | --- | --- |",
    ]
    for key, label in DIMENSIONS.items():
        dim = score["dimensoes"][key]
        lines.append("| {0} | {1} | {2} | {3} |".format(
            label, ("{0:.1f}".format(dim["nota"])).replace(".", ","),
            {"supported": "sustentada", "partial": "parcial", "unknown": "sem dado"}[dim["evidencia"]],
            dim["nota_txt"],
        ))
    if score["ajustes"]:
        lines += ["", "## Tetos aplicados", ""]
        for cap in score["ajustes"]:
            lines.append("- **{0}**: {1} (nota limitada a {2}/5).".format(
                cap["regra"], cap["porque"], ("{0:.1f}".format(cap["nota"])).replace(".", ",")))
    lines += ["", "## Requisitos", "", "| Banda | Requisito | Casamento | Evidência | Prova no currículo |", "| --- | --- | --- | --- | --- |"]
    for req in job.requisitos[:16]:
        prova = " · ".join(req.prova[:1]) or "—"
        lines.append("| {0} | {1} | {2} | {3} | {4} |".format(
            BANDS[req.banda][0], _truncate(req.texto, 110),
            MATCH[req.casamento][0],
            {"stated": "declarada", "structural": "estrutural", "inferred": "inferida"}[req.evidencia],
            _truncate(prova, 90),
        ))
    if gaps:
        lines += ["", "## Lacunas e mitigação", ""]
        for gap in gaps[:6]:
            lines.append("- **{0}** ({1}, {2}): {3}".format(
                _truncate(gap["requisito"], 100), gap["banda_rotulo"],
                {"ausente": "ausente", "parcial": "parcial", "indefinido": "indefinido"}[gap["casamento"]],
                gap["plano"]))
    lines += [
        "", "## Legitimidade do anúncio", "",
        "**{0}** ({1}/100) — sinal, nunca acusação.".format(
            {"alta": "Alta confiança", "cautela": "Cautela", "suspeita": "Suspeito"}[job.legitimidade],
            job.legitimidade_nota),
        "",
    ]
    for signal in job.sinais:
        mark = {"bom": "✓", "atencao": "!", "ruim": "✗"}.get(signal["estado"], "·")
        lines.append("- {0} **{1}** ({2}): {3}".format(mark, signal["titulo"], signal["confianca"], signal["leitura"]))
    comp = job.comp
    lines += ["", "## Remuneração", ""]
    if comp.get("declarada"):
        lines.append("- Faixa anunciada: {0} ({1}/{2}).".format(
            comp.get("texto") or "—", comp.get("moeda") or "moeda não dita", comp.get("periodo") or "período não dito"))
        lines.append("- Confiabilidade: **{0}** — {1}".format(
            comp.get("confiabilidade", "baixa"), COMP_RELIABILITY.get(comp.get("confiabilidade", "baixa"), "")))
    else:
        lines.append("- Sem faixa declarada. Trate como **{0}** ({1}).".format(
            job.empresa_tipo["rotulo"], job.empresa_tipo["porque"]))
    lines += ["", "## Perguntas antes de seguir", ""]
    for question in build_questions(job, score, cv, profile) or ["Nenhuma pergunta pendente."]:
        lines.append("- " + question)
    lines += ["", "## Não verificado", ""]
    lines += [
        "- Não li portais, LinkedIn nem o site da empresa: o texto colado é toda a evidência.",
        "- Não enviei candidatura, não abri navegador e não alterei nenhum arquivo.",
        "- Nota é triagem, não previsão de contratação.",
    ]
    return "\n".join(lines)


def _triage(payload: dict[str, Any]) -> dict[str, Any]:
    job_raw = str(payload.get("vaga") or "")
    if len(_clean(job_raw, MAX_VAGA + 1)) < 30:
        raise CareerError("Cole o texto da vaga (pelo menos 30 caracteres) para a triagem.")
    job = parse_job(job_raw)
    profile = parse_profile(str(payload.get("perfil") or ""))
    cv = parse_cv(str(payload.get("curriculo") or ""))
    mode = str(payload.get("modo") or "full")
    forcar = _as_bool(payload.get("forcar"), False)
    score = score_job(job, cv, profile)
    gaps = build_gaps(job, cv, profile)
    deck: list[dict[str, Any]] = []
    for gap in gaps[:4]:
        deck.append(finding(
            "should" if gap["bloqueio"] else "nice",
            "lacuna",
            "{0} sem prova suficiente".format(gap["banda_rotulo"]),
            "requisito",
            _truncate(gap["requisito"], 140),
            gap["risco"],
            gap["plano"],
            "A pergunta vem na entrevista e você responde no improviso.",
        ))
    if score["dealbreakers"]:
        deck.insert(0, finding(
            "must", "regra", "Regra dura do perfil violada", "vaga",
            " · ".join(hit["regra"] for hit in score["dealbreakers"][:2]),
            "O anúncio contradiz uma regra que você mesmo escreveu.",
            "Não aplique sem antes aceitar explicitamente o desvio." if not forcar else "Você pediu para avaliar mesmo assim; o desvio ficou registrado.",
            "Você gasta tempo num processo que já sabe onde termina.",
        ))
    near = job.publicado is not None and job.publicado > 60
    if job.legitimidade != "alta":
        deck.append(finding(
            "should", "legitimidade", "Legitimidade do anúncio em {0}".format(job.legitimidade), "vaga",
            "nota {0}/100".format(job.legitimidade_nota),
            "Sinais observáveis sugerem cautela antes de investir tempo.",
            "Confirme se a vaga está aberta, quem é a empresa e qual é a faixa antes de aplicar.",
            "Você pode preparar material para uma vaga que não existe mais." if not near else "A vaga está publicada há mais de 60 dias.",
        ))
    if not cv.texto:
        deck.append(finding(
            "should", "evidencia", "Sem currículo para comparar", "perfil",
            "nenhum texto de currículo",
            "A aderência foi calculada só pelo título e pelo vocabulário da vaga.",
            "Cole o currículo para uma nota com evidência de verdade.",
            "A nota pode subir ou cair bastante quando o currículo entrar.",
        ))
    if score["confianca"] == "baixa":
        deck.insert(0, finding(
            "must", "evidencia", "Confiança da evidência é baixa", "triagem",
            "; ".join(score["confidence_gaps"][:3]) or "faltam dados",
            "Sem evidência, a nota vira opinião com aparência de número.",
            "Complete perfil, currículo e faixa antes de decidir com base na nota.",
            "Você decide com um número que não se sustenta.",
        ))
    findings, counts, verdict, questions = finalize(deck, mode, build_questions(job, score, cv, profile))
    summary = [
        "**Nota:** {0}/5 ({1}) · confiança {2}".format(
            ("{0:.1f}".format(score["nota"])).replace(".", ","), score["faixa"], score["confianca_rotulo"]),
        "**Linha ética:** abaixo de 4,0 não se aplica sem um motivo nomeado; a decisão continua sua.",
    ]
    extra = ["", triage_markdown(job, score, cv, profile, gaps)]
    return common(
        analysis="triagem de vaga",
        mode=mode,
        title="Triagem: {0}{1}".format(job.titulo or "vaga", " · " + job.empresa if job.empresa else ""),
        summary=summary,
        findings=findings,
        counts=counts,
        verdict=verdict,
        questions=questions,
        rows=[{
            "requisito": _truncate(req.texto, 120), "banda": req.banda,
            "casamento": req.casamento, "evidencia": req.evidencia,
            "prova": _truncate(" · ".join(req.prova[:1]), 100),
        } for req in job.requisitos],
        metrics={
            "nota": score["nota"], "base": score["base"], "faixa": score["faixa"],
            "confianca": score["confianca"], "cobertura": score["cobertura"],
            "legitimidade": job.legitimidade, "legitimidadeNota": job.legitimidade_nota,
            "dimensoes": score["dimensoes"], "ajustes": score["ajustes"],
            "scoreEvidence": score["score_evidence"], "confidenceGaps": score["confidence_gaps"],
            "sinais": job.sinais, "comp": job.comp, "empresaTipo": job.empresa_tipo,
            "bloqueada": bool(score["dealbreakers"]) and not forcar,
        },
        limitations=[
            "Nenhum portal, LinkedIn ou site da empresa foi acessado.",
            "Nenhuma candidatura foi enviada; nenhum arquivo foi alterado.",
            "A nota é triagem qualitativa com bandas declaradas, não probabilidade de contratação.",
        ],
        extra_sections=extra,
    )


# ------------------------------------------------------------ ATS

def _strip_html(html: str) -> str:
    text = re.sub(r"(?is)<(script|style)\b.*?</\1>", " ", html)
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    text = text.replace("&nbsp;", " ").replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    return re.sub(r"\s+", " ", text).strip()


def _ats_checks(cv: Curriculum, html: str) -> list[dict[str, Any]]:
    text = _strip_html(html) if html else cv.texto
    low = _norm(text)
    checks: list[dict[str, Any]] = []

    def add(code: str, ok: bool, evidence: str, hint: str) -> None:
        data = ATS_CHECKS[code]
        checks.append({
            "codigo": code, "titulo": data["titulo"], "peso": data["peso"],
            "ok": ok, "status": "ok" if ok else "falha",
            "evidencia": evidence, "regra": data["regra"], "ajuste": hint,
        })

    real = len(re.sub(r"\s+", " ", text).strip())
    add("texto", real >= 300, "{0} caracteres legíveis".format(real),
        "Um parser precisa de texto de verdade; currículo em imagem não entra na triagem.")
    headings = {key: any(_heading_key(line) == key for line in _lines(cv.texto)) for key in ("experiencia", "formacao", "habilidades")}
    missing = [key for key, found in headings.items() if not found]
    add("secoes", not missing,
        "cabeçalhos ausentes: " + ", ".join(missing) if missing else "experiência, formação e habilidades encontrados",
        "Use os nomes de seção que o ATS conhece; título criativo vira texto solto.")
    email = cv.email or (re.search(r"[\w.+-]+@[\w-]+\.[\w.]+", text).group(0) if re.search(r"[\w.+-]+@[\w-]+\.[\w.]+", text) else "")
    header_email = bool(re.search(r"(?is)<header\b[^>]*>.*?" + re.escape(email) + r".*?</header>", html)) if email and html else False
    add("contato", bool(email) and not header_email, email or "e-mail não encontrado",
        "Deixe o e-mail no corpo do documento, não num cabeçalho que pode ser descartado.")
    if html:
        table_layout = bool(re.search(r"(?is)<table\b", html))
        multi = bool(re.search(r"(?is)(column-count\s*:\s*[2-9]|columns\s*:\s*[2-9]|display\s*:\s*(?:grid|flex)[^;}]*grid-template-columns\s*:\s*(?:[^;}]*,){1,})", html))
        add("coluna", not (table_layout or multi),
            "tabela de layout" if table_layout else ("CSS multicoluna" if multi else "fluxo de coluna única"),
            "Uma coluna, sem tabela: parsers leem de cima para baixo.")
        images = re.findall(r"(?is)<img\b[^>]*>", html)
        long_alt = [tag for tag in images if re.search(r'alt\s*=\s*["\'][^"\']{40,}', tag)]
        add("imagem", not long_alt,
            "{0} imagem(ns)".format(len(images)) if images else "nenhuma imagem",
            "Texto dentro de imagem não é indexado; mantenha-o no HTML.")
        fonts = re.findall(r"font-family\s*:\s*([^;}\"]+)", html)
        stack = " ".join(fonts).lower()
        common = any(name in stack for name in ("arial", "calibri", "helvetica", "georgia", "times", "system-ui", "roboto", "open sans", "lato"))
        add("fonte", common or not fonts, (fonts[0].strip() if fonts else "sem fonte declarada"),
            "Use uma pilha comum; fonte decorativa pode cair para outra sem aviso.")
        add("utf8", bool(re.search(r"(?is)<meta[^>]+charset\s*=\s*[\"']?utf-8", html)),
            "meta charset utf-8" if re.search(r"(?is)charset", html) else "sem meta charset",
            "Sem UTF-8, acentos viram símbolos no sistema de quem lê.")
        hidden = bool(re.search(r"(?is)(display\s*:\s*none|visibility\s*:\s*hidden|font-size\s*:\s*0(?:px)?\b|color\s*:\s*transparent|text-indent\s*:\s*-\d{4,})", html))
        add("oculto", not hidden, "CSS de ocultação encontrado" if hidden else "nenhum texto escondido",
            "Palavra escondida é penalizada por recrutadores e por filtros; não use.")
    else:
        for code in ("coluna", "imagem", "fonte", "utf8", "oculto"):
            data = ATS_CHECKS[code]
            checks.append({
                "codigo": code, "titulo": data["titulo"], "peso": data["peso"], "ok": None,
                "status": "nao-verificado", "evidencia": "sem HTML para inspecionar",
                "regra": data["regra"], "ajuste": "Cole o HTML final para pontuar esta checagem.",
            })
    return checks


def _payload_lints(cv: Curriculum) -> list[dict[str, Any]]:
    lints: list[dict[str, Any]] = []
    lines = _lines(cv.texto)
    for index, line in enumerate(lines, start=1):
        if re.search(r"(?i)\b(?:na|@|at)\s+[A-Z][\w&.-]+.*(?:19|20)\d{2}", line) and len(line) < 120:
            lints.append({
                "codigo": "empresa-no-cargo", "linha": index, "texto": _truncate(line, 160),
                "problema": "cargo e empresa na mesma linha; o parser pode gravar os dois como título",
                "ajuste": "Separe em Cargo | Empresa | Período, cada um no seu campo.",
            })
        if re.search(r"[A-Z][\w&.-]+\s*\((?:antig[ao]|ex-|antes)[^)]*\)", line):
            lints.append({
                "codigo": "parentese-na-empresa", "linha": index, "texto": _truncate(line, 160),
                "problema": "parêntese dentro do nome da empresa quebra o casamento com o histórico",
                "ajuste": "Use o nome atual da empresa; se a mudança importa, explique na entrevista.",
            })
        ranges = re.findall(r"(?:19|20)\d{2}\s*[-–—]\s*(?:(?:19|20)\d{2}|atual|presente|hoje)", _norm(line))
        if len(ranges) >= 2:
            lints.append({
                "codigo": "multiplas-faixas-de-data", "linha": index, "texto": _truncate(line, 160),
                "problema": "duas faixas de data na mesma entrada",
                "ajuste": "Uma entrada por cargo; junte promoções com datas separadas na mesma empresa.",
            })
    comp_heading = any(_norm(line).strip("#* ").rstrip(":") in ("competencias", "competências") for line in lines)
    skills_heading = any(_norm(line).strip("#* ").rstrip(":") in ("habilidades", "skills") for line in lines)
    if comp_heading and skills_heading:
        lints.append({
            "codigo": "competencias-duplicadas", "linha": 0, "texto": "seções Competências e Habilidades",
            "problema": "dois blocos com a mesma função: um deles pode ser ignorado no mapeamento",
            "ajuste": "Consolide em Habilidades, com as ferramentas que você usa de fato.",
        })
    return lints


def _job_keywords(job: Job, cv: Curriculum) -> dict[str, Any]:
    jd_terms = [term for term in job.termos]
    for req in job.requisitos:
        for term in _tech_terms(req.texto):
            if term not in jd_terms:
                jd_terms.append(term)
    present, missing = [], []
    for term in jd_terms[:MAX_TERMOS * 2]:
        (present if term in cv.termos else missing).append(term)
    return {
        "presentes": present[:MAX_TERMOS],
        "ausentes": missing[:MAX_TERMOS],
        "cobertura": round(100 * len(present) / max(1, len(present) + len(missing))),
        "nota": "Palavra-chave só entra se você tem a experiência. Reformular é honesto; empilhar não é.",
    }


def _ats(payload: dict[str, Any]) -> dict[str, Any]:
    cv_text = str(payload.get("curriculo") or "")
    if len(_clean(cv_text, MAX_CURRICULO + 1)) < 80:
        raise CareerError("Cole pelo menos um trecho real do currículo (80 caracteres) para checar o ATS.")
    cv = parse_cv(cv_text)
    html = str(payload.get("html") or "")
    _cap("html", html, MAX_CURRICULO * 2)
    mode = str(payload.get("modo") or "full")
    checks = _ats_checks(cv, html)
    applicable = [c for c in checks if c["ok"] is not None]
    score = sum(c["peso"] for c in applicable if c["ok"])
    max_score = sum(c["peso"] for c in applicable) or 1
    complete = max_score >= 100
    normalized = score if complete else round(100 * score / max_score)
    nota = next(letter for limit, letter in GRADES if normalized >= limit) if complete else "parcial"
    lints = _payload_lints(cv)
    keywords: dict[str, Any] = {"presentes": [], "ausentes": [], "cobertura": 0, "nota": "sem vaga informada"}
    if str(payload.get("vaga") or "").strip():
        keywords = _job_keywords(parse_job(str(payload.get("vaga"))), cv)

    deck: list[dict[str, Any]] = []
    for check in checks:
        if check["ok"] is False:
            deck.append(finding(
                "must" if check["peso"] >= 15 else "should",
                "ats",
                check["titulo"],
                "html" if html else "curriculo",
                check["evidencia"],
                "Esta checagem vale {0} de 100 e falhou.".format(check["peso"]),
                check["ajuste"],
                "O parser pode descartar parte do currículo sem avisar.",
            ))
    for lint in lints:
        deck.append(finding(
            "should", "payload", lint["codigo"], "linha {0}".format(lint["linha"] or "texto"),
            lint["texto"], lint["problema"], lint["ajuste"],
            "O campo entra trocado no histórico e a triagem perde o fio.",
        ))
    if len(keywords.get("ausentes", [])) > 4:
        deck.append(finding(
            "nice", "palavras", "Palavras da vaga fora do currículo", "palavras",
            ", ".join(keywords["ausentes"][:8]),
            "O anúncio pede termos que o currículo não menciona.",
            "Inclua apenas os que você domina de fato; reformule com o seu vocabulário.",
            "A triagem automática pode não reconhecer a experiência equivalente.",
        ))
    if not cv.metricas:
        deck.insert(0, finding(
            "should", "evidencia", "Nenhum número no currículo", "experiencia",
            "{0} bullets lidos".format(len(cv.bullets)),
            "Sem número, o impacto vira adjetivo.",
            "Para cada conquista, responda: quanto, em quanto tempo, comparado a quê?",
            "A entrevista cobra a métrica que o currículo prometeu.",
        ))
    findings, counts, verdict, questions = finalize(deck, mode, [
        "Cole também o HTML final se quiser o placar completo de 100 pontos.",
        "As palavras ausentes: você tem experiência real com alguma delas que ficou de fora?",
    ])
    return common(
        analysis="checagem ATS",
        mode=mode,
        title="ATS: {0}/{1} pontos medidos{2}".format(
            score, max_score, " · nota " + nota if complete else " (sem HTML)"),
        summary=[
            "**Placar:** {0} de {1} pontos medidos{2}.".format(
                score, max_score, " · nota **{0}**".format(nota) if complete else " · nota final exige o HTML"),
            "**Etapas:** payload ({0} lint(s)) e HTML ({1}).".format(
                len(lints), "inspecionado" if html else "não inspecionado"),
            "Read-only e advisory: nada é reescrito; você decide o que corrigir.",
        ],
        findings=findings,
        counts=counts,
        verdict=verdict,
        questions=questions,
        rows=[{
            "checagem": check["titulo"], "peso": check["peso"],
            "status": check["status"], "evidencia": check["evidencia"],
        } for check in checks] + [{
            "checagem": "lint: " + lint["codigo"], "peso": 0, "status": "aviso", "evidencia": lint["texto"],
        } for lint in lints],
        metrics={
            "score": score, "escala": max_score, "normalizado": normalized if complete else None,
            "nota": nota, "checklist": checks, "lints": lints,
            "palavras": keywords, "html": bool(html),
            "metricasCv": cv.metricas, "bullets": len(cv.bullets),
        },
        limitations=[
            "O placar lê o texto do HTML, não o PDF renderizado.",
            "Não abre o arquivo em navegador nem simula um ATS real.",
            "Palavra-chave é sugestão advisory; nada é inserido no currículo.",
        ],
        extra_sections=["", "## Checklist", "", "| Peso | Checagem | Status | Evidência |", "| --- | --- | --- | --- |"] + [
            "| {0} | {1} | {2} | {3} |".format(
                check["peso"], check["titulo"],
                {"ok": "✓", "falha": "✗", "nao-verificado": "—"}[check["status"]],
                _truncate(check["evidencia"], 70))
            for check in checks
        ] + (["", "## Lints de payload", ""] + [
            "- **{0}** (linha {1}): {2} → {3}".format(lint["codigo"], lint["linha"] or "texto", lint["problema"], lint["ajuste"])
            for lint in lints
        ] if lints else []),
    )


# ------------------------------------------------------------ carta

def _achievements(cv: Curriculum, job: Job, limit: int = 3) -> list[dict[str, Any]]:
    jd_terms = set(job.termos)
    for req in job.requisitos[:8]:
        jd_terms.update(_tech_terms(req.texto))
    scored: list[tuple[int, dict[str, Any]]] = []
    for bullet in cv.bullets:
        if not bullet.metrica:
            continue
        hits = [term for term in jd_terms if term in _norm(bullet.texto)]
        scored.append((len(hits) * 3 + min(3, bullet.tamanho // 60), {
            "texto": _truncate(bullet.texto, 240),
            "termos": hits,
            "linha": bullet.linha,
            "metrica": True,
        }))
    scored.sort(key=lambda item: item[0], reverse=True)
    if not scored:
        for bullet in cv.bullets:
            if len(bullet.texto) >= 50:
                scored.append((0, {
                    "texto": _truncate(bullet.texto, 240), "termos": [], "linha": bullet.linha, "metrica": False,
                }))
    return [item for _, item in scored[:limit]]


def _letter_checks(text: str, cv: Curriculum, job: Job, profile: Profile) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    low = _norm(text)
    cliches = [cliche for cliche in CLICHES if _norm(cliche) in low]
    checks.append({
        "codigo": "cliche", "ok": not cliches,
        "evidencia": ", ".join(cliches[:6]) or "nenhum clichê da lista",
        "ajuste": "Troque a frase feita por um fato que só você tem.",
        "peso": 20,
    })
    size = len(text)
    checks.append({
        "codigo": "tamanho", "ok": 600 <= size <= 1600,
        "evidencia": "{0} caracteres".format(size),
        "ajuste": "Carta de uma página: 600 a 1.600 caracteres, 3 ou 4 parágrafos.",
        "peso": 15,
    })
    numbers = _number_hits(text)
    allowed = _norm(cv.texto) + " " + _norm(str(profile.campos)) + " " + _norm(str(profile.anos)) + " 90 dias 30 dias"
    invented = [num for num in numbers if _norm(num) not in allowed]
    checks.append({
        "codigo": "numeros", "ok": not invented,
        "evidencia": ("números sem origem no currículo: " + ", ".join(invented[:5])) if invented else "{0} número(s), todos com origem".format(len(numbers)),
        "ajuste": "Todo número da carta precisa existir no currículo ou no perfil.",
        "peso": 25,
    })
    placeholders = re.findall(r"\[[^\]]{2,30}\]|\{[a-z_]+\}|<[a-z_]+>|lorem ipsum|\bXXX\b", _norm(text))
    checks.append({
        "codigo": "placeholder", "ok": not placeholders,
        "evidencia": ", ".join(placeholders[:5]) or "nenhum marcador",
        "ajuste": "Nenhum marcador: se falta informação, a carta não está pronta.",
        "peso": 20,
    })
    jd_terms = job.termos[:8]
    present = [term for term in jd_terms if term in _norm(text)]
    checks.append({
        "codigo": "palavras", "ok": len(present) >= min(3, len(jd_terms)),
        "evidencia": "termos da vaga presentes: " + (", ".join(present[:6]) or "nenhum"),
        "ajuste": "Cite as ferramentas que você realmente usou e que a vaga pede.",
        "peso": 10,
    })
    named = bool(job.empresa and _norm(job.empresa) in low) and bool(job.titulo and _norm(job.titulo) in low)
    checks.append({
        "codigo": "especificidade", "ok": named,
        "evidencia": "empresa e cargo citados" if named else "falta citar empresa ou cargo exato",
        "ajuste": "Nomeie a empresa e o cargo exatamente como no anúncio.",
        "peso": 10,
    })
    return checks


def _letter(payload: dict[str, Any]) -> dict[str, Any]:
    jd = str(payload.get("vaga") or "")
    cv_text = str(payload.get("curriculo") or "")
    profile = parse_profile(str(payload.get("perfil") or ""))
    pesquisa = _clean(str(payload.get("pesquisa") or ""), 4000)
    porque = _clean(str(payload.get("porque") or ""), 600)
    mode = str(payload.get("modo") or "full")
    if len(_clean(jd, MAX_VAGA + 1)) < 200:
        raise CareerError("Sem a descrição da vaga não há carta: cole o anúncio (200 caracteres ou mais).")
    if len(_clean(cv_text, MAX_CURRICULO + 1)) < 200:
        raise CareerError("Sem o currículo não há carta: cole suas experiências com números.")
    job = parse_job(jd)
    cv = parse_cv(cv_text)
    achievements = _achievements(cv, job)
    gaps = build_gaps(job, cv, profile, limit=3)

    missing_inputs: list[str] = []
    if not pesquisa and not porque:
        missing_inputs.append("O que essa empresa faz que te interessa de verdade? (uma frase, com fato, não elogio)")
    if not achievements:
        missing_inputs.append("Qual conquista sua tem número e cabe nesta vaga? Escreva como no currículo.")
    if not (profile.nome or cv.nome):
        missing_inputs.append("Como você assina? Nome completo para o fecho da carta.")
    if missing_inputs:
        deck = [finding(
            "must", "insumo", "Falta insumo para uma carta específica", "carta",
            item, "Sem isso a carta vira modelo genérico.", "Responda e rode de novo.", "A carta genérica é pior que nenhuma carta.",
        ) for item in missing_inputs]
        findings, counts, verdict, questions = finalize(deck, mode, missing_inputs)
        return common(
            analysis="carta de apresentação (insumos)", mode=mode,
            title="Carta: faltam {0} insumo(s)".format(len(missing_inputs)),
            summary=["**Status:** parado antes do rascunho, por decisão de projeto.",
                     "Nada é inventado: a carta só existe com fato seu e fato da empresa."],
            findings=findings, counts=counts, verdict=verdict, questions=questions,
            rows=[], metrics={"pronto": False, "faltando": missing_inputs},
            limitations=["Nenhum rascunho foi gerado sem pesquisa e conquista verificável."],
        )

    research_line = _truncate(pesquisa or porque, 220)
    if research_line and research_line[-1] not in ".!?":
        research_line += "."
    hook = porque or research_line
    top_reqs = [req for req in job.requisitos if req.banda in ("critical", "high")][:4]
    proof_lines = [ach["texto"].rstrip(".") for ach in achievements[:3]]
    terms = []
    for req in top_reqs:
        for term in _tech_terms(req.texto):
            if term not in terms and term in cv.termos:
                terms.append(term)
    paragraphs = [
        "À equipe de {0},".format(job.empresa) if job.empresa else "Olá,",
        "Candidato-me à vaga de {0}{1}. {2}".format(
            job.titulo or "descrita no anúncio",
            " em " + job.empresa if job.empresa else "",
            _truncate(hook, 240),
        ),
        " ".join([line + "." for line in proof_lines]) if proof_lines else "",
    ]
    if terms:
        paragraphs.append(
            "As ferramentas que o anúncio pede e que eu já uso no dia a dia são {0}. "
            "É por aí que consigo contribuir desde as primeiras semanas.".format(
                ", ".join(_display_term(term) for term in terms[:5]))
        )
    gap = next((g for g in gaps if g["casamento"] in ("ausente", "parcial")), None)
    if gap:
        paragraphs.append(
            "Não vou dizer que já fiz o que não fiz: {0} ainda não aparece no meu histórico. "
            "O que tenho de mais próximo é {1}, e o que sei fazer é aprender rápido em contexto real.".format(
                _truncate(gap["requisito"], 110), gap["adjacente"][0] if gap["adjacente"] else "trabalho adjacente na mesma área")
        )
    paragraphs.append(
        "Fico à disposição para conversar sobre o contexto do time e sobre o que vocês esperam de quem entrar.{0}".format(
            " Meu aviso prévio é de {0} dias.".format(profile.campos.get("notice_period_days")) if profile.campos.get("notice_period_days") else ""
        )
    )
    paragraphs.append("Atenciosamente,\n{0}".format(profile.nome or cv.nome or ""))
    draft = "\n\n".join(part for part in paragraphs if part.strip())
    checks = _letter_checks(draft, cv, job, profile)
    failed = [check for check in checks if not check["ok"]]

    deck: list[dict[str, Any]] = []
    for check in failed:
        deck.append(finding(
            "must" if check["peso"] >= 20 else "should",
            "carta", check["codigo"], "rascunho",
            check["evidencia"],
            "A checagem vale {0} e falhou.".format(check["peso"]),
            check["ajuste"],
            "A carta perde credibilidade justamente onde o recrutador repara.",
        ))
    for gap in gaps:
        if gap["casamento"] == "ausente" and gap["banda"] == "critical":
            deck.append(finding(
                "should", "lacuna", "Lacuna obrigatória exposta na carta", "rascunho",
                _truncate(gap["requisito"], 120), gap["risco"],
                "Mantenha a frase de fronteira e não prometa domínio.", "A entrevista cobra o que a carta sugerir.",
            ))
    findings, counts, verdict, questions = finalize(deck, mode, [
        "A frase de abertura usa um fato seu sobre a empresa?",
        "Algum número da carta veio de um projeto que você não pode comprovar?",
        "Qual é o seu aviso prévio real?",
        "Você revisou em voz alta antes de gerar o PDF?",
    ])
    return common(
        analysis="carta de apresentação",
        mode=mode,
        title="Carta: {0}{1}".format(job.titulo or "vaga", " · " + job.empresa if job.empresa else ""),
        summary=[
            "**Status:** rascunho para revisão humana; nada é enviado.",
            "**Base:** {0} conquista(s) do currículo, {1} requisito(s) da vaga, 1 pesquisa.".format(len(achievements), len(top_reqs)),
            "**Regra:** nenhum número fora do currículo ou do perfil.",
        ],
        findings=findings, counts=counts, verdict=verdict, questions=questions,
        rows=[{"paragrafo": index + 1, "texto": para} for index, para in enumerate(paragraphs) if para.strip()],
        metrics={
            "pronto": not failed, "rascunho": draft, "paragrafos": [p for p in paragraphs if p.strip()],
            "conquistas": achievements, "lacuna": gap, "checagens": checks,
            "caracteres": len(draft), "cliche": [c["evidencia"] for c in checks if c["codigo"] == "cliche" and not c["ok"]],
        },
        limitations=[
            "Não pesquisei a empresa: a pesquisa é o texto que você forneceu.",
            "Não li o PDF final nem verifiquei formatação.",
            "Não enviei nada; o botão de enviar continua sendo seu.",
        ],
        extra_sections=["", "## Rascunho", "", draft, "", "## Checagens", "", "| Checagem | Status | Evidência |", "| --- | --- | --- |"] + [
            "| {0} | {1} | {2} |".format(check["codigo"], "✓" if check["ok"] else "✗", _truncate(check["evidencia"], 90))
            for check in checks
        ],
    )


# ------------------------------------------------------------ bullets

def _bullet_issues(bullet: Bullet) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []
    low = _norm(bullet.texto)
    opener = next((cue for cue in WEAK_OPENERS if low.startswith(_norm(cue))), "")
    if opener:
        issues.append({
            "codigo": "abertura-fraca", "peso": 25,
            "problema": "Abre com '{0}', que descreve cargo, não resultado.".format(opener),
            "ajuste": "Comece pelo verbo no passado: reduzi, construí, migrei, automatizei.",
        })
    if bullet.passivo:
        issues.append({
            "codigo": "voz-passiva", "peso": 15,
            "problema": "Voz passiva esconde quem fez o trabalho.",
            "ajuste": "Diga 'eu' implicitamente: o sujeito da frase é você.",
        })
    if not bullet.metrica:
        issues.append({
            "codigo": "sem-metrica", "peso": 30,
            "problema": "Nenhum número: sem medida, o impacto vira opinião.",
            "ajuste": "Responda quanto, em quanto tempo ou comparado a quê; se não houver número, diga o antes e o depois.",
        })
    if bullet.tamanho > 220:
        issues.append({
            "codigo": "longo", "peso": 10,
            "problema": "Bullet com {0} caracteres: passa de duas linhas e perde leitura.".format(bullet.tamanho),
            "ajuste": "Corte contexto; mantenha ação, ferramenta e resultado.",
        })
    elif bullet.tamanho < 28:
        issues.append({
            "codigo": "curto", "peso": 5,
            "problema": "Bullet curto demais para mostrar o que mudou.",
            "ajuste": "Some o objeto e o resultado ao verbo.",
        })
    if bullet.cliche:
        issues.append({
            "codigo": "cliche", "peso": 20,
            "problema": "Clichê: {0}.".format(", ".join(bullet.cliche[:3])),
            "ajuste": "Troque o adjetivo por um fato que só você tem.",
        })
    if re.search(r"\b(?:eu|meu|minha|fiz)\b", _norm(bullet.texto)):
        issues.append({
            "codigo": "primeira-pessoa", "peso": 5,
            "problema": "Primeira pessoa no currículo.",
            "ajuste": "No CV, o sujeito é implícito; guarde o 'eu' para a carta.",
        })
    return issues


def _bullets(payload: dict[str, Any]) -> dict[str, Any]:
    cv_text = str(payload.get("curriculo") or "")
    if len(_clean(cv_text, MAX_CURRICULO + 1)) < 120:
        raise CareerError("Cole o currículo (120 caracteres ou mais) para auditar os bullets.")
    cv = parse_cv(cv_text)
    achievement_sections = {"experiencia", "projetos", "geral"}
    audited_bullets = [bullet for bullet in cv.bullets if bullet.secao in achievement_sections]
    if not audited_bullets:
        raise CareerError(
            "Não encontrei bullets de experiência: use uma linha por conquista, começando com '-', "
            "sob as seções Experiência ou Projetos. Formação e idiomas ficam fora da auditoria."
        )
    cv.bullets = audited_bullets
    mode = str(payload.get("modo") or "full")
    audited: list[dict[str, Any]] = []
    for bullet in cv.bullets[:MAX_ITENS]:
        issues = _bullet_issues(bullet)
        audited.append({
            "linha": bullet.linha, "texto": bullet.texto, "secao": bullet.secao,
            "tamanho": bullet.tamanho, "metrica": bullet.metrica,
            "pontuacao": max(0, 100 - sum(int(issue["peso"]) for issue in issues)),
            "problemas": issues,
            "modelo": "Verbo no passado + o que mudou + número + como",
            "pergunta": "Qual número mudou, em quanto tempo, comparado a quê?",
        })
    audited.sort(key=lambda item: item["pontuacao"])
    aberturas: dict[str, int] = {}
    for bullet in cv.bullets:
        first = (_tokens(bullet.texto) or ["?"])[0]
        aberturas[first] = aberturas.get(first, 0) + 1
    repetidas = {word: count for word, count in aberturas.items() if count >= 3}
    weak = [item for item in audited if any(issue["codigo"] == "abertura-fraca" for issue in item["problemas"])]
    no_metric = [item for item in audited if not item["metrica"]]
    deck: list[dict[str, Any]] = []
    by_code: dict[str, list[dict[str, Any]]] = {}
    for item in audited:
        for issue in item["problemas"]:
            by_code.setdefault(issue["codigo"], []).append({**item, "problema": issue})
    for code, entries in by_code.items():
        first = entries[0]["problema"]
        locations = ", ".join(str(entry["linha"]) for entry in entries[:4])
        deck.append(finding(
            "must" if int(first["peso"]) >= 25 else "should",
            "bullet",
            "{0} em {1} bullet(s)".format(code, len(entries)),
            "linhas " + locations,
            _truncate(entries[0]["texto"], 160),
            "{0} Esse padrão aparece em {1} de {2} bullets.".format(first["problema"], len(entries), len(audited)),
            first["ajuste"],
            "O recrutador lê 6 segundos por currículo; sem número, este bullet não fica.",
        ))
    if repetidas:
        deck.append(finding(
            "should", "bullet", "Aberturas repetidas", "currículo",
            ", ".join("{0}×{1}".format(word, count) for word, count in sorted(repetidas.items(), key=lambda kv: -kv[1])[:3]),
            "Bullets que começam igual soam como template.",
            "Varie o verbo: reduzi, construí, migrei, negociei, documentei.",
            "O leitor para de diferenciar uma conquista da outra.",
        ))
    if not cv.metricas:
        deck.insert(0, finding(
            "must", "bullet", "Nenhum bullet com número", "currículo",
            "{0} bullets auditados".format(len(cv.bullets)),
            "O currículo inteiro descreve atividades sem resultado.",
            "Escolha os 5 bullets de maior impacto e levante um número para cada.",
            "Sem número não há como comparar candidatos — e você perde a comparação.",
        ))
    findings, counts, verdict, questions = finalize(deck, mode, [
        "Quais desses números você consegue defender numa entrevista?",
        "Algum bullet descreve atividade de time em vez de resultado seu?",
        "Qual conquista ficou de fora do currículo por falta de espaço?",
    ])
    com_metrica = sum(1 for bullet in cv.bullets if bullet.metrica)
    return common(
        analysis="auditoria de bullets",
        mode=mode,
        title="Bullets: {0} de {1} com número".format(com_metrica, len(cv.bullets)),
        summary=[
            "**Cobertura de métrica:** {0}% ({1}/{2}).".format(
                round(100 * com_metrica / max(1, len(cv.bullets))), com_metrica, len(cv.bullets)),
            "**Aberturas fracas:** {0} · média de {1} caracteres.".format(
                len(weak), round(sum(b.tamanho for b in cv.bullets) / max(1, len(cv.bullets)))),
            "**Regra:** todo número sugerido precisa ter origem no seu trabalho; o modelo é sintaxe, não conteúdo.",
        ],
        findings=findings, counts=counts, verdict=verdict, questions=questions,
        rows=[{
            "linha": item["linha"], "pontuacao": item["pontuacao"],
            "texto": _truncate(item["texto"], 110),
            "problemas": ", ".join(issue["codigo"] for issue in item["problemas"]) or "—",
        } for item in audited],
        metrics={
            "bullets": len(cv.bullets), "comMetrica": com_metrica,
            "cobertura": round(100 * com_metrica / max(1, len(cv.bullets))),
            "mediaCaracteres": round(sum(b.tamanho for b in cv.bullets) / max(1, len(cv.bullets))),
            "aberturasRepetidas": repetidas, "auditoria": audited,
            "metricas": cv.metricas,
        },
        limitations=[
            "A auditoria lê texto; não vê layout nem PDF.",
            "Não reescreve seus bullets: aponta o padrão e pergunta o número.",
        ],
        extra_sections=["", "## Antes e depois (modelo, não conteúdo)", ""] + [
            "- **Linha {0}:** {1}\n  - modelo: *{2}*\n  - pergunta: {3}".format(
                item["linha"], _truncate(item["texto"], 140), item["modelo"], item["pergunta"])
            for item in audited[:5]
        ],
    )


# ------------------------------------------------------------ entrevista

STORY_HEADING = re.compile(r"^#{1,4}\s*(.+)$")


def parse_stories(text: str) -> list[dict[str, Any]]:
    stories: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    for line in str(text or "").splitlines():
        match = STORY_HEADING.match(line.strip())
        if match:
            current = {"titulo": _clean(match.group(1), 120), "texto": "", "linha": len(stories) + 1}
            stories.append(current)
            continue
        if current is None:
            if line.strip():
                current = {"titulo": "história {0}".format(len(stories) + 1), "texto": "", "linha": 1}
                stories.append(current)
            else:
                continue
        current["texto"] = (current["texto"] + " " + line.strip()).strip()
    for story in stories:
        low = _norm(story["texto"])
        story["numero"] = _has_metric(story["texto"])
        story["star"] = {
            "situacao": bool(re.search(r"situa|contexto|quando", low)),
            "tarefa": bool(re.search(r"tarefa|objetivo|meta|precisava", low)),
            "acao": bool(re.search(r"a[cç][aã]o|fiz|constru|liderei|decidi", low)),
            "resultado": bool(re.search(r"resultado|impacto|depois|reduzi|aumentei", low)),
        }
    return stories


def _interview_kind(req: Requirement) -> str:
    low = _norm(req.texto)
    if re.search(r"lider|gest[ãa]o|time|pessoas|mentor|contrata|people", low):
        return "gestao"
    if re.search(r"produto|roadmap|stakeholder|descoberta|discovery|prioriza", low):
        return "produto"
    if _tech_terms(req.texto):
        return "tecnica"
    return "comportamental"


def _interview(payload: dict[str, Any]) -> dict[str, Any]:
    jd = str(payload.get("vaga") or "")
    if len(_clean(jd, MAX_VAGA + 1)) < 120:
        raise CareerError("Cole a vaga (120 caracteres ou mais) para montar o plano de entrevista.")
    job = parse_job(jd)
    cv = parse_cv(str(payload.get("curriculo") or ""))
    profile = parse_profile(str(payload.get("perfil") or ""))
    stories = parse_stories(str(payload.get("historias") or ""))
    for req in job.requisitos:
        match_requirement(req, cv, profile)
    score = score_job(job, cv, profile)
    gaps = {gap["requisito"]: gap for gap in build_gaps(job, cv, profile, limit=10)}
    top = sorted(
        (req for req in job.requisitos if req.origem != "titulo"),
        key=lambda req: BANDS[req.banda][1], reverse=True,
    )[:6]
    plan: list[dict[str, Any]] = []
    for index, req in enumerate(top, start=1):
        kind = _interview_kind(req)
        templates = QUESTION_BANK[kind]
        terms = [_display_term(term) for term in _tech_terms(req.texto)]
        topic = ", ".join(terms[:4]) if terms else _truncate(
            re.sub(r"^(?:experi[êe]ncia|conhecimento|dom[íi]nio|ingl[êe]s)\s+(?:obrigat[óo]ri[ao]\s+)?(?:com|em|de|avan[çc]ado\s+para)?\s*",
                   "", _norm_first(req.texto)), 80)
        story = None
        for candidate in stories:
            if any(_stem(word) in {_stem(token) for token in _tokens(candidate["texto"])} for word in _content_tokens(req.texto)[:6]):
                story = candidate["titulo"]
                break
        plan.append({
            "ordem": index,
            "requisito": _truncate(req.texto, 180),
            "banda": req.banda, "banda_rotulo": BANDS[req.banda][0],
            "casamento": req.casamento,
            "perguntas": [template.format(topico=topic) for template in templates[:2]],
            "prova": req.prova[0] if req.prova else "",
            "risco": gaps.get(req.texto, {}).get("risco", "Requisito coberto pelo currículo; prepare um exemplo curto."),
            "historia": story or "",
        })
    company_questions = [
        "Como o time mede sucesso nos primeiros 90 dias desta posição?",
        "Qual é a faixa aprovada para o nível e como ela se divide entre base e variável?" if not job.comp.get("declarada") else "A faixa anunciada corresponde ao nível desta vaga?",
        "Qual é o modelo de trabalho na prática e como o time se organiza entre remoto e presencial?" if job.modelo in ("", "híbrido") else "Como o time combina o modelo {0} com a rotina de entregas?".format(job.modelo),
        "Como vocês acompanham o desenvolvimento de quem entra agora?",
        "O que faria vocês escolherem outra pessoa em vez de mim?",
    ]
    red_flags = [
        {"sinal": signal["titulo"], "pergunta": RED_FLAGS.get(signal["codigo"], {}).get("pergunta", "O que isso significa na prática?")}
        for signal in job.sinais if signal["estado"] in ("atencao", "ruim")
    ]
    deck: list[dict[str, Any]] = []
    if not stories:
        deck.append(finding(
            "must", "historia", "Sem banco de histórias", "entrevista",
            "nenhuma história fornecida",
            "Resposta sem história vira opinião; a entrevista pede exemplo.",
            "Escreva 3 histórias no formato Situação, Tarefa, Ação, Resultado, com número no resultado.",
            "Você improvisa sob pressão e perde a vaga numa pergunta previsível.",
        ))
    elif len(stories) < 3:
        deck.append(finding(
            "should", "historia", "Poucas histórias para cobrir a vaga", "entrevista",
            "{0} história(s)".format(len(stories)),
            "Com menos de 3, a mesma história responde tudo — e soa ensaiada.",
            "Prepare uma história por competência central, reaproveitando contexto.", "Perguntas diferentes recebem a mesma resposta.",
        ))
    for story in stories:
        if not story["numero"]:
            deck.append(finding(
                "should", "historia", "História sem resultado numérico", "história {0}".format(story["titulo"]),
                _truncate(story["texto"], 120),
                "Sem número, o resultado fica no adjetivo.",
                "Feche a história com número e período; se não houver, diga o que mudou de forma observável.",
                "A entrevista pede evidência e você entrega impressão.",
            ))
    for item in plan:
        if item["casamento"] in ("ausente", "indefinido") and item["banda"] in ("critical", "high"):
            deck.append(finding(
                "must", "lacuna", "Requisito central sem prova", "requisito {0}".format(item["ordem"]),
                _truncate(item["requisito"], 120),
                item["risco"],
                "Prepare a fronteira: o que já fez de parecido e como aprendeu o resto.",
                "Essa é a pergunta que decide o processo.",
            ))
    for flag in red_flags[:4]:
        deck.append(finding(
            "nice", "empresa", "Sinal a esclarecer: " + flag["sinal"], "empresa",
            flag["sinal"],
            "Sinal observável no anúncio; não é acusação.",
            "Pergunte na entrevista: " + flag["pergunta"],
            "Você descobre depois de assinar.",
        ))
    findings, counts, verdict, questions = finalize(deck, str(payload.get("modo") or "full"), [
        "Você tem uma história com número para cada requisito central?",
        "Quem entrevista nesta empresa e o que você sabe sobre essa pessoa?",
        "Qual pergunta você tem medo de receber? Prepare exatamente essa.",
    ])
    blocks = [
        {"bloco": "Antes de tudo", "tempo": "30 min", "tarefa": "Ler os 6 requisitos e escolher uma história por requisito."},
        {"bloco": "Ensaio", "tempo": "1 h", "tarefa": "Responder em voz alta, cronometrado em 2 minutos por história."},
        {"bloco": "Véspera", "tempo": "20 min", "tarefa": "Revisar números, nomes e 3 perguntas para fazer."},
    ]
    return common(
        analysis="plano de entrevista",
        mode=str(payload.get("modo") or "full"),
        title="Entrevista: {0}{1}".format(job.titulo or "vaga", " · " + job.empresa if job.empresa else ""),
        summary=[
            "**Plano:** {0} requisitos, {1} pergunta(s) para a empresa, {2} sinal(is) a esclarecer.".format(
                len(plan), len(company_questions), len(red_flags)),
            "**Confiança da triagem:** {0} · nota {1}/5.".format(
                score["confianca_rotulo"], ("{0:.1f}".format(score["nota"])).replace(".", ",")),
            "**Regra:** cada resposta sai do seu histórico; nada de resposta pronta inventada.",
        ],
        findings=findings, counts=counts, verdict=verdict, questions=questions,
        rows=[{
            "ordem": item["ordem"], "requisito": _truncate(item["requisito"], 90),
            "banda": item["banda_rotulo"], "casamento": MATCH[item["casamento"]][0],
            "historia": item["historia"],
        } for item in plan],
        metrics={
            "plano": plan, "perguntasEmpresa": company_questions, "sinais": red_flags,
            "historias": [{"titulo": s["titulo"], "numero": s["numero"], "star": s["star"]} for s in stories],
            "blocos": blocks, "confirmados": sum(1 for s in stories if s["numero"] and all(s["star"].values())),
        },
        limitations=[
            "Não sei quem vai entrevistar nem o roteiro real.",
            "As perguntas são derivadas do anúncio, não de um banco privado.",
            "Não simulo entrevista nem avalio respostas faladas.",
        ],
        extra_sections=["", "## Roteiro", ""] + [
            "### {0}. {1} ({2})\n- **Prova:** {3}\n- **Risco:** {4}\n{5}".format(
                item["ordem"], _truncate(item["requisito"], 120), item["banda_rotulo"],
                item["prova"] or "sem linha no currículo", item["risco"],
                "\n".join("- " + question for question in item["perguntas"]))
            for item in plan
        ] + ["", "## Perguntas para a empresa", ""] + ["- " + q for q in company_questions] + [
            "", "## Blocos de preparação", "",
        ] + ["- **{0}** ({1}): {2}".format(b["bloco"], b["tempo"], b["tarefa"]) for b in blocks],
    )


# ------------------------------------------------------------ funil

APPS_COLUMNS = {
    "data": ("data", "date", "dia", "aplicada em", "applied"),
    "empresa": ("empresa", "company", "organização", "organizacao"),
    "cargo": ("cargo", "vaga", "role", "posição", "posicao", "title"),
    "status": ("status", "estado", "state", "situação", "situacao"),
    "nota": ("nota", "score", "pontuação", "pontuacao"),
    "via": ("via", "canal", "fonte", "channel", "source"),
    "url": ("url", "link"),
}


def _parse_apps(text: str) -> tuple[list[dict[str, Any]], list[str]]:
    rows_raw: list[list[str]] = []
    warnings: list[str] = []
    for line in str(text or "").splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("|"):
            cells = [cell.strip() for cell in stripped.strip("|").split("|")]
            if all(re.fullmatch(r":?-{2,}:?", cell) for cell in cells if cell):
                continue
            rows_raw.append(cells)
        elif "\t" in stripped:
            rows_raw.append([cell.strip() for cell in stripped.split("\t")])
        elif stripped.count(",") >= 3:
            rows_raw.append([cell.strip().strip('"') for cell in stripped.split(",")])
    if not rows_raw:
        raise CareerError("Não encontrei linhas. Cole uma tabela (Data | Empresa | Cargo | Status | Nota) ou TSV/CSV.")
    mapping: dict[str, int] = {}
    header = rows_raw[0]
    low_header = [_norm(cell) for cell in header]
    for key, names in APPS_COLUMNS.items():
        for index, cell in enumerate(low_header):
            if cell in names:
                mapping[key] = index
                break
    has_header = "status" in mapping or "data" in mapping
    if not has_header:
        mapping = {"data": 0, "empresa": 1, "cargo": 2, "status": 3, "nota": 4}
        warnings.append("Sem cabeçalho reconhecido: li na ordem Data | Empresa | Cargo | Status | Nota.")
    else:
        rows_raw = rows_raw[1:]

    def cell(row: list[str], key: str) -> str:
        index = mapping.get(key)
        if index is None or index >= len(row):
            return ""
        return _clean(row[index], 200)

    apps: list[dict[str, Any]] = []
    for row in rows_raw:
        if not any(row):
            continue
        status_raw = cell(row, "status")
        status = STATE_ALIASES.get(_norm(status_raw).strip(), "")
        when = _parse_date(cell(row, "data"))
        apps.append({
            "data": when,
            "empresa": cell(row, "empresa"),
            "cargo": cell(row, "cargo"),
            "status": status,
            "status_original": status_raw,
            "nota": cell(row, "nota"),
            "via": cell(row, "via"),
        })
    return apps, warnings


def _parse_date(raw: str) -> str:
    text = _clean(raw, 40)
    if not text:
        return ""
    match = re.search(r"(\d{4})-(\d{2})-(\d{2})", text)
    if match:
        return "{0}-{1}-{2}".format(*match.groups())
    match = re.search(r"(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?", text)
    if match:
        day, month, year = match.groups()
        year = year or str(date.today().year)
        if len(year) == 2:
            year = "20" + year
        try:
            return date(int(year), int(month), int(day)).isoformat()
        except ValueError:
            return ""
    return ""


def _days_since(iso: str) -> int | None:
    if not iso:
        return None
    try:
        return (date.today() - datetime.strptime(iso, "%Y-%m-%d").date()).days
    except ValueError:
        return None


def _funnel(payload: dict[str, Any]) -> dict[str, Any]:
    applications = str(payload.get("aplicacoes") or "")
    if len(_clean(applications, MAX_APLICACOES + 1)) < 20:
        raise CareerError("Cole a lista de candidaturas (20 caracteres ou mais) para ler o funil.")
    apps, warnings = _parse_apps(applications)
    if not apps:
        raise CareerError("Nenhuma candidatura legível. Confira as colunas: Data | Empresa | Cargo | Status | Nota.")
    window = _as_int(payload.get("janela"), 90, 0, 3650)
    mode = str(payload.get("modo") or "full")
    today = date.today()
    if window:
        recent = [app for app in apps if (days := _days_since(app["data"])) is not None and days <= window]
        outside = [app for app in apps if app not in recent]
    else:
        recent, outside = apps, []

    counts = {key: 0 for key in STATES}
    unknown: list[dict[str, Any]] = []
    for app in apps:
        if app["status"]:
            counts[app["status"]] += 1
        else:
            unknown.append(app)
    sent = sum(1 for app in apps if app["status"] and app["status"] != "avaliada")
    responded = sum(counts[key] for key in ("respondeu", "teste", "entrevista", "oferta", "contratada", "recusada"))
    interviewed = sum(counts[key] for key in ("entrevista", "oferta", "contratada"))
    offers = sum(counts[key] for key in ("oferta", "contratada"))
    active = [app for app in apps if app["status"] in ACTIVE_STATES]

    def rate(numerator: int, denominator: int) -> dict[str, Any]:
        if denominator == 0:
            return {"valor": None, "numerador": numerator, "denominador": 0}
        return {"valor": round(100 * numerator / denominator, 1), "numerador": numerator, "denominador": denominator}

    stale = []
    for app in active:
        days = _days_since(app["data"])
        if days is not None and days >= 14:
            stale.append({**app, "dias": days})
    stale.sort(key=lambda item: -(item["dias"] or 0))

    month_rows: dict[str, dict[str, int]] = {}
    for app in apps:
        key = (app["data"] or "sem data")[:7]
        bucket = month_rows.setdefault(key, {"total": 0, "entrevista": 0, "oferta": 0})
        bucket["total"] += 1
        if app["status"] in ("entrevista", "oferta", "contratada"):
            bucket["entrevista"] += 1
        if app["status"] in ("oferta", "contratada"):
            bucket["oferta"] += 1

    deck: list[dict[str, Any]] = []
    for app in unknown:
        deck.append(finding(
            "must", "status", "Status desconhecido", app["empresa"] or "linha",
            "{0} → '{1}'".format(app["cargo"] or "cargo", app["status_original"] or "vazio"),
            "Um status fora da lista some de qualquer taxa calculada.",
            "Use: {0}.".format(", ".join(value[0] for value in STATES.values())),
            "O funil fica menor do que a realidade.",
        ))
    if len(apps) >= 5 and interviewed == 0:
        deck.append(finding(
            "should", "conversao", "Nenhuma entrevista no período", "funil",
            "{0} candidaturas, 0 entrevistas".format(sent or len(apps)),
            "Volume sem retorno costuma indicar aderência baixa ou material genérico.",
            "Reveja a triagem das últimas 5 vagas e o primeiro parágrafo do currículo.",
            "Você repete o mesmo envio e colhe o mesmo silêncio.",
        ))
    if stale:
        deck.insert(0, finding(
            "should", "followup", "{0} candidatura(s) sem retorno há 14 dias ou mais".format(len(stale)), "funil",
            ", ".join("{0} ({1}d)".format(app["empresa"] or "?", app["dias"]) for app in stale[:4]),
            "Processo parado não é processo vivo.",
            "Mande uma mensagem curta de acompanhamento ou marque como descartada.",
            "O funil acumula zumbis e as taxas mentem.",
        ))
    if not any(app["data"] for app in apps):
        deck.append(finding(
            "must", "data", "Nenhuma data legível", "funil",
            "coluna de data vazia",
            "Sem data não há janela, idade nem coorte.",
            "Use AAAA-MM-DD ou DD/MM/AAAA na primeira coluna.",
            "O funil vira uma lista sem tempo.",
        ))
    if len(apps) < 8:
        deck.append(finding(
            "nice", "amostra", "Amostra pequena para taxa", "funil",
            "{0} candidaturas".format(len(apps)),
            "Com menos de 8 linhas, percentual é aritmética, não tendência.",
            "Leia os números como contagem, não como taxa.",
            "Você otimiza ruído.",
        ))
    for warning in warnings:
        deck.append(finding(
            "nice", "formato", "Formato lido com suposição", "entrada",
            warning, "A ordem das colunas foi inferida.", "Inclua um cabeçalho com os nomes das colunas.",
            "Uma coluna trocada muda todas as taxas.",
        ))
    findings, counts_f, verdict, questions = finalize(deck, mode, [
        "Qual dessas candidaturas você ainda quer levar adiante?",
        "A última recusa trouxe algum motivo concreto?",
        "Qual etapa você mais erra: triagem, teste ou conversa?",
    ])
    summary = [
        "**Candidaturas:** {0} no total · {1} na janela de {2} dias.".format(len(apps), len(recent), window or "toda"),
        "**Conversão:** resposta {0} · entrevista {1} · oferta {2}.".format(
            _pct(rate(responded, sent or 1)["valor"]), _pct(rate(interviewed, sent or 1)["valor"]),
            _pct(rate(offers, sent or 1)["valor"])),
        "**Atenção:** {0} ativa(s), {1} sem retorno há 14+ dias, {2} status ilegível(is).".format(
            len(active), len(stale), len(unknown)),
    ]
    extra = ["", "## Por status", "", "| Status | Quantidade |", "| --- | --- |"]
    for key, (label, _) in STATES.items():
        extra.append("| {0} | {1} |".format(label, counts[key]))
    extra += ["", "## Por mês", "", "| Mês | Candidaturas | Entrevistas | Ofertas |", "| --- | --- | --- | --- |"]
    for key in sorted(month_rows, reverse=True):
        bucket = month_rows[key]
        extra.append("| {0} | {1} | {2} | {3} |".format(key, bucket["total"], bucket["entrevista"], bucket["oferta"]))
    extra += ["", "## Honestidade dos números", "",
              "- Percentual com menos de 8 candidaturas é contagem disfarçada; não vire tendência.",
              "- Candidaturas ainda ativas ficam fora da taxa de recusa (dados censurados).",
              "- Sem data de transição por etapa, não há velocidade de etapa; só idade da candidatura.",
              "- {0} linha(s) fora da janela de {1} dias não entram nas taxas.".format(len(outside), window) if window else "- Janela total: todas as linhas entram."]
    return common(
        analysis="funil de candidaturas",
        mode=mode,
        title="Funil: {0} candidaturas".format(len(apps)),
        summary=summary,
        findings=findings, counts=counts_f, verdict=verdict, questions=questions,
        rows=[{
            "data": app["data"], "empresa": app["empresa"], "cargo": _truncate(app["cargo"], 60),
            "status": STATES[app["status"]][0] if app["status"] else "?",
            "nota": app["nota"],
        } for app in apps],
        metrics={
            "total": len(apps), "janela": window, "porStatus": counts,
            "taxas": {
                "resposta": rate(responded, sent), "entrevista": rate(interviewed, sent),
                "oferta": rate(offers, sent),
            },
            "ativas": len(active), "paradas": len(stale), "semStatus": len(unknown),
            "meses": month_rows, "recusas": counts["recusada"], "foraDaJanela": len(outside),
        },
        limitations=[
            "Não leio e-mail, calendário nem LinkedIn: o funil é só o que você colou.",
            "Não há data de cada transição, então não calculo velocidade por etapa.",
            "Taxa com amostra pequena não é previsão.",
        ],
        extra_sections=extra,
    )


def _pct(value: float | None) -> str:
    if value is None:
        return "—"
    return ("{0:.1f}%".format(value)).replace(".", ",")


# ------------------------------------------------------------ catálogo

def career_catalog() -> dict[str, Any]:
    return {
        "bandas": [
            {"chave": key, "rotulo": BANDS[key][0], "peso": BANDS[key][1]}
            for key in BAND_ORDER
        ],
        "dimensoes": [
            {"chave": key, "rotulo": label, "peso": weight,
             "leitura": {
                 "aderencia": "cobertura ponderada dos requisitos pela prova do currículo",
                 "alvo": "termos em comum entre a vaga e o seu alvo declarado",
                 "comp": "faixa anunciada contra o seu piso e o seu alvo",
                 "cultura": "sinais de flexibilidade, desenvolvimento e inclusão no texto",
                 "risco": "legitimidade do anúncio e idade da publicação",
             }[key]}
            for key, (label, weight) in DIMENSIONS.items()
        ],
        "evidencia": [
            {"chave": key, "rotulo": {"stated": "Declarada", "structural": "Estrutural", "inferred": "Inferida"}[key],
             "leitura": text}
            for key, text in EVIDENCE.items()
        ],
        "casamento": [
            {"chave": key, "rotulo": MATCH[key][0], "credito": MATCH[key][1]}
            for key in MATCH
        ],
        "confianca": [
            {"chave": key, "rotulo": label} for key, label in CONFIDENCE.items()
        ],
        "faixasNota": [
            {"minimo": limit, "acao": action, "leitura": text}
            for limit, action, text in BANDS_SCORE
        ],
        "estados": [
            {"chave": key, "rotulo": label, "leitura": text, "ativa": key in ACTIVE_STATES}
            for key, (label, text) in STATES.items()
        ],
        "ats": [
            {"chave": key, "titulo": data["titulo"], "peso": data["peso"], "regra": data["regra"]}
            for key, data in ATS_CHECKS.items()
        ],
        "notas": [{"minimo": limit, "letra": letter} for limit, letter in GRADES],
        "tiposEmpresa": [
            {"chave": key, "rotulo": data["rotulo"], "confiabilidade": data["confiabilidade"]}
            for key, data in COMPANY_TYPES.items()
        ],
        "sinais": [
            {"codigo": key, "titulo": data["titulo"], "nivel": data["nivel"], "pergunta": data["pergunta"]}
            for key, data in RED_FLAGS.items()
        ],
        "cliches": list(CLICHES),
        "verbosFortes": list(STRONG_VERBS),
        "regras": [
            "A nota é triagem declarada, não probabilidade de contratação.",
            "Abaixo de 4,0 não se aplica sem um motivo nomeado — e a decisão é sua.",
            "Nenhum número entra na carta sem origem no currículo ou no perfil.",
            "Sinal de legitimidade é sinal, nunca acusação.",
            "Abaixo de 8 candidaturas, percentual é contagem, não tendência.",
            "O JARVIS não envia candidatura, não abre portal e não altera seu currículo.",
        ],
    }


# ------------------------------------------------------------ nomes públicos

def triage_job(payload: dict[str, Any]) -> dict[str, Any]:
    return _triage(payload)


def audit_ats(payload: dict[str, Any]) -> dict[str, Any]:
    return _ats(payload)


def audit_bullets(payload: dict[str, Any]) -> dict[str, Any]:
    return _bullets(payload)


def draft_letter(payload: dict[str, Any]) -> dict[str, Any]:
    return _letter(payload)


def plan_interview(payload: dict[str, Any]) -> dict[str, Any]:
    return _interview(payload)


def read_funnel(payload: dict[str, Any]) -> dict[str, Any]:
    return _funnel(payload)
