# JARVIS 0.82.2 — o Chrome mostrou três defeitos meus

Você rodou de novo, agora com o Chrome aberto, e mandou o resultado. Ele valeu
uma versão inteira.

```
chrome.exe — Arena | Benchmark...: 600 elemento(s), 596 acionável(is) — fonte: msaa.
botão “IME” → botão “IME” → botão “IME” → ...
botão “Minimizar” → botão “Minimizar” → ...
```

```
--fonte uia
o foco estava neste terminal; li “Iniciar” (explorer.exe) em vez dele.
a UIAutomation não devolveu árvore para esta janela.
```

**Nada disso era o seu PC.** Eram três erros no JARVIS.

## 1. A árvore se repetia dentro de si mesma

O Chrome expõe a moldura da janela *dentro* da própria janela: cada botão de
moldura devolve os cinco botões de novo. Sem guarda, o limite de 600 acabava
antes de chegar na página — e o JARVIS entregava **596 botões que não existem**.

Duas guardas, e o nó continua aparecendo (só a descida para):

| guarda | o que para |
|---|---|
| **moldura é folha** | Minimizar, Maximizar, Fechar, IME, Sistema, Ajuda de contexto |
| **quem repete um ancestral para** | o mesmo botão dentro dele mesmo, com qualquer nome |

Irmãos com o mesmo nome (“Excluir” e “Excluir” lado a lado) **não** são cortados:
a guarda olha a linhagem, não a lista.

Se a repetição voltar, agora vem um aviso em vez de números falsos:

> esta janela repetiu os mesmos botões dentro deles mesmos (moldura em vez de
> conteúdo). Tente `--fonte uia`.

## 2. Os índices da UIAutomation estavam todos +3

A vtable do COM começa em `CompareElements` — mas QueryInterface, AddRef e
Release ocupam as posições 0, 1 e 2, e eu não contei. Resultado: o
`ElementFromHandle` chamava `GetRootElementBuildCache`, e a leitura “não
devolvia árvore”.

O erro era **uniforme** (todos os índices três acima), o que confirmou o
diagnóstico. Corrigido e agora **preso por teste**: se alguém errar de novo, a
suíte quebra antes de chegar em você.

## 3. A troca de janela escolheu o menu Iniciar

“Iniciar” é do Windows, não é programa seu. Menu Iniciar, barra de tarefas e
área de trabalho saíram da lista de candidatas.

## O que entrou de novo para não errar calado

**`--diagnostico`** — o passo a passo do COM, com o retorno de cada chamada em
hexadecimal:

```
.venv\Scripts\python arvore_sonda.py --diagnostico
```

```
  [ok  ] CoInitializeEx(MTA)  0x00000000
  [ok  ] CoCreateInstance(IUIAutomation)  0x00000000  objeto criado
  [ok  ] get_ControlViewWalker (índice 14)  0x00000000
  [ok  ] ElementFromHandle (índice 6)  0x00000000  janela: Arena - Google Chrome
  [ok  ] get_CurrentControlType  0x00000000  tipo=50032
```

A 0.82.1 dizia “não devolveu árvore” e parava aí. Isso não é diagnóstico, é
silêncio com frase.

## O teste de agora

Com o **Chrome** na frente:

```
cd /d D:\JARVIS
```

```
atualizar.bat
```

```
.venv\Scripts\python arvore_sonda.py --alvo chrome
```

O que eu preciso: **quantos elementos**, **quantos acionáveis** e se apareceu
algum nome de verdade da página (título, link, botão) — em vez de “IME”.

Se vier pouco:

```
.venv\Scripts\python arvore_sonda.py --alvo chrome --fonte uia
```

```
.venv\Scripts\python arvore_sonda.py --alvo chrome --diagnostico
```

## O que continua fora

- **Clicar por `ref`** (etapa 2): ainda não. Primeiro quero ver a árvore do
  Chrome com conteúdo de verdade.
- **Windows 10 build 14393** (o seu, de 2016): funciona, mas é um Windows antigo
  — alguns programas publicam árvore pior nele do que no Windows 11. Isso é
  limite do sistema, não do JARVIS, e está dito em vez de escondido.
- **Gmail/Drive/Agenda por OAuth** e **WhatsApp**: como antes.
