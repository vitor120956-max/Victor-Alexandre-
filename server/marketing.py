"""Marketing mensurável — funil, poder estatístico, campanha, e-mail, SEO e anúncio.

Inspirado em `coreyhaines31/marketingskills` (MIT, © 2025 Corey Haines). O upstream
é uma biblioteca de 52 skills em markdown, escritas para um agente redigir plano,
copy e criativo. Isso não cabe aqui: o JARVIS não gera texto de marketing. O que
esta adaptação implementa é a parte que se **mede** — a conta do funil, o poder
do teste, a higiene da URL de campanha, o que um e-mail carrega, o que a página
declara ao buscador e o que cabe no limite da plataforma de anúncio.

Tudo é estático e determinístico: nenhuma plataforma é consultada, nenhum dado de
conta é lido, nenhum arquivo é gravado. As faixas de sanidade não são benchmarks
de mercado — são limites que separam conta plausível de erro de digitação.
"""
from __future__ import annotations

import json
import math
import re
import statistics
import unicodedata
from html.parser import HTMLParser
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from .review import common, finalize, finding

VERSAO = "0.26.0"
MAX_TEXTO = 200_000
MAX_URLS = 60

# --------------------------------------------------------------- limites

PLATAFORMAS: dict[str, dict[str, Any]] = {
    "google": {
        "nome": "Google Ads — anúncio responsivo de pesquisa",
        "campos": {
            "titulos": {"limite": 30, "minimo": 3, "maximo": 15, "rotulo": "Título"},
            "descricoes": {"limite": 90, "minimo": 2, "maximo": 4, "rotulo": "Descrição"},
        },
        "nota": "O Google combina até 3 títulos e 2 descrições; qualquer um pode aparecer em qualquer posição.",
    },
    "meta": {
        "nome": "Meta Ads — feed",
        "campos": {
            "texto_principal": {"limite": 125, "minimo": 1, "maximo": 1, "rotulo": "Texto principal"},
            "titulos": {"limite": 40, "minimo": 1, "maximo": 1, "rotulo": "Título"},
            "descricoes": {"limite": 30, "minimo": 0, "maximo": 1, "rotulo": "Descrição"},
        },
        "nota": "O texto principal é truncado por volta de 125 caracteres; em Stories e Reels, abaixo de 72.",
    },
    "linkedin": {
        "nome": "LinkedIn Ads — feed",
        "campos": {
            "texto_principal": {"limite": 150, "minimo": 1, "maximo": 1, "rotulo": "Texto de introdução"},
            "titulos": {"limite": 70, "minimo": 1, "maximo": 1, "rotulo": "Título"},
            "descricoes": {"limite": 100, "minimo": 0, "maximo": 1, "rotulo": "Descrição"},
        },
        "nota": "A introdução é truncada por volta de 150 caracteres; o restante fica atrás de “ver mais”.",
    },
}

MEDIUMS = (
    "cpc", "ppc", "paid-social", "display", "email", "newsletter", "social", "organic-social",
    "creator", "podcast", "affiliate", "community", "referral", "event", "print", "video",
    "retargeting", "influencer", "partner", "qr", "direct",
)

CURTOS = re.compile(r"^(bit\.ly|goo\.gl|t\.co|tinyurl\.com|ow\.ly|is\.gd|buff\.ly|rebrand\.ly)$", re.I)
EMAIL = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
TELEFONE = re.compile(r"(?:\+55[\s-]?)?\(\d{2}\)[\s-]?9?\d{4}[\s-]?\d{4}|\+55[\s-]?\d{2}[\s-]?9?\d{4}[\s-]?\d{4}|(?<!\d)9?\d{4}-\d{4}(?!\d)")
NAO_ASCII = re.compile(r"[^\x00-\x7F]")
ESPACO = re.compile(r"\s+")

SPAM = (
    "100% grátis", "100% gratis", "garantia de dinheiro", "dinheiro fácil", "dinheiro facil",
    "ganhe dinheiro", "renda extra garantida", "clique aqui agora", "última chance", "ultima chance",
    "compre agora", "sem risco", "risco zero", "milagre", "segredo revelado", "você foi selecionado",
    "voce foi selecionado", "parabéns você", "parabens voce", "promoção imperdível", "promocao imperdivel",
)

GENERICOS_ALT = ("imagem", "imagem do produto", "foto", "foto do produto", "image", "picture", "img", "banner", "logo")

TITULO_OK = (50, 60)
DESCRICAO_OK = (150, 160)

TEXTO_IA = (
    ("contraste", re.compile(r"\b(não é|nao e|não são|nao sao)\b[^.!?]{3,80}\b(mas|e sim|é|e)\b", re.I)),
    ("pergunta-respondida", re.compile(r"\b(o resultado|a melhor parte|o segredo|a verdade)\s*\?\s*[A-ZÀ-Ú]", re.I)),
    ("frase-de-efeito", re.compile(r"\b(say goodbye to|diga adeus a|chega de|unlock the power|libere o poder|"
                                   r"take it to the next level|levar ao próximo nível|levar ao proximo nivel|"
                                   r"here's the thing|a questão é|a questao e)\b", re.I)),
    ("abertura-de-envelope", re.compile(r"\b(espero que (este|essa) e-?mail|hope this email finds you well|"
                                        r"só passando para|so passando para|just checking in|great news!|"
                                        r"boa notícia!|boa noticia!)\b", re.I)),
    ("isca-de-assunto", re.compile(r"^\s*(re|fwd|fw)\s*:", re.I)),
    ("caixa-de-urgência", re.compile(r"\b(você não vai acreditar|voce nao vai acreditar|you won'?t believe|"
                                     r"🔥|🚨|urgente!!)\b", re.I)),
)

RECOMENDACAO_FORCADA = (
    ("melhor-da-categoria", re.compile(r"\b(o|a) melhor\b", re.I)),
    ("recomendado-sem-alternativa", re.compile(r"\b(recomendamos|recomendo|use|escolha)\s+[A-Z][\w.-]+", re.I)),
    ("substitua", re.compile(r"\b(use|prefira)\s+[\w.-]+\s+(em vez de|instead of|no lugar de)\b", re.I)),
    ("numero-um", re.compile(r"(#1|número 1|numero 1|nº ?1|n\.?1\b)", re.I)),
    ("garantia", re.compile(r"\b(garantido|garantia de \d|garantia incondicional|100% (seguro|eficaz|comprovado))\b", re.I)),
    ("superlativo", re.compile(r"\b(revolucionári[oa]|revolucionari[oa]|líder de mercado|lider de mercado|"
                               r"incomparável|incomparavel|definitiv[oa]|imbatível|imbatibel|"
                               r"world[- ]class|best[- ]in[- ]class|game[- ]?changer)\b", re.I)),
)


class MarketingError(ValueError):
    """Entrada inválida; a API devolve 200 com `ok:false` e a mensagem do erro."""


# --------------------------------------------------------------- utilidades

def _norm(valor: str) -> str:
    base = "".join(c for c in unicodedata.normalize("NFD", str(valor)) if unicodedata.category(c) != "Mn")
    return base.casefold().strip()


def _contem(valor: str, termo: str) -> bool:
    """Casamento por palavra inteira, insensível a acento e caixa."""
    alvo = _norm(valor)
    procurado = _norm(termo)
    if not procurado:
        return False
    return re.search(rf"(?<![0-9a-z]){re.escape(procurado)}(?![0-9a-z])", alvo) is not None


def _num(valor: float, casas: int = 0) -> str:
    texto = f"{valor:,.{casas}f}"
    return texto.replace(",", "\0").replace(".", ",").replace("\0", ".")


def _brl(valor: float, casas: int = 2) -> str:
    return f"R$ {_num(valor, casas)}"


def _pct(valor: float, casas: int = 2) -> str:
    return f"{_num(valor, casas)}%"


def _n(total: float, um: str, muitos: str) -> str:
    return f"{_num(total, 0)} {um if round(total) == 1 else muitos}"


def _texto(valor: Any) -> str:
    return "" if valor is None else str(valor).strip()


def _linhas(valor: str) -> list[str]:
    return [linha.strip() for linha in valor.splitlines() if linha.strip()]


def _frases(texto: str) -> list[str]:
    partes = re.split(r"(?<=[.!?])\s+", texto.strip())
    return [parte for parte in partes if parte.strip()]


def _palavras(texto: str) -> list[str]:
    return [palavra for palavra in re.findall(r"[0-9A-Za-zÀ-ÿ'-]+", _norm(texto)) if len(palavra) > 2]


def _similaridade(a: str, b: str) -> float:
    """Quanto do menor texto cabe no maior: 1,0 quando um repete o outro."""
    va, vb = set(_palavras(a)), set(_palavras(b))
    if not va or not vb:
        return 0.0
    return len(va & vb) / min(len(va), len(vb))


# --------------------------------------------------------------- 1. orçamento

def calcular_orcamento(
    *,
    orcamento: float,
    cpm: float,
    ctr: float,
    cvr: float,
    fechamento: float,
    ticket: float,
    margem: float,
    modelo: str = "assinatura",
    vida_util_meses: float = 0,
    cac_alvo: float = 0,
    meta_arr: float = 0,
    arpc: float = 0,
    retencao_anual: float = 0,
    moeda: str = "BRL",
    modo: str = "full",
) -> dict[str, Any]:
    if orcamento <= 0:
        raise MarketingError("O orçamento mensal precisa ser maior que zero.")
    if cpm <= 0:
        raise MarketingError("O CPM precisa ser maior que zero; sem ele não há impressão.")
    if ctr <= 0 or ctr > 100:
        raise MarketingError("O CTR é percentual: precisa ficar entre 0 e 100.")
    if cvr <= 0 or cvr > 100:
        raise MarketingError("A conversão de clique em lead é percentual: entre 0 e 100.")
    if fechamento <= 0 or fechamento > 100:
        raise MarketingError("A taxa de fechamento é percentual: entre 0 e 100.")
    if ticket <= 0:
        raise MarketingError("O ticket precisa ser maior que zero.")
    if margem <= 0 or margem > 100:
        raise MarketingError("A margem é percentual: entre 0 e 100.")
    if modelo not in {"assinatura", "unica"}:
        raise MarketingError("`modelo` aceita `assinatura` ou `unica`.")
    if moeda not in {"BRL", "USD", "EUR"}:
        raise MarketingError("`moeda` aceita BRL, USD ou EUR.")

    impressoes = orcamento / cpm * 1000
    cliques = impressoes * ctr / 100
    leads = cliques * cvr / 100
    clientes = leads * fechamento / 100
    cac = orcamento / clientes if clientes else math.inf
    receita = clientes * ticket
    roas = receita / orcamento
    retorno_cliente = ticket * margem / 100
    payback = cac / retorno_cliente if retorno_cliente else math.inf
    ltv = retorno_cliente * vida_util_meses if (vida_util_meses > 0 and modelo == "assinatura") else retorno_cliente
    ltv_cac = ltv / cac if cac and math.isfinite(cac) else 0.0

    simbolo = {"BRL": "R$", "USD": "US$", "EUR": "€"}[moeda]

    def dinheiro(valor: float, casas: int = 2) -> str:
        if not math.isfinite(valor):
            return "—"
        return f"{simbolo} {_num(valor, casas)}"

    achados: list[dict[str, Any]] = []
    if ctr > 10:
        achados.append(finding(
            "should", "ctr-alto", "CTR acima do plausível", _pct(ctr),
            "CTR mede clique sobre impressão, não clique sobre sessão.",
            "Acima de 10% costuma ser clique em qualquer elemento da página, ou impressão contada como sessão.",
            "Confirme a fonte do número antes de projetar receita com ele.",
            "A projeção fica otimista por um fator de 5 a 20.",
        ))
    if cvr > 60:
        achados.append(finding(
            "should", "cvr-alto", "Conversão de clique em lead acima do plausível", _pct(cvr),
            "A conversão de clique em lead raramente passa de 60%.",
            "Valor alto sugere formulário contando visita, ou bot sem filtro.",
            "Verifique o evento de conversão antes de usar o número.",
            "O funil promete leads que não existem.",
        ))
    if not math.isfinite(cac):
        achados.append(finding(
            "must", "sem-clientes", "O funil não fecha nenhum cliente", "0",
            "Com esse orçamento e essas taxas, nenhum cliente sai do funil no mês.",
            "CAC infinito não é plano: é sinal de que uma das taxas está errada ou o orçamento é baixo demais.",
            "Reveja CPM, CTR, conversão e fechamento, ou aumente o orçamento.",
            "Nenhuma decisão de mídia pode ser tomada.",
        ))
    elif ltv_cac < 1:
        achados.append(finding(
            "must", "cac-acima-do-ltv", "CAC maior que o retorno do cliente", f"{_num(ltv_cac, 2)}×",
            "O retorno por cliente é o ticket vezes a margem (vezes a vida útil, no plano de assinatura).",
            "Cada cliente novo destrói margem.",
            "Suba o ticket, melhore a margem, aumente a retenção ou corte o CAC.",
            "Crescer acelera o prejuízo.",
        ))
    elif ltv_cac < 3:
        achados.append(finding(
            "should", "ltv-cac-baixo", "Relação LTV/CAC abaixo de 3", f"{_num(ltv_cac, 2)}×",
            "A faixa saudável de SaaS fica em 3× ou mais.",
            "Pouca folga para erro de mídia e custo fixo.",
            "Melhore retenção ou reduza o CAC antes de escalar.",
            "O canal não paga o próprio crescimento.",
        ))
    else:
        achados.append(finding(
            "nice", "ltv-cac-ok", "Relação LTV/CAC saudável", f"{_num(ltv_cac, 2)}×",
            "Retorno por cliente bem acima do custo de aquisição.",
            "Nenhum: a folga existe.",
            "Escale com orçamento de teste antes de dobrar a mídia.",
            "Nada.",
        ))
    if math.isfinite(payback) and payback > 12:
        achados.append(finding(
            "should", "payback-longo", "Payback acima de 12 meses", f"{_num(payback, 1)} meses",
            "Payback é o tempo até o retorno do cliente cobrir o CAC.",
            "Caixa preso por mais de um ano limita o quanto você consegue investir.",
            "Encurte o ciclo, cobre anual antecipado ou reduza o CAC.",
            "O crescimento depende de capital externo.",
        ))
    if roas < 1:
        achados.append(finding(
            "must", "roas-abaixo-de-1", "ROAS abaixo de 1", f"{_num(roas, 2)}×",
            "ROAS é receita sobre investimento, não lucro.",
            "A mídia devolve menos receita do que custou.",
            "Corrija ticket, conversão ou custo antes de manter a verba.",
            "O canal queima caixa.",
        ))
    elif roas >= 3:
        achados.append(finding(
            "nice", "roas-alto", "ROAS acima de 3", f"{_num(roas, 2)}×",
            "Receita de três vezes o investimento.",
            "Nenhum.",
            "Teste o próximo canal com 10–20% da verba antes de migrar tudo.",
            "Nada.",
        ))
    if margem < 30:
        achados.append(finding(
            "should", "margem-baixa", "Margem abaixo de 30%", _pct(margem),
            "A margem define quanto sobra para pagar mídia, time e ferramenta.",
            "Com margem baixa, o mesmo CAC pesa muito mais.",
            "Reveja preço ou custo antes de escalar aquisição.",
            "O canal parece lucrativo no ROAS e não é no caixa.",
        ))

    # --- sensibilidade ao CAC alvo
    sensibilidade: list[dict[str, Any]] = []
    if cac_alvo > 0 and math.isfinite(cac) and cac > 0:
        ctr_necessario = ctr * cac / cac_alvo
        cvr_necessario = cvr * cac / cac_alvo
        fechamento_necessario = fechamento * cac / cac_alvo
        sensibilidade = [
            {"alavanca": "CTR", "atual": _pct(ctr), "necessario": _pct(ctr_necessario), "delta": _pct(ctr_necessario - ctr)},
            {"alavanca": "Conversão de clique em lead", "atual": _pct(cvr), "necessario": _pct(cvr_necessario), "delta": _pct(cvr_necessario - cvr)},
            {"alavanca": "Fechamento", "atual": _pct(fechamento), "necessario": _pct(fechamento_necessario), "delta": _pct(fechamento_necessario - fechamento)},
        ]
        if cac > cac_alvo:
            achados.append(finding(
                "should", "cac-alvo-distante", "CAC acima do alvo", f"{dinheiro(cac)} contra {dinheiro(cac_alvo)}",
                "A alavanca mostra quanto cada taxa precisaria subir, sozinha, para chegar ao alvo.",
                f"Para bater o alvo só com CTR, ele teria que ir de {_pct(ctr)} para {_pct(ctr_necessario)}.",
                "Escolha a alavanca com folga real; não presuma as três ao mesmo tempo.",
                "A meta vira desejo sem plano.",
            ))

    # --- orçamento por meta de ARR
    meta: dict[str, Any] = {}
    if meta_arr > 0 or arpc > 0 or retencao_anual > 0:
        if meta_arr <= 0 or arpc <= 0 or retencao_anual <= 0 or not math.isfinite(cac):
            raise MarketingError("Para o orçamento por meta, informe `meta_arr`, `arpc`, `retencao_anual` e um CAC finito.")
        if retencao_anual > 100:
            raise MarketingError("A retenção anual é percentual: entre 0 e 100.")
        novos_clientes = meta_arr / (arpc * 12)
        orcamento_meta = (novos_clientes * cac) / (retencao_anual / 100)
        meta = {
            "novos_clientes": round(novos_clientes, 2),
            "orcamento_necessario": round(orcamento_meta, 2),
            "informado": round(orcamento, 2),
            "gap": round(orcamento_meta - orcamento, 2),
        }
        if orcamento_meta > orcamento * 1.2:
            achados.append(finding(
                "should", "meta-sem-verba", "A meta de ARR pede mais verba", f"{dinheiro(orcamento_meta)} por mês",
                "Orçamento por meta = (novos clientes × CAC) ÷ retenção anual, com clientes novos = ARR ÷ (ARPC × 12).",
                f"Faltam {dinheiro(orcamento_meta - orcamento)} por mês para a meta no CAC atual.",
                "Reduza o CAC, aceite prazo maior ou ajuste a meta.",
                "A meta fica no slide e não no plano.",
            ))
        elif orcamento_meta <= orcamento:
            achados.append(finding(
                "nice", "meta-coberta", "A verba cobre a meta", f"{dinheiro(orcamento_meta)} necessários",
                "O orçamento informado é suficiente no CAC atual.",
                "Nenhum.",
                "Reserve 10–20% para o canal seguinte antes de comprometer o resto.",
                "Nada.",
            ))

    perguntas = ["O CAC inclui salário, ferramenta e retainer, ou só mídia?"] if modo == "ultra" else []
    linhas = [
        {"etapa": "Investimento", "numero": dinheiro(orcamento), "formula": "informado"},
        {"etapa": "Impressões", "numero": _num(impressoes), "formula": "orçamento ÷ CPM × 1000"},
        {"etapa": "Cliques", "numero": _num(cliques), "formula": "impressões × CTR"},
        {"etapa": "Leads", "numero": _num(leads), "formula": "cliques × conversão"},
        {"etapa": "Clientes", "numero": _num(clientes, 2), "formula": "leads × fechamento"},
        {"etapa": "CAC", "numero": dinheiro(cac), "formula": "orçamento ÷ clientes"},
        {"etapa": "Receita", "numero": dinheiro(receita), "formula": "clientes × ticket"},
        {"etapa": "ROAS", "numero": f"{_num(roas, 2)}×", "formula": "receita ÷ investimento"},
        {"etapa": "Retorno por cliente", "numero": dinheiro(retorno_cliente), "formula": "ticket × margem"},
        {"etapa": "Payback",
         "numero": f"{_num(payback, 1)} {'meses' if modelo == 'assinatura' else 'vendas'}" if math.isfinite(payback) else "—",
         "formula": "CAC ÷ retorno por cliente"},
        {"etapa": "LTV / CAC", "numero": f"{_num(ltv_cac, 2)}×", "formula": "LTV ÷ CAC"},
    ]
    metrics = {
        "orcamento": round(orcamento, 2), "impressoes": round(impressoes, 2), "cliques": round(cliques, 2),
        "leads": round(leads, 2), "clientes": round(clientes, 3), "cac": None if not math.isfinite(cac) else round(cac, 2),
        "receita": round(receita, 2), "roas": round(roas, 3), "ltv": round(ltv, 2) if math.isfinite(ltv) else None,
        "ltv_cac": round(ltv_cac, 3), "payback_meses": None if not math.isfinite(payback) else round(payback, 2),
        "margem_bruta": round(receita * margem / 100, 2), "modelo": modelo, "moeda": moeda,
    }
    achados, counts, veredito, perguntas = finalize(achados, modo, perguntas)
    extra = ["", "## De onde sai cada número", ""]
    for linha in linhas:
        extra.append(f"- **{linha['etapa']}**: {linha['numero']} — `{linha['formula']}`")
    if sensibilidade:
        extra += ["", "## Sensibilidade ao CAC alvo", "",
                  f"- Alvo: {dinheiro(cac_alvo)}",
                  "", "| Alavanca | Hoje | Necessário | Variação |", "|---|---|---|---|"]
        for item in sensibilidade:
            extra.append(f"| {item['alavanca']} | {item['atual']} | {item['necessario']} | {item['delta']} |")
    if meta:
        extra += ["", "## Orçamento por meta", "",
                  f"- Clientes novos por mês: {_num(meta['novos_clientes'], 2)}",
                  f"- Orçamento necessário: {dinheiro(meta['orcamento_necessario'])}",
                  f"- Informado: {dinheiro(meta['informado'])} · diferença: {dinheiro(meta['gap'])}"]
    extra += ["", "## Faixas usadas", "",
              "- CTR acima de 10% e conversão acima de 60% são tratados como erro de medição, não como bom desempenho.",
              "- LTV/CAC saudável começa em 3×; payback acima de 12 meses é sinal de caixa preso.",
              "- Essas faixas são limites de sanidade. Não são benchmark de mercado e não substituem o seu histórico.",
              ""]
    return {
        **common(
            analysis="marketing.orcamento",
            mode=modo,
            title="Plano de mídia e economia unitária",
            summary=[
                f"{dinheiro(orcamento)} por mês em {moeda} com CPM de {dinheiro(cpm)}.",
                f"O funil entrega {_n(leads, 'lead', 'leads')} e {_num(clientes, 2)} clientes por mês.",
                f"CAC de {dinheiro(cac)}, ROAS de {_num(roas, 2)}× e payback de "
                f"{_num(payback, 1) if math.isfinite(payback) else '—'} {'meses' if modelo == 'assinatura' else 'vendas'}.",
            ],
            findings=achados,
            counts=counts,
            verdict=veredito,
            questions=perguntas,
            rows=linhas,
            metrics=metrics,
            limitations=LIMITES_ORCAMENTO,
            extra_sections=extra,
        ),
        "sensibilidade": sensibilidade,
        "meta": meta,
        "executado": False,
    }


LIMITES_ORCAMENTO = [
    "As taxas são as que você informa; nenhuma conta de anúncio é lida.",
    "O funil é linear: cada etapa só multiplica a anterior, sem saturação, sazonalidade ou fadiga de criativo.",
    "CAC aqui é só mídia. CAC real soma salário, ferramenta, agência e conteúdo.",
    "Payback e LTV usam a margem informada; imposto e custo variável fora da margem mudam a conta.",
]


# --------------------------------------------------------------- 2. teste

def dimensionar_teste(
    *,
    baseline: float,
    mde: float,
    trafego_diario: float,
    variantes: int = 2,
    alfa: float = 0.05,
    poder: float = 0.8,
    exposicao: float = 100,
    tipo: str = "b2c",
    duracao_maxima: int = 56,
    modo: str = "full",
) -> dict[str, Any]:
    if baseline <= 0 or baseline >= 100:
        raise MarketingError("A linha de base é percentual: precisa ficar entre 0 e 100, sem os extremos.")
    if mde <= 0 or mde > 500:
        raise MarketingError("O efeito mínimo (MDE) é relativo e percentual: acima de 0 e até 500.")
    if trafego_diario <= 0:
        raise MarketingError("O tráfego diário precisa ser maior que zero.")
    if variantes < 2 or variantes > 6:
        raise MarketingError("O teste tem de 2 a 6 variantes.")
    if alfa <= 0 or alfa >= 0.5:
        raise MarketingError("O alfa precisa ficar entre 0 e 0,5.")
    if poder <= 0.5 or poder >= 0.999:
        raise MarketingError("O poder precisa ficar entre 50% e 99,9%.")
    if exposicao <= 0 or exposicao > 100:
        raise MarketingError("A exposição é percentual: entre 0 e 100.")
    if tipo not in {"b2c", "b2b"}:
        raise MarketingError("`tipo` aceita `b2c` ou `b2b`.")
    if duracao_maxima < 7 or duracao_maxima > 365:
        raise MarketingError("`duracao_maxima` fica entre 7 e 365 dias.")

    p1 = baseline / 100
    p2 = p1 * (1 + mde / 100)
    if p2 >= 1:
        raise MarketingError("Com esse MDE a variante passaria de 100% de conversão.")
    alfa_ajustado = alfa / (variantes - 1) if variantes > 2 else alfa
    z_alfa = statistics.NormalDist().inv_cdf(1 - alfa_ajustado / 2)
    z_poder = statistics.NormalDist().inv_cdf(poder)
    medio = (p1 + p2) / 2
    n = ((z_alfa * math.sqrt(2 * medio * (1 - medio)) +
          z_poder * math.sqrt(p1 * (1 - p1) + p2 * (1 - p2))) ** 2) / ((p2 - p1) ** 2)
    por_variante = math.ceil(n)
    total = por_variante * variantes
    efetivo = trafego_diario * exposicao / 100
    dias = math.ceil(total / efetivo)
    minimo = 14 if tipo == "b2b" else 7

    achados: list[dict[str, Any]] = []
    if dias > duracao_maxima:
        achados.append(finding(
            "must", "inviavel", "O teste não cabe no prazo", f"{dias} dias",
            f"Precisaria de {_num(total)} unidades para detectar {_pct(mde)} de efeito sobre {_pct(baseline)}.",
            f"Com {_num(efetivo)} unidades por dia, passaria de {duracao_maxima} dias: novelty e sazonalidade contaminam.",
            f"Aumente o MDE para {_pct(mde * math.sqrt(dias / duracao_maxima), 0)} ou aceite mais tráfego.",
            "O resultado chega tarde e já não vale.",
        ))
    if dias < minimo:
        achados.append(finding(
            "should", "curto-demais", "Duração abaixo de um ciclo completo", f"{dias} dias",
            f"{'B2B' if tipo == 'b2b' else 'B2C'} exige ao menos {minimo} dias para cobrir dia de semana e fim de semana.",
            "Amostra suficiente não garante amostra representativa.",
            f"Rode pelo menos {minimo} dias, mesmo que a amostra feche antes.",
            "O efeito medido pode ser efeito do dia.",
        ))
    if mde < 5:
        achados.append(finding(
            "should", "mde-apertado", "Efeito mínimo pequeno demais", _pct(mde),
            "Detectar menos de 5% custa amostra em ordem de grandeza.",
            "O custo do teste cresce ao quadrado quando o efeito encolhe.",
            "Pergunte se um efeito de 5% mudaria a decisão.",
            "O teste nunca termina.",
        ))
    if variantes >= 4:
        achados.append(finding(
            "should", "muitas-variantes", "Muitas variantes para o tráfego", f"{variantes}",
            "Cada variante extra divide o tráfego e exige correção de comparação múltipla.",
            f"O alfa ajustado caiu para {_num(alfa_ajustado, 4)} e a amostra por variante subiu.",
            "Corte para 3 ou 4, ou rode em sequência.",
            "O teste fica sem poder e sem conclusão.",
        ))
    if alfa > 0.1:
        achados.append(finding(
            "should", "alfa-frouxo", "Alfa acima de 10%", _num(alfa, 3),
            "Alfa é a taxa de falso positivo aceita antes do teste.",
            "Acima de 10%, um em cada cinco ‘vencedores’ é ruído.",
            "Use 0,05 ou menos e comprometa-se antes de rodar.",
            "Você promove variante que não ganhou.",
        ))
    if p2 - p1 < 0.002:
        achados.append(finding(
            "nice", "efeito-absoluto-minimo", "Efeito absoluto muito pequeno", f"{_num((p2 - p1) * 100, 3)} p.p.",
            "O MDE relativo vira um efeito absoluto de fração de ponto percentual.",
            "Efeito desse tamanho raramente paga o custo de manutenção da variante.",
            "Confirme se a decisão depende de algo tão pequeno.",
            "O ganho não cobre a complexidade.",
        ))

    perguntas = ["Quem para o teste se uma métrica de guarda piorar?"] if modo == "ultra" else []
    linhas = [
        {"etapa": "Linha de base", "numero": _pct(baseline), "formula": "informado"},
        {"etapa": "Efeito absoluto", "numero": f"{_num((p2 - p1) * 100, 3)} p.p.", "formula": "baseline × MDE"},
        {"etapa": "Alfa ajustado", "numero": _num(alfa_ajustado, 4), "formula": "alfa ÷ (variantes − 1)" if variantes > 2 else "alfa"},
        {"etapa": "Amostra por variante", "numero": _num(por_variante), "formula": "duas proporções, dois lados"},
        {"etapa": "Amostra total", "numero": _num(total), "formula": "por variante × variantes"},
        {"etapa": "Unidades por dia", "numero": _num(efetivo), "formula": "tráfego × exposição"},
        {"etapa": "Duração", "numero": f"{dias} dias", "formula": "total ÷ unidades por dia"},
        {"etapa": "Duração mínima", "numero": f"{minimo} dias", "formula": "ciclo completo do tipo de negócio"},
    ]
    metrics = {
        "por_variante": por_variante, "total": total, "dias": dias, "minimo": minimo,
        "alfa_ajustado": round(alfa_ajustado, 5), "poder": poder, "efeito_absoluto": round((p2 - p1) * 100, 4),
        "efetivo_dia": round(efetivo, 2), "viavel": dias <= duracao_maxima, "variantes": variantes,
    }
    achados, counts, veredito, perguntas = finalize(achados, modo, perguntas)
    extra = ["", "## A conta", "",
             f"- p1 = {_num(p1, 4)} · p2 = {_num(p2, 4)} · p̄ = {_num(medio, 4)}",
             f"- z(1 − α/2) = {_num(z_alfa, 3)} · z(poder) = {_num(z_poder, 3)}",
             "- n = ((z_α·√(2p̄(1−p̄)) + z_β·√(p1(1−p1)+p2(1−p2)))²) ÷ (p2−p1)²",
             "", "## Antes de rodar", "",
             "- Comprometa a amostra e a regra de parada **antes** de olhar o resultado.",
             "- Olhar todo dia e parar no primeiro cruzamento de 95% transforma o alfa declarado em outro número.",
             "- Métrica primária, secundárias e de guarda definidas com o mesmo cuidado.",
             ""]
    return {
        **common(
            analysis="marketing.teste",
            mode=modo,
            title="Desenho do teste A/B",
            summary=[
                f"{_num(por_variante)} unidades por variante para detectar {_pct(mde)} sobre {_pct(baseline)}.",
                f"{_num(total)} no total, {dias} dias com {_num(efetivo)} unidades por dia.",
                f"Alfa de {_num(alfa, 3)} e poder de {_pct(poder * 100, 0)}.",
            ],
            findings=achados,
            counts=counts,
            verdict=veredito,
            questions=perguntas,
            rows=linhas,
            metrics=metrics,
            limitations=LIMITES_TESTE,
            extra_sections=extra,
        ),
        "executado": False,
    }


LIMITES_TESTE = [
    "A conta é de duas proporções, dois lados, com amostras independentes e iguais.",
    "Nada é calculado sobre dados reais: a linha de base e o MDE são os que você informa.",
    "O teste de uma variável por vez, com usuário fixo na mesma variante, é premissa — não é verificado aqui.",
    "Testes sequenciais e bayesianos têm outra regra de parada e não são cobertos por este alfa.",
]


# --------------------------------------------------------------- 3. UTM

def auditar_utm(*, urls: str, modo: str = "full") -> dict[str, Any]:
    lista = _linhas(urls)
    if not lista:
        raise MarketingError("Cole ao menos uma URL.")
    if len(lista) > MAX_URLS:
        raise MarketingError(f"No máximo {MAX_URLS} URLs por vez.")
    achados: list[dict[str, Any]] = []
    linhas: list[dict[str, Any]] = []
    vistas: set[str] = set()

    for bruta in lista:
        inicio = len(achados)
        if len(bruta) > 2_000:
            raise MarketingError(f"URL longa demais: {bruta[:60]}…")
        url = bruta.strip()
        local = url[:90] + ("…" if len(url) > 90 else "")
        partes = urlsplit(url)
        if partes.scheme not in {"http", "https"}:
            achados.append(finding(
                "must", "sem-esquema", "URL sem https", local,
                "Toda URL de campanha começa com `https://`.",
                "Sem esquema, o link não abre ou abre em http e perde o referenciador.",
                "Use a URL canônica com https.",
                "O clique não é medido.",
            ))
            linhas.append({"url": local, "source": "", "medium": "", "campaign": "", "status": "inválida"})
            continue
        if partes.scheme == "http":
            achados.append(finding(
                "should", "http", "URL em http", local,
                "HTTPS evita perda de referenciador.",
                "Navegador moderno corta o referrer ao sair de http para https.",
                "Troque para https.",
                "Parte da atribuição desaparece.",
            ))
        if ESPACO.search(url):
            achados.append(finding(
                "must", "espaco", "URL com espaço", local,
                "Espaço em URL quebra o link em e-mail e em Markdown.",
                "O cliente de e-mail corta a URL no primeiro espaço.",
                "Codifique como %20 ou, melhor, use hífen no valor.",
                "O clique vai para uma página quebrada.",
            ))
        if partes.fragment:
            achados.append(finding(
                "should", "fragmento", "Fragmento depois dos parâmetros", local,
                "O fragmento vem por último e não é enviado ao servidor.",
                "Alguns relatórios ignoram tudo que vem depois do `#`.",
                "Mova os parâmetros para antes do fragmento.",
                "Parte do tráfego some do relatório.",
            ))
        if CURTOS.match(partes.hostname or ""):
            achados.append(finding(
                "should", "encurtador", "Encurtador no lugar da URL final", local,
                "Encurtador esconde o destino e pode reescrever parâmetros.",
                "O destino real fica opaco e o redirecionamento pode descartar a UTM.",
                "Use a URL final; encurtador só para exibição.",
                "A atribuição depende de quem encurtou.",
            ))

        pares = parse_qsl(partes.query, keep_blank_values=True)
        chaves = [chave for chave, _ in pares]
        repetidas = sorted({chave for chave in chaves if chaves.count(chave) > 1})
        if repetidas:
            achados.append(finding(
                "must", "chave-repetida", "Parâmetro repetido", ", ".join(repetidas),
                "Cada parâmetro aparece uma vez.",
                "Com duas ocorrências, o relatório escolhe uma e a outra desaparece sem aviso.",
                "Deixe só a ocorrência correta.",
                "Duas verdades para o mesmo clique.",
            ))

        valores = {chave: valor for chave, valor in pares}
        faltando = [chave for chave in ("utm_source", "utm_medium", "utm_campaign") if not valores.get(chave, "").strip()]
        if faltando:
            achados.append(finding(
                "must", "utm-incompleta", "Campanha sem os três parâmetros obrigatórios", ", ".join(faltando),
                "`utm_source`, `utm_medium` e `utm_campaign` são o mínimo para o relatório agrupar.",
                "Sem um dos três, GA4 manda o tráfego para `(not set)` ou para `direct`.",
                "Preencha os três antes de publicar.",
                "O canal some do relatório.",
            ))
        if not pares:
            achados.append(finding(
                "must", "sem-utm", "URL sem nenhum parâmetro de campanha", local,
                "Campanha paga e parceria precisam de UTM.",
                "Sem parâmetro, o tráfego entra como direto ou como referenciador genérico.",
                "Adicione source, medium e campaign.",
                "Não há como separar o canal.",
            ))

        for chave, valor in pares:
            if EMAIL.search(valor):
                achados.append(finding(
                    "must", "pii-email", "E-mail dentro da URL", f"{chave}={valor[:40]}",
                    "Nenhum dado pessoal entra em parâmetro de campanha.",
                    "A URL fica em log de servidor, em relatório e em histórico do navegador.",
                    "Use um identificador opaco, nunca o e-mail.",
                    "Vazamento de dado pessoal em relatório de marketing.",
                ))
            elif TELEFONE.search(valor):
                achados.append(finding(
                    "must", "pii-telefone", "Telefone dentro da URL", f"{chave}={valor[:40]}",
                    "Nenhum dado pessoal entra em parâmetro de campanha.",
                    "O número fica exposto em log e em relatório.",
                    "Use um identificador opaco.",
                    "Vazamento de dado pessoal.",
                ))
            if valor != valor.lower():
                achados.append(finding(
                    "should", "maiuscula", "Valor com maiúscula", f"{chave}={valor}",
                    "GA4 trata maiúscula e minúscula como valores diferentes.",
                    "`LinkedIn` e `linkedin` viram duas origens que nunca se juntam.",
                    "Padronize tudo em minúsculas.",
                    "O relatório se divide em dois canais.",
                ))
            if "_" in valor or "+" in valor or ESPACO.search(valor) or NAO_ASCII.search(valor):
                achados.append(finding(
                    "should", "separador", "Separador fora do padrão", f"{chave}={valor}",
                    "O padrão da casa é hífen; acento e espaço pedem codificação.",
                    "Cada variação de escrita vira uma linha nova no relatório.",
                    "Use minúsculas com hífen, sem acento.",
                    "A série histórica se fragmenta.",
                ))
            if chave == "utm_source" and "." in valor:
                achados.append(finding(
                    "should", "origem-dominio", "Origem escrita como domínio", f"{chave}={valor}",
                    "`utm_source` nomeia quem mandou o tráfego, não o endereço.",
                    "`linkedin.com` e `linkedin` viram origens distintas.",
                    "Use o nome curto: `linkedin`, `google`, `newsletter`.",
                    "A mesma origem aparece duas vezes.",
                ))
            if chave == "utm_medium" and valor and _norm(valor) not in MEDIUMS:
                achados.append(finding(
                    "nice", "medium-novo", "Medium fora do vocabulário", f"{valor}",
                    "O vocabulário de medium é o que permite agrupar em canal.",
                    "Um medium inventado cai em `Unassigned` no GA4.",
                    "Use um medium conhecido ou cadastre o agrupamento.",
                    "O canal aparece como não atribuído.",
                ))
            if len(valor) > 60:
                achados.append(finding(
                    "nice", "valor-longo", "Valor longo demais", f"{chave}: {len(valor)} caracteres",
                    "Valor de campanha é para leitura humana no relatório.",
                    "Valor longo é truncado na exibição e não ajuda ninguém.",
                    "Reduza a 40 caracteres ou menos.",
                    "O relatório fica ilegível.",
                ))

        source = valores.get("utm_source", "")
        medium = valores.get("utm_medium", "")
        campaign = valores.get("utm_campaign", "")
        if not valores.get("utm_content"):
            achados.append(finding(
                "nice", "sem-content", "Sem `utm_content`", local,
                "`utm_content` separa posicionamento dentro da mesma campanha.",
                "Duas peças na mesma campanha ficam indistinguíveis.",
                "Use `utm_content` com o posicionamento: `hero-cta`, `rodape`, `stories`.",
                "Não dá para comparar criativo.",
            ))

        canonical = _reconstruir(partes, pares)
        if canonical in vistas:
            achados.append(finding(
                "should", "duplicada", "URL repetida na lista", local,
                "Uma linha por posicionamento.",
                "A mesma URL em duas linhas soma clique em dobro na conferência.",
                "Remova a duplicata.",
                "A contagem de placements mente.",
            ))
        vistas.add(canonical)
        novos = achados[inicio:]
        linhas.append({
            "url": local, "source": source, "medium": medium, "campaign": campaign,
            "canonica": canonical[:110] + ("…" if len(canonical) > 110 else ""),
            "status": "ok" if all(item["group"] == "nice" for item in novos) else "corrigir",
        })

    metrics = {
        "urls": len(lista),
        "ok": sum(1 for linha in linhas if linha["status"] == "ok"),
        "corrigir": sum(1 for linha in linhas if linha["status"] != "ok"),
        "achados": len(achados),
    }
    perguntas = ["Quem mantém a lista de valores aceitos de `utm_source`?"] if modo == "ultra" else []
    achados, counts, veredito, perguntas = finalize(achados, modo, perguntas)
    extra = ["", "## Convenção da casa", "",
             "- minúsculas, com hífen, sem acento e sem espaço;",
             "- `utm_source` é quem mandou (`linkedin`, `newsletter`, `parceiro-x`);",
             "- `utm_medium` é o tipo de acordo (`cpc`, `newsletter`, `creator`, `podcast`, `affiliate`, `community`);",
             "- `utm_campaign` agrupa no tempo (`parceiro-publicacao-2026-10`);",
             "- `utm_content` separa posicionamento; `utm_term` só em busca paga;",
             "- nenhum dado pessoal em nenhum campo.", "",
             "Mediums aceitos: " + ", ".join(f"`{item}`" for item in MEDIUMS) + ".", ""]
    return {
        **common(
            analysis="marketing.utm",
            mode=modo,
            title="Higiene de campanha",
            summary=[
                f"{_n(len(lista), 'URL conferida', 'URLs conferidas')}: {metrics['ok']} prontas, {metrics['corrigir']} para corrigir.",
                "A URL canônica de cada linha volta normalizada em minúsculas com hífen.",
                "Nenhum relatório é consultado: a conferência é do texto da URL.",
            ],
            findings=achados,
            counts=counts,
            verdict=veredito,
            questions=perguntas,
            rows=linhas,
            metrics=metrics,
            limitations=LIMITES_UTM,
            extra_sections=extra,
        ),
        "executado": False,
    }


def _reconstruir(partes: Any, pares: list[tuple[str, str]]) -> str:
    normal: list[tuple[str, str]] = []
    for chave, valor in pares:
        limpo = _norm(valor).replace("_", "-").replace("+", "-")
        limpo = re.sub(r"\s+", "-", limpo)
        limpo = re.sub(r"-{2,}", "-", limpo).strip("-")
        normal.append((chave.lower(), limpo))
    return urlunsplit((partes.scheme, partes.netloc.lower(), partes.path, urlencode(normal), ""))


LIMITES_UTM = [
    "A conferência é sintática: não abre o link, não segue redirecionamento e não confirma que o destino preserva os parâmetros.",
    "O vocabulário de medium é sugestão; agrupamento de canal no GA4 é configuração, não texto.",
    "Dado pessoal só é detectado por padrão de e-mail e de telefone; nome próprio escapa.",
]


# --------------------------------------------------------------- 4. e-mail

def auditar_email(
    *,
    assunto: str,
    corpo: str,
    preview: str = "",
    cta: str = "",
    tipo: str = "lifecycle",
    html: str = "",
    modo: str = "full",
) -> dict[str, Any]:
    if tipo not in {"lifecycle", "cold"}:
        raise MarketingError("`tipo` aceita `lifecycle` ou `cold`.")
    assunto, corpo, preview, cta = assunto.strip(), corpo.strip(), preview.strip(), cta.strip()
    if not assunto:
        raise MarketingError("O assunto é obrigatório.")
    if len(corpo) < 20:
        raise MarketingError("O corpo precisa de ao menos 20 caracteres.")
    if len(corpo) > 20_000 or len(html) > MAX_TEXTO:
        raise MarketingError("Texto acima do limite de leitura.")

    achados: list[dict[str, Any]] = []
    frio = tipo == "cold"
    links = re.findall(r"https?://[^\s)>\]]+", corpo + " " + html)

    if len(assunto) > 80:
        achados.append(finding(
            "must", "assunto-longo", "Assunto acima de 80 caracteres", f"{len(assunto)}",
            "O assunto ideal fica entre 40 e 60 caracteres; 80 é o teto do corte no celular.",
            "Assunto cortado perde justamente o fim, onde fica a promessa.",
            "Reescreva para caber em 60.",
            "O leitor vê reticências.",
        ))
    elif len(assunto) > 60 or len(assunto) < 25:
        achados.append(finding(
            "should", "assunto-fora-da-faixa", "Assunto fora da faixa de leitura", f"{len(assunto)}",
            "Entre 40 e 60 caracteres o assunto cabe inteiro na maioria dos clientes.",
            "Curto demais desperdiça espaço; longo demais é cortado.",
            "Ajuste para 40–60.",
            "O assunto perde força na lista de entrada.",
        ))
    if preview:
        if len(preview) < 40 or len(preview) > 140:
            achados.append(finding(
                "should", "preview-fora-da-faixa", "Pré-cabeçalho fora da faixa", f"{len(preview)}",
                "O pré-cabeçalho completa o assunto e aparece entre 90 e 140 caracteres.",
                "Fora dessa faixa, ele é cortado ou não diz nada.",
                "Ajuste para 90–140.",
                "A segunda linha de decisão é desperdiçada.",
            ))
        if _similaridade(preview, assunto) > 0.6:
            achados.append(finding(
                "should", "preview-repete", "Pré-cabeçalho repete o assunto", preview[:60],
                "O pré-cabeçalho é espaço novo, não eco.",
                "Repetir gasta a segunda chance de convencer.",
                "Use o pré-cabeçalho para a consequência: o que muda se abrir.",
                "A lista de entrada mostra a mesma frase duas vezes.",
            ))
        if "—" in preview or "–" in preview:
            achados.append(finding(
                "nice", "travessao-preview", "Travessão no pré-cabeçalho", preview[:60],
                "O travessão virou marca de texto gerado.",
                "Ele aparece em quase todo e-mail automático de IA.",
                "Troque por dois-pontos ou por ponto final.",
                "O leitor reconhece o padrão.",
            ))
    else:
        achados.append(finding(
            "should", "sem-preview", "Sem pré-cabeçalho", "—",
            "O cliente mostra a primeira linha do corpo quando não há pré-cabeçalho.",
            "O espaço é preenchido por acaso, com “Ver no navegador” ou uma saudação.",
            "Escreva 90–140 caracteres.",
            "A segunda linha de decisão vira ruído.",
        ))

    if "—" in assunto or "–" in assunto:
        achados.append(finding(
            "nice", "travessao-assunto", "Travessão no assunto", assunto[:60],
            "É um dos sinais mais reconhecíveis de texto gerado.",
            "Não estraga a entrega; gasta a credibilidade da linha.",
            "Troque por dois-pontos.",
            "O assunto parece template.",
        ))
    if re.search(r"[\U0001F300-\U0001FAFF\u2600-\u27BF]", assunto):
        achados.append(finding(
            "should", "emoji-assunto", "Emoji no assunto", assunto[:40],
            "Emoji em assunto de ciclo de vida compete com o remetente.",
            "Em cold e-mail, derruba a taxa de abertura em caixa corporativa.",
            "Deixe o assunto em texto.",
            "O e-mail parece promoção.",
        ))
    if frio and re.match(r"^\s*(re|fwd|fw)\s*:", assunto, re.I):
        achados.append(finding(
            "must", "assunto-falso", "“Re:” falso em primeiro contato", assunto,
            "Fingir resposta anterior é isca e quebra a confiança.",
            "O destinatário descobre ao abrir e marca como spam.",
            "Escreva o assunto real.",
            "A reputação do domínio cai.",
        ))
    if assunto.isupper() and len(assunto) > 12:
        achados.append(finding(
            "must", "assunto-caixa-alta", "Assunto em caixa alta", assunto[:40],
            "Caixa alta é o sinal clássico de spam.",
            "Filtro de conteúdo penaliza e o leitor interpreta como grito.",
            "Use caixa de frase.",
            "Entrega e abertura caem juntas.",
        ))
    if assunto.count("!") > 1:
        achados.append(finding(
            "should", "exclamacao", "Exclamação repetida no assunto", assunto[:40],
            "Uma exclamação já é ênfase suficiente.",
            "Duas ou mais pesam no filtro.",
            "Mantenha no máximo uma.",
            "O assunto parece anúncio.",
        ))

    for nome, padrao in TEXTO_IA:
        alvo = assunto if nome == "isca-de-assunto" else corpo
        achado = padrao.search(alvo)
        if not achado:
            continue
        if nome == "contraste":
            achados.append(finding(
                "should", "tell-contraste", "Contraste “não é X, é Y”", achado.group(0)[:60],
                "É a construção mais reconhecível de texto gerado.",
                "Quem lê e-mail automático todos os dias identifica na primeira linha.",
                "Diga Y direto, com o motivo.",
                "O e-mail parece gerado e é ignorado.",
            ))
        elif nome == "abertura-de-envelope":
            achados.append(finding(
                "should", "abertura-generica", "Abertura de envelope", achado.group(0)[:60],
                "A primeira linha precisa ser o motivo do e-mail.",
                "Saudação de cortesia e “só passando” gastam a única linha que quase todos leem.",
                "Abra com o fato que gerou o e-mail.",
                "O leitor fecha antes do primeiro parágrafo.",
            ))
        elif nome == "isca-de-assunto":
            if frio:
                achados.append(finding(
                    "must", "isca", "Assunto com isca de resposta", assunto,
                    "“Re:” e “Fwd:” falsos são isca.",
                    "Quebra a confiança e piora a reputação do domínio.",
                    "Escreva o assunto real.",
                    "O domínio passa a cair em spam.",
                ))
        else:
            achados.append(finding(
                "should", f"tell-{nome}", "Marca de texto gerado", achado.group(0)[:60],
                "Essas construções aparecem em quase todo texto de modelo.",
                "O leitor reconhece o padrão e para de ler.",
                "Reescreva a frase sem a fórmula.",
                "O e-mail é tratado como automático.",
            ))

    negacoes = len(re.findall(r"\b(sem|no|not|nada de)\b[^,.!?]{0,24},", corpo, re.I))
    if negacoes >= 2:
        achados.append(finding(
            "should", "lista-de-negacao", "Lista de negação em sequência", f"{negacoes} ocorrências",
            "“Sem X, sem Y, sem Z” é um padrão de texto gerado.",
            "A frase diz o que não acontece em vez de dizer o que acontece.",
            "Diga o que acontece, uma vez.",
            "O texto soa defensivo e genérico.",
        ))

    for termo in SPAM:
        if _contem(corpo, termo) or _contem(assunto, termo):
            achados.append(finding(
                "must", "spam", "Termo de spam", termo,
                "Filtro de conteúdo pontua esses termos.",
                "A mensagem perde entrega justamente para quem ainda não conhece a marca.",
                "Remova o termo e diga o fato.",
                "Taxa de entrada em spam sobe.",
            ))
            break

    if links and len(links) > (1 if frio else 3):
        achados.append(finding(
            "should", "muitos-links", "Links demais", f"{len(links)}",
            "Um e-mail, um trabalho: um link principal.",
            "Cada link a mais divide a atenção e aumenta o sinal de propaganda." if frio else "Muitos links competem com a ação principal.",
            "Deixe o CTA e, no máximo, um link de contexto.",
            "A taxa de clique no principal cai.",
        ))
    if not links and not cta:
        achados.append(finding(
            "must", "sem-cta", "Sem ação", "—",
            "Todo e-mail pede uma coisa só.",
            "Sem link e sem botão, o e-mail não tem próximo passo.",
            "Escolha a ação e escreva o botão.",
            "O e-mail informa e não move ninguém.",
        ))
    if len(corpo) > 3_000:
        achados.append(finding(
            "should", "longo", "Corpo longo para e-mail", f"{len(corpo)} caracteres",
            "E-mail transacional e de ciclo de vida é lido no celular.",
            "Acima de 3.000 caracteres, a maioria para antes do CTA.",
            "Corte para uma ideia e um pedido.",
            "O CTA não é visto.",
        ))
    paragrafos = [p for p in re.split(r"\n\s*\n", corpo) if p.strip()]
    longos = [p for p in paragrafos if len(_frases(p)) > 5]
    if longos:
        achados.append(finding(
            "should", "paragrafo-longo", "Parágrafo com mais de cinco frases", f"{len(longos)} parágrafo(s)",
            "Um parágrafo de e-mail tem de uma a três frases.",
            "Bloco de texto no celular é pulado.",
            "Quebre em parágrafos curtos.",
            "O meio do e-mail não é lido.",
        ))
    frases = [f for f in _frases(corpo) if len(f.split()) > 45]
    if frases:
        achados.append(finding(
            "nice", "frase-longa", "Frase acima de 45 palavras", frases[0][:70],
            "Frase longa esconde o sujeito e o verbo.",
            "O leitor perde o fio e volta ao começo.",
            "Corte em duas.",
            "A leitura trava.",
        ))

    if frio and not re.search(r"\{\{?\s*\w+|\b(Olá|Ola|Oi|Hello|Hi)\s+[A-ZÀ-Ú]", corpo):
        achados.append(finding(
            "nice", "sem-personalizacao", "Sem sinal de personalização", "—",
            "Cold e-mail sem nenhum elemento do destinatário parece disparo em massa.",
            "A resposta cai e a reclamação sobe.",
            "Use um dado verificável do destinatário, não só o nome.",
            "O e-mail é tratado como lista comprada.",
        ))
    if tipo == "lifecycle" and html and not re.search(r"descadastr|unsubscribe|cancelar (a )?inscri", html, re.I):
        achados.append(finding(
            "must", "sem-descadastro", "HTML sem link de descadastro", "—",
            "E-mail de ciclo de vida precisa de saída visível.",
            "Sem descadastro, a reclamação vira o único caminho de saída.",
            "Inclua o link no rodapé.",
            "Reclamação derruba a entrega do domínio.",
        ))

    metrics = {
        "assunto": len(assunto), "preview": len(preview), "corpo": len(corpo),
        "paragrafos": len(paragrafos), "frases": len(_frases(corpo)), "links": len(links),
        "tipo": tipo, "tells": sum(1 for nome, padrao in TEXTO_IA if padrao.search(corpo if nome != "isca-de-assunto" else assunto)),
    }
    perguntas = ["Quem é o remetente humano que assina este e-mail?"] if modo == "ultra" else []
    achados, counts, veredito, perguntas = finalize(achados, modo, perguntas)
    extra = ["", "## Estrutura mínima", "",
             "1. **Gancho**: a primeira linha é o motivo do e-mail.",
             "2. **Contexto**: por que isso importa para quem recebe.",
             "3. **Valor**: o conteúdo útil, em uma ideia.",
             "4. **Ação**: um pedido, um botão, um link.",
             "5. **Assinatura**: uma pessoa, não uma marca.", "",
             "Assunto 40–60 caracteres · pré-cabeçalho 90–140 · um CTA · parágrafos de 1–3 frases.", ""]
    return {
        **common(
            analysis="marketing.email",
            mode=modo,
            title="E-mail antes do disparo",
            summary=[
                f"{tipo} · assunto de {len(assunto)} caracteres · pré-cabeçalho de {len(preview)}.",
                f"{len(paragrafos)} parágrafo(s), {metrics['frases']} frase(s) e {len(links)} link(s).",
                "O que se mede aqui é o que o filtro e o leitor de celular vão ver.",
            ],
            findings=achados,
            counts=counts,
            verdict=veredito,
            questions=perguntas,
            rows=[
                {"campo": "Assunto", "valor": assunto, "tamanho": len(assunto)},
                {"campo": "Pré-cabeçalho", "valor": preview or "—", "tamanho": len(preview)},
                {"campo": "CTA", "valor": cta or "—", "tamanho": len(cta)},
                {"campo": "Corpo", "valor": f"{len(corpo)} caracteres", "tamanho": len(corpo)},
            ],
            metrics=metrics,
            limitations=LIMITES_EMAIL,
            extra_sections=extra,
        ),
        "executado": False,
    }


LIMITES_EMAIL = [
    "A conferência é lexical e estrutural: não envia, não autentica SPF/DKIM/DMARC e não mede entrega real.",
    "Termos de spam são uma lista curta e conservadora; ausência na lista não garante caixa de entrada.",
    "O pré-cabeçalho só é conferido quando informado; a primeira linha do HTML não é extraída.",
    "Regras de descadastro valem para ciclo de vida e são buscadas no HTML, não no texto.",
]


# --------------------------------------------------------------- 5. SEO

class _Pagina(HTMLParser):
    """Coleta o que a página declara: título, meta, títulos, imagens, links e dados."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.titulo = ""
        self.metas: list[dict[str, str]] = []
        self.headings: list[tuple[int, str]] = []
        self.imgs: list[dict[str, str]] = []
        self.links: list[dict[str, str]] = []
        self.jsonld: list[str] = []
        self.lang = ""
        self.texto: list[str] = []
        self.canonical = ""
        self._captura: str | None = None
        self._buffer: list[str] = []
        self._script = False
        self._script_buffer: list[str] = []
        self._ignorar = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        dados = {chave.lower(): (valor or "") for chave, valor in attrs}
        if tag == "html":
            self.lang = dados.get("lang", "")
        if tag == "title":
            self._captura = "title"
            self._buffer = []
        elif tag in {"h1", "h2", "h3", "h4", "h5", "h6"}:
            self._captura = tag
            self._buffer = []
        elif tag == "meta":
            self.metas.append(dados)
        elif tag == "img":
            self.imgs.append(dados)
        elif tag == "a":
            self.links.append(dados)
        elif tag == "link" and "canonical" in dados.get("rel", "").lower():
            self.canonical = dados.get("href", "")
        elif tag == "script":
            self._script = True
            self._script_buffer = []
            self._ignorar += 1
            if "ld+json" in dados.get("type", "").lower():
                self._captura = "jsonld"
        elif tag in {"style", "noscript"}:
            self._ignorar += 1
        elif tag in {"p", "li", "h1", "h2", "h3", "h4", "h5", "h6"}:
            self.texto.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag == "title" and self._captura == "title":
            self.titulo = " ".join("".join(self._buffer).split())
            self._captura = None
        elif tag in {"h1", "h2", "h3", "h4", "h5", "h6"} and self._captura == tag:
            nivel = int(tag[1])
            texto = " ".join("".join(self._buffer).split())
            if texto:
                self.headings.append((nivel, texto))
            self._captura = None
        elif tag == "script":
            self._script = False
            self._ignorar = max(0, self._ignorar - 1)
            if self._captura == "jsonld":
                self.jsonld.append("".join(self._script_buffer).strip())
                self._captura = None
        elif tag in {"style", "noscript"}:
            self._ignorar = max(0, self._ignorar - 1)

    def handle_data(self, data: str) -> None:
        if self._script:
            self._script_buffer.append(data)
            return
        if self._ignorar:
            return
        if self._captura:
            self._buffer.append(data)
        self.texto.append(data)


def _texto_da_pagina(pagina: _Pagina) -> str:
    return " ".join("".join(pagina.texto).split())


def _meta(pagina: _Pagina, nome: str) -> str:
    for dados in pagina.metas:
        if dados.get("name", "").lower() == nome or dados.get("property", "").lower() == nome:
            return dados.get("content", "")
    return ""


def _dominio(url: str) -> str:
    partes = urlsplit(url if "//" in url else f"//{url}")
    return (partes.hostname or "").lower()


def auditar_seo(
    *,
    html: str,
    palavra_chave: str = "",
    url: str = "",
    modo: str = "full",
) -> dict[str, Any]:
    if len(html.strip()) < 60:
        raise MarketingError("Cole o HTML da página; menos de 60 caracteres não é uma página.")
    if len(html) > MAX_TEXTO:
        raise MarketingError("HTML acima do limite de leitura.")
    pagina = _Pagina()
    try:
        pagina.feed(html)
        pagina.close()
    except Exception as erro:  # pragma: no cover - HTMLParser é tolerante
        raise MarketingError(f"HTML não pôde ser lido: {erro}") from erro

    texto = _texto_da_pagina(pagina)
    palavras = texto.split()
    descricao = _meta(pagina, "description")
    chave = palavra_chave.strip()
    h1 = [titulo for nivel, titulo in pagina.headings if nivel == 1]
    achados: list[dict[str, Any]] = []

    if not pagina.titulo:
        achados.append(finding(
            "must", "sem-title", "Página sem <title>", "—",
            "O título é o que aparece no resultado de busca e na aba.",
            "O buscador inventa um título a partir do conteúdo.",
            "Escreva 50–60 caracteres com a consulta principal no começo.",
            "A página perde o controle do próprio anúncio orgânico.",
        ))
    else:
        tamanho = len(pagina.titulo)
        if tamanho > 65:
            achados.append(finding(
                "must", "title-longo", "<title> acima de 65 caracteres", f"{tamanho}",
                "A faixa útil fica entre 50 e 60 caracteres.",
                "O resultado corta o fim, onde fica a diferenciação.",
                "Corte para 60.",
                "O anúncio orgânico termina em reticências.",
            ))
        elif tamanho < 25:
            achados.append(finding(
                "should", "title-curto", "<title> curto demais", f"{tamanho}",
                "Entre 50 e 60 caracteres o título usa o espaço que tem.",
                "Título curto desperdiça a linha mais visível do resultado.",
                "Acrescente a categoria ou o benefício.",
                "A página parece rasa.",
            ))
        if chave and not _contem(pagina.titulo, chave):
            achados.append(finding(
                "should", "chave-fora-do-title", "Palavra-chave fora do <title>", chave,
                "A consulta principal precisa aparecer no título, de preferência no começo.",
                "O buscador ainda entende o tema, mas o usuário não vê o termo que digitou.",
                "Reescreva o título com a consulta.",
                "A taxa de clique cai para a mesma posição.",
            ))

    if not descricao:
        achados.append(finding(
            "must", "sem-description", "Página sem meta description", "—",
            "A descrição é a linha de venda do resultado.",
            "O buscador monta o trecho com um pedaço qualquer do texto.",
            "Escreva 150–160 caracteres com a proposta e uma ação.",
            "O snippet vira sorte.",
        ))
    elif not (120 <= len(descricao) <= 170):
        achados.append(finding(
            "should", "description-fora-da-faixa", "Meta description fora da faixa", f"{len(descricao)}",
            "A faixa útil fica entre 150 e 160 caracteres.",
            "Curta demais sobra espaço; longa demais é cortada.",
            "Ajuste para 150–160.",
            "O resultado orgânico perde informação.",
        ))

    if not h1:
        achados.append(finding(
            "must", "sem-h1", "Página sem H1", "—",
            "O H1 diz ao leitor e ao buscador qual é o assunto da página.",
            "Sem H1, a hierarquia começa no H2 e a página perde o título interno.",
            "Promova o título principal a H1.",
            "A página parece não ter assunto.",
        ))
    elif len(h1) > 1:
        achados.append(finding(
            "must", "h1-repetido", "Mais de um H1", f"{len(h1)}",
            "Um H1 por página.",
            "Vários H1 diluem o tema e confundem a extração.",
            "Deixe um H1 e rebaixe os outros.",
            "O buscador escolhe por você qual é o título.",
        ))
    elif chave and not _contem(h1[0], chave):
        achados.append(finding(
            "should", "chave-fora-do-h1", "Palavra-chave fora do H1", h1[0][:60],
            "O H1 e o título devem falar do mesmo assunto.",
            "Divergência entre os dois enfraquece a página para a consulta.",
            "Alinhe o H1 com a consulta.",
            "A página parece responder a outra pergunta.",
        ))
    niveis = [nivel for nivel, _ in pagina.headings]
    saltos = [(antes, depois) for antes, depois in zip(niveis, niveis[1:]) if depois - antes > 1]
    if saltos:
        achados.append(finding(
            "should", "salto-de-nivel", "Salto na hierarquia de títulos", f"h{saltos[0][0]} → h{saltos[0][1]}",
            "A ordem desce um nível por vez.",
            "Salto de H2 para H4 quebra a leitura por leitor de tela e a extração do tema.",
            "Use H3 no lugar do salto.",
            "A estrutura é lida fora de ordem.",
        ))

    sem_alt = [img for img in pagina.imgs if not img.get("alt", "").strip()]
    if sem_alt:
        achados.append(finding(
            "must", "img-sem-alt", "Imagem sem texto alternativo", f"{len(sem_alt)} de {len(pagina.imgs)}",
            "O `alt` descreve a imagem para quem não a vê.",
            "Sem ele, o leitor de tela lê o nome do arquivo e o buscador não entende a imagem.",
            "Descreva o conteúdo em uma frase.",
            "Acessibilidade e indexação de imagem ficam incompletas.",
        ))
    genericos = [img for img in pagina.imgs if _norm(img.get("alt", "")) in GENERICOS_ALT]
    if genericos:
        achados.append(finding(
            "nice", "alt-generico", "Texto alternativo genérico", f"{len(genericos)}",
            "“Imagem” e “foto” não descrevem nada.",
            "O espaço do alt é desperdiçado.",
            "Diga o que a imagem mostra.",
            "A descrição não ajuda ninguém.",
        ))
    sem_dimensao = [img for img in pagina.imgs if not (img.get("width") and img.get("height"))]
    if len(sem_dimensao) > 3:
        achados.append(finding(
            "nice", "sem-dimensao", "Imagens sem largura e altura", f"{len(sem_dimensao)}",
            "Largura e altura reservam o espaço antes do carregamento.",
            "Sem elas, a página salta e o CLS piora.",
            "Declare `width` e `height`.",
            "A experiência de leitura piora.",
        ))

    if not pagina.canonical:
        achados.append(finding(
            "should", "sem-canonical", "Página sem link canonical", "—",
            "O canonical diz qual URL é a oficial.",
            "Com variação de parâmetro ou de domínio, a força se divide.",
            "Aponte para a própria URL canônica.",
            "Duas versões competem entre si.",
        ))
    else:
        if url and _dominio(pagina.canonical) and _dominio(url) and _dominio(pagina.canonical) != _dominio(url):
            achados.append(finding(
                "must", "canonical-cruzado", "Canonical aponta para outro domínio", pagina.canonical[:80],
                "O canonical de uma página aponta para ela mesma.",
                "Apontar para outro domínio transfere a indexação e some com a página.",
                "Corrija para a URL canônica deste domínio.",
                "A página sai do índice.",
            ))
    if not pagina.lang:
        achados.append(finding(
            "should", "sem-lang", "Tag <html> sem idioma", "—",
            "`lang` orienta leitor de tela, hifenização e busca regional.",
            "Sem ele, o navegador adivinha o idioma.",
            "Declare `lang=\"pt-BR\"`.",
            "A pronúncia do leitor de tela erra.",
        ))

    if not pagina.jsonld:
        achados.append(finding(
            "nice", "sem-jsonld", "Sem dados estruturados", "—",
            "JSON-LD descreve a entidade da página para o buscador.",
            "Sem marcação, o resultado perde rich snippet.",
            "Adicione um bloco com `@context` e `@type` coerentes com a página.",
            "A página não disputa resultado enriquecido.",
        ))
    else:
        invalidos = []
        for bloco in pagina.jsonld:
            try:
                dados = json.loads(bloco)
            except json.JSONDecodeError:
                invalidos.append(bloco[:60])
                continue
            itens = dados if isinstance(dados, list) else [dados]
            for item in itens:
                if isinstance(item, dict) and not item.get("@context"):
                    invalidos.append("@context ausente")
        if invalidos:
            achados.append(finding(
                "should", "jsonld-invalido", "JSON-LD inválido ou incompleto", invalidos[0][:60],
                "O bloco precisa ser JSON válido e declarar `@context`.",
                "Bloco inválido é ignorado e ainda gasta o tempo do robô.",
                "Corrija o JSON e o contexto.",
                "O rich snippet não aparece.",
            ))

    internos = 0
    externos = 0
    dominio_pagina = _dominio(url) if url else ""
    for link in pagina.links:
        href = link.get("href", "").strip()
        if not href or href.startswith(("#", "mailto:", "tel:", "javascript:")):
            continue
        if href.startswith("http") and dominio_pagina and _dominio(href) != dominio_pagina:
            externos += 1
        elif href.startswith("http"):
            externos += 1
        else:
            internos += 1
    if internos == 0:
        achados.append(finding(
            "should", "sem-link-interno", "Nenhum link interno", "—",
            "Link interno distribui autoridade e conduz a leitura.",
            "Página sem saída interna vira beco sem saída.",
            "Aponte para duas ou três páginas relacionadas.",
            "A página fica órfã na navegação.",
        ))
    if len(palavras) < 300:
        achados.append(finding(
            "should", "conteudo-curto", "Conteúdo curto", f"{len(palavras)} palavras",
            "Abaixo de 300 palavras raramente há o que ranquear.",
            "Página fina compete mal e atrai pouco link.",
            "Aprofunde o que a consulta pede, sem encher.",
            "A página não cobre a intenção.",
        ))

    ancoras_genericas = 0
    for link in pagina.links:
        href = link.get("href", "")
        if href and not link.get("aria-label") and href.startswith("#"):
            ancoras_genericas += 1
    if ancoras_genericas > 2:
        achados.append(finding(
            "nice", "muitas-ancoras", "Muitos links só de âncora", f"{ancoras_genericas}",
            "Âncora interna serve para navegar, não para somar link.",
            "Excesso de âncora polui a contagem de links.",
            "Use sumário só quando a página for longa.",
            "O robô gasta rastreamento em fragmento.",
        ))

    # --- sinais de busca por IA (AEO/GEO)
    blocos = [bloco.strip() for bloco in "".join(pagina.texto).split("\n") if bloco.strip()]
    titulos = {titulo for _, titulo in pagina.headings}
    paragrafos = [bloco for bloco in blocos if bloco not in titulos]
    apos_h1 = texto
    if h1:
        for indice, bloco in enumerate(blocos):
            if bloco == h1[0] and indice + 1 < len(blocos):
                apos_h1 = blocos[indice + 1]
                break
    primeiro = apos_h1
    if len(primeiro.split()) > 110:
        achados.append(finding(
            "should", "sem-resposta-direta", "Abertura longa sem resposta direta", f"{len(primeiro.split())} palavras",
            "Motor de resposta extrai o primeiro parágrafo que responde à pergunta.",
            "Abertura de 110 palavras costuma ser introdução, não resposta.",
            "Responda em 40–90 palavras logo abaixo do H1.",
            "A página fica de fora da citação.",
        ))
    perguntas = [titulo for _, titulo in pagina.headings if titulo.strip().endswith("?")]
    if not perguntas:
        achados.append(finding(
            "nice", "sem-pergunta", "Nenhum H2 ou H3 em forma de pergunta", "—",
            "Pergunta no título casa com a consulta em linguagem natural.",
            "Sem ela, a página descreve e não responde.",
            "Reescreva um subtítulo como a pergunta do leitor.",
            "A página perde a citação em resposta gerada.",
        ))
    if externos == 0:
        achados.append(finding(
            "nice", "sem-fonte", "Nenhum link para fonte externa", "—",
            "Citar a fonte sustenta o fato e ajuda a ser citado.",
            "Afirmação sem origem vale menos para quem avalia qualidade.",
            "Linke o dado primário.",
            "O texto parece opinião.",
        ))
    if not re.search(r"\b(20\d\d)\b", texto):
        achados.append(finding(
            "nice", "sem-data", "Texto sem nenhum ano", "—",
            "Data no conteúdo mostra atualidade.",
            "Sem data, o leitor não sabe se o dado é de ontem ou de 2019.",
            "Diga a data do dado citado.",
            "O texto parece atemporal e desatualizado.",
        ))

    metrics = {
        "palavras": len(palavras), "h1": len(h1), "headings": len(pagina.headings),
        "imgs": len(pagina.imgs), "sem_alt": len(sem_alt), "links_internos": internos,
        "links_externos": externos, "jsonld": len(pagina.jsonld), "titulo": len(pagina.titulo),
        "descricao": len(descricao), "canonical": bool(pagina.canonical), "lang": pagina.lang,
    }
    perguntas = ["Qual é a intenção de busca desta página: informar, comparar ou comprar?"] if modo == "ultra" else []
    achados, counts, veredito, perguntas = finalize(achados, modo, perguntas)
    extra = ["", "## Limites de referência", "",
             "| Elemento | Faixa útil |", "|---|---|",
             "| `<title>` | 50–60 caracteres |",
             "| Meta description | 150–160 caracteres |",
             "| H1 | exatamente 1 |",
             "| Texto | 300 palavras ou mais |",
             "| Imagens | todas com `alt` descritivo |",
             "| Canonical | autorreferente, mesmo domínio |", "",
             "Faixa útil não é regra do buscador: é o ponto em que o resultado costuma aparecer inteiro.", ""]
    return {
        **common(
            analysis="marketing.seo",
            mode=modo,
            title="Auditoria on-page",
            summary=[
                f"{len(palavras)} palavras, {len(pagina.headings)} título(s) e {len(pagina.imgs)} imagem(ns).",
                f"Título de {len(pagina.titulo)} e descrição de {len(descricao)} caracteres.",
                f"{internos} link(s) interno(s) e {externos} externo(s).",
            ],
            findings=achados,
            counts=counts,
            verdict=veredito,
            questions=perguntas,
            rows=[
                {"elemento": "Title", "valor": pagina.titulo or "—", "medida": len(pagina.titulo)},
                {"elemento": "Description", "valor": descricao or "—", "medida": len(descricao)},
                {"elemento": "H1", "valor": h1[0] if h1 else "—", "medida": len(h1)},
                {"elemento": "Canonical", "valor": pagina.canonical or "—", "medida": 1 if pagina.canonical else 0},
                {"elemento": "Idioma", "valor": pagina.lang or "—", "medida": 5 if pagina.lang else 0},
                {"elemento": "JSON-LD", "valor": f"{len(pagina.jsonld)} bloco(s)", "medida": len(pagina.jsonld)},
            ],
            metrics=metrics,
            limitations=LIMITES_SEO,
            extra_sections=extra,
        ),
        "executado": False,
    }


LIMITES_SEO = [
    "A auditoria é do HTML entregue: não executa JavaScript, não busca o DOM renderizado e não mede Core Web Vitals em campo.",
    "Não há consulta ao Search Console, à SERP nem a volume de busca.",
    "Rastreamento, sitemap, robôs e canonical entre páginas do site não são verificados — só o que está neste arquivo.",
    "Os sinais de busca por IA descrevem o que um motor de resposta costuma extrair; nenhum modelo é consultado.",
]


# --------------------------------------------------------------- 6. anúncio

def revisar_anuncio(
    *,
    plataforma: str,
    titulos: str = "",
    descricoes: str = "",
    texto_principal: str = "",
    url_final: str = "",
    modo: str = "full",
) -> dict[str, Any]:
    if plataforma not in PLATAFORMAS:
        raise MarketingError(f"`plataforma` aceita {', '.join(PLATAFORMAS)}.")
    config = PLATAFORMAS[plataforma]
    campos = {
        "titulos": _linhas(titulos),
        "descricoes": _linhas(descricoes),
        "texto_principal": _linhas(texto_principal),
    }
    if not any(campos.values()):
        raise MarketingError("Informe ao menos um texto de anúncio.")

    achados: list[dict[str, Any]] = []
    linhas: list[dict[str, Any]] = []
    for campo, regra in config["campos"].items():
        valores = campos.get(campo, [])
        if len(valores) < regra["minimo"]:
            achados.append(finding(
                "must", f"{campo}-faltando", f"{regra['rotulo']} abaixo do mínimo", f"{len(valores)} de {regra['minimo']}",
                f"A plataforma exige ao menos {regra['minimo']} {regra['rotulo'].lower()}(s).",
                "Com menos peças, o sistema não tem com o que combinar e a entrega cai.",
                f"Escreva {regra['minimo']} no mínimo.",
                "O anúncio não é aprovado ou entrega mal.",
            ))
        if len(valores) > regra["maximo"]:
            achados.append(finding(
                "must", f"{campo}-excesso", f"{regra['rotulo']} acima do máximo", f"{len(valores)} de {regra['maximo']}",
                f"A plataforma aceita até {regra['maximo']}.",
                "O excedente é descartado sem aviso.",
                "Corte o que não for diferente dos outros.",
                "Você escreve o que não vai rodar.",
            ))
        for indice, valor in enumerate(valores, start=1):
            excesso = len(valor) - regra["limite"]
            if excesso > 0:
                achados.append(finding(
                    "must", f"{campo}-longo", f"{regra['rotulo']} acima do limite", f"{regra['rotulo']} {indice}: {len(valor)} de {regra['limite']}",
                    f"O limite da plataforma é {regra['limite']} caracteres.",
                    f"Passa {excesso} caractere(s); o texto é recusado na subida.",
                    f"Corte {excesso} caractere(s) ou divida em duas peças.",
                    "A peça não entra ou entra cortada.",
                ))
            linhas.append({
                "campo": regra["rotulo"], "indice": indice, "texto": valor,
                "tamanho": len(valor), "limite": regra["limite"],
                "situacao": "ok" if excesso <= 0 else f"+{excesso}",
            })
            repetido = sum(1 for outro in valores if _norm(outro) == _norm(valor))
            if repetido > 1 and indice == valores.index(valor) + 1:
                achados.append(finding(
                    "should", f"{campo}-repetido", f"{regra['rotulo']} repetido", valor[:50],
                    "Cada peça precisa dizer algo diferente.",
                    "Peça repetida consome espaço de combinação sem trazer mensagem nova.",
                    "Reescreva com outro ângulo.",
                    "O teste entre variações mede a mesma coisa.",
                ))
            if valor.isupper() and len(valor) > 12:
                achados.append(finding(
                    "should", f"{campo}-caixa-alta", f"{regra['rotulo']} em caixa alta", valor[:40],
                    "Caixa alta é lida como grito e pesa no filtro.",
                    "A plataforma pode reprovar por uso excessivo de maiúsculas.",
                    "Use caixa de frase.",
                    "A peça é reprovada ou ignorada.",
                ))
            if valor.count("!") > 1 or re.search(r"[!?]{3,}", valor):
                achados.append(finding(
                    "should", f"{campo}-pontuacao", f"{regra['rotulo']} com pontuação excessiva", valor[:40],
                    "Uma exclamação basta.",
                    "Repetição de pontuação é sinal de anúncio enganoso.",
                    "Mantenha uma.",
                    "A revisão da plataforma marca a conta.",
                ))
            if re.search(r"[\U0001F300-\U0001FAFF\u2600-\u27BF]", valor):
                achados.append(finding(
                    "should", f"{campo}-emoji", f"Emoji em {regra['rotulo'].lower()}", valor[:40],
                    "Emoji em título de anúncio pago come espaço do limite.",
                    "O caractere ocupa espaço e não comunica nada novo.",
                    "Remova.",
                    "Você paga por espaço desperdiçado.",
                ))
            vistos: set[str] = set()
            for nome, padrao in RECOMENDACAO_FORCADA:
                achado = padrao.search(valor)
                if not achado or nome in vistos:
                    continue
                vistos.add(nome)
                grupo = "must" if nome in {"numero-um", "garantia"} else "should"
                achados.append(finding(
                    grupo, f"claim-{nome}", f"Afirmação não verificável: {nome}", achado.group(0)[:50],
                    "Anúncio pago precisa de afirmação verificável.",
                    "Superlativo sem prova é reprovado pela plataforma e cobrado pelo consumidor.",
                    "Troque por um fato: número, prazo, condição.",
                    "A peça cai na revisão ou vira reclamação.",
                ))

    if url_final:
        if not url_final.startswith("https://"):
            achados.append(finding(
                "must", "url", "URL final sem https", url_final[:80],
                "Toda peça leva a uma URL https.",
                "Link http é recusado ou marcado como inseguro.",
                "Use https.",
                "O clique não passa.",
            ))
        if not re.search(r"utm_|gclid|fbclid", url_final):
            achados.append(finding(
                "nice", "sem-parametro", "URL final sem parâmetro de campanha", url_final[:80],
                "A plataforma acrescenta o identificador de clique; o `utm_content` separa a peça.",
                "Sem parâmetro próprio, a peça não se distingue no relatório orgânico.",
                "Acrescente `utm_content` com o nome da peça.",
                "A comparação entre criativos fica só dentro da plataforma.",
            ))
    else:
        achados.append(finding(
            "should", "sem-url", "Sem URL final", "—",
            "Toda peça tem destino declarado.",
            "Sem URL, não há como conferir para onde o clique vai.",
            "Informe a URL final.",
            "A peça não pode ser publicada.",
        ))

    total = sum(len(valores) for valores in campos.values())
    metrics = {
        "plataforma": plataforma, "pecas": total,
        "titulos": len(campos["titulos"]), "descricoes": len(campos["descricoes"]),
        "texto_principal": len(campos["texto_principal"]),
        "acima_do_limite": sum(1 for linha in linhas if linha["situacao"] != "ok"),
    }
    perguntas = ["Quem assina a promessa que está no anúncio?"] if modo == "ultra" else []
    achados, counts, veredito, perguntas = finalize(achados, modo, perguntas)
    extra = ["", "## Limites da plataforma", "",
             f"**{config['nome']}** — {config['nota']}", "",
             "| Elemento | Limite | Mínimo | Máximo |", "|---|---|---|---|"]
    for campo, regra in config["campos"].items():
        extra.append(f"| {regra['rotulo']} | {regra['limite']} | {regra['minimo']} | {regra['maximo']} |")
    extra += ["", "## Regra de afirmação", "",
              "- Número, prazo, condição e prova no lugar de superlativo.",
              "- “O melhor”, “#1” e “garantido” voltam como achado bloqueante quando não há fonte.",
              "- O detalhe da oferta fica na página, não no título de 30 caracteres.", ""]
    return {
        **common(
            analysis="marketing.anuncio",
            mode=modo,
            title="Anúncio dentro do limite",
            summary=[
                f"{config['nome']}: {total} peça(s) conferida(s).",
                f"{metrics['acima_do_limite']} peça(s) acima do limite de caracteres.",
                "A contagem é exata: cada caractere conta, inclusive espaço e emoji.",
            ],
            findings=achados,
            counts=counts,
            verdict=veredito,
            questions=perguntas,
            rows=linhas,
            metrics=metrics,
            limitations=LIMITES_ANUNCIO,
            extra_sections=extra,
        ),
        "executado": False,
    }


LIMITES_ANUNCIO = [
    "Os limites são os publicados pelas plataformas na data da versão; mudam sem aviso e valem por elemento, não por combinação.",
    "Nenhuma conta de anúncio é acessada: a conferência é das peças que você cola.",
    "Política de anúncio muda por país e por categoria; um termo liberado aqui pode ser recusado na revisão real.",
    "Contagem de caracteres é a do texto Unicode; algumas plataformas contam bytes em emoji.",
]


# --------------------------------------------------------------- 7. regras

def marketing_catalogo() -> dict[str, Any]:
    grade = []
    for base in (1, 3, 5, 10):
        linha = {"baseline": base}
        for lift in (10, 20, 50):
            p1 = base / 100
            p2 = p1 * (1 + lift / 100)
            medio = (p1 + p2) / 2
            z_alfa = statistics.NormalDist().inv_cdf(0.975)
            z_poder = statistics.NormalDist().inv_cdf(0.8)
            n = ((z_alfa * math.sqrt(2 * medio * (1 - medio)) +
                  z_poder * math.sqrt(p1 * (1 - p1) + p2 * (1 - p2))) ** 2) / ((p2 - p1) ** 2)
            linha[f"lift_{lift}"] = math.ceil(n)
        grade.append(linha)
    return {
        "fonte": "coreyhaines31/marketingskills (MIT)",
        "versao": VERSAO,
        "principio": "Marketing se decide por número medido, não por adjetivo escolhido.",
        "plataformas": [
            {"id": chave, "nome": valor["nome"], "nota": valor["nota"],
             "campos": {campo: regra for campo, regra in valor["campos"].items()}}
            for chave, valor in PLATAFORMAS.items()
        ],
        "mediums": list(MEDIUMS),
        "faixas": {
            "ctr_maximo_plausivel": 10,
            "conversao_maxima_plausivel": 60,
            "ltv_cac_saudavel": 3,
            "payback_meses": 12,
            "margem_minima": 30,
            "titulo": list(TITULO_OK),
            "descricao": list(DESCRICAO_OK),
            "palavras_minimas": 300,
        },
        "amostra": grade,
        "formulas": [
            {"id": "impressoes", "formula": "orçamento ÷ CPM × 1000"},
            {"id": "cliques", "formula": "impressões × CTR"},
            {"id": "clientes", "formula": "cliques × conversão × fechamento"},
            {"id": "cac", "formula": "orçamento ÷ clientes"},
            {"id": "roas", "formula": "receita ÷ investimento"},
            {"id": "payback", "formula": "CAC ÷ (ticket × margem)"},
            {"id": "ltv-cac", "formula": "LTV ÷ CAC, com LTV = ticket × margem × vida útil"},
            {"id": "orcamento-por-meta", "formula": "(ARR ÷ (ARPC × 12) × CAC) ÷ retenção anual"},
            {"id": "amostra", "formula": "((z_α√(2p̄(1−p̄)) + z_β√(p1(1−p1)+p2(1−p2)))²) ÷ (p2−p1)²"},
            {"id": "duracao", "formula": "(amostra por variante × variantes) ÷ (tráfego diário × exposição)"},
        ],
        "integridade": [
            {"id": "opcoes", "regra": "Uma ferramenta aparece ao lado das alternativas reais, inclusive o caminho gratuito."},
            {"id": "relevancia", "regra": "A menção fica no ponto em que a escolha acontece, não no meio de assunto alheio."},
            {"id": "sem-empurrao", "regra": "Sem “o melhor”, “recomendado” ou “use X no lugar de Y” sem critério declarado."},
            {"id": "fatos", "regra": "O que a ferramenta faz, o custo e o esforço em termos verificáveis."},
            {"id": "interesse", "regra": "Quem escreve declara se é o dono da ferramenta ou parceiro."},
            {"id": "troca", "regra": "Se a ferramenta citada fosse trocada por uma concorrente, o texto continuaria justo."},
        ],
        "deixado_de_fora": [
            "As 52 skills de redação do upstream (copy, criativo, plano, PR, social) não foram portadas: o JARVIS mede, não escreve.",
            "Nenhum texto do upstream foi copiado: o módulo implementa as contas e as conferências em Python.",
            "Nenhuma conta de anúncio, pixel, CRM ou ferramenta de análise é acessada.",
        ],
        "executado": False,
    }
