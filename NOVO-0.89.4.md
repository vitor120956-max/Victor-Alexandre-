# JARVIS 0.89.4 — eu estava mentindo sobre o Windows

```
NÃO DEU: o Windows recusou abrir notepad.exe: [WinError 2] O sistema não pode
encontrar o arquivo especificado
```

Duas coisas erradas nessa frase — e a primeira é a que me incomoda: **o Windows
não recusou nada.**

`FileNotFoundError` é uma subclasse de `OSError`. O meu código testava o erro
genérico primeiro, então qualquer "não achei o arquivo" era reportado como
"o Windows recusou". Diagnóstico errado com cara de autoridade — o mesmo
defeito que você viu na 0.87.1, quando ele culpou o Bloco de Notas por um
índice trocado.

A segunda: **`notepad.exe` sozinho não basta.** Chamar pelo nome depende do
PATH do processo, e neste Windows (10.0.14393) isso voltou WinError 2.

## O que mudou

O caminho agora é procurado em três degraus:

| degrau | onde procura | por quê |
|---|---|---|
| 1 | `shutil.which` | respeita o PATH quando ele está certo |
| 2 | `C:\Windows\System32`, `SysWOW64`, raiz | onde o Windows guarda os próprios programas |
| 3 | registro `App Paths` | onde os instaladores registram o que não vai no PATH |

E se nada for achado, ele cai para `ShellExecute` — o **mesmo mecanismo do
duplo clique**, que acha pelo App Paths. Sem shell, sem linha digitada.

O erro também parou de mentir: agora diz `não achei o notepad.exe neste PC` e
mostra onde procurou.

E o plano informa o caminho usado:

```
  abri:    C:\Windows\System32\notepad.exe
```

## O comando

```
cd /d D:\JARVIS
```

```
atualizar.bat
```

```
.venv\Scripts\python arvore_sonda.py --programa "bloco de notas" --escrever "oi, mundo" --executar
```

O que eu espero ver agora:

```
  Abri o Bloco de notas. Feito: digitar 'oi, mundo' em texto em ... (conferi: o texto está no campo)

  janela:  notepad.exe — Sem título - Bloco de notas
  abri:    C:\Windows\System32\notepad.exe
  como:    valor do campo (put_accValue, sem teclado)
  conferi: o texto está no campo.
```

Se aparecer `não achei o notepad.exe neste PC`, cole a linha inteira: ela agora
traz os três lugares onde ele procurou, e é com isso que eu acho o quarto.
