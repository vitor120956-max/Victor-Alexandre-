from __future__ import annotations

import asyncio
from pathlib import Path
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


# ------------------------------------------------- 400 sem corpo reconhecível
#
# 0.91.5, no PC do dono: o passo 3 parou com “o provedor de IA respondeu com
# HTTP 400” — sem causa, sem o que fazer. O corpo que o provedor mandou não
# casava com `error.message` e era descartado em silêncio.


class CorpoCruResponse(FakeResponse):
    def __init__(self, status: int, texto: str) -> None:
        super().__init__(status=status)
        self.text = texto

    def json(self):  # type: ignore[override]
        raise ValueError("não é JSON")


class CorpoDictResponse(FakeResponse):
    def __init__(self, status: int, corpo: dict[str, Any]) -> None:
        super().__init__(status=status)
        self._corpo = corpo
        self.text = str(corpo)

    def json(self):  # type: ignore[override]
        return self._corpo


class ClienteQueResponde:
    def __init__(self, resposta) -> None:  # type: ignore[no-untyped-def]
        self.resposta = resposta
        self.chamadas = 0

    def __call__(self, **_kwargs: Any) -> "ClienteQueResponde":
        return self

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args: Any) -> None:
        return None

    async def post(self, _url: str, **_kwargs: Any):
        self.chamadas += 1
        return self.resposta


def _provedor_com_corpo(monkeypatch: pytest.MonkeyPatch, resposta) -> OpenAICompatibleProvider:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("JARVIS_AI_API_KEY", "test-key-not-a-real-secret")
    monkeypatch.setenv("JARVIS_AI_BASE_URL", "https://provider.example/v1")
    monkeypatch.setenv("JARVIS_AI_MODEL", "modelo-teste")
    monkeypatch.setattr("server.ai.httpx.AsyncClient", ClienteQueResponde(resposta))
    return OpenAICompatibleProvider()


def test_corpo_que_nao_e_json_aparece_na_mensagem(monkeypatch: pytest.MonkeyPatch):
    """Antes devolvia string vazia e a resposta ficava sem causa nenhuma."""
    provedor = _provedor_com_corpo(monkeypatch, CorpoCruResponse(400, "<html>Bad Request: modelo invalido</html>"))

    with pytest.raises(AIUnavailable) as erro:
        asyncio.run(provedor.generate(AIRequest(message="oi")))

    texto = str(erro.value)
    assert "HTTP 400" in texto
    assert "modelo invalido" in texto
    assert "conferir-ia.py" in texto


def test_corpo_com_detail_em_vez_de_error_message(monkeypatch: pytest.MonkeyPatch):
    """Servidor no estilo FastAPI (modelo local) usa `detail`, não `error.message`."""
    provedor = _provedor_com_corpo(monkeypatch, CorpoDictResponse(400, {"detail": "context length exceeded: 9000 > 8192"}))

    with pytest.raises(AIUnavailable) as erro:
        asyncio.run(provedor.generate(AIRequest(message="oi")))

    texto = str(erro.value)
    assert "context length exceeded" in texto


def test_o_400_diz_o_que_fazer_e_nao_culpa_a_chave(monkeypatch: pytest.MonkeyPatch):
    provedor = _provedor_com_corpo(monkeypatch, CorpoDictResponse(400, {"error": {"message": "model_not_found"}}))

    with pytest.raises(AIUnavailable) as erro:
        asyncio.run(provedor.generate(AIRequest(message="oi")))

    texto = str(erro.value)
    assert "não é a chave nem a cota" in texto
    assert "model_not_found" in texto


def test_a_mensagem_do_provedor_nunca_mostra_a_chave(monkeypatch: pytest.MonkeyPatch):
    provedor = _provedor_com_corpo(
        monkeypatch,
        CorpoCruResponse(400, "chave invalida: gsk_ABCDEFGHIJKLMNOPQRSTUVWXYZ123456 pedido ruim"),
    )

    with pytest.raises(AIUnavailable) as erro:
        asyncio.run(provedor.generate(AIRequest(message="oi")))

    assert "gsk_ABCDEFGHIJKLMNOPQRSTUVWXYZ123456" not in str(erro.value)


def test_conferir_ia_lista_o_modelo_e_aponta_o_errado(monkeypatch, tmp_path, capsys):
    """`conferir-ia.py` é o comando que transforma “HTTP 400” numa causa.

    O script é pequeno de propósito: ele não deve ter lógica que já não exista
    no `server/`. Aqui só se prova que ele compara o nome do `.env` com a lista
    real da conta e diz qual é o problema.
    """
    import importlib.util

    from server import chaves, provedores

    monkeypatch.setattr(
        chaves,
        "estado",
        lambda: {
            "quantidade": 1,
            "mascaradas": ["gsk_…abc"],
            "provedor": "groq",
            "provedor_id": "groq",
            "base": "https://api.groq.com/openai/v1",
            "modelo": "llama-3.3-70b-versatile-antigo",
            "arquivo": "/tmp/.env",
        },
    )
    monkeypatch.setattr(
        provedores,
        "listar_modelos",
        lambda **_kwargs: {
            "modelos": [
                {"id": "llama-3.3-70b-versatile", "gratis": True},
                {"id": "llama-3.1-8b-instant", "gratis": True},
            ],
            "total": 2,
        },
    )

    caminho = Path(__file__).resolve().parents[2] / "conferir-ia.py"
    spec = importlib.util.spec_from_file_location("conferir_ia", caminho)
    modulo = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(modulo)

    codigo = modulo.main([])
    saida = capsys.readouterr().out

    assert codigo == 1, "modelo fora da lista precisa sair com erro"
    assert "NÃO está na lista" in saida
    assert "llama-3.3-70b-versatile" in saida
    assert "gsk_ABCDEF" not in saida, "a chave nunca aparece inteira"


# ---------------------------------------------------------------------------
# Modelo de raciocínio: 200 com texto vazio (0.91.33)
# ---------------------------------------------------------------------------

class FakeRespostaCorpo(FakeResponse):
    """Uma resposta com corpo escolhido pelo teste."""

    def __init__(self, corpo: dict[str, Any]) -> None:
        super().__init__(200)
        self._corpo = corpo

    def json(self) -> dict[str, Any]:
        return self._corpo


class FakeClienteRoteiro(FakeClient):
    """Devolve a próxima resposta do roteiro a cada POST, em qualquer instância.

    A contagem é da **classe**: cada tentativa do provedor abre um `AsyncClient`
    novo, e o segundo pedido (o de mais espaço) cai numa instância nova.
    """

    roteiro: list[dict[str, Any]] = []
    feitos: list[dict[str, Any]] = []
    ultimo: "FakeClienteRoteiro | None" = None

    def __init__(self, **_kwargs: Any) -> None:
        super().__init__()
        self.calls: list[dict[str, Any]] = FakeClienteRoteiro.feitos
        FakeClienteRoteiro.ultimo = self

    async def post(self, url: str, **kwargs: Any) -> FakeResponse:
        FakeClienteRoteiro.feitos.append({"url": url, **kwargs})
        corpo = FakeClienteRoteiro.roteiro[
            min(len(FakeClienteRoteiro.feitos) - 1, len(FakeClienteRoteiro.roteiro) - 1)
        ]
        return FakeRespostaCorpo(corpo)


def _pedir(monkeypatch: pytest.MonkeyPatch, roteiro: list[dict[str, Any]]) -> tuple[str, list]:
    monkeypatch.setenv("JARVIS_AI_API_KEY", "test-key-not-a-real-secret")
    monkeypatch.setenv("JARVIS_AI_BASE_URL", "https://provider.example/v1")
    monkeypatch.setenv("JARVIS_AI_MODEL", "modelo-raciocinio:free")
    monkeypatch.setattr("server.ai.httpx.AsyncClient", FakeClienteRoteiro)
    FakeClienteRoteiro.roteiro = roteiro
    FakeClienteRoteiro.feitos = []
    provedor = OpenAICompatibleProvider()
    texto = asyncio.run(provedor._pedir([{"role": "user", "content": "oi"}], None, 30.0, 256))
    return texto, FakeClienteRoteiro.feitos


def test_resposta_cortada_por_pensamento_e_pedida_de_novo_com_mais_espaco(monkeypatch):
    """O caso do dono: `finish_reason: length`, `content` vazio.

    Uma segunda tentativa com espaço maior resolve — e é só uma, para não
    gastar duas vezes sem motivo.
    """
    roteiro = [
        {"choices": [{"message": {"content": ""}, "finish_reason": "length"}]},
        {"choices": [{"message": {"content": "pronto, aqui está"}, "finish_reason": "stop"}]},
    ]
    texto, chamadas = _pedir(monkeypatch, roteiro)

    assert texto == "pronto, aqui está"
    assert len(chamadas) == 2
    assert chamadas[1]["json"]["max_tokens"] > chamadas[0]["json"]["max_tokens"]


def test_sem_texto_e_sem_espaco_a_resposta_e_o_raciocinio(monkeypatch):
    """Melhor mostrar o raciocínio do que “resposta vazia” na tela."""
    roteiro = [
        {"choices": [{"message": {"content": "", "reasoning": "analisei e concluí: 2+2=4"}}]}
    ]
    texto, _ = _pedir(monkeypatch, roteiro)
    assert texto.startswith("analisei e concluí")


def test_texto_vazio_sem_nada_mesmo_vira_erro_claro(monkeypatch):
    roteiro = [{"choices": [{"message": {"content": ""}, "finish_reason": "stop"}]}]
    with pytest.raises(AIUnavailable) as erro:
        _pedir(monkeypatch, roteiro)
    assert "resposta vazia" in str(erro.value)
