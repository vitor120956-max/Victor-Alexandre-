@echo off
chcp 65001 >nul
cd /d "%~dp0"
title JARVIS - escanear o celular
REM Versao: 0.94.2
REM
REM Passa um scanner no celular e diz o que esta errado, com o que fazer.
REM SO LEITURA: nao desinstala, nao limpa cache, nao muda ajuste, nao reinicia.

if not exist ".venv\Scripts\python.exe" (
  echo.
  echo   O .venv ainda nao existe. Rode o iniciar-jarvis.bat uma vez;
  echo   ele cria o ambiente e instala o que falta.
  echo.
  pause
  exit /b 1
)

echo.
echo   JARVIS - escanear o celular
echo.
echo   Antes de comecar, no celular:
echo     1. Ajustes -^> Opcoes do desenvolvedor -^> Depuracao USB: ligada.
echo     2. Conecte o cabo (tem de ser cabo de dados, nao so de carga).
echo     3. Toque em "Permitir" no aviso que aparece na tela do celular.
echo.
echo   O scanner so LE. Nada e alterado no aparelho.
echo.
echo   Ele vai perguntar o que voce ve no aparelho (tela que trava,
echo   frame lento, tela que se mexe sozinha). Responda com os
echo   numeros separados por espaco - sao essas respostas que
echo   colocam a suspeita certa em primeiro lugar.
echo.
echo ------------------------------------------------------------
echo.
".venv\Scripts\python.exe" escanear-celular.py %*
echo ------------------------------------------------------------
echo.
echo   Copie esta tela e me mande o que aparecer - com ela eu ajusto
echo   o que o JARVIS recomenda. O relatorio tambem fica salvo em
echo   storage\diagnosticos.
echo.
pause
