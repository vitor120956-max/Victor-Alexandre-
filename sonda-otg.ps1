# JARVIS - sonda do driver do celular para o modo scrcpy --otg.
#
# Por que este arquivo existe: o erro
#
#     ERROR: Could not find any USB device
#
# nao diz QUAL aparelho faltou nem COM QUE DRIVER ele esta. Sem esse dado, sobram
# duas hipoteses (cabo/porta x driver de MTP) e a pessoa testa as duas no escuro.
# Esta sonda responde com o que o Windows ja sabe: quais nos USB existem para o
# aparelho (VID_04E8 = Samsung) e qual driver esta em cada um.
#
# Codigo de retorno (o .bat usa isto quando quiser decidir sozinho):
#   0 = driver de OTG (WinUSB/libusb) presente -> e so rodar o scrcpy --otg
#   1 = driver errado: o MTP do Windows esta segurando -> precisa do Zadig
#   2 = o Windows nao ve nenhum Samsung no USB -> cabo, porta ou aparelho
#
# Detalhe que importa: o no pai do aparelho composito (usbccgp) e normal e nao
# quer dizer nada. Quem diz se o MTP esta no meio do caminho e o driver da
# INTERFACE (MI_00, MI_01...), que no Windows e o WudfRd (ou wpdusb).
#
# ASCII puro de proposito: console do Windows com chcp 65001 embaralha acento.

$ErrorActionPreference = "SilentlyContinue"

function Fala([string]$texto) { Write-Host $texto }

Fala ""
Fala "  JARVIS - sonda do driver do celular (modo scrcpy --otg)"
Fala ""
Fala "  Perguntando ao Windows quais aparelhos USB Samsung existem..."
Fala ""

$usb = @(Get-WmiObject -Class Win32_PnPEntity -Filter "DeviceID LIKE 'USB%'")
$samsung = @($usb | Where-Object { $_.DeviceID -like 'USB\VID_04E8*' })

if ($samsung.Count -eq 0) {
    Fala "  Nenhum aparelho Samsung (VID_04E8) na lista USB do Windows."
    Fala ""
    $parecidos = @($usb | Where-Object { $_.Name -match 'MTP|Android|SAMSUNG|Portable' })
    if ($parecidos.Count -gt 0) {
        Fala "  O Windows lista isto com cara de celular, mas com outro VID:"
        foreach ($p in $parecidos) {
            Fala ("      " + $p.Name + "  [" + $p.DeviceID + "]")
        }
        Fala ""
    }
    Fala "  Sem aparelho na USB nao ha driver a consertar: o problema e antes"
    Fala "  disso. Confira, nesta ordem:"
    Fala "    1. o cabo esta na porta de tras do PC, sem hub e sem extensao;"
    Fala "    2. a tela do celular esta acesa (se apagou, o Windows derruba);"
    Fala "    3. troque a porta USB e rode esta sonda de novo."
    Fala ""
    Fala "  Se aparece 'Dispositivo portatil' no Explorer mas aqui nao aparece"
    Fala "  nada, o MTP esta ativo e o que falta e so o driver do --otg: rode"
    Fala "  o Zadig (https://zadig.akeo.ie) com o celular plugado."
    exit 2
}

Fala "  Aparelho(s) Samsung encontrado(s):"
Fala ""
foreach ($d in $samsung) {
    Fala ("      nome:   " + $d.Name)
    Fala ("      id:     " + $d.DeviceID)
    Fala ("      driver: " + $d.Service)
    Fala ""
}

$otg = @($samsung | Where-Object { $_.Service -match '(?i)^(winusb|libusbk|libusb0|libwdi)' })
$mtp = @($samsung | Where-Object { $_.Service -match '(?i)^(wudfrd|wpdusb)' })

if ($otg.Count -gt 0) {
    Fala "  RESULTADO: OK - o aparelho esta com driver de OTG"
    Fala "  (" + $otg[0].Service + "). E o que o scrcpy --otg precisa."
    Fala ""
    Fala "  Pode abrir o teclado-pelo-pc.bat. Se ainda der"
    Fala "  'Could not find any USB device', feche o Explorer e o Gerenciador"
    Fala "  de Dispositivos (eles seguram o aparelho) e tente de novo."
    Fala ""
    exit 0
}

$exemplo = $samsung[0].DeviceID
$ids = @($samsung | ForEach-Object { if ($_.DeviceID -match '(VID_[0-9A-Fa-f]{4}&PID_[0-9A-Fa-f]{4})') { $Matches[1] } })
$ids = @($ids | Select-Object -Unique)
if ($ids.Count -eq 0) { $ids = @($exemplo) }

if ($mtp.Count -gt 0) {
    Fala "  RESULTADO: FALTA O DRIVER - o Windows esta falando MTP com o"
    Fala "  celular, e o modo --otg precisa de outro driver para a mesma porta."
    Fala ""
    Fala "  Nao e cabo, nao e celular, nao e porta: e driver. Conserto uma vez:"
    Fala ""
    Fala "    1. baixe o Zadig em  https://zadig.akeo.ie   (um .exe, sem instalar)"
    Fala "    2. abra o Zadig com o celular plugado"
    Fala "    3. menu Options -> List All Devices"
    Fala "    4. escolha na lista:"
    foreach ($id in $ids) { Fala ("         " + $id) }
    Fala "       (e a linha do celular; ignore leitor de cartao, mouse, hub)"
    Fala "    5. no campo da direita escolha WinUSB (ou libusb-1.0)"
    Fala "    6. clique em Replace Driver e espere"
    Fala "    7. rode esta sonda de novo: tem de dizer OK"
    Fala ""
    Fala "  Depois que disser OK, o celular some do Explorer (normal: o driver"
    Fala "  mudou). Para o MTP voltar: Gerenciador de Dispositivos -> direito no"
    Fala "  aparelho -> Desinstalar dispositivo -> desconectar e reconectar."
    Fala ""
    exit 1
}

Fala "  RESULTADO: vi o aparelho, mas nao reconheci o driver dos nos acima."
Fala ""
Fala "  Se algum driver for estranho (ou vazio), o caminho e o mesmo do Zadig:"
Fala "    1. https://zadig.akeo.ie -> Options -> List All Devices"
Fala "    2. escolha o aparelho Samsung -> WinUSB -> Replace Driver"
    foreach ($id in $ids) { Fala ("       id do aparelho: " + $id) }
Fala ""
exit 1
