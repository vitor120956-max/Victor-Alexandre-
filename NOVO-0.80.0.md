# JARVIS 0.80.0 — DeepSeek, Claude e os outros: quem é grátis de verdade

Você perguntou: **“não dá para usar modelos tipo DeepSeek ou Claude ou algumas
outras de graça?”**

Dá — mas não todas do jeito que parece. A resposta curta:

| o que você quer | é grátis? | por onde |
|---|---|---|
| **DeepSeek** | **sim**, mas não direto | **OpenRouter**, escolhendo um nome que termina em `:free` |
| **Claude** | **não** | a API do Claude é paga; o site claude.ai é grátis, mas não é API |
| **Google Gemini** | **sim** (modelos Flash) | `aistudio.google.com/apikey` |
| **Groq** | **sim** — o que você já usa | `console.groq.com/keys` |
| **Mistral** | **sim** (modo Experiment) | `console.mistral.ai/api-keys` |
| **OpenAI, Cerebras** | **não** | pagos; a Cerebras virou teste de US$ 5 com cartão |

A partir desta versão o JARVIS **não esconde mais o preço**: a lista de
provedores aparece na tela com “grátis”, “grátis, com condição” ou “não” escrito
em cada um — antes de você criar conta em qualquer lugar.

---

## Passo a passo: DeepSeek de graça (5 passos, sem cartão)

1. abra `openrouter.ai/keys` no navegador do PC;
2. entre com Google ou GitHub (é login, não é pagamento);
3. **Create Key** → nome `jarvis` → copie a chave (começa com `sk-or-v1-`);
4. no JARVIS: **Configurações** → **Modelos de IA** → **Provedor** → **OpenRouter**;
5. **Colar chaves** → cole a `sk-or-v1-…` → salvar.

Pronto. O JARVIS troca o endereço sozinho (a cara da chave diz de quem ela é),
testa na hora e já responde. Se quiser saber **qual** DeepSeek está grátis hoje,
clique em **Ver modelos da minha chave** — a lista vem do próprio OpenRouter e
tudo que termina em `:free` aparece com selo verde.

Limite dos modelos `:free` no OpenRouter: **20 pedidos/min e 50/dia**. Comprou
US$ 10 de crédito uma vez na vida? Sobe para 1.000/dia.

## Passo a passo: Google Gemini (grátis, com uma condição)

1. abra `aistudio.google.com/apikey`;
2. entre com a conta Google;
3. **Create API key** → copie (começa com `AIza`);
4. no JARVIS: **Modelos de IA** → **Provedor** → **Google Gemini**;
5. **Colar chaves** → cole a `AIza…`.

**A condição, dita antes:** fora da União Europeia, Suíça e Reino Unido, o
conteúdo do plano grátis pode ser usado para melhorar os produtos do Google. Se
o que você conversa for sensível, fique no Groq (que não treina com o conteúdo)
ou no modelo local.

## Claude e DeepSeek direto: por que não estão na lista dos grátis

- **Claude:** a Anthropic dá um pequeno crédito inicial e depois cobra. Não
  existe nível grátis recorrente na API. O JARVIS aceita (endereço compatível),
  mas a tela diz **“não”** na coluna de preço.
- **DeepSeek direto:** a API é paga e barata (~US$ 0,28 por milhão de tokens de
  entrada). O `chat.deepseek.com` é grátis, mas é site — o JARVIS não fala com
  site. Para DeepSeek sem pagar, o caminho é o OpenRouter acima.

---

## O que mudou no programa

- **Catálogo de provedores** (`server/provedores.py`): oito casas — Groq,
  Google Gemini, OpenRouter, Mistral, DeepSeek, Claude, OpenAI, Cerebras — cada
  uma com endereço, modelo padrão, cara da chave e uma frase honesta de preço.
- **Uma tela para trocar:** chips de provedor no cartão **Modelos de IA**. Um
  clique grava `JARVIS_AI_PROVIDER`, `JARVIS_AI_BASE_URL` e `JARVIS_AI_MODEL` no
  `.env` e recarrega o cérebro na hora — sem fechar janela.
- **As chaves não se perdem:** ao trocar de casa, as chaves do provedor que sai
  ficam guardadas em `JARVIS_CHAVES_<ID>` e voltam sozinhas se você voltar.
- **Colar chave troca o endereço sozinho:** `gsk_` → Groq, `AIza` → Google,
  `sk-or-v1-` → OpenRouter, `sk-ant-` → Claude, `csk-` → Cerebras. `sk-` sozinho
  **não** chuta (DeepSeek, OpenAI e outros usam o mesmo prefixo) — nesse caso a
  escolha tem de ser sua, na tela.
- **“Ver modelos da minha chave”:** pergunta ao provedor (`GET /models`) quais
  nomes aquela conta enxerga hoje. Nome de modelo envelhece em semanas; a conta
  não. É o botão que acaba com o erro 404 “esse modelo não existe mais”.
- **O catálogo de modelos acompanha o provedor:** escolher Google mostra Gemini,
  não Llama. Antes a lista era sempre a do Groq — convite a colar nome que só
  podia dar 404.
- **O socorro da cota continua só onde faz sentido:** a segunda tentativa com
  `llama-3.1-8b-instant` só acontece no Groq, porque o nome não existe nos outros.
- **As mensagens de chave recusada apontam o painel certo:** antes todo erro
  mandava para `console.groq.com/keys`, mesmo em outro provedor.

## O que **não** foi feito, e por quê

- **Não coloquei Claude na lista de grátis** para “ficar bonito”. A API cobra.
- **Não inventei cotas do Google ou da Mistral**: os números não são públicos
  (aparecem só logado, no painel) e prometer número que não medi é o defeito das
  versões anteriores que já corrigimos.
- **Não somei as chaves de provedores diferentes numa cota só**: cada provedor
  tem a sua conta, o seu limite e o seu preço. A tela mostra um por vez.

## Detalhe que vale saber: `:free` é a linha entre grátis e fatura

No OpenRouter o mesmo modelo existe nas duas formas:
`deepseek/deepseek-chat` **cobra**; `deepseek/deepseek-chat-v3-0324:free` **não**.
Sem o sufixo, é fatura. Por isso a tela pinta o selo verde só quando o nome
termina em `:free` — e o aviso está nas duas telas (chaves e modelos).

## Números medidos

- pytest: **3.328 passed, 2 skipped, 0 failed** (26 testes novos de provedor)
- vitest: **134 passed**
- manifesto: **498 arquivos**
- skills: **315** (nenhuma nova)
