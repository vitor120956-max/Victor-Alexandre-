# JARVIS no pendrive

Este guia responde a duas perguntas: **“posso instalar o JARVIS num pendrive?”** e **“o que ele criar vai para o pendrive?”**.

Resposta curta: **sim para as duas**, desde que o projeto rode de dentro do pendrive. O JARVIS calcula todos os caminhos a partir da pasta onde está o `server/` — não existe caminho fixo no código. Medido: uma cópia de **16 MB** (sem `.venv`, `node_modules` e `.git`) subiu, criou `storage/`, gravou o token e escreveu um documento em `<pendrive>/storage/user-files/notas/ideia.md`, sem tocar no projeto original.

O que **não** é possível: transformar o pendrive num sistema operacional. O JARVIS é um programa (Node + Python) que roda numa máquina que tenha esses dois instalados.

---

## 0. Checagem automática — comece por aqui

Um comando responde “o que falta nesta máquina e nesta pasta?”:

```bash
npm run checar
# equivalente: node scripts/checar-pendrive.mjs
```

O script roda **só com Node** — e é de propósito: ele precisa funcionar antes de existir `.venv` ou `node_modules`, que é exatamente quando a dúvida aparece. Saída de exemplo, medida nesta sandbox:

```text
JARVIS — checagem desta pasta
/home/user/Victor-Alexandre-
linux 6.1.158+ · node v22.22.3

  OK       Node.js              v22.22.3 (mínimo v22)
  OK       Python               Python 3.11.2 (do .venv do projeto)
  OK       Bibliotecas Python   fastapi 0.162.0 · pydantic 2.14.1
  OK       Bibliotecas do Node  node_modules presente (vite instalado)
  OK       Arquivo .env         presente
  ATENÇÃO  Chave de IA          vazia — as 8 skills de perfil sem modelo funcionam; distilar.persona e o chat externo não
           → Cole o valor em JARVIS_AI_API_KEY e reinicie a API.
  OK       Endpoint e modelo    https://api.openai.com/v1 · gpt-4o-mini
  OK       Pasta storage        /home/user/Victor-Alexandre-/storage
  OK       Espaço livre         18.94 GB livres de 20.34 GB
  OK       Sistema de arquivos  ext2/3/4 — guarda permissão e link simbólico
  OK       Git                  2.39.5 · repositório presente (evoluir.promover disponível)
  OK       Portas 8000 e 5173   livres

Pronto para rodar. 1 aviso(s). Suba com: npm run dev
```

| Item medido | O que reprova |
|---|---|
| Node.js | versão abaixo de 22 |
| Python | nenhum interpretador 3.11+ encontrado |
| Bibliotecas Python | `fastapi`, `pydantic`, `httpx` ou `python-dotenv` não importam |
| Bibliotecas do Node | `node_modules` ausente |
| Arquivo `.env` | não existe |
| Chave de IA | **aviso** quando vazia: as oito skills de perfil sem modelo funcionam, `distilar.persona` não |
| Espaço livre | menos de 1 GB |
| Sistema de arquivos | **aviso** em exFAT/FAT32; aceita ext4, btrfs, XFS, ZFS, F2FS e NTFS. No Windows a leitura é pelo `Get-Volume` do PowerShell, porque o Node não distingue o tipo de volume |
| Git | **aviso** sem `.git`: a camada `evoluir.*` não promove sem repositório |
| Portas 8000 e 5173 | **aviso** quando ocupadas (pode ser o próprio JARVIS) |

Cada linha `FALTA` vem com o comando que resolve. O código de saída é `0` quando não falta nada obrigatório e `1` quando falta — dá para usar em script. `--json` imprime a mesma coisa em JSON:

```bash
node scripts/checar-pendrive.mjs --json
```

A checagem mede a pasta onde o **script** mora, não o diretório de onde você chamou. Copie o projeto inteiro; rodar o script de fora não ajuda.

## 1. O que a máquina precisa ter

| Programa | Versão mínima | Como conferir (Windows) | Como conferir (Linux/macOS) | Onde obter |
|---|---|---|---|---|
| Node.js | 22 | `node --version` | `node --version` | <https://nodejs.org> (LTS) |
| npm | vem com o Node | `npm --version` | `npm --version` | junto com o Node |
| Python | 3.11 | `python --version` ou `py --version` | `python3 --version` | <https://www.python.org/downloads/> |
| Git (opcional) | qualquer | `git --version` | `git --version` | <https://git-scm.com> |

No Windows, ao instalar o Python, marque **“Add python.exe to PATH”**. Sem isso o comando `python` não aparece no terminal.

**Se o comando responder “não é reconhecido” ou “command not found”:** o programa não está instalado ou não está no PATH. Instale pelo link acima e **feche e abra o terminal de novo** — o PATH só é relido em processo novo.

### Instalar Node, Python e Git pelo próprio cmd (winget)

O Windows 10 (1809+) e o Windows 11 já trazem o **winget**. Ele instala pelo terminal, sem baixar instalador à mão. Abra o **Prompt de Comando** e comece conferindo se ele existe:

```bat
winget --version
```

Se responder “não é reconhecido”, atualize o **App Installer** pela Microsoft Store — é ele que fornece o `winget`.

Com o winget disponível, os três comandos são:

```bat
winget install --id OpenJS.NodeJS.LTS -e --source winget --accept-package-agreements --accept-source-agreements
winget install --id Python.Python.3.12 -e --source winget --accept-package-agreements --accept-source-agreements
winget install --id Git.Git -e --source winget --accept-package-agreements --accept-source-agreements
```

| Comando | O que instala | Observação |
|---|---|---|
| `OpenJS.NodeJS.LTS` | Node.js LTS + npm | a linha LTS é a 22 ou mais nova; confira depois |
| `Python.Python.3.12` | Python 3.12 + `py` launcher | serve 3.11+; `Python.Python.3.13` também funciona |
| `Git.Git` | Git | opcional; só a camada `evoluir.*` precisa |

Se quiser conferir o identificador antes de instalar, ou se o seu estiver diferente:

```bat
winget search nodejs
winget search python
winget show OpenJS.NodeJS.LTS
```

**Depois de instalar, feche o cmd e abra outro.** O PATH é lido quando o processo nasce: na janela antiga o comando continua “não reconhecido” mesmo com tudo instalado. Confira na janela nova:

```bat
node --version
npm --version
python --version
py --version
git --version
```

Dois tropeços comuns no Windows:

- **`python` abre a Loja.** Isso é o atalho falso da Microsoft Store (alias de execução). Use `py --version` ou desligue o atalho em **Configurações → Aplicativos → Configurações avançadas de aplicativos → Aliases de execução de aplicativo**, desmarcando `python.exe`.
- **winget sem permissão de administrador.** Ele até instala para o usuário em alguns pacotes, mas o normal é abrir o cmd com **Executar como administrador**. No PowerShell, a mesma sintaxe funciona.

Alternativas ao winget, se ele não existir na sua máquina:

| Gerenciador | Comando | Requisito |
|---|---|---|
| Chocolatey | `choco install nodejs-lts python git -y` | instalar o Chocolatey antes, em PowerShell como administrador |
| Scoop | `scoop install nodejs-lts python git` | `scoop` instalado; não exige administrador |
| Instalador oficial | <https://nodejs.org> e <https://www.python.org/downloads/> | marcar “Add python.exe to PATH” |

### Quando o `winget` também não existe

É o caso mais comum em Windows antigo, em máquina reformatada ou em instalação sem a Microsoft Store. Sem winget, o caminho por comando continua existindo, mas cada peça vem de uma fonte diferente:

| Ferramenta | De onde vem | Dá para fazer só por comando? |
|---|---|---|
| Node.js | `nodejs.org` | **sim** — a versão é descoberta na hora pelo índice oficial |
| Python | `python.org` | **não com segurança** — o site não publica um índice estável de “última versão”; clique no link |
| Git | GitHub (`git-for-windows/git`) | **sim** — o endereço do instalador é fixo por versão |
| Projeto JARVIS | GitHub (arquivo ZIP) | **sim** — 2,3 MB, sem precisar de Git |

#### Node.js por comando (PowerShell)

Abra o **PowerShell** (Win + R, digite `powershell`, Enter) e cole o bloco inteiro:

```powershell
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
$indice = Invoke-RestMethod 'https://nodejs.org/dist/index.json'
$versao = ($indice | Where-Object { $_.lts -ne $false } | Select-Object -First 1).version
$url = "https://nodejs.org/dist/$versao/node-$versao-x64.msi"
$destino = Join-Path $env:TEMP 'node-lts.msi'
Invoke-WebRequest -Uri $url -OutFile $destino
Start-Process msiexec.exe -ArgumentList "/i `"$destino`" /qn /norestart" -Wait
Write-Host "Node $versao instalado."
```

O bloco não tem versão escrita à mão: ele pergunta ao `nodejs.org` qual é a LTS atual e baixa o `.msi` correspondente. O instalador roda em silêncio (`/qn`).

#### Git por comando (PowerShell)

```powershell
$url = 'https://github.com/git-for-windows/git/releases/download/v2.56.0.windows.3/Git-2.56.0.3-64-bit.exe'
$destino = Join-Path $env:TEMP 'git-setup.exe'
Invoke-WebRequest -Uri $url -OutFile $destino
Start-Process $destino -ArgumentList '/VERYSILENT /NORESTART' -Wait
Write-Host 'Git instalado.'
```

Original **66,8 MB**, conferido no GitHub em 25/10/2026 (`v2.56.0.windows.3`). Se a versão tiver mudado, a página <https://github.com/git-for-windows/git/releases/latest> mostra o instalador atual com o mesmo formato de nome.

#### Python: clique é mais seguro que comando

Não existe um endereço fixo do tipo `python-latest.exe`; o nome do arquivo carrega a versão. Vá em <https://www.python.org/downloads/> e clique no botão amarelo **Download Python 3.x.y**. No primeiro ecrã do instalador:

- marque **Add python.exe to PATH** (é a caixa de baixo; sem ela o comando não aparece no cmd);
- escolha **Install Now**.

Se preferir por comando e souber a versão exata (por exemplo 3.12.10):

```powershell
$versao = '3.12.10'
$url = "https://www.python.org/ftp/python/$versao/python-$versao-amd64.exe"
$destino = Join-Path $env:TEMP 'python-setup.exe'
Invoke-WebRequest -Uri $url -OutFile $destino
Start-Process $destino -ArgumentList '/quiet InstallAllUsers=0 PrependPath=1 Include_launcher=1' -Wait
```

`PrependPath=1` faz o papel da caixa “Add python.exe to PATH”.

#### O projeto sem Git: arquivo ZIP

O GitHub entrega o repositório em ZIP, sem precisar de Git instalado:

<https://codeload.github.com/vitor120956-max/Victor-Alexandre-/zip/refs/heads/arena/f26cfa7a-victor-alexandre>

Medido: **2.327.810 bytes (2,3 MB)**, **272 arquivos**, pasta de raiz `Victor-Alexandre--arena-f26cfa7a-victor-alexandre/`. O ZIP **não traz `.git`**, então a camada `evoluir.*` fica indisponível — tudo o mais funciona.

Ao extrair, renomeie a pasta para `JARVIS`: o nome original tem hífen duplo e o nome da branch, o que atrapalha na hora de digitar o caminho.

### Windows 10 antigo (build 14393 / versão 1607)

Algumas máquinas têm Windows 10 sem nenhuma das ferramentas modernas. Vale conferir a build antes de seguir:

```bat
winver
```

| Build | Versão | Tem `winget`? | Tem `tar.exe`? | O que usar |
|---|---|---|---|---|
| 14393 | 1607 | **não** (só 1809+) | **não** (só 1803+) | PowerShell + `Expand-Archive` |
| 17134 | 1803 | não | sim | PowerShell ou `tar -xf` |
| 17763 | 1809 | sim | sim | `winget` |

Numa build 14393, os comandos que funcionam são os de PowerShell abaixo — `winget` e `tar` respondem “não é reconhecido” e não há como instalar o `winget` sem atualizar o Windows.

```powershell
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
$zip = "$env:TEMP\jarvis.zip"
$temp = "$env:TEMP\jarvis-extraido"
Invoke-WebRequest -Uri "https://codeload.github.com/vitor120956-max/Victor-Alexandre-/zip/refs/heads/arena/f26cfa7a-victor-alexandre" -OutFile $zip
if (Test-Path $temp) { Remove-Item $temp -Recurse -Force }
Expand-Archive -Path $zip -DestinationPath $temp -Force
$pasta = Get-ChildItem $temp -Directory | Select-Object -First 1
if (Test-Path "D:\JARVIS") {
  Write-Host "ATENCAO: D:\JARVIS ja existe. Renomeie ou apague e rode de novo."
} else {
  Move-Item $pasta.FullName "D:\JARVIS"
  Write-Host "Pronto: D:\JARVIS"
}
```

Troque `D:` pela letra do seu pendrive. A linha de TLS 1.2 é obrigatória nessa build: sem ela, o `Invoke-WebRequest` falha com erro de conexão no GitHub.

Confira o sistema de arquivos do pendrive — em FAT32 o projeto roda, mas a camada de sistema não consegue marcar arquivo como executável:

```powershell
Get-Volume -DriveLetter D | Select-Object DriveLetter,FileSystem,SizeRemaining,Size
```

### Python 3.15 e as dependências: nada precisa ser compilado

O `pip` só instala sem compilador se existir **wheel pronta** para a versão do Python. Conferido no PyPI em 25/10/2026 para `cp315`/`win_amd64`:

| Pacote | Wheel para Python 3.15 no Windows |
|---|---|
| `pydantic-core` 2.50.1 | sim |
| `lxml` 6.1.3 (usado por `python-docx` e `python-pptx`) | sim |
| `Pillow` 13.0.0 (usado por `python-pptx`) | sim |
| `watchfiles` 1.3.0 | sim (`cp310-abi3`, vale para 3.15) |
| `httptools` 0.9.0 | sim |
| `websockets` 17.3 | sim |
| `reportlab` 4.5.1 | sim (wheel `py3-none-any`, Python puro) |

Ou seja: `pip install -r requirements-dev.txt` não precisa de Visual Studio Build Tools.

Um pacote ficou de fora dessa tabela de propósito: o **`PyYAML`**. Ele não publica wheel `cp315` para Windows em nenhuma versão recente (conferido em 25/10/2026: 6.0, 6.0.1, 6.0.2, 6.0.2rc1, 6.0.3, 6.0b1 — nenhuma). E ele não é usado pelo JARVIS: entrava só pelo extra `uvicorn[standard]`, que também traz `httptools`, `websockets`, `watchfiles` e `uvloop`. Desde a **0.37.1** o `requirements.txt` pede `uvicorn>=0.34,<1.0` **sem** o extra, então nada compila.

### Quando o `pip install` para em `Microsoft Visual C++ 14.0 or greater is required`

Sintoma no `cmd`, quase sempre no fim de uma instalação que parecia ir bem:

```text
Building wheel for pyyaml ... error
  error: Microsoft Visual C++ 14.0 or greater is required.
error: failed-wheel-build-for-install
```

O que aconteceu: essa dependência não tem wheel pronta para a sua versão do Python, o `pip` baixou o código-fonte e tentou compilar. Sem o compilador da Microsoft, o build falha — e **o `pip` aborta a instalação inteira**, deixando o `.venv` vazio. Não é o seu Windows quebrado, e não é preciso instalar o Visual Studio.

Três saídas, da mais simples para a mais completa:

| Situação | O que fazer |
|---|---|
| Quer só colocar o JARVIS no ar agora | Um comando, sem editar arquivo nenhum: `.venv\Scripts\pip install fastapi uvicorn httpx pydantic python-dotenv python-docx openpyxl python-pptx pypdf reportlab python-multipart` |
| Você baixou o projeto antes da 0.37.1 e quer o `requirements.txt` certo | Cole no `cmd`, dentro de `D:\JARVIS`, o conserto automático abaixo — ele reescreve a linha sem você abrir editor |
| Quer os aceleradores opcionais (parser HTTP em C, `--reload` instantâneo) | `.venv\Scripts\pip install -r requirements-rapido.txt` — é o `requirements.txt` mais `httptools`, `websockets` e `watchfiles`, e nenhum dos três pede compilador |

O conserto automático do `requirements.txt` de uma cópia antiga (2 segundos, não abre editor):

```bat
py -c "import pathlib;p=pathlib.Path('requirements.txt');t=p.read_text(encoding='utf-8');t=t.replace('uvicorn[standard]','uvicorn');p.write_text(t,encoding='utf-8',newline='\r\n');print(t)"
```

Ele troca o texto, **regrava com quebra de linha do Windows** e imprime o resultado. Se aparecer `uvicorn>=0.34,<1.0` no meio da lista, funcionou.

Se você realmente precisar do `uvicorn` completo, o comando avulso é `.venv\Scripts\pip install "uvicorn[standard]"` — mas saiba que hoje ele vai tentar compilar o `PyYAML` e falhar em Python 3.15 no Windows. O JARVIS não usa YAML nem WebSocket, então o `uvicorn` sem o extra atende tudo.

Como saber que deu certo, sem adivinhar:

```bat
.venv\Scripts\pip list
```

A lista precisa ter `fastapi`, `uvicorn`, `pydantic`, `python-docx`, `openpyxl`, `python-pptx`, `pypdf`, `reportlab` e `python-multipart`. Se faltar algum, o `pip install -r requirements.txt` parou no meio por causa de outra dependência — leia a última linha em vermelho, ela nomeia o pacote.

### O Bloco de Notas antigo mostra o arquivo numa linha só

Se você abrir `requirements.txt` ou `.env.example` no **Bloco de Notas** de um Windows 10 antigo (1607 = build 14393, 1709, 1803) e vir tudo grudado numa linha única, como `fastapi>=0.115,<1.0uvicorn[standard]>=0.34,...`, não é o arquivo que está corrompido: **é o Bloco de Notas** que não entende a quebra de linha do Unix (LF). Só a partir do build **17763 (1809)** ele passou a entender.

O perigo é apertar Ctrl+S nesse estado: ele grava tudo amassado numa linha só, e aí o `pip` não consegue mais ler. **Feche o Bloco de Notas sem salvar** (ou clique em não salvar quando ele perguntar).

Desde a **0.37.1** os quatro arquivos que você edita no Windows são gravados em **CRLF**, a quebra de linha do Windows, e o `.gitattributes` impede o git de converter de volta:

| Arquivo | Quebra de linha |
|---|---|
| `requirements.txt` | CRLF |
| `requirements-dev.txt` | CRLF |
| `requirements-rapido.txt` | CRLF |
| `.env.example` | CRLF |

Se o seu `requirements.txt` ainda mostra uma linha só no Bloco de Notas, a cópia é anterior — use o conserto automático da seção anterior, ou simplesmente instale a lista de pacotes na mão e siga em frente. Para conferir a quebra de linha pelo próprio `cmd`, sem abrir editor:

```bat
py -c "print(open('requirements.txt','rb').read().count(b'\r\n'))"
```

Se o número for igual à quantidade de linhas do arquivo (15 no `requirements.txt`), está em CRLF.

### Comandos que **não** funcionam no `cmd` do Windows

Vieram de exemplos Linux e falham com “não é reconhecido como um comando interno”:

| Errado no Windows | Certo no Windows | Por quê |
|---|---|---|
| `python3 --version` | `py --version` ou `python --version` | o executável no Windows é `python.exe`/`py.exe`, não `python3` |
| `.venv/bin/pip install ...` | `.venv\Scripts\pip install ...` | a estrutura do venv é `Scripts`, não `bin` |
| `.venv/bin/python -m uvicorn ...` | `.venv\Scripts\python -m uvicorn ...` | idem |
| `node --version · python --version` | um comando por linha | o `·` era separador da tabela, não faz parte do comando |
| `cd E:\JARVIS` estando em `C:` | `cd /d E:\JARVIS` | sem `/d` o `cd` troca de pasta mas não de unidade |
| `&&` entre comandos no cmd antigo | `&&` funciona no cmd atual; se falhar, rode um por vez | `&&` só existe em `cmd`/PowerShell recentes |

Comando único, uma linha cada:

```bat
node --version
npm --version
py --version
git --version
```

No Linux, o equivalente por distribuição:

```bash
sudo apt install -y nodejs npm python3 python3-venv git     # Debian/Ubuntu
sudo dnf install -y nodejs python3 python3-virtualenv git   # Fedora
```

Depois de qualquer um dos caminhos, o teste é o mesmo comando deste projeto:

```bash
npm run checar
```

Referência do ambiente onde este guia foi testado: `node v22.22.3`, `npm 10.9.8`, `Python 3.11.2`, `git 2.39.5`. Os seus números podem ser diferentes; o que importa é estarem acima do mínimo.

---

## 2. Preparar o pendrive

| Item | Recomendação | Por quê |
|---|---|---|
| Sistema de arquivos | **NTFS** (Windows) ou **ext4** (Linux) | guarda permissão e link simbólico; o `.venv` funciona |
| Alternativa | **exFAT** | funciona para código e documentos, mas não guarda permissão POSIX — `chmod +x` falha |
| Evitar | **FAT32** | limite de 4 GB por arquivo e nenhum link simbólico |
| Espaço livre | **1 GB** no mínimo; 8 GB confortável | dependências ≈ 294 MB e os downloads podem crescer |
| Pasta | uma pasta chamada `JARVIS` na raiz do pendrive | facilita achar e copiar |

---

## 3. Copiar o projeto para o pendrive

### Opção A — com Git (recomendada)

Traz o histórico e permite usar a camada de auto-alteração, que consulta `git status`.

```bash
git clone <url-do-seu-repositorio> /media/SEU_PENDRIVE/JARVIS
```

Windows (PowerShell):

```powershell
git clone <url-do-seu-repositorio> E:\JARVIS
```

### Opção B — arquivo ZIP (sem Git instalado)

Baixe o ZIP do repositório e extraia no pendrive:

<https://codeload.github.com/vitor120956-max/Victor-Alexandre-/zip/refs/heads/arena/f26cfa7a-victor-alexandre>

São **2,3 MB** e 272 arquivos. Ao extrair, **renomeie a pasta para `JARVIS`** — o nome original vem com o nome da branch. O ZIP não traz `.git`: a camada `evoluir.*` fica indisponível, o resto funciona.

### Opção C — cópia simples a partir de uma pasta já baixada

Não copie `.venv`, `node_modules` nem `storage` se quiser começar limpo.

```bash
rsync -a --exclude .venv --exclude node_modules --exclude storage ./ /media/SEU_PENDRIVE/JARVIS/
```

Windows (PowerShell):

```powershell
robocopy . E:\JARVIS /E /XD .venv node_modules storage
```

`robocopy` devolve código 1 a 7 quando copia com sucesso — isso não é erro.

Tamanho medido da cópia sem dependências: **16 MB**.

---

## 4. Instalar as dependências **no pendrive**

O `.venv` e o `node_modules` são específicos de cada máquina. Instale uma vez por computador.

### Windows

```bat
cd /d E:\JARVIS
py -m venv .venv
.venv\Scripts\pip install -r requirements-dev.txt
npm install
```

O `cd /d` é obrigatório quando o cmd está em outra unidade (`C:`) e o projeto está no pendrive (`E:`). Sem `/d`, o comando troca de pasta mas continua na unidade antiga.

Se `py` não existir, use `python`. Se o venv já existir e estiver quebrado, apague a pasta `.venv` e repita.

Se você só quer a API e a interface embutida (sem rodar testes), `requirements.txt` basta e é mais rápido: `.venv\Scripts\pip install -r requirements.txt`. Quer os aceleradores opcionais do uvicorn? `requirements-rapido.txt`. Nenhum dos dois compila nada — detalhes em [§1](#quando-o-pip-install-para-em-microsoft-visual-c-140-or-greater-is-required).

### `npm error ENOENT … C:\Users\SEU_USUARIO\package.json`

Esse erro não é problema do projeto: é **o comando rodando na pasta errada**. Cada janela do cmd nasce em `C:\Users\SEU_USUARIO`, e o npm procura `package.json` sempre na pasta atual.

```text
npm error code ENOENT
npm error path C:\Users\pc\package.json
npm error enoent Could not read package.json
```

Confira onde você está antes de qualquer comando:

```bat
cd
```

A resposta precisa ser `D:\JARVIS`. Se não for:

```bat
cd /d D:\JARVIS
```

Só depois disso `npm install`, `npm run dev` e `npm run checar` funcionam. O `/d` é obrigatório porque `cd D:\JARVIS` sem `/d` troca de pasta mas mantém a unidade `C:`.

### Como saber se o `npm install` terminou de verdade

Contar linhas de `node_modules` serve para ver progresso, mas **não prova que terminou** — dependências opcionais mudam de máquina para máquina. A prova é o `npm ls`:

```bat
cd /d D:\JARVIS
```

```bat
npm ls --depth=0
```

Saída correta: treze pacotes e **nenhuma** linha `UNMET DEPENDENCY`:

```text
jarvis-nucleo-pessoal@0.42.1 D:\JARVIS
+-- @fontsource-variable/manrope@5.3.0
+-- @fontsource/ibm-plex-mono@5.3.0
+-- @types/react-dom@19.3.0
+-- @types/react@19.3.0
+-- @vitejs/plugin-react@4.7.0
+-- concurrently@10.0.6
+-- lucide-react@0.468.0
+-- react-dom@19.3.1
+-- react-router-dom@7.18.4
+-- react@19.3.1
+-- typescript@5.7.3
+-- vite@6.4.5
`-- vitest@5.0.5
```

Se faltar algum, rode `npm install` de novo na pasta certa — ele é **idempotente**: baixa só o que falta e não estraga o que já existe. Nunca é preciso apagar `node_modules` para isso.

Conferência rápida dos quatro que quebram o `npm run dev` se faltarem:

```bat
dir D:\JARVIS\node_modules\vite /b
dir D:\JARVIS\node_modules\esbuild /b
dir D:\JARVIS\node_modules\react /b
dir D:\JARVIS\node_modules\concurrently /b
```

### Duas janelas de cmd: qual está fazendo o quê

Abrir uma janela nova **não interrompe** o que roda na antiga. Se o `npm install` ficou pendurado numa janela e você abriu outra, a instalação continua viva na primeira. Para não rodar dois ao mesmo tempo:

| Situação | O que fazer |
|---|---|
| A janela antiga ainda mostra `npm install` sem prompt | espere nela; não rode outro `npm install` em paralelo |
| A janela antiga já voltou ao prompt `D:\JARVIS>` | terminou; siga para `py -m venv .venv` |
| Você fechou a janela antiga | o processo morreu; rode `npm install` de novo na pasta certa |

### Quanto tempo demora o `npm install` (e como saber se travou)

O `npm install` fica **em silêncio** por vários minutos. Isso é normal, não é travamento: ele resolve a árvore inteira, baixa tudo para o cache em `C:\Users\SEU_USUARIO\AppData\Local\npm-cache` e só então descompacta em `node_modules`.

Números medidos deste projeto:

| Medida | Valor |
|---|---|
| Pacotes no `package-lock.json` | **161** |
| Pastas de primeiro nível em `node_modules` | **84** |
| Arquivos descompactados | **9.198** |
| Tamanho final em disco | **139 MB** |
| Maior binário (esbuild) | **9,9 MB** |

Num pendrive, o gargalo não é a internet — é **gravar 9.198 arquivos pequenos** e o antivírus lendo cada um deles na primeira gravação:

| Cenário | Tempo esperado |
|---|---|
| USB 3.0 + internet rápida | 2 a 6 minutos |
| USB 2.0 + internet razoável | 6 a 15 minutos |
| USB 2.0 + Defender ativo + internet lenta | até 25 minutos |

O `pip install` do passo seguinte é bem mais rápido: são ~30 pacotes e os wheels são arquivos grandes e poucos.

#### Como saber se está trabalhando, sem cancelar

Abra um **segundo** cmd (não feche o primeiro) e rode duas vezes, com um minuto de intervalo:

```bat
dir D:\JARVIS\node_modules /b | find /c /v ""
```

O número que aparece é a quantidade de entradas em `node_modules`. Se ele **cresce** entre uma medição e outra, a instalação está andando. Se o comando disser que a pasta não existe, o npm ainda está na fase de download — olhe o **Gerenciador de Tarefas → Desempenho → Rede**: se houver tráfego, está baixando.

#### Se passar de 30 minutos parado

1. **Não apague nada.** Se precisar, `Ctrl+C` é seguro: rode `npm install` de novo depois.
2. Confira espaço em `D:` — precisa de ~300 MB livres.
3. Rode com log detalhado para ver onde parou:

```bat
npm install --loglevel=http
```

Cada linha mostra o pacote sendo baixado. Se parar sempre no mesmo pacote, é rede ou proxy.

4. Para reaproveitar o que já foi baixado (o cache em `C:` continua válido):

```bat
npm install --prefer-offline --no-audit --no-fund
```

| Erro que aparece | Causa | O que fazer |
|---|---|---|
| `ETIMEDOUT` / `ENOTFOUND` / `ECONNRESET` | rede, proxy ou antivírus interceptando | tente de novo; se persistir, `npm config set registry https://registry.npmjs.org/` |
| `EPERM` / `EBUSY` / `EEXIST` | arquivo travado por antivírus ou indexador | feche o editor, rode de novo; em último caso apague `node_modules` e repita |
| `ENOSPC` | sem espaço | libere espaço no pendrive |
| `npm error code EJSONPARSE` | `package.json` corrompido na cópia | extraia o ZIP de novo |
| nada acontece e o pendrive pisca sem parar | gravação de arquivos pequenos em USB 2.0 | espere; é o cenário mais lento da tabela |

### Linux / macOS

```bash
cd /media/SEU_PENDRIVE/JARVIS
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
npm install
```

### Sem `.venv` no pendrive

O launcher `scripts/python.mjs` aceita a variável `PYTHON` e, sem ela, cai para o `python3` do sistema:

```bash
PYTHON=/usr/bin/python3 npm run dev
```

```powershell
$env:PYTHON="py"; npm run dev
```

Nesse caso as dependências precisam estar instaladas no Python do sistema: `pip install -r requirements-dev.txt`.

---

## 5. Modo sem Node: rodar sem `npm install`

Todo o resto do guia assume `npm install`. **Não é obrigatório.** A interface compilada está versionada na pasta `web-dist/` (19 arquivos, **1,6 MB**), e a API Python a serve na mesma porta. É o caminho para pendrive lento, máquina sem Node ou `npm install` que não termina.

```bat
cd /d D:\JARVIS
py -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\python iniciar.py
```

Depois abra **http://127.0.0.1:8000** — sem Vite, sem porta 5173, sem `node_modules`.

Validado numa cópia limpa (sem `node_modules`, sem `dist`, sem `.git`): `/api/health` respondeu `"interface": "web-dist"` e a raiz entregou o HTML da interface.

| Modo | Precisa de Node? | Precisa de `npm install`? | Arquivos a gravar | Tamanho no pendrive | Porta |
|---|---|---|---|---|---|
| `npm run dev` (desenvolvimento) | sim | sim | **9.198** | 18 MB + 139 MB = **157 MB** | 5173 + 8000 |
| `py iniciar.py` (sem Node) | **não** | **não** | **~4.400** | 18 MB + 103 MB = **121 MB** | **8000** |

Medido nesta máquina: cópia do projeto sem `node_modules`/`dist`/`.git` = **18 MB**; `.venv` só com `requirements.txt` (medido na 0.40.1, sem o extra `standard`) = **103 MB**, **31 pacotes** e **4.410 arquivos** — era 124 MB e 36 pacotes antes de tirar o `PyYAML`. O `npm install` grava **9.198 arquivos**; o `pip` grava pouco mais de **4.400**, cerca de metade, e nenhum deles é arquivo pequeno de dependência JavaScript, que é o que dói num pendrive USB 2.0.

O `iniciar.py` aceita `--porta 8080` e `--host 0.0.0.0` (para acessar de outro aparelho na rede local). Ele também troca sozinho para o Python do `.venv` quando existir.

Como conferir que a interface está sendo servida:

```bat
curl http://127.0.0.1:8000/api/health
```

A resposta inclui `"interface": "web-dist"` (ou `"dist"`, quando você rodou `npm run build`). Se aparecer `"ausente"`, a pasta não veio na cópia.

Para atualizar a interface embutida depois de mexer no React:

```bat
npm run build:embutido
```

### Limites do modo sem Node

- **Não recarrega ao editar.** Mudou código React? Precisa de `npm run build:embutido` — que exige Node.
- **Sem testes web.** `npx vitest` continua exigindo `npm install`.
- **Mesmas 223 skills.** O modo sem Node muda só como a tela é entregue; toda a lógica roda em Python.

---


## 6. Configurar a chave de IA

O jeito mais seguro, **sem abrir editor de texto**, é o script do projeto:

```bat
cd /d D:\JARVIS
.venv\Scripts\python configurar-chave.py
```

Ele pergunta provedor, base e modelo (já sugere OpenAI, `https://api.openai.com/v1` e `gpt-4o-mini`), depois pede a **chave sem mostrar o que você digita** — ela não fica no histórico do `cmd` nem aparece na tela. No fim, grava o `.env` **em CRLF** (o formato que o Bloco de Notas do Windows 10 antigo entende) e preserva todas as outras variáveis que já estavam lá.

```bat
.venv\Scripts\python configurar-chave.py --ver      # mostra o que está gravado, chave mascarada
.venv\Scripts\python configurar-chave.py --limpar   # apaga só a chave, mantém o resto
```

Depois de gravar, **reinicie o servidor**: Ctrl+C na janela do `iniciar.py` e suba de novo. Ele só lê o `.env` na inicialização.

Editar na mão também funciona:

```bash
cp .env.example .env
```

Windows:

```powershell
copy .env.example .env
```

Edite `.env` e preencha:

```dotenv
JARVIS_AI_PROVIDER=OpenAI
JARVIS_AI_BASE_URL=https://api.openai.com/v1
JARVIS_AI_MODEL=gpt-4o-mini
JARVIS_AI_API_KEY=valor-da-chave
```

### Onde conseguir a chave sem pagar

Não existe chave grátis da OpenAI — site que oferece isso está revendendo chave vazada. Servem três provedores compatíveis, **nenhum deles pede cartão**:

| Provedor | Camada gratuita | Base | Chave em |
|---|---|---|---|
| Groq | ~1.000 requisições/dia, 30 por minuto | `https://api.groq.com/openai/v1` | <https://console.groq.com/keys> |
| Google AI Studio | cota diária por modelo | `https://generativelanguage.googleapis.com/v1beta/openai` | <https://aistudio.google.com/apikey> |
| OpenRouter | 50 requisições/dia (modelos `:free`) | `https://openrouter.ai/api/v1` | <https://openrouter.ai/keys> |

O passo a passo de cada um, com o que digitar em cada campo e o aviso de privacidade (o plano gratuito do Google usa suas conversas para treinar; o do Groq não), está em [`CONFIGURAR-IA.md`](CONFIGURAR-IA.md) §0.

**Chave não é obrigatória.** Sem chave nenhuma, as 223 skills locais, a legislação, os documentos, a memória e as tarefas funcionam; fica de fora só o chat aberto. E existe a rota sem limite: rodar o modelo **na própria máquina** com `llama.cpp` ou `KoboldCpp` (o Ollama não instala no Windows 10 1607 — ele pede 22H2) e apontar com `.venv\Scripts\python configurar-chave.py --local`. Nesse modo nada sai da máquina. O que cabe em cada quantidade de RAM está na tabela do mesmo §0.

Com a chave em mãos, o teste rápido é:

```bat
.venv\Scripts\python configurar-chave.py --testar
```

Ele faz uma chamada de verdade e responde `FUNCIONOU` ou o motivo em português (401 chave, 404 modelo, 429 cota). Sem reiniciar nada.

> **Cuidado no Bloco de Notas antigo.** Se você baixou uma cópia anterior à 0.37.1, o `.env` e o `.env.example` vêm com quebra de linha Unix e o Notepad do Windows 10 1607 mostra tudo numa linha só. Se salvar nesse estado, o arquivo é amassado e a chave se perde. Ou use o `configurar-chave.py`, ou no Bloco de Notas faça **Arquivo → Novo**, cole as quatro linhas acima e salve como `D:\JARVIS\.env` (tipo **Todos os arquivos**) — arquivo novo já sai com a quebra de linha certa.

O `.env` está no `.gitignore`: não entra no Git e não deve ser compartilhado junto com o pendrive.

Como saber que a chave entrou:

```bat
curl http://127.0.0.1:8000/api/ai/status
```

Esperado: `"configured": true` com o provedor e o modelo. Se continuar `false`, o servidor não foi reiniciado ou a variável está com outro nome.

---

## 7. Subir e conferir

```bash
npm run dev
```

Abra **http://localhost:5173**. A API sobe em `http://127.0.0.1:8000`.

```bash
curl http://127.0.0.1:8000/api/health
```

Esperado: `"version": "0.42.1"` e `"skills": 223`.

O token de host aparece no terminal da API, no formato `UJ4F…q8CM`, e fica em `storage/host-token.txt`. Ele é exigido pelas skills que tocam a máquina — inclusive a importação.

---

## 8. Onde cada coisa é gravada

Tudo abaixo fica **dentro da pasta do projeto**, ou seja, no pendrive:

| O que | Caminho |
|---|---|
| Documentos, textos, planilhas criados | `storage/user-files` |
| Arquivos importados da pasta de downloads | `storage/user-files/<subpasta>` |
| Downloads da web e quarentena | `storage/host-downloads` |
| Token de host | `storage/host-token.txt` |
| Livro de auditoria | `storage/host-audit.jsonl` |
| Banco da Estação | `storage/estacao/estacao.db` |
| Chave e configuração | `.env` |

O que **não** fica no pendrive: arquivos baixados clicando no navegador (vão para a pasta de downloads do navegador) e ações de sistema (instalar `.deb`, drivers, Bluetooth) — essas agem na máquina, não no pendrive.

---

## 9. A skill que traz os arquivos da pasta Downloads

A skill **`files.import`** (“Importar do computador”) copia arquivos da pasta de downloads da máquina para a área isolada do JARVIS, que no seu caso é o pendrive.

O que ela faz:

- **copia**, não move; o original continua em Downloads;
- exige **token de host**;
- exige **confirmação** (`confirmed: true`);
- aceita **simulação** (`dryRun: true`) para mostrar o que faria, sem copiar;
- **não apaga** nem executa nada.

### Formatos aceitos

`pdf`, `docx`, `xlsx`, `pptx`, `txt`, `md`, `json`, `csv`, `log`.

São exatamente os formatos que a área isolada sabe listar (`files.list`) e ler (`files.read`, `document.read`). Copiar um `.exe` ou uma foto para lá não apareceria em lugar nenhum.

### Limites

| Limite | Valor |
|---|---|
| Arquivos por chamada | **200** |
| Tamanho por arquivo | **64 MB** |
| Tamanho total do lote | **512 MB** |
| Subpasta de destino | relativa, sem `..`, sem caminho absoluto, sem nome oculto |
| Sobrescrever | desligado por padrão |

### Pela interface

1. Abra **Skills → Arquivos → Importar do computador**.
2. Cole o **token de host**.
3. Deixe **Pasta de origem** vazio para usar a pasta Downloads do usuário, ou informe o caminho completo.
4. Em **Subpasta na área do JARVIS**, use algo como `importados`.
5. Rode primeiro com **simular** ligado; confira a lista; depois execute com a confirmação.

### Pela API

```bash
TOKEN=$(cat storage/host-token.txt)

curl -s -X POST http://127.0.0.1:8000/api/skills/files.import/execute \
  -H 'Content-Type: application/json' \
  -d "{\"parameters\":{\"origem\":\"\",\"destino\":\"importados\",\"autorizacao\":\"$TOKEN\"},\"dryRun\":true}"
```

Para copiar de verdade, troque `\"dryRun\":true` por `\"confirmed\":true`.

A resposta traz `copiados`, `ignorados` (com o motivo de cada um) e `bytes`.

---

## 10. Limites que precisam ficar ditos

1. **Não é um sistema operacional.** O pendrive carrega o programa, não a máquina.
2. **`.venv` e `node_modules` são por máquina.** Trocar a letra do drive (`E:` → `F:`) ou de computador quebra o `.venv`; recrie.
3. **Pendrive USB 2.0 é lento.** Rodar os 1.830 testes de API a partir dele demora bem mais que no disco interno.
4. **exFAT não guarda permissão.** Instalar AppImage pela camada de sistema vai falhar no `chmod +x`.
5. **A camada de auto-alteração precisa de `.git`.** Sem ele, `evoluir.promover` recusa.
6. **O pendrive pode ser perdido.** O `.env` viaja junto; se a chave estiver nele, troque a chave se o pendrive sumir.

---

## 11. Problemas comuns

| Sintoma | Causa provável | O que fazer |
|---|---|---|
| `winget` não reconhecido | Windows sem App Installer, ou versão antiga | instalar pelo site oficial (§1) ou usar os blocos de PowerShell da §1 |
| `node` não reconhecido | Node não instalado ou fora do PATH | instalar em <https://nodejs.org> e reabrir o terminal |
| `python3` não reconhecido | no Windows o comando é `py` ou `python` | usar `py --version` |
| `.venv/bin/pip` não existe | caminho de Linux | no Windows é `.venv\Scripts\pip` |
| `python` não reconhecido (Windows) | Python sem PATH | reinstalar marcando “Add python.exe to PATH” |
| `npm install` falha em pendrive FAT32 | sistema de arquivos sem suporte | formatar em NTFS ou ext4 |
| `npm error ENOENT … C:\Users\pc\package.json` | comando rodou fora da pasta do projeto | `cd /d D:\JARVIS` antes de qualquer `npm` |
| `npm ls` mostra `UNMET DEPENDENCY` | instalação interrompida | rodar `npm install` de novo (é idempotente) |
| `.venv` quebrou depois de trocar de porta USB | caminho absoluto mudou | apagar `.venv` e recriar na máquina |
| `Building wheel for pyyaml ... error` / `Microsoft Visual C++ 14.0 or greater is required` | `PyYAML` não tem wheel para Python 3.15 no Windows; vinha pelo `uvicorn[standard]` | usar o `requirements.txt` da 0.40.1 (sem `[standard]`) e rodar o `pip install` de novo — o `pip` aborta **tudo** quando um pacote falha, então até aqui nada foi instalado (§1) |
| `Faltam as bibliotecas Python` mas o `.venv` existe | o `pip install` parou no meio; o `.venv` está vazio | subir `pip list` e conferir; quase sempre é o caso da linha acima |
| `Token de host inválido` | token de outro projeto/cópia | ler `storage/host-token.txt` desta cópia |
| `A origem não existe` | caminho errado | informar o caminho completo da pasta Downloads |
| `formato fora da lista permitida` | extensão não suportada | salvar como PDF ou converter para um dos nove formatos |
| `já existe no destino` | arquivo repetido | marcar **sobrescrever** ou mudar a subpasta |

---

## 12. Checklist

- [ ] Node 22+ instalado (`node --version`)
- [ ] Python 3.11+ instalado (`python --version`)
- [ ] pendrive em NTFS ou ext4
- [ ] projeto copiado, clonado ou extraído do ZIP para o pendrive
- [ ] `npm install` executado
- [ ] `.venv` criado e `pip install -r requirements-dev.txt` executado
- [ ] `.env` preenchido com a chave (`py configurar-chave.py --ver` mostra `(vazia)` quando falta)
- [ ] `npm run checar` sem nenhuma linha FALTA
- [ ] `npm run dev` sobe sem erro
- [ ] `http://127.0.0.1:8000/api/health` mostra `0.42.1` e `223`
- [ ] `files.import` testado com simulação antes da cópia real

### Sequência completa no Windows (do zero ao `npm run dev`)

Supondo o projeto extraído em `E:\JARVIS` e as ferramentas já instaladas:

```bat
cd /d E:\JARVIS
npm install
py -m venv .venv
.venv\Scripts\pip install -r requirements-dev.txt
copy .env.example .env
notepad .env
npm run checar
npm run dev
```

Linha por linha:

| Comando | O que faz |
|---|---|
| `cd /d E:\JARVIS` | entra na pasta do projeto, trocando também de unidade |
| `npm install` | instala as bibliotecas da interface (≈ 139 MB) |
| `py -m venv .venv` | cria o ambiente Python isolado dentro do pendrive |
| `.venv\Scripts\pip install -r requirements-dev.txt` | instala FastAPI, Pydantic, pytest e o resto |
| `copy .env.example .env` | cria o arquivo de configuração |
| `notepad .env` | abre para você colar a chave em `JARVIS_AI_API_KEY=` |
| `npm run checar` | confere tudo e diz o que falta |
| `npm run dev` | sobe a API (:8000) e a interface (:5173) |

Depois, no navegador: <http://localhost:5173>.
