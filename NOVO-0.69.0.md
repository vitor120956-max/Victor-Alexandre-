# JARVIS 0.69.0 — os braços

Você disse a frase que muda o desenho:

> “eu não quero ter que fazer nada, por isso fiz o JARVIS com braços”

Até a 0.68.0 o debloat era **relatório**: o JARVIS lia a máquina e entregava um
`.bat` para você ler, salvar e rodar como administrador. Isso não é braço — é
dever de casa.

Agora ele **faz**.

## Um botão, ou um duplo clique

| onde | o que fazer |
|---|---|
| tela `/maquina` → aba **Limpeza** | botão **“Arrumar agora”** |
| sem abrir a tela | duplo clique em **`arrumar-pc.bat`** (mostra o plano, pergunta `S`, executa) |
| voltar atrás | botão **“Desfazer a última”** ou **`desfazer-limpeza.bat`** |
| pelo chat/skill | `maquina.arrumar` / `maquina.desfazer` |

Nada de copiar comando, nada de abrir PowerShell, nada de “agora vá em Serviços e
mude tal coisa para Manual”.

## O que ele executa

| tipo | ação |
|---|---|
| **processo** | `taskkill /PID` nas sobras — Steam Web Helper, SearchUI, OneDrive, GameBar, GoogleCrashHandler… |
| **app de loja** | `Remove-AppxPackage` no que é sobra — Solitaire, MSN Tempo/Notícias, Clipchamp, Mapas, Filmes e TV |
| **tarefa** | `schtasks /DISABLE` nas tarefas de telemetria (CEIP, Autochk Proxy, DmClient, ProgramDataUpdater) |
| **serviço** | `sc config … start= disabled` nos sem uso (DiagTrack, MapsBroker, RetailDemo, RemoteRegistry…) |
| **espaço** | `%LOCALAPPDATA%\Temp`, `C:\Windows\Temp`, cache de atualização, Otimização de Entrega, lixeira |

Tudo numa passada, com o resultado item por item na tela: ✓ e o ganho, ou ✕ e o
motivo (quase sempre “precisa de administrador”).

## O que ele **nunca** toca

- **driver** — NVIDIA Container, nvsphelper64, NvTelemetry seguem como `cuidado`;
- **essencial** — Microsoft Store, `winget`, Segurança, VCLibs/UI.Xaml, Calculadora, Fotos, Captura, Spooler, Wi-Fi, áudio, horário;
- **cuidado** — Xbox/Game Bar, Teams, Vínculo com o Telefone, Superfetch, Search, **WinSxS**, **hibernação**, **Windows.old**;
- **`C:\Windows\Installer`** e **`Prefetch`** — essenciais no catálogo, sem comando;
- **processo por PID velho** — antes de matar, confere se aquele PID ainda é o mesmo processo **e** continua sendo sobra. PID é reciclado pelo Windows e matar por número antigo fecha programa alheio. Tem teste para isso.

## As quatro travas que sobraram

1. **`JARVIS_HOST_ARRUMAR=1`** — o `iniciar-jarvis.bat` liga (é o que faz o botão funcionar); quem quer o JARVIS só olhando põe `0` no `.env`;
2. **token de host** — preenchido sozinho quando o pedido vem desta máquina;
3. **confirmação** — sem `confirmed`, a API recusa antes de chegar no módulo;
4. **diário** — cada ação grava comando, saída e desfazer em
   `storage/limpezas/limpeza-AAAAMMDD-HHMMSS.json`.

Cada uma existe porque já evitou estrago real. Braço não é carta branca.

## Desfazer, sem mentir

| ação | volta? |
|---|---|
| serviço desativado | **sim** — volta ao tipo original (`auto` ou `manual`, conforme era) |
| tarefa desativada | **sim** — `schtasks /ENABLE` |
| app de loja removido | **sim** — pela Microsoft Store |
| processo fechado | **não** — abre de novo quando precisar |
| cache e lixeira | **não** — eram lixo por definição |

O relatório diz nominalmente o que ficou `sem_volta`, em vez de dizer “desfeito” e
esconder que a lixeira não volta.

## Arquivos novos

| arquivo | papel |
|---|---|
| `server/arrumar.py` | planeja, executa, grava o diário e reverte |
| `arrumar-pc.bat` | duplo clique: plano → `S` → executa (liga a trava só neste processo) |
| `desfazer-limpeza.bat` | duplo clique para reverter o último diário |
| `maquina.arrumar` / `maquina.desfazer` | as skills (`side_effects=True`, `requires_confirmation=True`) |
| aba **Limpeza** | o painel “Não quero apertar nada” com os dois botões |

## Testes

- `pytest server/tests` → **3.025 passed, 7 skipped** (`test_arrumar.py`: 24).
- Os 24 travam: fora do Windows explica em vez de rodar `cmd /c`; só `sobra` vira comando (teste que quebra se alguém liberar driver/essencial/cuidado); `ESPACO_SEGURO` sem WinSxS/hibernação/Windows.old; as três recusas (sem trava, sem confirmação, token errado) **com o executor nunca chamado**; execução gravando o diário com data fixa; falha em uma ação não impedindo as outras; **PID reciclado sendo pulado** e PID legítimo sendo encerrado; plano vazio não gravando diário mentiroso; desfazer revertendo serviço/tarefa, listando o `sem_volta`, pegando o diário mais novo; os dois `.bat` em ASCII puro/CRLF com `goto` consistente, plano antes do `S`, e o texto dizendo o que não toca.
- `vitest` → 124, `tsc -b` limpo, build embutido ok.
- Skills: **304 → 306**.
