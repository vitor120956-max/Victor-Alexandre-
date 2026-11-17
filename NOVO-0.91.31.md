# JARVIS 0.91.31 — o conselho estava pior que o erro

A chave funcionou. O problema seguinte apareceu três linhas depois:

    modelo: deepseek/deepseek-chat-v3-0324:free
    NÃO  o modelo … NÃO está na lista.
    Use um destes:
      deepseek/deepseek-chat-v3-0324     ← pago
      deepseek/deepseek-chat-v3.1        ← pago
      deepseek/deepseek-chat             ← pago

O modelo que eu deixei como padrão saiu do catálogo do OpenRouter (eles mudam
toda semana). Até aí, azar. O problema é o conselho: os três nomes sugeridos são
**pagos**. Numa conta gratuita, trocar para qualquer um deles só muda o erro de
lugar — sai o “modelo não existe” e entra “sem crédito”.

## O que muda

**A escolha agora tem regra, não semelhança:**

1. **grátis primeiro** (`:free`) — chave que não gasta crédito não dá susto;
2. **conversa, não ferramenta** — fora embedding, áudio, imagem, moderação;
3. **modelo de verdade** — 8b para cima na frente de 1.7b, que erra demais em
   português;
4. **famílias que já se provaram** (deepseek, llama, qwen, gemma, nemotron…);
5. empate pelo nome — a mesma lista sempre dá a mesma escolha.

**E ele prova antes de gravar.** Um comando:

```bat
cd /d D:\JARVIS
```

```bat
.venv\Scripts\python conferir-ia.py --corrigir
```

Ele lê a lista que **a sua conta** vê, escolhe os melhores candidatos, **testa
cada um com uma chamada real de 8 tokens** e grava no `.env` o primeiro que
responder. Só a linha `JARVIS_AI_MODEL` muda, e antes disso ele guarda uma
cópia do `.env` (`env.antes-AAAAMMDD-HHMMSS`). Se nenhum responder, **nada é
gravado** — e a frase diz o que fazer.

Por que testar: a lista do provedor diz o que **existe**, não o que **responde**.
Um nome recém-morto pode continuar na lista por um tempo. Escolher no papel
seria trocar um 404 por outro.

## O `chave-pela-api.bat` já faz isso

Da 0.91.31 em diante, criar a chave e acertar o modelo são a mesma ação: o
atalho termina conferindo a IA de verdade e, se o modelo do `.env` tiver morrido,
escolhe outro e grava — com backup.

## Testado

- com a **sua lista real** de 17/11, a escolha é `meta-llama/llama-3.3-70b-instruct:free`
  (e nunca os três `deepseek` pagos que o `difflib` propunha);
- embedding e transcrição ficam fora; 70b ganha de 1.7b; a mesma lista dá a
  mesma escolha;
- `--corrigir`: testa antes de gravar, tenta o segundo quando o primeiro falha,
  faz backup, **não grava nada** se nenhum responder, e com o modelo certo não
  mexe em nada.

Suíte: **3.861 testes**, 7 pulados.
