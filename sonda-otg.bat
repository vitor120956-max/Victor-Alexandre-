@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo.
echo   JARVIS - ver com qual driver o Windows esta falando com o celular
echo.
echo   Serve para saber, sem adivinhar, se o erro do scrcpy --otg
echo   ("Could not find any USB device") e falta de driver ou outra coisa.
echo   Versao: 0.62.7
echo.
if not exist "sonda-otg.ps1" goto semsonda
set CODIGO=
powershell -NoProfile -ExecutionPolicy Bypass -File "sonda-otg.ps1"
set CODIGO=%errorlevel%
echo   Codigo da sonda: %CODIGO%
echo     0 = driver de OTG ok, pode abrir teclado-pelo-pc.bat
echo     1 = falta o driver (Zadig) - o passo a passo esta acima
echo     2 = o Windows nao ve o celular na USB (cabo, porta ou tela apagada)
echo     3 = a consulta ao Windows falhou (nao da para concluir nada)
echo.
if not "%CODIGO%"=="2" goto fim
echo   Quer que eu fique olhando por 30 segundos, para voce mexer no cabo
echo   e na tela sem correr contra o tempo?
echo.
set RESP=
set /p RESP=  Digite S e Enter para esperar (ou so Enter para sair): 
echo.
if /i not "%RESP%"=="S" goto fim
powershell -NoProfile -ExecutionPolicy Bypass -File "sonda-otg.ps1" -Segundos 30
echo.
echo   Codigo depois da espera: %errorlevel%
echo.
goto fim

:fim
echo.
echo   Se o codigo foi 2 (nada na USB), rode  teste-cabo.bat  para separar
echo   cabo, porta e conector do celular.
echo.
echo   Cole esta tela no chat do JARVIS se quiser que eu leia.
echo.
pause
exit /b 0

:semsonda
echo   Nao achei sonda-otg.ps1 nesta pasta.
echo   Rode atualizar.bat para baixar a versao completa.
echo.
pause
exit /b 1
