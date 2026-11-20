# Testar o seu jogo no iPhone

> **O APK não roda no iPhone.** Não é limitação do JARVIS e não há programa que
> resolva: o iOS só executa aplicativo assinado pela Apple. O arquivo `.apk` é
> do Android — formato, instalação e assinatura são outros.

O caminho de graça, sem Mac e sem conta de desenvolvedor, é **exportar o mesmo
jogo em WebGL/HTML5** e abrir no Safari do iPhone. O JARVIS serve esse export
na sua rede Wi-Fi e mostra o endereço.

## “Baixar no iPhone” tem dois sentidos

| o que você quer | dá? | o que custa |
|---|---|---|
| **ícone na tela de início** (abre em tela cheia, parece app) | **sim, de graça** | nada: Safari → Compartilhar → “Adicionar à Tela de Início” |
| **arquivo `.ipa` instalado** (app de verdade, assinado) | só com conta **Apple Developer** | US$ 99/ano + Mac (ou build na nuvem) |
| **APK instalado** | **não** | não existe: o iOS não executa `.apk` |
| **publicar na App Store** | sim, com conta paga | US$ 99/ano + revisão da Apple |

O JARVIS faz o primeiro: a página servida já sai com `apple-touch-icon`,
`apple-mobile-web-app-capable` e `manifest` injetados (o arquivo do export no
disco continua intacto), e o ícone é desenhado por ele — um PNG de 180×180 e
512×512, sem depender de arquivo extra no export.

---

## Antes de tudo: o veredito para **este** pacote (0.92.1)

Desde a 0.92.1 a análise do APK na aba **Meu jogo** responde sozinha a pergunta
“dá para passar isso para o iPhone de graça?” — e a resposta muda com o pacote,
porque “APK” não é um tipo só:

| o que é o pacote | dá de graça? | por quê |
|---|---|---|
| jogo feito em Unity, Godot, GameMaker, Construct, Cocos, Defold, LibGDX | **sim**, pelo export WebGL do **projeto** | o APK não vira site; o projeto exporta |
| jogo em Unreal | não | a Epic removeu o export HTML5 na 4.24 |
| app em Flutter / React Native | não, a partir do APK | só o projeto gera build web |
| app Cordova / PhoneGap | sim, se você tem o projeto | o conteúdo já é uma página (`www/`) |
| ReVanced / Vanced do YouTube (`com.google.android.youtube`, `com.vanced.android.youtube`) | **não** | é app Android; não existe versão iOS, nem paga |
| microG (`app.revanced.android.gms`, `com.microg`) | **não** | reimplementação dos serviços do Google **para Android**; no iOS não existe |
| motor não reconhecido | não prometo | sem saber o motor, “exporte em WebGL” seria chute |

O veredito sai no `relatorio.iphone` (JSON), no texto do chat e no cartão no topo
da análise — com **passo a passo**, **custo** e **limite**. Ele nunca promete
`.ipa` de graça: o único caminho gratuito é WebGL no Safari com ícone na tela de
início.

### “Não quero mudar nada no app — só quero que rode no iPhone”

Essa é a pergunta certa, e a resposta tem três degraus. Nenhum deles recompila o
APK: o JARVIS **não converte** APK em app de iPhone, e nenhum programa faz isso.

| o que você aceita | o que instala | custo | dura |
|---|---|---|---|
| o YouTube normal | app oficial (App Store) | grátis | enquanto quiser |
| YouTube sem anúncio **no navegador** | bloqueador de conteúdo grátis no Safari + `m.youtube.com` na Tela de Início | grátis | enquanto quiser |
| o **mesmo tipo** de app modificado | `.ipa` já pronto (YTLite/uYou+) por **sideload** com AltStore/Sideloadly e seu Apple ID comum | grátis | **7 dias** (reinstalar pelo PC) |
| idem, sem renovar toda semana | o mesmo `.ipa`, com conta Apple Developer | US$ 99/ano | 1 ano |

O sideload é o mais perto de “não mudar nada”: você não compila, não altera o
APK e não passa pela App Store — instala um pacote que alguém já modificou.
O preço é o prazo de 7 dias do Apple ID gratuito, e a renovação precisa do PC
com AltServer/iTunes na mesma rede.

**microG:** não existe no iPhone e não faz falta. Lá você entra direto com a
conta Google do sistema; o microG só existe para dar login aos apps
modificados no **Android**.

**O que o JARVIS não faz, e não é falta de vontade:** instalar qualquer coisa no
iPhone, gerar `.ipa` ou assinar app. Assinatura de iOS é da Apple, e o
ferramental exige macOS (ou AltServer no PC com iTunes). O que ele faz é ler o
pacote, dizer qual caminho existe para **aquele** arquivo e servir o export web
quando o pacote é um jogo com projeto.

## 1. Exportar o jogo para web

O export é feito **no motor**, não no JARVIS — é o motor que transforma o
projeto em arquivos que o navegador entende.

### Unity

1. `File → Build Settings…`
2. Selecione **WebGL** na lista e clique em **Switch Platform**.
3. `Player Settings → Publishing Settings`:
   - **Compression Format**: `Gzip` (o JARVIS já sabe servir `.gz`);
   - **Decompression Fallback**: ligado (evita tela preta em servidor simples).
4. **Build** e escolha uma pasta, por exemplo `MeuJogo-WebGL`.
5. **A pasta boa é a que tem o `index.html` dentro.**

### Godot 4

1. `Projeto → Exportar…` e adicione um preset **Web**.
2. Em **Variant**, prefira o export **sem threads** se o jogo for simples: o
   navegador do iPhone só liga `SharedArrayBuffer` em contexto seguro, e
   `http://192.168.x.x` não é um deles. (Se aparecer erro falando de
   `SharedArrayBuffer`, é isso.)
3. **Exportar Projeto** para uma pasta com o `index.html`.

### GameMaker / Construct / Defold

Todos têm destino HTML5/Web. O resultado é sempre **uma pasta com
`index.html`** — é ela que interessa.

---

## 2. Servir no JARVIS

### Pela tela (0.92.1)

Na aba **Meu jogo**, embaixo da análise, há a área **Testar no iPhone**: envie o
**`.zip` da pasta do export** (a que tem `index.html` dentro). O servidor achata
o zip do Unity sozinho e confirma que o `index.html` existe; zip sem ele é
recusado com a explicação. Pasta não sobe pelo navegador — o `.zip` é o formato
que dá.

A tela mostra o endereço do servidor do jogo (`http://<ip-do-pc>:8099/`) e quais
exports já estão guardados. Quem serve os arquivos continua sendo o
`testar-no-iphone.bat`, em outra janela.

### Pela pasta (CLI)

**Arraste a pasta do export em cima do `testar-no-iphone.bat`.**

Também aceita o `.zip` dela (inclusive o zip do Unity, que vem com uma pasta
dentro — o JARVIS acha o `index.html` sozinho).

Na mão:

```bat
.venv\Scripts\python testar-no-iphone.py "C:\caminho\MeuJogo-WebGL"
.venv\Scripts\python testar-no-iphone.py MeuJogo-WebGL.zip --nome Meu-Jogo
.venv\Scripts\python testar-no-iphone.py --lista
.venv\Scripts\python testar-no-iphone.py --servir Meu-Jogo --porta 8099
```

O export fica guardado em `storage/user-files/jogos-web/<nome>/` (a mesma área
isolada dos outros arquivos do JARVIS; dá para mudar com `JARVIS_FILES_ROOT`).

---

## 3. Abrir no iPhone

1. Deixe a janela do `testar-no-iphone.bat` aberta — **ela é o servidor**.
2. No iPhone, **na mesma rede Wi-Fi do PC**, abra o **Safari** e digite o
   endereço que aparece na janela, por exemplo:

   ```
   http://192.168.0.10:8099/
   ```

3. Para parar: **feche a janela no X**. (Não precisa de `Ctrl+C`.)

### Deixar como app na tela de início

Com a página aberta no Safari:

1. toque em **Compartilhar** (o quadrado com a seta para cima);
2. **Adicionar à Tela de Início**;
3. confirme o nome — o ícone do jogo já está lá.

Abre em tela cheia, sem a barra do Safari. **Não** é um app assinado: é o mesmo
site, com ícone e sem moldura. Não passa pela App Store e não tem custo.

### Se não abrir

| o que aparece | o que fazer |
|---|---|
| janela do `.bat` sem **nenhum** `pedido:` | o iPhone não chegou no PC: mesma rede? Wi-Fi de visitante? firewall? |
| aviso do Windows Firewall | marque **Redes particulares** (não “públicas”) |
| o endereço não abre no iPhone, mas abre no PC | o PC tem mais de uma placa: o `.bat` mostra um segundo endereço; confira com `ipconfig` qual é o da rede Wi-Fi |
| abre e fica preto | olhe a janela: cada arquivo pedido aparece com o código. `404` em `.data`/`.wasm` quer dizer export incompleto ou compressão diferente — gere de novo com `Gzip` + *Decompression Fallback* |
| erro falando de `SharedArrayBuffer` | export com threads: gere sem threads (Godot) ou use um servidor com HTTPS |

`127.0.0.1` **não** funciona no iPhone: ali esse endereço é o próprio iPhone.

---

## 4. O que o servidor do jogo é — e o que ele não é

- É um servidor **de arquivos**, em outra porta (`8099` por padrão), que só
  entrega o conteúdo da pasta do export.
- **Não** expõe a API do JARVIS: `/api/health`, chaves, biblioteca e `.env` não
  existem ali — pedir qualquer um deles dá `404` (há teste para isso).
- `..`, caminho absoluto, arquivo oculto e atalho (symlink) são recusados.
- Manda `Content-Encoding` para os `.gz`/`.br` do export (sem isso o Safari
  recebe lixo binário e a tela fica preta) e `Accept-Ranges` para áudio/vídeo.
- Manda `Cross-Origin-Opener-Policy` e `Cross-Origin-Embedder-Policy`, que o
  export com threads precisa.
- Serve `/jarvis-icone-180.png`, `/jarvis-icone-512.png` e
  `/manifest.webmanifest` — gerados em memória, não existem no disco.
- Injeta as tags do ícone no `index.html` **servido**; o arquivo do export
  nunca é alterado.

---

## 5. Quando você quiser de verdade na App Store

Aí o caminho muda de assunto e de custo:

- **TestFlight** — build iOS assinado, exige Mac com Xcode (ou serviço de
  build na nuvem) e conta **Apple Developer** (US$ 99/ano);
- **App Store** — mesma conta, mais revisão da Apple;
- converter o projeto: Unity e Godot exportam para iOS, mas o build e a
  assinatura só acontecem em macOS.

**Nada disso é “baixar no iPhone” de graça.** O que dá para baixar de graça é o
ícone na tela de início (seção 3). Para o jogo existir como app instalado de
verdade, o caminho é `.ipa` assinado — e a assinatura é da Apple, não do JARVIS.

Nada disso é o que você pediu agora — para **testar no seu iPhone**, o export
WebGL resolve hoje, de graça, e é o mesmo jogo.
