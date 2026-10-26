# 0.54.0 — ele abre programa e usa o cmd? Sim, sem entregar o shell

## 1. A resposta curta

**Sim, consegue** — abrir programa, abrir arquivo e rodar comando de leitura no
cmd/PowerShell. **O que ele não faz é receber linha de comando livre.** Essa é a
decisão de projeto, e é a razão de você poder deixar isso ligado sem medo.

| O que você pede | O que acontece |
|---|---|
| `abre o bloco de notas` | abre o notepad |
| `abre a calculadora` · `abre o paint` · `abre o explorer` | abre o programa |
| `abre o cmd` · `abre o powershell` | abre a janela (é você quem digita lá) |
| `abre o arquivo contrato.pdf` | abre no programa padrão do Windows |
| `qual é o meu ip` | roda `ipconfig` e mostra a saída |
| `quanto tem de espaço em disco` | roda a consulta de disco |
| `quais programas você abre` | mostra as duas listas |

## 2. As duas listas fechadas

**Programas:** bloco de notas, calculadora, paint, explorer, cmd, powershell,
gerenciador de tarefas, painel de controle, mapa de caracteres, lupa.

**Comandos (só leitura):** `ip`, `ip-tudo`, `sistema`, `processos`, `usuarios`,
`versao`, `disco`, `data`, `boot`.

O nome vem da lista — **nunca a linha**. Não existe campo por onde entrar `; rm
-rf`, `|`, `>` ou `&&`. O comando que roda é uma constante do código, com
`shell=False` e teto de 25 segundos.

## 3. O que ele recusa, de propósito

- **shell livre** (digitar comando): não existe campo para isso em nenhuma skill;
- **`.exe`, `.bat`, `.cmd`, `.ps1`, `.vbs`, `.msi`, `.lnk`** na abertura de
  arquivo — abrir isso é rodar programa, e instalar tem caminho próprio
  (`sistema.executar`, com allowlist, token e `JARVIS_HOST_INSTALAR=1`);
- **arquivo fora de** `storage\`, `Downloads`, `Documentos`, `Área de trabalho`
  e `OneDrive`;
- **fora do Windows**: a camada usa `ctypes`/`os.startfile`; em Linux/macOS ela
  responde o motivo em vez de falhar estranho.

## 4. Como ligar no seu PC

```bat
cd /d D:\JARVIS
git pull

set JARVIS_HOST_PC=1
.venv\Scripts\python iniciar.py
```

O terminal confirma na subida:

```text
JARVIS modo host: token em storage/host-token.txt -> ab12…cd34
(rede=desligada, instalar=desligado, root=desligado, pc=ligado)
```

Sem `JARVIS_HOST_PC=1`, ele responde:

```text
A camada do PC está desligada. Suba a API com JARVIS_HOST_PC=1
(é o mesmo cuidado de JARVIS_HOST_REDE e JARVIS_HOST_INSTALAR).
```

Toda abertura **pede confirmação** antes de acontecer, com o parâmetro à mostra.

## 5. Por que não abrir o shell inteiro

Porque o custo de errar é assimétrico: abrir o bloco de notas errado custa nada;
rodar `format C:` errado custa o PC. As outras três camadas que tocam a máquina já
seguem a mesma regra — `sistema.executar` (instalador com hash e token),
`repos.executar` (interpretador de lista fechada) e `estacao_runtime` (ferramentas
fixas com `allow/ask/deny`). `pc.*` entra na mesma linha: **catálogo,
confirmação, recusa do que não está na lista**.

Se um dia precisar de um comando que não está na lista, o caminho é acrescentar
na tabela `COMANDOS` de `server/pc.py` — uma linha revisada, não um campo aberto.

## 6. Números

- **264 skills** (4 novas: `pc.programas`, `pc.abrir-programa`, `pc.abrir-arquivo`,
  `pc.comando`).
- **2.452 testes** Python + **110** da interface.
- Testado com dublês: nenhum teste abre programa ou roda comando de verdade.

Conferir: `http://127.0.0.1:8000/api/health` → `"version": "0.54.0"` e
`"skills": 264`.

Detalhes em `docs/PC.md`.
