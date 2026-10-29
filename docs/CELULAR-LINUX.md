# Celular velho como PC/Linux — o caso do Galaxy J7 Prime

Este documento responde a uma pergunta concreta: **dá para transformar um Galaxy
J7 Prime em um PC com Linux?** A resposta curta é **sim**, e quem tem a tela
quebrada não está fora do jogo: o `scrcpy` transforma o celular em uma janela do
Windows — a tela física deixa de ser necessária. A condição que decide tudo é se
a *Depuração USB* já esteve ligada (§3).

O modelo é um dos melhores candidatos possíveis para Linux: port no Nura,
LineageOS e /e/OS.

Nada aqui é executado pelo JARVIS. Ele não tem `adb` nem `fastboot`; todo comando
no celular é feito por você, na mão. O que ele faz é o que está na última seção.

---

## 1. O aparelho

| Item | Valor |
|---|---|
| Modelos | SM-G610F, SM-G610F/DS, SM-G610M, SM-G610M/DS, SM-G610Y |
| Codename (o que importa) | **`on7xelte`** |
| SoC | Samsung Exynos 7870 — 8× Cortex-A53 até 1,6 GHz, 14 nm |
| GPU | Mali-T830MP2 |
| RAM | 3 GB |
| Tela | 5,5" IPS, 1920×1080 |
| Armazenamento | 16/32 GB + microSD até 128 GB |
| Bateria | 3300 mAh **não removível** |
| Android de fábrica | 6.0.1 (atualizações até Oreo em boa parte das variantes) |

O codename é o que os projetos de Linux usam. "Galaxy J7 Prime" não serve: existe
o **J7 Prime 2** (`on7xreflte`, SM-G611x), que é outro aparelho e não aceita as
mesmas ROMs nem os mesmos dtb. Confira em **Configurações → Sobre o telefone →
Número de compilação**, ou no adesivo atrás da tampa.

---

## 2. O bloqueio: a tela não funciona

Sem imagem, você não consegue nenhuma destas quatro coisas — e todas são
pré-requisito para "virar PC":

1. ligar **Depuração USB** (Opções do desenvolvedor → precisa do toque 7× em
   "Número da compilação" e de navegar);
2. aceitar o popup **"Permitir depuração USB?"** — o `adb` recusa o aparelho até
   isso ser tocado;
3. navegar no recovery para escolher *install*, *wipe* ou *reboot*;
4. ler qualquer progresso de flash.

E o J7 Prime **não tem saída de vídeo por cabo**: nada de MHL ou HDMI. Não há
"espelhar no monitor" por hardware, e o modo Download/Recovery só aparece na
própria tela. Mouse por OTG também não resolve: o touch pode até responder, mas
sem imagem não há o que clicar.

> **Conclusão parcial:** pela via normal (toque na tela) o projeto está travado.
> Mas existe **uma** saída pelo PC — o `scrcpy` — e ela depende de uma coisa só:
> se a *Depuração USB* já esteve ligada neste aparelho. Está no §3, antes de você
> gastar dinheiro com a peça.

### Diagnóstico antes de comprar a peça (5 minutos, custo zero)

1. **Carregue 20 min.** Se o aparelho esquentar na região do conector ou vibrar
   ao ligar, a placa está viva — só falta imagem.
2. **Ligue no PC por USB.** No Gerenciador de Dispositivos, veja se aparece algo
   como *SAMSUNG Mobile USB Composite Device* ou *MTP*. Se aparecer, a placa
   inicializa.
3. **Segure Volume − + Power por 10 s.** Se houver vibração, o bootloader roda.
4. **Ligue na tomada e olhe a tela de perto, com luz forte e de lado.** Se houver
   um brilho cinza fraco, o backlight vive e pode ser só o flex do display.
5. **Teste um carregador com outro cabo.** Antes de condenar o aparelho, elimine
   o óbvio.

Se 1, 2 e 3 falharem, pode ser placa, não tela — aí a peça não resolve.

---

## 3. Acesso pelo PC com a tela morta: `scrcpy`

**É assim que os vídeos funcionam.** O painel pode estar morto — a GPU continua
desenhando no *framebuffer*. O `scrcpy` lê esse framebuffer pelo `adb`, mostra a
tela do celular numa janela do Windows e devolve mouse e teclado como toque. Com
isso o J7 Prime deixa de precisar da tela **para sempre**: fica ligado ao PC (ou
com um adaptador de rede) e você o opera inteiro pela janela.

O que decide entre "5 minutos" e "impossível" é uma pergunta:

### 3.1 Primeiro, o teste de 2 minutos (custo zero)

No PC, baixe **Android Platform-Tools** e **scrcpy** (o `scrcpy` já traz o `adb`
na versão do Windows, mas o platform-tools separado facilita). Conecte o celular
e rode:

```bat
adb devices
```

Três respostas possíveis — e cada uma é um caminho diferente:

| Saída | O que significa | O que fazer |
|---|---|---|
| `ABCD1234    device` | Depuração USB **ligada** e este PC já é confiável | **Ganhou.** `scrcpy` e pronto |
| `ABCD1234    unauthorized` | Depuração ligada, mas falta autorizar este PC | §3.2 (autorizar às cegas) |
| nada (`List of devices attached` vazio) | Depuração **desligada**, ou o celular não boota | §3.2 ou §3.3 |

### 3.2 Autorizar e navegar sem ver nada (`scrcpy --otg`)

O `scrcpy --otg` **não usa ADB**: ele faz o PC se passar por teclado e mouse USB.
Serve justamente para operar um celular com a tela morta.

```bat
scrcpy --otg
```

O que se digita vai para o celular às cegas. A sequência clássica para aceitar o
popup de autorização, usada pela comunidade:

1. `scrcpy --otg`, digitar o **PIN** da tela de bloqueio e `Enter`;
2. fechar a janela e rodar `scrcpy` normal para o popup "Permitir depuração USB?"
   aparecer no celular;
3. `scrcpy --otg` de novo: **`Tab`, `Enter`, `Tab`, `Tab`, `Enter`** (em alguns
   aparelhos o `Enter` é `Espaço`);
4. com a autorização aceita, rodar `scrcpy` e a tela aparece no PC.

Depois de autorizado, dá para deixar de digitar o PIN às cegas:

```bat
adb shell locksettings clear --old 1234
```

Para o aparelho não voltar a pedir autorização: em Opções do desenvolvedor,
ligue **"Desativar tempo limite de autorização do adb"** (o padrão expira em 7
dias). Se a tela for definitivamente morta, isso é obrigatório.

**O auxílio que ninguém lembra: TalkBack.** Segure **Volume + e Volume −** por
3 s para ligar o leitor de tela e navegue com um teclado USB por OTG — ele fala
em voz alta onde o foco está, o que permite "ver" o menu sem ver. É lento, mas é
o que transforma navegação às cegas em algo possível.

**Ressalvas honestas do `--otg`:** no Windows ele é o modo mais chato (às vezes
pede driver `libusb`/WinUSB); no Linux e no macOS funciona direto. A tela de
bloqueio aparece **preta** no espelhamento (proteção `FLAG_SECURE`), então a
primeira autorização tem que ser às cegas mesmo.

### 3.3 Se a depuração nunca esteve ligada

Aí as opções caem para:

1. **Tela de teste numa assistência.** A maioria das bancadas tem um display de
   teste: em 5 minutos você liga **Depuração USB**, **Desativar tempo limite**,
   **Desbloqueio OEM** e "sempre permitir este computador". Custa menos que a
   peça e resolve para sempre — o aparelho volta para a gaveta e você o usa pelo
   `scrcpy`.
2. **Comprar o módulo** (§4) e fazer o mesmo em casa.
3. **Navegação às cegas pelo `--otg` + TalkBack** — funciona em tese, mas chegar
   em *Configurações → Sobre → Número da compilação 7× → Opções do desenvolvedor*
   sem ver nada é muito sofrimento e não é garantido.

### 3.4 O caminho do recovery (só se o OEM já estiver desbloqueado)

O modo **Download** do Samsung é operável às cegas: **Volume − + Home + Power**
até aparecer, depois **Volume +** para confirmar. O Odin no PC enxerga o aparelho
por COM e existe TWRP para `on7xelte` (3.3.0, 3.6.0, 3.7.0 em fóruns). O TWRP
abre **ADB sem pedir autorização**, e dele dá para:

```bat
adb pull /sdcard C:\resgate\                 :: fotos, WhatsApp, documentos
adb shell "echo <sua-chave-publica> >> /data/misc/adb/adb_keys"   :: autoriza o PC no Android
```

**Mas:** o Odin **recusa** o flash sem o **Desbloqueio OEM** ligado antes — o erro
clássico é *"BLOCKED BY FRP LOCK"*. E o Desbloqueio OEM só se liga em
*Opções do desenvolvedor*, que fica atrás da tela. Ou seja: esse caminho só serve
se o aparelho já foi desbloqueado no passado. Além disso, flashar binário
customizado **aciona o Knox para sempre**.

### 3.5 Por que não existe o truque do dock

Em celulares USB-C que suportam saída de vídeo, dá para plugar um dock com HDMI,
monitor e mouse e usar o aparelho como se fosse um PC. **O J7 Prime não faz
isso**: é micro-USB, não tem MHL nem DisplayPort alternativo. Nele, o vídeo só sai
por `scrcpy` (que depende do ADB) ou por uma tela física.

---

## 4. A peça

| Opção | Faixa de preço (Brasil, 2026) | Observação |
|---|---|---|
| Módulo compatível (LCD+touch) | R$ 70 – 160 | O que se acha no Mercado Livre; qualidade variável |
| Módulo "premium"/nacional | R$ 100 – 160 | Lojas de peça (Brascell, Empório, d7) |
| Original Samsung | R$ 220 – 240 | Vale se o aparelho for ficar de uso diário |

Códigos que servem: **SM-G610F, G610F/DS, G610M, G610M/DS, G610Y/DS**. Peça
sempre "com aro", se possível: sem aro você precisa transferir o chassi e a chance
de quebrar o vidro na hora da colagem sobe muito.

**Cuidado com a bateria.** Aparelho de 2016, bateria colada e 3300 mAh. Se estiver
estufada (tampa traseira abaulada ou tela "saltando"), **não recarregue** — e não
deixe o aparelho como monitor fixo na tomada 24 h. Bateria de celular estufada é
risco real de incêndio.

---

## 5. Caminho A — Linux **dentro** do Android (recomendado)

Sem root, sem desbloquear nada, sem risco de perder o aparelho. Você instala o
Termux e ganha um Debian com `apt`.

**Requisito:** Android 7.0 ou mais novo e o APK do **F-Droid** ou do GitHub — a
versão da Play Store é outro ramo, experimental, e exige Android 11. Para Android
5/6 existem APKs "legacy" (`apt-android-5`) com repositório congelado.

```bash
# Termux (F-Droid)
pkg update && pkg upgrade -y
pkg install proot-distro openssh
proot-distro install debian
proot-distro login debian
```

Dentro do Debian:

```bash
apt update && apt install -y python3 git nano curl
python3 --version
```

Área de trabalho (opcional; em 3 GB prefira algo leve, não XFCE completo):

```bash
# no Termux
pkg install x11-repo && pkg install tigervnc
# dentro do Debian
apt install -y lxqt-core tigervnc-standalone-server
vncserver :1 -geometry 1280x720 -depth 24
```

Depois, um app de VNC no Android (bVNC, por exemplo) apontando para
`127.0.0.1:5901`.

**O melhor uso na prática:** com `openssh`, o celular vira terminal do seu PC.

```bash
ssh seuusuario@192.168.1.15     # IP do PC na rede local
```

Limites honestos do caminho A: sem root, **sem `systemd`** (`systemctl` não
existe), sem Docker, gráfico por software (lento), 200 MB a 2 GB por distro, e no
Android 12+ o "matador de processos fantasma" pode derrubar o shell.

---

## 6. Caminho B — Linux **no lugar** do Android (Nura)

O projeto que se chamava **postmarketOS** virou **Nura** em 27/09/2026
(`nura.eco`; `postmarketos.org` redireciona).

**Estado do `on7xelte`:** existe device package desde 2023, na categoria
**testing**, com **rede por USB**, touchscreen, Wi-Fi e bateria funcionando. Há
trabalho de mainline em andamento para o Exynos 7870 (dtb `exynos7870-on7xelte`,
kernel `linux-postmarketos-exynos7870`). "Testing" quer dizer: **liga e faz o
básico** — não quer dizer telefone confiável.

| O que costuma funcionar | O que costuma não funcionar |
|---|---|
| Tela, touch, Wi-Fi | Câmera |
| Rede por USB (ótimo: dá SSH sem tela!) | Chamadas por VoLTE |
| Bateria/energia | Sensores finos, GNSS |
| Terminal, SSH, Python | Aceleração gráfica completa |

**Riscos, sem enfeite:**

- desbloquear e flashar **aciona o Knox** de forma permanente;
- no Exynos 7870 o **Heimdall é notoriamente problemático** — a comunidade usa
  **Odin** ou TWRP;
- errar o passo do recovery pode **bricar** o aparelho;
- e, no seu caso específico: **tudo isso exige tela funcionando primeiro.**

Se um dia chegar lá, a ordem é: firmware estoque → TWRP/Boot → image do Nura →
`ssh` pela rede USB. O guia por aparelho fica na wiki do projeto.

---

## 7. Caminho C — só reviver o Android

Se o objetivo é "ter um celular usável de novo" e não "ter Linux", o melhor custo-
benefício é ROM Android leve:

- **LineageOS 18.1** (Android 11) para `on7xelte`;
- builds não oficiais de **/e/OS** (Android 12) para `on7xelte`;
- kernels alternativos do projeto Exynos7870.

Com 3 GB de RAM e Android 11/12 enxuto, o aparelho volta a ser utilizável — e aí
o Termux do caminho A roda melhor do que rodaria no Android 8 de fábrica.

---

## 8. O celular como tela/terminal do PC (funciona hoje, sem instalar nada)

Independente da tela do celular, o contrário também vale: o PC expõe o JARVIS na
rede e o celular abre no navegador.

```bat
cd /d D:\JARVIS
.venv\Scripts\python iniciar.py --host 0.0.0.0
ipconfig
```

No celular, na mesma rede Wi-Fi: `http://<IPv4-do-PC>:8000`. A interface tem
breakpoints para 480–760 px, então se adapta à tela do celular. O bloqueio de
origem (`403 ORIGEM_RECUSADA`) só barra página de **outro site**; e o modo dono
**não vale** para o celular — ele só preenche o token para requisição vinda de
`127.0.0.1`. Do celular, o token continua sendo pedido para o que grava ou executa.

---

## 9. As skills `celular.*` (0.60.0)

A partir da 0.60.0 o JARVIS tem o próprio caminho para isso. Cinco skills, e a
regra é a de sempre: leitura sem confirmação, execução com confirmação, e tudo
atrás de `JARVIS_HOST_CELULAR=1`.

| Skill | O que faz | Confirmação |
|---|---|---|
| `celular.status` | Mede o aparelho: `adb devices -l` (só leitura), estado de autorização e, quando o adb não vê nada, a USB do Windows com VID/PID (Samsung = `04E8`), separando o celular de driver genérico, dispositivo que o Windows viu mas não identificou (`VID_0000`) e código de problema do Windows. Compara a lista com a da checagem anterior (guardada em `storage/celular/usb-ultima.json`) e diz o que entrou ou saiu — o teste conectar/desconectar sem a pessoa comparar no olho. Também diz onde estão `adb` e `scrcpy`. | não |
| `celular.rede` | Varre a rede local (só leitura): IP, MAC, nome e portas abertas de cada dispositivo, com prefixo Samsung marcado e destaque para a 5555 do adb sem fio. Explica por que o Wi-Fi não substitui o cabo — sem Depuração USB ligada (ou sem `adb tcpip 5555` feito antes pelo cabo) o Android não abre porta nenhuma. | não |
| `celular.plano` | Mede o aparelho com `adb devices` e monta o caminho exato para o estado encontrado — inclusive “nunca foi ligada”. | não (só lê) |
| `celular.preparar` | Baixa platform-tools (Google) e scrcpy (GitHub) para `ferramentas/`, com SHA-256 e extração à prova de zip-slip. | **sim** |
| `celular.espelhar` | Abre o `scrcpy`: a tela do celular vira janela do Windows. Opcionalmente grava `.mp4`. | **sim** |
| `celular.puxar` | `adb pull` de DCIM, Pictures, Download, Documents, Movies, Music, WhatsApp e Telegram para `storage/celular/<data>`. | **sim** |

O que o `celular.puxar` **não** faz: não lê `/data`, não copia base de aplicativo,
não apaga nada no aparelho e não aceita destino fora da raiz de dados.

### Como ligar (o passo que costuma falhar)

O `.env` fica na raiz do projeto: `D:\JARVIS\.env`. Como o nome começa com ponto,
ele some no meio dos outros — e, no Bloco de Notas, digitar `.env` no campo de
nome costuma salvar como `.env.txt`, que o JARVIS não lê.

Para não errar, use o atalho:

```bat
cd /d D:\JARVIS
ligar-celular.bat
```

Se o aparelho não aparecer nem no Windows (o caso clássico: carrega, mas nada na
lista), abra a vigia antes de trocar de cabo — ela apita na hora em que algo
mudar:

```bat
cd /d D:\JARVIS
vigiar-usb.bat
```

ou, pelo Python:

```bat
.venv\Scripts\python configurar-celular.py
```

O script acha o `.env` (ou cria a partir do `.env.example`), **substitui** a linha
de `JARVIS_HOST_REDE`, `JARVIS_HOST_CELULAR` e `JARVIS_HOST_CONFIAR_LOCAL` se ela
já existir — sem duplicar chave —, grava em UTF-8 sem BOM com CRLF, renomeia um
`.env.txt` perdido e mostra o antes e o depois. Nenhuma outra variável é tocada.

A terceira, `JARVIS_HOST_CONFIAR_LOCAL=1`, é o **modo dono**: na própria máquina o
token é preenchido pelo servidor e você não digita nada; de outra máquina da rede
ele continua sendo pedido. É o que evita o campo de token aparecer para baixar o
`adb` e o `scrcpy`. Para desligar, troque `=1` por `=0` e reinicie.

Depois do `celular.preparar`, as ferramentas ficam em `storage\ferramentas\`:
`platform-tools\adb.exe` e `scrcpy\scrcpy.exe`. O zip oficial do scrcpy extrai
numa pasta com a versão no nome (`scrcpy-win64-v3.3.1\`), então o JARVIS renomeia
para `scrcpy\` — se você baixar na mão, saiba que esse é o layout esperado.

Depois, feche a janela da API (o X), suba de novo e confira a primeira linha do terminal:

```text
(rede=ligada, instalar=desligado, root=desligado, pc=desligado, celular=ligado, dono=desligado)
```

`rede=ligada` é obrigatório porque baixar o `adb` e o `scrcpy` é download.

### O que nenhum programa resolve

Ligar a Depuração USB e tocar em **“Permitir depuração USB?”** exige uma pessoa na
frente da tela. É consentimento local com assinatura RSA por computador — o
Android foi desenhado para que nenhum programa no PC contorne isso. Ferramenta que
promete “habilitar ADB em aparelho bloqueado” está vendendo outra coisa (ou nada).

O que existe de verdade é o desvio: **`scrcpy --otg`**, em que o PC se passa por
teclado e mouse USB. Isso não liga a depuração, mas permite navegar às cegas até
ligá-la — com TalkBack falando o foco, se preciso. O `celular.plano` entrega a
sequência pronta para cada situação.

### Exemplo de resposta do `celular.plano`

```text
Depuração ligada, PC não autorizado.

1. Entender o que falta
    adb devices  →  unauthorized
    ...
2. Autorizar às cegas com teclado USB
    scrcpy --otg
    digitar o PIN da tela de bloqueio e Enter
    scrcpy            (o popup “Permitir depuração USB?” aparece no celular)
    scrcpy --otg      (foco no popup: Tab, Enter, Tab, Tab, Enter)
...
O que nenhum programa faz: tocar em “Permitir depuração USB?”. Esse
consentimento é do Android, na tela. Todo o resto acima é automatizável.
```

## 10. O que o JARVIS faz e não faz aqui

**Faz** (e você pode pedir pelo chat):

| Pedido | Skill usada |
|---|---|
| "pesquisa o port do on7xelte no Nura" | `sistema.rede` (busca sem chave) |
| "baixa o Termux do F-Droid" | `sistema.baixar` (quarentena + SHA-256) |
| "confere o hash desse APK" | `sistema.assinatura` |
| "esse .msi roda nesta máquina?" | `instalador.analisar` |
| "abre o Gerenciador de Dispositivos" | `pc.abrir-programa` |
| "meu celular não tem tela, dá para usar?" | `celular.plano` |
| "baixa o adb e o scrcpy" | `celular.preparar` |
| "espelha o celular aqui" | `celular.espelhar` |
| "puxa as fotos do celular" | `celular.puxar` |

**Não faz:** não liga a Depuração USB, não toca em “Permitir depuração USB?” e não
flasha nada. Não tem `fastboot` e não instala nada no celular. O `adb` que ele usa
é só de leitura de mídia (`devices`, `pull`) e de espelhamento (`scrcpy`) — não há
campo para comando livre. E
`sistema.executar` só aceita `msiexec`, `dpkg`, `rpm`, `npm` e Python. Ele não
flasha, não desbloqueia bootloader e não "entra" no aparelho por USB.

---

## 11. Resumo em uma tabela

| Pergunta | Resposta |
|---|---|
| O J7 Prime serve? | Sim: `on7xelte` tem port no Nura (testing), LineageOS e /e/OS |
| Com a tela morta, dá? | **Depende de uma coisa:** se a Depuração USB já estava ligada, `scrcpy` resolve (§3). Se nunca esteve, só com tela de teste ou peça |
| Quanto custa destravar? | R$ 0 (se o ADB já estava ligado) · ~R$ 50 numa bancada com tela de teste · R$ 70–160 o módulo |
| Melhor caminho depois da tela? | Termux + proot-distro (risco zero) |
| Vale o Nura? | Só como experimento: sem câmera e sem VoLTE confiável |
| Vale como PC? | Como **terminal** do PC, sim. Como PC autônomo, não |
| Cuidado maior | Bateria de 2016 — nunca deixe estufada na tomada |

---

## 12. Fontes

- Nura / postmarketOS — device `on7xelte` em testing:
  <https://gitlab.com/postmarketOS/pmaports/-/merge_requests/4220>
- Trabalho de mainline para Exynos 7870 / `on7xelte`:
  <https://github.com/Praxis1071/on7xelte-mainline>
- Renomeação postmarketOS → Nura (27/09/2026): <https://nura.eco/blog/2026/09/27/nura-rename/>
- Termux — requisitos e canais de instalação:
  <https://github.com/termux/termux-app>
- proot-distro: <https://github.com/termux/proot-distro>
- /e/OS não oficial para `on7xelte`:
  <https://community.e.foundation/t/unofficial-build-samsung-galaxy-j7-prime-j7-on-nxt-on7xelte-for-e-os-s-4-x/84419>
- Peças (preços de referência): Mercado Livre, Brascell, d7 Eletrônicos.
- scrcpy — controle do Android pelo PC (inclui `--otg`):
  <https://github.com/Genymobile/scrcpy>
- Guia de tela morta com `scrcpy --otg` e autorização às cegas (issue oficial):
  <https://github.com/Genymobile/scrcpy/issues/4914>
- TalkBack para navegar sem ver:
  <https://support.google.com/accessibility/android/answer/6283677>
- TWRP para `on7xelte` (e o aviso de *BLOCKED BY FRP LOCK* sem Desbloqueio OEM):
  <https://xdaforums.com/t/recovery-on7xelte-twrp-3-3-0-for-galaxy-j7-prime.3716355/>
