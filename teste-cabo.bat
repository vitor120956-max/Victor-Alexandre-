@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo.
echo   JARVIS - teste de cabo, porta e conector do celular
echo.
echo   Responde: quando eu plugo o celular, o Windows muda em alguma coisa?
echo   Se nao mudar, nao e driver (o Zadig so lista o que aparece).
echo   Versao: 0.62.6
echo.
echo   Antes de comecar:
echo     - feche o Gerenciador de Dispositivos e janelas do Explorer abertas
echo       na pasta do celular;
echo     - deixe a tela do celular acesa;
echo     - tenha em maos outro cabo micro-USB, se tiver.
echo.
if not exist "teste-cabo.ps1" goto semps1
pause
echo.
powershell -NoProfile -ExecutionPolicy Bypass -File "teste-cabo.ps1"
set CODIGO=%errorlevel%
echo.
echo   Codigo do teste: %CODIGO%
echo     0 = o celular aparece (VID_04E8): agora sim e driver, rode sonda-otg.bat
echo     1 = apareceu algo, mas nada Samsung: cole a tela no chat
echo     2 = NADA apareceu: e fisico (conector, cabo ou porta), nao driver
echo         -> rode  vigiar-cabo.bat  para saber se e solda fria ou pino quebrado
echo     3 = a leitura do Windows falhou: rode de novo
echo.
pause
exit /b 0

:semps1
echo   Nao achei teste-cabo.ps1 nesta pasta.
echo   Rode atualizar.bat para baixar a versao completa.
echo.
pause
exit /b 1
