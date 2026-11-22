# 0.93.0 — o relatório rodou de verdade, e achou quatro mentiras minhas

Você rodou. O `ver-tudo-no-celular.bat` fez 25 de 28 leituras, montou a fila de
suspeitas e achou um app travando. **Funcionou.** E mesmo assim ele mentiu em
quatro pontos — todos só aparecem com aparelho de verdade, porque o `adb` de
teste respondia bonito demais.

## 1. “«which su»: sem resposta” — um alarme por você **não** ter root

Esse item apareceu em **LEITURAS QUE NÃO RESPONDERAM**. É um falso positivo puro:
`which su` num aparelho sem root devolve **código 1 com saída vazia** — não é
falha, é a resposta correta (“não tem su”, que é o que se quer).

A varredura tratava “código ≠ 0 e saída vazia” como erro. Agora, quando não há
**mensagem de erro**, a leitura é guardada vazia e o scanner diz o que é:

> Não há binário de `su` no PATH — não é alarme, é o normal num aparelho sem root.

## 2. A fila dizia “sem medida no aparelho” para **tudo**

Quatro suspeitas, todas marcadas “sem medida”, num relatório com 25 leituras
boas. O motivo era uma tabela de evidências morta em três das cinco linhas:

| a tabela pedia | o problema realmente se chama | resultado |
|---|---|---|
| `app-travado` | `app-nao-responde` / `app-travando` | **nunca casava** |
| `aquecendo` | `aquecendo`, `bateria-quente-carregando` | parcial |
| `app-travando` | não estava ligado a nada | **nunca somava** |

Ou seja: **a função que devia mostrar “o aparelho mediu isso” nunca mostrava.**
Era o oposto do desenho. Corrigido — e agora um teste compara a tabela com os ids
que o scanner realmente emite, para não voltar a divergir.

## 3. O modelo do aparelho podia sair **truncado**

O cabeçalho abriu com “SM-A346M”. O modelo real é esse, mas o risco era real: o
`getprop` inteiro passa de 60 KB e o parser aceitava um valor **cortado no meio**
como se fosse inteiro (`[ro.product.model]: [SM-A346` virava `SM-A346`). Agora
linha sem o `]` final é descartada e a leitura é refeita por comando.

## 4. “440 instalado de fábrica” e “55 instalados” na mesma tela

Dois números diferentes com rótulos que pareciam o mesmo total. `pm list packages
-s` lista **quais pacotes são de sistema** (440). O total de apps no aparelho é
outro (`pm list packages` → 55 fora da loja). Agora a seção diz:

```
Pacotes de sistema (o Android em si)    440
Apps instalados no aparelho              55
```

## Bônus: a mesma negativa duas vezes

`Permission denied` do `/proc/partitions` aparecia duas vezes — a varredura
escreve `“cmd”: erro` e a anatomia escreve só `erro`. A dedup da 0.92.6
comparava o texto inteiro e não pegava. Agora compara o **miolo do erro** e fica
com a versão que diz **qual comando** falhou.

## O que o seu relatório **acertou**

Vale registrar, porque é o que estava funcionando:

- **Fila de suspeitas montada** com os 4 sintomas que você marcou:
  → **toque fantasma em 1º**, app travando em 2º, calor em 3º, memória em 4º.
  Essa ordem está certa para o seu relato (“se mexe sozinho” + “só para ao apagar
  a tela” é a assinatura do toque fantasma).
- **“Há app fechando sozinho — com.dti.telefonica”**: achado real, medido no
  `logcat`, com o nome do app.
- **Estado do aparelho**: bootloader travado, `verified boot: green`, build
  `user`, `ro.debuggable 0` — tudo certo, e é **isso** que explica por que o
  `adb root` não existe aí (pergunta da 0.92.8).
- **Bateria 95%, 31,7 °C, carregando, saúde boa.** Nada de errado.
- **RAM: 7,3 GB total, 3,2 GB disponíveis (43%)** — folgado.

## O que ainda não dá para descobrir

Sendo explícito, porque a fila pode enganar:

- **toque fantasma não se mede.** Nenhum `dumpsys` publica “toque sem dedo”. A
  fila aponta a causa mais provável dado o seu relato; quem fecha é o teste da
  capa/película.
- **temperatura de CPU sem root**: o seu aparelho esconde `/sys/class/thermal`.
  Só a da bateria aparece. Se for calor, o número do processador não vem.
- **o motivo interno do travamento do `com.dti.telefonica`** está no relatório
  completo de falhas, que só o próprio app grava.

## Medido

- **pytest 4 291** (0 falhas, 7 pulados) — **8 casos novos**.
- `test_varredura.py` agora com **64 casos**.
- Reproduzi o seu relatório com um `adb` que imita o SM-A346M, **incluindo o
  `which su` devolvendo código 1 e saída vazia**: o item sumiu das falhas, o
  modelo saiu certo, os dois totais de app apareceram, e a negativa duplicada
  virou uma linha só.
- `vitest` 243, `tsc` limpo, manifesto **673** arquivos em 0.93.0.

## O que eu preciso de você

Rode o **`atualizar.bat`** e o **`ver-tudo-no-celular.bat`** de novo. As
diferenças que você **deve** ver:

1. **nada** de “«which su»: sem resposta”;
2. as suspeitas com a marca **“medido no aparelho”** quando houver medida (com o
   app travando, a suspeita de app deve sair marcada);
3. os dois números de app, com rótulos diferentes;
4. `Permission denied` uma vez só.

Se algo continuar estranho, me manda a tela — cada rodada sua tem achado coisa
que o meu `adb` de teste não acha.
