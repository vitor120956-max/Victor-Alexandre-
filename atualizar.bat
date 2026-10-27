@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo.
echo   JARVIS - atualizar para a ultima versao
echo.
echo   So faz o que e seguro: se houver arquivo seu alterado, ele para
echo   antes de tocar em qualquer coisa e mostra o que fazer.
echo.

set RAMO=arena/f26cfa7a-victor-alexandre

where git >nul 2>nul
if errorlevel 1 goto semgit
if not exist ".git\" goto semgit

set SUJO=
for /f "delims=" %%i in ('git status --porcelain 2^>nul') do set SUJO=1
if defined SUJO goto sujo

for /f "delims=" %%i in ('git rev-parse --abbrev-ref HEAD') do set ATUAL=%%i
echo   Ramo atual: %ATUAL%

if /i "%ATUAL%"=="%RAMO%" goto jaoneramo
echo   Trocando para %RAMO% ...
git checkout %RAMO% 2>nul
if errorlevel 1 git checkout -b %RAMO% origin/%RAMO%
if errorlevel 1 goto falhou

:jaoneramo
for /f "delims=" %%i in ('git rev-parse --short HEAD') do set ANTES=%%i
echo   Versao local: %ANTES%
echo.
echo   Buscando novidades no GitHub...
git fetch origin %RAMO%
if errorlevel 1 goto sointernet

git merge --ff-only FETCH_HEAD
if errorlevel 1 goto divergiu

for /f "delims=" %%i in ('git rev-parse --short HEAD') do set DEPOIS=%%i
echo.
echo   Agora: %DEPOIS%
if /i "%ANTES%"=="%DEPOIS%" goto semnovidade

echo.
echo   O que entrou:
git log --oneline %ANTES%..%DEPOIS%
echo.

git diff --name-only %ANTES% %DEPOIS% | findstr /i "requirements" >nul
if not errorlevel 1 goto depender

echo   A versao aparece em http://127.0.0.1:8000/api/health
echo.
echo   Pronto. Agora:
echo     1^) feche a janela da API (Ctrl+C) se ela estiver aberta
echo     2^) rode:  .venv\Scripts\python iniciar.py
echo     3^) confira em http://127.0.0.1:8000/api/health
echo.
echo   Se aparecer alguma variavel nova em .env.example, copie a linha
echo   para o seu .env - o arquivo de exemplo nunca sobrescreve o seu.
echo.
pause
exit /b 0

:depender
echo   ATENCAO: as dependencias Python mudaram nesta versao. Rode:
echo     .venv\Scripts\python -m pip install -r requirements.txt
echo.
pause
exit /b 0

:semnovidade
echo.
echo   Ja estava na ultima versao. Nada a fazer.
echo.
pause
exit /b 0

:sujo
echo.
echo   Ha arquivo alterado nesta pasta - nao vou mexer em nada por cima.
echo.
git status --short
echo.
echo   Se as mudancas nao importam:
echo     git checkout -- .
echo   Se importam, copie esses arquivos para outro lugar e rode de novo.
echo.
pause
exit /b 1

:divergiu
echo.
echo   O historico local nao casa com o do GitHub (alguem commitou aqui).
echo   Nada foi perdido. Rode a mao para ver o que houve:
echo     git status
echo     git log --oneline -5
echo.
pause
exit /b 1

:sointernet
echo.
echo   Nao consegui falar com o GitHub. Confira a internet e tente de novo.
echo.
pause
exit /b 1

:semgit
echo.
echo   Esta pasta nao e um repositorio Git (ou o Git nao esta instalado).
echo.
echo   Opcao 1 - instale o Git: https://git-scm.com/download/win
echo   Opcao 2 - baixe o zip da versao atual:
echo     https://codeload.github.com/vitor120956-max/Victor-Alexandre-/zip/refs/heads/arena/f26cfa7a-victor-alexandre
echo   Ao descompactar, NAO apague .env, storage\ nem .venv\.
echo.
pause
exit /b 1

:falhou
echo.
echo   Nao consegui trocar de ramo. Rode "git status" e veja o que aparece.
echo.
pause
exit /b 1
