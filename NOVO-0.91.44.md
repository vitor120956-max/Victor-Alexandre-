# JARVIS 0.91.44 — jogo de 500 MB ou 1 GB: onde ele entra

Sua pergunta, em 19/11:

> ta mas e se o meu app ou jogo tiver 1gb ou 500 mb?

Resposta curta: **500 MB já entrava. 1 GB não entrava — agora entra.** E o
número novo não é promessa: eu subi o JARVIS, montei os dois APKs e enviei.

## O que eu medi

| arquivo | antes da 0.91.44 | agora |
|---|---|---|
| **500 MB** (524 MB de APK) | entrava — **3,1 s** | entra igual |
| **1 GB** (1.101 MB de APK) | **recusado**: “O APK passa de 600 MB” | entra — **6,8 s**, com a análise gravada ao lado |
| **2,1 GB** | recusado pelo teto de 600 MB | recusado em **8 ms**, com o número e a saída |

O APK de 1 GB voltou com o pacote certo (`com.teste.gigante`), motor **Unity**,
5 arquivos, `arm64-v8a`, 3 achados — e os arquivos `analise.txt` e
`analise.json` ficaram na pasta dele, `jogos/meu-jogo-1gb/`.

O que importa por baixo: o envio sempre foi feito em **pedaços de 1 MB**. A
memória do servidor não cresce com o tamanho do arquivo — medido, o pico foi de
**83,8 MB para 89,7 MB** entre o começo e o fim de um envio de 1 GB. O que
faltava era só o número do teto e espaço em disco.

## O que mudou no código

1. **Teto de 600 MB → 2 GB** (`MAXIMO_BYTES` em `server/jogo.py`). A tela
   anuncia o mesmo número (“aceita .apk, .aab, .apks, .xapk até **2 GB**”), e um
   teste impede os dois lados de se afastarem — foi assim que o defeito de
   2 MB × 600 MB apareceu na 0.91.42.
2. **Disco conferido antes de escrever.** Um APK de 1 GB precisa de 1 GB livre
   mais **500 MB de folga** (durante o envio o arquivo existe duas vezes: o
   temporário do pedido HTTP e a pasta do jogo). A conta é feita antes do
   primeiro byte e repetida a cada 64 MB. Sem espaço, a resposta é `507` com a
   frase inteira:
   > Não há espaço no disco para este APK: ele tem 1,1 GB e o disco tem 120 MB
   > livres (preciso de mais 500 MB de folga). **Nada foi guardado** — libere
   > espaço e envie de novo.
   Nada de pasta pela metade, nada de erro em inglês no meio do caminho.
3. **Os números falam a mesma língua da tela** (`rotulo_bytes`): 2 GB, 600 MB,
   524 MB, 1,1 GB — com vírgula, como você lê.
4. **A recusa ensina a saída.** Acima de 2 GB:
   > O APK passa de 2 GB, o teto da aba “Meu jogo”. Acima disso, envie o APK
   > sem o OBB (o OBB não é analisado) ou o AAB do jogo.

## Testes novos (todos reproduzem o seu caso)

`server/tests/test_jogo.py` — **56 testes**, com quatro novos:

- **1 GB passa do middleware** — o teto anunciado não recusa mais 1 GB;
- **o teto vale sem `content-length`** — envio em fluxo (corpo em pedaços) era
  a brecha: só o cabeçalho barrava, e o cabeçalho é escolha do cliente. Agora o
  próprio manipulador corta em 1 MB de teto no teste e **não sobra arquivo**
  pela metade;
- **disco cheio é dito antes de encher o disco** — com 120 MB livres simulados,
  a resposta é `507`, não um arquivo truncado;
- **o rótulo** de tamanho (2 GB, 1,1 GB, 524 MB).

## Para publicar na Play, o caminho é outro

Um APK de 1 GB serve para **testar no seu aparelho**, não para a loja: pelo
lado do Google Play, o APK legado tem teto de **100 MB**, com arquivos de
expansão (OBB) de até **2 GB cada**, e o recomendado é **AAB** com Play Asset
Delivery ([limites oficiais](https://developer.android.com/games/playgames/publish-deploy),
[expansion files](https://developer.android.com/google/play/expansion-files)).
Por isso a recusa acima de 2 GB manda para o **AAB** — que a aba aceita — em vez
de só dizer “não”.

O JARVIS continua analisando **o pacote**: manifesto, motor, ABIs, assinatura e
onde o peso está. O OBB não é analisado, e isso está dito na tela, não escondido.

## Como conferir no seu PC

1. `atualizar.bat` e abra o JARVIS.
2. **Menu → “Meu jogo”** (se a tela não mudar: **Ctrl+F5**).
3. Arraste o APK grande. A linha da área de envio tem de dizer **“até 2 GB”**.
4. Ao terminar, aparece `1 APK guardado em <pasta>/` e a análise logo abaixo —
   com pacote, motor e os achados.

Se mandar um arquivo acima de 2 GB, o esperado é a frase com o número **antes**
de qualquer envio — nem um byte sai do seu PC.

## Para quem for mexer no código

- `server/jogo.py` — `MAXIMO_BYTES` (2 GB), `MARGEM_DISCO` (500 MB),
  `rotulo_bytes()`, `espaco_livre()` e a conferência em `guardar()`.
- `server/app.py` — a rota de upload: espaço conferido antes e a cada 64 MB;
  `413 FILE_TOO_LARGE` e `507 DISK_FULL` com frase e números.
- `src/pages/JogoPage.tsx` — `LIMITE_BYTES` / `LIMITE_TEXTO`.
- `src/lib/artefatos.ts` — a frase da Reversa que manda o APK grande para a aba
  certa agora cita **2 GB**.
- `docs/ARVORE.md` — a seção 0.91.44, com a tabela das medições.
