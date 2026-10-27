# JARVIS 0.60.1 — o banner mostra o celular e o console para de avisar

Correção pequena, de duas coisas que só apareceram na máquina de verdade.

## 1. O banner agora diz se a camada do celular está ligada

Na 0.60.0 eu mandei procurar `celular=ligado` na primeira linha do terminal — e
essa palavra não existia ali. Agora existe:

```text
JARVIS modo host: token em storage/host-token.txt -> kF_9…StMI
(rede=ligada, instalar=desligado, root=desligado, pc=desligado,
 celular=ligado, dono=desligado)
```

Serve para o teste mais rápido de todos: se você acrescentou
`JARVIS_HOST_CELULAR=1` no `.env` e reiniciou, o banner confirma em uma linha. Se
continuar `desligado`, o `.env` não foi salvo ou a API não reiniciou.

## 2. O console para de cuspir `SyntaxWarning`

Ao subir a API apareciam três avisos:

```text
server\drive_setup.py:21: SyntaxWarning: "\S" is an invalid escape sequence
server\drive_setup.py:159: SyntaxWarning: "\M" is an invalid escape sequence
server\drive_setup.py:417: SyntaxWarning: "\D" is an invalid escape sequence
```

Eram docstrings com caminho do Windows escritos como texto normal
(`HKCU\Software\Google\DriveFS`, `G:\Meu Drive`,
`...\Drive File Stream\110.0.3.0`). Nada quebrava — o Python só avisava que, numa
versão futura, isso vira erro. As três viraram strings cruas (`r"""`).

A suíte agora tem um teste que percorre **todos** os arquivos de `server/`,
compila cada um com `SyntaxWarning` e `DeprecationWarning` tratados como erro e
falha se aparecer qualquer escape inválido. É o tipo de coisa que não volta.

## Como atualizar

Duplo clique em **`atualizar.bat`** — ele já sabe que a sua instalação é por zip,
baixa a versão nova e copia por cima sem tocar em `.env`, `storage`, `.venv` e
`node_modules`.

Depois, feche a API (**Ctrl+C**) e suba de novo:

```bat
.venv\Scripts\python iniciar.py
```

Confira:

```text
http://127.0.0.1:8000/api/health   →  {"version": "0.60.1", "skills": 288}
```

## Testes

- `pytest server/tests` → **2.650 passed** (2 novos: banner e escapes).
- `vitest` 117, `tsc` limpo, build embutido ok.

### Arquivos

- `server/app.py` — `celular=…` no banner.
- `server/drive_setup.py` — três docstrings viraram `r"""`.
- `server/tests/test_celular.py` — os dois testes novos.
