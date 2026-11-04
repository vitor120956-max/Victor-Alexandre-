# JARVIS 0.80.1 — a chave nova do Google e o caminho sem a tela

Duas coisas nesta versão, as duas nascidas de chaves que você colou no chat.

## 1. A chave `AQ.…` do Google agora é reconhecida

O AI Studio mudou o formato da chave. Antes era `AIza…`; agora o painel entrega
algo como `AQ.Ab8…`. O JARVIS conhecia só o formato antigo — então essa chave,
colada em **Colar chaves**, era recusada com *“não encontrei nenhuma chave no que
foi colado”*, mesmo estando certa.

Corrigido nos três lugares que leem chave:

- a tela (`server/chaves.py`);
- o script de terminal (`configurar-chave.py`);
- a dedução de provedor (`server/provedores.py`: `AQ.` → Google Gemini).

Os dois formatos continuam aceitos: quem tem chave antiga não perde nada.

## 2. `usar-openrouter.bat` — DeepSeek de graça sem abrir a tela

Duplo clique e ele faz o serviço:

1. aponta o JARVIS para o **OpenRouter**;
2. pede a chave **sem mostrar o que você digita**;
3. grava no `.env` e **testa na hora**.

A tela do JARVIS passa a usar a chave nova sozinha — não precisa reiniciar.

Pelo terminal, o mesmo caminho ficou mais curto: `--provedor` agora aceita o id
do catálogo e preenche endereço e modelo sozinho.

```
.venv\Scripts\python configurar-chave.py --provedor openrouter --testar
```

`--provedor` aceita: `groq`, `google`, `openrouter`, `mistral`, `deepseek`,
`anthropic`, `openai`, `cerebras`. Sem `--provedor`, a cara da chave decide
(`gsk_` → Groq, `sk-or-v1-` → OpenRouter, `AIza`/`AQ.` → Google, `sk-ant-` →
Claude, `csk-` → Cerebras). Um `sk-` solto continua **não** decidindo nada — ele
serve a DeepSeek, OpenAI e outros, e chutar mandaria a chave para a porta errada.

O resumo impresso agora mostra o **preço** do provedor, além de endereço e
modelo: *“grátis só nos modelos :free”*, *“pago, por token (barato)”*.

---

## ⚠️ Chaves coladas no chat

As duas chaves que você colou aqui estão expostas a quem vê a conversa. O certo,
hoje:

1. **OpenRouter**: abra `openrouter.ai/keys` → **Delete** na chave que passou
   por aqui → **Create Key** → cole só na tela do JARVIS (ou no `.bat`).
2. **Google**: abra `aistudio.google.com/apikey` → apague a chave exposta →
   crie outra.

Revogar não devolve cota; só impede que usem a chave no seu lugar. E o hábito que
resolve de vez: **chave não vai para o chat**, vai para o campo escuro da tela.

---

## Números medidos

- pytest: **3.338 passed, 2 skipped, 0 failed**
- vitest: **134 passed**
- manifesto: **500 arquivos**
- skills: **315** (nenhuma nova)
