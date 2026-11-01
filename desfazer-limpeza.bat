@echo off
chcp 65001 >nul
cd /d "%~dp0"
REM ---------------------------------------------------------------- elevacao
REM Religar tarefa e servico pede administrador. Se esta janela nao for
REM elevada, o proprio arquivo se reabre pedindo ao Windows - voce so clica
REM Sim no aviso do UAC. Sem isso, 13 de 16 acoes falhavam com acesso negado.
net session >nul 2>&1
if not errorlevel 1 goto ja_admin
echo.
echo   Esta janela nao esta elevada. Vou pedir permissao ao Windows agora.
echo   No aviso do UAC, clique Sim. (Se clicar Nao, sigo sem elevacao.)
powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
if errorlevel 1 goto sem_admin
exit /b 0

:sem_admin
echo.
echo   Nao consegui abrir o pedido de permissao. Sigo assim mesmo: processo e
echo   cache funcionam; tarefa e servico vao falhar com acesso negado.
echo.

:ja_admin
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
