# JARVIS 0.91.3 — o maestro rodou no seu PC (e mostrou três defeitos)

Primeira execução de verdade, na sua máquina:

```
1. conserto.diagnosticar — feito
   voltou: lido=True, fonte=colado, proximo=O traceback não cita arquivo deste projeto…
2. conserto.dossie — feito
   voltou: # Dossiê de conserto — JARVIS - versão: 0.75.0 - exceção: : …
3. conserto.propor — feito
   voltou: O provedor não respondeu: AIUnavailable.
Todos os 3 passos rodaram.
```

Três coisas erradas nisso, e nenhuma era do seu PC.

## 1. Ele tratou a sua frase como se fosse o erro

`fonte=colado` — só que você não colou erro nenhum. O maestro pegou "conserta o
erro do meu programa" e entregou ao diagnóstico como se fosse traceback. A
skill confiou, respondeu `lido: true`, e o dossiê saiu com `exceção: :` vazio.

Agora o maestro só passa um erro quando **há** um erro: traceback, ou uma linha
com `KeyError`/`ValueError`/`Exception` e afins. Fora isso, manda vazio e a
skill vai ao diário — que é onde os erros de verdade estão. Se o diário também
estiver vazio, a resposta é:

```
Parei no passo 1 (conserto.diagnosticar): a skill rodou mas não concluiu (lido=false):
Não há erro no diário e você não colou nenhum.
O que fazer: o diário de erros não tinha nada e o pedido não trouxe erro.
             Cole o traceback junto com o pedido.
```

Repare no **O que fazer**. O passo agora declara a própria saída:

```python
Passo(skill="conserto.diagnosticar", exigir="lido", dica="cole o traceback junto com o pedido…")
```

## 2. O dossiê dizia "versão: 0.75.0"

O `conserto.py` tinha `VERSAO = "0.75.0"` — a versão em que o módulo nasceu.
Só que o dossiê é sobre a instalação **de agora**. Eram dois números com o mesmo
nome, e o relatório que você mandaria para alguém dizia uma versão que não
existe mais no seu PC.

Agora sai `versão: 0.91.3`, lida da fonte única. Há teste que recusa o
`0.75.0` no texto.

## 3. "3. conserto.propor — feito" sem ter proposto nada

O provedor não respondeu (`AIUnavailable`) e o passo apareceu como feito,
porque a skill devolve erro dentro do próprio resultado em vez de levantar
exceção. O maestro só sabe o que o passo declara — então o passo passou a
declarar `exigir="proposto"`:

```
Parei no passo 3 (conserto.propor): a skill rodou mas não concluiu (proposto=false):
Sem chave de IA configurada, eu não escrevo o patch — inventar correção é pior que não corrigir.
```

Isso não é falha: é o comportamento certo. Sem chave, ele **recusa**. O que
estava errado era chamar isso de "feito".

## O que ficou provado

- O maestro executa no Windows, na sua instalação, e mostra o que cada passo
  trouxe.
- Com traceback colado, os três passos rodam de verdade: o dossiê saiu com
  `versão: 0.91.3`, `exceção: KeyError: 'nome'` e `arquivo: server/app.py linha 42`.
- Quando um passo não conclui, a fila para e diz onde.

## O que continua sem prova

- **A busca na web (`pesquisar-guardar`).** Nunca rodou no seu PC. Falta medir
  se `JARVIS_HOST_REDE=1` está ligado no seu `.env` — a 0.91.1 passou a ler
  esse arquivo, mas ninguém ainda viu a busca funcionar aqui.
- **`baixar-repositorio`.** Precisa de autorização e de rede. Não rodou.
- **Conserto com chave de IA.** Hoje ele para no passo 3 sem chave, que é o
  previsto. Com chave, o passo 3 chamaria o modelo — e isso ainda não foi
  medido nesta versão.
