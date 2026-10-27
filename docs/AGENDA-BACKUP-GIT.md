# Agenda, backup e Git — o que ele guarda, copia e enxerga

Três coisas que faltavam para o JARVIS ser útil no dia a dia, e que não precisam
de modelo nenhum:

1. **agenda** — guardar o que você tem para tal dia e devolver quando você
   perguntar;
2. **backup** — copiar o que importa para um `.zip` que abre, com hash ao lado;
3. **Git de leitura** — ver branch, commits e o que mudou, sem tocar no
   repositório.

As doze skills novas (0.59.0) estão descritas abaixo. Nenhuma delas chama provedor
de IA, nenhuma instala nada e nenhuma precisa de chave.

---

## 1. Agenda — `agenda.*`

Fica em `agenda.json`, dentro da raiz de dados (`storage/`, ou o que estiver em
`JARVIS_DADOS`). Sem conta, sem nuvem, sem sincronização. É um arquivo de texto
que você pode abrir no Bloco de Notas.

| Skill | O que faz | Efeito |
|---|---|---|
| `agenda.marcar` | grava um compromisso e mostra **como entendeu** a data | grava |
| `agenda.listar` | lista em ordem de data, marca o atrasado, diz o próximo | só lê |
| `agenda.concluir` | marca como feito, sai da lista sem ser apagado | grava |
| `agenda.remover` | apaga o compromisso | grava |

### A regra: nunca adivinhar data

Se a frase não tiver uma data reconhecível, ele **recusa** e pede outra — em vez
de marcar no dia errado. Quando reconhece, devolve por extenso o que entendeu:

```text
marca audiência amanhã às 14h
→ Marcado: audiência — terça-feira, 27/10/2026 às 14:00.
```

Formatos que ele entende:

- `2026-11-05`, `05/11/2026`, `05/11` (sem ano e já passado → próximo ano);
- `hoje`, `amanhã`, `depois de amanhã`, `daqui a 3 dias`;
- dia da semana: `segunda`, `terça-feira`, `sábado`… sempre o **próximo**
  (se hoje é segunda e você diz “segunda”, vale a semana que vem);
- hora: `às 14h`, `14h30`, `14:30`, `14 horas`. **Sem hora, fica às 09:00** — e o
  retorno mostra isso, você não precisa lembrar.

O que ele recusa:

- data que já passou (marcar o passado não serve para lembrar de nada);
- frase sem data (`marca o compromisso da reunião`) — devolve a lista de formatos;
- título repetido na hora de concluir/remover: pede o **id curto** em vez de
  escolher por você.

### Lembretes: o aviso chega enquanto a janela está aberta (0.59.0)

Cada compromisso guarda por quantos minutos antes avisar (`avisar_antes`, 30 por
padrão; `0` desliga). A skill `agenda.lembretes` responde “o que precisa de
atenção agora” — o que já passou e o que entra na janela:

```text
o que está vencendo agora
→ 2 lembrete(s) agora.
  • Prazo — segunda-feira, 26/10/2026 às 10:20 (atrasado há 6h40)
  • Audiência — terça-feira, 27/10/2026 às 14:00 (em 25 min)
```

E a tela consulta sozinha, a cada 45 segundos, `GET /api/agenda/lembretes`.
Quando aparece algo novo, ela mostra o aviso, escreve no chat e — se você já
tiver dado permissão de notificação ao navegador — dispara a notificação do
sistema. O que já foi mostrado fica na memória da aba (chave `id|quando|tipo`),
então o mesmo compromisso não avisa duas vezes e reiniciar a API não duplica.

**O limite, dito sem enfeite:** o JARVIS não tem serviço em segundo plano. Se a
janela estiver fechada, ninguém avisa. Para aviso com o JARVIS fechado seria
preciso um serviço do Windows rodando — não é o que existe aqui.

### No chat

```text
marca audiência amanhã às 14h            → agenda.marcar (pede confirmação)
marca audiência amanhã às 14h, avisa 2h antes  → agenda.marcar (avisar_antes=120)
o que está vencendo agora                → agenda.lembretes (só lê)
marca na agenda reunião quinta às 10h    → agenda.marcar
o que eu tenho para hoje                 → agenda.listar (dias=1)
minha agenda da semana                   → agenda.listar (dias=7)
quais são meus compromissos              → agenda.listar (tudo em aberto)
conclui o compromisso audiência          → agenda.concluir
```

### Limites, ditos sem rodeio

- **não toca o calendário do Windows nem o Google Agenda** — é uma lista própria;
- **não avisa sozinho**: ele não tem serviço em segundo plano mandando
  notificação. Você pergunta, ele responde. (Um lembrete de verdade exigiria um
  processo sempre ligado — está fora do escopo desta camada.)
- **não entende data relativa vaga**: “semana que vem”, “mês que vem”, “depois do
  dia 10” não são reconhecidas; use uma das formas da lista.

---

## 2. Backup — `backup.*`

O medo que abriu esta camada: *“e se eu perder tudo?”*. O JARVIS guarda
documentos, livros, catálogo, agenda e memória em `storage/`. O backup empacota
isso num `.zip` com data no nome, grava o **SHA-256** ao lado e **abre o arquivo
logo depois de escrever** — backup que não abre não é backup.

| Skill | O que faz | Efeito |
|---|---|---|
| `backup.planejar` | diz o que entraria, quanto pesa, o que ignorou e se cabe | só lê |
| `backup.criar` | cria o `.zip`, o `.sha256` e o manifesto `.json` | grava |
| `backup.listar` | mostra os backups já feitos, com data e tamanho | só lê |
| `backup.restaurar` | extrai numa pasta **nova e vazia** | grava |

### O que entra

Tudo em `storage/`, com quatro exclusões de propósito:

- `repos/` (os repositórios baixados) — só entra com `incluir_repos=True`,
  porque costuma ser a maior parte;
- `.venv`, `node_modules`, `__pycache__`, `.git`, `.pytest_cache` — não são
  dados seus, e só engordam o arquivo;
- a própria pasta de backups — senão cada backup carregaria os anteriores;
- arquivos acima de 512 MB e links simbólicos.

### O aviso que importa

Se o destino estiver **no mesmo disco** dos dados, o resultado diz na cara:

> O destino está no mesmo disco dos dados: protege contra apagar sem querer, não
> contra o disco morrer. Um pendrive ou o Drive resolve.

Backup no mesmo HD não é backup — é desfazer. Por isso `destino` aceita
caminho absoluto: `E:/JARVIS-backups` (pendrive) ou
`G:/Meu Drive/JARVIS-backups` (Drive).

### Restaurar

Só em pasta **vazia**. Restaurar por cima do que está em uso é como apagar o
original no meio do caminho. Antes de extrair, ele confere se algum caminho
dentro do `.zip` escapa da pasta de destino — o zip-slip clássico.

```text
faz backup dos meus dados em E:/JARVIS-backups
→ Criei jarvis-dados-20261026-141233.zip — 1.842 arquivo(s), 96,4 MB, sha256 3f9a…

quanto vai pesar o backup              → backup.planejar (sem copiar nada)
quais backups eu tenho                 → backup.listar
restaura o backup jarvis-dados-20261026-141233.zip para D:/restaurado
```

### Limites

- **não agenda backup automático** — quem dispara é você (ou o Agendador de
  Tarefas do Windows chamando `curl` na API; não está montado);
- **não apaga backup antigo** — rotatividade é decisão sua;
- **não criptografa** o `.zip`. Se for levar num pendrive que circula, o `.zip`
  abre com dois cliques em qualquer máquina;
- o teto padrão é 2 GB (ajustável em `teto_mb`), para não encher o disco por
  acidente.

---

## 3. Git — `git.*` (só leitura)

A pergunta era “dá para ele usar o Git?”. Dá — **lendo**. As quatro skills rodam
com argumentos fixos, sem shell e sem campo para texto livre:

| Skill | Comando | Para quê |
|---|---|---|
| `git.status` | `git status --porcelain=v1 -b` | branch, à frente/atrás, o que mudou |
| `git.log` | `git log -n N --pretty=…` | últimos commits com hash, data e autor |
| `git.diff` | `git diff` / `git diff --staged` | resumo por arquivo e o patch |
| `git.remoto` | `git remote -v` + upstream | de onde vem e para onde vai |

### O que ele **não** aceita

`commit`, `push`, `pull`, `clone`, `checkout`, `reset`, `clean`, `merge`,
`rebase` — nem como texto livre, nem por parâmetro. Não existe campo para
argumento: você escolhe a consulta, não a linha de comando.

Isso é de propósito. Um agente que faz `push` com um erro de digitação estraga
histórico; um que só lê não estraga nada. Se um dia o push fizer falta, ele entra
como skill própria, com plano, token e confirmação — do mesmo jeito que o
instalador.

### Onde ele aceita olhar

Só dentro de três lugares conhecidos:

1. a pasta do projeto (`D:\JARVIS`);
2. a raiz de dados (`storage/` ou `JARVIS_DADOS`);
3. `storage/repos/…` (os repositórios baixados).

Fora disso recusa. Um “leitor de Git” que aceita qualquer pasta da máquina é um
mapeador de disco com outro nome.

### Rodando

```text
como está o git                     → branch, à frente/atrás e arquivos
o que mudou no git                  → git.status
últimos commits do git              → git.log (10)
mostra o diff do git                → git.diff
qual o remoto do git                → git.remoto
```

Rodando com `shell=False`, `GIT_TERMINAL_PROMPT=0` (nunca pede senha), sem
paginador e com teto de 20 segundos por comando.

---

## 4. O que foi medido

| Verificação | Resultado |
|---|---|
| Testes da agenda | **32** (`test_agenda.py`: datas relativas, ISO, numérica, dia da semana, recusa, atraso, janela) |
| Testes do backup | **9** (`test_backup.py`: zip real, manifesto, hash, teto, restauração, zip-slip, pasta ocupada) |
| Testes do Git | **10** (`test_git.py`: repositório de verdade criado no teste, status, log, diff, remoto, recusa) |
| Skills novas | **13** (5 de agenda, incluindo `agenda.lembretes`, 4 de backup, 4 de Git) |
| Suíte total | **2.563** testes |

O Git é testado com um repositório criado na hora, dentro de `tmp_path` — nenhum
teste toca no repositório do projeto. O backup é testado com arquivos de
verdade, e o zip é aberto de novo para conferir o manifesto.

## 5. O que não foi medido

- **agenda no fuso do Windows**: o `datetime.now()` pega o fuso da máquina; não
  há teste com fuso trocado (o sandbox é UTC).
- **backup de 2 GB**: o teste usa poucos bytes; o caminho do arquivo grande
  (streaming, tempo, disco cheio no meio) não foi exercitado.
- **Git com repositório enorme**: o diff é cortado em 20 000 caracteres, mas não
  há teste com histórico de milhares de commits.
