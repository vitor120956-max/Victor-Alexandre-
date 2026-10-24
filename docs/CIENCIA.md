# Rigor científico

Dimensionar o estudo, conferir a estatística do relato, auditar o desenho, checar a reprodutibilidade, validar o método analítico e ler o manuscrito contra a diretriz. A camada parte de [`K-Dense-AI/scientific-agent-skills`](https://github.com/K-Dense-AI/scientific-agent-skills) — **MIT**, 177 skills —, mas o que entra aqui é só a parte **verificável**: nenhum dos 177 pacotes foi importado, nenhum script do upstream é chamado e nenhum modelo de linguagem participa. O JARVIS mede o que o texto declara; não executa análise e não escreve artigo.

| Camada | O que faz | Toca a rede? |
|---|---|---|
| **Motor** (`server/ciencia.py`, 7 skills) | Faz a conta de poder, confere número contra número, aplica a lista de itens e o critério que você declara | **Não** — lê só o texto ou a tabela colada |
| **Página** (`/ciencia`) | Aba por verbo, formulário por análise, métricas, itens presentes/ausentes e o parecer para copiar | Não |

O módulo reaproveita `server/review.py`: mesmos grupos (`must`, `should`, `nice`), mesmas contagens, veredito e Markdown. A saída é determinística — mesma entrada, mesmo parecer — e nenhuma skill grava arquivo, abre repositório, baixa DOI ou roda script.

---

## As sete skills

| Rota | Entrada | O que devolve |
|---|---|---|
| `ciencia.amostra` | teste, linha de base e efeito **ou** d, alfa, poder, alocação, perda, comparações, cluster e ICC | n por grupo, total, matrícula, poder calculado, alfa ajustado, DEFF e a conta aberta |
| `ciencia.estatistica` | trecho de resultados | p citados, tamanho de efeito, intervalo, n e achados sobre o que o relato faz com eles |
| `ciencia.desenho` | trecho de métodos e tipo (`ensaio`, `observacional`, `diagnostico`, `animal`) | item a item presente/ausente, cobertura e os erros estruturais que o texto revela |
| `ciencia.reprodutibilidade` | métodos e seção de disponibilidade | nove itens de dado, código, ambiente e registro, com cobertura |
| `ciencia.validacao` | tabela `nível,medido,alvo[,grupo]` e curva `concentração,sinal` | recuperação, RSD, R², LOD, LOQ e situação por nível contra o critério |
| `ciencia.manuscrito` | texto completo e tipo | 13 seções, itens da diretriz, cobertura e afirmações de risco (cura, risco zero, prova) |
| `ciencia.regras` | nada | benchmarks, critérios M10, 11 fórmulas, diretrizes, itens de desenho e reprodutibilidade |

Todas aceitam `modo` com `lite`, `full` (padrão) ou `ultra`. `lite` devolve só o que bloqueia, `full` inclui as correções e `ultra` inclui as perguntas que faltam para decidir.

---

## 1. Dimensionar o estudo

Quatro quantidades ficam travadas: **n**, **efeito**, **alfa** e **poder**. Informe três e a skill calcula a quarta. O poder informado é o alvo da conta; o `poder_calculado` volta do n arredondado para cima e mostra a diferença.

| Teste | Fórmula de n por grupo |
|---|---|
| Duas proporções | `n1 = (zα√((1+r)p̄q̄) + zβ√(p1q1 + r·p2q2))² ÷ (r·(p2−p1)²)` |
| Duas médias | `n1 = (zα + zβ)² · (1 + 1/r) ÷ d²` |
| Efeito de desenho | `DEFF = 1 + (m − 1)·ICC` |
| Perda | `n_matrícula = n_analisado ÷ (1 − perda)` |
| Multiplicidade | `alfa_ajustado = alfa ÷ comparações` |

Com linha de base de 3%, efeito relativo de 20% (3% → 3,6%), alfa 0,05 e poder 0,80, são **13.914 por grupo** — 27.828 analisados. Com perda de 15%, a matrícula sobe para **32.740**. Com d = 0,5, são **63 por grupo**. Quatro comparações reduzem o alfa para **0,0125** e elevam o n para 19.768 por grupo. Cluster de 20 com ICC 0,05 dá DEFF de **1,95** — o n praticamente dobra.

**Efeito ancorado, nunca observado.** Poder calculado sobre o efeito que o estudo encontrou é circular: todo estudo fica com 50% de poder por construção. `efeito` é sempre o que você declara — ou o SESOI, ou o menor efeito que mudaria a decisão, ou uma convenção justificada; o piloto entra apenas com o encolhimento declarado.

**Benchmarks** (convenção, não medida): d 0,20/0,50/0,80 · f 0,10/0,25/0,40 · r 0,10/0,30/0,50 · η² 0,01/0,06/0,14 · h 0,20/0,50/0,80 · w 0,10/0,30/0,50 · R² 0,02/0,13/0,26. Efeito abaixo do limite pequeno vira achado `efeito-pequeno`: a amostra cresce ao quadrado quando o efeito encolhe.

**Achados:** `poder-baixo` (must, abaixo de 80% no n informado), `poder-excessivo` (nice, acima de 95% — recurso desperdiçado), `alfa-frouxo` (acima de 0,05 sem justificativa), `perda-alta` (20% ou mais), `multiplicidade` (mais de uma comparação), `cluster-inflado` (ICC e cluster que encarecem o estudo), `amostra-inviavel` (n acima do plausível), `efeito-pequeno`.

**Limites da conta:** duas amostras independentes; teste pareado, ANOVA de k grupos, sobrevida e modelos mistos exigem outra fórmula; a aproximação é normal; não há poder para equivalência, não inferioridade, sequencial ou bayesiano.

---

## 2. Auditar a estatística do relato

Lê o trecho de resultados e confere número contra número: se o p citado é possível, se o IC está na ordem certa, se a média tem dispersão, se o percentual tem denominador, se a afirmação de equivalência tem margem. Nenhum teste é reexecutado.

**p exato.** `p = 0` não existe e vira `p-zero` (must); `p > 1` ou negativo vira `p-impossivel` (must); `p < 0,05` no lugar do valor exato vira `limiar-em-vez-de-valor`; p entre 0,05 e 0,10 chamado de "tendência" vira `tendencia`; "significativo" sem p nem teste vira `significancia-sem-teste`.

**O que todo resultado precisa mostrar.** `sem-efeito` (nenhum tamanho de efeito), `sem-intervalo` (nenhum IC), `sem-n` (nenhum tamanho de amostra), `media-sem-dispersao`, `sem-graus-de-liberdade`, `percentual-n-baixo` (percentual com n pequeno). "Não houve diferença" só é conclusão com margem e teste de equivalência — sem isso, vira `equivalencia-sem-margem` (must). `correlacao-sem-r` e `causalidade` (linguagem causal em desenho que não a sustenta) fecham a lista, com `ic-invertido`, `dispersao-zero` e `arredondamento` (nice, mais de duas casas em média/desvio).

**O que não é conferido:** ausência de item não prova que a análise não foi feita, só que o relato não a mostra; não há acesso a dado, saída de software ou suplemento.

---

## 3. Auditar o desenho

Quatorze itens, com peso diferente por tipo de estudo. As contagens aplicáveis (total / exigidos): **ensaio 12/11**, **observacional 9/8**, **diagnóstico 10/9**, **animal 13/10**. Só `must` e `should` entram na cobertura; `nice` fica fora da conta.

| Item | Pergunta que o texto precisa responder |
|---|---|
| `randomizacao` | Como a sequência foi sorteada e onde? |
| `alocacao` | Quem guardou a sequência e como o próximo grupo foi revelado? |
| `cegamento` | Quem estava cego: participante, quem aplica, quem mede, quem analisa? |
| `controle` | Qual é o comparador concorrente — placebo, sham, ativo? |
| `unidade` | Qual é a unidade de inferência e quantas unidades biológicas por grupo? |
| `bloqueio` | Houve bloco, estrato ou pareamento? |
| `primario` | Qual é o desfecho primário, declarado antes? |
| `amostra` | Qual é o cálculo amostral e o efeito que o sustenta? |
| `registro` | O protocolo foi registrado, com número e data? |
| `elegibilidade` | Quais são os critérios de inclusão e exclusão? |
| `perdas` | Quantos saíram, por quê, e como foram tratados? |
| `analise` | A análise primária foi pré-especificada? |
| `confundimento` | Que variável de incômodo foi medida ou controlada? |
| `referencia` | Qual é o padrão de referência, independente do teste? |

**Erros estruturais que a leitura pega.** `pseudorreplicacao` (must): "3 camundongos com 100 células cada" não é n = 300, é n = 3. `atribuicao-por-conveniencia` (must): tratamento na segunda e controle na terça confunde grupo com dia. Além deles, a cobertura abaixo de 60% vira `cobertura-baixa`. A lista completa de itens por tipo, com peso, sai em `ciencia.regras`.

A leitura é lexical: presença da palavra não prova que o procedimento foi feito, e ausência não prova que não foi. Risco de viés tem escala própria (RoB 2, ROBINS-I, QUADAS-2) e não é substituído por esta conferência.

---

## 4. Reprodutibilidade

Nove itens, sete exigidos (`must` ou `should`):

| Item | Peso | O que fecha a lacuna |
|---|---|---|
| `dados` | must | Repositório, DOI e versão do conjunto |
| `codigo` | must | Repositório com o commit usado |
| `versao` | should | Pacote e versão de cada dependência que entrou na conta |
| `semente` | should | Semente declarada e onde foi fixada |
| `ambiente` | should | Imagem ou arquivo de ambiente (`Docker`, `conda`, `renv`, `requirements.txt`) |
| `registro` | should | Registro do protocolo, com data e versão |
| `accession` | should | Identificador de cada conjunto (`GSE`, `PRJ`, `PXD`, `SRR`, PDB) |
| `licenca` | nice | Licença de dado, código e material |
| `materiais` | nice | Fabricante, catálogo e lote dos reagentes críticos |

"Dados sob solicitação" sem motivo declarado vira `acesso-por-solicitacao`; restrição justificada (privacidade, contrato, biossegurança) é legítima e não é penalizada. Ausência de código vira `sem-codigo`; cobertura abaixo de metade vira `cobertura-baixa`. Nenhum repositório, DOI ou registro é acessado pela rede.

---

## 5. Validar o método analítico

Duas regras valem antes da conta: **o framework é escolhido antes** — ICH Q2(R2)/Q14, USP <1220>/<1225>/<1226>, ICH M10, CLSI EP, ISO 17025 — e **o critério de aceitação é fixado antes do dado**. Critério definido depois de ver o resultado não é critério: é achado de auditoria. Por isso a skill aplica o limite que você informa; ela não escolhe um.

A tabela é `nível,medido,alvo[,grupo]`, com pelo menos **quatro medições em dois níveis**. O `grupo` separa rodadas e é o que permite medir precisão intermediária além da repetibilidade.

| Critério | Cromatográfico (ICH M10) | Ligante / LBA |
|---|---|---|
| Recuperação (exatidão) | ±15% (±20% no LLOQ) | ±20% (±25% no LLOQ) |
| Precisão (RSD) | ≤15% (≤20% no LLOQ) | ≤20% (≤25% no LLOQ) |
| R² mínimo da curva | 0,99 | 0,99 |
| LOD | `3,3 × s_resíduos ÷ inclinação` | — |
| LOQ | `10 × s_resíduos ÷ inclinação` | — |

Com dez medições em dois níveis, recuperação de 100,00% nos dois, RSD de 1,58% e curva de cinco pontos: R² **0,99996**, LOD **0,392** e LOQ **1,189**. O nível mais baixo ganha os 5 pontos percentuais de folga do LLOQ, e a linha mostra o limite aplicado — `±20% / RSD 20%` no nível 1, `±15% / RSD 15%` no nível 10.

**Achados:** `recuperacao-fora` (must), `rsd-alto` (must), `precisao-total-fora` (must, LBA), `inclinacao-nao-positiva` (must), `replicatas-insuficientes` (should, menos de três no nível), `precisao-intermediaria` (should — repetibilidade não representa a precisão do método), `vies-sistematico` (should, dentro do limite mas deslocado), `lod-acima-do-nivel` (should), `sem-curva` (should).

**Limites:** só a tabela colada é usada; nenhum cromatograma ou relatório de software é lido; linearidade é regressão simples por mínimos quadrados — falta de ajuste, homocedasticidade e faixa validada não são testadas.

---

## 6. Auditar o manuscrito

Treze seções e a diretriz do tipo declarado:

| Tipo | Diretriz | Itens |
|---|---|---|
| `ensaio` | CONSORT 2025 | 6 |
| `observacional` | STROBE | 6 |
| `diagnostico` | STARD | 5 |
| `revisao` | PRISMA 2020 | 5 |
| `animal` | ARRIVE 2.0 | 6 |

As seções conferidas são resumo, introdução, métodos, resultados, discussão, limitações, conclusão, financiamento, conflito de interesse, disponibilidade de dados, contribuição de autoria, aprovação ética e referências. Seção ausente vira `sem-secao-<id>` (must); item da diretriz ausente vira `sem-item-<id>` (should). Um texto completo de 137 palavras fecha 13/13 seções e 6/6 itens do CONSORT, e o parecer ainda aponta `texto-curto`: completude de relato não é extensão nem mérito.

**Afirmações de risco.** `cura` (must, "cura definitiva", "curou"), `sem-risco` (must, "sem nenhum efeito", "100% seguro") e `prova` (must, "prova que", "está provado que") são bloqueios: estudo sustenta hipótese com incerteza, não prova. `inedito` (should) lembra que novidade não é resultado.

**Limites:** a escolha da diretriz é pelo tipo declarado; extensões específicas (CONSORT-AI, STROBE-ME) exigem outra lista; nenhuma referência é acessada, contada ou verificada.

---

## 7. O catálogo de regras

`ciencia.regras` devolve o que o motor usa, para que a regra não fique escondida no código: os sete benchmarks, os critérios M10 das duas modalidades, o R² mínimo de 0,99, alfa 0,05, poder 0,80 (0,90 confirmatório), as **11 fórmulas**, as cinco diretrizes com seus itens, os itens de desenho por tipo com peso, os nove itens de reprodutibilidade, as quatro afirmações de risco e a lista do que ficou de fora.

---

## O que ficou de fora

Os **177 pacotes** do upstream — bioinformática, química, genômica, imagem, machine learning, escrita e busca bibliográfica — **não foram portados**: dependem de bibliotecas científicas, dados externos e execução de shell, e nada disso roda aqui. Também não foram instalados os scripts do repositório (`power.py`, `simulate_power.py`, `randomization.py`, `doe_designs.py`, `check_accuracy_precision.py`, `scan_skills.py`): as contas foram reimplementadas em Python a partir das fórmulas publicadas, e a validação de entrada usa Pydantic com allowlist, não o scanner de terceiro. Risco de viés, meta-análise, modelagem bayesiana e desenho experimental fatorial estão declarados como fora de escopo em vez de fingidos.

## Atribuição

Código e documentação do upstream sob licença MIT, `Copyright (c) 2025 K-Dense Inc.`. O texto integral está em [`docs/licenses/k-dense-ai-scientific-agent-skills.txt`](licenses/k-dense-ai-scientific-agent-skills.txt).

## Contrato

Toda resposta traz `executed: false`, `readOnly: true` e o `mode` herdado do `review`; o `analysis` é prefixado com `ciencia.` e cada `limitations` declara o que a conferência não cobre. Nenhuma skill grava arquivo, chama a rede, executa código ou consulta modelo — inclusive a de regras, que devolve o catálogo estático.
