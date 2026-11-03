from __future__ import annotations

import asyncio
from typing import Any

import pytest

from server.ai import AIRequest, AIUnavailable, OpenAICompatibleProvider


class FakeResponse:
    def __init__(self, status: int = 200) -> None:
        self.status_code = status

    def json(self) -> dict[str, Any]:
        return {"choices": [{"message": {"content": "Resposta gerada pelo provedor."}}]}


class FakeClient:
    last: "FakeClient | None" = None

    def __init__(self, status: int = 200, **_kwargs: Any) -> None:
        self.status = status
        self.calls: list[dict[str, Any]] = []
        FakeClient.last = self

    async def __aenter__(self):  # type: ignore[no-untyped-def]
        return self

    async def __aexit__(self, *_args: Any) -> None:
        return None

    async def post(self, url: str, **kwargs: Any) -> FakeResponse:
        self.calls.append({"url": url, **kwargs})
        return FakeResponse(self.status)


def test_openai_compatible_payload_and_response(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("JARVIS_AI_API_KEY", "test-key-not-a-real-secret")
    monkeypatch.setenv("JARVIS_AI_BASE_URL", "https://provider.example/v1")
    monkeypatch.setenv("JARVIS_AI_MODEL", "modelo-teste")
    monkeypatch.setattr("server.ai.httpx.AsyncClient", FakeClient)
    provider = OpenAICompatibleProvider()
    request = AIRequest(message="Pergunta atual", history=[{"role": "jarvis", "content": "Resposta anterior"}])
    content = asyncio.run(provider.generate(request))
    assert content == "Resposta gerada pelo provedor."
    call = FakeClient.last.calls[0]  # type: ignore[union-attr]
    assert call["url"] == "https://provider.example/v1/chat/completions"
    assert call["json"]["model"] == "modelo-teste"
    assert call["json"]["messages"][-1] == {"role": "user", "content": "Pergunta atual"}
    assert call["json"]["messages"][1]["role"] == "assistant"
    assert call["headers"]["Authorization"] == "Bearer test-key-not-a-real-secret"


def test_provider_errors_do_not_include_response_or_key(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("JARVIS_AI_API_KEY", "test-key-not-a-real-secret")
    monkeypatch.setattr("server.ai.httpx.AsyncClient", lambda **kwargs: FakeClient(status=401, **kwargs))
    provider = OpenAICompatibleProvider()
    with pytest.raises(AIUnavailable) as error:
        asyncio.run(provider.generate(AIRequest(message="Olá")))
    assert "401" in str(error.value)
    assert "test-key" not in str(error.value)
    assert "choices" not in str(error.value)


# ------------------------------------------------- modelo local (offline)

def test_modelo_local_sem_chave_fica_configurado(monkeypatch: pytest.MonkeyPatch):
    """Pendrive sem conta: llama.cpp em 127.0.0.1 não tem chave — e funciona."""
    monkeypatch.delenv("JARVIS_AI_API_KEY", raising=False)
    monkeypatch.delenv("JARVIS_AI_PROVIDER", raising=False)
    monkeypatch.setenv("JARVIS_AI_BASE_URL", "http://127.0.0.1:8080/v1")
    monkeypatch.setenv("JARVIS_AI_MODEL", "qwen2.5-1.5b-instruct-q4_k_m.gguf")
    provedor = OpenAICompatibleProvider()
    assert provedor.configured is True
    status = provedor.status()
    assert status["local"] is True
    assert status["external"] is False
    assert "local" in status["provider"].lower()


def test_servidor_remoto_sem_chave_continua_desconfigurado(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("JARVIS_AI_API_KEY", raising=False)
    monkeypatch.setenv("JARVIS_AI_BASE_URL", "https://api.groq.com/openai/v1")
    monkeypatch.setenv("JARVIS_AI_MODEL", "llama-3.3-70b-versatile")
    provedor = OpenAICompatibleProvider()
    assert provedor.configured is False
    assert provedor.status()["local"] is False


def test_sem_modelo_nao_adianta_ser_local(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("JARVIS_AI_API_KEY", raising=False)
    monkeypatch.setenv("JARVIS_AI_BASE_URL", "http://localhost:8080/v1")
    monkeypatch.setenv("JARVIS_AI_MODEL", "")
    assert OpenAICompatibleProvider().configured is False


def test_local_nao_manda_cabecalho_de_autorizacao_vazio(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("JARVIS_AI_API_KEY", raising=False)
    monkeypatch.setenv("JARVIS_AI_BASE_URL", "http://127.0.0.1:8080/v1")
    monkeypatch.setenv("JARVIS_AI_MODEL", "modelo-local")
    monkeypatch.setattr("server.ai.httpx.AsyncClient", FakeClient)

    provedor = OpenAICompatibleProvider()
    asyncio.run(provedor.generate(AIRequest(message="oi")))
    assert FakeClient.last is not None
    cabecalhos = FakeClient.last.calls[0]["headers"]
    assert "Authorization" not in cabecalhos
    assert cabecalhos["Content-Type"] == "application/json"


def test_remoto_com_chave_manda_autorizacao(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("JARVIS_AI_API_KEY", "gsk_de_teste")
    monkeypatch.setenv("JARVIS_AI_BASE_URL", "https://api.groq.com/openai/v1")
    monkeypatch.setenv("JARVIS_AI_MODEL", "llama-3.3-70b-versatile")
    monkeypatch.setattr("server.ai.httpx.AsyncClient", FakeClient)

    provedor = OpenAICompatibleProvider()
    asyncio.run(provedor.generate(AIRequest(message="oi")))
    assert FakeClient.last is not None
    assert FakeClient.last.calls[0]["headers"]["Authorization"] == "Bearer gsk_de_teste"


@pytest.mark.parametrize(
    "url, esperado",
    [
        ("http://127.0.0.1:8080/v1", True),
        ("http://localhost:11434/v1", True),
        ("http://[::1]:8080/v1", True),
        ("https://127.0.0.1:8080/v1", True),
        ("https://api.groq.com/openai/v1", False),
        ("http://192.168.0.10:8080/v1", False),  # outro PC da rede não é "local"
        ("nao e url", False),
    ],
)
def test_e_local_reconhece_so_o_endereco_da_propria_maquina(url: str, esperado: bool):
    from server.ai import e_local

    assert e_local(url) is esperado
