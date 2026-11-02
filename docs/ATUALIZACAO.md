# Atualização delta (0.74.0)

> Pedido: *“em vez de ficar baixando tudo só baixar e alterar o que foi mexido…
> e fazer o JARVIS reconhecer sempre que houver atualização.”*

O `atualizar.bat` sempre funcionou, mas baixava **3,5 MB e 464 arquivos** para
trocar, numa versão típica, umas cinco coisas. A 0.74.0 acrescenta o caminho
delta: um manifesto com o `sha256` de cada arquivo, comparação local e download
só do que mudou.

## As três perguntas, separadas

| Pergunta | O que acontece | Custo |
|---|---|---|
| **Tem versão nova?** | baixa só o `manifest.json` e compara hash por hash | ~56 KB, nenhuma escrita no projeto |
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

`manifest.json` (na raiz, ~56 KB) tem, para cada arquivo gerenciado:

```json
{"versao": "0.74.0", "gerado": "2026-11-01T21:00:00+00:00",
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
  terminal: `JARVIS atualizacao: versao 0.74.0 disponivel (5 arquivo(s), 210 KB…)`.
- A tela mostra o aviso no topo (`src/components/UpdateBanner.tsx`), no máximo
  uma vez por hora por sessão (`sessionStorage`), com dois botões:
  **Baixar só o que mudou** e **Aplicar e reiniciar**.
- `JARVIS_ATUALIZACAO=0` desliga. A skill `atualizacao.verificar` com
  `forcar: true` continua funcionando mesmo desligada — “tem versão nova?” não
  depende de configuração.

## O que **não** é automático, e por quê

Reconhecer é seguro: lê 56 KB e não escreve no projeto. **Aplicar sozinho não é.**
Três motivos concretos:

1. o código novo só vale depois de **reiniciar a API** — o processo velho tem o
   módulo carregado na memória, e trocar arquivo embaixo não o atualiza;
2. reiniciar sozinho derrubaria a sessão no meio de uma tarefa sua;
3. atualizar é exatamente o tipo de ação que, se der errado, você precisa poder
   identificar e desfazer — daí o backup em `storage/atualizacao/backup-<data>/`
   e a resposta dizendo como voltar.

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

## Números reais

| Caminho | Bytes | Arquivos tocados |
|---|---|---|
| zip inteiro (`atualizar.bat` antigo) | ~3,5 MB | 464 |
| delta (só o manifesto) | ~56 KB | 0 |
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
