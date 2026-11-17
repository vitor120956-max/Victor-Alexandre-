@echo off
chcp 65001 >nul
cd /d "%~dp0"
title JARVIS - criar a chave sem ler a tela
echo.
echo   JARVIS - criar a chave sem ler a tela
echo   Versao: 0.91.28
echo   ----------------------------------------------------------------
echo.
echo   Este atalho abre um Chrome proprio do JARVIS e deixa o JARVIS
echo   trabalhar por dentro dele, pelo protocolo do proprio Chrome.
echo.
echo   Nada de ler a tela, nada de mexer no mouse, nada de area de
echo   transferencia. O seu Chrome do dia a dia NAO e fechado.
echo.
echo   Na PRIMEIRA vez, entre na sua conta do OpenRouter na janela que
echo   vai abrir (clique em Sign In ali dentro). Eu espero ate 5 minutos
echo   e sigo sozinho quando a pagina das chaves aparecer. O login fica
echo   guardado na pasta perfil-cdp e nao e pedido de novo.
echo.
echo   A pagina do OpenRouter as vezes demora. Eu espero ate 90 segundos
echo   e vou mostrando o tempo aqui; se ela nao abrir, digo o que fazer.
echo.
set "segue="
set /p "segue=Tecle Enter para abrir ou N para sair: "
if /i "%segue%"=="N" goto fim
echo.
if not exist ".venv\Scripts\python.exe" goto semvenv
if not exist "chave-no-navegador.py" goto semscript
set "PYTHON=.venv\Scripts\python.exe"

set "CHROME="
if exist "%ProgramFiles%\Google\Chrome\Application\chrome.exe" set "CHROME=%ProgramFiles%\Google\Chrome\Application\chrome.exe"
if not defined CHROME if exist "%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe" set "CHROME=%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"
if not defined CHROME if exist "%LocalAppData%\Google\Chrome\Application\chrome.exe" set "CHROME=%LocalAppData%\Google\Chrome\Application\chrome.exe"
if not defined CHROME goto semchrome

set "PERFIL=%~dp0perfil-cdp"
if not exist "%PERFIL%" mkdir "%PERFIL%" >nul 2>&1
echo   Abrindo o Chrome do JARVIS (o seu fica como esta)...
start "" "%CHROME%" "--user-data-dir=%PERFIL%" --remote-debugging-port=9222 --no-first-run --no-default-browser-check "https://openrouter.ai/settings/keys"
call :esperar_porta
if errorlevel 1 goto semporta
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
echo   Se a mensagem falou de conta, entre na janela do JARVIS com a
echo   sua conta do OpenRouter e rode este atalho de novo.
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

:esperar_porta
rem O Chrome leva alguns segundos para abrir a porta. Aqui a espera e
rem de verdade: ate 20 tentativas, uma por segundo.
set /a "tentativas=0"
:laco_porta
powershell -NoProfile -Command "try { $c = New-Object Net.Sockets.TcpClient; $c.Connect('127.0.0.1', 9222); $c.Close(); exit 0 } catch { exit 1 }" >nul 2>&1
if not errorlevel 1 exit /b 0
set /a "tentativas+=1"
if %tentativas% GEQ 20 exit /b 1
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
echo   Abra o Chrome na mao e rode o pegar-chave.bat de novo.
pause
exit /b 1

:fim
echo.
echo   Sem problema. Nada foi aberto.
pause
exit /b 1
