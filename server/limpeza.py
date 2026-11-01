"""Debloat: o que dá para tirar do Windows sem quebrar nada.

A pergunta que gerou isto veio com cinco fotos do Gerenciador de Tarefas: *“tem
processos que sempre estão rodando sem funcionalidade ... fazer um debloat do que
não usamos e não é necessário, que só ocupa espaço”*.

O que as fotos mostram tem **três origens diferentes**, e misturar as três é o
erro mais comum de “debloat” de vídeo na internet:

1. **Windows de fábrica** — app de loja (Tempo, Notícias, Xbox, Cortana, Solitaire),
   tarefas de telemetria, serviços que ninguém usa (`RetailDemo`, `Fax`,
   `MapsBroker`). Isto ocupa **disco** e um pouco de RAM, e sai limpo.
2. **Programa que você instalou** — Google Drive, Chrome, Office Click-to-Run,
   WebView2. Não é bloat do Windows: é o que você usa. Tirar é decisão sua, não
   “limpeza”. O relatório separa e diz isso.
3. **Peça de driver** — NVIDIA Container, Intel DSA, Stereo Vision. Já explicado
   em `processos.py`.

Por isso o módulo **não tem uma lista mágica de `Remove-AppxPackage`**: ele
primeiro **lê** o que existe na máquina, cruza com um catálogo curado, e só
recomenda o que está de fato instalado — com o comando, o tamanho medido e a
volta. Aplicativo que não está no catálogo aparece como *“não classifico”*, e
não recebe palpite.

Regra de ouro repetida em todo lugar: **nada aqui executa nada.** `plano()`
devolve texto — um `.bat` com uma linha por comando — para você ler antes de
rodar. `executar` não existe nesta camada, e não vai existir sem você mandar.

Fontes do que está escrito em cada ficha: documentação da Microsoft sobre
serviços e tarefas do Windows 10/11, e o comportamento observado das próprias
caixas de diálogo (o texto de “se remover” é o que o Windows mostra). Nenhum
script de terceiro foi copiado ou executado.
"""
from __future__ import annotations

import json
import platform
import subprocess
from typing import Any

CRIACAO_SEM_JANELA = 0x08000000


class LimpezaError(RuntimeError):
    """Falha ao ler a máquina."""


# ---------------------------------------------------------------------------
# Catálogo de pacotes da Store (Appx). `chave` casa por trecho do PackageName.
#
# `veredito`:
#   sobra     -> não faz falta para tarefa nenhuma; sai inteiro
#   cuidado   -> pode ser útil dependendo de como você usa o PC
#   essencial -> NUNCA entra no plano (runtime, Store, Segurança, codecs)
# ---------------------------------------------------------------------------

APPS: list[dict[str, Any]] = [
    # ------------------------------------------------------------ ruído puro
    {"chave": "bingweather", "nome": "MSN Tempo", "veredito": "sobra", "mb": 60,
     "o_que_e": "previsão do tempo com notícias da MSN",
     "se_remover": "o widget de clima do menu Iniciar some; previsão continua no navegador"},
    {"chave": "bingnews", "nome": "MSN Notícias", "veredito": "sobra", "mb": 70,
     "o_que_e": "leitor de notícias da MSN",
     "se_remover": "some o feed de notícias do menu Iniciar e da barra de widgets"},
    {"chave": "bingfinance", "nome": "MSN Finanças", "veredito": "sobra", "mb": 55,
     "o_que_e": "cotações e notícias de mercado", "se_remover": "nada que o Windows use"},
    {"chave": "gethelp", "nome": "Obter Ajuda", "veredito": "sobra", "mb": 25,
     "o_que_e": "app que abre a página de suporte da Microsoft",
     "se_remover": "o link “Obter ajuda” de Configurações abre o navegador"},
    {"chave": "getstarted", "nome": "Dicas (Introdução)", "veredito": "sobra", "mb": 40,
     "o_que_e": "tutorial de primeiros passos que reaparece depois de atualização",
     "se_remover": "as dicas de boas-vindas somem"},
    {"chave": "feedbackhub", "nome": "Hub de Comentários", "veredito": "sobra", "mb": 45,
     "o_que_e": "app para mandar sugestão e erro à Microsoft",
     "se_remover": "você perde o canal de feedback; o Windows continua igual"},
    {"chave": "solitaire", "nome": "Solitaire Collection", "veredito": "sobra", "mb": 220,
     "o_que_e": "jogo de cartas com anúncio e assinatura",
     "se_remover": "o jogo sai; nada do sistema depende dele"},
    {"chave": "mixedreality", "nome": "Portal de Realidade Misturada", "veredito": "sobra", "mb": 30,
     "o_que_e": "central de headset de VR — só serve com óculos compatível",
     "se_remover": "sem headset, não muda nada"},
    {"chave": "microsoft3dviewer", "nome": "Visualizador 3D", "veredito": "sobra", "mb": 35,
     "o_que_e": "abre arquivos .3mf/.glb", "se_remover": "arquivos 3D abrem em outro programa"},
    {"chave": "print3d", "nome": "Impressão 3D", "veredito": "sobra", "mb": 40,
     "o_que_e": "assistente de impressora 3D", "se_remover": "só importa se você tem impressora 3D"},
    {"chave": "549981c3f5f10", "nome": "Cortana", "veredito": "sobra", "mb": 60,
     "o_que_e": "assistente da Microsoft, descontinuado no Windows 11",
     "se_remover": "some a busca por voz; a busca do menu Iniciar continua"},
    {"chave": "clipchamp", "nome": "Clipchamp", "veredito": "sobra", "mb": 150,
     "o_que_e": "editor de vídeo com marca d'água e limite no plano grátis",
     "se_remover": "edição de vídeo fica com FFmpeg (`video.*`) ou com o que você já usa"},
    {"chave": "spotify", "nome": "Spotify (da loja)", "veredito": "sobra", "mb": 190,
     "o_que_e": "instalador de Spotify que vem de fábrica em algumas máquinas",
     "se_remover": "sai a versão de loja; o app do site continua funcionando igual"},
    {"chave": "disney", "nome": "Disney+", "veredito": "sobra", "mb": 45,
     "o_que_e": "atalho de assinatura pré-instalado", "se_remover": "só tira o atalho"},
    {"chave": "tiktok", "nome": "TikTok", "veredito": "sobra", "mb": 90,
     "o_que_e": "app pré-instalado em algumas máquinas", "se_remover": "sai, e o site continua"},
    {"chave": "facebook", "nome": "Facebook", "veredito": "sobra", "mb": 60,
     "o_que_e": "app pré-instalado", "se_remover": "sai, e o site continua"},
    {"chave": "candycrush", "nome": "Candy Crush", "veredito": "sobra", "mb": 180,
     "o_que_e": "jogo que o Windows instala sozinho na primeira sessão",
     "se_remover": "sai; pode voltar depois de uma atualização grande"},
    {"chave": "linkedin", "nome": "LinkedIn", "veredito": "sobra", "mb": 40,
     "o_que_e": "app pré-instalado", "se_remover": "sai, e o site continua"},
    {"chave": "officehub", "nome": "Hub do Office", "veredito": "sobra", "mb": 45,
     "o_que_e": "vitrine que anuncia Office — **não** é o Office instalado",
     "se_remover": "quem tem Office de verdade não perde nada"},
    {"chave": "teams", "nome": "Microsoft Teams (consumidor)", "veredito": "cuidado", "mb": 300,
     "o_que_e": "Teams que abre no boot e pede login pessoal",
     "se_remover": "se você usa Teams do trabalho, **não remova por aqui** — desinstale pelo painel"},
    {"chave": "zunemusic", "nome": "Media Player (Groove)", "veredito": "cuidado", "mb": 70,
     "o_que_e": "tocador de música padrão do Windows",
     "se_remover": "arquivos de áudio abrem com o VLC (que está no catálogo portátil)"},
    {"chave": "zunevideo", "nome": "Filmes e TV", "veredito": "sobra", "mb": 80,
     "o_que_e": "aluguel de filme da Microsoft", "se_remover": "some a loja de vídeo"},
    {"chave": "windowsmaps", "nome": "Mapas", "veredito": "sobra", "mb": 130,
     "o_que_e": "mapa offline do Windows", "se_remover": "o mapa passa a ser o do navegador"},
    {"chave": "windowsalarms", "nome": "Alarme e Relógio", "veredito": "cuidado", "mb": 25,
     "o_que_e": "alarme, cronômetro e timer", "se_remover": "perde o timer nativo"},
    {"chave": "windowssoundrecorder", "nome": "Gravador de Som", "veredito": "cuidado", "mb": 15,
     "o_que_e": "grava áudio do microfone", "se_remover": "use FFmpeg para gravar (`video.*`)"},
    {"chave": "microsoftpeople", "nome": "Pessoas", "veredito": "cuidado", "mb": 30,
     "o_que_e": "agenda de contatos integrada", "se_remover": "contatos continuam no Outlook/conta"},
    {"chave": "yourphone", "nome": "Vínculo com o Telefone", "veredito": "cuidado", "mb": 120,
     "o_que_e": "espelha notificação e foto do celular por Wi-Fi",
     "se_remover": "perde o espelhamento sem cabo; o scrcpy por USB continua"},
    {"chave": "xbox", "nome": "Xbox (app e overlays)", "veredito": "cuidado", "mb": 260,
     "o_que_e": "app Xbox, Game Bar, overlay de gravação e identidade de jogos",
     "se_remover": "perde Game Bar e gravação por atalho; jogo da Microsoft Store pode pedir de volta"},
    # ------------------------------------------------------------- intocáveis
    {"chave": "windowsstore", "nome": "Microsoft Store", "veredito": "essencial", "mb": 90,
     "o_que_e": "loja; sem ela não há como reinstalar nenhum app removido",
     "se_remover": "é a sua rede de segurança: fica"},
    {"chave": "desktopappinstaller", "nome": "Instalador de App (winget)", "veredito": "essencial", "mb": 20,
     "o_que_e": "o `winget`, usado para instalar e restaurar pacotes",
     "se_remover": "sem ele, restaurar app removido fica manual"},
    {"chave": "sechealthui", "nome": "Segurança do Windows", "veredito": "essencial", "mb": 40,
     "o_que_e": "o antivírus e o firewall do próprio Windows",
     "se_remover": "remover isso deixa a máquina sem proteção"},
    {"chave": "vclibs", "nome": "VCLibs / UI.Xaml (runtime)", "veredito": "essencial", "mb": 60,
     "o_que_e": "biblioteca que **outros** apps da loja usam",
     "se_remover": "quebra apps que nem estão nesta lista"},
    {"chave": "windowscalculator", "nome": "Calculadora", "veredito": "essencial", "mb": 15,
     "o_que_e": "calculadora padrão", "se_remover": "não vale o risco por 15 MB"},
    {"chave": "windows.photos", "nome": "Fotos", "veredito": "essencial", "mb": 60,
     "o_que_e": "visualizador padrão de imagem", "se_remover": "todo JPG passa a abrir em outro app"},
    {"chave": "screensketch", "nome": "Ferramenta de Captura", "veredito": "essencial", "mb": 15,
     "o_que_e": "recorte de tela (Win+Shift+S)", "se_remover": "perde o print por atalho"},
]

# ---------------------------------------------------------------------------
# Serviços. Todos reversíveis com `sc config ... start= <tipo>`.
# ---------------------------------------------------------------------------

SERVICOS: list[dict[str, Any]] = [
    {"servico": "DiagTrack", "nome": "Experiências do Usuário Conectado e Telemetria", "veredito": "sobra",
     "o_que_e": "envia dados de uso para a Microsoft", "se_parar": "telemetria para; o sistema não sente",
     "tipo_volta": "auto"},
    {"servico": "dmwappushservice", "nome": "WAP Push de Mensagem", "veredito": "sobra",
     "o_que_e": "suporte a mensagem push de operadora — legado de celular", "se_parar": "nada visível",
     "tipo_volta": "manual"},
    {"servico": "MapsBroker", "nome": "Gerenciador de Mapas Baixados", "veredito": "sobra",
     "o_que_e": "baixa mapa offline em segundo plano", "se_parar": "para de baixar mapa; o Mapas ainda abre",
     "tipo_volta": "auto"},
    {"servico": "RetailDemo", "nome": "Demonstração de Varejo", "veredito": "sobra",
     "o_que_e": "modo de loja de shopping, que ninguém em casa usa", "se_parar": "nada",
     "tipo_volta": "manual"},
    {"servico": "WMPNetworkSvc", "nome": "Compartilhamento de Mídia do WMP", "veredito": "sobra",
     "o_que_e": "compartilha música pela rede", "se_parar": "nada, a menos que você use DLNA",
     "tipo_volta": "manual"},
    {"servico": "RemoteRegistry", "nome": "Registro Remoto", "veredito": "sobra",
     "o_que_e": "deixa outro PC ler o registro desta máquina", "se_parar": "fecha um caminho de ataque antigo",
     "tipo_volta": "disabled"},
    {"servico": "Fax", "nome": "Fax", "veredito": "sobra",
     "o_que_e": "envio de fax por modem — sem modem, sem uso", "se_parar": "nada",
     "tipo_volta": "manual"},
    {"servico": "DoSvc", "nome": "Otimização de Entrega", "veredito": "cuidado",
     "o_que_e": "distribui atualização do Windows entre PCs da rede",
     "se_parar": "atualização ainda baixa, só não compartilha; download pode ficar mais lento",
     "tipo_volta": "auto"},
    {"servico": "SysMain", "nome": "Superfetch", "veredito": "cuidado",
     "o_que_e": "pré-carrega programa na RAM conforme o seu hábito",
     "se_parar": "em **HD** costuma piorar o boot; em SSD é indiferente",
     "tipo_volta": "auto"},
    {"servico": "WSearch", "nome": "Windows Search", "veredito": "cuidado",
     "o_que_e": "indexa arquivo para a busca do menu Iniciar e do Explorador",
     "se_parar": "a busca acha menos e demora mais — é o preço de tirar o indexador",
     "tipo_volta": "auto"},
    {"servico": "XblAuthManager", "nome": "Xbox Live Auth", "veredito": "cuidado",
     "o_que_e": "login do Xbox Live", "se_parar": "só importa se você joga jogo da Microsoft Store",
     "tipo_volta": "manual"},
    {"servico": "XblGameSave", "nome": "Xbox Live Save", "veredito": "cuidado",
     "o_que_e": "sincroniza save na nuvem do Xbox", "se_parar": "save deixa de subir para a nuvem",
     "tipo_volta": "manual"},
    {"servico": "XboxNetApiSvc", "nome": "Xbox Live Networking", "veredito": "cuidado",
     "o_que_e": "rede dos jogos da Microsoft Store", "se_parar": "jogo da loja pode não conectar",
     "tipo_volta": "manual"},
    {"servico": "Spooler", "nome": "Fila de impressão", "veredito": "essencial",
     "o_que_e": "imprime em qualquer impressora", "se_parar": "nada imprime, inclusive PDF para impressora",
     "tipo_volta": "auto"},
    {"servico": "WlanSvc", "nome": "Wi-Fi", "veredito": "essencial",
     "o_que_e": "conexão sem fio", "se_parar": "o PC perde o Wi-Fi", "tipo_volta": "auto"},
    {"servico": "W32Time", "nome": "Horário do Windows", "veredito": "essencial",
     "o_que_e": "sincroniza o relógio", "se_parar": "hora erra e quebra certificado de site",
     "tipo_volta": "manual"},
    {"servico": "AudioSrv", "nome": "Áudio", "veredito": "essencial",
     "o_que_e": "som do sistema", "se_parar": "o PC fica mudo", "tipo_volta": "auto"},
    {"servico": "NvContainerLocalSystem", "nome": "NVIDIA Container", "veredito": "cuidado",
     "o_que_e": "painel da NVIDIA, ShadowPlay e checagem de driver — não desenha nada",
     "se_parar": "imagem e FPS iguais; perde painel, gravação e aviso de driver",
     "tipo_volta": "auto"},
]

# ---------------------------------------------------------------------------
# Tarefas agendadas. `/TN` é o caminho completo, como aparece no Agendador.
# ---------------------------------------------------------------------------

TAREFAS: list[dict[str, str]] = [
    {"tarefa": r"\Microsoft\Windows\Application Experience\ProgramDataUpdater",
     "nome": "ProgramDataUpdater (compatibilidade)", "veredito": "sobra",
     "o_que_e": "manda lista de programas instalados para a Microsoft avaliar compatibilidade",
     "se_parar": "nada visível"},
    {"tarefa": r"\Microsoft\Windows\Application Experience\StartupAppTask",
     "nome": "StartupAppTask", "veredito": "sobra",
     "o_que_e": "varre programa de inicialização a cada boot", "se_parar": "nada visível"},
    {"tarefa": r"\Microsoft\Windows\Autochk\Proxy",
     "nome": "Autochk Proxy", "veredito": "sobra",
     "o_que_e": "coleta de telemetria de disco", "se_parar": "nada visível"},
    {"tarefa": r"\Microsoft\Windows\Customer Experience Improvement Program\Consolidator",
     "nome": "CEIP Consolidator", "veredito": "sobra",
     "o_que_e": "junta e envia dados do programa de melhoria", "se_parar": "nada visível"},
    {"tarefa": r"\Microsoft\Windows\Customer Experience Improvement Program\UsbCeip",
     "nome": "USB CEIP", "veredito": "sobra",
     "o_que_e": "telemetria de dispositivo USB", "se_parar": "nada visível"},
    {"tarefa": r"\Microsoft\Windows\Feedback\Siuf\DmClient",
     "nome": "DmClient (feedback)", "veredito": "sobra",
     "o_que_e": "pergunta de satisfação que aparece do nada", "se_parar": "some o convite"},
    {"tarefa": r"\Microsoft\Windows\Feedback\Siuf\DmClientOnScenarioDownload",
     "nome": "DmClient OnScenarioDownload", "veredito": "sobra",
     "o_que_e": "dispara o mesmo convite depois de download", "se_parar": "nada visível"},
    {"tarefa": r"\Microsoft\Windows\Windows Error Reporting\QueueReporting",
     "nome": "QueueReporting (erros)", "veredito": "sobra",
     "o_que_e": "envia relatório de programa que travou", "se_parar": "o erro ainda aparece; só não é enviado"},
    {"tarefa": r"\Microsoft\Windows\Workplace Join\Automatic-Device-Join",
     "nome": "Device Join (domínio)", "veredito": "sobra",
     "o_que_e": "entra em domínio corporativo automaticamente", "se_parar": "nada em PC de casa"},
    {"tarefa": r"\Microsoft\Windows\CloudExperienceHost\CreateObjectTask",
     "nome": "CreateObjectTask", "veredito": "sobra",
     "o_que_e": "prepara a tela de configuração inicial", "se_parar": "nada depois que o PC já está configurado"},
    {"tarefa": r"\Microsoft\Windows\Application Experience\Microsoft Compatibility Appraiser",
     "nome": "Microsoft Compatibility Appraiser", "veredito": "cuidado",
     "o_que_e": "avalia se o PC roda a próxima versão do Windows",
     "se_parar": "atualização grande ainda aparece, só que sem aviso prévio de compatibilidade"},
    {"tarefa": r"\Microsoft\Windows\UpdateOrchestrator\Reboot",
     "nome": "UpdateOrchestrator Reboot", "veredito": "essencial",
     "o_que_e": "reinicia para concluir atualização de segurança",
     "se_parar": "atualização fica pendente e o PC fica sem a correção"},
    {"tarefa": r"\Microsoft\Windows\Defrag\ScheduledDefrag",
     "nome": "Desfragmentação agendada", "veredito": "essencial",
     "o_que_e": "mantém HD organizado (e faz TRIM em SSD)",
     "se_parar": "disco mecânico fica mais lento com o tempo"},
]

# ---------------------------------------------------------------------------
# Espaço em disco: cada item sabe como medir e como limpar.
# `comando` só usa ferramenta do próprio Windows.
# ---------------------------------------------------------------------------

ESPACO: list[dict[str, Any]] = [
    {"id": "win-sxs", "nome": "Component store (WinSxS)", "caminho": r"C:\Windows\WinSxS",
     "veredito": "cuidado",
     "o_que_e": "cópia de segurança das atualizações instaladas; é o que mais cresce no Windows",
     "se_remover": "não se apaga a pasta na mão: `DISM /StartComponentCleanup` remove só a versão antiga e mantém o sistema atualizável",
     "comando": "Dism.exe /Online /Cleanup-Image /StartComponentCleanup /ResetBase",
     "desfazer": "não dá para desfazer a limpeza; o Windows segue atualizando normalmente",
     "ganho": "1 a 8 GB"},
    {"id": "windows-old", "nome": "Windows.old (versão anterior)", "caminho": r"C:\Windows.old",
     "veredito": "sobra",
     "o_que_e": "cópia do Windows anterior, guardada 10 dias após atualizar de versão",
     "se_remover": "perde a opção “voltar para a versão anterior” — depois de 10 dias ela sumiria de qualquer jeito. "
                   "Não se apaga a pasta na mão (o dono dela é o TrustedInstaller): a linha abaixo abre a tela "
                   "certa, e você marca “Instalação anterior do Windows”",
     "comando": "start ms-settings:storagesense",
     "desfazer": "só reinstalando o Windows anterior",
     "ganho": "5 a 20 GB"},
    {"id": "update-cache", "nome": "Cache de atualização", "caminho": r"C:\Windows\SoftwareDistribution\Download",
     "veredito": "sobra",
     "o_que_e": "instaladores de atualização já aplicados; o Windows baixa de novo se precisar",
     "se_remover": "nada: o que já foi instalado continua instalado",
     "comando": "net stop wuauserv & net stop bits & rmdir /s /q C:\\Windows\\SoftwareDistribution\\Download & net start wuauserv & net start bits",
     "desfazer": "não é preciso: a pasta se recria no próximo download",
     "ganho": "300 MB a 3 GB"},
    {"id": "temp-usuario", "nome": "Temporários do usuário", "caminho": r"%LOCALAPPDATA%\Temp",
     "veredito": "sobra",
     "o_que_e": "arquivo que instalador e programa deixam para trás",
     "se_remover": "programa aberto pode reclamar de arquivo ausente; feche tudo antes",
     "comando": r"del /f /s /q %LOCALAPPDATA%\Temp\* & for /d %d in (%LOCALAPPDATA%\Temp\*) do rmdir /s /q %d",
     "desfazer": "não se desfaz — é lixo por definição",
     "ganho": "200 MB a 4 GB"},
    {"id": "temp-windows", "nome": "Temporários do Windows", "caminho": r"C:\Windows\Temp",
     "veredito": "sobra",
     "o_que_e": "resto de instalador e de atualização", "se_remover": "arquivo em uso é pulado; o resto sai",
     "comando": r"del /f /s /q C:\Windows\Temp\* & for /d %d in (C:\Windows\Temp\*) do rmdir /s /q %d",
     "desfazer": "não se desfaz", "ganho": "100 MB a 2 GB"},
    {"id": "lixeira", "nome": "Lixeira", "caminho": r"C:\$Recycle.Bin",
     "veredito": "sobra",
     "o_que_e": "arquivo apagado que ainda ocupa espaço", "se_remover": "o que estava na lixeira some de vez",
     "comando": "PowerShell -NoProfile -Command \"Clear-RecycleBin -Force -ErrorAction SilentlyContinue\"",
     "desfazer": "não se desfaz — confira antes se não precisa de algo",
     "ganho": "0 a 30 GB"},
    {"id": "hiberfil", "nome": "hiberfil.sys (hibernação)", "caminho": r"C:\hiberfil.sys",
     "veredito": "cuidado",
     "o_que_e": "arquivo do tamanho de ~40% da RAM; guarda a sessão para hibernar e para o “início rápido”",
     "se_remover": "perde hibernar **e** o início rápido (o boot fica alguns segundos mais lento)",
     "comando": "powercfg /h off",
     "desfazer": "powercfg /h on",
     "ganho": "40% da RAM (1,6 GB em 4 GB)"},
    {"id": "delivery", "nome": "Cache de Otimização de Entrega", "caminho": r"C:\Windows\ServiceProfiles\NetworkService\AppData\Local\Microsoft\Windows\DeliveryOptimization",
     "veredito": "sobra",
     "o_que_e": "pedaço de atualização guardado para repartir com outros PCs",
     "se_remover": "nada", "comando": "PowerShell -NoProfile -Command \"Delete-DeliveryOptimizationCache -Force\"",
     "desfazer": "não é preciso", "ganho": "100 MB a 2 GB"},
    {"id": "prefetch", "nome": "Prefetch", "caminho": r"C:\Windows\Prefetch",
     "veredito": "essencial",
     "o_que_e": "índice que deixa o programa abrir mais rápido",
     "se_remover": "NÃO limpe: o ganho é de MB e o custo é boot mais lento",
     "comando": "", "desfazer": "", "ganho": "—"},
    {"id": "winsxs-manual", "nome": "Pasta Instalar (C:\\Windows\\Installer)", "caminho": r"C:\Windows\Installer",
     "veredito": "essencial",
     "o_que_e": "cache de desinstalação do MSI; apagar quebra “Desinstalar” de vários programas",
     "se_remover": "NÃO apague. É o erro clássico de “limpador de disco”",
     "comando": "", "desfazer": "", "ganho": "—"},
]

VEREDITO_ROTULO = {
    "sobra": "Sobra — sai sem perda",
    "cuidado": "Decida você — tem uso possível",
    "essencial": "Fica — tirar quebra algo",
}


# ---------------------------------------------------------------------------
# Leitura da máquina
# ---------------------------------------------------------------------------


def _ps(script: str, timeout: int = 90) -> str:
    """PowerShell fixo, sem janela. Script vem do módulo, nunca do usuário."""
    try:
        concluido = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
            capture_output=True,
            text=True,
            timeout=timeout,
            creationflags=CRIACAO_SEM_JANELA if hasattr(subprocess, "CREATE_NO_WINDOW") else 0,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise LimpezaError("Não consegui falar com o PowerShell.") from exc
    return concluido.stdout or ""


def _mb(total: float) -> float:
    return round(float(total) / (1024 * 1024), 1)


def _ps_caminho(caminho: str) -> str:
    """Troca %VAR% pelo equivalente do PowerShell, `$env:VAR`."""
    for variavel in ("LOCALAPPDATA", "APPDATA", "USERPROFILE", "TEMP", "SYSTEMROOT"):
        caminho = caminho.replace(f"%{variavel}%", f"$env:{variavel}")
    return caminho.replace('"', '')


def pasta_existe(caminho: str, timeout: int = 20) -> bool:
    alvo = _ps_caminho(caminho)
    saida = _ps('if (Test-Path -LiteralPath "{}") {{ "sim" }}'.format(alvo), timeout=timeout).strip()
    return saida == "sim"


def medir_pasta(caminho: str, timeout: int = 45) -> float | None:
    """Tamanho de uma pasta em MB, medido. `None` quando não existe ou não deu tempo."""
    script = (
        '$p = "{alvo}"; if (Test-Path -LiteralPath $p) {{ '
        "(Get-ChildItem -LiteralPath $p -Recurse -Force -File -ErrorAction SilentlyContinue | "
        "Measure-Object -Property Length -Sum).Sum }}"
    ).format(alvo=_ps_caminho(caminho))
    try:
        saida = _ps(script, timeout=timeout).strip()
    except LimpezaError:
        return None
    if not saida:
        return None
    try:
        return _mb(float(saida))
    except ValueError:
        return None


def medir_pastas(itens: list[dict[str, Any]] | None = None, *, medir: bool = False) -> dict[str, dict[str, Any]]:
    """Para cada item do catálogo: existe? e, se `medir`, quanto ocupa.

    Somar `C:\\Windows\\WinSxS` leva minutos numa máquina real. Por isso o padrão
    só confere existência (rápido) e a medição é opt-in — quem chamar escolhe
    esperar.
    """
    resultado: dict[str, dict[str, Any]] = {}
    for item in itens if itens is not None else ESPACO:
        caminho = str(item.get("caminho") or "")
        if not caminho:
            continue
        existe = pasta_existe(caminho)
        if not existe:
            continue
        resultado[str(item["id"])] = {
            "existe": True,
            "tamanho_mb": medir_pasta(caminho) if medir else None,
        }
    return resultado


def medir_apps(timeout: int = 120) -> list[dict[str, Any]]:
    """Pacotes da Store instalados para o usuário atual, com nome e tamanho."""
    if platform.system() != "Windows":
        return []
    script = (
        "Get-AppxPackage | Where-Object { -not $_.IsFramework } | "
        "Select-Object Name,PackageFullName,InstallLocation | ConvertTo-Json -Compress"
    )
    saida = _ps(script, timeout=timeout).strip()
    if not saida:
        return []
    try:
        dados = json.loads(saida)
    except json.JSONDecodeError as exc:
        raise LimpezaError("Não consegui ler a lista de aplicativos instalados.") from exc
    if isinstance(dados, dict):
        dados = [dados]
    return [item for item in dados if isinstance(item, dict)]


def medir_servicos(timeout: int = 60) -> dict[str, dict[str, Any]]:
    if platform.system() != "Windows":
        return {}
    saida = _ps(
        "Get-CimInstance Win32_Service | Select-Object Name,State,StartMode | ConvertTo-Json -Compress",
        timeout=timeout,
    ).strip()
    if not saida:
        return {}
    try:
        dados = json.loads(saida)
    except json.JSONDecodeError:
        return {}
    if isinstance(dados, dict):
        dados = [dados]
    return {
        str(item.get("Name")): {"estado": item.get("State"), "inicio": item.get("StartMode")}
        for item in dados
        if isinstance(item, dict) and item.get("Name")
    }


def medir_tarefas(timeout: int = 90) -> dict[str, str]:
    if platform.system() != "Windows":
        return {}
    saida = _ps(
        "Get-ScheduledTask | Select-Object TaskPath,TaskName,State | ConvertTo-Json -Compress",
        timeout=timeout,
    ).strip()
    if not saida:
        return {}
    try:
        dados = json.loads(saida)
    except json.JSONDecodeError:
        return {}
    if isinstance(dados, dict):
        dados = [dados]
    return {
        f"{item.get('TaskPath') or ''}{item.get('TaskName') or ''}": str(item.get("State") or "")
        for item in dados
        if isinstance(item, dict) and item.get("TaskName")
    }


# ---------------------------------------------------------------------------
# Análise (pura) — é o que os testes exercitam
# ---------------------------------------------------------------------------


def _casa(chave: str, nome_pacote: str) -> bool:
    return chave.lower() in nome_pacote.lower()


def analisar_apps(pacotes: list[dict[str, Any]]) -> dict[str, Any]:
    """Cruza os pacotes instalados com o catálogo. Nada fora do catálogo é julgado."""
    fichas: list[dict[str, Any]] = []
    nao_classificados: list[str] = []
    for pacote in pacotes:
        nome = str(pacote.get("Name") or "").strip()
        if not nome:
            continue
        achado = next((item for item in APPS if _casa(item["chave"], nome)), None)
        if achado is None:
            nao_classificados.append(nome)
            continue
        fichas.append(
            {
                "id": achado["chave"],
                "pacote": nome,
                "nome": achado["nome"],
                "veredito": achado["veredito"],
                "o_que_e": achado["o_que_e"],
                "se_remover": achado["se_remover"],
                "tamanho_estimado_mb": achado["mb"],
                "comando": f'powershell -NoProfile -Command "Get-AppxPackage -Name {nome} | Remove-AppxPackage"',
                "desfazer": f"abrir a loja: ms-windows-store://search/?query={achado['nome']}",
            }
        )
    ordem = {"sobra": 0, "cuidado": 1, "essencial": 2}
    fichas.sort(key=lambda item: (ordem.get(item["veredito"], 9), -item["tamanho_estimado_mb"]))
    sobras = [item for item in fichas if item["veredito"] == "sobra"]
    return {
        "apps": fichas,
        "sobras": len(sobras),
        "estimado_sobra_mb": sum(item["tamanho_estimado_mb"] for item in sobras),
        "nao_classificados": sorted(nao_classificados),
        "nao_classificados_total": len(nao_classificados),
    }


def analisar_servicos(servicos: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    fichas: list[dict[str, Any]] = []
    for item in SERVICOS:
        atual = servicos.get(item["servico"])
        if atual is None:
            continue
        fichas.append(
            {
                **{k: item[k] for k in ("servico", "nome", "veredito", "o_que_e", "se_parar")},
                "estado": atual.get("estado"),
                "inicio_atual": atual.get("inicio"),
                "comando": f'sc config {item["servico"]} start= disabled',
                "desfazer": f'sc config {item["servico"]} start= {item["tipo_volta"]} && net start {item["servico"]}',
            }
        )
    ordem = {"sobra": 0, "cuidado": 1, "essencial": 2}
    fichas.sort(key=lambda item: ordem.get(item["veredito"], 9))
    return fichas


def analisar_tarefas(tarefas: dict[str, str]) -> list[dict[str, Any]]:
    fichas: list[dict[str, Any]] = []
    for item in TAREFAS:
        estado = tarefas.get(item["tarefa"])
        if estado is None:
            continue
        fichas.append(
            {
                **{k: item[k] for k in ("tarefa", "nome", "veredito", "o_que_e", "se_parar")},
                "estado": estado,
                "comando": f'schtasks /Change /TN "{item["tarefa"]}" /DISABLE',
                "desfazer": f'schtasks /Change /TN "{item["tarefa"]}" /ENABLE',
            }
        )
    ordem = {"sobra": 0, "cuidado": 1, "essencial": 2}
    fichas.sort(key=lambda item: ordem.get(item["veredito"], 9))
    return fichas


def analisar_espaco(medidos: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    """Só os itens que existem nesta máquina — medição opcional, nunca inventada."""
    fichas: list[dict[str, Any]] = []
    for item in ESPACO:
        achado = medidos.get(item["id"])
        if not achado:
            continue
        fichas.append(
            {
                **{k: item[k] for k in ("id", "nome", "veredito", "o_que_e", "se_remover", "comando", "desfazer", "ganho")},
                "caminho": item["caminho"],
                "tamanho_mb": achado.get("tamanho_mb"),
                "existe": True,
            }
        )
    ordem = {"sobra": 0, "cuidado": 1, "essencial": 2}
    fichas.sort(key=lambda item: (ordem.get(item["veredito"], 9), -(item.get("tamanho_mb") or 0)))
    return fichas


# ---------------------------------------------------------------------------
# Plano + script
# ---------------------------------------------------------------------------


def _limpo(texto: str) -> str:
    """Tira a marcação de markdown: o texto vai para dentro de um .bat, não de uma tela."""
    return texto.replace("**", "").replace("`", "")


def plano(apps: dict[str, Any], servicos: list[dict[str, Any]],
          tarefas: list[dict[str, Any]], espaco: list[dict[str, Any]]) -> dict[str, Any]:
    """Monta o texto que o usuário lê antes de rodar. Não executa nada.

    Só o veredito **sobra** entra como comando ativo. O que é **cuidado** entra
    comentado, com um `rem` na frente: a decisão fica com você, e a linha está
    ali para descomentar depois de pensar.
    """
    linhas: list[str] = []
    restaurar: list[str] = []

    apps_sobra = [item for item in apps["apps"] if item["veredito"] == "sobra"]
    apps_cuidado = [item for item in apps["apps"] if item["veredito"] == "cuidado"]
    servicos_sobra = [item for item in servicos if item["veredito"] == "sobra"]
    servicos_cuidado = [item for item in servicos if item["veredito"] == "cuidado"]
    tarefas_sobra = [item for item in tarefas if item["veredito"] == "sobra"]
    espaco_sobra = [item for item in espaco if item["comando"] and item["veredito"] == "sobra"]
    espaco_cuidado = [item for item in espaco if item["comando"] and item["veredito"] == "cuidado"]

    linhas.append("@echo off")
    linhas.append("title JARVIS - debloat revisavel")
    linhas.append("rem Gerado pelo JARVIS. Uma linha por comando. Nada roda sozinho.")
    linhas.append("rem Leia tudo, feche os programas e rode como administrador.")
    linhas.append("rem Para desfazer: veja o campo restaurar (restaurar-windows.bat).")
    linhas.append("net session >nul 2>&1")
    linhas.append('if %errorlevel% neq 0 echo ATENCAO: rode como administrador, senao metade falha.')
    linhas.append("echo.")
    linhas.append("echo Este script NAO apaga arquivo pessoal: app de loja, tarefa de")
    linhas.append("echo telemetria, servico sem uso e cache do proprio Windows.")
    linhas.append("pause")
    linhas.append("")

    if apps_sobra:
        linhas.append("rem ---------- 1. apps de loja sem uso ----------")
        for item in apps_sobra:
            linhas.append(f"rem {item['nome']} - {_limpo(item['o_que_e'])}")
            linhas.append(item["comando"])
        linhas.append("")

    if apps_cuidado:
        linhas.append("rem ---------- 1b. apps que dependem do seu uso (descomente o que quiser) ----------")
        for item in apps_cuidado:
            linhas.append(f"rem {item['nome']}: {_limpo(item['se_remover'])}")
            linhas.append("rem " + item["comando"])
        linhas.append("")

    if tarefas_sobra:
        linhas.append("rem ---------- 2. tarefas de telemetria ----------")
        for item in tarefas_sobra:
            linhas.append(f"rem {item['nome']}")
            linhas.append(item["comando"])
            restaurar.append(item["desfazer"])
        linhas.append("")

    if servicos_sobra:
        linhas.append("rem ---------- 3. servicos sem uso ----------")
        for item in servicos_sobra:
            linhas.append(f"rem {item['nome']}: {_limpo(item['se_parar'])}")
            linhas.append(item["comando"])
            restaurar.append(item["desfazer"])
        linhas.append("")

    if servicos_cuidado:
        linhas.append("rem ---------- 3b. servicos que dependem do seu uso ----------")
        for item in servicos_cuidado:
            linhas.append(f"rem {item['nome']}: {_limpo(item['se_parar'])}")
            linhas.append("rem " + item["comando"])
            restaurar.append(item["desfazer"])
        linhas.append("")

    if espaco_sobra or espaco_cuidado:
        linhas.append("rem ---------- 4. espaco em disco ----------")
        for item in espaco_sobra:
            linhas.append(f"rem {item['nome']} ({item['ganho']})")
            linhas.append(item["comando"])
            if item["desfazer"].startswith(("powercfg", "sc ", "schtasks")):
                restaurar.append(item["desfazer"])
        for item in espaco_cuidado:
            linhas.append(f"rem OPCIONAL {item['nome']} ({_limpo(item['ganho'])}): {_limpo(item['se_remover'])}")
            linhas.append("rem " + item["comando"])
            if item["desfazer"].startswith(("powercfg", "sc ", "schtasks")):
                restaurar.append(item["desfazer"])
        linhas.append("")

    linhas.append("echo.")
    linhas.append("echo Pronto. Reinicie para o efeito completo.")
    linhas.append("pause")

    restaurar_linhas = [
        "@echo off",
        "title JARVIS - desfazer o debloat",
        "rem Devolve o Windows ao estado anterior. Rode como administrador.",
        "pause",
        "",
    ]
    restaurar_linhas += restaurar or ["rem Nada a restaurar neste plano."]
    restaurar_linhas += ["", "echo Pronto.", "pause"]

    return {
        "script": "\r\n".join(linhas) + "\r\n",
        "restaurar": "\r\n".join(restaurar_linhas) + "\r\n",
        "linhas_comando": sum(
            1 for linha in linhas
            if linha and not linha.startswith(("rem", "echo", "@echo", "title", "pause", "net session", "if %errorlevel%"))
        ),
        "apps": [item["nome"] for item in apps_sobra],
        "apps_opcionais": [item["nome"] for item in apps_cuidado],
        "tarefas": [item["nome"] for item in tarefas_sobra],
        "servicos": [item["nome"] for item in servicos_sobra],
        "servicos_opcionais": [item["nome"] for item in servicos_cuidado],
        "espaco": [item["nome"] for item in espaco_sobra],
        "espaco_opcional": [item["nome"] for item in espaco_cuidado],
        "estimado_apps_mb": apps["estimado_sobra_mb"],
        "resumo": _resumo(apps_sobra, tarefas_sobra, servicos_sobra, espaco_sobra, apps["estimado_sobra_mb"]),
        "aviso": (
            "Nada foi executado. Este texto é o plano: salve como debloat.bat, leia, e "
            "rode como administrador quando quiser. O que é ‘cuidado’ vem comentado, "
            "para você descomentar só o que não usa. O caminho de volta está em “restaurar”."
        ),
    }


def _resumo(apps: list[dict[str, Any]], tarefas: list[dict[str, Any]],
            servicos: list[dict[str, Any]], espaco: list[dict[str, Any]], mb_apps: float) -> str:
    if not any((apps, tarefas, servicos, espaco)):
        return "Nada para tirar: ou a máquina já está limpa, ou nada do catálogo está instalado."
    partes = []
    if apps:
        partes.append(f"{len(apps)} app de loja sem uso (~{round(mb_apps)} MB)")
    if tarefas:
        partes.append(f"{len(tarefas)} tarefa de telemetria")
    if servicos:
        partes.append(f"{len(servicos)} serviço sem uso")
    if espaco:
        partes.append(f"{len(espaco)} limpeza de cache")
    return "Dá para tirar " + ", ".join(partes) + " — e cada item tem volta."


def inventario(*, medir: bool = False) -> dict[str, Any]:
    """Lê a máquina inteira e devolve o diagnóstico. Fora do Windows, diz por quê."""
    sistema = platform.system()
    if sistema != "Windows":
        return {
            "sistema": sistema,
            "lido": False,
            "motivo": "Debloat é do Windows; fora dele não há app de loja, serviço nem pasta do sistema para medir.",
            "apps": [],
            "servicos": [],
            "tarefas": [],
            "espaco": [],
            "catalogo": catalogo(),
        }
    apps = analisar_apps(medir_apps())
    servicos = analisar_servicos(medir_servicos())
    tarefas = analisar_tarefas(medir_tarefas())
    espaco = analisar_espaco(medir_pastas(medir=medir))
    return {
        "sistema": sistema,
        "lido": True,
        "medido": medir,
        "apps": apps,
        "servicos": servicos,
        "tarefas": tarefas,
        "espaco": espaco,
        "rotulos": VEREDITO_ROTULO,
        "catalogo": catalogo(),
    }


def catalogo() -> dict[str, Any]:
    """O que o módulo sabe classificar, sem tocar na máquina."""
    return {
        "apps": len(APPS),
        "servicos": len(SERVICOS),
        "tarefas": len(TAREFAS),
        "espaco": len(ESPACO),
        "regra": (
            "Só entra no plano o que está instalado E está no catálogo. App fora do "
            "catálogo aparece em ‘não classificados’ e não recebe palpite."
        ),
        "intocaveis": [item["nome"] for item in APPS if item["veredito"] == "essencial"],
    }


def relatorio(*, medir: bool = False) -> dict[str, Any]:
    """Inventário + plano em uma chamada — é o que a skill devolve."""
    dados = inventario(medir=medir)
    if not dados.get("lido"):
        return dados
    dados["plano"] = plano(dados["apps"], dados["servicos"], dados["tarefas"], dados["espaco"])
    return dados


def _cli() -> int:
    import sys

    dados = relatorio(medir="--medir" in sys.argv)
    if "--json" in sys.argv:
        print(json.dumps(dados, ensure_ascii=False, indent=2))
        return 0
    if not dados.get("lido"):
        print(dados.get("motivo"))
        return 0
    print(dados["plano"]["resumo"])
    print()
    for chave, titulo in (("apps", "apps de loja"), ("tarefas", "tarefas"), ("servicos", "serviços"), ("espaco", "espaço")):
        itens = dados[chave] if isinstance(dados[chave], list) else dados[chave]["apps"]
        print(f"— {titulo}: {len(itens)}")
        for item in itens:
            if item.get("veredito") != "sobra":
                continue
            extra = f" {item['tamanho_mb']} MB" if item.get("tamanho_mb") else ""
            print(f"   {item['nome']}{extra}")
    print()
    print("Script em dados['plano']['script'] (use --json).")
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli())
