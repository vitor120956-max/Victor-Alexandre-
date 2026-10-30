# Direção de arte

Adaptação própria, em português, de ideias observadas em [`Leonxlnx/taste-skill`](https://github.com/Leonxlnx/taste-skill) — licença **MIT**, Copyright (c) 2026 Leonxlnx. O texto integral está em [`licenses/leonxlnx-taste-skill.txt`](licenses/leonxlnx-taste-skill.txt).

O JARVIS **não instala nem executa** nada do upstream: não há `npx skills add`, plugin de Claude/Codex, `install.sh`, SDK de agente, `draw.mjs`, `inspect.mjs`, `assets.mjs` nem `scenes.mjs` — esses scripts exigem Node 22 e Chrome e não são chamados aqui. O que existe é uma leitura estática, determinística e somente leitura do que você declara: briefing, argumento, deck de copy, HTML/CSS, texto para os tells e notas de júri.

## O que foi adaptado

| Upstream | Aqui |
|---|---|
| Sorteio de uma entre 20 direções com `draw.mjs --sector --brief --sections --tone --have --keep` | Sorteio determinístico de três entre **12 direções próprias** em português, com semente SHA-256 e ficha da escolhida |
| Ficha com herói, tipo, paleta, imagens, movimento e seções | A mesma ficha, com blueprint por papel de seção, armadilhas e redesenhos registrados |
| Redesenho só com motivo declarado | `peça | motivo` com no mínimo 20 caracteres; trocar a direção inteira vira achado |
| Argumento em afirmações + prova, antes do desenho | `taste.argument` exige prova por seção e reconhece número sem fonte como prova inventada |
| Copy deck com orçamento de título, apoio, corpo, ações e navegação | `taste.copy` mede o deck e aplica as formas proibidas e a micro-tipografia |
| `lint.mjs` com ~22 regras, isenções e modo app | **29 regras** próprias, em página ou app, com isenções declaradas |
| `tells.md` datado em ondas | **25 tells** em três ondas, com onda dominante e contramedida |
| Crítica de 14 passes com pesos 40/30/20/10 e tabela de caps | `taste.judge` pondera as quatro dimensões, aplica **16 tetos** e devolve a ordem de correção |
| Estudo de 247 sites de galeria | As medidas citadas nas regras vêm do estudo descrito pelo upstream e são tratadas como referência, não como laudo |

Fora do escopo por decisão: `draw.mjs`, `inspect.mjs`, `assets.mjs`, `scenes.mjs`, biblioteca JSON de 20 direções, 1.000+ fotos, CDP/Chrome, captura em 1440/768/390, geração de imagens, análise de movimento ao vivo, 14 passes automáticos e qualquer plugin ou marketplace de agentes.

## Página Direção (`/direcao`)

Sete abas:

- **Direção** — briefing, setor, tom, seções, ativos, peças de marca, semente, escolha e redesenhos;
- **Argumento** — sujeito, afirmações e provas, título, apoio e ação;
- **Copy** — deck `peça | texto`;
- **Regras** — HTML ou CSS, em superfície de página ou app;
- **Tells** — texto ou fonte confrontada com o registro datado;
- **Júri** — quatro notas com evidência e os sinais de teto;
- **Biblioteca** — vocabulário completo, tetos e ondas, lido de `taste.library`.

Cada formulário tem **Carregar exemplo**. O nível `lite` devolve só bloqueios; `full` inclui correções; `ultra` acrescenta perguntas para a revisão. Tudo é `executed: false` e `readOnly: true`.

## Direção

### Vocabulário

| Dimensão | Valores |
|---|---|
| Setor (10) | `alimentacao`, `hospitalidade`, `software`, `portfolio`, `evento`, `varejo`, `servico`, `cultura`, `saude`, `imovel` |
| Tom (7) | `quieto`, `ousado`, `quente`, `tecnico`, `ludico`, `luxo`, `editorial` |
| Ativo (5) | `fotografia`, `produto`, `interface`, `ilustracao`, `video` |
| Peça preservada (2) | `paleta`, `tipografia` |
| Papel de seção (16) | `intro`, `sobre`, `trabalho`, `galeria`, `vitrine`, `como-funciona`, `recursos`, `prova`, `numeros`, `preco`, `faq`, `depoimento`, `contato`, `lista`, `cta`, `rodape` |

Aliases comuns são aceitos (`food`, `menu`, `warm`, `saas`, `case`). Valor fora do vocabulário vira achado `must` e o filtro correspondente é desligado — o sorteio continua, mas a ficha perde afinidade.

### As 12 direções

| Direção | Tese |
|---|---|
| A fachada (`fachada`) | A rua entra antes da marca: toldo, vitrine, endereço e o que está aberto agora. |
| O arquivo (`arquivo`) | O acervo é o argumento: fichas, datas, procedência e o que já foi feito. |
| O campo de cor (`campo`) | Uma cor ocupa a página inteira e o conteúdo se organiza como amostras de tinta. |
| A carta (`carta`) | Voz de correspondência: papel, remetente, parágrafo curto e assinatura. |
| O mapa (`mapa`) | O lugar organiza a leitura: distância, rota, ponto de encontro e horário. |
| O mostruário (`mostruario`) | Objetos em close, ficha técnica ao lado e preço dito sem rodeio. |
| O cinema (`cinema`) | Uma cena por seção, crédito de imagem e ritmo de projeção. |
| A oficina (`oficina`) | Processo exposto: matéria-prima, etapa, ferramenta e o que está em conserto. |
| A vitrine (`vitrine`) | O produto na altura do olho, com a mão que o segura e a etiqueta honesta. |
| O cartaz (`cartaz`) | Uma frase grande, uma imagem e o evento; sem menu de sete itens. |
| O boletim (`boletim`) | Notícia curta, data visível e hierarquia de jornal local. |
| O passeio (`passeio`) | A página se percorre como um trajeto, com paradas numeradas pelo lugar. |

Cada direção declara setores e tons de afinidade, ativos necessários, paleta, tipo, imagens, movimento, blueprint por papel, armadilhas e o que evitar.

### Sorteio e ficha

- a semente é SHA-256 de briefing + setor + tom + seções, reduzida a 12 caracteres;
- a mesma semente devolve sempre a mesma mão; o campo `seed` aceita `[a-z0-9-]{2,32}`;
- as três opções vêm ordenadas por afinidade de setor e tom;
- cada opção mostra o que a sustenta (`fit`) e o que ela vai cobrar (`tension`);
- a ficha só é montada quando você escolhe uma direção (`direction`), e só essa escolha habilita os redesenhos;
- `keep=paleta` ou `keep=tipografia` preserva a marca: a paleta vira `mode: brand` e a tipografia é mantida, com a direção entrando pela composição.

Redesenhos aceitam `hero`, `type`, `palette`, `photos`, `scenes`, `direction` e `section:<papel>`. Motivo com menos de 20 caracteres é bloqueio; `direction` isolado é um achado `should`, porque trocar a direção inteira desfaz o estudo.

## Argumento

Entrada: `papel | afirmação | prova`, uma seção por linha, com 1 a 120 linhas. O papel usa o mesmo vocabulário de seções da direção.

Achados:

| Grupo | Achado | Regra |
|---|---|---|
| obrigatório | `empty-claim` | Seção sem afirmação é preenchimento |
| obrigatório | `claim-without-proof` | Toda afirmação pede prova |
| obrigatório | `invented-proof` | Número, prêmio ou avaliação na afirmação sem fonte na prova |
| obrigatório | `missing-headline` | Sem título declarado |
| obrigatório | `long-headline` | Acima de 42 caracteres |
| obrigatório | `missing-support` | Sem linha de apoio |
| obrigatório | `missing-action` | Sem ação principal |
| correção | `headline-tight` | Entre 33 e 42 caracteres |
| correção | `correction-copy` | “Não é X, é Y” |
| correção | `stock-phrase` | Vocabulário de catálogo |
| correção | `stock-order` | Ordem padrão hero → recursos → prova → preço → ação |
| correção | `duplicate-section` | Mesmo papel duas vezes |
| correção | `generic-action` | “Saiba mais”, “Comece agora” |
| correção | `em-dash-budget` | Mais de três travessões |
| dica | `headline-words`, `colon-headline`, `headline-period`, `action-long` | Ajustes de forma |

A prova inventada é lexical: a afirmação precisa conter número, percentual, avaliação, prêmio ou contagem e a prova precisa conter fonte, link, ano, relatório, pesquisa ou recorte. Falso positivo é possível e declarado.

## Copy

Entrada: `peça | texto`, uma peça por linha. Papéis: `manchete`, `apoio`, `corpo`, `acao`, `nav`, `legenda`, `statement`, `rotulo`, `eyebrow`.

Limites e formas:

- título até **32 caracteres** é confortável; acima de **42** é bloqueio; mais de sete palavras é dica;
- linha de apoio até **22 palavras**, sem repetir o título;
- ação de uma a três palavras, nomeada pelo resultado; rótulo de prateleira é correção;
- uma única ação principal por tela; navegação com até cinco links;
- `statement` acima de 25 palavras vira parágrafo;
- sobrancelha (`eyebrow`) é bloqueio;
- micro-tipografia: aspas curvas, reticências reais, travessão com parcimônia, nada de caixa alta em sequência;
- `lorem ipsum` e texto de exemplo são bloqueio.

## Regras (linter)

29 regras lexicais. Grupo `must` falha, `should` avisa e `nice` é dica. No modo `app`, `mono`, `numbering`, `eyebrow`, `hairline` e `default-font` são desligadas, e `placeholder-data` e `framework-blue` entram.

| Regra | Grupo | Regra | Grupo |
|---|---|---|---|
| `gradient-text` | falha | `gradient` | aviso |
| `mono` | aviso | `numbering` | aviso |
| `eyebrow` | aviso | `micro-label` | aviso |
| `purple` | falha | `claude-palette` | dica |
| `emoji` | aviso | `lorem` | falha |
| `hairline` | aviso | `pill` | aviso |
| `shadow` | aviso | `text-shadow` | aviso |
| `glass` | aviso | `stock-copy` | aviso |
| `cta-copy` | dica | `default-font` | dica |
| `transition-all` | aviso | `ease-in` | dica |
| `scale-zero` | aviso | `h-screen` | dica |
| `bounce` | aviso | `outline-none` | aviso |
| `important` | dica | `zindex` | dica |
| `placeholder-data` | aviso | `framework-blue` | aviso |
| `em-dash` | dica | `no-h1` | falha |
| `few-images` | aviso | | |

Isenções: conteúdo dentro de `<pre>`, `<code>`, `<table>` e `<form>`; elementos com `data-ui`; comentários HTML e CSS; e qualquer linha que contenha `taste-skill-ignore`. A contagem de isenções aparece no parecer.

## Tells

O registro é datado por onda. Cada tell traz o que é, por que envelheceu, a correção e o custo de ignorar.

| Onda | Sinais | Tells |
|---|---|---|
| 1 · 2023 | vidro, gradiente roxo, ícone genérico | `glass`, `purple-gradient`, `icon-cards`, `mockup-hero`, `emoji-title`, `unlock` |
| 2 · 2024–2025 | micro-rótulo, numeração, fio de 1 px, mobília editorial | `eyebrow`, `numbering`, `hairline`, `mono-label`, `shadow-rest`, `status-dot`, `est-year`, `coordinates`, `tricolon`, `not-x-but-y`, `micro-caps` |
| 3 · 2026 | creme e terracota, serifa apertada, manchete-parágrafo | `cream-terracotta`, `serif-tight`, `headline-paragraph`, `colon-brand`, `styled-word`, `gradient-drift`, `reveal`, `editorial-furniture` |

O parecer devolve a onda dominante, a densidade por mil palavras e o registro completo com a marcação do que foi encontrado. A varredura é lexical: o que é puramente de composição — margem desigual, vazio, hierarquia — fica para o júri.

## Júri

Pesos fixos:

| Dimensão | Peso |
|---|---|
| Design | 40 |
| Usabilidade | 30 |
| Criatividade | 20 |
| Conteúdo | 10 |

As quatro notas são obrigatórias e cada uma precisa de evidência com referência; não existe nota parcial. A média ponderada é calculada, cada sinal marcado como `sim` aplica o teto correspondente e a nota final é o menor valor entre a média e os tetos globais.

| Sinal | Alvo | Teto |
|---|---|---|
| `lint-fail` | final | 6,0 |
| `manchete-longa` | final | 6,5 |
| `manchete-problema` | final | 6,0 |
| `eyebrow` | final | 6,5 |
| `mono` | final | 6,5 |
| `numeracao` | final | 6,5 |
| `gradiente` | final | 6,5 |
| `sombra` | final | 6,5 |
| `fio` | final | 6,5 |
| `margens-desiguais` | final | 6,5 |
| `faixa-em-branco` | final | 5,0 |
| `sem-titulo` | final | 6,0 |
| `serviria-a-qualquer-um` | criatividade | 6,0 |
| `menos-de-4-fotos` | design | 6,5 |
| `sem-coisa-viva` | criatividade | 7,5 |
| `sem-botao-real` | usabilidade | 7,0 |

Bandas: **8,5–10 excepcional**; **7,5–8,4 pronto**; **6,5–7,4 com ressalvas**; **6,0–6,4 abaixo**; **0–5,9 não publicar**. O parecer mostra a média bruta, a média com tetos de dimensão, a perda, os tetos aplicados, o eixo mais fraco, os três problemas e a ordem de correção em oito passos — ideia, hierarquia, composição, tipografia, imagens, cor, detalhe e movimento.

## Skills

| Skill | Entrada | Devolve |
|---|---|---|
| `taste.direction` | `brief`, `sector`, `sections`, `tone`, `have`, `keep`, `seed`, `direction`, `redraws` | Três opções, semente, ficha, redesenhos, achados |
| `taste.argument` | `brief`, `claims`, `headline`, `support`, `action` | Seções com estado, métricas de título e achados |
| `taste.copy` | `deck` | Deck auditado, métricas e achados |
| `taste.lint` | `source`, `surface` | Regras acionadas, isenções e achados |
| `taste.tells` | `text`, `kind` | Onda dominante, densidade, registro e achados |
| `taste.judge` | `scores`, `signals` | Nota, banda, tetos, ordem e três problemas |
| `taste.library` | vazio | Direções, vocabulário, tetos e ondas |

## Como usar

Na página **Direção** (`/direcao`), carregue um exemplo e execute. Pela API:

```bash
curl -s http://localhost:8000/api/skills/taste.direction/execute \
  -H 'content-type: application/json' \
  -d '{"parameters": {"brief": "Padaria de fermentação natural na rua das Palmeiras, 7 anos de forno a lenha.", "sector": "alimentacao", "tone": "quente", "sections": "sobre, vitrine, como-funciona, contato", "have": "fotografia"}}'

curl -s http://localhost:8000/api/skills/taste.tells/execute \
  -H 'content-type: application/json' \
  -d '{"parameters": {"text": "Não é só uma padaria, é um laboratório. Est. 2024. Rápido. Simples. Seguro."}}'
```

A API responde `200` com `{ok: false, error}` quando a entrada é recusada — nunca `4xx` para erro de skill.

## Verificação

```bash
.venv/bin/python -m pytest server/tests -q
npx tsc --noEmit
npx vitest run
npm run build
curl -s http://localhost:8000/api/health   # 0.62.4, 288 skills
```

A suíte cobre determinismo do sorteio, semente, ficha por seção, preservação de paleta e tipo, redesenho sem motivo, vocabulário inválido, prova sem fonte, orçamento de título, formas proibidas, deck limpo e sujo, as 29 regras, isenções, modo app, ondas de tells, pesos e tetos do júri, revisão incompleta, biblioteca e os sete endpoints.

## Limites desta etapa

- Nada é desenhado, renderizado ou publicado: a ficha é um contrato para você executar.
- A biblioteca é própria e embutida: 12 direções em português, não as 20 do upstream; 25 tells, não o registro completo.
- O sorteio é determinístico, mas não vê imagens, não avalia o seu projeto real e não mede a quebra de linha do título no navegador.
- Toda a varredura é lexical: falso positivo é possível e está declarado em cada parecer.
- As notas e os sinais são declarados por quem revisa; a skill pondera, aplica tetos e confere evidência — não audita a página.
- Nenhum script Node, navegador, plugin ou CLI do upstream é instalado, chamado ou executado.
