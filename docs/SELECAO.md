# Seleção de skills

Escolher entre milhares de skills sem chutar: ler o briefing, ranquear o catálogo com uma conta explícita, cobrir as dez dimensões de capacidade, validar a stack contra o índice e montar um plano com checagem de saída.

A camada parte do **AAS Core** do [`sickn33/agentic-awesome-skills`](https://github.com/sickn33/agentic-awesome-skills) — **MIT**, 48 mil estrelas, 2.743 skills em 114 categorias. O Core entrega descoberta, seleção pelo agente, validação de stack e plano, mas recusa pontuar: o `search_skills` devolve ordem estável **sem score** e o `compose_stack` só confere ids. Aqui está o que ele deliberadamente não faz — e com a conta à vista.

| Camada | O que faz | Toca a rede? |
|---|---|---|
| **Motor** (`server/selecao.py`, 7 skills) | Ranqueia por BM25, mede cobertura por dimensão, valida ids, soma risco e ordena fases | **Não** — só o JSON colado |
| **Página** (`/selecao`) | Aba por verbo, filtros por categoria, risco e alvo, tabela de evidência e parecer para copiar | Não |

Nada é baixado, instalado, composto ou gravado: o catálogo é o JSON (ou as linhas) que você cola, e cada resposta marca `executed: false`.

## As sete skills

| Rota | Entrada | O que devolve |
|---|---|---|
| `selecao.brief` | briefing | dimensões tocadas, entregáveis, restrições, critério de sucesso e público |
| `selecao.buscar` | briefing, catálogo, filtros | ranking com score, termos que casaram e cobertura das dimensões |
| `selecao.stack` | briefing, ids, catálogo, alvo | id inválido, repetido, lacuna, sobreposição, risco e compatibilidade |
| `selecao.plano` | briefing, ids, catálogo | fases com artefato, checagem, dependência e portão de aprovação |
| `selecao.cobertura` | briefing, catálogo | por dimensão: quantas skills, as melhores candidatas e a lacuna |
| `selecao.catalogo` | catálogo | saúde do índice: campos, ids, caminhos, risco e distribuição |
| `selecao.regras` | nada | léxico, pesos do BM25, pontos de risco, artefatos do plano e limites |

Todas aceitam `modo` com `lite`, `full` (padrão) ou `ultra`.

O catálogo entra em três formatos: o **JSON** do `skills_index.json` (lista ou objeto com `skills`), a lista de **ids** para a stack, e as **linhas compactas** `id | categoria | descrição` ou `id | categoria | risco | descrição`. O formato compacto existe por tamanho: o índice completo tem 2,1 MB em JSON e 506 KB em linhas — quatro vezes menor e bem abaixo do teto de 1,8 MB da skill.

## 1. O briefing

Dez dimensões de capacidade, tiradas do contrato de cobertura que o Core entrega aos clientes MCP: arquitetura/runtime, linguagens/frameworks, domínio, dados, integrações, testes/qualidade, segurança/privacidade, experiência/acessibilidade, deploy/operação e manutenção. O briefing é lido contra um léxico fechado por dimensão; o que casar vira linha com a palavra que casou.

O que o briefing precisa declarar, e o que acontece quando falta:

| Achado | Peso | Quando |
|---|---|---|
| `brief-curto` | must | menos de 20 palavras |
| `brief-sem-objetivo` | must | nenhuma dimensão e nenhum entregável reconhecido |
| `sem-criterio-de-sucesso` | should | nenhuma meta, número ou aceite |
| `sem-restricao` | should | sem prazo, orçamento, equipe, compliance ou escala |
| `sem-entregavel` | should | não diz o artefato: api, app, site, painel, relatório, deck |
| `sem-publico` | nice | não nomeia usuário, cliente ou time |
| `brief-difuso` | nice | toca mais de seis dimensões |
| `brief-longo` | nice | mais de 400 palavras |

Entregáveis são reconhecidos por léxico próprio (api, app, site, painel, relatório, deck, planilha, documento, bot, cli, plugin, dados) e as restrições por padrão: prazo, orçamento, equipe, compliance e escala.

## 2. A busca

BM25 clássico com `k1 = 1,2` e `b = 0,75`, sobre um documento que repete o nome três vezes, a categoria duas e a descrição uma — o mesmo truque de peso por campo que os buscadores usam, escrito para poder ser conferido.

```text
score = Σ idf(t) · (tf · (k1 + 1)) / (tf + k1 · (1 − b + b · |D| / |D|médio))
idf(t)  = ln(1 + (N − df(t) + 0,5) / (df(t) + 0,5))
```

A normalização remove acento e caixa e **indexa plural e singular juntos**, para que "teste" e "testes" caiam no mesmo termo. Filtros por categoria (trecho), risco e alvo são aplicados antes do ranking; o limite padrão é 8 e o máximo 50.

| Achado | Peso | Quando |
|---|---|---|
| `nenhum-resultado` | must | nenhum documento contém os termos |
| `filtro-sem-resultado` | must | o filtro zerou o catálogo |
| `score-baixo` | should | melhor score abaixo de 1,0 |
| `cobertura-parcial` | should | as dimensões do briefing não aparecem nos candidatos |
| `termos-poucos` | should | menos de dois termos úteis depois das palavras vazias |
| `empate-no-topo` | nice | diferença de até 0,05 entre o primeiro e o segundo |

Com o briefing de exemplo — cobrança com Stripe, SaaS em Next.js, testes, deploy na Vercel, LGPD, dois devs, seis semanas — e o catálogo real, o topo sai assim:

| # | Skill | Score | Casou com |
|---|---|---|---|
| 1 | `stripe-integration` | 15,93 | api, stripe, checkout |
| 2 | `vercel-cli-with-tokens` | 14,74 | deploy, vercel |
| 3 | `payment-integration` | 13,97 | api, stripe, checkout |
| 4 | `vercel-deployment` | 13,14 | next.js, vercel |
| 5 | `vercel-ai-sdk-expert` | 11,92 | api, next.js, vercel |

## 3. A stack

A validação confere o que o `compose_stack` do Core confere — ids existem, formato é válido — e acrescenta o que ele não opina: cobertura, sobreposição, risco e alvo.

| Achado | Peso | Quando |
|---|---|---|
| `skill-inexistente` | must | id fora do catálogo |
| `id-repetido` | must | mesmo id duas vezes |
| `stack-acima-do-limite` | must | acima do teto técnico de 128 |
| `stack-vazia` | must | nenhum id válido |
| `lacuna-de-dimensao` | must | dimensão do briefing sem skill |
| `alvo-incompativel` | must | skill sem o alvo pedido em `plugin.targets` |
| `sobreposicao` | should | duas skills em ≥2 dimensões com Jaccard ≥ 0,20 |
| `risco-alto` | should | soma de risco acima do limite |
| `setup-manual` | should | `setup.type = manual` |
| `sem-evidencia` | nice | manifesto sem campo de evidência |

O **orçamento de risco** é explícito: `safe` 0, `none` e `unknown` 1, `offensive` 2, `critical` 3, e o limite padrão é 4. Com as quatro skills escolhidas no exemplo, o resultado é 4 pontos e uma lacuna — Testes e qualidade — além de sobreposição entre `stripe-integration` e `payment-integration`, que tocam as mesmas três dimensões com vocabulário quase igual.

## 4. O plano

As skills viram fases na ordem canônica das dimensões, e a fase de cada uma vem da **categoria** quando ela casa (`api-integration` → integrações, `devops` → operação, `web-development` → linguagens); sem categoria que case, vale a dimensão com mais palavras no texto. Cada fase declara artefato, checagem de saída e de qual fase depende.

| Dimensão | Artefato | Checagem de saída |
|---|---|---|
| Arquitetura | decisão de arquitetura | cabe em uma página e nomeia o que fica fora |
| Linguagens | esqueleto do projeto | roda com um comando e sem passo manual |
| Domínio | regra de domínio implementada | um caso de teste passa de ponta a ponta |
| Dados | schema e migração | a migração roda para frente e para trás sem perda |
| Integrações | contrato de integração | documentado e com resposta de erro |
| Qualidade | suíte de teste | falha quando o comportamento quebra |
| Segurança | revisão de segurança | nenhum segredo no repositório |
| Experiência | tela revisada | fluxo principal sem mouse, em 390 px |
| Operação | pipeline de deploy | deploy repetível e rollback ensaiado |
| Manutenção | nota de manutenção | a próxima pessoa entende o porquê |

Quando a stack tem skill `critical` ou `offensive` e o briefing não pede revisão nem aprovação, o plano **bloqueia** com `risco-sem-portao`: o passo mais perigoso não roda sem alguém olhar.

## 5. A cobertura

Por dimensão do briefing: quantas entradas do catálogo a tocam, o percentual, as melhores candidatas por BM25 e — quando nenhuma serve — a lacuna. No catálogo real, com o briefing de exemplo:

| Dimensão | Skills | Cobertura | Melhor candidata |
|---|---|---|---|
| Segurança e privacidade | 423 | 15,4% | `security-compliance-compliance-check` |
| Integrações externas | 414 | 15,1% | `api-integration-architect` |
| Testes e qualidade | 381 | 13,9% | `testing-qa` |
| Deploy e operação | 381 | 13,9% | `devops-deploy` |
| Linguagens e frameworks | 364 | 13,3% | `markstream-install` |
| Comportamento de domínio | 47 | 1,7% | `domain-modeling` |

Domínio com 1,7% acende `dimensao-escassa`: há candidata, mas pouca — e escolher ali é escolher por falta de alternativa.

## 6. O catálogo

O índice real tem 2.743 entradas, 114 categorias, 1.351 marcadas como `critical` (49,3%), 134 indefinidas (4,9%), 22 com setup manual e média de 20,4 palavras por descrição. Nenhuma sem descrição, nenhum id repetido.

| Achado | Peso | Quando |
|---|---|---|
| `sem-descricao` | must | entrada sem descrição |
| `id-duplicado` | must | id repetido no índice |
| `path-fora-do-padrao` | should | caminho fora de `skills/` |
| `id-diferente-do-nome` | should | `name` diverge do id |
| `risco-indefinido` | should | `unknown`, `none` ou vazio |
| `risco-critico-alto` | should | metade ou mais do catálogo em `critical` |
| `descricao-longa` | should | acima de 40 palavras |
| `alvo-ausente` | should | `plugin.targets` vazio |
| `categoria-unica` | nice | categoria com uma entrada só |
| `setup-manual` | nice | setup manual na entrada |

O achado de risco crítico é o mais interessante: metade do catálogo marcada como crítica apaga a distinção, e um catálogo que não separa não serve para triar. No índice atual são 49,3% — a um passo do limiar.

## Exemplo

Com o briefing de cobrança e a stack `stripe-integration`, `payment-integration`, `nextjs-best-practices` e `vercel-deployment`:

- `selecao.brief` → 6 dimensões, 1 entregável (api), 3 restrições, critério de sucesso e público declarados: **nenhum bloqueio**.
- `selecao.buscar` → 2.743 entradas, 5 resultados, melhor score **15,93**, 5 de 6 dimensões cobertas.
- `selecao.stack` → 4 ids válidos, **1 lacuna** (Testes e qualidade), **1 sobreposição**, 4 pontos de risco no limite.
- `selecao.plano` → **3 fases**: linguagens → integrações → operação, com dependência declarada e uma dimensão descoberta.
- `selecao.cobertura` → 6 dimensões, 6 com candidata, média de 12,2% do catálogo por dimensão, 1 escassa.

## O que ficou de fora

Não há embeddings: BM25 casa palavra, não sentido, e paráfrase sem termo em comum não é encontrada. Não há leitura de repositório nem download — o catálogo é o JSON colado, e o que não está nele não existe para a busca. Não há julgamento semântico da skill: a adequação fina continua sendo leitura do SKILL.md. Não há instalação, composição nem gravação de manifesto, e nada é consultado no Core remoto. O limite de texto é 1,8 MB, o de entradas é 3.000 e o de skills por stack é 128, o mesmo do Core.

## Atribuição

Obra original: [`sickn33/agentic-awesome-skills`](https://github.com/sickn33/agentic-awesome-skills), licença **MIT**. O aviso completo está em [`docs/licenses/sickn33-agentic-awesome-skills.txt`](licenses/sickn33-agentic-awesome-skills.txt). Nenhum SKILL.md, descrição ou script do upstream foi copiado: o que veio foi o contrato de cobertura, o vocabulário de risco e o formato do manifesto, reimplementados em Python.

## Contrato

Toda resposta traz `executed: false`, `readOnly: true` e o `mode` herdado do `review`; o `analysis` é prefixado com `selecao.`. Nenhuma skill abre arquivo, chama a rede, instala skill, grava manifesto ou consulta modelo — inclusive a de regras, que devolve o catálogo estático.
