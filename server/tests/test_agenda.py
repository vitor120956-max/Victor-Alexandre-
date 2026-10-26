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
