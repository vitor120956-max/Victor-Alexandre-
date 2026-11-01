# JARVIS 0.70.0 — por que aquilo é proibido, e o backup que resolve

Você perguntou duas coisas:

1. **por que** o JARVIS não mexe naqueles itens;
2. se não seria bom **fazer um backup na nuvem antes de remover**, para ele ter
   controle e tirar só o que não é útil.

A segunda pergunta está certa no instinto e errada na ferramenta — para uma parte
deles. Para a outra parte, era exatamente o que faltava. Segue o porquê, item por
item, e o que mudou.

## 1. Backup não salva o que quebra *na hora*

| item | o que acontece nos 5 minutos seguintes | backup resolve? |
|---|---|---|
| **Spooler** | nenhuma impressora funciona — nem “salvar em PDF” | não: o problema é o tempo até restaurar |
| **áudio** | a máquina fica muda | não |
| **Wi-Fi** | sem rede — **e sem rede não existe nuvem para restaurar** | péssimo: o backup depende da conexão que acabou de cair |
| **horário** | hora erra → certificado de site falha → quase todo HTTPS quebra | não |
| **Store / winget** | é **o caminho de volta** de todo o resto | não: você apagaria a própria ferramenta de restaurar |
| **VCLibs / UI.Xaml** | quebra apps que **nem estão na lista** | não: é dependência compartilhada |
| **driver NVIDIA** | perde painel/ShadowPlay; volta reinstalando do site | não é dado |

Nada disso é “arquivo que se guarda”: são serviços e bibliotecas em uso. O backup
não evita o estrago, só documenta.

## 2. Backup não faz sentido para os “grandes”

| item | o que é | por que backup é a ferramenta errada |
|---|---|---|
| **WinSxS** | componentes que o Windows guarda para se atualizar | 5–10 GB. O certo é `DISM /StartComponentCleanup`, que apaga **só a versão antiga** e mantém o sistema atualizável |
| **Windows.old** | a versão anterior do Windows | some sozinha em 10 dias; copiar = não limpar |
| **`C:\Windows\Installer`** | cache de desinstalação dos MSI | 1–3 GB **sem volta útil**: os MSI apontam caminho absoluto, um zip disso não reinstala nada |
| **Prefetch** | índice que deixa o programa abrir rápido | ganho de MB; o custo é boot mais lento |

## 3. O backup que **faz** sentido — e agora acontece sozinho

Antes de qualquer remoção, o JARVIS faz duas coisas:

**a) Instantâneo do estado — KB, sempre**

`storage\limpezas\instantaneo-AAAAMMDD-HHMMSS.json` com:
lista de apps de loja (nome + `PackageFullName`), estado de **cada** serviço
(rodando/parado, modo de início) e estado de **cada** tarefa.

É do tamanho de um e-mail — cabe no Drive, no pendrive ou num anexo — e é o que
permite reinstalar pela Store e saber como cada serviço estava.

**b) Ponto de restauração do Windows — 1 a 2 GB, local**

`Checkpoint-Computer "JARVIS antes da limpeza"`. É o único mecanismo que o Windows
tem para voltar **driver, serviço e registro**. Para voltar tudo: `Win+R` → `rstrui`
→ escolher o ponto.

Se a Proteção do Sistema estiver desligada (é comum), o ponto falha — e o relatório
**diz isso** em vez de fingir que salvou. A limpeza segue com o instantâneo.

> Sobre “nuvem”: o JARVIS não envia nada para fora por conta própria — não há
> chave, não há API. O instantâneo fica em `storage\limpezas\`; se quiser na nuvem,
> é o `drive.*` (já existe no projeto) apontando para esse arquivo de 3 KB. Mandar
> o Windows inteiro seria lento, caro e pior que o `rstrui`.

## 4. Modo ousado — o controle que você pediu

O que **tem volta** deixou de ser proibido e virou escolha:

| entra no modo ousado | volta como |
|---|---|
| Xbox / Game Bar | Store |
| Teams (consumidor) | painel de programas |
| Windows Search (indexador) | `sc config WSearch start= auto` |
| Superfetch (SysMain) | `sc config SysMain start= auto` |
| Otimização de Entrega | `sc config DoSvc start= auto` |
| hibernação (`hiberfil.sys`) | `powercfg /h on` |

Como ligar:

- **tela** `/maquina` → aba **Limpeza** → checkbox **“Modo ousado”**;
- **`.bat`** → tecla **O** quando `arrumar-pc.bat` perguntar;
- **skill** → `maquina.arrumar` com `ousado: true`.

O que **não** tem volta continua fora **nos dois modos**: WinSxS, Windows.old,
`C:\Windows\Installer`, Prefetch, driver (NVIDIA Container) e essencial.

## Resumo em uma linha

Braço não é “faz tudo”: é **fazer o que dá para fazer sem te deixar no escuro**,
guardar o caminho de volta, e dar a chave do que é escolha sua — não decisão dele.

## Testes

- `pytest server/tests` → **3.035 passed, 7 skipped** (`test_arrumar.py`: 34).
- Os 10 novos travam: instantâneo com apps/serviços/tarefas e **menos de 4 KB**;
  fora do Windows explicando; ponto de restauração que relata falha sem derrubar a
  limpeza e que reconhece o “criado”; `executar` gravando foto e ponto no diário
  (e o `como_voltar_tudo` citando `rstrui`); `ponto=False` apontando o instantâneo;
  **modo ousado trazendo `cuidado` e nunca `essencial`**; hibernação no ousado e
  WinSxS/Windows.old/Installer/Prefetch fora dos **dois** modos.
- `vitest` → 124, `tsc -b` limpo, build embutido ok.
- Skills: **306** (as duas de braço ganharam `ousado` e `ponto_de_restauracao`).
