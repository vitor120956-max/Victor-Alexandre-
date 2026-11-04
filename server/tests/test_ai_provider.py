from __future__ import annotations

import asyncio
from typing import Any

import pytest

from server.ai import AIRequest, AIUnavailable, OpenAICompatibleProvider


class FakeResponse:
    def __init__(self, status: int = 200, headers: dict[str, str] | None = None) -> None:
        self.status_code = status
        self.headers = headers or {}

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


# ------------------------------------------------- três cérebros (troca de chave)

class FakeMulti:
    """Responde conforme a chave: 429 na primeira, 200 na segunda, 401 na terceira.

    O registro de chamadas é da classe, não da instância: `_pedir` abre um
    `AsyncClient` por tentativa, então cada tentativa seria uma instância nova —
    e o teste perderia justamente a troca de chave que quer provar.
    """

    respostas: dict[str, int] = {}
    chamadas: list[str] = []

    def __init__(self, respostas: dict[str, int] | None = None, **_kwargs: Any) -> None:
        if respostas is not None:
            FakeMulti.respostas = respostas

    @classmethod
    def zerar(cls, respostas: dict[str, int]) -> None:
        cls.respostas = respostas
        cls.chamadas = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args: Any) -> None:
        return None

    async def post(self, url: str, **kwargs: Any) -> "FakeDyn":
        chave = kwargs["headers"].get("Authorization", "").removeprefix("Bearer ")
        FakeMulti.chamadas.append(chave)
        return FakeDyn(FakeMulti.respostas.get(chave, 200))


class FakeDyn(FakeResponse):
    def __init__(self, status: int) -> None:
        super().__init__(status)


def test_separar_chaves_aceita_virgula_quebra_de_linha_e_nao_repete():
    from server.ai import separar_chaves

    assert separar_chaves("a,b;c|d\ne") == ["a", "b", "c", "d", "e"]
    assert separar_chaves(" gsk_1 , gsk_1 , gsk_2 ") == ["gsk_1", "gsk_2"]
    assert separar_chaves("") == []


def test_troca_de_chave_quando_a_primeira_estoura_a_cota(monkeypatch: pytest.MonkeyPatch):
    """Cota estourada na chave 1 → tenta a 2 e responde. É o pedido dos 3 cérebros."""
    monkeypatch.setenv("JARVIS_AI_API_KEY", "chave-1,chave-2,chave-3")
    monkeypatch.setenv("JARVIS_AI_BASE_URL", "https://provider.example/v1")
    monkeypatch.setenv("JARVIS_AI_MODEL", "modelo-teste")
    FakeMulti.zerar({"chave-1": 429, "chave-2": 200, "chave-3": 200})
    monkeypatch.setattr("server.ai.httpx.AsyncClient", FakeMulti)
    provider = OpenAICompatibleProvider()
    assert asyncio.run(provider.generate(AIRequest(message="Olá"))) == "Resposta gerada pelo provedor."
    assert FakeMulti.chamadas == ["chave-1", "chave-2"]
    assert provider.status()["keys"] == 3
    assert provider.status()["key_in_use"] == 2


def test_a_proxima_chamada_comeca_na_chave_que_funcionou(monkeypatch: pytest.MonkeyPatch):
    """Não gastar um pedido por resposta numa chave que já se sabe estourada."""
    monkeypatch.setenv("JARVIS_AI_API_KEY", "chave-1,chave-2")
    monkeypatch.setenv("JARVIS_AI_BASE_URL", "https://provider.example/v1")
    monkeypatch.setenv("JARVIS_AI_MODEL", "modelo-teste")
    FakeMulti.zerar({"chave-1": 429, "chave-2": 200})
    monkeypatch.setattr("server.ai.httpx.AsyncClient", FakeMulti)
    provider = OpenAICompatibleProvider()
    asyncio.run(provider.generate(AIRequest(message="Primeira")))
    asyncio.run(provider.generate(AIRequest(message="Segunda")))
    assert FakeMulti.chamadas == ["chave-1", "chave-2", "chave-2"]


def test_se_todas_forem_recusadas_a_frase_diz_quantas_e_o_que_fazer(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("JARVIS_AI_API_KEY", "chave-1,chave-2,chave-3")
    monkeypatch.setenv("JARVIS_AI_BASE_URL", "https://provider.example/v1")
    FakeMulti.zerar({"chave-1": 401, "chave-2": 401, "chave-3": 401})
    monkeypatch.setattr("server.ai.httpx.AsyncClient", FakeMulti)
    provider = OpenAICompatibleProvider()
    with pytest.raises(AIUnavailable) as erro:
        asyncio.run(provider.generate(AIRequest(message="Olá")))
    texto = str(erro.value)
    assert "3 chaves" in texto and "401" in texto
    assert "chave-1" not in texto and "chave-2" not in texto and "chave-3" not in texto
    assert "console.groq.com/keys" in texto


def test_todas_no_limite_pede_espera_ou_mais_uma_chave(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("JARVIS_AI_API_KEY", "chave-1,chave-2")
    monkeypatch.setenv("JARVIS_AI_BASE_URL", "https://provider.example/v1")
    FakeMulti.zerar({"chave-1": 429, "chave-2": 429})
    monkeypatch.setattr("server.ai.httpx.AsyncClient", FakeMulti)
    provider = OpenAICompatibleProvider()
    with pytest.raises(AIUnavailable, match="429"):
        asyncio.run(provider.generate(AIRequest(message="Olá")))


def test_erro_que_nao_e_de_chave_nao_fica_trocando(monkeypatch: pytest.MonkeyPatch):
    """404 é modelo errado: tentar outra chave só perderia tempo."""
    monkeypatch.setenv("JARVIS_AI_API_KEY", "chave-1,chave-2")
    monkeypatch.setenv("JARVIS_AI_BASE_URL", "https://provider.example/v1")
    FakeMulti.zerar({"chave-1": 404, "chave-2": 404})
    monkeypatch.setattr("server.ai.httpx.AsyncClient", FakeMulti)
    provider = OpenAICompatibleProvider()
    with pytest.raises(AIUnavailable, match="404"):
        asyncio.run(provider.generate(AIRequest(message="Olá")))
    assert FakeMulti.chamadas == ["chave-1"]


def test_status_nao_revela_a_chave(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("JARVIS_AI_API_KEY", "gsk_segredo_1,gsk_segredo_2")
    monkeypatch.setenv("JARVIS_AI_BASE_URL", "https://provider.example/v1")
    provider = OpenAICompatibleProvider()
    texto = str(provider.status())
    assert "gsk_segredo" not in texto
    assert provider.status()["keys"] == 2


# ------------------------------------- cota: avisar quando acaba e quando acabou
# O pedido: *“dá para o JARVIS avisar quando estiver acabando ou quando acabar
# totalmente as APIs?”*. O aviso só vale se for medido: o que entra aqui é o
# código HTTP e o cabeçalho `x-ratelimit-*` de cada tentativa.

def _provedor(monkeypatch: pytest.MonkeyPatch, chaves: str) -> OpenAICompatibleProvider:
    monkeypatch.setenv("JARVIS_AI_API_KEY", chaves)
    monkeypatch.setenv("JARVIS_AI_BASE_URL", "https://provider.example/v1")
    monkeypatch.setenv("JARVIS_AI_MODEL", "modelo-teste")
    return OpenAICompatibleProvider()


def test_uma_chave_no_limite_avisa_que_esta_acabando(monkeypatch: pytest.MonkeyPatch):
    FakeMulti.zerar({"chave-1": 429, "chave-2": 200, "chave-3": 200})
    monkeypatch.setattr("server.ai.httpx.AsyncClient", FakeMulti)
    provedor = _provedor(monkeypatch, "chave-1,chave-2,chave-3")
    asyncio.run(provedor.generate(AIRequest(message="Olá")))

    saude = provedor.status()["saude"]
    assert saude["situacao"] == "apertando"
    assert saude["no_limite"] == [1]
    assert saude["disponiveis"] == 2
    assert "2 de 3" in saude["aviso"]
    assert "skills locais" in saude["aviso"]


def test_todas_caidas_viram_aviso_de_que_acabou(monkeypatch: pytest.MonkeyPatch):
    FakeMulti.zerar({"chave-1": 429, "chave-2": 429})
    monkeypatch.setattr("server.ai.httpx.AsyncClient", FakeMulti)
    provedor = _provedor(monkeypatch, "chave-1,chave-2")
    with pytest.raises(AIUnavailable):
        asyncio.run(provedor.generate(AIRequest(message="Olá")))

    saude = provedor.status()["saude"]
    assert saude["situacao"] == "esgotado"
    assert saude["disponiveis"] == 0
    assert "parou" in saude["aviso"] or "pararam" in saude["aviso"]
    assert "skills locais" in saude["aviso"]


def test_chave_recusada_401_aparece_como_recusada(monkeypatch: pytest.MonkeyPatch):
    FakeMulti.zerar({"chave-1": 401, "chave-2": 200})
    monkeypatch.setattr("server.ai.httpx.AsyncClient", FakeMulti)
    provedor = _provedor(monkeypatch, "chave-1,chave-2")
    asyncio.run(provedor.generate(AIRequest(message="Olá")))

    saude = provedor.status()["saude"]
    assert saude["recusadas"] == [1]
    assert saude["chaves"][0]["estado"] == "recusada"
    assert saude["chaves"][0]["codigo"] == 401
    assert "troque no cartão" in saude["aviso"]


def test_os_cabecalhos_dizem_quanto_resta_no_minuto(monkeypatch: pytest.MonkeyPatch):
    class ComCota(FakeMulti):
        async def post(self, url: str, **kwargs: Any) -> FakeResponse:
            return FakeResponse(200, {
                "x-ratelimit-remaining-requests": "2",
                "x-ratelimit-limit-requests": "20",
                "x-ratelimit-remaining-tokens": "52000",
                "x-ratelimit-limit-tokens": "6000",
            })

    monkeypatch.setattr("server.ai.httpx.AsyncClient", ComCota)
    provedor = _provedor(monkeypatch, "chave-1")
    asyncio.run(provedor.generate(AIRequest(message="Olá")))

    saude = provedor.status()["saude"]
    chave = saude["chaves"][0]
    assert chave["estado"] == "apertando"
    assert chave["aperto"] == "pedidos"
    assert chave["restam_pedidos"] == 2 and chave["limite_pedidos"] == 20
    assert saude["situacao"] == "apertando"
    assert "2 de 20" in saude["aviso"]


def test_retry_after_do_429_aparece_na_frase(monkeypatch: pytest.MonkeyPatch):
    class ComEspera(FakeMulti):
        async def post(self, url: str, **kwargs: Any) -> FakeResponse:
            return FakeResponse(429, {"retry-after": "12"})

    monkeypatch.setattr("server.ai.httpx.AsyncClient", ComEspera)
    provedor = _provedor(monkeypatch, "chave-1,chave-2")
    with pytest.raises(AIUnavailable):
        asyncio.run(provedor.generate(AIRequest(message="Olá")))
    saude = provedor.status()["saude"]
    assert saude["chaves"][0]["retry_after"] == 12.0
    assert "12s" in saude["aviso"]


def test_teste_das_chaves_limpa_o_aviso_de_esgotado(monkeypatch: pytest.MonkeyPatch):
    """As três responderem no botão Testar não pode continuar dizendo “acabou”."""
    provedor = _provedor(monkeypatch, "chave-1,chave-2")
    provedor._anotar_recusa(0, 429)
    provedor._anotar_recusa(1, 429)
    assert provedor.saude_resumo()["situacao"] == "esgotado"

    provedor.anotar_teste([
        {"indice": 1, "ok": True, "codigo": 200},
        {"indice": 2, "ok": True, "codigo": 200},
    ])
    assert provedor.saude_resumo()["situacao"] == "ok"


def test_recusa_de_uma_hora_atras_deixa_de_valer(monkeypatch: pytest.MonkeyPatch):
    from datetime import datetime, timedelta, timezone

    provedor = _provedor(monkeypatch, "chave-1")
    antiga = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat(timespec="seconds")
    provedor._recusas[0] = {"codigo": 429, "em": antiga, "retry_after": None}
    assert provedor.saude_resumo()["situacao"] == "ok"


def test_recusa_401_nao_vence_com_o_tempo(monkeypatch: pytest.MonkeyPatch):
    """Chave inválida continua inválida: só trocar a chave resolve."""
    from datetime import datetime, timedelta, timezone

    provedor = _provedor(monkeypatch, "chave-1")
    antiga = (datetime.now(timezone.utc) - timedelta(days=3)).isoformat(timespec="seconds")
    provedor._recusas[0] = {"codigo": 401, "em": antiga, "retry_after": None}
    assert provedor.saude_resumo()["situacao"] == "esgotado"


def test_modelo_local_nao_inventa_cota(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("JARVIS_AI_API_KEY", raising=False)
    monkeypatch.setenv("JARVIS_AI_BASE_URL", "http://127.0.0.1:8080/v1")
    monkeypatch.setenv("JARVIS_AI_MODEL", "modelo-local")
    saude = OpenAICompatibleProvider().saude_resumo()
    assert saude["situacao"] == "local"
    assert saude["aviso"] is None


def test_sem_chave_nao_inventa_aviso(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("JARVIS_AI_API_KEY", raising=False)
    monkeypatch.setenv("JARVIS_AI_BASE_URL", "https://provider.example/v1")
    monkeypatch.setenv("JARVIS_AI_MODEL", "modelo-teste")
    saude = OpenAICompatibleProvider().saude_resumo()
    assert saude["situacao"] == "sem_chave"
    assert saude["aviso"] is None


def test_o_diario_da_cota_nunca_mostra_a_chave(monkeypatch: pytest.MonkeyPatch):
    provedor = _provedor(monkeypatch, "gsk_segredo_um,gsk_segredo_dois")
    provedor._anotar_recusa(0, 429, 5.0)
    provedor._anotar_recusa(1, 401)
    texto = str(provedor.status())
    assert "gsk_segredo" not in texto
