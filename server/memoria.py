"""Memória de agente: roteamento, entidades, grafo, sessão, recall e esquecimento.

O upstream é o `topoteretes/cognee` (Apache-2.0, 32 mil estrelas, Python): uma
plataforma de memória que transforma documento, código e conversa em grafo de
conhecimento pesquisável. Lá a rota de busca é escolhida por LLM e as lições da
sessão são destiladas por pipeline; aqui a parte determinística é reimplementada
em Python, com a conta à vista — nenhuma chamada de modelo, nenhum embedding,
nenhum banco.

O desenho aproveitado é o das quatro operações públicas do upstream
(`remember`, `recall`, `improve`, `forget`), o portão determinístico de skill do
`recall()` — regras com peso, limiar e janela de negação —, a rota de busca por
família de pergunta, o conjunto de nós por sessão e o escopo de esquecimento com
`memory_only`. Nada é copiado: o texto da memória é o que você cola.
"""
from __future__ import annotations

import json
import math
import re
import unicodedata
from collections import Counter
from dataclasses import dataclass
from datetime import date
from typing import Any

from .review import common, finalize, finding

VERSAO = "0.61.8"

MAX_TEXTO = 1_800_000
MAX_ENTRADAS = 2_000
MAX_TRIPLAS = 5_000
MAX_TURNOS = 500
MAX_RESULTADOS = 50
MAX_ROWS = 200

MODOS = ("lite", "full", "ultra")

# Roteamento --------------------------------------------------------------
LIMIAR_ROTA = 3.0
MARGEM_MINIMA = 1.0
JANELA_NEGACAO = 20

VIAS = (
    "chunks",
    "grafo",
    "hibrido",
    "resumo",
    "temporal",
    "codigo",
    "procedimento",
    "regras",
)
VIA_PADRAO = "hibrido"
PRIORIDADE_VIA = {via: indice for indice, via in enumerate(VIAS)}

# Extração de entidade ----------------------------------------------------
TIPOS_ENTIDADE = (
    "nome",
    "sigla",
    "codigo",
    "arquivo",
    "data",
    "valor",
    "local",
)
TIPOS_MEMORIA = ("fato", "relacao", "regra", "decisao", "procedimento", "codigo", "resumo", "evento")

PALAVRAS_VAZIAS = {
    "a", "o", "as", "os", "um", "uma", "de", "da", "do", "das", "dos", "em", "no", "na", "nos", "nas",
    "por", "para", "com", "sem", "que", "e", "ou", "se", "ao", "aos", "à", "às", "como", "mais", "menos",
    "the", "a", "an", "of", "in", "on", "at", "to", "for", "and", "or", "with", "without", "is", "are",
    "was", "were", "be", "by", "from", "as", "it", "this", "that", "est", "sont", "der", "die", "das",
}

# Grafo -------------------------------------------------------------------
MAX_GRAU = 12
MAX_CICLOS = 20

# Sessão ------------------------------------------------------------------
LIMIAR_PROMOCAO = 4.0
MAX_CANDIDATOS = 10
MIN_TEXTO_LICAO = 40
MAX_TEXTO_LICAO = 600
FEEDBACK_RUIM = 2

# Recall ------------------------------------------------------------------
K1 = 1.2
B = 0.75
MEIA_VIDA_DIAS = 180.0
PESO_RECENCIA = 0.4
PESO_AFINIDADE = 0.6
COBERTURA_MINIMA = 40
MEMORIA_VENCIDA_DIAS = 365


class MemoriaError(ValueError):
    """Entrada recusada antes do cálculo."""


def _modo(valor: str) -> str:
    if valor not in MODOS:
        raise MemoriaError(f"Modo inválido: {valor}. Use {', '.join(MODOS)}.")
    return valor


def _normalizar(texto: str) -> str:
    decomposto = unicodedata.normalize("NFD", (texto or "").lower())
    return "".join(ch for ch in decomposto if unicodedata.category(ch) != "Mn")


def _slug(texto: str) -> str:
    limpo = _normalizar(texto).strip()
    limpo = re.sub(r"[^a-z0-9]+", "-", limpo)
    return limpo.strip("-")


def _resumo(texto: str, limite: int) -> str:
    limpo = re.sub(r"\s+", " ", (texto or "").strip())
    if len(limpo) <= limite:
        return limpo
    return limpo[: limite - 1].rstrip() + "…"


def _tokens(texto: str) -> list[str]:
    return [token for token in re.findall(r"\w+", _normalizar(texto)) if len(token) >= 2]


def _termos(texto: str) -> list[str]:
    """Termos para busca: sem palavra vazia, que em corpus pequeno gera casamento falso."""
    return [token for token in _tokens(texto) if token not in PALAVRAS_VAZIAS]


def _fmt_pct(valor: float) -> str:
    return f"{valor:.0f}%".replace(".", ",")


def _data(valor: str) -> date | None:
    texto = (valor or "").strip()
    if not texto:
        return None
    try:
        return date.fromisoformat(texto)
    except ValueError:
        return None


def _questoes() -> list[str]:
    return [
        "Quem é o dono desta memória e por quanto tempo ela precisa durar?",
        "O que acontece se um fato desta sessão for promovido por engano?",
    ]


# ------------------------------------------------------------------ rotas

@dataclass(frozen=True)
class RegraRota:
    via: str
    peso: float
    etiqueta: str
    padrao: re.Pattern[str]


def _rota(via: str, peso: float, etiqueta: str, padrao: str) -> RegraRota:
    return RegraRota(via, peso, etiqueta, re.compile(padrao, re.IGNORECASE))


# Pesos como no portão de skill do upstream: sinal forte (4,0) decide sozinho,
# frase procedural (3,0) decide sozinha, sinal fraco (2,0) só soma.
REGRAS_ROTA: tuple[RegraRota, ...] = (
    # chunks: fato pontual, um valor, uma data, um nome
    _rota("chunks", 3.0, "quando-aconteceu", r"\b(quando|em que (ano|mês|data)|que ano|desde quando)\b"),
    _rota("chunks", 3.0, "quem-exatamente", r"\b(quem (é|foi|era|criou|escreveu)|qual (é|foi) o (nome|valor|número))\b"),
    _rota("chunks", 3.0, "onde-fica", r"\b(onde (fica|está|mora|nasceu)|em que (cidade|país|local))\b"),
    _rota("chunks", 2.0, "número-específico", r"\b(quantos|quantas|qual o total|a partir de|quanto (custa|é|foi))\b"),
    _rota("chunks", 3.0, "valor-direto", r"\b(qual (o|a) (valor|número|nome|data|código|versão)|em que versão)\b"),
    # grafo: relação entre duas coisas, caminho, conexão
    _rota("grafo", 4.0, "relação-entre", r"\b(relação entre|como .{1,40} (se )?(relaciona|conecta)|o que liga)\b"),
    _rota("grafo", 3.0, "dependente-de", r"\b(depende de|quem depende|o que usa|o que consome|está ligado a)\b"),
    _rota(
        "grafo",
        3.5,
        "caminho-multi-hop",
        r"\b(quem (foi|era|é) (o|a) (pai|mãe|filho|filha|avô|avó|marido|esposa|mentor|chefe|autor) d[aeo]|"
        r"o \w+ d[ao] \w+ que|através de quem|por meio de quem|quem (inventou|criou).{0,40}(dessa|desse) (pessoa|autor))\b",
    ),
    _rota("grafo", 2.0, "conexão", r"\b(conecta|vizinhança|grafo|nós|arestas?)\b"),
    # resumo: visão geral, síntese
    _rota("resumo", 4.0, "resumo-explícito", r"\b(resuma|resumir|resumo|síntese|sintetize|to sum up)\b"),
    _rota("resumo", 3.0, "visão-geral", r"\b(visão geral|panorama|principais (pontos|achados|temas)|no geral|overview)\b"),
    _rota("resumo", 2.0, "muitos-documentos", r"\b(documentos|corpus|acervo|memória inteira|todos os arquivos)\b"),
    # temporal: evolução, histórico, ordem
    _rota("temporal", 4.0, "linha-do-tempo", r"\b(linha do tempo|timeline|histórico de|evolução de|o que mudou)\b"),
    _rota("temporal", 3.0, "antes-depois", r"\b(antes de|depois de|desde que|até quando|última vez|primeira vez)\b"),
    _rota("temporal", 3.0, "mais-recente", r"\b(mais recente|última (decisão|versão|mudança)|vigente|atual)\b"),
    # código: símbolo, arquivo, implementação
    _rota(
        "codigo",
        4.0,
        "símbolo",
        r"\b(onde (está|foi|fica) (implementad|definid)[oa]s?|qual arquivo define|assinatura d[ao]|qual (é|foi) a assinatura)\b",
    ),
    _rota("codigo", 3.0, "código-explícito", r"(\b\w+\(\)|[\w/]+\.(py|ts|tsx|js|mjs|go|rs|java|sql)\b)"),
    _rota("codigo", 2.5, "erro-de-código", r"\b(stack ?trace|traceback|erro na linha|exceção|compila)\b"),
    # procedimento: como fazer — o portão de skill do recall
    _rota("procedimento", 4.0, "como-fazer", r"\b(como (faço|fazer|posso|devo)|passo a passo|step.by.step|how (do|can|to))\b"),
    _rota("procedimento", 4.0, "documento-procedural", r"\b(runbook|playbook|checklist|procedimento|receita|roteiro)\b"),
    _rota("procedimento", 3.0, "instalação", r"\b(instalar|configurar|implantar|deploy|migrar|provisionar|integrar)\b"),
    _rota("procedimento", 2.0, "verbo-operacional", r"\b(setup|upgrade|rotacionar|troubleshoot|diagnosticar|corrigir)\b"),
    # regras: política, convenção, decisão tomada
    _rota("regras", 4.0, "política", r"\b(política|convenção|norma interna|padrão do time|código de conduta)\b"),
    _rota("regras", 3.5, "decisão-registrada", r"\b(por que decidimos|qual foi a decisão|ficou decidido|acordado que)\b"),
    _rota("regras", 3.0, "permissão", r"\b(pode|pode-se|é permitido|não pode|proibido|precisa de aprovação)\b"),
    _rota("regras", 3.0, "lição-aprendida", r"\b(lição|aprendizado|regra de ouro|nunca|sempre)\b"),
    # hibrido: passagem + entidade, o caso comum
    _rota("hibrido", 3.0, "passagem-e-entidade", r"\b(trecho|passagem|documento que (fala|menciona)|cite a fonte|com a fonte)\b"),
    _rota("hibrido", 2.0, "fonte", r"\b(fonte|fontes|cite|cit[ea]r|citação)\b"),
    _rota("hibrido", 2.0, "pergunta-ampla", r"\b(explique|descreva|conte sobre|fale sobre)\b"),
)

NEGACAO = re.compile(r"\b(não|nunca|sem|nem|exceto|not|never|without|no)\b", re.IGNORECASE)


def _negado(consulta: str, casado: re.Match[str]) -> bool:
    inicio = max(0, casado.start() - JANELA_NEGACAO)
    return bool(NEGACAO.search(consulta[inicio: casado.start()]))


def rotear_consulta(*, consulta: str, modo: str = "full") -> dict[str, Any]:
    """Escolhe a via de recuperação pela forma da pergunta, com a conta à vista."""
    modo = _modo(modo)
    texto = (consulta or "").strip()
    if not texto:
        raise MemoriaError("Informe a consulta: a via de recuperação sai da forma da pergunta.")
    if len(texto) > MAX_TEXTO:
        raise MemoriaError(f"A consulta passa de {MAX_TEXTO:,} caracteres.")

    tokens = _tokens(texto)
    scores: dict[str, float] = {via: 0.0 for via in VIAS}
    rows: list[dict[str, Any]] = []
    negados = 0
    for regra in REGRAS_ROTA:
        for casado in regra.padrao.finditer(texto):
            trecho = casado.group(0)
            if _negado(texto, casado):
                negados += 1
                rows.append(
                    {
                        "via": regra.via,
                        "regra": regra.etiqueta,
                        "peso": f"{regra.peso:.1f}",
                        "trecho": _resumo(trecho, 60),
                        "situacao": "negado",
                    }
                )
                continue
            scores[regra.via] += regra.peso
            rows.append(
                {
                    "via": regra.via,
                    "regra": regra.etiqueta,
                    "peso": f"{regra.peso:.1f}",
                    "trecho": _resumo(trecho, 60),
                    "situacao": "conta",
                }
            )

    ordenadas = sorted(scores.items(), key=lambda item: (-item[1], PRIORIDADE_VIA[item[0]]))
    topo, pontos = ordenadas[0]
    segundo, pontos_segundo = ordenadas[1]
    margem = round(pontos - pontos_segundo, 2)

    fallback = pontos < LIMIAR_ROTA
    escolhida = VIA_PADRAO if fallback else topo
    if fallback:
        motivo = f"nenhuma via passou do limiar {LIMIAR_ROTA:.1f}; usa `{VIA_PADRAO}`"
    elif margem < MARGEM_MINIMA and pontos_segundo >= LIMIAR_ROTA:
        motivo = f"margem de {margem:.1f} para `{segundo}`; desempate pela ordem fixa"
    else:
        motivo = f"`{topo}` somou {pontos:.1f} contra {pontos_segundo:.1f} de `{segundo}`"

    problemas: list[dict[str, Any]] = []
    if len(tokens) < 3:
        problemas.append(
            finding(
                "should",
                "consulta-curta",
                f"{len(tokens)} termo(s) na consulta",
                _resumo(texto, 60),
                "Pergunta com menos de três termos.",
                "Consulta curta quase não dá sinal de via e costuma acertar só por sorte.",
                "Diga o objeto e o que você quer saber dele.",
                "A via cai no padrão e o recall devolve o que casar por acaso.",
            )
        )
    if len(tokens) > 120:
        problemas.append(
            finding(
                "should",
                "consulta-longa",
                f"{len(tokens)} termo(s) na consulta",
                _resumo(texto, 60),
                "Pergunta acima de 120 termos.",
                "Consulta longa mistura várias perguntas e dilui o peso de cada sinal.",
                "Separe em uma pergunta por chamada, com o mesmo dataset.",
                "A via escolhida atende uma das perguntas e ignora as outras.",
            )
        )
    if pontos >= LIMIAR_ROTA and margem < MARGEM_MINIMA and pontos_segundo >= LIMIAR_ROTA:
        problemas.append(
            finding(
                "should",
                "ambiguidade-de-via",
                f"margem de {margem:.1f}",
                f"{topo} × {segundo}",
                "Duas vias passaram do limiar quase empatadas.",
                "Empate técnico significa que a pergunta pede duas coisas ao mesmo tempo.",
                "Rode as duas vias e compare o lastro de cada uma, ou divida a pergunta.",
                "A via escolhida devolve metade do que você pediu.",
            )
        )
    if fallback:
        problemas.append(
            finding(
                "should",
                "sem-sinal",
                "nenhuma via passou do limiar",
                _resumo(texto, 60),
                f"A consulta não casou nenhuma regra com peso suficiente ({pontos:.1f}).",
                "Sem sinal, a escolha da via é arbitrária.",
                f"Use `{VIA_PADRAO}` de propósito ou reformule citando o objeto e o tipo de resposta.",
                "O recall devolve passagem solta quando a pergunta pedia relação.",
            )
        )
    if negados:
        problemas.append(
            finding(
                "nice",
                "sinal-negado",
                f"{negados} sinal(is) descartado(s) por negação",
                f"janela de {JANELA_NEGACAO} caracteres",
                "Regra casada logo depois de uma palavra de negação.",
                "“Não quero resumo” não pede resumo.",
                "Nada a corrigir: a negação é respeitada de propósito.",
                "Sem esse descarte, a via seria a oposta da intenção.",
            )
        )

    findings, counts, veredito, perguntas = finalize(problemas, modo, _questoes() if modo == "ultra" else [])
    metricas = {
        "termos": len(tokens),
        "regras": sum(1 for row in rows if row["situacao"] == "conta"),
        "negados": negados,
        "pontuacao": round(pontos, 1),
        "segunda": round(pontos_segundo, 1),
        "margem": margem,
        "via": escolhida,
        "fallback": 1 if fallback else 0,
    }
    resumo = [
        f"Consulta com **{len(tokens)} termos** roteada para `{escolhida}`: {motivo}.",
        f"Limiar {LIMIAR_ROTA:.1f}; {metricas['regras']} regra(s) contaram e {negados} foram descartadas por negação.",
    ]
    if rows:
        linhas = ["| Via | Regra | Peso | Trecho |", "|---|---|---|---|"]
        linhas += [f"| `{row['via']}` | {row['regra']} | {row['peso']} | {row['trecho']} |" for row in rows[:20]]
        extra = ["", "## Evidência", "", *linhas]
    else:
        extra = []
    return common(
        analysis="memoria.roteamento",
        mode=modo,
        title="Roteamento da consulta",
        summary=resumo,
        findings=findings,
        counts=counts,
        verdict=veredito,
        questions=perguntas,
        rows=rows,
        metrics=metricas,
        limitations=[
            "A via é escolhida por regra lexical: paráfrase sem as palavras-chave cai no padrão.",
            "Português e inglês apenas; outro idioma não casa nenhuma regra.",
            "O roteador não executa a busca: ele diz onde procurar.",
        ],
        extra_sections=extra,
    )


# ------------------------------------------------------------- extração

RE_CODIGO = re.compile(r"\b[A-Z]{2,5}-\d{1,6}\b")
RE_ISSUE = re.compile(r"(?:^|\s)#(\d{1,6})\b")
RE_ARQUIVO = re.compile(r"[\w./-]+\.(?:py|ts|tsx|js|mjs|go|rs|java|sql|json|ya?ml|md|toml|cfg|ini|sh)\b")
RE_SIGLA = re.compile(r"\b[A-Z][A-Z0-9]{1,7}\b")
RE_DATA_ISO = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")
RE_DATA_BR = re.compile(r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b")
RE_DATA_MES = re.compile(
    r"\b(\d{1,2}) de (janeiro|fevereiro|março|abril|maio|junho|julho|agosto|setembro|outubro|novembro|dezembro)"
    r"(?: de (\d{4}))?\b",
    re.IGNORECASE,
)
RE_VALOR = re.compile(r"(?:R\$|US\$|\$|€)\s?\d[\d.,]*(?:\s?(?:mil|milhões|milhão|bi|k|m))?", re.IGNORECASE)
RE_PORCENTAGEM = re.compile(r"\b\d+(?:[.,]\d+)?\s?%")
CONECTORES_LOCAL = r"(?:de|do|da|dos|das|of|the|del|la|von|van)"
RE_LOCAL = re.compile(
    r"\b(?:em|no|na|de|from|in)\s+([A-ZÁÉÍÓÚÂÊÔÃÕÇ][\wÀ-ÿ]+(?:\s+" + CONECTORES_LOCAL + r"\s+[\wÀ-ÿ]+)?(?:\s+[A-ZÁÉÍÓÚÂÊÔÃÕÇ][\wÀ-ÿ]+)?)"
)
RE_PAPEL = re.compile(
    r"\b([A-ZÁÉÍÓÚÂÊÔÃÕÇ][\wÀ-ÿ-]+(?:\s+[A-ZÁÉÍÓÚÂÊÔÃÕÇ][\wÀ-ÿ-]+)?)\s+"
    r"(foi|é|era|tornou-se)\s+"
    r"(professor|professora|engenheir[oa]|autor|autora|diretor|diretora|fundador|fundadora|"
    r"membro|respons[áa]vel|coordenador|coordenadora)\s+"
    r"(?:n[ao]|em|d[aeo])\s+"
    r"([A-ZÁÉÍÓÚÂÊÔÃÕÇ][\wÀ-ÿ-]+(?:\s+[A-ZÁÉÍÓÚÂÊÔÃÕÇ][\wÀ-ÿ-]+)?)"
)
RE_NOME = re.compile(r"\b([A-ZÁÉÍÓÚÂÊÔÃÕÇ][a-záéíóúâêôãõç]{2,}(?:\s+(?:de|da|do|dos|das|van|von|di|du)\s+)?(?:\s+[A-ZÁÉÍÓÚÂÊÔÃÕÇ][a-záéíóúâêôãõç]{2,}){1,3})\b")
RE_TRIPLA_PT = re.compile(
    r"\b([A-ZÁÉÍÓÚÂÊÔÃÕÇ][\wÀ-ÿ-]+(?:\s+[A-ZÁÉÍÓÚÂÊÔÃÕÇ][\wÀ-ÿ-]+)?)\s+"
    r"(foi|é|era|trabalha|trabalhou|nasceu|mora|pertence|usa|depende de|substitui|criou|escreveu|"
    r"mantém|publicou|fundou|comprou|vendeu|migrou|integra)\s+"
    r"(?:o |a |os |as |em |no |na |de |do |da |para )?"
    r"([A-ZÁÉÍÓÚÂÊÔÃÕÇ][\wÀ-ÿ-]+(?:\s+[A-ZÁÉÍÓÚÂÊÔÃÕÇ][\wÀ-ÿ-]+)?)"
)
RE_TRIPLA_EN = re.compile(
    r"\b([A-Z][\w-]+(?:\s+[A-Z][\w-]+)?)\s+"
    r"(was|is|worked at|works at|born in|uses|depends on|replaced|created|wrote|owns|maintains)\s+"
    r"(?:the |a |an )?([A-Z][\w-]+(?:\s+[A-Z][\w-]+)?)"
)
RE_TEMPORAL = re.compile(
    r"\b(antes|depois|desde|até|em 19\d{2}|em 20\d{2}|no ano de \d{4}|\d{4})\b", re.IGNORECASE
)


def _entidade_tipo(valor: str, regex: re.Pattern[str]) -> str:
    if regex is RE_ISSUE:
        return "codigo"
    if regex is RE_ARQUIVO:
        return "arquivo"
    if regex is RE_SIGLA:
        return "sigla"
    if regex is RE_LOCAL:
        return "local"
    if regex is RE_NOME:
        return "nome"
    return "nome"


def _plural(chave: str) -> str:
    return "s" if chave.endswith("s") else ""


def _chave_entidade(tipo: str, valor: str) -> str:
    return f"{tipo}:{_slug(valor)}"


def extrair_entidades(*, texto: str, modo: str = "full") -> dict[str, Any]:
    """Extrai entidades por tipo e as triplas declaradas, sem modelo de linguagem."""
    modo = _modo(modo)
    bruto = (texto or "").strip()
    if not bruto:
        raise MemoriaError("Informe o texto: as entidades saem do que você colar.")
    if len(bruto) > MAX_TEXTO:
        raise MemoriaError(f"O texto passa de {MAX_TEXTO:,} caracteres.")

    linhas = bruto.split("\n")
    if len(linhas) > MAX_ENTRADAS * 4:
        raise MemoriaError(f"O texto passa de {MAX_ENTRADAS * 4:,} linhas.")

    encontrados: dict[str, dict[str, Any]] = {}
    ordem: list[str] = []
    triplas: list[dict[str, Any]] = []
    ignorados = 0

    def registrar(tipo: str, valor: str, linha: int, trecho: str) -> None:
        limpo = " ".join(valor.split()).strip(" .,;:")
        if not limpo or len(limpo) < 2:
            return
        chave = _chave_entidade(tipo, limpo)
        if chave not in encontrados:
            encontrados[chave] = {"tipo": tipo, "entidade": limpo, "ocorrencias": 0, "linha": linha, "trecho": _resumo(trecho, 70)}
            ordem.append(chave)
        encontrados[chave]["ocorrencias"] += 1

    for numero, linha in enumerate(linhas, start=1):
        if len(linha) > 20_000:
            ignorados += 1
            continue
        ocupados: list[tuple[int, int]] = []
        for casado in RE_ISSUE.finditer(linha):
            registrar("codigo", f"#{casado.group(1)}", numero, linha)
            ocupados.append(casado.span())
        for casado in RE_CODIGO.finditer(linha):
            registrar("codigo", casado.group(0), numero, linha)
            ocupados.append(casado.span())
        for casado in RE_ARQUIVO.finditer(linha):
            registrar("arquivo", casado.group(0), numero, linha)
        for casado in RE_DATA_ISO.finditer(linha):
            registrar("data", casado.group(0), numero, linha)
        for casado in RE_DATA_BR.finditer(linha):
            registrar("data", casado.group(0), numero, linha)
        for casado in RE_DATA_MES.finditer(linha):
            registrar("data", casado.group(0), numero, linha)
        for casado in RE_VALOR.finditer(linha):
            registrar("valor", casado.group(0), numero, linha)
        for casado in RE_PORCENTAGEM.finditer(linha):
            registrar("valor", casado.group(0), numero, linha)
        for casado in RE_SIGLA.finditer(linha):
            if casado.group(0) in {"E", "OU", "AND", "OR", "DE", "DA", "DO"}:
                continue
            if any(inicio <= casado.start() and casado.end() <= fim for inicio, fim in ocupados):
                continue
            registrar("sigla", casado.group(0), numero, linha)
        for casado in RE_LOCAL.finditer(linha):
            valor = casado.group(1)
            if _chave_entidade("sigla", valor) in encontrados:
                continue
            registrar("local", valor, numero, linha)
        for casado in RE_NOME.finditer(linha):
            nome = casado.group(1)
            if _normalizar(nome) in PALAVRAS_VAZIAS:
                continue
            if _chave_entidade("local", nome) in encontrados:
                continue
            if any(palavra in {"R", "US", "CA"} for palavra in nome.split()):
                continue
            registrar("nome", nome, numero, linha)
        for casado in RE_PAPEL.finditer(linha):
            sujeito, verbo, papel, objeto = casado.group(1), casado.group(2), casado.group(3), casado.group(4)
            triplas.append(
                {
                    "sujeito": sujeito.strip(),
                    "relacao": f"{_normalizar(verbo)}-{_normalizar(papel)}",
                    "objeto": objeto.strip(),
                    "linha": numero,
                    "idioma": "pt",
                    "trecho": _resumo(casado.group(0), 70),
                }
            )
        for regex, sujeito_padrao in ((RE_TRIPLA_PT, "pt"), (RE_TRIPLA_EN, "en")):
            for casado in regex.finditer(linha):
                sujeito, predicado, objeto = casado.group(1), casado.group(2), casado.group(3)
                if _normalizar(sujeito) in PALAVRAS_VAZIAS or _normalizar(objeto) in PALAVRAS_VAZIAS:
                    continue
                triplas.append(
                    {
                        "sujeito": sujeito.strip(),
                        "relacao": _normalizar(predicado).replace(" ", "-"),
                        "objeto": objeto.strip(),
                        "linha": numero,
                        "idioma": sujeito_padrao,
                        "trecho": _resumo(casado.group(0), 70),
                    }
                )

    rows = [encontrados[chave] for chave in ordem][:MAX_ROWS]
    por_tipo = Counter(item["tipo"] for item in rows)
    repetidas = sorted(
        (item for item in rows if item["ocorrencias"] > 1),
        key=lambda item: (-item["ocorrencias"], item["entidade"]),
    )[:10]

    problemas: list[dict[str, Any]] = []
    if not rows:
        problemas.append(
            finding(
                "must",
                "sem-entidades",
                "Nenhuma entidade reconhecida",
                _resumo(bruto, 60),
                "O texto não trouxe nome, sigla, código, arquivo, data nem valor.",
                "Memória sem entidade não forma grafo: só vira trecho solto.",
                "Cite o que existe — nome próprio, código de ticket, arquivo ou data — e o que se afirma sobre isso.",
                "O recall devolve o texto bruto sem relação nenhuma.",
            )
        )
    sem_sujeito = [item for item in rows if item["tipo"] == "nome" and item["ocorrencias"] == 1]
    if rows and len(sem_sujeito) == len([item for item in rows if item["tipo"] == "nome"]) and rows:
        problemas.append(
            finding(
                "should",
                "nome-solto",
                f"{len(sem_sujeito)} nome(s) citado(s) uma única vez",
                ", ".join(item["entidade"] for item in sem_sujeito[:4]),
                "Todo nome aparece uma vez só, sem relação declarada.",
                "Sujeito que não se repete e não se liga a nada não é memória útil: é menção.",
                "Repita o sujeito junto do que ele fez, ou escreva a relação em `sujeito -> relação -> objeto`.",
                "O grafo fica com nós folha e nenhuma aresta.",
            )
        )
    if triplas:
        identicas = Counter((item["sujeito"], item["relacao"], item["objeto"]) for item in triplas)
        for (sujeito, relacao, objeto), vezes in identicas.items():
            if vezes > 1:
                problemas.append(
                    finding(
                        "nice",
                        "tripla-repetida",
                        f"{vezes}× a mesma relação",
                        f"{sujeito} → {relacao} → {objeto}",
                        "A mesma tripla foi declarada mais de uma vez.",
                        "Repetição exata infla a contagem de arestas sem acrescentar memória.",
                        "Nada a corrigir: o grafo deduplica.",
                        "Sem deduplicação, o grau do nó ficaria artificialmente alto.",
                    )
                )
                break
    if qualquer_maiuscula_ruim := [item for item in rows if item["tipo"] == "sigla" and len(item["entidade"]) > 6]:
        problemas.append(
            finding(
                "nice",
                "sigla-longa",
                f"{len(qualquer_maiuscula_ruim)} sigla(s) com mais de seis letras",
                ", ".join(item["entidade"] for item in qualquer_maiuscula_ruim[:4]),
                "Sequência de maiúsculas longa foi lida como sigla.",
                "Texto todo em maiúscula costuma ser ênfase, não sigla.",
                "Escreva a sigla e o nome por extenso na primeira ocorrência.",
                "O mesmo conceito entra duas vezes no grafo com nomes diferentes.",
            )
        )
    if ignorados:
        problemas.append(
            finding(
                "should",
                "linha-longa",
                f"{ignorados} linha(s) ignorada(s) por tamanho",
                f"limite de 20.000 caracteres por linha",
                "Linha gigante não foi varrida.",
                "Linha acima do limite costuma ser payload colado, não memória.",
                "Cole o texto em parágrafos.",
                "Entidade dentro dessa linha não entra no grafo.",
            )
        )

    findings, counts, veredito, perguntas = finalize(problemas, modo, _questoes() if modo == "ultra" else [])
    if modo == "lite":
        rows = rows if counts["must"] else rows[:0]
    metricas = {
        "entidades": len(rows),
        "linhas": len(linhas),
        "triplas": len(triplas),
        "repetidas": len(repetidas),
        **{f"tipo_{tipo}": por_tipo.get(tipo, 0) for tipo in TIPOS_ENTIDADE},
    }
    resumo = [
        f"**{len(rows)} entidades** em {len(linhas)} linhas: "
        + ", ".join(f"{por_tipo.get(tipo, 0)} {tipo}{_plural(tipo)}" for tipo in TIPOS_ENTIDADE if por_tipo.get(tipo))
        + f"; {len(triplas)} tripla{_plural('tripla')} declarada{_plural('tripla')}.",
        "Extração lexical por padrão — nenhum modelo de linguagem foi chamado.",
    ]
    extra: list[str] = []
    if triplas:
        extra = [
            "",
            "## Relações declaradas",
            "",
            "| Sujeito | Relação | Objeto | Linha |",
            "|---|---|---|---|",
            *[
                f"| {item['sujeito']} | `{item['relacao']}` | {item['objeto']} | {item['linha']} |"
                for item in triplas[:30]
            ],
        ]
    return common(
        analysis="memoria.entidades",
        mode=modo,
        title="Extração de entidades",
        summary=resumo,
        findings=findings,
        counts=counts,
        verdict=veredito,
        questions=perguntas,
        rows=rows,
        metrics=metricas,
        limitations=[
            "A extração é lexical: nome próprio em minúscula e entidade sem maiúscula não são vistas.",
            "Relação só entra na forma `sujeito -> relação -> objeto` em português ou inglês.",
            "Nada é enviado a modelo: não há desambiguação nem resolução de correferência.",
        ],
        extra_sections=extra,
    )


# ---------------------------------------------------------------- grafo

@dataclass
class Grafo:
    """Grafo dirigido simples: nó é entidade, aresta é relação declarada."""

    nos: dict[str, dict[str, Any]]
    arestas: list[tuple[str, str, str]]
    adjacencia: dict[str, set[str]]
    sucessores: dict[str, set[str]]
    antecessores: dict[str, set[str]]

    def grau_saida(self, no: str) -> int:
        return sum(1 for aresta in self.arestas if aresta[0] == no)

    def grau_entrada(self, no: str) -> int:
        return sum(1 for aresta in self.arestas if aresta[2] == no)

    def grau(self, no: str) -> int:
        return self.grau_saida(no) + self.grau_entrada(no)


def _componentes(grafo: Grafo) -> list[list[str]]:
    """Componentes conectados ignorando nó isolado — isolado já tem achado próprio."""
    vistos: set[str] = set()
    componentes: list[list[str]] = []
    for inicio in grafo.nos:
        if inicio in vistos or not grafo.adjacencia.get(inicio):
            continue
        pilha = [inicio]
        componentes_atual: list[str] = []
        while pilha:
            atual = pilha.pop()
            if atual in vistos:
                continue
            vistos.add(atual)
            componentes_atual.append(atual)
            pilha.extend(grafo.adjacencia.get(atual, ()))
        componentes.append(sorted(componentes_atual))
    return componentes


def _ciclos(grafo: Grafo, limite: int = MAX_CICLOS) -> list[list[str]]:
    """Ciclos simples na direção das arestas, sem repetir o mesmo conjunto de nós."""
    achados: list[list[str]] = []
    vistos: set[frozenset[str]] = set()

    def visitar(inicio: str, atual: str, caminho: list[str]) -> None:
        if len(achados) >= limite:
            return
        for vizinho in sorted(grafo.sucessores.get(atual, ())):
            if vizinho == inicio and len(caminho) >= 2:
                conjunto = frozenset(caminho)
                if conjunto not in vistos:
                    vistos.add(conjunto)
                    achados.append([*caminho, inicio])
                continue
            if vizinho in caminho or vizinho < inicio:
                continue
            visitar(inicio, vizinho, [*caminho, vizinho])

    for no in sorted(grafo.nos):
        visitar(no, no, [no])
    return achados[:limite]


def ler_grafo(*, texto: str) -> Grafo:
    """Lê o grafo declarado em `nó -> relação -> nó` ou em JSON de arestas."""
    bruto = (texto or "").strip()
    if not bruto:
        raise MemoriaError("Informe as arestas: `A -> relação -> B`, uma por linha, ou o JSON com `arestas`.")
    if len(bruto) > MAX_TEXTO:
        raise MemoriaError(f"O texto passa de {MAX_TEXTO:,} caracteres.")

    nos: dict[str, dict[str, Any]] = {}
    arestas: list[tuple[str, str, str]] = []

    def registrar_no(nome: str) -> str:
        limpo = " ".join(nome.split()).strip(" .,;:")
        chave = _slug(limpo)
        if not chave:
            raise MemoriaError(f"Nó sem nome válido: {nome!r}.")
        nos.setdefault(chave, {"no": limpo, "chave": chave})
        return chave

    if bruto.startswith("{"):
        try:
            dados = json.loads(bruto)
        except json.JSONDecodeError as exc:
            raise MemoriaError(f"JSON inválido na linha {exc.lineno}: {exc.msg}.") from exc
        itens = dados.get("arestas") if isinstance(dados, dict) else None
        if not isinstance(itens, list) or not itens:
            raise MemoriaError("O JSON precisa da chave `arestas` com pelo menos uma aresta.")
        for item in itens:
            if not isinstance(item, dict):
                raise MemoriaError("Cada aresta do JSON precisa ser um objeto com `de`, `relacao` e `para`.")
            de = str(item.get("de", "")).strip()
            relacao = str(item.get("relacao", "")).strip()
            para = str(item.get("para", "")).strip()
            if not de or not para or not relacao:
                raise MemoriaError("Aresta incompleta: `de`, `relacao` e `para` são obrigatórios.")
            arestas.append((registrar_no(de), _slug(relacao), registrar_no(para)))
    else:
        for numero, linha in enumerate(bruto.split("\n"), start=1):
            limpa = linha.strip()
            if not limpa or limpa.startswith("#"):
                continue
            partes = re.split(r"\s*(?:->|→|=>)\s*", limpa)
            if len(partes) == 1:
                registrar_no(limpa)
                continue
            if len(partes) == 2:
                de, para = partes
                relacao = "relaciona"
            elif len(partes) == 3:
                de, relacao, para = partes
            else:
                raise MemoriaError(
                    f"Linha {numero} sem aresta reconhecível: {_resumo(limpa, 50)}. Use `A -> relação -> B`."
                )
            if not relacao.strip():
                relacao = "relaciona"
            arestas.append((registrar_no(de), _slug(relacao), registrar_no(para)))

    if len(arestas) > MAX_TRIPLAS:
        raise MemoriaError(f"O grafo passa de {MAX_TRIPLAS:,} arestas.")
    if len(nos) > MAX_ENTRADAS:
        raise MemoriaError(f"O grafo passa de {MAX_ENTRADAS:,} nós.")

    adjacencia: dict[str, set[str]] = {chave: set() for chave in nos}
    sucessores: dict[str, set[str]] = {chave: set() for chave in nos}
    antecessores: dict[str, set[str]] = {chave: set() for chave in nos}
    for de, _, para in arestas:
        adjacencia[de].add(para)
        adjacencia[para].add(de)
        sucessores[de].add(para)
        antecessores[para].add(de)
    return Grafo(
        nos=nos,
        arestas=arestas,
        adjacencia=adjacencia,
        sucessores=sucessores,
        antecessores=antecessores,
    )


def montar_grafo(*, arestas: str, modo: str = "full") -> dict[str, Any]:
    """Mede o grafo declarado: grau, componente, ciclo, hub e nó folha."""
    modo = _modo(modo)
    grafo = ler_grafo(texto=arestas)
    componentes = _componentes(grafo)
    ciclos = _ciclos(grafo)

    graus = {chave: grafo.grau(chave) for chave in grafo.nos}
    ordem = sorted(grafo.nos, key=lambda chave: (-graus[chave], chave))
    maior = max(graus.values()) if graus else 0

    rows: list[dict[str, Any]] = []
    for chave in ordem[:MAX_ROWS]:
        no = grafo.nos[chave]
        entrada = grafo.grau_entrada(chave)
        saida = grafo.grau_saida(chave)
        grau = graus[chave]
        if grau == 0:
            situacao = "isolado"
        elif grau >= MAX_GRAU:
            situacao = "hub"
        elif entrada == 0:
            situacao = "origem"
        elif saida == 0:
            situacao = "folha"
        else:
            situacao = "interno"
        rows.append(
            {
                "no": no["no"],
                "grau": grau,
                "entrada": entrada,
                "saida": saida,
                "situacao": situacao,
                "componente": next((indice + 1 for indice, item in enumerate(componentes) if chave in item), 0),
            }
        )

    isolados = [grafo.nos[chave]["no"] for chave in grafo.nos if graus[chave] == 0]
    hubs = [grafo.nos[chave]["no"] for chave in ordem if graus[chave] >= MAX_GRAU]
    folhas = [grafo.nos[chave]["no"] for chave in grafo.nos if graus[chave] == 1]
    maior_componente = max((len(item) for item in componentes), default=0)
    ligados = len(grafo.nos) - len(isolados)
    cobertura = 100.0 * maior_componente / ligados if ligados else 0.0

    problemas: list[dict[str, Any]] = []
    if not grafo.arestas:
        problemas.append(
            finding(
                "must",
                "grafo-vazio",
                "Nenhuma aresta declarada",
                "grafo",
                "Há nós, mas nenhuma relação entre eles.",
                "Memória de grafo sem aresta não responde pergunta relacional nenhuma.",
                "Escreva ao menos uma aresta `A -> relação -> B`.",
                "O recall por relação devolve nó solto.",
            )
        )
    if isolados:
        problemas.append(
            finding(
                "should",
                "no-isolado",
                f"{len(isolados)} nó(s) sem aresta",
                ", ".join(isolados[:5]),
                "Nó declarado que não aparece em nenhuma relação.",
                "Nó isolado não contribui para a vizinhança e não é alcançável por travessia.",
                "Ligue o nó ao que ele explica ou remova do envio.",
                "O grafo cresce em número de nós sem crescer em memória.",
            )
        )
    if len(componentes) > 1 and ligados:
        problemas.append(
            finding(
                "should",
                "grafo-fragmentado",
                f"{len(componentes)} componente(s) desconectado(s)",
                f"maior componente tem {maior_componente} de {ligados} nó(s) ligado(s) ({_fmt_pct(cobertura)})",
                "O grafo tem ilhas que não se alcançam.",
                "Pergunta que atravessa duas ilhas não é respondida por travessia.",
                "Declare a aresta que liga os assuntos, mesmo que seja `relaciona`.",
                "A busca por vizinhança só vê a ilha de partida.",
            )
        )
    if ciclos:
        exemplo = " → ".join(grafo.nos[chave]["no"] for chave in ciclos[0])
        problemas.append(
            finding(
                "should",
                "ciclo",
                f"{len(ciclos)} ciclo(s) simples",
                _resumo(exemplo, 90),
                "As relações formam caminho de volta ao nó de origem.",
                "Ciclo faz travessia sem profundidade máxima repetir nó e inflar contexto.",
                "Se a relação é de identidade (`é`, `substitui`), troque por `relaciona` e diga a diferença.",
                "A expansão de vizinhança pode não terminar sem um teto explícito.",
            )
        )
    if hubs:
        problemas.append(
            finding(
                "nice",
                "hub",
                f"{len(hubs)} nó(s) com grau {MAX_GRAU} ou mais",
                ", ".join(hubs[:5]),
                "Nó concentra muitas relações.",
                "Hub é atalho para tudo e por isso não diferencia nada na recuperação.",
                "Confira se o hub não é um rótulo genérico (`sistema`, `projeto`) que deveria ser um tipo.",
                "A busca por vizinhança do hub devolve o grafo inteiro.",
            )
        )
    if grafo.nos and len(folhas) == len(grafo.nos) and len(grafo.nos) > 2:
        problemas.append(
            finding(
                "nice",
                "grafo-estrela",
                "todos os nós são folha",
                f"{len(grafo.nos)} nós",
                "Toda relação tem um nó de grau 1.",
                "Grafo em estrela responde só o par pergunta→resposta, sem cadeia.",
                "Nada a corrigir se a memória é rasa por desenho.",
                "Pergunta de duas etapas não encontra o segundo salto.",
            )
        )

    findings, counts, veredito, perguntas = finalize(problemas, modo, _questoes() if modo == "ultra" else [])
    metricas = {
        "nos": len(grafo.nos),
        "arestas": len(grafo.arestas),
        "componentes": len(componentes),
        "maior_componente": maior_componente,
        "cobertura": round(cobertura, 1),
        "ciclos": len(ciclos),
        "isolados": len(isolados),
        "hubs": len(hubs),
        "folhas": len(folhas),
        "grau_maximo": maior,
        "densidade": round(len(grafo.arestas) / max(1, len(grafo.nos)), 2),
    }
    resumo = [
        f"**{len(grafo.nos)} nós** e **{len(grafo.arestas)} arestas** em {len(componentes)} componente(s); "
        f"maior componente com {_fmt_pct(cobertura)} dos nós.",
        f"{len(isolados)} isolado(s), {len(hubs)} hub(s), {len(folhas)} folha(s) e {len(ciclos)} ciclo(s).",
    ]
    extra: list[str] = []
    if ciclos:
        extra = ["", "## Ciclos", ""]
        extra += [f"- {' → '.join(grafo.nos[chave]['no'] for chave in ciclo)}" for ciclo in ciclos[:10]]
    return common(
        analysis="memoria.grafo",
        mode=modo,
        title="Grafo de memória",
        summary=resumo,
        findings=findings,
        counts=counts,
        verdict=veredito,
        questions=perguntas,
        rows=rows,
        metrics=metricas,
        limitations=[
            "A leitura é declarada: a camada não infere aresta do texto corrido.",
            "Relações diferentes entre o mesmo par viram arestas separadas, mas a adjacência é não dirigida.",
            "Ciclo é contado em nós, não em arestas paralelas.",
        ],
        extra_sections=extra,
    )


# --------------------------------------------------------------- sessão

RE_TURNO = re.compile(
    r"^\s*(?:\[(?P<hora>[^\]]*)\]\s*)?(?P<papel>usu[áa]rio|user|humano|agente|assistente|assistant|bot|sistema|system)\s*:\s*(?P<texto>.*)$",
    re.IGNORECASE,
)
RE_MARCADOR = re.compile(
    r"^\s*(?:\*\*)?(decis[ãa]o|decidido|li[çc][ãa]o|aprendizado|li[çc][ãa]o|regra|conven[çc][ãa]o|aten[çc][ãa]o|"
    r"nunca|sempre|armadilha|erro|cuidado)(?:\*\*)?\s*[:—-]\s*(?P<texto>.+)$",
    re.IGNORECASE,
)
RE_FEEDBACK = re.compile(r"feedback\s*[:=]\s*(-?\d+)", re.IGNORECASE)
RE_TURNO_FRACO = re.compile(r"\b(ok|okay|certo|sim|não|talvez|obrigado|thanks|valeu|beleza|entendi)\b", re.IGNORECASE)
RE_FATO = re.compile(
    r"\b(é|são|foi|foram|tem|têm|usa|usam|exige|permite|fica|contém|possui|concorda|responde|aceita)\b",
    re.IGNORECASE,
)


@dataclass
class Turno:
    numero: int
    papel: str
    texto: str
    hora: str


def _ler_turnos(bruto: str) -> list[Turno]:
    turnos: list[Turno] = []
    atual: Turno | None = None
    for numero, linha in enumerate(bruto.split("\n"), start=1):
        casado = RE_TURNO.match(linha)
        if casado:
            papel = _normalizar(casado.group("papel"))
            if papel in {"usuario", "user", "humano"}:
                papel = "usuario"
            elif papel in {"agente", "assistente", "assistant", "bot"}:
                papel = "agente"
            else:
                papel = "sistema"
            atual = Turno(numero=numero, papel=papel, texto=casado.group("texto").strip(), hora=(casado.group("hora") or "").strip())
            turnos.append(atual)
            continue
        if atual is not None and linha.strip():
            atual.texto = f"{atual.texto}\n{linha.strip()}".strip()
    return turnos


def _candidatos(turnos: list[Turno]) -> list[dict[str, Any]]:
    """Pontua cada turno como lição em potencial: marcador, verbo de fato, feedback e repetição."""
    textos = [_normalizar(turno.texto) for turno in turnos]
    contagem = Counter(textos)
    candidatos: list[dict[str, Any]] = []
    for turno, texto in zip(turnos, textos):
        if turno.papel == "sistema":
            continue
        limpo = turno.texto.strip()
        if len(limpo) < 20:
            continue
        pontos = 0.0
        motivos: list[str] = []
        marcador = RE_MARCADOR.match(limpo)
        if marcador:
            pontos += 3.0
            motivos.append(f"marcador `{_normalizar(marcador.group(1))}`")
        if turno.papel == "usuario" and RE_FATO.search(limpo):
            pontos += 1.0
            motivos.append("verbo de fato do usuário")
        if turno.papel == "agente":
            if marcador:
                motivos.append("regra declarada pelo agente")
            else:
                pontos -= 0.5
                motivos.append("fala do agente")
        if len(limpo) >= MIN_TEXTO_LICAO:
            pontos += 1.0
            motivos.append("texto com corpo")
        if RE_TURNO_FRACO.search(limpo) and len(limpo) < 60:
            pontos -= 2.0
            motivos.append("confirmação curta")
        if contagem[texto] > 1:
            pontos += 1.5
            motivos.append(f"repetido {contagem[texto]}×")
        feedback = RE_FEEDBACK.search(limpo)
        if feedback:
            valor = int(feedback.group(1))
            if valor < 0:
                pontos -= 3.0
                motivos.append(f"feedback {valor}")
            elif valor >= FEEDBACK_RUIM:
                pontos += 2.0
                motivos.append(f"feedback +{valor}")
        if pontos <= 0:
            continue
        candidatos.append(
            {
                "turno": turno.numero,
                "papel": turno.papel,
                "texto": _resumo(limpo, MAX_TEXTO_LICAO),
                "pontos": round(pontos, 1),
                "motivos": motivos,
                "tipo": _tipo_de_memoria(limpo, marcador.group(1) if marcador else ""),
                "hora": turno.hora,
                "repeticoes": contagem[texto],
            }
        )
    candidatos.sort(key=lambda item: (-item["pontos"], item["turno"]))
    return candidatos


def _tipo_de_memoria(texto: str, marcador: str) -> str:
    chave = _normalizar(marcador or "")
    if chave in {"decisao", "decidido", "licao", "aprendizado"}:
        return "decisao" if chave in {"decisao", "decidido"} else "regra"
    if chave in {"regra", "convencao", "nunca", "sempre"}:
        return "regra"
    if chave in {"armadilha", "erro", "cuidado", "atencao"}:
        return "procedimento"
    if RE_ARQUIVO.search(texto) or RE_CODIGO.search(texto):
        return "codigo"
    if RE_TEMPORAL.search(texto):
        return "evento"
    if RE_TRIPLA_PT.search(texto) or RE_TRIPLA_EN.search(texto):
        return "relacao"
    if RE_FATO.search(texto):
        return "fato"
    return "resumo"


def destilar_sessao(*, conversa: str, limiar: float = LIMIAR_PROMOCAO, modo: str = "full") -> dict[str, Any]:
    """Promove lição da sessão para memória permanente com nota, motivo e destino."""
    modo = _modo(modo)
    bruto = (conversa or "").strip()
    if not bruto:
        raise MemoriaError("Cole a conversa: a destilação lê turno a turno o que você colar.")
    if len(bruto) > MAX_TEXTO:
        raise MemoriaError(f"A conversa passa de {MAX_TEXTO:,} caracteres.")
    if not isinstance(limiar, (int, float)) or limiar < 1 or limiar > 10:
        raise MemoriaError("O limiar precisa ficar entre 1 e 10.")

    turnos = _ler_turnos(bruto)
    if not turnos:
        raise MemoriaError("Nenhum turno reconhecido. Use `usuário: …` e `agente: …`, um turno por bloco.")
    if len(turnos) > MAX_TURNOS:
        raise MemoriaError(f"A conversa passa de {MAX_TURNOS:,} turnos.")

    candidatos = _candidatos(turnos)
    if not candidatos:
        candidatos = []
    promovidos = [item for item in candidatos if item["pontos"] >= limiar][:MAX_CANDIDATOS]
    descartados = [item for item in candidatos if item["pontos"] < limiar]
    pendentes = [item for item in candidatos if limiar - 1.0 <= item["pontos"] < limiar]

    rows: list[dict[str, Any]] = []
    for indice, item in enumerate(candidatos[:MAX_ROWS], start=1):
        rows.append(
            {
                "turno": item["turno"],
                "papel": item["papel"],
                "pontos": f"{item['pontos']:.1f}",
                "tipo": item["tipo"],
                "decisao": "promove" if item["pontos"] >= limiar else "descarta",
                "motivo": "; ".join(item["motivos"]),
                "texto": item["texto"],
            }
        )

    problemas: list[dict[str, Any]] = []
    if not promovidos:
        problemas.append(
            finding(
                "should",
                "sessao-sem-licao",
                "Nenhuma lição passou do limiar",
                f"{len(turnos)} turnos, limiar {limiar:.1f}",
                "A sessão não tem decisão, regra nem aprendizado explícito acima do limiar.",
                "Promover conversa fiada enche a memória permanente de ruído que volta em todo recall.",
                "Escreva a lição com marcador (`decisão:`, `regra:`, `aprendizado:`) ou aceite não promover nada.",
                "A próxima sessão herda contexto sem valor.",
            )
        )
    if len(promovidos) > MAX_CANDIDATOS:
        problemas.append(
            finding(
                "should",
                "sessao-grande",
                f"{len(promovidos)} lições acima do limiar",
                f"teto de {MAX_CANDIDATOS}",
                "Muita lição promovida de uma vez.",
                "Sessão que promove tudo não destilou nada — só copiou a conversa.",
                "Escolha as que mudam a próxima decisão e descarte o resto.",
                "A memória permanente vira log de conversa.",
            )
        )
    agentes_com_regra = [item for item in promovidos if item["papel"] == "agente"]
    if agentes_com_regra:
        problemas.append(
            finding(
                "should",
                "regra-do-agente",
                f"{len(agentes_com_regra)} lição(ões) vindas do agente",
                ", ".join(f"turno {item['turno']}" for item in agentes_com_regra[:4]),
                "O agente, não a pessoa, declarou a regra que será promovida.",
                "Regra que o agente escreve sobre si mesmo não é decisão do time.",
                "Confirme a regra com quem usa o sistema antes de promover.",
                "O agente passa a citar como acordado algo que só ele escreveu.",
            )
        )
    sem_tipo = [item for item in promovidos if item["tipo"] == "resumo"]
    if sem_tipo:
        problemas.append(
            finding(
                "nice",
                "licao-sem-tipo",
                f"{len(sem_tipo)} lição(ões) sem classe",
                ", ".join(f"turno {item['turno']}" for item in sem_tipo[:4]),
                "A lição não se encaixa em fato, regra, decisão nem procedimento.",
                "Sem classe, a lição entra no recall por afinidade e sem vizinhança.",
                "Diga o que ela é: regra, decisão, fato ou procedimento.",
                "O grafo recebe nó que não conversa com os outros.",
            )
        )
    if pendentes:
        problemas.append(
            finding(
                "nice",
                "quase-promovido",
                f"{len(pendentes)} lição(ões) a um passo do limiar",
                ", ".join(f"turno {item['turno']} ({item['pontos']:.1f})" for item in pendentes[:4]),
                "Candidato que ficou logo abaixo do limiar.",
                "A diferença entre promover e descartar aqui é de décimos.",
                "Acrescente o porquê de cada uma e a lição passa.",
                "Fica de fora uma lição que talvez devesse entrar.",
            )
        )

    findings, counts, veredito, perguntas = finalize(problemas, modo, _questoes() if modo == "ultra" else [])
    por_tipo = Counter(item["tipo"] for item in promovidos)
    metricas = {
        "turnos": len(turnos),
        "candidatos": len(candidatos),
        "promovidos": len(promovidos),
        "descartados": len(descartados),
        "pendentes": len(pendentes),
        "limiar": limiar,
        "do_agente": len(agentes_com_regra),
        "do_usuario": len([item for item in promovidos if item["papel"] == "usuario"]),
        "repetidos": len([item for item in promovidos if item["repeticoes"] > 1]),
        **{f"tipo_{tipo}": por_tipo.get(tipo, 0) for tipo in TIPOS_MEMORIA if por_tipo.get(tipo)},
    }
    resumo = [
        f"**{len(turnos)} turnos** geraram {len(candidatos)} candidato(s); **{len(promovidos)} passaram** do limiar {limiar:.1f} "
        f"e {len(descartados)} ficaram de fora.",
        "A nota soma marcador explícito, verbo de fato, repetição e feedback — e desconta fala do agente, confirmação curta e feedback negativo.",
    ]
    extra: list[str] = []
    if promovidos:
        extra = ["", "## Lições promovidas", ""]
        extra += [
            f"- **turno {item['turno']}** ({item['tipo']}, {item['pontos']:.1f}) — {item['texto']}"
            for item in promovidos
        ]
    return common(
        analysis="memoria.sessao",
        mode=modo,
        title="Destilação da sessão",
        summary=resumo,
        findings=findings,
        counts=counts,
        verdict=veredito,
        questions=perguntas,
        rows=rows,
        metrics=metricas,
        limitations=[
            "A leitura é lexical: a camada não entende ironia, correção posterior nem contexto externo.",
            "Feedback só é lido na forma `feedback: 3` (ou `feedback=-1`), dentro do turno.",
            "Promover aqui não grava nada: o parecer é a lista do que você deve gravar.",
        ],
        extra_sections=extra,
    )


# --------------------------------------------------------------- recall

@dataclass
class Memorias:
    id: str
    tipo: str
    texto: str
    criado: str
    fonte: str
    dataset: str


def ler_memorias(*, texto: str) -> list[Memorias]:
    """Lê memória em `id | tipo | criado | fonte | dataset | texto` ou em JSON."""
    bruto = (texto or "").strip()
    if not bruto:
        raise MemoriaError("Informe as memórias: uma por linha, com `id | tipo | criado | fonte | dataset | texto`, ou o JSON.")
    if len(bruto) > MAX_TEXTO:
        raise MemoriaError(f"O texto passa de {MAX_TEXTO:,} caracteres.")

    itens: list[Memorias] = []
    if bruto.startswith("{"):
        try:
            dados = json.loads(bruto)
        except json.JSONDecodeError as exc:
            raise MemoriaError(f"JSON inválido na linha {exc.lineno}: {exc.msg}.") from exc
        brutos = dados.get("memorias") if isinstance(dados, dict) else None
        if not isinstance(brutos, list) or not brutos:
            raise MemoriaError("O JSON precisa da chave `memorias` com pelo menos um item.")
        for indice, item in enumerate(brutos, start=1):
            if not isinstance(item, dict):
                raise MemoriaError(f"A memória {indice} precisa ser um objeto.")
            corpo = str(item.get("texto", "")).strip()
            if not corpo:
                raise MemoriaError(f"A memória {indice} está sem `texto`.")
            itens.append(
                Memorias(
                    id=str(item.get("id") or f"m{indice}").strip(),
                    tipo=_normalizar(str(item.get("tipo") or "fato")),
                    texto=corpo,
                    criado=str(item.get("criado") or "").strip(),
                    fonte=str(item.get("fonte") or "—").strip() or "—",
                    dataset=str(item.get("dataset") or "padrao").strip() or "padrao",
                )
            )
    else:
        for numero, linha in enumerate(bruto.split("\n"), start=1):
            limpa = linha.strip()
            if not limpa or limpa.startswith("#"):
                continue
            partes = [parte.strip() for parte in limpa.split("|")]
            if len(partes) < 2:
                raise MemoriaError(f"Linha {numero} sem separador: use `id | tipo | criado | fonte | dataset | texto`.")
            if len(partes) == 2:
                identificador, corpo = partes
                tipo, criado, fonte, dataset = "fato", "", "—", "padrao"
            else:
                if len(partes) < 6:
                    partes += ["—"] * (6 - len(partes))
                identificador, tipo, criado, fonte, dataset = partes[0], _normalizar(partes[1]) or "fato", partes[2], partes[3] or "—", partes[4] or "padrao"
                corpo = " | ".join(partes[5:]).strip()
            if not identificador or not corpo:
                raise MemoriaError(f"Linha {numero} sem id ou sem texto.")
            itens.append(Memorias(id=identificador, tipo=tipo, texto=corpo, criado=criado, fonte=fonte, dataset=dataset))

    if len(itens) > MAX_ENTRADAS:
        raise MemoriaError(f"O conjunto passa de {MAX_ENTRADAS:,} memórias: divida por dataset e pergunte por um deles.")
    vistos: set[str] = set()
    for item in itens:
        if item.id in vistos:
            raise MemoriaError(f"Id repetido: `{item.id}`. O id é a chave do esquecimento e precisa ser único.")
        vistos.add(item.id)
    return itens


def _bm25(consulta: list[str], documentos: list[list[str]]) -> list[float]:
    if not documentos:
        return []
    total = len(documentos)
    tamanho_medio = sum(len(doc) for doc in documentos) / total or 1.0
    frequencias = [Counter(doc) for doc in documentos]
    df = Counter()
    for doc in documentos:
        for termo in set(doc):
            df[termo] += 1
    scores: list[float] = []
    for indice, doc in enumerate(documentos):
        score = 0.0
        for termo in consulta:
            tf = frequencias[indice].get(termo, 0)
            if not tf:
                continue
            idf = math.log(1 + (total - df[termo] + 0.5) / (df[termo] + 0.5))
            denominador = tf + K1 * (1 - B + B * (len(doc) / tamanho_medio))
            score += idf * (tf * (K1 + 1)) / denominador
        scores.append(score)
    return scores


def _decair(criado: str, hoje: date) -> float:
    data = _data(criado)
    if data is None:
        return 0.5
    dias = max(0, (hoje - data).days)
    return math.exp(-dias * math.log(2) / MEIA_VIDA_DIAS)


def consultar_memoria(
    *,
    consulta: str,
    memorias: str,
    via: str = "",
    dataset: str = "",
    limite: int = 10,
    hoje: str = "",
    modo: str = "full",
) -> dict[str, Any]:
    """Recupera memória por via declarada ou roteada e devolve cada item com lastro."""
    modo = _modo(modo)
    texto = (consulta or "").strip()
    if not texto:
        raise MemoriaError("Informe a consulta.")
    if len(texto) > MAX_TEXTO:
        raise MemoriaError(f"A consulta passa de {MAX_TEXTO:,} caracteres.")
    if via and via not in VIAS:
        raise MemoriaError(f"Via inválida: {via}. Use {', '.join(VIAS)} ou deixe vazio para rotear.")
    if limite < MIN_RESULTADOS if False else limite < 1 or limite > MAX_RESULTADOS:
        raise MemoriaError(f"O limite fica entre 1 e {MAX_RESULTADOS}.")
    data_hoje = _data(hoje) if hoje else date.today()
    if hoje and data_hoje is None:
        raise MemoriaError("A data de hoje precisa estar no formato AAAA-MM-DD.")

    itens = ler_memorias(texto=memorias)
    rota = rotear_consulta(consulta=texto, modo="full")
    via_final = via or rota["metrics"]["via"]
    filtradas = [item for item in itens if not dataset or item.dataset == dataset]
    if not filtradas:
        raise MemoriaError(f"Nenhuma memória no dataset `{dataset}`.")

    consulta_tokens = _termos(texto)
    documentos = [_termos(item.texto) for item in filtradas]
    scores = _bm25(consulta_tokens, documentos)

    linhas: list[dict[str, Any]] = []
    for item, doc, score in zip(filtradas, documentos, scores):
        intersectado = len(set(consulta_tokens) & set(doc))
        cobertura = 100.0 * intersectado / len(set(consulta_tokens)) if consulta_tokens else 0.0
        recencia = _decair(item.criado, data_hoje)
        sinal_via = 0.0
        if via_final == "temporal" and item.criado:
            sinal_via += 0.5
        if via_final == "codigo" and (RE_ARQUIVO.search(item.texto) or RE_CODIGO.search(item.texto)):
            sinal_via += 0.5
        if via_final == "regras" and item.tipo in {"regra", "decisao", "procedimento"}:
            sinal_via += 0.5
        if via_final == "procedimento" and item.tipo in {"procedimento", "regra"}:
            sinal_via += 0.5
        if via_final == "grafo" and (RE_TRIPLA_PT.search(item.texto) or RE_TRIPLA_EN.search(item.texto)):
            sinal_via += 0.5
        if via_final == "resumo" and len(item.texto) > 200:
            sinal_via += 0.5
        pontuacao = score + PESO_AFINIDADE * (cobertura / 100.0) + PESO_RECENCIA * recencia + sinal_via
        if item.criado and data_hoje and _data(item.criado) and (data_hoje - _data(item.criado)).days > MEMORIA_VENCIDA_DIAS:  # type: ignore[operator]
            pontuacao -= 0.3
        linhas.append(
            {
                "id": item.id,
                "tipo": item.tipo,
                "dataset": item.dataset,
                "criado": item.criado or "—",
                "afinidade": round(min(1.0, cobertura / 100.0), 3),
                "bm25": round(score, 3),
                "recencia": round(recencia, 3),
                "via": via_final,
                "pontuacao": round(pontuacao, 3),
                "fonte": item.fonte,
                "texto": _resumo(item.texto, 160),
            }
        )

    linhas.sort(key=lambda row: (-row["pontuacao"], row["id"]))
    for indice, linha in enumerate(linhas, start=1):
        linha["ordem"] = indice
    descartadas = [linha for linha in linhas if linha["bm25"] == 0]
    com_lastro = [linha for linha in linhas if linha["bm25"] > 0]
    topo = (com_lastro or linhas)[:limite]
    sem_lastro = [linha for linha in topo if linha["afinidade"] < COBERTURA_MINIMA / 100]
    zeradas = [] if com_lastro else topo
    vencidas = [linha for linha in topo if linha["criado"] != "—" and _data(linha["criado"]) and (data_hoje - _data(linha["criado"])).days > MEMORIA_VENCIDA_DIAS]  # type: ignore[operator]

    problemas: list[dict[str, Any]] = []
    if descartadas and com_lastro:
        problemas.append(
            finding(
                "nice",
                "sem-lastro-descartado",
                f"{len(descartadas)} item(ns) fora do resultado por lastro zero",
                ", ".join(linha["id"] for linha in descartadas[:5]),
                "Item do recorte não casa nenhum termo da consulta.",
                "Devolver item sem afinidade é ruído que ocupa contexto e não responde.",
                "Nada a corrigir: o corte é de propósito; se quiser o histórico inteiro, peça por via `temporal`.",
                "Sem o corte, o contexto do agente enche de memória irrelevante.",
            )
        )
    if not com_lastro:
        problemas.append(
            finding(
                "should",
                "resultado-fraco",
                "nenhum item casa termo da consulta",
                f"{len(topo)} devolvido(s) por recência e tipo",
                "A consulta não tem termo em comum com a memória do recorte.",
                "Resultado sem afinidade não sustenta resposta: é palpite com carimbo de memória.",
                "Use os termos que estão na memória, filtre por dataset ou reformule a pergunta.",
                "O agente cita memória que não fala do assunto.",
            )
        )
    if not topo:
        problemas.append(
            finding(
                "must",
                "sem-resultado",
                "Nenhuma memória no recorte",
                f"dataset `{dataset or 'todos'}`",
                "O filtro não deixou nenhum item.",
                "Recall vazio faz o agente afirmar que não sabe o que está na memória.",
                "Confira o dataset ou importe a memória antes.",
                "A resposta volta sem lastro nenhum.",
            )
        )
    if vencidas:
        problemas.append(
            finding(
                "should",
                "memoria-vencida",
                f"{len(vencidas)} memória(s) acima de {MEMORIA_VENCIDA_DIAS} dias",
                ", ".join(linha["id"] for linha in vencidas[:5]),
                "Item antigo ainda sendo recuperado.",
                "Memória velha sobrevive a decisão nova e passa a contradizer o presente.",
                "Confirme o fato ou rode o esquecimento por escopo.",
                "A resposta cita como vigente algo que já mudou.",
            )
        )
    if sem_lastro and not zeradas:
        problemas.append(
            finding(
                "nice",
                "lastro-baixo",
                f"{len(sem_lastro)} resultado(s) abaixo de {COBERTURA_MINIMA}% de termos",
                ", ".join(linha["id"] for linha in sem_lastro[:5]),
                "Poucos termos da consulta aparecem no item.",
                "Resultado de lastro baixo entra no contexto sem sustentar a afirmação.",
                "Peça a fonte (`cite a fonte`) ou aumente a especificidade da consulta.",
                "O agente cita memória que não fala do assunto.",
            )
        )
    if dataset and len(filtradas) < 3:
        problemas.append(
            finding(
                "nice",
                "dataset-pequeno",
                f"{len(filtradas)} memória(s) no dataset",
                dataset,
                "Dataset com menos de três itens.",
                "Amostra pequena: a cobertura não representa a memória do domínio.",
                "Nada a corrigir se o dataset é novo.",
                "A resposta parece mais completa do que é.",
            )
        )

    findings, counts, veredito, perguntas = finalize(problemas, modo, _questoes() if modo == "ultra" else [])
    metricas = {
        "memorias": len(itens),
        "recorte": len(filtradas),
        "resultados": len(topo),
        "via": via_final,
        "roteada": 0 if via else 1,
        "dataset": dataset or "todos",
        "descartados": len(descartadas),
        "vencidas": len(vencidas),
        "cobertura_media": round(
            100.0 * sum(linha["afinidade"] for linha in topo) / len(topo), 1
        ) if topo else 0.0,
        "topo": round(topo[0]["pontuacao"], 3) if topo else 0.0,
    }
    resumo = [
        f"Via `{via_final}`" + (" (roteada pela pergunta)" if not via else " (declarada)")
        + f" sobre {len(filtradas)} memória(s) do dataset `{dataset or 'todos'}`: **{len(topo)} resultado(s)**.",
        f"Pontuação = BM25 + {PESO_AFINIDADE:.1f}×afinidade + {PESO_RECENCIA:.1f}×recência (meia-vida de {MEIA_VIDA_DIAS:.0f} dias) + sinal da via.",
    ]
    extra: list[str] = []
    if topo:
        extra = [
            "",
            "## Lastro de cada resultado",
            "",
            "| # | Id | Tipo | BM25 | Afinidade | Recência | Pontuação |",
            "|---|---|---|---|---|---|---|",
            *[
                f"| {linha['ordem']} | `{linha['id']}` | {linha['tipo']} | {linha['bm25']:.2f} | "
                f"{_fmt_pct(linha['afinidade'] * 100)} | {linha['recencia']:.2f} | {linha['pontuacao']:.2f} |"
                for linha in topo
            ],
        ]
    return common(
        analysis="memoria.recall",
        mode=modo,
        title="Recall com lastro",
        summary=resumo,
        findings=findings,
        counts=counts,
        verdict=veredito,
        questions=perguntas,
        rows=topo,
        metrics=metricas,
        limitations=[
            "A afinidade é lexical (BM25): sinônimo e paráfrase não aproximam.",
            "A data de criação vem do que você declarou; sem data, a recência vale 0,5 para todo mundo.",
            "O lastro mede termo em comum, não verdade: memória errada continua errada.",
        ],
        extra_sections=extra,
    )


# ------------------------------------------------------------ esquecer

ESCOPOS_ESQUECIMENTO = ("item", "dataset", "tudo")


def _raio_de_alcance(itens: list[Memorias], alvo: Memorias) -> int:
    """Quantos itens do conjunto falam de alguma entidade citada no alvo."""
    entidades = set()
    extraido = extrair_entidades(texto=alvo.texto)
    for linha in extraido["rows"]:
        entidades.add(_normalizar(linha["entidade"]))
    if not entidades:
        return 1
    tocados = 0
    for item in itens:
        normalizado = _normalizar(item.texto)
        if any(entidade and entidade in normalizado for entidade in entidades):
            tocados += 1
    return max(1, tocados)


def esquecer(
    *,
    memorias: str,
    ids: str = "",
    dataset: str = "",
    escopo: str = "item",
    somente_memoria: bool = False,
    modo: str = "full",
) -> dict[str, Any]:
    """Remove por item, por dataset ou tudo — e mede o raio de alcance antes de apagar."""
    modo = _modo(modo)
    if escopo not in ESCOPOS_ESQUECIMENTO:
        raise MemoriaError(f"Escopo inválido: {escopo}. Use {', '.join(ESCOPOS_ESQUECIMENTO)}.")
    if escopo == "item" and not (ids or "").strip():
        raise MemoriaError("No escopo `item`, informe ao menos um id para esquecer.")
    if escopo == "dataset" and not (dataset or "").strip():
        raise MemoriaError("No escopo `dataset`, informe o nome do dataset.")

    itens = ler_memorias(texto=memorias)
    pedidos = [parte.strip() for parte in re.split(r"[,\s]+", ids or "") if parte.strip()]
    if escopo == "item":
        alvo_ids = set(pedidos)
        alvos = [item for item in itens if item.id in alvo_ids]
        ausentes = sorted(alvo_ids - {item.id for item in alvos})
        if ausentes:
            raise MemoriaError(f"Id não encontrado: {', '.join(ausentes)}.")
    elif escopo == "dataset":
        alvos = [item for item in itens if item.dataset == dataset]
        if not alvos:
            raise MemoriaError(f"Nenhuma memória no dataset `{dataset}`.")
    else:
        alvos = list(itens)

    restantes = [item for item in itens if item not in alvos]
    alcance_total = 0
    rows: list[dict[str, Any]] = []
    for item in alvos:
        alcance = _raio_de_alcance(itens, item) if escopo != "tudo" else len(itens)
        alcance_total += alcance
        rows.append(
            {
                "id": item.id,
                "dataset": item.dataset,
                "tipo": item.tipo,
                "criado": item.criado or "—",
                "alcance": alcance,
                "acao": "apaga memória" if somente_memoria else "apaga tudo",
                "texto": _resumo(item.texto, 110),
            }
        )
    dependentes = [item for item in restantes if escopo == "item"]
    entidades_alvo = {
        _normalizar(linha["entidade"])
        for alvo in alvos
        for linha in extrair_entidades(texto=alvo.texto)["rows"]
        if _normalizar(linha["entidade"])
    }
    compartilham = [
        dependente
        for dependente in dependentes
        if any(entidade in _normalizar(dependente.texto) for entidade in entidades_alvo)
    ]

    problemas: list[dict[str, Any]] = []
    if escopo == "tudo":
        problemas.append(
            finding(
                "must",
                "esquecimento-total",
                f"apaga as {len(itens)} memória(s)",
                "escopo `tudo`",
                "O pedido remove a memória inteira, não um item.",
                "Não há desfazer: a camada não grava nem restaura nada.",
                "Confirme duas vezes, ou use `dataset` para limitar o alcance.",
                "Toda resposta futura volta sem memória.",
            )
        )
    if escopo == "item" and len(alvos) == 1 and alcance_total > 1:
        problemas.append(
            finding(
                "should",
                "raio-de-alcance",
                f"uma remoção afeta {alcance_total} memória(s)",
                ", ".join(row["id"] for row in rows[:5]),
                "O item carrega entidade citada em outros itens.",
                "Apagar o item deixa os outros falando de algo que não existe mais no grafo.",
                "Apague os dependentes na mesma chamada ou reescreva o que sobrou.",
                "O grafo fica com aresta apontando para nó inexistente.",
            )
        )
    if compartilham:
        problemas.append(
            finding(
                "should",
                "dependentes",
                f"{len(compartilham)} memória(s) citam entidade do alvo",
                ", ".join(item.id for item in compartilham[:5]),
                "Outros itens mencionam a mesma entidade.",
                "Esquecer só o alvo deixa afirmação órfã sobre a mesma entidade.",
                "Inclua os ids dependentes ou use `dataset` para apagar o bloco inteiro.",
                "O recall continua devolvendo o assunto que você quis esquecer.",
            )
        )
    if somente_memoria:
        problemas.append(
            finding(
                "nice",
                "somente-memoria",
                "arquivo bruto preservado",
                f"{len(alvos)} item(ns)",
                "O escopo `memory_only` remove grafo e vetor e mantém o original.",
                "Sem o bruto, o dataset não pode ser reprocessado com outro modelo.",
                "Nada a corrigir: é o comportamento pedido.",
                "O conteúdo continua no disco mesmo depois do esquecimento.",
            )
        )
    if not restantes:
        problemas.append(
            finding(
                "must",
                "memoria-vazia",
                "o recorte fica vazio",
                f"{len(alvos)} de {len(itens)}",
                "Todas as memórias do conjunto serão removidas.",
                "Conjunto vazio faz o próximo recall falhar em vez de responder pouco.",
                "Mantenha ao menos uma memória por dataset.",
                "O agente perde o contexto inteiro daquele domínio.",
            )
        )

    findings, counts, veredito, perguntas = finalize(problemas, modo, _questoes() if modo == "ultra" else [])
    metricas = {
        "memorias": len(itens),
        "apagadas": len(alvos),
        "restantes": len(restantes),
        "escopo": escopo,
        "raio": alcance_total,
        "dependentes": len(compartilham),
        "somente_memoria": 1 if somente_memoria else 0,
        "datasets": len({item.dataset for item in itens}),
    }
    resumo = [
        f"Escopo `{escopo}`: **{len(alvos)} de {len(itens)} memória(s)** saem"
        + (f" (só a memória: o bruto fica)" if somente_memoria else " inteiras")
        + f"; {len(restantes)} permanecem.",
        f"Raio de alcance somado: {alcance_total} — {len(compartilham)} item(ns) fora do alvo citam entidade apagada.",
    ]
    return common(
        analysis="memoria.esquecer",
        mode=modo,
        title="Esquecimento por escopo",
        summary=resumo,
        findings=findings,
        counts=counts,
        verdict=veredito,
        questions=perguntas,
        rows=rows[:MAX_ROWS],
        metrics=metricas,
        limitations=[
            "O raio de alcance usa as entidades que a própria camada extrai: nome em minúscula não é visto.",
            "Nada é apagado de verdade: a camada devolve o plano e o que sobra.",
            "Dependente fora do conjunto informado não aparece no raio.",
        ],
    )


def memoria_catalogo() -> dict[str, Any]:
    """Publica vias, pesos, tipos, limites e a semântica de cada operação."""
    return {
        "versao": VERSAO,
        "origem": {
            "projeto": "topoteretes/cognee",
            "licenca": "Apache-2.0",
            "estrelas": 32_723,
            "operacoes": ["remember", "recall", "improve", "forget"],
        },
        "principio": (
            "Memória de agente é o que sobrevive à sessão: rotear a pergunta, ligar entidade por relação, "
            "promover só a lição que muda a próxima decisão e esquecer com raio de alcance declarado."
        ),
        "vias": [
            {"via": via, "prioridade": PRIORIDADE_VIA[via], "padrao": via == VIA_PADRAO}
            for via in VIAS
        ],
        "roteamento": {
            "limiar": LIMIAR_ROTA,
            "margem_minima": MARGEM_MINIMA,
            "janela_negacao": JANELA_NEGACAO,
            "regras": [
                {"via": regra.via, "regra": regra.etiqueta, "peso": regra.peso, "padrao": regra.padrao.pattern}
                for regra in REGRAS_ROTA
            ],
            "negacao": NEGACAO.pattern,
        },
        "entidades": {
            "tipos": list(TIPOS_ENTIDADE),
            "tipos_memoria": list(TIPOS_MEMORIA),
            "relacoes_aceitas": [
                "foi", "é", "era", "trabalha", "trabalhou", "nasceu", "mora", "pertence", "usa",
                "depende de", "substitui", "criou", "escreveu", "mantém", "publicou", "fundou",
                "comprou", "vendeu", "migrou", "integra",
            ],
            "papel": ["professor", "engenheiro", "autor", "diretor", "fundador", "membro", "responsável", "coordenador"],
        },
        "grafo": {
            "formato": "A -> relação -> B, uma por linha; linha sozinha declara nó isolado; JSON com `arestas`",
            "grau_hub": MAX_GRAU,
            "ciclos_maximos": MAX_CICLOS,
        },
        "sessao": {
            "limiar_padrao": LIMIAR_PROMOCAO,
            "max_candidatos": MAX_CANDIDATOS,
            "marcadores": ["decisão", "decidido", "lição", "aprendizado", "regra", "convenção", "nunca", "sempre", "armadilha", "erro", "cuidado"],
            "pesos": {
                "marcador": 3.0,
                "verbo_de_fato_do_usuario": 1.0,
                "texto_com_corpo": 1.0,
                "repeticao": 1.5,
                "feedback_positivo": 2.0,
                "feedback_negativo": -3.0,
                "fala_do_agente": -0.5,
                "confirmacao_curta": -2.0,
            },
        },
        "recall": {
            "bm25": {"k1": K1, "b": B},
            "peso_afinidade": PESO_AFINIDADE,
            "peso_recencia": PESO_RECENCIA,
            "meia_vida_dias": MEIA_VIDA_DIAS,
            "cobertura_minima": COBERTURA_MINIMA,
            "memoria_vencida_dias": MEMORIA_VENCIDA_DIAS,
            "formula": "pontuacao = BM25 + 0.6*afinidade + 0.4*recencia + sinal_da_via",
        },
        "esquecimento": {
            "escopos": list(ESCOPOS_ESQUECIMENTO),
            "memory_only": "remove grafo e vetor e mantém o arquivo bruto",
            "raio_de_alcance": "conta itens que citam entidade do alvo antes de apagar",
        },
        "limites": {
            "texto": MAX_TEXTO,
            "entradas": MAX_ENTRADAS,
            "arestas": MAX_TRIPLAS,
            "turnos": MAX_TURNOS,
            "resultados": MAX_RESULTADOS,
            "linhas_por_tabela": MAX_ROWS,
        },
        "modos": list(MODOS),
        "deixado_de_fora": [
            "Chamar modelo de linguagem para extrair entidade, escolher via ou gerar resposta.",
            "Gerar embedding, abrir banco de grafo, gravar sessão ou aplicar feedback.",
            "Baixar conector (Google Drive, Gmail), plugin de IDE ou servidor MCP.",
            "Resolver correferência, traduzir pergunta ou fundir entidade com nome diferente.",
            "Julgar se a memória é verdadeira: o lastro mede termo em comum, não fato.",
        ],
        "executed": False,
        "readOnly": True,
    }
