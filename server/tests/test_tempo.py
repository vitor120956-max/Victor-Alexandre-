"""A previsão do tempo sem modelo, sem chave e sem inventar (0.91.36).

A pergunta do dono, logo depois de a IA provar que responde:

    deu isso e se eu perguntar como esta a previsao de tempo hj ou se vai
    chover hj?

Até a 0.91.35 a frase ia para o **modelo**, e o modelo não vê o tempo: ou diz
que não tem acesso, ou inventa uma temperatura plausível. Numa tela que acabou
de mostrar “· IA EXTERNA”, as duas respostas parecem igualmente confiáveis — e
só uma é verdade.

O que estes testes prendem:

1. a frase vira consulta ao serviço de previsão (Open-Meteo), não ao modelo;
2. a resposta diz **de onde veio** e **quando foi lida**;
3. chuva é respondida com número (“sim, deve chover — 80% de chance”);
4. sem rede, cidade errada ou resposta estragada, ele **não inventa**: diz que
   não conseguiu e explica o motivo.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from server import tempo
from server.app import create_app
from server.skill_registry import build_registry

RAIZ = Path(__file__).resolve().parents[2]

GEO_PALHOCA = {
    "results": [
        {
            "name": "Palhoça",
            "latitude": -27.6444,
            "longitude": -48.6678,
            "admin1": "Santa Catarina",
            "country": "Brasil",
        }
    ]
}

PREVISAO_HOJE_CHUVOSA = {
    "current": {
        "time": "2026-11-18T10:00",
        "temperature_2m": 23.4,
        "apparent_temperature": 25.1,
        "relative_humidity_2m": 88,
        "precipitation": 0.0,
        "weather_code": 3,
        "wind_speed_10m": 9.2,
    },
    "daily": {
        "time": ["2026-11-18", "2026-11-19"],
        "weather_code": [61, 3],
        "temperature_2m_max": [26.5, 24.0],
        "temperature_2m_min": [18.2, 16.9],
        "precipitation_probability_max": [80, 20],
        "precipitation_sum": [6.4, 0.0],
    },
}

PREVISAO_SECA = {
    "current": {"temperature_2m": 31.0, "weather_code": 0, "wind_speed_10m": 4.0},
    "daily": {
        "time": ["2026-11-18", "2026-11-19"],
        "weather_code": [0, 1],
        "temperature_2m_max": [33.0, 32.0],
        "temperature_2m_min": [21.0, 20.0],
        "precipitation_probability_max": [5, 10],
        "precipitation_sum": [0.0, 0.0],
    },
}


def _baixar(respostas: dict[str, dict]):
    """Dublê de rede: devolve por tipo de endereço e guarda o que foi pedido."""
    pedidos: list[str] = []

    def baixar(url: str) -> dict:
        pedidos.append(url)
        if "geocoding" in url:
            return respostas.get("geo", GEO_PALHOCA)
        return respostas.get("previsao", PREVISAO_HOJE_CHUVOSA)

    baixar.pedidos = pedidos  # type: ignore[attr-defined]
    return baixar


# ---------------------------------------------------------------------------
# A tradução do código do tempo
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "codigo, frase",
    [
        (0, "céu limpo"),
        (3, "encoberto"),
        (45, "neblina"),
        (61, "chuva fraca"),
        (65, "chuva forte"),
        (80, "pancadas de chuva"),
        (95, "trovoada"),
        (99, "trovoada com granizo"),
    ],
)
def test_codigo_do_tempo_vira_frase(codigo, frase):
    assert tempo.descrever(codigo) == frase


def test_codigo_desconhecido_nao_vira_mentira():
    assert "não catalogada" in tempo.descrever(1234)
    assert tempo.descrever(None) == "condição não informada"


# ---------------------------------------------------------------------------
# Cidade
# ---------------------------------------------------------------------------

def test_cidade_vira_coordenadas_e_traz_o_estado():
    baixar = _baixar({})
    lugar = tempo.geocodificar("Palhoça", baixar=baixar)

    assert lugar["nome"] == "Palhoça"
    assert lugar["estado"] == "Santa Catarina"
    assert round(lugar["latitude"], 2) == -27.64
    # O nome vai na URL, codificado: acento e espaço não quebram o pedido.
    assert "name=Palho%C3%A7a" in baixar.pedidos[0]  # type: ignore[attr-defined]


def test_cidade_que_nao_existe_e_dita_com_o_proximo_passo():
    baixar = _baixar({"geo": {"results": []}})
    with pytest.raises(tempo.TempoError) as erro:
        tempo.geocodificar("Xyzzy", baixar=baixar)
    assert "não achei a cidade “Xyzzy”" in str(erro.value)
    assert "JARVIS_CIDADE" in str(erro.value)


def test_sem_cidade_usa_a_do_env_e_sem_env_usa_palhoca(monkeypatch):
    monkeypatch.delenv("JARVIS_CIDADE", raising=False)
    assert tempo.cidade_padrao() == "Palhoça"
    monkeypatch.setenv("JARVIS_CIDADE", "Florianópolis")
    assert tempo.cidade_padrao() == "Florianópolis"


def test_sem_cidade_na_frase_a_previsao_usa_a_padrao(monkeypatch):
    monkeypatch.delenv("JARVIS_CIDADE", raising=False)
    baixar = _baixar({})
    dados = tempo.previsao(None, baixar=baixar)
    assert dados["cidade"]["nome"] == "Palhoça"


# ---------------------------------------------------------------------------
# A resposta
# ---------------------------------------------------------------------------

def test_previsao_traz_hoje_amanha_fonte_e_hora():
    dados = tempo.previsao("Palhoça", baixar=_baixar({}))

    assert dados["hoje"]["maxima"] == 26.5
    assert dados["hoje"]["chuva_probabilidade"] == 80
    assert dados["amanha"]["chuva_probabilidade"] == 20
    assert dados["agora"]["temperatura"] == 23.4
    assert dados["fonte"] == "Open-Meteo"
    assert " às " in dados["lido_em"]


def test_a_resposta_diz_de_onde_veio_e_que_nao_foi_o_modelo():
    """Sem isso, o texto é indistinguível de um palpite — o erro da 0.91.34."""
    texto = tempo.formatar(tempo.previsao("Palhoça", baixar=_baixar({})))

    assert "Fonte: Open-Meteo (open-meteo.com)" in texto
    assert "lida agora" in texto
    assert "não o modelo" in texto
    assert "Palhoça, Santa Catarina" in texto
    assert "Agora: 23 °C" in texto


def test_vai_chover_hoje_responde_sim_com_o_numero():
    texto = tempo.formatar(tempo.previsao("Palhoça", baixar=_baixar({})), quando="hoje")
    assert "Vai chover hoje? sim, deve chover — 80% de chance." in texto


def test_sem_chuva_responde_nao_com_o_numero():
    baixar = _baixar({"previsao": PREVISAO_SECA})
    texto = tempo.formatar(tempo.previsao("Palhoça", baixar=baixar), quando="hoje")
    assert "Vai chover hoje? não deve chover — 5% de chance." in texto


@pytest.mark.parametrize("chance, esperado", [(25, "talvez chova"), (35, "talvez chova"), (49, "talvez chova")])
def test_chance_media_vira_talvez_em_vez_de_sim_ou_nao(chance, esperado):
    assert esperado in tempo._vai_chover({"chuva_probabilidade": chance})


def test_perguntar_por_amanha_responde_por_amanha():
    """Amanhã tem 20%: a resposta de hoje (80%) não pode vazar para amanhã."""
    dados = tempo.previsao("Palhoça", baixar=_baixar({}))
    texto = tempo.formatar(dados, quando="amanha")

    assert "Vai chover amanhã? não deve chover — 20% de chance." in texto
    # 26,5 arredonda para 26 (meio para o par): o número é o que o serviço deu.
    assert "Hoje: 18 °C a 26 °C" in texto
    assert "Amanhã: 17 °C a 24 °C" in texto


def test_sem_chance_de_chuva_ele_diz_que_o_servico_nao_disse():
    dados = tempo.previsao("Palhoça", baixar=_baixar({"previsao": {"current": {"temperature_2m": 20}, "daily": {"temperature_2m_max": [22], "temperature_2m_min": [15], "weather_code": [1]}}}))
    assert "não disse a chance de chuva" in tempo._vai_chover(dados["hoje"])


# ---------------------------------------------------------------------------
# Quando não dá: nunca inventa
# ---------------------------------------------------------------------------

def test_sem_internet_o_erro_diz_que_nao_vai_inventar():
    def baixar(_url: str) -> dict:
        raise tempo.TempoError("falhou a conexão")

    with pytest.raises(tempo.TempoError):
        tempo.previsao("Palhoça", baixar=baixar)

    # A frase que o dono lê quando a rede cai — sem número nenhum.
    assert "não vou inventar" in (
        "não consegui falar com o serviço de previsão "
        "(URLError). Sem internet não há previsão — e eu não vou inventar uma."
    )


def test_endereco_fora_da_lista_e_recusado():
    """O módulo só fala com dois hosts fixos: nada de URL vinda de fora."""
    with pytest.raises(tempo.TempoError) as erro:
        tempo._baixar_json("https://exemplo.com/previsao")
    assert "fora da lista do tempo" in str(erro.value)


def test_resposta_que_nao_e_json_explica(monkeypatch):
    class Resposta:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def read(self, _limite):
            return b"<html>manutencao</html>"

    monkeypatch.setattr(tempo, "urlopen", lambda *_a, **_k: Resposta())
    with pytest.raises(tempo.TempoError) as erro:
        tempo._baixar_json("https://api.open-meteo.com/v1/forecast?x=1")
    assert "não é JSON" in str(erro.value)


def test_erro_do_servico_mostra_o_motivo(monkeypatch):
    corpo = json.dumps({"error": True, "reason": "Latitude must be in range"}).encode()

    class Resposta:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def read(self, _limite):
            return corpo

    monkeypatch.setattr(tempo, "urlopen", lambda *_a, **_k: Resposta())
    with pytest.raises(tempo.TempoError) as erro:
        tempo._baixar_json("https://api.open-meteo.com/v1/forecast?x=1")
    assert "Latitude must be in range" in str(erro.value)


def test_resposta_sem_dados_do_tempo_nao_vira_zero_grau():
    baixar = _baixar({"previsao": {"daily": {}}})
    with pytest.raises(tempo.TempoError) as erro:
        tempo.previsao("Palhoça", baixar=baixar)
    assert "sem os dados do tempo" in str(erro.value)


# ---------------------------------------------------------------------------
# A rota que a tela usa
# ---------------------------------------------------------------------------

@pytest.fixture()
def cliente(monkeypatch, tmp_path):
    monkeypatch.setattr(tempo, "_baixar_json", _baixar({}))
    app = create_app(registry=build_registry(tmp_path / "files"))
    return TestClient(app)


def test_a_rota_devolve_texto_com_fonte(cliente):
    resposta = cliente.get("/api/tempo", params={"cidade": "Palhoça", "quando": "hoje"})
    assert resposta.status_code == 200
    corpo = resposta.json()

    assert corpo["ok"] is True
    assert corpo["fonte"] == "Open-Meteo"
    assert "Fonte: Open-Meteo" in corpo["texto"]
    assert corpo["result"]["hoje"]["chuva_probabilidade"] == 80


def test_a_rota_sem_cidade_usa_a_padrao(cliente, monkeypatch):
    monkeypatch.delenv("JARVIS_CIDADE", raising=False)
    corpo = cliente.get("/api/tempo").json()
    assert corpo["result"]["cidade"]["nome"] == "Palhoça"


def test_quando_nao_da_a_rota_explica_e_nao_inventa(monkeypatch, tmp_path):
    def falhar(_url: str) -> dict:
        raise tempo.TempoError("sem internet")

    monkeypatch.setattr(tempo, "_baixar_json", falhar)
    app = create_app(registry=build_registry(tmp_path / "files"))
    resposta = TestClient(app).get("/api/tempo", params={"cidade": "Palhoça"})

    assert resposta.status_code == 502
    erro = resposta.json()["error"]
    assert erro["code"] == "TEMPO_INDISPONIVEL"
    assert "Nada foi inventado" in erro["message"]


def test_a_previsao_nao_toca_no_modelo(cliente):
    """Zero tokens: funciona com a chave apagada e sem provedor configurado."""
    corpo = cliente.get("/api/tempo", params={"cidade": "Palhoça"}).json()
    texto = json.dumps(corpo, ensure_ascii=False).lower()
    assert "openrouter" not in texto
    assert "openai" not in texto
    assert "tokens" not in texto


# ---------------------------------------------------------------------------
# Quando a frase escapa do parser, o modelo não pode inventar (0.91.36)
# ---------------------------------------------------------------------------

def test_o_prompt_do_modelo_proibe_inventar_tempo_e_cotacao():
    """A rede de segurança: o parser cobre as frases comuns, o prompt cobre o resto."""
    fonte = (RAIZ / "server" / "ai.py").read_text(encoding="utf-8")
    inicio = fonte.index("Você é a camada generativa do JARVIS")
    trecho = fonte[inicio : inicio + 2000]

    assert "não vê dados em tempo real" in trecho
    assert "tempo" in trecho and "cotação" in trecho
    assert "em vez de estimar um número" in trecho
    assert "vai chover hoje?" in trecho
