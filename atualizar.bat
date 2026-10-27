@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo.
echo   JARVIS - atualizar para a ultima versao
echo.
echo   Antes de continuar: feche a janela da API (o X dela). Arquivo
echo   aberto pela API pode nao ser copiado.
echo.
pause
echo.

if exist ".git\" goto comgit
goto semgit

REM ===========================================================================
REM  Com Git: atualiza pelo repositorio, sem tocar em arquivo seu
REM ===========================================================================
:comgit
where git >nul 2>nul
if errorlevel 1 goto semgit

set RAMO=arena/f26cfa7a-victor-alexandre
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
if not errorlevel 1 echo   ATENCAO: as dependencias Python mudaram - veja o fim desta tela.
goto terminou

REM ===========================================================================
REM  Sem Git (instalado pelo zip): baixa o zip e copia por cima, preservando
REM  .env, storage, .venv e node_modules
REM ===========================================================================
:semgit
echo   Esta pasta nao e um repositorio Git (instalacao pelo zip).
echo   Vou baixar a versao atual do GitHub e copiar por cima.
echo.
echo   Ficam intocados: .env, storage, .venv e node_modules.
echo.
set JARVIS_DESTINO=%CD%
powershell -NoProfile -ExecutionPolicy Bypass -Command "$ErrorActionPreference='Stop'; [Net.ServicePointManager]::SecurityProtocol=[Net.SecurityProtocolType]::Tls12; $ProgressPreference='SilentlyContinue'; $z=$env:TEMP+'\jarvis-novo.zip'; $d=$env:TEMP+'\jarvis-novo'; Invoke-WebRequest -Uri 'https://codeload.github.com/vitor120956-max/Victor-Alexandre-/zip/refs/heads/arena/f26cfa7a-victor-alexandre' -OutFile $z; if(Test-Path $d){Remove-Item $d -Recurse -Force}; Expand-Archive -LiteralPath $z -DestinationPath $d -Force; $r=(Get-ChildItem -LiteralPath $d -Directory | Select-Object -First 1).FullName; robocopy $r $env:JARVIS_DESTINO /E /XF .env /XD .venv storage node_modules .git /NFL /NDL /NJH /NJS; if($LASTEXITCODE -ge 8){exit 1}else{exit 0}"
if errorlevel 1 goto zipfalhou
echo.
echo   Copia concluida.
goto checar_dist

:checar_dist
if not exist "dist\index.html" goto checar_req
echo.
echo   ATENCAO: existe uma pasta dist\ de um build antigo. A API prefere
echo   dist\ a web-dist\, entao a tela continuaria velha. Apague ou renomeie:
echo     rmdir /s /q dist
echo.

:checar_req
echo.
echo   Se esta for a primeira vez que voce atualiza depois de varias versoes,
echo   as dependencias Python podem ter mudado. Se a API reclamar de modulo,
echo   rode:
echo     .venv\Scripts\python -m pip install -r requirements.txt
goto terminou

:terminou
echo.
echo   A versao aparece em http://127.0.0.1:8000/api/health
echo.
echo   Pronto. Agora:
echo     1^) feche a janela da API no X (nao digite nada no terminal dela)
echo     2^) se a interface ainda pedir token, rode ligar-celular.bat uma vez:
echo        ele liga o modo dono e o token deixa de ser pedido nesta maquina
echo     3^) rode:  .venv\Scripts\python iniciar.py
echo     4^) abra http://127.0.0.1:8000/api/health e confira version e skills
echo.
echo   Se aparecer alguma variavel nova em .env.example, copie a linha
echo   para o seu .env - o arquivo de exemplo nunca sobrescreve o seu.
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

:zipfalhou
echo.
echo   O download ou a copia falhou. Se a mensagem citar TLS ou conexao,
echo   tente de novo; se persistir, baixe o zip no navegador:
echo     https://codeload.github.com/vitor120956-max/Victor-Alexandre-/zip/refs/heads/arena/f26cfa7a-victor-alexandre
echo   e descompacte por cima desta pasta, mantendo .env, storage e .venv.
echo.
pause
exit /b 1

:falhou
echo.
echo   Nao consegui trocar de ramo. Rode "git status" e veja o que aparece.
echo.
pause
exit /b 1
