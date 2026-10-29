# JARVIS 0.62.3 — a máquina diz qual é o driver, em vez de você adivinhar

A tela que você mandou mostrou duas coisas de uma vez:

1. **o `.bat` que rodou era o antigo** (o texto ainda mandava "puxar a barra de
   notificações no celular", que é justamente o que eu tinha removido);
2. `ERROR: Could not find any USB device` de novo.

Sobre (1): agora o arquivo **imprime o próprio número de versão** na tela. Se o
número não aparecer, é arquivo velho — `atualizar.bat` não rodou.

Sobre (2): o erro continua sendo driver, mas eu estava te mandando instalar o
Zadig **no escuro**. Agora não.

## `sonda-otg.bat` — o driver na tela, antes de qualquer coisa

Ele pergunta ao Windows quais nós USB existem com **VID_04E8** (Samsung) e qual
driver está em cada um:

- `usbccgp` no nó pai → **normal**, é o aparelho composto;
- `WudfRd` / `wpdusb` na **interface** → o **MTP está segurando** — é esse o caso
  do seu J7;
- `WinUSB` / `libusbK` / `libusb0` → o `--otg` está pronto.

E devolve um código que o `.bat` entende:

| código | significa | o que fazer |
| --- | --- | --- |
| **0** | driver de OTG já instalado | abrir `teclado-pelo-pc.bat` |
| **1** | o MTP está segurando | Zadig (o passo a passo sai na tela, com o **id exato** do aparelho) |
| **2** | nenhum Samsung na USB | cabo, porta ou tela apagada — **não** é driver |

O caso 2 é o detalhe que faltava: se a sonda não achar o aparelho, ela diz
"não há driver a consertar" e manda olhar cabo/porta. Se achar, imprime
`VID_04E8&PID_xxxx` para você escolher a linha certa no Zadig — sem confundir
com leitor de cartão, mouse ou hub.

## O `.bat` do teclado agora confere antes de abrir

`teclado-pelo-pc.bat` roda a sonda **antes** do `scrcpy --otg` e mostra o
resultado. Se falhar, o bloco de erro já vem com o "a sonda acima disse X".

```
sonda-otg.bat                 -> só o diagnóstico
teclado-pelo-pc.bat           -> diagnóstico + abre o scrcpy --otg
```

## Trava nova no repositório

Um teste passa por **todos** os `.bat` e `.ps1` do projeto e exige ASCII puro +
CRLF. Isso já pegou dois arquivos (`.ps1`) que tinham perdido o CRLF neste
próprio commit — o tipo de coisa que só aparece quando o usuário roda e o `goto`
do `cmd` lê a linha errada.

## Testes

- `pytest server/tests` → **2.816 passed** (`test_celular.py`: 160).
- Novos: a sonda existe em ASCII/CRLF, não tem erro de sintaxe de PowerShell
  (tree-sitter), distingue OTG de MTP pelo driver **da interface**, avisa que
  ausência de Samsung é cabo e não driver, o `.bat` confere antes de abrir, o
  selo de versão bate com o `package.json`, e `celular.otg` aponta a sonda
  **antes** do Zadig.
