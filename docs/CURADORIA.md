# Curadoria de listas

Validar entrada, agrupar catálogo, derivar README, comparar estrelas e auditar higiene. A adaptação parte de [`hesreallyhim/awesome-claude-code`](https://github.com/hesreallyhim/awesome-claude-code) — **CC BY-NC-ND 4.0** —, mas o que entra aqui é só o **mecanismo**: nenhum recurso do catálogo curado, nenhuma descrição e nenhuma categoria do upstream foram copiados ou adaptados. A lista é sua; as regras são o que este módulo implementa.

| Camada | O que faz | Toca a rede? |
|---|---|---|
| **Motor** (`server/curadoria.py`, 6 skills) | Valida a entrada contra as regras, agrupa o CSV, gera o README, compara snapshots de estrelas e audita a higiene | **Não** — tudo é texto que você cola |
| **Página** (`/curadoria`) | Formulário por verbo, métricas, achados e o artefato pronto para copiar | Não |

O módulo reaproveita `server/review.py`: mesmos grupos (`must`, `should`, `nice`), mesmas contagens, veredito e Markdown. O resultado é determinístico — mesma entrada, mesmo parecer — e nenhuma skill grava arquivo.

---

## O schema

Doze colunas, uma linha por recurso. O cabeçalho é normalizado antes da leitura, então o inglês do schema original também funciona.

| Coluna | Conteúdo | Regra |
|---|---|---|
| `id` | 8 dígitos hexadecimais minúsculos | Único, opaco, nunca sequencial |
| `nome` | Como o recurso aparece na lista | 2–80 caracteres |
| `categoria` | Uma das declaradas na configuração | Obrigatória |
| `subcategoria` | Declarada **sob** a categoria | Opcional |
| `link` | URL canônica | `https://`, sem espaço nem metacaractere |
| `autor` | Crédito | Obrigatório |
| `link_autor` | URL do crédito | `https://` |
| `ativo` | `TRUE` / `FALSE` | Ausente conta como ativo |
| `adicionado_em` | `AAAA-MM-DD` | Formato único |
| `checado_em` | `AAAA-MM-DD` | Vazio = nunca checado |
| `descricao` | Uma linha sobre o que o software faz | 10–500 caracteres |
| `estagnado` | `TRUE` quando a última checagem encontrou o projeto parado | Só com data que justifique |

Cabeçalho em inglês: `ID`, `Display Name`, `Category`, `Sub-Category`, `Link`, `Author Name`, `Author Link`, `Active`, `Date Added`, `Last Checked`, `Description`, `Stale`. Coluna a mais não quebra a leitura: vira achado `coluna-ignorada`. Coluna obrigatória faltando quebra, e a mensagem diz qual.

### Categorias

A ordem do README é a ordem da configuração, não a do CSV. O exemplo embutido tem nove categorias — Comece aqui, Skills e comandos, Memória e contexto, Observabilidade, Segurança e permissões, Design e interface, Infraestrutura e entrega, Qualidade e revisão, Coleções — e quatro subcategorias (Revisão de código, Testes, Custo e uso, Sessões). `Coleções` é `submetivel: false`: a seção existe na leitura e recusa entrada nova.

A configuração é um JSON opcional em todas as skills:

```json
{ "categorias": [
  { "nome": "Ferramentas", "descricao": "O que já roda no terminal.", "subcategorias": [{"nome": "CLI"}] },
  { "nome": "Arquivo", "submetivel": false }
] }
```

Categoria repetida, item sem `nome` ou subcategoria malformada são erro de entrada, não achado.

---

## Entrada

`curadoria.entrada` responde uma pergunta só: **este recurso pode entrar na lista hoje?**

### Elegibilidade

Aceita-se **(a)** 14 dias desde o primeiro commit com desenvolvimento depois dele, **ou** **(b)** 100 estrelas.

| Situação | Achado | Veredito |
|---|---|---|
| 40 dias e 12 commits depois | nenhum | elegível pelo caminho `idade` |
| 10 dias e 9 commits | `inelegivel` (must) | recusado até amadurecer |
| 20 dias e 0 commit depois do primeiro | `sem-atividade` (must) | recusado — a idade sozinha não basta |
| 3 dias e 100 estrelas | nenhum | elegível pelo caminho `estrelas` |
| 40 dias, 12 commits e 100 estrelas | `elegivel-duplo` (nice) | elegível pelos dois caminhos |

Os números são **declarados por você**: nenhuma API de repositório é chamada. Isso é limite, não bug — está escrito no parecer.

### Estilo da descrição

A descrição diz o que o software faz, no presente, em uma linha, sem falar com o leitor.

| Marca | Exemplo |
|---|---|
| `descricao-emoji` | qualquer emoji |
| `descricao-exclamacao` | `!` na frase |
| `descricao-segunda-pessoa` | “você”, “seu”, “you” |
| `descricao-pitch` | “o melhor”, “revolucionário”, “imperdível”, “10x” |
| `descricao-chamada` | “clique aqui”, “saiba mais” |
| `descricao-multilinha` | quebra de linha no campo |
| `descricao-curta` / `descricao-longa` | menos de 10 ou mais de 500 caracteres |
| `descricao-caixa-alta` | texto inteiro em maiúsculas |

### Outras barreiras

- `url-invalida` — começa com `http://`, tem espaço, aspas ou metacaractere de Markdown/HTML.
- `um-por-vez` — mais de um link na mesma recomendação.
- `categoria-fechada` — a categoria existe, mas não aceita submissão.
- `subcategoria-orfa` — a subcategoria não está declarada sob a categoria escolhida.
- `licenca-ausente` / `licenca-fechada` — a licença não é identificável, ou o projeto é fechado.
- `acesso-bloqueado` — cadastro ou pagamento obrigatório.
- `duplicata-link` / `duplicata-nome` — comparação normalizada contra a lista que você colar em `existentes` (`link|nome` por linha).

### Saída

A entrada limpa devolve a **linha pronta**, com ID opaco, datas de inclusão e checagem, e a tabela dos 12 campos:

```csv
2d711642,JARVIS OS,Skills e comandos,Revisão de código,https://github.com/exemplo/jarvis,Ana Lima,https://github.com/analima,TRUE,2026-10-23,2026-10-23,Orquestra skills locais com revisão estática.,FALSE
```

Sem `semente`, o ID é aleatório (`secrets.token_hex(4)`); com semente, é determinístico e serve para teste.

---

## Catálogo

`curadoria.catalogo` lê o CSV inteiro e devolve a árvore na ordem editorial.

| Achado | Quando |
|---|---|
| `categoria-desconhecida` (must) | A linha aponta para categoria fora da configuração |
| `subcategoria-orfa` (should) | A subcategoria não existe sob aquela categoria |
| `categoria-vazia` (nice) | A categoria está declarada e não tem nenhum recurso |
| `estagnados` (should) | Há linha com `estagnado = TRUE` |
| `nunca-checados` (should) | Há linha sem `checado_em` |
| `coluna-ignorada` (nice) | O CSV trouxe coluna fora do schema |

Categoria desconhecida **não é descartada**: as linhas aparecem no fim, marcadas `desconhecida: true`, e o sumário não as esconde. Dentro de cada seção, a ordem é alfabética sem acento (`Fluxo` antes de `Ferramenta`, `Árvore` no lugar de `A`).

---

## README

`curadoria.readme` deriva o README do CSV. O arquivo não é editado à mão: categoria nova, recurso novo e remoção entram pela base.

```markdown
# Recursos escolhidos

**3 recursos** em 9 categorias · 3 ativos · atualizado em 2026-10-23

## Sumário

- [Skills e comandos](#skills-e-comandos)
  - [Skills e comandos › Revisão de código](#skills-e-comandos-revisao-de-codigo)
- [Memória e contexto](#memoria-e-contexto)
```

- Âncora no padrão do GitHub: minúsculas, sem acento, hífen no lugar de espaço; título repetido ganha sufixo numérico (`-1`).
- Seção vazia não aparece no README, mas continua no sumário de `curadoria.catalogo` para você decidir se preenche ou remove.
- Colchete e barra vertical no nome são escapados (`\[`, `\|`) para não quebrar o link nem a tabela.
- Seções sem recurso geram `secao-vazia` (nice): um README com cabeçalho oco parece abandonado.
- Título até 90 caracteres; introdução opcional de até 2 000 caracteres.

---

## Ticker

`curadoria.ticker` compara dois snapshots `dono/repo,estrelas` e ordena por variação.

| Métrica | O que conta |
|---|---|
| `comum` | Repositórios nos dois arquivos |
| `novos` / `sairam` | Entraram ou desapareceram entre os snapshots |
| `subiram` | Variação positiva |
| `excluidos` | Filtrados pelas proteções |
| `delta_total` | Soma das variações |

Saída por repositório: `antes`, `depois`, `delta`, `percentual` e `estado` (`novo`, `saiu`, `subiu`, `caiu`, `estável`). O ranking mostra os cinco maiores movimentos em Markdown e até 80 linhas na tabela.

### Proteções

Antes de rankear, o ticker remove nomes que existem para desviar quem procura o projeto real:

| Proteção | Padrão |
|---|---|
| `donos_banidos` | vazio |
| `nomes_exatos` | `claude-code`, `claudecode`, `claude_code`, `claude.code` |
| `nomes_contem` | `source-code`, `sourcecode`, `source-map`, `sourcemap` |
| `nomes_completos` | vazio |

É heurística de nome e dono: não prova má-fé nem lê o conteúdo do repositório. Repositório renomeado aparece como um que saiu e outro que nasceu — a comparação é por nome completo. Snapshot vazio, linha sem `dono/repo` e estrela não numérica são erro de entrada.

---

## Higiene

`curadoria.higiene` audita a base inteira em dez checagens.

1. ID presente, único e no formato de 8 dígitos hexadecimais
2. Link `https` válido, sem espaço nem metacaractere
3. Link e nome sem duplicata no catálogo
4. Link do autor válido quando declarado
5. Categoria declarada na configuração
6. Subcategoria declarada sob a categoria
7. Data de inclusão no formato `AAAA-MM-DD`
8. Data de checagem presente e recente (`dias_para_checar`, padrão 90)
9. Descrição em uma linha, sem emoji, pitch ou segunda pessoa
10. Estagnação acompanhada da checagem que a justifica

`checagem-antiga` é lembrete, não prova de abandono. O estilo é lexical: um texto honesto pode esbarrar numa palavra da lista de pitch — por isso o achado diz qual palavra casou.

---

## Skills

| Skill | Categoria | Tempo | Entrada principal |
|---|---|---|---|
| `curadoria.entrada` | Curadoria | 10 s | nome, link, autor, link do autor, categoria, descrição, licença, dias, commits, estrelas, cadastro, pagamento |
| `curadoria.catalogo` | Curadoria | 10 s | CSV, configuração opcional, data de referência |
| `curadoria.readme` | Curadoria | 10 s | CSV, título, introdução, configuração opcional |
| `curadoria.ticker` | Curadoria | 10 s | dois snapshots, proteções opcionais |
| `curadoria.higiene` | Curadoria | 15 s | CSV, janela de checagem |
| `curadoria.regras` | Curadoria | 5 s | — |

Todas aceitam `modo` (`lite` filtra só `must`, `full` é o padrão, `ultra` acrescenta perguntas). Entrada inválida responde `ok: false` com `SKILL_ERROR` e a mensagem que diz o que corrigir; parâmetro desconhecido é recusado pelo Pydantic (`extra="forbid"`).

```bash
curl -s http://localhost:8000/api/skills/curadoria.entrada/execute \
  -H 'content-type: application/json' \
  -d '{"parameters": {
        "nome": "JARVIS OS",
        "link": "https://github.com/exemplo/jarvis",
        "autor": "Ana Lima",
        "link_autor": "https://github.com/analima",
        "categoria": "Skills e comandos",
        "descricao": "Orquestra skills locais com revisão estática.",
        "licenca": "MIT",
        "dias_desde_o_primeiro_commit": 40,
        "commits_depois_do_primeiro_dia": 12
      }}'
```

```json
{
  "ok": true,
  "result": {
    "id": "2d711642",
    "linha": "2d711642,JARVIS OS,Skills e comandos,,https://github.com/exemplo/jarvis,...",
    "elegivel": true,
    "metrics": {"dias": 40, "commits": 12, "regra": "idade"},
    "executed": false,
    "readOnly": true
  }
}
```

---

## O que não é feito

- **Nada de rede.** Elegibilidade, licença, categoria, atividade e data são o que o CSV e o formulário declaram. Não há descoberta de licença via API, checagem de link nem consulta de estrelas.
- **Nada é escrito.** O módulo não cria arquivo, não move linha e não grava README. A saída é texto para você colar no seu repositório.
- **Nada do catálogo do upstream.** A lista de 263 recursos, as categorias e as descrições de lá não estão no repositório: a licença **CC BY-NC-ND 4.0** proíbe derivados e uso comercial. Veja [`docs/licenses/hesreallyhim-awesome-claude-code.txt`](licenses/hesreallyhim-awesome-claude-code.txt).
- **Não há julgamento de valor.** O parecer descreve o que a regra mede e o que acontece se você ignorar. Quem decide se a lista aceita o recurso é você.

---

## Testes

`server/tests/test_curadoria.py` cobre elegibilidade pelos dois caminhos, recusa por idade sem atividade, link que quebra Markdown, categoria desconhecida/fechada/órfã, estilo da descrição, duplicata, ID determinístico, modo `lite`, leitura com cabeçalho em inglês, coluna faltando e coluna a mais, configuração inválida, âncoras e escape do README, âncora repetida, movimentos e proteções do ticker, snapshots inválidos, higiene com ID/link/data repetidos e checagem antiga, e as seis skills pela API.

```bash
.venv/bin/python -m pytest server/tests/test_curadoria.py -o addopts="" -q   # 39 testes
```
