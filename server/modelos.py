"""Catálogo de modelos de IA — qual cérebro o JARVIS usa e como trocar.

## O que é “modelo”, dito sem rodeio

Chave é a **entrada**; modelo é o **cérebro** que responde. A mesma chave do Groq
dá acesso a vários modelos, e a diferença entre eles é sempre a mesma troca:
**qualidade × velocidade × quanto dura a cota grátis**.

- modelo **grande** (70B, 120B): entende melhor frases tortas e mantém o fio da
  conversa; gasta mais cota por resposta e é mais lento;
- modelo **pequeno** (8B, 20B): responde quase instantâneo e rende muito mais
  pedidos por dia; erra mais em pedido confuso.

Não existe “o melhor”: existe o melhor para o uso de cada um. Por isso este
módulo lista o que dá para escolher, diz **para que serve cada um** e grava a
escolha no `.env` — sem ninguém decorar nome de modelo.

## Honestidade sobre a lista

Os números de cota abaixo são os publicados pelo provedor e **mudam**. A lista é
um atalho, não uma promessa: o campo aceita qualquer nome de modelo que a conta
tenha. Se um nome sair do ar, o erro do provedor (HTTP 404) aparece na hora em
que a pessoa testar — e o botão **Testar** diz isso sem enrolação.
"""
from __future__ import annotations

import re
from typing import Any

from . import chaves, provedores

MODELO_PADRAO = "llama-3.3-70b-versatile"

# Ordem: do mais equilibrado para os extremos. `quando` é a frase que aparece na
# tela — em português, curta, e dizendo o custo, não só a virtude.
CATALOGO: list[dict[str, str]] = [
    {
        "id": "llama-3.3-70b-versatile",
        "nome": "Llama 3.3 70B",
        "perfil": "equilíbrio",
        "quando": "O padrão. Entende bem frase torta e mantém a conversa. Cota grátis menor (uns 1.000 pedidos por dia).",
    },
    {
        "id": "llama-3.1-8b-instant",
        "nome": "Llama 3.1 8B Instant",
        "perfil": "rápido e resistente",
        "quando": "Resposta quase instantânea e a maior cota grátis do Groq (uns 14.400 pedidos por dia). Erra mais em pedido confuso.",
    },
    {
        "id": "openai/gpt-oss-120b",
        "nome": "GPT-OSS 120B",
        "perfil": "qualidade",
        "quando": "O mais forte dos abertos no Groq. Melhor raciocínio, mais lento e cota diária média (uns 200 mil tokens).",
    },
    {
        "id": "openai/gpt-oss-20b",
        "nome": "GPT-OSS 20B",
        "perfil": "rápido",
        "quando": "Bom meio-termo: rápido, esperto o suficiente e com a mesma cota diária do 120B.",
    },
    {
        "id": "meta-llama/llama-4-scout-17b-16e-instruct",
        "nome": "Llama 4 Scout 17B",
        "perfil": "texto grande",
        "quando": "Aguenta documento enorme na mesma conversa e tem cota diária generosa. Bom para ler arquivo longo.",
    },
    {
        "id": "qwen/qwen3-32b",
        "nome": "Qwen3 32B",
        "perfil": "raciocínio",
        "quando": "Forte em conta e passo a passo; pode pensar antes de responder, então é mais lento.",
    },
]

_ID_VALIDO = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{1,119}$")


class ModeloInvalido(ValueError):
    """Nome que não pode ir para o `.env`."""


def nome_valido(modelo: str) -> bool:
    return bool(_ID_VALIDO.match((modelo or "").strip()))


def estado() -> dict[str, Any]:
    """O que a tela precisa: qual é o modelo agora, se é local e as opções.

    0.80.0 — o catálogo passou a depender do **provedor**: o nome
    `llama-3.3-70b-versatile` não existe no Google, e `gemini-2.5-flash` não
    existe no Groq. Mostrar a lista errada era convidar a pessoa a colar um
    nome que só podia dar 404.
    """
    atual = chaves.estado()
    em_uso = provedores.provedor_atual()
    provedor_id = em_uso["id"] if em_uso else "groq"
    padrao = em_uso["modelo"] if em_uso else MODELO_PADRAO
    opcoes = provedores.modelos_do(provedor_id) or CATALOGO
    return {
        "modelo": atual.get("modelo") or "",
        "padrao": padrao,
        "provedor": atual.get("provedor") or "",
        "provedor_id": provedor_id,
        "provedor_nome": em_uso["nome"] if em_uso else (atual.get("provedor") or ""),
        "gratis": em_uso["gratis"] if em_uso else "",
        "provedores": provedores.catalogo()["provedores"],
        "base": atual.get("base") or "",
        "local": bool(atual.get("local")),
        "opcoes": [
            {**item, "atual": item["id"] == (atual.get("modelo") or "")}
            for item in opcoes
        ],
        # Modelo local não tem catálogo: o “modelo” é o arquivo `.gguf` no disco.
        "nota": (
            "Modelo local: o nome aqui é o arquivo .gguf que o llama-server carrega. "
            "Para trocar de arquivo, use “rodar a IA sem chave”."
            if atual.get("local")
            else ""
        ),
    }


def aplicar(modelo: str) -> dict[str, Any]:
    """Grava `JARVIS_AI_MODEL` no `.env`. Quem recarrega o provedor é quem chama."""
    limpo = (modelo or "").strip()
    if not limpo:
        raise ModeloInvalido("diga qual modelo usar")
    if not nome_valido(limpo):
        raise ModeloInvalido(
            "nome de modelo inválido: use só letras, números e . _ : / - (por exemplo llama-3.3-70b-versatile)"
        )
    if len(limpo) > 120:
        raise ModeloInvalido("nome de modelo longo demais")

    atual = chaves._texto_atual()  # noqa: SLF001 - o `.env` é o mesmo arquivo
    texto = chaves.definir(atual, "JARVIS_AI_MODEL", limpo)
    chaves.gravar(texto)
    chaves.aplicar_no_ambiente()
    return {"modelo": limpo, "salvo": True}


def restaurar() -> dict[str, Any]:
    """Volta ao modelo padrão **do provedor em uso** — não ao do Groq."""
    em_uso = provedores.provedor_atual()
    return aplicar(em_uso["modelo"] if em_uso else MODELO_PADRAO)
