# JARVIS 0.89.6 — o programa está instalado

O diagnóstico respondeu o que faltava saber:

```
O Bloco de notas (notepad.exe) não está aberto.
Instalado em: C:\Windows\system32\notepad.exe
```

**Existe.** O problema nunca foi o programa — era o caminho até ele. Com essa
linha, o JARVIS sabe exatamente qual arquivo abrir.

## Dois furos que eu achei revisando

Revisando o caminho de ponta a ponta antes de te mandar o comando de novo,
encontrei duas falhas que só aparecem no instante em que o programa nasce:

**1. A lista de janelas ficava velha.** Era lida *antes* de abrir o programa —
quando ele ainda não existia. Depois de abrir, o plano e a mensagem de erro
falavam de uma janela que não era a nova. Agora a lista é relida depois.

**2. A sondagem roubava a janela recém-aberta.** Se já houvesse um Bloco de
Notas antigo aberto — e há, das nossas tentativas —, ele também tem campo de
escrita. A rotina que escolhe "a janela que serve" podia escolher a **antiga**.
Isso é escrever no arquivo errado, e o arquivo errado pode ser o documento de
alguém.

Agora: **se eu acabei de abrir, a janela é a que eu abri.** Sem sorteio.

## O comando

```
cd /d D:\JARVIS
```

```
atualizar.bat
```

Depois, **feche todos os Blocos de Notas** (o X de cada um) — inclusive os das
tentativas anteriores, que podem ter texto dentro. Aí:

```
.venv\Scripts\python arvore_sonda.py --programa "bloco de notas" --escrever "oi, mundo" --executar
```

O que eu espero, em texto (não copie nada disso):

- a linha começa com `Abri o Bloco de notas.` e continua com
  `Feito: digitar 'oi, mundo'` e `(conferi: o texto está no campo)`
- abaixo vêm `janela:`, `alvo:`, `onde:`, `fonte:`, `abri:` com
  `C:\Windows\system32\notepad.exe`
- `como:` dirá `valor do campo (put_accValue, sem teclado)` — é o caminho que
  já escreveu de verdade duas vezes neste PC

Se parar antes, a mensagem agora diz **quantas janelas do programa existem e o
que cada uma publica**, então uma rodada basta para eu saber onde está o
problema.

## O que já está provado neste PC

- ele **escreve** no Bloco de Notas e **confere lendo de volta** (0.87.1/0.88.0)
- ele **acrescenta** sem apagar (0.88.0)
- ele **acha o programa** pelo caminho certo (0.89.5)
- o que faltava era só **abrir** e escolher a janela certa — esta versão.
