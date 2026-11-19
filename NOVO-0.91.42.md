# JARVIS 0.91.42 — a aba “Meu jogo”: é lá que se joga o APK

Sua observação, em 18/11:

> e eu perguntei pq o unico lugar do jarvis q achei para jogar e analisar o
> arquivo foi na aba reversa

Você estava certo, e a resposta era incômoda: **não existia aba**. O upload de
APK existia em dois lugares, e nenhum era o jogo:

- a **Reversa** aceita `.apk` como qualquer artefato — 25 MB de teto, sem
  manifesto, sem motor, sem “o que melhorar”;
- o `analisar-jogo.bat` fazia a análise certa, mas **fora da tela**.

Quem procura “onde eu jogo o apk” abre o menu, vê “Reversa” (que aceita `.apk`)
e para ali. O caminho existia; faltava um endereço.

## Onde fica agora

**Menu lateral → “Meu jogo”**, logo abaixo de Reversa. Endereço:
`http://127.0.0.1:8000/jogo`.

A tela tem uma **área de arrastar**:

> **Jogue o APK (ou os dois) nesta área**
> ou *escolha o arquivo* — aceita .apk, .aab, .apks, .xapk até 600 MB, vários de uma vez

Arrastou, ele:

1. envia o arquivo para `storage/user-files/jogos/<nome-do-jogo>/`;
2. grava `analise.txt` e `analise.json` **ao lado do APK**;
3. mostra a análise na hora, sem precisar de `.bat` nem de chat.

## O que aparece na tela

| bloco | o que mostra |
|---|---|
| métricas | tamanho descompactado, nº de arquivos, minSdk → targetSdk, assinatura |
| linha técnica | ABIs, DEX, quantidade de permissões |
| achados | cada um com severidade (CRÍTICO / ATENÇÃO / INFO), **O que é**, **Por que importa**, **Como melhorar** e **Onde** |
| maiores arquivos | os que pesam, com MB |
| pacotes guardados | uma linha por pasta: `teste-1/ — teste-1.apk · 8,4 MB (analisado)` |

Clicar num pacote da esquerda abre a análise dele. Se você mandar dois, os dois
ficam lá — cada um na pasta dele.

## A Reversa agora avisa

Quem chegar na Reversa procurando o jogo (foi o seu caso) lê no topo:

> **É o APK do seu jogo?** Use a aba **Meu jogo**: ela lê o manifesto, o motor,
> as ABIs e o tamanho, guarda cada pacote na própria pasta e diz o que melhorar.
> Aqui a Reversa é para qualquer artefato (até 25 MB); lá o limite é 600 MB.

## Um defeito que o `tsc` pegou

Ao montar a tela, o TypeScript reprovou **três campos** que o front declarava
errados desde a 0.91.38 — o tipo tinha sido escrito “a olho”:

| campo | o tipo dizia | o servidor manda |
|---|---|---|
| `maiores` | `{ nome, bytes }` | `{ nome, mb }` |
| `areas` | lista de `{ nome, bytes }` | objeto `área → bytes` |
| `permissoes` | lista de objetos | lista de strings |

Nenhum desses quebrava o chat (que só usa o `texto`), mas quebraria a tela.
Corrigidos, e agora há um teste que prende o formato para os dois lados não se
afastarem de novo.

## O defeito que só apareceu com a aba pronta

Montei a tela, subi o JARVIS e mandei um APK de 8 MB pela rota, do jeito que a
aba manda. Voltou **`413`** — e o mesmo com qualquer APK de verdade:

> a rota dizia aceitar **600 MB**, mas o **middleware de corpo** só liberava
> 26 MB para documentos e **2 MB para todo o resto**, e `/api/jogo/upload`
> caía nesse “resto”.

Era o pior tipo de defeito: o `.bat` funcionava (não passa por HTTP), o chat
funcionava (lê do disco), e **só a tela nova** quebrava — exatamente no
primeiro arquivo que você fosse arrastar. Corrigido: a rota do jogo agora tem
o teto dela no middleware, e um teste manda um APK de mais de 2 MB pela rota
para provar que chega inteiro.

## Como conferir se funcionou (do jeito barato)

1. Atualize (`atualizar.bat`) e abra o JARVIS.
2. **Menu → “Meu jogo”.**
3. Arraste um APK (ou os dois) na área tracejada.
4. Tem de aparecer a linha “1 APK guardado em `nome/`” e, logo abaixo, a
   análise — com o **nome do pacote** e o **motor** nas primeiras linhas.

Se a aba não aparecer no menu, o navegador está com a tela antiga em cache:
recarregue com **Ctrl+F5** (o `index.html` é servido com `no-cache`, mas o
navegador às vezes segura).

## O que continua igual

- O `analisar-jogo.bat` continua funcionando — os dois caminhos usam a mesma
  análise e a mesma pasta.
- O chat continua: `analisar jogo <pasta>/<arquivo>.apk`, `analisar os dois jogos`.
- Nada é descompactado, descompilado ou enviado para fora do seu PC.
- A Reversa continua para os outros artefatos (binário, APK alheio, EXE…) —
  agora com um aviso, não como única porta.

## Para quem for mexer no código

- `src/pages/JogoPage.tsx` — a aba: zona de arrastar, envio, lista de pastas e
  painel de análise.
- `src/jogo.css` — o estilo (usa as variáveis de `styles.css`).
- `src/lib/api.ts` — `uploadJogo()` e os tipos corrigidos do relatório.
- `src/App.tsx` (rota `/jogo`), `Sidebar.tsx` (menu), `Topbar.tsx` (título),
  `CommandPalette.tsx` (busca “meu jogo”).
- `src/pages/ReversePage.tsx` — o aviso que aponta para a aba.
- `server/tests/test_jogo.py` — o teste de contrato do relatório (**49 testes**).
