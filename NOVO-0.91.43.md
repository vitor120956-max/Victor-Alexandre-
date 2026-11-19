# JARVIS 0.91.43 — sim, a engenharia reversa funciona (medido, não prometido)

Sua pergunta, em 19/11:

> e o engenharia reversa ta funcionando?

Resposta curta: **sim**. Mas “deve estar” não valia, então subi o JARVIS, mandei
arquivos de verdade para a área reversa e apertei os cinco botões, um por um.
O que está abaixo é o que a tela devolveu — não é leitura de código.

## O que eu mandei e o que voltou

Montei um APK de teste (ZIP com `AndroidManifest.xml`, `classes.dex` e
`lib/arm64-v8a/libunity.so`), um `app.js` com Electron e usei também um
executável ELF e uma imagem PNG de verdade.

| botão | o que voltou |
|---|---|
| **Inspecionar** | “ZIP / arquivo compactado”, entropia **7,2747**, 4 entradas, **46 strings** |
| **Layout** | as 4 entradas do ZIP, com tamanho comprimido e CRC |
| **Strings** | achou `lib/arm64-v8a/libunity.so` e `classes.dex` — os nomes que identificam o pacote |
| **Entropia** | 7,2747 no arquivo; nenhuma região com cara de cifrada |
| **JavaScript** | 1 módulo analisado, e o fato `electron.ipc-renderer` na **linha 2** |

Fora do ZIP: um ELF de verdade voltou “ELF64 little-endian”, **31 seções** e 2
imports; um PNG voltou com entropia **7,7625**.

E em **todas** as respostas vem `executed: false` e `readOnly: true`: a Reversa
lê o arquivo, ela não roda o arquivo. Isso não mudou.

## O que estava errado não era a análise — era a recusa muda

Os cinco botões estavam certos. O problema era o que a tela fazia quando
**recusava** um arquivo:

1. **APK acima de 25 MB.** Você escolhia o arquivo e… nada. Sem frase, sem
   erro, sem envio. A tela ficava exatamente igual. Como todo APK de jogo passa
   de 25 MB, a impressão era “a Reversa não funciona” — quando na verdade ela
   tem teto de 25 MB e o APK do jogo pertence à aba **Meu jogo** (600 MB).
2. **Pasta com arquivo descartado.** Ao arrastar uma pasta, o que não cabia era
   jogado fora calado, e a tela ainda dizia **“pasta enviada”**, contando só os
   que sobraram. O arquivo grande sumia sem nome e sem motivo.

Agora a tela diz o que recusou, com nome, tamanho e motivo. Para o APK grande,
embaixo do seletor:

> “meu-jogo.apk” tem 90,0 MB e a Reversa aceita até 25,0 MB. Para o APK do seu
> jogo use a aba **Meu jogo** (até 600 MB): ela lê o manifesto, descobre o motor
> e diz o que melhorar.

Numa pasta com vários descartes, a frase de cada um aparece na ordem e, se
sobrar, o resto vem contado: *“E mais 2 arquivos fora pelos mesmos motivos.”*
E o “enviado” só aparece sobre o que **foi** enviado: nada de comemorar em cima
de arquivo perdido.

## O mesmo cuidado do lado da API

Quem chama o endereço de upload direto recebia, quando o arquivo passava do
teto:

> A requisição excede o limite de tamanho.

Sem número e sem saída. Agora a resposta é `413` dizendo o teto (**25 MB**), o
destino (aba **Meu jogo**, 600 MB) e devolvendo `limitBytes`. A aba do jogo tem
a mesma frase no teto dela, também presa por teste.

## Como conferir em dois minutos (do jeito barato)

1. `atualizar.bat` e abra o JARVIS.
2. **Menu → Reversa**.
3. Arraste **um arquivo pequeno** (um `.js`, um `.png`, ou um `.exe`/ELF) na
   área de upload — ele aparece na lista à esquerda.
4. Clique em **Inspecionar**. Tem de aparecer o formato, o tamanho e o
   SHA-256; depois **Layout**, **Strings** e **Entropia** no mesmo arquivo.

Para o APK do jogo, o caminho é o outro: **Menu → “Meu jogo”**. Se você tentar
um APK grande na Reversa de propósito, agora ele **avisa** e manda para lá, em
vez de não fazer nada.

Se a tela não mudar, é cache: **Ctrl+F5**.

## O que continua feio (e fica escrito)

Mandar 26 MB pela API, no fio, ainda termina em **conexão cortada** antes de o
JSON de recusa chegar: o servidor recusa pelo tamanho declarado e fecha sem ler
o corpo, e quem está escrevendo recebe *reset*. Pela tela isso não acontece —
a triagem barra antes de enviar. Drenar dezenas de MB só para recusar seria pior
que o sintoma, então isto fica registrado como limitação, não como promessa.

## Para quem for mexer no código

- `src/lib/artefatos.ts` — a triagem pura: `classificarArquivos()`,
  `explicarRecusa()`, `resumoDaTriagem()`.
- `src/lib/artefatos.test.ts` — **14 testes**, um por jeito de sumir calado.
- `src/pages/ReversePage.tsx` — usa a triagem no seletor de arquivo e no
  arrastar de pasta; o aviso de sucesso fala só dos aceitos.
- `server/app.py` — o `413` com teto, destino e `limitBytes`.
- `server/tests/test_reverse.py` (**16**) e `server/tests/test_jogo.py` (**52**)
  prendem as duas frases.
- `docs/ARVORE.md` — a seção 0.91.43 com a tabela das medições.
