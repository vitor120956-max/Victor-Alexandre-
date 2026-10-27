"""Testes da agenda — datas interpretadas sem modelo e sem adivinhação."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from server import agenda

AGORA = datetime(2026, 10, 26, 10, 0)  # uma segunda-feira


def test_amanha_com_hora():
    achado = agenda.interpretar_quando("amanhã às 14h", agora=AGORA)
    assert achado["quando"] == "2026-10-27T14:00:00"
    assert "terça-feira" in achado["texto"]
    assert "14:00" in achado["texto"]


def test_data_iso():
    achado = agenda.interpretar_quando("2026-11-05", agora=AGORA)
    assert achado["dia"] == "2026-11-05"
    assert achado["hora"] == "09:00"


def test_data_numerica_do_ano():
    achado = agenda.interpretar_quando("05/11/2027 às 8:30", agora=AGORA)
    assert achado["quando"] == "2027-11-05T08:30:00"


def test_data_numerica_que_passou_vai_para_o_proximo_ano():
    achado = agenda.interpretar_quando("01/02", agora=AGORA)
    assert achado["dia"] == "2027-02-01"


def test_dia_da_semana_e_sempre_o_proximo():
    achado = agenda.interpretar_quando("segunda às 9h", agora=AGORA)
    assert achado["dia"] == "2026-11-02"  # hoje é segunda: vale a próxima


def test_daqui_a_dias():
    achado = agenda.interpretar_quando("daqui a 3 dias", agora=AGORA)
    assert achado["dia"] == "2026-10-29"


@pytest.mark.parametrize("frase", ["qualquer dia", "", "depois", "semana que vem talvez"])
def test_frase_sem_data_recusa(frase):
    with pytest.raises(agenda.AgendaError):
        agenda.interpretar_quando(frase, agora=AGORA)


def test_adicionar_grava_e_mostra_o_que_entendeu(tmp_path):
    item = agenda.adicionar(titulo="Audiência", quando="amanhã às 14h", raiz=tmp_path, agora=AGORA)
    assert item["id"]
    assert item["quando"] == "2026-10-27T14:00:00"
    assert "Audiência" in item["resposta"]
    assert len(agenda.carregar(tmp_path)) == 1


def test_adicionar_no_passado_recusa(tmp_path):
    with pytest.raises(agenda.AgendaError) as erro:
        agenda.adicionar(titulo="Ontem", quando="ontem", raiz=tmp_path, agora=AGORA)
    assert "já passou" in str(erro.value) or "não reconheci" in str(erro.value).lower()


def test_listar_ordena_e_marca_atrasado(tmp_path):
    agenda.adicionar(titulo="Depois", quando="2026-11-10", raiz=tmp_path, agora=AGORA)
    agenda.adicionar(titulo="Antes", quando="2026-10-27", raiz=tmp_path, agora=AGORA)
    dados = agenda.listar(raiz=tmp_path, agora=datetime(2026, 10, 28, 10, 0))
    assert [item["titulo"] for item in dados["itens"]] == ["Antes", "Depois"]
    assert dados["itens"][0]["atrasado"] is True
    assert dados["atrasados"] == 1


def test_janela_de_dias(tmp_path):
    agenda.adicionar(titulo="Amanhã", quando="amanhã", raiz=tmp_path, agora=AGORA)
    agenda.adicionar(titulo="Mês que vem", quando="2026-12-01", raiz=tmp_path, agora=AGORA)
    dados = agenda.listar(raiz=tmp_path, agora=AGORA, dias=7)
    assert dados["total"] == 1
    assert dados["itens"][0]["titulo"] == "Amanhã"


def test_concluir_tira_da_lista_padrao(tmp_path):
    item = agenda.adicionar(titulo="Protocolo", quando="amanhã", raiz=tmp_path, agora=AGORA)
    agenda.concluir(item["id"], raiz=tmp_path)
    assert agenda.listar(raiz=tmp_path, agora=AGORA)["total"] == 0
    assert agenda.listar(raiz=tmp_path, agora=AGORA, incluir_concluidos=True)["total"] == 1


def test_remover(tmp_path):
    item = agenda.adicionar(titulo="Ligar", quando="amanhã", raiz=tmp_path, agora=AGORA)
    resultado = agenda.remover(item["id"], raiz=tmp_path)
    assert resultado["total"] == 0
    assert agenda.carregar(tmp_path) == []


def test_titulo_repetido_exige_id(tmp_path):
    agenda.adicionar(titulo="Reunião", quando="amanhã", raiz=tmp_path, agora=AGORA)
    agenda.adicionar(titulo="Reunião", quando="depois de amanhã", raiz=tmp_path, agora=AGORA)
    with pytest.raises(agenda.AgendaError) as erro:
        agenda.remover("reunião", raiz=tmp_path)
    assert "Use o id" in str(erro.value)


def test_texto_do_chat(tmp_path):
    agenda.adicionar(titulo="Prazo", quando="amanhã às 10h", raiz=tmp_path, agora=AGORA)
    dados = agenda.listar(raiz=tmp_path, agora=AGORA)
    texto = agenda.texto(dados["itens"], agora=AGORA)
    assert "Prazo" in texto and "10:00" in texto


# ---------------------------------------------------------------------------
# Lembretes (0.59.0)
# ---------------------------------------------------------------------------


def test_marcar_guarda_a_antecedencia(tmp_path):
    item = agenda.adicionar(titulo="Audiência", quando="amanhã às 14h", raiz=tmp_path, agora=AGORA)
    assert item["avisar_antes"] == 30
    assert "Aviso 30 min antes" in item["resposta"]
    sem_aviso = agenda.adicionar(
        titulo="Consulta", quando="amanhã às 16h", avisar_antes=0, raiz=tmp_path, agora=AGORA
    )
    assert sem_aviso["avisar_antes"] == 0
    assert "Sem aviso" in sem_aviso["resposta"]


def test_antecedencia_invalida_recusa(tmp_path):
    with pytest.raises(agenda.AgendaError):
        agenda.adicionar(titulo="X", quando="amanhã", avisar_antes="muito", raiz=tmp_path, agora=AGORA)


def test_devidos_traz_o_que_esta_chegando(tmp_path):
    agenda.adicionar(titulo="Reunião", quando="amanhã às 10h", raiz=tmp_path, agora=AGORA)
    lembretes = agenda.devidos(raiz=tmp_path, agora=datetime(2026, 10, 27, 9, 40), antecedencia=30)
    assert len(lembretes) == 1
    assert lembretes[0]["tipo"] == "chegando"
    assert lembretes[0]["minutos"] == 20
    assert lembretes[0]["id"]


def test_devidos_marca_atrasado_e_vem_primeiro(tmp_path):
    # cada compromisso declara a própria janela: 10h de antecedência nos dois
    agenda.adicionar(titulo="Cedo", quando="amanhã às 9h", avisar_antes=600, raiz=tmp_path, agora=AGORA)
    agenda.adicionar(titulo="Tarde", quando="amanhã às 18h", avisar_antes=600, raiz=tmp_path, agora=AGORA)
    lembretes = agenda.devidos(raiz=tmp_path, agora=datetime(2026, 10, 27, 10, 0), antecedencia=600)
    assert [item["titulo"] for item in lembretes] == ["Cedo", "Tarde"]
    assert lembretes[0]["tipo"] == "atrasado"
    assert lembretes[0]["minutos"] == 60
    assert lembretes[1]["tipo"] == "chegando"


def test_devidos_respeita_o_avisar_antes_de_cada_item(tmp_path):
    agenda.adicionar(titulo="Sem aviso", quando="amanhã às 10h", avisar_antes=0, raiz=tmp_path, agora=AGORA)
    agenda.adicionar(titulo="Com aviso", quando="amanhã às 10h", raiz=tmp_path, agora=AGORA)
    lembretes = agenda.devidos(raiz=tmp_path, agora=datetime(2026, 10, 27, 9, 45), antecedencia=120)
    assert [item["titulo"] for item in lembretes] == ["Com aviso"]


def test_devidos_pode_ignorar_atrasados(tmp_path):
    agenda.adicionar(titulo="Velho", quando="amanhã às 9h", avisar_antes=600, raiz=tmp_path, agora=AGORA)
    assert agenda.devidos(raiz=tmp_path, agora=datetime(2026, 10, 27, 12, 0), incluir_atrasados=False) == []


def test_concluido_nao_gera_lembrete(tmp_path):
    item = agenda.adicionar(titulo="Feito", quando="amanhã às 10h", raiz=tmp_path, agora=AGORA)
    agenda.concluir(item["id"], raiz=tmp_path)
    assert agenda.devidos(raiz=tmp_path, agora=datetime(2026, 10, 27, 9, 50)) == []


def test_texto_do_lembrete(tmp_path):
    agenda.adicionar(titulo="Prazo", quando="amanhã às 10h", raiz=tmp_path, agora=AGORA)
    lembretes = agenda.devidos(raiz=tmp_path, agora=datetime(2026, 10, 27, 9, 30), antecedencia=60)
    texto = agenda.texto_lembretes(lembretes)
    assert "Prazo" in texto and "em 30 min" in texto
    assert agenda.texto_lembretes([]) == "Nada vencendo agora."


def test_chave_do_lembrete_e_estavel(tmp_path):
    agenda.adicionar(titulo="Prazo", quando="amanhã às 10h", raiz=tmp_path, agora=AGORA)
    primeiro = agenda.devidos(raiz=tmp_path, agora=datetime(2026, 10, 27, 9, 30), antecedencia=60)[0]
    segundo = agenda.devidos(raiz=tmp_path, agora=datetime(2026, 10, 27, 9, 45), antecedencia=60)[0]
    assert agenda.chave_do_lembrete(primeiro) == agenda.chave_do_lembrete(segundo)


def test_duracao_legivel():
    assert agenda._duracao(5) == "5 min"
    assert agenda._duracao(90) == "1h30"
    assert agenda._duracao(120) == "2h"
    assert agenda._duracao(60 * 26) == "1d 2h"


# ---------------------------------------------------------------------------
# A rota que a tela consulta (0.59.0)
# ---------------------------------------------------------------------------


@pytest.fixture()
def api(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from server.app import create_app
    from server.skill_registry import build_registry

    monkeypatch.setenv("JARVIS_DADOS", str(tmp_path))
    monkeypatch.setenv("JARVIS_HOST_TOKEN_SILENCIOSO", "1")
    aplicacao = create_app(registry=build_registry(tmp_path / "files"))
    with TestClient(aplicacao) as cliente:
        yield cliente


def test_rota_de_lembretes_nao_grava_e_devolve_o_texto(api, tmp_path):
    from datetime import timedelta

    agora = datetime.now().replace(microsecond=0)
    agenda.adicionar(
        titulo="Audiência",
        quando=(agora + timedelta(minutes=10)).strftime("%Y-%m-%d %H:%M"),
        raiz=tmp_path,
        agora=agora,
    )
    corpo = api.get("/api/agenda/lembretes?antecedencia=30").json()
    assert corpo["ok"] is True
    assert corpo["total"] == 1
    assert corpo["lembretes"][0]["titulo"] == "Audiência"
    assert corpo["lembretes"][0]["tipo"] == "chegando"
    assert "Audiência" in corpo["texto"]
    # nada foi marcado como concluído nem reescrito
    assert len(agenda.carregar(tmp_path)) == 1


def test_rota_de_lembretes_vazia(api):
    corpo = api.get("/api/agenda/lembretes").json()
    assert corpo["total"] == 0
    assert corpo["texto"] == "Nada vencendo agora."


def test_rota_recusa_antecedencia_invalida(api):
    resposta = api.get("/api/agenda/lembretes?antecedencia=-5")
    assert resposta.status_code in (400, 422)


def test_sem_lembrete_o_compromisso_distante_fica_fora(api, tmp_path):
    from datetime import timedelta

    agora = datetime.now().replace(microsecond=0)
    agenda.adicionar(
        titulo="Mês que vem",
        quando=(agora + timedelta(days=30)).strftime("%Y-%m-%d %H:%M"),
        raiz=tmp_path,
        agora=agora,
    )
    assert api.get("/api/agenda/lembretes").json()["total"] == 0
