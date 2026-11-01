# JARVIS 0.66.0 — a tela que você viu: “não é um repositório git” e “concurrently não existe”

Você rodou três comandos e dois falharam:

```text
D:\JARVIS>git pull
fatal: not a git repository (or any of the parent directories): .git

D:\JARVIS>npm run dev
'concurrently' não é reconhecido como um comando interno
```

**Nada disso é o JARVIS quebrado.** São dois fatos sobre a pasta:

| mensagem | o que é, de verdade |
|---|---|
| `not a git repository` | a pasta foi extraída do **zip**; não existe `.git` para o `git pull` usar |
| `concurrently não é reconhecido` | falta `node_modules` — o `npm install` nunca rodou ali (e a versão que está na pasta é a **0.62.6**, três versões atrás) |

O que faltava era o JARVIS ter um caminho que **não precise de Node nem de Git**.
Ele já tinha (`iniciar.py` serve a API junto com a interface compilada em
`web-dist/`), mas nada na tela dizia isso — e o erro do Windows é o oposto de uma
instrução.

## 1. `iniciar-jarvis.bat` — duplo clique e pronto

Um atalho que faz o que falta, **dizendo cada passo**:

```text
  JARVIS - iniciar
  ----------------------------------------------------------------
  Esta janela faz o que falta e diz o que esta fazendo:
    1. cria o ambiente Python (.venv), se ainda nao existir
    2. instala as bibliotecas, se faltarem
    3. sobe a API com a interface e abre o navegador

  Nao precisa de Node, nem de npm install, nem de Git.

  [1/3] Criando o ambiente Python em .venv (uma vez so, cerca de 1 minuto)...
        pronto.
  [2/3] Instalando as bibliotecas Python (so na primeira vez).
        O pip mostra o progresso abaixo. Pode levar de 2 a 5 minutos.
  [3/3] Subindo o JARVIS. O navegador abre sozinho quando a API responder.
```

Três decisões dentro dele:

- **o navegador abre depois da API responder**, não antes. Abrir na hora mostra
  “não foi possível acessar” e o usuário conclui que quebrou. A espera é um
  PowerShell escondido batendo em `/api/health` a cada meio segundo;
- **cada etapa imprime `[1/3]`, `[2/3]`, `[3/3]`** — nada de janela parada em
  cursor piscando;
- **não chama git, não roda `npm install`, não pede administrador.** Instalar
  140 MB de `node_modules` para *usar* o JARVIS seria desperdício.

Erros têm saída própria: sem Python, manda instalar com “Add python.exe to PATH”;
se o `pip` falhar, aponta as duas causas comuns (internet, Visual C++ 14.0); se
faltar `web-dist`, avisa que a API sobe mas a tela não.

## 2. `npm run dev` deixou de cuspir o erro cru

`dev` agora chama `scripts/dev.mjs`, que confere antes de falhar:

```text
  O JARVIS nao esta quebrado: falta a pasta node_modules.
  Ela vem do "npm install" (cerca de 140 MB, uma vez so). Versao desta pasta: 0.66.0.

  Opcao 1 - nao instalar nada e usar o JARVIS agora:
    .venv\Scripts\python.exe iniciar.py
    (ou clique duas vezes em iniciar-jarvis.bat, se existir aqui)
    A interface compilada esta em web-dist\ e sobe junto com a API.

  Opcao 2 - trabalhar no codigo da interface (precisa do Node):
    npm install
    npm run dev
```

Ele **não instala nada sozinho** — baixar 140 MB sem pedir não é atalho, é
surpresa. Com `node_modules` presente, roda o `concurrently` como sempre.

## 3. Atualizar pasta que veio do zip

`atualizar.bat` já sabia fazer isso: detecta que não há `.git`, baixa o zip do
ramo com **porcentagem, MB, velocidade e tempo**, e copia por cima preservando
`.env`, `storage`, `.venv` e `node_modules`. O que mudou é a última tela — agora
ela manda rodar `iniciar-jarvis.bat` em vez de só o `python iniciar.py`, e diz em
voz alta que Node não é necessário para usar.

## 4. `npm run checar` fala a mesma língua

As mensagens de conserto do verificador foram atualizadas: quando falta
`node_modules` ou `.env`, ele lembra que o atalho existe e que **a chave de IA é
opcional** — o JARVIS sobe sem ela, só fica sem as funções que chamam modelo.

## Correção de um número que eu publiquei errado

O `NOVO-0.65.0.md` dizia **2.970 passed**. Esse era o número de testes
*coletados*: o `pytest.ini` já traz `-q` e eu passei outro `-q` na linha de
comando, o que esconde o resumo (`-qq`). O número certo, agora medido com o
resumo visível: **2.954 passed, 7 skipped** na 0.65.0. O arquivo foi corrigido.

## Testes

- `pytest server/tests` → **2.967 passed, 7 skipped** (`test_iniciar.py`: 13).
- Os 13 travam: o atalho existir, ser **ASCII puro** (o console do 1607 com
  `chcp 65001` embaralha acento), estar em **CRLF** (o Notepad antigo amassa LF),
  todo `goto` ter rótulo, **nenhum comando git/npm** executado por ele, o
  `iniciar.py` do `.venv` ser o que sobe, os três `[n/3]` aparecerem, nenhum
  “Ctrl+C” pedido, a espera pela API antes de abrir o navegador, `pause` para ler
  erro, o `package.json` apontar `dev` para o script novo, a mensagem citar a
  versão da pasta — e o script **não** instalar nada quando `node_modules` falta.
- `vitest` → 124, `tsc -b` limpo, build embutido ok.
- Skills: **304** (nenhuma nova nesta versão — é conserto de caminho, não recurso).
