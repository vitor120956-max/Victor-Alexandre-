# Atualização delta (0.75.0)

> Pedido: *“em vez de ficar baixando tudo só baixar e alterar o que foi mexido…
> e fazer o JARVIS reconhecer sempre que houver atualização.”*

O `atualizar.bat` sempre funcionou, mas baixava **3,5 MB e 472 arquivos** para
trocar, numa versão típica, umas cinco coisas. A 0.75.0 acrescenta o caminho
delta: um manifesto com o `sha256` de cada arquivo, comparação local e download
só do que mudou.

## As três perguntas, separadas

| Pergunta | O que acontece | Custo |
|---|---|---|
| **Tem versão nova?** | baixa só o `manifest.json` e compara hash por hash | ~57 KB, nenhuma escrita no projeto |
| **Baixar o que mudou** | baixa os arquivos divergentes e confere cada `sha256` | uns poucos arquivos, centenas de KB |
| **Aplicar** | copia o palco conferido por cima, com backup | exige confirmação e reinício da API |

A confusão comum é juntar as três. Aqui elas são skills diferentes:

| Skill | Efeito | Confirmação |
|---|---|---|
| `atualizacao.estado` | lê o registro da última checagem | não |
| `atualizacao.verificar` | baixa o manifesto e diz o que mudou | não |
| `atualizacao.preparar` | baixa para `storage/atualizacao/<versão>/` | sim |
| `atualizacao.aplicar` | substitui arquivos, com backup | sim |

No chat: *“tem versão nova?”* → verificar; *“atualiza o jarvis”* ou *“baixa só o
que mudou”* → preparar; *“aplica a atualização”* → aplicar. *“Atualizar o
Windows”* ou *“atualizar o celular”* **não** cai aqui — é outra coisa.

## Como a comparação funciona

`manifest.json` (na raiz, ~57 KB) tem, para cada arquivo gerenciado:

```json
{"versao": "0.75.0", "gerado": "2026-11-01T21:00:00+00:00",
 "arquivos": {"server/app.py": {"sha256": "…", "bytes": 12345}}}
```

A comparação é **por conteúdo**, não por número de versão: um arquivo que você
editou para voltar ao conteúdo publicado não é baixado de novo, e um arquivo
que o GitHub não mudou não ocupa banda nem disco. Sobras (o que existia na sua
cópia e saiu do projeto) aparecem em `extras` — e **não são apagadas**: apagar
arquivo seu continua sendo decisão sua.

O manifesto nunca inclui `.env`, `storage/`, `.venv/`, `node_modules/`, `.git/`,
`dist/`, logs, `.pyc` ou ele mesmo. Ou seja: atualizar não pode sobrescrever seus
dados nem sua chave.

## O que garante que o download não veio trocado

Cada arquivo baixado é conferido contra o `sha256` do manifesto **antes** de
entrar no palco. Se não confere, ele é recusado e o palco fica marcado como
`pronto: false` — e `aplicar` se recusa a rodar em palco sujo. Aplicar um palco
pela metade é o jeito mais fácil de ficar com metade de cada versão no disco.

Antes de copiar, o `aplicar` confere o caminho: nada de `..`, nada de caminho
absoluto, nada fora do que o manifesto gerencia. Um `pronto.json` forjado não
escreve fora da pasta do projeto.

## Aviso automático

- `iniciar-jarvis.bat` exporta `JARVIS_ATUALIZACAO=1`.
- Ao subir a API, uma thread espera 8 s, baixa o manifesto uma vez e escreve no
  terminal: `JARVIS atualizacao: versao 0.75.0 disponivel (5 arquivo(s), 210 KB…)`.
- A tela mostra o aviso no topo (`src/components/UpdateBanner.tsx`), no máximo
  uma vez por hora por sessão (`sessionStorage`), com dois botões:
  **Baixar só o que mudou** e **Aplicar e reiniciar**.
- `JARVIS_ATUALIZACAO=0` desliga. A skill `atualizacao.verificar` com
  `forcar: true` continua funcionando mesmo desligada — “tem versão nova?” não
  depende de configuração.

## Atualização automática ao subir (0.78.0)

Até a 0.77.1 o JARVIS **reconhecia** versão nova, mas aplicar era sempre um
clique seu — e a pergunta voltou: *“ué, o JARVIS ainda não se auto atualiza?”*.

A resposta certa não é aplicar no meio do expediente (aí o motivo original
continua valendo: o processo velho tem o código na memória). É aplicar **no
start**, quando a API ainda não existe:

```text
iniciar-jarvis.bat
  [1/4] .venv
  [2/4] bibliotecas
  [3/4] se atualiza sozinho   <- aqui: verifica, baixa só o que mudou, aplica
  [4/4] sobe a API            <- já com o código novo
```

O que roda é `python -m server.atualizacao --auto`, em
`server/atualizacao.py:auto_atualizar`.

### As três travas

| trava | por quê |
|---|---|
| **nunca derruba o start** | sem internet, GitHub bloqueado, hash estranho: sobe na versão atual e diz o motivo |
| **nunca aplica palco com falha** | um arquivo que não conferiu cancela o lote inteiro |
| **nunca em pasta com `.git`** | ali quem manda é o `git`; aplicar por cima deixaria a árvore suja e o `evoluir.promover` exige árvore limpa |

Além disso, `requirements.txt` mudou → o `.bat` roda `pip install -r
requirements.txt` antes de subir (o Python avisa isso pelo código de saída **4**).

### Ligar e desligar

| onde | efeito |
|---|---|
| padrão | **ligado** (o `iniciar-jarvis.bat` exporta `JARVIS_AUTO_ATUALIZAR=1`) |
| `.env` com `JARVIS_AUTO_ATUALIZAR=0` | desliga — o `.env` **manda mais** que a variável do `.bat` |
| `py iniciar.py --sem-atualizar` | sobe sem checar (uma vez, sem mexer no `.env`) |
| `py iniciar.py` sozinho | também atualiza (a menos que `JARVIS_AUTO_FEITO=1`, que o `.bat` marca) |

### O que continua sendo você

- **reiniciar** o JARVIS depois de uma atualização aplicada pela **tela** ou pelo
  chat (aliás, o `atualizar.bat` e o start já reiniciam por natureza);
- **decidir** quando não usar: se estiver no meio de um trabalho e não quiser
  versão nova agora, é só `JARVIS_AUTO_ATUALIZAR=0` no `.env`;
- **conferir o backup** quando algo parecer estranho: `storage/atualizacao/backup-<data>/`.

### Por que não no meio do expediente

1. o código novo só vale depois de **reiniciar a API** — o processo velho tem o
   módulo carregado na memória, e trocar arquivo embaixo não o atualiza;
2. reiniciar sozinho derrubaria a sessão no meio de uma tarefa sua;
3. atualizar é o tipo de ação que, se der errado, você precisa poder identificar
   e desfazer — daí o backup em `storage/atualizacao/backup-<data>/` e a
   resposta dizendo como voltar.

## Plano B continua valendo

Se o GitHub estiver fora do ar, se o `raw.githubusercontent.com` estiver
bloqueado, ou se algum arquivo não conferir, o `atualizar.bat` cai no caminho
antigo: baixa o zip inteiro e copia por cima, preservando `.env`, `storage`,
`.venv` e `node_modules`. O delta é o caminho rápido, não o único.

O `.bat` lê o código de saída do Python:

| Código | Significado | O que o `.bat` faz |
|---|---|---|
| 0 | seguiu | continua para o próximo passo |
| 1 | falhou (rede, manifesto inválido) | cai no zip |
| 2 | palco com falha de hash | cai no zip |
| 3 | já está na última | não baixa nada |
| 4 | `--auto` aplicou e as dependências mudaram | roda `pip install -r requirements.txt` antes de subir |

## Números reais

| Caminho | Bytes | Arquivos tocados |
|---|---|---|
| zip inteiro (`atualizar.bat` antigo) | ~3,5 MB | 464 |
| delta (só o manifesto) | ~57 KB | 0 |
| delta (versão típica) | ~60–400 KB | 2–15 |

Numa versão típica isso é **~1% do zip**. E, para quem tem `.git`, o delta já era
nativo: `git fetch` só transfere objeto novo. O ganho real é para quem instalou
pelo zip — inclusive no pendrive, onde cada arquivo reescrito custa mais do que o
tamanho dele.

## Como testar sem tocar no seu projeto

```bat
cd /d D:\JARVIS
.venv\Scripts\python.exe -m server.atualizacao --verificar
```

Só lê. Para ver o estado gravado:

```bat
.venv\Scripts\python.exe -m server.atualizacao --json
```

E para gerar o manifesto de um release (é o que o script de publicação usa):

```bat
.venv\Scripts\python.exe scripts\gerar-manifesto.py
.venv\Scripts\python.exe scripts\gerar-manifesto.py --conferir
```

`--conferir` devolve 0 quando o manifesto no disco bate com os arquivos, 1 quando
ele falta e 2 quando está velho (algum hash mudou depois de gerado). É o teste
que impede publicar manifesto desatualizado — e ele tem de ser gerado **depois**
de qualquer mudança, inclusive do próprio número de versão.
