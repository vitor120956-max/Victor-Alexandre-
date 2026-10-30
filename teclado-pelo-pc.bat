@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo.
echo   JARVIS - usar o PC como teclado e mouse do celular
echo.
echo   Para quando o toque da tela morreu (digitalizador quebrado, toque
echo   fantasma). O PC manda teclas e cliques pelo proprio cabo USB: o Android
echo   recebe como se fosse um teclado e um mouse ligados nele.
echo.
echo   Nao precisa de adaptador OTG nem de mouse novo: e o cabo que ja esta
echo   ligado. Aqui o cursor do mouse do PC aparece na tela do celular.
echo.
echo   Versao deste arquivo: 0.62.4   (se o numero nao aparecer, este .bat
echo   e antigo: rode atualizar.bat antes de tudo.)
echo.
pause
echo.

set SCRCPY=
if exist "storage\ferramentas\scrcpy\scrcpy.exe" set SCRCPY=storage\ferramentas\scrcpy\scrcpy.exe
if not defined SCRCPY for /r "storage\ferramentas" %%f in (scrcpy.exe) do if not defined SCRCPY set SCRCPY=%%f
if not defined SCRCPY goto semsrcpy

echo   Encontrado: %SCRCPY%
for /f "usebackq delims=" %%v in (`"%SCRCPY%" --version 2^>^&1`) do if not defined VERSAO set VERSAO=%%v
echo   Versao: %VERSAO%
echo.

echo   IMPORTANTE: voce NAO precisa mexer na tela do celular.
echo   Nada de puxar a barra de notificacoes, nada de tocar em menu.
echo   O que solta o MTP e o driver do PC (passo do Zadig); depois disso
echo   quem mexe em tudo e o mouse do PC.
echo.
echo   Deixe a tela acesa e o cabo plugado. Se a tela estiver no PIN,
echo   e ali mesmo que voce vai digitar com o teclado do PC.
echo.
echo   Como usar, depois que a janela abrir:
echo     - o cursor do mouse do PC passa a andar na tela do CELULAR;
echo     - clique = toque; arraste = deslizar;
echo     - digite o PIN no teclado do PC e aperte Enter;
echo     - Esc volta, Tab e setas navegam, Enter confirma.
echo.
echo   Para abrir a barra de notificacoes sem tocar na tela:
echo     clique no topo da tela e ARRASTE para baixo (com o mouse do PC);
echo     a tecla Windows do teclado tambem costuma abrir a gaveta.
echo.
echo   Conferindo o driver do Windows antes de abrir (leva alguns segundos):
echo.
if not exist "sonda-otg.ps1" goto semSonda
powershell -NoProfile -ExecutionPolicy Bypass -File "sonda-otg.ps1"
goto depoisSonda

:semSonda
echo   (sonda-otg.ps1 nao esta aqui - pulando a conferencia do driver)

:depoisSonda
echo.
pause
echo.
echo   Abrindo... (olhe a tela do CELULAR, nao a do PC)
echo.
"%SCRCPY%" --otg
if errorlevel 1 goto falhou
goto fim

:semsrcpy
echo   Nao achei o scrcpy em storage\ferramentas.
echo.
echo   Rode primeiro, no chat do JARVIS:
echo     celular.preparar
echo.
echo   Ele baixa o adb e o scrcpy e confere o SHA-256.
echo.
pause
exit /b 1

:falhou
echo.
echo   O scrcpy terminou com erro. O erro mais comum e este:
echo.
echo     ERROR: Could not find any USB device
echo.
echo   Isso NAO e o cabo e NAO e o celular: e o driver do Windows. O driver
echo   de MTP (que faz o "Desbloqueie para acessar os dados") esta segurando
echo   o aparelho, e o modo --otg precisa falar com ele por outro driver.
echo.
echo   A sonda acima ja disse qual driver esta em uso e qual e o id do
echo   aparelho. Se ela disse "FALTA O DRIVER", siga por aqui.
echo   Conserto (uma vez so, com o celular plugado):
echo.
echo     1. baixe o Zadig:  https://zadig.akeo.ie
echo        (e um .exe unico, nao instala nada)
echo     2. abra o Zadig
echo     3. menu Options -^> List All Devices
echo     4. no seletor do meio, escolha o aparelho Samsung
echo        (aparece como SAMSUNG Mobile USB Composite Device, MTP,
echo         SM-G610M ou parecido; ignore o leitor de cartao e o mouse)
echo     5. no campo da direita, escolha WinUSB (ou libusb-1.0)
echo     6. clique em Replace Driver e espere terminar
echo     7. rode este .bat de novo
echo.
echo   Depois disso o aparelho deixa de aparecer no Explorer como "celular":
echo   e normal, o driver mudou. O MTP volta quando voce desfizer (fim desta
echo   tela).
echo.
echo   Se o Zadig nao resolver, o plano B e o driver oficial do Google:
echo     - baixe  https://dl.google.com/android/repository/usb_driver_r13-windows.zip
echo     - Gerenciador de Dispositivos -^> direito no aparelho -^> Atualizar
echo       driver -^> Procurar no computador -^> Escolher em uma lista -
echo       -^> Todos os dispositivos -^> Com disco -^> android_winusb.inf
echo       -^> Android ADB Interface
echo     (relatado como o que faz adb, scrcpy e scrcpy --otg funcionarem)
echo.
echo   -- "unknown option --otg" ou "unrecognized" --
echo      O scrcpy instalado e antigo. Rode  celular.preparar  no chat
echo      para baixar a versao atual.
echo.
echo   -- "Could not find any ADB device" --
echo      Esse e do modo normal (sem --otg) e significa depuracao desligada.
echo      Aqui nao se aplica: o --otg nao usa adb.
echo.
echo   -- nada aparece e volta na hora --
echo      Confirme que o celular esta com a tela acesa e o cabo na porta de
echo      tras do PC, sem hub.
echo.
echo   Para voltar o aparelho ao normal depois de usar o --otg:
echo      Gerenciador de Dispositivos -^> direito no aparelho -^>
echo      Desinstalar dispositivo -^> desconecte e reconecte o cabo.
echo      O Windows reinstala o MTP sozinho.
echo.
echo   Para rever o diagnostico do driver a qualquer momento, rode:
echo     sonda-otg.bat
echo.
echo   Cole esta tela no chat do JARVIS se continuar.
echo.
pause
exit /b 1

:fim
echo.
echo   Fechou a janela do teclado.
echo.
echo   Se destravou e ligou a Depuracao USB, rode no chat:
echo     status do celular
echo.
echo   Se ainda falta ligar a Depuracao USB, o caminho com o mouse do PC:
echo     Configuracoes -^> Sobre o telefone -^> Informacoes do software
echo     -^> "Numero da versao" (7 cliques) -^> voltar
echo     -^> Opcoes do desenvolvedor -^> Depuracao USB
echo.
pause
