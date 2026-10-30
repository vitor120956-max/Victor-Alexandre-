# JARVIS - vigiar a USB ao vivo enquanto voce troca de cabo.
#
# Por que este arquivo existe: quando o celular nao aparece, o teste que decide
# e "plugue e desplugue e veja se a lista muda". Rodar `status do celular` a
# cada tentativa tem dois problemas: demora (cada rodada abre PowerShell,
# consulta o adb e a USB) e nao mostra o instante.
#
# COMO ELE OLHA A USB (importa, e mudou na 0.64.0):
#
#   1. **Modo evento** (padrao): assina o evento de PnP do Windows com
#      `Register-WmiEvent` sobre `__InstanceOperationEvent` / Win32_PnPEntity e
#      espera com `Wait-Event`. O Windows avisa na hora em que algo entra ou sai,
#      e a espera custa zero. Nao existe "passar batido": o evento nao depende do
#      intervalo, so da assinatura estar ativa.
#   2. **Modo consulta**: lista tudo com `Get-PnpDevice` a cada N ms. E o modo
#      antigo, mantido como reserva. Numa maquina de 4 GB essa consulta pode
#      levar ~4,7 s (medido num Windows 10 1607 com ICH7) - mais que o intervalo
#      pedido. Por isso ele avisa quando isso acontece, em vez de fingir que
#      esta olhando 5 vezes por segundo.
#
# O que aparece:
#   - a lista atual, para saber o que ja estava la (hub, controladora, pendrive);
#   - linha verde "ENTROU" e apito a cada dispositivo novo (com VID e modelo);
#   - "SAIU" quando o cabo sai;
#   - a cada 30 s, "ainda vigiando" com o tempo decorrido - janela parada
#     nunca e sinal de travamento;
#   - quando aparece VID_04E8, avisa em destaque que e a Samsung.
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
    [switch]$SemLog,
    [ValidateSet('auto', 'evento', 'consulta')]
    [string]$Modo = 'auto',
    [switch]$SoAparelhos
)

$ErrorActionPreference = 'Stop'
$FonteEvento = 'JARVIS-USB-{0}' -f $PID

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

function Vid-De([string]$instanceId) {
    if ($instanceId -match 'VID_([0-9A-Fa-f]{4})') { return $Matches[1].ToUpper() }
    return ''
}

function Modelo-De([string]$instanceId, [string]$vid) {
    # O modelo vem do proprio aparelho (SM-A346B, SM-G610M): e o que separa um
    # Galaxy de outro quando o driver tem nome generico.
    if (-not $instanceId) { return '' }
    if ($vid -ne '04E8' -and $instanceId -notmatch 'VID_04E8') { return '' }
    try {
        $prop = Get-PnpDeviceProperty -InstanceId $instanceId -KeyName 'DEVPKEY_Device_BusReportedDeviceDesc' -ErrorAction SilentlyContinue
        if (-not $prop -or -not $prop.Data) { return '' }
        $modelo = [string]$prop.Data
        if ($modelo -like '\*' -or $modelo -notmatch '^(SM-|GT-|SCH-)') { return '' }
        return $modelo
    } catch { return '' }
}

function Descrever($item) {
    $vid = 'sem VID'
    if ($item.Vid -and $item.Vid -ne '0000') { $vid = "VID_$($item.Vid)" }
    $modelo = ''
    if ($item.Modelo) { $modelo = " $($item.Modelo)" }
    return ("{0}{1} [{2}]" -f $item.Nome, $modelo, $vid)
}

function Anunciar-Entrada($item, [string]$hora) {
    Write-Host ("{0}  ENTROU  {1}" -f $hora, (Descrever $item)) -ForegroundColor Green
    Registrar ("ENTROU  " + (Descrever $item))
    if ($item.Vid -eq '04E8') {
        $quem = 'Samsung'
        if ($item.Modelo) { $quem = "Samsung $($item.Modelo)" }
        Write-Host ("          E a {0}: o aparelho esta na porta agora." -f $quem) -ForegroundColor Green
        Write-Host '          Rode "status do celular" no JARVIS para o proximo passo.' -ForegroundColor Green
    } elseif ([string]$item.Chave -match '^SWD|WPDBUSENUM' -or [string]$item.Classe -match 'WPD|Portable') {
        Write-Host '          E o celular por MTP: o Windows ja o ve, a linha de dados funciona.' -ForegroundColor Green
        Write-Host '          Se a tela pedir para desbloquear, desbloqueie: ai os arquivos abrem.' -ForegroundColor Green
        Write-Host '          A Depuracao USB (adb) e outro passo, separado deste.' -ForegroundColor Green
    } elseif ($item.Vid -eq '0000' -or $item.Nome -match 'esconhecid|unknown') {
        Write-Host '          O Windows viu algo e nao conseguiu identificar: cabo de' -ForegroundColor Yellow
        Write-Host '          carga ou conector. Troque por um cabo de dados e veja de novo.' -ForegroundColor Yellow
    }
    [console]::Beep(1200, 120)
}

function Anunciar-Saida($item, [string]$hora) {
    Write-Host ("{0}  SAIU    {1}" -f $hora, (Descrever $item)) -ForegroundColor DarkYellow
    Registrar ("SAIU    " + (Descrever $item))
}

# --------------------------------------------------------------- modo consulta
function Ler-Usb {
    Get-PnpDevice -PresentOnly -ErrorAction SilentlyContinue |
        Where-Object {
            $_.Class -in @('USB', 'WPD', 'Portable Devices', 'AndroidUsbDeviceClass', 'Modem') -or
            $_.FriendlyName -match 'SAMSUNG|Android|Galaxy|ADB|MTP|SM-|esconhecid|nknown|escritor|escriptor' -or
            $_.InstanceId -match 'VID_04E8'
        } |
        ForEach-Object {
            $vid = Vid-De ([string]$_.InstanceId)
            $modelo = Modelo-De ([string]$_.InstanceId) $vid
            $chave = $_.InstanceId
            if (-not $chave) { $chave = $_.FriendlyName }
            [pscustomobject]@{
                Chave  = $chave
                Nome   = $_.FriendlyName
                Vid    = $vid
                Modelo = $modelo
                Status = [string]$_.Status
            }
        }
}

# ----------------------------------------------------------------- modo evento
function Interessa([string]$instanceId, [string]$nome, [string]$classe) {
    if ($instanceId -match '^USB') { return $true }
    if ($instanceId -match 'VID_04E8') { return $true }
    # ^SWD: o barramento WPD do Windows. E por aqui que o MTP aparece quando o
    # aparelho esta bloqueado ("desbloqueie o dispositivo para ver os arquivos"):
    # o InstanceId nao tem VID nenhum, comeca com SWD\WPDBUSENUM.
    if ($instanceId -match '^SWD') { return $true }
    if ($classe -match 'WPD|Portable|Android|Modem') { return $true }
    if ($nome -match 'SAMSUNG|Android|Galaxy|ADB|MTP|SM-|esconhecid|nknown|portat|portable') { return $true }
    return $false
}

function Item-DeEvento($evento) {
    $novo = $evento.SourceEventArgs.NewEvent
    $classe = [string]$novo.ClassPath.ClassName
    $alvo = $novo.TargetInstance
    if (-not $alvo) { return $null }
    $instanceId = [string]$alvo.DeviceID
    $nome = [string]$alvo.Name
    $classePnp = [string]$alvo.PNPClass
    if (-not (Interessa $instanceId $nome $classePnp)) { return $null }
    $vid = Vid-De $instanceId
    # Win32_PnPEntity tambem dispara __InstanceModificationEvent (status, driver):
    # isso nao e aparelho entrando nem saindo. Classificar errado aqui faria um
    # "SAIU" falso no meio da vigia.
    $operacao = 'mudou'
    if ($classe -like '*Creation*') { $operacao = 'entrou' }
    if ($classe -like '*Deletion*') { $operacao = 'saiu' }
    $modelo = ''
    if ($operacao -eq 'entrou') { $modelo = Modelo-De $instanceId $vid }
    return [pscustomobject]@{
        Chave    = $instanceId
        Nome     = $nome
        Vid      = $vid
        Modelo   = $modelo
        Status   = [string]$alvo.Status
        Operacao = $operacao
        Classe   = $classePnp
    }
}

# O que interessa quando o teste e o celular: aparelho (VID da Samsung, modelo,
# nome de telefone) e o "desconhecido" (porta viu, Windows nao identificou).
# Leitor de cartao, hub e controladora nao sao: vao para o log e, na tela, viram
# uma linha so - senao o ruido esconde justamente o que se esta esperando.
function Testa-Aparelho($item) {
    if ($item.Vid -eq '04E8') { return $true }
    if ($item.Vid -eq '0000') { return $true }
    if ($item.Modelo) { return $true }
    # WPD/Portable = o Windows vendo o aparelho por MTP (mesmo bloqueado). E o
    # que faz o Windows dizer "desbloqueie o dispositivo para liberar os recursos".
    $chave = [string]$item.Chave
    if ($chave -match '^SWD|WPDBUSENUM') { return $true }
    if ([string]$item.Classe -match 'WPD|Portable|Android|Modem') { return $true }
    if ($item.Nome -match 'SAMSUNG|Galaxy|Android|MTP|SM-|esconhecid|unknown|portat|portable') { return $true }
    return $false
}

# ------------------------------------------------------------------ cabecalho
Write-Host ''
Write-Host '  JARVIS - vigiando a USB do Windows' -ForegroundColor Cyan
Write-Host '  Plugue e desplugue o cabo do celular: o que mudar aparece aqui na hora.'
if ($CaminhoLog) {
    Write-Host ("  Log: {0}" -f $CaminhoLog) -ForegroundColor DarkGray
}
if ($SoAparelhos) {
    Write-Host '  Filtro: so aparelho (VID da Samsung, modelo ou desconhecido). O resto vai para o log.' -ForegroundColor DarkGray
}
Write-Host '  Para parar: feche esta janela no X.'

$AssinaturaOk = $false
if ($Modo -ne 'consulta') {
    try {
        $consultaWmi = "SELECT * FROM __InstanceOperationEvent WITHIN 1 WHERE TargetInstance ISA 'Win32_PnPEntity'"
        Register-WmiEvent -Query $consultaWmi -SourceIdentifier $FonteEvento -ErrorAction Stop | Out-Null
        $AssinaturaOk = $true
        Write-Host '  Modo evento: o Windows avisa na hora (nao existe intervalo para passar batido).' -ForegroundColor DarkGray
    } catch {
        $AssinaturaOk = $false
        Write-Host '  O Windows recusou a assinatura de eventos; vou consultar a lista.' -ForegroundColor DarkYellow
        $Modo = 'consulta'
    }
}
if (-not $AssinaturaOk) {
    Write-Host ("  Modo consulta: olhando a cada {0} ms." -f $Intervalo) -ForegroundColor DarkGray
    if ($Intervalo -lt 1000) {
        Write-Host '  Atencao: aqui a consulta costuma levar segundos; o intervalo real sera o da consulta.' -ForegroundColor DarkYellow
    }
}
Write-Host ''

# A lista de agora: serve para nao anunciar como novo o que ja estava na porta.
$mapa = @{}
try {
    foreach ($item in @(Ler-Usb)) { $mapa[$item.Chave] = $item }
} catch {
    if (-not $AssinaturaOk) {
        Write-Host '  Nao consegui consultar a USB do Windows (Get-PnpDevice).' -ForegroundColor Red
        Write-Host '  Este script existe so para o Windows 10 ou mais novo.'
        exit 1
    }
    Write-Host '  Nao consegui listar o estado atual; sigo so com os eventos.' -ForegroundColor DarkYellow
}

Write-Host ("  Agora: {0} dispositivo(s) na USB." -f $mapa.Count)
$mostrar = @($mapa.Values | Select-Object -First 8)
foreach ($item in $mostrar) {
    $marca = ''
    if ($item.Vid -eq '04E8') { $marca = '  <-- SAMSUNG' }
    Write-Host ("    - {0}{1}" -f (Descrever $item), $marca) -ForegroundColor DarkGray
}
if ($mapa.Count -gt $mostrar.Count) {
    Write-Host ("    ... e mais {0}" -f ($mapa.Count - $mostrar.Count)) -ForegroundColor DarkGray
}
Write-Host ''
Write-Host '  Esperando mudanca...' -ForegroundColor DarkGray

$inicio = Get-Date
$ultimoAviso = Get-Date
$limite = $null
if ($Minutos -gt 0) { $limite = $inicio.AddMinutes($Minutos) }

# Contadores da sessao, para o sinal de vida nao mentir: dizer "nada mudou"
# com o leitor de cartao entrando e saindo cinco vezes e falso.
$eventosVistos = 0
$eventosAparelho = 0

# Quantas vezes cada dispositivo entrou. Um aparelho que entra 3+ vezes na mesma
# sessao esta oscilando - e isso nao e curiosidade: porta fraca, cabo ruim ou hub
# sem energia. Enquanto a porta oscila, um aparelho novo pode nem ser enumerado,
# entao o aviso vale mais que a contagem.
$entradasPorDispositivo = @{}
$jaAvisouOscilacao = @{}
$oscilando = @{}

function Contar-Entrada($item) {
    $chave = [string]$item.Chave
    if (-not $chave) { $chave = [string]$item.Nome }
    $quantas = 1
    if ($entradasPorDispositivo.ContainsKey($chave)) {
        $quantas = [int]$entradasPorDispositivo[$chave] + 1
    }
    $entradasPorDispositivo[$chave] = $quantas
    if ($quantas -ge 3 -and -not $jaAvisouOscilacao.ContainsKey($chave)) {
        $jaAvisouOscilacao[$chave] = $true
        $oscilando[$chave] = [pscustomobject]@{ Nome = $item.Nome; Quantas = $quantas }
        Write-Host ("          ATENCAO: {0} ja entrou {1} vezes nesta sessao." -f $item.Nome, $quantas) -ForegroundColor Yellow
        Write-Host '          Isso e oscilacao de porta/cabo, nao do aparelho que voce esta testando.' -ForegroundColor Yellow
        Write-Host '          Enquanto a porta oscila, um aparelho novo pode nem ser enumerado.' -ForegroundColor Yellow
        Write-Host '          Prefira a porta USB de tras, direto na placa, sem hub - e teste' -ForegroundColor Yellow
        Write-Host '          com os outros dispositivos desligados dessa porta.' -ForegroundColor Yellow
        Registrar ("OSCILANDO  {0} entrou {1} vezes" -f $item.Nome, $quantas)
    }
    return $quantas
}

function Mostrar-Sinal($desde) {
    $agora = Get-Date
    if (($agora - $desde).TotalSeconds -ge 30) {
        $minutos = [int]($agora - $inicio).TotalMinutes
        if ($eventosAparelho -gt 0) {
            Write-Host ("          ainda vigiando ({0} min) - {1} evento(s) de aparelho ate agora" -f $minutos, $eventosAparelho) -ForegroundColor DarkGray
        } elseif ($eventosVistos -gt 0) {
            Write-Host ("          ainda vigiando ({0} min) - nenhum aparelho; {1} evento(s) de outros dispositivos USB" -f $minutos, $eventosVistos) -ForegroundColor DarkGray
        } else {
            Write-Host ("          ainda vigiando ({0} min) - nada mudou na USB" -f $minutos) -ForegroundColor DarkGray
        }
        return $agora
    }
    return $desde
}

function Fim-Do-Tempo {
    $agora = Get-Date
    if (-not $limite) { return $false }
    if ($agora -le $limite) { return $false }
    Write-Host ''
    Write-Host ("  Tempo esgotado ({0} min): encerrando a vigia." -f $Minutos) -ForegroundColor DarkGray
    Write-Host ("  Nesta sessao: {0} evento(s) de USB, {1} de aparelho." -f $eventosVistos, $eventosAparelho) -ForegroundColor DarkGray
    if ($oscilando.Count -gt 0) {
        Write-Host '  Dispositivo(s) que ficaram entrando e saindo (porta/cabo instavel):' -ForegroundColor Yellow
        foreach ($chave in @($oscilando.Keys)) {
            $dado = $oscilando[$chave]
            Write-Host ("    - {0}: {1} entrada(s)" -f $dado.Nome, $dado.Quantas) -ForegroundColor Yellow
        }
        Write-Host '  Se o celular nao aparece, resolva essa oscilacao antes: porta de tras,' -ForegroundColor Yellow
        Write-Host '  sem hub, e com o resto dos dispositivos USB fora do caminho.' -ForegroundColor Yellow
    }
    if ($CaminhoLog) {
        Write-Host ("  O que passou ficou em: {0}" -f $CaminhoLog) -ForegroundColor DarkGray
        Write-Host '  Cole esse arquivo no chat se quiser que eu leia a sessao inteira.' -ForegroundColor DarkGray
    }
    return $true
}

try {
    if ($AssinaturaOk) {
        # ------------------------------------------------ laco por evento
        while ($true) {
            $evento = Wait-Event -SourceIdentifier $FonteEvento -Timeout 2
            $processados = 0
            $ruidoEntrou = 0
            $ruidoSaiu = 0
            $nomesRuido = @{}
            while ($evento -and $processados -lt 60) {
                $hora = (Get-Date).ToString('HH:mm:ss')
                $item = $null
                try { $item = Item-DeEvento $evento } catch { $item = $null }
                if ($item) {
                    $eventosVistos = $eventosVistos + 1
                    $deAparelho = Testa-Aparelho $item
                    if ($deAparelho) { $eventosAparelho = $eventosAparelho + 1 }
                    if ($item.Operacao -eq 'entrou') {
                        $mapa[$item.Chave] = $item
                        Contar-Entrada $item | Out-Null
                        if ($deAparelho -or -not $SoAparelhos) {
                            Anunciar-Entrada $item $hora
                            $ultimoAviso = Get-Date
                        } else {
                            Registrar ("ENTROU  " + (Descrever $item))
                            $ruidoEntrou = $ruidoEntrou + 1
                            $nomesRuido[$item.Nome] = $true
                        }
                    } elseif ($item.Operacao -eq 'saiu') {
                        if ($mapa.ContainsKey($item.Chave)) { $item = $mapa[$item.Chave] }
                        $mapa.Remove($item.Chave)
                        if ($deAparelho -or -not $SoAparelhos) {
                            Anunciar-Saida $item $hora
                            $ultimoAviso = Get-Date
                        } else {
                            Registrar ("SAIU    " + (Descrever $item))
                            $ruidoSaiu = $ruidoSaiu + 1
                            $nomesRuido[$item.Nome] = $true
                        }
                    }
                }
                Remove-Event -EventIdentifier $evento.EventIdentifier -ErrorAction SilentlyContinue
                $processados = $processados + 1
                $evento = Wait-Event -SourceIdentifier $FonteEvento -Timeout 1
            }
            if (($ruidoEntrou + $ruidoSaiu) -gt 0) {
                # Uma linha para o que nao e aparelho: o log guarda tudo, a tela
                # guarda o que interessa.
                $partes = @()
                if ($ruidoEntrou -gt 0) { $partes += ("{0} entrou" -f $ruidoEntrou) }
                if ($ruidoSaiu -gt 0) { $partes += ("{0} saiu" -f $ruidoSaiu) }
                $lista = @($nomesRuido.Keys | Select-Object -First 3)
                $nomes = ''
                if ($lista.Count -gt 0) {
                    $nomes = ' - ' + ($lista -join ', ')
                    if ($nomesRuido.Count -gt 3) { $nomes = $nomes + ', ...' }
                }
                Write-Host ("          ({0} dispositivo(s) do PC: {1}{2} - no log)" -f ($ruidoEntrou + $ruidoSaiu), ($partes -join ', '), $nomes) -ForegroundColor DarkGray
            }
            $ultimoAviso = Mostrar-Sinal $ultimoAviso
            if (Fim-Do-Tempo) { break }
        }
    } else {
        # ----------------------------------------------- laco por consulta
        $avisoDemora = Get-Date
        while ($true) {
            Start-Sleep -Milliseconds $Intervalo

            $marca = Get-Date
            $novo = @{}
            foreach ($item in @(Ler-Usb)) { $novo[$item.Chave] = $item }
            $gasto = ((Get-Date) - $marca).TotalMilliseconds

            # Numa maquina de 4 GB a consulta passa do intervalo: dizer isso uma
            # vez a cada minuto - repetir a cada volta enchia o log de ruido.
            if ($gasto -gt 1000 -and ((Get-Date) - $avisoDemora).TotalSeconds -ge 60) {
                Write-Host ("          (a consulta levou {0:N0} ms - o intervalo real e esse; o modo evento nao tem esse custo)" -f $gasto) -ForegroundColor DarkGray
                $avisoDemora = Get-Date
            }

            foreach ($chave in @($novo.Keys)) {
                if (-not $mapa.ContainsKey($chave)) {
                    $item = $novo[$chave]
                    $eventosVistos = $eventosVistos + 1
                    Contar-Entrada $item | Out-Null
                    if (Testa-Aparelho $item) {
                        $eventosAparelho = $eventosAparelho + 1
                        Anunciar-Entrada $item (Get-Date).ToString('HH:mm:ss')
                    } else {
                        Registrar ("ENTROU  " + (Descrever $item))
                    }
                }
            }
            foreach ($chave in @($mapa.Keys)) {
                if (-not $novo.ContainsKey($chave)) {
                    $item = $mapa[$chave]
                    $eventosVistos = $eventosVistos + 1
                    if (Testa-Aparelho $item) {
                        $eventosAparelho = $eventosAparelho + 1
                        Anunciar-Saida $item (Get-Date).ToString('HH:mm:ss')
                    } else {
                        Registrar ("SAIU    " + (Descrever $item))
                    }
                }
            }
            $mapa = $novo
            $ultimoAviso = Mostrar-Sinal $ultimoAviso
            if (Fim-Do-Tempo) { break }
        }
    }
} finally {
    if ($AssinaturaOk) {
        Unregister-Event -SourceIdentifier $FonteEvento -ErrorAction SilentlyContinue
        Get-Event -SourceIdentifier $FonteEvento -ErrorAction SilentlyContinue |
            Remove-Event -ErrorAction SilentlyContinue
    }
}
