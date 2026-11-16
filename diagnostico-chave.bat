@echo off
chcp 65001 >nul
cd /d "%~dp0"
title JARVIS - diagnostico da pagina da chave
echo.
echo   JARVIS - por que ele nao ve o painel da chave
echo   Versao: 0.91.26
echo   ----------------------------------------------------------------
echo   Isto NAO cria chave e NAO clica em nada.
echo.
echo   Ele mede o que o Windows consegue ler da janela do Chrome e
echo   escreve um relatorio no arquivo chave-leitura.txt, nesta pasta.
echo.
echo   Dica: abra o painel "Create API key" na tela antes de rodar
echo   (clique em New key), que ai eu meco com o painel aberto.
echo.
if not exist ".venv\Scripts\python.exe" goto semvenv
if not exist "chave-no-navegador.py" goto semscript
set "PYTHON=.venv\Scripts\python.exe"
echo.
"%PYTHON%" chave-no-navegador.py --diagnostico
echo.
echo   ----------------------------------------------------------------
echo   O relatorio esta em: chave-leitura.txt (nesta pasta).
echo   Me mande esse arquivo.
echo.
pause
exit /b 0

:semvenv
echo   Nao encontrei o .venv nesta pasta.
echo   Rode iniciar-jarvis.bat uma vez (ele cria o ambiente) e volte aqui.
pause
exit /b 1

:semscript
echo   Nao encontrei chave-no-navegador.py nesta pasta.
echo   Voce esta na pasta certa do JARVIS? A mesma do iniciar-jarvis.bat.
pause
exit /b 1
