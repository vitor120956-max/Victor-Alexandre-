# A árvore da janela: ver os elementos sem tocar (0.82.0)

Etapa 1 do que o [`vercel-labs/agent-desktop`](ANALISE-AGENT-DESKTOP.md) propõe.
O `mesa.py` antigo só via **títulos** de janela e clicava por coordenada que você
ditava — sem saber se acertou. Aqui o JARVIS passa a **ler** o que a janela
publica sobre si mesma.

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
