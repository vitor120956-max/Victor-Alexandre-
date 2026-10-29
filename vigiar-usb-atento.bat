@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo.
echo   JARVIS - vigia atenta (5 vezes por segundo, 10 minutos)
echo.
echo   Para conector com mau contato: um aparelho com solda trincada pode
echo   aparecer por menos de um segundo. Aqui a USB e olhada a cada 400 ms.
echo   Deixe a janela aberta e mexa no cabo/conector devagar.
echo   Ao fim de 10 minutos ela fecha sozinha e mostra o arquivo do log.
echo.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0vigiar-usb.ps1" -Intervalo 400 -Minutos 10 %*
if errorlevel 1 (
  echo.
  echo   O script terminou com erro. Cole esta tela no chat do JARVIS.
  pause
)
