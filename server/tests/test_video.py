"""Testes da legenda de vídeo (0.43.0): link, escolha de idioma e importação.

Sem rede: o HTML do YouTube é montado no teste e injetado por `buscar=`.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from server import biblioteca, video
from server.video import VideoError, id_do_video, legenda

FALA = (
    "Nesta aula eu explico o rateio de custo indireto: a despesa comum da fabrica "
    "e distribuida entre os produtos conforme o criterio que a contabilidade escolher, "
    "e o total rateado tem de fechar com o total da conta."
)


def _json3(texto: str = FALA) -> str:
    pedacos = texto.split()
    return json.dumps(
        {
            "events": [
                {"tStartMs": 0, "segs": [{"utf8": pedaco + " "} for pedaco in pedacos[:5]]},
                {"tStartMs": 2000, "segs": [{"utf8": " ".join(pedacos[5:]) + " "}]},
            ]
        }
    )


def _html(faixas: list[dict[str, str]]) -> str:
    dados = {"captions": {"playerCaptionsTracklistRenderer": {"captionTracks": faixas}}}
    return (
        '<html><head><title>Aula de rateio - YouTube</title></head><body>'
        "var ytInitialPlayerResponse = "
        + json.dumps(dados)
        + ';var meta = {};</script></body></html>'
    )


def _faixa(idioma: str, url: str, asr: bool = False) -> dict[str, str]:
    item = {"baseUrl": url, "languageCode": idioma, "name": {"simpleText": idioma}}
    if asr:
        item["kind"] = "asr"
    return item


def _buscador(pagina: str, legendas: dict[str, str], vistos: list[str] | None = None):
    def buscar(url: str) -> str:
        if vistos is not None:
            vistos.append(url)
        if "timedtext" in url:
            for chave, valor in legendas.items():
                if chave in url:
                    return valor
            return ""
        return pagina

    return buscar


@pytest.mark.parametrize(
    "entrada",
    [
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        "https://youtu.be/dQw4w9WgXcQ?t=30",
        "https://www.youtube.com/shorts/dQw4w9WgXcQ",
        "https://www.youtube.com/embed/dQw4w9WgXcQ",
        "www.youtube.com/watch?v=dQw4w9WgXcQ&list=PL123",
        "dQw4w9WgXcQ",
    ],
)
def test_id_do_video_aceita_varios_formatos(entrada):
    assert id_do_video(entrada) == "dQw4w9WgXcQ"


@pytest.mark.parametrize("entrada", ["", "https://www.youtube.com/", "https://exemplo.com/video", "abc"])
def test_id_do_video_recusa_link_sem_id(entrada):
    with pytest.raises(VideoError):
        id_do_video(entrada)


def test_legenda_baixa_json3_e_prefere_portugues():
    pagina = _html(
        [
            _faixa("en", "https://www.youtube.com/api/timedtext?v=x&lang=en"),
            _faixa("pt-BR", "https://www.youtube.com/api/timedtext?v=x&lang=pt-BR", asr=True),
        ]
    )
    vistos: list[str] = []
    resultado = legenda(
        "https://youtu.be/dQw4w9WgXcQ",
        buscar=_buscador(pagina, {"lang=pt-BR": _json3(), "lang=en": _json3("only english")}, vistos),
    )
    assert resultado["video_id"] == "dQw4w9WgXcQ"
    assert resultado["idioma"] == "pt-BR"
    assert resultado["automatica"] is True
    assert "rateio de custo indireto" in resultado["texto"]
    assert resultado["titulo"].startswith("Aula de rateio")
    assert any("fmt=json3" in url for url in vistos)


def test_legenda_cai_para_ingles_quando_nao_ha_portugues():
    pagina = _html([_faixa("en", "https://www.youtube.com/api/timedtext?v=x&lang=en")])
    resultado = legenda(
        "dQw4w9WgXcQ",
        buscar=_buscador(pagina, {"lang=en": _json3("this lesson explains overhead allocation")}),
    )
    assert resultado["idioma"] == "en"
    assert resultado["automatica"] is False


def test_legenda_aceita_xml_quando_o_json3_nao_vem():
    pagina = _html([_faixa("pt", "https://www.youtube.com/api/timedtext?v=x&lang=pt")])
    xml = '<transcript><text start="0" dur="2">rateio de custo</text><text start="2" dur="2">indireto</text></transcript>'
    resultado = legenda("dQw4w9WgXcQ", buscar=_buscador(pagina, {"lang=pt": xml}))
    assert "rateio de custo indireto" in resultado["texto"]


def test_video_sem_legenda_explica_que_nao_transcreve():
    pagina = _html([])
    with pytest.raises(VideoError) as erro:
        legenda("dQw4w9WgXcQ", buscar=_buscador(pagina, {}))
    assert "não tem legenda" in str(erro.value)
    assert "não transcreve" in str(erro.value)


def test_pagina_sem_faixas_mas_com_atalho_no_html():
    bruto = (
        'var ytInitialPlayerResponse = {"videoDetails":{"title":"Aula"}};</script>'
        '"captions":{"playerCaptionsTracklistRenderer":{"captionTracks":[{"baseUrl":"https://www.youtube.com/api/timedtext?v=x&lang=pt","languageCode":"pt"}]}},'
    )
    resultado = legenda("dQw4w9WgXcQ", buscar=_buscador(bruto, {"lang=pt": _json3()}))
    assert resultado["idioma"] == "pt"
    assert resultado["texto"]


def test_legenda_vazia_e_erro():
    pagina = _html([_faixa("pt", "https://www.youtube.com/api/timedtext?v=x&lang=pt")])
    with pytest.raises(VideoError) as erro:
        legenda("dQw4w9WgXcQ", buscar=_buscador(pagina, {"lang=pt": '{"events":[]}'}))
    assert "vazia" in str(erro.value)


def test_biblioteca_importa_video_como_fonte(tmp_path, monkeypatch):
    monkeypatch.setattr(biblioteca.dados, "raiz", lambda: tmp_path)
    monkeypatch.setenv("JARVIS_HOST_REDE", "1")
    pagina = _html([_faixa("pt-BR", "https://www.youtube.com/api/timedtext?v=x&lang=pt-BR")])
    fonte = biblioteca.importar_video(
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        buscar=_buscador(pagina, {"lang=pt-BR": _json3()}),
    )
    assert fonte["tipo"] == "video"
    assert fonte["origem"].endswith("dQw4w9WgXcQ")
    assert fonte["idioma"] == "pt-BR"
    assert Path(tmp_path, "biblioteca").exists()
    achados = biblioteca.buscar("rateio de custo indireto", limite=3)
    assert achados and "rateio" in achados[0]["trecho"].lower()


def test_biblioteca_recusa_video_sem_legenda(tmp_path, monkeypatch):
    monkeypatch.setattr(biblioteca.dados, "raiz", lambda: tmp_path)
    monkeypatch.setenv("JARVIS_HOST_REDE", "1")
    with pytest.raises(biblioteca.BibliotecaError) as erro:
        biblioteca.importar_video("dQw4w9WgXcQ", buscar=_buscador(_html([]), {}))
    assert "legenda" in str(erro.value).lower()


def test_biblioteca_recusa_legenda_com_a_rede_desligada(tmp_path, monkeypatch):
    monkeypatch.setattr(biblioteca.dados, "raiz", lambda: tmp_path)
    monkeypatch.delenv("JARVIS_HOST_REDE", raising=False)
    with pytest.raises(biblioteca.BibliotecaError) as erro:
        biblioteca.importar_video("dQw4w9WgXcQ")
    assert "JARVIS_HOST_REDE=1" in str(erro.value)
