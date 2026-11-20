@echo off
chcp 65001 >nul
cd /d "%~dp0"
title JARVIS - analisar o APK do seu jogo
setlocal enabledelayedexpansion
REM Versao: 0.92.2
REM
REM O jeito mais facil: ARRASTE o APK para cima deste arquivo.
REM Ele copia para a pasta de jogos do JARVIS e analisa na hora.
REM O que ele le: manifesto, motor, arquiteturas, tamanho e assinatura.
REM Nada sai da sua maquina.

if not exist ".venv\Scripts\python.exe" (
  echo.
  echo   O .venv ainda nao existe. Rode o iniciar-jarvis.bat uma vez;
  echo   ele cria o ambiente e instala o que falta.
  echo.
  pause
  exit /b 1
)

if "%~1"=="" (
  echo.
  echo   JARVIS - analisar o APK do seu jogo
  echo.
  echo   Como usar: arraste o arquivo .apk para cima DESTE arquivo.
  echo   Ele copia o APK para a pasta de jogos e analisa em seguida.
  echo.
  echo   Pode arrastar DOIS (ou mais) de uma vez: selecione os arquivos
  echo   e arraste todos juntos. Ele analisa um por um, na ordem.
  echo.
  echo   Se ja mandou algum APK antes, veja a lista:
  echo.
  ".venv\Scripts\python.exe" analisar-jogo.py --lista
  echo.
  pause
  exit /b 0
)

REM `%*` = todos os arquivos arrastados. Com "%~1" o segundo APK
REM era ignorado em silencio, e o dono achava que tinha analisado os dois.
".venv\Scripts\python.exe" analisar-jogo.py %*
echo.
pause
