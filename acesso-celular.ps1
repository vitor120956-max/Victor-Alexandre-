# JARVIS - o mapa do acesso: por onde se entra neste celular?
#
# Por que este arquivo existe: depois de zerar o aparelho, a pergunta que sobrou
# nao era "como zerar" nem "como tirar foto" - era "como eu entro nele". Sem
# entrada nao se troca sistema operacional, nao se instala ROM, nao se liga
# depuracao. E as duas entradas normais de um Android estao quebradas aqui:
#
#   - TOQUE (digitalizador): morto, com toque fantasma;
#   - DADOS NA USB (D+/D- do micro-USB): mortos - carrega, mas nao enumera.
#
# Este guia poe isso numa tabela, diz o que cada caminho exige, e mostra que UMA
# solda reabre tudo. Nao executa nada no aparelho: quem aperta parafuso e o
# tecnico.
#
# ASCII puro de proposito: console do Windows com chcp 65001 embaralha acento.

[CmdletBinding()]
param([switch]$SemPausa)

$ErrorActionPreference = 'Continue'

function Fala([string]$texto, [string]$cor = 'Gray') { Write-Host $texto -ForegroundColor $cor }
function Regua { Fala ('  ' + ('-' * 62)) }

Fala ''
Fala '  JARVIS - o mapa do acesso: por onde se entra neste celular?' 'Cyan'
Fala ''
Fala '  A pergunta nao e "como zerar" nem "como tirar foto". E esta: por onde'
Fala '  se entra? Sem entrada nao se troca sistema operacional, nao se instala'
Fala '  ROM e nao se liga a depuracao.'
Fala ''
Fala '  Versao: 0.64.0'
Fala ''
Regua
Fala ''
Fala '  AS ENTRADAS QUE UM ANDROID TEM' 'Cyan'
Fala ''

Fala '  1. TOQUE NA TELA .................. QUEBRADA' 'Red'
Fala '     toque fantasma: acende, desenha, mas dispara sozinho.'
Fala '     serviria para: Configuracoes, recovery de fabrica, TWRP.'
Fala ''
Fala '  2. DADOS NA PORTA micro-USB ....... QUEBRADA' 'Red'
Fala '     60 segundos de pressao e inclinacao e nada apareceu no Windows,'
Fala '     com cabos que passam dados em outro aparelho.'
Fala '     serviria para: adb, scrcpy, MTP, Odin, Heimdall, TWRP por USB,'
Fala '     e a troca de sistema operacional.'
Fala ''
Fala '  3. CARTAO microSD ................. ABERTA, mas nao instala sistema' 'Yellow'
Fala '     o leitor funciona (o Windows ja lista o cartao).'
Fala '     serve para: tirar arquivos.'
Fala '     nao serve para: instalar ROM. O recovery de fabrica da Samsung so'
Fala '     aceita pacote assinado PELA SAMSUNG - nao aceita LineageOS nem'
Fala '     ROM de terceiro, e essa assinatura nao se fabrica em casa.'
Fala ''
Fala '  4. WI-FI / NUVEM .................. FECHADA por desenho' 'Red'
Fala '     adb sem fio exige Depuracao USB JA ligada - e ela se liga por toque.'
Fala '     flash de sistema por rede nao existe.'
Fala '     serve para: backup que ja estava configurado antes (Google Fotos).'
Fala ''
Regua
Fala ''
Fala '  A CONCLUSAO, SEM ENFEITE' 'Cyan'
Fala ''
Fala '  Trocar o sistema operacional passa pela porta USB. No Samsung nao existe'
Fala '  instalacao por cartao SD, e o download mode (Odin) so existe pela porta.'
Fala ''
Fala '  Com os dados mortos, nenhuma ROM entra: nem a stock, nem LineageOS.'
Fala '  O bloqueio e fisico - e a solucao tambem.'
Fala ''
Regua
Fala ''
Fala '  A BOA NOTICIA: UMA SOLDA REABRE TUDO' 'Green'
Fala ''
Fala '  Consertar o conector micro-USB devolve os dados. Com dados na porta:'
Fala ''
Fala '     - o scrcpy devolve TECLADO E MOUSE pelo cabo -> a tela quebrada'
Fala '       deixa de ser bloqueio;'
Fala '     - o mesmo cabo serve para o Odin -> a troca de sistema volta a ser'
Fala '       possivel;'
Fala '     - o digitalizador vira OPCIONAL (voce opera pelo PC).'
Fala ''
Fala '  Ou seja: o item mais barato dos dois e o que destrava o mais caro.'
Fala ''
Regua
Fala ''
Fala '  A ORDEM, DEPOIS DO CONSERTO' 'Cyan'
Fala ''
Fala '   1. ligar o celular e plugar no PC com um cabo que ja passou dados;'
Fala '   2. sonda-otg.bat    -> tem de aparecer VID_04E8'
Fala '      (se aparecer, o conector voltou DE VERDADE; se nao aparecer, o'
Fala '      problema e o controlador USB na placa, e o conserto e outro);'
Fala '   3. teclado-pelo-pc.bat -> mouse e teclado do PC operam o celular,'
Fala '      mesmo com o vidro morto (scrcpy --otg);'
Fala '   4. nas Configuracoes: Opcoes do desenvolvedor -> Desbloqueio OEM ->'
Fala '      Depuracao USB (com o mouse do PC, nao com o dedo);'
Fala '   5. Odin no PC + TWRP no aparelho:'
Fala '      download mode = Volume Baixo + Home + Power, depois Volume Cima;'
Fala '   6. no TWRP, sem toque: instalar a ROM por  adb sideload  pelo cabo;'
Fala '   7. LineageOS 18.1 (Android 11) tem build para on7xelte / G610F.'
Fala '      postmarketOS existe para on7xelte, mas em testing: nao e para uso'
Fala '      diario;'
Fala '   8. depois da ROM: celular.espelhar deixa a tela numa janela do'
Fala '      Windows - o uso vira o de um computador pequeno.'
Fala ''
Regua
Fala ''
Fala '  O QUE ISSO NAO RESOLVE (e nao ha software que resolva)' 'Yellow'
Fala ''
Fala '  - DeX nao existe neste modelo: comeca no Galaxy S8 e exige USB-C com'
Fala '    video;'
Fala '  - o J7 Prime nao tem saida de video: a Samsung confirma que MHL nao e'
Fala '    suportado, entao adaptador micro-USB -> HDMI nao funciona;'
Fala '  - se depois da solda continuar sem enumerar, e o controlador USB na'
Fala '    placa: bancada, mais caro que o conector.'
Fala ''
Regua
Fala ''
Fala '  O QUE DIZER AO TECNICO' 'Cyan'
Fala ''
Fala '  1. "quero trocar o conector de carga micro-USB do Galaxy J7 Prime,'
Fala '      SM-G610 / on7xelte, com solda em bancada."'
Fala '  2. "ele CARREGA mas nao passa dados - nao aceito teste so com'
Fala '      carregador."'
Fala '  3. "teste com um PC: plugue e veja se aparece no Gerenciador de'
Fala '      Dispositivos."'
Fala '  4. "se aparecer alguma coisa, o conector esta bom - o resto e'
Fala '      software e eu resolvo."'
Fala ''
Fala '  Se o tecnico disser que "so carrega, entao esta bom", troque de tecnico:' 'DarkYellow'
Fala '  carga e dois pinos; dados sao outros dois.' 'DarkYellow'
Fala ''
Regua
Fala ''
Fala '  Nada foi executado no aparelho por este guia. Ele so mede e explica.' 'DarkGray'
Fala ''
if (-not $SemPausa) {
    Read-Host '  Enter para fechar' | Out-Null
}
exit 0
