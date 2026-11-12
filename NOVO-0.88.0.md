# JARVIS 0.88.0 — ele escreveu

O print que você mandou:

```
Feito: digitar 'oi, mundo' em texto em 378,542 (970x69) (conferi: o texto está no campo)
como:    valor do campo (put_accValue, sem teclado)
conferi: o texto está no campo.
```

E o `oi, mundo` no Bloco de Notas. **Funcionou**, e funcionou do jeito honesto:
ele não disse "mandei as teclas" — ele leu o campo de volta e conferiu.

## O que o print me contou

O caminho que venceu foi o **terceiro degrau**: escrever direto no valor do
campo. Nem o elemento, nem o campo inteiro aceitaram foco neste Bloco de
Notas — e ele **não digitou às cegas**, como devia.

Isso também confirma que o problema da versão anterior não era o Bloco de
Notas recusando nada. Era o número errado. Mas mesmo com o número certo, o foco
não vem nesse controle; quem dependesse só de teclado teria ficado sem
escrever. O terceiro degrau é o que faz funcionar.

## Duas coisas que o print mostrou erradas — e já estão corrigidas

**1. `janela: notepad.exe — notepad.exe — Sem título`.** O nome saía duas
vezes. Agora sai `notepad.exe — Sem título - Bloco de notas`.

**2. A segunda vez ia falhar.** `put_accValue` **substitui** o conteúdo. Na
primeira vez o campo estava vazio; agora ele já tem `oi, mundo`. A versão
anterior ia recusar com *"o campo já tem texto e eu não sobrescrevo o que não
escrevi"* — recusar estava certo, mas não resolvia o seu problema.

## O que mudou

**`--acrescentar`**: se o campo já tiver texto, ele lê o que está lá e escreve
`o que existe + o novo`, sem apagar nada.

```
.venv\Scripts\python arvore_sonda.py --alvo "notepad.exe" --escrever ". e mais isto" --acrescentar --executar
```

E ele diz o que fez:

```
  Feito: digitar '. e mais isto' em texto em ... (conferi: o texto está no campo)
  como:    valor do campo, acrescentado ao que já havia
```

**Sem `--acrescentar`, continua recusando.** Acrescentar por conta própria
mudaria o significado do que já está escrito — essa é decisão de quem escreveu,
não minha.

## O comando

```
cd /d D:\JARVIS
```

```
atualizar.bat
```

```
.venv\Scripts\python arvore_sonda.py --alvo "notepad.exe" --escrever " e agora sem apagar o que ja estava" --acrescentar --executar
```

O que eu espero ver:

```
  Feito: digitar ' e agora sem apagar o que ja estava' em texto em ... (conferi: o texto está no campo)

  janela:  notepad.exe — Sem título - Bloco de notas
  como:    valor do campo, acrescentado ao que já havia
  conferi: o texto está no campo.
```

E o Bloco de Notas passa a dizer `oi, mundo e agora sem apagar o que ja estava`.
Se aparecer `o campo já tem texto e eu não sobrescrevo`, faltou o
`--acrescentar` — e a mensagem agora diz isso.

## O que isso já permite

O JARVIS consegue, sem mouse, sem tela, sem `ref` copiado: achar o campo,
escrever, conferir e não apagar o que já existia. É a mão que faltava para as
skills agirem sozinhas no desktop.
