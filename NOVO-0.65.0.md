# JARVIS 0.65.0 — debloat: o que sai do Windows sem quebrar nada

As cinco fotos do Gerenciador de Tarefas mostram **três coisas diferentes na
mesma lista**, e é por isso que quase todo “debloat” da internet quebra alguma
coisa:

| o que aparece nas fotos | de onde vem | é lixo? |
|---|---|---|
| Google Drive, Chrome, Office Click-to-Run, Edge WebView2 | programa **que você instalou** e usa | **não** |
| NVIDIA Container, NVIDIA Web Helper, NVIDIA Driver Helper, Stereo Vision | **driver** — já explicado em `processos.py` | **não**, e não ocupa disco |
| Solitaire, Tempo, Notícias, Hub do Office, Xbox overlay, `DiagTrack`, tarefas `\Microsoft\Windows\*` | **Windows de fábrica** | **sim** — é aqui que está o ganho |

O JARVIS agora separa as três e **só põe no plano a terceira**.

## `maquina.debloat` — o diagnóstico

Lê a máquina de verdade (`Get-AppxPackage`, `Win32_Service`, `Get-ScheduledTask`,
`Test-Path`) e cruza com um catálogo de **35 apps, 18 serviços, 13 tarefas e 10
itens de espaço**. Só entra no relatório o que **existe** ali.

Três vereditos, e a diferença entre eles é o que evita estrago:

- **sobra** — sai sem perda: MSN Tempo/Notícias/Finanças, Solitaire, Hub do
  Office, Clipchamp, Mapas, Filmes e TV, telemetria (`DiagTrack`,
  `dmwappushservice`, `MapsBroker`), tarefas `CEIP`, `Autochk\Proxy`, lixeira,
  temporários, cache de atualização.
- **cuidado** — depende de como você usa: Xbox/Game Bar, Teams, Vínculo com o
  Telefone, Otimização de Entrega, Superfetch, Windows Search, WinSxS,
  hibernação, **NVIDIA Container**.
- **essencial** — tirar quebra algo: Microsoft Store, `winget`, Segurança do
  Windows, runtime VCLibs/UI.Xaml, Calculadora, Fotos, Ferramenta de Captura,
  Spooler, Wi-Fi, áudio, horário, `C:\Windows\Installer`.

App instalado que não está no catálogo vai para **“fora do catálogo”** e não
recebe palpite — o mesmo princípio de `maquina.processos`.

## `maquina.limpar` — o script que você lê antes

Devolve **dois** arquivos, em CRLF, uma linha por comando:

- **`debloat.bat`** — começa com `net session` (avisa se não for administrador),
  faz `pause` antes de cada bloco, e **só o que é sobra vem ativo**. O que é
  cuidado entra **comentado** com `rem`, para você descomentar só o que não usa.
- **`restaurar-windows.bat`** — `sc config ... start= auto|manual` (no tipo
  original do serviço, não num chute), `schtasks /ENABLE` em cada tarefa, e o
  comando de volta de cada app.

Trecho real, gerado a partir de uma máquina simulada:

```bat
rem ---------- 1. apps de loja sem uso ----------
rem Solitaire Collection - jogo de cartas com anúncio e assinatura
powershell -NoProfile -Command "Get-AppxPackage -Name Microsoft.MicrosoftSolitaireCollection_8wekyb3d8bbwe | Remove-AppxPackage"

rem ---------- 3b. servicos que dependem do seu uso ----------
rem NVIDIA Container: imagem e FPS iguais; perde painel, gravação e aviso de driver
rem sc config NvContainerLocalSystem start= disabled
```

## O espaço, medido onde dá e admitido onde não dá

| item | ganho | observação |
|---|---|---|
| `Windows.old` | 5 a 20 GB | não se apaga na mão (dono é o `TrustedInstaller`): a linha abre a tela certa |
| Cache de atualização | 300 MB – 3 GB | já instalado continua instalado |
| Temporários | 200 MB – 4 GB | fecha os programas antes |
| Lixeira | 0 – 30 GB | some de vez, confira antes |
| WinSxS por `DISM /StartComponentCleanup /ResetBase` | 1 – 8 GB | **opcional**: mantém atualizável, mas não desinstala atualização antiga |
| `hiberfil.sys` por `powercfg /h off` | ~40% da RAM | **opcional**: perde hibernar e início rápido |

Duas armadilhas ficam **de fora com o motivo escrito**: `C:\Windows\Prefetch`
(deixa o programa abrir rápido) e `C:\Windows\Installer` (é o cache de
desinstalação — apagar quebra o “Desinstalar” de vários programas). Ambas estão
marcadas como essenciais, **com o campo de comando vazio**.

## A tela

`/maquina` ganhou a aba **Limpeza**, ao lado de Processos e Pendrive:

- quatro números: apps de loja sem uso, tarefas de telemetria, serviços sem uso,
  caches a limpar;
- o **script inteiro** num bloco escuro, com *Copiar*, **Salvar debloat.bat** e
  **Salvar restaurar.bat**;
- as listas por categoria, cada linha expansível (o que é / se remover / se parar
  / comando / desfazer), com o selo do veredito;
- “apps fora do catálogo” e um cartão com o que o plano **nunca toca**.

## O que eu me recuso a fazer

- **Executar a limpeza.** `subprocess.run` existe uma vez só no módulo (a função
  `_ps`), e ela só recebe script fixo do catálogo. Não há skill que rode o `.bat`.
- **Remover driver.** O NVIDIA Container aparece como *cuidado*, com o texto de
  `processos.py`, e o comando vem comentado.
- **Apagar pasta de sistema na mão.** WinSxS vai por `DISM`; `Windows.old` vai
  pela tela do Windows.
- **Listar o essencial como opção.** Store, `winget`, Segurança, VCLibs, Fotos,
  Spooler, Wi-Fi, áudio e horário não aparecem nem comentados.

## Testes

- `pytest server/tests` → **2.970 passed** (`test_limpeza.py`: 23).
- Os 23 travam: todo app do catálogo com nome e explicação; Store/VCLibs/
  Segurança/`winget` como essenciais; NVIDIA como cuidado; Prefetch e Installer
  essenciais **sem comando**; app instalado virando ficha; desconhecido sem
  palpite; sobra somando só sobra; item não instalado fora da lista; serviço
  voltando ao **tipo original**; script começando com `@echo off` e checando
  administrador; só sobra como comando ativo; cuidado com `rem`; essencial
  ausente; `restaurar` religando serviço e tarefa; resumo contando o que sai;
  aviso de que nada foi executado; `subprocess.run` uma vez só, sem `shell=True`
  nem `os.system`; fora do Windows explicando; e medição de pasta opt-in.
- `vitest` → 124, `tsc -b` limpo, build embutido ok.
- Skills: **302 → 304**.

A referência está em `server/limpeza.py`: a classificação vem da documentação da
Microsoft sobre serviços e tarefas do Windows 10/11 e do comportamento das
próprias caixas de diálogo. Nenhum `.bat` de terceiro foi copiado ou executado.
