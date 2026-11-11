# JARVIS 0.87.1 — não era o Bloco de Notas recusando

Você mandou escrever e recebeu isto:

```
Não foi feito: digitar 'oi, mundo' em texto em 339,298 (970x69) — o elemento
recusou o foco (accSelect). Sem foco, digitar iria para outra janela — parei.
```

Aconteceu de verdade: o JARVIS pediu o foco, o pedido voltou como recusa, e
ele parou em vez de digitar no programa errado. Isso foi certo.

Mas **o Bloco de Notas não recusou nada**. O JARVIS pediu a coisa errada.

## O que estava errado

Os métodos da acessibilidade do Windows são numerados. A lista é esta:

| número | método | para que serve |
|---|---|---|
| 20 | `get_accDefaultAction` | ler a ação do elemento |
| **21** | **`accSelect`** | **dar foco / selecionar** |
| 22 | `accLocation` | posição do elemento |
| 23 | `accNavigate` | navegar na árvore |
| **25** | **`accDoDefaultAction`** | **executar a ação** |
| 27 | `put_accValue` | escrever no valor do campo |

O JARVIS usava **21** para "executar a ação" e **23** para "dar foco". Um a
mais, outro a menos. Então, quando ele quis dar foco, chamou `accNavigate` — que
devolve "não é por aqui" — e leu isso como "o programa recusou". O erro que
você leu era um erro do meu código com cara de problema do Windows.

## O que mudou

**1. Os números certos.** Foco é 21, ação é 25.

**2. Três degraus para escrever**, do mais natural ao mais direto:

1. foco no elemento exato e teclado;
2. foco no campo inteiro e teclado (quando o texto é um pedaço do campo);
3. escrever direto no valor do campo (`put_accValue`) — sem teclado e sem foco.

**3. O JARVIS confere de quem é o teclado antes de digitar.** Ele pergunta ao
Windows qual janela está com o foco; se não for a que ele leu, ele não digita.
"Digitei" e "digitei no lugar certo" precisam ser a mesma frase.

**4. Ele lê o campo de volta depois de digitar.** A resposta agora diz o que
foi visto, não o que foi tentado:

```
Feito: digitar 'oi, mundo' em texto em 445,577 (970x140) (conferi: o texto está no campo)
```

Se o campo não mostrar o texto, ele diz `atenção: o campo não mostrou o texto —
confira na tela` em vez de comemorar.

**5. O campo nunca é sobrescrito.** O terceiro degrau substitui o conteúdo, por
isso só roda quando o campo está vazio. Apagar o que você escreveu para "dar
certo" seria pior do que não escrever.

**6. `janela: —` virou o nome da janela.** O plano lia um campo que a leitura
não devolve; agora mostra `notepad.exe — Sem título - Bloco de notas`.

## O comando

```
cd /d D:\JARVIS
```

```
atualizar.bat
```

```
.venv\Scripts\python arvore_sonda.py --alvo "notepad.exe" --escrever "oi, mundo" --executar
```

O que eu espero ver agora:

```
  Feito: digitar 'oi, mundo' em texto em ... (970x69) (conferi: o texto está no campo)

  janela:  notepad.exe — Sem título - Bloco de notas
  alvo:    @...:e11  texto “”
  onde:    ...,... (970x69)
  fonte:   msaa   leitura: ...
  como:    foco + teclado
  conferi: o texto está no campo.
```

Se em vez disso vier `accSelect devolveu 0x...` ou `o campo inteiro também não
aceitou foco`, cole a saída: aí o terceiro degrau entra e a mensagem diz o
número que o Windows devolveu — é com esse número que eu acho o caminho.
