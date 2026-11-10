# JARVIS 0.82.1 — a leitura que o seu PC ensinou a corrigir

Você rodou a sonda e me mandou o resultado. Ele dizia, três vezes:

```
cmd.exe — C:\Windows\system32\cmd.exe - ...: 1 elemento(s), 0 acionável(is) — fonte: msaa.
área do cliente “C:\Windows\system32\cmd.exe - ...”
```

Não era o seu PC falhando. Eram **duas coisas erradas no JARVIS**. Esta versão
conserta as duas.

## 1. A sonda estava lendo a si mesma

O comando roda **dentro** de um `cmd.exe`, e a janela em foco era justamente
esse `cmd`. Você queria ver o programa aberto **atrás** — e recebeu a moldura do
terminal.

Agora, quando o foco é o terminal, a sonda pega a janela anterior e **avisa**:

```
o foco estava neste terminal; li “Sem título - Bloco de Notas” (notepad.exe) em vez dele.
```

Se você pedir `--alvo` explícito, ela obedece — não troca nada por conta própria.

## 2. Faltava a segunda fonte

A MSAA é de 1996. O `cmd` (e boa parte dos programas de hoje) só publica a
moldura nela — “1 elemento, 0 acionável” era a resposta **correta** para a
pergunta errada.

O Windows tem uma segunda árvore, a **UIAutomation** — a mesma que o Narrador
usa. É nela que os programas atuais publicam: Bloco de Notas do Windows 11, apps
WinUI, Explorer, boa parte do Chrome.

Agora a leitura **tenta as duas** e fica com a que mostrou mais elementos:

| quando | quem ganha | por quê |
|---|---|---|
| MSAA veio com 1–8 elementos | vai para a UIA também | moldura não é conteúdo |
| MSAA já veio rica | fica só na MSAA | a espera seria sua |
| as duas vieram vazias | diz o motivo | jogo em tela cheia, instalador antigo, janela elevada |

O resumo diz qual fonte respondeu (`fonte: uia`) e, quando houve comparação,
quantos elementos cada uma mostrou.

## 3. Vazio deixou de ser silêncio

Quando a árvore vem quase vazia, agora aparece uma **dica**:

> o JARVIS leu o próprio terminal — é ele que está em foco. Clique na janela que
> quer examinar e rode de novo, ou peça `--alvo` com parte do título.

Antes, “1 elemento, 0 acionável” deixava você sem saber se era o programa, o
Windows ou o JARVIS. Era o JARVIS.

## 4. Detalhes menores que vieram de graça

- **Nome do papel traduzido:** a UIA já manda “editar”, “botão”, “aba”. Quando
  existe, ele tem preferência sobre a nossa tabela.
- **Botão desativado não ganha `ref`.** Clicar num botão cinza não é ação
  possível — dar `ref` a ele seria prometer o impossível.
- **`--fonte msaa` / `--fonte uia`** na sonda, para você comparar as duas na
  mesma janela. É essa comparação que decide a etapa 2.

## O teste de agora

Abra o **Bloco de Notas** (ou o **Chrome**) e, **com ele na frente**, rode:

```
cd /d D:\JARVIS
```

```
.venv\Scripts\python arvore_sonda.py
```

Agora a sonda troca sozinha do terminal para a janela de trás. O que interessa é
o número: quantos elementos, quantos acionáveis, e `fonte: msaa` ou `fonte: uia`.

Para comparar:

```
.venv\Scripts\python arvore_sonda.py --fonte msaa
```

```
.venv\Scripts\python arvore_sonda.py --fonte uia
```

## O que continua fora

- **Clicar por `ref`** (etapa 2): depende dessa medição. Sem saber quais
  programas respondem, prometer clique seria chute.
- **Gmail/Drive/Agenda por OAuth**: exige projeto no Google Cloud, feito por você.
- **WhatsApp**: segue sem API para conta pessoal.

## Para atualizar

```
cd /d D:\JARVIS
```

```
atualizar.bat
```

E, se a tela parecer a versão antiga:

```
conferir-versao.bat
```
