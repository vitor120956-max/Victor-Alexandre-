# Submissão de artefatos

Quem recebe contribuição em catálogo de skill repete as mesmas perguntas antes de ler o conteúdo: o arquivo está na pasta certa? O front matter tem `name` e `description`? O texto manda rodar `curl | sh`? A licença é SPDX ou “MIT License”? O link aponta para um arquivo que veio no PR? A camada de submissão responde essas perguntas com conta explícita e devolve o rótulo do envio. O mérito do conteúdo continua com a pessoa.

O insumo é o [`github/awesome-copilot`](https://github.com/github/awesome-copilot) — **MIT**, 40 mil estrelas, o catálogo comunitário de skills, agentes, instruções, hooks e plugins do GitHub. Lá a aceitação passa por `eng/validate-skills.mjs`, `eng/pr-risk-scan.mjs`, `eng/lib/license.mjs` e o `eng/submission-gate`. Daqui não veio código JavaScript: veio o desenho — os limites de nome e descrição, as regras de risco por linha, o parser de SPDX e o vocabulário de estados — reimplementado em Python e medido com fixtures próprias.

| Camada | O que faz | Toca a rede? |
|---|---|---|
| **Motor** (`server/submissao.py`, 7 skills) | Lê ficha, estrutura, risco, licença e link do texto colado e decide o estado do envio | **Não** — só o que foi colado |
| **Página** (`/submissao`) | Aba por etapa, bundle de amostra, tabela de evidência e parecer pronto para copiar | Não |

Nada é executado: nenhum `vally lint` roda, nenhum plugin é instalado, nenhum repositório é baixado, nenhum rótulo é aplicado. Toda resposta marca `executed: false` e `readOnly: true`.

## As sete skills

| Rota | Entrada | O que devolve |
|---|---|---|
| `submissao.ficha` | caminho, conteúdo | campos do front matter conferidos contra o tipo, obrigatório ausente, inválido, extra e tamanho da descrição |
| `submissao.estrutura` | lista de caminhos ou bundle | caminho absoluto, saída por `..`, asset grande, vizinho obrigatório, nome repetido, arquivo oculto, caixa alta, pasta profunda e binário vazio |
| `submissao.risco` | bundle, teto de achados | nove regras por linha: guardrail desligado, shell remoto, `npx -y`, execução de pacote, versão flutuante, segredo, comando destrutivo, caminho absoluto e `sudo` |
| `submissao.licenca` | licença, esperada, obrigatória | expressão SPDX lida token a token, identificador desconhecido, copyleft, divergência da política e alias |
| `submissao.links` | bundle com conteúdo | destino inexistente, saída, âncora sem título, caixa diferente, link absoluto, `http://`, texto genérico e asset órfão |
| `submissao.gate` | bundle, licença esperada | roda as cinco checagens e decide `requires-submitter-fixes`, `awaiting-review` ou `ready-for-review` |
| `submissao.regras` | — | catálogo: tipos, campos, limites, regras de risco, ids SPDX e semântica do rótulo |

Todas aceitam `modo` com `lite`, `full` (padrão) ou `ultra`; `lite` devolve só o que bloqueia e `ultra` acrescenta as perguntas antes de liberar.

## O formato do envio

Cinco das sete skills leem o envio inteiro. O formato é um cabeçalho por arquivo:

```text
>>> skills/minha-skill/SKILL.md
---
name: minha-skill
description: Faz uma coisa específica em três passos.
---
# Minha skill

Veja o [guia](guia.md).
```

`>>> caminho` é a forma canônica porque não colide com título de Markdown. `### caminho` continua aceito, mas só quando a linha **parece caminho** — tem `/` ou termina em extensão de arquivo. `### Passos` dentro de um `SKILL.md` fica no corpo do arquivo, como deve ser. Também é aceito o JSON `{"arquivos": {"caminho": "conteúdo"}}`. Constantes: **1,8 MB** de texto, **300 arquivos** e **200 linhas por tabela**.

## 1. Ficha: o front matter é contrato

O tipo sai do caminho (`skills/<nome>/SKILL.md`, `agents/<nome>.agent.md`, `hooks/<nome>/`, `plugins/<nome>/`…), e cada tipo tem os seus obrigatórios:

| Tipo | Obrigatórios | Opcionais |
|---|---|---|
| `skill` | `name`, `description` | `license`, `version`, `allowed-tools`, `metadata` |
| `agent` | `name`, `description` | `model`, `tools`, `mcp-servers`, `title` |
| `instruction` | `description`, `applyTo` | `title`, `tools` |
| `hook` | `name`, `description` | `tags`, `version` |
| `plugin` | `name`, `description`, `version`, `author` | `keywords`, `license`, `repository`, `homepage`, `$schema`, `extensions` |
| `workflow` | `description` | `name`, `on`, `permissions`, `tools` |
| `prompt` | `description` | `name`, `mode`, `tools`, `model` |

O leitor de front matter é próprio e mínimo: `chave: valor`, aspas simples ou duplas (com comentário depois do fechamento), lista `[a, b]`, bloco `- item`, número, booleano, `null` e comentário iniciado por `#`. Não interpreta âncora, alias, tag nem multi-documento — isso é limite declarado, não bug.

Achados: `nome-divergente` (must — o `name` não bate com a pasta), `front-matter-invalido` (must), `campo-obrigatorio-ausente` (must), `campo-invalido` (must — nome fora de `^[a-z0-9]+(-[a-z0-9]+)*$`, descrição fora de 10–1024, tag fora de 30 caracteres, mais de 10 tags, `version` que não é semver, `repository` que não é URL), `tipo-desconhecido`, `campo-extra` e `descricao-longa` (acima de 1024).

## 2. Estrutura: caminho, tamanho e vizinho

O envio pode vir como bundle (com conteúdo) ou só como lista de caminhos, um por linha, opcionalmente com o tamanho em bytes — útil para conferir um PR sem colar os arquivos. O caminho pode ter espaço (`skills/meu time/SKILL.md 120`), e o número no fim é lido como tamanho.

| Achado | Nível | Quando |
|---|---|---|
| `caminho-absoluto` | must | começa com `/` ou `C:/` |
| `caminho-com-saida` | must | tem `..` em qualquer segmento |
| `asset-grande` | must | passa de **5 MB** por arquivo |
| `vizinho-obrigatorio` | must | hook sem `hooks.json` ou plugin sem `README.md` na mesma pasta |
| `nome-repetido` | should | dois artefatos com o mesmo nome — `skills/x/SKILL.md` e `plugins/x/plugin.json` são ambos `x` |
| `arquivo-oculto` | should | arquivo ou pasta começando com ponto (`.github` é exceção) |
| `caixa-alta` | should | nome de arquivo com maiúscula que não é canônico (`SKILL.md`, `README.md`, `hooks.json`, `plugin.json` são) |
| `pasta-profunda` | nice | mais de quatro níveis |
| `binario-vazio` | nice | imagem ou binário com zero byte |

Nome repetido é contado pelo **nome do artefato**, não do arquivo: a pasta em `skills/x/SKILL.md`, o nome sem sufixo em `agents/x.agent.md` e o id em `plugins/x/plugin.json` comparecem todos como `x`. Arquivos de documentação (`README.md`, `LICENSE`, `CHANGELOG.md`) ficam fora da conta — eles se repetem por desenho.

## 3. Risco: nove regras, uma linha por vez

A varredura é lexical e conservadora: cada linha é testada contra nove padrões, o trecho é **mascarado** quando há segredo e truncado em **180 caracteres**, e o total para em **1.000 achados**.

| Regra | Nível | O que pega |
|---|---|---|
| `bypass-de-guardrail` | alto | “ignore as regras”, “bypass the guardrails”, “disable safety” |
| `shell-remoto` | alto | `curl … \| sh`, `wget … \| bash`, inclusive com `sudo` |
| `autoyes` | alto | `npx -y`, `npm exec --yes`, `pnpm dlx … --force`, `uvx -y` |
| `segredo-no-texto` | alto | chave conhecida (`AKIA…`, `ghp_…`, `sk-…`, `BEGIN PRIVATE KEY`, `xox[baprs]-…`) e atribuição longa |
| `comando-destrutivo` | alto | `rm -rf`, `mkfs`, `dd of=/dev/`, `git push --force`, truncar tabela |
| `execucao-de-pacote` | médio | `npx`, `pnpm dlx`, `uvx`, `pipx run`, `uv tool run` |
| `versao-flutuante` | médio | `@latest`, `^`/`~`/`*` em dependência, `pip install pkg>=2` sem teto |
| `caminho-absoluto` | médio | `/usr/…`, `/etc/…`, `/opt/…` em comando |
| `sudo` | médio | `sudo` seguido de comando |

Além das regras, saem `script-empacotado` (nice — há `.sh`, `.ps1`, `.py` ou `.js` sob `skills/`: o script também é revisado), `binario-no-envio` (nice — arquivo com byte NUL), `sem-conteudo` (should — só caminhos, sem texto para varrer), `risco-limpo` (nice) e o agregado `risco-alto` (must) / `risco-medio` (should) que alimentam o portão.

## 4. Licença: expressão SPDX, não prosa

O parser é próprio, com **45 identificadores**, 10 exceções e os operadores `AND`, `OR` e `WITH`, além de parênteses, `LicenseRef-` e `DocumentRef-`. Ele devolve a árvore, os tokens e a expressão normalizada.

| Situação | Achado | Nível |
|---|---|---|
| vazia e `obrigatoria` | `licenca-ausente` | must |
| sintaxe quebrada (`MIT AND`) | `licenca-malformada` | must |
| id fora da lista (`MIT-0x`) | `licenca-desconhecida` | should |
| família copyleft (`GPL`, `AGPL`, `MPL`, `EPL`, `CC-BY-SA`…) | `licenca-copyleft` | should |
| diferente da esperada pela política | `licenca-divergente` | should |
| prosa que virou id (`GPLv3`, `Apache 2.0`, `MIT License`) | `licenca-alias` | should, com sugestão |

`GPLv3` e `Apache 2.0` **não** são erro de sintaxe: viram identificador desconhecido com alias sugerido. Só `MIT License` cai em malformada, porque o sufixo “License” não é operador nem id — e a sugestão é `MIT`.

## 5. Links: destino, âncora e texto

Antes de procurar link, o texto é limpo: bloco cercado por ``` ``` ``` e trecho entre crases são ignorados — exemplo de Markdown dentro de documentação não é link. São reconhecidos `[texto](destino)`, `[texto][ref]` com `[ref]: destino` e `href="…"`/`src="…"` em HTML.

| Situação | Achado | Nível |
|---|---|---|
| arquivo não está no envio | `link-quebrado` | must |
| `../` sai da pasta do envio | `link-escapa` | must |
| `#trecho` sem título correspondente | `ancora-quebrada` | should |
| arquivo existe com outra caixa | `caixa-do-caminho` | should |
| começa com `/` | `link-absoluto` | should |
| `http://` | `link-inseguro` | nice |
| texto “clique aqui”, “leia mais”, “link” | `texto-de-link-generico` | nice |
| asset no envio sem nenhum link | `asset-nao-referenciado` | nice |
| nenhum link no envio | `sem-links` | nice |

A âncora segue o slug do GitHub: minúscula, sem formatação, acento removido, espaço vira hífen, repetição ganha `-1`, `-2`. Cada link externo (`https:`, `mailto:`, `tel:`) conta como **ok** sem sair da máquina.

## 6. Portão: a decisão do rótulo

As cinco checagens rodam em sequência e alimentam a tabela de evidência — uma linha por checagem, com achados, bloqueios e estado.

| Decisão | Regra |
|---|---|
| `requires-submitter-fixes` | existe **qualquer** achado `must` |
| `awaiting-review` | não há conteúdo para conferir (só caminhos) |
| `ready-for-review` | nenhum `must` e o conteúdo foi conferido |
| `approved` / `rejected` | ficam para a revisão humana; a camada não aplica rótulo |

O parecer já diz qual rótulo remover: `awaiting-review`. `sem-artefato` (must) e `envio-grande` (should, acima de 300 arquivos) completam o portão.

## 7. Catálogo

`submissao.regras` publica o que a camada sabe, sem calcular nada: os sete tipos e seus campos, os limites (1,8 MB, 300 arquivos, 1.000 achados, 5 MB por asset, nome de 1 a 64, descrição de 10 a 1024, até 10 tags de 30 caracteres), as nove regras de risco com motivo e correção, os 45 ids SPDX, as dez exceções, os aliases, as situações de link, as decisões do portão e a lista do que **não** é feito.

## Execução real

Rodando as skills contra cinco artefatos reais do `awesome-copilot` (uma skill, um agente, uma instrução, um hook com `hooks.json` e um plugin com `README.md` — 7 arquivos, 28 kB, 839 linhas):

| Skill | Resultado |
|---|---|
| `submissao.ficha` | 2 campos, 2 obrigatórios, 0 ausentes, 0 inválidos, descrição de 98 caracteres |
| `submissao.estrutura` | 7 arquivos, 5 pastas, 5 tipos, 28.416 bytes, 0 grandes, 0 repetidos, 0 vizinhos faltando |
| `submissao.risco` | 7 arquivos varridos, 839 linhas, **0 achados** |
| `submissao.licenca` | 1 token, 1 id, válida, 0 copyleft |
| `submissao.links` | 0 links — os `[texto](url)` do README estão dentro de tabela de código e foram ignorados |
| `submissao.gate` | **`ready-for-review`**, 0 bloqueios, 2 opcionais (`risco-limpo`, `sem-links`) |

E contra uma skill com quatro linhas de comando:

| Skill | Resultado |
|---|---|
| `submissao.risco` | **7 achados** em 14 linhas: 3 altos (`shell-remoto`, `autoyes`, `comando-destrutivo`) e 4 médios (`execucao-de-pacote`, `caminho-absoluto`, `sudo`, `versao-flutuante`) |
| `submissao.gate` | **`requires-submitter-fixes`**, 1 bloqueio (`risco-alto`) e 1 atenção (`risco-medio`) |

Os números são do texto colado, não do repositório: a camada não abre `git` nem `gh`.

## Limites declarados

- O front matter é lido por um parser de subconjunto: âncora, alias, tag e multi-documento ficam de fora.
- O risco é lexical: frase reescrita que não case com o padrão não é vista, e idioma fora do português e do inglês escapa.
- O texto dentro de bloco de código **é** varrido pelo risco (é lá que o comando perigoso costuma estar) e **não** é varrido pelos links.
- A âncora segue a slug do GitHub, não o `id` explícito de HTML.
- Licença é comparada por identificador, não por texto de arquivo `LICENSE`.
- Nada é publicado: nenhum rótulo, comentário ou issue é criado.
- O mérito do conteúdo — clareza, utilidade, duplicata com o que já existe — continua na revisão humana.

## Licença e atribuição

O desenho vem de [`github/awesome-copilot`](https://github.com/github/awesome-copilot), **MIT**. Nenhum arquivo JavaScript foi copiado e nenhuma dependência foi adicionada: o validador de skill, a varredura de risco, o parser SPDX e o vocabulário de estados foram reimplementados em Python com fixtures próprias. A atribuição e o texto da licença estão em [`licenses/awesome-copilot.txt`](licenses/awesome-copilot.txt).
