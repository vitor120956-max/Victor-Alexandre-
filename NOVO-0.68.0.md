# JARVIS 0.68.0 — “já está em uso” é boa notícia (e agora diz de qual versão)

Você viu a mensagem do próprio JARVIS:

```text
Já existe uma API respondendo em http://127.0.0.1:8000
Não precisa subir outra: abra o endereço no navegador.
```

**Isso não é erro.** É o atalho encontrando um JARVIS já rodando e se recusando a
subir um segundo na mesma porta. Acontece quando a janela anterior ficou aberta
(minimizada, ou aberta por `npm run dev` em outro terminal).

Mas a mensagem tinha dois buracos que custam tempo:

1. **não dizia qual versão está no ar.** Se você acabou de atualizar a pasta e a
   janela antiga continua aberta, o navegador mostra o código **antigo** — e a
   conclusão natural é “a atualização não pegou”;
2. **não dizia como fechar a janela antiga** quando ela sumiu da tela.

## O que a mesma situação mostra agora

```text
  Já existe um JARVIS na porta 8000 — mas é de outra versão
  Rodando: 0.62.6. Esta pasta: 0.68.0. O navegador mostraria o código antigo
  e pareceria que a atualização não pegou.

    - Feche a janela antiga no X (procure “JARVIS” na barra de tarefas)
    - Se a janela sumiu: duplo clique em parar-jarvis.bat
    - Depois rode iniciar-jarvis.bat de novo
```

## Os quatro estados da porta

| estado | quando | o que acontece |
|---|---|---|
| **livre** | ninguém escuta | sobe normal |
| **mesma versão** | o `/api/health` diz o mesmo número do `package.json` | só manda abrir o navegador — nada de subir um segundo |
| **outra versão** | números diferentes | explica as duas versões e manda fechar a antiga |
| **outro programa** | a porta responde, mas não é `jarvis-python-api` | **não toca** no processo e sugere `--porta 8001` |

A comparação é de **texto exato**: `0.6.8` não é `0.68.0`, e `0.68.0` não é
`0.68.0-rc1`. Tem teste para os três casos.

## `parar-jarvis.bat` — para quando a janela sumiu

Duplo clique. O que ele faz, nesta ordem:

1. pergunta ao `/api/health` **quem** está na porta;
2. **só se a resposta for do próprio JARVIS**, procura o PID com `netstat -ano` e
   encerra com `taskkill /PID`;
3. espera até 8 segundos e confirma que a porta ficou livre;
4. se não conseguir, **não insiste**: mostra o caminho manual (Gerenciador de
   Tarefas → aba Detalhes → `python` → Finalizar tarefa).

A ordem é de propósito: **identidade antes de PID**. Uma porta ocupada por outro
programa nunca vira alvo — nem por engano, nem por pressa.

## Onde isso mora

| arquivo | papel |
|---|---|
| `server/instancia.py` | lê o `/api/health`, compara versões, acha o PID e encerra só o JARVIS |
| `iniciar.py` | deixou de ter a lógica duplicada; usa `server.instancia` |
| `parar-jarvis.bat` | duplo clique, com confirmação `[s/N]` |
| `consertar-arquivos.bat` | passou a conferir o `.bat` novo também |
| `npm run checar` | item **Atalhos da pasta** agora inclui `parar-jarvis.bat` |

## Por que não virou skill

`maquina.*` lê processo sem efeito colateral, e assim continua. Encerrar a própria
API por skill criaria um jeito de derrubar a interface **a partir da interface**.
A decisão fica com quem está na frente da máquina: duplo clique, confirmação
`s/N`, identidade conferida antes.

## Testes

- `pytest server/tests` → **3.001 passed, 7 skipped** (`test_instancia.py`: 28).
- Os 28 travam: os quatro estados sempre com “o que fazer”; comparação de versão
  exata (`0.6.8`, `0.68.0-rc1`, versão ausente); `netstat` pegando só `LISTENING`
  e sem confundir `8000` com `80000` nem `800`; vários PIDs na mesma porta;
  `encerrar()` recusando quando não há JARVIS **ou quando quem responde não é
  ele** (os testes falham se o PID for sequer procurado nesses casos); o
  encerramento que confirma a porta livre; o aviso quando ela continua
  respondendo; `versao_da_pasta` com `package.json` quebrado; o `.bat` em ASCII
  puro/CRLF com `goto` consistente, sem git nem npm, com plano B manual; e o
  `iniciar.py` sem voltar a ter `"jarvis-python-api"` escrito dentro dele.
- `vitest` → 124, `tsc -b` limpo, build embutido ok.
- Skills: **304** — nenhuma nova. Isto é conserto de caminho, não recurso.
