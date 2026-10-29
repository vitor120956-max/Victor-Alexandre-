# Diagramas

O JARVIS desenha em duas camadas. O **IR** (0.12.0, de [`tt-a1i/archify`](https://github.com/tt-a1i/archify)) tem especificação JSON própria, validação estrutural, layout medido e entrega em **HTML autocontido**. A **camada editorial** (0.18.0, de [`cathrynlavery/diagram-design`](https://github.com/cathrynlavery/diagram-design)) decide o tipo e o orçamento antes do traço, mede a marca, confere as seis regras de conector e escreve o recibo do que foi cortado numa importação.

As duas adaptações são estáticas: nenhum CLI, template, pacote, plugin, navegador ou script do upstream é instalado ou executado. O desenho continua saindo do Python deste repositório.

O valor que sobrevive sem navegador no archify é o **IR validado**, o **roteador de tipos**, as **regras de geometria** e o **contrato de entrega**. No diagram-design é o **vocabulário editorial**: 45 tipos com orçamento, nove padrões semânticos, papéis de cor com contrato de contraste e o recibo de fidelidade.

---

## O que foi adaptado

| Do upstream | Aqui |
|---|---|
| 10 tipos com schema JSON e `additionalProperties: false` | 10 tipos com o mesmo recorte, em PT-BR e com o IR do upstream aceito na entrada |
| Router de tipo por pergunta | `diagram.type` pontua dez tipos por sinal e devolve o esqueleto |
| Geometria medida (folga de rótulo, leque, canvas) | `diagram.layout` mede cruzamento, colisão, folga, leque e preenchimento |
| Renderer HTML de 786 KB e template próprio | Gerador Python de SVG + HTML autocontido (10 KB típicos) |
| CLI `archify.mjs` com `finalize`/`deliver`/`check` | `diagram.delivery` roda os gates em ordem, sem subprocesso |
| `visual-check` em Chrome | **Não adaptado**: sem navegador, o piso de texto é estimado e declarado |
| `.archify/<tipo>-<slug>-<data>/candidate.json` | O IR normalizado volta no corpo da resposta para você salvar |
| Explicador de uma página com painéis | Cartões de leitura no HTML gerado (até 4) |
| `brand-marks/catalog.json` e captura | **Não adaptado**: marca é opcional e textual (`brandMark` fica fora do recorte) |

### O que ficou de fora, de propósito

- `npx -y skills add tt-a1i/archify`, `archify.zip`, `bin/archify.mjs`, `bin/finalize.mjs`, `bin/visual-check.mjs`;
- plugins DSH para Claude Code e Codex, e o Chrome de inspeção;
- captura de tela e revisão visual automática;
- catálogo de 23 ícones e marcas de produto — o desenho usa tipo, rótulo, sub-rótulo, etiqueta e membros;
- `views` aposentado do upstream: a leitura por etapas foi trocada por seções de abertura no HTML.

---

## Os dez tipos

| Tipo | Pergunta que responde | Arrays principais | Orçamento |
|---|---|---|---|
| `architecture` | componentes, serviços, fronteiras e implantação | `componentes`, `conexoes` | 24 |
| `workflow` | processo, aprovação, runbook, chamada de ferramenta | `raias`, `etapas`, `conexoes` | 20 |
| `sequence` | quem chama quem, em que ordem, com que resposta | `participantes`, `mensagens` | 8 |
| `dataflow` | de onde o dado vem, como é processado, para onde vai | `estagios`, `elementos`, `fluxos` | 22 |
| `lifecycle` | estados, transições, retentativa e estados terminais | `estados`, `transicoes`, `caminhoPrincipal` | 14 |
| `erd` | tabelas, colunas, chaves e cardinalidade | `entidades`, `relacionamentos` | 9 |
| `tree` | hierarquia de um pai só: módulos, pastas, capacidades | `nos` | 40 |
| `class` | classes, interfaces, membros e relações | `tipos`, `relacionamentos` | 9 |
| `timeline` | incidente, release ou histórico num relógio | `raias`, `eventos` | 22 |
| `waterfall` | onde o tempo foi: duração, sobreposição, aninhamento | `trechos` | 16 |

O orçamento é a densidade em que o tipo ainda é lido de relance. Passar dele é aviso; passar de **40 nós** é bloqueio.

### Vocabulário dos nós

- **Componentes:** `frontend`, `backend`, `database`, `cloud`, `security`, `messagebus`, `external` — aceita `api`, `banco`, `fila`, `nuvem`, `auth`, `usuário` e outros apelidos em português.
- **Ciclo de vida:** `start`, `active`, `waiting`, `decision`, `success`, `failure`, `neutral`, `external`.
- **Classes:** `class`, `abstract`, `interface`, `enum`, `record`.
- **Relações UML:** `dependency`, `association`, `inheritance`, `realization`, `composition`, `aggregation`.

---

## O IR em português

```json
{
  "tipo": "arquitetura",
  "titulo": "Checkout da loja",
  "subtitulo": "Do clique ao pedido pago.",
  "saida": "checkout.html",
  "preset": "classico",
  "legenda": "auto",
  "componentes": [
    { "id": "loja", "rotulo": "Loja", "tipo": "frontend", "faixa": 0 },
    { "id": "checkout", "rotulo": "Checkout", "tipo": "backend", "faixa": 1 },
    { "id": "pagamentos", "rotulo": "Pagamentos", "tipo": "security", "faixa": 1 }
  ],
  "conexoes": [
    { "de": "loja", "para": "checkout", "rotulo": "HTTPS" },
    { "de": "checkout", "para": "pagamentos", "rotulo": "cobra", "variante": "emphasis" }
  ],
  "fronteiras": [
    { "id": "pci", "rotulo": "Perímetro PCI", "membros": ["pagamentos"] }
  ],
  "cartoes": [
    { "cor": "cyan", "titulo": "Contrato", "itens": ["Toda chamada é HTTPS."] }
  ]
}
```

Regras fixas:

- `id` começa com letra e segue com letras, números, hífen ou sublinhado (`^[a-zA-Z][a-zA-Z0-9_-]*$`);
- `titulo` e a saída `.html` são obrigatórios; título acima de 72 caracteres é aviso;
- rótulo de nó até 28 caracteres é confortável e 44 é o limite duro;
- rótulo de aresta acima de 28 caracteres rouba a folga entre caixas;
- até 40 nós, 120 relações e 4 cartões;
- especificação de até 200 000 caracteres.

### O IR do archify também entra

A leitura aceita o formato do upstream — `schema_version`, `diagram_type`, `meta`, `components`, `connections`, `boundaries`, `nodes`, `edges`, `participants`, `messages`, `entities`, `types`, `states`, `spans`, `lanes`, `stages`, `cards` — e converte para o modelo local. A resposta avisa quando isso acontece. Campos que não têm equivalente (`brandMark`, `repository`, `translations`, `views`, `icon`) são ignorados em vez de reinterpretados.

---

## As sete skills do IR

| Skill | Entra | Sai |
|---|---|---|
| `diagram.type` | pedido em texto, plateia opcional | tipo escolhido, dez candidatos pontuados, esqueleto JSON |
| `diagram.spec` | especificação JSON | achados em quatro partes, contagens, IR normalizado |
| `diagram.layout` | especificação JSON | coordenadas, métricas medidas, mapa em texto |
| `diagram.render` | especificação JSON + formato | HTML, SVG, Mermaid, texto ou DOT |
| `diagram.legend` | tipo, preset e modo, com especificação opcional | variantes, presets com contraste, lacunas de legenda |
| `diagram.delivery` | especificação JSON | gates em ordem, parada, resumo para gravar |
| `diagram.library` | nada | catálogo de tipos, vocabulários, presets e limites |

Todas devolvem `executed: false` e `readOnly: true`. Nenhuma grava arquivo, abre processo, instala dependência ou chama provedor.

---

## A camada editorial

A camada editorial não desenha: ela decide **antes** do traço e confere **depois** do arquivo. São sete verbos, todos estáticos, que respondem a perguntas que o IR sozinho não faz.

### O que foi adaptado

| Do upstream | Aqui |
|---|---|
| 45 tipos com `type-<nome>.md` e orçamento por tipo | `editorial.tipo` pontua os 45 tipos e devolve orçamento, preset e rampa |
| Tokens semânticos com contrato de contraste WCAG | `editorial.marca` resolve 11 papéis e propõe o menor ajuste que passa |
| `lint-render.py` com navegador e 12 anti-padrões | `editorial.lint` aplica os mesmos 12 anti-padrões ao texto do arquivo |
| `verify-geometry.py` sobre o SVG renderizado | `editorial.conector` mede as 6 regras na geometria **declarada** |
| `drawio_extract.py`, `mermaid_extract.py`, `excalidraw_extract.py` + Playwright | `editorial.importar` lê os três formatos como texto e redesenha com recibo |
| `self_check.py`, `lint-render.py --all`, `export_svg.py`, `export_png.py` | `editorial.entrega` confere acessibilidade, viewBox, `min-width`, impressão e rampa |
| Marketplace `npx skills add` e o CLI de agente | **Não adaptado**: nada é instalado; a página Diagramas chama a API local |

### Os 45 tipos

Cada tipo carrega a pergunta que responde, a família de layout e o orçamento de nós e setas. O catálogo completo está em `editorial.catalogo` e na aba **Catálogo**.

| Família | Tipos |
|---|---|
| Arquitetura (6) | `arquitetura`, `delta-arquitetura`, `estado-atual-ti`, `alto-nivel`, `implantacao`, `dependencia` |
| Fluxo (3) | `fluxograma`, `sequencia`, `maquina-estado` |
| Processo (10) | `linha-tempo`, `raia`, `loop`, `gantt`, `processo`, `espinha-peixe`, `kanban`, `jornada`, `blueprint`, `story-map` |
| Hierarquia (5) | `aninhado`, `arvore`, `organograma`, `camadas`, `piramide` |
| Comparação (11) | `quadrante`, `radar`, `polar`, `venn`, `barras`, `cascata`, `treemap`, `mapa-calor`, `linha`, `dispersao`, `wardley` |
| Dados (8) | `er`, `medalhao`, `fluxo-dados`, `integracao-dp`, `matriz-seguranca`, `sankey`, `uml-classe`, `esquema-bd` |
| Objeto (2) | `explodido`, `planta` |

Duas famílias ganham variantes de eixo em vez de tipos novos: `linha` cobre **slopegraph**, **ridgeline**, **streamgraph** e **bump**; `dispersao` cobre **bolha** e **enxame**. As variantes continuam dentro do mesmo orçamento.

Os tetos seguem o upstream: `arquitetura` 8 nós, `raia` 9, `camadas` 6, `linha` 5 séries, `dispersao` 30 pontos, `gantt` 12 tarefas, `sankey` 8 nós e 12 fluxos. Acima do teto do tipo — ou de 9 nós em qualquer tipo — o veredito **bloqueia** e pede divisão em visão geral + detalhe.

### Os nove padrões semânticos

O padrão descreve **o que o sistema faz**; o tipo descreve **como a informação é arranjada**. Escolher o padrão primeiro evita o desenho bonito que responde à pergunta errada.

| O leitor precisa entender | Padrão | Tipo mais próximo |
|---|---|---|
| Muitas chegadas competindo por capacidade finita | `fila` | fluxo de dados |
| Perguntas, entradas, controles e saídas repetidos por estágio | `estagios` | processo |
| Uma conversa virando registro durável | `entrada-estruturada` | fluxo de dados |
| Por que duas decisões de política diferem | `traços-política` | fluxograma |
| Quais rotas cruzam a fronteira de confiança | `estrada` | arquitetura |
| Quais controles valem em cada superfície | `catálogo-controles` | camadas |
| Como defesas reduzem risco e o que sobra | `defesas` | camadas |
| Em que subelementos o sistema se divide, cada um citável | `blocos` | árvore |
| Como um sujeito percorre fases, esperas e desfechos | `ciclo-vida` | máquina de estados |

O casamento é por palavra inteira: `id` não casa dentro de `pedido`. Quando o padrão aparece com dois sinais ou mais, ele **decide o tipo**; com um sinal só, fica como sugestão ao lado do tipo escolhido.

### Papéis de cor e contraste

O desenho referencia **papéis**, nunca hex. Trocar `accent` muda todos os diagramas de uma vez.

| Papel | Claro | Escuro | Papel no desenho |
|---|---|---|---|
| `paper` | `#f5f5f5` | `#2d3142` | Fundo e preenchimento padrão |
| `paper-2` | `#ececec` | `#393e53` | Contêiner, preenchimento secundário |
| `ink` | `#2d3142` | `#f5f5f5` | Texto e traço primário |
| `ink-strong` | `#111111` | `#111111` | Texto sobre preenchimento de acento |
| `muted` | `#4f5d75` | `#bfc0c0` | Texto secundário, seta padrão |
| `soft` | `#5a6580` | `#949eb2` | Sublabel e rótulo de fronteira |
| `rule` | `rgba(45,49,66,.12)` | `rgba(245,245,245,.12)` | Fio de borda |
| `rule-solid` | `#bfc0c0` | `rgba(191,192,192,.25)` | Borda forte, linha de base |
| `accent` | `#bf4520` | `#f08a59` | Foco: 1–2 elementos por diagrama |
| `accent-tint` | `rgba(191,69,32,.08)` | `rgba(240,138,89,.10)` | Preenchimento de caixa com borda de acento |
| `link` | `#2e5aa8` | `#739fdf` | Chamada HTTP/API, sistema externo |

O contrato é WCAG 2.x: **4,5:1** para texto (inclusive `soft`, `link` e `accent` usados como texto), **3:1** para marca essencial (linha, seta, borda, ponto), e nenhum mínimo para `rule`, `rule-solid`, `paper-2`, `accent-tint` — desde que nunca sejam o único portador de significado. Cor translúcida é composta sobre o papel **antes** de medir. `ink-strong` é medido contra o preenchimento de acento a 85%, não contra o papel.

Quando um papel de texto não passa, o ajuste proposto muda a **luminosidade** e preserva o matiz: o acento da marca continua sendo o acento da marca, só legível.

### Tipografia

| Papel | Família | Tamanho | Uso |
|---|---|---|---|
| `title` | Instrument Serif | 1,75rem | H1 da página |
| `node-name` | Geist (sans) 600 | 12px | Nome legível por gente |
| `sublabel` | Geist Mono | 9px | Porta, protocolo, URL, tipo de campo |
| `eyebrow` | Geist Mono 500 | 7–8px, 0,18em, caixa alta | Etiqueta de tipo e eixo |
| `arrow-label` | Geist Mono | 8px, 0,06em | Anotação de seta |
| `callout` | Instrument Serif itálico | 14px | Aparte editorial |

Mono é para conteúdo **técnico**. Nome de componente é sans; título é serifa; itálico é para o aparte. `JetBrains Mono` é recusado pelo nome — é o atalho de "fonte de dev" que o guia não aceita.

### Tamanhos, rampas e os quatro discos

Todo desenho tem quatro discos: **formato**, **tamanho**, **detalhe** e **plateia**. Eles são escolhidos antes de desenhar porque mudam o deliverable, o `viewBox`, a rampa tipográfica e a contagem de nós.

| Preset | `viewBox` | Rampa | Uso |
|---|---|---|---|
| `doc-inline` | 960 × 600 | standard | Diagrama na largura do corpo |
| `doc-wide` | 1280 × 720 | standard | Documentação de largura total |
| `slide-16x9` | 1280 × 720 | presentation | Slide projetado |
| `slide-4x3` | 1024 × 768 | presentation | Template de slide antigo |
| `social-og` | 1200 × 632 | presentation | Cartão de link |
| `social-square` | 1080 × 1080 | presentation | Post de feed |
| `print-a4-landscape` | 1120 × 792 | print | A4 paisagem |
| `print-a3-landscape` | 1584 × 1120 | print | A3 paisagem |
| `print-letter-landscape` | 1056 × 816 | print | Carta paisagem |
| `fit` | derivado do conteúdo | standard | Handoff vetorial |

Todos os valores são divisíveis por 4. A rampa acompanha o tamanho: nome a 12px no padrão, 16px na apresentação, 12px no impresso. Nome de 12px num `slide-16x9` é **bloqueio**, não preferência.

| Detalhe | Nós | Arestas | Sublabel |
|---|---|---|---|
| `faithful` | ≤24, com zonas obrigatórias | ≤32 | todo port, protocolo e versão |
| `balanced` | ≤12 | ≤16 | técnico em até 4 nós |
| `simplified` | ≤7 | ≤9 | nenhum |

| Plateia | Nome do nó | Sublabel | Rótulo de seta | Nunca |
|---|---|---|---|---|
| `engineer` | nome exato do serviço | protocolo, porta, versão | `POST /v2/orders` | "conecta com" |
| `mixed` | componente, sigla expandida | tecnologia só quando muda a decisão | verifica, grava, avisa | porta, versão, codinome |
| `executive` | capacidade e resultado | nenhum | aprova, paga | fornecedor, infraestrutura, protocolo |

### As seis regras de conector

O upstream chama as seis de não negociáveis. Elas são medidas, não opinadas.

| # | Regra | Falha quando |
|---|---|---|
| 1 | Cotovelo ortogonal com `r=8` (`r=6` no aperto); reta só com os extremos no mesmo eixo | Conector diagonal |
| 2 | Rótulo ≤14 caracteres, caixa alta, sobre máscara opaca, com 6–10px visíveis até o traço | Rótulo encostado, cortado ou sobre a própria linha |
| 3 | Sem sobreposição: paralelos a ≥12px, cruzamento único com ponte | Traços empilhados |
| 4 | Leque no ponto de encaixe: `L·k/(N+1)`, ≥12px entre vizinhos | Dois conectores no mesmo ponto |
| 5 | Sem trânsito atrás de caixa que não seja ponta; se inevitável, tracejado `4,3` | Linha sumindo atrás de um nó |
| 6 | Máscara do rótulo não sobrepõe nó desenhado depois | Rótulo cortado pela borda do nó |

A entrada é a geometria declarada: `de`/`para` com `{x,y,w,h}` e `lado`, ou `pontos` explícitos; opcionalmente `rotulo`, `mascara`, `raio`, `tracejado`, `cruzaCaixa`, `setaNaIntermediaria` e `nosDepois`. A conta é feita em coordenada, sem renderizar.

### Contrato de SVG acessível

1. `<svg>` com `role="img"` e `aria-labelledby` apontando para título **e** descrição que existem.
2. `<title>` é o primeiro filho de `<svg>`, antes de `<defs>`.
3. IDs prefixados por diagrama e variante (`fila-title`, `fila-dark-desc`); `title` e `desc` puros são proibidos.
4. `<title>` é o nome curto do assunto, até ~60 caracteres.
5. `<desc>` é uma frase sobre o **conteúdo**, não sobre a geometria.
6. SVG só decorativo leva `aria-hidden="true"`.

`editorial.entrega` confere os seis no texto, mais o `viewBox` do preset, o `min-width` igual à largura do `viewBox`, o invólucro com `overflow-x: auto`, a liberação em `@media print` **depois** da regra do SVG, e a rampa tipográfica. Movimento é opcional: exige `prefers-reduced-motion` e um quadro estático completo.

### Importar é redesenhar

`editorial.importar` lê Mermaid (fluxograma, sequência, classe, estado, ER e Gantt), draw.io (`<mxCell>` com vértices, arestas e pais) e Excalidraw (`elements`, `text` com `containerId`, `arrow` com binding).

O que atravessa: **componentes, relações, agrupamento e direção**.
O que não atravessa: coordenada, paleta, fonte, o emaranhado de conectores do draw.io, o layout automático do Mermaid e a geometria à mão do Excalidraw.

Quando a origem passa do teto do detalhe, a **escada de degradação** corta nesta ordem e para assim que cabe:

1. células decorativas — nota adesiva, texto solto, legenda da própria fonte;
2. duplicatas exatas — `Worker ×6` no lugar de seis nós;
3. clusters de folhas — o contêiner engole os filhos;
4. sumidouros de grau 1 — monitoração, bucket de log, camada de arquivo;
5. infraestrutura transversal — log, métrica, segredo, CI;
6. **ainda acima?** divide em visão geral + detalhe em vez de encolher.

Tudo o que sai nos passos 2–6 aparece no **recibo de fidelidade**, no parecer e na aba Importar. O draw.io comprimido é detectado e não descomprimido: o recibo pede o XML do modelo.

### Os doze anti-padrões

Brilho ciano ou roxo no escuro, sombra, raio acima de 12, mono como fonte geral, JetBrains Mono, caixas todas idênticas, legenda dentro da área do desenho, rótulo de seta sem máscara, texto vertical, três cartões de resumo iguais, acento em três ou mais elementos e conector diagonal.

Cada achado traz o que é, por que é genérico, como corrigir e o que acontece se ficar. O lint lê o texto do arquivo: ele não substitui o render.

### As sete skills da camada editorial

| Skill | Entra | Sai |
|---|---|---|
| `editorial.tipo` | pedido, plateia, destino, número de nós | tipo, padrão, orçamento, preset, rampa e plano |
| `editorial.marca` | tokens `papel=valor`, tema | 11 papéis com contraste, mínimo, situação e proposta |
| `editorial.lint` | HTML ou SVG | achados em quatro partes, os 12 anti-padrões |
| `editorial.conector` | lista de conectores em JSON | seis regras medidas, por conector |
| `editorial.importar` | origem draw.io/Mermaid/Excalidraw + 4 discos | nós, arestas, escada aplicada e recibo |
| `editorial.entrega` | HTML + preset | acessibilidade, canvas, rolagem, impressão e rampa |
| `editorial.catalogo` | nada | 45 tipos, 9 padrões, 12 papéis, 10 presets, 6 regras |

Todas devolvem `executed: false` e `readOnly: true`, como as do IR.

### A página `/diagramas`

A página ganhou duas camadas, e a chave fica acima das abas:

- **Desenho por IR** — as sete abas anteriores (Tipo, IR, Layout, Desenho, Legenda, Entrega, Catálogo);
- **Camada editorial** — sete abas novas (Tipo, Marca, Lint, Conector, Importar, Entrega, Catálogo), cada uma com exemplo carregável, parecer, Markdown para copiar e JSON para baixar.

A camada editorial fecha tipo, orçamento, marca e conectores; o esqueleto aprovado vira especificação na camada do IR, que mede o layout e entrega o HTML.

### Limites da camada editorial

- **Sem render:** o lint e a entrega leem texto; nenhuma sobreposição real é medida no pixel.
- **Geometria declarada:** as seis regras valem sobre as coordenadas que você informa, não sobre um SVG renderizado.
- **Sem descompressão:** draw.io comprimido é reconhecido e pede o XML.
- **Escada heurística:** o corte é por rótulo, grau e palavra-chave; qual caminho é principal continua sendo julgamento humano.
- **Sem fonte pública:** o upstream deriva a paleta de um site com `getComputedStyle`; aqui os tokens vêm do texto colado.

---

## Geometria medida

O layout é determinístico: a mesma especificação produz as mesmas coordenadas. As regras vêm do contrato de autoria do upstream, traduzidas para o nosso motor:

- **Folga de rótulo:** uma aresta horizontal entre caixas precisa de `6,5 px × caracteres + 21 px`. Abaixo disso, aviso.
- **Leque:** um lado com `k` relações precisa de `32 + 14 × (k − 1) px`; se a lateral do nó não tem isso, as linhas se empilham.
- **Canvas:** até 1240 px de largura, ou 1790 px quando o desenho é pelo menos 1,55× mais largo que alto. Acima, o texto cai do piso de leitura.
- **Piso de texto:** 8,4 px declarados como estimativa. O upstream mede 6 px no navegador; aqui não há navegador, e isso é dito.
- **Cruzamento e colisão:** segmentos ortogonais são testados entre si e contra caixas que não são ponta. Cruzamento é aviso; linha sobre caixa e caixa sobreposta são bloqueio.
- **Corredores:** cada tipo tem um corredor próprio — faixa na arquitetura, raia no fluxo, estágio no fluxo de dados, nível na árvore, relógio na linha do tempo.

Nenhuma dessas regras "conserta" o desenho: o motor reposiciona, mas não reescreve a topologia. Uma rodada de reposicionamento só pode mudar posições e tamanhos, nunca a verdade do diagrama.

---

## Desenho e formatos

- **HTML** — página única, SVG inline, CSS embutido, cartões e legenda. Sem script, sem fonte remota, sem imagem externa. Abre de um pendrive e imprime.
- **SVG** — só o desenho, com `viewBox` e título acessível.
- **Mermaid** — `flowchart`, `sequenceDiagram`, `stateDiagram-v2`, `erDiagram`, `classDiagram`, `timeline` e `gantt`, conforme o tipo. Texto para outra ferramenta; não é renderizado aqui.
- **Texto** — mapa monoespaçado para colar em revisão, ticket ou chat.
- **DOT** — Graphviz, com `rankdir` e subgrafos de região.

Quatro presets mudam papel, tinta e acento sem mudar a topologia:

| Preset | Papel | Tinta | Contraste |
|---|---|---|---|
| Clássico | `#ffffff` | `#0f172a` | 17,9:1 |
| Sinal | `#071018` | `#e2e8f0` | 15,5:1 |
| Planta | `#0b1d2a` | `#dbeafe` | 14,1:1 |
| Editorial | `#fbf7ef` | `#1b1917` | 16,4:1 |

### Variantes de relação

| Variante | Significado | Traço |
|---|---|---|
| `default` | fluxo comum | linha |
| `emphasis` | caminho principal | linha grossa |
| `security` | política, PII, fronteira | linha vermelha |
| `dashed` | assíncrono ou lote | tracejada |
| `return` | resposta | tracejada fina |
| `dependency` … `aggregation` | notação UML | conforme a relação |

A legenda automática lista **só as variantes usadas**. Esconder a legenda com mais de uma variante é aviso: a linha perde o significado que o autor conhecia.

---

## Contrato de entrega

`diagram.delivery` roda cinco gates em ordem e **para no primeiro que falha**:

1. **Validar o IR** — bloqueios estruturais: título, ids, pontas, hierarquia, datas, orçamento, saída.
2. **Renderizar o HTML** — se o gate anterior falhou, não renderiza e diz por quê.
3. **Checar a geometria** — cruzamentos, colisões, folgas e sobreposição.
4. **Checar no navegador** — sempre `não executado` aqui: não há navegador nesta máquina.
5. **Revisão visual** — `not-requested` por padrão; só vira `pendente` se você pedir.

O resumo devolvido tem o formato que o upstream grava em `<stem>.finalize-summary.json`:

```json
{
  "titulo": "Checkout da loja",
  "tipo": "architecture",
  "saida": "checkout.html",
  "gates": { "validar": "passou", "entregar": "passou", "checar": "passou com ressalvas", "navegador": "nao-executado", "revisao-visual": "nao-solicitada" },
  "parouEm": "",
  "visualReview": "not-requested"
}
```

O contrato nunca finge: se a captura não foi feita, aparece `não executado`; se ninguém olhou o desenho, `not-requested`.

---

## Página `/diagramas`

Sete abas, cada uma com formulário próprio, exemplo carregável e parecer:

- **Tipo** — pedido, candidatos com pontuação e esqueleto para colar;
- **IR** — validação, contagens, avisos e IR normalizado;
- **Layout** — métricas, tabela de coordenadas e mapa em texto;
- **Desenho** — prévia em sandbox, código, download e troca de formato;
- **Legenda** — presets com contraste, variantes e política de movimento;
- **Entrega** — gates com evidência e resumo JSON;
- **Catálogo** — tipos, vocabulários, presets e limites.

A prévia usa `<iframe sandbox="">`: nenhum script do artefato executa. O botão **Baixar** grava o arquivo localmente; nada é enviado a servidor.

---

## Limites

- **Sem navegador:** o piso de texto de 8,4 px é estimativa de projeto, não medição. Overflow horizontal de texto real não é verificado.
- **Sem código-fonte:** o desenho só afirma o que a especificação declara. Não há leitura de repositório nem prova de código no nó.
- **Sem renderização de terceiros:** Mermaid e DOT são exportados como texto; o JARVIS não os desenha.
- **Sem captura:** nenhuma imagem do desenho é gerada; a prévia é o próprio SVG.
- **Sem reposicionamento automático:** a rodada de reposicionamento é sugerida, não aplicada.
- **Sem ícones e marcas:** o recorte usa tipo, etiqueta e membros no lugar do catálogo de 23 ícones e das marcas de produto.
- **Falsos positivos:** a folga é calculada por caracteres e a interseção é geométrica; texto real pode ser mais estreito que a estimativa.

---

## Como rodar e testar

```bash
npm run dev
curl -s http://localhost:8000/api/health   # 0.62.3, 288 skills
curl -s -X POST http://localhost:8000/api/skills/diagram.type/execute \
  -H 'Content-Type: application/json' \
  -d '{"parameters":{"pedido":"onde o tempo foi num checkout lento"}}'
```

```bash
.venv/bin/python -m pytest server/tests --tb=short -q
npx vitest run
npx tsc --noEmit
npm run build
```

São **72 testes de diagrama** em `server/tests/test_diagram.py` (roteador, IR válido e inválido, hierarquia, datas, orçamento, determinismo do layout, cruzamento medido, folga de rótulo, desenho dos dez tipos, escape de HTML, formatos, legenda, gates e API) e **42 testes editoriais** em `server/tests/test_editorial.py` (catálogo de 45 tipos, seleção por padrão, contraste com proposta de ajuste, os 12 anti-padrões, as 6 regras de conector, os três parsers de importação, a escada, o contrato de entrega e a API).

---

## Licença e atribuição

Dois upstreams, ambos MIT:

- [`tt-a1i/archify`](https://github.com/tt-a1i/archify) — `Copyright (c) 2026 tt-a1i (Archify)` e `Copyright (c) 2025 Cocoon AI`, texto integral em [`licenses/tt-a1i-archify.txt`](licenses/tt-a1i-archify.txt);
- [`cathrynlavery/diagram-design`](https://github.com/cathrynlavery/diagram-design) — `Copyright (c) 2025 Cathryn Lavery`, texto integral em [`licenses/cathrynlavery-diagram-design.txt`](licenses/cathrynlavery-diagram-design.txt).

A implementação deste repositório é independente: o código Python, o vocabulário em português, os presets, os textos das skills e o HTML gerado foram escritos aqui. O que veio dos estudos foi o **recorte de valor** — tipos, IR validado, geometria medida, gates de entrega, papéis de cor, orçamentos, as seis regras de conector e a escada de degradação —, não arquivos dos projetos originais.
