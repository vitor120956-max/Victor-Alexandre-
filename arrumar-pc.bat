@echo off
chcp 65001 >nul
cd /d "%~dp0"
title JARVIS - arrumar o PC
setlocal enabledelayedexpansion

echo.
echo   JARVIS - arrumar o PC
echo   ----------------------------------------------------------------
echo   Este atalho faz o que o JARVIS faria com a tela aberta:
echo     - fecha processo de sobra (devolve RAM)
echo     - remove app de loja sem uso
echo     - desativa tarefa de telemetria e servico inutil
echo     - limpa cache do Windows e a lixeira
echo.
echo   O que ele NAO toca: driver (NVIDIA Container), Microsoft Store,
echo   runtime VCLibs, Seguranca do Windows, Wi-Fi, som, impressao,
echo   WinSxS, hibernacao e a pasta C:\Windows\Installer.
echo.
echo   Tudo fica registrado em storage\limpezas\ com o caminho de volta.
echo   Para desfazer: duplo clique em desfazer-limpeza.bat
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
echo   Quer incluir tambem o "modo ousado"? Ele pega o que tem VOLTA:
echo     Xbox, Teams, Search, Superfetch e hibernacao.
echo   O que nao tem volta continua fora: WinSxS, Windows.old, Installer, Prefetch.
echo     Digite O para ousado, ou so Enter para o modo normal.
echo.
choice /C NO /N /M "  Normal (N) ou ousado (O)? "
set OUSADO=
if errorlevel 2 set OUSADO=--ousado
echo.

REM A trava vale para este processo apenas: fora daqui, o JARVIS continua
REM so olhando a maquina. E o duplo clique + o "sim" abaixo que autorizam.
set JARVIS_HOST_ARRUMAR=1

%PYEXE% -m server.arrumar %OUSADO%
if errorlevel 1 goto falhou

echo.
echo   ----------------------------------------------------------------
echo   Quer que eu execute agora? Digite S e Enter. Qualquer outra
echo   tecla cancela sem mexer em nada.
echo.
pause
%PYEXE% -m server.arrumar --aplicar --sim %OUSADO%
if errorlevel 1 goto falhou
echo.
echo   Pronto. Se alguma linha falhou, quase sempre e falta de
echo   administrador: feche esta janela, clique com o botao direito em
echo   arrumar-pc.bat e escolha "Executar como administrador".
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

:falhou
echo.
echo   Algo falhou. Leia a mensagem acima.
echo   Se disser "travados"/"desligados", rode iniciar-jarvis.bat uma vez
echo   (ele liga os bracos) e tente de novo.
echo.
pause
exit /b 1
