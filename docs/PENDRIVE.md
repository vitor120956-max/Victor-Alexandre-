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

### Opção B — cópia simples

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

```powershell
cd E:\JARVIS
py -m venv .venv
.venv\Scripts\pip install -r requirements-dev.txt
npm install
```

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

Esperado: `"version": "0.36.0"` e `"skills": 209`.

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
| `node` não reconhecido | Node não instalado ou fora do PATH | instalar em <https://nodejs.org> e reabrir o terminal |
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
- [ ] projeto copiado ou clonado para o pendrive
- [ ] `npm install` executado
- [ ] `.venv` criado e `pip install -r requirements-dev.txt` executado
- [ ] `.env` preenchido com a chave
- [ ] `npm run checar` sem nenhuma linha FALTA
- [ ] `npm run dev` sobe sem erro
- [ ] `http://127.0.0.1:8000/api/health` mostra `0.36.0` e `209`
- [ ] `files.import` testado com simulação antes da cópia real
