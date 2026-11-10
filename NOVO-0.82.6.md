# JARVIS 0.82.6 — a tabela mediu o terminal

Antes de qualquer coisa: **o erro foi meu, não do seu Chrome.**

Você rodou o comando certo, com o alvo certo:

```
.venv\Scripts\python arvore_sonda.py --alvo chrome --diagnostico
```

E a resposta foi esta:

```
  [FALHA] varredura de janelas (1)
  janela                                  msaa  uia   conteudo
  ConsoleWindowClass                         1    12   nenhum
```

`ConsoleWindowClass` é o **terminal onde você digitou o comando**. O diagnóstico
nunca olhou o Chrome.

## O defeito

`diagnostico()` não recebia o handle da janela. Ele chamava sempre
`janela_em_foco()` e ignorava o `--alvo`. A 0.82.3 corrigiu exatamente isso na
**leitura normal** e deixou o diagnóstico de fora — o mesmo erro, no outro
caminho.

A consequência foi pior do que parece: a tabela era a peça que ia decidir a
etapa 2. Uma tabela que mede a janela errada não decide nada. **Não há veredito
sobre o Chrome até esta versão rodar.**

## O que mudou

### 1. O diagnóstico escolhe a janela como a leitura escolhe

A sonda usa o **mesmo** `_escolher` / `arvore.escolher_janela` da leitura e
passa o handle já escolhido:

```python
quadro = leitor.diagnostico(args.alvo, handle=janela_diagnostico["handle"])
```

Não existe uma segunda escolha para divergir da primeira.

### 2. A tabela diz o que está medindo

Antes de qualquer número:

```
  medindo: chrome.exe — Arena | Benchmark...
  classe:  Chrome_WidgetWin_1
```

E a tabela ganhou a coluna **processo**:

```
  janela                            msaa   uia   conteudo  processo
  ------------------------------------------------------------------------
  Chrome_WidgetWin_1                  47     4   nenhum    chrome.exe
    Chrome_RenderWidgetHostHWND        0   812   uia       chrome.exe
```

Se a linha de cima não disser `chrome.exe`, a janela não é o Chrome — e agora
isso salta aos olhos em vez de passar.

### 3. A MSAA também desce as janelas filhas

A 0.82.5 varria as filhas só na UIAutomation. Mas o Chrome publica a página
pela MSAA da janela filha em várias versões. Agora as **duas** fontes descem
até 24 filhas, conteúdo primeiro.

### 4. Há um veredito, medido como a leitura mede

A tabela mostra cada janela **isolada**. A leitura de verdade **agrega** as
filhas. Se o diagnóstico só mostrasse a tabela, você teria que deduzir — e a
dedução podia errar de novo. Então o fim é explícito:

```
  VEREDITO: a leitura vai funcionar — 812 elemento(s) de conteudo, fonte uia.
  lido de dentro de: Chrome_RenderWidgetHostHWND
```

ou

```
  VEREDITO: 12 elemento(s), nenhum de conteudo (fonte uia).
```

## O que fazer agora

Uma rodada, o mesmo comando de antes:

```
.venv\Scripts\python arvore_sonda.py --alvo chrome --diagnostico
```

Agora ele mede o Chrome. Confira duas coisas: a linha `medindo:` diz
`chrome.exe`, e o `VEREDITO` fala de conteúdo.

## O compromisso continua de pé

Se a tabela **do Chrome** disser `nenhum` em todas as linhas e o veredito vier
sem conteúdo, eu **encerro a leitura do Chrome neste PC**. Não peço outra
rodada, não mudo a pergunta: passo para Explorer, Bloco de Notas e instaladores,
que publicam árvore clássica, e a etapa 2 (clique por `ref`) é medida lá.

O que eu não faço é concluir sobre o Chrome com uma tabela que mediu o
terminal.
