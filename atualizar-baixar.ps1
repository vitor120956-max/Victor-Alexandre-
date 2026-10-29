# JARVIS - baixar a versao nova mostrando progresso de verdade.
#
# Por que este arquivo existe: o atualizar.bat chamava `Invoke-WebRequest` com
# `$ProgressPreference='SilentlyContinue'` (a barra do PowerShell 5.1 e lenta e
# poluida). Resultado: a janela ficava parada num cursor piscando, sem dizer se
# estava baixando, travada ou morta.
#
# O que aparece agora:
#   - download: porcentagem, MB de MB, velocidade e tempo que falta;
#   - extracao: aviso e tempo;
#   - copia: arquivo X de Y com porcentagem (o passo mais lento num pendrive).
#
# Sobre a porcentagem do download: o codeload do GitHub manda o zip em streaming,
# sem informar o tamanho (nao ha Content-Length). Entao:
#   1. se o servidor informar o tamanho, a porcentagem e exata;
#   2. senao, usa o tamanho do ultimo download bem-sucedido (guardado em
#      %LOCALAPPDATA%\JARVIS) e mostra com "~", dizendo que e estimativa;
#   3. na primeira vez sem referencia, mostra MB baixados, velocidade e tempo -
#      que ja e melhor que uma tela parada.
#
# Regras que este script respeita:
# - nada acentuado na saida (o console do Windows com chcp 65001 embaralha);
# - nunca toca em .env, storage, .venv, node_modules nem .git;
# - codigo de saida 0 = deu certo; 1 = falhou (o .bat decide por ele);
# - funciona no PowerShell 5.1 do Windows 10 1607, sem modulo extra.

[CmdletBinding()]
param(
    [string]$Destino = (Get-Location).Path,
    [string]$Url = 'https://codeload.github.com/vitor120956-max/Victor-Alexandre-/zip/refs/heads/arena/f26cfa7a-victor-alexandre'
)

$ErrorActionPreference = 'Stop'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

$MB = 1048576
$Zip = Join-Path $env:TEMP 'jarvis-novo.zip'
$Pasta = Join-Path $env:TEMP 'jarvis-novo'

# Onde o tamanho do ultimo zip fica guardado, para estimar a barra na proxima vez.
$CacheDir = Join-Path $env:LOCALAPPDATA 'JARVIS'
if (-not (Test-Path -LiteralPath $CacheDir)) {
    try { New-Item -ItemType Directory -Path $CacheDir -Force | Out-Null } catch { $CacheDir = $env:TEMP }
}
$CacheTamanho = Join-Path $CacheDir 'jarvis-zip-bytes.txt'


function Escrever {
    param([string]$Texto, [switch]$SemLinha)
    if ($SemLinha) { [Console]::Write($Texto) } else { [Console]::WriteLine($Texto) }
}


function Formatar-Tempo {
    param([double]$Segundos)
    if ([double]::IsNaN($Segundos) -or [double]::IsInfinity($Segundos) -or $Segundos -lt 0) { return '--:--' }
    $total = [int][Math]::Round($Segundos)
    if ($total -ge 3600) {
        return ('{0}:{1:00}:{2:00}' -f [int]($total / 3600), [int](($total % 3600) / 60), ($total % 60))
    }
    return ('{0}:{1:00}' -f [int]($total / 60), ($total % 60))
}


function Formatar-MB {
    param([double]$Bytes)
    return ($Bytes / $MB)
}


function Definir-Titulo {
    param([string]$Texto)
    try { $Host.UI.RawUI.WindowTitle = "JARVIS - $Texto" } catch { }
}


function Ler-TamanhoGuardado {
    if (-not (Test-Path -LiteralPath $CacheTamanho)) { return 0 }
    try {
        $texto = (Get-Content -LiteralPath $CacheTamanho -TotalCount 1).Trim()
        $valor = [long]0
        if ([long]::TryParse($texto, [ref]$valor) -and $valor -gt 0) { return $valor }
    }
    catch { }
    return 0
}


function Gravar-Tamanho {
    param([long]$Bytes)
    try { Set-Content -LiteralPath $CacheTamanho -Value ([string]$Bytes) -Encoding ASCII } catch { }
}


# ------------------------------------------------------------------ 1. baixar
function Baixar {
    param([string]$De, [string]$Para)

    Escrever ''
    Escrever '  Baixando a versao nova do GitHub...'

    $relogio = [Diagnostics.Stopwatch]::StartNew()
    $pedido = [Net.HttpWebRequest]::Create($De)
    $pedido.UserAgent = 'JARVIS-atualizador'
    $pedido.Timeout = 60000
    $pedido.ReadWriteTimeout = 120000
    $pedido.AllowAutoRedirect = $true

    $resposta = $pedido.GetResponse()

    $total = [long]0
    try {
        if ($null -ne $resposta.ContentLength -and $resposta.ContentLength -gt 0) {
            $total = [long]$resposta.ContentLength
        }
    }
    catch { $total = 0 }

    $estimado = $false
    if ($total -le 0) {
        # O codeload nao declara o tamanho. Usa o do download anterior.
        $guardado = Ler-TamanhoGuardado
        if ($guardado -gt 0) {
            $total = $guardado
            $estimado = $true
        }
    }

    if ($total -gt 0) {
        $rotulo = if ($estimado) { 'de ~{0:N1} MB (estimado)' } else { 'de {0:N1} MB' }
        Escrever ('  {0}' -f ($rotulo -f (Formatar-MB $total)))
    }
    else {
        Escrever '  (o GitHub nao informa o tamanho; a porcentagem aparece na proxima atualizacao)'
    }
    Escrever ''

    $entrada = $resposta.GetResponseStream()
    $saida = [IO.File]::Create($Para)
    $buffer = New-Object byte[] (256 * 1024)
    $lido = [long]0
    $avisoEm = 0.0

    try {
        while ($true) {
            $n = $entrada.Read($buffer, 0, $buffer.Length)
            if ($n -le 0) { break }
            $saida.Write($buffer, 0, $n)
            $lido += $n

            $decorrido = $relogio.Elapsed.TotalSeconds
            # Reescreve a linha umas 4 vezes por segundo: rapido o bastante para
            # parecer vivo, devagar o bastante para nao piscar.
            if (($decorrido - $avisoEm) -ge 0.25) {
                $avisoEm = $decorrido
                $velocidade = if ($decorrido -gt 0) { $lido / $decorrido } else { 0 }
                if ($total -gt 0) {
                    $pct = [int][Math]::Min(100, [Math]::Floor(100 * $lido / $total))
                    $restante = if ($velocidade -gt 0 -and $lido -lt $total) { ($total - $lido) / $velocidade } else { 0 }
                    $marca = if ($estimado) { '~' } else { '' }
                    $linha = '  {0}{1,3}%  {2,5:N1} MB  {3,4:N1} MB/s  faltam {4}   ' -f `
                        $marca, $pct, (Formatar-MB $lido), (Formatar-MB $velocidade), (Formatar-Tempo $restante)
                    Definir-Titulo ('baixando {0}{1}%' -f $marca, $pct)
                }
                else {
                    $linha = '  {0,5:N1} MB  {1,4:N1} MB/s  {2} decorridos   ' -f `
                        (Formatar-MB $lido), (Formatar-MB $velocidade), (Formatar-Tempo $decorrido)
                    Definir-Titulo 'baixando'
                }
                Escrever ("`r" + $linha) -SemLinha
            }
        }
    }
    finally {
        $saida.Close()
        $entrada.Close()
        $resposta.Close()
    }

    $segundos = $relogio.Elapsed.TotalSeconds
    $media = if ($segundos -gt 0) { $lido / $segundos } else { 0 }
    $final = '  pronto: {0,5:N1} MB em {1}   ({2,4:N1} MB/s)          ' -f `
        (Formatar-MB $lido), (Formatar-Tempo $segundos), (Formatar-MB $media)
    Escrever ("`r" + $final)
    Definir-Titulo 'extraindo'

    if ($lido -le 0) { throw 'O download veio vazio (0 byte). Confira a internet e tente de novo.' }
    Gravar-Tamanho -Bytes $lido
    return $lido
}


# ---------------------------------------------------------------- 2. extrair
function Extrair {
    param([string]$De, [string]$Para)

    Escrever ''
    Escrever '  Extraindo o zip...'
    $relogio = [Diagnostics.Stopwatch]::StartNew()

    if (Test-Path -LiteralPath $Para) { Remove-Item -LiteralPath $Para -Recurse -Force }
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    [IO.Compression.ZipFile]::ExtractToDirectory($De, $Para)

    $raiz = Get-ChildItem -LiteralPath $Para -Directory | Select-Object -First 1
    if (-not $raiz) { throw 'O zip veio sem pasta nenhuma.' }
    $quantos = @(Get-ChildItem -LiteralPath $raiz.FullName -Recurse -File).Count
    Escrever ('  {0} arquivo(s) extraido(s) em {1}.' -f $quantos, (Formatar-Tempo $relogio.Elapsed.TotalSeconds))
    return $raiz.FullName
}


# ------------------------------------------------------------------ 3. copiar
function Copiar {
    param([string]$De, [string]$Para)

    $ignorados = @('.env')
    $pastasIgnoradas = @('.venv', 'storage', 'node_modules', '.git')

    $todos = @(
        Get-ChildItem -LiteralPath $De -Recurse -File -Force -ErrorAction SilentlyContinue | Where-Object {
            $relativo = $_.FullName.Substring($De.Length).TrimStart('\')
            $partes = $relativo.Split('\')
            if ($partes.Count -gt 1 -and ($pastasIgnoradas -contains $partes[0])) { return $false }
            if ($ignorados -contains $_.Name) { return $false }
            return $true
        }
    )

    Escrever ''
    Escrever ('  Copiando {0} arquivo(s) para {1}' -f $todos.Count, $Para)
    Escrever '  Ficam intocados: .env, storage, .venv, node_modules e .git'
    Escrever ''

    $relogio = [Diagnostics.Stopwatch]::StartNew()
    $copiados = 0
    $falhas = New-Object System.Collections.ArrayList
    $ultimoAviso = 0.0
    $atual = 0

    foreach ($arquivo in $todos) {
        $atual += 1
        $relativo = $arquivo.FullName.Substring($De.Length).TrimStart('\')
        $alvo = Join-Path $Para $relativo
        $pastaAlvo = Split-Path -Parent $alvo
        try {
            if (-not (Test-Path -LiteralPath $pastaAlvo)) {
                New-Item -ItemType Directory -Path $pastaAlvo -Force | Out-Null
            }
            [IO.File]::Copy($arquivo.FullName, $alvo, $true)
            $copiados += 1
        }
        catch {
            # Arquivo em uso (o proprio .bat em execucao, por exemplo) entra aqui.
            Start-Sleep -Milliseconds 120
            try {
                [IO.File]::Copy($arquivo.FullName, $alvo, $true)
                $copiados += 1
            }
            catch {
                [void]$falhas.Add($relativo)
            }
        }

        $decorrido = $relogio.Elapsed.TotalSeconds
        if (($decorrido - $ultimoAviso) -ge 0.2 -or $atual -eq $todos.Count) {
            $ultimoAviso = $decorrido
            $pct = [int][Math]::Floor(100 * $atual / [Math]::Max(1, $todos.Count))
            $linha = '  {0,3}%  {1} de {2} arquivos  {3}   ' -f `
                $pct, $atual, $todos.Count, (Formatar-Tempo $decorrido)
            Escrever ("`r" + $linha) -SemLinha
            Definir-Titulo ('copiando {0}%' -f $pct)
        }
    }

    $segundos = $relogio.Elapsed.TotalSeconds
    Escrever ("`r  copiado: {0} de {1} arquivo(s) em {2}                    " -f `
            $copiados, $todos.Count, (Formatar-Tempo $segundos))
    Definir-Titulo 'pronto'

    if ($falhas.Count -gt 0) {
        Escrever ''
        Escrever ('  ATENCAO: {0} arquivo(s) nao puderam ser copiados:' -f $falhas.Count)
        foreach ($nome in ($falhas | Select-Object -First 5)) { Escrever "    $nome" }
        # O proprio .bat em execucao nao pode ser sobrescrito: ele atualiza na
        # proxima vez, e isso nao e falha da atualizacao.
        $soOBat = @($falhas | Where-Object { $_ -eq 'atualizar.bat' }).Count -eq $falhas.Count
        if (-not $soOBat) {
            throw ('{0} arquivo(s) ficaram para tras (arquivo em uso ou sem permissao). Feche a API e rode de novo.' -f $falhas.Count)
        }
        Escrever '  (so o atualizar.bat, que esta rodando agora: ele se atualiza na proxima vez)'
    }

    return $copiados
}


# -------------------------------------------------------------------- execucao
$geral = [Diagnostics.Stopwatch]::StartNew()
try {
    if (-not (Test-Path -LiteralPath $Destino)) { throw "A pasta de destino nao existe: $Destino" }
    Definir-Titulo 'baixando'

    $bytes = Baixar -De $Url -Para $Zip
    $raiz = Extrair -De $Zip -Para $Pasta
    $quantos = Copiar -De $raiz -Para $Destino

    Remove-Item -LiteralPath $Zip -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $Pasta -Recurse -Force -ErrorAction SilentlyContinue

    Escrever ''
    Escrever ('  Tudo pronto em {0}: {1:N1} MB baixados, {2} arquivos copiados.' -f `
            (Formatar-Tempo $geral.Elapsed.TotalSeconds), (Formatar-MB $bytes), $quantos)
    exit 0
}
catch {
    Definir-Titulo 'falhou'
    Escrever ''
    Escrever ('  NAO consegui atualizar: {0}' -f $_.Exception.Message)
    Escrever '  Nada do que ja estava na pasta foi apagado.'
    Escrever '  Se for internet, tente de novo; se repetir, baixe o zip na mao:'
    Escrever '    https://codeload.github.com/vitor120956-max/Victor-Alexandre-/zip/refs/heads/arena/f26cfa7a-victor-alexandre'
    exit 1
}
