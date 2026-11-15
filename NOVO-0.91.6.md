# JARVIS 0.91.6 — o 400 agora diz o que fazer

O dossiê saiu inteiro no seu PC. O passo 3 parou com:

```
O provedor não respondeu (AIUnavailable): o provedor de IA respondeu com HTTP 400.
```

Isso já é melhor que "AIUnavailable" sozinho, mas ainda não serve: **400 não é
chave nem cota**. Chave recusada é 401, cota estourada é 429. 400 é *pedido
recusado* — e o provedor tinha escrito o motivo, mas o JARVIS jogou fora.

## 1. O motivo estava lá e foi descartado

O JARVIS só sabia ler o motivo em dois formatos (`error.message` e `message`).
Se o provedor respondesse em qualquer outro — `detail` (servidor de modelo
local usa esse), `error` como texto, HTML de proxy —, a mensagem virava
**vazia** e você lia só "HTTP 400".

Agora, quando o formato não é reconhecido, ele mostra o corpo cru, limpo de
chave e de endereço, cortado em 300 caracteres. Ver o que o provedor escreveu,
mesmo feio, é melhor que não ver nada.

## 2. A frase do 400 agora diz o que fazer

```
o provedor recusou o pedido (HTTP 400) — não é a chave nem a cota.
Quase sempre é o nome do modelo, que muda sem aviso nos planos grátis.
Rode `.venv\Scripts\python conferir-ia.py` na pasta do JARVIS: ele lista os
modelos que a sua chave vê e diz se o nome atual está entre eles.
```

## 3. `conferir-ia.py` — o comando que resolve

Novo arquivo na pasta do JARVIS. Ele não gasta cota de geração: pergunta ao
provedor a **lista de modelos que a sua chave vê** (é leitura de catálogo).

```
py conferir-ia.py
py conferir-ia.py --testar    # manda 8 tokens de verdade
```

Ele mostra provedor, endereço, modelo, quantas chaves (mascaradas) e então:

```
LISTA DE MODELOS: 12 que a sua chave vê.
llama-3.3-70b-versatile, llama-3.1-8b-instant, …

NÃO  o modelo “llama-3.3-70b-versatile-antigo” NÃO está na lista.
Use um destes:
  llama-3.3-70b-versatile
```

A chave nunca aparece inteira, e há teste para isso.

## Por que isso importa

Nome de modelo grátis muda sem aviso. O do Groq não existe no OpenRouter, e
vice-versa: `llama-3.3-70b-versatile` (Groq) contra
`meta-llama/llama-3.3-70b-instruct` (OpenRouter). Quando a chave é de um
provedor e o nome do modelo é de outro, o provedor responde **400** — e não
401, porque a chave está boa.

Antes, isso virava "o provedor não respondeu". Agora vira uma frase que diz
onde trocar e um comando que confirma.

## Testes

Cinco novos: corpo não-JSON aparece na mensagem; corpo com `detail` aparece; a
frase do 400 orienta e não culpa a chave; a chave nunca vaza na mensagem; e o
`conferir-ia.py` aponta o modelo errado e sai com erro.

## O que continua sem prova

Não sei ainda **qual** é o seu caso — se é nome de modelo, se é tamanho de
pedido. O `conferir-ia.py` responde isso na primeira linha, e é por isso que
ele existe: eu poderia ficar chutando, mas o dado está a um comando de
distância.
