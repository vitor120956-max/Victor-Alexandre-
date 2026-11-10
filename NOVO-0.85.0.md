# JARVIS 0.85.0 — os 26 acionáveis eram todos moldura

A leitura do Bloco de Notas que você mandou:

```
notepad.exe — Sem título - Bloco de notas: 49 elemento(s), 26 acionável(is) — fonte: msaa.
  SERVE para agir: 49 elemento(s) de árvore, 26 acionável(is) e 26 com nome ou escrita.
```

Vinte e seis acionáveis. Fui ver quais eram:

```
botão “IME”            botão “Minimizar”     botão “Maximizar”
botão “Fechar”         botão “Uma linha acima”
botão “Uma página acima”   botão “Uma página abaixo”   alça
```

**Moldura inteira.** E o campo onde se escreve, que é o único lugar que
importa num Bloco de Notas, aparecia assim:

```
texto  em 227,559 (970x140)
```

Sem `ref`. Nem o JARVIS podia digitar nele, nem a minha frase “dá para agir”
era verdade.

## As duas contas erradas

### 1. A prontidão contava botão de janela como trabalho

O critério era “existe acionável com nome”. Os 26 botões de moldura têm nome,
então passavam. Agora moldura é reconhecida e **contamina os filhos** — os
botões dentro da barra de título continuam moldura mesmo com papel de “botão”:

| conta antes | conta agora |
|---|---|
| 26 acionáveis → serve | 26 de moldura + 1 onde se escreve → serve pelo campo |

### 2. O campo de escrita não era acionável

A MSAA não dá ação padrão a um campo de texto, e a minha tabela de papéis
acionáveis não incluía `texto`. Agora papel `texto` (42) e `documento` (15)
com caixa na tela recebem a ação **digitar** — e ganham `ref`.

E só quando a janela deixa: eu leio `get_accState` e recuso se vier
`STATE_SYSTEM_READONLY`. Um painel de log também é papel de texto e não aceita
escrita; prometer digitação ali seria mentira na árvore.

## Como a sua leitura vai sair agora

```
notepad.exe — Sem título - Bloco de notas: 49 elemento(s), 26 acionável(is) — fonte: msaa.
Todos os acionáveis são moldura (fechar/minimizar/rolagem); o lugar de escrever é @7625b028:e10.

  SERVE para agir: 49 elemento(s) de árvore, 1 onde se escreve — dá para agir por `ref`.
  Onde escrever: @7625b028:e10 em 227,559 (970x140)

  texto  @7625b028:e10  em 227,559 (970x140)  (escreve aqui)
```

E o `--provados` passa a dizer onde cada janela aceita escrita:

```
  - notepad.exe — Sem título - Bloco de notas — escreve em 227,559
```

## Por que isto vem antes do clique

A etapa 2 (clicar por `ref`) ia ser inútil do jeito que estava: o elemento que
o JARVIS precisa — o campo onde se escreve — não tinha `ref`. Eu ia entregar
um clique que só sabia fechar janela.

Agora o alvo existe, tem nome, tem posição e tem `ref`. **A próxima versão é o
clique e a digitação por `ref`**, com `--executar` obrigatório para agir.

## O comando

```
cd /d D:\JARVIS
```

```
atualizar.bat
```

```
.venv\Scripts\python arvore_sonda.py --alvo "notepad.exe"
```

Me mande a saída. Quero ver o `(escreve aqui)` e o `Onde escrever:` na tela
antes de ligar o braço.
