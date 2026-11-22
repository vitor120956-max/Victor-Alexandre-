# 0.94.0 — o aparelho mediu, e a tela disse “sem medida”

Segundo relatório de verdade: **27 de 29 leituras**, SM-A346M, Android 16, bateria
a 63% carregando, 440 pacotes de sistema. O scanner achou o `[MEDIA]` do
`com.dti.telefonica` travando. E aí, na fila de suspeitas, escreveu
**“sem medida no aparelho”** em todas as quatro — inclusive na do app travado,
que estava medido no `logcat` duas telas acima.

## 1. A fila inteira dizia “sem medida” — e era um contrato, não um chute

`cruzar()` espera o **relatório** do scanner, porque é por `p["id"]` que ele
descobre o que o aparelho sustenta. A 0.92.9 passava as **saídas cruas**
(`{"serial", "saidas", "falhas"}`) — que não têm `problemas`. Sem `problemas`,
toda evidência vira “não achei”, e “não achei” virou **“sem medida”**.

Numa versão anterior eu tinha “consertado” isso consertando a **tabela** de
evidências. A tabela estava certa; o que chegava nela era o dicionário errado.
Agora `montar()` guarda a saúde que já calculou (`_saude`) e o cruzamento usa
**ela** — o scanner não roda duas vezes, e não há como divergir. `_saude` é
removido antes de imprimir.

```
1. Um app específico travando (ANR)  (medido no aparelho)
```

## 2. “495 instalados” e “55 instalados” na mesma tela

O total do aparelho é 495 (`pm list packages`). `pm list packages -3` — **só os
que você instalou** — dá 55. A otimização `menos-apps` usava o segundo número
com a palavra “instalados”, colada no primeiro. Três contas com o mesmo nome:

```
Pacotes de sistema (o Android em si)   440
Apps instalados (sistema + seus)       495
Fora da loja do fabricante              55
```

E a otimização agora diz de onde vem o número dela:

> Desinstalar os apps que você não abre: libera espaço e reduz processo em
> segundo plano — são **55 apps que você mesmo instalou** (apps de fábrica não
> entram nesta conta).

## 3. A mesma limitação térmica, duas vezes

`diagnostico_celular` dizia “Este aparelho não expõe sensores térmicos sem root”
e `anatomia` dizia “muitos Androids escondem `/sys/class/thermal`”. Os miolos
eram diferentes, então a dedup da 0.93.0 não pegava — e as duas apareciam em
**LEITURAS QUE NÃO RESPONDERAM**. Agora há **um texto só**, escrito nos dois
lugares, e a lista mostra uma linha:

> Sem temperatura de CPU: este Android esconde `/sys/class/thermal` de quem não
> é root — o aquecimento fica sem número (a da bateria continua aparecendo).

De quebra, a frase “o scanner não lê memória por app” também era escrita duas
vezes (scanner e anatomia). Ficou uma.

## O que o seu relatório mostrou de novo

- **27 de 29 leituras** — as duas que faltam são `/data/app` e
  `/proc/partitions`, ambas `Permission denied`: desenho do Android, não falha.
- **RAM 7,3 GB com 35% disponível** — o suficiente para o Android não estar
  fechando app por memória. Isso **tira** memória da frente das suspeitas, e a
  fila mostra isso.
- **Bateria 63%, 30,7 °C, carregando** — nada de térmico. Calor também sai da
  frente, mesmo sem leitura de CPU.
- **ZRAM de 12 GB com 762 MB físicos para 2,36 GB de swap** — o aparelho está
  comprimindo memória, mas não está no limite.
- O travamento do `com.dti.telefonica` é de app, não do sistema: aparece no
  `logcat -b crash` com `FATAL EXCEPTION`.

## O que continua valendo

- Sem root. O JARVIS lê o que o Android publica para `adb` e diz o que não lê.
- “Sem medida” nunca virou “está tudo bem”: quando não há número, a frase diz
  **por que** não há.
- Nada é executado no aparelho: 29 leituras, todas de leitura.
