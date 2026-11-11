# JARVIS 0.87.0 — sem copiar código

Você colou isto:

```
--ref @SEU_REF_AQUI
```

A recusa funcionou — o ref não existia, o JARVIS se negou a agir. Mas **o erro
foi meu**: eu escrevi um comando que pedia para você copiar um código de uma
saída para a linha seguinte. Você disse que não quer ter que fazer nada, e
copiar ref é fazer.

O JARVIS já sabe onde se escreve — ele escreveu isso na sua tela:
`Onde escrever: @c7aa400c:e11 em 445,577 (970x140)`. Ele só não estava usando
esse conhecimento sozinho.

## Agora é um comando

```
.venv\Scripts\python arvore_sonda.py --alvo "notepad.exe" --escrever "oi, mundo"
```

```
  Ação pronta (nada foi feito): digitar 'oi, mundo' em texto em 445,577 (970x140)

  janela:  notepad.exe — Sem título - Bloco de notas
  alvo:    @c7aa400c:e11  texto “”
  onde:    445,577 (970x140)
  fonte:   msaa   leitura: c7aa400c

  repita o comando com --executar para fazer de verdade.
```

E com `--executar`:

```
.venv\Scripts\python arvore_sonda.py --alvo "notepad.exe" --escrever "oi, mundo" --executar
```

Nenhum ref para copiar. Ele acha o campo, mostra onde vai escrever, e escreve.

O `--ref` continua existindo para quem quiser apontar um elemento específico —
clicar num botão, por exemplo. Para escrever, ninguém precisa mais dele.

## O erro agora fala português

O erro do ref apareceu assim na sua tela:

```
{"erro": "o ref @SEU_REF_AQUI não existe nesta leitura — ..."}
```

JSON numa linha só, sem ninguém ter pedido JSON. Agora:

```
  NÃO DEU: o ref @SEU_REF_AQUI não existe nesta leitura — ele deve ser de uma
  leitura anterior, e a tela já mudou. Refs válidos agora: @c7aa400c:e11, ...
```

`--json` continua entregando o formato de máquina para quem é máquina.

## O que continua igual

- **relê a janela antes de agir** — ref velho nunca vira alvo por acaso;
- **não move o mouse** — a ação vem do elemento (foco + teclado);
- **sem `--executar`, nada é tocado**;
- moldura (Fechar, Minimizar, rolagem) continua recusada como alvo.

## O comando, agora sem marcador

```
cd /d D:\JARVIS
```

```
atualizar.bat
```

```
.venv\Scripts\python arvore_sonda.py --alvo "notepad.exe" --escrever "oi, mundo" --executar
```

Se aparecer:

```
  Feito: digitar 'oi, mundo' em texto em 445,577 (970x140)
  como:    foco + teclado
```

o JARVIS escreveu no seu Bloco de Notas sem tocar no mouse. Aí ele tem mãos.

Se aparecer `o elemento recusou o foco`, me diga — há um segundo caminho
(`put_accValue`, que escreve direto no valor do campo) que eu faço na próxima.
