"""Provedores: quem é grátis, quem é pago, e trocar de casa sem perder chave.

O que estes testes protegem, em uma frase cada:

- a lista diz a verdade sobre preço (DeepSeek e Claude **não** são grátis na API);
- a cara da chave identifica o provedor — e `sk-` sozinho não chuta;
- trocar de provedor grava endereço e modelo no `.env` e recarrega na hora;
- as chaves do provedor que sai ficam guardadas e voltam se ele for escolhido;
- a lista de modelos vem da conta (`GET /models`), com `:free` primeiro.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from server import chaves, modelos, provedores


@pytest.fixture()
def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    caminho = tmp_path / ".env"
    caminho.write_bytes(
        b"# comentario do dono\r\n"
        b"JARVIS_DONO=1\r\n"
        b"JARVIS_AI_PROVIDER=Groq\r\n"
        b"JARVIS_AI_BASE_URL=https://api.groq.com/openai/v1\r\n"
        b"JARVIS_AI_MODEL=llama-3.3-70b-versatile\r\n"
        b"JARVIS_AI_API_KEY=\r\n"
    )
    monkeypatch.setattr(chaves, "ENV_CAMINHO", caminho)
    for nome in chaves.CHAVES_IA:
        monkeypatch.delenv(nome, raising=False)
    return caminho


def _env_texto(caminho: Path) -> str:
    return caminho.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# O catálogo diz a verdade
# ---------------------------------------------------------------------------

def test_todo_provedor_tem_id_unico_e_preco_declarado():
    ids = [item["id"] for item in provedores.PROVEDORES]
    assert len(ids) == len(set(ids))
    for item in provedores.PROVEDORES:
        assert item["gratis"], item["id"]
        assert item["onde"], item["id"]
        assert item["base"].startswith("https://"), item["id"]
        assert item["modelos"], item["id"]


def test_deepseek_e_claude_sao_declarados_pagos():
    """A pergunta que o dono fez: “dá para usar DeepSeek ou Claude de graça?”

    Na API, não. O site do DeepSeek e o claude.ai são grátis, mas não são API.
    Deixar isso implícito faria a pessoa criar conta para descobrir depois.
    """
    assert provedores.POR_ID["deepseek"]["gratis"] == "não"
    assert provedores.POR_ID["anthropic"]["gratis"] == "não"
    assert "chat.deepseek.com" in provedores.POR_ID["deepseek"]["nota"]


def test_os_tres_caminhos_gratis_estao_marcados():
    for id_gratis in ("groq", "google", "openrouter"):
        assert provedores.POR_ID[id_gratis]["gratis"].startswith("sim"), id_gratis
    # O OpenRouter é a ponte para DeepSeek de graça: a nota tem de dizer o sufixo.
    assert ":free" in provedores.POR_ID["openrouter"]["nota"]


def test_catalogo_marca_quem_esta_em_uso(env: Path):
    dados = provedores.catalogo()
    assert dados["atual"] == "groq"
    atual = [item for item in dados["provedores"] if item["atual"]]
    assert [item["id"] for item in atual] == ["groq"]


# ---------------------------------------------------------------------------
# A cara da chave
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "chave, esperado",
    [
        ("gsk_abc", "groq"),
        ("sk-or-v1-abc", "openrouter"),
        ("sk-ant-abc", "anthropic"),
        ("AIza" + "x" * 30, "google"),  # formato antigo
        ("AQ.Ab8" + "x" * 40, "google"),  # formato novo do AI Studio
        ("csk-abc", "cerebras"),
        # Ambíguo de propósito: DeepSeek, OpenAI e outros usam `sk-`.
        ("sk-abc", None),
        ("", None),
    ],
)
def test_detectar_pela_cara_da_chave(chave: str, esperado: str | None):
    assert provedores.detectar(chave) == esperado


def test_detectar_varias_nao_chuta_com_lista_misturada():
    assert provedores.detectar_varias(["gsk_a", "gsk_b"]) == "groq"
    assert provedores.detectar_varias(["gsk_a", "AIzaB"]) is None
    assert provedores.detectar_varias([]) is None


# ---------------------------------------------------------------------------
# Trocar de provedor
# ---------------------------------------------------------------------------

def test_aplicar_grava_endereco_modelo_e_provedor(env: Path):
    resultado = provedores.aplicar("google")
    texto = _env_texto(env)
    assert "JARVIS_AI_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai" in texto
    assert "JARVIS_AI_MODEL=gemini-2.5-flash" in texto
    assert "JARVIS_AI_PROVIDER=Google Gemini" in texto
    assert resultado["provedor"] == "google"
    assert os.environ["JARVIS_AI_BASE_URL"].startswith("https://generativelanguage")
    # O resto do `.env` sobrevive: trocar de provedor não é apagar configuração.
    assert "JARVIS_DONO=1" in texto


def test_as_chaves_do_provedor_anterior_ficam_guardadas_e_voltam(env: Path):
    chaves.salvar("gsk_" + "A" * 40)
    assert chaves.estado()["quantidade"] == 1

    provedores.aplicar("google")
    assert chaves.estado()["quantidade"] == 0
    assert f"JARVIS_CHAVES_GROQ=gsk_{'A' * 40}" in _env_texto(env)

    voltou = provedores.aplicar("groq")
    assert voltou["chaves_voltaram"] == 1
    assert chaves.estado()["quantidade"] == 1
    assert chaves.estado()["provedor_id"] == "groq"


def test_aplicar_modelo_escolhido_a_mao(env: Path):
    resultado = provedores.aplicar("openrouter", "deepseek/deepseek-r1:free")
    assert resultado["modelo"] == "deepseek/deepseek-r1:free"
    assert "JARVIS_AI_MODEL=deepseek/deepseek-r1:free" in _env_texto(env)


def test_provedor_desconhecido_nao_grava_nada(env: Path):
    antes = _env_texto(env)
    with pytest.raises(provedores.ProvedorInvalido):
        provedores.aplicar("nao-existe")
    assert _env_texto(env) == antes


def test_por_base_reconhece_endereco_com_e_sem_sufixo():
    assert provedores.por_base("https://api.groq.com/openai/v1")["id"] == "groq"
    assert provedores.por_base("https://api.groq.com/openai/v1/")["id"] == "groq"
    assert provedores.por_base("http://127.0.0.1:8080/v1") is None
    assert provedores.por_base("") is None


# ---------------------------------------------------------------------------
# Salvar chave de outro provedor troca a casa sozinho
# ---------------------------------------------------------------------------

def test_colar_chave_do_google_troca_o_provedor_sozinho(env: Path):
    """Sem isso, a chave nova bateria na porta do Groq e daria 401 sem explicação."""
    resultado = chaves.salvar("AIza" + "B" * 35)
    assert resultado["provedor_id"] == "google"
    assert resultado["base"].startswith("https://generativelanguage")
    assert "Google Gemini" in resultado["resumo"]


def test_colar_chave_ambigua_nao_troca_o_endereco(env: Path):
    """`sk-…` pode ser DeepSeek, OpenAI ou outro: melhor não chutar endereço."""
    chaves.salvar("sk-" + "C" * 40)
    assert chaves.estado()["base"] == "https://api.groq.com/openai/v1"


# ---------------------------------------------------------------------------
# O catálogo de modelos acompanha o provedor
# ---------------------------------------------------------------------------

def test_modelos_do_google_nao_mostram_nome_do_groq(env: Path):
    provedores.aplicar("google")
    dados = modelos.estado()
    ids = [item["id"] for item in dados["opcoes"]]
    assert dados["provedor_id"] == "google"
    assert dados["padrao"] == "gemini-2.5-flash"
    assert "llama-3.3-70b-versatile" not in ids
    assert all(item.startswith("gemini") for item in ids)


def test_restaurar_volta_ao_padrao_do_provedor_em_uso(env: Path):
    provedores.aplicar("openrouter")
    chaves.salvar("sk-or-v1-" + "D" * 40)
    modelos.aplicar("deepseek/deepseek-r1:free")
    resultado = modelos.restaurar()
    assert resultado["modelo"] == "deepseek/deepseek-chat-v3-0324:free"


# ---------------------------------------------------------------------------
# A lista real da conta
# ---------------------------------------------------------------------------

class _Resposta:
    def __init__(self, status_code: int, corpo: object) -> None:
        self.status_code = status_code
        self._corpo = corpo

    def json(self) -> object:
        return self._corpo


def _buscador(status: int, corpo: object):
    def buscar(url: str, cabecalho: dict[str, str], tempo: float) -> _Resposta:
        assert url.endswith("/models"), url
        assert cabecalho["Authorization"].startswith("Bearer ")
        return _Resposta(status, corpo)

    return buscar


def test_listar_modelos_marca_free_e_poe_gratis_primeiro(env: Path):
    chaves.salvar("sk-or-v1-" + "E" * 40)
    corpo = {
        "data": [
            {"id": "openai/gpt-4o"},
            {"id": "deepseek/deepseek-r1:free"},
            {"id": "deepseek/deepseek-chat-v3-0324:free"},
        ]
    }
    resultado = provedores.listar_modelos(buscador=_buscador(200, corpo))
    assert resultado["total"] == 3
    assert resultado["gratis"] == 2
    assert resultado["modelos"][0]["id"].endswith(":free")
    assert "grátis" in resultado["resumo"]


def test_listar_modelos_sem_chave_nao_chama_rede(env: Path):
    with pytest.raises(provedores.ProvedorInvalido, match="sem chave"):
        provedores.listar_modelos(buscador=_buscador(200, {"data": []}))


def test_listar_modelos_com_401_diz_onde_pegar_outra(env: Path):
    chaves.salvar("gsk_" + "F" * 40)
    with pytest.raises(provedores.ProvedorInvalido, match="console.groq.com/keys"):
        provedores.listar_modelos(buscador=_buscador(401, {}))


def test_listar_modelos_que_nao_existe_nao_inventa_lista(env: Path):
    chaves.salvar("gsk_" + "G" * 40)
    with pytest.raises(provedores.ProvedorInvalido, match="não publica lista"):
        provedores.listar_modelos(buscador=_buscador(404, {}))


def test_listar_modelos_sem_duplicata_e_com_teto(env: Path):
    chaves.salvar("gsk_" + "H" * 40)
    corpo = {"data": [{"id": "a"}, {"id": "a"}, {"id": "b"}, {"id": "c"}]}
    resultado = provedores.listar_modelos(buscador=_buscador(200, corpo), limite=2)
    ids = [item["id"] for item in resultado["modelos"]]
    assert ids == ["a", "b"]
    assert resultado["total"] == 3
