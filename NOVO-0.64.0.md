# JARVIS 0.64.0 — o que está aberto e o que vai no pendrive

Três perguntas suas, nesta ordem:

1. “tem mais melhorias, plugins e drivers que dá para baixar e deixar no pendrive?”
2. “tem algo no PC e não no pendrive?”
3. “no Gerenciador de Tarefas tem coisas abertas que não precisam, tipo o NVIDIA Container”

A primeira e a segunda são a mesma pergunta vista dos dois lados. A terceira
parece outra coisa, mas é a mesma raiz: **o que é do sistema e o que é ferramenta
solta**. Driver é do sistema. Ferramenta é solta. O NVIDIA Container está aberto
porque é peça de driver — e é exatamente por isso que ele não vai para o pendrive.

## A resposta curta sobre o NVIDIA Container

Ele **não desenha nada**. Quem desenha é o driver de vídeo, e o driver continua
funcionando com ele fechado. O `nvcontainer.exe` serve ao painel da NVIDIA, ao
ShadowPlay e à checagem de atualização do driver.

| pergunta | resposta |
| --- | --- |
| é vírus ou telemetria de terceiro? | não — é do próprio pacote de driver |
| fechar melhora imagem ou FPS? | **não**. Nada muda no jogo |
| quanto devolve? | 60 a 150 MB de RAM |
| o que se perde? | painel da NVIDIA, gravação do ShadowPlay, aviso de driver novo |
| volta sozinho? | sim, no próximo boot ou quando o painel abre |

Parar, voltar e não voltar no boot:

```bat
taskkill /IM nvcontainer.exe /F
sc config NvContainerLocalSystem start= auto  &&  net start NvContainerLocalSystem
```

Para não voltar: **Serviços** → `NvContainerLocalSystem` → Inicialização: **Manual**.
O `nvdisplay.container` se recria sozinho — parar ele é enxugar gelo.

## `maquina.processos` — o Gerenciador de Tarefas com veredito

Lê a lista real da máquina (`Get-Process` via PowerShell, com janela oculta) e
classifica cada processo em cinco grupos:

| grupo | exemplos | o que significa |
| --- | --- | --- |
| **sobra** | Steam Web Helper, SearchUI, OneDrive, GameBar, YourPhone, GoogleCrashHandler | pode fechar: devolve RAM, nada que você usa cai |
| **driver** | NvContainer, nvsphelper64, NvTelemetryContainer | peça do driver: fechar é seguro e não muda imagem/FPS |
| **cuidado** | Chrome, Edge, SearchIndexer, antivírus | funciona, mas fechar atrapalha |
| **essencial** | System, csrss, lsass, svchost, explorer, dwm | não feche: o Windows cai ou a sessão termina |
| **próprio** | node, python, pythonw | é o JARVIS: fechar derruba esta tela |

Cada linha abre com **o que é**, **se parar**, **o comando**, **como desfazer** e
**como impedir no boot**. Processo fora do catálogo vai para **não classificados**
e não recebe palpite nenhum — 400 processos numa máquina real, 45 fichas escritas
à mão; o resto é honestamente “não sei”.

Duas decisões que valem dizer em voz alta:

1. **Nada é fechado.** O módulo lê e devolve o comando. Tem teste que varre o
   código e falha se aparecer `os.kill`, `TerminateProcess` ou `Stop-Process -Name`.
2. **Não prometo FPS.** A ficha do NVIDIA Container diz, com essas palavras, que
   fechar não aumenta FPS. Tem teste que falha se essa frase sumir.

## `maquina.portatil` — 18 que vão, 9 que não vão

Portátil de verdade é `.exe` que roda sozinho, sem instalar e sem reiniciar.
O catálogo inteiro ocupa **≈ 454 MB**:

| ferramenta | MB | libera |
| --- | --- | --- |
| ADB + scrcpy | 30 | `acesso-celular`, `celular.*` |
| 7-Zip (extraível) | 2 | `backup.*` |
| SumatraPDF | 8 | `biblioteca.*` |
| Everything | 3 | `files.buscar` |
| Sysinternals | 12 | `sistema.*` |
| CrystalDiskInfo | 6 | `sistema.disco` |
| HWiNFO | 10 | `estacao.*` |
| Tesseract | 60 | `biblioteca.ocr` |
| FFmpeg | 90 | `video.*`, `legenda.*` |
| Notepad++ · KeePassXC · WinMerge | 6 · 40 · 12 | `revisao.*` |
| ImageMagick · HxD | 30 · 3 | `estudio.*`, `reversa.*` |
| VLC · Rufus · Ventoy · TestDisk | 45 · 2 · 70 · 25 | `sistema.instalar`, `recuperar.*` |

Só **Sysinternals (com detalhe), TestDisk, Rufus e Ventoy** pedem administrador —
e pedem porque escrevem em disco bruto, não por descuido.

### E a lista que importa: o que é do PC e **não** vai

| item | por que não |
| --- | --- |
| driver de vídeo (NVIDIA/AMD/Intel) | vira **serviço** no Windows e pede reinício — é ele que roda o NVIDIA Container |
| .NET Framework / Desktop Runtime | instala em `C:\Windows\Microsoft.NET` e registra na máquina |
| Visual C++ Redistributable | DLL vai para `System32`/`WinSxS`; o programa depende da versão registrada |
| Npcap / WinPcap | driver de rede em modo kernel, reinicia a placa |
| antivírus | serviço em kernel, atualização constante, dois brigam |
| Office | licença e ativação são da máquina |
| Docker Desktop / WSL 2 | Hyper-V e serviço: ou o recurso do Windows está ligado, ou não roda |
| JRE do sistema | o `.exe` até é portátil; `JAVA_HOME` e o registro não são |
| driver de impressora, Bluetooth, Wi-Fi | driver de dispositivo é do Windows, não do pendrive |

Resumo: **ferramenta portátil é arquivo, driver é instalação.** Por isso a
resposta é 18 + 9 em vez de “27 ferramentas no pendrive” — que seria mentira em
9 delas, e mentira que você descobriria na hora de usar.

## `maquina.plano` — e em que ordem baixar

A ordem não é alfabética, é “o que destrava mais coisa primeiro”: **ADB + scrcpy**
na frente (é o que libera o celular), depois o que faz o PC caber em 4 GB de RAM
(7-Zip, SumatraPDF, Everything, Sysinternals), e por último o que é grande e
opcional (FFmpeg, Ventoy). Cada etapa traz MB, acumulado e site oficial.

**Nada é baixado por aqui.** Baixar é `sistema.baixar` (quarentena + SHA-256) e
`sistema.assinatura` (conferência). Tem teste que falha se `urlopen`,
`requests.get` ou `subprocess.run` aparecerem no módulo.

## A tela

`/maquina` (menu **Máquina**), duas abas:

- **Processos** — quatro números no topo (lidos, sobras recuperáveis, driver
  NVIDIA, não classificados), o cartão do NVIDIA Container em destaque com os
  três comandos clicáveis para copiar, e os cinco grupos com linha expansível
  (o que é / se parar / comando / desfazer / no boot).
- **Pendrive** — quantos dos 18 já estão na pasta, quanto falta baixar, o plano
  em ordem com acumulado, os 18 em cartão (com “no pendrive” marcado) e a lista
  dos 9 que não vão, com o motivo técnico de cada um.

## Limites que ficam ditos

- A leitura de processos é do **Windows**. Fora dele a skill devolve
  `lido: false` e o motivo, em vez de fingir uma lista vazia.
- O catálogo é **curado à mão**: tamanho em MB é estimativa de download, não
  medição do arquivo. Nenhum link é aberto para conferir.
- `medir()` procura o executável pelo nome (`scrcpy.exe`, `procexec*.exe`,
  `7z*.exe`) na pasta `ferramentas` e na raiz do projeto; ferramenta com nome
  trocado aparece como ausente.
- Fechar processo em lote, desinstalar driver ou mexer em serviço **não** existe
  como skill — nem vai existir sem você mandar fazer, uma por uma.

## Testes

- `pytest server/tests` → **2.947 passed** (`test_processos_portatil.py`: 20).
- Os 20 travam: o veredito de cada grupo, a frase “não aumenta FPS”, o comando e
  o desfazer do NVIDIA Container, memória somada por grupo, sobras em ordem
  decrescente, processo desconhecido sem palpite, o aviso de que nada foi
  fechado, a varredura anti-`taskkill` no código, o “fora do Windows”, nome com
  caminho/`NVSPHELPER64`/`python.exe`, licença e URL em todos os 18 itens, o
  “não dá” explicado nos 9, ADB+scrcpy primeiro no plano, `medir()` com pasta
  falsa e as três skills no registro sem efeito colateral.
- `vitest` → 124, `tsc -b` limpo, build embutido ok.
- Skills: **299 → 302**.
