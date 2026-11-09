"""Conectores por token: Notion, Linear, Dropbox, Vercel e Supabase (0.82.0).

## “Não tem como criar conectores igual ao do Arena?”

Tem — mas é preciso separar duas coisas que parecem iguais e não são:

- **OAuth** (o que o Arena usa): o serviço devolve um token depois que você
  autoriza no navegador. Para isso alguém precisa ter registrado um aplicativo
  no serviço — no caso do Arena, o time dele. No seu PC, esse aplicativo teria
  de ser registrado **por você**.
- **Token pessoal** (o que este módulo faz): Notion, Linear, Dropbox, Vercel e
  Supabase deixam você criar uma chave no painel e colar. O resultado é o mesmo
  — o JARVIS fala com o serviço em seu nome — sem passar por cadastro de
  aplicativo, sem tela de consentimento e sem servidor no meio.

Ou seja: **os conectores existem. O que muda é quem cria a credencial.** Aqui, é
você, em 1 minuto por serviço, e a chave fica só no `.env` desta máquina.

## O que este módulo garante

- o token **nunca** volta numa resposta: o estado mostra só `sk-…abcd`;
- cada conector tem um **teste de verdade** (uma chamada de leitura que prova
  que o token funciona), e a frase de erro diz o que fazer;
- nada é gravado fora do `.env`; `esquecer` apaga só aquela chave.

## O que ele ainda não faz

Ações de cada serviço (listar páginas do Notion, criar tarefa no Linear…)
dependem de qual serviço você quer usar primeiro. O teste e o estado vêm antes
de propósito: primeiro provar que a porta abre, depois construir a sala.
"""
from __future__ import annotations

import os
from typing import Any, Callable

from . import chaves as chaves_mod

# Como cada serviço autentica e como provar que o token vale.
# `teste` é uma leitura barata (perfil/conta), não uma escrita.
PROVEDORES: dict[str, dict[str, Any]] = {
    "notion": {
        "nome": "Notion",
        "onde": "notion.so/my-integrations → New integration → copie o “Internal Integration Secret”",
        "variavel": "JARVIS_CONECTOR_NOTION",
        "teste": ("GET", "https://api.notion.com/v1/users/me", {"Notion-Version": "2022-06-28"}),
        "leitura": "workspace e pessoa dona do token",
        "extra": "",
    },
    "linear": {
        "nome": "Linear",
        "onde": "linear.app/settings/api → Personal API keys",
        "variavel": "JARVIS_CONECTOR_LINEAR",
        # A Linear usa GraphQL: o teste é uma consulta que só lê o próprio perfil.
        "teste": (
            "POST",
            "https://api.linear.app/graphql",
            {},
            {"query": "{ viewer { name email } }"},
        ),
        "leitura": "nome e e-mail da conta",
        "extra": "",
    },
    "dropbox": {
        "nome": "Dropbox",
        "onde": "dropbox.com/developers/apps → Create app → Generated access token",
        "variavel": "JARVIS_CONECTOR_DROPBOX",
        "teste": ("POST", "https://api.dropboxapi.com/2/users/get_current_account", {}, {}),
        "leitura": "nome da conta e espaço usado",
        "extra": "Token gerado no painel expira em algumas horas; para durar, use “App folder” com refresh token.",
    },
    "vercel": {
        "nome": "Vercel",
        "onde": "vercel.com/account/tokens → Create",
        "variavel": "JARVIS_CONECTOR_VERCEL",
        "teste": ("GET", "https://api.vercel.com/v2/user", {}),
        "leitura": "usuário e times",
        "extra": "",
    },
    "supabase": {
        "nome": "Supabase",
        "onde": "supabase.com/dashboard → seu projeto → Settings → API → service_role key",
        "variavel": "JARVIS_CONECTOR_SUPABASE",
        # Sem o endereço do projeto não há como testar: ele entra junto.
        "teste": ("GET", "", {}),
        "leitura": "tabelas do projeto (precisa do endereço do projeto)",
        "extra": "A service_role ignora as regras de acesso. Use só em projeto seu.",
        "precisa_endereco": True,
    },
}

VAR_ENDERECO = "JARVIS_CONECTOR_SUPABASE_URL"


class TokenError(ValueError):
    """Token vazio, serviço desconhecido, ou o serviço recusou — com frase útil."""


# ---------------------------------------------------------------------------
# Guardar e ler
# ---------------------------------------------------------------------------

def _texto() -> str:
    return chaves_mod._texto_atual()  # noqa: SLF001 - o `.env` é o mesmo arquivo


def _gravar(**valores: str) -> None:
    texto = _texto()
    for nome, valor in valores.items():
        texto = chaves_mod.definir(texto, nome, valor)
    chaves_mod.gravar(texto)
    for nome in valores:
        os.environ[nome] = chaves_mod.ler_valor(nome)


def _token(identificador: str) -> str:
    dados = PROVEDORES[identificador]
    return (chaves_mod.ler_valor(dados["variavel"]) or os.environ.get(dados["variavel"], "")).strip()


def mascarar(token: str) -> str:
    """Mesmo cuidado das chaves de IA: começo e fim, nunca o miolo."""
    limpo = (token or "").strip()
    if not limpo:
        return ""
    if len(limpo) <= 10:
        return limpo[:2] + "…"
    return f"{limpo[:4]}…{limpo[-4:]} ({len(limpo)} caracteres)"


def conferir(identificador: str, token: str, endereco: str = "") -> None:
    """Recusa antes de gravar: serviço conhecido, token com cara de token."""
    if identificador not in PROVEDORES:
        raise TokenError("serviço desconhecido: use " + ", ".join(PROVEDORES) + ".")
    limpo = (token or "").strip()
    if len(limpo) < 12:
        raise TokenError(
            f"o token do {PROVEDORES[identificador]['nome']} parece curto demais. "
            f"Copie o valor inteiro em: {PROVEDORES[identificador]['onde']}."
        )
    if any(caractere.isspace() for caractere in limpo):
        raise TokenError("o token tem espaço no meio — copie de novo, sem quebra de linha.")
    if PROVEDORES[identificador].get("precisa_endereco"):
        alvo = (endereco or "").strip()
        if not alvo.startswith("https://") or ".supabase.co" not in alvo:
            raise TokenError(
                "para o Supabase diga o endereço do projeto (https://xxxx.supabase.co) — "
                "ele aparece em Settings → API, ao lado das chaves."
            )


def configurar(identificador: str, token: str, endereco: str = "") -> dict[str, Any]:
    """Grava o token no `.env`. Devolve o estado, nunca o token."""
    conferir(identificador, token, endereco)
    dados = PROVEDORES[identificador]
    valores = {dados["variavel"]: token.strip()}
    if dados.get("precisa_endereco"):
        valores[VAR_ENDERECO] = endereco.strip().rstrip("/")
    _gravar(**valores)
    return {**estado(), "salvo": identificador}


def esquecer(identificador: str) -> dict[str, Any]:
    if identificador not in PROVEDORES:
        raise TokenError("serviço desconhecido.")
    _gravar(**{PROVEDORES[identificador]["variavel"]: ""})
    return {**estado(), "apagado": identificador}


def estado() -> dict[str, Any]:
    """Quem está ligado: nome, onde pegar o token, e a máscara do que existe."""
    itens = []
    for identificador, dados in PROVEDORES.items():
        token = _token(identificador)
        item = {
            "id": identificador,
            "nome": dados["nome"],
            "onde": dados["onde"],
            "leitura": dados["leitura"],
            "extra": dados.get("extra", ""),
            "pronto": bool(token),
            "mascara": mascarar(token),
            "precisa_endereco": bool(dados.get("precisa_endereco")),
        }
        if dados.get("precisa_endereco"):
            item["endereco"] = chaves_mod.ler_valor(VAR_ENDERECO) or ""
        itens.append(item)
    prontos = sum(1 for item in itens if item["pronto"])
    return {
        "tokens": itens,
        "prontos": prontos,
        "total": len(itens),
        "resumo": f"{prontos} de {len(itens)} conectores por token ligados.",
        "nota": (
            "Token pessoal é o mesmo que OAuth sem o aplicativo no meio: você cria a chave no "
            "painel do serviço e cola aqui. Ela fica só no .env desta máquina."
        ),
    }


# ---------------------------------------------------------------------------
# Teste de verdade
# ---------------------------------------------------------------------------

def _pedir_httpx(metodo: str, url: str, cabecalho: dict[str, str], corpo: Any, tempo: float) -> Any:
    import httpx  # noqa: PLC0415 (só quem testa paga o custo)

    if metodo == "GET":
        return httpx.get(url, headers=cabecalho, timeout=tempo)
    return httpx.post(url, headers=cabecalho, json=corpo or {}, timeout=tempo)


def testar(
    identificador: str,
    *,
    pedir: Callable[[str, str, dict[str, str], Any, float], Any] | None = None,
    tempo: float = 12.0,
) -> dict[str, Any]:
    """Uma chamada de leitura de verdade: prova que o token abre a porta."""
    if identificador not in PROVEDORES:
        raise TokenError("serviço desconhecido.")
    dados = PROVEDORES[identificador]
    token = _token(identificador)
    if not token:
        raise TokenError(
            f"o {dados['nome']} ainda não está ligado — cole o token primeiro "
            f"(ele sai em: {dados['onde']})."
        )

    metodo, url = dados["teste"][0], dados["teste"][1]
    extra = dados["teste"][2] if len(dados["teste"]) > 2 else {}
    corpo = dados["teste"][3] if len(dados["teste"]) > 3 else None

    cabecalho = {"Content-Type": "application/json", **extra}
    if identificador == "linear":
        cabecalho["Authorization"] = token  # a Linear não usa “Bearer”
    elif identificador == "supabase":
        endereco = (os.environ.get(VAR_ENDERECO) or chaves_mod.ler_valor(VAR_ENDERECO) or "").rstrip("/")
        if not endereco:
            raise TokenError("falta o endereço do projeto Supabase.")
        url = f"{endereco}/rest/v1/"
        cabecalho["apikey"] = token
        cabecalho["Authorization"] = f"Bearer {token}"
    else:
        cabecalho["Authorization"] = f"Bearer {token}"

    enviar = pedir or _pedir_httpx
    try:
        resposta = enviar(metodo, url, cabecalho, corpo, tempo)
    except Exception as exc:  # noqa: BLE001 - rede é imprevisível
        raise TokenError(
            f"não consegui falar com o {dados['nome']} ({type(exc).__name__}) — internet ou serviço fora do ar."
        ) from exc

    codigo = int(getattr(resposta, "status_code", 0) or 0)
    if codigo in (401, 403):
        raise TokenError(
            f"o {dados['nome']} recusou o token (HTTP {codigo}). Gere outro em: {dados['onde']}."
        )
    if codigo == 404:
        raise TokenError(
            f"o endereço do {dados['nome']} não respondeu (HTTP 404) — confira o endereço do projeto."
        )
    if codigo >= 400:
        raise TokenError(f"o {dados['nome']} respondeu HTTP {codigo}.")

    try:
        conteudo = resposta.json()
    except Exception:  # noqa: BLE001 - resposta vazia é sucesso em alguns serviços
        conteudo = {}

    return {
        "ok": True,
        "conector": identificador,
        "nome": dados["nome"],
        "resumo": f"{dados['nome']} respondeu: o token vale e dá acesso a {dados['leitura']}.",
        "perfil": _perfil(identificador, conteudo),
    }


def _perfil(identificador: str, corpo: Any) -> str:
    """Um nome legível do que respondeu — nunca o token, nunca dado sensível."""
    if not isinstance(corpo, dict):
        return ""
    if identificador == "notion":
        dono = corpo.get("bot") or corpo.get("owner") or {}
        return str(dono.get("workspace_name") or corpo.get("name") or "")[:80]
    if identificador == "linear":
        pessoa = ((corpo.get("data") or {}).get("viewer") or {})
        return str(pessoa.get("name") or pessoa.get("email") or "")[:80]
    if identificador == "dropbox":
        return str(corpo.get("name", {}).get("display_name") or "")[:80] if isinstance(corpo.get("name"), dict) else ""
    if identificador == "vercel":
        return str(corpo.get("user", {}).get("username") or corpo.get("username") or "")[:80]
    return ""


def resumo_json(estado_atual: dict[str, Any]) -> str:
    """Texto curto para o chat, sem nenhum token."""
    if not estado_atual.get("prontos"):
        return "Nenhum conector por token ligado ainda."
    ligados = [item["nome"] for item in estado_atual.get("tokens") or [] if item.get("pronto")]
    return f"Ligados: {', '.join(ligados)}. " + str(estado_atual.get("resumo") or "")

