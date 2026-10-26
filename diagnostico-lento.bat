@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo.
echo   JARVIS - diagnostico de lentidao
echo   Nada e instalado, alterado ou enviado: so mede.
echo.
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" diagnostico.py %*
) else (
  py -3 diagnostico.py %* 2>nul || python diagnostico.py %*
)
echo.
pause
