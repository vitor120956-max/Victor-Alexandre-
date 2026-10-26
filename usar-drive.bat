@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo.
echo   JARVIS - levar livros e repositorios para o Google Drive
echo.
echo   Copia SO a biblioteca e os repositorios. O historico do agente
echo   fica no PC, porque muda toda hora e faria o Drive sincronizar sem parar.
echo   Nada e apagado: a pasta antiga continua onde esta.
echo.
echo   Se a pasta do Drive nao for encontrada, rode assim:
echo     usar-drive.bat "C:\Users\voce\Google Drive\Meu Drive"
echo.
pause
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" mover-dados.py --drive %*
) else (
  py -3 mover-dados.py --drive %* 2>nul || python mover-dados.py --drive %*
)
echo.
pause
