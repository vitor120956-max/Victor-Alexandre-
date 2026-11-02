# JARVIS 0.74.0 — baixar só o que mudou, e saber sozinho que há versão nova

O pedido, nas palavras do dono:

> *“em vez de ficar baixando tudo só baixar e alterar o que foi mexido e modificado,
> isso diminuiria o tempo de espera; e também fazer o JARVIS reconhecer sempre que
> houver atualização que você lançar — ele reconhece e puxaria as atualizações e
> melhorias.”*

São duas coisas, e a 0.74.0 entrega as duas:

1. **atualização delta** — baixa o manifesto, compara hash por hash e puxa só os
   arquivos que mudaram;
2. **aviso automático** — o JARVIS vê a versão nova sozinho, no terminal e no topo
   da tela, sem você procurar.

E uma terceira que **não** foi entregue de propósito: **aplicar sozinho**.

---

## 1. O que já existia, e por que ainda valia mexer

| Caminho | Antes | Custo |
|---|---|---|
| quem instalou por `.git` | `git fetch` + `pull` | **já era delta**: o fetch só transfere objeto novo |
| quem instalou pelo **zip** | `atualizar.bat` → 3,5 MB, `robocopy` em 464 arquivos | tudo, sempre |

Ou seja: o desperdício real nunca foi do Git — foi do zip. É o seu caso (a pasta
`D:\JARVIS` não tem `.git`), e é o caso do pendrive, onde cada arquivo reescrito
custa mais do que o tamanho dele.

## 2. O mecanismo — `manifest.json` + `server/atualizacao.py`

`manifest.json`, na raiz do projeto, lista cada arquivo gerenciado com `sha256` e
tamanho (464 arquivos, ~56 KB). No seu computador:

```
baixa só o manifest.json  →  calcula o hash dos seus arquivos
   →  compara  →  baixa só os divergentes (cada um ~2–60 KB)
   →  confere o sha256 de cada um  →  guarda em storage/atualizacao/<versão>/
   →  [só com a sua confirmação]  copia por cima, guardando backup
```

A comparação é **por conteúdo**, não por número de versão. Consequências práticas:

- arquivo igual não é baixado de novo (nem se a versão mudou);
- arquivo que você editou e voltou ao conteúdo publicado também não é;
- o que sumiu do projeto aparece como **sobra** e **não é apagado** — apagar
  arquivo seu continua sendo decisão sua;
- `.env`, `storage/`, `.venv/`, `node_modules/`, `.git/`, `dist/`, logs e `.pyc`
  **não entram no manifesto** por definição, então não há como a atualização
  sobrescrever a sua chave ou os seus dados.

**Prova de que veio certo:** cada arquivo baixado é conferido contra o `sha256` do
manifesto *antes* de entrar no palco. Se não confere, é recusado e o palco fica
marcado como não confiável — e `aplicar` se recusa a rodar. Palco pela metade é o
jeito mais fácil de ficar com metade de cada versão no disco.

**Um defeito que a própria conferência achou:** a primeira versão do manifesto
incluía `tsconfig.tsbuildinfo` — cache do `tsc -b`, que o `.gitignore` exclui e
que muda a cada compilação. Nenhum usuário tem esse arquivo igual ao publicado,
então todo mundo apareceria “com arquivo divergente” para sempre. O sufixo entrou
na lista de ignorados e há teste fixando isso.

**Prova de que não sai da pasta:** o `aplicar` recusa caminho com `..`, caminho
absoluto ou arquivo fora do que o manifesto gerencia. Um `pronto.json` forjado não
escreve fora do projeto (tem teste para isso).

## 3. Quatro skills, e a diferença entre elas

| skill | faz | pede confirmação |
|---|---|---|
| `atualizacao.estado` | lê o registro da última checagem e dos palcos | não |
| `atualizacao.verificar` | baixa **só** o manifesto e diz o que mudou | não |
| `atualizacao.preparar` | baixa os divergentes para `storage/atualizacao/<versão>/` | **sim** |
| `atualizacao.aplicar` | substitui arquivos com backup e manda reiniciar | **sim** |

No chat (sem modelo nenhum, por regra escrita):

| você diz | vai para |
|---|---|
| “tem versão nova?”, “saiu atualização?”, “o que mudou na versão nova?” | `verificar` |
| “atualiza o jarvis”, “baixa só o que mudou”, “puxa as melhorias” | `preparar` |
| “aplica a atualização” | `aplicar` |
| “como atualizo o windows”, “atualizar o celular”, “arruma o pc” | **nada disso** — é outro assunto |

## 4. O aviso automático

- `iniciar-jarvis.bat` exporta `JARVIS_ATUALIZACAO=1`.
- Ao subir a API, uma thread espera 8 s, faz **uma** checagem e escreve no
  terminal:
  `JARVIS atualizacao: versao 0.74.0 disponivel (5 arquivo(s), 210 KB, a sua e 0.73.0)`.
- A tela mostra um aviso no topo (`src/components/UpdateBanner.tsx`), no máximo
  uma vez por hora por sessão, com **Baixar só o que mudou** e **Aplicar e
  reiniciar**. Depois de aplicar, o aviso passa a dizer o que falta: fechar a API
  no X e rodar `iniciar-jarvis.bat`.
- `JARVIS_ATUALIZACAO=0` desliga a checagem automática. “Tem versão nova?” continua
  funcionando no chat mesmo desligada — perguntar não depende de configuração.

## 5. O `atualizar.bat` ficou com o caminho rápido e o plano B

Com `.venv` na pasta, ele tenta, em ordem:

```bat
.venv\Scripts\python.exe -m server.atualizacao --verificar
.venv\Scripts\python.exe -m server.atualizacao --preparar
.venv\Scripts\python.exe -m server.atualizacao --aplicar --sim
```

Códigos de saída que ele entende: `0` seguiu, `1` falhou, `2` palco com hash
errado, `3` já está na última. Em `1` e `2` ele **cai no zip inteiro**, que
continua lá, preservando `.env`, `storage`, `.venv` e `node_modules`. Sem `.venv`,
vai direto para o zip. O delta é o atalho — não o único caminho.

## 6. O que eu acho — e o que **não** foi feito

**O ganho é real, mas menor do que parece fora do zip.** Com `.git`, o delta já
era nativo; a conta abaixo é do caminho zip:

| caminho | bytes | arquivos tocados |
|---|---|---|
| zip inteiro | ~3,5 MB | 464 |
| delta, só o manifesto | ~56 KB | 0 |
| delta, versão típica | ~60–400 KB | 2–15 |

Numa versão típica é **~1% do zip**. Não é “instantâneo”, é “não precisa mais
esperar 3,5 MB para trocar cinco arquivos”.

**Reconhecer é seguro; aplicar sozinho não é.** Três razões concretas:

1. o código novo só vale **depois de reiniciar a API** — o processo antigo tem os
   módulos carregados na memória, e trocar o arquivo embaixo não o atualiza;
2. reiniciar sozinho derrubaria a sua sessão no meio de uma tarefa;
3. atualização é justamente a ação que, quando dá errado, você precisa poder
   **identificar e desfazer** — daí o backup em
   `storage/atualizacao/backup-<data>/` e a resposta dizendo como voltar.

Então o desenho é: **checar é automático, baixar é silencioso, aplicar pede um
clique e um reinício.** Se um dia você quiser que ele aplique e reinicie sozinho,
o caminho já existe e é o mesmo da evolução de código: `JARVIS_HOST_EVOLUIR=1` com
token — não é o padrão, e não deveria ser.

## 7. Números desta versão

- **+4 skills** → 314 no registro;
- **+31 testes** (`server/tests/test_atualizacao.py`) → **3.121 passed, 7 skipped**;
- `vitest` → 128; `tsc -b` limpo; `build:embutido` ok; `checar-pendrive.mjs` ok;
- `manifest.json`: **464 arquivos, ~56 KB**, gerado **depois** do bump — se for
  gerado antes, ele hasheia a versão velha e passa a mentir.

## 8. O que ficou de fora, dito

- **baixar em segundo plano sem ninguém pedir**: não. Só a checagem é automática;
  o download de código só acontece quando você manda (botão, chat ou `.bat`).
- **apagar sobras automaticamente**: não. Ele lista; apagar é seu.
- **atualizar sem reiniciar**: não existe, e qualquer coisa que prometa isso está
  mentindo — o Python não recarrega módulo já importado.

Documento técnico completo, com os códigos de saída, o formato do manifesto e como
testar sem tocar no projeto: [`docs/ATUALIZACAO.md`](docs/ATUALIZACAO.md).
