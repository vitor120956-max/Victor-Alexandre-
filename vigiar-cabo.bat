@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo.
echo   JARVIS - teste de pressao do conector do celular
echo.
echo   Prova, em um minuto, se o conector AINDA passa dados em algum angulo.
echo   Isso separa 'solda fria' (da para segurar com calco e trabalhar) de
echo   'pino quebrado' (so solda).
echo.
echo   Como fazer, com o cabo plugado no PC e no celular:
echo     - pressione o plugue para dentro, com cuidado, sem forcar;
echo     - incline de leve para cima, para baixo, para os lados;
echo     - gire o plugue devagar;
echo     - encoste uma cunha fina (papel dobrado) entre cabo e aparelho.
echo.
echo   A janela olha por 60 segundos e avisa na hora em que QUALQUER
echo   aparelho aparecer no Windows.
echo   Versao: 0.62.6
echo.
echo   Antes de comecar: deixe a tela do celular acesa e feche o Gerenciador
echo   de Dispositivos e janelas do Explorer abertas na pasta do celular.
echo.
if not exist "teste-cabo.ps1" goto semps1
pause
echo.
powershell -NoProfile -ExecutionPolicy Bypass -File "teste-cabo.ps1" -Vigiar 60
set CODIGO=%errorlevel%
echo.
echo   Codigo do teste: %CODIGO%
echo     0 = o celular apareceu em algum angulo: e solda fria, da para calcar
echo     1 = apareceu algo, mas nada Samsung: cole a tela no chat
echo     2 = nada apareceu em 60s de pressao: e pino quebrado (solda)
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
