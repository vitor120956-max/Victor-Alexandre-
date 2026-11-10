# JARVIS 0.83.0 — o Chrome não entrega a página; agora eu sei onde trabalhar

Esta versão fecha uma pergunta e abre a certa.

## A resposta sobre o Chrome

Medindo a janela certa, como a 0.82.6 faz:

```
  medindo: chrome.exe — Arena | Benchmark & Compare the Best AI Models - Google Chro
  classe:  Chrome_WidgetWin_1

  janela                            msaa   uia   conteudo  processo
  ------------------------------------------------------------------------
  Chrome_WidgetWin_1                   4     4   nenhum   chrome.exe
    Chrome_RenderWidgetHostHWND        1     1   nenhum   chrome.exe
    Chrome_RenderWidgetHostHWND        1     1   nenhum   chrome.exe

  VEREDITO: 4 elemento(s), nenhum de conteudo (fonte uia).
```

As duas janelas filhas que deveriam conter a página entregaram **1 elemento
cada**. A página não está lá — nem pela MSAA, nem pela UIAutomation.

**Eu encerro o Chrome neste PC**, como prometi. Sem sétima rodada, sem nova
pergunta. Este Chrome do `Windows 10.0.14393`, nesta máquina, não publica o
conteúdo da página para um leitor de acessibilidade. Sem foto e sem OCR — que
você não quer e que eu não faria —, não há o que ler.

Isso não é um defeito que a próxima versão resolve. É o programa.

## O que ficou pronto

### 1. Toda leitura diz se serve para agir

O número sozinho enganou por seis versões. “47 elementos” parecia bom; eram 47
botões de janela. Agora a resposta vem junto:

```
  NAO SERVE para agir: a janela publicou só moldura (barra de título,
  rolagem, botões de janela). Esta é a mesma parede que o Chrome deu neste PC.
```

E quando serve:

```
  SERVE para agir: 31 elemento(s) de árvore, 6 acionável(is) e 5 com nome
  ou escrita — dá para agir por `ref`.
```

A conta está em `arvore.prontidao()`, com os números à mostra: total,
acionáveis, com nome, editáveis. Ela recusa moldura mesmo com 600 botões, e
aceita o campo do Bloco de Notas, que não tem nome nenhum — porque é onde se
escreve.

O `mesa.arvore` também devolve `pronto`: o JARVIS sabe disso antes de tentar.

### 2. Um comando mede todas as janelas abertas

Seis mensagens suas foram gastas medindo um programa por vez. Agora é uma:

```
.venv\Scripts\python arvore_sonda.py --provados
```

```
  janela aberta                        elementos  conteudo  serve?  fonte  seg
  ------------------------------------------------------------------------------
  notepad.exe        Sem título - B...       31  sim        SIM     uia   0.4
  explorer.exe       Downloads               88  sim        SIM     msaa  0.9
  chrome.exe         Arena | Benchmar...      4  nao        nao     uia   1.2

  2 de 3 janela(s) servem para o JARVIS agir:
    - notepad.exe — Sem título - Bloco de notas
    - explorer.exe — Downloads

    .venv\Scripts\python arvore_sonda.py --alvo "notepad.exe"
```

Tem teto de 60 segundos: uma janela travada não vira espera sem fim, e o que
não foi medido é dito.

### 3. Consertei a ordem que estragava a medição

Na 0.82.6 a coluna MSAA do Chrome saiu com **4**, quando a leitura da 0.82.4
tinha achado **47** na mesma janela. A diferença: a UIA já tinha aberto a
janela antes da medição da MSAA.

Não sei dizer por que o Windows muda o número — e não vou inventar. Sei o que
resolve: medir na ordem em que a leitura mede. Agora a MSAA vem primeiro, e o
veredito é a **própria `ler_janela`**, não uma segunda implementação dela.

### 4. Uma correção de conteúdo

`tem_conteudo()` exigia nome no elemento. Isso recusaria o campo do Bloco de
Notas, que não tem nome — o programa mais simples que existe. Documento e área
de edição (papéis 15 e 42) agora contam mesmo sem nome. Moldura de janela nunca
tem esses papéis, então a regra “conteúdo vence moldura” continua de pé.

## O que fazer agora

Um comando, com o Bloco de Notas e o Explorer abertos:

```
.venv\Scripts\python arvore_sonda.py --provados
```

Ele diz **em quais programas** o JARVIS consegue trabalhar neste PC. Com essa
lista, a etapa 2 (clicar por `ref`) deixa de ser aposta: ela é medida nos
programas que publicam árvore.

## O que eu não fiz, e por quê

- **Não cliquei em nada.** A etapa 2 continua dependendo de uma leitura válida,
  e agora ela tem um nome e um número: `pronto: true`.
- **Não insisti no Chrome.** Encerrado, como combinado.
- **Não prometo que todo programa vai servir.** O `--provados` é justamente
  para não prometer: ele mede e mostra.
