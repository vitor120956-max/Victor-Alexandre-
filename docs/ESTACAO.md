# Estação do agente

Tarefa durável, permissões, aprovação, recuperação após queda, agenda, limites e memória de um agente que trabalha num computador próprio. A adaptação parte de [`feder-cr/invisible_dots`](https://github.com/feder-cr/invisible_dots) (MIT, 2026), mas o código é local: nenhuma VM, QEMU, imagem dourada, navegador, chave OpenRouter, servidor MCP, Telegram, WhatsApp ou chamada de rede acontece aqui.

O upstream é um agente self-hosted: cada "Dot" é uma máquina virtual Linux com desktop persistente, um navegador próprio por identidade, memória escrita em arquivos e um contrato de permissões `allow`/`ask`/`deny` que decide cada chamada de ferramenta antes de ela rodar. O que a versão 0.16.0 traz é **o contrato de governança**, não a máquina: o plano de uma tarefa, a matriz de permissões, a auditoria de execução, a agenda, a classificação de limites e a higiene das notas — tudo determinístico, em texto e em português.

> **Uma recusa declarada.** O upstream se anuncia como "undetectable by anti-bot systems" e implementa fingerprint de navegador em C++. Esse ponto **não** é adaptado. `estacao.limites` bloqueia evasão de detecção, CAPTCHA, rotação de conta, proxy para furar limite e desrespeito a termos ou `robots.txt`, e apresenta a via oficial em cada caso. Esconder automação não é uma feature deste projeto.

---

## O que foi adaptado

| Do upstream | Aqui |
|---|---|
| `permissions:` com `allow`/`ask`/`deny` por ferramenta | Matriz de 14 permissões com risco, padrão e efeito de `ask` |
| `PERMISSIONS` e tabela de 30 ferramentas | Catálogo validado: ferramenta → permissão → risco → efeito |
| `ask` para a rodada, persiste a chamada e vale uma vez | Auditoria da política e do plano, com aviso de aprovação pendente |
| `tool.called` com intenção, resultado e `interrupted` | Leitura de recibos: sem resultado, dupla execução, aprovação reaproveitada, retomada sem conferir |
| Crash recovery: aceito não se perde, chamada cortada não repete | Critérios de parada e de retomada no plano e na auditoria de recibos |
| `cron` e automações recorrentes | Validador de cinco campos, sobreposição, presença, orçamento de acordadas |
| Sleep/wake com `idle_timeout` (15 min) | Verificação de ócio zero e de agenda que acorda demais |
| `MEMORY.md` até 25 000 caracteres | Auditoria de tamanho, segredo, fato sem dia e regra absoluta |
| Skills escritas pelo agente | Cartões com gatilho, passos, verificação e gatilho repetido |

### O que ficou de fora, de propósito

- **Nada de máquina.** Sem QEMU, KVM, imagem dourada, disco de runtime, systemd, `setup`, `doctor` ou `image build`.
- **Nada de navegador.** Sem Firefox patchado, fingerprint, proxy por identidade, perfil persistente ou `invisible_playwright_mcp`.
- **Nada de rede ou credencial.** Sem OpenRouter, PostgreSQL, `server.lock`, tokens, `secret openrouter` ou variáveis de ambiente lidas.
- **Nada de canal.** Sem Telegram, WhatsApp, SSE, webhook ou API de controle; nada é enviado a ninguém.
- **Nada de execução.** Nenhuma ferramenta é oferecida, chamada ou aprovada. Toda saída marca `executado: false` e `readOnly: true`.

---

## Ferramentas e permissões

Cada uma das 30 ferramentas declara **uma** permissão:

| Grupo | Ferramentas | Permissão | Risco |
|---|---|---|---|
| Execução | `exec`, `exec_session`, `list_exec_sessions` | `computer.exec` | alto |
| Arquivos (leitura) | `read_file`, `list_dir`, `find_files`, `grep` | `files.read` | baixo |
| Arquivos (escrita) | `write_file`, `edit_file`, `apply_patch` | `files.write` | médio |
| Futuro | `cron` | `automations` | alto |
| Tela | `computer_screenshot` | `computer.screenshot` | médio |
| Identidades | `browser_identity_*` | `browser.identity.*` | baixo a alto |
| Página (leitura) | `browser_navigate`, `browser_snapshot`, `browser_read_*`, `browser_take_screenshot`, `browser_evaluate` | `browser.read` | baixo |
| Página (ação) | `browser_click*`, `browser_type`, `browser_press_key`, `browser_select_option`, `browser_upload_files` | `browser.act` | alto |
| MCP | `add_mcp_server` | `mcp.servers.add` | alto |

Padrões quando a permissão não aparece na política — os mesmos do upstream:

- `computer.*`, `files.*`, `browser.*` e `memory.*` são **`allow`**;
- `browser.identity.delete` e `automations` são **`ask`**;
- permissão de MCP é **`ask`**;
- nome desconhecido é **`deny`**.

A auditoria trata como bloqueio obrigatório qualquer permissão de risco alto em `allow` — `computer.exec`, `automations`, `mcp.servers.add`, `browser.act` e `browser.identity.delete` —, ferramenta usada com permissão negada e permissão de MCP sem servidor declarado. Avisa, sem bloquear, quando a leitura está negada, quando se age na página sem poder lê-la, quando o limite de passos passa de 120, quando o custo passa de US$ 5 e quando `idle_timeout` é zero.

### O que `ask` faz

1. A chamada **para a rodada**: nada depois dela no mesmo turno roda.
2. A chamada é persistida com os **argumentos completos**, identificada pelo id.
3. A pessoa aceita ou recusa. A decisão é registrada **uma vez**; uma segunda é ignorada.
4. Ao aceitar, o modelo é avisado de que a chamada **não rodou** e precisa ser repetida; a aprovação libera **aquela** chamada, **uma vez**.
5. A aprovação não vira permissão: a próxima chamada `ask` pede de novo.

Por isso a auditoria reprova aprovação reaproveitada em mais de uma chamada: a pessoa aprovou uma coisa e o agente fez outra.

---

## O plano da tarefa

`estacao.tarefa` transforma um objetivo observável em passos com ferramenta, permissão e prova:

1. **Observar** — ler o estado antes de decidir.
2. **Agir** — a ferramenta que o verbo do objetivo pede.
3. **Verificar** — depois de escrever, executar ou agendar, ler de volta.
4. **Registrar** — gravar onde ficou e qual foi o resultado.

O plano é **lexical de propósito**: o verbo do objetivo escolhe a ferramenta (`abrir` → `browser_navigate`, `salvar` → `write_file`, `executar` → `exec`, `agendar` → `cron`), mas a ferramenta só entra se estiver declarada; se a permissão existe e a ferramenta não, a auditoria aponta `acao-sem-ferramenta` em vez de inventar. Nada aqui decide *o que* a tarefa deve fazer — isso é da pessoa.

Critérios de parada:

- **Concluída** quando a prova do objetivo é observada, não quando a chamada devolve `ok`.
- **Sem progresso** após três observações idênticas.
- **Aprovação pendente**: a rodada para.
- **Orçamento**: `max_steps_per_task` (padrão 60, teto 500) ou `max_cost_per_task_usd` (padrão US$ 1,00).
- **Queda**: reler o estado; não repetir chamada sem resultado.

---

## Execução e recuperação

`estacao.recibos` lê uma linha por chamada no formato:

```text
id=c1 tool=write_file status=ok result=gravado verificado=sim
id=c2 tool=write_file status=interrompido
```

Campos aceitos: `id`/`chamada`, `tool`/`ferramenta`, `status` (`intent`, `ok`, `erro`, `interrompido`, `recusado`), `approval`/`aprovacao`, `result`/`resultado` e `verificado=sim`. Separadores: `|` ou espaço antes de `chave=`.

Regras verificadas:

- **Chamada sem resultado** (`intent` ou `interrompido`, sem `ok`): pode ter sido aplicada e pode ainda estar rodando; exige leitura do estado antes de repetir.
- **Execução dupla**: a mesma chamada com dois `ok`. Uma chamada roda no máximo uma vez.
- **Aprovação reutilizada**: o mesmo `approval` em chamadas distintas.
- **Retomada sem conferir**: a chamada repetida não traz `verificado=sim`.
- **Status inválido**, **ferramenta fora do catálogo** (aceita prefixo `mcp_`) e **`ok` sem resultado**.

O recibo é despacho, não prova: a prova é o estado observado depois.

---

## Agenda

`estacao.agenda` lê `nome | cron | minutos | presença` por linha.

- **Cron de cinco campos**, aceito só com dia do mês e mês em `*`; dia da semana aceita lista e faixa (`1-5`), e `7` vira domingo.
- **Tempestade**: `* * * * *` (um disparo por minuto) é bloqueado — mantém a máquina acordada e esgota orçamento.
- **Sobreposição**: duas automações com janela comum no mesmo dia. A segunda espera ou falha.
- **Presença**: se a linha marca `sim` e o horário cai fora da janela (`9-18`), a automação para esperando alguém que não está.
- **Acordadas por dia**: quantas horas distintas ligam a máquina, comparadas ao orçamento declarado (padrão 8).
- **Duração** acima de 120 minutos vira aviso; dia quase todo ocupado também.

Atraso e queda: automação perdida enquanto a máquina dormia roda **uma vez** no próximo acordar; três falhas seguidas param a automação e avisam. Mudar a agenda é a permissão `automations`, que pede aprovação por padrão.

---

## Limites e consentimento

`estacao.limites` classifica cada ação pretendida em **liberada**, **confirmar** ou **bloqueada**.

Liberadas são as de leitura: ler, abrir, navegar, consultar, listar, baixar, conferir, buscar. O que não é reconhecido como leitura cai em **confirmar** — a classificação é conservadora de propósito.

Bloqueadas, por definição:

| Regra | Por quê |
|---|---|
| `indetectavel` | Esconder a automação fere os termos da maioria dos sites. |
| `fingerprint` | Forjar canvas, WebGL, fuso e fontes é evasão de controle de acesso. |
| `captcha` | O desafio existe para separar pessoa de programa. |
| `limite` | Proxy ou conta extra para escapar de 429 sobrecarrega o serviço. |
| `contas` | Várias contas para o mesmo fim contornam limite e banimento. |
| `termos` | O contrato do site vale mesmo quando é tecnicamente possível. |
| `dados` | Raspar dado pessoal sem base legal viola LGPD e equivalentes. |
| `credencial` | Acesso com conta alheia é apropriação de identidade. |

Cada bloqueio traz **a alternativa legítima**: API oficial, canal autorizado, `Retry-After`, consentimento do titular, login feito pela própria pessoa.

---

## Memória e skills

`estacao.memoria` audita o que o agente escreveu sobre si:

- **Tamanho**: acima de 25 000 caracteres, o fim do `MEMORY.md` não entra no prompt.
- **Segredo aparente**: `sk-…`, `api_key=`, `token=`, `senha=`, chave privada e `ghp_…` viram bloqueio — nota é lida, copiada e versionada.
- **Fato sem dia**: cada fato precisa da data em que foi aprendido, ou envelhece sem aviso.
- **Regra absoluta**: `sempre`, `nunca`, `jamais`, `todos os dias` viram aviso.
- **Skill sem gatilho** e **skill sem verificação** são bloqueios; **gatilho repetido** é aviso.
- **Segredo dentro de skill** é bloqueio.

Formato de skill aceito:

```text
nome: fechar-planilha
gatilho: quando pedirem o fechamento do mês
passos: abrir a planilha; conferir totais; salvar PDF
verificacao: o PDF existe e os totais batem
permissoes: files.read, files.write
```

Blocos separados por `---`.

---

## As sete skills

| Skill | O que faz |
|---|---|
| `estacao.tarefa` | Objetivo → passos com ferramenta, permissão, prova, parada e orçamento. |
| `estacao.permissoes` | Política → matriz allow/ask/deny, risco alto livre, ferramenta negada, MCP sem servidor. |
| `estacao.recibos` | Log → chamada sem resultado, execução dupla, aprovação reaproveitada, retomada sem conferir. |
| `estacao.agenda` | Automações → cron válido, sobreposição, presença, acordadas por dia. |
| `estacao.limites` | Ações → liberada, confirmar ou bloqueada, com alternativa em cada bloqueio. |
| `estacao.memoria` | Notas e skills → tamanho, segredo, fato sem dia, gatilho e verificação. |
| `estacao.regras` | Catálogo: 30 ferramentas, 14 permissões, 6 estados, 8 regras de evasão e orçamentos. |

Todas devolvem `findings` no formato de `server/review.py` (o que é, problema, correção, o que acontece se ignorar), `counts`, `verdict`, `metrics`, `rows`, `limitations` e `markdown`. **Nenhuma altera configuração, arquivo ou processo.**

---

## Página `/estacao`

Sete abas: **Tarefa**, **Permissões**, **Execução**, **Agenda**, **Limites**, **Memória** e **Regras**. Níveis `lite` (só obrigatórios), `full` e `ultra` (com perguntas). Cada aba tem exemplo próprio; o catálogo é lido de `estacao.regras` na primeira abertura.

- A matriz pinta cada permissão pela decisão (`allow` verde, `ask` âmbar, `deny` vermelho) e mostra o padrão.
- Os recibos listam chamada, ferramenta, status, aprovação e se o estado foi conferido.
- Limites mostram a alternativa em cada bloqueio, sem esconder a recusa.
- A página não guarda nada: recarregar limpa o resultado.

---

## Determinismo e limites

- Mesma entrada, mesmos achados: nenhuma chamada de modelo, nenhum relógio, nenhuma ordem de dicionário.
- A análise é **lexical**: lê verbos e palavras, não intenção. Um texto ambíguo cai no lado mais restritivo.
- O catálogo vem da documentação pública do upstream em outubro de 2026; ferramentas e padrões podem mudar.
- O custo é **estimativa declarada**, não medição; o gasto real depende do modelo e do provedor.
- A agenda é calculada numa semana genérica, sem fuso nem horário de verão.
- Bloquear não é sanção: é o limite do que este núcleo se dispõe a preparar.

---

## Como rodar e testar

```bash
# API
.venv/bin/python -m uvicorn server.app:app --reload --port 8000

# página
npm run dev   # http://localhost:5173/estacao

# testes
.venv/bin/python -m pytest server/tests -o addopts="" -q

# smoke
curl -s http://localhost:5173/api/skills/estacao.limites/execute \
  -H 'content-type: application/json' \
  -d '{"parameters":{"acoes":"ler o extrato\nresolver captcha","modo":"full"}}'
```

---

## Licença e atribuição

O upstream é MIT, © 2026 feder-cr. O texto integral está em [`licenses/feder-cr-invisible-dots.txt`](licenses/feder-cr-invisible-dots.txt). Nenhum código do upstream foi copiado: a adaptação reescreve as regras em Python e **recusa explicitamente** a parte de evasão de detecção.
