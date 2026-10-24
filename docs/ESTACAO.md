# Estação do agente

Execução real, permissões, fila de aprovação, recuperação após queda, agenda e memória. A adaptação parte de [`feder-cr/invisible_dots`](https://github.com/feder-cr/invisible_dots) (MIT, 2026), mas sem a máquina do upstream: aqui o agente roda no seu próprio sistema de arquivos, não numa VM.

Duas camadas, com regras diferentes:

| Camada | O que faz | Executa algo? |
|---|---|---|
| **Executor** (`server/estacao_runtime.py`) | Roda `bash`, lê e grava arquivos, busca com regex, agenda automações | **Sim**, no diretório da Estação |
| **Análise** (`server/estacao.py`, 7 skills) | Planeja a tarefa, audita a política, lê recibos, valida a agenda, classifica efeitos, revisa notas | Não — devolve texto |

---

## O executor

### Ferramentas

| Ferramenta | Permissão | O que faz |
|---|---|---|
| `exec` | `computer.exec` | `bash -lc` no diretório da Estação, com `timeout_s` (1–600) e `diretorio` opcional |
| `read_file` | `files.read` | Lê texto por linha, detecta binário, corta em 20 000 caracteres |
| `write_file` | `files.write` | Grava um arquivo inteiro; `simular: true` não grava |
| `list_dir` | `files.read` | Lista até 300 entradas, com ou sem recursão |
| `grep` | `files.read` | Expressão regular nos arquivos, até 200 achados |
| `cron` | `automations` | Cria automação que roda `exec` no horário do cron |

Argumento desconhecido é recusado — `{"comando":"ls","shell":true}` devolve erro em vez de adivinhar.

### Permissões e o gate

Cada chamada passa por uma decisão antes de rodar:

| Decisão | Efeito |
|---|---|
| `allow` | Roda na hora e grava o resultado |
| `ask` | Fica **pendente** com os argumentos completos, esperando decisão |
| `deny` | Não roda; o recibo registra `negado` |

Padrões: `files.read` em `allow`; `computer.exec`, `files.write` e `automations` em `ask`.

A política é editável pela página (`allow` / `ask` / `deny` em cada permissão) e grava em SQLite. Mude para `allow` e o mesmo comando roda direto; mude para `deny` e ele é recusado sem tocar no disco. **Não há lista de assuntos proibidos** — quem decide é a sua política.

### Aprovação

1. A chamada `ask` fica em `pendente`, com os argumentos guardados no banco.
2. O painel mostra a fila; aprovar executa, recusar encerra com `recusado` e a nota.
3. A decisão é registrada **uma vez**: uma segunda tentativa devolve `ignorada: true` com o motivo.
4. A aprovação libera **aquela** chamada, não a permissão — a próxima `ask` pede de novo.

Concorrência: a execução reivindica a linha com `UPDATE ... WHERE estado='pendente'`, então aprovar duas vezes (ou clicar duas vezes) não roda duas vezes.

### Recibos

Toda chamada escreve uma linha por evento, em ordem, com hora:

```text
seq  chamada       evento        detalhe
3    d38d521245b0  ok            18 ms
2    d38d521245b0  aprovado      visto
1    d38d521245b0  intent        exec echo ola-estacao && pwd
```

Eventos: `intent`, `aprovado`, `ok`, `erro`, `recusado`, `negado`, `interrompido`.

### Recuperação

Se o processo cair no meio de uma chamada, a linha fica em `executando`. Na próxima entrada (`POST /api/estacao/recuperar`, chamado também no start da API), ela vira `interrompido` com a mensagem:

> Esta chamada foi interrompida antes de o resultado ser registrado. Pode ter surtido efeito e pode ainda estar rodando. Confira o estado atual antes de chamar de novo.

Chamada interrompida **não roda de novo**: aprovar depois não a executa.

### Agenda

`cron` com cinco campos (sem dia do mês e mês restritos, como na validação da análise) vira automação real:

- o agendador da API verifica a cada 30 s;
- cada disparo passa pelo mesmo gate — com `automations=ask`, a execução também pede aprovação;
- três falhas seguidas pausam a automação;
- pausar, ativar e remover pela página.

### Confinamento — o que ele é e o que não é

**É:** caminhos presos ao diretório da Estação (`..`, absoluto, oculto e symlink recusados), ambiente do subprocesso reduzido a `PATH`/`HOME`/`LANG`/`TERM` (sem `JARVIS_*`, sem `.env`), timeout com `SIGKILL` no grupo de processos, saída cortada em 20 000 caracteres.

**Não é:** jaula de sistema operacional. Um comando aprovado como `exec` pode ler `/etc/passwd` ou acessar a rede — é shell com os seus privilégios de usuário. Para isolar de verdade seria preciso uma VM ou um contêiner, e **esse é justamente o componente do upstream que este repositório não tem**: sem QEMU, sem imagem dourada, sem systemd no guest.

---

## A análise (7 skills, somente leitura)

| Skill | O que faz |
|---|---|
| `estacao.tarefa` | Objetivo → passos com ferramenta, permissão, prova, parada e orçamento |
| `estacao.permissoes` | Política → matriz, risco alto em `allow`, ferramenta negada, MCP sem servidor |
| `estacao.recibos` | Log → chamada sem resultado, execução dupla, aprovação reaproveitada, retomada sem conferir |
| `estacao.agenda` | Automações → cron válido, sobreposição, presença, acordadas por dia |
| `estacao.limites` | Ações → liberada, confirmar ou **irreversível**, por efeito declarado |
| `estacao.memoria` | Notas e skills → tamanho, segredo, fato sem dia, gatilho, verificação |
| `estacao.regras` | Catálogo: 30 ferramentas, 14 permissões, 6 estados, 6 regras de efeito |

### Limites por efeito, não por assunto

`estacao.limites` classifica pelo que a ação faz, não pelo tema:

| Nível | Quando | Exemplo |
|---|---|---|
| `liberado` | Verbo de leitura | `ler o extrato` |
| `confirmar` | Efeito externo ou indefinido | `enviar e-mail`, `organizar a pasta` |
| `irreversivel` | Não tem desfazer | `apagar os comprovantes`, `pagar a fatura` |

O nível é informativo: quem decide executar é o gate do executor. Não existe lista de assuntos vetados.

---

## API

| Rota | O que faz |
|---|---|
| `GET /api/estacao/estado` | Política, ferramentas, chamadas, pendentes, automações |
| `POST /api/estacao/executar` | `{ferramenta, argumentos, tarefa}` → chamada (pendente ou executada) |
| `GET /api/estacao/aprovacoes` | Fila de aprovação |
| `POST /api/estacao/aprovacoes/{id}/decidir` | `{aprovado, nota}` |
| `PUT /api/estacao/politica` | `{permissao, decisao}` |
| `GET`/`POST`/`DELETE /api/estacao/agenda` | Automações |
| `POST /api/estacao/agenda/tick` | Dispara vencidas agora (o agendador já faz a cada 30 s) |
| `POST /api/estacao/recuperar` | Marca `executando` como `interrompido` |

Uso direto:

```bash
curl -s localhost:8000/api/estacao/executar -H 'content-type: application/json' \
  -d '{"ferramenta":"exec","argumentos":{"comando":"echo ola && pwd"}}'
curl -s -X POST localhost:8000/api/estacao/aprovacoes/<id>/decidir \
  -H 'content-type: application/json' -d '{"aprovado":true}'
```

---

## Página `/estacao`

Oito abas. A primeira, **Executor**, é operacional: escolhe a ferramenta, edita os argumentos em JSON, roda e vê o resultado; edita a política; decide a fila; lê as chamadas recentes; cria e pausa automações. As outras sete são análise, com níveis `lite`/`full`/`ultra`.

---

## Como rodar e testar

```bash
.venv/bin/python -m uvicorn server.app:app --reload --port 8000
npm run dev                      # Vite em 5173, proxy para a API
.venv/bin/python -m pytest server/tests -o addopts="" -q
```

O banco fica em `storage/estacao/estacao.db` (fora da área de arquivos e fora do Git).

---

## Licença e atribuição

O upstream é MIT, © 2026 feder-cr. Texto integral em [`licenses/feder-cr-invisible-dots.txt`](licenses/feder-cr-invisible-dots.txt). Nenhum código do upstream foi copiado: o executor é SQLite + `subprocess`, escrito aqui, e a VM/QEMU do upstream não está presente.
