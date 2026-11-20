# Anatomia do aparelho — ler sem mudar (0.92.2)

O pedido veio de uma conversa colada no chat: *“tem como pedir para uma IA se
implementar 100% a um dispositivo… fazer uma varredura ou engenharia reversa,
não para modificar, mas para entender todos os componentes do dispositivo e
arquivos, igual anatomia humana”*. E, em seguida: *“e se eu quiser conectar uma
TV antiga que pega wifi, tipo uma TCL Roku?”*

A resposta curta: **dá para ler muita coisa, e o que não dá tem nome.** Este
documento é o mapa — e ele corrige, ponto por ponto, o que a resposta colada
prometia a mais.

## 1. Os três alvos

| alvo | como conecta | o que o JARVIS lê | o que precisa |
|---|---|---|---|
| `local` | nenhum cabo | CPU, memória, discos, GPU, temperatura (com a fonte) | nada |
| `android` | cabo USB | identidade, bateria, memória, CPU, armazenamento, partições, térmica, apps | `adb` instalado + Depuração USB ligada + `JARVIS_HOST_CELULAR=1` |
| `roku` | Wi-Fi | modelo, série, Roku OS, canais, canal ativo, portas | IP da TV na mesma rede + `JARVIS_HOST_REDE=1` |

Na tela: menu **Anatomia** (entre “Reversa” e “Meu jogo”). A API é
`GET /api/anatomia/fontes`, `/api/anatomia/local`, `/api/anatomia/android` e
`/api/anatomia/roku?ip=…`.

## 2. Android: o que dá, e o que o sistema esconde

O `adb` já é usado pela aba Máquina desde a 0.91.x. Aqui ele só recebe
**leitura**:

```
adb -s <serial> shell getprop
adb -s <serial> shell dumpsys battery
adb -s <serial> shell cat /proc/meminfo
adb -s <serial> shell cat /proc/cpuinfo
adb -s <serial> shell df -k
adb -s <serial> shell cat /proc/partitions
adb -s <serial> shell for z in /sys/class/thermal/thermal_zone*; do ...
adb -s <serial> shell pm list packages        (só a contagem)
adb -s <serial> shell pm list packages -3     (só os de fora da loja)
```

Nunca: `install`, `uninstall`, `push`, `pull`, `reboot`, `su`, `rm`, `keyevent`.
Há um teste que confere isso comando por comando — se alguém acrescentar um
comando de efeito no futuro, o teste cai antes do dono.

**O que a conversa colada prometia a mais:**

- *“varredura automática ao plugar o cabo”* — não existe. O Android exige a
  Depuração USB ligada **e** o toque em “Permitir depuração USB?” na tela, uma
  vez por computador. É consentimento local, por desenho.
- *“leitura completa sem root”* — depende do aparelho. Muitos escondem
  `/sys/class/thermal` e todas as partições criptografadas. Quando o aparelho
  esconde, a tela diz **“não exposta”** com o motivo, em vez de mostrar zero.
- *“puxar o APK e descompilar com Jadx dentro da IA”* — são **dois passos** e
  dois lugares: o `adb pull` copia o arquivo (é escrita no PC), e a aba Reversa
  analisa o que foi copiado. O JARVIS não baixa e descompila sozinho porque
  copiar arquivo é efeito, e efeito aqui pede confirmação.

## 3. Roku: ECP, e só GET

A porta **8060** da TV é uma API oficial (ECP). O módulo usa três rotas:

```
GET http://<ip>:8060/query/device-info
GET http://<ip>:8060/query/apps
GET http://<ip>:8060/query/active-app
```

**Não** existe `POST /keypress` aqui. Apertar botão muda o estado da TV — e o
pedido era entender, não mexer. Pelo mesmo motivo, as “telas secretas” do
controle não são acionadas por software: elas só aparecem no controle, na TV.

**O que a conversa colada prometia a mais:**

- *“temperatura de CPU pela API do Roku”* — o ECP não publica temperatura. Quem
  mostra é a tela de engenharia no aparelho; software na rede não vê.
- *“telnet na 8085 para ler memória do sistema”* — a porta existe, mas só com
  **Modo de Desenvolvedor** ligado e para os apps que **você** carrega; os canais
  da loja continuam fechados.
- *“binwalk no firmware”* — o firmware do Roku é assinado e criptografado; o
  binwalk não abre o que não tem cabeçalho para reconhecer.

O endereço aceito é só da própria rede: público, laço local, link-local e
multicast são recusados — a mesma regra do resto do projeto, para a API não
virar proxy.

## 4. Local: cada número com a fonte

| dado | Windows | Linux | quando não há |
|---|---|---|---|
| CPU | registro (`ProcessorNameString`) | `/proc/cpuinfo` | `platform.processor()` |
| memória | `GlobalMemoryStatusEx` (ctypes) | `/proc/meminfo` | omitido |
| discos | letras de unidade existentes | `/` | omitido |
| GPU | `nvidia-smi` se existir; senão WMI `Win32_VideoController` | `/sys/class/drm` | “não exposta”, com o motivo |
| temperatura | `MSAcpi_ThermalZoneTemperature`; `psutil` se instalado | `/sys/class/thermal` | “não exposta”, com o motivo |

O caso da temperatura no Windows é o mais mal contado na internet: **o Windows
comum não entrega temperatura**. Muitos notebooks e placas não publicam a zona
térmica por WMI. A resposta honesta é essa — e o caminho de verdade é o
LibreHardwareMonitor aberto em segundo plano, que o JARVIS ainda **não** lê.

## 5. O que este módulo não faz

1. Não instala, não desinstala, não reinicia, não altera configuração.
2. Não lê memória de outros apps nem partição criptografada sem root.
3. Não faz “varredura automática ao plugar”: consentimento na tela é de gente.
4. Não descompila app do celular sozinho: copiar e analisar são dois passos.
5. Não aperta botão na TV e não abre tela secreta por software.
6. Não transforma a API em scanner de internet: IP público é recusado.

## 6. Como ligar

No `iniciar-jarvis.bat` (uma linha, uma vez, e reabrir):

```bat
set JARVIS_HOST_CELULAR=1
set JARVIS_HOST_REDE=1
```

A leitura do computador não precisa de nada. O Android, se o `adb` ainda não
existe, pede “Preparar celular” na aba **Máquina** — o download vem do site
oficial do Google e o hash é conferido.

## 7. Medido

- `pytest server/tests/test_anatomia.py` — 21 casos.
- Leitura local real na máquina de teste: CPU (2 núcleos), memória (15,3 GB),
  disco, e **“não exposta”** para GPU e temperatura — exatamente o
  comportamento prometido quando não há sensor acessível.
- Roku: testado com XML real de `device-info`/`apps`/`active-app` de um TCL
  32S305 (fixture), incluindo `uptime` 93784 s → “1d 2h 3min”.
