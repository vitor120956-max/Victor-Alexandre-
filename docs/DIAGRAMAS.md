# Diagramas

Dez tipos de diagrama com **especificação JSON própria**, validação estrutural, layout medido e entrega em **HTML autocontido**. A adaptação parte de [`tt-a1i/archify`](https://github.com/tt-a1i/archify) (MIT, 2026), mas o código é local: nenhum CLI, template, pacote, plugin ou navegador do upstream é instalado ou executado.

O upstream transforma uma ideia, plano ou repositório em um diagrama interativo de página única. O valor que sobrevive sem navegador é o **IR validado**, o **roteador de tipos**, as **regras de geometria** e o **contrato de entrega**. É isso que a versão 0.12.0 traz, em português e com vocabulário próprio.

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

## As sete skills

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
curl -s http://localhost:8000/api/health   # 0.16.0, 93 skills
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

São **72 testes de diagrama** em `server/tests/test_diagram.py`: roteador nos dez tipos, IR válido e inválido, hierarquia, datas, orçamento, determinismo do layout, cruzamento medido, folga de rótulo, desenho dos dez tipos, escape de HTML, formatos, legenda, gates e API.

---

## Licença e atribuição

O upstream é MIT: `Copyright (c) 2026 tt-a1i (Archify)` e `Copyright (c) 2025 Cocoon AI`. O texto integral está em [`licenses/tt-a1i-archify.txt`](licenses/tt-a1i-archify.txt).

A implementação deste repositório é independente: o código Python, o vocabulário em português, os presets, os textos das skills e o HTML gerado foram escritos aqui. O que veio do estudo foi o **recorte de valor** (tipos, IR validado, geometria medida, gates de entrega), não arquivos do projeto original.
