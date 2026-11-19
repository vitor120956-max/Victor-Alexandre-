@echo off
chcp 65001 >nul
cd /d "%~dp0"
title JARVIS - criar a chave sem navegador
echo.
echo   JARVIS - criar a chave sem navegador
echo   Versao: 0.91.42
echo   ----------------------------------------------------------------
echo.
echo   Este atalho NAO abre Chrome nenhum. Ele pede a chave ao proprio
echo   OpenRouter, por HTTPS: leva um segundo e nao depende de pagina
echo   carregar.
echo.
if not exist ".venv\Scripts\python.exe" goto semvenv
if not exist "chave-no-navegador.py" goto semscript
set "PYTHON=.venv\Scripts\python.exe"

findstr /B /C:"JARVIS_OPENROUTER_GESTAO=sk-or-v1-" ".env" >nul 2>&1
if not errorlevel 1 goto criar

echo   Na primeira vez falta uma coisa: a chave de gestao.
echo   Ela e uma chave que so serve para criar outras - e o proprio
echo   OpenRouter que oferece isso. E criada uma vez, no seu Chrome
echo   normal (o rapido), e fica guardada no .env para sempre.
echo.
echo   Vou abrir a pagina dela agora. La:
echo     1. clique em Create New Key
echo     2. de o nome jarvis-gestao
echo     3. clique em COPIAR na chave que aparecer
echo   Depois volte para esta janela e aperte Enter: eu leio a area
echo   de transferencia sozinho.
echo.
pause
start "" "https://openrouter.ai/settings/management-keys"
"%PYTHON%" chave-no-navegador.py --gestao
if errorlevel 1 goto falhou
echo.

:criar
echo   Criando a chave do JARVIS (sem limite e sem validade)...
echo.
"%PYTHON%" chave-no-navegador.py --api --autorizar
if errorlevel 1 goto falhou
goto pronto

:pronto
echo.
echo   Pronto: a chave esta no .env e o JARVIS ja usa ela.
echo.
echo   Conferindo a IA de verdade (8 tokens) e, se o modelo do .env
echo   nao existir mais, escolhendo um que exista e gravando...
echo.
"%PYTHON%" conferir-ia.py --corrigir --testar
if errorlevel 1 goto conferencia_falhou
goto conferencia_ok

:conferencia_falhou
echo.
echo   A chave esta gravada, mas a conferencia nao passou.
echo   O motivo esta acima. Se falar de modelo, rode de novo este
echo   atalho: ele escolhe outro. Se falar de credito, a conta esta
echo   sem saldo ou o modelo e pago (use um terminado em :free).
goto fim_ok

:conferencia_ok
echo.
echo   A chave responde. Pode abrir o JARVIS.

:fim_ok
echo.
pause
exit /b 0

:falhou
echo.
echo   ----------------------------------------------------------------
echo   Nao deu para terminar. O motivo esta acima, na linha que comeca
echo   com "NAO DEI".
echo.
echo   Se a mensagem falou de chave de gestao, abra
echo   openrouter.ai/settings/management-keys no seu Chrome, crie uma
echo   chave la e clique em COPIAR; depois rode este atalho de novo.
echo.
pause
exit /b 1

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
