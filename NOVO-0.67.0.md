# JARVIS 0.67.0 — o `>` do prompt zerou os arquivos

A tela que você colou tem a resposta inteira dentro dela:

```text
D:\JARVIS>D:\JARVIS>atualizar.bat
'D:\JARVIS' não é reconhecido como um comando interno ou externo
```

Repare no **prompt duplicado**: `D:\JARVIS>` apareceu duas vezes. Isso quer dizer
que o bloco copiado trouxe o prompt junto com o comando. No `cmd.exe` o `>` não é
enfeite — ele **redireciona a saída para um arquivo**.

| você colou | o cmd entendeu | o que aconteceu |
|---|---|---|
| `D:\JARVIS>atualizar.bat` | comando `D:\JARVIS`, saída para o arquivo `atualizar.bat` | erro `'D:\JARVIS' não é reconhecido` **e `atualizar.bat` ficou com 0 byte** |
| `atualizar.bat` | executa o arquivo | funciona |

Por isso, na linha seguinte, `atualizar.bat` “rodou” e voltou ao prompt sem fazer
nada: **o arquivo estava vazio.** Mesma coisa com `iniciar-jarvis.bat`.

Não é o JARVIS quebrado: foi o `>` do prompt comendo o conteúdo dos `.bat`.

## O conserto

**`consertar-arquivos.bat`** (novo) — duplo clique no Explorador:

1. mostra `ok`, `FALTA` ou `VAZIO` com o tamanho em **bytes** de cada arquivo
   principal (`iniciar-jarvis.bat`, `atualizar.bat`, `consertar-arquivos.bat`,
   `iniciar.py`, `package.json`, `web-dist\index.html`);
2. se algo estiver faltando ou com menos de 100 bytes, baixa o zip do ramo e
   copia **só o que falta** — nunca apaga nada seu: `.env`, `storage`, `.venv`,
   `node_modules` e `.git` ficam de fora da cópia;
3. confere **de novo** depois de copiar, e se ainda estiver vazio diz a causa
   (pendrive protegido contra escrita, antivírus bloqueando `.bat`) em vez de
   dizer “pronto”.

E ele abre explicando o erro, para não acontecer outra vez:

```text
  No prompt do Windows, o sinal ">" nao e enfeite: ele manda a saida
  do comando para um arquivo. Digitar
      D:\JARVIS>atualizar.bat
  faz o Windows criar - ou ZERAR - um arquivo chamado atualizar.bat.
  O arquivo continua ali, com 0 byte, e "nao faz nada" quando roda.

  Regra: copiar so o comando. O "D:\JARVIS>" e do Windows, nao seu.
```

## `npm run checar` agora acusa isso

Item novo **Atalhos da pasta**: se `iniciar-jarvis.bat`, `atualizar.bat` ou
`iniciar.py` estiverem ausentes ou com 0 byte, ele falha com o conserto na linha
de baixo:

```text
  FALTA  Atalhos da pasta   atualizar.bat com 0 byte
         → Rode consertar-arquivos.bat. Causa comum: copiar o "D:\JARVIS>" junto
           com o comando — o ">" zera o arquivo.
```

## Por que o pacote não consegue se proteger sozinho

Um `.bat` zerado não tem como se reescrever: ele **é** o arquivo que sumiu. Por
isso a proteção é em três camadas:

| camada | onde | o que faz |
|---|---|---|
| prevenção | `docs/PENDRIVE.md` §15 + o texto dentro do atalho | ensina que o `>` é redirecionamento |
| detecção | `npm run checar` | acusa `0 byte` antes de você perder tempo |
| conserto | `consertar-arquivos.bat` | baixa e restaura só o que falta |

## Testes

- `pytest server/tests` → **2.973 passed, 7 skipped** (`test_iniciar.py`: 19).
- Os 6 novos travam: `consertar-arquivos.bat` existe em ASCII puro e CRLF; explica
  a armadilha com as palavras `ZERAR` e `0 byte`; detecta arquivo vazio antes de
  baixar (`LSS 100` + `VAZIO`/`FALTA`); a cópia preserva `.env`, `storage`,
  `.venv`, `node_modules` e `.git` e só apaga a pasta temporária; confere **depois**
  de copiar (tem `:nao_deu`); e **nenhum `.bat` da raiz pode ter menos de 100
  bytes** — o teste que impede um arquivo zerado de entrar no repositório.
- `vitest` → 124, `tsc -b` limpo, build embutido ok.
- Skills: **304** (nenhuma nova — é conserto de caminho).
