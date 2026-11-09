"""Conectores por token: Notion, Linear, Dropbox, Vercel e Supabase (0.82.0).

A pergunta do dono: “não tem como criar conectores igual ao do Arena?”. A
resposta é sim, com token pessoal — o mesmo resultado de OAuth, sem precisar
registrar aplicativo. Estes testes prendem o essencial:

- o token **nunca** aparece numa resposta, nem na máscara nem no erro;
- gravar exige token com cara de token e, no Supabase, o endereço do projeto;
- o teste é chamada de leitura de verdade, com a frase certa em 401 e 404;
- cada serviço autentica do jeito dele (a Linear não usa `Bearer`).
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from server import chaves, conectores_tokens as ct

TOKEN = "secret_teste_1234567890abcdef"


@pytest.fixture()
def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    caminho = tmp_path / ".env"
    caminho.write_bytes(b"JARVIS_DONO=1\r\n")
    monkeypatch.setattr(chaves, "ENV_CAMINHO", caminho)
    for dados in ct.PROVEDORES.values():
        monkeypatch.delenv(dados["variavel"], raising=False)
    monkeypatch.delenv(ct.VAR_ENDERECO, raising=False)
    return caminho


class Resposta:
    def __init__(self, status: int, corpo: Any = None) -> None:
        self.status_code = status
        self._corpo = corpo if corpo is not None else {}

    def json(self) -> Any:
        return self._corpo


def pedir_com(status: int, corpo: Any = None, registro: list[dict[str, Any]] | None = None):
    def pedir(metodo: str, url: str, cabecalho: dict[str, str], corpo_enviado: Any, tempo: float) -> Resposta:
        if registro is not None:
            registro.append({"metodo": metodo, "url": url, "cabecalho": dict(cabecalho)})
        return Resposta(status, corpo)

    return pedir


# ---------------------------------------------------------------------------
# Catálogo
# ---------------------------------------------------------------------------

def test_todo_servico_tem_onde_pegar_o_token_e_variavel_propria():
    assert set(ct.PROVEDORES) == {"notion", "linear", "dropbox", "vercel", "supabase"}
    variaveis = set()
    for identificador, dados in ct.PROVEDORES.items():
        assert dados["onde"], identificador
        assert dados["leitura"], identificador
        assert dados["variavel"].startswith("JARVIS_CONECTOR_"), identificador
        assert dados["variavel"] not in variaveis, identificador
        variaveis.add(dados["variavel"])


def test_o_estado_inicial_diz_zero_de_cinco(env: Path):
    dados = ct.estado()
    assert dados["total"] == 5 and dados["prontos"] == 0
    assert "0 de 5" in dados["resumo"]
    assert all(item["mascara"] == "" for item in dados["tokens"])


# ---------------------------------------------------------------------------
# Gravar
# ---------------------------------------------------------------------------

def test_gravar_mostra_so_a_mascara(env: Path):
    resultado = ct.configurar("notion", TOKEN)
    assert resultado["prontos"] == 1
    item = next(item for item in resultado["tokens"] if item["id"] == "notion")
    assert item["pronto"] is True
    assert TOKEN not in str(resultado)
    assert item["mascara"].startswith("secr")
    assert "…" in item["mascara"]
    assert TOKEN not in item["mascara"]
    assert b"JARVIS_CONECTOR_NOTION=" in env.read_bytes()


def test_token_curto_e_recusado_com_onde_achar(env: Path):
    with pytest.raises(ct.TokenError, match="curto demais"):
        ct.configurar("notion", "abc")
    assert b"JARVIS_CONECTOR_NOTION" not in env.read_bytes()


def test_token_com_espaco_e_recusado(env: Path):
    with pytest.raises(ct.TokenError, match="espaço"):
        ct.configurar("vercel", "abc def ghijklmnop")


def test_servico_desconhecido_nao_grava(env: Path):
    with pytest.raises(ct.TokenError, match="desconhecido"):
        ct.configurar("tiktok", TOKEN)


def test_supabase_exige_o_endereco_do_projeto(env: Path):
    with pytest.raises(ct.TokenError, match="endereço do projeto"):
        ct.configurar("supabase", TOKEN)
    resultado = ct.configurar("supabase", TOKEN, "https://abc123.supabase.co")
    item = next(item for item in resultado["tokens"] if item["id"] == "supabase")
    assert item["endereco"] == "https://abc123.supabase.co"


def test_esquecer_apaga_so_aquele_token(env: Path):
    ct.configurar("notion", TOKEN)
    ct.configurar("vercel", TOKEN)
    ct.esquecer("notion")
    dados = ct.estado()
    prontos = [item["id"] for item in dados["tokens"] if item["pronto"]]
    assert prontos == ["vercel"]
    assert b"JARVIS_DONO=1" in env.read_bytes()


# ---------------------------------------------------------------------------
# Testar (chamada de leitura de verdade, com dublê)
# ---------------------------------------------------------------------------

def test_testar_notion_manda_bearer_e_versao(env: Path):
    ct.configurar("notion", TOKEN)
    registro: list[dict[str, Any]] = []
    prova = ct.testar("notion", pedir=pedir_com(200, {"name": "JARVIS", "bot": {"workspace_name": "Casa"}}, registro))
    assert prova["ok"] is True
    assert prova["perfil"] == "Casa"
    enviado = registro[0]
    assert enviado["url"] == "https://api.notion.com/v1/users/me"
    assert enviado["cabecalho"]["Authorization"] == f"Bearer {TOKEN}"
    assert enviado["cabecalho"]["Notion-Version"] == "2022-06-28"
    assert TOKEN not in str(prova)


def test_testar_linear_nao_usa_bearer(env: Path):
    ct.configurar("linear", TOKEN)
    registro: list[dict[str, Any]] = []
    ct.testar("linear", pedir=pedir_com(200, {"data": {"viewer": {"name": "Victor"}}}, registro))
    enviado = registro[0]
    assert enviado["metodo"] == "POST"
    assert enviado["cabecalho"]["Authorization"] == TOKEN  # sem “Bearer”


def test_testar_supabase_usa_apikey_e_endereco(env: Path):
    ct.configurar("supabase", TOKEN, "https://abc123.supabase.co")
    registro: list[dict[str, Any]] = []
    ct.testar("supabase", pedir=pedir_com(200, {}, registro))
    enviado = registro[0]
    assert enviado["url"] == "https://abc123.supabase.co/rest/v1/"
    assert enviado["cabecalho"]["apikey"] == TOKEN


def test_401_diz_que_o_token_foi_recusado_e_onde_gerar_outro(env: Path):
    ct.configurar("dropbox", TOKEN)
    with pytest.raises(ct.TokenError) as erro:
        ct.testar("dropbox", pedir=pedir_com(401))
    texto = str(erro.value)
    assert "recusou o token" in texto
    assert "dropbox.com/developers/apps" in texto
    assert TOKEN not in texto


def test_404_aponta_endereco_errado(env: Path):
    ct.configurar("vercel", TOKEN)
    with pytest.raises(ct.TokenError, match="404"):
        ct.testar("vercel", pedir=pedir_com(404))


def test_sem_token_nao_chama_rede(env: Path):
    chamou = {"sim": False}

    def pedir(*_args: Any) -> Resposta:
        chamou["sim"] = True
        return Resposta(200)

    with pytest.raises(ct.TokenError, match="ainda não está ligado"):
        ct.testar("notion", pedir=pedir)
    assert chamou["sim"] is False


def test_falha_de_rede_nao_estoura_pilha(env: Path):
    ct.configurar("vercel", TOKEN)

    def explodir(*_args: Any) -> Resposta:
        raise OSError("sem internet")

    with pytest.raises(ct.TokenError, match="internet"):
        ct.testar("vercel", pedir=explodir)


def test_mascara_curta_nao_revela(env: Path):
    assert ct.mascarar("1234567890") == "12…"
    assert ct.mascarar("") == ""
