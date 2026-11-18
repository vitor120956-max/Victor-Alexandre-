"""Previsão do tempo de verdade — sem modelo, sem chave, sem inventar (0.91.36).

A pergunta que gerou isto, depois de a IA provar que responde:

    deu isso e se eu perguntar como esta a previsao de tempo hj ou se vai
    chover hj?

Até a 0.91.35, essa pergunta ia para o **modelo**. E o modelo não vê o tempo:
ele não tem relógio, nem janela, nem acesso à previsão. Ou responde *“não tenho
acesso a dados em tempo real”*, ou **inventa** uma temperatura plausível. As
duas respostas são ruins, e a segunda é pior: parece a mesma coisa que funcionou
no “testar ia”.

Aqui a previsão vem de um serviço público e gratuito, por HTTPS, sem chave:

- `geocoding-api.open-meteo.com` — transforma o nome da cidade em latitude e
  longitude;
- `api.open-meteo.com` — devolve o tempo de agora e a previsão de hoje e de
  amanhã, incluindo a **probabilidade de chuva**.

## O que este módulo garante

1. **Fonte na resposta.** Todo texto sai com *“Fonte: Open-Meteo”* e a hora em
   que foi lido. Sem isso a resposta é indistinguível de um palpite — e foi
   exatamente esse o problema da 0.91.34.
2. **Nunca inventa.** Sem rede, cidade não encontrada ou resposta estragada, o
   módulo levanta `TempoError` com o motivo em português. Não existe caminho em
   que ele devolva uma temperatura “mais ou menos”.
3. **Não passa pelo modelo.** Zero tokens, zero cota; funciona com a chave
   apagada.
4. **Só dois endereços fixos.** Não aceita URL de fora, não baixa página
   escolhida pelo texto do usuário, não manda nada além do nome da cidade.

O nome da cidade vem da frase (`previsão em São José`) ou de `JARVIS_CIDADE` no
`.env`; sem nenhum dos dois, é **Palhoça**, onde o dono mora.
"""
from __future__ import annotations

import json
import os
from datetime import datetime
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import quote_plus, urlparse
from urllib.request import Request, urlopen

FONTE = "Open-Meteo"
SITE = "open-meteo.com"
GEO = "https://geocoding-api.open-meteo.com/v1/search"
PREVISAO = "https://api.open-meteo.com/v1/forecast"
CIDADE_PADRAO = "Palhoça"
AGENTE = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) JarvisTempo/1.0"
TIMEOUT = 15
MAX_RESPOSTA = 1 * 1024 * 1024

# Códigos WMO, que é o que o Open-Meteo devolve no lugar de “nublado”.
# A tabela é a oficial, reduzida a frases de gente.
_CONDICOES: tuple[tuple[tuple[int, ...], str], ...] = (
    ((0,), "céu limpo"),
    ((1,), "quase limpo"),
    ((2,), "parcialmente nublado"),
    ((3,), "encoberto"),
    ((45, 48), "neblina"),
    ((51, 53, 55, 56, 57), "garoa"),
    ((61,), "chuva fraca"),
    ((63,), "chuva"),
    ((65,), "chuva forte"),
    ((66, 67), "chuva congelante"),
    ((71, 73, 75, 77), "neve"),
    ((80, 81, 82), "pancadas de chuva"),
    ((85, 86), "pancadas de neve"),
    ((95,), "trovoada"),
    ((96, 99), "trovoada com granizo"),
)

Baixar = Callable[[str], dict[str, Any]]


class TempoError(ValueError):
    """Não deu para saber o tempo — e a frase diz por quê, sem adivinhar."""


def cidade_padrao() -> str:
    """A cidade de quem usa: `JARVIS_CIDADE` no `.env`, ou Palhoça."""
    return (os.getenv("JARVIS_CIDADE", "") or "").strip() or CIDADE_PADRAO


def descrever(codigo: Any) -> str:
    """Código WMO → frase em português. Código desconhecido não vira mentira."""
    try:
        numero = int(codigo)
    except (TypeError, ValueError):
        return "condição não informada"
    for codigos, frase in _CONDICOES:
        if numero in codigos:
            return frase
    return f"condição {numero} (não catalogada)"


def _numero(valor: Any, casas: int = 0) -> str:
    """Número no formato brasileiro, sem `None` virando `0`."""
    try:
        numero = float(valor)
    except (TypeError, ValueError):
        return "—"
    return f"{numero:.{casas}f}".replace(".", ",")


def _baixar_json(url: str) -> dict[str, Any]:
    """Uma leitura de JSON dos endereços fixos deste módulo.

    Só http(s), só os dois hosts do Open-Meteo e com teto de tamanho. É o mesmo
    cuidado de `busca_web`: este módulo não baixa o que o texto do usuário
    mandar.
    """
    partes = urlparse(url)
    if partes.scheme != "https" or partes.hostname not in {
        "api.open-meteo.com",
        "geocoding-api.open-meteo.com",
    }:
        raise TempoError(f"endereço fora da lista do tempo: {partes.hostname or url}")
    pedido = Request(
        url,
        headers={"User-Agent": AGENTE, "Accept": "application/json", "Accept-Language": "pt-BR,pt;q=0.9"},
    )
    try:
        with urlopen(pedido, timeout=TIMEOUT) as resposta:
            dados = resposta.read(MAX_RESPOSTA + 1)
    except HTTPError as exc:
        raise TempoError(f"o serviço de previsão respondeu HTTP {exc.code}") from exc
    except (URLError, OSError) as exc:
        raise TempoError(
            "não consegui falar com o serviço de previsão "
            f"({type(exc).__name__}). Sem internet não há previsão — e eu não vou inventar uma."
        ) from exc
    if len(dados) > MAX_RESPOSTA:
        raise TempoError("a resposta do serviço de previsão veio grande demais")
    try:
        corpo = json.loads(dados.decode("utf-8", errors="replace"))
    except ValueError as exc:
        raise TempoError("o serviço de previsão respondeu algo que não é JSON") from exc
    if not isinstance(corpo, dict):
        raise TempoError("o serviço de previsão respondeu num formato inesperado")
    if corpo.get("error"):
        raise TempoError(f"o serviço de previsão recusou o pedido: {corpo.get('reason') or corpo['error']}")
    return corpo


def geocodificar(cidade: str, baixar: Baixar | None = None) -> dict[str, Any]:
    """Nome da cidade → lugar do mundo. Cidade que não existe é dita, não chutada."""
    nome = " ".join((cidade or "").split()).strip(" ,.")
    if not nome:
        raise TempoError("não sei para qual cidade perguntar. Diga “previsão em Palhoça”.")
    url = f"{GEO}?name={quote_plus(nome)}&count=1&language=pt&format=json"
    corpo = (baixar or _baixar_json)(url)
    resultados = corpo.get("results") if isinstance(corpo, dict) else None
    if not isinstance(resultados, list) or not resultados:
        raise TempoError(
            f"não achei a cidade “{nome}”. Tente com o nome mais completo "
            "(“Palhoça, SC”, “São Paulo”) ou mude JARVIS_CIDADE no .env."
        )
    lugar = resultados[0] if isinstance(resultados[0], dict) else {}
    try:
        latitude = float(lugar["latitude"])
        longitude = float(lugar["longitude"])
    except (KeyError, TypeError, ValueError) as exc:
        raise TempoError("o serviço devolveu a cidade sem coordenadas") from exc
    return {
        "nome": str(lugar.get("name") or nome),
        "estado": str(lugar.get("admin1") or ""),
        "pais": str(lugar.get("country") or ""),
        "latitude": latitude,
        "longitude": longitude,
    }


def _url_previsao(lugar: dict[str, Any]) -> str:
    return (
        f"{PREVISAO}?latitude={lugar['latitude']:.4f}&longitude={lugar['longitude']:.4f}"
        "&current=temperature_2m,apparent_temperature,relative_humidity_2m,"
        "precipitation,weather_code,wind_speed_10m"
        "&daily=weather_code,temperature_2m_max,temperature_2m_min,"
        "precipitation_probability_max,precipitation_sum"
        "&timezone=auto&forecast_days=2"
    )


def _primeiro(lista: Any, posicao: int = 0) -> Any:
    if isinstance(lista, list) and len(lista) > posicao:
        return lista[posicao]
    return None


def previsao(cidade: str | None = None, baixar: Baixar | None = None) -> dict[str, Any]:
    """O tempo de agora, de hoje e de amanhã, com a fonte e a hora da leitura."""
    procurada = (cidade or "").strip() or cidade_padrao()
    lugar = geocodificar(procurada, baixar=baixar)
    corpo = (baixar or _baixar_json)(_url_previsao(lugar))

    atual = corpo.get("current") if isinstance(corpo.get("current"), dict) else {}
    diario = corpo.get("daily") if isinstance(corpo.get("daily"), dict) else {}
    if not atual and not diario:
        raise TempoError("o serviço respondeu sem os dados do tempo (nem agora, nem hoje)")

    hoje = {
        "codigo": _primeiro(diario.get("weather_code"), 0),
        "maxima": _primeiro(diario.get("temperature_2m_max"), 0),
        "minima": _primeiro(diario.get("temperature_2m_min"), 0),
        "chuva_probabilidade": _primeiro(diario.get("precipitation_probability_max"), 0),
        "chuva_mm": _primeiro(diario.get("precipitation_sum"), 0),
    }
    amanha = {
        "codigo": _primeiro(diario.get("weather_code"), 1),
        "maxima": _primeiro(diario.get("temperature_2m_max"), 1),
        "minima": _primeiro(diario.get("temperature_2m_min"), 1),
        "chuva_probabilidade": _primeiro(diario.get("precipitation_probability_max"), 1),
        "chuva_mm": _primeiro(diario.get("precipitation_sum"), 1),
    }
    if hoje["maxima"] is None and atual.get("temperature_2m") is None:
        raise TempoError("o serviço não mandou temperatura para hoje")

    lido = datetime.now()
    return {
        "cidade": lugar,
        "agora": {
            "temperatura": atual.get("temperature_2m"),
            "sensacao": atual.get("apparent_temperature"),
            "umidade": atual.get("relative_humidity_2m"),
            "vento": atual.get("wind_speed_10m"),
            "chuva_mm": atual.get("precipitation"),
            "codigo": atual.get("weather_code"),
        },
        "hoje": hoje,
        "amanha": amanha,
        "lido_em": lido.strftime("%d/%m às %H:%M"),
        "fonte": FONTE,
        "site": SITE,
    }


def _vai_chover(dia: dict[str, Any]) -> str:
    """A resposta direta que ele pediu: sim, não, ou “talvez” com o número."""
    probabilidade = dia.get("chuva_probabilidade")
    try:
        chance = float(probabilidade)
    except (TypeError, ValueError):
        chance = -1.0
    if chance < 0:
        return "o serviço não disse a chance de chuva"
    if chance >= 50:
        return f"sim, deve chover — {_numero(chance)}% de chance"
    if chance >= 25:
        return f"talvez chova — {_numero(chance)}% de chance"
    return f"não deve chover — {_numero(chance)}% de chance"


def _linha_do_dia(rotulo: str, dia: dict[str, Any]) -> str:
    partes = [
        f"{rotulo}: {_numero(dia['minima'])} °C a {_numero(dia['maxima'])} °C",
        descrever(dia["codigo"]),
        _vai_chover(dia),
    ]
    chuva = dia.get("chuva_mm")
    try:
        if float(chuva) > 0.2:
            partes.append(f"~{_numero(chuva, 1)} mm")
    except (TypeError, ValueError):
        pass
    return " · ".join(partes)


def formatar(dados: dict[str, Any], quando: str = "hoje") -> str:
    """O texto que vai para a conversa — com fonte, hora e a resposta direta."""
    lugar = dados["cidade"]
    cidade = lugar["nome"] + (f", {lugar['estado']}" if lugar.get("estado") else "")
    agora = dados.get("agora") or {}
    linhas = [
        f"Previsão para {cidade} — lida agora, {dados['lido_em']} (fonte: {FONTE}):",
        "",
    ]
    if agora.get("temperatura") is not None:
        partes = [f"Agora: {_numero(agora['temperatura'])} °C"]
        if agora.get("sensacao") is not None:
            partes.append(f"sensação {_numero(agora['sensacao'])} °C")
        partes.append(descrever(agora.get("codigo")))
        if agora.get("umidade") is not None:
            partes.append(f"umidade {_numero(agora['umidade'])}%")
        if agora.get("vento") is not None:
            partes.append(f"vento {_numero(agora['vento'])} km/h")
        linhas.append(" · ".join(partes))
    linhas.append(_linha_do_dia("Hoje", dados["hoje"]))
    if dados["amanha"].get("maxima") is not None:
        linhas.append(_linha_do_dia("Amanhã", dados["amanha"]))

    alvo = dados["hoje"] if quando != "amanha" else dados["amanha"]
    quando_texto = "hoje" if quando != "amanha" else "amanhã"
    linhas.append("")
    linhas.append(f"Vai chover {quando_texto}? {_vai_chover(alvo)}.")
    linhas.append("")
    linhas.append(
        f"Fonte: {FONTE} ({SITE}) — previsão, não medição da janela. "
        "Quem respondeu foi o serviço de previsão, não o modelo."
    )
    return "\n".join(linhas)
