"""Contexto de conversa — o que cabe na janela antes de a conversa quebrar.

Camada determinística inspirada no subsistema de contexto do **Cherry Studio**
(AGPL-3.0). Nenhuma linha do upstream foi copiada: o que está aqui é a regra
reimplementada em Python — orçamento da janela, estimativa de tokens,
fechamento por turno, higiene do histórico, resumo de retenção e contabilidade
de uso. Nenhum tokenizador BPE é usado, nenhum modelo é chamado e nenhuma
conversa sai da máquina.
"""

from __future__ import annotations

import json
import math
import re
from typing import Any

from .review import common, finalize, finding, verdict as veredito_padrao

VERSAO = "0.37.1"

MAX_TEXTO = 200_000
MAX_MENSAGENS = 400

MODOS = ("lite", "full", "ultra")

DIALETOS = ("anthropic", "openai", "google", "ollama")

# Proporção mínima da janela que fica com o prompt, mesmo quando a reserva de
# saída é grande: sem ela, um `max_tokens` igual à janela zeraria a entrada.
MIN_SALA_ENTRADA = 0.2

# Limiar de compactação padrão: 80% da sala de entrada.
LIMIAR_COMPACTACAO = 80

# Corte de saída de ferramenta, em caracteres: piso, padrão e cabeça/cauda.
MIN_LIMIAR_FERRAMENTA = 2_000
LIMIAR_FERRAMENTA = 50_000
CAUDA_FERRAMENTA = 1_000

# Escalada de stub do resumo, em caracteres (do mais generoso ao mais agressivo).
ESCALADA_STUB = (4_000, 1_000, 200, 0)

# Custo de mídia por dialeto: (segundos de áudio, segundos de vídeo).
TAXAS_MIDIA = {
    "anthropic": (32, 258),
    "openai": (32, 170),
    "google": (32, 258),
    "ollama": (32, 258),
}
DURACAO_PADRAO = {"audio": 60, "video": 40}

# Constante de imagem usada quando a dimensão não aparece no texto.
IMAGEM_PADRAO = {"anthropic": 1590, "openai": 765, "google": 258, "ollama": 1000}

PAPEIS = {
    "system": "system", "sistema": "system",
    "user": "user", "usuario": "user", "usuário": "user",
    "assistant": "assistant", "assistente": "assistant",
    "tool": "tool", "ferramenta": "tool",
}

MARCA_ANEXO = "[anexo]"
MARCA_RESUMO = "[resumo]"
MARCA_ORFA = "[Conversa continua]"
SEM_RESULTADO = "[Sem resultado da ferramenta]"

RE_LINHA = re.compile(
    r"^\s*(?P<papel>[A-Za-zÀ-ÿ]+)\s*(?:\((?P<extra>[^)]*)\))?\s*:\s?(?P<conteudo>.*)$"
)
RE_MIDIA = re.compile(
    r"\[(imagem|image|áudio|audio|vídeo|video|documento|document)\b([^\]]*)\]",
    re.IGNORECASE,
)
RE_DIMENSAO = re.compile(r"(\d{1,5})\s*[x×]\s*(\d{1,5})")
RE_DURACAO = re.compile(r"(\d+(?:[.,]\d+)?)\s*(ms|s|seg|segundos?|min|minutos?|h|horas?)\b", re.IGNORECASE)
RE_IMAGEM_TEXTUAL = re.compile(r"\b(\d{1,5})\s*[x×]\s*(\d{1,5})\b")
RE_CJK = re.compile(r"[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uac00-\ud7af]")
RE_CERCA = re.compile(r"```")


class ContextoError(ValueError):
    """Erro de entrada da camada de contexto."""


# ----------------------------------------------------------------- utilidades

def _modo(modo: str) -> str:
    if modo not in MODOS:
        raise ContextoError(f"Nível inválido: use {', '.join(MODOS)}.")
    return modo


def _texto(valor: Any) -> str:
    return valor if isinstance(valor, str) else ""


def _num(valor: Any, padrao: int = 0) -> int:
    try:
        return int(valor)
    except (TypeError, ValueError):
        return padrao


def _pct(parte: float, todo: float) -> float:
    if not todo:
        return 0.0
    return round(100 * parte / todo, 1)


def _linhas(texto: str) -> list[str]:
    return texto.replace("\r\n", "\n").replace("\r", "\n").split("\n")


def _curto(texto: str, limite: int = 64) -> str:
    limpo = re.sub(r"\s+", " ", texto).strip()
    if len(limpo) <= limite:
        return limpo
    corte = limpo.rfind(" ", 0, limite)
    return limpo[: corte if corte > 0 else limite].rstrip(" ,;:") + "…"


def _exemplos(valores: list[str], limite: int = 3) -> str:
    vistos: list[str] = []
    for valor in valores:
        if valor and valor not in vistos:
            vistos.append(valor)
        if len(vistos) >= limite:
            break
    if not vistos:
        return "—"
    return "; ".join(vistos)


# ------------------------------------------------------------------ estimativa

def _tokens_texto(texto: str) -> int:
    """Estimativa lexical: 1 token por caractere CJK, 1 a cada 4 latinos.

    Código cercado por ``` conta a 1 token a cada 3 caracteres, porque
    identificador curto e pontuação densa tokenizam pior que prosa. O teto é
    len(texto): nenhuma estimativa passa de um token por caractere.
    """
    if not texto or not texto.strip():
        return 0
    total = 0.0
    pedacos = RE_CERCA.split(texto)
    for indice, pedaco in enumerate(pedacos):
        if not pedaco:
            continue
        cercado = indice % 2 == 1
        cjk = len(RE_CJK.findall(pedaco))
        resto = len(pedaco) - cjk
        total += cjk + math.ceil(resto / (3 if cercado else 4))
    return max(1, min(len(texto), int(math.ceil(total))))


def _segundos(bruto: str) -> float | None:
    achado = RE_DURACAO.search(bruto)
    if not achado:
        return None
    valor = float(achado.group(1).replace(",", "."))
    unidade = achado.group(2).lower()
    if unidade == "ms":
        return valor / 1000
    if unidade.startswith("min"):
        return valor * 60
    if unidade.startswith("h"):
        return valor * 3600
    return valor


def _clamp_imagem(largura: float, altura: float, borda: int, pixels: int) -> tuple[float, float]:
    maior = max(largura, altura)
    if maior > borda:
        escala = borda / maior
        largura *= escala
        altura *= escala
    if largura * altura > pixels:
        escala = math.sqrt(pixels / (largura * altura))
        largura *= escala
        altura *= escala
    return max(1.0, round(largura)), max(1.0, round(altura))


def _ajustar_openai(largura: float, altura: float) -> tuple[float, float]:
    maior = max(largura, altura)
    if maior > 2048:
        escala = 2048 / maior
        largura *= escala
        altura *= escala
    menor = min(largura, altura)
    if menor > 768:
        escala = 768 / menor
        largura *= escala
        altura *= escala
    return max(1.0, round(largura)), max(1.0, round(altura))


def _tokens_imagem(dialeto: str, largura: float | None = None, altura: float | None = None) -> int:
    """Custo de uma imagem pela fórmula documentada de cada dialeto."""
    if dialeto == "anthropic":
        if not largura or not altura:
            return IMAGEM_PADRAO["anthropic"]
        w, h = _clamp_imagem(largura, altura, 1568, 1_150_000)
        return math.ceil(w * h / 750)
    if dialeto == "openai":
        if not largura or not altura:
            return IMAGEM_PADRAO["openai"]
        w, h = _ajustar_openai(largura, altura)
        ladrilhos = math.ceil(w / 512) * math.ceil(h / 512)
        return 85 + 170 * ladrilhos
    if dialeto == "google":
        if not largura or not altura:
            return IMAGEM_PADRAO["google"]
        if largura <= 384 and altura <= 384:
            return 258
        corte = max(1, math.floor(min(largura, altura) / 1.5))
        return 258 * max(1, math.ceil(largura / corte)) * max(1, math.ceil(altura / corte))
    return IMAGEM_PADRAO["ollama"]


def _tokens_midia(dialeto: str, tipo: str, segundos: float | None) -> int:
    taxa_audio, taxa_video = TAXAS_MIDIA.get(dialeto, TAXAS_MIDIA["ollama"])
    duracao = segundos if segundos and segundos > 0 else DURACAO_PADRAO[tipo]
    taxa = taxa_audio if tipo == "audio" else taxa_video
    return math.ceil(duracao * taxa)


def _anexos(texto: str, dialeto: str) -> tuple[int, list[dict[str, Any]]]:
    """Lê marcadores `[imagem 1024x768]`, `[áudio 90s]`, `[documento 12000]`."""
    total = 0
    itens: list[dict[str, Any]] = []
    for achado in RE_MIDIA.finditer(texto):
        tipo = achado.group(1).lower()
        resto = achado.group(2).strip(" :,")
        if tipo in {"imagem", "image"}:
            dimensao = RE_DIMENSAO.search(resto)
            largura = float(dimensao.group(1)) if dimensao else None
            altura = float(dimensao.group(2)) if dimensao else None
            custo = _tokens_imagem(dialeto, largura, altura)
            itens.append({"tipo": "imagem", "tokens": custo,
                          "detalhe": f"{int(largura)}x{int(altura)}" if dimensao else "sem dimensão"})
        elif tipo in {"áudio", "audio", "vídeo", "video"}:
            familia = "audio" if tipo.startswith("á") or tipo == "audio" else "video"
            segundos = _segundos(resto)
            custo = _tokens_midia(dialeto, familia, segundos)
            itens.append({"tipo": familia, "tokens": custo,
                          "detalhe": f"{segundos:g}s" if segundos else "duração padrão"})
        else:
            tamanho = re.search(r"(\d{1,9})", resto)
            caracteres = int(tamanho.group(1)) if tamanho else 2_000
            custo = max(1, math.ceil(caracteres / 4))
            itens.append({"tipo": "documento", "tokens": custo, "detalhe": f"{caracteres} caracteres"})
        total += custo
    return total, itens


def estimar_texto(texto: str) -> int:
    """Tokens de um texto puro, sem contar anexos."""
    return _tokens_texto(texto)


def estimar_conteudo(conteudo: Any, dialeto: str = "anthropic") -> tuple[int, list[dict[str, Any]]]:
    """Tokens de um conteúdo: string, lista de partes ou nulo."""
    if conteudo is None:
        return 0, []
    if isinstance(conteudo, str):
        anexos, itens = _anexos(conteudo, dialeto)
        # O marcador `[imagem 1024x768]` é metadado nosso: não vai ao provedor.
        limpo = RE_MIDIA.sub(" ", conteudo)
        return _tokens_texto(limpo) + anexos, itens
    total = 0
    itens: list[dict[str, Any]] = []
    if isinstance(conteudo, list):
        for parte in conteudo:
            if isinstance(parte, str):
                total += _tokens_texto(parte)
                continue
            if not isinstance(parte, dict):
                continue
            tipo = _texto(parte.get("type")).lower()
            if tipo in {"image", "imagem"}:
                custo = _tokens_imagem(dialeto, parte.get("width"), parte.get("height"))
                total += custo
                itens.append({"tipo": "imagem", "tokens": custo,
                              "detalhe": f"{parte.get('width')}x{parte.get('height')}" if parte.get("width") else "sem dimensão"})
            elif tipo in {"audio", "video", "media"}:
                familia = "video" if tipo == "video" else "audio"
                custo = _tokens_midia(dialeto, familia, parte.get("duration"))
                total += custo
                itens.append({"tipo": familia, "tokens": custo, "detalhe": "duração declarada"})
            else:
                total += _tokens_texto(_texto(parte.get("text")))
    return total, itens


# ------------------------------------------------------------------- mensagens

def _normalizar(item: dict[str, Any]) -> dict[str, Any]:
    papel = _texto(item.get("role", item.get("papel", ""))).lower()
    papel = PAPEIS.get(papel, papel)
    chamadas: list[dict[str, str]] = []
    for chamada in item.get("tool_calls") or item.get("chamadas") or []:
        if isinstance(chamada, dict):
            identificador = _texto(chamada.get("id", chamada.get("tool_call_id", ""))).strip()
            funcao = chamada.get("function")
            nome = _texto(chamada.get("name") or (funcao.get("name") if isinstance(funcao, dict) else "")).strip()
            if identificador:
                chamadas.append({"id": identificador, "name": nome})
    return {
        "role": papel,
        "content": item.get("content", item.get("conteudo", "")),
        "tool_calls": chamadas,
        "tool_call_id": _texto(item.get("tool_call_id", item.get("id_chamada", ""))).strip(),
        "name": _texto(item.get("name", item.get("nome", ""))).strip(),
    }


def ler_mensagens(texto: str) -> list[dict[str, Any]]:
    """Lê a conversa em JSON ou no formato `papel: conteúdo`."""
    bruto = texto.strip()
    if not bruto:
        return []
    if bruto[0] in "[{":
        try:
            dados = json.loads(bruto)
        except json.JSONDecodeError as exc:
            raise ContextoError(f"JSON inválido na linha {exc.lineno}: {exc.msg}.") from exc
        if isinstance(dados, dict):
            dados = dados.get("messages", dados.get("mensagens", []))
        if not isinstance(dados, list):
            raise ContextoError("O JSON precisa ser uma lista de mensagens.")
        mensagens = [_normalizar(item) for item in dados if isinstance(item, dict)]
        for indice, mensagem in enumerate(mensagens, start=1):
            if not mensagem["role"]:
                raise ContextoError(f"A mensagem {indice} não tem `role`.")
        return mensagens

    mensagens: list[dict[str, Any]] = []
    for numero, linha in enumerate(_linhas(texto), start=1):
        if not linha.strip():
            continue
        achado = RE_LINHA.match(linha)
        papel = PAPEIS.get(achado.group("papel").lower()) if achado else None
        if not achado or not papel:
            if not mensagens:
                raise ContextoError(
                    f"Linha {numero}: comece por `system:`, `user:`, `assistant:` ou `tool(id):`."
                )
            anterior = mensagens[-1]["content"]
            mensagens[-1]["content"] = (anterior + "\n" + linha).strip() if isinstance(anterior, str) else anterior
            continue
        extra = (achado.group("extra") or "").strip()
        conteudo = achado.group("conteudo").strip()
        mensagem = {"role": papel, "content": conteudo, "tool_calls": [], "tool_call_id": "", "name": ""}
        if papel == "tool":
            if "=" in extra:
                identificador, nome = extra.split("=", 1)
                mensagem["tool_call_id"] = identificador.strip()
                mensagem["name"] = nome.strip()
            else:
                mensagem["tool_call_id"] = extra
        elif papel == "assistant" and extra:
            if extra.lower() in {"tools", "chamadas", "chamada", "calls"}:
                extra = conteudo
                mensagem["content"] = ""
            for parte in re.split(r"[,;]", extra):
                pedaco = parte.strip()
                if not pedaco:
                    continue
                if "=" in pedaco:
                    identificador, nome = pedaco.split("=", 1)
                else:
                    nome, _, identificador = pedaco.partition(" ")
                identificador = identificador.strip() or nome.strip()
                if identificador:
                    mensagem["tool_calls"].append({"id": identificador, "name": nome.strip()})
        mensagens.append(mensagem)
    return mensagens


def _tokens_mensagem(mensagem: dict[str, Any], dialeto: str) -> tuple[int, list[dict[str, Any]]]:
    tokens, itens = estimar_conteudo(mensagem.get("content"), dialeto)
    for chamada in mensagem.get("tool_calls", []):
        tokens += _tokens_texto(chamada.get("name", "")) + 4
    if mensagem["role"] == "tool":
        tokens += 4
    return tokens, itens


def _tokens_conversa(mensagens: list[dict[str, Any]], dialeto: str) -> int:
    return sum(_tokens_mensagem(mensagem, dialeto)[0] for mensagem in mensagens)


def _turnos(mensagens: list[dict[str, Any]]) -> list[tuple[int, int]]:
    """Agrupa em turnos atômicos: assistente com ferramentas + seus resultados."""
    turnos: list[tuple[int, int]] = []
    indice = 0
    while indice < len(mensagens):
        mensagem = mensagens[indice]
        if mensagem["role"] == "assistant" and mensagem["tool_calls"]:
            inicio = indice
            indice += 1
            while indice < len(mensagens) and mensagens[indice]["role"] == "tool":
                indice += 1
            turnos.append((inicio, indice))
        else:
            turnos.append((indice, indice + 1))
            indice += 1
    return turnos


def _papel_rotulo(papel: str) -> str:
    return {"system": "sistema", "user": "usuário", "assistant": "assistente", "tool": "ferramenta"}.get(papel, papel)


def _formatar_mensagens(mensagens: list[dict[str, Any]]) -> str:
    linhas: list[str] = []
    for mensagem in mensagens:
        papel = _papel_rotulo(mensagem["role"])
        if mensagem["role"] == "tool":
            marca = mensagem.get("tool_call_id") or "?"
            nome = f"={mensagem['name']}" if mensagem.get("name") else ""
            linhas.append(f"{papel}({marca}{nome}): {_texto(mensagem.get('content'))}")
        elif mensagem["role"] == "assistant" and mensagem["tool_calls"]:
            chamadas = ", ".join(f"{chamada['id']}={chamada['name']}" for chamada in mensagem["tool_calls"])
            conteudo = _texto(mensagem.get("content"))
            linhas.append(f"{papel}({chamadas}): {conteudo}" if conteudo else f"{papel}({chamadas}):")
        else:
            linhas.append(f"{papel}: {_texto(mensagem.get('content'))}")
    return "\n".join(linhas)


# ------------------------------------------------------------------- orçamento

LIMITES_ORCAMENTO = [
    "A janela é a que você declarar: o catálogo do provedor não é consultado.",
    "A conta supõe que entrada e saída disputam a mesma janela, como fazem os provedores que cobram `entrada + max_tokens` contra o limite.",
    "A estimativa de tokens é lexical, não BPE: espere erro de 10% a 20% para texto comum e mais em código.",
    "Cache, desconto de lote e janela compartilhada entre chamadas ficam fora.",
]


def _reserva_efetiva(
    *,
    reserva: int | None,
    saida_assistente: int | None,
    assistente_habilitado: bool,
    max_saida_modelo: int | None,
    dialeto: str,
) -> tuple[int | None, str]:
    if reserva and reserva > 0:
        return reserva, "informada na chamada"
    if assistente_habilitado and saida_assistente and saida_assistente > 0:
        return saida_assistente, "limite do assistente"
    if dialeto == "anthropic" and max_saida_modelo and max_saida_modelo > 0:
        return max_saida_modelo, "teto do modelo (o endpoint Anthropic exige `max_tokens`)"
    return None, "sem reserva"


def planejar_orcamento(
    *,
    janela: int,
    mensagens: str = "",
    dialeto: str = "anthropic",
    reserva: int | None = None,
    max_saida_modelo: int | None = None,
    saida_assistente: int | None = None,
    assistente_habilitado: bool = False,
    margem: int = 0,
    modo: str = "full",
) -> dict[str, Any]:
    """Divide a janela entre prompt e resposta e diz se a conversa cabe."""
    _modo(modo)
    if dialeto not in DIALETOS:
        raise ContextoError(f"Dialeto inválido: use {', '.join(DIALETOS)}.")
    if not 1_000 <= janela <= 10_000_000:
        raise ContextoError("A janela precisa estar entre 1.000 e 10.000.000 tokens.")
    if not 0 <= margem <= 20:
        raise ContextoError("A margem de segurança vai de 0 a 20 por cento.")
    if len(mensagens) > MAX_TEXTO:
        raise ContextoError("Texto acima do limite de leitura.")

    reserva_final, origem = _reserva_efetiva(
        reserva=reserva, saida_assistente=saida_assistente,
        assistente_habilitado=assistente_habilitado,
        max_saida_modelo=max_saida_modelo, dialeto=dialeto,
    )
    sala = janela if reserva_final is None else max(
        janela - reserva_final, math.floor(janela * MIN_SALA_ENTRADA)
    )
    disponivel = math.floor(sala * (100 - margem) / 100)
    lista = ler_mensagens(mensagens) if mensagens.strip() else []
    prompt = _tokens_conversa(lista, dialeto)
    sobra = disponivel - prompt
    pressao = _pct(prompt, disponivel)

    achados: list[dict[str, Any]] = []
    linhas: list[dict[str, Any]] = [
        {"etapa": "Janela", "valor": f"{janela:,}".replace(",", "."), "regra": "declarada pelo provedor"},
    ]
    if reserva_final is None:
        linhas.append({"etapa": "Reserva de saída", "valor": "0", "regra": "nada é reservado: o prompt ocupa a janela inteira"})
    else:
        linhas.append({"etapa": "Reserva de saída", "valor": f"{reserva_final:,}".replace(",", "."), "regra": origem})
    linhas.append({"etapa": "Sala de entrada", "valor": f"{sala:,}".replace(",", "."),
                   "regra": "janela − reserva, com piso de 20% para a entrada" if reserva_final else "janela inteira"})
    if margem:
        linhas.append({"etapa": "Margem", "valor": f"{margem}%", "regra": "desconto de segurança sobre a sala"})
    linhas.append({"etapa": "Disponível", "valor": f"{disponivel:,}".replace(",", "."), "regra": "sala − margem"})
    linhas.append({"etapa": "Prompt medido", "valor": f"{prompt:,}".replace(",", "."), "regra": f"{len(lista)} mensagem(ns) estimada(s)"})
    linhas.append({"etapa": "Sobra", "valor": f"{sobra:,}".replace(",", "."), "regra": "disponível − prompt"})

    if max_saida_modelo and max_saida_modelo >= janela:
        achados.append(finding(
            "must", "max-saida-maior-que-janela", "Teto de saída maior que a janela",
            f"modelo: {max_saida_modelo} tokens",
            "O modelo declara gerar mais tokens do que a própria janela comporta.",
            "A reserva consome a entrada inteira; a requisição nasce impossível — é o padrão dos modelos cujo `maxOutputTokens` encontra ou passa do limite.",
            "Recorte a reserva para 20% a 30% da janela e deixe o prompt com o resto.",
            "O provedor recusa, trunca ou gasta a janela toda antes de gerar.",
        ))
    if reserva_final and reserva_final > janela / 2:
        achados.append(finding(
            "should", "reserva-acima-da-metade", "Reserva de saída acima da metade",
            f"{_pct(reserva_final, janela)}% da janela",
            "A resposta reserva mais da metade do contexto.",
            "Cada token reservado é um token que o histórico não pode usar.",
            "Baixe o limite de saída para o que a resposta realmente precisa.",
            "Conversas longas compactam cedo demais.",
        ))
    if prompt > disponivel:
        achados.append(finding(
            "must", "prompt-acima-da-sala", "Prompt maior que a sala de entrada",
            f"{prompt:,} tokens contra {disponivel:,}".replace(",", "."),
            f"Faltam {abs(sobra):,} tokens para a conversa caber.".replace(",", "."),
            "Enviar assim estoura a janela ou o provedor corta o começo sem avisar.",
            "Corte o histórico com `contexto.corte` ou resuma as mensagens antigas com `contexto.resumo`.",
            "A chamada falha ou perde justamente o começo da conversa.",
        ))
    elif pressao >= LIMIAR_COMPACTACAO:
        achados.append(finding(
            "should", "compactar-agora", "Prompt no limiar de compactação",
            f"{pressao}% da sala",
            "O prompt passou de 80% do que cabe.",
            "Compactar no limite deixa a próxima mensagem sem espaço.",
            "Resuma ou corte em torno de 60% e mantenha folga para o turno seguinte.",
            "A próxima pergunta já não cabe.",
        ))
    if dialeto == "anthropic" and reserva_final is None:
        achados.append(finding(
            "nice", "sem-teto-declarado", "Endpoint Anthropic sem `max_tokens`",
            "dialeto anthropic",
            "A chamada vai sem reserva de saída.",
            "Esse endpoint exige o campo; sem ele a requisição é recusada na borda.",
            "Declare a reserva ou o teto do modelo.",
            "A chamada falha antes de chegar ao modelo.",
        ))
    if reserva_final is None and max_saida_modelo and dialeto != "anthropic":
        achados.append(finding(
            "nice", "teto-ignorado", "Teto de saída declarado e não usado",
            f"modelo: {max_saida_modelo} tokens",
            "O modelo tem teto declarado, mas nenhuma reserva é feita.",
            "É legítimo: quem não declara `max_tokens` não reserva nada. Só confirme que o provedor aceita.",
            "Se o provedor exigir `max_tokens`, informe a reserva.",
            "O provedor pode recusar a chamada sem o campo.",
        ))
    if margem > 10:
        achados.append(finding(
            "nice", "margem-grande", "Margem de segurança alta",
            f"{margem}%",
            "A margem desconta mais de um décimo da sala.",
            "Margem grande cabe no orçamento e custa contexto útil.",
            "Use 5% a 10% quando a estimativa for boa; 15% só com código denso.",
            "Você compacta antes do necessário.",
        ))
    if janela < 4_096:
        achados.append(finding(
            "should", "janela-baixa", "Janela pequena para conversa com ferramentas",
            f"{janela:,} tokens".replace(",", "."),
            "Abaixo de 4 mil tokens, um turno com resultado de ferramenta já enche a janela.",
            "O histórico útil sobra para poucas trocas.",
            "Prefira um modelo com janela maior ou mantenha as saídas de ferramenta curtas.",
            "A conversa perde o fio a cada duas ou três trocas.",
        ))

    if prompt == 0:
        resumo = [
            f"**Sala de entrada:** {disponivel:,} tokens com reserva de {reserva_final or 0:,}.".replace(",", "."),
            f"**Reserva:** {origem}.",
        ]
        veredito = f"Reserva de {reserva_final or 0} tokens e {disponivel} livres para o prompt."
    else:
        resumo = [
            f"**Prompt:** {prompt:,} de {disponivel:,} tokens ({pressao}% da sala).".replace(",", "."),
            f"**Sobra:** {sobra:,} tokens.".replace(",", "."),
        ]
        veredito = (
            f"Cabe: {sobra:,} tokens de folga.".replace(",", ".") if sobra >= 0
            else f"Não cabe: {abs(sobra):,} tokens acima da sala.".replace(",", ".")
        )
    achados, contagens, _sugerido, perguntas = finalize(achados, modo, [
        "O provedor cobra `max_tokens` da mesma janela da entrada?",
        "A estimativa foi comparada com o `usage` real de alguma chamada?",
    ] if modo == "ultra" else [])
    if contagens["must"] or contagens["should"]:
        veredito = veredito_padrao(achados)

    metricas = {
        "janela": janela, "reserva": reserva_final or 0, "sala": sala,
        "disponivel": disponivel, "prompt": prompt, "sobra": sobra,
        "pressao": pressao, "reserva_pct": _pct(reserva_final or 0, janela), "mensagens": len(lista),
    }
    return common(
        analysis="contexto.orcamento", mode=modo, title="Orçamento da janela",
        summary=resumo, findings=achados, counts=contagens, verdict=veredito,
        questions=perguntas, rows=linhas, metrics=metricas, limitations=LIMITES_ORCAMENTO,
    )


# ------------------------------------------------------------------ estimativa

LIMITES_TOKENS = [
    "A estimativa é lexical: 1 token por caractere CJK e 1 a cada 4 caracteres latinos, com código a 1 a cada 3.",
    "Ela erra para menos em texto repleto de símbolos e para mais em listas de palavras curtas.",
    "Dimensão de imagem e duração de mídia só entram se estiverem escritas no texto.",
    "O `usage` do provedor é a única medida autoritativa; esta serve para planejar antes da chamada.",
]


def estimar_conversa(
    *, mensagens: str, dialeto: str = "anthropic", modo: str = "full"
) -> dict[str, Any]:
    """Mede a conversa: tokens por mensagem, por papel e por tipo de anexo."""
    _modo(modo)
    if dialeto not in DIALETOS:
        raise ContextoError(f"Dialeto inválido: use {', '.join(DIALETOS)}.")
    if len(mensagens) > MAX_TEXTO:
        raise ContextoError("Texto acima do limite de leitura.")
    lista = ler_mensagens(mensagens)
    if not lista:
        raise ContextoError("Cole a conversa: uma linha por mensagem, no formato `papel: conteúdo`.")
    if len(lista) > MAX_MENSAGENS:
        raise ContextoError(f"A conversa passa de {MAX_MENSAGENS} mensagens; recorte antes de medir.")

    linhas: list[dict[str, Any]] = []
    por_papel: dict[str, int] = {}
    contagem = {"imagem": 0, "audio": 0, "video": 0, "documento": 0}
    caracteres = 0
    total = 0
    achados: list[dict[str, Any]] = []
    base64_longo = 0
    gigante = 0
    sem_dimensao = 0
    sem_duracao = 0

    for indice, mensagem in enumerate(lista, start=1):
        tokens, itens = _tokens_mensagem(mensagem, dialeto)
        conteudo = mensagem.get("content")
        texto = conteudo if isinstance(conteudo, str) else json.dumps(conteudo, ensure_ascii=False)
        caracteres += len(texto)
        total += tokens
        por_papel[mensagem["role"]] = por_papel.get(mensagem["role"], 0) + tokens
        for item in itens:
            contagem[item["tipo"]] = contagem.get(item["tipo"], 0) + 1
            if "sem dimensão" in item["detalhe"]:
                sem_dimensao += 1
            if "duração padrão" in item["detalhe"]:
                sem_duracao += 1
        if re.search(r"data:[\w/+.-]+;base64,", texto) or re.search(r"[A-Za-z0-9+/]{2000,}={0,2}", texto):
            base64_longo += 1
        if tokens > 20_000:
            gigante += 1
        linhas.append({
            "n": indice, "papel": _papel_rotulo(mensagem["role"]), "tokens": tokens,
            "anexos": len(itens), "texto": _curto(texto, 70),
        })

    if base64_longo:
        achados.append(finding(
            "must", "anexo-em-base64", "Anexo medido pelos bytes",
            f"{base64_longo} mensagem(ns)",
            "Há payload base64 no conteúdo; o contador o trata como texto.",
            "Mídia é cobrada por pixel ou por segundo, não por byte: um MP3 de 13 MB vira milhões de tokens falsos e dispara compactação na primeira troca.",
            "Envie a mídia como parte estruturada (`{type: image, width, height}`) ou descreva o anexo entre colchetes.",
            "O orçamento inteiro é consumido por um número que não existe na fatura.",
        ))
    if sem_dimensao:
        achados.append(finding(
            "should", "imagem-sem-dimensao", "Imagem sem largura e altura",
            f"{sem_dimensao} imagem(ns)",
            "O marcador não traz dimensão, então a constante de fallback foi usada.",
            "O custo real depende dos pixels; a constante erra para mais ou para menos.",
            "Escreva `[imagem 1024x768]` ou envie a parte de imagem com `width` e `height`.",
            "A estimativa perde precisão justamente em conversas com muitas imagens.",
        ))
    if sem_duracao:
        achados.append(finding(
            "should", "midia-sem-duracao", "Áudio ou vídeo sem duração",
            f"{sem_duracao} item(ns)",
            "Sem duração, a taxa do dialeto foi aplicada à duração padrão.",
            "Provedores cobram por segundo; a suposição pode dobrar ou reduzir pela metade.",
            "Escreva `[áudio 90s]` ou `[vídeo 2min]`, ou envie `duration`.",
            "A conta de mídia fica no chute.",
        ))
    if gigante:
        achados.append(finding(
            "should", "mensagem-gigante", "Mensagem acima de 20 mil tokens",
            f"{gigante} mensagem(ns)",
            "Uma única mensagem carrega mais que a maioria das janelas comporta junto do histórico.",
            "Ela domina o orçamento e esconde o resto da conversa.",
            "Corte a saída da ferramenta, pagine o documento ou resuma antes de enviar.",
            "O histórico fica com uma mensagem e nenhum contexto.",
        ))
    papeis = {_papel_rotulo(papel): tokens for papel, tokens in por_papel.items()}
    if "system" not in por_papel:
        achados.append(finding(
            "nice", "sem-system", "Conversa sem mensagem de sistema",
            "nenhuma",
            "Não há instrução permanente medida.",
            "Sem ela, o custo fixo do comportamento não entra na conta.",
            "Inclua a mensagem `system` que o agente usa.",
            "A estimativa esquece a parte que nunca muda.",
        ))
    maior = max(linhas, key=lambda linha: linha["tokens"]) if linhas else None
    resumo = [
        f"**Total:** {total:,} tokens em {len(lista)} mensagem(ns).".replace(",", "."),
        f"**Anexos:** {contagem['imagem']} imagem(ns), {contagem['audio']} áudio(s), {contagem['video']} vídeo(s), {contagem['documento']} documento(s).",
    ]
    veredito = (
        f"{total:,} tokens; a maior mensagem é a {maior['n']} ({maior['tokens']:,}).".replace(",", ".")
        if maior else "Conversa vazia."
    )
    achados, contagens, _sugerido, perguntas = finalize(achados, modo, [
        "Qual foi o `usage` da última chamada com esta conversa?",
        "As imagens e mídias chegam como parte estruturada ou como base64 no texto?",
    ] if modo == "ultra" else [])
    if contagens["must"] or contagens["should"]:
        veredito = veredito_padrao(achados)
    return common(
        analysis="contexto.tokens", mode=modo, title="Estimativa de tokens",
        summary=resumo, findings=achados, counts=contagens, verdict=veredito,
        questions=perguntas, rows=linhas[:60], metrics={
            "mensagens": len(lista), "tokens": total, "caracteres": caracteres,
            "por_papel": papeis, **contagem,
        }, limitations=LIMITES_TOKENS,
    )


# ----------------------------------------------------------------------- corte

LIMITES_CORTE = [
    "O corte remove conteúdo: nenhum resumo é gerado e nenhum trecho é recuperado depois.",
    "Os tokens são estimados, não contados pelo tokenizador do provedor.",
    "System prompt é sempre preservado, e um turno de ferramenta nunca é partido ao meio.",
    "A ordem original é mantida; a marca de corte ocupa o lugar do bloco removido.",
]


def cortar_historico(
    *,
    mensagens: str,
    janela: int,
    reserva: int | None = None,
    dialeto: str = "anthropic",
    manter_ultimas: int = 6,
    limite_mensagens: int | None = None,
    modo: str = "full",
) -> dict[str, Any]:
    """Fecha o histórico por turno até caber na sala de entrada."""
    _modo(modo)
    if dialeto not in DIALETOS:
        raise ContextoError(f"Dialeto inválido: use {', '.join(DIALETOS)}.")
    if not 1_000 <= janela <= 10_000_000:
        raise ContextoError("A janela precisa estar entre 1.000 e 10.000.000 tokens.")
    if not 1 <= manter_ultimas <= 50:
        raise ContextoError("`manter_ultimas` vai de 1 a 50 turnos.")
    if limite_mensagens is not None and not 1 <= limite_mensagens <= MAX_MENSAGENS:
        raise ContextoError(f"`limite_mensagens` vai de 1 a {MAX_MENSAGENS}.")
    if len(mensagens) > MAX_TEXTO:
        raise ContextoError("Texto acima do limite de leitura.")

    lista = ler_mensagens(mensagens)
    if not lista:
        raise ContextoError("Cole a conversa: uma linha por mensagem, no formato `papel: conteúdo`.")
    original = list(lista)
    tokens_antes = _tokens_conversa(lista, dialeto)
    pre_removidas = 0

    recorte = False
    if limite_mensagens is not None and len(lista) > limite_mensagens:
        lista = lista[-limite_mensagens:]
        pre_removidas = len(original) - len(lista)
        recorte = True
        # Não comece por resultado de ferramenta: traga a chamada junto.
        while lista and lista[0]["role"] == "tool":
            primeira = lista[0]
            anterior = [msg for msg in original[: len(original) - len(lista) + 1]
                        if msg["role"] == "assistant"
                        and any(chamada["id"] == primeira["tool_call_id"] for chamada in msg["tool_calls"])]
            if not anterior:
                lista = lista[1:]
                continue
            lista = [anterior[-1], *lista]

    sala = janela if reserva is None else max(janela - reserva, math.floor(janela * MIN_SALA_ENTRADA))
    turnos = _turnos(lista)
    sistema = [turno for turno in turnos if lista[turno[0]]["role"] == "system"]
    candidatos = [turno for turno in turnos if lista[turno[0]]["role"] != "system"]
    manter = candidatos[-manter_ultimas:] if candidatos else []

    def custo(turnos_escolhidos: list[tuple[int, int]]) -> int:
        total = 0
        for inicio, fim in turnos_escolhidos:
            total += _tokens_conversa(lista[inicio:fim], dialeto)
        return total

    mantidos = list(manter)
    tokens_fixos = custo(sistema)
    while len(mantidos) > 1 and tokens_fixos + custo(mantidos) > sala:
        mantidos.pop(0)

    tokens_depois = tokens_fixos + custo(mantidos)
    mantidos_set = set(mantidos)
    linhas: list[dict[str, Any]] = []
    servidas: list[dict[str, Any]] = []
    removidas = pre_removidas
    marcador_usado = False
    if pre_removidas:
        servidas.append({"role": "user", "content": f"[{pre_removidas} mensagem(ns) omitida(s) pelo limite de mensagens]", "tool_calls": [], "tool_call_id": "", "name": ""})
        marcador_usado = True
        linhas.append({"turno": 0, "papel": "—", "tokens": 0, "decisao": "removido",
                       "motivo": f"limite de {limite_mensagens} mensagens"})
    for numero, turno in enumerate(turnos, start=1):
        inicio, fim = turno
        trecho = lista[inicio:fim]
        tokens = _tokens_conversa(trecho, dialeto)
        papel = _papel_rotulo(trecho[0]["role"]) if trecho else "—"
        if turno in mantidos_set or turno in sistema:
            servidas.extend(trecho)
            linhas.append({"turno": numero, "papel": papel, "tokens": tokens,
                           "decisao": "mantido", "motivo": "system" if turno in sistema else "recente"})
            continue
        removidas += len(trecho)
        linhas.append({"turno": numero, "papel": papel, "tokens": tokens,
                       "decisao": "removido", "motivo": "fora do recorte" if recorte else "acima da sala"})
        if not marcador_usado:
            servidas.append({"role": "user", "content": f"[{removidas} mensagem(ns) omitida(s) — resuma com contexto.resumo]", "tool_calls": [], "tool_call_id": "", "name": ""})
            marcador_usado = True

    achados: list[dict[str, Any]] = []
    ultimo = candidatos[-1] if candidatos else None
    if ultimo is not None:
        custo_ultimo = tokens_fixos + custo([ultimo])
        if custo_ultimo > sala:
            achados.append(finding(
                "must", "ultimo-turno-nao-cabe", "O último turno sozinho não cabe",
                f"{custo_ultimo:,} tokens contra {sala:,}".replace(",", "."),
                "Mesmo mantendo só o turno mais recente, a conversa passa da sala.",
                "Não há corte que salve este turno: ele precisa ser encurtado ou resumido.",
                "Corte a saída da ferramenta do último turno ou resuma o turno anterior.",
                "A chamada falha mesmo com o histórico mínimo.",
            ))
    if tokens_antes and (tokens_antes - tokens_depois) / tokens_antes > 0.6 and removidas:
        achados.append(finding(
            "should", "corte-profundo", "Corte removeu mais de 60% do contexto",
            f"{_pct(tokens_antes - tokens_depois, tokens_antes)}% dos tokens",
            "O que sobrou é uma fração pequena da conversa.",
            "Perder mais da metade costuma apagar a decisão que originou o pedido atual.",
            "Gere um resumo do trecho removido e sirva-o no começo do histórico.",
            "O agente responde sem saber o que já foi decidido.",
        ))
    if removidas:
        achados.append(finding(
            "nice", "sem-resumo", "Corte sem resumo do trecho removido",
            f"{removidas} mensagem(ns)",
            "O bloco saiu e nada ficou no lugar além da marca.",
            "Cortar é a última opção; resumir preserva decisão, número e pendência.",
            "Rode `contexto.resumo` no trecho removido e insira o resultado como primeira mensagem de usuário.",
            "A conversa continua, mas sem a memória do que veio antes.",
        ))
    if recorte and removidas:
        achados.append(finding(
            "should", "limite-mensagens-cortou", "O limite de mensagens já removeu o começo",
            f"limite de {limite_mensagens}",
            "O recorte por contagem aconteceu antes do orçamento.",
            "Limite de mensagens ignora tamanho: seis mensagens curtas e seis enormes caem no mesmo teto.",
            "Use o limite só como piso; deixe o orçamento decidir o resto.",
            "Você corta sem saber quanto token está jogando fora.",
        ))
    conhecidas: set[str] = set()
    orfas: list[dict[str, Any]] = []
    for mensagem in servidas:
        if mensagem["role"] == "assistant":
            conhecidas.update(chamada["id"] for chamada in mensagem["tool_calls"])
        elif mensagem["role"] == "tool" and mensagem["tool_call_id"] not in conhecidas:
            orfas.append(mensagem)
    if orfas:
        achados.append(finding(
            "must", "orfa-no-corte", "Resultado de ferramenta sem a chamada",
            f"{len(orfas)} mensagem(ns)",
            "O corte deixou um `tool` cujo `assistant` correspondente saiu.",
            "Provedores recusam histórico com resultado órfão.",
            "Traga a chamada de volta ou remova o resultado.",
            "A chamada é recusada por erro de histórico, não por tamanho.",
        ))
    primeiro = next((mensagem for mensagem in servidas if mensagem["role"] != "system"), None)
    if primeiro is not None and primeiro["role"] != "user":
        achados.append(finding(
            "should", "primeiro-nao-usuario", "Histórico servido não começa com usuário",
            _papel_rotulo(primeiro["role"]),
            "A primeira mensagem depois do sistema não é do usuário.",
            "Parte dos provedores exige que o turno abra com o usuário.",
            "Use `contexto.higiene` para inserir a mensagem de abertura.",
            "A chamada pode ser recusada mesmo cabendo na janela.",
        ))
    if not removidas and not recorte:
        achados.append(finding(
            "nice", "nada-a-cortar", "Nada foi removido",
            f"{tokens_antes:,} de {sala:,} tokens".replace(",", "."),
            "A conversa já cabia na sala com os turnos pedidos.",
            "Nenhum corte é necessário agora.",
            "Siga sem cortar e monitore a pressão com `contexto.orcamento`.",
            "Nada muda; a análise só confirma que há folga.",
        ))

    extra = ["", "## Histórico servido", "", "```text", _formatar_mensagens(servidas)[:6_000], "```"]
    resumo = [
        f"**Antes:** {tokens_antes:,} tokens em {len(original)} mensagem(ns).".replace(",", "."),
        f"**Depois:** {tokens_depois:,} tokens em {len(servidas)} mensagem(ns), contra sala de {sala:,}.".replace(",", "."),
    ]
    veredito = (
        f"Cabe em {sala:,} tokens: {tokens_depois:,} servidos, {removidas} mensagem(ns) fora.".replace(",", ".")
        if tokens_depois <= sala else f"Não cabe: {tokens_depois:,} tokens contra {sala:,}.".replace(",", ".")
    )
    achados, contagens, _sugerido, perguntas = finalize(achados, modo, [
        "O trecho removido pode ser resumido antes de sair?",
        "O provedor aceita dois turnos de usuário seguidos depois da marca?",
    ] if modo == "ultra" else [])
    if contagens["must"] or contagens["should"]:
        veredito = veredito_padrao(achados)
    return common(
        analysis="contexto.corte", mode=modo, title="Corte do histórico",
        summary=resumo, findings=achados, counts=contagens, verdict=veredito,
        questions=perguntas, rows=linhas, metrics={
            "mensagens": len(original), "servidas": len(servidas), "removidas": removidas,
            "turnos": len(turnos), "mantidos": len(mantidos), "tokens_antes": tokens_antes,
            "tokens_depois": tokens_depois, "sala": sala,
            "economia_pct": _pct(tokens_antes - tokens_depois, tokens_antes),
        }, limitations=LIMITES_CORTE, extra_sections=extra,
    )


# --------------------------------------------------------------------- higiene

LIMITES_HIGIENE = [
    "A limpeza é estrutural: conteúdo é removido ou sintetizado, nunca reescrito.",
    "Ela não decide se o que sobrou é verdade, só se o histórico satisfaz a forma que o provedor exige.",
    "Resultado injetado é um marcador, não uma nova execução da ferramenta.",
    "O saneamento é silencioso no upstream; aqui cada mudança aparece com a mensagem de origem.",
]


def sanear_historico(*, mensagens: str, modo: str = "full") -> dict[str, Any]:
    """Conserta órfã, resultado faltante e abertura fora de ordem."""
    _modo(modo)
    if len(mensagens) > MAX_TEXTO:
        raise ContextoError("Texto acima do limite de leitura.")
    lista = ler_mensagens(mensagens)
    if not lista:
        raise ContextoError("Cole a conversa: uma linha por mensagem, no formato `papel: conteúdo`.")
    if len(lista) > MAX_MENSAGENS:
        raise ContextoError(f"A conversa passa de {MAX_MENSAGENS} mensagens; recorte antes de medir.")

    achados: list[dict[str, Any]] = []
    linhas: list[dict[str, Any]] = []

    # 1. Resultados órfãos: `tool` sem chamada anterior.
    conhecidas: set[str] = set()
    sem_orfas: list[dict[str, Any]] = []
    orfas: list[dict[str, Any]] = []
    for indice, mensagem in enumerate(lista, start=1):
        if mensagem["role"] == "assistant":
            conhecidas.update(chamada["id"] for chamada in mensagem["tool_calls"])
            sem_orfas.append(mensagem)
        elif mensagem["role"] == "tool":
            if mensagem["tool_call_id"] and mensagem["tool_call_id"] in conhecidas:
                sem_orfas.append(mensagem)
            else:
                orfas.append({"n": indice, "id": mensagem["tool_call_id"] or "sem id"})
        else:
            sem_orfas.append(mensagem)
    if orfas:
        linhas.append({"correcao": "Resultado órfão removido", "alvo": _exemplos([item["id"] for item in orfas]),
                       "efeito": f"{len(orfas)} mensagem(ns) de ferramenta sem chamada saíram"})
        achados.append(finding(
            "must", "orfa-removida", "Resultado de ferramenta sem chamada",
            _exemplos([item["id"] for item in orfas]),
            "Há mensagem `tool` cujo `tool_call_id` não aparece em nenhum `assistant` anterior.",
            "O provedor valida o par chamada/resultado e recusa o histórico inteiro por causa de um órfão.",
            "Remova o resultado ou traga de volta a mensagem do assistente que o pediu.",
            "A chamada falha com erro de histórico, mesmo cabendo na janela.",
        ))
    if not sem_orfas and lista:
        sem_orfas = [{"role": "user", "content": MARCA_ORFA, "tool_calls": [], "tool_call_id": "", "name": ""}]
        linhas.append({"correcao": "Placeholder de abertura", "alvo": "histórico vazio após a limpeza",
                       "efeito": MARCA_ORFA})

    # 2. Resultados faltantes: chamada sem `tool` correspondente.
    com_resultados: list[dict[str, Any]] = []
    injetadas: list[str] = []
    for indice, mensagem in enumerate(sem_orfas):
        com_resultados.append(mensagem)
        if mensagem["role"] != "assistant" or not mensagem["tool_calls"]:
            continue
        esperados = {chamada["id"]: chamada["name"] for chamada in mensagem["tool_calls"]}
        for seguinte in sem_orfas[indice + 1:]:
            if seguinte["role"] in {"assistant", "user"}:
                break
            if seguinte["role"] == "tool" and seguinte["tool_call_id"] in esperados:
                esperados.pop(seguinte["tool_call_id"], None)
        for identificador, nome in esperados.items():
            com_resultados.append({"role": "tool", "content": SEM_RESULTADO, "tool_calls": [],
                                   "tool_call_id": identificador, "name": nome})
            injetadas.append(identificador)
    if injetadas:
        linhas.append({"correcao": "Resultado injetado", "alvo": _exemplos(injetadas),
                       "efeito": f"{len(injetadas)} marcador(es) `{SEM_RESULTADO}`"})
        achados.append(finding(
            "should", "resultado-injetado", "Chamada sem resultado",
            _exemplos(injetadas),
            "O assistente pediu ferramenta e nenhuma mensagem `tool` respondeu.",
            "Histórico com chamada pendente é recusado por parte dos provedores e confunde o modelo sobre o que já foi executado.",
            "Injete o resultado sintético ou remova a chamada.",
            "A chamada falha ou o modelo repete a ferramenta para sempre.",
        ))

    # 3. Primeira mensagem depois do sistema precisa ser do usuário.
    primeiro = next((indice for indice, mensagem in enumerate(com_resultados) if mensagem["role"] != "system"), None)
    abertura = False
    if primeiro is not None and com_resultados[primeiro]["role"] != "user":
        com_resultados.insert(primeiro, {"role": "user", "content": MARCA_ORFA, "tool_calls": [],
                                         "tool_call_id": "", "name": ""})
        abertura = True
        linhas.append({"correcao": "Abertura de usuário", "alvo": _papel_rotulo(com_resultados[primeiro + 1]["role"]),
                       "efeito": f"`{MARCA_ORFA}` inserido antes da primeira mensagem"})
        achados.append(finding(
            "should", "abertura-inserida", "Histórico começa sem o usuário",
            _papel_rotulo(com_resultados[primeiro + 1]["role"]),
            "A primeira mensagem depois do sistema não é do usuário.",
            "Parte dos provedores exige que o turno abra com a pergunta do usuário.",
            "Insira uma mensagem de abertura ou comece pelo pedido.",
            "A requisição é recusada por formato.",
        ))

    # 4. Forma: id duplicado, ferramenta sem id, conteúdo vazio, chamada com texto.
    ids = [chamada["id"] for mensagem in com_resultados if mensagem["role"] == "assistant"
           for chamada in mensagem["tool_calls"]]
    duplicados = sorted({identificador for identificador in ids if ids.count(identificador) > 1})
    sem_id = [mensagem for mensagem in lista if mensagem["role"] == "tool" and not mensagem["tool_call_id"]]
    vazias = [mensagem for mensagem in com_resultados
              if mensagem["role"] in {"assistant", "user"} and not _texto(mensagem.get("content")).strip()
              and not mensagem["tool_calls"]]
    com_texto = [mensagem for mensagem in com_resultados
                 if mensagem["role"] == "assistant" and mensagem["tool_calls"]
                 and _texto(mensagem.get("content")).strip()]

    if sem_id:
        linhas.append({"correcao": "Resultado sem id", "alvo": f"{len(sem_id)} mensagem(ns)",
                       "efeito": "não há como casar com a chamada"})
        achados.append(finding(
            "must", "tool-sem-id", "Resultado de ferramenta sem id",
            f"{len(sem_id)} mensagem(ns)",
            "A mensagem `tool` não traz `tool_call_id`.",
            "Sem o id não existe par chamada/resultado, e o provedor recusa.",
            "Recupere o id da chamada ou descarte o resultado.",
            "O histórico fica inválido.",
        ))
    if duplicados:
        linhas.append({"correcao": "Id de chamada repetido", "alvo": _exemplos(duplicados),
                       "efeito": "o resultado pode casar com a chamada errada"})
        achados.append(finding(
            "should", "id-duplicado", "Id de chamada repetido",
            _exemplos(duplicados),
            "Dois `tool_calls` usam o mesmo id.",
            "O resultado passa a ser ambíguo e o pareamento deixa de ser determinístico.",
            "Gere um id por chamada.",
            "Ferramentas trocam de resultado entre si.",
        ))
    if vazias:
        achados.append(finding(
            "nice", "mensagem-vazia", "Mensagem sem conteúdo",
            f"{len(vazias)} mensagem(ns)",
            "Há turno de usuário ou assistente sem texto e sem chamada.",
            "Mensagem vazia consome token de envelope e não informa nada.",
            "Remova a mensagem ou preencha o conteúdo.",
            "O histórico acumula ruído.",
        ))
    if com_texto:
        achados.append(finding(
            "nice", "chamada-com-texto", "Chamada de ferramenta com texto",
            f"{len(com_texto)} mensagem(ns)",
            "O assistente escreveu conteúdo e pediu ferramenta na mesma mensagem.",
            "É permitido, mas alguns provedores só honram um dos dois.",
            "Separe a explicação do pedido de ferramenta quando o provedor reclamar.",
            "A explicação some do histórico.",
        ))
    if not achados:
        achados.append(finding(
            "nice", "historico-valido", "Histórico já válido",
            f"{len(com_resultados)} mensagem(ns)",
            "Nenhum órfão, nenhum resultado faltante, abertura correta.",
            "Nada a corrigir.",
            "Siga com o histórico como está.",
            "Nada muda.",
        ))

    servidas = _formatar_mensagens(com_resultados)
    extra = ["", "## Histórico saneado", "", "```text", servidas[:6_000], "```"]
    resumo = [
        f"**Entrada:** {len(lista)} mensagem(ns); **saída:** {len(com_resultados)}.".replace(",", "."),
        f"**Correções:** {len(orfas)} órfã(s), {len(injetadas)} resultado(s) injetado(s), abertura {'inserida' if abertura else 'ok'}.",
    ]
    veredito = (
        "Histórico válido: nada a corrigir." if not (orfas or injetadas or abertura or sem_id or duplicados)
        else f"{len(orfas) + len(injetadas) + int(abertura)} correção(ões) aplicada(s)."
    )
    achados, contagens, _sugerido, perguntas = finalize(achados, modo, [
        "O provedor aceita resultado sintético no lugar do real?",
        "A chamada órfã pode ser recuperada do log em vez de descartada?",
    ] if modo == "ultra" else [])
    if contagens["must"] or contagens["should"]:
        veredito = veredito_padrao(achados)
    return common(
        analysis="contexto.higiene", mode=modo, title="Higiene do histórico",
        summary=resumo, findings=achados, counts=contagens, verdict=veredito,
        questions=perguntas, rows=linhas, metrics={
            "mensagens": len(lista), "saida": len(com_resultados), "orfas": len(orfas),
            "injetadas": len(injetadas), "abertura": int(abertura), "duplicados": len(duplicados),
            "vazias": len(vazias), "sem_id": len(sem_id),
        }, limitations=LIMITES_HIGIENE, extra_sections=extra,
    )


# ----------------------------------------------------------------------- resumo

LIMITES_RESUMO = [
    "O resumo é um índice de retenção, não uma síntese: ele lista o que precisa sobreviver, com a origem.",
    "Nenhum modelo escreve prosa; a extração é por padrão lexical (decisão, número, caminho, pendência).",
    "Saídas de ferramenta acima do limiar viram stub com nome e tamanho, como no upstream.",
    "O que não for extraído continua fora do resumo — confira a lista antes de descartar o original.",
]

RE_DECISAO = re.compile(
    r"\b(decidimos|decidido|ficou definido|vamos (?:usar|adotar|fazer)|opção escolhida|escolhemos|acordado)\b",
    re.IGNORECASE,
)
RE_PENDENCIA = re.compile(
    r"\b(pendente|falta|faltando|próximo passo|proximo passo|a fazer|todo|aguardando|pergunta em aberto)\b",
    re.IGNORECASE,
)
RE_NUMERO = re.compile(r"\b\d+(?:[.,]\d+)?\s*(?:%|ms|s|min|minutos?|h|horas?|dias?|semanas?|meses?|R\$|US\$|MB|GB|TB|k|mil|milh(?:ão|ões))\b", re.IGNORECASE)
RE_CAMINHO = re.compile(r"(?:[\w.-]+/)+[\w.-]+\.\w{1,5}\b|\b[\w-]+\.(?:py|ts|tsx|js|jsx|json|ya?ml|md|csv|pdf|sh|toml|sql)\b")


def _itens_retencao(mensagens: list[dict[str, Any]], limite_por_tipo: int = 6) -> list[dict[str, Any]]:
    itens: list[dict[str, Any]] = []
    for numero, mensagem in enumerate(mensagens, start=1):
        conteudo = mensagem.get("content")
        if not isinstance(conteudo, str) or not conteudo:
            continue
        for linha in _linhas(conteudo):
            limpa = linha.strip(" -•\t")
            if len(limpa) < 12:
                continue
            tipos = [
                (tipo, padrao.search(limpa))
                for tipo, padrao in (("decisão", RE_DECISAO), ("pendência", RE_PENDENCIA),
                                     ("número", RE_NUMERO), ("caminho", RE_CAMINHO))
            ]
            for tipo, achado in [par for par in tipos if par[1]][:2]:
                itens.append({"tipo": tipo, "texto": _curto(limpa, 110), "mensagem": numero,
                              "trecho": _curto(achado.group(0), 40)})
    por_tipo: dict[str, int] = {}
    filtrados: list[dict[str, Any]] = []
    for item in itens:
        if por_tipo.get(item["tipo"], 0) >= limite_por_tipo:
            continue
        por_tipo[item["tipo"]] = por_tipo.get(item["tipo"], 0) + 1
        filtrados.append(item)
    return filtrados


def resumir_historico(
    *,
    mensagens: str,
    limite: int = 2_000,
    limiar: int = 4_000,
    modo: str = "full",
) -> dict[str, Any]:
    """Prepara o resumo de retenção que substitui o trecho cortado."""
    _modo(modo)
    if not 100 <= limite <= 20_000:
        raise ContextoError("O limite do resumo vai de 100 a 20.000 tokens.")
    if not 0 <= limiar <= 20_000:
        raise ContextoError("O limiar de stub vai de 0 a 20.000 caracteres.")
    if len(mensagens) > MAX_TEXTO:
        raise ContextoError("Texto acima do limite de leitura.")
    lista = ler_mensagens(mensagens)
    if not lista:
        raise ContextoError("Cole a conversa: uma linha por mensagem, no formato `papel: conteúdo`.")

    nomes: dict[str, str] = {}
    for mensagem in lista:
        for chamada in mensagem["tool_calls"]:
            nomes[chamada["id"]] = chamada["name"]

    mensagens_stub: list[dict[str, Any]] = []
    stubs = 0
    anexos = 0
    for mensagem in lista:
        conteudo = mensagem.get("content")
        if mensagem["role"] == "tool" and isinstance(conteudo, str) and len(conteudo) > limiar:
            nome = mensagem.get("name") or nomes.get(mensagem["tool_call_id"], "ferramenta")
            conteudo = f"[Ferramenta {nome} devolveu {len(conteudo)} caracteres; omitida antes do resumo]"
            stubs += 1
        if isinstance(conteudo, str):
            achados_midia = list(RE_MIDIA.finditer(conteudo))
            if achados_midia:
                anexos += len(achados_midia)
                conteudo = RE_MIDIA.sub(lambda m: f"[{m.group(1).lower()}]", conteudo)
        mensagens_stub.append({**mensagem, "content": conteudo})

    itens = _itens_retencao(mensagens_stub)
    ferramentas: dict[str, int] = {}
    for mensagem in lista:
        if mensagem["role"] == "tool":
            nome = mensagem.get("name") or nomes.get(mensagem["tool_call_id"], "ferramenta sem nome")
            ferramentas[nome] = ferramentas.get(nome, 0) + 1

    linhas: list[dict[str, Any]] = [
        {"tipo": item["tipo"], "item": item["texto"], "origem": f"mensagem {item['mensagem']}"}
        for item in itens
    ]
    for nome, quantidade in sorted(ferramentas.items(), key=lambda par: -par[1]):
        linhas.append({"tipo": "ferramenta", "item": nome, "origem": f"{quantidade} chamada(s)"})

    secoes = ["## O que precisa sobreviver", ""]
    for tipo in ("decisão", "número", "caminho", "pendência"):
        do_tipo = [item for item in itens if item["tipo"] == tipo]
        if not do_tipo:
            continue
        secoes.append(f"### {tipo.capitalize()} ({len(do_tipo)})")
        secoes += [f"- {item['texto']} (mensagem {item['mensagem']})" for item in do_tipo]
        secoes.append("")
    if ferramentas:
        secoes.append("### Ferramentas usadas")
        secoes += [f"- {nome}: {quantidade} chamada(s)" for nome, quantidade in sorted(ferramentas.items(), key=lambda par: -par[1])]
        secoes.append("")
    if anexos:
        secoes.append("### Anexos")
        secoes.append("- [imagem], [áudio], [vídeo] ou [documento] conforme o marcador original")
        secoes.append("")
    if stubs:
        secoes.append("### Saídas omitidas")
        secoes += [f"- {stubs} saída(s) de ferramenta acima de {limiar} caracteres virou stub com nome e tamanho"]
        secoes.append("")

    texto = "\n".join(secoes).strip()
    tokens_resumo = _tokens_texto(texto)
    tokens_antes = _tokens_conversa(lista, "anthropic")
    tokens_stub = _tokens_conversa(mensagens_stub, "anthropic")

    cortados = 0
    while tokens_resumo > limite and linhas:
        removido = linhas.pop()
        if removido["tipo"] != "ferramenta":
            cortados += 1
        texto = texto.replace(f"- {removido['item']}", "").strip()
        tokens_resumo = _tokens_texto(texto)

    achados: list[dict[str, Any]] = []
    if not itens:
        achados.append(finding(
            "must", "sem-retencao", "Nada foi reconhecido para retenção",
            f"{len(lista)} mensagem(ns)",
            "Nenhuma decisão, número, caminho ou pendência apareceu no texto.",
            "Um resumo sem item é uma linha dizendo que houve conversa — o que se perde é tudo o que foi dito.",
            "Reveja o trecho e escreva à mão os pontos que importam, ou mantenha o histórico.",
            "A conversa perde a memória e ninguém percebe até a resposta errada.",
        ))
    if cortados:
        achados.append(finding(
            "should", "itens-cortados", "Itens acima do limite do resumo",
            f"{cortados} item(ns)",
            "O índice de retenção passou do limite e os últimos itens saíram.",
            "Limite de resumo é orçamento: o que não cabe aqui se perde de vez.",
            "Aumente o limite ou escreva um resumo manual mais curto.",
            "A decisão mais recente é a primeira a sumir.",
        ))
    if stubs == 0 and any(mensagem["role"] == "tool" for mensagem in lista):
        achados.append(finding(
            "nice", "sem-stub", "Saídas de ferramenta inteiras no resumo",
            f"limiar de {limiar} caracteres",
            "Nenhuma saída passou do limiar, então o resumo carrega o texto inteiro.",
            "Resumir com o texto bruto gasta o orçamento da própria chamada de resumo.",
            "Baixe o limiar para 1.000 ou 200 caracteres.",
            "A chamada de resumo pode estourar a janela antes de resumir.",
        ))
    if limiar == 0 and stubs:
        achados.append(finding(
            "should", "stub-total", "Todas as saídas viraram stub",
            f"{stubs} saída(s)",
            "O limiar zero removeu o conteúdo de toda ferramenta.",
            "O resumo fica só com nomes e tamanhos; o resultado em si desaparece.",
            "Use a escalada 4.000 → 1.000 → 200 antes de zerar.",
            "O resumo não consegue dizer o que a ferramenta devolveu.",
        ))
    if not any(item["tipo"] == "decisão" for item in itens):
        achados.append(finding(
            "nice", "sem-decisao", "Nenhuma decisão registrada",
            "conversa",
            "O texto não usa marcador de decisão.",
            "Sem decisão explícita, o resumo vira lista de fatos e o próximo turno reabre o que já estava fechado.",
            "Registre a escolha em uma frase com “decidimos” ou “ficou definido”.",
            "A mesma discussão volta no turno seguinte.",
        ))

    extra = ["", "## Resumo proposto", "", "```markdown", texto[:8_000], "```"]
    resumo = [
        f"**Itens retidos:** {len(itens)} em {len(linhas)} linha(s).",
        f"**Tokens:** {tokens_stub:,} de entrada viram {tokens_resumo:,} de resumo (limite {limite:,}).".replace(",", "."),
    ]
    veredito = (
        f"Resumo de {tokens_resumo:,} tokens com {len(itens)} item(ns) retido(s).".replace(",", ".")
        if itens else "Nada a reter: escreva o resumo à mão."
    )
    achados, contagens, _sugerido, perguntas = finalize(achados, modo, [
        "O trecho removido pode ser descartado depois deste resumo?",
        "Quem revisa o resumo antes de ele virar memória?",
    ] if modo == "ultra" else [])
    if contagens["must"] or contagens["should"]:
        veredito = veredito_padrao(achados)
    return common(
        analysis="contexto.resumo", mode=modo, title="Resumo de retenção",
        summary=resumo, findings=achados, counts=contagens, verdict=veredito,
        questions=perguntas, rows=linhas[:40], metrics={
            "mensagens": len(lista), "stubs": stubs, "anexos": anexos, "itens": len(itens),
            "cortados": cortados, "tokens_antes": tokens_antes, "tokens_stub": tokens_stub,
            "tokens_resumo": tokens_resumo, "limite": limite,
        }, limitations=LIMITES_RESUMO, extra_sections=extra,
    )


# ------------------------------------------------------------------------- uso

LIMITES_USO = [
    "A conta usa os números que você informa; a fatura do provedor é a fonte.",
    "O contexto ancorado é uma reconstrução a partir de `total − entrada + inicial`, não uma leitura do servidor.",
    "Preço por milhão é o que estiver na sua tabela: desconto, imposto e câmbio ficam fora.",
    "Repetição de hop supõe o mesmo contexto reenviado; retomada com histórico diferente muda a conta.",
]


def contabilizar_uso(
    *,
    entrada: int,
    saida: int,
    total: int | None = None,
    cache: int = 0,
    inicial: int | None = None,
    preco_entrada: float = 0.0,
    preco_saida: float = 0.0,
    preco_cache: float = 0.0,
    hops: int = 1,
    janela: int | None = None,
    modo: str = "full",
) -> dict[str, Any]:
    """Ancora o tamanho do contexto e conta o custo da chamada."""
    _modo(modo)
    if entrada < 0 or saida < 0 or cache < 0:
        raise ContextoError("Tokens não podem ser negativos.")
    if not 1 <= hops <= 20:
        raise ContextoError("`hops` vai de 1 a 20.")
    if min(preco_entrada, preco_saida, preco_cache) < 0:
        raise ContextoError("Preço não pode ser negativo.")
    if janela is not None and not 1_000 <= janela <= 10_000_000:
        raise ContextoError("A janela precisa estar entre 1.000 e 10.000.000 tokens.")

    achados: list[dict[str, Any]] = []
    linhas: list[dict[str, Any]] = []
    if total is not None:
        contexto = total - entrada + (inicial if inicial is not None else entrada)
    else:
        contexto = entrada
    if total is not None and total < entrada:
        achados.append(finding(
            "must", "total-menor-que-entrada", "Total menor que a entrada",
            f"total {total} · entrada {entrada}",
            "O total informado não comporta os tokens de entrada.",
            "Números inconsistentes fazem qualquer conta de contexto derivar errado.",
            "Corrija o `usage` da chamada antes de contabilizar.",
            "O contexto ancorado vira negativo e a pressão deixa de significar algo.",
        ))
        contexto = entrada

    custo = (entrada / 1_000_000) * preco_entrada + (saida / 1_000_000) * preco_saida + (cache / 1_000_000) * preco_cache
    custo_hop = hops * ((contexto / 1_000_000) * preco_entrada + (saida / 1_000_000) * preco_saida)
    pressao = _pct(contexto, janela) if janela else 0.0

    linhas = [
        {"grandeza": "Entrada", "valor": f"{entrada:,}".replace(",", "."), "regra": "tokens de prompt cobrados"},
        {"grandeza": "Saída", "valor": f"{saida:,}".replace(",", "."), "regra": "tokens gerados"},
        {"grandeza": "Total", "valor": f"{total:,}".replace(",", ".") if total is not None else "—", "regra": "informado pelo provedor"},
    ]
    if cache:
        linhas.append({"grandeza": "Cache", "valor": f"{cache:,}".replace(",", "."), "regra": "parte da entrada lida do cache"})
    if inicial is not None:
        linhas.append({"grandeza": "Prompt inicial", "valor": f"{inicial:,}".replace(",", "."), "regra": "contagem da primeira dobra (Gemini/Vertex)"})
    linhas += [
        {"grandeza": "Contexto ancorado", "valor": f"{contexto:,}".replace(",", "."), "regra": "total − entrada + inicial"},
        {"grandeza": "Custo", "valor": f"US$ {custo:.6f}", "regra": "entrada + saída + cache, por milhão"},
        {"grandeza": "Custo em hops", "valor": f"US$ {custo_hop:.6f}", "regra": f"{hops} chamada(s) com o mesmo contexto"},
    ]
    if janela:
        linhas.append({"grandeza": "Pressão na janela", "valor": f"{pressao}%", "regra": f"contexto contra {janela:,}".replace(",", ".")})

    if total is None:
        achados.append(finding(
            "should", "sem-total", "Uso sem total",
            f"entrada {entrada}",
            "Sem `total`, o contexto é só a entrada desta chamada.",
            "Um relatório só de saída não ancora o tamanho da conversa: o contexto real pode ser bem maior.",
            "Registre `totalTokens` junto de `inputTokens`.",
            "A pressão na janela fica subestimada.",
        ))
    if cache > entrada:
        achados.append(finding(
            "must", "cache-acima-da-entrada", "Cache maior que a entrada",
            f"cache {cache} · entrada {entrada}",
            "A parcela lida do cache não cabe na entrada.",
            "Ou o provedor reporta em outra unidade, ou os números vieram de chamadas diferentes.",
            "Confira a semântica do campo de cache no provedor.",
            "O custo calculado fica acima do real.",
        ))
    if saida == 0:
        achados.append(finding(
            "should", "saida-vazia", "Nenhum token de saída",
            "saída 0",
            "A chamada não gerou resposta contabilizada.",
            "Pode ser cancelamento, erro ou resposta vazia — e nenhum dos três é conversa normal.",
            "Confira o status da chamada antes de somar o custo.",
            "O custo de saída some e o total parece barato.",
        ))
    if janela and entrada > janela:
        achados.append(finding(
            "must", "janela-ultrapassada", "Entrada acima da janela",
            f"{entrada:,} contra {janela:,}".replace(",", "."),
            "O prompt enviado é maior que a janela declarada.",
            "Ou a janela está errada, ou a requisição foi truncada ou recusada.",
            "Recalcule o orçamento com `contexto.orcamento` e corte o histórico.",
            "A resposta veio de um prompt diferente do que você enviou.",
        ))
    if hops > 1:
        achados.append(finding(
            "nice", "hops-repetem-prompt", "Continuação recobra o prompt",
            f"{hops} hops",
            "Cada hop reenvia o contexto inteiro como entrada.",
            "O contexto ocupa a janela uma vez, mas é cobrado a cada hop.",
            "Prefira uma resposta só quando o custo importar.",
            "O custo cresce em progressão com o número de retomadas.",
        ))
    if not any((preco_entrada, preco_saida, preco_cache)):
        achados.append(finding(
            "nice", "sem-preco", "Nenhum preço informado",
            "US$ 0,00",
            "Sem preço por milhão, o custo fica zerado.",
            "A análise mede token, não dinheiro.",
            "Informe o preço de entrada e de saída do modelo.",
            "O custo parece gratuito.",
        ))

    resumo = [
        f"**Contexto ancorado:** {contexto:,} tokens.".replace(",", "."),
        f"**Custo da chamada:** US$ {custo:.6f} em {hops} hop(s) → US$ {custo_hop:.6f}.".replace(",", "."),
    ]
    veredito = (
        f"Contexto de {contexto:,} tokens e US$ {custo_hop:.6f} em {hops} hop(s).".replace(",", ".")
    )
    achados, contagens, _sugerido, perguntas = finalize(achados, modo, [
        "O provedor conta cache dentro ou fora do `inputTokens`?",
        "Quantas retomadas a mesma conversa teve de fato?",
    ] if modo == "ultra" else [])
    if contagens["must"] or contagens["should"]:
        veredito = veredito_padrao(achados)
    return common(
        analysis="contexto.uso", mode=modo, title="Uso e custo",
        summary=resumo, findings=achados, counts=contagens, verdict=veredito,
        questions=perguntas, rows=linhas, metrics={
            "entrada": entrada, "saida": saida, "total": total or entrada + saida,
            "contexto": contexto, "cache": cache, "custo": round(custo, 6),
            "custo_hop": round(custo_hop, 6), "hops": hops, "pressao": pressao,
        }, limitations=LIMITES_USO,
    )


# ---------------------------------------------------------------------- regras

def contexto_catalogo() -> dict[str, Any]:
    """Publica fórmulas, padrões e limites que o motor usa."""
    return {
        "fonte": "CherryHQ/cherry-studio (AGPL-3.0)",
        "versao": VERSAO,
        "principio": "Contexto é orçamento: o que não cabe não é respondido.",
        "dialetos": list(DIALETOS),
        "imagem": {
            "formula": {
                "anthropic": "ceil(largura × altura / 750), com borda de 1568 px e 1,15 MP",
                "openai": "85 + 170 × ladrilhos de 512 px, após caber em 2048² e reduzir o menor lado a 768 px",
                "google": "258 quando os dois lados têm até 384 px; senão 258 × recortes de floor(min/1,5)",
                "ollama": "constante de 1.000 tokens por imagem",
            },
            "fallback": IMAGEM_PADRAO,
        },
        "midia": {
            "taxa_por_segundo": {dialeto: {"audio": taxas[0], "video": taxas[1]} for dialeto, taxas in TAXAS_MIDIA.items()},
            "duracao_padrao": DURACAO_PADRAO,
            "regra": "áudio e vídeo são cobrados por segundo; base64 nunca é tokenizado como texto",
        },
        "orcamento": {
            "sala_minima": MIN_SALA_ENTRADA,
            "limiar_compactacao": LIMIAR_COMPACTACAO,
            "precedencia_da_reserva": [
                "reserva explícita da chamada",
                "limite do assistente, quando habilitado",
                "teto do modelo, só no endpoint Anthropic",
                "sem reserva",
            ],
        },
        "corte": {
            "unidade": "turno",
            "agrupamento": "assistente com chamadas + todos os resultados seguintes formam um turno atômico",
            "preservados": ["mensagens de sistema", "último turno", "ordem original"],
            "marca": "[N mensagem(ns) omitida(s) — resuma com contexto.resumo]",
        },
        "higiene": {
            "regras": [
                "resultado sem chamada é removido",
                "chamada sem resultado recebe marcador",
                "a primeira mensagem depois do sistema é do usuário",
                "id de chamada precisa ser único",
            ],
            "marcadores": {"orfa": MARCA_ORFA, "sem_resultado": SEM_RESULTADO},
        },
        "resumo": {
            "escalada_de_stub": list(ESCALADA_STUB),
            "retencao": ["decisão", "número", "caminho", "pendência", "ferramenta"],
            "placeholder_de_anexo": "[imagem], [áudio], [vídeo], [documento]",
        },
        "ferramenta": {
            "limiar_padrao": LIMIAR_FERRAMENTA,
            "limiar_minimo": MIN_LIMIAR_FERRAMENTA,
            "cauda_preservada": CAUDA_FERRAMENTA,
            "marca": "primeiros e últimos caracteres com aviso de omissão no meio",
        },
        "estimativa": {
            "regra": "1 token por caractere CJK; 1 a cada 4 latinos; 1 a cada 3 dentro de bloco cercado",
            "teto": "nunca mais de um token por caractere",
        },
        "limites": {
            "texto": MAX_TEXTO, "mensagens": MAX_MENSAGENS,
            "orcamento": LIMITES_ORCAMENTO, "tokens": LIMITES_TOKENS, "corte": LIMITES_CORTE,
            "higiene": LIMITES_HIGIENE, "resumo": LIMITES_RESUMO, "uso": LIMITES_USO,
        },
        "deixado_de_fora": [
            "Nenhum tokenizador BPE: a estimativa é lexical e erra de 10% a 20%.",
            "Nenhum modelo é chamado para resumir; o resumo é um índice de retenção.",
            "Nenhuma conversa é enviada a provedor, cache ou telemetria.",
            "Compactação automática em segundo plano, cache de prompt e cobrança real ficam fora.",
        ],
        "executado": False,
    }
