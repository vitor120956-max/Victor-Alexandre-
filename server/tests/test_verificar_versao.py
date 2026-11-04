"""Testes do `verificar-versao.py` (0.79.1) — o duplo clique que diz a verdade.

Ele existe porque o print da tela (“VERSÃO 0.5.0”) não dizia se o problema era
arquivo, processo ou cache. Aqui se prova que o veredito muda com o fato:

* API fora → manda abrir o `iniciar-jarvis.bat`;
* API de versão diferente da do disco → manda fechar a janela no X e abrir de novo;
* tela mais velha que o servidor → manda rodar o `atualizar.bat`;
* tudo batendo → manda Ctrl+F5 e para de alarmar.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

# O `verificar-versao.py` vive na raiz (é o que o `.bat` chama), fora do pacote
# `server` — por isso o caminho entra à mão antes do import.
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import verificar_versao as vv  # noqa: E402


def _interface(base: Path, versao: str) -> None:
    pasta = base / "web-dist"
    (pasta / "assets").mkdir(parents=True, exist_ok=True)
    (pasta / "index.html").write_text("<html></html>", encoding="utf-8")
    (pasta / "versao.json").write_text(json.dumps({"versao": versao}), encoding="utf-8")


@pytest.fixture()
def sem_api(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(vv, "_api", lambda porta: {})


@pytest.fixture()
def raiz(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(vv, "RAIZ", tmp_path)
    monkeypatch.setattr(vv, "_versao_do_arquivo", lambda: "0.79.1")
    return tmp_path


def test_api_fora_manda_abrir_o_iniciar(raiz: Path, sem_api):
    _interface(raiz, "0.79.1")
    dados = vv.diagnostico(8000)
    assert dados["pronto"] is False
    assert any("não respondeu" in item for item in dados["problemas"])
    assert any("iniciar-jarvis" in acao for acao in dados["acoes"])


def test_api_de_versao_diferente_manda_reiniciar(raiz: Path, monkeypatch: pytest.MonkeyPatch):
    _interface(raiz, "0.75.0")
    monkeypatch.setattr(vv, "_api", lambda porta: {"version": "0.75.0", "interface": "web-dist"})
    dados = vv.diagnostico(8000)
    assert dados["pronto"] is False
    assert any("em execução" in item for item in dados["problemas"])
    assert any("X" in acao and "iniciar-jarvis" in acao for acao in dados["acoes"])


def test_tela_mais_velha_manda_atualizar(raiz: Path, monkeypatch: pytest.MonkeyPatch):
    _interface(raiz, "0.76.1")
    monkeypatch.setattr(
        vv, "_api", lambda porta: {"version": "0.79.1", "interface": "web-dist", "interfaceVersao": "0.76.1"}
    )
    dados = vv.diagnostico(8000)
    assert any("mais velha" in item for item in dados["problemas"])
    assert any("atualizar.bat" in acao for acao in dados["acoes"])


def test_tudo_certo_manda_ctrl_f5(raiz: Path, monkeypatch: pytest.MonkeyPatch):
    _interface(raiz, "0.79.1")
    monkeypatch.setattr(
        vv, "_api", lambda porta: {"version": "0.79.1", "interface": "web-dist", "interfaceVersao": "0.79.1"}
    )
    dados = vv.diagnostico(8000)
    assert dados["pronto"] is True, dados["problemas"]
    assert any("Ctrl+F5" in acao for acao in dados["acoes"])


def test_relatorio_mostra_os_dois_numeros(raiz: Path, monkeypatch: pytest.MonkeyPatch):
    _interface(raiz, "0.76.1")
    monkeypatch.setattr(
        vv, "_api", lambda porta: {"version": "0.79.1", "interface": "web-dist", "interfaceVersao": "0.76.1"}
    )
    texto = vv.relatorio(vv.diagnostico(8000))
    assert "0.79.1" in texto and "0.76.1" in texto
    assert "VEREDITO" in texto
    # O que fazer vem em linha separada, para copiar sem juntar dois comandos.
    assert "atualizar.bat" in texto


def test_json_nao_quebra(raiz: Path, sem_api):
    _interface(raiz, "0.79.1")
    json.dumps(vv.diagnostico(8000), ensure_ascii=False)


def test_retorno_de_codigo_distingue_certo_de_errado(raiz: Path, sem_api, capsys):
    _interface(raiz, "0.79.1")
    assert vv.main([]) == 2  # sem API: tem coisa a fazer
