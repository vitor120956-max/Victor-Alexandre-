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
# insistir no Zadig e perder tempo. Antes de culpar driver, tem de responder uma
# pergunta so: "quando eu plugo o celular, o Windows muda em alguma coisa?"
#
# Este script faz exatamente essa pergunta, N vezes, com pausa para a pessoa
# trocar de cabo/porta sem correr contra o tempo. No fim ele da um veredito com
# base no que VIU, nao no que se imagina:
#
#   - apareceu VID_04E8  -> o celular enumera: agora sim e driver (sonda-otg.bat)
#   - apareceu outra coisa-> aparece algo, mas nao e Samsung: colar no chat
#   - nao apareceu nada  -> NAO e driver: e cabo, porta ou conector do celular
#
# Cuidado que este script evita: dizer "nao apareceu nada" quando na verdade a
# consulta ao Windows falhou. Consulta vazia (0 dispositivos) e tratada como
# erro de leitura, nao como ausencia de aparelho.
#
# Regras que respeita:
# - ASCII puro (console do Windows com chcp 65001 embaralha acento);
# - so leitura: nao instala, nao altera, nao reinicia nada;
# - PowerShell 5.1 puro, sem modulo extra, sem admin;
# - a espera mostra contagem na tela: janela parada nunca e sinal de travamento.

[CmdletBinding()]
param(
    [int]$Espera = 18,
    [int]$Tentativas = 4
)

$ErrorActionPreference = 'Continue'

$Vistos = @()      # tudo que entrou em qualquer tentativa
$Samsung = @()     # so os que tem VID_04E8
$FalhaLeitura = $false

function Fala([string]$texto, [string]$cor = 'Gray') {
    Write-Host $texto -ForegroundColor $cor
}

function Regua {
    Fala ("  " + ("-" * 62))
}

function NosUsb {
    $lista = @(Get-WmiObject -Class Win32_PnPEntity -ErrorAction SilentlyContinue)
    if ($lista.Count -eq 0) { return $null }
    return @($lista | Where-Object { $_.DeviceID -like 'USB\*' })
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

function EsperaNovos([object[]]$antes, [int]$segundos) {
    $idsAntes = IdsDe $antes
    $limite = [DateTime]::Now.AddSeconds($segundos)
    while ([DateTime]::Now -lt $limite) {
        $agora = NosUsb
        if ($null -eq $agora) { return $null }
        $novos = @($agora | Where-Object { $idsAntes -notcontains $_.DeviceID })
        if ($novos.Count -gt 0) { return $novos }
        $resta = [int]($limite - [DateTime]::Now).TotalSeconds
        Fala ("     ... " + $resta + "s  (o Windows ainda nao mudou nada)")
        Start-Sleep -Seconds 2
    }
    return @()
}

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

$base = NosUsb
if ($null -eq $base) {
    Fala ""
    Fala "  Nao consegui ler a lista de dispositivos do Windows." 'Red'
    Fala "  Sem isso o teste nao vale: nada de concluir 'nao apareceu'."
    Fala ""
    exit 3
}

Fala ""
$contagem = '  Agora o Windows tem ' + $base.Count + ' nos USB ligados.'
Fala $contagem 'Gray'
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

    $antes = NosUsb
    if ($null -eq $antes) {
        Fala ""
        Fala "  A leitura do Windows falhou no meio do teste. Rode de novo." 'Red'
        Fala ""
        exit 3
    }

    Fala ""
    Fala "  2) Plugue o celular AGORA e aperte Enter."
    Read-Host "     Enter quando o celular estiver plugado" | Out-Null
    Fala ""
    Fala ("  Olhando o Windows por ate " + $Espera + " segundos...") 'Gray'

    $novos = EsperaNovos $antes $Espera
    if ($null -eq $novos) {
        $FalhaLeitura = $true
        Fala ""
        Fala "  A consulta ao Windows falhou nesta tentativa (nao concluo nada)." 'Red'
    } elseif ($novos.Count -eq 0) {
        Fala ""
        Fala "  Nada novo apareceu nesta tentativa." 'Yellow'
    } else {
        Fala ""
        Fala ("  APARECEU: " + $novos.Count + " no(s) USB novo(s)") 'Green'
        foreach ($n in $novos) {
            $vid = VidDe $n.DeviceID
            $marca = ''
            if ($vid -eq '04E8') { $marca = '   <== SAMSUNG (o celular)' }
            $l1 = '     ' + $n.Name + $marca
            $l2 = '       vid:    ' + $vid
            $l3 = '       id:     ' + $n.DeviceID
            $l4 = '       driver: ' + $n.Service
            Fala $l1 'Green'
            Fala $l2 'Green'
            Fala $l3 'Green'
            Fala $l4 'Green'
            $Vistos = $Vistos + $n
            if ($vid -eq '04E8') { $Samsung = $Samsung + $n }
        }
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

if ($Vistos.Count -gt 0 -and $Samsung.Count -eq 0) {
    Fala "  Apareceu dispositivo USB, mas NENHUM com VID_04E8 (Samsung)." 'Yellow'
    Fala ""
    Fala "  Pode ser hub/controladora entrando junto, ou o celular enumerando"
    Fala "  com id que nao e Samsung. Cole esta tela no chat do JARVIS:"
    Fala ""
    foreach ($v in $Vistos) {
        $linha = '     ' + $v.Name + '  [' + (VidDe $v.DeviceID) + ']  ' + $v.Service
        Fala $linha
    }
    Fala ""
    exit 1
}

if ($FalhaLeitura) {
    Fala "  Houve falha de leitura do Windows durante o teste." 'Red'
    Fala ""
    Fala "  Sem leitura confiavel eu nao digo 'nao apareceu'. Feche outras"
    Fala "  janelas do PowerShell e rode teste-cabo.bat de novo."
    Fala ""
    exit 3
}

$fim = '  Em ' + $Tentativas + ' tentativa(s), NADA apareceu quando o celular entrou.'
Fala $fim 'Red'
Fala ""
Fala "  Isso NAO e driver, e NAO e o Zadig: ele so lista o que aparece. O"
Fala "  Windows simplesmente nao esta vendo o aparelho. A ordem que resolve,"
Fala "  do mais barato para o mais caro:"
Fala ""
Fala "  1. LIMPE O CONECTOR do celular." 'Yellow'
Fala "     Desligue o celular, olhe o buraco do micro-USB com uma lanterna."
Fala "     Pelusa/poeira encosta nos pinos do meio (os de dados) e deixa a"
Fala "     carga funcionando: e o caso classico de 'carrega mas o PC nao ve'."
Fala "     Tire com palito de dente, sem forca. Nunca metal, nunca liquido."
Fala ""
Fala "  2. OUTRA PORTA do PC." 'Yellow'
Fala "     A de tras, direto na placa-mae. Hub e extensao ficam de fora:"
Fala "     eles aparecem como um aparelho so e escondem o que esta atras."
Fala ""
Fala "  3. OUTRO CABO micro-USB." 'Yellow'
Fala "     O do carregador, o do power bank, o de qualquer aparelho antigo."
Fala "     Cabo de 'so carga' existe e nao tem marca externa: a unica forma"
Fala "     de saber e trocar."
Fala ""
Fala "  4. CONFIRME QUE O CELULAR ESTA LIGADO." 'Yellow'
Fala "     Segure o botao de ligar por 10 segundos. Quando plugar, a tela"
Fala "     tem de mostrar carga (raio ou porcentagem). Se nem a carga"
Fala "     aparece, o problema e o conector e nao o cabo."
Fala ""
Fala "  5. Se 1 a 4 nao mudarem nada, o conector do celular esta com pino" 'Yellow'
Fala "     quebrado (mesma queda que trincou o vidro). Ai e solda ou"
Fala "     assistencia: o PC nao tem como consertar isso por software."
Fala ""
Fala "  Rode este teste de novo depois de cada mudanca. Ele e curto."
Fala ""
exit 2
