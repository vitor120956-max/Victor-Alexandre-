# JARVIS 0.91.45 — o OBB agora é analisado (o que dá, e o que não dá)

Sua pergunta, em 19/11:

> pq o obb não é analisado? pode fazer o javis analisar pfv

Feito. E vale dizer o que mudou de verdade — porque “o OBB não é analisado” era
uma resposta **pela metade**, não uma lei da física.

## Por que antes não era

O OBB não é um APK. Ele não tem `AndroidManifest.xml`, não tem `classes.dex`,
não tem assinatura. As perguntas do APK (pacote, motor, SDK…) não se respondem
nele. Só que as perguntas **do OBB** se respondem — e são justamente as que
quebram o jogo em silêncio.

## O que o JARVIS lê agora

| o que | como |
|---|---|
| **o nome** | `main.<versionCode>.<pacote>.obb` — e `patch.` também |
| **o conteúdo**, se abre como ZIP | quantos arquivos, quanto pesa cada pasta, os 10 maiores |
| **compressão desperdiçada** | WAV/JSON/TGA guardados sem compressão |
| **o que está pesando** | `assets/`, `Audio/`, `Textures/`… com o conselho certo para cada um |
| **entropia** | amostra de 2 MB (não lê 2 GB para dar um número) |
| **a conferência com o APK** | pacote e versão, lado a lado |

O que ele **não** faz: decifrar. OBB cifrado com o `jobb` não expõe a lista sem
a chave, e o relatório diz isso com todas as letras — em vez de inventar nomes
de arquivo.

## O achado que só existe porque os dois são lidos juntos

Este é o motivo principal de valer a pena:

> **CRÍTICO — O número do OBB não bate com a versão do APK**
> O OBB se chama `main.20.com.exemplo.jogo.obb` (versão 20); o APK desta pasta é
> a versão 14.
> **Por que importa:** o arquivo é encontrado pelo nome
> `main.<versionCode>.<pacote>.obb`. Com o número antigo, o jogo procura
> `main.14.com.exemplo.jogo.obb`, não acha, e abre sem os dados — mesmo com o
> OBB do lado do APK.
> **Como melhorar:** gere o OBB de novo junto com este APK, ou renomeie para
> `main.14.com.exemplo.jogo.obb`.

Isso acontece com build refeito, OBB de teste antigo e pacote baixado de outro
lugar. Antes, passava despercebido: o arquivo estava lá, do lado do APK, e o
jogo abria “sem os dados” sem ninguém saber por quê.

## Onde o OBB é guardado

Na **mesma pasta do APK do mesmo jogo**. Se o OBB chegar primeiro, a pasta nasce
com o nome do pacote (`jogos/com-exemplo-jogo/`) e o APK que chegar depois entra
nela — não viram duas pastas com metade do jogo em cada.

## Como usar

1. `atualizar.bat` e abra o JARVIS.
2. **Menu → “Meu jogo”** (se a tela não mudar: **Ctrl+F5**).
3. Arraste o **APK** e o **`.obb`** juntos na área, ou um de cada vez — tanto faz
   a ordem.
4. O painel mostra a análise do APK e, embaixo, o bloco **“OBB — os dados fora
   do APK”**, com o selo **confere / NÃO confere**.

## Medido no JARVIS de verdade (porta 8151)

| cenário | resultado |
|---|---|
| `main.14.com.exemplo.jogo.obb` + APK v14 | ZIP, **8 arquivos**, **8,6 MB** descompactado, entropia **3,08**, maiores arquivos listados, selo **confere** |
| `main.20…obb` na pasta do APK v14 | **CRÍTICO**, com o nome correto sugerido |
| OBB enviado antes do APK | o APK entrou na pasta `jogos/com-exemplo-jogo/` — uma pasta, o par junto |
| OBB sozinho | relatório só do OBB, com “envie o APK para eu conferir pacote e versão” |

**Testes:** `server/tests/test_obb.py` — **22 casos** (nome, conteúdo, opaco,
compressão, conferência, ordem do envio, rota, XAPK com OBB dentro). Suíte
inteira: **4083 passed / 7 skipped**; vitest **243**; `tsc` e pyflakes limpos.

## O tamanho continua com teto — e ele é do formato

- **2 GB por OBB** (é o limite do próprio formato de expansão do Android);
- um `main` e um `patch`, cada um até 2 GB;
- acima de 1,5 GB, o caminho recomendado pela Google passa a ser **Play Asset
  Delivery** (AAB), que baixa por partes.

E, para publicar na Play no formato antigo: **APK de até 100 MB + OBB**. Um APK
de 1 GB serve para testar no seu aparelho; para a loja, o caminho é outro — e o
JARVIS diz isso no relatório, não deixa você descobrir no envio.

## Para quem for mexer no código

- `server/obb.py` (novo) — `do_nome()`, `analisar()`, `conferir()`.
- `server/jogo.py` — `parte_do_obb()`, `parte_do_obb_orfao()`,
  `relatar_parte()`, `relatar_obb()`, `texto_obb()`.
- `server/app.py` — a rota de upload aceita `.obb` e escolhe a pasta pelo pacote.
- `src/pages/JogoPage.tsx` + `src/lib/api.ts` — o bloco do OBB e o selo.
- `server/tests/test_obb.py` — os 22 casos.
