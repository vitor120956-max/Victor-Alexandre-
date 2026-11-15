# JARVIS 0.91.4 — traceback numa linha só também vale

Achado ao preparar o teste que eu ia te mandar. Se eu tivesse mandado sem
conferir, você ia ver um dossiê assim:

```
2. conserto.dossie — feito
   voltou: # Dossiê de conserto — versão: 0.91.3 - exceção: : - causa classificada: **desconhecida**
```

`exceção: :` — vazia. E a causa, "desconhecida".

## Por quê

O conserto procurava o tipo da exceção com uma regra que exige o `KeyError: ...`
**no começo de uma linha**. Num traceback normal, é assim mesmo:

```
Traceback (most recent call last):
  File "server/app.py", line 417, in execute_skill
KeyError: 'pedido'
```

Mas quando o texto vem numa linha só — terminal estreito, chat, ou o próprio
maestro montando o pedido —, o `KeyError` fica no meio:

```
Traceback (most recent call last): File "server/app.py", line 417, in execute_skill KeyError: 'pedido'
```

Nenhuma linha começa com `KeyError`, então a busca falhava em silêncio. O
dossiê saía pela metade e a causa caía em "desconhecida".

## O que mudou

Se o começo de linha não achar nada, a busca pega a **última** ocorrência em
qualquer posição — num traceback, a exceção é sempre a última coisa escrita.
Continua valendo o começo de linha primeiro, porque é o formato canônico.

O resultado do mesmo comando agora:

```
2. conserto.dossie — feito
   voltou: # Dossiê de conserto — versão: 0.91.4 - exceção: KeyError: 'pedido'
           - arquivo: `server/app.py` linha 417 (função `execute_skill`)
           - causa classificada: **chave_ausente**
```

## Testes

Dois novos: um prova que a linha única acha `KeyError` **e** classifica a causa;
outro que garante que o traceback de várias linhas continua idêntico — a
correção não podia quebrar o caminho que já funcionava.

## O que isso não conserta

O dossiê continua não sendo um patch. Sem chave de IA, o passo 3 para e diz que
não vai inventar correção — isso é o previsto, não um defeito.
