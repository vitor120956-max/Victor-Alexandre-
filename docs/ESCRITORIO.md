# Escritório assistido

Comando, receita, paginação, lote, escopos e triagem de erro para o Google Workspace. A adaptação parte de [`googleworkspace/cli`](https://github.com/googleworkspace/cli) (Apache-2.0, 2026), mas o código é local: nenhum binário Rust, release, `npm install -g`, extensão do Gemini, `gcloud`, OAuth ou chamada ao Google acontece aqui.

O upstream é um CLI que **não carrega uma lista fixa de comandos**: lê o documento de descoberta do Google em tempo de execução (com cache de 24 h) e monta a árvore `serviço → recurso → método`. Toda chamada vira `gws <serviço> <recurso> <método> --params '<json>' --json '<json>'`, com saída JSON estruturada, paginação automática, `--dry-run` e códigos de saída estáveis. É isso que a versão 0.15.0 traz, em português: o **contrato da linha de comando**, não o binário.

---

## O que foi adaptado

| Do upstream | Aqui |
|---|---|
| Árvore montada da descoberta (`drive files list`) | Montador validado: serviço, recurso, método, `--params` e `--json` |
| `--dry-run` para ver o pedido sem enviar | Ensaio obrigatório em escrita e proibido em leitura |
| `--page-all`, `--page-limit` (10), `--page-delay` (100 ms) | Leitura de páginas com token, duplicata, chave de itens e próxima chamada |
| `batchUpdate`/`batchModify` com corpo único | Planejador de lote com teto curado, validação por item e aviso de atomicidade |
| Escopos pedidos no `auth login` | Comparação entre operações, escopos exigidos, concedidos, faltando e sobrando |
| Códigos de saída 0 a 5 e `reason` da API | Triagem com causa, ação, comando e política de repetição |
| Ajudantes `+send`, `+append`, `+agenda` | Catálogo de 29 ajudantes com flags permitidas |
| 50+ receitas e personas do repositório | 15 receitas com passos, ensaio, verificação e saída de emergência |

### O que ficou de fora, de propósito

- **Nada de CLI.** Sem download de release, `cargo install`, Homebrew, Nix, `npm install -g` ou execução do binário.
- **Nada de autenticação.** Sem `auth setup`, `auth login`, `auth export`, service account, token do `gcloud` ou leitura de `~/.config/gws`.
- **Nada de rede.** Nenhuma chamada ao Google, nenhuma leitura da descoberta ao vivo, nenhum download de anexo.
- **Nada de persona ou extensão.** Sem `gemini extensions install`, sem plugins do Claude/Codex, sem `skills add`.
- **Nada de execução silenciosa.** Toda saída marca `executado: false`; o comando é texto para você revisar.

---

## O comando

### Forma

```bash
gws <serviço> [<recurso>] <método> \
  --params '<objeto JSON>' \
  --json '<objeto JSON>' \
  [--dry-run] [--page-all --page-limit N --page-delay MS]
```

Exemplos que a skill monta:

```bash
gws drive files list --params '{"pageSize":5,"q":"trashed = false"}'
gws gmail users.messages get --params '{"userId":"me","id":"18f2c9a1","format":"metadata"}'
gws sheets spreadsheets values append \
  --params '{"spreadsheetId":"1AbC","range":"Vendas!A1","valueInputOption":"USER_ENTERED"}' \
  --json '{"values":[["Ana","95"]]}'
gws calendar events insert --params '{"calendarId":"primary"}' \
  --json '{"summary":"Revisão","start":{"dateTime":"2026-11-03T10:00:00-03:00"},"end":{"dateTime":"2026-11-03T11:00:00-03:00"}}' \
  --dry-run
```

### Regras do montador

- O JSON é compactado e embrulhado em **aspas simples**, com `'\''` para aspas internas — o mesmo cuidado que o `!` de intervalo de planilha exige no shell.
- `--params` e `--json` precisam ser **objetos**. Array, número ou string solta é recusado antes de virar comando.
- Recurso aceita pontos (`users.messages`, `spreadsheets.values`) e o método aceita `recurso.metodo` junto.
- Ajudantes (`+send`, `+append`, `+agenda`) não usam recurso nem `--params`: as flags vão em um campo próprio e passam por uma **lista branca por ajudante**.
- `--upload` só vale em `drive files create`/`update`; `--sanitize` exige o formato `projects/P/locations/L/templates/T`; `--page-limit`/`--page-delay` só com `--page-all`.
- Parâmetro de caminho obrigatório é conferido por uma tabela curada: `fileId`, `spreadsheetId`, `range`, `userId` + `id`, `calendarId`, `documentId`, `presentationId`, `parent`, `tasklist`.

### Risco e ensaio

| Risco | Exemplos | Regra |
|---|---|---|
| leitura | `list`, `get`, `export`, `search`, `watch` | nunca recebe `--dry-run` |
| escrita | `create`, `insert`, `update`, `batchUpdate`, `send` | ensaio recomendado; corpo obrigatório |
| destrutivo | `delete`, `trash`, `empty`, `clear`, `move` | ensaio + confirmação dos IDs |

O ensaio não garante nada sobre o resultado: ele mostra o pedido HTTP, não o efeito.

---

## Receitas

Quinze roteiros determinísticos, cada um com entrada obrigatória marcada, passos ordenados, ensaio antes da escrita, **como saber que deu certo** e, quando existe, como desfazer.

| Receita | Serviços | Passos |
|---|---|---|
| `agenda-do-dia` | Calendar | fuso da conta → `+agenda --today` |
| `standup` | Workflow | `+standup-report` |
| `digest-semanal` | Workflow | `+weekly-digest` |
| `triagem-da-caixa` | Gmail | `+triage` → `messages list --page-all` |
| `enviar-email` | Gmail | `+send --dry-run` → `+send` |
| `responder-email` | Gmail | `messages get` → `+reply --dry-run` → `+reply` |
| `ler-planilha` | Sheets | `+read` |
| `acrescentar-linha` | Sheets | cabeçalho → `+append --dry-run` → `+append` |
| `subir-arquivo` | Drive | `files create --upload --dry-run` → real → `files list` |
| `organizar-pasta` | Drive | `files list --page-all` → `files update addParents/removeParents` |
| `convidar-evento` | Calendar | `events insert --dry-run` → real → `events get` |
| `arquivar-rotulados` | Gmail | `labels list` → `messages list` → `batchModify` |
| `tarefa-do-email` | Workflow | `messages get` → `+email-to-task` |
| `relatorio-de-planilha` | Sheets + Docs | `+read` → `jq` → `docs +write` |
| `checar-arquivos-grandes` | Drive | `files list --page-all` → `jq sort_by(size)` |

Regras da receita:

- Entrada obrigatória vazia é bloqueio; entrada opcional vazia vira marcador `${NOME}` para você substituir.
- Escrita sem ensaio equivalente é achado `should`.
- Receita que pede mais de cinco escopos recebe aviso: divida por serviço.
- O plano inteiro em ensaio é avisado, porque as verificações não vão encontrar o efeito que ainda não aconteceu.

---

## Páginas

A leitura aceita **uma página**, **NDJSON** (uma por linha, como `--page-all` imprime) ou um **array** de páginas.

O parser descobre a chave dos itens (`files`, `messages`, `threads`, `values`, `events`, `spaces`, `tasks`, `responses`, `changes`, `permissions`, `calendars`…) ou usa a que você fixar. Para cada página: chave, total, únicos, token e `nextSyncToken`.

O que ele cobra:

- `nextPageToken` na última página → **coleta incompleta**, com a próxima chamada montada (`pageToken` mesclado aos parâmetros base).
- Token repetido entre páginas → laço; pare e recomece.
- IDs repetidos → deduplique antes de agir em lote.
- Item sem `id` → não há como chamar o `get` seguinte.
- Chaves misturadas (`files` e `messages` na mesma coleta) → total sem sentido.
- Página com objeto `error` → o total está furado.
- Itens que são só strings → cada detalhe custa um `get`.

`--page-all` imprime **NDJSON**, não um array: um `jq -s` é necessário para tratar tudo junto.

---

## Lotes

| Operação | Teto curado | Corpo |
|---|---|---|
| `sheets.valores` | 100 | `{"valueInputOption":…,"data":[…]}` |
| `sheets.requisicoes` | 100 | `{"requests":[…]}` |
| `docs.requisicoes` | 100 | `{"requests":[…]}` |
| `gmail.ids` | 1000 | `{"ids":[…],"addLabelIds":…,"removeLabelIds":…}` |
| `drive.permissoes` | 1 | uma escrita por arquivo |
| `calendar.eventos` | 1 | um `events insert` por evento |

Cada item é validado antes de entrar no lote: `range` + `values` em Sheets, **exatamente uma chave** por requisição de `batchUpdate`, ID não vazio no Gmail, `fileId` + `permission` no Drive, `summary` + `start` + `end` no Calendar.

`batchUpdate` é **atômico por chamada**: um item inválido derruba o lote inteiro. Operações sem lote viram N chamadas independentes, sem ordem garantida.

---

## Escopos e consentimento

Cada operação declarada (`gmail users.messages list`, `sheets +append`, `drive files create`) aponta o escopo mínimo. A comparação entende superconjunto: `drive` cobre `drive.file` e `drive.readonly`; `spreadsheets` cobre `spreadsheets.readonly`.

| Situação | Efeito |
|---|---|
| falta escopo | `403 insufficientPermissions` na primeira chamada |
| sobra escopo | acesso maior que o trabalho exige — dívida de consentimento |
| mais de 25 escopos | app em teste recusa o consentimento |
| escopo fora do catálogo | pode ser novo do Google ou erro de digitação |

O comando de correção é montado junto: `gws auth login --scopes drive.file,gmail.readonly,spreadsheets`. Revogar consentimento antigo é ação no navegador, em `myaccount.google.com/permissions`.

Presets existem (`recommended`, `drive`, `gmail`, `calendar`, `sheets`, `docs`, `admin`), mas o preset largo é justamente o que estoura o limite de teste.

---

## Erros

### Códigos de saída

| Código | Significado |
|---|---|
| 0 | sucesso |
| 1 | erro de API (4xx/5xx do Google) |
| 2 | erro de autenticação |
| 3 | erro de validação (argumento, serviço ou flag) |
| 4 | erro de descoberta |
| 5 | erro interno do CLI |

### Reasons mapeados

`accessNotConfigured`, `rateLimitExceeded`, `userRateLimitExceeded`, `quotaExceeded`, `backendError`, `invalid_grant`, `invalid_token`, `insufficientPermissions`, `ACCESS_TOKEN_SCOPE_INSUFFICIENT`, `redirect_uri_mismatch`, `notFound`, `failedPrecondition`, `invalid`. Sem `reason`, o status HTTP decide (400/401/403/404/409/429/5xx) e, por fim, o código de saída.

### Política de repetição

- **Cota e falha transitória**: repetir com espera determinística (base do motivo, dobrando até 60 s).
- **Autenticação e permissão**: repetir não resolve; reautentique ou ajuste o escopo.
- **Validação e não encontrado**: repita só depois de corrigir o pedido.
- **Escrita não idempotente**: **nunca** repetir às cegas — a chamada pode ter sido aplicada mesmo com erro. Leia o recurso e compare.

---

## As sete skills

| Skill | Entrada | Devolve |
|---|---|---|
| `escritorio.comando` | serviço, recurso, método, params, corpo, argumentos, flags | comando, partes, risco, escopos, achados |
| `escritorio.receita` | receita, entradas, ensaio | passos com comando, por quê, verificação, escopos e rollback |
| `escritorio.paginas` | páginas, chave, campo de ID, comando e params base | páginas, únicos, duplicados, se está completa e a próxima chamada |
| `escritorio.lote` | operação, itens, parâmetros, limite | lotes com corpo, recusados, contagem de chamadas |
| `escritorio.escopos` | operações, concedidos | exigidos, faltando, sobrando e o `auth login` |
| `escritorio.erros` | código, mensagem, tentativas, idempotência | causa, ação, comando, repetir e espera |
| `escritorio.regras` | — | 18 serviços, 10 flags, 6 códigos, 31 escopos, 15 receitas, 6 lotes, 13 erros |

Todas devolvem `executado: false`. Nenhuma autentica, chama API, lê credencial, grava arquivo ou instala o CLI.

---

## Página `/escritorio`

Sete abas com exemplo próprio e nível `lite`, `full` ou `ultra`:

- **Comando** — comando pronto, botão de copiar, risco, escopos e achados;
- **Receita** — passos com ensaio, verificação e saída de emergência;
- **Páginas** — métricas, tabela de páginas e próxima chamada;
- **Lote** — itens recusados e um bloco de comando por lote;
- **Escopos** — exigidos, diferença, operações e reautenticação;
- **Erros** — diagnóstico, política de repetição e mensagem original;
- **Regras** — catálogo completo lido da API.

O relatório em Markdown é copiável em todas as abas.

---

## Determinismo e limites

- O catálogo de serviços, ajudantes e flags vem do README do upstream em outubro de 2026; `gws <serviço> --help` é a fonte final.
- A checagem de parâmetros obrigatórios é curada por recurso, não derivada da descoberta ao vivo.
- O mapa operação → escopo é curado; a descoberta pode exigir um escopo adicional.
- Os tetos de lote são conservadores e não medem bytes.
- A espera de retry não lê `Retry-After`: é calculada, para ser reproduzível.
- Nada é autenticado, enviado, baixado ou executado por estas skills.

---

## Como rodar e testar

```bash
.venv/bin/python -m pytest server/tests -q     # 484 testes, 103 deles em test_escritorio.py
npx vitest run                                 # 41 testes web
npx tsc --noEmit && npm run build
```

As skills ficam em `server/escritorio.py` e o registro em `server/skill_registry.py`. A página está em `src/pages/EscritorioPage.tsx`, com o CSS em `src/escritorio.css`.

---

## Licença e atribuição

O upstream está sob **Apache-2.0**. A licença completa está em [`docs/licenses/googleworkspace-cli.txt`](licenses/googleworkspace-cli.txt).

Este projeto não copia código do upstream: o montador, as receitas, a leitura de páginas, os lotes, os escopos e a triagem foram escritos aqui, a partir do contrato documentado. O CLI não é baixado, instalado ou executado, e este projeto não é um produto oficial do Google.
