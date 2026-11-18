# JARVIS 0.91.39 — testar o jogo no seu iPhone

Seu pedido, em 18/11:

> ta bom e dps q esse apk estiver bom eu quero testar no meu iphone

## Primeiro, o fato — para você não perder uma tarde

**APK não roda em iPhone.** Não é limitação do JARVIS e não existe programa que
resolva: o iOS só executa aplicativo **assinado pela Apple**. O `.apk` é do
Android — formato, instalação e assinatura são outros. Qualquer vídeo ou
programa que prometa “instalar APK no iPhone” está mentindo ou pedindo conta de
desenvolvedor paga.

## O caminho de graça, hoje: o mesmo jogo em WebGL no Safari

Sem Mac, sem Xcode, sem conta Apple de US$ 99/ano. O **mesmo jogo** exportado em
HTML5 abre no Safari do iPhone, e o JARVIS serve essa pasta no seu Wi-Fi.

### Passo 1 — exportar o jogo em web (no motor)

| motor | onde |
|---|---|
| Unity | `File → Build Settings → WebGL` → **Switch Platform** → **Build** |
| Godot 4 | `Projeto → Exportar → Web` → **Exportar Projeto** |
| GameMaker / Construct / Defold | destino **HTML5/Web** |

**O que importa é a pasta que tem o `index.html` dentro.** No Unity, em
`Player Settings → Publishing Settings`, deixe **Compression Format: Gzip** e
**Decompression Fallback** ligado.

### Passo 2 — arrastar a pasta no `testar-no-iphone.bat`

O `.bat` novo:

- guarda o export em `storage/user-files/jogos-web/<nome>/` (sem sobrescrever);
- acha o `index.html` mesmo quando o `.zip` vem com uma pasta dentro;
- sobe um servidor só do jogo e mostra **o endereço** que você digita no
  iPhone, tipo `http://192.168.0.10:8099/`.

Também aceita o `.zip` do export. E, se já mandou antes:

```
.venv\Scripts\python testar-no-iphone.py --lista
.venv\Scripts\python testar-no-iphone.py --servir Meu-Jogo
```

### Passo 3 — no iPhone

Safari → digite o endereço da janela → jogo rodando.

- iPhone e PC na **mesma rede Wi-Fi**;
- se o Windows perguntar do firewall, marque **Redes particulares**;
- **deixe a janela aberta** enquanto testa; para parar, **feche no X**;
- `127.0.0.1` não funciona no iPhone — ali esse endereço é o próprio iPhone.

## O que muda no seu jeito de conferir

A janela do `.bat` mostra **cada arquivo que o iPhone pede**:

```
  pedido: GET / -> 200
  pedido: GET /Build/jogo.wasm -> 200
  pedido: GET /Build/jogo.data.gz -> 200
```

Isso separa dois problemas que parecem o mesmo:

| o que você vê | o que é |
|---|---|
| **nenhum** `pedido:` na janela | o iPhone não chegou no PC: rede diferente, firewall, Wi-Fi de visitante |
| `pedido:` com **404** em `.data`/`.wasm` | o export está incompleto ou com compressão diferente — gere de novo |
| abre e fica preto | veja os 404 na janela; quase sempre é o `.gz`/`.data` |

## Detalhes que fazem o jogo abrir (e que o servidor resolve)

- **`Content-Encoding` no `.gz`** — o export da Unity pede `jogo.data.gz`. Sem
  avisar que o arquivo está comprimido, o Safari entrega lixo binário e a tela
  fica preta. O servidor do JARVIS manda o cabeçalho.
- **`Range`** — sem isso, áudio e vídeo do jogo param no meio.
- **COOP/COEP** — o export com *threads* do Godot exige. Vão ligados.
- **Pasta sem barra no fim vira 301** — sem a barra, o `index.html` pediria
  `/jogo.js` em vez de `/Build/jogo.js`.

## O que este servidor não é

Ele **não** é o JARVIS aberto para a rede. É outro processo, em outra porta, que
só entrega arquivos da pasta do export. `/api/health`, as chaves e o `.env` dão
**404** ali — e existe teste pedindo cada um deles. `..`, caminho absoluto,
arquivo oculto e atalho (symlink) são recusados.

## O limite honesto

- `http://192.168.x.x` **não** é contexto seguro: export com `SharedArrayBuffer`
  (threads) pode ser recusado. Se aparecer esse erro, gere o export **sem
  threads** — o jogo continua o mesmo.
- **App Store / TestFlight** é outro assunto e outro custo: Mac + Xcode + conta
  Apple Developer (US$ 99/ano). Para *testar no seu iPhone*, o WebGL resolve
  hoje, de graça.
- Isto **não converte** o APK: o export web é gerado pelo motor, a partir do
  projeto.

## Como conferir se funcionou (do jeito barato)

1. Atualize (`atualizar.bat`).
2. Gere o export web no motor (é a única parte fora do JARVIS).
3. Arraste a pasta no `testar-no-iphone.bat` → aparece um endereço `http://…`.
4. No iPhone, abra no Safari **e** olhe a janela do PC ao mesmo tempo: o pedido
   aparecer na janela é a prova de que os dois estão na mesma rede.

Se não abrir, me diga **o que a janela mostra** quando você tenta: se aparece
`pedido:` (e com qual código) ou se não aparece nada. Um olhar nessa janela
separa rede de jogo quebrado.

## Para quem for mexer no código

- `server/jogo_web.py` — guarda o export, acha o `index.html`, serve com
  `Content-Encoding`, `Range`, 301 de pasta e COOP/COEP; escolhe o endereço
  mais provável da rede (`192.168` na frente, link-local no fim).
- `testar-no-iphone.py` / `.bat` — arrastar a pasta; `--lista`, `--servir`,
  `--porta`.
- `server/app.py` — `GET /api/jogo/web` (só lista o que está guardado).
- `server/tests/test_jogo_web.py` — **31 testes**, com servidor HTTP de
  verdade: `..`, `%2e%2e`, `.env` e `../../` dão 404, o `.gz` sai com o
  cabeçalho, e a API do JARVIS não existe naquela porta.
- `docs/JOGO-NO-IPHONE.md` — o passo a passo completo, com a tabela de “se não
  abrir”.
