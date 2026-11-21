@echo off
chcp 65001 >nul
cd /d "%~dp0"
title JARVIS - criar a chave sem ler a tela
echo.
echo   JARVIS - criar a chave sem ler a tela
echo   Versao: 0.92.4
echo   ----------------------------------------------------------------
echo.
echo   Este atalho usa um Chrome proprio do JARVIS e trabalha por dentro
echo   dele, pelo protocolo do proprio Chrome.
echo.
echo   Nada de ler a tela, nada de mexer no mouse, nada de area de
echo   transferencia. O seu Chrome do dia a dia NAO e fechado.
echo.
echo   Se a janela do JARVIS ja estiver aberta, ele aproveita ela - nao
echo   abre outra e nao recarrega a pagina.
echo.
set "segue="
set /p "segue=Tecle Enter para continuar ou N para sair: "
if /i "%segue%"=="N" goto fim
echo.
if not exist ".venv\Scripts\python.exe" goto semvenv
if not exist "chave-no-navegador.py" goto semscript
set "PYTHON=.venv\Scripts\python.exe"

call :testa_porta
if not errorlevel 1 goto ja_aberto

set "CHROME="
if exist "%ProgramFiles%\Google\Chrome\Application\chrome.exe" set "CHROME=%ProgramFiles%\Google\Chrome\Application\chrome.exe"
if not defined CHROME if exist "%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe" set "CHROME=%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"
if not defined CHROME if exist "%LocalAppData%\Google\Chrome\Application\chrome.exe" set "CHROME=%LocalAppData%\Google\Chrome\Application\chrome.exe"
if not defined CHROME goto semchrome

set "PERFIL=%~dp0perfil-cdp"
if not exist "%PERFIL%" mkdir "%PERFIL%" >nul 2>&1
echo   Abrindo o Chrome do JARVIS (o seu fica como esta)...
rem As opcoes abaixo so tiram trabalho do Chrome na abertura: sem sincronizar
rem conta, sem extensoes, sem atualizacao de componente e sem os pedidos que
rem ele faz sozinho em segundo plano. Num perfil novo isso faz diferenca.
start "" "%CHROME%" "--user-data-dir=%PERFIL%" --remote-debugging-port=9222 --no-first-run --no-default-browser-check --disable-sync --disable-extensions --disable-background-networking --disable-component-update --disable-default-apps --no-service-autorun --disable-features=Translate,MediaRouter,OptimizationHints "https://openrouter.ai/settings/keys"
call :esperar_porta
if errorlevel 1 goto semporta
goto trabalhar

:ja_aberto
echo   A janela do JARVIS ja esta aberta: vou aproveitar ela.

:trabalhar
echo   Chrome do JARVIS pronto na porta 9222.
echo.
"%PYTHON%" chave-no-navegador.py --cdp --autorizar
if errorlevel 1 goto falhou
goto pronto

:semporta
echo.
echo   A porta de controle nao abriu.
echo   Duas causas comuns:
echo     1. o Chrome demorou: rode este atalho de novo, ele aproveita a
echo        janela que ja esta aberta;
echo     2. o Chrome instalado e antigo demais para esta opcao.
echo   Se a janela do JARVIS abriu, deixe-a aberta e rode de novo.
pause
exit /b 1

:falhou
echo.
echo   ----------------------------------------------------------------
echo   Nao deu para terminar. O motivo esta escrito acima, em uma
echo   frase comecando com "NAO DEI".
echo.
echo   Se o problema for a pagina demorando, ha um caminho que nao abre
echo   navegador nenhum: chave-pela-api.bat (pede a chave por HTTPS).
echo.
pause
exit /b 1

:pronto
echo.
echo   ----------------------------------------------------------------
echo   A chave esta no .env e o JARVIS ja usa ela.
echo.
echo   Para conferir que ela responde de verdade:
echo     .venv\Scripts\python conferir-ia.py
echo.
pause
exit /b 0

:testa_porta
powershell -NoProfile -Command "try { $c = New-Object Net.Sockets.TcpClient; $c.Connect('127.0.0.1', 9222); $c.Close(); exit 0 } catch { exit 1 }" >nul 2>&1
exit /b %errorlevel%

:esperar_porta
rem O Chrome leva alguns segundos para abrir a porta. Aqui a espera e
rem de verdade: ate 30 tentativas, uma por segundo.
set /a "tentativas=0"
:laco_porta
call :testa_porta
if not errorlevel 1 exit /b 0
set /a "tentativas+=1"
if %tentativas% GEQ 30 exit /b 1
timeout /t 1 >nul
goto laco_porta

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

:semchrome
echo   Nao achei o chrome.exe nos lugares de sempre.
echo   Use o chave-pela-api.bat: ele cria a chave sem navegador.
pause
exit /b 1

:fim
echo.
echo   Sem problema. Nada foi aberto.
pause
exit /b 1
