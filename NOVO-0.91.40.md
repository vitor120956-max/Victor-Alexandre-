# JARVIS 0.91.40 — dá para “baixar” no iPhone, sim: como ícone na tela de início

Sua pergunta, em 18/11:

> entao so da para rodar via web?? nao da para baixar no iphone?

A pergunta tem duas respostas, e elas não são a mesma coisa:

| o que “baixar no iPhone” pode querer dizer | dá? | custo |
|---|---|---|
| **ícone na tela de início**, abre em tela cheia | **sim** | zero |
| app `.ipa` instalado (assinado) | só com conta **Apple Developer** | US$ 99/ano + Mac |
| APK instalado | **não** | não existe no iOS |
| publicar na App Store | sim, com conta paga | US$ 99/ano + revisão |

**O que você consegue hoje, de graça, é o primeiro.** E na prática é o que
importa para testar e mostrar: abre com um toque, sem barra de endereço, com
ícone próprio — igual a um app instalado.

## O ícone é este

![ícone do jogo](icone-do-jogo-exemplo.png)

Ele é **desenhado pelo JARVIS** (sem imagem pronta, sem Pillow), em 180×180 (o
tamanho que o iPhone usa na tela de início) e 512×512.

## Como põe no iPhone — 3 toques

1. Arraste a pasta do export WebGL no `testar-no-iphone.bat` e abra o endereço
   no **Safari** do iPhone.
2. Toque em **Compartilhar** (o quadrado com a seta para cima).
3. Toque em **Adicionar à Tela de Início** e confirme.

Pronto: aparece um ícone do jogo na tela inicial. Abre em **tela cheia**, sem a
barra do Safari, e o iOS guarda a página — não precisa digitar o endereço de novo.

## O que mudou por dentro

- A página que o servidor entrega já sai com:
  - `apple-touch-icon` (o ícone),
  - `apple-mobile-web-app-capable` (abrir sem a barra do Safari),
  - `apple-mobile-web-app-title` (o nome embaixo do ícone),
  - `manifest` (para navegador que usa isso),
  - `theme-color` (a cor da barra de status).
- O servidor passa a responder `/jarvis-icone-180.png`,
  `/jarvis-icone-512.png` e `/manifest.webmanifest` — **gerados em memória**.
- **O arquivo do seu export não é alterado.** As tags entram na resposta HTTP;
  o `index.html` no disco continua exatamente como o Unity/Godot gerou (tem
  teste comparando os bytes antes e depois).
- Se a página já vier preparada, as tags não entram duas vezes.

## O ícone teve um defeito — e o teste ficou

O primeiro PNG gerado saiu com **três linhas atravessando a imagem inteira**.
A causa: eu media a distância até a **reta** de cada aresta do triângulo, e o
prolongamento dessa reta pintava o fundo todo.

Corrigido para distância até o **segmento**, e entrou um teste de regressão que
conta os pixels fora da cor da marca e reprova o desenho defeituoso. (Foi
olhando o arquivo, não só rodando o teste, que o defeito apareceu.)

## O que continua sendo verdade

- **Nada é assinado pela Apple.** Este ícone não é um app `.ipa`: é o site com
  ícone e sem moldura. Não passa pela App Store e não tem custo.
- **TestFlight / App Store** seguem exigindo Mac + conta paga. Nenhum programa
  no Windows transforma um APK em `.ipa`.
- Se algum dia você quiser o app assinado, o projeto é o mesmo — muda só o
  build (Unity/Godot exportam para iOS) e a assinatura, que é da Apple.

## Como conferir se funcionou (do jeito barato)

1. Atualize (`atualizar.bat`) e arraste a pasta do export no
   `testar-no-iphone.bat`.
2. No iPhone, abra o endereço no Safari.
3. Compartilhar → **Adicionar à Tela de Início**.
4. O ícone do jogo (triângulo verde-água em fundo azul) tem de aparecer na tela
   inicial; abrindo por ele, o jogo roda **sem a barra de endereço**.

Se o ícone aparecer em branco ou for uma miniatura da página, me diga: significa
que a tag do ícone não chegou, e a janela do `.bat` mostra os pedidos — nesse
caso o `GET /jarvis-icone-180.png` vai estar com código diferente de `200`.

## Para quem for mexer no código

- `server/jogo_web.py`: `icone_png()` (PNG escrito à mão: IHDR/IDAT/IEND),
  `manifest()`, `_injetar_pwa()` e a rota virtual no handler.
- `testar-no-iphone.py` / `.bat`: o texto agora ensina a tela de início.
- `server/tests/test_jogo_web.py`: **41 testes** (10 novos desta versão).
- `docs/JOGO-NO-IPHONE.md`: a tabela “o que dá e o que não dá”, com o custo de
  cada caminho.
