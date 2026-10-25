# Portabilidade de skills

Uma skill que só funciona na ferramenta onde nasceu não é ativo, é dívida. Quem publica o mesmo procedimento para Claude Code, Codex, Cursor e Aider descobre três problemas na primeira semana: o formato do front matter muda, o caminho de instalação muda e o que acompanha a skill muda — regra em arquivo único não carrega `scripts/`, espelho gerado não admite edição à mão, `plugin.json` com uma chave a mais derruba a instalação inteira. A camada de portabilidade responde essas perguntas com o plano aberto: **o que cada alvo aceita**, **o que a conversão copia, reescreve, embute ou descarta**, **o que divergiu do espelho**, **onde duas skills colidem** e **como o lote vira plugin de marketplace**.

O insumo é o [`alirezarezvani/claude-skills`](https://github.com/alirezarezvani/claude-skills) — **MIT**, 28.656 estrelas, 3.980 forks, Python. Ele publica centenas de skills para 13 ferramentas e mantém scripts de conversão (`convert.sh`), instalação (`install.sh`), espelho (`sync-*-skills.py`) e verificação (`check_dual_publish.py`, `check_plugin_json.py`). Daqui não veio código do upstream: veio o desenho — a anatomia da skill, a matriz de ferramentas, os três estilos de empacotamento, o padrão de dual publish e o schema de oito chaves — reimplementado com fixtures próprias.

| Camada | O que faz | Toca a rede? |
|---|---|---|
| **Motor** (`server/portabilidade.py`, 7 skills) | Audita o bundle, converte para um alvo, mede deriva, acha colisão, monta o lote e cruza a matriz | **Não** — só o que foi colado |
| **Página** (`/portabilidade`) | Aba por operação, amostra com skill completa, skill sem apoio e espelho com deriva | Não |

Nada é escrito, copiado ou instalado: nenhum `git clone`, nenhuma chamada a `convert.sh`, nenhum arquivo no disco. Toda resposta marca `executed: false` e `readOnly: true`. O plano de conversão é o produto.

## As sete skills

| Rota | Entrada | O que devolve |
|---|---|---|
| `portabilidade.auditar` | bundle, alvo, modo | achado por skill: front matter, nome e slug, descrição, script não citado, `allowed-tools`, licença, tamanho, arquivo solto |
| `portabilidade.converter` | bundle, alvo | plano arquivo a arquivo com origem, destino, ação e bytes |
| `portabilidade.deriva` | fonte, espelho, estrito | status de cada caminho: igual, alterado, faltando, sobrando, não comparável |
| `portabilidade.colisoes` | bundle | nome repetido, cópia idêntica, cópia divergente, slug que colide e caixa trocada |
| `portabilidade.lote` | bundle, marketplace, versão, autor, repositório, licença | `plugin.json` de oito chaves por domínio e o `marketplace.json` |
| `portabilidade.matriz` | bundle, alvos | cada skill contra cada ferramenta, com o que sobrevive e o que se perde |
| `portabilidade.regras` | — | alvos, estilos, as dez regras, os limites e o que a camada não faz |

Todas aceitam `modo` com `lite`, `full` (padrão) ou `ultra`; `lite` devolve só o que bloqueia e `ultra` acrescenta as perguntas antes de liberar.

## O inventário é a entrada

O bundle entra de três formas, todas sem acesso a disco:

```
>>> caminho/da/skill/SKILL.md
conteúdo inteiro do arquivo
>>> caminho/da/skill/scripts/run.py
print("oi")
```

```json
{"arquivos": {"caminho/SKILL.md": "---\nname: x\n..."}}
```

```
caminho/SKILL.md | 412 | 9f2c1a77c0de5512 | arquivo
caminho/scripts/run.py | 40 | 12ab34cd56ef7890 | symlink
```

O bundle traz conteúdo e permite auditar o corpo; a lista plana traz só metadados e serve para deriva e lote. O agrupamento é por proximidade: cada arquivo pertence à skill mais próxima acima dele na árvore — o diretório que contém `SKILL.md`. Arquivo fora de qualquer skill aparece como **solto**, e solto não chega a alvo nenhum.

## Os treze alvos

| Alvo | Estilo | Base | Carrega apoio | Front matter |
|---|---|---|---|---|
| Claude Code | pasta | `~/.claude/skills/<slug>` | script, referência, asset, agente, comando | name, description, allowed-tools, model, version, license |
| OpenAI Codex | espelho | `.codex/skills/<slug>` + `skills-index.json` | script, referência, asset | name, description |
| Gemini CLI | pasta | `.gemini/skills/<slug>` | script, referência, asset | name, description |
| OpenClaw | pasta | `<plugin>/skills/<slug>` | script, referência, asset | name, description |
| Hermes Agent | espelho | `~/.hermes/skills/claude-skills/<slug>` | script, referência, asset | name, description |
| Mistral Vibe | espelho | `~/.vibe/skills/claude-skills/<slug>` | script, referência, asset | name, description |
| Windsurf | pasta | `.windsurf/skills/<slug>` | script, referência, asset | name, description |
| OpenCode | pasta | `.opencode/skills/<slug>` | script, referência, asset | name, description |
| Antigravity | pasta | `~/.gemini/antigravity/skills/<slug>` | script, referência, asset | name, description |
| Cursor | regra | `.cursor/rules/<slug>.mdc` | **nada** | description + alwaysApply |
| Kilo Code | regra | `.kilocode/rules/<slug>.md` | **nada** | description |
| Augment | regra | `.augment/rules/<slug>.md` | **nada** | description |
| Aider | convenção | `CONVENTIONS.md` | **nada** | sem front matter |

As treze notas de cada alvo estão em `portabilidade.regras`, incluindo a que mais dói: **espelho no Windows exige `git clone -c core.symlinks=true`**, senão o ponteiro vira arquivo de texto.

## 1. Auditar: o que quebra antes de converter

A auditoria lê o `SKILL.md` de cada pasta e separa o que **bloqueia** do que **corrige** e do que é **ajuste fino**.

| Grupo | Achado | Por que importa |
|---|---|---|
| must | front matter ausente ou ilegível | a skill existe no disco e não é indexada |
| must | `name` ausente | cada ferramenta escolhe um nome diferente |
| must | `name` fora do slug | caminho com espaço ou maiúscula não casa com o índice |
| should | `name` diverge da pasta | um vira chave de instalação, o outro é ignorado |
| must | `description` vazia | a descrição é o único gatilho que o agente lê |
| should | descrição acima de 500 caracteres | o `marketplace.json` corta no meio da frase |
| should | descrição abaixo de 40 caracteres | duas skills do domínio empatam |
| should | script que o corpo não menciona | código publicado que o agente nunca executa |
| should | script sem `allowed-tools` | a skill herda todas as ferramentas da sessão |
| should | corpo acima de 12 mil caracteres | o texto inteiro entra no contexto a cada ativação |
| should | binário acima de 512 KB | pesa em todos os espelhos |
| nice | sem gatilho explícito, sem `license`, sem `version` | funciona, mas é acionado e licenciado por sorte |
| nice | arquivo fora de `scripts/`, `references/`, `assets/` | copiado sem papel definido |
| nice | campo que o alvo escolhido descarta | informação que existe no repositório e não na ferramenta |

## 2. Converter: o plano, não o efeito

A conversão nunca escreve. Ela monta a lista de arquivos que a conversão faria, com cinco ações possíveis:

| Ação | Quando | Efeito |
|---|---|---|
| `copiar` | pasta ou espelho | o arquivo vai inteiro, com front matter reduzido ao que o alvo lê |
| `reescrever` | regra ou convenção | o `SKILL.md` vira arquivo de regra com `alwaysApply` ou seção de `CONVENTIONS.md` |
| `embutir` | convenção | todas as skills viram seções de um arquivo único, com `#` rebaixado um nível |
| `gerar` | espelho | `skills-index.json` com nome e caminho de cada skill |
| `descartar` | regra e convenção | script, referência e asset não acompanham |

Achados da conversão: **dois arquivos disputando o mesmo destino** (must — a cópia silenciosa sobrescreve), **alvo de regra que não carrega a pasta de apoio** (must — a regra manda rodar um script que não foi instalado), **destino acima de 200 caracteres** (should) e **skill grande em `CONVENTIONS.md`** (nice — o arquivo é lido inteiro em toda tarefa).

## 3. Deriva: espelho é derivado, não editado

A comparação classifica cada caminho em cinco estados:

| Estado | Significado | Grupo |
|---|---|---|
| `igual` | conteúdo ou hash batem | — |
| `alterado` | existe dos dois lados e o conteúdo difere | must |
| `faltando` | está na fonte e não está no espelho | should |
| `sobrando` | está no espelho e não está na fonte | should |
| `nao_comparavel` | nenhum dos dois lados trouxe conteúdo ou hash | should (ou must com `estrito`) |

Hash truncado compara só o prefixo comum aos dois lados; a cobertura declara quantos caminhos puderam ser comparados. Symlink no espelho sem caminho na fonte é **ponteiro quebrado** (must); symlink com caminho correspondente é ajuste fino, porque clone sem `core.symlinks=true` transforma o ponteiro em arquivo de texto.

## 4. Colisão: o destino decide

O upstream descobre o dual publish por script: a mesma skill em `<domínio>/skills/<nome>` e `<domínio>/<nome>/skills/<nome>`. Aqui a regra é mais ampla:

- **mesmo nome com corpo idêntico** — duplicata sincronizada (should);
- **mesmo nome com corpo diferente** — duas versões circulando (must);
- **nomes diferentes que geram o mesmo slug** — `Skill X` e `skill-x` no mesmo `.cursor/rules/` (must);
- **corpos idênticos com nomes diferentes** — capacidade duplicada (should);
- **arquivo de entrada com caixa trocada** — `skill.md` carrega no Linux e desaparece onde a comparação é literal (should).

## 5. Lote: oito chaves, sem exceção

O `plugin.json` gerado tem **exatamente** as oito chaves do schema: `name`, `description`, `version`, `author`, `homepage`, `repository`, `license`, `skills`. Qualquer chave a mais faz o validador recusar o manifesto e derrubar a instalação do plugin inteiro — o upstream chegou a manter metadados em arquivo irmão só por isso.

| Regra | Verificação |
|---|---|
| slug em minúsculas | `marketplace` e nome de plugin |
| semver | `X.Y.Z`, com pré-release opcional |
| autor e repositório obrigatórios | `https://github.com/dono/repo` |
| caminho com `./` | `./skills/<slug>`; sem o prefixo, o manifesto inteiro falha |
| limite de pacote | 25 MB por plugin (must acima disso) |
| vitrine | acima de 24 skills vira should; uma skill só vira nice |

O agrupamento é pela primeira pasta do caminho (`engineering/…` → plugin `engineering`), salvo quando o domínio é forçado na chamada.

## 6. Matriz: onde a skill chega inteira

A matriz cruza cada skill com cada alvo e classifica o par em `completo`, `parcial` (parte do apoio se perde) ou `so-entrada` (só o `SKILL.md` chega). É a resposta para “vale converter para o Cursor?”: se o valor da skill está no script, não vale — e o parecer diz isso com número.

## Limites

- **Nada é executado**: nenhum `--help` de script de skill, nenhum `convert.sh`, nenhum `install.sh`.
- **Nada é escrito**: o plano de conversão e os manifestos são texto na resposta; o disco fica intocado.
- **Nenhum modelo é chamado**: reescrita de instrução, tradução de front matter e escolha de alvo são determinísticas, não generativas.
- **Nenhum repositório é lido**: o inventário é o que foi colado; não há `git clone`, API do GitHub nem download de pacote.
- **YAML é lido no subconjunto do catálogo**: chave escalar e lista simples, sem âncora, alias ou objeto aninhado.
- **A validação de destino é declarada, não testada**: as oito chaves e o prefixo `./` vêm do validador do upstream; não há chamada ao servidor do marketplace.
- **Limites de volume**: 1.800.000 caracteres por entrada, 2.000 arquivos, 500 skills por bundle, 200 linhas de tabela na resposta.
- **Não publica nem versiona**: o número de versão é o informado na chamada; o lote não sobe pacote.

## Como rodar

```bash
npm run dev            # API 8000 + Vite 5173
# página: /portabilidade
curl -s localhost:8000/api/health
curl -s localhost:8000/api/skills/portabilidade.regras/execute \
  -H 'content-type: application/json' -d '{"parameters": {}}'
```

```bash
.venv/bin/python -m pytest server/tests/test_portabilidade.py -q
```

## Licença e atribuição

Desenho derivado de [`alirezarezvani/claude-skills`](https://github.com/alirezarezvani/claude-skills) (MIT, Alireza Rezvani e colaboradores). Nenhum arquivo do upstream foi copiado; a atribuição completa, com o que foi e o que não foi usado, está em [`docs/licenses/alirezarezvani-claude-skills.txt`](licenses/alirezarezvani-claude-skills.txt).
