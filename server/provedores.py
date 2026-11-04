"""Catálogo de provedores — quem é grátis, quem não é, e como trocar.

O JARVIS fala o dialeto **OpenAI-compatible** (`/chat/completions`), que virou o
esperanto dos provedores: Groq, Google Gemini, OpenRouter, DeepSeek, Mistral,
Anthropic (por camada de compatibilidade) e até o llama-server local respondem
assim. Então trocar de provedor não é reescrever o cérebro: é trocar **três
linhas do `.env`** — endereço, modelo e chave.

Este módulo faz essa troca por você e, principalmente, **não mente sobre preço**:

- **grátis de verdade, sem cartão**: Groq, Google Gemini (com uma condição) e
  os modelos `:free` do OpenRouter — e é por lá que se usa DeepSeek de graça;
- **grátis com condição**: o plano grátis do Google pode usar o conteúdo para
  melhorar os produtos dele; o do OpenRouter é limitado a 50 pedidos/dia;
- **pago, sem nível grátis**: DeepSeek (API), Claude, OpenAI, Cerebras (virou
  teste de US$ 5 com cartão em julho/2026).

Modelo e cota mudam de mês em mês. Por isso a lista é **atalho**, não promessa:
o campo livre e o botão “ver modelos da chave” (consulta a própria conta) são a
fonte da verdade.
"""
from __future__ import annotations

from typing import Any

from . import chaves

# ---------------------------------------------------------------------------
# O catálogo
# ---------------------------------------------------------------------------
# `gratis` é uma frase curta que vai para a tela. Quem lê tem de conseguir
# decidir sem abrir outra aba: “sim”, “sim, com condição” ou “não”.
PROVEDORES: list[dict[str, Any]] = [
    {
        "id": "groq",
        "nome": "Groq",
        "gratis": "sim",
        "resumo": "Grátis, sem cartão. O mais rápido — e o que já está configurado.",
        "base": "https://api.groq.com/openai/v1",
        "modelo": "llama-3.3-70b-versatile",
        "chave_dica": "gsk_",
        "site": "console.groq.com/keys",
        "onde": "console.groq.com/keys",
        "nota": (
            "Cota por conta (chaves do mesmo login dividem o mesmo balde), "
            "mas cada modelo tem a sua cota. Llama 8B: ~14.400 pedidos/dia."
        ),
        "modelos": [
            {
                "id": "llama-3.3-70b-versatile",
                "nome": "Llama 3.3 70B",
                "perfil": "equilíbrio",
                "quando": "O padrão do Groq. Entende bem frase torta. Cota grátis menor (uns 1.000 pedidos por dia).",
            },
            {
                "id": "llama-3.1-8b-instant",
                "nome": "Llama 3.1 8B Instant",
                "perfil": "rápido e resistente",
                "quando": "Quase instantâneo e a maior cota do Groq (uns 14.400 pedidos por dia). O modelo de socorro.",
            },
            {
                "id": "openai/gpt-oss-120b",
                "nome": "GPT-OSS 120B",
                "perfil": "qualidade",
                "quando": "O mais forte dos abertos no Groq. Mais lento, cota média (uns 200 mil tokens/dia).",
            },
            {
                "id": "openai/gpt-oss-20b",
                "nome": "GPT-OSS 20B",
                "perfil": "rápido",
                "quando": "Meio-termo: rápido e com a mesma cota diária do 120B.",
            },
            {
                "id": "meta-llama/llama-4-scout-17b-16e-instruct",
                "nome": "Llama 4 Scout 17B",
                "perfil": "texto grande",
                "quando": "Aguenta documento enorme na mesma conversa.",
            },
            {
                "id": "qwen/qwen3-32b",
                "nome": "Qwen3 32B",
                "perfil": "raciocínio",
                "quando": "Forte em conta e passo a passo; pensa antes de responder.",
            },
        ],
    },
    {
        "id": "google",
        "nome": "Google Gemini",
        "gratis": "sim, com condição",
        "resumo": "Grátis nos modelos Flash. A condição está escrita abaixo — leia antes.",
        "base": "https://generativelanguage.googleapis.com/v1beta/openai",
        "modelo": "gemini-2.5-flash",
        "chave_dica": "AIza",
        "site": "aistudio.google.com/apikey",
        "onde": "aistudio.google.com/apikey",
        "nota": (
            "Flash e Flash-Lite são grátis; os Pro são pagos. Condição: fora da "
            "UE, Suíça e Reino Unido, o conteúdo do plano grátis pode ser usado "
            "para melhorar os produtos do Google. Os limites aparecem no AI Studio."
        ),
        "modelos": [
            {
                "id": "gemini-2.5-flash",
                "nome": "Gemini 2.5 Flash",
                "perfil": "equilíbrio",
                "quando": "Grátis. Contexto grande (bom para ler arquivo inteiro) e resposta rápida.",
            },
            {
                "id": "gemini-2.5-flash-lite",
                "nome": "Gemini 2.5 Flash-Lite",
                "perfil": "rápido",
                "quando": "Grátis. O mais leve da família: mais pedidos por minuto, menos raciocínio.",
            },
            {
                "id": "gemini-2.5-pro",
                "nome": "Gemini 2.5 Pro",
                "perfil": "qualidade (pago)",
                "quando": "O mais forte da casa — e o único desta lista que não é grátis. Exige faturamento ligado.",
            },
        ],
    },
    {
        "id": "openrouter",
        "nome": "OpenRouter",
        "gratis": "sim, só o que termina em :free",
        "resumo": "É por aqui que se usa DeepSeek de graça. O nome do modelo tem de terminar em :free.",
        "base": "https://openrouter.ai/api/v1",
        # O sufixo `:free` é a linha que separa grátis de cobrança. Sem ele, o
        # mesmo modelo é pago — e o usuário só descobre na fatura.
        "modelo": "deepseek/deepseek-chat-v3-0324:free",
        "chave_dica": "sk-or-v1-",
        "site": "openrouter.ai/keys",
        "onde": "openrouter.ai/keys",
        "nota": (
            "20 pedidos/min e 50/dia nos modelos :free; 1.000/dia depois de "
            "comprar US$10 de crédito uma única vez. O catálogo grátis muda "
            "toda semana — use “ver modelos da chave” para pegar o nome de hoje."
        ),
        "modelos": [
            {
                "id": "deepseek/deepseek-chat-v3-0324:free",
                "nome": "DeepSeek V3 :free",
                "perfil": "grátis",
                "quando": "DeepSeek de graça, via OpenRouter. Bom em código e português.",
            },
            {
                "id": "deepseek/deepseek-r1:free",
                "nome": "DeepSeek R1 :free",
                "perfil": "raciocínio grátis",
                "quando": "O DeepSeek que pensa antes de responder — grátis, mas mais lento.",
            },
            {
                "id": "meta-llama/llama-3.3-70b-instruct:free",
                "nome": "Llama 3.3 70B :free",
                "perfil": "grátis",
                "quando": "Mesmo cérebro do padrão do Groq, com a cota do OpenRouter.",
            },
        ],
    },
    {
        "id": "mistral",
        "nome": "Mistral",
        "gratis": "sim, modo Experiment",
        "resumo": "Plano grátis com limite mensal; os números aparecem só no painel.",
        "base": "https://api.mistral.ai/v1",
        "modelo": "mistral-small-latest",
        # Chave da Mistral não tem prefixo reconhecível: 32 caracteres soltos.
        # Por isso ela não é detectada sozinha — tem de ser escolhida na tela.
        "chave_dica": "",
        "site": "console.mistral.ai/api-keys",
        "onde": "console.mistral.ai/api-keys",
        "nota": (
            "A Mistral não publica os números do modo grátis: eles ficam na aba "
            "Limits, dentro do console. Conta sem faturamento fica no plano mais baixo."
        ),
        "modelos": [
            {
                "id": "mistral-small-latest",
                "nome": "Mistral Small",
                "perfil": "equilíbrio",
                "quando": "Grátis no modo Experiment. Rápido e bom em português.",
            },
            {
                "id": "mistral-large-latest",
                "nome": "Mistral Large",
                "perfil": "qualidade (pago)",
                "quando": "Mais forte; no modo grátis pode não estar liberado.",
            },
        ],
    },
    {
        "id": "deepseek",
        "nome": "DeepSeek (direto)",
        "gratis": "não",
        "resumo": "A API do DeepSeek é paga — barata, mas paga. Para DeepSeek de graça, use OpenRouter.",
        "base": "https://api.deepseek.com/v1",
        "modelo": "deepseek-chat",
        "chave_dica": "sk-",
        "site": "platform.deepseek.com/api_keys",
        "onde": "platform.deepseek.com/api_keys",
        "nota": (
            "Não existe nível grátis recorrente na API. O preço é baixo (~US$0,28 "
            "por milhão de tokens de entrada) e não exige assinatura. O chat em "
            "chat.deepseek.com é grátis, mas é site — não serve para o JARVIS."
        ),
        "modelos": [
            {
                "id": "deepseek-chat",
                "nome": "DeepSeek Chat",
                "perfil": "equilíbrio (pago)",
                "quando": "O modelo geral do DeepSeek. Cobra por token; sem mensalidade.",
            },
            {
                "id": "deepseek-reasoner",
                "nome": "DeepSeek Reasoner",
                "perfil": "raciocínio (pago)",
                "quando": "Pensa antes de responder. Mais caro por resposta.",
            },
        ],
    },
    {
        "id": "anthropic",
        "nome": "Claude (Anthropic)",
        "gratis": "não",
        "resumo": "A API do Claude é paga. O Claude grátis é o site claude.ai — não é API.",
        "base": "https://api.anthropic.com/v1",
        "modelo": "claude-sonnet-4-5",
        "chave_dica": "sk-ant-",
        "site": "console.anthropic.com/settings/keys",
        "onde": "console.anthropic.com/settings/keys",
        "nota": (
            "A Anthropic dá um pequeno crédito inicial e depois cobra por token. "
            "O endereço abaixo é a camada de compatibilidade com o formato OpenAI; "
            "se o provedor mudar de nome de modelo, use “ver modelos da chave”."
        ),
        "modelos": [
            {
                "id": "claude-sonnet-4-5",
                "nome": "Claude Sonnet 4.5",
                "perfil": "qualidade (pago)",
                "quando": "Equilíbrio entre qualidade e preço na Anthropic.",
            },
            {
                "id": "claude-haiku-4-5",
                "nome": "Claude Haiku 4.5",
                "perfil": "rápido (pago)",
                "quando": "O mais barato da família — ainda pago.",
            },
        ],
    },
    {
        "id": "openai",
        "nome": "OpenAI",
        "gratis": "não",
        "resumo": "Sem nível grátis para texto. Só faz sentido se você já paga.",
        "base": "https://api.openai.com/v1",
        "modelo": "gpt-4o-mini",
        "chave_dica": "sk-",
        "site": "platform.openai.com/api-keys",
        "onde": "platform.openai.com/api-keys",
        "nota": "Não há nível grátis para geração de texto. Pede cartão e cobra por token.",
        "modelos": [
            {
                "id": "gpt-4o-mini",
                "nome": "GPT-4o mini",
                "perfil": "equilíbrio (pago)",
                "quando": "O mais barato da OpenAI.",
            },
            {
                "id": "gpt-4o",
                "nome": "GPT-4o",
                "perfil": "qualidade (pago)",
                "quando": "Mais forte e mais caro.",
            },
        ],
    },
    {
        "id": "cerebras",
        "nome": "Cerebras",
        "gratis": "teste de US$ 5",
        "resumo": "Deixou de ser grátis em julho/2026: virou teste de US$ 5 com cartão.",
        "base": "https://api.cerebras.ai/v1",
        "modelo": "gpt-oss-120b",
        "chave_dica": "csk-",
        "site": "cloud.cerebras.ai",
        "onde": "cloud.cerebras.ai",
        "nota": "Cartão obrigatório, US$ 5 que expiram em 30 dias. Muito rápido, mas não é opção grátis.",
        "modelos": [
            {
                "id": "gpt-oss-120b",
                "nome": "GPT-OSS 120B",
                "perfil": "velocidade (teste)",
                "quando": "Roda em hardware próprio; poucos pedidos por minuto no teste.",
            },
        ],
    },
]

POR_ID: dict[str, dict[str, Any]] = {item["id"]: item for item in PROVEDORES}

# Provedores que se identificam pela cara da chave. `sk-` sozinho fica de fora
# de propósito: DeepSeek, OpenAI e outros usam o mesmo prefixo — chutar seria
# mandar a chave para o endereço errado.
_POR_PREFIXO = (
    ("sk-ant-", "anthropic"),
    ("sk-or-v1-", "openrouter"),
    ("gsk_", "groq"),
    ("csk-", "cerebras"),
    ("AIza", "google"),
)


class ProvedorInvalido(ValueError):
    """Id de provedor que não existe no catálogo."""


def por_id(provedor_id: str) -> dict[str, Any]:
    achado = POR_ID.get((provedor_id or "").strip().lower())
    if not achado:
        raise ProvedorInvalido(
            "provedor desconhecido: use " + ", ".join(item["id"] for item in PROVEDORES)
        )
    return achado


def detectar(chave: str) -> str | None:
    """Qual provedor a chave denuncia pela cara. `None` quando não dá para saber."""
    limpa = (chave or "").strip()
    for prefixo, provedor_id in _POR_PREFIXO:
        if limpa.startswith(prefixo):
            return provedor_id
    return None


def detectar_varias(lista: list[str]) -> str | None:
    """O provedor comum a todas as chaves — só quando todas apontam para o mesmo."""
    achados = {detectar(chave) for chave in lista if chave}
    if len(achados) == 1:
        (unico,) = achados
        return unico
    return None


def por_base(base: str) -> dict[str, Any] | None:
    """Qual provedor tem este endereço. Não lê `.env`: serve de dentro de `chaves`."""
    limpa = (base or "").rstrip("/").lower()
    if not limpa:
        return None
    for item in PROVEDORES:
        if item["base"].rstrip("/").lower() == limpa:
            return item
    for item in PROVEDORES:  # endereço com /chat/completions no fim, por exemplo
        if item["base"].rstrip("/").lower() in limpa:
            return item
    return None


def provedor_atual() -> dict[str, Any] | None:
    """O provedor que a configuração atual usa, identificado pelo endereço."""
    return por_base(chaves.estado().get("base") or "")


def modelos_do(provedor_id: str) -> list[dict[str, str]]:
    """Atalhos de modelo do provedor; lista vazia se o id não existir."""
    item = POR_ID.get((provedor_id or "").strip().lower())
    return [dict(modelo) for modelo in item["modelos"]] if item else []


def resumo(provedor_id: str) -> dict[str, Any]:
    """Uma linha para a tela: nome, se é grátis e onde pegar a chave."""
    item = POR_ID.get((provedor_id or "").strip().lower())
    if not item:
        return {}
    return {
        "id": item["id"],
        "nome": item["nome"],
        "gratis": item["gratis"],
        "resumo": item["resumo"],
        "onde": item["onde"],
        "nota": item["nota"],
        "chave_dica": item["chave_dica"],
        "modelo": item["modelo"],
        "base": item["base"],
    }


def catalogo() -> dict[str, Any]:
    """O que a tela mostra: a lista inteira e quem está em uso agora."""
    atual = provedor_atual()
    atual_id = atual["id"] if atual else ""
    return {
        "atual": atual_id,
        "provedores": [
            {
                "id": item["id"],
                "nome": item["nome"],
                "gratis": item["gratis"],
                "resumo": item["resumo"],
                "onde": item["onde"],
                "nota": item["nota"],
                "chave_dica": item["chave_dica"],
                "modelo": item["modelo"],
                "atual": item["id"] == atual_id,
            }
            for item in PROVEDORES
        ],
    }


# ---------------------------------------------------------------------------
# Trocar de provedor
# ---------------------------------------------------------------------------

def aplicar(provedor_id: str, modelo: str | None = None) -> dict[str, Any]:
    """Grava provedor, endereço e modelo no `.env`; guarda as chaves do antigo.

    A chave é do provedor: uma `gsk_` não abre a porta do Google. Por isso as
    chaves do provedor que sai ficam guardadas em `JARVIS_CHAVES_<ID>` e voltam
    se ele for escolhido de novo — trocar de ideia não custa colar de novo.
    """
    alvo = por_id(provedor_id)
    escolhido = (modelo or "").strip() or alvo["modelo"]

    texto = chaves._texto_atual()  # noqa: SLF001 - `.env` é o mesmo arquivo
    atual = provedor_atual()
    ativas = chaves.separar_chaves(chaves.ler_valor("JARVIS_AI_API_KEY", texto))
    if atual and ativas:
        texto = chaves.definir(texto, f"JARVIS_CHAVES_{atual['id'].upper()}", ",".join(ativas))
    voltando = chaves.separar_chaves(chaves.ler_valor(f"JARVIS_CHAVES_{alvo['id'].upper()}", texto))

    valores = {
        "JARVIS_AI_PROVIDER": alvo["nome"],
        "JARVIS_AI_BASE_URL": alvo["base"],
        "JARVIS_AI_MODEL": escolhido,
        "JARVIS_AI_API_KEY": ",".join(voltando),
    }
    for nome, valor in valores.items():
        texto = chaves.definir(texto, nome, valor)
    chaves.gravar(texto)
    chaves.aplicar_no_ambiente()

    return {
        "provedor": alvo["id"],
        "nome": alvo["nome"],
        "base": alvo["base"],
        "modelo": escolhido,
        "chaves_voltaram": len(voltando),
        "chaves_guardadas": len(ativas) if atual else 0,
        "gratis": alvo["gratis"],
        "onde": alvo["onde"],
        "resumo": _resumo_da_troca(alvo, voltando),
    }


def _resumo_da_troca(alvo: dict[str, Any], voltando: list[str]) -> str:
    cabeca = (
        f"Agora o provedor é {alvo['nome']} ({alvo['gratis']}), "
        f"com o modelo {alvo['modelo']}."
    )
    if voltando:
        return f"{cabeca} As {len(voltando)} chave(s) que você já tinha deste provedor voltaram."
    return (
        f"{cabeca} Cole a chave nova em “Colar chaves” — pegue em {alvo['onde']}. "
        "As chaves do provedor anterior ficaram guardadas, para o caso de você voltar."
    )


# ---------------------------------------------------------------------------
# Descobrir os modelos da conta (a verdade em vez da lista)
# ---------------------------------------------------------------------------

def _gratis_pelo_nome(modelo_id: str) -> bool:
    """No OpenRouter o preço está no nome: `:free` é grátis, o resto é cobrado."""
    return modelo_id.endswith(":free")


def listar_modelos(
    base: str | None = None,
    chave: str | None = None,
    limite: int = 200,
    buscador: Any = None,
    tempo: float = 8.0,
) -> dict[str, Any]:
    """`GET {base}/models` — pergunta ao provedor quais modelos **esta conta** vê.

    A lista de atalhos envelhece; a conta não. Este é o botão que transforma
    “esse nome não existe mais” em “aqui estão os nomes de hoje”. Não gasta
    cota de geração: é leitura de catálogo.
    """
    config = chaves.estado()
    alvo_base = (base or config.get("base") or "").rstrip("/")
    if not alvo_base:
        raise ProvedorInvalido("nenhum provedor configurado: cole uma chave primeiro")

    ativa = (chave or "").strip()
    if not ativa:
        lista = chaves.separar_chaves(chaves.ler_valor("JARVIS_AI_API_KEY"))
        ativa = lista[0] if lista else ""
    if not ativa:
        raise ProvedorInvalido("sem chave: cole a chave do provedor antes de listar os modelos")

    dono = por_base(alvo_base)
    provedor_id = dono["id"] if dono else ""
    cabecalho = {"Authorization": f"Bearer {ativa}"}

    try:
        if buscador is not None:  # teste: não sai da máquina
            resposta = buscador(f"{alvo_base}/models", cabecalho, tempo)
        else:
            import httpx  # noqa: PLC0415 (só quem chama paga o custo)

            resposta = httpx.get(f"{alvo_base}/models", headers=cabecalho, timeout=tempo)
    except Exception as exc:  # noqa: BLE001 - rede é imprevisível e a frase é a saída
        raise ProvedorInvalido(
            f"não consegui falar com {alvo_base} ({type(exc).__name__}) — internet ou provedor fora do ar"
        ) from exc

    codigo = int(getattr(resposta, "status_code", 0) or 0)
    if codigo in (401, 403):
        raise ProvedorInvalido(
            f"a chave foi recusada (HTTP {codigo}) — gere outra em {dono['onde'] if dono else 'o painel do provedor'}"
        )
    if codigo == 404:
        raise ProvedorInvalido(
            "este provedor não publica lista de modelos — use o campo livre com o nome do painel"
        )
    if codigo >= 400:
        raise ProvedorInvalido(f"o provedor respondeu HTTP {codigo} ao pedir a lista")

    try:
        corpo = resposta.json()
    except Exception as exc:  # noqa: BLE001
        raise ProvedorInvalido("a resposta da lista de modelos não era JSON") from exc

    itens = corpo.get("data") if isinstance(corpo, dict) else corpo
    if not isinstance(itens, list):
        raise ProvedorInvalido("a lista de modelos veio num formato inesperado")

    modelos: list[dict[str, Any]] = []
    vistos: set[str] = set()
    for item in itens:
        nome = item.get("id") if isinstance(item, dict) else str(item)
        if not nome or nome in vistos:
            continue
        vistos.add(nome)
        modelos.append({"id": nome, "gratis": _gratis_pelo_nome(nome)})

    # Grátis primeiro (é o que interessa a quem chegou aqui), depois alfabético.
    modelos.sort(key=lambda item: (not item["gratis"], item["id"].lower()))
    total = len(modelos)
    gratis = sum(1 for item in modelos if item["gratis"])
    recortados = modelos[: max(1, limite)]
    return {
        "provedor": provedor_id,
        "base": alvo_base,
        "modelos": recortados,
        "total": total,
        "gratis": gratis,
        "resumo": (
            f"{total} modelos nesta chave"
            + (f", {gratis} grátis (terminam em :free)" if gratis else "")
            + ("; mostrando os primeiros " + str(len(recortados)) if total > len(recortados) else "")
            + "."
        ),
    }
