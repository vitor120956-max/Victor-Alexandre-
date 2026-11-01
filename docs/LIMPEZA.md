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
