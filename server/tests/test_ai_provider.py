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
