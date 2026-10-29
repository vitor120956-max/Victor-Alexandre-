@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo.
echo   JARVIS - vigia atenta (modo evento, 10 minutos)
echo.
echo   O Windows avisa no instante em que um dispositivo USB entra ou sai,
echo   entao nao existe intervalo para a piscada passar batido.
echo   Deixe a janela aberta e mexa no cabo/conector devagar.
echo   Ao fim de 10 minutos ela fecha sozinha e mostra o arquivo do log.
echo.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0vigiar-usb.ps1" -Modo evento -Minutos 10 %*
if errorlevel 1 (
  echo.
  echo   O script terminou com erro. Cole esta tela no chat do JARVIS.
  pause
)
