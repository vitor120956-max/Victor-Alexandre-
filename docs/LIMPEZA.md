# Debloat: o que sai do Windows sem quebrar nada

O pedido veio com cinco fotos do Gerenciador de Tarefas: *“tem processos que
sempre estão rodando sem funcionalidade… fazer um debloat do que não usamos e
não é necessário, que só ocupa espaço no Windows”*.

Este documento é a resposta em três partes: **por que a lista das fotos mistura
três coisas diferentes**, **o que o JARVIS classifica** e **o que ele se recusa a
fazer**.

---

## 1. As fotos mostram três origens, não uma

| nas fotos | origem | é bloat? |
|---|---|---|
| Google Drive, Google Chrome, Microsoft Office Click-to-Run, Microsoft Edge WebView2 | programa **que você instalou** e usa | **não**. É uso, não lixo |
| NVIDIA Container, NVIDIA Web Helper, NVIDIA Driver Helper, Stereo Vision Control Panel | **driver** (ver `docs/PENDRIVE.md` §13 e `processos.py`) | não ocupa disco, é serviço do driver |
| Solitaire, Tempo, Notícias, Hub do Office, Xbox overlay, telemetria (`DiagTrack`), tarefas `\Microsoft\Windows\*` | **Windows de fábrica** | **sim** — é aqui que o ganho mora |

Uma lista que mistura as três é o que produz os “debloats” que quebram a loja, o
Wi-Fi ou o Office. O JARVIS separa: só o que é de fábrica entra no plano, e o
que é seu aparece com o nome e **sem comando**.

## 2. O que ele lê da máquina

| leitura | como | o que devolve |
|---|---|---|
| apps de loja | `Get-AppxPackage` | nome do pacote; framework é filtrado |
| serviços | `Get-CimInstance Win32_Service` | estado e modo de início |
| tarefas | `Get-ScheduledTask` | caminho e estado |
| pastas de cache | `Test-Path` + soma opcional | existe / quanto ocupa |

Nada disso é chute: o catálogo tem 35 apps, 18 serviços, 13 tarefas e 10 itens de
espaço — e **só o que existe na sua máquina entra no relatório**. App instalado
que não está no catálogo vai para “fora do catálogo”, e ali fica sem palpite.

## 3. Os três vereditos

| veredito | significado | entra no `.bat` |
|---|---|---|
| **sobra** | sai sem perda: jogo de cartas, MSN, telemetria, cache | comando ativo |
| **cuidado** | depende de como você usa o PC: Xbox, Teams, OneDrive, WinSxS, hibernação | **comentado** com `rem` |
| **essencial** | tirar quebra algo: Store, `winget`, Segurança, VCLibs, Fotos, Spooler, Wi-Fi, horário, `C:\Windows\Installer` | nunca aparece |

O detalhe que importa: **sobra vira linha ativa, cuidado vira `rem`**. Você lê,
descomenta o que não usa, e roda. Não existe caixa “deixe o JARVIS decidir”.

## 4. O espaço, com honestidade

| item | ganho real | por que |
|---|---|---|
| `Windows.old` | 5 a 20 GB | cópia da versão anterior, some sozinha em 10 dias |
| Cache de atualização | 300 MB a 3 GB | instalador já aplicado |
| Temporários (`%LOCALAPPDATA%\Temp`, `C:\Windows\Temp`) | 200 MB a 4 GB | lixo por definição |
| Lixeira | 0 a 30 GB | depende de você |
| WinSxS (`DISM /StartComponentCleanup /ResetBase`) | 1 a 8 GB | **opcional**: mantém o sistema atualizável, mas não dá para desinstalar atualização antiga |
| `hiberfil.sys` (`powercfg /h off`) | ~40% da RAM | **opcional**: perde hibernar **e** o início rápido |

E as duas armadilhas que todo “otimizador” cai: **`C:\Windows\Prefetch`** e
**`C:\Windows\Installer`**. A primeira deixa o programa abrir mais rápido; a
segunda é o cache de desinstalação — apagar quebra o “Desinstalar” de vários
programas. As duas estão no catálogo marcadas como **essencial**, com `comando`
vazio: o JARVIS prefere não sugerir do que sugerir errado.

## 5. O script

`maquina.limpar` devolve dois arquivos, em CRLF, uma linha por comando:

- **`debloat.bat`** — começa conferindo se está como administrador
  (`net session`), avisa que não apaga arquivo pessoal, faz `pause` antes de cada
  bloco. Só o que é sobra vem ativo.
- **`restaurar-windows.bat`** — religa cada serviço (`sc config ... start= auto`
  ou `manual`, conforme o tipo original) e cada tarefa (`schtasks /ENABLE`), e
  mostra o comando de volta de cada app.

Na tela `/maquina`, aba **Limpeza**, os dois botões salvam o arquivo direto —
sem copiar e colar em bloco de notas.

## 6. O que este módulo se recusa a fazer

- **Não executa nada.** Nem aqui, nem por skill escondida: `subprocess.run` só
  existe em uma função (`_ps`), e ela só recebe script fixo do módulo.
- **Não remove driver.** O NVIDIA Container aparece como *cuidado*, com o texto
  de `processos.py`, e o `sc config` dele vem comentado.
- **Não apaga pasta do sistema na mão.** WinSxS vai por `DISM`; `Windows.old` vai
  pela tela do Windows, porque o dono da pasta é o `TrustedInstaller`.
- **Não faz “desativar tudo”.** O que é essencial não é listado como opção, nem
  comentado — não aparece.

## 7. Fora do Windows

`maquina.debloat` devolve `lido: false` com o motivo. Debloat é do Windows; num
Linux (ou no sandbox onde este projeto é testado) não há app de loja para listar,
e fingir uma lista vazia seria pior que dizer “não se aplica”.

## 8. Testes

`server/tests/test_limpeza.py` — 23 testes, com máquina simulada:

- catálogo: todo item tem nome e explicação; Store/VCLibs/Segurança/`winget` são
  essenciais; NVIDIA é cuidado; Prefetch e Installer são essenciais **sem comando**;
- análise: app instalado vira ficha, desconhecido **não** recebe palpite, sobra
  soma só sobra, item não instalado não aparece, serviço volta ao tipo original;
- plano: script começa com `@echo off` e checa administrador, só sobra é comando
  ativo, cuidado entra com `rem`, essencial nunca aparece, `restaurar` religa
  serviço e tarefa, e o resumo conta o que sai;
- travas: `subprocess.run` aparece uma vez só, sem `shell=True` nem `os.system`,
  fora do Windows explica, e medir pasta é opt-in (WinSxS leva minutos).

---

## 9. Os braços: `maquina.arrumar` (0.72.0)

Até a 0.72.0 esta camada **diagnosticava** e entregava um `.bat` — o usuário lia,
salvava e rodava como administrador. Isso é relatório, não braço. O pedido foi
literal: *“eu não quero ter que fazer nada, por isso fiz o JARVIS com braços”*.

Agora existe **um comando que executa**:

| onde | como |
|---|---|
| tela `/maquina` → aba **Limpeza** | botão **“Arrumar agora”** (e **“Desfazer a última”**) |
| duplo clique | `arrumar-pc.bat` → mostra o plano, pede `S`, executa |
| duplo clique para voltar | `desfazer-limpeza.bat` |
| chat/skill | `maquina.arrumar` e `maquina.desfazer` |

**O que dizer no chat** (0.72.0: as escolhas da frase chegam como parâmetro, em vez
de serem engolidas):

| frase | o que acontece |
|---|---|
| `arruma o pc` | pede confirmação e executa o plano normal |
| `arruma o pc só o plano` | mostra o plano e **não** pede confirmação — nada é mexido |
| `o que dá para limpar do windows` | mesma coisa: só o plano |
| `arruma o pc no modo ousado` | inclui o `cuidado` reversível (Xbox, Teams, Search, Superfetch, hibernação) |
| `arruma o pc sem ponto de restauração` | pula o ponto e mantém o instantâneo |
| `arruma o pc ousado e só o plano` | as duas escolhas juntas |
| `desfaz a última limpeza` / `volta tudo como era` | reverte o último diário |
| `me manda o script da limpeza` | continua sendo texto (`maquina.limpar`) — script não é braço |

O que não é dito na frase fica no padrão da skill: **ponto de restauração ligado**,
modo normal, todas as cinco frentes. E “o que dá para tirar do Windows” continua
indo para o debloat, que só lê.

### 9.1 O que ele executa

| tipo | ação | quantos |
|---|---|---|
| processo | `taskkill /PID` nas sobras (Steam Web Helper, SearchUI, OneDrive…) | os que existirem agora |
| app de loja | `Get-AppxPackage … Remove-AppxPackage` no que é **sobra** | os instalados |
| tarefa | `schtasks /Change /DISABLE` nas tarefas de telemetria | as existentes |
| serviço | `sc config … start= disabled` nos serviços sem uso | os existentes |
| espaço | `%LOCALAPPDATA%\Temp`, `C:\Windows\Temp`, cache de atualização, Otimização de Entrega, lixeira | os que existirem |
| espaço, **só no ousado** | `powercfg /h off` (hibernação, `hiberfil.sys`) | se existir |

### 9.2 O que ele **nunca** executa

- **driver** — o NVIDIA Container continua de fora (é `cuidado`);
- **essencial** — Store, `winget`, Segurança, VCLibs/UI.Xaml, Calculadora, Fotos, Captura, Spooler, Wi-Fi, áudio, horário;
- **cuidado** — Xbox/Game Bar, Teams, Vínculo com o Telefone, Superfetch, Search, Otimização de Entrega — **a menos que o modo ousado esteja ligado**, e então só o que tem volta declarada (§10.5);
- **WinSxS**, **Windows.old**, **hibernação** fora do ousado — nunca entram no plano normal;
- **`C:\Windows\Installer`** e **`Prefetch`** — marcados como essenciais no catálogo, sem comando;
- **processo por PID velho** — antes de matar, confere se aquele PID ainda é o mesmo processo **e** continua classificado como sobra. PID reciclado é comum no Windows, e matar por número antigo fecha programa alheio.

### 9.3 As quatro travas

1. `JARVIS_HOST_ARRUMAR=1` — o `iniciar-jarvis.bat` liga; o `.env` desliga;
2. **token de host** — preenchido sozinho quando o pedido vem desta máquina;
3. **confirmação** — o botão envia `confirmed: true`; a API recusa sem isso;
4. **diário** — cada ação bem-sucedida grava comando, saída e comando de volta em
   `storage/limpezas/limpeza-AAAAMMDD-HHMMSS.json`.

### 9.4 Desfazer, com honestidade

`desfazer()` relê o **último diário** e reverte o que tem volta:

| ação | volta? |
|---|---|
| serviço desativado | **sim** — `sc config … start= auto` (ou `manual`, o tipo original) |
| tarefa desativada | **sim** — `schtasks /Change /ENABLE` |
| app de loja removido | **sim** — pela Microsoft Store (o diário traz o comando) |
| processo fechado | **não** — ele abre de novo quando precisar |
| cache e lixeira | **não** — eram lixo por definição |

O relatório lista nominalmente o que ficou `sem_volta` — em vez de dizer
“desfeito” e esconder que a lixeira não volta.

E antes de remover qualquer coisa, a 0.72.0 grava **duas** coisas: o instantâneo do
estado (`instantaneo-*.json`, 3 KB) e, quando a Proteção do Sistema permite, um ponto
de restauração do Windows — o único jeito de voltar driver, serviço e registro de uma
vez (`Win+R` → `rstrui`). Detalhe em §10.3.

No código, as duas listas que separam isso são `ESPACO_SEGURO` (temp, cache de
atualização, lixeira, Otimização de Entrega) e `ESPACO_OUSADO` (só `hiberfil`).

---

## 10. Por que cada item proibido é proibido — e o backup que resolve (0.72.0)

A pergunta foi: *“não entendi por que ele não pode mexer nessas coisas; uma ideia
boa é ele fazer um backup na nuvem antes de remover”*.

A resposta tem duas partes: **backup não resolve tudo**, e **o que backup resolve
o JARVIS passou a fazer**.

### 10.1 Backup não salva o que quebra na hora

| item | o que quebra **nos 5 minutos seguintes** | backup ajuda? |
|---|---|---|
| **Spooler** | nenhuma impressora funciona, inclusive “imprimir em PDF” | não: o problema é o intervalo até restaurar |
| **áudio (Audiosrv)** | a máquina fica muda | não |
| **Wi-Fi (WlanSvc)** | sem rede — e sem rede **não há nuvem para restaurar** | **péssimo**: o backup depende da conexão que você acabou de perder |
| **horário (W32Time)** | hora erra → certificado de site falha → quase todo HTTPS quebra | não |
| **Microsoft Store / winget** | é **o caminho de volta** de tudo o resto | não: você apagaria a própria ferramenta de restaurar |
| **VCLibs / UI.Xaml** | quebra apps que **não estão na lista** | não: é dependência compartilhada |
| **driver NVIDIA** | perde painel/ShadowPlay; volta com reinício | não é dado — reinstala-se do site |

Nenhum desses é “arquivo que a gente guarda”: são serviços e bibliotecas que o
Windows usa o tempo todo. Backup não evita o estrago — só documenta.

### 10.2 Backup não faz sentido para os “grandes”

| item | o que é de verdade | por que backup é a ferramenta errada |
|---|---|---|
| **WinSxS** | cópia de componentes que o Windows mantém para poder atualizar | 5–10 GB; o certo é `DISM /StartComponentCleanup`, que apaga **só a versão antiga** e mantém o sistema atualizável. Copiar 8 GB para depois devolver não é limpeza |
| **Windows.old** | a versão anterior do Windows | some sozinha em 10 dias; copiar significa **não** limpar |
| **`C:\Windows\Installer`** | cache de desinstalação dos MSI | 1–3 GB, **sem volta útil**: os MSI referenciam caminho absoluto — um zip disso não reinstala nada |
| **Prefetch** | índice que deixa o programa abrir rápido | ganho de **MB**; o custo é boot mais lento. Não vale nem o backup |

### 10.3 O que o JARVIS passou a fazer antes de qualquer remoção

Duas coisas, e nenhuma delas é “mandar 20 GB para a nuvem”:

**1. Instantâneo do estado — KB, sempre**

`storage/limpezas/instantaneo-AAAAMMDD-HHMMSS.json` com a lista de apps de loja
(nome e `PackageFullName`), o estado de cada serviço (rodando/parado e modo de
início) e o estado de cada tarefa. É pequeno o bastante para caber num Drive, num
pendrive ou num anexo — e é o que permite **reinstalar pela Store** e saber como
cada serviço estava antes.

**2. Ponto de restauração do Windows — 1 a 2 GB, no disco local**

`Checkpoint-Computer` antes da limpeza. É o único mecanismo que o Windows tem para
voltar **driver, serviço e registro**. Para voltar tudo: `Win+R` → `rstrui` →
escolher “JARVIS antes da limpeza”.

Se a Proteção do Sistema estiver desligada (comum), o ponto falha — e o JARVIS
**diz isso no relatório** em vez de fingir que salvou, e segue com o instantâneo.

### 10.4 Sobre “nuvem”

O JARVIS não manda nada para fora por conta própria: não há chave, não há API, e
o módulo não faz upload. O instantâneo fica em `storage/limpezas/` — se você quiser
na nuvem, é `drive.*` (já existe no projeto) apontando para esse arquivo de 3 KB.
Mandar o Windows inteiro para a nuvem seria lento, caro e pior que o `rstrui`.

### 10.5 Modo ousado — o controle que você pediu

O que **tem volta** deixou de ser proibido e virou escolha:

| entra no modo ousado | volta como |
|---|---|
| Xbox / Game Bar | Store |
| Teams (consumidor) | painel de programas |
| Windows Search (indexador) | `sc config WSearch start= auto` |
| Superfetch (SysMain) | `sc config SysMain start= auto` |
| Otimização de Entrega | `sc config DoSvc start= auto` |
| hibernação (`hiberfil.sys`) | `powercfg /h on` |

Liga na tela (checkbox **“Modo ousado”**), no `.bat` (tecla **O**) ou na skill
(`ousado: true`). O que **não** tem volta continua fora **nos dois modos**:
WinSxS, Windows.old, `C:\Windows\Installer`, Prefetch, driver e essencial.

---

## 11. Quando falha — e quando parece que travou (0.72.0)

Em 01/11/2026 o primeiro uso real rodou assim: **3 feitas, 13 falhas**. O resumo
dizia *“13 falharam — normalmente falta de administrador; o diário diz qual”*, e a
tela ficava com três pontinhos animados sem tempo, sem dizer o que estava rodando
e sem dizer se tinha travado. Duas coisas foram corrigidas.

### 11.1 Por que falhou, com o próximo passo

Cada ação que falha agora leva `causa` e `motivo` traduzidos, e o resultado do
braço leva `falhas_por_causa`, `nao_feitas` e `como_resolver`:

| causa | o que significa | o que fazer |
|---|---|---|
| `admin` | “acesso negado” — a janela da API não está elevada | botão direito no `arrumar-pc.bat` → **Executar como administrador** |
| `sumiu` | o item já não existia (o Windows mudou sozinho) | nada |
| `tempo` | o comando estourou o tempo | tentar de novo; a saída fica no diário |
| `pulado` | o PID mudou entre a leitura e o `taskkill` | nada: era a trava fazendo o trabalho |
| `parado` | já estava parado | nada |
| `outro` | recusa por outro motivo | a saída do Windows, item por item, no diário |

E o aviso vem **antes**: `planejar()` devolve `elevado`, `precisam_admin` e
`aviso_admin`. Sem elevação, o plano já diz “13 de 16 vão falhar com acesso
negado”. A aba **Limpeza** mostra esse aviso antes do clique (ela pede o plano com
`planejar_apenas`, sem executar nada).

No chat, o relatório deixa de despejar `- falhas_por_causa: {'admin': 13}` e passa
a ser texto: o resumo com a causa, os nomes que não foram feitos, o próximo passo,
o instantâneo, o diário e o estado do ponto de restauração.

### 11.2 Saber que está trabalhando — sem inventar progresso

A bolha do chat agora mostra três coisas que são **medidas**, não decorativas:

- **o que** está rodando (“Arrumando a máquina (limpeza)”, ou o nome da skill);
- **há quanto tempo** (`00:42`), atualizado a cada segundo;
- **o limite** daquela skill — o mesmo `timeout_seconds` que o servidor usa em
  `asyncio.wait_for` (300 s para `maquina.arrumar`, 180 s para `desfazer`).

Aos 40% do limite a linha fica âmbar (“Ainda rodando — pode cancelar sem estragar
nada”); no limite, vermelha (“Passou do limite: confira se a janela da API ainda
está aberta”). E existe **Cancelar** de verdade: o pedido é abortado no navegador
(`AbortController`) e a resposta diz que o que já rodou está no diário.

O que **não** existe: barra de porcentagem da limpeza. O trabalho é uma fila de
comandos do Windows, e cada comando só informa sucesso ou falha no fim — uma barra
enchendo ali seria animação, não medição.

---

## 12. Administrador: por que o JARVIS não resolve sozinho (e o que ele faz)

Desativar **tarefa agendada** (`schtasks /Change`) e **serviço** (`sc config`) é
ação que o Windows só aceita de processo elevado. Fechar processo e apagar cache
do próprio usuário, não. Foi por isso que o primeiro uso real deu 3 ações certas e
13 falhas de “acesso negado”, todas do mesmo motivo.

**O que não existe:** um programa se tornar administrador sozinho. O controle de
conta de usuário (UAC) é justamente a barreira contra isso — quem clica **Sim** é
você, na tela. Qualquer programa que dissesse “eu me elevo sem te perguntar”
estaria explorando uma falha do Windows.

**O que passou a existir (0.72.0):**

| onde | o que acontece |
|---|---|
| tela `/maquina` → aba **Limpeza** | quando o plano diz `elevado: false`, aparece **Reabrir como administrador** — um clique, e o Windows pergunta |
| chat | `reinicia como administrador` (skill `maquina.administrador`) |
| `arrumar-pc.bat` e `desfazer-limpeza.bat` | **se elevam sozinhos**: duplo clique basta, sem botão direito. Se você recusar o UAC, seguem sem elevação e dizem o que vai falhar |
| recusa | nada é reiniciado, nada é alterado — e o relatório diz “você clicou Não” em vez de fingir sucesso |

O mecanismo: o JARVIS escreve `storage/subir-como-admin.bat` (ASCII/CRLF) e chama
`ShellExecuteW(..., "runas", ...)`. Esse auxiliar espera 4 s (para a resposta do
pedido sair), encerra a instância atual com `server.instancia --parar --sim` e sobe
`iniciar-jarvis.bat` elevado — que já liga `JARVIS_HOST_ARRUMAR=1`.

**O que isso não muda:** ele continua sem tocar em driver, essencial, WinSxS,
Windows.old, `C:\Windows\Installer` ou Prefetch. Elevação é permissão, não
permissividade.
