# JARVIS 0.60.9 — o atualizador que mostra o que está fazendo

Você ficou olhando um cursor piscando:

```
Ficam intocados: .env, storage, .venv e node_modules.
_
```

E nada. Não dava para saber se estava baixando, travado ou morto — e a vontade
era fechar a janela no meio, que é a pior hora possível para fechar.

## O que mudou

O `atualizar.bat` agora chama um auxiliar (`atualizar-baixar.ps1`) que mostra,
em tempo real:

```
  Baixando a versao nova do GitHub...
  de ~3,2 MB (estimado)

  ~ 42%    1,4 MB   820,5 KB/s   faltam 0:03
```

E depois:

```
  pronto:   3,2 MB em 0:04   (812,4 KB/s)

  Extraindo o zip...
  380 arquivo(s) extraido(s) em 0:01.

  Copiando 380 arquivo(s) para D:\JARVIS
  Ficam intocados: .env, storage, .venv e node_modules e .git

  64%   243 de 380 arquivos  0:06
```

No fim, uma linha só, com o total:

```
  Tudo pronto em 0:12: 3,2 MB baixados, 380 arquivos copiados.
```

O título da janela também acompanha (`JARVIS - baixando 42%`), então dá para ver
o andamento sem trazer a janela para frente.

## A parte honesta sobre a porcentagem

O GitHub **não informa o tamanho** do zip (ele monta o arquivo na hora e manda
em streaming, sem `Content-Length`). Então a porcentagem do download é:

1. **exata**, quando o servidor informar o tamanho;
2. **estimada** — marcada com `~` — usando o tamanho do último download
   bem-sucedido, guardado em `%LOCALAPPDATA%\JARVIS\jarvis-zip-bytes.txt`;
3. na primeiríssima vez, sem referência, a tela mostra MB baixados, velocidade e
   tempo decorrido (dá para ver que está vivo) e avisa que a porcentagem aparece
   na próxima.

A porcentagem da **cópia** é sempre exata: são `X de Y arquivos`, contados antes
de começar.

## Também nesta versão

- A cópia deixou de depender do `robocopy` e passou a ser feita arquivo por
  arquivo, para poder contar o progresso. Arquivo em uso ganha uma segunda
  tentativa antes de virar falha.
- Se o problema for `atualizar.bat` em execução (ele não pode ser sobrescrito
  enquanto roda), isso **não** conta como falha: o próprio `.bat` se atualiza na
  atualização seguinte, e o JARVIS avisa em vez de gritar erro.
- Falha de verdade mostra o nome dos arquivos que ficaram para trás e mantém
  tudo o que já estava na pasta — nada é apagado.
- Se o auxiliar for apagado da pasta, o `.bat` ainda atualiza pela barra do
  próprio PowerShell (mais lenta, mas funciona) e avisa que o auxiliar sumiu.
- O zip e a pasta temporária são removidos ao final, mesmo quando dá erro.

## Testes

- `server/tests/test_atualizador.py` → **13**: o auxiliar existe, é ASCII puro
  (console com `chcp 65001` embaralha acento), **não tem erro de sintaxe
  PowerShell** (analisado pelo parser `tree_sitter_powershell` quando instalado),
  usa streaming em vez de `Invoke-WebRequest`, trata zip sem tamanho, nunca
  copia por cima de `.env`/`storage`/`.venv`/`node_modules`/`.git`, devolve 0 ou
  1, e — no `.bat` — todo `goto` tem rótulo.
- `pytest server/tests` → **2.709 passed**.
