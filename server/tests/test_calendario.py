"""Que dia é hoje, quanto falta para o sábado e os feriados — sem modelo (0.91.37).

A pergunta do dono, em 18/11:

    e se eu perguntar para o javis q dia e hj proximos feriados quantos dias
    faltam para final de semana hj e quarta quinta...?

Só o “que dia é hoje” funcionava. O resto caía em `unknown` e ia para o modelo —
que não tem relógio. Feriado fixo ele até chuta certo; **feriado móvel**
(Carnaval, Sexta-feira Santa, Corpus Christi) não: sai uma data plausível com a
mesma confiança do Natal.

Aqui nada vem da rede e nada é estimado: a Páscoa é calculada (Meeus/Jones/
Butcher), os feriados saem dela e da lei, e a resposta diz de onde veio.
"""
from __future__ import annotations

from datetime import date

import pytest
from fastapi.testclient import TestClient

from server import calendario
from server.app import create_app
from server.skill_registry import build_registry

# Quarta-feira, 18/11/2026 — o dia do print do dono.
HOJE = date(2026, 11, 18)


# ---------------------------------------------------------------------------
# A Páscoa, que é a âncora dos feriados móveis
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "ano, esperado",
    [
        (2020, date(2020, 4, 12)),
        (2021, date(2021, 4, 4)),
        (2022, date(2022, 4, 17)),
        (2023, date(2023, 4, 9)),
        (2024, date(2024, 3, 31)),
        (2025, date(2025, 4, 20)),
        (2026, date(2026, 4, 5)),
        (2027, date(2027, 3, 28)),
        (2028, date(2028, 4, 16)),
        (2038, date(2038, 4, 25)),
    ],
)
def test_pascoa_de_cada_ano(ano, esperado):
    """Dez anos conferidos: o algoritmo é o mesmo da Igreja, não uma tabela."""
    assert calendario.pascoa(ano) == esperado


def test_feriados_moveis_saem_da_pascoa():
    """Sem isto, Carnaval e Corpus Christi teriam de vir de tabela que envelhece."""
    itens = {item["nome"]: item["data"] for item in calendario.feriados_do_ano(2026)}
    pascoa = calendario.pascoa(2026)

    assert pascoa == date(2026, 4, 5)
    assert itens["Sexta-feira Santa"] == date(2026, 4, 3)
    assert itens["Carnaval"] == date(2026, 2, 17)  # terça, -47 dias
    assert itens["Corpus Christi"] == date(2026, 6, 4)  # +60 dias


# ---------------------------------------------------------------------------
# A lista de feriados
# ---------------------------------------------------------------------------

def test_feriados_fixos_do_ano_estao_todos():
    nomes = {item["nome"] for item in calendario.feriados_do_ano(2026)}
    for esperado in (
        "Confraternização Universal",
        "Tiradentes",
        "Dia do Trabalho",
        "Independência do Brasil",
        "Nossa Senhora Aparecida",
        "Finados",
        "Proclamação da República",
        "Natal",
    ):
        assert esperado in nomes


def test_consciencia_negra_e_feriado_nacional_desde_2024():
    """Lei 14.759/2023: 20/11 virou feriado nacional. Antes era só em alguns estados."""
    item = next(i for i in calendario.feriados_do_ano(2026) if i["nome"] == "Dia da Consciência Negra")
    assert item["data"] == date(2026, 11, 20)
    assert item["tipo"] == calendario.TIPO_NACIONAL


def test_ponto_facultativo_e_dito_como_tal():
    """Carnaval e Corpus Christi não são feriado nacional por lei — fingir que são seria inventar."""
    tipos = {item["nome"]: item["tipo"] for item in calendario.feriados_do_ano(2026)}
    assert tipos["Carnaval"] == calendario.TIPO_FACULTATIVO
    assert tipos["Corpus Christi"] == calendario.TIPO_FACULTATIVO
    assert tipos["Sexta-feira Santa"] == calendario.TIPO_NACIONAL


def test_a_lista_do_ano_vem_em_ordem_de_data():
    datas = [item["data"] for item in calendario.feriados_do_ano(2027)]
    assert datas == sorted(datas)


def test_pascoa_nao_entra_na_lista_padrao_mas_aparece_pelo_nome():
    padrao = calendario.proximos(HOJE, limite=10)
    assert all(item["nome"] != "Páscoa" for item in padrao)
    pelo_nome = calendario.proximos(HOJE, nome="páscoa", limite=1)
    assert pelo_nome and pelo_nome[0]["nome"] == "Páscoa"
    assert pelo_nome[0]["data"] == calendario.pascoa(2027)


# ---------------------------------------------------------------------------
# O dia de hoje e o fim de semana
# ---------------------------------------------------------------------------

def test_hoje_diz_a_data_e_o_dia_da_semana():
    dados = calendario.resumo_do_dia(HOJE)
    assert dados["data_br"] == "18/11/2026"
    assert dados["dia_semana"] == "quarta-feira"
    assert dados["dias_ate_sabado"] == 3
    assert dados["sabado"] == "2026-11-21"


def test_quanto_falta_para_o_fim_de_semana():
    texto = calendario.resumo_do_dia(HOJE)["fim_de_semana"]
    assert texto == "Faltam 3 dias para o sábado (21/11/2026)."


def test_no_sabado_o_fim_de_semana_e_hoje():
    texto = calendario.resumo_do_dia(date(2026, 11, 21))["fim_de_semana"]
    assert "Hoje é sábado" in texto


def test_no_domingo_ele_diz_que_o_proximo_e_em_seis_dias():
    dados = calendario.resumo_do_dia(date(2026, 11, 22))
    assert dados["dia_semana"] == "domingo"
    assert dados["dias_ate_sabado"] == 6
    assert "próximo sábado é 28/11/2026" in dados["fim_de_semana"]


def test_na_sexta_falta_um_dia():
    texto = calendario.resumo_do_dia(date(2026, 11, 20))["fim_de_semana"]
    assert texto.startswith("Falta 1 dia para o sábado")


# ---------------------------------------------------------------------------
# Os próximos feriados
# ---------------------------------------------------------------------------

def test_os_proximos_feriados_a_partir_de_18_de_novembro():
    lista = calendario.proximos(HOJE, limite=4)
    assert [item["nome"] for item in lista] == [
        "Dia da Consciência Negra",
        "Natal",
        "Confraternização Universal",
        "Carnaval",
    ]
    assert lista[0]["data"] == date(2026, 11, 20)
    # O Carnaval são dois dias (segunda e terça, ponto facultativo): o de 2027
    # começa em 8 de fevereiro.
    assert lista[3]["data"] == date(2027, 2, 8)
    assert calendario.proximos(HOJE, limite=5)[4]["data"] == date(2027, 2, 9)


def test_o_feriado_de_hoje_conta_como_proximo():
    """Em 20/11 ele não pode pular o feriado do próprio dia."""
    lista = calendario.proximos(date(2026, 11, 20), limite=1)
    assert lista[0]["nome"] == "Dia da Consciência Negra"
    assert calendario.formatar_feriados(lista, date(2026, 11, 20)).count("é hoje") == 1


def test_dezembro_ja_mostra_o_ano_seguinte():
    """Fim de ano: o próximo feriado é 01/01 do ano que vem, não “nenhum”."""
    lista = calendario.proximos(date(2026, 12, 26), limite=1)
    assert lista[0]["data"] == date(2027, 1, 1)


def test_perguntar_pelo_natal_traz_o_natal_do_ano_que_vem():
    """Em 26/12, “quanto falta para o Natal” é o de 2027 — não o de ontem."""
    lista = calendario.proximos(date(2026, 12, 26), nome="natal", limite=1)
    assert lista[0]["data"] == date(2027, 12, 25)


def test_nome_sem_acento_encontra_o_feriado():
    assert calendario.proximos(HOJE, nome="consciencia negra", limite=1)[0]["nome"] == "Dia da Consciência Negra"
    assert calendario.proximos(HOJE, nome="pascoa", limite=1)[0]["nome"] == "Páscoa"


def test_feriado_de_um_ano_especifico():
    lista = calendario.proximos(HOJE, ano=2027, limite=20)
    assert lista[0]["data"] == date(2027, 1, 1)
    assert all(item["data"].year == 2027 for item in lista)


def test_nome_que_nao_existe_nao_vira_data_aproximada():
    texto = calendario.formatar_feriados(
        calendario.proximos(HOJE, nome="dia do programador", limite=1),
        HOJE,
        nome="dia do programador",
    )
    assert "Não achei feriado com “dia do programador”" in texto
    assert "Próximos feriados" in texto


def test_ano_impossivel_e_recusado():
    assert calendario.ano_do_pedido(1800) is None
    assert calendario.ano_do_pedido("abc") is None
    assert calendario.ano_do_pedido("2027") == 2027


# ---------------------------------------------------------------------------
# O texto que vai para a conversa
# ---------------------------------------------------------------------------

def test_o_texto_diz_a_fonte_e_que_nada_foi_estimado():
    texto = calendario.formatar_feriados(calendario.proximos(HOJE, limite=3), HOJE)
    assert "Hoje é quarta-feira, 18/11/2026" in texto
    assert "Faltam 3 dias para o sábado" in texto
    assert "1. 20/11/2026 (sexta-feira) — Dia da Consciência Negra — em 2 dias" in texto
    assert "calculadas pela Páscoa" in texto
    assert "nada aqui foi estimado" in texto


def test_o_texto_marca_o_ponto_facultativo():
    texto = calendario.formatar_feriados(calendario.proximos(HOJE, limite=4), HOJE)
    assert "Carnaval — ponto facultativo" in texto


def test_so_um_feriado_muda_o_titulo():
    texto = calendario.formatar_feriados(calendario.proximos(HOJE, nome="natal", limite=1), HOJE, nome="natal")
    assert "Próximo feriado" in texto
    assert "Próximos feriados" not in texto


# ---------------------------------------------------------------------------
# A rota que a tela usa
# ---------------------------------------------------------------------------

@pytest.fixture()
def cliente(tmp_path):
    app = create_app(registry=build_registry(tmp_path / "files"))
    return TestClient(app)


def test_a_rota_de_feriados_devolve_texto_e_lista(cliente):
    resposta = cliente.get("/api/calendario", params={"tipo": "feriados", "limite": 3})
    assert resposta.status_code == 200
    corpo = resposta.json()

    assert corpo["ok"] is True
    assert corpo["fonte"] == "calendário do PC"
    assert "Próximos feriados" in corpo["texto"]
    assert len(corpo["result"]["feriados"]) == 3
    assert corpo["result"]["feriados"][0]["dia_semana"] in calendario.DIAS


def test_a_rota_da_data_devolve_o_dia_e_o_sabado(cliente):
    corpo = cliente.get("/api/calendario", params={"tipo": "dia"}).json()
    assert corpo["result"]["dia_semana"] in calendario.DIAS
    assert "Faltam" in corpo["result"]["fim_de_semana"] or "sábado" in corpo["result"]["fim_de_semana"]
    assert "sem modelo" in corpo["texto"]


def test_a_rota_por_nome(cliente):
    corpo = cliente.get("/api/calendario", params={"nome": "natal", "limite": 1}).json()
    assert corpo["result"]["feriados"][0]["nome"] == "Natal"


def test_a_rota_lista_um_ano(cliente):
    corpo = cliente.get("/api/calendario", params={"ano": 2027, "limite": 20}).json()
    assert all(item["data"].startswith("2027") for item in corpo["result"]["feriados"])


def test_a_rota_recusa_tipo_desconhecido(cliente):
    assert cliente.get("/api/calendario", params={"tipo": "horoscopo"}).status_code == 422
