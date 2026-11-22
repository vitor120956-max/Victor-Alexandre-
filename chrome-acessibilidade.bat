@echo off
chcp 65001 >nul
cd /d "%~dp0"
title JARVIS - abrir o Chrome com acessibilidade ligada
echo.
echo   JARVIS - abrir o Chrome com a acessibilidade ligada
echo   Versao: 0.92.9
echo   ----------------------------------------------------------------
echo.
echo   O JARVIS le a pagina do Chrome pela acessibilidade do Windows.
echo   O Chrome liga e desliga essa publicacao sozinho; este atalho o
echo   abre ja com ela ligada, para nao depender disso.
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
taskkill /IM chrome.exe /T /F >nul 2>&1
call :esperar_fechar
echo   Abrindo o Chrome com a acessibilidade ligada...
set "CHROME="
if exist "%ProgramFiles%\Google\Chrome\Application\chrome.exe" set "CHROME=%ProgramFiles%\Google\Chrome\Application\chrome.exe"
if not defined CHROME if exist "%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe" set "CHROME=%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"
if not defined CHROME if exist "%LocalAppData%\Google\Chrome\Application\chrome.exe" set "CHROME=%LocalAppData%\Google\Chrome\Application\chrome.exe"
if not defined CHROME goto semchrome
echo   (Se o Chrome ainda estiver fechando, ele pode reaproveitar a janela antiga
echo    e ignorar a opcao. Se o diagnostico continuar vendo 3 elementos, rode
echo    este atalho de novo.)
start "" "%CHROME%" --force-renderer-accessibility "https://openrouter.ai/settings/keys"
echo.
echo   Pronto. O Chrome abriu na pagina das chaves.
echo   Agora rode o pegar-chave.bat: o JARVIS continua sozinho daqui.
echo.
pause
exit /b 0

:esperar_fechar
rem Abrir o Chrome de novo antes de o antigo sair faz o Windows entregar a
rem chamada ao processo antigo, e a opcao de acessibilidade e ignorada.
rem Aqui a espera e de verdade: ate 15 segundos, conferindo a lista.
set /a "tentativas=0"
:laco_fechar
tasklist /FI "IMAGENAME eq chrome.exe" 2>nul | find /I "chrome.exe" >nul
if errorlevel 1 goto fechou
set /a "tentativas+=1"
if %tentativas% GEQ 15 goto fechou
timeout /t 1 >nul
goto laco_fechar
:fechou
timeout /t 1 >nul
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
