# Provedores: quem é grátis, quem é pago e como trocar (0.80.0)

A pergunta que abriu esta versão: **“não dá para usar modelos tipo DeepSeek ou
Claude ou algumas outras de graça?”**

A resposta curta, sem enrolação:

| o que você quer | dá de graça? | como |
|---|---|---|
| **DeepSeek** | **sim**, mas não direto | pelo **OpenRouter**, escolhendo um modelo com `:free` no nome |
| **Claude** | **não** | a API do Claude é paga. O claude.ai é grátis, mas é site, não é API |
| **Google Gemini** | **sim**, nos modelos Flash | chave em `aistudio.google.com/apikey` |
| **Groq** | **sim** (o que já está aqui) | `console.groq.com/keys` |
| **Mistral** | **sim**, modo Experiment | `console.mistral.ai/api-keys` |
| **OpenAI / Cerebras** | **não** | pagos (a Cerebras virou teste de US$ 5 com cartão) |

A tela não acredita em mim: o botão **Ver modelos da minha chave** pergunta ao
próprio provedor quais modelos aquela conta enxerga hoje. Nome de modelo
envelhece em semanas; a conta não.

---

## O caminho mais curto: DeepSeek de graça pelo OpenRouter

Não precisa cartão, não precisa trocar de programa. São cinco passos, um por
linha:

1. abra `openrouter.ai/keys` no navegador;
2. entre com Google ou GitHub (é login, não é pagamento);
3. clique em **Create Key**, dê um nome qualquer (`jarvis`) e copie a chave
   (ela começa com `sk-or-v1-`);
4. no JARVIS, abra **Configurações** → cartão **Modelos de IA** → **Provedor** →
   clique em **OpenRouter**;
5. clique em **Colar chaves**, cole a `sk-or-v1-…` e confirme.

O JARVIS troca o endereço sozinho ao ver a chave — e já testa. Se quiser conferir
qual DeepSeek está grátis **hoje**, clique em **Ver modelos da minha chave**: a
lista vem do OpenRouter, com `:free` marcado em verde.

> **A armadilha do `:free`.** No OpenRouter, o mesmo modelo existe pago e grátis:
> `deepseek/deepseek-chat` cobra; `deepseek/deepseek-chat-v3-0324:free` não.
> Sem o sufixo, é fatura. O JARVIS pinta o selo **grátis** só quando o nome
> termina em `:free`.

Limite do OpenRouter nos modelos grátis: **20 pedidos por minuto e 50 por dia**.
Comprou US$ 10 de crédito uma vez na vida? Sobe para 1.000 por dia.

---

## Google Gemini: o grátis mais capaz — com uma condição

1. abra `aistudio.google.com/apikey`;
2. entre com a conta Google;
3. **Create API key**, copie a chave (começa com `AIza`);
4. no JARVIS: **Modelos de IA** → **Provedor** → **Google Gemini**;
5. **Colar chaves** → cole a `AIza…`.

A condição, escrita antes de você decidir: **fora da União Europeia, Suíça e
Reino Unido, o conteúdo do plano grátis pode ser usado para melhorar os produtos
do Google.** Se o que você conversa com o JARVIS for sensível, use o Groq (que
não treina com o conteúdo) ou o modelo local.

Os modelos **Flash** e **Flash-Lite** são grátis; os **Pro** são pagos. Trocar de
Flash para Flash-Lite muda a cota — cada modelo tem a sua, como no Groq.

---

## DeepSeek direto: pago, porém barato

A API do DeepSeek **não tem nível grátis recorrente**. O que existe:

- `chat.deepseek.com` grátis — mas é site, o JARVIS não fala com site;
- API paga, sem mensalidade, ~US$ 0,28 por milhão de tokens de entrada (dá para
  conversar muito com um dólar).

Se um dia você puser crédito lá: **Modelos de IA** → **Provedor** →
**DeepSeek (direto)**, cole a chave `sk-…` (ela é ambígua, por isso o JARVIS
**não** troca o endereço sozinho — a escolha tem de ser sua).

## Claude: pago, sem exceção

A API do Claude não tem nível grátis. A Anthropic costuma dar um pequeno crédito
inicial, que acaba. O JARVIS suporta porque a Anthropic publica uma camada
compatível com o formato OpenAI; o endereço é `https://api.anthropic.com/v1` e a
chave começa com `sk-ant-`.

Se o objetivo é **não pagar nada**, Claude não é o caminho. Se o objetivo é
qualidade e você já paga, é uma escolha legítima.

---

## Como o JARVIS decide o que usar, em ordem

1. o provedor que está no `.env` (`JARVIS_AI_BASE_URL`);
2. o modelo escolhido no cartão **Modelos de IA** (`JARVIS_AI_MODEL`);
3. a primeira chave que responder (`JARVIS_AI_API_KEY`, uma lista separada por
   vírgula);
4. se a chave der 429/404 **no Groq**, uma tentativa com `llama-3.1-8b-instant`
   para provar que a chave é boa;
5. se nada responder, o modelo local (`ia.local`), que não tem conta.

## O que acontece com as chaves ao trocar de provedor

A chave é **do provedor**: uma `gsk_` não abre a porta do Google. Ao trocar:

- as chaves do provedor que sai ficam guardadas em `JARVIS_CHAVES_<ID>` no
  `.env` — nada é jogado fora;
- o campo ativo fica vazio até você colar a chave do novo;
- se você voltar para o provedor antigo, **as chaves dele voltam sozinhas**.

## Se der erro depois de trocar

| erro | o que significa | o que fazer |
|---|---|---|
| `401` | chave do provedor errado, ou revogada | confira se a chave é do provedor escolhido; gere outra |
| `404` | o nome do modelo não existe naquele provedor | **Ver modelos da minha chave** e clique no nome certo |
| `429` | cota da conta acabou | troque de modelo (cada um tem cota própria) ou espere o tempo que o provedor disse |
| `conexão` | internet ou provedor fora do ar | tente de novo; se for sempre, volte ao Groq |

## Uma tabela para colar na parede

| provedor | chave começa com | grátis? | pede cartão? |
|---|---|---|---|
| Groq | `gsk_` | sim | não |
| Google Gemini | `AIza` | sim (Flash), com condição | não |
| OpenRouter | `sk-or-v1-` | sim, só `:free` | não |
| Mistral | 32 caracteres, sem prefixo | sim, modo Experiment | não |
| DeepSeek | `sk-` | não | não (mas cobra) |
| Claude | `sk-ant-` | não | sim, para usar |
| OpenAI | `sk-` | não | sim |
| Cerebras | `csk-` | teste de US$ 5 | sim |
| local (llama.cpp) | — | sim | não |
