"""Criar chave do OpenRouter por HTTPS, sem navegador (0.91.29).

Por que existe. O caminho bonito da 0.91.27 (controlar o Chrome pelo protocolo
dele) funciona — mas o Chrome do JARVIS é um perfil novo, sem cache, e no PC do
dono ele demora a abrir a página. Esperar 90 s funciona; não é bom.

O OpenRouter tem uma porta de serviço: a **chave de gestão** (management /
provisioning key). Ela não serve para conversar com o modelo; ela serve para
criar outras chaves. Com ela, criar uma chave é um `POST` e uma resposta:
nenhuma janela, nenhuma página, nenhuma espera.

    POST https://openrouter.ai/api/v1/keys
    Authorization: Bearer <chave de gestão>
    {"name": "jarvis-2026-11-16"}

    → {"data": {...}, "key": "sk-or-v1-…"}

O `POST` devolve a chave **uma única vez** (o site diz o mesmo); não há como
buscá-la depois. Por isso quem chama grava na hora.

O que este módulo garante, e é o que dá para garantir sem o PC do dono:

- os erros chegam em português e dizem o que fazer (401 = chave de gestão
  errada, 403 = a chave não tem permissão de criar, 429 = muitos pedidos);
- nada é inventado: sem campo `key` na resposta, é erro;
- a mesma função serve para **testar** uma chave de gestão antes de gravar.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any, Callable

BASE_PADRAO = "https://openrouter.ai/api/v1"
SEGUNDOS = 30.0


class OpenRouterError(RuntimeError):
    """Falou com o OpenRouter e deu errado — com o motivo em português."""


def _abrir_padrao(pedido: urllib.request.Request, segundos: float = SEGUNDOS):
    return urllib.request.urlopen(pedido, timeout=segundos)  # noqa: S310 - endereço fixo do OpenRouter


def _pedir(
    metodo: str,
    caminho: str,
    gestao: str,
    *,
    corpo: dict[str, Any] | None = None,
    base: str = BASE_PADRAO,
    abrir: Callable[..., Any] | None = None,
    segundos: float = SEGUNDOS,
) -> dict[str, Any]:
    """Um pedido autenticado. Devolve o JSON; levanta `OpenRouterError` no resto."""
    abrir = abrir or _abrir_padrao
    dados = json.dumps(corpo).encode("utf-8") if corpo is not None else None
    pedido = urllib.request.Request(
        f"{base.rstrip('/')}/{caminho.lstrip('/')}",
        data=dados,
        method=metodo,
        headers={
            "Authorization": f"Bearer {gestao}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            # O OpenRouter pede isto nas chamadas de fora do navegador.
            "HTTP-Referer": "https://github.com/vitor120956-max/Victor-Alexandre-",
            "X-Title": "JARVIS",
        },
    )
    try:
        with abrir(pedido, segundos) as resposta:
            bruto = resposta.read()
    except urllib.error.HTTPError as exc:
        raise OpenRouterError(_explicar(exc.code, _corpo_do_erro(exc))) from exc
    except urllib.error.URLError as exc:
        raise OpenRouterError(
            f"não consegui falar com o OpenRouter ({exc.reason}). "
            "Confira a internet e rode de novo."
        ) from exc
    except TimeoutError as exc:
        raise OpenRouterError("o OpenRouter demorou demais para responder. Rode de novo.") from exc
    except OSError as exc:  # inclui erro de certificado
        raise OpenRouterError(f"a conexão com o OpenRouter falhou ({exc}).") from exc
    try:
        return json.loads(bruto.decode("utf-8", "replace"))
    except ValueError as exc:
        raise OpenRouterError("o OpenRouter respondeu algo que não é JSON.") from exc


def _corpo_do_erro(exc: urllib.error.HTTPError) -> str:
    try:
        bruto = exc.read()
    except Exception:  # noqa: BLE001 - corpo ilegível não é o problema principal
        return ""
    try:
        dados = json.loads(bruto.decode("utf-8", "replace"))
    except ValueError:
        return bruto.decode("utf-8", "replace")[:300]
    if isinstance(dados, dict):
        erro = dados.get("error")
        if isinstance(erro, dict):
            return str(erro.get("message") or erro.get("code") or "")[:300]
        if erro:
            return str(erro)[:300]
        if dados.get("message"):
            return str(dados["message"])[:300]
    return json.dumps(dados, ensure_ascii=False)[:300]


def _explicar(codigo: int, detalhe: str) -> str:
    """O código HTTP em uma frase que diz o que fazer."""
    if codigo == 401:
        return (
            "o OpenRouter não aceitou essa chave de gestão (401). "
            "Confira se ela foi copiada inteira e se ainda existe na página "
            "openrouter.ai/settings/management-keys."
        )
    if codigo == 403:
        return (
            "essa chave não pode criar outras chaves (403). Ela é uma chave comum, "
            "não a de gestão: a de gestão é criada em openrouter.ai/settings/management-keys."
        )
    if codigo == 429:
        return "o OpenRouter pediu para esperar um pouco (429). Rode de novo em um minuto."
    if codigo >= 500:
        return f"o OpenRouter está com problema no servidor ({codigo}). Tente mais tarde."
    extra = f" — {detalhe}" if detalhe else ""
    return f"o OpenRouter recusou o pedido ({codigo}){extra}"


def listar_chaves(
    gestao: str,
    *,
    base: str = BASE_PADRAO,
    abrir: Callable[..., Any] | None = None,
    segundos: float = SEGUNDOS,
) -> list[dict[str, Any]]:
    """As chaves da conta. Também é o teste de “esta chave de gestão vale?”."""
    dados = _pedir("GET", "keys", gestao, base=base, abrir=abrir, segundos=segundos)
    chaves = dados.get("data")
    if isinstance(chaves, list):
        return [item for item in chaves if isinstance(item, dict)]
    if isinstance(chaves, dict) and isinstance(chaves.get("keys"), list):
        return [item for item in chaves["keys"] if isinstance(item, dict)]
    return []


def chave_de_gestao_vale(
    gestao: str,
    *,
    base: str = BASE_PADRAO,
    abrir: Callable[..., Any] | None = None,
    segundos: float = SEGUNDOS,
) -> tuple[bool, str]:
    """(vale?, motivo). Ler a lista é o teste mais barato que existe."""
    try:
        listar_chaves(gestao, base=base, abrir=abrir, segundos=segundos)
    except OpenRouterError as exc:
        return False, str(exc)
    return True, ""


def criar_chave(
    gestao: str,
    nome: str,
    *,
    limite: float | None = None,
    expira_em: str | None = None,
    base: str = BASE_PADRAO,
    abrir: Callable[..., Any] | None = None,
    segundos: float = SEGUNDOS,
) -> str:
    """Cria a chave e devolve o texto dela. Levanta `OpenRouterError` se não der.

    Sem `limite` e sem `expira_em`, a chave nasce **sem limite e sem validade** —
    que é exatamente o que o dono pediu (“sem limite e sem tempo de expiração”).
    """
    corpo: dict[str, Any] = {"name": nome}
    if limite is not None:
        corpo["limit"] = limite
    if expira_em:
        corpo["expires_at"] = expira_em
    dados = _pedir("POST", "keys", gestao, corpo=corpo, base=base, abrir=abrir, segundos=segundos)
    chave = dados.get("key")
    if not isinstance(chave, str) or not chave.strip():
        # A resposta trazer `data` sem `key` quer dizer que a chave foi criada
        # mas não veio — não dá para gravar o que não se tem.
        raise OpenRouterError(
            "o OpenRouter respondeu sem a chave. Se ela foi criada mesmo, "
            "aparece na lista do site; rode de novo para criar outra."
        )
    return chave.strip()
