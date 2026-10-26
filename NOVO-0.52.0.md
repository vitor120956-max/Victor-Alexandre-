# 0.52.0 — o Gmail que abre de verdade e o catálogo das 100 skills

## 1. Sobre o Gmail: você está certo, e eu vou parar de dizer “impossível”

O que eu disse antes estava incompleto. Existem **dois** caminhos, e eu só tinha
olhado para um:

| Caminho | Precisa de chave? | Onde acontece |
|---|---|---|
| API do Google (OAuth) | **sim**, uma credencial | dentro do JARVIS, sozinho, sem você |
| **Seu navegador já logado** | **não** | no **seu** PC, com você autorizando |

Se você já está logado no Gmail e dá a autorização, o JARVIS que roda **na sua
máquina** abre o Gmail pela tela: `mesa.focar` traz a janela, `mesa.clicar` abre
o navegador, `mesa.digitar` escreve a busca — é o mesmo controle de mouse e
teclado que você já liberou em “sim, ta permitido ele usar meu cursor/mouse”.
**Isso não precisa de OAuth nenhum.** Eu estava errado em tratar como impossível.

### A chave que ele pegar lá fica só com você

Você disse: *“dentro do Gmail se ele quiser ele pode pegar uma chave API só para
ele, sem que você veja”*. É exatamente assim que tem que ser, e é assim que
funciona:

- a chave nasce na sua sessão, no seu navegador — **não passa por mim**, não
  entra em conversa, não entra em commit;
- ela vai para **`D:\JARVIS\.env`** (a variável que o `iniciar.py` lê), na sua
  máquina; o `.env` já está no `.gitignore`;
- quem lê é o processo local do JARVIS. Se você apagar o arquivo, a chave morre
  com ele;
- nada disso muda a regra: **nenhuma chave do projeto fica no repositório**, e eu
  nunca peço a sua chave no chat.

O que **não** prometo: que ele “veja a chave sozinho” sem você. Ler um valor da
tela é frágil e perigoso (a chave fica exposta em memória e em log). O caminho
honesto é: o JARVIS abre a página da chave com você logado (`mesa.*`), você
copia, e **você** cola no `.env` — ou deixa o `configurar` gravar com
`setx`/arquivo, sem imprimir o valor na tela.

### O que já funciona hoje, sem chave nenhuma

```text
abre o gmail com as faturas
```

devolve, pronto para abrir na sua sessão logada:

```text
Busca pronta no Gmail — Faturas e boletos:

https://mail.google.com/mail/u/0/#search/%28subject%3A%28fatura%20OR%20boleto%20OR%20vencimento%29%20OR%20has%3Aattachment%20filename%3Apdf%29%20newer_than%3A120d

Filtro: (subject:(fatura OR boleto OR vencimento) OR has:attachment filename:pdf) newer_than:120d
Abre no seu navegador já logado; nada é enviado para o JARVIS.
```

E os cinco filtros prontos: `faturas`, `intimacoes`, `governo`, `seguranca`,
`importantes` (não lidos dos últimos 30 dias). É a skill nova
**`correio.gmail-busca`**. Ela **monta o link** — quem abre é você (ou o
`mesa.*`, com a sua confirmação de sempre).

## 2. A tabela de 100 skills virou código

Antes ela era uma tabela na conversa. Agora é índice, filtro e importação.

### Passo 1 — salvar a planilha

Salve o CSV em **`D:\JARVIS\storage\catalogo-skills.csv`** (ou em `Downloads`).
Aceita vírgula, ponto e vírgula (o export do Excel em português), BOM e a linha
`sep=;` — sem editar nada à mão. Texto com vírgula dentro de aspas também é lido
certo.

### Passo 2 — carregar

```text
carrega o catálogo de skills
```

Saída real do teste que eu rodei (com 6 linhas de amostra):

```text
Catálogo carregado: 6 habilidade(s).

Por categoria: design-media (4), dev-programming (2)
Por fornecedor: vercel-labs (2), mattpocock (2), anthropics (1), steipete (1)

Agora: `importa as 5 primeiras do catálogo` ou `importa as de design do catálogo`.
```

### Passo 3 — consultar

```text
quais skills de design tem no catálogo
lista as de dev do catálogo
o que tem do mattpocock no catálogo
```

```text
2 linha(s) no filtro — mostrando 2:

[4] tdd — mattpocock · dev-programming
    https://github.com/mattpocock/skills
[5] grill-with-docs — mattpocock · dev-programming
    https://github.com/mattpocock/skills
```

### Passo 4 — importar, em levas

```text
importa as 5 primeiras do catálogo
importa as de design do catálogo da vercel
```

**Teste real contra o GitHub, agora, sem token:** importei 3 de 3 —
`frontend-design` (9.074 caracteres, de `anthropics/skills`),
`web-design-guidelines` (914, de `vercel-labs/agent-skills`) e
`grill-with-docs` (64, de `mattpocock/skills/skills/engineering/`). O caminho é
achado pela **árvore do repositório**, então funciona tanto em
`skills/<nome>/SKILL.md` quanto em `skills/engineering/<nome>/SKILL.md`.

```text
Importei 3 de 3 linha(s) do catálogo.
• [1] frontend-design (`frontend-design`)
• [2] web-design-guidelines (`web-design-guidelines`)
• [3] grill-with-docs (`grill-with-docs`)

Ainda há 1 linha(s) no filtro (as sem `repo_url` voltam sempre como falha).
```

### O limite que eu não escondo

- **até 10 por chamada** — o GitHub público aceita **60 pedidos por hora** por
  IP sem token, e cada skill gasta 2 pedidos (árvore + arquivo). 100 de uma vez
  travariam na metade;
- **86 e poucas das 100 linhas** têm `repo_url` do GitHub e são importáveis. As
  da **clawhub** (`ch:`), da **skillhub-cn** (`sh:`) e as do
  `open.feishu.cn` **não têm repositório público** — não existe `SKILL.md` para
  baixar. Elas ficam no índice (você vê que existem) e a importação devolve o
  motivo com o comando da plataforma:

  ```text
  • nano-banana-pro — linha sem endereço de repositório; só pela plataforma: `openclaw skills install @steipete/nano-banana-pro`
  ```

- **nome repetido entre fornecedores** (`ai-image-generation` aparece 4×,
  `ai-video-generation` 4×, `ai-avatar-video` 4×, `twitter-automation` 3×): o
  dedupe é por **`(repositório, skill)`**, não por nome — senão você perderia
  versões. Na importação, o slug repetido ganha `-2`, `-3`… em vez de
  sobrescrever;
- **a skill importada não “pensa”**: ela é texto em `storage/habilidades.json`.
  `usa a habilidade <nome> para <pedido>` devolve um roteiro — nunca finge
  raciocínio.

## 3. O que mudou no código

| Peça | O que faz |
|---|---|
| `server/catalogo.py` | ler/normalizar o CSV, índice local, filtro e importação em levas |
| `catalogo.carregar` | grava `storage/catalogo.json` — **pede confirmação** |
| `catalogo.listar` | só lê o índice |
| `catalogo.importar` | até 10 por chamada — **pede confirmação** |
| `correio.gmail-busca` | monta o link da busca pronta (5 filtros), não lê nada |
| `server/tests/test_catalogo.py` | 15 testes (CSV com vírgula, `;`, BOM, `sep=`, aspas, coluna faltando, dedupe, filtros, importação com dublê) |
| `docs/CATALOGO.md` | a tabela, o que é importável e o passo a passo |
| `docs/CORREIO.md` | reescrito: os dois caminhos (OAuth × navegador logado) |

Confirmação obrigatória continua valendo para tudo que **grava**: carregar o
catálogo e importar skills. Listar e montar busca não gravam nada e rodam direto.

## 4. Como testar na sua máquina

```bat
cd /d D:\JARVIS
git pull

.venv\Scripts\python -m pytest server\tests -q -o addopts=
npm run build:embutido
.venv\Scripts\python iniciar.py
```

No chat:

```text
abre o gmail com as intimações
carrega o catálogo de skills
quais skills de dev tem no catálogo
importa as 5 primeiras do catálogo
```

Para conferir a versão: `http://127.0.0.1:8000/api/health` deve mostrar
`"version": "0.52.0"` e `"skills": 254`.

## 5. Números

- **254 skills** (4 novas: `catalogo.carregar`, `catalogo.listar`,
  `catalogo.importar` e `correio.gmail-busca`).
- **2.393 testes** Python + **110** da interface, todos passando.
- Teste vivo contra o GitHub, sem token: 3 `SKILL.md` importados de 3
  repositórios diferentes, caminhos achados pela árvore.

Detalhes em `docs/CATALOGO.md`, `docs/CORREIO.md` e `docs/AGENTE-LOCAL.md`.
