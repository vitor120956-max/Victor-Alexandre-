"""Chaves de IA: colar, guardar, conferir e apagar — sem passar pelo prompt.

O pedido que gerou este módulo: *“não é melhor botar um botão dentro do JARVIS
onde eu só coloco as chaves?”*. Sim. O caminho anterior era um comando no
`cmd`, e o que aconteceu na prática foi o dono colando as anotações
(`api grok 1 gsk_…`) direto no prompt, recebendo três vezes *“'api' não é
reconhecido como um comando interno ou externo”*.

## O desenho

| camada | arquivo | o que faz |
|---|---|---|
| núcleo | `server/chaves.py` (aqui) | extrai, mascara, grava e lê o `.env` |
| HTTP | `server/app.py` | `GET/POST/DELETE /api/ai/chaves`, `POST /api/ai/chaves/testar` |
| tela | `src/pages/SettingsPage.tsx` | o cartão “Chaves de IA”, com o campo e os botões |

## As regras que este módulo não negocia

1. **A chave nunca volta.** `estado()` devolve quantidade e máscara
   (`gsk_a…BkXV`); o texto colado é gravado e esquecido. Nenhuma resposta HTTP
   contém a chave inteira — nem em erro.
2. **Só de dentro da máquina.** Quem grava chave é o dono, na própria máquina.
   Requisição da rede local (celular, outro PC) lê o estado, mas não escreve.
3. **O que vem colado não é confiável.** O texto é varrido por padrão de chave
   (`gsk_…`, `sk-…`, `AIza…`, `sk-or-v1-…`); rótulo, número e palavra são
   descartados. Sem nenhuma chave reconhecível, nada é gravado e a resposta diz
   o porquê.
4. **O `.env` é do usuário.** A gravação troca só as quatro linhas da IA e
   mantém comentário, ordem e as outras variáveis; o arquivo continua em CRLF
   com BOM nenhum (o Bloco de Notas do Windows 10 antigo precisa disso).
5. **Aplicar não é reiniciar.** `aplicar_no_ambiente()` põe os valores em
   `os.environ` e o provedor recarrega na hora — salvar chave não exige fechar a
   janela. Se algo falhar, o próximo start lê o `.env` e fica igual.
"""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

from . import dados as dados_locais

# Formatos aceitos. A lista existe para não confundir "api groq 1" com chave.
PADROES_CHAVE = (
    r"gsk_[A-Za-z0-9]{20,}",          # Groq
    r"sk-or-v1-[A-Za-z0-9]{20,}",     # OpenRouter
    r"sk-[A-Za-z0-9_-]{20,}",         # OpenAI e compatíveis
    r"AIza[A-Za-z0-9_-]{30,}",        # Google AI Studio
)

CHAVES_IA = (
    "JARVIS_AI_PROVIDER",
    "JARVIS_AI_BASE_URL",
    "JARVIS_AI_MODEL",
    "JARVIS_AI_API_KEY",
)
# O Groq é o provedor grátis recomendado; quando as chaves têm essa cara, o
# endereço e o modelo são preenchidos sozinhos (ninguém decora `llama-3.3-70b`).
GROQ = {
    "JARVIS_AI_PROVIDER": "Groq",
    "JARVIS_AI_BASE_URL": "https://api.groq.com/openai/v1",
    "JARVIS_AI_MODEL": "llama-3.3-70b-versatile",
}
MAX_CHAVES = 10  # mais que isso não é cota, é coleção
MAX_TEXTO = 20_000  # ~200 chaves de 56 caracteres; recusa colagem absurda

# Troca em teste: `monkeypatch.setattr(chaves, "ENV_CAMINHO", tmp_path / ".env")`.
ENV_CAMINHO: Path | None = None


def env_path() -> Path:
    return Path(ENV_CAMINHO) if ENV_CAMINHO else dados_locais.PROJETO / ".env"


# ---------------------------------------------------------------------------
# Ler o que a pessoa colou
# ---------------------------------------------------------------------------

def separar_chaves(bruto: str) -> list[str]:
    """Separa o campo `JARVIS_AI_API_KEY` (vírgula, `;`, `|`, espaço ou linha)."""
    vistas: set[str] = set()
    saida: list[str] = []
    for parte in re.split(r"[,;|\s]+", (bruto or "").strip()):
        parte = parte.strip()
        if parte and parte not in vistas:
            vistas.add(parte)
            saida.append(parte)
    return saida


def chaves_do_texto(texto: str) -> list[str]:
    """Acha chaves em qualquer texto colado, na ordem em que aparecem.

    É o que salva o caso real: o dono cola o bloco inteiro

        api grok 1 gsk_AAAA…
        api groq 2 gsk_BBBB…

    e o JARVIS guarda só as chaves — os rótulos são ignorados. Também aceita
    colagem só de chaves, separadas por vírgula ou por linha.
    """
    achadas: list[str] = []
    for padrao in PADROES_CHAVE:
        for achado in re.findall(padrao, texto or ""):
            if achado not in achadas:
                achadas.append(achado)
    # Ordem do texto, não ordem dos padrões: quem colou "gsk_, AIza" espera ver
    # as duas nessa ordem na máscara.
    posicoes = [(chave, (texto or "").find(chave)) for chave in achadas]
    posicoes.sort(key=lambda par: par[1] if par[1] >= 0 else 10**9)
    return [chave for chave, _ in posicoes]


def mascarar(chave: str) -> str:
    """`gsk_a…BkXV (56 caracteres)` — o suficiente para reconhecer, não para usar."""
    if len(chave) <= 10:
        return f"{chave[:2]}…{chave[-2:]}"
    return f"{chave[:5]}…{chave[-4:]} ({len(chave)} caracteres)"


# ---------------------------------------------------------------------------
# O arquivo .env
# ---------------------------------------------------------------------------

def _texto_atual() -> str:
    caminho = env_path()
    if caminho.is_file():
        return caminho.read_bytes().decode("utf-8", errors="replace")
    exemplo = dados_locais.PROJETO / ".env.example"
    if exemplo.is_file():
        return exemplo.read_bytes().decode("utf-8", errors="replace")
    return ""


def ler_valor(nome: str, texto: str | None = None) -> str:
    base = _texto_atual() if texto is None else texto
    for linha in re.split(r"\r?\n", base):
        limpa = linha.strip()
        if limpa.startswith("#") or "=" not in limpa:
            continue
        chave, _, valor = limpa.partition("=")
        if chave.strip() == nome:
            return valor.strip().strip('"').strip("'")
    return ""


def definir(texto: str, nome: str, valor: str) -> str:
    """Troca (ou acrescenta) uma variável, sem tocar no resto do arquivo."""
    linhas = re.split(r"\r?\n", texto)
    achou = False
    saida: list[str] = []
    for linha in linhas:
        limpa = linha.strip()
        chave = limpa.partition("=")[0].strip() if "=" in limpa and not limpa.startswith("#") else ""
        if chave == nome:
            saida.append(f"{nome}={valor}")
            achou = True
        else:
            saida.append(linha)
    if not achou:
        while saida and saida[-1].strip() == "":
            saida.pop()
        saida.append(f"{nome}={valor}")
    return "\r\n".join(saida).rstrip("\r\n") + "\r\n"


def gravar(texto: str) -> Path:
    """Escreve o `.env` em CRLF, sem BOM — como o Bloco de Notas antigo espera."""
    caminho = env_path()
    caminho.parent.mkdir(parents=True, exist_ok=True)
    normalizado = texto.replace("\r\n", "\n").replace("\r", "\n").replace("\n", "\r\n")
    caminho.write_bytes(normalizado.encode("utf-8"))
    return caminho


def aplicar_no_ambiente() -> None:
    """Põe o que está no `.env` em `os.environ` — inclusive vazio, para apagar.

    `load_dotenv` não serve aqui: ele não sobrescreve variável já definida, e é
    exatamente isso que precisa acontecer quando a chave muda com a API no ar.
    """
    for nome in CHAVES_IA:
        os.environ[nome] = ler_valor(nome) if env_path().is_file() else ""


# ---------------------------------------------------------------------------
# Estado
# ---------------------------------------------------------------------------

def estado() -> dict[str, Any]:
    """Quantas chaves, quais máscaras, e para onde a IA aponta. Nunca o valor."""
    from .ai import e_local  # noqa: PLC0415 (import tardio: ai puxa httpx)

    texto = _texto_atual()
    chaves = separar_chaves(ler_valor("JARVIS_AI_API_KEY", texto))
    base = ler_valor("JARVIS_AI_BASE_URL", texto)
    return {
        "quantidade": len(chaves),
        "mascaradas": [mascarar(chave) for chave in chaves],
        "provedor": ler_valor("JARVIS_AI_PROVIDER", texto),
        "base": base,
        "modelo": ler_valor("JARVIS_AI_MODEL", texto),
        "local": e_local(base),
        "arquivo": str(env_path()),
        "maximo": MAX_CHAVES,
    }


# ---------------------------------------------------------------------------
# Salvar e apagar
# ---------------------------------------------------------------------------

def _todos_groq(chaves: list[str]) -> bool:
    return bool(chaves) and all(chave.startswith("gsk_") for chave in chaves)


def salvar(texto_colado: str, acrescentar: bool = False) -> dict[str, Any]:
    """Extrai as chaves do texto colado, grava no `.env` e aplica na hora.

    `acrescentar=False` (padrão) **substitui** a lista: é o que a pessoa espera
    ao colar as três do zero. Com `acrescentar=True`, as novas entram depois das
    que já existem (sem repetir) — o caso de "comprei mais uma cota".
    """
    if len(texto_colado or "") > MAX_TEXTO:
        raise ValueError(
            f"o texto colado é grande demais ({len(texto_colado)} caracteres). "
            "Cole só as chaves, ou o arquivo com elas."
        )
    novas = chaves_do_texto(texto_colado)
    if not novas:
        raise ValueError(
            "não encontrei nenhuma chave no que foi colado. "
            "Ela começa com gsk_ (Groq), sk- (OpenAI/OpenRouter) ou AIza (Google)."
        )

    atual = _texto_atual()
    anteriores = separar_chaves(ler_valor("JARVIS_AI_API_KEY", atual))
    if acrescentar:
        juntas = anteriores + [chave for chave in novas if chave not in anteriores]
    else:
        juntas = list(novas)
    if len(juntas) > MAX_CHAVES:
        raise ValueError(
            f"são {len(juntas)} chaves; o limite é {MAX_CHAVES}. "
            "Mais que isso não aumenta cota de forma útil."
        )

    texto = atual
    valores = {"JARVIS_AI_API_KEY": ",".join(juntas)}
    # Endereço e modelo só entram se ainda não estiverem apontando para o Groq:
    # quem configurou OpenRouter de propósito não perde a configuração.
    if _todos_groq(juntas) and "groq.com" not in ler_valor("JARVIS_AI_BASE_URL", texto):
        valores.update(GROQ)
    for nome, valor in valores.items():
        texto = definir(texto, nome, valor)
    gravar(texto)
    aplicar_no_ambiente()

    resultado = estado()
    trocado = "groq.com" in (resultado["base"] or "")
    resultado["salvo"] = True
    resultado["novas"] = len(novas)
    resultado["acrescentou"] = acrescentar
    resultado["resumo"] = (
        f"{len(juntas)} chave(s) guardada(s) no .env"
        + (f", endereço e modelo do Groq preenchidos" if trocado and "JARVIS_AI_BASE_URL" in valores else "")
        + ". O JARVIS já está usando — nada de reiniciar."
    )
    return resultado


def apagar() -> dict[str, Any]:
    """Limpa a lista de chaves. Não mexe no provedor, no endereço nem no modelo."""
    texto = definir(_texto_atual(), "JARVIS_AI_API_KEY", "")
    gravar(texto)
    aplicar_no_ambiente()
    resultado = estado()
    resultado["apagado"] = True
    resultado["resumo"] = (
        "As chaves foram apagadas do .env. As skills locais continuam funcionando; "
        "o chat aberto para de responder até você colar outra."
    )
    return resultado


# ---------------------------------------------------------------------------
# Testar (fala com o provedor de verdade)
# ---------------------------------------------------------------------------

def testar(
    indice: int | None = None,
    limite: int = 45.0,
    postar: Any = None,
    modelo_socorro: str | None = None,
) -> dict[str, Any]:
    """Uma chamada real de 8 tokens por chave, na ordem, para dizer o que vale.

    `indice` (1-based) testa só uma — útil para conferir a que acabou de entrar.
    A resposta nunca contém a chave: só posição, se respondeu e o motivo.

    **Por que há um segundo teste com outro modelo (0.79.2).** No print do dono
    as quatro chaves falharam juntas e a tela dizia só *“nenhuma das 4 respondeu”*.
    Isso confunde duas causas muito diferentes:

    * a **chave** está inválida (401) — não adianta esperar, tem de trocar;
    * o **modelo** está no limite (429) — a chave é boa, só aquele modelo parou.

    Quando a primeira tentativa falha por 429 ou 404, a segunda usa um modelo com
    cota separada. Se ele responde, a chave está viva e o problema é o modelo:
    a resposta já diz qual usar. Custa 8 tokens, e só quando há falha.
    """
    valores = estado()
    chaves = separar_chaves(ler_valor("JARVIS_AI_API_KEY"))
    if not chaves:
        raise ValueError("não há chave guardada para testar")
    base = valores["base"] or "https://api.groq.com/openai/v1"
    modelo = valores["modelo"] or "llama-3.3-70b-versatile"
    socorro = modelo_socorro or MODELO_DE_SOCORRO
    # Só tenta o segundo modelo quando faz sentido: provedor Groq e modelo
    # diferente do atual. Num provedor alheio, o nome do socorro pode não existir.
    tentar_outro = bool(socorro) and socorro != modelo and "groq.com" in base

    escolhidas = list(enumerate(chaves, 1))
    if indice is not None:
        escolhidas = [(i, chave) for i, chave in escolhidas if i == indice]
        if not escolhidas:
            raise ValueError(f"não existe chave {indice}; há {len(chaves)}")

    resultados = []
    for posicao, chave in escolhidas:
        primeira = _testar_uma_detalhado(base, modelo, chave, limite, postar)
        codigo = int(primeira["codigo"])
        item: dict[str, Any] = {
            "indice": posicao,
            "ok": codigo == 200,
            "codigo": codigo,
            "motivo": primeira["motivo"],
            "detalhe": primeira["detalhe"],
            "modelo": modelo,
        }
        # Falhou por limite ou por modelo inexistente: a chave pode estar ótima.
        if codigo in (404, 429) and tentar_outro:
            segunda = _testar_uma_detalhado(base, socorro, chave, limite, postar)
            if int(segunda["codigo"]) == 200:
                item["ok"] = True
                item["codigo"] = codigo  # o código que a pessoa precisa ver
                item["chave_valida"] = True
                item["modelo_que_respondeu"] = socorro
                item["motivo"] = f"a chave é válida: só o modelo {modelo} está indisponível agora"
            else:
                item["chave_valida"] = False
                if segunda["detalhe"]:
                    item["detalhe"] = f"{item['detalhe']} | com {socorro}: {segunda['detalhe']}".strip(" |")
        resultados.append(item)

    boas = sum(1 for item in resultados if item["ok"])
    sugestao = next(
        (item["modelo_que_respondeu"] for item in resultados if item.get("modelo_que_respondeu")),
        None,
    )
    return {
        "ok": boas > 0,
        "resultados": resultados,
        "boas": boas,
        "total": len(resultados),
        "modelo": modelo,
        "modelo_sugerido": sugestao,
        "resumo": _resumo_teste(boas, len(resultados), resultados),
    }


def _resumo_teste(boas: int, total: int, resultados: list[dict[str, Any]] | None = None) -> str:
    """Diz o que aconteceu **e** o que fazer — separando chave, cota e modelo."""
    itens = resultados or []
    if total == 0:
        return "Nada para testar."

    # Antes de dizer “responderam”, é preciso dizer **com qual modelo**: se a
    # resposta só veio pelo modelo de socorro, o modelo configurado está fora do
    # ar — e o resumo tem de mandar trocar, não comemorar.
    via_socorro = [item for item in itens if item.get("modelo_que_respondeu")]
    diretas = sum(1 for item in itens if item.get("ok") and not item.get("modelo_que_respondeu"))
    if via_socorro and diretas == 0:
        modelo = via_socorro[0].get("modelo") or "o modelo atual"
        socorro = via_socorro[0]["modelo_que_respondeu"]
        quantas = "A chave é válida" if total == 1 else f"As {total} chaves são válidas"
        return (
            f"{quantas}: o modelo {modelo} é que está indisponível. "
            f"Troque para {socorro} no cartão Modelos de IA e a conversa volta."
        )

    if boas == total:
        return f"As {total} chaves responderam." if total > 1 else "A chave respondeu. O cérebro está de pé."

    codigos = {int(item.get("codigo") or 0) for item in itens}
    if codigos == {429}:
        return (
            f"As {total} chaves bateram no mesmo limite (HTTP 429). "
            "No Groq a cota é por conta, não por chave: chaves do mesmo login dividem a mesma cota. "
            "Troque de modelo (cada modelo tem cota própria) ou crie uma conta nova."
        )
    if codigos == {401} or codigos == {401, 403}:
        return (
            f"As {total} chaves foram recusadas (HTTP 401/403). Gere chaves novas em console.groq.com/keys "
            "e cole aqui de novo."
        )
    if codigos == {404}:
        return (
            "A chave não é o problema: o nome do modelo não existe no provedor (HTTP 404). "
            "Escolha outro no cartão Modelos de IA."
        )
    if boas == 0:
        detalhe = next((item.get("detalhe") for item in itens if item.get("detalhe")), "")
        if total > 1:
            return f"Nenhuma das {total} respondeu agora. {detalhe or 'Veja o motivo chave por chave.'}"
        return f"A chave não respondeu agora: {detalhe or 'veja o motivo acima.'}"
    return f"{boas} de {total} responderam — as outras ficam de reserva para quando faltar cota."


_MOTIVOS = {
    401: "chave recusada (HTTP 401) — copiada pela metade, revogada ou apagada no painel",
    403: "chave sem permissão para este modelo (HTTP 403)",
    404: "modelo não encontrado (HTTP 404) — esse nome não existe mais no provedor",
    413: "o pedido passou do limite do provedor (HTTP 413)",
    422: "o provedor recusou o formato (HTTP 422) — quase sempre o nome do modelo",
    429: "cota ou limite de requisições estourado (HTTP 429)",
}

# Modelo de socorro: tem a maior cota grátis do Groq. Serve para **separar** duas
# causas que dão o mesmo sintoma no teste: “a chave é inválida” e “este modelo
# está no limite”. Se a chave responde com ele, a chave está boa.
MODELO_DE_SOCORRO = "llama-3.1-8b-instant"

# O provedor devolve, no 429, o número exato do limite. Sem isso a pessoa lê
# “cota estourada” e não sabe se espera 30 s ou 8 h.
_RE_SEGUNDOS = re.compile(r"(?:try again|tente|retry) in ([0-9]+m?[0-9.]*s?)", re.I)
_RE_LIMITE = re.compile(r"(?:limit|limite)\s*[:=]?\s*([\d.,]+)", re.I)
_RE_USADO = re.compile(r"(?:used|usado)\s*[:=]?\s*([\d.,]+)", re.I)


def _limpar_mensagem(texto: str) -> str:
    """Mensagem do provedor, sem nada que possa ser chave ou endereço interno."""
    limpo = re.sub(r"(gsk_|sk-|AIza)[A-Za-z0-9_-]+", "[chave]", texto or "")
    limpo = re.sub(r"https?://\S+", "[endereço]", limpo)
    limpo = re.sub(r"\s+", " ", limpo).strip()
    return limpo[:400]


def _motivo_do_corpo(codigo: int, corpo: Any) -> str:
    """A frase que o provedor escreveu, traduzida para o que interessa.

    O Groq manda, no 429, algo como *“Rate limit reached for model `x` … on
    tokens per day (TPD): Limit 100000, Used 100000, try again in 12m34s”*. Isso
    é o dado que resolve o problema — guardar só “HTTP 429” foi o que fez o dono
    perguntar “e agora?” no print.
    """
    if not isinstance(corpo, dict):
        return ""
    erro = corpo.get("error") if isinstance(corpo.get("error"), dict) else {}
    mensagem = str(erro.get("message") or corpo.get("message") or "")
    if not mensagem:
        return ""
    mensagem = _limpar_mensagem(mensagem)
    pedacos: list[str] = []
    espera = _RE_SEGUNDOS.search(mensagem)
    if espera:
        pedacos.append(f"tente de novo em {espera.group(1)}")
    limite = _RE_LIMITE.search(mensagem)
    usado = _RE_USADO.search(mensagem)
    if limite and usado:
        # `[\d.,]+` pega a vírgula da frase junto com o número: limpa as pontas.
        teto = limite.group(1).rstrip(".,")
        gasto = usado.group(1).rstrip(".,")
        pedacos.append(f"limite {teto}, usado {gasto}")
    if codigo == 404:
        pedacos.append("confira o nome no cartão Modelos de IA")
    return " — ".join(pedacos) or mensagem


def _testar_uma_detalhado(
    base: str,
    modelo: str,
    chave: str,
    limite: float,
    postar: Any = None,
) -> dict[str, Any]:
    """Uma chamada real de 8 tokens. Devolve código, motivo e o que o provedor disse."""
    url = f"{base.rstrip('/')}/chat/completions"
    corpo = {
        "model": modelo,
        "messages": [{"role": "user", "content": "responda apenas: ok"}],
        "max_tokens": 8,
    }
    cabecalho = {"Authorization": f"Bearer {chave}", "Content-Type": "application/json"}

    if postar is not None:  # teste: não sai da máquina
        try:
            resposta = postar(url, corpo, cabecalho)
        except Exception as exc:  # noqa: BLE001 - qualquer falha vira motivo
            return {"codigo": 0, "motivo": f"falhou na conexão ({type(exc).__name__})", "detalhe": ""}
        if isinstance(resposta, dict):
            codigo = int(resposta.get("codigo") or resposta.get("status") or 0)
            corpo_resposta = resposta.get("corpo")
        else:
            codigo = int(resposta)
            corpo_resposta = None
        motivo = _MOTIVOS.get(codigo, f"respondeu HTTP {codigo}" if codigo != 200 else "respondeu")
        detalhe = _motivo_do_corpo(codigo, corpo_resposta) if codigo != 200 else ""
        return {"codigo": codigo, "motivo": motivo, "detalhe": detalhe}

    try:
        import httpx  # noqa: PLC0415 - só quem testa paga o import
    except ImportError:
        return {"codigo": 0, "motivo": "o pacote httpx não está instalado", "detalhe": ""}
    try:
        resposta = httpx.post(url, json=corpo, headers=cabecalho, timeout=limite)
    except Exception as exc:  # noqa: BLE001
        return {
            "codigo": 0,
            "motivo": f"falhou na conexão ({type(exc).__name__}) — internet ou provedor",
            "detalhe": "",
        }
    if resposta.status_code == 200:
        return {"codigo": 200, "motivo": "respondeu", "detalhe": ""}
    try:
        corpo_resposta = resposta.json()
    except Exception:  # noqa: BLE001 - corpo que não é JSON não ajuda em nada
        corpo_resposta = None
    return {
        "codigo": resposta.status_code,
        "motivo": _MOTIVOS.get(resposta.status_code, f"respondeu HTTP {resposta.status_code}"),
        "detalhe": _motivo_do_corpo(resposta.status_code, corpo_resposta),
    }


def _testar_uma(
    base: str,
    modelo: str,
    chave: str,
    limite: float,
    postar: Any = None,
) -> tuple[int, str]:
    """Forma curta de `_testar_uma_detalhado` — mantida para quem só quer o código."""
    detalhe = _testar_uma_detalhado(base, modelo, chave, limite, postar)
    motivo = detalhe["motivo"]
    if detalhe["detalhe"]:
        motivo = f"{motivo} — {detalhe['detalhe']}"
    return int(detalhe["codigo"]), motivo


# ---------------------------------------------------------------------------
# Linha de comando (o mesmo caminho da tela, para script e teste)
# ---------------------------------------------------------------------------

def _cli(argv: list[str] | None = None) -> int:
    import argparse  # noqa: PLC0415
    import json  # noqa: PLC0415

    parser = argparse.ArgumentParser(description="Chaves de IA do JARVIS (as mesmas da tela).")
    parser.add_argument("--estado", action="store_true")
    parser.add_argument("--salvar", metavar="TEXTO", default="")
    parser.add_argument("--arquivo", metavar="CAMINHO", default="")
    parser.add_argument("--acrescentar", action="store_true")
    parser.add_argument("--apagar", action="store_true")
    parser.add_argument("--testar", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    try:
        if args.arquivo:
            colado = Path(args.arquivo).read_bytes().decode("utf-8", errors="replace")
            dados = salvar(colado, acrescentar=args.acrescentar)
        elif args.salvar:
            dados = salvar(args.salvar, acrescentar=args.acrescentar)
        elif args.apagar:
            dados = apagar()
        elif args.testar:
            dados = testar()
        else:
            dados = estado()
    except (ValueError, OSError) as exc:
        print(f"  Falhou: {exc}")
        return 1

    if args.json:
        print(json.dumps(dados, ensure_ascii=False, indent=2))
        return 0
    if dados.get("resumo"):
        print(f"  {dados['resumo']}")
    for item in dados.get("resultados") or []:
        estado_ = "OK  " if item["ok"] else "FALHA"
        print(f"  {estado_} chave {item['indice']}: {item['motivo']}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(_cli())
