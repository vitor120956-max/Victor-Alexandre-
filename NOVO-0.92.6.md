# 0.92.6 — o relatório do seu celular estava mentindo, e o defeito era meu

> **“Passei por 10 de 12 leituras… Nenhum problema nas áreas que o scanner mede.”**

Essa frase saiu da varredura no seu **SM-A346MU, Android 16**, e ela está errada.
Não porque o aparelho está ruim — porque a varredura **não mediu** o que dizia
ter medido. Foi o primeiro relatório de verdade, e ele achou quatro defeitos.

## O que estava quebrado

### 1. O scanner recebia uma pasta vazia

A varredura rodava **12 leituras**, mas o scanner de problemas procura **19** —
e procura por nome exato. Faltavam `getprop`, `dumpsys battery`, `df -k`,
`/proc/meminfo`, `/proc/uptime`, `ps`, `logcat`, `dumpsys gfxinfo`, `dumpsys input`,
configuração de animação e `pm list packages -3`.

Resultado: o scanner olhava um dicionário sem nenhuma dessas chaves, não achava
nada, e escrevia **“nenhum problema”** — a mesma frase de um aparelho saudável.
**Ausência de medida virou atestado de saúde.** É o pior tipo de defeito: o que
tranquiliza.

**Correção:** a lista da varredura passou a ser **derivada** da lista do scanner
(`LEITURAS_DO_SCANNER = diagnostico_celular.COMANDOS`). Acrescentar uma leitura
lá passa a valer aqui sozinha; a divergência deixou de ser possível — e um teste
compara as duas listas para sempre.

### 2. Partições sumiam, memória aparecia duas vezes

A seção **PARTIÇÕES** saía vazia mesmo sem erro (o `/proc/partitions` é negado no
Android 16). E a seção de memória era montada duas vezes: a do scanner era
**jogada fora** e só ficava o `dumpsys meminfo` — que não traz `MemAvailable`, o
número que importa.

**Correção:** partição negada vira uma linha que **explica** (“este Android não
entrega `/proc/partitions` sem root — não é falta de cabo”) em vez de sumir. As
duas leituras de memória convivem, a do scanner primeiro.

### 3. “Leituras que não responderam” repetia a mesma negativa 3 vezes

`Permission denied` aparecia três vezes: da varredura, do scanner e da anatomia,
cada uma com um prefixo diferente. **Correção:** deduplicação pelo miolo do erro.

### 4. O cabeçalho saía sem o modelo

O seu relatório abriu em **“Android 16”**, sem dizer qual aparelho. O `getprop`
inteiro passa de 60 KB e a linha do modelo cai depois do corte. **Correção:**
quando o modelo não está na leitura, o JARVIS pergunta direto —
`adb shell getprop ro.product.model` — em vez de aceitar um título cego.

## O que muda para você

- O `ver-tudo-no-celular.bat` agora faz **28 leituras** (o texto dizia 25 — número
  inventado; agora ele conta a lista de verdade).
- O console passa a mostrar **O QUE ESTÁ ERRADO** (com a medida e o que fazer) e
  **O QUE DÁ PARA MELHORAR** — antes esses blocos simplesmente não existiam.
- A aba **Anatomia** ganhou o botão **“Ver tudo no aparelho”** e o cartão da
  varredura. Antes essa leitura só existia no console: quem não abre `.bat` não
  tinha acesso a ela.
- O cartão traz o que o scanner achou, o mapa do aparelho, o que não foi possível
  ler e o que não dá sem root.

## O teste que faltava

O teste antigo passava porque o **exemplo de teste** era menor que a lista de
comandos: ele nunca exercitava o caminho real. Agora existe um teste que compara
a lista de comandos com o dicionário de exemplos — se faltar exemplo para uma
leitura, o teste falha, e o buraco não volta.

E o veredito ganhou uma regra dura: sem as leituras de saúde, a frase é
**“não deu para medir”**, nunca “está tudo bem”.

## Medido

- **pytest 4 261** (0 falhas, 7 pulados) — **12 casos novos**.
- Suíte do módulo: **34 casos** em `test_varredura.py`.
- `vitest` 243, `tsc` limpo, build OK, manifesto **669** arquivos em 0.92.6.
- Ponta a ponta com um `adb` que imita o seu aparelho (mesmas recusas de
  `/proc/partitions`, `/data/app` e sensores térmicos): o relatório agora abre
  com **“SM-A346MU · Android 16”**, mostra as **25 de 28** leituras que
  responderam e diz **por que** as 3 não responderam.

## O que eu preciso de você

Rode o **`atualizar.bat`** e depois o **`ver-tudo-no-celular.bat`** de novo. Me
mande a tela. A diferença que você deve ver: o cabeçalho com o modelo, a seção
de **O QUE ESTÁ ERRADO** (se houver algo) e nenhuma frase repetida em
“leituras que não responderam”.
