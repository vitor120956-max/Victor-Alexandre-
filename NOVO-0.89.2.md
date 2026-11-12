# JARVIS 0.89.2 — eram 12 elementos porque a janela estava recolhida

```
NÃO DEU: a janela do Bloco de notas está aberta, mas em 15s ela não publicou
nenhum lugar de escrever. ... 12 de 12 elemento(s) vieram com coordenada
```

**Doze elementos. Todos de moldura.** Esse número tem nome: **janela
minimizada**. Recolhida na barra de tarefas, a janela só publica a moldura — o
campo de escrita não existe para a leitura enquanto ela está lá.

Somando ao Bloco de Notas antigo, aberto desde as tentativas anteriores, havia
**duas janelas do mesmo programa**: uma recolhida, outra servindo. E nada dizia
qual era qual.

## O que mudou

**1. Cada janela diz de que processo veio (`pid`).** Quando ele abre o
programa, guarda o `pid` do processo que acabou de nascer e só aceita janela
daquele `pid`. É a janela que ele abriu — não a antiga.

**2. Cada janela diz se está minimizada.** As abertas vêm antes das recolhidas
na escolha, em vez de "a primeira da lista".

**3. Ele restaura sozinho.** `ShowWindow(SW_RESTORE)` — **sem mouse, sem
coordenada, sem pedir clique a ninguém**. Depois de restaurar, lê de novo e o
campo aparece.

**4. O erro agora mostra o retrato.** Em vez de "não achei lugar para
escrever", lista cada janela: título, minimizada, quantos elementos, se tem
campo.

## Um comando novo: ver as janelas do programa

```
.venv\Scripts\python arvore_sonda.py --programa "bloco de notas"
```

```
  Bloco de notas (notepad.exe) — 2 janela(s):
    Sem título - Bloco de notas  —  49 elemento(s), tem campo @f14b5235:e11
    velho - Bloco de notas  —  minimizada, 12 elemento(s), sem campo

  1 aceita(m) escrita. Uma delas é a que o JARVIS usa.
```

Se der errado de novo, **rode esse primeiro** — ele diz exatamente qual janela
está atrapalhando, sem adivinhação.

## O comando

```
cd /d D:\JARVIS
```

```
atualizar.bat
```

```
.venv\Scripts\python arvore_sonda.py --programa "bloco de notas"
```

Cole a saída dele. Com ela eu vejo quantas janelas existem e qual está
minimizada — e se o problema for outro, ele aparece escrito em vez de virar
mais uma tentativa às cegas.

Depois, para escrever:

```
.venv\Scripts\python arvore_sonda.py --programa "bloco de notas" --escrever "oi, mundo" --executar
```

Se aparecer `Restaurei a janela do Bloco de notas.` antes do `Feito:`, foi
exatamente esse o caso — e agora ele resolve sem você tocar em nada.
