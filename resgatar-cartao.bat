@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo.
echo   JARVIS - resgatar as fotos do cartao microSD do celular
echo.
echo   Serve quando o celular nao fala mais com o PC pela USB: o cartao sai
echo   do aparelho, entra no leitor e as fotos vem para o PC. O conector do
echo   celular nao e usado em nenhum momento.
echo.
echo   O cartao e tratado como SOMENTE LEITURA: nada e apagado nem movido nele.
echo   Versao: 0.63.0
echo.
echo   Como fazer:
echo     1. desligue o celular;
echo     2. tire o cartao microSD (na bandeja, com o pino de ejetar, ou na
echo        lateral conforme o modelo);
echo     3. encaixe no adaptador SD e ponha no leitor de cartao do PC;
echo     4. rode este .bat.
echo.
echo   Se ja sabe a letra do cartao, rode:
echo     resgatar-cartao.bat E:
echo.
if not exist "resgatar-cartao.ps1" goto semps1
pause
echo.
powershell -NoProfile -ExecutionPolicy Bypass -File "resgatar-cartao.ps1" %*
set CODIGO=%errorlevel%
echo.
echo   Codigo do resgate: %CODIGO%
echo     0 = copiou tudo (o que ja existia foi pulado)
echo     1 = nao achei cartao nem dado nele
echo     2 = copiou, mas alguns arquivos deram erro (lista na tela)
echo     3 = nao ha espaco suficiente no destino
echo.
pause
exit /b 0

:semps1
echo   Nao achei resgatar-cartao.ps1 nesta pasta.
echo   Rode atualizar.bat para baixar a versao completa.
echo.
pause
exit /b 1
