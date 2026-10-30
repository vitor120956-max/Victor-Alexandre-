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
# O QUE MUDOU NA 0.64.0 (dois furos da 1a versao, que davam falso negativo):
#
#   1. a versao antiga consultava `DeviceID LIKE 'USB%'` e depois procurava
#      "MTP/Portable" DENTRO desse resultado. So que o MTP do celular vive em
#      `SWD\WPDBUSENUM\...`, que nao comeca com USB. Ou seja: a sonda nunca
#      conseguiria ver o "Dispositivo portatil" que ela mesma mandava procurar.
#      Agora a consulta e uma so, sem filtro, e a classificacao e feita aqui.
#   2. `$ErrorActionPreference = "SilentlyContinue"` escondia falha de WMI: se a
#      consulta falhasse, a lista vinha vazia e a sonda dizia "nao ha aparelho"
#      com toda a confianca. Agora falha de consulta = codigo 3, e nao 2.
#
# Codigo de retorno (o .bat usa isto quando quiser decidir sozinho):
#   0 = driver de OTG (WinUSB/libusb) presente -> e so rodar o scrcpy --otg
#   1 = driver errado: o MTP do Windows esta segurando -> precisa do Zadig
#   2 = o Windows nao ve nenhum Samsung no USB -> cabo, porta ou aparelho
#   3 = a consulta ao Windows falhou (nao da para concluir nada)
#
# Detalhe que importa: o no pai do aparelho composito (usbccgp) e normal e nao
# quer dizer nada. Quem diz se o MTP esta no meio do caminho e o driver da
# INTERFACE (MI_00, MI_01...), que no Windows e o WudfRd (ou wpdusb).
#
# ASCII puro de proposito: console do Windows com chcp 65001 embaralha acento.

param([int]$Segundos = 0)

$ErrorActionPreference = "SilentlyContinue"

function Fala([string]$texto) { Write-Host $texto }

function Coletar {
    $lista = @(Get-WmiObject -Class Win32_PnPEntity -ErrorAction SilentlyContinue)
    $samsung = @($lista | Where-Object { $_.DeviceID -like 'USB\VID_04E8*' })
    $wpd = @($lista | Where-Object { $_.DeviceID -like 'SWD\WPDBUSENUM*' })
    $usb = @($lista | Where-Object { $_.DeviceID -like 'USB\*' })
    $suspeitos = @($lista | Where-Object { $_.Name -match 'MTP|Android|SAMSUNG|Portable|Portatil' })
    return [PSCustomObject]@{
        Total     = $lista.Count
        Usb       = $usb
        Samsung   = $samsung
        Wpd       = $wpd
        Suspeitos = $suspeitos
    }
}

function MostraLista([object[]]$itens, [string]$rotulo) {
    if ($itens.Count -eq 0) { return }
    Fala ("  " + $rotulo + ":")
    foreach ($i in $itens) {
        $driver = $i.Service
        if (-not $driver) { $driver = "(sem driver)" }
        Fala ("      " + $i.Name)
        Fala ("        id:     " + $i.DeviceID)
        Fala ("        driver: " + $driver)
    }
    Fala ""
}

Fala ""
Fala "  JARVIS - sonda do driver do celular (modo scrcpy --otg)"
Fala ""
Fala "  Consultando o Windows (uma consulta so; leva alguns segundos)..."
Fala ""

$dados = Coletar

if ($dados.Total -eq 0) {
    Fala "  RESULTADO: NAO CONSEGUI CONSULTAR O WINDOWS (codigo 3)."
    Fala ""
    Fala "  Isso nao quer dizer que falta aparelho: quer dizer que a consulta"
    Fala "  ao WMI voltou vazia. Feche outras janelas do PowerShell e rode"
    Fala "  sonda-otg.bat de novo. Se repetir, rode no chat do JARVIS:"
    Fala "     diagnostico do pc"
    Fala ""
    exit 3
}

if ($Segundos -gt 0 -and $dados.Samsung.Count -eq 0) {
    $limite = [DateTime]::Now.AddSeconds($Segundos)
    while ([DateTime]::Now -lt $limite) {
        $resta = [int]($limite - [DateTime]::Now).TotalSeconds
        Fala ("  aguardando o celular aparecer... " + $resta + "s  (plugue o cabo / acenda a tela)")
        Start-Sleep -Seconds 3
        $dados = Coletar
        if ($dados.Samsung.Count -gt 0) { break }
    }
    Fala ""
}

Fala ("  O Windows tem " + $dados.Total + " dispositivos; " + $dados.Usb.Count + " sao nos USB.")
Fala ""

MostraLista $dados.Wpd "Dispositivo portatil / MTP que o Windows esta vendo"
MostraLista $dados.Suspeitos "Outros com nome de celular"

$vids = @()
foreach ($d in $dados.Usb) {
    if ($d.DeviceID -match 'VID_([0-9A-Fa-f]{4})') {
        $v = $Matches[1].ToUpper()
        if ($vids -notcontains $v) { $vids = $vids + $v }
    }
}
if ($dados.Usb.Count -gt 0) {
    Fala ("  VID dos nos USB ligados agora: " + ($vids -join " "))
    Fala ("  (04E8 seria Samsung; 058F e o leitor de cartao; 046D e mouse/teclado)")
    Fala ""
}

if ($dados.Samsung.Count -eq 0) {
    Fala "  RESULTADO: NENHUM APARELHO SAMSUNG NA USB (codigo 2)."
    Fala ""
    Fala "  Sem aparelho na USB nao ha driver a consertar: o problema e antes"
    Fala "  disso. Confira, nesta ordem:"
    Fala "    1. o celular esta mesmo plugado no PC agora (nao no carregador)?"
    Fala "    2. o cabo esta na porta de tras do PC, sem hub e sem extensao;"
    Fala "    3. a tela do celular esta acesa (se apagou, o Windows derruba);"
    Fala "    4. troque a porta USB e rode esta sonda de novo."
    Fala ""
    if ($dados.Wpd.Count -gt 0) {
        Fala "  ATENCAO: a lista acima TEM dispositivo portatil, mas nenhum com"
        Fala "  VID 04E8. Ou esse portatil e outro aparelho (cartao, camera), ou"
        Fala "  o celular esta enumerando com outro id. Cole esta tela no chat."
    } else {
        Fala "  Nada com cara de celular apareceu. Se o Explorer mostra"
        Fala "  'Dispositivo portatil', o WPD esta ativo e o problema e so driver:"
        Fala "  rode o Zadig (https://zadig.akeo.ie) com o celular plugado."
    }
    Fala ""
    Fala "  Dica: rode  sonda-otg.bat  e aceite o modo de espera (30s) para"
    Fala "  plugar o cabo enquanto ela olha."
    Fala ""
    Fala "  Se nem com a espera aparecer nada, nao e driver (o Zadig so lista o"
    Fala "  que aparece). Rode  teste-cabo.bat : ele separa cabo, porta e"
    Fala "  conector do celular, com pausa entre as tentativas."
    Fala ""
    exit 2
}

Fala "  Aparelho(s) Samsung encontrado(s):"
Fala ""
foreach ($d in $dados.Samsung) {
    $driver = $d.Service
    if (-not $driver) { $driver = "(sem driver)" }
    Fala ("      nome:   " + $d.Name)
    Fala ("      id:     " + $d.DeviceID)
    Fala ("      driver: " + $driver)
    Fala ""
}

$otg = @($dados.Samsung | Where-Object { $_.Service -match '(?i)^(winusb|libusbk|libusb0|libwdi)' })
$mtp = @($dados.Samsung | Where-Object { $_.Service -match '(?i)^(wudfrd|wpdusb)' })
$semDriver = @($dados.Samsung | Where-Object { -not $_.Service })

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

$ids = @($dados.Samsung | ForEach-Object { if ($_.DeviceID -match '(VID_[0-9A-Fa-f]{4}&PID_[0-9A-Fa-f]{4})') { $Matches[1] } })
$ids = @($ids | Select-Object -Unique)

if ($mtp.Count -gt 0 -or $semDriver.Count -gt 0) {
    if ($mtp.Count -gt 0) {
        Fala "  RESULTADO: FALTA O DRIVER (codigo 1) - o Windows esta falando MTP"
        Fala "  com o celular, e o modo --otg precisa de outro driver para a"
        Fala "  mesma porta. Nao e cabo, nao e celular, nao e porta: e driver."
    } else {
        Fala "  RESULTADO: FALTA O DRIVER (codigo 1) - o aparelho esta na USB,"
        Fala "  mas sem driver associado (o Windows nao sabe o que ele e)."
    }
    Fala ""
    Fala "  Conserto uma vez so, com o celular plugado:"
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
Fala "       id do aparelho: ver os ids listados acima"
Fala ""
exit 1
