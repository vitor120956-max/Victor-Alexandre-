# JARVIS 0.86.0 — o braço

O Bloco de Notas entregou o alvo:

```
texto  @4ab283d9:e11  em 227,559 (970x140)  (escreve aqui)
Onde escrever: @4ab283d9:e11 em 227,559 (970x140)
```

Nome, posição e `ref`. Com isso o JARVIS pode **agir**.

## Como se usa

Primeiro, uma leitura — é ela que produz o `ref`:

```
.venv\Scripts\python arvore_sonda.py --alvo "notepad.exe"
```

Depois, o pedido **sem** `--executar`:

```
.venv\Scripts\python arvore_sonda.py --alvo "notepad.exe" --ref @4ab283d9:e11 --acao digitar --texto "oi"
```

```
  Ação pronta (nada foi feito): digitar 'oi' em texto em 227,559 (970x140)

  janela:  notepad.exe — Sem título - Bloco de notas
  alvo:    @4ab283d9:e11  texto “”
  onde:    227,559 (970x140)
  fonte:   msaa   leitura: 4ab283d9

  repita o comando com --executar para fazer de verdade.
```

E só com `--executar` ele age:

```
  Feito: digitar 'oi' em texto em 227,559 (970x140)
  como:    foco + teclado
```

**Sem `--executar`, nada é tocado.** É o mesmo desenho do `dry_run` das outras
skills: o passo perigoso é o último, e é explícito.

## A regra que manda em tudo

`ref` não é o nome do elemento — é o **número dele naquela leitura**. A tela
muda. Por isso todo pedido **relê a janela antes** e procura o ref na leitura
nova:

```
o ref @antigo:e12 não existe nesta leitura — ele deve ser de uma leitura
anterior, e a tela já mudou. Refs válidos agora: @4ab283d9:e11, ...
```

Um `ref` velho nunca vira alvo por acaso. É a diferença entre um braço e um
chute.

## Sem mover o mouse

| ação | como |
|---|---|
| clicar | `accDoDefaultAction` — a ação que o próprio programa declara |
| sem ação padrão | `accSelect(TAKEFOCUS)` — o mesmo que o clique faria |
| digitar | foco no elemento, depois teclado (Unicode, com acento) |
| foco recusado | **para** e diz: digitar sem foco iria para outra janela |

Isso não é preferência estética. Você disse que a tela não responde a toque e
que não tem mouse USB. Clicar por coordenada seria justamente o caminho que
não funciona aí — então ele não existe aqui.

## O que ele recusa

| pedido | resposta |
|---|---|
| `ref` de leitura anterior | recusa e lista os refs válidos agora |
| moldura (Fechar, Minimizar, rolagem) | recusa — fechar janela não é trabalhar no programa |
| digitar num botão | recusa, dizendo o que o elemento aceita |
| digitar sem texto | recusa |
| agir sem `--executar` | mostra o plano e para |

## No chat, também

Nova skill: **`mesa.agir`** — 321 no registro. Mesmo desenho: recebe o `ref`,
relê, mostra o plano, e só age com `executar=true`. Tem confirmação e simulação.

## O que eu preciso de você

Duas coisas, nesta ordem:

1. **a leitura** do Bloco de Notas (para o `ref` do campo ser desta execução);
2. o **mesmo comando com `--executar`**.

Se aparecer `Feito: digitar 'oi' ...  como: foco + teclado`, o JARVIS digitou no
seu Bloco de Notas **sem mover o mouse**. Aí ele tem mãos.

Se aparecer `Não foi feito: ... o elemento recusou o foco`, me diga — significa
que a MSAA desse Bloco de Notas não aceita foco, e há outro caminho
(`put_accValue`, que escreve direto no valor do campo) que eu implemento na
próxima.
