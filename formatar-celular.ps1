# JARVIS - zerar o celular pelos BOTOES (sem toque na tela, sem cabo).
#
# Por que este arquivo existe: o digitalizador do celular morreu (toque fantasma) e
# a porta micro-USB perdeu os pinos de dados. Isso tira do jogo, de uma vez, tudo o
# que depende de toque (Configuracoes) e tudo o que depende de USB (adb, scrcpy,
# MTP). O que sobra e o recovery de fabrica da Samsung, que se opera com Volume e
# Power - botoes fisicos, que continuam funcionando.
#
# A ARMADILHA QUE ESTE ARQUIVO EXISTE PARA EVITAR: FRP.
#
#   Depois de um factory reset, o Android exige que se entre com A MESMA CONTA
#   GOOGLE que estava no aparelho antes (Factory Reset Protection). Se a senha
#   dessa conta nao for conhecida, o celular NAO volta a funcionar nem com a tela
#   consertada: ele para na tela "verifique sua conta" para sempre.
#
#   E o pior detalhe: com a tela sem toque, NAO da para abrir Configuracoes para
#   ver QUAL conta esta la. Por isso a primeira pergunta deste guia e essa - e se
#   a resposta for "nao sei", ele para e nao deixa zerar.
#
# O que este guia NAO faz (e nao existe software que faca):
#   - transformar o celular num PC com DeX: o DeX existe do Galaxy S8 em diante e
#     exige USB-C com saida de video. O J7 Prime e micro-USB de 2016 e nunca teve;
#   - consertar o toque por software;
#   - passar dados pela porta USB que perdeu os pinos.
#
# Codigo de retorno:
#   0 = percorreu o roteiro (o aparelho foi zerado)
#   1 = o usuario desistiu no meio
#   4 = NAO sabe a conta Google: nao zera (risco de FRP)
#
# Regras que respeita:
# - ASCII puro (console do Windows com chcp 65001 embaralha acento);
# - so leitura no PC: nao executa nada no celular - quem aperta os botoes e a mao;
# - PowerShell 5.1 puro, sem modulo extra, sem admin.

[CmdletBinding()]
param(
    [switch]$Roteiro,
    [switch]$SemPausa
)

$ErrorActionPreference = 'Continue'

function Fala([string]$texto, [string]$cor = 'Gray') { Write-Host $texto -ForegroundColor $cor }
function Regua { Fala ('  ' + ('-' * 62)) }
function Linha { Fala '' }

function Espera([string]$pergunta) {
    if ($SemPausa -or $Roteiro) { return '' }
    return (Read-Host $pergunta)
}

function Confirma([string]$pergunta) {
    if ($Roteiro) { Fala ($pergunta + ' s/n') 'DarkGray'; return $true }
    if ($SemPausa) { return $true }
    $r = Read-Host $pergunta
    if ($r -match '^[sSyY]') { return $true }
    return $false
}

# ------------------------------------------------------------------ roteiro
function MostraRoteiro {
    Linha
    Fala '  O CAMINHO, EM ORDEM' 'Cyan'
    Linha
    Fala ''
    Fala '  1. DESLIGAR o celular.'
    Fala '     Segure o botao de ligar por 10 segundos. Se aparecer menu na tela,'
    Fala '     escolha Desligar com as teclas de volume e confirme com o Power.'
    Fala ''
    Fala '  2. ENTRAR NO RECOVERY.'
    Fala '     Com o aparelho desligado, segure JUNTOS:'
    Fala ''
    Fala '        VOLUME CIMA  +  HOME  +  POWER' 'Yellow'
    Fala ''
    Fala '     Solte os tres assim que o logo SAMSUNG aparecer. Nao solte antes.'
    Fala '     Em alguns aparelhos aparece "No command" com um robo deitado:'
    Fala '     nesse caso segure o POWER e toque VOLUME CIMA uma vez.'
    Fala ''
    Fala '  3. ANDAR NO MENU (o menu e azul, letras pequenas).'
    Fala ''
    Fala '        VOLUME BAIXO  = desce a lista' 'Yellow'
    Fala '        VOLUME CIMA   = sobe a lista' 'Yellow'
    Fala '        POWER         = confirma o item destacado' 'Yellow'
    Fala ''
    Fala '  4. ESCOLHER "wipe data/factory reset".'
    Fala '     Desca com Volume Baixo ate essa linha e confirme com Power.'
    Fala '     Na tela seguinte, desca ate "Yes -- delete all user data" e'
    Fala '     confirme com Power. A barra de progresso comeca a andar.'
    Fala ''
    Fala '  5. ESCOLHER "Reboot system now" e confirmar com Power.'
    Fala ''
    Fala '  6. PRIMEIRA LIGACAO.'
    Fala '     Demora de 5 a 15 minutos e o aparelho esquenta. Nao tire a bateria'
    Fala '     e nao aperte nada. Se voltar sozinho para o recovery, repita o passo 5.'
    Fala ''
    Fala '  7. TELA DE CONTA (FRP).'
    Fala '     O Android vai pedir a conta Google que estava no aparelho. E aqui'
    Fala '     que se descobre se a senha esta na mao: sem ela, o celular para aqui.'
    Fala ''
    Regua
    Fala ''
    Fala '  O QUE ISSO RESOLVE - E O QUE NAO RESOLVE' 'Cyan'
    Fala ''
    Fala '  Resolve: apagar tudo (fotos, contas, apps, senha de tela, lixo).'
    Fala ''
    Fala '  NAO resolve, porque e peca quebrada:' 'Yellow'
    Fala '     - o TOQUE na tela (digitalizador) continua morto;'
    Fala '     - os DADOS da porta USB continuam mortos (segue so carregando);'
    Fala '     - e por isso o aparelho continua sem receber teclado, mouse ou PC.'
    Fala ''
    Fala '  Virar PC com DeX: nao existe neste modelo.' 'Yellow'
    Fala '     O Samsung DeX comeca no Galaxy S8 e exige USB-C com saida de video.'
    Fala '     O J7 Prime e micro-USB de 2016: nunca teve DeX, e a porta dele nao'
    Fala '     transmite video nem com adaptador.'
    Fala ''
    Fala '  Qualquer "modo PC" em Android (Termux com area de trabalho, Sentio,'
    Fala '  Taskbar) precisa de entrada - mouse, teclado ou toque. As tres coisas'
    Fala '  estao fora do ar neste aparelho.'
    Fala ''
    Fala '  A ORDEM QUE FUNCIONA: consertar o toque primeiro.' 'Cyan'
    Fala '     Com a tela respondendo, o celular volta a ser um celular util, e o'
    Fala '     reset pode ser feito em Configuracoes, com calma, vendo qual conta'
    Fala '     Google esta la antes de apagar.'
    Fala ''
    Regua
}

# ------------------------------------------------------------------ inicio
Linha
Fala '  JARVIS - zerar o celular pelos BOTOES (sem tela, sem cabo)' 'Cyan'
Linha
Fala ''
Fala '  O toque da tela nao funciona e a porta USB perdeu os dados. Mesmo assim o'
Fala '  Android tem um menu de fabrica que se opera SO com botoes: o recovery.'
Fala '  Este guia leva voce por ele, com pausa em cada passo.'
Fala ''
Fala '  Versao: 0.63.0'
Fala ''

if ($Roteiro) {
    MostraRoteiro
    exit 0
}

# A pergunta que decide se vale continuar: sem a conta Google, o reset vira tijolo.
Regua
Fala ''
Fala '  ANTES DE TUDO - A PERGUNTA QUE DECIDE' 'Cyan'
Fala ''
Fala '  Depois de zerar, o Android exige a MESMA conta Google que estava no'
Fala '  aparelho (protecao contra roubo, chamada FRP).'
Fala ''
Fala '  Se a senha dessa conta nao for conhecida, o celular NAO volta a'
Fala '  funcionar nem depois de consertar a tela: ele para na tela de conta.'
Fala ''
Fala '  E com a tela sem toque nao da para abrir Configuracoes para ver qual'
Fala '  conta esta la. Por isso a pergunta e esta, agora:'
Fala ''
$sabe = Confirma '  Voce sabe o e-mail E a senha da conta Google que esta nesse celular?'
Fala ''
if (-not $sabe) {
    Fala '  Entao NAO zerar agora.' 'Red'
    Fala ''
    Fala '  Sem essa senha, o reset nao devolve o aparelho ao uso: ele para na'
    Fala '  tela "verifique sua conta" e nao sai de la. Voce perde o que estava'
    Fala '  dentro (fotos, conversas) e ganha um tijolo mais limpo.'
    Fala ''
    Fala '  O caminho certo, nesta ordem:'
    Fala ''
    Fala '    1. consertar o toque (tela/digitalizador) em assistencia;' 'Yellow'
    Fala '    2. ligar o aparelho e abrir Configuracoes -^> Contas -^> Google para'
    Fala '       VER qual conta esta la (e Anotar);'
    Fala '    3. recuperar a senha em myaccount.google.com, no PC, se precisar;'
    Fala '    4. so entao zerar - em Configuracoes, com calma, ou por este guia.'
    Fala ''
    Fala '  Se voce ja tem certeza de que a conta esta lembrada, rode o guia de'
    Fala '  novo e responda "s".'
    Fala ''
    exit 4
}

Regua
Fala ''
Fala '  CHECKLIST - confira antes de mexer' 'Cyan'
Fala ''
Fala '    1. BATERIA: pelo menos meia carga. Zerar com bateria fraca pode'
Fala '       deixar o aparelho no meio do processo.'
Fala '    2. CARTAO microSD: se quiser guardar o que esta nele, tire agora.'
Fala '       O reset apaga a memoria interna; o cartao normalmente escapa, mas'
Fala '       nao conte com isso.'
Fala '    3. SENHA DO GOOGLE: anotada ou decorada. Sem ela, nao passe daqui.'
Fala '    4. CONTA SAMSUNG: se existia, tenha a senha tambem (o aparelho pode'
Fala '       pedir a conta Samsung depois do reset).'
Fala '    5. ACEITE: o que esta dentro vai embora. Nao ha desfazer.'
Fala ''
$ok = Confirma '  Tudo conferido e quer seguir?'
Fala ''
if (-not $ok) {
    Fala '  Parado sem tocar em nada. Nada foi apagado.' 'Yellow'
    Fala ''
    exit 1
}

# ------------------------------------------------------------------ execucao
Regua
Fala ''
Fala '  PASSO 1 - DESLIGAR' 'Cyan'
Fala ''
Fala '  Segure o botao de LIGAR por 10 segundos, ate a tela apagar.'
Fala '  Se aparecer o menu de energia, use Volume para escolher Desligar e'
Fala '  Power para confirmar.'
Fala ''
Espera '  Enter quando o celular estiver desligado' | Out-Null
Fala ''

Regua
Fala ''
Fala '  PASSO 2 - ENTRAR NO RECOVERY' 'Cyan'
Fala ''
Fala '  Segure JUNTOS, sem soltar:'
Fala ''
Fala '        VOLUME CIMA  +  HOME  +  POWER' 'Yellow'
Fala ''
Fala '  Solte os TRES quando o logo SAMSUNG aparecer.'
Fala ''
function TentaRecovery {
    $entrou = Confirma '  Apareceu um menu azul com letras pequenas na tela?'
    if ($entrou) { return $true }
    Fala ''
    Fala '  Sem problema - o timing dos tres botoes e chato mesmo. Tente assim:' 'Yellow'
    Fala ''
    Fala '    a) segure VOLUME CIMA e HOME primeiro, e so depois aperte POWER'
    Fala '       - e mantenha os tres por uns 8 segundos;'
    Fala '    b) solte no instante em que o logo aparece (segurar demais reinicia);'
    Fala '    c) se aparecer um robo deitado com "No command", segure POWER e'
    Fala '       toque VOLUME CIMA uma vez;'
    Fala '    d) se ele ligar normal, desligue e tente de novo com mais calma.'
    Fala ''
    Fala '  Se depois de 3 tentativas nao entrar, o botao de VOLUME CIMA pode'
    Fala '  estar com defeito - e ai e assistencia tambem.'
    Fala ''
    return (Confirma '  Tentar de novo agora?')
}

$tentativas = 0
$noRecovery = $false
while ($tentativas -lt 3) {
    $tentativas = $tentativas + 1
    $noRecovery = TentaRecovery
    if ($noRecovery) { break }
    if ($tentativas -lt 3) {
        Espera '  Enter quando estiver pronto para tentar de novo' | Out-Null
        Fala ''
    }
}
if (-not $noRecovery) {
    Fala ''
    Fala '  Nao entrei no recovery com voce. Nada foi apagado.' 'Red'
    Fala ''
    Fala '  Quando quiser tentar de novo, rode este guia outra vez. O roteiro'
    Fala '  completo, sem perguntas, sai com:'
    Fala '     formatar-celular.bat -Roteiro'
    Fala ''
    exit 1
}

Regua
Fala ''
Fala '  PASSO 3 - ANDAR NO MENU' 'Cyan'
Fala ''
Fala '        VOLUME BAIXO = desce     VOLUME CIMA = sobe     POWER = confirma' 'Yellow'
Fala ''
Fala '  Desca ate a linha "wipe data/factory reset" e confirme com POWER.'
Fala ''
Espera '  Enter depois de escolher wipe data/factory reset' | Out-Null
Fala ''

Fala '  Agora aparece uma tela pedindo confirmacao, com varias linhas "No" e'
Fala '  uma "Yes -- delete all user data".'
Fala ''
Fala '  Desca ate a linha do YES e confirme com POWER.'
Fala ''
$apagou = Confirma '  A barra de progresso andou e apareceu "Data wipe complete"?'
Fala ''
if (-not $apagou) {
    Fala '  Se a barra nao andou, o item escolhido foi um "No". Volte ao menu com' 'Yellow'
    Fala '  VOLUME BAIXO e escolha de novo "wipe data/factory reset", descendo ate'
    Fala '  a linha do YES antes de apertar POWER. Nada foi apagado ainda.' 'Yellow'
    Fala ''
    exit 1
}

Regua
Fala ''
Fala '  PASSO 4 - REINICIAR' 'Cyan'
Fala ''
Fala '  De volta ao menu, escolha "Reboot system now" e confirme com POWER.'
Fala ''
Fala '  A primeira ligacao demora de 5 a 15 minutos e o aparelho esquenta.'
Fala '  Nao tire a bateria e nao aperte nada. Se voltar sozinho ao recovery,'
Fala '  repita este passo.'
Fala ''
Espera '  Enter quando o celular estiver na tela de boas-vindas ou de conta' | Out-Null
Fala ''

Regua
Fala ''
Fala '  O APARELHO ESTA ZERADO' 'Green'
Fala ''
Fala '  O que voce vai encontrar agora:'
Fala '     - a tela de boas-vindas do Android, pedindo idioma e Wi-Fi;'
Fala '     - depois, a tela de CONTA, pedindo a conta Google que estava aqui.'
Fala ''
Fala '  E o momento da verdade sobre o FRP: se a senha estiver certa, o aparelho'
Fala '  segue e fica limpo. Se nao estiver, ele para ali.'
Fala ''
Fala '  Mas atencao: para PASSAR dessas telas voce precisa de entrada - toque,'
Fala '  mouse ou teclado. E as tres coisas estao fora do ar neste aparelho.' 'Yellow'
Fala ''
Regua
MostraRoteiro
Fala ''
Fala '  Nada foi executado pelo PC: quem apertou os botoes foi voce.'
Fala '  Este guia nao apaga nada sozinho e nao tem como apagar.' 'DarkGray'
Fala ''
exit 0
