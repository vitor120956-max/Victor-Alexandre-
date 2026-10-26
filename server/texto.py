"""Normalização de texto compartilhada: minúscula, sem acento, sem palavra vazia.

Estava duplicada dentro do agente local; a biblioteca precisa da mesma regra para
que "Contabilidade" no livro e "contabilidade" no pedido caiam no mesmo lugar.
"""
from __future__ import annotations

import re
import unicodedata

# Palavras que não ajudam a distinguir um assunto de outro.
PARADAS = frozenset(
    {
        "a", "o", "e", "de", "do", "da", "dos", "das", "um", "uma", "uns", "umas",
        "para", "com", "em", "no", "na", "nos", "nas", "que", "se", "por", "como",
        "mais", "menos", "seu", "sua", "seus", "suas", "ao", "aos", "as", "os",
        "voce", "vc", "eu", "me", "minha", "meu", "isso", "este", "esta", "esse",
        "essa", "tem", "ter", "foi", "ser", "sao", "ja", "nao", "sim", "muito",
        "pode", "quero", "queria", "gostaria", "favor", "por", "entao", "aqui",
    }
)


def normalizar(texto: str) -> str:
    """Minúsculas, sem acento e com espaço simples — a forma de comparar."""
    decomposto = unicodedata.normalize("NFKD", texto or "")
    sem_acento = "".join(caractere for caractere in decomposto if not unicodedata.combining(caractere))
    return re.sub(r"\s+", " ", sem_acento.lower()).strip()


def palavras(texto: str) -> list[str]:
    """Palavras úteis (3+ letras, fora as vazias), sem repetição."""
    vistas: list[str] = []
    for palavra in re.findall(r"[a-z0-9]+", normalizar(texto)):
        if len(palavra) >= 3 and palavra not in PARADAS and palavra not in vistas:
            vistas.append(palavra)
    return vistas


def todas_as_palavras(texto: str) -> list[str]:
    """Como `palavras`, mas mantendo repetição — para contar frequência."""
    return [
        palavra
        for palavra in re.findall(r"[a-z0-9]+", normalizar(texto))
        if len(palavra) >= 3 and palavra not in PARADAS
    ]


def frases(texto: str) -> list[str]:
    """Quebra em frases aproveitáveis, cortando espaço e markdown solto."""
    pedacos = re.split(r"(?<=[.!?])\s+|\n{2,}", texto or "")
    return [re.sub(r"\s+", " ", pedaco).strip() for pedaco in pedacos if len(pedaco.strip()) >= 30]
