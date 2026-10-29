@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo.
echo   JARVIS - vigiar a USB ao vivo (para descobrir se o celular aparece)
echo.
echo   Deixe esta janela aberta e plugue/desplugue o cabo do celular.
echo   O que entrar ou sair aparece aqui na hora, com apito.
echo   Para parar: feche a janela no X.
echo.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0vigiar-usb.ps1" %*
if errorlevel 1 (
  echo.
  echo   O script terminou com erro. Cole esta tela no chat do JARVIS.
  pause
)
