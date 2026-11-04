# JARVIS 0.80.2 — `usar-google.bat`: a chave do Google em dois cliques

Você colou a chave do Google aqui de novo. Colar no chat **não instala nada** —
o JARVIS desta máquina lê a chave do `.env`, e o `.env` só nasce quando a chave
é digitada **no seu PC**. Então o que faltava não era a chave: era o caminho até
o `.env`.

Agora existe um `.bat` para isso, igual ao do OpenRouter.

## O que fazer, na ordem

1. **Revogue a chave que apareceu no chat** (ela foi colada duas vezes):
   abra `aistudio.google.com/apikey`, apague essa e clique em **Create API key**;
2. copie a chave nova;
3. no PC, na pasta do JARVIS, **duplo clique em `usar-google.bat`**;
4. quando ele pedir, **cole a chave** (ela não aparece na tela enquanto você
   digita) e aperte Enter;
5. no fim ele mostra `ok` se o Google respondeu.

Se aparecer `ok`, acabou: a tela do JARVIS já usa a chave nova sozinha, sem
reiniciar e sem fechar nada.

## Por que o `.bat` e não a tela

Os dois caminhos funcionam. O `.bat` serve para quando:

- a tela ainda está na versão antiga (o `atualizar.bat` resolve, mas é mais um
  passo);
- você prefere não abrir o navegador.

Dentro dele, o que roda é exatamente isto:

```
.venv\Scripts\python configurar-chave.py --provedor google --testar
```

## O que os dois `.bat` fazem

| arquivo | provedor | chave começa com | grátis? |
|---|---|---|---|
| `usar-google.bat` | Google Gemini | `AIza…` ou `AQ.…` | sim, nos modelos Flash |
| `usar-openrouter.bat` | OpenRouter | `sk-or-v1-…` | sim, só nos modelos `:free` |

Nenhum dos dois precisa de cartão. Nenhum instala nada. Os dois pedem a chave sem
eco, gravam no `.env` desta máquina e testam na hora.

## A condição do Google, dita de novo

Fora da União Europeia, Suíça e Reino Unido, o conteúdo do plano grátis **pode
ser usado para melhorar os produtos do Google**. Se o que você conversa com o
JARVIS for sensível, use o Groq (que não treina com o conteúdo) ou o modelo
local — os dois continuam funcionando.

## Números medidos

- pytest: **3.341 passed, 2 skipped, 0 failed**
- vitest: **134 passed**
- manifesto: **502 arquivos**
- skills: **315** (nenhuma nova)
