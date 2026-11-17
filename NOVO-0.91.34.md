# JARVIS 0.91.34 — o “oi” parecia a IA. Não era.

Seu print de 17/11 mostra a tela do JARVIS em `127.0.0.1:8000`: você mandou
**“oi”**, ele respondeu na hora — *“Olá, Victor. Estou por aqui. Você pode me
pedir uma tarefa…”* — e você perguntou **“funcionou?”**.

Aquela frase não veio do modelo. Ela é a **skill local de saudação**
(`case 'greeting'`): texto fixo, dentro do programa, sem chave, sem internet,
sem gastar cota. O “oi” nunca chegou ao OpenRouter.

O defeito não é a saudação existir — é ela responder **igual ao modelo
responderia**, sem nada na tela dizendo de onde veio. Depois de doze versões
consertando chave, modelo e cota, a primeira prova na tela não provava nada.

## O que muda

- **A saudação se declara local.** Ela agora termina dizendo, com essas
  palavras, que aquela resposta é local e sem IA — e ensina o comando que prova
  o resto.
- **Existe um comando que fala com o modelo de verdade: `testar ia`.** Também
  aceita “conferir a ia”, “verificar a ia”, “a ia está funcionando?”, “a ia
  responde?”, “status da ia”. Ele manda `Responda apenas: ok` para
  `/api/ai/chat`, **cronometra** e responde com o provedor e o tempo — e a
  mensagem sai marcada `· IA EXTERNA` no balão, a mesma marca do modelo.
- **Se falhar, ele diz o que conserta.** Em vez de “erro”, a tela mostra que a
  IA externa não respondeu, o motivo, e o comando `conferir-ia.py --corrigir`.
- **Sem backend ou sem chave, ele explica** — não finge ter testado.
- **O parser ganhou 13 formas de pedir o teste sem roubar os vizinhos**:
  “status do sistema”, “testar python” e “testar conexão” continuam indo para
  onde iam.

“oi” continua respondendo na hora e sem gastar cota, de propósito. O que muda é
que agora ele **avisa** que é local.

## Como provar na sua tela

Primeiro, pegue a versão:

```bat
cd /d D:\JARVIS
```

```bat
atualizar.bat
```

Depois abra o JARVIS:

```bat
iniciar-jarvis.bat
```

E, na conversa, diga:

```text
testar ia
```

O que você deve ver: uma frase dizendo que a **IA externa respondeu**, em
quantos milissegundos, e qual provedor atendeu — com `· IA EXTERNA` no canto da
mensagem. Se ela disser que **não** respondeu, o próprio recado traz o comando
que conserta; rode-o e mande `testar ia` de novo.

## Testado

- a saudação diz “resposta é local” e ensina `testar ia` (antes não dizia nada);
- o comando chama `/api/ai/chat`, cronometra, marca `'ai'` e cita o
  `conferir-ia.py --corrigir` na falha;
- sem API ou sem chave, explica em vez de fingir;
- 13 formas de pedir o teste; “status do sistema” e “testar python” não são
  capturados;
- o balão continua marcando `· IA EXTERNA` / `· SKILL PYTHON`.

Rodei esses testes contra a **0.91.33**: 5 dos 6 de origem falham e 18 dos novos
da interface falham. Contra a 0.91.34, passam todos.

Suíte: **3.884 testes de API** (7 pulados) e **153 testes web**.

## Um comando, se quiser medir sem abrir a tela

```bat
.venv\Scripts\python conferir-ia.py --testar
```
