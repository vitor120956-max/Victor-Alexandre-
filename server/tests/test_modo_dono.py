"""Modo dono: instalar sem digitar token quando o pedido vem da própria máquina.

O que estes testes provam, e o que eles não deixam acontecer:

1. desligado (padrão), nada muda — token continua obrigatório;
2. ligado e pedido da própria máquina, o token é preenchido pelo servidor e o
   plano de instalação pendente é usado sem copiar código;
3. ligado mas pedido de **outra** origem (página de fora) ou de **outra
   máquina**, nada é preenchido — a trava continua de pé;
4. página de outro site não consegue disparar a API (CSRF).
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from server import app as app_mod
from server import sistema
from server.skill_registry import SistemaExecutarInput, build_registry


class _Pedido:
    """Requisição mínima: só o que as guardas leem."""

    def __init__(self, host: str = "127.0.0.1", origem: str = "", host_header: str = "127.0.0.1:8000") -> None:
        self.client = type("Cliente", (), {"host": host})()
        self.headers = {"host": host_header}
        if origem:
            self.headers["origin"] = origem


class _Skill:
    def __init__(self, identificacao: str, modelo: Any) -> None:
        self.id = identificacao
        self.input_model = modelo


# ---------------------------------------------------------------------------
# As guardas, sem HTTP
# ---------------------------------------------------------------------------


def test_enderecos_locais_sao_reconhecidos():
    assert app_mod._veio_da_propria_maquina(_Pedido("127.0.0.1")) is True
    assert app_mod._veio_da_propria_maquina(_Pedido("::1")) is True
    assert app_mod._veio_da_propria_maquina(_Pedido("192.168.0.42")) is False


def test_origem_de_outro_site_e_recusada():
    assert app_mod._mesma_origem(_Pedido()) is True  # sem Origin: requisição local, ex. curl
    assert app_mod._mesma_origem(_Pedido(origem="http://127.0.0.1:8000")) is True
    assert app_mod._mesma_origem(_Pedido(origem="http://localhost:5173")) is True
    assert app_mod._mesma_origem(_Pedido(origem="https://site-malicioso.example")) is False
    assert app_mod._mesma_origem(_Pedido(origem="null")) is False


def test_origem_igual_ao_host_da_api_passa():
    pedido = _Pedido(origem="https://jarvis.exemplo:8443", host_header="jarvis.exemplo")
    assert app_mod._mesma_origem(pedido) is True


def test_propria_maquina_nao_digita_token_por_padrao(monkeypatch):
    """0.62.9: sem variável nenhuma, 127.0.0.1 já não pede token."""
    monkeypatch.delenv("JARVIS_HOST_CONFIAR_LOCAL", raising=False)
    monkeypatch.delenv("JARVIS_HOST_EXIGIR_TOKEN_LOCAL", raising=False)
    skill = _Skill("sistema.executar", SistemaExecutarInput)
    dados, preencheu = app_mod._autorizacao_do_dono(_Pedido(), skill, {})
    assert dados["autorizacao"]
    assert preencheu is True


def test_trava_explicita_devolve_o_token_ate_na_propria_maquina(monkeypatch):
    monkeypatch.delenv("JARVIS_HOST_CONFIAR_LOCAL", raising=False)
    monkeypatch.setenv("JARVIS_HOST_EXIGIR_TOKEN_LOCAL", "1")
    skill = _Skill("sistema.executar", SistemaExecutarInput)
    dados, preencheu = app_mod._autorizacao_do_dono(_Pedido(), skill, {})
    assert dados == {}
    assert preencheu is False


def test_pedido_de_outra_maquina_nunca_e_preenchido(monkeypatch):
    monkeypatch.delenv("JARVIS_HOST_CONFIAR_LOCAL", raising=False)
    monkeypatch.delenv("JARVIS_HOST_EXIGIR_TOKEN_LOCAL", raising=False)
    skill = _Skill("sistema.executar", SistemaExecutarInput)
    dados, preencheu = app_mod._autorizacao_do_dono(_Pedido("192.168.0.42"), skill, {})
    assert dados == {}
    assert preencheu is False


def test_modo_ligado_preenche_o_token_na_propria_maquina(monkeypatch):
    monkeypatch.setenv("JARVIS_HOST_CONFIAR_LOCAL", "1")
    skill = _Skill("sistema.instalar", type("Entrada", (object,), {}))
    # skill sem modelo Pydantic não arrisca nada: só o que tem campo `autorizacao`
    dados, preencheu = app_mod._autorizacao_do_dono(_Pedido(), skill, {})
    assert dados == {}
    assert preencheu is False


def test_modo_ligado_preenche_token_em_skill_com_campo(monkeypatch):
    from server.skill_registry import SistemaInstalarInput

    monkeypatch.setenv("JARVIS_HOST_CONFIAR_LOCAL", "1")
    dados, preencheu = app_mod._autorizacao_do_dono(
        _Pedido(), _Skill("sistema.instalar", SistemaInstalarInput), {"arquivo": "a.exe"}
    )
    assert preencheu is True
    assert dados["autorizacao"] == sistema.token_host()
    assert dados["arquivo"] == "a.exe"


def test_modo_ligado_nao_preenche_para_outra_maquina(monkeypatch):
    from server.skill_registry import SistemaInstalarInput

    monkeypatch.setenv("JARVIS_HOST_CONFIAR_LOCAL", "1")
    dados, preencheu = app_mod._autorizacao_do_dono(
        _Pedido("192.168.0.42"), _Skill("sistema.instalar", SistemaInstalarInput), {}
    )
    assert dados == {}
    assert preencheu is False


def test_modo_ligado_respeita_o_token_certo_digitado(monkeypatch):
    """Token válido e explícito continua sendo usado como veio."""
    from server.skill_registry import SistemaInstalarInput
    from server.sistema import token_host

    monkeypatch.setenv("JARVIS_HOST_CONFIAR_LOCAL", "1")
    certo = token_host()
    dados, preencheu = app_mod._autorizacao_do_dono(
        _Pedido(), _Skill("sistema.instalar", SistemaInstalarInput), {"autorizacao": certo}
    )
    assert dados["autorizacao"] == certo
    assert preencheu is False


def test_modo_ligado_corrige_token_torto_na_propria_maquina(monkeypatch):
    """O bug de 0.62.9: o chat mandava "sim, pode" no campo do token."""
    from server.skill_registry import SistemaInstalarInput
    from server.sistema import token_host

    monkeypatch.setenv("JARVIS_HOST_CONFIAR_LOCAL", "1")
    certo = token_host()
    for torto in ("sim, pode", "não", "baixa o adb e o scrcpy", "1234"):
        dados, preencheu = app_mod._autorizacao_do_dono(
            _Pedido(), _Skill("sistema.instalar", SistemaInstalarInput), {"autorizacao": torto}
        )
        assert dados["autorizacao"] == certo, torto
        assert preencheu is True


def test_modo_ligado_nao_corrige_para_outra_maquina(monkeypatch):
    from server.skill_registry import SistemaInstalarInput

    monkeypatch.setenv("JARVIS_HOST_CONFIAR_LOCAL", "1")
    dados, preencheu = app_mod._autorizacao_do_dono(
        _Pedido("192.168.0.42"),
        _Skill("sistema.instalar", SistemaInstalarInput),
        {"autorizacao": "sim, pode"},
    )
    assert dados["autorizacao"] == "sim, pode"
    assert preencheu is False


def test_modo_ligado_usa_o_plano_pendente_unico(monkeypatch):
    monkeypatch.setenv("JARVIS_HOST_CONFIAR_LOCAL", "1")
    monkeypatch.setattr(
        sistema,
        "planos_pendentes",
        lambda: [{"confirmacao": "ab12cd34", "arquivo": "setup.exe", "expira_em": 120}],
    )
    dados, preencheu = app_mod._autorizacao_do_dono(
        _Pedido(), _Skill("sistema.executar", SistemaExecutarInput), {}
    )
    assert preencheu is True
    assert dados["confirmacao"] == "ab12cd34"
    assert dados["autorizacao"] == sistema.token_host()


def test_modo_ligado_com_dois_planos_nao_escolhe_por_voce(monkeypatch):
    monkeypatch.setenv("JARVIS_HOST_CONFIAR_LOCAL", "1")
    monkeypatch.setattr(
        sistema,
        "planos_pendentes",
        lambda: [
            {"confirmacao": "aaaa1111", "expira_em": 100},
            {"confirmacao": "bbbb2222", "expira_em": 200},
        ],
    )
    dados, _ = app_mod._autorizacao_do_dono(_Pedido(), _Skill("sistema.executar", SistemaExecutarInput), {})
    assert "confirmacao" not in dados


# ---------------------------------------------------------------------------
# Planos pendentes
# ---------------------------------------------------------------------------


def test_planos_pendentes_lista_e_expira(monkeypatch):
    monkeypatch.setattr(sistema, "_CONFIRMACAO", {})
    assert sistema.planos_pendentes() == []
    sistema._CONFIRMACAO["vivo"] = {"expira": 9_999_999_999, "arquivo": "a.exe", "tipo": "exe"}
    sistema._CONFIRMACAO["morto"] = {"expira": 1, "arquivo": "b.exe", "tipo": "exe"}
    pendentes = sistema.planos_pendentes()
    assert [item["confirmacao"] for item in pendentes] == ["vivo"]
    assert "morto" not in sistema._CONFIRMACAO  # expirado é limpo na leitura


# ---------------------------------------------------------------------------
# Pela API de verdade
# ---------------------------------------------------------------------------


@pytest.fixture()
def cliente(tmp_path, monkeypatch):
    monkeypatch.setenv("JARVIS_HOST_TOKEN_SILENCIOSO", "1")
    registry = build_registry(tmp_path / "files")
    aplicacao = app_mod.create_app(registry=registry, agente_root=tmp_path)
    with TestClient(aplicacao) as test_client:
        yield test_client


def test_api_com_trava_local_continua_exigindo_token(cliente: TestClient, monkeypatch):
    monkeypatch.setenv("JARVIS_HOST_EXIGIR_TOKEN_LOCAL", "1")
    resposta = cliente.post(
        "/api/skills/sistema.executar/execute",
        json={"parameters": {"confirmacao": "abcd1234"}, "confirmed": True},
    )
    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["ok"] is False
    assert "token" in corpo["error"]["message"].lower()


def test_api_na_propria_maquina_nao_reclama_do_token(cliente: TestClient, monkeypatch):
    monkeypatch.delenv("JARVIS_HOST_EXIGIR_TOKEN_LOCAL", raising=False)
    monkeypatch.delenv("JARVIS_HOST_CONFIAR_LOCAL", raising=False)
    resposta = cliente.post(
        "/api/skills/sistema.executar/execute",
        json={"parameters": {"confirmacao": "abcd1234"}, "confirmed": True},
    )
    corpo = resposta.json()
    # passou da trava do token e parou na próxima trava (rede) — o esperado
    assert corpo["ok"] is False
    assert "token" not in corpo["error"]["message"].lower()
    assert "rede desligada" in corpo["error"]["message"].lower()


def test_api_com_modo_dono_nao_reclama_do_token(cliente: TestClient, monkeypatch):
    monkeypatch.setenv("JARVIS_HOST_CONFIAR_LOCAL", "1")
    monkeypatch.setenv("JARVIS_HOST_REDE", "1")
    monkeypatch.setenv("JARVIS_HOST_INSTALAR", "1")
    resposta = cliente.post(
        "/api/skills/sistema.executar/execute",
        json={"parameters": {"confirmacao": "abcd1234"}, "confirmed": True},
    )
    corpo = resposta.json()
    # passa da trava do token e para na confirmação desconhecida — o esperado
    assert corpo["ok"] is False
    assert "token" not in corpo["error"]["message"].lower()
    assert "confirma" in corpo["error"]["message"].lower()


def test_api_recusa_origem_de_fora(cliente: TestClient):
    resposta = cliente.post(
        "/api/skills/sistema.executar/execute",
        json={"parameters": {}, "confirmed": True},
        headers={"origin": "https://site-malicioso.example"},
    )
    assert resposta.status_code == 403
    assert resposta.json()["error"]["code"] == "ORIGEM_RECUSADA"


def test_api_aceita_origem_local(cliente: TestClient):
    resposta = cliente.post(
        "/api/skills/sistema.executar/execute",
        json={"parameters": {}, "confirmed": True},
        headers={"origin": "http://127.0.0.1:8000"},
    )
    assert resposta.status_code == 200


def test_health_responde_por_origem_quem_pode_ficar_sem_token(cliente: TestClient, monkeypatch):
    monkeypatch.delenv("JARVIS_HOST_CONFIAR_LOCAL", raising=False)
    monkeypatch.delenv("JARVIS_HOST_EXIGIR_TOKEN_LOCAL", raising=False)
    corpo = cliente.get("/api/health").json()
    assert corpo["confiarLocal"] is True  # o test client fala de 127.0.0.1
    assert corpo["confiarLocalPorVariavel"] is False
    assert corpo["exigirTokenLocal"] is False

    monkeypatch.setenv("JARVIS_HOST_EXIGIR_TOKEN_LOCAL", "1")
    assert cliente.get("/api/health").json()["confiarLocal"] is False


def test_arquivo_de_token_fica_fora_do_git():
    raiz = Path(__file__).resolve().parents[2]
    ignorados = (raiz / ".gitignore").read_text(encoding="utf-8")
    assert "storage/" in ignorados


# ---------------------------------------------------------------------------
# A rota que alimenta o botão "Executar este plano" (0.60.3)
# ---------------------------------------------------------------------------


def _plano_falso(confirmacao: str = "ab12cd34") -> dict[str, Any]:
    return {
        "confirmacao": confirmacao,
        "acao": "instalar",
        "arquivo": "setup.exe",
        "rotulo": "setup.exe",
        "tipo": "exe",
        "comando": "setup.exe /S",
        "sha256": "a" * 64,
        "expira_em": 300,
    }


def test_planos_traz_comando_e_hash(monkeypatch):
    monkeypatch.setattr(sistema, "_CONFIRMACAO", {})
    monkeypatch.setattr(
        sistema,
        "_CONFIRMACAO",
        {"ab12cd34": {"expira": 9_999_999_999, "comando": ["setup.exe", "/S"], "sha256": "b" * 64, "rotulo": "setup.exe"}},
    )
    pendentes = sistema.planos_pendentes()
    assert pendentes[0]["comando"] == "setup.exe /S"
    assert pendentes[0]["sha256"] == "b" * 64


def test_rota_planos_devolve_o_codigo_para_a_propria_maquina(cliente: TestClient, monkeypatch):
    monkeypatch.setattr(sistema, "_CONFIRMACAO", {"ab12cd34": {"expira": 9_999_999_999, "rotulo": "setup.exe"}})
    corpo = cliente.get("/api/host/planos").json()
    assert corpo["ok"] is True
    assert corpo["local"] is True
    assert corpo["total"] == 1
    assert corpo["planos"][0]["confirmacao"] == "ab12cd34"


def test_rota_planos_nao_vaza_o_codigo_para_fora(monkeypatch):
    from server import app as app_mod2

    monkeypatch.setattr(sistema, "_CONFIRMACAO", {"ab12cd34": {"expira": 9_999_999_999}})
    monkeypatch.setattr(app_mod2, "_veio_da_propria_maquina", lambda _pedido: False)
    aplicacao = app_mod2.create_app(registry=build_registry(Path(tempfile.mkdtemp())))
    with TestClient(aplicacao) as test_client:
        corpo = test_client.get("/api/host/planos").json()
    assert corpo["local"] is False
    assert corpo["total"] == 1
    assert "confirmacao" not in corpo["planos"][0]


def test_rota_planos_sem_plano(cliente: TestClient, monkeypatch):
    monkeypatch.setattr(sistema, "_CONFIRMACAO", {})
    corpo = cliente.get("/api/host/planos").json()
    assert corpo["planos"] == []
    assert corpo["total"] == 0


def test_rota_planos_diz_se_a_instalacao_esta_ligada(cliente: TestClient, monkeypatch):
    monkeypatch.setenv("JARVIS_HOST_INSTALAR", "0")
    assert cliente.get("/api/host/planos").json()["instalar"] is False
    monkeypatch.setenv("JARVIS_HOST_INSTALAR", "1")
    assert cliente.get("/api/host/planos").json()["instalar"] is True


# --- tokens: acento nao pode derrubar a requisicao ---------------------------

def test_comparar_token_com_acento_nao_estoura():
    from server import tokens

    assert tokens.iguais("não", "abc") is False
    assert tokens.iguais("ação", "ação") is True
    assert tokens.iguais("", "") is True
    assert tokens.iguais(None, "abc") is False


def test_explicar_distingue_nao_token_de_token_errado():
    from server import tokens

    texto = tokens.explicar("não, pode")
    assert "não é um token" in texto
    assert "acento" in texto

    assert "inválido" in tokens.explicar("abcdefgh")

    vazio = tokens.explicar("", automatico_local=True)
    assert "não veio da própria máquina" in vazio
    assert "storage/host-token.txt" in vazio

    travado = tokens.explicar("", trava_local=True)
    assert "JARVIS_HOST_EXIGIR_TOKEN_LOCAL" in travado


def test_explicar_modo_dono_ligado_de_outra_maquina():
    from server import tokens

    texto = tokens.explicar("", modo_dono=True, da_propria_maquina=False)
    assert "própria máquina" in texto or "da própria máquina" in texto


def test_token_gerado_parece_token():
    import secrets

    from server import tokens

    assert tokens.parece_token(secrets.token_urlsafe(24))
    assert not tokens.parece_token("sim")
    assert not tokens.parece_token("baixa o adb")
