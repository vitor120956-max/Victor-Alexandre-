# Análise: `vercel-labs/agent-desktop` (lida em 2026-11-09)

Pergunta: *“o que você acha do repositório vercel-labs/agent-desktop?”*

Resposta curta: **é a melhor referência aberta que existe sobre “o agente vê e
opera a tela do PC” — e é justamente o que falta no JARVIS. Mas ele não resolve o
que você pediu antes (Gmail e WhatsApp), e eu não o instalaria nesta máquina.**
O que vale a pena é copiar o **protocolo**, não o binário.

---

## Ficha técnica (medida na API do GitHub hoje)

| item | valor |
|---|---|
| nome | `vercel-labs/agent-desktop` |
| descrição | *Computer use CLI for AI agents* |
| estrelas / forks | **20.404** / 1.508 |
| licença | Apache-2.0 |
| linguagem | Rust (núcleo) + launcher npm |
| criado | 2026-02-19 |
| último release | **v1.2.0**, 2026-11-05 |
| último commit | 2026-11-09 |
| issues abertas | 205 |
| tamanho | 3.746 arquivos |
| plataformas | macOS 13+, **Windows 10 1809+**, Ubuntu 24.04+ |

---

## O que ele faz — e faz bem

1. **Lê a árvore de acessibilidade, não a imagem.** No Windows usa **UI
   Automation (UIA)**; no macOS, AX; no Linux, AT-SPI. Nada de screenshot nem
   “achar o botão pela cor”. Cada elemento acionável ganha um **`ref`**.
2. **Ciclo observar → agir → verificar.** `snapshot` devolve a árvore em JSON com
   os refs; a ação usa o ref; o agente tira outro snapshot para conferir. Refs são
   presos ao snapshot: se a tela mudou, vem `STALE_REF` em vez de clicar errado.
   Se houver duas janelas parecidas: `AMBIGUOUS_TARGET`. **Sistema de erro
   explícito** — é metade do valor do projeto.
3. **Ação sem mexer o ponteiro.** Por padrão é *headless*: usa a API semântica,
   sem mover o mouse nem roubar o foco. `--headed` existe para o que é físico.
   **Isso resolve um problema real seu**: você não tem mouse USB nem tela que
   aceite toque — o JARVIS poderia clicar sem ninguém mexer no cursor.
4. **Sem modelo dentro.** O loop mora no agente que chama. É CLI (e biblioteca C,
   e servidor MCP). Arquitetura limpa: `PlatformAdapter` → um crate por sistema.
5. **Recusas catalogadas.** `win+l`, `alt+f4`, `alt+tab`, `win+r`, `ctrl+alt+del`
   são **recusados** sem `--force`; `ctrl+alt+del` não é sintetizável de jeito
   nenhum. `type` no Windows exige `--headed`; sem foco, usa `set-value`. Isso é
   pensamento de segurança, não enfeite.

O melhor arquivo do repositório, para mim, não é código: é `docs/solutions/`, um
catálogo de **modos de falha** que custaram tempo de verdade — *“a test that
cannot fail is not coverage”*, *“an AT-SPI write that returns success has not
changed anything”*, *“a wait for closed right after the opener is satisfied
falsely”*. É a mesma cultura que a gente vem usando aqui (“declarar o que foi
medido”), só que com mais quilometragem.

---

## O que ele **não** faz (e isso importa muito no seu caso)

| limite declarado pelo próprio projeto | o que significa para você |
|---|---|
| **“não automatiza páginas web”** — para isso existe o `agent-browser` | **Gmail e WhatsApp Web são web.** O repositório que você me mostrou **não** resolve o pedido da mensagem anterior; quem resolveria é o `agent-browser` (ou o nosso conector IMAP) |
| Windows 10 **1809 ou superior** | seu PC já deu problema com versões antigas de Windows neste projeto (1607/1709/1803). Se o build for anterior a 1809, **não roda** |
| app **sem árvore de acessibilidade** é invisível | programas antigos, jogos e alguns instaladores simplesmente não aparecem |
| binário **não assinado** | SmartScreen avisa, antivírus pode quarentenar, Smart App Control bloqueia — no Windows 11 limpo, barra de vez |
| app **como administrador** só é dirigido de um terminal elevado | abrir o JARVIS como admin muda o resto do ambiente |
| sessão bloqueada, tela de login, prompt do UAC, sessão 0 | nada funciona ali — e é bom que seja assim |
| **Chromium/Electron**: a primeira leitura da árvore leva **10 a 25 s** | num PC de 4 GB, Chrome, WhatsApp Desktop e VS Code começam **lentos**; a primeira ação parece travada |
| segurar tecla/botão (`key-down`, `mouse-down`…) **recusado** | não dá para “segurar Shift e arrastar” |
| produto de **labs**, 205 issues abertas, 56 comandos | muda rápido; um `npm update` pode quebrar o roteiro |

E o ponto que decide para mim: **é outro binário nativo** (Rust, com helpers por
plataforma) numa máquina de 4 GB que já sofre com o `.venv`. Instalar isso
contradiz a regra que a gente combinou — *implementação própria, sem instalar
upstream* — e adiciona uma dependência que eu não consigo testar daqui.

---

## O que o JARVIS faz hoje — comparação honesta

| | JARVIS 0.81.0 (`mesa.*`) | agent-desktop |
|---|---|---|
| **ver** a tela | só os **títulos** das janelas | árvore inteira, com nome, papel e posição de cada botão |
| **clicar** | coordenada x,y que **você** informa | ref do elemento: “o botão Salvar” |
| conferir se deu certo | não confere | tira snapshot novo e compara |
| freio de segurança | **pânico por movimento** (se você mexer o mouse, ele para) | ações semânticas sem mexer o mouse; refs que ficam velhos recusam |
| erro quando o alvo sumiu | clique no vazio | `STALE_REF` / `AMBIGUOUS_TARGET` |
| dependências | **nenhuma** (ctypes fala com o Windows) | binário Rust + Node para instalar |
| web (Gmail, WhatsApp) | conector IMAP + link do navegador | **não faz** |

O `mesa.py` foi escrito de propósito para **não** ler a tela (“não faz captura de
imagem nem OCR”). Isso o deixou cego: ele clica no escuro e não sabe se acertou.
É exatamente a lacuna que o agent-desktop expõe.

---

## Veredito

- **Como referência de arquitetura: nota alta.** O par `snapshot` + `ref` +
  verificação é o desenho certo, e as recusas (atalhos perigosos, sessão
  bloqueada, app elevado) são o tipo de rigor que eu quero copiar.
- **Como dependência do JARVIS: não.** Binário de terceiro, não assinado, exige
  Windows 1809+, não faz web, e eu não consigo medir o comportamento dele no seu
  PC daqui — o que contraria a regra de não prometer ganho não medido.
- **Como solução para Gmail/WhatsApp: irrelevante.** São páginas web; o caminho
  certo é o que a 0.81.0 já abriu (IMAP somente leitura + link do navegador), ou
  um navegador controlado (o `agent-browser`, do mesmo time, é o par dele).

---

## O que eu proponho fazer com isso (0.82.0, em duas etapas)

**Etapa 1 — só leitura (sem risco).** `mesa.arvore`: lê a árvore de
acessibilidade da **janela em foco** no Windows (UIA/MSAA via `ctypes`, sem
dependência nova) e devolve JSON — papel, nome, posição e se é clicável. É
*somente leitura*: não clica, não digita, não muda nada. Serve para descobrir, no
seu PC, **quais programas realmente expõem árvore** (Chrome? WhatsApp? o
Explorer?) antes de qualquer ação.

**Etapa 2 — clicar por ref, só depois que a etapa 1 se provar.** `mesa.clicar_alvo`
recebe o `ref` do snapshot, confere se ele ainda existe (senão `REF_VELHA`),
clica no centro do elemento e **tira um snapshot novo** para dizer se o alvo
sumiu — que é o sinal de que o clique funcionou. Mantém o pânico por movimento e
a confirmação antes de cada ação.

**O que eu recuso das duas:** mexer o ponteiro sem necessidade, sintetizar
`ctrl+alt+del`, e mandar snapshot para o modelo sem você autorizar (um snapshot
de janela pode conter o conteúdo da sua tela — está escrito no SECURITY deles e
vale aqui também).

**O que eu não vou fazer:** empacotar o `agent-desktop` dentro do JARVIS. Se
algum dia você quiser experimentar o original, o caminho é o `npm install -g
agent-desktop` no seu PC, sabendo dos avisos acima — mas aí é ferramenta de fora,
rodando fora do JARVIS, com o seu consentimento e não como parte do produto.

## Origem declarada

Tudo acima foi lido de `api.github.com` (README, FAQ, `apps/docs/.../windows.mdx`,
árvore de arquivos, releases e commits) em **2026-11-09**. As páginas do site
(`agent-browser.dev`) **não** foram acessadas daqui; o que está citado delas veio
do README do repositório. Números de estrelas, issues e datas mudam — são um
retrato, não uma promessa.
