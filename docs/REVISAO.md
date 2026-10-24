# Revisão de código

Revisar um diff grande com agente tem três falhas conhecidas: ele **corta caminho** e cobre só parte do changeset, **erra a linha** do comentário e **varia com o prompt**. A camada de revisão resolve a parte determinística disso — escopo, lote, severidade, âncora, duplicata, cobertura e regra por caminho — e deixa para o modelo a parte que exige leitura.

O insumo é o [`alibaba/open-code-review`](https://github.com/alibaba/open-code-review) — **Apache-2.0**, 48 mil estrelas, Go, dois anos de uso interno na Alibaba. Ele é híbrido: pipelines determinísticos mais agente com LLM. Daqui não veio código Go: veio o desenho — parser de diff unificado com hunks, *bundle* de arquivos relacionados, módulo de posicionamento, regra por caminho em `.opencodereview/rule.json` — reimplementado em Python e medido com fixtures próprias.

| Camada | O que faz | Toca a rede? |
|---|---|---|
| **Motor** (`server/revisao.py`, 7 skills) | Lê diff e achados em texto, mede escopo, agrupa lote, normaliza severidade, confere âncora, compara fontes, mede cobertura e monta `rule.json` | **Não** — só o que foi colado |
| **Página** (`/revisao`) | Aba por verbo, diff e achados de amostra, tabela de evidência, `rule.json` pronto para copiar | Não |

Nada é executado: o diff não é aplicado, o repositório não é lido, nenhum comentário é publicado. Toda resposta marca `executed: false` e `readOnly: true`.

## As sete skills

| Rota | Entrada | O que devolve |
|---|---|---|
| `revisao.escopo` | diff | classe por caminho, churn, risco, segredo em linha nova, migration sem rollback, binário e o que revisar |
| `revisao.lotes` | diff, teto de arquivos | unidades de revisão com código junto do teste e locales juntas, com tokens estimados |
| `revisao.achados` | achados, limite, severidade mínima | severidade e fonte padronizadas, repetido exato junto, inflação de bloqueios e ordem de leitura |
| `revisao.posicao` | diff, achados, tolerância | cada comentário situado: linha adicionada, contexto, perto da adição, fora do hunk, removida ou inexistente |
| `revisao.duplicatas` | achados, similaridade, tolerância | o mesmo problema reportado por regra e por agente, com conflito de gravidade quando as duas discordam |
| `revisao.cobertura` | diff, arquivos revisados | cobertura contra o piso, risco alto esquecido, caminho fora do diff e revisão vazia |
| `revisao.regras` | diff, convenções, teto | `rule.json` com uma regra em prosa por caminho, mesclada ao prompt de sistema |

Todas aceitam `modo` com `lite`, `full` (padrão) ou `ultra`; `lite` devolve só bloqueios e `ultra` acrescenta as perguntas antes de liberar.

## 1. Escopo: 12 classes, e só o que precisa de olho

A classificação vem antes de qualquer conta. A ordem das regras importa: lockfile vence segredo, segredo vence gerado, gerado vence vendor, e assim por diante — um `.env.example` dentro de `node_modules/` é vendor, não segredo.

| Classe | Peso | Revisa? | Exemplo |
|---|---|---|---|
| `segredo` | 5 | sim | `.env`, `id_rsa`, `secrets.yml`, `*.pem` |
| `migracao` | 4 | sim | `migrations/`, `*.sql`, `schema.prisma` |
| `infra` | 4 | sim | `Dockerfile`, `.github/workflows/`, `*.tf` |
| `codigo` | 3 | sim | `*.go`, `*.py`, `*.ts`, `*.tsx` |
| `teste` | 2 | sim | `tests/`, `*_test.go`, `test_*.py`, `*.spec.ts` |
| `config` | 2 | sim | `*.json`, `*.yaml`, `*.properties` |
| `outro` | 2 | sim | o que não casa com nenhuma regra |
| `doc` | 1 | **não** | `*.md`, `docs/`, `README` |
| `lockfile` | 1 | **não** | `package-lock.json`, `go.sum`, `Cargo.lock` |
| `binario` | 1 | **não** | qualquer `Binary files ... differ` |
| `gerado` | 0 | **não** | `dist/`, `*.min.js`, `*.pb.go` |
| `vendor` | 0 | **não** | `vendor/`, `node_modules/`, `third_party/` |

Sobre essa base, o escopo levanta: `diff-sem-linhas` (must — só há arquivo binário ou renomeação pura), `segredo-no-diff` (must), `migracao-sem-rollback` (must), `binario-sem-revisao`, `sem-teste`, `diff-grande` (acima de 400 linhas), `arquivo-gigante` (acima de 200 linhas em um arquivo), `gerado-no-diff` e `diff-so-de-documentacao` (nice).

Segredo é detectado por duas vias: chave conhecida (`AKIA…`, `ghp_…`, `sk-…`, bloco `BEGIN PRIVATE KEY`, `xox[baprs]-…`) e atribuição longa (`api_key = "…"`, `senha: …`, 16 caracteres ou mais). A linha aparece na evidência com o valor **truncado em 90 caracteres**.

## 2. Lotes: assunto, não pasta

O agrupamento é por união-find, nesta ordem:

1. **teste junto da origem** — `src/test_app.py` puxa `src/app.py`, `providers_test.go` puxa `providers.go`, `__tests__/x.test.ts` puxa `x.ts`;
2. **família de locale** — `messages_pt.properties`, `messages_en.properties` e `messages_zh-CN.properties` caem no mesmo lote, como no *bundle* do upstream;
3. **mesma pasta e extensão** quando o grupo tem até o teto de arquivos.

O teto é **12 arquivos** e **20 mil tokens** por lote (1 token a cada 4 caracteres de diff, aritmética explícita, sem tokenizador de provedor). Acima disso saem `lote-grande`, `teste-separado`, `i18n-sem-original`, `lote-unico` e `lote-desbalanceado` quando o maior lote passa de três vezes a média.

## 3. Achados: quatro níveis, duas fontes

| Nível | Sinônimos aceitos |
|---|---|
| `blocker` | critical, critico, bloqueio, high, alto, fatal |
| `major` | erro, error, serious, importante, medium |
| `minor` | warning, warn, aviso, baixo, low |
| `nit` | info, suggestion, sugestao, trivial, style |

Severidade fora da lista vira `minor` e levanta `severidade-desconhecida`. Achado sem texto é **must**: marcador mudo não é acionável. Repetido exato (arquivo, linha, severidade e texto normalizado) é juntado com contagem. Acima de **40 % de blockers** em três ou mais itens, `severidade-inflada` cobra calibragem — bloqueio que bloqueia tudo não bloqueia nada.

A fonte é `regra` ou `agente`. Sem fonte declarada, id de regra presente indica pipeline determinístico; prosa solta indica agente. A inferência está declarada nos limites de cada resposta.

## 4. Posição: a âncora contra o hunk

Esta é a falha mais concreta do upstream e a mais fácil de medir: o comentário cai na linha errada. Contra o diff colado, cada achado recebe uma situação:

| Situação | Conta como âncora válida? |
|---|---|
| `exato` — linha adicionada | sim |
| `contexto` — linha de contexto do hunk | sim (nem todo host aceita comentar nela) |
| `proximo` — até 2 linhas de uma adição | sim, pela tolerância |
| `arquivo` — comentário sem linha | sim, mas sem trecho |
| `deslocado` — dentro do arquivo, fora do hunk | não |
| `linha-removida` — só existe na versão antiga | não |
| `linha-inexistente` — passa do maior número do diff | não |
| `arquivo-fora-do-diff` | não |

A precisão é `válidos ÷ total`; abaixo de **80 %** entra `precisao-baixa`. As sugestões de reancoragem usam a linha adicionada mais próxima, não a intenção do comentário — isso está nos limites.

## 5. Duplicatas: o efeito colateral da revisão híbrida

Regra e agente apontam o mesmo trecho com palavras diferentes. A comparação é lexical: palavras de três letras ou mais, sem acento, sem palavras vazias, Jaccard entre as duas assinaturas, mesmo arquivo e até **2 linhas** de distância. Acima de **0,5** é o mesmo problema. Repetição dentro da mesma fonte exige **0,75**.

O agrupamento é transitivo (A parecido com B e B com C põe os três juntos) e a ação sugerida é manter um comentário na maior gravidade. Quando as duas fontes discordam do nível, `conflito-severidade` é **must**: o autor não sabe se aquilo trava o merge. Se só uma camada revisou, `fonte-unica` cobra a outra — a determinística não cobre o que exige leitura e o agente não garante cobertura.

## 6. Cobertura: lido contra pedido

O diff define o denominador (arquivos `revisar: true`); a lista de revisados define o numerador. O piso é **60 %**. Abaixo dele, `cobertura-baixa` é must — é a falha número um de revisão feita por agente. Arquivo de risco 4 ou 5 sem revisão levanta `risco-alto-sem-revisao` mesmo com cobertura alta. Caminho declarado que não existe no diff vira `caminho-desconhecido`, e revisão que citou arquivos sem abrir nenhum revisável vira `revisao-vazia`.

Cobertura é medida em arquivos citados, não em linhas lidas; abrir o arquivo não garante leitura. É o limite honesto da conta.

## 7. Regras por caminho

O formato é o do upstream:

```json
{
  "rules": [
    {
      "path": "internal/llm/providers.go",
      "rule": "# internal/llm/providers.go\n\n## Estilo\n\n- Preserve o estilo do arquivo…",
      "merge_system_rule": true
    }
  ]
}
```

Cada regra sai com guia por classe de arquivo (`codigo`, `teste`, `config`, `migracao`, `infra`, `segredo`, `outro`), um bloco de pontos específicos do caminho — teste cita a origem que ele cobre, locale pede a chave em todas as traduções, migration exige rollback — e as **convenções do projeto** coladas no campo próprio. `merge_system_rule: true` significa que o texto é mesclado ao prompt de sistema, não que o substitui.

`regras-repetidas` cobra quando três ou mais caminhos recebem o mesmo texto-base: isso deveria ser convenção compartilhada, não cópia por arquivo. `regra-longa` (acima de 2.000 caracteres) e `regras-caras` (acima de 20 mil tokens somados) existem porque cada regra entra no contexto de **toda** revisão daquele caminho.

## Execução real

Rodando as sete skills contra o diff do próprio commit 0.24.0 deste repositório (207 kB, 46 arquivos):

| Skill | Resultado |
|---|---|
| `revisao.escopo` | 46 arquivos, **33 para revisar** e 13 filtrados, +3.484 −54 linhas, 15 de teste, 12 de documentação, risco somado 82, 0 segredos |
| `revisao.lotes` | 25 lotes, maior com 2 arquivos e **24.540 tokens**, 38.026 no total |
| `revisao.regras` | 20 regras (teto), 13 caminhos omitidos, 191 linhas de prosa, 1.722 tokens, 17 regras repetindo o mesmo guia |
| `revisao.cobertura` | com um único arquivo declarado: **3 %** de cobertura, 32 faltando e 15 de risco alto |
| `revisao.posicao` | 2 comentários, 2 âncoras exatas, precisão 100 % |
| `revisao.duplicatas` | 2 achados, 1 duplicata entre fontes e 1 conflito de gravidade |
| `revisao.achados` | 4 brutos viram 3 únicos, 1 repetido, 1 blocker (33,3 % de inflação) |

Os números são do texto colado, não do repositório: a camada não abre `git`.

## Limites declarados

- O diff precisa ser unificado (`git diff`, `git show`, `gh pr diff`); diff truncado faz linha válida parecer inexistente.
- Renomeação é lida pelo cabeçalho `rename from`/`rename to`, mas não é reconstruída para casar comentário antigo com arquivo novo.
- A estimativa de token é lexical (4 caracteres por token), não usa o tokenizador do provedor.
- Duplicata é lexical: sinônimo e frase reescrita não são reconhecidos.
- Cobertura mede arquivo citado, não linha lida.
- O texto da regra sai do caminho, da classe e do tamanho do diff — não do conteúdo do arquivo.
- Nada é publicado: nenhuma API de host é chamada, nenhum comentário é criado.
- Teto de 1,8 MB de texto, 5.000 achados e 2.000 arquivos por chamada.

## Licença e atribuição

O desenho vem de [`alibaba/open-code-review`](https://github.com/alibaba/open-code-review), **Apache-2.0**. Nenhum arquivo Go foi copiado e nenhuma dependência foi adicionada: o parser de diff, o agrupamento, o posicionamento e o formato de regra foram reimplementados em Python com fixtures próprias. A atribuição e o aviso da licença estão em [`licenses/alibaba-open-code-review.txt`](licenses/alibaba-open-code-review.txt).
