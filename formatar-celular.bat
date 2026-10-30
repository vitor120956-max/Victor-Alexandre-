@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo.
echo   JARVIS - zerar o celular pelos BOTOES (sem tela, sem cabo)
echo.
echo   O toque da tela morreu e a porta USB perdeu os dados. Mesmo assim o
echo   Android tem um menu de fabrica que se opera so com Volume e Power:
echo   o recovery. Este guia leva voce por ele, com pausa em cada passo.
echo.
echo   ATENCAO: depois do reset o Android exige a MESMA conta Google que
echo   estava no aparelho (FRP). Sem essa senha o celular nao volta a
echo   funcionar nem com a tela consertada. O guia pergunta isso primeiro
echo   e, se a resposta for 'nao sei', ele para sem zerar.
echo.
echo   Versao: 0.64.0
echo.
echo   Para so LER o roteiro, sem responder nada:
echo     formatar-celular.bat -Roteiro
echo.
if not exist "formatar-celular.ps1" goto semps1
pause
echo.
powershell -NoProfile -ExecutionPolicy Bypass -File "formatar-celular.ps1" %*
set CODIGO=%errorlevel%
echo.
echo   Codigo do guia: %CODIGO%
echo     0 = percorreu os passos (o aparelho foi zerado)
echo     1 = parou no meio, nada foi apagado
echo     4 = nao sabe a conta Google: o guia NAO zerou (risco de FRP)
echo.
pause
exit /b 0

:semps1
echo   Nao achei formatar-celular.ps1 nesta pasta.
echo   Rode atualizar.bat para baixar a versao completa.
echo.
pause
exit /b 1
