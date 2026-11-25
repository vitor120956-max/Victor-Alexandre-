@echo off
chcp 65001 >nul
cd /d "%~dp0"
title JARVIS - instalar o driver do celular
REM Versao: 0.95.5
REM
REM Nasceu de um pedido literal do dono: "pq vc nao faz javris instalar para mim".
REM
REM O que este arquivo faz, na ordem:
REM   1. liga no .env as duas permissoes que o download e a instalacao exigem;
REM   2. chama o JARVIS, que baixa da Samsung, confere o sha256 e instala.
REM
REM Nao edite nada a mao. Ele mesmo escreve o .env se faltar a linha.

echo.
echo   JARVIS - instalar o driver do celular (Samsung USB Driver)
echo.
echo   Isto resolve o caso "a pasta do celular aparece no Explorer mas o"
echo   adb diz que nao tem aparelho nenhum".
echo.
echo   O driver e instalado NO PC. Nada e instalado no celular.
echo   Ele vem do site oficial da Samsung e o sha256 e conferido antes.
echo.

if not exist ".venv\Scripts\python.exe" (
  echo   O .venv ainda nao existe. Rode o iniciar-jarvis.bat uma vez;
  echo   ele cria o ambiente e instala o que falta.
  echo.
  pause
  exit /b 1
)

echo   Ligando as permissoes no .env (so acrescenta o que falta)...
".venv\Scripts\python.exe" configurar-celular.py --driver
if errorlevel 1 (
  echo.
  echo   Nao consegui escrever no .env. Cole esta tela no chat do JARVIS.
  echo.
  pause
  exit /b 1
)

echo.
echo   Baixando e instalando (uns 33 MB; pode pedir confirmacao do Windows)...
echo.
".venv\Scripts\python.exe" escanear-celular.py --driver
echo.
echo ------------------------------------------------------------
echo.
echo   Se o driver instalou, agora: desconecte o cabo, conecte de novo,
echo   toque em "Permitir" no celular, e rode o escanear-celular.bat.
echo.
echo   Deu erro? Copie esta tela inteira e mande no chat do JARVIS.
echo.
pause
