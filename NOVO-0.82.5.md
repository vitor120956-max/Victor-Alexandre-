# JARVIS 0.82.5 — 47 elementos, e todos de mentira

A 0.82.4 funcionou: a repetição acabou. **600 elementos viraram 47.** Mas o
número novo acusou o próximo problema, e ele é o mais importante até agora:

```
chrome.exe — Arena | Benchmark...: 47 elemento(s), 26 acionável(is) — fonte: msaa.
a UIAutomation mostrou 4; a MSAA mostrou mais (47).
```

Os 47 são **todos moldura**: barra de título, barra de rolagem, “alça”. Nenhum
item da página. E a minha regra — “ganha quem mostrou mais” — premiava
exatamente a leitura vazia: 47 pedaços de moldura venciam 4 elementos de página.

## O que mudou

### 1. Conteúdo vence moldura

A escolha entre fontes parou de contar elementos e passou a perguntar **o que**
eles são. Link, texto, item de lista, célula, documento valem mais do que
qualquer quantidade de botão de janela.

| situação | quem ganha |
|---|---|
| uma tem conteúdo, a outra só moldura | a que tem conteúdo |
| navegador (Chrome, Edge, Firefox…) | UIAutomation, mesmo com menos nós |
| nenhuma tem conteúdo | quem mostrou mais (regra antiga) |

### 2. A página mora numa janela filha

A página do Chrome não é um elemento da janela principal. É a janela filha
`Chrome_RenderWidgetHostHWND` — outro processo, outra árvore. Ler só a janela
de topo dá a moldura; foi por isso que a UIA “mostrava 4”.

Agora a leitura varre as janelas filhas (até 24), começando pelas classes que
carregam conteúdo, e fica com a que tiver mais nós. O resumo diz de onde veio:

```
(lido de dentro: Chrome_RenderWidgetHostHWND)
```

### 3. O diagnóstico passou a medir isso

`--diagnostico` agora termina com uma tabela por janela e por fonte:

```
  janela                                  msaa  uia   conteudo
  --------------------------------------------------------------
  Chrome_WidgetWin_1                        47     4   nenhum
    Chrome_RenderWidgetHostHWND              0   812   uia
```

Essa tabela é a resposta definitiva.

## O teste de agora — e é o último que eu peço

```
cd /d D:\JARVIS
```

```
atualizar.bat
```

```
.venv\Scripts\python arvore_sonda.py --alvo chrome --diagnostico
```

**Me mande só a tabela do fim.** Ela tem duas ou três linhas e responde tudo:

- se a linha indentada (`Chrome_RenderWidgetHostHWND` ou parecida) mostrar um
  número em `uia` e **`uia` na coluna conteúdo** → funciona, e eu sigo para a
  etapa 2 (clicar por `ref`);
- se mostrar **`nenhum`** em todas as linhas → o Windows 10 build 14393 do seu
  PC não expõe a página do Chrome. Aí eu **paro com essa história**, digo isso
  na cara e passo a usar `mesa.arvore` só em programas onde ela funciona
  (Bloco de Notas, Explorer, instaladores, Ferramentas do Windows).

## Compromisso, escrito

Depois desta rodada eu não peço mais uma “tentativa” no Chrome. Já foram cinco.
Se a tabela disser `nenhum`, o problema é o sistema, não o código — e insistir
seria fazer você trabalhar de graça para mim.

## O que continua fora

- **Clicar por `ref`** (etapa 2): só depois da tabela mostrar conteúdo.
- **Gmail/Drive/Agenda por OAuth**, **WhatsApp**: como antes.
