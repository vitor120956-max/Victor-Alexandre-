# A árvore da janela: ver os elementos sem tocar (0.82.0)

Etapa 1 do que o [`vercel-labs/agent-desktop`](ANALISE-AGENT-DESKTOP.md) propõe.
O `mesa.py` antigo só via **títulos** de janela e clicava por coordenada que você
ditava — sem saber se acertou. Aqui o JARVIS passa a **ler** o que a janela
publica sobre si mesma.

## Etapa 2: agir por `ref` (0.86.0)

A leitura do Bloco de Notas entregou o alvo:

```
texto  @4ab283d9:e11  em 227,559 (970x140)  (escreve aqui)
Onde escrever: @4ab283d9:e11 em 227,559 (970x140)
```

Com um alvo que tem nome, posição e `ref`, o braço pode existir:

```
.venv\Scripts\python arvore_sonda.py --alvo "notepad.exe" --ref @4ab283d9:e11 --acao digitar --texto "oi"
```

```
  Ação pronta (nada foi feito): digitar 'oi' em texto em 227,559 (970x140)

  janela:  notepad.exe — Sem título - Bloco de notas
  alvo:    @4ab283d9:e11  texto “”
  onde:    227,559 (970x140)
  fonte:   msaa   leitura: 4ab283d9

  repita o comando com --executar para fazer de verdade.
```

Sem `--executar`, **nada é tocado**. Com ele:

```
  Feito: digitar 'oi' em texto em 227,559 (970x140)
  como:    foco + teclado
```

### A regra que manda em tudo: `ref` não sobrevive à leitura

`ref` não é o nome do elemento — é o número dele naquela leitura. A tela muda.
Por isso **todo `agir` relê a janela antes** e procura o ref na leitura nova:

```
o ref @antigo:e12 não existe nesta leitura — ele deve ser de uma leitura
anterior, e a tela já mudou. Refs válidos agora: @4ab283d9:e11, ...
```

Um `ref` velho nunca vira alvo por acaso. É a diferença entre um braço e um
chute.

### Sem mover o mouse

A ação vem do próprio elemento:

| ação | como |
|---|---|
| clicar | `accDoDefaultAction` — a ação que o programa declara |
| sem ação padrão | `accSelect(TAKEFOCUS)` — o mesmo que um clique faria |
| digitar | foco no elemento, depois teclado (Unicode) |
| recusa de foco | **para** e diz; digitar sem foco iria para outra janela |

Isso não é preferência estética: no seu PC a tela não responde a toque e não há
mouse USB. Clicar por coordenada seria o único caminho que não funciona ali.

### O que é recusado, e por quê

| pedido | resposta |
|---|---|
| `ref` de leitura anterior | recusa e lista os refs válidos agora |
| moldura (Fechar, Minimizar, rolagem) | recusa — não é trabalhar no programa |
| digitar em botão | recusa com a ação que o elemento aceita |
| digitar sem texto | recusa |
| agir sem `--executar` | mostra o plano e para |

### No chat

`mesa.agir` faz o mesmo pelo JARVIS, com `executar` explícito e confirmação.
A etapa 2 deixou de ser promessa: é a skill `mesa.agir`.

## Os 26 acionáveis eram moldura (0.85.0)

A leitura do Bloco de Notas, no PC do usuário:

```
notepad.exe — Sem título - Bloco de notas: 49 elemento(s), 26 acionável(is) — fonte: msaa.
  SERVE para agir: 49 elemento(s) de árvore, 26 acionável(is) e 26 com nome ou escrita.
```

26 acionáveis. E olhando a árvore, quais eram: **IME, Minimizar, Maximizar,
Fechar**, os botões das duas barras de rolagem e uma alça. Moldura inteira.

O campo onde se escreve aparecia assim:

```
texto  em 227,559 (970x140)
```

Sem `ref`. A MSAA não dá ação padrão a um campo de texto, e a minha tabela de
papéis acionáveis não incluía `texto`. Ou seja: **o JARVIS não tinha como
digitar no Bloco de Notas**, e a prontidão dizia “dá para agir”.

### Duas contas erradas, uma causa

1. **A prontidão contava botão de janela como ação.** 26 botões de moldura
   passavam no critério “existe acionável com nome”. Agora moldura é
   reconhecida — por papel (barra de título, rolagem, alça, status, indicador)
   e por nome (IME, Minimizar, Maximizar, Fechar, “uma linha acima”…) — e
   **contamina os filhos**: os botões dentro da barra de título são moldura
   mesmo que o papel deles seja “botão”.

2. **O lugar de escrever não era acionável.** Papel `texto` (42) e `documento`
   (15) com caixa na tela passam a receber a ação **digitar** — e portanto um
   `ref`. Só quando a janela deixa: `get_accState` é consultado e
   `STATE_SYSTEM_READONLY` recusa. Um painel de log também é “texto”, e
   prometer escrita ali seria mentira.

A leitura do Bloco de Notas agora sai assim:

```
notepad.exe — Sem título - Bloco de notas: 49 elemento(s), 26 acionável(is) — fonte: msaa.
Todos os acionáveis são moldura (fechar/minimizar/rolagem); o lugar de escrever é @7625b028:e10.

  SERVE para agir: 49 elemento(s) de árvore, 1 onde se escreve — dá para agir por `ref`.
  Onde escrever: @7625b028:e10 em 227,559 (970x140)

  texto  @7625b028:e10  em 227,559 (970x140)  (escreve aqui)
```

E `--provados` diz onde cada janela aceita escrita:

```
  - notepad.exe — Sem título - Bloco de notas — escreve em 227,559
```

## O Chrome acordou (0.84.0)

A medição que virou o quadro, no PC do usuário, dois comandos seguidos sem
tocar em nada:

```
1ª rodada:  chrome.exe   Arena | Benchmar     3     3  nao   nao   uia  1.0
2ª rodada:  chrome.exe   Arena | Benchmar   104   104  sim   SIM   uia  0.9
```

A mesma janela. **3 elementos sem conteúdo** e, no comando seguinte, **104 com
conteúdo**. A diferença não foi código: foi o **Chrome ligando a
acessibilidade** ao perceber que alguém estava lendo.

É o comportamento conhecido dos navegadores: a árvore da página é construída
sob demanda, quando um programa de acessibilidade aparece. A primeira leitura
é o que acende a luz; ela chega antes de a luz acender.

### O erro que isso revelou — e que era meu

Eu li **uma vez** e concluí “não publica”. Era o primeiro estado, não o único.
Foi por isso que encerrei o Chrome na 0.83.0, com toda a convicção e errado.
Uma leitura não é uma medição quando o objeto muda de estado ao ser tocado.

### O que mudou

- `ler_janela` relê **uma vez**, 0,4 s depois, quando a primeira leitura vem
  sem conteúdo. Se a segunda trouxer conteúdo (ou mais elementos), ela vence e
  o resultado diz por quê:

  ```
  A janela só publicou o conteúdo na segunda leitura — é o caso do navegador,
  que liga a acessibilidade quando percebe alguém lendo.
  ```

- Janela que já vem com conteúdo **não paga** a segunda passada.
- `--provados` avisa quais acordaram, para ninguém achar que precisa rodar
  duas vezes:

  ```
  Acordaram na segunda leitura (o navegador liga a acessibilidade quando
  percebe alguém lendo — já vem lido, não precisa repetir):
    - chrome.exe — Arena | Benchmark & Compare the Best AI Mode
  ```

## Onde ele enxerga, e onde para (0.83.1)

Pergunta justa depois do veredito: **“mas ele não está reconhecendo onde fica
cada coisa?”** — sim, para a moldura. E a resposta nunca esteve na tela, o que
é um defeito meu: a posição era medida (`caixa`: x, y, largura, altura) e o
desenho não a mostrava.

Agora mostra:

```
janela “Chrome”  em 0,0 (1200x800)
  botão “Fechar”  @568600ab:e2  em 1180,5 (30x20)
  botão “Minimizar”  @568600ab:e3  em 1140,5 (30x20)
```

E a diferença fica escrita, não deduzida:

| o que | ele sabe? |
|---|---|
| a janela existe, e onde ela está na tela | **sim** — coordenada |
| barra de título, minimizar, fechar, rolagem | **sim** — nome, ação e coordenada |
| o que está **dentro** da página | **não** — o Chrome não publica |

`--provados` ganhou a coluna `posicoes`:

```
  janela aberta                    elementos  posicoes  conteudo  serve?  fonte  seg
  --------------------------------------------------------------------------------------
  chrome.exe     Arena | Benchmar         4         4  nao       nao     uia    1.2
  explorer.exe   Downloads               88        88  sim       SIM     msaa   0.9
```

`posicoes` alto com `conteudo` baixo quer dizer exatamente isto: **ele vê as
peças e onde estão; não vê o que elas são.** Moldura tem posição e não serve
para trabalhar; conteúdo é o que serve.

Isso também corrige uma coisa que eu disse rápido demais. “O Chrome não
publica” é impreciso. O mais provável é que o Chrome só ligue a árvore da
página quando percebe um programa de acessibilidade, e aqui ela tenha ficado
desligada. É ajuste do Chrome, não do JARVIS — e não é algo que eu vá pedir
para você fazer à mão.

## O veredito do Chrome (0.83.0)

A 0.82.6 mediu a janela certa. A resposta:

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

Duas janelas filhas `Chrome_RenderWidgetHostHWND`, **1 elemento cada**, sem
conteúdo. A página não é publicada — nem pela MSAA, nem pela UIAutomation.

**Está encerrado o Chrome neste PC.** Era a promessa, e ela vale: não peço
outra rodada, não mudo a pergunta, não há uma sétima tentativa.

> **Correção (0.84.0):** estava errado. O Chrome publica a página sim — ele
> liga a acessibilidade quando percebe alguém lendo, e a primeira leitura
> pegou o estado antes disso. Ver “O Chrome acordou”, acima. A promessa de não
> insistir continua; o que mudou é que agora não há por que insistir: funciona.

O que isso significa na prática: neste `Windows 10.0.14393`, este Chrome não
expõe o conteúdo da página para um leitor de acessibilidade. O JARVIS não vai
adivinhar o que está na tela — sem foto, sem OCR, sem clique às cegas. Ler o
Chrome **aqui** não é um problema de código meu que mais uma versão resolve.

### O que ficou de aprendizado, e virou código

**1. Número não é resposta.** “47 elementos” manteve a etapa 2 parada por seis
versões, porque os 47 eram moldura. Agora toda leitura termina com a pergunta
que importa:

```
  NAO SERVE para agir: a janela publicou só moldura (barra de título,
  rolagem, botões de janela). Esta é a mesma parede que o Chrome deu neste PC.
```

**2. Não perguntar uma janela por vez.** Seis mensagens suas foram gastas
medindo um programa por vez. Agora existe um comando que mede **todas as
janelas abertas** de uma vez e responde onde dá para trabalhar:

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
```

**3. A ordem da medição importa.** Na 0.82.6 a coluna da MSAA do Chrome saiu
com 4, quando a leitura da 0.82.4 tinha achado 47 na mesma janela — a diferença
era a UIA já ter aberto a janela antes da medição. O diagnóstico agora mede a
MSAA **primeiro**, e o veredito é a leitura de verdade (`ler_janela`), não uma
segunda implementação dela.

**4. A conta da prontidão é explícita.** `arvore.prontidao()` responde com
números: total, acionáveis, com nome, editáveis, e um motivo em português. Ela
recusa moldura mesmo com 600 botões, e aceita o campo do Bloco de Notas, que
não tem nome nenhum — porque é onde se escreve.

## A sexta medição: a tabela mediu o terminal (0.82.6)

A 0.82.5 pediu uma tabela e ela veio assim:

```
  [FALHA] varredura de janelas (1)
  janela                                  msaa  uia   conteudo
  ConsoleWindowClass                         1    12   nenhum
```

`ConsoleWindowClass` é o **terminal**. O comando pedia o Chrome.

**O defeito era meu, não do Chrome.** `diagnostico()` não recebia o handle:
ignorava o `--alvo` e media sempre a janela em foco. A 0.82.3 tinha corrigido
exatamente isso na leitura normal e deixou o diagnóstico de fora — o mesmo erro,
no outro caminho. A tabela que devia decidir a etapa 2 estava olhando para a
janela errada.

### O que mudou

1. **O diagnóstico escolhe como a leitura escolhe.** A sonda usa o mesmo
   `_escolher`/`arvore.escolher_janela` e passa o **handle** para
   `diagnostico(alvo, handle=…)`. Não há segunda escolha para divergir.
2. **A tabela diz qual janela está medindo**, com processo e classe, antes de
   qualquer número:

   ```
   medindo: chrome.exe — Arena | Benchmark...
   classe:  Chrome_WidgetWin_1
   ```

3. **A MSAA também desce as filhas.** A 0.82.5 varria as filhas só na UIA. O
   Chrome publica a página pela MSAA da filha em várias versões; agora
   `varrer_msaa` percorre até 24 filhas, conteúdo primeiro, com a mesma regra
   de `escolher_fonte`.
4. **Há um veredito, e ele é medido como a leitura mede.** A tabela mostra cada
   janela isolada; a leitura agrega. No fim:

   ```
   VEREDITO: a leitura vai funcionar — 812 elemento(s) de conteudo, fonte uia.
   lido de dentro de: Chrome_RenderWidgetHostHWND
   ```
   ou `VEREDITO: 12 elemento(s), nenhum de conteudo (fonte uia).` — sem deixar a
   interpretação para você.
5. **A coluna `processo`** existe para o engano não se repetir: se a linha não
   diz `chrome.exe`, a janela não é o Chrome.

### O critério continua o mesmo

Se, **medindo a janela certa**, a tabela do Chrome disser `nenhum` em todas as
linhas e o veredito não tiver conteúdo, eu encerro a leitura do Chrome neste PC.
Sem nova rodada, sem nova tentativa: sigo com Explorer, Bloco de Notas e
instaladores, que publicam árvore clássica — e a etapa 2 (clique por `ref`) é
medida neles.

## A quinta medição: moldura não é conteúdo (0.82.5)

A 0.82.4 matou a repetição — **600 para 47 elementos**. Mas o número novo
denunciou outra coisa:

```
chrome.exe — Arena | Benchmark...: 47 elemento(s), 26 acionável(is) — fonte: msaa.
a UIAutomation mostrou 4; a MSAA mostrou mais (47).
```

Os 47 eram **todos moldura**: barra de título, barra de rolagem, “alça”.
Nenhum item da página. E a regra “ganha quem mostrou mais” premiava exatamente
a leitura sem conteúdo — 47 pedaços de moldura venciam 4 elementos de página.

Três correções:

### 1. Conteúdo vence moldura

A escolha entre fontes parou de contar elementos e passou a perguntar **o que**
eles são. Papéis de conteúdo — link, texto, item de lista, célula, documento —
valem mais do que qualquer quantidade de botão de janela.

| situação | quem ganha |
|---|---|
| uma tem conteúdo, a outra só moldura | a que tem conteúdo |
| navegador (Chrome, Edge, Firefox…) | UIAutomation, mesmo com menos nós |
| nenhuma tem conteúdo | quem mostrou mais (regra antiga) |

### 2. A página mora numa janela **filha**

A página do Chrome não é um elemento da janela principal: é a janela filha
`Chrome_RenderWidgetHostHWND` — outro processo. Ler só a janela de topo dá a
moldura; é por isso que a UIA “mostrava 4”.

Agora a leitura varre as janelas filhas (até 24), começando pelas classes que
carregam conteúdo, e fica com a que tiver mais nós. O resumo diz de onde veio:

```
(lido de dentro: Chrome_RenderWidgetHostHWND)
```

### 3. O diagnóstico passou a medir isso

`--diagnostico` agora mostra uma tabela por janela e por fonte:

```
  janela                                  msaa  uia   conteudo
  --------------------------------------------------------------
  Chrome_WidgetWin_1                        47     4   nenhum
    Chrome_RenderWidgetHostHWND              0   812   uia
```

Essa tabela é a resposta definitiva. Se a linha indentada mostrar `uia` com
conteúdo, a leitura funciona. Se mostrar `nenhum` em tudo, o Windows 10 do seu
PC não expõe a página — e aí eu paro, em vez de te fazer rodar de novo.

## A quarta medição: a causa raiz (0.82.4)

`--alvo chrome` passou a achar o Chrome. Mas a árvore continuou repetindo — e
agora dava para ver **o quê** repetia:

```
barra de rolagem “Vertical”
  botão “Uma linha acima”
    botão “Uma linha acima”
      botão “Uma página acima”
        botão “Uma linha acima” ...
```

Não era a moldura da janela. Era a **barra de rolagem**. E a causa não era o
Chrome — era uma linha minha:

```python
usar = ponteiro_filho or ponteiro      # <- o defeito
```

A MSAA tem dois tipos de filho:

| tipo | o que é | tem filhos? |
|---|---|---|
| **objeto** (VT_DISPATCH) | um objeto COM de verdade, com ponteiro próprio | sim |
| **simples** (VT_I4) | só um número de identificação dentro do pai | **não** |

Para um filho simples, `get_accChildCount` **no pai** devolve os filhos *do
pai*. Ao reusar o ponteiro do pai, eu pedia ao pai que listasse os próprios
filhos — de novo, e de novo, até acabar o limite. Cada “botão Uma linha acima”
era o mesmo botão, lido repetidamente.

O certo: **elemento simples entra na árvore (nome e papel são lidos dele), mas
não se desce nele.** Uma linha.

Junto com isso, a montagem ganhou a mesma guarda em segundo lugar: mesmo que a
sonda devolva árvore repetida (versão antiga, programa estranho), o `montar`
corta antes de chegar ao chat. E a distinção passou a ser explícita:

- **moldura** (Minimizar, Fechar, IME): o nó é real, entra e para ali;
- **repetição** (o mesmo nó dentro de si mesmo): não é nó novo, **não entra**.

Por fim: navegador (Chrome, Edge, Firefox, VS Code, Slack, Discord…) agora
**sempre** tenta a UIAutomation, mesmo que a MSAA venha grande. No seu PC a
MSAA do Chrome devolveu 600 elementos de barra de rolagem e **zero** da página.

## A terceira medição no seu PC (0.82.3)

A 0.82.2 consertou os índices da UIAutomation — e isso **funcionou**:

```
D:\JARVIS>.venv\Scripts\python arvore_sonda.py --alvo chrome --diagnostico
  [ok  ] CoInitializeEx(MTA)                0x00000000
  [ok  ] CoCreateInstance(IUIAutomation)    0x00000000  objeto criado
  [ok  ] get_ControlViewWalker (índice 14)  0x00000000
  [ok  ] ElementFromHandle (índice 6)       0x00000000
  [ok  ] get_CurrentControlType             0x00000000  tipo=50032
```

E a leitura pela UIA trouxe conteúdo de verdade onde a MSAA trazia a moldura:

```
--alvo chrome: 12 elemento(s), 7 acionável(is) — fonte: uia
  barra de rolagem “Vertical”
    botão “Uma linha acima”  @93d11915:e3
    botão “Uma página acima”  @93d11915:e4
    elevador “Posição”
```

**Mas `--alvo chrome` leu o terminal, não o Chrome.** O motivo está no título
daquela janela:

```
cmd.exe — C:\Windows\system32\cmd.exe - .venv\Scripts\python arvore_sonda.py --alvo chrome
```

A busca procurava **primeiro no título**, e o título do `cmd` é a linha de
comando — que contém a palavra “chrome”. A janela que roda a sonda é a **única**
que sempre carrega o pedido escrito nela. Era o pior lugar possível para
começar a busca.

Agora:

1. a janela que roda a sonda **nunca** é candidata;
2. **processo vence título**: `chrome` casa com `chrome.exe` (nota 0) antes de
   casar com qualquer título que mencione a palavra (nota 3);
3. quando nada casa, a mensagem lista só janelas de programas de verdade.

## A segunda medição no seu PC (0.82.2)

Depois da 0.82.1 você rodou de novo, agora com o Chrome aberto:

```
chrome.exe — Arena | Benchmark...: 600 elemento(s), 596 acionável(is) — fonte: msaa.
botão “IME” → botão “IME” → botão “IME” → ...
botão “Minimizar” → botão “Minimizar” → ...
```

```
D:\JARVIS>.venv\Scripts\python arvore_sonda.py --fonte uia
o foco estava neste terminal; li “Iniciar” (explorer.exe) em vez dele.
a UIAutomation não devolveu árvore para esta janela.
```

Eram **três defeitos meus**, e nenhum do seu PC:

1. **A árvore se repetia dentro de si mesma.** O Chrome expõe a moldura da
   janela *dentro* da janela: cada botão de moldura devolve os cinco botões de
   novo. Sem guarda, os 600 elementos acabaram antes de chegar ao conteúdo da
   página — 596 “botões” que não existem. Agora **moldura é folha** (não se desce
   em Minimizar/Maximizar/Fechar/IME) e **quem repete um ancestral para**.
2. **Os índices da UIAutomation estavam todos +3.** A vtable começa em
   `CompareElements`, mas QueryInterface/AddRef/Release ocupam as posições 0, 1
   e 2 — eu tinha esquecido. Na prática, `ElementFromHandle` chamava
   `GetRootElementBuildCache`. Corrigido e **preso por teste**.
3. **A troca de janela pegou o menu Iniciar.** “Iniciar” é do Windows, não é um
   programa seu. Agora a lista de janelas de sistema (menu Iniciar, barra,
   área de trabalho) fica de fora da escolha.

E o que faltava para não errar de novo em silêncio: `--diagnostico`, que mostra o
retorno de **cada** passo do COM, em hexadecimal.

```
.venv\Scripts\python arvore_sonda.py --diagnostico
```

## A primeira medição no seu PC (0.82.1)

Você rodou isto no `cmd` e recebeu, três vezes:

```
D:\JARVIS>.venv\Scripts\python arvore_sonda.py
cmd.exe — C:\Windows\system32\cmd.exe - ...: 1 elemento(s), 0 acionável(is) — fonte: msaa.
área do cliente “C:\Windows\system32\cmd.exe - ...”
```

**Duas coisas estavam erradas, e nenhuma era o seu PC:**

1. **A sonda leu a si mesma.** O comando roda *dentro* de um `cmd.exe`, e a
   janela em foco era esse `cmd`. Você queria ver o programa aberto **atrás**.
   Agora, quando o foco é o terminal que roda a sonda, ela pega a janela anterior
   e **diz que trocou** (`o foco estava neste terminal; li “...” em vez dele`).
2. **O console não publica botões pela MSAA.** A MSAA é de 1996 e o `cmd` só
   expõe a moldura. O Windows tem uma **segunda** árvore, a **UIAutomation**, que
   é a mesma que o Narrador usa — e é nela que os programas de hoje publicam
   (Bloco de Notas do Windows 11, apps WinUI, boa parte do Chrome).

Por isso a leitura agora **tenta as duas** e fica com a que mostrou mais
elementos. Numa janela rica ela não paga a segunda leitura: o tempo de espera
seria seu.

E quando a árvore vem quase vazia, aparece a **dica** em vez de silêncio — o
resumo diz *por que* e *o que fazer* (trocar de janela, usar `--alvo`).

## O que é a árvore de acessibilidade

Todo programa no Windows é obrigado (por acessibilidade) a dizer quais elementos
tem: “aqui há um botão chamado Salvar, nesta posição, e clicar nele faz X”. É o
mesmo canal que o **Narrador** e o **NVDA** usam.

São **duas** portas para a mesma ideia, e o JARVIS usa as duas:

| fonte | biblioteca | quem publica |
|---|---|---|
| **MSAA** | `oleacc.dll` | programas clássicos (Win32, MFC, VB6, muito do Chrome) |
| **UIAutomation** | `uiautomationcore.dll` | programas atuais (WinUI, WPF, Bloco de Notas novo, Explorer) |

As duas via `ctypes` puro — **sem instalar nada**. E as duas só leem: `get_*`,
`accessLocation`, `GetFirstChildElement`, `GetCurrentPattern` (este último só
para **perguntar** se o elemento aceita ação).

```
janela “Cadastro de cliente”
  painel
    botão “Salvar”              @a1b2c3d4:e3
    botão “Cancelar”            @a1b2c3d4:e4
    texto “Nome completo”
    caixa de seleção “Aceito os termos”  @a1b2c3d4:e6
  barra de ferramentas
    item de menu “Arquivo”      @a1b2c3d4:e8
```

O `ref` (`@a1b2c3d4:e3`) só vai para o que **dá para acionar**, e carrega o id da
leitura: se a tela mudar, o `ref` antigo deixa de valer — é assim que se evita
clicar no botão errado depois de uma atualização da janela.

## Como usar

No chat:

```
vê os elementos da janela
lê a janela do chrome
o que dá para clicar no bloco de notas
```

Ou direto no terminal do PC (não precisa do JARVIS aberto):

```
.venv\Scripts\python arvore_sonda.py
.venv\Scripts\python arvore_sonda.py --janelas
.venv\Scripts\python arvore_sonda.py --alvo chrome --profundidade 8
.venv\Scripts\python arvore_sonda.py --json --limite 200
```

## O que ele garante

| garantia | como |
|---|---|
| **só leitura** | o módulo não tem função de clicar, digitar ou mover — há teste que falha se alguém acrescentar |
| **sem foto da tela** | não usa `screenshot`, não lê pixel, não faz OCR |
| **não derruba a API** | a leitura roda em `arvore_sonda.py`, processo separado, com tempo limite |
| **não trava** | profundidade (máx. 14), total de elementos (máx. 3.000) e tempo (25 s) limitados |
| **não finge** | corte vira `completo: false` com o motivo; papel desconhecido vira `elemento 999`; janela sem árvore vem com aviso |
| **fora do Windows** | recusa com frase clara, em vez de devolver vazio |
| **duas fontes** | MSAA e UIAutomation; quem decide é a que mostrou mais elementos |
| **não lê a si mesma** | se o foco é o terminal que roda a sonda, ela pega a janela de trás e avisa |
| **não entra em laço** | moldura é folha e nó que repete um ancestral para — o Chrome já provou que sem isso a leitura vira 600 botões falsos |
| **não escolhe o Windows** | menu Iniciar, barra de tarefas e área de trabalho ficam fora da lista de janelas |
| **não escolhe a si mesma nem por engano** | a janela que roda a sonda é excluída, e processo vence título — `--alvo chrome` acha o Chrome |
| **não repete o mesmo elemento** | filho “simples” da MSAA não desce (era a causa de 600 botões falsos), e a montagem corta repetição de qualquer origem |
| **navegador vai direto na UIA** | Chrome/Edge/Firefox/VS Code publicam a página pela UIAutomation, não pela MSAA |
| **conteúdo vence moldura** | 47 botões de janela não valem mais do que 3 elementos de página |
| **lê as janelas filhas** | a página do navegador é uma janela filha (`Chrome_RenderWidgetHostHWND`), não um elemento da janela de topo |
| **falha com endereço** | `--diagnostico` mostra o retorno de cada passo do COM, não só “não devolveu” |
| **mede a janela certa** | o diagnóstico recebe o handle já escolhido — `--alvo chrome` não mede mais o terminal |
| **diz se serve para agir** | toda leitura termina com serve/não serve e o motivo; `mesa.arvore` devolve `pronto` |
| **mostra onde fica** | cada elemento sai com `em x,y (largura x altura)`; `--provados` tem a coluna `posicoes` |
| **não desiste na primeira** | janela que responde só moldura é relida uma vez, 0,4 s depois — navegador acorda ao ser lido |
| **não confunde moldura com trabalho** | botão de janela, rolagem e alça ficam de fora da conta de “dá para agir” |
| **sabe onde se escreve** | papel `texto`/`documento` com caixa ganha ação `digitar` e `ref`, salvo se for somente leitura |
| **age por `ref`, com freio** | relê antes de agir; ref antigo, moldura e digitar sem texto são recusados; `--executar` é obrigatório |
| **não move o mouse** | a ação vem do elemento (ação padrão / foco), que é o único caminho que funciona na sua tela |
| **mede todas as janelas de uma vez** | `--provados` varre o que está aberto, com teto de 60 s, e diz onde dá para trabalhar |
| **mede na ordem da leitura** | MSAA antes de a UIA tocar na mesma janela; o veredito é a própria `ler_janela` |
| **diz o que mediu** | a tabela abre com processo e classe da janela, e fecha com veredito medido como a leitura mede |
| **varre as filhas nas duas fontes** | MSAA e UIA descem até 24 janelas filhas, conteúdo primeiro |

## O que **não** faz (ainda) e por quê

- **Clicar por `ref`** é a **etapa 2**. Ela só entra depois que você rodar isto no
  seu PC e me disser o que apareceu — porque o que decide é **quais programas
  publicam árvore**. Chrome, WhatsApp Desktop e Explorer se comportam de formas
  diferentes, e prometer clique sem essa medição seria repetir o erro das
  versões anteriores.
- **Ver a tela por imagem.** Se um programa não publica árvore (jogo, instalador
  antigo), o JARVIS não vê. Isso é limite do programa, não do JARVIS — e está
  dito em vez de escondido.

## O teste que você mesmo pode fazer

1. abra **o Bloco de Notas** e clique nele;
2. no terminal do PC:

```
cd /d D:\JARVIS
.venv\Scripts\python arvore_sonda.py
```

3. me diga o que apareceu (ou mande o `--json`).

Para saber **em quais programas** dá para trabalhar, sem tentativa e erro:

```
.venv\Scripts\python arvore_sonda.py --provados
```

Se alguma coisa vier estranha, o primeiro comando é sempre:

```
.venv\Scripts\python arvore_sonda.py --diagnostico
```

Quer comparar as duas fontes na mesma janela? Rode uma vez com `--fonte msaa` e
outra com `--fonte uia`. O número de elementos de cada uma é a resposta crua —
e é ela que eu uso para decidir a etapa 2, não um palpite meu.

Se o Bloco de Notas publicar árvore (deve publicar), a etapa 2 fica viável para
programas clássicos. Depois repetimos com o **Chrome** e com o **WhatsApp** —
esses são os que decidem se vale a pena.

## Detalhe técnico: por que a sonda é um processo separado

A leitura conversa por COM com **código de outra pessoa** (o programa que você
tem aberto). Um aplicativo malcomportado pode travar a chamada ou derrubar o
processo inteiro. Derrubar uma sonda descartável é aceitável; derrubar o JARVIS
no meio de uma conversa não é. É o mesmo princípio do `conferir-versao.bat`: o
diagnóstico não pode ser perigoso.
