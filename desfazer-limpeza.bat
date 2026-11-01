@echo off
chcp 65001 >nul
cd /d "%~dp0"
title JARVIS - desfazer a ultima limpeza

echo.
echo   JARVIS - desfazer a ultima limpeza
echo   ----------------------------------------------------------------
echo   Religa o que tem volta: servico e tarefa desativados e app de
echo   loja removido (volta pela Microsoft Store).
echo.
echo   O que NAO tem volta: processo fechado e cache apagado. O relatorio
echo   abaixo diz exatamente o que ficou sem retorno.
echo.

if not exist "server\arrumar.py" goto pasta_errada

set PYEXE=
if exist ".venv\Scripts\python.exe" set PYEXE=.venv\Scripts\python.exe
if defined PYEXE goto tem_python
py -3 --version >nul 2>nul
if not errorlevel 1 set PYEXE=py -3
if defined PYEXE goto tem_python
python --version >nul 2>nul
if not errorlevel 1 set PYEXE=python
if defined PYEXE goto tem_python
goto sem_python

:tem_python
set JARVIS_HOST_ARRUMAR=1
%PYEXE% -m server.arrumar --desfazer
if errorlevel 1 goto falhou
echo.
pause
exit /b 0

:sem_python
echo   Nao achei o Python. Rode iniciar-jarvis.bat primeiro.
echo.
pause
exit /b 1

:pasta_errada
echo   Este arquivo precisa ficar dentro da pasta do JARVIS.
echo   Pasta atual: %CD%
echo.
pause
exit /b 1

:falhou
echo.
echo   Nada foi desfeito. Leia a mensagem acima.
echo.
pause
exit /b 1
