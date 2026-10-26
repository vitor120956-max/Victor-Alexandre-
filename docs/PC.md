# PC — abrir programa e usar o cmd sem entregar o shell

A pergunta que abriu esta camada: *“se eu pedir para ele abrir um programa ou usar
meu PowerShell ou o cmd, ele consegue?”*

**Consegue — do jeito seguro.** E “do jeito seguro” aqui não é detalhe: é o que
separa um assistente de um acidente.

## O que ele faz

| Você pede | Ele faz |
|---|---|
| `abre o bloco de notas` · `abre a calculadora` · `abre o paint` | abre o programa da **lista fechada** |
| `abre o arquivo contrato.pdf` | abre o documento no programa padrão do Windows |
| `qual é o meu ip` · `roda o ipconfig` | roda o comando de leitura e mostra a saída |
| `quanto tem de espaço em disco` · `que dia é hoje` | idem, com o comando próprio |
| `quais programas você abre` | mostra as duas listas |

### Programas (lista fechada)

`notepad` (bloco de notas), `calc` (calculadora), `mspaint` (paint), `explorer`,
`cmd`, `powershell`, `taskmgr`, `control`, `charmap`, `magnify`.

O nome vem da lista — **não existe caminho livre, nem argumento**. `abre o
notepad com o arquivo X` não é uma coisa que esta camada aceite.

### Comandos (lista fechada, só leitura)

| Nome | Roda | Devolve |
|---|---|---|
| `ip` | `ipconfig` | endereços de rede |
| `ip-tudo` | `ipconfig /all` | MAC, DNS, DHCP |
| `sistema` | `systeminfo` | informações do sistema |
| `processos` | `tasklist` | processos em execução |
| `usuarios` | `query user` | sessões abertas |
| `versao` | `cmd /c ver` | versão do Windows |
| `disco` | PowerShell fixo com `Get-PSDrive` | usado e livre por unidade |
| `data` | PowerShell fixo com `Get-Date` | data e hora do PC |
| `boot` | PowerShell fixo com `CimInstance` | quando o PC foi ligado |

O comando é **escolhido por nome**, nunca digitado. Isso é o ponto: não há campo
livre por onde entrar `; rm -rf`, `|`, `>` ou `&&`. A linha que executa é uma
constante do código.

Todas as execuções usam lista de argumentos com `shell=False` e teto de 25
segundos.

## O que ele **não** faz

1. **Shell livre.** Nenhuma skill aceita “digite o comando”. Um agente com shell
   aberto pode apagar o disco por causa de uma frase ambígua — e o pedido “usa o
   PowerShell” não precisa disso para ser atendido: 90% do uso real é consulta,
   e consulta está na lista.
2. **Rodar `.exe`, `.bat`, `.ps1`, `.lnk` ou `.url`.** `pc.abrir-arquivo` recusa
   esses formatos de propósito. Instalar programa é `sistema.executar`, com
   allowlist, token e `JARVIS_HOST_INSTALAR=1`.
3. **Mexer fora das pastas do usuário.** Abrir arquivo só vale dentro de
   `storage/`, `Downloads`, `Documentos`, `Área de trabalho` e `OneDrive`.
4. **Funcionar no Linux/macOS.** A camada é Windows (`ctypes`/`os.startfile`); em
   outro sistema ela recusa e diz o motivo, em vez de falhar de um jeito estranho.

## Como ligar

Desligada por padrão, como todas as camadas que tocam a máquina:

```bat
cd /d D:\JARVIS
set JARVIS_HOST_PC=1
.venv\Scripts\python iniciar.py
```

Ao subir, o terminal mostra:

```text
JARVIS modo host: token em storage/host-token.txt -> ab12…cd34 (rede=desligada, instalar=desligado, root=desligado, pc=ligado)
```

E cada abertura **pede confirmação** na tela antes de acontecer (`requires
confirmation`), com os parâmetros à mostra — igual às skills que gravam arquivo.

## Por que não existe “executar qualquer comando”

Porque o custo de errar é assimétrico. Abrir o bloco de notas errado custa nada;
rodar `format C:` errado custa o PC. As três camadas que já existiam escolheram o
mesmo caminho:

- `sistema.executar` — instalador de allowlist, hash, token, `JARVIS_HOST_INSTALAR=1`;
- `repos.executar` — interpretador de lista fechada, dentro de um repositório baixado;
- `estacao_runtime` — ferramentas fixas com política `allow/ask/deny` e recibo.

`pc.*` segue a mesma regra: **catálogo, confirmação, recusa do que não está na
lista**.

## Onde ficam os arquivos

| Peça | Caminho |
|---|---|
| listas, abertura e execução | `server/pc.py` |
| skills | `pc.programas`, `pc.abrir-programa`, `pc.abrir-arquivo`, `pc.comando` |
| testes | `server/tests/test_pc.py` (17, com abertura e execução dublês) |

Os testes **não abrem programa nenhum** e **não rodam comando nenhum**: a função
de abrir e a de executar são substituídas por dublês. O que se verifica é o que
importa — apelido resolvido, nome fora da lista recusado, extensão executável
recusada, caminho fora das pastas recusado, saída cortada no teto, código de erro
preservado e a variável de ambiente desligando tudo.
