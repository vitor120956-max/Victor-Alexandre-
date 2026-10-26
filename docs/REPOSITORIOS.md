# Repositórios: copiar e usar sem Git

A partir da **0.41.0** o JARVIS baixa um repositório público do GitHub como `.zip`,
guarda em `storage/repos`, descreve o que veio e — só depois do seu “sim” — roda
um comando dentro dele.

Isso resolve o pedido literal: *“copiar um repositório e usá-lo”*. A máquina não
tem Git, não tem `tar` e o Python é 3.15; nada disso é necessário aqui.

---

## 1. As seis skills

| Skill | O que faz | Tem efeito? |
|---|---|---|
| `repos.baixar` | baixa o `.zip` do `codeload`, extrai, analisa e registra | **sim**, pede confirmação |
| `repos.analisar` | README, linguagens, dependências, entradas e árvore do que já está baixado | não |
| `repos.listar` | o que está em `storage/repos`, com data e tamanho | não |
| `repos.ler` | texto de um arquivo de dentro do repositório | não |
| `repos.executar` | roda `python` / `node` / `npm` / `npx` / `make` na pasta do repositório | **sim**, pede confirmação |
| `repos.remover` | apaga a pasta baixada e tira do índice | **sim**, pede confirmação |

---

## 2. No chat

```text
você: baixar o repositório virgiliojr94/book-to-skill
ele:   A skill “Baixar repositório” (repos.baixar) baixa, grava ou executa algo.
       Vou usar: url=virgiliojr94/book-to-skill. Responda “sim, pode” para eu seguir.

você: sim, pode
ele:   <o que veio: arquivos, tamanho, linguagens, README, entradas prováveis>
```

Duas coisas importantes nesse desenho:

- **antes do efeito**, ele mostra exatamente os parâmetros que vai usar;
- **o “sim” vale uma vez** — se você pedir outro download, ele pergunta de novo.

O endereço pode vir de quatro jeitos: `dono/repo`, `https://github.com/dono/repo`,
`git@github.com:dono/repo.git` ou `.../tree/branch`.

---

## 3. O que a análise devolve

Para o `virgiliojr94/book-to-skill`, medido em 25/10/2026:

| Medida | Valor |
|---|---|
| Arquivos | **130** |
| Tamanho extraído | **2,0 MB** |
| Linguagens | Python 83 · Markdown 24 · YAML 6 |
| README | “book-to-skill” |
| **SKILL.md** | presente na raiz (padrão Agent Skills) |
| Entradas | `book-to-skill` (script do `pyproject`) · `pip install -e .` · `python -m book_to_skill` |

A resposta em texto sai assim:

> Linguagem principal: Python, Markdown, YAML. Entradas prováveis: `book-to-skill`;
> `pip install -e .`; `python -m book_to_skill`. Traz skill no padrão Agent Skills:
> `SKILL.md`. Nada foi instalado nem executado.

---

## 4. Usar de verdade

Depois de baixar, o que dá para fazer sem instalar nada:

```text
ver o README do repositório virgiliojr94--book-to-skill
ler o arquivo SKILL.md do repositório virgiliojr94--book-to-skill
rodar python -m book_to_skill --help no repositório virgiliojr94--book-to-skill
```

O terceiro pedido exige autorização, roda com tempo limite e devolve código de
saída, saída padrão e erro.

Se o projeto precisa de dependência que não está instalada, o comando falha com o
`ModuleNotFoundError` do próprio Python. O JARVIS **não instala** nada por conta
própria: ele mostra o erro e você decide.

---

## 5. As travas

| Trava | Valor |
|---|---|
| Tamanho do `.zip` | 64 MB |
| Arquivos no pacote | 4.000 |
| Conteúdo extraído | 200 MB |
| Arquivo individual | 20 MB |
| Caminho absoluto, `..` ou `C:` | recusado |
| Link simbólico no pacote | recusado |
| Interpretadores | `python`, `python3`, `py`, `node`, `npm`, `npx`, `make` |
| Caracteres de shell (`;`, `\|`, `&&`, `>`, `` ` ``, `$(`) | recusados |
| Tempo de execução | 120 s por padrão (máx. 600) |
| Variáveis de ambiente | qualquer uma com `TOKEN`, `SECRET`, `PASS`, `KEY` ou `JARVIS_` é removida |
| Diretório de trabalho | sempre a pasta do repositório |

Não existe shell: o comando é quebrado em argumentos e executado direto, sem
`shell=True`. Não existe `git clone`, `pip install` automático, repositório
privado nem acesso à sua pasta pessoal.

---

## 6. O que esta camada não faz

- **não instala dependências** — isso é `sistema.instalar`, com plano e token de uso único;
- **não garante que o projeto roda** — descreve e diz o que falta;
- **não clona com Git** — baixa o `.zip` da branch padrão (ou da que você indicar em `ref`);
- **não lê repositório privado**;
- **não usa modelo de IA** em nenhum passo.

---

## 7. Onde fica

| Caminho | Conteúdo |
|---|---|
| `storage/repos/<dono>--<repo>/` | o repositório extraído |
| `storage/repos/indice.json` | lista dos últimos 50, com data, tamanho e entradas |
| `server/repos.py` | baixar, extrair, analisar, ler, executar e remover |
| `server/skill_registry.py` | as seis skills da categoria **Repositórios** |
| `server/tests/test_repos.py` | 50 testes, sem rede |

`storage/` está no `.gitignore`: repositório baixado não entra no seu commit.
