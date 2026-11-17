@echo off
chcp 65001 >nul
cd /d "%~dp0"
title JARVIS - pegar a chave no site
echo.
echo   JARVIS - pegar a chave no site, sozinho
echo   Versao: 0.91.28
echo   ----------------------------------------------------------------
echo   (o jeito bom agora e o chrome-cdp.bat: ele nao le a tela)
echo   Um duplo clique e o JARVIS abre a pagina, entra se preciso,
echo   cria a chave, copia e grava no .env dele.
echo   Na primeira vez ele pergunta qual conta do Google e lembra.
echo.
echo   Se o Chrome do JARVIS (chrome-cdp.bat) estiver aberto, ele vai
echo   por dentro dele: sem ler a tela e sem area de transferencia.
echo.
if not exist ".venv\Scripts\python.exe" goto semvenv
if not exist "chave-no-navegador.py" goto semscript
set "PYTHON=.venv\Scripts\python.exe"
powershell -NoProfile -Command "try { $c = New-Object Net.Sockets.TcpClient; $c.Connect('127.0.0.1', 9222); $c.Close(); exit 0 } catch { exit 1 }" >nul 2>&1
if not errorlevel 1 goto via_cdp
echo   Abrindo o site e tentando fazer tudo sozinho...
echo   (se ele nao conseguir clicar, ele avisa e espera voce)
echo.
"%PYTHON%" chave-no-navegador.py --auto --autorizar
if errorlevel 1 goto tentar
goto pronto

:via_cdp
echo   O Chrome do JARVIS esta aberto: vou por dentro dele.
echo.
"%PYTHON%" chave-no-navegador.py --cdp --autorizar
if not errorlevel 1 goto pronto
goto tentar

:tentar
echo.
echo   ----------------------------------------------------------------
echo   Faltou a chave. Ela pode estar copiada agora.
echo   Se voce copiou no site, aperte Enter que eu leio.
echo   Para sair, digite N e Enter.
echo.
echo   Se ele nao conseguiu VER o painel (erro de leitura), rode antes
echo   diagnostico-chave.bat: ele mede a pagina e nao cria nada.
set /p "de_novo=  Enter para tentar / N para sair: "
if /i "%de_novo%"=="N" goto fim
echo.
"%PYTHON%" chave-no-navegador.py --pegar
if errorlevel 1 goto tentar
goto pronto

:pronto
echo.
echo   ----------------------------------------------------------------
echo   Pronto. A chave esta no .env e o JARVIS ja usa ela.
echo.
echo   Para conferir que ela responde de verdade:
echo     .venv\Scripts\python conferir-ia.py
echo.
pause
exit /b 0

:semvenv
echo   Nao encontrei o .venv nesta pasta.
echo   Rode iniciar-jarvis.bat uma vez (ele cria o ambiente) e volte aqui.
pause
exit /b 1

:semscript
echo   Nao encontrei chave-no-navegador.py nesta pasta.
echo   Voce esta na pasta certa do JARVIS? A mesma do iniciar-jarvis.bat.
pause
exit /b 1

:fim
echo.
echo   Sem problema. Quando quiser, rode este .bat de novo.
pause
exit /b 1
