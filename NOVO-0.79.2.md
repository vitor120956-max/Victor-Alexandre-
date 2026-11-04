# JARVIS 0.79.2 — por que as 4 chaves falharam juntas (e o que fazer)

Seu print: quatro chaves coladas, aviso verde **“4 chaves guardadas”** e, dois
segundos depois, vermelho **“Nenhuma das 4 respondeu agora”**.

O JARVIS estava dizendo a verdade e não dizendo **nada de útil**. Corrigido nas
duas pontas: o diagnóstico e a explicação.

---

## 1. A causa mais provável: cota é da **conta**, não da chave

No Groq — e em quase todo provedor — o limite é **por organização/conta**, não
por chave. Quatro chaves criadas no mesmo login (`console.groq.com`, mesmo
e-mail) **dividem o mesmo limite**. Elas não somam cota.

Então, se a conta estourou o dia, as quatro dão `429` juntas. É exatamente o
padrão do seu print.

> Isso corrige uma promessa minha das versões anteriores: eu tratei “três
> chaves” como “três cotas”. Não é. Chaves servem para **trocar quando uma
> falha**, não para multiplicar limite.

## 2. A alavanca que funciona: **trocar de modelo**

Cada **modelo** tem a sua própria cota, mesmo dentro da mesma conta:

| modelo | cota grátis (ordem de grandeza) |
|---|---|
| `llama-3.3-70b-versatile` (padrão) | ~1.000 pedidos/dia · 100 mil tokens/dia |
| `llama-3.1-8b-instant` | ~14.400 pedidos/dia · 500 mil tokens/dia |
| `openai/gpt-oss-120b` | ~1.000 pedidos/dia · 200 mil tokens/dia |

Com a conta estourada no 70B, o `llama-3.1-8b-instant` **ainda responde com a
mesma chave**. É o socorro mais barato que existe: custo zero, sem conta nova,
sem esperar o dia virar.

## 3. O botão **Testar** agora investiga

O que ele passou a fazer quando uma chave falha:

1. lê a **mensagem do provedor** e mostra o número que importa —
   *“tente de novo em 12m34s — limite 100000, usado 100000”* — em vez de só
   “HTTP 429”;
2. se a falha for **429** (limite) ou **404** (modelo inexistente), testa
   **uma vez** com `llama-3.1-8b-instant`;
3. se esse responder, a tela diz **“a chave é válida: o modelo X é que está
   indisponível”** e oferece o botão **Usar llama-3.1-8b-instant**;
4. se as quatro derem **401**, diz que é chave mesmo (revogada ou copiada pela
   metade), sem te mandar esperar à toa.

O segundo teste custa 8 tokens e só roda quando o primeiro falha.

## 4. O que eu **não** posso saber daqui

Só você pode ver, no painel do Groq, *quando* a conta estourou e *qual* limite
bateu (minuto ou dia). O teste mostra o que o provedor respondeu; a decisão de
esperar, trocar de modelo ou criar conta nova é sua — e agora com o número na
mão, não no escuro.

## ⚠️ Importante: as 4 chaves que você colou aqui

Você colou as quatro chaves **no chat**. Quem vê esta conversa vê as chaves.
Faça isto hoje, na ordem:

1. abra `console.groq.com/keys`;
2. **revogue as quatro** (Delete/Revoke em cada uma);
3. crie uma chave nova;
4. cole **na tela do JARVIS** — Configurações → Chaves de IA → **Colar chaves**.

Revogar não zera a cota da conta; só impede que alguém use a chave no seu lugar.

## O caminho mais curto, agora

1. revogue as 4 e crie 1 nova (item acima);
2. **Testar** no cartão Chaves de IA — ele agora diz se é chave, cota ou modelo;
3. se disser cota, clique em **Usar llama-3.1-8b-instant**;
4. se ainda faltar cota no dia, o socorro seguinte é o **modelo local**
   (`ia.local`), que não tem conta nem limite.

## Números

- pytest: **3.302 passed, 2 skipped, 0 failed**
- vitest: **134 passed**
- manifesto: **493 arquivos**
- skills: **315** (nenhuma nova)
