# JARVIS 0.91.38 — “analisa meu jogo e melhora ele”

Seu pedido, em 18/11:

> eu to criando um jogo q ele e apk quero q o jarvis possa analisar meu jogo e
> melhorar ele

Agora o JARVIS lê o **APK do seu jogo** e responde com o que está dentro dele:
qual motor foi usado, quantas arquiteturas, o que pesa, se a assinatura está
certa, quais permissões o jogo pede — e, em cada problema, **onde exatamente
mexer**.

## Como usar — dois passos

**1. Arraste o APK em cima do `analisar-jogo.bat`.**

O arquivo pode estar em qualquer pasta (Downloads, Desktop, a pasta do
export do Unity/Godot). O `.bat` copia para a pasta de jogos do JARVIS
(`storage/user-files/jogos`) **sem sobrescrever** — se já existir, entra um
`-1` no nome — e já mostra o relatório na tela.

**2. No chat, diga:**

```
analisar jogo meujogo.apk
```

ou só:

```
analisar meu jogo
```

Sem nome, ele lista o que tem na pasta (e analisa direto quando só tem um).

Também entende `como melhorar meu jogo?`, `analisa o apk do jogo`,
`otimizar meu jogo` e `melhorar o jogo`.

## O que ele olha

| o que | de onde sai |
|---|---|
| pacote, versão, minSdk, targetSdk | `AndroidManifest.xml` — inclusive o **binário**, lido sem Android SDK |
| motor e versão | marca real no pacote: `libunity.so`, `libgodot*.so`, `libUE4*.so`, `assets/bin/Data`, `*.pck`… |
| arquiteturas | pastas `lib/arm64-v8a`, `lib/armeabi-v7a`, `lib/x86` |
| peso | tamanho descompactado, por área (`lib/`, `assets/`, `res/`, dex) e os 10 maiores arquivos |
| assinatura | v1 (META-INF) e v2/v3 (bloco `APK Sig Block 42`) |
| permissões | as do manifesto, com o rótulo em português e as sensíveis marcadas |

## Exemplo de saída

Este é um APK de exemplo (não é o seu), para você ver o formato:

```
Análise do jogo “meujogo.apk”:
com.exemplo.meujogo · versão 0.3 · Unity
90,2 MB descompactado em 10 arquivos · ABIs: arm64-v8a, armeabi-v7a, x86 · DEX: 1
Android: minSdk 21 · targetSdk 33

1. [CRÍTICO] APK de depuração (debuggable=true)
   O que é: Este pacote permite depurador e é mais lento: o código não foi otimizado.
   Por que importa: É o build de teste. Publicar assim expõe o app a inspeção e é recusado pela Play.
   Como melhorar: No motor, troque de Development Build / Debug para Release, e gere de novo.
   Onde: Unity: File → Build Settings → desmarque Development Build · Godot: Export → Release
2. [ATENÇÃO] Backup do app ligado (allowBackup=true)
   Onde: AndroidManifest: android:allowBackup="false" (ou android:fullBackupContent)
3. [ATENÇÃO] targetSdk antigo (33)
   Onde: Unity: Player Settings → Other Settings → Target API Level · Godot: Export → Target SDK
4. [ATENÇÃO] 3 arquiteturas no mesmo pacote
   Por que importa: O aparelho usa uma só: as outras só engordam o download (~40,9 MB em lib/).
   Como melhorar: Publique um AAB (App Bundle) em vez de APK universal.
5. [ATENÇÃO] Assinatura antiga (só v1)
6. [ATENÇÃO] Permissões sensíveis pedidas
   O que é: CAMERA (usar a câmera)
7. [INFO] Onde está o tamanho
   O que é: lib: 40,9 MB · assets: 39,8 MB · classes.dex: 6,3 MB — total 90,2 MB.

Maiores arquivos (é aqui que o peso está):
    39.9 MB  assets/bin/Data/data.unity3d
    14.7 MB  lib/arm64-v8a/libunity.so
    13.6 MB  lib/x86/libunity.so
    12.6 MB  lib/armeabi-v7a/libunity.so
     6.3 MB  classes.dex

Isto é o que se vê do pacote pronto. Não descompilei o jogo nem recompilei: o
que muda o jogo de verdade — equilíbrio, controles, ritmo — só você decide, e
o ajuste é feito no motor e no build de novo.
(Análise feita no seu PC, sem enviar o APK para lugar nenhum.)
```

*(No relatório de verdade cada achado vem completo — o exemplo acima está
encurtado nos itens 2 a 6 para não ficar gigante aqui.)*

## O que ele **não** faz — e por que isso está escrito

- **Não descompacta nada no disco.** Lê por dentro do ZIP, em memória. Teto de
  600 MB, 60 mil arquivos, manifesto até 4 MB.
- **Não descompila o jogo.** Não tem engenharia reversa de `il2cpp`, não mexe
  no seu projeto, não recompila.
- **Não mede quadros por segundo nem “diversão”.** Isso só roda no aparelho.
  Ele lê o pacote e diz o que o pacote mostra — nada de conselho inventado.
- **Não envia o APK para lugar nenhum.** Tudo no seu PC, e o rodapé do
  relatório diz isso.

## Como conferir se funcionou (do jeito barato)

Você tem que atualizar e testar, então o caminho mais curto é este:

1. Atualize (`atualizar.bat`) e suba (`iniciar-jarvis.bat`).
2. Arraste o APK do seu jogo no `analisar-jogo.bat`.
3. A tela tem de mostrar, nas primeiras linhas, o **nome do pacote**, o
   **motor** e a **versão** do jogo — se o motor sair vazio, o APK não tem
   nenhuma das marcas conhecidas e o relatório vai dizer isso, sem chutar.
4. No chat, `analisar meu jogo` — o balão vem com o selo
   **`· ANÁLISE DO JOGO (PC)`**.

Se algo não bater, me diga o que apareceu na **primeira linha** do relatório:
é ela que diz se o arquivo foi lido como APK de verdade.

## Para quem for mexer no código

- `server/jogo.py` — leitor de AXML (pool UTF-16, resource map, start
  elements), detecção de motor, tamanho por área, assinatura e o texto.
- `server/app.py` — `GET /api/jogo/arquivos`, `POST /api/jogo/upload`
  (exige `confirmed`), `GET /api/jogo/analisar?arquivo=&texto=`.
- `analisar-jogo.py` / `analisar-jogo.bat` — a ferramenta de arrastar.
- `server/tests/_axml.py` — monta um `AndroidManifest.xml` **binário** de
  verdade para os testes; `server/tests/test_jogo.py` — 35 testes.

Dois defeitos que o teste pegou antes de chegar em você:

1. O leitor lia os atributos na posição errada (`posicao + headerSize` em vez
   de `posicao + 16 + attributeStart`), e o `<manifest>` chegava sem nenhum
   atributo.
2. `classes.dex` era tratado como marca de motor: existe em **todo** APK,
   então todo jogo virava “LibGDX”. Agora marca genérica não identifica nada.

Um teste usa o manifesto do molde e exige que a string `uses-permission`
apareça em **UTF-16**: procurar ASCII dentro do ZIP nunca acharia nada, e o
teste impede que alguém volte a tentar por esse caminho.
