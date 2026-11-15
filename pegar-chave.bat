@echo off
chcp 65001 >nul
cd /d "%~dp0"
title JARVIS - pegar a chave do navegador
echo.
echo   JARVIS - pegar a chave do navegador
echo   Versao: 0.91.11
echo   ----------------------------------------------------------------
echo   Um duplo clique aqui e o JARVIS faz o resto.
echo   Voce nao digita chave nenhuma: ela vem copiada do site.
echo.
if not exist ".venv\Scripts\python.exe" goto semvenv
if not exist "chave-no-navegador.py" goto semscript
echo   Abrindo a pagina de chaves no seu navegador...
".venv\Scripts\python.exe" chave-no-navegador.py --abrir
if errorlevel 1 goto semnavegador
echo.
echo   No site, com a sua conta (voce ja esta logado):
echo     1. clique em Create Key
echo     2. de um nome para a chave (ou deixe o que ele sugere)
echo     3. clique em Create
echo     4. clique no botao COPIAR
echo.
echo   Nao selecione o texto com o mouse: copie pelo botao.
echo.
pause
echo.
:tentar
echo   Lendo a area de transferencia...
echo.
".venv\Scripts\python.exe" chave-no-navegador.py --pegar
if not errorlevel 1 goto pronto
echo.
set /p "de_novo=  Tentar de novo? Aperte Enter. Para sair, digite N e Enter: "
if /i "%de_novo%"=="N" goto fim
echo.
goto tentar

:pronto
echo.
echo   ----------------------------------------------------------------
echo   Pronto. A chave esta no .env e o JARVIS ja usa ela.
echo.
echo   Se quiser conferir que ela responde de verdade:
echo     .venv\Scripts\python conferir-ia.py
echo.
pause
exit /b 0

:semnavegador
echo.
echo   Nao consegui abrir o navegador sozinho.
echo   Abra voce mesmo este endereco:
echo     openrouter.ai/keys
echo.
echo   Depois de copiar a chave, rode este .bat de novo.
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

:fim
echo.
echo   Sem problema. Quando quiser, rode este .bat de novo.
pause
exit /b 1
