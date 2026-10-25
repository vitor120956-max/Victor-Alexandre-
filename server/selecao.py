"""Seleção de skills em catálogo grande: briefing, busca, stack, plano e catálogo.

O upstream é o AAS Core do `sickn33/agentic-awesome-skills` (MIT, 48 mil
estrelas, 2.743 skills em 114 categorias). Lá o `search_skills` devolve os
matches em ordem estável e **sem pontuação**, e o `compose_stack` valida os ids
escolhidos sem opinar — a decisão fica com o agente. Esta camada faz o oposto do
que o Core recusa fazer, de forma determinística: pontua, ranqueia, cobre as dez
dimensões de capacidade e monta o plano, sempre explicando a conta.

Nada é baixado, executado ou chamado: o catálogo é o JSON que você cola.
"""
from __future__ import annotations

import json
import math
import re
import unicodedata
from collections import Counter
from typing import Any

from .review import common, finalize, finding

VERSAO = "0.37.6"

MODOS = ("lite", "full", "ultra")

MAX_TEXTO = 1_800_000
MAX_ENTRADAS = 3_000
MAX_SKILLS = 128
MAX_RESULTADOS = 50
MIN_RESULTADOS = 1

LIMIAR_SCORE = 1.0
EMPATE = 0.05
SOBREPOSICAO = 0.20
COBERTURA_MINIMA = 60

K1 = 1.2
B = 0.75

PESO_NOME = 3
PESO_CATEGORIA = 2
PESO_DESCRICAO = 1

PONTOS_RISCO = {"safe": 0, "none": 1, "unknown": 1, "offensive": 2, "critical": 3}
RISCO_ORDEM = ("safe", "none", "unknown", "offensive", "critical")
ALVOS = ("claude", "codex")

DIMENSOES: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    (
        "arquitetura",
        "Arquitetura e runtime",
        ("arquitetura", "architecture", "runtime", "monolito", "monolith", "microsservi", "microservic", "serverless", "hexagonal", "ddd", "event-driven", "evento", "eventos"),
    ),
    (
        "linguagens",
        "Linguagens e frameworks",
        ("python", "typescript", "javascript", "react", "vue", "angular", "next.js", "nextjs", "django", "fastapi", "flask", "node", "rust", "golang", "java", "spring", "flutter", "swift", "kotlin", "php", "rails", "expo", "tailwind"),
    ),
    (
        "dominio",
        "Comportamento de domínio",
        ("dominio", "domain", "regra de negocio", "regras de negocio", "pedido", "checkout", "pagamento", "faturamento", "estoque", "crm", "erp", "reserva", "agendamento", "assinatura", "carrinho"),
    ),
    (
        "dados",
        "Dados e armazenamento",
        ("banco de dados", "database", "postgres", "mysql", "sqlite", "mongo", "redis", "etl", "migracao", "schema", "data lake", "warehouse", "supabase", "firebase", "prisma", "orm", "storage"),
    ),
    (
        "integracoes",
        "Integrações externas",
        ("integracao", "integrations", "api", "webhook", "oauth", "stripe", "whatsapp", "smtp", "graphql", "rest", "sdk", "terceiro", "third-party", "zapier", "n8n"),
    ),
    (
        "qualidade",
        "Testes e qualidade",
        ("teste", "testes", "testing", "tdd", "cobertura", "coverage", "lint", "pipeline", "ci", "qa", "bug", "debug", "regressao", "e2e"),
    ),
    (
        "seguranca",
        "Segurança e privacidade",
        ("seguranca", "security", "lgpd", "gdpr", "hipaa", "soc2", "pci", "criptografia", "auth", "autenticacao", "autorizacao", "secreto", "segredos", "vulnerabilidade", "pentest", "owasp"),
    ),
    (
        "experiencia",
        "Experiência e acessibilidade",
        ("experiencia", "usabilidade", "ux", "ui", "design", "acessibilidade", "accessibility", "a11y", "wcag", "prototipo", "figma", "layout", "responsivo"),
    ),
    (
        "operacao",
        "Deploy e operação",
        ("deploy", "kubernetes", "docker", "terraform", "observabilidade", "observability", "monitoramento", "sre", "infra", "aws", "gcp", "azure", "ci/cd", "vercel", "railway", "heroku"),
    ),
    (
        "manutencao",
        "Manutenção e evolução",
        ("refator", "refactor", "divida tecnica", "legado", "documentacao", "docs", "manutencao", "deprecat", "code review", "revisao de codigo", "onboarding", "changelog"),
    ),
)

CATEGORIA_DIMENSAO: tuple[tuple[str, str], ...] = (
    ("api-integration", "integracoes"),
    ("integration", "integracoes"),
    ("devops", "operacao"),
    ("cloud", "operacao"),
    ("infrastructure", "operacao"),
    ("deployment", "operacao"),
    ("web-development", "linguagens"),
    ("frontend", "linguagens"),
    ("backend", "linguagens"),
    ("mobile", "linguagens"),
    ("language", "linguagens"),
    ("security", "seguranca"),
    ("testing", "qualidade"),
    ("quality", "qualidade"),
    ("data", "dados"),
    ("database", "dados"),
    ("design", "experiencia"),
    ("content", "experiencia"),
    ("ux", "experiencia"),
    ("accessibility", "experiencia"),
    ("architecture", "arquitetura"),
    ("maintenance", "manutencao"),
    ("documentation", "manutencao"),
    ("productivity", "manutencao"),
    ("workflow", "manutencao"),
    ("business", "dominio"),
    ("marketing", "dominio"),
    ("product", "dominio"),
    ("finance", "dominio"),
)

ENTREGAVEIS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("api", ("api", "endpoint", "rest", "graphql", "webhook")),
    ("app", ("app", "aplicativo", "mobile", "android", "ios")),
    ("site", ("site", "landing", "pagina", "página", "web")),
    ("painel", ("painel", "dashboard", "admin", "backoffice")),
    ("relatorio", ("relatorio", "report", "analise", "diagnostico")),
    ("deck", ("deck", "apresentacao", "slides", "pitch")),
    ("planilha", ("planilha", "spreadsheet", "csv", "xlsx")),
    ("documento", ("documento", "documentation", "pdf", "docx", "contrato", "politica")),
    ("bot", ("bot", "chatbot", "agente", "assistant")),
    ("cli", ("cli", "terminal", "script", "automacao")),
    ("plugin", ("plugin", "extensao", "mcp", "skill")),
    ("dados", ("dataset", "pipeline", "etl", "modelo", "model")),
)

RESTRICOES: tuple[tuple[str, str, str], ...] = (
    ("prazo", r"\b(prazo|deadline|ate\s+\d|em\s+\d+\s*(dia|dias|semana|semanas|mes|meses)|q[1-4]|urgente)\b"),
    ("orcamento", r"\b(orcamento|budget|r\$\s*\d|us\$\s*\d|\d+\s*(mil|k)\s*(reais|brl|usd|dolares)|custo maximo)\b"),
    ("equipe", r"\b(equipe|time|squad|sozinho|solo|um dev|dois devs|dupla)\b"),
    ("compliance", r"\b(lgpd|gdpr|hipaa|soc\s*2|pci|iso\s*27001|auditoria|compliance)\b"),
    ("escala", r"\b(escala|throughput|rps|requisicoes por segundo|milhoes de|milhao de)\b"),
)

CRITERIOS = (
    "sucesso", "aceite", "pronto", "criterio", "metric", "metrica", "kpi", "meta",
    "reduzir", "aumentar", "converter", "conversao", "latencia", "sla", "nps",
    "receita", "churn", "erro", "cobertura",
)

PUBLICOS = (
    "usuario", "usuarios", "cliente", "clientes", "time", "equipe", "publico",
    "persona", "desenvolvedor", "dev", "operador", "gestor", "diretoria",
    "c-level", "colaborador", "aluno", "paciente",
)

STOPWORDS = frozenset(
    """a o os as um uma uns umas de do da dos das em no na nos nas num numa para por com sem sob sobre que se
    e ou mas como quando onde qual quais quem cujo cuja ja nao sim muito pouco mais menos entre ate apos
    ser sou e sao foi era sera seriam tem tinha ter tera teriam ha havia isso isto aquilo este esta esse essa
    seu sua seus suas meu minha nosso nossa dele dela deles delas eu tu ele ela nos vos eles elas voce voces
    the a an and or of to in on at for with without from by as is are was were be been being this that these
    those it its we our you your they their he she his her them us not no yes more less very can could should
    would will shall may might must do does did done have has had having use using used when how what why which
    who whom whose if then than so such also just only about into over under again further once here there all
    any both each few other some own same too s t don now el la los las un una de del en y o se por para con sin
    que como cuando donde es son fue ser muy mas menos entre
    """.split()
)

RE_PALAVRA = re.compile(r"[a-z0-9][a-z0-9+#./-]*")
RE_ID = re.compile(r"^[a-z0-9][a-z0-9._-]*$")
RE_KW = re.compile(r"\s*\|\s*")


def _modo(valor: str) -> str:
    if valor not in MODOS:
        raise SelecaoError(f"Modo inválido: {valor}. Use {', '.join(MODOS)}.")
    return valor


class SelecaoError(ValueError):
    """Entrada recusada antes do cálculo."""


def _normalizar(texto: str) -> str:
    decomposto = unicodedata.normalize("NFD", texto.lower())
    return "".join(ch for ch in decomposto if unicodedata.category(ch) != "Mn")


def _singular(palavra: str) -> str:
    if len(palavra) > 4 and palavra.endswith("es"):
        return palavra[:-2]
    if len(palavra) > 3 and palavra.endswith("s"):
        return palavra[:-1]
    return palavra


def _tokens(texto: str) -> list[str]:
    """Tokeniza e indexa plural e singular juntos, para casar as duas formas."""
    saida: list[str] = []
    for bruto in RE_PALAVRA.findall(_normalizar(texto)):
        palavra = bruto.strip(".-/")
        if len(palavra) < 2 or palavra in STOPWORDS:
            continue
        saida.append(palavra)
        singular = _singular(palavra)
        if singular != palavra:
            saida.append(singular)
    return saida


def _termos(texto: str) -> list[str]:
    """Termos únicos da consulta, sem as variantes de plural."""
    vistos: list[str] = []
    for bruto in RE_PALAVRA.findall(_normalizar(texto)):
        palavra = bruto.strip(".-/")
        if len(palavra) < 2 or palavra in STOPWORDS:
            continue
        if palavra not in vistos:
            vistos.append(palavra)
    return vistos


def _dimensoes(texto: str) -> dict[str, list[str]]:
    """Dimensões de capacidade tocadas pelo texto, com as palavras que casaram."""
    alvo = _normalizar(texto)
    achados: dict[str, list[str]] = {}
    for chave, _rotulo, _palavras in DIMENSOES:
        casadas = [palavra for palavra, padrao in _PADROES_DIMENSAO[chave] if padrao.search(alvo)]
        if casadas:
            achados[chave] = casadas
    return achados


_PADROES_DIMENSAO = {
    chave: [(palavra, re.compile(rf"(?<![a-z0-9]){re.escape(palavra)}")) for palavra in palavras]
    for chave, _rotulo, palavras in DIMENSOES
}


def _rotulo_dimensao(chave: str) -> str:
    for nome, rotulo, _palavras in DIMENSOES:
        if nome == chave:
            return rotulo
    return chave


def _dimensao_da_categoria(categoria: str) -> str:
    alvo = _normalizar(categoria)
    for trecho, dimensao in CATEGORIA_DIMENSAO:
        if trecho in alvo:
            return dimensao
    return ""


def _principal(entrada: dict[str, Any]) -> str:
    """Dimensão da fase: a da categoria quando ela casa, senão a de mais palavras no texto."""
    dimensoes = _dimensoes(_campo(entrada))
    da_categoria = _dimensao_da_categoria(entrada["categoria"])
    if da_categoria:
        return da_categoria
    if not dimensoes:
        return ""
    ordem = {chave: indice for indice, (chave, _rotulo, _palavras) in enumerate(DIMENSOES)}
    return min(dimensoes, key=lambda chave: (-len(dimensoes[chave]), ordem[chave]))


def _entregaveis(texto: str) -> dict[str, list[str]]:
    alvo = _normalizar(texto)
    achados: dict[str, list[str]] = {}
    for nome, palavras in ENTREGAVEIS:
        casadas = [palavra for palavra in palavras if re.search(rf"(?<![a-z0-9]){re.escape(palavra)}", alvo)]
        if casadas:
            achados[nome] = casadas
    return achados


def _restricoes(texto: str) -> dict[str, str]:
    alvo = _normalizar(texto)
    achados: dict[str, str] = {}
    for nome, padrao in RESTRICOES:
        casado = re.search(padrao, alvo)
        if casado:
            achados[nome] = casado.group(0)
    return achados


def _tem(texto: str, palavras: tuple[str, ...]) -> list[str]:
    alvo = _normalizar(texto)
    return [palavra for palavra in palavras if re.search(rf"(?<![a-z0-9]){re.escape(palavra)}", alvo)]


def _palavras(texto: str) -> int:
    return len(texto.split())


def _linha_de(texto: str, posicao: int) -> int:
    return texto.count("\n", 0, posicao) + 1


def _trecho(texto: str, inicio: int, fim: int, largura: int = 90) -> str:
    comeco = max(0, inicio - 20)
    recorte = " ".join(texto[comeco:inicio + fim + largura].split())
    if len(recorte) > largura * 2:
        recorte = recorte[: largura * 2].rstrip() + "…"
    return recorte


def _percentual(parte: int, total: int) -> float:
    if total <= 0:
        return 0.0
    return round(100.0 * parte / total, 1)


# --- catálogo ---------------------------------------------------------------


def _entrada_json(item: dict[str, Any]) -> dict[str, Any] | None:
    if not isinstance(item, dict):
        return None
    identificador = str(item.get("id") or item.get("name") or "").strip()
    if not identificador:
        return None
    plugin = item.get("plugin") if isinstance(item.get("plugin"), dict) else {}
    alvos = plugin.get("targets") if isinstance(plugin.get("targets"), dict) else {}
    setup = plugin.get("setup") if isinstance(plugin.get("setup"), dict) else {}
    return {
        "id": identificador,
        "nome": str(item.get("name") or identificador).strip(),
        "categoria": str(item.get("category") or "").strip(),
        "descricao": str(item.get("description") or "").strip(),
        "risco": str(item.get("risk") or "").strip().lower(),
        "fonte": str(item.get("source") or "").strip(),
        "alvos": [chave for chave, ativo in alvos.items() if ativo],
        "setup": str(setup.get("type") or "").strip(),
        "path": str(item.get("path") or "").strip(),
    }


def ler_catalogo(texto: str) -> tuple[list[dict[str, Any]], list[str]]:
    """Aceita a lista JSON do índice, um objeto com `skills` ou linhas `id | categoria [| risco] | descrição`."""
    if len(texto) > MAX_TEXTO:
        raise SelecaoError(f"O catálogo passa de {MAX_TEXTO:,} caracteres.")
    bruto = texto.strip()
    avisos: list[str] = []
    if not bruto:
        raise SelecaoError("Informe o catálogo em JSON ou em linhas `id | categoria [| risco] | descrição`.")
    itens: list[dict[str, Any]] = []
    if bruto[0] in "[{":
        try:
            dados = json.loads(bruto)
        except json.JSONDecodeError as exc:
            raise SelecaoError(f"Catálogo JSON inválido na linha {exc.lineno}: {exc.msg}.") from exc
        if isinstance(dados, dict):
            lista = dados.get("skills") or dados.get("items") or dados.get("catalog") or []
        else:
            lista = dados
        if not isinstance(lista, list):
            raise SelecaoError("O JSON precisa ser uma lista de skills ou um objeto com a chave `skills`.")
        for item in lista:
            entrada = _entrada_json(item) if isinstance(item, dict) else None
            if entrada is not None:
                itens.append(entrada)
        ignorados = len(lista) - len(itens)
        if ignorados:
            avisos.append(f"{ignorados} entrada(s) sem id foram ignoradas.")
    else:
        for numero, linha in enumerate(bruto.splitlines(), start=1):
            limpa = linha.strip()
            if not limpa or limpa.startswith("#"):
                continue
            partes = RE_KW.split(limpa)
            if len(partes) < 2:
                avisos.append(f"Linha {numero} sem categoria; ignorada.")
                continue
            identificador = partes[0].strip()
            if not identificador:
                avisos.append(f"Linha {numero} sem id; ignorada.")
                continue
            categoria = partes[1].strip()
            risco = "unknown"
            resto = partes[2:]
            if len(resto) >= 2 and _normalizar(resto[0].strip()) in RISCO_ORDEM:
                risco = _normalizar(resto[0].strip())
                resto = resto[1:]
            itens.append(
                {
                    "id": identificador,
                    "nome": identificador,
                    "categoria": categoria,
                    "descricao": " | ".join(resto).strip(),
                    "risco": risco,
                    "fonte": "",
                    "alvos": [],
                    "setup": "",
                    "path": "",
                }
            )
    if len(itens) > MAX_ENTRADAS:
        avisos.append(f"Catálogo truncado em {MAX_ENTRADAS:,} entradas; o restante não foi considerado.")
        itens = itens[:MAX_ENTRADAS]
    return itens, avisos


def _campo(entrada: dict[str, Any]) -> str:
    """Texto indexado com peso por campo: nome e categoria repetem os termos."""
    partes = [
        *([entrada["nome"]] * PESO_NOME),
        *([entrada["categoria"].replace("-", " ")] * PESO_CATEGORIA),
        *([entrada["descricao"]] * PESO_DESCRICAO),
    ]
    return " ".join(partes)


def _pontuar(
    entradas: list[dict[str, Any]],
    consulta: list[str],
    documentos: list[list[str]] | None = None,
) -> list[float]:
    """BM25 com k1 e b declarados; a mesma fórmula vale para qualquer catálogo."""
    documentos = documentos if documentos is not None else [_tokens(_campo(entrada)) for entrada in entradas]
    total = len(documentos)
    if not total or not consulta:
        return [0.0] * total
    frequencias = [Counter(documento) for documento in documentos]
    tamanhos = [len(documento) or 1 for documento in documentos]
    medio = sum(tamanhos) / total
    documento_frequencia: Counter[str] = Counter()
    for frequencia in frequencias:
        documento_frequencia.update(set(frequencia) & set(consulta))
    pontuacoes: list[float] = []
    for frequencia, tamanho in zip(frequencias, tamanhos):
        total_termo = 0.0
        for termo in consulta:
            tf = frequencia.get(termo, 0)
            if not tf:
                continue
            df = documento_frequencia.get(termo, 0)
            idf = math.log(1 + (total - df + 0.5) / (df + 0.5))
            total_termo += idf * (tf * (K1 + 1)) / (tf + K1 * (1 - B + B * tamanho / medio))
        pontuacoes.append(round(total_termo, 4))
    return pontuacoes


def _filtrar(
    entradas: list[dict[str, Any]],
    *,
    categoria: str = "",
    risco: str = "",
    alvo: str = "",
) -> list[dict[str, Any]]:
    alvo_categoria = _normalizar(categoria).strip()
    alvo_risco = _normalizar(risco).strip()
    alvo_nome = _normalizar(alvo).strip()
    filtradas = []
    for entrada in entradas:
        if alvo_categoria and alvo_categoria not in _normalizar(entrada["categoria"]):
            continue
        if alvo_risco and alvo_risco != _normalizar(entrada["risco"]):
            continue
        if alvo_nome and alvo_nome not in [_normalizar(item) for item in entrada["alvos"]]:
            continue
        filtradas.append(entrada)
    return filtradas


# --- 1. briefing ------------------------------------------------------------


def ler_brief(*, brief: str, modo: str = "full") -> dict[str, Any]:
    """Lê o pedido e devolve as dimensões, entregáveis e restrições que ele toca."""
    modo = _modo(modo)
    if len(brief) > MAX_TEXTO:
        raise SelecaoError(f"O briefing passa de {MAX_TEXTO:,} caracteres.")
    texto = brief.strip()
    if len(texto) < 40:
        raise SelecaoError("Descreva o trabalho em pelo menos 40 caracteres.")

    dimensoes = _dimensoes(texto)
    entregaveis = _entregaveis(texto)
    restricoes = _restricoes(texto)
    criterios = _tem(texto, CRITERIOS)
    publicos = _tem(texto, PUBLICOS)
    palavras = _palavras(texto)

    rows = [
        {
            "dimensao": _rotulo_dimensao(chave),
            "chave": chave,
            "evidencia": ", ".join(palavras_casadas[:4]),
            "termos": len(palavras_casadas),
        }
        for chave, palavras_casadas in sorted(
            dimensoes.items(), key=lambda item: (-len(item[1]), item[0])
        )
    ]

    achados: list[dict[str, Any]] = []
    if palavras < 20:
        achados.append(
            finding(
                "must",
                "brief-curto",
                "Briefing curto demais para escolher",
                f"{palavras} palavra(s)",
                "A seleção depende do que o pedido declara; com menos de 20 palavras não há o que casar.",
                "Sem contexto suficiente, a busca casa por acaso e a stack vira palpite.",
                "Descreva o resultado esperado, o público e uma restrição real.",
                "A escolha não é auditável: não dá para dizer por que cada skill entrou.",
            )
        )
    if not dimensoes and not entregaveis:
        achados.append(
            finding(
                "must",
                "brief-sem-objetivo",
                "Nenhuma dimensão ou entregável reconhecido",
                "briefing inteiro",
                "Nenhuma palavra do léxico de dez dimensões nem do léxico de entregáveis apareceu.",
                "Não há como cobrir capacidade que o texto não nomeia.",
                "Diga o que o sistema precisa fazer e o que precisa sair no final.",
                "Qualquer recomendação seria decorativa.",
            )
        )
    if not criterios:
        achados.append(
            finding(
                "should",
                "sem-criterio-de-sucesso",
                "Sem critério de sucesso",
                "briefing inteiro",
                "Não há meta, métrica, aceite ou número que diga quando o trabalho terminou.",
                "Sem critério, plano e stack não têm como ser verificados.",
                "Acrescente uma frase com o número que prova que ficou pronto.",
                "A entrega vira opinião: ninguém sabe se acertou.",
            )
        )
    if not restricoes:
        achados.append(
            finding(
                "should",
                "sem-restricao",
                "Sem restrição declarada",
                "briefing inteiro",
                "Prazo, orçamento, equipe, compliance e escala não aparecem no texto.",
                "A mesma stack serve para um protótipo de um dia e para um sistema regulado — a restrição é o que separa os dois.",
                "Declare prazo, orçamento, tamanho do time ou a norma que precisa cumprir.",
                "A recomendação ignora o custo real de executar.",
            )
        )
    if not entregaveis:
        achados.append(
            finding(
                "should",
                "sem-entregavel",
                "Sem entregável explícito",
                "briefing inteiro",
                "O texto não diz o que precisa existir no final: api, app, site, painel, relatório, deck.",
                "Sem artefato, a fase final do plano fica vazia.",
                "Nomeie o artefato: 'uma API', 'um painel', 'um relatório de 2 páginas'.",
                "O plano termina sem nada para mostrar.",
            )
        )
    if not publicos:
        achados.append(
            finding(
                "nice",
                "sem-publico",
                "Sem público declarado",
                "briefing inteiro",
                "Não há usuário, cliente, time ou persona nomeada.",
                "Público muda o peso de experiência, segurança e manutenção.",
                "Diga para quem o trabalho existe.",
                "A cobertura fica genérica e a fase de experiência vira palpite.",
            )
        )
    if len(dimensoes) > 6:
        achados.append(
            finding(
                "nice",
                "brief-difuso",
                f"Briefing toca {len(dimensoes)} dimensões",
                ", ".join(sorted(dimensoes)),
                "Um briefing que pede tudo não prioriza nada.",
                "Cobrir dez dimensões ao mesmo tempo dilui a stack e o plano.",
                "Eleja as duas ou três dimensões que decidem o resultado e trate o resto como apoio.",
                "A stack cresce até o limite e nenhuma fase fica clara.",
            )
        )
    if palavras > 400:
        achados.append(
            finding(
                "nice",
                "brief-longo",
                "Briefing longo",
                f"{palavras} palavra(s)",
                "Texto longo costuma misturar objetivo, histórico e desejo.",
                "A busca pontua o que mais repete, não o que mais importa.",
                "Separe objetivo, restrição e contexto em blocos curtos.",
                "Termos de contexto roubam o ranking dos termos do objetivo.",
            )
        )

    findings, counts, veredito, perguntas = finalize(achados, modo, _perguntas_brief(dimensoes, entregaveis, restricoes, criterios))
    metrics = {
        "palavras": palavras,
        "dimensoes": len(dimensoes),
        "entregaveis": len(entregaveis),
        "restricoes": len(restricoes),
        "tem_criterio": int(bool(criterios)),
        "tem_publico": int(bool(publicos)),
        "termos": len(_termos(texto)),
    }
    summary = [
        f"{palavras} palavra(s), {len(dimensoes)} dimensão(ões), {len(entregaveis)} entregável(is) e "
        f"{len(restricoes)} restrição(ões) reconhecida(s).",
        f"Dimensões: {', '.join(_rotulo_dimensao(chave) for chave in dimensoes) or 'nenhuma'}.",
    ]
    if entregaveis:
        summary.append(f"Entregáveis: {', '.join(sorted(entregaveis))}.")
    limitations = [
        "O léxico é fechado: nomes fora da lista não são reconhecidos, mesmo quando óbvios para quem lê.",
        "A contagem de dimensões mede menção, não importância — uma dimensão citada de passagem pesa igual a uma central.",
        "O briefing não é corrigido nem reescrito: só o que existe no texto é lido.",
        "Idioma suportado: português, inglês e espanhol nas palavras do léxico; o resto cai em `brief-sem-objetivo`.",
    ]
    return common(
        analysis="selecao.brief",
        mode=modo,
        title="Briefing de seleção",
        summary=summary,
        findings=findings,
        counts=counts,
        verdict=veredito,
        questions=perguntas,
        rows=rows,
        metrics=metrics,
        limitations=limitations,
    )


def _perguntas_brief(
    dimensoes: dict[str, list[str]],
    entregaveis: dict[str, list[str]],
    restricoes: dict[str, str],
    criterios: list[str],
) -> list[str]:
    perguntas = []
    if not dimensoes:
        perguntas.append("Quais áreas o sistema precisa cobrir: arquitetura, dados, integrações, segurança, operação?")
    if not entregaveis:
        perguntas.append("O que precisa existir no final: código rodando, documento, painel, apresentação?")
    if not restricoes:
        perguntas.append("Qual é o prazo e quem executa — uma pessoa, um time, um agente?")
    if not criterios:
        perguntas.append("Qual número prova que o trabalho ficou pronto?")
    perguntas.append("Qual dimensão pode falhar primeiro sem derrubar o resto?")
    return perguntas[:4]


# --- 2. busca ---------------------------------------------------------------


def recomendar(
    *,
    brief: str,
    catalogo: str,
    categoria: str = "",
    risco: str = "",
    alvo: str = "",
    limite: int = 8,
    modo: str = "full",
) -> dict[str, Any]:
    """Ranqueia o catálogo contra o briefing com BM25 e devolve o porquê de cada posição."""
    modo = _modo(modo)
    if limite < MIN_RESULTADOS or limite > MAX_RESULTADOS:
        raise SelecaoError(f"O limite precisa estar entre {MIN_RESULTADOS} e {MAX_RESULTADOS}.")
    if len(brief) < 20:
        raise SelecaoError("Descreva o pedido em pelo menos 20 caracteres para haver consulta.")
    entradas, avisos = ler_catalogo(catalogo)
    if not entradas:
        raise SelecaoError("O catálogo não tem nenhuma entrada válida.")

    consulta = _termos(brief)
    dimensoes_brief = _dimensoes(brief)
    filtradas = _filtrar(entradas, categoria=categoria, risco=risco, alvo=alvo)
    pontuacoes = _pontuar(filtradas, consulta)
    ordem = sorted(range(len(filtradas)), key=lambda indice: (-pontuacoes[indice], filtradas[indice]["id"]))
    top = [indice for indice in ordem if pontuacoes[indice] > 0][:limite]

    rows = []
    cobertas: set[str] = set()
    for posicao, indice in enumerate(top, start=1):
        entrada = filtradas[indice]
        texto = _campo(entrada)
        casadas = [termo for termo in consulta if termo in set(_tokens(texto))]
        dimensoes = set(_dimensoes(texto))
        cobertas.update(dimensoes & set(dimensoes_brief))
        rows.append(
            {
                "rank": posicao,
                "skill": entrada["id"],
                "categoria": entrada["categoria"] or "—",
                "risco": entrada["risco"] or "—",
                "score": pontuacoes[indice],
                "termos": ", ".join(casadas[:6]) or "—",
            }
        )

    achados: list[dict[str, Any]] = []
    melhor = pontuacoes[top[0]] if top else 0.0
    if len(consulta) < 2:
        achados.append(
            finding(
                "should",
                "termos-poucos",
                "Consulta com menos de dois termos úteis",
                f"{len(consulta)} termo(s)",
                "Depois de remover as palavras vazias, sobrou quase nada para casar.",
                "BM25 com um termo ordena por frequência, e frequência não é relevância.",
                "Acrescente o objeto e o verbo do trabalho: 'API de cobrança com Stripe'.",
                "O ranking obedece a uma palavra só.",
            )
        )
    if not top:
        if categoria or risco or alvo:
            achados.append(
                finding(
                    "must",
                    "filtro-sem-resultado",
                    "Nenhuma skill sobreviveu ao filtro",
                    f"categoria={categoria or '—'}, risco={risco or '—'}, alvo={alvo or '—'}",
                    "A consulta casaria, mas os filtros eliminaram todas as entradas.",
                    "Um filtro que zera o catálogo não informa nada sobre o trabalho.",
                    "Solte o filtro mais restritivo e refaça a busca.",
                    "A stack começa vazia e a lacuna é falsa.",
                )
            )
        else:
            achados.append(
                finding(
                    "must",
                    "nenhum-resultado",
                    "Nenhuma skill casou com a consulta",
                    f"{len(consulta)} termo(s) contra {len(filtradas)} entrada(s)",
                    "Nenhum documento do catálogo contém os termos da consulta.",
                    "Ou o briefing fala outra língua, ou o catálogo não cobre o assunto.",
                    "Reescreva com o vocabulário do catálogo — nome de tecnologia, domínio e artefato.",
                    "A seleção não tem candidato e qualquer escolha vira chute.",
                )
            )
    else:
        if melhor < LIMIAR_SCORE:
            achados.append(
                finding(
                    "should",
                    "score-baixo",
                    "Melhor score abaixo do limiar",
                    f"score {melhor:.2f} < {LIMIAR_SCORE:.2f}",
                    "A melhor entrada casou, mas com pouca evidência textual.",
                    "Score baixo em BM25 quer dizer casamento raso: uma palavra em comum e nada mais.",
                    "Use termos mais específicos ou aceite que o catálogo só cobre parte do pedido.",
                    "A primeira da lista parece escolha, mas é empate fraco.",
                )
            )
        if len(top) >= 2 and abs(pontuacoes[top[0]] - pontuacoes[top[1]]) <= EMPATE:
            achados.append(
                finding(
                    "nice",
                    "empate-no-topo",
                    "Empate técnico no topo",
                    f"{filtradas[top[0]]['id']} e {filtradas[top[1]]['id']}",
                    f"A diferença de score é de {abs(pontuacoes[top[0]] - pontuacoes[top[1]]):.3f}.",
                    "Empate dentro de 0,05 é ruído de tokenização, não preferência.",
                    "Desempate pelo risco declarado e pelo que você vai usar de fato.",
                    "A ordem apresentada sugere uma preferência que a conta não sustenta.",
                )
            )
        faltando = sorted(set(dimensoes_brief) - cobertas)
        if faltando:
            achados.append(
                finding(
                    "should",
                    "cobertura-parcial",
                    "Candidatos não cobrem todas as dimensões do briefing",
                    ", ".join(_rotulo_dimensao(chave) for chave in faltando[:3]),
                    "As dimensões do pedido aparecem no texto, mas nenhum dos candidatos as toca.",
                    "Cobrir o pedido exige ao menos um candidato por dimensão citada.",
                    "Busque as dimensões que faltam separadamente e aceite uma lacuna declarada.",
                    "A stack fecha com buraco silencioso.",
                )
            )

    findings, counts, veredito, perguntas = finalize(
        achados,
        modo,
        [
            "Algum candidato foi descartado só pelo nome? Leia a descrição antes de excluir.",
            "A dimensão que falta é lacuna de catálogo ou de briefing?",
            "Quem aprova a escolha sabe por que esta skill entrou e a de cima não?",
        ],
    )
    metrics = {
        "entradas": len(entradas),
        "filtradas": len(filtradas),
        "consulta": len(consulta),
        "resultados": len(rows),
        "melhor": round(melhor, 3),
        "dimensoes": len(dimensoes_brief),
        "cobertas": len(cobertas),
    }
    summary = [
        f"{len(entradas):,} entrada(s) no catálogo, {len(filtradas):,} depois dos filtros, {len(rows)} no resultado.".replace(",", "."),
        f"Consulta com {len(consulta)} termo(s); melhor score {melhor:.2f} com k1={K1} e b={B}.",
    ]
    limitations = [
        "BM25 pontua coincidência de termos, não adequação: uma skill pode ser a certa sem repetir as palavras do briefing.",
        "O catálogo é o que você colou; entrada ausente do JSON é invisível para a busca.",
        *avisos,
        "A soma de risco não entra no ranking — risco se declara depois, na validação da stack.",
    ]
    return common(
        analysis="selecao.buscar",
        mode=modo,
        title="Recomendação de skills",
        summary=summary,
        findings=findings,
        counts=counts,
        verdict=veredito,
        questions=perguntas,
        rows=rows,
        metrics=metrics,
        limitations=limitations,
    )


# --- 3. stack ---------------------------------------------------------------


def ler_stack(texto: str) -> tuple[list[str], bool]:
    """Aceita `aas-stack.json`, lista JSON de ids, ou um id por linha. Devolve os ids e se havia evidência."""
    bruto = texto.strip()
    if not bruto:
        raise SelecaoError("Informe a stack: ids em JSON, manifesto `aas-stack.json` ou um id por linha.")
    if bruto[0] in "[{":
        try:
            dados = json.loads(bruto)
        except json.JSONDecodeError as exc:
            raise SelecaoError(f"Stack JSON inválida na linha {exc.lineno}: {exc.msg}.") from exc
        if isinstance(dados, dict):
            lista = dados.get("skills") or dados.get("selected") or []
            evidencia = bool(dados.get("evidence") or dados.get("selectionEvidence") or dados.get("profile"))
        else:
            lista = dados
            evidencia = False
        if not isinstance(lista, list):
            raise SelecaoError("A stack precisa ser uma lista de ids ou um objeto com a chave `skills`.")
        ids = []
        for item in lista:
            if isinstance(item, str):
                ids.append(item.strip())
            elif isinstance(item, dict):
                identificador = item.get("id") or item.get("name") or item.get("skill")
                if identificador:
                    ids.append(str(identificador).strip())
                    if item.get("evidence") or item.get("rationale"):
                        evidencia = True
        return [item for item in ids if item], evidencia
    ids = []
    for linha in bruto.splitlines():
        limpa = linha.strip().lstrip("-*").strip().strip('"').strip("'")
        if not limpa or limpa.startswith("#"):
            continue
        ids.append(limpa.split("|")[0].strip())
    return [item for item in ids if item], False


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def validar_stack(
    *,
    brief: str,
    skills: str,
    catalogo: str,
    alvo: str = "claude",
    limite_risco: int = 4,
    max_skills: int = MAX_SKILLS,
    modo: str = "full",
) -> dict[str, Any]:
    """Confere os ids escolhidos contra o catálogo e contra as dimensões do briefing."""
    modo = _modo(modo)
    if max_skills < 1 or max_skills > MAX_SKILLS:
        raise SelecaoError(f"O teto de skills precisa estar entre 1 e {MAX_SKILLS}.")
    if limite_risco < 0:
        raise SelecaoError("O limite de risco não pode ser negativo.")
    entradas, avisos = ler_catalogo(catalogo)
    if not entradas:
        raise SelecaoError("O catálogo não tem nenhuma entrada válida.")
    ids, evidencia = ler_stack(skills)
    if not ids:
        raise SelecaoError("A stack não tem nenhum id.")

    por_id = {entrada["id"]: entrada for entrada in entradas}
    por_nome = {_normalizar(entrada["id"]): entrada for entrada in entradas}
    selecionadas: list[dict[str, Any]] = []
    inexistentes: list[str] = []
    for identificador in ids:
        entrada = por_id.get(identificador) or por_nome.get(_normalizar(identificador))
        if entrada is None:
            inexistentes.append(identificador)
        else:
            selecionadas.append(entrada)

    repetidas = [item for item, contagem in Counter(entrada["id"] for entrada in selecionadas).items() if contagem > 1]
    dimensoes_brief = set(_dimensoes(brief))
    cobertas: set[str] = set()
    linhas = []
    for entrada in selecionadas:
        dimensoes = set(_dimensoes(_campo(entrada)))
        cobertas.update(dimensoes & dimensoes_brief)
        situacao = "ok"
        if alvo and entrada["alvos"] and _normalizar(alvo) not in [_normalizar(item) for item in entrada["alvos"]]:
            situacao = "alvo ausente"
        linhas.append(
            {
                "skill": entrada["id"],
                "categoria": entrada["categoria"] or "—",
                "risco": entrada["risco"] or "—",
                "dimensoes": ", ".join(_rotulo_dimensao(chave) for chave in sorted(dimensoes)) or "—",
                "situacao": situacao,
            }
        )

    sobrepostas: list[tuple[str, str]] = []
    for indice, primeira in enumerate(selecionadas):
        for segunda in selecionadas[indice + 1 :]:
            dim_a = set(_dimensoes(_campo(primeira)))
            dim_b = set(_dimensoes(_campo(segunda)))
            if len(dim_a & dim_b) < 2:
                continue
            tokens_a = set(_tokens(_campo(primeira)))
            tokens_b = set(_tokens(_campo(segunda)))
            if _jaccard(tokens_a, tokens_b) >= SOBREPOSICAO:
                sobrepostas.append((primeira["id"], segunda["id"]))

    pontos = sum(PONTOS_RISCO.get(entrada["risco"], 1) for entrada in selecionadas)
    criticos = sum(1 for entrada in selecionadas if entrada["risco"] in {"critical", "offensive"})
    lacunas = sorted(dimensoes_brief - cobertas)
    manuais = [entrada["id"] for entrada in selecionadas if entrada["setup"] == "manual"]
    alvo_ausente = [linha["skill"] for linha in linhas if linha["situacao"] == "alvo ausente"]

    achados: list[dict[str, Any]] = []
    if not brief.strip():
        achados.append(
            finding(
                "must",
                "sem-brief",
                "Stack sem briefing para comparar",
                f"{len(selecionadas)} skill(s)",
                "Sem o pedido, não há dimensão para conferir cobertura.",
                "A validação vira só checagem de id válido.",
                "Cole o briefing usado na escolha.",
                "Não há como saber se a stack cobre o trabalho.",
            )
        )
    if inexistentes:
        achados.append(
            finding(
                "must",
                "skill-inexistente",
                f"{len(inexistentes)} id(s) fora do catálogo",
                ", ".join(inexistentes[:5]),
                "O id não existe na versão do catálogo que você colou.",
                "Id inválido no manifesto faz o `compose_stack` do Core recusar a stack inteira.",
                "Copie o id exato do catálogo ou remova a entrada.",
                "O manifesto não passa na validação e nada é instalado.",
            )
        )
    if repetidas:
        achados.append(
            finding(
                "must",
                "id-repetido",
                "Id repetido na stack",
                ", ".join(repetidas[:5]),
                "O mesmo id aparece mais de uma vez.",
                "Repetição infla a contagem e mascara lacuna de cobertura.",
                "Deixe uma ocorrência de cada id.",
                "O plano ganha fase duplicada e o orçamento de skills mente.",
            )
        )
    if len(ids) > max_skills:
        achados.append(
            finding(
                "must",
                "stack-acima-do-limite",
                "Stack acima do teto técnico",
                f"{len(ids)} > {max_skills}",
                "O manifesto do Core aceita no máximo 128 ids; acima disso a composição não fecha.",
                "Teto não é meta: uma stack grande demais não é lida nem revisada.",
                "Corte para o que cobre as dimensões do briefing e declare o resto como lacuna.",
                "A stack é recusada ou revisada por amostragem.",
            )
        )
    if not selecionadas:
        achados.append(
            finding(
                "must",
                "stack-vazia",
                "Nenhum id válido na stack",
                f"{len(ids)} id(s) informado(s)",
                "Todos os ids informados estão fora do catálogo.",
                "Sem skill válida não há cobertura, risco nem plano.",
                "Recomece pela busca e copie os ids do resultado.",
                "Não há stack para validar.",
            )
        )
    else:
        if lacunas:
            amostra = ", ".join(_rotulo_dimensao(chave) for chave in lacunas[:3])
            achados.append(
                finding(
                    "must",
                    "lacuna-de-dimensao",
                    f"{len(lacunas)} dimensão(ões) do briefing sem skill",
                    amostra,
                    "O briefing nomeia a dimensão e nenhuma skill selecionada a toca.",
                    "Lacuna silenciosa é a falha mais cara da seleção: o trabalho começa sem cobertura.",
                    "Busque uma skill para cada dimensão que falta ou declare a lacuna no plano.",
                    "A entrega chega na fase final sem ter passado por ali.",
                )
            )
        if sobrepostas:
            achados.append(
                finding(
                    "should",
                    "sobreposicao",
                    f"{len(sobrepostas)} par(es) de skills sobrepostas",
                    "; ".join(f"{a} ~ {b}" for a, b in sobrepostas[:3]),
                    "Duas skills tocam as mesmas duas dimensões com vocabulário muito próximo.",
                    "Sobreposição gasta contexto e produz instruções concorrentes.",
                    "Fique com a de melhor score e mais específica; a outra vira redundante.",
                    "Duas instruções discordam e o agente escolhe a última lida.",
                )
            )
        if pontos > limite_risco:
            achados.append(
                finding(
                    "should",
                    "risco-alto",
                    "Orçamento de risco estourado",
                    f"{pontos} ponto(s) > {limite_risco}",
                    "Cada skill soma pontos: safe 0, none/unknown 1, offensive 2, critical 3.",
                    "Muitas skills críticas juntas aumentam a superfície sem aumentar a cobertura.",
                    "Troque uma crítica por uma segura equivalente ou eleve o limite com justificativa.",
                    "A stack executa comandos destrutivos e ninguém revisou o conjunto.",
                )
            )
        if alvo_ausente:
            achados.append(
                finding(
                    "must",
                    "alvo-incompativel",
                    f"{len(alvo_ausente)} skill(s) sem o alvo `{alvo}`",
                    ", ".join(alvo_ausente[:5]),
                    "O manifesto declara um alvo que a skill não suporta.",
                    "Skill sem o alvo não é carregada pelo host escolhido.",
                    "Troque a skill ou mude o alvo da stack.",
                    "A skill entra no manifesto e não aparece no host.",
                )
            )
        if manuais:
            achados.append(
                finding(
                    "should",
                    "setup-manual",
                    f"{len(manuais)} skill(s) com setup manual",
                    ", ".join(manuais[:5]),
                    "A entrada declara `setup.type = manual`: precisa de passo humano antes de rodar.",
                    "Setup manual quebrado interrompe a fase no meio.",
                    "Liste o passo de setup como pré-requisito da fase.",
                    "A fase trava esperando uma credencial que ninguém provisionou.",
                )
            )
        if dimensoes_brief and len(cobertas) < len(dimensoes_brief):
            pct = _percentual(len(cobertas), len(dimensoes_brief))
            if not lacunas and pct < COBERTURA_MINIMA:
                achados.append(
                    finding(
                        "should",
                        "cobertura-baixa",
                        "Cobertura abaixo do mínimo",
                        f"{pct}% < {COBERTURA_MINIMA}%",
                        "Menos de 60% das dimensões do briefing têm skill.",
                        "Stack que cobre pouco não sustenta o plano.",
                        "Volte à busca para as dimensões descobertas.",
                        "O plano nasce com fases vazias.",
                    )
                )
    if not evidencia:
        achados.append(
            finding(
                "nice",
                "sem-evidencia",
                "Manifesto sem evidência de seleção",
                "campo `evidence` ausente",
                "O Core registra traço de busca e ledgers quando o cliente exporta a evidência.",
                "Sem evidência, a escolha não é auditável depois.",
                "Acrescente `evidence` por skill ou exporte o sidecar de seleção.",
                "Ninguém consegue refazer a decisão seis meses depois.",
            )
        )

    extra = []
    if lacunas:
        extra = ["", "## Lacunas declaradas", ""]
        extra += [f"- **{_rotulo_dimensao(chave)}** — nenhuma skill selecionada toca esta dimensão." for chave in lacunas]

    findings, counts, veredito, perguntas = finalize(
        achados,
        modo,
        [
            "A skill que falta é lacuna do catálogo ou você não buscou por ela?",
            "Qual skill crítica pode ser trocada por uma segura sem perder cobertura?",
            "Quem revisa a stack antes de instalar?",
        ],
    )
    metrics = {
        "skills": len(ids),
        "validas": len(selecionadas),
        "dimensoes": len(dimensoes_brief),
        "cobertas": len(cobertas),
        "lacunas": len(lacunas),
        "sobrepostas": len(sobrepostas),
        "criticos": criticos,
        "pontos_risco": pontos,
        "limite": limite_risco,
    }
    summary = [
        f"{len(selecionadas)} de {len(ids)} id(s) existem no catálogo; {len(cobertas)} de {len(dimensoes_brief)} dimensão(ões) cobertas.",
        f"Risco somado: {pontos} ponto(s) contra limite de {limite_risco}; {criticos} skill(s) crítica(s).",
    ]
    limitations = [
        "A cobertura é lexical: a skill pode cobrir a dimensão sem repetir as palavras do léxico.",
        "Sobreposição mede vocabulário compartilhado, não instrução contraditória — leia os dois SKILL.md.",
        "O catálogo é o que você colou; a versão do Core pode ter mais ou menos skills.",
        *avisos,
        "Nada é instalado, composto ou gravado: a validação é a mesma `compose_stack` feita em memória, aqui sem escrever manifesto.",
    ]
    return common(
        analysis="selecao.stack",
        mode=modo,
        title="Validação de stack",
        summary=summary,
        findings=findings,
        counts=counts,
        verdict=veredito,
        questions=perguntas,
        rows=linhas,
        metrics=metrics,
        limitations=limitations,
        extra_sections=extra,
    )


# --- 4. plano ---------------------------------------------------------------

ARTEFATOS = {
    "arquitetura": "decisão de arquitetura",
    "linguagens": "esqueleto do projeto",
    "dominio": "regra de domínio implementada",
    "dados": "schema e migração",
    "integracoes": "contrato de integração",
    "qualidade": "suíte de teste",
    "seguranca": "revisão de segurança",
    "experiencia": "tela revisada",
    "operacao": "pipeline de deploy",
    "manutencao": "nota de manutenção",
}

CHECAGENS = {
    "arquitetura": "a decisão cabe em uma página e nomeia o que fica fora",
    "linguagens": "o esqueleto roda com um comando e sem passo manual",
    "dominio": "um caso de teste do domínio passa de ponta a ponta",
    "dados": "a migração roda para frente e para trás sem perda",
    "integracoes": "o contrato está documentado e tem resposta de erro",
    "qualidade": "a suíte falha quando o comportamento quebra",
    "seguranca": "nenhum segredo no repositório e nenhum acesso sem autorização",
    "experiencia": "o fluxo principal passa sem mouse e em 390 px de largura",
    "operacao": "o deploy é repetível e o rollback foi ensaiado",
    "manutencao": "a próxima pessoa entende o porquê sem perguntar",
}

PORTOES = ("aprov", "revis", "portao", "portão", "checkpoint", "gate", "sign-off", "assinatura")


def montar_plano(
    *,
    brief: str,
    skills: str,
    catalogo: str = "",
    alvo: str = "claude",
    modo: str = "full",
) -> dict[str, Any]:
    """Ordena as skills escolhidas em fases com objetivo, artefato e checagem de saída."""
    modo = _modo(modo)
    if len(brief.strip()) < 20:
        raise SelecaoError("Descreva o pedido em pelo menos 20 caracteres para haver plano.")
    ids, _evidencia = ler_stack(skills)
    if not ids:
        raise SelecaoError("A stack não tem nenhum id.")
    entradas, avisos = ler_catalogo(catalogo) if catalogo.strip() else ([], [])
    por_id = {entrada["id"]: entrada for entrada in entradas}
    por_nome = {_normalizar(entrada["id"]): entrada for entrada in entradas}

    dimensoes_brief = set(_dimensoes(brief))
    dimensoes_skills: set[str] = set()
    ordem = {chave: indice for indice, (chave, _rotulo, _palavras) in enumerate(DIMENSOES)}
    fases: dict[str, list[str]] = {}
    sem_catalogo: list[str] = []
    desconhecidas: list[str] = []
    for identificador in ids:
        entrada = por_id.get(identificador) or por_nome.get(_normalizar(identificador))
        if entrada is None:
            if entradas:
                desconhecidas.append(identificador)
                continue
            sem_catalogo.append(identificador)
            dimensoes_id = _dimensoes(identificador.replace("-", " "))
            chave = min(dimensoes_id, key=lambda item: ordem[item]) if dimensoes_id else "execucao"
            fases.setdefault(chave, []).append(identificador)
            dimensoes_skills.update(dimensoes_id)
            continue
        chave = _principal(entrada) or "execucao"
        fases.setdefault(chave, []).append(entrada["id"])
        dimensoes_skills.update(_dimensoes(_campo(entrada)))

    sequeladas = sorted(fases, key=lambda chave: ordem.get(chave, len(ordem)))
    linhas = []
    for numero, chave in enumerate(sequeladas, start=1):
        for skill in fases[chave]:
            rotulo = _rotulo_dimensao(chave) if chave in ordem else "Execução"
            linhas.append(
                {
                    "fase": numero,
                    "dimensao": rotulo,
                    "skill": skill,
                    "artefato": ARTEFATOS.get(chave, "saída revisada"),
                    "checagem": CHECAGENS.get(chave, "a fase produz o artefato declarado"),
                    "depende": str(numero - 1) if numero > 1 else "—",
                }
            )

    criticas = [entrada["id"] for entrada in entradas if entrada["id"] in {linha["skill"] for linha in linhas} and entrada["risco"] in {"critical", "offensive"}]
    portao = bool(_tem(brief, PORTOES))
    cobertas = len(dimensoes_brief & dimensoes_skills)

    achados: list[dict[str, Any]] = []
    if desconhecidas:
        achados.append(
            finding(
                "must",
                "skill-inexistente",
                f"{len(desconhecidas)} id(s) fora do catálogo",
                ", ".join(desconhecidas[:5]),
                "O id não existe na versão do catálogo colada.",
                "Fase construída sobre id inexistente não tem instrução para executar.",
                "Corrija o id ou remova a fase.",
                "A fase é um título sem conteúdo.",
            )
        )
    if not linhas:
        achados.append(
            finding(
                "must",
                "plano-vazio",
                "Nenhuma fase montada",
                "stack sem id utilizável",
                "Nenhum id gerou fase, com ou sem catálogo.",
                "Plano sem fase não é plano.",
                "Informe ids válidos, com catálogo quando possível.",
                "Não há sequência para executar.",
            )
        )
    if criticas and not portao:
        achados.append(
            finding(
                "must",
                "risco-sem-portao",
                "Skill crítica sem portão de aprovação",
                ", ".join(criticas[:5]),
                "A stack tem skill classificada como crítica ou ofensiva, e o briefing não pede revisão nem aprovação.",
                "Ação destrutiva ou ofensiva precisa de parada explícita antes de rodar.",
                "Acrescente uma fase de revisão com critério de aceite antes da skill crítica.",
                "O plano executa o passo mais perigoso sem ninguém olhar.",
            )
        )
    if len(sequeladas) > 8:
        achados.append(
            finding(
                "should",
                "muitas-fases",
                f"Plano com {len(sequeladas)} fases",
                "sequência completa",
                "Mais de oito fases costuma ser catálogo, não plano.",
                "Fase demais esconde dependência e dilui a checagem.",
                "Agrupe fases da mesma dimensão e mantenha a checagem no fim do grupo.",
                "Ninguém acompanha o plano até o fim.",
            )
        )
    if dimensoes_brief and cobertas < len(dimensoes_brief):
        achados.append(
            finding(
                "should",
                "plano-descoberto",
                f"{len(dimensoes_brief) - cobertas} dimensão(ões) do briefing fora do plano",
                ", ".join(_rotulo_dimensao(chave) for chave in sorted(dimensoes_brief - dimensoes_skills)[:3]),
                "O briefing nomeia dimensões que nenhuma fase cobre.",
                "Plano que ignora dimensão do pedido entrega pela metade.",
                "Acrescente a fase ou declare a lacuna com justificativa.",
                "A entrega falha onde ninguém olhou.",
            )
        )
    if len(linhas) < 2:
        achados.append(
            finding(
                "nice",
                "plano-curto",
                "Plano com uma fase",
                f"{len(linhas)} fase",
                "Uma skill só não gera sequência com dependência.",
                "Plano de uma fase é tarefa, não plano.",
                "Use a busca para achar as skills das outras dimensões.",
                "O plano não acrescenta nada ao uso direto da skill.",
            )
        )
    findings, counts, veredito, perguntas = finalize(
        achados,
        modo,
        [
            "A ordem das fases respeita a dependência real ou só a ordem do léxico?",
            "Qual fase pode ser cortada se o prazo encurtar?",
            "Quem aprova a fase crítica e com qual critério?",
        ],
    )
    metrics = {
        "fases": len(sequeladas),
        "linhas": len(linhas),
        "skills": len(ids),
        "criticas": len(criticas),
        "cobertas": cobertas,
        "dimensoes": len(dimensoes_brief),
        "portao": int(portao),
    }
    summary = [
        f"{len(linhas)} passo(s) em {len(sequeladas)} fase(s), {cobertas} de {len(dimensoes_brief)} dimensão(ões) do briefing cobertas.",
        f"{len(criticas)} skill(s) crítica(s); portão de aprovação {'declarado' if portao else 'ausente'}.",
    ]
    limitations = [
        "A ordem segue a sequência canônica das dez dimensões, não a dependência real do seu projeto.",
        "O artefato e a checagem são derivados da dimensão, não do conteúdo do SKILL.md.",
        *avisos,
        "Sem catálogo, as fases saem dos ids e das dimensões do briefing: o objetivo e o risco de cada skill não são conhecidos.",
        "O plano não executa nada: é texto para revisão.",
    ]
    return common(
        analysis="selecao.plano",
        mode=modo,
        title="Plano por dimensão",
        summary=summary,
        findings=findings,
        counts=counts,
        verdict=veredito,
        questions=perguntas,
        rows=linhas,
        metrics=metrics,
        limitations=limitations,
    )


# --- 5. catálogo ------------------------------------------------------------


def auditar_catalogo(*, catalogo: str, modo: str = "full") -> dict[str, Any]:
    """Confere o índice: campos, ids, caminhos, risco e distribuição."""
    modo = _modo(modo)
    entradas, avisos = ler_catalogo(catalogo)
    if not entradas:
        raise SelecaoError("O catálogo não tem nenhuma entrada válida.")

    total = len(entradas)
    categorias = Counter(entrada["categoria"] for entrada in entradas if entrada["categoria"])
    riscos = Counter(entrada["risco"] or "vazio" for entrada in entradas)
    fontes = Counter(entrada["fonte"] or "vazio" for entrada in entradas)
    sem_descricao = [entrada["id"] for entrada in entradas if not entrada["descricao"]]
    duplicados = [item for item, contagem in Counter(entrada["id"] for entrada in entradas).items() if contagem > 1]
    id_diferente = [entrada["id"] for entrada in entradas if entrada["nome"] and entrada["nome"] != entrada["id"]]
    path_ruim = [entrada["id"] for entrada in entradas if entrada["path"] and not entrada["path"].startswith("skills/")]
    indefinidos = [entrada["id"] for entrada in entradas if entrada["risco"] in {"", "unknown", "none"}]
    longas = [entrada["id"] for entrada in entradas if _palavras(entrada["descricao"]) > 40]
    sem_alvo = [entrada["id"] for entrada in entradas if not entrada["alvos"]]
    manuais = [entrada["id"] for entrada in entradas if entrada["setup"] == "manual"]
    unicas = [categoria for categoria, contagem in categorias.items() if contagem == 1]
    criticos = riscos.get("critical", 0)
    palavras = [_palavras(entrada["descricao"]) for entrada in entradas]

    achados: list[dict[str, Any]] = []
    if sem_descricao:
        achados.append(
            finding(
                "must",
                "sem-descricao",
                f"{len(sem_descricao)} entrada(s) sem descrição",
                ", ".join(sem_descricao[:5]),
                "A busca casa nome, categoria e descrição; sem descrição sobra o nome.",
                "Entrada sem descrição é invisível para quem procura por intenção.",
                "Escreva a linha que diz o que a skill faz e quando usar.",
                "A skill existe no catálogo e nunca aparece na busca.",
            )
        )
    if duplicados:
        achados.append(
            finding(
                "must",
                "id-duplicado",
                f"{len(duplicados)} id(s) repetido(s)",
                ", ".join(duplicados[:5]),
                "O mesmo id aparece mais de uma vez no índice.",
                "Id duplicado quebra a composição de stack, que indexa por id.",
                "Fique com uma entrada e mescle a outra.",
                "O `compose_stack` do host recusa o manifesto.",
            )
        )
    if path_ruim:
        achados.append(
            finding(
                "should",
                "path-fora-do-padrao",
                f"{len(path_ruim)} caminho(s) fora de `skills/`",
                ", ".join(path_ruim[:5]),
                "O caminho declarado não começa por `skills/`.",
                "O instalador procura o SKILL.md no caminho declarado.",
                "Mova a pasta ou corrija o campo `path`.",
                "A instalação falha depois de baixar.",
            )
        )
    if id_diferente:
        achados.append(
            finding(
                "should",
                "id-diferente-do-nome",
                f"{len(id_diferente)} id(s) diferente(s) do nome",
                ", ".join(id_diferente[:5]),
                "O campo `name` do frontmatter diverge do id do índice.",
                "A regra do repositório é o nome da pasta casar com o nome da skill.",
                "Alinhe nome, pasta e id.",
                "Busca acha por um nome e a instalação usa outro.",
            )
        )
    if indefinidos:
        achados.append(
            finding(
                "should",
                "risco-indefinido",
                f"{len(indefinidos)} entrada(s) sem risco classificado",
                f"{_percentual(len(indefinidos), total)}% do catálogo",
                "`unknown`, `none` ou vazio: o risco não foi classificado.",
                "Sem risco, a stack não consegue somar orçamento de risco.",
                "Classifique como safe, offensive ou critical conforme o comportamento real.",
                "Toda skill indefinida pesa como risco no cálculo e some da triagem.",
            )
        )
    if criticos and _percentual(criticos, total) >= 50:
        achados.append(
            finding(
                "should",
                "risco-critico-alto",
                f"Metade ou mais do catálogo é crítica ({_percentual(criticos, total)}%)",
                f"{criticos:,} de {total:,}".replace(",", "."),
                "Marcar quase tudo como crítico apaga a distinção.",
                "Risco que não separa não serve para escolher.",
                "Reveja a classificação das skills que só leem ou resumem conteúdo.",
                "O limite de risco estoura com qualquer stack.",
            )
        )
    if longas:
        achados.append(
            finding(
                "should",
                "descricao-longa",
                f"{len(longas)} descrição(ões) acima de 40 palavras",
                ", ".join(longas[:5]),
                "A descrição vira parágrafo em vez de linha de catálogo.",
                "Descrição longa dilui o BM25 e não cabe na lista.",
                "Deixe a primeira frase como gatilho e o resto no SKILL.md.",
                "A busca pontua palavra acessória acima do objetivo.",
            )
        )
    if sem_alvo:
        achados.append(
            finding(
                "should",
                "alvo-ausente",
                f"{len(sem_alvo)} entrada(s) sem alvo declarado",
                ", ".join(sem_alvo[:5]),
                "`plugin.targets` vazio: nenhum host declarado.",
                "Sem alvo, a validação de stack não consegue conferir compatibilidade.",
                "Declare os alvos suportados (claude, codex).",
                "A skill entra na stack e não carrega em host nenhum.",
            )
        )
    if unicas:
        achados.append(
            finding(
                "nice",
                "categoria-unica",
                f"{len(unicas)} categoria(s) com uma entrada só",
                ", ".join(sorted(unicas)[:6]),
                "Categoria de um item não ajuda a navegar.",
                "Categoria com uma entrada é filtro que não filtra.",
                "Mescle na categoria vizinha.",
                "O catálogo ganha taxonomia sem utilidade.",
            )
        )
    if manuais:
        achados.append(
            finding(
                "nice",
                "setup-manual",
                f"{len(manuais)} skill(s) com setup manual",
                ", ".join(manuais[:5]),
                "`setup.type = manual` exige passo humano antes do uso.",
                "Instalação em lote quebra no primeiro setup manual.",
                "Documente o passo junto da entrada.",
                "O host instala e a skill não roda.",
            )
        )

    rows = []
    problemas = (
        [(item, "sem descrição") for item in sem_descricao]
        + [(item, "id repetido") for item in duplicados]
        + [(item, "path fora de skills/") for item in path_ruim]
        + [(item, "nome diverge do id") for item in id_diferente]
        + [(item, "risco indefinido") for item in indefinidos]
        + [(item, "descrição longa") for item in longas]
        + [(item, "sem alvo") for item in sem_alvo]
    )
    for identificador, problema in problemas[:60]:
        rows.append({"id": identificador, "problema": problema})

    findings, counts, veredito, perguntas = finalize(
        achados,
        modo,
        [
            "A classificação de risco foi revista depois da última mudança de comportamento?",
            "Quantas entradas o instalador carrega por padrão — o catálogo todo ou uma seleção?",
            "Quem revisa o índice quando a categoria cresce?",
        ],
    )
    metrics = {
        "entradas": total,
        "categorias": len(categorias),
        "criticos": criticos,
        "indefinidos": len(indefinidos),
        "manuais": len(manuais),
        "sem_descricao": len(sem_descricao),
        "duplicados": len(duplicados),
        "media_palavras": round(sum(palavras) / total, 1) if total else 0.0,
        "alvos": len({alvo for entrada in entradas for alvo in entrada["alvos"]}),
    }
    summary = [
        f"{total:,} entrada(s) em {len(categorias)} categoria(s); média de {metrics['media_palavras']} palavra(s) por descrição.".replace(",", "."),
        "Risco: " + ", ".join(f"{nome} {quantidade}" for nome, quantidade in riscos.most_common(5)) + ".",
        "Fontes: " + ", ".join(f"{nome[:40]} {quantidade}" for nome, quantidade in fontes.most_common(3)) + ".",
    ]
    limitations = [
        "O índice descreve a intenção declarada: uma descrição pode prometer o que o SKILL.md não faz.",
        "Risco é o rótulo do catálogo, não uma auditoria; a análise de uma skill específica é outro trabalho.",
        "Categorias não são validadas contra uma lista fechada: o catálogo tem 114 e muda toda semana.",
        *avisos,
    ]
    return common(
        analysis="selecao.catalogo",
        mode=modo,
        title="Auditoria do catálogo",
        summary=summary,
        findings=findings,
        counts=counts,
        verdict=veredito,
        questions=perguntas,
        rows=rows,
        metrics=metrics,
        limitations=limitations,
    )


# --- catálogo ---------------------------------------------------------------


def selecao_catalogo() -> dict[str, Any]:
    """Publica o que a camada mede, com que números, e o que fica de fora."""
    return {
        "fonte": "sickn33/agentic-awesome-skills (MIT)",
        "versao": VERSAO,
        "principio": "O Core não ranqueia nem recomenda: ele valida ids. Aqui a conta é explícita e auditável.",
        "dimensoes": [{"chave": chave, "rotulo": rotulo, "palavras": list(palavras)} for chave, rotulo, palavras in DIMENSOES],
        "categorias": {trecho: dimensao for trecho, dimensao in CATEGORIA_DIMENSAO},
        "busca": {
            "algoritmo": "BM25 sobre nome (peso 3), categoria (peso 2) e descrição (peso 1)",
            "k1": K1,
            "b": B,
            "pesos": {"nome": PESO_NOME, "categoria": PESO_CATEGORIA, "descricao": PESO_DESCRICAO},
            "limiar_de_score": LIMIAR_SCORE,
            "empate": EMPATE,
            "normalizacao": "sem acento, minúsculas, plural e singular indexados juntos",
        },
        "risco": {
            "pontos": PONTOS_RISCO,
            "ordem": list(RISCO_ORDEM),
            "limite_padrao": 4,
            "regra": "safe 0, none/unknown 1, offensive 2, critical 3; a soma é comparada ao limite",
        },
        "stack": {
            "max_skills": MAX_SKILLS,
            "alvos": list(ALVOS),
            "cobertura_minima": COBERTURA_MINIMA,
            "sobreposicao": SOBREPOSICAO,
            "regra": "lacuna e id inexistente bloqueiam; sobreposição e risco estourado corrigem",
            "manifesto": "aceita `aas-stack.json`, lista JSON de ids ou um id por linha",
        },
        "plano": {
            "ordem": [chave for chave, _rotulo, _palavras in DIMENSOES],
            "artefatos": ARTEFATOS,
            "checagens": CHECAGENS,
            "portoes": list(PORTOES),
            "regra": "a fase vem da categoria da skill; sem categoria que case, da dimensão com mais palavras",
        },
        "catalogo": {
            "campos": ["id", "path", "category", "name", "description", "risk", "source", "plugin.targets", "plugin.setup"],
            "riscos": list(RISCO_ORDEM),
            "regras": [
                "toda entrada precisa de id, caminho em `skills/` e descrição",
                "id não pode repetir: a composição indexa por id",
                "o nome do frontmatter casa com o id",
                "risco precisa ser classificado; `unknown` e `none` contam como indefinido",
                "descrição deve caber em uma linha, até 40 palavras",
                "todo item declara ao menos um alvo em `plugin.targets`",
                "setup manual precisa estar documentado",
                "categoria com uma entrada só é candidata a fusão",
                "catálogo com metade ou mais em `critical` perde poder de triagem",
            ],
        },
        "limites": {
            "texto": MAX_TEXTO,
            "entradas": MAX_ENTRADAS,
            "resultados": {"minimo": MIN_RESULTADOS, "maximo": MAX_RESULTADOS},
            "skills": MAX_SKILLS,
        },
        "deixado_de_fora": [
            "Não há leitura de repositório nem download: o catálogo é o JSON colado, e o que não está nele não existe para a busca.",
            "Não há embeddings: BM25 casa palavra, não sentido — paráfrase sem termo em comum não é encontrada.",
            "Não há julgamento semântico da skill: a adequação fina continua sendo leitura humana do SKILL.md.",
            "Não há instalação, composição nem gravação de manifesto: nada é escrito em disco.",
            "Não há consulta ao Core nem ao índice remoto: versão, ids e risco são os do arquivo informado.",
        ],
        "executado": False,
    }


# --- 7. cobertura -----------------------------------------------------------


def mapear_cobertura(
    *,
    brief: str,
    catalogo: str,
    limite_por_dimensao: int = 3,
    modo: str = "full",
) -> dict[str, Any]:
    """Para cada dimensão do briefing, conta o que o catálogo tem e o que falta."""
    modo = _modo(modo)
    if limite_por_dimensao < 1 or limite_por_dimensao > 10:
        raise SelecaoError("O limite por dimensão precisa estar entre 1 e 10.")
    entradas, avisos = ler_catalogo(catalogo)
    if not entradas:
        raise SelecaoError("O catálogo não tem nenhuma entrada válida.")
    dimensoes_brief = _dimensoes(brief)
    if not dimensoes_brief:
        raise SelecaoError("O briefing não toca nenhuma das dez dimensões: descreva o que precisa ser feito.")

    total = len(entradas)
    documentos = [_tokens(_campo(entrada)) for entrada in entradas]
    dimensoes_por_entrada = [_dimensoes(_campo(entrada)) for entrada in entradas]
    linhas = []
    lacunas: list[str] = []
    for chave in sorted(dimensoes_brief, key=lambda item: -len(dimensoes_brief[item])):
        palavras = next(p for nome, _rotulo, p in DIMENSOES if nome == chave)
        consulta = _termos(" ".join(palavras))
        pontuacoes = _pontuar(entradas, consulta, documentos)
        ordem = sorted(range(total), key=lambda indice: (-pontuacoes[indice], entradas[indice]["id"]))
        melhores = [entradas[indice] for indice in ordem[:limite_por_dimensao] if pontuacoes[indice] > 0]
        cobertura = sum(1 for achadas in dimensoes_por_entrada if chave in achadas)
        if not melhores:
            lacunas.append(chave)
        linhas.append(
            {
                "dimensao": _rotulo_dimensao(chave),
                "chave": chave,
                "skills": cobertura,
                "cobertura": _percentual(cobertura, total),
                "melhor": melhores[0]["id"] if melhores else "—",
                "candidatas": ", ".join(entrada["id"] for entrada in melhores) or "—",
            }
        )

    achados: list[dict[str, Any]] = []
    if lacunas:
        achados.append(
            finding(
                "must",
                "dimensao-sem-skill",
                f"{len(lacunas)} dimensão(ões) sem nenhuma skill",
                ", ".join(_rotulo_dimensao(chave) for chave in lacunas[:3]),
                "O briefing pede a dimensão e o catálogo não tem nenhuma entrada que a toque.",
                "Lacuna de catálogo não se resolve escolhendo melhor: falta material.",
                "Declare a lacuna no plano e trate a dimensão fora do catálogo.",
                "A stack fecha com um buraco que ninguém vê.",
            )
        )
    vazias = [linha for linha in linhas if linha["cobertura"] < 5 and linha["skills"] > 0]
    if vazias:
        achados.append(
            finding(
                "should",
                "dimensao-escassa",
                f"{len(vazias)} dimensão(ões) cobrem menos de 5% do catálogo",
                ", ".join(linha["dimensao"] for linha in vazias[:3]),
                "Há candidata, mas pouca: menos de 5% das entradas tocam a dimensão.",
                "Dimensão escassa tende a ter uma skill genérica cobrindo tudo.",
                "Confira se a candidata realmente cobre ou se é a única opção.",
                "A escolha é por falta de alternativa, não por adequação.",
            )
        )
    saturadas = [linha for linha in linhas if linha["cobertura"] >= 60]
    if saturadas:
        achados.append(
            finding(
                "nice",
                "dimensao-saturada",
                "Dimensão presente em mais de 60% do catálogo",
                ", ".join(linha["dimensao"] for linha in saturadas[:3]),
                "Quase toda descrição toca a dimensão: o léxico dela é amplo demais.",
                "Dimensão saturada não distingue skill nenhuma.",
                "Use uma palavra mais específica do que a dimensão para buscar.",
                "O filtro por dimensão deixa de filtrar.",
            )
        )
    if len(dimensoes_brief) == 1:
        achados.append(
            finding(
                "nice",
                "brief-estreito",
                "Briefing toca uma dimensão só",
                next(iter(dimensoes_brief)),
                "Um pedido de uma dimensão raramente é um projeto inteiro.",
                "Cobrir só a dimensão citada deixa o resto sem plano.",
                "Confirme se as outras dimensões são fora de escopo.",
                "O plano termina na metade do trabalho.",
            )
        )

    findings, counts, veredito, perguntas = finalize(
        achados,
        modo,
        [
            "A dimensão sem skill é lacuna real ou o catálogo usa outro vocabulário?",
            "A dimensão escassa tem uma skill boa ou apenas a única disponível?",
            "Quem executa as dimensões que o catálogo não cobre?",
        ],
    )
    metrics = {
        "entradas": total,
        "dimensoes": len(linhas),
        "cobertas": len(linhas) - len(lacunas),
        "lacunas": len(lacunas),
        "media": round(sum(linha["cobertura"] for linha in linhas) / len(linhas), 1) if linhas else 0.0,
    }
    summary = [
        f"{metrics['cobertas']} de {len(linhas)} dimensão(ões) do briefing têm candidata; média de {metrics['media']}% do catálogo por dimensão.",
    ]
    limitations = [
        "Cobertura é contagem de entradas que mencionam a dimensão, não de entradas boas para ela.",
        "O léxico da dimensão é fixo: sinônimo fora da lista não é contado.",
        *avisos,
        "A melhor candidata por dimensão é a de maior BM25 contra as palavras da dimensão, não contra o seu contexto.",
    ]
    return common(
        analysis="selecao.cobertura",
        mode=modo,
        title="Cobertura do catálogo",
        summary=summary,
        findings=findings,
        counts=counts,
        verdict=veredito,
        questions=perguntas,
        rows=linhas,
        metrics=metrics,
        limitations=limitations,
    )
