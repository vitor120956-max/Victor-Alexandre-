# JARVIS 0.91.41 — dois APKs: cada um na sua pasta, com a análise do lado

Você disse:

> ta vou testar com dois apks meus
> nn sao diferentes mas quero usar os dois para teste

Entendi: são **dois pacotes seus para testar** — não “antes e depois”. E, indo
conferir o caminho, achei **dois problemas de verdade**:

1. **O `analisar-jogo.bat` pegava só o primeiro APK.** A chamada era
   `analisar-jogo.py "%~1"` — o `%~1` é o primeiro arquivo. Você arrastava dois
   e o segundo era **ignorado em silêncio**. Dava para jurar que tinha
   analisado os dois.
2. **Os dois caíam soltos na mesma pasta**, e os relatórios não tinham dono.
   Com dois builds do mesmo jogo, não dava para saber qual análise era de qual.

## O que muda

**Arraste os dois (ou mais) de uma vez.** Cada um vai para a **própria pasta**:

    storage/user-files/jogos/
      teste-1/
        teste-1.apk
        analise.txt      <- o relatório em português
        analise.json     <- o mesmo relatório, para a tela
      teste-2/
        teste-2.apk
        analise.txt
        analise.json

O console mostra um por um, com a pasta de cada:

```
  JARVIS — analisar 2 APKs, um de cada vez

  [1/2] build-teste-1.apk
  ...
  guardado em: ...\storage\user-files\jogos\build-teste-1
    build-teste-1.apk · analise.txt · analise.json

  [2/2] build-teste-2.apk
  ...
  guardado em: ...\storage\user-files\jogos\build-teste-2
    build-teste-2.apk · analise.txt · analise.json
```

E o relatório de cada um termina dizendo onde ele mora:

```
(Guardado em jogos/build-teste-1/ — o APK, o analise.txt e o analise.json
ficam juntos, um jogo por pasta.)
```

## No chat

```
analisar os dois jogos
```

analisa **todos** os pacotes, um de cada vez, avisando o nome de cada pasta.
Também entende `analisar ambos`, `analisar todos os jogos`.

Com dois pacotes na pasta, pedir um só é assim:

```
analisar jogo build-teste-1/build-teste-1.apk
```

E `analisar meu jogo` lista as pastas antes de fazer qualquer coisa:

```
Tenho 2 pacotes, cada um na pasta dele:
• build-teste-1/ — build-teste-1.apk (já analisado)
• build-teste-2/ — build-teste-2.apk (já analisado)
```

## Regras que ficaram (para dois testes não se atrapalharem)

| situação | o que acontece |
|---|---|
| arrastou o mesmo arquivo de novo | **reaproveita** a pasta (não cria cópia nem `-1`) |
| dois arquivos com o mesmo nome | `jogo/` e `jogo-1/` — nunca um por cima do outro |
| nome com espaço ou acento | vira pasta segura: `Meu Jogo Épico!.apk` → `meu-jogo-pico/` |
| nome igual em duas pastas | ele **pede qual**, em vez de escolher calado |
| APK antigo, solto em `jogos/` | continua listado e analisado (formato da 0.91.38–0.91.40) |

## Dois defeitos que só apareceram rodando

1. **`--lista` imprimia `build-teste-1,apk`.** A conversão de ponto para vírgula
   (formato brasileiro de número) era aplicada à **linha inteira**, e comia o
   ponto do nome do arquivo. Agora só o tamanho passa por essa conversão.
2. **O chat não entendia “os dois jogos”.** O verificador procurava a palavra
   `jogo` no singular — “jogos” no plural caía em `unknown` e ia para o modelo,
   que não vê APK nenhum. E o caminho `pasta/arquivo.apk` era cortado, sobrando
   só o nome do arquivo.

Os dois viraram teste de regressão.

## Como conferir se funcionou (do jeito barato)

1. Atualize (`atualizar.bat`).
2. Selecione **os dois APKs** no Explorador e arraste **juntos** em cima do
   `analisar-jogo.bat`.
3. A janela tem de mostrar `[1/2]` e `[2/2]`, e **duas pastas** em
   `storage\user-files\jogos\` — cada uma com o APK, `analise.txt` e
   `analise.json`.
4. No chat, `analisar os dois jogos`.

Se aparecer só um `[1/2]` sem o `[2/2]`, me diga: significa que o Windows
entregou um caminho só, e aí a correção é outra.

## Para quem for mexer no código

- `server/jogo.py`: `_slug()`, `partes()`, `guardar()`, `_gravar_analise()`,
  `arquivo()` (aceita nome solto, pasta e `pasta/arquivo.apk`) e `listar()`
  (agora com `partes`).
- `analisar-jogo.py` / `.bat`: o `.bat` chama `%*`; o CLI usa `guardar()`,
  aceita vários arquivos e tem `--comparar` (opcional) para antes/depois.
- `server/app.py`: upload grava em `jogos/<parte>/` e já deixa a análise ao
  lado; `/api/jogo/analisar` aceita `parte/arquivo.apk`.
- `src/lib/jarvisEngine.ts`: `todos` e caminho com pasta.
- `server/tests/test_jogo.py`: **48 testes** (13 novos desta versão), incluindo
  o que roda o `--lista` de verdade.
