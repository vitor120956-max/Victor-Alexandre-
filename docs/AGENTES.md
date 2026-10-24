# Governo de agentes

Adaptação local do modelo de governança de [`paperclipai/paperclip`](https://github.com/paperclipai/paperclip) (MIT, Copyright (c) 2025 Paperclip AI). O upstream é um *control plane* para uma empresa de agentes: organograma, tarefas com checkout atômico, heartbeats, orçamentos, rotinas, aprovações e portabilidade. Aqui fica apenas a parte que o JARVIS consegue fazer **sem executar agentes**: revisar o que você declara sobre a equipe, o trabalho, o dinheiro e as permissões.

Nada do upstream é instalado, clonado ou executado. Não há servidor, adapter, plugin, MCP, heartbeat, Docker, `pnpm` ou worker. As skills leem texto colado ou uma pasta já existente na área isolada e devolvem candidatos com evidência, veredito e limites. A licença original está em [`docs/licenses/paperclipai-paperclip.txt`](licenses/paperclipai-paperclip.txt).

## O que foi adaptado

| Conceito do upstream | Como aparece aqui |
|---|---|
| Organograma de agentes com linha de reporte | Revisão de equipe: raiz humana, ciclos, responsável inativo, amplitude, orçamento e permissões |
| Quadro de tarefas com dono único e blockers | Revisão de quadro: dono, evidência, bloqueio sem causa, ciclo de dependências, WIP e inatividade |
| Budgets com aviso e hard stop | Revisão de orçamento: utilização, estouro, parada ausente, projeção linear e teto da empresa |
| Task watchdog de subárvore | Verificação de parada com impressão digital SHA-256, supressão e uma única tarefa de revisão |
| Permissões padrão de agente | Linha de base de 18 grants e 6 negações, exceções, cota e override de runtime |
| Ciclo de vida do agente | Documentado como referência; não é aplicado por falta de runtime |
| Heartbeat, adapters, plugins, portabilidade | Fora do escopo: exigiriam executar agentes |

## As quatro leis

1. **Recebe heartbeat, foi contratado.** Só entra no quadro quem tem identidade, estado e teto declarados.
2. **Todo trabalho tem um dono.** Tarefa em andamento sem responsável para no próximo ciclo.
3. **Toda parada tem revisão.** Subárvore sem caminho vivo gera uma revisão; a mesma parada não a gera duas vezes.
4. **Todo limite tem parada.** Alerta sem hard stop é apenas um número no painel.

## Formatos de entrada

Cada linha é um registro; campos são separados por `|`. Linhas vazias e linhas iniciadas por `#` são ignoradas. O limite é 200 linhas por análise, 300 caracteres por campo e 50.000 caracteres por entrada.

### Equipe

```text
nome | papel | responde a | orçamento mensal | permissões | estado
Ana | Tech lead | board | 900 | deploy, shell | ativo
Bruno | Backend | Ana | 600.00 | shell | ativo
Carla | Pesquisa | Ana | 350 | network | pausado
```

- `board` (ou `conselho`, `humano`, `diretoria`) é a raiz humana.
- Estados: `ativo`, `pausado`, `pendente`, `encerrado`, `rejeitado`, `sem_orcamento`.
- Permissões são separadas por vírgula; `*`, `admin` e `sudo` são tratados como curinga.

### Quadro

```text
id | título | dono | estado | objetivo | bloqueadores | evidência | atualizado
ENG-1 | Login | Ana | in_progress | lançar beta | — | — | 2026-10-19
ENG-2 | Testes de login | Bruno | blocked | lançar beta | ENG-1 | — | 2026-10-18
ENG-3 | Documentação | Carla | done | lançar beta | — | PR #12, revisão de Ana | 2026-10-18
```

- Estados: `triage`, `backlog`, `todo`, `in_progress`, `in_review`, `blocked`, `waiting`, `done`, `cancelled`, `queued`, `retry` (e equivalentes em português).
- Conclusão exige evidência; revisão exige evidência e revisor; bloqueio exige bloqueador nomeado.
- Bloqueadores apontam para IDs do próprio quadro. ID inexistente, auto-bloqueio e ciclo são bloqueios.
- A data de referência vazia usa o dia atual em UTC; datas futuras são sinalizadas.

### Orçamento

```text
agente | limite | gasto | alerta% | parada automática
Ana | 900 | 740 | 80 | sim
Bruno | 600 | 610 | 80 | sim
Carla | 350 | 40 | 80 | não
```

- A unidade é livre (`US$`, `BRL`, `€`); **não há conversão de moeda**.
- `dia do período` maior que zero ativa a projeção linear `gasto / dia × dias no mês`.
- O teto da empresa é opcional e compara com a soma dos limites, do gasto e da projeção.

### Permissões

```text
agente | concedidas | negadas | flags
Ana | tasks:assign, tools:use, agents:configure | users:invite | cota:3, criados:2
Bruno | * | | baixa_confianca
```

Flags aceitas: `baixa_confianca`, `gerenciado`, `cota:N`, `criados:N` e campos de runtime (`adapter:...`, `comando:...`, `cwd:...`, `env:...`, `sandbox:...`). As caixas “tratar todos como baixa confiança/gerenciados” aplicam a exceção à entrada inteira.

## Skills

| Skill | Entrada | O que devolve |
|---|---|---|
| `agency.roster` | equipe | Ciclos, raiz humana, responsável inativo, amplitude, orçamento e permissões sensíveis |
| `agency.board` | quadro | Dono, evidência, bloqueio, ciclo, WIP, atraso e objetivo |
| `agency.budget` | orçamentos | Utilização, estouro, alerta, parada ausente, projeção e teto da empresa |
| `agency.watchdog` | subárvore | Impressão digital, revisão devida/suprimida, verificação de cada folha e mandato |
| `agency.permissions` | permissões | Grants, negações, conflito, chave fora do catálogo, exceção e override de runtime |
| `agency.defaults` | — | Linha de base de permissões e exceções (referência) |

Todas as skills devolvem `executed: false` e `readOnly: true`, com `findings` em quatro partes (o que é, problema, correção, se ignorar), `verdict`, `counts` e `limitations`. O nível `lite` mostra apenas bloqueios; `ultra` acrescenta perguntas de revisão.

## Watchdog de parada

A verificação é o recorte mais fiel ao upstream: o watchdog observa uma subárvore, e não uma tarefa isolada.

```text
id | estado | dono | evidência | bloqueador | interação pendente | atualizado
ENG-1 | done | Ana | PR #3 e teste verde | — | — | 2026-10-20
ENG-2 | in_review | Bruno | — | — | — | 2026-10-19
ENG-3 | blocked | Carla | — | @ana marketing | — | 2026-10-18
```

- **Caminho vivo:** alguma folha em `queued`, `retry` ou em andamento. Enquanto existir, a revisão não dispara.
- **Impressão digital:** SHA-256 de um JSON canônico com a tarefa observada, as instruções e, para cada folha, `id`, estado, dono, evidência, bloqueador, interação e atualização. Mudou uma vírgula, muda o hash.
- **Supressão:** se a impressão digital é igual à última revisada, `suppressed: true` e `fired: false`. Informe o hash anterior na própria página (há um botão para reutilizá-lo).
- **Tarefa de revisão:** `watchdog-<slug>-<8 primeiros do hash>`, estável para a mesma parada — a mesma parada nunca gera duas revisões.
- **Alegações:** cada folha é classificada como verificada ou não. `done` sem evidência, `in_review` sem revisor, `blocked` sem causa/dono e `waiting` sem alvo são achados.
- **Mandato fixo:** cada folha é alegação; parada legítima registra o que foi checado; parada indevida restaura um caminho vivo; bloqueio real exige dono e próximo passo; nada fora do recorte; sem impersonar aprovação, gasto ou contratação; sem criar outro watchdog; sem acordar a si mesmo; uma revisão por impressão digital.
- **Instruções só estreitam:** a skill varre o texto e marca como bloqueio frases que ampliam o mandato (aprovar, gastar, contratar, criar outro watchdog, acordar a si mesmo, mexer fora da árvore), ignorando negações explícitas como “não crie outro watchdog”.

IDs do próprio watchdog podem ser excluídos do recorte pelo campo “IDs fora do recorte” — o equivalente ao `originKind='task_watchdog'` do upstream.

“Me acorde quando terminar” não é watchdog: no upstream isso é rotina ou interação com `continuationPolicy: wake_assignee`. Aqui, a página apenas aponta essa distinção.

## Linha de base de permissões

Concedido por padrão a um agente comum (18 chaves):

```text
agents:configure            agents:suggest-changes      skills:create
skills:suggest-changes      tools:manage_connections    tools:profiles
tools:view_audit            tools:use                   tools:manage_runtime
audit:view_agent_actions    inbox:manage                tasks:assign
tasks:assign_scope          tasks:manage_active_checkouts
canCreateAgents             canCreateSkills             config:read_own
self:wake
```

Negado por padrão (6 chaves):

```text
agents:create               environments:manage         tools:admin
users:invite                users:manage_permissions    joins:approve
```

Exceções e regras:

- Agentes de **baixa confiança** e **gerenciados** não recebem os grants novos (`agents:configure`, `skills:create`, `tools:manage_*`, `canCreateAgents`, `canCreateSkills`, `tasks:assign_scope`, `tasks:manage_active_checkouts`) até revisão explícita.
- **Sem backfill:** a revisão não altera permissões existentes; a migração fica a cargo de uma decisão registrada.
- O agente **não** define adapter de processo, comando de host, `cwd`, `env` arbitrário nem sandbox de filesystem. Esses campos são do operador; se aparecem nas flags do agente, são bloqueio.
- `canCreateAgents` exige `cota:N`; `criados:N` acima da cota é bloqueio.

## Ciclo de vida e estados

O upstream usa estados explícitos e transições válidas para não concluir uma operação com resultado antigo. O JARVIS não executa agentes, então esse ciclo fica como **referência de modelagem**, não como máquina de estados aplicada:

```text
pending_approval → preparing → verifying → ready
ready → pausing → paused → resuming → ready
ready|paused|pending_approval → terminating → cleaning_up → terminated
pending_approval → rejected
```

Regras que valem mesmo sem runtime: término pode começar antes da preparação; resultado de uma operação antiga não conclui a nova; comandos de pausa e término são assíncronos; mensagens recebidas durante o setup ficam em fila até `ready`. Estados na revisão de equipe são o recorte simplificado (`ativo`, `pausado`, `pendente`, `encerrado`, `rejeitado`, `sem_orcamento`).

## Limitações

- Tudo é declarado: a revisão não lê banco, runtime, provedor de identidade, fatura ou histórico de execução.
- Não há execução, agendamento, heartbeat, conexão com ferramentas ou alteração de permissões.
- Orçamento não converte moeda nem incorpora retries, picos ou mudança de modelo; a projeção é linear.
- A impressão digital cobre a parada e as instruções, não o conteúdo de arquivos, testes ou anexos.
- A varredura de instruções é lexical: encontra ampliações explícitas, não intenções implícitas.
- O quadro não substitui um sistema de tarefas; ele revisa o recorte colado.

## Verificação

```bash
npm test                                   # 38 testes web + 148 de API
.venv/bin/python -m pytest server/tests/test_agency.py -q
curl -s http://localhost:8000/api/health   # 0.17.0, 93 skills
```

Os testes de `server/tests/test_agency.py` cobrem as regras de cada análise, a supressão do watchdog, o mandato não ampliável, a linha de base e os caminhos da API.
