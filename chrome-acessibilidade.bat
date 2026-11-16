@echo off
chcp 65001 >nul
cd /d "%~dp0"
title JARVIS - abrir o Chrome com acessibilidade ligada
echo.
echo   JARVIS - abrir o Chrome com a acessibilidade ligada
echo   Versao: 0.91.25
echo   ----------------------------------------------------------------
echo.
echo   O JARVIS le a pagina do Chrome pela acessibilidade do Windows.
echo   Em algumas instalacoes o Chrome so publica a pagina quando e
echo   iniciado com essa opcao ligada.
echo.
echo   ATENCAO: este atalho FECHA o Chrome antes de abrir de novo.
echo   As abas voltam (o Chrome restaura a sessao), mas salve o que
echo   estiver escrevendo antes de continuar.
echo.
set "segue="
set /p "segue=Tecle Enter para continuar ou N para sair: "
if /i "%segue%"=="N" goto fim
echo.
echo   Fechando o Chrome...
taskkill /IM chrome.exe >nul 2>&1
timeout /t 2 >nul
set "CHROME="
if exist "%ProgramFiles%\Google\Chrome\Application\chrome.exe" set "CHROME=%ProgramFiles%\Google\Chrome\Application\chrome.exe"
if not defined CHROME if exist "%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe" set "CHROME=%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"
if not defined CHROME if exist "%LocalAppData%\Google\Chrome\Application\chrome.exe" set "CHROME=%LocalAppData%\Google\Chrome\Application\chrome.exe"
if not defined CHROME goto semchrome
echo   Abrindo o Chrome com a acessibilidade ligada...
start "" "%CHROME%" --force-renderer-accessibility "https://openrouter.ai/settings/keys"
echo.
echo   Pronto. O Chrome abriu na pagina das chaves.
echo   Agora rode o pegar-chave.bat: o JARVIS continua sozinho daqui.
echo.
pause
exit /b 0

:semchrome
echo   Nao achei o chrome.exe nos lugares de sempre.
echo   Abra o Chrome na mao e rode o pegar-chave.bat de novo.
pause
exit /b 1

:fim
echo.
echo   Sem problema. Nada foi fechado.
pause
exit /b 1
