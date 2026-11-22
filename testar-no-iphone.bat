@echo off
chcp 65001 >nul
cd /d "%~dp0"
title JARVIS - testar o jogo no iPhone
setlocal enabledelayedexpansion
REM Versao: 0.95.1
REM
REM O jeito mais facil: ARRASTE a pasta do export WebGL para cima deste arquivo.
REM Ele guarda o jogo, sobe o servidor local e mostra o endereco que voce
REM digita no Safari do iPhone. O APK nao roda no iPhone: o iOS so executa
REM app assinado pela Apple. O mesmo jogo em HTML5 abre no Safari, de graca.

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
  echo   JARVIS - testar o jogo no iPhone
  echo.
  echo   Como usar: arraste a PASTA do export WebGL para cima DESTE arquivo.
  echo.
  echo   Onde esta esse export:
  echo     Unity  -^> Build Settings -^> WebGL -^> Build
  echo     Godot  -^> Projeto -^> Exportar -^> Web
  echo   E a pasta que tem o index.html dentro. Se preferir, arraste o .zip dela.
  echo.
  echo   No iPhone da para deixar como APP: Safari -^> Compartilhar -^>
  echo   "Adicionar a Tela de Inicio". Fica um icone, em tela cheia,
  echo   sem App Store e sem conta Apple (US$ 99/ano).
  echo.
  echo   Ja mandou algum export antes? A lista:
  echo.
  ".venv\Scripts\python.exe" testar-no-iphone.py --lista
  echo.
  pause
  exit /b 0
)

echo.
echo   Guardando o export e subindo o servidor do jogo...
echo.
".venv\Scripts\python.exe" testar-no-iphone.py "%~1"
if errorlevel 1 (
  echo.
  echo   Nao subiu. Veja a mensagem acima; se ela falar de porta ocupada,
  echo   tente de novo com outra porta:
  echo     .venv\Scripts\python testar-no-iphone.py --lista
  echo     .venv\Scripts\python testar-no-iphone.py --servir NOME --porta 8100
  echo.
  pause
)
