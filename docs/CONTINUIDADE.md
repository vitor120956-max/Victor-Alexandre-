# Continuidade de plano

A versão **0.6.0** adaptou o [`OthmanAdi/planning-with-files`](https://github.com/OthmanAdi/planning-with-files) para criar, listar, retomar e atualizar planos em disco. O repositório seguiu evoluindo e resolveu o problema seguinte: o plano existe, e a sessão é limpa no meio. Sem continuidade, o agente volta sem saber onde parou, o portão bloqueia onde deveria ceder, e o bloco reinjetado a cada turno muda de forma e encarece a conversa.

A versão **0.29.0** cobre esse lado com sete skills de leitura. Nada é escrito, nenhum hook é instalado e nenhum agente é bloqueado: o parecer é a decisão que o hook tomaria e o bloco que ele injetaria.

| Camada | O que faz | Escreve? |
|---|---|---|
| **Motor** (`server/continuidade.py`, 7 skills) | Lê fases, aplica o portão, reconstrói a retomada, monta a injeção, valida o livro e diagnostica o diretório | **Não** |
| **Página** (`/continuidade`) | Aba por operação, amostra com plano em andamento, progresso divergente e livro válido | Não |

Referência inspecionada: `master` em 24/10/2026 (27.629 estrelas, 2.297 forks), scripts `inject-plan.py`, `session-catchup.py`, `check-complete.sh`, `plan-doctor.sh`, `phase-status.sh`, `ledger-append.sh` e `ledger-summary.sh`. A 0.6.0 usou o commit `de837a95cc845b6341a6cbfd902a89a8190c568e`. Licença MIT, Copyright 2026 Ahmad Adi; o texto está em [`docs/licenses/othmanadi-planning-with-files.txt`](licenses/othmanadi-planning-with-files.txt).

## As sete skills

| Rota | Entrada | O que devolve |
|---|---|---|
| `continuidade.fases` | `task_plan.md` | fases com status, marca, critério, ordem e consistência de seção |
| `continuidade.portao` | plano, modo, bloqueios, livro | `block` ou `allow` com o guarda que decidiu e o motivo |
| `continuidade.retomada` | plano, progresso, achados | divergência entre as fontes e as cinco perguntas de reboot |
| `continuidade.injecao` | plano, progresso, livro, orçamento | bloco reinjetado, tamanho, corte e hash do plano |
| `continuidade.livro` | linhas JSONL | entradas válidas, ordem, lacuna, resumo por agente |
| `continuidade.medico` | bundle `>>> <plano>/<arquivo>` | arquivo faltando, livro, atestação e ambiguidade de plano ativo |
| `continuidade.regras` | — | arquivos, formatos, eventos, guardas, orçamento e limites |

Todas aceitam `modo` com `lite`, `full` (padrão) ou `ultra`; `lite` devolve só o que bloqueia e `ultra` acrescenta as perguntas antes de liberar.

## Os arquivos do padrão

```text
<projeto>/
├── task_plan.md          # Goal, Next Step, Current Phase, Phases
├── progress.md           # Session com data, fases, Test Results, Error Log
├── findings.md           # Requirements, Research Findings, Decisions
├── ledger-<agente>.jsonl # uma entrada JSON por linha, append-only
├── .mode                 # contém `gate` para armar o portão
└── .attest               # hash do plano, refeito a cada fase
```

`task_plan.md` é do orquestrador; o livro é de cada agente. Quem trabalha registra, quem coordena decide.

## 1. Fases: uma marca por fase

O upstream aceita dois formatos — `**Status:** complete` e `[complete]` — porque planos antigos usam o segundo. A camada lê os dois e repete a regra de contagem do portão: **conta cada formato e usa o maior valor por campo**. Isso preserva o resultado de plano de formato único e pega o plano misto.

| Achado | Grupo | Por quê |
|---|---|---|
| fase com mais de uma marca | must | o contador soma marcas, não fases: duas marcas adiantam a conclusão |
| fase sem status | must | não entra em nenhuma contagem |
| fase sem critério verificável | should | conclusão sem critério é opinião |
| fase `complete` com critério aberto | should | o status e a lista dizem coisas diferentes |
| fase fora de ordem | should | a fase ativa é lida de cima para baixo |
| concluída antes da anterior | should | fase marcada por engano, não trabalho adiantado |
| sem fase em andamento | should | o portão só bloqueia com fase ativa |
| `## Goal` / `## Next Step` vazios | must / should | a injeção depende das duas seções |

## 2. Portão: saber quando não bloquear

A tabela de decisão tem cinco guardas, avaliados nesta ordem. O portão só bloqueia quando **todos** passam:

| # | Guarda | Permite a parada quando |
|---|---|---|
| 1 | modo `gate` declarado | sem `.mode` com `gate`, o portão é consultivo |
| 2 | existe fase em andamento | nenhuma fase ativa é estado normal, não laço |
| 3 | parada forçada desligada | `stop_hook_active` verdadeiro evita recursão |
| 4 | abaixo do teto de bloqueios | ao atingir o teto (padrão 20) |
| 5 | o livro avançou | nada registrado desde o último bloqueio é estagnação |

O detalhe que mais importa: a guarda 5 libera a parada. Bloquear de novo sem entrada nova no livro só repete a mensagem — o agente aprende a ignorar o portão.

## 3. Retomada: duas fontes, um fato

`task_plan.md` e `progress.md` registram o mesmo status em dois lugares. Quando divergem, quem retoma escolhe uma das versões e erra na metade das vezes. A camada aponta a divergência e reconstrói o estado nas cinco perguntas do template:

| Pergunta | Resposta vem de |
|---|---|
| Onde estou? | fase `in_progress` do plano |
| Para onde vou? | fases `pending` |
| Qual é o objetivo? | `## Goal` |
| O que aprendi? | `## Research Findings` do `findings.md` |
| O que já fiz? | contagem de fases `complete` |

Pergunta sem resposta vira achado: a nova sessão começaria com menos contexto do que a anterior tinha.

## 4. Injeção: o bloco que cabe e não muda

O upstream reinjeta o plano a cada turno. A camada monta o mesmo bloco com quatro regras:

1. **Visão inteligente** — só `## Goal`, `## Next Step`, `## Current Phase`, a fase ativa e `## Decisions Made`. Sem essas seções, cai para as primeiras *N* linhas do arquivo.
2. **Orçamento** — 65.536 bytes para o plano, 32.768 para o progresso; o corte é em linha inteira e declarado no parecer.
3. **Progresso por livro** — com livro, o resumo tem forma fixa (`entries`, `phases`, `in_progress`, último evento por agente); sem livro, entram as últimas 20 linhas do `progress.md`.
4. **Relógio normalizado** — toda hora vira `T00:00:00`, com o fuso preservado. Timestamp que muda a cada turno invalida o prefixo em cache e faz cada mensagem pagar o bloco inteiro de novo.

O parecer devolve o bloco, os bytes de cada fonte e o hash do plano — a impressão digital que a atestação compara.

## 5. Livro: a camada de máquina

Uma entrada JSON por linha, append-only, com sete campos:

```json
{"tick":3,"ts":"2026-10-23T09:10:00Z","agent":"main","phase":"2","event":"progress","summary":"migration escrita","files":["db/0042.sql"]}
```

| Campo | Regra |
|---|---|
| `tick` | inteiro, `1 + maior tick` entre todos os livros do diretório |
| `ts` | ISO-8601 com `Z` ou offset |
| `agent` | `[A-Za-z0-9_-]`; vazio cai para `main` |
| `event` | `progress`, `phase_complete`, `error`, `gate_block`, `attest`, `note` |
| `summary` | até 200 caracteres, sem quebra de linha |
| `files` | lista de caminhos |
| `phase` | número ou nome da fase |

Achados: JSON inválido, evento fora dos seis, tick inválido ou repetido, campo obrigatório ausente, data fora do padrão, resumo longo, agente fora do padrão, ordem, lacuna e `files` malformado. Problemas do mesmo tipo viram **um** achado com os primeiros locais, não quinhentos iguais.

## 6. Médico: o diretório inteiro

Cinco perguntas sobre o conjunto:

- falta `task_plan.md`, `progress.md` ou `findings.md`?
- existe livro? existe atestação?
- dois planos têm o mesmo título?
- o plano declarado como ativo existe?
- mais de um plano tem fase em andamento e nenhum foi declarado ativo?

A última é a mais cara: no upstream o seletor explícito é **vínculo**, não dica — quando não resolve, nenhum outro plano é substituído. Sem vínculo, o resolvedor escolhe pelo mais recente e a escolha fica invisível.

## Limites

- **Nada é escrito**: nem plano, nem progresso, nem livro, nem `.mode`, nem atestação.
- **Nenhum hook é instalado** e **nenhum agente é bloqueado**: a decisão do portão é texto na resposta.
- **Nada é lido do disco**: o diretório chega no bundle `>>> <plano>/<arquivo>`.
- **Nenhum modelo é chamado**: o bloco injetado é corte, contagem e normalização de relógio, não resumo generativo.
- **Conclusão não é verificada**: a camada sabe se o critério está marcado, não se foi cumprido.
- **Data é texto**: fuso e ordem de fuso não são interpretados.
- **Limites de volume**: 1.800.000 caracteres, 20.000 linhas, 40 fases, 200 planos e 200 linhas de tabela por resposta.
- **Teto de bloqueios padrão 20**: igual ao `PWF_GATE_CAP` do upstream, configurável na chamada.

## Como rodar

```bash
npm run dev            # API 8000 + Vite 5173
# página: /continuidade
curl -s localhost:8000/api/health
curl -s localhost:8000/api/skills/continuidade.regras/execute \
  -H 'content-type: application/json' -d '{"parameters": {}}'
```

```bash
.venv/bin/python -m pytest server/tests/test_continuidade.py -q
```

## Licença e atribuição

Desenho derivado de [`OthmanAdi/planning-with-files`](https://github.com/OthmanAdi/planning-with-files) (MIT, Copyright 2026 Ahmad Adi), já usado como base da 0.6.0. Nenhum arquivo do upstream foi copiado; a atribuição completa, com o que a 0.6.0 e a 0.29.0 usaram e o que nenhuma das duas usou, está em [`docs/licenses/othmanadi-planning-with-files.txt`](licenses/othmanadi-planning-with-files.txt).
