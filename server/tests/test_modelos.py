"""Testes do catálogo de modelos (0.79.1).

A pergunta foi *“e sobre os modelos, como funcionam?”*. A resposta virou uma
lista com o custo de cada opção e um botão que grava a escolha no `.env`. Aqui se
prova o que não pode dar errado:

1. o `.env` é tocado **só** na linha do modelo;
2. nome inválido é recusado antes de virar arquivo;
3. a lista é catálogo aberto: o campo livre aceita qualquer nome real;
4. modelo local não recebe catálogo de nuvem.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from server import chaves, modelos


@pytest.fixture()
def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    arquivo = tmp_path / ".env"
    arquivo.write_text(
        "JARVIS_AI_PROVIDER=Groq\r\n"
        "JARVIS_AI_BASE_URL=https://api.groq.com/openai/v1\r\n"
        "JARVIS_AI_MODEL=llama-3.3-70b-versatile\r\n"
        "JARVIS_AI_API_KEY=gsk_de_teste_nao_e_real\r\n"
        "OUTRA_COISA=fica\r\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(chaves, "ENV_CAMINHO", arquivo)
    return arquivo


def test_catalogo_tem_o_padrao_e_diz_o_que_cada_um_custa():
    ids = [item["id"] for item in modelos.CATALOGO]
    assert modelos.MODELO_PADRAO in ids
    for item in modelos.CATALOGO:
        assert item["quando"].strip(), item["id"]
        assert item["perfil"].strip(), item["id"]


def test_estado_marca_qual_esta_em_uso(env: Path):
    dados = modelos.estado()
    assert dados["modelo"] == "llama-3.3-70b-versatile"
    assert dados["padrao"] == modelos.MODELO_PADRAO
    atual = [item for item in dados["opcoes"] if item["atual"]]
    assert len(atual) == 1 and atual[0]["id"] == "llama-3.3-70b-versatile"
    assert dados["local"] is False


def test_aplicar_troca_so_a_linha_do_modelo(env: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("JARVIS_AI_MODEL", "llama-3.3-70b-versatile")
    resultado = modelos.aplicar("llama-3.1-8b-instant")
    assert resultado["modelo"] == "llama-3.1-8b-instant"
    texto = env.read_text(encoding="utf-8")
    assert "JARVIS_AI_MODEL=llama-3.1-8b-instant" in texto
    # A chave continua lá, e o resto do arquivo não foi tocado.
    assert "gsk_de_teste_nao_e_real" in texto
    assert "OUTRA_COISA=fica" in texto
    assert "JARVIS_AI_PROVIDER=Groq" in texto


def test_aplicar_grava_em_crlf(env: Path):
    modelos.aplicar("openai/gpt-oss-20b")
    bruto = env.read_bytes()
    assert b"\r\n" in bruto
    assert b"\xef\xbb\xbf" not in bruto  # sem BOM


def test_nome_invalido_e_recusado_antes_de_gravar(env: Path):
    antes = env.read_text(encoding="utf-8")
    for ruim in ("", "   ", "modelo com espaço", "a" * 200, "'; rm -rf /", "modelo\nquebrado"):
        with pytest.raises(modelos.ModeloInvalido):
            modelos.aplicar(ruim)
    assert env.read_text(encoding="utf-8") == antes


def test_nome_com_barra_e_aceito(env: Path):
    """`openai/gpt-oss-120b` é nome real, com barra. Recusar seria negar o modelo."""
    modelos.aplicar("meta-llama/llama-4-scout-17b-16e-instruct")
    assert "JARVIS_AI_MODEL=meta-llama/llama-4-scout-17b-16e-instruct" in env.read_text(encoding="utf-8")


def test_restaurar_volta_ao_padrao(env: Path):
    modelos.aplicar("llama-3.1-8b-instant")
    modelos.restaurar()
    assert f"JARVIS_AI_MODEL={modelos.MODELO_PADRAO}" in env.read_text(encoding="utf-8")


def test_modelo_local_avisa_que_o_nome_e_o_arquivo(env: Path):
    texto = env.read_text(encoding="utf-8").replace(
        "https://api.groq.com/openai/v1", "http://127.0.0.1:8080/v1"
    )
    env.write_text(texto, encoding="utf-8")
    dados = modelos.estado()
    assert dados["local"] is True
    assert "gguf" in dados["nota"]
