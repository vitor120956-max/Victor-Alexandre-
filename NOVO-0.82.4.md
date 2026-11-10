# JARVIS 0.82.4 — a causa raiz das repetições

Você rodou `--alvo chrome` e a janela certa foi lida. Mas a árvore continuou
repetindo — e agora dava para ver **o que** repetia:

```
barra de rolagem “Vertical”
  botão “Uma linha acima”
    botão “Uma linha acima”
      botão “Uma página acima”
        botão “Uma linha acima” ...
```

Não era a moldura da janela. Era a **barra de rolagem**. E a culpa não era do
Chrome.

## O defeito era uma linha minha

```python
usar = ponteiro_filho or ponteiro      # <- aqui
```

A MSAA tem dois tipos de filho:

| tipo | o que é | tem filhos? |
|---|---|---|
| **objeto** | objeto COM de verdade, com ponteiro próprio | sim |
| **simples** | só um número de identificação dentro do pai | **não** |

Para um filho simples, `get_accChildCount` **no pai** devolve os filhos *do
pai*. Ao reusar o ponteiro do pai, eu pedia ao pai que listasse os próprios
filhos — de novo, e de novo, até o limite de 600. Os 475 “acionáveis” do Chrome
eram o mesmo punhado de botões, lidos repetidamente.

O certo: **elemento simples entra na árvore (nome e papel são lidos dele), mas
não se desce nele.**

## Três defesas agora, não uma

| defesa | onde | o que faz |
|---|---|---|
| **origem** | `arvore_windows.py` | filho simples não desce — a correção de verdade |
| **montagem** | `arvore.py` | repetição é cortada mesmo vindo de sonda antiga |
| **alarme** | resumo | se ainda repetir, o texto avisa em vez de fingir |

E a distinção ficou explícita:

- **moldura** (Minimizar, Fechar, IME): o nó é real, entra na árvore e para ali;
- **repetição** (o mesmo nó dentro de si mesmo): não é nó novo, **não entra**.

## Navegador agora vai direto na UIA

No seu PC, a MSAA do Chrome devolveu **600 elementos, nenhum da página** — só
barra de rolagem e barra de título. A árvore de verdade está na UIAutomation.

Chrome, Edge, Brave, Opera, Vivaldi, Firefox, VS Code, Cursor, Slack, Discord,
Spotify, WhatsApp, Notion e Figma agora **sempre** tentam a UIA, mesmo que a
MSAA venha grande. Para os outros programas continua valendo a regra antiga:
árvore rica na MSAA não paga segunda leitura.

## O teste de agora

Com o **Chrome** aberto e na frente:

```
cd /d D:\JARVIS
```

```
atualizar.bat
```

```
.venv\Scripts\python arvore_sonda.py --alvo chrome
```

Agora a linha de resumo deve dizer algo como:

```
chrome.exe — Arena | Benchmark...: N elemento(s), M acionável(is) — fonte: uia.
```

O que eu preciso: **o N e o M**, e se aparece **nome da página** (título, link,
botão do site) em vez de “Uma linha acima”.

Se ainda vier pouco:

```
.venv\Scripts\python arvore_sonda.py --alvo chrome --fonte uia --limite 1500
```

## Sendo honesto sobre o histórico

Esta é a quarta versão seguida em que a leitura vem vazia ou errada no seu PC.
Cada vez o defeito foi diferente, e cada um só apareceu porque você rodou e me
mandou a saída. Não é o desenho que está errado — é que eu não tenho Windows
aqui e estava adivinhando o comportamento do COM.

O que mudou nesta: a causa era **estrutural** (uma linha que pedia a lista
errada), não um ajuste de heurística. Se o número ainda vier baixo depois
desta, eu digo que a MSAA/UIA desse Windows 10 de 2016 não serve para o Chrome
e paro de insistir — em vez de te fazer rodar uma quinta vez à toa.

## O que continua fora

- **Clicar por `ref`** (etapa 2): continua sem entrar. Depois de quatro
  tentativas, a etapa 1 precisa mostrar conteúdo de verdade **duas vezes
  seguidas** antes de eu prometer clique.
- **Gmail/Drive/Agenda por OAuth**, **WhatsApp**: como antes.
