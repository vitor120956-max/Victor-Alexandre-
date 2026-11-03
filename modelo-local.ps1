# JARVIS - modelo local: a IA que roda sem chave e sem internet.
#
# O que este arquivo faz que o Python sozinho nao faz:
#   - mostra progresso de verdade no download de 1 a 2 GB (MB, porcentagem,
#     velocidade e tempo que falta);
#   - sobe o llama-server e espera a porta responder antes de dizer "ligado";
#   - diz, em portugues, o que falta quando falta alguma peca.
#
# Por que existe um .ps1 e nao so a skill: o download de 2 GB precisa de barra
# de progresso, e a barra do PowerShell 5.1 e o unico jeito de mostrar isso sem
# depender de pacote. A configuracao do .env continua sendo feita pelo Python
# (server/ia_local.py), para haver uma implementacao so.
#
# Uso:
#   powershell -ExecutionPolicy Bypass -File modelo-local.ps1
#       -> mostra o estado (nenhum arquivo e alterado)
#   powershell -ExecutionPolicy Bypass -File modelo-local.ps1 -Estado
#       -> idem, explicito
#   powershell -ExecutionPolicy Bypass -File modelo-local.ps1 -Baixar <url> [-Nome arquivo.gguf]
#       -> baixa o .gguf para storage\modelo-local
#   powershell -ExecutionPolicy Bypass -File modelo-local.ps1 -Ligar
#       -> sobe o llama-server e aponta o .env para ele
#   powershell -ExecutionPolicy Bypass -File modelo-local.ps1 -Desligar
#       -> devolve o .env ao que era antes
#
# Regras (as mesmas dos outros scripts do projeto):
# - nada acentuado na saida: o console do Windows embaralha;
# - PowerShell 5.1 puro, sem modulo externo, sem instalador;
# - nunca baixa para fora de storage\modelo-local;
# - codigo de saida 0 = deu certo; 1 = falhou.

[CmdletBinding()]
param(
    [switch]$Estado,
    [string]$Baixar = '',
    [string]$Nome = '',
    [switch]$Ligar,
    [switch]$Desligar
)

$ErrorActionPreference = 'Stop'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

$Raiz = Split-Path -Parent $MyInvocation.MyCommand.Path
$PastaModelo = Join-Path $Raiz 'storage\modelo-local'
$Python = Join-Path $Raiz '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $Python)) { $Python = 'python' }

function Escrever {
    param([string]$Texto)
    [Console]::WriteLine($Texto)
}

function Formatar-Tempo {
    param([double]$Segundos)
    if ([double]::IsNaN($Segundos) -or [double]::IsInfinity($Segundos) -or $Segundos -lt 0) { return '--:--' }
    $total = [int][Math]::Round($Segundos)
    if ($total -ge 3600) {
        return ('{0}:{1:00}:{2:00}' -f [int]($total / 3600), [int](($total % 3600) / 60), ($total % 60))
    }
    return ('{0:00}:{1:00}' -f [int]($total / 60), ($total % 60))
}

function Formatar-MB {
    param([double]$Bytes)
    return ('{0:N0}' -f ($Bytes / 1MB))
}

function Chamar-Python {
    param([string[]]$Argumentos)
    & $Python (Join-Path $Raiz 'server\ia_local.py') @Argumentos
    return $LASTEXITCODE
}

function Achar-Llama {
    $candidatos = @(
        (Join-Path $PastaModelo 'llama-server.exe'),
        (Join-Path $Raiz 'ferramentas\llama\llama-server.exe'),
        (Join-Path $Raiz 'ferramentas\llama-server.exe')
    )
    foreach ($caminho in $candidatos) {
        if (Test-Path -LiteralPath $caminho) { return $caminho }
    }
    # Procura ate dois niveis abaixo de ferramentas: o zip do llama.cpp vem
    # dentro de uma pasta com o nome da build.
    $base = Join-Path $Raiz 'ferramentas'
    if (Test-Path -LiteralPath $base) {
        $achado = Get-ChildItem -LiteralPath $base -Filter 'llama-server.exe' -Recurse -Depth 2 -ErrorAction SilentlyContinue |
            Select-Object -First 1
        if ($achado) { return $achado.FullName }
    }
    return $null
}

function Achar-Modelo {
    if (-not (Test-Path -LiteralPath $PastaModelo)) { return $null }
    $achado = Get-ChildItem -LiteralPath $PastaModelo -Filter '*.gguf' -ErrorAction SilentlyContinue |
        Sort-Object Length -Descending | Select-Object -First 1
    if ($achado) { return $achado.FullName }
    return $null
}

function Testar-Porta {
    param([string]$HostNome = '127.0.0.1', [int]$Porta = 8080)
    $cliente = New-Object System.Net.Sockets.TcpClient
    try {
        $tentativa = $cliente.BeginConnect($HostNome, $Porta, $null, $null)
        if (-not $tentativa.AsyncWaitHandle.WaitOne(700)) { return $false }
        $cliente.EndConnect($tentativa)
        return $true
    } catch {
        return $false
    } finally {
        $cliente.Close()
    }
}

function Baixar-Modelo {
    param([string]$Url, [string]$NomeArquivo)

    if ($Url -notmatch '^https?://') { throw 'o endereco precisa comecar com http:// ou https://' }
    if (-not $NomeArquivo) {
        $NomeArquivo = ($Url -split '/')[-1]
        $NomeArquivo = ($NomeArquivo -split '\?')[0]
    }
    if ($NomeArquivo -notmatch '\.gguf$') { throw 'o arquivo do modelo precisa terminar em .gguf' }
    if ($NomeArquivo -match '[\\/:*?"<>|]') { throw 'nome de arquivo invalido' }

    if (-not (Test-Path -LiteralPath $PastaModelo)) {
        New-Item -ItemType Directory -Path $PastaModelo -Force | Out-Null
    }
    $Destino = Join-Path $PastaModelo $NomeArquivo
    if (Test-Path -LiteralPath $Destino) {
        Escrever ("  {0} ja esta na pasta ({1} MB). Nada baixado." -f $NomeArquivo, (Formatar-MB (Get-Item -LiteralPath $Destino).Length))
        return 0
    }

    $Disco = Get-WmiObject Win32_LogicalDisk -Filter ("DeviceID='" + (Split-Path -Qualifier $Destino) + "'")
    if ($Disco) {
        $Livre = [double]$Disco.FreeSpace
        if ($Livre -lt 512MB) {
            throw ("disco quase cheio: {0} MB livres. Libere espaco antes." -f (Formatar-MB $Livre))
        }
    }

    Escrever ("  Baixando {0}" -f $NomeArquivo)
    $Parcial = $Destino + '.parcial'
    $requisicao = [System.Net.HttpWebRequest]::Create($Url)
    $requisicao.UserAgent = 'JARVIS'
    $requisicao.Timeout = 60000
    $requisicao.ReadWriteTimeout = 120000
    $resposta = $requisicao.GetResponse()
    $Total = [double]$resposta.ContentLength
    $entrada = $resposta.GetResponseStream()
    $saida = [System.IO.File]::Create($Parcial)
    $baixado = [double]0
    $buffer = New-Object byte[] 262144
    $inicio = Get-Date
    $ultimoAviso = -10
    try {
        while (($lido = $entrada.Read($buffer, 0, $buffer.Length)) -gt 0) {
            $saida.Write($buffer, 0, $lido)
            $baixado += $lido
            $segundos = ((Get-Date) - $inicio).TotalSeconds
            $aviso = [int]($segundos * 2)
            if ($aviso -gt $ultimoAviso) {
                $ultimoAviso = $aviso
                $velocidade = 0
                if ($segundos -gt 0) { $velocidade = $baixado / $segundos }
                if ($Total -gt 0) {
                    $pct = [int](($baixado / $Total) * 100)
                    $resta = 0
                    if ($velocidade -gt 0) { $resta = ($Total - $baixado) / $velocidade }
                    [Console]::Write(("`r  {0,3}%  {1} de {2} MB  {3} MB/s  faltam {4}   " -f `
                        $pct, (Formatar-MB $baixado), (Formatar-MB $Total), ('{0:N1}' -f ($velocidade / 1MB)), (Formatar-Tempo $resta)))
                } else {
                    [Console]::Write(("`r  {0} MB  {1} MB/s   " -f (Formatar-MB $baixado), ('{0:N1}' -f ($velocidade / 1MB))))
                }
            }
        }
    } finally {
        $saida.Close()
        $entrada.Close()
        $resposta.Close()
        [Console]::WriteLine('')
    }

    if (-not (Test-Path -LiteralPath $Parcial) -or (Get-Item -LiteralPath $Parcial).Length -eq 0) {
        if (Test-Path -LiteralPath $Parcial) { Remove-Item -LiteralPath $Parcial -Force }
        throw 'o download terminou vazio; o endereco pode estar errado'
    }
    Move-Item -LiteralPath $Parcial -Destination $Destino -Force
    $tamanho = (Get-Item -LiteralPath $Destino).Length
    Escrever ("  Pronto: {0} ({1} MB) em {2}" -f $NomeArquivo, (Formatar-MB $tamanho), $PastaModelo)
    Escrever '  Agora: modelo-local.ps1 -Ligar (ou, no chat: "liga o modelo local")'
    return 0
}

function Ligar-Modelo {
    $exe = Achar-Llama
    $modelo = Achar-Modelo
    if (-not $modelo) {
        throw ("nao ha .gguf em {0}. Baixe um primeiro: -Baixar <url>" -f $PastaModelo)
    }
    if (-not $exe) {
        Escrever '  Falta o llama-server.exe.'
        Escrever '  Baixe o zip do llama.cpp (build win-x64 ou win-arm64), descompacte em:'
        Escrever ("    {0}\n" -f (Join-Path $Raiz 'ferramentas\llama'))
        Escrever '  Sem ele o .env pode ate ficar pronto, mas nada responde na porta.'
        return 1
    }
    if (Testar-Porta) {
        Escrever '  Ja tem um servidor escutando em 127.0.0.1:8080 - nao subi outro.'
    } else {
        $argumentos = @('-m', $modelo, '--host', '127.0.0.1', '--port', '8080', '-c', '2048')
        Escrever ("  Subindo: {0}" -f $exe)
        Start-Process -FilePath $exe -ArgumentList $argumentos -WorkingDirectory (Split-Path -Parent $exe) -WindowStyle Minimized | Out-Null
        $esperou = 0
        while ($esperou -lt 60 -and -not (Testar-Porta)) {
            Start-Sleep -Seconds 2
            $esperou += 2
            [Console]::Write(("`r  carregando o modelo... {0}s  " -f $esperou))
        }
        [Console]::WriteLine('')
        if (Testar-Porta) {
            Escrever '  Servidor respondendo em 127.0.0.1:8080'
        } else {
            Escrever '  O servidor nao respondeu em 60s. Modelo grande demais para a RAM?'
            Escrever '  Veja a janela minimizada do llama-server: o erro aparece la.'
        }
    }
    return (Chamar-Python @('--ligar'))
}

# ------------------------------------------------------------------ roteamento

try {
    if ($Baixar) {
        exit (Baixar-Modelo -Url $Baixar -NomeArquivo $Nome)
    }
    if ($Ligar) {
        exit (Ligar-Modelo)
    }
    if ($Desligar) {
        exit (Chamar-Python @('--desligar'))
    }
    exit (Chamar-Python @('--estado'))
} catch {
    Escrever ("  Falhou: {0}" -f $_.Exception.Message)
    exit 1
}
