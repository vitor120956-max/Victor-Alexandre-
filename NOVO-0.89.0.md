# JARVIS 0.89.0 — ele abre o programa sozinho

A 0.88.0 escreveu no Bloco de Notas. Mas quem abriu o Bloco de Notas foi você.

Isso é pedir trabalho a quem pediu que o JARVIS fizesse o trabalho. Agora é uma
linha só, com o Bloco de Notas fechado:

```
.venv\Scripts\python arvore_sonda.py --programa "bloco de notas" --escrever "oi, mundo" --executar
```

```
  Abri o Bloco de notas. Feito: digitar 'oi, mundo' em texto em 476,472 (970x69) (conferi: o texto está no campo)

  janela:  notepad.exe — Sem título - Bloco de notas
  alvo:    @da9f5b32:e11  texto “”
  onde:    476,472 (970x69)
  fonte:   msaa   leitura: da9f5b32
  como:    valor do campo (put_accValue, sem teclado)
  conferi: o texto está no campo.
```

## O que ele faz, em ordem

1. vê se o programa já está aberto (pelo processo, não pelo título solto);
2. se não estiver, **abre** — da lista fechada: bloco de notas, paint,
   calculadora, cmd, powershell, explorador…;
3. **espera a janela aparecer** (até 12 segundos). Abrir e ler no mesmo
   instante é ler o vazio — era isso que faltava;
4. acha o campo de escrita, escreve, e **confere lendo de volta**.

Se a janela já estava aberta, ele usa a que existe e não abre uma segunda.

## O que ele se recusa a fazer

- **Abrir sem `--executar`.** Sem a opção, ele só diz: *"o Bloco de notas não
  está aberto: eu abriria, esperaria a janela e escreveria 'oi, mundo'. Nada
  foi aberto e nada foi escrito."* Abrir programa já é agir.
- **Abrir o que não está na lista.** Nada de caminho livre, nada de `.exe`
  digitado. A lista é fechada de propósito.
- **Ficar esperando para sempre.** Se a janela não aparecer em 12 segundos, ele
  diz e para.

## Pela conversa também

Nasceu a skill **`mesa.ditar`**: você diz *"escreve oi no bloco de notas"* e ele
abre, escreve e confere. Pela API ela exige `JARVIS_HOST_PC=1` e confirmação —
porque ali quem pede não é você na linha de comando, é o modelo.

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

**Feche o Bloco de Notas antes** (o X dele). Assim você vê o JARVIS abrindo,
esperando e escrevendo — do zero, sem você tocar em nada.

Se aparecer:

```
  Abri o Bloco de notas. Feito: digitar 'oi, mundo' em texto em ...
  conferi: o texto está no campo.
```

então ele não tem só mãos: tem o começo do movimento.
