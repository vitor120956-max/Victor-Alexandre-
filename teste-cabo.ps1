# JARVIS - teste do cabo, da porta e do conector: o Windows ve ALGUMA coisa
# quando o celular entra?
#
# Por que este arquivo existe: a sonda-otg.bat respondeu "nenhum Samsung na USB"
# e mostrou os VID que existem (leitor de cartao, teclado, mouse). Isso prova que
# o celular NAO esta enumerando. E aqui esta o ponto que muda tudo:
#
#     o Zadig so lista o que esta enumerado.
#
# Ou seja: se o aparelho nao aparece na USB, nao existe driver a instalar - e
# insistir no Zadig e perder tempo.
#
# O QUE MUDOU NA 0.64.0 (tres correcoes, todas vindas de falha real em campo):
#
#   1. **Leitura confiavel.** A 0.64.0 usava uma consulta WMI so. Numa maquina de
#      4 GB com Win10 1607 essa consulta as vezes volta VAZIA sem erro, e o teste
#      entao dizia "falha de leitura" (codigo 3) e mandava repetir. Agora sao 3
#      tentativas e, se ainda vier vazio, dois planos B (CIM e Get-PnpDevice).
#      Piso de sanidade: menos de 5 dispositivos = leitura falhou, nunca
#      "nao ha aparelho".
#   2. **Vigia por EVENTO, nao por consulta.** O conector com solda fria faz o
#      aparelho enumerar por fracoes de segundo. Consultar a cada 2 s perde isso
#      e conclui "nunca apareceu" - falso negativo caro, porque manda a pessoa
#      desistir de um conector que ainda funciona em certo angulo. Agora, durante
#      a espera, o Windows AVISA por evento (Register-WmiEvent), e cada aparelho
#      que entra e registrado com a hora.
#   3. **Modo -Vigiar (teste de pressao).** 60 s olhando enquanto a pessoa
#      pressiona/inclina o conector. Se aparecer qualquer coisa nesse tempo, o
#      problema e contato fisico (solda fria), e da para segurar com calco e
#      fazer o trabalho. Se nao aparecer nada, e pino quebrado.
#
# Codigo de retorno:
#   0 = o celular apareceu (VID_04E8): cabo, porta e conector bons -> driver
#   1 = apareceu dispositivo, mas nenhum Samsung -> colar no chat
#   2 = nada apareceu: fisico (conector, cabo ou porta)
#   3 = a leitura do Windows falhou de verdade (nem com os planos B)
#
# Regras que respeita:
# - ASCII puro (console do Windows com chcp 65001 embaralha acento);
# - so leitura: nao instala, nao altera, nao reinicia nada;
# - PowerShell 5.1 puro, sem modulo extra, sem admin;
# - a espera mostra contagem na tela: janela parada nunca e sinal de travamento.

[CmdletBinding()]
param(
    [int]$Espera = 20,
    [int]$Tentativas = 4,
    [int]$Vigiar = 0
)

$ErrorActionPreference = 'Continue'
$Piso = 5

$Vistos = @()
$Samsung = @()

function Fala([string]$texto, [string]$cor = 'Gray') {
    Write-Host $texto -ForegroundColor $cor
}

function Regua {
    Fala ("  " + ("-" * 62))
}

# ---------------------------------------------------------------- leitura
# Devolve objetos com Name/DeviceID/Service, ou $null se nao deu para ler.
# A ordem importa: WMI (mais rapido aqui) -> CIM -> Get-PnpDevice (lento, mas
# e o ultimo recurso que ainda enxerga o que esta presente).
function LerDispositivos {
    for ($i = 1; $i -le 3; $i++) {
        $bruto = @(Get-WmiObject -Class Win32_PnPEntity -ErrorAction SilentlyContinue)
        if ($bruto.Count -ge $Piso) {
            return @($bruto | ForEach-Object {
                [PSCustomObject]@{ Name = $_.Name; DeviceID = $_.DeviceID; Service = $_.Service }
            })
        }
        Start-Sleep -Milliseconds 700
    }
    try {
        $bruto = @(Get-CimInstance -ClassName Win32_PnPEntity -ErrorAction Stop)
        if ($bruto.Count -ge $Piso) {
            return @($bruto | ForEach-Object {
                [PSCustomObject]@{ Name = $_.Name; DeviceID = $_.DeviceID; Service = $_.Service }
            })
        }
    } catch { }
    try {
        $bruto = @(Get-PnpDevice -PresentOnly -ErrorAction Stop)
        if ($bruto.Count -ge $Piso) {
            return @($bruto | ForEach-Object {
                [PSCustomObject]@{ Name = $_.FriendlyName; DeviceID = $_.InstanceId; Service = $_.Class }
            })
        }
    } catch { }
    return $null
}

function SoUsb([object[]]$itens) {
    if ($null -eq $itens) { return $null }
    return @($itens | Where-Object { $_.DeviceID -like 'USB\*' })
}

function IdsDe([object[]]$itens) {
    $ids = @()
    foreach ($i in $itens) { $ids = $ids + $i.DeviceID }
    return $ids
}

function VidDe([string]$id) {
    if ($id -match 'VID_([0-9A-Fa-f]{4})') { return $Matches[1].ToUpper() }
    return ''
}

function Guardar([object]$item, [string]$hora) {
    $vid = VidDe $item.DeviceID
    $marca = ''
    if ($vid -eq '04E8') { $marca = '   <== SAMSUNG (o celular)' }
    $l1 = '     ' + $hora + '  ' + $item.Name + $marca
    $l2 = '               vid:    ' + $vid
    $l3 = '               id:     ' + $item.DeviceID
    $l4 = '               driver: ' + $item.Service
    $cor = 'Green'
    if ($vid -ne '04E8') { $cor = 'Yellow' }
    Fala $l1 $cor
    Fala $l2 $cor
    Fala $l3 $cor
    Fala $l4 $cor
    $script:Vistos = $script:Vistos + $item
    if ($vid -eq '04E8') { $script:Samsung = $script:Samsung + $item }
}

# ---------------------------------------------------------------- vigia por evento
function MontarVigia {
    $fonte = 'JARVIS-CABO-{0}' -f $PID
    try {
        $consulta = "SELECT * FROM __InstanceCreationEvent WITHIN 1 WHERE TargetInstance ISA 'Win32_PnPEntity'"
        Register-WmiEvent -Query $consulta -SourceIdentifier $fonte -ErrorAction Stop | Out-Null
        return $fonte
    } catch {
        return ''
    }
}

function DerrubarVigia([string]$fonte) {
    if (-not $fonte) { return }
    Unregister-Event -SourceIdentifier $fonte -ErrorAction SilentlyContinue
    Remove-Event -SourceIdentifier $fonte -ErrorAction SilentlyContinue
}

# Olha por evento por N segundos. Devolve $true se a vigia estava ativa.
# $Conhecidos sao os ids que ja existiam: o que ja estava na porta nao conta.
function OlharPorEvento([int]$segundos, [string[]]$conhecidos) {
    $fonte = MontarVigia
    if (-not $fonte) {
        Fala "  (o Windows recusou a assinatura de eventos; vou consultar a lista)" 'DarkYellow'
        return $false
    }
    Fala "  Modo evento: o Windows avisa na hora, mesmo que o aparelho apareca por" 'DarkGray'
    Fala "  meio segundo. Nao existe intervalo para passar batido." 'DarkGray'
    $fim = [DateTime]::Now.AddSeconds($segundos)
    try {
        while ([DateTime]::Now -lt $fim) {
            Wait-Event -SourceIdentifier $fonte -Timeout 2 | Out-Null
            $pendentes = @(Get-Event -SourceIdentifier $fonte -ErrorAction SilentlyContinue)
            foreach ($ev in $pendentes) {
                $item = $null
                try {
                    $t = $ev.SourceEventArgs.NewEvent.TargetInstance
                    $item = [PSCustomObject]@{ Name = $t.Name; DeviceID = $t.DeviceID; Service = $t.Service }
                } catch { $item = $null }
                if ($item -and $item.DeviceID) {
                    if ($conhecidos -notcontains $item.DeviceID) {
                        Guardar $item ((Get-Date).ToString('HH:mm:ss'))
                        $conhecidos = $conhecidos + $item.DeviceID
                    }
                }
                Remove-Event -EventIdentifier $ev.EventIdentifier -ErrorAction SilentlyContinue
            }
            if ($script:Samsung.Count -gt 0) { break }
            $resta = [int]($fim - [DateTime]::Now).TotalSeconds
            Fala ("     ... " + $resta + "s")
        }
    } finally {
        DerrubarVigia $fonte
    }
    return $true
}

# ---------------------------------------------------------------- modo vigiar
if ($Vigiar -gt 0) {
    Fala ""
    Fala "  JARVIS - teste de pressao do conector do celular" 'Cyan'
    Fala ""
    Fala "  Prova, em um minuto, se o conector AINDA passa dados em algum angulo."
    Fala "  Isso separa 'solda fria' (da para segurar com calco e trabalhar) de"
    Fala "  'pino quebrado' (so solda)."
    Fala ""
    Fala "  Com o cabo plugado no PC e no celular:"
    Fala "     - pressione o plugue para dentro, com cuidado, sem forcar;"
    Fala "     - incline de leve para cima, para baixo, para os lados;"
    Fala "     - gire o plugue devagar;"
    Fala "     - encoste uma cunha fina (papel dobrado) entre cabo e aparelho."
    Fala ""
    Fala "  Se o celular aparecer em QUALQUER momento, eu registro a hora." 'Yellow'
    Fala ""
    Regua
    $todos = LerDispositivos
    if ($null -eq $todos) {
        Fala ""
        Fala "  Nao consegui ler a lista do Windows nem com os planos B." 'Red'
        Fala "  Nao concluo nada. Feche outras janelas do PowerShell e rode de novo."
        Fala ""
        exit 3
    }
    $usb = SoUsb $todos
    $conhecidos = IdsDe $usb
    Fala ""
    $linha = '  Agora: ' + $usb.Count + ' nos USB ligados. Olhando por ' + $Vigiar + ' segundos...'
    Fala $linha 'Gray'
    Fala ""
    $deuEvento = OlharPorEvento $Vigiar $conhecidos
    if (-not $deuEvento) {
        # Plano B: consulta no intervalo mais curto que a maquina aguenta.
        $fim = [DateTime]::Now.AddSeconds($Vigiar)
        while ([DateTime]::Now -lt $fim) {
            $agora = SoUsb (LerDispositivos)
            if ($null -eq $agora) { continue }
            $novos = @($agora | Where-Object { $conhecidos -notcontains $_.DeviceID })
            foreach ($n in $novos) {
                Guardar $n ((Get-Date).ToString('HH:mm:ss'))
                $conhecidos = $conhecidos + $n.DeviceID
            }
            $resta = [int]($fim - [DateTime]::Now).TotalSeconds
            Fala ("     ... " + $resta + "s")
        }
    }
    Fala ""
    Regua
    Fala ""
    Fala "  VEREDITO" 'Cyan'
    Fala ""
    if ($Samsung.Count -gt 0) {
        Fala "  O CELULAR APARECEU durante o teste de pressao." 'Green'
        Fala ""
        Fala "  Cabo e porta estao bons; o conector do celular e que esta com contato" 'Green'
        Fala "  ruim (solda fria tipica de queda). Isso e otimo: da para trabalhar." 'Green'
        Fala ""
        Fala "  Como aproveitar: descubra o angulo em que ele aparece e mantenha com"
        Fala "  uma cunha de papel dobrado entre o plugue e o aparelho, ou com o"
        Fala "  celular apoiado em algo. Com ele aparecendo de forma estavel, rode:"
        Fala "     sonda-otg.bat        (diz o driver)"
        Fala "     teclado-pelo-pc.bat  (abre o teclado do PC)"
        Fala ""
        Fala "  Conserto definitivo: solda no conector, em assistencia. E barato"
        Fala "  perto de trocar o aparelho."
        Fala ""
        exit 0
    }
    if ($Vistos.Count -gt 0) {
        Fala "  Apareceu dispositivo, mas nenhum Samsung. Cole esta tela no chat." 'Yellow'
        Fala ""
        exit 1
    }
    Fala ("  Em " + $Vigiar + " segundos de pressao e inclinacao, NADA apareceu.") 'Red'
    Fala ""
    Fala "  Isso e o pior dos dois casos fisicos: nao e contato intermitente."
    Fala "  Com cabos que comprovadamente passam dados em outro aparelho, e sem"
    Fala "  nenhuma enumeracao em nenhum angulo, o conector do celular (ou o"
    Fala "  controlador USB na placa) perdeu os pinos de dados."
    Fala ""
    Fala "  O que ainda vale tentar, sem gastar:"
    Fala "    1. limpar o conector (palito, sem metal): as vezes e so sujeira;"
    Fala "    2. conferir com lanterna se algum pino esta dobrado ou escuro;"
    Fala "    3. assistencia tecnica para solda do conector micro-USB (a peca e"
    Fala "       barata; o servico e o custo)."
    Fala ""
    Fala "  Por software eu nao consigo consertar pino quebrado, e nao vou dizer"
    Fala "  que consigo."
    Fala ""
    exit 2
}

# ---------------------------------------------------------------- modo tentativas
Fala ""
Fala "  JARVIS - teste de cabo, porta e conector do celular" 'Cyan'
Fala ""
Fala "  A pergunta que isto responde: quando voce pluga o celular, o Windows"
Fala "  muda em alguma coisa?"
Fala ""
Fala "  Por que importa: o Zadig (driver do modo --otg) so lista aparelho que"
Fala "  esta enumerado. Se o celular nao aparece na USB, nao ha driver a"
Fala "  instalar - o problema e fisico, e o teste abaixo diz onde."
Fala ""
Regua

$base = LerDispositivos
if ($null -eq $base) {
    Fala ""
    Fala "  Nao consegui ler a lista de dispositivos do Windows." 'Red'
    Fala "  Sem isso o teste nao vale: nao concluo nada."
    Fala ""
    exit 3
}
$baseUsb = SoUsb $base
Fala ""
$linha = '  Agora o Windows tem ' + $base.Count + ' dispositivos; ' + $baseUsb.Count + ' sao nos USB.'
Fala $linha 'Gray'
Fala "  (leitor de cartao, teclado, mouse e o que mais estiver plugado)"
Fala ""

$tentativa = 1
while ($tentativa -le $Tentativas) {
    Regua
    Fala ("  TENTATIVA " + $tentativa + " de " + $Tentativas) 'Cyan'
    Fala ""
    Fala "  1) Desplugue o celular do PC."
    if ($tentativa -eq 1) {
        Fala "     (se ja esta fora, so aperte Enter)"
    } else {
        Fala "     Use um cabo ou uma porta DIFERENTE da tentativa anterior."
    }
    Read-Host "     Enter quando o celular estiver fora" | Out-Null

    $antes = SoUsb (LerDispositivos)
    if ($null -eq $antes) {
        Fala ""
        Fala "  A leitura falhou aqui; repetindo esta tentativa." 'DarkYellow'
        Fala ""
        continue
    }

    Fala ""
    Fala "  2) Plugue o celular AGORA e aperte Enter."
    Read-Host "     Enter quando o celular estiver plugado" | Out-Null
    Fala ""
    $linha = '  Olhando o Windows por ate ' + $Espera + ' segundos...'
    Fala $linha 'Gray'

    $conhecidos = IdsDe $antes
    $deuEvento = OlharPorEvento $Espera $conhecidos
    if (-not $deuEvento) {
        $fim = [DateTime]::Now.AddSeconds($Espera)
        while ([DateTime]::Now -lt $fim) {
            $agora = SoUsb (LerDispositivos)
            if ($null -eq $agora) { continue }
            $novos = @($agora | Where-Object { $conhecidos -notcontains $_.DeviceID })
            foreach ($n in $novos) {
                Guardar $n ((Get-Date).ToString('HH:mm:ss'))
                $conhecidos = $conhecidos + $n.DeviceID
            }
            $resta = [int]($fim - [DateTime]::Now).TotalSeconds
            Fala ("     ... " + $resta + "s")
        }
    }
    Fala ""
    if ($Vistos.Count -eq 0) {
        Fala "  Nada novo apareceu nesta tentativa." 'Yellow'
    }
    if ($Samsung.Count -gt 0) { break }
    $tentativa = $tentativa + 1
}

Regua
Fala ""
Fala "  VEREDITO" 'Cyan'
Fala ""

if ($Samsung.Count -gt 0) {
    Fala "  O celular APARECE na USB (VID_04E8). O cabo, a porta e o conector" 'Green'
    Fala "  estao bons." 'Green'
    Fala ""
    Fala "  Agora sim a pergunta e de driver. Rode:"
    Fala "     sonda-otg.bat"
    Fala "  Se ela disser FALTA O DRIVER, o conserto e o Zadig, com o id que"
    Fala "  ela mesma imprime na tela."
    Fala ""
    exit 0
}

if ($Vistos.Count -gt 0) {
    Fala "  Apareceu dispositivo USB, mas NENHUM com VID_04E8 (Samsung)." 'Yellow'
    Fala ""
    Fala "  Pode ser hub/controladora entrando junto, ou o celular enumerando"
    Fala "  com id que nao e Samsung. Cole esta tela no chat do JARVIS."
    Fala ""
    foreach ($v in $Vistos) {
        $linha = '     ' + $v.Name + '  [' + (VidDe $v.DeviceID) + ']  ' + $v.Service
        Fala $linha
    }
    Fala ""
    exit 1
}

$fim2 = '  Em ' + $Tentativas + ' tentativa(s), NADA apareceu quando o celular entrou.'
Fala $fim2 'Red'
Fala ""
Fala "  Isso NAO e driver, e NAO e o Zadig: ele so lista o que aparece. O"
Fala "  Windows simplesmente nao esta vendo o aparelho."
Fala ""
Fala "  Proximo passo: descubra se e contato fisico. Rode:"
Fala "     vigiar-cabo.bat"
Fala "  Ele fica 60 s olhando por evento enquanto voce pressiona e inclina o"
Fala "  conector. Se aparecer em algum angulo, e solda fria e da para segurar"
Fala "  com calco. Se nunca aparecer, e pino quebrado."
Fala ""
Fala "  A ordem que resolve, do mais barato para o mais caro:"
Fala ""
Fala "  1. LIMPE O CONECTOR do celular." 'Yellow'
Fala "     Desligue o celular, olhe o buraco do micro-USB com uma lanterna."
Fala "     Pelusa/poeira encosta nos pinos do meio (os de dados) e deixa a"
Fala "     carga funcionando: e o caso classico de 'carrega mas o PC nao ve'."
Fala "     Tire com palito de dente, sem forca. Nunca metal, nunca liquido."
Fala ""
Fala "  2. TESTE DE PRESSAO (vigiar-cabo.bat)." 'Yellow'
Fala "     Se aparecer em algum angulo, o conector esta com solda fria."
Fala ""
Fala "  3. CABO: tem de ser micro-USB." 'Yellow'
Fala "     Cabo USB-C que passa dados no A34 nao entra no J7, entao ele nao"
Fala "     testa o J7. O que vale e um micro-USB que ja passou dados em algum"
Fala "     aparelho (ou o do carregador, como comparacao)."
Fala ""
Fala "  4. OUTRA PORTA do PC, de tras, direto na placa-mae." 'Yellow'
Fala "     Hub e extensao ficam de fora: eles escondem o que esta atras."
Fala ""
Fala "  5. Se 1 a 4 nao mudarem nada, o conector perdeu os pinos de dados" 'Yellow'
Fala "     (mesma queda que trincou o vidro). Ai e solda ou assistencia."
Fala ""
Fala "  Rode este teste de novo depois de cada mudanca. Ele e curto."
Fala ""
exit 2
