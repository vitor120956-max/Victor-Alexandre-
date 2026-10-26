"""Distilação de pessoa em perfil com lastro (0.35.0).

Porta a parte determinística de `titanwings/distilly` (MIT): famílias de
personagem, perfil de pessoa empacotado como skill, gate de qualidade,
hierarquia de fonte, tabela de hospedeiros e o fluxo de correção.

O que esta camada **não** faz é o que o original faz com um modelo: ela não
escreve a persona. Ela mede o material, aponta o que tem lastro, mostra o que
falta e recusa afirmação sem fonte. O texto do perfil é seu — ou do modelo que
você escolher —, e entra aqui para ser conferido.

Regra que organiza tudo: citação é prova, não enfeite. Sem linha de origem,
uma frase é opinião.
"""
from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .review import common, finalize, finding

VERSAO = "0.46.0"

PROJETO = Path(__file__).resolve().parents[1]
MODOS = ("lite", "full", "ultra")

MAX_CORPUS = 900_000
MAX_TEXTO = 900_000
MAX_ROWS = 200
MAX_SLUG = 40
CITACAO_MAXIMA = 240

RESERVADOS_WINDOWS = {
    "con", "prn", "aux", "nul",
    *(f"com{i}" for i in range(1, 10)),
    *(f"lpt{i}" for i in range(1, 10)),
}

# Quatro famílias do projeto original, com as dimensões que o perfil precisa cobrir.
FAMILIAS: dict[str, dict[str, Any]] = {
    "colleague": {
        "rotulo": "Colega",
        "dominio": "trabalho",
        "raiz": "skills/colleague",
        "relacao": "coworker",
        "dimensoes": (
            "padroes_de_decisao",
            "padrao_tecnico",
            "fluxo_de_trabalho",
            "voz",
            "comportamento_no_time",
            "limites",
        ),
    },
    "relationship": {
        "rotulo": "Relação",
        "dominio": "pessoal",
        "raiz": "skills/relationship",
        "relacao": "relationship",
        "dimensoes": (
            "voz",
            "gatilhos_emocionais",
            "conflito",
            "reparo",
            "memoria_afetiva",
            "limites",
        ),
    },
    "celebrity": {
        "rotulo": "Figura pública",
        "dominio": "público",
        "raiz": "skills/celebrity",
        "relacao": "public_figure",
        "dimensoes": (
            "modelos_mentais",
            "decisoes_observaveis",
            "dna_de_expressao",
            "genealogia_intelectual",
            "tensao_interna",
            "o_que_nao_sabe",
        ),
    },
    "owner": {
        "rotulo": "Dono do agente",
        "dominio": "pessoal",
        "raiz": "skills/owner",
        "relacao": "owner",
        "dimensoes": (
            "preferencias",
            "contexto_de_vida",
            "rotina",
            "limites",
            "como_quer_ser_tratado",
        ),
    },
}

# Sinais lexicais por dimensão. Não é análise semântica: é o que dá para provar
# sem modelo, e o relatório diz isso.
SINAIS: dict[str, tuple[str, ...]] = {
    "padroes_de_decisao": ("decidi", "escolhi", "optei", "vamos", "prefiro", "melhor", "porque"),
    "padrao_tecnico": ("teste", "deploy", "arquitetura", "servidor", "código", "codigo", "banco", "api"),
    "fluxo_de_trabalho": ("processo", "rotina", "primeiro", "depois", "revisão", "revisao", "checklist"),
    "voz": ("acho", "na verdade", "sinceramente", "tipo", "né", "ne", "cara"),
    "comportamento_no_time": ("time", "equipe", "reunião", "reuniao", "feedback", "ajuda", "delega"),
    "limites": ("não sei", "nao sei", "não faço", "nao faco", "preciso", "limite", "não posso"),
    "gatilhos_emocionais": ("sinto", "fiquei", "irritado", "feliz", "triste", "medo", "ansioso"),
    "conflito": ("briga", "discussão", "discussao", "conflito", "irritou", "discord"),
    "reparo": ("desculpa", "foi mal", "perdão", "perdao", "vamos resolver", "entendi"),
    "memoria_afetiva": ("lembro", "lembrança", "lembranca", "sempre", "quando a gente"),
    "modelos_mentais": ("modelo", "ideia", "teoria", "penso", "premissa", "princípio", "principio"),
    "decisoes_observaveis": ("decidiu", "optou", "escolheu", "anunciou", "recusou"),
    "dna_de_expressao": ("metáfora", "metafora", "ritmo", "frase", "estilo", "escreve"),
    "genealogia_intelectual": ("influenci", "leu", "inspirou", "citou", "baseado em"),
    "tensao_interna": ("contradiz", "tensão", "tensao", "ao mesmo tempo", "mas também", "mas tambem"),
    "o_que_nao_sabe": ("não sabe", "nao sabe", "não conhece", "nao conhece", "fora da área", "fora da area"),
    "preferencias": ("prefiro", "gosto", "não gosto", "nao gosto", "quero"),
    "contexto_de_vida": ("moro", "morava", "família", "familia", "filho", "trabalho em"),
    "rotina": ("acordo", "de manhã", "de manha", "todo dia", "semana", "horário", "horario"),
    "como_quer_ser_tratado": ("me chame", "me trate", "prefiro que", "não me", "nao me"),
}

# Hierarquia de fonte do projeto original: peso 1-3 é primária, 4-5 média, 6-7 baixa.
PESO_PRIMARIA = (1, 2, 3)
PESO_MEDIA = (4, 5)
PADRAO_PESO = re.compile(r"source weight:\s*([1-7])", re.IGNORECASE)
PADRAO_URL = re.compile(r"https?://[^\s)>\]]+")
PADRAO_TIMESTAMP = re.compile(r"\b\d{2}:\d{2}:\d{2}(?:[.,]\d{1,3})?\b")
PADRAO_HOSPEDEIRO = re.compile(r">>>\s*(\S+)")
PADRAO_FALANTE = re.compile(r"^([^:]{1,40}):\s+(.+)$")

URLS_GENERICAS = {"", "/", "/topic", "/topic/", "/search", "/search/", "/video", "/video/", "/article", "/article/", "/read", "/read/", "/podcast", "/podcast/"}

# Tabela de hospedeiros do original (tools/hosts.json), com o comando de invocação.
HOSPEDEIROS: dict[str, dict[str, Any]] = {
    "claude-code": {"nome": "Claude Code", "skills": (".claude", "skills"), "invocacao": "/distilly"},
    "openclaw": {"nome": "OpenClaw", "skills": (".openclaw", "workspace", "skills"), "invocacao": "/distilly ou /skill distilly"},
    "hermes": {
        "nome": "Hermes",
        "skills": (".hermes", "skills", "openclaw-imports"),
        "gerado": (".hermes", "skills", "distilly-generated"),
        "invocacao": "/distilly",
    },
    "codex": {"nome": "Codex", "skills": (".agents", "skills"), "invocacao": "$distilly ou /skills"},
    "deepseek-harness": {
        "nome": "DeepSeek Harness",
        "skills": (".dsh", "skills"),
        "home_env": "DSH_HOME",
        "invocacao": "/distilly",
    },
    "pi": {"nome": "Pi", "skills": (".pi", "agent", "skills"), "invocacao": "/skill:distilly"},
    "grok-build": {"nome": "Grok Build", "skills": (".grok", "skills"), "invocacao": "/distilly"},
    "opencode": {"nome": "OpenCode", "skills": (".config", "opencode", "skills"), "invocacao": "nativo, sem comando"},
}

CHECAGENS_OBRIGATORIAS = (
    "modelos_mentais",
    "limites",
    "dna_de_expressao",
    "fronteiras_honestas",
    "tensao_interna",
    "lastro_de_fonte",
    "seguranca_de_direito",
)

CHECAGENS_ESTRITAS = (
    "genealogia_intelectual",
    "protocolo_de_agente",
    "hierarquia_de_fonte",
    "cadeia_de_revisao",
    "profundidade_de_validacao",
    "profundidade_de_pesquisa",
)

STOPWORDS = {
    "para", "porque", "como", "mais", "menos", "muito", "muita", "isso", "isto", "aquilo",
    "quando", "onde", "então", "entao", "também", "tambem", "sobre", "entre", "depois",
    "antes", "agora", "coisa", "coisas", "gente", "ainda", "aqui", "ali", "assim", "mesmo",
    "pode", "poderia", "deve", "deveria", "fazer", "feito", "faz", "vai", "vou", "está",
    "esta", "estou", "estava", "ser", "sou", "era", "tem", "tinha", "ter", "há", "ha",
    "the", "and", "that", "this", "with", "from", "have", "will", "would", "there",
}


class DistilarError(ValueError):
    """Entrada inválida ou operação recusada."""


# ---------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------


def _modo(modo: str) -> str:
    valor = (modo or "full").strip().lower()
    if valor not in MODOS:
        raise DistilarError("Modo inválido: use lite, full ou ultra.")
    return valor


def _familia(nome: str) -> str:
    valor = (nome or "").strip().lower()
    if valor not in FAMILIAS:
        raise DistilarError(f"Família inválida: `{nome}`. Use {', '.join(FAMILIAS)}.")
    return valor


def _tokens(texto: str) -> set[str]:
    return {
        palavra
        for palavra in re.findall(r"[a-zà-ÿ]{4,}", (texto or "").lower())
        if palavra not in STOPWORDS
    }


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _slug(nome: str) -> str:
    """Slug portátil: sem acento, minúsculo, hífen, até 40 caracteres."""
    base = unicodedata.normalize("NFKD", (nome or "").strip())
    base = "".join(letra for letra in base if not unicodedata.combining(letra))
    base = re.sub(r"[^a-zA-Z0-9]+", "-", base).strip("-").lower()
    return base[:MAX_SLUG].strip("-")


def slug_seguro(nome: str) -> str:
    """Slug portátil, recusando nome reservado do sistema operacional."""
    slug = _slug(nome)
    if slug in RESERVADOS_WINDOWS:
        raise DistilarError(f"`{slug}` é nome reservado do Windows e não serve como pasta de skill.")
    return slug


def _normalizar_url(url: str) -> str:
    return url.rstrip(".,;:!?")


def _url_com_conteudo(url: str) -> bool:
    from urllib.parse import urlparse

    try:
        caminho = urlparse(url).path
    except ValueError:
        return False
    return caminho not in URLS_GENERICAS


def _corpo(texto: str, *, limite: int = MAX_CORPUS) -> str:
    valor = texto or ""
    if len(valor) > limite:
        raise DistilarError(f"Texto acima do teto de {limite} caracteres. Divida em partes.")
    if not valor.strip():
        raise DistilarError("Texto vazio: cole o material antes de pedir a análise.")
    return valor


# ---------------------------------------------------------------------------
# 1. Perfil a partir do corpus
# ---------------------------------------------------------------------------


def _analisar_corpus(corpus: str) -> dict[str, Any]:
    fontes: list[str] = []
    mensagens: list[dict[str, Any]] = []
    atual = "(colado)"
    for numero, linha in enumerate(corpus.splitlines(), start=1):
        limpa = linha.rstrip()
        if not limpa.strip():
            continue
        achado = PADRAO_HOSPEDEIRO.search(limpa)
        if achado:
            atual = achado.group(1)
            if atual not in fontes:
                fontes.append(atual)
            continue
        falante = PADRAO_FALANTE.match(limpa.strip().lstrip("-* "))
        if falante and len(falante.group(2)) > 2:
            mensagens.append(
                {"linha": numero, "fonte": atual, "autor": falante.group(1).strip()[:40], "texto": falante.group(2).strip()}
            )
        else:
            mensagens.append({"linha": numero, "fonte": atual, "autor": "", "texto": limpa.strip()})
    if not fontes:
        fontes = ["(colado)"]
    palavras = sum(len(re.findall(r"\S+", item["texto"])) for item in mensagens)
    return {"fontes": fontes, "mensagens": mensagens, "palavras": palavras}


def _evidencias(mensagens: list[dict[str, Any]]) -> list[dict[str, Any]]:
    achados: list[dict[str, Any]] = []
    for item in mensagens:
        texto = item["texto"]
        if len(texto) < 25:
            continue
        baixo = texto.lower()
        for dimensao, sinais in SINAIS.items():
            for sinal in sinais:
                if sinal in baixo:
                    achados.append(
                        {
                            "dimensao": dimensao,
                            "sinal": sinal,
                            "citacao": texto[:CITACAO_MAXIMA],
                            "fonte": item["fonte"],
                            "linha": item["linha"],
                            "forca": "alta" if len(texto) >= 90 else "média",
                        }
                    )
                    break
    return achados


def perfil(*, corpus: str, familia: str = "colleague", modo: str = "full") -> dict[str, Any]:
    """Mede o corpus e mostra o que já tem lastro por dimensão — e o que falta."""
    modo = _modo(modo)
    familia = _familia(familia)
    texto = _corpo(corpus)
    dados = _analisar_corpus(texto)
    dimensoes = FAMILIAS[familia]["dimensoes"]
    achados = _evidencias(dados["mensagens"])

    por_dimensao: dict[str, list[dict[str, Any]]] = {nome: [] for nome in dimensoes}
    for achado in achados:
        if achado["dimensao"] in por_dimensao:
            por_dimensao[achado["dimensao"]].append(achado)

    cobertas, parciais, ausentes = [], [], []
    for nome, itens in por_dimensao.items():
        if len(itens) >= 3:
            cobertas.append(nome)
        elif itens:
            parciais.append(nome)
        else:
            ausentes.append(nome)

    rows = []
    for nome in dimensoes:
        itens = sorted(por_dimensao[nome], key=lambda item: (item["forca"] != "alta", item["linha"]))[:4]
        rows.append(
            {
                "dimensao": nome,
                "evidencias": len(itens),
                "estado": "coberta" if nome in cobertas else ("parcial" if nome in parciais else "ausente"),
                "citacao": itens[0]["citacao"][:110] if itens else "—",
                "fonte": f"{itens[0]['fonte']}:{itens[0]['linha']}" if itens else "—",
            }
        )

    findings: list[dict[str, Any]] = []
    if dados["palavras"] < 300:
        findings.append(
            finding(
                "must",
                "corpus",
                "Material insuficiente para um perfil",
                f"{dados['palavras']} palavras em {len(dados['mensagens'])} linhas",
                "Um perfil precisa de repetição para distinguir padrão de acidente.",
                "Com menos de 300 palavras, qualquer dimensão 'coberta' é coincidência.",
                "Junte mais material — conversas, documentos, e-mails — antes de destilar.",
                "O perfil vira caricatura de três frases.",
            )
        )
    if ausentes:
        findings.append(
            finding(
                "should",
                "lacuna",
                "Dimensões sem nenhuma evidência",
                ", ".join(ausentes),
                f"{len(ausentes)} de {len(dimensoes)} dimensões de `{familia}` não têm uma linha de apoio.",
                "Perfil com buraco preenchido por imaginação é o erro mais comum da destilação.",
                "Ou junte material que toque essas dimensões, ou escreva 'não há evidência' na seção.",
                "O agente inventa justamente onde você não olhou.",
            )
        )
    if len(dados["fontes"]) == 1 and dados["fontes"] != ["(colado)"]:
        findings.append(
            finding(
                "nice",
                "fonte",
                "Uma única fonte",
                dados["fontes"][0],
                "Todo o material vem do mesmo arquivo.",
                "Fonte única não permite confrontar versão nem datar mudança de opinião.",
                "Acrescente pelo menos uma segunda fonte com data.",
                "Você não distingue o que a pessoa pensa do que ela pensava.",
            )
        )
    if parciais:
        findings.append(
            finding(
                "nice",
                "lacuna",
                "Dimensões com uma ou duas evidências",
                ", ".join(parciais),
                f"{len(parciais)} dimensões têm menos de três evidências.",
                "Uma evidência isolada pode ser exceção, não padrão.",
                "Busque uma terceira ocorrência antes de escrever a seção como regra.",
                "O perfil generaliza a partir de um caso.",
            )
        )
    findings, counts, veredito, questions = finalize(
        findings, modo, ["Quantas fontes independentes você tem?", "O material cobre tempo suficiente para mostrar mudança?"]
    )
    resultado = common(
        analysis="perfil",
        mode=modo,
        title="Perfil a partir do material",
        summary=[
            f"Família **{FAMILIAS[familia]['rotulo']}** com {len(dimensoes)} dimensões.",
            f"{len(dados['mensagens'])} linha(s), {dados['palavras']} palavra(s), {len(dados['fontes'])} fonte(s).",
            f"{len(cobertas)} dimensão(ões) coberta(s), {len(parciais)} parcial(is), {len(ausentes)} sem evidência.",
        ],
        findings=findings,
        counts=counts,
        verdict=veredito,
        questions=questions,
        rows=rows,
        metrics={
            "mensagens": len(dados["mensagens"]),
            "palavras": dados["palavras"],
            "fontes": len(dados["fontes"]),
            "evidencias": len(achados),
            "cobertas": len(cobertas),
            "parciais": len(parciais),
            "ausentes": len(ausentes),
        },
        limitations=[
            "A busca é lexical: encontra o sinal, não entende o contexto.",
            "Ironia, negação e citação de terceiro passam como sinal positivo.",
            "Cobertura mede ocorrência, não qualidade da evidência.",
            "O perfil em si não é escrito aqui: esta skill mede o material.",
        ],
        extra_sections=[
            "",
            "## Citações candidatas",
            "",
            *[f"- `{item['fonte']}:{item['linha']}` — {item['citacao'][:160]}" for item in achados[:12]],
        ],
    )
    resultado["familia"] = familia
    resultado["fontes"] = dados["fontes"][:20]
    resultado["ausentes"] = ausentes
    return resultado


# ---------------------------------------------------------------------------
# 2. Dimensões por família
# ---------------------------------------------------------------------------


def dimensoes(*, familia: str = "", modo: str = "full") -> dict[str, Any]:
    """Lista as famílias e, para a escolhida, o que cada dimensão exige."""
    modo = _modo(modo)
    familias = [familia] if familia else list(FAMILIAS)
    rows: list[dict[str, Any]] = []
    for nome in familias:
        if nome not in FAMILIAS:
            raise DistilarError(f"Família inválida: `{nome}`. Use {', '.join(FAMILIAS)}.")
        dados = FAMILIAS[nome]
        for dimensao in dados["dimensoes"]:
            sinais = SINAIS.get(dimensao, ())
            rows.append(
                {
                    "familia": nome,
                    "dimensao": dimensao,
                    "sinais": ", ".join(sinais[:5]),
                    "raiz": dados["raiz"],
                }
            )
    findings, counts, veredito, questions = finalize([], modo, ["Qual família descreve o seu caso?"])
    resultado = common(
        analysis="dimensoes",
        mode=modo,
        title="Dimensões por família",
        summary=[
            f"{len(rows)} dimensão(ões) em {len(familias)} família(s).",
            "Cada dimensão só é declarada quando existe linha de origem no material.",
        ],
        findings=findings,
        counts=counts,
        verdict=veredito,
        questions=questions,
        rows=rows[:MAX_ROWS],
        metrics={"familias": len(familias), "dimensoes": len(rows)},
        limitations=[
            "As dimensões vêm do desenho do projeto original, não de pesquisa validada.",
            "As palavras-chave são um ponto de partida: ajuste ao vocabulário do material.",
            "Nenhuma dimensão é obrigatória para toda família — o recorte é seu.",
        ],
    )
    resultado["familias"] = {nome: list(FAMILIAS[nome]["dimensoes"]) for nome in familias}
    return resultado


# ---------------------------------------------------------------------------
# 3. Esqueleto do perfil
# ---------------------------------------------------------------------------


def esboco(*, nome: str, familia: str = "colleague", corpus: str = "", modo: str = "full") -> dict[str, Any]:
    """Monta o esqueleto do SKILL.md do perfil. Não escreve persona: abre espaço com prova pendente."""
    modo = _modo(modo)
    familia = _familia(familia)
    bruto = (nome or "").strip()
    if not bruto:
        raise DistilarError("Informe o nome da pessoa ou do perfil.")
    slug = _slug(bruto)
    if not slug:
        raise DistilarError("O nome não gerou slug utilizável: use letras ou números.")
    if slug in RESERVADOS_WINDOWS:
        raise DistilarError(f"`{slug}` é nome reservado do Windows e não serve como pasta de skill.")
    if bruto.lower() in RESERVADOS_WINDOWS:
        raise DistilarError("Nome reservado do sistema operacional. Escolha outro.")

    dados_familia = FAMILIAS[familia]
    cobertura: dict[str, int] = {dimensao: 0 for dimensao in dados_familia["dimensoes"]}
    fontes: list[str] = []
    if corpus.strip():
        analise = _analisar_corpus(_corpo(corpus))
        fontes = analise["fontes"]
        for achado in _evidencias(analise["mensagens"]):
            if achado["dimensao"] in cobertura:
                cobertura[achado["dimensao"]] += 1

    descricao = f"Perfil de {bruto} ({dados_familia['rotulo'].lower()}) com lastro no material fornecido."
    linhas = [
        "---",
        f"name: distilly-{slug}",
        f'description: "{descricao}"',
        f"version: {VERSAO}",
        "user-invocable: true",
        "---",
        "",
        f"# {bruto}",
        "",
        f"> Perfil de **{dados_familia['rotulo'].lower()}** gerado como esqueleto. Cada seção só vale quando",
        "> aponta a linha de origem. Onde não há prova, o texto diz que não há.",
        "",
        "## Como usar",
        "",
        "- Responda no tom descrito em **Voz**, sem prometer o que a pessoa não saberia.",
        "- Se a pergunta cair em **O que não sabe**, diga que não sabe em vez de improvisar.",
        "",
        "## Retrato",
        "",
        "<!-- evidência pendente: 2 linhas de origem sobre quem é esta pessoa -->",
        "",
    ]
    for dimensao in dados_familia["dimensoes"]:
        quantidade = cobertura.get(dimensao, 0)
        estado = "coberta" if quantidade >= 3 else ("parcial" if quantidade else "sem evidência")
        linhas += [
            f"## {dimensao.replace('_', ' ').capitalize()}",
            "",
            f"<!-- evidência: {quantidade} linha(s) — {estado} -->",
            "",
        ]
        if quantidade:
            linhas += ["- (escreva o padrão observado e cite a linha de origem)", ""]
        else:
            linhas += ["- Não há evidência sobre este ponto no material fornecido.", ""]
    linhas += [
        "## Limites honestos",
        "",
        "- O que este perfil **não** afirma: não é a pessoa, é um recorte observável do material.",
        "- O que este perfil não sabe: tudo que não está nas fontes listadas abaixo.",
        "",
        "## Fontes",
        "",
        *[f"- `{fonte}`" for fonte in (fontes or ["(nenhuma fonte declarada)"])],
        "",
    ]
    conteudo = "\n".join(linhas)
    manifesto = {
        "slug": slug,
        "familia": familia,
        "rotulo": dados_familia["rotulo"],
        "raiz": dados_familia["raiz"],
        "versao": VERSAO,
        "gerado_em": datetime.now(timezone.utc).isoformat(),
        "artefatos": ["SKILL.md", "manifest.json"],
        "fontes": fontes,
        "dimensoes": [
            {"nome": dimensao, "evidencias": cobertura.get(dimensao, 0)} for dimensao in dados_familia["dimensoes"]
        ],
        "sha256": hashlib.sha256(conteudo.encode("utf-8")).hexdigest(),
    }

    sem_evidencia = [nome for nome, quantidade in cobertura.items() if quantidade == 0]
    findings: list[dict[str, Any]] = []
    if sem_evidencia:
        findings.append(
            finding(
                "should",
                "lacuna",
                "Esqueleto com seções vazias",
                ", ".join(sem_evidencia),
                f"{len(sem_evidencia)} seção(ões) foram abertas como 'sem evidência'.",
                "Deixar a marca é melhor que preencher; mas o perfil fica incompleto.",
                "Junte material para essas dimensões ou remova a seção do escopo.",
                "O agente lê o vazio como permissão para inventar.",
            )
        )
    if not fontes:
        findings.append(
            finding(
                "must",
                "fonte",
                "Esqueleto sem fonte declarada",
                slug,
                "Nenhum arquivo de origem foi informado.",
                "Perfil sem lista de fontes não pode ser auditado depois.",
                "Cole o material com cabeçalhos `>>> arquivo` para que as fontes entrem no manifesto.",
                "O perfil vira afirmação sem procedência.",
            )
        )
    findings, counts, veredito, questions = finalize(
        findings, modo, ["O nome público deve ser esse?", "Quem vai instalar este perfil?"]
    )
    resultado = common(
        analysis="esboco",
        mode=modo,
        title="Esqueleto do perfil",
        summary=[
            f"Slug **{slug}**, família **{dados_familia['rotulo']}**, destino sugerido `{dados_familia['raiz']}/{slug}/`.",
            f"{len(fontes)} fonte(s), {sum(cobertura.values())} evidência(s) distribuídas.",
            "Nada foi escrito em disco: o conteúdo abaixo é a proposta.",
        ],
        findings=findings,
        counts=counts,
        verdict=veredito,
        questions=questions,
        rows=[
            {"dimensao": nome, "evidencias": quantidade, "estado": "coberta" if quantidade >= 3 else ("parcial" if quantidade else "sem evidência")}
            for nome, quantidade in cobertura.items()
        ],
        metrics={"dimensoes": len(cobertura), "fontes": len(fontes), "evidencias": sum(cobertura.values())},
        limitations=[
            "É um esqueleto: o texto de cada seção é seu, ou do modelo que você usar.",
            "As marcas `<!-- evidência: -->` devem ser trocadas por citação com linha.",
            "O manifesto é proposta; nada é gravado.",
        ],
        extra_sections=["", "## SKILL.md proposto", "", "```markdown", conteudo[:20_000], "```"],
    )
    resultado["slug"] = slug
    resultado["conteudo"] = conteudo
    resultado["manifesto"] = manifesto
    resultado["destino"] = f"{dados_familia['raiz']}/{slug}/"
    return resultado


# ---------------------------------------------------------------------------
# 4. Gate de qualidade
# ---------------------------------------------------------------------------


def _metricas_pesquisa(texto: str) -> dict[str, Any]:
    pesos = [int(valor) for valor in PADRAO_PESO.findall(texto)]
    urls = {_normalizar_url(url) for url in PADRAO_URL.findall(texto)}
    urls_com_conteudo = {url for url in urls if _url_com_conteudo(url)}
    primarias = sum(1 for peso in pesos if peso in PESO_PRIMARIA)
    medias = sum(1 for peso in pesos if peso in PESO_MEDIA)
    baixas = sum(1 for peso in pesos if peso not in PESO_PRIMARIA and peso not in PESO_MEDIA)
    total = primarias + medias + baixas
    blocos = len(re.findall(r"source weight:", texto, re.IGNORECASE))
    citacoes_longas = 0
    for linha in texto.splitlines():
        limpa = linha.strip()
        if limpa.startswith(">"):
            citacoes_longas += 1
        elif PADRAO_TIMESTAMP.search(limpa):
            citacoes_longas += 1
        elif any(marca in limpa for marca in ('"', "“", "”")):
            if len(re.findall(r"\S+", limpa)) > 25:
                citacoes_longas += 1
    return {
        "urls": len(urls_com_conteudo),
        "blocos_de_fonte": blocos,
        "primarias": primarias,
        "medias": medias,
        "baixas": baixas,
        "razao_primaria": round(100 * primarias / total) if total else 0,
        "citacoes_longas": citacoes_longas,
        "arquivos": len(re.findall(r"^>>> ", texto, re.MULTILINE)) or 1,
        "contradicoes": len(re.findall(r"^[-*]\s+.*(?:contradi|tensão|tensao)", texto, re.IGNORECASE | re.MULTILINE)),
        "inferencias": len(re.findall(r"^[-*]\s+.*(?:infer|hipótese|hipotese)", texto, re.IGNORECASE | re.MULTILINE)),
        "lacunas": len(re.findall(r"^[-*]\s+.*(?:lacuna|falta|não há evidência|nao ha evidencia)", texto, re.IGNORECASE | re.MULTILINE)),
        "trilhas": len(set(re.findall(r"^(\d{2})[-_]", texto, re.MULTILINE))),
    }


def qualidade(*, perfil_texto: str, referencia: str = "budget-friendly", modo: str = "full") -> dict[str, Any]:
    """Aplica o gate do projeto original ao texto do perfil."""
    modo = _modo(modo)
    texto = _corpo(perfil_texto)
    referencia = (referencia or "budget-friendly").strip().lower()
    if referencia not in {"budget-friendly", "budget-unfriendly"}:
        raise DistilarError("Referência inválida: use budget-friendly ou budget-unfriendly.")
    estrito = referencia == "budget-unfriendly"
    metricas = _metricas_pesquisa(texto)
    bullets = len(re.findall(r"^\s*[-*]\s+", texto, re.MULTILINE))

    checagens = {
        "modelos_mentais": bullets >= 3 and bool(re.search(r"mental model|modelo mental|modelos mentais", texto, re.IGNORECASE)),
        "limites": bool(re.search(r"limitations|limite|fronteira|boundary", texto, re.IGNORECASE)),
        "dna_de_expressao": bool(re.search(r"expression DNA|dna de express|ritmo|metáfora|metafora|voz", texto, re.IGNORECASE)),
        "fronteiras_honestas": bool(re.search(r"não sabe|nao sabe|does not know|não afirma|nao afirma", texto, re.IGNORECASE)),
        "tensao_interna": bool(re.search(r"contradi|tensão|tensao|tension", texto, re.IGNORECASE)),
        "lastro_de_fonte": metricas["urls"] >= (4 if estrito else 2),
        "seguranca_de_direito": "```" not in texto and metricas["citacoes_longas"] == 0,
        "genealogia_intelectual": (bool(re.search(r"genealogia|influenci|influenced by", texto, re.IGNORECASE)) if estrito else True),
        "protocolo_de_agente": (bool(re.search(r"protocolo|passo 1|step 1|dimensões de pesquisa", texto, re.IGNORECASE)) if estrito else True),
        "hierarquia_de_fonte": ((metricas["razao_primaria"] >= 50 or metricas["primarias"] >= 3) if estrito else True),
        "cadeia_de_revisao": (
            bool(re.search(r"revisão|revisao|auditoria", texto, re.IGNORECASE))
            and bool(re.search(r"aprovad|passou", texto, re.IGNORECASE))
            if estrito
            else True
        ),
        "profundidade_de_validacao": (
            (metricas["contradicoes"] >= 2 and metricas["inferencias"] >= 2) if estrito else True
        ),
        "profundidade_de_pesquisa": (
            (metricas["arquivos"] >= 6 and metricas["urls"] >= 8 and metricas["blocos_de_fonte"] >= 6 and metricas["trilhas"] >= 6)
            if estrito
            else True
        ),
    }
    reprovadas = [nome for nome, ok in checagens.items() if not ok]
    obrigatorias = [nome for nome in reprovadas if nome in CHECAGENS_OBRIGATORIAS or (estrito and nome in CHECAGENS_ESTRITAS)]

    findings: list[dict[str, Any]] = []
    for nome in reprovadas:
        grupo = "must" if nome in obrigatorias else "nice"
        findings.append(
            finding(
                grupo,
                "qualidade",
                f"Checagem reprovada: {nome.replace('_', ' ')}",
                f"perfil ({referencia})",
                "A marca esperada não aparece no texto, ou aparece abaixo do mínimo.",
                "O gate existe para impedir perfil genérico, sem fonte e com citação longa.",
                "Corrija a seção correspondente antes de empacotar o perfil.",
                "O perfil passa a parecer o que não é: um retrato com prova.",
            )
        )
    if metricas["citacoes_longas"]:
        findings.append(
            finding(
                "must",
                "direito",
                "Trecho com cara de transcrição",
                f"{metricas['citacoes_longas']} linha(s)",
                "Linhas com marca de tempo ou citação longa em bloco foram encontradas.",
                "Reproduzir transcrição inteira é problema de direito autoral, além de ruído.",
                "Resuma e cite a linha de origem, sem copiar o bloco.",
                "O perfil se torna um recorte não autorizado da fonte.",
            )
        )
    findings, counts, veredito, questions = finalize(
        findings, modo, ["Quantas fontes independentes sustentam o texto?", "Quem revisou antes de empacotar?"]
    )
    rows = [
        {"checagem": nome, "estado": "passa" if ok else "reprova", "obrigatoria": nome in CHECAGENS_OBRIGATORIAS}
        for nome, ok in checagens.items()
    ]
    resultado = common(
        analysis="qualidade",
        mode=modo,
        title="Gate de qualidade do perfil",
        summary=[
            f"Referência **{referencia}**: {'estrita' if estrito else 'padrão'}.",
            f"{len(checagens) - len(reprovadas)} de {len(checagens)} checagens passam.",
            f"{len(obrigatorias)} reprovação(ões) obrigatória(s).",
        ],
        findings=findings,
        counts=counts,
        verdict=veredito,
        questions=questions,
        rows=rows,
        metrics={
            "checagens": len(checagens),
            "passam": len(checagens) - len(reprovadas),
            "reprovam": len(reprovadas),
            "obrigatorias": len(obrigatorias),
            "bullets": bullets,
            "urls": metricas["urls"],
            "citacoesLongas": metricas["citacoes_longas"],
        },
        limitations=[
            "É busca por marca textual, não leitura crítica do perfil.",
            "Passar no gate não prova que o perfil é fiel: prova que ele tem as seções exigidas.",
            "A referência estrita foi desenhada para figura pública, não para colega.",
        ],
        extra_sections=[
            "",
            "## Métricas de pesquisa",
            "",
            *[f"- {chave}: {valor}" for chave, valor in metricas.items()],
        ],
    )
    resultado["aprovado"] = not obrigatorias and not metricas["citacoes_longas"]
    resultado["reprovadas"] = reprovadas
    return resultado


# ---------------------------------------------------------------------------
# 5. Lastro: afirmação contra fonte
# ---------------------------------------------------------------------------


def lastro(*, perfil_texto: str, corpus: str, modo: str = "full") -> dict[str, Any]:
    """Confere cada afirmação do perfil contra o material: com lastro ou sem."""
    modo = _modo(modo)
    texto = _corpo(perfil_texto)
    material = _corpo(corpus, limite=MAX_CORPUS)
    dados = _analisar_corpus(material)

    linhas_corpus = [
        {"texto": item["texto"], "fonte": item["fonte"], "linha": item["linha"], "tokens": _tokens(item["texto"])}
        for item in dados["mensagens"]
    ]

    afirmacoes = [
        {"linha": numero, "texto": linha.strip()[2:].strip()}
        for numero, linha in enumerate(texto.splitlines(), start=1)
        if re.match(r"^\s*[-*]\s+\S", linha) and len(linha.strip()) > 24
    ]

    rows: list[dict[str, Any]] = []
    sem_lastro: list[str] = []
    for afirmacao in afirmacoes:
        tokens = _tokens(afirmacao["texto"])
        melhor, nota = None, 0.0
        for candidato in linhas_corpus:
            valor = _jaccard(tokens, candidato["tokens"])
            if valor > nota:
                melhor, nota = candidato, valor
        tem = nota >= 0.18
        if not tem:
            sem_lastro.append(afirmacao["texto"][:120])
        rows.append(
            {
                "afirmacao": afirmacao["texto"][:120],
                "lastro": "sim" if tem else "não",
                "similaridade": round(nota, 2),
                "fonte": f"{melhor['fonte']}:{melhor['linha']}" if (melhor and tem) else "—",
                "evidencia": melhor["texto"][:110] if (melhor and tem) else "—",
            }
        )

    citacoes = re.findall(r'["“](.{20,})["”]', texto)
    longas = [citacao for citacao in citacoes if len(citacao) > CITACAO_MAXIMA]
    fora_do_corpus = [
        citacao
        for citacao in citacoes
        if citacao.strip() and citacao.strip() not in material
    ]

    findings: list[dict[str, Any]] = []
    if sem_lastro:
        findings.append(
            finding(
                "should",
                "lastro",
                "Afirmação sem linha de apoio",
                f"{len(sem_lastro)} de {len(afirmacoes)}",
                f"Primeira: `{sem_lastro[0]}`.",
                "Afirmação sem origem é opinião de quem escreveu o perfil, não observação.",
                "Ache a linha no material, reescreva como hipótese ou remova a afirmação.",
                "O perfil atribui à pessoa algo que ela nunca disse.",
            )
        )
    if longas:
        findings.append(
            finding(
                "must",
                "direito",
                "Citação acima do limite",
                f"{len(longas)} trecho(s) com mais de {CITACAO_MAXIMA} caracteres",
                "Trecho longo copiado do material.",
                "Reproduzir bloco inteiro é problema de direito autoral e esconde o padrão.",
                "Resuma o trecho e cite `fonte:linha`.",
                "O perfil deixa de ser destilação e vira cópia.",
            )
        )
    if fora_do_corpus:
        findings.append(
            finding(
                "should",
                "lastro",
                "Citação que não está no material",
                f"{len(fora_do_corpus)} trecho(s)",
                f"Primeira: `{fora_do_corpus[0][:80]}`.",
                "Aspas indicam fala literal; se não está na fonte, não é literal.",
                "Remova as aspas ou traga a fonte correta.",
                "Você põe na boca de alguém uma frase inventada.",
            )
        )
    if not afirmacoes:
        findings.append(
            finding(
                "nice",
                "lastro",
                "Nenhuma afirmação para conferir",
                "perfil",
                "O texto não tem bullets com mais de 24 caracteres.",
                "Sem afirmação não há o que verificar — e provavelmente não há perfil.",
                "Escreva o perfil em bullets curtos, um padrão por linha.",
                "O gate de lastro não tem efeito.",
            )
        )
    findings, counts, veredito, questions = finalize(
        findings, modo, ["Cada afirmação tem uma linha de origem?", "As aspas são fala literal mesmo?"]
    )
    resultado = common(
        analysis="lastro",
        mode=modo,
        title="Lastro do perfil",
        summary=[
            f"{len(afirmacoes)} afirmação(ões) conferida(s) contra {len(linhas_corpus)} linha(s) do material.",
            f"{len(afirmacoes) - len(sem_lastro)} com lastro, {len(sem_lastro)} sem.",
        ],
        findings=findings,
        counts=counts,
        verdict=veredito,
        questions=questions,
        rows=rows[:MAX_ROWS],
        metrics={
            "afirmacoes": len(afirmacoes),
            "comLastro": len(afirmacoes) - len(sem_lastro),
            "semLastro": len(sem_lastro),
            "citacoes": len(citacoes),
            "citacoesLongas": len(longas),
            "citacoesFora": len(fora_do_corpus),
        },
        limitations=[
            "Similaridade de palavras, não de sentido: frase parafraseada pode ficar sem lastro.",
            "Uma linha parecida não prova que a afirmação está correta.",
            "O limiar de 0,18 foi calibrado à mão; ajuste ao seu material.",
        ],
    )
    resultado["semLastro"] = sem_lastro
    return resultado


# ---------------------------------------------------------------------------
# 6. Correção
# ---------------------------------------------------------------------------


MARCADORES_CORRECAO = {
    "fato": ("na verdade", "não foi", "nao foi", "data errada", "nunca aconteceu", "errado o nome", "ele não disse", "ela não disse"),
    "voz": ("não fala assim", "nao fala assim", "não usaria essa palavra", "nao usaria essa palavra", "tom errado", "soa artificial"),
    "julgamento": ("não faria", "nao faria", "não decidiria", "nao decidiria", "não pensa assim", "nao pensa assim"),
    "limite": ("não sabe", "nao sabe", "não é especialista", "nao e especialista", "fora da área", "fora da area"),
}


def correcao(*, correcao: str, secao: str = "", evidencia: str = "", modo: str = "full") -> dict[str, Any]:
    """Classifica a correção e diz o que ela muda no perfil — com ou sem lastro."""
    modo = _modo(modo)
    texto = (correcao or "").strip()
    if len(texto) < 10:
        raise DistilarError("Descreva a correção em pelo menos 10 caracteres.")
    baixo = texto.lower()
    tipo = "indefinido"
    for candidato, marcadores in MARCADORES_CORRECAO.items():
        if any(marcador in baixo for marcador in marcadores):
            tipo = candidato
            break
    if tipo == "indefinido":
        if any(palavra in baixo for palavra in ("errado", "corrige", "corrija", "ajusta", "não é", "nao e")):
            tipo = "fato"
        else:
            tipo = "julgamento"

    secoes_validas = {dimensao for dados in FAMILIAS.values() for dimensao in dados["dimensoes"]} | {"retrato", "limites_honestos", "fontes"}
    alvo = (secao or "").strip().lower().replace(" ", "_")
    if alvo and alvo not in secoes_validas:
        raise DistilarError(
            f"Seção desconhecida: `{secao}`. Use uma dimensão, `retrato`, `limites_honestos` ou `fontes`."
        )

    tem_lastro = len((evidencia or "").strip()) >= 15
    manifesto = {
        "tipo": tipo,
        "secao": alvo or "a definir",
        "correcao": texto[:400],
        "evidencia": (evidencia or "").strip()[:400],
        "com_lastro": tem_lastro,
        "registrado_em": datetime.now(timezone.utc).isoformat(),
    }

    efeito = {
        "fato": "Reescreve a afirmação e a citação de origem; se não houver origem, a afirmação sai.",
        "voz": "Ajusta vocabulário, ritmo e exemplos na seção de voz, sem mudar julgamento.",
        "julgamento": "Remove a regra atribuída e acrescenta o caso observado que a contradiz.",
        "limite": "Acrescenta o tema em 'o que não sabe' e remove promessa sobre ele.",
        "indefinido": "Sem classificação: descreva melhor o que está errado antes de mexer no perfil.",
    }[tipo]

    findings: list[dict[str, Any]] = []
    if not tem_lastro:
        findings.append(
            finding(
                "must",
                "correcao",
                "Correção sem evidência",
                alvo or "perfil",
                "A correção não trouxe linha, arquivo ou citação de origem.",
                "Trocar uma afirmação sem lastro por outra sem lastro não melhora o perfil — só troca o erro.",
                "Cole a linha do material que sustenta a correção, ou marque o ponto como 'não há evidência'.",
                "O perfil passa a registrar a sua memória como se fosse observação.",
            )
        )
    if not alvo:
        findings.append(
            finding(
                "should",
                "correcao",
                "Seção não informada",
                "perfil",
                "A correção não diz qual seção muda.",
                "Sem alvo, a correção vira reescrita geral e perde a rastreabilidade.",
                "Informe a dimensão afetada, por exemplo `voz` ou `padroes_de_decisao`.",
                "Você não consegue revisar o que mudou.",
            )
        )
    findings, counts, veredito, questions = finalize(
        findings, modo, ["A evidência nova contradiz ou complementa o que já estava?", "Outra seção depende desta afirmação?"]
    )
    resultado = common(
        analysis="correcao",
        mode=modo,
        title="Correção do perfil",
        summary=[
            f"Tipo **{tipo}**, seção **{alvo or 'a definir'}**, lastro {'presente' if tem_lastro else 'ausente'}.",
            efeito,
        ],
        findings=findings,
        counts=counts,
        verdict=veredito,
        questions=questions,
        rows=[
            {"campo": "tipo", "valor": tipo},
            {"campo": "seção", "valor": alvo or "a definir"},
            {"campo": "efeito", "valor": efeito},
            {"campo": "com lastro", "valor": "sim" if tem_lastro else "não"},
            {"campo": "evidência", "valor": (evidencia or "(nenhuma)")[:200]},
        ],
        metrics={"tipo": tipo, "comLastro": tem_lastro, "secaoInformada": bool(alvo)},
        limitations=[
            "A classificação é por marcador de texto; corrija a seção se ela errar.",
            "Correção com lastro ainda precisa de revisão humana: a evidência pode estar fora de contexto.",
            "A camada não reescreve o perfil nem grava o livro de correções.",
        ],
    )
    resultado["tipo"] = tipo
    resultado["registro"] = manifesto
    return resultado


# ---------------------------------------------------------------------------
# 7. Hospedeiros
# ---------------------------------------------------------------------------


def hospedeiros(*, host: str = "", raiz: str = "", modo: str = "full") -> dict[str, Any]:
    """Mostra onde o perfil gerado é instalado em cada agente compatível."""
    modo = _modo(modo)
    escolhido = (host or "").strip().lower()
    if escolhido and escolhido not in HOSPEDEIROS:
        raise DistilarError(f"Hospedeiro desconhecido: `{host}`. Use {', '.join(HOSPEDEIROS)}.")
    nomes = [escolhido] if escolhido else list(HOSPEDEIROS)
    casa = Path((raiz or "").strip() or "~").expanduser()

    rows: list[dict[str, Any]] = []
    for nome in nomes:
        dados = HOSPEDEIROS[nome]
        base = casa
        if dados.get("home_env"):
            import os

            valor = os.environ.get(dados["home_env"], "").strip()
            if valor:
                base = Path(valor).expanduser()
        destino = base.joinpath(*dados["skills"])
        gerado = base.joinpath(*dados.get("gerado", dados["skills"]))
        rows.append(
            {
                "host": nome,
                "nome": dados["nome"],
                "skills": str(destino),
                "gerado": str(gerado),
                "invocacao": dados["invocacao"],
                "home_env": dados.get("home_env", "—"),
            }
        )

    findings: list[dict[str, Any]] = []
    if str(casa) == "/root":
        findings.append(
            finding(
                "nice",
                "hospedeiro",
                "Raiz em /root",
                str(casa),
                "A raiz resolvida é a pasta do superusuário.",
                "Perfil instalado em /root fica inacessível para o seu usuário.",
                "Informe a raiz do usuário (`raiz` = /home/você ou vazio para usar ~).",
                "Você instala no lugar errado.",
            )
        )
    findings, counts, veredito, questions = finalize(findings, modo, ["Qual agente você usa hoje?"])
    resultado = common(
        analysis="hospedeiros",
        mode=modo,
        title="Hospedeiros compatíveis",
        summary=[
            f"{len(rows)} hospedeiro(s) com caminho de skill nativo.",
            "A tabela é do projeto original; nada é instalado por esta skill.",
        ],
        findings=findings,
        counts=counts,
        verdict=veredito,
        questions=questions,
        rows=rows,
        metrics={"hospedeiros": len(rows), "com_env": len([item for item in nomes if HOSPEDEIROS[item].get("home_env")])},
        limitations=[
            "Os caminhos vêm do hosts.json do projeto original e podem mudar.",
            "A skill não copia arquivo: instalar continua sendo um passo seu.",
            "Grok Bot não importa SKILL.md local — o README do original diz isso.",
        ],
    )
    return resultado


# ---------------------------------------------------------------------------
# 8. Catálogo
# ---------------------------------------------------------------------------


def catalogo() -> dict[str, Any]:
    """Publica famílias, dimensões, checagens, hospedeiros e o que a camada recusa."""
    return {
        "executed": False,
        "readOnly": True,
        "versao": VERSAO,
        "origem": {
            "projeto": "titanwings/distilly",
            "licenca": "MIT",
            "url": "https://github.com/titanwings/distilly",
            "o_que_foi_portado": (
                "Famílias e dimensões, gate de qualidade com referência estrita e padrão, "
                "hierarquia de fonte por peso, tabela de oito hospedeiros, slug portátil e o fluxo de correção."
            ),
        },
        "principio": (
            "Perfil de pessoa é afirmação sobre alguém: cada linha precisa de origem, e o que não tem "
            "fica declarado como ausência em vez de ser preenchido."
        ),
        "familias": [
            {"familia": nome, "rotulo": dados["rotulo"], "dominio": dados["dominio"], "raiz": dados["raiz"], "dimensoes": len(dados["dimensoes"])}
            for nome, dados in FAMILIAS.items()
        ],
        "dimensoes": [
            {"familia": nome, "dimensao": dimensao}
            for nome, dados in FAMILIAS.items()
            for dimensao in dados["dimensoes"]
        ],
        "checagens": [{"nome": nome, "grupo": "obrigatória"} for nome in CHECAGENS_OBRIGATORIAS]
        + [{"nome": nome, "grupo": "estrita"} for nome in CHECAGENS_ESTRITAS],
        "hospedeiros": [
            {"host": nome, "nome": dados["nome"], "skills": "/".join(dados["skills"]), "invocacao": dados["invocacao"]}
            for nome, dados in HOSPEDEIROS.items()
        ],
        "limites": {
            "corpus": MAX_CORPUS,
            "texto": MAX_TEXTO,
            "slug": MAX_SLUG,
            "citacao": CITACAO_MAXIMA,
            "linhas": MAX_ROWS,
        },
        "nao_faz": [
            "Não escreve a persona: mede o material e confere o texto que você traz.",
            "Não chama modelo de linguagem: nenhuma inferência semântica acontece aqui.",
            "Não baixa fonte: o material é colado por você.",
            "Não instala o perfil no agente: a tabela de hospedeiros é referência.",
            "Não copia transcrição nem bloco longo: citação acima de 240 caracteres é bloqueio.",
            "Não afirma parentesco, doença ou opinião íntima sem linha de origem.",
        ],
    }
