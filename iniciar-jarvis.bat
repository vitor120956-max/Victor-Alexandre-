@echo off
chcp 65001 >nul
cd /d "%~dp0"
title JARVIS - iniciar
setlocal enabledelayedexpansion
REM Bracos ligados: o JARVIS pode ARRUMAR esta maquina quando voce mandar
REM (maquina.arrumar / arrumar-pc.bat). Ele continua sem tocar em driver,
REM essencial nem no que depende do seu uso. Desligue com JARVIS_HOST_ARRUMAR=0
REM no .env se preferir so diagnostico.
if not defined JARVIS_HOST_ARRUMAR set JARVIS_HOST_ARRUMAR=1

echo.
echo   JARVIS - iniciar
echo   ----------------------------------------------------------------
echo   Esta janela faz o que falta e diz o que esta fazendo:
echo     1. cria o ambiente Python (.venv), se ainda nao existir
echo     2. instala as bibliotecas, se faltarem
echo     3. sobe a API com a interface e abre o navegador
echo.
echo   Nao precisa de Node, nem de npm install, nem de Git.
echo.

if not exist "iniciar.py" goto pastel_errada

REM ------------------------------------------------------------------ 1. Python
if exist ".venv\Scripts\python.exe" goto tem_venv

set PYCMD=
py -3 --version >nul 2>nul
if not errorlevel 1 set PYCMD=py -3
if not defined PYCMD (
  python --version >nul 2>nul
  if not errorlevel 1 set PYCMD=python
)
if not defined PYCMD goto sem_python

echo   [1/3] Criando o ambiente Python em .venv (uma vez so, cerca de 1 minuto)...
%PYCMD% -m venv .venv
if not exist ".venv\Scripts\python.exe" goto venv_falhou
echo         pronto.
goto tem_venv

:sem_python
echo.
echo   Nao achei o Python 3 nesta maquina.
echo   Instale o Python 3.11 ou mais novo em https://www.python.org/downloads/windows/
echo   Na primeira tela do instalador, marque "Add python.exe to PATH".
echo   Depois rode este arquivo de novo.
echo.
pause
exit /b 1

:venv_falhou
echo.
echo   A criacao do .venv falhou. Copie as mensagens acima e mande para mim.
echo.
pause
exit /b 1

REM ---------------------------------------------------------- 2. Bibliotecas
:tem_venv
".venv\Scripts\python.exe" -c "import uvicorn, fastapi, dotenv" >nul 2>nul
if not errorlevel 1 goto tem_bibliotecas

echo   [2/3] Instalando as bibliotecas Python (so na primeira vez).
echo         O pip mostra o progresso abaixo. Pode levar de 2 a 5 minutos.
echo.
".venv\Scripts\python.exe" -m pip install --upgrade pip --quiet
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto pip_falhou
echo.
echo         bibliotecas prontas.
goto tem_bibliotecas

:pip_falhou
echo.
echo   A instalacao parou. Duas causas comuns:
echo     - sem internet: conecte e rode de novo;
echo     - mensagem citando "Microsoft Visual C++ 14.0": veja o fim de
echo       docs\PENDRIVE.md, secao "Sem compilador no Windows".
echo.
pause
exit /b 1

REM ---------------------------------------------------------------- 3. Subir
:tem_bibliotecas
if exist "web-dist\index.html" goto tem_interface
if exist "dist\index.html" goto tem_interface
echo   [aviso] Nao achei a interface compilada (web-dist\index.html).
echo           A API sobe, mas a tela nao. Rode atualizar.bat para trazer
echo           a pasta web-dist de novo.
echo.

:tem_interface
echo   [3/3] Subindo o JARVIS. O navegador abre sozinho quando a API responder.
echo         Para parar: feche esta janela no X.
echo.
start "" /min powershell -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -Command "for($i=0;$i -lt 120;$i++){ try { $r=Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:8000/api/health' -TimeoutSec 2; if($r.StatusCode -eq 200){ Start-Process 'http://127.0.0.1:8000'; break } } catch {}; Start-Sleep -Milliseconds 500 }"

".venv\Scripts\python.exe" iniciar.py
set CODIGO=%errorlevel%
echo.
if not "%CODIGO%"=="0" goto saiu_com_erro
echo   A janela do JARVIS foi fechada.
echo.
pause
exit /b 0

:saiu_com_erro
echo   O JARVIS parou com codigo %CODIGO%. Leia a mensagem acima.
echo   Se falar de porta ocupada, o proprio texto mostra a porta seguinte.
echo.
pause
exit /b %CODIGO%

:pastel_errada
echo.
echo   Este arquivo precisa ficar dentro da pasta do JARVIS, ao lado do iniciar.py.
echo   Pasta atual: %CD%
echo.
pause
exit /b 1
