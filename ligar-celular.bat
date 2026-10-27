@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo.
echo   JARVIS - ligar a camada do celular no .env
echo.

if exist ".venv\Scripts\python.exe" goto venv
where py >nul 2>nul
if errorlevel 1 goto sempython
py configurar-celular.py
if errorlevel 1 goto falhou
goto fim

:venv
".venv\Scripts\python.exe" configurar-celular.py
if errorlevel 1 goto falhou
goto fim

:falhou
echo.
echo   Nao consegui configurar. Cole esta tela no chat do JARVIS.
echo.
pause
exit /b 1

:sempython
echo   Nao achei o Python (nem .venv nem o comando py).
echo   Rode na mao, dentro de D:\JARVIS:
echo     .venv\Scripts\python configurar-celular.py
echo.
pause
exit /b 1

:fim
pause
exit /b 0
