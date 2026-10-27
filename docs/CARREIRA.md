# Carreira

Triagem de vaga com **nota 1–5 e evidência declarada**, placar **ATS de pesos fixos**, auditoria de bullets, carta com fonte, plano de entrevista e leitura de funil. A adaptação parte de [`career-ops-hq/career-ops`](https://github.com/career-ops-hq/career-ops) (MIT, 2026), mas o código é local: nenhum CLI, plugin, script Node, portal, dashboard ou workflow do upstream é instalado ou executado.

O upstream é um agente de busca de emprego que roda no CLI de IA do usuário, com 39 modos. O valor que sobrevive sem portal, navegador e sem uma IA no meio é o **método de decisão**: bandas de importância, níveis de evidência, tetos nomeados, legitimidade do anúncio, pesos fixos do ATS e a disciplina de escrever só o que tem fonte. É isso que a versão 0.13.0 traz, em português.

---

## O que foi adaptado

| Do upstream | Aqui |
|---|---|
| Nota global 1–5 sem fórmula, com linha ética em 4,0 | Nota com base ponderada, **tetos nomeados** e faixas iguais às do upstream |
| Cinco dimensões (match, norte, comp, cultura, red flags) | `aderencia`, `alvo`, `comp`, `cultura`, `risco`, com peso declarado |
| Importância por banda e evidência `stated/structural/inferred` | Mesmas cinco bandas, gate que impede inferência de virar obrigatório |
| Confiança Low/Medium/High | `alta/media/baixa` derivada de `score_evidence` e `confidence_gaps` |
| Bloco G de legitimidade em três tiers | Treze sinais catalogados, nota 0–100 e tier, **fora da nota 1–5** |
| Taxonomia de 10 tipos de empresa → confiabilidade de comp | Mesma taxonomia, em PT-BR, com sinal e motivo |
| ATS em duas etapas (`ats-payload.mjs` + `verify-ats.mjs`) | Lints de payload próprios + placar de 100 com oito checagens e nota A–F |
| Carta em 10 passos com gate de JD e quatro perguntas | Gate de três insumos, rascunho só com conquista verificável e seis checagens |
| Plano de entrevista e banco de histórias STAR | Matriz requisito → pergunta, cruzamento de histórias e perguntas para a empresa |
| Tracker `applications.md` com estados | Leitura de tabela/TSV/CSV, dez estados, taxas e coortes |
| 5 dimensões + gates em `modes/apply.md`, `batch/` | **Não adaptado**: volume, auto-pipeline e envio em lote ficam fora |

### O que ficou de fora, de propósito

- **Nada de portal, navegador ou scraping.** O texto colado é toda a evidência. Checagem de liveness de URL, scan de job boards, dashboard Go, `batch-runner.sh` e workflows de GitHub não existem aqui.
- **Nada de envio.** O JARVIS não candidata, não abre formulário e não gera PDF. O botão de enviar continua sendo seu.
- **Nada de IA no laço.** A nota é determinística: mesma vaga, mesmo perfil, mesma saída. Onde o upstream usa julgamento, aqui há regra declarada ou ausência de dado.
- **Nada de `cv.md` reescrito.** A auditoria aponta o padrão e pergunta o número; não inventa conquista, verbo ou métrica.
- **Nada de precedência de arquivo.** `modes/_profile.md` e `_custom.md` viram o campo `perfil`; não há leitura de disco nem ordem de override.

---

## A nota em cinco dimensões

| Dimensão | Peso | O que mede |
|---|---|---|
| Aderência ao perfil | 45% | cobertura ponderada dos requisitos pela prova do currículo |
| Alinhamento com o alvo | 20% | termos em comum entre vaga e alvo declarado |
| Remuneração | 15% | faixa anunciada contra piso e alvo, com moeda e período |
| Sinais culturais | 10% | flexibilidade, desenvolvimento, inclusão e benefícios concretos no texto |
| Risco da vaga | 10% | legitimidade do anúncio e idade da publicação |

A base é `Σ(dimensão × peso)`, arredondada a uma casa. Depois entram os tetos:

| Teto | Quando dispara |
|---|---|
| 2,0 | regra dura do perfil violada (com trecho citado) **ou** requisito obrigatório declarado ausente |
| 2,5 | anúncio com legitimidade `suspeita` |
| 3,4 | contradição cultural (promete flexibilidade e pede disponibilidade total, ou linguagem de família) |
| 3,5 | dois ou mais requisitos centrais ausentes |

O resultado aparece com `base` e `ajustes`, para você ver de onde veio. **A nota não é média das dimensões** e não é probabilidade de contratação.

### Bandas de importância

| Banda | Peso | Leitura |
|---|---|---|
| `critical` | 5 | obrigatório declarado, título, gate legal ou de idioma, responsabilidade repetida |
| `high` | 3 | requisito central, provável de ser cobrado em entrevista |
| `meaningful` | 2 | requisito real, não obviamente decisivo |
| `preferred` | 1 | diferencial ou "nice to have" |
| `low_signal` | 0,5 | genérico ou boilerplate |

### Níveis de evidência

| Nível | Como é reconhecido | Regra |
|---|---|---|
| `stated` | "obrigatório", "exigido", "must", título, gate legal ou de idioma | exige marcação na própria vaga |
| `structural` | seção de requisitos, repetição, posição na lista | auditável só pelo texto |
| `inferred` | leitura de mercado, sem marcação | **nunca** vira `critical` ou `high` |

O gate é assimétrico de propósito: inflar a importância de algo que você não tem desencoraja uma candidatura que valia a pena; subestimar um requisito real custa uma entrevista pior — e isso é recuperável.

### Faixas da nota

| Nota | Ação | Leitura |
|---|---|---|
| ≥ 4,5 | aplicar agora | sinal verde: o perfil cobre o que a vaga pede |
| 4,0–4,4 | vale aplicar | bom encaixe; prepare as lacunas antes |
| 3,5–3,9 | hesitar | encaixe parcial; só com motivo declarado |
| < 3,5 | não aplicar | abaixo da linha ética de 4,0 |

### Confiança

- **Alta:** as cinco dimensões têm evidência `supported` e há data de publicação.
- **Média:** alguma dimensão parcial, ou falta a data de publicação.
- **Baixa:** sem currículo, sem alvo declarado, duas ou mais dimensões sem dado, ou contradição cultural.

`score_evidence` guarda o estado de cada dimensão e `confidence_gaps` nomeia o que falta. Não existe conversão de nota em probabilidade.

---

## Legitimidade do anúncio

O bloco roda em paralelo à nota e **não a altera**. Cada sinal tem estado (`bom`, `atencao`, `ruim`), peso 1–3, confiança e evidência citada. A nota de legitimidade começa em 100 e perde 12 × peso para sinal ruim e 5 × peso para atenção.

| Tier | Faixa | Leitura |
|---|---|---|
| Alta confiança | ≥ 85 | sinais coerentes, vaga recente e específica |
| Cautela | 60–84 | há pergunta a fazer antes de investir tempo |
| Suspeito | < 60 | confirme a vaga antes de preparar material |

Sinais catalogados: vaga antiga, republicada, faixa ausente, faixa larga, PJ para rotina de emprego, cobrança do candidato, trabalho sem remuneração, jornada crítica, requisito protegido, requisito contraditório, triagem automática, local indefinido e benefício vago. A avaliação também registra sinais positivos (idade recente, faixa estreita, especificidade técnica, cargo conectado à empresa).

**Enquadramento obrigatório:** sinal, nunca acusação. Nenhuma skill diz que a empresa "está quebrando a lei" ou que a vaga é "ilegal"; o texto aponta o fato observável e a pergunta a fazer.

### Empresa × confiabilidade de remuneração

Dez tipos: big tech, startup em crescimento, startup inicial, corporação tradicional, agência/consultoria, PME local, comissão, recrutadora, governo/academia/terceiro setor e comunidade open source. Cada um devolve `alta`, `media` ou `baixa` confiabilidade e o motivo. Sem faixa declarada, a resposta tem duas linhas — tipo de empresa e confiabilidade — e nenhum palpite de número. Moedas diferentes não são convertidas: a comparação para e a lacuna é declarada.

---

## ATS em duas etapas

### 1. Payload (texto)

Quatro lints, somente reportados:

| Código | O que detecta |
|---|---|
| `empresa-no-cargo` | cargo e empresa na mesma linha, com data |
| `parentese-na-empresa` | "Acme (antiga Beta)" dentro do nome |
| `multiplas-faixas-de-data` | duas faixas de data na mesma entrada |
| `competencias-duplicadas` | seções Competências e Habilidades ao mesmo tempo |

### 2. HTML (placar de 100)

| Peso | Checagem | Regra |
|---|---|---|
| 15 | Texto selecionável | pelo menos 300 caracteres legíveis |
| 20 | Cabeçalhos padrão | experiência, formação e habilidades reconhecíveis |
| 15 | E-mail no corpo | fora de `header` |
| 20 | Coluna única | sem tabela de layout nem CSS multicoluna |
| 10 | Sem texto em imagem | imagem não carrega conteúdo essencial |
| 10 | Fonte comum | pilha com Arial, Calibri, Helvetica, Georgia, Times ou system-ui |
| 5 | UTF-8 declarado | `meta charset` |
| 5 | Sem texto oculto | `display:none`, `visibility:hidden`, `font-size:0`, `color:transparent` |

Nota: A ≥ 90, B ≥ 80, C ≥ 70, D ≥ 60, F < 60. Sem HTML, as cinco checagens de layout ficam `nao-verificado`, o placar é **parcial** e a letra **não é emitida** — 50 de 50 pontos medidos não é 100 de 100.

Palavras-chave são opt-in e advisory: a skill mostra presentes e ausentes e lembra que palavra só entra se houver experiência. O placar **não detecta** o defeito de payload — são etapas separadas por um motivo.

---

## Auditoria de bullets

Só entram bullets de Experiência e Projetos; Formação, Idiomas e Certificações ficam fora. Cada bullet perde pontos por:

| Código | Peso | Problema |
|---|---|---|
| `sem-metrica` | 30 | nenhum número |
| `abertura-fraca` | 25 | começa com "responsável por", "ajudei", "participei" |
| `cliche` | 20 | adjetivo de catálogo |
| `voz-passiva` | 15 | "foi feito", "foi realizado" |
| `longo` | 10 | mais de 220 caracteres |
| `curto` | 5 | menos de 28 caracteres |
| `primeira-pessoa` | 5 | "eu", "meu", "fiz" |

A saída traz a pontuação por linha, o padrão de reescrita ("verbo no passado + o que mudou + número + como") e a pergunta que falta responder. **Não há bullet reescrito**, porque a métrica é sua.

---

## Carta em etapas

1. **Gate de vaga:** menos de 200 caracteres, para.
2. **Gate de currículo:** menos de 200 caracteres, para.
3. **Gate de insumo:** sem pesquisa da empresa (ou razão declarada) e sem conquista com número, para antes do rascunho e devolve as perguntas.
4. **Seleção de prova:** até três bullets do currículo, priorizando os que têm número e casam com os termos da vaga.
5. **Lacuna assumida:** uma frase de fronteira, com o adjacente mais próximo — nunca "domino".
6. **Rascunho:** 3–4 parágrafos, com empresa e cargo nomeados, sem placeholder.
7. **Checagens:** clichê (20), número sem origem (25), placeholder (20), tamanho 600–1.600 (15), palavras da vaga (10), especificidade (10).

A checagem de número é literal: todo número do rascunho precisa aparecer no currículo, no perfil ou no aviso prévio declarado. O rascunho fica no chat para revisão; PDF e envio não existem aqui.

---

## Entrevista

- Seis requisitos principais (título fica fora: ele é o cargo, não uma competência).
- Duas perguntas por requisito, escolhidas pelo tipo: técnica, comportamental, gestão ou produto.
- Prova do currículo e risco de lacuna em cada linha.
- Cruzamento com o banco de histórias: uma história por título, com `Situação`, `Tarefa`, `Ação`, `Resultado` e número no resultado.
- Cinco perguntas para a empresa, derivadas de faixa, modelo, legitimidade e rotina.
- Sinais do anúncio viram perguntas a esclarecer, nunca veredito sobre a empresa.
- Três blocos de preparação: 30 min de leitura, 1 h de ensaio cronometrado, 20 min na véspera.

---

## Funil

Dez estados: `avaliada`, `aplicada`, `respondeu`, `teste`, `entrevista`, `oferta`, `recusada`, `descartada`, `pulada`, `contratada`. A entrada aceita tabela markdown, TSV ou CSV, com cabeçalho em português ou inglês; sem cabeçalho, a ordem é Data | Empresa | Cargo | Status | Nota e o fato é avisado.

Saída: contagem por status, taxas de resposta/entrevista/oferta, coortes por mês, candidaturas ativas, paradas há 14 dias ou mais e status ilegíveis. As taxas excluem `pulada` e `avaliada` do denominador, contam candidaturas ainda ativas como censuradas e avisam quando há menos de 8 linhas. Sem data de transição por etapa, **não há velocidade de etapa** — só idade da candidatura.

---

## As sete skills

| Skill | Entrada | O que devolve |
|---|---|---|
| `carreira.triagem` | vaga, perfil, currículo, `forcar` | nota, dimensões, tetos, requisitos, lacunas, legitimidade, perguntas |
| `carreira.ats` | currículo, HTML opcional, vaga opcional | placar, checklist, lints, cobertura de palavras |
| `carreira.bullets` | currículo | auditoria por linha, padrão e pergunta |
| `carreira.carta` | vaga, currículo, perfil, pesquisa, razão | rascunho, conquistas-fonte, checagens, lacuna |
| `carreira.entrevista` | vaga, currículo, perfil, histórias | matriz, perguntas para a empresa, sinais, blocos |
| `carreira.funil` | candidaturas, janela | status, taxas, coortes, paradas, limites |
| `carreira.regras` | — | bandas, dimensões, evidência, faixas, estados, pesos, sinais |

Todas são `readOnly`, `executed: false` e determinísticas. Nenhuma grava arquivo, abre rede ou chama IA.

## Página `/carreira`

Sete abas: Triagem, ATS, Bullets, Carta, Entrevista, Funil e Regras. Cada aba tem exemplo próprio, seletor de nível (`lite`, `full`, `ultra`), resultado com métricas, achados de quatro partes, perguntas, limites declarados e o relatório em markdown para copiar. A aba Regras carrega o catálogo direto da API.

O comando de voz ou texto `carreira`, `triagem de vaga`, `checar ats`, `auditar bullets`, `carta de apresentação`, `plano de entrevista` ou `funil de candidaturas` abre a página sem executar nada.

## Determinismo e limites

- Mesma entrada, mesma saída: nenhuma chamada de IA, nenhuma aleatoriedade.
- O parser de YAML cobre o subconjunto usado por perfis: mapas indentados, listas e escalares. Não é um parser YAML completo.
- A extração de faixa salarial exige moeda, período e os dois limites para comparar; ambiguidade vira ausência.
- O placar ATS lê o texto do HTML, não o PDF renderizado. Não simula um ATS real nem abre navegador.
- A auditoria de bullets é lexical: pode ter falso positivo em frase incomum.
- O funil não lê e-mail, calendário ou LinkedIn; é só o que foi colado.
- A nota é triagem declarada, não previsão de contratação. Abaixo de 4,0 a decisão continua sua.

## Como rodar e testar

```bash
npm run dev                                   # API em 8000 e Vite em 5173
curl -s http://localhost:8000/api/health      # 0.58.0, 281 skills
```

```bash
.venv/bin/python -m pytest server/tests/test_career.py   # 51 testes
.venv/bin/python -m pytest server/tests                  # 312 testes
npx vitest run                                           # 41 testes web
npx tsc --noEmit
npm run build
```

## Licença e atribuição

O upstream é MIT, Copyright (c) 2026 Santiago Fernández de Valderrama. A licença original está em [`docs/licenses/career-ops-hq-career-ops.txt`](licenses/career-ops-hq-career-ops.txt). O código desta adaptação é independente: nenhum arquivo do upstream foi copiado, e as ideias foram reescritas em Python e em português.
