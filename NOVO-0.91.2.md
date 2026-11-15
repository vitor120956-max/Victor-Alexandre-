# JARVIS 0.91.2 — o passo que não leu nada não conta como feito

Duas coisas que só apareceram quando eu fui olhar a **execução de verdade**, e
não só o plano.

## 1. O maestro aceitava passo vazio

Rodei o procedimento de conserto com o diário de erros vazio. O primeiro passo
respondeu:

```
{"lido": false, "motivo": "Não há erro no diário e você não colou nenhum."}
```

E o maestro seguiu em frente: montou o dossiê, propôs o patch, e terminou com
"todos os 3 passos rodaram". Um dossiê de um erro que ninguém leu. Era
exatamente o buraco que eu tinha listado como "o primeiro lugar a medir".

Agora o passo **declara** o que precisa voltar verdadeiro:

```python
Passo(skill="conserto.diagnosticar", campos={"erro": "$erro"}, exigir="lido")
```

Se voltar `lido: false`, a fila para e a resposta é:

```
Parei no passo 1 (conserto.diagnosticar): a skill rodou mas devolveu lido=False:
Não há erro no diário e você não colou nenhum.
```

É declarado, não adivinhado: se a skill não tem campo de confirmação, o passo
não tem `exigir` e nada muda.

## 2. A execução não mostrava o que cada passo trouxe

Antes:

```
1. conserto.diagnosticar — feito
2. conserto.dossie — feito
Todos os 3 passos rodaram.
```

Isso não diz nada sobre o resultado. Agora cada passo mostra o que voltou:

```
1. conserto.diagnosticar — feito
   voltou: lido=True, fonte=colado, proximo=O traceback não cita arquivo deste projeto…
2. conserto.dossie — feito
   voltou: # Dossiê de conserto — JARVIS - versão: 0.75.0 - skill que falhou: não registrada…
3. conserto.propor — feito
   voltou: Sem chave de IA configurada, eu não escrevo o patch — inventar correção é pior…
Todos os 3 passos rodaram.
```

E o plano passou a avisar o que cada passo precisa confirmar:

```
1. conserto.diagnosticar
   por quê: dizer onde quebrou e por quê, antes de propor conserto
   só vale se voltar lido=true
```

## 3. O erro começa no traceback

Se você colar o erro junto com a frase — "conserta esse erro: Traceback
(most recent call last)…" —, o diagnóstico recebia a frase inteira. Agora ele
corta no traceback. Sem traceback, o texto vai inteiro: erro de uma linha só é
legítimo.

## Medido

- `--orquestrar "conserta o erro do meu programa" --autorizar` no sandbox:
  antes, 3 passos "feitos" com conteúdo vazio; agora, cada passo mostra o que
  voltou, e o passo 1 barra a fila quando não leu nada.
- **54 testes** no `test_maestro.py` (eram 49), suíte verde.

## O que continua sem prova

O maestro ainda **não rodou no seu PC**. O que mudou é que, quando rodar, a
resposta vai mostrar o que cada passo trouxe — e vai parar quando não trouxer
nada, em vez de te entregar um dossiê bonito de coisa nenhuma.
