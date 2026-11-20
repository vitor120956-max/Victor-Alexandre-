# JARVIS 0.92.1 — “passar esses dois apps para o iPhone de graça”

Seu pedido, em 19/11:

> to testando e quero passar esses dois apps/jogo para o iphone de graca

Olhei os dois pacotes que estão na sua tela. **Nenhum dos dois é jogo** — e é
por isso que a resposta antiga (“exporte em WebGL”) não servia para eles.

| o que está na sua pasta | pacote | dá no iPhone? |
|---|---|---|
| `vanced-to-revanced-com-google-android-youtube-…` | `com.google.android.youtube` | **não** — é o ReVanced do YouTube |
| `vanced-to-vanced-gms-microg-v0.3.1-3` | `app.revanced.android.gms` | **não** — é o microG |

## Por que não dá

O iPhone só executa aplicativo assinado pela Apple. `.apk` é do Android — não é
limitação do JARVIS, é do sistema. E, nesses dois casos, não existe versão de
iOS:

- **ReVanced/Vanced** é um YouTube modificado para Android. Não há build para
  iOS, nem paga. O que existe no iPhone é o **app oficial, grátis, na App
  Store** — sem bloqueio de anúncio nativo e sem reprodução em segundo plano.
  Para bloquear anúncio no Safari: **Ajustes → Safari → Extensões** e uma
  extensão gratuita de bloqueador.
- **microG** é a reimplementação dos serviços do Google **para Android**, feita
  para dar login aos apps modificados. No iPhone não há equivalente — e não
  seria necessário: o sistema já tem as contas dele. Não há o que instalar.

### “Não quero mudar nada no app — só quero que rode no iPhone”

Entendi. Então o caminho é **não mexer no APK** mesmo — ele não vai. O que existe,
sem recompilar nada:

| o que você aceita | o que instala | custo | dura |
|---|---|---|---|
| o YouTube normal | app oficial (App Store) | grátis | sempre |
| sem anúncio **no navegador** | bloqueador grátis no Safari + `m.youtube.com` na Tela de Início | grátis | sempre |
| o **mesmo tipo** de app modificado | `.ipa` já pronto (YTLite/uYou+) por **sideload** com AltStore/Sideloadly e seu Apple ID | grátis | **7 dias** (renova pelo PC) |
| idem, sem renovar toda semana | o mesmo `.ipa` com conta Apple Developer | US$ 99/ano | 1 ano |

O sideload é o mais próximo do seu pedido: você não compila nem altera o APK —
instala um pacote que já foi modificado. O preço é o prazo de 7 dias do Apple ID
gratuito.

**microG:** não existe no iPhone e não faz falta — lá você entra direto com a
conta Google do sistema.

**O que eu não faço:** instalar no iPhone, gerar `.ipa` ou assinar app. A
assinatura é da Apple e o ferramental pede macOS (ou AltServer no PC com iTunes).
Eu leio o pacote, digo qual caminho existe para **aquele** arquivo e sirvo o
export web quando é jogo com projeto.

## O que mudou na tela

**1. Cartão “No iPhone, de graça” em toda análise.** O veredito agora é por
pacote, lido do manifesto e do motor, com **passo a passo**, **custo** e
**limite**. Ele sai igual no texto do chat, no `analise.txt` e no JSON.

- motor com export web (Unity, Godot, GameMaker, Construct, Cocos, Defold,
  LibGDX) → **sim, de graça**, com o menu exato daquele motor;
- Unreal → não: a Epic removeu o HTML5 na 4.24;
- Flutter/React Native → não a partir do APK: só o projeto gera build web;
- motor desconhecido → não prometo, e digo que seria chute.

**2. Área “Testar no iPhone”**, embaixo da análise: você manda o **`.zip` da
pasta do export** (a que tem `index.html` dentro) direto pela tela — sem `.bat`
para arrastar. O servidor achata o zip do Unity, confere o `index.html` e
mostra o **endereço real** (`http://<ip-do-pc>:8099/`) para digitar no Safari.

**3. O caminho continua o mesmo:** no motor do jogo, gere **WebGL** (Unity) ou
**Web** (Godot); envie o zip aqui; abra o `testar-no-iphone.bat`; no iPhone, no
mesmo Wi-Fi, abra o endereço no Safari → **Compartilhar → Adicionar à Tela de
Início**. Ícone em tela cheia, sem App Store, sem conta paga.

## Se você quiser um jogo seu no iPhone

O caminho é o da tabela acima — **export web do projeto**. Se um dia o projeto
for Unity ou Godot, eu já sei o passo do seu motor e digo na análise, sem você
procurar no menu.

## Defeito achado no caminho

O relatório de um pacote que **não é jogo** terminava com “o que muda o jogo de
verdade — equilíbrio, controles, ritmo”. Era a frase de outro relatório; para
app, agora ele diz o que de fato não fez: não descompilei, não executei, não
modifiquei.

## Medido

- pytest: **4 148** (0 falhas, 7 pulados) — 14 casos novos (10 em `test_jogo.py`,
  4 em `test_jogo_web.py`);
- vitest **243**; `tsc` limpo;
- 352 skills; manifesto com a versão 0.92.1.

> Como conferir: `conferir-versao.bat` deve dizer **0.92.1**. Se a área nova não
> aparecer, **Ctrl+F5**.
