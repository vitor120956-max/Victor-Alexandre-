"""Quando o provedor diz não: por que, em português, e o que fazer (0.80.3).

O print do dono: o JARVIS respondeu *“Não consegui concluir pela IA externa: O
provedor de IA respondeu com HTTP 400.”* — verdade e inútil. O Google usa **400**
para três problemas diferentes (chave inválida, região não atendida e histórico
que não alterna), e o corpo da resposta diz qual é. Estes testes prendem a
tradução e a correção do histórico.
"""
from __future__ import annotations

import asyncio
import json
from typing import Any

import pytest

from server import chaves
from server.ai import (
    AIRequest,
    AIUnavailable,
    OpenAICompatibleProvider,
    categoria_do_erro,
    detalhe_do_corpo,
    frase_do_erro,
    normalizar_mensagens,
)


# ---------------------------------------------------------------------------
# Falsos: um provedor que responde com corpo de erro
# ---------------------------------------------------------------------------

class Resposta:
    def __init__(self, status: int, corpo: Any = None) -> None:
        self.status_code = status
        self.headers: dict[str, str] = {}
        self._corpo = corpo

    def json(self) -> Any:
        if self._corpo is None:
            raise ValueError("corpo sem JSON")
        return self._corpo


def erro_google(mensagem: str) -> dict[str, Any]:
    return {"error": {"code": 400, "message": mensagem, "status": "INVALID_ARGUMENT"}}


class ClienteFalso:
    """Devolve a primeira resposta e guarda o que foi enviado em cada tentativa."""

    chamadas: list[dict[str, Any]] = []

    def __init__(self, respostas: list[Resposta], **_kwargs: Any) -> None:
        self._respostas = list(respostas)
        ClienteFalso.chamadas = []

    async def __aenter__(self) -> "ClienteFalso":
        return self

    async def __aexit__(self, *_args: Any) -> None:
        return None

    async def post(self, url: str, **kwargs: Any) -> Resposta:
        ClienteFalso.chamadas.append({"url": url, "json": kwargs.get("json")})
        if len(self._respostas) > 1:
            return self._respostas.pop(0)
        return self._respostas[0]


@pytest.fixture()
def provedor(monkeypatch: pytest.MonkeyPatch) -> OpenAICompatibleProvider:
    monkeypatch.setenv("JARVIS_AI_API_KEY", "chave-de-teste-nao-e-segredo")
    monkeypatch.setenv("JARVIS_AI_BASE_URL", "https://generativelanguage.googleapis.com/v1beta/openai")
    monkeypatch.setenv("JARVIS_AI_MODEL", "gemini-2.5-flash")
    return OpenAICompatibleProvider()


def _rodar(respostas: list[Resposta], monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("server.ai.httpx.AsyncClient", lambda **kw: ClienteFalso(respostas, **kw))


# ---------------------------------------------------------------------------
# O histórico: a causa mais provável do 400 do print
# ---------------------------------------------------------------------------

def test_falas_seguidas_do_mesmo_lado_sao_juntadas():
    """Duas perguntas suas em sequência = 400 no Google; juntas, é um pedido só."""
    mensagens = [
        {"role": "system", "content": "Você é o JARVIS."},
        {"role": "system", "content": "Contexto pessoal."},
        {"role": "user", "content": "abre o gmail"},
        {"role": "user", "content": "veja e faça um filtro do que é importante"},
    ]
    juntas = normalizar_mensagens(mensagens)
    assert [item["role"] for item in juntas] == ["system", "user"]
    assert "abre o gmail" in juntas[1]["content"]
    assert "filtro" in juntas[1]["content"]


def test_juntar_nao_muda_a_ordem_nem_o_conteudo_dos_papeis_alternados():
    mensagens = [
        {"role": "system", "content": "s"},
        {"role": "user", "content": "u1"},
        {"role": "assistant", "content": "a1"},
        {"role": "user", "content": "u2"},
    ]
    assert normalizar_mensagens(mensagens) == mensagens


def test_mensagem_vazia_sai_para_nao_gerar_400():
    assert normalizar_mensagens([{"role": "user", "content": "  "}]) == []


def test_o_historico_com_falas_seguidas_vai_junto_para_o_provedor(provedor, monkeypatch):
    _rodar([Resposta(200, {"choices": [{"message": {"content": "ok"}}]})], monkeypatch)
    request = AIRequest(
        message="e agora?",
        history=[
            {"role": "user", "content": "abre o gmail"},
            {"role": "user", "content": "faz um filtro"},
        ],
    )
    assert asyncio.run(provedor.generate(request)) == "ok"
    enviadas = ClienteFalso.chamadas[0]["json"]["messages"]
    papeis = [item["role"] for item in enviadas]
    assert papeis.count("user") == 1  # as três viraram uma só
    assert "faz um filtro" in enviadas[-1]["content"]


# ---------------------------------------------------------------------------
# As três caras do HTTP 400 do Google
# ---------------------------------------------------------------------------

def test_400_de_chave_invalida_vira_aviso_de_chave_recusada(provedor, monkeypatch):
    """O Google responde 400 (não 401) para chave inválida. A frase tem de dizer isso."""
    _rodar([Resposta(400, erro_google("API key not valid. Please pass a valid API key."))], monkeypatch)
    with pytest.raises(AIUnavailable) as erro:
        asyncio.run(provedor.generate(AIRequest(message="Olá")))
    texto = str(erro.value)
    assert "recusada" in texto or "recusadas" in texto
    assert "aistudio.google.com/apikey" in texto
    assert "HTTP 400" not in texto.split("O provedor disse")[0]


def test_400_de_regiao_diz_que_e_a_regiao_e_manda_para_o_groq(provedor, monkeypatch):
    _rodar([Resposta(400, erro_google("User location is not supported for the API use."))], monkeypatch)
    with pytest.raises(AIUnavailable) as erro:
        asyncio.run(provedor.generate(AIRequest(message="Olá")))
    texto = str(erro.value)
    assert "região" in texto
    assert "Groq" in texto and "OpenRouter" in texto


def test_400_de_historico_manda_comecar_conversa_nova(provedor, monkeypatch):
    corpo = erro_google("Please ensure that multiturn requests alternate between user and model.")
    _rodar([Resposta(400, corpo)], monkeypatch)
    with pytest.raises(AIUnavailable) as erro:
        asyncio.run(provedor.generate(AIRequest(message="Olá")))
    texto = str(erro.value)
    assert "conversa nova" in texto
    assert "alternar" in texto


def test_404_de_modelo_diz_que_o_nome_nao_existe(provedor, monkeypatch):
    _rodar([Resposta(404, {"error": {"message": "model `gemini-9.9` does not exist"}})], monkeypatch)
    with pytest.raises(AIUnavailable) as erro:
        asyncio.run(provedor.generate(AIRequest(message="Olá")))
    texto = str(erro.value)
    assert "não existe" in texto
    assert "Ver modelos da minha chave" in texto


def test_400_desconhecido_ganha_uma_segunda_tentativa_minima(provedor, monkeypatch):
    """Parâmetro extra é a causa mais comum: uma segunda chamada sem eles resolve."""
    _rodar(
        [
            Resposta(400, erro_google("Invalid JSON payload received. Unknown name 'temperature'.")),
            Resposta(200, {"choices": [{"message": {"content": "respondeu no segundo"}}]}),
        ],
        monkeypatch,
    )
    assert asyncio.run(provedor.generate(AIRequest(message="Olá"))) == "respondeu no segundo"
    assert len(ClienteFalso.chamadas) == 2
    assert set(ClienteFalso.chamadas[1]["json"]) == {"model", "messages"}


def test_400_que_continua_400_depois_da_segunda_tentativa_mostra_o_motivo(provedor, monkeypatch):
    corpo = erro_google("Unsupported field: seed")
    _rodar([Resposta(400, corpo)], monkeypatch)
    with pytest.raises(AIUnavailable) as erro:
        asyncio.run(provedor.generate(AIRequest(message="Olá")))
    assert "Unsupported field: seed" in str(erro.value)


def test_a_frase_do_provedor_nunca_mostra_a_chave(provedor, monkeypatch):
    """O provedor às vezes ecoa a chave na mensagem; ela não pode ir para a tela."""
    corpo = erro_google("invalid api key: AIzaSyFAKE0000000000000000000000000000 for request")
    _rodar([Resposta(400, corpo)], monkeypatch)
    with pytest.raises(AIUnavailable) as erro:
        asyncio.run(provedor.generate(AIRequest(message="Olá")))
    texto = str(erro.value)
    assert "AIzaSyFAKE0000000000000000000000000000" not in texto
    assert "chave" in texto


# ---------------------------------------------------------------------------
# Peças soltas
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "status, mensagem, esperado",
    [
        (400, "API key not valid. Please pass a valid API key.", "chave"),
        (400, "User location is not supported for the API use.", "regiao"),
        (400, "Please ensure that multiturn requests alternate between user and model.", "historico"),
        (404, "model `x` does not exist", "modelo"),
        (429, "quota exceeded", "cota"),
        (500, "", "outro"),
    ],
)
def test_classificacao_do_erro(status: int, mensagem: str, esperado: str):
    assert categoria_do_erro(status, mensagem) == esperado


def test_detalhe_do_corpo_aceita_corpo_sem_json():
    assert detalhe_do_corpo(Resposta(502)) == ""
    assert detalhe_do_corpo(Resposta(400, {"erro": "outra forma"})) == ""


def test_frase_do_erro_sem_detalhe_nao_inventa_causa():
    frase = frase_do_erro(500, "", "outro")
    assert frase == "o provedor de IA respondeu com HTTP 500."


# ---------------------------------------------------------------------------
# O teste das chaves conta a mesma história
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "mensagem, trecho",
    [
        ("API key not valid. Please pass a valid API key.", "chave inválida"),
        ("User location is not supported for the API use.", "região"),
        ("Please ensure that multiturn requests alternate between user and model.", "conversa nova"),
    ],
)
def test_o_teste_das_chaves_traduz_o_400_do_google(mensagem: str, trecho: str):
    motivo = chaves._motivo_do_corpo(400, {"error": {"message": mensagem}})
    assert trecho in motivo


def test_o_teste_das_chaves_tem_frase_propria_para_400():
    assert 400 in chaves._MOTIVOS
    assert "400" in chaves._MOTIVOS[400]


def test_429_continua_com_os_numeros_do_provedor():
    motivo = chaves._motivo_do_corpo(
        429, {"error": {"message": "Rate limit reached. Limit 100000, Used 100000, try again in 12m34s"}}
    )
    assert "12m34s" in motivo
    assert "limite 100000" in motivo
