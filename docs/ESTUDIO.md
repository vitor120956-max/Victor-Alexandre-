# Estúdio de design

Adaptação própria, em português, de ideias observadas em [`nexu-io/open-design`](https://github.com/nexu-io/open-design) — licença **Apache-2.0**, Copyright 2026 Open Design contributors. O texto integral está em [`licenses/nexu-io-open-design.txt`](licenses/nexu-io-open-design.txt).

O JARVIS **não instala nem executa** nada do upstream: não há daemon Express/SQLite, CLI `od`, MCP, plugins, Electron, Docker, Sealos, Next.js de estúdio, provedor BYOK, captura de tela ou publicação. O que existe aqui é uma leitura estática, determinística e somente leitura do que você declara: um pacote de design, pares de contraste, notas de crítica e um HTML de arquivo único.

## O que foi adaptado

| Upstream | Aqui |
|---|---|
| Pacote `od-design-system-project/v1` com `manifest.json`, `DESIGN.md` e `tokens.css` | Contrato embutido de 56 slots em 14 grupos, com camadas A1/A2/B |
| Crítica em cinco dimensões com bandas e listas Keep/Fix/Quick wins | Mesmas cinco dimensões, bandas em português e as listas Manter/Corrigir/Ganhos rápidos |
| Regra de contraste 4,5:1 e 3:1 | Cálculo WCAG com AA/AAA para texto normal e grande, repetindo o par mais próximo de AAA |
| Linter anti-slop do daemon | 26 regras lexicais sobre HTML, sem renderizar e sem executar |
| Movimento com ease-out forte, 200/140 ms, sem `scale(0)` | As mesmas convenções viram achados do contrato e do artefato |

Fora do escopo por decisão: catálogo de 151 pacotes, 277 plugins, 100+ skills, 26 CLIs, templates de protótipo/deck, prompts de imagem, HyperFrames/Seedance, geração de artefato, handoff e memória de projeto.

## Página Estúdio (`/estudio`)

Cinco abas:

- **Contrato** — manifesto, `DESIGN.md` e `tokens.css`;
- **Contraste** — pares `rótulo | frente | fundo | tamanho`;
- **Crítica** — cinco notas com evidência e as três listas de ação;
- **Artefato** — HTML de arquivo único;
- **Base** — referência de slots, bandas, dimensões, movimento e limites, lida de `studio.defaults`.

Cada formulário tem **Carregar exemplo** com dados completos e clicáveis para demonstrar o fluxo. O nível `lite` devolve só bloqueios; `full` inclui correções; `ultra` acrescenta perguntas para a revisão. Tudo é `executed: false` e `readOnly: true`.

## Contrato

### `manifest.json`

- `schemaVersion` precisa ser exatamente `od-design-system-project/v1`;
- `id` é slug ASCII minúsculo (`acme-papel`), igual ao nome da pasta;
- `files.design` precisa ser `DESIGN.md` e `files.tokens`, `tokens.css`;
- caminhos precisam ser relativos: `/`, `\` e `..` são bloqueio;
- `source.type` é obrigatório para proveniência; `name`, `category` e `description` são recomendados;
- manifesto ausente não é erro se você enviar prosa e tokens; manifesto presente exige `files`.

Limite: 20.000 caracteres.

### `DESIGN.md`

- pelo menos **7 títulos H2 substantivos** (o exemplo cobre tema, cor, tipografia, espaçamento, componentes, movimento, acessibilidade e antíteses);
- H1 recomendado como nome legível;
- seção com menos de 40 caracteres de conteúdo vira achado `should`;
- `lorem ipsum`, `todo:`, `tbd` e `preencher depois` são bloqueio;
- `DESIGN.md` ausente quando há tokens ou manifesto é um achado `should`, porque a prosa é o que o agente lê para decidir.

Limite: 120.000 caracteres.

### `tokens.css`

O contrato tem **56 slots em 14 grupos**. Slots A1 são identidade sem fallback; A2 têm fallback declarado; B são slots de consistência que podem apontar para o irmão nomeado.

| Grupo | Slots |
|---|---|
| Superfícies (3) | `--bg`, `--surface`, `--surface-warm` |
| Texto (4) | `--fg`, `--fg-2`, `--muted`, `--meta` |
| Bordas (2) | `--border`, `--border-soft` |
| Acento (4) | `--accent`, `--accent-on`, `--accent-hover`, `--accent-active` |
| Estados semânticos (3) | `--success`, `--warn`, `--danger` |
| Famílias tipográficas (3) | `--font-display`, `--font-body`, `--font-mono` |
| Escala tipográfica (8) | `--text-xs` … `--text-4xl` |
| Entrelinha e kerning (3) | `--leading-body`, `--leading-tight`, `--tracking-display` |
| Espaçamento (8) | `--space-1` … `--space-12` |
| Ritmo de seção (3) | `--section-y-desktop`, `--section-y-tablet`, `--section-y-phone` |
| Raios (4) | `--radius-sm`, `--radius-md`, `--radius-lg`, `--radius-pill` |
| Elevação e foco (4) | `--elev-flat`, `--elev-ring`, `--elev-raised`, `--focus-ring` |
| Movimento (3) | `--motion-fast`, `--motion-base`, `--ease-standard` |
| Layout (4) | `--container-max`, `--container-gutter-desktop`, `--container-gutter-tablet`, `--container-gutter-phone` |

Achados do contrato de tokens:

| Grupo | Achado | Regra |
|---|---|---|
| obrigatório | `missing-tokens` | Slot do esquema ausente em `:root` |
| obrigatório | `empty-token` | Declaração sem valor |
| obrigatório | `undefined-token` | `var()` aponta para token não declarado |
| obrigatório | `reduced-motion` | Há transição/animação e nenhuma consulta de movimento reduzido |
| obrigatório | `tokens-missing` | Só prosa ou manifesto enviados |
| corrigir | `theme-parity` | Tema não redefine `--bg` e `--fg` |
| corrigir | `raw-color` | Hexadecimal ou `rgb()` dentro de regra de componente |
| corrigir | `scale-zero` | Animação parte de `scale(0)` |
| corrigir | `ease-in` | Curva `ease-in` em interface |
| corrigir | `ease-standard-weak` | `--ease-standard` sem ease-out ou `cubic-bezier` |
| opcional | `theme-shallow` | Tema redefine menos de quatro tokens de superfície/texto/borda/acento |
| opcional | `unknown-token` | Token fora do esquema e sem citação no `DESIGN.md` |
| opcional | `unused-token` | Extensão declarada e nunca usada em `var()` |

O parser cobre blocos simples de CSS, `:root`, seletores de tema (`[data-theme]`, `.dark`) e regras de componente. Aninhamento profundo, valores calculados e `color-mix()` ficam fora.

## Contraste

Entrada: uma linha por par, no formato `rótulo | frente | fundo | corpo|grande`. Até 120 linhas e 400 caracteres por campo. Só hexadecimal de 3 ou 6 dígitos é medido.

| Texto | AA | AAA |
|---|---|---|
| Normal | 4,5:1 | 7,0:1 |
| Grande | 3,0:1 | 4,5:1 |

- `contrast-fail` (obrigatório) quando a razão fica abaixo de AA;
- `contrast-aaa` (opcional) aparece **uma vez**, no par mais próximo de AAA, para não repetir o mesmo conselho;
- `missing-color` e `invalid-color` impedem a medição e são obrigatórios;
- o resultado traz cada par com razão, limites, nível e linha, além da pior razão.

Limites: luminância relativa WCAG 2.x, sem simular opacidade herdada, fundo composto por imagem, daltonismo, tamanho real de fonte ou peso.

## Crítica

Entrada: `dimensão | nota inteira 0–10 | evidência`. As cinco dimensões são fixas:

1. **Filosofia** — uma direção clara sustenta cada micro-decisão?
2. **Hierarquia** — um estranho sabe o que ler primeiro, sem legenda?
3. **Detalhe** — alinhamento, entrelinha, enquadramento e polimento?
4. **Função** — o artefato cumpre o trabalho para o qual existe?
5. **Inovação** — existe um momento que faz alguém se inclinar?

Bandas: **Quebrado** 0–4, **Funcional** 5–6, **Forte** 7–8, **Excepcional** 9–10. O veredito usa a banda do eixo mais fraco, não a média; o resultado também devolve `radar` para desenhar a página.

Achados:

- `unknown-dimension`, `duplicate-dimension`, `invalid-score`, `thin-evidence` e `missing-dimension` são obrigatórios;
- `no-citation` (corrigir) quando a evidência não cita classe, seletor, arquivo, linha, página ou medida;
- `grade-inflation` (corrigir) quando a média passa de 8;
- `no-weak-axis` (opcional) quando todas as notas são 7 ou mais;
- `manter-short`, `corrigir-short` e `ganhos rápidos-short` quando faltam itens (mínimo 3 em cada lista);
- `win-without-time` quando um ganho não declara minutos; `win-out-of-range` quando sai da faixa 5–15.

A skill **não vê** o artefato: valida disciplina de notas, evidência e listas. Revisar o próprio artefato na mesma rodada em que ele foi gerado continua sendo um viés registrado.

## Artefato

Entrada: HTML de arquivo único, até 200.000 caracteres. O linter remove comentários, separa `<style>`, `:root` e o corpo, e não renderiza nem executa nada. Emoji só é avaliado fora de `code` e `pre`.

| Regra | Grupo | O que procura |
|---|---|---|
| `purple-gradient` | obrigatório | Gradiente roxo/violeta |
| `trust-gradient` | obrigatório | Azul→ciano em gradiente |
| `indigo-accent` | obrigatório | Índigo padrão fora de `:root` |
| `emoji-icon` | obrigatório | Emoji como ícone de recurso |
| `invented-metric` | obrigatório | `10x faster`, `99.9% uptime`, `zero downtime` |
| `filler-copy` | obrigatório | Lorem ipsum e textos de exemplo |
| `sans-display` | obrigatório | Título em Inter/Roboto/system-ui |
| `external-css` | obrigatório | `<link rel="stylesheet">` |
| `external-import` | obrigatório | `@import` remoto |
| `external-js` | obrigatório | `<script src>` |
| `missing-alt` | obrigatório | `<img>` sem `alt` |
| `no-reduced-motion` | obrigatório | Movimento sem alternativa reduzida |
| `no-doctype` | corrigir | Sem `<!doctype html>` |
| `no-lang` | corrigir | `<html>` sem `lang` |
| `no-title` | corrigir | Sem `<title>` |
| `no-viewport` | corrigir | Sem meta viewport |
| `raw-color` | corrigir | Hexadecimal fora de `:root` |
| `blank-noopener` | corrigir | `target="_blank"` sem `rel` |
| `caps-no-tracking` | corrigir | Caixa alta sem `letter-spacing` |
| `external-image` | corrigir | Imagem remota |
| `scale-zero` | corrigir | Animação de `scale(0)` |
| `left-accent` | corrigir | Cartão com barra de acento à esquerda |
| `inline-handler` | opcional | `onclick` e afins no HTML |
| `accent-overuse` | opcional | `var(--accent)` mais de 8 vezes |
| `smart-quotes` | corrigir | Aspas curvas em `code`/`pre` |
| `iframe-sandbox` | corrigir | `<iframe>` sem `sandbox` |

O linter é lexical: aceita falso positivo em troca de um trecho de evidência por achado. Contraste real depende de fundo composto, e o julgamento visual continua humano.

## Skills

| Skill | Entrada | Limite |
|---|---|---|
| `studio.contract` | `manifest`, `design`, `tokens`, `mode` | 20k / 120k / 120k |
| `studio.contrast` | `pairs`, `mode` | 50k, até 120 linhas |
| `studio.critique` | `entries`, `keep`, `fix`, `quickWins`, `mode` | 50k nas notas, 8k por lista |
| `studio.artifact` | `artifact`, `mode` | 200k |
| `studio.defaults` | — | referência estática |

Todas devolvem `findings` em quatro partes (o que é, problema, correção, se ignorar), contagens `must`/`should`/`nice`, veredito determinístico, perguntas no nível `ultra`, `limitations`, `markdown`, `rows`, `metrics`, `executed: false` e `readOnly: true`. `studio.critique` acrescenta `radar`, `bands`, `keep`, `fix` e `quickWins`.

## Como usar

Pela página `/estudio`, pela paleta (`Ctrl/Cmd + K`) ou pela conversa:

```text
abrir estúdio
design system
revisar contraste
criticar design
revisar artefato de design
```

Pela API:

```bash
curl -s http://localhost:8000/api/health   # 0.12.0, 65 skills

curl -s http://localhost:8000/api/skills/studio.contrast/execute \
  -H 'content-type: application/json' \
  -d '{"parameters":{"pairs":"Corpo | #18181b | #faf9f6 | corpo"}}'
```

A API de skills sempre responde HTTP 200: `{ok: true, skill, dryRun, result, durationMs, executedAt}` ou `{ok: false, error: {code, message}}`.

## Verificação

- `server/tests/test_studio.py`: contrato, manifesto, prosa, 56 slots, temas, movimento, tokens desconhecidos, contraste, cinco dimensões, inflação, listas, 26 regras do artefato e a API;
- `npm test`: Vitest do parser em português e pytest da API;
- `npm run build`: TypeScript e bundle de produção.

Os fixtures são sintéticos e não baixam nenhum pacote do upstream.

## Limites desta etapa

- Tudo é declarado: nada é lido do repositório do pacote, compilado, renderizado ou publicado.
- O esquema de 56 slots é embutido, não sincronizado com o catálogo de 151 pacotes do upstream.
- O parser de CSS não cobre aninhamento profundo, `@layer`, `color-mix()` ou valores calculados.
- O contraste não simula opacidade, imagem de fundo, daltonismo ou tamanho real de fonte.
- A crítica valida a disciplina do relatório, não inspeciona o artefato.
- O linter é lexical e pode gerar falso positivo; cada achado traz trecho e limite declarado.
- Nenhum daemon, CLI, MCP, plugin, Electron, Docker ou provedor do upstream é instalado ou executado.
