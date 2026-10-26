# 0.56.0 — agenda, backup e Git de leitura

Três coisas de rotina que faltavam, e um erro de promessa que foi corrigido.
Nada aqui usa modelo, chave ou conta.

---

## 1. Agenda — ele guarda o que você tem para tal dia

```text
marca audiência amanhã às 14h
→ Marcado: audiência — terça-feira, 27/10/2026 às 14:00.

o que eu tenho para hoje
→ 2 compromisso(s) na agenda.
  • [4f1a] Audiência — terça-feira, 27/10/2026 às 14:00
  • [9c02] Entregar petição — quinta-feira, 29/10/2026 às 09:00
```

- **A data é lida sem modelo.** `2026-11-05`, `05/11`, `amanhã`, `depois de
  amanhã`, `daqui a 3 dias`, `segunda`, `quinta às 10h`, `14h30` — e sem hora
  fica às 09:00, dito na resposta.
- **Nunca adivinha em silêncio.** Frase sem data reconhecível recebe uma recusa
  com os formatos aceitos. Data no passado é recusada.
- **Mostra o que entendeu por extenso** antes de você confiar: “terça-feira,
  27/10/2026 às 14:00”.
- Fica em `agenda.json` na raiz de dados. Sem conta, sem nuvem, sem sincronização.

**O limite, dito:** ele **não avisa sozinho** e **não toca no calendário do
Windows nem no Google Agenda**. Você pergunta, ele responde.

Skills: `agenda.marcar`, `agenda.listar`, `agenda.concluir`, `agenda.remover`.

## 2. Backup — um `.zip` que abre, com prova de que abriu

```text
faz backup dos meus dados em E:/JARVIS-backups
→ Backup criado: jarvis-dados-20261026-141233.zip — 1.842 arquivo(s), 96,4 MB,
  sha256 3f9a2c1e…

quanto vai pesar o backup
→ 1.842 arquivo(s), 96,4 MB. Maiores: livros/direito-civil.pdf (12,3 MB)…
  ⚠️ O destino está no mesmo disco dos dados: protege contra apagar sem querer,
     não contra o disco morrer. Um pendrive ou o Drive resolve.
```

- Compacta `storage/` **sem** `.venv`, `node_modules`, `__pycache__`, `.git` e
  **sem a própria pasta de backups** (senão cada rodada engordaria a próxima).
- Grava o **SHA-256** ao lado e o manifesto `.json` com a lista de arquivos.
- **Abre o `.zip` logo depois de escrever** e recusa se saiu corrompido.
- Avisa quando o destino está no **mesmo disco** dos dados.
- Restaura só em pasta **vazia**, recusando caminho que saia da pasta (zip-slip).
- Teto de 2 GB por padrão, ajustável.

**O limite, dito:** não agenda backup automático, não apaga os antigos e **não
criptografa** o `.zip`.

Skills: `backup.planejar`, `backup.criar`, `backup.listar`, `backup.restaurar`.

## 3. Git — enxergar sem estragar

```text
como está o git
→ Branch: arena/f26cfa7a-victor-alexandre
  • M server/skill_registry.py
  • ?? server/agenda.py

últimos commits do git
→ • f97e2e5 2026-10-26 — 0.55.0: instalador que confere antes de instalar…
```

Quatro consultas, cada uma com os argumentos fixos no código:

| Skill | Comando |
|---|---|
| `git.status` | `git status --porcelain=v1 -b` |
| `git.log` | `git log -n N --pretty=…` |
| `git.diff` | `git diff` / `git diff --staged` |
| `git.remoto` | `git remote -v` + upstream |

**Não existe campo para linha de comando.** `commit`, `push`, `pull`, `clone`,
`checkout`, `reset`, `clean`, `merge` e `rebase` não são aceitos nem como texto
livre. Roda com `shell=False`, `GIT_TERMINAL_PROMPT=0` (nunca pede senha), sem
paginador e com teto de 20 segundos.

Só olha repositório dentro de três lugares: a pasta do projeto, a raiz de dados
e `storage/repos`. Fora disso, recusa.

## 4. Correção: fora do Windows, ele não promete mais “roda”

A análise do instalador media o arquivo e comparava com o Windows. Quando a
análise rodava **fora** do Windows (na máquina de teste, Linux), não havia build
para comparar — e mesmo assim o veredito saía **“roda”**. Agora sai **“não dá
para saber”**, com a frase “não estou no Windows, então não comparo com o build
do seu PC” e o motivo. O que é decisivo continua decisivo: programa de 16 bits,
ARM64 em x64 e MSIX no 1607 continuam **“não roda”** em qualquer sistema.

Na sua máquina, que é Windows, nada muda — o veredito já usava o build real.

## 5. Medido

| Verificação | Resultado |
|---|---|
| Skills no registro | **281** (12 novas) |
| Suíte Python | **2.563** testes |
| Interface | **110** testes (vitest) |
| Tipos | `npx tsc -b` sem erro |
| Interface embutida | `npm run build:embutido` refeito |

Novos arquivos de teste: `test_agenda.py` (14), `test_backup.py` (9),
`test_git.py` (10) — o Git é testado com um repositório criado na hora em
`tmp_path`; o backup com arquivos de verdade, abrindo o `.zip` de novo para
conferir o manifesto.

## 6. Como atualizar no seu PC

```bat
cd /d D:\JARVIS
git pull
set JARVIS_HOST_REDE=1
.venv\Scripts\python iniciar.py
```

Confira em `http://127.0.0.1:8000/api/health`:

```json
{"version": "0.56.0", "skills": 281}
```

## 7. Arquivos

- `server/agenda.py` — datas relativas, arquivo, status e texto do chat.
- `server/backup.py` — planejar, criar com hash e teste de abertura, listar,
  restaurar com recusa de zip-slip.
- `server/git.py` — as quatro consultas, com lista de raízes permitidas.
- `server/skill_registry.py` — 12 modelos Pydantic, 12 handlers, 12 entradas.
- `server/agente_local.py` — falas do chat, três formatadores de resposta.
- `server/instalador.py` — veredito fora do Windows.
- `server/tests/` — `test_agenda.py`, `test_backup.py`, `test_git.py` e casos
  novos em `test_agente_local.py` e `test_instalador.py`.
- `docs/AGENDA-BACKUP-GIT.md` — o documento completo desta rodada.

## 8. O que **não** entrou, e por quê

- **Lembrete automático** (“me avisa às 13h30”): exigiria um processo sempre
  ligado, com notificação do Windows. A agenda é consultada, não empurrada.
- **Backup agendado**: dá para fazer com o Agendador de Tarefas chamando a API,
  mas não está montado — e um backup que roda sozinho precisa de rotação e de
  teste de restauração, que também não existem.
- **Git de escrita** (`commit`/`push`): fica para uma skill própria, com plano,
  token e confirmação — o mesmo desenho do instalador. Hoje ele só lê.
