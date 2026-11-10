# A árvore da janela: ver os elementos sem tocar (0.82.0)

Etapa 1 do que o [`vercel-labs/agent-desktop`](ANALISE-AGENT-DESKTOP.md) propõe.
O `mesa.py` antigo só via **títulos** de janela e clicava por coordenada que você
ditava — sem saber se acertou. Aqui o JARVIS passa a **ler** o que a janela
publica sobre si mesma.

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
