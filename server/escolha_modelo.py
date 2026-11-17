"""Qual modelo usar quando o do `.env` não existe mais (0.91.31).

O problema, medido no PC do dono em 17/11:

    modelo: deepseek/deepseek-chat-v3-0324:free
    NÃO  o modelo … NÃO está na lista.
    Use um destes:
      deepseek/deepseek-chat-v3-0324      ← pago
      deepseek/deepseek-chat-v3.1         ← pago
      deepseek/deepseek-chat              ← pago

O `difflib` sugeriu os nomes **mais parecidos**, e os mais parecidos eram
justamente os pagos. Numa conta gratuita, trocar para qualquer um deles só muda
o erro de lugar: sai o 404 e entra o 402.

Este módulo resolve a escolha, e a regra é simples e declarada:

1. **grátis primeiro** (`:free`): chave que não gasta crédito não dá susto na
   conta do dono;
2. **conversa, não ferramenta**: fora quem só faz embedding, áudio, imagem,
   moderação ou ranking — esses respondem 400 num chat;
3. **modelo de verdade**: prefere de 8b para cima; 1–3b erra demais em
   português e o dono culpa o JARVIS;
4. **quem já se provou**: uma ordem curta de famílias que conversam bem
   (deepseek, llama, qwen, mistral, gemma, nemotron, gpt-oss…);
5. **empate é decidido por nome** — a mesma lista sempre dá a mesma escolha.

O que este arquivo **não** faz: perguntar ao provedor se o modelo responde. Isso
é `chaves.testar_modelo`, e é o passo seguinte: escolher não é provar.
"""
from __future__ import annotations

import re

# Nomes que nunca servem para conversar: o endpoint de chat devolve 400 neles.
PARA_FORA = (
    "embed",
    "whisper",
    "tts",
    "audio",
    "speech",
    "moderation",
    "rerank",
    "guard",
    "clip",
    "dall-e",
    "stable-diffusion",
    "sdxl",
    "flux",
    "image",
    "vision-only",
    "ocr",
)

# Famílias que conversam bem em português, na ordem em que eu confiaria nelas.
# A ordem não é gosto: é o que sobrou de bom nos testes do dono e nos modelos
# gratuitos que existem de verdade (a lista muda toda semana; por isso a lista
# aqui é de **prefixos**, não de nomes completos).
FAMILIAS = (
    "deepseek/",
    "meta-llama/",
    "qwen/",
    "mistralai/",
    "google/gemma",
    "nvidia/nemotron",
    "openai/gpt-oss",
    "microsoft/phi",
    "moonshotai/",
    "z-ai/",
    "x-ai/",
    "amazon/nova",
    "cohere/",
    "baidu/",
    "inclusionai/",
    "liquid/",
    "dots-studio/",
)

# Palavras que costumam indicar um modelo ajustado para conversar.
BOAS_PALAVRAS = ("instruct", "chat", "versatile", "flash", "mini", "it")

# Modelos de **raciocínio**: pensam antes de responder e o pensamento também
# ocupa o limite de tokens. No PC do dono (17/11) o escolhido foi um deles — e
# ele responde com `content` vazio quando o pensamento come o limite inteiro.
# Funcionam, mas para o JARVIS (respostas curtas, conversa) vêm depois dos
# modelos de conversa comuns: o custo é uma resposta em branco na tela.
MARCAS_DE_RACIOCINIO = ("reasoning", "thinking", "qwq", "-r1")

_TAMANHO = re.compile(r"(\d+(?:\.\d+)?)\s*b(?![a-z0-9])")


def parametros(nome: str) -> float:
    """Os bilhões de parâmetros que o nome declara (0 quando não declara)."""
    achados = [float(item) for item in _TAMANHO.findall(nome.lower())]
    return max(achados) if achados else 0.0


def serve_para_conversar(nome: str) -> bool:
    """Este nome pode ser usado num chat?"""
    baixo = nome.lower()
    return not any(marca in baixo for marca in PARA_FORA)


def e_gratis(nome: str) -> bool:
    return nome.lower().endswith(":free")


def e_raciocinio(nome: str) -> bool:
    """O nome diz que é modelo de raciocínio (pensa antes de responder)?"""
    baixo = nome.lower()
    return any(marca in baixo for marca in MARCAS_DE_RACIOCINIO)


def _familia(nome: str) -> int:
    baixo = nome.lower()
    for posicao, prefixo in enumerate(FAMILIAS):
        if baixo.startswith(prefixo):
            return posicao
    return len(FAMILIAS)  # desconhecida: depois de todas as conhecidas


def pontuar(nome: str) -> tuple:
    """A ordem de preferência, do melhor para o pior (menor é melhor)."""
    tamanho = parametros(nome)
    # Fora da faixa útil: 1–3b erra demais; acima de 400b é lento demais para
    # um programa que roda no PC do dono.
    if tamanho == 0:
        faixa = 1
    elif tamanho < 8:
        faixa = 2
    elif tamanho <= 400:
        faixa = 0
    else:
        faixa = 1
    palavras = any(palavra in nome.lower() for palavra in BOAS_PALAVRAS)
    return (
        0 if e_gratis(nome) else 1,
        faixa,
        1 if e_raciocinio(nome) else 0,
        _familia(nome),
        0 if palavras else 1,
        -tamanho,
        len(nome),
        nome,
    )


def candidatos(disponiveis: list[str], limite: int = 3, atual: str = "") -> list[str]:
    """Os melhores nomes para tentar, do melhor para o pior. Nunca inclui `atual`."""
    vistos: set[str] = set()
    uteis: list[str] = []
    for nome in disponiveis:
        limpo = str(nome or "").strip()
        if not limpo or limpo in vistos or limpo == atual:
            continue
        vistos.add(limpo)
        if serve_para_conversar(limpo):
            uteis.append(limpo)
    uteis.sort(key=pontuar)
    return uteis[: max(0, int(limite))]


def sugestoes(
    disponiveis: list[str],
    atual: str = "",
    *,
    so_gratis: bool = False,
    limite: int = 3,
) -> list[str]:
    """Nomes para mostrar a quem só quer trocar à mão — respeitando conta grátis."""
    lista = candidatos(disponiveis, limite=limite * 6 if so_gratis else limite, atual=atual)
    if so_gratis:
        lista = [nome for nome in lista if e_gratis(nome)]
    return lista[:limite]
