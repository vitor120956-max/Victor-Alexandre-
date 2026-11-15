# JARVIS 0.90.0 — ele abriu o Bloco de Notas e escreveu

Você mandou uma linha, com o Bloco de Notas fechado:

```
Abri o Bloco de notas. Feito: digitar 'oi, mundo' em texto em 22,465 (970x69) (conferi: o texto está no campo)

janela:  notepad.exe — Sem título - Bloco de notas
alvo:    @95bc8c3d:e11  texto “”
onde:    22,465 (970x69)
fonte:   msaa   leitura: 95bc8c3d
como:    valor do campo (put_accValue, sem teclado)
abri:    C:\Windows\system32\notepad.exe
conferi: o texto está no campo.
```

E o `oi, mundo` estava lá, no print. **Funcionou de ponta a ponta.**

## O que isso prova, passo por passo

| passo | como ele fez | dá para verificar? |
|---|---|---|
| achar o programa | PATH → System32 → App Paths | o caminho aparece na saída |
| abrir | pelo caminho, ou ShellExecute | a janela é a do processo novo |
| escolher a janela | processo vence título; minimizada por último | sim |
| **escrever** | `put_accValue` — escreve no valor do campo | **lê de volta e confere** |
| chegar antes | `SetForegroundWindow` | sem tocar no mouse |

O caminho que venceu foi o **quarto degrau**. Neste Bloco de Notas o foco não
vem — nem no elemento, nem no campo inteiro. Se eu tivesse só teclado, estaria
parado até hoje. Foi bom ter quatro degraus.

## O que ainda não está provado (e não vou fingir que está)

- **Programas que não publicam o valor do campo.** Se um programa não expõe
  `accValue`, o quarto degrau não existe — sobra o `--mouse` ou nada. Cada
  programa é uma medição.
- **Teclado de verdade.** Neste PC ele nunca chegou a rodar. Aqui não precisou.
- **Escrever no meio de um texto.** Ou acrescenta no fim (`--acrescentar`), ou
  recusa. Editar o meio é outra etapa.

## O que mudou nesta versão

**O agente agora escolhe a skill certa.** "escreve oi no bloco de notas"
empatava em 0,56 com uma skill de memória — e empate é sorteio. As skills
passaram a declarar **palavras-chave**:

| frase | skill escolhida | nota |
|---|---|---|
| escreve oi no bloco de notas | `mesa.ditar` | 1,00 |
| abre o paint e escreve oi | `mesa.ditar` | 0,78 |
| leia a janela do notepad | `mesa.arvore` | 0,67 |
| quais janelas estao abertas | `mesa.status` | 0,75 |

Ou seja: pela conversa, o JARVIS agora entende o pedido e cai na skill que
abre, escreve e confere — em vez de ir para uma skill de memória por empate.

## O comando do dia

```
cd /d D:\JARVIS
```

```
atualizar.bat
```

Depois, suba a API e peça pela conversa (a skill exige `JARVIS_HOST_PC=1`; o
`iniciar-jarvis.bat` já cuida disso se a variável estiver no `.env`):

```
iniciar-jarvis.bat
```

E na conversa, com o Bloco de Notas fechado: *"escreve bom dia no bloco de
notas"*. Ele deve abrir, escrever e conferir.

Se a API reclamar que a camada do PC está desligada, é só acrescentar no `.env`:

```
JARVIS_HOST_PC=1
```

## Onde estamos

Você pediu três coisas para virar o Visão: **olhos** (ler a tela), **mãos**
(mouse/teclado) e **cabeça** (programação). Hoje:

- olhos: a árvore lê a janela — 49 elementos no Bloco de Notas, 104 no Chrome;
- mãos: **abre, escreve e confere** — provado no seu PC;
- cabeça: 322 skills, com Git, GitHub, engenharia, conserto e 20 de código.

A próxima etapa é o maestro: um objetivo em português que ele decompõe sozinho
— "arruma o erro do meu programa", "abre o navegador e pesquisa isso". As peças
existem e agora funcionam; falta a orquestração.
