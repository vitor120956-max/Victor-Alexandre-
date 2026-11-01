@echo off
chcp 65001 >nul
cd /d "%~dp0"
title JARVIS - encerrar a instancia que esta no ar

echo.
echo   JARVIS - encerrar a instancia que esta no ar
echo   ----------------------------------------------------------------
echo   Use quando o JARVIS ja esta rodando mas voce quer a versao
echo   desta pasta, e a janela antiga sumiu (minimizada ou perdida).
echo.
echo   O JARVIS so encerra o processo que se identifica como ele mesmo
echo   em /api/health. Se for outro programa na porta, ele nao toca.
echo.

if not exist "server\instancia.py" goto pasta_errada

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
%PYEXE% -m server.instancia --parar
if errorlevel 1 goto nao_encerrou
goto fim

:nao_encerrou
echo.
echo   Se apareceu "Nao consegui encerrar", faca assim:
echo     1. clique com o botao direito na barra de tarefas
echo     2. abra o Gerenciador de Tarefas
echo     3. procure "python" na aba Detalhes, clique e escolha Finalizar tarefa
echo.
pause
exit /b 1

:fim
echo   Se a API foi encerrada, agora clique duas vezes em iniciar-jarvis.bat.
echo.
pause
exit /b 0

:sem_python
echo.
echo   Nao achei o Python. Rode iniciar-jarvis.bat primeiro: ele cria o .venv.
echo.
pause
exit /b 1

:pasta_errada
echo.
echo   Este arquivo precisa ficar dentro da pasta do JARVIS, ao lado do iniciar.py.
echo   Pasta atual: %CD%
echo.
pause
exit /b 1
