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

---

# 0.94.1 — o celular entra aqui, em vez de eu tentar sair

Você perguntou se eu não podia entrar no celular e testar. **Não posso** — e não
é falta de vontade. O `adb` conversa por USB com a máquina em que o JARVIS roda;
do meu lado existe um repositório, não um cabo. Nenhum comando daqui atravessa a
internet e chega no seu aparelho.

Mas havia um jeito melhor de atender o pedido, e ele existia porque **o arquivo
do relatório não guardava o que o `adb` respondeu** — só o que a tela decidiu
mostrar. Era por isso que, a cada versão, eu dependia de você colar um print:
o print é a conclusão, não a medida.

## `--pacote`: o celular vem para cá

```
ver-tudo-no-celular.bat --pacote
```

Ao lado do `relatorio.json` sai um `.zip` de ~7 KB com:

| arquivo | o que é |
|---|---|
| `leituras.json` | a resposta de cada um dos comandos de leitura (getprop, df, meminfo, ps, pm list, logcat…) |
| `falhas.json` | as negativas do Android (`Permission denied`), que explicam 27 de 29 |
| `limites.json` | o que a anatomia não conseguiu ler |
| `relatorio.json` | o que a tela mostrou, para comparar |
| `LEIA-ME.txt` | o que tem e o que não tem, em linguagem de gente |

## O que **não** vai no pacote

O zip sai do seu PC para o meu. Então ele passa por uma limpeza antes:

| campo | vira |
|---|---|
| serial, IMEI, operadora | `<removido>` |
| nome de app instalado | `app-N` (a contagem continua exata: 440 / 495 / 55) |
| nome de arquivo seu | `item` (a contagem e o tipo continuam) |
| e-mail, telefone no log | `<email>`, `<telefone>` |
| pasta em foco, app do ANR | `com.<app>` |

O que fica é o que reproduz o defeito: modelo, versão, memória, bateria, as
negativas, o `FATAL EXCEPTION`. **Nome de app não é diagnóstico; é vida privada.**

De quebra, isso consertou um vazamento que já existia: a seção “Aplicativos fora
da loja” listava os 12 primeiros pacotes **na tela e no arquivo** — quem recebia
o relatório via quais apps você tem.

## `--refazer`: o relatório sem o celular

```
escanear-celular.py --refazer SM-A346M-20261122-201808.zip
```

Roda o mesmo parser e os mesmos limiares sobre as leituras do zip. Não toca em
aparelho nenhum. Daqui eu conserto, escrevo o teste e te devolvo a versão — sem
esperar o próximo print.

## O que os testes pegaram (e eu não teria visto lendo o código)

1. o pacote **omitia** `pm list packages`, e sem ele 440/495/55 viravam vazio;
2. o `ps` do Android tem **duas** colunas, e ao trocar o nome por marcador a
   linha ficava ilegível — “fechar app” desaparecia do relatório;
3. faltavam `thermal` e as falhas da anatomia: o relatório refeito vinha com
   menos limitação que o original, e o defeito “mudava de cara”.

O teste compara o refeito com o original campo a campo. Ele reprovou três vezes
até o pacote ficar fiel — que é exatamente o trabalho.

---

# 0.94.2 — “zip do quê?”: o pacote nos dois caminhos

Duas coisas apareceram na pergunta.

**A primeira é minha culpa:** eu escrevi “me manda o zip” sem dizer o que é. O
zip é um arquivo de ~7 KB que fica **ao lado do relatório**, na mesma pasta
`storage\diagnosticos\`, com o mesmo nome. Ele contém a resposta crua de cada
comando de leitura e o `relatorio.json` que a tela mostrou.

**A segunda é um defeito de verdade:** o `--pacote` só funcionava na varredura
completa. Quem usava o scanner sozinho —

```
escanear-celular.bat --pacote
```

— tinha a opção aceita e **nenhum zip gerado**. O `diagnosticar()` não guardava
as leituras cruas; só o `varrer()` guardava. Corrigido: agora o scanner também
guarda e também empacota.

O teste novo reprovou duas vezes, e a segunda foi feia: o zip do scanner levava
a chave `comandos`, e **cada item dela é `adb -s RXCW400ZV3F shell …`** — o
serial do aparelho viajava como texto, no único lugar em que ele não estava
sendo limpo. Agora a lista não vai, e o teste confere só o que sai de fato no
arquivo.

## Como usar, em uma linha

```
ver-tudo-no-celular.bat --pacote     (a varredura completa)
escanear-celular.bat --pacote        (só o scanner)
```

Rodou, apareceu `Pacote para mandar: ...zip` — é esse arquivo. Se não aparecer
essa linha, o zip não foi gerado.
