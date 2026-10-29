"""Comparação de token de host — sem estourar com acento.

O problema real: `hmac.compare_digest` aceita `str`, mas **levanta TypeError** se
qualquer um dos lados tiver caractere fora de ASCII:

    >>> hmac.compare_digest("abc", "não")
    TypeError: comparing strings with non-ASCII characters is not supported

Isso virava uma mensagem em inglês no meio do chat ("comparing strings with
non-ASCII characters is not supported") em vez de "token errado". Token de host é
gerado por `secrets.token_urlsafe`, então é sempre ASCII: qualquer valor com
acento é, por definição, entrada errada — e a resposta certa é recusar, não cair.

Além da comparação, este módulo explica **por que** o valor não serve, para a
mensagem poder dizer o que fazer.
"""
from __future__ import annotations

import hmac
import re

# token_urlsafe usa A-Z a-z 0-9 - _ ; o teto evita colar um texto gigante
_PLAUSIVEL = re.compile(r"^[A-Za-z0-9_-]{8,200}$")


def tem_fora_de_ascii(texto: str) -> bool:
    """Verdadeiro quando existe acento, cedilha ou qualquer símbolo não-ASCII."""
    return any(ord(caractere) > 127 for caractere in (texto or ""))


def parece_token(texto: str) -> bool:
    """Formato que um token de host pode ter (`token_urlsafe`)."""
    return bool(_PLAUSIVEL.match((texto or "").strip()))


def iguais(informado: str, esperado: str) -> bool:
    """Compara em tempo constante, sem levantar exceção com entrada estranha.

    Converte para bytes: `compare_digest` com bytes nunca reclama de non-ASCII, e a
    comparação continua em tempo constante, que é o motivo de usar `compare_digest`.
    """
    a = (informado or "").strip().encode("utf-8", "surrogatepass")
    b = (esperado or "").strip().encode("utf-8", "surrogatepass")
    try:
        return hmac.compare_digest(a, b)
    except (TypeError, ValueError):  # defesa extra: nunca derruba a requisição
        return False


def explicar(
    informado: str,
    *,
    modo_dono: bool = False,
    da_propria_maquina: bool = False,
    automatico_local: bool = False,
    trava_local: bool = False,
) -> str:
    """Mensagem acionável para um token recusado.

    O caso mais comum de longe é o dono do projeto na própria máquina: a partir
    da 0.61.7 o token nem é pedido ali, então "recusou" quase sempre significa
    que o pedido veio de fora — e a mensagem precisa dizer isso, não mandar
    configurar o que já está configurado.
    """
    valor = (informado or "").strip()
    if not valor:
        if trava_local:
            return (
                "Token vazio. `JARVIS_HOST_EXIGIR_TOKEN_LOCAL=1` está ligado, então "
                "até nesta máquina o token é pedido: copie o valor de "
                "storage/host-token.txt."
            )
        if da_propria_maquina:
            return "Token vazio. Cole o valor de storage/host-token.txt."
        if automatico_local or modo_dono:
            return (
                "Sem token e este pedido não veio da própria máquina. Em 127.0.0.1 ele "
                "é preenchido sozinho; de outra máquina, cole o valor de "
                "storage/host-token.txt."
            )
        return (
            "Sem token. Na sua máquina ele é preenchido sozinho — reinicie a API para "
            "carregar o .env atualizado. De outra máquina, cole o valor de "
            "storage/host-token.txt."
        )
    if tem_fora_de_ascii(valor):
        return (
            "Isso não é um token: o valor tem acento ou símbolo. Token de host é só "
            "letras, números, hífen e sublinhado — copie o conteúdo de "
            "storage/host-token.txt."
        )
    if not parece_token(valor):
        return (
            "Isso não parece um token de host (curto demais ou com espaço). Copie o "
            "conteúdo de storage/host-token.txt, que aparece no terminal quando a API sobe."
        )
    return "Token de host inválido. Confira o valor em storage/host-token.txt."
