"""O calendário do PC: que dia é hoje, quanto falta para o sábado e os feriados.

A pergunta que gerou isto (18/11):

    e se eu perguntar para o javis q dia e hj proximos feriados quantos dias
    faltam para final de semana hj e quarta quinta...?

“Que dia é hoje” já funcionava, mas só ele. As outras três iam para o **modelo** —
e o modelo não sabe que dia é hoje: não tem relógio. Ele pode acertar o dia da
semana por conta (a data atual costuma chegar no prompt de sistema dele, ou não),
mas os **feriados móveis** (Carnaval, Sexta-feira Santa, Corpus Christi) ele não
calcula: chuta uma data plausível com a mesma confiança com que acerta o Natal.

Aqui tudo é conta de calendário, feita na máquina:

- **dia da semana** e **quantos dias faltam para o sábado** — aritmética de data;
- **feriados nacionais** — os fixos por lei e os móveis pela **Páscoa**, que é
  calculada pelo algoritmo de Meeus/Jones/Butcher (o mesmo da Igreja e do
  Excel), não por tabela que envelhece;
- **ponto facultativo** é dito como tal: Carnaval e Corpus Christi não são
  feriado nacional por lei, e fingir que são seria inventar.

## O que este módulo garante

1. **Nada vem da rede.** É conta local; funciona sem internet, sem chave, sem
   modelo, e é sempre a mesma resposta para a mesma data.
2. **Nada é inventado.** Feriado fora da lista não existe aqui; feriado que a
   pessoa nomeia e não está nos próximos dois anos recebe a lista do que existe,
   não uma data “aproximada”.
3. **A resposta diz de onde veio**: “calculado aqui no PC, sem internet e sem
   modelo”.

Duas datas que envelhecem e estão registradas de propósito: **20/11 — Dia da
Consciência Negra** virou feriado nacional pela Lei 14.759/2023 (vale desde
2024), e **Sexta-feira Santa** é feriado nacional (Lei 9.093/1995). Se a lei
mudar de novo, é esta lista que muda — e o `docs/BIBLIOTECA.md` diz onde.
"""
from __future__ import annotations

import unicodedata
from datetime import date, timedelta
from typing import Any, Iterable

DIAS = (
    "segunda-feira",
    "terça-feira",
    "quarta-feira",
    "quinta-feira",
    "sexta-feira",
    "sábado",
    "domingo",
)

# Feriados nacionais de data fixa (Lei 662/1949, Lei 10.607/2002 e Lei
# 14.759/2023). Cada linha é (dia, mês, nome) — a ordem é a do ano, não a de
# importância.
FIXOS: tuple[tuple[int, int, str], ...] = (
    (1, 1, "Confraternização Universal"),
    (21, 4, "Tiradentes"),
    (1, 5, "Dia do Trabalho"),
    (7, 9, "Independência do Brasil"),
    (12, 10, "Nossa Senhora Aparecida"),
    (2, 11, "Finados"),
    (15, 11, "Proclamação da República"),
    (20, 11, "Dia da Consciência Negra"),
    (25, 12, "Natal"),
)

# Feriados que andam com a Páscoa: quantos dias a partir do domingo dela.
MOVEIS: tuple[tuple[int, str, str], ...] = (
    (0, "Páscoa", "não é feriado nacional"),
    (-48, "Carnaval", "ponto facultativo"),
    (-47, "Carnaval", "ponto facultativo"),
    (-2, "Sexta-feira Santa", "nacional"),
    (60, "Corpus Christi", "ponto facultativo"),
)

TIPO_NACIONAL = "nacional"
TIPO_FACULTATIVO = "ponto facultativo"
# Domingo de Páscoa não é feriado por lei: é a âncora dos outros. Aparece só
# quando a pessoa pergunta por ele — não na lista padrão, onde seria ruído.
TIPO_COMEMORATIVO = "não é feriado nacional"
FONTE = "calendário do PC"


def normalizar(texto: str) -> str:
    """Sem acento, minúsculo: “Consciência” e “consciencia” são a mesma coisa."""
    decomposto = unicodedata.normalize("NFD", texto or "")
    return "".join(c for c in decomposto if unicodedata.category(c) != "Mn").lower().strip()


def pascoa(ano: int) -> date:
    """Domingo de Páscoa do ano (Meeus/Jones/Butcher, calendário gregoriano).

    É a âncora de Carnaval, Sexta-feira Santa e Corpus Christi. Sem ela, os
    feriados móveis teriam de vir de uma tabela — e tabela de feriado envelhece.
    """
    a = ano % 19
    b = ano // 100
    c = ano % 100
    d = b // 4
    e = b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i = c // 4
    k = c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    mes = (h + l - 7 * m + 114) // 31
    dia = ((h + l - 7 * m + 114) % 31) + 1
    return date(ano, mes, dia)


def feriados_do_ano(ano: int) -> list[dict[str, Any]]:
    """Todos os feriados do ano, em ordem de data, com o tipo declarado."""
    itens: list[dict[str, Any]] = [
        {"data": date(ano, mes, dia), "nome": nome, "tipo": TIPO_NACIONAL}
        for dia, mes, nome in FIXOS
    ]
    domingo = pascoa(ano)
    vistos: set[tuple[date, str]] = set()
    for deslocamento, nome, tipo in MOVEIS:
        quando = domingo + timedelta(days=deslocamento)
        chave = (quando, nome)
        if chave in vistos:
            continue
        vistos.add(chave)
        itens.append({"data": quando, "nome": nome, "tipo": tipo})
    itens.sort(key=lambda item: item["data"])
    return itens


def dia_da_semana(quando: date) -> str:
    return DIAS[quando.weekday()]


def dias_ate_sabado(quando: date) -> int:
    """Dias até o próximo sábado (0 = hoje é sábado). Domingo conta 6."""
    return (5 - quando.weekday()) % 7


def _curto(quando: date) -> str:
    return quando.strftime("%d/%m/%Y")


def _em_dias(quando: date, hoje: date) -> str:
    dias = (quando - hoje).days
    if dias == 0:
        return "é hoje"
    if dias == 1:
        return "é amanhã"
    if dias < 0:
        return f"foi há {-dias} dias"
    return f"em {dias} dias"


def resumo_do_dia(quando: date | None = None) -> dict[str, Any]:
    """O dia de hoje em palavras: data, dia da semana e o que falta para o sábado."""
    hoje = quando or date.today()
    faltam = dias_ate_sabado(hoje)
    sabado = hoje + timedelta(days=faltam)
    if faltam == 0:
        fim_de_semana = f"Hoje é sábado: o fim de semana é hoje ({_curto(hoje)})."
    elif hoje.weekday() == 6:
        fim_de_semana = (
            f"É domingo — o fim de semana está acabando. O próximo sábado é "
            f"{_curto(sabado)}, em {faltam} dias."
        )
    elif faltam == 1:
        fim_de_semana = f"Falta 1 dia para o sábado ({_curto(sabado)})."
    else:
        fim_de_semana = f"Faltam {faltam} dias para o sábado ({_curto(sabado)})."
    return {
        "data": hoje.isoformat(),
        "data_br": _curto(hoje),
        "dia_semana": dia_da_semana(hoje),
        "sabado": sabado.isoformat(),
        "dias_ate_sabado": faltam,
        "fim_de_semana": fim_de_semana,
        "fonte": FONTE,
    }


def formatar_dia(dados: dict[str, Any]) -> str:
    return (
        f"Hoje é {dados['dia_semana']}, {dados['data_br']}. {dados['fim_de_semana']}\n\n"
        f"(Conta de calendário feita aqui no PC — sem internet e sem modelo.)"
    )


def proximos(
    hoje: date | None = None,
    *,
    limite: int = 4,
    nome: str = "",
    ano: int | None = None,
) -> list[dict[str, Any]]:
    """Os próximos feriados a partir de hoje (ou todos de um ano, ou um pelo nome)."""
    referencia = hoje or date.today()
    procurado = normalizar(nome)

    if ano is not None:
        lista = feriados_do_ano(int(ano))
        if procurado:
            lista = [item for item in lista if procurado in normalizar(item["nome"])]
        return lista[: max(0, int(limite)) or len(lista)]

    # Dois anos bastam: de dezembro em diante o próximo feriado já é do ano
    # seguinte, e um feriado de novembro pode ter acabado de passar.
    candidatos: list[dict[str, Any]] = []
    for deslocamento in (0, 1):
        candidatos.extend(feriados_do_ano(referencia.year + deslocamento))
    futuros = [item for item in candidatos if item["data"] >= referencia]
    if not procurado:
        # A Páscoa só entra quando é pedida pelo nome.
        futuros = [item for item in futuros if item["tipo"] != TIPO_COMEMORATIVO]
    futuros.sort(key=lambda item: item["data"])
    if procurado:
        # Pelo nome, o ano que vem também vale — “quanto falta para o Natal” em
        # 26/12 é o Natal do ano seguinte, não “foi ontem”.
        futuros = [item for item in futuros if procurado in normalizar(item["nome"])]
    return futuros[: max(1, int(limite))]


def formatar_feriados(
    lista: Iterable[dict[str, Any]],
    hoje: date | None = None,
    *,
    nome: str = "",
) -> str:
    """O texto da conversa: o dia de hoje em cima, os feriados embaixo."""
    referencia = hoje or date.today()
    itens = list(lista)
    dia = resumo_do_dia(referencia)

    if not itens:
        if nome:
            return (
                f"Não achei feriado com “{nome}” nos próximos dois anos.\n\n"
                + formatar_feriados(proximos(referencia, limite=4), referencia)
            )
        return f"{dia['data_br']} — {dia['dia_semana']}, e nenhum feriado nacional pela frente."

    # A Páscoa não é feriado: quando é ela que a pessoa pediu, o título não
    # pode chamá-la de feriado.
    so_ancora = all(item.get("tipo") == TIPO_COMEMORATIVO for item in itens)
    if so_ancora:
        titulo = "A data que você pediu"
    else:
        titulo = "Próximo feriado" if len(itens) == 1 else "Próximos feriados"
    legenda = "" if so_ancora else " — nacionais, e os facultativos marcados como tal"
    linhas = [
        f"Hoje é {dia['dia_semana']}, {dia['data_br']}. {dia['fim_de_semana']}",
        "",
        f"{titulo}{legenda}:",
    ]
    for indice, item in enumerate(itens, start=1):
        quando: date = item["data"]
        marca = "" if item.get("tipo") == TIPO_NACIONAL else f" — {item.get('tipo')}"
        linhas.append(
            f"{indice}. {_curto(quando)} ({dia_da_semana(quando)}) — {item['nome']}"
            f"{marca} — {_em_dias(quando, referencia)}"
        )
    linhas.append("")
    linhas.append(
        f"(Fonte: {FONTE} — datas fixas por lei e as móveis calculadas pela Páscoa. "
        "Sem internet e sem modelo: nada aqui foi estimado.)"
    )
    return "\n".join(linhas)


def ano_do_pedido(ano: Any) -> int | None:
    """Ano citado na frase, se for plausível (1900–2100). Nada de inventar."""
    try:
        numero = int(ano)
    except (TypeError, ValueError):
        return None
    return numero if 1900 <= numero <= 2100 else None
