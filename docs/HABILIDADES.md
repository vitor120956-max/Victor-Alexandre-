# Habilidades de fora — puxar, guardar e usar

O pedido que originou esta camada: *“se eu pedir para ele adicionar essas melhorias
[lista de habilidades de skills.sh e clawhub.ai], ele vai conseguir pesquisar e puxar
os dados e depois usar numa pergunta minha?”*

Resposta curta: **puxar e guardar, sim — de graça, sem token. “Usar” tem limite, e o
limite está escrito aqui embaixo.** Nada nesta camada é escondido atrás de uma
promessa que não se cumpre.

## O que é uma “habilidade” dessas

As habilidades publicadas em `skills.sh`, `clawhub.ai` e nos repositórios do GitHub
são **arquivos de texto** no padrão *Agent Skills*: um `SKILL.md` em markdown, com um
cabeçalho e um corpo de instruções.

```markdown
---
name: frontend-design
description: Diretrizes de design de front-end
allowed-tools: Read, Write
---
# Front-end
...
```

Quem “usa” esse arquivo é um **modelo de linguagem**: ele lê as instruções e escreve
o código seguindo aquilo. O JARVIS, por decisão sua, **não tem modelo**: sem chave, sem
provedor, sem API. Então a habilidade não vira raciocínio sozinha — vira **roteiro**.

## O que o JARVIS faz, de fato

| Você pede | Ele faz |
|---|---|
| `importa a habilidade <link>` | baixa o `SKILL.md`, lê o cabeçalho, guarda em `storage/habilidades.json` |
| `quais habilidades você importou` | lista nome, descrição e origem de cada uma |
| `usa a habilidade <nome> para <pedido>` | devolve o roteiro inteiro, com a sua pergunta em cima e a fonte embaixo |
| `esquece a habilidade <nome>` | apaga do arquivo local |

Nada é instalado, nada é executado, nada sai da máquina a não ser a leitura do link.
O token de host **não** é pedido: é texto, não binário.

## De onde ele consegue puxar

| Link colado | Como é resolvido |
|---|---|
| `github.com/dono/repo/blob/main/caminho/SKILL.md` | vira `raw.githubusercontent.com/...` e vem como texto |
| `github.com/dono/repo/tree/main/skills/nome` | tenta `.../skills/nome/SKILL.md` |
| `github.com/dono/repo` | tenta `SKILL.md`, `skills/<repo>/SKILL.md`, `.claude/skills/<repo>/SKILL.md` — e, se não houver, **varre a árvore do repositório** e pega o primeiro `SKILL.md` que achar |
| botão **Raw** do GitHub | passa direto |
| `skills.sh/...` ou `clawhub.ai/...` | baixa a página, acha o link do GitHub dentro dela e segue até o `SKILL.md` |

Repositório com dezenas de habilidades (como `vercel-labs/agent-skills`) funciona
assim: ele importa a primeira e avisa **quantas outras existem**, com o link da
pasta para você escolher a próxima.

Se nenhum endereço devolver markdown, ele **não inventa**: responde que não achou e
pede o link do arquivo — no GitHub, o do botão **Raw**.

## Os limites, ditos sem rodeio

1. **Habilidade não é código que roda.** Ela é um roteiro para você (ou para um modelo)
   seguir. O JARVIS guarda, mostra e aponta — não “executa a skill”.
2. **Sem modelo, não há raciocínio.** Uma habilidade como *front-end design* vira uma
   lista de conferência; *grill-me* vira uma sequência de perguntas para você mesmo
   responder. Nada disso acontece “sozinho”.
3. **Habilidades que dependem de modelo pago não funcionam sem chave.** “geração de
   imagens por IA”, “nano-banana-pro” e similares precisam de um serviço de imagem.
   O texto delas é guardado; o efeito, não acontece.
4. **As que dão para checar de verdade já existem como código.** Contraste, tokens de
   design, estrutura de componente, revisão de plano: isso está em `studio.*`,
   `revisao.*`, `selecao.*` e companhia — skills determinísticas, com teste, sem chave.
   A habilidade importada complementa; ela não substitui a verificação.
5. **Copilot não entra.** O GitHub Copilot é serviço de modelo **pago**, com assinatura
   e token. O projeto é sem chave por decisão sua — e o JARVIS não finge que usa o que
   não pode usar.

## GitHub sem Git e sem token

Para achar e ler as habilidades, existe a camada `github.*`, que fala com a API
pública do GitHub:

| Skill | O que devolve |
|---|---|
| `github.repo` | estrelas, linguagem, licença, branch padrão, tópicos, link |
| `github.arquivos` | o que tem dentro de uma pasta (pasta/arquivo, tamanho, caminho) |
| `github.arquivo` | o texto de um arquivo, decodificado do base64 da API |
| `github.buscar` | repositórios públicos por palavra, ordenados por estrelas |
| `github.arvore` (interna) | todos os caminhos do repositório de uma vez, para descobrir onde estão os `SKILL.md` |

Limites honestos: **60 pedidos por hora** por endereço IP, só repositório **público**,
sem `push`, sem *issue*, sem `clone`. Para trazer o repositório inteiro existe
`repos.baixar` (o `.zip`); esta camada é para **espiar**.

## Passo a passo no seu PC

1. Suba a API com rede ligada:

```bat
cd /d D:\JARVIS
set JARVIS_HOST_REDE=1
.venv\Scripts\python iniciar.py
```

2. No chat, cole o link do arquivo:

```text
importa a habilidade https://github.com/anthropics/skills/blob/main/skills/frontend-design/SKILL.md
```

3. Responda **“sim, pode”**. Ele responde com o nome, a fonte e o tamanho.

4. Confira a lista:

```text
quais habilidades você importou
```

5. Use como roteiro:

```text
usa a habilidade frontend-design para revisar a tela de login
```

## Onde ficam os arquivos

| Peça | Arquivo |
|---|---|
| puxar, interpretar e guardar | `server/habilidades.py` |
| ler a API do GitHub | `server/github.py` |
| o que você importou | `storage/habilidades.json` (ou `JARVIS_DADOS/habilidades.json`) |
| skills no registro | `habilidades.importar`, `habilidades.listar`, `habilidades.aplicar`, `habilidades.remover`, `github.repo`, `github.arquivos`, `github.arquivo`, `github.buscar` |

O arquivo é JSON legível — dá para abrir no Bloco de Notas, copiar e apagar à mão.

## O que dá para testar sem rede

Tudo. Os 38 testes de `server/tests/test_habilidades.py` e `server/tests/test_github.py`
usam um baixador falso: cobrem front matter, link `blob` → `raw`, `tree` → `SKILL.md`,
página de catálogo seguindo link interno, marcação “novo” × “atualizado”, corte no
limite, remoção, base64 da API, pasta que não é arquivo, a árvore que descobre `SKILL.md` dentro de
pastas e o aviso de limite de 60 pedidos por hora. Nenhum deles abre um socket.
