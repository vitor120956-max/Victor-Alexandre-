"""Rigor científico determinístico — adaptação de K-Dense-AI/scientific-agent-skills (MIT, 2026).

Nada é executado, baixado ou calculado sobre dados que o texto não traz: as
contas são as da fórmula publicada, e a conferência de um texto é lexical, com
a evidência citada. Nenhum script do upstream (power.py, simulate_power.py,
randomization.py, check_accuracy_precision.py) é instalado ou chamado, e nenhum
modelo de linguagem participa da decisão.
"""
from __future__ import annotations

import math
import re
import statistics
from typing import Any

from .review import common, finalize, finding

VERSAO = "0.61.2"

MAX_TEXTO = 120_000

MODOS = ("lite", "full", "ultra")

CINZA = "-\u2014"


class CienciaError(ValueError):
    """Entrada inválida; a API devolve 200 com `ok:false` e a mensagem do erro."""


# ------------------------------------------------------------------ utilidades

def _modo(modo: str) -> str:
    if modo not in MODOS:
        raise CienciaError("Nível aceita lite, full ou ultra.")
    return modo


def _norm(texto: str) -> str:
    return re.sub(r"\s+", " ", texto or "").strip().lower()


def _contem(texto: str, termo: str) -> bool:
    """Casamento por palavra inteira, insensível a caixa e acento."""
    import unicodedata

    alvo = "".join(c for c in unicodedata.normalize("NFD", _norm(texto)) if unicodedata.category(c) != "Mn")
    agulha = "".join(c for c in unicodedata.normalize("NFD", _norm(termo)) if unicodedata.category(c) != "Mn")
    return re.search(rf"(?<!\w){re.escape(agulha)}(?!\w)", alvo) is not None


def _num(valor: float, casas: int = 0) -> str:
    if not math.isfinite(valor):
        return "—"
    inteiro = f"{valor:,.{casas}f}"
    return inteiro.replace(",", "\u00a0").replace(".", ",").replace("\u00a0", ".")


def _pct(valor: float, casas: int = 2) -> str:
    return f"{_num(valor, casas)}%"


def _n(total: float, um: str, muitos: str) -> str:
    return f"{_num(total, 0)} {um if abs(total) == 1 else muitos}"


def _texto(valor: Any) -> str:
    return "" if valor is None else str(valor)


def _linhas(valor: str) -> list[str]:
    return [linha.strip() for linha in (valor or "").replace("\r", "").split("\n") if linha.strip()]


def _frases(texto: str) -> list[str]:
    partes = re.split(r"(?<=[.!?])\s+", (texto or "").strip())
    return [parte.strip() for parte in partes if parte.strip()]


def _palavras(texto: str) -> list[str]:
    return re.findall(r"\b[\wÀ-ÿ'-]+\b", texto or "")


def _trecho(texto: str, inicio: int, fim: int, largura: int = 70) -> str:
    """Devolve o trecho em volta do casamento, para citar a evidência."""
    esquerda = max(0, inicio - largura // 2)
    direita = min(len(texto), fim + largura // 2)
    pedaco = re.sub(r"\s+", " ", texto[esquerda:direita]).strip()
    return ("…" if esquerda else "") + pedaco + ("…" if direita < len(texto) else "")


def _z(probabilidade: float) -> float:
    """Quantil da normal padrão (inverso da CDF)."""
    return statistics.NormalDist().inv_cdf(probabilidade)


def _decimal(bruto: str) -> float | None:
    """Converte `0,03`, `.03` e `3,5` em número."""
    limpo = bruto.strip().replace("%", "")
    if "," in limpo and "." in limpo:
        limpo = limpo.replace(".", "").replace(",", ".")
    else:
        limpo = limpo.replace(",", ".")
    try:
        return float(limpo)
    except ValueError:
        return None


# ------------------------------------------------------------------ 1. amostra

BENCHMARKS = {
    "d": (0.20, 0.50, 0.80),
    "f": (0.10, 0.25, 0.40),
    "r": (0.10, 0.30, 0.50),
    "eta2": (0.01, 0.06, 0.14),
    "h": (0.20, 0.50, 0.80),
    "w": (0.10, 0.30, 0.50),
    "r2": (0.02, 0.13, 0.26),
}

LIMITES_AMOSTRA = [
    "A conta é de duas amostras independentes e iguais ou desiguais por razão declarada; teste pareado, ANOVA de k grupos, sobrevida e modelos mistos precisam de outra fórmula.",
    "O efeito é o que você declara. Nenhum dado é lido e nenhum efeito é estimado a partir de resultado observado — poder calculado sobre o efeito observado é circular.",
    "A aproximação é normal. Para amostras muito pequenas o valor exato (t não central) difere em poucas unidades.",
    "Não há poder para equivalência, não inferioridade, sequencial ou bayesiano: cada um tem margem e regra de parada próprias.",
]


def dimensionar_estudo(
    *,
    teste: str,
    alfa: float = 0.05,
    poder: float = 0.80,
    alocacao: float = 1.0,
    perda: float = 0.0,
    comparacoes: int = 1,
    baseline: float = 0,
    efeito: float = 0,
    media_controle: float = 0,
    media_tratamento: float = 0,
    desvio: float = 0,
    cohen_d: float = 0,
    n_por_grupo: int = 0,
    tamanho_cluster: int = 0,
    icc: float = 0.0,
    modo: str = "full",
) -> dict[str, Any]:
    _modo(modo)
    if teste not in {"proporcoes", "medias"}:
        raise CienciaError("`teste` aceita proporcoes ou medias.")
    if not 0 < alfa < 0.5:
        raise CienciaError("Alfa é probabilidade: fica entre 0 e 0,5.")
    if not 0.5 <= poder < 0.999:
        raise CienciaError("Poder fica entre 0,5 e 0,999.")
    if alocacao <= 0 or alocacao > 20:
        raise CienciaError("A alocação é a razão n2/n1: fica entre 0 e 20.")
    if not 0 <= perda < 1:
        raise CienciaError("A perda é fração: 0,2 para 20%.")
    if comparacoes < 1 or comparacoes > 100:
        raise CienciaError("Comparações: de 1 a 100.")
    if tamanho_cluster < 0 or not 0 <= icc < 1:
        raise CienciaError("Cluster: tamanho >= 0 e ICC entre 0 e 1.")

    alfa_ajustado = alfa / comparacoes
    z_alfa = _z(1 - alfa_ajustado / 2)
    z_poder = _z(poder)
    r = alocacao
    linhas: list[dict[str, Any]] = [
        {"etapa": "Alfa ajustado", "numero": _num(alfa_ajustado, 5),
         "formula": "alfa ÷ comparações" if comparacoes > 1 else "alfa informado"},
        {"etapa": "z alfa", "numero": _num(z_alfa, 4), "formula": "Φ⁻¹(1 − alfa/2)"},
        {"etapa": "z poder", "numero": _num(z_poder, 4), "formula": "Φ⁻¹(poder)"},
    ]

    achados: list[dict[str, Any]] = []
    perguntas: list[str] = []

    if teste == "proporcoes":
        if not 0 < baseline < 100:
            raise CienciaError("A linha de base é percentual entre 0 e 100.")
        if efeito == 0 and baseline == 0:
            raise CienciaError("Informe a linha de base e o efeito relativo.")
        p1 = baseline / 100
        p2 = p1 * (1 + efeito / 100)
        if not 0 < p2 < 1:
            raise CienciaError("O efeito leva a proporção para fora de 0–100%.")
        delta = abs(p2 - p1)
        pbar = (p1 + r * p2) / (1 + r)
        q1, q2, qbar = 1 - p1, 1 - p2, 1 - pbar
        if n_por_grupo > 0:
            n1, n2 = float(n_por_grupo), math.ceil(r * n_por_grupo)
            poder_calculado = _poder_proporcoes(n1, n2, p1, p2, alfa_ajustado)
            linhas.append({"etapa": "Amostra informada", "numero": _num(n1, 0),
                           "formula": "n por grupo declarado"})
        else:
            numerador = (z_alfa * math.sqrt((1 + r) * pbar * qbar)
                         + z_poder * math.sqrt(p1 * q1 + r * p2 * q2)) ** 2
            n1 = math.ceil(numerador / (r * delta ** 2))
            n2 = math.ceil(r * n1)
            poder_calculado = _poder_proporcoes(n1, n2, p1, p2, alfa_ajustado)
            linhas.append({"etapa": "n por grupo", "numero": f"{n1} e {n2}",
                           "formula": "(zα√((1+r)p̄q̄) + zβ√(p1q1 + r·p2q2))² ÷ (r·(p2−p1)²)"})
        h = 2 * math.asin(math.sqrt(p2)) - 2 * math.asin(math.sqrt(p1))
        linhas.append({"etapa": "h de Cohen", "numero": _num(abs(h), 3), "formula": "2·arcsen√p2 − 2·arcsen√p1"})
        efeito_rotulo = _num(abs(p2 - p1) * 100, 2) + " p.p."
        if abs(h) < BENCHMARKS["h"][0]:
            achados.append(finding(
                "should", "efeito-pequeno", "Efeito menor que o limite convencional pequeno", f"h = {_num(abs(h), 3)}",
                "h de Cohen abaixo de 0,20 é convenção de efeito pequeno.",
                "Detectar esse tamanho exige amostra grande e o resultado raramente muda decisão.",
                "Justifique o efeito por decisão (SESOI), não por convenção.",
                "O estudo custa mais e conclui pouco.",
            ))
    else:
        if cohen_d > 0:
            d = cohen_d
        elif media_controle and media_tratamento and desvio > 0:
            d = abs(media_tratamento - media_controle) / desvio
        elif media_controle and desvio > 0 and efeito:
            d = abs(media_controle) * abs(efeito) / 100 / desvio
        else:
            raise CienciaError("Informe `cohen_d` ou média de controle, média de tratamento e desvio.")
        if not 0 < d < 10:
            raise CienciaError("O tamanho de efeito d precisa ficar entre 0 e 10.")
        if n_por_grupo > 0:
            n1, n2 = float(n_por_grupo), math.ceil(r * n_por_grupo)
            poder_calculado = _poder_medias(n1, n2, d, alfa_ajustado)
            linhas.append({"etapa": "Amostra informada", "numero": _num(n1, 0),
                           "formula": "n por grupo declarado"})
        else:
            n1 = math.ceil((z_alfa + z_poder) ** 2 * (1 + 1 / r) / d ** 2)
            n2 = math.ceil(r * n1)
            poder_calculado = _poder_medias(n1, n2, d, alfa_ajustado)
            linhas.append({"etapa": "n por grupo", "numero": f"{n1} e {n2}",
                           "formula": "(zα + zβ)² · (1 + 1/r) ÷ d²"})
        linhas.append({"etapa": "d de Cohen", "numero": _num(d, 3), "formula": "|média tratada − média controle| ÷ desvio"})
        efeito_rotulo = f"d = {_num(d, 2)}"
        if d < BENCHMARKS["d"][0]:
            achados.append(finding(
                "should", "efeito-pequeno", "Efeito menor que o limite convencional pequeno", f"d = {_num(d, 3)}",
                "d abaixo de 0,20 é convenção de efeito pequeno — e convenção, não medida.",
                "A amostra cresce ao quadrado quando o efeito encolhe.",
                "Ancore o efeito no menor valor que mudaria a decisão.",
                "O estudo fica caro para um resultado que não muda conduta.",
            ))

    deff = 1.0
    if tamanho_cluster > 1 and icc > 0:
        deff = 1 + (tamanho_cluster - 1) * icc
        n1 = math.ceil(n1 * deff)
        n2 = math.ceil(n2 * deff)
        linhas.append({"etapa": "Efeito de desenho", "numero": _num(deff, 3),
                       "formula": "1 + (m − 1)·ICC"})
        linhas.append({"etapa": "n após cluster", "numero": f"{n1} e {n2}",
                       "formula": "n × DEFF"})
        if tamanho_cluster * icc >= 1:
            achados.append(finding(
                "should", "cluster-inflado", "Cluster com ICC alto encarece o estudo", f"{tamanho_cluster} por cluster",
                "O efeito de desenho multiplica a amostra pelo tamanho do cluster.",
                "Com esse ICC, a amostra efetiva é uma fração pequena da amostra coletada.",
                "Reduza o cluster ou aumente o número de clusters, não o de unidades dentro deles.",
                "O estudo coleta muito e informa pouco.",
            ))

    total_analisado = n1 + n2
    n1_matricula = math.ceil(n1 / (1 - perda)) if perda > 0 else n1
    n2_matricula = math.ceil(n2 / (1 - perda)) if perda > 0 else n2
    linhas.append({"etapa": "Total analisado", "numero": _num(total_analisado, 0), "formula": "n1 + n2"})
    if perda > 0:
        linhas.append({"etapa": "Matrícula por grupo", "numero": f"{n1_matricula} e {n2_matricula}",
                       "formula": "n ÷ (1 − perda)"})
        linhas.append({"etapa": "Total a recrutar", "numero": _num(n1_matricula + n2_matricula, 0),
                       "formula": "matrícula 1 + matrícula 2"})

    if poder_calculado < 0.80:
        achados.append(finding(
            "must", "poder-baixo", "Poder abaixo de 80%", _pct(poder_calculado * 100),
            "Com a amostra informada, a chance de detectar o efeito declarado fica abaixo do convencional.",
            "Estudo subdimensionado produz resultado inconclusivo e desperdiça recurso.",
            f"Aumente para {math.ceil(max(n1, n2) * 1.2)} por grupo ou aceite um efeito maior.",
            "O resultado negativo não distingue ausência de efeito de falta de amostra.",
        ))
    if poder > 0.95:
        achados.append(finding(
            "nice", "poder-excessivo", "Poder acima de 95%", _pct(poder * 100),
            "Poder muito acima de 90% raramente é exigido fora de confirmação regulatória.",
            "Cada ponto de poder custa amostra; acima de 95% o custo cresce sem mudar a decisão.",
            "Padronize 80% (exploratório) ou 90% (confirmatório).",
            "Você recruta além do necessário.",
        ))
    if alfa > 0.05:
        achados.append(finding(
            "should", "alfa-frouxo", "Alfa acima do convencional", _num(alfa, 3),
            "Alfa é a taxa de falso positivo aceita; 0,05 é a convenção bilateral.",
            "Alfa maior aumenta o poder ao custo de mais falso positivo.",
            "Declare o custo dessa escolha ou volte para 0,05.",
            "O resultado positivo fica menos crível.",
        ))
    if perda >= 0.20:
        achados.append(finding(
            "should", "perda-alta", "Perda esperada de 20% ou mais", _pct(perda * 100),
            "Perda alta exige inflar a matrícula e ainda ameaça a validade.",
            "Quem sai do estudo raramente sai ao acaso.",
            "Declare a estratégia de retenção e a análise de dados faltantes.",
            "A amostra analisada pode não ser a amostra sorteada.",
        ))
    if comparacoes > 1:
        achados.append(finding(
            "should", "multiplicidade", "Mais de uma comparação", f"{comparacoes} comparações",
            "Cada teste extra aumenta o falso positivo da família.",
            "Sem correção, um achado entre vinte testes parece descoberta.",
            f"O alfa já foi corrigido para {_num(alfa_ajustado, 5)} por teste (Bonferroni).",
            "O achado positivo pode ser o vigésimo teste.",
        ))
    if n1 > 100_000:
        achados.append(finding(
            "should", "amostra-inviavel", "Amostra acima do plausível", _num(n1, 0),
            "A conta pede mais unidades do que qualquer estudo entrega.",
            "Efeito pequeno com variância alta produz exigência irreal.",
            "Reveja o efeito mínimo: aumente o efeito que vale detectar.",
            "O estudo não acontece — ou acontece subdimensionado.",
        ))
    if modo == "ultra" and n_por_grupo == 0:
        perguntas.append("O efeito declarado veio de qual estudo, piloto ou decisão clínica?")

    extra = ["", "## Cálculo", "",
             "| Etapa | Número | Fórmula |", "|---|---|---|"]
    for linha in linhas:
        extra.append(f"| {linha['etapa']} | {linha['numero']} | `{linha['formula']}` |")
    extra += ["", "## Efeito de referência", "",
              "| d | f | r | η² | h | w | R² |", "|---|---|---|---|---|---|---|",
              "| 0,20 / 0,50 / 0,80 | 0,10 / 0,25 / 0,40 | 0,10 / 0,30 / 0,50 | "
              "0,01 / 0,06 / 0,14 | 0,20 / 0,50 / 0,80 | 0,10 / 0,30 / 0,50 | "
              "0,02 / 0,13 / 0,26 |", "",
              "Pequeno / médio / grande por convenção de Cohen — convenção, não medida."]

    metrics = {
        "teste": teste, "n1": n1, "n2": n2, "total": total_analisado,
        "matricula": n1_matricula + n2_matricula, "perda": perda,
        "poder_alvo": poder, "poder_calculado": round(poder_calculado, 4),
        "alfa": alfa, "alfa_ajustado": round(alfa_ajustado, 6),
        "efeito": efeito_rotulo, "deff": round(deff, 4), "comparacoes": comparacoes,
    }
    achados, counts, veredito, perguntas = finalize(achados, modo, perguntas)
    return {
        **common(
            analysis="ciencia.amostra",
            mode=modo,
            title="Dimensionamento de estudo",
            summary=[
                f"{teste == 'proporcoes' and 'Duas proporções' or 'Duas médias'} com efeito {efeito_rotulo}, "
                f"alfa {_num(alfa, 3)} e poder alvo {_pct(poder * 100, 0)}.",
                f"A conta pede {_n(n1, 'unidade', 'unidades')} no primeiro grupo e {_n(n2, 'unidade', 'unidades')} no segundo"
                + (f", e {_n(n1_matricula + n2_matricula, 'matrícula', 'matrículas')} com {_pct(perda * 100, 0)} de perda." if perda else "."),
                f"Poder realizado com a amostra final: {_pct(poder_calculado * 100)}.",
            ],
            findings=achados,
            counts=counts,
            verdict=veredito,
            questions=perguntas,
            rows=linhas,
            metrics=metrics,
            limitations=LIMITES_AMOSTRA,
            extra_sections=extra,
        ),
        "executado": False,
    }


def _poder_proporcoes(n1: float, n2: float, p1: float, p2: float, alfa: float) -> float:
    pbar = (p1 * n1 + p2 * n2) / (n1 + n2)
    erro = math.sqrt(pbar * (1 - pbar) * (1 / n1 + 1 / n2))
    if erro == 0:
        return 1.0
    z = (abs(p2 - p1) - _z(1 - alfa / 2) * erro) / math.sqrt(
        p1 * (1 - p1) / n1 + p2 * (1 - p2) / n2)
    return max(0.0, min(1.0, statistics.NormalDist().cdf(z)))


def _poder_medias(n1: float, n2: float, d: float, alfa: float) -> float:
    nao_central = d / math.sqrt(1 / n1 + 1 / n2)
    critico = _z(1 - alfa / 2)
    return max(0.0, min(1.0, statistics.NormalDist().cdf(nao_central - critico)))


# --------------------------------------------------- 2. estatística do relato

STATS_LIMITES = [
    "A leitura é lexical e numérica sobre o texto colado: não há acesso a dados, saída de software ou suplemento.",
    "Ausência de um item não prova que a análise não foi feita; prova apenas que o relato não a mostra.",
    "Nenhum teste é reexecutado: os números citados são conferidos entre si, não contra os dados.",
    "Equivalência, não inferioridade e modelos bayesianos exigem margem e desenho próprios; aqui só se aponta a falta de margem.",
]


def auditar_estatistica(*, texto: str, modo: str = "full") -> dict[str, Any]:
    _modo(modo)
    if len(texto.strip()) < 40:
        raise CienciaError("Cole o trecho de resultados com os números.")
    if len(texto) > MAX_TEXTO:
        raise CienciaError("Texto acima do limite de leitura.")

    achados: list[dict[str, Any]] = []
    linhas: list[dict[str, Any]] = []
    perguntas: list[str] = []

    padrao_p = re.compile(r"\bp\s*([=<>≤≥])\s*(\d*[.,]?\d+|\d+)", re.I)
    citados: list[dict[str, Any]] = []
    for achado in padrao_p.finditer(texto):
        operador = achado.group(1)
        valor = _decimal(achado.group(2))
        if valor is None:
            continue
        status = "ok"
        if valor == 0 and operador == "=":
            status = "impossível"
            achados.append(finding(
                "must", "p-zero", "p = 0 não existe", _trecho(texto, achado.start(), achado.end()),
                "Um p-valor é uma probabilidade: nunca chega a zero.",
                "O software escreve `p < 0,001` e quem transcreve arredonda para zero.",
                "Escreva `p < 0,001`.",
                "O revisor reconhece transcrição descuidada e desconfia do resto.",
            ))
        elif valor > 1 or valor < 0:
            status = "impossível"
            achados.append(finding(
                "must", "p-impossivel", "p fora de 0–1", _trecho(texto, achado.start(), achado.end()),
                "p-valor é probabilidade entre 0 e 1.",
                "Valor fora do intervalo indica erro de transcrição ou de unidade.",
                "Confira a saída do teste.",
                "Todo o parágrafo perde credibilidade.",
            ))
        elif operador in {"<", ">"} and valor >= 0.001:
            status = "limiar"
            achados.append(finding(
                "should", "limiar-em-vez-de-valor", "Limiar no lugar do valor exato",
                _trecho(texto, achado.start(), achado.end()),
                "O relato pede o valor exato, e `p < 0,001` só abaixo de 0,001.",
                "`p < 0,05` esconde a distância até o limiar e impede quem lê de julgar.",
                f"Escreva `p = {_num(valor, 3)}` ou o valor que o software deu.",
                "A força da evidência fica ilegível.",
            ))
        citados.append({"tipo": "p", "valor": f"{operador} {_num(valor, 4)}", "status": status,
                        "evidencia": _trecho(texto, achado.start(), achado.end(), 50)})

    minusculo = texto.lower()
    if re.search(r"tend[eê]ncia|marginalmente|borderline", minusculo) and re.search(r"p\s*[=<>]\s*0[.,]0?[5-9]", minusculo):
        achados.append(finding(
            "should", "tendencia", "p perto de 0,05 chamado de tendência", "p entre 0,05 e 0,10",
            "“Tendência” não é categoria estatística, e p acima de 0,05 não indica tendência.",
            "A frase sugere efeito que o teste não sustenta.",
            "Relate o valor e o intervalo do efeito, sem rótulo de tendência.",
            "O leitor conclui o que o teste não mostrou.",
        ))
    tem_p = bool(padrao_p.search(texto))
    if re.search(r"significativ", minusculo) and not tem_p and not _contem(texto, "p"):
        achados.append(finding(
            "must", "significancia-sem-teste", "“Significativo” sem p-valor nem teste", "—",
            "Significância é uma decisão sobre um teste, com estatística e p.",
            "Sem o número, o adjetivo não é verificável.",
            "Cite o teste, a estatística, os graus de liberdade e o p.",
            "A afirmação central fica sem prova.",
        ))
    if re.search(r"\b(t|f|χ²|qui-quadrado|u|w)\s*\(\s*\d", texto) is None and re.search(r"\b[tF]\s*=\s*\d", texto):
        achados.append(finding(
            "should", "sem-graus-de-liberdade", "Estatística sem graus de liberdade", "—",
            "t, F e χ² se reportam com graus de liberdade entre parênteses.",
            "Sem eles não dá para reconstruir o teste nem o n.",
            "Escreva `t(98) = 3,82`, `F(2, 147) = 8,45`.",
            "O teste não é reproduzível.",
        ))
    if re.search(r"significativ|p\s*[=<>]", minusculo) and not re.search(
            r"\bd\s*=|η²|eta|r\s*=|OR\s*=|RR\s*=|β\s*=|Cohen", texto):
        achados.append(finding(
            "should", "sem-efeito", "Nenhum tamanho de efeito", "—",
            "p mede incompatibilidade com o nulo, não a magnitude do efeito.",
            "Sem efeito estimado, um p pequeno pode corresponder a diferença irrelevante.",
            "Reporte d, r, η², OR ou a diferença com unidade.",
            "O leitor não sabe se o efeito importa.",
        ))
    if re.search(r"significativ|p\s*[=<>]", minusculo) and not re.search(
            r"IC\s*9\d|CI\s*9\d|intervalo de confiança|\[[-\d.,;\s]+\]", texto):
        achados.append(finding(
            "should", "sem-intervalo", "Nenhum intervalo de confiança", "—",
            "O intervalo mostra a precisão da estimativa; o p não mostra.",
            "Duas estimativas com o mesmo p podem ter precisões muito diferentes.",
            "Acrescente o IC de 95% do efeito.",
            "A incerteza fica invisível.",
        ))
    n_casamento = re.search(r"\bn\s*=\s*(\d+)|\bN\s*=\s*(\d+)", texto)
    if not n_casamento:
        achados.append(finding(
            "should", "sem-n", "Nenhum tamanho de amostra", "—",
            "Todo número depende de quantas unidades entraram na conta.",
            "Sem n, média e proporção não têm denominador.",
            "Declare o n de cada grupo e o total analisado.",
            "O resultado não pode ser dimensionado.",
        ))
    else:
        n_valor = int(n_casamento.group(1) or n_casamento.group(2))
        if n_valor < 20 and "%" in texto:
            achados.append(finding(
                "should", "percentual-n-baixo", "Percentual com amostra pequena", f"n = {n_valor}",
                "Com n abaixo de 20, cada unidade muda o percentual em mais de cinco pontos.",
                "Percentual sem denominador exagera a precisão.",
                "Mostre a contagem (7 de 12) e não só o percentual.",
                "O leitor superestima a precisão.",
            ))
        linhas.append({"item": "Amostra", "valor": f"n = {n_valor}", "status": "ok"})
    if re.search(r"m[eé]dia", minusculo) and "±" not in texto and not re.search(r"\b(DP|SD|desvio)", texto):
        achados.append(finding(
            "should", "media-sem-dispersao", "Média sem desvio", "—",
            "Média sozinha não descreve distribuição.",
            "Duas amostras com a mesma média podem ter dispersões incompatíveis.",
            "Reporte média ± DP (ou mediana e IQR, se a distribuição não for simétrica).",
            "O leitor não vê a variabilidade.",
        ))
    if re.search(r"(equivalente|equivalência|não houve diferença|sem diferença|não diferiu)", minusculo) \
            and not re.search(r"margem|não inferioridade|equivalência.*\d", minusculo):
        achados.append(finding(
            "must", "equivalencia-sem-margem", "Equivalência afirmada sem margem", "—",
            "Não significativo não é equivalente: ausência de prova não é prova de ausência.",
            "Sem margem e teste de equivalência, o intervalo pode excluir efeito importante.",
            "Declare a margem e o teste de equivalência, ou troque a afirmação por “não foi possível detectar”.",
            "O estudo vira prova do que nunca testou.",
        ))
    if re.search(r"(prova que|comprova que|demonstra causalidade|portanto,?\s+\w+\s+causa)", minusculo):
        achados.append(finding(
            "should", "causalidade", "Causalidade afirmada no relato", "—",
            "Causalidade vem do desenho — randomização, controle, temporalidade —, não do p.",
            "Um teste significativo em desenho observacional não identifica causa.",
            "Troque “prova que” por “é compatível com” e diga qual desenho sustenta a inferência.",
            "A conclusão excede o desenho.",
        ))
    intervalo = re.search(r"(?:IC|CI)\s*9\d%?\s*[:=]?\s*\[?\s*(-?\d+[.,]?\d*)\s*[,;]\s*(-?\d+[.,]?\d*)\s*\]?", texto)
    if intervalo:
        limite_inferior = _decimal(intervalo.group(1))
        limite_superior = _decimal(intervalo.group(2))
        if limite_inferior is not None and limite_superior is not None:
            status = "ok" if limite_inferior <= limite_superior else "invertido"
            if status == "invertido":
                achados.append(finding(
                    "must", "ic-invertido", "Intervalo com limites trocados",
                    _trecho(texto, intervalo.start(), intervalo.end()),
                    "O limite inferior do IC vem antes do superior.",
                    "Intervalo invertido indica erro de transcrição.",
                    "Reordene os limites.",
                    "O leitor não consegue interpretar a precisão.",
                ))
            linhas.append({"item": "Intervalo", "valor": f"[{_num(limite_inferior, 2)}; {_num(limite_superior, 2)}]",
                           "status": status})
    if re.search(r"correla[cç][aã]o", minusculo) and not re.search(r"\br\s*=", texto):
        achados.append(finding(
            "should", "correlacao-sem-r", "Correlação sem coeficiente", "—",
            "Correlação se reporta pelo coeficiente e pelo intervalo.",
            "“Correlação forte” sem r não é verificável.",
            "Reporte r (ou ρ), o IC e o método.",
            "A força da associação fica no adjetivo.",
        ))
    if re.search(r"±\s*0[.,]?0*\b", texto):
        achados.append(finding(
            "must", "dispersao-zero", "Dispersão igual a zero", "± 0",
            "Desvio zero em dado biológico indica erro de arredondamento ou coluna trocada.",
            "Variância zero é improvável e quebra o teste.",
            "Confira a planilha e o número de decimais.",
            "O resultado é impossível.",
        ))
    if re.search(r"\b\d+[.,]\d{3,}\b", texto) and re.search(r"m[eé]dia|M\s*=", texto):
        achados.append(finding(
            "nice", "arredondamento", "Mais de duas casas em média ou desvio", "M/SD",
            "Média e desvio com três casas dão precisão que o n não sustenta.",
            "Casas a mais sugerem saída de software colada sem revisão.",
            "Arredonde para duas casas e mantenha a consistência.",
            "O número parece preciso sem ser.",
        ))
    if modo == "ultra":
        perguntas.append("Qual era o desfecho primário e quantos desfechos foram testados na mesma família?")
        perguntas.append("Como os dados faltantes foram tratados?")

    metrics = {
        "p_citados": len(citados),
        "com_efeito": bool(re.search(r"\bd\s*=|η²|r\s*=|OR\s*=|RR\s*=|β\s*=", texto)),
        "com_intervalo": bool(re.search(r"IC|CI", texto)),
        "n_declarado": int(n_casamento.group(1) or n_casamento.group(2)) if n_casamento else 0,
        "palavras": len(_palavras(texto)),
    }
    linhas = citados + linhas
    achados, counts, veredito, perguntas = finalize(achados, modo, perguntas)
    return {
        **common(
            analysis="ciencia.estatistica",
            mode=modo,
            title="Relato estatístico",
            summary=[
                f"{_n(len(citados), 'p-valor citado', 'p-valores citados')}, "
                f"{'com' if metrics['com_efeito'] else 'sem'} tamanho de efeito e "
                f"{'com' if metrics['com_intervalo'] else 'sem'} intervalo de confiança.",
                f"{_n(metrics['n_declarado'], 'unidade declarada', 'unidades declaradas')} na amostra citada.",
            ],
            findings=achados,
            counts=counts,
            verdict=veredito,
            questions=perguntas,
            rows=linhas,
            metrics=metrics,
            limitations=STATS_LIMITES,
        ),
        "executado": False,
    }


# ------------------------------------------------------------- 3. desenho

ITENS_DESENHO: list[dict[str, Any]] = [
    {
        "id": "randomizacao", "rotulo": "Randomização",
        "padroes": [r"randomiz", r"aleatori[sz]", r"sorteio", r"randomic"],
        "grupo": {"ensaio": "must", "animal": "must", "observacional": "nao", "diagnostico": "nao"},
        "porque": "Sem sorteio, quem escolhe o grupo também escolhe, mesmo sem querer, quem tem melhor prognóstico.",
        "correcao": "Descreva o sorteio e a sequência (simples, blocos, estratificado) e onde ela foi gerada.",
    },
    {
        "id": "alocacao", "rotulo": "Sigilo da alocação",
        "padroes": [r"aloca[cç][aã]o\s+(oculta|sigilosa|central)", r"envelope", r"central de randomiza"],
        "grupo": {"ensaio": "should", "animal": "should", "observacional": "nao", "diagnostico": "nao"},
        "porque": "Sequência previsível permite adiar ou adiantar a entrada de um caso.",
        "correcao": "Diga quem gerou a sequência e como o próximo grupo foi revelado.",
    },
    {
        "id": "cegamento", "rotulo": "Cegamento",
        "padroes": [r"cego", r"cegament", r"mascarad", r"\bblind"],
        "grupo": {"ensaio": "must", "animal": "should", "observacional": "nao", "diagnostico": "should"},
        "porque": "Quem mede sabendo o grupo tende a medir diferente, sobretudo em desfecho subjetivo.",
        "correcao": "Diga quem estava cego — participante, quem aplica, quem mede, quem analisa.",
    },
    {
        "id": "controle", "rotulo": "Controle concorrente",
        "padroes": [r"grupo\s+controle", r"placebo", r"\bsham\b", r"controle\s+(concorrente|ativo)",
                    r"comparador"],
        "grupo": {"ensaio": "must", "animal": "must", "observacional": "nao", "diagnostico": "nao"},
        "porque": "Sem controle no mesmo período, tempo, sazonalidade e manuseio se confundem com o tratamento.",
        "correcao": "Descreva o controle, o que ele recebeu e quando foi medido.",
    },
    {
        "id": "unidade", "rotulo": "Unidade de inferência",
        "padroes": [r"unidade\s+(experimental|de\s+an[aá]lise)", r"cada\s+(animal|paciente|sujeito|amostra)",
                    r"por\s+(animal|sujeito|paciente)"],
        "grupo": {"ensaio": "should", "animal": "must", "observacional": "should", "diagnostico": "should"},
        "porque": "O n é o número de unidades que receberam o tratamento, não o de medições feitas nelas.",
        "correcao": "Declare qual unidade foi sorteada e qual foi medida.",
    },
    {
        "id": "bloqueio", "rotulo": "Bloqueio ou estratificação",
        "padroes": [r"\bbloco", r"blocos", r"estratific", r"lote", r"batch", r"placa"],
        "grupo": {"ensaio": "nice", "animal": "should", "observacional": "nice", "diagnostico": "nice"},
        "porque": "Lote, dia e placa variam; se a condição coincide com o lote, o efeito é do lote.",
        "correcao": "Distribua as condições dentro de cada bloco e diga quais fatores foram blocados.",
    },
    {
        "id": "primario", "rotulo": "Desfecho primário",
        "padroes": [r"desfecho\s+prim[aá]rio", r"endpoint\s+prim[aá]rio", r"desfecho\s+principal",
                    r"primary\s+(outcome|endpoint)"],
        "grupo": {"ensaio": "must", "animal": "must", "observacional": "should", "diagnostico": "must"},
        "porque": "Sem desfecho declarado antes, qualquer resultado vira o principal depois de visto.",
        "correcao": "Nomeie um desfecho primário, a métrica e o momento da medida.",
    },
    {
        "id": "amostra", "rotulo": "Justificativa amostral",
        "padroes": [r"c[aá]lculo\s+amostral", r"tamanho\s+amostral", r"\bpoder\b", r"power\s+analysis",
                    r"amostra\s+de\s+\d+", r"n\s*=\s*\d+"],
        "grupo": {"ensaio": "must", "animal": "must", "observacional": "should", "diagnostico": "should"},
        "porque": "Sem conta de poder, o n é o que deu para coletar.",
        "correcao": "Informe efeito esperado, alfa, poder e a conta.",
    },
    {
        "id": "registro", "rotulo": "Pré-registro",
        "padroes": [r"pr[eé][- ]registr", r"protocolo\s+registrado", r"\bNCT\d{6,}", r"\bISRCTN\d+",
                    r"osf\.io", r"clinicaltrials\.gov"],
        "grupo": {"ensaio": "should", "animal": "nice", "observacional": "should", "diagnostico": "should"},
        "porque": "O registro fixa hipótese e desfecho antes do dado; é o que separa confirmar de procurar.",
        "correcao": "Cite o identificador e a versão do protocolo.",
    },
    {
        "id": "elegibilidade", "rotulo": "Critérios de elegibilidade",
        "padroes": [r"crit[eé]rios\s+de\s+inclus[aã]o", r"crit[eé]rios\s+de\s+exclus[aã]o",
                    r"elegibilidade", r"inclusion\s+criteria"],
        "grupo": {"ensaio": "should", "animal": "should", "observacional": "must", "diagnostico": "must"},
        "porque": "A população estudada é o que os critérios deixam entrar, não o título do artigo.",
        "correcao": "Liste inclusão, exclusão e o momento da avaliação.",
    },
    {
        "id": "perdas", "rotulo": "Perdas e exclusões",
        "padroes": [r"perdidos", r"perdas", r"exclu[ií]dos", r"desist", r"atrito", r"missing"],
        "grupo": {"ensaio": "should", "animal": "should", "observacional": "should", "diagnostico": "should"},
        "porque": "Quem sai do estudo raramente sai ao acaso; a amostra analisada deixa de ser a sorteada.",
        "correcao": "Informe quantos saíram, por quê e como a análise tratou os dados faltantes.",
    },
    {
        "id": "analise", "rotulo": "Análise pré-especificada",
        "padroes": [r"an[aá]lise\s+pr[eé][- ]especificada", r"plano\s+de\s+an[aá]lise",
                    r"an[aá]lise\s+prim[aá]ria", r"pr[eé]especific"],
        "grupo": {"ensaio": "should", "animal": "nice", "observacional": "should", "diagnostico": "should"},
        "porque": "Modelo escolhido depois de ver o dado se adapta ao resultado.",
        "correcao": "Diga qual análise foi planejada e o que foi exploratório.",
    },
    {
        "id": "confundimento", "rotulo": "Controle de confundimento",
        "padroes": [r"confundidor", r"confundimento", r"propensity", r"ajustad[oa]\s+por", r"vari[aá]veis\s+de\s+ajuste"],
        "grupo": {"ensaio": "nao", "animal": "nice", "observacional": "must", "diagnostico": "nao"},
        "porque": "Em estudo observacional, a comparação só vale se o confundimento for nomeado e tratado.",
        "correcao": "Liste os confundidores medidos, o momento da medida e o ajuste usado.",
    },
    {
        "id": "referencia", "rotulo": "Padrão de referência",
        "padroes": [r"padr[aã]o\s+de\s+refer[eê]ncia", r"gold\s+standard", r"teste\s+de\s+refer[eê]ncia"],
        "grupo": {"ensaio": "nao", "animal": "nao", "observacional": "nao", "diagnostico": "must"},
        "porque": "Acurácia diagnóstica é sempre relativa ao padrão usado.",
        "correcao": "Nomeie o padrão de referência, o limiar e quem mediu.",
    },
]

TIPOS_DESENHO = ("ensaio", "observacional", "diagnostico", "animal")

LIMITES_DESENHO = [
    "A leitura é lexical: presença da palavra não prova que o procedimento foi feito, e ausência não prova que não foi.",
    "Nenhum protocolo, registro ou suplemento é consultado — só o texto colado.",
    "O desenho é julgado pelos itens declarados, não pela qualidade dos dados, que não estão aqui.",
    "Risco de viés tem escalas próprias (RoB 2, ROBINS-I, QUADAS-2); esta conferência não substitui nenhuma.",
]


def auditar_desenho(*, texto: str, tipo: str = "ensaio", modo: str = "full") -> dict[str, Any]:
    _modo(modo)
    if tipo not in TIPOS_DESENHO:
        raise CienciaError("`tipo` aceita ensaio, observacional, diagnostico ou animal.")
    if len(texto.strip()) < 120:
        raise CienciaError("Cole o trecho de métodos; ele precisa de ao menos 120 caracteres.")
    if len(texto) > MAX_TEXTO:
        raise CienciaError("Texto acima do limite de leitura.")

    achados: list[dict[str, Any]] = []
    linhas: list[dict[str, Any]] = []
    perguntas: list[str] = []
    exigidos = presentes = 0

    for item in ITENS_DESENHO:
        grupo = item["grupo"].get(tipo, "nao")
        if grupo == "nao":
            continue
        casamento = None
        for padrao in item["padroes"]:
            casamento = re.search(padrao, texto, re.I)
            if casamento:
                break
        evidencia = _trecho(texto, casamento.start(), casamento.end()) if casamento else "—"
        if grupo in {"must", "should"}:
            exigidos += 1
            if casamento:
                presentes += 1
        linhas.append({
            "item": item["rotulo"],
            "status": "presente" if casamento else "ausente",
            "peso": grupo,
            "evidencia": evidencia,
        })
        if not casamento and grupo in {"must", "should"}:
            achados.append(finding(
                grupo, f"sem-{item['id']}", f"{item['rotulo']}: ausente do texto", item["rotulo"],
                item["porque"],
                "O relato não mostra o item; quem lê não pode avaliar a validade.",
                item["correcao"],
                "O revisor trata como omissão e o achado não pode ser distinguido de ausência real.",
            ))

    animais = re.search(r"(\d+)\s+(camundongos|ratos|animais|peixes|moscas|coelhos|porcos)", texto, re.I)
    celulas = re.search(r"(\d+)\s+(c[eé]lulas|po[cç]os|medi[cç][oõ]es|imagens|spots|campos|replicatas\s+t[eé]cnicas)", texto, re.I)
    if animais and celulas and re.search(r"cada|por\s+(animal|po[cç]o)", texto, re.I):
        achados.append(finding(
            "must", "pseudorreplicacao", "Pseudorreplicação aparente", f"{animais.group(1)} unidades biológicas",
            f"O texto cita {animais.group(1)} unidades e {celulas.group(1)} medidas dentro delas.",
            "Medição repetida na mesma unidade não é replicata independente: o n infla e o p encolhe.",
            "Conte o n pela unidade sorteada e analise com o aninhamento (modelo misto).",
            "O efeito pode ser artefato de uma única unidade.",
        ))
    if re.search(r"por\s+conveni[eê]ncia|primeiros\s+\w+\s+(a\s+)?(chegar|serem)|n[aã]o\s+randomiz", texto, re.I):
        achados.append(finding(
            "must", "atribuicao-por-conveniencia", "Atribuição não aleatória declarada", "—",
            "A ordem de chegada ou a disponibilidade define o grupo.",
            "Conveniência confunde tratamento com tempo, gravidade e acesso.",
            "Sorteie dentro de blocos ou assuma o desenho observacional e ajuste por confundidores.",
            "A comparação não sustenta causalidade.",
        ))

    cobertura = (presentes / exigidos * 100) if exigidos else 0.0
    if exigidos and cobertura < 60:
        achados.append(finding(
            "should", "cobertura-baixa", "Menos de 60% dos itens de desenho declarados", _pct(cobertura, 0),
            "O trecho cobre poucos itens que um revisor procura.",
            "A ausência de declaração impede separar desenho fraco de relato incompleto.",
            "Complete o relato dos métodos item a item.",
            "O estudo é lido como pior do que talvez seja.",
        ))
    if modo == "ultra":
        perguntas.append("Qual é a unidade sorteada, e o n declarado conta essa unidade?")
        perguntas.append("Quem sabia a alocação no momento da medida?")

    metrics = {
        "tipo": tipo, "itens": exigidos, "presentes": presentes,
        "ausentes": exigidos - presentes, "cobertura": round(cobertura, 1),
    }
    achados, counts, veredito, perguntas = finalize(achados, modo, perguntas)
    return {
        **common(
            analysis="ciencia.desenho",
            mode=modo,
            title="Desenho do estudo",
            summary=[
                f"Leitura de métodos como {tipo}, com {_n(exigidos, 'item exigido', 'itens exigidos')}.",
                f"{_n(presentes, 'item declarado', 'itens declarados')} — cobertura de {_pct(cobertura, 0)}.",
            ],
            findings=achados,
            counts=counts,
            verdict=veredito,
            questions=perguntas,
            rows=linhas,
            metrics=metrics,
            limitations=LIMITES_DESENHO,
        ),
        "executado": False,
    }


# --------------------------------------------------- 4. reprodutibilidade

ITENS_REPRO: list[dict[str, Any]] = [
    {"id": "dados", "rotulo": "Disponibilidade dos dados",
     "padroes": [r"dados\s+(est[aã]o\s+)?dispon", r"data\s+availability", r"zenodo", r"figshare",
                 r"dryad", r"osf\.io/\w+", r"depositad[oa]s?\s+em"],
     "grupo": "must", "porque": "Sem o dado, o resultado não pode ser recalculado.",
     "correcao": "Aponte o repositório, o DOI e a versão do conjunto."},
    {"id": "codigo", "rotulo": "Disponibilidade do código",
     "padroes": [r"c[oó]digo\s+(est[aá]\s+)?dispon", r"code\s+availability", r"github\.com", r"gitlab",
                 r"software\s+dispon"],
     "grupo": "must", "porque": "Sem o código, a transformação entre dado bruto e número não é verificável.",
     "correcao": "Publique o repositório com o commit usado e cite o DOI do arquivo."},
    {"id": "versao", "rotulo": "Versões de software",
     "padroes": [r"\bvers[aã]o\s+\d", r"\bv?\d+\.\d+\.\d+\b", r"version\s+\d", r"pacote\s+\w+\s+\d"],
     "grupo": "should", "porque": "Resultado que depende da versão do pacote muda quando a versão muda.",
     "correcao": "Liste pacote e versão de cada dependência que participou da conta."},
    {"id": "semente", "rotulo": "Semente aleatória",
     "padroes": [r"semente", r"\bseed\b", r"random_state", r"set\.seed"],
     "grupo": "should", "porque": "Sem a semente, o sorteio e a validação cruzada não se repetem.",
     "correcao": "Declare a semente e onde ela foi fixada."},
    {"id": "ambiente", "rotulo": "Ambiente computacional",
     "padroes": [r"docker", r"container", r"conda", r"renv", r"sessioninfo", r"singularity",
                 r"environment\.ya?ml", r"requirements\.txt", r"imagem\s+de"],
     "grupo": "should", "porque": "O ambiente é parte do método: biblioteca de sistema muda resultado.",
     "correcao": "Publique a imagem ou o arquivo de ambiente com a versão do interpretador."},
    {"id": "registro", "rotulo": "Protocolo registrado",
     "padroes": [r"pr[eé][- ]registr", r"protocolo\s+registrado", r"\bNCT\d{6,}", r"\bISRCTN\d+",
                 r"protocols\.io", r"clinicaltrials\.gov"],
     "grupo": "should", "porque": "O registro fixa hipótese e desfecho antes do dado.",
     "correcao": "Cite o registro, a data e a versão do protocolo."},
    {"id": "accession", "rotulo": "Identificadores de dados",
     "padroes": [r"\bGSE\d+", r"\bPRJ[EDN][A-Z]\d+", r"\bPXD\d+", r"\bSRR\d+", r"\bERR\d+",
                 r"\bEMD-\d+", r"\baccession\b", r"\bPDB\s?\w{4}\b"],
     "grupo": "should", "porque": "Identificador é o que liga o artigo ao dado depositado.",
     "correcao": "Cite o identificador de cada conjunto, não só o nome do repositório."},
    {"id": "licenca", "rotulo": "Licença do material",
     "padroes": [r"licen[cç]a", r"CC[-\s]?BY", r"\bMIT\b", r"Apache", r"GPL", r"c[oó]digo\s+aberto"],
     "grupo": "nice", "porque": "Licença diz o que terceiro pode fazer com o material.",
     "correcao": "Declare a licença de dados, código e materiais."},
    {"id": "materiais", "rotulo": "Materiais e reagentes",
     "padroes": [r"addgene", r"ATCC", r"cataloga", r"n[uú]mero\s+de\s+lote", r"reagente\s+de"],
     "grupo": "nice", "porque": "Lote e catálogo são o que permitem repetir o experimento.",
     "correcao": "Informe fabricante, catálogo e lote dos reagentes críticos."},
]

LIMITES_REPRO = [
    "A conferência é sobre o que o texto declara: nenhum repositório, DOI ou registro é acessado pela rede.",
    "Completude de disponibilidade não é qualidade do dado nem suficiência para reproduzir.",
    "Reprodução exige rodar o material com ambiente e comando documentados; isto aqui não roda nada.",
    "Restrição justificada (privacidade, contrato, biossegurança) é legítima; o que se aponta é a restrição sem motivo declarado.",
]


def auditar_reprodutibilidade(*, texto: str, modo: str = "full") -> dict[str, Any]:
    _modo(modo)
    if len(texto.strip()) < 60:
        raise CienciaError("Cole a seção de métodos e a de disponibilidade.")
    if len(texto) > MAX_TEXTO:
        raise CienciaError("Texto acima do limite de leitura.")

    achados: list[dict[str, Any]] = []
    linhas: list[dict[str, Any]] = []
    perguntas: list[str] = []
    exigidos = presentes = 0

    for item in ITENS_REPRO:
        casamento = None
        for padrao in item["padroes"]:
            casamento = re.search(padrao, texto, re.I)
            if casamento:
                break
        if item["id"] == "versao" and casamento and not re.search(r"\d+\.\d+", casamento.group(0)):
            casamento = None
        evidencia = _trecho(texto, casamento.start(), casamento.end()) if casamento else "—"
        if item["grupo"] in {"must", "should"}:
            exigidos += 1
            if casamento:
                presentes += 1
        linhas.append({"item": item["rotulo"], "status": "presente" if casamento else "ausente",
                       "peso": item["grupo"], "evidencia": evidencia})
        if not casamento and item["grupo"] in {"must", "should"}:
            achados.append(finding(
                item["grupo"], f"sem-{item['id']}", f"{item['rotulo']}: ausente do texto", item["rotulo"],
                item["porque"], "O material não aparece no relato, então a reprodução não começa.",
                item["correcao"], "A reprodução fica dependente de contato com os autores.",
            ))

    if re.search(r"sob\s+solicita[cç][aã]o|mediante\s+solicita|upon\s+request|available\s+on\s+request", texto, re.I):
        achados.append(finding(
            "should", "acesso-por-solicitacao", "Material apenas sob solicitação", "—",
            "“Sob solicitação” não é política de acesso: é ausência de política.",
            "O dado deixa de existir quando o autor muda de instituição ou deixa de responder.",
            "Deposite em repositório com DOI ou declare a restrição e o motivo.",
            "A reprodutibilidade depende da disponibilidade de uma pessoa.",
        ))
    if not re.search(r"restri[cç][aã]o|devido a|por\s+(motivo|raz[aã]o)|privacidade|contrato|biosseguran", texto, re.I):
        if re.search(r"acesso\s+restrito|embargad|confidencial", texto, re.I):
            achados.append(finding(
                "should", "restricao-sem-motivo", "Restrição de acesso sem motivo", "—",
                "Restrição é legítima quando nomeia o motivo e o prazo.",
                "Sem justificativa, a restrição é lida como recusa.",
                "Diga o motivo, o prazo e o canal de pedido.",
                "O revisor não distingue ética de conveniência.",
            ))

    cobertura = (presentes / exigidos * 100) if exigidos else 0.0
    if modo == "ultra":
        perguntas.append("Quem executa o material daqui a dois anos consegue, com o que está escrito?")
    if cobertura < 50:
        achados.append(finding(
            "should", "cobertura-baixa", "Menos de metade dos itens de reprodutibilidade", _pct(cobertura, 0),
            "O relato cobre poucos itens que permitem repetir o trabalho.",
            "Sem eles, a reprodução vira reinterpretação.",
            "Complete os itens ausentes, começando por dado e código.",
            "O trabalho envelhece como afirmação, não como método.",
        ))

    metrics = {"itens": exigidos, "presentes": presentes, "ausentes": exigidos - presentes,
               "cobertura": round(cobertura, 1)}
    achados, counts, veredito, perguntas = finalize(achados, modo, perguntas)
    return {
        **common(
            analysis="ciencia.reprodutibilidade",
            mode=modo,
            title="Reprodutibilidade do material",
            summary=[
                f"{_n(presentes, 'item declarado', 'itens declarados')} de {exigidos} — cobertura de {_pct(cobertura, 0)}.",
                "Completude aqui é declaração, não prova de que o material funciona.",
            ],
            findings=achados,
            counts=counts,
            verdict=veredito,
            questions=perguntas,
            rows=linhas,
            metrics=metrics,
            limitations=LIMITES_REPRO,
        ),
        "executado": False,
    }


# ------------------------------------------------- 5. validação de método

CRITERIOS_M10 = {
    "cromatografico": {"recuperacao": 15.0, "rsd": 15.0, "lloq": 20.0, "rotulo": "ICH M10 — cromatográfico"},
    "lba": {"recuperacao": 20.0, "rsd": 20.0, "lloq": 25.0, "rotulo": "ICH M10 — ligante (LBA)"},
}

LIMITES_VALIDACAO = [
    "A conta usa só a tabela colada; nenhum cromatograma, curva de calibração ou relatório de software é lido.",
    "O critério é o que você declara. O ICH Q2(R2) não fornece limites numéricos: eles vêm da especificação, do compêndio ou do protocolo.",
    "Critério definido depois de ver o dado não é critério de aceitação — esta conferência aplica o limite que você informa, não escolhe um.",
    "Linearidade aqui é regressão linear simples por mínimos quadrados; falta de ajuste, homocedasticidade e faixa validada não são testadas.",
]


def validar_metodo(
    *,
    dados: str,
    curva: str = "",
    tipo: str = "cromatografico",
    limite_recuperacao: float = 0.0,
    limite_rsd: float = 0.0,
    modo: str = "full",
) -> dict[str, Any]:
    _modo(modo)
    if tipo not in CRITERIOS_M10:
        raise CienciaError("`tipo` aceita cromatografico ou lba.")
    criterio = CRITERIOS_M10[tipo]
    limite_rec = limite_recuperacao or criterio["recuperacao"]
    limite_prec = limite_rsd or criterio["rsd"]
    if not 0 < limite_rec <= 50:
        raise CienciaError("O limite de recuperação fica entre 0 e 50%.")
    if not 0 < limite_prec <= 50:
        raise CienciaError("O limite de RSD fica entre 0 e 50%.")

    registros: list[dict[str, float | str]] = []
    for indice, linha in enumerate(_linhas(dados), start=1):
        partes = [parte.strip() for parte in re.split(r"[,;\t]", linha)]
        if len(partes) < 3:
            raise CienciaError(f"Linha {indice}: use `nivel,medido,alvo[,grupo]`.")
        nivel, medido, alvo = _decimal(partes[0]), _decimal(partes[1]), _decimal(partes[2])
        if nivel is None or medido is None or alvo is None or alvo <= 0:
            raise CienciaError(f"Linha {indice}: número ilegível ou alvo menor que zero.")
        grupo = partes[3] if len(partes) > 3 and partes[3] else "1"
        registros.append({"nivel": nivel, "medido": medido, "alvo": alvo, "grupo": grupo})
    if len(registros) < 4:
        raise CienciaError("Informe ao menos quatro medições, em dois níveis.")

    niveis = sorted({registro["nivel"] for registro in registros})
    achados: list[dict[str, Any]] = []
    linhas: list[dict[str, Any]] = []
    perguntas: list[str] = []
    menor_nivel = niveis[0]
    precisao_repetibilidade: list[float] = []
    precisao_intermediaria: list[float] = []

    for nivel in niveis:
        do_nivel = [registro for registro in registros if registro["nivel"] == nivel]
        medidas = [float(registro["medido"]) for registro in do_nivel]
        alvo = float(do_nivel[0]["alvo"])
        media = statistics.fmean(medidas)
        desvio = statistics.stdev(medidas) if len(medidas) > 1 else 0.0
        recuperacao = media / alvo * 100
        rsd = desvio / media * 100 if media else 0.0
        largura_rec = limite_rec + (5.0 if nivel == menor_nivel else 0.0)
        largura_prec = limite_prec + (5.0 if nivel == menor_nivel else 0.0)
        dentro_rec = abs(recuperacao - 100) <= largura_rec
        dentro_prec = rsd <= largura_prec
        linhas.append({
            "nivel": _num(nivel, 2), "n": len(medidas),
            "recuperacao": _pct(recuperacao), "rsd": _pct(rsd),
            "limite": f"±{_num(largura_rec, 0)}% / RSD {_num(largura_prec, 0)}%",
            "situacao": "ok" if dentro_rec and dentro_prec else "fora",
        })
        if not dentro_rec:
            achados.append(finding(
                "must", "recuperacao-fora", "Recuperação fora do critério", f"nível {_num(nivel, 2)}: {_pct(recuperacao)}",
                f"O critério aceita 100 ± {_num(largura_rec, 0)}%; a média do nível deu {_pct(recuperacao)}.",
                "Erro sistemático de exatidão desloca toda medição do nível.",
                "Revise extração, padronização e branco de matriz antes de liberar o método.",
                "O resultado é aceito com viés embutido.",
            ))
        if not dentro_prec:
            achados.append(finding(
                "must", "rsd-alto", "Precisão fora do critério", f"nível {_num(nivel, 2)}: RSD {_pct(rsd)}",
                f"O critério aceita RSD de até {_num(largura_prec, 0)}%.",
                "Dispersão acima do limite indica método fora de controle naquele nível.",
                "Verifique preparo, injeção e estabilidade da amostra.",
                "O método não distingue amostra de ruído.",
            ))
        if len(medidas) < 3:
            achados.append(finding(
                "should", "replicatas-insuficientes", "Menos de três replicatas no nível", f"nível {_num(nivel, 2)}: n = {len(medidas)}",
                "Precisão estimada com duas medidas é quase o intervalo entre elas.",
                "O RSD fica instável e não representa a rotina.",
                "Use ao menos três replicatas por nível.",
                "A precisão declarada depende de duas injeções.",
            ))
        grupos = {registro["grupo"] for registro in do_nivel}
        if len(grupos) > 1:
            somas = []
            graus = 0
            for grupo in grupos:
                valores = [float(r["medido"]) for r in do_nivel if r["grupo"] == grupo]
                if len(valores) > 1:
                    somas.append((len(valores) - 1) * statistics.variance(valores))
                    graus += len(valores) - 1
            if graus:
                repetibilidade = math.sqrt(sum(somas) / graus) / media * 100
                total = statistics.stdev(medidas) / media * 100
                precisao_repetibilidade.append(repetibilidade)
                precisao_intermediaria.append(total)
                if repetibilidade and total / repetibilidade >= 2 and total > limite_prec:
                    achados.append(finding(
                        "should", "precisao-intermediaria", "Repetibilidade não representa a precisão", f"nível {_num(nivel, 2)}",
                        f"Repetibilidade de {_pct(repetibilidade)} subiu para {_pct(total)} entre grupos.",
                        "O componente entre dias ou analistas fica invisível quando só se reporta repetibilidade.",
                        "Reporte precisão intermediária, com o fator que variou nomeado.",
                        "A rotina performa pior do que o método promete.",
                    ))
        if abs(recuperacao - 100) > 5 and dentro_rec:
            achados.append(finding(
                "should", "vies-sistematico", "Viés sistemático dentro do limite", _pct(recuperacao),
                "A recuperação está dentro do critério, mas longe de 100%.",
                "Viés de 5% ou mais soma ao erro de toda medição do nível.",
                "Declare o fator de correção ou ajuste a extração.",
                "O resultado fica deslocado de forma previsível.",
            ))

    if precisao_intermediaria and precisao_repetibilidade:
        pior = max(precisao_intermediaria)
        if pior > limite_prec and max(precisao_repetibilidade) <= limite_prec:
            achados.append(finding(
                "must", "precisao-total-fora", "Precisão intermediária acima do critério", _pct(pior),
                "A repetibilidade passa, mas a precisão intermediária não.",
                "Reportar só a repetibilidade esconde a variabilidade entre dias ou analistas.",
                "Trate a causa entre grupos e reporte a precisão intermediária.",
                "O método é aprovado com desempenho de rotina fora do critério.",
            ))

    curva_metricas: dict[str, float] = {}
    if curva.strip():
        pontos: list[tuple[float, float]] = []
        for indice, linha in enumerate(_linhas(curva), start=1):
            partes = [parte.strip() for parte in re.split(r"[,;\t]", linha)]
            if len(partes) < 2:
                raise CienciaError(f"Curva, linha {indice}: use `concentracao,resposta`.")
            x, y = _decimal(partes[0]), _decimal(partes[1])
            if x is None or y is None:
                raise CienciaError(f"Curva, linha {indice}: número ilegível.")
            pontos.append((x, y))
        if len(pontos) < 3:
            raise CienciaError("A curva precisa de ao menos três pontos.")
        xs = [x for x, _ in pontos]
        ys = [y for _, y in pontos]
        media_x, media_y = statistics.fmean(xs), statistics.fmean(ys)
        sxx = sum((x - media_x) ** 2 for x in xs)
        if sxx == 0:
            raise CienciaError("A curva tem todas as concentrações iguais.")
        sxy = sum((x - media_x) * (y - media_y) for x, y in pontos)
        inclinacao = sxy / sxx
        intercepto = media_y - inclinacao * media_x
        residuos = [y - (intercepto + inclinacao * x) for x, y in pontos]
        syy = sum((y - media_y) ** 2 for y in ys)
        r2 = 1 - sum(r * r for r in residuos) / syy if syy else 0.0
        sd_resid = math.sqrt(sum(r * r for r in residuos) / max(1, len(pontos) - 2))
        curva_metricas = {
            "inclinacao": inclinacao, "intercepto": intercepto, "r2": round(r2, 5),
            "lod": 3.3 * sd_resid / inclinacao if inclinacao > 0 else 0.0,
            "loq": 10 * sd_resid / inclinacao if inclinacao > 0 else 0.0,
        }
        for rotulo, valor in (("Inclinação", _num(inclinacao, 4)),
                              ("Intercepto", _num(intercepto, 4)),
                              ("R²", _num(r2, 5)),
                              ("LOD", _num(curva_metricas["lod"], 3)),
                              ("LOQ", _num(curva_metricas["loq"], 3))):
            linhas.append({"nivel": rotulo, "n": len(pontos), "recuperacao": valor,
                           "rsd": "—", "limite": "—", "situacao": "curva"})
        if inclinacao <= 0:
            achados.append(finding(
                "must", "inclinacao-nao-positiva", "Resposta não cresce com a concentração", _num(inclinacao, 4),
                "A inclinação da curva é zero ou negativa.",
                "Sem relação positiva, não há como quantificar.",
                "Confira rótulos, diluições e faixa da curva.",
                "O método não mede o que diz medir.",
            ))
        elif r2 < 0.99:
            achados.append(finding(
                "must", "r2-baixo", "Linearidade abaixo de 0,99", _num(r2, 4),
                "O coeficiente de determinação ficou abaixo de 0,99.",
                "O modelo linear não descreve a faixa testada.",
                "Restrinja a faixa, refaça os pontos extremos ou use ajuste ponderado.",
                "A concentração estimada carrega erro do modelo.",
            ))
        if curva_metricas["lod"] > menor_nivel:
            achados.append(finding(
                "should", "lod-acima-do-nivel", "LOD estimado acima do menor nível", _num(curva_metricas["lod"], 3),
                "O limite de detecção calculado passa da menor concentração medida.",
                "A faixa validada começa abaixo do que o método consegue detectar.",
                "Estenda a curva para baixo ou declare o LOD real.",
                "O limite inferior do método é ficção.",
            ))
    else:
        achados.append(finding(
            "should", "sem-curva", "Sem curva de calibração", "—",
            "Linearidade, LOD e LOQ saem da curva.",
            "Sem ela, a faixa declarada não tem suporte numérico.",
            "Cole a curva como `concentracao,resposta`.",
            "A validação fica pela metade.",
        ))

    if modo == "ultra":
        perguntas.append("Os critérios de aceitação estavam escritos no protocolo antes da coleta?")
        perguntas.append("Qual foi a matriz, e branco de matriz foi usado na curva?")

    achados, counts, veredito, perguntas = finalize(achados, modo, perguntas)
    metrics = {
        "tipo": tipo, "niveis": len(niveis), "medicoes": len(registros),
        "limite_recuperacao": limite_rec, "limite_rsd": limite_prec,
        "r2": curva_metricas.get("r2", 0.0), "lod": round(curva_metricas.get("lod", 0.0), 4),
        "loq": round(curva_metricas.get("loq", 0.0), 4),
    }
    return {
        **common(
            analysis="ciencia.validacao",
            mode=modo,
            title="Validação de método analítico",
            summary=[
                f"{criterio['rotulo']}, com {_n(len(niveis), 'nível', 'níveis')} e {_n(len(registros), 'medição', 'medições')}.",
                f"Critério aplicado: recuperação 100 ± {_num(limite_rec, 0)}% e RSD até {_num(limite_prec, 0)}% "
                f"(mais largo no menor nível).",
                (f"Curva com R² {_num(curva_metricas['r2'], 4)}, LOD {_num(curva_metricas['lod'], 3)} e "
                 f"LOQ {_num(curva_metricas['loq'], 3)}.") if curva_metricas else "Sem curva informada.",
            ],
            findings=achados,
            counts=counts,
            verdict=veredito,
            questions=perguntas,
            rows=linhas,
            metrics=metrics,
            limitations=LIMITES_VALIDACAO,
        ),
        "executado": False,
    }


# ------------------------------------------------------- 6. manuscrito

SECOES = [
    ("resumo", "Resumo", [r"\bresumo\b", r"\babstract\b"]),
    ("introducao", "Introdução", [r"introdu[cç][aã]o", r"\bbackground\b"]),
    ("metodos", "Métodos", [r"m[eé]todos?\b", r"materials?\s+and\s+methods"]),
    ("resultados", "Resultados", [r"resultados?\b", r"\bresults\b"]),
    ("discussao", "Discussão", [r"discuss[aã]o", r"\bdiscussion\b"]),
    ("limitacoes", "Limitações", [r"limita[cç][oõ]es", r"\blimitations\b"]),
    ("conclusao", "Conclusão", [r"conclus[aã]o", r"\bconclusions?\b"]),
    ("financiamento", "Financiamento", [r"financiamento", r"funding", r"ag[eê]ncia\s+de\s+fomento",
                                        r"bolsa\s+de"]),
    ("conflito", "Conflito de interesse", [r"conflito\s+de\s+interesse", r"conflicts?\s+of\s+interest",
                                          r"declara[cç][aã]o\s+de\s+interesse"]),
    ("dados", "Disponibilidade de dados", [r"disponibilidade\s+de\s+dados", r"data\s+availability",
                                           r"dados\s+suplementares"]),
    ("autoria", "Contribuição de autoria", [r"contribui[cç][oõ]es", r"author\s+contributions",
                                            r"concep[cç][aã]o\s+e\s+desenho"]),
    ("etica", "Aprovação ética", [r"comit[eê]\s+de\s+[eé]tica", r"\bCEP\b", r"\bIRB\b",
                                  r"aprova[cç][aã]o\s+do\s+comit[eê]", r"consentimento\s+livre"]),
    ("referencias", "Referências", [r"refer[eê]ncias", r"\breferences\b", r"refer[eê]ncias\s+bibliogr[aá]ficas"]),
]

DIRETRIZES: dict[str, dict[str, Any]] = {
    "ensaio": {
        "nome": "CONSORT 2025",
        "itens": [
            ("randomizacao", "Sequência de randomização", [r"randomiz", r"sequ[eê]ncia\s+de\s+aloca"]),
            ("alocacao", "Sigilo da alocação", [r"aloca[cç][aã]o\s+(oculta|sigilosa)", r"envelope", r"central"]),
            ("cegamento", "Cegamento", [r"cegament", r"cego", r"mascarad"]),
            ("fluxo", "Fluxo de participantes", [r"fluxo\s+de\s+participantes", r"triados", r"eleg[ií]veis",
                                                r"alocados"]),
            ("desfechos", "Desfechos primários e secundários", [r"desfecho\s+prim[aá]rio", r"desfechos?\s+secund"]),
            ("amostra", "Tamanho amostral", [r"tamanho\s+amostral", r"c[aá]lculo\s+amostral", r"\bpoder\b"]),
        ],
    },
    "observacional": {
        "nome": "STROBE",
        "itens": [
            ("participantes", "Participantes e elegibilidade", [r"crit[eé]rios\s+de\s+(inclus|exclus)",
                                                                r"elegibilidade", r"participantes"]),
            ("variaveis", "Variáveis e fontes", [r"vari[aá]veis", r"fontes?\s+de\s+dados", r"coletad"]),
            ("vies", "Viés", [r"vi[eé]s", r"confundidor", r"sele[cç][aã]o"]),
            ("amostra", "Tamanho amostral", [r"tamanho\s+amostral", r"c[aá]lculo\s+amostral"]),
            ("estatistica", "Métodos estatísticos", [r"m[eé]todos\s+estat[ií]sticos", r"regress[aã]o", r"modelo"]),
            ("limitacoes", "Limitações", [r"limita[cç][oõ]es"]),
        ],
    },
    "diagnostico": {
        "nome": "STARD",
        "itens": [
            ("referencia", "Padrão de referência", [r"padr[aã]o\s+de\s+refer[eê]ncia", r"teste\s+de\s+refer[eê]ncia"]),
            ("cegamento", "Cegamento entre testes", [r"cego", r"mascarad", r"independente"]),
            ("fluxo", "Fluxo de participantes", [r"fluxo", r"eleg[ií]veis", r"inclu[ií]dos"]),
            ("acuracia", "Acurácia com denominadores", [r"sensibilidade", r"especificidade", r"acur[aá]cia",
                                                        r"VPP", r"VPN"]),
            ("indeterminados", "Resultados indeterminados", [r"indeterminad", r"inconclusiv", r"n[aã]o\s+avali[aá]vel"]),
        ],
    },
    "revisao": {
        "nome": "PRISMA 2020",
        "itens": [
            ("busca", "Estratégia de busca", [r"estrat[eé]gia\s+de\s+busca", r"bases?\s+de\s+dados", r"pubmed",
                                              r"scopus", r"embase"]),
            ("criterios", "Critérios de elegibilidade", [r"crit[eé]rios\s+de\s+elegibilidade", r"inclus[aã]o",
                                                         r"exclus[aã]o"]),
            ("selecao", "Processo de seleção", [r"sele[cç][aã]o", r"triagem", r"dupla\s+avalia"]),
            ("vies", "Risco de viés", [r"risco\s+de\s+vi[eé]s", r"robin", r"rob\s?2", r"qualidade\s+dos\s+estudos"]),
            ("sintese", "Síntese", [r"meta-?an[aá]lise", r"s[ií]ntese", r"heterogeneidade", r"\bI²\b"]),
        ],
    },
    "animal": {
        "nome": "ARRIVE 2.0",
        "itens": [
            ("especie", "Espécie, cepa e sexo", [r"esp[eé]cie", r"cepa", r"linhagem", r"machos?\s+e\s+f[eê]meas"]),
            ("randomizacao", "Randomização", [r"randomiz", r"aleatori[sz]", r"sorteio"]),
            ("cegamento", "Cegamento", [r"cego", r"mascarad"]),
            ("amostra", "Tamanho amostral", [r"tamanho\s+amostral", r"c[aá]lculo\s+amostral", r"poder"]),
            ("humanitario", "Ponto final humanitário", [r"ponto\s+final\s+humanit[aá]rio", r"humane\s+endpoint",
                                                         r"eutan[aá]sia", r"crit[eé]rio\s+de\s+parada"]),
            ("alojamento", "Alojamento e manejo", [r"alojamento", r"ciclo\s+claro", r"temperatura", r"ra[cç][aã]o"]),
        ],
    },
}

CLAIMS = [
    ("inedito", "should", "Novidade como argumento", r"in[eé]dit|pioneir|primeir[oa]\s+estudo|first\s+study|\bnovel\b",
     "Novidade não é resultado; o valor está no que foi medido.",
     "Descreva o que o estudo acrescenta, não que ninguém fez antes."),
    ("cura", "must", "Promessa de cura", r"\bcura\s+(definitiva|completa)|\bcurou\b",
     "Cura é desfecho clínico que exige ensaio próprio e população definida.",
     "Troque por “reduziu” ou “melhorou” com o desfecho e o n."),
    ("sem-risco", "must", "Ausência de risco afirmada", r"sem\s+(nenhum\s+)?(efeito|risco|rea[cç][aã]o)|100%\s+seguro|isento\s+de\s+risco",
     "Nenhuma intervenção tem risco zero demonstrado por um estudo.",
     "Reporte os eventos adversos observados e a janela de seguimento."),
    ("prova", "must", "Prova afirmada", r"prova\s+que|comprova\s+que|est[aá]\s+provado\s+que",
     "Estudo sustenta hipótese com incerteza; não prova.",
     "Troque por “é compatível com” e informe o intervalo."),
]

LIMITES_MANUSCRITO = [
    "A conferência é sobre o que o texto declara: seção ausente pode existir em outro arquivo, e a leitura não vê suplemento.",
    "Completude de relato não é qualidade do desenho, risco de viés nem mérito científico — e esta análise não converte item ausente em nota.",
    "A escolha da diretriz é pelo tipo declarado; estudo híbrido ou extensão específica (CONSORT-AI, STROBE-ME) pode exigir outra lista.",
    "Nenhuma referência é acessada, contada ou verificada contra base bibliográfica.",
]


def auditar_manuscrito(*, texto: str, tipo: str = "ensaio", modo: str = "full") -> dict[str, Any]:
    _modo(modo)
    if tipo not in DIRETRIZES:
        raise CienciaError("`tipo` aceita ensaio, observacional, diagnostico, revisao ou animal.")
    if len(texto.strip()) < 200:
        raise CienciaError("Cole o manuscrito ou o resumo com as seções; ao menos 200 caracteres.")
    if len(texto) > MAX_TEXTO:
        raise CienciaError("Texto acima do limite de leitura.")

    achados: list[dict[str, Any]] = []
    linhas: list[dict[str, Any]] = []
    perguntas: list[str] = []

    presentes_secoes = 0
    for identificador, rotulo, padroes in SECOES:
        casamento = next((re.search(p, texto, re.I) for p in padroes if re.search(p, texto, re.I)), None)
        if casamento:
            presentes_secoes += 1
        linhas.append({"item": rotulo, "tipo": "seção", "status": "presente" if casamento else "ausente",
                       "evidencia": _trecho(texto, casamento.start(), casamento.end()) if casamento else "—"})
        if not casamento and identificador in {"resumo", "metodos", "resultados", "discussao"}:
            achados.append(finding(
                "must", f"sem-secao-{identificador}", f"Seção de {rotulo.lower()} ausente", rotulo,
                "A estrutura IMRaD é o que permite ao leitor achar método e resultado.",
                f"Sem {rotulo.lower()}, o manuscrito não pode ser avaliado no item.",
                f"Inclua a seção de {rotulo.lower()}.",
                "A revista devolve antes da revisão.",
            ))
        if not casamento and identificador in {"financiamento", "conflito", "etica", "dados"}:
            achados.append(finding(
                "should", f"sem-{identificador}", f"{rotulo} não declarado", rotulo,
                "Declaração exigida por revista e por agência.",
                "A omissão é lida como pendência de integridade.",
                f"Acrescente a declaração de {rotulo.lower()}.",
                "A submissão fica incompleta.",
            ))

    diretriz = DIRETRIZES[tipo]
    presentes_itens = 0
    for identificador, rotulo, padroes in diretriz["itens"]:
        casamento = next((re.search(p, texto, re.I) for p in padroes if re.search(p, texto, re.I)), None)
        if casamento:
            presentes_itens += 1
        linhas.append({"item": rotulo, "tipo": diretriz["nome"],
                       "status": "presente" if casamento else "ausente",
                       "evidencia": _trecho(texto, casamento.start(), casamento.end()) if casamento else "—"})
        if not casamento:
            achados.append(finding(
                "should", f"sem-item-{identificador}", f"{diretriz['nome']}: {rotulo.lower()} ausente", rotulo,
                f"{diretriz['nome']} pede esse item no relato.",
                "Sem ele, o leitor não consegue avaliar o que a diretriz considera essencial.",
                f"Descreva {rotulo.lower()} no corpo do texto.",
                "O revisor aponta a diretriz na primeira leitura.",
            ))

    for identificador, grupo, rotulo, padrao, porque, correcao in CLAIMS:
        casamento = re.search(padrao, texto, re.I)
        if not casamento:
            continue
        achados.append(finding(
            grupo, f"claim-{identificador}", rotulo, _trecho(texto, casamento.start(), casamento.end()),
            porque,
            "A afirmação excede o que o desenho e os números sustentam.",
            correcao,
            "A conclusão é lida como exagero e contamina o resto do texto.",
        ))

    palavras = len(_palavras(texto))
    cobertura_secoes = presentes_secoes / len(SECOES) * 100
    cobertura_diretriz = presentes_itens / len(diretriz["itens"]) * 100
    if cobertura_diretriz < 50:
        achados.append(finding(
            "should", "diretriz-incompleta", f"Menos de metade dos itens de {diretriz['nome']}",
            _pct(cobertura_diretriz, 0),
            "O manuscrito cobre poucos itens da diretriz do tipo de estudo.",
            "Itens ausentes são o motivo mais comum de devolução sem revisão.",
            "Percorra a lista da diretriz item a item antes de submeter.",
            "A submissão volta com pedido de complemento.",
        ))
    if palavras < 800:
        achados.append(finding(
            "nice", "texto-curto", "Texto com menos de 800 palavras", _n(palavras, "palavra", "palavras"),
            "Manuscrito completo raramente cabe em tão pouco.",
            "Pode ser só o resumo: a conferência então vale para o que está escrito.",
            "Cole o corpo inteiro se quiser conferir o manuscrito.",
            "A cobertura de seções fica subestimada.",
        ))
    if modo == "ultra":
        perguntas.append("Qual lista de checagem a revista de destino exige, e qual versão?")
        perguntas.append("O protocolo registrado tem os mesmos desfechos do manuscrito?")

    extrass = ["", f"## {diretriz['nome']}", "", "| Item | Situação | Evidência |", "|---|---|---|"]
    for linha in linhas:
        if linha["tipo"] == diretriz["nome"]:
            extrass.append(f"| {linha['item']} | {linha['status']} | {linha['evidencia']} |")

    metrics = {
        "tipo": tipo, "diretriz": diretriz["nome"], "palavras": palavras,
        "secoes_presentes": presentes_secoes, "secoes_total": len(SECOES),
        "itens_presentes": presentes_itens, "itens_total": len(diretriz["itens"]),
        "cobertura_secoes": round(cobertura_secoes, 1), "cobertura_diretriz": round(cobertura_diretriz, 1),
        "claims": sum(1 for item in CLAIMS if re.search(item[3], texto, re.I)),
    }
    achados, counts, veredito, perguntas = finalize(achados, modo, perguntas)
    return {
        **common(
            analysis="ciencia.manuscrito",
            mode=modo,
            title="Completude do manuscrito",
            summary=[
                f"{_n(presentes_secoes, 'seção presente', 'seções presentes')} de {len(SECOES)} — {_pct(cobertura_secoes, 0)}.",
                f"{diretriz['nome']} (por tipo {tipo}): {presentes_itens} de {len(diretriz['itens'])} itens — "
                f"{_pct(cobertura_diretriz, 0)}.",
                "Completude de relato não é qualidade do desenho: a lista diz o que deveria estar escrito, não se está certo.",
            ],
            findings=achados,
            counts=counts,
            verdict=veredito,
            questions=perguntas,
            rows=linhas,
            metrics=metrics,
            limitations=LIMITES_MANUSCRITO,
            extra_sections=extrass,
        ),
        "executado": False,
    }


# ---------------------------------------------------------- 7. catálogo

def ciencia_catalogo() -> dict[str, Any]:
    return {
        "fonte": "K-Dense-AI/scientific-agent-skills (MIT)",
        "versao": VERSAO,
        "principio": "Rigor é o que o texto consegue mostrar; o resto é promessa.",
        "benchmarks": {chave: list(valores) for chave, valores in BENCHMARKS.items()},
        "criterios": {
            "cromatografico": CRITERIOS_M10["cromatografico"],
            "lba": CRITERIOS_M10["lba"],
            "r2_minimo": 0.99,
            "alfa": 0.05,
            "poder": 0.80,
            "poder_confirmatorio": 0.90,
        },
        "formulas": [
            {"id": "proporcoes", "formula": "n1 = (zα√((1+r)p̄q̄) + zβ√(p1q1 + r·p2q2))² ÷ (r·(p2−p1)²)"},
            {"id": "medias", "formula": "n1 = (zα + zβ)² · (1 + 1/r) ÷ d²"},
            {"id": "efeito-desenho", "formula": "DEFF = 1 + (m − 1)·ICC"},
            {"id": "perda", "formula": "n_matrícula = n_analisado ÷ (1 − perda)"},
            {"id": "multiplicidade", "formula": "alfa_ajustado = alfa ÷ comparações"},
            {"id": "poder-proporcoes", "formula": "Φ((|p2−p1| − zα·√(p̄q̄(1/n1+1/n2))) ÷ √(p1q1/n1 + p2q2/n2))"},
            {"id": "recuperacao", "formula": "média(medido) ÷ alvo × 100"},
            {"id": "rsd", "formula": "desvio-padrão ÷ média × 100"},
            {"id": "r2", "formula": "1 − SQ_resíduo ÷ SQ_total"},
            {"id": "lod", "formula": "3,3 × desvio dos resíduos ÷ inclinação"},
            {"id": "loq", "formula": "10 × desvio dos resíduos ÷ inclinação"},
        ],
        "diretrizes": {
            tipo: {"nome": valor["nome"], "itens": [item[1] for item in valor["itens"]]}
            for tipo, valor in DIRETRIZES.items()
        },
        "desenho": {
            tipo: [
                {"id": item["id"], "rotulo": item["rotulo"], "peso": item["grupo"][tipo]}
                for item in ITENS_DESENHO if item["grupo"].get(tipo, "nao") != "nao"
            ]
            for tipo in TIPOS_DESENHO
        },
        "reprodutibilidade": [
            {"id": item["id"], "rotulo": item["rotulo"], "peso": item["grupo"]}
            for item in ITENS_REPRO
        ],
        "claims": [
            {"id": identificador, "grupo": grupo, "rotulo": rotulo, "padrao": padrao}
            for identificador, grupo, rotulo, padrao, _porque, _correcao in CLAIMS
        ],
        "deixado_de_fora": [
            "Nenhum dos 177 pacotes de skill do upstream foi importado: o JARVIS mede relato e material, não executa análise.",
            "Nenhum script do repositório (power.py, simulate_power.py, randomization.py, check_accuracy_precision.py) é instalado ou chamado.",
            "Nenhum modelo de linguagem participa: a conferência é lexical e a conta é a da fórmula publicada.",
            "Risco de viés (RoB 2, ROBINS-I, QUADAS-2), meta-análise e modelagem não são implementados aqui.",
        ],
        "executado": False,
    }
