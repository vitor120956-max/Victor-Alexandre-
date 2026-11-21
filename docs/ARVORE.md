# A árvore da janela: ver os elementos sem tocar (0.82.0)

Etapa 1 do que o [`vercel-labs/agent-desktop`](ANALISE-AGENT-DESKTOP.md) propõe.
O `mesa.py` antigo só via **títulos** de janela e clicava por coordenada que você
ditava — sem saber se acertou. Aqui o JARVIS passa a **ler** o que a janela
publica sobre si mesma.

## O maestro: juntar os degraus num objetivo (0.91.0)

As etapas anteriores deram **olhos** (ler a árvore) e **mãos** (abrir, escrever,
conferir). Faltava a cabeça que decide a ordem — e ela chegou com uma escolha
deliberada: **não usar modelo**.

O motivo é o mesmo desta semana inteira. Um passo errado com confiança custa
mais que um passo a menos. Então o plano não é gerado, é **declarado**:

```python
Procedimento(
    id="consertar-erro",
    precisa=("erro",),
    grupos=(("conserta", "arruma", "diagnostic", "corrig"),),
    passos=(
        Passo(skill="conserto.diagnosticar", campos={"erro": "$erro"}),
        Passo(skill="conserto.dossie",       campos={"erro": "$erro"}),
        Passo(skill="conserto.propor",       campos={"erro": "$erro"}),
    ),
)
```

`precisa` são substrings que precisam aparecer todas; `grupos` são grupos em que
**pelo menos uma** de cada grupo precisa aparecer. É assim que "salva" e
"guarda" viram a mesma intenção sem uma lista de sinônimos solta: o
procedimento exige *um* verbo de pesquisa **e** *um* de gravação.

### Por que grupo, e não uma lista só

"procura passagens e salva no arquivo" só casaria com `("guard",)` se eu
tivesse escrito "salva" dentro da lista — e amanhã "anota" quebraria de novo. O
primeiro teste que escrevi falhou exatamente aqui. Grupo é a forma certa: cada
intenção é uma condição, e todas as condições precisam valer.

### O que o maestro **não** faz, e é de propósito

- não abre shell nem interpreta expressão livre (`$1.__class__` devolve vazio —
  e há teste para isso);
- não escolhe skill por modelo;
- não segue depois de um erro;
- não grava arquivo vazio quando a busca voltou sem nada.

### 0.91.1 — a sonda passou a ler o `.env`

Achado antes do primeiro teste no PC: o `arvore_sonda.py` roda solto no
terminal e **não** carregava o `.env` — só o `server/app.py` carregava. Com
`JARVIS_HOST_REDE=1` no arquivo, a fila parava no passo 1 dizendo "Rede
desligada". Medido no sandbox: antes, mensagem de configuração; depois, falha de
rede de verdade. O mesmo valia para `JARVIS_FILES_ROOT`, que decidiria em qual
pasta o maestro grava.


### 0.91.2 — passo que não leu nada não conta como feito

Olhando a execução de verdade (e não só o plano): `conserto.diagnosticar`
devolvia `{"lido": false, "motivo": "Não há erro no diário…"}` e o maestro
seguia para o dossiê e para a proposta, terminando com "todos os 3 passos
rodaram". Dossiê de erro que ninguém leu.

Agora o passo declara `exigir="lido"`, e o maestro confere **antes** de aceitar
o passo: se voltar falso, a fila para com `nao_confirmado` e a saída da skill no
motivo. Declarado, não adivinhado — skill sem campo de confirmação não tem
`exigir` e nada muda.

Junto: cada passo passou a mostrar `voltou: …` (antes só dizia "feito"), o plano
avisa `só vale se voltar lido=true`, e o `$erro` do conserto corta no
`Traceback` quando você cola o erro junto com a frase.


### 0.91.3 — a primeira execução no PC do dono

Medido no `D:\JARVIS`, em 0.91.2. Três defeitos, os três reais:

| o que apareceu | por que era defeito | correção |
|---|---|---|
| `fonte=colado` sem erro colado, `exceção: :` | o pedido inteiro ia como traceback; a skill dizia `lido: true` e o dossiê saía vazio | `erro_do_pedido` só devolve algo que **pareça** erro; senão vazio, e a skill cai no diário |
| `versão: 0.75.0` no dossiê | `conserto.VERSAO` era a versão em que o módulo nasceu | dossiê usa `atualizacao.VERSAO`; teste recusa o `0.75.0` |
| `3. conserto.propor — feito` sem propor | o provedor falhou dentro da skill, sem exceção | passo declara `exigir="proposto"` |

E a parada ganhou **dica declarada no passo**, para a resposta dizer o que fazer
e não só o que faltou:

```
Parei no passo 1 (conserto.diagnosticar): a skill rodou mas não concluiu (lido=false): …
O que fazer: o diário de erros não tinha nada e o pedido não trouxe erro. Cole o traceback junto com o pedido.
```


### 0.91.4 — traceback numa linha só

Achado ao preparar o comando de teste para o PC, antes de mandar. O
`diagnosticar` procurava o tipo da exceção com `^...$` em modo multilinha, então
um traceback colapsado numa linha (terminal estreito, chat, ou o maestro
montando o texto) não tinha `KeyError` no começo de linha: o dossiê saía com
`exceção: :` e causa `desconhecida`.

Agora, se o começo de linha não achar, a busca fica com a **última** ocorrência
em qualquer posição — num traceback, a exceção é a última coisa escrita. Dois
testes fixam: linha única acha e classifica, várias linhas continua igual.


### 0.91.5 — o dossiê inteiro e a falha da IA com causa

Duas coisas que só aparecem quando a máquina funciona: na primeira execução em
que o diagnóstico **achou** o erro (`IndexError`, `server/app.py` linha 318), o
dossiê saiu cortado em 160 caracteres e a falha do passo 3 saiu como
`AIUnavailable` — o nome da exceção, não a explicação.

- `Passo.mostrar_texto`: o terminal imprime o documento inteiro entre
  marcadores; a API continua resumida. Só o passo que produz documento abre.
- `conserto.propor` passou a usar o `str()` do erro: `AIUnavailable` existe para
  poder ser mostrada sem segredo, e diz se a chave foi recusada, se está no
  limite ou se é rede.


### 0.91.6 — o 400 do provedor

No PC: o dossiê saiu inteiro (missão cumprida) e o passo 3 parou com
`O provedor não respondeu (AIUnavailable): o provedor de IA respondeu com HTTP 400.`

400 não é chave (401) nem cota (429): é pedido recusado. E o motivo que o
provedor mandou estava sendo **descartado** — só dois formatos de corpo eram
lidos (`error.message` e `message`). Formato desconhecido virava mensagem vazia.

- `detalhe_do_corpo` passou a aceitar `detail` e `error` como texto, e a mostrar
  o corpo cru (limpo, cortado) quando nada casa.
- A frase do 400 diz o que fazer e aponta `conferir-ia.py`.
- `conferir-ia.py`: script novo que lista os modelos que **a chave vê**
  (`GET /models`, sem gastar geração) e diz se o nome configurado está lá.

Causa mais provável, e é de graça confirmar: nome de modelo de um provedor com
chave de outro — `llama-3.3-70b-versatile` (Groq) × `meta-llama/llama-3.3-70b-instruct`
(OpenRouter). A chave está boa; o nome é que não existe ali.


### 0.91.7 — a chave com Ctrl+V dentro

O `conferir-ia.py` respondeu antes de qualquer chamada de rede:
`chaves: 1 configurada(s) ['\x16…\x16']` — 4 caracteres, dois deles `\x16`.

`\x16` é o código de controle do **Ctrl+V**. No console do Windows 10
(10.0.14393) o Ctrl+V **não cola**: escreve o caractere. A chave foi gravada
com lixo nas pontas, o provedor respondeu 400, e a investigação ia para o
modelo — lugar errado.

- `sem_controle()` em `server/ai.py`, `server/chaves.py` e `configurar-chave.py`:
  caracteres de controle saem na leitura (preservando `\t\n\r` — tirar a
  quebra de linha cola linhas e a extração pega chave a mais).
- `chaves.suspeitas()`: diz, em português, que a chave não tem cara de chave e
  que o Ctrl+V foi o culpado; `estado()` devolve a lista.
- `conferir-ia.py` para **antes** da rede quando há suspeita.
- `configurar-chave.py` limpa ao digitar e avisa quando removeu algo.

Colar no console antigo: **botão direito do mouse**, não Ctrl+V.


### 0.91.8 — o script passa a dizer onde pegar a chave

Medido no PC: `configurar-chave.py` abria com `Provedor [OpenRouter]:` e nenhuma
palavra sobre onde criar a chave. Quem nunca fez isso fica parado no prompt —
foi exatamente a pergunta do dono. O endereço já estava no catálogo
(`provedores.onde`), só não era impresso.

- `guia_do_provedor()` + `mostrar_guia()`: endereço, passo a passo, aviso do
  botão direito (Ctrl+V não cola no console antigo) e o modelo sugerido.
- O endereço reaparece no prompt da chave, quando a tela já rolou.
- Provedor fora do catálogo não quebra: só não mostra endereço.


### 0.92.1 — “passar esses dois apps/jogo para o iPhone de graça”

> to testando e quero passar esses dois apps/jogo para o iphone de graca

Na tela **Meu jogo** havia dois APKs e nenhuma resposta. O documento
`docs/JOGO-NO-IPHONE.md` já explicava o caminho WebGL — mas explicava para
“um jogo qualquer”, e os dois pacotes do dono **não são jogos**: um é ReVanced
do YouTube (`com.google.android.youtube`) e o outro é microG
(`app.revanced.android.gms`). Mandar os dois “exportarem em WebGL” seria a
frase certa para o pacote errado.

Então o veredito passou a ser **por pacote**, em `jogo.caminho_para_iphone`:

- motor com export web (Unity, Godot, GameMaker, Construct, Cocos, Defold,
  LibGDX) → **sim, de graça**, com o passo a passo do menu daquele motor —
  e o aviso de que quem vai para o iPhone é o export, não o APK;
- Unreal → não: a Epic removeu o HTML5 na 4.24;
- Flutter/React Native → não a partir do APK: só o projeto gera build web;
- Cordova → o conteúdo já é página (`www/`), mas o JARVIS não extrai de APK;
- ReVanced/Vanced → **não existe no iOS**; a resposta entrega o que existe
  (app oficial grátis, bloqueador no Safari, TestFlight instável);
- microG → não há o que instalar no iPhone, e ele nem seria necessário;
- motor desconhecido → não promete: diz que seria chute.

O veredito sai em três lugares: `relatorio.iphone` (JSON), o texto do chat e um
cartão no topo da análise, com **passo a passo**, **custo** e **limite** — e
nunca promete `.ipa` grátis.

Faltava também o caminho de volta: o `.bat` funcionava, mas o dono estava na
tela. A área **Testar no iPhone** aceita o `.zip` da pasta do export, achata o
zip do Unity, cobra o `index.html` e mostra o endereço real do servidor do jogo
(`http://<ip>:8099/`, calculado pelo mesmo código do console).

O dono voltou com a condição que importa: *“não quero que mude nada do app, só
que dê para rodar no iPhone”*. Então o veredito do YouTube passou a trazer o
caminho mais próximo disso — e ele não é exportar nada: é **sideload de um
`.ipa` já pronto** (YTLite/uYou+) com AltStore/Sideloadly e Apple ID comum,
grátis por **7 dias** e renovado pelo PC, ou 1 ano com conta de
desenvolvedor. O relatório diz também o que o JARVIS **não** faz: instalar no
iPhone, gerar `.ipa` e assinar app.

**Defeito achado no caminho:** o texto do relatório de um app que não é jogo
terminava com “o que muda o jogo de verdade — equilíbrio, controles, ritmo”. A
frase é de outro relatório; agora o app tem a sua.

### 0.92.0 — o que era “não faz por decisão” passa a fazer

> adicione essas coisas arrume oq tiver q ser arrumado e adicione filosofia,
> psicólogo, psicologia, como responder uma mulher por msg/presencialmente como
> se comportar dicas e ideias como comecar uma conversa como ir levando a garota
> para q ela queira ou de vontade de ela sair cmg ou q se apaixone por quem eu sou

A 0.91.46 tinha listado doze módulos que liam, mediam ou planejavam e paravam
ali. O dono leu e pediu o efeito. O efeito entrou em duas camadas separadas de
propósito:

**`server/acoes.py`** — a mão. `smtplib` com TLS, REST do Google com token
OAuth, `webbrowser` para abrir aba, conversão por tabela fechada (pandoc,
LibreOffice, ImageMagick, ffmpeg), renderizador **próprio** de Mermaid
`flowchart`/`graph` (sem Puppeteer), Graphviz para DOT, `jadx`/`apktool` para
descompilar, `pytest`/`npm test` preso à pasta, a API do GitHub para PR
(blob → tree → commit → ref → PR, ou PATCH quando a branch já existe), vetores
por provedor ou hash local **declarado**, e o maestro executando plano com teto
de passos. Tudo com `JARVIS_ACOES=1` e confirmação em dois tempos: sem
`confirmed`, a resposta é o **plano**, nunca o efeito.

**`server/conversa.py`** — a parte humana. Oito escolas de filosofia com
pergunta, prática e limite; sete conceitos de psicologia com a base declarada e
o exagero popular ao lado; aberturas por contexto; princípios para a conversa
não morrer; o convite com saída fácil e o “não” tratado como resposta; a revisão
da mensagem (tamanho, perguntas, cobrança, pressão, elogio ao corpo antes da
hora); e a lista de recusas com motivo — neg, insistir depois do não, chantagem,
personagem falso, confundir, vigiar.

A parte do pedido que **não** se entrega é “fazer ela se apaixonar”. Isso não é
técnica honesta, é pressão com nome bonito — e está escrito em
`docs/CONVERSA.md`, na lista `RECUSADOS` e nos testes. Crise e violência são
interceptadas **antes** de qualquer conteúdo: 188 (CVV), 180 e 190.

Os dois defeitos que os testes pegaram antes de virarem rotina: `revisar()`
mandava texto vazio ao detector (violência no rascunho passava calada) e o
parser do Mermaid apagava o rótulo de um nó repetido (`B[Pedido]` na primeira
linha, `B` na segunda). Também caiu um `_NO_MM` que ninguém usava e uma chave
`idea_key` vazia.

No frontend, a aba **Guia de conversa** (`/guia`) junta as oito seções numa
página só, com o catálogo vindo do servidor — as recusas na tela são as mesmas
do código, não um texto de marketing.

### 0.91.46 — “e o que mais o JARVIS não faz?”

> e oq mais o jarvis atualmente ele nao faz?

Pergunta de inventário, não de recurso. A resposta fácil seria listar os
módulos “estáticos” do README — mas essa lista mistura três coisas que não se
misturam: o que **não tem como**, o que **não faz de propósito** e o que **não
faz por falta**. Quem lê “o navegador não abre aba” e “não roda no iPhone” na
mesma lista conclui que o projeto é menor do que é; quem lê “não faz OCR” (como
o README dizia) conclui que é maior do que é.

A lista foi para `docs/NAO-FAZ.md`, em três seções, com o caminho que existe em
cada caso. E — o ponto desta versão — **virou teste**: `test_nao_faz.py`
confere as lacunas (a rota de comparação de APKs continua ausente, `jogo.*` não
existe como skill, `celular.instalar` não existe), confere as decisões (IA sem
visão, sem streaming, host `127.0.0.1`) e confere o “já faz” (OCR de PDF, voz do
navegador, OBB, teto de 2 GB). Fechar uma lacuna quebra o teste de propósito.

O defeito que apareceu no caminho: o README dizia **“PDF não tem OCR”** e o
`server/ocr.py` existe, é usado por `biblioteca.py` e lê PDF escaneado com
Tesseract + `pypdfium2`. A frase estava errada desde que o OCR entrou, e
sobreviveu porque nada a cobrava. Agora o teste reprova se ela voltar.

### 0.91.45 — “pq o obb não é analisado? pode fazer o javis analisar pfv”

> pq o obb mao e analisado? pode fazer o javis analisar pfv

“O OBB não é analisado” estava escrito em três lugares (a tela, a recusa de
tamanho e `docs/ENGENHARIA-REVERSA.md`). Era verdade **pela metade** e servia
mal: o OBB é onde mora quase todo o peso de um jogo — texturas, áudio, vídeo —,
e quem acabou de gerar um build quer saber o que tem dentro dele.

A metade falsa é que o OBB não é um APK: não tem `AndroidManifest.xml`, não tem
DEX, não tem assinatura. As perguntas do APK não se respondem nele. Mas as
perguntas do **OBB** sim, e elas são as que quebram o jogo em silêncio:

1. **o nome** — o Android procura `main.<versionCode>.<pacote>.obb`. O OBB da
   versão 20 com o APK da 14 existe, está do lado do APK, e **não é usado**: o
   jogo procura `main.14.<pacote>.obb`, não acha, e abre sem os dados. Antes,
   ninguém via isso;
2. **o conteúdo**, quando ele abre como ZIP (o caso do OBB gerado pelo Unity):
   quantos arquivos, quanto pesa cada pasta e os dez maiores;
3. **o que não comprime à toa** — 30 MB de JSON/WAV guardados sem compressão
   só engordam o download;
4. **o que não dá para ler** — OBB cifrado com o `jobb` não expõe a lista sem a
   chave, e a resposta é “não dá para listar, e por quê”, nunca uma lista
   inventada.

## Medido no JARVIS de verdade (porta 8151)

| cenário | o que voltou |
|---|---|
| `main.14.com.exemplo.jogo.obb` com o APK v14 | ZIP, **8 arquivos**, **8,6 MB** descompactado, entropia 3,08, maiores arquivos listados, conferência `igual / igual` |
| `main.20...obb` na mesma pasta do APK v14 | **CRÍTICO** “O número do OBB não bate com a versão do APK” — e a frase ensina: *renomeie para `main.14.com.exemplo.jogo.obb`* |
| OBB enviado **antes** do APK | pasta `jogos/com-exemplo-jogo/`, e o APK que chega depois **entra nela** (uma pasta, o par junto) |
| OBB sozinho (sem APK) | relatório `somenteObb: true`, com o bloco do OBB e a saída “envie o APK para eu conferir pacote e versão” |

## O que mudou no código

- `server/obb.py` (novo): `do_nome()` lê `main|patch.<versionCode>.<pacote>.obb`;
  `analisar()` abre como ZIP (só o diretório central), calcula áreas, maiores,
  entropia por amostra (2 MB) e produz achados com o formato do resto do
  projeto; `conferir()` compara com o APK e transforma a divergência em achado.
- `server/jogo.py`: `EXTENSOES_ACEITAS` (APK + `.obb`), `parte_do_obb()` (o OBB
  entra na pasta do APK do mesmo pacote), `parte_do_obb_orfao()` (o APK entra na
  pasta do OBB quando ele chegou primeiro), `relatar_parte()`, `relatar_obb()`,
  `texto_obb()` e o bloco do OBB no texto do APK. Pacote que traz OBB dentro
  (XAPK) ganha achado apontando o envio separado.
- `server/app.py`: a rota de upload aceita `.obb` e decide a pasta pelo pacote;
  antes de transmitir, lê o manifesto do próprio upload para saber se há uma
  pasta de OBB esperando o APK.
- `src/lib/api.ts` + `src/pages/JogoPage.tsx`: o OBB aparece na lista da pasta,
  tem bloco próprio no painel (formato, arquivos, tamanho aberto, selo de
  conferência, achados e maiores arquivos) e a área de arrastar aceita `.obb`.
- `analisar-jogo.py`: listar uma pasta só com OBB estourava `apks[0]` — o `.bat`
  morria antes de mostrar qualquer coisa.

## O que continua verdade

O OBB **cifrado** (por exemplo, gerado com `jobb -k`) não é decifrado: o
relatório diz que não consegue listar e mostra o que consegue (nome, tamanho,
entropia, conferência). Nada é extraído em disco: o ZIP é lido pelo diretório
central, como no resto do projeto.

E o limite do Play não muda por causa disso: são **100 MB de APK + OBB de até
2 GB** (um `main` e um `patch`) no formato antigo, ou AAB com Play Asset
Delivery, com 1,5 GB por asset pack. O JARVIS lê o pacote; publicar é outra
conversa, e o texto diz qual é.

### 0.91.44 — “e se o meu app ou jogo tiver 1 GB ou 500 MB?”

> ta mas e se o meu app ou jogo tiver 1gb ou 500 mb?

A pergunta veio logo depois de a Reversa explicar que o APK grande pertence à
aba “Meu jogo”. Faltava o outro lado da frase: a aba dizia aceitar **600 MB**,
e o dono tem jogo que pode passar de 1 GB. “Aceita até 600 MB” é uma resposta
para um problema que ninguém tem — jogo grande é o normal.

Medido antes de mexer:

| arquivo | teto de 600 MB | teto de 2 GB |
|---|---|---|
| 500 MB (524 MB de APK) | 200 em **3,1 s** | 200 |
| 1 GB (1.101 MB de APK) | **413** “O APK passa de 600 MB” | 200 em **6,8 s**, análise gravada em `jogos/<parte>/` |
| 2,1 GB | 413 | 413 em **8 ms**, zero bytes enviados |

O envio já era em pedaços de 1 MB desde a 0.91.38: o pico de memória do
servidor foi de **83,8 MB para 89,7 MB** num envio de 1 GB. Não era a
transmissão que impedia — era o número, e o disco.

O que mudou:

- `MAXIMO_BYTES` de 600 MB para **2 GB**; a tela anuncia o mesmo valor
  (`LIMITE_TEXTO`) e os dois são presos pelo mesmo teste.
- `MARGEM_DISCO` (500 MB) e `espaco_livre()`: a conta é feita **antes** de
  escrever o primeiro byte e repetida a cada 64 MB — durante o envio o arquivo
  existe duas vezes (temporário do pedido + pasta do jogo). Sem espaço, `507`
  com “o disco tem X livres, preciso de mais 500 MB de folga. Nada foi
  guardado”. Antes, o disco enchia e sobrava erro de sistema em inglês e pasta
  pela metade.
- `rotulo_bytes()`: 2 GB, 600 MB, 1,1 GB — o número que a pessoa lê é o mesmo
  que o servidor cobra.
- Acima de 2 GB, a recusa manda dividir em **main + patch** (até 2 GB cada) ou
  usar **Play Asset Delivery** com o AAB. (Na 0.91.45 o OBB passou a ser
  analisado, então “sem o OBB” deixou de ser conselho.)

O que a medição **não** muda: o Android só instala APK até um certo tamanho e a
Play trabalha com **APK de 100 MB + OBB de até 2 GB cada** (ou AAB com Play
Asset Delivery). Ou seja: 1 GB serve para testar no aparelho; para publicar, o
caminho é dividir o pacote.

### 0.91.43 — “e o engenharia reversa ta funcionando?”

> e o engenharia reversa ta funcionando?

“Deve estar” não é resposta. Então a pergunta virou medição: subi o JARVIS,
mandei quatro arquivos de verdade para a área reversa e apertei os cinco
botões. Nada de opinião sobre o código — o que a tela devolveu:

| botão | arquivo | o que voltou |
|---|---|---|
| Inspecionar | APK de teste | “ZIP / arquivo compactado”, entropia **7,2747**, 4 entradas, 46 strings |
| Layout | APK de teste | as 4 entradas do ZIP, com tamanho comprimido e CRC |
| Strings | APK de teste | achou `lib/arm64-v8a/libunity.so` e `classes.dex` — os dois nomes que identificam o pacote |
| Entropia | APK de teste | 7,2747 no arquivo; blocos sem região cifrada |
| JavaScript | `app.js` com `ipcRenderer` | 1 módulo, fato `electron.ipc-renderer` na **linha 2** |

Para não testar só ZIP: um ELF de verdade (`/bin/ls`) voltou “ELF64
little-endian”, **31 seções** e 2 imports; um PNG voltou com entropia
**7,7625**. Em todas as respostas, `executed: false` e `readOnly: true` — a
Reversa lê, não roda. E `server/tests/test_reverse.py`: 15 testes passando
(agora 16).

Então: **funciona**. O que não funcionava era o que ela fazia quando
**recusava** — e recusar calado é pior que recusar, porque parece que o botão
não respondeu.

Dois defeitos, os dois do tipo que só aparece usando:

1. **APK acima de 25 MB.** Escolher o arquivo no seletor não fazia nada. Nem
   erro, nem “grande demais”, nem envio. O `input` voltava vazio e a tela
   ficava igual. Quem arrastou um APK de verdade (todo APK de jogo passa de
   25 MB) conclui que a Reversa está quebrada — e não está: o teto é 25 MB, e
   o APK do jogo tem a aba “Meu jogo”, com 600 MB.
2. **Pasta com arquivo descartado.** Arrastar uma pasta filtrava o que não
   cabia e ainda anunciava “pasta enviada”, com a contagem dos que sobraram.
   O arquivo grande sumia sem nome e sem motivo.

A correção saiu do componente e virou uma função pura,
`src/lib/artefatos.ts`: `classificarArquivos()` devolve `aceitos`,
`recusados[{nome, motivo, bytes}]` (motivo `grande`, `formato`, `oculto` ou
`vazio`), `totalBytes`, `excedeTotal` e `excedeQuantidade`;
`explicarRecusa()` transforma o motivo em frase — e, no caso do APK grande,
manda para a aba certa com o teto de lá. `resumoDaTriagem()` cita até três
recusados e conta o resto. A tela passou a usar isso nos dois caminhos (o
seletor de arquivo e o arrastar de pasta), e o aviso de sucesso agora fala
**só** dos aceitos. São 14 testes em `artefatos.test.ts`, um por jeito de
sumir calado.

Terceiro ajuste, menor e da mesma família: quem chama a API direto recebia
`413` com a frase “A requisição excede o limite de tamanho.” — sem número e
sem saída. Agora a resposta diz o teto (25 MB), para onde ir (aba “Meu jogo”,
600 MB) e devolve `limitBytes`; o teto de 600 MB do jogo tem a mesma frase, e
as duas estão presas por teste (`test_reverse.py` e `test_jogo.py`).

**O que continua feio, e fica escrito:** mandar 26 MB pela API, no fio, ainda
termina em conexão cortada antes do JSON chegar — o servidor recusa pelo
`content-length` e fecha sem ler o corpo, e o cliente que está escrevendo
recebe *reset*. Pela tela isso não acontece (a triagem barra antes de enviar),
e drenar 26 MB só para recusar seria pior que o sintoma. É limitação
registrada, não promessa de conserto.

### 0.91.42 — “em qual aba ta? e onde eu jogo o apk”

> e eu perguntei pq o unico lugar do jarvis q achei para jogar e analisar o
> arquivo foi na aba reversa

Ele estava certo, e a resposta era incômoda: **não havia aba**. O upload de
APK existia em dois lugares e nenhum era o jogo:

- a **Reversa** aceitava `.apk` como artefato genérico — 25 MB de teto, sem
  manifesto, sem motor, sem “o que melhorar”;
- o `analisar-jogo.bat` fazia a análise certa, **fora da tela**.

Quem procura “onde eu jogo o apk” abre o menu, vê “Reversa” (que aceita
`.apk`) e para ali. O caminho existia, mas não tinha endereço.

| antes | agora |
|---|---|
| só Reversa, 25 MB, sem análise de jogo | aba **Meu jogo**, 600 MB, com a análise inteira |
| arrastar o APK no `.bat` (fora da tela) | arrastar o APK **na aba**, que envia para `jogos/<parte>/` e já analisa |
| relatório só no console | cartões de métrica + achados com severidade, na tela |
| dois APKs soltos na mesma pasta | cada um na pasta dele, com `analise.txt` e `analise.json` ao lado |

Três decisões que valem registro:

1. **A aba fica ao lado da Reversa, no menu.** É o vizinho que o dono já
   conhecia; esconder em “Configurações” ou só no chat repetiria o erro.
2. **A Reversa aponta para lá.** Quem chegar primeiro na Reversa (como ele
   chegou) lê, no topo, que o APK do jogo tem aba própria — e o porquê: 600 MB
   contra 25 MB, e a análise de pacote que a Reversa não faz.
3. **O contrato do relatório virou teste.** O `tsc` reprovou três campos que o
   front declarava errados (`maiores.mb`, `areas` como objeto, `permissoes` como
   string). O teste prende o formato para os dois lados não se afastarem.

### 0.91.41 — dois APKs: separar, analisar e guardar cada um na sua pasta

> ta vou testar com dois apks meus
> nn sao diferentes mas quero usar os dois para teste

Dois pacotes do mesmo jogo, para testar. O que não podia acontecer era o que
estava acontecendo em dois lugares:

1. **o `.bat` entregava só o primeiro.** A chamada era `analisar-jogo.py "%~1"`,
   e o segundo APK era ignorado **em silêncio** — o dono arrastava dois e
   achava que tinha analisado os dois;
2. **os dois caíam soltos na mesma pasta**, e as análises não tinham dono. Com
   dois builds do mesmo jogo, não dava para saber qual relatório era de qual.

Agora cada pacote tem a pasta dele:

    storage/user-files/jogos/
      teste-1/
        teste-1.apk
        analise.txt
        analise.json
      teste-2/
        teste-2.apk
        analise.txt
        analise.json

Três decisões que valem registro:

1. **A análise fica ao lado do APK.** `analise.txt` é o que se lê; `analise.json`
   é o mesmo relatório para a tela. Quem abre a pasta meses depois sabe de qual
   build é aquele texto sem procurar em outro lugar.
2. **Nada se mistura nem se sobrescreve.** O mesmo arquivo arrastado de novo
   reaproveita a pasta (`novo=False`); dois arquivos de mesmo nome viram `jogo/`
   e `jogo-1/`. Nome igual em duas pastas, o chat **pede qual** em vez de
   escolher calado.
3. **O formato antigo continua valendo.** APK solto na raiz de `jogos/`
   (0.91.38–0.91.40) é listado e analisado como antes — atualizar não quebra o
   que já estava guardado.

O `.bat` passou a chamar `%*` (todos os arquivos arrastados), e o `--lista`
mostra `teste-1/ — teste-1.apk — 8,4 MB (analisado)`. A comparação entre dois
pacotes continua existindo (`--comparar`), mas como ferramenta opcional: o dono
disse que os dois são para teste, não antes/depois.

### 0.91.40 — “não dá para baixar no iPhone?”

> entao so da para rodar via web?? nao da para baixar no iphone?

A pergunta tem duas respostas, e misturá-las é o que faz o dono perder tempo:

| o que ele quis dizer | resposta |
|---|---|
| ícone na tela de início, abre em tela cheia | **sim, de graça** — e é o que esta versão faz |
| app `.ipa` instalado | só com conta Apple Developer (US$ 99/ano) + Mac |
| APK instalado | não existe no iOS |

A 0.91.39 servia o export, mas o Safari mostrava a barra de endereço e um
favicon qualquer. Agora a página servida sai com `apple-touch-icon`,
`apple-mobile-web-app-capable` e `manifest`, e o ícone (180 e 512) é
**desenhado no próprio servidor** — sem Pillow, sem arquivo extra no export.

Três decisões que valem registro:

1. **O arquivo do export não é tocado.** As tags entram na resposta HTTP; o
   `index.html` no disco continua igual ao que o motor gerou. Teste compara os
   bytes antes e depois.
2. **A injeção é idempotente.** A marca `data-jarvis-pwa` impede que uma
   página já preparada ganhe as tags duas vezes (e o `count` está no teste).
3. **O ícone foi olhado, não só testado.** O primeiro PNG saiu com três linhas
   atravessando o fundo: a distância era à **reta** da aresta, e o
   prolongamento dela pintava o ícone inteiro. Virou teste de regressão que
   conta pixels fora da marca.

### 0.91.39 — “testar no meu iPhone”: o APK não roda lá

> ta bom e dps q esse apk estiver bom eu quero testar no meu iphone

A resposta fácil seria “sim” e um tutorial de instalar APK no iPhone — que não
existe. O iOS só executa aplicativo assinado pela Apple; nenhum programa
instala um `.apk` num iPhone.

O caminho de graça é outro, e é o mesmo jogo: **exportar em WebGL/HTML5** e
abrir no Safari. Quem faz o export é o motor; o JARVIS faz o que faltava —
transformar a pasta do export em um endereço que o iPhone abre.

| antes | agora |
|---|---|
| “testar no iphone” caía no modelo, que inventava um passo | `jogo_web.py` serve o export no Wi-Fi, e o chat diz o fato primeiro |
| servir um export da Unity “na mão” dá tela preta | `.gz` sai com `Content-Encoding` (sem isso o Safari recebe lixo) |
| zip do Unity vem com pasta dentro | `index.html` é procurado e a pasta é achatada |
| abrir o JARVIS para o iPhone seria abrir a API | servidor separado, outra porta, só arquivos do export |

Três decisões que valem registro:

1. **O fato vem antes do passo.** A primeira linha da resposta é “APK não roda
   em iPhone”, não uma lista de cliques que termina em frustração.
2. **O servidor do jogo não é o JARVIS.** Outro processo, outra porta, nenhuma
   rota da API. `/api/health`, chaves e `.env` dão `404` ali — e há teste
   pedindo cada um deles.
3. **O diagnóstico é a própria janela.** Cada arquivo que o iPhone pede aparece
   com o código; nenhum pedido quer dizer “não chegou no PC” (rede, firewall,
   Wi-Fi de visitante) — não “o jogo está quebrado”.

Limites declarados: sem Mac, sem conta Apple e sem HTTPS, o que não roda é
`SharedArrayBuffer` (export com threads); a App Store continua exigindo Mac +
US$ 99/ano, e isso está escrito em `docs/JOGO-NO-IPHONE.md`.

### 0.91.38 — o APK do jogo: analisar o pacote, não opinar sobre ele

> eu to criando um jogo q ele e apk quero q o jarvis possa analisar meu jogo e
> melhorar ele

“Melhorar o jogo” é pedido grande, e a tentação é responder com conselho de
game design que ninguém mediu. O que dá para fazer sem inventar é ler o
**pacote** e dizer, com base no que está dentro dele, o que está errado e onde
se conserta: manifesto, motor, ABIs, tamanho, assinatura, permissões.

| antes | agora |
|---|---|
| “analisar meu jogo” caía no modelo, que não vê o APK | `server/jogo.py` lê o pacote e devolve achados |
| motor do jogo: adivinhação pela conversa | marca **real** no ZIP: `libunity.so`, `libgodot*.so`, `libUE4.so`, `*.pck`, `assets/bin/Data`… |
| “está grande” sem número | tamanho descompactado, por área (`assets/`, `lib/`, `res/`, dex) e os 10 maiores arquivos |
| conselho genérico | cada achado diz **o que é**, **por que importa**, **como melhorar** e **onde** (motor, build) |

Três decisões que valem registro:

1. **Nada é descompactado no disco.** O APK é lido por dentro do ZIP, em
   memória: 600 MB de teto, 60 mil entradas, manifesto até 4 MB. Análise local,
   sem enviar o arquivo para lugar nenhum — e isso está escrito no relatório.
2. **`classes.dex` não é marca de motor.** A primeira versão reconhecia LibGDX
   por ele; o teste mostrou que **todo** APK tem `classes.dex`, então todo jogo
   virava LibGDX. Marca genérica não identifica nada, e o teste que reprovou
   isso ficou no arquivo.
3. **O manifesto binário é lido de verdade.** Sem `aapt2`, sem Android SDK: o
   AXML é interpretado com `struct` (pool UTF-16, resource map, start
   elements). O molde do teste é montado byte a byte, e o teste exige que a
   string esteja **em UTF-16** — procurar ASCII nos bytes não acharia nada.

O caminho do dono é arrastar o APK no `analisar-jogo.bat`: ele copia para
`storage/user-files/jogos`, sem sobrescrever, e imprime o relatório. Depois,
“analisar jogo <nome>.apk” no chat responde o mesmo texto com o selo
`· ANÁLISE DO JOGO (PC)`.

Limite declarado: **este módulo não mede quadros por segundo nem diversão.**
Ele lê o pacote; diz o que o pacote mostra e o que fazer a respeito.

### 0.91.37 — “que dia é hoje” funcionava; o resto ia para o modelo

A pergunta, logo depois da previsão do tempo:

> e se eu perguntar para o javis q dia e hj proximos feriados quantos dias
> faltam para final de semana hj e quarta quinta...?

Medido no parser: **só** “que dia é hoje” era local. “Quantos dias faltam para o
fim de semana”, “hoje é quinta?” e “próximos feriados” caíam em `unknown` e iam
para o modelo — que não tem relógio. O dia da semana ele pode acertar de
memória; o **Carnaval** ele chuta com a mesma confiança com que acerta o Natal.

| pergunta | antes | agora |
|---|---|---|
| que dia é hoje | local (só a data) | local: data, dia da semana e quanto falta para o sábado |
| quantos dias faltam para o fim de semana | modelo | conta local (`Faltam 3 dias para o sábado (21/11/2026)`) |
| hoje é quinta? | modelo | conta local: confirma ou corrige (“quinta-feira é amanhã”) |
| próximos feriados | modelo | `server/calendario.py`: fixos por lei + móveis pela **Páscoa** |
| quanto falta para o Natal | modelo | o próximo Natal de verdade, com a contagem em dias |

Duas decisões que valem registro:

1. **A Páscoa é calculada, não tabelada.** Meeus/Jones/Butcher, o mesmo
   algoritmo da Igreja e do Excel. Dez anos conferidos no teste (2020–2038).
   Tabela de feriado móvel envelhece; conta, não.
2. **Ponto facultativo é dito como tal.** Carnaval e Corpus Christi não são
   feriado nacional por lei. Chamá-los de feriado seria a mesma classe de erro
   de inventar uma temperatura: parece certo e não é.

O dia da semana e a contagem até o sábado ficam no **front** (`src/lib/
calendario.ts`): não dependem de lei, funcionam com a API fora do ar e respondem
na hora. Os feriados ficam no **servidor**, que é onde a lei muda. Sem a API, o
chat ainda responde o dia de hoje e diz o que falta subir.

### 0.91.36 — “vai chover hoje?” era pergunta para o modelo

Depois de a IA provar que respondeu — *“A IA externa respondeu em 2832 ms
(provedor OpenRouter)”* —, a pergunta seguinte do dono foi sobre o que ele ainda
não tinha:

> deu isso e se eu perguntar como esta a previsao de tempo hj ou se vai chover hj?

A resposta honesta, olhando o código: **ia para o modelo**. E o modelo não vê o
tempo — não tem janela, nem relógio, nem previsão. Ou diz *“não tenho acesso a
dados em tempo real”*, ou **inventa** uma temperatura plausível. Numa tela que
acabou de mostrar `· IA EXTERNA`, as duas respostas parecem igualmente
confiáveis. É o mesmo defeito de “prova”, uma camada abaixo.

Agora a frase vira consulta ao **Open-Meteo** — serviço público, sem chave, sem
cota, dois endereços fixos:

| antes | agora |
|---|---|
| o modelo chutava (ou se esquivava) | `tempo.previsao()`: cidade → coordenadas → agora, hoje e amanhã |
| nada dizia a origem | a resposta termina com *“Fonte: Open-Meteo … quem respondeu foi o serviço de previsão, não o modelo”* e a hora da leitura |
| “vai chover?” era texto solto | **número**: `sim, deve chover — 80% de chance` / `não deve chover — 5%` / `talvez` entre 25% e 49% |
| sem cidade, ficava sem resposta | `JARVIS_CIDADE` no `.env`; vazio, Palhoça |
| rede fora virava silêncio | “não consegui falar com o serviço de previsão … e eu não vou inventar uma” |

O parser ganhou as frases comuns (“vai chover”, “previsão do tempo”, “que tempo
faz”, “guarda-chuva”, “temperatura agora”), com dois cuidados: “de hoje” e
“guarda-chuva” **não** viram cidade, e quem escreve “pesquise a previsão do
tempo” continua indo para a busca na web — a pessoa quer a página, não o número.

E o modelo recebeu uma instrução nova: não estimar tempo, cotação nem placar. O
que escapar do parser ganha um “não tenho esse dado”, não um número falso.

### 0.91.35 — o teste disse “OK” para um modelo que não fala

O console do dono, logo depois do `atualizar.bat` da 0.91.34:

    TESTE DE VERDADE (8 tokens por chave)...
    OK   chave 1: HTTP 200
         motivo: respondeu com raciocínio em vez de texto
         o provedor disse: “o modelo pode gastar o limite pensando e não sobrar resposta”

    Pronto: provedor, modelo e chave estão coerentes.

Três linhas que se contradizem, e todas na mesma tela. A 0.91.33 já tinha
ensinado `_testar_uma_detalhado` a marcar `sem_texto` e `testar_modelo` a
recusar — mas o `chaves.testar()`, que é quem responde ao `--testar` e ao botão
“testar” da tela, continuou aprovando pelo **código HTTP**. O modelo escolhido
na véspera era de raciocínio: gasta os 8 tokens pensando e devolve `content`
vazio. O teste viu 200 e disse “OK”.

E o conserto prometido não consertava: `--corrigir` só agia quando o nome
**não estava** na lista. Com o nome na lista (o caso do mudo), ele não
perguntava nada ao modelo e respondia “estão coerentes” — a mesma frase errada,
agora numa execução que parecia um conserto.

| antes | agora |
|---|---|
| 200 aprova, mesmo sem uma palavra | `ok` exige **texto**; 200 mudo é “a chave vale, o modelo não fala” |
| resumo: “A chave respondeu. O cérebro está de pé.” | “A chave está válida: o modelo respondeu HTTP 200 e não mandou texto… — `conferir-ia.py --corrigir`” |
| modelo de **socorro** com 200 mudo “provava” a chave | o socorro também precisa falar |
| `--corrigir` com o nome na lista: nada testado, “coerentes” | `--corrigir` testa o modelo na hora e, se ele não fala, troca |
| 3 candidatos testados | **6** (no console do dono os 3 primeiros eram dois 429 e o mudo) |
| `.env` trocado e a API em memória com o antigo, sem aviso | “feche a janela da API no X e rode iniciar-jarvis.bat” |

O `--corrigir` também passou a dizer o que aconteceu com cada candidato:
*“respondeu, mas sem texto (gastou o limite pensando) — pulando”* é diferente de
*“não (HTTP 429)”*.

### 0.91.34 — “funcionou?” era a pergunta errada para a tela certa

Em 17/11 o dono abriu o JARVIS em `127.0.0.1:8000`, mandou “oi”, recebeu
*“Olá, Victor. Estou por aqui. Você pode me pedir uma tarefa…”* e perguntou:
**“funcionou?”**.

Não tinha funcionado nada. Aquela frase é a skill local `case 'greeting'` do
`AppContext`: texto fixo, sem chave, sem rede, sem modelo. O “oi” não gastou
cota nenhuma. A tela é que não sabia dizer de onde a resposta veio — e por isso
a primeira prova depois de doze versões de trabalho com chave não provava nada.

Três mudanças, todas de texto, porque o defeito era de texto:

| antes | agora |
|---|---|
| a saudação soava igual ao modelo | a saudação termina “(Essa resposta é local, sem IA… diga “testar ia”.)” |
| não havia prova nenhuma na tela | `testar ia` (e “conferir a ia”, “a ia está funcionando?”, “status da ia”) pede ao modelo `Responda apenas: ok`, **cronometra** e imprime “A IA externa respondeu em N ms (provedor X)” |
| falha virava silêncio | “A IA externa NÃO respondeu: …” + o comando que conserta (`conferir-ia.py --corrigir`); sem backend ou sem chave ele diz isso em vez de fingir |

A resposta do teste sai marcada `· IA EXTERNA` no balão — a mesma marca que só
aparece quando o texto veio de fora, pelo `/api/ai/chat`. E o parser ganhou 13
formas de pedir o teste sem roubar os vizinhos (“status do sistema”, “testar
python”, “testar conexão” continuam indo para onde iam).

“oi” continua respondendo na hora, sem gastar cota, de propósito: mandar toda
saudação ao modelo é pagar por uma frase que o programa já sabe. O que muda é
que agora a resposta **avisa** que é local e ensina o comando que mede o resto.

### 0.91.33 — “respondeu” só vale se veio texto

O console de 17/11 terminou com uma escolha: os dois `gemma` deram **429** e o
terceiro candidato — `nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free` —
“respondeu”. Respondeu **HTTP 200**, e o teste de 8 tokens aprovou.

O problema é o tipo de modelo. Nome com `reasoning` pensa antes de falar, e o
pensamento ocupa o mesmo limite de tokens. Com o JARVIS pedindo 800 tokens, o
raciocínio pode consumir tudo: volta `finish_reason: length` e `content` vazio.
O usuário abre o JARVIS e recebe *“O provedor retornou uma resposta vazia”* —
longe da causa, de novo.

| antes | agora |
|---|---|
| 200 = aprovado | **200 só aprova com texto** (`choices[0].message.content`); vazio vira “respondeu HTTP 200 sem nenhum texto” e o próximo candidato é testado |
| resposta cortada = “vazia” | `finish_reason: length` → **um** segundo pedido com até 3× o espaço (teto de 4.096) |
| vazio e sem espaço → erro | se veio `reasoning`, é ele que aparece — melhor que “resposta vazia” |
| escolha podia cair em modelo de raciocínio | `escolha_modelo` põe `reasoning`/`thinking` **depois** dos de conversa da mesma faixa; e o `--corrigir` avisa “é um modelo de raciocínio: pode demorar” |

E o `--corrigir` passou a contar os 429: eles não são defeito do modelo, são
limite de pedidos da conta gratuita — e agora a tela diz isso.

### 0.91.32 — duas telas que não diziam o que a pessoa precisava saber

Dois consertos pequenos, os dois nascidos de uma pergunta que o dono fez no
console e que a tela não respondia:

**1. “Tem versão nova?” sem data.** O `atualizar.bat` dizia
`Versão nova: 0.91.29 (a sua é 0.91.28)`. Número não é data: não dava para saber
se aquela resposta era de hoje ou de três dias atrás — e o dono atualizou sem
saber se havia algo mais no ar. O manifesto já trazia `gerado`; agora ele sai na
frase (`publicada em 17/11 09:12 UTC`) e o `verificar()` devolve o campo
`publicado`.

**2. `--corrigir` numa cópia que não o conhece.** O comando foi rodado numa
instalação **0.91.29**, publicada antes de a opção existir, e a resposta foi
`conferir-ia.py: error: unrecognized arguments: --corrigi`. Isso é erro de
ferramenta falando com quem não programa. Agora o script usa
`parse_known_args`, e o que sobrar vira:

    Esta cópia do JARVIS não conhece: --corrigir
    Ela é a 0.91.29 — a opção pode ser de uma versão mais nova.
    Rode o atualizar.bat (ele baixa só o que mudou) e tente de novo.

De quebra, o cabeçalho passou a mostrar a versão (`JARVIS — conferir a IA
(0.91.32)`) e o `--corrigir` passou a consertar também o caso em que o **nome
está na lista mas dá 404** — a lista do provedor demora a tirar o morto, e o
teste de verdade é que prova.

### 0.91.31 — o modelo do `.env` tinha morrido, e o conselho era pior que o erro

O console de 17/11 mostrou a chave funcionando (73 caracteres, gravada) e, três
linhas depois, o problema seguinte:

    modelo: deepseek/deepseek-chat-v3-0324:free
    NÃO  o modelo … NÃO está na lista.
    Use um destes:  deepseek/deepseek-chat-v3-0324 · …-v3.1 · …/deepseek-chat

Os três “use um destes” são **pagos**. Numa conta gratuita, trocar para qualquer
um deles só muda o erro de lugar: sai o 404 e entra o 402. O `difflib` estava
fazendo o que sabia — escolher o nome mais parecido — e o mais parecido era o
vizinho pago.

| antes | agora |
|---|---|
| `difflib` sugere o mais parecido | `server/escolha_modelo.py`: **grátis primeiro**, ferramenta fora (embedding, áudio, imagem), 8b+ na frente de 1.7b, família conhecida, empate por nome |
| o conselho era trocar à mão e rezar | `conferir-ia.py --corrigir`: escolhe, **testa com 8 tokens de verdade** e só então grava |
| gravaria por cima sem cópia | **backup** do `.env` antes (`env.antes-AAAAMMDD-HHMMSS`) |
| nenhum candidato responde → ??? | nada é gravado e a frase diz o que fazer |

A decisão que mais importa: **escolher não é provar**. A lista do provedor diz o
que existe, não o que responde — e um nome recém-morto pode continuar na lista
por um tempo. Por isso o primeiro candidato que responde 200 é o que entra; os
outros dois ficam de reserva.

O `chave-pela-api.bat` passou a terminar com esse comando: criar a chave e
acertar o modelo viraram a mesma ação.

### 0.91.29 — o caminho em que não há página para carregar

O dono perguntou o que qualquer pessoa perguntaria: “esse Chrome é muito lento,
não tem outro jeito?”. Tem. O problema nunca foi o Chrome — foi **precisar de
uma página** para criar uma chave.

O OpenRouter tem a **chave de gestão** (management / provisioning): uma chave
que não conversa com modelo, só cria outras, pelo `POST /api/v1/keys`. Com ela,
criar a chave do JARVIS é um pedido HTTPS e uma resposta — sem janela, sem
carregamento, sem login, sem espera.

| peça | o que faz |
|---|---|
| `server/openrouter_api.py` | `criar_chave`, `listar_chaves`, `chave_de_gestao_vale`; erros do site traduzidos (401/403/429/5xx) com o próximo passo |
| `chave-no-navegador.py --api` | cria a chave pelo `POST` e grava no `.env` (exige `--autorizar`) |
| `chave-no-navegador.py --gestao` | lê a chave de gestão da área de transferência, **confere** e guarda em `JARVIS_OPENROUTER_GESTAO` |
| `chave-pela-api.bat` | um duplo clique: na primeira vez ensina onde criar a chave de gestão; depois, cria a chave em um segundo |
| `chrome-cdp.bat` | **não abre outro Chrome** se a janela do JARVIS já estiver de pé, e abre com as opções que tiram sincronização, extensões e pedidos de segundo plano |

Duas decisões que custaram cuidado:

1. **a chave de gestão é conferida antes de ser gravada.** Ela tem o mesmo
   formato de uma chave comum; guardar a errada só daria erro na vez seguinte.
   Ler a lista de chaves é o teste mais barato que existe — e só a de gestão
   pode fazer isso;
2. **o `POST` não manda `limit` nem `expires_at`.** “Sem limite e sem tempo de
   expiração” é o que se pede **não** mandando nada; mandar `null` seria
   adivinhar o que o site faz com nulo.

O teste não precisa de rede: um OpenRouter falso devolve a chave, o 401, o 403,
o 429, o servidor fora e a resposta sem `key` — e cada um tem de virar a frase
certa, sem gravar nada quando não deu.

### 0.91.28 — lentidão não é recusa; e a primeira vez pede um login

O print de 16/11 11:57 mostrou o caminho novo funcionando até certo ponto: o
`chrome-cdp.bat` abriu o Chrome do JARVIS, achou a porta 9222 — e a aba ficou
num **cartão branco**, com o endereço `openrouter.ai/sign-in?redirect_url=…`.
Duas coisas ao mesmo tempo: a página **demorando** para carregar e a janela
nova **sem conta**.

A 0.91.27 dava 25 s para a página e tratava “Sign In” como fim de linha
(“entre e rode de novo”). As duas coisas estavam erradas:

| antes | agora |
|---|---|
| 25 s e desiste | até **90 s** carregando, com o tempo aparecendo a cada 10 s |
| “Sign In” = pare e recomece | **espera o dono entrar** na janela (até 5 min) e **segue sozinho** quando a página das chaves aparece |
| conexão que cai no meio = erro | reconecta na mesma aba (5 falhas seguidas) e continua |
| aba vazia = “não deu” | diz que a página **não terminou de carregar**, sugere F5 e lembra que a janela já está logada |

O `--espera-carregar` e o `--espera-login` existem para isso, e o teste os usa
para não dormir de verdade.

### 0.91.27 — o fim da loteria: a página responde pelo protocolo do Chrome

O log de 16/11 fechou a conta do caminho antigo. Duas medidas, na mesma tarde:

- o diagnóstico da **0.91.26** ligou o sinal de leitor de tela **antes** da
  primeira leitura, pediu a árvore (`WM_GETOBJECT`, OBJID −4) **três vezes** e
  nas três rodadas “DEPOIS do pedido de árvore” leu **3/3/3/3/2**;
- o `pegar-chave.bat` leu **quatro nomes** — “Keys | Settings | OpenRouter”
  duas vezes e “Restaurar páginas?” duas vezes — e chamou isso de “a página foi
  lida inteira”.

Ou seja: doze versões tentando **ler a tela** de uma janela que o Chrome
publica e despublica quando quer, e um balão do Chrome (“Restaurar páginas?”,
que apareceu porque o `taskkill /F` mata o navegador sem ele salvar a sessão)
entrando na leitura como se fosse o site.

A 0.91.27 para de ler a tela. O Chrome tem uma porta de controle própria, a
mesma que o F12 usa — o **DevTools Protocol**. Por ela, o programa não olha
pixels nem árvore de acessibilidade: ele **pergunta à página** quais são os
botões e recebe a resposta em texto. É determinístico: a mesma página, a mesma
pergunta, a mesma resposta.

| peça | o que faz |
|---|---|
| `server/chrome_cdp.py` | WebSocket mínimo (aperto de mão, quadros mascarados, ping/pong) e `Sessao.chamar/javascript`. Sem biblioteca externa: o JARVIS é instalado por zip, sem internet |
| `chave-no-navegador.py --cdp` | o fluxo inteiro pela página: “New key” → nome → expiração → limite → “Create” → lê a chave → grava no `.env` |
| `_CDP_AJUDA` | a única função injetada na página (`pronta`, `texto`, `clicar`, `select`, `opcoes`, `digitar`, `chave`). Ela não sabe de OpenRouter: recebe uma ordem e devolve o que a página respondeu |
| `chrome-cdp.bat` | abre um Chrome **próprio** do JARVIS (perfil em `perfil-cdp`), com a porta 9222, e já chama o `--cdp`. O Chrome do dono não é fechado |
| `_leitura_boa` | título repetido e o balão “Restaurar páginas?” passam a ser moldura: 4 títulos iguais não são a página |
| `--pegar` | se a porta 9222 está aberta, vai por ela; se não, segue o caminho antigo |

Duas verdades do Chrome que a 0.91.27 respeita:

1. **A porta não abre no Chrome que já estava rodando.** É preciso iniciar o
   Chrome com `--remote-debugging-port=9222`.
2. **Desde o Chrome 136 a porta é ignorada no perfil padrão.** O Chrome passou
   a exigir um `--user-data-dir` que não seja o de sempre — é proteção contra
   roubo de cookie por porta de depuração. Por isso o `chrome-cdp.bat` usa a
   pasta `perfil-cdp`, e por isso a **primeira** vez pede um login nessa janela:
   ela é separada da do dia a dia, e fica guardada para as próximas.

O que fica provado por teste, sem Chrome nenhum:

- o transporte (aperto de mão, quadro mascarado, resposta casada por `id`,
  erro do Chrome virando frase em português);
- o JavaScript injetado, rodando no `node` sobre uma página falsa que tem o
  OpenRouter **e** a moldura do print de 16/11. O clique em “New key” acha o
  botão mesmo com os títulos repetidos na frente, o painel abre, o nome entra,
  a lista de expiração oferece “No expiration”, e a chave só aparece depois do
  “Create”.

### 0.91.26 — a página publicada e despublicada em segundos

O log do dono (16/11) trouxe a prova que faltava, e ela é de duas metades:

    1a rodada:   msaa 85 elementos — diálogo: SIM
    2a rodada:   auto 3 — uia 3 — uia_raw 3 — uia_content 3 — msaa 2

**Mesma janela, mesmo processo, sem nada mudar na tela.** O Chrome liga a
árvore da página quando alguém a pede e a desliga quando para de pedir. Ligar o
sinal de leitor de tela **uma vez** (0.91.26) não segura a página: ela aparece,
o programa lê, e três passos depois está de volta a moldura.

| peça | o que muda |
|---|---|
| `_tomar_o_sinal` | o modo leitor de tela é ligado **antes da primeira leitura**, não na primeira falha; volta ao normal no `finally` |
| `_reler(..., curar=True)` | quando a leitura vem pobre, **toda** leitura do programa pede a árvore de novo (`WM_GETOBJECT`) e relê — é por aqui que passam o preenchimento do painel, o “Create”, a conferência e a cópia |
| `acordar_acessibilidade` | 3 pedidos com pausa (o Chrome leva 1–2 s para ligar o modo completo) e o `LPARAM` com sinal (`-4`), que no Windows de 64 bits era ignorado |
| `FONTES_DE_LEITURA` | a **MSAA** vai primeiro: foi a única que viu o painel aberto (85 elementos, contra 43–58 das vistas da UIAutomation) |
| `chrome-acessibilidade.bat` | espera o Chrome **fechar de verdade** (até 15 s) antes de abrir: reabrir cedo faz o Windows entregar a chamada ao processo antigo, e a opção de acessibilidade é ignorada |
| `--diagnostico` | insiste três rodadas com pedido de árvore e diz em qual delas a página apareceu; se não aparecer em nenhuma, diz o que ainda dá para tentar |

O teste do fluxo inteiro reproduz a sequência: a página existe, **some depois
de seis leituras** e o programa tem de pedir de novo e terminar com a chave no
`.env`. Contra o código da 0.91.26, ele falha — que é o que um teste de
regressão tem de fazer.

### 0.91.26 — o Chrome não estava publicando a página

O `diagnostico-chave.bat` da 0.91.26 respondeu a pergunta, e a resposta não era
nenhuma das que eu vinha tentando:

    auto        :   3 elementos — painel: não
    uia         :   3 elementos — painel: não
    uia_raw     :   3 elementos — painel: não
    uia_content :   3 elementos — painel: não
    msaa        :   2 elementos — painel: não

Com o painel **aberto na tela**. Não era a janela atrás (0.91.22), nem a vista
(0.91.23): o Chrome estava com a **acessibilidade desligada** e não publicava a
página para ninguém.

| peça | o que faz |
|---|---|
| `arvore_windows.ligar_leitor_de_tela` | liga `SPI_SETSCREENREADER` — o mesmo sinal que o NVDA dá ao abrir; é ele que faz o Chrome publicar a página |
| `arvore_windows.acordar_acessibilidade` | o sinal + um `WM_GETOBJECT` na janela e nas filhas (o pedido formal de árvore) |
| `arvore_windows.desligar_leitor_de_tela` | devolve a configuração como estava — o programa não toma o que não é dele |
| `_acordar_a_acessibilidade` | chamado quando a leitura vem pobre; **uma vez por janela**, com aviso em português |
| `--diagnostico` | mostra o estado do modo leitor de tela, mede **antes e depois** de ligar, e lista as **janelas filhas** do Chrome com a contagem de cada uma |
| `chrome-acessibilidade.bat` | último recurso: fecha o Chrome e abre com `--force-renderer-accessibility` |

O teste reproduz o print: um Chrome falso que devolve moldura em **todas** as
fontes até receber o sinal — e o caminho inteiro termina com a chave no `.env`.

O que continua não provado: se o sinal é suficiente no Chrome do dono. Se não
for, o diagnóstico agora diz isso — e a diferença entre “o Chrome não publica
nada” e “eu leio a janela errada” aparece nas linhas das filhas.

### 0.91.26 — o manual da página, e um jeito de medir sem gastar chave

Pedido do dono (16/11): *“eu vou ter que atualizar e testar de novo, você não
consegue testar isso; leia o manual da página de como configurar, onde é o
nome, onde deve clicar, passo a passo”*.

Duas entregas, e a segunda vale mais que a primeira:

| peça | o que é |
|---|---|
| `docs/CHAVE-OPENROUTER.md` | o manual da página, campo por campo, com o que o JARVIS faz em cada ponto |
| `diagnostico-chave.bat` + `--diagnostico` | mede o que **cada leitura** enxerga e escreve o relatório — **sem criar chave e sem clicar em nada** |

O manual foi escrito da documentação oficial (`Creating an API key`,
`Authentication`) e dos prints: a ordem é **Name → Expiration → Credit limit →
(Reset limit every) → Create**, as opções de expiração vão de `1 day` a
`No expiration`, o `Reset limit every` fica em `N/A` com “No limit”, e a chave
aparece **uma vez só**, com o botão `Copy`.

O `--diagnostico` é a resposta ao “você não consegue testar”: ele imprime uma
linha por leitura (`auto`, `uia`, `uia_raw`, `uia_content`, `msaa`) com quantos
elementos cada uma trouxe e **quais campos do painel cada uma vê**, e grava
tudo em `chave-leitura.txt`. Com o painel aberto na tela — que é a situação dos
prints —, o arquivo responde a pergunta que sobrou: **qual vista enxerga o
painel?**

O `chave-leitura.txt` ganhou a linha `painel: SIM — nome, expiração, limite,
criar` (ou `não — nenhum campo do painel nesta leitura`). É o que separa
“a página não tem o painel” de “esta leitura não vê o painel”.

O que **não** se sabe continua sendo o de sempre: se a vista crua resolve no
Chrome do dono. Mas agora dá para descobrir isso sem criar chave nenhuma — um
duplo clique e um arquivo.

### 0.91.23 — o problema não era a janela: era a vista

Print de 16/11, 07:52. O painel **Create API key** aberto, e outra vez

    2. NÃO DEI: … (3 elementos com nome, fonte uia; os primeiros:
    Chrome Legacy Window, Keys | Settings | OpenRouter, Notifications)

A 0.91.22 tinha uma teoria: a janela estava atrás do console e por isso a
leitura caía. Nesse print, a 0.91.22 **fez** o que prometia — trouxe a janela
para a frente, duas vezes — e a leitura continuou pobre. A teoria estava
errada, e a mensagem estava certa em dizer que o defeito era **ver**, não
clicar.

A causa é a **vista** de acessibilidade. A UIAutomation tem três: controle
(o que um teclado alcança), conteúdo e **crua**. Com um modal aberto, o site
esconde a página da tecnologia assistiva — e a vista de controle, que era a
única usada, passa a devolver a moldura. A vista crua continua vendo tudo,
inclusive o painel, porque ela não respeita o que o site marcou como
escondido.

| peça | o que muda |
|---|---|
| `arvore_windows.UIA_VIEWS` | as três vistas (índices 14, 15, 16); `ler_janela` aceita `uia`, `uia_content`, `uia_raw` |
| `_ler_pela_fonte` | a vista crua ganha orçamento maior (profundidade 18, 6.000 nós): o painel é o **último** nó do documento, e com o teto normal seria cortado |
| `_reler` | quando a automática vem pobre, uma fonte extra por chamada, girando entre as quatro; achada a que mostra a página, ela passa a ser a primeira (`_FONTE_PREFERIDA`) |
| `_leitura_boa` (novo) | contagem sozinha não decide: o painel tem 6 nomes e a página recém-criada também; moldura é o que tem “Chrome Legacy Window” no nome |
| `chave-leitura.txt` | mede as cinco leituras (auto, uia, uia_raw, uia_content, msaa), para a próxima falha dizer qual vista vê |

Duas correções menores que vieram do mesmo print:

- **a espera da área de transferência não fica calada**: a cada 20 s uma linha
  diz que ele continua olhando (o dono já apertou Ctrl+C numa espera muda de
  120 s);
- **lista de crédito sem “sem limite”**: ele escolhe o maior valor da lista e
  diz que escolheu, em vez de parar sem criar chave nenhuma.

O que **não** se sabe: se a vista crua é o que resolve no Chrome do dono. O
teste prova o comportamento (com a vista de controle na moldura e a crua na
página, o caminho inteiro termina com a chave no `.env`), não a causa. Se
falhar de novo, o `chave-leitura.txt` agora traz a contagem das cinco leituras
— e a linha com mais nomes é a resposta.

### 0.91.22 — o painel estava na tela e a leitura era da moldura

Print de 15/11, 20:32. Três coisas ao mesmo tempo: o painel **Create API key**
aberto e vazio, o console com o log, e o veredito:

    2. NÃO DEI: a leitura não trouxe o que eu procurava (3 elementos com nome,
    fonte uia; os primeiros: Chrome Legacy Window, Keys | Settings | OpenRouter,
    Notifications).

O clique tinha funcionado. O que falhou foi **ver**: a janela do Chrome estava
atrás do console (o dono foi ler o log), e a leitura passou a trazer só a
moldura. O script leu 3 elementos, chamou de “o painel não abriu” e ainda
escreveu “a página foi lida inteira” — que era falso.

**Leitura pobre não é resposta.** É a mesma regra da 0.91.20, aplicada onde ela
ainda faltava:

| onde | o que passou a acontecer |
|---|---|
| `_acordar_leitura` (novo) | leitura com menos de 8 nomes → traz a janela para a frente, confirma o foco e relê |
| `_esperar_dialogo` | leitura pobre acorda a janela e relê em vez de contar como tentativa; olha a janela vizinha nesse caso também |
| `_esperar_pagina_pronta` | página que “não aparece” pode ser janela atrás — acorda antes de concluir lentidão |
| degrau 2 do `_criar_e_copiar` | a queda depois do clique acorda a janela antes de decidir não repetir |
| desistência | só diz “o clique não abriu o painel” se a leitura era **rica**; se era pobre, diz “não consegui ver a página” e o que fazer |
| `chave-leitura.txt` | linha nova `estado:` com minimizada / com foco / **SEM o foco (o foco está em …)** |

Paciência também subiu: 20 s por degrau de clique (era 12) e o aviso de leitura
caída aparece uma vez, em português.

O que **não** se sabe: se a janela atrás é mesmo a causa. O teste prova o
comportamento — janela que para de publicar é acordada e o painel é lido —, não
a causa no Chrome do dono. Se voltar a falhar, a linha `estado:` no
`chave-leitura.txt` responde isso na primeira tentativa.

### 0.91.21 — a regra dos testes, e um buraco que ela encontrou

Pedido do dono: *“toda vez q corrigir um bug crie um teste de regressao”*.

Antes de escrever a regra, veio a prova de que ela é necessária: o primeiro
teste de ponta a ponta **reprovou o código da 0.91.20**. Com a página lenta, o
`--auto` desistia da criação automática antes de esperar — o
`_levar_ate_as_chaves` devolve a última leitura que fez, e ela podia ser de uma
página em construção. O `_criar_e_copiar`, que espera e relê, era chamado só
quando a página já parecia pronta.

Duas coisas entraram:

| peça | regra |
|---|---|
| espera antes de desistir | sem o botão na leitura, o `--auto` espera a página sossegar e relê fundo **antes** de cair no plano B |
| `docs/TESTES.md` | a regra do projeto, com a tabela versão → teste |
| `test_regras_do_projeto.py` | a regra cobrada por máquina: toda versão com `NOVO-*.md` (a partir da 0.91.13) tem teste listado, e todo teste citado existe |

O teste de ponta a ponta (`test_chave_ponta_a_ponta.py`) roda o `main()` de
verdade contra um Chrome de mentira que **muda de estado quando é clicado**. De
mentira: janelas, árvore, clique, área de transferência, relógio. De verdade:
`chave-no-navegador.py`, `chave_web.py`, `arvore.py` e a escrita do `.env`.
São 19 cenários, um por print do dono — da página lenta ao botão apagado.

Por que a regra precisa ser cobrada por máquina: entre a 0.91.17 e a 0.91.20 o
**mesmo sintoma** (“não criou a chave”) voltou quatro vezes por causas
diferentes. Cada correção desfez um pedaço da anterior sem que ninguém
percebesse — porque o teste da anterior não existia.

### 0.91.20 — o botão estava na tela e a leitura não o trouxe

Print do dono: a página inteira, “New key” visível no canto direito, e a saída

    1. NÃO DEI: o botão de criar não está na árvore desta janela.

O script desistia na **primeira** tentativa, com a leitura que tinha em mãos —
a mesma que acabara de dizer “a página ainda está carregando”. Ou seja: ele
sabia que a leitura era de uma página em construção, e usou essa leitura como
veredito.

O que entrou:

| peça | regra |
|---|---|
| `_achar_elemento` | procura **relendo** por 18 s, com leitura funda, antes de dizer que não existe |
| outras janelas | a cada duas tentativas ele olha as outras janelas do navegador — a página pode ter aberto na vizinha |
| `_esperar_pagina_pronta` | passou a reler **fundo** (era rasa) e, ao cansar, diz quantos elementos vieram |
| desistir com prova | o erro diz quantos elementos a leitura trouxe e os primeiros nomes, e grava `chave-leitura.txt` |
| diagnóstico neutro | “a leitura não trouxe o que eu procurava” — a frase serve para o botão e para o painel |

Duas decisões que valem registro:

- **a leitura que decide é a mesma que clica.** Ter uma leitura rasa para
  decidir “pronto” e uma funda para clicar é o que produzia “o botão não
  existe” com o botão na tela;
- **“não achei” precisa de número.** Sem a contagem e os primeiros nomes, a
  próxima execução falharia igual e ninguém saberia por quê.

### 0.91.19 — o clique acertou o botão, e o nome não foi digitado

Depois da 0.91.18 o painel **abriu** (o clique de mouse resolveu). E o campo
“Name” ficou vazio. O script procurava o campo pelo **nome** — e no painel do
OpenRouter “Name” e a caixa de texto são **dois nós**: o rótulo é texto (papel
41), a caixa é edição (papel 42, ação “escrever”). Ele achava o rótulo,
clicava nele e mandava as teclas para o nada — e seguia dizendo “escrevendo…”.

O que entrou:

| peça | regra |
|---|---|
| `e_campo_de_escrita` | quem recebe texto é quem **aceita escrever** (`escrever`/`digitar`), não o rótulo ao lado |
| `campo_do_nome` | quatro regras: nome do campo → acima da expiração → abaixo do rótulo “Name” → a caixa mais alta do painel |
| filtro por posição | o que está acima do título “Create API key” é a página (a busca “Search by name…”), não o painel |
| `_escrever_no_campo` | três degraus com **conferência**: clique + teclado → foco pela árvore → teclado com a janela na frente |
| `conferido` | relê o valor do campo (MSAA) mesmo no degrau do clique físico — antes ele dizia “digitei” sem saber |
| botão apagado | o “Create” desabilitado é a prova final: não se clica nele, e a mensagem diz **qual** campo faltou |
| reescrita | botão apagado + nome sem confirmação → reescreve o nome do zero, com `Ctrl+A` antes (senão vira “nome nome”) |
| `_botao_de_criar` | “Create” exato, não o título “Create API key” — o título também contém “create” e passava na frente quando o botão estava apagado |

Duas decisões que valem registro:

- **`conferido=None` não é falha.** Campo que não publica valor não prova nada;
  tentar digitar de novo escreveria o nome duas vezes. Quem decide é o botão;
- **botão apagado não se clica.** Clicar num botão desabilitado não gera erro,
  não cria nada e deixa o dono olhando uma tela parada — foi o que aconteceu
  duas vezes.

### 0.91.18 — a ação do elemento devolve sucesso e não faz nada

Depois da 0.91.17 a página passou a ser lida inteira — 43 elementos, o botão
“New key” nela — e **o painel continuou não abrindo**. Duas esperas de 35 s
depois de dois cliques que “deram certo”. O print mostrava a saída exata:

    1. clicando em “New key”…
       ação padrão do elemento

`accDoDefaultAction` devolve `S_OK`. No Chrome, para este botão, ela não faz
nada. O `executar_ref` tentava a ação **antes** do clique físico, e o clique
físico só vinha primeiro com `--mouse` — que o `.bat` não passa. Ou seja: o
`pegar-chave.bat` nunca clicava de verdade.

E havia prova do contrário na própria história: na 0.91.15 o clique saiu como
**“clique físico em 68,317”** e o painel abriu (o print do dono mostrava o
painel na tela; quem falhou ali foi a leitura). Ação do elemento: nada. Clique
de verdade: painel aberto.

O que entrou:

| peça | regra |
|---|---|
| clique físico primeiro | `primeiro_mouse` passou a ser “o mouse está autorizado” (o padrão), não “o dono passou `--mouse`” |
| `_garantir_na_frente` | traz a janela e **confirma** pelo `GetForegroundWindow` — `SetForegroundWindow` pode dizer ok sem trocar nada |
| escada de 3 degraus | clique → clique de novo (o primeiro pode só ativar a janela) → ação do elemento |
| esperas curtas | 12 s, 12 s, 10 s — em vez de 70 s parado depois de um clique que não fez nada |
| relatório com os cliques | `chave-leitura.txt` passa a listar o que cada degrau fez |
| Ctrl+C | sai com “Interrompido com Ctrl+C. Nada foi gravado.”, sem traceback |
| `--pegar` honesto | chave igual à que já está no `.env` deixa de ser anunciada como nova |

Duas decisões que valem registro:

- **clique recusado para a escada.** Se o Windows *recusa* o clique (janela
  coberta, ponto fora), repetir do mesmo jeito não muda a resposta: para ali e
  diz o motivo — a regra da 0.91.10 continua;
- **repetir só com leitura boa.** Um degrau novo só acontece se a página ainda
  se parece com a que tinha o botão (mesma ordem de grandeza de elementos). Sem
  isso, um segundo clique poderia abrir um painel em cima de outro.


### 0.91.17 — a página ainda carregava, e a leitura às vezes volta só a moldura

Duas telas, dois defeitos diferentes — e a leitura era a mesma nos dois:

| tela | o que a leitura trouxe | o que aconteceu |
|---|---|---|
| print 1 | 43 elementos, a página inteira | o clique em “New key” caiu enquanto a página ainda montava; o painel não abriu |
| print 2 | **3 elementos**: “Chrome Legacy Window”, o título da aba, “Notifications” | o painel estava aberto na tela e o script disse que não |

O segundo é o mais instrutivo: **3 nomes é a moldura do Chrome, não a página.**
O Chrome moderno publica o conteúdo pela UIAutomation; a MSAA devolve só a
casca da janela. Quando a escolha automática de fonte caía nessa casca, a
página inteira sumia da leitura — e o script concluía “o painel não apareceu”
com toda a confiança do mundo.

O que entrou:

| peça | regra |
|---|---|
| `LEITURA_POBRE = 8` | abaixo de 8 nomes a leitura não chegou na página |
| `_reler` | leitura pobre é repetida pedindo `uia` e `msaa` na mão; fica a que mostrou mais |
| `_esperar_dialogo` | 35 s (eram 12), com aviso de progresso a cada tentativa |
| `_esperar_pagina_pronta` | antes de clicar: o botão existe **e** duas leituras seguidas trazem os mesmos elementos |
| segunda tentativa | se a página está legível e o painel **não** está, repete o clique uma vez |
| `_gravar_relatorio` | ao falhar, grava `chave-leitura.txt` com as três leituras |
| conferência do passo 3 | leitura que despenca (43 → 3) não vira veredito: quem decide é a cópia |

Três decisões que valem registro:

- **repetir o clique só com prova.** A segunda tentativa exige leitura boa (≥ 8
  nomes) e ausência do painel. Com leitura pobre não se sabe o que está na
  tela — repetir poderia abrir um segundo painel em cima do primeiro;
- **espera com aviso.** Trinta e cinco segundos calados parecem travamento (o
  dono chegou a interromper com Ctrl+C: o `KeyboardInterrupt` aparece no print);
- **cansar é diferente de falhar.** O relatório em arquivo existe porque a tela
  mostra só o veredito; o arquivo mostra o que cada fonte leu.

### 0.91.16 — o diálogo estava na tela e a leitura não o via

O dono rodou a 0.91.15 no PC e mandou o print: **Create API key aberto na
tela**, e a saída dizendo

    NÃO DEI: o diálogo de criação não apareceu na leitura.

O script estava certo sobre o que queria; errado sobre o que lê. Quatro
defeitos, todos medidos nesse mesmo print:

| defeito | o que acontecia | correção |
|---|---|---|
| leitura rasa | `ler_janela(handle, 8, 1500)` — o painel mora no fim do documento, depois do nível 8 | a espera e o preenchimento releem fundo (`PROFUNDA = 14`, `TETO_FUNDO = 3000`) |
| reler pelo **nome** | cada passo escolhia “a janela do chrome”; com duas abertas, podia ler a errada | `_reler(janela)` relê **pelo handle** — o nome é palpite, o handle é identidade |
| uma janela só | se o clique caía na janela A e o painel abria na B, ninguém olhava a B | `_esperar_dialogo` confere as até 3 janelas do navegador |
| falso positivo | “Create Key” estava na lista de títulos do diálogo — e é o **botão**, que existe o tempo todo | título agora é só “Create API key”; o botão ficou de fora |

E duas coisas a mais, porque a mensagem de erro era o problema:

- **o diagnóstico diz o que a leitura viu** — quantos elementos com nome e os
  primeiros nomes, em vez de “não apareceu”. Com o diálogo na tela, a frase
  passa a ser investigável em vez de misteriosa;
- **o teclado é o último degrau do nome**: o diálogo nasce com o cursor dentro
  do “Name”. Se a leitura não der o campo, digitar só acontece com a janela na
  frente e o teclado nela — nunca às cegas.

O que **não** mudou: as escolhas continuam “Never” (ou o maior prazo) e “No
limit”; sem diálogo o passo para; sem chave nada é gravado; o cursor volta
para onde estava.


### 0.91.15 — o diálogo de criação tem três campos (e um botão apagado)

Tela do dono, medida: **Create API key** pede

    Name *          caixa de texto
    Expiration *    “Select expiration” — lista
    Credit limit *  “Choose a credit limit” — lista

com o botão **Create** no rodapé. Preencher só o nome e clicar em Create não
cria nada: o botão está apagado. No Windows isso não gera erro — o clique
“acontece” e nada muda. Era esse o travamento, e o relatório dizia que tinha
dado certo.

O que entrou:

| peça | regra |
|---|---|
| `e_dialogo_de_criacao` | reconhece “Create API key” aberto |
| `melhor_expiracao` | escolhe o **maior prazo**; “Never/Nunca” ganha de tudo |
| `melhor_limite` | escolhe “No limit/Sem limite”; se só há números, não escolhe |
| `nomes_novos` | as opções de uma lista são os nós **que apareceram** entre as duas leituras |
| `_preencher_dialogo` | nome → expiração → limite, cada um dizendo o que escolheu |
| conferência do diálogo | depois do Create, relê: se o diálogo continua aberto, **não criou** |

Três decisões que valem registro:

- **o maior prazo, não o mais curto.** A chave que expira em 90 dias derruba o
  JARVIS três meses depois, e ninguém liga uma coisa à outra;
- **“No limit”** para o crédito: escolher um teto faz a chave parar sozinha no
  meio do mês;
- **sem o diálogo, não segue.** Antes, se o diálogo não abria, o passo seguinte
  achava o “New key” da página e clicava de novo — e o relatório dizia “criei”.

Quando um campo não é preenchido, o script diz qual ficou faltando e manda
completar no navegador e rodar `--pegar`; nada é gravado sem chave.


### 0.91.14 — “ele tem que saber a página e a parte em que ele tá”

Medido nas telas do dono, e o defeito era grave: abrir `openrouter.ai/keys` sem
sessão cai em **“Sign In | OpenRouter”**. Como a marca de “página de chaves”
incluía a palavra `openrouter`, o JARVIS achou que já estava no lugar certo,
parou e pediu um botão “Create Key” que não existia naquela tela.

Três páginas, na mesma janela, na ordem em que aparecem:

| onde estou | como se reconhece | o que fazer |
|---|---|---|
| login | “Sign In”, “log in”, “entrar” no título/texto | clicar no botão **Google** |
| escolha de conta | `accounts.google.com`, “escolha uma conta”, “prosseguir para” | clicar na conta do dono |
| página de chaves | “API keys”, “New key”, “Create key” | criar, copiar, gravar |

Regras novas em `chave_web`: `onde_estou`, `contas_visiveis`, `casar_conta`,
`texto_do_estado`. `MARCAS_DA_PAGINA` perdeu `openrouter` — a palavra que
causou o falso positivo — e ganhou `new key`, que é o botão de verdade.

Detalhes que evitam estrago:

- **conta ambígua não é escolhida no chute**: duas contas e nenhuma dita →
  pergunta (no console) ou para e pede `--conta`. Entrar na conta de outra
  pessoa criaria a chave no lugar errado;
- a conta escolhida fica no `.env` como `JARVIS_CONTA_GOOGLE`;
- depois de clicar, três segundos de pausa antes de clicar de novo — no Google,
  dois cliques no mesmo botão abrem duas janelas de login;
- “o que dá para apertar” vem antes de “o que só está escrito”: o parágrafo
  “Create and manage your API keys.” não pode ganhar do botão “Create”.


### 0.91.13 — a chave nova vale na hora (sem fechar o JARVIS)

O servidor lê o `.env` **uma vez**, no start. Toda chave gravada por fora da
tela — pelo `chave-no-navegador.py`, pelo `.bat`, editando o arquivo — ficava
certa no arquivo e velha na memória: a tela continuava mostrando a anterior até
alguém fechar e abrir. É o mesmo defeito de “tela velha” de versões atrás,
aparecendo por outra porta.

Duas peças:

| peça | o que faz |
|---|---|
| `POST /api/ai/recarregar` | só da própria máquina: recoloca o `.env` no ambiente e manda o cérebro em memória reler. Não reinicia processo. |
| `_avisar_jarvis_aberto()` no script | tenta essa rota após gravar (1,5 s, portas 8000/8001). API desligada não é erro. |

O script passa a dizer qual dos dois casos aconteceu: “o JARVIS que já está
aberto passou a usar esta chave agora” ou “ele vai ler esta chave quando abrir”.


### 0.91.12 — o JARVIS copia sozinho (e espera quando não consegue clicar)

O dono corrigiu o desenho: “ele deve abrir os sites onde estão as chaves para
ele poder copiar e colar na própria pasta”. Abrir e esperar o dono fazer o
resto era meio caminho.

Entrou o `--auto --autorizar`, que é o que o `pegar-chave.bat` chama:

| passo | como |
|---|---|
| 1. abrir | `guia_do_provedor` → o site do provedor que está no `.env` (ou `--provedor`) |
| 2. achar a janela certa | entre várias janelas do Chrome, a da página de chaves; a em foco primeiro |
| 3. criar | Create Key → nome → Create, com o mouse nos botões medidos |
| 4. copiar | Ctrl+A/Ctrl+C no texto da página (não depende de botão) e, se falhar, o botão “Copy” |
| 5. gravar | só a chave, sem questionário (0.91.11) |

Três decisões que sustentam o resto:

- **a foto da área de transferência é tirada antes do primeiro clique.** Sem
  isso, o texto que o próprio “Create” põe na área seria confundido com “o que
  já estava lá” e a chave nova seria recusada por ser igual a si mesma — este
  defeito existiu por uma hora e o dublê pegou;
- **sem botão na árvore, o comando não morre**: ele explica os quatro cliques,
  deixa a página aberta e espera a chave aparecer (90 a 120 segundos), depois
  grava;
- **`Ctrl+C` só é enviado se o teclado estiver na janela do navegador**
  (`arvore_windows.teclado_na_janela`).


### 0.91.11 — o duplo clique (nenhum comando para decorar)

Resposta ao “não entendi, só atualizei”: o caminho existia, mas exigia lembrar
um comando de duas linhas e uma opção. Agora é um arquivo na pasta:
`pegar-chave.bat`.

Ele faz, na ordem: abre `openrouter.ai/keys`; mostra no console os quatro
cliques do site (Create Key → nome → Create → COPIAR); espera; lê a área de
transferência; grava. Se a leitura falhar, oferece tentar de novo sem fechar a
janela — o caso comum de copiar a chave depois de já ter apertado Enter.

Duas correções que vieram junto:

| antes | depois |
|---|---|
| gravar chamava o questionário inteiro (provedor, base, modelo) | com provedor já gravado, troca só a chave e diz o que manteve |
| `--pegar` lendo área vazia só dizia “não deu” | diz para copiar no site e rodar de novo |

O `.bat` é ASCII puro com CRLF, como os outros: o console antigo não desenha
acento e o Bloco de Notas não entende LF.


### 0.91.10 — o mouse no botão (medido antes de clicar, e com freio)

A pergunta do dono — “por que não clica no botão de copiar com o mouse?” — tinha
resposta técnica: até a 0.91.9 o executor só sabia pedir a **ação padrão do
elemento**. Quando a página não declara essa ação, ou quando a leitura veio da
UIAutomation (e a janela não publica MSAA), não havia o que fazer.

O que entrou:

| peça | regra |
|---|---|
| `arvore.dentro_da_janela` | o ponto do clique tem de cair dentro do retângulo da janela — conta pura, testada |
| `arvore_windows.clicar_fisico` | traz a janela para a frente, confere a posição, clica e **devolve o cursor** ao dono |
| `executar_ref(..., mouse=True)` | o clique por coordenada é o último degrau; sem `mouse`, continua só a árvore |
| `chave_web.PADROES_CONFIRMAR` | o botão do diálogo é “Create”, não “Create Key” |
| `chave_web.diagnostico` | diz se o botão tem **posição medida** (“o mouse acerta”) ou só nome |

O `--criar --autorizar` usa o mouse por padrão (foi o pedido); `--sem-mouse`
volta ao comportamento antigo. O `--ver` nunca clica.

Também consertou um erro silencioso: o retorno do clique era descartado, e um
passo que falhava fazia o script culpar o seguinte. Agora o primeiro que não dá
para ali, com o motivo do Windows.


### 0.91.9 — a chave pelo navegador (medir antes de clicar)

Pedido do dono: entrar no site, gerar a chave e salvar sozinho. Duas coisas
precisam ser ditas com clareza:

1. **A chave existente não é legível.** O OpenRouter mostra o valor uma vez, na
   criação, e depois só o prefixo mascarado. Não há o que coletar da página.
2. **Criar uma nova é automatizável em princípio** — clicar, nomear, criar,
   copiar, ler a área de transferência — mas depende de o Chrome publicar esses
   botões na árvore de acessibilidade, e isso **não foi medido**.

Por isso o script novo (`chave-no-navegador.py`) chega em três degraus:

| comando | o que faz | risco |
|---|---|---|
| `--pegar` | lê a área de transferência e grava | nenhum — só lê o que você copiou |
| `--ver` | lê a janela e diz quais botões existem | nenhum — não clica |
| `--criar --autorizar` | clica e cria uma chave nova na conta | cria credencial de verdade |

A regra de achar (normalizar, preferir nome curto, ignorar página errada) mora
em `server/chave_web.py` e é testada sem Windows; o driver fica no script.

O `--pegar` é a peça que resolve o problema real das últimas três versões: a
chave **não passa pelo console**, então não há Ctrl+V para virar `\x16` nem
seleção de mouse para cortar caractere.


## Etapa 3 fechada — do zero ao texto conferido (0.90.0)

Na máquina do usuário, com o Bloco de Notas **fechado**, um comando:

```
.venv\Scripts\python arvore_sonda.py --programa "bloco de notas" --escrever "oi, mundo" --executar
```

```
Abri o Bloco de notas. Feito: digitar 'oi, mundo' em texto em 22,465 (970x69) (conferi: o texto está no campo)

janela:  notepad.exe — Sem título - Bloco de notas
alvo:    @95bc8c3d:e11  texto “”
onde:    22,465 (970x69)
fonte:   msaa   leitura: 95bc8c3d
como:    valor do campo (put_accValue, sem teclado)
abri:    C:\Windows\system32\notepad.exe
conferi: o texto está no campo.
```

A cadeia inteira, medida: **achar o executável → abrir → achar a janela nova →
esperar o campo → escrever → ler de volta e conferir.**

### O que ficou provado, e por qual caminho

| passo | como | confere? |
|---|---|---|
| achar o programa | PATH → System32 → App Paths | caminho impresso |
| abrir | `Popen(caminho)`; sem caminho, ShellExecute | janela do `pid` novo |
| escolher a janela | processo vence título; minimizada por último | sim |
| escrever | `put_accValue` (o 4º degrau) | texto de volta |
| chegar antes | `SetForegroundWindow` | sem mouse |

O caminho vencedor foi o **quarto degrau** — `put_accValue`. Neste Bloco de
Notas o foco não vem (nem no elemento, nem no campo inteiro), então o teclado
nunca seria usado. Foi bom ter os quatro: quem dependesse só de teclado estaria
parado até hoje.

### O que ainda não está provado

- **programas que não publicam o valor do campo.** Se um programa não expõe
  `accValue`, o quarto degrau não existe. Aí resta o `--mouse` (5º degrau) ou
  nada. Cada programa é uma medição, não uma suposição.
- **teclado de verdade.** Neste PC ele nunca chegou a rodar, porque o foco não
  vem. Em outro programa pode ser o caminho natural.
- **escrever no meio de um texto existente.** Ou é acrescentar no fim
  (`--acrescentar`), ou recusa. Editar o meio é outra etapa.

### E o agente escolhe essa skill sozinho

“escreve oi no bloco de notas” empatava em 0,56 com uma skill de memória —
empate é sorteio. As skills passaram a declarar **palavras-chave** (campo
`keywords`), que contam como termo forte na busca do agente local:

| frase | skill escolhida | nota |
|---|---|---|
| escreve oi no bloco de notas | `mesa.ditar` | 1.00 |
| abre o paint e escreve oi | `mesa.ditar` | 0.78 |
| leia a janela do notepad | `mesa.arvore` | 0.67 |
| quais janelas estao abertas | `mesa.status` | 0.75 |

## Depois de abrir, reler — e não trocar a janela nova pela velha (0.89.6)

Com o caminho do executável certo (0.89.5), faltavam dois furos que só
aparecem no momento exato em que o programa nasce:

1. **A lista de janelas ficava velha.** Ela era lida **antes** de abrir o
   programa — quando ele não existia. Depois de abrir, o plano e o retrato do
   erro falavam de uma janela que não era a que acabou de nascer. Agora a lista
   é relida depois da abertura.

2. **A sondagem roubava a janela recém-aberta.** Com mais de uma janela do
   programa, uma leitura em cada decide qual serve. Mas se um Bloco de Notas
   **antigo** também tem campo, ele vencia — e o texto iria para o arquivo
   errado, que pode ser o documento de alguém. A sondagem agora só vale para
   janelas que já existiam: **se eu acabei de abrir, a janela é a que eu abri.**

O teste `test_a_janela_aberta_nao_e_trocada_por_uma_antiga_com_campo` fixa
essa regra: dois Blocos de Notas, um com `relatorio`, outro recém-aberto — o
texto vai para o recém-aberto.

## Nome de gente × nome de arquivo (0.89.5)

O erro seguinte foi:

```
não achei bloco de notas no PATH, em C:\Windows nem no App Paths
([WinError 2] ...: 'bloco de notas')
```

`'bloco de notas'` — com aspas e tudo: **o nome falado usado como nome de
arquivo**. Duas camadas, dois vocabulários:

| camada | recebe | exemplo |
|---|---|---|
| `pc.abrir_programa` (API) | nome de gente | `bloco de notas` |
| `abrir` injetado (sonda) | executável | `notepad.exe` |

A 0.89.4 passou cada um para o lado errado. Não era programa ausente: era
argumento trocado — e a mensagem acusava o PC.

Agora cada camada recebe o que entende, e `abrir_direto` **tolera** o nome
falado (resolve em vez de falhar, porque quem chama nem sempre sabe o que tem
em mãos).

### O diagnóstico passou a responder duas perguntas

```
.venv\Scripts\python arvore_sonda.py --programa "bloco de notas"
```

Se o programa não estiver aberto, ele diz **e** diz se está instalado:

```
  O Bloco de notas (notepad.exe) não está aberto.
  Instalado em: C:\Windows\System32\notepad.exe
```

ou

```
  E não achei notepad.exe no PATH, em %SystemRoot% nem no App Paths —
  o programa pode não estar instalado neste PC.
```

Uma rodada, as duas respostas. Sem precisar adivinhar qual metade falhou.

## “O Windows recusou abrir notepad.exe” — mentira minha (0.89.4)

Depois da 0.89.3 o terminal parou de ser confundido com o Bloco de Notas, e o
erro seguinte foi:

```
NÃO DEU: o Windows recusou abrir notepad.exe: [WinError 2] O sistema não pode
encontrar o arquivo especificado
```

Duas coisas erradas nessa frase:

1. **“o Windows recusou”** — ele não recusou nada. `FileNotFoundError` é
   subclasse de `OSError`, e o `except OSError` genérico veio antes: qualquer
   “não achei o arquivo” era reportado como recusa.
2. **“notepad.exe” sozinho não basta** — `subprocess.Popen(["notepad.exe"])`
   depende do PATH do processo. Neste Windows (10.0.14393) voltou WinError 2.

A correção é `caminho_do_programa`, que procura em três degraus:

| degrau | onde | por quê |
|---|---|---|
| 1 | `shutil.which` | respeita o PATH quando ele está certo |
| 2 | `%SystemRoot%\System32`, `SysWOW64`, raiz | onde o Windows guarda os próprios programas |
| 3 | registro `App Paths` | onde os instaladores registram o que não vai no PATH |

E se nada for achado, `abrir_sem_shell` cai para `os.startfile` — o mesmo
mecanismo do duplo clique (`ShellExecute`), que acha pelo App Paths. Nenhum
shell de verdade é usado: não existe linha digitada nesse caminho.

O plano também passou a mostrar **qual caminho** foi aberto:

```
  abri:    C:\Windows\System32\notepad.exe
```

## O terminal não é o programa (0.89.3)

O diagnóstico da 0.89.2 entregou o culpado na primeira linha:

```
Bloco de notas (notepad.exe) — 1 janela(s):
  C:\Windows\system32\cmd.exe - .venv\Scripts\python arvore_sonda.py
  --programa "bloco de notas"  —  12 elemento(s), sem campo
```

A “janela do Bloco de notas” era **o próprio terminal**. O título do `cmd` é a
linha de comando, e a linha de comando dizia `"bloco de notas"`. O casamento
por título achava o mensageiro e chamava de alvo.

Corrigido em três regras:

1. **processo vence título, sempre** — e o título só é usado quando o processo
   não veio;
2. **terminal nunca casa por título** (`cmd.exe`, `powershell.exe`,
   `conhost.exe`, `wt.exe`… o título deles é o comando);
3. **título só casa inteiro** — igual, começando ou terminando com o rótulo.
   “Como abrir o Bloco de notas” é um artigo, não o programa.

## A pergunta do mouse: três degraus, e o mouse é o último

“Por que ele não usa o mouse para ir na janela e clicar no Bloco de Notas?”

**Para chegar na janela, mouse não é necessário.** `trazer_para_frente` usa
`SetForegroundWindow` + `BringWindowToTop` — com o truque de
`AttachThreadInput` que o Alt+Tab usa por dentro. A janela vem para a frente
sem mover o ponteiro, e isso agora acontece sozinho antes de escrever.

**Para apertar algo, o mouse é o último degrau**, nesta ordem:

| grau | o que faz | precisa de mouse? | confere? |
|---|---|---|---|
| 1 | ação padrão do elemento (`accDoDefaultAction`) | não | não |
| 2 | foco no elemento e teclado (`accSelect`) | não | sim, lê de volta |
| 3 | foco no campo inteiro e teclado | não | sim |
| 4 | `put_accValue` no valor do campo | não | sim |
| 5 | **clique físico no centro medido** (`--mouse`) | **sim** | sim |

O degrau 5 existe desde a 0.89.3, com o nome certo: `clicar_fisico`. Ele só
entra quando pedido (`--mouse`), porque:

- mover o ponteiro mexe na máquina de quem está usando;
- a tela deste PC dá **toque fantasma** — o ponteiro pode ser levado embora
  entre o `mover` e o `clicar`;
- clique errado numa tela que a pessoa está usando pode apagar trabalho.

E a coordenada nunca é inventada: é o **centro da caixa que a leitura mediu**
(`caixa[0] + caixa[2] // 2`). Sem caixa medida, ele não clica — diz que não tem
posição.

## A janela minimizada publica 12 elementos (0.89.2)

Depois da 0.89.1, o usuário viu:

```
NÃO DEU: a janela do Bloco de notas está aberta, mas em 15s ela não publicou
nenhum lugar de escrever. ... 12 de 12 elemento(s) vieram com coordenada
```

Doze elementos, todos de moldura. Esse número tem nome: **janela minimizada**.
Na barra de tarefas o Windows só descreve a moldura — o campo não existe para a
leitura enquanto a janela está recolhida. Some-se a isso um Bloco de Notas
antigo, aberto desde as tentativas anteriores, e o JARVIS tinha duas janelas
do mesmo programa: uma recolhida, uma servindo, e nenhuma informação para
saber qual era qual.

Quatro correções:

1. **`pid` na lista de janelas.** Cada janela passa a dizer de que processo
   veio. Quando o JARVIS abre o programa, ele guarda o `pid` do processo que
   acabou de nascer e só aceita janela daquele `pid` — é a janela que ele
   abriu, não a antiga.
2. **`minimizada` na lista.** `IsIconic` é perguntado direto ao Windows. A
   escolha põe as abertas antes das recolhidas, em vez de pegar a primeira.
3. **Restaurar em vez de pedir clique.** Janela recolhida é restaurada com
   `ShowWindow(SW_RESTORE)` — sem mouse, sem coordenada, sem pedir nada a
   ninguém. Depois disso a leitura acha o campo.
4. **O erro mostra o retrato.** Em vez de “não achei lugar para escrever”, ele
   lista cada janela do programa: título, se está minimizada, quantos elementos
   e se tem campo.

E a sonda ganhou um diagnóstico direto:

```
.venv\Scripts\python arvore_sonda.py --programa "bloco de notas"
```

```
  Bloco de notas (notepad.exe) — 2 janela(s):
    Sem título - Bloco de notas  —  49 elemento(s), tem campo @f14b5235:e11
    velho - Bloco de notas  —  minimizada, 12 elemento(s), sem campo

  1 aceita(m) escrita. Uma delas é a que o JARVIS usa.
```

## A janela que não era a janela (0.89.1)

A primeira tentativa real de `--programa` morreu assim:

```
NÃO DEU: não achei lugar para escrever nesta janela. a janela publicou só
moldura (barra de título, rolagem, botões de janela)... 12 de 12 elemento(s)
vieram com coordenada
```

Não era o Bloco de Notas. Havia **duas janelas `notepad.exe`** vivas — uma que
publica o campo e outra que publica só moldura — e o código pegava a
**primeira da lista**. Depois, para agir, **escolhia de novo** pela regra de
peso, podendo cair na outra. Escolher duas vezes é escolher errado uma vez.

Três correções:

1. **Quem acha, decide.** `ditar` passa o `handle` da janela que achou; a ação
   não escolhe outra. Janela que sumiu no meio vira erro claro, não sorteio.
2. **Várias janelas, uma serve.** Com mais de uma candidata, uma leitura em
   cada uma descobre qual publica campo antes de esperar 15 s na errada. E
   `escrever_na_janela` sem `handle` também tenta as outras janelas do mesmo
   processo antes de desistir.
3. **Esperar o campo, não a janela.** A janela do programa aparece antes de o
   campo existir. Reler até o campo nascer (até 15 s) evita dizer “esta janela
   não aceita escrita” meio segundo antes de ela aceitar.

O erro final agora repete o que a janela respondeu, em vez de só dizer “não
deu”.

## Do zero: abrir, esperar, escrever e conferir (0.89.0)

Até aqui o JARVIS escrevia numa janela **que já estava aberta**. Quem abria o
Bloco de Notas era você — e pedir isso é pedir trabalho a quem pediu que ele
fizesse o trabalho.

A 0.89.0 junta as duas peças que já existiam:

1. `pc.abrir_programa` — lista fechada (bloco de notas, paint, calculadora,
   cmd, powershell…), sem caminho livre;
2. `mesa_agir.escrever_na_janela` — acha o campo, escreve, confere.

E acrescenta o que faltava: **esperar a janela aparecer**. Abrir um programa e
ler a tela no mesmo instante é ler o vazio.

```
.venv\Scripts\python arvore_sonda.py --programa "bloco de notas" --escrever "oi, mundo" --executar
```

```
  Abri o Bloco de notas. Feito: digitar 'oi, mundo' em texto em 476,472 (970x69) (conferi: o texto está no campo)

  janela:  notepad.exe — Sem título - Bloco de notas
  alvo:    @da9f5b32:e11  texto “”
  onde:    476,472 (970x69)
  fonte:   msaa   leitura: da9f5b32
  como:    valor do campo (put_accValue, sem teclado)
  conferi: o texto está no campo.
```

Se o programa já estiver aberto, ele usa a janela que existe e **não abre uma
segunda**. Se a janela não aparecer em 12 segundos, ele diz isso e para — não
fica esperando para sempre diante de uma tela parada.

### O que continua valendo

- **sem `--executar`, nada é aberto e nada é escrito** — abrir programa já é
  agir, e o plano diz o que faria;
- a lista de programas é fechada; o executável vem dela, nunca de um caminho
  digitado;
- **pela API**, `mesa.ditar` exige `JARVIS_HOST_PC=1` (quem chama é o modelo).
  Na sonda, quem autoriza é a linha que a pessoa digitou;
- nada de mouse, nada de foto da tela, e a leitura de volta sempre.

## Escreveu de verdade — pelo terceiro degrau (0.88.0)

Na máquina do usuário, a 0.87.1 escreveu:

```
  Feito: digitar 'oi, mundo' em texto em 378,542 (970x69) (conferi: o texto está no campo)
  como:    valor do campo (put_accValue, sem teclado)
  conferi: o texto está no campo.
```

O `oi, mundo` estava no Bloco de Notas. Mas o caminho vencedor foi o
**terceiro**: `put_accValue`. Nem `accSelect` no elemento, nem no campo inteiro,
deram foco neste Bloco de Notas — e o JARVIS não digitou às cegas: escreveu
direto no valor e **conferiu lendo de volta**.

Isso também explica por que a 0.86.0 falhava: não era o programa recusando
foco, era o índice trocado; mas mesmo com o índice certo o foco não vem neste
controle. Quem depende de teclado teria ficado sem escrever.

### O problema que aparece na segunda vez

`put_accValue` **substitui** o conteúdo. Na primeira vez o campo estava vazio.
Na segunda, ele já tem `oi, mundo` — e escrever por cima apagaria o que já
estava lá.

Antes, o JARVIS recusava: *"o campo já tem texto e eu não sobrescrevo o que não
escrevi"*. Recusar está certo, mas não resolve — a pessoa quer continuar
escrevendo.

Agora ele lê o que existe e escreve `o que existe + o novo`, e diz o que fez:

```
  Feito: digitar ' de novo' em texto em ... (conferi: o texto está no campo)
  como:    valor do campo, acrescentado ao que já havia
```

Isso só acontece com `--acrescentar`. Sem a opção, continua recusando — porque
**acrescentar por conta própria mudaria o significado do que está escrito**, e
isso é decisão de quem escreveu, não minha.

## O foco que nunca foi pedido (0.87.1)

Na primeira tentativa de verdade, a tela do usuário disse:

```
Não foi feito: digitar 'oi, mundo' em texto em 339,298 (970x69) — o elemento
recusou o foco (accSelect). Sem foco, digitar iria para outra janela — parei.
```

O Bloco de Notas não recusou nada. **O índice da vtable estava errado.**
`IAccessible` tem, depois dos métodos de `IDispatch`:

| índice | método |
|---|---|
| 20 | `get_accDefaultAction` |
| **21** | **`accSelect`** |
| 22 | `accLocation` |
| 23 | `accNavigate` |
| **25** | **`accDoDefaultAction`** |
| 27 | `put_accValue` |

A 0.86.0 usava **21** para `accDoDefaultAction` e **23** para `accSelect` — um
a mais, outro a menos. Ou seja: o "pedido de foco" chamava `accNavigate`, que
devolve `S_FALSE`, e o JARVIS contava isso como recusa do programa. Um erro de
diagnóstico apresentado como se fosse do Bloco de Notas.

### E a escrita agora tem três degraus

1. **foco no elemento exato** (`accSelect`) + teclado;
2. **foco no dono** — o campo inteiro, quando o texto é filho simples;
3. **`put_accValue`** — escreve no valor do campo, sem teclado e sem foco.

O teclado só é usado quando o Windows confirma que o foco está **dentro da
janela alvo** (`GetGUIThreadInfo` → `hwndFocus` → sobe pelos pais). Se não
está, ele não digita às cegas: dizer "digitei" e ter digitado noutro programa
seria pior do que não fazer nada.

E depois de digitar, ele **lê o campo de volta** e diz o que viu:

```
  Feito: digitar 'oi, mundo' em texto em 445,577 (970x140) (conferi: o texto está no campo)
```

`put_accValue` substitui o conteúdo, então só é usado quando o campo está
vazio — sobrescrever o que a pessoa escreveu para "dar certo" é destruir
trabalho.

## Escrever sem copiar ref nenhum (0.87.0)

A etapa 2 pediu um `ref`, e o usuário colou o marcador que eu tinha escrito:

```
--ref @SEU_REF_AQUI
```

A recusa funcionou (o ref não existia) — mas o erro era do comando: pedir para
copiar um código de uma saída para a linha seguinte é trabalho que não devia
existir. O JARVIS já sabe apontar onde se escreve.

Agora:

```
.venv\Scripts\python arvore_sonda.py --alvo "notepad.exe" --escrever "oi, mundo"
```

```
  Ação pronta (nada foi feito): digitar 'oi, mundo' em texto em 445,577 (970x140)

  janela:  notepad.exe — Sem título - Bloco de notas
  alvo:    @c7aa400c:e11  texto “”
  onde:    445,577 (970x140)

  repita o comando com --executar para fazer de verdade.
```

E com `--executar`, escreve. O `--ref` continua existindo para quem quer
apontar um elemento específico (clicar num botão, por exemplo) — mas para
escrever, ninguém precisa mais dele.

`mesa.agir` no chat ficou igual: `ref` em branco na ação digitar, e ele acha o
campo.

### O erro agora fala português

O erro do ref saía como `{"erro": "..."}` numa linha só. Quem lê no terminal
não merece JSON sem ter pedido:

```
  NÃO DEU: não achei lugar para escrever nesta janela. a janela publicou só
  moldura... Rode `--provados` para ver quais janelas aceitam escrita.
```

`--json` continua entregando o formato de máquina para quem é máquina.

## Etapa 2: agir por `ref` (0.86.0)

A leitura do Bloco de Notas entregou o alvo:

```
texto  @4ab283d9:e11  em 227,559 (970x140)  (escreve aqui)
Onde escrever: @4ab283d9:e11 em 227,559 (970x140)
```

Com um alvo que tem nome, posição e `ref`, o braço pode existir:

```
.venv\Scripts\python arvore_sonda.py --alvo "notepad.exe" --ref @4ab283d9:e11 --acao digitar --texto "oi"
```

```
  Ação pronta (nada foi feito): digitar 'oi' em texto em 227,559 (970x140)

  janela:  notepad.exe — Sem título - Bloco de notas
  alvo:    @4ab283d9:e11  texto “”
  onde:    227,559 (970x140)
  fonte:   msaa   leitura: 4ab283d9

  repita o comando com --executar para fazer de verdade.
```

Sem `--executar`, **nada é tocado**. Com ele:

```
  Feito: digitar 'oi' em texto em 227,559 (970x140)
  como:    foco + teclado
```

### A regra que manda em tudo: `ref` não sobrevive à leitura

`ref` não é o nome do elemento — é o número dele naquela leitura. A tela muda.
Por isso **todo `agir` relê a janela antes** e procura o ref na leitura nova:

```
o ref @antigo:e12 não existe nesta leitura — ele deve ser de uma leitura
anterior, e a tela já mudou. Refs válidos agora: @4ab283d9:e11, ...
```

Um `ref` velho nunca vira alvo por acaso. É a diferença entre um braço e um
chute.

### Sem mover o mouse

A ação vem do próprio elemento:

| ação | como |
|---|---|
| clicar | `accDoDefaultAction` — a ação que o programa declara |
| sem ação padrão | `accSelect(TAKEFOCUS)` — o mesmo que um clique faria |
| digitar | foco no elemento, depois teclado (Unicode) |
| recusa de foco | **para** e diz; digitar sem foco iria para outra janela |

Isso não é preferência estética: no seu PC a tela não responde a toque e não há
mouse USB. Clicar por coordenada seria o único caminho que não funciona ali.

### O que é recusado, e por quê

| pedido | resposta |
|---|---|
| `ref` de leitura anterior | recusa e lista os refs válidos agora |
| moldura (Fechar, Minimizar, rolagem) | recusa — não é trabalhar no programa |
| digitar em botão | recusa com a ação que o elemento aceita |
| digitar sem texto | recusa |
| agir sem `--executar` | mostra o plano e para |

### No chat

`mesa.agir` faz o mesmo pelo JARVIS, com `executar` explícito e confirmação.
A etapa 2 deixou de ser promessa: é a skill `mesa.agir`.

## Os 26 acionáveis eram moldura (0.85.0)

A leitura do Bloco de Notas, no PC do usuário:

```
notepad.exe — Sem título - Bloco de notas: 49 elemento(s), 26 acionável(is) — fonte: msaa.
  SERVE para agir: 49 elemento(s) de árvore, 26 acionável(is) e 26 com nome ou escrita.
```

26 acionáveis. E olhando a árvore, quais eram: **IME, Minimizar, Maximizar,
Fechar**, os botões das duas barras de rolagem e uma alça. Moldura inteira.

O campo onde se escreve aparecia assim:

```
texto  em 227,559 (970x140)
```

Sem `ref`. A MSAA não dá ação padrão a um campo de texto, e a minha tabela de
papéis acionáveis não incluía `texto`. Ou seja: **o JARVIS não tinha como
digitar no Bloco de Notas**, e a prontidão dizia “dá para agir”.

### Duas contas erradas, uma causa

1. **A prontidão contava botão de janela como ação.** 26 botões de moldura
   passavam no critério “existe acionável com nome”. Agora moldura é
   reconhecida — por papel (barra de título, rolagem, alça, status, indicador)
   e por nome (IME, Minimizar, Maximizar, Fechar, “uma linha acima”…) — e
   **contamina os filhos**: os botões dentro da barra de título são moldura
   mesmo que o papel deles seja “botão”.

2. **O lugar de escrever não era acionável.** Papel `texto` (42) e `documento`
   (15) com caixa na tela passam a receber a ação **digitar** — e portanto um
   `ref`. Só quando a janela deixa: `get_accState` é consultado e
   `STATE_SYSTEM_READONLY` recusa. Um painel de log também é “texto”, e
   prometer escrita ali seria mentira.

A leitura do Bloco de Notas agora sai assim:

```
notepad.exe — Sem título - Bloco de notas: 49 elemento(s), 26 acionável(is) — fonte: msaa.
Todos os acionáveis são moldura (fechar/minimizar/rolagem); o lugar de escrever é @7625b028:e10.

  SERVE para agir: 49 elemento(s) de árvore, 1 onde se escreve — dá para agir por `ref`.
  Onde escrever: @7625b028:e10 em 227,559 (970x140)

  texto  @7625b028:e10  em 227,559 (970x140)  (escreve aqui)
```

E `--provados` diz onde cada janela aceita escrita:

```
  - notepad.exe — Sem título - Bloco de notas — escreve em 227,559
```

## O Chrome acordou (0.84.0)

A medição que virou o quadro, no PC do usuário, dois comandos seguidos sem
tocar em nada:

```
1ª rodada:  chrome.exe   Arena | Benchmar     3     3  nao   nao   uia  1.0
2ª rodada:  chrome.exe   Arena | Benchmar   104   104  sim   SIM   uia  0.9
```

A mesma janela. **3 elementos sem conteúdo** e, no comando seguinte, **104 com
conteúdo**. A diferença não foi código: foi o **Chrome ligando a
acessibilidade** ao perceber que alguém estava lendo.

É o comportamento conhecido dos navegadores: a árvore da página é construída
sob demanda, quando um programa de acessibilidade aparece. A primeira leitura
é o que acende a luz; ela chega antes de a luz acender.

### O erro que isso revelou — e que era meu

Eu li **uma vez** e concluí “não publica”. Era o primeiro estado, não o único.
Foi por isso que encerrei o Chrome na 0.83.0, com toda a convicção e errado.
Uma leitura não é uma medição quando o objeto muda de estado ao ser tocado.

### O que mudou

- `ler_janela` relê **uma vez**, 0,4 s depois, quando a primeira leitura vem
  sem conteúdo. Se a segunda trouxer conteúdo (ou mais elementos), ela vence e
  o resultado diz por quê:

  ```
  A janela só publicou o conteúdo na segunda leitura — é o caso do navegador,
  que liga a acessibilidade quando percebe alguém lendo.
  ```

- Janela que já vem com conteúdo **não paga** a segunda passada.
- `--provados` avisa quais acordaram, para ninguém achar que precisa rodar
  duas vezes:

  ```
  Acordaram na segunda leitura (o navegador liga a acessibilidade quando
  percebe alguém lendo — já vem lido, não precisa repetir):
    - chrome.exe — Arena | Benchmark & Compare the Best AI Mode
  ```

## Onde ele enxerga, e onde para (0.83.1)

Pergunta justa depois do veredito: **“mas ele não está reconhecendo onde fica
cada coisa?”** — sim, para a moldura. E a resposta nunca esteve na tela, o que
é um defeito meu: a posição era medida (`caixa`: x, y, largura, altura) e o
desenho não a mostrava.

Agora mostra:

```
janela “Chrome”  em 0,0 (1200x800)
  botão “Fechar”  @568600ab:e2  em 1180,5 (30x20)
  botão “Minimizar”  @568600ab:e3  em 1140,5 (30x20)
```

E a diferença fica escrita, não deduzida:

| o que | ele sabe? |
|---|---|
| a janela existe, e onde ela está na tela | **sim** — coordenada |
| barra de título, minimizar, fechar, rolagem | **sim** — nome, ação e coordenada |
| o que está **dentro** da página | **não** — o Chrome não publica |

`--provados` ganhou a coluna `posicoes`:

```
  janela aberta                    elementos  posicoes  conteudo  serve?  fonte  seg
  --------------------------------------------------------------------------------------
  chrome.exe     Arena | Benchmar         4         4  nao       nao     uia    1.2
  explorer.exe   Downloads               88        88  sim       SIM     msaa   0.9
```

`posicoes` alto com `conteudo` baixo quer dizer exatamente isto: **ele vê as
peças e onde estão; não vê o que elas são.** Moldura tem posição e não serve
para trabalhar; conteúdo é o que serve.

Isso também corrige uma coisa que eu disse rápido demais. “O Chrome não
publica” é impreciso. O mais provável é que o Chrome só ligue a árvore da
página quando percebe um programa de acessibilidade, e aqui ela tenha ficado
desligada. É ajuste do Chrome, não do JARVIS — e não é algo que eu vá pedir
para você fazer à mão.

## O veredito do Chrome (0.83.0)

A 0.82.6 mediu a janela certa. A resposta:

```
  medindo: chrome.exe — Arena | Benchmark & Compare the Best AI Models - Google Chro
  classe:  Chrome_WidgetWin_1

  janela                            msaa   uia   conteudo  processo
  ------------------------------------------------------------------------
  Chrome_WidgetWin_1                   4     4   nenhum   chrome.exe
    Chrome_RenderWidgetHostHWND        1     1   nenhum   chrome.exe
    Chrome_RenderWidgetHostHWND        1     1   nenhum   chrome.exe

  VEREDITO: 4 elemento(s), nenhum de conteudo (fonte uia).
```

Duas janelas filhas `Chrome_RenderWidgetHostHWND`, **1 elemento cada**, sem
conteúdo. A página não é publicada — nem pela MSAA, nem pela UIAutomation.

**Está encerrado o Chrome neste PC.** Era a promessa, e ela vale: não peço
outra rodada, não mudo a pergunta, não há uma sétima tentativa.

> **Correção (0.84.0):** estava errado. O Chrome publica a página sim — ele
> liga a acessibilidade quando percebe alguém lendo, e a primeira leitura
> pegou o estado antes disso. Ver “O Chrome acordou”, acima. A promessa de não
> insistir continua; o que mudou é que agora não há por que insistir: funciona.

O que isso significa na prática: neste `Windows 10.0.14393`, este Chrome não
expõe o conteúdo da página para um leitor de acessibilidade. O JARVIS não vai
adivinhar o que está na tela — sem foto, sem OCR, sem clique às cegas. Ler o
Chrome **aqui** não é um problema de código meu que mais uma versão resolve.

### O que ficou de aprendizado, e virou código

**1. Número não é resposta.** “47 elementos” manteve a etapa 2 parada por seis
versões, porque os 47 eram moldura. Agora toda leitura termina com a pergunta
que importa:

```
  NAO SERVE para agir: a janela publicou só moldura (barra de título,
  rolagem, botões de janela). Esta é a mesma parede que o Chrome deu neste PC.
```

**2. Não perguntar uma janela por vez.** Seis mensagens suas foram gastas
medindo um programa por vez. Agora existe um comando que mede **todas as
janelas abertas** de uma vez e responde onde dá para trabalhar:

```
.venv\Scripts\python arvore_sonda.py --provados
```

```
  janela aberta                        elementos  conteudo  serve?  fonte  seg
  ------------------------------------------------------------------------------
  notepad.exe        Sem título - B...       31  sim        SIM     uia   0.4
  explorer.exe       Downloads               88  sim        SIM     msaa  0.9
  chrome.exe         Arena | Benchmar...      4  nao        nao     uia   1.2

  2 de 3 janela(s) servem para o JARVIS agir:
    - notepad.exe — Sem título - Bloco de notas
    - explorer.exe — Downloads
```

**3. A ordem da medição importa.** Na 0.82.6 a coluna da MSAA do Chrome saiu
com 4, quando a leitura da 0.82.4 tinha achado 47 na mesma janela — a diferença
era a UIA já ter aberto a janela antes da medição. O diagnóstico agora mede a
MSAA **primeiro**, e o veredito é a leitura de verdade (`ler_janela`), não uma
segunda implementação dela.

**4. A conta da prontidão é explícita.** `arvore.prontidao()` responde com
números: total, acionáveis, com nome, editáveis, e um motivo em português. Ela
recusa moldura mesmo com 600 botões, e aceita o campo do Bloco de Notas, que
não tem nome nenhum — porque é onde se escreve.

## A sexta medição: a tabela mediu o terminal (0.82.6)

A 0.82.5 pediu uma tabela e ela veio assim:

```
  [FALHA] varredura de janelas (1)
  janela                                  msaa  uia   conteudo
  ConsoleWindowClass                         1    12   nenhum
```

`ConsoleWindowClass` é o **terminal**. O comando pedia o Chrome.

**O defeito era meu, não do Chrome.** `diagnostico()` não recebia o handle:
ignorava o `--alvo` e media sempre a janela em foco. A 0.82.3 tinha corrigido
exatamente isso na leitura normal e deixou o diagnóstico de fora — o mesmo erro,
no outro caminho. A tabela que devia decidir a etapa 2 estava olhando para a
janela errada.

### O que mudou

1. **O diagnóstico escolhe como a leitura escolhe.** A sonda usa o mesmo
   `_escolher`/`arvore.escolher_janela` e passa o **handle** para
   `diagnostico(alvo, handle=…)`. Não há segunda escolha para divergir.
2. **A tabela diz qual janela está medindo**, com processo e classe, antes de
   qualquer número:

   ```
   medindo: chrome.exe — Arena | Benchmark...
   classe:  Chrome_WidgetWin_1
   ```

3. **A MSAA também desce as filhas.** A 0.82.5 varria as filhas só na UIA. O
   Chrome publica a página pela MSAA da filha em várias versões; agora
   `varrer_msaa` percorre até 24 filhas, conteúdo primeiro, com a mesma regra
   de `escolher_fonte`.
4. **Há um veredito, e ele é medido como a leitura mede.** A tabela mostra cada
   janela isolada; a leitura agrega. No fim:

   ```
   VEREDITO: a leitura vai funcionar — 812 elemento(s) de conteudo, fonte uia.
   lido de dentro de: Chrome_RenderWidgetHostHWND
   ```
   ou `VEREDITO: 12 elemento(s), nenhum de conteudo (fonte uia).` — sem deixar a
   interpretação para você.
5. **A coluna `processo`** existe para o engano não se repetir: se a linha não
   diz `chrome.exe`, a janela não é o Chrome.

### O critério continua o mesmo

Se, **medindo a janela certa**, a tabela do Chrome disser `nenhum` em todas as
linhas e o veredito não tiver conteúdo, eu encerro a leitura do Chrome neste PC.
Sem nova rodada, sem nova tentativa: sigo com Explorer, Bloco de Notas e
instaladores, que publicam árvore clássica — e a etapa 2 (clique por `ref`) é
medida neles.

## A quinta medição: moldura não é conteúdo (0.82.5)

A 0.82.4 matou a repetição — **600 para 47 elementos**. Mas o número novo
denunciou outra coisa:

```
chrome.exe — Arena | Benchmark...: 47 elemento(s), 26 acionável(is) — fonte: msaa.
a UIAutomation mostrou 4; a MSAA mostrou mais (47).
```

Os 47 eram **todos moldura**: barra de título, barra de rolagem, “alça”.
Nenhum item da página. E a regra “ganha quem mostrou mais” premiava exatamente
a leitura sem conteúdo — 47 pedaços de moldura venciam 4 elementos de página.

Três correções:

### 1. Conteúdo vence moldura

A escolha entre fontes parou de contar elementos e passou a perguntar **o que**
eles são. Papéis de conteúdo — link, texto, item de lista, célula, documento —
valem mais do que qualquer quantidade de botão de janela.

| situação | quem ganha |
|---|---|
| uma tem conteúdo, a outra só moldura | a que tem conteúdo |
| navegador (Chrome, Edge, Firefox…) | UIAutomation, mesmo com menos nós |
| nenhuma tem conteúdo | quem mostrou mais (regra antiga) |

### 2. A página mora numa janela **filha**

A página do Chrome não é um elemento da janela principal: é a janela filha
`Chrome_RenderWidgetHostHWND` — outro processo. Ler só a janela de topo dá a
moldura; é por isso que a UIA “mostrava 4”.

Agora a leitura varre as janelas filhas (até 24), começando pelas classes que
carregam conteúdo, e fica com a que tiver mais nós. O resumo diz de onde veio:

```
(lido de dentro: Chrome_RenderWidgetHostHWND)
```

### 3. O diagnóstico passou a medir isso

`--diagnostico` agora mostra uma tabela por janela e por fonte:

```
  janela                                  msaa  uia   conteudo
  --------------------------------------------------------------
  Chrome_WidgetWin_1                        47     4   nenhum
    Chrome_RenderWidgetHostHWND              0   812   uia
```

Essa tabela é a resposta definitiva. Se a linha indentada mostrar `uia` com
conteúdo, a leitura funciona. Se mostrar `nenhum` em tudo, o Windows 10 do seu
PC não expõe a página — e aí eu paro, em vez de te fazer rodar de novo.

## A quarta medição: a causa raiz (0.82.4)

`--alvo chrome` passou a achar o Chrome. Mas a árvore continuou repetindo — e
agora dava para ver **o quê** repetia:

```
barra de rolagem “Vertical”
  botão “Uma linha acima”
    botão “Uma linha acima”
      botão “Uma página acima”
        botão “Uma linha acima” ...
```

Não era a moldura da janela. Era a **barra de rolagem**. E a causa não era o
Chrome — era uma linha minha:

```python
usar = ponteiro_filho or ponteiro      # <- o defeito
```

A MSAA tem dois tipos de filho:

| tipo | o que é | tem filhos? |
|---|---|---|
| **objeto** (VT_DISPATCH) | um objeto COM de verdade, com ponteiro próprio | sim |
| **simples** (VT_I4) | só um número de identificação dentro do pai | **não** |

Para um filho simples, `get_accChildCount` **no pai** devolve os filhos *do
pai*. Ao reusar o ponteiro do pai, eu pedia ao pai que listasse os próprios
filhos — de novo, e de novo, até acabar o limite. Cada “botão Uma linha acima”
era o mesmo botão, lido repetidamente.

O certo: **elemento simples entra na árvore (nome e papel são lidos dele), mas
não se desce nele.** Uma linha.

Junto com isso, a montagem ganhou a mesma guarda em segundo lugar: mesmo que a
sonda devolva árvore repetida (versão antiga, programa estranho), o `montar`
corta antes de chegar ao chat. E a distinção passou a ser explícita:

- **moldura** (Minimizar, Fechar, IME): o nó é real, entra e para ali;
- **repetição** (o mesmo nó dentro de si mesmo): não é nó novo, **não entra**.

Por fim: navegador (Chrome, Edge, Firefox, VS Code, Slack, Discord…) agora
**sempre** tenta a UIAutomation, mesmo que a MSAA venha grande. No seu PC a
MSAA do Chrome devolveu 600 elementos de barra de rolagem e **zero** da página.

## A terceira medição no seu PC (0.82.3)

A 0.82.2 consertou os índices da UIAutomation — e isso **funcionou**:

```
D:\JARVIS>.venv\Scripts\python arvore_sonda.py --alvo chrome --diagnostico
  [ok  ] CoInitializeEx(MTA)                0x00000000
  [ok  ] CoCreateInstance(IUIAutomation)    0x00000000  objeto criado
  [ok  ] get_ControlViewWalker (índice 14)  0x00000000
  [ok  ] ElementFromHandle (índice 6)       0x00000000
  [ok  ] get_CurrentControlType             0x00000000  tipo=50032
```

E a leitura pela UIA trouxe conteúdo de verdade onde a MSAA trazia a moldura:

```
--alvo chrome: 12 elemento(s), 7 acionável(is) — fonte: uia
  barra de rolagem “Vertical”
    botão “Uma linha acima”  @93d11915:e3
    botão “Uma página acima”  @93d11915:e4
    elevador “Posição”
```

**Mas `--alvo chrome` leu o terminal, não o Chrome.** O motivo está no título
daquela janela:

```
cmd.exe — C:\Windows\system32\cmd.exe - .venv\Scripts\python arvore_sonda.py --alvo chrome
```

A busca procurava **primeiro no título**, e o título do `cmd` é a linha de
comando — que contém a palavra “chrome”. A janela que roda a sonda é a **única**
que sempre carrega o pedido escrito nela. Era o pior lugar possível para
começar a busca.

Agora:

1. a janela que roda a sonda **nunca** é candidata;
2. **processo vence título**: `chrome` casa com `chrome.exe` (nota 0) antes de
   casar com qualquer título que mencione a palavra (nota 3);
3. quando nada casa, a mensagem lista só janelas de programas de verdade.

## A segunda medição no seu PC (0.82.2)

Depois da 0.82.1 você rodou de novo, agora com o Chrome aberto:

```
chrome.exe — Arena | Benchmark...: 600 elemento(s), 596 acionável(is) — fonte: msaa.
botão “IME” → botão “IME” → botão “IME” → ...
botão “Minimizar” → botão “Minimizar” → ...
```

```
D:\JARVIS>.venv\Scripts\python arvore_sonda.py --fonte uia
o foco estava neste terminal; li “Iniciar” (explorer.exe) em vez dele.
a UIAutomation não devolveu árvore para esta janela.
```

Eram **três defeitos meus**, e nenhum do seu PC:

1. **A árvore se repetia dentro de si mesma.** O Chrome expõe a moldura da
   janela *dentro* da janela: cada botão de moldura devolve os cinco botões de
   novo. Sem guarda, os 600 elementos acabaram antes de chegar ao conteúdo da
   página — 596 “botões” que não existem. Agora **moldura é folha** (não se desce
   em Minimizar/Maximizar/Fechar/IME) e **quem repete um ancestral para**.
2. **Os índices da UIAutomation estavam todos +3.** A vtable começa em
   `CompareElements`, mas QueryInterface/AddRef/Release ocupam as posições 0, 1
   e 2 — eu tinha esquecido. Na prática, `ElementFromHandle` chamava
   `GetRootElementBuildCache`. Corrigido e **preso por teste**.
3. **A troca de janela pegou o menu Iniciar.** “Iniciar” é do Windows, não é um
   programa seu. Agora a lista de janelas de sistema (menu Iniciar, barra,
   área de trabalho) fica de fora da escolha.

E o que faltava para não errar de novo em silêncio: `--diagnostico`, que mostra o
retorno de **cada** passo do COM, em hexadecimal.

```
.venv\Scripts\python arvore_sonda.py --diagnostico
```

## A primeira medição no seu PC (0.82.1)

Você rodou isto no `cmd` e recebeu, três vezes:

```
D:\JARVIS>.venv\Scripts\python arvore_sonda.py
cmd.exe — C:\Windows\system32\cmd.exe - ...: 1 elemento(s), 0 acionável(is) — fonte: msaa.
área do cliente “C:\Windows\system32\cmd.exe - ...”
```

**Duas coisas estavam erradas, e nenhuma era o seu PC:**

1. **A sonda leu a si mesma.** O comando roda *dentro* de um `cmd.exe`, e a
   janela em foco era esse `cmd`. Você queria ver o programa aberto **atrás**.
   Agora, quando o foco é o terminal que roda a sonda, ela pega a janela anterior
   e **diz que trocou** (`o foco estava neste terminal; li “...” em vez dele`).
2. **O console não publica botões pela MSAA.** A MSAA é de 1996 e o `cmd` só
   expõe a moldura. O Windows tem uma **segunda** árvore, a **UIAutomation**, que
   é a mesma que o Narrador usa — e é nela que os programas de hoje publicam
   (Bloco de Notas do Windows 11, apps WinUI, boa parte do Chrome).

Por isso a leitura agora **tenta as duas** e fica com a que mostrou mais
elementos. Numa janela rica ela não paga a segunda leitura: o tempo de espera
seria seu.

E quando a árvore vem quase vazia, aparece a **dica** em vez de silêncio — o
resumo diz *por que* e *o que fazer* (trocar de janela, usar `--alvo`).

## O que é a árvore de acessibilidade

Todo programa no Windows é obrigado (por acessibilidade) a dizer quais elementos
tem: “aqui há um botão chamado Salvar, nesta posição, e clicar nele faz X”. É o
mesmo canal que o **Narrador** e o **NVDA** usam.

São **duas** portas para a mesma ideia, e o JARVIS usa as duas:

| fonte | biblioteca | quem publica |
|---|---|---|
| **MSAA** | `oleacc.dll` | programas clássicos (Win32, MFC, VB6, muito do Chrome) |
| **UIAutomation** | `uiautomationcore.dll` | programas atuais (WinUI, WPF, Bloco de Notas novo, Explorer) |

As duas via `ctypes` puro — **sem instalar nada**. E as duas só leem: `get_*`,
`accessLocation`, `GetFirstChildElement`, `GetCurrentPattern` (este último só
para **perguntar** se o elemento aceita ação).

```
janela “Cadastro de cliente”
  painel
    botão “Salvar”              @a1b2c3d4:e3
    botão “Cancelar”            @a1b2c3d4:e4
    texto “Nome completo”
    caixa de seleção “Aceito os termos”  @a1b2c3d4:e6
  barra de ferramentas
    item de menu “Arquivo”      @a1b2c3d4:e8
```

O `ref` (`@a1b2c3d4:e3`) só vai para o que **dá para acionar**, e carrega o id da
leitura: se a tela mudar, o `ref` antigo deixa de valer — é assim que se evita
clicar no botão errado depois de uma atualização da janela.

## Como usar

No chat:

```
vê os elementos da janela
lê a janela do chrome
o que dá para clicar no bloco de notas
```

Ou direto no terminal do PC (não precisa do JARVIS aberto):

```
.venv\Scripts\python arvore_sonda.py
.venv\Scripts\python arvore_sonda.py --janelas
.venv\Scripts\python arvore_sonda.py --alvo chrome --profundidade 8
.venv\Scripts\python arvore_sonda.py --json --limite 200
```

## O que ele garante

| garantia | como |
|---|---|
| **só leitura** | o módulo não tem função de clicar, digitar ou mover — há teste que falha se alguém acrescentar |
| **sem foto da tela** | não usa `screenshot`, não lê pixel, não faz OCR |
| **não derruba a API** | a leitura roda em `arvore_sonda.py`, processo separado, com tempo limite |
| **não trava** | profundidade (máx. 14), total de elementos (máx. 3.000) e tempo (25 s) limitados |
| **não finge** | corte vira `completo: false` com o motivo; papel desconhecido vira `elemento 999`; janela sem árvore vem com aviso |
| **fora do Windows** | recusa com frase clara, em vez de devolver vazio |
| **duas fontes** | MSAA e UIAutomation; quem decide é a que mostrou mais elementos |
| **não lê a si mesma** | se o foco é o terminal que roda a sonda, ela pega a janela de trás e avisa |
| **não entra em laço** | moldura é folha e nó que repete um ancestral para — o Chrome já provou que sem isso a leitura vira 600 botões falsos |
| **não escolhe o Windows** | menu Iniciar, barra de tarefas e área de trabalho ficam fora da lista de janelas |
| **não escolhe a si mesma nem por engano** | a janela que roda a sonda é excluída, e processo vence título — `--alvo chrome` acha o Chrome |
| **não repete o mesmo elemento** | filho “simples” da MSAA não desce (era a causa de 600 botões falsos), e a montagem corta repetição de qualquer origem |
| **navegador vai direto na UIA** | Chrome/Edge/Firefox/VS Code publicam a página pela UIAutomation, não pela MSAA |
| **conteúdo vence moldura** | 47 botões de janela não valem mais do que 3 elementos de página |
| **lê as janelas filhas** | a página do navegador é uma janela filha (`Chrome_RenderWidgetHostHWND`), não um elemento da janela de topo |
| **falha com endereço** | `--diagnostico` mostra o retorno de cada passo do COM, não só “não devolveu” |
| **mede a janela certa** | o diagnóstico recebe o handle já escolhido — `--alvo chrome` não mede mais o terminal |
| **diz se serve para agir** | toda leitura termina com serve/não serve e o motivo; `mesa.arvore` devolve `pronto` |
| **mostra onde fica** | cada elemento sai com `em x,y (largura x altura)`; `--provados` tem a coluna `posicoes` |
| **não desiste na primeira** | janela que responde só moldura é relida uma vez, 0,4 s depois — navegador acorda ao ser lido |
| **não confunde moldura com trabalho** | botão de janela, rolagem e alça ficam de fora da conta de “dá para agir” |
| **sabe onde se escreve** | papel `texto`/`documento` com caixa ganha ação `digitar` e `ref`, salvo se for somente leitura |
| **age por `ref`, com freio** | relê antes de agir; ref antigo, moldura e digitar sem texto são recusados; `--executar` é obrigatório |
| **acha o campo sozinho** | `--escrever "texto"` — sem copiar ref de uma saída para outra |
| **acrescenta sem apagar** | `--acrescentar`: campo com texto ganha o novo no fim, não por cima |
| **abre o programa sozinho** | `--programa "bloco de notas"`: abre se não estiver aberto, espera a janela e escreve |
| **chega na janela sem mouse** | `SetForegroundWindow` antes de agir |
| **mouse como último recurso** | `--mouse`: clique físico no centro medido, só se a ação e o foco falharem |
| **não move o mouse** | a ação vem do elemento (ação padrão / foco), que é o único caminho que funciona na sua tela |
| **mede todas as janelas de uma vez** | `--provados` varre o que está aberto, com teto de 60 s, e diz onde dá para trabalhar |
| **mede na ordem da leitura** | MSAA antes de a UIA tocar na mesma janela; o veredito é a própria `ler_janela` |
| **diz o que mediu** | a tabela abre com processo e classe da janela, e fecha com veredito medido como a leitura mede |
| **varre as filhas nas duas fontes** | MSAA e UIA descem até 24 janelas filhas, conteúdo primeiro |

## O que **não** faz (ainda) e por quê

- **Clicar por `ref`** é a **etapa 2**. Ela só entra depois que você rodar isto no
  seu PC e me disser o que apareceu — porque o que decide é **quais programas
  publicam árvore**. Chrome, WhatsApp Desktop e Explorer se comportam de formas
  diferentes, e prometer clique sem essa medição seria repetir o erro das
  versões anteriores.
- **Ver a tela por imagem.** Se um programa não publica árvore (jogo, instalador
  antigo), o JARVIS não vê. Isso é limite do programa, não do JARVIS — e está
  dito em vez de escondido.

## O teste que você mesmo pode fazer

1. abra **o Bloco de Notas** e clique nele;
2. no terminal do PC:

```
cd /d D:\JARVIS
.venv\Scripts\python arvore_sonda.py
```

3. me diga o que apareceu (ou mande o `--json`).

Para saber **em quais programas** dá para trabalhar, sem tentativa e erro:

```
.venv\Scripts\python arvore_sonda.py --provados
```

Se alguma coisa vier estranha, o primeiro comando é sempre:

```
.venv\Scripts\python arvore_sonda.py --diagnostico
```

Quer comparar as duas fontes na mesma janela? Rode uma vez com `--fonte msaa` e
outra com `--fonte uia`. O número de elementos de cada uma é a resposta crua —
e é ela que eu uso para decidir a etapa 2, não um palpite meu.

Se o Bloco de Notas publicar árvore (deve publicar), a etapa 2 fica viável para
programas clássicos. Depois repetimos com o **Chrome** e com o **WhatsApp** —
esses são os que decidem se vale a pena.

## Detalhe técnico: por que a sonda é um processo separado

A leitura conversa por COM com **código de outra pessoa** (o programa que você
tem aberto). Um aplicativo malcomportado pode travar a chamada ou derrubar o
processo inteiro. Derrubar uma sonda descartável é aceitável; derrubar o JARVIS
no meio de uma conversa não é. É o mesmo princípio do `conferir-versao.bat`: o
diagnóstico não pode ser perigoso.

### 0.92.2 — “anatomia do aparelho”: ler sem mudar

> tem como pedir para uma IA… fazer uma varredura ou uma engenharia reversa —
> não para modificar, mas para entender todos os componentes do dispositivo e
> arquivos, igual a anatomia humana

> ou se eu quiser conectar por exemplo uma tv antiga q pega wifi tipo uma tcl

> Roku TV

O dono colou uma conversa inteira de outro assistente e, no fim, a pergunta que
importava: **o JARVIS consegue?** A resposta virou módulo (`server/anatomia.py`),
rota (`/api/anatomia/*`) e tela (menu **Anatomia**), com três alvos e uma regra
só — **ler não é mexer**.

- **`local`** — CPU, memória, discos, GPU e temperatura, cada número com a
  **fonte** (`/proc`, registro do Windows, `nvidia-smi`, `psutil`,
  `/sys/class/thermal`, WMI). Quando não há sensor, a resposta é “não exposta”
  **com o motivo**, nunca um zero decorativo. No Windows comum, a temperatura
  muitas vezes não existe: o módulo diz isso em vez de fingir.
- **`android`** — `adb` já existia na aba Máquina; aqui ele recebe só `shell`
  de leitura: `getprop`, `dumpsys battery`, `/proc/*`, `df`, `pm list packages`
  e `/sys/class/thermal`. Nada de `install`, `push`, `pull`, `reboot` ou `su` —
  e há teste que varre a lista de comandos para garantir isso.
- **`roku`** — ECP na porta 8060: `/query/device-info`, `/query/apps`,
  `/query/active-app`. **Só GET**: `POST /keypress` mudaria a TV, e o pedido
  era entender, não apertar botão.

Três correções ao que a conversa colada prometia:

1. **“varredura automática ao plugar o cabo”** não existe: a Depuração USB e o
   “Permitir” na tela são consentimento de uma pessoa, uma vez por computador.
2. **temperatura sem root** depende do aparelho; muitos Androids escondem
   `/sys/class/thermal`, e a resposta honesta é dizer que escondeu.
3. **temperatura da TV pela rede** não existe no ECP; quem mostra é a tela de
   engenharia no aparelho. E o firmware do Roku é assinado — binwalk não abre.

Defeito achado no caminho: `dumpsys battery` publica temperatura em **décimos**
de grau, e o primeiro código tratou como milésimos (312 virava 0,3 °C). O teste
fixa 31,2 °C.

Na tela, cada alvo desligado mostra **o que ligar** (a variável e o arquivo),
o botão não fica mudo, e o resultado vem em seções de rótulo/valor com
“o que a leitura não alcança” e “o que o JARVIS não faz” embaixo.

### 0.92.3 — scanner do celular: medir, achar e dizer o que fazer

> vou testar com o meu cll quero ver se consigo melhorar e otimizar e ver uns
> problemas q ele ta apresentando talvez passsando um escaner nele talvez
> consegimos resolver

A 0.92.2 deu olhos: `anatomia.py` descreve o aparelho. Faltava o **juízo** — e
é isso que o dono pediu: “ver uns problemas” e “otimizar”. Então o
`diagnostico_celular.py` pega a mesma leitura de somente-leitura e a transforma
em **achados**.

- **`analisar()`** é função pura: entra a saída crua do `adb`, sai
  `problemas[]` + `otimizacoes[]` + `secoes[]`. Isso permite testar os limiares
  com um SM-A346B sintético, sem aparelho na mesa.
- **Cada achado tem quatro campos e não tem menos:** `medido` (o número e de
  onde veio), `causa`, `o_que_fazer` (o passo que a pessoa executa na tela) e
  `limite` (o que aquilo não resolve).
- **Cada otimização diz se o ganho foi medido.** “Fechar o Instagram libera
  928 MB” é medido; “diminuir a animação deixa mais rápido” é **sensação**, e
  vem marcado assim — porque essa é a frase que a internet de otimização
  vende, e quase nunca é verdade medida.
- **A lista de comandos é auditada na importação** e no teste: nada de
  `install`, `push`, `rm`, `settings put`, `reboot` ou `su`.

Três portas para o mesmo motor: `escanear-celular.bat` (duplo clique, texto no
console e JSON em `storage/diagnosticos/`), o botão **“Passar o scanner”** no
cartão do Android da aba Anatomia, e a skill `celular.diagnostico` no chat.

Defeitos achados na primeira leitura *de verdade* (com um `adb` de teste
servindo um aparelho sintético): vírgula sobrando em “42,8 °C carregando,”; o
texto mandava ver “a lista abaixo” quando a lista estava acima; 11,8% de RAM
aparecia como “12%” e o achado parecia contradição; e `**qual**` de markdown
vazava para o console do Windows.

O limite é declarado no rodapé, sempre: o scanner **não** desinstala, **não**
limpa cache, **não** muda ajuste e **não** reinicia. Quem mexe no aparelho é o
dono, na tela dele — o JARVIS mede e explica.

### 0.92.4 — “a tela trava e se mexe sozinha”: o sintoma vira ordem de suspeita

> as vezes minha tela trava ou ta lenta o frame meio q fica lento do nada ou ele
> comeca a se mexer sozinho so para quando desliga a tela e ligo de volta

O scanner da 0.92.3 media o aparelho. Faltava medir **o que o dono vê** — e esse
relato tem uma assinatura que nenhuma medida isolada entrega.

A cadeia: o controlador de toque entrega evento sem dedo → o Android espera o app
responder (ANR) → a fila de desenho atrasa (quadro travado) → o app reage a
toques fora de hora. **Apagar a tela desliga o controlador e esvazia a fila** —
por isso só o desligar/ligar resolve. Nenhuma outra causa tem esse gesto.

Três leituras novas, todas de leitura:

- `logcat -b system -d` → `ANR in <pacote>` + `Reason:` (o app que não respondeu);
- `dumpsys gfxinfo` → quadros travados por app (o número por trás de “frame lento”);
- `dumpsys input` e `dumpsys window displays` → dispositivo de toque e janela em foco.

E o cruzamento: cinco perguntas (`tela-prende`, `frame-lento`, `se-mexe-sozinho`,
`so-para-apagar-tela`, `esquenta`) somam pontos na matriz `CAUSAS`, e o que o
aparelho mediu soma mais. O resultado é uma **fila de suspeitas** com o teste mais
barato de cada uma.

Duas honestidades no desenho: o Android **não publica** “toque sem dedo” — o
achado de toque fantasma é a leitura da consequência, e o próprio limite diz
“não é diagnóstico fechado”. E a tela marca `medido no aparelho` × `sem medida
no aparelho`, para o relato não virar laudo.

Defeito achado: o parser do `gfxinfo` exigia a linha inicial sem `**`, e o Android
imprime `** com.app/1234`; o pacote nunca era lido e o achado de frame lento
nunca aparecia. O teste com 28% de quadros travados fixa isso.

### 0.92.5 — “100% de acesso ao celular”: os cinco degraus, ditos na cara

> quero e preciso q o jarvis tenha 100 de acesso ao meu celular
> ta ja conectei o cll no pc como faço o jarvis rodar por todo o meu celular

Duas perguntas que parecem uma. A primeira pede um número que **não existe**; a
segunda pede um botão que **existe e faltava**: passar por todo o celular, uma vez,
sem perguntas.

**Os degraus.** `varredura.CONTROLE` guarda os cinco como dado, não como promessa:
1) cabo + Depuração USB (lê tudo o que o Android publica, espelha, manda toque e
tecla, instala/remove, copia mídia); 2) `adb tcpip 5555` (o mesmo sem cabo);
3) root via bootloader + Magisk; 4) flash de ROM/kernel; 5) explorar falha de
segurança. `controle(aparelho=...)` mede em qual o aparelho está e devolve
`degrau_atual`, `degrau_maximo_jarvis = 2`, e para 3/4/5 `jarvis_faz=False` com a
`recusa` escrita. O texto do degrau 3 diz o preço: o desbloqueio **apaga o
aparelho** e quebra OTA, banco e carteira.

**Por que não se promete 100%.** Nem a fabricante entra no aparelho bloqueado:
sandbox por app, memória embaralhada, bootloader que recusa imagem sem assinatura e
verified boot que **detecta** a troca. É a mesma porta que lê a sua conversa que lê
a senha do banco — e por isso a recusa é declarada onde o dono pode discordar dela.

**As mãos do degrau 1.** `acoes.celular_abrir_app` / `celular_fechar_app` /
`celular_instalar_apk`: `monkey`, `am force-stop`, `install -r`, sempre
`adb -s <serial>` e `shell=False`, sempre atrás de `JARVIS_ACOES=1` **e**
`confirmed: true`, pacote validado por regex (o teste manda
`com.whatsapp; rm -rf /` e espera recusa) e só `.apk` de dentro da área do JARVIS.

**A varredura inteira.** `varredura.py` faz 12 leituras em 6 seções (pastas,
partições, memória, processos, sistema/apps, identidade), monta veredito
“Passei por N de 12 leituras…” e escreve relatório em `storage/diagnosticos/`.
`ver-tudo-no-celular.bat` é o duplo clique (`--completo --sem-perguntas`); a rota
`GET /api/anatomia/android/varredura` é a mesma coisa pela tela; a skill
`celular.varredura` é a mesma coisa pelo chat. É **só leitura** — o teste varre a
lista de comandos e recusa `install`, `push`, `rm`, `reboot`, `su`.

**A tela.** Anatomia ganhou o cartão “Até onde o JARVIS chega”, com badge
“degrau N de 5”, o que ganha / o que falta / o que custa, e a lista do que o JARVIS
**não** faz e por quê. Sem aparelho a rota responde **409** com o que ligar.

### 0.92.6 — o primeiro relatório de verdade achou quatro defeitos

> o relatório do `ver-tudo-no-celular.bat` no SM-A346MU (Android 16): “Passei por
> 10 de 12 leituras… Nenhum problema nas áreas que o scanner mede”, com PARTIÇÕES
> vazia na mesma tela que listava as pastas.

A 0.92.5 juntou Anatomia, scanner e mapa de pastas numa passada. O desenho estava
certo e a **junção** estava quebrada. O primeiro aparelho real mostrou o buraco:

**A varredura não media o que o scanner lia.** A lista era escrita à mão, com 12
comandos; o scanner de problemas procura por 19, chave por chave. Faltavam
`getprop`, `dumpsys battery`, `df -k`, `/proc/meminfo`, `logcat`, `gfxinfo`,
`dumpsys input` e mais. O scanner recebia um dicionário sem nada disso, não
achava nada, e escrevia “nenhum problema” — **a mesma frase de um aparelho
saudável**. Ausência de medida virou atestado de saúde, que é o pior defeito
possível num relatório: o que tranquiliza sem ter olhado.

A correção não foi acrescentar os 7 comandos que faltavam (isso voltaria a
divergir na próxima skill): a lista da varredura agora **é derivada** da lista do
scanner — `LEITURAS_DO_SCANNER = diagnostico_celular.COMANDOS` — e o que é só da
varredura (mapa de pastas, `dumpsys meminfo`, apps de fábrica, partições) ficou
num bloco separado e explícito. Um teste compara as duas listas para sempre.

**O teste que deixou passar.** O dicionário de saídas de exemplo dos testes era
menor que a lista de comandos. O teste rodava `montar()` com um `saidas` sem as
chaves do scanner, e “passava” — porque o defeito era exatamente esse. Agora um
teste cobra que **toda** leitura de `COMANDOS` tenha exemplo; se faltar, falha.

**Partição negada virava seção vazia.** No Android 16 o `cat /proc/partitions`
responde `Permission denied`. A seção sumia e parecia falha do JARVIS. Agora ela
existe e diz o motivo, com o mesmo texto que o rodapé já usava para root.

**Dois relatórios de memória, um jogado fora.** A seção `memoria` do scanner era
substituída pela do `dumpsys meminfo`, que não publica `MemAvailable` — o número
que decide se falta RAM. Agora as duas convivem, a do scanner primeiro.

**A mesma negativa três vezes.** `Permission denied` aparecia três vezes, uma por
módulo, cada uma com um prefixo. A dedup passou a ser pelo miolo do erro.

**O título sem o modelo.** O cabeçalho abriu em “Android 16”: o `getprop` inteiro
passa de 60 KB e a linha do modelo cai depois do corte. Agora, quando a chave não
está na leitura, o `adb` é perguntado direto — `getprop ro.product.model` — em vez
de aceitar um título cego.

E a tela: a varredura só existia no console. A aba Anatomia ganhou o botão **“Ver
tudo no aparelho”** e o cartão, com problemas, mapa, limites e o que não dá sem
root. Um leitura que só existe em `.bat` não serve para quem não abre `.bat`.
