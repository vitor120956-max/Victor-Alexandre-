@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo.
echo   JARVIS - usar o PC como teclado e mouse do celular
echo.
echo   Para quando o toque da tela morreu (digitalizador quebrado, toque
echo   fantasma). O PC manda teclas e cliques pelo proprio cabo USB, e voce
echo   navega no Android sem encostar no vidro.
echo.
echo   Nao precisa de adaptador OTG nem de mouse: e o cabo que ja esta ligado.
echo.
pause
echo.

set SCRCPY=
if exist "storage\ferramentas\scrcpy\scrcpy.exe" set SCRCPY=storage\ferramentas\scrcpy\scrcpy.exe
if not defined SCRCPY for /r "storage\ferramentas" %%f in (scrcpy.exe) do if not defined SCRCPY set SCRCPY=%%f
if not defined SCRCPY goto semsrcpy

echo   Encontrado: %SCRCPY%
echo.
echo   ANTES DE RODAR - no celular:
echo     1. puxe a barra de notificacoes e toque em "USB" (ou na notificacao
echo        "Conectado como...") e escolha "Carregar este dispositivo".
echo     2. deixe a tela acesa e o cabo plugado no PC.
echo.
echo   No Windows, o scrcpy --otg precisa do driver libusb (Zadig).
echo   Se a janela der erro de USB, e isso. O passo a passo esta no chat:
echo   pergunte "como instalar o zadig para o otg" que o JARVIS responde.
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
echo   O scrcpy terminou com erro.
echo.
echo   Se a mensagem falar de USB, driver ou "Could not open device":
echo     - falta o driver libusb (Zadig) na interface do aparelho;
echo     - no celular, confirme que a notificacao USB esta em "Carregar
echo       este dispositivo" e nao em MTP;
echo     - troque a porta USB do PC (prefira a de tras, sem hub).
echo.
echo   Se falar de "unauthorized" ou permissao, a depuracao nao esta ligada
echo   neste aparelho: o --otg nao precisa dela, mas o Windows pode estar
echo   segurando o dispositivo com o driver de MTP.
echo.
echo   Cole esta tela no chat do JARVIS.
echo.
pause
exit /b 1

:fim
echo.
echo   Fechou. Se destravou e ligou a Depuracao USB, rode no chat:
echo     status do celular
echo.
pause
