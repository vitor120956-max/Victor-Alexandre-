# JARVIS - resgate do cartao microSD: tirar as fotos do celular SEM o conector.
#
# Por que este arquivo existe: o conector micro-USB do celular perdeu os pinos de
# dados (o teste de pressao deu negativo em todos os angulos, com cabos que
# comprovadamente passam dados em outro aparelho). Sem dados na USB nao existe
# scrcpy, nem adb, nem MTP - e nao existe driver que conserte pino. O que sobra,
# sem gastar nada: o cartao microSD, que ja esta na mao e cujo leitor o Windows
# ja reconhece.
#
# O que ele faz:
#   1. acha os discos removiveis (DriveType=2) e os que tem cara de aparelho
#      (pastas DCIM, Pictures, WhatsApp, Android\media\com.whatsapp);
#   2. MOSTRA o que achou (pasta, quantidade de arquivos, tamanho) e espera
#      confirmacao - nada de comecar a copiar 8 GB sem avisar;
#   3. copia para o PC com progresso na tela (arquivos, MB, velocidade, falta);
#   4. confere no fim: copiados, ja existentes, erros; e nunca escreve no cartao.
#
# Regras que respeita:
# - o cartao e SO LEITURA: nada e apagado, movido ou renomeado nele;
# - nada acentuado na saida (console do Windows com chcp 65001 embaralha);
# - PowerShell 5.1 puro, sem modulo extra, sem admin;
# - progresso sempre visivel: janela parada nunca e sinal de travamento;
# - espaco em disco conferido ANTES de comecar (falhar no meio e pior).
#
# Codigo de retorno:
#   0 = copiou tudo (ou nao havia nada novo)
#   1 = nao achei cartao/dado nenhum
#   2 = copiou com erro em algum arquivo (lista os 5 primeiros)
#   3 = nao ha espaco suficiente no destino

[CmdletBinding()]
param(
    [string]$Origem = '',
    [string]$Destino = '',
    [switch]$Tudo,
    [switch]$Sim
)

$ErrorActionPreference = 'Continue'

# Pastas que guardam o que a pessoa quer (foto, video, conversa).
$PastasBoas = @(
    'DCIM', 'Pictures', 'WhatsApp', 'Download', 'Movies', 'Music',
    'Documents', 'Samsung', 'Viber', 'Telegram', 'Instagram', 'Snapchat'
)
# Pastas de sistema do cartao: nao copiar (nao tem foto e enchem o relatorio).
$PastasRuins = @('$RECYCLE.BIN', 'System Volume Information', 'LOST.DIR', '.thumbnails', '.Trash-1000')

function Fala([string]$texto, [string]$cor = 'Gray') { Write-Host $texto -ForegroundColor $cor }
function Regua { Fala ('  ' + ('-' * 62)) }

function EmTexto([double]$bytes) {
    # Multiplicadores em numero puro: o parser do PowerShell nao aceita "1GB",
    # e o teste de sintaxe deste projeto usa esse parser.
    if ($bytes -ge 1073741824) { return ('{0:N2} GB' -f ($bytes / 1073741824)) }
    if ($bytes -ge 1048576) { return ('{0:N1} MB' -f ($bytes / 1048576)) }
    if ($bytes -ge 1024) { return ('{0:N0} KB' -f ($bytes / 1024)) }
    return ('{0:N0} B' -f $bytes)
}

function TemCara([string]$raiz) {
    foreach ($p in @('DCIM', 'Pictures', 'WhatsApp', 'Android')) {
        if (Test-Path -LiteralPath (Join-Path $raiz $p)) { return $true }
    }
    return $false
}

# Lista de discos: removiveis primeiro; se nenhum tiver cara de aparelho,
# aceita disco local (alguns leitores aparecem como DriveType=3).
function AcharCandidatos {
    $discos = @()
    try {
        $discos = @(Get-WmiObject -Class Win32_LogicalDisk -ErrorAction SilentlyContinue |
            Where-Object { $_.DriveType -eq 2 -or $_.DriveType -eq 3 })
    } catch { }
    if ($discos.Count -eq 0) {
        try {
            $discos = @(Get-CimInstance -ClassName Win32_LogicalDisk -ErrorAction Stop |
                Where-Object { $_.DriveType -eq 2 -or $_.DriveType -eq 3 })
        } catch { }
    }
    if ($discos.Count -eq 0) { return @() }

    $removiveis = @($discos | Where-Object { $_.DriveType -eq 2 })
    $comCara = @($discos | Where-Object { (TemCara ($_.DeviceID + '\')) })
    $juntos = @()
    foreach ($d in $comCara) { $juntos = $juntos + $d.DeviceID }
    foreach ($d in $removiveis) { if ($juntos -notcontains $d.DeviceID) { $juntos = $juntos + $d.DeviceID } }
    return @($discos | Where-Object { $juntos -contains $_.DeviceID })
}

# Tudo o que sera copiado daquela raiz, com o tamanho somado.
function Planejar([string]$raiz) {
    $itens = @()
    if ($Tudo) {
        $subs = @(Get-ChildItem -LiteralPath $raiz -Directory -ErrorAction SilentlyContinue |
            Where-Object { $PastasRuins -notcontains $_.Name })
        foreach ($s in $subs) { $itens = $itens + $s.FullName }
    } else {
        foreach ($nome in $PastasBoas) {
            $caminho = Join-Path $raiz $nome
            if (Test-Path -LiteralPath $caminho) { $itens = $itens + $caminho }
        }
        # WhatsApp moderno guarda a midia aqui, e nao na pasta WhatsApp.
        $wa = Join-Path $raiz 'Android\media\com.whatsapp'
        if (Test-Path -LiteralPath $wa) { $itens = $itens + $wa }
    }

    $arquivos = @()
    foreach ($caminho in $itens) {
        $arquivos = $arquivos + @(Get-ChildItem -LiteralPath $caminho -Recurse -File -ErrorAction SilentlyContinue)
    }
    $bytes = 0
    foreach ($a in $arquivos) { $bytes = $bytes + $a.Length }
    return [PSCustomObject]@{
        Raiz     = $raiz
        Pastas   = $itens
        Arquivos = $arquivos
        Bytes    = $bytes
    }
}

Fala ''
Fala '  JARVIS - resgate do cartao microSD (sem depender do conector do celular)' 'Cyan'
Fala ''
Fala '  Para quando o celular nao fala mais com o PC pela USB: as fotos que'
Fala '  estao no cartao saem pelo leitor de cartao, que nao usa o conector.'
Fala ''
Fala '  O cartao e tratado como SOMENTE LEITURA: nada e apagado nem movido nele.'
Fala '  Versao: 0.62.9'
Fala ''
Regua

if (-not $Origem) {
    Fala ''
    Fala '  Procurando cartoes e leitores...'
    $candidatos = AcharCandidatos
    if ($candidatos.Count -eq 0) {
        Fala ''
        Fala '  Nao achei nenhum disco removivel nem leitor com cartao.' 'Red'
        Fala ''
        Fala '  Confira:'
        Fala '    1. o cartao microSD esta DENTRO do adaptador e plugado no leitor;'
        Fala '    2. o leitor esta numa porta USB do PC (o teste da sonda ja via um'
        Fala '       leitor Alcor ligado: pode ser o mesmo);'
        Fala '    3. as vezes o cartao demora alguns segundos para aparecer.'
        Fala ''
        Fala '  Se nao houver cartao nenhum no celular, este caminho nao serve -'
        Fala '  e o resgate passa a depender do conserto do conector.'
        Fala ''
        exit 1
    }
    Fala ''
    Fala '  Discos encontrados:'
    foreach ($d in $candidatos) {
        $tipo = 'local'
        if ($d.DriveType -eq 2) { $tipo = 'removivel' }
        $linha = '     ' + $d.DeviceID + '  ' + $tipo + '  livre ' + (EmTexto $d.FreeSpace)
        if ($d.VolumeName) { $linha = $linha + '  "' + $d.VolumeName + '"' }
        Fala $linha
    }
    Fala ''
    $comCara = @($candidatos | Where-Object { (TemCara ($_.DeviceID + '\')) })
    if ($comCara.Count -eq 1) {
        $Origem = $comCara[0].DeviceID
        Fala ('  Escolhido automaticamente: ' + $Origem + '  (tem DCIM/Pictures/WhatsApp)') 'Green'
    } elseif ($comCara.Count -gt 1) {
        Fala '  Mais de um disco tem cara de aparelho. Rode de novo dizendo qual:' 'Yellow'
        foreach ($d in $comCara) { Fala ('     resgatar-cartao.bat ' + $d.DeviceID) }
        Fala ''
        exit 1
    } else {
        Fala '  Nenhum disco tem DCIM/Pictures/WhatsApp.' 'Yellow'
        Fala '  Se o cartao esta vazio, nao ha foto para resgatar nele.'
        Fala '  Para copiar um disco assim mesmo: resgatar-cartao.bat D:' 'Yellow'
        Fala ''
        exit 1
    }
}

if ($Origem.Length -eq 1) { $Origem = $Origem + ':' }
if (-not $Origem.EndsWith('\')) { $Origem = $Origem + '\' }

if (-not (Test-Path -LiteralPath $Origem)) {
    Fala ''
    Fala ('  O disco ' + $Origem + ' nao existe agora.') 'Red'
    Fala '  Confira a letra no Explorer e rode de novo.'
    Fala ''
    exit 1
}

$plano = Planejar $Origem
if ($plano.Arquivos.Count -eq 0) {
    Fala ''
    Fala ('  No disco ' + $Origem + ' nao ha nenhuma das pastas de foto/video.') 'Yellow'
    Fala '  Para copiar tudo que existe nele, rode:'
    Fala ('     resgatar-cartao.bat ' + $Origem.Substring(0, 2) + ' -Tudo')
    Fala ''
    exit 1
}

if (-not $Destino) {
    $base = Join-Path (Get-Location).Path 'storage\celular'
    if ($env:JARVIS_DADOS) { $base = Join-Path $env:JARVIS_DADOS 'celular' }
    $Destino = Join-Path $base ('cartao-' + (Get-Date).ToString('yyyy-MM-dd-HHmm'))
}

Fala ''
Fala '  O que vou copiar:'
foreach ($p in $plano.Pastas) {
    $n = @($plano.Arquivos | Where-Object { $_.FullName.StartsWith($p, 'OrdinalIgnoreCase') }).Count
    $tam = 0
    foreach ($a in $plano.Arquivos) { if ($a.FullName.StartsWith($p, 'OrdinalIgnoreCase')) { $tam = $tam + $a.Length } }
    $linha = '     ' + (Split-Path $p -Leaf).PadRight(22) + $n.ToString().PadLeft(7) + ' arquivos  ' + (EmTexto $tam).PadLeft(10)
    Fala $linha
}
Fala ''
$resumo = '  TOTAL: ' + $plano.Arquivos.Count + ' arquivos, ' + (EmTexto $plano.Bytes)
Fala $resumo 'Cyan'
Fala ('  PARA:  ' + $Destino)
Fala ''

# Espaco: falhar no meio de 8 GB e pior do que falhar agora.
$letraDestino = Split-Path $Destino -Qualifier
$livre = 0
try {
    $discoDestino = Get-WmiObject -Class Win32_LogicalDisk -Filter ("DeviceID='" + $letraDestino + "'") -ErrorAction SilentlyContinue
    if ($discoDestino) { $livre = $discoDestino.FreeSpace }
} catch { }
if ($livre -gt 0 -and $plano.Bytes -gt ($livre * 0.98)) {
    Fala ('  ESPACO INSUFICIENTE em ' + $letraDestino + ': precisa de ' + (EmTexto $plano.Bytes) + ', livre ' + (EmTexto $livre)) 'Red'
    Fala ''
    Fala '  Escolha outro destino (ou outro disco) e rode de novo:'
    Fala ('     resgatar-cartao.bat ' + $Origem.Substring(0, 2) + ' -Destino "D:\FOTOS"')
    Fala ''
    exit 3
}
if ($livre -gt 0) {
    Fala ('  Espaco livre em ' + $letraDestino + ': ' + (EmTexto $livre) + '  (cabe)') 'DarkGray'
    Fala ''
}

if (-not $Sim) {
    Fala '  Aperte Enter para comecar, ou feche a janela no X para desistir.'
    Read-Host '  Enter para copiar' | Out-Null
    Fala ''
}

$copiados = 0
$pulados = 0
$bytesCopiados = 0
$erros = @()
$inicio = Get-Date
$ultimoAviso = Get-Date
$feitos = 0

foreach ($arq in $plano.Arquivos) {
    $rel = $arq.FullName.Substring($Origem.Length)
    $alvo = Join-Path $Destino $rel
    $feitos = $feitos + 1

    $pular = $false
    if (Test-Path -LiteralPath $alvo) {
        try {
            $existente = Get-Item -LiteralPath $alvo -ErrorAction Stop
            if ($existente.Length -eq $arq.Length) { $pular = $true }
        } catch { }
    }

    if ($pular) {
        $pulados = $pulados + 1
    } else {
        $pastaAlvo = Split-Path $alvo -Parent
        try {
            if (-not (Test-Path -LiteralPath $pastaAlvo)) {
                New-Item -ItemType Directory -Force -Path $pastaAlvo | Out-Null
            }
            Copy-Item -LiteralPath $arq.FullName -Destination $alvo -Force -ErrorAction Stop
            $copiados = $copiados + 1
            $bytesCopiados = $bytesCopiados + $arq.Length
        } catch {
            $erros = $erros + ($arq.FullName + ' -> ' + $_.Exception.Message)
        }
    }

    $agora = Get-Date
    if (($feitos % 25 -eq 0) -or (($agora - $ultimoAviso).TotalSeconds -ge 3)) {
        $ultimoAviso = $agora
        $decorrido = ($agora - $inicio).TotalSeconds
        $velocidade = 0
        if ($decorrido -gt 0) { $velocidade = $bytesCopiados / $decorrido }
        $falta = ''
        if ($velocidade -gt 0) {
            $restam = $plano.Bytes - $bytesCopiados
            $seg = [int]($restam / $velocidade)
            $falta = '  faltam ~' + [int]($seg / 60) + 'min' + ($seg % 60) + 's'
        }
        $linha = '     ' + $feitos + '/' + $plano.Arquivos.Count + '  ' +
            (EmTexto $bytesCopiados) + '  ' + (EmTexto $velocidade) + '/s' + $falta
        Fala $linha 'DarkGray'
    }
}

$fim = Get-Date
$dur = [int]($fim - $inicio).TotalSeconds

Fala ''
Regua
Fala ''
Fala '  RESULTADO' 'Cyan'
Fala ''
Fala ('  Copiados:      ' + $copiados + ' arquivos  (' + (EmTexto $bytesCopiados) + ')') 'Green'
if ($pulados -gt 0) { Fala ('  Ja existiam:   ' + $pulados + ' arquivos (mesmo nome e mesmo tamanho)') }
if ($erros.Count -gt 0) {
    Fala ('  Com erro:      ' + $erros.Count + ' arquivos') 'Red'
    foreach ($e in @($erros | Select-Object -First 5)) { Fala ('     ' + $e) 'Red' }
    if ($erros.Count -gt 5) { Fala ('     ... e mais ' + ($erros.Count - 5)) 'Red' }
}
Fala ('  Tempo:         ' + [int]($dur / 60) + 'min' + ($dur % 60) + 's')
Fala ('  Onde ficou:    ' + $Destino) 'Cyan'
Fala ''
Fala '  O cartao nao foi alterado: nada foi apagado nem movido nele.'
Fala ''
Fala '  Se faltar alguma foto, ela estava na memoria interna do celular -'
Fala '  e essa so sai com o conector funcionando.'
Fala ''
if ($erros.Count -gt 0) { exit 2 }
exit 0
