# JARVIS - vigiar a USB ao vivo enquanto voce troca de cabo.
#
# Por que este arquivo existe: quando o celular nao aparece, o teste que decide
# e "plugue e desplugue e veja se a lista muda". Rodar `status do celular` a
# cada tentativa tem dois problemas: demora (cada rodada abre PowerShell,
# consulta o adb e a USB) e nao mostra o instante. Aqui a janela fica aberta,
# checa a cada 2 segundos e apita na hora em que algo entra ou sai.
#
# O que aparece:
#   - a lista atual, para saber o que ja estava la (hub, controladora, pendrive);
#   - uma linha verde "ENTROU" e um apito a cada dispositivo novo (com o VID);
#   - "SAIU" quando o cabo sai;
#   - a cada 30 s, "ainda vigiando" com o tempo decorrido - a janela parada
#     nunca e sinal de travamento;
#   - quando aparece VID_04E8, avisa em destaque que e a Samsung.
#
# Modo atento (para conector com mau contato): um aparelho com solda trincada as
# vezes aparece por menos de um segundo. `vigiar-usb-atento.bat` chama este
# script com -Intervalo 400 -Minutos 10, que olha a USB 5 vezes por segundo.
# Sem isso, uma piscada de 0,5 s pode passar entre duas checagens de 2 s.
#
# Toda entrada e saida tambem vai para um arquivo (storage\celular\vigia-DATA.log):
# se a janela fechar, o que passou continua registrado para colar no chat.
#
# Regras que este script respeita:
# - nada acentuado na saida (o console do Windows com chcp 65001 embaralha);
# - so leitura: nao instala, nao altera, nao toca em aparelho nenhum;
# - PowerShell 5.1 puro, sem modulo extra, sem admin;
# - para parar: feche a janela no X (nao existe tecla para decorar).

[CmdletBinding()]
param(
    [int]$Intervalo = 2000,
    [int]$Minutos = 0,
    [string]$Log = '',
    [switch]$SemLog
)

$ErrorActionPreference = 'Stop'

# O log: por padrao em storage\celular (ou JARVIS_DADOS). Falha em gravar nunca
# derruba a vigia - ela e a informacao principal, o arquivo e so a copia.
$CaminhoLog = ''
if (-not $SemLog) {
    if (-not $Log) {
        $base = Join-Path (Get-Location).Path 'storage\celular'
        if ($env:JARVIS_DADOS) { $base = Join-Path $env:JARVIS_DADOS 'celular' }
        $Log = Join-Path $base ('vigia-{0}.log' -f (Get-Date).ToString('yyyy-MM-dd-HHmm'))
    }
    try {
        New-Item -ItemType Directory -Force -Path (Split-Path $Log) | Out-Null
        $CaminhoLog = $Log
    } catch { $CaminhoLog = '' }
}

function Registrar([string]$texto) {
    if (-not $CaminhoLog) { return }
    try { Add-Content -Path $CaminhoLog -Value ("{0}  {1}" -f (Get-Date).ToString('HH:mm:ss'), $texto) -Encoding UTF8 } catch { }
}

function Ler-Usb {
    Get-PnpDevice -PresentOnly -ErrorAction SilentlyContinue |
        Where-Object {
            $_.Class -in @('USB', 'WPD', 'Portable Devices', 'AndroidUsbDeviceClass', 'Modem') -or
            $_.FriendlyName -match 'SAMSUNG|Android|Galaxy|ADB|MTP|SM-|esconhecid|nknown|escritor|escriptor' -or
            $_.InstanceId -match 'VID_04E8'
        } |
        ForEach-Object {
            $vid = ''
            if ($_.InstanceId -match 'VID_([0-9A-Fa-f]{4})') {
                $vid = $Matches[1].ToUpper()
            }
            $chave = $_.InstanceId
            if (-not $chave) { $chave = $_.FriendlyName }
            # O modelo vem do proprio aparelho (SM-A346B, SM-G610M): e o que
            # separa um Galaxy de outro quando o driver tem nome generico.
            $modelo = ''
            if ($vid -eq '04E8' -or $_.FriendlyName -match 'SAMSUNG|Galaxy|SM-|MTP|Android') {
                try {
                    $prop = Get-PnpDeviceProperty -InstanceId $_.InstanceId -KeyName 'DEVPKEY_Device_BusReportedDeviceDesc' -ErrorAction SilentlyContinue
                    if ($prop -and $prop.Data) { $modelo = [string]$prop.Data }
                } catch { $modelo = '' }
                if ($modelo -like '\*' -or $modelo -notmatch '^(SM-|GT-|SCH-)') { $modelo = '' }
            }
            [pscustomobject]@{
                Chave  = $chave
                Nome   = $_.FriendlyName
                Vid    = $vid
                Modelo = $modelo
                Status = [string]$_.Status
            }
        }
}

function Descrever($item) {
    $vid = 'sem VID'
    if ($item.Vid -and $item.Vid -ne '0000') { $vid = "VID_$($item.Vid)" }
    $modelo = ''
    if ($item.Modelo) { $modelo = " $($item.Modelo)" }
    return ("{0}{1} [{2}]" -f $item.Nome, $modelo, $vid)
}

Write-Host ''
Write-Host '  JARVIS - vigiando a USB do Windows' -ForegroundColor Cyan
Write-Host '  Plugue e desplugue o cabo do celular: o que mudar aparece aqui na hora.'
Write-Host ("  Olhando a cada {0} ms." -f $Intervalo) -ForegroundColor DarkGray
if ($CaminhoLog) {
    Write-Host ("  Log: {0}" -f $CaminhoLog) -ForegroundColor DarkGray
}
if ($Intervalo -gt 1000) {
    Write-Host '  Conector com mau contato? Feche e use vigiar-usb-atento.bat (5x por segundo).' -ForegroundColor DarkGray
}
Write-Host '  Para parar: feche esta janela no X.'
Write-Host ''

$mapa = @{}
try {
    $atuais = @(Ler-Usb)
} catch {
    Write-Host '  Nao consegui consultar a USB do Windows (Get-PnpDevice).' -ForegroundColor Red
    Write-Host '  Este script existe so para o Windows 10 ou mais novo.'
    exit 1
}
foreach ($item in $atuais) { $mapa[$item.Chave] = $item }

Write-Host ("  Agora: {0} dispositivo(s) na USB." -f $atuais.Count)
$mostrar = @($atuais | Select-Object -First 8)
foreach ($item in $mostrar) {
    $marca = ''
    if ($item.Vid -eq '04E8') { $marca = '  <-- SAMSUNG' }
    Write-Host ("    - {0}{1}" -f (Descrever $item), $marca) -ForegroundColor DarkGray
}
if ($atuais.Count -gt $mostrar.Count) {
    Write-Host ("    ... e mais {0}" -f ($atuais.Count - $mostrar.Count)) -ForegroundColor DarkGray
}
Write-Host ''
Write-Host '  Esperando mudanca...' -ForegroundColor DarkGray

$inicio = Get-Date
$ultimoAviso = Get-Date
$limite = $null
if ($Minutos -gt 0) { $limite = $inicio.AddMinutes($Minutos) }

while ($true) {
    Start-Sleep -Milliseconds $Intervalo

    $marca = Get-Date
    $novo = @{}
    foreach ($item in @(Ler-Usb)) { $novo[$item.Chave] = $item }
    $gasto = ((Get-Date) - $marca).TotalMilliseconds
    if ($gasto -gt (2 * $Intervalo) -and $gasto -gt 2000) {
        # Numa maquina de 4 GB a consulta pode passar do intervalo: sem dizer
        # isso, "nada mudou" viraria "o programa travou".
        Write-Host ("          (a consulta levou {0:N0} ms; o intervalo efetivo e esse)" -f $gasto) -ForegroundColor DarkGray
    }

    foreach ($chave in @($novo.Keys)) {
        if (-not $mapa.ContainsKey($chave)) {
            $item = $novo[$chave]
            $hora = (Get-Date).ToString('HH:mm:ss')
            Write-Host ("{0}  ENTROU  {1}" -f $hora, (Descrever $item)) -ForegroundColor Green
            Registrar ("ENTROU  " + (Descrever $item))
            if ($item.Vid -eq '04E8') {
                $quem = 'Samsung'
                if ($item.Modelo) { $quem = "Samsung $($item.Modelo)" }
                Write-Host ("          E a {0}: o aparelho esta na porta agora." -f $quem) -ForegroundColor Green
                Write-Host '          Rode "status do celular" no JARVIS para o proximo passo.' -ForegroundColor Green
            } elseif ($item.Vid -eq '0000' -or $item.Nome -match 'esconhecid|unknown') {
                Write-Host '          O Windows viu algo e nao conseguiu identificar: cabo de' -ForegroundColor Yellow
                Write-Host '          carga ou conector. Troque por um cabo de dados e veja de novo.' -ForegroundColor Yellow
            }
            [console]::Beep(1200, 120)
        }
    }
    foreach ($chave in @($mapa.Keys)) {
        if (-not $novo.ContainsKey($chave)) {
            $item = $mapa[$chave]
            $hora = (Get-Date).ToString('HH:mm:ss')
            Write-Host ("{0}  SAIU    {1}" -f $hora, (Descrever $item)) -ForegroundColor DarkYellow
            Registrar ("SAIU    " + (Descrever $item))
        }
    }

    $mapa = $novo

    $agora = Get-Date
    if (($agora - $ultimoAviso).TotalSeconds -ge 30) {
        $minutos = [int]($agora - $inicio).TotalMinutes
        Write-Host ("          ainda vigiando ({0} min) - nada mudou na USB" -f $minutos) -ForegroundColor DarkGray
        $ultimoAviso = $agora
    }
    if ($limite -and $agora -gt $limite) {
        Write-Host ''
        Write-Host ("  Tempo esgotado ({0} min): encerrando a vigia." -f $Minutos) -ForegroundColor DarkGray
        if ($CaminhoLog) {
            Write-Host ("  O que passou ficou em: {0}" -f $CaminhoLog) -ForegroundColor DarkGray
            Write-Host '  Cole esse arquivo no chat se quiser que eu leia a sessao inteira.' -ForegroundColor DarkGray
        }
        exit 0
    }
}
