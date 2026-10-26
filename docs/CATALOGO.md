# Catálogo — as 100 habilidades de fora, linha por linha

A tabela que você colou tem **100 linhas** e dez colunas:

| coluna | serve para |
|---|---|
| `rank` | a ordem em que você quer tentar; é por ela que o catálogo ordena |
| `skill` | o nome da pasta dentro do repositório (é a chave do casamento) |
| `skill_key` | o identificador da vitrine (`ss:anthropics/frontend-design`, `ch:…`) |
| `platform` | de onde veio: skills.sh, clawhub, skillhub-cn |
| `vendor` | quem publicou |
| `repo_url` | o repositório do GitHub — **só as linhas com isto são importáveis** |
| `url` | a página de vitrine |
| `install` | o comando que a plataforma sugere |
| `description` | o que a habilidade faz |
| `category` | `design-media`, `dev-programming`, `ai-agent`, `office-knowledge`, … |

Ela vira três coisas aqui: um **índice local** (`storage/catalogo.json`), um
**filtro** e uma **importação em levas**.

## O que dá para fazer hoje

| Você pede no chat | Ele faz |
|---|---|
| `carrega o catálogo de skills` | lê `storage/catalogo-skills.csv`, normaliza, tira duplicata e guarda o índice |
| `lista o catálogo` | mostra as primeiras linhas do índice |
| `quais skills de design tem no catálogo` | filtra por categoria, fornecedor, palavra ou faixa de rank |
| `importa as 5 primeiras do catálogo` | traz o `SKILL.md` de cada uma e guarda em `storage/habilidades.json` |
| `importa as de design do catálogo da vercel` | mesma coisa, com filtro antes |

Equivalente por API:

```bash
curl -s -X POST http://localhost:8000/api/skills/catalogo.carregar/run \
  -H "Content-Type: application/json" \
  -d '{"caminho": "catalogo-skills.csv"}'

curl -s -X POST http://localhost:8000/api/skills/catalogo.listar/run \
  -H "Content-Type: application/json" \
  -d '{"categoria": "design", "limite": 20}'

curl -s -X POST http://localhost:8000/api/skills/catalogo.importar/run \
  -H "Content-Type: application/json" \
  -d '{"quantos": 5, "fornecedor": "vercel-labs"}'
```

## Onde pôr o CSV

Salve a planilha como **CSV** em um destes dois lugares (é o mesmo confinamento de
`files.import`; qualquer outro caminho é recusado):

- `D:\JARVIS\storage\catalogo-skills.csv` — o nome que o chat usa por padrão;
- `C:\Users\<você>\Downloads\catalogo-skills.csv`.

O arquivo pode vir com **vírgula**, **ponto e vírgula** (o Excel em português
exporta assim), com **BOM** (`\ufeff`) ou com a linha `sep=;`. Tudo isso é
detectado — não precisa editar nada à mão. Texto com vírgula dentro de aspas
(`"Design de front-end, com vírgula"`) também é lido certo.

Só duas colunas são obrigatórias: **`skill`** e uma das duas de endereço
(**`repo_url`** ou **`url`**). Faltando alguma, ele recusa a planilha inteira e
diz qual coluna ficou de fora, em vez de importar metade.

## O que é importável, e o que não é

A sua tabela mistura três fontes:

- **`ss:` (skills.sh)** — quase todas apontam para um repositório do GitHub
  (`anthropics/skills`, `vercel-labs/agent-skills`, `mattpocock/skills`,
  `prisma/skills`, `neondatabase/…`, `supabase/…`, `cloudflare/skills`,
  `remotion-dev/skills`, `heygen-com/hyperframes`, `101-skills/superpowers`…).
  São as que o catálogo importa.
- **`ch:` (clawhub)** — não têm `repo_url`; o conteúdo mora no site da
  plataforma, atrás do comando `openclaw skills install @vendor/nome`. O catálogo
  **não** roda esse comando (não instala nada sem você autorizar) e a linha volta
  em `falhas` com `linha sem endereço de repositório`.
- **`sh:` (skillhub-cn) e `open.feishu.cn`** — mesma coisa: página de vitrine, sem
  repositório público para puxar o `SKILL.md`.

Ou seja: das 100 linhas, **cerca de 86 são importáveis** hoje; o resto fica no
índice (para você ver o que existe) mas só pode ser instalado pela plataforma de
origem.

Um detalhe que a tabela esconde: **o mesmo nome aparece em fornecedores
diferentes** (`ai-image-generation` quatro vezes, `ai-video-generation` quatro,
`ai-avatar-video` quatro, `twitter-automation` três). O dedupe é por
**`(repositório, skill)`** — não por nome —, senão você perderia versões. Na
hora de importar, a segunda skill com o mesmo slug ganha `-2`, `-3`… em vez de
sobrescrever a primeira.

## Como ele acha o arquivo dentro do repositório

`repo_url` aponta para o repositório, não para o `SKILL.md`. O caminho varia:

- `anthropics/skills` → `skills/frontend-design/SKILL.md`
- `vercel-labs/agent-skills` → `skills/web-design-guidelines/SKILL.md`
- `mattpocock/skills` → `skills/engineering/tdd/SKILL.md`

Então o catálogo consulta a árvore do repositório (`github.arvore`, a mesma API
pública de `github.repo`) e casa o **último segmento da pasta** com o nome da
skill. Se a pasta não existir, a linha falha com o motivo
(`não achei a pasta \`X\` em dono/repo`) — e **não** baixa o repositório inteiro
por engano. Se a árvore não responder (limite do GitHub), ele tenta o repositório
como último recurso, que é o comportamento antigo do `habilidades.importar`.

## Os limites, sem rodeio

1. **60 pedidos por hora.** É o teto da API pública do GitHub por IP, sem token.
   Cada importação gasta **um** pedido para a árvore e **um** para o arquivo.
   Por isso `catalogo.importar` aceita **no máximo 10 por chamada**, e devolve
   quantas ficaram para a próxima (`restantes`).
2. **Não instala nada.** Importar = baixar o texto do `SKILL.md` e guardar em
   `storage/habilidades.json`. Não roda `npx skills add`, não roda
   `openclaw skills install`, não cria comando no sistema.
3. **Não pede token.** Nenhuma chave, nenhum login. Se um dia o limite de 60/h
   incomodar, um token do GitHub é opcional — e ficaria no `.env` da **sua**
   máquina, não no código.
4. **A skill importada não vira ferramenta.** Ela é texto: o `habilidades.aplicar`
   devolve um roteiro para você seguir — nunca promete que a habilidade “pensa”.
5. **Gravar pede confirmação.** `catalogo.carregar` e `catalogo.importar` têm
   efeito colateral e exigem confirmação explícita; `catalogo.listar` não.

## Onde ficam os arquivos

| Peça | Caminho |
|---|---|
| leitura, filtro e importação | `server/catalogo.py` |
| o CSV que você salva | `storage/catalogo-skills.csv` (ou `Downloads`) |
| o índice normalizado | `storage/catalogo.json` (ou `JARVIS_DADOS/catalogo.json`) |
| as habilidades importadas | `storage/habilidades.json` (mesmo arquivo de `habilidades.*`) |
| skills | `catalogo.carregar`, `catalogo.listar`, `catalogo.importar` |
| testes | `server/tests/test_catalogo.py` (15, com CSV montado no teste e download dublê) |

Os testes **nunca** abrem socket: o download e a árvore são substituídos por
dublês. O que é testado de verdade é o parsing (vírgula, ponto e vírgula, BOM,
`sep=`, aspas, coluna faltando), o dedupe, o filtro por categoria/fornecedor/
rank e a importação em que uma linha ruim não derruba as outras.

## Receita para começar

1. Salve a tabela como `D:\JARVIS\storage\catalogo-skills.csv`.
2. No chat: `carrega o catálogo de skills`.
3. Veja o resumo: quantas linhas, quantas por categoria e por fornecedor.
4. `quais skills de design tem no catálogo` → escolha o que interessa.
5. `importa as 5 primeiras do catálogo` → repita até acabar, ou filtre antes
   (`importa as de dev do catálogo`). Cada leva respeita o teto de 10.
6. Para usar uma importada: `usa a habilidade <nome> para <pedido>`.
