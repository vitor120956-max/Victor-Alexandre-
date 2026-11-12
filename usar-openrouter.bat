@echo off
chcp 65001 >nul
cd /d "%~dp0"
title JARVIS - chave do OpenRouter (DeepSeek de graca)
echo.
echo   JARVIS - usar o OpenRouter
echo   Versao: 0.89.1
echo   ----------------------------------------------------------------
echo   Serve para ter DeepSeek de graca, sem cartao.
echo.
echo   Este .bat faz tres coisas:
echo     1. aponta o JARVIS para o OpenRouter
echo     2. pede a chave SEM mostrar o que voce digita
echo     3. grava no .env e testa na hora
echo.
echo   Antes, em openrouter.ai/keys: crie a chave e copie.
echo   A chave comeca com sk-or-v1-
echo.
if not exist ".venv\Scripts\python.exe" goto semvenv
if not exist "configurar-chave.py" goto semscript
echo   Cole a chave quando ele pedir e aperte Enter.
echo.
".venv\Scripts\python.exe" configurar-chave.py --provedor openrouter --testar
echo.
echo   Terminou. Se apareceu a resposta "ok", o cerebro esta de pe.
echo   A tela do JARVIS ja usa a chave nova sozinha, sem reiniciar.
echo.
pause
exit /b 0

:semvenv
echo   Nao encontrei o .venv nesta pasta.
echo   Rode iniciar-jarvis.bat uma vez (ele cria o ambiente) e volte aqui.
pause
exit /b 1

:semscript
echo   Nao encontrei configurar-chave.py nesta pasta.
echo   Voce esta na pasta certa do JARVIS? A mesma do iniciar-jarvis.bat.
pause
exit /b 1
