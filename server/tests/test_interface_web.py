"""Testes do carimbo de versão da interface (0.79.1).

O caso real: *“já atualizei mas ainda não tem a parte para botar as APIs”*, com
o rodapé dizendo `VERSÃO 0.5.0`. Python novo, tela velha — e nenhuma forma de a
pessoa saber qual das duas metades falhou. Aqui se prova que:

1. a pasta servida é a de **maior versão carimbada**, não a de data mais nova;
2. pasta sem carimbo (build antigo) não esconde a que veio na atualização;
3. `JARVIS_INTERFACE` manda, para quem desenvolve;
4. o `estado()` só acusa “desatualizada” quando existem dois números.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from server import interface_web


def _pasta(base: Path, nome: str, versao: str | None, *, mtime: float | None = None) -> Path:
    pasta = base / nome
    (pasta / "assets").mkdir(parents=True, exist_ok=True)
    (pasta / "index.html").write_text("<html></html>", encoding="utf-8")
    (pasta / "assets" / "app.js").write_text("console.log(1)", encoding="utf-8")
    if versao:
        (pasta / interface_web.ARQUIVO_VERSAO).write_text(
            json.dumps({"versao": versao}), encoding="utf-8"
        )
    if mtime is not None:
        os.utime(pasta / "index.html", (mtime, mtime))
    return pasta


# ------------------------------------------------------------- versão e carimbo

def test_le_a_versao_carimbada(tmp_path):
    pasta = _pasta(tmp_path, "web-dist", "0.79.1")
    assert interface_web.versao_da_pasta(pasta) == "0.79.1"


def test_sem_carimbo_nao_inventa_versao(tmp_path):
    pasta = _pasta(tmp_path, "dist", None)
    assert interface_web.versao_da_pasta(pasta) is None


def test_carimbo_quebrado_nao_derruba_nada(tmp_path):
    pasta = _pasta(tmp_path, "web-dist", None)
    (pasta / interface_web.ARQUIVO_VERSAO).write_text("{isso não é json", encoding="utf-8")
    assert interface_web.versao_da_pasta(pasta) is None


@pytest.mark.parametrize(
    "nova, velha, esperado",
    [
        ("0.79.1", "0.79.0", True),
        ("0.79.0", "0.79.1", False),
        ("0.100.0", "0.99.9", True),   # 100 > 99: comparar como texto erraria
        ("0.79.0", None, True),
        ("0.79.0", "0.79.0", False),
    ],
)
def test_compara_versao_por_numero(nova: str, velha: str | None, esperado: bool):
    assert interface_web.mais_nova(nova, velha) is esperado


# ----------------------------------------------------------- escolha da pasta

def test_sem_interface_devolve_none(tmp_path):
    assert interface_web.escolher(tmp_path) is None


def test_carimbo_vence_data_mais_nova(tmp_path):
    """`dist` recém-compilado (sem carimbo) não pode ganhar da `web-dist` 0.79.1."""
    _pasta(tmp_path, "dist", None, mtime=2_000_000_000)
    _pasta(tmp_path, "web-dist", "0.79.1", mtime=1_000_000_000)
    escolhida = interface_web.escolher(tmp_path)
    assert escolhida is not None and escolhida.name == "web-dist"


def test_entre_duas_carimbadas_ganha_a_maior(tmp_path):
    _pasta(tmp_path, "dist", "0.78.0")
    _pasta(tmp_path, "web-dist", "0.79.1")
    escolhida = interface_web.escolher(tmp_path)
    assert escolhida is not None and escolhida.name == "web-dist"


def test_sem_carimbo_nenhum_cai_na_data(tmp_path):
    """Compatível com quem tem build de antes da 0.79.1: a regra antiga vale."""
    _pasta(tmp_path, "dist", None, mtime=1_600_000_000)
    _pasta(tmp_path, "web-dist", None, mtime=1_700_000_000)
    escolhida = interface_web.escolher(tmp_path)
    assert escolhida is not None and escolhida.name == "web-dist"


def test_variavel_de_ambiente_manda(tmp_path, monkeypatch: pytest.MonkeyPatch):
    _pasta(tmp_path, "dist", "0.78.0")
    _pasta(tmp_path, "web-dist", "0.79.1")
    monkeypatch.setenv(interface_web.AMBIENTE_ESCOLHA, "dist")
    escolhida = interface_web.escolher(tmp_path)
    assert escolhida is not None and escolhida.name == "dist"


def test_variavel_invalida_e_ignorada(tmp_path, monkeypatch: pytest.MonkeyPatch):
    _pasta(tmp_path, "web-dist", "0.79.1")
    monkeypatch.setenv(interface_web.AMBIENTE_ESCOLHA, "outra-coisa")
    escolhida = interface_web.escolher(tmp_path)
    assert escolhida is not None and escolhida.name == "web-dist"


# ------------------------------------------------------------------- estado()

def test_estado_acusa_tela_mais_velha(tmp_path):
    _pasta(tmp_path, "web-dist", "0.76.1")
    quadro = interface_web.estado(tmp_path, versao_servidor="0.79.1")
    assert quadro["servida"] == "web-dist"
    assert quadro["versao"] == "0.76.1"
    assert quadro["desatualizada"] is True
    assert "0.76.1" in (quadro["aviso"] or "") and "0.79.1" in (quadro["aviso"] or "")


def test_estado_calado_quando_bate(tmp_path):
    _pasta(tmp_path, "web-dist", "0.79.1")
    quadro = interface_web.estado(tmp_path, versao_servidor="0.79.1")
    assert quadro["desatualizada"] is False
    assert quadro["aviso"] is None


def test_estado_sem_carimbo_nao_alarma(tmp_path):
    """“Não sei” é melhor do que alarme sem motivo."""
    _pasta(tmp_path, "dist", None)
    quadro = interface_web.estado(tmp_path, versao_servidor="0.79.1")
    assert quadro["servida"] == "dist"
    assert quadro["versao"] is None
    assert quadro["desatualizada"] is False
    assert quadro["candidatas"][0]["carimbo"] is False


def test_estado_sem_interface_explica(tmp_path):
    quadro = interface_web.estado(tmp_path, versao_servidor="0.79.1")
    assert quadro["servida"] is None
    assert "npm run build" in (quadro["aviso"] or "")


# --------------------------------------------------- o repositório de verdade

def test_a_interface_embutida_do_repositorio_tem_carimbo():
    """`web-dist` versionada precisa declarar a própria versão — é o que a API lê."""
    raiz = Path(__file__).resolve().parents[2]
    versao = interface_web.versao_da_pasta(raiz / "web-dist")
    assert versao, "web-dist sem versao.json: rode `npm run build:embutido`"
    from server.atualizacao import VERSAO

    assert versao == VERSAO, f"web-dist é {versao} e o servidor é {VERSAO}"
