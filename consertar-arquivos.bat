@echo off
chcp 65001 >nul
cd /d "%~dp0"
title JARVIS - consertar arquivos da pasta
setlocal enabledelayedexpansion

echo.
echo   JARVIS - consertar os arquivos desta pasta
echo   ----------------------------------------------------------------
echo   Este atalho existe por causa de um erro facil de cometer:
echo   copiar a linha inteira do prompt, com o "D:\JARVIS>" na frente.
echo.
echo   No prompt do Windows, o sinal ">" nao e enfeite: ele manda a saida
echo   do comando para um arquivo. Digitar
echo       D:\JARVIS^>atualizar.bat
echo   faz o Windows criar - ou ZERAR - um arquivo chamado atualizar.bat.
echo   O arquivo continua ali, com 0 byte, e "nao faz nada" quando roda.
echo.
echo   Regra: copiar so o comando. O "D:\JARVIS>" e do Windows, nao seu.
echo.
echo   Conferindo os arquivos principais...
echo.

set RUINS=
for %%F in (iniciar-jarvis.bat atualizar.bat consertar-arquivos.bat iniciar.py package.json web-dist\index.html) do (
  if not exist "%%F" (
    echo     FALTA    %%F
    set RUINS=1
  ) else (
    for %%S in ("%%F") do (
      if %%~zS LSS 100 (
        echo     VAZIO    %%F  ^(%%~zS bytes^)
        set RUINS=1
      ) else (
        echo     ok       %%F  ^(%%~zS bytes^)
      )
    )
  )
)

if not defined RUINS goto tudo_bem

echo.
echo   Ha arquivo faltando ou vazio. Vou baixar a versao atual do GitHub
echo   e copiar SO os arquivos que faltam - nada seu e apagado.
echo   Ficam intocados: .env, storage, .venv, node_modules e .git.
echo.
pause
echo   baixando e copiando (pode levar alguns minutos)...
echo.

powershell -NoProfile -ExecutionPolicy Bypass -Command "$ErrorActionPreference='Stop'; [Net.ServicePointManager]::SecurityProtocol=[Net.SecurityProtocolType]::Tls12; $z=$env:TEMP+'\jarvis-novo.zip'; $d=$env:TEMP+'\jarvis-novo'; Invoke-WebRequest -Uri 'https://codeload.github.com/vitor120956-max/Victor-Alexandre-/zip/refs/heads/arena/f26cfa7a-victor-alexandre' -OutFile $z; if(Test-Path $d){Remove-Item $d -Recurse -Force}; Expand-Archive -LiteralPath $z -DestinationPath $d -Force; $r=(Get-ChildItem -LiteralPath $d -Directory | Select-Object -First 1).FullName; robocopy $r '%CD%' /E /XF .env /XD .venv storage node_modules .git /NFL /NDL /NJH /NJS; if($LASTEXITCODE -ge 8){exit 1}else{exit 0}"

if errorlevel 1 goto baixou_errado

echo.
echo   Arquivos restaurados. Conferindo de novo:
echo.
set RUINS=
for %%F in (iniciar-jarvis.bat atualizar.bat iniciar.py) do (
  for %%S in ("%%F") do (
    if %%~zS LSS 100 (
      echo     ainda VAZIO  %%F
      set RUINS=1
    ) else (
      echo     ok           %%F  ^(%%~zS bytes^)
    )
  )
)
if defined RUINS goto nao_deu
goto pronto

:nao_deu
echo.
echo   O download veio, mas os arquivos continuam vazios. Isso acontece se
echo   esta pasta nao tem permissao de escrita (pendrive protegido) ou se
echo   um antivirus bloqueou a copia dos .bat.
echo   Alternativa: baixe o zip no navegador e descompacte por cima,
echo   mantendo .env, storage e .venv.
echo.
pause
exit /b 1

:baixou_errado
echo.
echo   O download falhou. Duas causas comuns:
echo     - sem internet: conecte e rode de novo;
echo     - antivirus bloqueando o PowerShell.
echo   Alternativa: baixe o zip no navegador e descompacte por cima desta pasta:
echo     https://codeload.github.com/vitor120956-max/Victor-Alexandre-/zip/refs/heads/arena/f26cfa7a-victor-alexandre
echo   Mantenha .env, storage e .venv.
echo.
pause
exit /b 1

:pronto
echo.
echo   Pronto. Agora clique duas vezes em iniciar-jarvis.bat
echo   (no Explorador de Arquivos, nao digitando o nome).
echo.
pause
exit /b 0

:tudo_bem
echo.
echo   Tudo no lugar: nenhum arquivo faltando ou vazio.
echo   Se o JARVIS ainda nao sobe, clique duas vezes em iniciar-jarvis.bat
echo   e copie para mim a mensagem que aparecer.
echo.
pause
exit /b 0
