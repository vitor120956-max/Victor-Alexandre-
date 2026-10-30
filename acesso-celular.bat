@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo.
echo   JARVIS - o mapa do acesso: por onde se entra neste celular?
echo.
echo   Sem entrada nao se troca sistema operacional, nao se instala ROM e
echo   nao se liga a depuracao. Este guia mostra o que cada caminho exige,
echo   o que esta aberto e o que esta quebrado, e o que pedir ao tecnico.
echo.
echo   Versao: 0.62.9
echo.
if not exist "acesso-celular.ps1" goto semps1
pause
echo.
powershell -NoProfile -ExecutionPolicy Bypass -File "acesso-celular.ps1"
echo.
pause
exit /b 0

:semps1
echo   Nao achei acesso-celular.ps1 nesta pasta.
echo   Rode atualizar.bat para baixar a versao completa.
echo.
pause
exit /b 1
