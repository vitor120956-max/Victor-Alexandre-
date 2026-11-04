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
) -> dict[str, Any]:
    """Uma chamada real de 8 tokens por chave, na ordem, para dizer o que vale.

    `indice` (1-based) testa só uma — útil para conferir a que acabou de entrar.
    A resposta nunca contém a chave: só posição, se respondeu e o motivo.
    """
    valores = estado()
    chaves = separar_chaves(ler_valor("JARVIS_AI_API_KEY"))
    if not chaves:
        raise ValueError("não há chave guardada para testar")
    base = valores["base"] or "https://api.groq.com/openai/v1"
    modelo = valores["modelo"] or "llama-3.3-70b-versatile"

    escolhidas = list(enumerate(chaves, 1))
    if indice is not None:
        escolhidas = [(i, chave) for i, chave in escolhidas if i == indice]
        if not escolhidas:
            raise ValueError(f"não existe chave {indice}; há {len(chaves)}")

    resultados = []
    for posicao, chave in escolhidas:
        codigo, detalhe = _testar_uma(base, modelo, chave, limite, postar)
        resultados.append({"indice": posicao, "ok": codigo == 200, "codigo": codigo, "motivo": detalhe})

    boas = sum(1 for item in resultados if item["ok"])
    return {
        "ok": boas > 0,
        "resultados": resultados,
        "boas": boas,
        "total": len(resultados),
        "resumo": _resumo_teste(boas, len(resultados)),
    }


def _resumo_teste(boas: int, total: int) -> str:
    if total == 0:
        return "Nada para testar."
    if boas == total:
        return f"As {total} chaves responderam." if total > 1 else "A chave respondeu. O cérebro está de pé."
    if boas == 0:
        return (
            f"Nenhuma das {total} respondeu agora. "
            "Se todas deram 429, a cota do dia acabou; se deram 401, gere chaves novas."
            if total > 1
            else "A chave não respondeu agora. Veja o motivo acima."
        )
    return f"{boas} de {total} responderam — as outras ficam de reserva para quando faltar cota."


_MOTIVOS = {
    401: "chave recusada (HTTP 401) — copiada pela metade ou apagada no painel",
    403: "chave sem permissão para este modelo (HTTP 403)",
    404: "modelo não encontrado (HTTP 404) — o nome muda com o tempo",
    422: "o provedor recusou o formato (HTTP 422) — provavelmente o modelo",
    429: "cota ou limite de requisições estourado (HTTP 429)",
}


def _testar_uma(
    base: str,
    modelo: str,
    chave: str,
    limite: float,
    postar: Any = None,
) -> tuple[int, str]:
    url = f"{base.rstrip('/')}/chat/completions"
    corpo = {
        "model": modelo,
        "messages": [{"role": "user", "content": "responda apenas: ok"}],
        "max_tokens": 8,
    }
    cabecalho = {"Authorization": f"Bearer {chave}", "Content-Type": "application/json"}

    if postar is not None:  # teste: não sai da máquina
        try:
            codigo = postar(url, corpo, cabecalho)
        except Exception as exc:  # noqa: BLE001 - qualquer falha vira motivo
            return 0, f"falhou na conexão ({type(exc).__name__})"
        return int(codigo), _MOTIVOS.get(int(codigo), f"respondeu HTTP {codigo}" if int(codigo) != 200 else "respondeu")

    try:
        import httpx  # noqa: PLC0415 - só quem testa paga o import
    except ImportError:
        return 0, "o pacote httpx não está instalado"
    try:
        resposta = httpx.post(url, json=corpo, headers=cabecalho, timeout=limite)
    except Exception as exc:  # noqa: BLE001
        return 0, f"falhou na conexão ({type(exc).__name__}) — internet ou provedor"
    if resposta.status_code == 200:
        return 200, "respondeu"
    return resposta.status_code, _MOTIVOS.get(resposta.status_code, f"respondeu HTTP {resposta.status_code}")


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
