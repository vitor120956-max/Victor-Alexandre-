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
| Sistema de arquivos | **aviso** em exFAT/FAT32; aceita ext4, btrfs, XFS, ZFS, F2FS e NTFS |
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

## 5. Configurar a chave de IA

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

O `.env` está no `.gitignore`: não entra no Git e não deve ser compartilhado junto com o pendrive.

---

## 6. Subir e conferir

```bash
npm run dev
```

Abra **http://localhost:5173**. A API sobe em `http://127.0.0.1:8000`.

```bash
curl http://127.0.0.1:8000/api/health
```

Esperado: `"version": "0.36.2"` e `"skills": 209`.

O token de host aparece no terminal da API, no formato `UJ4F…q8CM`, e fica em `storage/host-token.txt`. Ele é exigido pelas skills que tocam a máquina — inclusive a importação.

---

## 7. Onde cada coisa é gravada

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

## 8. A skill que traz os arquivos da pasta Downloads

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

## 9. Limites que precisam ficar ditos

1. **Não é um sistema operacional.** O pendrive carrega o programa, não a máquina.
2. **`.venv` e `node_modules` são por máquina.** Trocar a letra do drive (`E:` → `F:`) ou de computador quebra o `.venv`; recrie.
3. **Pendrive USB 2.0 é lento.** Rodar os 1.815 testes de API a partir dele demora bem mais que no disco interno.
4. **exFAT não guarda permissão.** Instalar AppImage pela camada de sistema vai falhar no `chmod +x`.
5. **A camada de auto-alteração precisa de `.git`.** Sem ele, `evoluir.promover` recusa.
6. **O pendrive pode ser perdido.** O `.env` viaja junto; se a chave estiver nele, troque a chave se o pendrive sumir.

---

## 10. Problemas comuns

| Sintoma | Causa provável | O que fazer |
|---|---|---|
| `winget` não reconhecido | Windows sem App Installer, ou versão antiga | instalar pelo site oficial (§1) ou usar os blocos de PowerShell da §1 |
| `node` não reconhecido | Node não instalado ou fora do PATH | instalar em <https://nodejs.org> e reabrir o terminal |
| `python3` não reconhecido | no Windows o comando é `py` ou `python` | usar `py --version` |
| `.venv/bin/pip` não existe | caminho de Linux | no Windows é `.venv\Scripts\pip` |
| `python` não reconhecido (Windows) | Python sem PATH | reinstalar marcando “Add python.exe to PATH” |
| `npm install` falha em pendrive FAT32 | sistema de arquivos sem suporte | formatar em NTFS ou ext4 |
| `.venv` quebrou depois de trocar de porta USB | caminho absoluto mudou | apagar `.venv` e recriar na máquina |
| `Token de host inválido` | token de outro projeto/cópia | ler `storage/host-token.txt` desta cópia |
| `A origem não existe` | caminho errado | informar o caminho completo da pasta Downloads |
| `formato fora da lista permitida` | extensão não suportada | salvar como PDF ou converter para um dos nove formatos |
| `já existe no destino` | arquivo repetido | marcar **sobrescrever** ou mudar a subpasta |

---

## 11. Checklist

- [ ] Node 22+ instalado (`node --version`)
- [ ] Python 3.11+ instalado (`python --version`)
- [ ] pendrive em NTFS ou ext4
- [ ] projeto copiado, clonado ou extraído do ZIP para o pendrive
- [ ] `npm install` executado
- [ ] `.venv` criado e `pip install -r requirements-dev.txt` executado
- [ ] `.env` preenchido com a chave
- [ ] `npm run checar` sem nenhuma linha FALTA
- [ ] `npm run dev` sobe sem erro
- [ ] `http://127.0.0.1:8000/api/health` mostra `0.36.2` e `209`
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
