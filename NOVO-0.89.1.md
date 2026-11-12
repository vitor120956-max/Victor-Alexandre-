# JARVIS 0.89.1 — a janela não era a janela

Você rodou e recebeu:

```
NÃO DEU: não achei lugar para escrever nesta janela. a janela publicou só
moldura (barra de título, rolagem, botões de janela)... 12 de 12 elemento(s)
vieram com coordenada
```

O Bloco de Notas aceita escrita — você já viu isso funcionar duas vezes. O
problema era que havia **duas janelas `notepad.exe` vivas**: uma publica o
campo, a outra publica só moldura. O JARVIS pegava a primeira da lista.

E pior: ele achava uma janela e, na hora de agir, **escolhia outra de novo**.
Escolher duas vezes é escolher errado uma vez.

## As três correções

**1. Quem acha, decide.** A janela achada é a janela usada, pelo `handle`.
Não há segunda escolha. Se ela sumir no meio, o erro diz isso — não tenta
outra às cegas.

**2. Várias janelas, uma serve.** Com mais de uma candidata, ele faz **uma
leitura em cada** e fica com a que publica campo — antes de esperar 15 segundos
na errada. O mesmo vale para `--alvo "notepad.exe"` com `--escrever`: se a
primeira não tem campo, ele olha as outras do mesmo programa.

**3. Espera o campo, não a janela.** A janela do programa aparece antes de o
campo existir. Agora ele relê até o campo nascer (até 15 s) em vez de dizer
"não aceita escrita" meio segundo antes de aceitar.

O erro final também mudou: repete o que a janela respondeu, em vez de só dizer
"não deu".

## O comando

```
cd /d D:\JARVIS
```

```
atualizar.bat
```

Antes de rodar, **feche todos os Blocos de Notas** (o X de cada um). Aí não
sobra janela velha para confundir:

```
.venv\Scripts\python arvore_sonda.py --programa "bloco de notas" --escrever "oi, mundo" --executar
```

O que eu espero:

```
  Abri o Bloco de notas. Feito: digitar 'oi, mundo' em texto em ... (970x69) (conferi: o texto está no campo)

  janela:  notepad.exe — Sem título - Bloco de notas
  como:    valor do campo (put_accValue, sem teclado)
  conferi: o texto está no campo.
```

Se em vez disso aparecer `a janela do Bloco de notas está aberta, mas em 15s
ela não publicou nenhum lugar de escrever`, cole a saída inteira: ela agora
traz o que a janela respondeu, e é por esse texto que eu descubro qual é a
janela errada.

Se você tiver **mais de um** Bloco de Notas aberto de propósito, pode dizer
qual: `--alvo "notas.txt"` escolhe pela parte do título.
